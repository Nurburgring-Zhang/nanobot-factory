"""Story director — splits a brief into a storyboard of shots.

LLM-backed with a deterministic stub so the pipeline works offline /
in tests. The StoryDirector is one of three LLM agents wired together
by :class:`director.studio.DirectorStudio`.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from .studio import LLMClient, Shot

logger = logging.getLogger(__name__)


class StoryDirector:
    """LLM-driven storyboard generator."""

    SYSTEM = (
        "You are story_director: a top-tier creative director who turns "
        "user briefs into concise, cinematographic storyboards. Always "
        "respond with strict JSON {\"shots\":[...]}."
    )

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm or LLMClient()

    async def run(self, brief: str,
                  shot_count: Optional[int] = None) -> List[Shot]:
        user_prompt = brief
        if shot_count:
            user_prompt = f"{brief}\n[Constraint: produce exactly {shot_count} shots]"
        raw = await self.llm.complete(self.SYSTEM, user_prompt)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("story LLM returned non-JSON; falling back to 5 shots")
            data = {"shots": [
                {"index": i, "title": f"Shot {i+1}",
                 "description": brief[:60], "duration_seconds": 5.0,
                 "visual_prompt": brief, "voiceover": "",
                 "camera": "wide", "mood": "neutral"}
                for i in range(5)
            ]}
        shots: List[Shot] = []
        for i, s in enumerate(data.get("shots", [])):
            sid = s.get("shot_id") or f"shot-{i+1:02d}"
            shots.append(Shot(
                shot_id=sid,
                index=int(s.get("index", i)),
                title=s.get("title", f"Shot {i+1}"),
                description=s.get("description", ""),
                duration_seconds=float(s.get("duration_seconds", 5.0)),
                visual_prompt=s.get("visual_prompt", ""),
                voiceover=s.get("voiceover", ""),
                camera=s.get("camera", ""),
                mood=s.get("mood", ""),
            ))
        return shots


__all__ = ["StoryDirector"]
