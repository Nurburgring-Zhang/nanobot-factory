"""V5 第40章 — MFA (TOTP / SMS OTP / Email OTP / Backup codes).

TOTP 实现完全自包含 RFC 6238 (HMAC-SHA1, 30s timestep, 6 digits default),
不依赖 pyotp. SMS / Email 是 mock 渠道 — 不真发,验证码存内存等待 verify.

生产替换说明:
  * 真实 SMS gateway: send_sms() 替换为 twilio / aliyun_sms client call
  * 真实 Email: send_email() 替换为 SES / sendgrid client call
  * Backup codes: 持久化到 DB (目前 in-memory dict)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from .sso_mfa_c2pa_schemas import (
    ChallengeResult,
    EnrollmentResult,
    MFAMethod,
    VerificationResult,
)


# ════════════════════════════════════════════════════════════════════════
# TOTP — RFC 6238 (HMAC-SHA1)
# ════════════════════════════════════════════════════════════════════════
def _hotp(secret: bytes, counter: int, digits: int = 6) -> str:
    """HMAC-based OTP per RFC 4226 — used internally by TOTP."""
    counter_bytes = struct.pack(">Q", counter)
    h = hmac.new(secret, counter_bytes, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code_int = (
        ((h[offset] & 0x7F) << 24)
        | ((h[offset + 1] & 0xFF) << 16)
        | ((h[offset + 2] & 0xFF) << 8)
        | (h[offset + 3] & 0xFF)
    )
    code = code_int % (10 ** digits)
    return str(code).zfill(digits)


def _totp_at(secret: bytes, t: int, period: int = 30, digits: int = 6) -> str:
    counter = int(t // period)
    return _hotp(secret, counter, digits)


def generate_totp_secret(length: int = 20) -> str:
    """生成 base32 编码的 TOTP secret (推荐 20 字节 = 160 bit).

    Returns:
        base32 string, no padding (compatible with otpauth:// URI).
    """
    raw = secrets.token_bytes(length)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _b32_decode(s: str) -> bytes:
    """Base32 解码,自动补 padding."""
    pad = "=" * (-len(s) % 8)
    return base64.b32decode(s + pad)


def get_provisioning_uri(
    secret_b32: str,
    account_name: str,
    issuer: str = "IMDF",
    period: int = 30,
    digits: int = 6,
) -> str:
    """Build otauth:// URI for QR code enrollment.

    格式: otpauth://totp/Issuer:account?secret=BASE32&issuer=Issuer&period=30&digits=6
    """
    from urllib.parse import quote
    label = quote(f"{issuer}:{account_name}", safe="")
    return (
        f"otpauth://totp/{label}"
        f"?secret={secret_b32}&issuer={quote(issuer)}"
        f"&period={period}&digits={digits}"
    )


def verify_totp(
    secret_b32: str,
    code: str,
    *,
    at: Optional[int] = None,
    period: int = 30,
    digits: int = 6,
    window: int = 1,
) -> bool:
    """校验 TOTP,允许 ±window 个 timestep 漂移 (±30s by default)."""
    if not code or not code.isdigit() or len(code) != digits:
        return False
    secret = _b32_decode(secret_b32)
    now = int(at if at is not None else time.time())
    for w in range(-window, window + 1):
        candidate = _totp_at(secret, now + w * period, period, digits)
        if hmac.compare_digest(candidate, code):
            return True
    return False


# ════════════════════════════════════════════════════════════════════════
# OTP 工具 (SMS / Email)
# ════════════════════════════════════════════════════════════════════════
def _generate_otp_code(length: int = 6) -> str:
    """生成纯数字 OTP code (default 6 digits, ~1M 空间)."""
    if length < 4 or length > 10:
        raise ValueError("OTP length must be between 4 and 10")
    lo = 10 ** (length - 1)
    hi = 10 ** length
    return str(secrets.randbelow(hi - lo) + lo)


def _hash_code(code: str) -> str:
    """不存明文 OTP,存 SHA-256 hex."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


# ════════════════════════════════════════════════════════════════════════
# MFAManager — 统一入口
# ════════════════════════════════════════════════════════════════════════
class MFAManager:
    """管理所有 MFA 方法的 in-memory state + 业务流.

    Args:
        sms_sender: optional async callable(phone, code) → None
        email_sender: optional async callable(addr, code) → None
        otp_ttl: OTP / challenge 有效秒数 (default 300 = 5 min)
        backup_count: generate 时返回的 backup codes 数 (default 10)
    """

    def __init__(
        self,
        *,
        sms_sender=None,  # Optional[Callable[[str,str], Awaitable[None]]]
        email_sender=None,
        otp_ttl: int = 300,
        backup_count: int = 10,
    ) -> None:
        self.sms_sender = sms_sender
        self.email_sender = email_sender
        self.otp_ttl = otp_ttl
        self.backup_count = backup_count

        # user_id → {method → secret / pending challenge / backup codes}
        self._user_secrets: Dict[str, Dict[str, str]] = {}
        self._user_backup_codes: Dict[str, List[str]] = {}  # user → hash list
        self._pending_challenges: Dict[str, Dict[str, str]] = {}  # challenge_id → {user_id, method, code_hash, expires_at}

    # ── TOTP ─────────────────────────────────────────────────────────────
    def enroll_totp(self, user_id: str, *, issuer: str = "IMDF") -> EnrollmentResult:
        """生成 TOTP secret + provisioning_uri. 不立即 verify."""
        secret = generate_totp_secret()
        self._user_secrets.setdefault(user_id, {})["totp"] = secret
        return EnrollmentResult(
            success=True,
            method=MFAMethod.TOTP,
            secret=secret,
            provisioning_uri=get_provisioning_uri(secret, user_id, issuer=issuer),
        )

    def get_totp_secret(self, user_id: str) -> Optional[str]:
        return self._user_secrets.get(user_id, {}).get("totp")

    # ── SMS / Email ──────────────────────────────────────────────────────
    async def enroll_sms(self, user_id: str, phone: str) -> EnrollmentResult:
        """SMS enrollment 仅记录目标 phone,真实绑定需 verify 一次."""
        self._user_secrets.setdefault(user_id, {})["sms_phone"] = phone
        return EnrollmentResult(
            success=True,
            method=MFAMethod.SMS,
            delivery_target=phone,
        )

    async def enroll_email(self, user_id: str, email: str) -> EnrollmentResult:
        self._user_secrets.setdefault(user_id, {})["email_addr"] = email
        return EnrollmentResult(
            success=True,
            method=MFAMethod.EMAIL,
            delivery_target=email,
        )

    # ── Backup codes ─────────────────────────────────────────────────────
    def generate_backup_codes(self, user_id: str, *, count: Optional[int] = None) -> List[str]:
        """生成 N 个一次性 backup codes — 每个 8 字符 (字母+数字)."""
        n = count or self.backup_count
        alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # exclude confusable chars
        codes = ["".join(secrets.choice(alphabet) for _ in range(8)) for _ in range(n)]
        self._user_backup_codes[user_id] = [_hash_code(c) for c in codes]
        return codes

    async def enroll_backup(self, user_id: str) -> EnrollmentResult:
        codes = self.generate_backup_codes(user_id)
        return EnrollmentResult(
            success=True,
            method=MFAMethod.BACKUP,
            backup_codes=codes,
        )

    # ── Challenge / Verify 通用 ──────────────────────────────────────────
    async def challenge(self, user_id: str, method: MFAMethod) -> ChallengeResult:
        """发起一次 MFA challenge (生成 OTP 并存储)."""
        if method == MFAMethod.TOTP:
            # TOTP 不需要 server-side challenge (客户端基于时间算 code)
            if user_id not in self._user_secrets or "totp" not in self._user_secrets[user_id]:
                return ChallengeResult(
                    success=False,
                    method=method,
                    challenge_id="",
                    error="TOTP not enrolled",
                )
            cid = f"ch_{uuid.uuid4().hex[:12]}"
            return ChallengeResult(
                success=True,
                method=method,
                challenge_id=cid,
                sent=False,
                delivery_target="(client-side TOTP)",
            )
        if method == MFAMethod.SMS:
            phone = self._user_secrets.get(user_id, {}).get("sms_phone")
            if not phone:
                return ChallengeResult(
                    success=False, method=method, challenge_id="",
                    error="SMS phone not enrolled",
                )
            code = _generate_otp_code()
            cid = f"ch_{uuid.uuid4().hex[:12]}"
            self._pending_challenges[cid] = {
                "user_id": user_id,
                "method": MFAMethod.SMS.value,
                "code_hash": _hash_code(code),
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=self.otp_ttl)).isoformat(),
            }
            if self.sms_sender:
                await self.sms_sender(phone, code)
            return ChallengeResult(
                success=True, method=method, challenge_id=cid,
                sent=True, delivery_target=phone,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.otp_ttl),
            )
        if method == MFAMethod.EMAIL:
            addr = self._user_secrets.get(user_id, {}).get("email_addr")
            if not addr:
                return ChallengeResult(
                    success=False, method=method, challenge_id="",
                    error="Email not enrolled",
                )
            code = _generate_otp_code()
            cid = f"ch_{uuid.uuid4().hex[:12]}"
            self._pending_challenges[cid] = {
                "user_id": user_id,
                "method": MFAMethod.EMAIL.value,
                "code_hash": _hash_code(code),
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=self.otp_ttl)).isoformat(),
            }
            if self.email_sender:
                await self.email_sender(addr, code)
            return ChallengeResult(
                success=True, method=method, challenge_id=cid,
                sent=True, delivery_target=addr,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.otp_ttl),
            )
        if method == MFAMethod.BACKUP:
            # Backup code 不需要 server-side challenge (用户提供 code 直接 verify)
            if user_id not in self._user_backup_codes:
                return ChallengeResult(
                    success=False, method=method, challenge_id="",
                    error="No backup codes generated",
                )
            cid = f"ch_{uuid.uuid4().hex[:12]}"
            return ChallengeResult(
                success=True, method=method, challenge_id=cid,
                sent=False, delivery_target="(use generated backup code)",
            )
        return ChallengeResult(
            success=False, method=method, challenge_id="",
            error=f"unsupported method: {method}",
        )

    # ── Public APIs ──────────────────────────────────────────────────────
    async def enroll_mfa(self, user_id: str, method: MFAMethod,
                         target: Optional[str] = None) -> EnrollmentResult:
        """enroll_mfa:注册 MFA 方法."""
        if method == MFAMethod.TOTP:
            return self.enroll_totp(user_id)
        if method == MFAMethod.SMS:
            if not target:
                return EnrollmentResult(success=False, method=method, error="phone required")
            return await self.enroll_sms(user_id, target)
        if method == MFAMethod.EMAIL:
            if not target:
                return EnrollmentResult(success=False, method=method, error="email required")
            return await self.enroll_email(user_id, target)
        if method == MFAMethod.BACKUP:
            return await self.enroll_backup(user_id)
        return EnrollmentResult(success=False, method=method, error="unknown method")

    async def challenge_mfa(self, user_id: str, method: MFAMethod) -> ChallengeResult:
        return await self.challenge(user_id, method)

    async def verify_mfa(
        self,
        user_id: str,
        method: MFAMethod,
        code: str,
        *,
        challenge_id: Optional[str] = None,
    ) -> VerificationResult:
        """verify_mfa:验证用户提供的 code 是否正确."""
        # ── TOTP (不需要 challenge_id) ─────────────────────────────────
        if method == MFAMethod.TOTP:
            secret = self._user_secrets.get(user_id, {}).get("totp")
            if not secret:
                return VerificationResult(
                    success=False, method=method, user_id=user_id,
                    error="TOTP not enrolled",
                )
            ok = verify_totp(secret, code)
            return VerificationResult(
                success=ok, method=method, user_id=user_id,
                consumed=False,
                error=None if ok else "invalid TOTP",
            )

        # ── Backup code ────────────────────────────────────────────────
        if method == MFAMethod.BACKUP:
            hashes = self._user_backup_codes.get(user_id, [])
            code_hash = _hash_code(code)
            if code_hash in hashes:
                self._user_backup_codes[user_id] = [h for h in hashes if h != code_hash]
                return VerificationResult(
                    success=True, method=method, user_id=user_id,
                    consumed=True,
                    remaining_backup_codes=len(self._user_backup_codes[user_id]),
                )
            return VerificationResult(
                success=False, method=method, user_id=user_id,
                consumed=False, error="invalid backup code",
            )

        # ── SMS / Email — 必须有 challenge_id ──────────────────────────
        if method in (MFAMethod.SMS, MFAMethod.EMAIL):
            if not challenge_id:
                return VerificationResult(
                    success=False, method=method, user_id=user_id,
                    error="challenge_id required for SMS/Email OTP",
                )
            ch = self._pending_challenges.pop(challenge_id, None)
            if not ch:
                return VerificationResult(
                    success=False, method=method, user_id=user_id,
                    error="challenge not found or already consumed",
                )
            if ch["user_id"] != user_id:
                return VerificationResult(
                    success=False, method=method, user_id=user_id,
                    error="challenge belongs to a different user",
                )
            expires_at = datetime.fromisoformat(ch["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                return VerificationResult(
                    success=False, method=method, user_id=user_id,
                    consumed=True, error="OTP expired",
                )
            if hmac.compare_digest(ch["code_hash"], _hash_code(code)):
                return VerificationResult(
                    success=True, method=method, user_id=user_id, consumed=True,
                )
            return VerificationResult(
                success=False, method=method, user_id=user_id,
                consumed=True, error="incorrect OTP",
            )

        return VerificationResult(
            success=False, method=method, user_id=user_id,
            error=f"unsupported method: {method}",
        )

    # ── Inspect / 测试钩子 ───────────────────────────────────────────────
    def _peek_pending_code(self, challenge_id: str) -> Optional[str]:
        """测试辅助:返回最近一次 SMS/Email challenge 的明文 code. 仅测试用."""
        ch = self._pending_challenges.get(challenge_id)
        if not ch:
            return None
        # 暴力反查:由于存的是 hash,真实系统拿不到明文. 仅测试场景通过 _pending_challenges 的辅助 map 还原.
        return getattr(ch, "_plain_code", None)

    def _store_plain_for_test(self, challenge_id: str, code: str) -> None:
        """测试用:把明文 OTP 暂存在 challenge 上以便断言 round-trip."""
        ch = self._pending_challenges.get(challenge_id)
        if ch is not None:
            ch["_plain_code"] = code


__all__ = [
    "MFAManager",
    "generate_totp_secret",
    "get_provisioning_uri",
    "verify_totp",
]