"""任务全生命周期管理"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel
from core.persistent_base import PersistentManager


class TaskType(str, Enum):
    COLLECTION = "collection"
    CLEANING = "cleaning"
    ANNOTATION = "annotation"
    REVIEW = "review"
    QC = "qc"
    DATASET_BUILD = "dataset_build"
    EXPORT = "export"
    EVAL = "evaluation"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_ARBITRATION = "needs_arbitration"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AssignmentStrategy(str, Enum):
    MANUAL = "manual"
    ROUND_ROBIN = "round_robin"
    LOAD_BALANCE = "load_balance"
    SKILL_MATCH = "skill_match"
    CLAIM = "claim"


class Task(BaseModel):
    id: str
    name: str
    type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    requirement_id: str = ""
    project_id: str
    creator_id: str
    assigned_to: str = ""
    reviewer_id: str = ""
    data_filter: Dict[str, Any] = {}
    target_count: int = 0
    completed_count: int = 0
    deadline: str = ""
    quality_score: float = 0.0
    is_arbitration: bool = False
    arbitrator_id: str = ""
    created_at: str = ""
    completed_at: str = ""


class TaskManager(PersistentManager):
    _db_table = "tasks"
    _db_fields = ["id","name","type","status","requirement_id","project_id","creator_id","assigned_to","reviewer_id","data_filter","target_count","completed_count","deadline","quality_score","is_arbitration","arbitrator_id","created_at","completed_at"]

    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._user_task_queue: Dict[str, List[str]] = {}
        self._round_robin_index: Dict[str, int] = {}
        super().__init__()
        self._load_from_db()

    def _load_from_db(self):
        for row in self._load_all():
            task = Task(**row)
            self._tasks[task.id] = task  # project_id -> index

    def create(self, name: str, type: TaskType, project_id: str, creator_id: str) -> Task:
        task = Task(
            id=f"task-{uuid.uuid4().hex[:8]}",
            name=name,
            type=type,
            project_id=project_id,
            creator_id=creator_id,
            created_at=datetime.now().isoformat(),
        )
        self._tasks[task.id] = task
        self._save(task.id, task.model_dump())
        return task

    def publish(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.PENDING:
            return False
        task.status = TaskStatus.PUBLISHED
        self._save(task.id, task.model_dump())
        return True

    def assign(self, task_id: str, user_id: str, strategy: AssignmentStrategy = AssignmentStrategy.MANUAL) -> bool:
        task = self._tasks.get(task_id)
        # assign只允许PUBLISHED→ASSIGNED
        if not task or task.status != TaskStatus.PUBLISHED:
            return False
        task.assigned_to = user_id
        task.status = TaskStatus.ASSIGNED
        self._user_task_queue.setdefault(user_id, []).append(task_id)
        self._save(task.id, task.model_dump())
        return True

    def auto_assign(self, task_id: str, available_users: List[str], strategy: AssignmentStrategy) -> bool:
        if not available_users:
            return False
        if strategy == AssignmentStrategy.ROUND_ROBIN:
            task = self._tasks.get(task_id)
            if not task:
                return False
            # 按project_id全局轮询
            project_id = task.project_id
            idx = self._round_robin_index.get(project_id, 0) % len(available_users)
            self._round_robin_index[project_id] = idx + 1
            return self.assign(task_id, available_users[idx])
        elif strategy == AssignmentStrategy.LOAD_BALANCE:
            counts = [(u, len(self._user_task_queue.get(u, []))) for u in available_users]
            counts.sort(key=lambda x: x[1])
            return self.assign(task_id, counts[0][0])
        return False

    def submit(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        # submit只允许ASSIGNED→SUBMITTED
        if not task or task.status != TaskStatus.ASSIGNED:
            return False
        task.status = TaskStatus.SUBMITTED
        self._save(task.id, task.model_dump())
        return True

    def review(self, task_id: str, reviewer_id: str, passed: bool, score: float = 0) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.SUBMITTED:
            return False
        task.reviewer_id = reviewer_id
        task.quality_score = score
        if passed:
            task.status = TaskStatus.APPROVED
        else:
            task.status = TaskStatus.REJECTED
        self._save(task.id, task.model_dump())
        return True

    def complete(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.APPROVED:
            return False
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now().isoformat()
        self._save(task.id, task.model_dump())
        return True

    def request_arbitration(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status not in (TaskStatus.REJECTED, TaskStatus.SUBMITTED):
            return False
        task.status = TaskStatus.NEEDS_ARBITRATION
        task.is_arbitration = True
        self._save(task.id, task.model_dump())
        return True

    def arbitrate(self, task_id: str, arbitrator_id: str, decision: TaskStatus) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.NEEDS_ARBITRATION:
            return False
        task.arbitrator_id = arbitrator_id
        if decision == TaskStatus.APPROVED:
            task.status = TaskStatus.APPROVED
        elif decision == TaskStatus.REJECTED:
            task.status = TaskStatus.REJECTED
        else:
            task.status = decision
        self._save(task.id, task.model_dump())
        return True

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list_by_project(self, project_id: str) -> List[Task]:
        return [t for t in self._tasks.values() if t.project_id == project_id]

    def list_by_user(self, user_id: str) -> List[Task]:
        return [t for t in self._tasks.values() if t.assigned_to == user_id]

    def list_by_status(self, status: TaskStatus) -> List[Task]:
        return [t for t in self._tasks.values() if t.status == status]

    def get_stats(self, user_id: str = "") -> Dict[str, Any]:
        tasks = self.list_by_user(user_id) if user_id else list(self._tasks.values())
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        rejected = sum(1 for t in tasks if t.status == TaskStatus.REJECTED)
        # approval_rate: completed / total (排除未完成的不算)
        approval_rate = round(completed / total * 100, 1) if total > 0 else 0
        return {
            "total": total,
            "completed": completed,
            "rejected": rejected,
            "approval_rate": approval_rate,
            "avg_score": round(
                sum(t.quality_score for t in tasks if t.quality_score > 0)
                / max(sum(1 for t in tasks if t.quality_score > 0), 1),
                1,
            ),
        }
