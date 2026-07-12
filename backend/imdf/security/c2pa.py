"""V5 第40章 — C2PA 内容来源 (Content Provenance).

实现 C2PA 1.4 子集,重点放在 Ed25519 签名 (比 engines/c2pa_engine.py 的
RSA-PSS 更轻量,适合 skill-level 快速验证).

模块组成:
  * C2PAManifest — Pydantic v2 化 (复用 sso_mfa_c2pa_schemas)
  * C2PASigner   — generate keypair + sign asset → manifest + sidecar JSON
  * C2PAVerifier — verify signature + asset hash + claim + time
  * C2PAStore    — SQLite 持久化 (如果环境没 sqlite3 则降级为 JSON 文件)

生产替换建议:
  * 真实 C2PA 应嵌入 asset 的 APP1/JUMBF box,而不是 sidecar. 这里为了演示
    完整流程,使用 sidecar JSON (文件名 = {asset_path}.c2pa.json).
  * 真实 Ed25519 应使用 HSM 或 KMS 保管 private_key. 当前实现是 in-memory.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .sso_mfa_c2pa_schemas import (
    C2PAAction,
    C2PAIngredient,
    C2PAManifest,
    C2PAVerificationResult,
)

logger = logging.getLogger(__name__)


# ── 工具:hash / canonical body ──────────────────────────────────────────
def _hash_asset(asset_data: bytes, algorithm: str = "sha256") -> str:
    if algorithm != "sha256":
        raise ValueError(f"unsupported hash algorithm: {algorithm}")
    return hashlib.sha256(asset_data).hexdigest()


def _b64encode(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64decode(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _canonical_manifest(manifest: C2PAManifest) -> bytes:
    """求 manifest 的 canonical body (用于 hash + signature 输入).

    排除 signature 本身 (不能把自己签进自己),其他字段按 sorted key 序列化
    以保证不同实现之间可以互验.
    """
    d = manifest.model_dump(mode="json", exclude={"signature", "manifest_hash"})
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# ════════════════════════════════════════════════════════════════════════
# C2PASigner — Ed25519 签名
# ════════════════════════════════════════════════════════════════════════
class C2PASigner:
    """C2PA manifest 签名器 — Ed25519.

    Args:
        claim_generator: claim_generator 字符串 (标识谁签的)
        private_key: 可选 Ed25519PrivateKey; 不传则生成
        public_key:  对应 public key; 不传则从 private_key 推
        ttl_seconds: manifest 有效期 (default 365 days)
    """

    def __init__(
        self,
        claim_generator: str = "IMDF-Security-C2PA/1.0",
        private_key: Optional[Ed25519PrivateKey] = None,
        public_key: Optional[Ed25519PublicKey] = None,
        ttl_seconds: int = 365 * 24 * 3600,
    ) -> None:
        self.claim_generator = claim_generator
        if private_key is None:
            private_key = Ed25519PrivateKey.generate()
        self.private_key = private_key
        self.public_key = public_key or private_key.public_key()
        self.ttl_seconds = ttl_seconds

    @classmethod
    def generate(cls, claim_generator: str = "IMDF-Security-C2PA/1.0") -> "C2PASigner":
        return cls(claim_generator=claim_generator)

    def public_key_b64(self) -> str:
        return _b64encode(self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ))

    def private_key_pem(self) -> bytes:
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    async def sign_manifest(
        self,
        asset_data: bytes,
        claim: Dict[str, Any],
        *,
        actions: Optional[List[C2PAAction]] = None,
        ingredients: Optional[List[C2PAIngredient]] = None,
        manifest_id: Optional[str] = None,
        issued_at: Optional[datetime] = None,
    ) -> C2PAManifest:
        """签 asset_data + claim → C2PAManifest.

        步骤:
          1. asset hash
          2. 组 manifest (with manifest_id + issued_at + actions + ingredients)
          3. canonical body 序列化
          4. Ed25519 签 body
          5. 填 signature + manifest_hash 字段
          6. 返回
        """
        asset_hash = _hash_asset(asset_data)
        now = issued_at or datetime.now(timezone.utc)
        expires = now + timedelta(seconds=self.ttl_seconds)
        mid = manifest_id or f"mf_{uuid.uuid4().hex[:16]}"

        # actions 默认补一条 c2pa.created
        if not actions:
            actions = [C2PAAction(
                action="c2pa.created",
                when=now,
                software_agent=self.claim_generator,
            )]

        manifest = C2PAManifest(
            manifest_id=mid,
            claim_generator=self.claim_generator,
            claim_generator_info=[{"name": self.claim_generator, "version": "1.0"}],
            asset_hash=asset_hash,
            hash_algorithm="sha256",
            signature_algorithm="ed25519",
            signature="",
            public_key=self.public_key_b64(),
            issued_at=now,
            expires_at=expires,
            actions=actions,
            ingredients=ingredients or [],
            claim=claim,
        )
        body = _canonical_manifest(manifest)
        sig_bytes = self.private_key.sign(body)
        manifest.signature = _b64encode(sig_bytes)
        manifest.manifest_hash = _hash_asset(body)
        return manifest


# ════════════════════════════════════════════════════════════════════════
# C2PAVerifier — Ed25519 验签
# ════════════════════════════════════════════════════════════════════════
class C2PAVerifier:
    """C2PA manifest 验证器.

    验证 4 件事:
      1. asset_hash 与提供的 asset_data 匹配 (asset integrity)
      2. signature 对 canonical body 合法 (Ed25519 verify)
      3. claim_generator 匹配期望值 (issuer 绑定)
      4. issued_at/expires_at 落在当前时间窗口 (validity period)
    """

    def __init__(
        self,
        *,
        expected_claim_generator: Optional[str] = None,
        require_unexpired: bool = True,
        public_key: Optional[Ed25519PublicKey] = None,
    ) -> None:
        self.expected_claim_generator = expected_claim_generator
        self.require_unexpired = require_unexpired
        self.public_key = public_key  # 默认从 manifest 中提取

    async def verify(
        self,
        asset_data: bytes,
        manifest: C2PAManifest,
    ) -> C2PAVerificationResult:
        # 1. asset hash
        computed_hash = _hash_asset(asset_data)
        asset_ok = (computed_hash == manifest.asset_hash)

        # 2. signature
        pub = self.public_key
        if pub is None:
            try:
                pub = Ed25519PublicKey.from_public_bytes(_b64decode(manifest.public_key))
            except Exception as e:  # noqa: BLE001
                return C2PAVerificationResult(
                    valid=False,
                    reason=f"invalid public key in manifest: {e}",
                    manifest_id=manifest.manifest_id,
                )
        sig_ok = False
        try:
            # 重建 canonical body (exclude signature + manifest_hash)
            body = _canonical_manifest(manifest)
            pub.verify(_b64decode(manifest.signature), body)
            sig_ok = True
        except InvalidSignature:
            sig_ok = False
        except Exception as e:  # noqa: BLE001
            return C2PAVerificationResult(
                valid=False,
                asset_hash_match=asset_ok,
                signature_valid=False,
                reason=f"signature verify error: {e}",
                manifest_id=manifest.manifest_id,
            )

        # 3. claim_generator
        gen_ok = True
        if self.expected_claim_generator:
            gen_ok = (manifest.claim_generator == self.expected_claim_generator)

        # 4. time window
        time_ok = True
        now = datetime.now(timezone.utc)
        if self.require_unexpired:
            iat = manifest.issued_at
            exp = manifest.expires_at
            if iat.tzinfo is None:
                iat = iat.replace(tzinfo=timezone.utc)
            if exp and exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now < iat or (exp is not None and now > exp):
                time_ok = False

        overall = asset_ok and sig_ok and gen_ok and time_ok
        reasons: List[str] = []
        if not asset_ok:
            reasons.append("asset hash mismatch")
        if not sig_ok:
            reasons.append("invalid signature")
        if not gen_ok:
            reasons.append(
                f"claim_generator mismatch: {manifest.claim_generator} != {self.expected_claim_generator}"
            )
        if not time_ok:
            reasons.append("outside validity period")
        return C2PAVerificationResult(
            valid=overall,
            asset_hash_match=asset_ok,
            signature_valid=sig_ok,
            claim_generator_match=gen_ok,
            time_valid=time_ok,
            reason="; ".join(reasons) if reasons else "ok",
            manifest_id=manifest.manifest_id,
        )


# ════════════════════════════════════════════════════════════════════════
# C2PAStore — SQLite / JSON-file 持久化
# ════════════════════════════════════════════════════════════════════════
class C2PAStore:
    """C2PA manifest 存储 — 按 asset_hash 索引.

    Args:
        db_path: SQLite 文件路径; 默认 tempfile; 设为 ":memory:" 用内存 sqlite
        fallback_json: 当 sqlite3 不可用时降级使用 JSON 文件路径
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        fallback_json: Optional[str] = None,
    ) -> None:
        self.db_path = db_path or os.path.join(tempfile.gettempdir(), "imdf_c2pa_store.sqlite3")
        self.fallback_json = fallback_json or os.path.join(tempfile.gettempdir(), "imdf_c2pa_store.json")
        self._use_sqlite = False
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS c2pa_manifests ("
                "  asset_hash TEXT PRIMARY KEY,"
                "  manifest_json TEXT NOT NULL,"
                "  issued_at TEXT NOT NULL,"
                "  claim_generator TEXT"
                ")"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_c2pa_issued ON c2pa_manifests(issued_at)")
            conn.commit()
            conn.close()
            self._use_sqlite = True
        except Exception as e:  # noqa: BLE001
            logger.warning("C2PAStore: sqlite unavailable (%s), using JSON fallback", e)
            self._use_sqlite = False

    async def record(self, manifest: C2PAManifest) -> None:
        d = manifest.model_dump(mode="json")
        body = json.dumps(d, ensure_ascii=False)
        if self._use_sqlite:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO c2pa_manifests (asset_hash, manifest_json, issued_at, claim_generator)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        manifest.asset_hash,
                        body,
                        manifest.issued_at.isoformat(),
                        manifest.claim_generator,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        else:
            store: Dict[str, Any] = {}
            if os.path.exists(self.fallback_json):
                try:
                    with open(self.fallback_json, "r", encoding="utf-8") as f:
                        store = json.load(f)
                except Exception:
                    store = {}
            store[manifest.asset_hash] = d
            with open(self.fallback_json, "w", encoding="utf-8") as f:
                json.dump(store, f, ensure_ascii=False)

    async def get(self, asset_hash: str) -> Optional[C2PAManifest]:
        body: Optional[str] = None
        if self._use_sqlite:
            conn = sqlite3.connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT manifest_json FROM c2pa_manifests WHERE asset_hash = ?",
                    (asset_hash,),
                ).fetchone()
                body = row[0] if row else None
            finally:
                conn.close()
        else:
            if os.path.exists(self.fallback_json):
                with open(self.fallback_json, "r", encoding="utf-8") as f:
                    store = json.load(f)
                d = store.get(asset_hash)
                if d is not None:
                    return C2PAManifest.model_validate(d)
        if body is None:
            return None
        return C2PAManifest.model_validate(json.loads(body))

    async def list_recent(self, limit: int = 10) -> List[C2PAManifest]:
        out: List[C2PAManifest] = []
        if self._use_sqlite:
            conn = sqlite3.connect(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT manifest_json FROM c2pa_manifests ORDER BY issued_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                for r in rows:
                    out.append(C2PAManifest.model_validate(json.loads(r[0])))
            finally:
                conn.close()
        else:
            if os.path.exists(self.fallback_json):
                with open(self.fallback_json, "r", encoding="utf-8") as f:
                    store = json.load(f)
                for asset_hash, d in sorted(
                    store.items(),
                    key=lambda kv: kv[1].get("issued_at", ""),
                    reverse=True,
                )[:limit]:
                    out.append(C2PAManifest.model_validate(d))
        return out


# ════════════════════════════════════════════════════════════════════════
# Sidecar helpers (写入 / 读取 .c2pa.json 文件)
# ════════════════════════════════════════════════════════════════════════
def write_sidecar(asset_path: str, manifest: C2PAManifest) -> str:
    """把 manifest 写到 {asset_path}.c2pa.json 文件; 返回 sidecar path."""
    sidecar = f"{asset_path}.c2pa.json"
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump(manifest.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    return sidecar


def read_sidecar(asset_path: str) -> Optional[C2PAManifest]:
    sidecar = f"{asset_path}.c2pa.json"
    if not os.path.exists(sidecar):
        return None
    with open(sidecar, "r", encoding="utf-8") as f:
        return C2PAManifest.model_validate(json.load(f))


__all__ = [
    "C2PASigner",
    "C2PAVerifier",
    "C2PAStore",
    "write_sidecar",
    "read_sidecar",
]