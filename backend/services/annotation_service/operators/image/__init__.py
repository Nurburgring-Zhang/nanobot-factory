"""annot.image — re-exports for 8 image annotation operators."""
from services._none_safety import safe_dict_run  # P6-Fix-P0-1: NoneType guard

from . import (
    bbox,
    polygon,
    keypoint,
    semantic_seg,
    instance_seg,
    classification,
    caption,
    ocr_box,
)

# P6-Fix-P0-1: wrap each module's run() with None-safety guard so callers
# get {"ok": False, "error": ...} instead of AttributeError on None inputs.
for _mod in (bbox, polygon, keypoint, semantic_seg, instance_seg,
             classification, caption, ocr_box):
    _mod.run = safe_dict_run(_mod.run)  # type: ignore[attr-defined]

__all__ = [
    "bbox",
    "polygon",
    "keypoint",
    "semantic_seg",
    "instance_seg",
    "classification",
    "caption",
    "ocr_box",
]