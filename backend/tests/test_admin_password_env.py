"""
P11-D-1: Admin 密码 .env 注入测试套件
======================================

覆盖维度:
1. 默认 admin 密码从 ADMIN_INITIAL_PASSWORD env 注入
2. 缺省 + 非测试模式 → AdminConfigError (fail-fast, 防止默默用弱密码)
3. 缺省 + IMDF_TEST_MODE=1 → ephemeral 密码生成 + 启动成功
4. 显式 env → 用 env 提供的密码 (不修改)
5. 已存在的 admin 用户不会被覆盖 (idempotent)
6. .env.example 包含 ADMIN_INITIAL_PASSWORD 文档
7. 源码 grep 0 硬编码 Admin@2026! (除 docstring/测试 fixture)
8. 密码强度 (>= 12 字符) 软警告

目标: >= 8 用例 PASS
"""
from __future__ import annotations

import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

# ── 让 backend 目录可 import ──────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest  # noqa: E402

# P11-D-1: 必须先设置必要的 env 才能 import 模块
os.environ.setdefault("JWT_SECRET", secrets.token_hex(32))


from auth.unified_auth import (  # noqa: E402
    AdminConfigError,
    UnifiedAuthManager,
    reset_unified_auth,
)


# ── Fixtures ──────────────────────────────────────────────────────────────
@pytest.fixture
def fresh_db():
    """Each test gets a fresh SQLite DB."""
    with tempfile.TemporaryDirectory(prefix="admin_pw_test_") as td:
        db_path = str(Path(td) / "auth.db")
        yield db_path


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Strip ALL admin-related env vars so tests are hermetic."""
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    monkeypatch.delenv("IMDF_TEST_MODE", raising=False)
    reset_unified_auth()


# ── TEST 1: 默认 admin 密码从 env 注入 ───────────────────────────────────
def test_admin_password_loaded_from_env(fresh_db, monkeypatch):
    """env ADMIN_INITIAL_PASSWORD=foo 必须用于创建 admin 账户。"""
    pw = "TestPass_" + secrets.token_urlsafe(12)
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", pw)

    auth = UnifiedAuthManager(db_path=fresh_db)
    admin_user = auth.get_user(username="admin")
    assert admin_user is not None, "admin user should be created"
    assert admin_user.role == "admin"

    # 用注入的密码登录 → 成功
    result = auth.login("admin", pw)
    assert result.status == "success", f"login failed: {result.reason}"
    assert result.user["username"] == "admin"


# ── TEST 2: 缺省 + 非测试模式 → AdminConfigError (fail-fast) ─────────────
def test_missing_admin_password_raises_in_production(fresh_db, monkeypatch):
    """缺 ADMIN_INITIAL_PASSWORD + 不在测试模式 → AdminConfigError。"""
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    monkeypatch.delenv("IMDF_TEST_MODE", raising=False)

    with pytest.raises(AdminConfigError) as exc_info:
        UnifiedAuthManager(db_path=fresh_db)
    assert "ADMIN_INITIAL_PASSWORD" in str(exc_info.value)


# ── TEST 3: 缺省 + IMDF_TEST_MODE=1 → ephemeral 密码启动成功 ─────────────
def test_missing_admin_password_uses_ephemeral_in_test_mode(fresh_db, monkeypatch):
    """缺 ADMIN_INITIAL_PASSWORD + IMDF_TEST_MODE=1 → 自动生成 ephemeral 密码。"""
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    monkeypatch.setenv("IMDF_TEST_MODE", "1")

    auth = UnifiedAuthManager(db_path=fresh_db)
    admin_user = auth.get_user(username="admin")
    assert admin_user is not None
    assert admin_user.role == "admin"


# ── TEST 4: 已存在的 admin 不会被覆盖 (idempotent) ───────────────────────
def test_existing_admin_not_overwritten(fresh_db, monkeypatch):
    """如果 admin 已经存在, _ensure_admin_exists 不应该重置密码。"""
    pw_old = "Original_" + secrets.token_urlsafe(12)
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", pw_old)

    # 第一次启动 → 创建 admin
    auth1 = UnifiedAuthManager(db_path=fresh_db)
    assert auth1.get_user(username="admin") is not None

    # 关闭 + 改 env
    reset_unified_auth()
    pw_new = "ShouldNotBeUsed_" + secrets.token_urlsafe(12)
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", pw_new)

    # 第二次启动 → admin 仍存在, 但应该用原密码(不是新 env)
    auth2 = UnifiedAuthManager(db_path=fresh_db)
    login_old = auth2.login("admin", pw_old)
    login_new = auth2.login("admin", pw_new)
    assert login_old.status == "success", "original password should still work"
    assert login_new.status != "success", "new env password should NOT be used for existing admin"


# ── TEST 5: .env.example 包含 ADMIN_INITIAL_PASSWORD 文档 ─────────────────
def test_env_example_documents_admin_password():
    """P11-D-1: 部署文档必须包含 ADMIN_INITIAL_PASSWORD 说明。"""
    env_example = _BACKEND.parent / ".env.example"
    assert env_example.exists(), f".env.example not found at {env_example}"
    content = env_example.read_text(encoding="utf-8")
    assert "ADMIN_INITIAL_PASSWORD" in content, (
        ".env.example must document ADMIN_INITIAL_PASSWORD"
    )
    # 必须包含生成建议
    assert "secrets" in content or "token" in content, (
        ".env.example must show how to generate the password"
    )


# ── TEST 6: 源码 grep 0 硬编码 Admin@2026! (active code) ─────────────────
def test_no_hardcoded_admin_password_in_source():
    """P12-B1: 整个项目 (backend/ + scripts/ + .bat) 都不能有硬编码 Admin@2026!。

    范围扩大: P11-D-1 修复只覆盖了 backend/auth/; P12-B1 扩展到:
      - backend/ (Python)
      - scripts/ (Python, 项目根)
      - *.bat / *.sh (项目根 + 部署脚本)
    排除: 文档 (reports/*.md), .git, venv, node_modules, build, dist, omni_gen_studio
    """
    project_root = _BACKEND.parent
    EXCLUDE_DIRS = {"venv", ".venv", "__pycache__", "node_modules", ".git", "build", "dist", "omni_gen_studio", ".pytest_cache", "frontend", "web", ".mavis", ".harness", "outputs", "workspace"}
    EXCLUDE_FILES = {"test_admin_password_env.py"}  # 测试本身允许
    TARGET_EXT = (".py", ".bat", ".sh", ".cmd")
    source_files = []
    for root, dirs, files in os.walk(project_root, followlinks=False):
        # Prune excluded dirs in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            if fname.endswith(TARGET_EXT):
                source_files.append(Path(root) / fname)

    violations = []
    for f in source_files:
        if f.name in EXCLUDE_FILES:
            continue
        rel = f.relative_to(project_root)
        # tests/ 下的 fixture 允许 (monkeypatch.setenv)
        if "tests" in rel.parts and rel.name != "test_admin_password_env.py":
            continue
        # reports/*.md 历史文档已排除 (不在 TARGET_EXT)
        text = f.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            # 排除纯注释行
            if stripped.startswith("#"):
                continue
            # 排除 docstring / 错误消息中的历史叙述
            if "Admin@2026" in line:
                if any(kw in line for kw in ["removed", "硬编码", "硬编", "弃用", "deprecat", "legacy"]):
                    continue
                violations.append(f"{rel}:{lineno}: {line.strip()}")

    assert not violations, (
        f"Admin@2026! still hardcoded in active code:\n" + "\n".join(violations)
    )


# ── TEST 6b: 全项目 grep 0 硬编码非-admin 密码 (active code) ────────────────
def test_no_hardcoded_preset_passwords_in_source():
    """P12-B1: 11 个预设账号的密码(Prod@2026!, QC@20261! 等)也不能硬编码。

    检测的具体模式: Prod@, QC@, Crowd@, CrowdM@, CrowdQ@, Crowd1@, Client@
    """
    project_root = _BACKEND.parent
    EXCLUDE_DIRS = {"venv", ".venv", "__pycache__", "node_modules", ".git", "build", "dist", "omni_gen_studio", ".pytest_cache", "frontend", "web"}
    EXCLUDE_FILES = {"test_admin_password_env.py", "verify.py"}
    # 11 个非-admin 预设账号的密码前缀
    FORBIDDEN_PATTERNS = [
        "Prod@2026", "Prod1@2026", "Prod2@2026", "Prod3@2026",
        "QC@2026",
        "Crowd@2026", "CrowdM@2026", "CrowdQ@2026", "Crowd1@2026",
        "Client@2026",
    ]
    TARGET_EXT = (".py",)
    source_files = []
    for root, dirs, files in os.walk(project_root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in files:
            if fname.endswith(TARGET_EXT):
                source_files.append(Path(root) / fname)

    violations = []
    for f in source_files:
        if f.name in EXCLUDE_FILES:
            continue
        rel = f.relative_to(project_root)
        if "tests" in rel.parts and rel.name != "test_admin_password_env.py":
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            for pat in FORBIDDEN_PATTERNS:
                if pat in line:
                    # 排除 docstring / 错误消息中的历史叙述
                    if any(kw in line for kw in ["removed", "硬编码", "硬编", "弃用", "deprecat", "legacy"]):
                        continue
                    violations.append(f"{rel}:{lineno}: {line.strip()} (pattern: {pat})")
                    break  # 一次只报一行第一个匹配

    assert not violations, (
        f"Non-admin preset passwords still hardcoded:\n" + "\n".join(violations)
    )


# ── TEST 7: AdminConfigError 可被显式捕获 ───────────────────────────────
def test_admin_config_error_is_runtime_error_subclass():
    """AdminConfigError 必须继承 RuntimeError, 便于 catch 分类。"""
    assert issubclass(AdminConfigError, RuntimeError)
    err = AdminConfigError("test")
    assert str(err) == "test"
    with pytest.raises(RuntimeError):
        raise AdminConfigError("catches as RuntimeError")


# ── TEST 8: init_accounts.py 同步使用 env (一致性) ───────────────────────
def test_init_accounts_uses_env_for_admin():
    """scripts/init_accounts.py 的 admin password 必须从 env 解析。"""
    init_script = _BACKEND / "scripts" / "init_accounts.py"
    assert init_script.exists()
    text = init_script.read_text(encoding="utf-8")
    # 必须引用 ADMIN_INITIAL_PASSWORD
    assert "ADMIN_INITIAL_PASSWORD" in text, (
        "init_accounts.py must use ADMIN_INITIAL_PASSWORD env var"
    )
    # 必须不直接硬编码 Admin@2026! 作为 password 值
    # 允许 docstring 内的历史说明
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith('"""'):
            continue
        assert 'password="Admin@2026!"' not in line, (
            f"init_accounts.py hardcodes admin password: {line}"
        )


# ── TEST 9: 配置错误的错误消息清晰 ──────────────────────────────────────
def test_admin_config_error_message_mentions_remediation(fresh_db, monkeypatch):
    """错误消息应告诉运维怎么修, 而不只是说"配置错"。"""
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD", raising=False)
    monkeypatch.delenv("IMDF_TEST_MODE", raising=False)

    with pytest.raises(AdminConfigError) as exc_info:
        UnifiedAuthManager(db_path=fresh_db)
    msg = str(exc_info.value)
    # 必须包含 actionable 建议
    assert "ADMIN_INITIAL_PASSWORD" in msg
    assert "secrets" in msg.lower() or ".env" in msg.lower(), (
        f"error message should mention how to fix: {msg}"
    )


# ── TEST 10: 非 admin 账号密码也走 env (P12-B1) ─────────────────────────
def test_non_admin_accounts_use_env_passwords(fresh_db, monkeypatch):
    """P12-B1: scripts/init_accounts.py 的 10 个非 admin 账号必须从 env 读密码。"""
    # Set env for all 10 non-admin accounts
    envs = {
        "PROD_LEAD_PASSWORD": "ProdLeadPw_" + secrets.token_urlsafe(8),
        "QC_LEAD_PASSWORD": "QcLeadPw_" + secrets.token_urlsafe(8),
        "PROD_USER1_PASSWORD": "ProdU1Pw_" + secrets.token_urlsafe(8),
        "PROD_USER2_PASSWORD": "ProdU2Pw_" + secrets.token_urlsafe(8),
        "PROD_USER3_PASSWORD": "ProdU3Pw_" + secrets.token_urlsafe(8),
        "CROWD_LEAD_PASSWORD": "CrowdLeadPw_" + secrets.token_urlsafe(8),
        "CROWD_MGR_PASSWORD": "CrowdMgrPw_" + secrets.token_urlsafe(8),
        "CROWD_QC_PASSWORD": "CrowdQcPw_" + secrets.token_urlsafe(8),
        "CROWD_USER1_PASSWORD": "CrowdU1Pw_" + secrets.token_urlsafe(8),
        "CLIENT1_PASSWORD": "Client1Pw_" + secrets.token_urlsafe(8),
    }
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "AdminPw_" + secrets.token_urlsafe(8))
    for k, v in envs.items():
        monkeypatch.setenv(k, v)

    backend = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend))
    from scripts.init_accounts import init_accounts

    # Mock auth
    class MockAuth:
        def __init__(self):
            self.created = []
        def get_user(self, username):
            return None  # all users don't exist
        def register_user(self, username, password, role, email, display_name, team, metadata):
            self.created.append((username, password, role))
            return type("U", (), {
                "user_id": "u-" + username, "role": role, "team": team,
                "display_name": display_name, "username": username,
            })()
        def delete_user(self, uid):
            pass
        def list_users(self):
            return [{"username": u, "role": r, "team": t, "display_name": u} for u, p, r in self.created]

    auth = MockAuth()
    result = init_accounts(auth, reset=False)
    assert len(result["errors"]) == 0, f"errors: {result['errors']}"
    assert len(result["created"]) == 11, f"created: {len(result['created'])}"

    # Verify each non-admin account used its env password
    for username, password, role in auth.created:
        if username == "admin":
            continue
        expected = envs[f"{username.upper()}_PASSWORD"]
        assert password == expected, f"{username}: env_password mismatch"
    print(f"  All 10 non-admin accounts used env passwords")


# ── TEST 11: 非 admin 账号缺 env → fail-fast (P12-B1) ───────────────────
def test_non_admin_missing_env_fails_fast(fresh_db, monkeypatch):
    """P12-B1: 缺任一非 admin 账号 env, init_accounts 必须 fail-fast。"""
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "AdminPw_test")
    # 不设 PROD_LEAD_PASSWORD 等

    backend = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend))
    from scripts.init_accounts import init_accounts

    class MockAuth:
        def get_user(self, username):
            return None
        def register_user(self, username, password, role, email, display_name, team, metadata):
            return type("U", (), {
                "user_id": "u-" + username, "role": role, "team": team,
                "display_name": display_name, "username": username,
            })()
        def delete_user(self, uid):
            pass
        def list_users(self):
            return []

    auth = MockAuth()
    result = init_accounts(auth, reset=False)
    # 至少 1 个错误 (10 个非 admin 都缺 env, 每个都报错)
    assert len(result["errors"]) >= 10, f"expected >= 10 errors, got {len(result['errors'])}"
    # 第一个错误应该是 prod_lead
    first_err = result["errors"][0]
    assert "PROD_LEAD_PASSWORD" in str(first_err["reason"]), f"first error should mention PROD_LEAD_PASSWORD: {first_err}"
    print(f"  init_accounts failed fast with {len(result['errors'])} env errors (expected behavior)")


# ── TEST 12: IMDF_TEST_MODE=1 让非 admin 也走 ephemeral (P12-B1) ─────────
def test_non_admin_test_mode_uses_ephemeral(fresh_db, monkeypatch):
    """P12-B1: IMDF_TEST_MODE=1 时, 非 admin 缺 env 也能用 ephemeral 密码。"""
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "AdminPw_test")
    monkeypatch.setenv("IMDF_TEST_MODE", "1")
    # 不设任何非 admin env

    backend = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend))
    from scripts.init_accounts import init_accounts

    class MockAuth:
        def __init__(self):
            self.created = []
        def get_user(self, username):
            return None
        def register_user(self, username, password, role, email, display_name, team, metadata):
            self.created.append((username, password, role))
            return type("U", (), {
                "user_id": "u-" + username, "role": role, "team": team,
                "display_name": display_name, "username": username,
            })()
        def delete_user(self, uid):
            pass
        def list_users(self):
            return []

    auth = MockAuth()
    result = init_accounts(auth, reset=False)
    assert len(result["errors"]) == 0, f"errors: {result['errors']}"
    # admin + 10 non-admin 都创建成功
    assert len(result["created"]) == 11, f"created: {len(result['created'])}"
    # 非 admin 账号的 password 都是 ephemeral (token_urlsafe(16) → 至少 16 chars)
    for username, password, role in auth.created:
        if username == "admin":
            # admin 用 env 提供的 AdminPw_test (12 chars)
            assert password == "AdminPw_test", f"admin should use env password"
        else:
            assert len(password) >= 16, f"{username}: ephemeral too short: {len(password)}"
    print(f"  All 11 accounts created with ephemeral passwords in IMDF_TEST_MODE=1")


# ── TEST 13: rbac_test.py 也用 env 解析 (P12-B1) ───────────────────────
def test_rbac_test_uses_env():
    """P12-B1: scripts/rbac_test.py 必须用 ENV: 占位符, 不能硬编码密码。"""
    rbac_test = _BACKEND.parent / "scripts" / "rbac_test.py"
    assert rbac_test.exists()
    text = rbac_test.read_text(encoding="utf-8")
    # 必须用 ENV:<VARNAME> 占位符
    assert "ENV:ADMIN_INITIAL_PASSWORD" in text
    assert "ENV:PROD_LEAD_PASSWORD" in text
    # 必须不硬编码 Admin@2026!
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # 历史叙述允许
        if any(kw in line for kw in ["removed", "硬编码", "硬编", "弃用", "deprecat", "legacy"]):
            continue
        assert '"Admin@2026!"' not in line, f"rbac_test.py hardcodes Admin@2026!: {line}"
        assert "'Admin@2026!'" not in line, f"rbac_test.py hardcodes Admin@2026!: {line}"


# ── TEST 14: .bat 脚本不再显示密码 (P12-B1) ────────────────────────────
def test_batch_scripts_no_password():
    """P12-B1: 完整部署.bat / 启动.bat 不能显示 Admin@2026! 字面量。"""
    project_root = _BACKEND.parent
    for bat_name in ["完整部署.bat", "启动.bat"]:
        bat = project_root / bat_name
        if not bat.exists():
            continue
        text = bat.read_text(encoding="utf-8", errors="ignore")
        assert "Admin@2026!" not in text, (
            f"{bat_name} still contains 'Admin@2026!':\n{text}"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
