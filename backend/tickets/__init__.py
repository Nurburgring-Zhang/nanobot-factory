"""
P4-10-W2: 工单系统 (Tickets)
- 类型: problem / feature_request / billing / incident
- 优先级: P0 (停机 1h) / P1 (高 4h) / P2 (中 24h) / P3 (低 72h)
- 状态机: new → assigned → in_progress → resolved → closed
- SLA 自动计算达标率
- P0 通知 oncall (webhook 回调, 复用 P2-2 webhook 模式)
"""
import os
import json
import uuid
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 优先级 → SLA 响应时长 (小时)
SLA_HOURS = {
    "P0": 1,    # 停机
    "P1": 4,    # 高
    "P2": 24,   # 中
    "P3": 72,   # 低
}

# 工单类型
TICKET_TYPES = ["problem", "feature_request", "billing", "incident"]
TICKET_TYPE_LABELS = {
    "problem": "问题反馈",
    "feature_request": "功能请求",
    "billing": "账单问题",
    "incident": "紧急事故",
}

# 优先级
PRIORITIES = ["P0", "P1", "P2", "P3"]

# 状态
STATES = ["new", "assigned", "in_progress", "resolved", "closed", "merged"]
STATE_TRANSITIONS = {
    "new": ["assigned", "closed"],
    "assigned": ["in_progress", "closed"],
    "in_progress": ["resolved", "closed"],
    "resolved": ["closed", "in_progress"],  # 允许重开
    "closed": [],
    "merged": [],  # 终态 (合并后)
}

# Oncall webhook (P2-2 integration; W1 不存在时使用 file log stub)
ONCALL_WEBHOOK_URL = os.getenv("ONCALL_WEBHOOK_URL", "")


# ---------------------------------------------------------------------------
# Ticket 模型
# ---------------------------------------------------------------------------
class Ticket:
    def __init__(
        self,
        ticket_type: str,
        priority: str,
        subject: str,
        description: str,
        customer_id: Optional[str] = None,
        reporter: str = "anonymous",
    ):
        if ticket_type not in TICKET_TYPES:
            raise ValueError(f"invalid type: {ticket_type}")
        if priority not in PRIORITIES:
            raise ValueError(f"invalid priority: {priority}")
        self.ticket_id = f"TK-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        self.type = ticket_type
        self.priority = priority
        self.subject = subject
        self.description = description
        self.customer_id = customer_id
        self.reporter = reporter
        self.assignee: Optional[str] = None
        self.status = "new"
        self.comments: List[Dict[str, Any]] = []
        self.created_at = datetime.utcnow().isoformat()
        self.assigned_at: Optional[str] = None
        self.first_response_at: Optional[str] = None
        self.resolved_at: Optional[str] = None
        self.closed_at: Optional[str] = None
        self.sla_deadline = (datetime.utcnow() + timedelta(hours=SLA_HOURS[priority])).isoformat()
        self.sla_breached = False
        self.sla_responded_within_sla: Optional[bool] = None
        # P1-6: merge/split tracking
        self.merged_into: Optional[str] = None
        self.merged_at: Optional[str] = None
        self.split_into: List[str] = []

    def add_comment(self, content: str, by: str, internal: bool = False) -> Dict[str, Any]:
        c = {
            "comment_id": f"CMT-{uuid.uuid4().hex[:6].upper()}",
            "content": content,
            "by": by,
            "internal": internal,
            "at": datetime.utcnow().isoformat(),
        }
        self.comments.append(c)
        # 第一次回复 = 标记 first_response_at
        if not self.first_response_at and by != self.reporter:
            self.first_response_at = c["at"]
            self._evaluate_sla()
        return c

    def transition(self, new_status: str, by: str = "system") -> None:
        if new_status not in STATES:
            raise ValueError(f"invalid status: {new_status}")
        if new_status not in STATE_TRANSITIONS[self.status]:
            raise ValueError(f"invalid transition: {self.status} → {new_status}")
        prev = self.status
        self.status = new_status
        now = datetime.utcnow().isoformat()
        if new_status == "assigned":
            self.assigned_at = now
        elif new_status == "resolved":
            self.resolved_at = now
            self._evaluate_sla()
        elif new_status == "closed":
            self.closed_at = now
        self.add_comment(f"状态变更: {prev} → {new_status}", by=by, internal=True)

    def _evaluate_sla(self) -> None:
        """评估 SLA 达标情况 (从创建到首次响应)."""
        if not self.first_response_at:
            return
        try:
            created = datetime.fromisoformat(self.created_at)
            responded = datetime.fromisoformat(self.first_response_at)
            deadline = datetime.fromisoformat(self.sla_deadline)
            duration_min = (responded - created).total_seconds() / 60
            sla_min = SLA_HOURS[self.priority] * 60
            self.sla_responded_within_sla = duration_min <= sla_min
            if responded > deadline:
                self.sla_breached = True
        except Exception:
            pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "type": self.type,
            "type_label": TICKET_TYPE_LABELS.get(self.type, self.type),
            "priority": self.priority,
            "subject": self.subject,
            "description": self.description,
            "customer_id": self.customer_id,
            "reporter": self.reporter,
            "assignee": self.assignee,
            "status": self.status,
            "comments": self.comments,
            "created_at": self.created_at,
            "assigned_at": self.assigned_at,
            "first_response_at": self.first_response_at,
            "resolved_at": self.resolved_at,
            "closed_at": self.closed_at,
            "sla_deadline": self.sla_deadline,
            "sla_breached": self.sla_breached,
            "sla_responded_within_sla": self.sla_responded_within_sla,
            "merged_into": self.merged_into,
            "merged_at": self.merged_at,
            "split_into": self.split_into,
        }


_TICKETS: Dict[str, Ticket] = {}


def create_ticket(**kwargs) -> Ticket:
    t = Ticket(**kwargs)
    _TICKETS[t.ticket_id] = t
    logger.info("ticket created: %s priority=%s type=%s", t.ticket_id, t.priority, t.type)
    # P0 立即通知 oncall
    if t.priority == "P0":
        _notify_oncall(t)
    return t


def _notify_oncall(t: Ticket) -> None:
    """P0 通知 oncall — webhook 或 fallback log."""
    payload = {
        "event": "ticket_p0_created",
        "ticket_id": t.ticket_id,
        "subject": t.subject,
        "priority": t.priority,
        "reporter": t.reporter,
        "sla_deadline": t.sla_deadline,
        "at": datetime.utcnow().isoformat(),
    }
    if ONCALL_WEBHOOK_URL:
        try:
            import urllib.request
            req = urllib.request.Request(
                ONCALL_WEBHOOK_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5).read()
        except Exception as e:
            logger.warning("oncall webhook failed: %s, fallback log", e)
            _log_oncall(payload)
    else:
        _log_oncall(payload)


def _log_oncall(payload: Dict[str, Any]) -> None:
    log_dir = os.getenv("ONCALL_LOG_DIR", "D:/Hermes/生产平台/nanobot-factory/backend/logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "oncall.log")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def get_ticket(ticket_id: str) -> Optional[Ticket]:
    return _TICKETS.get(ticket_id)


def list_tickets(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    ticket_type: Optional[str] = None,
    assignee: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> List[Ticket]:
    items = list(_TICKETS.values())
    if status:
        items = [t for t in items if t.status == status]
    if priority:
        items = [t for t in items if t.priority == priority]
    if ticket_type:
        items = [t for t in items if t.type == ticket_type]
    if assignee:
        items = [t for t in items if t.assignee == assignee]
    if customer_id:
        items = [t for t in items if t.customer_id == customer_id]
    return items


def transition_ticket(ticket_id: str, new_status: str, by: str = "system") -> Ticket:
    t = get_ticket(ticket_id)
    if not t:
        raise KeyError(f"ticket not found: {ticket_id}")
    t.transition(new_status, by=by)
    return t


def add_ticket_comment(ticket_id: str, content: str, by: str, internal: bool = False) -> Dict[str, Any]:
    t = get_ticket(ticket_id)
    if not t:
        raise KeyError(f"ticket not found: {ticket_id}")
    return t.add_comment(content, by, internal)


def assign_ticket(ticket_id: str, assignee: str) -> Ticket:
    t = get_ticket(ticket_id)
    if not t:
        raise KeyError(f"ticket not found: {ticket_id}")
    t.assignee = assignee
    if t.status == "new":
        t.transition("assigned", by=assignee)
    return t


def sla_stats() -> Dict[str, Any]:
    """SLA 达标率统计 (按优先级)."""
    by_priority: Dict[str, Dict[str, int]] = {}
    for p in PRIORITIES:
        by_priority[p] = {"total": 0, "responded_in_sla": 0, "breached": 0, "compliance_rate": 0.0}
    for t in _TICKETS.values():
        bucket = by_priority[t.priority]
        bucket["total"] += 1
        if t.sla_responded_within_sla:
            bucket["responded_in_sla"] += 1
        if t.sla_breached:
            bucket["breached"] += 1
    for p, b in by_priority.items():
        if b["total"] > 0:
            b["compliance_rate"] = round(b["responded_in_sla"] / b["total"] * 100, 2)
    # 整体
    total = sum(b["total"] for b in by_priority.values())
    responded = sum(b["responded_in_sla"] for b in by_priority.values())
    overall = round(responded / total * 100, 2) if total else 0.0
    return {
        "overall_compliance_rate": overall,
        "total_tickets": total,
        "by_priority": by_priority,
        "sla_targets_hours": SLA_HOURS,
    }


# ---------------------------------------------------------------------------
# 集成: 客户工单 → CRM
# ---------------------------------------------------------------------------
def on_customer_ticket(customer_id: str, ticket_type: str, subject: str, description: str, priority: str = "P3") -> Ticket:
    """CRM 集成: 为客户创建工单."""
    return create_ticket(
        ticket_type=ticket_type,
        priority=priority,
        subject=subject,
        description=description,
        customer_id=customer_id,
        reporter=f"customer:{customer_id}",
    )


# ---------------------------------------------------------------------------
# P1-6: 工单合并 / 拆分
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def merge_tickets(
    primary_ticket_id: str,
    secondary_ticket_ids: List[str],
    operator: str = "system",
    note: str = "",
) -> Dict[str, Any]:
    """合并工单: secondary 的 comments 迁移到 primary, secondary 标记为 merged.

    Returns:
        {"primary": Ticket, "merged": [Ticket, ...], "moved_comments": int}

    Raises:
        KeyError: 任何 ID 不存在
        ValueError: 状态冲突 (e.g. closed 不可合并; 同一客户不同 customer_id)
    """
    primary = get_ticket(primary_ticket_id)
    if not primary:
        raise KeyError(f"primary ticket not found: {primary_ticket_id}")
    if primary.status == "closed":
        raise ValueError(f"cannot merge into closed ticket: {primary_ticket_id}")
    merged = []
    moved = 0
    for sid in secondary_ticket_ids:
        if sid == primary_ticket_id:
            continue  # skip self
        sec = get_ticket(sid)
        if not sec:
            raise KeyError(f"secondary ticket not found: {sid}")
        if sec.status == "closed":
            raise ValueError(f"cannot merge closed ticket: {sid}")
        if sec.status == "merged":
            raise ValueError(f"ticket {sid!r} already merged into another")
        # 客户不一致警告 (但不阻塞)
        if sec.customer_id and primary.customer_id and sec.customer_id != primary.customer_id:
            logger.warning(
                "merge cross-customer: primary=%s (%s) ← secondary=%s (%s)",
                primary_ticket_id, primary.customer_id, sid, sec.customer_id,
            )
        # 迁 comments
        for c in sec.comments:
            primary.comments.append(c)
            moved += 1
        # 优先级升级: 取最高
        pri_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        if sec.priority in pri_order and primary.priority in pri_order:
            if pri_order[sec.priority] < pri_order[primary.priority]:
                primary.priority = sec.priority
        # secondary 状态: merged
        sec.status = "merged"
        sec.merged_into = primary_ticket_id
        sec.merged_at = _now_iso()
        sec.add_comment(
            f"已合并到主工单 {primary_ticket_id} (操作员: {operator})",
            by=operator, internal=True,
        )
        merged.append(sec)
    # 主工单加合并记录
    primary.add_comment(
        f"合并了 {len(merged)} 张工单: {', '.join(sid for sid in secondary_ticket_ids if sid != primary_ticket_id)}. 迁移 {moved} 条评论。"
        + (f" 备注: {note}" if note else ""),
        by=operator, internal=True,
    )
    logger.info(
        "tickets merged: primary=%s merged=%d moved_comments=%d",
        primary_ticket_id, len(merged), moved,
    )
    return {
        "primary": primary,
        "merged": merged,
        "moved_comments": moved,
    }


def split_ticket(
    ticket_id: str,
    comment_indices: List[int],
    new_subject: str,
    operator: str = "system",
    new_priority: Optional[str] = None,
    new_ticket_type: Optional[str] = None,
) -> Dict[str, Any]:
    """拆分工单: 把指定 indices 的 comments 拆到新工单.

    Args:
        ticket_id: 原工单
        comment_indices: 要拆走的 comment 在原工单 comments 列表中的索引 (0-based)
        new_subject: 新工单主题
        operator: 操作员
        new_priority: 新工单优先级 (默认继承)
        new_ticket_type: 新工单类型 (默认继承)

    Returns:
        {"original": Ticket, "new": Ticket, "moved_count": int}
    """
    orig = get_ticket(ticket_id)
    if not orig:
        raise KeyError(f"ticket not found: {ticket_id}")
    if orig.status in ("closed", "merged"):
        raise ValueError(f"cannot split ticket in status {orig.status!r}")
    if not comment_indices:
        raise ValueError("comment_indices must not be empty")
    # 校验 indices
    max_idx = len(orig.comments) - 1
    for i in comment_indices:
        if not (0 <= i <= max_idx):
            raise ValueError(f"comment index {i} out of range (0..{max_idx})")
    # 创建新工单
    new_priority = new_priority or orig.priority
    new_type = new_ticket_type or orig.type
    new_ticket = create_ticket(
        ticket_type=new_type,
        priority=new_priority,
        subject=new_subject,
        description=f"拆分自工单 {ticket_id}",
        customer_id=orig.customer_id,
        reporter=orig.reporter,
    )
    # 搬移 comments (按降序避免 index 漂移)
    moved = 0
    for i in sorted(comment_indices, reverse=True):
        if i < len(orig.comments):
            c = orig.comments.pop(i)
            new_ticket.comments.append(c)
            moved += 1
    # 审计 trail
    new_ticket.add_comment(
        f"由 {ticket_id} 拆分而来 (操作员: {operator})", by=operator, internal=True,
    )
    orig.add_comment(
        f"已拆分 {moved} 条评论到新工单 {new_ticket.ticket_id} (操作员: {operator})",
        by=operator, internal=True,
    )
    # 记录原→新关联
    orig.split_into = (orig.__dict__.get("split_into") or []) + [new_ticket.ticket_id]
    logger.info(
        "ticket split: original=%s new=%s moved=%d",
        ticket_id, new_ticket.ticket_id, moved,
    )
    return {
        "original": orig,
        "new": new_ticket,
        "moved_count": moved,
    }
