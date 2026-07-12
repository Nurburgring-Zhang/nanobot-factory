"""P15-A2: 签名器 + 验证器工厂 (根据 SIGN_MODE 决定).

公开入口:
- get_signer(mode=...) → BaseSigner 实例
- ensure_dev_ca() → CertBundle (CA 持久化到 backend/data/contracts_ca.pem)
- SignMode: 类型常量 (enum-like)
"""
from __future__ import annotations

import json
import os
import threading
from enum import Enum
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key, NoEncryption, Encoding, PrivateFormat

from .pki import (
    CertBundle,
    generate_ca,
    generate_leaf,
    load_cert_pem,
    load_key_pem,
)
from .signers import (
    BaseSigner,
    SM2Signer,
    ECDSASigner,
    RSASigner,
    HMACSM3Signer,
    SignResult,
)


class SignMode(str, Enum):
    SM2 = "sm2"
    ECDSA = "ecdsa"
    RSA = "rsa"

    @classmethod
    def from_env(cls) -> "SignMode":
        v = os.getenv("SIGN_MODE", "ecdsa").lower().strip()
        if v in ("sm2", "sm3-fallback"):
            return cls.SM2
        if v in ("ecdsa", "ecdsa-p256", "p256"):
            return cls.ECDSA
        if v in ("rsa", "rsa-2048-pss"):
            return cls.RSA
        # 默认 ECDSA
        return cls.ECDSA


# ============================================================================
# Default CA persistence — 单例: backend/data/contracts_ca.{pem,key}
# ============================================================================

def _default_ca_path() -> Path:
    base = Path(__file__).resolve().parent.parent.parent / "data"
    custom = os.getenv("CONTRACT_CA_DIR")
    p = Path(custom) if custom else base
    p.mkdir(parents=True, exist_ok=True)
    return p


def _default_ca_files() -> tuple[Path, Path]:
    d = _default_ca_path()
    return (d / "contracts_ca.pem", d / "contracts_ca.key")


_CA_LOCK = threading.Lock()
_DEV_CA: Optional[CertBundle] = None


def ensure_dev_ca(force_new: bool = False) -> CertBundle:
    """返回 / 创建开发 CA.

    流程:
    1. 读 CONTRACT_CA_CERT_PATH / CONTRACT_CA_KEY_PATH (env override).
    2. 读 default path (backend/data/contracts_ca.{pem,key}).
    3. 不存在则生成新的 ECDSA CA, 落盘.
    """
    global _DEV_CA
    with _CA_LOCK:
        if _DEV_CA is not None and not force_new:
            return _DEV_CA

        # 1. env override
        env_cert = os.getenv("CONTRACT_CA_CERT_PATH")
        env_key = os.getenv("CONTRACT_CA_KEY_PATH")
        if env_cert and env_key and Path(env_cert).exists() and Path(env_key).exists():
            cert_pem = Path(env_cert).read_bytes()
            key_pem = Path(env_key).read_bytes()
            try:
                cert = load_cert_pem(cert_pem)
                fingerprint = _pem_fingerprint(cert_pem)
                _DEV_CA = CertBundle(
                    cert_pem=cert_pem,
                    key_pem=key_pem,
                    serial=cert.serial_number,
                    subject_cn=cert.subject.rfc4514_string().split("CN=", 1)[-1].split(",", 1)[0],
                    issuer_cn=cert.issuer.rfc4514_string().split("CN=", 1)[-1].split(",", 1)[0],
                    not_before=cert.not_valid_before.isoformat(),
                    not_after=cert.not_valid_after.isoformat(),
                    public_key_alg="from-env",
                    fingerprint=fingerprint,
                )
                return _DEV_CA
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("env CA load failed: %s, generating new", e)

        # 2. default path
        cert_path, key_path = _default_ca_files()
        if cert_path.exists() and key_path.exists() and not force_new:
            cert_pem = cert_path.read_bytes()
            key_pem = key_path.read_bytes()
            try:
                cert = load_cert_pem(cert_pem)
                _DEV_CA = CertBundle(
                    cert_pem=cert_pem,
                    key_pem=key_pem,
                    serial=cert.serial_number,
                    subject_cn=cert.subject.rfc4514_string().split("CN=", 1)[-1].split(",", 1)[0],
                    issuer_cn=cert.issuer.rfc4514_string().split("CN=", 1)[-1].split(",", 1)[0],
                    not_before=cert.not_valid_before.isoformat(),
                    not_after=cert.not_valid_after.isoformat(),
                    public_key_alg="ecdsa-p256",
                    fingerprint=_pem_fingerprint(cert_pem),
                )
                return _DEV_CA
            except Exception:
                pass  # 文件损坏, 重新生成

        # 3. 新建
        ca = generate_ca(
            common_name=os.getenv("CONTRACT_CA_CN", "ZhiYing-NB-CA-2026"),
            validity_days=int(os.getenv("CONTRACT_CA_VALIDITY_DAYS", "3650")),
            key_type="ecdsa",
        )
        cert_path.write_bytes(ca.cert_pem)
        key_path.write_bytes(ca.key_pem)
        try:
            os.chmod(key_path, 0o600)
        except Exception:
            pass
        _DEV_CA = ca
        return _DEV_CA


def _pem_fingerprint(cert_pem: bytes) -> str:
    """Compute SHA-256 of DER (用于缓存 fingerprint)."""
    import hashlib
    from cryptography import x509
    cert = x509.load_pem_x509_certificate(cert_pem)
    return hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest()


# ============================================================================
# 颁发叶子证书
# ============================================================================

def issue_leaf_for_subject(
    subject_cn: str,
    *,
    subject_email: Optional[str] = None,
    subject_org: str = "ZhiYing Signer",
    validity_days: int = 1095,
) -> CertBundle:
    """基于默认 CA 颁发叶子证书."""
    ca = ensure_dev_ca()
    return generate_leaf(
        ca,
        subject_cn=subject_cn,
        subject_email=subject_email,
        subject_org=subject_org,
        validity_days=validity_days,
    )


# ============================================================================
# 工厂入口
# ============================================================================

def get_signer(
    *,
    mode: Optional[SignMode] = None,
    key_pem: Optional[bytes] = None,
    cert: Optional[CertBundle] = None,
):
    """默认根据 SIGN_MODE 选 signer."""
    if mode is None:
        mode = SignMode.from_env()
    if key_pem is None:
        raise ValueError(
            "key_pem required (or pass a CertBundle via cert=); "
            "for production use issue_leaf_for_subject() first."
        )
    if mode == SignMode.SM2:
        return SM2Signer(key_pem, cert=cert)
    if mode == SignMode.ECDSA:
        return ECDSASigner(key_pem, cert=cert)
    if mode == SignMode.RSA:
        return RSASigner(key_pem, cert=cert)
    raise ValueError(f"unsupported mode: {mode!r}")


def reset_ca_for_tests() -> None:
    """测试用 — 清空 CA singleton."""
    global _DEV_CA
    _DEV_CA = None


__all__ = [
    "SignMode",
    "ensure_dev_ca",
    "issue_leaf_for_subject",
    "get_signer",
    "reset_ca_for_tests",
]
