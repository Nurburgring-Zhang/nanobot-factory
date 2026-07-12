"""V5 第40章 — SSO/MFA/ABAC/C2PA 共享 Pydantic v2 schemas.

集中放置 auth + mfa + abac + c2pa 4 类的 input/output model,避免每个文件
重复定义.BaseModelConfig 统一开启 from_attributes + populate_by_name + extra=ignore
以兼容内部 dataclass / dict 输入.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Shared config ────────────────────────────────────────────────────────
class _Base(BaseModel):
    """所有 schema 共享的 config:从 dataclass/dict 都能构造."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )


# ════════════════════════════════════════════════════════════════════════
# SSO schemas
# ════════════════════════════════════════════════════════════════════════
class SSOProvider(str, Enum):
    SAML = "saml"
    OAUTH2 = "oauth2"
    OIDC = "oidc"
    LDAP = "ldap"


class AuthResult(_Base):
    """SSO 认证结果."""

    success: bool
    user_id: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    provider: SSOProvider
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    raw_claims: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class OIDCConfig(_Base):
    """OIDC discovery 文档的子集."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None
    scopes_supported: List[str] = Field(default_factory=list)
    response_types_supported: List[str] = Field(default_factory=list)
    subject_types_supported: List[str] = Field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════
# MFA schemas
# ════════════════════════════════════════════════════════════════════════
class MFAMethod(str, Enum):
    TOTP = "totp"
    SMS = "sms"
    EMAIL = "email"
    BACKUP = "backup"


class EnrollmentResult(_Base):
    """MFA 初始化注册结果 — TOTP 返回 provisioning_uri, SMS/Email 返回已发送."""

    success: bool
    method: MFAMethod
    secret: Optional[str] = None  # 仅 TOTP 用,base32 编码
    provisioning_uri: Optional[str] = None  # 仅 TOTP 用,otpauth://
    challenge_id: Optional[str] = None  # 用于 verify 时回查
    delivery_target: Optional[str] = None  # SMS/Email 的目标地址
    backup_codes: Optional[List[str]] = None  # 仅在 enroll backup 时返回
    expires_at: Optional[datetime] = None
    error: Optional[str] = None


class ChallengeResult(_Base):
    """MFA challenge 发起结果."""

    success: bool
    method: MFAMethod
    challenge_id: str
    delivery_target: Optional[str] = None  # SMS/Email 把验证码发到哪
    sent: bool = False  # 是否已真正发出 (mocked 时为 True)
    expires_at: Optional[datetime] = None
    error: Optional[str] = None


class VerificationResult(_Base):
    """MFA 验证结果."""

    success: bool
    method: MFAMethod
    user_id: str
    consumed: bool = False  # OTP / backup code 是否被消耗 (防止重放)
    remaining_backup_codes: Optional[int] = None
    error: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════
# ABAC schemas
# ════════════════════════════════════════════════════════════════════════
class ConditionOp(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    IN = "in"
    NOT_IN = "not_in"
    GT = "gt"
    LT = "lt"
    CONTAINS = "contains"  # list / str contains
    IN_ATTR = "in_attr"  # value 视为 attribute path,从 ctx 中动态解析 (用于 user.id IN resource.member_ids)


class Condition(_Base):
    """单条 ABAC 条件:  attribute operator value.

    attribute 支持 dot path (e.g. "user.id", "resource.owner_id",
    "context.time_of_day").  value 类型随 op 变化:eq/neq 任意;in/not_in
    必须 list; gt/lt 仅数字/可比较类型;contains 字符串子串或 list 成员;
    in_attr 时 value 是另一个 attribute path (例如 "resource.member_ids"),
    运行时从 ctx 动态解析.

    哨兵 "__SELF__" (向后兼容):
      * op=EQ / NEQ:  对应 user.id == resource.owner_id 等自指比较
      * op=IN / NOT_IN:  视为 IN_ATTR,attribute 的解析值作为 needle,
        value 路径解析为 list (向后兼容老语法)
    """

    attribute: str
    op: ConditionOp
    value: Any


class ABACPolicy(_Base):
    """一组策略 = resource + action + 全部条件 AND 求值."""

    name: str
    resource: str  # e.g. "project", "dataset", "user"
    action: str  # e.g. "read", "write", "delete"
    conditions: List[Condition] = Field(default_factory=list)
    effect: Literal["allow", "deny"] = "allow"
    description: str = ""


class ABACDecision(_Base):
    """ABAC enforce 决策."""

    allow: bool
    matched_policy: Optional[str] = None
    reason: str = ""
    user_id: Optional[str] = None
    resource: Optional[str] = None
    action: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════
# C2PA schemas
# ════════════════════════════════════════════════════════════════════════
class C2PAAction(_Base):
    """C2PA action assertion (c2pa.created / c2pa.edited / etc)."""

    action: str  # e.g. "c2pa.created", "c2pa.edited"
    when: Optional[datetime] = None
    software_agent: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class C2PAIngredient(_Base):
    """C2PA ingredient reference (parent asset)."""

    ingredient_id: str
    relationship: str  # "parentOf" / "componentOf" / etc
    asset_hash: str
    hash_algorithm: str = "sha256"
    url: Optional[str] = None
    manifest_url: Optional[str] = None


class C2PAManifest(_Base):
    """C2PA manifest — simplified for V5 ch.40."""

    manifest_id: str
    claim_generator: str
    claim_generator_info: List[Dict[str, Any]] = Field(default_factory=list)
    asset_hash: str
    hash_algorithm: str = "sha256"
    signature_algorithm: str = "ed25519"
    signature: str  # base64-encoded Ed25519 signature
    public_key: str  # base64-encoded Ed25519 public key (绑定 issuer)
    issued_at: datetime
    expires_at: Optional[datetime] = None
    actions: List[C2PAAction] = Field(default_factory=list)
    ingredients: List[C2PAIngredient] = Field(default_factory=list)
    claim: Dict[str, Any] = Field(default_factory=dict)
    manifest_hash: Optional[str] = None  # SHA-256(canonical manifest body)


class C2PAVerificationResult(_Base):
    """C2PA verify 输出."""

    valid: bool
    asset_hash_match: bool = False
    signature_valid: bool = False
    claim_generator_match: bool = False
    time_valid: bool = False
    reason: str = ""
    manifest_id: Optional[str] = None


__all__ = [
    # base
    "_Base",
    # SSO
    "SSOProvider",
    "AuthResult",
    "OIDCConfig",
    # MFA
    "MFAMethod",
    "EnrollmentResult",
    "ChallengeResult",
    "VerificationResult",
    # ABAC
    "ConditionOp",
    "Condition",
    "ABACPolicy",
    "ABACDecision",
    # C2PA
    "C2PAAction",
    "C2PAIngredient",
    "C2PAManifest",
    "C2PAVerificationResult",
]