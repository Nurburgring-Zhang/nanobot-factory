"""账号与数据统计 — 个人/项目/全局三维度 + 排行 + 报告"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from core.persistent_base import PersistentManager


@dataclass
class UserStats:
    user_id: str
    username: str = ""
    total_tasks: int = 0
    completed_tasks: int = 0
    approval_rate: float = 0.0
    avg_score: float = 0.0
    total_hours: float = 0.0
    daily_output: List[int] = field(default_factory=lambda: [0] * 30)
    rank_in_dept: int = 0
    rank_global: int = 0


@dataclass
class ProjectStats:
    project_id: str
    name: str = ""
    total_items: int = 0
    datasets: int = 0
    data_types: Dict[str, int] = field(default_factory=dict)
    task_completion_rate: float = 0.0
    avg_quality_score: float = 0.0
    total_cost: float = 0.0
    cost_per_item: float = 0.0
    daily_new: List[int] = field(default_factory=lambda: [0] * 30)


@dataclass
class GlobalStats:
    total_users: int = 0
    active_users_dau: int = 0
    active_users_mau: int = 0
    total_items: int = 0
    total_datasets: int = 0
    storage_used_gb: float = 0.0
    total_tasks: int = 0
    tasks_completed: int = 0
    avg_process_days: float = 0.0
    data_growth: List[int] = field(default_factory=lambda: [0] * 12)


@dataclass
class Ranking:
    annotator_weekly: List[Dict] = field(default_factory=list)
    quality_weekly: List[Dict] = field(default_factory=list)
    efficiency_weekly: List[Dict] = field(default_factory=list)
    active_weekly: List[Dict] = field(default_factory=list)


class StatsManager(PersistentManager):
    _db_table = "user_stats"
    _db_key_field = "user_id"
    _db_fields = ["user_id","username","total_tasks","completed_tasks","approval_rate","avg_score","total_hours","daily_output","rank_in_dept","rank_global"]

    def __init__(self):
        self._user_stats: Dict[str, UserStats] = {}
        self._project_stats: Dict[str, ProjectStats] = {}
        self._global = GlobalStats()
        self._rankings = Ranking()
        super().__init__()
        self._load_from_db()

    def _load_from_db(self):
        for row in self._load_all():
            uid = row.pop("user_id")
            stats = UserStats(user_id=uid, **row)
            self._user_stats[uid] = stats

    def record_task_completed(self, user_id: str, username: str, score: float):
        s = self._user_stats.setdefault(
            user_id, UserStats(user_id=user_id, username=username)
        )
        s.total_tasks += 1
        s.completed_tasks += 1
        s.avg_score = (
            s.avg_score * (s.completed_tasks - 1) + score
        ) / s.completed_tasks
        s.approval_rate = s.completed_tasks / s.total_tasks * 100
        self._save(user_id, {"user_id": user_id, "username": username, "total_tasks": s.total_tasks, "completed_tasks": s.completed_tasks, "approval_rate": s.approval_rate, "avg_score": s.avg_score, "total_hours": s.total_hours, "daily_output": s.daily_output, "rank_in_dept": s.rank_in_dept, "rank_global": s.rank_global})

    def get_user_stats(self, user_id: str) -> Optional[UserStats]:
        return self._user_stats.get(user_id)

    def get_all_user_stats(self) -> List[UserStats]:
        return list(self._user_stats.values())

    def update_project(
        self,
        project_id: str,
        name: str,
        items_added: int = 0,
        task_done: int = 0,
        score: float = 0,
        cost: float = 0,
    ):
        s = self._project_stats.setdefault(
            project_id, ProjectStats(project_id=project_id, name=name)
        )
        s.total_items += items_added
        s.total_cost += cost
        if items_added > 0:
            s.cost_per_item = s.total_cost / s.total_items if s.total_items > 0 else 0

    def get_project_stats(self, project_id: str) -> Optional[ProjectStats]:
        return self._project_stats.get(project_id)

    def get_global_stats(self) -> GlobalStats:
        self._global.total_users = len(self._user_stats)
        self._global.total_items = sum(
            ps.total_items for ps in self._project_stats.values()
        )
        self._global.total_tasks = sum(
            us.total_tasks for us in self._user_stats.values()
        )
        self._global.tasks_completed = sum(
            us.completed_tasks for us in self._user_stats.values()
        )
        self._global.storage_used_gb = round(
            self._global.total_items * 0.5 / 1024, 2
        )
        return self._global

    def get_rankings(self) -> Ranking:
        users = list(self._user_stats.values())
        by_completed = sorted(users, key=lambda u: u.completed_tasks, reverse=True)[
            :10
        ]
        by_quality = sorted(users, key=lambda u: u.avg_score, reverse=True)[:10]
        by_efficiency = sorted(
            users, key=lambda u: u.approval_rate, reverse=True
        )[:10]
        self._rankings.annotator_weekly = [
            {"user": u.username, "value": u.completed_tasks} for u in by_completed
        ]
        self._rankings.quality_weekly = [
            {"user": u.username, "value": u.avg_score} for u in by_quality
        ]
        self._rankings.efficiency_weekly = [
            {"user": u.username, "value": u.approval_rate} for u in by_efficiency
        ]
        return self._rankings
