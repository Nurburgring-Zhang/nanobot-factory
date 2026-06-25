"""
P4-10-W2: 客户关系管理 (CRM)
- 客户分级: 个人 / SMB / 中型 / 大型 / 战略
- 跟进记录: 沟通/合同/付款/投诉
- 1 客户 1 manager (1:1)
- 多联系人 (采购/技术/财务/法务)
"""
import os
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# P1-1: Lead scoring — tier/followup/recency/LTV 量化打分
# ---------------------------------------------------------------------------
# 各 tier 基础分 (战略 > 大型 > 中型 > SMB > 个人)
TIER_BASE_SCORE = {
    "individual": 10,
    "smb": 25,
    "mid_market": 50,
    "large": 75,
    "strategic": 100,
}

# 行业加分 (高客单价行业: 金融/政企/制造)
INDUSTRY_BONUS = {
    "金融": 15,
    "政企": 12,
    "制造": 10,
    "互联网/科技": 8,
    "汽车/出行": 8,
    "医疗": 7,
    "教育": 5,
    "零售/电商": 5,
    "媒体/广告": 4,
    "游戏": 3,
    "其他": 0,
}

# 公司规模加分 (员工数越多越值钱)
SIZE_BONUS = {
    "1-10": 0,
    "11-50": 3,
    "51-200": 8,
    "201-1000": 15,
    "1000+": 25,
}

# 跟进类型权重
FOLLOWUP_TYPE_WEIGHT = {
    "contract": 10,    # 合同相关最有价值
    "payment": 8,      # 付款相关
    "communication": 3,  # 普通沟通
    "complaint": 2,    # 投诉 (有信号但偏负面)
    "other": 1,
}

# 客户活跃度窗口 (7/30/90 天)
ACTIVITY_WINDOWS_DAYS = [7, 30, 90]


def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def compute_lead_score(
    tier: str,
    industry: str,
    size: str,
    followups: List[Dict[str, Any]],
    lifetime_value: float,
    updated_at: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """计算 Lead Score (0-200 分).
    
    公式 (加权):
        score = tier_base  * 1.0
              + industry_bonus * 0.8
              + size_bonus   * 0.6
              + followup_activity_score (0-40)
              + ltv_score (0-20, 对数曲线)
              + recency_bonus (0-15)
    
    grade:
        A: ≥ 130  — 高价值目标, 优先分配资深销售
        B: 90-129 — 优质潜客, 正常跟进
        C: 50-89  — 一般潜客, 培育中
        D: < 50   — 低优先级, 自动化跟进
    """
    if now is None:
        now = datetime.utcnow()
    # 基础分
    base = TIER_BASE_SCORE.get(tier, 10)
    ind_b = INDUSTRY_BONUS.get(industry, 0)
    size_b = SIZE_BONUS.get(size, 0)
    # 跟进活跃度 (类型权重 + 近期衰减)
    fu_score = 0.0
    for fu in followups:
        weight = FOLLOWUP_TYPE_WEIGHT.get(fu.get("type", "other"), 1)
        fu_at = _parse_dt(fu.get("at", ""))
        if fu_at:
            days_ago = (now - fu_at).total_seconds() / 86400
            # 近期跟进权重更高 (90 天内满权重, 之后线性衰减)
            if days_ago <= 90:
                fu_score += weight
            else:
                fu_score += weight * max(0.2, 1.0 - (days_ago - 90) / 365)
        else:
            fu_score += weight * 0.5
    fu_score = min(fu_score, 40)
    # LTV 对数曲线 (¥1万→3分, ¥10万→12分, ¥100万→20分, 封顶 20)
    import math
    ltv_score = min(20.0, math.log10(max(1.0, lifetime_value) / 100.0) * 6.0) if lifetime_value > 0 else 0
    ltv_score = max(0.0, ltv_score)
    # 最近活跃度加分 (updated_at / 最后跟进)
    recency_bonus = 0.0
    up_at = _parse_dt(updated_at or "")
    if up_at:
        days_since = (now - up_at).total_seconds() / 86400
        if days_since <= 7:
            recency_bonus = 15
        elif days_since <= 30:
            recency_bonus = 10
        elif days_since <= 90:
            recency_bonus = 5
    # 总分 (封顶 200)
    raw = base + ind_b * 0.8 + size_b * 0.6 + fu_score + ltv_score + recency_bonus
    score = round(min(200.0, max(0.0, raw)), 2)
    # 评级
    if score >= 130:
        grade = "A"
    elif score >= 90:
        grade = "B"
    elif score >= 50:
        grade = "C"
    else:
        grade = "D"
    return {
        "score": score,
        "grade": grade,
        "breakdown": {
            "tier_base": base,
            "industry_bonus": round(ind_b * 0.8, 2),
            "size_bonus": round(size_b * 0.6, 2),
            "followup_activity": round(fu_score, 2),
            "ltv_score": round(ltv_score, 2),
            "recency_bonus": recency_bonus,
        },
    }


def _customer_to_score_input(c: "Customer") -> Dict[str, Any]:
    return {
        "tier": c.tier,
        "industry": c.industry,
        "size": c.size,
        "followups": c.followups,
        "lifetime_value": c.lifetime_value,
        "updated_at": c.updated_at,
    }


def recompute_customer_score(c: "Customer") -> Dict[str, Any]:
    """刷新单个客户 lead score, 写入实例. 返回 score 详情."""
    res = compute_lead_score(**_customer_to_score_input(c))
    c.lead_score = res["score"]
    c.lead_grade = res["grade"]
    c.lead_score_breakdown = res["breakdown"]
    c.lead_score_updated_at = datetime.utcnow().isoformat()
    return res


def recompute_all_scores() -> int:
    """全局重算所有客户 lead score. 返回处理的客户数."""
    n = 0
    for c in _CUSTOMERS.values():
        recompute_customer_score(c)
        n += 1
    return n


def get_top_leads(limit: int = 20, grade: Optional[str] = None) -> List["Customer"]:
    """按 lead score 倒序返回 Top 客户. 可选按 grade 过滤."""
    items = list(_CUSTOMERS.values())
    if grade:
        items = [c for c in items if c.lead_grade == grade]
    items.sort(key=lambda c: c.lead_score, reverse=True)
    return items[:limit]


def get_lead_stats() -> Dict[str, Any]:
    """Lead Score 全局统计 (A/B/C/D 分布, 平均分, Top 行业)."""
    by_grade: Dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    by_industry: Dict[str, int] = {}
    total = 0
    score_sum = 0.0
    for c in _CUSTOMERS.values():
        if c.lead_grade in by_grade:
            by_grade[c.lead_grade] += 1
        by_industry[c.industry] = by_industry.get(c.industry, 0) + 1
        total += 1
        score_sum += c.lead_score
    return {
        "total_customers": total,
        "avg_lead_score": round(score_sum / total, 2) if total else 0.0,
        "by_grade": by_grade,
        "by_industry": by_industry,
    }

# 客户分级
TIERS = ["individual", "smb", "mid_market", "large", "strategic"]
TIER_LABELS = {
    "individual": "个人",
    "smb": "SMB (小型企业)",
    "mid_market": "中型企业",
    "large": "大型企业",
    "strategic": "战略客户",
}
INDUSTRIES = [
    "互联网/科技", "金融", "教育", "医疗", "零售/电商",
    "制造", "政企", "媒体/广告", "汽车/出行", "游戏", "其他",
]
SIZES = ["1-10", "11-50", "51-200", "201-1000", "1000+"]
FOLLOWUP_TYPES = ["communication", "contract", "payment", "complaint", "other"]
FOLLOWUP_LABELS = {
    "communication": "沟通",
    "contract": "合同",
    "payment": "付款",
    "complaint": "投诉",
    "other": "其他",
}
CONTACT_ROLES = ["procurement", "technical", "finance", "legal", "executive", "other"]
CONTACT_ROLE_LABELS = {
    "procurement": "采购",
    "technical": "技术",
    "finance": "财务",
    "legal": "法务",
    "executive": "高管",
    "other": "其他",
}


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------
class Customer:
    def __init__(
        self,
        company_name: str,
        contact_name: str,
        email: str,
        phone: str = "",
        industry: str = "其他",
        size: str = "1-10",
        tier: str = "individual",
        tags: Optional[List[str]] = None,
        manager_id: Optional[str] = None,
    ):
        self.customer_id = f"CUS-{uuid.uuid4().hex[:8].upper()}"
        self.company_name = company_name
        self.contact_name = contact_name
        self.email = email
        self.phone = phone
        self.industry = industry
        self.size = size
        self.tier = tier
        self.tags = tags or []
        self.manager_id = manager_id  # 1 客户 1 manager
        self.followups: List[Dict[str, Any]] = []
        self.created_at = datetime.utcnow().isoformat()
        self.updated_at = self.created_at
        self.lifetime_value: float = 0.0  # 累计消费
        self.status = "active"  # active / churned / prospect
        # P1-1: Lead scoring
        self.lead_score: float = 0.0
        self.lead_grade: str = "D"
        self.lead_score_breakdown: Dict[str, float] = {}
        self.lead_score_updated_at: Optional[str] = None

    def add_followup(self, followup_type: str, content: str, by: str = "system") -> Dict[str, Any]:
        if followup_type not in FOLLOWUP_TYPES:
            raise ValueError(f"unknown followup_type: {followup_type}")
        record = {
            "followup_id": f"FU-{uuid.uuid4().hex[:8].upper()}",
            "type": followup_type,
            "content": content,
            "by": by,
            "at": datetime.utcnow().isoformat(),
        }
        self.followups.append(record)
        self.updated_at = record["at"]
        return record

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "company_name": self.company_name,
            "contact_name": self.contact_name,
            "email": self.email,
            "phone": self.phone,
            "industry": self.industry,
            "size": self.size,
            "tier": self.tier,
            "tier_label": TIER_LABELS.get(self.tier, self.tier),
            "tags": self.tags,
            "manager_id": self.manager_id,
            "followups": self.followups,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "lifetime_value": self.lifetime_value,
            "status": self.status,
            "lead_score": self.lead_score,
            "lead_grade": self.lead_grade,
            "lead_score_breakdown": self.lead_score_breakdown,
            "lead_score_updated_at": self.lead_score_updated_at,
        }


_CUSTOMERS: Dict[str, Customer] = {}


def create_customer(**kwargs) -> Customer:
    c = Customer(**kwargs)
    if c.tier not in TIERS:
        raise ValueError(f"invalid tier: {c.tier}. valid: {TIERS}")
    _CUSTOMERS[c.customer_id] = c
    return c


def get_customer(customer_id: str) -> Optional[Customer]:
    return _CUSTOMERS.get(customer_id)


def list_customers(
    tier: Optional[str] = None,
    industry: Optional[str] = None,
    manager_id: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Customer]:
    items = list(_CUSTOMERS.values())
    if tier:
        items = [c for c in items if c.tier == tier]
    if industry:
        items = [c for c in items if c.industry == industry]
    if manager_id:
        items = [c for c in items if c.manager_id == manager_id]
    if tag:
        items = [c for c in items if tag in c.tags]
    if search:
        s = search.lower()
        items = [c for c in items if s in c.company_name.lower() or s in c.contact_name.lower() or s in c.email.lower()]
    return items


def update_customer(customer_id: str, **fields) -> Optional[Customer]:
    c = _CUSTOMERS.get(customer_id)
    if not c:
        return None
    for k, v in fields.items():
        if hasattr(c, k) and k not in ("customer_id", "created_at"):
            setattr(c, k, v)
    c.updated_at = datetime.utcnow().isoformat()
    return c


def delete_customer(customer_id: str) -> bool:
    return _CUSTOMERS.pop(customer_id, None) is not None


def add_followup(customer_id: str, followup_type: str, content: str, by: str = "system") -> Dict[str, Any]:
    c = _CUSTOMERS.get(customer_id)
    if not c:
        raise KeyError(f"customer not found: {customer_id}")
    return c.add_followup(followup_type, content, by)


# ---------------------------------------------------------------------------
# Contact (多联系人)
# ---------------------------------------------------------------------------
class Contact:
    def __init__(
        self,
        customer_id: str,
        name: str,
        role: str,
        email: str = "",
        phone: str = "",
        is_primary: bool = False,
    ):
        self.contact_id = f"CT-{uuid.uuid4().hex[:8].upper()}"
        self.customer_id = customer_id
        self.name = name
        self.role = role
        self.email = email
        self.phone = phone
        self.is_primary = is_primary
        self.created_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contact_id": self.contact_id,
            "customer_id": self.customer_id,
            "name": self.name,
            "role": self.role,
            "role_label": CONTACT_ROLE_LABELS.get(self.role, self.role),
            "email": self.email,
            "phone": self.phone,
            "is_primary": self.is_primary,
            "created_at": self.created_at,
        }


_CONTACTS: Dict[str, Contact] = {}


def create_contact(**kwargs) -> Contact:
    if kwargs.get("role") not in CONTACT_ROLES:
        raise ValueError(f"invalid role: {kwargs.get('role')}. valid: {CONTACT_ROLES}")
    if not get_customer(kwargs.get("customer_id", "")):
        raise KeyError(f"customer not found: {kwargs.get('customer_id')}")
    c = Contact(**kwargs)
    _CONTACTS[c.contact_id] = c
    return c


def list_contacts(customer_id: str) -> List[Contact]:
    return [c for c in _CONTACTS.values() if c.customer_id == customer_id]


def get_contact(contact_id: str) -> Optional[Contact]:
    return _CONTACTS.get(contact_id)


def update_contact(contact_id: str, **fields) -> Optional[Contact]:
    c = _CONTACTS.get(contact_id)
    if not c:
        return None
    for k, v in fields.items():
        if hasattr(c, k) and k != "contact_id":
            setattr(c, k, v)
    return c


def delete_contact(contact_id: str) -> bool:
    return _CONTACTS.pop(contact_id, None) is not None


# 集成: 客户升级套餐 → 创建新 Order (回调 billing W1)
def on_plan_upgrade(customer_id: str, new_plan: str) -> Dict[str, Any]:
    """客户升级套餐 — 写跟进 + 同步提升 tier + 返回 Order 模板 (W1 billing 实际创建)."""
    c = get_customer(customer_id)
    if not c:
        raise KeyError(f"customer not found: {customer_id}")
    fu = c.add_followup("contract", f"客户升级套餐: {new_plan}", by="system")
    # 升级时按 plan 映射到目标 tier
    plan_tier = {
        "Free": "individual",
        "Starter": "smb",
        "Pro": "mid_market",
        "Business": "large",
        "Enterprise": "strategic",
        "战略": "strategic",
    }
    target_tier = plan_tier.get(new_plan)
    if target_tier:
        tier_order = ["individual", "smb", "mid_market", "large", "strategic"]
        cur_idx = tier_order.index(c.tier) if c.tier in tier_order else 0
        new_idx = tier_order.index(target_tier)
        if new_idx > cur_idx:
            c.tier = target_tier
    return {"followup": fu, "suggested_order": {"customer_id": customer_id, "plan": new_plan, "action": "create_order"}}
