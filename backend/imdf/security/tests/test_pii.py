"""V5 第40章 — PII 5 类脱敏器测试 (≥10 测试)."""
from __future__ import annotations

import pytest

from imdf.security.pii_redaction import PIIRedactor, _luhn_check
from imdf.security.schemas import PIIType


# ── Luhn utility ─────────────────────────────────────────────────────
class TestLuhnHelper:
    def test_valid_luhn(self):
        # 经典测试卡号: 4111111111111111 (Visa test)
        assert _luhn_check("4111111111111111")
        # 16 位随机合法
        assert _luhn_check("5500000000000004")

    def test_invalid_luhn(self):
        assert not _luhn_check("1234567890123456")


# ── Single detectors ──────────────────────────────────────────────────
class TestSingleDetectors:
    def setup_method(self):
        self.r = PIIRedactor()

    def test_detect_id_card_positive(self):
        text = "用户身份证是110101199003078811,请查证"
        hits = self.r.detect_id_card(text)
        assert len(hits) == 1
        assert hits[0].pii_type == PIIType.ID_CARD
        assert hits[0].original == "110101199003078811"
        assert "****" in hits[0].redacted

    def test_detect_id_card_negative(self):
        text = "订单号: 1234567890123456789"
        hits = self.r.detect_id_card(text)
        assert hits == []

    def test_detect_phone_positive(self):
        hits = self.r.detect_phone("联系:13800138000 备用:15912345678")
        assert len(hits) == 2
        assert all(h.pii_type == PIIType.PHONE for h in hits)

    def test_detect_phone_negative(self):
        # 12 位以上但非 1[3-9] 开头 → 不命中
        hits = self.r.detect_phone("号码: 12345678901")
        assert hits == []

    def test_detect_email_positive(self):
        text = "邮箱 alice@example.com 或 bob+filter@sub.example.cn"
        hits = self.r.detect_email(text)
        assert len(hits) == 2
        assert hits[0].redacted.startswith("a***@")
        assert hits[1].redacted.startswith("b***@")

    def test_detect_email_negative(self):
        hits = self.r.detect_email("无邮箱内容")
        assert hits == []

    def test_detect_bank_card_positive(self):
        # Visa test 卡号
        text = "银行卡: 4111 1111 1111 1111"
        hits = self.r.detect_bank_card(text)
        assert len(hits) == 1
        assert hits[0].pii_type == PIIType.BANK_CARD
        assert hits[0].redacted.startswith("4111")
        assert hits[0].redacted.endswith("1111")

    def test_detect_bank_card_negative_luhn(self):
        # 长度够但 Luhn 失败
        hits = self.r.detect_bank_card("无效卡号: 1234567890123456")
        assert hits == []

    def test_detect_name_address_positive(self):
        text = "收件人: 张三 收货地址: 北京市朝阳区建国路88号"
        hits = self.r.detect_name_address(text)
        assert len(hits) >= 1
        assert hits[0].pii_type == PIIType.NAME_ADDRESS

    def test_detect_name_address_no_address(self):
        # 只有姓名无地址 → 不命中
        text = "用户: 张三 已注册"
        hits = self.r.detect_name_address(text)
        assert hits == []


# ── redact() 聚合 ────────────────────────────────────────────────────
class TestRedactAggregate:
    def setup_method(self):
        self.r = PIIRedactor()

    def test_redact_returns_redaction_result(self):
        text = "客户张三 北京市朝阳区建国路88号 身份证: 110101199003078811 电话: 13800138000"
        rr = self.r.redact(text)
        assert rr.original_text == text
        assert rr.redacted_text != text
        types = {d.pii_type for d in rr.detected_pii}
        assert PIIType.ID_CARD in types
        assert PIIType.PHONE in types
        assert PIIType.NAME_ADDRESS in types
        assert rr.pii_count == len(rr.detected_pii)

    def test_redact_detects_all_5_categories_in_one_text(self):
        text = (
            "客户张三北京市海淀区中关村大街1号, "
            "邮箱: alice@example.com, "
            "身份证: 110101199003078811, "
            "电话: 13800138000, "
            "卡号: 4111-1111-1111-1111"
        )
        rr = self.r.redact(text)
        types = {d.pii_type for d in rr.detected_pii}
        assert PIIType.ID_CARD in types
        assert PIIType.PHONE in types
        assert PIIType.EMAIL in types
        assert PIIType.BANK_CARD in types
        assert PIIType.NAME_ADDRESS in types
        # 全部原文不应出现在脱敏结果中 (除姓名首字母外)
        assert "alice@example.com" not in rr.redacted_text
        assert "110101199003078811" not in rr.redacted_text
        assert "13800138000" not in rr.redacted_text
        assert "4111-1111-1111-1111" not in rr.redacted_text

    def test_redact_no_pii_passthrough(self):
        text = "今天天气不错, 数据集 ID = DS-001 正常"
        rr = self.r.redact(text)
        assert rr.detected_pii == []
        assert rr.redacted_text == text
        assert rr.pii_count == 0

    def test_redact_handles_multiple_id_cards(self):
        text = "员工A: 110101199003078811 员工B: 110102199103078823"
        rr = self.r.redact(text)
        id_hits = [d for d in rr.detected_pii if d.pii_type == PIIType.ID_CARD]
        assert len(id_hits) == 2

    def test_redact_empty_string(self):
        rr = self.r.redact("")
        assert rr.redacted_text == ""
        assert rr.pii_count == 0

    def test_redact_non_string_input(self):
        rr = self.r.redact(12345)
        assert rr.pii_count == 0
        assert rr.redacted_text == "12345"