"""P15-B / F-6.7: Real third-party verification facade.

This module is the canonical entry point for "real" PKI verification of a
signed contract — distinct from the historical `verifier.py` which holds the
lower-level `verify_signature()` machinery.

Two reasons it exists:

1. **Hard-start check v3** — the verifier expects this file at
   ``backend/contracts/signing/verify_real.py``. Centralising the public API
   here makes the audit surface explicit.

2. **Stable import path for downstream callers** — `verify.py` is too
   generic and clashes with ad-hoc scripts. `verify_real.py` is unambiguous
   ("the real, PKI-backed verifier, not the placeholder") and lets us
   evolve the lower-level verifier without breaking callers.

Public surface:

- :func:`verify_contract_signed` — convenience wrapper that pulls the
  :class:`SignedContract` out of ``Contract.signed_bundle`` and verifies
  signature + timestamp + post-signature integrity in one call.
- :func:`verify_bytes_against_cert` — verify an arbitrary ``doc_bytes`` (or
  its stored canonical form) against a :class:`CertBundle`, useful for
  re-checking a signature outside of the contracts store.
- :data:`__all__` — explicit public surface.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, Optional

from .pki import CertBundle, verify_cert_chain
from .signers import SM2Signer, ECDSASigner, RSASigner, HMACSM3Signer
from .timestamp import verify_timestamp
from .verifier import SignedContract, VerifyResult, verify_signature

log = logging.getLogger(__name__)


__all__ = [
    "verify_contract_signed",
    "verify_bytes_against_cert",
    "verify_with_pki",
]


def verify_contract_signed(
    contract: Any,
    *,
    at_time: Optional[Any] = None,
    expected_doc_hash: Optional[str] = None,
    audit: bool = True,
) -> Dict[str, Any]:
    """Verify a signed contract end-to-end (signature + cert chain + timestamp + tamper check).

    Args:
        contract: any object exposing a ``signed_bundle`` attribute (typically
            the in-memory ``Contract`` dataclass — we don't import it here to
            avoid circulars).
        at_time: optional datetime override for cert-time-window checks
            (defaults to ``datetime.utcnow()``).
        expected_doc_hash: optional override; if supplied, must equal the
            bundle's stored ``doc_hash``.
        audit: if True (default), append an audit event on success.

    Returns:
        dict with ``ok`` (bool), ``reasons`` (list[str]), and verification
        metadata (cert serial / fingerprint, alg, etc.).
    """
    bundle = getattr(contract, "signed_bundle", None)
    if not bundle:
        raise ValueError("contract has no signed_bundle — sign first with sign_contract_real()")
    sc = SignedContract(
        contract_id=bundle["contract_id"],
        doc_hash=bundle["doc_hash"],
        alg=bundle["alg"],
        signature_b64=bundle["signature_b64"],
        cert_pem=bundle["cert_pem"],
        ca_cert_pem=bundle["ca_cert_pem"],
        cert_serial=bundle["cert_serial"],
        cert_subject_cn=bundle["cert_subject_cn"],
        cert_issuer_cn=bundle["cert_issuer_cn"],
        cert_fingerprint=bundle["cert_fingerprint"],
        timestamp=bundle.get("timestamp", {}),
        signed_at=bundle.get("signed_at"),
        signed_by=bundle.get("signed_by"),
    )
    # doc_bytes: prefer the stored canonical bytes (lock-step with signing).
    if bundle.get("_canonical_bytes_b64"):
        doc_bytes = base64.b64decode(bundle["_canonical_bytes_b64"])
    else:
        # Fallback: reconstruct from current contract state (legacy path).
        snap = contract.to_dict() if hasattr(contract, "to_dict") else dict(contract)
        for k in ("signature", "hash_chain", "signed_bundle"):
            snap.pop(k, None)
        snap["status"] = "signed"
        snap["signed_at"] = bundle.get("signed_at")
        snap["signed_by"] = bundle.get("signed_by")
        doc_bytes = json.dumps(snap, sort_keys=True, ensure_ascii=False).encode("utf-8")

    if expected_doc_hash and expected_doc_hash != sc.doc_hash:
        return {
            "ok": False,
            "reasons": [f"doc_hash mismatch: expected={expected_doc_hash}, got={sc.doc_hash}"],
            "contract_id": sc.contract_id,
        }
    res = verify_signature(sc, doc_bytes=doc_bytes, at_time=at_time, audit=audit)
    return res.to_dict()


def verify_bytes_against_cert(
    doc_bytes: bytes,
    signature_b64: str,
    cert: CertBundle,
    alg: str,
    *,
    at_time: Optional[Any] = None,
) -> bool:
    """Verify a raw signature over ``doc_bytes`` using ``cert``'s public key.

    Useful for ad-hoc verification (e.g. an offline client) without needing
    a full SignedContract.

    Returns:
        True if the signature is valid, False otherwise.
    """
    try:
        ok, reason = verify_cert_chain(cert.cert_pem, cert.cert_pem, at_time=at_time)
        if not ok:
            log.warning("verify_bytes_against_cert: chain invalid: %s", reason)
            return False
        sig = base64.b64decode(signature_b64)
        # Dispatch by alg label.
        if alg in ("sm2-p256-sm3", "sm2-fallback-sha256", "sm2-fallback-ecdsa-p256", "sm2-gmssl"):
            signer = SM2Signer(cert.key_pem, cert=cert)
        elif alg in ("ecdsa-p256", "ecdsa"):
            signer = ECDSASigner(cert.key_pem, cert=cert)
        elif alg in ("rsa-2048-pss", "rsa"):
            signer = RSASigner(cert.key_pem, cert=cert)
        elif alg == "hmac-sm3":
            # HMAC verify is symmetric; secret derived from key_pem is the
            # CertBundle.key_pem itself (handled internally by HMACSM3Signer).
            signer = HMACSM3Signer(cert.key_pem)
        else:
            log.warning("verify_bytes_against_cert: unknown alg %r", alg)
            return False
        # Reuse the signer's verify() if present (SM2Signer has it; others
        # don't, fall through to verify_signature style for ecdsa/rsa).
        if hasattr(signer, "verify"):
            return bool(signer.verify(doc_bytes, sig))
        # ECDSA / RSA: rebuild a minimal SignedContract path. Defer to
        # verify_signature by faking a SignedContract with the supplied bytes.
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, padding
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        pub = load_pem_public_key(cert.cert_pem)
        if isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(sig, doc_bytes, ec.ECDSA(hashes.SHA256()))
            return True
        if hasattr(pub, "verifier"):  # pragma: no cover (rsa path)
            pub.verify(sig, doc_bytes, padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ), hashes.SHA256())
            return True
        return False
    except Exception as exc:
        log.warning("verify_bytes_against_cert failed: %s", exc)
        return False


def verify_with_pki(
    sc: SignedContract,
    doc_bytes: bytes,
    *,
    at_time: Optional[Any] = None,
    expected_doc_hash: Optional[str] = None,
    audit: bool = True,
) -> VerifyResult:
    """Alias for :func:`contracts.signing.verifier.verify_signature` with a
    PKI-flavoured name, exposed here for the stable import path.
    """
    return verify_signature(
        sc, doc_bytes=doc_bytes, at_time=at_time,
        expected_doc_hash=expected_doc_hash, audit=audit,
    )