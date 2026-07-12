"""
管道监控路由 - Sprint 3-2 (真实数据库实现)
======================
GET /api/monitor/pipeline → 管道快照
GET /api/monitor/history?minutes=60 → 历史趋势 (从 scheduler_history.db 读取)

R2-Worker-5: 添加 DateRangeParams / Granularity / Dimension 白名单校验。
"""
from fastapi import APIRouter, Query, Depends
from typing import Dict, Any, List
from datetime import datetime, timedelta
import sqlite3, os

from api._common.date_range import DateRangeParams
from api._common.granularity import Granularity
from api._common.dimension import is_valid_dimension

router = APIRouter(prefix="/api/monitor", tags=["monitor"])

_IMDF_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "imdf.db")
_SCHEDULER_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "scheduler_history.db")

# 监控模块允许的聚合维度
MONITOR_ALLOWED_DIMENSIONS = (
    "job", "status", "queue", "date", "hour", "category", "action",
)


@router.get("/pipeline")
async def pipeline_snapshot(
    dr: DateRangeParams = Depends(),
    dimension: str = Query(
        "job",
        description=f"聚合维度, 允许: {list(MONITOR_ALLOWED_DIMENSIONS)}",
    ),
):
    """管道快照: 队列深度 / 运行中任务数 / 成功率 - 从 scheduler_history.db + imdf.db 读取

    R2-Worker-5: 注入 ``DateRangeParams`` + 维度白名单校验。
    """
    if not is_valid_dimension(dimension, scope="monitor"):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(MONITOR_ALLOWED_DIMENSIONS)}",
        )
    try:
        conn = sqlite3.connect(_SCHEDULER_DB)
        cursor = conn.cursor()

        # 队列深度 = 所有 job 数量
        total_jobs = cursor.execute("SELECT COUNT(*) FROM job_history").fetchone()[0]
        # 运行中 = status='running'
        running = cursor.execute(
            "SELECT COUNT(*) FROM job_history WHERE status='running'"
        ).fetchone()[0]
        # 成功率
        completed = cursor.execute(
            "SELECT COUNT(*) FROM job_history WHERE status='completed'"
        ).fetchone()[0]
        failed = cursor.execute(
            "SELECT COUNT(*) FROM job_history WHERE status='failed'"
        ).fetchone()[0]
        conn.close()

        success_rate = round(completed / max(total_jobs, 1) * 100, 1)

        return {
            "queue_depth": total_jobs,
            "running_tasks": running,
            "completed": completed,
            "failed": failed,
            "success_rate": success_rate,
            "timestamp": datetime.now().isoformat(),
            "source": "scheduler_history.db",
            "range": {"start": str(dr.start), "end": str(dr.end)},
            "dimension": dimension,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/history")
async def pipeline_history(
    minutes: int = Query(60, ge=1, le=1440),
    granularity: Granularity = Query("hour", description="聚合粒度"),
    dimension: str = Query(
        "job",
        description=f"聚合维度, 允许: {list(MONITOR_ALLOWED_DIMENSIONS)}",
    ),
):
    """历史趋势数据 - 从 scheduler_history.db job_history 表读取

    R2-Worker-5: granularity 枚举 + 维度白名单校验 (保留 minutes 兼容)。
    """
    if not is_valid_dimension(dimension, scope="monitor"):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(MONITOR_ALLOWED_DIMENSIONS)}",
        )
    try:
        conn = sqlite3.connect(_SCHEDULER_DB)
        cursor = conn.cursor()
        # P13-C1 优化: 加 LIMIT 500 (job_history 频繁写入, 大表全扫会拖死监控接口)
        rows = cursor.execute(
            "SELECT id, job_id, job_name, run_at, status, result, error, retry_count, duration_ms FROM job_history ORDER BY run_at DESC LIMIT 500"
        ).fetchall()
        conn.close()

        points: List[Dict[str, Any]] = []
        for r in rows:
            run_at = r[3]
            # 过滤时间范围
            try:
                ts = datetime.fromisoformat(run_at)
            except Exception:
                ts = datetime.now()
            if (datetime.now() - ts).total_seconds() > minutes * 60:
                continue

            points.append({
                "id": r[0],
                "job_id": r[1],
                "job_name": r[2],
                "timestamp": run_at,
                "status": r[4],
                "result": r[5] or "",
                "error": r[6] or "",
                "retry_count": r[7] or 0,
                "duration_ms": r[8] or 0,
            })

        return {
            "minutes": minutes,
            "granularity": granularity,
            "dimension": dimension,
            "points": points,
            "total": len(points),
            "source": "scheduler_history.db/job_history"
        }
    except Exception as e:
        return {"success": False, "error": str(e), "points": []}
