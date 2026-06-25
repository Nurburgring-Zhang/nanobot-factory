"""
P6-Fix-C-6: 发票红冲 (Red-Letter) 测试

覆盖:
  1. 基本红冲流程 (原票 → 红冲票 + 记录)
  2. 负数金额 + 红冲标记
  3. 红冲对查询 (原票号 / 红冲票号 双向)
  4. 已红冲防重入 (KeyError + ValueError)
  5. 已作废防重入 (voided 状态)
  6. 部分退款 (refund_amount < amount)
  7. 关联订单退款 (mock OrderService)
  8. 退款失败不阻塞红冲 (异常被吞, 红冲照常完成)
  9. 红冲 PDF / OFD 生成 (复用现有渲染)
 10. SM3 哈希链 (红冲后原票 + 红冲票的 hash_chain 都有更新)
 11. 校验: 原票 verify 失败 / 红冲票 verify 通过
 12. 编号生成 (R1 后缀, 防重复)
 13. Reason 校验 (空 / 过长)
 14. list_redlettered (按 order_id 过滤)
 15. RedLetterRecord / RedLetterResult.to_dict 结构
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from invoices import (  # noqa: E402
    _STORE,
    _BY_ORDER,
    generate_invoice,
    get_invoice,
    list_invoices,
    render_invoice_pdf,
    render_invoice_ofd,
    verify_invoice,
)
from invoices.redletter import (  # noqa: E402
    RedLetterRecord,
    RedLetterResult,
    _REDLETTER_STORE,
    _RED_BY_REVERSE,
    _RED_BY_ORDER,
    _reset_redletter_store,
    get_redletter,
    get_redletter_pair,
    get_reverse_invoice_no,
    is_redlettered,
    list_redlettered,
    redletter,
)


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clean_state():
    """每个测试前清空全局存储, 避免污染."""
    _STORE.clear()
    _BY_ORDER.clear()
    _reset_redletter_store()
    yield
    _STORE.clear()
    _BY_ORDER.clear()
    _reset_redletter_store()


def _make_invoice(
    order_id: str = "ORD-RL-001",
    amount: float = 1130.0,
    invoice_type: str = "electronic",
    invoice_no: Optional[str] = None,
):
    """工厂: 生成一张测试发票."""
    kwargs: Dict[str, Any] = dict(
        invoice_type=invoice_type,
        order_id=order_id,
        buyer_name="测试客户",
        buyer_tax_id="91110000TEST12345",
        seller_name="智影纳米机器人",
        seller_tax_id="91110000XXXXXXX5X",
        items=[{
            "name": "数据生成服务",
            "spec": "Pro 套餐",
            "qty": 1,
            "unit_price": amount,
            "amount": amount,
        }],
        amount=amount,
    )
    if invoice_no:
        # 注: 不支持直接指定 invoice_no, 但 generate_invoice_number 可控
        from invoices import _DAILY_COUNTER, generate_invoice_number
        # 占位一次以递增
        generate_invoice_number()
    return generate_invoice(**kwargs)


# ── 测试 ───────────────────────────────────────────────────────────────────

class TestBasicRedLetter:
    """基本红冲流程."""

    def test_redletter_marks_original_voided_and_creates_reverse(self):
        inv = _make_invoice()
        assert inv.status == "issued"

        result = redletter(inv.invoice_no, reason="客户申请退款")

        # 原票被作废
        assert result.original.status == "voided"
        assert is_redlettered(inv.invoice_no)
        # 红冲票反向生成
        assert result.red_letter.invoice_no == f"{inv.invoice_no}-R1"
        assert result.red_letter.amount == -inv.amount
        assert getattr(result.red_letter, "is_red_letter", False) is True
        assert getattr(result.red_letter, "original_invoice_no") == inv.invoice_no

    def test_redletter_record_has_required_fields(self):
        inv = _make_invoice(amount=1130.0)
        result = redletter(inv.invoice_no, reason="服务未交付", operator="admin01")

        rec = result.record
        assert rec.original_invoice_no == inv.invoice_no
        assert rec.red_letter_invoice_no == f"{inv.invoice_no}-R1"
        assert rec.reason == "服务未交付"
        assert rec.refund_amount == 1130.0
        assert rec.refund_currency == "CNY"
        assert rec.operator == "admin01"
        assert rec.red_lettered_at  # ISO8601

    def test_redletter_stores_reverse_in_store(self):
        inv = _make_invoice()
        result = redletter(inv.invoice_no, reason="测试")
        # 红冲票存到 _STORE (可查询/验证/下载)
        red = _STORE[result.red_letter.invoice_no]
        assert red.invoice_no == result.red_letter.invoice_no
        # 可通过 get_invoice 拿到
        assert get_invoice(result.red_letter.invoice_no) is red


class TestNegativeAmountAndTax:
    """红字发票 — 负数金额 + 负数税额."""

    def test_reverse_invoice_has_negative_amount(self):
        inv = _make_invoice(amount=2260.0)
        result = redletter(inv.invoice_no, reason="全额退款")
        assert result.red_letter.amount == -2260.0
        # 税额也取负
        assert result.red_letter.tax["net"] < 0
        assert result.red_letter.tax["tax"] < 0
        assert result.red_letter.tax["gross"] == -2260.0

    def test_reverse_invoice_preserves_buyer_seller(self):
        inv = _make_invoice(amount=500.0)
        result = redletter(inv.invoice_no, reason="测试")
        red = result.red_letter
        assert red.buyer_name == inv.buyer_name
        assert red.buyer_tax_id == inv.buyer_tax_id
        assert red.seller_name == inv.seller_name
        assert red.seller_tax_id == inv.seller_tax_id
        assert red.invoice_type == inv.invoice_type
        assert red.order_id == inv.order_id


class TestQueryAndLookup:
    """查询 API."""

    def test_is_redlettered_true_false(self):
        inv = _make_invoice()
        assert is_redlettered(inv.invoice_no) is False
        redletter(inv.invoice_no, reason="x")
        assert is_redlettered(inv.invoice_no) is True
        # 其他发票未被红冲
        inv2 = _make_invoice(order_id="ORD-RL-002")
        assert is_redlettered(inv2.invoice_no) is False

    def test_get_redletter_returns_record(self):
        inv = _make_invoice()
        assert get_redletter(inv.invoice_no) is None
        redletter(inv.invoice_no, reason="客户取消订单")
        rec = get_redletter(inv.invoice_no)
        assert rec is not None
        assert rec.original_invoice_no == inv.invoice_no

    def test_get_redletter_pair_by_original(self):
        inv = _make_invoice()
        redletter(inv.invoice_no, reason="测试")
        pair = get_redletter_pair(inv.invoice_no)
        assert pair is not None
        orig, red = pair
        assert orig.invoice_no == inv.invoice_no
        assert red.invoice_no == f"{inv.invoice_no}-R1"

    def test_get_redletter_pair_by_reverse_no(self):
        inv = _make_invoice()
        redletter(inv.invoice_no, reason="测试")
        reverse_no = f"{inv.invoice_no}-R1"
        pair = get_redletter_pair(reverse_no)
        assert pair is not None
        orig, red = pair
        assert orig.invoice_no == inv.invoice_no
        assert red.invoice_no == reverse_no

    def test_get_redletter_pair_not_found(self):
        assert get_redletter_pair("INV-NOT-EXIST") is None

    def test_get_reverse_invoice_no(self):
        inv = _make_invoice()
        assert get_reverse_invoice_no(inv.invoice_no) is None
        redletter(inv.invoice_no, reason="测试")
        assert get_reverse_invoice_no(inv.invoice_no) == f"{inv.invoice_no}-R1"

    def test_list_redlettered_by_order_id(self):
        # 3 张发票, 2 个订单, 各红冲 1 张
        inv_a1 = _make_invoice(order_id="ORD-A")
        inv_a2 = _make_invoice(order_id="ORD-A")
        inv_b1 = _make_invoice(order_id="ORD-B")

        redletter(inv_a1.invoice_no, reason="A1 退款")
        redletter(inv_b1.invoice_no, reason="B1 退款")

        all_recs = list_redlettered()
        assert len(all_recs) == 2
        a_recs = list_redlettered(order_id="ORD-A")
        assert len(a_recs) == 1
        assert a_recs[0].original_invoice_no == inv_a1.invoice_no
        b_recs = list_redlettered(order_id="ORD-B")
        assert len(b_recs) == 1

    def test_list_redlettered_empty_for_unused_order(self):
        inv = _make_invoice(order_id="ORD-X")
        redletter(inv.invoice_no, reason="测试")
        assert list_redlettered(order_id="ORD-NONEXISTENT") == []


class TestIdempotencyAndGuards:
    """防重入 + 边界校验."""

    def test_redletter_unknown_invoice_raises_keyerror(self):
        with pytest.raises(KeyError, match="invoice not found"):
            redletter("INV-NOT-EXIST", reason="x")

    def test_double_redletter_raises_valueerror(self):
        inv = _make_invoice()
        redletter(inv.invoice_no, reason="首次")
        with pytest.raises(ValueError, match="already redlettered"):
            redletter(inv.invoice_no, reason="再次")

    def test_voided_invoice_cannot_be_redlettered(self):
        """已被作废 (voided) 的发票不能再红冲."""
        inv = _make_invoice()
        inv.status = "voided"
        with pytest.raises(ValueError, match="already voided"):
            redletter(inv.invoice_no, reason="试图二次")

    def test_blank_reason_rejected(self):
        inv = _make_invoice()
        with pytest.raises(ValueError, match="reason"):
            redletter(inv.invoice_no, reason="")
        with pytest.raises(ValueError, match="reason"):
            redletter(inv.invoice_no, reason="   ")

    def test_oversized_reason_rejected(self):
        inv = _make_invoice()
        with pytest.raises(ValueError, match="too long"):
            redletter(inv.invoice_no, reason="x" * 513)

    def test_zero_refund_amount_rejected(self):
        inv = _make_invoice(amount=1130.0)
        with pytest.raises(ValueError, match="refund_amount must be > 0"):
            redletter(inv.invoice_no, reason="测试", refund_amount=0.0)

    def test_over_refund_amount_rejected(self):
        inv = _make_invoice(amount=1130.0)
        with pytest.raises(ValueError, match="exceeds original"):
            redletter(inv.invoice_no, reason="测试", refund_amount=2000.0)


class TestPartialRefund:
    """部分退款红冲."""

    def test_partial_refund_amount(self):
        inv = _make_invoice(amount=1130.0)
        result = redletter(inv.invoice_no, reason="部分退款", refund_amount=565.0)
        assert result.record.refund_amount == 565.0
        assert result.red_letter.amount == -565.0

    def test_default_refund_amount_is_full(self):
        inv = _make_invoice(amount=1130.0)
        result = redletter(inv.invoice_no, reason="全额")
        assert result.record.refund_amount == 1130.0
        assert result.red_letter.amount == -1130.0


class TestOrderRefundIntegration:
    """关联订单退款."""

    def test_redletter_calls_order_refund_full(self):
        """无 amount_cents 时调用 refund 触发全额退款."""
        inv = _make_invoice(order_id="ORD-REFUND-001", amount=1130.0)
        mock_svc = MagicMock()
        mock_order = MagicMock()
        mock_order.to_dict.return_value = {
            "order_id": "ORD-REFUND-001",
            "refunded_amount_cents": 113000,
            "status": "refunded",
        }
        mock_svc.refund.return_value = mock_order

        result = redletter(
            inv.invoice_no,
            reason="客户申请",
            order_service=mock_svc,
        )

        # order_service.refund 被调用
        mock_svc.refund.assert_called_once()
        call_args = mock_svc.refund.call_args
        assert call_args.args[0] == "ORD-REFUND-001"
        # reason 含 redletter 前缀
        assert "redletter" in call_args.kwargs["reason"]
        # 全额退款 (amount_cents=None)
        assert call_args.kwargs.get("amount_cents") is None

        # 订单退款记录被保存
        assert result.record.order_refund is not None
        assert result.record.order_refund["refunded_amount_cents"] == 113000

    def test_redletter_calls_order_refund_partial(self):
        """部分退款时 amount_cents 转换为分."""
        inv = _make_invoice(amount=1130.0)
        mock_svc = MagicMock()
        mock_svc.refund.return_value = MagicMock(to_dict=lambda: {"ok": True})

        result = redletter(
            inv.invoice_no,
            reason="部分",
            refund_amount=565.0,
            order_service=mock_svc,
        )
        # 565 元 → 56500 分
        call_args = mock_svc.refund.call_args
        assert call_args.kwargs["amount_cents"] == 56500

    def test_redletter_order_refund_failure_does_not_block(self):
        """订单退款失败时, 红冲仍正常完成."""
        inv = _make_invoice()
        mock_svc = MagicMock()
        mock_svc.refund.side_effect = ValueError("order not in PAID state")

        # 不应抛异常
        result = redletter(
            inv.invoice_no,
            reason="退款失败但红冲照常",
            order_service=mock_svc,
        )

        assert is_redlettered(inv.invoice_no)
        assert result.record.order_refund["refunded"] is False
        assert "order not in PAID" in result.record.order_refund["error"]

    def test_redletter_no_order_service(self):
        """不提供 order_service 时, 红冲仍正常, order_refund=None."""
        inv = _make_invoice()
        result = redletter(inv.invoice_no, reason="无退款")
        assert result.record.order_refund is None
        assert is_redlettered(inv.invoice_no)

    def test_redletter_order_service_without_refund_method(self):
        """order_service 没有 refund() 方法时不报错."""
        inv = _make_invoice()
        fake_svc = MagicMock(spec=[])  # 无 refund
        result = redletter(
            inv.invoice_no,
            reason="无 refund 方法",
            order_service=fake_svc,
        )
        assert result.record.order_refund is None


class TestRenderAndHash:
    """PDF / OFD 渲染 + SM3 哈希链."""

    def test_redletter_pdf_renderable(self):
        inv = _make_invoice(amount=1130.0)
        result = redletter(inv.invoice_no, reason="测试")
        # 红冲票 PDF
        pdf = render_invoice_pdf(result.red_letter)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 200
        assert pdf[:5] == b"%PDF-"

    def test_redletter_ofd_renderable(self):
        inv = _make_invoice(amount=1130.0)
        result = redletter(inv.invoice_no, reason="测试")
        ofd = render_invoice_ofd(result.red_letter)
        assert isinstance(ofd, bytes)
        with zipfile.ZipFile(io.BytesIO(ofd), "r") as z:
            xml = z.read("ofd.xml").decode("utf-8")
        # OFD 含原票号 + 红冲票号
        assert result.red_letter.invoice_no in xml

    def test_redletter_updates_original_hash_chain(self):
        inv = _make_invoice()
        old_hash_count = len(inv.hash_chain)
        redletter(inv.invoice_no, reason="测试")
        # 原票 hash_chain 应增加 (状态变 voided 触发 _compute_hash)
        assert len(inv.hash_chain) > old_hash_count

    def test_redletter_reverse_has_hash_chain(self):
        inv = _make_invoice()
        result = redletter(inv.invoice_no, reason="测试")
        # 红冲票本身有 hash_chain
        assert len(result.red_letter.hash_chain) >= 1

    def test_original_verify_fails_after_redletter(self):
        """红冲后原票 verify 应失败 (status=voided)."""
        inv = _make_invoice()
        # 红冲前 verify 通过
        v_before = verify_invoice(inv.invoice_no)
        assert v_before["valid"] is True

        redletter(inv.invoice_no, reason="测试")

        # 红冲后原票 verify 失败 (因为 status=voided 改了 hash)
        v_after = verify_invoice(inv.invoice_no)
        assert v_after["valid"] is False

    def test_reverse_invoice_verifies(self):
        """红冲票本身 verify 通过 (它是有效发票)."""
        inv = _make_invoice()
        result = redletter(inv.invoice_no, reason="测试")
        v = verify_invoice(result.red_letter.invoice_no)
        assert v["valid"] is True


class TestNumbering:
    """红冲编号 — R1/R2 后缀."""

    def test_reverse_no_first_attempt_is_r1(self):
        inv = _make_invoice()
        result = redletter(inv.invoice_no, reason="首次")
        assert result.red_letter.invoice_no == f"{inv.invoice_no}-R1"

    def test_reverse_no_avoids_existing(self):
        """编号 R1/R2 后缀: 直接测试编号生成器跳过已占号.
        现实场景: voided 守卫会拦截二次红冲, 所以 R2 仅在跨进程残留时触发."""
        from invoices.redletter import _RED_BY_REVERSE_loop
        # 没有任何占用时, 应得 R1
        _, c1 = _RED_BY_REVERSE_loop("INV-XYZ")
        assert c1 == 1
        # 手动占用 R1
        _RED_BY_REVERSE["INV-XYZ-R1"] = "INV-XYZ"
        _, c2 = _RED_BY_REVERSE_loop("INV-XYZ")
        assert c2 == 2
        # 再占 R2
        _RED_BY_REVERSE["INV-XYZ-R2"] = "INV-XYZ"
        _, c3 = _RED_BY_REVERSE_loop("INV-XYZ")
        assert c3 == 3


class TestSerialization:
    """to_dict 结构完整性."""

    def test_redletter_result_to_dict(self):
        inv = _make_invoice()
        result = redletter(inv.invoice_no, reason="测试")
        d = result.to_dict()
        assert "original" in d
        assert "red_letter" in d
        assert "record" in d
        # original 是已作废
        assert d["original"]["status"] == "voided"
        # red_letter 是负数
        assert d["red_letter"]["amount"] < 0
        assert d["record"]["original_invoice_no"] == inv.invoice_no

    def test_redletter_record_to_dict(self):
        inv = _make_invoice()
        result = redletter(inv.invoice_no, reason="x")
        d = result.record.to_dict()
        assert d["original_invoice_no"] == inv.invoice_no
        assert d["reason"] == "x"
        assert d["refund_currency"] == "CNY"


class TestFullFlow:
    """端到端流程."""

    def test_full_flow_paid_invoice_to_refund(self):
        """模拟: 创建发票 → 红冲 → 部分退款 → 查询红冲对."""
        inv = _make_invoice(order_id="ORD-E2E", amount=2260.0)
        # 红冲 (半额)
        result = redletter(
            inv.invoice_no,
            reason="客户对服务不满意, 申请半价退款",
            refund_amount=1130.0,
            operator="ops_team",
        )
        # 原票作废
        assert result.original.status == "voided"
        # 红冲票反向
        assert result.red_letter.amount == -1130.0
        # 记录正确
        assert result.record.refund_amount == 1130.0
        assert result.record.operator == "ops_team"
        # 查询红冲对
        pair = get_redletter_pair(inv.invoice_no)
        assert pair is not None
        orig, red = pair
        assert orig.status == "voided"
        assert red.amount == -1130.0
        # 原票 verify 失败, 红冲票 verify 通过
        assert verify_invoice(orig.invoice_no)["valid"] is False
        assert verify_invoice(red.invoice_no)["valid"] is True

    def test_multiple_orders_independent_redletter(self):
        """多订单独立红冲."""
        invs = [
            _make_invoice(order_id=f"ORD-MULTI-{i}", amount=100.0 * (i + 1))
            for i in range(5)
        ]
        # 红冲第 0 和第 2 个
        redletter(invs[0].invoice_no, reason="0 退款")
        redletter(invs[2].invoice_no, reason="2 退款")
        # 列表
        recs = list_redlettered()
        assert len(recs) == 2
        redlettered_nos = {r.original_invoice_no for r in recs}
        assert invs[0].invoice_no in redlettered_nos
        assert invs[2].invoice_no in redlettered_nos
        # 未被红冲的发票状态仍为 issued
        assert invs[1].status == "issued"
        assert invs[3].status == "issued"
        assert invs[4].status == "issued"
