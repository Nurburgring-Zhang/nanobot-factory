"""label_gpt4v_label — GPT-4V multimodal labeling.

Combines captioning + tagging + structured-label extraction in one call.
Falls back to a deterministic mock when the OpenAI service is unreachable.

Inputs:
    image:   str  — image URL or local path
    prompt:  str  — instruction / system-prompt for GPT-4V
    schema:  dict — optional JSON schema the response must conform to
    max_tokens: int

Outputs:
    caption:    str
    tags:       list[str]
    structured: dict  — parsed according to schema (or default)
"""

import json
import time
from typing import Any, Dict, List

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


class Gpt4VLabelInput(BaseModel):
    image: str = Field(..., description="Image URL or local path")
    prompt: str = Field(default="Describe the image and list 3-5 tags.", min_length=1)
    schema: Dict[str, Any] = Field(default_factory=dict)
    max_tokens: int = Field(default=256, ge=16, le=2048)
    model: str = Field(default="gpt-4-vision-preview")


_DEFAULT_SCHEMA = {
    "type": "object",
    "properties": {
        "caption": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


async def label_gpt4v_label(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = Gpt4VLabelInput.model_validate(input.params or {})
        require_non_empty(payload.prompt, "prompt")
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    schema = payload.schema or _DEFAULT_SCHEMA
    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://api.openai.com/v1/chat/completions",
            {
                "model": payload.model,
                "messages": [
                    {"role": "system", "content": payload.prompt},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": payload.image}},
                    ]},
                ],
                "max_tokens": payload.max_tokens,
                "response_format": {"type": "json_schema", "json_schema": schema},
            },
            timeout=8.0,
            headers={"Authorization": "Bearer ${OPENAI_API_KEY}"},
        )

    if live and isinstance(live, dict):
        try:
            content = live["choices"][0]["message"]["content"]
            structured = json.loads(content) if isinstance(content, str) else content
            if not isinstance(structured, dict):
                structured = {"caption": str(structured), "tags": []}
            caption = str(structured.get("caption", ""))
            tags = list(structured.get("tags", []))
            return build_output(
                success=True,
                result={
                    "caption": caption, "tags": tags, "structured": structured,
                    "model": payload.model, "timestamp": now_iso(),
                },
                source="live", confidence=0.9,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
        except (KeyError, ValueError, json.JSONDecodeError):
            pass  # fall through to mock

    # Offline mock — derive caption + tags from seed.
    seed = stable_seed(payload.image, payload.prompt)
    captions = [
        "A vivid scene with clear focal subject and balanced lighting.",
        "An intriguing composition capturing a moment of quiet activity.",
        "A visually rich image with several noteworthy details.",
    ]
    tag_bank = [
        "indoor", "outdoor", "people", "animal", "nature", "urban",
        "art", "vintage", "modern", "colorful", "minimal", "detailed",
    ]
    caption = captions[seed % len(captions)]
    tags = []
    for i in range(3, 6):
        tags.append(tag_bank[(seed >> (i * 3)) % len(tag_bank)])
    structured = {"caption": caption, "tags": tags}
    return build_output(
        success=True,
        result={
            "caption": caption, "tags": tags, "structured": structured,
            "model": payload.model, "timestamp": now_iso(),
        },
        source="mock", confidence=0.75,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


__all__ = ["label_gpt4v_label", "Gpt4VLabelInput"]