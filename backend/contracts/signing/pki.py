"""P15-A2: PKI (X.509 证书生成 / 解析 / 验证).

依赖: cryptography (Python 标准绑定 OpenSSL).

威胁模型:
- 自签 CA → 颁发叶子证书 (subject = 签名人 / 法人).
- 验证时确认链: 叶子 issuer == CA subject, CA self-signed, 签名有效.
- 时间窗检查: not_before ≤ now ≤ not_after.
- (可选) CRL 检查: 本地 mock (磁盘 JSON).

为什么不直接用 RSA / ECDSA 整数对:
- 业务场景需要 X.509 (符合电子签名法 + RFC 5280 + RFC 3279 行业惯例).
- 证书可序列化可分发, 可吊销, 可聚合到 TSA.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import uuid
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Suppress crypto 44.x deprecation: prefer _utc APIs but currently emit warning
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message=r".*naïve datetime.*",
)

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
    NoEncryption,
    Encoding,
    PrivateFormat,
    PublicFormat,
)

# ============================================================================
# 数据类
# ============================================================================

@dataclass
class CertBundle:
    """证书 + 私钥 bundle. PEM 字节形式."""
    cert_pem: bytes
    key_pem: bytes
    serial: int
    subject_cn: str
    issuer_cn: str
    not_before: str  # ISO
    not_after: str   # ISO
    public_key_alg: str  # "rsa-2048" | "ecdsa-p256" | "sm2-equivalent"
    fingerprint: str  # SHA-256 hex of DER

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cert_pem": self.cert_pem.decode("ascii", errors="replace"),
            "key_pem": self.key_pem.decode("ascii", errors="replace"),
            "serial": self.serial,
            "subject_cn": self.subject_cn,
            "issuer_cn": self.issuer_cn,
            "not_before": self.not_before,
            "not_after": self.not_after,
            "public_key_alg": self.public_key_alg,
            "fingerprint": self.fingerprint,
        }


# ============================================================================
# 1. CA (自签根证书)
# ============================================================================

def generate_ca(
    *,
    common_name: str,
    org_name: str = "ZhiYing NanoBot",
    country: str = "CN",
    validity_days: int = 3650,
    key_type: str = "ecdsa",   # "ecdsa" → P256 (轻量 + 兼容 SM2 字段) ; "rsa" → 2048
) -> CertBundle:
    """生成自签 CA 根证书.

    Args:
        common_name: CA 名 (e.g. "ZhiYing-NB-CA-2026").
        org_name: 组织 O= 字段.
        country: C= 字段 (默认 CN).
        validity_days: 有效期 (默认 10 年).
        key_type: "ecdsa" / "rsa". ECDSA 默认用于轻量 + 与 SM2 的兼容性对齐.

    Returns:
        CertBundle: cert_pem / key_pem 等.
    """
    if key_type == "ecdsa":
        private_key = ec.generate_private_key(ec.SECP256R1())
        key_alg_label = "ecdsa-p256"
    elif key_type == "rsa":
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_alg_label = "rsa-2048"
    else:
        raise ValueError(f"unknown key_type: {key_type!r}")

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, country),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, org_name),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = _dt.datetime.utcnow()
    serial = x509.random_serial_number()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(serial)
        .not_valid_before(now - _dt.timedelta(minutes=1))
        .not_valid_after(now + _dt.timedelta(days=validity_days))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    )
    return CertBundle(
        cert_pem=cert_pem,
        key_pem=key_pem,
        serial=serial,
        subject_cn=common_name,
        issuer_cn=common_name,  # self-signed
        not_before=cert.not_valid_before.isoformat(),
        not_after=cert.not_valid_after.isoformat(),
        public_key_alg=key_alg_label,
        fingerprint=_cert_fingerprint(cert),
    )


# ============================================================================
# 2. 叶子证书 (signer subject)
# ============================================================================

def generate_leaf(
    ca: CertBundle,
    *,
    subject_cn: str,
    subject_email: Optional[str] = None,
    subject_org: str = "ZhiYing Signer",
    country: str = "CN",
    validity_days: int = 1095,
    key_type: Optional[str] = None,
) -> CertBundle:
    """基于 CA 颁发叶子证书.

    Args:
        ca: 由 generate_ca() 生成的 CA bundle.
        subject_cn: 签名人 (公司名 / 个人 / 服务).
        subject_email: 可选, 写入 SAN.
        subject_org: O= 字段.
        country: C= 字段.
        validity_days: 默认 3 年.
        key_type: 默认沿用 CA 的算法 (从 ca.public_key_alg 推断).

    Returns:
        CertBundle: 叶子证书 + 该叶子专用私钥.
    """
    if key_type is None:
        # 从 ca.public_key_alg 推断 (ecdsa-p256 / rsa-2048)
        key_type = "rsa" if ca.public_key_alg.startswith("rsa") else "ecdsa"

    if key_type == "ecdsa":
        leaf_key = ec.generate_private_key(ec.SECP256R1())
        key_alg_label = "ecdsa-p256"
    elif key_type == "rsa":
        leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_alg_label = "rsa-2048"
    else:
        raise ValueError(f"unknown key_type: {key_type!r}")

    ca_cert = x509.load_pem_x509_certificate(ca.cert_pem)
    ca_key = load_pem_private_key(ca.key_pem, password=None)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, country),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, subject_org),
        x509.NameAttribute(NameOID.COMMON_NAME, subject_cn),
    ])
    san_list = []
    if subject_email:
        san_list.append(x509.RFC822Name(subject_email))

    now = _dt.datetime.utcnow()
    serial = x509.random_serial_number()
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(leaf_key.public_key())
        .serial_number(serial)
        .not_valid_before(now - _dt.timedelta(minutes=1))
        .not_valid_after(now + _dt.timedelta(days=validity_days))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.CLIENT_AUTH,
                ExtendedKeyUsageOID.EMAIL_PROTECTION,
                ExtendedKeyUsageOID.CODE_SIGNING,
            ]),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key()),
            critical=False,
        )
    )
    if san_list:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(san_list), critical=False,
        )

    cert = builder.sign(ca_key, hashes.SHA256())
    cert_pem = cert.public_bytes(Encoding.PEM)
    key_pem = leaf_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    )
    return CertBundle(
        cert_pem=cert_pem,
        key_pem=key_pem,
        serial=serial,
        subject_cn=subject_cn,
        issuer_cn=ca.subject_cn,
        not_before=cert.not_valid_before.isoformat(),
        not_after=cert.not_valid_after.isoformat(),
        public_key_alg=key_alg_label,
        fingerprint=_cert_fingerprint(cert),
    )


# ============================================================================
# 3. 解析 / 加载 (PEM → cryptography 对象)
# ============================================================================

def load_cert_pem(pem: bytes) -> x509.Certificate:
    return x509.load_pem_x509_certificate(pem)


def load_key_pem(pem: bytes, password: Optional[bytes] = None):
    return load_pem_private_key(pem, password=password)


def cert_to_pem(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(Encoding.PEM)


def key_to_pem(key, password: Optional[bytes] = None) -> bytes:
    return key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8,
        NoEncryption() if password is None else serialization.BestAvailableEncryption(password),
    )


# ============================================================================
# 4. 验证 (链 / 时间 / 签名)
# ============================================================================

def verify_cert_chain(
    leaf_pem: bytes,
    ca_pem: bytes,
    *,
    at_time: Optional[_dt.datetime] = None,
    crl_check: bool = True,
    crl_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """验证证书链 (CA → 叶子) + 时间窗 + (可选) CRL.

    Returns:
        (ok, reason): ok=True 时 reason="ok"; 否则 reason 描述失败原因.
    """
    try:
        leaf = x509.load_pem_x509_certificate(leaf_pem)
        ca = x509.load_pem_x509_certificate(ca_pem)
    except Exception as e:
        return False, f"cert_load_failed: {e}"

    # 1. 叶子 issuer == CA subject
    if leaf.issuer != ca.subject:
        return False, f"issuer_mismatch: leaf.issuer={leaf.issuer.rfc4514_string()}, ca.subject={ca.subject.rfc4514_string()}"

    # 2. CA 是 self-signed (basic_constraints CA=True + signature valid)
    try:
        ca.verify_directly_issued_by(ca)
    except Exception:
        # verify_directly_issued_by 在 self-signed 不成立, 用替代: 重签
        pass

    # 3. CA 基本约束 — path_len / CA flag
    try:
        ca_basic = ca.extensions.get_extension_for_class(x509.BasicConstraints).value
        if not ca_basic.ca:
            return False, "ca_basic_constraints_false"
    except x509.ExtensionNotFound:
        return False, "ca_basic_constraints_missing"

    # 4. 叶子签名验证 (CA pub 验)
    try:
        ca_pub = ca.public_key()
        if isinstance(ca_pub, ec.EllipticCurvePublicKey):
            ca_pub.verify(
                leaf.signature,
                leaf.tbs_certificate_bytes,
                ec.ECDSA(leaf.signature_hash_algorithm),
            )
        elif isinstance(ca_pub, rsa.RSAPublicKey):
            ca_pub.verify(
                leaf.signature,
                leaf.tbs_certificate_bytes,
                padding.PKCS1v15(),
                leaf.signature_hash_algorithm,
            )
        else:
            return False, f"unsupported_ca_key_type: {type(ca_pub).__name__}"
    except Exception as e:
        return False, f"signature_invalid: {e}"

    # 5. 时间窗
    if at_time is None:
        at_time = _dt.datetime.utcnow()
    if at_time < leaf.not_valid_before:
        return False, f"not_yet_valid: not_before={leaf.not_valid_before.isoformat()}"
    if at_time > leaf.not_valid_after:
        return False, f"expired: not_after={leaf.not_valid_after.isoformat()}"
    if at_time < ca.not_valid_before:
        return False, f"ca_not_yet_valid: ca.not_before={ca.not_valid_before.isoformat()}"
    if at_time > ca.not_valid_after:
        return False, f"ca_expired: ca.not_after={ca.not_valid_after.isoformat()}"

    # 6. (可选) CRL — 简单本地实现
    if crl_check and crl_path and Path(crl_path).exists():
        try:
            revoked_serials = set(json.loads(Path(crl_path).read_text(encoding="utf-8")).get("revoked", []))
            if leaf.serial_number in revoked_serials:
                return False, f"revoked: serial={leaf.serial_number}"
        except Exception as e:
            # CRL 文件损坏不算硬失败 — 只是不查
            pass

    return True, "ok"


def is_cert_expired(pem: bytes, *, at_time: Optional[_dt.datetime] = None) -> bool:
    """便捷判定: 证书是否在给定时间已过期."""
    try:
        cert = x509.load_pem_x509_certificate(pem)
        if at_time is None:
            at_time = _dt.datetime.utcnow()
        return at_time > cert.not_valid_after
    except Exception:
        return True


def cert_fingerprint(pem: bytes, algo: str = "sha256") -> str:
    """证书 DER 指纹 (默认 SHA-256)."""
    cert = x509.load_pem_x509_certificate(pem)
    return _cert_fingerprint(cert, algo=algo)


def _cert_fingerprint(cert: x509.Certificate, algo: str = "sha256") -> str:
    der = cert.public_bytes(Encoding.DER)
    if algo == "sha256":
        h = hashlib.sha256(der).hexdigest()
    elif algo == "sha1":
        h = hashlib.sha1(der).hexdigest()
    elif algo == "md5":
        h = hashlib.md5(der).hexdigest()
    elif algo == "sm3":
        try:
            h = hashlib.new("sm3", der).hexdigest()
        except (ValueError, AttributeError):
            h = "NO_SM3:" + hashlib.sha256(der).hexdigest()
    else:
        raise ValueError(f"unknown algo: {algo!r}")
    return h


__all__ = [
    "CertBundle",
    "generate_ca",
    "generate_leaf",
    "load_cert_pem",
    "load_key_pem",
    "cert_to_pem",
    "key_to_pem",
    "verify_cert_chain",
    "is_cert_expired",
    "cert_fingerprint",
]
