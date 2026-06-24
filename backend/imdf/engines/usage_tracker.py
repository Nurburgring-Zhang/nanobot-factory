"""AI provider 用量追踪 + 计费 — P2-3-W2。

对外接口 (4 个):
- ``UsageTracker.record(...)``              写入一条 UsageLog (供 canvas_web 调用 AI 时调用)
- ``UsageTracker.user_summary(user_id, days)``   聚合用户 N 天内的消耗 + 成本
- ``UsageTracker.org_summary(org_id, days)``     聚合组织
- ``UsageTracker.check_rate_limit(user_id, provider_id, per_hour)``  简单滑动窗口限流

设计:
- **降级写盘**: DB 不可用 → 写 JSONL ``data/usage_fallback.jsonl`` (不抛错, 不影响 AI 调用主链路)。
- **同步函数**: record() 同步写, 因为它在 AI 调用链路中, 不能 await 半天。
- **provider registry 解耦**: 通过 ``engines.provider_registry.compute_cost_usd`` 算钱,
  tracker 不重复计费逻辑。

调用示例::

    from engines.usage_tracker import UsageTracker
    from engines.provider_registry import compute_cost_usd

    cost = compute_cost_usd("openai-compatible", "gpt-4o", prompt_tokens=100, completion_tokens=200)
    UsageTracker.record(
        user_id="user_abc", provider_id="openai-compatible", protocol="openai-compatible",
        kind="chat", model="gpt-4o", status="ok",
        prompt_tokens=100, completion_tokens=200, cost_usd=cost, latency_ms=1234,
    )
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── DB fallback 路径 ─────────────────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _BACKEND_ROOT / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_FALLBACK_LOG = _DATA_DIR / "usage_fallback.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _new_id() -> str:
    return f"ul_{uuid.uuid4().hex[:12]}"


def _safe_bcrypt_input(s: str) -> str:  # noqa: ARG001  (placeholder for future)
    return s[:4096] if isinstance(s, str) else ""


# ══════════════════════════════════════════════════════════════════════════════
# 内存限流 (per (user_id, provider_id) 滑动窗口)
# ══════════════════════════════════════════════════════════════════════════════
class _SlidingWindowLimiter:
    """进程内滑动窗口 — 每个 (user_id, provider_id) 维护一个 ``deque[timestamps]``。

    生产环境应换 Redis 集群版 (P3+ 任务), 这里先做单机够用。
    """

    def __init__(self, window_seconds: int = 3600) -> None:
        self.window_seconds = window_seconds
        self._buckets: Dict[Tuple[str, str], Deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: Tuple[str, str], limit: int) -> Tuple[bool, int]:
        """记录一次 hit, 返回 ``(allowed, remaining)``。

        ``allowed=False`` 表示已达上限; ``remaining`` 是当前窗口剩余配额。
        """
        now = time.time()
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            # 弹出过期
            cutoff = now - self.window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False, 0
            bucket.append(now)
            return True, max(0, limit - len(bucket))


# ══════════════════════════════════════════════════════════════════════════════
# UsageTracker
# ══════════════════════════════════════════════════════════════════════════════
class UsageTracker:
    """用量追踪 + 计费聚合。

    单例 — 所有调用方共享同一进程内 sliding-window limiter 和 fallback 写盘句柄。
    """

    _instance: Optional["UsageTracker"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._limiter = _SlidingWindowLimiter(window_seconds=3600)
        self._fallback_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "UsageTracker":
        """单例懒加载。"""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── record ────────────────────────────────────────────────────────────
    def record(
        self,
        user_id: str,
        provider_id: str,
        protocol: str,
        kind: str,
        *,
        org_id: str = "",
        model: str = "",
        status: str = "ok",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: Optional[int] = None,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        error_code: str = "",
        error_message: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """写一条 UsageLog, 返回 id (成功) / None (失败)。

        失败模式:
        - DB 不可用 → 写 fallback jsonl, 仍然返回 ``ul_fallback_<id>`` 形式的伪 id (给调用方记录用)。
        - 任何异常 → logger.warning, 不抛 (不能拖垮 AI 主链路)。
        """
        uid = _clean_text(user_id, 60) or "anonymous"
        pid = _clean_text(provider_id, 60) or "unknown"
        proto = _clean_text(protocol, 40) or "unknown"
        k = _clean_text(kind, 20) or "chat"
        st = _clean_text(status, 20) or "ok"

        total = int(total_tokens) if total_tokens is not None else int(prompt_tokens) + int(completion_tokens)
        log_id = _new_id()
        now_dt = _now()
        # ORM 写入用 datetime 对象 (SQLAlchemy + SQLite 需要);
        # fallback jsonl 用 ISO 字符串 (跨语言友好)。
        row_db = {
            "id": log_id,
            "user_id": uid,
            "org_id": _clean_text(org_id, 60),
            "provider_id": pid,
            "protocol": proto,
            "model": _clean_text(model, 240),
            "kind": k,
            "status": st,
            "prompt_tokens": max(0, int(prompt_tokens)),
            "completion_tokens": max(0, int(completion_tokens)),
            "total_tokens": max(0, total),
            "cost_usd": max(0.0, float(cost_usd)),
            "latency_ms": max(0, int(latency_ms)),
            "error_code": _clean_text(error_code, 60),
            "error_message": _clean_text(error_message, 2000),
            "extra": _safe_extra(extra),
            "created_at": now_dt,
        }
        row_json = {**row_db, "created_at": now_dt.isoformat()}

        try:
            from db import SessionLocal as _SessionLocal  # type: ignore
            from models import UsageLog  # type: ignore

            db = _SessionLocal()
            try:
                db.add(UsageLog(**row_db))
                db.commit()
                return log_id
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"UsageTracker DB write failed, fallback jsonl: {e}")
            try:
                with self._fallback_lock:
                    with open(_FALLBACK_LOG, "a", encoding="utf-8") as f:
                        f.write(json.dumps(row_json, ensure_ascii=False) + "\n")
            except Exception as e2:
                logger.error(f"UsageTracker fallback write failed: {e2}")
            return None

    # ── summary ───────────────────────────────────────────────────────────
    def user_summary(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """聚合用户 N 天内的用量 + 计费。

        返回 ``{"user_id", "days", "total_calls", "total_tokens", "total_cost_usd",
        "by_provider": [{provider_id, calls, tokens, cost_usd}],
        "by_kind": [{kind, calls, tokens, cost_usd}],
        "errors": int, "month_to_date_cost_usd": float, "fallback_rows": int}``。

        降级: DB 不可用 → 读 ``usage_fallback.jsonl`` 行内聚合。
        """
        uid = _clean_text(user_id, 60) or "anonymous"
        days_n = max(1, min(365, int(days)))
        cutoff = _now() - timedelta(days=days_n)

        rows: List[Dict[str, Any]] = []
        db_ok = False

        try:
            from db import SessionLocal  # type: ignore
            from models import UsageLog  # type: ignore
            from sqlalchemy import and_  # type: ignore

            db = SessionLocal()
            try:
                q = db.query(UsageLog).filter(
                    and_(UsageLog.user_id == uid, UsageLog.created_at >= cutoff)
                )
                for r in q.all():
                    rows.append({
                        "provider_id": r.provider_id,
                        "kind": r.kind,
                        "status": r.status,
                        "total_tokens": int(r.total_tokens or 0),
                        "cost_usd": float(r.cost_usd or 0.0),
                    })
                db_ok = True
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"UsageTracker.user_summary DB read failed: {e}")

        fallback_count = 0
        if not db_ok:
            rows, fallback_count = _read_fallback_rows(user_id=uid, since_iso=cutoff.isoformat())

        return _aggregate_summary(uid, days_n, rows, fallback_count)

    def org_summary(self, org_id: str, days: int = 30) -> Dict[str, Any]:
        """聚合组织 N 天用量。"""
        oid = _clean_text(org_id, 60) or "unknown"
        days_n = max(1, min(365, int(days)))
        cutoff = _now() - timedelta(days=days_n)

        rows: List[Dict[str, Any]] = []
        db_ok = False

        try:
            from db import SessionLocal  # type: ignore
            from models import UsageLog  # type: ignore
            from sqlalchemy import and_  # type: ignore

            db = SessionLocal()
            try:
                q = db.query(UsageLog).filter(
                    and_(UsageLog.org_id == oid, UsageLog.created_at >= cutoff)
                )
                for r in q.all():
                    rows.append({
                        "provider_id": r.provider_id,
                        "kind": r.kind,
                        "status": r.status,
                        "total_tokens": int(r.total_tokens or 0),
                        "cost_usd": float(r.cost_usd or 0.0),
                        "user_id": r.user_id,
                    })
                db_ok = True
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"UsageTracker.org_summary DB read failed: {e}")

        fallback_count = 0
        if not db_ok:
            rows, fallback_count = _read_fallback_rows(org_id=oid, since_iso=cutoff.isoformat())

        result = _aggregate_summary(oid, days_n, rows, fallback_count)
        # 额外加 unique users
        result["unique_users"] = len({r.get("user_id", "") for r in rows if r.get("user_id")})
        result["scope"] = "org"
        return result

    # ── rate limit ────────────────────────────────────────────────────────
    def check_rate_limit(
        self,
        user_id: str,
        provider_id: str = "*",
        per_hour: Optional[int] = None,
    ) -> Tuple[bool, int]:
        """检查 (user_id, provider_id) 是否超额。

        ``per_hour=None`` → 用环境变量 ``AI_RATE_LIMIT_PER_HOUR``, 默认 1000。
        返回 ``(allowed, remaining)``。
        """
        limit = int(per_hour) if per_hour and per_hour > 0 else int(
            os.environ.get("AI_RATE_LIMIT_PER_HOUR", "1000")
        )
        uid = _clean_text(user_id, 60) or "anonymous"
        pid = _clean_text(provider_id, 60) or "*"
        return self._limiter.hit((uid, pid), limit)


# ══════════════════════════════════════════════════════════════════════════════
# 工具函数 (供 record 内部 + 单元测试用)
# ══════════════════════════════════════════════════════════════════════════════
def _clean_text(value: Any, maxlen: int) -> str:
    return str(value or "").strip()[:maxlen]


def _safe_extra(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        text = json.dumps(value)
        if len(text) > 16 * 1024:
            return {"_truncated": True, "size": len(text)}
        return value
    except Exception:
        return {}


def _read_fallback_rows(
    *,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
    since_iso: str = "",
) -> Tuple[List[Dict[str, Any]], int]:
    """从 ``usage_fallback.jsonl`` 读行, 按 user_id/org_id + 时间过滤。"""
    rows: List[Dict[str, Any]] = []
    fallback_count = 0
    if not _FALLBACK_LOG.exists():
        return rows, fallback_count
    try:
        cutoff_dt = datetime.fromisoformat(since_iso) if since_iso else None
        with open(_FALLBACK_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                fallback_count += 1
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if user_id and r.get("user_id") != user_id:
                    continue
                if org_id and r.get("org_id") != org_id:
                    continue
                if cutoff_dt:
                    try:
                        ts = datetime.fromisoformat(r.get("created_at", ""))
                        if ts < cutoff_dt:
                            continue
                    except Exception:
                        pass
                rows.append(r)
    except Exception as e:
        logger.warning(f"_read_fallback_rows failed: {e}")
    return rows, fallback_count


def _aggregate_summary(
    entity_id: str,
    days: int,
    rows: List[Dict[str, Any]],
    fallback_count: int,
) -> Dict[str, Any]:
    """聚合一组 dict 行 → 摘要 dict。"""
    by_provider: Dict[str, Dict[str, Any]] = {}
    by_kind: Dict[str, Dict[str, Any]] = {}
    total_calls = len(rows)
    total_tokens = 0
    total_cost = 0.0
    errors = 0
    month_start = _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mtd_cost = 0.0

    for r in rows:
        pid = r.get("provider_id", "unknown")
        kind = r.get("kind", "chat")
        status = r.get("status", "ok")
        toks = int(r.get("total_tokens", 0) or 0)
        cost = float(r.get("cost_usd", 0.0) or 0.0)

        bp = by_provider.setdefault(pid, {"provider_id": pid, "calls": 0, "tokens": 0, "cost_usd": 0.0})
        bp["calls"] += 1
        bp["tokens"] += toks
        bp["cost_usd"] = round(bp["cost_usd"] + cost, 6)

        bk = by_kind.setdefault(kind, {"kind": kind, "calls": 0, "tokens": 0, "cost_usd": 0.0})
        bk["calls"] += 1
        bk["tokens"] += toks
        bk["cost_usd"] = round(bk["cost_usd"] + cost, 6)

        total_tokens += toks
        total_cost += cost
        if status == "error":
            errors += 1

        try:
            ts = datetime.fromisoformat(r.get("created_at", ""))
            if ts >= month_start:
                mtd_cost += cost
        except Exception:
            pass

    return {
        "entity_id": entity_id,
        "scope": "user",
        "days": days,
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "errors": errors,
        "month_to_date_cost_usd": round(mtd_cost, 6),
        "by_provider": sorted(by_provider.values(), key=lambda x: -x["cost_usd"]),
        "by_kind": sorted(by_kind.values(), key=lambda x: -x["cost_usd"]),
        "fallback_rows": fallback_count,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 全局单例 + 便捷导入
# ══════════════════════════════════════════════════════════════════════════════
def get_tracker() -> UsageTracker:
    return UsageTracker.instance()


__all__ = [
    "UsageTracker",
    "get_tracker",
]
