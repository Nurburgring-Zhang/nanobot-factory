"""P4-5-W1 — Character asset model tests (4 tests).

Coverage:
  1. CharacterAsset schema validation — name, features, references
  2. ReferenceImage + LockedFeature sub-schemas — angle/category whitelist
  3. CharacterAssetModel SQLAlchemy ORM — table creation + round-trip
  4. InMemoryCharacterStore CRUD + lock/unlock semantics
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ── path setup: backend/ on sys.path so services.* resolves ──
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def test_character_asset_schema_validation():
    """CharacterAsset accepts a minimal valid payload and rejects bad ones."""
    from services.asset_service.characters.models import (
        CharacterAsset,
        LockedFeature,
        ReferenceImage,
    )

    # Happy path — minimal payload
    c = CharacterAsset(
        name="苏晚晴",
        reference_images=[
            ReferenceImage(angle="front", url="https://cdn.example.com/c1_front.png"),
            ReferenceImage(angle="side", url="https://cdn.example.com/c1_side.png"),
            ReferenceImage(angle="3-quarter", url="https://cdn.example.com/c1_3q.png"),
        ],
        face_features={"shape": "oval", "eye_color": "black", "skin_tone": "fair"},
        voice_features={"language": "zh", "pitch": "medium"},
        style_features={
            "art_style": "anime",
            "hair": {"color": "black", "length": "long", "style": "ponytail"},
            "outfit": {"top": "school uniform", "main_color": "navy"},
        },
        locked_features=[
            LockedFeature(category="face", name="oval face", weight=2.0),
            LockedFeature(category="hair", name="black long ponytail", weight=2.0),
        ],
    )
    assert c.id.startswith("char_")
    assert c.status == "draft"
    assert len(c.reference_images) == 3
    assert c.locked_features[0].weight == 2.0
    assert c.face_features["eye_color"] == "black"

    # Reject empty / too-long / invalid-chars name
    with pytest.raises(Exception):
        CharacterAsset(name="")
    with pytest.raises(Exception):
        CharacterAsset(name="bad/name")
    with pytest.raises(Exception):
        CharacterAsset(name="x" * 200)

    # Reject invalid status
    with pytest.raises(Exception):
        CharacterAsset(name="test", status="invalid_status")

    # Round-trip via dict
    d = c.to_orm_dict()
    assert d["name"] == "苏晚晴"
    assert isinstance(d["reference_images_json"], str)  # JSON-serialized
    assert "苏晚晴" in d["reference_images_json"] or "front" in d["reference_images_json"]


def test_reference_and_locked_sub_schemas():
    """ReferenceImage and LockedFeature enforce their whitelists."""
    from services.asset_service.characters.models import LockedFeature, ReferenceImage

    # ReferenceImage angle whitelist
    with pytest.raises(Exception):
        ReferenceImage(angle="invalid", url="https://x.com/a.png")
    with pytest.raises(Exception):
        ReferenceImage(angle="front", url="not-a-url")
    # OK with expression-X form
    ri = ReferenceImage(angle="expression-smile", url="/local/img.png")
    assert ri.angle == "expression-smile"
    # OK with asset://
    ri2 = ReferenceImage(angle="back", url="asset://characters/x/back.png")
    assert ri2.url.startswith("asset://")

    # LockedFeature category whitelist + weight bounds
    with pytest.raises(Exception):
        LockedFeature(category="unknown", name="x")
    lf = LockedFeature(category="face", name="blue eyes", weight=1.5)
    assert lf.weight == 1.5
    with pytest.raises(Exception):
        LockedFeature(category="hair", name="x", weight=5.0)  # > 2.0


def test_character_orm_create_and_roundtrip(tmp_path):
    """SQLAlchemy ORM: create_all + insert + read back via from_orm_row."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from services.asset_service.characters.models import (
        CharacterAsset,
        CharacterAssetModel,
    )

    db_path = tmp_path / "test_characters.db"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    CharacterAssetModel.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Insert
    c = CharacterAsset(
        name="Captain Vega",
        description="Sci-fi female captain",
        reference_images=[
            {"angle": "front", "url": "https://cdn.example.com/vega_front.png"},
            {"angle": "side", "url": "https://cdn.example.com/vega_side.png"},
        ],
        face_features={"eye_color": "green", "skin_tone": "tan"},
        style_features={
            "art_style": "sci-fi",
            "outfit": {"main_color": "silver", "fabric": "metallic"},
        },
        locked_features=[{"category": "outfit", "name": "silver metallic suit", "weight": 2.0}],
        tags=["sci-fi", "captain"],
    )
    Session = SessionLocal()
    try:
        row = CharacterAssetModel(**c.to_orm_dict())
        row.id = c.id  # ensure PK is set
        Session.add(row)
        Session.commit()
        Session.refresh(row)

        # Read back
        fetched = Session.query(CharacterAssetModel).filter(CharacterAssetModel.id == c.id).first()
        assert fetched is not None
        assert fetched.name == "Captain Vega"
        assert fetched.status == "draft"
        # Round-trip via Pydantic
        hydrated = CharacterAsset.from_orm_row(fetched)
        assert hydrated.id == c.id
        assert len(hydrated.reference_images) == 2
        assert hydrated.reference_images[0].angle == "front"
        assert hydrated.style_features["outfit"]["main_color"] == "silver"
        assert len(hydrated.locked_features) == 1
        assert hydrated.locked_features[0].name == "silver metallic suit"
        assert hydrated.tags == ["sci-fi", "captain"]
    finally:
        Session.close()
        engine.dispose()


def test_inmemory_store_crud_and_lock():
    """InMemoryCharacterStore: create / get / list / lock / unlock / delete."""
    from services.asset_service.characters.models import (
        CharacterAsset,
        InMemoryCharacterStore,
    )

    store = InMemoryCharacterStore()
    assert store.count() == 0

    # Create
    c1 = CharacterAsset(name="角色甲", owner_id="user_alice")
    c2 = CharacterAsset(name="角色乙", owner_id="user_bob", status="locked")
    store.upsert(c1)
    store.upsert(c2)

    assert store.count() == 2

    # Get
    fetched = store.get(c1.id)
    assert fetched is not None
    assert fetched.name == "角色甲"

    # List
    items = store.list(owner_id="user_alice")
    assert len(items) == 1
    assert items[0].name == "角色甲"

    items_by_status = store.list(status="locked")
    assert len(items_by_status) == 1
    assert items_by_status[0].name == "角色乙"

    # Lock
    locked = store.lock(c1.id, "user_alice")
    assert locked is not None
    assert locked.status == "locked"
    assert locked.locked_by == "user_alice"
    assert locked.locked_at is not None

    # Re-lock should be idempotent
    locked2 = store.lock(c1.id, "user_other")
    assert locked2.locked_by == "user_other"

    # Unlock
    unlocked = store.unlock(c1.id)
    assert unlocked.status == "draft"
    assert unlocked.locked_at is None

    # Delete
    assert store.delete(c2.id) is True
    assert store.delete("nonexistent_id") is False
    assert store.count() == 1

    # Lock non-existent returns None
    assert store.lock("does-not-exist", "x") is None
