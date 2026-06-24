"""
NanoBot Factory - 安全认证与访问控制系统
文件: security/auth.py
功能: 身份认证、访问控制、日志审计
作者: Matrix Agent
版本: v1.0.0
"""

import hashlib
import hmac
import secrets
import time
import jwt
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


# ==================== 枚举类型 ====================

class AuthProvider(Enum):
    """认证提供者"""
    LOCAL = "local"
    LDAP = "ldap"
    OAUTH2 = "oauth2"
    SAML = "saml"
    API_KEY = "api_key"


class UserRole(Enum):
    """用户角色"""
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"
    GUEST = "guest"


class Permission(Enum):
    """权限类型"""
    # 用户管理
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"

    # 工具调用
    TOOL_EXECUTE = "tool:execute"
    TOOL_MANAGE = "tool:manage"

    # Agent操作
    AGENT_CREATE = "agent:create"
    AGENT_EXECUTE = "agent:execute"
    AGENT_VIEW = "agent:view"

    # 文件操作
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    FILE_DELETE = "file:delete"

    # 敏感操作
    EXECUTE_SQL = "exec:sql"
    SYSTEM_CONFIG = "system:config"
    SECRET_ACCESS = "secret:access"

    # 生成操作
    GENERATE_IMAGE = "generate:image"
    GENERATE_VIDEO = "generate:video"
    GENERATE_3D = "generate:3d"


# ==================== 数据类 ====================

@dataclass
class User:
    """用户"""
    user_id: str
    username: str
    email: str
    role: UserRole
    permissions: Set[Permission] = field(default_factory=set)
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class APIKey:
    """API密钥"""
    key_id: str
    user_id: str
    key_hash: str
    name: str
    permissions: Set[Permission] = field(default_factory=set)
    is_active: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    rate_limit: int = 100  # 每分钟请求数


@dataclass
class Session:
    """会话"""
    session_id: str
    user_id: str
    token: str
    expires_at: datetime
    created_at: datetime = field(default_factory=datetime.now)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_valid: bool = True


@dataclass
class AuditLog:
    """审计日志"""
    log_id: str
    user_id: str
    action: str
    resource: str
    result: str
    ip_address: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


# ==================== 密码管理器 ====================

class PasswordManager:
    """密码哈希与验证"""

    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> tuple:
        """哈希密码"""
        if salt is None:
            salt = secrets.token_hex(32)

        hashed = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return hashed.hex(), salt

    @staticmethod
    def verify_password(password: str, hashed: str, salt: str) -> bool:
        """验证密码"""
        computed_hash, _ = PasswordManager.hash_password(password, salt)
        return hmac.compare_digest(computed_hash, hashed)


# ==================== JWT管理器 ====================

class JWTManager:
    """JWT令牌管理"""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.default_expiry = 3600  # 1小时

    def create_token(self, user_id: str, permissions: List[str], expiry: int = None) -> str:
        """创建令牌"""
        if expiry is None:
            expiry = self.default_expiry

        payload = {
            'user_id': user_id,
            'permissions': [p.value for p in permissions],
            'exp': datetime.utcnow() + timedelta(seconds=expiry),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token无效: {e}")
            return None


# ==================== 权限管理器 ====================

class PermissionManager:
    """权限管理"""

    ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
        UserRole.ADMIN: set(Permission),
        UserRole.OPERATOR: {
            Permission.USER_READ,
            Permission.TOOL_EXECUTE,
            Permission.AGENT_CREATE,
            Permission.AGENT_EXECUTE,
            Permission.AGENT_VIEW,
            Permission.FILE_READ,
            Permission.FILE_WRITE,
            Permission.GENERATE_IMAGE,
            Permission.GENERATE_VIDEO,
            Permission.GENERATE_3D,
        },
        UserRole.USER: {
            Permission.USER_READ,
            Permission.TOOL_EXECUTE,
            Permission.AGENT_EXECUTE,
            Permission.AGENT_VIEW,
            Permission.FILE_READ,
            Permission.GENERATE_IMAGE,
        },
        UserRole.GUEST: {
            Permission.AGENT_VIEW,
            Permission.FILE_READ,
        }
    }

    @classmethod
    def get_role_permissions(cls, role: UserRole) -> Set[Permission]:
        """获取角色默认权限"""
        return cls.ROLE_PERMISSIONS.get(role, set())


# ==================== 认证管理器 ====================

class AuthManager:
    """认证管理器"""

    def __init__(self, jwt_secret: str):
        self.jwt_manager = JWTManager(jwt_secret)
        self.password_manager = PasswordManager()

        self.users: Dict[str, User] = {}
        self.api_keys: Dict[str, APIKey] = {}
        self.sessions: Dict[str, Session] = {}
        self.audit_logs: List[AuditLog] = []

        self._init_default_admin()

    def _init_default_admin(self):
        """初始化默认管理员"""
        if "admin" not in self.users:
            hashed, salt = self.password_manager.hash_password("admin123")
            admin = User(
                user_id="admin_001",
                username="admin",
                email="admin@nanobot.local",
                role=UserRole.ADMIN,
                permissions=PermissionManager.get_role_permissions(UserRole.ADMIN),
                is_active=True,
                is_verified=True,
                metadata={'password_salt': salt, 'password_hash': hashed}
            )
            self.users["admin"] = admin
            logger.info("默认管理员账户已创建")

    def register_user(self, username: str, email: str, password: str, role: UserRole = UserRole.USER) -> str:
        """注册用户"""
        if username in self.users:
            raise ValueError("用户名已存在")

        hashed, salt = self.password_manager.hash_password(password)
        user_id = f"user_{len(self.users) + 1:03d}"

        user = User(
            user_id=user_id,
            username=username,
            email=email,
            role=role,
            permissions=PermissionManager.get_role_permissions(role),
            metadata={'password_salt': salt, 'password_hash': hashed}
        )
        self.users[username] = user

        self._audit("user.register", user_id, "success")
        return user_id

    def authenticate(self, username: str, password: str, ip: str = None) -> Optional[str]:
        """用户认证"""
        user = self.users.get(username)
        if not user or not user.is_active:
            self._audit("auth.failed", username, "failed", ip)
            return None

        salt = user.metadata.get('password_salt')
        hashed = user.metadata.get('password_hash')

        if not self.password_manager.verify_password(password, hashed, salt):
            self._audit("auth.failed", user.user_id, "failed", ip)
            return None

        user.last_login = datetime.now()
        token = self.jwt_manager.create_token(user.user_id, list(user.permissions))

        session = Session(
            session_id=secrets.token_hex(16),
            user_id=user.user_id,
            token=token,
            expires_at=datetime.now() + timedelta(hours=24),
            ip_address=ip
        )
        self.sessions[session.session_id] = session

        self._audit("auth.success", user.user_id, "success", ip)
        return token

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证令牌"""
        return self.jwt_manager.verify_token(token)

    def create_api_key(self, user_id: str, name: str, permissions: List[Permission] = None, expiry_days: int = 365) -> str:
        """创建API密钥"""
        raw_key = f"nb_{secrets.token_hex(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_id= f"key_{len(self.api_keys) + 1:03d}"

        if permissions is None:
            user = self._find_user_by_id(user_id)
            permissions = list(user.permissions) if user else []

        api_key = APIKey(
            key_id=key_id,
            user_id=user_id,
            key_hash=key_hash,
            name=name,
            permissions=set(permissions),
            expires_at=datetime.now() + timedelta(days=expiry_days)
        )
        self.api_keys[raw_key] = api_key

        self._audit("apikey.create", user_id, "success")
        return raw_key

    def verify_api_key(self, raw_key: str) -> Optional[APIKey]:
        """验证API密钥"""
        api_key = self.api_keys.get(raw_key)
        if not api_key:
            return None

        if not api_key.is_active:
            return None

        if api_key.expires_at and api_key.expires_at < datetime.now():
            return None

        api_key.last_used = datetime.now()
        return api_key

    def check_permission(self, user_id: str, permission: Permission) -> bool:
        """检查权限"""
        user = self._find_user_by_id(user_id)
        if not user:
            return False
        return permission in user.permissions or Permission.ADMIN in user.permissions

    def _find_user_by_id(self, user_id: str) -> Optional[User]:
        """通过ID查找用户"""
        for user in self.users.values():
            if user.user_id == user_id:
                return user
        return None

    def _audit(self, action: str, user_id: str, result: str, ip: str = None):
        """记录审计日志"""
        log = AuditLog(
            log_id=f"log_{len(self.audit_logs) + 1:06d}",
            user_id=user_id,
            action=action,
            resource="system",
            result=result,
            ip_address=ip
        )
        self.audit_logs.append(log)

    def get_audit_logs(self, user_id: str = None, limit: int = 100) -> List[AuditLog]:
        """获取审计日志"""
        logs = self.audit_logs
        if user_id:
            logs = [l for l in logs if l.user_id == user_id]
        return logs[-limit:]


# ==================== 访问控制 ====================

class AccessController:
    """访问控制器"""

    def __init__(self, auth_manager: AuthManager):
        self.auth_manager = auth_manager
        self.rate_limiter = RateLimiter(calls_per_minute=100, calls_per_hour=1000)

    def authorize(self, token: str, required_permission: Permission) -> bool:
        """授权检查"""
        payload = self.auth_manager.verify_token(token)
        if not payload:
            return False

        permissions = set(payload.get('permissions', []))
        return required_permission.value in permissions

    def rate_limit_check(self, key: str) -> bool:
        """速率限制检查"""
        return self.rate_limiter.check(key)


# ==================== 速率限制器 ====================

class RateLimiter:
    """速率限制器"""

    def __init__(self, calls_per_minute: int, calls_per_hour: int):
        self.calls_per_minute = calls_per_minute
        self.calls_per_hour = calls_per_hour
        self._minute_window: Dict[str, List[datetime]] = defaultdict(list)
        self._hour_window: Dict[str, List[datetime]] = defaultdict(list)

    def check(self, key: str) -> bool:
        """检查是否允许调用"""
        now = datetime.now()

        minute_ago = now - timedelta(minutes=1)
        self._minute_window[key] = [t for t in self._minute_window[key] if t > minute_ago]

        hour_ago = now - timedelta(hours=1)
        self._hour_window[key] = [t for t in self._hour_window[key] if t > hour_ago]

        if len(self._minute_window[key]) >= self.calls_per_minute:
            return False
        if len(self._hour_window[key]) >= self.calls_per_hour:
            return False

        self._minute_window[key].append(now)
        self._hour_window[key].append(now)
        return True


# ==================== 导出模块 ====================

__all__ = [
    'AuthProvider', 'UserRole', 'Permission',
    'User', 'APIKey', 'Session', 'AuditLog',
    'PasswordManager', 'JWTManager', 'PermissionManager',
    'AuthManager', 'AccessController', 'RateLimiter'
]
