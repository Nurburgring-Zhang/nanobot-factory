"""
Nanobot Factory - 统一认证模块
"""

from .unified_auth import (
    UnifiedRole, ROLE_PERMISSIONS,
    AuthUser, PasswordManager, JWTManager,
    AuthDatabase, UnifiedAuthManager, LoginResult,
    get_unified_auth, reset_unified_auth,
    create_auth_dependency,
)
from .bruteforce import (
    BruteForceProtector, BruteForceConfig, ThrottleResult,
)
from .token_revocation import (
    TokenRevocationStore,
    get_revocation_store,
    reset_default_store,
)

__all__ = [
    'UnifiedRole', 'ROLE_PERMISSIONS',
    'AuthUser', 'PasswordManager', 'JWTManager',
    'AuthDatabase', 'UnifiedAuthManager', 'LoginResult',
    'get_unified_auth', 'reset_unified_auth',
    'create_auth_dependency',
    'BruteForceProtector', 'BruteForceConfig', 'ThrottleResult',
    'TokenRevocationStore',
    'get_revocation_store',
    'reset_default_store',
]
