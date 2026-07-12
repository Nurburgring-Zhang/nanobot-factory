"""
数据导出中心路由
----------------
- POST /api/v1/export                                  — 统一导出入口 (generic 6 formats)
- GET  /api/v1/export/formats                          — 支持的导出格式列表
- POST /api/v1/datasets/{dataset_id}/export            — 训练格式导出入口 (18 training formats)
- GET  /api/v1/datasets/{dataset_id}/export/formats    — 训练格式列表

P19 v5.1-D3: 加 18 训练格式 (12 既有 + 6 新).
"""

import os
import json
import csv
import io
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/export", tags=["export"])
datasets_router = APIRouter(prefix="/api/v1/datasets", tags=["datasets-export"])


# 支持的导出格式 (generic 6 — 历史兼容)
SUPPORTED_FORMATS = {
    "json": {
        "label": "JSON",
        "mime": "application/json",
        "ext": ".json",
        "description": "标准JSON格式",
        "category": "generic",
    },
    "csv": {
        "label": "CSV",
        "mime": "text/csv",
        "ext": ".csv",
        "description": "逗号分隔值",
        "category": "generic",
    },
    "jsonl": {
        "label": "JSON Lines",
        "mime": "application/jsonl",
        "ext": ".jsonl",
        "description": "每行一个JSON对象",
        "category": "generic",
    },
    "parquet": {
        "label": "Parquet",
        "mime": "application/octet-stream",
        "ext": ".parquet",
        "description": "Apache Parquet列式存储",
        "category": "generic",
    },
    "arrow": {
        "label": "Apache Arrow",
        "mime": "application/octet-stream",
        "ext": ".arrow",
        "description": "Apache Arrow IPC格式",
        "category": "generic",
    },
    "tfrecord": {
        "label": "TFRecord",
        "mime": "application/octet-stream",
        "ext": ".tfrecord",
        "description": "TensorFlow TFRecord格式",
        "category": "generic",
    },
}


# P19 v5.1-D3: 18 训练格式 (12 既有 + 6 新)
TRAINING_FORMATS: Dict[str, Dict[str, str]] = {
    # 3D (3 NEW)
    "glb": {"label": "GLB", "mime": "model/gltf-binary", "ext": ".glb",
            "description": "Binary glTF 2.0 (.glb) for 3D meshes.", "category": "3d"},
    "gltf": {"label": "glTF", "mime": "model/gltf+json", "ext": ".gltf",
             "description": "glTF 2.0 JSON for 3D meshes (Khronos).", "category": "3d"},
    "obj": {"label": "Wavefront OBJ", "mime": "model/obj", "ext": ".obj",
            "description": "Wavefront OBJ text format (vertices + faces).", "category": "3d"},
    # Image (5 existing + 1 NEW)
    "coco": {"label": "COCO Detection", "mime": "application/json", "ext": ".json",
             "description": "COCO object detection JSON.", "category": "image"},
    "coco_panoptic": {"label": "COCO Panoptic", "mime": "application/json", "ext": ".json",
                      "description": "COCO Panoptic Segmentation (JSON + PNG masks).", "category": "image"},
    "yolo": {"label": "YOLO TXT", "mime": "text/plain", "ext": ".zip",
             "description": "YOLOv5/v8 TXT labels + classes.names.", "category": "image"},
    "pascal_voc": {"label": "Pascal VOC", "mime": "application/xml", "ext": ".xml",
                   "description": "Pascal VOC XML per image.", "category": "image"},
    "createml": {"label": "CreateML", "mime": "application/json", "ext": ".json",
                 "description": "Apple CreateML annotation JSON.", "category": "image"},
    "clip": {"label": "CLIP", "mime": "application/jsonl", "ext": ".jsonl",
             "description": "CLIP image-text pair JSONL.", "category": "image"},
    # Video (1)
    "webdataset": {"label": "WebDataset", "mime": "application/x-tar", "ext": ".tar",
                   "description": "WebDataset tar shards.", "category": "video"},
    # Multimodal (3)
    "llava": {"label": "LLaVA", "mime": "application/json", "ext": ".json",
              "description": "LLaVA instruction-tuning JSON.", "category": "multimodal"},
    "internvl": {"label": "InternVL", "mime": "application/json", "ext": ".json",
                 "description": "InternVL multi-modal dialog JSON.", "category": "multimodal"},
    "diffusiondb": {"label": "DiffusionDB", "mime": "application/octet-stream", "ext": ".parquet",
                    "description": "DiffusionDB style Parquet (prompt+image metadata).", "category": "multimodal"},
    # Table (3)
    "jsonl": {"label": "JSON Lines", "mime": "application/jsonl", "ext": ".jsonl",
              "description": "JSON Lines (one record per line).", "category": "table"},
    "parquet": {"label": "Apache Parquet", "mime": "application/octet-stream", "ext": ".parquet",
                "description": "Apache Parquet columnar storage.", "category": "table"},
    "csv": {"label": "CSV", "mime": "text/csv", "ext": ".csv",
            "description": "RFC4180 CSV (UTF-8 BOM for Excel).", "category": "table"},
    # Audio (2 NEW)
    "wav": {"label": "WAV PCM", "mime": "audio/wav", "ext": ".wav",
            "description": "RIFF WAVE PCM audio (16-bit).", "category": "audio"},
    "mp3": {"label": "MP3", "mime": "audio/mpeg", "ext": ".mp3",
            "description": "MP3 (MPEG-1 Layer 3) via lameenc.", "category": "audio"},
}


# 合并所有支持格式 (generic + training)
ALL_FORMATS: Dict[str, Dict[str, str]] = {**SUPPORTED_FORMATS, **TRAINING_FORMATS}


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
    category: str = "generic"


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.get("/formats")
async def list_export_formats():
    """列出所有支持的导出格式 (generic + training 24 total)."""
    formats = [
        {"format": k, **v} for k, v in ALL_FORMATS.items()
    ]
    return {
        "success": True,
        "data": formats,
        "count": len(formats),
        "training_count": len(TRAINING_FORMATS),
        "message": "ok",
    }


@router.post("")
async def export_data(req: ExportRequest):
    """统一导出入口 (generic 6 formats — 历史兼容)

    接收 format, dataset_id, filters 等参数，
    返回导出结果摘要（实际场景下会生成文件流）。
    """
    if req.format not in ALL_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{req.format}'. Supported: {', '.join(ALL_FORMATS.keys())}",
        )

    fmt_info = ALL_FORMATS[req.format]

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


# ─── P19 v5.1-D3: Training format routes ─────────────────────────────────────


@datasets_router.get("/{dataset_id}/export/formats")
async def list_training_formats(dataset_id: str):
    """列出 18 训练格式."""
    formats = [
        {"format": k, **v} for k, v in TRAINING_FORMATS.items()
    ]
    return {
        "success": True,
        "dataset_id": dataset_id,
        "data": formats,
        "count": len(formats),
        "message": "ok",
    }


@datasets_router.post("/{dataset_id}/export")
async def export_dataset_training(dataset_id: str, format: str = Query(...),
                                  output_path: Optional[str] = Query(None)):
    """P19 v5.1-D3: 训练格式导出端点.

    支持 18 训练格式: glb / gltf / obj / coco / coco_panoptic / yolo /
    pascal_voc / createml / clip / webdataset / llava / internvl /
    diffusiondb / jsonl / parquet / csv / wav / mp3.

    Body (optional): {"manager": "engines.dataset_manager:DatasetManager"}
    默认用 in-process DatasetManager 单例 (production 应替换为 DI).
    """
    if format not in TRAINING_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported training format '{format}'. "
                   f"Supported: {', '.join(sorted(TRAINING_FORMATS.keys()))}",
        )

    fmt_info = TRAINING_FORMATS[format]

    # 1. 拿 DatasetManager 单例 (production 用 DI; 现在 lazy import)
    try:
        from engines.dataset_manager import DatasetManager
        from exports.export_engine import ExportEngine
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"import error: {exc}")

    DATA_DIR = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "datasets"
    )
    mgr = DatasetManager(data_dir=DATA_DIR)
    ver = mgr.get_version(dataset_id)
    if ver is None:
        # 自动用 dataset_id 当 path 当作单文件 dataset
        path = os.path.join(DATA_DIR, dataset_id)
        if os.path.exists(path):
            try:
                ver = mgr.create_version_from_paths(name=dataset_id, paths=[path])
            except Exception as exc:
                raise HTTPException(status_code=404,
                                    detail=f"dataset {dataset_id!r} not found: {exc}")
        else:
            raise HTTPException(status_code=404, detail=f"dataset {dataset_id!r} not found")

    # 2. 走 ExportEngine
    engine = ExportEngine(data_dir=os.path.join(DATA_DIR, "exports"))
    try:
        if format in {"coco", "webdataset", "jsonl", "parquet", "llava", "internvl"}:
            # manager-bound methods
            out = engine.export_with_manager(
                format, mgr, ver.version, output=output_path or "")
        else:
            out = engine.export(format, ver, output=output_path or "")
    except Exception as exc:
        raise HTTPException(status_code=500,
                            detail=f"export {format} failed: {exc}")

    if not out or not os.path.exists(out):
        raise HTTPException(status_code=500,
                            detail=f"export {format} produced no output")

    return {
        "success": True,
        "dataset_id": dataset_id,
        "format": format,
        "format_label": fmt_info["label"],
        "output_path": out,
        "file_size": os.path.getsize(out),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": f"Exported {dataset_id} to {format} ({os.path.getsize(out)} bytes)",
    }
