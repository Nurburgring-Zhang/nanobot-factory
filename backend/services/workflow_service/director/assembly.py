"""Assembly director — stitches shots + assets into a final cut.

LLM-backed with a deterministic stub. The output is a single
``final_cut`` descriptor (URI + duration + transcript + format).
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from .studio import LLMClient, Shot, VisualAsset

logger = logging.getLogger(__name__)


class AssemblyDirector:
    """LLM-driven editor that produces the final cut."""

    SYSTEM = (
        "You are assembly_director: an expert editor. Given a storyboard "
        "and assets, you plan the final cut (sequence, transitions, "
        "B-roll, music). Respond with strict JSON {\"final_cut_uri\":...}."
    )

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm or LLMClient()

    async def run(self, shots: List[Shot],
                  assets: List[VisualAsset]) -> Dict[str, Any]:
        payload = {
            "shots": [s.to_dict() for s in shots],
            "assets": [a.to_dict() for a in assets],
        }
        raw = await self.llm.complete(self.SYSTEM, json.dumps(payload))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        uri = data.get("final_cut_uri", "")
        if not uri:
            uri = f"local://director/final-{uuid.uuid4().hex[:8]}.mp4"
        return {
            "final_cut_uri": uri,
            "duration_seconds": float(
                data.get("duration_seconds",
                         sum(s.duration_seconds for s in shots))),
            "format": data.get("format", "mp4"),
            "transcript": " ".join(s.voiceover for s in shots if s.voiceover),
        }


__all__ = ["AssemblyDirector"]
