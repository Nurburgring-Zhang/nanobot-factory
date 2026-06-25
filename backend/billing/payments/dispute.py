"""P1-2: Stripe Dispute / Chargeback 处理模块.

业务背景:
- Dispute (争议 / Chargeback) 是国际支付 (Stripe/Adyen/Braintree) 必备功能.
- 客户在发卡行发起争议 → Stripe 扣款 + 资金冻结 → 商家需在 7-21 天内提供证据.
- 我们需要:
  1. 接收 `charge.dispute.created` / `charge.dispute.closed` webhook
  2. 标记订单状态 (Order.status = "disputed")
  3. 触发 oncall 告警 (高优, 需立即响应)
  4. 提供证据上传接口 + 接受/拒绝流程

本模块独立于 StripeProvider (provider 负责验签, 本模块负责业务动作),
符合 P6-Fix-C-1 边界设计: provider 保持纯净, 业务逻辑在 route 层.

公开 API:
  - register_dispute(order_id, dispute_id, amount_cents, reason, evidence_due_by)
  - get_dispute(dispute_id)
  - get_disputes_by_order(order_id)
  - upload_evidence(dispute_id, evidence: dict)
  - resolve_dispute(dispute_id, status, resolution_note)
  - list_open_disputes()
  - dispute_stats()
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
DISPUTE_STATUSES = ["needs_response", "under_review", "won", "lost", "closed"]
DISPUTE_REASONS = [
    "fraudulent",          # 欺诈
    "duplicate",           # 重复扣款
    "subscription_canceled",  # 已退订但继续扣款
    "product_not_received",   # 未收到商品/服务
    "product_unacceptable",   # 商品/服务不符
    "credit_not_processed",   # 退款未处理
    "general",             # 其他
]

# 告警 webhook (可对接飞书/Slack/钉钉)
DISPUTE_ALERT_WEBHOOK = os.getenv("DISPUTE_ALERT_WEBHOOK_URL", "")


@dataclass
class Dispute:
    """Dispute (争议/拒付) 记录."""
    dispute_id: str
    order_id: str
    payment_id: str
    amount_cents: int
    currency: str
    reason: str
    status: str = "needs_response"     # needs_response / under_review / won / lost / closed
    evidence: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    evidence_due_by: Optional[str] = None   # ISO8601, 证据截止时间 (Stripe 默认 7-21 天)
    closed_at: Optional[str] = None
    resolution_note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# 进程内存储
_DISPUTES: Dict[str, Dispute] = {}        # dispute_id -> Dispute
_BY_ORDER: Dict[str, List[str]] = {}        # order_id -> [dispute_id]


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _alert_oncall(d: Dispute) -> None:
    """Dispute 告警: webhook 优先, fallback oncall.log."""
    payload = {
        "event": "dispute_created",
        "severity": "critical" if d.amount_cents >= 10000 else "warning",
        "dispute_id": d.dispute_id,
        "order_id": d.order_id,
        "amount_cents": d.amount_cents,
        "currency": d.currency,
        "reason": d.reason,
        "evidence_due_by": d.evidence_due_by,
        "at": _now_iso(),
    }
    if DISPUTE_ALERT_WEBHOOK:
        try:
            import urllib.request
            req = urllib.request.Request(
                DISPUTE_ALERT_WEBHOOK,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5).read()
            return
        except Exception as e:
            logger.warning("dispute alert webhook failed: %s, fallback log", e)
    # Fallback: 写 oncall.log
    log_dir = os.getenv("ONCALL_LOG_DIR", "D:/Hermes/生产平台/nanobot-factory/backend/logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "oncall.log"), "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------
def register_dispute(
    order_id: str,
    payment_id: str,
    amount_cents: int,
    currency: str = "USD",
    reason: str = "general",
    evidence_due_days: int = 14,
    dispute_id: Optional[str] = None,
    alert: bool = True,
) -> Dispute:
    """注册一笔 dispute (通常由 webhook handler 调用)."""
    if reason not in DISPUTE_REASONS:
        raise ValueError(f"invalid reason: {reason!r}. valid: {DISPUTE_REASONS}")
    if amount_cents <= 0:
        raise ValueError(f"amount_cents must be > 0, got {amount_cents}")
    did = dispute_id or f"dp_{uuid.uuid4().hex[:16]}"
    if did in _DISPUTES:
        raise ValueError(f"dispute_id {did!r} already exists")
    due = (datetime.utcnow() + timedelta(days=evidence_due_days)).isoformat()
    d = Dispute(
        dispute_id=did,
        order_id=order_id,
        payment_id=payment_id,
        amount_cents=int(amount_cents),
        currency=currency.upper(),
        reason=reason,
        evidence_due_by=due,
    )
    _DISPUTES[did] = d
    _BY_ORDER.setdefault(order_id, []).append(did)
    if alert:
        _alert_oncall(d)
    logger.warning(
        "dispute registered: %s order=%s amount=%d %s reason=%s",
        did, order_id, amount_cents, currency, reason,
    )
    return d


def get_dispute(dispute_id: str) -> Optional[Dispute]:
    return _DISPUTES.get(dispute_id)


def get_disputes_by_order(order_id: str) -> List[Dispute]:
    return [_DISPUTES[i] for i in _BY_ORDER.get(order_id, []) if i in _DISPUTES]


def upload_evidence(dispute_id: str, evidence: Dict[str, Any]) -> Dispute:
    """上传争议证据 (customer_communication / receipt / shipping / etc.)."""
    d = _DISPUTES.get(dispute_id)
    if not d:
        raise KeyError(f"dispute not found: {dispute_id}")
    if d.status not in ("needs_response", "under_review"):
        raise ValueError(
            f"cannot upload evidence for dispute in status {d.status!r}"
        )
    d.evidence.update(evidence or {})
    d.updated_at = _now_iso()
    if d.status == "needs_response":
        d.status = "under_review"
    return d


def resolve_dispute(
    dispute_id: str,
    status: str,
    resolution_note: Optional[str] = None,
) -> Dispute:
    """结案 (won / lost / closed)."""
    if status not in ("won", "lost", "closed"):
        raise ValueError(f"invalid resolution status: {status!r}")
    d = _DISPUTES.get(dispute_id)
    if not d:
        raise KeyError(f"dispute not found: {dispute_id}")
    d.status = status
    d.closed_at = _now_iso()
    d.resolution_note = resolution_note
    d.updated_at = d.closed_at
    logger.info(
        "dispute resolved: %s status=%s amount=%d",
        dispute_id, status, d.amount_cents,
    )
    return d


def list_open_disputes() -> List[Dispute]:
    """列出未结案 dispute."""
    return [d for d in _DISPUTES.values() if d.status in ("needs_response", "under_review")]


def dispute_stats() -> Dict[str, Any]:
    """Dispute 全局统计 (总额 / 状态分布 / 胜率)."""
    by_status: Dict[str, int] = {s: 0 for s in DISPUTE_STATUSES}
    by_reason: Dict[str, int] = {}
    total_amount = 0
    won_amount = 0
    lost_amount = 0
    open_amount = 0
    for d in _DISPUTES.values():
        by_status[d.status] = by_status.get(d.status, 0) + 1
        by_reason[d.reason] = by_reason.get(d.reason, 0) + 1
        total_amount += d.amount_cents
        if d.status == "won":
            won_amount += d.amount_cents
        elif d.status == "lost":
            lost_amount += d.amount_cents
        elif d.status in ("needs_response", "under_review"):
            open_amount += d.amount_cents
    total_decided = by_status.get("won", 0) + by_status.get("lost", 0)
    win_rate = round(by_status.get("won", 0) / total_decided * 100, 2) if total_decided else 0.0
    return {
        "total_disputes": len(_DISPUTES),
        "by_status": by_status,
        "by_reason": by_reason,
        "total_amount_cents": total_amount,
        "open_amount_cents": open_amount,
        "won_amount_cents": won_amount,
        "lost_amount_cents": lost_amount,
        "win_rate_pct": win_rate,
    }


def _reset_disputes() -> None:
    """测试用 — 清空 dispute 存储."""
    _DISPUTES.clear()
    _BY_ORDER.clear()


__all__ = [
    "DISPUTE_STATUSES", "DISPUTE_REASONS",
    "Dispute",
    "register_dispute", "get_dispute", "get_disputes_by_order",
    "upload_evidence", "resolve_dispute",
    "list_open_disputes", "dispute_stats",
    "_reset_disputes",
]
