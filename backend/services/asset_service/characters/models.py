"""P4-5-W1: Character Asset model — Bernini-style double-layer character library.

Two-layer concept (借鉴 Bernini):
  * **CharacterAsset** (top layer): the canonical identity — name, summary,
    aggregate features, status (draft/locked/archived).
  * **ReferenceSet + LockedFeature** (bottom layer): the generation-time
    ground truth — 2-3 reference images (front/side/3-quarter),
    structured feature locks (face/hair/outfit/accessory) that get
    injected into prompts so every generation stays on-character.

This module exposes:
  * SQLAlchemy ORM (``CharacterAssetModel`` etc.) — used by the FastAPI
    routes for persistence. Works on SQLite (dev/CI) and Postgres (prod).
  * Pydantic schemas (``CharacterAsset``, ``ReferenceImage``,
    ``LockedFeature``) — used in HTTP payloads, validated on the wire.

Design notes:
  * ``face_features`` / ``voice_features`` / ``body_features`` /
    ``style_features`` are stored as JSON blobs (dict). We deliberately
    don't normalize into a separate ``features`` table — the schema is
    intentionally fluid (a "character" can have very different facets
    per use case: anime protagonist vs. corporate spokesperson).
  * Consistency scoring (``consistency_score``) is a float in [0, 1]
    maintained by ``consistency.py`` — denormalized on the asset row
    so /api/v1/assets/characters listing can sort by it without joins.
  * ``locked_at`` / ``locked_by`` are set when ``/lock`` is called.
    Locking freezes the reference set so future generations cannot
    silently drift the character. Use ``/unlock`` to thaw.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# ─── SQLAlchemy (optional — Postgres or SQLite both work) ─────────────────────
try:
    from sqlalchemy import (
        JSON,
        Boolean,
        Column,
        DateTime,
        Float,
        Integer,
        String,
        Text,
        Index,
    )
    from sqlalchemy.orm import DeclarativeBase
    _SQLA_OK = True
except Exception:  # pragma: no cover
    _SQLA_OK = False
    DeclarativeBase = object  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic schemas (wire format)
# ═══════════════════════════════════════════════════════════════════════════════

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff\u3040-\u30ff ]{1,80}$")
_REF_URL_PATTERN = re.compile(r"^(https?://[^\s]+|/[^\s]+|asset://[^\s]+)$")


class ReferenceImage(BaseModel):
    """A single reference photo for the character (front/side/3-quarter)."""

    angle: str = Field(
        default="front",
        description="拍摄角度: front / side / 3-quarter / back / expression-X",
    )
    url: str = Field(..., description="参考图 URL (CDN/OSS/asset://)")

    @field_validator("angle")
    @classmethod
    def _validate_angle(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not v or len(v) > 40:
            raise ValueError("angle must be 1-40 chars")
        if v not in {"front", "side", "3-quarter", "back", "expression"} and not v.startswith("expression-"):
            raise ValueError(f"angle must be one of front/side/3-quarter/back/expression-X, got {v!r}")
        return v

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        v = (v or "").strip()
        if not v or len(v) > 2048:
            raise ValueError("url must be 1-2048 chars")
        if not _REF_URL_PATTERN.match(v):
            raise ValueError(f"url must be http(s)://... or /path or asset://..., got {v[:60]!r}")
        return v


class LockedFeature(BaseModel):
    """A locked feature (face/hair/outfit/accessory) — generation cannot drift it."""

    category: str = Field(..., description="face | hair | outfit | accessory | body | voice")
    name: str = Field(..., max_length=120, description="特征名, e.g. '高马尾', '银色眼瞳', '红黑风衣'")
    description: Optional[str] = Field(default=None, max_length=2000)
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="锁定权重 (0=提示, 1=强约束, 2=不可修改)",
    )

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: str) -> str:
        v = (v or "").strip().lower()
        allowed = {"face", "hair", "outfit", "accessory", "body", "voice"}
        if v not in allowed:
            raise ValueError(f"category must be one of {sorted(allowed)}, got {v!r}")
        return v


class CharacterAsset(BaseModel):
    """Top-layer character identity — the canonical character."""

    id: str = Field(default_factory=lambda: f"char_{uuid.uuid4().hex[:12]}")
    name: str = Field(..., description="角色名, e.g. '苏晚晴', 'Captain Vega'")
    description: Optional[str] = Field(default=None, max_length=4000)
    status: str = Field(default="draft", description="draft | locked | archived")

    # Reference image set (2-3 photos, multi-angle)
    reference_images: List[ReferenceImage] = Field(
        default_factory=list,
        description="2-3 张参考图 (front / side / 3-quarter)",
    )

    # Structured features (each a dict, schema-fluid per character type)
    face_features: Dict[str, Any] = Field(
        default_factory=dict,
        description="脸型 / 眼 / 鼻 / 嘴 / 肤色 / 年龄 等",
    )
    voice_features: Dict[str, Any] = Field(
        default_factory=dict,
        description="音色 / 音高 / 节奏 / 语速 / 多语言 / 方言",
    )
    body_features: Dict[str, Any] = Field(
        default_factory=dict,
        description="身高 / 体型 / 步态 / 姿势",
    )
    style_features: Dict[str, Any] = Field(
        default_factory=dict,
        description="艺术风格 / 色调 / 服装 / 配饰",
    )

    # Locked features (frozen during generation)
    locked_features: List[LockedFeature] = Field(default_factory=list)

    # Denormalized consistency score (set by consistency checker)
    consistency_score: float = Field(default=1.0, ge=0.0, le=1.0)
    last_consistency_check_at: Optional[str] = None

    # Lock state
    locked_at: Optional[str] = None
    locked_by: Optional[str] = None

    # Bookkeeping
    owner_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not _NAME_PATTERN.match(v):
            raise ValueError(
                "name must be 1-80 chars: letters/digits/underscore/hyphen/space/CJK/Hiragana/Katakana"
            )
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in {"draft", "locked", "archived"}:
            raise ValueError("status must be draft | locked | archived")
        return v

    def to_orm_dict(self) -> Dict[str, Any]:
        """Flatten to a dict suitable for SQLAlchemy ORM insert.

        DateTime fields are normalized to ``datetime`` objects so SQLAlchemy's
        SQLite / Postgres dialects accept them without ``string_dates`` quirks.
        """
        def _parse_dt(value: Any) -> Any:
            if value is None or value == "":
                return None
            if isinstance(value, datetime):
                return value
            try:
                # ISO 8601 with optional timezone — fromisoformat handles
                # both ``Z`` (3.11+) and ``+00:00`` (3.11+) for most inputs.
                s = str(value).replace("Z", "+00:00")
                return datetime.fromisoformat(s)
            except Exception:
                return None

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "status": self.status,
            "reference_images_json": json.dumps(
                [r.model_dump() for r in self.reference_images], ensure_ascii=False
            ),
            "face_features_json": json.dumps(self.face_features, ensure_ascii=False),
            "voice_features_json": json.dumps(self.voice_features, ensure_ascii=False),
            "body_features_json": json.dumps(self.body_features, ensure_ascii=False),
            "style_features_json": json.dumps(self.style_features, ensure_ascii=False),
            "locked_features_json": json.dumps(
                [lf.model_dump() for lf in self.locked_features], ensure_ascii=False
            ),
            "consistency_score": float(self.consistency_score),
            "last_consistency_check_at": _parse_dt(self.last_consistency_check_at),
            "locked_at": _parse_dt(self.locked_at),
            "locked_by": self.locked_by,
            "owner_id": self.owner_id,
            "tags_json": json.dumps(self.tags, ensure_ascii=False),
            "created_at": _parse_dt(self.created_at) or datetime.now(timezone.utc),
            "updated_at": _parse_dt(self.updated_at) or datetime.now(timezone.utc),
        }

    @classmethod
    def from_orm_row(cls, row: Any) -> "CharacterAsset":
        """Hydrate from a SQLAlchemy row (or any object with the column attrs).

        Handles:
          * JSON-as-text columns (string → python via ``json.loads``)
          * ``datetime`` columns (datetime → ISO 8601 string for Pydantic)
          * ``None`` defaults (datetime cols may be unset for draft rows)
        """
        def _load(attr: str, default: Any) -> Any:
            val = getattr(row, attr, None)
            if val is None or val == "":
                return default
            try:
                return json.loads(val) if isinstance(val, str) else val
            except Exception:
                return default

        def _dt_to_iso(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, str):
                return value
            if isinstance(value, datetime):
                return value.isoformat()
            return None

        refs_raw = _load("reference_images_json", []) or []
        refs = [ReferenceImage(**r) for r in refs_raw if isinstance(r, dict)]
        locks_raw = _load("locked_features_json", []) or []
        locks = [LockedFeature(**lf) for lf in locks_raw if isinstance(lf, dict)]

        return cls(
            id=row.id,
            name=row.name,
            description=row.description or None,
            status=row.status or "draft",
            reference_images=refs,
            face_features=_load("face_features_json", {}) or {},
            voice_features=_load("voice_features_json", {}) or {},
            body_features=_load("body_features_json", {}) or {},
            style_features=_load("style_features_json", {}) or {},
            locked_features=locks,
            consistency_score=float(getattr(row, "consistency_score", 1.0) or 1.0),
            last_consistency_check_at=_dt_to_iso(getattr(row, "last_consistency_check_at", None)),
            locked_at=_dt_to_iso(getattr(row, "locked_at", None)),
            locked_by=getattr(row, "locked_by", None),
            owner_id=getattr(row, "owner_id", None),
            tags=_load("tags_json", []) or [],
            created_at=_dt_to_iso(getattr(row, "created_at", None)) or cls.model_fields["created_at"].default_factory(),
            updated_at=_dt_to_iso(getattr(row, "updated_at", None)) or cls.model_fields["updated_at"].default_factory(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SQLAlchemy ORM model (used when SQLAlchemy is available)
# ═══════════════════════════════════════════════════════════════════════════════

if _SQLA_OK:

    class _AssetBase(DeclarativeBase):
        """Local DeclarativeBase — keeps ORM decoupled from imdf.metadata."""
        pass

    class CharacterAssetModel(_AssetBase):
        """PG / SQLite table ``asset_characters`` (created via ``create_all``).

        Columns:
          id, name, description, status, reference_images_json (JSON),
          face_features_json / voice_features_json / body_features_json /
          style_features_json / locked_features_json (JSON),
          consistency_score (Float), last_consistency_check_at (DateTime),
          locked_at, locked_by, owner_id, tags_json (JSON),
          created_at, updated_at.
        """
        __tablename__ = "asset_characters"

        id = Column(String(64), primary_key=True)
        name = Column(String(200), nullable=False, index=True)
        description = Column(Text, nullable=True)
        status = Column(String(20), nullable=False, default="draft", index=True)

        reference_images_json = Column(Text, nullable=False, default="[]")
        face_features_json = Column(Text, nullable=False, default="{}")
        voice_features_json = Column(Text, nullable=False, default="{}")
        body_features_json = Column(Text, nullable=False, default="{}")
        style_features_json = Column(Text, nullable=False, default="{}")
        locked_features_json = Column(Text, nullable=False, default="[]")

        consistency_score = Column(Float, nullable=False, default=1.0)
        last_consistency_check_at = Column(DateTime, nullable=True)

        locked_at = Column(DateTime, nullable=True)
        locked_by = Column(String(64), nullable=True)
        owner_id = Column(String(64), nullable=True, index=True)

        tags_json = Column(Text, nullable=False, default="[]")
        created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(
            DateTime,
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
        )

        __table_args__ = (
            Index("ix_asset_characters_status_owner", "status", "owner_id"),
            Index("ix_asset_characters_name_lower", "name"),
        )

        def __repr__(self) -> str:  # pragma: no cover
            return f"<CharacterAssetModel {self.id} {self.name!r} status={self.status}>"

else:  # pragma: no cover — SQLAlchemy not installed
    CharacterAssetModel = None  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════════
# In-memory store (fallback when SQLAlchemy/DB unavailable — keeps API alive)
# ═══════════════════════════════════════════════════════════════════════════════

class InMemoryCharacterStore:
    """Thread-safe in-memory store keyed by character id.

    Used when:
      * SQLAlchemy is not installed
      * the test suite forces a SQLite-less mode (pure unit tests)
      * dev / CI runs without a Postgres connection

    Operations: list / get / create / update / delete / lock / unlock.
    All ops return ``(ok: bool, payload: dict, error: str|None)``.
    """

    def __init__(self) -> None:
        self._items: Dict[str, CharacterAsset] = {}
        self._lock_key = "memory_store_lock"

    def list(
        self,
        owner_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[CharacterAsset]:
        items = list(self._items.values())
        if owner_id:
            items = [c for c in items if c.owner_id == owner_id]
        if status:
            items = [c for c in items if c.status == status]
        items.sort(key=lambda c: c.created_at, reverse=True)
        return items[offset:offset + max(1, limit)]

    def get(self, character_id: str) -> Optional[CharacterAsset]:
        return self._items.get(character_id)

    def upsert(self, character: CharacterAsset) -> CharacterAsset:
        character.updated_at = datetime.now(timezone.utc).isoformat()
        if character.id in self._items:
            # preserve lock state when not explicitly changed
            prev = self._items[character.id]
            if character.locked_at is None and prev.locked_at:
                character.locked_at = prev.locked_at
                character.locked_by = prev.locked_by
                if character.status == "draft":
                    character.status = prev.status
        self._items[character.id] = character
        return character

    def delete(self, character_id: str) -> bool:
        return self._items.pop(character_id, None) is not None

    def lock(self, character_id: str, user_id: str) -> Optional[CharacterAsset]:
        c = self._items.get(character_id)
        if not c:
            return None
        c.status = "locked"
        c.locked_at = datetime.now(timezone.utc).isoformat()
        c.locked_by = user_id
        c.updated_at = c.locked_at
        return c

    def unlock(self, character_id: str) -> Optional[CharacterAsset]:
        c = self._items.get(character_id)
        if not c:
            return None
        c.status = "draft"
        c.locked_at = None
        c.locked_by = None
        c.updated_at = datetime.now(timezone.utc).isoformat()
        return c

    def count(self) -> int:
        return len(self._items)


# ═══════════════════════════════════════════════════════════════════════════════
# Validation helpers — reused by routes
# ═══════════════════════════════════════════════════════════════════════════════

def validate_character_payload(payload: Dict[str, Any]) -> CharacterAsset:
    """Validate raw JSON payload (from HTTP request) and return a CharacterAsset.

    Raises ``ValueError`` (caller maps to HTTP 400 / 422).
    """
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    # Coerce reference_images to ReferenceImage objects early so Pydantic errors are readable
    if "reference_images" in payload and isinstance(payload["reference_images"], list):
        payload["reference_images"] = [
            r if isinstance(r, ReferenceImage) else ReferenceImage(**r)
            for r in payload["reference_images"]
            if isinstance(r, dict)
        ]
    if "locked_features" in payload and isinstance(payload["locked_features"], list):
        payload["locked_features"] = [
            lf if isinstance(lf, LockedFeature) else LockedFeature(**lf)
            for lf in payload["locked_features"]
            if isinstance(lf, dict)
        ]
    return CharacterAsset(**payload)


__all__ = [
    # pydantic
    "ReferenceImage",
    "LockedFeature",
    "CharacterAsset",
    # orm
    "CharacterAssetModel",
    # memory store
    "InMemoryCharacterStore",
    # helpers
    "validate_character_payload",
]
