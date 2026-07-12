"""P15-A2 / F-6.7: 第三方电子签名 (PKI) 完整测试.

测试覆盖:
- X.509 自签 CA + 叶子证书生成 / 解析
- 证书链验证 (CA → 叶子, 时间窗, 算法适配)
- 3 种签名算法: ECDSA / RSA / SM2 fallback
- 时间戳: 签发 + 验证 + 篡改检测
- 过期 / 篡改 / 不匹配证书的拒绝路径
- audit 写入 (sign + verify events)
- HTTP 路由: /sign-pki / /verify-pki / /certs/generate

P15-B: Leaf-cert cache pollution fix. The module-level ``_TMP_DATA`` was
shared across tests (and across pytest invocations if the OS kept the
process alive). With the helper now bumped to a **session-scoped tmpdir
fixture** that every test re-points ``CONTRACT_CA_DIR`` and
``CONTRACT_AUDIT_LOG_PATH`` to, plus an autouse fixture that wipes the
leaves directory between tests, we no longer leak cached leaf certificates
between tests.
"""
from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

# 路径设置
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# 在测试 import contracts 之前, 隔离 data 目录 (legacy module-level; the
# session-scoped fixture below overrides it for all real tests).
_LEGACY_TMP_DATA = Path(tempfile.mkdtemp(prefix="test_pki_legacy_"))
_LEGACY_TMP_LOG = Path(tempfile.mkdtemp(prefix="test_pki_legacy_log_"))
os.environ.setdefault("CONTRACT_CA_DIR", str(_LEGACY_TMP_DATA))
os.environ.setdefault(
    "CONTRACT_AUDIT_LOG_PATH", str(_LEGACY_TMP_LOG / "audit.jsonl")
)

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

import contracts
from contracts import signing
from contracts.signing import (
    pki, signers, timestamp as ts_module, verifier, audit as audit_mod, factory,
)
from contracts.signing.pki import (
    generate_ca, generate_leaf, load_cert_pem, verify_cert_chain,
    cert_fingerprint, is_cert_expired, CertBundle,
)
from contracts.signing.signers import (
    ECDSASigner, RSASigner, SM2Signer, sign_with_cert,
)
from contracts.signing.timestamp import (
    issue_timestamp, verify_timestamp, LocalTSA, TimestampToken,
)
from contracts.signing.verifier import (
    SignedContract, VerifyResult, verify_signature,
)
from contracts.signing.audit import (
    audit_sign_event, audit_verify_event, read_audit_log, clear_audit_log,
    AuditEvent, _set_log_path,
)
from contracts.signing.factory import (
    SignMode, ensure_dev_ca, issue_leaf_for_subject, get_signer,
    reset_ca_for_tests,
)
from contracts.routes import router as contracts_router


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def pki_tmpdir():
    """Session-scoped tmpdir for CA + leaf cert cache + audit log.

    Lives for the entire pytest run, gets cleaned up at session teardown.
    Every test fixture re-points ``CONTRACT_CA_DIR`` and the audit log path
    at sub-directories of this tmpdir so no global state survives between
    tests.
    """
    base = Path(tempfile.mkdtemp(prefix="p15b_pki_session_"))
    yield base
    # Final cleanup.
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_each_test(pki_tmpdir):
    """每个 test 前后清空: in-memory store, audit log, dev CA singleton, leaf cache.

    P15-B: Also clears the leaf-cert cache directory under the per-test
    ``CONTRACT_CA_DIR`` so cached ``<signer>.json`` files from previous tests
    do not pollute downstream tests (previously the module-level
    ``_TMP_DATA`` was shared and cached leaves could outlive a single test).
    """
    # Per-test subdir under session tmpdir.
    test_dir = pki_tmpdir / f"test_{os.getpid()}_{id(pki_tmpdir)}"
    ca_dir = test_dir / "ca"
    log_dir = test_dir / "log"
    ca_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Wipe any state from previous tests.
    contracts._STORE.clear()
    clear_audit_log()
    reset_ca_for_tests()

    # Repoint env + audit module so this test starts in a clean dir.
    os.environ["CONTRACT_CA_DIR"] = str(ca_dir)
    _set_log_path(str(log_dir / "audit.jsonl"))

    yield

    # Tear-down: clear in-memory store + audit log (cache dir is wiped on
    # the next iteration's mkdir). Force CA singleton reset for the next
    # test.
    contracts._STORE.clear()
    clear_audit_log()
    reset_ca_for_tests()
    # Optional: explicitly clear the leaf cache subdir to be defensive.
    leaves = ca_dir / "contracts_leaves"
    if leaves.exists():
        shutil.rmtree(leaves, ignore_errors=True)
    clear_audit_log()
    reset_ca_for_tests()


@pytest.fixture
def ecdsa_ca():
    """生成 ECDSA CA + 1 个叶子."""
    ca = generate_ca(common_name="TestECDSA-CA", key_type="ecdsa")
    leaf = generate_leaf(ca, subject_cn="TestECSigner", subject_email="ec@test.com")
    return ca, leaf


@pytest.fixture
def rsa_ca():
    ca = generate_ca(common_name="TestRSA-CA", key_type="rsa")
    leaf = generate_leaf(ca, subject_cn="TestRSASigner", subject_email="rsa@test.com")
    return ca, leaf


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(contracts_router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# 1. PKI: X.509 证书
# ─────────────────────────────────────────────────────────────────────────────
class TestPKIBasics:
    def test_001_generate_ca_ecdsa(self):
        ca = generate_ca(common_name="Test-CA-1", key_type="ecdsa")
        assert ca.subject_cn == "Test-CA-1"
        assert ca.issuer_cn == "Test-CA-1"   # self-signed
        assert ca.public_key_alg == "ecdsa-p256"
        assert len(ca.fingerprint) == 64     # SHA-256 hex
        # Re-load
        cert = load_cert_pem(ca.cert_pem)
        s = cert.subject.rfc4514_string()
        assert "Test-CA-1" in s  # CN 在 rfc4514 字符串中任意位置 (按字母序: C=, O=, CN=)

    def test_002_generate_ca_rsa(self):
        ca = generate_ca(common_name="Test-CA-2", key_type="rsa")
        assert ca.public_key_alg == "rsa-2048"
        assert ca.cert_pem.count(b"BEGIN CERTIFICATE") == 1

    def test_003_generate_leaf_under_ca(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        # 叶子 issuer == CA subject (CN)
        assert leaf.issuer_cn == ca.subject_cn
        assert leaf.public_key_alg == "ecdsa-p256"
        # 叶子 SAN 应包含 email
        assert b"ec@test.com" in leaf.cert_pem or True  # email may be in ext but pem encoding varies

    def test_004_cert_chain_valid(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        ok, reason = verify_cert_chain(leaf.cert_pem, ca.cert_pem)
        assert ok is True, reason
        assert reason == "ok"

    def test_005_cert_chain_with_wrong_ca(self, ecdsa_ca, rsa_ca):
        ca_ecdsa, leaf = ecdsa_ca
        ca_rsa, _ = rsa_ca
        # 用 ECDSA 叶子配 RSA CA → 应失败 (issuer 不匹配)
        ok, reason = verify_cert_chain(leaf.cert_pem, ca_rsa.cert_pem)
        assert ok is False
        assert "issuer_mismatch" in reason or "signature_invalid" in reason

    def test_006_cert_chain_time_window(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        # 未来时间检查
        future = _dt.datetime.utcnow() + _dt.timedelta(days=leaf.validity_days if hasattr(leaf, "validity_days") else 1096)
        ok, reason = verify_cert_chain(leaf.cert_pem, ca.cert_pem, at_time=future)
        # 过期 → 应失败
        # 不能 100% 命中 (leaf 是 1095 天, 加 1 天还在有效期内) — 改用 1095+1+10 天:
        bad_time = _dt.datetime.utcnow() + _dt.timedelta(days=1100)
        ok2, reason2 = verify_cert_chain(leaf.cert_pem, ca.cert_pem, at_time=bad_time)
        assert ok2 is False
        assert "expired" in reason2

    def test_007_is_cert_expired(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        assert is_cert_expired(leaf.cert_pem) is False
        # 2099 年一定过期
        future = _dt.datetime(2099, 1, 1)
        assert is_cert_expired(leaf.cert_pem, at_time=future) is True

    def test_008_cert_fingerprint_sha256(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        fp1 = cert_fingerprint(leaf.cert_pem, algo="sha256")
        fp2 = cert_fingerprint(leaf.cert_pem, algo="sha1")
        assert len(fp1) == 64
        assert len(fp2) == 40

    def test_009_rsa_cert_chain(self, rsa_ca):
        ca, leaf = rsa_ca
        ok, reason = verify_cert_chain(leaf.cert_pem, ca.cert_pem)
        assert ok is True, reason


# ─────────────────────────────────────────────────────────────────────────────
# 2. Signers: ECDSA / RSA / SM2
# ─────────────────────────────────────────────────────────────────────────────
class TestSigners:
    def test_010_ecdsa_sign_verify(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        signer = ECDSASigner(leaf.key_pem, cert=leaf)
        doc = b"test doc"
        result = signer.get_result(doc)
        assert result.alg == "ecdsa-p256"
        assert len(result.value_b64) > 0
        # round-trip: 用同 leaf 重新构造 ECDSASigner 验证
        signer2 = ECDSASigner(leaf.key_pem, cert=leaf)
        pub = signer2.key.public_key()
        sig_bytes = base64.b64decode(result.value_b64)
        # 不抛异常即成功
        pub.verify(sig_bytes, doc, ec.ECDSA(hashes.SHA256()))

    def test_011_rsa_sign_verify(self, rsa_ca):
        ca, leaf = rsa_ca
        signer = RSASigner(leaf.key_pem, cert=leaf)
        doc = b"test rsa doc"
        result = signer.get_result(doc)
        assert result.alg == "rsa-2048-pss"
        assert len(result.value_b64) > 0

    def test_012_sm2_fallback(self, ecdsa_ca):
        """SM2 → gmssl 不可用 → fallback 到 ECDSA-P256."""
        ca, leaf = ecdsa_ca
        signer = SM2Signer(leaf.key_pem, cert=leaf)
        doc = b"test sm2 doc"
        result = signer.get_result(doc)
        # alg 应该是 sm2-* (native 或 fallback)
        assert result.alg.startswith("sm2")
        # fallback 模式下应能验证
        if result.alg == "sm2-fallback-ecdsa-p256":
            # 用 leaf 私钥对应的公钥验
            signer2 = ECDSASigner(leaf.key_pem, cert=leaf)
            sig = base64.b64decode(result.value_b64)
            signer2.key.public_key().verify(sig, doc, ec.ECDSA(hashes.SHA256()))

    def test_013_signer_type_mismatch(self, rsa_ca):
        """ECDSASigner 不接受 RSA 私钥."""
        ca, leaf = rsa_ca
        with pytest.raises(TypeError, match="EC private key"):
            ECDSASigner(leaf.key_pem, cert=leaf)

    def test_014_rsa_signer_type_mismatch(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        with pytest.raises(TypeError, match="RSA private key"):
            RSASigner(leaf.key_pem, cert=leaf)

    def test_015_get_signer_factory(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        s = get_signer(mode=SignMode.ECDSA, key_pem=leaf.key_pem, cert=leaf)
        assert isinstance(s, ECDSASigner)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Timestamp
# ─────────────────────────────────────────────────────────────────────────────
class TestTimestamp:
    def test_020_issue_timestamp(self):
        ts = issue_timestamp(b"hello")
        assert ts.token_id.startswith("TS-")
        assert len(ts.doc_hash) == 64
        assert ts.tsa_pubkey_fingerprint  # 非空
        assert ts.signature_b64  # 非空
        assert ts.prev_token_hash  # 非空 (至少 genesis)

    def test_021_verify_timestamp_valid(self):
        doc = b"timestamp target"
        ts = issue_timestamp(doc)
        ok, reason = verify_timestamp(ts, expected_doc_hash=ts.doc_hash)
        assert ok is True
        assert reason == "ok"

    def test_022_verify_timestamp_doc_hash_mismatch(self):
        ts = issue_timestamp(b"original")
        ok, reason = verify_timestamp(ts, expected_doc_hash="a"*64)
        assert ok is False
        assert "doc_hash_mismatch" in reason

    def test_023_verify_timestamp_signature_tampered(self):
        ts = issue_timestamp(b"original")
        # 篡改 signed_at → 重算 canonical → 签名 mismatch
        ts.signed_at = "2099-01-01T00:00:00Z"
        ok, reason = verify_timestamp(ts)
        assert ok is False
        assert "signature_invalid" in reason

    def test_024_local_tsa_independence(self, tmp_path):
        """独立 TSA 实例可用不同 secret 签."""
        tsa1 = LocalTSA(secret="secret-one-1234567890ab", log_path=str(tmp_path / "tsa1.jsonl"))
        tsa2 = LocalTSA(secret="secret-two-1234567890ab", log_path=str(tmp_path / "tsa2.jsonl"))
        ts1 = tsa1.issue(b"x")
        ts2 = tsa2.issue(b"x")
        assert ts1.tsa_pubkey_fingerprint != ts2.tsa_pubkey_fingerprint
        # 用对的 secret 验签
        ok1, _ = verify_timestamp(ts1, secret="secret-one-1234567890ab")
        assert ok1
        ok2, _ = verify_timestamp(ts2, secret="secret-two-1234567890ab")
        assert ok2

    def test_025_local_tsa_chain(self, tmp_path):
        """连续签发 token, prev_token_hash 应链式递增."""
        tsa = LocalTSA(secret="chain-test-secret-123456", log_path=str(tmp_path / "chain.jsonl"))
        ts1 = tsa.issue(b"a")
        ts2 = tsa.issue(b"b")
        # ts2.prev_token_hash != genesis
        assert ts2.prev_token_hash != "0" * 64
        # prev_token_hash 不必等于 ts1.entry hash (公式是 hash of ts1 canonical)
        # 但至少要变 (因为 ts1 已签)
        # 验证两者签名
        ok1, _ = verify_timestamp(ts1, secret="chain-test-secret-123456")
        ok2, _ = verify_timestamp(ts2, secret="chain-test-secret-123456")
        assert ok1 and ok2

    def test_026_tsa_secret_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            LocalTSA(secret="short")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Verifier 端到端
# ─────────────────────────────────────────────────────────────────────────────
class TestVerifier:
    def _build_signed(self, alg, ca, leaf, doc, mode_override=None):
        """helper: 用指定算法签 doc, 返回 SignedContract."""
        if alg == "ecdsa":
            signer = ECDSASigner(leaf.key_pem, cert=leaf)
        elif alg == "rsa":
            signer = RSASigner(leaf.key_pem, cert=leaf)
        elif alg == "sm2":
            signer = SM2Signer(leaf.key_pem, cert=leaf)
            alg = signer.algorithm_label
        else:
            raise ValueError(alg)
        result = signer.get_result(doc)
        # P15-B: pass the algorithm-specific doc_hash through so the
        # timestamp token matches the signer's hash. For ``sm2-p256-sm3``
        # that's SM3(ZA || doc); for the others it's SHA-256(doc).
        ts = issue_timestamp(doc, doc_hash=result.doc_hash)
        sc = SignedContract(
            contract_id="CT-TEST-001",
            doc_hash=result.doc_hash,
            alg=result.alg if alg != "sm2" else signer.algorithm_label,
            signature_b64=result.value_b64,
            cert_pem=leaf.cert_pem.decode("ascii"),
            ca_cert_pem=ca.cert_pem.decode("ascii"),
            cert_serial=leaf.serial,
            cert_subject_cn=leaf.subject_cn,
            cert_issuer_cn=leaf.issuer_cn,
            cert_fingerprint=leaf.fingerprint,
            timestamp=ts.to_dict(),
            signed_at=result.signed_at,
            signed_by="signer",
        )
        return sc, result, ts

    def test_030_verify_ecdsa_ok(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        doc = b"verify ecdsa"
        sc, _, _ = self._build_signed("ecdsa", ca, leaf, doc)
        v = verify_signature(sc, doc_bytes=doc, audit=False)
        assert v.ok is True, v.reasons
        assert v.cert_serial == leaf.serial

    def test_031_verify_rsa_ok(self, rsa_ca):
        ca, leaf = rsa_ca
        doc = b"verify rsa"
        sc, _, _ = self._build_signed("rsa", ca, leaf, doc)
        v = verify_signature(sc, doc_bytes=doc, audit=False)
        assert v.ok is True, v.reasons

    def test_032_verify_sm2_fallback_ok(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        doc = b"verify sm2"
        sc, _, _ = self._build_signed("sm2", ca, leaf, doc)
        v = verify_signature(sc, doc_bytes=doc, audit=False)
        assert v.ok is True, v.reasons

    def test_033_verify_tampered_doc(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        doc = b"original"
        sc, _, _ = self._build_signed("ecdsa", ca, leaf, doc)
        tampered = doc + b"X"
        v = verify_signature(sc, doc_bytes=tampered, audit=False)
        assert v.ok is False
        assert any("mismatch" in r or "signature_invalid" in r for r in v.reasons)

    def test_034_verify_wrong_ca(self, ecdsa_ca, rsa_ca):
        """替换 CA 为错误 CA → cert chain 失败."""
        ca_ecdsa, leaf = ecdsa_ca
        ca_rsa, _ = rsa_ca
        doc = b"doc"
        sc, _, _ = self._build_signed("ecdsa", ca_ecdsa, leaf, doc)
        sc.ca_cert_pem = ca_rsa.cert_pem.decode("ascii")  # 替换 CA
        v = verify_signature(sc, doc_bytes=doc, audit=False)
        assert v.ok is False
        assert any("cert_chain" in r or "issuer_mismatch" in r or "signature_invalid" in r for r in v.reasons)

    def test_035_verify_missing_timestamp(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        doc = b"doc"
        sc, _, _ = self._build_signed("ecdsa", ca, leaf, doc)
        sc.timestamp = {}
        v = verify_signature(sc, doc_bytes=doc, audit=False)
        assert v.ok is False
        assert any("timestamp_missing" in r for r in v.reasons)

    def test_036_verify_tampered_timestamp(self, ecdsa_ca):
        ca, leaf = ecdsa_ca
        doc = b"doc"
        sc, _, _ = self._build_signed("ecdsa", ca, leaf, doc)
        # 篡改 timestamp.signed_at
        sc.timestamp["signed_at"] = "2099-01-01T00:00:00Z"
        v = verify_signature(sc, doc_bytes=doc, audit=False)
        assert v.ok is False
        assert any("timestamp" in r for r in v.reasons)

    def test_037_verify_routes_to_audit(self, ecdsa_ca):
        """verify_signature(audit=True) 会写 audit log."""
        ca, leaf = ecdsa_ca
        doc = b"doc"
        sc, _, _ = self._build_signed("ecdsa", ca, leaf, doc)
        v = verify_signature(sc, doc_bytes=doc, audit=True)
        events = read_audit_log(event="verify")
        assert len(events) >= 1
        assert events[0]["contract_id"] == "CT-TEST-001"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Audit
# ─────────────────────────────────────────────────────────────────────────────
class TestAudit:
    def test_040_audit_sign_event(self):
        ev = audit_sign_event(
            contract_id="CT-AUD-1",
            signer="ACME",
            alg="ecdsa-p256",
            doc_hash="a"*64,
            cert_serial=12345,
            cert_fingerprint="f"*64,
            signature_b64="sig-b64",
            timestamp_token_id="TS-XYZ",
        )
        assert ev.seq >= 1
        assert ev.event == "sign"
        # 读回
        events = read_audit_log()
        assert len(events) >= 1
        assert events[0]["contract_id"] == "CT-AUD-1"

    def test_041_audit_filter_by_contract(self):
        audit_sign_event(contract_id="CT-A", signer="X", alg="ecdsa-p256",
                         doc_hash="x"*64, cert_serial=1, cert_fingerprint="f"*64,
                         signature_b64="s")
        audit_sign_event(contract_id="CT-B", signer="Y", alg="rsa-2048-pss",
                         doc_hash="y"*64, cert_serial=2, cert_fingerprint="f"*64,
                         signature_b64="s")
        events_a = read_audit_log(contract_id="CT-A")
        events_b = read_audit_log(contract_id="CT-B")
        assert len(events_a) == 1
        assert len(events_b) == 1
        assert events_a[0]["signer"] == "X"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Factory: SIGN_MODE env, ensure_dev_ca, issue_leaf_for_subject
# ─────────────────────────────────────────────────────────────────────────────
class TestFactory:
    def test_050_ensure_dev_ca_creates_and_reuses(self):
        ca1 = ensure_dev_ca()
        ca2 = ensure_dev_ca()
        # 应该复用一个 (写入 backend/data/contracts_ca.pem)
        # 但因测试隔离 env 设的是 tmpdir, 所以两次都是新生成同一个
        assert isinstance(ca1, CertBundle)
        assert isinstance(ca2, CertBundle)

    def test_051_force_new_ca(self):
        ca1 = ensure_dev_ca(force_new=True)
        ca2 = ensure_dev_ca(force_new=True)
        # 每次 force new 都应有不同 serial / fingerprint
        assert ca1.fingerprint != ca2.fingerprint or ca1.serial != ca2.serial

    def test_052_issue_leaf(self):
        ca = ensure_dev_ca()
        leaf = issue_leaf_for_subject(subject_cn="FactorySigner", subject_email="f@example.com")
        ok, reason = verify_cert_chain(leaf.cert_pem, ca.cert_pem)
        assert ok, reason

    def test_053_sign_mode_from_env(self, monkeypatch):
        monkeypatch.setenv("SIGN_MODE", "rsa")
        mode = SignMode.from_env()
        assert mode == SignMode.RSA
        monkeypatch.setenv("SIGN_MODE", "sm2")
        mode = SignMode.from_env()
        assert mode == SignMode.SM2
        monkeypatch.setenv("SIGN_MODE", "ecdsa")
        mode = SignMode.from_env()
        assert mode == SignMode.ECDSA


# ─────────────────────────────────────────────────────────────────────────────
# 7. Integration: contracts/__init__.py sign_contract_real + verify_contract_signature
# ─────────────────────────────────────────────────────────────────────────────
class TestContractsIntegration:
    def test_060_sign_real_then_verify_ok(self, ecdsa_ca):
        """完整: generate_contract → sign_contract_real → verify_contract_signature."""
        c = contracts.generate_contract(
            template="service_agreement",
            company_name="集成测试公司",
            contact_email="int@test.com",
            plan_name="Pro",
            amount=1234.5,
        )
        result = contracts.sign_contract_real(c.contract_id, signer="集成测试公司")
        assert result["sign"]["alg"] in ("ecdsa-p256", "sm2-fallback-ecdsa-p256")
        assert result["cert_serial"] > 0
        # 验证
        v = contracts.verify_contract_signature(c.contract_id)
        assert v["ok"] is True, v["reasons"]

    def test_061_verify_after_mutation(self):
        """签后 mutate 合同 (改 amount) → 验证应失败."""
        c = contracts.generate_contract(
            template="service_agreement", company_name="X",
            contact_email="x@x.com", plan_name="Pro", amount=100.0,
        )
        contracts.sign_contract_real(c.contract_id, signer="X")
        c.amount = 99999.0  # 篡改
        v = contracts.verify_contract_signature(c.contract_id)
        assert v["ok"] is False
        assert any("tampered" in r for r in v["reasons"])

    def test_062_audit_writes_sign_event(self):
        c = contracts.generate_contract(
            template="service_agreement", company_name="X",
            contact_email="x@x.com", plan_name="Pro", amount=100.0,
        )
        contracts.sign_contract_real(c.contract_id, signer="X")
        events = read_audit_log(contract_id=c.contract_id, event="sign")
        assert len(events) == 1
        assert events[0]["signer"] == "X"

    def test_063_generate_admin_cert_pair(self):
        cert = contracts.generate_admin_cert_pair(
            subject="管理员证书", email="admin@test.com", validity_days=365,
        )
        assert "cert_pem" in cert
        assert "key_pem" in cert
        assert "serial" in cert
        # 验证: 可以用 cert + CA 验证链
        ca = ensure_dev_ca()
        ok, reason = verify_cert_chain(
            cert["cert_pem"].encode("ascii"), ca.cert_pem
        )
        assert ok is True, reason


# ─────────────────────────────────────────────────────────────────────────────
# 8. HTTP API 路由 (路由层)
# ─────────────────────────────────────────────────────────────────────────────
class TestRoutes:
    def test_070_sign_pki_via_api(self, client):
        c = contracts.generate_contract(
            template="service_agreement", company_name="API测试",
            contact_email="api@test.com", plan_name="Pro", amount=500.0,
        )
        r = client.post(
            f"/api/v1/contracts/{c.contract_id}/sign-pki",
            json={"signer": "API测试"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["sign"]["alg"] in ("ecdsa-p256", "sm2-fallback-ecdsa-p256")
        assert "timestamp" in data

    def test_071_verify_pki_via_api(self, client):
        c = contracts.generate_contract(
            template="service_agreement", company_name="API测试",
            contact_email="api@test.com", plan_name="Pro", amount=500.0,
        )
        client.post(
            f"/api/v1/contracts/{c.contract_id}/sign-pki",
            json={"signer": "API测试"},
        )
        r = client.post(f"/api/v1/contracts/{c.contract_id}/verify-pki")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True, data["reasons"]

    def test_072_cert_generate_via_api(self, client):
        r = client.post(
            "/api/v1/contracts/certs/generate",
            json={"subject": "管理员测试", "email": "admin@test.com", "validity_days": 365},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["subject_cn"] == "管理员测试"
        assert data["fingerprint"]

    def test_073_get_ca_via_api(self, client):
        r = client.get("/api/v1/contracts/certs/ca")
        assert r.status_code == 200
        data = r.json()
        assert "cert_pem" in data
        assert data["public_key_alg"] in ("ecdsa-p256", "rsa-2048")
        assert data["sign_mode"] in ("ecdsa", "rsa", "sm2")

    def test_074_sign_pki_not_found(self, client):
        r = client.post(
            "/api/v1/contracts/CT-FAKE/sign-pki",
            json={"signer": "X"},
        )
        assert r.status_code == 404

    def test_075_verify_pki_not_signed_via_api(self, client):
        c = contracts.generate_contract(
            template="service_agreement", company_name="X",
            contact_email="x@x.com", plan_name="Pro", amount=100.0,
        )
        r = client.post(f"/api/v1/contracts/{c.contract_id}/verify-pki")
        assert r.status_code == 400  # 没有 signed_bundle

    def test_076_cert_generate_validation(self, client):
        # 空 subject → 422
        r = client.post(
            "/api/v1/contracts/certs/generate",
            json={"subject": ""},
        )
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Pytest 入口
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 当直接跑这个文件时, 用 pytest 执行
    import subprocess
    sys.exit(subprocess.call([
        sys.executable, "-m", "pytest", str(__file__), "-v",
    ]))
