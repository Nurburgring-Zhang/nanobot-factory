"""P1-8: 公开 Webhook (Outbound Event Hooks)

业务背景:
- 内部系统事件 (工单创建/状态变更, 客户升级, 发票开具) 需要推送给外部系统
  (Slack / 飞书 / 钉钉 / 自家 BI / 数据中台).
- 公开 API: 第三方系统通过 API Key 订阅事件类型, 我们推送.

设计:
- 订阅: 第三方系统 POST /api/v1/public/hooks  注册 webhook URL + event types.
- 推送: 内部事件触发 → 遍历订阅 → POST 事件 payload.
- 重试: 失败重试 3 次 (exponential backoff).
- 安全: HMAC-SHA256 签名 (X-Webhook-Signature).

事件类型:
  - ticket.created / ticket.assigned / ticket.resolved / ticket.closed
  - customer.created / customer.upgraded / customer.churned
  - invoice.generated / invoice.redlettered

公开 API:
  - register_webhook(url, events, secret=None)  → WebhookSubscription
  - list_webhooks()                             → [WebhookSubscription]
  - delete_webhook(hook_id)                     → bool
  - emit(event_type, payload)                   → DispatchResult
  - list_emits(limit)                           → [EmitRecord]  (审计/重放)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUPPORTED_EVENTS = [
    # Tickets
    "ticket.created", "ticket.assigned", "ticket.resolved", "ticket.closed", "ticket.merged",
    # CRM
    "customer.created", "customer.upgraded", "customer.churned",
    # Invoices
    "invoice.generated", "invoice.redlettered", "invoice.verified",
    # Billing
    "order.paid", "order.refunded", "subscription.created", "subscription.cancelled",
    "dispute.created", "dispute.resolved",
    # Contracts
    "contract.signed", "contract.expired", "contract.expiring",
]

MAX_RETRY = 3
RETRY_BACKOFF_SECONDS = [1, 3, 9]  # exponential
WEBHOOK_TIMEOUT_SECONDS = 5
SIGNATURE_HEADER = "X-Webhook-Signature"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class WebhookSubscription:
    hook_id: str
    url: str
    events: List[str]
    secret: str
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_triggered_at: Optional[str] = None
    failure_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # 不暴露 secret 明文
        d["secret"] = d["secret"][:6] + "***" if d["secret"] else ""
        return d


@dataclass
class EmitRecord:
    emit_id: str
    event_type: str
    payload: Dict[str, Any]
    sent_to: List[str] = field(default_factory=list)        # hook_ids succeeded
    failed_to: List[str] = field(default_factory=list)       # hook_ids failed (after retry)
    signature: str = ""
    emitted_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
_HOOKS: Dict[str, WebhookSubscription] = {}
_EMITS: List[EmitRecord] = []  # 审计
_MAX_EMIT_HISTORY = 500


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _sign_payload(secret: str, body: str) -> str:
    """HMAC-SHA256 签名."""
    return hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------
def register_webhook(
    url: str,
    events: List[str],
    secret: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> WebhookSubscription:
    """注册一个公开 webhook."""
    if not url or not url.startswith(("http://", "https://")):
        raise ValueError("url must be a valid http(s) URL")
    for e in events:
        if e not in SUPPORTED_EVENTS and e != "*":
            raise ValueError(f"unsupported event: {e!r}. valid: {SUPPORTED_EVENTS} or '*'")
    hook_id = f"WHK-{uuid.uuid4().hex[:12].upper()}"
    sub = WebhookSubscription(
        hook_id=hook_id,
        url=url,
        events=events,
        secret=secret or uuid.uuid4().hex,
        metadata=metadata or {},
    )
    _HOOKS[hook_id] = sub
    logger.info("webhook registered: %s url=%s events=%s", hook_id, url, events)
    return sub


def list_webhooks(active_only: bool = False) -> List[WebhookSubscription]:
    items = list(_HOOKS.values())
    if active_only:
        items = [h for h in items if h.active]
    return items


def get_webhook(hook_id: str) -> Optional[WebhookSubscription]:
    return _HOOKS.get(hook_id)


def delete_webhook(hook_id: str) -> bool:
    return _HOOKS.pop(hook_id, None) is not None


def update_webhook(hook_id: str, **fields) -> Optional[WebhookSubscription]:
    h = _HOOKS.get(hook_id)
    if not h:
        return None
    for k, v in fields.items():
        if hasattr(h, k) and k not in ("hook_id", "created_at"):
            setattr(h, k, v)
    return h


# ---------------------------------------------------------------------------
# Emit (推送)
# ---------------------------------------------------------------------------
def emit(event_type: str, payload: Dict[str, Any], *, sync: bool = True) -> EmitRecord:
    """发出事件 → 推送给所有订阅的 webhook.

    sync=True: 同步推送 (测试用, 失败计入 EmitRecord)
    sync=False: 真实环境用 Celery async (本模块只记 emit record, 留接口)
    """
    rec = EmitRecord(
        emit_id=f"EMT-{uuid.uuid4().hex[:12].upper()}",
        event_type=event_type,
        payload=payload,
    )
    body = json.dumps({
        "event": event_type,
        "payload": payload,
        "emit_id": rec.emit_id,
        "emitted_at": rec.emitted_at,
    }, sort_keys=True, ensure_ascii=False, default=str)
    start = time.time()
    for hook in _HOOKS.values():
        if not hook.active:
            continue
        if hook.events != ["*"] and event_type not in hook.events:
            continue
        sig = _sign_payload(hook.secret, body)
        rec.signature = sig
        ok = _deliver_with_retry(hook, body, sig)
        if ok:
            rec.sent_to.append(hook.hook_id)
            hook.last_triggered_at = _now_iso()
        else:
            rec.failed_to.append(hook.hook_id)
            hook.failure_count += 1
    rec.duration_ms = int((time.time() - start) * 1000)
    _EMITS.append(rec)
    if len(_EMITS) > _MAX_EMIT_HISTORY:
        del _EMITS[:len(_EMITS) - _MAX_EMIT_HISTORY]
    logger.info(
        "event emitted: %s type=%s delivered=%d failed=%d",
        rec.emit_id, event_type, len(rec.sent_to), len(rec.failed_to),
    )
    return rec


def _deliver_with_retry(hook: WebhookSubscription, body: str, sig: str) -> bool:
    """POST + 指数退避重试."""
    import urllib.request
    import urllib.error
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRY):
        if attempt > 0:
            time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
        try:
            req = urllib.request.Request(
                hook.url,
                data=body.encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    SIGNATURE_HEADER: f"sha256={sig}",
                    "User-Agent": "nanobot-factory-webhook/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=WEBHOOK_TIMEOUT_SECONDS) as resp:
                if 200 <= resp.status < 300:
                    return True
                last_exc = RuntimeError(f"HTTP {resp.status}")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            last_exc = e
            logger.debug("webhook delivery attempt %d failed: %s", attempt + 1, e)
        except Exception as e:
            last_exc = e
            logger.warning("webhook delivery unexpected error: %s", e)
    logger.warning(
        "webhook delivery exhausted retries: hook=%s url=%s last_error=%s",
        hook.hook_id, hook.url, last_exc,
    )
    return False


def list_emits(limit: int = 50) -> List[EmitRecord]:
    return list(_EMITS)[-limit:]


# ---------------------------------------------------------------------------
# 测试用 — 重置
# ---------------------------------------------------------------------------
def _reset_webhooks() -> None:
    _HOOKS.clear()
    _EMITS.clear()


__all__ = [
    "SUPPORTED_EVENTS", "SIGNATURE_HEADER", "MAX_RETRY",
    "WebhookSubscription", "EmitRecord",
    "register_webhook", "list_webhooks", "get_webhook", "delete_webhook", "update_webhook",
    "emit", "list_emits",
    "_reset_webhooks",
]
