"""标注类 (annotation) workflow templates — 5 项."""
from __future__ import annotations
from .image_classification import TEMPLATE as _TPL_CLS
from .bbox_detection import TEMPLATE as _TPL_BBOX
from .video_caption import TEMPLATE as _TPL_CAP
from .text_ner_qa import TEMPLATE as _TPL_NER
from .obj3d_detection import TEMPLATE as _TPL_3D

__all__ = [
    "_TPL_CLS", "_TPL_BBOX", "_TPL_CAP", "_TPL_NER", "_TPL_3D",
]