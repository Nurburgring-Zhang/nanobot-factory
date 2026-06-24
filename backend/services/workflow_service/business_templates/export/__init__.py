"""P3-6.5-W2: business export templates (5 W1 + 2 W2.5 hybrid = 7).

Per-file TEMPLATE constants:
  * jsonl_alpaca.py              - Alpaca SFT JSONL 商业级 (W1)
  * sharegpt_conversation.py     - ShareGPT 多轮对话商业级 (W1)
  * coco_detection.py            - COCO 检测商业级 (W1)
  * yolo_training.py             - YOLO 训练商业级 (W1)
  * parquet_hf.py                - HF Parquet 商业级 (W1)
  * alpaca_sft_v2.py             - Alpaca SFT + cardinality check (W2.5 new)
  * sharegpt_conversation_v2.py  - ShareGPT + token-length filter (W2.5 new)

每个文件导出 TEMPLATE: Dict[str, Any] - 与 basic_templates 完全一致的
schema contract: id / category / name / description / tags / version /
inputs / outputs / steps / metrics。
"""
from __future__ import annotations

from typing import Any, Dict, List

from .jsonl_alpaca import TEMPLATE as _TPL_ALPACA
from .sharegpt_conversation import TEMPLATE as _TPL_SHAREGPT
from .coco_detection import TEMPLATE as _TPL_COCO
from .yolo_training import TEMPLATE as _TPL_YOLO
from .parquet_hf import TEMPLATE as _TPL_PARQUET
from .alpaca_sft_v2 import TEMPLATE as _TPL_ALPACA_V2
from .sharegpt_conversation_v2 import TEMPLATE as _TPL_SHAREGPT_V2


TEMPLATES: List[Dict[str, Any]] = [
    _TPL_ALPACA,
    _TPL_SHAREGPT,
    _TPL_COCO,
    _TPL_YOLO,
    _TPL_PARQUET,
    _TPL_ALPACA_V2,
    _TPL_SHAREGPT_V2,
]


__all__ = [
    "TEMPLATES",
    "_TPL_ALPACA",
    "_TPL_SHAREGPT",
    "_TPL_COCO",
    "_TPL_YOLO",
    "_TPL_PARQUET",
    "_TPL_ALPACA_V2",
    "_TPL_SHAREGPT_V2",
]