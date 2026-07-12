"""V5 第40章 — OWASP Top 10 + PII 5 类脱敏 Pydantic v2 schemas.

公共数据类型:
  * PIIType        — 5 类 PII 枚举
  * DetectedPII    — 一次 PII 命中
  * RedactionResult — redact() 输出
  * SecurityEvent  — 审计事件
  * JWTPayload     — JWT claims
  * ProtectedRequest — protect_request() 输出
  * PermissionDecision — AccessControl.check_permission() 输出
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
#  PII 5 类
# ──────────────────────────────────────────────────────────────────────
class PIIType(str, Enum):
    """5 类 PII 枚举 — 身份证 / 手机号 / 邮箱 / 银行卡 / 姓名地址组合."""

    ID_CARD = "id_card"
    PHONE = "phone"
    EMAIL = "email"
    BANK_CARD = "bank_card"
    NAME_ADDRESS = "name_address"


class DetectedPII(BaseModel):
    """单条 PII 命中记录."""

    pii_type: PIIType
    original: str = Field(..., description="命中原文片段")
    redacted: str = Field(..., description="脱敏后片段 (e.g. ***-****-****)")
    start: int = Field(..., ge=0, description="在原文中的起始 offset")
    end: int = Field(..., ge=0, description="在原文中的结束 offset (exclusive)")
    confidence: float = Field(1.0, ge=0.0, le=1.0)

    model_config = {"extra": "allow"}


class RedactionResult(BaseModel):
    """PIIRedactor.redact() 的统一返回结构."""

    original_text: str
    redacted_text: str
    detected_pii: List[DetectedPII] = Field(default_factory=list)
    pii_count: int = 0

    model_config = {"extra": "allow"}

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# ──────────────────────────────────────────────────────────────────────
#  OWASP / 审计 / JWT
# ──────────────────────────────────────────────────────────────────────
class SecurityEvent(BaseModel):
    """安全审计事件 — LoggingMonitoring.SecurityEventLogger 输出."""

    event_type: str = Field(..., description="auth.login / auth.failed / access.denied / ...")
    actor: str = Field(..., description="触发该事件的用户 / 服务标识")
    payload: Dict[str, Any] = Field(default_factory=dict)
    severity: str = Field("info", description="debug / info / warn / error / critical")
    timestamp: str = ""
    topic: str = Field("security.event", description="bus topic, 默认 security.event")

    model_config = {"extra": "allow"}


class JWTPayload(BaseModel):
    """JWT 解码后的 claims — IdentificationAuth.JWTManager.verify 返回."""

    sub: str = Field(..., description="subject (user id)")
    roles: List[str] = Field(default_factory=list)
    exp: int = 0
    iat: int = 0
    iss: str = ""
    raw: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class PermissionDecision(BaseModel):
    """AccessControl.check_permission() 输出."""

    allowed: bool
    user: str
    resource: str
    action: str
    reason: str = ""

    model_config = {"extra": "allow"}


class ProtectedRequest(BaseModel):
    """OWASPProtection.protect_request() 的统一输出 — 聚合 10 个检查器的结果."""

    user: str
    resource: str
    action: str
    permission: PermissionDecision
    sanitized_input: Dict[str, Any] = Field(default_factory=dict)
    safe_path: Optional[str] = None
    ssrf_checked: bool = False
    rate_limit_ok: bool = True
    integrity_ok: bool = True
    config_snapshot: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)

    model_config = {"extra": "allow"}


__all__ = [
    "PIIType",
    "DetectedPII",
    "RedactionResult",
    "SecurityEvent",
    "JWTPayload",
    "PermissionDecision",
    "ProtectedRequest",
]