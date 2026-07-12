"""label_qwen_vl — Qwen-VL multimodal annotation.

Provides bilingual (zh/en) captioning + tag generation via Alibaba's
Qwen-VL model. Falls back to a deterministic mock.

Inputs:
    image:     str
    prompt:    str
    lang:      str  — "en"|"zh"
    max_tokens: int

Outputs:
    caption:   str
    tags:      list[str]
    lang:      str
"""
from __future__ import annotations

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


class QwenVlInput(BaseModel):
    image: str = Field(..., description="Image URL or local path")
    prompt: str = Field(default="请用一句话描述这张图片。", min_length=1)
    lang: str = Field(default="zh")
    max_tokens: int = Field(default=256, ge=16, le=2048)
    model: str = Field(default="qwen-vl-plus")

    @classmethod
    def _normalize_lang(cls, v: str) -> str:
        v = (v or "zh").lower().strip()
        return v if v in {"en", "zh"} else "zh"


async def label_qwen_vl(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = QwenVlInput.model_validate(input.params or {})
        require_non_empty(payload.prompt, "prompt")
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    payload_dict = payload.model_dump()
    payload_dict["lang"] = QwenVlInput._normalize_lang(payload_dict.get("lang", "zh"))

    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
            {
                "model": payload_dict["model"],
                "input": {"messages": [
                    {"role": "user", "content": [
                        {"image": payload.image},
                        {"text": payload_dict["prompt"]},
                    ]},
                ]},
                "parameters": {"max_tokens": payload_dict["max_tokens"]},
            },
            timeout=8.0,
        )

    if live and isinstance(live, dict):
        try:
            content = live["output"]["choices"][0]["message"]["content"]
            text = content[0]["text"] if isinstance(content, list) else str(content)
            caption = text.strip()
            tags = _extract_tags(caption, payload_dict["lang"])
            return build_output(
                success=True,
                result={"caption": caption, "tags": tags, "lang": payload_dict["lang"],
                        "model": payload_dict["model"], "timestamp": now_iso()},
                source="live", confidence=0.88,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
        except (KeyError, TypeError, IndexError):
            pass

    # Offline mock.
    seed = stable_seed(payload.image, payload_dict["prompt"], payload_dict["lang"])
    captions_zh = [
        "图中展示了一个光线柔和的场景,主体清晰可见。",
        "这是一张构图均衡的图片,色彩协调自然。",
        "画面捕捉到了一个生动而富有层次的瞬间。",
    ]
    captions_en = [
        "An image with soft lighting and a clear main subject.",
        "A well-composed picture with balanced colors.",
        "The frame captures a vivid moment with rich detail.",
    ]
    if payload_dict["lang"] == "zh":
        caption = captions_zh[seed % len(captions_zh)]
        tag_bank = ["自然", "人物", "动物", "城市", "艺术", "复古", "极简"]
    else:
        caption = captions_en[seed % len(captions_en)]
        tag_bank = ["nature", "people", "animal", "urban", "art", "vintage", "minimal"]
    tags = [tag_bank[(seed >> (i * 4)) % len(tag_bank)] for i in range(3)]

    return build_output(
        success=True,
        result={"caption": caption, "tags": tags, "lang": payload_dict["lang"],
                "model": payload_dict["model"], "timestamp": now_iso()},
        source="mock", confidence=0.7,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


def _extract_tags(text: str, lang: str) -> List[str]:
    """Cheap keyword extractor — pulls short tokens / Chinese bigrams."""
    if not text:
        return []
    if lang == "zh":
        out: List[str] = []
        for i, ch in enumerate(text):
            if "\u4e00" <= ch <= "\u9fff" and i + 1 < len(text) and "\u4e00" <= text[i + 1] <= "\u9fff":
                out.append(text[i : i + 2])
        return out[:5]
    return [w.strip(".,;:!?\"'()[]") for w in text.split() if len(w) > 3][:5]


__all__ = ["label_qwen_vl", "QwenVlInput"]