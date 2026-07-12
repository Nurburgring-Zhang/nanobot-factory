"""label_yolo_detect — YOLO object detection.

Detects objects in an image and returns bounding boxes + class labels +
confidence scores. Falls back to a deterministic offline mock.

Inputs:
    image:    str
    classes:  list[str]?  — optional whitelist of class names
    conf_threshold: float — min detection confidence

Outputs:
    boxes:        list — each {label, score, bbox: [x1,y1,x2,y2]}
    count:        int
    classes:      list[str]
"""

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


_DEFAULT_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus",
    "train", "truck", "boat", "traffic light", "fire hydrant",
    "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe",
]


class YoloDetectInput(BaseModel):
    image: str = Field(...)
    classes: List[str] = Field(default_factory=list)
    conf_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    model: str = Field(default="yolov8n")


async def label_yolo_detect(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = YoloDetectInput.model_validate(input.params or {})
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    classes = payload.classes or _DEFAULT_CLASSES
    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://api.yolo.example/detect",
            payload.model_dump(), timeout=5.0,
        )

    if live and isinstance(live, dict) and live.get("boxes"):
        boxes = [
            {
                "label": str(b.get("label", "object")),
                "score": clamp(float(b.get("score", 0.0))),
                "bbox": list(b.get("bbox", [0, 0, 0, 0])),
            }
            for b in live["boxes"]
            if clamp(float(b.get("score", 0.0))) >= payload.conf_threshold
        ]
        return build_output(
            success=True,
            result={"boxes": boxes, "count": len(boxes), "classes": classes,
                    "model": payload.model, "timestamp": now_iso()},
            source="live", confidence=0.9,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — synthesize 2-5 boxes from seed.
    seed = stable_seed(payload.image, tuple(classes))
    n = (seed % 4) + 2  # 2..5 boxes
    boxes = []
    for i in range(n):
        b_seed = (seed >> (i * 5)) & 0xFFFF
        label = classes[b_seed % len(classes)]
        score = clamp(0.45 + ((b_seed % 500) / 1000.0))
        x1 = (b_seed * 13) % 400
        y1 = (b_seed * 17) % 300
        w = 40 + (b_seed % 80)
        h = 40 + ((b_seed >> 4) % 80)
        boxes.append({
            "label": label, "score": round(score, 4),
            "bbox": [x1, y1, x1 + w, y1 + h],
        })
    boxes = [b for b in boxes if b["score"] >= payload.conf_threshold]

    return build_output(
        success=True,
        result={"boxes": boxes, "count": len(boxes), "classes": classes,
                "model": payload.model, "timestamp": now_iso()},
        source="mock", confidence=0.75,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


__all__ = ["label_yolo_detect", "YoloDetectInput"]