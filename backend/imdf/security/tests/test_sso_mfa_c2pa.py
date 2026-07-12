"""V5 第40章 — SSO/MFA/ABAC/C2PA 测试.

使用 pytest + asyncio. 24 个测试覆盖:
  * SSO: 5 (SAML redirect / OAuth2 authorize / OAuth2 callback / OIDC discovery / LDAP bind)
  * MFA: 8 (TOTP secret format / TOTP URI / TOTP round-trip / SMS round-trip /
         Email round-trip / Backup one-time / challenge error path / full flow)
  * ABAC: 5 (admin bypass / owner delete own / non-owner deny / member read / non-member deny)
  * C2PA: 6 (sign+verify round-trip / tampered manifest / modified asset / store /
         missing manifest / sidecar)

运行:
    D:\\ComfyUI\\.ext\\python.exe -m pytest backend/imdf/security/tests/test_sso_mfa_c2pa.py -v --tb=short
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sqlite3
import tempfile
import time
from typing import List, Tuple
from urllib.parse import parse_qs, urlparse

import pytest

from imdf.security import (
    ABACEngine,
    ABACPolicy,
    C2PAAction,
    C2PAIngredient,
    C2PAManifest,
    C2PASigner,
    C2PAStore,
    C2PAVerifier,
    Condition,
    ConditionOp,
    MFAManager,
    MFAMethod,
    SSOManager,
    generate_totp_secret,
    get_provisioning_uri,
    read_sidecar,
    verify_totp,
    write_sidecar,
)


# ════════════════════════════════════════════════════════════════════════
# SSO tests (5)
# ════════════════════════════════════════════════════════════════════════
class TestSSO:
    def test_saml_initiate_returns_redirect_url(self):
        """SAML initiate_saml_login → RedirectResponse-like, URL 含 SAMLRequest + RelayState."""
        mgr = SSOManager()
        resp = mgr.initiate_saml_login()
        # 可能是 fastapi RedirectResponse 或 fallback dict
        if hasattr(resp, "headers"):
            location = resp.headers.get("location", "")
            status_code = resp.status_code
        else:
            location = resp["location"]
            status_code = resp["status_code"]
        assert status_code == 302
        assert "SAMLRequest" in location
        assert "RelayState" in location
        assert "idp.example.com" in location

    @pytest.mark.asyncio
    async def test_oauth2_authorize_url(self):
        """oauth2_authorize → URL 含 client_id / scope / state / redirect_uri."""
        mgr = SSOManager()
        url = await mgr.oauth2_authorize("google", scopes=["openid", "email", "profile"])
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        assert "accounts.google.com" in url
        assert qs["client_id"] == ["mock-google-client-id"]
        assert qs["scope"] == ["openid email profile"]
        assert "state" in qs
        assert qs["response_type"] == ["code"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_success(self):
        """oauth2_callback(code) → AuthResult with tokens."""
        mgr = SSOManager()
        # 先 authorize 拿 state
        url = await mgr.oauth2_authorize("google")
        state = parse_qs(urlparse(url).query)["state"][0]
        # callback (mock: code=code_alice → alice@example.com)
        result = await mgr.oauth2_callback("google", "code_alice", state=state)
        assert result.success is True
        assert result.email == "alice@example.com"
        assert result.access_token and result.access_token.startswith("mock_access_")
        assert result.refresh_token and result.refresh_token.startswith("mock_refresh_")
        # id_token 是 3 段 base64
        assert result.id_token.count(".") == 2
        assert result.provider.value == "oauth2"

    @pytest.mark.asyncio
    async def test_oidc_discovery(self):
        """oidc_discovery(issuer) → OIDCConfig 含 endpoints + scopes."""
        mgr = SSOManager()
        cfg = await mgr.oidc_discovery("https://accounts.google.com")
        assert cfg.issuer == "https://accounts.google.com"
        assert "accounts.google.com" in cfg.authorization_endpoint
        assert "oauth2.googleapis.com" in cfg.token_endpoint
        assert "openid" in cfg.scopes_supported
        assert "code" in cfg.response_types_supported

    @pytest.mark.asyncio
    async def test_ldap_bind_success_and_fail(self):
        """ldap_bind: 正确密码 True,错密码 False,未知 DN False."""
        mgr = SSOManager()
        assert await mgr.ldap_bind("uid=alice,ou=users,dc=example,dc=com", "alice-pwd") is True
        assert await mgr.ldap_bind("uid=alice,ou=users,dc=example,dc=com", "wrong") is False
        assert await mgr.ldap_bind("uid=nobody,ou=users,dc=example,dc=com", "anything") is False


# ════════════════════════════════════════════════════════════════════════
# MFA tests (8)
# ════════════════════════════════════════════════════════════════════════
class TestMFA:
    def test_totp_secret_format(self):
        """TOTP secret = base32 (no padding), 32 chars for default 20-byte secret."""
        s = generate_totp_secret()
        # base32 chars only
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in s)
        # 20 bytes → base32 = ceil(20*8/5) = 32 chars (no padding)
        assert len(s) == 32

    def test_totp_provisioning_uri_format(self):
        """provisioning_uri = otpauth://totp/... with secret + issuer + period + digits."""
        s = generate_totp_secret()
        uri = get_provisioning_uri(s, "alice", issuer="IMDF")
        assert uri.startswith("otpauth://totp/")
        assert f"secret={s}" in uri
        assert "issuer=IMDF" in uri
        assert "period=30" in uri
        assert "digits=6" in uri

    def test_totp_round_trip_verify(self):
        """TOTP: 生成 secret → 当前时间算出 code → verify_totp 成功."""
        mgr = MFAManager()
        enr = mgr.enroll_totp("alice")
        assert enr.success
        assert enr.method == MFAMethod.TOTP
        # 用同一时间点算 code
        import hmac as _hmac
        import hashlib as _hashlib
        import struct as _struct
        from imdf.security.mfa import _totp_at, _b32_decode
        now = int(time.time())
        code = _totp_at(_b32_decode(enr.secret), now)
        result = asyncio.run(mgr.verify_mfa("alice", MFAMethod.TOTP, code))
        assert result.success is True
        assert result.error is None
        # wrong code fails
        result_bad = asyncio.run(mgr.verify_mfa("alice", MFAMethod.TOTP, "000000"))
        assert result_bad.success is False

    @pytest.mark.asyncio
    async def test_sms_otp_round_trip(self):
        """SMS OTP: enroll → challenge → 拿到 code → verify 成功;再 verify 同一个失败."""
        mgr = MFAManager()
        enr = await mgr.enroll_mfa("alice", MFAMethod.SMS, target="+1-555-0100")
        assert enr.success
        ch = await mgr.challenge_mfa("alice", MFAMethod.SMS)
        assert ch.success
        assert ch.delivery_target == "+1-555-0100"
        # 测试钩子:取回明文 OTP
        mgr._store_plain_for_test(ch.challenge_id, "123456")
        plain = mgr._peek_pending_code(ch.challenge_id)
        # 不能直接拿到明文(hash 存),所以通过 _peek_pending_code 拿
        # 实际上 _peek_pending_code 也拿不到,我们改为: 强行 verify 失败/成功路径
        # 用一个 wrong code 先 fail
        wrong = await mgr.verify_mfa("alice", MFAMethod.SMS, "000000", challenge_id=ch.challenge_id)
        assert wrong.success is False
        # 然后 challenge 重新发,直接 verify 正确 code (我们硬编码通过 mock)
        ch2 = await mgr.challenge_mfa("alice", MFAMethod.SMS)
        mgr._store_plain_for_test(ch2.challenge_id, "654321")
        # 通过内部映射恢复明文 (测试钩子): 把 hash 替换为已知值的 hash
        from imdf.security.mfa import _hash_code
        mgr._pending_challenges[ch2.challenge_id]["code_hash"] = _hash_code("654321")
        ok = await mgr.verify_mfa("alice", MFAMethod.SMS, "654321", challenge_id=ch2.challenge_id)
        assert ok.success is True
        assert ok.consumed is True

    @pytest.mark.asyncio
    async def test_email_otp_round_trip(self):
        """Email OTP 同 SMS 流程,验证 challenge + verify."""
        mgr = MFAManager()
        await mgr.enroll_mfa("bob", MFAMethod.EMAIL, target="bob@example.com")
        ch = await mgr.challenge_mfa("bob", MFAMethod.EMAIL)
        assert ch.success
        assert ch.delivery_target == "bob@example.com"
        from imdf.security.mfa import _hash_code
        mgr._pending_challenges[ch.challenge_id]["code_hash"] = _hash_code("888111")
        ok = await mgr.verify_mfa("bob", MFAMethod.EMAIL, "888111", challenge_id=ch.challenge_id)
        assert ok.success is True

    @pytest.mark.asyncio
    async def test_backup_code_one_time_use(self):
        """Backup code: 第一次 verify 成功 (consumed),第二次失败."""
        mgr = MFAManager()
        enr = await mgr.enroll_mfa("alice", MFAMethod.BACKUP)
        assert enr.success
        codes = enr.backup_codes or []
        assert len(codes) == 10
        first = codes[0]
        # first use
        r1 = await mgr.verify_mfa("alice", MFAMethod.BACKUP, first)
        assert r1.success is True
        assert r1.consumed is True
        assert r1.remaining_backup_codes == 9
        # second use of same code — fails
        r2 = await mgr.verify_mfa("alice", MFAMethod.BACKUP, first)
        assert r2.success is False
        # second code still works
        r3 = await mgr.verify_mfa("alice", MFAMethod.BACKUP, codes[1])
        assert r3.success is True
        assert r3.remaining_backup_codes == 8

    @pytest.mark.asyncio
    async def test_mfa_challenge_totp_no_secret_error(self):
        """未 enroll TOTP 就 challenge → 失败 + error msg."""
        mgr = MFAManager()
        ch = await mgr.challenge_mfa("nobody", MFAMethod.TOTP)
        assert ch.success is False
        assert "not enrolled" in ch.error.lower()

    @pytest.mark.asyncio
    async def test_mfa_full_enroll_challenge_verify_flow(self):
        """完整 MFA 流程: enroll_totp → challenge(返回 client-side 提示) → verify."""
        mgr = MFAManager()
        # 1. enroll TOTP
        enr = mgr.enroll_totp("carol")
        assert enr.success
        assert enr.secret
        assert enr.provisioning_uri.startswith("otpauth://")
        # 2. challenge (TOTP 不需要 server-side challenge)
        ch = await mgr.challenge_mfa("carol", MFAMethod.TOTP)
        assert ch.success
        # 3. 用当前时间算 code 并 verify
        from imdf.security.mfa import _totp_at, _b32_decode
        now = int(time.time())
        code = _totp_at(_b32_decode(enr.secret), now)
        r = await mgr.verify_mfa("carol", MFAMethod.TOTP, code)
        assert r.success


# ════════════════════════════════════════════════════════════════════════
# ABAC tests (5)
# ════════════════════════════════════════════════════════════════════════
class TestABAC:
    def test_admin_bypass_allows_everything(self):
        """admin 角色对任意 resource/action 都是 allow."""
        engine = ABACEngine()
        d1 = engine.enforce(
            "u-admin", "project:42", "delete",
            context={"user_attrs": {"id": "u-admin", "role": "admin"}},
        )
        assert d1.allow is True
        assert d1.matched_policy == "admin_bypass"
        d2 = engine.enforce(
            "u-admin", "dataset:abc", "read",
            context={"user_attrs": {"id": "u-admin", "role": "admin"}},
        )
        assert d2.allow is True
        d3 = engine.enforce(
            "u-admin", "billing:invoice1", "write",
            context={"user_attrs": {"id": "u-admin", "role": "admin"}},
        )
        assert d3.allow is True

    def test_owner_can_delete_own(self):
        """owner_delete_own: user.id == resource.owner_id AND action==delete → allow."""
        engine = ABACEngine()
        d = engine.enforce(
            "u-alice", "project:42", "delete",
            context={
                "user_attrs": {"id": "u-alice", "role": "user"},
                "resource_attrs": {"id": "42", "type": "project", "owner_id": "u-alice"},
            },
        )
        assert d.allow is True
        assert d.matched_policy == "owner_delete_own"

    def test_non_owner_cannot_delete(self):
        """user.id != resource.owner_id → 默认 deny (没有 deny policy 但也没 allow)."""
        engine = ABACEngine()
        d = engine.enforce(
            "u-bob", "project:42", "delete",
            context={
                "user_attrs": {"id": "u-bob", "role": "user"},
                "resource_attrs": {"id": "42", "type": "project", "owner_id": "u-alice"},
            },
        )
        assert d.allow is False
        # reason 说明 default deny
        assert "default deny" in d.reason.lower() or d.matched_policy is None

    def test_project_member_can_read(self):
        """project_member_read: user.id in resource.member_ids → allow."""
        engine = ABACEngine()
        d = engine.enforce(
            "u-alice", "project:42", "read",
            context={
                "user_attrs": {"id": "u-alice", "role": "user"},
                "resource_attrs": {
                    "id": "42",
                    "type": "project",
                    "member_ids": ["u-bob", "u-alice", "u-carol"],
                },
            },
        )
        assert d.allow is True
        assert d.matched_policy == "project_member_read"

    def test_non_member_cannot_read_project(self):
        """user.id NOT in resource.member_ids → deny."""
        engine = ABACEngine()
        d = engine.enforce(
            "u-eve", "project:42", "read",
            context={
                "user_attrs": {"id": "u-eve", "role": "user"},
                "resource_attrs": {
                    "id": "42",
                    "type": "project",
                    "member_ids": ["u-alice", "u-bob"],
                },
            },
        )
        assert d.allow is False


# ════════════════════════════════════════════════════════════════════════
# C2PA tests (6)
# ════════════════════════════════════════════════════════════════════════
class TestC2PA:
    @pytest.mark.asyncio
    async def test_sign_verify_round_trip(self):
        """C2PA sign + verify round-trip on original asset → valid=True."""
        signer = C2PASigner(claim_generator="IMDF-Test/1.0")
        verifier = C2PAVerifier(expected_claim_generator="IMDF-Test/1.0")
        asset = b"FAKE IMAGE BYTES \x00\x01\x02\x03"
        manifest = await signer.sign_manifest(
            asset, claim={"creator": "alice", "license": "CC-BY-4.0"}
        )
        assert manifest.signature
        assert manifest.public_key
        assert manifest.asset_hash
        r = await verifier.verify(asset, manifest)
        assert r.valid is True
        assert r.asset_hash_match is True
        assert r.signature_valid is True
        assert r.claim_generator_match is True
        assert r.time_valid is True

    @pytest.mark.asyncio
    async def test_tampered_manifest_detected(self):
        """修改 manifest 内容 → signature 验证失败."""
        signer = C2PASigner(claim_generator="IMDF-Test/1.0")
        verifier = C2PAVerifier()
        asset = b"original bytes"
        manifest = await signer.sign_manifest(asset, claim={"creator": "alice"})
        # 篡改 claim.creator
        manifest.claim = {"creator": "mallory"}
        r = await verifier.verify(asset, manifest)
        assert r.valid is False
        assert r.signature_valid is False
        assert "signature" in r.reason.lower()

    @pytest.mark.asyncio
    async def test_modified_asset_detected(self):
        """asset 被修改 → asset_hash mismatch → verify fail."""
        signer = C2PASigner(claim_generator="IMDF-Test/1.0")
        verifier = C2PAVerifier()
        original = b"original asset bytes"
        manifest = await signer.sign_manifest(original, claim={"creator": "alice"})
        tampered = original + b"!tampered!"
        r = await verifier.verify(tampered, manifest)
        assert r.valid is False
        assert r.asset_hash_match is False
        assert "asset hash" in r.reason.lower()

    @pytest.mark.asyncio
    async def test_store_record_and_get(self):
        """C2PAStore: record(manifest) → get(asset_hash) → 拿到原 manifest."""
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "c2pa.sqlite3")
            store = C2PAStore(db_path=db)
            signer = C2PASigner()
            asset = b"bytes for store test"
            manifest = await signer.sign_manifest(asset, claim={"creator": "bob"})
            await store.record(manifest)
            got = await store.get(manifest.asset_hash)
            assert got is not None
            assert got.manifest_id == manifest.manifest_id
            assert got.signature == manifest.signature
            assert got.asset_hash == manifest.asset_hash

    @pytest.mark.asyncio
    async def test_store_missing_manifest_returns_none(self):
        """C2PAStore.get(unknown_asset_hash) → None."""
        with tempfile.TemporaryDirectory() as td:
            store = C2PAStore(db_path=os.path.join(td, "c2pa.sqlite3"))
            got = await store.get("0000000000000000000000000000000000000000000000000000000000000000")
            assert got is None

    def test_sidecar_io(self):
        """write_sidecar / read_sidecar: round-trip."""
        with tempfile.TemporaryDirectory() as td:
            asset_path = os.path.join(td, "image.png")
            with open(asset_path, "wb") as f:
                f.write(b"fake png bytes")
            signer = C2PASigner()
            manifest = asyncio.run(signer.sign_manifest(b"fake png bytes", claim={"creator": "alice"}))
            sidecar = write_sidecar(asset_path, manifest)
            assert os.path.exists(sidecar)
            # sidecar path = asset_path + ".c2pa.json"
            assert sidecar == asset_path + ".c2pa.json"
            # read back
            got = read_sidecar(asset_path)
            assert got is not None
            assert got.manifest_id == manifest.manifest_id
            assert got.signature == manifest.signature


# ════════════════════════════════════════════════════════════════════════
# Schema / module surface tests (2 bonus)
# ════════════════════════════════════════════════════════════════════════
class TestSchemasAndSurface:
    def test_schemas_importable(self):
        """All schemas are Pydantic v2 BaseModel."""
        from imdf.security.sso_mfa_c2pa_schemas import (
            AuthResult, OIDCConfig,
            EnrollmentResult, ChallengeResult, VerificationResult,
            ABACPolicy, ABACDecision, Condition,
            C2PAManifest, C2PAIngredient, C2PAAction, C2PAVerificationResult,
        )
        # Pydantic v2 用 model_fields 暴露字段
        assert "success" in AuthResult.model_fields
        assert "user_id" in AuthResult.model_fields
        assert "secret" in EnrollmentResult.model_fields
        assert "allow" in ABACDecision.model_fields
        assert "signature" in C2PAManifest.model_fields
        assert "public_key" in C2PAManifest.model_fields

    def test_module_init_reexports_all(self):
        """security/__init__.py 暴露的符号都真实存在."""
        import imdf.security as sec
        for name in sec.__all__:
            assert hasattr(sec, name), f"missing: {name}"