"""智影 V5 — Matter (从聊天→事项,可追踪/可复盘/可验收)"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MatterStatus(str, Enum):
    """Matter 状态"""
    DRAFT = "draft"            # 草稿
    PROPOSED = "proposed"      # 待确认
    ACCEPTED = "accepted"      # 已接受,准备执行
    IN_PROGRESS = "in_progress"  # 执行中
    BLOCKED = "blocked"        # 阻塞
    REVIEW = "review"          # 验收中
    DONE = "done"              # 完成
    REJECTED = "rejected"      # 拒绝
    CANCELLED = "cancelled"    # 取消


@dataclass
class AcceptanceCriteria:
    """验收标准"""
    criterion_id: str = field(default_factory=lambda: f"ac-{uuid.uuid4().hex[:8]}")
    description: str = ""
    metric: str = ""  # 度量 (e.g., "测试通过率 >= 95%")
    threshold: str = ""
    required: bool = True
    met: bool = False
    verifier_id: str = ""
    verified_at: float = 0.0
    notes: str = ""


@dataclass
class DeliveryRecord:
    """交付记录"""
    delivery_id: str = field(default_factory=lambda: f"del-{uuid.uuid4().hex[:8]}")
    deliverer_id: str = ""  # 谁交付
    deliverable: str = ""  # 交付物描述
    artifact_refs: List[str] = field(default_factory=list)  # 引用文件/URL
    delivered_at: float = 0.0
    accepted_at: float = 0.0
    feedback: str = ""
    rating: int = 0  # 1-5
    iteration: int = 1  # 第几轮迭代


@dataclass
class Matter:
    """Matter — 从聊天变行动,从行动变交付

    Matter 的核心思路:当讨论中出现需要跟进的工作,Agent 自动总结要点,由人确认后创建成事项。
    这个事项里有负责人、有交付物、有验收标准,也有从 Brief、过程讨论、产出、反馈到验收结论的完整记录。
    """

    title: str
    matter_id: str = field(default_factory=lambda: f"mtt-{uuid.uuid4().hex[:12]}")
    description: str = ""
    status: MatterStatus = MatterStatus.DRAFT

    # 关联
    channel_id: str = ""
    thread_id: str = ""  # 来源 Thread
    parent_matter_id: str = ""  # 子 Matter

    # 责任人
    owner_id: str = ""  # 负责人
    contributor_ids: List[str] = field(default_factory=list)  # 协作者
    reviewer_id: str = ""  # 审核人

    # 交付
    deliverable: str = ""  # 最终交付物描述
    deliverables: List[Dict[str, Any]] = field(default_factory=list)  # 实际产物
    delivery_records: List[DeliveryRecord] = field(default_factory=list)

    # 验收
    acceptance_criteria: List[AcceptanceCriteria] = field(default_factory=list)

    # 时间
    due_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0

    # 反馈闭环
    taste_signals: List[Dict[str, Any]] = field(default_factory=list)
    # 每个信号: {"source": "user", "type": "approve|reject|edit", "target": "deliverable", "delta": {...}, "at": ts}

    # 优先级/标签
    priority: str = "medium"  # low/medium/high/urgent
    tags: List[str] = field(default_factory=list)
    category: str = ""

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 时间戳
    created_at: float = 0.0
    updated_at: float = 0.0

    def accept(self, by_user_id: str = ""):
        """人确认接受"""
        if self.status in (MatterStatus.DRAFT, MatterStatus.PROPOSED):
            self.status = MatterStatus.ACCEPTED
            self.started_at = time.time()
            self.updated_at = time.time()
            logger.info(f"Matter[{self.title}] accepted by {by_user_id}")

    def start(self, by_user_id: str = ""):
        """开始执行"""
        if self.status == MatterStatus.ACCEPTED:
            self.status = MatterStatus.IN_PROGRESS
            self.started_at = time.time()
            self.updated_at = time.time()

    def block(self, reason: str = ""):
        """阻塞"""
        self.status = MatterStatus.BLOCKED
        if reason:
            self.metadata["block_reason"] = reason
        self.updated_at = time.time()

    def submit_for_review(self):
        """提交验收"""
        if self.status == MatterStatus.IN_PROGRESS:
            self.status = MatterStatus.REVIEW
            self.updated_at = time.time()

    def complete(self, record: Optional[DeliveryRecord] = None):
        """完成"""
        if record:
            self.delivery_records.append(record)
        self.status = MatterStatus.DONE
        self.completed_at = time.time()
        self.updated_at = time.time()

    def reject(self, reason: str = ""):
        """拒绝"""
        self.status = MatterStatus.REJECTED
        if reason:
            self.metadata["reject_reason"] = reason
        self.updated_at = time.time()

    def add_taste_signal(
        self,
        source: str,
        signal_type: str,
        target: str = "",
        delta: Optional[Dict[str, Any]] = None,
    ):
        """记录偏好信号 (用于 Taste 学习)"""
        self.taste_signals.append(
            {
                "source": source,
                "type": signal_type,  # approve/reject/edit/select/prefer
                "target": target,
                "delta": delta or {},
                "at": time.time(),
            }
        )
        self.updated_at = time.time()

    def add_acceptance_criterion(
        self,
        description: str,
        metric: str = "",
        threshold: str = "",
        required: bool = True,
    ) -> AcceptanceCriteria:
        ac = AcceptanceCriteria(
            description=description,
            metric=metric,
            threshold=threshold,
            required=required,
        )
        self.acceptance_criteria.append(ac)
        return ac

    def check_acceptance(self) -> Dict[str, Any]:
        """检查验收"""
        if not self.acceptance_criteria:
            return {"all_met": True, "required_met": True, "optional_count": 0, "required_count": 0, "met_count": 0, "details": []}
        required = [ac for ac in self.acceptance_criteria if ac.required]
        optional = [ac for ac in self.acceptance_criteria if not ac.required]
        met_required = sum(1 for ac in required if ac.met)
        met_optional = sum(1 for ac in optional if ac.met)
        all_required_met = met_required == len(required)
        return {
            "all_met": all_required_met and met_optional == len(optional),
            "required_met": all_required_met,
            "required_count": len(required),
            "required_met_count": met_required,
            "optional_count": len(optional),
            "optional_met_count": met_optional,
            "met_count": met_required + met_optional,
            "details": [
                {
                    "criterion_id": ac.criterion_id,
                    "description": ac.description,
                    "required": ac.required,
                    "met": ac.met,
                    "metric": ac.metric,
                    "threshold": ac.threshold,
                }
                for ac in self.acceptance_criteria
            ],
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matter_id": self.matter_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "channel_id": self.channel_id,
            "thread_id": self.thread_id,
            "parent_matter_id": self.parent_matter_id,
            "owner_id": self.owner_id,
            "contributor_ids": self.contributor_ids,
            "reviewer_id": self.reviewer_id,
            "deliverable": self.deliverable,
            "deliverables": self.deliverables,
            "delivery_count": len(self.delivery_records),
            "acceptance": self.check_acceptance(),
            "due_at": self.due_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "taste_signal_count": len(self.taste_signals),
            "priority": self.priority,
            "tags": self.tags,
            "category": self.category,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
