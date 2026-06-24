"""评分类 (scoring) workflow templates — 5 项."""
from __future__ import annotations
from .aesthetic_quality import TEMPLATE as _TPL_AES
from .sft_preference import TEMPLATE as _TPL_DPO
from .multimodal_consistency import TEMPLATE as _TPL_MM
from .safety_filter import TEMPLATE as _TPL_SAF
from .diversity_score import TEMPLATE as _TPL_DIV

__all__ = [
    "_TPL_AES", "_TPL_DPO", "_TPL_MM", "_TPL_SAF", "_TPL_DIV",
]