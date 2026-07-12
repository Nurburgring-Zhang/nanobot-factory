"""V5 第40章 — PII 5 类脱敏 (id_card / phone / email / bank_card / name_address).

公开 API:
    PIIRedactor          — 主类
    PIIRedactor.redact() → RedactionResult

启发式 (无外部 NER 依赖):
    detect_id_card   — 18 位身份证 (末位校验码可选)
    detect_phone     — 11 位中国手机号 (1[3-9]\\d{9})
    detect_email     — 标准 email 正则
    detect_bank_card — 16-19 位银行卡 (Luhn 校验可选)
    detect_name_address — 中文姓名 + 地址关键字组合启发式
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Match, Optional, Tuple

from .schemas import DetectedPII, PIIType, RedactionResult


# ── 工具: Luhn 校验 ───────────────────────────────────────────────────
def _luhn_check(digits: str) -> bool:
    """标准 Luhn 校验.  digits 只含数字."""
    if not digits.isdigit() or len(digits) < 2:
        return False
    total = 0
    parity = (len(digits) - 2) % 2  # 倒数第二位开始翻倍
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ── 工具: 中文姓名词典 (mock NER) ─────────────────────────────────────
_COMMON_SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史"
    "唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟"
    "平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈"
    "项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏"
    "蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪"
    "包诸左石崔吉钮龚程嵇邢滑裴陆荣翁"
)
# 常见中文名 length 2-4
# 不使用 negative lookbehind 避免 "客户张三" 这类紧邻中文场景漏检;
# 配合 name+address 邻近约束, false positive 可控.
_CN_NAME = re.compile(
    r"[" + _COMMON_SURNAMES + r"][一-龥]{1,3}"
)
# 简易中文地址关键字 (省/市/区/县/路/街/号/室/楼/村/镇/乡)
_ADDRESS_KW = re.compile(
    r"([一-龥]{2,8}(省|市|自治区|特别行政区))"
    r"|([一-龥]{2,8}(市|区|县|州|盟))"
    r"|([一-龥]{2,30}(路|街|大道|巷|弄)[\d一二三四五六七八九十百千号]*)"
    r"|([\d一二三四五六七八九十百千]+号[\d一二三四五六七八九十百千]*室?)"
    r"|([一-龥]{2,8}(镇|乡|村|屯))"
)


def _mask_id_card(s: str) -> str:
    """身份证: 保留前 6 + 后 4, 中间 8 位 *."""
    if len(s) <= 10:
        return "*" * len(s)
    return s[:6] + "*" * (len(s) - 10) + s[-4:]


def _mask_phone(s: str) -> str:
    """手机: 138****8000."""
    if len(s) < 7:
        return "*" * len(s)
    return s[:3] + "****" + s[-4:]


def _mask_email(s: str) -> str:
    """邮箱: a***@b.com (本地部分保留首字母)."""
    if "@" not in s:
        return "*" * len(s)
    local, _, domain = s.partition("@")
    if not local:
        return "*" * len(s)
    masked_local = local[0] + "***" if len(local) > 1 else "*"
    return f"{masked_local}@{domain}"


def _mask_bank_card(s: str) -> str:
    """银行卡: 保留前 4 + 后 4."""
    digits = re.sub(r"\s+", "", s)
    if len(digits) <= 8:
        return "*" * len(s)
    return digits[:4] + "*" * (len(digits) - 8) + digits[-4:]


def _mask_name(s: str) -> str:
    """姓名: 张* (姓 + *)."""
    if len(s) <= 1:
        return "*" * len(s)
    return s[0] + "*" * (len(s) - 1)


def _mask_address(s: str) -> str:
    """地址: 仅保留省级前缀 + [REDACTED]."""
    m = re.match(r"^([一-龥]{2,8}(省|市|自治区|特别行政区))", s)
    if m:
        return m.group(1) + "[REDACTED]"
    return "[REDACTED]"


# ════════════════════════════════════════════════════════════════════════
#  PIIRedactor
# ════════════════════════════════════════════════════════════════════════
@dataclass
class PIIRedactor:
    """5 类 PII 脱敏器.

    默认 confidence: id_card=0.95, phone=0.95, email=0.99, bank_card=0.90,
    name_address=0.70 (启发式 NER).
    """

    enable_luhn_for_bank: bool = True
    require_id_checksum: bool = False  # 默认不强制 (避免误杀)
    _id_re = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
    _phone_re = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    _email_re = re.compile(
        r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?![A-Za-z0-9._%+\-])"
    )
    _bank_re = re.compile(r"(?<!\d)(?:\d[\s-]?){13,18}\d(?!\d)")

    # ── 单 detector ──────────────────────────────────────────────────
    def detect_id_card(self, text: str) -> List[DetectedPII]:
        out: List[DetectedPII] = []
        for m in self._id_re.finditer(text):
            s = m.group(0)
            if self.require_id_checksum and not self._id_checksum_ok(s):
                continue
            out.append(DetectedPII(
                pii_type=PIIType.ID_CARD,
                original=s, redacted=_mask_id_card(s),
                start=m.start(), end=m.end(), confidence=0.95,
            ))
        return out

    def detect_phone(self, text: str) -> List[DetectedPII]:
        out: List[DetectedPII] = []
        for m in self._phone_re.finditer(text):
            out.append(DetectedPII(
                pii_type=PIIType.PHONE,
                original=m.group(0),
                redacted=_mask_phone(m.group(0)),
                start=m.start(), end=m.end(), confidence=0.95,
            ))
        return out

    def detect_email(self, text: str) -> List[DetectedPII]:
        out: List[DetectedPII] = []
        for m in self._email_re.finditer(text):
            out.append(DetectedPII(
                pii_type=PIIType.EMAIL,
                original=m.group(0),
                redacted=_mask_email(m.group(0)),
                start=m.start(), end=m.end(), confidence=0.99,
            ))
        return out

    def detect_bank_card(self, text: str) -> List[DetectedPII]:
        out: List[DetectedPII] = []
        for m in self._bank_re.finditer(text):
            digits = re.sub(r"\s+|-", "", m.group(0))
            if not (13 <= len(digits) <= 19):
                continue
            if self.enable_luhn_for_bank and not _luhn_check(digits):
                continue
            out.append(DetectedPII(
                pii_type=PIIType.BANK_CARD,
                original=m.group(0),
                redacted=_mask_bank_card(m.group(0)),
                start=m.start(), end=m.end(), confidence=0.90,
            ))
        return out

    def detect_name_address(self, text: str) -> List[DetectedPII]:
        """姓名 + 地址组合启发式 — 仅当两者邻近 (≤12 字符) 才判定."""
        out: List[DetectedPII] = []
        names = list(_CN_NAME.finditer(text))
        addrs = list(_ADDRESS_KW.finditer(text))
        if not names or not addrs:
            return out
        for nm in names:
            for ad in addrs:
                if abs(nm.start() - ad.start()) <= 12:
                    # 合并为同一段
                    start, end = min(nm.start(), ad.start()), max(nm.end(), ad.end())
                    segment = text[start:end]
                    redacted = _mask_name(nm.group(0)) + " " + _mask_address(ad.group(0))
                    out.append(DetectedPII(
                        pii_type=PIIType.NAME_ADDRESS,
                        original=segment,
                        redacted=redacted,
                        start=start, end=end, confidence=0.70,
                    ))
                    break  # 一个 name 只配一个 address
        return out

    # ── 聚合 redact ──────────────────────────────────────────────────
    def redact(self, text: str) -> RedactionResult:
        """对原文做全 5 类检测 + 替换, 返回 RedactionResult."""
        if not isinstance(text, str):
            return RedactionResult(
                original_text=str(text), redacted_text=str(text),
                detected_pii=[], pii_count=0,
            )

        detected: List[DetectedPII] = []
        detected.extend(self.detect_id_card(text))
        detected.extend(self.detect_phone(text))
        detected.extend(self.detect_email(text))
        detected.extend(self.detect_bank_card(text))
        detected.extend(self.detect_name_address(text))

        # 按 start 倒序替换 (避免 offset 偏移)
        detected.sort(key=lambda d: d.start, reverse=True)
        redacted = text
        for d in detected:
            redacted = redacted[: d.start] + d.redacted + redacted[d.end :]

        return RedactionResult(
            original_text=text,
            redacted_text=redacted,
            detected_pii=detected,
            pii_count=len(detected),
        )

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _id_checksum_ok(id18: str) -> bool:
        """GB 11643-1999 身份证校验码."""
        if len(id18) != 18:
            return False
        weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        check_map = "10X98765432"
        try:
            total = sum(int(c) * w for c, w in zip(id18[:17], weights))
        except ValueError:
            return False
        return check_map[total % 11] == id18[17].upper()


__all__ = ["PIIRedactor"]