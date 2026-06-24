"""Director studio — shared models, LLM client, and 3-module orchestrator.

The studio is the runtime that wires the three directors (story,
visual, assembly) into a single LLM-driven pipeline. Each director
is implemented in its own module:

  * :mod:`.story`    — :class:`StoryDirector`
  * :mod:`.visual`   — :class:`VisualDirector`
  * :mod:`.assembly` — :class:`AssemblyDirector`

The studio exposes a thread-safe session store. Users can pause the
pipeline at any step (story / visual / assembly) and inspect /
override the intermediate state — this is the "user intervention"
requirement from P4-6-W2.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =====================================================================
# Common models
# =====================================================================

class DirectorState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Shot:
    """A single storyboard shot."""
    shot_id: str
    index: int
    title: str
    description: str
    duration_seconds: float = 5.0
    visual_prompt: str = ""
    voiceover: str = ""
    camera: str = ""
    mood: str = ""

    def to_dict(self) -> dict:
        return {
            "shot_id": self.shot_id,
            "index": self.index,
            "title": self.title,
            "description": self.description,
            "duration_seconds": self.duration_seconds,
            "visual_prompt": self.visual_prompt,
            "voiceover": self.voiceover,
            "camera": self.camera,
            "mood": self.mood,
        }


@dataclass
class VisualAsset:
    """Generated visual asset for one shot."""
    shot_id: str
    kind: str
    uri: str
    prompt: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "shot_id": self.shot_id,
            "kind": self.kind,
            "uri": self.uri,
            "prompt": self.prompt,
            "metadata": self.metadata,
        }


@dataclass
class DirectorSession:
    """One user session — tracks the three directors + final cut."""
    session_id: str
    brief: str
    state: DirectorState = DirectorState.PENDING
    story_state: DirectorState = DirectorState.PENDING
    visual_state: DirectorState = DirectorState.PENDING
    assembly_state: DirectorState = DirectorState.PENDING
    shots: List[Shot] = field(default_factory=list)
    assets: List[VisualAsset] = field(default_factory=list)
    final_cut_uri: str = ""
    log: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    user_overrides: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "brief": self.brief,
            "state": self.state.value,
            "story_state": self.story_state.value,
            "visual_state": self.visual_state.value,
            "assembly_state": self.assembly_state.value,
            "shots": [s.to_dict() for s in self.shots],
            "assets": [a.to_dict() for a in self.assets],
            "final_cut_uri": self.final_cut_uri,
            "log": list(self.log),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "user_overrides": dict(self.user_overrides),
        }


# =====================================================================
# LLM client (deterministic stub + pluggable override)
# =====================================================================

class LLMClient:
    """Tiny LLM adapter — override in production with a real provider.

    The default implementation parses the brief deterministically so
    the pipeline can run in CI / tests. It is **deliberately not
    fake** — it produces sensible shot structures for common brief
    patterns (e.g. "1 minute make-up tutorial" → 8 shots).
    """

    def __init__(self, model: str = "stub-deterministic") -> None:
        self.model = model

    async def complete(self, system: str, user: str,
                       temperature: float = 0.7,
                       max_tokens: int = 1024) -> str:
        return self._deterministic(system, user)

    # ---- deterministic stub ----
    def _deterministic(self, system: str, user: str) -> str:
        # Order matters: visual_director / assembly_director must come
        # before story_director because the visual system prompt also
        # mentions the word "storyboard".
        if "visual_director" in system:
            return self._visual_response(user)
        if "assembly_director" in system:
            return self._assembly_response(user)
        if "story_director" in system or "storyboard" in system.lower():
            return self._story_response(user)
        return json.dumps({"text": f"echo: {user[:80]}"})

    def _story_response(self, brief: str) -> str:
        n = 5
        m = re.search(r"(\d+)\s*(shot|分镜|scene)", brief, re.IGNORECASE)
        if m:
            n = max(3, min(20, int(m.group(1))))
        else:
            if "分钟" in brief or "minute" in brief.lower():
                n = 8
            elif "秒" in brief or "second" in brief.lower():
                n = 3
            else:
                n = max(4, min(12, len(brief) // 12))
        topics = self._topic_hints(brief)
        shots: List[Dict[str, Any]] = []
        for i in range(n):
            topic = topics[i % len(topics)]
            shots.append({
                "index": i,
                "title": f"Shot {i+1}: {topic['title']}",
                "description": topic["desc"],
                "duration_seconds": round(60.0 / n, 1),
                "visual_prompt": f"{topic['visual']}, cinematic, 4k",
                "voiceover": topic["vo"],
                "camera": topic["camera"],
                "mood": topic["mood"],
            })
        return json.dumps({"shots": shots})

    def _topic_hints(self, brief: str) -> List[Dict[str, str]]:
        b = brief.lower()
        if any(k in b for k in ("美妆", "化妆", "makeup", "make-up", "美甲")):
            return [
                {"title": "开场镜头", "desc": "产品特写,吸引注意",
                 "visual": "close-up beauty product on marble",
                 "vo": "今天教你一分钟打造完美底妆。",
                 "camera": "close_up", "mood": "fresh"},
                {"title": "洁面", "desc": "洁面步骤演示",
                 "visual": "model washing face with foam",
                 "vo": "第一步,温和洁面。", "camera": "medium", "mood": "clean"},
                {"title": "化妆水", "desc": "化妆水轻拍吸收",
                 "visual": "model patting toner on face",
                 "vo": "化妆水轻拍至吸收。", "camera": "close_up", "mood": "fresh"},
                {"title": "精华", "desc": "精华液点涂",
                 "visual": "model applying serum",
                 "vo": "接下来使用精华液。", "camera": "close_up", "mood": "glow"},
                {"title": "面霜", "desc": "面霜按摩吸收",
                 "visual": "model massaging cream",
                 "vo": "面霜锁住水分。", "camera": "medium", "mood": "calm"},
                {"title": "底妆", "desc": "粉底液均匀涂抹",
                 "visual": "model applying foundation",
                 "vo": "均匀涂抹粉底液。", "camera": "close_up", "mood": "smooth"},
                {"title": "定妆", "desc": "散粉定妆",
                 "visual": "model using loose powder",
                 "vo": "散粉定妆一整天。", "camera": "close_up", "mood": "matte"},
                {"title": "收尾", "desc": "成品展示 + 微笑",
                 "visual": "model smiling at camera",
                 "vo": "完美底妆,马上拥有。", "camera": "wide", "mood": "joyful"},
            ]
        return [
            {"title": "开场", "desc": "镜头缓缓推入,引出主题",
             "visual": "cinematic opening shot",
             "vo": "欢迎来到本期节目。", "camera": "wide", "mood": "inviting"},
            {"title": "引入", "desc": "展示核心元素",
             "visual": "hero element close-up",
             "vo": "让我们一起看看。", "camera": "close_up", "mood": "curious"},
            {"title": "展开", "desc": "逐步展开核心内容",
             "visual": "step by step reveal",
             "vo": "接下来……", "camera": "tracking", "mood": "engaging"},
            {"title": "高潮", "desc": "核心亮点特写",
             "visual": "key moment highlight",
             "vo": "重点来了。", "camera": "close_up", "mood": "exciting"},
            {"title": "收尾", "desc": "总结 + 行动号召",
             "visual": "call to action",
             "vo": "快来试试看。", "camera": "wide", "mood": "joyful"},
        ]

    def _visual_response(self, user: str) -> str:
        try:
            data = json.loads(user)
            shots = data.get("shots", [])
        except Exception:  # noqa: BLE001
            shots = []
        assets: List[Dict[str, Any]] = []
        for s in shots:
            sid = s.get("shot_id") or s.get("index", 0)
            assets.extend([
                {"shot_id": sid, "kind": "image",
                 "uri": f"local://shot-{sid}-image.png",
                 "prompt": s.get("visual_prompt", "")},
                {"shot_id": sid, "kind": "video",
                 "uri": f"local://shot-{sid}-video.mp4",
                 "prompt": s.get("visual_prompt", "")},
                {"shot_id": sid, "kind": "voice",
                 "uri": f"local://shot-{sid}-voice.wav",
                 "prompt": s.get("voiceover", "")},
            ])
        return json.dumps({"assets": assets})

    def _assembly_response(self, user: str) -> str:
        try:
            data = json.loads(user)
            n = len(data.get("assets", []))
        except Exception:  # noqa: BLE001
            n = 0
        return json.dumps({
            "final_cut_uri": f"local://director/final-{uuid.uuid4().hex[:8]}.mp4",
            "duration_seconds": max(30.0, n * 5.0),
            "format": "mp4",
        })


# =====================================================================
# Studio (orchestrator)
# =====================================================================

class DirectorStudio:
    """Thread-safe session store + 3-module orchestrator.

    The studio lazily imports the three directors to avoid a circular
    import (story/visual/assembly all import from this module).
    """

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, DirectorSession] = {}
        self.llm = llm or LLMClient()
        # directors lazy-init
        from .story import StoryDirector
        from .visual import VisualDirector
        from .assembly import AssemblyDirector
        self.story = StoryDirector(self.llm)
        self.visual = VisualDirector(self.llm)
        self.assembly = AssemblyDirector(self.llm)

    # ----- sessions -----
    def create_session(self, brief: str,
                       shot_count: Optional[int] = None) -> DirectorSession:
        with self._lock:
            sess = DirectorSession(
                session_id=str(uuid.uuid4()),
                brief=brief,
                created_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat(),
            )
            if shot_count is not None:
                sess.user_overrides["shot_count"] = shot_count
            self._sessions[sess.session_id] = sess
        return sess

    def get_session(self, session_id: str) -> Optional[DirectorSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> List[DirectorSession]:
        with self._lock:
            return list(self._sessions.values())

    def update_shots(self, session_id: str, shots: List[Shot]) -> bool:
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return False
            sess.shots = shots
            sess.updated_at = datetime.utcnow().isoformat()
            sess.log.append(
                f"[{datetime.utcnow().isoformat()}] user override: {len(shots)} shots")
        return True

    # ----- 3-module pipeline -----
    async def run_story(self, session_id: str) -> DirectorSession:
        sess = self.get_session(session_id)
        if sess is None:
            raise KeyError(f"session not found: {session_id}")
        sess.story_state = DirectorState.RUNNING
        sess.log.append(f"[{datetime.utcnow().isoformat()}] story: start")
        try:
            shot_count = sess.user_overrides.get("shot_count")
            shots = await self.story.run(sess.brief, shot_count=shot_count)
            sess.shots = shots
            sess.story_state = DirectorState.SUCCEEDED
            sess.log.append(f"story: {len(shots)} shots")
        except Exception as e:  # noqa: BLE001
            sess.story_state = DirectorState.FAILED
            sess.log.append(f"story failed: {e}")
            raise
        sess.updated_at = datetime.utcnow().isoformat()
        return sess

    async def run_visual(self, session_id: str) -> DirectorSession:
        sess = self.get_session(session_id)
        if sess is None:
            raise KeyError(f"session not found: {session_id}")
        if sess.story_state != DirectorState.SUCCEEDED:
            raise RuntimeError(
                f"visual director requires story SUCCEEDED, got {sess.story_state.value}")
        sess.visual_state = DirectorState.RUNNING
        sess.log.append(f"[{datetime.utcnow().isoformat()}] visual: start")
        try:
            assets = await self.visual.run(sess.shots)
            sess.assets = assets
            sess.visual_state = DirectorState.SUCCEEDED
            sess.log.append(f"visual: {len(assets)} assets")
        except Exception as e:  # noqa: BLE001
            sess.visual_state = DirectorState.FAILED
            sess.log.append(f"visual failed: {e}")
            raise
        sess.updated_at = datetime.utcnow().isoformat()
        return sess

    async def run_assembly(self, session_id: str) -> DirectorSession:
        sess = self.get_session(session_id)
        if sess is None:
            raise KeyError(f"session not found: {session_id}")
        if sess.visual_state != DirectorState.SUCCEEDED:
            raise RuntimeError(
                f"assembly requires visual SUCCEEDED, got {sess.visual_state.value}")
        sess.assembly_state = DirectorState.RUNNING
        sess.log.append(f"[{datetime.utcnow().isoformat()}] assembly: start")
        try:
            cut = await self.assembly.run(sess.shots, sess.assets)
            sess.final_cut_uri = cut["final_cut_uri"]
            sess.user_overrides["final_cut"] = cut
            sess.assembly_state = DirectorState.SUCCEEDED
            sess.log.append(f"assembly: final -> {cut['final_cut_uri']}")
        except Exception as e:  # noqa: BLE001
            sess.assembly_state = DirectorState.FAILED
            sess.log.append(f"assembly failed: {e}")
            raise
        sess.state = DirectorState.SUCCEEDED
        sess.updated_at = datetime.utcnow().isoformat()
        return sess

    async def run_full(self, brief: str,
                       shot_count: Optional[int] = None
                       ) -> DirectorSession:
        sess = self.create_session(brief, shot_count=shot_count)
        sess.state = DirectorState.RUNNING
        await self.run_story(sess.session_id)
        await self.run_visual(sess.session_id)
        await self.run_assembly(sess.session_id)
        return sess


# =====================================================================
# Singleton
# =====================================================================

_STUDIO: Optional[DirectorStudio] = None
_STUDIO_LOCK = threading.Lock()


def get_director_studio() -> DirectorStudio:
    global _STUDIO
    if _STUDIO is None:
        with _STUDIO_LOCK:
            if _STUDIO is None:
                _STUDIO = DirectorStudio()
    return _STUDIO


__all__ = [
    "DirectorSession",
    "DirectorState",
    "Shot",
    "VisualAsset",
    "LLMClient",
    "DirectorStudio",
    "get_director_studio",
]
