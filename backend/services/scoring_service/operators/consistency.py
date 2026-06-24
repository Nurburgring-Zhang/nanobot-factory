"""consistency — 一致性评分算子 (多模态: 文本-图像-音频跨模态一致性).

op_id: score.consistency
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict

OP_ID = "score.consistency"
NAME = "一致性"
CATEGORY = "multimodal"
DESCRIPTION = "多模态一致性评分 (text-image-audio 跨模态对齐, 0-100)"
PARAMS: list = [
    {"name": "modalities", "type": "dict", "default": {}, "required": False,
     "description": "Dict of modality keys {text, image, audio} → content/path"},
]


def _tokens(s: str) -> set:
    return set(re.findall(r"[\u4e00-\u9fa5]+|[a-zA-Z]+", s.lower()))


def _hash_md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _image_text_sim(image_ref: str, text: str) -> float:
    """Mock image-text similarity: does image path contain any text token?"""
    if not image_ref or not text:
        return 0.0
    base = image_ref.rsplit(".", 1)[0].lower()
    parts = re.split(r"[/_-]", base)
    text_tokens = _tokens(text)
    base_tokens = set(p for p in parts if len(p) >= 3)
    return _jaccard(base_tokens, text_tokens)


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    items = data if isinstance(data, list) else [data]
    out = []
    for x in items:
        # Accept either dict with text/image/audio OR 3-tuple/list
        if isinstance(x, dict):
            text = str(x.get("text", "") or x.get("caption", ""))
            image = str(x.get("image", "") or x.get("image_path", ""))
            audio = str(x.get("audio", "") or x.get("audio_path", ""))
        else:
            text = str(x)
            image = ""
            audio = ""
        modalities = params.get("modalities", {}) or {}
        if isinstance(modalities, dict):
            text = text or str(modalities.get("text", ""))
            image = image or str(modalities.get("image", ""))
            audio = audio or str(modalities.get("audio", ""))
        # text-image similarity
        ti = _image_text_sim(image, text)
        # text-audio similarity (file-name token overlap)
        ta = _image_text_sim(audio, text) if audio else 0.0
        # image-audio (cross-modal) — deterministic from hashes
        h = int(_hash_md5(image + "||" + audio)[:8], 16)
        ia = (h % 100) / 200.0  # 0-0.5
        n_mods = sum(1 for v in (text, image, audio) if v)
        if n_mods < 2:
            consistency = 0.0
        else:
            avg = (ti + ta + ia) / max(1, sum(1 for v in [ti, ta, ia] if v > 0) or 1)
            consistency = round(min(100.0, avg * 100), 2)
        out.append({
            "text_image_sim": round(ti, 4),
            "text_audio_sim": round(ta, 4),
            "image_audio_sim": round(ia, 4),
            "modalities": n_mods,
            "consistency": consistency,
        })
    return out[0] if not isinstance(data, list) else out
