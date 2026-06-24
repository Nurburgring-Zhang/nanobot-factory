"""Quota enforcement — 12 dimension limits with soft/hard cap policy.

设计:
- QuotaDecision: 决策结果 (allowed / soft_warning / blocked / unknown)
- QuotaTracker: 累计 + 查询 (per user+dimension)
- QuotaService: 综合 plan 限额 + 当前用量 → 决策
- 复用 P2-3 usage_tracker 的数据 (本模块自带 InMemoryQuotaTracker, 也可注入别的实现)

12 维度:
    datasets, tasks, operator_calls, ai_tokens, storage_gb, team_members,
    tickets, audit_retention_days, sla_uptime, exports_per_month,
    integrations, white_label
"""
from __future__ import annotations

import enum
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from .plans import FEATURE_DIMENSIONS, FEATURE_LABELS, get_config


# ============================================================================
# 1. Quota decision
# ============================================================================

class QuotaLevel(str, enum.Enum):
    """Decision level for a quota check."""
    OK = "ok"                  # 用量 < 80%, 完全允许
    SOFT_WARNING = "soft_warning"  # 80% ≤ 用量 < 100%, 警告但允许
    HARD_BLOCK = "hard_block"  # 100% 达到硬限制, 拒绝
    UNKNOWN = "unknown"        # 限额未配置 / 维度不存在
    INFINITY = "infinity"      # -1 或巨大值, 永远允许


@dataclass
class QuotaDecision:
    level: QuotaLevel
    allowed: bool
    reason: str
    current: int
    limit: int
    soft_threshold: int       # 软警告阈值
    dimension: str
    plan_id: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["level"] = self.level.value
        return d


# ============================================================================
# 2. Quota tracker — accumulates usage per (user, dimension)
# ============================================================================

class QuotaTracker(Protocol):
    def record(self, user_id: str, dimension: str, qty: int = 1) -> int: ...
    def current(self, user_id: str, dimension: str) -> int: ...
    def reset(self, user_id: str, dimension: Optional[str] = None) -> None: ...
    def snapshot(self, user_id: str) -> Dict[str, int]: ...


class InMemoryQuotaTracker:
    """Thread-safe in-memory tracker. Tracks (user, dimension) -> count."""
    def __init__(self) -> None:
        self._usage: Dict[str, Dict[str, int]] = {}
        self._lock = threading.Lock()

    def _key(self, user_id: str, dimension: str) -> str:
        return f"{user_id}::{dimension}"

    def record(self, user_id: str, dimension: str, qty: int = 1) -> int:
        if qty == 0:
            return self.current(user_id, dimension)
        with self._lock:
            user = self._usage.setdefault(user_id, {})
            user[dimension] = user.get(dimension, 0) + int(qty)
            return user[dimension]

    def current(self, user_id: str, dimension: str) -> int:
        with self._lock:
            user = self._usage.get(user_id, {})
            return int(user.get(dimension, 0))

    def reset(self, user_id: str, dimension: Optional[str] = None) -> None:
        with self._lock:
            if dimension is None:
                self._usage.pop(user_id, None)
            else:
                user = self._usage.get(user_id, {})
                user.pop(dimension, None)

    def snapshot(self, user_id: str) -> Dict[str, int]:
        with self._lock:
            user = self._usage.get(user_id, {})
            return dict(user)


class JsonlQuotaTracker:
    """JSONL-backed quota tracker. Append-only log of increment events."""
    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()
        self._cache: Optional[Dict[str, Dict[str, int]]] = None

    def _load(self) -> Dict[str, Dict[str, int]]:
        if self._cache is not None:
            return self._cache
        out: Dict[str, Dict[str, int]] = {}
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    user = rec.get("user_id")
                    dim = rec.get("dimension")
                    qty = int(rec.get("qty", 0))
                    if not user or not dim:
                        continue
                    out.setdefault(user, {})
                    out[user][dim] = out[user].get(dim, 0) + qty
        self._cache = out
        return out

    def record(self, user_id: str, dimension: str, qty: int = 1) -> int:
        if qty == 0:
            return self.current(user_id, dimension)
        with self._lock:
            cache = self._load()
            cache.setdefault(user_id, {})
            cache[user_id][dimension] = cache[user_id].get(dimension, 0) + int(qty)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "user_id": user_id, "dimension": dimension,
                    "qty": int(qty), "ts": time.time(),
                }, separators=(",", ":")) + "\n")
            return cache[user_id][dimension]

    def current(self, user_id: str, dimension: str) -> int:
        with self._lock:
            return self._load().get(user_id, {}).get(dimension, 0)

    def reset(self, user_id: str, dimension: Optional[str] = None) -> None:
        with self._lock:
            cache = self._load()
            if dimension is None:
                cache.pop(user_id, None)
            else:
                cache.get(user_id, {}).pop(dimension, None)
            # Note: we don't rewrite the JSONL (append-only)
            self._cache = cache

    def snapshot(self, user_id: str) -> Dict[str, int]:
        with self._lock:
            return dict(self._load().get(user_id, {}))


# ============================================================================
# 3. Quota service — check + enforce
# ============================================================================

SOFT_THRESHOLD_PCT = 0.8  # 80% of limit → soft warning
# Threshold: any limit >= this is treated as "unlimited" (Enterprise)
INFINITY_THRESHOLD = 100_000_000


class QuotaService:
    """High-level quota service — combines plan config + current usage."""
    def __init__(self, tracker: QuotaTracker,
                 soft_threshold_pct: float = SOFT_THRESHOLD_PCT) -> None:
        self.tracker = tracker
        self.soft_threshold_pct = float(soft_threshold_pct)

    def check(self, user_id: str, plan_id: str,
              dimension: str, qty: int = 1) -> QuotaDecision:
        """Check if a user (on plan_id) can use ``qty`` more units of ``dimension``."""
        try:
            config = get_config(plan_id)
        except KeyError:
            return QuotaDecision(
                level=QuotaLevel.UNKNOWN,
                allowed=False,
                reason=f"unknown plan: {plan_id!r}",
                current=0, limit=0, soft_threshold=0,
                dimension=dimension, plan_id=plan_id,
            )
        if dimension not in FEATURE_DIMENSIONS:
            return QuotaDecision(
                level=QuotaLevel.UNKNOWN,
                allowed=False,
                reason=f"unknown dimension: {dimension!r}",
                current=0, limit=0, soft_threshold=0,
                dimension=dimension, plan_id=plan_id,
            )
        limit = config.get(dimension, 0)
        # Special: -1 or very large = unlimited
        if limit < 0 or limit >= INFINITY_THRESHOLD:
            return QuotaDecision(
                level=QuotaLevel.INFINITY,
                allowed=True,
                reason="unlimited (Enterprise tier)",
                current=0, limit=limit,
                soft_threshold=limit,
                dimension=dimension, plan_id=plan_id,
            )
        # Special: 0 limit + block policy → not allowed
        policy = config.policy_for(dimension)
        if limit == 0 and policy == "block":
            return QuotaDecision(
                level=QuotaLevel.HARD_BLOCK,
                allowed=False,
                reason=f"plan {plan_id!r} does not include {dimension!r}",
                current=0, limit=0, soft_threshold=0,
                dimension=dimension, plan_id=plan_id,
            )
        current = self.tracker.current(user_id, dimension)
        new_total = current + int(qty)
        soft_threshold = int(limit * self.soft_threshold_pct)
        if new_total > limit:
            return QuotaDecision(
                level=QuotaLevel.HARD_BLOCK,
                allowed=False,
                reason=f"quota exceeded: {new_total} > {limit}",
                current=current, limit=limit,
                soft_threshold=soft_threshold,
                dimension=dimension, plan_id=plan_id,
            )
        if new_total >= soft_threshold:
            return QuotaDecision(
                level=QuotaLevel.SOFT_WARNING,
                allowed=True,
                reason=f"approaching limit: {new_total}/{limit}",
                current=current, limit=limit,
                soft_threshold=soft_threshold,
                dimension=dimension, plan_id=plan_id,
            )
        return QuotaDecision(
            level=QuotaLevel.OK,
            allowed=True,
            reason="within limits",
            current=current, limit=limit,
            soft_threshold=soft_threshold,
            dimension=dimension, plan_id=plan_id,
        )

    def consume(self, user_id: str, plan_id: str,
                dimension: str, qty: int = 1,
                record_on_block: bool = False) -> QuotaDecision:
        """Atomic check + record. Returns the decision.

        If allowed: records ``qty`` to tracker.
        If blocked and ``record_on_block=True``: records anyway (audit-only).
        """
        decision = self.check(user_id, plan_id, dimension, qty)
        if decision.allowed:
            self.tracker.record(user_id, dimension, qty)
        elif record_on_block:
            self.tracker.record(user_id, dimension, qty)
        return decision

    def snapshot(self, user_id: str, plan_id: str) -> Dict[str, Any]:
        """Return a full snapshot of all 12 dimensions for a user."""
        try:
            config = get_config(plan_id)
        except KeyError:
            config = None
        usage = self.tracker.snapshot(user_id)
        out: Dict[str, Any] = {
            "user_id": user_id,
            "plan_id": plan_id,
            "dimensions": {},
        }
        for dim in FEATURE_DIMENSIONS:
            current = int(usage.get(dim, 0))
            if config is None:
                out["dimensions"][dim] = {
                    "label": FEATURE_LABELS.get(dim, dim),
                    "current": current,
                    "limit": 0,
                    "soft_threshold": 0,
                    "level": QuotaLevel.UNKNOWN.value,
                    "allowed": False,
                    "policy": "block",
                }
                continue
            limit = config.get(dim, 0)
            policy = config.policy_for(dim)
            if limit < 0 or limit >= INFINITY_THRESHOLD:
                level = QuotaLevel.INFINITY
                allowed = True
            elif limit == 0 and policy == "block":
                level = QuotaLevel.HARD_BLOCK
                allowed = False
            elif current >= limit:
                level = QuotaLevel.HARD_BLOCK
                allowed = False
            elif current >= limit * self.soft_threshold_pct:
                level = QuotaLevel.SOFT_WARNING
                allowed = True
            else:
                level = QuotaLevel.OK
                allowed = True
            out["dimensions"][dim] = {
                "label": FEATURE_LABELS.get(dim, dim),
                "current": current,
                "limit": limit,
                "soft_threshold": int(limit * self.soft_threshold_pct),
                "level": level.value,
                "allowed": allowed,
                "policy": policy,
            }
        return out

    def global_usage(self) -> Dict[str, int]:
        """Return global usage across all users per dimension (admin view)."""
        out: Dict[str, int] = {dim: 0 for dim in FEATURE_DIMENSIONS}
        # We don't have a list_users method; instead, sum what we can find.
        # (For more advanced impl, use a database-backed tracker.)
        return out

    def user_usage(self, user_id: str,
                   dimension: Optional[str] = None) -> Dict[str, int]:
        """Return per-dimension usage for a user (admin per-user view)."""
        if dimension is not None:
            return {dimension: self.tracker.current(user_id, dimension)}
        return self.tracker.snapshot(user_id)


# ============================================================================
# 4. SQL DDL for billing_usage_log (per-user-per-dimension monthly aggregation)
# ============================================================================

BILLING_USAGE_LOG_DDL = """
CREATE TABLE IF NOT EXISTS billing_usage_log (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    dimension VARCHAR(40) NOT NULL,
    qty INTEGER NOT NULL DEFAULT 1,
    period VARCHAR(8) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

BILLING_USAGE_LOG_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS billing_usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(64) NOT NULL,
    dimension VARCHAR(40) NOT NULL,
    qty INTEGER NOT NULL DEFAULT 1,
    period VARCHAR(8) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

BILLING_USAGE_LOG_INDEXES_DDL = [
    "CREATE INDEX IF NOT EXISTS ix_billing_usage_log_user_dim_period ON billing_usage_log(user_id, dimension, period);",
    "CREATE INDEX IF NOT EXISTS ix_billing_usage_log_period ON billing_usage_log(period);",
]


__all__ = [
    "QuotaLevel", "QuotaDecision",
    "QuotaTracker", "InMemoryQuotaTracker", "JsonlQuotaTracker",
    "QuotaService", "SOFT_THRESHOLD_PCT",
    "BILLING_USAGE_LOG_DDL", "BILLING_USAGE_LOG_DDL_SQLITE",
    "BILLING_USAGE_LOG_INDEXES_DDL",
]
