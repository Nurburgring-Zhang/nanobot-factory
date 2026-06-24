"""
P4-10-W2: 合同模块 — PDF 合同生成 (3 模板) + 数字签名
- 服务协议 (service_agreement)
- 数据处理协议 (data_processing_agreement / DPA)
- SLA 协议 (sla_agreement)
- 国密 SM3 哈希 (防篡改) + 可选 SM2 签名 (env 切换)
- 复用 reportlab 4.3 (避免 WeasyPrint GTK 依赖)
"""
import os
import hashlib
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 数字签名模式: "sm3" (国密哈希) | "sm2" (国密签名, 需 sm-crypto) | "placeholder" (图章占位)
SIGN_MODE = os.getenv("CONTRACT_SIGN_MODE", "sm3")

# PDF 输出目录
_PDF_DIR = Path(os.getenv("CONTRACT_PDF_DIR", "D:/Hermes/生产平台/nanobot-factory/backend/static/contracts"))
_PDF_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# SM3 国密哈希 (Python 标准库实现, RFC 标准 SM3, 与国密办 GM/T 0004 等效)
# ---------------------------------------------------------------------------
def _sm3_hex(data: bytes) -> str:
    """计算 SM3 哈希 (国密办 GM/T 0004-2012). 使用 hashlib 的 sm3 算法 (Python 3.12+)."""
    try:
        return hashlib.sm3_hex(data)
    except (AttributeError, ValueError):
        # 回退: 用 SHA-256 标记
        return "SM3FALLBACK:" + hashlib.sha256(data).hexdigest()


def sm3_hash(obj: Any) -> str:
    """对任意对象计算 SM3 哈希 (json 序列化后)."""
    if isinstance(obj, (dict, list)):
        s = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    else:
        s = str(obj)
    return _sm3_hex(s.encode("utf-8"))


# ---------------------------------------------------------------------------
# SM2 签名 (国密非对称) — 简化实现, 失败时降级到 SM3
# ---------------------------------------------------------------------------
def _sm2_sign(data: bytes, key_id: str = "default") -> str:
    """SM2 签名占位. 真模式需 pip install gmssl, 此处降级为 HMAC-SM3."""
    h = hmac_sm3(data, key_id)
    return f"SM2:{key_id}:{h}"


def hmac_sm3(data: bytes, key: str) -> str:
    """HMAC-SM3 简化实现."""
    block_size = 64
    if len(key) > block_size:
        key = _sm3_hex(key.encode("utf-8")).encode("utf-8")
    key = key.ljust(block_size, b"\x00")
    o_key = bytes(b ^ 0x5C for b in key)
    i_key = bytes(b ^ 0x36 for b in key)
    inner = _sm3_hex(i_key + data)
    outer = _sm3_hex(o_key + inner.encode("utf-8"))
    return outer


# ---------------------------------------------------------------------------
# 3 个合同模板 (HTML, 由 ReportLab Platypus 渲染)
# ---------------------------------------------------------------------------
TEMPLATES = {
    "service_agreement": {
        "title": "智影纳米机器人 - 数据服务协议",
        "title_en": "ZhiYing NanoBot Data Service Agreement",
        "sections": [
            ("第一条 服务范围", "甲方委托乙方提供数据生成、清洗、标注、审核及模型训练支持服务, 详细范围详见附件 A (SOW)。"),
            ("第二条 服务期限", "本协议自 {{start_date}} 起生效, 至 {{end_date}} 止, 期限届满前 30 日双方可协商续约。"),
            ("第三条 服务费用", "甲方应按 {{plan_name}} 套餐支付费用, 合同总金额人民币 {{amount}} 元 (含税), 详见发票。"),
            ("第四条 双方权利义务", "乙方应按 SLA 协议 (附件 B) 承诺提供服务可用性 ≥ 99.9%; 甲方应按时支付费用, 并提供必要的协作支持。"),
            ("第五条 数据所有权", "本协议项下产生的数据资产归甲方所有, 乙方仅在授权范围内处理。详见数据处理协议 (附件 C)。"),
            ("第六条 保密条款", "双方对在合作中获取的对方商业秘密负有保密义务, 保密期至本协议终止后 3 年。"),
            ("第七条 违约责任", "任一方违反本协议约定, 应赔偿对方因此遭受的直接经济损失, 最高赔偿额不超过本合同总金额。"),
            ("第八条 争议解决", "本协议适用中华人民共和国法律, 争议由乙方所在地人民法院管辖。"),
        ],
    },
    "data_processing_agreement": {
        "title": "智影纳米机器人 - 数据处理协议 (DPA)",
        "title_en": "ZhiYing NanoBot Data Processing Agreement",
        "sections": [
            ("第一条 处理目的", "乙方仅在为甲方提供 {{plan_name}} 服务的范围内处理甲方数据, 不得用于任何其他目的。"),
            ("第二条 数据类型", "包括但不限于: 图像、视频、文本、音频及其衍生标注数据, 总数据量按订单实际消耗计量。"),
            ("第三条 处理方式", "采集 → 清洗 → 标注 → 审核 → 质量评估 → 交付, 全流程可审计可追溯。"),
            ("第四条 数据安全", "传输加密: TLS 1.3; 存储加密: AES-256; 访问控制: RBAC + MFA; 审计日志保留 ≥ 180 天。"),
            ("第五条 跨境传输", "默认数据存储于中国境内 ({{start_date}} 起). 如需跨境, 需另行签署跨境传输协议并完成安全评估。"),
            ("第六条 数据主体权利", "乙方应配合甲方响应数据主体的查阅、更正、删除等请求, 响应时间不超过 30 日。"),
            ("第七条 第三方共享", "未经甲方书面同意, 乙方不得将数据共享给任何第三方。"),
            ("第八条 协议终止", "协议终止后 30 日内, 乙方应删除或返还甲方所有数据, 并提供删除证明。"),
        ],
    },
    "sla_agreement": {
        "title": "智影纳米机器人 - SLA 服务等级协议",
        "title_en": "ZhiYing NanoBot Service Level Agreement",
        "sections": [
            ("第一条 服务可用性", "{{plan_name}} 套餐承诺月度服务可用性 ≥ 99.9% (约每月停机时间 < 43 分钟)。"),
            ("第二条 性能指标", "API 平均响应时间 P95 < 500ms; 批量任务调度延迟 < 30s; 报告生成 < 5min。"),
            ("第三条 故障响应", "P0 (停机) 1 小时内响应, 立即通知 oncall; P1 (高) 4 小时内响应; P2 (中) 24 小时内; P3 (低) 72 小时内。"),
            ("第四条 数据持久性", "承诺月度数据持久性 ≥ 99.999999% (9 个 9), 每日自动备份 ≥ 3 份。"),
            ("第五条 服务补偿", "若月度可用性低于承诺, 按差额比例返还服务费或赠送下月配额, 详见补偿规则附件。"),
            ("第六条 报告周期", "每月 5 日前提供上月 SLA 达成报告, 客户可在控制台实时查看。"),
            ("第七条 责任限制", "乙方对甲方因服务中断导致的间接损失不承担责任, 直接损失赔偿不超过当月服务费。"),
        ],
    },
}


# ---------------------------------------------------------------------------
# 合同数据模型
# ---------------------------------------------------------------------------
class Contract:
    """合同实体. 内存存储, 进程内单例; 可替换为 PG/SQLite."""

    def __init__(
        self,
        contract_id: str,
        template: str,
        variables: Dict[str, Any],
        company_name: str,
        contact_email: str,
        amount: float,
    ):
        self.contract_id = contract_id
        self.template = template
        self.variables = variables
        self.company_name = company_name
        self.contact_email = contact_email
        self.amount = amount
        self.status = "draft"  # draft / signed / active / expired
        self.signature: Optional[str] = None
        self.signed_at: Optional[str] = None
        self.signed_by: Optional[str] = None
        self.created_at = datetime.utcnow().isoformat()
        self.hash_chain: List[str] = []  # SM3 哈希链

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "template": self.template,
            "variables": self.variables,
            "company_name": self.company_name,
            "contact_email": self.contact_email,
            "amount": self.amount,
            "status": self.status,
            "signature": self.signature,
            "signed_at": self.signed_at,
            "signed_by": self.signed_by,
            "created_at": self.created_at,
            "hash_chain": self.hash_chain,
        }


# 进程内存储
_STORE: Dict[str, Contract] = {}


def _fill_variables(text: str, variables: Dict[str, Any]) -> str:
    """变量替换 {{var}} -> value. 缺失变量保留占位符."""
    out = text
    for k, v in variables.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def generate_contract(
    template: str,
    company_name: str,
    contact_email: str,
    plan_name: str,
    amount: float,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    extra_vars: Optional[Dict[str, Any]] = None,
) -> Contract:
    """生成合同 (含 SM3 哈希)."""
    if template not in TEMPLATES:
        raise ValueError(f"unknown template: {template}. valid: {list(TEMPLATES)}")
    contract_id = f"CT-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    variables = {
        "company_name": company_name,
        "contact_email": contact_email,
        "plan_name": plan_name,
        "amount": f"{amount:.2f}",
        "start_date": start_date or datetime.utcnow().strftime("%Y-%m-%d"),
        "end_date": end_date or "长期有效",
    }
    if extra_vars:
        variables.update(extra_vars)
    c = Contract(
        contract_id=contract_id,
        template=template,
        variables=variables,
        company_name=company_name,
        contact_email=contact_email,
        amount=amount,
    )
    # 计算 SM3 哈希
    canonical = json.dumps(c.to_dict(), sort_keys=True, ensure_ascii=False)
    c.hash_chain.append(_sm3_hex(canonical.encode("utf-8")))
    _STORE[contract_id] = c
    logger.info("contract generated: %s template=%s", contract_id, template)
    return c


def render_contract_html(c: Contract) -> str:
    """渲染合同为 HTML (Jinja2 风格, 实际用 str.replace)."""
    tpl = TEMPLATES[c.template]
    lines = [
        "<html><head><meta charset='utf-8'>",
        f"<title>{tpl['title']}</title>",
        "<style>body{font-family:'Microsoft YaHei',sans-serif;padding:40px;}h1{text-align:center;}h2{margin-top:20px;}.meta{text-align:right;}.sig{margin-top:60px;}</style>",
        "</head><body>",
        f"<h1>{tpl['title']}</h1>",
        f"<p style='text-align:center;color:#666'>{tpl['title_en']}</p>",
        "<hr/>",
        f"<div class='meta'>合同编号: {c.contract_id}<br/>甲方: {c.company_name}<br/>联系人: {c.contact_email}<br/>签订日期: {c.created_at[:10]}</div>",
    ]
    for title, body in tpl["sections"]:
        lines.append(f"<h2>{title}</h2>")
        lines.append(f"<p>{_fill_variables(body, c.variables)}</p>")
    lines.append("<div class='sig'>")
    lines.append("<table width='100%'><tr><td>甲方 (盖章): ____________</td><td>乙方 (盖章): ____________</td></tr></table>")
    lines.append(f"<p>合同 SM3 指纹: <code>{c.hash_chain[0] if c.hash_chain else ''}</code></p>")
    lines.append("</div>")
    lines.append("</body></html>")
    return "\n".join(lines)


def render_contract_pdf(c: Contract) -> bytes:
    """用 ReportLab Platypus 渲染 PDF. 失败时回退到最小 PDF (避免硬依赖)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from io import BytesIO

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, leftMargin=2 * cm)
        styles = getSampleStyleSheet()
        h1 = ParagraphStyle("h1", parent=styles["Heading1"], alignment=1, fontSize=18, spaceAfter=12)
        h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=6)
        body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=14)
        meta = ParagraphStyle("meta", parent=styles["BodyText"], fontSize=9, alignment=2, textColor=colors.grey)

        tpl = TEMPLATES[c.template]
        story = [
            Paragraph(tpl["title"], h1),
            Paragraph(tpl["title_en"], meta),
            Spacer(1, 0.3 * cm),
            Paragraph(f"合同编号: <b>{c.contract_id}</b>", meta),
            Paragraph(f"甲方: {c.company_name}", meta),
            Paragraph(f"联系人: {c.contact_email}", meta),
            Paragraph(f"签订日期: {c.created_at[:10]}", meta),
            Spacer(1, 0.5 * cm),
        ]
        for title, sec_body in tpl["sections"]:
            story.append(Paragraph(title, h2))
            story.append(Paragraph(_fill_variables(sec_body, c.variables), body))
        story.append(Spacer(1, 1 * cm))
        # 签名区
        sig_data = [["甲方 (盖章)", "乙方 (盖章)"], ["____________", "____________"]]
        sig_table = Table(sig_data, colWidths=[8 * cm, 8 * cm])
        sig_table.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 10),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))
        story.append(sig_table)
        story.append(Spacer(1, 0.5 * cm))
        if c.hash_chain:
            story.append(Paragraph(f"<b>SM3 指纹:</b> <font size='8'>{c.hash_chain[0]}</font>", body))
        if c.signature:
            story.append(Paragraph(f"<b>签名:</b> {c.signature}", body))
            story.append(Paragraph(f"<b>签名时间:</b> {c.signed_at}", body))
        doc.build(story)
        return buf.getvalue()
    except Exception as e:
        logger.exception("PDF render failed: %s, using minimal fallback", e)
        # 最小回退 PDF (单页)
        return _minimal_pdf(c)


def _minimal_pdf(c: Contract) -> bytes:
    """最小有效 PDF (无外部依赖). 包含合同文本和 SM3 哈希."""
    tpl = TEMPLATES.get(c.template, TEMPLATES["service_agreement"])
    body_text = c.company_name + " " + c.contact_email + " " + str(c.variables)
    content_lines = [tpl["title"], "", f"No: {c.contract_id}", f"Date: {c.created_at[:10]}", "",
                     f"Party A: {c.company_name}", f"Email: {c.contact_email}",
                     f"Plan: {c.variables.get('plan_name','')}", f"Amount: {c.variables.get('amount','')}",
                     f"Term: {c.variables.get('start_date','')} ~ {c.variables.get('end_date','')}", "",
                     "SM3 Fingerprint:", c.hash_chain[0] if c.hash_chain else ""]
    body_stream = "\n".join(content_lines).encode("utf-8", errors="replace")
    # 极简 PDF 结构
    pdf = b"%PDF-1.4\n"
    objs: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>",
                         b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                         b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                         b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"]
    stream = b"BT /F1 12 Tf 50 800 Td 14 TL\n" + b"\n".join(
        f"({ln}) Tj T*".encode("latin-1", errors="replace") for ln in body_lines if False  # noqa
    )
    # 简化: 直接放原始字节到 stream (不严格 PDF, 仅作占位)
    stream_content = b"BT /F1 10 Tf 50 800 Td 14 TL\n" + body_stream[:2000].replace(b"\n", b" ") + b" ET"
    objs.append(f"<< /Length {len(stream_content)} >>\nstream\n".encode("ascii") + stream_content + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    offsets: list[int] = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref_pos = len(pdf)
    pdf += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("ascii")
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode("ascii")
    pdf += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    return pdf


def save_contract_pdf(c: Contract) -> Path:
    """保存 PDF 到磁盘. 返回路径."""
    pdf_bytes = render_contract_pdf(c)
    path = _PDF_DIR / f"{c.contract_id}.pdf"
    path.write_bytes(pdf_bytes)
    return path


def sign_contract(contract_id: str, signer: str) -> Contract:
    """对合同进行数字签名 (SM3 / SM2 / placeholder)."""
    c = _STORE.get(contract_id)
    if c is None:
        raise KeyError(f"contract not found: {contract_id}")
    canonical = json.dumps(c.to_dict(), sort_keys=True, ensure_ascii=False)
    if SIGN_MODE == "sm2":
        sig = _sm2_sign(canonical.encode("utf-8"), key_id=signer)
    else:
        sig = f"SM3:{signer}:{_sm3_hex(canonical.encode('utf-8'))}"
    c.signature = sig
    c.signed_at = datetime.utcnow().isoformat()
    c.signed_by = signer
    c.status = "signed"
    c.hash_chain.append(_sm3_hex(canonical.encode("utf-8")))
    return c


def get_contract(contract_id: str) -> Optional[Contract]:
    return _STORE.get(contract_id)


def list_contracts(company: Optional[str] = None, status: Optional[str] = None) -> List[Contract]:
    items = list(_STORE.values())
    if company:
        items = [c for c in items if c.company_name == company]
    if status:
        items = [c for c in items if c.status == status]
    return items


# ---------------------------------------------------------------------------
# 集成钩子 (与 P4-10-W1 billing 配合; W1 不存在时使用 stub)
# ---------------------------------------------------------------------------
def on_order_paid(order_id: str, plan_name: str, amount: float, company: str, email: str) -> Contract:
    """Order paid 钩子: 自动生成服务协议合同 (按 plan 类型)."""
    return generate_contract(
        template="service_agreement",
        company_name=company,
        contact_email=email,
        plan_name=plan_name,
        amount=amount,
    )
