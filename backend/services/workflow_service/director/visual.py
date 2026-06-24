"""Visual director — generates image / video / voice assets per shot.

LLM-backed with a deterministic stub. Each shot produces 3 assets:
  * image (key visual)
  * video (motion clip)
  * voice (voiceover)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .studio import LLMClient, Shot, VisualAsset

logger = logging.getLogger(__name__)


class VisualDirector:
    """LLM-driven multi-modal art director."""

    SYSTEM = (
        "You are visual_director: a multi-modal art director. Given a "
        "storyboard, you produce a list of assets (image + video + voice "
        "per shot). Always respond with strict JSON {\"assets\":[...]}."
    )

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm or LLMClient()

    async def run(self, shots: List[Shot]) -> List[VisualAsset]:
        if not shots:
            return []
        payload = {
            "shots": [
                {
                    "shot_id": s.shot_id, "index": s.index,
                    "visual_prompt": s.visual_prompt,
                    "voiceover": s.voiceover,
                    "camera": s.camera,
                }
                for s in shots
            ]
        }
        raw = await self.llm.complete(self.SYSTEM, json.dumps(payload))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"assets": []}
        assets: List[VisualAsset] = []
        for a in data.get("assets", []):
            assets.append(VisualAsset(
                shot_id=a.get("shot_id", ""),
                kind=a.get("kind", "image"),
                uri=a.get("uri", ""),
                prompt=a.get("prompt", ""),
                metadata=a.get("metadata", {}),
            ))
        return assets


__all__ = ["VisualDirector"]
