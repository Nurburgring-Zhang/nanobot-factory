"""
数据导出中心路由
----------------
- POST /api/v1/export          — 统一导出入口
- GET  /api/v1/export/formats  — 支持的导出格式列表
"""

import os
import json
import csv
import io
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/export", tags=["export"])


# 支持的导出格式
SUPPORTED_FORMATS = {
    "json": {
        "label": "JSON",
        "mime": "application/json",
        "ext": ".json",
        "description": "标准JSON格式",
    },
    "csv": {
        "label": "CSV",
        "mime": "text/csv",
        "ext": ".csv",
        "description": "逗号分隔值",
    },
    "jsonl": {
        "label": "JSON Lines",
        "mime": "application/jsonl",
        "ext": ".jsonl",
        "description": "每行一个JSON对象",
    },
    "parquet": {
        "label": "Parquet",
        "mime": "application/octet-stream",
        "ext": ".parquet",
        "description": "Apache Parquet列式存储",
    },
    "arrow": {
        "label": "Apache Arrow",
        "mime": "application/octet-stream",
        "ext": ".arrow",
        "description": "Apache Arrow IPC格式",
    },
    "tfrecord": {
        "label": "TFRecord",
        "mime": "application/octet-stream",
        "ext": ".tfrecord",
        "description": "TensorFlow TFRecord格式",
    },
}


class ExportRequest(BaseModel):
    format: str = "json"
    dataset_id: str = ""
    filters: Dict[str, Any] = {}
    include_metadata: bool = True
    compress: bool = False


class ExportFormatInfo(BaseModel):
    format: str
    label: str
    mime: str
    ext: str
    description: str


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.get("/formats")
async def list_export_formats():
    """列出所有支持的导出格式"""
    formats = [
        {"format": k, **v} for k, v in SUPPORTED_FORMATS.items()
    ]
    return {
        "success": True,
        "data": formats,
        "message": "ok",
    }


@router.post("")
async def export_data(req: ExportRequest):
    """统一导出入口

    接收 format, dataset_id, filters 等参数，
    返回导出结果摘要（实际场景下会生成文件流）。
    """
    if req.format not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{req.format}'. Supported: {', '.join(SUPPORTED_FORMATS.keys())}",
        )

    fmt_info = SUPPORTED_FORMATS[req.format]

    # 查找数据集文件
    DATA_DIR = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "datasets", req.dataset_id
    )

    records = []
    if os.path.exists(DATA_DIR):
        for root, _, fnames in os.walk(DATA_DIR):
            for fn in fnames:
                fpath = os.path.join(root, fn)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    records.append({
                        "file": os.path.relpath(fpath, DATA_DIR),
                        "content_preview": content[:500],
                        "size": os.path.getsize(fpath),
                    })
                except Exception:
                    records.append({
                        "file": os.path.relpath(fpath, DATA_DIR),
                        "content_preview": "[binary]",
                        "size": os.path.getsize(fpath),
                    })
    else:
        records = []

    # 应用过滤器（简单实现：如果filters非空，仅用key匹配）
    if req.filters:
        filtered = []
        for rec in records:
            match = True
            for k, v in req.filters.items():
                if k == "file" and v not in rec.get("file", ""):
                    match = False
                elif k == "min_size" and rec.get("size", 0) < v:
                    match = False
                elif k == "max_size" and rec.get("size", 0) > v:
                    match = False
            if match:
                filtered.append(rec)
        records = filtered

    return {
        "success": True,
        "data": {
            "format": req.format,
            "format_label": fmt_info["label"],
            "dataset_id": req.dataset_id,
            "record_count": len(records),
            "records_preview": records[:10],  # 只预览前10个
            "filters_applied": bool(req.filters),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "message": f"Export ready. {len(records)} records in {req.format} format.",
    }
