"""sharegpt — ShareGPT 多轮对话格式导出器.

op_id: export.sharegpt
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

OP_ID = "export.sharegpt"
NAME = "ShareGPT 导出"
CATEGORY = "llm_sft"
DESCRIPTION = "导出多轮对话 dataset 到 ShareGPT 格式 (conversations JSONL)"
PARAMS: list = [
    {"name": "path", "type": "str", "default": "", "required": True},
    {"name": "system_field", "type": "str", "default": "system", "required": False},
    {"name": "conversations_field", "type": "str", "default": "conversations", "required": False},
]


def _normalize_conv(conv: Any) -> List[Dict[str, str]]:
    """Normalize a conversation list to [{from, value}, ...]."""
    out: List[Dict[str, str]] = []
    if not isinstance(conv, list):
        return out
    for i, m in enumerate(conv):
        if isinstance(m, dict):
            role = str(m.get("role") or m.get("from") or ("human" if i % 2 == 0 else "gpt"))
            value = str(m.get("content") or m.get("value") or "")
            out.append({"from": role, "value": value})
        elif isinstance(m, (list, tuple)) and len(m) >= 2:
            role = str(m[0]) if m[0] is not None else ("human" if i % 2 == 0 else "gpt")
            value = str(m[1])
            out.append({"from": role, "value": value})
    return out


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    path = str(params.get("path", "")).strip()
    if not path:
        return {"ok": False, "error": "missing_path"}
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    sys_f = str(params.get("system_field", "system"))
    conv_f = str(params.get("conversations_field", "conversations"))
    items = list(data) if isinstance(data, list) else [data]
    written = 0
    with open(path, "w", encoding="utf-8") as fp:
        for x in items:
            if isinstance(x, dict):
                system = str(x.get(sys_f, ""))
                convs = x.get(conv_f) or x.get("messages") or x.get("turns") or []
            else:
                system = ""
                convs = [{"from": "human", "value": str(x)}]
            convs = _normalize_conv(convs)
            rec = {"system": system, "conversations": convs}
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
    return {
        "ok": True,
        "format": "sharegpt",
        "path": os.path.abspath(path),
        "rows_written": written,
    }
