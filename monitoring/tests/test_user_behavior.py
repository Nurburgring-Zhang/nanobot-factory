"""Layer 12 — User behavior tests."""

from __future__ import annotations

import pytest

from monitoring import user_behavior as ub_mod


@pytest.fixture(autouse=True)
def _reset_tracker():
    ub_mod._TRACKER = None
    yield
    ub_mod._TRACKER = None


def test_record_heatmap():
    t = ub_mod.UserBehaviorTracker()
    ev = t.record_heatmap(
        user_id="u1", session_id="s1", route="/home",
        x=0.5, y=0.5, event_type="click",
    )
    assert ev.x == 0.5
    assert ev.route == "/home"
    assert len(t.heatmap) == 1


def test_heatmap_for_route_filters():
    t = ub_mod.UserBehaviorTracker()
    t.record_heatmap(user_id="u1", session_id="s", route="/home", x=0.1, y=0.1)
    t.record_heatmap(user_id="u1", session_id="s", route="/about", x=0.5, y=0.5)
    home_items = t.heatmap_for_route("/home")
    assert len(home_items) == 1
    assert home_items[0]["route"] == "/home"


def test_heatmap_routes_summary():
    t = ub_mod.UserBehaviorTracker()
    for _ in range(3):
        t.record_heatmap(user_id="u1", session_id="s", route="/home", x=0, y=0)
    for _ in range(2):
        t.record_heatmap(user_id="u1", session_id="s", route="/about", x=0, y=0)
    routes = t.heatmap_routes()
    by_route = {r["route"]: r["events"] for r in routes}
    assert by_route["/home"] == 3
    assert by_route["/about"] == 2


def test_record_funnel():
    t = ub_mod.UserBehaviorTracker()
    t.record_funnel(user_id="u1", stage="login")
    t.record_funnel(user_id="u1", stage="first_action")
    rep = t.funnel_report()
    assert rep["total_events"] == 2
    assert rep["unique_users"] == 1


def test_funnel_conversion_rates():
    t = ub_mod.UserBehaviorTracker()
    # 10 users log in
    for i in range(10):
        t.record_funnel(user_id=f"u{i}", stage="login")
    # 5 reach first_action
    for i in range(5):
        t.record_funnel(user_id=f"u{i}", stage="first_action")
    # 2 reach first_paid_action
    for i in range(2):
        t.record_funnel(user_id=f"u{i}", stage="first_paid_action")
    rep = t.funnel_report()
    stages = {s["stage"]: s for s in rep["stages"]}
    assert stages["login"]["users"] == 10
    assert stages["first_action"]["users"] == 5
    assert stages["first_paid_action"]["users"] == 2
    assert stages["first_paid_action"]["conversion_from_first"] == 0.2


def test_on_event_hook_called():
    called = []

    def hook(kind: str, payload: dict) -> None:
        called.append((kind, payload))

    t = ub_mod.UserBehaviorTracker()
    t.set_on_event(hook)
    t.record_heatmap(user_id="u1", session_id="s", route="/x", x=0, y=0)
    t.record_funnel(user_id="u1", stage="login")
    assert len(called) == 2
    assert called[0][0] == "heatmap"
    assert called[1][0] == "funnel"


def test_stats_shape():
    t = ub_mod.UserBehaviorTracker()
    t.record_heatmap(user_id="u1", session_id="s", route="/x", x=0, y=0)
    t.record_funnel(user_id="u1", stage="login")
    s = t.stats()
    assert s["heatmap"]["buffer_size"] == 1
    assert s["funnel"]["buffer_size"] == 1
