"""
scoring_service operators — 15 评分算子定义与执行.
复用 imdf.engines.aesthetic_scorer + imdf.engines.operators_lib 的 5 基础评分算子.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import statistics
from typing import Any, Dict, List, Optional

try:
    from imdf.engines.operators_lib import get_registry as _get_imdf_registry
    _IMDF_REG = _get_imdf_registry()
except Exception:
    _IMDF_REG = None

try:
    from imdf.engines.aesthetic_scorer import (
        AestheticScorer, get_aesthetic_scorer, HAS_PILLOW,
    )
    _AESTHETIC = get_aesthetic_scorer()
except Exception:
    AestheticScorer = None
    _AESTHETIC = None
    HAS_PILLOW = False# 15 评分算子定义 (5 基础 imdf + 10 扩展)
SCORING_OPERATORS: List[Dict[str, Any]] = [
    # === 5 基础 (复用 imdf.engines.operators_lib score 类目) ===
    {"id": "score.aesthetic", "name": "美学评分", "category": "image",
     "description": "图像美学评分 (CLIP-IQA + MUSIQ 风格, 0-100)",
     "params": [], "imdf_op": "score.aesthetic"},
    {"id": "score.technical_quality", "name": "技术质量评分", "category": "image",
     "description": "图像技术指标评分 (sharpness/noise)",
     "params": [], "imdf_op": "score.technical_quality"},
    {"id": "score.nsfw_detector", "name": "NSFW检测", "category": "safety",
     "description": "不安全内容检测评分",
     "params": [{"name": "threshold", "type": "float", "default": 0.7, "required": False}],
     "imdf_op": "score.nsfw_detector"},
    {"id": "score.coherence", "name": "连贯性评分", "category": "video",
     "description": "视频/文本时序连贯性评分",
     "params": [], "imdf_op": "score.coherence"},
    {"id": "score.diversity", "name": "多样性评分", "category": "dataset",
     "description": "数据集多样性评分",
     "params": [], "imdf_op": "score.diversity"},
    # === 10 扩展 ===
    {"id": "score.clip_score", "name": "CLIP图文匹配", "category": "vision_language",
     "description": "CLIP 图文匹配度 (0-1)",
     "params": []},
    {"id": "score.text_quality", "name": "文本质量", "category": "text",
     "description": "文本流畅度/可读性评分",
     "params": []},
    {"id": "score.toxicity", "name": "毒性检测", "category": "safety",
     "description": "文本毒性/有害性评分",
     "params": [{"name": "threshold", "type": "float", "default": 0.5, "required": False}]},
    {"id": "score.sentiment", "name": "情感极性", "category": "text",
     "description": "文本情感正负向 (-1 到 1)",
     "params": []},
    {"id": "score.language_quality", "name": "语言质量", "category": "text",
     "description": "语法/拼写/标点综合评分",
     "params": []},
    {"id": "score.factuality", "name": "事实性", "category": "text",
     "description": "文本事实性/无幻觉评分",
     "params": []},
    {"id": "score.video_motion", "name": "视频运动幅度", "category": "video",
     "description": "视频帧间运动幅度评分",
     "params": []},
    {"id": "score.video_stability", "name": "视频稳定性", "category": "video",
     "description": "视频抖动/稳定度评分",
     "params": []},
    {"id": "score.audio_quality", "name": "音频质量", "category": "audio",
     "description": "音频信噪比/清晰度评分",
     "params": []},
    {"id": "score.code_quality", "name": "代码质量", "category": "code",
     "description": "代码可读性/复杂度评分",
     "params": []},
]


def get_operator_meta(op_id: str) -> Optional[Dict[str, Any]]:
    for op in SCORING_OPERATORS:
        if op["id"] == op_id:
            return op
    return None