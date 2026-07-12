"""P15-A2: 第三方电子签名 (PKI) 子包.

设计目标 (F-6.7):
- 真实 PKI 证书链 (X.509) — 自签 CA → 叶子证书
- 3 种签名算法: SM2 (国密) / ECDSA-P256 / RSA-2048-PSS
- RFC 3161 时间戳 (本地 TSA, 可选外部)
- 验证器: 证书链 + 签名 + 时间戳 + 时间有效性 + (可选) 吊销
- 审计日志: 每次签/验都记录 (signer / doc_hash / sig / ts / cert_serial / result)
- 工厂模式: SIGN_MODE 环境变量切换

模块构成:
- pki.py         X.509 证书生成 / 解析 / 验证
- signers.py     SM2 / ECDSA / RSA 签名器
- timestamp.py   RFC 3161 时间戳 (本地 + 可选外部)
- verifier.py    签名验证 (链 + 时戳 + 时间)
- audit.py       审计日志 (本地 JSONL, 复用 P10-A 模式)
- factory.py     签名器 + 验证器工厂 (由 SIGN_MODE 决定)

环境变量:
- SIGN_MODE                sm2 | ecdsa | rsa (默认 ecdsa)
- CONTRACT_CA_CERT_PATH    CA 证书 PEM 路径 (None → 用开发 CA)
- CONTRACT_CA_KEY_PATH     CA 私钥 PEM 路径 (None → 用开发 CA)
- CONTRACT_AUDIT_LOG_PATH  审计日志路径 (默认 backend/logs/contracts_audit.jsonl)
- CONTRACT_TSA_URL         外部 TSA URL (None → 用本地)
"""
from .pki import (
    generate_ca,
    generate_leaf,
    load_cert_pem,
    load_key_pem,
    verify_cert_chain,
    cert_fingerprint,
    cert_to_pem,
    key_to_pem,
    is_cert_expired,
    CertBundle,
)
from .signers import (
    BaseSigner,
    SM2Signer,
    ECDSASigner,
    RSASigner,
    SignResult,
    sign_with_cert,
)
from .timestamp import (
    issue_timestamp,
    verify_timestamp,
    LocalTSA,
    TimestampToken,
    TIMESTAMP_GENESIS_HASH,
)
from .verifier import (
    SignedContract,
    VerifyResult,
    verify_signature,
)
from .audit import (
    audit_sign_event,
    audit_verify_event,
    read_audit_log,
    clear_audit_log,
    AuditEvent,
)
from .factory import (
    get_signer,
    ensure_dev_ca,
    issue_leaf_for_subject,
    SignMode,
)

__all__ = [
    # pki
    "generate_ca",
    "generate_leaf",
    "load_cert_pem",
    "load_key_pem",
    "verify_cert_chain",
    "cert_fingerprint",
    "cert_to_pem",
    "key_to_pem",
    "is_cert_expired",
    "CertBundle",
    # signers
    "BaseSigner",
    "SM2Signer",
    "ECDSASigner",
    "RSASigner",
    "SignResult",
    "sign_with_cert",
    # timestamp
    "issue_timestamp",
    "verify_timestamp",
    "LocalTSA",
    "TimestampToken",
    "TIMESTAMP_GENESIS_HASH",
    # verifier
    "SignedContract",
    "VerifyResult",
    "verify_signature",
    # audit
    "audit_sign_event",
    "audit_verify_event",
    "read_audit_log",
    "clear_audit_log",
    "AuditEvent",
    # factory
    "get_signer",
    "ensure_dev_ca",
    "SignMode",
]
