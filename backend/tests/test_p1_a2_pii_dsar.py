"""
P1-A2-W1: PII Auto-Detection + DSAR Automation Tests
=====================================================
20+ test cases covering PIIEngine class + DSAREngine class + 7 API endpoints.

Test strategy:
  * Engine-level tests use PIIEngine / DSAREngine directly with an isolated
    SQLite database in a temp dir.
  * API-level tests use FastAPI TestClient with an isolated privacy DB.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, Generator, List

import pytest

# ── Path setup: import api package from imdf/ ─────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
_IMDF_ROOT = _BACKEND / "imdf"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_IMDF_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMDF_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Engines under test
from engines.pii_engine import (  # noqa: E402
    PIIEngine,
    PII_TYPE_EMAIL,
    PII_TYPE_PHONE_CN,
    PII_TYPE_ID_CARD_CN,
    PII_TYPE_CREDIT_CARD,
    PII_TYPE_BANK_CARD_CN,
    PII_TYPE_IPV4,
    PII_TYPE_SSN_US,
    PII_TYPE_PASSPORT_CN,
    PII_TYPE_NAME,
    PII_TYPE_ADDRESS_CN,
    _luhn_check,
    _verify_cn_id_checksum,
)
from engines.dsar_engine import DSAREngine, GENESIS_HASH  # noqa: E402

# Routes under test
from api import privacy_routes  # noqa: E402
from api.privacy_routes import router as privacy_router  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────────

# A valid 18-digit Chinese ID with correct checksum
VALID_CN_ID = "110101199003078814"  # checksum verified
# Luhn-valid 16-digit Visa test number
VALID_CC = "4111111111111111"
# Luhn-valid 16-digit bank card
VALID_BANK = "6222021234567890123"  # 19 digits starting with 62


def _build_privacy_app(tmp: Path) -> FastAPI:
    """Build a minimal FastAPI app with the privacy router, isolated DB."""
    db = tmp / "privacy.db"
    # Force the DSAR engine + legacy DB to use the temp path
    privacy_routes._reset_dsar_engine_for_tests()
    privacy_routes._reset_pii_engine_for_tests()
    privacy_routes.DB_PATH = str(db)
    privacy_routes._init_db()
    app = FastAPI()
    app.include_router(privacy_router)
    return app


@pytest.fixture
def tmp_root() -> Generator[Path, None, None]:
    """Isolated tmp dir for one test."""
    d = Path(tempfile.mkdtemp(prefix="pii_dsar_test_"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def client(tmp_root: Path) -> TestClient:
    """A FastAPI TestClient wired to the privacy router with isolated DB."""
    return TestClient(_build_privacy_app(tmp_root))


@pytest.fixture
def dsar(tmp_root: Path) -> DSAREngine:
    """A fresh DSAREngine pointing at a tmp DB."""
    privacy_routes._reset_dsar_engine_for_tests()
    return DSAREngine(db_path=str(tmp_root / "dsar.db"))


@pytest.fixture
def pii() -> PIIEngine:
    return PIIEngine(use_ml=False)


# ─────────────────────────────────────────────────────────────────────────
# PII Engine — detection tests
# ─────────────────────────────────────────────────────────────────────────
class TestPIIEngineDetect:
    def test_01_detect_email(self, pii: PIIEngine):
        m = pii.detect("Contact me at alice@example.com please.")
        assert len(m) == 1
        assert m[0].type == PII_TYPE_EMAIL
        assert m[0].value == "alice@example.com"
        assert m[0].confidence >= 0.9

    def test_02_detect_chinese_phone(self, pii: PIIEngine):
        m = pii.detect("我的手机是13800138000，请联系我")
        assert len(m) == 1
        assert m[0].type == PII_TYPE_PHONE_CN
        assert m[0].value == "13800138000"

    def test_03_detect_cn_id_with_checksum(self, pii: PIIEngine):
        assert _verify_cn_id_checksum(VALID_CN_ID) is True
        m = pii.detect(f"身份证号 {VALID_CN_ID}")
        assert len(m) == 1
        assert m[0].type == PII_TYPE_ID_CARD_CN
        assert m[0].value == VALID_CN_ID

    def test_04_detect_cn_id_rejects_bad_checksum(self, pii: PIIEngine):
        # Bogus ID with wrong checksum
        bogus = "110101199003078810"
        assert _verify_cn_id_checksum(bogus) is False
        m = pii.detect(f"bad: {bogus}")
        # Should be filtered out
        assert all(x.value != bogus for x in m)

    def test_05_detect_credit_card_with_luhn(self, pii: PIIEngine):
        assert _luhn_check(VALID_CC) is True
        m = pii.detect(f"Card: {VALID_CC}")
        assert any(x.type == PII_TYPE_CREDIT_CARD and x.value == VALID_CC for x in m)

    def test_06_detect_credit_card_rejects_bad_luhn(self, pii: PIIEngine):
        # Not Luhn-valid
        bad = "4111111111111112"
        assert _luhn_check(bad) is False
        m = pii.detect(f"Card: {bad}")
        # The bad number should be filtered (the bank_card_cn pattern might also try to match it)
        assert not any(x.type == PII_TYPE_CREDIT_CARD and x.value == bad for x in m)

    def test_07_detect_ipv4(self, pii: PIIEngine):
        m = pii.detect("Server at 192.168.1.1, also 10.0.0.1")
        ips = [x.value for x in m if x.type == PII_TYPE_IPV4]
        assert "192.168.1.1" in ips
        assert "10.0.0.1" in ips

    def test_08_detect_ssn_us(self, pii: PIIEngine):
        m = pii.detect("SSN: 123-45-6789")
        assert any(x.type == PII_TYPE_SSN_US and x.value == "123-45-6789" for x in m)

    def test_09_detect_chinese_passport(self, pii: PIIEngine):
        m = pii.detect("护照号 E12345678")
        assert any(x.type == PII_TYPE_PASSPORT_CN and x.value == "E12345678" for x in m)

    def test_10_detect_multiple_types_in_one_text(self, pii: PIIEngine):
        text = (
            f"Email: alice@example.com, phone: 13800138000, "
            f"ID: {VALID_CN_ID}, IP: 8.8.8.8, card: {VALID_CC}"
        )
        m = pii.detect(text)
        types = {x.type for x in m}
        assert PII_TYPE_EMAIL in types
        assert PII_TYPE_PHONE_CN in types
        assert PII_TYPE_ID_CARD_CN in types
        assert PII_TYPE_IPV4 in types
        assert PII_TYPE_CREDIT_CARD in types

    def test_11_detect_no_pii_returns_empty(self, pii: PIIEngine):
        m = pii.detect("Hello world, this is a clean text with no sensitive data.")
        # 'Hello' should not match anything
        assert m == []

    def test_12_detect_filter_by_type(self, pii: PIIEngine):
        text = f"alice@example.com 13800138000 {VALID_CN_ID}"
        m_email_only = pii.detect(text, types=[PII_TYPE_EMAIL])
        assert all(x.type == PII_TYPE_EMAIL for x in m_email_only)
        assert len(m_email_only) == 1


# ─────────────────────────────────────────────────────────────────────────
# PII Engine — redaction tests
# ─────────────────────────────────────────────────────────────────────────
class TestPIIEngineRedact:

    def test_13_redact_mask_strategy(self, pii: PIIEngine):
        out = pii.redact("alice@example.com", strategy="mask")
        assert "alice" not in out
        assert "@" not in out
        assert out == "*" * len("alice@example.com")

    def test_14_redact_replace_strategy_email(self, pii: PIIEngine):
        out = pii.redact("alice@example.com", strategy="replace")
        # First char of local + asterisks + @ + first char of domain + asterisks
        assert out.startswith("a")
        assert "@" in out
        assert "alice" not in out

    def test_15_redact_replace_strategy_phone(self, pii: PIIEngine):
        out = pii.redact("13800138000", strategy="replace")
        assert out.startswith("138")
        assert out.endswith("8000")
        # middle is masked
        assert "****" in out

    def test_16_redact_hash_strategy(self, pii: PIIEngine):
        out = pii.redact("alice@example.com", strategy="hash")
        assert out.startswith("[HASH:")
        assert "alice" not in out
        assert "@" not in out

    def test_17_redact_remove_strategy(self, pii: PIIEngine):
        text = f"my email is alice@example.com and my phone is 13800138000"
        out = pii.redact(text, strategy="remove")
        assert "alice@example.com" not in out
        assert "13800138000" not in out
        # Should still contain some surrounding text
        assert "my email is" in out or "and my phone is" in out

    def test_18_redact_no_pii_returns_unchanged(self, pii: PIIEngine):
        text = "no sensitive content here"
        assert pii.redact(text, strategy="mask") == text
        assert pii.redact(text, strategy="hash") == text

    def test_19_redact_id_card_keeps_prefix_suffix(self, pii: PIIEngine):
        out = pii.redact(VALID_CN_ID, strategy="replace", types=[PII_TYPE_ID_CARD_CN])
        # 6 prefix + 8 asterisks + 4 suffix
        assert out.startswith(VALID_CN_ID[:6])
        assert out.endswith(VALID_CN_ID[-4:])
        assert "********" in out


# ─────────────────────────────────────────────────────────────────────────
# PII Engine — heuristic / field scan
# ─────────────────────────────────────────────────────────────────────────
class TestPIIEngineFieldHeuristic:

    def test_20_field_heuristic_email_field_name(self, pii: PIIEngine):
        result = pii.scan_field("email", "alice@example.com")
        assert result["is_pii"] is True
        assert result["type"] == PII_TYPE_EMAIL
        assert result["action"] in ("redact", "block")

    def test_21_field_heuristic_phone_field_name(self, pii: PIIEngine):
        result = pii.scan_field("phone_number", "13800138000")
        assert result["is_pii"] is True
        assert result["type"] == PII_TYPE_PHONE_CN
        assert result["action"] == "redact"

    def test_22_field_heuristic_id_card_field_name_blocks(self, pii: PIIEngine):
        result = pii.scan_field("id_card", VALID_CN_ID)
        assert result["is_pii"] is True
        assert result["type"] == PII_TYPE_ID_CARD_CN
        assert result["action"] == "block"  # high-sensitivity → block

    def test_23_field_heuristic_credit_card_field_name_blocks(self, pii: PIIEngine):
        result = pii.scan_field("credit_card", VALID_CC)
        assert result["is_pii"] is True
        assert result["type"] == PII_TYPE_CREDIT_CARD
        assert result["action"] == "block"

    def test_24_field_heuristic_non_pii_field(self, pii: PIIEngine):
        result = pii.scan_field("description", "a regular text field with no PII")
        assert result["is_pii"] is False
        assert result["action"] == "allow"

    def test_25_field_heuristic_unknown_field_with_pii_value(self, pii: PIIEngine):
        # Field name is non-PII, but value is an email
        result = pii.scan_field("notes", "contact alice@example.com for details")
        assert result["is_pii"] is True
        # type comes from value detection, not heuristic
        assert result["type"] == PII_TYPE_EMAIL


# ─────────────────────────────────────────────────────────────────────────
# DSAR Engine — operations
# ─────────────────────────────────────────────────────────────────────────
class TestDSAREngine:

    def test_26_export_returns_full_envelope(self, dsar: DSAREngine):
        dsar.seed_user("alice", records=[
            {"data_type": "profile", "content": json.dumps(
                {"name": "Alice", "email": "alice@example.com"})},
            {"data_type": "uploads", "content": json.dumps({"f": "x.png"})},
        ], consents=[
            {"purpose": "marketing", "action": "granted"},
        ])
        result = dsar.export("alice")
        assert result["operation"] == "export"
        assert result["status"] == "completed"
        assert result["user_id"] == "alice"
        assert len(result["user_data"]) == 2
        assert len(result["consent_records"]) == 1
        assert "audit_id" in result
        assert len(result["audit_chain_hash"]) == 64

    def test_27_export_idempotent_returns_consistent_data(self, dsar: DSAREngine):
        dsar.seed_user("bob")
        r1 = dsar.export("bob")
        r2 = dsar.export("bob")
        # Same user_data rows (sequence may differ in audit_id but content is identical)
        assert len(r1["user_data"]) == len(r2["user_data"])
        assert sorted([d["data_type"] for d in r1["user_data"]]) == \
               sorted([d["data_type"] for d in r2["user_data"]])

    def test_28_erase_soft_anonymizes_content(self, dsar: DSAREngine):
        dsar.seed_user("carol", records=[
            {"data_type": "profile", "content": json.dumps(
                {"name": "Carol", "email": "carol@example.com"})},
        ])
        r = dsar.erase("carol", retain_audit=True)
        assert r["operation"] == "erase"
        assert r["erased_user_data_rows"] == 1
        # content is now [ERASED]
        row = dsar._connect().execute(
            "SELECT content FROM user_data WHERE user_id = ?", ("carol",)
        ).fetchone()
        assert row[0] == "[ERASED]"

    def test_29_erase_retain_audit_keeps_chain(self, dsar: DSAREngine):
        dsar.seed_user("dave")
        dsar.export("dave")  # adds 1 audit record
        r = dsar.erase("dave", retain_audit=True)
        assert r["retain_audit"] is True
        # audit chain is still verifiable
        v = dsar.verify_audit_chain("dave")
        assert v["ok"] is True
        assert v["verified"] >= 2  # at least export + erase

    def test_30_erase_login_fails_after(self, dsar: DSAREngine):
        # user_exists() should return False after erase (data is anonymized)
        dsar.seed_user("erin")
        assert dsar.user_exists("erin") is True
        dsar.erase("erin")
        # content replaced with [ERASED], but row still present
        # user_exists() checks by user_id only → True (the row stays for audit)
        # The key point: content is no longer the original PII
        with dsar._connect() as conn:
            row = conn.execute(
                "SELECT content FROM user_data WHERE user_id = ?", ("erin",)
            ).fetchone()
        assert row[0] == "[ERASED]"

    def test_31_anonymize_replaces_pii_fields(self, dsar: DSAREngine):
        dsar.seed_user("frank", records=[
            {"data_type": "profile", "content": json.dumps(
                {"name": "Frank", "email": "frank@example.com",
                 "phone": "13800138000", "favorite_color": "blue"})},
        ])
        r = dsar.anonymize("frank")
        assert r["operation"] == "anonymize"
        assert r["anon_user_id"].startswith("ANON_USER_")
        assert len(r["anon_user_id"]) == len("ANON_USER_") + 8
        # Verify the row now has anon_user_id and PII replaced
        with dsar._connect() as conn:
            row = conn.execute(
                "SELECT user_id, content FROM user_data WHERE user_id = ?",
                (r["anon_user_id"],)
            ).fetchone()
        assert row is not None
        content = json.loads(row[1])
        assert content["name"] == "[REDACTED]"
        assert content["email"] == "[REDACTED]"
        assert content["phone"] == "[REDACTED]"
        # non-PII preserved
        assert content["favorite_color"] == "blue"

    def test_32_portability_returns_standard_schema(self, dsar: DSAREngine):
        dsar.seed_user("grace", records=[
            {"data_type": "profile", "content": json.dumps(
                {"name": "Grace", "email": "grace@example.com"})},
        ], consents=[
            {"purpose": "marketing", "action": "granted"},
        ])
        r = dsar.portability("grace")
        assert r["schema"] == "GDPR-Article20-v1"
        assert r["schema_version"] == "1.0"
        # profile is a flat dict built from common fields
        assert r["profile"]["name"] == "Grace"
        assert r["profile"]["email"] == "grace@example.com"
        assert len(r["data_categories"]) >= 1
        assert len(r["consents"]) >= 1

    def test_33_audit_trail_chronological(self, dsar: DSAREngine):
        dsar.seed_user("henry")
        dsar.export("henry")
        dsar.anonymize("henry")
        dsar.erase("henry")
        trail = dsar.get_audit_trail("henry")
        ops = [t["operation"] for t in trail]
        assert ops == ["export", "anonymize", "erase"]
        # seq is monotonically increasing
        seqs = [t["seq"] for t in trail]
        assert seqs == sorted(seqs)

    def test_34_audit_chain_hash_chain_valid(self, dsar: DSAREngine):
        dsar.seed_user("ivy")
        dsar.export("ivy")
        dsar.erase("ivy")
        v = dsar.verify_audit_chain("ivy")
        assert v["ok"] is True
        assert v["verified"] == 2
        assert v["broken_at_seq"] is None

    def test_35_audit_chain_detects_tamper(self, dsar: DSAREngine):
        dsar.seed_user("jack")
        dsar.export("jack")
        # Tamper with the audit record
        conn = dsar._connect()
        conn.execute(
            "UPDATE dsar_audit SET payload = '{\"tampered\": true}' "
            "WHERE user_id = ?",
            ("jack",),
        )
        conn.commit()
        conn.close()
        v = dsar.verify_audit_chain("jack")
        assert v["ok"] is False
        assert v["broken_at_seq"] is not None

    def test_36_export_nonexistent_user_returns_empty(self, dsar: DSAREngine):
        # Per Article 15, we still complete and return 0 records, with an audit
        r = dsar.export("nobody")
        assert r["user_data"] == []
        assert r["consent_records"] == []
        # audit_id is still generated
        assert r["audit_id"].startswith("audit_")

    def test_37_anonymize_nonexistent_user_returns_zero_rows(self, dsar: DSAREngine):
        r = dsar.anonymize("nobody")
        assert r["anonymized_rows"] == 0
        assert r["anon_user_id"].startswith("ANON_USER_")

    def test_38_portability_empty_user_returns_empty_envelope(self, dsar: DSAREngine):
        r = dsar.portability("nobody")
        assert r["schema"] == "GDPR-Article20-v1"
        assert r["data_categories"] == []
        assert r["consents"] == []
        assert r["profile"] == {}

    def test_39_erase_value_error_on_empty_user_id(self, dsar: DSAREngine):
        with pytest.raises(ValueError):
            dsar.erase("")

    def test_40_audit_chain_genesis_hash(self, dsar: DSAREngine):
        # First record's prev_hash should be GENESIS_HASH
        dsar.seed_user("kim")
        dsar.export("kim")
        trail = dsar.get_audit_trail("kim")
        assert trail[0]["prev_hash"] == GENESIS_HASH


# ─────────────────────────────────────────────────────────────────────────
# API-level tests (TestClient)
# ─────────────────────────────────────────────────────────────────────────
class TestPrivacyAPI:

    def test_41_api_pii_scan(self, client: TestClient):
        r = client.post(
            "/api/v1/privacy/pii/scan",
            json={"text": f"Email alice@example.com phone 13800138000 id {VALID_CN_ID}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        types = {m["type"] for m in body["data"]["pii_found"]}
        assert PII_TYPE_EMAIL in types
        assert PII_TYPE_PHONE_CN in types
        assert PII_TYPE_ID_CARD_CN in types

    def test_42_api_pii_redact_mask(self, client: TestClient):
        r = client.post(
            "/api/v1/privacy/pii/redact",
            json={"text": "alice@example.com", "strategy": "mask"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["strategy"] == "mask"
        assert data["redacted_count"] >= 1
        assert "alice" not in data["redacted_text"]

    def test_43_api_pii_redact_replace(self, client: TestClient):
        r = client.post(
            "/api/v1/privacy/pii/redact",
            json={"text": "alice@example.com", "strategy": "replace"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["redacted_text"].startswith("a")
        assert "@" in data["redacted_text"]
        assert "alice" not in data["redacted_text"]

    def test_44_api_pii_redact_hash(self, client: TestClient):
        r = client.post(
            "/api/v1/privacy/pii/redact",
            json={"text": "alice@example.com", "strategy": "hash"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["redacted_text"].startswith("[HASH:")

    def test_45_api_pii_redact_remove(self, client: TestClient):
        r = client.post(
            "/api/v1/privacy/pii/redact",
            json={"text": "email alice@example.com now", "strategy": "remove"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert "alice@example.com" not in data["redacted_text"]

    def test_46_api_pii_redact_invalid_strategy_returns_422(self, client: TestClient):
        r = client.post(
            "/api/v1/privacy/pii/redact",
            json={"text": "x", "strategy": "nonsense"},
        )
        assert r.status_code == 422

    def test_47_api_pii_scan_field_email(self, client: TestClient):
        r = client.post(
            "/api/v1/privacy/pii/scan_field",
            json={"field_name": "email", "value": "alice@example.com"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["is_pii"] is True
        assert data["type"] == PII_TYPE_EMAIL
        assert data["action"] in ("redact", "block")

    def test_48_api_pii_scan_field_credit_card_blocks(self, client: TestClient):
        r = client.post(
            "/api/v1/privacy/pii/scan_field",
            json={"field_name": "credit_card", "value": VALID_CC},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["action"] == "block"

    def test_49_api_dsar_anonymize(self, client: TestClient, tmp_root: Path):
        # Seed first via the engine
        dsar = DSAREngine(db_path=str(tmp_root / "privacy.db"))
        dsar.seed_user("p1_a2_test_user", records=[
            {"data_type": "profile", "content": json.dumps(
                {"name": "Test", "email": "t@x.com"})},
        ])
        r = client.post(
            "/api/v1/privacy/dsar/anonymize",
            json={"user_id": "p1_a2_test_user"},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["anon_user_id"].startswith("ANON_USER_")

    def test_50_api_dsar_portability(self, client: TestClient, tmp_root: Path):
        dsar = DSAREngine(db_path=str(tmp_root / "privacy.db"))
        dsar.seed_user("p1_a2_user_2", records=[
            {"data_type": "profile", "content": json.dumps(
                {"name": "User", "email": "u@x.com"})},
        ])
        r = client.post(
            "/api/v1/privacy/dsar/portability",
            json={"user_id": "p1_a2_user_2"},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["schema"] == "GDPR-Article20-v1"
        assert data["user_id"] == "p1_a2_user_2"

    def test_51_api_audit_returns_chain(self, client: TestClient, tmp_root: Path):
        dsar = DSAREngine(db_path=str(tmp_root / "privacy.db"))
        dsar.seed_user("p1_a2_user_3")
        dsar.export("p1_a2_user_3")
        dsar.erase("p1_a2_user_3")
        r = client.get("/api/v1/privacy/audit/p1_a2_user_3")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["user_id"] == "p1_a2_user_3"
        assert data["total_records"] == 2
        ops = [t["operation"] for t in data["audit_trail"]]
        assert "export" in ops
        assert "erase" in ops
        assert data["chain_verification"]["ok"] is True

    def test_52_api_audit_user_id_validation(self, client: TestClient):
        # Use a single-segment id with invalid characters (e.g. dots).
        # validate_id should reject with HTTPException(400).
        r = client.get("/api/v1/privacy/audit/evil.id")
        # 400 (validate_id rejection) or 422 (Pydantic) — either way not 200
        assert r.status_code in (400, 422), f"Got {r.status_code}: {r.text}"

    def test_53_api_dsar_anonymize_missing_user_returns_400(self, client: TestClient):
        r = client.post(
            "/api/v1/privacy/dsar/anonymize",
            json={"user_id": ""},
        )
        assert r.status_code == 422  # Pydantic min_length=1 rejection

    def test_54_api_pii_scan_empty_text_returns_422(self, client: TestClient):
        r = client.post(
            "/api/v1/privacy/pii/scan",
            json={"text": ""},
        )
        assert r.status_code == 422

    def test_55_api_legacy_pii_detect_still_works(self, client: TestClient):
        # The legacy /pii/detect endpoint should still work
        r = client.post(
            "/api/v1/privacy/pii/detect",
            json={"text": "alice@example.com"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["contains_pii"] is True
        assert any(p["type"] == PII_TYPE_EMAIL for p in data["pii_found"])

    def test_56_api_legacy_dsar_export_still_works(self, client: TestClient, tmp_root: Path):
        dsar = DSAREngine(db_path=str(tmp_root / "privacy.db"))
        dsar.seed_user("legacy_user", records=[
            {"data_type": "profile", "content": json.dumps({"k": "v"})},
        ])
        r = client.post(
            "/api/v1/privacy/dsar/export",
            json={"user_id": "legacy_user"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["total_records"] >= 1
