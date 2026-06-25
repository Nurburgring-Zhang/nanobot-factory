"""P4-6-W1 tests for effect engine.

3 tests covering: 16 effects + per-category split + validation.
"""
from __future__ import annotations

import pytest

from services.workflow_service.editor.effect import (
    EFFECT_CATALOG, Effect, EffectEngine, list_effects,
)


def test_effect_catalog_16_types():
    """16 effects split 8 visual + 4 aesthetic + 4 utility."""
    assert len(EFFECT_CATALOG) == 16
    by_cat: dict = {}
    for k, v in EFFECT_CATALOG.items():
        by_cat.setdefault(v["category"], []).append(k)
    assert len(by_cat["visual"]) == 8
    assert len(by_cat["aesthetic"]) == 4
    assert len(by_cat["utility"]) == 4
    items = list_effects()
    assert len(items) == 16


def test_build_filter_for_all_16_effects():
    """Each effect yields a non-empty FFmpeg filter expression."""
    eng = EffectEngine()
    for type_id, spec in EFFECT_CATALOG.items():
        params = dict(spec["default"])
        eff = Effect(type=type_id, clip_id="c1", params=params)
        built = eng.build_filter(eff)
        assert built["type"] == type_id
        assert built["category"] == spec["category"]
        assert built["ffmpeg_filter"], f"empty filter for {type_id}"
        # Defaults should be filled
        assert built["params"]


def test_effect_validation_rejects_out_of_range():
    """Out-of-range intensity values are rejected."""
    eng = EffectEngine()
    # blur with intensity 100 is out of range
    eff = Effect(type="blur", clip_id="c1",
                 params={"intensity": 100.0})
    with pytest.raises(ValueError):
        eng.build_filter(eff)
    # vignette intensity > 1 rejected
    eff = Effect(type="vignette", clip_id="c1",
                 params={"intensity": 1.5})
    with pytest.raises(ValueError):
        eng.build_filter(eff)
    # unknown effect type rejected
    eff = Effect(type="unknown_effect", clip_id="c1", params={})
    with pytest.raises(ValueError):
        eng.build_filter(eff)
    # end <= start rejected
    eff = Effect(type="blur", clip_id="c1",
                 params={"intensity": 5.0}, start=5.0, end=3.0)
    with pytest.raises(ValueError):
        eng.build_filter(eff)
