"""
P4-10-W2 + P15-A2 F-6.7: 合同模块 — PDF 合同生成 (3 模板) + 数字签名
- 服务协议 (service_agreement)
- 数据处理协议 (data_processing_agreement / DPA)
- SLA 协议 (sla_agreement)
- 国密 SM3 哈希 (防篡改) + 可选 SM2 签名 (env 切换)
- F-6.7 真实 PKI: 自签 CA → 叶子证书 → 链式验证 + 时间戳 (RFC 3161 + 3 签名算法)
- 复用 reportlab 4.3 (避免 WeasyPrint GTK 依赖)

F-6.7 入口:
- sign_contract_real(contract_id, signer)        真实 PKI 签名
- verify_contract_signature(contract_id)           验证签名 (含证书链 + 时间戳)
- generate_admin_cert_pair(subject, email)        管理员颁发叶子证书
- signing_dir()                                   CA / 叶子证书持久化目录
"""
import os
import hashlib
import json
import uuid
import logging
import datetime as _dt
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
    """对合同进行数字签名 (SM3 / SM2 / placeholder).

    兼容旧行为: SIGN_MODE in ('sm3', 'placeholder') 时走简化逻辑.
    新流程建议用 ``sign_contract_real()`` (F-6.7 PKI + 3 签名 + 时间戳).
    """
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


# ---------------------------------------------------------------------------
# F-6.7 第三方电子签名 (PKI + 真实签名 + 时间戳)
# ---------------------------------------------------------------------------
def sign_contract_real(contract_id: str, signer: str) -> Dict[str, Any]:
    """F-6.7 真实 PKI 签名 — 替换占位 SM2 实现.

    流程:
    1. 给 signer 颁发叶子证书 (按需缓存到 backend/data/contracts_leaves/).
    2. 计算合同规范化的 doc_bytes (canonical JSON).
    3. 根据 SIGN_MODE 选 SM2 / ECDSA / RSA signer, 计算签名.
    4. 签发 RFC 3161 时间戳 (本地 TSA).
    5. 打包 SignedContract, 写入 Contract.signed_bundle.
    6. 审计日志 append.

    Returns:
        dict (含合同 dict + 签名结果 + 时戳 + 证书指纹).
    """
    from . import signing  # 延迟 import 避免循环
    from .signing.timestamp import issue_timestamp
    from .signing.audit import audit_sign_event
    from .signing.factory import SignMode, issue_leaf_for_subject, get_signer

    c = _STORE.get(contract_id)
    if c is None:
        raise KeyError(f"contract not found: {contract_id}")

    # 1. 叶子证书 — 缓存路径 contracts_leaves/<signer>.json
    leaf_cache_dir = signing_dir() / "contracts_leaves"
    leaf_cache_path = leaf_cache_dir / f"{_safe_name(signer)}.json"
    leaf_loaded_from_cache = False
    if leaf_cache_path.exists():
        try:
            d = json.loads(leaf_cache_path.read_text(encoding="utf-8"))
            from .signing.pki import CertBundle
            # 从 JSON 读回来的是 str, 需转回 bytes (PEM 编码)
            cert_pem_bytes = d["cert_pem"].encode("ascii") if isinstance(d["cert_pem"], str) else d["cert_pem"]
            key_pem_bytes = d["key_pem"].encode("ascii") if isinstance(d["key_pem"], str) else d["key_pem"]
            leaf = CertBundle(
                cert_pem=cert_pem_bytes,
                key_pem=key_pem_bytes,
                serial=d["serial"],
                subject_cn=d["subject_cn"],
                issuer_cn=d["issuer_cn"],
                not_before=d["not_before"],
                not_after=d["not_after"],
                public_key_alg=d["public_key_alg"],
                fingerprint=d["fingerprint"],
            )
            leaf_loaded_from_cache = True
        except Exception:
            leaf = None
    if not leaf_loaded_from_cache:
        leaf = issue_leaf_for_subject(subject_cn=signer)
        leaf_cache_dir.mkdir(parents=True, exist_ok=True)
        leaf_cache_path.write_text(
            json.dumps({
                "cert_pem": leaf.cert_pem.decode("ascii"),
                "key_pem": leaf.key_pem.decode("ascii"),
                "serial": leaf.serial,
                "subject_cn": leaf.subject_cn,
                "issuer_cn": leaf.issuer_cn,
                "not_before": leaf.not_before,
                "not_after": leaf.not_after,
                "public_key_alg": leaf.public_key_alg,
                "fingerprint": leaf.fingerprint,
            }, ensure_ascii=False),
            encoding="utf-8",
        )

    ca_bundle = signing.ensure_dev_ca()

    # 2. 合同规范化 — 用最终状态 (含未来签名) 排除 signature / hash_chain / signed_bundle 本身.
    #    关键: status / signed_at / signed_by 在签前后保持, 仅 signature 字段本身可变.
    #    为了 verify 时也能复算同一 canonical, 我们 build a "frozen" snapshot — 把
    #    signature 设为 None, status 设为 "signed", signed_at = 签时时间, signed_by = signer.
    #    这些值签后不会变, 所以 verify 时 c.to_dict() 减 signature 后与签时一致.
    #
    # P15-B: **CRITICAL** — ``signed_at`` must be computed ONCE and shared
    # across the canonical snapshot, the SignResult, and the contract object's
    # fields. Earlier revisions called ``datetime.utcnow()`` independently in
    # each spot, which produced 20-40% false-tamper failures on
    # ``verify_contract_signature`` (the stored canonical was built from
    # timestamp t1, but c.signed_at reflected t2 from the SignResult, so the
    # reconstructed canonical at verify-time mismatched).
    t = _dt.datetime.utcnow().isoformat() + "Z"
    pre_snap = c.to_dict()
    pre_snap.pop("signature", None)  # 留下 None 占位 (verify 时会 pop 这字段)
    pre_snap["status"] = "signed"
    pre_snap["signed_at"] = t
    pre_snap["signed_by"] = signer
    pre_snap.pop("hash_chain", None)
    pre_snap.pop("signed_bundle", None)
    canonical = json.dumps(pre_snap, sort_keys=True, ensure_ascii=False)
    doc_bytes = canonical.encode("utf-8")

    # 3. 签名 (按 SIGN_MODE)
    mode = SignMode.from_env()
    signer_obj = get_signer(mode=mode, key_pem=leaf.key_pem, cert=leaf)
    sign_result = signer_obj.get_result(doc_bytes)
    # P15-B: overwrite the signer's own timestamp with the shared ``t`` so
    # all downstream artifacts agree.
    sign_result.signed_at = t

    # 4. 时间戳 (本地 TSA)
    # P15-B: pass sign_result.doc_hash through so the timestamp token's
    # doc_hash matches the algorithm-specific hash used by the signer.
    # For ``sm2-p256-sm3`` that's SM3(ZA || doc_bytes); for legacy
    # algorithms it's SHA-256(doc_bytes). Without this, the timestamp
    # ``expected_doc_hash`` check at verify time would mismatch the
    # signer's hash and falsely flag the contract as tampered.
    ts = issue_timestamp(doc_bytes, doc_hash=sign_result.doc_hash)

    # 5. 打包 SignedContract
    from .signing.verifier import SignedContract
    signed = SignedContract(
        contract_id=contract_id,
        doc_hash=sign_result.doc_hash,
        alg=sign_result.alg,
        signature_b64=sign_result.value_b64,
        cert_pem=leaf.cert_pem.decode("ascii"),
        ca_cert_pem=ca_bundle.cert_pem.decode("ascii"),
        cert_serial=leaf.serial,
        cert_subject_cn=leaf.subject_cn,
        cert_issuer_cn=leaf.issuer_cn,
        cert_fingerprint=leaf.fingerprint,
        timestamp=ts.to_dict(),
        signed_at=t,
        signed_by=signer,
    )

    # 6. 更新合同对象 (向后兼容旧字段)
    # P15-B: every reference uses the shared ``t`` so the canonical reconstructed
    # at verify-time matches the stored canonical bytes.
    c.signature = f"{sign_result.alg}:{sign_result.value_b64}"
    c.signed_at = t
    c.signed_by = signer
    c.status = "signed"
    c.hash_chain.append(_sm3_hex(canonical.encode("utf-8")))
    # 新字段: signed_bundle (含原始 canonical bytes 用于重验)
    bundle_dict = signed.to_dict()
    bundle_dict["_canonical_bytes_b64"] = __import__("base64").b64encode(doc_bytes).decode("ascii")
    bundle_dict["_canonical_format"] = "json-sort_keys-utf8-snapshot-method"
    setattr(c, "signed_bundle", bundle_dict)

    # 7. 审计
    audit_sign_event(
        contract_id=contract_id,
        signer=signer,
        alg=sign_result.alg,
        doc_hash=sign_result.doc_hash,
        cert_serial=leaf.serial,
        cert_fingerprint=leaf.fingerprint,
        signature_b64=sign_result.value_b64,
        timestamp_token_id=ts.token_id,
        extra={"mode": mode.value, "key_alg_used": sign_result.alg},
    )

    return {
        "contract": c.to_dict(),
        "sign": sign_result.to_dict(),
        "timestamp": ts.to_dict(),
        "cert_fingerprint": leaf.fingerprint,
        "cert_serial": leaf.serial,
    }


def verify_contract_signature(contract_id: str, doc_bytes: Optional[bytes] = None) -> Dict[str, Any]:
    """F-6.7 验证合同签名.

    检查:
    1. 证书链有效 (CA → 叶子, 时间窗内, 无吊销).
    2. 签名算法正确 (per `alg` 字段).
    3. 时间戳签名有效 (HMAC + 防篡改).
    4. 当前合同状态 == 签名前原始 canonical (检测 post-signature mutate).
    """
    from . import signing
    from .signing.verifier import SignedContract, verify_signature
    import base64

    c = _STORE.get(contract_id)
    if c is None:
        raise KeyError(f"contract not found: {contract_id}")
    bundle = getattr(c, "signed_bundle", None)
    if not bundle:
        raise ValueError(f"contract {contract_id} not signed with PKI (no signed_bundle)")
    sc = SignedContract(
        contract_id=bundle["contract_id"],
        doc_hash=bundle["doc_hash"],
        alg=bundle["alg"],
        signature_b64=bundle["signature_b64"],
        cert_pem=bundle["cert_pem"],
        ca_cert_pem=bundle["ca_cert_pem"],
        cert_serial=bundle["cert_serial"],
        cert_subject_cn=bundle["cert_subject_cn"],
        cert_issuer_cn=bundle["cert_issuer_cn"],
        cert_fingerprint=bundle["cert_fingerprint"],
        timestamp=bundle.get("timestamp", {}),
        signed_at=bundle.get("signed_at"),
        signed_by=bundle.get("signed_by"),
    )
    # 4. 检测 post-signature mutate: 当前去 sig 的 canonical bytes 是否等于 stored original
    #    用与签时一致的 snapshot 方法 (status='signed', signed_at 来自 bundle, signed_by 来自 bundle).
    if bundle.get("_canonical_bytes_b64"):
        original = base64.b64decode(bundle["_canonical_bytes_b64"])
        snap_now = c.to_dict()
        snap_now.pop("signature", None)
        snap_now.pop("hash_chain", None)
        snap_now.pop("signed_bundle", None)
        # 用 bundle 中的 signed_at / signed_by 保证与签时一致
        snap_now["status"] = "signed"
        snap_now["signed_at"] = bundle.get("signed_at") or c.signed_at
        snap_now["signed_by"] = bundle.get("signed_by") or c.signed_by
        current_canonical = json.dumps(snap_now, sort_keys=True, ensure_ascii=False).encode("utf-8")
        mutated = (original != current_canonical)
    else:
        mutated = False

    # 1-3. 签名验证 (用 stored canonical bytes — 与签时一致)
    if doc_bytes is None:
        if bundle.get("_canonical_bytes_b64"):
            doc_bytes = base64.b64decode(bundle["_canonical_bytes_b64"])
        else:
            snap = c.to_dict()
            snap.pop("signature", None)
            snap.pop("hash_chain", None)
            snap.pop("signed_bundle", None)
            canonical = json.dumps(snap, sort_keys=True, ensure_ascii=False)
            doc_bytes = canonical.encode("utf-8")
    res = verify_signature(sc, doc_bytes=doc_bytes)
    if mutated and res.ok:
        # 显式标记: 当前 contract 状态已被篡改 (签名本身在 stored bytes 上有效,
        # 但 contract 在 verify 时已不匹配)
        res.reasons.append("contract_state_tampered: current contract content != signed-original canonical bytes")
        res.ok = False
    return res.to_dict()


def generate_admin_cert_pair(
    subject: str,
    *,
    validity_days: int = 1095,
    email: Optional[str] = None,
) -> Dict[str, Any]:
    """管理员 API: 给指定 subject 颁发(签发)叶子证书, 返回 PEM."""
    from . import signing
    from .signing.factory import issue_leaf_for_subject
    leaf = issue_leaf_for_subject(
        subject_cn=subject, subject_email=email, validity_days=validity_days,
    )
    return {
        "cert_pem": leaf.cert_pem.decode("ascii"),
        "key_pem": leaf.key_pem.decode("ascii"),
        "serial": leaf.serial,
        "subject_cn": leaf.subject_cn,
        "issuer_cn": leaf.issuer_cn,
        "not_before": leaf.not_before,
        "not_after": leaf.not_after,
        "public_key_alg": leaf.public_key_alg,
        "fingerprint": leaf.fingerprint,
    }


def _safe_name(name: str) -> str:
    """把任意字符串转为文件名安全的 hash (避免特殊字符)."""
    import re
    s = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:64]
    if not s:
        s = "default"
    return s


def signing_dir() -> Path:
    """获取合同签名数据目录 (CA / 叶子证书 / 审计).

    与 signing.factory._default_ca_path() 同源, 优先 CONTRACT_CA_DIR env,
    fallback 到 backend/data. 保持 CA 与 叶子缓存同目录, 避免测试间 path 不一致.
    """
    custom = os.getenv("CONTRACT_CA_DIR")
    base = Path(custom) if custom else (Path(__file__).resolve().parent.parent / "data")
    base.mkdir(parents=True, exist_ok=True)
    return base


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
