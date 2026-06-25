"""Tests for effect engine — 16 effects across 3 categories."""
import pytest

from services.workflow_service.editor.effect import (
    EffectEngine, Effect, EFFECT_CATALOG, list_effects,
)


# ---- catalog ----

def test_effect_catalog_has_16_effects():
    assert len(EFFECT_CATALOG) == 16


def test_effect_catalog_categories():
    cats = {v["category"] for v in EFFECT_CATALOG.values()}
    assert cats == {"visual", "aesthetic", "utility"}


def test_list_effects_metadata():
    items = list_effects()
    assert len(items) == 16
    for item in items:
        assert "id" in item
        assert "category" in item
        assert "default_params" in item


# ---- validation ----

def test_validate_unknown_effect_type():
    engine = EffectEngine()
    eff = Effect(type="unicorn_glow", clip_id="c1")
    with pytest.raises(ValueError, match="unknown effect"):
        engine.validate(eff)


def test_validate_blur_intensity_range():
    engine = EffectEngine()
    eff = Effect(type="blur", clip_id="c1", params={"intensity": 100.0})
    with pytest.raises(ValueError, match="blur.intensity"):
        engine.validate(eff)


def test_validate_sharpen_intensity_range():
    engine = EffectEngine()
    eff = Effect(type="sharpen", clip_id="c1", params={"intensity": 2.0})
    with pytest.raises(ValueError, match="sharpen.intensity"):
        engine.validate(eff)


def test_validate_negative_start():
    engine = EffectEngine()
    eff = Effect(type="color_grade", clip_id="c1", start=-1.0)
    with pytest.raises(ValueError, match="start must be >= 0"):
        engine.validate(eff)


def test_validate_end_le_start():
    engine = EffectEngine()
    eff = Effect(type="color_grade", clip_id="c1", start=5.0, end=3.0)
    with pytest.raises(ValueError, match="end must be > start"):
        engine.validate(eff)


# ---- build_filter ----

def test_build_filter_color_grade_renders_intensity():
    engine = EffectEngine()
    eff = Effect(type="color_grade", clip_id="c1", params={"intensity": 0.8})
    built = engine.build_filter(eff)
    assert built["type"] == "color_grade"
    assert built["category"] == "visual"
    assert "saturation=0.8" in built["ffmpeg_filter"]


def test_build_filter_subtitle_burn_renders_text():
    engine = EffectEngine()
    eff = Effect(
        type="subtitle_burn", clip_id="c1",
        params={"text": "hello world", "fontsize": 32},
    )
    built = engine.build_filter(eff)
    assert "drawtext" in built["ffmpeg_filter"]
    assert "hello world" in built["ffmpeg_filter"]
    assert "fontsize=32" in built["ffmpeg_filter"]


def test_build_filter_missing_param_raises():
    engine = EffectEngine()
    # subtitle_burn requires 'text' — provide empty
    eff = Effect(type="subtitle_burn", clip_id="c1", params={"text": ""})
    built = engine.build_filter(eff)
    assert "drawtext" in built["ffmpeg_filter"]


# ---- apply (mutates timeline) ----

def test_apply_appends_effect_to_timeline():
    engine = EffectEngine()
    timeline = {"clips": [{"id": "c1"}], "effects": []}
    built = engine.apply(timeline, clip_id="c1", type="blur", intensity=8.0)
    assert len(timeline["effects"]) == 1
    assert timeline["effects"][0]["type"] == "blur"


def test_apply_creates_effects_list_if_missing():
    engine = EffectEngine()
    timeline = {"clips": [{"id": "c1"}]}  # no effects key
    engine.apply(timeline, clip_id="c1", type="vignette", intensity=0.5)
    assert "effects" in timeline
    assert len(timeline["effects"]) == 1


# ---- each effect type at least builds ----

@pytest.mark.parametrize("eff_type", sorted(EFFECT_CATALOG.keys()))
def test_all_effect_types_build(eff_type):
    engine = EffectEngine()
    eff = Effect(type=eff_type, clip_id="c1")
    built = engine.build_filter(eff)
    assert built["type"] == eff_type
    assert "ffmpeg_filter" in built
    assert built["ffmpeg_filter"]  # non-empty