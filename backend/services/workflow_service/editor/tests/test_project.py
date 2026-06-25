"""Tests for project store — CRUD + snapshots + lock + undo."""
import time
import pytest

from services.workflow_service.editor.project import (
    ProjectStore, EditorProject, TemplateFetchError,
)


@pytest.fixture
def store():
    return ProjectStore()


# ---- CRUD ----

def test_create_project(store):
    p = store.create(name="My Video", owner="alice")
    assert p.id.startswith("prj-")
    assert p.name == "My Video"
    assert p.owner == "alice"
    assert p.version == 1
    assert "clips" in p.timeline


def test_create_empty_name_raises(store):
    with pytest.raises(ValueError, match="name must be non-empty"):
        store.create(name="")


def test_create_duplicate_id_raises(store):
    p1 = store.create(name="A", project_id="p1")
    with pytest.raises(ValueError, match="project_exists"):
        store.create(name="B", project_id="p1")


def test_get_project(store):
    p = store.create(name="X")
    fetched = store.get(p.id)
    assert fetched is p
    assert store.get("nonexistent") is None


def test_update_name(store):
    p = store.create(name="old")
    updated = store.update(p.id, name="new")
    assert updated.name == "new"
    assert updated.version == 2


def test_update_timeline_pushes_undo(store):
    p = store.create(name="X", timeline={"clips": ["a"]})
    store.update(p.id, timeline={"clips": ["b"]})
    assert len(p.undo_stack) == 1
    assert p.timeline["clips"] == ["b"]


def test_update_version_conflict(store):
    p = store.create(name="X")
    with pytest.raises(ValueError, match="version_conflict"):
        store.update(p.id, name="new", expected_version=99)


def test_delete_project(store):
    p = store.create(name="X")
    assert store.delete(p.id) is True
    assert store.get(p.id) is None
    assert store.delete(p.id) is False


def test_list_projects_by_owner(store):
    store.create(name="A", owner="alice")
    store.create(name="B", owner="bob")
    store.create(name="C", owner="alice")
    alice_projects = store.list(owner="alice")
    assert len(alice_projects) == 2


# ---- Undo / Redo ----

def test_undo_after_update(store):
    p = store.create(name="X", timeline={"v": 1})
    store.update(p.id, timeline={"v": 2})
    store.undo(p.id)
    assert p.timeline["v"] == 1


def test_redo_after_undo(store):
    p = store.create(name="X", timeline={"v": 1})
    store.update(p.id, timeline={"v": 2})
    store.undo(p.id)
    store.redo(p.id)
    assert p.timeline["v"] == 2


def test_undo_empty_raises(store):
    p = store.create(name="X")
    with pytest.raises(ValueError, match="nothing to undo"):
        store.undo(p.id)


def test_redo_empty_raises(store):
    p = store.create(name="X")
    with pytest.raises(ValueError, match="nothing to redo"):
        store.redo(p.id)


# ---- Snapshots ----

def test_snapshot_creates_entry(store):
    p = store.create(name="X", timeline={"v": 1})
    store.snapshot(p.id, label="v1-snap")
    assert len(p.snapshots) == 1
    assert p.snapshots[0]["label"] == "v1-snap"


def test_restore_snapshot(store):
    p = store.create(name="X", timeline={"v": 1})
    store.update(p.id, timeline={"v": 2})
    snap_id = p.snapshots[0]["id"] if p.snapshots else None
    # Need to snapshot v1 first
    store.update(p.id, timeline={"v": 1})  # no, this would also push undo
    # Actually, let's do: create → snapshot → update → restore
    p2 = store.create(name="Y", timeline={"v": 1})
    store.snapshot(p2.id, label="first")
    store.update(p2.id, timeline={"v": 99})
    sid = p2.snapshots[0]["id"]
    store.restore_snapshot(p2.id, sid)
    assert p2.timeline["v"] == 1


def test_restore_unknown_snapshot_raises(store):
    p = store.create(name="X")
    with pytest.raises(ValueError, match="snapshot_not_found"):
        store.restore_snapshot(p.id, "nope")


# ---- Lock ----

def test_acquire_lock(store):
    p = store.create(name="X")
    store.acquire_lock(p.id, user_id="alice", ttl_sec=60)
    assert p.lock["user_id"] == "alice"


def test_acquire_lock_already_held_raises(store):
    p = store.create(name="X")
    store.acquire_lock(p.id, user_id="alice", ttl_sec=60)
    with pytest.raises(ValueError, match="project_locked_by"):
        store.acquire_lock(p.id, user_id="bob", ttl_sec=60)


def test_acquire_lock_same_user_refreshes(store):
    p = store.create(name="X")
    store.acquire_lock(p.id, user_id="alice", ttl_sec=60)
    store.acquire_lock(p.id, user_id="alice", ttl_sec=120)
    assert p.lock["ttl_sec"] == 120


def test_release_lock(store):
    p = store.create(name="X")
    store.acquire_lock(p.id, user_id="alice", ttl_sec=60)
    store.release_lock(p.id, user_id="alice")
    assert p.lock is None


def test_release_lock_wrong_user_does_nothing(store):
    p = store.create(name="X")
    store.acquire_lock(p.id, user_id="alice", ttl_sec=60)
    store.release_lock(p.id, user_id="bob")
    assert p.lock is not None


def test_heartbeat_updates_since(store):
    p = store.create(name="X")
    store.acquire_lock(p.id, user_id="alice", ttl_sec=60)
    original_since = p.lock["since"]
    time.sleep(0.01)
    store.heartbeat(p.id, user_id="alice")
    assert p.lock["since"] > original_since


# ---- Template load ----

def test_load_unknown_template_raises(store):
    p = store.create(name="X")
    # load_template raises ValueError("template_not_found: ...") wrapping the
    # underlying TemplateFetchError; verify either type matches.
    with pytest.raises((TemplateFetchError, ValueError)) as exc_info:
        store.load_template(p.id, "definitely_not_a_real_template_xyz")
    # The error message should reference the template id
    assert "definitely_not_a_real_template_xyz" in str(exc_info.value)


# ---- to_dict ----

def test_to_dict_includes_essentials(store):
    p = store.create(name="X")
    d = p.to_dict()
    assert "id" in d
    assert "name" in d
    assert "timeline" in d
    assert "status" in d
    assert "owner" in d
    assert "version" in d
    assert "undo_depth" in d
    assert "redo_depth" in d
    assert "snapshots" in d
    assert "collaborators" in d
    assert "lock" in d