"""
P6-Fix-C-6: 发票红冲 (Invoice Red-Letter / 红冲发票)

国标发票红冲流程 (Chinese accounting practice):
  1. 原发票被标记为 redlettered (作废, 不能再用)
  2. 系统生成一张反向发票 (red_letter_invoice), 金额为负
  3. 反向发票含原发票号 + 红冲编号, 形成完整的红冲链路
  4. 关联订单退款 (partial / full) — 调用 billing.orders.OrderService.refund()

为什么不直接删原发票?
  - 财务审计要求原票作废但可追溯 (国标《发票管理办法》)
  - 红冲链路是双向闭环: 原票 → 红冲 → 新红字发票
  - 反向发票的 SM3 哈希链也含原票号, 防篡改

公开 API:
  - redletter(invoice_no, reason, refund_amount=None, order_service=None)
        → RedLetterResult (原票 + 红冲票 + 订单退款信息)
  - get_redletter(invoice_no)        → Optional[RedLetterRecord]
  - get_redletter_pair(invoice_no)   → Optional[Tuple[Invoice, Invoice]] (原票, 红冲票)
  - list_redlettered(order_id=None)  → List[RedLetterRecord]
  - is_redlettered(invoice_no)       → bool
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import (
    Invoice,
    _STORE,
    _BY_ORDER,
    generate_invoice,
    generate_invoice_number,
    sm3_hash,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class RedLetterRecord:
    """红冲记录 — 持久化在 _REDLETTER_STORE 中."""
    original_invoice_no: str        # 原发票号
    red_letter_invoice_no: str      # 红冲反向发票号
    reason: str                     # 红冲原因
    red_lettered_at: str            # 红冲时间 (ISO8601)
    refund_amount: float            # 退款金额 (与发票金额一致, 简化版)
    refund_currency: str = "CNY"    # 货币
    order_refund: Optional[Dict[str, Any]] = None  # 关联订单退款记录
    operator: Optional[str] = None  # 操作人

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 状态存储 (进程内)
# ---------------------------------------------------------------------------
_REDLETTER_STORE: Dict[str, RedLetterRecord] = {}
# 反向索引: 红冲票 → 原票
_RED_BY_REVERSE: Dict[str, str] = {}
# 订单维度的红冲历史
_RED_BY_ORDER: Dict[str, List[str]] = {}


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _validate_reason(reason: str) -> str:
    if not reason or not isinstance(reason, str):
        raise ValueError("reason is required and must be a non-empty string")
    if len(reason.strip()) == 0:
        raise ValueError("reason must not be blank")
    if len(reason) > 512:
        raise ValueError(f"reason too long ({len(reason)} > 512 chars)")
    return reason.strip()


def _reverse_number(original_no: str) -> str:
    """生成红冲发票号: 在原号基础上加 -R1 / -R2 后缀.
    
    国标没有强制规定编号规则, 但常见做法是:
      原票: INV-YYYYMMDD-NNNN
      红冲: INV-YYYYMMDD-NNNN-R1  (第一次红冲)
            INV-YYYYMMDD-NNNN-R2  (第二次红冲 — 罕见)
    """
    base, counter = _RED_BY_REVERSE_loop(original_no)
    return f"{base}-R{counter}"


def _RED_BY_REVERSE_loop(original_no: str) -> Tuple[str, int]:  # noqa: N802
    """求下一个可用红冲编号."""
    counter = 1
    while True:
        candidate = f"{original_no}-R{counter}"
        if candidate not in _STORE and candidate not in _RED_BY_REVERSE:
            return original_no, counter
        counter += 1
        if counter > 99:
            # 防爆
            raise RuntimeError(
                f"too many redletter attempts for {original_no!r} (>99)"
            )


def _attempt_order_refund(
    invoice: Invoice,
    refund_amount: float,
    reason: str,
    order_service: Any,
) -> Optional[Dict[str, Any]]:
    """尝试调用订单服务退款. order_service 可能是 None (无退款链路)."""
    if order_service is None:
        logger.info(
            "redletter %s: no order_service provided, skipping order refund",
            invoice.invoice_no,
        )
        return None
    if not hasattr(order_service, "refund"):
        logger.warning(
            "redletter %s: order_service has no refund() method, skipping",
            invoice.invoice_no,
        )
        return None
    try:
        # amount_cents (元 → 分). 当 refund_amount 等于原发票全额时,
        # 传 None (OrderService.refund 的语义: None = 全额退剩余).
        order_amount = float(invoice.amount)
        if abs(refund_amount - order_amount) < 0.01:
            amount_cents: Optional[int] = None  # 全额退款
        else:
            amount_cents = int(round(refund_amount * 100))
        result = order_service.refund(
            invoice.order_id,
            reason=f"redletter: {reason}",
            amount_cents=amount_cents,
        )
        if hasattr(result, "to_dict"):
            return result.to_dict()
        if isinstance(result, dict):
            return result
        return {"refunded": True, "raw": str(result)}
    except Exception as e:
        logger.warning(
            "redletter %s: order refund failed: %s",
            invoice.invoice_no,
            e,
        )
        return {"refunded": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 主入口: redletter()
# ---------------------------------------------------------------------------
@dataclass
class RedLetterResult:
    """红冲结果."""
    original: Invoice
    red_letter: Invoice
    record: RedLetterRecord

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original": self.original.to_dict(),
            "red_letter": self.red_letter.to_dict(),
            "record": self.record.to_dict(),
        }


def redletter(
    invoice_no: str,
    reason: str,
    refund_amount: Optional[float] = None,
    operator: Optional[str] = None,
    order_service: Any = None,
) -> RedLetterResult:
    """执行红冲.

    Args:
        invoice_no:  原发票号
        reason:      红冲原因 (必填, ≤512 字符)
        refund_amount: 退款金额, None=全额退款 (默认等于原票金额)
        operator:    操作人 (审计字段)
        order_service: 订单服务实例, 若提供且原发票关联订单,
                        会自动调用 refund() 触发订单退款

    Returns:
        RedLetterResult (原票 + 红冲票 + 记录)

    Raises:
        KeyError:     原发票不存在
        ValueError:   原因无效, 或原票已红冲, 或原票已被作废,
                      或 refund_amount 不合法
    """
    reason = _validate_reason(reason)

    # 1. 校验原票
    original = _STORE.get(invoice_no)
    if original is None:
        raise KeyError(f"invoice not found: {invoice_no!r}")

    if is_redlettered(invoice_no):
        existing = get_redletter(invoice_no)
        raise ValueError(
            f"invoice {invoice_no!r} is already redlettered "
            f"(reverse invoice: {existing.red_letter_invoice_no if existing else 'unknown'})"
        )
    if original.status == "voided":
        raise ValueError(
            f"invoice {invoice_no!r} is already voided — cannot redletter"
        )
    if original.status not in ("issued", "verified"):
        raise ValueError(
            f"cannot redletter invoice in status {original.status!r} "
            f"(only 'issued' or 'verified' are redletterable)"
        )

    # 2. 计算退款金额
    if refund_amount is None:
        refund_amount = float(original.amount)
    if refund_amount <= 0:
        raise ValueError(
            f"refund_amount must be > 0, got {refund_amount}"
        )
    if refund_amount > original.amount + 0.01:  # 浮点容差
        raise ValueError(
            f"refund_amount {refund_amount} exceeds original amount "
            f"{original.amount}"
        )

    # 3. 标记原票作废
    original.status = "voided"
    original._compute_hash()

    # 4. 生成反向发票 (金额为负 — 红字发票)
    _, counter = _RED_BY_REVERSE_loop(invoice_no)
    red_no = f"{invoice_no}-R{counter}"
    red_letter = _build_reverse_invoice(
        original=original,
        reverse_no=red_no,
        reason=reason,
        refund_amount=refund_amount,
    )

    # 5. 关联订单退款
    order_refund_info = _attempt_order_refund(
        invoice=original,
        refund_amount=refund_amount,
        reason=reason,
        order_service=order_service,
    )

    # 6. 写红冲记录
    record = RedLetterRecord(
        original_invoice_no=invoice_no,
        red_letter_invoice_no=red_no,
        reason=reason,
        red_lettered_at=_now_iso(),
        refund_amount=refund_amount,
        refund_currency="CNY",
        order_refund=order_refund_info,
        operator=operator,
    )
    _REDLETTER_STORE[invoice_no] = record
    _RED_BY_REVERSE[red_no] = invoice_no
    _RED_BY_ORDER.setdefault(original.order_id, []).append(invoice_no)

    logger.info(
        "redletter: %s → %s (order=%s, refund=%.2f, operator=%s)",
        invoice_no, red_no, original.order_id, refund_amount, operator,
    )

    return RedLetterResult(
        original=original,
        red_letter=red_letter,
        record=record,
    )


def _build_reverse_invoice(
    original: Invoice,
    reverse_no: str,
    reason: str,
    refund_amount: float,
) -> Invoice:
    """构造红字发票 (反向, 负数金额)."""
    # 直接 new 一个 Invoice 实例, 不走 generate_invoice (避免重计 SM3 默认值)
    red = Invoice(
        invoice_no=reverse_no,
        invoice_type=original.invoice_type,
        order_id=original.order_id,
        buyer_name=original.buyer_name,
        buyer_tax_id=original.buyer_tax_id,
        seller_name=original.seller_name,
        seller_tax_id=original.seller_tax_id,
        items=original.items,
        amount=-refund_amount,        # 负数 — 红字
        tax_rate=original.tax_rate,
    )
    # 标记红冲属性 + 重算 SM3 (含红冲元数据)
    red.status = "issued"           # 红冲票本身是有效发票
    red.is_red_letter = True
    red.original_invoice_no = original.invoice_no
    red.red_letter_reason = reason
    # 重算 tax: 红字发票税额也取负
    red.tax = {
        "net": -round(refund_amount / (1 + original.tax_rate), 2),
        "tax": -round(refund_amount - refund_amount / (1 + original.tax_rate), 2),
        "gross": -refund_amount,
        "rate": original.tax_rate,
    }
    red._compute_hash()
    # 存入 _STORE (红字发票本身可查询/验证/下载 PDF/OFD)
    _STORE[reverse_no] = red
    return red


# ---------------------------------------------------------------------------
# 查询 API
# ---------------------------------------------------------------------------
def is_redlettered(invoice_no: str) -> bool:
    """是否已被红冲 (作为原票)."""
    return invoice_no in _REDLETTER_STORE


def get_redletter(invoice_no: str) -> Optional[RedLetterRecord]:
    """取红冲记录 (输入原票号)."""
    return _REDLETTER_STORE.get(invoice_no)


def get_redletter_pair(
    invoice_no: str,
) -> Optional[Tuple[Invoice, Invoice]]:
    """取红冲对 (原票, 红冲票).  invoice_no 可以是原票或红冲票."""
    # 输入是红冲票?
    original_no = _RED_BY_REVERSE.get(invoice_no)
    if original_no is None:
        # 输入可能是原票
        if invoice_no not in _REDLETTER_STORE:
            return None
        original_no = invoice_no
    record = _REDLETTER_STORE.get(original_no)
    if not record:
        return None
    orig = _STORE.get(original_no)
    red = _STORE.get(record.red_letter_invoice_no)
    if orig is None or red is None:
        return None
    return (orig, red)


def list_redlettered(
    order_id: Optional[str] = None,
) -> List[RedLetterRecord]:
    """列出所有红冲记录 (可选按订单过滤)."""
    if order_id:
        ids = _RED_BY_ORDER.get(order_id, [])
        return [_REDLETTER_STORE[i] for i in ids if i in _REDLETTER_STORE]
    return list(_REDLETTER_STORE.values())


def get_reverse_invoice_no(original_invoice_no: str) -> Optional[str]:
    """取红冲反向发票号."""
    rec = _REDLETTER_STORE.get(original_invoice_no)
    return rec.red_letter_invoice_no if rec else None


# ---------------------------------------------------------------------------
# 测试用 — 重置内部状态
# ---------------------------------------------------------------------------
def _reset_redletter_store() -> None:
    """清空所有红冲状态. 仅用于测试."""
    _REDLETTER_STORE.clear()
    _RED_BY_REVERSE.clear()
    _RED_BY_ORDER.clear()


__all__ = [
    "RedLetterRecord",
    "RedLetterResult",
    "redletter",
    "is_redlettered",
    "get_redletter",
    "get_redletter_pair",
    "list_redlettered",
    "get_reverse_invoice_no",
    "_reset_redletter_store",
]
