"""P3-6.5-W2: business pipeline templates (10 hybrid + 1 short-drama = 11).

Per-file TEMPLATE constants:
  * pretrain_image_collection.py  - 图像 Pretrain 完整流 (W2.5 new)
  * sft_image_classification.py  - 图像分类 SFT 流 (W2.5 new)
  * sft_image_caption.py         - 图像描述 SFT 流 (W2.5 new)
  * sft_video_caption.py         - 视频描述 SFT 流 (W2.5 new)
  * sft_text_ner.py              - 文本 NER SFT 流 (W2.5 new)
  * dpo_preference.py            - DPO 偏好数据流 (W2.5 new)
  * rlhf_reward.py               - RLHF Reward Model 数据流 (W2.5 new)
  * multimodal_sft.py            - 多模态 SFT 流 (W2.5 new)
  * video_edit_sft.py            - 视频编辑 SFT 流 (W2.5 new)
  * picture_book_generation.py   - 绘本生成 SFT 流 (W2.5 new)
  * short_drama_sft.py           - 短剧 SFT (W1 legacy)

每个文件导出 TEMPLATE: Dict[str, Any] - 与 basic_templates 完全一致的
schema contract。
"""
from __future__ import annotations

from typing import Any, Dict, List

from .pretrain_image_collection import TEMPLATE as _TPL_PRETRAIN
from .sft_image_classification import TEMPLATE as _TPL_SFT_CLS
from .sft_image_caption import TEMPLATE as _TPL_SFT_CAP
from .sft_video_caption import TEMPLATE as _TPL_SFT_VCAP
from .sft_text_ner import TEMPLATE as _TPL_SFT_NER
from .dpo_preference import TEMPLATE as _TPL_DPO
from .rlhf_reward import TEMPLATE as _TPL_RLHF
from .multimodal_sft import TEMPLATE as _TPL_MM_SFT
from .video_edit_sft import TEMPLATE as _TPL_VED_SFT
from .picture_book_generation import TEMPLATE as _TPL_PBOOK
from .short_drama_sft import TEMPLATE as _TPL_DRAMA


TEMPLATES: List[Dict[str, Any]] = [
    _TPL_PRETRAIN,
    _TPL_SFT_CLS,
    _TPL_SFT_CAP,
    _TPL_SFT_VCAP,
    _TPL_SFT_NER,
    _TPL_DPO,
    _TPL_RLHF,
    _TPL_MM_SFT,
    _TPL_VED_SFT,
    _TPL_PBOOK,
    _TPL_DRAMA,
]


__all__ = [
    "TEMPLATES",
    "_TPL_PRETRAIN",
    "_TPL_SFT_CLS",
    "_TPL_SFT_CAP",
    "_TPL_SFT_VCAP",
    "_TPL_SFT_NER",
    "_TPL_DPO",
    "_TPL_RLHF",
    "_TPL_MM_SFT",
    "_TPL_VED_SFT",
    "_TPL_PBOOK",
    "_TPL_DRAMA",
]