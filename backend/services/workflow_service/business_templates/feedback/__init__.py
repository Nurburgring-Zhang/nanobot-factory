"""P3-6-W1: business feedback templates (5 项).

Per-file TEMPLATE constants:
  * bad_case_analysis.py    - Bad Case 自动分析商业级
  * model_eval_feedback.py  - 模型评测反馈数据生成商业级
  * human_review_loop.py    - 人工审核闭环 (callback URL) 商业级
  * auto_relabel.py         - 自动重标注 (基于评分阈值) 商业级
  * data_iteration.py       - 数据迭代闭环商业级

每个文件导出 TEMPLATE: Dict[str, Any]。
"""
from __future__ import annotations

from .bad_case_analysis import TEMPLATE as _TPL_BAD
from .model_eval_feedback import TEMPLATE as _TPL_EVAL
from .human_review_loop import TEMPLATE as _TPL_HUMAN
from .auto_relabel import TEMPLATE as _TPL_RELABEL
from .data_iteration import TEMPLATE as _TPL_ITER

TEMPLATES = [
    _TPL_BAD,
    _TPL_EVAL,
    _TPL_HUMAN,
    _TPL_RELABEL,
    _TPL_ITER,
]

__all__ = [
    "TEMPLATES",
    "_TPL_BAD",
    "_TPL_EVAL",
    "_TPL_HUMAN",
    "_TPL_RELABEL",
    "_TPL_ITER",
]