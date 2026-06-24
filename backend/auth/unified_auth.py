#!/usr/bin/env python3
"""
Nanobot Factory - 统一认证系统 (Unified Auth)
文件: auth/unified_auth.py
功能: JWT + Argon2密码哈希 + SQLite持久化 + RBAC角色集成
兼容: 与 nanobot-factory 现有认证系统 (security/auth.py, core/rbac.py, core/multi_tenant.py) 完全兼容
作者: Hermes Agent
版本: v2.0.0
"""

import os
import sys
import json
import secrets
import hashlib
import hmac
import threading
import sqlite3
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

# JWT
try:
    import jwt
except ImportError:
    jwt = None
    print("[WARN] PyJWT not installed. Run: pip install PyJWT")

# Argon2 (优先) 或 fallback 到 hashlib pbkdf2
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError
    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False
    print("[WARN] argon2-cffi not installed, falling back to PBKDF2-SHA256. Run: pip install argon2-cffi")

logger = logging.getLogger("unified_auth")


# ============================================================================
# 角色枚举 — 与 core/rbac.py 保持兼容，并扩展 team_lead
# ============================================================================

class UnifiedRole(str, Enum):
    """统一角色定义，兼容 rbac.py 的 Role 和多租户的 UserRole"""
    ADMIN = "admin"                   # 超级管理员 — 全部权限
    TEAM_LEAD = "team_lead"           # 团队负责人 — 管理生产/众包团队
    REVIEWER = "reviewer"             # 审核员 — 审核标注/质检
    ANNOTATOR = "annotator"           # 标注员 — 执行标注/生产
    VIEWER = "viewer"                 # 查看者 — 只读/提需求

    # 以下为 rbac.py 兼容角色，默认映射到上方角色
    ORG_OWNER = "org_owner"           # → TEAM_LEAD
    ORG_ADMIN = "org_admin"           # → TEAM_LEAD
    PROJECT_MANAGER = "project_manager"  # → TEAM_LEAD
    OPERATOR = "operator"             # → REVIEWER
    USER = "user"                     # → ANNOTATOR
    GUEST = "guest"                   # → VIEWER

    @classmethod
    def normalize(cls, role_str: str) -> "UnifiedRole":
        """将任意角色字符串规范化为统一角色"""
        role_str = role_str.lower().strip()
        mapping = {
            "admin": cls.ADMIN,
            "super_admin": cls.ADMIN,
            "team_lead": cls.TEAM_LEAD,
            "org_owner": cls.TEAM_LEAD,
            "org_admin": cls.TEAM_LEAD,
            "project_manager": cls.TEAM_LEAD,
            "reviewer": cls.REVIEWER,
            "operator": cls.REVIEWER,
            "qc_lead": cls.REVIEWER,
            "annotator": cls.ANNOTATOR,
            "user": cls.ANNOTATOR,
            "viewer": cls.VIEWER,
            "guest": cls.VIEWER,
        }
        return mapping.get(role_str, cls.VIEWER)


# ============================================================================
# 权限定义
# ============================================================================

ROLE_PERMISSIONS: Dict[UnifiedRole, List[str]] = {
    UnifiedRole.ADMIN: [
        # 所有权限
        "user:create", "user:read", "user:update", "user:delete",
        "tool:execute", "tool:manage",
        "agent:create", "agent:execute", "agent:view",
        "file:read", "file:write", "file:delete",
        "exec:sql", "system:config", "secret:access",
        "generate:image", "generate:video", "generate:3d",
        "project:create", "project:manage", "project:view",
        "task:create", "task:assign", "task:review", "task:view",
        "requirement:create", "requirement:view",
        "delivery:review",
    ],
    UnifiedRole.TEAM_LEAD: [
        "user:read", "user:create",
        "tool:execute", "tool:manage",
        "agent:create", "agent:execute", "agent:view",
        "file:read", "file:write",
        "generate:image", "generate:video", "generate:3d",
        "project:create", "project:manage", "project:view",
        "task:create", "task:assign", "task:review", "task:view",
        "requirement:create", "requirement:view",
        "delivery:review",
    ],
    UnifiedRole.REVIEWER: [
        "user:read",
        "tool:execute",
        "agent:execute", "agent:view",
        "file:read", "file:write",
        "project:view",
        "task:review", "task:view",
        "requirement:view",
        "delivery:review",
    ],
    UnifiedRole.ANNOTATOR: [
        "user:read",
        "tool:execute",
        "agent:execute", "agent:view",
        "file:read", "file:write",
        "project:view",
        "task:view",
    ],
    UnifiedRole.VIEWER: [
        "user:read",
        "agent:view",
        "file:read",
        "project:view",
        "task:view",
        "requirement:create",   # 可以提需求
        "requirement:view",     # 可以查看进度
        "delivery:review",      # 可以审核交付
    ],
}


# ============================================================================
# 数据类
# ============================================================================

@dataclass
class AuthUser:
    """统一认证用户模型"""
    user_id: str
    username: str
    email: str
    role: str  # UnifiedRole value
    password_hash: str = ""
    password_salt: str = ""    # argon2不需要salt（内置），pbkdf2需要
    hash_method: str = "argon2"  # "argon2" 或 "pbkdf2"
    is_active: bool = True
    is_verified: bool = True
    display_name: str = ""
    team: str = ""              # "production" | "crowdsource" | "client"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    last_login: Optional[str] = None
    login_count: int = 0

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "display_name": self.display_name,
            "team": self.team,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "login_count": self.login_count,
        }


# ============================================================================
# 密码管理器 (Argon2 优先，PBKDF2 备用)
# ============================================================================

class PasswordManager:
    """密码哈希与验证 — Argon2id 优先，兼容 PBKDF2"""

    def __init__(self):
        if ARGON2_AVAILABLE:
            self._argon2 = PasswordHasher(
                time_cost=3,        # 迭代次数
                memory_cost=65536,  # 64 MB
                parallelism=4,      # 并行度
                hash_len=32,        # 哈希输出长度
                salt_len=16,        # salt长度（内置）
            )
        else:
            self._argon2 = None

    def hash_password(self, password: str) -> Tuple[str, str, str]:
        """
        哈希密码
        Returns: (hash_string, salt_string, method)
        - argon2: hash_string 包含完整哈希 (含内置salt), salt="" , method="argon2"
        - pbkdf2: hash_string=hex, salt=hex, method="pbkdf2"
        """
        if self._argon2:
            hash_str = self._argon2.hash(password)
            return hash_str, "", "argon2"
        else:
            salt = secrets.token_hex(32)
            hashed = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            )
            return hashed.hex(), salt, "pbkdf2"

    def verify_password(self, password: str, hash_str: str, salt: str = "", method: str = "argon2") -> bool:
        """验证密码"""
        if method == "argon2" or (method == "" and self._argon2 and salt == ""):
            if not self._argon2:
                # argon2不可用但存储的是argon2哈希 -> 无法验证
                logger.error("argon2 not available, cannot verify argon2 hash")
                return False
            try:
                return self._argon2.verify(hash_str, password)
            except (VerifyMismatchError, VerificationError):
                return False
        elif method == "pbkdf2":
            computed, _ = self._hash_pbkdf2_only(password, salt)
            return hmac.compare_digest(computed.hex(), hash_str)
        else:
            # 未知方法，尝试 argon2 然后 pbkdf2
            if self._argon2:
                try:
                    return self._argon2.verify(hash_str, password)
                except Exception:
                    pass
            if salt:
                try:
                    computed, _ = self._hash_pbkdf2_only(password, salt)
                    return hmac.compare_digest(computed.hex(), hash_str)
                except Exception:
                    return False
            return False

    @staticmethod
    def _hash_pbkdf2_only(password: str, salt: str) -> Tuple[bytes, str]:
        hashed = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return hashed, salt

    @staticmethod
    def needs_rehash(password: str, hash_str: str, method: str = "pbkdf2") -> bool:
        """检查是否需要用 argon2 重新哈希"""
        return ARGON2_AVAILABLE and method == "pbkdf2"


# ============================================================================
# JWT 管理器
# ============================================================================

class JWTManager:
    """JWT 令牌管理"""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expiry = 3600      # 1小时
        self.refresh_token_expiry = 86400 * 7  # 7天

    def create_access_token(self, user_id: str, username: str, role: str,
                            permissions: List[str] = None, expiry: int = None) -> str:
        """创建访问令牌"""
        if expiry is None:
            expiry = self.access_token_expiry
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        payload = {
            'sub': user_id,
            'username': username,
            'role': role,
            'permissions': permissions or [],
            'type': 'access',
            'iat': now,
            'exp': now + timedelta(seconds=expiry),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: str, expiry: int = None) -> str:
        """创建刷新令牌"""
        if expiry is None:
            expiry = self.refresh_token_expiry
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        payload = {
            'sub': user_id,
            'type': 'refresh',
            'iat': now,
            'exp': now + timedelta(seconds=expiry),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str, token_type: str = None) -> Optional[Dict[str, Any]]:
        """验证令牌"""
        if not jwt:
            logger.error("PyJWT not installed")
            return None
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if token_type and payload.get('type') != token_type:
                logger.warning(f"Token type mismatch: expected {token_type}")
                return None
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token无效: {e}")
            return None

    def decode_token_unsafe(self, token: str) -> Optional[Dict[str, Any]]:
        """不验证过期、仅解码 payload（用于调试）"""
        if not jwt:
            return None
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm],
                             options={"verify_exp": False})
        except Exception:
            return None


# ============================================================================
# SQLite 持久化存储
# ============================================================================

class AuthDatabase:
    """认证系统的 SQLite 持久化存储"""

    def __init__(self, db_path: str = ""):
        if not db_path:
            base = os.environ.get(
                "DATA_DIR",
                os.path.join(os.path.dirname(__file__), "..", "data")
            )
            os.makedirs(base, exist_ok=True)
            db_path = os.path.join(base, "unified_auth.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS auth_users (
                        user_id     TEXT PRIMARY KEY,
                        username    TEXT NOT NULL UNIQUE,
                        email       TEXT NOT NULL DEFAULT '',
                        role        TEXT NOT NULL DEFAULT 'viewer',
                        password_hash TEXT NOT NULL DEFAULT '',
                        password_salt TEXT NOT NULL DEFAULT '',
                        hash_method TEXT NOT NULL DEFAULT 'argon2',
                        is_active   INTEGER NOT NULL DEFAULT 1,
                        is_verified INTEGER NOT NULL DEFAULT 1,
                        display_name TEXT NOT NULL DEFAULT '',
                        team        TEXT NOT NULL DEFAULT '',
                        metadata    TEXT NOT NULL DEFAULT '{}',
                        created_at  TEXT NOT NULL DEFAULT '',
                        last_login  TEXT,
                        login_count INTEGER NOT NULL DEFAULT 0
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS auth_sessions (
                        session_id  TEXT PRIMARY KEY,
                        user_id     TEXT NOT NULL,
                        token_hash  TEXT NOT NULL,
                        token_type  TEXT NOT NULL DEFAULT 'access',
                        expires_at  TEXT NOT NULL,
                        created_at  TEXT NOT NULL DEFAULT '',
                        ip_address  TEXT,
                        user_agent  TEXT,
                        is_valid    INTEGER NOT NULL DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES auth_users(user_id)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS auth_audit_log (
                        log_id      TEXT PRIMARY KEY,
                        user_id     TEXT,
                        action      TEXT NOT NULL,
                        resource    TEXT NOT NULL DEFAULT 'auth',
                        result      TEXT NOT NULL DEFAULT 'success',
                        ip_address  TEXT,
                        details     TEXT NOT NULL DEFAULT '{}',
                        timestamp   TEXT NOT NULL DEFAULT '',
                        FOREIGN KEY (user_id) REFERENCES auth_users(user_id)
                    )
                """)
                # 索引
                conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_users_username ON auth_users(username)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_users_role ON auth_users(role)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_audit_user ON auth_audit_log(user_id)")
                conn.commit()
            finally:
                conn.close()

    # ---- 用户 CRUD ----

    def insert_user(self, user: AuthUser) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO auth_users
                    (user_id, username, email, role, password_hash, password_salt,
                     hash_method, is_active, is_verified, display_name, team,
                     metadata, created_at, last_login, login_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user.user_id, user.username, user.email, user.role,
                    user.password_hash, user.password_salt, user.hash_method,
                    1 if user.is_active else 0, 1 if user.is_verified else 0,
                    user.display_name, user.team,
                    json.dumps(user.metadata, ensure_ascii=False),
                    user.created_at, user.last_login, user.login_count
                ))
                conn.commit()
                return True
            except sqlite3.IntegrityError as e:
                logger.error(f"Insert user failed: {e}")
                return False
            finally:
                conn.close()

    def get_user_by_username(self, username: str) -> Optional[AuthUser]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM auth_users WHERE username = ?", (username,)
                ).fetchone()
                if row:
                    return self._row_to_user(dict(row))
                return None
            finally:
                conn.close()

    def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM auth_users WHERE user_id = ?", (user_id,)
                ).fetchone()
                if row:
                    return self._row_to_user(dict(row))
                return None
            finally:
                conn.close()

    def list_users(self, role: str = None, team: str = None,
                   is_active: bool = None, limit: int = 200) -> List[AuthUser]:
        conds = []
        params = []
        if role:
            conds.append("role = ?")
            params.append(role)
        if team:
            conds.append("team = ?")
            params.append(team)
        if is_active is not None:
            conds.append("is_active = ?")
            params.append(1 if is_active else 0)
        # Safe concatenation: WHERE clause built from parameterized conditions
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM auth_users " + where + " ORDER BY created_at DESC LIMIT ?",
                    params + [limit]
                ).fetchall()
                return [self._row_to_user(dict(r)) for r in rows]
            finally:
                conn.close()

    def update_user(self, user_id: str, updates: dict) -> bool:
        allowed = {"email", "role", "is_active", "is_verified", "display_name",
                   "team", "metadata", "last_login", "login_count",
                   "password_hash", "password_salt", "hash_method"}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return False
        set_clause = ", ".join(k + " = ?" for k in filtered)
        values = list(filtered.values()) + [user_id]
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    f"UPDATE auth_users SET {set_clause} WHERE user_id = ?",
                    values
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def delete_user(self, user_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM auth_users WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
                conn.commit()
                return True
            finally:
                conn.close()

    def user_exists(self, username: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT 1 FROM auth_users WHERE username = ?", (username,)
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def count_users(self) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT COUNT(*) as cnt FROM auth_users").fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    @staticmethod
    def _row_to_user(row: dict) -> AuthUser:
        try:
            metadata = json.loads(row.get("metadata", "{}"))
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        return AuthUser(
            user_id=row.get("user_id", ""),
            username=row.get("username", ""),
            email=row.get("email", ""),
            role=row.get("role", "viewer"),
            password_hash=row.get("password_hash", ""),
            password_salt=row.get("password_salt", ""),
            hash_method=row.get("hash_method", "argon2"),
            is_active=bool(row.get("is_active", 1)),
            is_verified=bool(row.get("is_verified", 1)),
            display_name=row.get("display_name", ""),
            team=row.get("team", ""),
            metadata=metadata,
            created_at=row.get("created_at", ""),
            last_login=row.get("last_login"),
            login_count=row.get("login_count", 0),
        )


# ============================================================================
# 统一认证管理器
# ============================================================================

class UnifiedAuthManager:
    """
    统一认证管理器
    功能: 用户注册/登录/令牌管理/权限检查/审计日志
    兼容: security/auth.py 的 AuthManager 接口
    """

    def __init__(self, jwt_secret: str = "", db_path: str = ""):
        # JWT 密钥
        self.jwt_secret = jwt_secret or os.environ.get(
            "JWT_SECRET",
            secrets.token_hex(32)
        )
        self.jwt_manager = JWTManager(self.jwt_secret)
        self.password_manager = PasswordManager()
        self.db = AuthDatabase(db_path)

        # 启动时确保至少有一个 admin
        self._ensure_admin_exists()

    # ---- 初始化 ----

    def _ensure_admin_exists(self):
        """确保至少有一个管理员账户"""
        existing = self.db.get_user_by_username("admin")
        if not existing:
            self._create_user(
                username="admin",
                password="Admin@2026!",
                role=UnifiedRole.ADMIN.value,
                email="admin@nanobot.local",
                display_name="系统管理员",
                team="system",
                is_verified=True,
            )
            logger.info("Default admin account created: admin / Admin@2026!")

    def _create_user(self, username: str, password: str, role: str,
                     email: str = "", display_name: str = "", team: str = "",
                     is_verified: bool = True, metadata: dict = None) -> Optional[AuthUser]:
        """内部创建用户"""
        if self.db.user_exists(username):
            logger.warning(f"User already exists: {username}")
            return None

        user_id = f"u-{secrets.token_hex(8)}"
        hash_str, salt, method = self.password_manager.hash_password(password)

        user = AuthUser(
            user_id=user_id,
            username=username,
            email=email or f"{username}@nanobot.local",
            role=UnifiedRole.normalize(role).value,
            password_hash=hash_str,
            password_salt=salt,
            hash_method=method,
            is_active=True,
            is_verified=is_verified,
            display_name=display_name or username,
            team=team,
            metadata=metadata or {},
            created_at=datetime.now().isoformat(),
            login_count=0,
        )
        if self.db.insert_user(user):
            logger.info(f"User created: {username} (role={user.role}, team={team})")
            return user
        return None

    # ---- 公共 API ----

    def register_user(self, username: str, password: str, role: str = "viewer",
                      email: str = "", display_name: str = "", team: str = "",
                      metadata: dict = None) -> Optional[AuthUser]:
        """
        注册新用户
        Args:
            username: 用户名
            password: 明文密码
            role: 角色 (admin/team_lead/reviewer/annotator/viewer)
            email: 邮箱
            display_name: 显示名称
            team: 所属团队 (production/crowdsource/client)
            metadata: 额外元数据
        Returns:
            AuthUser 或 None (用户名已存在)
        """
        return self._create_user(
            username=username, password=password, role=role,
            email=email, display_name=display_name, team=team,
            metadata=metadata
        )

    def authenticate(self, username: str, password: str,
                     ip_address: str = None, user_agent: str = None) -> Optional[Dict[str, Any]]:
        """
        用户认证 → 返回 JWT token pair
        Returns:
            {"access_token": str, "refresh_token": str, "user": dict} 或 None
        """
        user = self.db.get_user_by_username(username)
        if not user:
            logger.warning(f"Authentication failed: user not found: {username}")
            self._audit("auth.failed", username=username, result="failed",
                        ip_address=ip_address, details={"reason": "user_not_found"})
            return None

        if not user.is_active:
            logger.warning(f"Authentication failed: user inactive: {username}")
            self._audit("auth.failed", user.user_id, "failed", ip_address,
                        details={"reason": "user_inactive"})
            return None

        if not self.password_manager.verify_password(
            password, user.password_hash, user.password_salt, user.hash_method
        ):
            logger.warning(f"Authentication failed: wrong password: {username}")
            self._audit("auth.failed", user.user_id, "failed", ip_address,
                        details={"reason": "wrong_password"})
            return None

        # 升级密码哈希 (pbkdf2 → argon2)
        if self.password_manager.needs_rehash(password, user.password_hash, user.hash_method):
            new_hash, _, new_method = self.password_manager.hash_password(password)
            self.db.update_user(user.user_id, {
                "password_hash": new_hash,
                "password_salt": "",
                "hash_method": new_method,
            })
            logger.info(f"Password upgraded to argon2 for user: {username}")

        # 更新登录信息
        now = datetime.now().isoformat()
        self.db.update_user(user.user_id, {
            "last_login": now,
            "login_count": user.login_count + 1,
        })

        # 生成令牌
        permissions = ROLE_PERMISSIONS.get(UnifiedRole(user.role), [])
        access_token = self.jwt_manager.create_access_token(
            user.user_id, user.username, user.role, permissions
        )
        refresh_token = self.jwt_manager.create_refresh_token(user.user_id)

        self._audit("auth.success", user.user_id, "success", ip_address)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.jwt_manager.access_token_expiry,
            "user": user.to_dict(),
        }

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证 access token"""
        return self.jwt_manager.verify_token(token, token_type="access")

    def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """使用 refresh token 获取新的 access token"""
        payload = self.jwt_manager.verify_token(refresh_token, token_type="refresh")
        if not payload:
            return None
        user_id = payload.get("sub")
        user = self.db.get_user_by_id(user_id)
        if not user or not user.is_active:
            return None
        permissions = ROLE_PERMISSIONS.get(UnifiedRole(user.role), [])
        access_token = self.jwt_manager.create_access_token(
            user.user_id, user.username, user.role, permissions
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": self.jwt_manager.access_token_expiry,
        }

    def get_user(self, user_id: str = None, username: str = None) -> Optional[AuthUser]:
        """获取用户信息"""
        if user_id:
            return self.db.get_user_by_id(user_id)
        if username:
            return self.db.get_user_by_username(username)
        return None

    def list_users(self, role: str = None, team: str = None,
                   is_active: bool = None) -> List[Dict[str, Any]]:
        """列出用户"""
        users = self.db.list_users(role=role, team=team, is_active=is_active)
        return [u.to_dict() for u in users]

    def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        return self.db.delete_user(user_id)

    def check_permission(self, user_id: str, required_permission: str) -> bool:
        """检查用户是否有某权限"""
        user = self.db.get_user_by_id(user_id)
        if not user or not user.is_active:
            return False
        permissions = ROLE_PERMISSIONS.get(UnifiedRole(user.role), [])
        # admin 拥有所有权限
        if user.role == UnifiedRole.ADMIN.value:
            return True
        return required_permission in permissions

    def get_user_permissions(self, user_id: str) -> List[str]:
        """获取用户的所有权限"""
        user = self.db.get_user_by_id(user_id)
        if not user:
            return []
        return ROLE_PERMISSIONS.get(UnifiedRole(user.role), [])

    def change_password(self, user_id: str, old_password: str,
                        new_password: str) -> bool:
        """修改密码"""
        user = self.db.get_user_by_id(user_id)
        if not user:
            return False
        if not self.password_manager.verify_password(
            old_password, user.password_hash, user.password_salt, user.hash_method
        ):
            return False
        new_hash, new_salt, new_method = self.password_manager.hash_password(new_password)
        return self.db.update_user(user.user_id, {
            "password_hash": new_hash,
            "password_salt": new_salt,
            "hash_method": new_method,
        })

    # ---- 内部 ----

    def _audit(self, action: str, user_id: str = "", result: str = "success",
               ip_address: str = None, details: dict = None,
               username: str = ""):
        """记录审计日志"""
        log_id = f"log_{secrets.token_hex(8)}"
        with self.db._lock:
            conn = self.db._get_conn()
            try:
                conn.execute("""
                    INSERT INTO auth_audit_log
                    (log_id, user_id, action, resource, result, ip_address, details, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_id,
                    user_id or username,
                    action,
                    "auth",
                    result,
                    ip_address,
                    json.dumps(details or {}, ensure_ascii=False),
                    datetime.now().isoformat(),
                ))
                conn.commit()
            except Exception as e:
                logger.error(f"Audit log failed: {e}")
            finally:
                conn.close()

    def get_audit_logs(self, user_id: str = None, limit: int = 100) -> List[dict]:
        """获取审计日志"""
        with self.db._lock:
            conn = self.db._get_conn()
            try:
                if user_id:
                    rows = conn.execute(
                        "SELECT * FROM auth_audit_log WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                        (user_id, limit)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM auth_audit_log ORDER BY timestamp DESC LIMIT ?",
                        (limit,)
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()


# ============================================================================
# 全局单例
# ============================================================================

_auth_instance: Optional[UnifiedAuthManager] = None
_auth_lock = threading.Lock()


def get_unified_auth(jwt_secret: str = "", db_path: str = "") -> UnifiedAuthManager:
    """获取统一认证管理器单例"""
    global _auth_instance
    if _auth_instance is None:
        with _auth_lock:
            if _auth_instance is None:
                _auth_instance = UnifiedAuthManager(
                    jwt_secret=jwt_secret,
                    db_path=db_path,
                )
    return _auth_instance


def reset_unified_auth():
    """重置单例（主要用于测试）"""
    global _auth_instance
    with _auth_lock:
        _auth_instance = None


# ============================================================================
# FastAPI 兼容的路由辅助
# ============================================================================

def create_auth_dependency(auth: UnifiedAuthManager = None):
    """
    创建 FastAPI 认证依赖
    Usage:
        from auth.unified_auth import create_auth_dependency, get_unified_auth
        auth = get_unified_auth()
        require_auth = create_auth_dependency(auth)

        @router.get("/protected")
        async def protected_route(current_user = Depends(require_auth)):
            return {"user": current_user}
    """
    from fastapi import Depends, HTTPException, status
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

    security = HTTPBearer()
    _auth = auth or get_unified_auth()

    async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> Dict[str, Any]:
        token = credentials.credentials
        payload = _auth.verify_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        user = _auth.get_user(user_id=payload.get("sub"))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return user.to_dict()

    return get_current_user


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    'UnifiedRole', 'ROLE_PERMISSIONS',
    'AuthUser', 'PasswordManager', 'JWTManager',
    'AuthDatabase', 'UnifiedAuthManager',
    'get_unified_auth', 'reset_unified_auth',
    'create_auth_dependency',
]
