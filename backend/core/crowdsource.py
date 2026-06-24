"""众包管理——人员/任务/计费/质量审核"""
import uuid, logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)

class CrowdWorkerLevel(str, Enum):
    BEGINNER = "beginner"     # 新手
    JUNIOR = "junior"         # 初级
    INTERMEDIATE = "intermediate"  # 中级
    SENIOR = "senior"         # 高级
    EXPERT = "expert"         # 专家

class TaskType(str, Enum):
    ANNOTATION = "annotation"       # 标注
    REVIEW = "review"               # 审核
    CAPTION = "caption"             # 描述
    QUALITY_CHECK = "quality_check" # 质量检查
    DATA_COLLECTION = "data_collection" # 数据采集

class TaskStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"

class CrowdWorker:
    """众包人员"""
    def __init__(self, username: str, email: str = ""):
        self.worker_id = f"cw_{uuid.uuid4().hex[:12]}"
        self.username = username
        self.email = email
        self.level = CrowdWorkerLevel.BEGINNER
        self.tasks_completed = 0
        self.accuracy = 1.0
        self.earnings = 0.0
        self.skills: List[str] = []
        self.registered_at = datetime.now().isoformat()

class CrowdTask:
    """众包任务"""
    def __init__(self, title: str, task_type: TaskType, budget: float = 0, 
                 description: str = "", data_ref: str = "", 
                 max_assignees: int = 1, quality_threshold: float = 0.8):
        self.task_id = f"ct_{uuid.uuid4().hex[:12]}"
        self.title = title
        self.task_type = task_type
        self.status = TaskStatus.OPEN
        self.budget = budget
        self.description = description
        self.data_ref = data_ref
        self.max_assignees = max_assignees
        self.quality_threshold = quality_threshold
        self.assignees: List[str] = []  # worker_ids
        self.submissions: List[dict] = []
        self.created_at = datetime.now().isoformat()

class CrowdManager:
    _workers: Dict[str, CrowdWorker] = {}
    _tasks: Dict[str, CrowdTask] = {}
    
    @classmethod
    def register_worker(cls, username: str, email: str = "", skills: List[str] = None) -> CrowdWorker:
        worker = CrowdWorker(username, email)
        if skills:
            worker.skills = skills
        cls._workers[worker.worker_id] = worker
        return worker
    
    @classmethod
    def get_worker(cls, worker_id: str) -> Optional[CrowdWorker]:
        return cls._workers.get(worker_id)
    
    @classmethod
    def list_workers(cls, level: Optional[CrowdWorkerLevel] = None) -> List[dict]:
        workers = cls._workers.values()
        if level:
            workers = [w for w in workers if w.level == level]
        return [{"worker_id": w.worker_id, "username": w.username, "level": w.level.value,
                 "tasks_completed": w.tasks_completed, "accuracy": w.accuracy,
                 "earnings": w.earnings, "skills": w.skills} for w in workers]
    
    @classmethod
    def create_task(cls, title: str, task_type: TaskType, budget: float = 0,
                    description: str = "", data_ref: str = "",
                    max_assignees: int = 1, quality_threshold: float = 0.8) -> CrowdTask:
        task = CrowdTask(title, task_type, budget, description, data_ref, max_assignees, quality_threshold)
        cls._tasks[task.task_id] = task
        return task
    
    @classmethod
    def list_tasks(cls, status: Optional[TaskStatus] = None) -> List[dict]:
        tasks = cls._tasks.values()
        if status:
            tasks = [t for t in tasks if t.status == status]
        return [{"task_id": t.task_id, "title": t.title, "task_type": t.task_type.value,
                 "status": t.status.value, "budget": t.budget, "assignees": len(t.assignees),
                 "submissions": len(t.submissions), "created_at": t.created_at} for t in tasks]
    
    @classmethod
    def assign_task(cls, task_id: str, worker_id: str) -> bool:
        task = cls._tasks.get(task_id)
        worker = cls._workers.get(worker_id)
        if not task or not worker:
            return False
        if task.status != TaskStatus.OPEN:
            return False
        if len(task.assignees) >= task.max_assignees:
            return False
        task.assignees.append(worker_id)
        task.status = TaskStatus.ASSIGNED
        return True
    
    @classmethod
    def submit_task(cls, task_id: str, worker_id: str, result: dict) -> bool:
        task = cls._tasks.get(task_id)
        if not task or worker_id not in task.assignees:
            return False
        task.submissions.append({"worker_id": worker_id, "result": result, "submitted_at": datetime.now().isoformat()})
        task.status = TaskStatus.SUBMITTED
        return True
    
    @classmethod
    def review_task(cls, task_id: str, passed: bool, score: float = 0, feedback: str = "") -> Optional[dict]:
        task = cls._tasks.get(task_id)
        if not task or task.status != TaskStatus.SUBMITTED:
            return None
        task.status = TaskStatus.APPROVED if passed else TaskStatus.REJECTED
        if passed and task.submissions:
            # 更新人员统计
            last_sub = task.submissions[-1]
            worker = cls._workers.get(last_sub["worker_id"])
            if worker:
                worker.tasks_completed += 1
                worker.earnings += task.budget
                worker.accuracy = (worker.accuracy * (worker.tasks_completed - 1) + score) / worker.tasks_completed
                # 升级逻辑
                if worker.tasks_completed >= 100 and worker.accuracy >= 0.95:
                    worker.level = CrowdWorkerLevel.EXPERT
                elif worker.tasks_completed >= 50 and worker.accuracy >= 0.9:
                    worker.level = CrowdWorkerLevel.SENIOR
                elif worker.tasks_completed >= 20 and worker.accuracy >= 0.85:
                    worker.level = CrowdWorkerLevel.INTERMEDIATE
                elif worker.tasks_completed >= 5:
                    worker.level = CrowdWorkerLevel.JUNIOR
                task.status = TaskStatus.PAID
        return {"task_id": task_id, "status": task.status.value, "score": score, "feedback": feedback}

crowd = CrowdManager()
