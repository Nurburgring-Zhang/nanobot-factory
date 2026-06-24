"""
P1-A1-W1: C2PA 1.4 Content Authenticity Engine
================================================
Implements C2PA (Coalition for Content Provenance and Authenticity) v1.4
manifest generation, X.509 RSA-PSS signature, and CRL (Certificate/Manifest
Revocation List).

Spec reference: https://c2pa.org/specifications/specifications/1.4/specs/C2PA_Specification.html

Engine is self-contained:
  * Auto-generates RSA-2048 key + self-signed X.509 cert if not supplied
  * Manifest is a CBOR-like JSON dict (C2PA 1.4 box model simplified for
    JSON transport; real C2PA uses CBOR boxes in JPEG/PNG APP segments)
  * Signature uses RSA-PSS-SHA256 with the X.509 private key
  * Hash chain links the asset hash → manifest → previous manifest via SHA-256
  * CRL is an in-memory list of revoked manifest_ids (also persisted in
    SQLite by the api layer)
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.x509.oid import NameOID

logger = logging.getLogger(__name__)

# C2PA 1.4 standard claim_generator identifier
DEFAULT_CLAIM_GENERATOR = "IMDF-C2PA-Engine/1.4.0"
DEFAULT_HASH_ALG = "sha256"
DEFAULT_SIG_ALG = "rsa-pss-sha256"

# Manifest magic header to mark a sidecar manifest file (C2PA store forward
# compatibility — embedding into binary assets requires format-aware code).
MANIFEST_MAGIC = "c2pa_manifest_v1"


# ── Manifest dataclass ───────────────────────────────────────────────────
@dataclass
class C2PAManifest:
    """A C2PA 1.4 manifest.

    Required fields per spec: claim_generator, claim_generator_info, actions,
    ingredient (asset hash), signature, certificate_ref.
    """
    manifest_id: str
    claim_generator: str
    actions: List[Dict[str, Any]]
    asset_hash: str
    hash_algorithm: str
    signature_algorithm: str
    signature: str  # base64-encoded RSA-PSS signature over canonical manifest body
    cert_fingerprint: str  # SHA-256 of DER-encoded X.509 cert
    issued_at: str  # ISO-8601 UTC
    expires_at: str  # ISO-8601 UTC (5 years default)
    previous_manifest_id: Optional[str]  # hash chain link
    previous_manifest_hash: Optional[str]  # hash chain link
    manifest_hash: str  # SHA-256 of canonical manifest body (excludes signature)
    claim: Dict[str, Any] = field(default_factory=dict)  # original claim payload
    revoked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def canonical_body(self) -> Dict[str, Any]:
        """Manifest body used for signing/verification (excludes signature)."""
        d = self.to_dict()
        d.pop("signature", None)
        d.pop("manifest_hash", None)
        # Sort keys for deterministic serialization
        return _sort_dict(d)


def _sort_dict(d: Any) -> Any:
    """Recursively sort dict keys for deterministic canonical form."""
    if isinstance(d, dict):
        return {k: _sort_dict(d[k]) for k in sorted(d.keys())}
    if isinstance(d, list):
        return [_sort_dict(x) for x in d]
    return d


def _canonical_json(d: Any) -> bytes:
    """Deterministic JSON encoding (RFC 8785-like for our subset)."""
    return json.dumps(_sort_dict(d), separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# ── Engine ───────────────────────────────────────────────────────────────
class C2PAEngine:
    """C2PA 1.4 Content Authenticity standard implementation.

    Args:
        cert_path: path to PEM-encoded X.509 certificate. If file does not
            exist, a self-signed cert is generated and saved.
        key_path: path to PEM-encoded RSA private key. If file does not exist,
            a 2048-bit RSA key is generated and saved.
        issuer: CN field for auto-generated self-signed cert.
        ttl_seconds: manifest validity period (default 5 years).
    """

    def __init__(
        self,
        cert_path: str,
        key_path: str,
        issuer: str = "IMDF-Platform-C2PA",
        ttl_seconds: int = 5 * 365 * 24 * 3600,
    ) -> None:
        self.cert_path = cert_path
        self.key_path = key_path
        self.issuer = issuer
        self.ttl_seconds = ttl_seconds

        self.cert: x509.Certificate
        self.key: rsa.RSAPrivateKey
        self.crl: List[str] = []  # list of revoked manifest_ids
        self._manifest_chain: List[C2PAManifest] = []  # ordered by issuance

        self._load_or_generate_keys()
        logger.info(
            f"C2PAEngine initialized: cert={cert_path} key={key_path} "
            f"fingerprint={self.cert_fingerprint()[:16]}..."
        )

    # ── Key/cert management ─────────────────────────────────────────────
    def _load_or_generate_keys(self) -> None:
        cert_p = Path(self.cert_path)
        key_p = Path(self.key_path)

        if cert_p.exists() and key_p.exists():
            try:
                with open(cert_p, "rb") as f:
                    self.cert = x509.load_pem_x509_certificate(f.read())
                with open(key_p, "rb") as f:
                    self.key = serialization.load_pem_private_key(
                        f.read(), password=None
                    )
                if not isinstance(self.key, rsa.RSAPrivateKey):
                    raise ValueError("Loaded key is not RSA")
                return
            except Exception as e:
                logger.warning(f"Failed to load existing key/cert: {e}; regenerating")

        # Generate new RSA-2048 key + self-signed X.509 cert
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, self.issuer),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "IMDF"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "C2PA-Engine"),
            ]
        )
        now = datetime.now(timezone.utc)
        self.cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - __import__("datetime").timedelta(minutes=5))
            .not_valid_after(now + __import__("datetime").timedelta(days=365 * 10))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
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
                x509.SubjectKeyIdentifier.from_public_key(self.key.public_key()),
                critical=False,
            )
            .sign(self.key, hashes.SHA256())
        )

        # Persist
        cert_p.parent.mkdir(parents=True, exist_ok=True)
        key_p.parent.mkdir(parents=True, exist_ok=True)
        with open(cert_p, "wb") as f:
            f.write(self.cert.public_bytes(serialization.Encoding.PEM))
        # Save private key unencrypted (test/dev context only; production
        # should encrypt with passphrase from KMS).
        with open(key_p, "wb") as f:
            f.write(
                self.key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        # Restrict permissions (best-effort on Windows: clear read for others)
        try:
            os.chmod(key_p, 0o600)
        except Exception:
            pass

    def cert_fingerprint(self) -> str:
        """SHA-256 of DER-encoded certificate, hex-encoded."""
        return hashlib.sha256(self.cert.public_bytes(serialization.Encoding.DER)).hexdigest()

    def cert_pem(self) -> str:
        return self.cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    # ── Hash chain ──────────────────────────────────────────────────────
    def _last_manifest(self) -> Optional[C2PAManifest]:
        return self._manifest_chain[-1] if self._manifest_chain else None

    def _compute_asset_hash(self, asset_path: str) -> str:
        if not os.path.exists(asset_path):
            raise FileNotFoundError(f"Asset not found: {asset_path}")
        h = hashlib.sha256()
        with open(asset_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    # ── Signing ─────────────────────────────────────────────────────────
    def sign_asset(self, asset_path: str, claim: Dict[str, Any]) -> Dict[str, Any]:
        """Sign an asset and produce a C2PA manifest.

        Steps (per C2PA 1.4):
          1. Compute SHA-256 hash of asset
          2. Build claim assertion (claim_generator + actions + hash)
          3. Construct manifest with hash chain link to previous manifest
          4. Sign canonical manifest body with RSA-PSS-SHA256
          5. Embed manifest_hash in the manifest
          6. Optionally write sidecar .c2pa manifest file
          7. Return manifest dict

        Args:
            asset_path: absolute or relative path to the asset to sign.
            claim: free-form claim dict from the user, e.g.
                {"creator": "alice", "license": "CC-BY-4.0",
                 "actions": [{"action": "c2pa.created"}]}

        Returns:
            manifest dict with all fields populated.
        """
        if not isinstance(claim, dict):
            raise ValueError("claim must be a dict")

        asset_hash = self._compute_asset_hash(asset_path)

        # Normalize actions
        actions = claim.get("actions") or [{"action": "c2pa.created"}]
        if not isinstance(actions, list) or not actions:
            raise ValueError("claim.actions must be a non-empty list")

        now = datetime.now(timezone.utc)
        expires = now.timestamp() + self.ttl_seconds
        expires_dt = datetime.fromtimestamp(expires, tz=timezone.utc)
        manifest_id = f"manifest_{uuid.uuid4().hex[:16]}"

        # Hash chain link
        last = self._last_manifest()
        prev_id = last.manifest_id if last else None
        prev_hash = last.manifest_hash if last else None

        # Build manifest WITHOUT signature/manifest_hash first (so we can sign)
        manifest = C2PAManifest(
            manifest_id=manifest_id,
            claim_generator=claim.get("claim_generator", DEFAULT_CLAIM_GENERATOR),
            actions=actions,
            asset_hash=asset_hash,
            hash_algorithm=DEFAULT_HASH_ALG,
            signature_algorithm=DEFAULT_SIG_ALG,
            signature="",  # filled below
            cert_fingerprint=self.cert_fingerprint(),
            issued_at=now.isoformat(),
            expires_at=expires_dt.isoformat(),
            previous_manifest_id=prev_id,
            previous_manifest_hash=prev_hash,
            manifest_hash="",  # filled below
            claim=dict(claim),
            revoked=False,
        )

        # Compute manifest_hash = SHA-256(canonical_body)
        body = manifest.canonical_body()
        canonical = _canonical_json(body)
        manifest_hash = hashlib.sha256(canonical).hexdigest()
        manifest.manifest_hash = manifest_hash

        # Re-canonicalize now that manifest_hash is set, then sign
        body2 = manifest.canonical_body()
        # Per C2PA spec the signature covers claim_signature_payload, which
        # is the hash chain from the previous manifest hash. We use the
        # concatenation prev_hash || manifest_hash as the signature input.
        sig_input = (prev_hash or "").encode("utf-8") + manifest_hash.encode("utf-8")
        signature_bytes = self.key.sign(
            sig_input,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        manifest.signature = base64.b64encode(signature_bytes).decode("ascii")

        # Append to chain (chronological)
        self._manifest_chain.append(manifest)

        # Write sidecar manifest file (forward-compat with future embedding)
        try:
            sidecar = str(asset_path) + ".c2pa.json"
            with open(sidecar, "w", encoding="utf-8") as f:
                json.dump(manifest.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write sidecar manifest (non-fatal): {e}")

        logger.info(
            f"C2PA manifest signed: id={manifest_id} asset={asset_path} "
            f"hash={asset_hash[:16]}..."
        )
        return manifest.to_dict()

    # ── Verification ────────────────────────────────────────────────────
    def verify_signature(self, asset_path: str) -> Tuple[bool, Dict[str, Any]]:
        """Verify C2PA signature on an asset.

        Returns:
            (is_valid, manifest_dict) tuple. is_valid=False with reason
            populated in manifest_dict if verification fails.
        """
        if not os.path.exists(asset_path):
            return False, {"error": "asset_not_found", "asset_path": asset_path}

        # Locate sidecar manifest
        sidecar = str(asset_path) + ".c2pa.json"
        if not os.path.exists(sidecar):
            return False, {"error": "manifest_not_found", "sidecar": sidecar}

        try:
            with open(sidecar, "r", encoding="utf-8") as f:
                manifest_dict = json.load(f)
        except Exception as e:
            return False, {"error": "manifest_corrupt", "detail": str(e)}

        manifest_id = manifest_dict.get("manifest_id", "")
        if manifest_id in self.crl or manifest_dict.get("revoked"):
            manifest_dict["is_valid"] = False
            manifest_dict["reason"] = "revoked"
            return False, manifest_dict

        # Recompute asset hash
        try:
            current_asset_hash = self._compute_asset_hash(asset_path)
        except FileNotFoundError:
            return False, {"error": "asset_not_found", "asset_path": asset_path}

        if current_asset_hash != manifest_dict.get("asset_hash"):
            manifest_dict["is_valid"] = False
            manifest_dict["reason"] = "asset_hash_mismatch"
            return False, manifest_dict

        # Recompute manifest_hash
        body_for_hash = {k: v for k, v in manifest_dict.items()
                         if k not in ("signature", "manifest_hash")}
        body_for_hash = _sort_dict(body_for_hash)
        canonical = _canonical_json(body_for_hash)
        expected_manifest_hash = hashlib.sha256(canonical).hexdigest()
        if expected_manifest_hash != manifest_dict.get("manifest_hash"):
            manifest_dict["is_valid"] = False
            manifest_dict["reason"] = "manifest_hash_mismatch"
            return False, manifest_dict

        # Verify RSA-PSS signature
        sig_b64 = manifest_dict.get("signature", "")
        try:
            sig_bytes = base64.b64decode(sig_b64)
        except Exception as e:
            return False, {"error": "signature_decode_failed", "detail": str(e)}

        prev_hash = manifest_dict.get("previous_manifest_hash") or ""
        sig_input = prev_hash.encode("utf-8") + manifest_dict["manifest_hash"].encode("utf-8")
        try:
            self.cert.public_key().verify(
                sig_bytes,
                sig_input,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        except Exception as e:
            manifest_dict["is_valid"] = False
            manifest_dict["reason"] = "signature_verification_failed"
            manifest_dict["detail"] = str(e)
            return False, manifest_dict

        # Check cert fingerprint matches the engine's current cert
        if manifest_dict.get("cert_fingerprint") != self.cert_fingerprint():
            manifest_dict["is_valid"] = False
            manifest_dict["reason"] = "cert_fingerprint_mismatch"
            return False, manifest_dict

        manifest_dict["is_valid"] = True
        manifest_dict["reason"] = "ok"
        return True, manifest_dict

    # ── Revocation ──────────────────────────────────────────────────────
    def revoke(self, manifest_id: str) -> bool:
        """Add manifest_id to CRL. Returns True if newly revoked, False if already revoked."""
        if not manifest_id:
            raise ValueError("manifest_id required")
        if manifest_id in self.crl:
            return False
        self.crl.append(manifest_id)
        # Also mark in chain
        for m in self._manifest_chain:
            if m.manifest_id == manifest_id:
                m.revoked = True
                # Best-effort: rewrite sidecar
                try:
                    sidecar_p = None
                    for sidecar in Path(".").rglob("*.c2pa.json"):
                        try:
                            with open(sidecar, "r", encoding="utf-8") as f:
                                d = json.load(f)
                            if d.get("manifest_id") == manifest_id:
                                d["revoked"] = True
                                with open(sidecar, "w", encoding="utf-8") as f:
                                    json.dump(d, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                except Exception:
                    pass
                break
        logger.info(f"C2PA manifest revoked: {manifest_id}")
        return True

    def get_crl(self) -> List[Dict[str, Any]]:
        return [{"manifest_id": mid, "revoked_at": datetime.now(timezone.utc).isoformat()}
                for mid in self.crl]

    # ── Manifest retrieval ─────────────────────────────────────────────
    def get_manifest(self, manifest_id: str) -> Optional[Dict[str, Any]]:
        for m in self._manifest_chain:
            if m.manifest_id == manifest_id:
                return m.to_dict()
        return None

    def list_manifests(self) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self._manifest_chain]
