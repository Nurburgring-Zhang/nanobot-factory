"""V5 第40章 — imdf.security 子包: SSO + MFA + ABAC + C2PA + OWASP + PII.

模块结构:
  * sso_mfa_c2pa_schemas.py — 4 类共享 Pydantic v2 schemas (SSO/MFA/ABAC/C2PA)
  * sso.py                  — SSOManager (SAML/OAuth2/OIDC/LDAP)
  * mfa.py                  — MFAManager (TOTP RFC 6238 / SMS / Email / Backup)
  * abac.py                 — ABACEngine (3 built-in policies + enforce)
  * c2pa.py                 — C2PASigner / Verifier / Store (Ed25519)
  * owasp_protection.py     — OWASPProtection (10 inner classes) + 聚合入口
  * pii_redaction.py        — PIIRedactor (5 类 detector) + redact()
  * schemas.py              — OWASP/PII 共享 Pydantic v2 schemas
  * tests/                  — ≥80 tests (sso_mfa_c2pa + owasp + pii)

第40章合并包: 多个并行 worker 写不同模块, 顶层 __all__ 合并所有公开符号.
"""
from .abac import ABACEngine
from .c2pa import C2PASigner, C2PAStore, C2PAVerifier, read_sidecar, write_sidecar
from .mfa import MFAManager, generate_totp_secret, get_provisioning_uri, verify_totp
from .owasp_protection import (
    OWASPProtection,
    AccessControl,
    Cryptographic,
    IdentificationAuth,
    Injection,
    IntegrityFailures,
    LoggingMonitoring,
    SecureDesign,
    SecurityConfig,
    SSRFProtection,
    VulnerableComponents,
)
from .pii_redaction import PIIRedactor
from .schemas import (
    DetectedPII,
    JWTPayload,
    PermissionDecision,
    PIIType,
    ProtectedRequest,
    RedactionResult,
    SecurityEvent,
)
from .sso import SSOManager
from .sso_mfa_c2pa_schemas import (
    ABACDecision,
    ABACPolicy,
    AuthResult,
    C2PAAction,
    C2PAIngredient,
    C2PAManifest,
    C2PAVerificationResult,
    ChallengeResult,
    Condition,
    ConditionOp,
    EnrollmentResult,
    MFAMethod,
    OIDCConfig,
    SSOProvider,
    VerificationResult,
)

__all__ = [
    # ── SSO / MFA / ABAC / C2PA (平行 worker p19_v54_sso_mfa_c2pa) ──
    "ABACEngine",
    "C2PASigner", "C2PAStore", "C2PAVerifier",
    "MFAManager",
    "SSOManager",
    "generate_totp_secret", "get_provisioning_uri", "verify_totp",
    "read_sidecar", "write_sidecar",
    "AuthResult", "OIDCConfig", "SSOProvider",
    "EnrollmentResult", "ChallengeResult", "VerificationResult", "MFAMethod",
    "ABACPolicy", "ABACDecision", "Condition", "ConditionOp",
    "C2PAManifest", "C2PAAction", "C2PAIngredient", "C2PAVerificationResult",
    # ── OWASP Top 10 防护 (本任务 p19_v54_owasp_pii) ──
    "OWASPProtection",
    "AccessControl", "Cryptographic", "Injection", "SecureDesign",
    "SecurityConfig", "VulnerableComponents", "IdentificationAuth",
    "IntegrityFailures", "LoggingMonitoring", "SSRFProtection",
    # ── PII 5 类脱敏 (本任务 p19_v54_owasp_pii) ──
    "PIIRedactor",
    # ── 共享 Pydantic v2 schemas (本任务) ──
    "DetectedPII", "JWTPayload", "PermissionDecision",
    "PIIType", "ProtectedRequest", "RedactionResult", "SecurityEvent",
]