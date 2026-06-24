"""
Nanobot Factory - 统一认证模块
"""

from .unified_auth import (
    UnifiedRole, ROLE_PERMISSIONS,
    AuthUser, PasswordManager, JWTManager,
    AuthDatabase, UnifiedAuthManager,
    get_unified_auth, reset_unified_auth,
    create_auth_dependency,
)

__all__ = [
    'UnifiedRole', 'ROLE_PERMISSIONS',
    'AuthUser', 'PasswordManager', 'JWTManager',
    'AuthDatabase', 'UnifiedAuthManager',
    'get_unified_auth', 'reset_unified_auth',
    'create_auth_dependency',
]
