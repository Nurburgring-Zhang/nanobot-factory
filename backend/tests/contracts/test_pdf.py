"""
P4-10-W2: 合同 PDF 生成测试 (3 模板)
"""
import sys
import os
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from contracts import (
    TEMPLATES,
    generate_contract,
    sign_contract,
    get_contract,
    list_contracts,
    render_contract_pdf,
    save_contract_pdf,
    sm3_hash,
    _sm3_hex,
)


def test_sm3_hash_basic():
    """SM3 哈希基本功能."""
    h = _sm3_hex(b"hello")
    assert isinstance(h, str)
    assert len(h) >= 32  # 32 字节 = 64 字符
    # 确定性
    assert _sm3_hex(b"hello") == h


def test_sm3_hash_object():
    h = sm3_hash({"a": 1, "b": "x"})
    assert isinstance(h, str)
    assert len(h) >= 32


@pytest.mark.parametrize("template", list(TEMPLATES.keys()))
def test_pdf_three_templates(template, tmp_path):
    """3 合同模板都能生成真实 PDF."""
    c = generate_contract(
        template=template,
        company_name="测试科技有限公司",
        contact_email="test@example.com",
        plan_name="Pro",
        amount=1234.56,
        start_date="2026-07-01",
        end_date="2027-07-01",
    )
    assert c.contract_id.startswith("CT-")
    assert c.template == template
    # SM3 指纹
    assert len(c.hash_chain) == 1
    # 渲染 PDF
    pdf = render_contract_pdf(c)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 200, f"PDF too small: {len(pdf)} bytes for {template}"
    # PDF 文件头
    assert pdf[:5] == b"%PDF-", f"not a valid PDF: starts with {pdf[:10]!r}"
    # 保存到磁盘
    out = save_contract_pdf(c)
    assert out.exists()
    assert out.stat().st_size > 200
    # 二次读回仍合法
    data = out.read_bytes()
    assert data[:5] == b"%PDF-"
    # 清理
    out.unlink(missing_ok=True)


def test_contract_signing():
    c = generate_contract(
        template="service_agreement",
        company_name="ABC 公司",
        contact_email="abc@example.com",
        plan_name="Business",
        amount=5000.0,
    )
    signed = sign_contract(c.contract_id, signer="zhang@example.com")
    assert signed.status == "signed"
    assert signed.signature is not None
    assert signed.signed_by == "zhang@example.com"
    assert signed.signed_at is not None
    assert len(signed.hash_chain) >= 1
    # 签名包含 SM3 指纹
    assert "SM3" in signed.signature or "SM2" in signed.signature


def test_contract_list_and_get():
    generate_contract(
        template="sla_agreement",
        company_name="X 客户",
        contact_email="x@x.com",
        plan_name="Starter",
        amount=99.0,
    )
    items = list_contracts()
    assert len(items) >= 1
    one = items[0]
    fetched = get_contract(one.contract_id)
    assert fetched is not None
    assert fetched.contract_id == one.contract_id


def test_invalid_template():
    with pytest.raises(ValueError, match="unknown template"):
        generate_contract(
            template="invalid_template",
            company_name="X",
            contact_email="x@x.com",
            plan_name="X",
            amount=1.0,
        )


def test_variable_substitution():
    c = generate_contract(
        template="service_agreement",
        company_name="宇宙科技",
        contact_email="hi@u.com",
        plan_name="Enterprise",
        amount=99999.0,
        start_date="2027-01-01",
        end_date="2028-01-01",
    )
    assert c.variables["company_name"] == "宇宙科技"
    assert c.variables["plan_name"] == "Enterprise"
    assert c.variables["amount"] == "99999.00"
    assert c.variables["start_date"] == "2027-01-01"
