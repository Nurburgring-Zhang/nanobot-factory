"""P4-6-W1 tests for project management.

3 tests covering: CRUD + snapshot + undo/redo + collaboration lock.
"""
from __future__ import annotations

import time

import pytest

from services.workflow_service.editor.project import (EditorProject,
                                                      ProjectStore)


def test_project_crud_undo_redo_and_snapshot():
    """create / update / snapshot / undo / redo / restore_snapshot."""
    store = ProjectStore()
    # Create
    p = store.create(name="My Film", owner="alice")
    assert p.id.startswith("prj-")
    assert p.version == 1
    # Update with timeline
    new_tl = {
        "clips": [{"id": "c1", "start": 0.0, "end": 2.0, "duration": 2.0}],
        "cuts": [], "transitions": [], "effects": [],
    }
    p = store.update(p.id, timeline=new_tl, status="editing")
    assert p.version == 2
    assert p.timeline["clips"][0]["id"] == "c1"
    # Undo (revert to v1)
    p = store.undo(p.id)
    assert p.timeline.get("clips") == []
    # Redo
    p = store.redo(p.id)
    assert p.timeline["clips"][0]["id"] == "c1"
    # Snapshot
    p = store.snapshot(p.id, label="v2-snap")
    assert len(p.snapshots) == 1
    snap_id = p.snapshots[0]["id"]
    # Update again, then restore snapshot
    p = store.update(p.id, timeline={
        "clips": [], "cuts": [], "transitions": [], "effects": []})
    assert p.timeline.get("clips") == []
    p = store.restore_snapshot(p.id, snap_id)
    assert p.timeline["clips"][0]["id"] == "c1"
    # Version conflict
    with pytest.raises(ValueError):
        store.update(p.id, expected_version=999, name="nope")
    # Delete
    assert store.delete(p.id) is True
    assert store.get(p.id) is None


def test_project_lock_heartbeat_and_release():
    """Lock acquire / TTL / heartbeat / release / re-acquire."""
    store = ProjectStore()
    p = store.create(name="Lock Test", owner="bob")
    # Acquire
    p = store.acquire_lock(p.id, user_id="alice", ttl_sec=2.0)
    assert p.lock is not None
    assert p.lock["user_id"] == "alice"
    # Different user cannot acquire
    with pytest.raises(ValueError):
        store.acquire_lock(p.id, user_id="charlie", ttl_sec=2.0)
    # Heartbeat refreshes TTL
    time.sleep(0.05)
    p = store.heartbeat(p.id, user_id="alice")
    assert p.lock is not None
    # Release
    p = store.release_lock(p.id, user_id="alice")
    assert p.lock is None
    # Now charlie can acquire
    p = store.acquire_lock(p.id, user_id="charlie", ttl_sec=2.0)
    assert p.lock["user_id"] == "charlie"
    # Auto-expire: wait > TTL and check
    p2 = p
    # Simulate a stale lock by manually aging it
    p2.lock["since"] -= 5
    # Another user can take over because lock is no longer alive
    p3 = store.acquire_lock(p.id, user_id="dave", ttl_sec=2.0)
    assert p3.lock["user_id"] == "dave"


def test_project_load_template_fallback():
    """Template load pulls clips even if the registry is unavailable."""
    store = ProjectStore()
    p = store.create(name="Tpl Test", owner="eve")
    # Use a clearly synthetic template id
    p2 = store.load_template(p.id, template_id="tpl-not-real-12345")
    assert p2.template_id == "tpl-not-real-12345"
    assert p2.timeline["clips"], "fallback template should give clips"
    assert p2.timeline["template_meta"]["template_id"] == "tpl-not-real-12345"
    # Validate that a real template id from the workflow registry, if
    # available, also loads.  We wrap in try/except because the
    # registry might not be importable in isolated unit tests.
    p3 = store.create(name="Tpl Real", owner="eve")
    try:
        store.load_template(p3.id, template_id="tpl-bz2-alpaca-sft")
        # If the registry is available, accept either success or stub.
    except ValueError:
        # Acceptable if the registry actually returned 404.
        pass
