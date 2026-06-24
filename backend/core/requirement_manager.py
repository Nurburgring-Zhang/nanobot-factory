"""需求全生命周期管理 — 提出/评审/拆解/验收/归档"""

import uuid
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel
from core.persistent_base import PersistentManager


class RequirementType(str, Enum):
    DATASET_PRODUCTION = "dataset_production"
    DATA_CLEANING = "data_cleaning"
    ANNOTATION = "annotation"
    QUALITY_EVAL = "quality_evaluation"
    DATA_EXPORT = "data_export"
    DATA_ANALYSIS = "data_analysis"


class Priority(str, Enum):
    P0 = "p0"  # 紧急
    P1 = "p1"  # 高
    P2 = "p2"  # 中
    P3 = "p3"  # 低


class RequirementStatus(str, Enum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class SubTask(BaseModel):
    id: str
    name: str
    assigned_role: str  # 采集员/清洗员/AI/审核员/QA/管理员
    estimated_hours: float = 0
    status: str = "pending"
    dependencies: List[str] = []


class Requirement(BaseModel):
    id: str
    name: str
    type: RequirementType
    priority: Priority = Priority.P2
    description: str
    proposer_id: str
    project_id: str
    target_spec: Dict[str, Any] = {}
    status: RequirementStatus = RequirementStatus.DRAFT
    subtasks: List[SubTask] = []
    acceptance_criteria: List[str] = []
    created_at: str = ""
    updated_at: str = ""
    completed_at: str = ""


# 合法状态转换表
_VALID_TRANSITIONS = {
    RequirementStatus.DRAFT: {RequirementStatus.REVIEWING},
    RequirementStatus.REVIEWING: {RequirementStatus.APPROVED, RequirementStatus.REJECTED},
    RequirementStatus.APPROVED: {RequirementStatus.IN_PROGRESS},
    RequirementStatus.IN_PROGRESS: {RequirementStatus.COMPLETED},
    RequirementStatus.COMPLETED: {RequirementStatus.ARCHIVED},
    RequirementStatus.REJECTED: {RequirementStatus.DRAFT},
}


class RequirementManager(PersistentManager):
    _db_table = "requirements"
    _db_fields = ["id","name","type","priority","description","proposer_id","project_id","target_spec","status","subtasks","acceptance_criteria","created_at","updated_at","completed_at"]

    def __init__(self):
        self._requirements: Dict[str, Requirement] = {}
        self._lock = threading.Lock()
        super().__init__()
        self._load_from_db()

    def _load_from_db(self):
        for row in self._load_all():
            req = Requirement(**row)
            self._requirements[req.id] = req

    def create(
        self,
        name: str,
        type: RequirementType,
        priority: Priority,
        description: str,
        proposer_id: str,
        project_id: str,
    ) -> Requirement:
        with self._lock:
            req = Requirement(
                id=f"req-{uuid.uuid4().hex[:8]}",
                name=name,
                type=type,
                priority=priority,
                description=description,
                proposer_id=proposer_id,
                project_id=project_id,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )
            self._requirements[req.id] = req
            self._save(req.id, req.model_dump())
            return req

    def get(self, id: str) -> Optional[Requirement]:
        return self._requirements.get(id)

    def list(
        self,
        project_id: str = "",
        status: Optional[RequirementStatus] = None,
    ) -> List[Requirement]:
        results = list(self._requirements.values())
        if project_id:
            results = [r for r in results if r.project_id == project_id]
        if status:
            results = [r for r in results if r.status == status]
        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def update_status(self, id: str, status: RequirementStatus) -> bool:
        req = self._requirements.get(id)
        if not req:
            return False
        # 验证状态转换合法性
        allowed = _VALID_TRANSITIONS.get(req.status, set())
        if status not in allowed:
            return False
        req.status = status
        req.updated_at = datetime.now().isoformat()
        if status == RequirementStatus.COMPLETED:
            req.completed_at = datetime.now().isoformat()
        self._save(req.id, req.model_dump())
        return True

    def add_subtask(
        self, req_id: str, name: str, role: str, hours: float = 0
    ) -> Optional[SubTask]:
        with self._lock:
            req = self._requirements.get(req_id)
            if not req:
                return None
            st = SubTask(
                id=f"st-{uuid.uuid4().hex[:6]}",
                name=name,
                assigned_role=role,
                estimated_hours=hours,
            )
            req.subtasks.append(st)
            req.updated_at = datetime.now().isoformat()
            self._save(req.id, req.model_dump())
            return st

    def auto_decompose(self, req_id: str) -> bool:
        """Agent自动拆解需求为子任务"""
        req = self._requirements.get(req_id)
        if not req:
            return False
        # 基于需求类型自动生成子任务
        templates = {
            RequirementType.DATASET_PRODUCTION: [
                ("数据采集（预留冗余）", "采集员", 16),
                ("数据清洗（分辨率/模糊/NSFW过滤）", "清洗员", 8),
                ("AI自动打标（CLIP+BLIP）", "AI", 4),
                ("AI质量评分与筛选", "AI", 2),
                ("人工抽样审核（5%）", "审核员", 8),
                ("数据集构建与导出", "管理员", 4),
            ],
            RequirementType.DATA_CLEANING: [
                ("去重处理（MD5/Phash）", "清洗员", 4),
                ("质量过滤（分辨率/模糊/NSFW）", "AI", 2),
                ("格式归一化", "清洗员", 2),
                ("质量报告生成", "QA", 1),
            ],
            RequirementType.ANNOTATION: [
                ("AI预标注", "AI", 2),
                ("人工标注", "标注员", 16),
                ("审核标注", "审核员", 8),
                ("IAA一致性检查", "QA", 2),
            ],
            RequirementType.QUALITY_EVAL: [
                ("构建评测数据集", "管理员", 4),
                ("运行自动评测", "AI", 4),
                ("人工主观评测", "审核员", 8),
                ("生成评测报告", "QA", 2),
            ],
            RequirementType.DATA_EXPORT: [
                ("格式转换与校验", "清洗员", 4),
                ("数据抽样验证", "QA", 2),
                ("导出压缩与归档", "管理员", 2),
            ],
            RequirementType.DATA_ANALYSIS: [
                ("数据统计与分析", "QA", 4),
                ("可视化报告生成", "管理员", 3),
                ("异常数据检测报告", "AI", 2),
            ],
        }
        for name, role, hours in templates.get(
            req.type, [(req.name, "管理员", 8)]
        ):
            self.add_subtask(req_id, name, role, hours)
        return True
