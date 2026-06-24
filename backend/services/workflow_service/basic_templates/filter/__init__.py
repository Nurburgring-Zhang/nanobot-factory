"""筛选类 (filter) workflow templates — 5 项."""
from __future__ import annotations
from .top_k_quality import TEMPLATE as _TPL_TOPK
from .balance_subset import TEMPLATE as _TPL_BAL
from .difficulty_curriculum import TEMPLATE as _TPL_CUR
from .domain_balanced import TEMPLATE as _TPL_DOM
from .human_preference import TEMPLATE as _TPL_PRF

__all__ = [
    "_TPL_TOPK", "_TPL_BAL", "_TPL_CUR", "_TPL_DOM", "_TPL_PRF",
]