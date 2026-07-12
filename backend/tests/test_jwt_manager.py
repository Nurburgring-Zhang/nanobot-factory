"""
P10-C: JWT 2 P0 修复 单元测试
=============================
覆盖:
1. JWTManager(secret="x") / 短 secret 拒绝 (ValueError)
2. JWTManager 签发的 access / refresh token 含 iss / aud / jti 标准声明
3. 连续签发两个 token → jti 必须唯一 (RFC 7519 §4.1.7 全局唯一性)

RFC 7519 参考:
- §4.1.1  "iss" (Issuer)
- §4.1.3  "aud" (Audience)
- §4.1.7  "jti" (JWT ID) — 提供唯一性, 用于防重放

对应 OWASP A02:2021 (Cryptographic Failures) — secret 强度校验。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ── 让 ``backend/`` 包可 import ─────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
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
from security.auth import Permission  # noqa: E402

import jwt as pyjwt  # noqa: E402  (PyJWT 用于解码验证 payload)


# ── 测试 1: 短 secret 拒绝 (P10-C-1) ───────────────────────────────────────
class TestJWTSecretLengthRejection:
    """P10-C-1: JWTManager 启动时拒绝 < 16 字符 secret (与 AuditChain 一致)."""

    @pytest.mark.parametrize(
        "short_secret",
        [
            "",           # 空字符串
            "x",          # 1 字符 (任务原例)
            "short",      # 5 字符
            "1234567890", # 10 字符
            "fifteen-char",  # 13 字符 (边界)
        ],
    )
    def test_unified_jwt_rejects_short_secret(self, short_secret):
        """unified_auth.JWTManager: 短 secret 必须 raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            UnifiedJWTManager(secret_key=short_secret)
        # 错误消息要明确说明长度要求 (空字符串走另一分支, 但仍是 secret 错误)
        assert "secret" in str(exc_info.value).lower()
        # 长度分支错误消息必须含阈值数字
        if short_secret:  # 非空短 secret → 走长度分支
            assert str(JWT_MIN_SECRET_LENGTH) in str(exc_info.value)

    @pytest.mark.parametrize(
        "short_secret",
        ["", "x", "short", "fifteen-char"],
    )
    def test_legacy_jwt_rejects_short_secret(self, short_secret):
        """security.auth.JWTManager: 短 secret 必须 raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            LegacyJWTManager(secret_key=short_secret)
        assert "secret" in str(exc_info.value).lower()
        if short_secret:
            assert str(JWT_MIN_SECRET_LENGTH) in str(exc_info.value)

    def test_unified_jwt_rejects_non_string_secret(self):
        """非字符串 secret 也必须拒绝 (避免 bytes 被错误地编码)."""
        with pytest.raises(ValueError):
            UnifiedJWTManager(secret_key=None)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            UnifiedJWTManager(secret_key=12345)  # type: ignore[arg-type]

    def test_unified_jwt_accepts_exact_min_length(self):
        """恰好 16 字符的 secret 应当接受 (边界正向)."""
        mgr = UnifiedJWTManager(secret_key="a" * JWT_MIN_SECRET_LENGTH)
        assert mgr.secret_key == "a" * JWT_MIN_SECRET_LENGTH

    def test_unified_jwt_accepts_long_random_secret(self):
        """典型生产场景: 64 字符随机 secret 接受."""
        import secrets
        mgr = UnifiedJWTManager(secret_key=secrets.token_urlsafe(64))
        assert len(mgr.secret_key) > JWT_MIN_SECRET_LENGTH

    def test_legacy_jwt_accepts_long_random_secret(self):
        """Legacy 系统: 长随机 secret 接受."""
        import secrets
        secret = secrets.token_urlsafe(64)
        mgr = LegacyJWTManager(secret_key=secret)
        assert mgr.secret_key == secret


# ── 测试 2: iss / aud / jti 标准声明存在 (P10-C-2) ─────────────────────────
class TestJWTStandardClaims:
    """P10-C-2: 签发的 JWT 必须含 iss / aud / jti (RFC 7519)."""

    SECRET = "test-secret-32-chars-long-aaaa"  # 31 chars, >= 16

    def _decode_unverified(self, token: str) -> dict:
        """不验签解码, 拿到 payload 用于断言标准声明."""
        return pyjwt.decode(token, options={"verify_signature": False})

    def test_access_token_has_iss_aud_jti_unified(self):
        """unified_auth.JWTManager.create_access_token 必须含 3 标准声明."""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        token = mgr.create_access_token(
            user_id="u-123", username="alice", role="viewer",
            permissions=["user:read"],
        )
        payload = self._decode_unverified(token)

        # RFC 7519 §4.1.1 — Issuer
        assert payload.get("iss") == JWT_ISSUER
        assert payload["iss"] == "nanobot-factory"

        # RFC 7519 §4.1.3 — Audience
        assert payload.get("aud") == JWT_AUDIENCE
        assert payload["aud"] == "nanobot-factory-api"

        # RFC 7519 §4.1.7 — JWT ID
        assert "jti" in payload
        assert isinstance(payload["jti"], str)
        assert len(payload["jti"]) >= 16  # uuid4().hex = 32 chars

    def test_refresh_token_has_iss_aud_jti_unified(self):
        """unified_auth.JWTManager.create_refresh_token 也必须含 3 标准声明."""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        token = mgr.create_refresh_token(user_id="u-123")
        payload = self._decode_unverified(token)

        assert payload.get("iss") == JWT_ISSUER
        assert payload.get("aud") == JWT_AUDIENCE
        assert "jti" in payload and len(payload["jti"]) >= 16

    def test_access_token_has_iss_aud_jti_legacy(self):
        """security.auth.JWTManager.create_token 也必须含 3 标准声明."""
        mgr = LegacyJWTManager(secret_key=self.SECRET)
        token = mgr.create_token(user_id="u-123", permissions=[Permission.USER_READ])
        payload = self._decode_unverified(token)

        assert payload.get("iss") == JWT_ISSUER
        assert payload.get("aud") == JWT_AUDIENCE
        assert "jti" in payload and len(payload["jti"]) >= 16

    def test_backwards_compat_verify_still_works(self):
        """verify_token / verify 仍可解码新签发的 token (向后兼容).

        不强制 iss/aud 校验, 仅解码 + 类型校验。
        旧 token (无 iss/aud) 也能解码 (P10-C 不破坏现有 refresh 流程)。
        """
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        token = mgr.create_access_token(
            user_id="u-123", username="alice", role="viewer",
        )
        payload = mgr.verify_token(token, token_type="access")
        assert payload is not None
        assert payload["sub"] == "u-123"
        assert payload["type"] == "access"
        # 新字段也在
        assert payload["iss"] == JWT_ISSUER
        assert payload["aud"] == JWT_AUDIENCE

    def test_verify_token_type_mismatch(self):
        """access token 当 refresh 用 → verify 返回 None (类型守卫保留)."""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        access = mgr.create_access_token(user_id="u-1", username="x", role="viewer")
        # 用 access token 调 verify_token(type="refresh") → 应返回 None
        assert mgr.verify_token(access, token_type="refresh") is None


# ── 测试 3: jti 全局唯一 (RFC 7519 §4.1.7) ────────────────────────────────
class TestJTIUniqueness:
    """P10-C-2 验证: jti 在每次签发时必须唯一 (用于黑名单 / 防重放)."""

    SECRET = "test-secret-32-chars-long-bbbb"  # 31 chars, >= 16

    def _decode_unverified(self, token: str) -> dict:
        return pyjwt.decode(token, options={"verify_signature": False})

    def test_jti_unique_across_access_tokens(self):
        """unified_auth: 连签 100 个 access token → 100 个 jti 必须互不相同."""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        jtis = set()
        for _ in range(100):
            token = mgr.create_access_token(
                user_id="u-1", username="alice", role="viewer",
            )
            payload = self._decode_unverified(token)
            jti = payload["jti"]
            assert jti not in jtis, f"Duplicate jti detected: {jti}"
            jtis.add(jti)
        assert len(jtis) == 100

    def test_jti_unique_across_refresh_tokens(self):
        """unified_auth: 连签 50 个 refresh token → 50 个 jti 必须互不相同."""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        jtis = set()
        for _ in range(50):
            token = mgr.create_refresh_token(user_id="u-1")
            payload = self._decode_unverified(token)
            jti = payload["jti"]
            assert jti not in jtis
            jtis.add(jti)
        assert len(jtis) == 50

    def test_jti_unique_mixed_access_refresh(self):
        """unified_auth: 混合 access + refresh → jti 仍全局唯一."""
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        jtis = set()
        for i in range(40):
            if i % 2 == 0:
                token = mgr.create_access_token(user_id="u-1", username="x", role="viewer")
            else:
                token = mgr.create_refresh_token(user_id="u-1")
            payload = self._decode_unverified(token)
            jtis.add(payload["jti"])
        assert len(jtis) == 40  # 全部唯一

    def test_jti_unique_legacy(self):
        """security.auth.JWTManager: jti 同样必须唯一."""
        mgr = LegacyJWTManager(secret_key=self.SECRET)
        jtis = set()
        for _ in range(100):
            token = mgr.create_token(user_id="u-1", permissions=[Permission.USER_READ])
            payload = self._decode_unverified(token)
            jti = payload["jti"]
            assert jti not in jtis, f"Duplicate jti (legacy): {jti}"
            jtis.add(jti)
        assert len(jtis) == 100

    def test_jti_is_uuid4_hex_format(self):
        """jti 应当是 uuid4().hex 格式 (32 个十六进制字符)."""
        import re
        mgr = UnifiedJWTManager(secret_key=self.SECRET)
        token = mgr.create_access_token(user_id="u-1", username="x", role="viewer")
        payload = self._decode_unverified(token)
        jti = payload["jti"]
        # uuid4().hex = 32 个 hex chars
        assert re.fullmatch(r"[0-9a-f]{32}", jti), f"jti '{jti}' is not uuid4().hex format"