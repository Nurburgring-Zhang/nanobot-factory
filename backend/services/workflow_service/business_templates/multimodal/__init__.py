"""P3-6.5-W2: business multimodal templates (5 - i2v / edit / char / style / tts).

Per-file TEMPLATE constants:
  * image_to_video.py         - 图生视频商业�?
  * text_to_image_edit.py     - 文本引导图像编辑
  * character_consistency.py  - 角色一致性多图训练
  * style_transfer_dataset.py - 风格迁移数据集
  * tts_dataset.py            - TTS 训练数据集

每个文件导出 TEMPLATE: Dict[str, Any] - 与 basic_templates 完全一致的
schema contract: id / category / name / description / tags / version /
inputs / outputs / steps / metrics.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .image_to_video import TEMPLATE as _TPL_I2V
from .text_to_image_edit import TEMPLATE as _TPL_EDIT
from .character_consistency import TEMPLATE as _TPL_CHAR
from .style_transfer_dataset import TEMPLATE as _TPL_STYLE
from .tts_dataset import TEMPLATE as _TPL_TTS


TEMPLATES: List[Dict[str, Any]] = [
    _TPL_I2V,
    _TPL_EDIT,
    _TPL_CHAR,
    _TPL_STYLE,
    _TPL_TTS,
]


__all__ = [
    "TEMPLATES",
    "_TPL_I2V",
    "_TPL_EDIT",
    "_TPL_CHAR",
    "_TPL_STYLE",
    "_TPL_TTS",
]