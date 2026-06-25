"""Tests for transition engine — 12 transitions + easing curves."""
import pytest

from services.workflow_service.editor.transition import (
    TransitionEngine, Transition,
    TRANSITION_TYPES, EASING_FUNCTIONS,
    list_transitions, list_easing_functions,
    apply_easing,
)


# ---- catalog ----

def test_transition_types_count():
    assert len(TRANSITION_TYPES) == 12


def test_easing_functions_count():
    assert len(EASING_FUNCTIONS) == 6


def test_list_transitions_meta():
    items = list_transitions()
    assert len(items) == 12
    for item in items:
        assert "id" in item
        assert "min_duration" in item
        assert "max_duration" in item
        assert "default_duration" in item


def test_list_easing_functions_meta():
    items = list_easing_functions()
    assert len(items) == 6
    assert all("id" in item and "name" in item for item in items)


# ---- easing ----

def test_easing_linear():
    assert apply_easing(0.0, "linear") == 0.0
    assert apply_easing(0.5, "linear") == 0.5
    assert apply_easing(1.0, "linear") == 1.0


def test_easing_ease_in_quadratic():
    assert apply_easing(0.5, "ease-in") == 0.25
    assert apply_easing(1.0, "ease-in") == 1.0


def test_easing_ease_out():
    assert apply_easing(0.0, "ease-out") == 0.0
    assert apply_easing(1.0, "ease-out") == 1.0
    # ease-out curve is concave — value at midpoint > 0.5
    assert apply_easing(0.5, "ease-out") > 0.5


def test_easing_ease_in_out():
    assert apply_easing(0.5, "ease-in-out") == 0.5
    assert 0 < apply_easing(0.25, "ease-in-out") < 0.5


def test_easing_cubic_bezier_material():
    val = apply_easing(0.5, "cubic-bezier(0.4,0,0.2,1)")
    assert 0 <= val <= 1.05


def test_easing_invalid_raises():
    with pytest.raises(ValueError, match="unknown easing"):
        apply_easing(0.5, "magical_easing")


def test_easing_clip_t():
    # t > 1 should be clipped to 1
    assert apply_easing(1.5, "linear") == 1.0
    assert apply_easing(-0.5, "linear") == 0.0


# ---- validation ----

def test_validate_unknown_type():
    engine = TransitionEngine()
    t = Transition(type="nope", duration=0.5, from_clip="a", to_clip="b")
    with pytest.raises(ValueError, match="unknown transition type"):
        engine.validate(t)


def test_validate_duration_out_of_range():
    engine = TransitionEngine()
    # glitch has max 1.0
    t = Transition(type="glitch", duration=5.0, from_clip="a", to_clip="b")
    with pytest.raises(ValueError, match="out of range"):
        engine.validate(t)


def test_validate_unknown_easing():
    engine = TransitionEngine()
    t = Transition(
        type="fade", duration=0.5, from_clip="a", to_clip="b",
        easing="magic",
    )
    with pytest.raises(ValueError, match="unknown easing"):
        engine.validate(t)


# ---- build_filter ----

def test_build_filter_fade_emits_xfade():
    engine = TransitionEngine()
    t = Transition(type="fade", duration=0.5, from_clip="a", to_clip="b")
    built = engine.build_filter(t)
    assert "xfade" in built["ffmpeg_filter"]
    assert built["type"] == "fade"
    assert len(built["keyframes"]) == 5  # 5 sampled keyframes


def test_build_filter_dip_to_color_includes_color():
    engine = TransitionEngine()
    t = Transition(
        type="dip_to_color", duration=0.5, from_clip="a", to_clip="b",
        color="white",
    )
    built = engine.build_filter(t)
    assert "color=white" in built["ffmpeg_filter"]


def test_build_filter_wipe_with_direction():
    engine = TransitionEngine()
    t = Transition(
        type="wipe", duration=0.6, from_clip="a", to_clip="b",
        direction="right",
    )
    built = engine.build_filter(t)
    assert "wiperight" in built["ffmpeg_filter"]


# ---- apply ----

def test_apply_same_clips_raises():
    engine = TransitionEngine()
    with pytest.raises(ValueError, match="must differ"):
        engine.apply({"clips": []}, from_clip="a", to_clip="a")


def test_apply_appends_transition_to_timeline():
    engine = TransitionEngine()
    timeline = {"clips": [], "transitions": []}
    built = engine.apply(timeline, from_clip="a", to_clip="b", type="fade")
    assert len(timeline["transitions"]) == 1


# ---- each transition type at least builds ----

# Per-transition max durations (must stay within the engine's validation range).
# Some transitions like ``match_cut`` cap at 0.3 s; others allow up to 2.0 s.
_TRANSITION_DURATION = {
    "cut": 0.0, "fade": 1.0, "dissolve": 1.5, "wipe": 1.0,
    "slide": 1.0, "push": 1.0, "zoom": 1.0, "morph": 2.0,
    "match_cut": 0.25, "jump_cut": 0.1, "crossfade": 1.5, "blink": 0.2,
}


@pytest.mark.parametrize("t_type", TRANSITION_TYPES)
def test_all_transition_types_build(t_type):
    engine = TransitionEngine()
    duration = _TRANSITION_DURATION.get(t_type, 0.5)
    t = Transition(type=t_type, duration=duration, from_clip="a", to_clip="b")
    built = engine.build_filter(t)
    assert built["type"] == t_type
    assert "ffmpeg_filter" in built