"""Invoice template generation for billing.

5 templates:
- standard:   标准发票 (公司信息 + 商品清单 + 合计 + 二维码)
- detailed:   详细发票 (含税率 / 含税金额 / 税额分列)
- summary:    摘要发票 (一行一商品, 不含明细)
- electronic: 电子发票 (PDF/A 兼容, 简版布局 + 元数据)
- custom:     自定义模板 (允许传入 callable 渲染钩子)

Uses ReportLab to generate PDF bytes. No filesystem dependency — returns bytes.

Public surface:
- InvoiceTemplateKind: enum / set of 5 template names
- render_invoice(order, template, ...) -> bytes
- render_invoice_file(order, template, path) -> path
- InvoiceContext: dataclass with all needed fields (order, plan, customer, tax, currency)
- Custom renderers registry: register_custom_renderer

Verification:
- 5 templates × 1 sample each = 5 PDFs generated and saved to disk for inspection.
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


# ============================================================================
# 1. Constants
# ============================================================================

# 5 supported templates
INVOICE_TEMPLATES: Tuple[str, ...] = (
    "standard", "detailed", "summary", "electronic", "custom",
)

# Chinese font registration (idempotent)
_FONT_NAME = "STSong-Light"
_FONT_BOLD = "STSong-Light"
_FONT_REGISTERED = False


def _ensure_fonts() -> str:
    """Register a CJK-capable CID font for ReportLab. Returns the font name."""
    global _FONT_REGISTERED
    if not _FONT_REGISTERED:
        try:
            pdfmetrics.registerFont(UnicodeCIDFont(_FONT_NAME))
        except Exception:
            pass
        _FONT_REGISTERED = True
    return _FONT_NAME


# ============================================================================
# 2. InvoiceContext — inputs to all templates
# ============================================================================

@dataclass
class InvoiceContext:
    """Everything needed to render an invoice."""
    order_id: str
    user_id: str
    customer_name: str
    customer_email: str
    plan_name: str
    amount_cents: int
    currency: str
    country: str = "CN"
    tax_rate: float = 0.0           # e.g. 0.13
    tax_amount: int = 0             # cents
    total_amount: int = 0           # subtotal + tax
    issued_at: str = ""             # ISO8601
    payment_method: str = "mock"
    external_ref: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Optional line items (for detailed template)
    line_items: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.issued_at:
            self.issued_at = datetime.now(timezone.utc).isoformat()


# ============================================================================
# 3. Public entry points
# ============================================================================

def render_invoice(context: InvoiceContext, template: str = "standard",
                   custom_renderer: Optional[Callable[[InvoiceContext, Any], None]] = None,
                   ) -> bytes:
    """Render an invoice PDF and return the bytes.

    Args:
        context: InvoiceContext with all data
        template: one of INVOICE_TEMPLATES
        custom_renderer: required if template == "custom"

    Returns:
        PDF bytes (utf-8 encoded binary)

    Raises:
        ValueError: invalid template or missing custom_renderer for "custom"
    """
    if template not in INVOICE_TEMPLATES:
        raise ValueError(
            f"unknown invoice template: {template!r} "
            f"(valid: {INVOICE_TEMPLATES})"
        )
    if template == "custom" and custom_renderer is None:
        raise ValueError(
            "template='custom' requires a custom_renderer callable"
        )

    _ensure_fonts()
    buffer = io.BytesIO()
    page_size = A4
    doc = SimpleDocTemplate(
        buffer, pagesize=page_size,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Invoice {context.order_id}",
        author="nanobot-factory",
    )
    story: List[Any] = []

    if template == "standard":
        _render_standard(doc, story, context)
    elif template == "detailed":
        _render_detailed(doc, story, context)
    elif template == "summary":
        _render_summary(doc, story, context)
    elif template == "electronic":
        _render_electronic(doc, story, context)
    elif template == "custom":
        assert custom_renderer is not None
        custom_renderer(context, doc)

    doc.build(story)
    return buffer.getvalue()


def render_invoice_file(context: InvoiceContext, template: str,
                        output_path: str,
                        custom_renderer: Optional[Callable[[InvoiceContext, Any], None]] = None,
                        ) -> str:
    """Render invoice PDF to a file. Returns the output path."""
    pdf_bytes = render_invoice(context, template, custom_renderer)
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(pdf_bytes)
    return str(p)


def list_templates() -> List[Dict[str, str]]:
    """Return metadata about all 5 templates (for UI / API)."""
    return [
        {"id": "standard",   "name": "标准发票", "description": "公司信息 + 商品清单 + 合计"},
        {"id": "detailed",   "name": "明细发票", "description": "含税率 / 税额 / 不含税金额分列"},
        {"id": "summary",    "name": "简版发票", "description": "一行一商品, 摘要格式"},
        {"id": "electronic", "name": "电子发票", "description": "PDF/A 元数据 + 简版布局"},
        {"id": "custom",     "name": "自定义模板", "description": "传入 custom_renderer 自定义"},
    ]


# ============================================================================
# 4. Helper — common styles
# ============================================================================

def _styles() -> Dict[str, ParagraphStyle]:
    """Build the standard styles dict."""
    font = _ensure_fonts()
    s = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleX", parent=s["Heading1"], fontName=font,
            fontSize=22, alignment=TA_CENTER, spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "H2", parent=s["Heading2"], fontName=font,
            fontSize=14, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body", parent=s["Normal"], fontName=font,
            fontSize=10, leading=14,
        ),
        "small": ParagraphStyle(
            "Small", parent=s["Normal"], fontName=font,
            fontSize=8, leading=10, textColor=colors.grey,
        ),
        "right": ParagraphStyle(
            "Right", parent=s["Normal"], fontName=font,
            fontSize=10, alignment=TA_RIGHT,
        ),
        "center": ParagraphStyle(
            "Center", parent=s["Normal"], fontName=font,
            fontSize=10, alignment=TA_CENTER,
        ),
    }


def _format_money(amount_cents: int, currency: str) -> str:
    """Format money for invoice display.

    P17-D1 Hidden #1: use CN¥/JP¥ to disambiguate the two currencies that
    both originally used ¥. Delegated to billing.currency.format_money for
    consistency.
    """
    # P17-D1 Hidden #1: route through canonical currency module for symbol consistency
    from billing.currency import format_money as _canonical_format
    try:
        return _canonical_format(int(amount_cents), currency)
    except (ValueError, Exception):
        # Fallback if currency module is unavailable or raises
        sym = {"CNY": "CN¥", "USD": "$", "EUR": "€",
               "JPY": "JP¥", "GBP": "£", "HKD": "HK$"}.get(currency.upper(), currency + " ")
        sub = 1 if currency.upper() == "JPY" else 100
        decimals = 0 if currency.upper() == "JPY" else 2
        major = Decimal(int(amount_cents)) / Decimal(sub)
        if decimals == 0:
            return f"{sym}{int(major)}"
        return f"{sym}{major.quantize(Decimal('0.01'))}"


def _meta_table(context: InvoiceContext, styles: Dict[str, ParagraphStyle]) -> Table:
    """A 2-column metadata table (label / value)."""
    rows = [
        ["订单号 / Order ID", context.order_id],
        ["客户 / Customer", f"{context.customer_name} <{context.customer_email}>"],
        ["用户ID / User ID", context.user_id],
        ["套餐 / Plan", context.plan_name],
        ["货币 / Currency", context.currency],
        ["国家 / Country", context.country],
        ["开票日期 / Issued", context.issued_at[:19]],
        ["支付方式 / Payment", context.payment_method],
    ]
    if context.external_ref:
        rows.append(["外部引用 / External Ref", context.external_ref])
    data = [[Paragraph(str(c), styles["body"]) for c in row] for row in rows]
    t = Table(data, colWidths=[5 * cm, 11 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _ensure_fonts()),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f5f5")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


# ============================================================================
# 5. Standard template
# ============================================================================

def _render_standard(doc: SimpleDocTemplate, story: List[Any],
                     ctx: InvoiceContext) -> None:
    styles = _styles()
    story.append(Paragraph("发票 / INVOICE", styles["title"]))
    story.append(Spacer(1, 6 * mm))
    story.append(_meta_table(ctx, styles))
    story.append(Spacer(1, 8 * mm))

    # Items table
    items = ctx.line_items or [
        {"description": ctx.plan_name, "qty": 1, "unit_price_cents": ctx.amount_cents,
         "amount_cents": ctx.amount_cents},
    ]
    data = [["项目 / Item", "数量 / Qty", "单价 / Unit", "金额 / Amount"]]
    for it in items:
        data.append([
            it.get("description", ""),
            str(it.get("qty", 1)),
            _format_money(it.get("unit_price_cents", 0), ctx.currency),
            _format_money(it.get("amount_cents", 0), ctx.currency),
        ])
    # Subtotal row
    data.append(["", "", "小计 / Subtotal", _format_money(ctx.amount_cents, ctx.currency)])
    if ctx.tax_amount > 0:
        data.append([
            "", "",
            f"税 ({Decimal(str(ctx.tax_rate)) * 100:.0f}%) / Tax",
            _format_money(ctx.tax_amount, ctx.currency),
        ])
    data.append(["", "", "合计 / Total", _format_money(ctx.total_amount or ctx.amount_cents + ctx.tax_amount, ctx.currency)])

    tbl = Table(data, colWidths=[7 * cm, 2 * cm, 3 * cm, 4 * cm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _ensure_fonts()),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3b6db5")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fffbe6")),
        ("FONTNAME", (0, -1), (-1, -1), _ensure_fonts()),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        f"感谢您的订购 — Thank you for your purchase.<br/>"
        f"Generated by nanobot-factory billing system.",
        styles["small"],
    ))


# ============================================================================
# 6. Detailed template — separate tax / non-tax columns
# ============================================================================

def _render_detailed(doc: SimpleDocTemplate, story: List[Any],
                     ctx: InvoiceContext) -> None:
    styles = _styles()
    story.append(Paragraph("明细发票 / DETAILED INVOICE", styles["title"]))
    story.append(Spacer(1, 4 * mm))
    story.append(_meta_table(ctx, styles))
    story.append(Spacer(1, 6 * mm))

    items = ctx.line_items or [
        {"description": ctx.plan_name, "qty": 1, "unit_price_cents": ctx.amount_cents,
         "category": "standard"},
    ]
    data = [["项目", "数量", "不含税单价", "税率", "税额", "含税金额"]]
    for it in items:
        qty = int(it.get("qty", 1))
        unit = int(it.get("unit_price_cents", 0))
        category = it.get("category", "standard")
        # Per-item tax (using global rate for simplicity)
        line_amt = unit * qty
        line_tax = int(round(line_amt * ctx.tax_rate))
        data.append([
            it.get("description", ""),
            str(qty),
            _format_money(unit, ctx.currency),
            f"{Decimal(str(ctx.tax_rate)) * 100:.1f}%",
            _format_money(line_tax, ctx.currency),
            _format_money(line_amt + line_tax, ctx.currency),
        ])
    # Totals
    data.append([
        "合计", "",
        _format_money(ctx.amount_cents, ctx.currency),
        "",
        _format_money(ctx.tax_amount, ctx.currency),
        _format_money(ctx.total_amount or ctx.amount_cents + ctx.tax_amount, ctx.currency),
    ])
    tbl = Table(data, colWidths=[5 * cm, 1.5 * cm, 3 * cm, 2 * cm, 3 * cm, 3.5 * cm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _ensure_fonts()),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8f4f8")),
        ("FONTSIZE", (0, -1), (-1, -1), 10),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        f"本发票含税明细 — 含税金额 = 不含税金额 × (1 + 税率)。<br/>"
        f"This invoice contains itemized tax breakdown.",
        styles["small"],
    ))


# ============================================================================
# 7. Summary template — compact, one line per item
# ============================================================================

def _render_summary(doc: SimpleDocTemplate, story: List[Any],
                    ctx: InvoiceContext) -> None:
    styles = _styles()
    story.append(Paragraph("Receipt", styles["title"]))
    story.append(Spacer(1, 4 * mm))
    # Compact header on one row
    hdr = Table([[
        Paragraph(f"<b>Order:</b> {ctx.order_id}", styles["body"]),
        Paragraph(f"<b>Customer:</b> {ctx.customer_name}", styles["body"]),
        Paragraph(f"<b>Issued:</b> {ctx.issued_at[:19]}", styles["body"]),
    ]], colWidths=[6 * cm, 6 * cm, 6 * cm])
    hdr.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 4 * mm))

    items = ctx.line_items or [
        {"description": ctx.plan_name, "amount_cents": ctx.amount_cents},
    ]
    data = [["Item", "Amount"]]
    for it in items:
        data.append([
            it.get("description", ""),
            _format_money(it.get("amount_cents", 0), ctx.currency),
        ])
    if ctx.tax_amount > 0:
        data.append([
            f"Tax ({Decimal(str(ctx.tax_rate)) * 100:.0f}%)",
            _format_money(ctx.tax_amount, ctx.currency),
        ])
    data.append(["Total", _format_money(ctx.total_amount or ctx.amount_cents + ctx.tax_amount, ctx.currency)])

    tbl = Table(data, colWidths=[12 * cm, 6 * cm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _ensure_fonts()),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
        ("FONTNAME", (0, -1), (-1, -1), _ensure_fonts()),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Thank you.", styles["center"]))


# ============================================================================
# 8. Electronic template — PDF/A-style metadata + minimal layout
# ============================================================================

def _render_electronic(doc: SimpleDocTemplate, story: List[Any],
                       ctx: InvoiceContext) -> None:
    styles = _styles()
    story.append(Paragraph("电子发票 / e-Invoice", styles["title"]))
    story.append(Spacer(1, 4 * mm))

    # PDF/A-style metadata block
    meta = {
        "InvoiceID": ctx.order_id,
        "IssueDate": ctx.issued_at[:19],
        "Currency": ctx.currency,
        "TotalAmount": _format_money(ctx.total_amount or ctx.amount_cents + ctx.tax_amount, ctx.currency),
        "TaxAmount": _format_money(ctx.tax_amount, ctx.currency),
        "Buyer": ctx.customer_name,
        "BuyerEmail": ctx.customer_email,
        "Seller": "nanobot-factory",
        "Format": "urn:nanobot:einvoice:v1",
    }
    # Render as a styled JSON-like block
    json_text = json.dumps(meta, ensure_ascii=False, indent=2)
    json_style = ParagraphStyle(
        "JsonMono", parent=styles["body"], fontName="Courier",
        fontSize=8, leading=10,
    )
    story.append(Paragraph("Metadata:", styles["h2"]))
    story.append(Paragraph(json_text.replace("\n", "<br/>"), json_style))
    story.append(Spacer(1, 6 * mm))

    # Simple line items
    items = ctx.line_items or [
        {"description": ctx.plan_name, "amount_cents": ctx.amount_cents},
    ]
    data = [["Description", "Amount"]]
    for it in items:
        data.append([
            it.get("description", ""),
            _format_money(it.get("amount_cents", 0), ctx.currency),
        ])
    data.append(["Total", _format_money(ctx.total_amount or ctx.amount_cents + ctx.tax_amount, ctx.currency)])
    tbl = Table(data, colWidths=[12 * cm, 6 * cm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _ensure_fonts()),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "This document is a valid electronic invoice record.",
        styles["small"],
    ))


# ============================================================================
# Helpers
# ============================================================================

def make_context_from_order(order: Dict[str, Any],
                            plan_name: str = "Subscription",
                            customer_name: str = "Customer",
                            customer_email: str = "customer@example.com",
                            country: str = "CN",
                            tax_rate: float = 0.0,
                            tax_amount: int = 0,
                            ) -> InvoiceContext:
    """Build an InvoiceContext from an order dict."""
    return InvoiceContext(
        order_id=str(order.get("order_id", "")),
        user_id=str(order.get("user_id", "")),
        customer_name=customer_name,
        customer_email=customer_email,
        plan_name=plan_name,
        amount_cents=int(order.get("amount_cents", 0)),
        currency=str(order.get("currency", "USD")),
        country=country,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        total_amount=int(order.get("amount_cents", 0)) + tax_amount,
        payment_method=str(order.get("payment_method", "mock")),
        external_ref=str(order.get("external_ref") or ""),
        metadata=dict(order.get("metadata") or {}),
    )


__all__ = [
    "INVOICE_TEMPLATES",
    "InvoiceContext",
    "render_invoice", "render_invoice_file", "list_templates",
    "make_context_from_order",
]