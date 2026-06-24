"""P4-5-W1: character routes — REST surface for the character asset double-layer.

Endpoints (all prefixed ``/api/v1/assets/characters``):

  GET    /                            — list characters (?owner_id= &status= &limit= &offset=)
  POST   /                            — create character
  GET    /{character_id}              — get character
  PUT    /{character_id}              — update character (full replace)
  DELETE /{character_id}              — delete character
  POST   /{character_id}/lock         — lock character (status → locked)
  POST   /{character_id}/unlock       — unlock character (status → draft)
  POST   /{character_id}/consistency_check
                                      — run Bernini-style consistency check
  POST   /{character_id}/references   — add a reference image (front/side/3-quarter)
  DELETE /{character_id}/references   — remove a reference image (by angle or url)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .consistency import CharacterConsistencyChecker
from .models import (
    CharacterAsset,
    LockedFeature,
    ReferenceImage,
    validate_character_payload,
)
from .storage import (
    count_characters,
    delete_character,
    get_character,
    init_storage,
    list_characters as _list_characters,
    lock_character,
    storage_backend,
    unlock_character,
    update_consistency_score,
    upsert_character,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assets/characters", tags=["character-assets"])


# ─── Request / Response shapes ───────────────────────────────────────────────

class LockRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, description="用户 id, 写入 locked_by")


class ConsistencyCheckRequest(BaseModel):
    generated_meta: Optional[Dict[str, Any]] = Field(
        default=None,
        description="生成物的特征 (face_features / voice_features / style_features 等)",
    )


class ReferenceAddRequest(BaseModel):
    angle: str = Field(..., description="front / side / 3-quarter / back / expression-X")
    url: str = Field(..., description="参考图 URL")


class ReferenceRemoveRequest(BaseModel):
    angle: Optional[str] = None
    url: Optional[str] = None


# ─── Startup hook ────────────────────────────────────────────────────────────

@router.on_event("startup")
async def _startup() -> None:  # pragma: no cover
    init_storage()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _character_to_dict(c: CharacterAsset) -> Dict[str, Any]:
    return c.model_dump()


# ─── List ────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[Dict[str, Any]])
async def list_characters(
    owner_id: Optional[str] = Query(default=None, max_length=64),
    status: Optional[str] = Query(default=None, max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> List[Dict[str, Any]]:
    init_storage()
    items = _list_characters(owner_id=owner_id, status=status, limit=limit, offset=offset)
    return [_character_to_dict(c) for c in items] 


# ─── Create ─────────────────────────────────────────────────────────────────

@router.post("", response_model=Dict[str, Any])
async def create_character(payload: Dict[str, Any]) -> Dict[str, Any]:
    init_storage()
    try:
        character = validate_character_payload(payload)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"invalid character payload: {e!s}")
    stored = upsert_character(character)
    return _character_to_dict(stored)


# ─── Get ─────────────────────────────────────────────────────────────────────

@router.get("/{character_id}", response_model=Dict[str, Any])
async def get_one_character(character_id: str) -> Dict[str, Any]:
    init_storage()
    c = get_character(character_id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"character not found: {character_id}")
    return _character_to_dict(c)


# ─── Update (full replace) ───────────────────────────────────────────────────

@router.put("/{character_id}", response_model=Dict[str, Any])
async def update_character(character_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    init_storage()
    existing = get_character(character_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"character not found: {character_id}")
    payload["id"] = character_id
    try:
        character = validate_character_payload(payload)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"invalid payload: {e!s}")
    # Preserve locked state when not explicitly changed
    if character.status != "locked":
        if existing.locked_at:
            character.status = existing.status
            character.locked_at = existing.locked_at
            character.locked_by = existing.locked_by
    stored = upsert_character(character)
    return _character_to_dict(stored)


# ─── Delete ──────────────────────────────────────────────────────────────────

@router.delete("/{character_id}", response_model=Dict[str, Any])
async def delete_one_character(character_id: str) -> Dict[str, Any]:
    init_storage()
    ok = delete_character(character_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"character not found: {character_id}")
    return {"deleted": True, "id": character_id}


# ─── Lock / Unlock ───────────────────────────────────────────────────────────

@router.post("/{character_id}/lock", response_model=Dict[str, Any])
async def lock_one(character_id: str, body: Optional[LockRequest] = None) -> Dict[str, Any]:
    init_storage()
    user_id = (body.user_id if body else None) or "system"
    c = lock_character(character_id, user_id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"character not found: {character_id}")
    return _character_to_dict(c)


@router.post("/{character_id}/unlock", response_model=Dict[str, Any])
async def unlock_one(character_id: str) -> Dict[str, Any]:
    init_storage()
    c = unlock_character(character_id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"character not found: {character_id}")
    return _character_to_dict(c)


# ─── Consistency check ───────────────────────────────────────────────────────

@router.post("/{character_id}/consistency_check", response_model=Dict[str, Any])
async def consistency_check(
    character_id: str,
    body: Optional[ConsistencyCheckRequest] = None,
) -> Dict[str, Any]:
    init_storage()
    c = get_character(character_id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"character not found: {character_id}")
    checker = CharacterConsistencyChecker()
    meta = body.generated_meta if body else None
    result = checker.check(c, meta)
    # Persist updated score (denormalized for sort-by-consistency queries)
    update_consistency_score(character_id, result.score)
    return result.to_dict()


# ─── Reference image management ──────────────────────────────────────────────

@router.post("/{character_id}/references", response_model=Dict[str, Any])
async def add_reference(character_id: str, body: ReferenceAddRequest) -> Dict[str, Any]:
    init_storage()
    c = get_character(character_id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"character not found: {character_id}")
    try:
        new_ref = ReferenceImage(angle=body.angle, url=body.url)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    refs = list(c.reference_images)
    # Replace if same angle already present
    refs = [r for r in refs if r.angle != new_ref.angle]
    refs.append(new_ref)
    if len(refs) > 8:
        refs = refs[:8]
    c.reference_images = refs
    upsert_character(c)
    return _character_to_dict(c)


@router.delete("/{character_id}/references", response_model=Dict[str, Any])
async def remove_reference(character_id: str, body: ReferenceRemoveRequest) -> Dict[str, Any]:
    init_storage()
    c = get_character(character_id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"character not found: {character_id}")
    refs = list(c.reference_images)
    if body.angle:
        refs = [r for r in refs if r.angle != body.angle]
    if body.url:
        refs = [r for r in refs if r.url != body.url]
    c.reference_images = refs
    upsert_character(c)
    return _character_to_dict(c)


# ─── Stats / health ──────────────────────────────────────────────────────────

@router.get("/_meta/stats", response_model=Dict[str, Any])
async def stats() -> Dict[str, Any]:
    init_storage()
    return {
        "backend": storage_backend(),
        "total_characters": count_characters(),
    }


__all__ = ["router"]
