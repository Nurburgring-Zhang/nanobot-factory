"""csv — CSV 导出器.

op_id: export.csv
"""
from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict

OP_ID = "export.csv"
NAME = "CSV 导出"
CATEGORY = "tabular"
DESCRIPTION = "导出 dataset 到 CSV (dict-of-dict 自动 flatten)"
PARAMS: list = [
    {"name": "path", "type": "str", "default": "", "required": True},
    {"name": "delimiter", "type": "str", "default": ",", "required": False},
]


def _flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(_flatten(v, key))
            else:
                out[key] = v
    else:
        out[prefix or "value"] = obj
    return out


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    path = str(params.get("path", "")).strip()
    if not path:
        return {"ok": False, "error": "missing_path"}
    delim = str(params.get("delimiter", ","))[:1] or ","
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    items = list(data) if isinstance(data, list) else [data]
    flat = [_flatten(x) for x in items]
    keys: list = []
    for r in flat:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    with open(path, "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=keys, delimiter=delim)
        w.writeheader()
        for r in flat:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                        for k, v in r.items()})
    return {
        "ok": True,
        "format": "csv",
        "path": os.path.abspath(path),
        "rows_written": len(items),
        "columns": keys,
        "delimiter": delim,
    }
