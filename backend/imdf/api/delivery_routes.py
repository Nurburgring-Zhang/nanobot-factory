"""交付管理路由 - 真实数据库实现 (R2-2: Body 验证)"""
from typing import Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel
import sqlite3, os
from datetime import datetime

from api._common.body_schemas import DeliveryCreateRequest

router = APIRouter(prefix="/api/delivery", tags=["delivery"])

_IMDF_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "imdf.db")


@router.get("/")
async def delivery_list(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """从 imdf.db deliveries 表读取真实交付列表 (R2.5-W1: Pydantic Query 验证)"""
    try:
        conn = sqlite3.connect(_IMDF_DB)
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT id, name, dataset_version, status, reviewer, comments FROM deliveries ORDER BY id DESC"
        ).fetchall()
        conn.close()
        deliveries = []
        for r in rows:
            deliveries.append({
                "id": f"d{r[0]}",
                "name": r[1],
                "format": "JSON",
                "dataset_version": r[2],
                "status": r[3],
                "reviewer": r[4] or "",
                "comments": r[5] or "",
            })
        if q:
            ql = q.lower()
            deliveries = [d for d in deliveries if ql in (d.get("name") or "").lower() or ql in (d.get("status") or "").lower()]
        total = len(deliveries)
        if sort_by:
            deliveries.sort(
                key=lambda d: d.get(sort_by, "") or "",
                reverse=(order == "desc"),
            )
        page = deliveries[offset: offset + limit]
        return {
            "success": True,
            "data": {"deliveries": page, "total": total, "source": "imdf.db/deliveries"},
            "limit": limit,
            "offset": offset,
            "error": None,
            "message": "ok",
        }
    except Exception as e:
        return {"success": False, "data": None, "error": str(e), "message": "failed to fetch deliveries"}

@router.post("/create")
async def delivery_create(req: DeliveryCreateRequest):
    """写入 imdf.db deliveries 表 (R2-2: Pydantic 验证)"""
    try:
        conn = sqlite3.connect(_IMDF_DB)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        # 获取下一个ID
        max_id = cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM deliveries").fetchone()[0]
        cursor.execute(
            "INSERT INTO deliveries (id, name, dataset_version, status, comments) VALUES (?, ?, ?, ?, ?)",
            (max_id, req.name, "v1.0", "pending", f"format={req.format}, items={len(req.items)}")
        )
        conn.commit()
        conn.close()
        return {"success": True, "data": {"delivery_id": f"d{max_id}"}, "error": None, "message": f"交付包 {req.name} 已创建", "source": "imdf.db/deliveries"}
    except Exception as e:
        return {"success": False, "data": None, "error": str(e), "message": "failed to create delivery"}
