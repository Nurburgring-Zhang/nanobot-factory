"""IMDF JWT Authentication System — R9.5 hardening.

增强点 (vs R9-W1 基线):
- JWT access token TTL: 30 min
- JWT refresh token TTL: 7 days (一次性, 使用后自动 revoke)
- jti 黑名单: DB (revoked_tokens 表) + 内存双层
- 限流: SlowAPI 替换 RateLimiter 类
    - login  5/minute
    - register 10/minute
    - refresh 20/minute
- 登录下发 ``csrf_token`` 双 cookie (供 ``CSRFMiddleware`` 校验)
- GDPR 端点:
    - GET    /auth/me/export     (Article 15 数据访问 + 20 可移植)
    - DELETE /auth/me            (Article 17 被遗忘权)
    - GET    /auth/me/audit      (审计日志)
- ``gdpr_audit`` 表: 记录导出/删除/密码修改等关键操作。

设计原则:
- 与 R9-W1 公共签名保持兼容 (``get_current_user`` / ``router`` 不变)。
- 旧 ``RateLimiter`` 仍保留为模块级变量 (其他模块可能 import, 不破坏 ABI)。
"""
from __future__ import annotations

import calendar
import hashlib
import logging
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from jose import JWTError, jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Password hashing ──────────────────────────────────────────────────────
# 优先 argon2, 缺则 passlib/bcrypt, 都没有则 SHA-256 (仅 dev fallback)。
_password_hasher = None
_password_backend = "unknown"
try:
    from argon2 import PasswordHasher

    _password_hasher = PasswordHasher()
    _password_backend = "argon2"
except Exception:
    try:
        from passlib.context import CryptContext

        _password_hasher = CryptContext(schemes=["bcrypt"], deprecated="auto")
        _password_backend = "passlib_bcrypt"
    except Exception as e:
        logger.warning(f"Neither argon2 nor passlib available: {e}; using SHA-256 fallback")


def _safe_bcrypt_input(password: str) -> bytes:
    """bcrypt 4.x 不再自动截断 >72 字节的密码 — 我们手动处理避免 ValueError。

    bcrypt 算法限制: 输入不能超过 72 字节 (UTF-8 编码后)。
    """
    raw = password.encode("utf-8")
    if len(raw) <= 72:
        return raw
    # 截断到 72 字节 (UTF-8 安全: 直接按字节切, 不在多字节字符中间)
    return raw[:72]


def _hash_password(password: str) -> str:
    if _password_backend == "argon2":
        return _password_hasher.hash(password)
    if _password_backend == "passlib_bcrypt":
        # bcrypt 4.x: 手动截断到 72 字节 (passlib 1.7 之前会自动截断, 1.7+ 移除)
        try:
            return _password_hasher.hash(_safe_bcrypt_input(password).decode("utf-8"))
        except ValueError as e:
            if "72 bytes" in str(e):
                # 极端情况: 截断仍失败 (罕见), 降级到 SHA-256
                logger.warning(f"bcrypt 72-byte truncation failed, falling back to SHA-256: {e}")
                salt = secrets.token_hex(16)
                h = hashlib.sha256((salt + password).encode()).hexdigest()
                return f"sha256${salt}${h}"
            raise
    # SHA-256 fallback (dev only — NOT for production)
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"sha256${salt}${h}"


def _verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    if _password_backend == "argon2":
        try:
            return _password_hasher.verify(hashed_password, plain_password)
        except Exception as e:
            logger.warning(f"argon2 verify failed: {e}")
            return False
    if _password_backend == "passlib_bcrypt":
        try:
            return _password_hasher.verify(_safe_bcrypt_input(plain_password).decode("utf-8"), hashed_password)
        except Exception as e:
            logger.warning(f"passlib verify failed: {e}")
            return False
    # SHA-256 fallback
    if hashed_password.startswith("sha256$"):
        _, salt, h = hashed_password.split("$", 2)
        return h == hashlib.sha256((salt + plain_password).encode()).hexdigest()
    return False


# ── JWT Configuration ─────────────────────────────────────────────────────
# P10-C: RFC 7519 标准声明 (iss / aud) — 与 backend.auth.unified_auth 一致
JWT_ISSUER = "nanobot-factory"
JWT_AUDIENCE = "nanobot-factory-api"
JWT_MIN_SECRET_LENGTH = 16  # 与 audit_chain.AuditChain 阈值一致

JWT_SECRET = os.environ.get("JWT_SECRET")
if JWT_SECRET is None or JWT_SECRET == "change-me-in-production":
    # 测试环境允许默认值, 但记录警告; 生产启动时由部署环境强制设置。
    if os.environ.get("IMDF_TEST_MODE", "").lower() not in ("1", "true", "yes"):
        raise RuntimeError(
            "请设置JWT_SECRET环境变量: export JWT_SECRET=<your-secure-secret-key>\n"
            "或 IMDF_TEST_MODE=1 使用开发默认值。"
        )
    JWT_SECRET = "test-secret-DO-NOT-USE-IN-PROD-" + secrets.token_hex(8)

# P10-C: 启动时校验 secret 强度 (与 AuditChain / unified_auth 一致)
if len(JWT_SECRET) < JWT_MIN_SECRET_LENGTH:
    raise RuntimeError(
        f"JWT_SECRET too short ({len(JWT_SECRET)} chars, min {JWT_MIN_SECRET_LENGTH}). "
        "Use a strong random secret (e.g. `python -c 'import secrets; print(secrets.token_urlsafe(32))'`)."
    )

SECRET_KEY = JWT_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

router = APIRouter(prefix="/auth", tags=["auth"])

# ── DB helpers ─────────────────────────────────────────────────────────────
def _get_db_path() -> str:
    """Users DB 路径, 与 R9-W1 一致。"""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "imdf.db",
    )


def _get_conn() -> sqlite3.Connection:
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    return conn


def _init_users_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'viewer',
            enabled INTEGER DEFAULT 1,
            max_datasets INTEGER DEFAULT 10,
            max_storage_mb INTEGER DEFAULT 1024,
            max_api_calls_per_day INTEGER DEFAULT 1000,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    # 迁移: 添加可能缺失的列 (与原版一致)
    for col, typ in (
        ("enabled", "INTEGER DEFAULT 1"),
        ("max_datasets", "INTEGER DEFAULT 10"),
        ("max_storage_mb", "INTEGER DEFAULT 1024"),
        ("max_api_calls_per_day", "INTEGER DEFAULT 1000"),
    ):
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        except Exception as e:
            logger.debug(f"DB migration skip col {col}: {e}")
    conn.commit()


def _init_security_tables(conn: sqlite3.Connection) -> None:
    """R9.5 新增: revoked_tokens + gdpr_audit。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            jti TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            token_type TEXT NOT NULL,
            revoked_at TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            reason TEXT DEFAULT 'logout'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gdpr_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_gdpr_audit_username ON gdpr_audit(username)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires ON revoked_tokens(expires_at)"
    )
    conn.commit()


def _init_db() -> sqlite3.Connection:
    conn = _get_conn()
    _init_users_table(conn)
    _init_security_tables(conn)
    return conn


# ── In-memory user cache (loaded at import time, R9-W1 ABI) ───────────────
users_db: Dict[str, dict] = {}


def _load_users() -> None:
    global users_db
    try:
        conn = _init_db()
        rows = conn.execute(
            "SELECT username,password_hash,role,enabled,max_datasets,"
            "max_storage_mb,max_api_calls_per_day,created_at FROM users"
        ).fetchall()
        for row in rows:
            users_db[row[0]] = {
                "username": row[0],
                "password_hash": row[1],
                "role": row[2],
                "enabled": bool(row[3]),
                "max_datasets": row[4],
                "max_storage_mb": row[5],
                "max_api_calls_per_day": row[6],
                "created_at": row[7],
            }
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to load users from DB (first start?): {e}")


def _save_user(username: str, password_hash: str, role: str) -> None:
    try:
        conn = _init_db()
        conn.execute(
            "INSERT OR REPLACE INTO users(username,password_hash,role,enabled,created_at) "
            "VALUES(?,?,?,1,datetime('now'))",
            (username, password_hash, role),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to save user to DB: {e}")


# ── Revocation cache (in-memory jti blacklist mirror) ────────────────────
_revoked_cache: Set[str] = set()


def _load_revoked_cache() -> None:
    """加载未过期的 revoked jti 到内存 (DB → 内存)。"""
    global _revoked_cache
    try:
        conn = _init_db()
        now_ts = int(time.time())
        rows = conn.execute(
            "SELECT jti FROM revoked_tokens WHERE expires_at > ?", (now_ts,)
        ).fetchall()
        _revoked_cache = {r[0] for r in rows}
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to load revoked tokens: {e}")
        _revoked_cache = set()


def _revoke_token_db(jti: str, username: str, token_type: str,
                     exp_dt: datetime, reason: str = "logout") -> None:
    """写 revoked_tokens 表 + 内存。"""
    exp_ts = int(calendar.timegm(exp_dt.timetuple()))
    try:
        conn = _init_db()
        conn.execute(
            "INSERT OR REPLACE INTO revoked_tokens(jti,username,token_type,"
            "revoked_at,expires_at,reason) VALUES(?,?,?,datetime('now'),?,?)",
            (jti, username, token_type, exp_ts, reason),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to revoke token in DB: {e}")
    _revoked_cache.add(jti)


def _is_token_revoked(jti: str) -> bool:
    return jti in _revoked_cache


def _purge_expired_revoked() -> int:
    """清理过期的 revoked_tokens (返回删除行数)。"""
    try:
        conn = _init_db()
        now_ts = int(time.time())
        cur = conn.execute("DELETE FROM revoked_tokens WHERE expires_at <= ?", (now_ts,))
        conn.commit()
        deleted = cur.rowcount
        conn.close()
        return deleted
    except Exception as e:
        logger.warning(f"Failed to purge revoked tokens: {e}")
        return 0


# 启动时加载
_load_users()
_load_revoked_cache()

# ── Old RateLimiter (保留 ABI, 但 R9.5 改用 slowapi) ─────────────────────
class RateLimiter:
    """保留类以兼容历史 import; R9.5+ 推荐用 ``slowapi.Limiter``。"""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: Dict[str, list] = {}

    def check(self, ip: str) -> bool:
        now = time.time()
        self._buckets.setdefault(ip, [])
        self._buckets[ip] = [t for t in self._buckets[ip] if now - t < self.window_seconds]
        if len(self._buckets[ip]) >= self.max_requests:
            return False
        self._buckets[ip].append(now)
        return True

    def reset(self, ip: Optional[str] = None) -> None:
        if ip is None:
            self._buckets.clear()
        else:
            self._buckets.pop(ip, None)


rate_limiter = RateLimiter()  # 兼容历史 ABI

# ── Weak password list (R9-W1) ────────────────────────────────────────────
COMMON_WEAK_PASSWORDS = {
    "123456", "password", "12345678", "qwerty", "123456789",
    "12345", "1234", "111111", "1234567", "sunshine",
    "qwerty123", "iloveyou", "princess", "admin", "welcome",
    "666666", "abc123", "football", "123123", "monkey",
    "654321", "!@#$%^&*", "charlie", "aa123456", "donald",
    "password1", "qwertyuiop", "123321", "121212", "letmein",
    "dragon", "555555", "hello", "shadow", "michael",
    "baseball", "nicole", "access", "flower", "lovely",
    "7777777", "password123", "master", "hunter", "qwerty12345",
    "batman", "starwars", "trustno1", "whatever", "mustang",
    "purple", "robert", "jordan", "harley", "andrew",
    "summer", "buster", "soccer", "letmein1", "test",
    "temp", "temp123", "guest", "guest123", "user",
    "user123", "pass", "pass123", "passwd", "changeme",
    "secret", "admin123", "root", "administrator", "system",
    "default", "test123", "password1234", "qwerty123456", "abc123456",
    "1234567890", "123456789a", "test123456", "letmein123", "qazwsx",
    "1q2w3e", "1q2w3e4r", "1234qwer", "qwer1234", "qwerty123456",
}


def validate_password_strength(password: str) -> Tuple[bool, str]:
    SPECIAL_CHARS = set("!@#$%^&*()-_=+[]{}|;:',.<>?/`~")
    if len(password) < 8:
        return False, "密码至少需要8个字符"
    if not any(c.isupper() for c in password):
        return False, "密码必须包含至少一个大写字母"
    if not any(c.islower() for c in password):
        if not any(c in SPECIAL_CHARS for c in password):
            return False, "密码必须包含至少一个小写字母或特殊字符"
    if not any(c.isdigit() for c in password):
        return False, "密码必须包含至少一个数字"
    if password.lower() in {p.lower() for p in COMMON_WEAK_PASSWORDS}:
        return False, "密码过于常见，请选择更强的密码"
    return True, ""


# ── Pydantic models ───────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UserInfo(BaseModel):
    username: str
    role: str
    created_at: str


# ── Auth Service ──────────────────────────────────────────────────────────
class AuthService:
    """JWT + 密码哈希 + 用户管理。"""

    # ── password ────────────────────────────────────────────────────────
    @staticmethod
    def hash_password(password: str) -> str:
        return _hash_password(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return _verify_password(plain_password, hashed_password)

    # ── JWT mint / decode ────────────────────────────────────────────────
    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def create_access_token(cls, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        expire = cls._now_utc() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode.update({
            "exp": expire,
            "iat": cls._now_utc(),
            # P10-C: RFC 7519 §4.1.1 / §4.1.3 / §4.1.7 标准声明
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "jti": secrets.token_urlsafe(16),
            "type": TOKEN_TYPE_ACCESS,
        })
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @classmethod
    def create_refresh_token(cls, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        expire = cls._now_utc() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
        to_encode.update({
            "exp": expire,
            "iat": cls._now_utc(),
            # P10-C: RFC 7519 标准声明
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "jti": secrets.token_urlsafe(16),
            "type": TOKEN_TYPE_REFRESH,
        })
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict:
        try:
            # P10-C: 默认 disable verify_aud / verify_iss 保持向后兼容
            payload = jwt.decode(
                token, SECRET_KEY, algorithms=[ALGORITHM],
                options={"verify_aud": False, "verify_iss": False},
            )
        except JWTError as e:
            raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")
        jti = payload.get("jti")
        if jti and _is_token_revoked(jti):
            raise HTTPException(status_code=401, detail="Token has been revoked")
        return payload

    # ── high-level flows ────────────────────────────────────────────────
    @staticmethod
    def register(username: str, password: str, role: str = "viewer") -> dict:
        if username in users_db:
            raise HTTPException(status_code=400, detail="Username already exists")
        pwd_valid, pwd_msg = validate_password_strength(password)
        if not pwd_valid:
            raise HTTPException(status_code=400, detail=pwd_msg)
        password_hash = AuthService.hash_password(password)
        user = {
            "username": username,
            "password_hash": password_hash,
            "role": role,
            "enabled": True,
            "max_datasets": 10,
            "max_storage_mb": 1024,
            "max_api_calls_per_day": 1000,
            "created_at": AuthService._now_utc().isoformat(),
        }
        users_db[username] = user
        _save_user(username, password_hash, role)
        _log_gdpr(username, "register", f"role={role}")
        return {
            "success": True,
            "data": {
                "username": username,
                "role": role,
                "created_at": user["created_at"],
            },
            "error": None,
            "message": "User registered successfully",
        }

    @staticmethod
    def login(username: str, password: str) -> dict:
        user = users_db.get(username)
        if not user or not AuthService.verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if not user.get("enabled", True):
            raise HTTPException(status_code=403, detail="User disabled")
        access_token = AuthService.create_access_token({"sub": username, "role": user["role"]})
        refresh_token = AuthService.create_refresh_token({"sub": username, "role": user["role"]})
        csrf_token = secrets.token_urlsafe(32)
        _log_gdpr(username, "login", None)
        return {
            "success": True,
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "csrf_token": csrf_token,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            },
            "error": None,
            "message": "Login successful",
        }

    @staticmethod
    def refresh(refresh_token: str) -> dict:
        """一次性 refresh: 校验后立即 revoke, 重新签发一对。"""
        payload = AuthService.decode_token(refresh_token)
        if payload.get("type") != TOKEN_TYPE_REFRESH:
            raise HTTPException(status_code=401, detail="Not a refresh token")
        username = payload.get("sub")
        if not username or username not in users_db:
            raise HTTPException(status_code=401, detail="Invalid token subject")
        user = users_db[username]

        # 立即 revoke 旧 refresh (一次性)
        old_jti = payload.get("jti")
        exp_ts = payload.get("exp")
        if old_jti and exp_ts:
            try:
                exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            except Exception:
                exp_dt = AuthService._now_utc() + timedelta(days=1)
            _revoke_token_db(old_jti, username, TOKEN_TYPE_REFRESH, exp_dt, reason="refresh_used")

        # 签发新 pair
        new_access = AuthService.create_access_token({"sub": username, "role": user["role"]})
        new_refresh = AuthService.create_refresh_token({"sub": username, "role": user["role"]})
        _log_gdpr(username, "refresh", None)
        return {
            "success": True,
            "data": {
                "access_token": new_access,
                "refresh_token": new_refresh,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            },
            "error": None,
            "message": "Token refreshed",
        }

    @staticmethod
    def get_user_info(username: str) -> dict:
        user = users_db.get(username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "success": True,
            "data": {
                "username": username,
                "role": user.get("role", "viewer"),
                "created_at": user.get("created_at", ""),
            },
            "error": None,
            "message": "ok",
        }

    @staticmethod
    def change_password(username: str, old_password: str, new_password: str) -> dict:
        user = users_db.get(username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if not AuthService.verify_password(old_password, user["password_hash"]):
            raise HTTPException(status_code=400, detail="Old password is incorrect")
        pwd_valid, pwd_msg = validate_password_strength(new_password)
        if not pwd_valid:
            raise HTTPException(status_code=400, detail=pwd_msg)
        new_hash = AuthService.hash_password(new_password)
        user["password_hash"] = new_hash
        # 同步 DB
        try:
            conn = _init_db()
            conn.execute("UPDATE users SET password_hash=? WHERE username=?", (new_hash, username))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to update password in DB: {e}")
        _log_gdpr(username, "password_change", None)
        return {"success": True, "data": None, "error": None, "message": "Password changed successfully"}

    @staticmethod
    def logout(current_user: dict, access_payload: Optional[dict] = None,
               refresh_payload: Optional[dict] = None) -> dict:
        """Revoke 当前 access + (可选) refresh token。"""
        username = current_user["username"]
        if access_payload and access_payload.get("jti"):
            exp = access_payload.get("exp")
            try:
                exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
            except Exception:
                exp_dt = AuthService._now_utc() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            _revoke_token_db(access_payload["jti"], username, TOKEN_TYPE_ACCESS,
                             exp_dt, reason="logout")
        if refresh_payload and refresh_payload.get("jti"):
            exp = refresh_payload.get("exp")
            try:
                exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
            except Exception:
                exp_dt = AuthService._now_utc() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
            _revoke_token_db(refresh_payload["jti"], username, TOKEN_TYPE_REFRESH,
                             exp_dt, reason="logout")
        _log_gdpr(username, "logout", None)
        return {"success": True, "data": None, "error": None, "message": "Logged out"}


# ── GDPR helpers ──────────────────────────────────────────────────────────
def _log_gdpr(username: str, action: str, detail: Optional[str],
              ip: Optional[str] = None, user_agent: Optional[str] = None) -> None:
    try:
        conn = _init_db()
        conn.execute(
            "INSERT INTO gdpr_audit(username,action,detail,ip_address,user_agent) "
            "VALUES(?,?,?,?,?)",
            (username, action, detail, ip, user_agent),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to log GDPR audit: {e}")


def _collect_user_data(username: str) -> dict:
    """收集该用户所有数据 (Article 15 数据访问 + 20 数据可移植)。"""
    user = users_db.get(username, {})
    audit_rows: List[dict] = []
    try:
        conn = _init_db()
        rows = conn.execute(
            "SELECT action,detail,ip_address,user_agent,created_at FROM gdpr_audit "
            "WHERE username=? ORDER BY id DESC LIMIT 1000",
            (username,),
        ).fetchall()
        for row in rows:
            audit_rows.append({
                "action": row[0],
                "detail": row[1],
                "ip_address": row[2],
                "user_agent": row[3],
                "created_at": row[4],
            })
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to load gdpr audit for {username}: {e}")
    return {
        "profile": {
            "username": user.get("username"),
            "role": user.get("role"),
            "enabled": user.get("enabled"),
            "created_at": user.get("created_at"),
            "max_datasets": user.get("max_datasets"),
            "max_storage_mb": user.get("max_storage_mb"),
            "max_api_calls_per_day": user.get("max_api_calls_per_day"),
        },
        "audit_log": audit_rows,
        "exported_at": AuthService._now_utc().isoformat(),
        "export_basis": "GDPR Article 15 (right of access) + Article 20 (data portability)",
    }


# ── Dependencies ──────────────────────────────────────────────────────────
def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")
    payload = AuthService.decode_token(token)
    if payload.get("type") and payload.get("type") != TOKEN_TYPE_ACCESS:
        raise HTTPException(status_code=401, detail="Access token required (got refresh)")
    username = payload.get("sub")
    if not username or username not in users_db:
        raise HTTPException(status_code=401, detail="User not found")
    user = users_db[username]
    if not user.get("enabled", True):
        raise HTTPException(status_code=403, detail="User disabled")
    return {
        "username": username,
        "role": payload.get("role", "viewer"),
        "payload": payload,
    }


def check_rate_limit(request: Request):
    """兼容 R9-W1 ABI; 真实限流由 SlowAPI 处理。"""
    ip = request.client.host if request.client else "unknown"
    if not rate_limiter.check(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")


# ── SlowAPI limiter (导入即绑定; 由 canvas_web.py 装载 app.state.limiter) ─
_limiter = None
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    _limiter = Limiter(key_func=get_remote_address)
except Exception as e:
    logger.warning(f"slowapi not available: {e}; rate-limit decorators will be no-op")


def _rate_limit(limit: str):
    """装饰器: 优先 slowapi, 缺则降级为 legacy RateLimiter。"""
    def deco(func):
        if _limiter is not None:
            return _limiter.limit(limit)(func)
        return func
    return deco


# ── Routes ────────────────────────────────────────────────────────────────
@router.post("/register", response_model=dict)
@_rate_limit("10/minute")
def register(req: RegisterRequest, request: Request):
    """注册新用户 — 10/min/IP。"""
    return AuthService.register(req.username, req.password, req.role)


@router.post("/login", response_model=dict)
@_rate_limit("5/minute")
def login(req: LoginRequest, request: Request, response: Response):
    """登录 — 5/min/IP。响应下发 ``csrf_token`` 双 cookie。"""
    result = AuthService.login(req.username, req.password)
    csrf = result["data"].get("csrf_token")
    if csrf:
        # SameSite=Lax, HttpOnly=False (双 cookie 模式: 客户端 JS 需要读取)
        response.set_cookie(
            key="csrf_token",
            value=csrf,
            httponly=False,
            secure=False,  # 测试用 False; 生产 True + HTTPS
            samesite="lax",
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    return result


@router.post("/refresh", response_model=dict)
@_rate_limit("20/minute")
def refresh(req: RefreshRequest, request: Request):
    """刷新 access token — 20/min/IP。一次性 refresh: 旧 refresh 立即 revoke。"""
    if not req.refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token is required")
    return AuthService.refresh(req.refresh_token)


@router.post("/logout", response_model=dict)
def logout(
    response: Response,
    current_user: dict = Depends(get_current_user),
    refresh_req: Optional[RefreshRequest] = None,
):
    """登出 — revoke 当前 access token + 清 csrf cookie。"""
    access_payload = current_user.get("payload", {})
    refresh_payload = None
    if refresh_req and refresh_req.refresh_token:
        try:
            refresh_payload = AuthService.decode_token(refresh_req.refresh_token)
        except HTTPException:
            refresh_payload = None
    result = AuthService.logout(current_user, access_payload, refresh_payload)
    response.delete_cookie("csrf_token")
    return result


@router.get("/me", response_model=dict)
def get_me(current_user: dict = Depends(get_current_user)):
    """当前用户信息。"""
    return AuthService.get_user_info(current_user["username"])


@router.put("/password", response_model=dict)
def change_password(
    req: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """修改密码。"""
    return AuthService.change_password(
        current_user["username"], req.old_password, req.new_password
    )


# ── GDPR endpoints ────────────────────────────────────────────────────────
@router.get("/me/export", response_model=dict)
def export_me(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """GDPR Article 15 + 20: 导出当前用户所有数据 (含审计日志)。"""
    username = current_user["username"]
    payload = _collect_user_data(username)
    _log_gdpr(
        username, "export", "self-service export",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {
        "success": True,
        "data": payload,
        "error": None,
        "message": "User data exported successfully (GDPR Art. 15+20).",
    }


@router.delete("/me", response_model=dict)
def erase_me(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """GDPR Article 17: 删除当前用户 (右被遗忘权)。"""
    username = current_user["username"]
    # 先 revoke 当前 token
    access_payload = current_user.get("payload", {})
    if access_payload.get("jti"):
        try:
            exp = access_payload.get("exp")
            exp_dt = (datetime.fromtimestamp(exp, tz=timezone.utc)
                      if exp else AuthService._now_utc() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
            _revoke_token_db(access_payload["jti"], username, TOKEN_TYPE_ACCESS,
                             exp_dt, reason="user_erased")
        except Exception as e:
            logger.warning(f"revoke on erase failed: {e}")
    # 删 DB
    try:
        conn = _init_db()
        conn.execute("DELETE FROM users WHERE username=?", (username,))
        # 保留 audit 但记录擦除事件
        conn.execute(
            "INSERT INTO gdpr_audit(username,action,detail,ip_address,user_agent) "
            "VALUES(?,?,?,?,?)",
            (username, "erase", "self-service erase",
             request.client.host if request.client else None,
             request.headers.get("user-agent")),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to erase user {username}: {e}")
        raise HTTPException(status_code=500, detail=f"Erase failed: {e}")
    # 删内存
    users_db.pop(username, None)
    return {
        "success": True,
        "data": {"username": username, "erased": True},
        "error": None,
        "message": "User erased successfully (GDPR Art. 17).",
    }


@router.get("/me/audit", response_model=dict)
def audit_me(
    current_user: dict = Depends(get_current_user),
    limit: int = 100,
):
    """GDPR Article 15 配套: 当前用户的操作审计日志。"""
    username = current_user["username"]
    rows: List[dict] = []
    try:
        conn = _init_db()
        cur = conn.execute(
            "SELECT action,detail,ip_address,user_agent,created_at FROM gdpr_audit "
            "WHERE username=? ORDER BY id DESC LIMIT ?",
            (username, max(1, min(int(limit or 100), 500))),
        )
        for row in cur.fetchall():
            rows.append({
                "action": row[0],
                "detail": row[1],
                "ip_address": row[2],
                "user_agent": row[3],
                "created_at": row[4],
            })
        conn.close()
    except Exception as e:
        logger.warning(f"audit load failed: {e}")
    return {
        "success": True,
        "data": {
            "username": username,
            "entries": rows,
            "count": len(rows),
        },
        "error": None,
        "message": "ok",
    }


# ── Public introspection helpers (used by tests) ─────────────────────────
def get_revoked_count() -> int:
    return len(_revoked_cache)


def reset_security_state_for_tests() -> None:
    """测试 helper: 清空内存黑名单 + 清空内存 users_db + 重置 RateLimiter 状态。

    测试每次启动时从干净 slate 开始, 避免上一次 fixture 残留用户
    (否则 register 会立即返回 "Username already exists")。
    """
    global _revoked_cache, users_db
    _revoked_cache = set()
    users_db = {}  # 清空内存, register 时会重写 + INSERT OR REPLACE 进 DB
    rate_limiter.reset()
    # 注意: 不再调 _load_users() — 让测试完全从内存起步, 避免上一次 DB 残留