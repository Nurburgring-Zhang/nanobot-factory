"""
P10R4-1 / P0-5: Token Revocation 单元测试
=============================================

覆盖:
1. revoke(jti) 基本功能
2. is_revoked() O(1) 查询
3. revoke_user(user_id) 吊销用户所有 token
4. revoke_all() 全场吊销
5. gc() 清理过期条目
6. persistence (SQLite) 跨实例保留
7. UnifiedAuthManager 集成 (verify_token 检查 revocation)

OWASP A07:2021 对标: Identification and Authentication Failures
"""
from __future__ import annotations

import os
import sys
import time
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Add backend/ to sys.path
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from auth.token_revocation import (
    TokenRevocationStore,
    get_revocation_store,
    reset_default_store,
)
from auth.unified_auth import AuthUser


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """临时 SQLite 文件 — 每个 test 隔离."""
    return str(tmp_path / "test_revocation.db")


@pytest.fixture
def store(tmp_db):
    """新 store 实例, 每次 test 重置."""
    reset_default_store()
    s = TokenRevocationStore(db_path=tmp_db)
    yield s
    s.gc()
    reset_default_store()


@pytest.fixture
def fixed_clock():
    """可注入时钟 — 避免真实 sleep."""
    return mock.MagicMock(return_value=1_700_000_000.0)


# ── Test 1: 基本 revoke + is_revoked ────────────────────────────────────

class TestRevokeBasics:
    def test_revoke_and_is_revoked_true(self, store):
        ok = store.revoke(
            jti="abc123",
            user_id="user-1",
            reason="logout",
            expires_at_epoch=time.time() + 3600,
        )
        assert ok is True
        assert store.is_revoked("abc123") is True

    def test_is_revoked_returns_false_for_unknown(self, store):
        assert store.is_revoked("never_revoked") is False

    def test_revoke_empty_jti_raises(self, store):
        with pytest.raises(ValueError, match="jti is required"):
            store.revoke(jti="")

    def test_revoke_already_revoked_returns_false(self, store):
        expires = time.time() + 3600
        assert store.revoke("dup", expires_at_epoch=expires) is True
        assert store.revoke("dup", expires_at_epoch=expires) is False

    def test_revoke_already_expired_skipped(self, store):
        # expires_at_epoch 已过 — 不应加入 revocation list
        expired_ts = time.time() - 100
        ok = store.revoke("expired_jti", expires_at_epoch=expired_ts)
        assert ok is False
        assert store.is_revoked("expired_jti") is False


# ── Test 2: expire 后 lazy cleanup ──────────────────────────────────────

class TestExpire:
    def test_is_revoked_lazy_clears_expired(self, tmp_db):
        # 用 fixed clock 控制时间
        clock = mock.MagicMock(return_value=1_700_000_000.0)
        reset_default_store()
        store = TokenRevocationStore(db_path=tmp_db, clock=clock)
        # T=1_700_000_000 (revoke, expires 100s later)
        store.revoke("j1", expires_at_epoch=1_700_000_000 + 100)
        assert store.is_revoked("j1") is True
        # T=1_700_000_200 (expired)
        clock.return_value = 1_700_000_000 + 200
        assert store.is_revoked("j1") is False
        reset_default_store()

    def test_gc_removes_expired(self, tmp_db):
        clock = mock.MagicMock(return_value=1_700_000_000.0)
        reset_default_store()
        store = TokenRevocationStore(db_path=tmp_db, clock=clock)
        store.revoke("j2", expires_at_epoch=1_700_000_000 + 100)
        # 推进时间
        clock.return_value = 1_700_000_000 + 200
        removed = store.gc()
        assert removed >= 1
        # SQLite 中也应清理
        assert store.is_revoked("j2") is False
        reset_default_store()


# ── Test 3: revoke_user ──────────────────────────────────────────────────

class TestRevokeUser:
    def test_revoke_user_creates_marker(self, store):
        deleted = store.revoke_user("user-42", reason="password_changed")
        assert store.is_user_revoked("user-42") is True
        assert isinstance(deleted, int)

    def test_revoke_user_other_user_unaffected(self, store):
        store.revoke_user("user-A", reason="x")
        store.revoke_user("user-B", reason="y")
        assert store.is_user_revoked("user-A") is True
        assert store.is_user_revoked("user-B") is True
        assert store.is_user_revoked("user-C") is False

    def test_revoke_user_empty_id_returns_zero(self, store):
        assert store.revoke_user("") == 0


# ── Test 4: revoke_all ───────────────────────────────────────────────────

class TestRevokeAll:
    def test_revoke_all_sets_global_marker(self, store):
        n = store.revoke_all("compromised_secret")
        assert n >= 1
        assert store.is_globally_revoked() is True

    def test_is_globally_revoked_false_initially(self, store):
        assert store.is_globally_revoked() is False


# ── Test 5: 持久化 / 重启 ────────────────────────────────────────────────

class TestPersistence:
    def test_state_survives_restart(self, tmp_db):
        reset_default_store()
        # 实例 1: revoke
        s1 = TokenRevocationStore(db_path=tmp_db)
        s1.revoke("persistent_jti", expires_at_epoch=time.time() + 3600)
        s1.revoke_user("user-X", reason="test")
        del s1

        # 实例 2: 重新加载
        s2 = TokenRevocationStore(db_path=tmp_db)
        assert s2.is_revoked("persistent_jti") is True
        assert s2.is_user_revoked("user-X") is True
        reset_default_store()

    def test_default_singleton(self, tmp_db):
        reset_default_store()
        # 默认 singleton 用 env DATA_DIR — 这里我们直接构造 + 替换
        store = TokenRevocationStore(db_path=tmp_db)
        with mock.patch("auth.token_revocation._default_store", store):
            assert get_revocation_store() is store
        reset_default_store()

    def test_reset_default_store(self):
        reset_default_store()
        assert get_revocation_store() is not None  # lazy init
        reset_default_store()


# ── Test 6: 统计 / 调试 ──────────────────────────────────────────────────

class TestStats:
    def test_stats_empty(self, store):
        s = store.stats()
        assert s["tracked_jti"] == 0
        assert s["active_revocations"] == 0
        assert s["globally_revoked"] is False

    def test_stats_after_revoke(self, store):
        store.revoke("a", expires_at_epoch=time.time() + 3600)
        store.revoke("b", expires_at_epoch=time.time() + 3600)
        s = store.stats()
        assert s["tracked_jti"] >= 2
        assert s["active_revocations"] >= 2

    def test_list_revoked(self, store):
        store.revoke("audit-1", user_id="u1", reason="test", expires_at_epoch=time.time() + 3600)
        recs = store.list_revoked(user_id="u1", limit=10)
        assert any(r["jti"] == "audit-1" for r in recs)
        assert any(r["user_id"] == "u1" for r in recs)


# ── Test 7: UnifiedAuthManager 集成 ──────────────────────────────────────

class TestUnifiedAuthIntegration:
    """P10R4-1: UnifiedAuthManager.verify_token 必须 check revocation."""

    SECRET = "test-secret-revocation-integration-aaaaa"

    def _make_manager(self, tmp_db):
        from auth.unified_auth import UnifiedAuthManager, JWT_ISSUER, JWT_AUDIENCE
        import os
        os.environ["JWT_SECRET"] = self.SECRET
        mgr = UnifiedAuthManager(jwt_secret=self.SECRET, db_path=tmp_db)
        return mgr

    def test_verify_token_after_revoke_returns_none(self, tmp_db):
        from auth.unified_auth import UnifiedAuthManager
        import os
        os.environ["JWT_SECRET"] = self.SECRET
        mgr = UnifiedAuthManager(jwt_secret=self.SECRET, db_path=tmp_db)

        # 创建一个 user + login 获取 token
        from auth.unified_auth import UnifiedRole
        import secrets as _sec
        from datetime import datetime
        user = AuthUser(
            user_id="u_" + _sec.token_hex(4),
            username="revoke_test_user",
            email="t@t.com",
            role=UnifiedRole.VIEWER.value,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$xxx",
            password_salt="",
            hash_method="argon2",
            is_active=True,
            display_name="Test",
            created_at=datetime.now().isoformat(),
        )
        mgr.db.insert_user(user)
        user_id = user.user_id
        token = mgr.jwt_manager.create_access_token(
            user_id=user_id, username="revoke_test_user",
            role=UnifiedRole.VIEWER.value, permissions=[],
        )

        # 1) verify 应当成功
        payload = mgr.verify_token(token)
        assert payload is not None
        assert payload["sub"] == user_id

        # 2) 吊销 token
        ok = mgr.revoke_token(token, reason="logout_test")
        assert ok is True

        # 3) verify 现在应返回 None
        assert mgr.verify_token(token) is None

    def test_revoke_user_invalidates_all_tokens(self, tmp_db):
        from auth.unified_auth import UnifiedAuthManager, UnifiedRole
        import os
        import secrets as _sec
        from datetime import datetime
        os.environ["JWT_SECRET"] = self.SECRET
        mgr = UnifiedAuthManager(jwt_secret=self.SECRET, db_path=tmp_db)

        user = AuthUser(
            user_id="u_" + _sec.token_hex(4),
            username="user_revoke_all",
            email="r@r.com",
            role=UnifiedRole.VIEWER.value,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$xxx",
            password_salt="",
            hash_method="argon2",
            is_active=True,
            created_at=datetime.now().isoformat(),
        )
        mgr.db.insert_user(user)
        user_id = user.user_id
        token = mgr.jwt_manager.create_access_token(
            user_id=user_id, username="user_revoke_all",
            role=UnifiedRole.VIEWER.value, permissions=[],
        )
        # verify 成功
        assert mgr.verify_token(token) is not None
        # revoke_user
        mgr.revoke_user(user_id, reason="account_disabled")
        # 现在 verify 应失败 (user-level)
        assert mgr.verify_token(token) is None

    def test_revoke_all_blocks_everyone(self, tmp_db):
        from auth.unified_auth import UnifiedAuthManager, UnifiedRole
        import os
        import secrets as _sec
        from datetime import datetime
        os.environ["JWT_SECRET"] = self.SECRET
        mgr = UnifiedAuthManager(jwt_secret=self.SECRET, db_path=tmp_db)

        user = AuthUser(
            user_id="u_" + _sec.token_hex(4),
            username="user_global_revoke",
            email="g@g.com",
            role=UnifiedRole.VIEWER.value,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$xxx",
            password_salt="",
            hash_method="argon2",
            is_active=True,
            created_at=datetime.now().isoformat(),
        )
        mgr.db.insert_user(user)
        user_id = user.user_id
        token = mgr.jwt_manager.create_access_token(
            user_id=user_id, username="user_global_revoke",
            role=UnifiedRole.VIEWER.value, permissions=[],
        )
        assert mgr.verify_token(token) is not None
        mgr.revoke_all("security_incident_test")
        assert mgr.verify_token(token) is None

    def test_change_password_auto_revokes_old_tokens(self, tmp_db):
        from auth.unified_auth import UnifiedAuthManager, UnifiedRole
        import os
        import secrets as _sec
        from datetime import datetime
        os.environ["JWT_SECRET"] = self.SECRET
        mgr = UnifiedAuthManager(jwt_secret=self.SECRET, db_path=tmp_db)

        # 用 manager 创建一个 user + 设置已知密码
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        hash_ = ph.hash("OldPassword@2026!")
        user = AuthUser(
            user_id="u_" + _sec.token_hex(4),
            username="change_pw_user",
            email="c@c.com",
            role=UnifiedRole.VIEWER.value,
            password_hash=hash_,
            password_salt="",
            hash_method="argon2",
            is_active=True,
            created_at=datetime.now().isoformat(),
        )
        mgr.db.insert_user(user)
        user_id = user.user_id
        token = mgr.jwt_manager.create_access_token(
            user_id=user_id, username="change_pw_user",
            role=UnifiedRole.VIEWER.value, permissions=[],
        )
        assert mgr.verify_token(token) is not None

        # 修改密码
        ok = mgr.change_password(
            user_id=user_id,
            old_password="OldPassword@2026!",
            new_password="NewPassword@2026!EvenStronger",
        )
        assert ok is True
        # 旧 token 必须失效 (OWASP A07)
        assert mgr.verify_token(token) is None