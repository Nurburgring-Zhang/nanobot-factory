"""Standalone verification of admin password hardening."""
import os
import sys
import tempfile

backend = r"D:\Hermes\生产平台\nanobot-factory\backend"
sys.path.insert(0, backend)


def test_init_accounts_fail_fast():
    """Missing ADMIN_INITIAL_PASSWORD + no test mode → RuntimeError."""
    os.environ.pop("ADMIN_INITIAL_PASSWORD", None)
    os.environ.pop("IMDF_TEST_MODE", None)
    from scripts.init_accounts import _resolve_admin_password
    try:
        pw = _resolve_admin_password()
        print(f"  [FAIL] got password: {pw}")
        return False
    except RuntimeError as e:
        msg = str(e)
        ok_env = "ADMIN_INITIAL_PASSWORD" in msg
        ok_help = "secrets" in msg.lower() or ".env" in msg.lower()
        ok_legacy = "Admin@2026" in msg  # Mentions the legacy removal
        print(f"  [PASS] RuntimeError raised, env_mentioned={ok_env}, remediation={ok_help}, legacy_mentioned={ok_legacy}")
        return ok_env and ok_help


def test_init_accounts_env_injection():
    """ADMIN_INITIAL_PASSWORD set → returned."""
    os.environ["ADMIN_INITIAL_PASSWORD"] = "TestInitPassword_abc123def456"
    from scripts.init_accounts import _resolve_admin_password
    pw = _resolve_admin_password()
    ok = pw == "TestInitPassword_abc123def456"
    print(f"  [{'PASS' if ok else 'FAIL'}] env injection: returned={pw!r}")
    return ok


def test_unified_auth_fail_fast():
    """UnifiedAuthManager.__init__ raises AdminConfigError when env missing."""
    os.environ.pop("ADMIN_INITIAL_PASSWORD", None)
    os.environ.pop("IMDF_TEST_MODE", None)
    from auth.unified_auth import UnifiedAuthManager, AdminConfigError
    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "auth.db")
        try:
            UnifiedAuthManager(db_path=db)
            print("  [FAIL] no error raised")
            return False
        except AdminConfigError as e:
            msg = str(e)
            ok_env = "ADMIN_INITIAL_PASSWORD" in msg
            ok_help = "secrets" in msg.lower() or ".env" in msg.lower()
            print(f"  [PASS] AdminConfigError raised, env={ok_env}, remediation={ok_help}")
            return ok_env and ok_help


def test_unified_auth_env_injection():
    """Admin account uses env password."""
    os.environ["ADMIN_INITIAL_PASSWORD"] = "TestEnvPw_xyz789"
    from auth.unified_auth import UnifiedAuthManager
    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "auth.db")
        mgr = UnifiedAuthManager(db_path=db)
        admin = mgr.get_user(username="admin")
        if admin is None:
            print("  [FAIL] admin not created")
            return False
        result = mgr.login("admin", "TestEnvPw_xyz789")
        ok = result.status == "success"
        print(f"  [{'PASS' if ok else 'FAIL'}] admin created from env, login={result.status}")
        return ok


def test_test_mode_ephemeral():
    """IMDF_TEST_MODE=1 + no env → ephemeral password."""
    os.environ.pop("ADMIN_INITIAL_PASSWORD", None)
    os.environ["IMDF_TEST_MODE"] = "1"
    from auth.unified_auth import UnifiedAuthManager
    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "auth.db")
        mgr = UnifiedAuthManager(db_path=db)
        admin = mgr.get_user(username="admin")
        if admin is None:
            print("  [FAIL] admin not created")
            return False
        print(f"  [PASS] test mode created ephemeral admin, role={admin.role}")
        return True


def main():
    print("=== Admin Password Hardening Verification ===\n")
    results = []
    print("[1] UnifiedAuthManager fail-fast:")
    results.append(test_unified_auth_fail_fast())
    print("\n[2] UnifiedAuthManager env injection:")
    results.append(test_unified_auth_env_injection())
    print("\n[3] init_accounts fail-fast:")
    results.append(test_init_accounts_fail_fast())
    print("\n[4] init_accounts env injection:")
    results.append(test_init_accounts_env_injection())
    print("\n[5] IMDF_TEST_MODE ephemeral:")
    results.append(test_test_mode_ephemeral())
    passed = sum(results)
    total = len(results)
    print(f"\n=== Result: {passed}/{total} PASS ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())