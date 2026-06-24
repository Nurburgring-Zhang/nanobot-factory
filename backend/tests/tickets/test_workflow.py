"""
P4-10-W2: 工单工作流测试 (状态机 + SLA)
"""
import sys
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from tickets import (
    TICKET_TYPES, PRIORITIES, STATES, SLA_HOURS,
    STATE_TRANSITIONS,
    create_ticket, get_ticket, list_tickets,
    transition_ticket, assign_ticket, add_ticket_comment,
    sla_stats, on_customer_ticket, Ticket,
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """隔离 oncall log 到临时目录."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setenv("ONCALL_LOG_DIR", str(log_dir))
    monkeypatch.setenv("ONCALL_WEBHOOK_URL", "")


def test_state_machine_happy_path():
    """new → assigned → in_progress → resolved → closed."""
    t = create_ticket(
        ticket_type="problem",
        priority="P2",
        subject="登录失败",
        description="用户反馈登录失败",
        reporter="user-1",
    )
    assert t.status == "new"
    assign_ticket(t.ticket_id, assignee="agent-1")
    assert t.status == "assigned"
    assert t.assignee == "agent-1"
    transition_ticket(t.ticket_id, "in_progress", by="agent-1")
    transition_ticket(t.ticket_id, "resolved", by="agent-1")
    assert t.status == "resolved"
    assert t.resolved_at is not None
    transition_ticket(t.ticket_id, "closed", by="agent-1")
    assert t.status == "closed"
    assert t.closed_at is not None


def test_state_machine_invalid_transition():
    """状态机非法转移应拒绝."""
    t = create_ticket(
        ticket_type="billing",
        priority="P3",
        subject="账单问题",
        description="...",
    )
    # new → in_progress 非法 (必须先 assigned)
    with pytest.raises(ValueError, match="invalid transition"):
        transition_ticket(t.ticket_id, "in_progress")
    # closed 不能再去任何状态
    transition_ticket(t.ticket_id, "assigned", by="sys")
    transition_ticket(t.ticket_id, "in_progress", by="sys")
    transition_ticket(t.ticket_id, "resolved", by="sys")
    transition_ticket(t.ticket_id, "closed", by="sys")
    with pytest.raises(ValueError):
        transition_ticket(t.ticket_id, "in_progress")


def test_sla_targets_p0_p1_p2_p3():
    """SLA 4 等级时长正确: P0=1h, P1=4h, P2=24h, P3=72h."""
    assert SLA_HOURS["P0"] == 1
    assert SLA_HOURS["P1"] == 4
    assert SLA_HOURS["P2"] == 24
    assert SLA_HOURS["P3"] == 72
    for p in PRIORITIES:
        t = create_ticket(
            ticket_type="problem",
            priority=p,
            subject=f"SLA test {p}",
            description="x",
        )
        deadline = datetime.fromisoformat(t.sla_deadline)
        created = datetime.fromisoformat(t.created_at)
        diff_hours = (deadline - created).total_seconds() / 3600
        # 允许 0.01 小时误差
        assert abs(diff_hours - SLA_HOURS[p]) < 0.02, f"{p} SLA mismatch: {diff_hours} vs {SLA_HOURS[p]}"


def test_sla_response_within_sla():
    """P3 立即响应 → sla_responded_within_sla = True."""
    t = create_ticket(
        ticket_type="problem",
        priority="P3",
        subject="P3 测试",
        description="x",
    )
    add_ticket_comment(t.ticket_id, "已收到, 正在排查", by="agent-1")
    assert t.first_response_at is not None
    assert t.sla_responded_within_sla is True
    assert t.sla_breached is False


def test_sla_breach_on_late_response():
    """SLA 违约 — 修改 created_at 模拟超过 72h 后响应."""
    t = create_ticket(
        ticket_type="problem",
        priority="P3",
        subject="late test",
        description="x",
    )
    # 把 created_at 倒回 80 小时前 (超过 P3 72h)
    t.created_at = (datetime.utcnow() - timedelta(hours=80)).isoformat()
    t.sla_deadline = (datetime.fromisoformat(t.created_at) + timedelta(hours=72)).isoformat()
    add_ticket_comment(t.ticket_id, "迟来的回复", by="agent-1")
    assert t.sla_breached is True
    assert t.sla_responded_within_sla is False


def test_p0_notifies_oncall():
    """P0 工单应触发 oncall 通知 (无 webhook 时写 log)."""
    t = create_ticket(
        ticket_type="incident",
        priority="P0",
        subject="生产环境停机",
        description="所有服务 500",
        reporter="monitor",
    )
    assert t.priority == "P0"
    assert t.ticket_id.startswith("TK-")
    # 验证 oncall log 被写入
    log_path = Path(os.environ["ONCALL_LOG_DIR"]) / "oncall.log"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "ticket_p0_created" in content
    assert t.ticket_id in content


def test_sla_stats():
    """SLA 达标率统计 — 4 优先级 + 整体."""
    # 创建几个工单
    for p in ["P0", "P1", "P2", "P3"]:
        t = create_ticket(ticket_type="problem", priority=p, subject=f"stats {p}", description="x")
        add_ticket_comment(t.ticket_id, "quick reply", by="agent-1")
    stats = sla_stats()
    assert "overall_compliance_rate" in stats
    assert "by_priority" in stats
    assert stats["total_tickets"] >= 4
    for p in ["P0", "P1", "P2", "P3"]:
        assert p in stats["by_priority"]
        assert stats["by_priority"][p]["total"] >= 1
    # sla_targets_hours 完整
    assert stats["sla_targets_hours"]["P0"] == 1
    assert stats["sla_targets_hours"]["P1"] == 4


def test_ticket_list_and_filter():
    t1 = create_ticket(ticket_type="billing", priority="P1", subject="发票错", description="x", customer_id="CUS-1")
    t2 = create_ticket(ticket_type="problem", priority="P2", subject="慢", description="x", customer_id="CUS-1")
    t3 = create_ticket(ticket_type="problem", priority="P3", subject="x", description="x", customer_id="CUS-2")
    p1 = list_tickets(priority="P1")
    assert any(t.ticket_id == t1.ticket_id for t in p1)
    cus1 = list_tickets(customer_id="CUS-1")
    assert len(cus1) == 2
    bt = list_tickets(ticket_type="billing")
    assert all(t.type == "billing" for t in bt)


def test_invalid_inputs():
    with pytest.raises(ValueError, match="invalid type"):
        create_ticket(ticket_type="invalid", priority="P3", subject="x", description="y")
    with pytest.raises(ValueError, match="invalid priority"):
        create_ticket(ticket_type="problem", priority="P9", subject="x", description="y")


def test_customer_ticket_hook():
    """CRM 集成: 为客户创建工单."""
    t = on_customer_ticket("CUS-001", "problem", "客户报障", "服务异常", priority="P2")
    assert t.customer_id == "CUS-001"
    assert t.priority == "P2"
    assert t.reporter == "customer:CUS-001"
