"""
P11-B: JWTManager.verify() 强制校验 iss/aud 单元测试
=====================================================
覆盖:
1. unified_auth.JWTManager.verify_token() 强制校验 iss/aud (P11-B-2)
2. security.auth.JWTManager.verify_token() 强制校验 iss/aud
3. common/auth._decode_token() 强制校验 iss/aud (FastAPI 路径)
4. 不同 issuer / audience 的伪造 token 一律拒绝 (RFC 7519 §4.1.1 / §4.1.3)

RFC 7519 参考:
  - §4.1.1  "iss" (Issuer) — 签发方身份, 必须等于 JWT_ISSUER
  - §4.1.3  "aud" (Audience) — 受众身份, 必须等于 JWT_AUDIENCE
  - §4.1.7  "jti" (JWT ID) — 防重放

对应 OWASP A02:2021 (Cryptographic Failures) + A07 (Auth Failures)。
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import pytest

# ── 让 ``backend/`` 包可 import ─────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent.parent  # backend/auth/tests/.. → backend
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ── 被测对象 ────────────────────────────────────────────────────────────────
from auth.unified_auth import JWTManager as UnifiedJWTManager  # noqa: E402
from auth.unified_auth import (  # noqa: E402
    JWT_ISSUER,
    JWT_AUDIENCE,
    JWT_MIN_SECRET_LENGTH,
)
from security.auth import JWTManager as LegacyJWTManager  # noqa: E402


# ── 测试 1: unified_auth.JWTManager.verify_token enforce iss/aud ────────────
class TestUnifiedJWTEnforcesIssAud:
    """P11-B-2: unified_auth.JWTManager.verify_token 必须 enforce iss + aud。"""

    SECRET = "test-secret-unified-enforce-aaaa"  # 31 chars >= 16

    # ---- 1.1 正向: 正确签发的 token 必须通过验证 ----

    def test_verify_accepts_correct_iss_aud(self):
        """正确签发 → verify_token 返回完整 payload."""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        token = mgr.create_access_token(
            user_id="u-1", username="alice", role="viewer",
        )
        payload = mgr.verify_token(token, token_type="access")
        assert payload is not None
        assert payload["iss"] == JWT_ISSUER
        assert payload["aud"] == JWT_AUDIENCE
        assert payload["sub"] == "u-1"

    def test_verify_accepts_refresh_token_correct_iss_aud(self):
        """refresh token 同样 enforce."""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        token = mgr.create_refresh_token(user_id="u-2")
        payload = mgr.verify_token(token, token_type="refresh")
        assert payload is not None
        assert payload["iss"] == JWT_ISSUER
        assert payload["aud"] == JWT_AUDIENCE

    # ---- 1.2 反向: 错误 iss/aud 必须拒绝 ----

    def test_verify_rejects_wrong_issuer(self):
        """iss 不匹配 → verify_token 返回 None (InvalidTokenError → None)。"""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        bogus = self._make_token_with(
            issuer="evil-corp",
            audience=JWT_AUDIENCE,
        )
        assert mgr.verify_token(bogus, token_type="access") is None

    def test_verify_rejects_wrong_audience(self):
        """aud 不匹配 → verify_token 返回 None。"""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        bogus = self._make_token_with(
            issuer=JWT_ISSUER,
            audience="some-other-api",
        )
        assert mgr.verify_token(bogus, token_type="access") is None

    def test_verify_rejects_missing_iss(self):
        """iss 缺失 → None。"""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        bogus = self._make_token_with(
            issuer=None,
            audience=JWT_AUDIENCE,
        )
        assert mgr.verify_token(bogus, token_type="access") is None

    def test_verify_rejects_missing_aud(self):
        """aud 缺失 → None。"""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        bogus = self._make_token_with(
            issuer=JWT_ISSUER,
            audience=None,
        )
        assert mgr.verify_token(bogus, token_type="access") is None

    def test_verify_rejects_completely_wrong_iss_and_aud(self):
        """iss + aud 都错 → None."""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        bogus = self._make_token_with(
            issuer="attacker.example.com",
            audience="victim-api",
        )
        assert mgr.verify_token(bogus, token_type="access") is None

    # ---- 1.3 helper ----

    @staticmethod
    def _make_token_with(issuer, audience, *, user_id="u-test"):
        """用同 secret 但自定义 iss/aud 签发 token (PyJWT)。"""
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        payload = {
            "sub": user_id,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(seconds=60),
        }
        if issuer is not None:
            payload["iss"] = issuer
        if audience is not None:
            payload["aud"] = audience
        return pyjwt.encode(
            payload,
            TestUnifiedJWTEnforcesIssAud.SECRET,
            algorithm="HS256",
        )


# ── 测试 2: security.auth.JWTManager.verify_token enforce iss/aud ───────────
class TestLegacyJWTEnforcesIssAud:
    """P11-B-2: security.auth.JWTManager.verify_token 必须 enforce iss + aud."""

    SECRET = "test-secret-legacy-enforce-bbbbb"  # 30 chars >= 16

    def test_legacy_verify_accepts_correct_iss_aud(self):
        """Legacy JWTManager 签发的 token → verify_token 接受。"""
        mgr = LegacyJWTManager(secret_key=self.SECRET)
        from security.auth import Permission

        token = mgr.create_token(user_id="u-1", permissions=[Permission.USER_READ])
        payload = mgr.verify_token(token)
        assert payload is not None
        assert payload["iss"] == JWT_ISSUER
        assert payload["aud"] == JWT_AUDIENCE

    def test_legacy_verify_rejects_wrong_issuer(self):
        """Legacy: 错 iss → None。"""
        mgr = LegacyJWTManager(secret_key=self.SECRET)
        bogus = self._make_token_with(
            issuer="forged-issuer",
            audience=JWT_AUDIENCE,
        )
        assert mgr.verify_token(bogus) is None

    def test_legacy_verify_rejects_wrong_audience(self):
        """Legacy: 错 aud → None。"""
        mgr = LegacyJWTManager(secret_key=self.SECRET)
        bogus = self._make_token_with(
            issuer=JWT_ISSUER,
            audience="wrong-aud",
        )
        assert mgr.verify_token(bogus) is None

    def test_legacy_verify_rejects_missing_iss(self):
        """Legacy: 缺 iss → None。"""
        mgr = LegacyJWTManager(secret_key=self.SECRET)
        bogus = self._make_token_with(issuer=None, audience=JWT_AUDIENCE)
        assert mgr.verify_token(bogus) is None

    def test_legacy_verify_rejects_missing_aud(self):
        """Legacy: 缺 aud → None。"""
        mgr = LegacyJWTManager(secret_key=self.SECRET)
        bogus = self._make_token_with(issuer=JWT_ISSUER, audience=None)
        assert mgr.verify_token(bogus) is None

    @staticmethod
    def _make_token_with(issuer, audience, *, user_id="u-test"):
        """用同 secret 但自定义 iss/aud 签发 token (PyJWT)。"""
        import jwt as pyjwt
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        payload = {
            "user_id": user_id,
            "permissions": [],
            "iat": now,
            "exp": now + timedelta(seconds=60),
        }
        if issuer is not None:
            payload["iss"] = issuer
        if audience is not None:
            payload["aud"] = audience
        return pyjwt.encode(
            payload,
            TestLegacyJWTEnforcesIssAud.SECRET,
            algorithm="HS256",
        )


# ── 测试 3: common/auth._decode_token() enforce iss/aud (FastAPI 路径) ─────
class TestCommonAuthDecodeEnforcesIssAud:
    """P11-B-2: common.auth._decode_token() 必须 enforce iss + aud (jose.jwt)。"""

    @pytest.fixture(autouse=True)
    def _set_strong_secret(self, monkeypatch):
        """给 common.auth 注入 64 字符 secret, 让 _secret() 不 raise。"""
        monkeypatch.setenv("JWT_SECRET", "x" * 64)

    def test_decode_accepts_correct_iss_aud(self, monkeypatch):
        """正确 token → 解码成功."""
        from common.auth import issue_access_token, _decode_token

        token = issue_access_token(username="alice", role="viewer")
        payload = _decode_token(token)
        assert payload["iss"] == JWT_ISSUER
        assert payload["aud"] == JWT_AUDIENCE
        assert payload["sub"] == "alice"

    def test_decode_rejects_wrong_issuer(self, monkeypatch):
        """错 iss → HTTPException(401)。"""
        from fastapi import HTTPException
        from jose import jwt as jose_jwt
        from common.auth import _decode_token

        bogus = self._make_jose_token(
            issuer="malicious-issuer",
            audience=JWT_AUDIENCE,
        )
        with pytest.raises(HTTPException) as exc_info:
            _decode_token(bogus)
        assert exc_info.value.status_code == 401

    def test_decode_rejects_wrong_audience(self, monkeypatch):
        """错 aud → HTTPException(401)。"""
        from fastapi import HTTPException
        from jose import jwt as jose_jwt
        from common.auth import _decode_token

        bogus = self._make_jose_token(
            issuer=JWT_ISSUER,
            audience="unauthorized-api",
        )
        with pytest.raises(HTTPException) as exc_info:
            _decode_token(bogus)
        assert exc_info.value.status_code == 401

    def test_decode_rejects_missing_iss(self, monkeypatch):
        """缺 iss → 401。"""
        from fastapi import HTTPException
        from common.auth import _decode_token

        bogus = self._make_jose_token(issuer=None, audience=JWT_AUDIENCE)
        with pytest.raises(HTTPException):
            _decode_token(bogus)

    def test_decode_rejects_missing_aud(self, monkeypatch):
        """缺 aud → 401。"""
        from fastapi import HTTPException
        from common.auth import _decode_token

        bogus = self._make_jose_token(issuer=JWT_ISSUER, audience=None)
        with pytest.raises(HTTPException):
            _decode_token(bogus)

    @staticmethod
    def _make_jose_token(issuer, audience, *, sub="u-test"):
        """用 jose.jwt 自签 token (python-jose 与 common.auth 同 lib)。"""
        from jose import jwt as jose_jwt

        payload = {
            "sub": sub,
            "type": "access",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "jti": uuid.uuid4().hex,
        }
        if issuer is not None:
            payload["iss"] = issuer
        if audience is not None:
            payload["aud"] = audience
        return jose_jwt.encode(payload, "x" * 64, algorithm="HS256")


# ── 测试 4: 跨系统综合 - 强 secret + 正确 iss/aud 的端到端 round-trip ──────
class TestEndToEndRoundTrip:
    """统一端到端: issue → decode → iss/aud 全链路一致."""

    def test_unified_issue_then_unified_verify(self):
        """unified_auth: 自己签 + 自己 verify."""
        import secrets

        mgr = UnifiedJWTManager(secret_key=secrets.token_urlsafe(64))
        token = mgr.create_access_token(
            user_id="u-roundtrip", username="rt", role="admin",
            permissions=["user:create"],
        )
        payload = mgr.verify_token(token, token_type="access")
        assert payload is not None
        assert payload["iss"] == "nanobot-factory"
        assert payload["aud"] == "nanobot-factory-api"
        assert payload["sub"] == "u-roundtrip"
        assert payload["username"] == "rt"
        assert payload["role"] == "admin"
        assert "user:create" in payload["permissions"]

    def test_legacy_issue_then_legacy_verify(self):
        """security.auth: 自己签 + 自己 verify。"""
        import secrets
        from security.auth import Permission

        mgr = LegacyJWTManager(secret_key=secrets.token_urlsafe(64))
        token = mgr.create_token(
            user_id="u-rt2",
            permissions=[Permission.USER_READ, Permission.TOOL_EXECUTE],
        )
        payload = mgr.verify_token(token)
        assert payload is not None
        assert payload["iss"] == "nanobot-factory"
        assert payload["aud"] == "nanobot-factory-api"
        assert payload["user_id"] == "u-rt2"
