"""P4-6-W1 tests for transition engine.

3 tests covering: 12 transition types + easing + filter-graph build.
"""
from __future__ import annotations

import pytest

from services.workflow_service.editor.transition import (
    EASING_FUNCTIONS, TRANSITION_TYPES, TransitionEngine, Transition,
    apply_easing, list_easing_functions, list_transitions,
)


def test_transition_catalog_12_types():
    assert len(TRANSITION_TYPES) == 12
    expected = {"fade", "dissolve", "wipe", "slide", "zoom", "blur",
                "glitch", "match_cut", "j_cut", "l_cut",
                "cross_dissolve", "dip_to_color"}
    assert set(TRANSITION_TYPES) == expected
    items = list_transitions()
    assert len(items) == 12
    # All transitions have min/max/default within [0, 2.0]
    for t in items:
        assert 0.0 <= t["min_duration"] <= 2.0
        assert 0.0 <= t["max_duration"] <= 2.0
        assert t["min_duration"] <= t["default_duration"] <= t["max_duration"]


def test_easing_functions_and_apply():
    """6 easing functions; apply_easing monotonic and 0/1 fixed points."""
    assert len(EASING_FUNCTIONS) == 6
    items = list_easing_functions()
    assert len(items) == 6
    for fn in EASING_FUNCTIONS:
        # fixed points
        assert apply_easing(0.0, fn) == pytest.approx(0.0, abs=0.01)
        assert apply_easing(1.0, fn) == pytest.approx(1.0, abs=0.01)
    # linear = identity
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert apply_easing(t, "linear") == pytest.approx(t)
    # ease-in is below linear for t < 0.5
    assert apply_easing(0.3, "ease-in") < 0.3
    # ease-out is above linear for t < 0.5
    assert apply_easing(0.3, "ease-out") > 0.3


def test_build_filter_for_all_12_transitions():
    """Each transition type yields a valid filter string + 5 keyframes."""
    eng = TransitionEngine()
    for t in TRANSITION_TYPES:
        # Use the per-type default duration so we respect each transition's
        # min/max bounds (e.g. match_cut only allows 0-0.3s).
        from services.workflow_service.editor.transition import (
            _TRANSITION_META,
        )
        dur = _TRANSITION_META[t]["default"]
        trans = Transition(
            type=t, duration=dur, from_clip="c1", to_clip="c2",
            easing="ease-in-out", direction="left", color="black",
        )
        built = eng.build_filter(trans)
        assert built["type"] == t
        assert built["duration"] == dur
        assert len(built["keyframes"]) == 5
        assert built["ffmpeg_filter"], f"empty filter for {t}"
        # Duration out of range is rejected
        with pytest.raises(ValueError):
            eng.build_filter(Transition(
                type=t, duration=999, from_clip="c1", to_clip="c2",
                easing="ease-in-out"))
