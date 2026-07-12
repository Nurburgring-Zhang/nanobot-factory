"""P19 v5.1-D3: RFC4180 CSV exporter (UTF-8 BOM)."""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List


def _flatten(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if isinstance(obj, bool):
        return "true" if obj else "false"
    return str(obj)


def export(dataset, output: str, **kwargs) -> str:
    files = list(getattr(dataset, "files", []) or []) if dataset is not None else []
    out_path = output or "dataset.csv"
    Path(os.path.dirname(out_path) or ".").mkdir(parents=True, exist_ok=True)

    columns = ["id", "path", "data_type", "modality_id", "size", "hash"]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerow(columns)
        for i, f in enumerate(files):
            writer.writerow([
                i,
                getattr(f, "path", ""),
                getattr(f, "data_type", "document"),
                getattr(f, "modality_id", ""),
                getattr(f, "size", 0),
                getattr(f, "hash", ""),
            ])
    return out_path


def validate_csv(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"ok": False, "error": "file not found"}
    with open(path, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    has_id = "id" in (reader.fieldnames or [])
    return {"ok": has_id and len(rows) > 0, "n_rows": len(rows), "fieldnames": reader.fieldnames}


__all__ = ["export", "validate_csv"]