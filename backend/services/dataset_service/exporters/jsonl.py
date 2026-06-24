"""jsonl — JSONL 导出器.

op_id: export.jsonl
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

OP_ID = "export.jsonl"
NAME = "JSONL 导出"
CATEGORY = "text"
DESCRIPTION = "导出 dataset 到 JSONL (一行一个 JSON 对象)"
PARAMS: list = [
    {"name": "path", "type": "str", "default": "", "required": True},
    {"name": "pretty", "type": "bool", "default": False, "required": False},
]


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    path = str(params.get("path", "")).strip()
    if not path:
        return {"ok": False, "error": "missing_path"}
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    items = list(data) if isinstance(data, list) else [data]
    written = 0
    with open(path, "w", encoding="utf-8") as fp:
        for x in items:
            fp.write(json.dumps(x, ensure_ascii=False) + "\n")
            written += 1
    return {
        "ok": True,
        "format": "jsonl",
        "path": os.path.abspath(path),
        "rows_written": written,
        "size_bytes": os.path.getsize(path),
    }
