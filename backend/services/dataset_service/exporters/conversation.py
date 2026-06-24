"""conversation — 通用多轮对话格式导出器 (messages schema).

op_id: export.conversation
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

OP_ID = "export.conversation"
NAME = "通用多轮对话导出"
CATEGORY = "llm_sft"
DESCRIPTION = "导出 dataset 到通用对话格式 (OpenAI messages 风格, JSONL)"
PARAMS: list = [
    {"name": "path", "type": "str", "default": "", "required": True},
    {"name": "system_field", "type": "str", "default": "system", "required": False},
    {"name": "messages_field", "type": "str", "default": "messages", "required": False},
]


def _normalize_messages(msgs: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if not isinstance(msgs, list):
        return out
    for m in msgs:
        if isinstance(m, dict):
            role = str(m.get("role") or m.get("from") or "user")
            content = str(m.get("content") or m.get("value") or "")
            out.append({"role": role, "content": content})
        elif isinstance(m, (list, tuple)) and len(m) >= 2:
            out.append({"role": str(m[0]), "content": str(m[1])})
    return out


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    path = str(params.get("path", "")).strip()
    if not path:
        return {"ok": False, "error": "missing_path"}
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    sys_f = str(params.get("system_field", "system"))
    msg_f = str(params.get("messages_field", "messages"))
    items = list(data) if isinstance(data, list) else [data]
    written = 0
    with open(path, "w", encoding="utf-8") as fp:
        for x in items:
            if isinstance(x, dict):
                system = str(x.get(sys_f, ""))
                msgs = x.get(msg_f) or x.get("conversations") or x.get("turns") or []
            else:
                system = ""
                msgs = [{"role": "user", "content": str(x)}]
            msgs = _normalize_messages(msgs)
            rec = {"system": system, "messages": msgs}
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
    return {
        "ok": True,
        "format": "conversation",
        "path": os.path.abspath(path),
        "rows_written": written,
    }
