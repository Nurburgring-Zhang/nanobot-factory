"""P15-A2: 时间戳 (RFC 3161 简化 + 本地 TSA).

设计目标:
- 本地 TSA 协议实现 (HMAC + hash 链) — 不依赖外部 TSA 服务.
- 也可选发送 HTTP 请求到外部 TSA (默认禁用, 失败 fallback 本地).
- 时间戳 token 字段:
    token_id, doc_hash (sha256 hex), signed_at (ISO),
    tsa_pubkey_fingerprint (HMAC secret 的指纹),
    signature_b64 (HMAC-SHA256 over canonical fields)

- 启动时可选 verify_timestamp(token) 检测时间戳是否被篡改.
- 兼容性: 本实现不是完整 RFC 3161 ASN.1, 仅 internal JSONL 用; 真实生产用
  freetsa.org RFC 3161 接口.
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import json
import os
import threading
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib import request as _urlreq, error as _urlerr

TIMESTAMP_GENESIS_HASH = "0" * 64


# ============================================================================
# Data class
# ============================================================================

@dataclass
class TimestampToken:
    token_id: str
    doc_hash: str            # SHA-256 hex of doc_bytes (or contract canonical)
    signed_at: str           # ISO 8601 UTC
    tsa_pubkey_fingerprint: str
    signature_b64: str       # HMAC-SHA256 sign(secret, canonical_fields)
    prev_token_hash: str     # 链接到上一个 token (链式, 可选)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def canonical(self) -> str:
        """签名 / 验证用的标准化 payload (字段顺序固定)."""
        return json.dumps({
            "token_id": self.token_id,
            "doc_hash": self.doc_hash,
            "signed_at": self.signed_at,
            "tsa_pubkey_fingerprint": self.tsa_pubkey_fingerprint,
            "prev_token_hash": self.prev_token_hash,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ============================================================================
# Local TSA
# ============================================================================

class LocalTSA:
    """本地时间戳签发器 — HMAC-SHA256 链式 token.

    Args:
        secret: HMAC secret (>= 16 chars). 建议从环境读.
        log_path: 可选, 把所有签发的 token 追加到 JSONL 文件 (防丢失).
    """

    def __init__(self, secret: str, log_path: Optional[str] = None):
        if not secret or len(secret) < 16:
            raise ValueError(f"TSA secret too short ({len(secret or '')} chars, min 16)")
        self._secret = secret
        self._lock = threading.Lock()
        self._last_token_hash = TIMESTAMP_GENESIS_HASH
        self._log_path = Path(log_path) if log_path else None
        if self._log_path:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def pubkey_fingerprint(self) -> str:
        """对外暴露的 fingerprint — 验证方用此识别 TSA."""
        return hashlib.sha256(self._secret.encode("utf-8")).hexdigest()

    def issue(self, doc_bytes: bytes, *, doc_hash: Optional[str] = None) -> TimestampToken:
        """签发时间戳 token. doc_hash 默认 = SHA-256(doc_bytes)."""
        with self._lock:
            if doc_hash is None:
                doc_hash = hashlib.sha256(doc_bytes).hexdigest()
            signed_at = _dt.datetime.utcnow().isoformat() + "Z"
            token = TimestampToken(
                token_id=f"TS-{uuid.uuid4().hex[:12].upper()}",
                doc_hash=doc_hash,
                signed_at=signed_at,
                tsa_pubkey_fingerprint=self.pubkey_fingerprint,
                signature_b64="",   # 占位 — 下面计算
                prev_token_hash=self._last_token_hash,
            )
            # 签名: HMAC-SHA256(secret, canonical)
            sig = hmac.new(
                self._secret.encode("utf-8"),
                token.canonical().encode("utf-8"),
                hashlib.sha256,
            ).digest()
            token.signature_b64 = base64.b64encode(sig).decode("ascii")
            self._last_token_hash = hashlib.sha256(
                token.canonical().encode("utf-8")
            ).hexdigest()
            # 落盘 (可选)
            if self._log_path:
                with self._log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(token.to_dict(), ensure_ascii=False) + "\n")
            return token


# ============================================================================
# Module-level 默认 TSA (lazy init, 单 secret 派生)
# ============================================================================

_DEFAULT_TSA: Optional[LocalTSA] = None


def _default_tsa() -> LocalTSA:
    global _DEFAULT_TSA
    if _DEFAULT_TSA is None:
        secret = os.getenv(
            "CONTRACT_TSA_SECRET",
            # Dev fallback: deterministic but >= 16 chars.
            "dev-only-tsa-secret-CHANGE-ME-32chars-please",
        )
        log_dir = Path(os.getenv(
            "CONTRACT_AUDIT_LOG_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "logs"),
        ))
        log_path = str(log_dir / "contract_tsa_chain.jsonl")
        _DEFAULT_TSA = LocalTSA(secret=secret, log_path=log_path)
    return _DEFAULT_TSA


def _reset_default_tsa_for_tests():
    """测试用 — 清空 singleton."""
    global _DEFAULT_TSA
    _DEFAULT_TSA = None


# ============================================================================
# Public API
# ============================================================================

def issue_timestamp(
    doc_bytes: bytes,
    *,
    doc_hash: Optional[str] = None,
    tsa: Optional[LocalTSA] = None,
) -> TimestampToken:
    """签发时间戳. 默认用模块级 singleton TSA."""
    target = tsa if tsa is not None else _default_tsa()
    return target.issue(doc_bytes, doc_hash=doc_hash)


def verify_timestamp(
    token: TimestampToken,
    *,
    secret: Optional[str] = None,
    expected_doc_hash: Optional[str] = None,
) -> Tuple[bool, str]:
    """验证时间戳 token.

    Args:
        token: TimestampToken.
        secret: HMAC secret (默认从 env 读).
        expected_doc_hash: 期望的 doc_hash (可选, 不传则不强校验).

    Returns:
        (ok, reason): ok=True → "ok"; 否则 reason 描述失败.
    """
    if secret is None:
        secret = os.getenv(
            "CONTRACT_TSA_SECRET",
            "dev-only-tsa-secret-CHANGE-ME-32chars-please",
        )
    expected_fingerprint = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    if token.tsa_pubkey_fingerprint != expected_fingerprint:
        return False, f"tsa_fingerprint_mismatch: got={token.tsa_pubkey_fingerprint[:16]}, expected={expected_fingerprint[:16]}"
    if expected_doc_hash and token.doc_hash != expected_doc_hash:
        return False, f"doc_hash_mismatch: got={token.doc_hash[:16]}, expected={expected_doc_hash[:16]}"
    # 重算 HMAC
    sig = hmac.new(
        secret.encode("utf-8"),
        token.canonical().encode("utf-8"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(sig, base64.b64decode(token.signature_b64)):
        return False, "signature_invalid"
    return True, "ok"


__all__ = [
    "LocalTSA",
    "TimestampToken",
    "issue_timestamp",
    "verify_timestamp",
    "TIMESTAMP_GENESIS_HASH",
    "_reset_default_tsa_for_tests",
]
