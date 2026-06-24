"""domain_filter — 领域筛选算子 (关键词 + 元数据匹配).

op_id: filter.domain
"""
from __future__ import annotations

import re
from typing import Any, Dict

OP_ID = "filter.domain"
NAME = "领域筛选"
CATEGORY = "domain"
DESCRIPTION = "按领域关键词/标签筛选 (支持 include/exclude)"
PARAMS: list = [
    {"name": "include_keywords", "type": "list", "default": [], "required": False},
    {"name": "exclude_keywords", "type": "list", "default": [], "required": False},
    {"name": "tag_field", "type": "str", "default": "tags", "required": False},
    {"name": "text_field", "type": "str", "default": "text", "required": False},
]


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    include = [str(k).lower() for k in params.get("include_keywords", []) or []]
    exclude = [str(k).lower() for k in params.get("exclude_keywords", []) or []]
    tag_field = str(params.get("tag_field", "tags"))
    text_field = str(params.get("text_field", "text"))
    items = list(data) if isinstance(data, list) else [data]
    kept = []
    dropped = []
    for x in items:
        if isinstance(x, dict):
            tags = [str(t).lower() for t in (x.get(tag_field) or [])]
            text = str(x.get(text_field, ""))
        else:
            tags = []
            text = str(x)
        lo = text.lower()
        if exclude and any(k in lo or k in tags for k in exclude):
            dropped.append(x)
            continue
        if include and not any(k in lo or k in tags for k in include):
            dropped.append(x)
            continue
        kept.append(x)
    return {
        "kept": kept,
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "include_keywords": include,
        "exclude_keywords": exclude,
    }
