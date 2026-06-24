"""
Requirement Engine — 需求管理+任务分配 (智影设计文档 §7)
=========================================================
需求全生命周期: draft → open → in_progress → review → done → closed
自动分配策略: by_skill / by_workload / random
"""
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json, os, logging, uuid, random

logger = logging.getLogger(__name__)


class RequirementStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    CLOSED = "closed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class Priority(str, Enum):
    P0 = "P0"  # 紧急
    P1 = "P1"  # 高
    P2 = "P2"  # 中
    P3 = "P3"  # 低


class RequirementType(str, Enum):
    DATA_COLLECTION = "data_collection"      # 数据采集
    DATA_ANNOTATION = "data_annotation"       # 数据标注
    DATA_CLEANING = "data_cleaning"           # 数据清洗
    MODEL_EVALUATION = "model_evaluation"     # 模型评测
    DATA_AUGMENTATION = "data_augmentation"   # 数据增强
    QUALITY_REVIEW = "quality_review"          # 质量审查


@dataclass
class Requirement:
    """需求"""
    id: str = ""
    title: str = ""
    type: RequirementType = RequirementType.DATA_ANNOTATION
    status: RequirementStatus = RequirementStatus.DRAFT
    priority: Priority = Priority.P2
    created_by: str = ""
    description: str = ""
    acceptance_criteria: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    closed_at: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "title": self.title,
            "type": self.type.value, "status": self.status.value,
            "priority": self.priority.value,
            "created_by": self.created_by,
            "description": self.description,
            "acceptance_criteria": self.acceptance_criteria,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "closed_at": self.closed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Requirement":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            type=RequirementType(data.get("type", "data_annotation")),
            status=RequirementStatus(data.get("status", "draft")),
            priority=Priority(data.get("priority", "P2")),
            created_by=data.get("created_by", ""),
            description=data.get("description", ""),
            acceptance_criteria=data.get("acceptance_criteria", ""),
            tags=data.get("tags", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            closed_at=data.get("closed_at", ""),
        )


@dataclass
class Task:
    """任务 — 需求的分解单元"""
    id: str = ""
    requirement_id: str = ""
    title: str = ""
    assignee: str = ""           # user_id
    status: TaskStatus = TaskStatus.PENDING
    acceptance_criteria: str = ""
    estimated_hours: float = 0.0
    actual_hours: float = 0.0
    priority: Priority = Priority.P2
    created_at: str = ""
    completed_at: str = ""
    notes: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "requirement_id": self.requirement_id,
            "title": self.title, "assignee": self.assignee,
            "status": self.status.value,
            "acceptance_criteria": self.acceptance_criteria,
            "estimated_hours": self.estimated_hours,
            "actual_hours": self.actual_hours,
            "priority": self.priority.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Task":
        return cls(
            id=data.get("id", ""),
            requirement_id=data.get("requirement_id", ""),
            title=data.get("title", ""),
            assignee=data.get("assignee", ""),
            status=TaskStatus(data.get("status", "pending")),
            acceptance_criteria=data.get("acceptance_criteria", ""),
            estimated_hours=data.get("estimated_hours", 0.0),
            actual_hours=data.get("actual_hours", 0.0),
            priority=Priority(data.get("priority", "P2")),
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at", ""),
            notes=data.get("notes", ""),
        )


@dataclass
class UserSkill:
    """用户技能信息 — 供自动分配使用"""
    user_id: str = ""
    skills: List[str] = field(default_factory=list)    # ["text_annotation", "image_labeling", ...]
    workload: float = 0.0  # 当前任务数
    efficiency: float = 1.0  # 效率系数 (1.0=基准)


class AllocationStrategy:
    """自动分配策略 — 支持多种策略"""

    @staticmethod
    def by_skill(
        task_requirements: List[str],
        candidates: List[UserSkill],
    ) -> List[Tuple[str, float]]:
        """
        根据技能匹配度分配
        返回: [(user_id, match_score)], 按匹配度降序
        """
        scored = []
        for user in candidates:
            if not user.skills:
                scored.append((user.user_id, 0.0))
                continue
            # 计算技能匹配度 (交集/并集)
            req_set = set(task_requirements)
            user_set = set(user.skills)
            if not req_set:
                match = 1.0
            else:
                intersection = req_set & user_set
                match = len(intersection) / max(len(req_set), 1)
            scored.append((user.user_id, match))

        scored.sort(key=lambda x: (-x[1], -candidates[0].efficiency
                                    if candidates else 0))
        return scored

    @staticmethod
    def by_workload(
        candidates: List[UserSkill],
        ascending: bool = True,
    ) -> List[Tuple[str, float]]:
        """
        根据工作负载分配 (默认负载最低优先)
        返回: [(user_id, workload)]
        """
        scored = [(u.user_id, u.workload) for u in candidates]
        scored.sort(key=lambda x: x[1], reverse=not ascending)
        return scored

    @staticmethod
    def random(candidates: List[UserSkill]) -> List[Tuple[str, float]]:
        """
        随机分配
        返回: [(user_id, random_score)]
        """
        scored = [(u.user_id, random.random()) for u in candidates]
        scored.sort(key=lambda x: -x[1])
        return scored

    @staticmethod
    def hybrid(
        task_requirements: List[str],
        candidates: List[UserSkill],
        skill_weight: float = 0.7,
        workload_weight: float = 0.3,
    ) -> List[Tuple[str, float]]:
        """混合策略: 技能匹配 * skill_weight + 负载 * workload_weight"""
        skill_scores = dict(AllocationStrategy.by_skill(task_requirements, candidates))
        workload_scores = dict(AllocationStrategy.by_workload(candidates))

        # 归一化负载分数: 低负载得高分
        workloads = [u.workload for u in candidates]
        max_wl = max(workloads) if workloads else 1
        norm_workload = {
            u.user_id: 1.0 - (u.workload / max(max_wl, 1))
            for u in candidates
        }

        combined = []
        for user in candidates:
            s_score = skill_scores.get(user.user_id, 0.0)
            w_score = norm_workload.get(user.user_id, 0.5)
            total = s_score * skill_weight + w_score * workload_weight
            combined.append((user.user_id, total))

        combined.sort(key=lambda x: -x[1])
        return combined


class RequirementEngine:
    """需求引擎 — 全生命周期管理"""

    def __init__(self):
        self.requirements: Dict[str, Requirement] = {}
        self.tasks: Dict[str, Task] = {}
        self.users: Dict[str, UserSkill] = {}  # 用于分配
        self.strategy = AllocationStrategy()

    # ──────────── 需求创建 ────────────

    def create_requirement(
        self,
        title: str,
        req_type: RequirementType = RequirementType.DATA_ANNOTATION,
        priority: Priority = Priority.P2,
        created_by: str = "",
        description: str = "",
        acceptance_criteria: str = "",
        tags: Optional[List[str]] = None,
    ) -> Requirement:
        """创建新需求，初始状态为draft"""
        req_id = f"req_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        req = Requirement(
            id=req_id,
            title=title,
            type=req_type,
            status=RequirementStatus.DRAFT,
            priority=priority,
            created_by=created_by,
            description=description,
            acceptance_criteria=acceptance_criteria,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self.requirements[req_id] = req
        logger.info(f"Created requirement: {req.title} ({req_id}) [{req.priority.value}]")
        return req

    def get_requirement(self, req_id: str) -> Optional[Requirement]:
        return self.requirements.get(req_id)

    def list_requirements(
        self,
        status: Optional[RequirementStatus] = None,
        priority: Optional[Priority] = None,
        req_type: Optional[RequirementType] = None,
    ) -> List[Requirement]:
        """按条件筛选需求列表"""
        results = list(self.requirements.values())
        if status:
            results = [r for r in results if r.status == status]
        if priority:
            results = [r for r in results if r.priority == priority]
        if req_type:
            results = [r for r in results if r.type == req_type]
        return results

    def update_requirement_status(self, req_id: str, new_status: RequirementStatus) -> bool:
        """更新需求状态（生命周期流转）"""
        req = self.requirements.get(req_id)
        if not req:
            return False
        # 检查状态流转合法性
        valid_transitions = {
            RequirementStatus.DRAFT: [RequirementStatus.OPEN],
            RequirementStatus.OPEN: [RequirementStatus.IN_PROGRESS, RequirementStatus.CLOSED],
            RequirementStatus.IN_PROGRESS: [RequirementStatus.REVIEW, RequirementStatus.CLOSED],
            RequirementStatus.REVIEW: [RequirementStatus.DONE, RequirementStatus.IN_PROGRESS,
                                        RequirementStatus.CLOSED],
            RequirementStatus.DONE: [RequirementStatus.CLOSED],
            RequirementStatus.CLOSED: [],
        }
        allowed = valid_transitions.get(req.status, [])
        if new_status not in allowed:
            logger.warning(
                f"Invalid status transition: {req.status.value} -> {new_status.value}"
            )
            return False

        req.status = new_status
        req.updated_at = datetime.now().isoformat()
        if new_status == RequirementStatus.CLOSED:
            req.closed_at = datetime.now().isoformat()
        return True

    # ──────────── 需求分析 ────────────

    def analyze_requirement(self, req_id: str) -> Dict[str, Any]:
        """
        分析需求：复杂度评估、资源估算、风险识别
        返回分析报告字典
        """
        req = self.requirements.get(req_id)
        if not req:
            return {"error": f"Requirement {req_id} not found"}

        # 复杂度评估（基于描述长度和标签数量）
        desc_length = len(req.description) if req.description else 0
        num_tags = len(req.tags)
        complexity = "low"
        if desc_length > 500 or num_tags > 5:
            complexity = "high"
        elif desc_length > 200 or num_tags > 2:
            complexity = "medium"

        # 资源估算
        type_base_hours = {
            RequirementType.DATA_COLLECTION: 40,
            RequirementType.DATA_ANNOTATION: 80,
            RequirementType.DATA_CLEANING: 20,
            RequirementType.MODEL_EVALUATION: 30,
            RequirementType.DATA_AUGMENTATION: 25,
            RequirementType.QUALITY_REVIEW: 15,
        }
        base_hours = type_base_hours.get(req.type, 20)
        complexity_multiplier = {"low": 1.0, "medium": 1.5, "high": 2.5}
        estimated_hours = base_hours * complexity_multiplier.get(complexity, 1.0)

        # 风险识别
        risks = []
        if req.priority == Priority.P0:
            risks.append("紧急优先级，时间窗口紧张")
        if not req.description:
            risks.append("需求描述为空，信息不完整")
        if not req.acceptance_criteria:
            risks.append("缺少验收标准，无法验证完成质量")
        if complexity == "high":
            risks.append("复杂度高，建议拆分")

        # 现有任务统计
        related_tasks = [t for t in self.tasks.values() if t.requirement_id == req_id]
        completed_tasks = [t for t in related_tasks if t.status == TaskStatus.APPROVED]

        return {
            "requirement_id": req_id,
            "title": req.title,
            "type": req.type.value,
            "priority": req.priority.value,
            "complexity": complexity,
            "estimated_hours": round(estimated_hours, 1),
            "total_tasks": len(related_tasks),
            "completed_tasks": len(completed_tasks),
            "completion_rate": round(len(completed_tasks) / max(len(related_tasks), 1) * 100, 1),
            "risks": risks,
            "description_length": desc_length,
            "tags": req.tags,
            "status": req.status.value,
        }

    # ──────────── 需求分解 ────────────

    def decompose_to_tasks(self, req_id: str) -> List[Task]:
        """
        将需求自动分解为可执行的子任务
        根据需求类型和复杂度决定分解粒度
        返回创建的Task列表
        """
        req = self.requirements.get(req_id)
        if not req:
            logger.error(f"Cannot decompose: requirement {req_id} not found")
            return []

        if req.status != RequirementStatus.OPEN:
            logger.warning(f"Cannot decompose: requirement {req_id} status is {req.status.value}, "
                         f"must be OPEN first")
            return []

        analysis = self.analyze_requirement(req_id)
        complexity = analysis.get("complexity", "low")

        # 根据类型和复杂度决定分解策略
        task_definitions = self._get_task_definitions(req.type, complexity, req)

        created_tasks = []
        for tdef in task_definitions:
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            task = Task(
                id=task_id,
                requirement_id=req_id,
                title=tdef["title"],
                status=TaskStatus.PENDING,
                acceptance_criteria=tdef.get("criteria", req.acceptance_criteria),
                estimated_hours=tdef.get("hours", 0),
                priority=req.priority,
                created_at=datetime.now().isoformat(),
            )
            self.tasks[task_id] = task
            created_tasks.append(task)

        # 更新需求状态
        req.status = RequirementStatus.IN_PROGRESS
        req.updated_at = datetime.now().isoformat()

        logger.info(f"Decomposed requirement {req_id} into {len(created_tasks)} tasks")
        return created_tasks

    def _get_task_definitions(
        self, req_type: RequirementType, complexity: str, req: Requirement
    ) -> List[Dict]:
        """根据需求类型和复杂度生成任务定义列表"""
        base_tasks = []

        if req_type == RequirementType.DATA_ANNOTATION:
            base_tasks = [
                {"title": "标注规范培训与对齐", "hours": 2},
                {"title": f"数据集{req.title}初步标注", "hours": 40 if complexity in ("high",) else 20},
                {"title": "标注质量自检", "hours": 4},
                {"title": "标注成果提交", "hours": 2},
            ]
        elif req_type == RequirementType.DATA_COLLECTION:
            base_tasks = [
                {"title": "采集方案设计", "hours": 4},
                {"title": f"数据采集: {req.title}", "hours": 30 if complexity in ("high",) else 15},
                {"title": "数据去重与清洗", "hours": 6},
                {"title": "采集报告编写", "hours": 2},
            ]
        elif req_type == RequirementType.DATA_CLEANING:
            base_tasks = [
                {"title": "数据质量评估", "hours": 3},
                {"title": "异常数据识别与标注", "hours": 8},
                {"title": f"数据清洗: {req.title}", "hours": 10 if complexity in ("high",) else 5},
                {"title": "清洗后验证", "hours": 3},
            ]
        elif req_type == RequirementType.MODEL_EVALUATION:
            base_tasks = [
                {"title": "评测数据集准备", "hours": 4},
                {"title": f"模型推理: {req.title}", "hours": 8},
                {"title": "评测指标计算", "hours": 3},
                {"title": "评测报告生成", "hours": 4},
            ]
        elif req_type == RequirementType.DATA_AUGMENTATION:
            base_tasks = [
                {"title": "数据增强方案设计", "hours": 3},
                {"title": f"数据增强执行: {req.title}", "hours": 15 if complexity in ("high",) else 8},
                {"title": "增强效果验证", "hours": 5},
            ]
        elif req_type == RequirementType.QUALITY_REVIEW:
            base_tasks = [
                {"title": f"{req.title} 抽样审查", "hours": 8},
                {"title": "问题汇总与分类", "hours": 3},
                {"title": "审核报告撰写", "hours": 3},
            ]
        else:
            base_tasks = [
                {"title": f"执行: {req.title}", "hours": 8},
            ]

        # 添加验收标准
        for t in base_tasks:
            t["criteria"] = req.acceptance_criteria or f"{t['title']} 完成并确认"

        return base_tasks

    # ──────────── 自动分配 ────────────

    def register_user(self, user_id: str, skills: List[str],
                      workload: float = 0.0, efficiency: float = 1.0) -> None:
        """注册用户信息供分配使用"""
        self.users[user_id] = UserSkill(
            user_id=user_id,
            skills=skills,
            workload=workload,
            efficiency=efficiency,
        )

    def auto_assign(
        self,
        task_id: str,
        strategy: str = "hybrid",
        skill_requirements: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        自动分配任务给最合适的人
        strategy: "by_skill" / "by_workload" / "random" / "hybrid"
        返回分配的user_id，如果无可用用户则返回None
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return None

        if not self.users:
            logger.warning("No users registered for assignment")
            return None

        candidates = list(self.users.values())
        req_skills = skill_requirements or []

        # 选择分配策略
        if strategy == "by_skill":
            ranked = self.strategy.by_skill(req_skills, candidates)
        elif strategy == "by_workload":
            ranked = self.strategy.by_workload(candidates, ascending=True)
        elif strategy == "random":
            ranked = self.strategy.random(candidates)
        else:  # hybrid
            ranked = self.strategy.hybrid(req_skills, candidates)

        if not ranked:
            return None

        assignee_id = ranked[0][0]
        task.assignee = assignee_id
        task.status = TaskStatus.ASSIGNED

        # 更新用户负载
        if assignee_id in self.users:
            self.users[assignee_id].workload += 1.0

        logger.info(f"Assigned task {task_id} to user {assignee_id} "
                    f"(strategy={strategy}, score={ranked[0][1]:.3f})")
        return assignee_id

    # ──────────── 任务管理 ────────────

    def get_tasks(
        self,
        requirement_id: Optional[str] = None,
        assignee: Optional[str] = None,
        status: Optional[TaskStatus] = None,
    ) -> List[Task]:
        """按条件查询任务列表"""
        results = list(self.tasks.values())
        if requirement_id:
            results = [t for t in results if t.requirement_id == requirement_id]
        if assignee:
            results = [t for t in results if t.assignee == assignee]
        if status:
            results = [t for t in results if t.status == status]
        return results

    def update_task_status(self, task_id: str, new_status: TaskStatus,
                           notes: str = "") -> bool:
        task = self.tasks.get(task_id)
        if not task:
            return False
        task.status = new_status
        if notes:
            task.notes = notes
        if new_status == TaskStatus.APPROVED:
            task.completed_at = datetime.now().isoformat()
        return True

    # ──────────── 验收完成 ────────────

    def verify_completion(self, req_id: str) -> Dict[str, Any]:
        """
        验证需求的所有任务是否完成并通过验收
        如果全部完成则自动关闭需求
        返回验证报告
        """
        req = self.requirements.get(req_id)
        if not req:
            return {"error": f"Requirement {req_id} not found"}

        related_tasks = [t for t in self.tasks.values() if t.requirement_id == req_id]
        total = len(related_tasks)
        approved = [t for t in related_tasks if t.status == TaskStatus.APPROVED]
        rejected = [t for t in related_tasks if t.status == TaskStatus.REJECTED]
        pending = [t for t in related_tasks if t.status not in
                   (TaskStatus.APPROVED, TaskStatus.REJECTED)]

        all_done = total > 0 and len(pending) == 0
        passed = all_done and len(rejected) == 0

        # 自动关闭需求
        if passed:
            req.status = RequirementStatus.CLOSED
            req.closed_at = datetime.now().isoformat()
            req.updated_at = datetime.now().isoformat()
            logger.info(f"Requirement {req_id} auto-closed: all {total} tasks approved")
        elif all_done and len(rejected) > 0:
            req.status = RequirementStatus.REVIEW
            req.updated_at = datetime.now().isoformat()
            logger.info(f"Requirement {req_id} needs rework: {len(rejected)} tasks rejected")

        return {
            "requirement_id": req_id,
            "title": req.title,
            "total_tasks": total,
            "approved": len(approved),
            "rejected": len(rejected),
            "pending": len(pending),
            "progress": round(len(approved) / max(total, 1) * 100, 1),
            "passed": passed,
            "auto_closed": passed,
            "current_status": req.status.value,
        }

    def close_requirement(self, req_id: str) -> bool:
        """
        强制关闭需求 (无论如何)
        要求所有任务已处理
        """
        req = self.requirements.get(req_id)
        if not req:
            return False

        # 标记所有未完成任务为blocked
        for task in self.tasks.values():
            if task.requirement_id == req_id and task.status in (
                TaskStatus.PENDING, TaskStatus.ASSIGNED,
                TaskStatus.IN_PROGRESS, TaskStatus.SUBMITTED,
            ):
                task.status = TaskStatus.BLOCKED

        req.status = RequirementStatus.CLOSED
        req.closed_at = datetime.now().isoformat()
        req.updated_at = datetime.now().isoformat()
        return True

    # ──────────── 序列化 ────────────

    def to_dict(self) -> Dict:
        return {
            "requirements": {k: v.to_dict() for k, v in self.requirements.items()},
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "RequirementEngine":
        eng = cls()
        eng.requirements = {
            k: Requirement.from_dict(v)
            for k, v in data.get("requirements", {}).items()
        }
        eng.tasks = {
            k: Task.from_dict(v)
            for k, v in data.get("tasks", {}).items()
        }
        return eng
