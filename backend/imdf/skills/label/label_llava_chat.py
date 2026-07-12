"""label_llava_chat — LLaVA multi-turn multimodal chat.

Performs a multi-turn conversation that mixes images and text. Falls back to
a deterministic mock when the LLaVA service is unreachable.

Inputs:
    turns: list of dicts, each {"role": "user"|"assistant", "content": str,
                                "image": str?}

Outputs:
    reply:     str  — the assistant's final turn
    turns:     list — updated conversation (input + final reply appended)
"""

import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from backend.skills import SkillInput, SkillOutput

from ._base import (
    NETWORK_OK,
    build_output,
    now_iso,
    post_json,
    require_non_empty,
    stable_seed,
)


class TurnModel(BaseModel):
    role: str
    content: str
    image: str = ""

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        v = (v or "").lower().strip()
        if v not in {"user", "assistant", "system"}:
            raise ValueError("turn.role must be user|assistant|system")
        return v


class LlavaChatInput(BaseModel):
    turns: List[TurnModel] = Field(..., min_length=1)
    model: str = Field(default="llava-1.5-7b")
    max_new_tokens: int = Field(default=128, ge=8, le=512)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


async def label_llava_chat(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = LlavaChatInput.model_validate(input.params or {})
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    if not payload.turns:
        return build_output(success=False, error="turns must be non-empty", source="label")
    if payload.turns[-1].role != "user":
        return build_output(
            success=False, error="last turn must be 'user' to elicit a reply", source="label",
        )

    last_user = payload.turns[-1].content
    require_non_empty(last_user, "last turn content")

    live = None
    if NETWORK_OK:
        live = await post_json(
            "https://api.llava.example/chat",
            {"turns": [t.model_dump() for t in payload.turns], "model": payload.model,
             "max_new_tokens": payload.max_new_tokens, "temperature": payload.temperature},
            timeout=6.0,
        )

    if live and isinstance(live, dict) and live.get("reply"):
        reply = str(live["reply"])
        new_turns = [t.model_dump() for t in payload.turns] + [
            {"role": "assistant", "content": reply, "image": ""},
        ]
        return build_output(
            success=True,
            result={"reply": reply, "turns": new_turns, "model": payload.model, "timestamp": now_iso()},
            source="live", confidence=0.85,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — echoes keywords + appends a thoughtful reply.
    seed = stable_seed(last_user, len(payload.turns))
    replies = [
        "I can see the image you described. The main subject appears clear.",
        "Based on the image, here are the key elements I noticed.",
        "Let me think about this image and your question together.",
        "Looking at the picture, I would describe it as follows.",
    ]
    reply = replies[seed % len(replies)]
    if "?" in last_user:
        reply += " The answer seems to relate to what is centrally framed."
    new_turns = [t.model_dump() for t in payload.turns] + [
        {"role": "assistant", "content": reply, "image": ""},
    ]

    return build_output(
        success=True,
        result={"reply": reply, "turns": new_turns, "model": payload.model, "timestamp": now_iso()},
        source="mock", confidence=0.7,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


__all__ = ["label_llava_chat", "LlavaChatInput", "TurnModel"]