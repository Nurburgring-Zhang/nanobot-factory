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
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

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
