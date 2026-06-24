"""清洗类 (cleaning) workflow templates — 5 项."""
from __future__ import annotations
from .image_standard_clean import TEMPLATE as _TPL_IMG
from .video_dedup_clean import TEMPLATE as _TPL_VID
from .text_pii_redact import TEMPLATE as _TPL_PII
from .audio_quality_filter import TEMPLATE as _TPL_AUD
from .multimodal_dedup import TEMPLATE as _TPL_MM

__all__ = [
    "_TPL_IMG", "_TPL_VID", "_TPL_PII", "_TPL_AUD", "_TPL_MM",
]