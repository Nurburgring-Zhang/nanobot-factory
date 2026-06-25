"""P1-4: 合同到期提醒 (Contract Expiration Monitor)

业务背景:
- 合同在到期前 30 天需要触发续约提醒 (商务 + 法务).
- 通过 cron / Celery beat 每日扫描.
- 提醒渠道: 邮件 (默认) + 飞书/钉钉 webhook (env 切换).
- 合同状态机: draft → signed → active → (renewed | expired).
- 重复提醒: 到期前 30 天每天提醒一次; 到期后每天一次 (expired_notice).

公开 API:
  - check_expiring(window_days=30)            → ExpirationReport
  - expire_overdue()                          → int  (强制过期已过截止日的 active 合同)
  - renew_contract(contract_id, new_end_date) → Contract
  - get_expiration_stats()                    → Dict
  - send_expiration_notices(report)           → DispatchResult (calls hooks)
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

# 提醒配置
EXPIRATION_DEFAULT_WINDOW_DAYS = 30
EXPIRATION_NOTICE_WEBHOOK = os.getenv("CONTRACT_EXPIRATION_WEBHOOK_URL", "")
# 邮件发送: 真实环境用 SMTP/SendGrid; 此处用 log stub.
EXPIRATION_EMAIL_TO = os.getenv("CONTRACT_EXPIRATION_EMAIL_TO", "")
EXPIRATION_LOG_DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "logs"
)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
NOTICE_KINDS = ["upcoming", "today", "overdue", "renewed"]

@dataclass
class ExpirationNotice:
    notice_id: str
    contract_id: str
    company_name: str
    contact_email: str
    end_date: str
    days_to_expiry: int
    kind: str                # upcoming / today / overdue / renewed
    sent_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    channel: str = "log"     # log / email / webhook
    sent_to: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExpirationReport:
    upcoming: List[ExpirationNotice] = field(default_factory=list)
    today: List[ExpirationNotice] = field(default_factory=list)
    overdue: List[ExpirationNotice] = field(default_factory=list)
    scanned: int = 0
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scanned": self.scanned,
            "upcoming_count": len(self.upcoming),
            "today_count": len(self.today),
            "overdue_count": len(self.overdue),
            "upcoming": [n.to_dict() for n in self.upcoming],
            "today": [n.to_dict() for n in self.today],
            "overdue": [n.to_dict() for n in self.overdue],
            "generated_at": self.generated_at,
        }


# 内部记录 — 同一合同同一日只发一次
_SENT_TODAY: Dict[str, str] = {}  # contract_id -> ISO date (Y-M-D)


def _today_str(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _parse_end_date(c: Any) -> Optional[datetime]:
    """提取合同结束日期. 优先 variables.end_date, 否则 fallback 到 created_at + 1y."""
    vars_ = getattr(c, "variables", {}) or {}
    raw = vars_.get("end_date")
    if not raw or raw == "长期有效":
        return None  # 长期合同, 不提醒
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(raw)[:10], fmt)
        except (ValueError, TypeError):
            continue
    # 尝试 ISO 格式
    try:
        return datetime.fromisoformat(str(raw)[:10])
    except (ValueError, TypeError):
        return None


def _classify_contract(
    c: Any,
    now: datetime,
    window_days: int,
) -> Optional[ExpirationNotice]:
    """Return a notice for the contract if it needs attention, else None."""
    status = getattr(c, "status", None)
    # 仅 active / signed 状态需提醒 (draft 未生效, expired/renewed 已结)
    if status not in ("active", "signed"):
        return None
    end_dt = _parse_end_date(c)
    if end_dt is None:
        return None
    days_to_expiry = (end_dt - now).days
    if days_to_expiry < 0:
        kind = "overdue"
    elif days_to_expiry == 0:
        kind = "today"
    elif days_to_expiry <= window_days:
        kind = "upcoming"
    else:
        return None
    contract_id = getattr(c, "contract_id", "")
    # 去重: 同日同合同不重复
    today = _today_str(now)
    if _SENT_TODAY.get(contract_id) == today and kind != "overdue":
        # overdue 每天提醒
        return None
    return ExpirationNotice(
        notice_id=f"EN-{uuid.uuid4().hex[:8].upper()}",
        contract_id=contract_id,
        company_name=getattr(c, "company_name", ""),
        contact_email=getattr(c, "contact_email", ""),
        end_date=end_dt.strftime("%Y-%m-%d"),
        days_to_expiry=days_to_expiry,
        kind=kind,
    )


def check_expiring(
    *,
    now: Optional[datetime] = None,
    window_days: int = EXPIRATION_DEFAULT_WINDOW_DAYS,
    contracts: Optional[List[Any]] = None,
) -> ExpirationReport:
    """扫描所有合同, 返回到期提醒报告."""
    if now is None:
        now = datetime.utcnow()
    if contracts is None:
        from . import list_contracts  # type: ignore
        contracts = list_contracts()
    report = ExpirationReport()
    for c in contracts:
        notice = _classify_contract(c, now, window_days)
        if notice is None:
            continue
        if notice.kind == "upcoming":
            report.upcoming.append(notice)
        elif notice.kind == "today":
            report.today.append(notice)
        elif notice.kind == "overdue":
            report.overdue.append(notice)
        report.scanned += 1
    report.upcoming.sort(key=lambda n: n.days_to_expiry)
    report.today.sort(key=lambda n: n.contract_id)
    report.overdue.sort(key=lambda n: n.days_to_expiry)
    return report


def send_expiration_notices(report: ExpirationReport) -> Dict[str, int]:
    """发送提醒: webhook 优先, fallback log."""
    counters = {"emails_sent": 0, "webhooks_sent": 0, "logs_written": 0}
    for bucket_name, items in [
        ("upcoming", report.upcoming),
        ("today", report.today),
        ("overdue", report.overdue),
    ]:
        for n in items:
            payload = {
                "event": "contract_expiration_notice",
                "bucket": bucket_name,
                "notice": n.to_dict(),
                "at": datetime.utcnow().isoformat(),
            }
            # Webhook
            if EXPIRATION_NOTICE_WEBHOOK:
                try:
                    import urllib.request
                    req = urllib.request.Request(
                        EXPIRATION_NOTICE_WEBHOOK,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    urllib.request.urlopen(req, timeout=5).read()
                    counters["webhooks_sent"] += 1
                    n.channel = "webhook"
                    n.sent_to = EXPIRATION_NOTICE_WEBHOOK
                    _SENT_TODAY[n.contract_id] = _today_str(datetime.utcnow())
                    continue
                except Exception as e:
                    logger.warning("expiration webhook failed: %s, fallback log", e)
            # Email
            if EXPIRATION_EMAIL_TO and n.contact_email:
                try:
                    _send_email(n, payload)
                    counters["emails_sent"] += 1
                    n.channel = "email"
                    n.sent_to = n.contact_email
                    _SENT_TODAY[n.contract_id] = _today_str(datetime.utcnow())
                    continue
                except Exception as e:
                    logger.warning("expiration email failed: %s, fallback log", e)
            # Log fallback
            _append_log(payload)
            counters["logs_written"] += 1
            n.channel = "log"
            _SENT_TODAY[n.contract_id] = _today_str(datetime.utcnow())
    return counters


def _send_email(n: ExpirationNotice, payload: Dict[str, Any]) -> None:
    """邮件发送 (mock). 真实环境用 smtplib / SendGrid SDK."""
    log_dir = os.getenv("CONTRACT_EXPIRATION_LOG_DIR") or EXPIRATION_LOG_DEFAULT_DIR
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "contract_expiration_emails.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "to": n.contact_email,
            "subject": f"[{'紧急' if n.kind == 'overdue' else '提醒'}] 合同 {n.contract_id} 将于 {n.days_to_expiry} 天后到期",
            "body": f"贵司合同 {n.contract_id} ({n.company_name}) 将于 {n.end_date} 到期, 请及时续约。",
            "payload": payload,
        }, ensure_ascii=False) + "\n")


def _append_log(entry: Dict[str, Any]) -> None:
    log_dir = os.getenv("CONTRACT_EXPIRATION_LOG_DIR") or EXPIRATION_LOG_DEFAULT_DIR
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "contract_expiration.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def expire_overdue(*, now: Optional[datetime] = None) -> int:
    """强制将已过 end_date 的 active/signed 合同标记为 expired. 返回处理数."""
    if now is None:
        now = datetime.utcnow()
    from . import _STORE, list_contracts  # type: ignore
    n = 0
    for c in list_contracts():
        if c.status not in ("active", "signed"):
            continue
        end_dt = _parse_end_date(c)
        if end_dt and end_dt < now and c.status != "expired":
            c.status = "expired"
            # 重算 SM3 哈希链
            try:
                from . import sm3_hash  # type: ignore
                c.hash_chain.append(sm3_hash(c.to_dict()))
            except Exception:
                pass
            _STORE[c.contract_id] = c
            n += 1
            logger.info("contract expired: %s (end_date=%s)", c.contract_id, end_dt.strftime("%Y-%m-%d"))
    return n


def renew_contract(contract_id: str, new_end_date: str) -> Any:
    """续约: 生成新合同 (按当前合同复制) + 标记旧合同 renewed."""
    from . import get_contract, generate_contract  # type: ignore
    old = get_contract(contract_id)
    if not old:
        raise KeyError(f"contract not found: {contract_id}")
    if old.status not in ("active", "signed", "expired"):
        raise ValueError(f"cannot renew contract in status {old.status!r}")
    # 复制生成新合同
    new = generate_contract(
        template=old.template,
        company_name=old.company_name,
        contact_email=old.contact_email,
        plan_name=old.variables.get("plan_name", ""),
        amount=old.amount,
        start_date=datetime.utcnow().strftime("%Y-%m-%d"),
        end_date=new_end_date,
        extra_vars={"renewed_from": old.contract_id},
    )
    # 标记旧合同 renewed
    old.status = "renewed"
    from . import sm3_hash  # type: ignore
    old.hash_chain.append(sm3_hash(old.to_dict()))
    return new


def get_expiration_stats() -> Dict[str, Any]:
    """合同状态 + 到期分布."""
    from . import list_contracts  # type: ignore
    by_status: Dict[str, int] = {}
    now = datetime.utcnow()
    by_window: Dict[str, int] = {"expired": 0, "0-7d": 0, "8-30d": 0, "31-90d": 0, "90d+": 0, "long_term": 0}
    for c in list_contracts():
        by_status[c.status] = by_status.get(c.status, 0) + 1
        end_dt = _parse_end_date(c)
        if end_dt is None:
            by_window["long_term"] += 1
            continue
        days = (end_dt - now).days
        if days < 0:
            by_window["expired"] += 1
        elif days <= 7:
            by_window["0-7d"] += 1
        elif days <= 30:
            by_window["8-30d"] += 1
        elif days <= 90:
            by_window["31-90d"] += 1
        else:
            by_window["90d+"] += 1
    return {
        "by_status": by_status,
        "by_expiration_window": by_window,
        "total_contracts": sum(by_status.values()),
    }


def _reset_expiration() -> None:
    """测试用 — 清空去重状态."""
    _SENT_TODAY.clear()


__all__ = [
    "NOTICE_KINDS", "EXPIRATION_DEFAULT_WINDOW_DAYS",
    "ExpirationNotice", "ExpirationReport",
    "check_expiring", "send_expiration_notices",
    "expire_overdue", "renew_contract", "get_expiration_stats",
    "_reset_expiration",
]
