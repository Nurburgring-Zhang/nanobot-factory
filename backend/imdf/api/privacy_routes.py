"""
F8.4 PII/DSAR 数据隐私 API — 真实化实现
=========================================
- /pii/scan: 检测文本中的PII (regex + Luhn + ID checksum + optional spaCy)
- /pii/redact: 脱敏 (mask / replace / hash / remove)
- /pii/scan_field: 基于字段名+值的启发式 PII 扫描
- /dsar/export: Article 15 数据访问请求
- /dsar/erase: Article 17 被遗忘权
- /dsar/anonymize: Article 17 匿名化 (保留统计价值)
- /dsar/portability: Article 20 数据可携
- /audit/{user_id}: 查看用户的所有 DSAR 操作审计
- /consent/record: 记录用户同意
- /consent/{user_id}: 查询用户同意

实现:
  - PIIEngine: 引擎化正则 + Luhn + ID checksum + 可选 spaCy NER
  - DSAREngine: SQLite + 哈希链审计 (SHA-256 chain)
  - 两者位于 engines/ 目录,可被其他模块直接复用
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# R2-3: 路径 ID 校验
from api._common.validators import validate_id

# P1-A2-W1: 引擎依赖
from engines.pii_engine import (
    PIIEngine,
    PII_LABELS,
    PII_TYPE_EMAIL,
    PII_TYPE_PHONE_CN,
    PII_TYPE_ID_CARD_CN,
    PII_TYPE_CREDIT_CARD,
    PII_TYPE_IPV4,
    PII_TYPE_GENERIC,
    FIELD_HEURISTIC_PII,
)
from engines.dsar_engine import DSAREngine

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])

# ── Engine singletons (lazy-init) ───────────────────────────────────────────
_pii_engine: Optional[PIIEngine] = None
_dsar_engine: Optional[DSAREngine] = None


def _get_pii_engine() -> PIIEngine:
    global _pii_engine
    if _pii_engine is None:
        _pii_engine = PIIEngine(use_ml=False)
    return _pii_engine


def _get_dsar_engine() -> DSAREngine:
    global _dsar_engine
    if _dsar_engine is None:
        # Honor module-level DB_PATH so tests can redirect to a tmp DB.
        _dsar_engine = DSAREngine(db_path=DB_PATH)
    return _dsar_engine


def _reset_pii_engine_for_tests() -> None:
    global _pii_engine
    _pii_engine = None


def _reset_dsar_engine_for_tests() -> None:
    global _dsar_engine
    _dsar_engine = None


# ── Legacy DB path kept for back-compat with existing endpoints ────────────
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BACKEND_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_DATA_DIR / "privacy.db")


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db():
    """Legacy pii_detection_log / dsar_requests tables (legacy endpoints)."""
    with _get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS dsar_requests (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                request_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                scope TEXT DEFAULT 'all',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                metadata TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS pii_detection_log (
                id TEXT PRIMARY KEY,
                user_id TEXT DEFAULT '',
                content_hash TEXT NOT NULL,
                pii_types TEXT DEFAULT '[]',
                pii_count INTEGER DEFAULT 0,
                detected_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_dsar_user ON dsar_requests(user_id);
        """)
    # Also initialize the DSAR engine (creates user_data, consent_records, dsar_audit)
    _get_dsar_engine()

_init_db()

# ── PII Patterns (legacy alias) ─────────────────────────────────────────────
# PII_LABELS is now imported from engines.pii_engine. PII_PATTERNS kept as
# an empty list for back-compat with any module that imports the name.
PII_PATTERNS: List = []
# Back-compat: keep the legacy checksum validator reachable as a symbol.
from engines.pii_engine import _verify_cn_id_checksum  # noqa: E402  type: ignore

# ── Pydantic Models ─────────────────────────────────────────────────────────

class PIIDetectRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100000, description="要检测的文本内容")
    user_id: str = Field(default="", max_length=128)
    patterns: Optional[List[str]] = Field(default=None, description="指定检测哪些PII类型，不指定则全检")

class PIIMaskRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100000)
    user_id: str = Field(default="", max_length=128)
    method: str = Field(default="replacement", pattern="^(replacement|redaction|hash)$")
    mask_char: str = Field(default="*", max_length=1)

class DSARExportRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    data_types: Optional[List[str]] = Field(default=None)
    format: str = Field(default="json", pattern="^(json|csv)$")

class DSARDeleteRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    scope: str = Field(default="all", pattern="^(all|specific_categories)$")
    categories: Optional[List[str]] = Field(default=None)

class ConsentRecordRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    purpose: str = Field(..., min_length=1, max_length=128)
    action: str = Field(..., pattern="^(granted|withdrawn)$")
    version: str = Field(default="v1.0", max_length=32)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ── P1-A2-W1: new Pydantic models (engine-driven endpoints) ────────────────

class PIIRedactRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100000)
    user_id: str = Field(default="", max_length=128)
    strategy: str = Field(default="mask", pattern="^(mask|replace|hash|remove)$")
    types: Optional[List[str]] = Field(default=None)
    mask_char: str = Field(default="*", max_length=1)


class PIIScanFieldRequest(BaseModel):
    field_name: str = Field(..., min_length=1, max_length=128)
    value: Any = Field(...)


class DSARAnonymizeRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)


class DSARPortabilityRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)

# ── Helper Functions ─────────────────────────────────────────────────────────

def _detect_pii(text: str, patterns: Optional[List[str]] = None) -> List[Dict]:
    """Detect PII in text using the PIIEngine. Returns legacy dict format."""
    eng = _get_pii_engine()
    matches = eng.detect(text, types=patterns)
    out: List[Dict[str, Any]] = []
    for m in matches:
        out.append({
            "type": m.type,
            "label": m.label,
            "value": m.value,
            "confidence": m.confidence,
            "position": {"start": m.start, "end": m.end},
        })
    return out


def _mask_text(text: str, pii_results: List[Dict], method: str, mask_char: str = "*") -> str:
    """Mask PII in text — legacy replacement/redaction/hash strategies.

    Internally delegates to PIIEngine.redact by re-running detection. The
    'method' values are aliased to the engine strategies:
      - replacement -> replace
      - redaction   -> remove  (legacy: emits [REDACTED:TYPE] tags)
      - hash        -> hash
    """
    if not pii_results:
        return text
    # Re-detect using the engine so we get the full PIIMatch objects.
    eng = _get_pii_engine()
    matches = eng.detect(text)
    if not matches:
        return text

    if method == "replacement":
        return eng.redact(text, strategy="replace", mask_char=mask_char)
    if method == "hash":
        return eng.redact(text, strategy="hash", mask_char=mask_char)
    # Legacy "redaction" → emit [REDACTED:TYPE] tags (engine "remove" drops content)
    out = text
    for m in sorted(matches, key=lambda x: x.start, reverse=True):
        tag = f"[REDACTED:{m.type.upper()}]"
        out = out[:m.start] + tag + out[m.end:]
    return out


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health")
async def privacy_health():
    """健康检查"""
    try:
        with _get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "module": "privacy", "version": "1.0.0", "db": "connected"}
    except Exception as e:
        return {"status": "degraded", "module": "privacy", "version": "1.0.0", "db_error": str(e)}


@router.post("/pii/detect")
async def pii_detect(req: PIIDetectRequest):
    """
    检测文本中的PII: 使用正则引擎匹配邮箱/手机/身份证/地址等。
    返回所有检测到的PII类型、位置和置信度。
    """
    try:
        results = _detect_pii(req.text, req.patterns)
        pii_types = list(set(r["type"] for r in results))
        content_hash = hashlib.sha256(req.text.encode()).hexdigest()

        # Log detection
        log_id = f"pii_{uuid.uuid4().hex[:12]}"
        with _get_db() as conn:
            conn.execute(
                "INSERT INTO pii_detection_log (id, user_id, content_hash, pii_types, pii_count, detected_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (log_id, req.user_id, content_hash, json.dumps(pii_types), len(results),
                 datetime.now(timezone.utc).isoformat())
            )
            conn.commit()

        logger.info(f"PII detection: {len(results)} items found, types={pii_types}")
        return {
            "ok": True,
            "data": {
                "pii_found": results,
                "contains_pii": len(results) > 0,
                "pii_types": pii_types,
                "total_count": len(results),
                "content_hash": content_hash[:16] + "...",
            }
        }
    except Exception as e:
        logger.exception(f"PII detection failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pii/mask")
async def pii_mask(req: PIIMaskRequest):
    """
    脱敏处理: 对检测到的PII进行脱敏(替换/遮蔽/哈希)。
    """
    try:
        # First detect
        results = _detect_pii(req.text)
        if not results:
            return {
                "ok": True,
                "data": {
                    "masked_text": req.text,
                    "pii_found": [],
                    "masked_count": 0,
                }
            }

        masked_text = _mask_text(req.text, results, req.method, req.mask_char)

        logger.info(f"PII masked: {len(results)} items using method={req.method}")
        return {
            "ok": True,
            "data": {
                "masked_text": masked_text,
                "original_length": len(req.text),
                "masked_length": len(masked_text),
                "pii_found": [{"type": r["type"], "label": r["label"]} for r in results],
                "masked_count": len(results),
                "method": req.method,
            }
        }
    except Exception as e:
        logger.exception(f"PII masking failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dsar/export")
async def dsar_export(req: DSARExportRequest):
    """
    导出用户数据: 从数据库读取用户的所有数据并返回。
    实现 GDPR Art.15 (访问权) & Art.20 (数据可携权)。
    """
    try:
        dsar_id = f"dsar_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()

        with _get_db() as conn:
            # Query user data
            if req.data_types:
                placeholders = ",".join("?" * len(req.data_types))
                rows = conn.execute(
                    f"SELECT * FROM user_data WHERE user_id = ? AND data_type IN ({placeholders})",
                    [req.user_id] + req.data_types
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM user_data WHERE user_id = ?", (req.user_id,)
                ).fetchall()

            # Get consent records
            consents = conn.execute(
                "SELECT * FROM consent_records WHERE user_id = ?", (req.user_id,)
            ).fetchall()

            # Record DSAR request
            conn.execute(
                "INSERT INTO dsar_requests (id, user_id, request_type, status, scope, created_at, updated_at) "
                "VALUES (?, ?, 'export', 'completed', ?, ?, ?)",
                (dsar_id, req.user_id, req.scope if hasattr(req, 'scope') else 'all', created_at, created_at)
            )
            conn.commit()

        data_categories = list(set(r["data_type"] for r in rows))
        exported_data = [{
            "id": r["id"],
            "data_type": r["data_type"],
            "content": r["content"],
            "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
            "created_at": r["created_at"],
        } for r in rows]

        consent_data = [{
            "purpose": c["purpose"],
            "action": c["action"],
            "recorded_at": c["recorded_at"],
            "version": c["version"],
        } for c in consents]

        logger.info(f"DSAR export: user={req.user_id}, data_categories={data_categories}, records={len(rows)}")
        return {
            "ok": True,
            "data": {
                "request_id": dsar_id,
                "user_id": req.user_id,
                "status": "completed",
                "data_categories": data_categories,
                "exported_data": exported_data,
                "consents": consent_data,
                "total_records": len(rows),
                "exported_at": created_at,
            }
        }
    except Exception as e:
        logger.exception(f"DSAR export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dsar/status/{request_id}")
async def dsar_status(request_id: str):
    """查询DSAR请求状态"""
    validate_id(request_id, "request_id")
    try:
        with _get_db() as conn:
            row = conn.execute("SELECT * FROM dsar_requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"DSAR request {request_id} not found")
        return {
            "ok": True,
            "data": {
                "request_id": row["id"],
                "user_id": row["user_id"],
                "request_type": row["request_type"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "completed_at": row["completed_at"],
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"DSAR status query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dsar/delete")
async def dsar_delete(req: DSARDeleteRequest):
    """
    删除用户数据: 按scope删除用户的相关数据。
    实现 GDPR Art.17 (被遗忘权)。
    """
    try:
        dsar_id = f"dsar_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()

        with _get_db() as conn:
            # Count records to delete
            if req.scope == "all":
                count_row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM user_data WHERE user_id = ?", (req.user_id,)
                ).fetchone()
            else:
                placeholders = ",".join("?" * len(req.categories)) if req.categories else ""
                count_row = conn.execute(
                    f"SELECT COUNT(*) as cnt FROM user_data WHERE user_id = ? AND data_type IN ({placeholders})",
                    [req.user_id] + (req.categories or [''])
                ).fetchone()

            deleted_count = count_row["cnt"] if count_row else 0

            # Perform delete
            if req.scope == "all":
                conn.execute("DELETE FROM user_data WHERE user_id = ?", (req.user_id,))
                conn.execute("DELETE FROM consent_records WHERE user_id = ?", (req.user_id,))
            elif req.categories:
                placeholders = ",".join("?" * len(req.categories))
                conn.execute(
                    f"DELETE FROM user_data WHERE user_id = ? AND data_type IN ({placeholders})",
                    [req.user_id] + req.categories
                )

            # Record DSAR request
            conn.execute(
                "INSERT INTO dsar_requests (id, user_id, request_type, status, scope, created_at, updated_at, completed_at) "
                "VALUES (?, ?, 'delete', 'completed', ?, ?, ?, ?)",
                (dsar_id, req.user_id, req.scope, created_at, created_at, created_at)
            )
            conn.commit()

        logger.info(f"DSAR delete: user={req.user_id}, deleted={deleted_count} records, scope={req.scope}")
        return {
            "ok": True,
            "data": {
                "request_id": dsar_id,
                "user_id": req.user_id,
                "status": "completed",
                "deletion_scope": req.scope,
                "deleted_records": deleted_count,
                "deleted_at": created_at,
                "retention_note": "Audit trail and DSAR request records are retained as legally required.",
            }
        }
    except Exception as e:
        logger.exception(f"DSAR delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/consent/record")
async def consent_record(req: ConsentRecordRequest):
    """
    记录用户同意: 记录用户对特定数据处理目的的同意或撤销。
    """
    try:
        consent_id = f"consent_{uuid.uuid4().hex[:12]}"
        recorded_at = datetime.now(timezone.utc).isoformat()

        with _get_db() as conn:
            conn.execute(
                "INSERT INTO consent_records (id, user_id, purpose, action, version, recorded_at, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (consent_id, req.user_id, req.purpose, req.action, req.version,
                 recorded_at, json.dumps(req.metadata))
            )
            conn.commit()

        logger.info(f"Consent recorded: {consent_id}, user={req.user_id}, purpose={req.purpose}, action={req.action}")
        return {
            "ok": True,
            "data": {
                "consent_id": consent_id,
                "user_id": req.user_id,
                "purpose": req.purpose,
                "action": req.action,
                "version": req.version,
                "recorded_at": recorded_at,
            }
        }
    except Exception as e:
        logger.exception(f"Consent record failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/consent/{user_id}")
async def consent_query(user_id: str):
    """查询用户同意状态"""
    validate_id(user_id, "user_id")
    try:
        with _get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM consent_records WHERE user_id = ? ORDER BY recorded_at DESC",
                (user_id,)
            ).fetchall()

        # Get latest consent per purpose
        purposes = {}
        for r in rows:
            if r["purpose"] not in purposes:
                purposes[r["purpose"]] = {
                    "purpose": r["purpose"],
                    "status": r["action"],
                    "granted_at": r["recorded_at"] if r["action"] == "granted" else None,
                    "version": r["version"],
                }

        consents = list(purposes.values())
        return {
            "ok": True,
            "data": {
                "user_id": user_id,
                "consents": consents,
                "total_purposes": len(consents),
            }
        }
    except Exception as e:
        logger.exception(f"Consent query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Helper: Seed some test user data (for testing export/delete) ─────────────

@router.post("/_seed_test_data")
async def seed_test_data(user_id: str = "test_user_001"):
    """（测试用）为指定用户生成测试数据"""
    try:
        now = datetime.now(timezone.utc).isoformat()
        records = [
            ("profile", json.dumps({"name": "Test User", "email": "test@example.com"})),
            ("uploads", json.dumps({"filename": "test_image.png", "size": 1024})),
            ("annotations", json.dumps({"count": 5, "labels": ["cat", "dog"]})),
            ("generated_content", json.dumps({"prompt": "a cat", "result": "image_001"})),
        ]
        with _get_db() as conn:
            for dtype, content in records:
                rid = f"ud_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO user_data (id, user_id, data_type, content, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (rid, user_id, dtype, content, "{}", now)
                )
            conn.commit()
        return {"ok": True, "message": f"Seeded {len(records)} test records for user {user_id}"}
    except Exception as e:
        logger.exception(f"Seed test data failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════
# P1-A2-W1: engine-driven endpoints (new naming, full coverage)
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/pii/scan")
async def pii_scan(req: PIIDetectRequest):
    """P1-A2-W1: scan free-form text for PII via PIIEngine.

    Same payload as /pii/detect, exposed under the new naming for parity
    with downstream P1-A2 consumers.
    """
    try:
        eng = _get_pii_engine()
        matches = eng.detect(req.text, types=req.patterns)
        results = [
            {
                "type": m.type,
                "label": m.label,
                "value": m.value,
                "confidence": m.confidence,
                "position": {"start": m.start, "end": m.end},
                "strategy": m.strategy,
            }
            for m in matches
        ]
        return {
            "ok": True,
            "data": {
                "pii_found": results,
                "contains_pii": len(results) > 0,
                "pii_types": sorted({r["type"] for r in results}),
                "total_count": len(results),
                "engine": "PIIEngine",
                "supported_types": eng.supported_types(),
            },
        }
    except Exception as e:
        logger.exception(f"pii_scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pii/redact")
async def pii_redact(req: PIIRedactRequest):
    """P1-A2-W1: redact PII using one of 4 strategies.

    Strategies:
      * mask    — full-width replacement with mask_char (default *)
      * replace — partial mask, preserves type-specific structure
      * hash    — [HASH:12-hex] tag, value never recoverable
      * remove  — strip PII + collapse whitespace
    """
    try:
        eng = _get_pii_engine()
        redacted = eng.redact(req.text, strategy=req.strategy, types=req.types, mask_char=req.mask_char)
        # Echo back what was detected
        matches = eng.detect(req.text, types=req.types)
        return {
            "ok": True,
            "data": {
                "redacted_text": redacted,
                "strategy": req.strategy,
                "pii_found": [
                    {"type": m.type, "label": m.label, "value": m.value}
                    for m in matches
                ],
                "redacted_count": len(matches),
                "original_length": len(req.text),
                "redacted_length": len(redacted),
            },
        }
    except Exception as e:
        logger.exception(f"pii_redact failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pii/scan_field")
async def pii_scan_field(req: PIIScanFieldRequest):
    """P1-A2-W1: scan a single structured field (column-style) for PII.

    Combines:
      * field_name heuristic (column name → pii type)
      * value regex scan (with type filter from heuristic)

    Returns action: 'allow' | 'warn' | 'redact' | 'block'.
    """
    try:
        eng = _get_pii_engine()
        result = eng.scan_field(req.field_name, req.value)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.exception(f"pii_scan_field failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dsar/anonymize")
async def dsar_anonymize(req: DSARAnonymizeRequest):
    """P1-A2-W1 / Article 17: anonymize a user (preserve statistical value).

    Replaces identifiable fields in user_data.content and remaps the
    user_id to a one-way hash (ANON_USER_<8 hex>). The audit chain
    records both the original and anonymous user_id.
    """
    try:
        engine = _get_dsar_engine()
        result = engine.anonymize(req.user_id)
        return {"ok": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"dsar_anonymize failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dsar/portability")
async def dsar_portability(req: DSARPortabilityRequest):
    """P1-A2-W1 / Article 20: machine-readable data portability export.

    Returns a structured JSON envelope under schema 'GDPR-Article20-v1'.
    Suitable for ingestion by another service.
    """
    try:
        engine = _get_dsar_engine()
        result = engine.portability(req.user_id)
        return {"ok": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"dsar_portability failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit/{user_id}")
async def dsar_audit(user_id: str):
    """P1-A2-W1: return the full DSAR audit trail for a user.

    Each record carries the SHA-256 chain hash linking it to the
    previous record. The response also includes a chain verification
    summary that external auditors can re-run.
    """
    validate_id(user_id, "user_id")
    try:
        engine = _get_dsar_engine()
        trail = engine.get_audit_trail(user_id)
        verification = engine.verify_audit_chain(user_id)
        return {
            "ok": True,
            "data": {
                "user_id": user_id,
                "total_records": len(trail),
                "audit_trail": trail,
                "chain_verification": verification,
            },
        }
    except Exception as e:
        logger.exception(f"dsar_audit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
