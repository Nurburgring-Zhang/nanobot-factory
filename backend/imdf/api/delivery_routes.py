"""交付管理路由 - 真实数据库实现 (R2-2: Body 验证 + P5-R1-T6 扩展)

扩展端点:
  GET    /api/delivery/pending-requester       # 列出待需求方验收
  POST   /api/delivery/{id}/requester-accept   # 需求方接受
  POST   /api/delivery/{id}/requester-reject   # 需求方拒绝 (退回)
  GET    /api/delivery/{id}/timeline           # 时间线
  POST   /api/delivery/{id}/finalize-and-share # approved 后自动分享
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException
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


# ============================================================================
# P5-R1-T6 扩展 — 需求方验收 / 时间线 / finalize-and-share
# ============================================================================

@router.get("/pending-requester")
async def list_pending_for_requester(
    requester_id: str = Query(..., min_length=1, max_length=64),
):
    """列出待需求方验收的交付物 (P5-R1-T6)"""
    from engines.requester_acceptance_engine import get_requester_engine
    eng = get_requester_engine()
    records = eng.list_pending_for_requester(requester_id)
    return {
        "success": True,
        "data": {
            "items": [r.to_dict() for r in records],
            "total": len(records),
        },
        "error": None,
        "message": "ok",
    }


@router.post("/{delivery_id}/requester-accept")
async def requester_accept(
    delivery_id: str,
    requester_id: str = Query(..., min_length=1, max_length=64),
    comments: str = Query("", max_length=4096),
    sample_rate: float = Query(0.05, gt=0.0, le=1.0),
    expiry_hours: int = Query(72, ge=1, le=8760),
    max_downloads: int = Query(0, ge=0, le=1000000),
    password: Optional[str] = Query(None, max_length=128),
):
    """需求方接受 (自动创建 + 提交验收 + 触发 finalize_and_share)

    P5-R1-T6 P0 fix: 链路完整 — 接受后自动 finalize_and_share
    返回 acceptance + share_url (若 delivery 已 approved)
    """
    from engines.requester_acceptance_engine import get_requester_engine
    from engines.delivery_workflow import get_delivery_workflow
    eng = get_requester_engine()
    wf = get_delivery_workflow()
    try:
        # 1. 创建验收
        record = eng.create_acceptance(
            delivery_id=delivery_id,
            requester_id=requester_id,
            sample_rate=sample_rate,
        )
        # 2. 提交 accepted
        record = eng.submit_acceptance(
            acceptance_id=record.id,
            status="accepted",
            comments=comments,
            accepted_assets=record.sampled_assets,
        )
        # 3. (P0 fix) 自动触发 finalize_and_share, 串联到 delivery workflow
        share_result: Dict[str, Any] = {}
        share_error: Optional[str] = None
        try:
            share_result = wf.finalize_and_share(
                delivery_id=delivery_id,
                owner_id=requester_id,
                expiry_hours=expiry_hours,
                max_downloads=max_downloads,
                password=password,
                note=f"Auto-shared after acceptance {record.id} by {requester_id}",
            )
        except ValueError as e:
            # delivery 还没 approved — 验收通过但暂不分享
            share_error = str(e)
        except Exception as e:
            share_error = f"finalize_and_share failed: {e}"

        # 4. 返回 acceptance + share info (链路口径完整)
        response_data: Dict[str, Any] = {
            "acceptance": record.to_dict(),
            "share_url": share_result.get("share_url", ""),
            "share_token": share_result.get("share_token", ""),
            "share_expires_at": share_result.get("expires_at", ""),
            "snapshot_id": share_result.get("snapshot_id", ""),
            "shared": bool(share_result.get("share_url")),
        }
        if share_error:
            response_data["share_warning"] = share_error

        return {
            "success": True,
            "data": response_data,
            "error": None,
            "message": (
                "需求方已接受, 已自动分享" if share_result.get("share_url")
                else "需求方已接受, 待 delivery 批准后自动分享"
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"验收失败: {e}")


@router.post("/{delivery_id}/requester-reject")
async def requester_reject(
    delivery_id: str,
    requester_id: str = Query(..., min_length=1, max_length=64),
    comments: str = Query("", max_length=4096),
    sample_rate: float = Query(0.05, gt=0.0, le=1.0),
):
    """需求方拒绝 (退回生产 — loop-back)

    P5-R1-T6 P0 fix: 退回生产真正触发 status → draft
    通过 FSM transition 实现状态反转, 让 production 重新开始
    """
    from engines.requester_acceptance_engine import get_requester_engine
    from engines.delivery_workflow import get_delivery_workflow, _status_compare
    eng = get_requester_engine()
    wf = get_delivery_workflow()
    # 用 workflow 实例的 db_path, 与 get_requester_engine 保持一致
    db_for_loop = wf.db_path
    try:
        record = eng.create_acceptance(
            delivery_id=delivery_id,
            requester_id=requester_id,
            sample_rate=sample_rate,
        )
        record = eng.submit_acceptance(
            acceptance_id=record.id,
            status="rejected",
            comments=comments,
            rejected_assets=record.sampled_assets,
        )
        # (P0 fix) 触发 loop-back: rejected → draft via FSM transition
        # 这样 production 可以重新开始 (撤回循环真正闭环)
        loop_back_result: Dict[str, Any] = {"triggered": False}
        try:
            # 先确认 delivery 存在 — 用 workflow 的 db
            with sqlite3.connect(db_for_loop) as conn:
                row = conn.execute(
                    "SELECT id, status FROM deliveries WHERE id = ? OR name = ? LIMIT 1",
                    (delivery_id, delivery_id)
                ).fetchone()
            if row:
                prev_status = row[1] or "draft"  # 用 index 而非 row["status"] (无 row_factory)
                # FSM: rejected → draft 是合法的 loop-back
                # approved → draft 也是合法的 (回到起草)
                if _status_compare(prev_status, "draft") != "unknown":
                    with sqlite3.connect(db_for_loop) as conn:
                        conn.execute(
                            "UPDATE deliveries SET status = ?, reviewer = ? WHERE id = ?",
                            ("draft", f"rejected_by_{requester_id}", row[0])
                        )
                        conn.commit()
                    # 记录时间线
                    wf._add_timeline_event(
                        delivery_id, "production_loopback", requester_id,
                        {
                            "acceptance_id": record.id,
                            "reason": comments or "未指定",
                            "from_status": prev_status,
                            "to_status": "draft",
                            "loop_back": True,
                        }
                    )
                    loop_back_result = {
                        "triggered": True,
                        "from_status": prev_status,
                        "to_status": "draft",
                    }
        except Exception as e:
            loop_back_result = {"triggered": False, "error": str(e)}

        response_data: Dict[str, Any] = {
            "acceptance": record.to_dict(),
            "production_loopback": loop_back_result,
        }

        return {
            "success": True,
            "data": response_data,
            "error": None,
            "message": (
                "已拒绝并退回生产, production loop-back 已触发"
                if loop_back_result.get("triggered")
                else "已拒绝, 退回生产失败 (delivery 不存在或状态非法)"
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"拒绝失败: {e}")


@router.get("/{delivery_id}/timeline")
async def get_timeline(delivery_id: str):
    """获取交付物时间线 (P5-R1-T6)"""
    from engines.delivery_workflow import get_delivery_workflow
    wf = get_delivery_workflow()
    timeline = wf.get_delivery_timeline(delivery_id)
    return {
        "success": True,
        "data": {
            "delivery_id": delivery_id,
            "events": timeline,
            "total": len(timeline),
        },
        "error": None,
        "message": "ok",
    }


@router.post("/{delivery_id}/finalize-and-share")
async def finalize_and_share(
    delivery_id: str,
    owner_id: str = Query("system", min_length=1, max_length=64),
    expiry_hours: int = Query(72, ge=1, le=8760),
    max_downloads: int = Query(0, ge=0, le=1000000),
    password: Optional[str] = Query(None, max_length=128),
    note: str = Query("", max_length=2048),
):
    """approved 后自动分享 (P5-R1-T6)

    串联 transfer_engine.create_share + delivery_inc.snapshot + 时间线记录
    """
    from engines.delivery_workflow import get_delivery_workflow
    wf = get_delivery_workflow()
    try:
        result = wf.finalize_and_share(
            delivery_id=delivery_id,
            owner_id=owner_id,
            expiry_hours=expiry_hours,
            max_downloads=max_downloads,
            password=password,
            note=note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"finalize 失败: {e}")
    return {
        "success": True,
        "data": result,
        "error": None,
        "message": "交付物已分享",
    }


@router.get("/compare/{delivery_id_a}/{delivery_id_b}")
async def compare_deliveries(delivery_id_a: str, delivery_id_b: str):
    """对比两个交付物"""
    from engines.delivery_workflow import get_delivery_workflow
    wf = get_delivery_workflow()
    result = wf.compare_deliveries(delivery_id_a, delivery_id_b)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {
        "success": True,
        "data": result,
        "error": None,
        "message": "ok",
    }