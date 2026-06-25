"""P4-3-W2: 6-layer MemoryPalace CRUD tests.

8 tests:

  1. test_l2_wing_create_and_get
  2. test_l2_wing_update_and_delete
  3. test_l3_room_create_list
  4. test_l3_room_status_transitions
  5. test_l4_drawer_create_and_search
  6. test_l5_tunnel_bridge
  7. test_free_form_items_l0_l1_l3
  8. test_palace_stats_5_tables

Run with::

    cd D:\\Hermes\\生产平台\\nanobot-factory
    D:\\ComfyUI\\.ext\\python.exe -m pytest tests/agent/test_memory_palace.py -v
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

# Path setup — see test_p3_3_w1_agent_service.py for the canonical recipe.
_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_PROJECT_ROOT = _BACKEND.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("IMDF_DATA_DIR", str(_BACKEND / "imdf" / "data"))
os.environ.setdefault("JWT_SECRET", "test-secret-DO-NOT-USE-IN-PROD-abcdef123456")
os.environ.setdefault("IMDF_TEST_MODE", "1")


def _fresh_palace(tmp_path=None):
    """Reset the module-level singleton so each test gets a clean DB."""
    import tempfile

    from services.agent_service.memory_palace import reset_memory_palace_for_test

    if tmp_path is None:
        tmp_path = tempfile.mkdtemp(prefix="mempalace_")
    db_path = str(tmp_path / "palace.db")
    return reset_memory_palace_for_test(db_path=db_path)


# ── 1. L2 Wing CRUD ─────────────────────────────────────────────────────────
def test_l2_wing_create_and_get(tmp_path):
    palace = _fresh_palace(tmp_path)
    w = palace.create_wing(
        name="prompt-engineering",
        description="All things prompts",
        trigger_keywords=["prompt", "system prompt", "few-shot"],
    )
    assert w.wing_id.startswith("wing-")
    assert w.name == "prompt-engineering"
    assert "prompt" in w.trigger_keywords
    fetched = palace.get_wing(w.wing_id)
    assert fetched is not None
    assert fetched.wing_id == w.wing_id


def test_l2_wing_update_and_delete(tmp_path):
    palace = _fresh_palace(tmp_path)
    w = palace.create_wing(name="data-quality", description="quality stuff")
    updated = palace.update_wing(w.wing_id, description="image quality metrics")
    assert updated is not None and updated.description == "image quality metrics"
    assert updated.updated_at >= w.created_at
    deleted = palace.delete_wing(w.wing_id)
    assert deleted is True
    assert palace.get_wing(w.wing_id) is None


# ── 2. L3 Room CRUD ─────────────────────────────────────────────────────────
def test_l3_room_create_list(tmp_path):
    palace = _fresh_palace(tmp_path)
    w = palace.create_wing(name="evaluation")
    r1 = palace.create_room(wing_id=w.wing_id, title="eval-round-1", summary="first pass")
    r2 = palace.create_room(wing_id=w.wing_id, title="eval-round-2", summary="second pass")
    rooms = palace.list_rooms(wing_id=w.wing_id)
    assert len(rooms) == 2
    assert {r.room_id for r in rooms} == {r1.room_id, r2.room_id}


def test_l3_room_status_transitions(tmp_path):
    palace = _fresh_palace(tmp_path)
    w = palace.create_wing(name="ops")
    r = palace.create_room(wing_id=w.wing_id, title="incident-001", status="active")
    r2 = palace.update_room(r.room_id, status="closed")
    assert r2 is not None and r2.status == "closed"
    closed_rooms = palace.list_rooms(wing_id=w.wing_id, status="closed")
    assert any(x.room_id == r.room_id for x in closed_rooms)


# ── 3. L4 Drawer + free-form items ─────────────────────────────────────────
def test_l4_drawer_create_and_search(tmp_path):
    palace = _fresh_palace(tmp_path)
    w = palace.create_wing(name="docs")
    r = palace.create_room(wing_id=w.wing_id, title="onboarding")
    d1 = palace.create_drawer(
        room_id=r.room_id,
        title="quickstart.md",
        content="Welcome to the platform.  Use --flag to enable verbose mode.",
        content_type="text",
    )
    d2 = palace.create_drawer(
        room_id=r.room_id,
        title="troubleshooting.md",
        content="If the server fails to start, check the port.",
        content_type="text",
    )
    found = palace.list_drawers(room_id=r.room_id)
    assert len(found) == 2
    # Search by content
    matching = [d for d in palace.list_drawers(limit=500) if "verbose" in d.content]
    assert any(d.drawer_id == d1.drawer_id for d in matching)


# ── 4. L5 Tunnels ───────────────────────────────────────────────────────────
def test_l5_tunnel_bridge(tmp_path):
    palace = _fresh_palace(tmp_path)
    w1 = palace.create_wing(name="wing-A")
    w2 = palace.create_wing(name="wing-B")
    t = palace.create_tunnel(
        from_id=w1.wing_id, to_id=w2.wing_id,
        from_kind="wing", to_kind="wing",
        relation="mirrors", note="A is the operational view of B",
    )
    assert t.tunnel_id.startswith("tun-")
    by_anchor = palace.list_tunnels(anchor_id=w1.wing_id)
    assert any(x.tunnel_id == t.tunnel_id for x in by_anchor)
    by_other = palace.list_tunnels(anchor_id=w2.wing_id)
    assert any(x.tunnel_id == t.tunnel_id for x in by_other)


# ── 5. Free-form Items (L0/L1/L3) ───────────────────────────────────────────
def test_free_form_items_l0_l1_l3(tmp_path):
    palace = _fresh_palace(tmp_path)
    # L0 identity record
    it0 = palace.create_item(level="L0_identity", parent_id="global", content="SOUL: 智影 platform", role="system")
    # L1 essential story record
    it1 = palace.create_item(level="L1_essential_story", parent_id="global", content="Project: nanobot-factory", role="system")
    # L3 verbatim record inside a room
    w = palace.create_wing(name="runtime")
    r = palace.create_room(wing_id=w.wing_id, title="incident-42")
    it3 = palace.create_item(level="L3_room", parent_id=r.room_id, content="User: please check the loader", role="user")

    identity = palace.list_items(level="L0_identity")
    story = palace.list_items(level="L1_essential_story")
    room_items = palace.list_items(parent_id=r.room_id)
    assert any(i.item_id == it0.item_id for i in identity)
    assert any(i.item_id == it1.item_id for i in story)
    assert any(i.item_id == it3.item_id for i in room_items)
    # search by content
    matches = palace.search_items("loader", level="L3_room")
    assert any(i.item_id == it3.item_id for i in matches)


# ── 6. Stats: 5 tables ──────────────────────────────────────────────────────
def test_palace_stats_5_tables(tmp_path):
    palace = _fresh_palace(tmp_path)
    s0 = palace.stats()
    assert set(s0.keys()) == {
        "memory_wings",
        "memory_rooms",
        "memory_drawers",
        "memory_tunnels",
        "memory_items",
    }
    # Populate
    w = palace.create_wing(name="w1")
    palace.create_wing(name="w2")
    palace.create_room(wing_id=w.wing_id, title="r1")
    palace.create_tunnel(from_id="x", to_id="y", from_kind="wing", to_kind="wing")
    palace.create_item(level="L0_identity", parent_id="global", content="x")
    s1 = palace.stats()
    assert s1["memory_wings"] == 2
    assert s1["memory_rooms"] == 1
    assert s1["memory_tunnels"] == 1
    assert s1["memory_items"] == 1


__all__ = [
    "test_l2_wing_create_and_get",
    "test_l2_wing_update_and_delete",
    "test_l3_room_create_list",
    "test_l3_room_status_transitions",
    "test_l4_drawer_create_and_search",
    "test_l5_tunnel_bridge",
    "test_free_form_items_l0_l1_l3",
    "test_palace_stats_5_tables",
]
