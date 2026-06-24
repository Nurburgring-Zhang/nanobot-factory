"""P4-5-W1: Character storage — SQLAlchemy-first with in-memory fallback.

Persistence order (first wins):
  1. SQLAlchemy engine from ``common.db`` if SQLAlchemy is installed AND
     ``init_db()`` succeeds (Postgres in prod / SQLite in tests).
  2. ``InMemoryCharacterStore`` — keeps API alive when DB is unavailable.

Public API (used by routes):
  * ``list_characters(owner_id, status, limit, offset)``
  * ``get_character(character_id)``
  * ``upsert_character(character)`` — insert or update by id
  * ``delete_character(character_id)``
  * ``lock_character(character_id, user_id)``
  * ``unlock_character(character_id)``
  * ``count_characters()`` — for stats
  * ``update_consistency_score(character_id, score)`` — denormalized
  * ``storage_backend()`` → "sqlalchemy" | "memory" (for /healthz)

Design notes:
  * The store is module-level singleton (``_store`` + ``_store_lock``) so
    multiple routes share state without a global FastAPI dependency.
  * ``init_storage()`` is idempotent and safe to call from FastAPI
    ``lifespan``. It tries to bootstrap the SQLAlchemy engine + create tables.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    CharacterAsset,
    CharacterAssetModel,
    InMemoryCharacterStore,
)

logger = logging.getLogger(__name__)

# ─── Module-level state ──────────────────────────────────────────────────────
_store: Optional["_CharacterStore"] = None
_store_lock = threading.Lock()


class _CharacterStore:
    """Composite store: SQLAlchemy + in-memory mirror."""

    def __init__(self) -> None:
        self.backend: str = "memory"
        self._memory = InMemoryCharacterStore()
        self._session_factory = None
        self._CharacterModel = CharacterAssetModel

    def init(self) -> None:
        """Try to bind a SQLAlchemy engine. Fall back to memory."""
        if CharacterAssetModel is None:
            self.backend = "memory"
            return
        try:
            # Use common.db for engine + session — same engine as the rest
            # of the asset_service, ensuring character writes participate in
            # the same transaction boundary as the route handler.
            from common.db import get_session_factory  # type: ignore

            factory = get_session_factory()
            try:
                from common.db import get_engine  # type: ignore
                engine = get_engine()
                CharacterAssetModel.metadata.create_all(bind=engine)
            except Exception as e:  # pragma: no cover
                logger.warning("character store: create_all failed (%s); using memory backend", e)
                self.backend = "memory"
                return
            self._session_factory = factory
            self.backend = "sqlalchemy"
            logger.info("character store backend=sqlalchemy")
        except Exception as e:  # pragma: no cover
            logger.warning("character store: SQLAlchemy unavailable (%s); using memory", e)
            self.backend = "memory"

    # ── CRUD ──────────────────────────────────────────────────────────────
    def list(
        self,
        owner_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[CharacterAsset]:
        if self.backend == "sqlalchemy" and self._session_factory is not None:
            try:
                with self._session_factory() as db:
                    q = db.query(CharacterAssetModel)
                    if owner_id:
                        q = q.filter(CharacterAssetModel.owner_id == owner_id)
                    if status:
                        q = q.filter(CharacterAssetModel.status == status)
                    rows = q.order_by(CharacterAssetModel.created_at.desc()).offset(offset).limit(limit).all()
                    return [CharacterAsset.from_orm_row(r) for r in rows]
            except Exception as e:  # pragma: no cover
                logger.warning("character list (sqlalchemy) failed: %s", e)
        return self._memory.list(owner_id=owner_id, status=status, limit=limit, offset=offset)

    def get(self, character_id: str) -> Optional[CharacterAsset]:
        if self.backend == "sqlalchemy" and self._session_factory is not None:
            try:
                with self._session_factory() as db:
                    row = db.query(CharacterAssetModel).filter(CharacterAssetModel.id == character_id).first()
                    if row is not None:
                        return CharacterAsset.from_orm_row(row)
            except Exception as e:  # pragma: no cover
                logger.warning("character get (sqlalchemy) failed: %s", e)
        return self._memory.get(character_id)

    def upsert(self, character: CharacterAsset) -> CharacterAsset:
        if self.backend == "sqlalchemy" and self._session_factory is not None:
            try:
                with self._session_factory() as db:
                    row = db.query(CharacterAssetModel).filter(CharacterAssetModel.id == character.id).first()
                    payload = character.to_orm_dict()
                    payload["updated_at"] = datetime.now(timezone.utc)
                    if row is None:
                        row = CharacterAssetModel(**payload)
                        db.add(row)
                    else:
                        for k, v in payload.items():
                            setattr(row, k, v)
                    db.commit()
                    db.refresh(row)
                    return CharacterAsset.from_orm_row(row)
            except Exception as e:  # pragma: no cover
                logger.warning("character upsert (sqlalchemy) failed: %s", e)
        return self._memory.upsert(character)

    def delete(self, character_id: str) -> bool:
        if self.backend == "sqlalchemy" and self._session_factory is not None:
            try:
                with self._session_factory() as db:
                    row = db.query(CharacterAssetModel).filter(CharacterAssetModel.id == character_id).first()
                    if row is None:
                        return False
                    db.delete(row)
                    db.commit()
                    return True
            except Exception as e:  # pragma: no cover
                logger.warning("character delete (sqlalchemy) failed: %s", e)
        return self._memory.delete(character_id)

    def lock(self, character_id: str, user_id: str) -> Optional[CharacterAsset]:
        if self.backend == "sqlalchemy" and self._session_factory is not None:
            try:
                with self._session_factory() as db:
                    row = db.query(CharacterAssetModel).filter(CharacterAssetModel.id == character_id).first()
                    if row is None:
                        return None
                    row.status = "locked"
                    row.locked_at = datetime.now(timezone.utc)
                    row.locked_by = user_id
                    row.updated_at = row.locked_at
                    db.commit()
                    db.refresh(row)
                    return CharacterAsset.from_orm_row(row)
            except Exception as e:  # pragma: no cover
                logger.warning("character lock (sqlalchemy) failed: %s", e)
        return self._memory.lock(character_id, user_id)

    def unlock(self, character_id: str) -> Optional[CharacterAsset]:
        if self.backend == "sqlalchemy" and self._session_factory is not None:
            try:
                with self._session_factory() as db:
                    row = db.query(CharacterAssetModel).filter(CharacterAssetModel.id == character_id).first()
                    if row is None:
                        return None
                    row.status = "draft"
                    row.locked_at = None
                    row.locked_by = None
                    row.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    db.refresh(row)
                    return CharacterAsset.from_orm_row(row)
            except Exception as e:  # pragma: no cover
                logger.warning("character unlock (sqlalchemy) failed: %s", e)
        return self._memory.unlock(character_id)

    def update_consistency_score(self, character_id: str, score: float) -> bool:
        if self.backend == "sqlalchemy" and self._session_factory is not None:
            try:
                with self._session_factory() as db:
                    row = db.query(CharacterAssetModel).filter(CharacterAssetModel.id == character_id).first()
                    if row is None:
                        return False
                    row.consistency_score = float(score)
                    row.last_consistency_check_at = datetime.now(timezone.utc)
                    row.updated_at = row.last_consistency_check_at
                    db.commit()
                    return True
            except Exception as e:  # pragma: no cover
                logger.warning("character update_consistency_score failed: %s", e)
        c = self._memory.get(character_id)
        if not c:
            return False
        c.consistency_score = float(score)
        c.last_consistency_check_at = datetime.now(timezone.utc).isoformat()
        c.updated_at = c.last_consistency_check_at
        return True

    def count(self) -> int:
        if self.backend == "sqlalchemy" and self._session_factory is not None:
            try:
                with self._session_factory() as db:
                    return db.query(CharacterAssetModel).count()
            except Exception:  # pragma: no cover
                pass
        return self._memory.count()


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level facade
# ═══════════════════════════════════════════════════════════════════════════════

def get_store() -> _CharacterStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = _CharacterStore()
                _store.init()
    return _store


def init_storage() -> None:
    """Idempotent — call from FastAPI lifespan."""
    get_store()


def storage_backend() -> str:
    return get_store().backend


def list_characters(
    owner_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[CharacterAsset]:
    return get_store().list(owner_id=owner_id, status=status, limit=limit, offset=offset)


def get_character(character_id: str) -> Optional[CharacterAsset]:
    return get_store().get(character_id)


def upsert_character(character: CharacterAsset) -> CharacterAsset:
    return get_store().upsert(character)


def delete_character(character_id: str) -> bool:
    return get_store().delete(character_id)


def lock_character(character_id: str, user_id: str) -> Optional[CharacterAsset]:
    return get_store().lock(character_id, user_id)


def unlock_character(character_id: str) -> Optional[CharacterAsset]:
    return get_store().unlock(character_id)


def update_consistency_score(character_id: str, score: float) -> bool:
    return get_store().update_consistency_score(character_id, score)


def count_characters() -> int:
    return get_store().count()


__all__ = [
    "init_storage",
    "storage_backend",
    "list_characters",
    "get_character",
    "upsert_character",
    "delete_character",
    "lock_character",
    "unlock_character",
    "update_consistency_score",
    "count_characters",
    "get_store",
]
