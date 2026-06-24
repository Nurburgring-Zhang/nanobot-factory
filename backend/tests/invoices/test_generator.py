"""
P4-10-W2: 发票生成器测试 (编号 + SM3 + 防篡改 + OFD)
"""
import sys
import io
import zipfile
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from invoices import (
    TEMPLATE_TYPES,
    generate_invoice,
    get_invoice,
    list_invoices,
    verify_invoice,
    render_invoice_pdf,
    render_invoice_ofd,
    save_invoice_pdf,
    save_invoice_ofd,
    calc_tax,
    generate_invoice_number,
    on_order_paid,
    _sm3_hex,
)


def _make_invoice(**overrides):
    defaults = dict(
        invoice_type="electronic",
        order_id="ORD-001",
        buyer_name="测试客户",
        buyer_tax_id="91110000TEST12345",
        seller_name="智影纳米机器人",
        seller_tax_id="91110000XXXXXXX5X",
        items=[{"name": "数据生成服务", "spec": "Pro 套餐", "qty": 1, "unit_price": 1130.0, "amount": 1130.0}],
        amount=1130.0,
    )
    defaults.update(overrides)
    return generate_invoice(**defaults)


def test_invoice_number_format():
    """编号规则 INV-YYYYMMDD-NNNN."""
    n1 = generate_invoice_number()
    n2 = generate_invoice_number()
    assert n1.startswith("INV-")
    # YYYYMMDD = 8 digits
    m = n1.split("-")
    assert len(m) == 3
    assert len(m[1]) == 8 and m[1].isdigit()
    assert len(m[2]) == 4 and m[2].isdigit()
    # 顺序递增
    assert int(m[2]) < int(n2.split("-")[2]) or m[1] < n2.split("-")[1]


def test_tax_calculation():
    """含税/不含税计算正确性."""
    # 113 元含税 → 100 + 13
    r = calc_tax(113.0, rate=0.13, inclusive=True)
    assert abs(r["net"] - 100.0) < 0.01
    assert abs(r["tax"] - 13.0) < 0.01
    assert abs(r["gross"] - 113.0) < 0.01
    # 100 不含税 → 100 + 13 = 113
    r2 = calc_tax(100.0, rate=0.13, inclusive=False)
    assert abs(r2["net"] - 100.0) < 0.01
    assert abs(r2["tax"] - 13.0) < 0.01
    assert abs(r2["gross"] - 113.0) < 0.01


def test_sm3_antitamper():
    """SM3 哈希防篡改验证."""
    inv = _make_invoice(amount=226.0)
    # 初始 verify 应通过
    v1 = verify_invoice(inv.invoice_no)
    assert v1["valid"] is True
    assert v1["stored_hash"] == v1["computed_hash"]
    # 篡改 amount 后 verify 失败
    original = inv.amount
    inv.amount = 9999.0
    v2 = verify_invoice(inv.invoice_no)
    assert v2["valid"] is False
    # 还原
    inv.amount = original


def test_invoice_ofd_format():
    """OFD 格式电子发票 (XML + zip)."""
    inv = _make_invoice(invoice_type="electronic", amount=1130.0)
    ofd = render_invoice_ofd(inv)
    assert isinstance(ofd, bytes)
    assert len(ofd) > 100
    # 验证是有效 zip
    with zipfile.ZipFile(io.BytesIO(ofd), "r") as z:
        names = z.namelist()
        assert "ofd.xml" in names
        assert "signature.xml" in names
        # ofd.xml 含发票号
        xml = z.read("ofd.xml").decode("utf-8")
        assert inv.invoice_no in xml
        assert "SM3" in xml


def test_invoice_pdf_generation():
    """发票 PDF 生成."""
    inv = _make_invoice(amount=1130.0)
    pdf = render_invoice_pdf(inv)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 200
    assert pdf[:5] == b"%PDF-"
    # 保存磁盘
    out = save_invoice_pdf(inv)
    assert out.exists()
    data = out.read_bytes()
    assert data[:5] == b"%PDF-"
    out.unlink(missing_ok=True)


def test_invoice_list_and_get():
    _make_invoice(order_id="ORD-X")
    _make_invoice(order_id="ORD-Y", invoice_type="vat_normal")
    items = list_invoices()
    assert len(items) >= 2
    by_order = list_invoices(order_id="ORD-X")
    assert len(by_order) == 1
    one = items[0]
    fetched = get_invoice(one.invoice_no)
    assert fetched is not None
    assert fetched.invoice_no == one.invoice_no


def test_invalid_invoice_type():
    with pytest.raises(ValueError, match="unknown invoice_type"):
        _make_invoice(invoice_type="invalid")


def test_empty_items_rejected():
    with pytest.raises(ValueError, match="items must not be empty"):
        generate_invoice(
            invoice_type="electronic",
            order_id="ORD-Z",
            buyer_name="X",
            buyer_tax_id=None,
            seller_name="S",
            seller_tax_id="T",
            items=[],
            amount=100.0,
        )


def test_order_paid_hook():
    """Order paid 钩子自动生成发票."""
    inv = on_order_paid(
        order_id="ORD-HOOK-001",
        buyer_name="客户 X",
        buyer_tax_id=None,
        amount=113.0,
    )
    assert inv.invoice_type == "electronic"
    assert inv.order_id == "ORD-HOOK-001"
    assert inv.amount == 113.0
    assert abs(inv.tax["gross"] - 113.0) < 0.01
