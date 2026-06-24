"""P4-5-W2: Iterative creation session.

A session is a long-running multi-turn dialogue with a generative model.

State machine
-------------
::

    draft  ─►  review  ─►  final      (user picks "best" variant)
       │         │
       │         └────►  discarded   (user drops the session)
       └────────────────────────►    discarded at any time

Each session keeps:
  * ``prompt_versions``    — the evolving text prompt and its parameters
  * ``generated_assets``   — outputs produced for each prompt version
  * ``feedback``           — user feedback entries (thumbs / text)
  * ``ab_tests``           — concurrent variants (A/B/C) and their scores
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from .store import JsonTable, _now_iso


class SessionState(str, Enum):
    DRAFT = "draft"
    REVIEW = "review"
    FINAL = "final"
    DISCARDED = "discarded"


# ── Dataclasses ────────────────────────────────────────────────────────────
@dataclass
class PromptVersion:
    """A single revision of the prompt."""

    version_id: str
    parent_version_id: Optional[str]
    text: str
    params: Dict[str, Any]
    created_at: str
    note: Optional[str] = None


@dataclass
class GeneratedAsset:
    """One concrete output tied to a prompt version."""

    asset_id: str
    prompt_version_id: str
    modality: str  # "image" | "video" | "audio" | "voice" | "storyboard"
    url: str
    seed: int
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _now_iso()


@dataclass
class FeedbackEntry:
    """User feedback that drives the next iteration."""

    feedback_id: str
    asset_id: Optional[str]
    rating: int  # 1-5; 0 = pure-text feedback
    text: Optional[str]
    created_at: str

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _now_iso()


@dataclass
class ABTest:
    """A concurrent A/B (or A/B/C) variant run.

    Variants share a ``parent_prompt_version_id`` and are scored via the
    QA workflow (consistency.py).
    """

    ab_id: str
    parent_prompt_version_id: str
    variants: List[PromptVersion]
    scores: Dict[str, float] = field(default_factory=dict)
    winner_variant_id: Optional[str] = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _now_iso()


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def _serialise(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (PromptVersion, GeneratedAsset, FeedbackEntry, ABTest)):
        return asdict(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


# ── Session store ───────────────────────────────────────────────────────────
class SessionStore:
    """Thread-safe in-memory + JSONL-backed session storage.

    Three tables:
      * ``sessions``       — one row per session (state, owner, project, prompt history...)
      * ``session_assets`` — every generated asset linked to its session + version
      * ``session_feedback`` — feedback entries (1 row per ``POST /feedback``)
      * ``session_ab``     — A/B variant runs

    Keyed by ``session_id`` (UUID-12). Stable across processes via JSONL.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.sessions = JsonTable("sessions")
        self.assets = JsonTable("session_assets")
        self.feedback = JsonTable("session_feedback")
        self.ab = JsonTable("session_ab")

    # ── CRUD ──────────────────────────────────────────────────────────
    def create_session(
        self,
        owner_id: str,
        project_id: str,
        modality: str,
        initial_prompt: str,
        params: Optional[Dict[str, Any]] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            sid = _uuid()
            pv_id = _uuid()
            prompt = PromptVersion(
                version_id=pv_id,
                parent_version_id=None,
                text=initial_prompt,
                params=params or {},
                created_at=_now_iso(),
                note="initial",
            )
            row = {
                "session_id": sid,
                "owner_id": owner_id,
                "project_id": project_id,
                "modality": modality,
                "title": title or f"session-{sid[:6]}",
                "state": SessionState.DRAFT.value,
                "best_variant_id": None,
                "prompt_versions": [asdict(prompt)],
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
            self.sessions.insert(row)
            return row

    def list_sessions(
        self,
        owner_id: Optional[str] = None,
        project_id: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        rows = self.sessions.all()
        if owner_id:
            rows = [r for r in rows if r.get("owner_id") == owner_id]
        if project_id:
            rows = [r for r in rows if r.get("project_id") == project_id]
        if state:
            rows = [r for r in rows if r.get("state") == state]
        rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
        return rows[offset : offset + limit]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.sessions.find_one(session_id=session_id)

    def update_session(self, session_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.sessions.update("session_id", session_id, patch)

    def delete_session(self, session_id: str) -> bool:
        # cascade-delete assets / feedback / ab rows
        with self._lock:
            self.assets.delete("session_id", session_id)
            self.feedback.delete("session_id", session_id)
            self.ab.delete("session_id", session_id)
            return self.sessions.delete("session_id", session_id) > 0

    # ── Multi-turn dialogue ──────────────────────────────────────────
    def iterate_prompt(
        self,
        session_id: str,
        new_text: str,
        parent_version_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        note: Optional[str] = None,
    ) -> Optional[PromptVersion]:
        with self._lock:
            sess = self.get_session(session_id)
            if not sess:
                return None
            if sess.get("state") == SessionState.DISCARDED.value:
                return None
            if not parent_version_id:
                versions = sess.get("prompt_versions") or []
                parent_version_id = versions[-1]["version_id"] if versions else None
            pv = PromptVersion(
                version_id=_uuid(),
                parent_version_id=parent_version_id,
                text=new_text,
                params=params or {},
                created_at=_now_iso(),
                note=note,
            )
            versions = list(sess.get("prompt_versions") or [])
            versions.append(asdict(pv))
            patch = {
                "prompt_versions": versions,
                "state": SessionState.REVIEW.value,
                "updated_at": _now_iso(),
            }
            self.update_session(session_id, patch)
            return pv

    def add_asset(
        self,
        session_id: str,
        prompt_version_id: str,
        modality: str,
        url: str,
        seed: int = 0,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        sess = self.get_session(session_id)
        if not sess:
            return None
        asset = GeneratedAsset(
            asset_id=_uuid(),
            prompt_version_id=prompt_version_id,
            modality=modality,
            url=url,
            seed=seed,
            metrics=metrics or {},
        )
        row = asdict(asset)
        row["session_id"] = session_id
        self.assets.insert(row)
        return row

    def list_assets(self, session_id: str) -> List[Dict[str, Any]]:
        return self.assets.find(session_id=session_id)

    def add_feedback(
        self,
        session_id: str,
        rating: int,
        text: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        sess = self.get_session(session_id)
        if not sess:
            return None
        fb = FeedbackEntry(
            feedback_id=_uuid(),
            asset_id=asset_id,
            rating=max(-1, min(5, int(rating))),
            text=text,
            created_at=_now_iso(),
        )
        row = asdict(fb)
        row["session_id"] = session_id
        self.feedback.insert(row)
        # feedback implies the session is in / moved to review state
        if sess.get("state") == SessionState.DRAFT.value:
            self.update_session(session_id, {"state": SessionState.REVIEW.value})
        return row

    def list_feedback(self, session_id: str) -> List[Dict[str, Any]]:
        return self.feedback.find(session_id=session_id)

    # ── A/B testing ──────────────────────────────────────────────────
    def start_ab(
        self,
        session_id: str,
        parent_prompt_version_id: str,
        variants: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """``variants`` is a list of ``{text, params, note}`` dicts (>=2)."""
        sess = self.get_session(session_id)
        if not sess:
            return None
        if len(variants) < 2:
            return None
        pv_objs: List[PromptVersion] = []
        for v in variants:
            pv_objs.append(
                PromptVersion(
                    version_id=_uuid(),
                    parent_version_id=parent_prompt_version_id,
                    text=v.get("text", ""),
                    params=v.get("params", {}) or {},
                    created_at=_now_iso(),
                    note=v.get("note", "ab-variant"),
                )
            )
        ab = ABTest(
            ab_id=_uuid(),
            parent_prompt_version_id=parent_prompt_version_id,
            variants=pv_objs,
        )
        row = asdict(ab)
        row["session_id"] = session_id
        row["status"] = "running"
        self.ab.insert(row)
        return row

    def list_ab(self, session_id: str) -> List[Dict[str, Any]]:
        return self.ab.find(session_id=session_id)

    def score_ab(self, ab_id: str, scores: Dict[str, float]) -> Optional[Dict[str, Any]]:
        return self.ab.update(
            "ab_id",
            ab_id,
            {
                "scores": scores,
                "updated_at": _now_iso(),
            },
        )

    def pick_best(self, ab_id: str) -> Optional[Dict[str, Any]]:
        ab = self.ab.find_one(ab_id=ab_id)
        if not ab:
            return None
        scores: Dict[str, float] = ab.get("scores") or {}
        if not scores:
            return None
        winner_variant_id = max(scores, key=lambda k: scores[k])
        self.ab.update("ab_id", ab_id, {"winner_variant_id": winner_variant_id, "status": "decided"})
        # promote winner into the session prompt history
        sid = ab["session_id"]
        variants: List[Dict[str, Any]] = ab.get("variants") or []
        winner = next((v for v in variants if v["version_id"] == winner_variant_id), None)
        if winner:
            sess = self.get_session(sid)
            if sess:
                versions = list(sess.get("prompt_versions") or [])
                versions.append(winner)
                self.update_session(
                    sid,
                    {
                        "best_variant_id": winner_variant_id,
                        "prompt_versions": versions,
                        "state": SessionState.FINAL.value,
                        "updated_at": _now_iso(),
                    },
                )
        return self.ab.find_one(ab_id=ab_id)

    # ── Final / discard ──────────────────────────────────────────────
    def finalize(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.update_session(
            session_id,
            {"state": SessionState.FINAL.value, "updated_at": _now_iso()},
        )

    def discard(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.update_session(
            session_id,
            {"state": SessionState.DISCARDED.value, "updated_at": _now_iso()},
        )


# ── Module-level singleton (mirrors get_session_store pattern) ─────────────
_STORE: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    global _STORE
    if _STORE is None:
        _STORE = SessionStore()
    return _STORE


# ── IterativeSession (object-oriented facade) ──────────────────────────────
class IterativeSession:
    """High-level wrapper for one user session.

    Keeps a cached reference to the underlying ``SessionStore`` row.
    Not used by the FastAPI layer directly but exposed for tests + future
    in-process callers (Celery workers, IDE plugins, ...).
    """

    def __init__(self, store: SessionStore, row: Dict[str, Any]) -> None:
        self.store = store
        self.row = row

    @property
    def session_id(self) -> str:
        return self.row["session_id"]

    @property
    def state(self) -> SessionState:
        return SessionState(self.row.get("state", "draft"))

    @property
    def prompt_versions(self) -> List[PromptVersion]:
        return [PromptVersion(**pv) for pv in self.row.get("prompt_versions", [])]

    @property
    def assets(self) -> List[Dict[str, Any]]:
        return self.store.list_assets(self.session_id)

    @property
    def feedback(self) -> List[Dict[str, Any]]:
        return self.store.list_feedback(self.session_id)

    def refresh(self) -> None:
        fresh = self.store.get_session(self.session_id)
        if fresh:
            self.row = fresh

    def iterate(self, text: str, **kwargs: Any) -> PromptVersion:
        pv = self.store.iterate_prompt(self.session_id, text, **kwargs)
        if pv is None:
            raise ValueError(f"cannot iterate session {self.session_id}")
        self.refresh()
        return pv

    def record_asset(self, prompt_version_id: str, modality: str, url: str, **kw: Any) -> Dict[str, Any]:
        row = self.store.add_asset(self.session_id, prompt_version_id, modality, url, **kw)
        if row is None:
            raise ValueError(f"session {self.session_id} not found")
        return row

    def submit_feedback(self, rating: int, text: Optional[str] = None, asset_id: Optional[str] = None) -> Dict[str, Any]:
        row = self.store.add_feedback(self.session_id, rating, text, asset_id)
        if row is None:
            raise ValueError(f"session {self.session_id} not found")
        return row

    def start_ab(self, parent_prompt_version_id: str, variants: List[Dict[str, Any]]) -> Dict[str, Any]:
        row = self.store.start_ab(self.session_id, parent_prompt_version_id, variants)
        if row is None:
            raise ValueError("A/B requires ≥2 variants and an existing session")
        return row

    def score_ab(self, ab_id: str, scores: Dict[str, float]) -> Dict[str, Any]:
        row = self.store.score_ab(ab_id, scores)
        if row is None:
            raise ValueError(f"A/B {ab_id} not found")
        return row

    def pick_best(self, ab_id: str) -> Dict[str, Any]:
        row = self.store.pick_best(ab_id)
        if row is None:
            raise ValueError(f"A/B {ab_id} not found or not yet scored")
        self.refresh()
        return row

    def finalize(self) -> None:
        self.store.finalize(self.session_id)
        self.refresh()

    def discard(self) -> None:
        self.store.discard(self.session_id)
        self.refresh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "owner_id": self.row.get("owner_id"),
            "project_id": self.row.get("project_id"),
            "modality": self.row.get("modality"),
            "title": self.row.get("title"),
            "state": self.state.value,
            "best_variant_id": self.row.get("best_variant_id"),
            "prompt_versions": [asdict(pv) for pv in self.prompt_versions],
            "assets": self.assets,
            "feedback": self.feedback,
            "ab_tests": self.store.list_ab(self.session_id),
            "created_at": self.row.get("created_at"),
            "updated_at": self.row.get("updated_at"),
        }


__all__ = [
    "IterativeSession",
    "SessionState",
    "PromptVersion",
    "GeneratedAsset",
    "FeedbackEntry",
    "ABTest",
    "SessionStore",
    "get_session_store",
]