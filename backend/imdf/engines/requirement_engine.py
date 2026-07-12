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
    # P5-R1-T2 新增字段: 与 ProjectCenter / Pack / QC / Delivery 关联
    project_id: Optional[str] = None     # 关联 projects.id (T1 ProjectCenter)
    pack_id: Optional[str] = None        # 关联 packs.id (成果包)
    qc_status: Optional[str] = None      # not_started / in_progress / passed / failed
    delivery_id: Optional[str] = None    # 关联 deliveries.id
    due_date: str = ""                    # ISO 格式截止日期
    owner: str = ""                       # 责任人 user_id

    def to_dict(self) -> Dict:
        # 容错: type/status/priority 可能是 enum 或 str
        def _val(v):
            return v.value if hasattr(v, "value") else v

        return {
            "id": self.id, "title": self.title,
            "type": _val(self.type), "status": _val(self.status),
            "priority": _val(self.priority),
            "created_by": self.created_by,
            "description": self.description,
            "acceptance_criteria": self.acceptance_criteria,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "closed_at": self.closed_at,
            "project_id": self.project_id,
            "pack_id": self.pack_id,
            "qc_status": self.qc_status,
            "delivery_id": self.delivery_id,
            "due_date": self.due_date,
            "owner": self.owner,
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
            project_id=data.get("project_id") or None,
            pack_id=data.get("pack_id") or None,
            qc_status=data.get("qc_status") or None,
            delivery_id=data.get("delivery_id") or None,
            due_date=data.get("due_date", "") or "",
            owner=data.get("owner", "") or "",
        )


# 合法 qc_status 枚举值 — 与前端 UI 保持一致
QC_STATUSES = ("not_started", "in_progress", "passed", "failed")


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
        # Depth-7: write-through store (内存 dict + DB row, 跨进程持久)
        # 默认 lazy import 避免循环; get_requirement_store() 单例复用
        from engines.requirement_store import get_requirement_store
        self.store = get_requirement_store()

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
        project_id: Optional[str] = None,
        pack_id: Optional[str] = None,
        qc_status: Optional[str] = None,
        delivery_id: Optional[str] = None,
        due_date: str = "",
        owner: str = "",
    ) -> Requirement:
        """创建新需求，初始状态为draft"""
        req_id = f"req_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        # 校验 qc_status 合法值
        if qc_status is not None and qc_status not in QC_STATUSES:
            qc_status = None
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
            project_id=project_id,
            pack_id=pack_id,
            qc_status=qc_status,
            delivery_id=delivery_id,
            due_date=due_date,
            owner=owner,
        )
        self.requirements[req_id] = req
        # Depth-7: write-through to DB (内存 dict 已写, 再同步 row)
        try:
            self.store.upsert_requirement(req)
        except Exception as exc:  # pragma: no cover
            logger.debug(f"create_requirement DB write skipped: {exc}")
        logger.info(f"Created requirement: {req.title} ({req_id}) [{req.priority.value}] "
                    f"project={project_id} owner={owner}")
        return req

    def get_requirement(self, req_id: str) -> Optional[Requirement]:
        # Depth-7: 优先 store (跨 instance 一致), fallback 内存 dict
        got = self.store.get_requirement(req_id)
        if got is not None:
            # 同步到本地 dict (缓存, 避免每次跨 lock)
            self.requirements.setdefault(req_id, got)
            return got
        return self.requirements.get(req_id)

    def list_requirements(
        self,
        status: Optional[RequirementStatus] = None,
        priority: Optional[Priority] = None,
        req_type: Optional[RequirementType] = None,
        project_id: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> List[Requirement]:
        """按条件筛选需求列表 (兼容旧调用方 — 返回全量列表, 不分页)"""
        results = list(self.requirements.values())
        if status:
            results = [r for r in results if r.status == status]
        if priority:
            results = [r for r in results if r.priority == priority]
        if req_type:
            results = [r for r in results if r.type == req_type]
        if project_id:
            results = [r for r in results if r.project_id == project_id]
        if owner:
            results = [r for r in results if r.owner == owner]
        return results

    def paginate_requirements(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        req_type: Optional[str] = None,
        priority: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Requirement], int]:
        """
        P5-R1-T2 新增 — 分页查询需求列表.
        接收字符串形式的状态/类型/优先级 (与 Pydantic 路由 schema 对齐),
        内部归一化为枚举再过滤. 返回 (items, total).
        """
        # 归一化枚举
        status_enum = None
        if status:
            try:
                status_enum = RequirementStatus(status)
            except ValueError:
                status_enum = None
        type_enum = None
        if req_type:
            try:
                type_enum = RequirementType(req_type)
            except ValueError:
                type_enum = None
        priority_enum = None
        if priority:
            try:
                priority_enum = Priority(priority)
            except ValueError:
                priority_enum = None

        results = list(self.requirements.values())
        if status_enum:
            results = [r for r in results if r.status == status_enum]
        if type_enum:
            results = [r for r in results if r.type == type_enum]
        if priority_enum:
            results = [r for r in results if r.priority == priority_enum]
        if project_id:
            results = [r for r in results if r.project_id == project_id]
        if keyword:
            kw = keyword.lower()
            results = [
                r for r in results
                if kw in r.title.lower()
                or kw in (r.description or "").lower()
                or kw in (r.owner or "").lower()
            ]
        # 稳定排序: 按 created_at 倒序 (新 → 旧), 无 created_at 时按 id
        results.sort(
            key=lambda r: (r.created_at or "", r.id or ""),
            reverse=True,
        )
        total = len(results)
        # 分页
        page = max(1, int(page))
        page_size = max(1, min(200, int(page_size)))
        start = (page - 1) * page_size
        end = start + page_size
        return results[start:end], total

    def get_requirement_with_stats(self, requirement_id: str) -> Dict[str, Any]:
        """
        P5-R1-T2 新增 — 返回需求详情 + 关联统计 (含 tasks_count / packs_count / progress%)
        找不到时返回 {"error": ...}
        """
        req = self.requirements.get(requirement_id)
        if not req:
            return {"error": f"Requirement {requirement_id} not found"}

        related_tasks = [t for t in self.tasks.values() if t.requirement_id == requirement_id]
        total_tasks = len(related_tasks)
        approved = [t for t in related_tasks if t.status == TaskStatus.APPROVED]
        rejected = [t for t in related_tasks if t.status == TaskStatus.REJECTED]
        in_progress = [t for t in related_tasks if t.status == TaskStatus.IN_PROGRESS]
        pending = [
            t for t in related_tasks
            if t.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED)
        ]
        submitted = [t for t in related_tasks if t.status == TaskStatus.SUBMITTED]
        blocked = [t for t in related_tasks if t.status == TaskStatus.BLOCKED]

        # packs_count = 与该需求关联的成果包数 (目前 1 个 — 由 pack_id 字段记录)
        packs_count = 1 if req.pack_id else 0
        # 进度 = 已 approved / total, 无任务时为 0
        progress = round(
            len(approved) / total_tasks * 100, 1
        ) if total_tasks > 0 else 0.0

        # 状态机映射 — 前端用 5 步进度条
        status_flow = [
            "draft", "open", "in_progress", "review", "done", "closed",
        ]
        current_step = status_flow.index(req.status.value) \
            if req.status.value in status_flow else 0

        # 按 assignee 聚合 (便于前端任务树展示)
        assignee_breakdown: Dict[str, int] = {}
        for t in related_tasks:
            aid = t.assignee or "unassigned"
            assignee_breakdown[aid] = assignee_breakdown.get(aid, 0) + 1

        # 任务树 — 子任务状态聚合
        task_tree = []
        for t in related_tasks:
            task_tree.append({
                "id": t.id,
                "title": t.title,
                "status": t.status.value,
                "assignee": t.assignee,
                "priority": t.priority.value,
                "estimated_hours": t.estimated_hours,
                "actual_hours": t.actual_hours,
            })

        return {
            "requirement": req.to_dict(),
            "tasks_count": total_tasks,
            "approved_count": len(approved),
            "rejected_count": len(rejected),
            "in_progress_count": len(in_progress),
            "pending_count": len(pending),
            "submitted_count": len(submitted),
            "blocked_count": len(blocked),
            "packs_count": packs_count,
            "progress": progress,
            "status_flow": status_flow,
            "current_step": current_step,
            "assignee_breakdown": assignee_breakdown,
            "task_tree": task_tree,
            "qc_status": req.qc_status or "not_started",
        }

    def reassign_tasks(
        self,
        requirement_id: str,
        strategy: str = "hybrid",
    ) -> int:
        """
        P5-R1-T2 新增 — 按策略重派需求下的所有任务
        strategy: by_skill / by_workload / random / hybrid
        返回: 实际被重派的任务数 (未分配/已完成的跳过)
        """
        req = self.requirements.get(requirement_id)
        if not req:
            logger.warning(f"reassign_tasks: requirement {requirement_id} not found")
            return 0
        if not self.users:
            logger.warning("reassign_tasks: no users registered")
            return 0

        related_tasks = [
            t for t in self.tasks.values()
            if t.requirement_id == requirement_id
            and t.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED,
                             TaskStatus.IN_PROGRESS, TaskStatus.REJECTED,
                             TaskStatus.BLOCKED)
        ]
        if not related_tasks:
            return 0

        candidates = list(self.users.values())
        # 技能需求从 requirement type 推断
        skill_map = {
            RequirementType.DATA_COLLECTION: ["data_collection"],
            RequirementType.DATA_ANNOTATION: ["text_annotation", "image_labeling"],
            RequirementType.DATA_CLEANING: ["data_cleaning"],
            RequirementType.MODEL_EVALUATION: ["model_eval"],
            RequirementType.DATA_AUGMENTATION: ["data_augmentation"],
            RequirementType.QUALITY_REVIEW: ["quality_review"],
        }
        required_skills = skill_map.get(req.type, [])

        # 选择策略
        if strategy == "by_skill":
            ranked = self.strategy.by_skill(required_skills, candidates)
        elif strategy == "by_workload":
            ranked = self.strategy.by_workload(candidates, ascending=True)
        elif strategy == "random":
            ranked = self.strategy.random(candidates)
        else:  # hybrid (default)
            ranked = self.strategy.hybrid(required_skills, candidates)

        if not ranked:
            return 0

        # 还原旧 assignee 的负载 (用于多任务平均)
        old_assignee_load: Dict[str, int] = {}
        reassigned = 0
        for task in related_tasks:
            old_assignee_load[task.assignee] = \
                old_assignee_load.get(task.assignee, 0) + 1
        # 减负载
        for aid, cnt in old_assignee_load.items():
            if aid and aid in self.users:
                self.users[aid].workload = max(0.0,
                    self.users[aid].workload - cnt)

        # 按排名轮询分配 (避免所有任务都给同一人)
        for i, task in enumerate(related_tasks):
            pick = ranked[i % len(ranked)][0]
            task.assignee = pick
            task.status = TaskStatus.ASSIGNED
            if pick in self.users:
                self.users[pick].workload += 1
            reassigned += 1

        req.updated_at = datetime.now().isoformat()
        logger.info(
            f"Reassigned {reassigned} tasks under requirement {requirement_id} "
            f"strategy={strategy}"
        )
        return reassigned

    def preview_decompose(self, requirement_id: str) -> Dict[str, Any]:
        """
        P5-R1-T2 新增 — 预览拆解 (不真拆)
        返回: { requirement_id, complexity, estimated_hours, tasks: [...] }
        """
        req = self.requirements.get(requirement_id)
        if not req:
            return {"error": f"Requirement {requirement_id} not found"}
        if req.status not in (RequirementStatus.DRAFT,
                              RequirementStatus.OPEN):
            return {
                "error": f"Cannot preview decompose: requirement status is "
                         f"{req.status.value!r}, must be draft or open",
                "requirement_id": requirement_id,
                "current_status": req.status.value,
            }
        analysis = self.analyze_requirement(requirement_id)
        complexity = analysis.get("complexity", "low")
        task_defs = self._get_task_definitions(req.type, complexity, req)
        preview_tasks = [
            {
                "title": td["title"],
                "estimated_hours": td.get("hours", 0),
                "acceptance_criteria": td.get("criteria", ""),
            }
            for td in task_defs
        ]
        return {
            "requirement_id": requirement_id,
            "title": req.title,
            "type": req.type.value,
            "complexity": complexity,
            "estimated_hours": analysis.get("estimated_hours", 0),
            "tasks": preview_tasks,
            "task_count": len(preview_tasks),
        }

    def update_requirement_meta(
        self,
        requirement_id: str,
        project_id: Optional[str] = None,
        pack_id: Optional[str] = None,
        qc_status: Optional[str] = None,
        delivery_id: Optional[str] = None,
        due_date: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> bool:
        """P5-R1-T2 新增 — 更新需求的关联字段 (project_id / pack_id / qc_status / ...)"""
        req = self.requirements.get(requirement_id)
        if not req:
            return False
        if project_id is not None:
            req.project_id = project_id or None
        if pack_id is not None:
            req.pack_id = pack_id or None
        if qc_status is not None:
            if qc_status in QC_STATUSES:
                req.qc_status = qc_status
        if delivery_id is not None:
            req.delivery_id = delivery_id or None
        if due_date is not None:
            req.due_date = due_date
        if owner is not None:
            req.owner = owner
        req.updated_at = datetime.now().isoformat()
        return True

    def update_requirement_status(self, req_id: str, new_status) -> bool:
        """更新需求状态（生命周期流转）

        P5-R2-T5 fix (audit P1-5): 容错处理 — 接受 str 或 RequirementStatus 枚举.
        之前 ``logger.warning(f"{new_status.value}")`` 在传 str 时直接 AttributeError 500.
        现在先做 enum 归一化, 转换非法时优雅返回 False (而不是 500).
        """
        req = self.requirements.get(req_id)
        if not req:
            return False
        # P5-R2-T5: 归一化 string → enum (兼容前端 Pydantic 未强校验场景)
        if isinstance(new_status, str):
            try:
                new_status = RequirementStatus(new_status)
            except ValueError:
                logger.warning(
                    f"Invalid status string: {new_status!r} for req {req_id}"
                )
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

    # ──────────── P5-R2-T2 统计辅助 (供 project_engine.get_project_stats 调用) ────────────
    def count_requirements_by_project(self, project_id: str) -> int:
        """统计某项目下的需求总数 (active + draft + 任何状态, 因为需求"创建了"就算项目一部分).

        与 list_requirements(project_id=...) 保持一致 — 复用同一过滤条件.

        Depth-7: 走 store (内存 dict + DB), 跨进程一致.
        """
        if not project_id:
            return 0
        return self.store.count_requirements_by_project(project_id)

    def count_tasks_by_project(self, project_id: str) -> int:
        """统计某项目下的任务总数 (RequirementEngine 内的 Task).

        修正 (P5-R2-T2 bug fix): ``Task`` dataclass 仅有 ``requirement_id`` 字段,
        没有 ``project_id``. 原实现用 ``getattr(t, "project_id", None)`` 永远
        返回 None, 对所有项目都返回 0. 正确做法是 join via ``Requirement.project_id``:
        先取该项目下所有 requirement_id, 再统计 task.requirement_id 命中数.

        Depth-7: 走 store (内存 dict + DB), 跨进程一致.
        """
        return self.store.count_tasks_by_project(project_id)

    def count_done_tasks_by_project(self, project_id: str) -> int:
        """统计某项目下已完成 (APPROVED) 的任务数, 用于 project_engine 计算 progress.

        Depth-7: 走 store (内存 dict + DB), 跨进程一致.
        """
        return self.store.count_done_tasks_by_project(project_id)

    # ──────────── Depth-7 持久化支持 ────────────
    def rehydrate(self) -> int:
        """启动时调用 — 把 DB 现有 row 拉回内存 dict。

        返回 rehydrate 数量 (reqs + tasks)。失败返回 0。

        Depth-7 修复: rehydrate 不只填 store 内部 dict, 还同步到 engine
        的 ``self.requirements`` / ``self.tasks`` (legacy 业务代码用的是
        这两个 dict, 不是 store 的)。否则 ``rehydrate()`` 之后
        ``eng.list_requirements()`` 仍然是空, 看起来 rehydrate 没生效.
        """
        # 1. store 先拉 (DB → store 内部 dict)
        n = self.store.rehydrate()
        # 2. 同步到 engine 自身的 dict (legacy API 一致)
        for req_id, req in self.store._reqs.items():
            self.requirements.setdefault(req_id, req)
        for task_id, task in self.store._tasks.items():
            self.tasks.setdefault(task_id, task)
        return n

    def upsert_requirement(self, req: Requirement) -> bool:
        """写内存 + DB (write-through)。"""
        return self.store.upsert_requirement(req)

    def upsert_task(self, task: Task) -> bool:
        """写内存 + DB (write-through)。"""
        return self.store.upsert_task(task)


# ──────────── P5-R2-T2 模块级单例 (供 project_engine / dashboard 等跨模块统计使用) ────────────
_REQ_ENGINE_SINGLETON: Optional["RequirementEngine"] = None


def get_requirement_engine() -> "RequirementEngine":
    """获取 (或懒创建) 模块级 RequirementEngine 单例.

    背景: project_engine.get_project_stats 需统计项目下的需求数,
    而 RequirementEngine 内存中的 requirements dict 只在 routes_extended 的
    局部单例中维护. 改为模块级共享单例后, 跨引擎统计才能拿到正确数字.
    """
    global _REQ_ENGINE_SINGLETON
    if _REQ_ENGINE_SINGLETON is None:
        _REQ_ENGINE_SINGLETON = RequirementEngine()
    return _REQ_ENGINE_SINGLETON
