"""
审计日志前端API路由
-------------------
- GET /api/v1/audit-logs       — 审计日志分页查询
- GET /api/v1/audit-logs/stats — 审计统计

R2-Worker-5: 添加 DateRangeParams / 维度白名单校验 (审计维度白名单: user/method/path/status/date/hour)。
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, Depends, HTTPException

from api._common.date_range import DateRangeParams
from api._common.granularity import Granularity
from api._common.dimension import is_valid_dimension

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit"])

AUDIT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "audit.db"
)

# 审计模块允许的聚合维度
AUDIT_ALLOWED_DIMENSIONS = ("user", "method", "path", "status", "date", "hour")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(AUDIT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# 实际存在的表名和列名（基于现有 audit.db schema）
TABLE_NAME = "audit_log"
COL_TIMESTAMP = "timestamp"
COL_METHOD = "method"
COL_PATH = "path"
COL_USER = "user"
COL_STATUS_CODE = "status_code"
COL_BODY_HASH = "body_hash"


def _parse_row(row) -> dict:
    return {
        "id": row["id"],
        "timestamp": row[COL_TIMESTAMP],
        "method": row[COL_METHOD],
        "path": row[COL_PATH],
        "user": row[COL_USER],
        "status_code": row[COL_STATUS_CODE],
        "body_hash": row[COL_BODY_HASH],
    }


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.get("")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    method: Optional[str] = Query(None, max_length=16, pattern=r"^(GET|POST|PUT|PATCH|DELETE)$"),
    path: Optional[str] = Query(None, max_length=512),
    dr: DateRangeParams = Depends(),
    dimension: str = Query(
        "user",
        description=f"聚合维度, 允许: {list(AUDIT_ALLOWED_DIMENSIONS)}",
    ),
):
    """审计日志分页查询

    R2-Worker-5: 注入 ``DateRangeParams`` + 维度白名单校验。
    """
    if not is_valid_dimension(dimension, scope="audit"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(AUDIT_ALLOWED_DIMENSIONS)}",
        )
    conn = get_db()
    conditions = []
    params = []
    if method:
        conditions.append(f"{COL_METHOD} = ?")
        params.append(method)
    if path:
        conditions.append(f"{COL_PATH} LIKE ?")
        params.append(f"%{path}%")
    # 日期范围过滤 (R2-Worker-5)
    if dr.start:
        conditions.append(f"{COL_TIMESTAMP} >= ?")
        params.append(dr.start.isoformat())
    if dr.end:
        conditions.append(f"{COL_TIMESTAMP} <= ?")
        params.append(f"{dr.end.isoformat()}T23:59:59")
    where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    # 总数
    total = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME}{where_clause}", params
    ).fetchone()[0]

    # 分页
    offset = (page - 1) * size
    rows = conn.execute(
        f"SELECT * FROM {TABLE_NAME}{where_clause} ORDER BY {COL_TIMESTAMP} DESC LIMIT ? OFFSET ?",
        params + [size, offset],
    ).fetchall()
    conn.close()

    items = [_parse_row(r) for r in rows]
    pages = max(1, (total + size - 1) // size)
    return {
        "success": True,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        },
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "dimension": dimension,
        "message": "ok",
    }


@router.get("/stats")
async def get_audit_stats(
    dr: DateRangeParams = Depends(),
    granularity: Granularity = Query("day", description="聚合粒度"),
    dimension: str = Query(
        "method",
        description=f"聚合维度, 允许: {list(AUDIT_ALLOWED_DIMENSIONS)}",
    ),
):
    """审计统计：今日操作数 / 类型分布

    R2-Worker-5: 注入 ``DateRangeParams`` + granularity 枚举 + 维度白名单校验。
    """
    if not is_valid_dimension(dimension, scope="audit"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(AUDIT_ALLOWED_DIMENSIONS)}",
        )
    conn = get_db()
    # 按时间范围过滤
    if dr.start:
        start_ts = dr.start.isoformat()
    else:
        start_ts = "1970-01-01"
    if dr.end:
        end_ts = f"{dr.end.isoformat()}T23:59:59"
    else:
        end_ts = "2999-12-31"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_count = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE {COL_TIMESTAMP} LIKE ?",
        (f"{today}%",),
    ).fetchone()[0]

    # 方法分布（按时间范围 + 维度聚合）
    rows = conn.execute(
        f"""SELECT {COL_METHOD} as action, COUNT(*) as cnt FROM {TABLE_NAME}
           WHERE {COL_TIMESTAMP} >= ? AND {COL_TIMESTAMP} <= ?
           GROUP BY {COL_METHOD} ORDER BY cnt DESC""",
        (start_ts, end_ts),
    ).fetchall()
    conn.close()

    action_distribution = {row["action"]: row["cnt"] for row in rows}
    return {
        "success": True,
        "data": {
            "today_operations": today_count,
            "action_distribution": action_distribution,
            "total_actions": sum(action_distribution.values()),
        },
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "granularity": granularity,
        "dimension": dimension,
        "message": "ok",
    }
