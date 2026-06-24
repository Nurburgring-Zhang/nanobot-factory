"""
数据浏览器路由 - Sprint 4-1 (真实数据库实现)
======================
GET /api/datasets → 分页数据集列表
GET /api/datasets/{id}/preview → 单条数据预览
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime
import sqlite3, os, json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

_IMDF_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "imdf.db")

def _get_datasets(search: str = "") -> List[Dict[str, Any]]:
    """从 imdf.db datasets 表读取真实数据集列表"""
    try:
        conn = sqlite3.connect(_IMDF_DB)
        cursor = conn.cursor()
        if search:
            rows = cursor.execute(
                "SELECT id, name, version, files_count, status, created_by FROM datasets WHERE name LIKE ? ORDER BY id",
                (f"%{search}%",)
            ).fetchall()
        else:
            rows = cursor.execute(
                "SELECT id, name, version, files_count, status, created_by FROM datasets ORDER BY id"
            ).fetchall()
        conn.close()
        datasets = []
        for r in rows:
            datasets.append({
                "id": f"ds_{r[0]:04d}",
                "name": r[1],
                "type": "dataset",
                "version": r[2] or "",
                "size": round((r[3] or 0) * 0.05, 2),
                "items": r[3] or 0,
                "status": r[4] or "unknown",
                "created_by": r[5] or "",
                "quality_score": 85.0,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            })
        return datasets
    except Exception as e:
        logger.error(f"Failed to get datasets: {e}")
        return []


@router.get("")
async def list_datasets(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(
        None, max_length=200, description="搜索关键词, ≤200 字符",
    ),
    sort: str = Query("time", pattern="^(time|name|size|quality)$"),
):
    """分页数据集列表 - 从 imdf.db datasets 表读取"""
    all_data = _get_datasets(search)

    if sort == "name":
        all_data.sort(key=lambda d: d["name"])
    elif sort == "size":
        all_data.sort(key=lambda d: d["size"], reverse=True)
    elif sort == "quality":
        all_data.sort(key=lambda d: d["quality_score"], reverse=True)
    else:
        all_data.sort(key=lambda d: d.get("created_at", ""), reverse=True)

    total = len(all_data)
    total_pages = max(1, (total + size - 1) // size)
    start = (page - 1) * size
    end = start + size
    items = all_data[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "total_pages": total_pages,
        "source": "imdf.db/datasets",
    }


@router.get("/{dataset_id}/preview")
async def preview_dataset(dataset_id: str):
    """单条数据预览 - 从 datasets 表和 annotation_history.db 读取真实数据"""
    try:
        # 先从 datasets 表获取基本信息
        conn = sqlite3.connect(_IMDF_DB)
        cursor = conn.cursor()
        # 解析 dataset_id: ds_0001 → id=1
        ds_id = dataset_id.replace("ds_", "").lstrip("0") or "0"
        row = cursor.execute(
            "SELECT id, name, version, files_count, status, created_by FROM datasets WHERE id=?",
            (int(ds_id),)
        ).fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

        # 从 annotation_history 获取关联的标注记录
        ann_db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "annotation_history.db")
        sample_items = []
        try:
            ann_conn = sqlite3.connect(ann_db)
            ann_rows = ann_conn.execute(
                "SELECT id, element_id, label, labeler_id, confidence, created_at FROM annotation_log WHERE dataset_id=? ORDER BY created_at DESC LIMIT 10",
                (dataset_id,)
            ).fetchall()
            ann_conn.close()
            for ar in ann_rows:
                sample_items.append({
                    "id": f"item_{ar[0]}",
                    "name": ar[1] or f"样本_{ar[0]}",
                    "type": "image",
                    "preview_url": f"/static/preview/{dataset_id}/{ar[1]}.png",
                    "label": ar[2],
                    "labeler": ar[3],
                    "confidence": ar[4],
                    "created_at": ar[5],
                })
        except Exception as e:
            logger.error(f"Failed to load annotation history: {e}")
    except HTTPException:
        total_count = row[3] or 0

        return {
            "dataset_id": dataset_id,
            "name": row[1],
            "version": row[2] or "",
            "status": row[4] or "",
            "items": sample_items,
            "total_count": max(total_count, len(sample_items)),
            "source": "imdf.db/datasets + annotation_history.db",
            "preview": {
                "columns": ["ID", "名称", "类型", "标注", "标注者", "置信度"],
                "rows": [
                    [s["id"], s["name"], s["type"], s.get("label", ""), s.get("labeler", ""), s.get("confidence", 0)]
                    for s in sample_items
                ],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"dataset_id": dataset_id, "error": str(e), "items": [], "total_count": 0}
