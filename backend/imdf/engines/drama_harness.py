"""P19-B4: DramaEngine (Harness) — 短剧生产 Harness 包装 (V5 第 29 章)

This module wraps the existing :class:`ShortDramaEngine` (in
:mod:`drama_engine`) with the canonical V5 Harness interface:

  * :meth:`create_drama_project`   — open a project record
  * :meth:`generate_script`        — generate / overwrite the script
  * :meth:`design_character`       — create or update a character asset
  * :meth:`design_scene`           — generate scene description + shot list
  * :meth:`generate_shot`          — generate one shot (storyboard ref + metadata)
  * :meth:`generate_video`         — produce the video clip for a shot
  * :meth:`assemble`               — compose the final cut
  * :meth:`start` / :meth:`stop` / :meth:`status`

The harness is intentionally a thin orchestrator: each method either
delegates to :class:`ShortDramaEngine` (for the real work) or emits a
deterministic stub when the underlying engine is missing.  That way
the harness is testable end-to-end without a real model gateway.
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from . import drama_engine as _drama_engine_mod
from .drama_engine import (
    Character,
    DramaPhase,
    DramaProject,
    DramaShot,
    ShortDramaEngine,
    get_drama_engine,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Enums + dataclasses
# --------------------------------------------------------------------------- #
class DramaHarnessState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class DramaScene:
    """Scene description + shot list (V5 scene design artefact)."""

    scene_id: str
    title: str
    setting: str = ""
    mood: str = ""
    shot_count: int = 0
    shots: List[DramaShot] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "title": self.title,
            "setting": self.setting,
            "mood": self.mood,
            "shot_count": self.shot_count,
            "shots": [s.__dict__ for s in self.shots],
        }


@dataclass
class DramaProjectRecord:
    """The harness's own project record (separate from :class:`DramaProject`).

    The harness treats the underlying :class:`DramaProject` as a
    payload — the harness's record carries lifecycle metadata
    (created_at, owner, current_phase, etc.) and is keyed by
    ``project_id`` so it can be looked up uniformly.
    """

    project_id: str
    title: str
    logline: str
    owner: str = ""
    current_phase: str = DramaPhase.REQUIREMENT.value
    phases: Dict[str, str] = field(default_factory=dict)
    characters: List[Character] = field(default_factory=list)
    scenes: List[DramaScene] = field(default_factory=list)
    shots: List[DramaShot] = field(default_factory=list)
    script: str = ""
    output_path: str = ""
    status: str = "draft"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    inner_project: Optional[DramaProject] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "logline": self.logline,
            "owner": self.owner,
            "current_phase": self.current_phase,
            "phases": dict(self.phases),
            "characters": [c.to_dict() for c in self.characters],
            "scenes": [s.to_dict() for s in self.scenes],
            "shots": [shot.__dict__ for shot in self.shots],
            "script": self.script,
            "output_path": self.output_path,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# --------------------------------------------------------------------------- #
#  Engine
# --------------------------------------------------------------------------- #
class DramaEngine:
    """Harness façade over :class:`ShortDramaEngine`."""

    def __init__(self, *, inner: Optional[ShortDramaEngine] = None,
                 output_dir: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._state = DramaHarnessState.IDLE
        self._projects: Dict[str, DramaProjectRecord] = {}
        self._inner: ShortDramaEngine = inner or get_drama_engine()
        if output_dir:
            self._inner._output_dir = output_dir  # type: ignore[attr-defined]
            os.makedirs(output_dir, exist_ok=True)

    # ── Lifecycle ────────────────────────────────────────────────────
    def start(self) -> None:
        with self._lock:
            self._state = DramaHarnessState.RUNNING

    def stop(self) -> None:
        with self._lock:
            self._state = DramaHarnessState.STOPPED

    def pause(self) -> None:
        with self._lock:
            if self._state == DramaHarnessState.RUNNING:
                self._state = DramaHarnessState.PAUSED

    def resume(self) -> None:
        with self._lock:
            if self._state == DramaHarnessState.PAUSED:
                self._state = DramaHarnessState.RUNNING

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "projects": len(self._projects),
                "inner_episodes": len(self._inner._episodes)
                if hasattr(self._inner, "_episodes") else 0,
            }

    # ── Harness interface ──────────────────────────────────────────
    def create_drama_project(self, title: str, logline: str, owner: str = "") -> str:
        if not title:
            raise ValueError("title must be non-empty")
        if not logline:
            raise ValueError("logline must be non-empty")

        project_id = uuid.uuid4().hex[:8]
        record = DramaProjectRecord(
            project_id=project_id,
            title=title,
            logline=logline,
            owner=owner,
        )

        # Delegate to the inner engine's phase_requirement so the
        # canonical :class:`DramaProject` is also initialised.
        try:
            inner_project = self._inner.phase_requirement(logline, archetype_id=title)
            inner_project.title = title
            record.inner_project = inner_project
            record.phases[DramaPhase.REQUIREMENT.value] = "completed"
            record.current_phase = DramaPhase.SCRIPT.value
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("inner phase_requirement failed: %s", exc)
            record.phases[DramaPhase.REQUIREMENT.value] = f"failed: {exc}"

        with self._lock:
            self._projects[project_id] = record
        return project_id

    def generate_script(self, project_id: str, *, script: Optional[str] = None) -> str:
        record = self._require_project(project_id)
        if script is None:
            # Default: ask the inner engine to write a stub script.
            try:
                if record.inner_project is None:
                    record.inner_project = self._inner.phase_requirement(record.logline, archetype_id=record.title)
                record.inner_project = self._inner.phase_script(record.inner_project)
                record.script = record.inner_project.script_full or ""
            except Exception as exc:
                record.script = (
                    f"# {record.title}\n\n"
                    f"## 一句话梗概\n{record.logline}\n\n"
                    f"## 剧情结构\n- 第一幕\n- 第二幕\n- 第三幕\n"
                    f"(stub — inner engine error: {exc})\n"
                )
        else:
            record.script = script
            if record.inner_project is not None:
                record.inner_project.script_full = script

        record.phases[DramaPhase.SCRIPT.value] = "completed"
        record.current_phase = DramaPhase.CHARACTER.value
        record.updated_at = datetime.now().isoformat()
        return record.script

    def design_character(
        self,
        project_id: str,
        *,
        name: str,
        appearance: str = "",
        personality: str = "",
        visual_ref_path: str = "",
        voice_profile: str = "",
        style: str = "写实",
    ) -> str:
        record = self._require_project(project_id)
        if not name:
            raise ValueError("character name must be non-empty")

        char = Character(
            name=name,
            appearance=appearance or "待设定",
            personality=personality or "待设定",
            visual_ref_path=visual_ref_path,
            voice_profile=voice_profile,
            style=style,
        )
        record.characters.append(char)

        if record.inner_project is not None:
            try:
                record.inner_project = self._inner.phase_character(
                    record.inner_project, record.characters
                )
            except Exception as exc:
                logger.debug("inner phase_character failed: %s", exc)

        record.phases[DramaPhase.CHARACTER.value] = "completed"
        record.current_phase = DramaPhase.STORYBOARD.value
        record.updated_at = datetime.now().isoformat()
        return char.name

    def design_scene(
        self,
        project_id: str,
        *,
        title: str,
        setting: str = "",
        mood: str = "",
        shot_count: int = 4,
    ) -> str:
        record = self._require_project(project_id)
        if not title:
            raise ValueError("scene title must be non-empty")
        if shot_count <= 0:
            raise ValueError("shot_count must be > 0")

        scene_id = uuid.uuid4().hex[:8]
        shots: List[DramaShot] = []
        for idx in range(shot_count):
            shot = DramaShot(
                shot_number=len(record.shots) + idx + 1,
                scene_id=scene_id,
                character_actions=f"{title} — 镜头{idx + 1}",
                narration=f"第{idx + 1}镜",
                duration=5.0,
                transition="cut",
            )
            shots.append(shot)
            record.shots.append(shot)

        scene = DramaScene(
            scene_id=scene_id,
            title=title,
            setting=setting,
            mood=mood,
            shot_count=shot_count,
            shots=shots,
        )
        record.scenes.append(scene)
        record.phases[DramaPhase.STORYBOARD.value] = "completed"
        record.current_phase = DramaPhase.SHOT_GEN.value
        record.updated_at = datetime.now().isoformat()
        return scene_id

    def generate_shot(self, project_id: str, shot_number: int, *,
                       visual_style: str = "", duration: Optional[float] = None,
                       storyboard_ref: str = "") -> Dict[str, Any]:
        record = self._require_project(project_id)
        shot = next((s for s in record.shots if s.shot_number == shot_number), None)
        if shot is None:
            raise ValueError(f"shot {shot_number} not in project {project_id}")
        if visual_style:
            shot.visual_style = visual_style
        if duration is not None and duration > 0:
            shot.duration = float(duration)
        if storyboard_ref:
            shot.storyboard_ref = storyboard_ref
        record.updated_at = datetime.now().isoformat()
        return {
            "shot_number": shot.shot_number,
            "visual_style": shot.visual_style,
            "duration": shot.duration,
            "storyboard_ref": shot.storyboard_ref,
        }

    def generate_video(self, project_id: str, shot_number: int) -> str:
        record = self._require_project(project_id)
        shot = next((s for s in record.shots if s.shot_number == shot_number), None)
        if shot is None:
            raise ValueError(f"shot {shot_number} not in project {project_id}")

        output_dir = getattr(self._inner, "_output_dir", "/tmp/imdf_dramas")
        os.makedirs(output_dir, exist_ok=True)
        video_path = os.path.join(output_dir, f"{record.project_id}_shot_{shot_number:03d}.mp4")
        shot.generated_video_path = video_path

        if record.inner_project is not None:
            try:
                record.inner_project = self._inner.phase_shot_gen(record.inner_project)
            except Exception as exc:
                logger.debug("inner phase_shot_gen failed: %s", exc)

        record.phases[DramaPhase.SHOT_GEN.value] = "completed"
        record.current_phase = DramaPhase.AUDIO.value
        record.updated_at = datetime.now().isoformat()
        return video_path

    def assemble(self, project_id: str) -> str:
        record = self._require_project(project_id)
        if not record.shots:
            raise ValueError("project has no shots; cannot assemble")

        output_dir = getattr(self._inner, "_output_dir", "/tmp/imdf_dramas")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(
            output_dir,
            f"{record.title or 'short_drama'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
        )
        record.output_path = output_path
        record.status = "composed"
        record.phases[DramaPhase.COMPOSE.value] = "completed"
        record.current_phase = DramaPhase.REVIEW.value
        record.updated_at = datetime.now().isoformat()

        if record.inner_project is not None:
            try:
                record.inner_project.output_path = output_path
                record.inner_project = self._inner.phase_compose(record.inner_project)
            except Exception as exc:
                logger.debug("inner phase_compose failed: %s", exc)

        return output_path

    # ── Lookup helpers ──────────────────────────────────────────────
    def get_project(self, project_id: str) -> Optional[DramaProjectRecord]:
        with self._lock:
            return self._projects.get(project_id)

    def list_projects(self) -> List[DramaProjectRecord]:
        with self._lock:
            return list(self._projects.values())

    def _require_project(self, project_id: str) -> DramaProjectRecord:
        with self._lock:
            record = self._projects.get(project_id)
        if record is None:
            raise KeyError(f"drama project {project_id!r} not found")
        return record


__all__ = [
    "DramaEngine",
    "DramaHarnessState",
    "DramaProjectRecord",
    "DramaScene",
]