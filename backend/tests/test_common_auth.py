"""
P11-B: common/auth.py 单元测试
================================
覆盖:
1. _secret() / _decode_token() / issue_access_token() 启动时拒绝 < 16 字符 secret
   (P11-B-1: silent warning → raise ValueError, fail-fast)
2. _decode_token() 强制校验 iss/aud (P11-B-2)
3. issue_access_token() 写入 RFC 7519 标准声明
4. require_role_dep() / get_current_user() FastAPI 依赖装配

RFC 7519 引用:
  - §4.1.1  "iss" (Issuer)
  - §4.1.3  "aud" (Audience)
  - §4.1.7  "jti" (JWT ID)

对应 OWASP A02:2021 (Cryptographic Failures) — secret 强度 + iss/aud 校验。
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


# ── Fixtures: 清空 env + 强 secret, 防止其他测试的 env 泄漏 ──────────────────
@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """每个 test 前清空 JWT_SECRET / JWT_ALGORITHM, 让 _secret() 走 test-mode 路径。

    common/auth._secret() 的解析顺序:
      1. JWT_SECRET env
      2. imdf.config.settings.SECRET_KEY (若有)
      3. IMDF_TEST_MODE=1 → "test-secret-common-lib"  (隐含)

    我们强制走 #3 + 强 secret, 避免每个 test 写 monkeypatch.setenv。
    """
    # 清掉任何预先设置的 JWT_SECRET (避免 TestClient 启动时从别处继承)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    # 设一个 64 字符强 secret (>= 16 字符最小值)
    monkeypatch.setenv("JWT_SECRET", "x" * 64)
    # 启用 IMDF_TEST_MODE, 让 _load_test_users 接受任何用户名 (FastAPI 测试用)
    monkeypatch.setenv("IMDF_TEST_MODE", "1")
    yield


# ── 测试 1: _secret() 拒绝短 secret (P11-B-1) ───────────────────────────────
class TestCommonAuthSecretValidation:
    """P11-B-1: _secret() 在 secret < 16 字符时必须 raise ValueError (而非 silent warning)。"""

    @pytest.mark.parametrize(
        "short_secret",
        [
            "x",            # 1 字符 (P10-C 任务原例)
            "short",        # 5 字符
            "1234567890",   # 10 字符
            "fifteen-char", # 13 字符 (边界)
            # 注: 空字符串 "" 会触发 _secret() 的 IMDF_TEST_MODE fallback
            # ("test-secret-common-lib"), 不会 raise — 单独测在下面。
        ],
    )
    def test_secret_raises_on_short_value(self, monkeypatch, short_secret):
        """直接传短 secret (绕过 env) → raise ValueError, fail-fast."""
        # 跳过 autouse fixture, 自己手动控制
        monkeypatch.setenv("JWT_SECRET", short_secret)
        # 必须重新导入以触发 module-level 计算 (但 _secret() 是 function, 每次调用重算)
        from common.auth import _secret, JWT_MIN_SECRET_LENGTH

        with pytest.raises(ValueError) as exc_info:
            _secret()
        msg = str(exc_info.value)
        # 错误消息明确说明长度阈值
        assert str(JWT_MIN_SECRET_LENGTH) in msg, f"错误消息缺少阈值: {msg}"
        assert "JWT_SECRET" in msg or "secret" in msg.lower()

    def test_secret_raises_on_explicitly_short_env(self, monkeypatch):
        """通过 env 设置 1 字符 secret → raise ValueError."""
        monkeypatch.setenv("JWT_SECRET", "x")
        from common.auth import _secret

        with pytest.raises(ValueError) as exc_info:
            _secret()
        assert "16" in str(exc_info.value) or "min" in str(exc_info.value).lower()

    def test_empty_secret_without_test_mode_raises(self, monkeypatch):
        """空 secret + 关闭 IMDF_TEST_MODE → raise ValueError (不是返回 fallback).

        这是 P11-B-1 的关键 fail-fast 行为: 部署时如果忘记设 JWT_SECRET
        且没开 test mode, 启动会直接崩, 而不是用 "test-secret-common-lib"
        这种弱默认值静默通过。
        """
        monkeypatch.setenv("JWT_SECRET", "")
        monkeypatch.delenv("IMDF_TEST_MODE", raising=False)
        from common.auth import _secret

        with pytest.raises(ValueError):
            _secret()

    def test_secret_accepts_exact_min_length(self, monkeypatch):
        """恰好 16 字符 secret → 通过 (边界正向)。"""
        monkeypatch.setenv("JWT_SECRET", "a" * 16)
        from common.auth import _secret, JWT_MIN_SECRET_LENGTH

        sec = _secret()
        assert sec == "a" * 16
        assert len(sec) >= JWT_MIN_SECRET_LENGTH

    def test_secret_accepts_long_random_secret(self, monkeypatch):
        """64 字符随机 secret → 通过 (生产场景)。"""
        import secrets

        secret = secrets.token_urlsafe(64)
        monkeypatch.setenv("JWT_SECRET", secret)
        from common.auth import _secret

        sec = _secret()
        assert sec == secret
        assert len(sec) >= 16


# ── 测试 2: _decode_token() 强制 iss/aud 校验 (P11-B-2) ─────────────────────
class TestCommonAuthDecodeEnforcesClaims:
    """P11-B-2: _decode_token() 必须 enforce iss/aud (RFC 7519 §4.1.1 / §4.1.3)。"""

    def test_decode_token_accepts_well_formed_token(self, monkeypatch):
        """正确签发的 token (iss + aud + jti + exp + iat) → 解码成功."""
        monkeypatch.setenv("JWT_SECRET", "x" * 64)
        from common.auth import _decode_token, issue_access_token, JWT_ISSUER, JWT_AUDIENCE

        token = issue_access_token(username="alice", role="viewer")
        payload = _decode_token(token)
        assert payload["sub"] == "alice"
        assert payload["role"] == "viewer"
        assert payload["iss"] == JWT_ISSUER
        assert payload["aud"] == JWT_AUDIENCE

    def test_decode_token_rejects_wrong_issuer(self, monkeypatch):
        """伪造的 iss → _decode_token raise HTTPException(401)."""
        from fastapi import HTTPException
        import time
        import uuid
        from jose import jwt as jose_jwt

        monkeypatch.setenv("JWT_SECRET", "x" * 64)
        # 用强 secret 自己签一个 wrong-iss token
        bogus = jose_jwt.encode(
            {
                "sub": "alice",
                "iss": "evil-corp",       # 错的 iss
                "aud": "nanobot-factory-api",
                "jti": uuid.uuid4().hex,
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "type": "access",
            },
            "x" * 64,
            algorithm="HS256",
        )
        from common.auth import _decode_token

        with pytest.raises(HTTPException) as exc_info:
            _decode_token(bogus)
        assert exc_info.value.status_code == 401

    def test_decode_token_rejects_wrong_audience(self, monkeypatch):
        """伪造的 aud → _decode_token raise HTTPException(401)."""
        from fastapi import HTTPException
        import time
        import uuid
        from jose import jwt as jose_jwt

        monkeypatch.setenv("JWT_SECRET", "x" * 64)
        bogus = jose_jwt.encode(
            {
                "sub": "alice",
                "iss": "nanobot-factory",
                "aud": "some-other-api",  # 错的 aud
                "jti": uuid.uuid4().hex,
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "type": "access",
            },
            "x" * 64,
            algorithm="HS256",
        )
        from common.auth import _decode_token

        with pytest.raises(HTTPException) as exc_info:
            _decode_token(bogus)
        assert exc_info.value.status_code == 401

    def test_decode_token_rejects_missing_iss(self, monkeypatch):
        """缺少 iss 声明的 token → 401."""
        from fastapi import HTTPException
        import time
        import uuid
        from jose import jwt as jose_jwt

        monkeypatch.setenv("JWT_SECRET", "x" * 64)
        bogus = jose_jwt.encode(
            {
                "sub": "alice",
                # iss 缺失
                "aud": "nanobot-factory-api",
                "jti": uuid.uuid4().hex,
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
                "type": "access",
            },
            "x" * 64,
            algorithm="HS256",
        )
        from common.auth import _decode_token

        with pytest.raises(HTTPException):
            _decode_token(bogus)


# ── 测试 3: issue_access_token() 写入 RFC 7519 标准声明 ─────────────────────
class TestIssueAccessTokenClaims:
    """P11-B-2 验证: issue_access_token() 必须含 iss/aud/jti (RFC 7519)."""

    def test_token_contains_iss_aud_jti(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "x" * 64)
        from common.auth import issue_access_token, JWT_ISSUER, JWT_AUDIENCE
        from jose import jwt as jose_jwt

        token = issue_access_token(username="bob", role="admin")
        payload = jose_jwt.get_unverified_claims(token)

        # RFC 7519 §4.1.1 — Issuer
        assert payload["iss"] == JWT_ISSUER
        assert payload["iss"] == "nanobot-factory"

        # RFC 7519 §4.1.3 — Audience
        assert payload["aud"] == JWT_AUDIENCE
        assert payload["aud"] == "nanobot-factory-api"

        # RFC 7519 §4.1.7 — JWT ID
        assert "jti" in payload
        assert len(payload["jti"]) >= 16  # uuid4().hex = 32 chars

        # sub / role / type
        assert payload["sub"] == "bob"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_two_tokens_have_distinct_jti(self, monkeypatch):
        """连签 2 个 token → jti 必须不同 (RFC 7519 §4.1.7 全局唯一)."""
        monkeypatch.setenv("JWT_SECRET", "x" * 64)
        from common.auth import issue_access_token
        from jose import jwt as jose_jwt

        t1 = issue_access_token(username="x", role="viewer")
        t2 = issue_access_token(username="x", role="viewer")
        p1 = jose_jwt.get_unverified_claims(t1)
        p2 = jose_jwt.get_unverified_claims(t2)
        assert p1["jti"] != p2["jti"]


# ── 测试 4: get_current_user() / require_role_dep() 装配 ────────────────────
class TestGetCurrentUserDependency:
    """get_current_user() FastAPI Depends 行为 (X-User + IMDF_TEST_MODE 路径)."""

    def test_get_current_user_via_x_user(self, monkeypatch):
        """Test mode + X-User header → 返回 user dict (无 JWT)."""
        monkeypatch.setenv("IMDF_TEST_MODE", "1")
        monkeypatch.setenv("IMDF_TEST_USERS", '[{"username":"alice","role":"admin"}]')

        from common.auth import get_current_user

        # 直接调用 (FastAPI Depends 内部就是传 kwargs 进来)
        user = get_current_user(authorization=None, x_user="alice")
        assert user["username"] == "alice"
        assert user["role"] == "admin"
        assert user["enabled"] is True

    def test_get_current_user_requires_auth_or_test_mode(self, monkeypatch):
        """无 Authorization + 无 X-User → raise HTTPException(401)."""
        monkeypatch.delenv("IMDF_TEST_MODE", raising=False)
        from fastapi import HTTPException
        from common.auth import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(authorization=None, x_user=None)
        assert exc_info.value.status_code == 401

    def test_get_current_user_rejects_bad_scheme(self, monkeypatch):
        """Authorization: Basic xxx → 401 invalid_auth_scheme."""
        monkeypatch.delenv("IMDF_TEST_MODE", raising=False)
        from fastapi import HTTPException
        from common.auth import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(authorization="Basic dXNlcjpwYXNz", x_user=None)
        assert exc_info.value.status_code == 401
        assert "invalid_auth_scheme" in str(exc_info.value.detail)

    def test_require_role_dep_allows_admin(self, monkeypatch):
        """require_role_dep('admin') 对 admin user 返回 user dict."""
        monkeypatch.setenv("IMDF_TEST_MODE", "1")
        monkeypatch.setenv("IMDF_TEST_USERS", '[{"username":"root","role":"admin"}]')
        from common.auth import get_current_user, require_role_dep

        user = get_current_user(authorization=None, x_user="root")
        checker = require_role_dep("admin")
        result = checker(user=user)
        assert result["role"] == "admin"

    def test_require_role_dep_blocks_non_admin(self, monkeypatch):
        """require_role_dep('admin') 对 viewer user raise HTTPException(403)."""
        monkeypatch.setenv("IMDF_TEST_MODE", "1")
        monkeypatch.setenv("IMDF_TEST_USERS", '[{"username":"bob","role":"viewer"}]')
        from fastapi import HTTPException
        from common.auth import get_current_user, require_role_dep

        user = get_current_user(authorization=None, x_user="bob")
        checker = require_role_dep("admin")
        with pytest.raises(HTTPException) as exc_info:
            checker(user=user)
        assert exc_info.value.status_code == 403


# ── 测试 5: _load_test_users() 解析 ─────────────────────────────────────────
class TestLoadTestUsers:
    """_load_test_users() 解析 IMDF_TEST_USERS env JSON."""

    def test_empty_env_returns_empty(self, monkeypatch):
        monkeypatch.delenv("IMDF_TEST_USERS", raising=False)
        from common.auth import _load_test_users

        assert _load_test_users() == {}

    def test_valid_json_parses(self, monkeypatch):
        monkeypatch.setenv(
            "IMDF_TEST_USERS",
            '[{"username":"a","role":"admin"},{"username":"b","role":"viewer"}]',
        )
        from common.auth import _load_test_users

        users = _load_test_users()
        assert "a" in users and users["a"]["role"] == "admin"
        assert "b" in users and users["b"]["role"] == "viewer"
        # enabled 默认 True
        assert users["a"]["enabled"] is True

    def test_invalid_json_returns_empty(self, monkeypatch):
        monkeypatch.setenv("IMDF_TEST_USERS", "not-json{")
        from common.auth import _load_test_users

        assert _load_test_users() == {}
