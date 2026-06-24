"""P4-5-W1 — Image generator tests (3 tests, mock mode).

Coverage:
  1. ImageGenerator.list_models returns all 5 image models
  2. ImageGenerator.generate (mock) returns n images + consistency score
  3. ImageGenerator.generate_batch produces one response per request
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def test_list_models_returns_5():
    """Image catalog lists exactly the 5 P4-5 models."""
    from services.asset_service.generators.image import IMAGE_MODELS, ImageGenerator

    assert set(IMAGE_MODELS.keys()) == {"sdxl", "dall-e-3", "midjourney", "imagen-3", "seedream-4"}
    gen = ImageGenerator()
    catalog = gen.list_models()
    assert len(catalog) == 5
    for entry in catalog:
        assert "name" in entry
        assert "provider_id" in entry
        assert "protocol" in entry
        assert "model" in entry
        assert "label" in entry


def test_generate_mock_returns_images():
    """ImageGenerator.generate (mock) returns n images with consistency score."""
    from services.asset_service.generators.image import ImageGenerateRequest, ImageGenerator

    gen = ImageGenerator()
    req = ImageGenerateRequest(
        prompt="A young female warrior, anime style, front view",
        reference_images=["https://x.com/ref1.png", "https://x.com/ref2.png"],
        style_preset="cinematic",
        model="dall-e-3",
        width=512,
        height=768,
        n=3,
        mock=True,
    )
    resp = gen.generate(req)
    assert len(resp.images) == 3
    for img in resp.images:
        assert img.url
        assert img.width == 512
        assert img.height == 768
        assert 0.0 <= img.consistency_score <= 1.0
        assert img.consistency_recommendation in {"accept", "warn", "reject"}
    # aggregate consistency should equal mean of per-image
    agg = sum(i.consistency_score for i in resp.images) / len(resp.images)
    assert abs(resp.consistency_score - round(agg, 4)) < 1e-3
    assert resp.model == "dall-e-3"
    assert resp.mock is True
    assert resp.elapsed_ms >= 0


def test_generate_batch_and_character_consistency():
    """ImageGenerator.generate_batch produces one response per request, with character ref."""
    from services.asset_service.characters.models import (
        CharacterAsset,
        LockedFeature,
        ReferenceImage,
    )
    from services.asset_service.characters.storage import (
        init_storage,
        upsert_character,
    )
    from services.asset_service.generators.image import (
        ImageGenerateRequest,
        ImageGenerator,
    )

    # Initialize storage (in-memory fallback OK)
    init_storage()
    character = CharacterAsset(
        name="苏晚晴",
        reference_images=[
            ReferenceImage(angle="front", url="https://x.com/c1f.png"),
            ReferenceImage(angle="side", url="https://x.com/c1s.png"),
        ],
        face_features={"shape": "oval", "eye_color": "black", "skin_tone": "fair"},
        style_features={
            "art_style": "anime",
            "hair": {"color": "black", "length": "long"},
            "outfit": {"top": "school uniform", "main_color": "navy"},
        },
        locked_features=[LockedFeature(category="face", name="oval face", weight=2.0)],
    )
    upsert_character(character)

    gen = ImageGenerator()
    reqs = [
        ImageGenerateRequest(
            prompt="character standing in classroom",
            character_id=character.id,
            model="sdxl",
            mock=True,
        ),
        ImageGenerateRequest(
            prompt="character walking in city",
            character_id=character.id,
            model="midjourney",
            mock=True,
        ),
        ImageGenerateRequest(
            prompt="close-up portrait",
            character_id=character.id,
            model="dall-e-3",
            mock=True,
            n=2,
        ),
    ]
    results = gen.generate_batch(reqs)
    assert len(results) == 3
    # Each must reference the character and run consistency check
    for r in results:
        assert r.character_id == character.id
        assert 0.0 <= r.consistency_score <= 1.0
        assert len(r.images) >= 1
    # The third request had n=2
    assert len(results[2].images) == 2
