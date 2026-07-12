"""V5 第40章 — OWASP Top 10 (2021) 完整实作层.

10 个 inner class 分别对应 OWASP 2021 十大风险:

  ┌──────────────────────────────────────────────────────────────────┐
  │ A01 Broken Access Control         → AccessControl               │
  │ A02 Cryptographic Failures        → Cryptographic                │
  │ A03 Injection                     → Injection                    │
  │ A04 Insecure Design               → SecureDesign                 │
  │ A05 Security Misconfiguration     → SecurityConfig               │
  │ A06 Vulnerable & Outdated Comp.   → VulnerableComponents         │
  │ A07 Identification & Auth Failures→ IdentificationAuth           │
  │ A08 Software & Data Integrity     → IntegrityFailures            │
  │ A09 Security Logging & Monitoring → LoggingMonitoring            │
  │ A10 Server-Side Request Forgery   → SSRFProtection               │
  └──────────────────────────────────────────────────────────────────┘

聚合入口: ``OWASPProtection.protect_request`` (返回 ProtectedRequest)
 + ``OWASPProtection.audit_event`` (写 SecurityEvent 到 bus).
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple

import bcrypt
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .schemas import (
    JWTPayload,
    PermissionDecision,
    ProtectedRequest,
    SecurityEvent,
)


# ════════════════════════════════════════════════════════════════════════
#  A01 Broken Access Control — RBAC + ABAC
# ════════════════════════════════════════════════════════════════════════
class AccessControl:
    """6 角色 RBAC 矩阵 + ABAC 上下文约束.

    Roles:
        admin          — 全部权限
        project_owner  — 自己项目的资源
        annotator      — 自己被分配的任务
        reviewer       — 审核阶段权限
        qc_staff       — QC 阶段权限
        viewer         — 只读
    """

    ROLES = ("admin", "project_owner", "annotator", "reviewer", "qc_staff", "viewer")

    # RBAC 矩阵: role → set[resource.action]
    # 7 资源: project / requirement / dataset / pack / annotation / qc / delivery
    _RBAC: Dict[str, Dict[str, Set[str]]] = {
        "admin": {
            r: {"read", "write", "delete", "approve", "publish", "audit", "admin"}
            for r in ("project", "requirement", "dataset", "pack",
                      "annotation", "qc", "delivery", "user", "config")
        },
        "project_owner": {
            "project": {"read", "write", "delete"},
            "requirement": {"read", "write"},
            "dataset": {"read", "write", "publish"},
            "pack": {"read", "write", "publish"},
            "annotation": {"read"},
            "qc": {"read"},
            "delivery": {"read", "approve"},
        },
        "annotator": {
            "annotation": {"read", "write"},
            "dataset": {"read"},
            "pack": {"read"},
            "requirement": {"read"},
        },
        "reviewer": {
            "annotation": {"read", "approve"},
            "qc": {"read"},
            "pack": {"read", "approve"},
            "delivery": {"read"},
        },
        "qc_staff": {
            "qc": {"read", "write", "approve"},
            "annotation": {"read"},
            "pack": {"read"},
            "delivery": {"read"},
        },
        "viewer": {
            r: {"read"} for r in
            ("project", "requirement", "dataset", "pack",
             "annotation", "qc", "delivery")
        },
    }

    def check_permission(
        self,
        user: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
        roles: Optional[List[str]] = None,
    ) -> PermissionDecision:
        """RBAC + ABAC 检查.

        ABAC 上下文约束:
          - project_owner 仅能在 owner_user 匹配时操作
          - annotator 仅能在 assigned_user 匹配时写
        """
        ctx = context or {}
        user_roles = roles or ctx.get("roles", ["viewer"])
        # 兼容 str 单角色输入
        if isinstance(user_roles, str):
            user_roles = [user_roles]

        # admin 万能
        if "admin" in user_roles:
            return PermissionDecision(
                allowed=True, user=user, resource=resource, action=action,
                reason="admin role grant",
            )

        # 任一角色满足 RBAC + ABAC 即放行
        for role in user_roles:
            if role not in self._RBAC:
                continue
            rbac_actions = self._RBAC[role].get(resource, set())
            if action not in rbac_actions:
                continue
            # ABAC 二次校验
            if role == "project_owner":
                owner = ctx.get("owner_user")
                if owner and owner != user:
                    continue
            if role == "annotator" and action in {"write", "delete"}:
                assigned = ctx.get("assigned_user")
                if assigned and assigned != user:
                    continue
            return PermissionDecision(
                allowed=True, user=user, resource=resource, action=action,
                reason=f"role={role} grant",
            )

        return PermissionDecision(
            allowed=False, user=user, resource=resource, action=action,
            reason=f"no role grants {resource}.{action} for {user_roles}",
        )


# ════════════════════════════════════════════════════════════════════════
#  A02 Cryptographic Failures — bcrypt + AES-256-GCM
# ════════════════════════════════════════════════════════════════════════
class Cryptographic:
    """bcrypt 密码 hash + AES-256-GCM 对称加密."""

    BCRYPT_ROUNDS = 12

    @staticmethod
    def hash_password(password: str) -> str:
        """bcrypt 密码 hash (cost=12)."""
        if not isinstance(password, str):
            raise TypeError("password must be str")
        salt = bcrypt.gensalt(rounds=Cryptographic.BCRYPT_ROUNDS)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("ascii")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """bcrypt 验证密码."""
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
        except (ValueError, TypeError):
            return False

    @staticmethod
    def generate_aes_key() -> bytes:
        """生成 256-bit AES key (32 bytes)."""
        return AESGCM.generate_key(bit_length=256)

    @staticmethod
    def aes_encrypt(plaintext: bytes, key: bytes,
                    associated_data: Optional[bytes] = None) -> bytes:
        """AES-256-GCM encrypt → nonce(12) + ciphertext + tag."""
        if len(key) != 32:
            raise ValueError("AES-256 key must be 32 bytes")
        nonce = secrets.token_bytes(12)
        cipher = AESGCM(key)
        ct = cipher.encrypt(nonce, plaintext, associated_data)
        return nonce + ct

    @staticmethod
    def aes_decrypt(blob: bytes, key: bytes,
                    associated_data: Optional[bytes] = None) -> bytes:
        """AES-256-GCM decrypt."""
        if len(blob) < 12 + 16:
            raise ValueError("ciphertext too short")
        nonce, ct = blob[:12], blob[12:]
        cipher = AESGCM(key)
        return cipher.decrypt(nonce, ct, associated_data)


# ════════════════════════════════════════════════════════════════════════
#  A03 Injection — sanitize_input + validate_path
# ════════════════════════════════════════════════════════════════════════
class Injection:
    """SQL / NoSQL / Path traversal 防护."""

    # SQL 危险 pattern (忽略大小写) — 涵盖 ; DROP / -- / UNION SELECT / xp_
    _SQL_PATTERNS = [
        re.compile(r"(?i)(\b(union\s+select|drop\s+table|delete\s+from|insert\s+into|"
                   r"update\s+\w+\s+set)\b)"),
        re.compile(r"(?i)(--\s|;\s*drop|;\s*delete|;\s*update)"),
        re.compile(r"(?i)\bxp_(cmdshell|exec)\b"),
        re.compile(r"(?i)\bor\s+1\s*=\s*1\b"),
        re.compile(r"(?i)\bexec\s*\("),
        # SQL 注释收尾 (admin'--, x' OR 1=1 -- 等)
        re.compile(r"'\s*--"),
        re.compile(r"\b--\s*$"),
        # 引号 + SQL 关键字 (admin'; DROP)
        re.compile(r"(?i)'\s*;\s*(drop|delete|update|insert|union)"),
    ]
    # NoSQL 操作符注入 (MongoDB $where / $ne)
    _NOSQL_PATTERNS = [
        re.compile(r"\$\s*where\b", re.I),
        re.compile(r"\$\s*(ne|gt|lt|regex|where)\b", re.I),
    ]
    # XSS 兜底 (script / onerror / javascript:)
    _XSS_PATTERNS = [
        re.compile(r"<\s*script\b", re.I),
        re.compile(r"\bon\w+\s*=", re.I),
        re.compile(r"javascript\s*:", re.I),
    ]

    @classmethod
    def sanitize_input(cls, value: Any) -> Tuple[bool, str]:
        """扫描字符串值是否含注入 pattern.

        Returns:
            (is_safe, reason) — is_safe=True 表示字符串安全,
            否则 reason 描述被拦截的原因.
        """
        if not isinstance(value, str):
            return True, ""
        for pat in cls._SQL_PATTERNS:
            if pat.search(value):
                return False, f"sql pattern blocked: {pat.pattern}"
        for pat in cls._NOSQL_PATTERNS:
            if pat.search(value):
                return False, f"nosql operator blocked: {pat.pattern}"
        for pat in cls._XSS_PATTERNS:
            if pat.search(value):
                return False, f"xss pattern blocked: {pat.pattern}"
        return True, ""

    @staticmethod
    def validate_path(path: str, allowed_roots: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Path traversal 防护.

        1. 拒绝 ``..`` / ``~`` / 绝对路径(以 / 或 X:\\ 开头)
        2. 若提供 allowed_roots, 必须前缀匹配 (规范化后)
        """
        if not isinstance(path, str) or not path:
            return False, "empty path"
        # 绝对路径拒绝
        if path.startswith("/") or (len(path) >= 3 and path[1] == ":" and path[2] in "/\\"):
            return False, f"absolute path rejected: {path[:32]}"
        # 含 .. 或 ~ 直接拒绝
        parts = path.replace("\\", "/").split("/")
        if any(p == ".." for p in parts):
            return False, "path traversal '..' blocked"
        if any(p.startswith("~") for p in parts):
            return False, "user-home '~' blocked"
        # 白名单
        if allowed_roots:
            normalized = path.replace("\\", "/").lower()
            ok = any(normalized.startswith(root.lower().rstrip("/") + "/") or
                     normalized == root.lower().rstrip("/")
                     for root in allowed_roots)
            if not ok:
                return False, f"path not under allowed roots: {path}"
        return True, ""


# ════════════════════════════════════════════════════════════════════════
#  A04 Insecure Design — RateLimiter + AuditChain + InputValidator
# ════════════════════════════════════════════════════════════════════════
class SecureDesign:
    """Insecure Design 防护三件套: 限流 / 审计链 / 强输入校验."""

    @dataclass
    class RateLimiter:
        """滑动窗口限流 — in-memory per-key deque."""

        max_requests: int = 60
        window_seconds: float = 60.0
        _buckets: Dict[str, Deque[float]] = field(default_factory=dict)

        def allow(self, key: str, now: Optional[float] = None) -> bool:
            t = now if now is not None else time.time()
            q = self._buckets.setdefault(key, deque())
            # 清掉过期
            while q and (t - q[0]) > self.window_seconds:
                q.popleft()
            if len(q) >= self.max_requests:
                return False
            q.append(t)
            return True

    @dataclass
    class AuditChain:
        """Append-only 哈希链审计 — 每条 entry 含 prev_hash + entry_hash."""

        _entries: List[Dict[str, Any]] = field(default_factory=list)
        _last_hash: str = ""

        def append(self, event_type: str, actor: str,
                   payload: Optional[Dict[str, Any]] = None) -> str:
            entry: Dict[str, Any] = {
                "event_type": event_type,
                "actor": actor,
                "payload": dict(payload or {}),
                "ts": time.time(),
                "seq": len(self._entries),
                "prev_hash": self._last_hash,
            }
            blob = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()
            h = hashlib.sha256(blob).hexdigest()
            entry["entry_hash"] = h
            self._entries.append(entry)
            self._last_hash = h
            return h

        def verify(self) -> bool:
            prev = ""
            for i, e in enumerate(self._entries):
                if e["seq"] != i or e["prev_hash"] != prev:
                    return False
                test = {k: v for k, v in e.items() if k != "entry_hash"}
                blob = json.dumps(test, sort_keys=True, ensure_ascii=False).encode()
                if hashlib.sha256(blob).hexdigest() != e["entry_hash"]:
                    return False
                prev = e["entry_hash"]
            return True

        def __len__(self) -> int:
            return len(self._entries)

    class InputValidator:
        """强类型 + 长度 + charset 校验器."""

        MAX_LEN = 65536

        @classmethod
        def validate_string(cls, value: str, *,
                            max_len: int = MAX_LEN,
                            charset: Optional[str] = None) -> Tuple[bool, str]:
            if not isinstance(value, str):
                return False, "not a string"
            if len(value) > max_len:
                return False, f"length {len(value)} > {max_len}"
            if charset:
                bad = [c for c in value if c not in charset]
                if bad:
                    return False, f"chars outside charset: {bad[:5]}"
            # NUL byte 拒绝
            if "\x00" in value:
                return False, "NUL byte not allowed"
            return True, ""


# ════════════════════════════════════════════════════════════════════════
#  A05 Security Misconfiguration — CONFIG 集中管控
# ════════════════════════════════════════════════════════════════════════
class SecurityConfig:
    """集中安全配置 — 单一来源, 不散落在代码各处."""

    CONFIG: Dict[str, Any] = {
        "jwt_expiry_seconds": 3600,
        "jwt_refresh_seconds": 86400,
        "jwt_algorithm": "HS256",
        "session_timeout_seconds": 1800,
        "password_min_length": 8,
        "password_require_upper": True,
        "password_require_lower": True,
        "password_require_digit": True,
        "password_require_symbol": True,
        "rate_limit_per_minute": 60,
        "rate_limit_burst": 10,
        "max_upload_bytes": 100 * 1024 * 1024,   # 100 MB
        "allowed_file_types": (
            ".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov",
            ".json", ".csv", ".txt", ".pdf", ".md",
        ),
        "cors_allowed_origins": (
            "http://localhost:3000", "http://localhost:5173",
        ),
        "max_login_failures": 5,
        "lockout_seconds": 900,
    }

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        return cls.CONFIG.get(key, default)

    @classmethod
    def check_password(cls, password: str) -> Tuple[bool, str]:
        cfg = cls.CONFIG
        if len(password) < cfg["password_min_length"]:
            return False, f"too short (min {cfg['password_min_length']})"
        if cfg["password_require_upper"] and not re.search(r"[A-Z]", password):
            return False, "missing uppercase"
        if cfg["password_require_lower"] and not re.search(r"[a-z]", password):
            return False, "missing lowercase"
        if cfg["password_require_digit"] and not re.search(r"\d", password):
            return False, "missing digit"
        if cfg["password_require_symbol"] and not re.search(
            r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
            return False, "missing symbol"
        return True, ""


# ════════════════════════════════════════════════════════════════════════
#  A06 Vulnerable & Outdated Components — DependencyVersionChecker (mock)
# ════════════════════════════════════════════════════════════════════════
class VulnerableComponents:
    """依赖版本 / 已知 CVE 检查 (mock).

    实际生产应接 OSV / NVD API; 这里给一份本地 mock DB, 保持完全离线可用.
    """

    # 包名 → 最低安全版本 (低于此版本的视为 vulnerable)
    KNOWN_VULN_DB: Dict[str, str] = {
        "django": "4.2.11",
        "flask": "3.0.3",
        "requests": "2.32.0",
        "urllib3": "2.2.2",
        "pillow": "10.3.0",
        "sqlalchemy": "2.0.30",
        "cryptography": "42.0.5",
        "jwt": "2.8.0",
        "bcrypt": "4.1.2",
        "pydantic": "2.7.0",
    }

    @classmethod
    def check_requirements_text(cls, text: str) -> List[Dict[str, str]]:
        """解析 requirements.txt 文本, 返回 vulnerable 包列表."""
        findings: List[Dict[str, str]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 取包名 + 版本约束
            m = re.match(r"^([A-Za-z0-9_.\-]+)\s*([><=!~]+)\s*([\w\.\-]+)", line)
            if not m:
                continue
            pkg, op, ver = m.group(1).lower(), m.group(2), m.group(3)
            if pkg not in cls.KNOWN_VULN_DB:
                continue
            min_safe = cls.KNOWN_VULN_DB[pkg]
            try:
                pkg_v = tuple(int(x) for x in re.findall(r"\d+", ver))
                safe_v = tuple(int(x) for x in re.findall(r"\d+", min_safe))
                if pkg_v < safe_v:
                    findings.append({
                        "package": pkg,
                        "current": ver,
                        "min_safe": min_safe,
                        "cve_status": "vulnerable",
                    })
            except ValueError:
                continue
        return findings

    @classmethod
    def check_file(cls, path: str) -> List[Dict[str, str]]:
        """读 requirements.txt 文件并扫描."""
        with open(path, "r", encoding="utf-8") as fh:
            return cls.check_requirements_text(fh.read())


# ════════════════════════════════════════════════════════════════════════
#  A07 Identification & Auth Failures — JWTManager + SessionManager
# ════════════════════════════════════════════════════════════════════════
class IdentificationAuth:
    """JWT (HS256) + Session + Lockout."""

    class JWTManager:
        """HS256 JWT sign/verify/refresh."""

        def __init__(self, secret: Optional[str] = None,
                     expiry_seconds: Optional[int] = None,
                     refresh_seconds: Optional[int] = None):
            self.secret = (secret or secrets.token_urlsafe(48)).encode("utf-8")
            self.expiry = expiry_seconds or int(SecurityConfig.get("jwt_expiry_seconds", 3600))
            self.refresh = refresh_seconds or int(SecurityConfig.get("jwt_refresh_seconds", 86400))
            self.algorithm = "HS256"

        def sign(self, user: str, roles: Optional[List[str]] = None,
                 extra: Optional[Dict[str, Any]] = None) -> str:
            now = int(time.time())
            payload = {
                "sub": user,
                "roles": list(roles or []),
                "iat": now,
                "exp": now + self.expiry,
                "iss": "imdf.owasp",
                **(extra or {}),
            }
            return jwt.encode(payload, self.secret, algorithm=self.algorithm)

        def verify(self, token: str) -> JWTPayload:
            """验证 token — 过期 / 签名错误 / 格式错误都抛 ValueError."""
            try:
                raw = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            except jwt.ExpiredSignatureError as exc:
                raise ValueError("token expired") from exc
            except jwt.InvalidSignatureError as exc:
                raise ValueError("invalid signature") from exc
            except jwt.InvalidTokenError as exc:
                raise ValueError(f"invalid token: {exc}") from exc
            return JWTPayload(
                sub=raw.get("sub", ""),
                roles=list(raw.get("roles", [])),
                exp=int(raw.get("exp", 0)),
                iat=int(raw.get("iat", 0)),
                iss=raw.get("iss", ""),
                raw=raw,
            )

        def refresh(self, token: str) -> str:
            """在 refresh 窗口内换发新 token. 过期则拒绝."""
            try:
                raw = jwt.decode(
                    token, self.secret,
                    algorithms=[self.algorithm],
                    options={"verify_exp": False},
                )
            except jwt.InvalidTokenError as exc:
                raise ValueError(f"invalid token: {exc}") from exc
            iat = int(raw.get("iat", 0))
            now = int(time.time())
            if now - iat > self.refresh:
                raise ValueError("refresh window expired")
            return self.sign(raw.get("sub", ""), raw.get("roles", []))

    class SessionManager:
        """Session 生命周期 + 失败计数 lockout."""

        def __init__(self, max_failures: Optional[int] = None,
                     lockout_seconds: Optional[int] = None,
                     session_timeout: Optional[int] = None):
            self.max_failures = max_failures or int(
                SecurityConfig.get("max_login_failures", 5))
            self.lockout_seconds = lockout_seconds or int(
                SecurityConfig.get("lockout_seconds", 900))
            self.session_timeout = session_timeout or int(
                SecurityConfig.get("session_timeout_seconds", 1800))
            self._sessions: Dict[str, Dict[str, Any]] = {}
            self._failed: Dict[str, int] = {}
            self._locked_until: Dict[str, float] = {}

        def _is_locked(self, user: str) -> bool:
            until = self._locked_until.get(user, 0.0)
            if until and time.time() < until:
                return True
            if until:
                self._locked_until.pop(user, None)
                self._failed.pop(user, None)
            return False

        def record_failure(self, user: str) -> int:
            cnt = self._failed.get(user, 0) + 1
            self._failed[user] = cnt
            if cnt >= self.max_failures:
                self._locked_until[user] = time.time() + self.lockout_seconds
            return cnt

        def record_success(self, user: str) -> None:
            self._failed.pop(user, None)
            self._locked_until.pop(user, None)

        def create(self, user: str, roles: Optional[List[str]] = None) -> str:
            if self._is_locked(user):
                raise ValueError(f"user {user} is locked out")
            sid = secrets.token_urlsafe(32)
            self._sessions[sid] = {
                "user": user,
                "roles": list(roles or []),
                "created_at": time.time(),
                "last_active": time.time(),
            }
            return sid

        def validate(self, sid: str) -> Optional[Dict[str, Any]]:
            sess = self._sessions.get(sid)
            if not sess:
                return None
            if time.time() - sess["last_active"] > self.session_timeout:
                self.invalidate(sid)
                return None
            sess["last_active"] = time.time()
            return dict(sess)

        def invalidate(self, sid: str) -> None:
            self._sessions.pop(sid, None)


# ════════════════════════════════════════════════════════════════════════
#  A08 Software & Data Integrity — Signature + Attestation (mock)
# ════════════════════════════════════════════════════════════════════════
class IntegrityFailures:
    """HMAC-SHA256 签名 / 验证 + CI artifact attestation (mock)."""

    class SignatureVerifier:
        def __init__(self, secret: Optional[bytes] = None):
            self.secret = secret or secrets.token_bytes(32)

        def sign(self, payload: bytes) -> str:
            return hmac.new(self.secret, payload, hashlib.sha256).hexdigest()

        def verify(self, payload: bytes, signature: str) -> bool:
            expected = self.sign(payload)
            return hmac.compare_digest(expected, signature)

    class CIArtifactAttestation:
        """Mock CI artifact attestation — 记录 build_id → 制品签名 + 来源.

        生产场景 secret 来自 KMS / env; 这里实例化时确定一次, sign 与
        verify 共用同一 secret.
        """

        def __init__(self, secret: Optional[bytes] = None):
            self._secret = secret or b"imdf-attestation-mock-secret-32bytes!!"
            self._attestations: Dict[str, Dict[str, Any]] = {}

        def attest(self, build_id: str, artifact_uri: str,
                   source_commit: str) -> Dict[str, Any]:
            verifier = IntegrityFailures.SignatureVerifier(self._secret)
            payload = f"{build_id}|{artifact_uri}|{source_commit}".encode()
            sig = verifier.sign(payload)
            record = {
                "build_id": build_id,
                "artifact_uri": artifact_uri,
                "source_commit": source_commit,
                "signature": sig,
                "ts": time.time(),
            }
            self._attestations[build_id] = record
            return record

        def verify(self, build_id: str) -> bool:
            rec = self._attestations.get(build_id)
            if not rec:
                return False
            payload = f"{rec['build_id']}|{rec['artifact_uri']}|{rec['source_commit']}".encode()
            verifier = IntegrityFailures.SignatureVerifier(self._secret)
            return verifier.verify(payload, rec["signature"])


# ════════════════════════════════════════════════════════════════════════
#  A09 Security Logging & Monitoring — SecurityEventLogger
# ════════════════════════════════════════════════════════════════════════
class LoggingMonitoring:
    """SecurityEventLogger — 写 bus topic ``security.event``."""

    class SecurityEventLogger:
        DEFAULT_TOPIC = "security.event"

        def __init__(self, bus: Any = None):
            self._bus = bus
            self._events: List[SecurityEvent] = []

        def _publish(self, event: SecurityEvent) -> None:
            self._events.append(event)
            if self._bus is not None:
                publish = getattr(self._bus, "publish", None)
                if callable(publish):
                    try:
                        publish(event.topic, event.model_dump())
                    except Exception:
                        pass

        def log_auth_success(self, actor: str, **payload: Any) -> SecurityEvent:
            ev = SecurityEvent(
                event_type="auth.login", actor=actor,
                payload=payload, severity="info",
                topic=self.DEFAULT_TOPIC,
            )
            self._publish(ev)
            return ev

        def log_auth_failure(self, actor: str, **payload: Any) -> SecurityEvent:
            ev = SecurityEvent(
                event_type="auth.failed", actor=actor,
                payload=payload, severity="warn",
                topic=self.DEFAULT_TOPIC,
            )
            self._publish(ev)
            return ev

        def log_access_denied(self, actor: str, **payload: Any) -> SecurityEvent:
            ev = SecurityEvent(
                event_type="access.denied", actor=actor,
                payload=payload, severity="warn",
                topic=self.DEFAULT_TOPIC,
            )
            self._publish(ev)
            return ev

        def log_config_change(self, actor: str, **payload: Any) -> SecurityEvent:
            ev = SecurityEvent(
                event_type="config.changed", actor=actor,
                payload=payload, severity="critical",
                topic=self.DEFAULT_TOPIC,
            )
            self._publish(ev)
            return ev

        def list_events(self, event_type: Optional[str] = None) -> List[SecurityEvent]:
            if event_type is None:
                return list(self._events)
            return [e for e in self._events if e.event_type == event_type]


# ════════════════════════════════════════════════════════════════════════
#  A10 Server-Side Request Forgery — URLValidator + HttpClient
# ════════════════════════════════════════════════════════════════════════
class SSRFProtection:
    """URL 白/黑名单 + 私有 IP / localhost / link-local 拦截."""

    class URLValidator:
        # 默认白名单 scheme
        ALLOWED_SCHEMES = ("http", "https")

        def __init__(self, allow_private: bool = False,
                     allowed_hosts: Optional[List[str]] = None,
                     blocked_hosts: Optional[List[str]] = None):
            self.allow_private = allow_private
            self.allowed_hosts = set(h.lower() for h in (allowed_hosts or []))
            self.blocked_hosts = set(h.lower() for h in (blocked_hosts or []))

        @staticmethod
        def _is_private_ip(ip_str: str) -> bool:
            try:
                ip = ipaddress.ip_address(ip_str)
                return (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_multicast
                    or ip.is_reserved
                    or ip.is_unspecified
                )
            except ValueError:
                return False

        @staticmethod
        def _parse_host(url: str) -> Optional[Tuple[str, str]]:
            """解析 scheme://host[:port][/path], 正确处理 IPv6 [..] 包裹.

            Returns:
                (scheme, host_no_port_no_brackets) or None if malformed.
            """
            m = re.match(
                r"^([a-zA-Z][a-zA-Z0-9+\-.]*)://([^/?#]+)", url
            )
            if not m:
                return None
            scheme = m.group(1).lower()
            rest = m.group(2)
            # strip userinfo
            if "@" in rest:
                rest = rest.split("@", 1)[1]
            # IPv6: [xxxx]:port
            if rest.startswith("["):
                close = rest.find("]")
                if close < 0:
                    return None
                host = rest[1:close]
                # 之后必须是 :port / 空 / ? / #
                tail = rest[close + 1 :]
                if tail and not tail.startswith((":", "/", "?", "#")):
                    return None
            else:
                # IPv4 / hostname — 去掉 :port (只切第一个 :)
                host = rest.split(":", 1)[0]
            return scheme, host

        def validate(self, url: str) -> Tuple[bool, str]:
            if not isinstance(url, str) or not url:
                return False, "empty url"
            parsed = self._parse_host(url)
            if not parsed:
                return False, "malformed url"
            scheme, host_no_port = parsed
            host_no_port = host_no_port.lower()

            if scheme not in self.ALLOWED_SCHEMES:
                return False, f"scheme {scheme} not allowed"
            if host_no_port in self.blocked_hosts:
                return False, f"host blocked: {host_no_port}"
            # 白名单: 若配置了 allowed_hosts, 仅放行白名单内的 host
            if self.allowed_hosts:
                if host_no_port in self.allowed_hosts:
                    return True, "whitelisted"
                return False, f"host not in whitelist: {host_no_port}"
            # localhost (含 IPv4-mapped IPv6 ::ffff:127.0.0.1 等)
            localhost_aliases = {"localhost", "127.0.0.1", "0.0.0.0"}
            if host_no_port in localhost_aliases:
                return False, "localhost blocked"
            # 私有 IP 检测 (含 IPv4 / IPv6 / IPv4-mapped IPv6)
            try:
                ip = ipaddress.ip_address(host_no_port)
                # ::1, ::, 127.x.x.x, 10.x, 172.16-31.x, 192.168.x,
                # 169.254.x (link-local), fe80::/10, fc00::/7, etc.
                if self._is_private_ip(host_no_port):
                    return False, f"private ip blocked: {host_no_port}"
            except ValueError:
                # 非 IP 字符串 → 视为域名; 拦截 "::1" 字面误识别
                if host_no_port == "::1":
                    return False, "localhost blocked"
                # 简单 internal 关键字拦截
                bad_internal = ("internal", "corp", "intranet", "lan", "local")
                if any(kw in host_no_port for kw in bad_internal):
                    return False, f"internal hostname blocked: {host_no_port}"
            return True, ""

    class HttpClient:
        """URL-validated HTTP client wrapper."""

        def __init__(self, validator: Optional["SSRFProtection.URLValidator"] = None):
            self.validator = validator or SSRFProtection.URLValidator()

        def get(self, url: str) -> Dict[str, Any]:
            ok, reason = self.validator.validate(url)
            if not ok:
                return {
                    "ok": False, "error": reason, "url": url,
                    "status": 0, "body": "",
                }
            # 真实环境调 requests / httpx; 这里给 mock response
            return {
                "ok": True,
                "url": url,
                "status": 200,
                "body": f"<mock-body for {url}>",
            }


# ════════════════════════════════════════════════════════════════════════
#  Aggregate — OWASPProtection 主类
# ════════════════════════════════════════════════════════════════════════
class OWASPProtection:
    """OWASP Top 10 防护聚合入口.

    暴露方法:
        protect_request(request) -> ProtectedRequest
        audit_event(event_type, actor, payload) -> SecurityEvent

    request 输入 schema (dict):
        {
          "user":   str,
          "resource": str,
          "action":  str,
          "roles":   List[str] | str,
          "context": dict (ABAC context: owner_user / assigned_user / ...),
          "inputs":  dict[str, Any]   (要被 sanitize 的字段),
          "path":    Optional[str]    (要被 validate_path 的路径),
          "url":     Optional[str]    (要被 SSRF validate 的 URL),
          "rate_key": Optional[str]   (限流 key, 默认 user),
          "artifact": Optional[bytes] (要签名校验的字节),
          "signature": Optional[str]   (对应签名),
        }
    """

    def __init__(self, bus: Any = None,
                 jwt_secret: Optional[str] = None,
                 aes_key: Optional[bytes] = None):
        self.access = AccessControl()
        self.crypto = Cryptographic()
        self.injection = Injection()
        self.secure_design = SecureDesign()
        self.config = SecurityConfig()
        self.vulnerable = VulnerableComponents()
        self.auth = IdentificationAuth()
        self.integrity = IntegrityFailures()
        self.logging = LoggingMonitoring.SecurityEventLogger(bus=bus)
        self.ssrf = SSRFProtection()

        # 给 JWTManager + SignatureVerifier 配独立 secret
        self.jwt_manager = self.auth.JWTManager(secret=jwt_secret)
        self.signature_verifier = self.integrity.SignatureVerifier()
        self.attestation = self.integrity.CIArtifactAttestation()
        self.rate_limiter = self.secure_design.RateLimiter(
            max_requests=int(self.config.get("rate_limit_per_minute", 60)),
            window_seconds=60.0,
        )
        self.audit_chain = self.secure_design.AuditChain()
        # 可选 AES key — 调用方可注入; 不传则在第一次 encrypt 时生成
        self._aes_key: Optional[bytes] = aes_key

    # ── public API ────────────────────────────────────────────────────
    def protect_request(self, request: Dict[str, Any]) -> ProtectedRequest:
        """聚合 10 个防护器的统一入口."""
        errors: List[str] = []
        user = str(request.get("user", "anonymous"))
        resource = str(request.get("resource", ""))
        action = str(request.get("action", "read"))
        ctx = dict(request.get("context") or {})
        roles = request.get("roles") or ctx.get("roles") or ["viewer"]

        # A01 — Access Control
        decision = self.access.check_permission(user, resource, action, ctx, roles)
        if not decision.allowed:
            self.logging.log_access_denied(
                actor=user, resource=resource, action=action,
                roles=roles, reason=decision.reason,
            )
            errors.append(f"access denied: {decision.reason}")

        # A04 — Rate Limit (per user 或 rate_key)
        rate_key = str(request.get("rate_key") or user)
        rl_ok = self.rate_limiter.allow(rate_key)
        if not rl_ok:
            errors.append(f"rate limit exceeded for {rate_key}")

        # A03 — sanitize inputs
        sanitized: Dict[str, Any] = {}
        for k, v in (request.get("inputs") or {}).items():
            safe, reason = self.injection.sanitize_input(v)
            sanitized[k] = v if safe else f"[BLOCKED:{reason}]"
            if not safe:
                errors.append(f"injection blocked: field={k}")

        # A03 — path validation
        path = request.get("path")
        safe_path: Optional[str] = None
        if path is not None:
            ok_path, path_reason = self.injection.validate_path(
                path, allowed_roots=request.get("allowed_roots"),
            )
            if ok_path:
                safe_path = path
            else:
                errors.append(f"path traversal: {path_reason}")

        # A10 — SSRF
        url = request.get("url")
        ssrf_ok = True
        if url is not None:
            ssrf_ok, ssrf_reason = self.ssrf.URLValidator().validate(url)
            if not ssrf_ok:
                errors.append(f"ssrf: {ssrf_reason}")

        # A08 — Integrity
        artifact = request.get("artifact")
        sig = request.get("signature")
        integrity_ok = True
        if artifact is not None and sig is not None:
            integrity_ok = self.signature_verifier.verify(artifact, sig)
            if not integrity_ok:
                errors.append("integrity: signature mismatch")

        # A05 — config snapshot
        cfg_snapshot = {
            "jwt_expiry": self.config.get("jwt_expiry_seconds"),
            "rate_limit": self.config.get("rate_limit_per_minute"),
            "max_upload": self.config.get("max_upload_bytes"),
            "cors_origins": list(self.config.get("cors_allowed_origins") or []),
        }

        # 写 audit chain + log
        if decision.allowed:
            self.audit_chain.append(
                "access.granted", user,
                {"resource": resource, "action": action, "roles": roles},
            )

        return ProtectedRequest(
            user=user, resource=resource, action=action,
            permission=decision,
            sanitized_input=sanitized,
            safe_path=safe_path,
            ssrf_checked=ssrf_ok,
            rate_limit_ok=rl_ok,
            integrity_ok=integrity_ok,
            config_snapshot=cfg_snapshot,
            errors=errors,
        )

    def audit_event(self, event_type: str, actor: str,
                    payload: Optional[Dict[str, Any]] = None) -> SecurityEvent:
        """写一条 SecurityEvent 到 logger + audit chain."""
        if event_type.startswith("auth.") and "fail" in event_type:
            ev = self.logging.log_auth_failure(actor, **(payload or {}))
        elif event_type.startswith("auth."):
            ev = self.logging.log_auth_success(actor, **(payload or {}))
        elif event_type.startswith("config."):
            ev = self.logging.log_config_change(actor, **(payload or {}))
        else:
            ev = self.logging._events and self.logging.list_events()  # noqa: SLF001
            # 默认 fallback: 直接构造事件
            ev = SecurityEvent(
                event_type=event_type, actor=actor,
                payload=payload or {},
                severity="info", topic=self.logging.DEFAULT_TOPIC,
            )
            self.logging._publish(ev)  # noqa: SLF001
        self.audit_chain.append(event_type, actor, payload)
        return ev


__all__ = [
    "OWASPProtection",
    "AccessControl",
    "Cryptographic",
    "Injection",
    "SecureDesign",
    "SecurityConfig",
    "VulnerableComponents",
    "IdentificationAuth",
    "IntegrityFailures",
    "LoggingMonitoring",
    "SSRFProtection",
]