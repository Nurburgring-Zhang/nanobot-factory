"""Data exporter — standardized JSON / CSV export (R10.5-Worker-2)

商用导出:
- JSONExporter: 标准 JSON (含 schema_version + exported_at + meta)
- CSVExporter:  UTF-8 BOM + RFC4180 (逗号/引号转义)
- ExportFormat: 枚举 (json / csv)
- 接受任意 dict / dataclass / pydantic, 自动 normalize

设计:
- 所有导出带 schema_version, 让下游消费者可以版本化兼容
- CSV 字段顺序 = 传入顺序 (preserve_order)
- pydantic v2 model 优先用 .model_dump()
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

# pydantic 可选
try:
    from pydantic import BaseModel as _PydanticBase
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    _PydanticBase = None  # type: ignore
    _HAS_PYDANTIC = False


SCHEMA_VERSION = "1.0.0"


class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"


# ============================================================================
# Normalize helpers
# ============================================================================

def _normalize(obj: Any) -> Any:
    """把 dataclass / pydantic / 任意 obj 转为可 JSON 序列化的 dict."""
    if obj is None or isinstance(obj, (str, int, bool, float)):
        return obj
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_normalize(v) for v in obj]
    if _HAS_PYDANTIC and isinstance(obj, _PydanticBase):
        return _normalize(obj.model_dump())
    if is_dataclass(obj):
        return _normalize(asdict(obj))
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return _normalize(obj.to_dict())
    if hasattr(obj, "__dict__"):
        return _normalize(vars(obj))
    return str(obj)


def _flatten_record(record: Dict[str, Any]) -> Dict[str, str]:
    """CSV 扁平化: dict / list 转字符串, 防 nested."""
    out: Dict[str, str] = {}
    for k, v in record.items():
        if v is None:
            out[k] = ""
        elif isinstance(v, (dict, list)):
            out[k] = json.dumps(_normalize(v), ensure_ascii=False, separators=(",", ":"))
        elif isinstance(v, bool):
            out[k] = "true" if v else "false"
        elif isinstance(v, Decimal):
            out[k] = str(v)
        else:
            out[k] = str(v)
    return out


# ============================================================================
# JSONExporter
# ============================================================================

class JSONExporter:
    """标准化 JSON 导出 — schema_version + exported_at + records."""
    def __init__(self, schema_version: str = SCHEMA_VERSION, pretty: bool = False):
        self.schema_version = schema_version
        self.pretty = pretty

    def export(self, records: Iterable[Any],
               meta: Optional[Dict[str, Any]] = None) -> str:
        norm_records = [_normalize(r) for r in records]
        envelope = {
            "schema_version": self.schema_version,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "count": len(norm_records),
            "meta": _normalize(meta) if meta else {},
            "records": norm_records,
        }
        if self.pretty:
            return json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=False)
        return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))

    def export_to_bytes(self, records: Iterable[Any],
                        meta: Optional[Dict[str, Any]] = None) -> bytes:
        return self.export(records, meta).encode("utf-8")


# ============================================================================
# CSVExporter
# ============================================================================

class CSVExporter:
    """标准化 CSV 导出 — RFC4180, UTF-8 BOM (Excel 友好), 字段顺序 = first seen."""
    def __init__(self, include_bom: bool = True):
        self.include_bom = include_bom

    def export(self, records: Iterable[Any],
               columns: Optional[Sequence[str]] = None) -> str:
        rows: List[Dict[str, Any]] = [_normalize(r) for r in records]
        if not rows:
            # 空记录 — 仍返回 header (如果有)
            if columns:
                buf = io.StringIO()
                w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
                if self.include_bom:
                    buf.write("\ufeff")
                w.writerow(list(columns))
                return buf.getvalue()
            return ""

        # 推断列顺序: 优先用 columns 参数, 否则按第一行顺序
        if columns:
            fieldnames = list(columns)
        else:
            seen: List[str] = []
            seen_set = set()
            for r in rows:
                for k in r.keys():
                    if k not in seen_set:
                        seen.append(k)
                        seen_set.add(k)
            fieldnames = seen

        buf = io.StringIO()
        w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        if self.include_bom:
            buf.write("\ufeff")
        w.writerow(fieldnames)
        for r in rows:
            flat = _flatten_record(r)
            w.writerow([flat.get(c, "") for c in fieldnames])
        return buf.getvalue()

    def export_to_bytes(self, records: Iterable[Any],
                        columns: Optional[Sequence[str]] = None) -> bytes:
        return self.export(records, columns).encode("utf-8")


# ============================================================================
# 顶层 dispatcher
# ============================================================================

def export_data(records: Iterable[Any], fmt: Union[str, ExportFormat],
                meta: Optional[Dict[str, Any]] = None,
                columns: Optional[Sequence[str]] = None) -> bytes:
    """统一入口 — fmt = "json" / "csv"."""
    efmt = ExportFormat(fmt) if isinstance(fmt, str) else fmt
    if efmt == ExportFormat.JSON:
        return JSONExporter().export_to_bytes(records, meta=meta)
    if efmt == ExportFormat.CSV:
        return CSVExporter().export_to_bytes(records, columns=columns)
    raise ValueError(f"unsupported export format: {fmt}")


__all__ = [
    "ExportFormat", "JSONExporter", "CSVExporter", "export_data",
    "SCHEMA_VERSION",
]


# Avoid circular: import here (only used at runtime, never type-checked)
from decimal import Decimal  # noqa: E402  (after dataclass-related symbols)