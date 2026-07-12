"""label_blip2_vqa — BLIP-2 visual question answering.

Answers a free-form natural-language question about an image. Falls back to
a deterministic stub when the model service is unreachable.

Inputs:
    image:     str
    question:  str  — non-empty
    max_new_tokens: int — 8..256

Outputs:
    answer:    str
    question:  str
    confidence: float
"""
from __future__ import annotations

import time
from typing import Any, Dict

from pydantic import BaseModel, Field

from backend.skills import SkillInput, SkillOutput

from ._base import (
    NETWORK_OK,
    build_output,
    now_iso,
    post_json,
    require_non_empty,
    stable_seed,
)


class Blip2VqaInput(BaseModel):
    image: str = Field(..., description="Image URL or local path")
    question: str = Field(..., min_length=1)
    max_new_tokens: int = Field(default=64, ge=8, le=256)
    model: str = Field(default="blip2-opt-2.7b")


async def label_blip2_vqa(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = Blip2VqaInput.model_validate(input.params or {})
        require_non_empty(payload.question, "question")
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://api.blip2.example/vqa",
            payload.model_dump(), timeout=6.0,
        )

    if live and isinstance(live, dict) and live.get("answer"):
        ans = str(live["answer"])[: payload.max_new_tokens * 4]
        conf = float(live.get("confidence", 0.85))
        return build_output(
            success=True,
            result={
                "answer": ans, "question": payload.question,
                "confidence": conf, "model": payload.model,
                "timestamp": now_iso(),
            },
            source="live", confidence=conf,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — pick from question-driven answer bank.
    seed = stable_seed(payload.image, payload.question)
    q_lower = payload.question.lower()
    bank = {
        "color": ["red", "blue", "green", "yellow", "black", "white", "purple"],
        "how many": ["two", "three", "four", "five", "one", "several"],
        "where": ["indoors", "outdoors", "on a table", "in a park", "by the window"],
        "what": ["a person", "an animal", "a vehicle", "a building", "a landscape"],
        "is there": ["yes", "no", "likely", "uncertain"],
        "who": ["a young woman", "an elderly man", "a child", "a group of people"],
        "when": ["during the day", "at night", "in the morning", "in autumn"],
    }
    answer = "uncertain"
    conf = 0.5
    for key, choices in bank.items():
        if key in q_lower:
            answer = choices[seed % len(choices)]
            conf = 0.7
            break

    return build_output(
        success=True,
        result={
            "answer": answer, "question": payload.question,
            "confidence": conf, "model": payload.model,
            "timestamp": now_iso(),
        },
        source="mock", confidence=conf,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


__all__ = ["label_blip2_vqa", "Blip2VqaInput"]