"""language_filter — 语言筛选算子 (ASCII / CJK ratio 启发式).

op_id: filter.language
"""
from __future__ import annotations

from typing import Any, Dict

OP_ID = "filter.language"
NAME = "语言筛选"
CATEGORY = "lang"
DESCRIPTION = "按语言 (zh/en/mixed/...) 启发式筛选"
PARAMS: list = [
    {"name": "target", "type": "str", "default": "any", "required": False,
     "description": "any | zh | en | mixed | cjk | latin"},
    {"name": "text_field", "type": "str", "default": "text", "required": False},
]


def _classify(text: str) -> str:
    if not text:
        return "empty"
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    total_alpha = cjk + latin
    if total_alpha == 0:
        return "other"
    if cjk / total_alpha > 0.8:
        return "zh"
    if latin / total_alpha > 0.8:
        return "en"
    return "mixed"


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    target = str(params.get("target", "any")).lower()
    text_field = str(params.get("text_field", "text"))
    items = list(data) if isinstance(data, list) else [data]
    kept = []
    dropped = []
    dist: Dict[str, int] = {}
    for x in items:
        if isinstance(x, dict):
            text = str(x.get(text_field, ""))
        else:
            text = str(x)
        lang = _classify(text)
        dist[lang] = dist.get(lang, 0) + 1
        if target in ("any", "*") or lang == target:
            kept.append(x)
        else:
            dropped.append(x)
    return {
        "kept": kept,
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "target": target,
        "language_distribution": dist,
    }
