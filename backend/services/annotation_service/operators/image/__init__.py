"""annot.image — re-exports for 8 image annotation operators."""
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