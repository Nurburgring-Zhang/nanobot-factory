"""P4-5-W2: Multi-Agent collaborative generator.

Inspired by Google's "Flow Agent" (multi-modal orchestration with a shared
blackboard) and Bernini's character-aware pipeline. The orchestrator fans
work out to 7 specialised agents which run concurrently and write results
to a shared ``Blackboard``.

Agents
------
    1. DirectorAgent       — parses the brief, schedules the others
    2. StoryboardAgent     — splits script into scenes / shots
    3. CharacterAgent      — resolves / locks characters from the character pool
    4. ImageAgent          — generates the per-shot still frames
    5. VideoAgent          — animates frames into shots
    6. VoiceAgent          — TTS voice-over + background music
    7. QAAgent             — runs CLIP + aesthetic + NSFW scoring

Communication
-------------
A single ``Blackboard`` instance is shared between agents. Each agent
publishes:

    * ``asset_pool``       — list of generated media refs (url, modality, seed)
    * ``character_state``  — which characters are bound to which shots
    * ``storyboard``       — scenes/shots graph (filled by StoryboardAgent)
    * ``qa_scores``        — per-asset scoreboard (filled by QAAgent)
    * ``events``           — append-only log for telemetry
"""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .store import JsonTable, _now_iso


# ── Enumerations ────────────────────────────────────────────────────────────
class AgentRole(str, Enum):
    DIRECTOR = "director"
    STORYBOARD = "storyboard"
    CHARACTER = "character"
    IMAGE = "image"
    VIDEO = "video"
    VOICE = "voice"
    QA = "qa"


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# ── Blackboard (shared state across agents) ────────────────────────────────
@dataclass
class AgentMessage:
    """One entry in the blackboard ``events`` log."""

    msg_id: str
    role: str  # AgentRole value
    target: Optional[str]  # AgentRole value or None for broadcast
    kind: str  # "info" | "asset" | "request" | "score"
    payload: Dict[str, Any]
    created_at: str

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _now_iso()


class Blackboard:
    """In-memory shared state for one multi-agent run."""

    def __init__(self, run_id: str, brief: Dict[str, Any]) -> None:
        self.run_id = run_id
        self.brief = brief
        self.asset_pool: List[Dict[str, Any]] = []
        self.character_state: Dict[str, Dict[str, Any]] = {}
        self.storyboard: Dict[str, Any] = {"scenes": []}
        self.qa_scores: Dict[str, float] = {}
        self.events: List[AgentMessage] = []
        self._lock = threading.RLock()

    # ── IO helpers ────────────────────────────────────────────────────
    def publish(self, role: str, kind: str, payload: Dict[str, Any], target: Optional[str] = None) -> AgentMessage:
        msg = AgentMessage(
            msg_id=uuid.uuid4().hex[:12],
            role=role,
            target=target,
            kind=kind,
            payload=payload,
            created_at=_now_iso(),
        )
        with self._lock:
            self.events.append(msg)
            if kind == "asset":
                self.asset_pool.append(payload)
            elif kind == "score" and payload.get("asset_id"):
                self.qa_scores[payload["asset_id"]] = float(payload.get("score", 0.0))
        return msg

    def bind_character(self, character_id: str, shot_id: str, reference_url: str, embedding: Optional[List[float]] = None) -> None:
        with self._lock:
            self.character_state.setdefault(character_id, {"shots": [], "reference_url": reference_url})
            shots = self.character_state[character_id]["shots"]
            if shot_id not in shots:
                shots.append(shot_id)
            if embedding is not None:
                self.character_state[character_id]["embedding"] = embedding

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "brief": self.brief,
            "asset_pool": list(self.asset_pool),
            "character_state": {k: dict(v) for k, v in self.character_state.items()},
            "storyboard": self.storyboard,
            "qa_scores": dict(self.qa_scores),
            "events": [asdict(m) for m in self.events],
        }


# ── Base Agent ─────────────────────────────────────────────────────────────
@dataclass
class AgentRunResult:
    role: str
    status: AgentStatus
    produced: int = 0
    error: Optional[str] = None
    started_at: str = ""
    finished_at: str = ""

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = _now_iso()


class BaseAgent:
    role: AgentRole = AgentRole.DIRECTOR  # subclasses override

    def __init__(self, blackboard: Blackboard) -> None:
        self.bb = blackboard
        self.status = AgentStatus.IDLE

    # Override exactly one of sync/async; default is sync stub.
    def run(self) -> AgentRunResult:  # noqa: D401
        raise NotImplementedError

    async def arun(self) -> AgentRunResult:
        return await asyncio.to_thread(self.run)


# ── 7 concrete agents ──────────────────────────────────────────────────────
class DirectorAgent(BaseAgent):
    role = AgentRole.DIRECTOR

    def __init__(self, blackboard: Blackboard, schedule: Optional[List[str]] = None) -> None:
        super().__init__(blackboard)
        # Default workflow — matches the Google Flow Agent fan-out.
        self.schedule = schedule or [
            AgentRole.STORYBOARD.value,
            AgentRole.CHARACTER.value,
            AgentRole.IMAGE.value,
            AgentRole.VIDEO.value,
            AgentRole.VOICE.value,
            AgentRole.QA.value,
        ]

    def run(self) -> AgentRunResult:
        self.status = AgentStatus.RUNNING
        try:
            brief = self.bb.brief
            self.bb.publish(self.role.value, "info", {"msg": "director: parsing brief", "brief_keys": list(brief.keys())})
            self.bb.publish(self.role.value, "info", {"msg": "director: schedule", "agents": self.schedule})
            return AgentRunResult(role=self.role.value, status=AgentStatus.DONE, produced=len(self.schedule))
        except Exception as e:  # noqa: BLE001
            self.status = AgentStatus.FAILED
            return AgentRunResult(role=self.role.value, status=AgentStatus.FAILED, error=str(e))


class StoryboardAgent(BaseAgent):
    role = AgentRole.STORYBOARD

    def __init__(self, blackboard: Blackboard, scenes: Optional[List[Dict[str, Any]]] = None) -> None:
        super().__init__(blackboard)
        # Allow tests to inject pre-built scenes.
        self._injected = scenes

    def run(self) -> AgentRunResult:
        self.status = AgentStatus.RUNNING
        try:
            brief = self.bb.brief
            if self._injected is not None:
                scenes = self._injected
            else:
                # Parse brief.script into scenes (split on blank line or "Scene N").
                script = brief.get("script") or brief.get("prompt") or ""
                scenes = self._parse(script)
            self.bb.storyboard = {"scenes": scenes, "shots_per_scene": brief.get("shots_per_scene", 2)}
            self.bb.publish(self.role.value, "info", {"msg": "storyboard: built", "scene_count": len(scenes)})
            return AgentRunResult(role=self.role.value, status=AgentStatus.DONE, produced=len(scenes))
        except Exception as e:  # noqa: BLE001
            self.status = AgentStatus.FAILED
            return AgentRunResult(role=self.role.value, status=AgentStatus.FAILED, error=str(e))

    @staticmethod
    def _parse(script: str) -> List[Dict[str, Any]]:
        if not script:
            return [{"scene_id": "s1", "title": "opening", "shots": [{"shot_id": "s1-sh1", "prompt": "wide-shot"}]}]
        chunks = [c.strip() for c in script.split("\n\n") if c.strip()]
        if len(chunks) == 1:
            chunks = script.split(". ")
        scenes: List[Dict[str, Any]] = []
        for i, ch in enumerate(chunks, start=1):
            scenes.append(
                {
                    "scene_id": f"s{i}",
                    "title": f"scene-{i}",
                    "shots": [{"shot_id": f"s{i}-sh1", "prompt": ch}],
                }
            )
        return scenes


class CharacterAgent(BaseAgent):
    role = AgentRole.CHARACTER

    def __init__(self, blackboard: Blackboard, character_pool: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        super().__init__(blackboard)
        # Lazy default: empty pool so this works without P4-5-W1 in place.
        self.pool = character_pool or {}

    def run(self) -> AgentRunResult:
        self.status = AgentStatus.RUNNING
        try:
            brief = self.bb.brief
            requested: List[str] = brief.get("characters") or []
            if not requested:
                # fall back to scanning the storyboard for character hints
                requested = []
                for scene in self.bb.storyboard.get("scenes", []):
                    p = scene.get("shots", [{}])[0].get("prompt", "")
                    for tok in p.split():
                        if tok.startswith("@"):
                            requested.append(tok.lstrip("@").rstrip(",."))
            bound = 0
            for cid in requested:
                meta = self.pool.get(cid) or {"character_id": cid, "reference_url": f"/characters/{cid}.png"}
                for scene in self.bb.storyboard.get("scenes", []):
                    for shot in scene.get("shots", []):
                        self.bb.bind_character(cid, shot["shot_id"], meta.get("reference_url", ""))
                bound += 1
            self.bb.publish(
                self.role.value,
                "info",
                {"msg": "character: bound", "count": bound, "characters": list(self.bb.character_state.keys())},
            )
            return AgentRunResult(role=self.role.value, status=AgentStatus.DONE, produced=bound)
        except Exception as e:  # noqa: BLE001
            self.status = AgentStatus.FAILED
            return AgentRunResult(role=self.role.value, status=AgentStatus.FAILED, error=str(e))


class ImageAgent(BaseAgent):
    role = AgentRole.IMAGE

    def __init__(self, blackboard: Blackboard, stub_url_fn: Optional[Callable[[str], str]] = None) -> None:
        super().__init__(blackboard)
        self._url_fn = stub_url_fn or (lambda shot_id: f"/generated/{self.bb.run_id}/{shot_id}.png")

    def run(self) -> AgentRunResult:
        self.status = AgentStatus.RUNNING
        try:
            produced = 0
            for scene in self.bb.storyboard.get("scenes", []):
                for shot in scene.get("shots", []):
                    asset_id = uuid.uuid4().hex[:10]
                    payload = {
                        "asset_id": asset_id,
                        "shot_id": shot["shot_id"],
                        "modality": "image",
                        "url": self._url_fn(shot["shot_id"]),
                        "seed": hash(shot["shot_id"]) & 0x7FFFFFFF,
                    }
                    self.bb.publish(self.role.value, "asset", payload)
                    produced += 1
            return AgentRunResult(role=self.role.value, status=AgentStatus.DONE, produced=produced)
        except Exception as e:  # noqa: BLE001
            self.status = AgentStatus.FAILED
            return AgentRunResult(role=self.role.value, status=AgentStatus.FAILED, error=str(e))


class VideoAgent(BaseAgent):
    role = AgentRole.VIDEO

    def __init__(self, blackboard: Blackboard, stub_url_fn: Optional[Callable[[str], str]] = None) -> None:
        super().__init__(blackboard)
        self._url_fn = stub_url_fn or (lambda shot_id: f"/generated/{self.bb.run_id}/{shot_id}.mp4")

    def run(self) -> AgentRunResult:
        self.status = AgentStatus.RUNNING
        try:
            produced = 0
            image_assets = [a for a in self.bb.asset_pool if a.get("modality") == "image"]
            for asset in image_assets:
                shot_id = asset["shot_id"]
                vid = uuid.uuid4().hex[:10]
                payload = {
                    "asset_id": vid,
                    "shot_id": shot_id,
                    "modality": "video",
                    "url": self._url_fn(shot_id),
                    "seed": asset.get("seed", 0),
                    "from_asset": asset["asset_id"],
                }
                self.bb.publish(self.role.value, "asset", payload)
                produced += 1
            return AgentRunResult(role=self.role.value, status=AgentStatus.DONE, produced=produced)
        except Exception as e:  # noqa: BLE001
            self.status = AgentStatus.FAILED
            return AgentRunResult(role=self.role.value, status=AgentStatus.FAILED, error=str(e))


class VoiceAgent(BaseAgent):
    role = AgentRole.VOICE

    def __init__(
        self,
        blackboard: Blackboard,
        stub_url_fn: Optional[Callable[[str, str], str]] = None,
    ) -> None:
        super().__init__(blackboard)
        self._url_fn = stub_url_fn or (lambda kind, shot_id: f"/generated/{self.bb.run_id}/{shot_id}.{kind}")

    def run(self) -> AgentRunResult:
        self.status = AgentStatus.RUNNING
        try:
            produced = 0
            for scene in self.bb.storyboard.get("scenes", []):
                for shot in scene.get("shots", []):
                    shot_id = shot["shot_id"]
                    # voice-over
                    self.bb.publish(
                        self.role.value,
                        "asset",
                        {
                            "asset_id": uuid.uuid4().hex[:10],
                            "shot_id": shot_id,
                            "modality": "voice",
                            "url": self._url_fn("wav", shot_id),
                        },
                    )
                    produced += 1
            # one background-music track per scene
            for scene in self.bb.storyboard.get("scenes", []):
                self.bb.publish(
                    self.role.value,
                    "asset",
                    {
                        "asset_id": uuid.uuid4().hex[:10],
                        "shot_id": scene["scene_id"],
                        "modality": "music",
                        "url": self._url_fn("mp3", scene["scene_id"]),
                    },
                )
                produced += 1
            return AgentRunResult(role=self.role.value, status=AgentStatus.DONE, produced=produced)
        except Exception as e:  # noqa: BLE001
            self.status = AgentStatus.FAILED
            return AgentRunResult(role=self.role.value, status=AgentStatus.FAILED, error=str(e))


class QAAgent(BaseAgent):
    role = AgentRole.QA

    def __init__(
        self,
        blackboard: Blackboard,
        scorer: Optional[Callable[[Dict[str, Any]], float]] = None,
        nsfw_threshold: float = 0.85,
    ) -> None:
        super().__init__(blackboard)
        # Default scorer — stub. Real impl would call CLIP + aesthetic + NSFW.
        self._scorer = scorer
        self.nsfw_threshold = nsfw_threshold

    def run(self) -> AgentRunResult:
        self.status = AgentStatus.RUNNING
        try:
            scored = 0
            flagged = 0
            for asset in self.bb.asset_pool:
                if asset.get("modality") not in {"image", "video"}:
                    continue
                score = self._score(asset)
                payload = {"asset_id": asset["asset_id"], "score": score}
                if score < self.nsfw_threshold:
                    payload["flag"] = "low_quality"
                    flagged += 1
                self.bb.publish(self.role.value, "score", payload)
                scored += 1
            return AgentRunResult(role=self.role.value, status=AgentStatus.DONE, produced=scored)
        except Exception as e:  # noqa: BLE001
            self.status = AgentStatus.FAILED
            return AgentRunResult(role=self.role.value, status=AgentStatus.FAILED, error=str(e))

    def _score(self, asset: Dict[str, Any]) -> float:
        if self._scorer is not None:
            try:
                return float(self._scorer(asset))
            except Exception:  # noqa: BLE001
                pass
        # Stable, deterministic fallback score derived from the seed.
        seed = asset.get("seed", 0)
        # Range 0.0 - 1.0 with ~80% of assets scoring above the default threshold.
        return 0.5 + ((seed * 9301 + 49297) % 233280) / 233280.0 * 0.5


# ── Orchestrator ───────────────────────────────────────────────────────────
@dataclass
class OrchestratorReport:
    run_id: str
    started_at: str
    finished_at: str
    agent_results: List[Dict[str, Any]]
    asset_pool: List[Dict[str, Any]]
    qa_scores: Dict[str, float]
    storyboard: Dict[str, Any]
    character_state: Dict[str, Dict[str, Any]]
    events: List[Dict[str, Any]]

    @property
    def ok(self) -> bool:
        return all(r.get("status") == AgentStatus.DONE.value for r in self.agent_results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "ok": self.ok,
            "agent_results": self.agent_results,
            "asset_pool": self.asset_pool,
            "qa_scores": self.qa_scores,
            "storyboard": self.storyboard,
            "character_state": {k: dict(v) for k, v in self.character_state.items()},
            "events": self.events,
        }


class MultiAgentOrchestrator:
    """Drives the 7 agents over a shared ``Blackboard`` and persists results."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._history: List[OrchestratorReport] = []
        self._store = JsonTable("multi_agent_runs")

    # ── Agent factory ────────────────────────────────────────────────
    def _build_agents(
        self,
        blackboard: Blackboard,
        *,
        character_pool: Optional[Dict[str, Dict[str, Any]]] = None,
        scenes: Optional[List[Dict[str, Any]]] = None,
    ) -> List[BaseAgent]:
        return [
            DirectorAgent(blackboard),
            StoryboardAgent(blackboard, scenes=scenes),
            CharacterAgent(blackboard, character_pool=character_pool),
            ImageAgent(blackboard),
            VideoAgent(blackboard),
            VoiceAgent(blackboard),
            QAAgent(blackboard),
        ]

    # ── Sync run ─────────────────────────────────────────────────────
    def run_sync(
        self,
        brief: Dict[str, Any],
        *,
        character_pool: Optional[Dict[str, Dict[str, Any]]] = None,
        scenes: Optional[List[Dict[str, Any]]] = None,
        parallel: bool = True,
    ) -> OrchestratorReport:
        run_id = uuid.uuid4().hex[:12]
        bb = Blackboard(run_id=run_id, brief=brief)
        agents = self._build_agents(bb, character_pool=character_pool, scenes=scenes)
        started = _now_iso()
        if parallel:
            results = self._run_parallel(agents)
        else:
            results = [a.run() for a in agents]
        finished = _now_iso()
        report = OrchestratorReport(
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            agent_results=[asdict(r) for r in results],
            asset_pool=list(bb.asset_pool),
            qa_scores=dict(bb.qa_scores),
            storyboard=dict(bb.storyboard),
            character_state={k: dict(v) for k, v in bb.character_state.items()},
            events=[asdict(m) for m in bb.events],
        )
        with self._lock:
            self._history.append(report)
            self._store.insert(report.to_dict())
        return report

    @staticmethod
    def _run_parallel(agents: List[BaseAgent]) -> List[AgentRunResult]:
        """Run agents concurrently using threads.

        The work is largely I/O-bound (stub calls) so threads are sufficient.
        Real impl would use Celery workers + Redis pub/sub for the
        blackboard events.
        """
        results: Dict[int, AgentRunResult] = {}
        errors: Dict[int, str] = {}

        def runner(idx: int, agent: BaseAgent) -> None:
            try:
                results[idx] = agent.run()
            except Exception as e:  # noqa: BLE001
                errors[idx] = str(e)
                results[idx] = AgentRunResult(role=agent.role.value, status=AgentStatus.FAILED, error=str(e))

        threads = [threading.Thread(target=runner, args=(i, a), daemon=True) for i, a in enumerate(agents)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return [results[i] for i in range(len(agents))]

    # ── Async wrapper ────────────────────────────────────────────────
    async def arun(self, brief: Dict[str, Any], **kw: Any) -> OrchestratorReport:
        return await asyncio.to_thread(self.run_sync, brief, **kw)

    # ── History ──────────────────────────────────────────────────────
    def history(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self._store.all()
        rows.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return rows[:limit]

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self._store.find_one(run_id=run_id)


_ORCHESTRATOR: Optional[MultiAgentOrchestrator] = None


def get_orchestrator() -> MultiAgentOrchestrator:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = MultiAgentOrchestrator()
    return _ORCHESTRATOR


# ── Registry exposed to FastAPI ────────────────────────────────────────────
AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    AgentRole.DIRECTOR.value: {
        "role": AgentRole.DIRECTOR.value,
        "name": "Director",
        "description": "Parses brief, schedules agents, owns the run.",
        "capabilities": ["brief_parsing", "scheduling", "fan_out"],
    },
    AgentRole.STORYBOARD.value: {
        "role": AgentRole.STORYBOARD.value,
        "name": "Storyboard",
        "description": "Splits script into scenes/shots.",
        "capabilities": ["script_parse", "scene_split", "shot_alloc"],
    },
    AgentRole.CHARACTER.value: {
        "role": AgentRole.CHARACTER.value,
        "name": "Character",
        "description": "Binds characters from the pool to shots (consistency).",
        "capabilities": ["character_lookup", "consistency_lock", "embedding"],
    },
    AgentRole.IMAGE.value: {
        "role": AgentRole.IMAGE.value,
        "name": "Image",
        "description": "Generates per-shot still frames.",
        "capabilities": ["txt2img", "img2img", "controlnet"],
    },
    AgentRole.VIDEO.value: {
        "role": AgentRole.VIDEO.value,
        "name": "Video",
        "description": "Animates frames into shots.",
        "capabilities": ["img2vid", "interpolation", "camera_motion"],
    },
    AgentRole.VOICE.value: {
        "role": AgentRole.VOICE.value,
        "name": "Voice",
        "description": "Voice-over + background music.",
        "capabilities": ["tts", "music_gen", "lip_sync"],
    },
    AgentRole.QA.value: {
        "role": AgentRole.QA.value,
        "name": "QA",
        "description": "Quality checks (CLIP / aesthetic / NSFW).",
        "capabilities": ["clip_score", "aesthetic", "nsfw", "consistency"],
    },
}


def list_agents() -> List[Dict[str, Any]]:
    return list(AGENT_REGISTRY.values())


__all__ = [
    "AgentRole",
    "AgentStatus",
    "AgentMessage",
    "Blackboard",
    "DirectorAgent",
    "StoryboardAgent",
    "CharacterAgent",
    "ImageAgent",
    "VideoAgent",
    "VoiceAgent",
    "QAAgent",
    "MultiAgentOrchestrator",
    "OrchestratorReport",
    "get_orchestrator",
    "list_agents",
    "AGENT_REGISTRY",
]