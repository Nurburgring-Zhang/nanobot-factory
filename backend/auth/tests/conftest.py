"""
Pytest configuration for backend/auth/tests/

Path setup so tests can import ``auth`` and ``security`` from sibling packages.
"""
import os
import sys
from pathlib import Path

import pytest

# Add backend/ (parent of auth/) to sys.path so ``from auth.unified_auth
# import ...`` and ``from security.auth import ...`` work consistently.
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True)
def _auth_test_env(monkeypatch):
    """每个 test 前: 设置强 JWT_SECRET + ADMIN_INITIAL_PASSWORD.

    P11-B-1: 强 JWT_SECRET 让 common.auth._secret() 不抛 ValueError。
    ADMIN_INITIAL_PASSWORD 让 UnifiedAuthManager 启动不要求手工设 env
    (P11-D-1 引入的强约束), 让 bruteforce 集成测试也能跑起来。

    单元测试如果需要覆盖 _secret() 的边界 (短 secret raise), 在自己的
    test body 里用 ``monkeypatch.setenv("JWT_SECRET", "x")`` 覆盖即可。
    """
    monkeypatch.setenv("JWT_SECRET", "x" * 64)
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "TestAdmin@2026!StrongSecret32chars")
    yield
