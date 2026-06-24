"""
P4-10-W2: CRM 客户管理测试
"""
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from crm import (
    TIERS, TIER_LABELS, INDUSTRIES, SIZES,
    FOLLOWUP_TYPES, CONTACT_ROLES,
    create_customer, get_customer, list_customers, update_customer, delete_customer, add_followup,
    create_contact, list_contacts, get_contact, update_contact, delete_contact,
    on_plan_upgrade,
)


def test_customer_crud_and_tier():
    """客户 CRUD + 5 分级."""
    c = create_customer(
        company_name="宇宙科技",
        contact_name="张三",
        email="zhang@u.com",
        phone="+86-138-0000-0000",
        industry="互联网/科技",
        size="51-200",
        tier="mid_market",
        tags=["VIP", "高潜力"],
    )
    assert c.customer_id.startswith("CUS-")
    assert c.tier == "mid_market"
    assert "VIP" in c.tags
    # 读取
    fetched = get_customer(c.customer_id)
    assert fetched.company_name == "宇宙科技"
    # 更新
    updated = update_customer(c.customer_id, tier="large", phone="+86-139-1111-1111")
    assert updated.tier == "large"
    assert updated.phone == "+86-139-1111-1111"
    # 删除
    assert delete_customer(c.customer_id) is True
    assert get_customer(c.customer_id) is None


def test_customer_search_and_filter():
    c1 = create_customer(company_name="AAA 公司", contact_name="赵一", email="a@a.com", tier="smb", industry="金融", tags=["重点"])
    c2 = create_customer(company_name="BBB 公司", contact_name="钱二", email="b@b.com", tier="large", industry="制造", manager_id="mgr-1")
    c3 = create_customer(company_name="CCC 公司", contact_name="孙三", email="c@c.com", tier="strategic", industry="金融", manager_id="mgr-1")
    # 按 tier 过滤
    finance = list_customers(tier="large")
    assert any(c.customer_id == c2.customer_id for c in finance)
    # 按 industry
    fin = list_customers(industry="金融")
    ids = [c.customer_id for c in fin]
    assert c1.customer_id in ids and c3.customer_id in ids
    # 按 manager
    mgr1 = list_customers(manager_id="mgr-1")
    assert len(mgr1) == 2
    # 搜索
    s = list_customers(search="aaa")
    assert any(c.customer_id == c1.customer_id for c in s)
    # tag
    tagged = list_customers(tag="重点")
    assert any(c.customer_id == c1.customer_id for c in tagged)


def test_followup_records():
    """5 类跟进记录 + 1 客户 1 manager."""
    c = create_customer(
        company_name="X 公司",
        contact_name="李四",
        email="l@x.com",
        tier="individual",
        manager_id="mgr-only",
    )
    # 1 客户 1 manager 约束由业务层保证 (同一 manager 不会有多个)
    fu1 = add_followup(c.customer_id, "communication", "初次电话沟通", by="王经理")
    fu2 = add_followup(c.customer_id, "contract", "签订服务协议", by="王经理")
    fu3 = add_followup(c.customer_id, "payment", "首付款到账", by="系统")
    fu4 = add_followup(c.customer_id, "complaint", "服务延迟投诉", by="客户")
    assert fu1["type"] == "communication"
    assert len(c.followups) == 4
    # 错误类型
    with pytest.raises(ValueError, match="unknown followup_type"):
        add_followup(c.customer_id, "invalid_type", "x")
    # 客户不存在
    with pytest.raises(KeyError):
        add_followup("CUS-NOT-EXIST", "communication", "x")


def test_contact_crud():
    """联系人 CRUD + 4 角色."""
    c = create_customer(company_name="客户 ABC", contact_name="主联系人", email="main@abc.com", tier="smb")
    # 创建 4 角色联系人
    roles = ["procurement", "technical", "finance", "legal"]
    contacts = []
    for role in roles:
        ct = create_contact(
            customer_id=c.customer_id,
            name=f"联系人-{role}",
            role=role,
            email=f"{role}@abc.com",
            is_primary=(role == "procurement"),
        )
        contacts.append(ct)
    # 列表
    listed = list_contacts(c.customer_id)
    assert len(listed) == 4
    roles_listed = {ct.role for ct in listed}
    assert roles_listed == set(roles)
    # 读取
    one = get_contact(contacts[0].contact_id)
    assert one.name == "联系人-procurement"
    # 更新
    upd = update_contact(contacts[0].contact_id, name="主采购")
    assert upd.name == "主采购"
    # 删除
    assert delete_contact(contacts[0].contact_id) is True
    assert len(list_contacts(c.customer_id)) == 3


def test_plan_upgrade_hook():
    """套餐升级 → 写跟进 + tier 提升."""
    c = create_customer(company_name="升级测试", contact_name="X", email="x@x.com", tier="smb")
    r = on_plan_upgrade(c.customer_id, "Enterprise")
    assert "followup" in r
    assert r["followup"]["type"] == "contract"
    # tier 应被提升
    assert c.tier in ("large", "strategic")
