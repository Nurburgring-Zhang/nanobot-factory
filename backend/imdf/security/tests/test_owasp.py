"""V5 第40章 — OWASP Top 10 防护层测试 (≥15 测试).

覆盖: 10 个 OWASP 类别各至少 1 测试 + AccessControl 6 角色 × 7 资源
权限矩阵 + crypto round-trip + JWT 过期/签名错误 + SSRF 4 个常见 bad URL.
"""
from __future__ import annotations

import os
import time

import pytest

from imdf.security.owasp_protection import (
    AccessControl,
    Cryptographic,
    IdentificationAuth,
    Injection,
    IntegrityFailures,
    LoggingMonitoring,
    OWASPProtection,
    SecureDesign,
    SecurityConfig,
    SSRFProtection,
    VulnerableComponents,
)
from imdf.security.schemas import PIIType


# ═══════════════════════════════════════════════════════════════════════
#  A01 — Access Control (RBAC + ABAC)
# ═══════════════════════════════════════════════════════════════════════
class TestAccessControl:
    def test_admin_has_all_permissions(self):
        ac = AccessControl()
        for r in ("project", "requirement", "dataset", "pack",
                  "annotation", "qc", "delivery"):
            for a in ("read", "write", "delete"):
                d = ac.check_permission("u1", r, a, roles=["admin"])
                assert d.allowed, f"admin should access {r}.{a}"

    def test_project_owner_only_own_projects(self):
        ac = AccessControl()
        # 自己是 owner → 允许
        d_ok = ac.check_permission("alice", "project", "write",
                                    context={"owner_user": "alice"},
                                    roles=["project_owner"])
        assert d_ok.allowed
        # 别人 owner → 拒绝
        d_no = ac.check_permission("alice", "project", "write",
                                    context={"owner_user": "bob"},
                                    roles=["project_owner"])
        assert not d_no.allowed

    def test_annotator_only_assigned_writes(self):
        ac = AccessControl()
        d_ok = ac.check_permission("ann", "annotation", "write",
                                    context={"assigned_user": "ann"},
                                    roles=["annotator"])
        assert d_ok.allowed
        d_no = ac.check_permission("ann", "annotation", "write",
                                    context={"assigned_user": "bob"},
                                    roles=["annotator"])
        assert not d_no.allowed

    def test_viewer_read_only(self):
        ac = AccessControl()
        for r in ("project", "dataset", "annotation", "qc"):
            d_read = ac.check_permission("v", r, "read", roles=["viewer"])
            assert d_read.allowed, f"viewer should read {r}"
            d_write = ac.check_permission("v", r, "write", roles=["viewer"])
            assert not d_write.allowed

    def test_unknown_role_denied(self):
        ac = AccessControl()
        d = ac.check_permission("u", "project", "write", roles=["ghost"])
        assert not d.allowed

    def test_qc_staff_can_approve_qc(self):
        ac = AccessControl()
        d = ac.check_permission("qc1", "qc", "approve", roles=["qc_staff"])
        assert d.allowed

    def test_reviewer_can_approve_pack(self):
        ac = AccessControl()
        d = ac.check_permission("rev1", "pack", "approve", roles=["reviewer"])
        assert d.allowed


# ═══════════════════════════════════════════════════════════════════════
#  A02 — Cryptographic
# ═══════════════════════════════════════════════════════════════════════
class TestCryptographic:
    def test_password_hash_and_verify_roundtrip(self):
        h = Cryptographic.hash_password("S3cure!Pass")
        assert h != "S3cure!Pass"
        assert Cryptographic.verify_password("S3cure!Pass", h) is True
        assert Cryptographic.verify_password("wrong", h) is False

    def test_aes_gcm_encrypt_decrypt_roundtrip(self):
        key = Cryptographic.generate_aes_key()
        blob = Cryptographic.aes_encrypt(b"hello-confidential", key)
        out = Cryptographic.aes_decrypt(blob, key)
        assert out == b"hello-confidential"

    def test_aes_gcm_aad_binding(self):
        key = Cryptographic.generate_aes_key()
        blob = Cryptographic.aes_encrypt(b"payload", key,
                                          associated_data=b"context-x")
        out = Cryptographic.aes_decrypt(blob, key, associated_data=b"context-x")
        assert out == b"payload"
        # 不同 AAD → 解密失败
        with pytest.raises(Exception):
            Cryptographic.aes_decrypt(blob, key, associated_data=b"context-y")

    def test_aes_key_length_enforced(self):
        with pytest.raises(ValueError):
            Cryptographic.aes_encrypt(b"x", b"short-key")


# ═══════════════════════════════════════════════════════════════════════
#  A03 — Injection
# ═══════════════════════════════════════════════════════════════════════
class TestInjection:
    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE users; --",
        "1 OR 1=1",
        "admin'--",
        "<script>alert(1)</script>",
        "javascript:alert(1)",
        "$where: this.x == 1",
    ])
    def test_sanitize_blocks_injection(self, payload):
        ok, reason = Injection.sanitize_input(payload)
        assert not ok
        assert "blocked" in reason

    def test_sanitize_passes_clean_text(self):
        ok, _ = Injection.sanitize_input("hello world 张三 123 abc")
        assert ok

    @pytest.mark.parametrize("path", [
        "../etc/passwd",
        "../../../../windows/system32",
        "/absolute/etc/passwd",
        "C:\\Windows\\System32",
        "~/secret/file",
    ])
    def test_validate_path_blocks_traversal(self, path):
        ok, _ = Injection.validate_path(path)
        assert not ok

    def test_validate_path_allows_normal(self):
        ok, _ = Injection.validate_path("datasets/project_001/ann.json")
        assert ok

    def test_validate_path_allowed_roots(self):
        ok, _ = Injection.validate_path("data/file.csv", allowed_roots=["data/"])
        assert ok
        ok2, _ = Injection.validate_path("etc/passwd", allowed_roots=["data/"])
        assert not ok2


# ═══════════════════════════════════════════════════════════════════════
#  A04 — Insecure Design (RateLimiter + AuditChain + InputValidator)
# ═══════════════════════════════════════════════════════════════════════
class TestSecureDesign:
    def test_rate_limiter_blocks_burst(self):
        rl = SecureDesign.RateLimiter(max_requests=3, window_seconds=60.0)
        assert rl.allow("k1")
        assert rl.allow("k1")
        assert rl.allow("k1")
        assert not rl.allow("k1")

    def test_audit_chain_verify(self):
        chain = SecureDesign.AuditChain()
        chain.append("e1", "alice", {"x": 1})
        chain.append("e2", "bob", {"y": 2})
        assert chain.verify()
        assert len(chain) == 2

    def test_input_validator_rejects_nul(self):
        ok, _ = SecureDesign.InputValidator.validate_string("hello\x00world")
        assert not ok

    def test_input_validator_rejects_oversize(self):
        ok, _ = SecureDesign.InputValidator.validate_string("a" * 70000)
        assert not ok


# ═══════════════════════════════════════════════════════════════════════
#  A05 — Security Misconfiguration
# ═══════════════════════════════════════════════════════════════════════
class TestSecurityConfig:
    def test_password_policy_pass(self):
        ok, _ = SecurityConfig.check_password("Aa1!secure")
        assert ok

    def test_password_policy_short_fail(self):
        ok, _ = SecurityConfig.check_password("Aa1!")
        assert not ok

    def test_password_policy_missing_upper_fail(self):
        ok, _ = SecurityConfig.check_password("aa1!secure")
        assert not ok

    def test_config_get_returns_default(self):
        assert SecurityConfig.get("nonexistent", "default") == "default"
        assert SecurityConfig.get("jwt_algorithm") == "HS256"


# ═══════════════════════════════════════════════════════════════════════
#  A06 — Vulnerable Components
# ═══════════════════════════════════════════════════════════════════════
class TestVulnerableComponents:
    def test_check_requirements_finds_vulnerable(self):
        text = (
            "django==4.0.0\n"
            "requests==2.31.0\n"
            "pillow>=10.0.0\n"
        )
        findings = VulnerableComponents.check_requirements_text(text)
        pkgs = {f["package"] for f in findings}
        assert "django" in pkgs
        assert "requests" in pkgs
        # 10.0.0 >= 10.3.0 → vulnerable
        assert "pillow" in pkgs

    def test_check_requirements_safe_packages(self):
        text = "django==4.2.11\nrequests==2.32.0\n"
        findings = VulnerableComponents.check_requirements_text(text)
        assert findings == []


# ═══════════════════════════════════════════════════════════════════════
#  A07 — Identification & Auth Failures (JWT + Session)
# ═══════════════════════════════════════════════════════════════════════
class TestIdentificationAuth:
    def test_jwt_sign_verify_roundtrip(self):
        mgr = IdentificationAuth.JWTManager(secret="test-secret")
        token = mgr.sign("alice", roles=["admin"])
        payload = mgr.verify(token)
        assert payload.sub == "alice"
        assert "admin" in payload.roles

    def test_jwt_expired_rejected(self):
        mgr = IdentificationAuth.JWTManager(secret="s", expiry_seconds=-1)
        token = mgr.sign("bob")
        with pytest.raises(ValueError, match="expired"):
            mgr.verify(token)

    def test_jwt_invalid_signature_rejected(self):
        mgr1 = IdentificationAuth.JWTManager(secret="secret-a")
        mgr2 = IdentificationAuth.JWTManager(secret="secret-b")
        token = mgr1.sign("alice")
        with pytest.raises(ValueError):
            mgr2.verify(token)

    def test_session_create_validate_invalidate(self):
        sm = IdentificationAuth.SessionManager()
        sid = sm.create("alice", roles=["viewer"])
        sess = sm.validate(sid)
        assert sess and sess["user"] == "alice"
        sm.invalidate(sid)
        assert sm.validate(sid) is None

    def test_session_lockout_after_failures(self):
        sm = IdentificationAuth.SessionManager(max_failures=3, lockout_seconds=10)
        for _ in range(3):
            sm.record_failure("evil")
        with pytest.raises(ValueError, match="locked"):
            sm.create("evil")


# ═══════════════════════════════════════════════════════════════════════
#  A08 — Integrity Failures
# ═══════════════════════════════════════════════════════════════════════
class TestIntegrityFailures:
    def test_signature_roundtrip(self):
        sv = IntegrityFailures.SignatureVerifier(secret=b"k" * 32)
        sig = sv.sign(b"artifact-bytes")
        assert sv.verify(b"artifact-bytes", sig)
        assert not sv.verify(b"tampered", sig)

    def test_attestation_roundtrip(self):
        att = IntegrityFailures.CIArtifactAttestation()
        rec = att.attest("build-001", "s3://artifacts/v1.bin", "abc123")
        assert rec["signature"]
        assert att.verify("build-001")
        assert not att.verify("build-002")


# ═══════════════════════════════════════════════════════════════════════
#  A09 — Logging & Monitoring
# ═══════════════════════════════════════════════════════════════════════
class TestLoggingMonitoring:
    def test_event_logger_records(self):
        logger = LoggingMonitoring.SecurityEventLogger()
        ev1 = logger.log_auth_success("alice", ip="1.2.3.4")
        ev2 = logger.log_auth_failure("eve", ip="5.6.7.8")
        ev3 = logger.log_config_change("admin", key="jwt_expiry")
        assert ev1.event_type == "auth.login"
        assert ev2.severity == "warn"
        assert ev3.severity == "critical"
        events = logger.list_events()
        assert len(events) == 3

    def test_event_logger_publishes_to_bus(self):
        class _Bus:
            def __init__(self):
                self.records = []
            def publish(self, topic, payload):
                self.records.append((topic, payload))

        bus = _Bus()
        logger = LoggingMonitoring.SecurityEventLogger(bus=bus)
        logger.log_auth_success("alice")
        assert len(bus.records) == 1
        topic, payload = bus.records[0]
        assert topic == "security.event"
        assert payload["actor"] == "alice"


# ═══════════════════════════════════════════════════════════════════════
#  A10 — SSRF Protection
# ═══════════════════════════════════════════════════════════════════════
class TestSSRFProtection:
    @pytest.mark.parametrize("bad_url", [
        # IPv4 private / loopback / link-local
        "http://127.0.0.1/admin",
        "http://10.0.0.1/admin",
        "http://192.168.1.1/admin",
        "http://localhost/api",
        "http://0.0.0.0/x",
        "http://172.16.0.1/internal",
        # IPv6 loopback (verifier AP8 — CRITICAL bypass)
        "http://[::1]/admin",
        "http://[::1]:8080/admin",
        "https://[::1]:443/admin",
        "http://[::]/admin",                              # IPv6 unspecified
        # IPv6 link-local
        "http://[fe80::1]/admin",
        # IPv6 unique-local (fc00::/7)
        "http://[fc00::1]/admin",
        "http://[fd00:ec2::254]/latest/meta-data/",        # AWS IPv6 metadata
        # IPv4-mapped IPv6 (real loopback via dual-stack)
        "http://[::ffff:127.0.0.1]/admin",
        # reserved / non-routable
        "http://[2001:db8::1]/admin",                     # 2001:db8::/32 documentation
        # 其他 bad scheme / internal hostname
        "ftp://example.com/file",
        "http://internal.corp/api",
    ])
    def test_url_validator_blocks(self, bad_url):
        v = SSRFProtection.URLValidator()
        ok, reason = v.validate(bad_url)
        assert not ok, f"should block {bad_url}, got ok=True reason={reason!r}"

    def test_url_validator_allows_public_ipv6(self):
        """IPv6 公网地址 (非 private/loopback/link-local) 应放行."""
        v = SSRFProtection.URLValidator()
        # Cloudflare DNS IPv6
        ok, reason = v.validate("https://[2606:4700:4700::1111]/dns-query")
        assert ok, f"public IPv6 should be allowed, got reason={reason!r}"
        # Google Public DNS IPv6
        ok2, reason2 = v.validate("https://[2001:4860:4860::8888]/resolve")
        assert ok2, f"public IPv6 should be allowed, got reason={reason2!r}"

    def test_url_validator_allows_public(self):
        v = SSRFProtection.URLValidator()
        ok, _ = v.validate("https://api.github.com/repos")
        assert ok

    def test_url_validator_whitelist(self):
        v = SSRFProtection.URLValidator(allowed_hosts=["api.example.com"])
        ok, _ = v.validate("https://api.example.com/v1")
        assert ok
        ok2, _ = v.validate("https://other.com/v1")
        assert not ok2

    def test_http_client_blocks_ssrf(self):
        client = SSRFProtection.HttpClient()
        r = client.get("http://127.0.0.1/x")
        assert not r["ok"]
        assert "ok" in r
        assert "error" in r

    def test_http_client_allows_public(self):
        client = SSRFProtection.HttpClient()
        r = client.get("https://example.com/")
        assert r["ok"]
        assert r["status"] == 200


# ═══════════════════════════════════════════════════════════════════════
#  Aggregate — OWASPProtection 主类
# ═══════════════════════════════════════════════════════════════════════
class TestOWASPProtectionAggregate:
    def test_protect_request_grants_clean_admin(self):
        ow = OWASPProtection()
        req = {
            "user": "alice", "resource": "project", "action": "read",
            "roles": ["admin"],
            "inputs": {"name": "safe-text"},
            "path": "datasets/x.json",
            "url": "https://api.github.com/x",
        }
        r = ow.protect_request(req)
        assert r.permission.allowed
        assert r.rate_limit_ok
        assert r.ssrf_checked
        assert r.integrity_ok
        assert r.errors == []

    def test_protect_request_blocks_injection(self):
        ow = OWASPProtection()
        req = {
            "user": "alice", "resource": "project", "action": "read",
            "roles": ["admin"],
            "inputs": {"q": "'; DROP TABLE users; --"},
        }
        r = ow.protect_request(req)
        assert any("injection" in e for e in r.errors)
        assert "[BLOCKED" in r.sanitized_input["q"]

    def test_protect_request_blocks_path_traversal(self):
        ow = OWASPProtection()
        req = {
            "user": "alice", "resource": "project", "action": "read",
            "roles": ["admin"],
            "path": "../../etc/passwd",
        }
        r = ow.protect_request(req)
        assert any("path traversal" in e for e in r.errors)
        assert r.safe_path is None

    def test_protect_request_denies_viewer_write(self):
        ow = OWASPProtection()
        req = {
            "user": "v1", "resource": "project", "action": "write",
            "roles": ["viewer"],
        }
        r = ow.protect_request(req)
        assert not r.permission.allowed

    def test_audit_event_writes_to_chain_and_logger(self):
        ow = OWASPProtection()
        ev = ow.audit_event("custom.event", "alice", {"k": "v"})
        assert ev.event_type == "custom.event"
        assert ev.actor == "alice"
        assert len(ow.audit_chain) >= 1
        assert ow.audit_chain.verify()

    def test_protect_request_rate_limit_eventually_blocks(self):
        ow = OWASPProtection()
        ow.rate_limiter = SecureDesign.RateLimiter(max_requests=2, window_seconds=60.0)
        req = {"user": "u", "resource": "x", "action": "r", "roles": ["admin"]}
        ow.protect_request(req)
        ow.protect_request(req)
        r = ow.protect_request(req)
        assert any("rate limit" in e for e in r.errors)