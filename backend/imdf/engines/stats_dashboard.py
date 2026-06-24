"""统计看板引擎 - 多维度数据/团队/生产统计"""
from __future__ import annotations
import time
import statistics
import calendar
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class StatsSnapshot:
    """统计快照"""
    timestamp: float = field(default_factory=time.time)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataStats:
    """数据统计"""
    total_data_count: int = 0
    daily_new_count: int = 0
    weekly_new_count: int = 0
    monthly_new_count: int = 0
    avg_quality_score: float = 0.0
    quality_distribution: Dict[str, int] = field(default_factory=dict)
    total_dataset_size_gb: float = 0.0


@dataclass
class TeamStats:
    """团队统计"""
    total_teams: int = 0
    total_members: int = 0
    per_capita_output: float = 0.0  # 人均产能
    task_completion_rate: float = 0.0  # 任务完成率
    delay_rate: float = 0.0  # 延迟率
    pass_rate: float = 0.0  # 通过率


class StatsDashboard:
    """统计看板 - 收集并展示多维统计指标"""

    def __init__(self):
        self.snapshots: List[StatsSnapshot] = []
        self._daily_logs: Dict[str, List[dict]] = defaultdict(list)
        self._daily_stats: Dict[str, dict] = {}

    # ── data collectors ──

    def collect_data_stats(self, data_count: int = 0, new_data: int = 0,
                           quality_scores: Optional[List[float]] = None,
                           dataset_size_gb: float = 0.0) -> DataStats:
        """收集数据总量/新增/质量分"""
        scores = quality_scores or []
        avg_q = round(statistics.mean(scores), 2) if scores else 0.0

        # 质量分分布
        dist: Dict[str, int] = {"0-60": 0, "60-80": 0, "80-90": 0, "90-100": 0}
        for s in scores:
            if s < 60:
                dist["0-60"] += 1
            elif s < 80:
                dist["60-80"] += 1
            elif s < 90:
                dist["80-90"] += 1
            else:
                dist["90-100"] += 1

        ds = DataStats(
            total_data_count=data_count,
            daily_new_count=new_data,
            weekly_new_count=new_data * 7,
            monthly_new_count=new_data * 30,
            avg_quality_score=avg_q,
            quality_distribution=dist,
            total_dataset_size_gb=dataset_size_gb,
        )
        self._record_snapshot("data_stats", ds)
        return ds

    def collect_team_stats(self, total_teams: int = 0, total_members: int = 0,
                           tasks_completed: int = 0, tasks_total: int = 0,
                           tasks_delayed: int = 0,
                           passed_items: int = 0, total_items: int = 0) -> TeamStats:
        """收集团队统计维度"""
        completion_rate = round(tasks_completed / tasks_total * 100, 2) if tasks_total else 0.0
        delay_rate = round(tasks_delayed / tasks_total * 100, 2) if tasks_total else 0.0
        pass_rate = round(passed_items / total_items * 100, 2) if total_items else 0.0
        per_capita = round(tasks_completed / total_members, 2) if total_members else 0.0

        ts = TeamStats(
            total_teams=total_teams,
            total_members=total_members,
            per_capita_output=per_capita,
            task_completion_rate=completion_rate,
            delay_rate=delay_rate,
            pass_rate=pass_rate,
        )
        self._record_snapshot("team_stats", ts)
        return ts

    def collect_production_stats(self, **kwargs) -> StatsSnapshot:
        """通用生产统计收集"""
        snap = StatsSnapshot(metrics=kwargs)
        self._record_snapshot("production_stats", snap)
        return snap

    # ── reporting ──

    def _date_key(self, dt: Optional[datetime] = None) -> str:
        dt = dt or datetime.now()
        return dt.strftime("%Y-%m-%d")

    def _week_key(self, dt: Optional[datetime] = None) -> str:
        dt = dt or datetime.now()
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    def _month_key(self, dt: Optional[datetime] = None) -> str:
        dt = dt or datetime.now()
        return dt.strftime("%Y-%m")

    def _record_snapshot(self, category: str, obj: Any):
        snap = StatsSnapshot(metrics={
            "category": category,
            "data": obj,
        })
        self.snapshots.append(snap)
        date_key = self._date_key()
        self._daily_logs[date_key].append(snap.metrics)

    def get_daily_report(self, date_str: Optional[str] = None) -> dict:
        """获取某天的聚合报告"""
        ds = date_str or self._date_key()
        logs = self._daily_logs.get(ds, [])
        report: Dict[str, Any] = {
            "date": ds,
            "total_snapshots": len(logs),
        }

        # aggregate data_stats
        data_vals = [l["data"] for l in logs if l.get("category") == "data_stats" and hasattr(l["data"], "total_data_count")]
        if data_vals:
            report["data"] = {
                "total_data": sum(d.total_data_count for d in data_vals),
                "new_data": sum(d.daily_new_count for d in data_vals),
                "avg_quality": round(statistics.mean(d.avg_quality_score for d in data_vals), 2),
            }

        # aggregate team_stats
        team_vals = [l["data"] for l in logs if l.get("category") == "team_stats" and hasattr(l["data"], "total_teams")]
        if team_vals:
            report["team"] = {
                "total_teams": sum(t.total_teams for t in team_vals),
                "total_members": sum(t.total_members for t in team_vals),
                "avg_completion_rate": round(statistics.mean(t.task_completion_rate for t in team_vals), 2),
                "avg_delay_rate": round(statistics.mean(t.delay_rate for t in team_vals), 2),
                "avg_pass_rate": round(statistics.mean(t.pass_rate for t in team_vals), 2),
                "avg_per_capita": round(statistics.mean(t.per_capita_output for t in team_vals), 2),
            }

        return report

    def get_weekly_report(self, week_str: Optional[str] = None) -> dict:
        """获取周报告"""
        ws = week_str or self._week_key()
        # collect daily logs for this week
        week_dates = []
        if week_str:
            year, w = week_str.split("-W")
            first_day = datetime.strptime(f"{year}-W{w}-1", "%G-W%V-%u")
        else:
            first_day = datetime.now()
            # go back to Monday
            first_day -= timedelta(days=first_day.weekday())

        for i in range(7):
            d = first_day + timedelta(days=i)
            week_dates.append(self._date_key(d))

        reports = [self.get_daily_report(d) for d in week_dates]
        return self._aggregate_period_report(ws, reports, "weekly")

    def get_monthly_report(self, month_str: Optional[str] = None) -> dict:
        """获取月报告"""
        ms = month_str or self._month_key()
        year, month = ms.split("-")
        _, days_in_month = calendar.monthrange(int(year), int(month))
        first_day = datetime(int(year), int(month), 1)
        month_dates = []
        for i in range(days_in_month):
            d = first_day + timedelta(days=i)
            month_dates.append(self._date_key(d))

        reports = [self.get_daily_report(d) for d in month_dates]
        return self._aggregate_period_report(ms, reports, "monthly")

    def _aggregate_period_report(self, period_key: str, reports: List[dict],
                                  period_type: str) -> dict:
        """聚合多日报告"""
        data_totals = [r["data"] for r in reports if "data" in r]
        team_totals = [r["team"] for r in reports if "team" in r]

        result: Dict[str, Any] = {
            "period": period_key,
            "type": period_type,
            "days_reported": len(reports),
        }

        if data_totals:
            result["data"] = {
                "total_data": sum(d["total_data"] for d in data_totals),
                "new_data": sum(d["new_data"] for d in data_totals),
                "avg_quality": round(
                    statistics.mean(d["avg_quality"] for d in data_totals), 2),
            }

        if team_totals:
            result["team"] = {
                "total_teams": max(d["total_teams"] for d in team_totals),
                "total_members": max(d["total_members"] for d in team_totals),
                "avg_completion_rate": round(
                    statistics.mean(d["avg_completion_rate"] for d in team_totals), 2),
                "avg_delay_rate": round(
                    statistics.mean(d["avg_delay_rate"] for d in team_totals), 2),
                "avg_pass_rate": round(
                    statistics.mean(d["avg_pass_rate"] for d in team_totals), 2),
                "avg_per_capita": round(
                    statistics.mean(d["avg_per_capita"] for d in team_totals), 2),
            }

        return result

    def compare_periods(self, period_a: str, period_b: str,
                        period_type: str = "daily") -> dict:
        """对比两个周期的统计指标"""
        if period_type == "daily":
            r_a = self.get_daily_report(period_a)
            r_b = self.get_daily_report(period_b)
        elif period_type == "weekly":
            r_a = self.get_weekly_report(period_a)
            r_b = self.get_weekly_report(period_b)
        elif period_type == "monthly":
            r_a = self.get_monthly_report(period_a)
            r_b = self.get_monthly_report(period_b)
        else:
            return {"error": f"unsupported period type: {period_type}"}

        comparison: Dict[str, Any] = {
            "period_a": period_a,
            "period_b": period_b,
            "type": period_type,
        }

        # compare data section
        if "data" in r_a and "data" in r_b:
            diff: Dict[str, Any] = {}
            for key in r_a["data"]:
                va = r_a["data"][key]
                vb = r_b["data"][key]
                if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                    diff[key] = {
                        "a": va,
                        "b": vb,
                        "diff": round(vb - va, 2),
                        "pct_change": round((vb - va) / va * 100, 2) if va else 0,
                    }
            comparison["data_diff"] = diff

        if "team" in r_a and "team" in r_b:
            tdiff: Dict[str, Any] = {}
            for key in r_a["team"]:
                va = r_a["team"][key]
                vb = r_b["team"][key]
                if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                    tdiff[key] = {
                        "a": va,
                        "b": vb,
                        "diff": round(vb - va, 2),
                        "pct_change": round((vb - va) / va * 100, 2) if va else 0,
                    }
            comparison["team_diff"] = tdiff

        return comparison
