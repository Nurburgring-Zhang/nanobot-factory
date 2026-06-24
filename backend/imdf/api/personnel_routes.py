"""
F7.2 人员绩效 API 路由
=======================
GET /api/stats/personnel         — 按人员统计 (标注量/审核量/质量分/效率)
GET /api/stats/personnel/{name}  — 单人详细绩效
POST /api/stats/personnel/log    — 记录人员活动

R2-Worker-5: 添加 DateRangeParams / 维度白名单校验 (period 受控枚举)。
"""

import json
import time
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Body, Query, Depends
from pydantic import BaseModel, Field

from api._common.date_range import DateRangeParams
from api._common.granularity import Granularity
from api._common.dimension import is_valid_dimension

router = APIRouter(prefix="/api/stats", tags=["personnel_stats"])

# 绩效数据持久化
STATS_DIR = Path("data/stats")
STATS_DIR.mkdir(parents=True, exist_ok=True)
PERSONNEL_FILE = STATS_DIR / "personnel_activity.json"

# 人员绩效允许的 period 枚举
PERSONNEL_PERIODS = ("today", "week", "month", "all")
# 人员绩效允许的 action 枚举
PERSONNEL_ACTIONS = ("annotate", "review", "approve", "export", "edit", "delete")
# 人员绩效允许的聚合维度
PERSONNEL_ALLOWED_DIMENSIONS = ("worker", "team", "action", "status", "date", "category")


class ActivityLog(BaseModel):
    """人员活动记录 — R2-Worker-5: 加字段约束"""
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\u4e00-\u9fa5]{1,128}$", description="人员姓名")
    action: str = Field("annotate", description=f"动作类型, 允许: {list(PERSONNEL_ACTIONS)}")
    item_count: int = Field(1, ge=1, le=1_000_000, description="处理数量")
    quality_score: float = Field(0.0, ge=0.0, le=100.0, description="质量评分 (0-100)")
    time_spent_minutes: float = Field(0.0, ge=0.0, le=100_000.0, description="耗时(分钟)")
    dataset_id: str = Field("", max_length=128, pattern=r"^[a-zA-Z0-9_\-]{0,128}$", description="关联数据集")
    note: str = Field("", max_length=2000, description="备注")


def _load_activities() -> Dict[str, List[dict]]:
    """加载所有活动记录"""
    if PERSONNEL_FILE.exists():
        try:
            return json.loads(PERSONNEL_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_activities(data: Dict[str, List[dict]]):
    """保存活动记录"""
    PERSONNEL_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ── Routes ──────────────────────────────────────────────────────────────

@router.post("/personnel/log")
async def log_activity(log: ActivityLog):
    """记录人员活动

    记录一次标注/审核/导出等操作，用于后续统计。

    R2-Worker-5: 字段约束由 Pydantic ``ActivityLog`` 强制 (Pydantic v2 自动 422)。
    """
    # action 枚举校验 (Pydantic Literal 也可, 这里保持字符串白名单)
    if log.action and log.action not in PERSONNEL_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"action {log.action!r} 不在白名单, 允许: {list(PERSONNEL_ACTIONS)}",
        )

    activities = _load_activities()
    if log.name not in activities:
        activities[log.name] = []

    activity = {
        "timestamp": datetime.now().isoformat(),
        "timestamp_ts": time.time(),
        "action": log.action,
        "item_count": log.item_count,
        "quality_score": log.quality_score,
        "time_spent_minutes": log.time_spent_minutes,
        "dataset_id": log.dataset_id,
        "note": log.note,
    }
    activities[log.name].append(activity)

    # 只保留最近1000条
    if len(activities[log.name]) > 1000:
        activities[log.name] = activities[log.name][-1000:]

    _save_activities(activities)

    return {
        "success": True,
        "data": activity,
        "message": f"Activity logged for {log.name}",
    }


@router.get("/personnel")
async def get_personnel_stats(
    period: str = Query(
        "all",
        description=f"统计周期, 允许: {list(PERSONNEL_PERIODS)}",
        pattern=f"^({'|'.join(PERSONNEL_PERIODS)})$",
    ),
    action: Optional[str] = Query(
        None,
        description=f"按动作过滤, 允许: {list(PERSONNEL_ACTIONS)}",
    ),
    dr: DateRangeParams = Depends(),
    dimension: str = Query(
        "worker",
        description=f"聚合维度, 允许: {list(PERSONNEL_ALLOWED_DIMENSIONS)}",
    ),
):
    """按人员统计 — 标注量/审核量/质量分/效率

    返回所有人员或指定人员的绩效汇总。

    R2-Worker-5: period 枚举 + action 白名单 + 注入 ``DateRangeParams`` + 维度白名单。
    """
    if action and action not in PERSONNEL_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"action {action!r} 不在白名单, 允许: {list(PERSONNEL_ACTIONS)}",
        )
    if not is_valid_dimension(dimension, scope="crowd"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(PERSONNEL_ALLOWED_DIMENSIONS)}",
        )
    activities = _load_activities()

    if not activities:
        # 返回模拟数据以便演示
        return {
            "success": True,
            "data": {
                "personnel": [],
                "total_personnel": 0,
                "total_activities": 0,
                "period": period,
            },
            "message": "No activity data yet. Use POST /api/stats/personnel/log to record activities.",
        }

    now = time.time()
    period_filters = {
        "today": 86400,
        "week": 604800,
        "month": 2592000,
        "all": float("inf"),
    }
    cutoff = now - period_filters.get(period, float("inf"))

    personnel_stats = []

    for name, acts in activities.items():
        # 时间过滤
        filtered = acts
        if period != "all":
            filtered = [a for a in acts if a.get("timestamp_ts", 0) >= cutoff]

        # 动作过滤
        if action:
            filtered = [a for a in filtered if a.get("action") == action]

        if not filtered:
            continue

        # 聚合统计
        total_items = sum(a.get("item_count", 0) for a in filtered)

        # 各动作计数
        action_counts = {}
        for a in filtered:
            act = a.get("action", "unknown")
            action_counts[act] = action_counts.get(act, 0) + a.get("item_count", 0)

        # 质量分
        quality_scores = [a["quality_score"] for a in filtered if a.get("quality_score", 0) > 0]
        avg_quality = round(statistics.mean(quality_scores), 2) if quality_scores else 0.0

        # 效率 (items per hour)
        total_minutes = sum(a.get("time_spent_minutes", 0) for a in filtered)
        efficiency = round(total_items / (total_minutes / 60), 2) if total_minutes > 0 else 0.0

        # 活动时间范围
        timestamps = [a.get("timestamp_ts", 0) for a in filtered]
        first_activity = datetime.fromtimestamp(min(timestamps)).isoformat() if timestamps else ""
        last_activity = datetime.fromtimestamp(max(timestamps)).isoformat() if timestamps else ""

        personnel_stats.append({
            "name": name,
            "total_items": total_items,
            "total_activities": len(filtered),
            "action_breakdown": action_counts,
            "avg_quality_score": avg_quality,
            "quality_scores_count": len(quality_scores),
            "total_time_minutes": round(total_minutes, 1),
            "efficiency_items_per_hour": efficiency,
            "first_activity": first_activity,
            "last_activity": last_activity,
        })

    # 按总处理量排序
    personnel_stats.sort(key=lambda x: x["total_items"], reverse=True)

    # 汇总
    total_items_all = sum(p["total_items"] for p in personnel_stats)
    total_activities_all = sum(p["total_activities"] for p in personnel_stats)

    return {
        "success": True,
        "data": {
            "personnel": personnel_stats,
            "total_personnel": len(personnel_stats),
            "total_activities": total_activities_all,
            "total_items_processed": total_items_all,
            "period": period,
            "action_filter": action,
        },
        "message": f"Stats for {len(personnel_stats)} personnel ({period})",
    }


@router.get("/personnel/{name}")
async def get_personnel_detail(
    name: str,
    period: str = Query(
        "all",
        description=f"统计周期, 允许: {list(PERSONNEL_PERIODS)}",
        pattern=f"^({'|'.join(PERSONNEL_PERIODS)})$",
    ),
    dr: DateRangeParams = Depends(),
):
    """获取单人详细绩效数据

    返回某人的完整活动历史和统计。

    R2-Worker-5: period 枚举 + 注入 ``DateRangeParams``。
    """
    if not name or len(name) > 128:
        raise HTTPException(status_code=400, detail="name 长度必须在 1..128 字符")
    activities = _load_activities()

    if name not in activities:
        raise HTTPException(status_code=404, detail=f"No data for personnel: {name}")

    acts = activities[name]

    # 时间过滤
    now = time.time()
    period_filters = {
        "today": 86400,
        "week": 604800,
        "month": 2592000,
        "all": float("inf"),
    }
    cutoff = now - period_filters.get(period, float("inf"))

    if period != "all":
        acts = [a for a in acts if a.get("timestamp_ts", 0) >= cutoff]

    acts = sorted(acts, key=lambda x: x.get("timestamp_ts", 0), reverse=True)

    # 聚合
    total_items = sum(a.get("item_count", 0) for a in acts)
    action_counts = {}
    quality_scores = []

    for a in acts:
        act = a.get("action", "unknown")
        action_counts[act] = action_counts.get(act, 0) + a.get("item_count", 0)
        if a.get("quality_score", 0) > 0:
            quality_scores.append(a["quality_score"])

    avg_quality = round(statistics.mean(quality_scores), 2) if quality_scores else 0.0
    total_minutes = sum(a.get("time_spent_minutes", 0) for a in acts)
    efficiency = round(total_items / (total_minutes / 60), 2) if total_minutes > 0 else 0.0

    # 按日期分组
    daily_summary: Dict[str, dict] = {}
    for a in acts:
        date_key = datetime.fromtimestamp(a.get("timestamp_ts", 0)).strftime("%Y-%m-%d")
        if date_key not in daily_summary:
            daily_summary[date_key] = {"items": 0, "activities": 0, "minutes": 0}
        daily_summary[date_key]["items"] += a.get("item_count", 0)
        daily_summary[date_key]["activities"] += 1
        daily_summary[date_key]["minutes"] += a.get("time_spent_minutes", 0)

    return {
        "success": True,
        "data": {
            "name": name,
            "period": period,
            "summary": {
                "total_items": total_items,
                "total_activities": len(acts),
                "action_breakdown": action_counts,
                "avg_quality_score": avg_quality,
                "total_time_minutes": round(total_minutes, 1),
                "efficiency_items_per_hour": efficiency,
            },
            "daily_breakdown": [
                {"date": d, **s} for d, s in sorted(daily_summary.items(), reverse=True)
            ],
            "recent_activities": acts[:50],  # 最近50条
        },
        "message": f"Detail stats for {name}",
    }
