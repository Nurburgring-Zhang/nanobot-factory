"""P15-A2: 签名验证器.

流程:
1. 验证书链 (CA → 叶子) — 时间窗 / CA 标志 / 签名有效.
2. 验签 (按 alg 调对应 verify).
3. 验时间戳 (HMAC 链 + 公指纹匹配 + 可选 doc_hash 匹配).
4. 返回 VerifyResult.

VerifyResult 字段:
    ok: bool
    reasons: List[str]       # 每条失败一项原因
    cert_serial, cert_subject, cert_fingerprint
    signature_alg, signature_value_b64
    timestamp_token_id, timestamp_signed_at
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from .pki import (
    CertBundle,
    load_cert_pem,
    verify_cert_chain,
    cert_fingerprint,
    is_cert_expired,
)
from .signers import SignResult
from .timestamp import TimestampToken, verify_timestamp, LocalTSA
from .audit import audit_verify_event  # noqa: E402  (delayed to break verifier ↔ audit cycle)

logger = logging.getLogger(__name__)


# ============================================================================
# Data classes
# ============================================================================

@dataclass
class SignedContract:
    """完整签名包 — 包含合同 + 证书链 + 签名值 + 时间戳."""
    contract_id: str
    doc_hash: str              # SHA-256 hex of canonical doc bytes
    alg: str
    signature_b64: str
    cert_pem: str              # 叶子证书 PEM
    ca_cert_pem: str           # CA 证书 PEM (打包, 便于传输 / 长期验证)
    cert_serial: int
    cert_subject_cn: str
    cert_issuer_cn: str
    cert_fingerprint: str      # SHA-256 指纹
    timestamp: Dict[str, Any] = field(default_factory=dict)  # TimestampToken dict
    signed_at: Optional[str] = None
    signed_by: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "doc_hash": self.doc_hash,
            "alg": self.alg,
            "signature_b64": self.signature_b64,
            "cert_pem": self.cert_pem,
            "ca_cert_pem": self.ca_cert_pem,
            "cert_serial": self.cert_serial,
            "cert_subject_cn": self.cert_subject_cn,
            "cert_issuer_cn": self.cert_issuer_cn,
            "cert_fingerprint": self.cert_fingerprint,
            "timestamp": self.timestamp,
            "signed_at": self.signed_at,
            "signed_by": self.signed_by,
            "extra": self.extra,
        }


@dataclass
class VerifyResult:
    ok: bool
    reasons: List[str] = field(default_factory=list)
    cert_serial: Optional[int] = None
    cert_subject: Optional[str] = None
    cert_issuer: Optional[str] = None
    cert_fingerprint: Optional[str] = None
    signature_alg: Optional[str] = None
    signature_value_b64: Optional[str] = None
    doc_hash: Optional[str] = None
    timestamp_token_id: Optional[str] = None
    timestamp_signed_at: Optional[str] = None
    verified_at: str = field(default_factory=lambda: _dt.datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# 签名验证 — 内部: 按 alg 校验 sig bytes
# ============================================================================

def _verify_signature_bytes(
    sig: bytes,
    doc_bytes: bytes,
    alg: str,
    public_key,
) -> Tuple[bool, str]:
    if alg in ("ecdsa", "ecdsa-p256", "sm2-fallback-ecdsa-p256"):
        try:
            public_key.verify(sig, doc_bytes, ec.ECDSA(hashes.SHA256()))
            return True, "ok"
        except Exception as e:
            return False, f"signature_invalid: {e}"
    if alg in ("rsa", "rsa-2048-pss"):
        try:
            public_key.verify(
                sig,
                doc_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True, "ok"
        except Exception as e:
            return False, f"signature_invalid: {e}"
    if alg == "sm2-p256-sm3":
        # P15-B: SM2-style fallback (NIST P-256 + SM3 with ZA preprocessing
        # per GM/T 0003-2012 §6.1). Recompute ZA from the public key (must
        # match what the signer computed) and verify the inner SM3 digest.
        try:
            import hashlib
            from .signers import _sm2_za, _sm3_hash
            za = _sm2_za(public_key)
            inner = hashlib.new("sm3", za + doc_bytes).digest()
            public_key.verify(sig, inner, ec.ECDSA(hashes.SHA256()))
            return True, "ok"
        except Exception as e:
            return False, f"signature_invalid: {e}"
    if alg == "sm2-fallback-sha256":
        # Legacy compatibility path: ECDSA-P256 over SHA-256(doc_bytes).
        try:
            public_key.verify(sig, doc_bytes, ec.ECDSA(hashes.SHA256()))
            return True, "ok"
        except Exception as e:
            return False, f"signature_invalid: {e}"
    if alg in ("hmac-sm3", "sm2-gmssl"):
        # HMAC-SM3 / 纯 SM2 在 verifier 流程不通用 — 仅在工厂模式下特殊处理
        return False, f"algorithm {alg!r} requires out-of-band verification"
    return False, f"unknown algorithm: {alg!r}"


# ============================================================================
# 公开 API
# ============================================================================

def verify_signature(
    sc: SignedContract,
    *,
    doc_bytes: Optional[bytes] = None,
    expected_doc_hash: Optional[str] = None,
    at_time: Optional[_dt.datetime] = None,
    crl_path: Optional[str] = None,
    audit: bool = True,
) -> VerifyResult:
    """完整验证流程.

    Args:
        sc: 已打包的 SignedContract.
        doc_bytes: 合同原始字节 (None → 跳过 doc_hash 强校验, 仅验证书 + 时戳 + 签名 alg 字段一致).
        expected_doc_hash: 期望的 doc_hash. None → 不强校验.
        at_time: 验证时刻 (默认 now). 用于证书时间窗.
        crl_path: 可选 CRL 文件路径.
        audit: 是否写入 audit log (默认 True).

    Returns:
        VerifyResult: 含 ok / reasons / 各字段摘要.
    """
    res = VerifyResult(
        ok=False,
        cert_serial=sc.cert_serial,
        cert_subject=sc.cert_subject_cn,
        cert_issuer=sc.cert_issuer_cn,
        cert_fingerprint=sc.cert_fingerprint,
        signature_alg=sc.alg,
        signature_value_b64=sc.signature_b64,
        doc_hash=sc.doc_hash,
        timestamp_token_id=sc.timestamp.get("token_id") if sc.timestamp else None,
        timestamp_signed_at=sc.timestamp.get("signed_at") if sc.timestamp else None,
    )

    # 1. 证书链 + 时间窗
    cert_pem = sc.cert_pem.encode("ascii") if isinstance(sc.cert_pem, str) else sc.cert_pem
    ca_pem = sc.ca_cert_pem.encode("ascii") if isinstance(sc.ca_cert_pem, str) else sc.ca_cert_pem
    chain_ok, chain_reason = verify_cert_chain(
        cert_pem,
        ca_pem,
        at_time=at_time,
        crl_path=crl_path,
    )
    if not chain_ok:
        res.reasons.append(f"cert_chain: {chain_reason}")

    # 2. 签名 (按 alg)
    try:
        leaf_cert = load_cert_pem(cert_pem)
        pubkey = leaf_cert.public_key()
    except Exception as e:
        res.reasons.append(f"cert_load: {e}")
        if audit:
            audit_verify_event(sc.contract_id, res)
        return res

    sig_bytes = base64.b64decode(sc.signature_b64)
    target_doc = doc_bytes if doc_bytes is not None else None
    if target_doc is None:
        # 无原始字节: 仅验证签名 alg 字段 & 证书字段, 跳过 signature 字节检查
        res.reasons.append("no_doc_bytes_provided: skipped_signature_verification")
    else:
        # P15-B: doc_hash is algorithm-dependent. For ``sm2-p256-sm3`` the
        # signer hashes ``SM3(ZA || doc_bytes)`` (per GM/T 0003-2012 §6.1
        # preprocessing), not the bare doc_bytes. Re-derive ZA from the
        # public key here so verifier and signer agree.
        if sc.alg == "sm2-p256-sm3":
            try:
                from .signers import _sm2_za
                za = _sm2_za(pubkey)
                target_hash = hashlib.new("sm3", za + target_doc).hexdigest()
            except Exception:
                target_hash = hashlib.sha256(target_doc).hexdigest()
        else:
            target_hash = hashlib.sha256(target_doc).hexdigest()
        if expected_doc_hash and expected_doc_hash != target_hash:
            res.reasons.append(
                f"doc_hash_mismatch: computed={target_hash[:16]}, expected={expected_doc_hash[:16]}"
            )
        if sc.doc_hash and sc.doc_hash != target_hash:
            res.reasons.append(
                f"signed_doc_hash_mismatch: signed={sc.doc_hash[:16]}, computed={target_hash[:16]}"
            )
        sig_ok, sig_reason = _verify_signature_bytes(sig_bytes, target_doc, sc.alg, pubkey)
        if not sig_ok:
            res.reasons.append(sig_reason)

    # 3. 时间戳
    if sc.timestamp:
        try:
            ts = TimestampToken(**sc.timestamp)
            ts_ok, ts_reason = verify_timestamp(ts, expected_doc_hash=sc.doc_hash)
            if not ts_ok:
                res.reasons.append(f"timestamp: {ts_reason}")
        except Exception as e:
            res.reasons.append(f"timestamp_parse: {e}")
    else:
        res.reasons.append("timestamp_missing")

    # 4. Final
    res.ok = len(res.reasons) == 0
    if audit:
        audit_verify_event(sc.contract_id, res)
    return res


__all__ = [
    "SignedContract",
    "VerifyResult",
    "verify_signature",
]
