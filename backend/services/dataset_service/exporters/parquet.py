"""parquet — Parquet 导出器 (优先 pyarrow, 降级 csv).

op_id: export.parquet
"""
from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict

OP_ID = "export.parquet"
NAME = "Parquet 导出"
CATEGORY = "tabular"
DESCRIPTION = "导出 dataset 到 Parquet (优先 pyarrow, 降级 CSV)"
PARAMS: list = [
    {"name": "path", "type": "str", "default": "", "required": True},
]


def _flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """Flten dict-of-dict to flat dict for tabular export."""
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


def _try_pyarrow(rows: list, path: str) -> Dict[str, Any]:
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore
        flat = [_flatten(r) for r in rows]
        table = pa.Table.from_pylist(flat)
        pq.write_table(table, path)
        return {"ok": True, "engine": "pyarrow"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "engine": "pyarrow", "error": str(e)}


def _write_csv_fallback(rows: list, path: str) -> Dict[str, Any]:
    flat = [_flatten(r) for r in rows]
    keys: list = []
    for r in flat:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    with open(path, "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=keys)
        w.writeheader()
        for r in flat:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                        for k, v in r.items()})
    return {"ok": True, "engine": "csv_fallback"}


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    path = str(params.get("path", "")).strip()
    if not path:
        return {"ok": False, "error": "missing_path"}
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    items = list(data) if isinstance(data, list) else [data]
    # Prefer .parquet extension; pyarrow unavailable → write CSV fallback
    if path.lower().endswith(".parquet"):
        result = _try_pyarrow(items, path)
        if not result["ok"]:
            csv_path = path.rsplit(".", 1)[0] + ".csv"
            fallback = _write_csv_fallback(items, csv_path)
            fallback["parquet_error"] = result["error"]
            fallback["fallback_path"] = csv_path
            return fallback
        return {
            "ok": True,
            "format": "parquet",
            "path": os.path.abspath(path),
            "rows_written": len(items),
            "engine": result.get("engine", "pyarrow"),
        }
    # Non-parquet path → csv
    result = _write_csv_fallback(items, path)
    return {
        "ok": True,
        "format": "csv",
        "path": os.path.abspath(path),
        "rows_written": len(items),
        "engine": result.get("engine", "csv_fallback"),
    }
