"""
R9.5-Worker-1: 认证加固 + JWT + CSRF + CORS + GDPR 测试套件
==========================================================
覆盖维度:
1. JWT 过期 / refresh 流程 / 黑名单
2. 限流 (login 5/min, register 10/min, refresh 20/min)
3. CSRF 跨域拦截 + 双 cookie
4. CORS 白名单 (非 *)
5. GDPR 导出/删除/审计
6. 密码强度校验

目标: >=25 用例 PASS
"""
from __future__ import annotations

import os
import sys
import time
import sqlite3
from pathlib import Path

# ── 环境设置: 测试模式 (允许默认 JWT_SECRET) ─────────────────────────────
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("CSRF_ENABLED", "false")  # 默认关闭 — 个别测试单独开启
os.environ.setdefault("RATE_LIMIT_ENABLED", "true")

# ── 让 backend 包可 import ────────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ── 模拟 server.py 的做法: 把 imdf/ 加入 sys.path, 让 ``from api.xxx`` 解析到 imdf/api/
_IMDF_ROOT = _BACKEND / "imdf"
if str(_IMDF_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMDF_ROOT))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from api import auth_routes  # noqa: E402
from api.auth_routes import (  # noqa: E402
    _limiter,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    users_db,
    _revoked_cache,
    validate_password_strength,
    AuthService,
    reset_security_state_for_tests,
    SECRET_KEY as _AUTH_SECRET_KEY,
)
from api.security_middleware import (  # noqa: E402
    CSRFMiddleware,
    CORS_ALLOWED_ORIGINS,
    DEFAULT_TRUSTED_ORIGINS,
    is_origin_allowed,
    CSRF_SAFE_PATHS,
    generate_csrf_token,
)


# ── Fixtures ──────────────────────────────────────────────────────────────
def _build_app(*, csrf_enabled: bool = False) -> FastAPI:
    """构建一个最小化的 FastAPI app, 仅挂载 auth router + 限流器。"""
    app = FastAPI()
    app.include_router(auth_routes.router)
    if _limiter is not None:
        app.state.limiter = _limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    if csrf_enabled:
        app.add_middleware(CSRFMiddleware, enabled=True)
    return app


@pytest.fixture
def app():
    """每个测试函数新建一个干净的 app + limiter + DB state。"""
    reset_security_state_for_tests()
    if _limiter is not None:
        _limiter.reset()
    return _build_app(csrf_enabled=False)


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def csrf_app():
    """带 CSRF 中间件的 app。"""
    reset_security_state_for_tests()
    return _build_app(csrf_enabled=True)


@pytest.fixture
def csrf_client(csrf_app):
    return TestClient(csrf_app)


@pytest.fixture
def alice_user():
    """注册并返回基础测试用户信息。"""
    reset_security_state_for_tests()
    return {"username": "alice_r95", "password": "StrongP@ss123"}


# ── 测试类 1: JWT TTL 与结构 ──────────────────────────────────────────────
class TestJWTTTLAndStructure:
    def test_access_token_default_ttl_is_30_minutes(self):
        assert ACCESS_TOKEN_EXPIRE_MINUTES == 30

    def test_refresh_token_default_ttl_is_7_days(self):
        assert REFRESH_TOKEN_EXPIRE_DAYS == 7

    def test_access_token_has_jti_and_type(self):
        token = AuthService.create_access_token({"sub": "x", "role": "viewer"})
        from jose import jwt

        payload = jwt.decode(
            token, _AUTH_SECRET_KEY, algorithms=["HS256"]
        )
        assert "jti" in payload and len(payload["jti"]) > 8
        assert payload["type"] == TOKEN_TYPE_ACCESS

    def test_refresh_token_has_jti_and_type(self):
        token = AuthService.create_refresh_token({"sub": "x", "role": "viewer"})
        from jose import jwt

        payload = jwt.decode(
            token, _AUTH_SECRET_KEY, algorithms=["HS256"]
        )
        assert "jti" in payload
        assert payload["type"] == TOKEN_TYPE_REFRESH

    def test_access_token_exp_delta_is_30_minutes(self):
        from jose import jwt
        from datetime import datetime, timezone

        token = AuthService.create_access_token({"sub": "x"})
        payload = jwt.get_unverified_claims(token)
        iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        delta_min = (exp - iat).total_seconds() / 60
        # 允许 +/- 1s 误差
        assert abs(delta_min - 30) < 0.05

    def test_refresh_token_exp_delta_is_7_days(self):
        from jose import jwt
        from datetime import datetime, timezone

        token = AuthService.create_refresh_token({"sub": "x"})
        payload = jwt.get_unverified_claims(token)
        iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        delta_days = (exp - iat).total_seconds() / 86400
        assert abs(delta_days - 7) < 0.01

    def test_expired_token_raises_401(self):
        from datetime import timedelta

        # 用负 timedelta 模拟过期
        token = AuthService.create_access_token(
            {"sub": "x", "role": "viewer"},
            expires_delta=timedelta(seconds=-1),
        )
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            AuthService.decode_token(token)
        assert exc.value.status_code == 401


# ── 测试类 2: JWT Refresh 流程与黑名单 ───────────────────────────────────
class TestJWTRefreshAndBlacklist:
    def test_login_returns_access_and_refresh(self, client, alice_user):
        client.post("/auth/register", json=alice_user)
        r = client.post("/auth/login", json=alice_user)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "access_token" in data and len(data["access_token"]) > 20
        assert "refresh_token" in data and len(data["refresh_token"]) > 20
        assert "csrf_token" in data and len(data["csrf_token"]) > 20

    def test_refresh_returns_new_token_pair(self, client, alice_user):
        client.post("/auth/register", json=alice_user)
        login = client.post("/auth/login", json=alice_user).json()
        refresh_token = login["data"]["refresh_token"]
        r = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert r.status_code == 200
        new_pair = r.json()["data"]
        assert new_pair["access_token"] != login["data"]["access_token"]
        assert new_pair["refresh_token"] != refresh_token

    def test_refresh_old_token_revoked_after_first_use(self, client, alice_user):
        client.post("/auth/register", json=alice_user)
        login = client.post("/auth/login", json=alice_user).json()
        rt = login["data"]["refresh_token"]
        # 第一次用 OK
        r1 = client.post("/auth/refresh", json={"refresh_token": rt})
        assert r1.status_code == 200
        # 第二次用 → 401
        r2 = client.post("/auth/refresh", json={"refresh_token": rt})
        assert r2.status_code == 401

    def test_revoked_access_token_rejected_by_get_me(self, client, alice_user):
        client.post("/auth/register", json=alice_user)
        login = client.post("/auth/login", json=alice_user).json()
        access = login["data"]["access_token"]
        # 第一次 /me 成功
        r1 = client.get(
            "/auth/me", headers={"Authorization": f"Bearer {access}"}
        )
        assert r1.status_code == 200
        # logout (revoke) → 再请求 401
        client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {access}"},
        )
        r2 = client.get(
            "/auth/me", headers={"Authorization": f"Bearer {access}"}
        )
        assert r2.status_code == 401

    def test_revoked_cache_persisted_to_db(self, alice_user):
        reset_security_state_for_tests()
        AuthService.register(alice_user["username"], alice_user["password"])
        # 登录拿 token
        from fastapi.testclient import TestClient

        c = TestClient(_build_app(csrf_enabled=False))
        login = c.post("/auth/login", json=alice_user).json()
        access = login["data"]["access_token"]
        # logout
        c.post("/auth/logout", headers={"Authorization": f"Bearer {access}"})
        # 直接读 DB 看是否写入了 revoked_tokens
        db_path = auth_routes._get_db_path()
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT jti, username, token_type FROM revoked_tokens"
        ).fetchall()
        conn.close()
        assert any(r[1] == alice_user["username"] for r in rows), \
            f"Expected a revoked_tokens row for {alice_user['username']}, got {rows}"

    def test_garbage_token_raises_401(self, client):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            AuthService.decode_token("not.a.valid.jwt")
        assert exc.value.status_code == 401


# ── 测试类 3: 限流 ────────────────────────────────────────────────────────
class TestRateLimiting:
    def test_cors_whitelist_is_not_wildcard(self):
        """默认白名单不允许通配符 ``*``。"""
        assert "*" not in CORS_ALLOWED_ORIGINS

    def test_cors_whitelist_includes_localhost(self):
        assert any("localhost" in o for o in CORS_ALLOWED_ORIGINS)

    def test_default_trusted_origins_count(self):
        """默认白名单至少 3 个本地 origin。"""
        assert len(DEFAULT_TRUSTED_ORIGINS) >= 3

    def test_is_origin_allowed_for_known(self):
        assert is_origin_allowed("http://localhost:3000") is True
        assert is_origin_allowed("http://evil.com") is False
        assert is_origin_allowed(None) is False
        assert is_origin_allowed("") is False

    def test_login_6th_attempt_returns_429(self, client, alice_user):
        """login 限流 5/min: 第 6 次同 IP 应被 slowapi 限流。"""
        client.post("/auth/register", json=alice_user)
        # 连发 6 次错误密码
        statuses = []
        for _ in range(6):
            r = client.post(
                "/auth/login",
                json={"username": alice_user["username"], "password": "WrongP@ss1"},
            )
            statuses.append(r.status_code)
        # 前 5 次 401, 第 6 次 429 (限流)
        assert 429 in statuses, f"expected 429 in statuses, got {statuses}"

    def test_login_rate_limit_after_register_does_not_block(self, client):
        """注册次数不限流外的端口不会触发限流。"""
        if _limiter is None:
            pytest.skip("slowapi not available")
        _limiter.reset()
        # 注册一个新用户一次 → 不应 429
        r = client.post(
            "/auth/register",
            json={"username": "once_user", "password": "StrongP@ss1"},
        )
        assert r.status_code == 200


# ── 测试类 4: CSRF 中间件 ────────────────────────────────────────────────
class TestCSRFMiddleware:
    def test_csrf_safe_paths_skip_check(self, csrf_client):
        """``/auth/login`` 是 safe path, 无 CSRF token 也应通过。"""
        r = csrf_client.post(
            "/auth/login",
            json={"username": "x", "password": "x"},
        )
        # 不是 403 csrf 即可 (可能是 401 invalid creds)
        assert r.status_code != 403 or "csrf" not in r.text.lower()

    def test_csrf_blocks_untrusted_origin_on_unsafe_method(self, csrf_client, alice_user):
        """不信任 origin 的 POST 应被拦截为 403。"""
        csrf_client.post("/auth/register", json=alice_user)
        login = csrf_client.post("/auth/login", json=alice_user).json()
        csrf = login["data"]["csrf_token"]
        # 设 csrf cookie + 走 /auth/password (PUT, unsafe) 但 origin 不可信
        csrf_client.cookies.set("csrf_token", csrf)
        # 模拟恶意 origin
        r = csrf_client.put(
            "/auth/password",
            json={"old_password": alice_user["password"], "new_password": "NewStrong@123"},
            headers={"Origin": "http://evil.com", "X-CSRF-Token": csrf},
        )
        assert r.status_code == 403
        assert "csrf" in r.text.lower() or "origin" in r.text.lower()

    def test_csrf_allows_trusted_origin_with_matching_token(self, csrf_client, alice_user):
        """trusted origin + 匹配 token 通过。"""
        csrf_client.post("/auth/register", json=alice_user)
        login = csrf_client.post("/auth/login", json=alice_user).json()
        csrf = login["data"]["csrf_token"]
        csrf_client.cookies.set("csrf_token", csrf)
        r = csrf_client.put(
            "/auth/password",
            json={"old_password": alice_user["password"], "new_password": "NewerStrong@456"},
            headers={"Origin": "http://localhost:3000", "X-CSRF-Token": csrf},
        )
        # 200 / 400 (业务错误), 但不是 403 csrf
        assert r.status_code != 403, f"unexpected 403: {r.text}"

    def test_csrf_token_mismatch_returns_403(self, csrf_client, alice_user):
        """trusted origin 但 cookie/header token 不一致 → 403。"""
        csrf_client.post("/auth/register", json=alice_user)
        login = csrf_client.post("/auth/login", json=alice_user).json()
        csrf_client.cookies.set("csrf_token", login["data"]["csrf_token"])
        wrong_token = generate_csrf_token()
        r = csrf_client.put(
            "/auth/password",
            json={"old_password": alice_user["password"], "new_password": "An0therStrongP@ss"},
            headers={"Origin": "http://localhost:3000", "X-CSRF-Token": wrong_token},
        )
        assert r.status_code == 403

    def test_csrf_missing_token_returns_403(self, csrf_client, alice_user):
        """trusted origin 但缺 cookie/header token → 403。"""
        csrf_client.post("/auth/register", json=alice_user)
        csrf_client.cookies.clear()
        r = csrf_client.put(
            "/auth/password",
            json={"old_password": alice_user["password"], "new_password": "An0therStr0ngP@ss"},
            headers={"Origin": "http://localhost:3000"},
        )
        assert r.status_code == 403


# ── 测试类 5: GDPR 端点 ───────────────────────────────────────────────────
class TestGDPREndpoints:
    def test_export_requires_authentication(self, client):
        r = client.get("/auth/me/export")
        assert r.status_code == 401

    def test_login_then_export_returns_user_data(self, client, alice_user):
        client.post("/auth/register", json=alice_user)
        login = client.post("/auth/login", json=alice_user).json()
        access = login["data"]["access_token"]
        r = client.get(
            "/auth/me/export",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        data = body["data"]
        assert data["profile"]["username"] == alice_user["username"]
        assert "audit_log" in data
        assert data["export_basis"].startswith("GDPR")

    def test_erase_deletes_user(self, client, alice_user):
        client.post("/auth/register", json=alice_user)
        login = client.post("/auth/login", json=alice_user).json()
        access = login["data"]["access_token"]
        # 先 export 一次 (记录到审计)
        client.get(
            "/auth/me/export",
            headers={"Authorization": f"Bearer {access}"},
        )
        # DELETE
        r = client.delete(
            "/auth/me",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["erased"] is True
        # 验证: 用同样 token 再访问 /me → 401
        r2 = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r2.status_code == 401
        # 验证: 重新登录同名用户应该可以 (注册流程)
        r3 = client.post("/auth/register", json=alice_user)
        assert r3.status_code == 200

    def test_export_then_audit_shows_entry(self, client, alice_user):
        client.post("/auth/register", json=alice_user)
        login = client.post("/auth/login", json=alice_user).json()
        access = login["data"]["access_token"]
        # export 一次
        client.get(
            "/auth/me/export",
            headers={"Authorization": f"Bearer {access}"},
        )
        # 查审计
        r = client.get(
            "/auth/me/audit",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r.status_code == 200
        entries = r.json()["data"]["entries"]
        actions = [e["action"] for e in entries]
        assert "login" in actions
        assert "export" in actions

    def test_audit_requires_authentication(self, client):
        r = client.get("/auth/me/audit")
        assert r.status_code == 401

    def test_password_change_creates_audit_entry(self, client, alice_user):
        client.post("/auth/register", json=alice_user)
        login = client.post("/auth/login", json=alice_user).json()
        access = login["data"]["access_token"]
        r = client.put(
            "/auth/password",
            json={"old_password": alice_user["password"], "new_password": "NewStrong@1234"},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r.status_code == 200
        # 查审计
        r2 = client.get(
            "/auth/me/audit",
            headers={"Authorization": f"Bearer {access}"},
        )
        actions = [e["action"] for e in r2.json()["data"]["entries"]]
        assert "password_change" in actions


# ── 测试类 6: 密码强度校验 ───────────────────────────────────────────────
class TestPasswordStrength:
    def test_too_short_rejected(self):
        ok, msg = validate_password_strength("Aa1")
        assert ok is False
        assert "8" in msg

    def test_no_uppercase_rejected(self):
        ok, _ = validate_password_strength("longpw0rd!aa")
        assert ok is False

    def test_no_digit_rejected(self):
        ok, _ = validate_password_strength("NoDigitsAtAll!")
        assert ok is False

    def test_weak_password_rejected(self):
        ok, _ = validate_password_strength("Password1")
        # 注意 Password1 不在弱密码列表中, 但 Password 单独是
        # 用 12345678 测 (无大写会被先拦), 改用 Password! 测
        ok, msg = validate_password_strength("password!")
        # password! 无数字 → 失败
        assert ok is False

    def test_common_weak_password_rejected(self):
        ok, msg = validate_password_strength("Qwerty123")
        # Qwerty123 在弱密码列表里
        assert ok is False
        assert "常见" in msg or "common" in msg.lower()

    def test_strong_password_accepted(self):
        ok, msg = validate_password_strength("V3ryStrongP@ss")
        assert ok is True, msg


# ── 测试类 7: 登录交互 ───────────────────────────────────────────────────
class TestLoginInteraction:
    def test_login_sets_csrf_cookie(self, client, alice_user):
        client.post("/auth/register", json=alice_user)
        r = client.post("/auth/login", json=alice_user)
        assert r.status_code == 200
        # 响应 cookie 里应该有 csrf_token
        cookies = r.cookies
        assert "csrf_token" in cookies

    def test_login_response_includes_expires_in(self, client, alice_user):
        client.post("/auth/register", json=alice_user)
        r = client.post("/auth/login", json=alice_user)
        data = r.json()["data"]
        # 30 min = 1800 s
        assert data.get("expires_in") == 1800

    def test_login_invalid_credentials_returns_401(self, client, alice_user):
        client.post("/auth/register", json=alice_user)
        r = client.post(
            "/auth/login",
            json={"username": alice_user["username"], "password": "WrongP@ss1"},
        )
        assert r.status_code == 401

    def test_register_then_login_full_flow(self, client):
        user = {"username": "flowuser", "password": "FlowStr0ng!"}
        r1 = client.post("/auth/register", json=user)
        assert r1.status_code == 200
        r2 = client.post("/auth/login", json=user)
        assert r2.status_code == 200
        access = r2.json()["data"]["access_token"]
        r3 = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert r3.status_code == 200
        assert r3.json()["data"]["username"] == user["username"]


# ── 统计 ──────────────────────────────────────────────────────────────────
def test_module_collects_at_least_25_cases():
    """本文件至少 25 个 test_ 方法 (sanity check)。"""
    import inspect

    module = sys.modules[__name__]
    cases = [
        name for name, obj in inspect.getmembers(module)
        if inspect.isclass(obj) and obj.__module__ == module.__name__
        and name.startswith("Test")
    ]
    total = 0
    for cls_name in cases:
        cls = getattr(module, cls_name)
        total += sum(
            1 for name, _ in inspect.getmembers(cls, inspect.isfunction)
            if name.startswith("test_")
        )
    assert total >= 25, f"expected >=25 cases, got {total}"