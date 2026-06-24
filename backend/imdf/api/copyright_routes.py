"""
F8.3 版权/C2PA/水印 API — 真实化实现
=====================================
- /sign: 生成数字签名(hash+HMAC)
- /verify: 验证签名
- /embed: 嵌入版权信息(返回版权声明JSON + 基础图片水印)
- /detect: 检测已有版权信息
- /similarity: 计算两个作品相似度(基础算法)
- /c2pa/*: C2PA 1.4 内容真实性签名 (X.509 RSA-PSS + SHA-256 哈希链)
实现: hashlib+hmac真实签名, Pillow基础图片水印, SQLite持久化,
      cryptography 库真实 X.509 证书 + RSA-PSS 签名
"""

import os
import sys
import json
import sqlite3
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Body, Query, UploadFile, File
from pydantic import BaseModel, Field, validator

# ── C2PA Engine (P1-A1-W1) ────────────────────────────────────────────────
try:
    from engines.c2pa_engine import C2PAEngine
    _C2PA_AVAILABLE = True
except Exception as _c2pa_import_err:  # pragma: no cover
    logger.warning(f"C2PAEngine import failed: {_c2pa_import_err}")
    C2PAEngine = None
    _C2PA_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/copyright", tags=["copyright"])

# ── Database ─────────────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BACKEND_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_DATA_DIR / "copyright.db")

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _init_db():
    with _get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS signatures (
                id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                signature TEXT NOT NULL,
                algorithm TEXT DEFAULT 'HMAC-SHA256',
                key_hint TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS copyright_records (
                id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                creator TEXT DEFAULT '',
                license TEXT DEFAULT 'CC-BY-4.0',
                copyright_text TEXT DEFAULT '',
                embedded_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS c2pa_manifests (
                id TEXT PRIMARY KEY,
                asset_path TEXT NOT NULL,
                asset_hash TEXT NOT NULL,
                claim_json TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                cert_fingerprint TEXT NOT NULL,
                revoked INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_signatures_asset ON signatures(asset_id);
            CREATE INDEX IF NOT EXISTS idx_copyright_asset ON copyright_records(asset_id);
            CREATE INDEX IF NOT EXISTS idx_c2pa_asset ON c2pa_manifests(asset_path);
        """)

_init_db()

# ── Pydantic Models ──────────────────────────────────────────────────────────

class SignRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=256)
    content: str = Field(..., min_length=1, description="要签名的内容")
    algorithm: str = Field(default="HMAC-SHA256", pattern="^(HMAC-SHA256|SHA256|SHA512)$")
    secret_key: Optional[str] = Field(default=None, description="HMAC密钥，不提供则自动生成")

class VerifyRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=256)
    content: str = Field(..., min_length=1)
    signature: str = Field(..., min_length=1)
    algorithm: str = Field(default="HMAC-SHA256")
    secret_key: Optional[str] = None

class EmbedCopyrightRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=256)
    creator: str = Field(default="", max_length=256)
    license: str = Field(default="CC-BY-4.0", max_length=128)
    copyright_text: str = Field(default="", max_length=1024)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class DetectCopyrightRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, max_length=256)

class SimilarityRequest(BaseModel):
    source_id: str = Field(..., min_length=1, max_length=256)
    content_a: str = Field(..., min_length=1, description="作品A的内容(文本或hash)")
    content_b: str = Field(..., min_length=1, description="作品B的内容(文本或hash)")
    method: str = Field(default="combined", pattern="^(hash|jaccard|levenshtein|combined)$")

class AttributionRequest(BaseModel):
    creator: str = Field(..., min_length=1, max_length=256)
    asset_id: str = Field(..., min_length=1, max_length=256)
    license: str = Field(default="CC-BY-4.0", max_length=128)


# ── Video Watermark Models (P1-A1-W2) ────────────────────────────────────────

class VideoTextWatermarkRequest(BaseModel):
    """Add a text watermark to a video."""
    video_id: str = Field(..., min_length=1, max_length=256,
                          description="Asset / video identifier")
    input_path: str = Field(..., min_length=1, max_length=1024,
                            description="Source video file path")
    text: str = Field(..., min_length=1, max_length=512,
                      description="Watermark text (e.g. 'IMDF © 2026')")
    position: str = Field(
        default="bottomright",
        pattern="^(topleft|topright|bottomleft|bottomright|center)$",
    )
    opacity: float = Field(default=0.7, ge=0.0, le=1.0)
    font_size: int = Field(default=24, ge=8, le=200)
    output_path: Optional[str] = Field(
        default=None, max_length=1024,
        description="Output path (defaults to <input>_watermarked.mp4)",
    )


class VideoImageWatermarkRequest(BaseModel):
    """Add an image logo watermark to a video."""
    video_id: str = Field(..., min_length=1, max_length=256)
    input_path: str = Field(..., min_length=1, max_length=1024)
    logo_path: str = Field(..., min_length=1, max_length=1024)
    position: str = Field(
        default="bottomright",
        pattern="^(topleft|topright|bottomleft|bottomright|center)$",
    )
    opacity: float = Field(default=0.5, ge=0.0, le=1.0)
    scale: float = Field(default=0.15, gt=0.0, le=1.0,
                         description="Logo width as fraction of video width")
    output_path: Optional[str] = Field(default=None, max_length=1024)

# ── Helper Functions ─────────────────────────────────────────────────────────

_SECRET_KEY = os.environ.get("COPYRIGHT_SECRET_KEY", "imdf-copyright-default-key-2026")

def _compute_hash(content: str, algorithm: str = "SHA256") -> str:
    if algorithm == "SHA256":
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    elif algorithm == "SHA512":
        return hashlib.sha512(content.encode('utf-8')).hexdigest()
    else:
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

def _compute_hmac(content: str, key: str) -> str:
    return hmac.new(key.encode('utf-8'), content.encode('utf-8'), hashlib.sha256).hexdigest()

def _compute_signature(content: str, algorithm: str, secret_key: Optional[str] = None) -> str:
    key = secret_key or _SECRET_KEY
    if algorithm == "HMAC-SHA256":
        return _compute_hmac(content, key)
    elif algorithm == "SHA256":
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    elif algorithm == "SHA512":
        return hashlib.sha512(content.encode('utf-8')).hexdigest()
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")

def _jaccard_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two texts (word-level)."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)

def _levenshtein_ratio(a: str, b: str) -> float:
    """Compute normalized Levenshtein similarity ratio."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    m, n = len(a), len(b)
    # Use dynamic programming for Levenshtein distance
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i-1] == b[j-1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(dp[j], dp[j-1], prev)
            prev = temp
    distance = dp[n]
    max_len = max(m, n)
    return 1.0 - (distance / max_len)

def _char_ngram_similarity(a: str, b: str, n: int = 3) -> float:
    """Compute character n-gram based similarity."""
    def get_ngrams(s, n):
        return set(s[i:i+n] for i in range(len(s) - n + 1))
    ngrams_a = get_ngrams(a.lower(), n)
    ngrams_b = get_ngrams(b.lower(), n)
    if not ngrams_a and not ngrams_b:
        return 1.0
    if not ngrams_a or not ngrams_b:
        return 0.0
    intersection = ngrams_a & ngrams_b
    union = ngrams_a | ngrams_b
    return len(intersection) / len(union)

# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health")
async def copyright_health():
    """健康检查"""
    try:
        with _get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "module": "copyright", "version": "1.0.0", "db": "connected"}
    except Exception as e:
        return {"status": "degraded", "module": "copyright", "version": "1.0.0", "db_error": str(e)}


@router.post("/sign")
async def copyright_sign(req: SignRequest):
    """
    生成数字签名: 对内容计算hash并用HMAC签名。
    返回签名ID、内容hash和签名值，持久化到SQLite。
    """
    try:
        content_hash = _compute_hash(req.content, "SHA256")
        signature = _compute_signature(req.content, req.algorithm, req.secret_key)
        sign_id = f"sig_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()

        with _get_db() as conn:
            conn.execute(
                "INSERT INTO signatures (id, asset_id, content_hash, signature, algorithm, key_hint, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sign_id, req.asset_id, content_hash, signature, req.algorithm,
                 "custom_key" if req.secret_key else "default_key", created_at)
            )
            conn.commit()

        logger.info(f"Signature created: {sign_id} for asset {req.asset_id}")
        return {
            "ok": True,
            "data": {
                "signature_id": sign_id,
                "asset_id": req.asset_id,
                "content_hash": content_hash,
                "signature": signature,
                "algorithm": req.algorithm,
                "created_at": created_at,
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Sign failed: {e}")
        raise HTTPException(status_code=500, detail=f"Signature generation failed: {str(e)}")


@router.post("/verify")
async def copyright_verify(req: VerifyRequest):
    """
    验证签名: 用同样的算法和密钥重新计算签名并比对。
    """
    try:
        expected = _compute_signature(req.content, req.algorithm, req.secret_key)
        valid = hmac.compare_digest(expected, req.signature)

        content_hash = _compute_hash(req.content, "SHA256")

        logger.info(f"Signature verification for asset {req.asset_id}: {'valid' if valid else 'invalid'}")
        return {
            "ok": True,
            "data": {
                "asset_id": req.asset_id,
                "valid": valid,
                "content_hash": content_hash,
                "expected_signature": expected[:16] + "..." if not valid else expected,
                "algorithm": req.algorithm,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Verify failed: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


@router.get("/verify/{signature_id}")
async def copyright_verify_by_id(signature_id: str):
    """通过签名ID查询签名记录"""
    try:
        with _get_db() as conn:
            row = conn.execute("SELECT * FROM signatures WHERE id = ?", (signature_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Signature {signature_id} not found")
        return {
            "ok": True,
            "data": {
                "signature_id": row["id"],
                "asset_id": row["asset_id"],
                "content_hash": row["content_hash"],
                "signature": row["signature"],
                "algorithm": row["algorithm"],
                "created_at": row["created_at"],
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Query signature failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embed")
async def copyright_embed(req: EmbedCopyrightRequest):
    """
    嵌入版权信息: 记录版权声明到SQLite。
    如果Pillow可用且提供了image_path，则添加文字水印。
    """
    try:
        record_id = f"cr_{uuid.uuid4().hex[:12]}"
        embedded_at = datetime.now(timezone.utc).isoformat()

        metadata_json = json.dumps(req.metadata)

        with _get_db() as conn:
            conn.execute(
                "INSERT INTO copyright_records (id, asset_id, creator, license, copyright_text, embedded_at, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record_id, req.asset_id, req.creator, req.license, req.copyright_text, embedded_at, metadata_json)
            )
            conn.commit()

        # Try Pillow watermark if image_path provided in metadata
        watermarked_path = None
        image_path = req.metadata.get("image_path", "")
        if image_path and os.path.exists(image_path):
            try:
                from PIL import Image, ImageDraw, ImageFont
                img = Image.open(image_path).convert("RGBA")
                overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
                draw = ImageDraw.Draw(overlay)
                text = req.copyright_text or f"© {req.creator}" if req.creator else "© IMDF Platform"
                # Use default font
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
                except Exception:
                    font = ImageFont.load_default()
                bbox = draw.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                x = img.width - tw - 20
                y = img.height - th - 20
                draw.text((x, y), text, font=font, fill=(255, 255, 255, 100))
                watermarked = Image.alpha_composite(img, overlay)
                watermarked_path = image_path.rsplit(".", 1)[0] + "_copyrighted.png"
                watermarked.convert("RGB").save(watermarked_path)
                logger.info(f"Watermark saved to {watermarked_path}")
            except ImportError:
                logger.warning("Pillow not available, skipping image watermark")
            except Exception as e:
                logger.warning(f"Image watermark failed (non-fatal): {e}")

        logger.info(f"Copyright embedded: {record_id} for asset {req.asset_id}")
        return {
            "ok": True,
            "data": {
                "record_id": record_id,
                "asset_id": req.asset_id,
                "creator": req.creator,
                "license": req.license,
                "copyright_text": req.copyright_text,
                "embedded_at": embedded_at,
                "watermarked_path": watermarked_path,
            }
        }
    except Exception as e:
        logger.exception(f"Embed copyright failed: {e}")
        raise HTTPException(status_code=500, detail=f"Copyright embedding failed: {str(e)}")


@router.post("/detect")
async def copyright_detect(req: DetectCopyrightRequest):
    """
    检测已嵌入的版权信息: 从SQLite查询资产的版权记录。
    """
    try:
        with _get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM copyright_records WHERE asset_id = ? ORDER BY embedded_at DESC",
                (req.asset_id,)
            ).fetchall()

        records = [{
            "record_id": r["id"],
            "creator": r["creator"],
            "license": r["license"],
            "copyright_text": r["copyright_text"],
            "embedded_at": r["embedded_at"],
            "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
        } for r in rows]

        has_copyright = len(records) > 0
        logger.info(f"Copyright detection for {req.asset_id}: {len(records)} records found")
        return {
            "ok": True,
            "data": {
                "asset_id": req.asset_id,
                "has_copyright": has_copyright,
                "records": records,
                "total": len(records),
            }
        }
    except Exception as e:
        logger.exception(f"Detect copyright failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/records/{asset_id}")
async def copyright_records_by_asset(asset_id: str):
    """查询资产的所有版权记录"""
    try:
        with _get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM copyright_records WHERE asset_id = ? ORDER BY embedded_at DESC",
                (asset_id,)
            ).fetchall()
        records = [{
            "record_id": r["id"],
            "creator": r["creator"],
            "license": r["license"],
            "copyright_text": r["copyright_text"],
            "embedded_at": r["embedded_at"],
            "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
        } for r in rows]
        return {"ok": True, "data": {"asset_id": asset_id, "records": records, "total": len(records)}}
    except Exception as e:
        logger.exception(f"Query copyright records failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/similarity")
async def similarity_check(req: SimilarityRequest):
    """
    计算两个作品的相似度。
    支持多种算法: hash完全匹配, Jaccard词集相似度, Levenshtein编辑距离, 综合评分。
    """
    try:
        hash_a = _compute_hash(req.content_a, "SHA256")
        hash_b = _compute_hash(req.content_b, "SHA256")
        hash_match = hash_a == hash_b

        jaccard = _jaccard_similarity(req.content_a, req.content_b)
        levenshtein = _levenshtein_ratio(req.content_a, req.content_b)
        char_ngram = _char_ngram_similarity(req.content_a, req.content_b, n=4)

        # Weighted combined score
        combined = round(0.3 * jaccard + 0.35 * levenshtein + 0.35 * char_ngram, 4)

        # Determine risk level
        if hash_match:
            risk_level = "critical"
        elif combined > 0.85:
            risk_level = "high"
        elif combined > 0.60:
            risk_level = "medium"
        elif combined > 0.30:
            risk_level = "low"
        else:
            risk_level = "none"

        method_result = {
            "hash": 1.0 if hash_match else 0.0,
            "jaccard": round(jaccard, 4),
            "levenshtein": round(levenshtein, 4),
            "char_ngram": round(char_ngram, 4),
            "combined": combined,
        }

        logger.info(f"Similarity check: source={req.source_id}, risk={risk_level}, combined={combined}")
        return {
            "ok": True,
            "data": {
                "source_id": req.source_id,
                "hash_a": hash_a[:16] + "...",
                "hash_b": hash_b[:16] + "...",
                "hash_match": hash_match,
                "similarity_scores": method_result,
                "max_similarity": combined,
                "risk_level": risk_level,
                "method_used": req.method,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        }
    except Exception as e:
        logger.exception(f"Similarity check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/attribution")
async def attribution_record(req: AttributionRequest):
    """创作者声明 + 授权链存证"""
    try:
        record_id = f"attr_{uuid.uuid4().hex[:12]}"
        recorded_at = datetime.now(timezone.utc).isoformat()
        # Hash the attribution data as a simple "blockchain" stub
        attr_data = f"{req.creator}|{req.asset_id}|{req.license}|{recorded_at}"
        chain_hash = hashlib.sha256(attr_data.encode('utf-8')).hexdigest()

        # Store as copyright record
        with _get_db() as conn:
            conn.execute(
                "INSERT INTO copyright_records (id, asset_id, creator, license, copyright_text, embedded_at, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record_id, req.asset_id, req.creator, req.license,
                 f"Attribution chain hash: {chain_hash}", recorded_at, "{}")
            )
            conn.commit()

        logger.info(f"Attribution recorded: {record_id} for creator {req.creator}")
        return {
            "ok": True,
            "data": {
                "attribution_id": record_id,
                "creator": req.creator,
                "asset_id": req.asset_id,
                "license": req.license,
                "recorded_at": recorded_at,
                "chain_hash": chain_hash,
            }
        }
    except Exception as e:
        logger.exception(f"Attribution record failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/attribution/{asset_id}")
async def attribution_query(asset_id: str):
    """查询授权链 — 返回资产的所有创作者声明"""
    try:
        with _get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM copyright_records WHERE asset_id = ? ORDER BY embedded_at ASC",
                (asset_id,)
            ).fetchall()
        chain = [{
            "record_id": r["id"],
            "creator": r["creator"],
            "license": r["license"],
            "timestamp": r["embedded_at"],
        } for r in rows]
        return {
            "ok": True,
            "data": {
                "asset_id": asset_id,
                "chain": chain,
                "chain_length": len(chain),
                "verified": len(chain) > 0,
            }
        }
    except Exception as e:
        logger.exception(f"Query attribution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# C2PA 1.4 Content Authenticity Endpoints (P1-A1-W1)
# ============================================================================
# These endpoints implement the C2PA manifest lifecycle:
#   POST /c2pa/sign                  — sign an asset, return manifest_id
#   GET  /c2pa/verify/{asset_id}     — verify a signed asset by ID
#   GET  /c2pa/manifest/{manifest_id}— retrieve a stored manifest
#   POST /c2pa/revoke/{manifest_id}  — revoke a manifest (add to CRL)
#   GET  /c2pa/crl                   — list revoked manifests
# ============================================================================

_C2PA_CERT_PATH = os.environ.get(
    "C2PA_CERT_PATH", str(_DATA_DIR / "c2pa_cert.pem")
)
_C2PA_KEY_PATH = os.environ.get(
    "C2PA_KEY_PATH", str(_DATA_DIR / "c2pa_key.pem")
)
_c2pa_engine: Optional["C2PAEngine"] = None
_c2pa_engine_lock_path = str(_DATA_DIR / ".c2pa_init.lock")


def _get_c2pa_engine() -> "C2PAEngine":
    """Lazy singleton accessor for the C2PAEngine instance."""
    global _c2pa_engine
    if _c2pa_engine is None:
        if not _C2PA_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="C2PA engine not available (cryptography lib missing)",
            )
        _c2pa_engine = C2PAEngine(_C2PA_CERT_PATH, _C2PA_KEY_PATH)
        # Restore CRL from DB
        try:
            with _get_db() as conn:
                rows = conn.execute(
                    "SELECT id FROM c2pa_manifests WHERE revoked = 1"
                ).fetchall()
                for r in rows:
                    if r["id"] not in _c2pa_engine.crl:
                        _c2pa_engine.crl.append(r["id"])
        except Exception as e:
            logger.warning(f"Failed to restore CRL from DB: {e}")
    return _c2pa_engine


def _reset_c2pa_engine_for_tests() -> None:
    """Reset singleton state between pytest runs."""
    global _c2pa_engine
    _c2pa_engine = None


# ── Pydantic models for C2PA endpoints ──────────────────────────────────
class C2PASignRequest(BaseModel):
    asset_path: str = Field(..., min_length=1, max_length=4096,
                            description="Absolute path to the asset to sign")
    claim: Dict[str, Any] = Field(
        default_factory=dict,
        description="C2PA claim payload (creator, actions, license, etc.)"
    )


class C2PARevokeRequest(BaseModel):
    reason: str = Field(default="", max_length=512,
                         description="Optional reason for revocation")


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/c2pa/sign")
async def c2pa_sign(req: C2PASignRequest):
    """Sign an asset with a C2PA 1.4 manifest.

    Body: { "asset_path": "...", "claim": { ... } }
    Returns: { "manifest_id": "manifest_xxx", "manifest": {...} }
    Status:
        200 — signed successfully
        400 — invalid request (missing field, bad claim shape)
        404 — asset file not found
        500 — signing failed
    """
    try:
        if not req.asset_path:
            raise HTTPException(status_code=400, detail="asset_path required")
        if not os.path.exists(req.asset_path):
            raise HTTPException(
                status_code=404,
                detail=f"Asset not found: {req.asset_path}",
            )
        if not isinstance(req.claim, dict):
            raise HTTPException(status_code=400, detail="claim must be a dict")

        engine = _get_c2pa_engine()
        manifest = engine.sign_asset(req.asset_path, req.claim)

        # Persist
        with _get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO c2pa_manifests "
                "(id, asset_path, asset_hash, claim_json, manifest_json, cert_fingerprint, revoked, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                (
                    manifest["manifest_id"],
                    req.asset_path,
                    manifest["asset_hash"],
                    json.dumps(req.claim, ensure_ascii=False),
                    json.dumps(manifest, ensure_ascii=False),
                    manifest["cert_fingerprint"],
                    manifest["issued_at"],
                ),
            )
            conn.commit()

        logger.info(f"C2PA manifest stored: {manifest['manifest_id']}")
        return {
            "ok": True,
            "data": {
                "manifest_id": manifest["manifest_id"],
                "asset_path": req.asset_path,
                "asset_hash": manifest["asset_hash"],
                "manifest": manifest,
            },
        }
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"C2PA sign failed: {e}")
        raise HTTPException(status_code=500, detail=f"C2PA sign failed: {str(e)}")


@router.get("/c2pa/verify/{asset_id}")
async def c2pa_verify(asset_id: str):
    """Verify a C2PA signature for an asset.

    asset_id: either the manifest_id or the original asset_path used at sign
              time. If a manifest_id is given, we look up the asset_path from
              the DB; otherwise we treat the path literally.

    Returns: { "is_valid": bool, "manifest": {...} }
    Status:
        200 — verification completed (check is_valid in body)
        404 — manifest/asset not found
    """
    try:
        # Resolve asset_path from manifest_id
        asset_path: Optional[str] = None
        manifest_id_hint: Optional[str] = None
        if asset_id.startswith("manifest_"):
            with _get_db() as conn:
                row = conn.execute(
                    "SELECT asset_path FROM c2pa_manifests WHERE id = ?",
                    (asset_id,),
                ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=404, detail=f"Manifest {asset_id} not found"
                )
            asset_path = row["asset_path"]
            manifest_id_hint = asset_id
        else:
            asset_path = asset_id

        if not os.path.exists(asset_path):
            raise HTTPException(
                status_code=404, detail=f"Asset file not found: {asset_path}"
            )

        engine = _get_c2pa_engine()
        is_valid, result = engine.verify_signature(asset_path)
        # If we have a manifest_id, also look it up
        if not manifest_id_hint and "manifest_id" in result:
            manifest_id_hint = result["manifest_id"]
        return {
            "ok": True,
            "data": {
                "asset_path": asset_path,
                "manifest_id": manifest_id_hint,
                "is_valid": is_valid,
                "result": result,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"C2PA verify failed: {e}")
        raise HTTPException(status_code=500, detail=f"C2PA verify failed: {str(e)}")


@router.get("/c2pa/manifest/{manifest_id}")
async def c2pa_get_manifest(manifest_id: str):
    """Retrieve a stored C2PA manifest by its manifest_id.

    Returns: { "manifest_id": "...", "manifest": {...} }
    Status:
        200 — found
        404 — manifest not found
    """
    try:
        with _get_db() as conn:
            row = conn.execute(
                "SELECT manifest_json, revoked FROM c2pa_manifests WHERE id = ?",
                (manifest_id,),
            ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Manifest {manifest_id} not found"
            )
        manifest = json.loads(row["manifest_json"])
        manifest["revoked"] = bool(row["revoked"])
        return {"ok": True, "data": {"manifest_id": manifest_id, "manifest": manifest}}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"C2PA get manifest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/c2pa/revoke/{manifest_id}")
async def c2pa_revoke(manifest_id: str, req: C2PARevokeRequest = Body(default=C2PARevokeRequest())):
    """Revoke a C2PA manifest (add to CRL).

    Status:
        200 — newly revoked
        404 — manifest not found
        409 — already revoked
    """
    try:
        with _get_db() as conn:
            row = conn.execute(
                "SELECT id, revoked FROM c2pa_manifests WHERE id = ?",
                (manifest_id,),
            ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Manifest {manifest_id} not found"
            )
        if row["revoked"]:
            raise HTTPException(
                status_code=409, detail=f"Manifest {manifest_id} already revoked"
            )

        engine = _get_c2pa_engine()
        newly_revoked = engine.revoke(manifest_id)

        with _get_db() as conn:
            conn.execute(
                "UPDATE c2pa_manifests SET revoked = 1 WHERE id = ?",
                (manifest_id,),
            )
            conn.commit()

        return {
            "ok": True,
            "data": {
                "manifest_id": manifest_id,
                "revoked": True,
                "newly_revoked": newly_revoked,
                "reason": req.reason,
                "revoked_at": datetime.now(timezone.utc).isoformat(),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"C2PA revoke failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/c2pa/crl")
async def c2pa_get_crl():
    """Get the C2PA Certificate/Manifest Revocation List (CRL).

    Returns: { "revoked": [{manifest_id, revoked_at}], "count": N }
    """
    try:
        engine = _get_c2pa_engine()
        crl = engine.get_crl()
        return {"ok": True, "data": {"revoked": crl, "count": len(crl)}}
    except Exception as e:
        logger.exception(f"C2PA get CRL failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Video Watermark Endpoints (P1-A1-W2)
# ─────────────────────────────────────────────────────────────────────────────

_WATERMARK_OUTPUT_DIR = str(_DATA_DIR / "watermark_videos")


def _get_watermark_engine():
    """Lazy import the watermark engine to avoid heavy startup cost."""
    try:
        from engines.watermark_engine import WatermarkEngine, WatermarkInputError, WatermarkProcessingError
        return WatermarkEngine(output_dir=_WATERMARK_OUTPUT_DIR), WatermarkInputError, WatermarkProcessingError
    except ImportError as e:
        logger.error(f"WatermarkEngine import failed: {e}")
        raise HTTPException(status_code=503, detail="Watermark engine not available")


def _resolve_output_path(input_path: str, output_path: Optional[str], suffix: str = "_watermarked") -> str:
    if output_path:
        return output_path
    base, ext = os.path.splitext(input_path)
    return f"{base}{suffix}{ext or '.mp4'}"


@router.post("/watermark/text")
async def watermark_text(req: VideoTextWatermarkRequest):
    """
    Apply a text watermark to a video via ffmpeg drawtext.

    Request body: VideoTextWatermarkRequest
    Returns: { ok, data: { watermark_id, output_path, ... } }
    """
    try:
        engine, WatermarkInputError, WatermarkProcessingError = _get_watermark_engine()
    except HTTPException:
        raise

    if not os.path.exists(req.input_path):
        raise HTTPException(status_code=400, detail=f"Input video not found: {req.input_path}")

    output_path = _resolve_output_path(req.input_path, req.output_path)

    try:
        result = engine.add_text_watermark(
            input_path=req.input_path,
            output_path=output_path,
            text=req.text,
            position=req.position,
            opacity=req.opacity,
            font_size=req.font_size,
        )
    except (WatermarkInputError, WatermarkProcessingError) as e:
        logger.warning(f"text watermark failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"text watermark unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Watermark processing error: {str(e)}")

    return {
        "ok": True,
        "data": {
            "watermark_id": result.watermark_id,
            "video_id": req.video_id,
            "kind": result.kind,
            "text": result.text,
            "position": result.position,
            "opacity": result.opacity,
            "output_path": result.output_path,
            "input_size": result.input_size,
            "output_size": result.output_size,
            "duration": result.duration,
            "width": result.width,
            "height": result.height,
            "elapsed_sec": result.elapsed_sec,
            "ffmpeg_available": engine.available,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.post("/watermark/image")
async def watermark_image(req: VideoImageWatermarkRequest):
    """
    Apply a logo image watermark to a video via ffmpeg overlay.

    Request body: VideoImageWatermarkRequest
    Returns: { ok, data: { watermark_id, output_path, ... } }
    """
    try:
        engine, WatermarkInputError, WatermarkProcessingError = _get_watermark_engine()
    except HTTPException:
        raise

    if not os.path.exists(req.input_path):
        raise HTTPException(status_code=400, detail=f"Input video not found: {req.input_path}")
    if not os.path.exists(req.logo_path):
        raise HTTPException(status_code=400, detail=f"Logo image not found: {req.logo_path}")

    output_path = _resolve_output_path(req.input_path, req.output_path, suffix="_logo")

    try:
        result = engine.add_image_watermark(
            input_path=req.input_path,
            output_path=output_path,
            logo_path=req.logo_path,
            position=req.position,
            opacity=req.opacity,
            scale=req.scale,
        )
    except (WatermarkInputError, WatermarkProcessingError) as e:
        logger.warning(f"image watermark failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"image watermark unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Watermark processing error: {str(e)}")

    return {
        "ok": True,
        "data": {
            "watermark_id": result.watermark_id,
            "video_id": req.video_id,
            "kind": result.kind,
            "logo_path": req.logo_path,
            "position": result.position,
            "opacity": result.opacity,
            "scale": req.scale,
            "output_path": result.output_path,
            "input_size": result.input_size,
            "output_size": result.output_size,
            "duration": result.duration,
            "width": result.width,
            "height": result.height,
            "elapsed_sec": result.elapsed_sec,
            "ffmpeg_available": engine.available,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/watermark/verify/{video_id}")
async def watermark_verify(video_id: str, video_path: Optional[str] = Query(default=None)):
    """
    Verify a watermark exists on the given video.

    Path param:
        video_id: the asset id (used to look up an optional watermark record)
    Query param:
        video_path (optional): absolute path to the video to verify; if omitted,
            the most recent record for video_id is used.
    """
    try:
        engine, _, _ = _get_watermark_engine()
    except HTTPException:
        raise

    # Resolve video path
    if not video_path:
        # Find most recent record for this video_id
        candidates = [
            r for r in engine._records.values() if r.video_id == video_id
        ]
        if not candidates:
            raise HTTPException(status_code=404, detail=f"No watermark record found for video_id={video_id}")
        candidates.sort(key=lambda r: r.created_at, reverse=True)
        rec = candidates[0]
        video_path = rec.output_path

    if not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail=f"Video file not found: {video_path}")

    # Find the latest record for this path (best effort)
    wm_id: Optional[str] = None
    for rid, r in engine._records.items():
        if r.output_path == video_path:
            wm_id = rid
            break

    verified = engine.verify_watermark(video_path, watermark_id=wm_id)
    return {
        "ok": True,
        "data": {
            "video_id": video_id,
            "video_path": video_path,
            "watermark_id": wm_id,
            "verified": bool(verified),
            "ffmpeg_available": engine.available,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        },
    }

