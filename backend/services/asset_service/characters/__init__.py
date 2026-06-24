"""P4-5-W1: characters package — re-exports for convenient ``from characters import ...``.

Public surface (used by routes.py):
  * ``CharacterAsset``, ``ReferenceImage``, ``LockedFeature`` — wire schemas
  * ``CharacterAssetModel`` — SQLAlchemy ORM
  * ``InMemoryCharacterStore`` — fallback persistence
  * ``CharacterConsistencyChecker``, ``ConsistencyResult`` — Bernini-style checker
  * ``router`` — FastAPI router with all /api/v1/assets/characters/* routes
"""
from __future__ import annotations

from .models import (
    CharacterAsset,
    CharacterAssetModel,
    InMemoryCharacterStore,
    LockedFeature,
    ReferenceImage,
    validate_character_payload,
)
from .consistency import (
    ACCEPT_THRESHOLD,
    CharacterConsistencyChecker,
    ConsistencyResult,
    WARN_THRESHOLD,
    aggregate,
    recommend,
    score_clip_similarity,
    score_face_match,
    score_hair_match,
    score_outfit_match,
)
from .storage import (
    count_characters,
    delete_character,
    get_character,
    get_store,
    init_storage,
    list_characters,
    lock_character,
    storage_backend,
    unlock_character,
    update_consistency_score,
    upsert_character,
)
from .routes import router

__all__ = [
    # models
    "CharacterAsset",
    "CharacterAssetModel",
    "ReferenceImage",
    "LockedFeature",
    "InMemoryCharacterStore",
    "validate_character_payload",
    # consistency
    "CharacterConsistencyChecker",
    "ConsistencyResult",
    "score_clip_similarity",
    "score_face_match",
    "score_hair_match",
    "score_outfit_match",
    "aggregate",
    "recommend",
    "WARN_THRESHOLD",
    "ACCEPT_THRESHOLD",
    # storage
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
    # router
    "router",
]
