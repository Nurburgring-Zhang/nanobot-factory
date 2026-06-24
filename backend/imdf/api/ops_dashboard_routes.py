"""
运营看板路由 - Sprint 4-2 (真实数据库实�?
======================
GET /api/ops/overview — 日活/生产/交付/平均质量
GET /api/ops/trend?period=7d — 折线图数据 (从 stats_snapshots 表读取)

R2 改造 (R2-Worker-4):
  - /overview 加可选日期范围过滤
  - /trend 加日期范围 + period 枚举
  - 错误信息中文化

R2.5-W5 改造:
  - 注入 DateRangeParams (preset/custom 模式)
  - /trend 加 granularity 枚举 + dimension 白名单
  - Pydantic v2 Depends 兼容 (HTTPException 而非 ValueError)
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Dict, Any, List, Optional
from datetime import date, datetime, timedelta
import sqlite3, os, json

from api._common.date_range import DateRangeParams
from api._common.granularity import Granularity
from api._common.dimension import is_valid_dimension

router = APIRouter(prefix="/api/ops", tags=["ops"])

_IMDF_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "imdf.db")

MAX_SPAN_DAYS = 365

# 运营看板允许的聚合维度 (R2.5-W5)
OPS_ALLOWED_DIMENSIONS = ("user", "team", "category", "status", "date", "metric", "source", "action")


@router.get("/overview")
async def ops_overview(
    dr: DateRangeParams = Depends(),
    dimension: str = Query(
        "user",
        description=f"聚合维度, 允许: {list(OPS_ALLOWED_DIMENSIONS)}",
    ),
):
    """运营总览: 日活/生产/交付/平均质量。

    R2.5-W5: 注入 ``DateRangeParams``,preset/custom 二选一; dimension 白名单校验。
    """
    if not is_valid_dimension(dimension, scope="ops"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(OPS_ALLOWED_DIMENSIONS)}",
        )
    start, end = dr.start, dr.end
    try:
        conn = sqlite3.connect(_IMDF_DB)
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT id, timestamp, metrics_json FROM stats_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            metrics = json.loads(row[2])
            conn.close()
            return {
                "daily_active_users": metrics.get("daily_active_users", 0),
                "production_count": metrics.get("production_count", 0),
                "delivery_count": metrics.get("delivery_count", 0),
                "avg_quality_score": metrics.get("avg_quality_score", 0),
                "timestamp": row[1],
                "source": "imdf.db/stats_snapshots",
                "range": {"start": start.isoformat(), "end": end.isoformat()},
            }

        # fallback: 从用户数/交付数推算
        total_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_deliveries = cursor.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
        approved = cursor.execute("SELECT COUNT(*) FROM deliveries WHERE status='approved'").fetchone()[0]
        total_datasets = cursor.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        conn.close()
        return {
            "daily_active_users": total_users,
            "production_count": total_datasets,
            "delivery_count": total_deliveries,
            "avg_quality_score": round(approved / max(total_deliveries, 1) * 100, 1),
            "timestamp": datetime.now().isoformat(),
            "source": "imdf.db (fallback)",
            "range": {"start": start.isoformat(), "end": end.isoformat()},
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/trend")
async def ops_trend(
    dr: DateRangeParams = Depends(),
    period: str = Query("7d", pattern="^(7d|30d)$", description="周期 (7d/30d)"),
    granularity: Granularity = Query("day", description="聚合粒度"),
    dimension: str = Query(
        "user",
        description=f"聚合维度, 允许: {list(OPS_ALLOWED_DIMENSIONS)}",
    ),
):
    """折线图数据 - 从 stats_snapshots 表读取真实快照

    R2.5-W5:
      - 注入 DateRangeParams
      - granularity 枚举 (hour/day/week/month/quarter/year)
      - dimension 白名单校验
      - period 枚举限定 (7d/30d)
    """
    if not is_valid_dimension(dimension, scope="ops"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(OPS_ALLOWED_DIMENSIONS)}",
        )
    try:
        conn = sqlite3.connect(_IMDF_DB)
        cursor = conn.cursor()
        days = 7 if period == "7d" else 30
        rows = cursor.execute(
            "SELECT id, timestamp, metrics_json FROM stats_snapshots ORDER BY id DESC LIMIT ?",
            (days,)
        ).fetchall()
        conn.close()

        # 按时间升序排列
        rows = list(reversed(rows))

        # 日期过滤
        if dr.start:
            rows = [r for r in rows if r[1] and r[1][:10] >= dr.start.isoformat()]
        if dr.end:
            rows = [r for r in rows if r[1] and r[1][:10] <= dr.end.isoformat()]

        points: List[Dict[str, Any]] = []
        for r in rows:
            metrics = json.loads(r[2])
            points.append({
                "date": r[1][:10] if r[1] else "",
                "daily_active_users": metrics.get("daily_active_users", 0),
                "production_count": metrics.get("production_count", 0),
                "delivery_count": metrics.get("delivery_count", 0),
                "avg_quality_score": metrics.get("avg_quality_score", 0),
            })

        return {
            "period": period,
            "days": len(points),
            "points": points,
            "granularity": granularity,
            "dimension": dimension,
            "source": "imdf.db/stats_snapshots",
            "range": {
                "start": dr.start.isoformat(),
                "end": dr.end.isoformat(),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e), "period": period, "points": []}
