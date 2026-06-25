"""P1-7: 财务月度报表 (Financial Monthly Report)

业务背景:
- 月度财务汇总, 给 CFO/财务团队使用.
- 数据来源: invoices + orders + subscriptions (跨服务聚合).
- 维度: 按月/季/年; 按发票类型; 按付款方式; 按客户层级.
- 输出格式: JSON (前端) + CSV (Excel 兼容).

公开 API:
  - generate_monthly_report(year, month, ...)   → MonthlyFinancialReport
  - generate_quarterly_report(year, quarter)     → AggregatedReport
  - export_report_csv(report)                    → str
  - get_revenue_by_payment_method(year, month)   → Dict
  - get_top_customers_by_revenue(year, month, n) → List
"""
from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MonthlyFinancialReport:
    """月度财务报表."""
    year: int
    month: int
    total_orders: int = 0
    paid_orders: int = 0
    refunded_orders: int = 0
    cancelled_orders: int = 0
    total_revenue_cents: int = 0      # 实收
    total_refund_cents: int = 0
    net_revenue_cents: int = 0        # 净收 (revenue - refund)
    total_invoices: int = 0
    total_tax_cents: int = 0
    total_invoice_amount_cents: int = 0
    by_payment_method: Dict[str, int] = field(default_factory=dict)
    by_invoice_type: Dict[str, Dict[str, int]] = field(default_factory=dict)
    by_currency: Dict[str, int] = field(default_factory=dict)
    top_customers: List[Dict[str, Any]] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _iter_invoices(year: int, month: int) -> List[Any]:
    """从 invoices 模块拉取当月所有发票."""
    try:
        from . import list_invoices  # type: ignore
        prefix = f"{year:04d}-{month:02d}"
        all_inv = list_invoices()
        return [inv for inv in all_inv if inv.issue_date.startswith(prefix)]
    except Exception as e:
        logger.debug("invoices module unavailable: %s", e)
        return []


def _iter_orders(year: int, month: int) -> List[Any]:
    """从 billing.routes 的全局 state 拉取当月订单 (与 API 共享同一实例)."""
    try:
        import billing.routes as br  # type: ignore
        state = br.get_state()  # 始终读最新 (state 可能在 reset_state 后被替换)
        service = state.get("order_service")
        if not service:
            return []
        store = service.store
        all_orders = store.list(limit=10000)
        prefix_start = f"{year:04d}-{month:02d}"
        return [o for o in all_orders if o.created_at.startswith(prefix_start)]
    except Exception as e:
        logger.debug("billing.orders unavailable: %s", e)
        return []


def generate_monthly_report(
    year: int,
    month: int,
    *,
    invoices: Optional[List[Any]] = None,
    orders: Optional[List[Any]] = None,
) -> MonthlyFinancialReport:
    """生成月度财务汇总."""
    if not (1 <= month <= 12):
        raise ValueError(f"month must be in 1..12, got {month}")
    if not (2000 <= year <= 2100):
        raise ValueError(f"year must be in 2000..2100, got {year}")
    if invoices is None:
        invoices = _iter_invoices(year, month)
    if orders is None:
        orders = _iter_orders(year, month)
    report = MonthlyFinancialReport(year=year, month=month)
    # Orders
    by_pm: Dict[str, int] = {}
    by_cur: Dict[str, int] = {}
    for o in orders:
        report.total_orders += 1
        status = getattr(o.status, "value", str(o.status))
        if status == "paid" or status == "fulfilled":
            report.paid_orders += 1
            report.total_revenue_cents += int(getattr(o, "amount_cents", 0) or 0)
        elif status == "refunded":
            report.refunded_orders += 1
            report.total_refund_cents += int(getattr(o, "amount_cents", 0) or 0)
        elif status == "cancelled":
            report.cancelled_orders += 1
        pm = getattr(o, "payment_method", "unknown")
        cur = getattr(o, "currency", "USD")
        if status in ("paid", "fulfilled", "refunded"):
            by_pm[pm] = by_pm.get(pm, 0) + int(getattr(o, "amount_cents", 0) or 0)
        by_cur[cur] = by_cur.get(cur, 0) + int(getattr(o, "amount_cents", 0) or 0)
    report.net_revenue_cents = report.total_revenue_cents - report.total_refund_cents
    report.by_payment_method = by_pm
    report.by_currency = by_cur
    # Invoices
    by_inv_type: Dict[str, Dict[str, int]] = {}
    for inv in invoices:
        report.total_invoices += 1
        # Support both Invoice objects and dicts
        if isinstance(inv, dict):
            it = inv.get("invoice_type", "electronic")
            amt_yuan = float(inv.get("amount", 0) or 0)
            tax = inv.get("tax", {}) or {}
        else:
            it = getattr(inv, "invoice_type", "electronic")
            amt_yuan = float(getattr(inv, "amount", 0) or 0)
            tax = getattr(inv, "tax", {}) or {}
        amt_cents = int(round(amt_yuan * 100))
        b = by_inv_type.setdefault(it, {"count": 0, "amount_cents": 0, "tax_cents": 0})
        b["count"] += 1
        b["amount_cents"] += amt_cents
        tax_yuan = float(tax.get("tax", 0)) if isinstance(tax, dict) else 0
        tax_cents = int(round(tax_yuan * 100))
        b["tax_cents"] += tax_cents
        report.total_invoice_amount_cents += amt_cents
        report.total_tax_cents += tax_cents
    report.by_invoice_type = by_inv_type
    # Top customers (聚合)
    customer_revenue: Dict[str, int] = {}
    for o in orders:
        uid = getattr(o, "user_id", "")
        if uid and (getattr(o.status, "value", str(o.status)) in ("paid", "fulfilled")):
            customer_revenue[uid] = customer_revenue.get(uid, 0) + int(getattr(o, "amount_cents", 0) or 0)
    top = sorted(customer_revenue.items(), key=lambda kv: kv[1], reverse=True)[:10]
    report.top_customers = [
        {"user_id": uid, "revenue_cents": rev}
        for uid, rev in top
    ]
    return report


def get_revenue_by_payment_method(year: int, month: int) -> Dict[str, int]:
    """按支付方式拆分收入."""
    rpt = generate_monthly_report(year, month)
    return rpt.by_payment_method


def get_top_customers_by_revenue(year: int, month: int, n: int = 10) -> List[Dict[str, Any]]:
    rpt = generate_monthly_report(year, month)
    return rpt.top_customers[:n]


def generate_quarterly_report(year: int, quarter: int) -> Dict[str, Any]:
    """季度汇总 (3 个月聚合)."""
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1..4, got {quarter}")
    start_month = (quarter - 1) * 3 + 1
    monthly = []
    for m in range(start_month, start_month + 3):
        monthly.append(generate_monthly_report(year, m))
    agg = {
        "year": year,
        "quarter": quarter,
        "total_orders": sum(r.total_orders for r in monthly),
        "paid_orders": sum(r.paid_orders for r in monthly),
        "total_revenue_cents": sum(r.total_revenue_cents for r in monthly),
        "total_refund_cents": sum(r.total_refund_cents for r in monthly),
        "net_revenue_cents": sum(r.net_revenue_cents for r in monthly),
        "total_invoices": sum(r.total_invoices for r in monthly),
        "total_tax_cents": sum(r.total_tax_cents for r in monthly),
        "by_payment_method": {},
        "monthly_breakdown": [r.to_dict() for r in monthly],
    }
    # 聚合 by_payment_method
    for r in monthly:
        for pm, amt in r.by_payment_method.items():
            agg["by_payment_method"][pm] = agg["by_payment_method"].get(pm, 0) + amt
    return agg


def export_report_csv(report: MonthlyFinancialReport) -> str:
    """导出 CSV (Excel 兼容)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["维度", "值"])
    w.writerow(["年份", report.year])
    w.writerow(["月份", report.month])
    w.writerow(["总订单数", report.total_orders])
    w.writerow(["已支付订单数", report.paid_orders])
    w.writerow(["已退款订单数", report.refunded_orders])
    w.writerow(["已取消订单数", report.cancelled_orders])
    w.writerow(["总收入(分)", report.total_revenue_cents])
    w.writerow(["总退款(分)", report.total_refund_cents])
    w.writerow(["净收入(分)", report.net_revenue_cents])
    w.writerow(["总发票数", report.total_invoices])
    w.writerow(["总税额(分)", report.total_tax_cents])
    w.writerow(["发票总额(分)", report.total_invoice_amount_cents])
    w.writerow([])
    w.writerow(["支付方式", "金额(分)"])
    for pm, amt in report.by_payment_method.items():
        w.writerow([pm, amt])
    w.writerow([])
    w.writerow(["发票类型", "数量", "金额(分)", "税额(分)"])
    for it, b in report.by_invoice_type.items():
        w.writerow([it, b["count"], b["amount_cents"], b["tax_cents"]])
    w.writerow([])
    w.writerow(["Top 客户 user_id", "收入(分)"])
    for c in report.top_customers:
        w.writerow([c["user_id"], c["revenue_cents"]])
    return buf.getvalue()


__all__ = [
    "MonthlyFinancialReport",
    "generate_monthly_report", "get_revenue_by_payment_method", "get_top_customers_by_revenue",
    "generate_quarterly_report", "export_report_csv",
]
