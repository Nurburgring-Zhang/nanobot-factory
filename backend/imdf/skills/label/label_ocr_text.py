"""label_ocr_text — OCR text recognition.

Extracts text from an image and returns per-region bounding boxes + the
concatenated full text. Falls back to a deterministic offline mock.

Inputs:
    image:      str
    lang:       str  — language hint, default "en"
    detect_orientation: bool

Outputs:
    text:       str
    regions:    list — {text, bbox, confidence}
    lang:       str
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from backend.skills import SkillInput, SkillOutput

from ._base import (
    NETWORK_OK,
    build_output,
    clamp,
    now_iso,
    post_json,
    stable_seed,
)


class OcrTextInput(BaseModel):
    image: str = Field(...)
    lang: str = Field(default="en")
    detect_orientation: bool = Field(default=False)
    model: str = Field(default="paddleocr-v4")


_MOCK_LINES = {
    "en": [
        "Welcome to the platform",
        "Open source AI",
        "Hello, World!",
        "Sample text 123",
        "Lorem ipsum dolor sit amet",
    ],
    "zh": [
        "欢迎使用本平台",
        "开源人工智能",
        "你好,世界!",
        "示例文本 123",
        "深度学习模型",
    ],
    "ja": [
        "プラットフォームへようこそ",
        "オープンソース AI",
        "こんにちは世界",
        "サンプルテキスト 123",
    ],
}


async def label_ocr_text(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = OcrTextInput.model_validate(input.params or {})
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://api.ocr.example/recognize",
            payload.model_dump(), timeout=6.0,
        )

    if live and isinstance(live, dict) and live.get("regions"):
        regions = [
            {
                "text": str(r.get("text", "")),
                "bbox": list(r.get("bbox", [0, 0, 0, 0])),
                "confidence": clamp(float(r.get("confidence", 0.0))),
            }
            for r in live["regions"]
        ]
        text = "\n".join(r["text"] for r in regions).strip()
        return build_output(
            success=True,
            result={"text": text, "regions": regions, "lang": payload.lang,
                    "model": payload.model, "timestamp": now_iso()},
            source="live", confidence=0.9,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — synthesize 2-4 lines from the language bank.
    seed = stable_seed(payload.image, payload.lang)
    bank = _MOCK_LINES.get(payload.lang, _MOCK_LINES["en"])
    n = (seed % 3) + 2  # 2..4
    regions: List[Dict[str, Any]] = []
    for i in range(n):
        s = (seed >> (i * 5)) & 0xFFFF
        text = bank[s % len(bank)]
        regions.append({
            "text": text,
            "bbox": [(s % 400), (i * 40), ((s >> 4) % 400) + 200, (i * 40) + 30],
            "confidence": round(clamp(0.75 + ((s >> 8) % 250) / 1000.0), 4),
        })
    full_text = "\n".join(r["text"] for r in regions)
    return build_output(
        success=True,
        result={"text": full_text, "regions": regions, "lang": payload.lang,
                "model": payload.model, "timestamp": now_iso()},
        source="mock", confidence=0.78,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


__all__ = ["label_ocr_text", "OcrTextInput"]