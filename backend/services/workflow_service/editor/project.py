"""P4-6-W1 Project Management — 项目 / 版本快照 / 协作锁 / 模板加载.

Project model:
  id / name / timeline_json / output_url / status / owner / version
  snapshots[]       - named snapshots (id, ts, timeline, label)
  undo_stack[]      - last 50 timeline states (for undo)
  redo_stack[]      - undone states (for redo)
  collaborators[]   - {user_id, role, last_seen, lock_id?}
  lock              - {user_id, since, ttl_sec} (single-writer lock)

Operations:
  create / get / update / delete / list
  snapshot / undo / redo / restore_snapshot
  lock / unlock / heartbeat (lock auto-expires after ttl)
  load_template (从 50+ workflow templates 加载到项目)
"""
from __future__ import annotations

import copy
import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)


class TemplateFetchError(LookupError):
    """Raised when a template cannot be located in the workflow registry.

    Carries the underlying reason so callers (and tests) can distinguish
    between ``"not_found"`` (legitimate miss) and ``"registry_unavailable"``
    (the catalog module could not be imported, e.g. in isolated unit tests).
    """

    def __init__(self, message: str, *,
                 reason: str = "not_found",
                 template_id: Optional[str] = None,
                 available: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.template_id = template_id
        self.available = list(available or [])


@dataclass
class EditorProject:
    id: str
    name: str
    timeline: Dict[str, Any] = field(default_factory=dict)
    output_url: str = ""
    status: str = "draft"           # draft / editing / rendering / done
    owner: str = "system"
    version: int = 1
    snapshots: List[Dict[str, Any]] = field(default_factory=list)
    undo_stack: List[Dict[str, Any]] = field(default_factory=list)
    redo_stack: List[Dict[str, Any]] = field(default_factory=list)
    collaborators: List[Dict[str, Any]] = field(default_factory=list)
    lock: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    template_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "timeline": self.timeline,
            "output_url": self.output_url,
            "status": self.status,
            "owner": self.owner,
            "version": self.version,
            "snapshots": list(self.snapshots),
            "undo_depth": len(self.undo_stack),
            "redo_depth": len(self.redo_stack),
            "collaborators": list(self.collaborators),
            "lock": self.lock,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "template_id": self.template_id,
        }


class ProjectStore:
    """In-memory project store with thread safety + lock TTL."""

    DEFAULT_LOCK_TTL = 60.0
    UNDO_LIMIT = 50

    def __init__(self) -> None:
        self._projects: Dict[str, EditorProject] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create(self, name: str, owner: str = "system",
               template_id: Optional[str] = None,
               timeline: Optional[Dict[str, Any]] = None,
               project_id: Optional[str] = None) -> EditorProject:
        if not name.strip():
            raise ValueError("name must be non-empty")
        pid = project_id or f"prj-{uuid.uuid4().hex[:12]}"
        with self._lock:
            if pid in self._projects:
                raise ValueError(f"project_exists: {pid}")
            proj = EditorProject(
                id=pid, name=name, owner=owner,
                template_id=template_id,
                timeline=timeline or {"clips": [], "cuts": [],
                                      "transitions": [], "effects": []},
            )
            self._projects[pid] = proj
        return proj

    def get(self, pid: str) -> Optional[EditorProject]:
        with self._lock:
            return self._projects.get(pid)

    def list(self, owner: Optional[str] = None,
             limit: int = 100) -> List[EditorProject]:
        limit = max(1, min(limit, 500))
        with self._lock:
            items = list(self._projects.values())
        if owner:
            items = [p for p in items if p.owner == owner]
        items.sort(key=lambda p: p.updated_at, reverse=True)
        return items[:limit]

    def update(self, pid: str,
               name: Optional[str] = None,
               timeline: Optional[Dict[str, Any]] = None,
               status: Optional[str] = None,
               output_url: Optional[str] = None,
               expected_version: Optional[int] = None
               ) -> EditorProject:
        with self._lock:
            proj = self._projects.get(pid)
            if proj is None:
                raise ValueError(f"project_not_found: {pid}")
            if expected_version is not None and \
                    proj.version != expected_version:
                raise ValueError(
                    f"version_conflict: have {proj.version}, "
                    f"expected {expected_version}")
            # Save undo snapshot before destructive change
            if timeline is not None:
                self._push_undo(proj, proj.timeline)
                proj.timeline = copy.deepcopy(timeline)
                proj.redo_stack.clear()
            if name is not None:
                if not name.strip():
                    raise ValueError("name must be non-empty")
                proj.name = name
            if status is not None:
                proj.status = status
            if output_url is not None:
                proj.output_url = output_url
            proj.version += 1
            proj.updated_at = time.time()
            return proj

    def delete(self, pid: str) -> bool:
        with self._lock:
            return self._projects.pop(pid, None) is not None

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------
    def _push_undo(self, proj: EditorProject,
                   old_timeline: Dict[str, Any]) -> None:
        proj.undo_stack.append({
            "version": proj.version,
            "timeline": copy.deepcopy(old_timeline),
            "ts": time.time(),
        })
        if len(proj.undo_stack) > self.UNDO_LIMIT:
            proj.undo_stack = proj.undo_stack[-self.UNDO_LIMIT:]

    def undo(self, pid: str) -> EditorProject:
        with self._lock:
            proj = self._projects.get(pid)
            if proj is None:
                raise ValueError(f"project_not_found: {pid}")
            if not proj.undo_stack:
                raise ValueError("nothing to undo")
            entry = proj.undo_stack.pop()
            proj.redo_stack.append({
                "version": proj.version,
                "timeline": copy.deepcopy(proj.timeline),
                "ts": time.time(),
            })
            proj.timeline = entry["timeline"]
            proj.version = entry["version"]
            proj.updated_at = time.time()
            return proj

    def redo(self, pid: str) -> EditorProject:
        with self._lock:
            proj = self._projects.get(pid)
            if proj is None:
                raise ValueError(f"project_not_found: {pid}")
            if not proj.redo_stack:
                raise ValueError("nothing to redo")
            entry = proj.redo_stack.pop()
            proj.undo_stack.append({
                "version": proj.version,
                "timeline": copy.deepcopy(proj.timeline),
                "ts": time.time(),
            })
            proj.timeline = entry["timeline"]
            proj.version = entry["version"]
            proj.updated_at = time.time()
            return proj

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------
    def snapshot(self, pid: str, label: str = "") -> EditorProject:
        with self._lock:
            proj = self._projects.get(pid)
            if proj is None:
                raise ValueError(f"project_not_found: {pid}")
            sid = "snap-" + hashlib.sha1(
                (str(time.time()) + pid).encode("utf-8")
            ).hexdigest()[:10]
            snap = {
                "id": sid,
                "label": label or f"snapshot@{proj.version}",
                "ts": time.time(),
                "version": proj.version,
                "timeline": copy.deepcopy(proj.timeline),
            }
            proj.snapshots.append(snap)
            if len(proj.snapshots) > 200:
                proj.snapshots = proj.snapshots[-200:]
            proj.updated_at = time.time()
            return proj

    def restore_snapshot(self, pid: str, snapshot_id: str) -> EditorProject:
        with self._lock:
            proj = self._projects.get(pid)
            if proj is None:
                raise ValueError(f"project_not_found: {pid}")
            snap = next(
                (s for s in proj.snapshots if s["id"] == snapshot_id),
                None)
            if snap is None:
                raise ValueError(f"snapshot_not_found: {snapshot_id}")
            self._push_undo(proj, proj.timeline)
            proj.timeline = copy.deepcopy(snap["timeline"])
            proj.version = snap["version"]
            proj.updated_at = time.time()
            return proj

    # ------------------------------------------------------------------
    # Collaboration / Lock
    # ------------------------------------------------------------------
    def _lock_alive(self, proj: EditorProject) -> bool:
        if not proj.lock:
            return False
        return (time.time() - proj.lock["since"]) < proj.lock["ttl_sec"]

    def acquire_lock(self, pid: str, user_id: str,
                     ttl_sec: Optional[float] = None) -> EditorProject:
        with self._lock:
            proj = self._projects.get(pid)
            if proj is None:
                raise ValueError(f"project_not_found: {pid}")
            if self._lock_alive(proj) and proj.lock["user_id"] != user_id:
                raise ValueError(
                    f"project_locked_by: {proj.lock['user_id']}")
            proj.lock = {
                "user_id": user_id,
                "since": time.time(),
                "ttl_sec": float(ttl_sec or self.DEFAULT_LOCK_TTL),
            }
            if not any(c.get("user_id") == user_id
                       for c in proj.collaborators):
                proj.collaborators.append({
                    "user_id": user_id, "role": "editor",
                    "last_seen": time.time(),
                })
            return proj

    def release_lock(self, pid: str, user_id: str) -> EditorProject:
        with self._lock:
            proj = self._projects.get(pid)
            if proj is None:
                raise ValueError(f"project_not_found: {pid}")
            if proj.lock and proj.lock["user_id"] == user_id:
                proj.lock = None
            return proj

    def heartbeat(self, pid: str, user_id: str) -> EditorProject:
        with self._lock:
            proj = self._projects.get(pid)
            if proj is None:
                raise ValueError(f"project_not_found: {pid}")
            if proj.lock and proj.lock["user_id"] == user_id:
                proj.lock["since"] = time.time()
            for c in proj.collaborators:
                if c.get("user_id") == user_id:
                    c["last_seen"] = time.time()
            return proj

    # ------------------------------------------------------------------
    # Template load — pull timeline from workflow template catalog
    # ------------------------------------------------------------------
    def load_template(self, pid: str, template_id: str) -> EditorProject:
        with self._lock:
            proj = self._projects.get(pid)
            if proj is None:
                raise ValueError(f"project_not_found: {pid}")
            try:
                tpl = self._fetch_template(template_id)
                template_reason = "loaded"
            except TemplateFetchError as exc:
                if exc.reason == "not_found":
                    # Hard miss — surface the error so the caller can fix it.
                    raise ValueError(
                        f"template_not_found: {template_id!r} "
                        f"(available: {exc.available[:5]})"
                    ) from exc
                # registry_unavailable — fall back to a synthetic template
                # so the editor remains usable in isolated tests.
                tpl = self._synthetic_template(template_id)
                template_reason = exc.reason
            # The template's "nodes" become placeholder clips
            clips: List[Dict[str, Any]] = []
            cursor = 0.0
            for n in tpl.get("nodes", []):
                dur = float(n.get("default_duration", 3.0))
                clips.append({
                    "id": f"{pid}-{n['id']}",
                    "src": n.get("default_src", ""),
                    "start": cursor,
                    "end": cursor + dur,
                    "duration": dur,
                    "node_type": n.get("node_type", "video"),
                    "name": n.get("name", n["id"]),
                })
                cursor += dur
            new_timeline: Dict[str, Any] = {
                "clips": clips,
                "cuts": [],
                "transitions": [],
                "effects": [],
                "template_meta": {
                    "template_id": template_id,
                    "template_name": tpl.get("name", ""),
                    "loaded_at": time.time(),
                    "template_source": template_reason,
                    "template_synthetic": bool(tpl.get("_synthetic")),
                },
            }
            self._push_undo(proj, proj.timeline)
            proj.timeline = new_timeline
            proj.template_id = template_id
            proj.version += 1
            proj.updated_at = time.time()
            return proj

    def _fetch_template(self, template_id: str) -> Dict[str, Any]:
        """Look up ``template_id`` in the workflow template registry.

        Raises :class:`TemplateFetchError` when the template cannot be
        located.  Two reasons are exposed via ``exc.reason``:

          * ``"registry_unavailable"`` — the catalog module could not be
            imported (e.g. running the editor in isolation).  Callers may
            decide to substitute a synthetic template themselves.
          * ``"not_found"`` — the registry was importable but did not
            contain the requested id.
        """
        try:
            from services.workflow_service.templates import (
                WORKFLOW_TEMPLATES, get_template,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "project.load_template.registry_unavailable: "
                "template_id=%r err=%s: %s",
                template_id, exc.__class__.__name__, exc,
            )
            raise TemplateFetchError(
                f"template registry unavailable for {template_id!r}: "
                f"{exc.__class__.__name__}: {exc}",
                reason="registry_unavailable",
                template_id=template_id,
            ) from exc
        try:
            return get_template(template_id)
        except KeyError as exc:
            _log.info(
                "project.load_template.get_template_miss: "
                "template_id=%r falling back to linear scan",
                template_id,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "project.load_template.get_template_error: "
                "template_id=%r err=%s: %s — falling back to linear scan",
                template_id, exc.__class__.__name__, exc,
            )
        for t in WORKFLOW_TEMPLATES:
            if t.get("id") == template_id:
                return t
        available = [t.get("id") for t in WORKFLOW_TEMPLATES
                     if isinstance(t, dict) and t.get("id")]
        _log.info(
            "project.load_template.not_found: template_id=%r "
            "available_count=%d",
            template_id, len(available),
        )
        raise TemplateFetchError(
            f"template not found: {template_id!r}",
            reason="not_found",
            template_id=template_id,
            available=available[:10],
        )

    @staticmethod
    def _synthetic_template(template_id: str) -> Dict[str, Any]:
        """Synthetic fallback used when the registry is unavailable.

        Returned with ``_synthetic=True`` so callers can distinguish from
        real catalog entries.
        """
        return {
            "id": template_id,
            "name": f"Stub Template {template_id}",
            "description": "synthetic template for editor isolation",
            "_synthetic": True,
            "_reason": "registry_unavailable",
            "nodes": [
                {"id": "intro", "node_type": "video", "name": "Intro",
                 "default_duration": 3.0, "default_src": ""},
                {"id": "main",  "node_type": "video", "name": "Main",
                 "default_duration": 5.0, "default_src": ""},
                {"id": "outro", "node_type": "video", "name": "Outro",
                 "default_duration": 2.0, "default_src": ""},
            ],
        }


# ---------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------

_store: Optional[ProjectStore] = None


def get_project_store() -> ProjectStore:
    global _store
    if _store is None:
        _store = ProjectStore()
    return _store
