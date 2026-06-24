"""
P4-10-W2: 发票模块 — 国标发票 (中文) + PDF + OFD + SM3 防篡改
- 增值税普通发票 / 增值税专用发票 / 电子发票
- 编号规则: INV-YYYYMMDD-NNNN
- 含税计算: 总额/税额/含税价
- SM3 哈希链防篡改
- OFD (Open Fixed-layout Document) 是中国国家标准电子发票格式 (GB/T 33190-2016),
  此处实现简化版 OFD (XML + zip 容器, 满足可解析可验证)
"""
import os
import io
import json
import zipfile
import hashlib
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 发票 PDF / OFD 输出目录
_INV_DIR = Path(os.getenv("INVOICE_OUTPUT_DIR", "D:/Hermes/生产平台/nanobot-factory/backend/static/invoices"))
_INV_DIR.mkdir(parents=True, exist_ok=True)

TAX_RATE = 0.13  # 增值税 13% (国标默认)


# ---------------------------------------------------------------------------
# SM3 哈希 (复用 contracts 模式)
# ---------------------------------------------------------------------------
def _sm3_hex(data: bytes) -> str:
    try:
        return hashlib.sm3_hex(data)
    except (AttributeError, ValueError):
        return "SM3FALLBACK:" + hashlib.sha256(data).hexdigest()


def sm3_hash(obj: Any) -> str:
    if isinstance(obj, (dict, list)):
        s = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    else:
        s = str(obj)
    return _sm3_hex(s.encode("utf-8"))


# ---------------------------------------------------------------------------
# 编号生成
# ---------------------------------------------------------------------------
_DAILY_COUNTER: Dict[str, int] = {}


def generate_invoice_number() -> str:
    """INV-YYYYMMDD-NNNN 编号."""
    today = datetime.utcnow().strftime("%Y%m%d")
    _DAILY_COUNTER[today] = _DAILY_COUNTER.get(today, 0) + 1
    return f"INV-{today}-{_DAILY_COUNTER[today]:04d}"


# ---------------------------------------------------------------------------
# 税计算
# ---------------------------------------------------------------------------
def calc_tax(amount: float, rate: float = TAX_RATE, inclusive: bool = True) -> Dict[str, float]:
    """含税/不含税计算.

    inclusive=True: amount 为含税总额 → 反推不含税 + 税额
    inclusive=False: amount 为不含税 → 计算税额 + 含税价
    """
    if inclusive:
        net = round(amount / (1 + rate), 2)
        tax = round(amount - net, 2)
        gross = amount
    else:
        tax = round(amount * rate, 2)
        gross = round(amount + tax, 2)
        net = amount
    return {"net": net, "tax": tax, "gross": gross, "rate": rate}


# ---------------------------------------------------------------------------
# 发票数据模型
# ---------------------------------------------------------------------------
class Invoice:
    """发票实体. 内存存储 (生产环境换 PG/SQLite)."""

    def __init__(
        self,
        invoice_no: str,
        invoice_type: str,  # vat_normal / vat_special / electronic
        order_id: str,
        buyer_name: str,
        buyer_tax_id: Optional[str],
        seller_name: str,
        seller_tax_id: str,
        items: List[Dict[str, Any]],
        amount: float,
        tax_rate: float = TAX_RATE,
    ):
        self.invoice_no = invoice_no
        self.invoice_type = invoice_type
        self.order_id = order_id
        self.buyer_name = buyer_name
        self.buyer_tax_id = buyer_tax_id
        self.seller_name = seller_name
        self.seller_tax_id = seller_tax_id
        self.items = items
        self.amount = amount
        self.tax_rate = tax_rate
        self.tax = calc_tax(amount, tax_rate, inclusive=True)
        self.issue_date = datetime.utcnow().strftime("%Y-%m-%d")
        self.created_at = datetime.utcnow().isoformat()
        self.hash_chain: List[str] = []
        self.status = "issued"  # issued / voided / verified
        self._compute_hash()

    def _compute_hash(self):
        canonical = json.dumps(self.to_dict(include_hash=False), sort_keys=True, ensure_ascii=False)
        self.hash_chain.append(_sm3_hex(canonical.encode("utf-8")))

    def to_dict(self, include_hash: bool = True) -> Dict[str, Any]:
        d = {
            "invoice_no": self.invoice_no,
            "invoice_type": self.invoice_type,
            "order_id": self.order_id,
            "buyer_name": self.buyer_name,
            "buyer_tax_id": self.buyer_tax_id,
            "seller_name": self.seller_name,
            "seller_tax_id": self.seller_tax_id,
            "items": self.items,
            "amount": self.amount,
            "tax_rate": self.tax_rate,
            "tax": self.tax,
            "issue_date": self.issue_date,
            "created_at": self.created_at,
            "status": self.status,
        }
        if include_hash:
            d["hash_chain"] = self.hash_chain
        return d


# 进程内存储
_STORE: Dict[str, Invoice] = {}
_BY_ORDER: Dict[str, str] = {}


# ---------------------------------------------------------------------------
# 模板定义
# ---------------------------------------------------------------------------
TEMPLATE_TYPES = {
    "vat_normal": "增值税普通发票",
    "vat_special": "增值税专用发票",
    "electronic": "电子发票 (国标)",
}


def generate_invoice(
    invoice_type: str,
    order_id: str,
    buyer_name: str,
    buyer_tax_id: Optional[str],
    seller_name: str,
    seller_tax_id: str,
    items: List[Dict[str, Any]],
    amount: float,
    tax_rate: float = TAX_RATE,
) -> Invoice:
    if invoice_type not in TEMPLATE_TYPES:
        raise ValueError(f"unknown invoice_type: {invoice_type}")
    if not items:
        raise ValueError("items must not be empty")
    if amount <= 0:
        raise ValueError("amount must be positive")
    invoice_no = generate_invoice_number()
    inv = Invoice(
        invoice_no=invoice_no,
        invoice_type=invoice_type,
        order_id=order_id,
        buyer_name=buyer_name,
        buyer_tax_id=buyer_tax_id,
        seller_name=seller_name,
        seller_tax_id=seller_tax_id,
        items=items,
        amount=amount,
        tax_rate=tax_rate,
    )
    _STORE[invoice_no] = inv
    _BY_ORDER[order_id] = invoice_no
    logger.info("invoice generated: %s order=%s amount=%.2f", invoice_no, order_id, amount)
    return inv


def render_invoice_pdf(inv: Invoice) -> bytes:
    """用 ReportLab 渲染发票 PDF (中文, 国标样式)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        # 尝试注册中文字体
        for font_path in [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
        ]:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont("zh", font_path))
                    break
                except Exception:
                    pass

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, leftMargin=1.5 * cm)
        styles = getSampleStyleSheet()
        font_name = "zh" if "zh" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
        h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=font_name, alignment=1, fontSize=20, spaceAfter=10)
        h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=font_name, fontSize=11, spaceBefore=8, spaceAfter=4)
        body = ParagraphStyle("body", parent=styles["BodyText"], fontName=font_name, fontSize=10, leading=14)

        story = [
            Paragraph(TEMPLATE_TYPES[inv.invoice_type], h1),
            Paragraph(f"发票号码: <b>{inv.invoice_no}</b>", body),
            Paragraph(f"开票日期: {inv.issue_date}", body),
            Spacer(1, 0.3 * cm),
            Paragraph("购买方信息", h2),
        ]
        buyer_data = [
            ["名称:", inv.buyer_name, "纳税人识别号:", inv.buyer_tax_id or "—"],
        ]
        story.append(Table(buyer_data, colWidths=[2 * cm, 6 * cm, 3 * cm, 6 * cm], style=TableStyle([
            ("FONT", (0, 0), (-1, -1), font_name, 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("销售方信息", h2))
        seller_data = [
            ["名称:", inv.seller_name, "纳税人识别号:", inv.seller_tax_id],
        ]
        story.append(Table(seller_data, colWidths=[2 * cm, 6 * cm, 3 * cm, 6 * cm], style=TableStyle([
            ("FONT", (0, 0), (-1, -1), font_name, 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph("商品明细", h2))
        # 明细表
        item_data = [["序号", "商品名称", "规格", "数量", "单价", "金额", "税率", "税额"]]
        for i, item in enumerate(inv.items, 1):
            item_data.append([
                str(i),
                item.get("name", "—"),
                item.get("spec", "—"),
                str(item.get("qty", 1)),
                f"{item.get('unit_price', inv.amount):.2f}",
                f"{item.get('amount', inv.amount):.2f}",
                f"{inv.tax_rate * 100:.0f}%",
                f"{inv.tax['tax']:.2f}",
            ])
        # 合计
        item_data.append([
            "合计", "", "", "", "",
            f"{inv.tax['net']:.2f}",
            f"{inv.tax_rate * 100:.0f}%",
            f"{inv.tax['tax']:.2f}",
        ])
        story.append(Table(item_data, colWidths=[1 * cm, 4 * cm, 1.5 * cm, 1.2 * cm, 1.5 * cm, 1.8 * cm, 1.2 * cm, 1.5 * cm], style=TableStyle([
            ("FONT", (0, 0), (-1, -1), font_name, 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (1, 1), (1, -1), "LEFT"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.lightyellow),
            ("FONT", (0, -1), (-1, -1), font_name, 9),
        ])))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(f"价税合计 (大写): <b>{_amount_to_chinese(inv.tax['gross'])}</b>", body))
        story.append(Paragraph(f"价税合计 (小写): <b>¥ {inv.tax['gross']:.2f}</b>", body))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(f"备注: 关联订单 {inv.order_id}", body))
        if inv.hash_chain:
            story.append(Spacer(1, 0.2 * cm))
            story.append(Paragraph(f"<font size='7' color='grey'>SM3 防篡改指纹: {inv.hash_chain[0]}</font>", body))
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("销售方 (盖章): ____________________", body))
        doc.build(story)
        return buf.getvalue()
    except Exception as e:
        logger.exception("invoice PDF render failed: %s, using minimal fallback", e)
        return _minimal_invoice_pdf(inv)


def _minimal_invoice_pdf(inv: Invoice) -> bytes:
    """最小发票 PDF (无中文字体时回退)."""
    text = (
        f"{TEMPLATE_TYPES[inv.invoice_type]}\n"
        f"No: {inv.invoice_no}\n"
        f"Date: {inv.issue_date}\n"
        f"Buyer: {inv.buyer_name}\n"
        f"Seller: {inv.seller_name}\n"
        f"Amount: {inv.amount:.2f}\n"
        f"Tax: {inv.tax['tax']:.2f}\n"
        f"Total: {inv.tax['gross']:.2f}\n"
        f"Order: {inv.order_id}\n"
        f"SM3: {inv.hash_chain[0] if inv.hash_chain else ''}\n"
    ).encode("ascii", errors="replace")
    # 简化 PDF 字节
    stream = b"BT /F1 10 Tf 50 800 Td 14 TL\n" + text.replace(b"\n", b" ") + b" ET"
    pdf = b"%PDF-1.4\n"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("ascii")
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode("ascii")
    pdf += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    return pdf


def _amount_to_chinese(amount: float) -> str:
    """金额转中文大写 (简化版)."""
    if amount < 0.01:
        return "零元整"
    units = ["", "拾", "佰", "仟"]
    big = ["", "万", "亿", "兆"]
    digits = "零壹贰叁肆伍陆柒捌玖"
    yuan = int(amount)
    fen = int(round((amount - yuan) * 100))
    if yuan == 0:
        s = "零"
    else:
        s = ""
        s_yuan = str(yuan)
        # 反向
        groups = []
        while s_yuan:
            groups.append(s_yuan[-4:])
            s_yuan = s_yuan[:-4]
        for gi, g in enumerate(groups):
            g = g.zfill(4)
            part = ""
            for i, ch in enumerate(g):
                d = int(ch)
                u = units[3 - i]
                if d == 0:
                    if part and not part.endswith("零"):
                        part += "零"
                else:
                    part += digits[d] + u
            part = part.rstrip("零")
            if part:
                s += part + big[gi]
            else:
                if s and not s.endswith("零"):
                    s += "零"
        s = s.rstrip("零")
    s += "元"
    if fen:
        s += digits[fen // 10] + "角" + digits[fen % 10] + "分"
    else:
        s += "整"
    return s


def render_invoice_ofd(inv: Invoice) -> bytes:
    """生成 OFD 格式电子发票 (GB/T 33190 简化版).

    OFD = Open Fixed-layout Document, 国家级标准电子文档格式.
    本实现: XML + zip 容器 (OFD 实际是 OFD 容器 = zip), 满足可解析可验证.
    """
    body = inv.to_dict()
    # OFD 文档结构 (简化)
    ofd_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ofd:OFD xmlns:ofd="http://www.ofdspec.org" Version="1.0" DocType="Invoice">
  <ofd:DocBody>
    <ofd:DocInfo>
      <ofd:DocID>{inv.invoice_no}</ofd:DocID>
      <ofd:Title>{TEMPLATE_TYPES[inv.invoice_type]}</ofd:Title>
      <ofd:Author>{inv.seller_name}</ofd:Author>
      <ofd:CreationDate>{inv.created_at}</ofd:CreationDate>
    </ofd:DocInfo>
    <ofd:DocContent>
      <ofd:Invoice>
        <ofd:InvoiceNo>{inv.invoice_no}</ofd:InvoiceNo>
        <ofd:InvoiceType>{inv.invoice_type}</ofd:InvoiceType>
        <ofd:IssueDate>{inv.issue_date}</ofd:IssueDate>
        <ofd:OrderId>{inv.order_id}</ofd:OrderId>
        <ofd:Buyer>
          <ofd:Name>{inv.buyer_name}</ofd:Name>
          <ofd:TaxId>{inv.buyer_tax_id or ''}</ofd:TaxId>
        </ofd:Buyer>
        <ofd:Seller>
          <ofd:Name>{inv.seller_name}</ofd:Name>
          <ofd:TaxId>{inv.seller_tax_id}</ofd:TaxId>
        </ofd:Seller>
        <ofd:Items>
{''.join(f'<ofd:Item><ofd:Name>{it.get("name","")}</ofd:Name><ofd:Qty>{it.get("qty",1)}</ofd:Qty><ofd:Amount>{it.get("amount",inv.amount):.2f}</ofd:Amount></ofd:Item>' for it in inv.items)}
        </ofd:Items>
        <ofd:Tax>
          <ofd:Rate>{inv.tax_rate:.4f}</ofd:Rate>
          <ofd:NetAmount>{inv.tax['net']:.2f}</ofd:NetAmount>
          <ofd:TaxAmount>{inv.tax['tax']:.2f}</ofd:TaxAmount>
          <ofd:GrossAmount>{inv.tax['gross']:.2f}</ofd:GrossAmount>
        </ofd:Tax>
        <ofd:Signature>
          <ofd:Algorithm>SM3</ofd:Algorithm>
          <ofd:HashValue>{inv.hash_chain[0] if inv.hash_chain else ''}</ofd:HashValue>
        </ofd:Signature>
      </ofd:Invoice>
    </ofd:DocContent>
  </ofd:DocBody>
</ofd:OFD>"""
    # OFD 容器 = zip, 包含 ofd.xml + signature.xml
    signature_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Signature xmlns="http://www.ofdspec.org" Algorithm="SM3">
  <SignedInfo>
    <Reference URI="ofd.xml">
      <DigestMethod Algorithm="SM3"/>
      <DigestValue>{inv.hash_chain[0] if inv.hash_chain else ''}</DigestValue>
    </Reference>
  </SignedInfo>
  <SignatureValue>{inv.hash_chain[0] if inv.hash_chain else ''}</SignatureValue>
  <KeyInfo>
    <X509Data>
      <X509SubjectName>CN={inv.seller_name}, O=智影纳米机器人</X509SubjectName>
    </X509Data>
  </KeyInfo>
</Signature>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("ofd.xml", ofd_xml)
        z.writestr("signature.xml", signature_xml)
        z.writestr("META/doc.json", json.dumps(body, ensure_ascii=False, indent=2))
    return buf.getvalue()


def save_invoice_pdf(inv: Invoice) -> Path:
    p = _INV_DIR / f"{inv.invoice_no}.pdf"
    p.write_bytes(render_invoice_pdf(inv))
    return p


def save_invoice_ofd(inv: Invoice) -> Path:
    p = _INV_DIR / f"{inv.invoice_no}.ofd"
    p.write_bytes(render_invoice_ofd(inv))
    return p


def verify_invoice(invoice_no: str) -> Dict[str, Any]:
    """验证发票防篡改 (重算 SM3 哈希与存储的 hash_chain 对比)."""
    inv = _STORE.get(invoice_no)
    if not inv:
        return {"valid": False, "error": "invoice not found"}
    # 重算 hash
    canonical = json.dumps(inv.to_dict(include_hash=False), sort_keys=True, ensure_ascii=False)
    current_hash = _sm3_hex(canonical.encode("utf-8"))
    stored = inv.hash_chain[0] if inv.hash_chain else None
    valid = (current_hash == stored)
    return {
        "valid": valid,
        "invoice_no": invoice_no,
        "stored_hash": stored,
        "computed_hash": current_hash,
        "invoice": inv.to_dict() if valid else None,
    }


def get_invoice(invoice_no: str) -> Optional[Invoice]:
    return _STORE.get(invoice_no)


def get_invoice_by_order(order_id: str) -> Optional[Invoice]:
    no = _BY_ORDER.get(order_id)
    if no:
        return _STORE.get(no)
    return None


def list_invoices(invoice_type: Optional[str] = None, order_id: Optional[str] = None) -> List[Invoice]:
    items = list(_STORE.values())
    if invoice_type:
        items = [i for i in items if i.invoice_type == invoice_type]
    if order_id:
        items = [i for i in items if i.order_id == order_id]
    return items


# ---------------------------------------------------------------------------
# 集成钩子 (与 W1 Order 配合)
# ---------------------------------------------------------------------------
def on_order_paid(
    order_id: str,
    buyer_name: str,
    buyer_tax_id: Optional[str],
    amount: float,
    items: Optional[List[Dict[str, Any]]] = None,
    seller_name: str = "智影纳米机器人科技有限公司",
    seller_tax_id: str = "91110000XXXXXXXX5X",
) -> Invoice:
    """Order paid 后自动生成电子发票."""
    if items is None:
        items = [{"name": "数据生成服务", "spec": "标准", "qty": 1, "unit_price": amount, "amount": amount}]
    return generate_invoice(
        invoice_type="electronic",
        order_id=order_id,
        buyer_name=buyer_name,
        buyer_tax_id=buyer_tax_id,
        seller_name=seller_name,
        seller_tax_id=seller_tax_id,
        items=items,
        amount=amount,
    )
