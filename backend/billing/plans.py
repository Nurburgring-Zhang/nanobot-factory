"""Pricing plan definitions for nanobot-factory.

5 standard tiers with 12 features each. Plan is the catalog
object; PlanConfig is a runtime instance (limits/prices per period).

Design:
- Pure stdlib (no Pydantic / no DB) — kept as dataclass for stable import surface.
- 5 tiers: Free / Starter / Pro / Business / Enterprise
- 12 feature dimensions tracked by quotas.py: assets, tasks, ops, ai_tokens, storage,
  users, team, tickets, audit, sla, exports, integrations, white_label.
- All limits in plan config are per-period (monthly for most, project-lifetime for assets).
- Prices in CNY (¥) and USD ($), stored in cents (CNY: 分, USD: ¢) to avoid float drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


# ============================================================================
# Feature dimension constants — single source of truth, used by quotas.py
# ============================================================================

# 12 dimensions: keys match what quotas.py expects. Values are human labels.
FEATURE_DIMENSIONS: List[str] = [
    "datasets",          # dataset count (per project lifetime)
    "tasks",             # concurrent task count
    "operator_calls",    # data ops per month
    "ai_tokens",         # AI provider tokens per month
    "storage_gb",        # storage in GB (perpetual)
    "team_members",      # team seats
    "tickets",           # support tickets per month
    "audit_retention_days",  # audit log retention in days
    "sla_uptime",        # SLA in % (e.g. 99.9 = 99.9%)
    "exports_per_month", # export operations per month
    "integrations",      # third-party integrations count
    "white_label",       # 0/1 boolean flag
]

# Map dimension -> human description (used in API responses / UI)
FEATURE_LABELS: Dict[str, str] = {
    "datasets": "数据集数量",
    "tasks": "并发任务数",
    "operator_calls": "算子调用/月",
    "ai_tokens": "AI Tokens/月",
    "storage_gb": "存储空间 (GB)",
    "team_members": "团队成员数",
    "tickets": "技术支持工单/月",
    "audit_retention_days": "审计日志保留 (天)",
    "sla_uptime": "SLA 可用性",
    "exports_per_month": "导出次数/月",
    "integrations": "集成对接数",
    "white_label": "白标定制",
}

assert len(FEATURE_DIMENSIONS) == 12, "must keep 12 features per spec"


# ============================================================================
# Plan / PlanConfig / PlanTier
# ============================================================================

@dataclass(frozen=True)
class Plan:
    """Static plan catalog entry."""
    plan_id: str           # "free" / "starter" / "pro" / "business" / "enterprise"
    name: str              # "Free" / "Starter" / "Pro" / "Business" / "Enterprise"
    tier: str              # "free" | "starter" | "pro" | "business" | "enterprise"
    description: str
    monthly_price_cny: int  # cents (分) — 0 for free
    monthly_price_usd: int  # cents (¢)
    annual_price_cny: int   # annual price in cents (分)
    annual_price_usd: int   # annual price in cents (¢)
    is_custom: bool = False  # True for Enterprise (contact sales)


@dataclass(frozen=True)
class PlanConfig:
    """Runtime configuration for a plan — limits per feature dimension."""
    plan_id: str
    # 限额字典: dim -> limit (int). For free plan, 0 means N/A.
    limits: Dict[str, int]
    # 额外能力 (超出限额后: "block" 拒绝, "metered" 走用量计费, "soft" 警告不阻)
    overflow_policy: Dict[str, str] = field(default_factory=dict)
    # 计费周期: "monthly" | "yearly" | "custom"
    billing_period: str = "monthly"

    def get(self, dimension: str, default: int = 0) -> int:
        return int(self.limits.get(dimension, default))

    def policy_for(self, dimension: str) -> str:
        return self.overflow_policy.get(dimension, "block")


# ============================================================================
# Plan catalog (5 plans)
# ============================================================================

PLAN_CATALOG: List[Plan] = [
    Plan(
        plan_id="free",
        name="Free",
        tier="free",
        description="个人体验, 永久免费",
        monthly_price_cny=0,
        monthly_price_usd=0,
        annual_price_cny=0,
        annual_price_usd=0,
    ),
    Plan(
        plan_id="starter",
        name="Starter",
        tier="starter",
        description="适合个人开发者 / 小团队",
        monthly_price_cny=2900,        # ¥29
        monthly_price_usd=2900,        # $29
        annual_price_cny=29000,        # ¥290/年 (省 ¥58)
        annual_price_usd=29000,        # $290/年
    ),
    Plan(
        plan_id="pro",
        name="Pro",
        tier="pro",
        description="适合中小团队, 含 AI tokens + SLA",
        monthly_price_cny=9900,        # ¥99
        monthly_price_usd=9900,        # $99
        annual_price_cny=99000,        # ¥990/年
        annual_price_usd=99000,        # $990/年
    ),
    Plan(
        plan_id="business",
        name="Business",
        tier="business",
        description="中大型团队, 高额度 + 工单 + SLA 99.9%",
        monthly_price_cny=29900,       # ¥299
        monthly_price_usd=29900,       # $299
        annual_price_cny=299000,       # ¥2990/年
        annual_price_usd=299000,       # $2990/年
    ),
    Plan(
        plan_id="enterprise",
        name="Enterprise",
        tier="enterprise",
        description="定制方案, 含白标 + 私有化 + 定制 SLA",
        monthly_price_cny=0,           # 定制报价
        monthly_price_usd=0,
        annual_price_cny=0,
        annual_price_usd=0,
        is_custom=True,
    ),
]


# ============================================================================
# Plan configs (5 limit tables)
# ============================================================================

# Helper: monthly/quarterly/annual limit templates
def _starter_limits() -> Dict[str, int]:
    return {
        "datasets": 10,
        "tasks": 5,
        "operator_calls": 10_000,
        "ai_tokens": 100_000,
        "storage_gb": 10,
        "team_members": 3,
        "tickets": 5,
        "audit_retention_days": 30,
        "sla_uptime": 99,         # 99% (公告)
        "exports_per_month": 20,
        "integrations": 2,
        "white_label": 0,
    }


def _pro_limits() -> Dict[str, int]:
    return {
        "datasets": 100,
        "tasks": 20,
        "operator_calls": 100_000,
        "ai_tokens": 1_000_000,
        "storage_gb": 100,
        "team_members": 10,
        "tickets": 50,
        "audit_retention_days": 90,
        "sla_uptime": 995,         # 99.5%
        "exports_per_month": 200,
        "integrations": 5,
        "white_label": 0,
    }


def _business_limits() -> Dict[str, int]:
    return {
        "datasets": 1000,
        "tasks": 100,
        "operator_calls": 1_000_000,
        "ai_tokens": 10_000_000,
        "storage_gb": 1000,
        "team_members": 50,
        "tickets": 200,
        "audit_retention_days": 365,
        "sla_uptime": 999,         # 99.9%
        "exports_per_month": 2000,
        "integrations": 20,
        "white_label": 1,
    }


def _enterprise_limits() -> Dict[str, int]:
    # 全部用 INFINITY_THRESHOLD (100M) 表示无限制 (quota service 视作 INFINITY)
    return {
        "datasets": 100_000_000,        # 实际不限制
        "tasks": 100_000_000,
        "operator_calls": 100_000_000,
        "ai_tokens": 100_000_000,
        "storage_gb": 100_000_000,
        "team_members": 100_000_000,
        "tickets": 100_000_000,
        "audit_retention_days": 100_000_000,  # 10 年
        "sla_uptime": 9999,         # 99.99% (具体值, 非限额)
        "exports_per_month": 100_000_000,
        "integrations": 100_000_000,
        "white_label": 1,
    }


PLAN_CONFIGS: Dict[str, PlanConfig] = {
    "free": PlanConfig(
        plan_id="free",
        limits={
            "datasets": 3,
            "tasks": 1,
            "operator_calls": 1_000,
            "ai_tokens": 10_000,
            "storage_gb": 1,
            "team_members": 1,
            "tickets": 0,
            "audit_retention_days": 7,
            "sla_uptime": 0,         # 无 SLA
            "exports_per_month": 5,
            "integrations": 0,
            "white_label": 0,
        },
        overflow_policy={k: "block" for k in FEATURE_DIMENSIONS},
    ),
    "starter": PlanConfig(
        plan_id="starter",
        limits=_starter_limits(),
        overflow_policy={
            "operator_calls": "metered",  # 超额按用量计费
            "ai_tokens": "metered",
            **{k: "block" for k in FEATURE_DIMENSIONS if k not in ("operator_calls", "ai_tokens")},
        },
    ),
    "pro": PlanConfig(
        plan_id="pro",
        limits=_pro_limits(),
        overflow_policy={
            "operator_calls": "metered",
            "ai_tokens": "metered",
            "storage_gb": "soft",       # 警告但不阻断
            **{k: "block" for k in FEATURE_DIMENSIONS
               if k not in ("operator_calls", "ai_tokens", "storage_gb")},
        },
    ),
    "business": PlanConfig(
        plan_id="business",
        limits=_business_limits(),
        overflow_policy={
            "operator_calls": "metered",
            "ai_tokens": "metered",
            "storage_gb": "soft",
            "team_members": "soft",     # 警告
            **{k: "block" for k in FEATURE_DIMENSIONS
               if k not in ("operator_calls", "ai_tokens", "storage_gb", "team_members")},
        },
    ),
    "enterprise": PlanConfig(
        plan_id="enterprise",
        limits=_enterprise_limits(),
        overflow_policy={k: "soft" for k in FEATURE_DIMENSIONS},  # 全部警告不阻
    ),
}


# ============================================================================
# Helpers
# ============================================================================

def get_plan(plan_id: str) -> Plan:
    """Lookup plan by id. Raises KeyError if not found."""
    for p in PLAN_CATALOG:
        if p.plan_id == plan_id:
            return p
    raise KeyError(f"unknown plan_id: {plan_id!r}")


def get_config(plan_id: str) -> PlanConfig:
    """Lookup plan config. Raises KeyError if not found."""
    if plan_id not in PLAN_CONFIGS:
        raise KeyError(f"unknown plan_id: {plan_id!r}")
    return PLAN_CONFIGS[plan_id]


def list_plans() -> List[Plan]:
    """Return all 5 plans in catalog."""
    return list(PLAN_CATALOG)


def get_plan_with_config(plan_id: str) -> Dict[str, object]:
    """Convenience: plan + its config as dict (for API responses)."""
    p = get_plan(plan_id)
    c = get_config(plan_id)
    return {
        "plan_id": p.plan_id,
        "name": p.name,
        "tier": p.tier,
        "description": p.description,
        "monthly_price_cny": p.monthly_price_cny,
        "monthly_price_usd": p.monthly_price_usd,
        "annual_price_cny": p.annual_price_cny,
        "annual_price_usd": p.annual_price_usd,
        "is_custom": p.is_custom,
        "limits": dict(c.limits),
        "overflow_policy": dict(c.overflow_policy),
        "billing_period": c.billing_period,
    }


def tier_rank(plan_id: str) -> int:
    """Return tier rank for upgrade/downgrade comparison. Higher = more capable."""
    rank = {
        "free": 0,
        "starter": 1,
        "pro": 2,
        "business": 3,
        "enterprise": 4,
    }
    if plan_id not in rank:
        raise KeyError(f"unknown plan_id: {plan_id!r}")
    return rank[plan_id]


def is_upgrade(from_plan: str, to_plan: str) -> bool:
    """True if to_plan is a higher tier than from_plan."""
    return tier_rank(to_plan) > tier_rank(from_plan)


def is_downgrade(from_plan: str, to_plan: str) -> bool:
    return tier_rank(to_plan) < tier_rank(from_plan)


def price_for(plan_id: str, period: str = "monthly",
              currency: str = "usd") -> int:
    """Return price in cents for a plan+period+currency."""
    p = get_plan(plan_id)
    period = period.lower()
    currency = currency.lower()
    if period == "monthly":
        return p.monthly_price_cny if currency == "cny" else p.monthly_price_usd
    if period == "yearly" or period == "annual":
        return p.annual_price_cny if currency == "cny" else p.annual_price_usd
    raise ValueError(f"unsupported period: {period!r}")


# ============================================================================
# Seed data — for tests / first-run
# ============================================================================

SEED_PLANS: List[Dict[str, object]] = [get_plan_with_config(p.plan_id) for p in PLAN_CATALOG]


__all__ = [
    "FEATURE_DIMENSIONS", "FEATURE_LABELS",
    "Plan", "PlanConfig", "PlanTier",  # PlanTier is a type-alias
    "PLAN_CATALOG", "PLAN_CONFIGS", "SEED_PLANS",
    "get_plan", "get_config", "list_plans", "get_plan_with_config",
    "tier_rank", "is_upgrade", "is_downgrade", "price_for",
]


# PlanTier is a type alias / stand-in (for spec compatibility; real tier is str)
PlanTier = str
