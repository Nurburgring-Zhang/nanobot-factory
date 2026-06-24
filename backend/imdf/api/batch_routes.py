"""
批量操作路由
------------
- POST /api/v1/batch/export — 批量导出
- POST /api/v1/batch/delete — 批量删除
"""

import os
import json
import zipfile
import io
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/batch", tags=["batch"])

# 数据目录 — 用于查找/删除数据集
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "datasets"
)


class BatchExportRequest(BaseModel):
    dataset_ids: List[str] = []
    format: str = "json"
    include_metadata: bool = True


class BatchDeleteRequest(BaseModel):
    dataset_ids: List[str] = []


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


@router.post("/export")
async def batch_export(req: BatchExportRequest):
    """批量导出数据集"""
    if not req.dataset_ids:
        raise HTTPException(status_code=400, detail="dataset_ids is required")
    _ensure_data_dir()

    exported = []
    errors = []
    for ds_id in req.dataset_ids:
        ds_path = os.path.join(DATA_DIR, ds_id)
        if not os.path.exists(ds_path):
            errors.append({"id": ds_id, "error": "dataset not found"})
            continue
        try:
            # 收集该数据集下的所有文件
            files = []
            for root, _, filenames in os.walk(ds_path):
                for fn in filenames:
                    fpath = os.path.join(root, fn)
                    rel = os.path.relpath(fpath, ds_path)
                    try:
                        with open(fpath, "rb") as f:
                            content = f.read()
                        files.append({"path": rel, "size": len(content), "content_b64": content.hex()[:200]})
                    except Exception as e:
                        files.append({"path": rel, "error": str(e)})
            exported.append({"dataset_id": ds_id, "files": files, "file_count": len(files)})
        except Exception as e:
            errors.append({"id": ds_id, "error": str(e)})

    return {
        "success": True,
        "data": {
            "exported": exported,
            "errors": errors,
            "total_requested": len(req.dataset_ids),
            "total_exported": len(exported),
            "format": req.format,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "message": "ok" if not errors else f"exported {len(exported)}/{len(req.dataset_ids)} datasets",
    }


@router.post("/delete")
async def batch_delete(req: BatchDeleteRequest):
    """批量删除数据集"""
    if not req.dataset_ids:
        raise HTTPException(status_code=400, detail="dataset_ids is required")
    _ensure_data_dir()

    deleted = []
    errors = []
    for ds_id in req.dataset_ids:
        ds_path = os.path.join(DATA_DIR, ds_id)
        if not os.path.exists(ds_path):
            errors.append({"id": ds_id, "error": "dataset not found"})
            continue
        try:
            import shutil
            shutil.rmtree(ds_path)
            deleted.append(ds_id)
        except Exception as e:
            errors.append({"id": ds_id, "error": str(e)})

    return {
        "success": True,
        "data": {
            "deleted": deleted,
            "errors": errors,
            "total_requested": len(req.dataset_ids),
            "total_deleted": len(deleted),
        },
        "message": "ok" if not errors else f"deleted {len(deleted)}/{len(req.dataset_ids)} datasets",
    }
