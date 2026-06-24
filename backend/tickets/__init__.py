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
STATES = ["new", "assigned", "in_progress", "resolved", "closed"]
STATE_TRANSITIONS = {
    "new": ["assigned", "closed"],
    "assigned": ["in_progress", "closed"],
    "in_progress": ["resolved", "closed"],
    "resolved": ["closed", "in_progress"],  # 允许重开
    "closed": [],
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
