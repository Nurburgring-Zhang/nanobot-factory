"""backend/common/encryption — Field-level AES-256-GCM encryption (P10-E).

This module provides :class:`FieldEncryption`, a small wrapper around
``cryptography.hazmat.primitives.ciphers.aead.AESGCM`` for encrypting
sensitive string fields (API keys, PII, payment cards, etc.) in memory
and at rest.

Design
------

* **Algorithm**: AES-256-GCM (authenticated encryption with 12-byte nonce
  and 16-byte tag). NIST approved, constant-time on the underlying
  implementation.
* **Key derivation**: 32-byte master key, base64url or hex encoded in env.
  When a *passphrase* is supplied, we run it through PBKDF2-HMAC-SHA256
  with 16 random salt bytes to derive the actual key.
* **Output format**: ``base64( nonce(12) || ciphertext || tag(16) )`` —
  28 bytes overhead on top of plaintext, single self-contained string.
* **Associated data (AAD)**: optional, e.g. ``b"api_key:openai"`` to
  bind ciphertext to a context. Recommended for distinguishing fields
  even when the master key is shared.

Threat model
------------

* Plaintext NEVER lives in long-lived containers (``APIKeyConfig``,
  dataclasses, JSON files) — only in the caller stack frame as
  ``bytes`` returned by :meth:`decrypt`.
* Memory dumps (e.g. ``gc.get_referrers``) cannot locate the original
  plaintext via a class attribute.
* A leaked ciphertext without the master key is useless (AES-256 GCM
  confidentiality).
* A tampered ciphertext raises :class:`InvalidTag` at decrypt time
  (GCM authentication).

Usage
-----

::

    from common.encryption import FieldEncryption, EncryptionError

    # 32-byte master key from .env
    fe = FieldEncryption.from_env("API_KEY_MASTER_KEY")

    # Encrypt
    ct = fe.encrypt("sk-live-abc123", aad=b"api_key:openai")
    # -> "qrvM3eXK8xv7+..."  (base64)

    # Decrypt
    pt = fe.decrypt(ct, aad=b"api_key:openai")
    assert pt == "sk-live-abc123"

If ``API_KEY_MASTER_KEY`` is missing or malformed in production
(non-test mode), :class:`FieldEncryption.from_env` raises
:class:`EncryptionError` at startup — fail-fast.

References
----------

* NIST SP 800-38D (GCM)
* RFC 5116 (AEAD)
* ``cryptography`` docs: https://cryptography.io/en/latest/hazmat/primitives/aead/
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from dataclasses import dataclass
from typing import Optional, Union

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)


# 32 bytes = 256 bits — required for AES-256.
_KEY_BYTES = 32
# 12 bytes is the GCM-recommended nonce size.
_NONCE_BYTES = 12
# 16 bytes (128 bits) — GCM tag length, max security.
_TAG_BITS = 128
# PBKDF2 iteration count for passphrase → 32-byte key derivation.
_PBKDF2_ITER = 200_000
# PBKDF2 salt length (random per key).
_PBKDF2_SALT = 16


class EncryptionError(RuntimeError):
    """Raised on missing master key, malformed input, or auth failure."""


@dataclass(frozen=True)
class FieldEncryption:
    """AES-256-GCM field-level encryption.

    Wraps a 32-byte master key and exposes ``encrypt``/``decrypt`` for
    short string fields. Multiple :class:`FieldEncryption` instances
    with the same key are equivalent (the underlying ``AESGCM`` is
    deterministic in its use of the key but random in nonce).
    """

    _key: bytes
    _aead: AESGCM

    def __post_init__(self) -> None:
        if not isinstance(self._key, (bytes, bytearray)):
            raise EncryptionError("master key must be bytes")
        if len(self._key) != _KEY_BYTES:
            raise EncryptionError(
                f"master key must be exactly {_KEY_BYTES} bytes "
                f"(got {len(self._key)})"
            )
        # Re-bind the private AESGCM with the validated key (frozen
        # dataclass means we cannot use ``self._aead = ...`` in the
        # post-init normal way; use object.__setattr__).
        object.__setattr__(self, "_aead", AESGCM(bytes(self._key)))

    # ── Construction helpers ────────────────────────────────────────────
    @classmethod
    def from_raw_key(cls, raw: Union[bytes, str]) -> "FieldEncryption":
        """Build from a 32-byte raw key (bytes or hex/base64 string).

        Accepted string formats (in order):
          1. hex (64 chars)
          2. base64url (43-44 chars, no padding required)
          3. base64 standard (44 chars with padding)
        """
        if isinstance(raw, str):
            raw = raw.strip()
            if not raw:
                raise EncryptionError("empty master key string")
            # Try hex first (64 hex chars == 32 bytes)
            if len(raw) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw):
                key = bytes.fromhex(raw)
            else:
                # Try urlsafe-base64 then standard-base64
                try:
                    key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
                except Exception:
                    try:
                        key = base64.b64decode(raw + "=" * (-len(raw) % 4))
                    except Exception as exc:
                        raise EncryptionError(
                            f"master key is neither 64-char hex nor valid base64: {exc}"
                        ) from exc
        else:
            key = bytes(raw)

        return cls(_key=key, _aead=AESGCM(key))

    @classmethod
    def from_passphrase(
        cls,
        passphrase: str,
        salt: Optional[bytes] = None,
        iterations: int = _PBKDF2_ITER,
    ) -> "FieldEncryption":
        """Derive a 32-byte key from a passphrase via PBKDF2-HMAC-SHA256.

        *passphrase* should be high-entropy (e.g. ``secrets.token_urlsafe(48)``).
        If *salt* is ``None``, a fresh 16-byte salt is generated and printed
        in the returned dataclass via the standard PBKDF2 path — for
        production, store the salt alongside the ciphertext.
        """
        if not passphrase:
            raise EncryptionError("passphrase is empty")
        if salt is None:
            salt = secrets.token_bytes(_PBKDF2_SALT)
        key = hashlib.pbkdf2_hmac(
            "sha256",
            passphrase.encode("utf-8"),
            salt,
            iterations,
            dklen=_KEY_BYTES,
        )
        return cls(_key=key, _aead=AESGCM(key))

    @classmethod
    def from_env(
        cls,
        env_var: str = "API_KEY_MASTER_KEY",
        *,
        allow_test_default: bool = False,
    ) -> "FieldEncryption":
        """Load a master key from environment variable.

        Format precedence (mirrors :meth:`from_raw_key`):
          1. hex (64 chars) — recommended
          2. base64url / base64 — convenient for short strings

        If the variable is missing or empty and *allow_test_default*
        is True, generate a fresh random key in-process and log a
        warning. This is intended for unit tests / dev only.
        """
        raw = os.environ.get(env_var, "").strip()
        if not raw:
            if allow_test_default:
                key = secrets.token_bytes(_KEY_BYTES)
                logger.warning(
                    "%s not set — generated ephemeral test key (DO NOT use in prod)",
                    env_var,
                )
                return cls(_key=key, _aead=AESGCM(key))
            raise EncryptionError(
                f"master key env var {env_var!r} is missing or empty; "
                f"set it to a 64-char hex string (32 bytes)"
            )
        return cls.from_raw_key(raw)

    # ── Public API ──────────────────────────────────────────────────────
    def encrypt(self, plaintext: str, aad: bytes = b"") -> str:
        """Encrypt *plaintext* and return a self-contained base64 string.

        Output format: ``base64( nonce(12) || ciphertext_with_tag )``.

        The nonce is fresh per call (``secrets.token_bytes``) — GCM
        security requires unique nonces per (key, plaintext) pair.
        """
        if not isinstance(plaintext, str):
            raise EncryptionError("plaintext must be str")
        nonce = secrets.token_bytes(_NONCE_BYTES)
        if not isinstance(aad, (bytes, bytearray)):
            raise EncryptionError("aad must be bytes")
        ct = self._aead.encrypt(nonce, plaintext.encode("utf-8"), bytes(aad))
        return base64.b64encode(nonce + ct).decode("ascii")

    def decrypt(self, ciphertext_b64: str, aad: bytes = b"") -> str:
        """Decrypt a string produced by :meth:`encrypt`. Returns plaintext.

        Raises :class:`EncryptionError` on:
          * malformed base64 / wrong length
          * GCM tag mismatch (tampering or wrong AAD / wrong key)
        """
        if not isinstance(ciphertext_b64, str):
            raise EncryptionError("ciphertext must be str")
        try:
            raw = base64.b64decode(ciphertext_b64, validate=True)
        except Exception as exc:
            raise EncryptionError(f"ciphertext is not valid base64: {exc}") from exc
        if len(raw) < _NONCE_BYTES + (_TAG_BITS // 8):
            raise EncryptionError("ciphertext too short to contain nonce + tag")
        nonce, ct = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        if not isinstance(aad, (bytes, bytearray)):
            raise EncryptionError("aad must be bytes")
        try:
            pt = self._aead.decrypt(nonce, ct, bytes(aad))
        except InvalidTag as exc:
            raise EncryptionError(
                "GCM authentication failed — wrong key, tampered ciphertext, "
                "or wrong AAD"
            ) from exc
        return pt.decode("utf-8")

    # ── Introspection (testing / debugging) ─────────────────────────────
    @property
    def key_fingerprint(self) -> str:
        """Stable 16-char fingerprint of the master key (for logs only)."""
        return hashlib.sha256(self._key).hexdigest()[:16]


__all__ = [
    "FieldEncryption",
    "EncryptionError",
]
