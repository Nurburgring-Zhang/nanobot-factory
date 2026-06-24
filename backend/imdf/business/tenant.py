"""Tenant management — isolation + quotas (R10.5-Worker-2)

多租户隔离:
- Tenant:  id / name / tier / created_at / enabled
- Quota:   hard / soft / audit 三档
    - hard: 严格上限, 超过即拒绝
    - soft: 警告阈值, 超过返回 warn flag, 不拒绝
    - audit: 仅审计, 用于事后审计
- TenantRegistry: CRUD + lookup + 配额检查
- 隔离: tenant_id 在 UsageMeter / AuditLog / 数据导出时均强制传入

设计:
- 内存 + 可选 JSON 文件持久化
- 配额按 metric 维度 (e.g. api_calls, storage_gb)
"""
from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional


# ============================================================================
# 1. 数据类
# ============================================================================

@dataclass
class Quota:
    """单个 metric 的三档配额."""
    hard: int = 0           # 硬上限, 0 = 不限
    soft: int = 0           # 软警告, 0 = 不限
    audit: int = 0          # 审计阈值, 0 = 不限
    unit: str = "count"     # 单位标签

    def to_dict(self) -> Dict[str, object]:
        return {"hard": self.hard, "soft": self.soft, "audit": self.audit, "unit": self.unit}


@dataclass
class Tenant:
    tenant_id: str
    name: str
    tier: str = "free"
    enabled: bool = True
    created_at: float = field(default_factory=lambda: time.time())
    metadata: Dict[str, str] = field(default_factory=dict)
    # metric -> Quota (e.g. {"api_calls": Quota(hard=10000, soft=8000, audit=5000)})
    quotas: Dict[str, Quota] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "tier": self.tier,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
            "quotas": {k: v.to_dict() for k, v in self.quotas.items()},
        }


@dataclass
class QuotaDecision:
    """配额检查结果."""
    allowed: bool
    reason: str = ""        # 拒因 / 警告说明
    level: str = "ok"       # ok / soft_warn / audit_warn / hard_block
    current: int = 0
    limit: int = 0


# ============================================================================
# 2. Registry / 持久化
# ============================================================================

class TenantRegistry:
    """租户注册中心 — 内存 + JSON 文件."""
    def __init__(self, storage_path: Optional[str | os.PathLike] = None):
        self._tenants: Dict[str, Tenant] = {}
        self._lock = threading.RLock()
        self._path = Path(storage_path) if storage_path else None
        if self._path and self._path.exists():
            self._load()

    # ── CRUD ──────────────────────────────────────────────────────────
    def create(self, tenant_id: str, name: str, tier: str = "free",
               quotas: Optional[Dict[str, Quota]] = None,
               metadata: Optional[Dict[str, str]] = None) -> Tenant:
        with self._lock:
            if not tenant_id or not isinstance(tenant_id, str):
                raise ValueError("tenant_id must be non-empty string")
            if not _TENANT_ID_RE.match(tenant_id):
                raise ValueError(f"invalid tenant_id {tenant_id!r}: must match {_TENANT_ID_RE.pattern}")
            if tenant_id in self._tenants:
                raise ValueError(f"tenant {tenant_id!r} already exists")
            t = Tenant(
                tenant_id=tenant_id,
                name=name,
                tier=tier,
                quotas=dict(quotas or {}),
                metadata=dict(metadata or {}),
            )
            self._tenants[tenant_id] = t
            self._persist()
            return t

    def get(self, tenant_id: str) -> Optional[Tenant]:
        with self._lock:
            return self._tenants.get(tenant_id)

    def get_or_404(self, tenant_id: str) -> Tenant:
        t = self.get(tenant_id)
        if t is None:
            raise KeyError(f"tenant not found: {tenant_id!r}")
        return t

    def list(self) -> List[Tenant]:
        with self._lock:
            return list(self._tenants.values())

    def disable(self, tenant_id: str) -> None:
        with self._lock:
            t = self.get_or_404(tenant_id)
            t.enabled = False
            self._persist()

    def enable(self, tenant_id: str) -> None:
        with self._lock:
            t = self.get_or_404(tenant_id)
            t.enabled = True
            self._persist()

    def delete(self, tenant_id: str) -> bool:
        with self._lock:
            if tenant_id in self._tenants:
                del self._tenants[tenant_id]
                self._persist()
                return True
            return False

    def set_quota(self, tenant_id: str, metric: str, quota: Quota) -> None:
        with self._lock:
            t = self.get_or_404(tenant_id)
            t.quotas[metric] = quota
            self._persist()

    def update_quota(self, tenant_id: str, metric: str,
                     hard: Optional[int] = None, soft: Optional[int] = None,
                     audit: Optional[int] = None, unit: Optional[str] = None) -> Quota:
        with self._lock:
            t = self.get_or_404(tenant_id)
            cur = t.quotas.get(metric, Quota())
            new = Quota(
                hard=hard if hard is not None else cur.hard,
                soft=soft if soft is not None else cur.soft,
                audit=audit if audit is not None else cur.audit,
                unit=unit if unit is not None else cur.unit,
            )
            t.quotas[metric] = new
            self._persist()
            return new

    # ── 配额检查 ──────────────────────────────────────────────────────
    def check_quota(self, tenant_id: str, metric: str, current: int) -> QuotaDecision:
        """返回: ok / soft_warn / audit_warn / hard_block."""
        with self._lock:
            t = self.get(tenant_id)
            if t is None:
                return QuotaDecision(False, reason=f"tenant not found: {tenant_id!r}",
                                     level="hard_block", current=current)
            if not t.enabled:
                return QuotaDecision(False, reason=f"tenant {tenant_id!r} is disabled",
                                     level="hard_block", current=current)
            q = t.quotas.get(metric)
            if q is None:
                return QuotaDecision(True, level="ok", current=current, limit=0)
            # 优先 hard
            if q.hard > 0 and current >= q.hard:
                return QuotaDecision(False,
                                     reason=f"hard quota exceeded: {current} >= {q.hard}",
                                     level="hard_block", current=current, limit=q.hard)
            # soft 警告 (不阻断)
            if q.soft > 0 and current >= q.soft:
                return QuotaDecision(True,
                                     reason=f"soft quota warning: {current} >= {q.soft}",
                                     level="soft_warn", current=current, limit=q.soft)
            if q.audit > 0 and current >= q.audit:
                return QuotaDecision(True,
                                     reason=f"audit quota reached: {current} >= {q.audit}",
                                     level="audit_warn", current=current, limit=q.audit)
            return QuotaDecision(True, level="ok", current=current,
                                 limit=q.hard if q.hard > 0 else 0)

    # ── 持久化 ────────────────────────────────────────────────────────
    def _persist(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {tid: t.to_dict() for tid, t in self._tenants.items()}
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        try:
            with self._path.open("r", encoding="utf-8") as f:  # type: ignore[union-attr]
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return
        for tid, td in data.items():
            quotas = {
                k: Quota(hard=v.get("hard", 0), soft=v.get("soft", 0),
                         audit=v.get("audit", 0), unit=v.get("unit", "count"))
                for k, v in (td.get("quotas") or {}).items()
            }
            self._tenants[tid] = Tenant(
                tenant_id=tid,
                name=td["name"],
                tier=td.get("tier", "free"),
                enabled=td.get("enabled", True),
                created_at=td.get("created_at", time.time()),
                metadata=td.get("metadata", {}),
                quotas=quotas,
            )

    # ── 导出 ──────────────────────────────────────────────────────────
    def export_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w.writerow(["tenant_id", "name", "tier", "enabled", "created_at_iso", "quotas_json"])
        for t in self.list():
            w.writerow([
                t.tenant_id,
                t.name,
                t.tier,
                "true" if t.enabled else "false",
                datetime.fromtimestamp(t.created_at, tz=timezone.utc).isoformat(),
                json.dumps({k: v.to_dict() for k, v in t.quotas.items()},
                           ensure_ascii=False, separators=(",", ":")),
            ])
        return buf.getvalue()


# ============================================================================
# 3. Tenant isolation helper
# ============================================================================

# tenant_id: 字母/数字/下划线/连字符, 长度 1-64
import re as _re
_TENANT_ID_RE = _re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def assert_tenant_isolation(tenant_id: str, resource_tenant_id: str) -> None:
    """检查 resource_tenant_id 是否归属 tenant_id. 不一致 → 拒绝."""
    if not tenant_id or not resource_tenant_id:
        raise PermissionError("missing tenant_id for isolation check")
    if tenant_id != resource_tenant_id:
        raise PermissionError(
            f"cross-tenant access denied: actor={tenant_id!r} resource={resource_tenant_id!r}"
        )


__all__ = [
    "Tenant", "Quota", "QuotaDecision",
    "TenantRegistry", "assert_tenant_isolation",
]