"""
P10R4-1: HIDDEN-1..5 Fix Verification Tests
============================================

HIDDEN-1: UnifiedAuthManager reads BRUTE_FORCE_PERSISTENCE env var
HIDDEN-2: routes/auth_routes.py /logout endpoint calls mgr.revoke_token
HIDDEN-3: server.py startup calls init_all_third_party()
HIDDEN-4: token_revocation.py has start_background_gc daemon thread
HIDDEN-5: clear_global_revocation() admin method exists
"""
from __future__ import annotations

import os
import sys
import time
import threading
from pathlib import Path
from unittest import mock

import pytest

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ─────────────────────────────────────────────────────────────────
# HIDDEN-1: BRUTE_FORCE_PERSISTENCE env var
# ─────────────────────────────────────────────────────────────────

class TestBruteForcePersistenceEnvVar:
    """HIDDEN-1: UnifiedAuthManager 必须读 BRUTE_FORCE_PERSISTENCE env."""

    SECRET = "test-secret-h1-aaaaa"

    def _make_mgr(self, env_value: str = ""):
        from auth.unified_auth import UnifiedAuthManager
        os.environ["JWT_SECRET"] = self.SECRET
        os.environ["ADMIN_INITIAL_PASSWORD"] = "TestAdmin@2026!StrongSecret32chars"
        if env_value:
            os.environ["BRUTE_FORCE_PERSISTENCE"] = env_value
        elif "BRUTE_FORCE_PERSISTENCE" in os.environ:
            del os.environ["BRUTE_FORCE_PERSISTENCE"]
        # Reset singleton
        from auth.unified_auth import reset_unified_auth
        reset_unified_auth()
        mgr = UnifiedAuthManager(jwt_secret=self.SECRET, db_path="")
        return mgr

    def test_default_no_env_persistence_disabled(self):
        mgr = self._make_mgr()
        assert mgr._bruteforce_persistence_enabled is False
        assert mgr.throttle._enable_persistence is False

    def test_env_true_enables_persistence(self):
        mgr = self._make_mgr(env_value="true")
        assert mgr._bruteforce_persistence_enabled is True
        assert mgr.throttle._enable_persistence is True

    def test_env_1_enables_persistence(self):
        mgr = self._make_mgr(env_value="1")
        assert mgr._bruteforce_persistence_enabled is True

    def test_env_false_disables_persistence(self):
        mgr = self._make_mgr(env_value="false")
        assert mgr._bruteforce_persistence_enabled is False

    def test_explicit_param_overrides_env(self):
        from auth.unified_auth import UnifiedAuthManager
        from auth.unified_auth import reset_unified_auth
        os.environ["BRUTE_FORCE_PERSISTENCE"] = "true"
        reset_unified_auth()
        mgr = UnifiedAuthManager(
            jwt_secret=self.SECRET,
            db_path="",
            enable_bruteforce_persistence=False,  # 显式 False
        )
        # 显式参数覆盖 env
        assert mgr._bruteforce_persistence_enabled is False


# ─────────────────────────────────────────────────────────────────
# HIDDEN-2: /logout endpoint
# ─────────────────────────────────────────────────────────────────

class TestLogoutEndpoint:
    """HIDDEN-2: /api/auth/logout 必须调 mgr.revoke_token."""

    def test_logout_endpoint_exists(self):
        from routes.auth_routes import router
        paths = [r.path for r in router.routes]
        # 接受 /logout 或 /api/auth/logout
        assert any("/logout" in p for p in paths), f"/logout not found in {paths}"

    def test_logout_revokes_token(self, tmp_path):
        """调 /logout 后 token 必须失效."""
        from fastapi.testclient import TestClient
        from routes.auth_routes import router
        from auth.unified_auth import (
            UnifiedAuthManager, UnifiedRole, AuthUser,
            get_unified_auth, reset_unified_auth,
        )
        from datetime import datetime
        import secrets as _sec

        # 准备 — 用模块级单例, 路由的 _get_auth() 也用同一个
        os.environ["JWT_SECRET"] = "x" * 64
        os.environ["ADMIN_INITIAL_PASSWORD"] = "TestAdmin@2026!StrongSecret32chars"
        reset_unified_auth()

        db_path = str(tmp_path / "logout_test.db")
        mgr = UnifiedAuthManager(jwt_secret="x" * 64, db_path=db_path)
        # 让 routes 用的 _get_auth() 也能找到这个实例 — 通过 module-level
        import routes.auth_routes as _ar
        _ar._auth = mgr

        # 创建一个 user
        user = AuthUser(
            user_id="u_" + _sec.token_hex(4),
            username="logout_user",
            email="l@l.com",
            role=UnifiedRole.VIEWER.value,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$xxx",
            password_salt="",
            hash_method="argon2",
            is_active=True,
            created_at=datetime.now().isoformat(),
        )
        mgr.db.insert_user(user)
        token = mgr.jwt_manager.create_access_token(
            user_id=user.user_id,
            username=user.username,
            role=user.role,
        )

        # 验证 token 当前有效
        assert mgr.verify_token(token) is not None

        # 用 TestClient 调 /logout
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # /logout 需要 get_current_user → 需要 Authorization header
        resp = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
            json={"reason": "user_logout_test"},
        )
        # 期望 200
        assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["token_revoked"] is True

        # 现在 token 必须失效
        assert mgr.verify_token(token) is None

    def test_logout_without_auth_rejected(self, tmp_path):
        """无 Authorization header 必须 401."""
        from fastapi.testclient import TestClient
        from routes.auth_routes import router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/auth/logout", json={})
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────
# HIDDEN-3: server.py startup calls init_all_third_party
# ─────────────────────────────────────────────────────────────────

class TestServerStartupThirdParty:
    """HIDDEN-3: server.py 启动时必须调 init_all_third_party()."""

    def test_server_imports_init_all_third_party(self):
        """server.py 必须 import init_all_third_party."""
        from pathlib import Path
        server_path = Path(_BACKEND) / "server.py"
        content = server_path.read_text(encoding="utf-8", errors="ignore")
        assert "init_all_third_party" in content, \
            "server.py should import / call init_all_third_party at startup"

    def test_init_all_third_party_callable(self):
        """import + 调用必须不抛."""
        from common.third_party import init_all_third_party
        # 清 SENTRY_DSN
        os.environ.pop("SENTRY_DSN", None)
        result = init_all_third_party()
        assert "sentry" in result
        assert "structlog" in result


# ─────────────────────────────────────────────────────────────────
# HIDDEN-4: token_revocation start_background_gc
# ─────────────────────────────────────────────────────────────────

class TestBackgroundGC:
    """HIDDEN-4: TokenRevocationStore.start_background_gc 必须存在并能启动."""

    def test_method_exists(self, tmp_path):
        from auth.token_revocation import TokenRevocationStore
        s = TokenRevocationStore(db_path=str(tmp_path / "gc_test.db"))
        assert hasattr(s, "start_background_gc")
        assert callable(s.start_background_gc)

    def test_starts_daemon_thread(self, tmp_path):
        from auth.token_revocation import TokenRevocationStore
        s = TokenRevocationStore(db_path=str(tmp_path / "gc_daemon.db"))
        thread = s.start_background_gc(interval_seconds=60)
        assert isinstance(thread, threading.Thread)
        assert thread.daemon is True
        assert thread.is_alive()
        # 第二次调用应返回已存在的 thread
        thread2 = s.start_background_gc(interval_seconds=60)
        assert thread2 is thread

    def test_gc_loop_actually_runs(self, tmp_path):
        """短间隔验证 GC 真的运行了."""
        from auth.token_revocation import TokenRevocationStore
        s = TokenRevocationStore(db_path=str(tmp_path / "gc_run.db"))
        # 加一个会过期的条目
        s.revoke("soon_expired", expires_at_epoch=time.time() - 100)
        # 启动短间隔 GC
        thread = s.start_background_gc(interval_seconds=1)
        # 等 3 秒
        time.sleep(3)
        # 至少 gc 一次
        assert s.is_revoked("soon_expired") is False

    def test_unified_auth_starts_gc_when_env_set(self, tmp_path):
        """TOKEN_REVOCATION_GC=true 应启动 background GC."""
        from auth.unified_auth import UnifiedAuthManager, reset_unified_auth
        os.environ["JWT_SECRET"] = "x" * 64
        os.environ["ADMIN_INITIAL_PASSWORD"] = "TestAdmin@2026!StrongSecret32chars"
        os.environ["TOKEN_REVOCATION_GC"] = "true"
        os.environ["TOKEN_REVOCATION_GC_INTERVAL"] = "60"
        reset_unified_auth()
        mgr = UnifiedAuthManager(
            jwt_secret="x" * 64,
            db_path=str(tmp_path / "uagm.db"),
        )
        assert mgr._revocation_gc_enabled is True
        assert hasattr(mgr.revocation, "_gc_thread")
        assert mgr.revocation._gc_thread is not None
        assert mgr.revocation._gc_thread.daemon is True
        # 清理
        del os.environ["TOKEN_REVOCATION_GC"]
        del os.environ["TOKEN_REVOCATION_GC_INTERVAL"]


# ─────────────────────────────────────────────────────────────────
# HIDDEN-5: clear_global_revocation
# ─────────────────────────────────────────────────────────────────

class TestClearGlobalRevocation:
    """HIDDEN-5: 必须有 clear_global_revocation() 方法."""

    def test_method_exists(self, tmp_path):
        from auth.token_revocation import TokenRevocationStore
        s = TokenRevocationStore(db_path=str(tmp_path / "cgr.db"))
        assert hasattr(s, "clear_global_revocation")
        assert callable(s.clear_global_revocation)

    def test_clear_after_revoke_all(self, tmp_path):
        from auth.token_revocation import TokenRevocationStore
        s = TokenRevocationStore(db_path=str(tmp_path / "cgr2.db"))
        s.revoke_all("test_incident")
        assert s.is_globally_revoked() is True
        result = s.clear_global_revocation()
        assert result is True
        assert s.is_globally_revoked() is False

    def test_clear_when_not_revoked(self, tmp_path):
        from auth.token_revocation import TokenRevocationStore
        s = TokenRevocationStore(db_path=str(tmp_path / "cgr3.db"))
        result = s.clear_global_revocation()
        assert result is False  # 之前没 revoke, 返回 False
        assert s.is_globally_revoked() is False

    def test_clear_persisted_across_restart(self, tmp_path):
        """clear 必须持久化 — 重启后仍然是 clear 状态."""
        from auth.token_revocation import TokenRevocationStore
        db = str(tmp_path / "cgr4.db")
        s1 = TokenRevocationStore(db_path=db)
        s1.revoke_all("incident")
        s1.clear_global_revocation()
        # 重启
        s2 = TokenRevocationStore(db_path=db)
        assert s2.is_globally_revoked() is False

    def test_unified_auth_exposes_clear_global_revocation(self, tmp_path):
        """UnifiedAuthManager 也要 expose 这个方法."""
        from auth.unified_auth import UnifiedAuthManager, reset_unified_auth
        os.environ["JWT_SECRET"] = "x" * 64
        os.environ["ADMIN_INITIAL_PASSWORD"] = "TestAdmin@2026!StrongSecret32chars"
        reset_unified_auth()
        mgr = UnifiedAuthManager(
            jwt_secret="x" * 64,
            db_path=str(tmp_path / "uacgr.db"),
        )
        assert hasattr(mgr, "clear_global_revocation")
        assert callable(mgr.clear_global_revocation)
        mgr.revoke_all("test")
        assert mgr.is_globally_revoked() is True
        cleared = mgr.clear_global_revocation()
        assert cleared is True
        assert mgr.is_globally_revoked() is False