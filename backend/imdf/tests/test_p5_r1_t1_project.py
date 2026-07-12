"""P5-R1-T1 ProjectCenter — 12 pytest 用例。

测试范围:
  1. test_create_project          创建项目 + 默认状态 + 默认优先级
  2. test_list_projects           列表 + keyword/status/priority 过滤 + 分页
  3. test_get_project             按 id 取详情, 不存在 404
  4. test_update_project          改 name / description / priority / tags / dates
  5. test_delete_project          删除后 get_project 抛 ProjectNotFoundError
  6. test_add_member              加成员 + 重复添加幂等 (role 更新)
  7. test_remove_member           移除成员 + 同步 Project.members JSON
  8. test_status_transition_valid planning → active → paused → active → closed
  9. test_status_transition_invalid closed → active 抛 ProjectStatusTransitionError
 10. test_stats                   stats 包含 4 KPI + progress
 11. test_timeline                创建 + 状态切换 → timeline 含 2+ events
 12. test_concurrent_create       多线程并发创建 5 个, 全部成功 + ID 唯一

执行:
    pytest backend/imdf/tests/test_p5_r1_t1_project.py -v --tb=short
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

# ── sys.path ────────────────────────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) in sys.path:
    sys.path.remove(str(_BACKEND))
sys.path.insert(0, str(_BACKEND))

# 清掉可能被 conftest 缓存的错误 ``api`` 包
for _bad in ("api", "api.canvas_web", "api._common", "api.middleware", "db", "models"):
    if _bad in sys.modules:
        del sys.modules[_bad]


# ── 临时 SQLite ─────────────────────────────────────────────────────────────
_TMP_DB_DIR = _BACKEND / "data" / "test_p5_r1_t1"
_TMP_DB_DIR.mkdir(parents=True, exist_ok=True)
_TMP_DB = _TMP_DB_DIR / f"project_engine_{os.getpid()}_{int(time.time())}.db"


@pytest.fixture(scope="module")
def engine_factory():
    """一次性创建临时 SQLite + Engine + ProjectEngine 实例。"""
    # 必须在 conftest 重置 sys.path 之前, 先把临时 DB URL 钉死
    os.environ["IMDF_P2_DB_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"

    # 强制重建 db + models 模块, 让其读到临时 URL
    for _bad in ("db", "models", "models.project", "engines.project_engine"):
        if _bad in sys.modules:
            del sys.modules[_bad]

    from engines.project_engine import (
        ProjectEngine, make_sqlite_session_factory,
    )

    SessionLocal, _eng = make_sqlite_session_factory(_TMP_DB)
    return ProjectEngine(session_factory=SessionLocal)


@pytest.fixture(scope="module")
def engine(engine_factory):
    return engine_factory


# ─────────────────────────────────────────────────────────────────────────────
# 1. test_create_project
# ─────────────────────────────────────────────────────────────────────────────
def test_create_project(engine):
    proj = engine.create_project(
        name="测试项目A",
        description="first project",
        owner_id="alice",
        members=["bob", "carol"],
        priority="P2",
        tags=["ai", "image"],
        start_date="2026-06-01",
        due_date="2026-07-01",
    )
    assert proj.id.startswith("proj_"), f"id format: {proj.id}"
    assert proj.name == "测试项目A"
    assert proj.description == "first project"
    assert proj.status == "planning"
    assert proj.priority == "P2"
    assert proj.owner_id == "alice"
    # members JSON 仅存显式传入的成员 (不含 owner, owner 单独存于 owner_id)
    assert set(proj.members) == {"bob", "carol"}
    assert set(proj.tags) == {"ai", "image"}
    assert proj.start_date == "2026-06-01"
    assert proj.due_date == "2026-07-01"
    assert proj.created_at != ""
    assert proj.updated_at != ""

    # owner_id 应在 ProjectMember 表里 (role=owner), bob/carol 应在 (role=member)
    members = engine.list_members(proj.id)
    members_by_uid = {m["user_id"]: m for m in members}
    assert members_by_uid["alice"]["role"] == "owner"
    assert members_by_uid["bob"]["role"] == "member"
    assert members_by_uid["carol"]["role"] == "member"


# ─────────────────────────────────────────────────────────────────────────────
# 2. test_list_projects
# ─────────────────────────────────────────────────────────────────────────────
def test_list_projects(engine):
    # 已有 "测试项目A", 再加 2 个用于过滤测试
    p1 = engine.create_project(name="数据采集项目", owner_id="bob", priority="P0", tags=["采集"])
    p2 = engine.create_project(name="模型评测项目", owner_id="carol", priority="P3", tags=["评测"])
    engine.create_project(name="(will be deleted)", owner_id="alice", priority="P1")

    # 全部
    all_items, total = engine.list_projects()
    assert total >= 4, f"total = {total}"
    assert any(p.id == p1.id for p in all_items)

    # status=planning 过滤
    planning_items, planning_total = engine.list_projects(status="planning")
    assert planning_total >= 3
    assert all(p.status == "planning" for p in planning_items)

    # owner 过滤
    bob_items, bob_total = engine.list_projects(owner_id="bob")
    assert bob_total >= 1
    assert all(p.owner_id == "bob" for p in bob_items)

    # priority 过滤
    p0_items, p0_total = engine.list_projects(priority="P0")
    assert p0_total >= 1
    assert all(p.priority == "P0" for p in p0_items)

    # keyword 过滤
    kw_items, kw_total = engine.list_projects(keyword="数据采集")
    assert kw_total >= 1
    assert any("数据采集" in p.name for p in kw_items)

    # 分页
    paged, paged_total = engine.list_projects(page=1, page_size=2)
    assert len(paged) <= 2
    assert paged_total >= 4


# ─────────────────────────────────────────────────────────────────────────────
# 3. test_get_project
# ─────────────────────────────────────────────────────────────────────────────
def test_get_project(engine):
    p = engine.create_project(name="get-target", owner_id="alice")
    got = engine.get_project(p.id)
    assert got.id == p.id
    assert got.name == "get-target"

    from engines.project_engine import ProjectNotFoundError
    with pytest.raises(ProjectNotFoundError):
        engine.get_project("proj_does_not_exist_zzz")


# ─────────────────────────────────────────────────────────────────────────────
# 4. test_update_project
# ─────────────────────────────────────────────────────────────────────────────
def test_update_project(engine):
    p = engine.create_project(name="upd-target", owner_id="alice", priority="P3")
    updated = engine.update_project(
        p.id,
        name="upd-target-renamed",
        description="updated",
        priority="P0",
        tags=["urgent", "v2"],
        start_date="2026-07-01",
        due_date="2026-08-01",
    )
    assert updated.name == "upd-target-renamed"
    assert updated.description == "updated"
    assert updated.priority == "P0"
    assert set(updated.tags) == {"urgent", "v2"}
    assert updated.start_date == "2026-07-01"
    assert updated.due_date == "2026-08-01"

    # 校验 timestamp 更新
    assert updated.updated_at >= p.updated_at


# ─────────────────────────────────────────────────────────────────────────────
# 5. test_delete_project
# ─────────────────────────────────────────────────────────────────────────────
def test_delete_project(engine):
    p = engine.create_project(name="del-target", owner_id="alice")
    ok = engine.delete_project(p.id)
    assert ok is True

    from engines.project_engine import ProjectNotFoundError
    with pytest.raises(ProjectNotFoundError):
        engine.get_project(p.id)

    # 二次删除返回 False
    ok2 = engine.delete_project(p.id)
    assert ok2 is False

    # 关联 members / timeline 也被清掉
    members = engine.list_members(p.id)
    assert members == []


# ─────────────────────────────────────────────────────────────────────────────
# 6. test_add_member
# ─────────────────────────────────────────────────────────────────────────────
def test_add_member(engine):
    p = engine.create_project(name="member-target", owner_id="alice")
    proj1 = engine.add_member(p.id, "diana", role="admin")
    assert "diana" in proj1.members

    members = engine.list_members(p.id)
    assert any(m["user_id"] == "diana" and m["role"] == "admin" for m in members)

    # 重复添加 — role 更新
    proj2 = engine.add_member(p.id, "diana", role="member")
    members2 = engine.list_members(p.id)
    roles = [m["role"] for m in members2 if m["user_id"] == "diana"]
    assert "member" in roles
    # 去重后 member 列表里 diana 只出现 1 次
    diana_count = sum(1 for m in members2 if m["user_id"] == "diana")
    assert diana_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# 7. test_remove_member
# ─────────────────────────────────────────────────────────────────────────────
def test_remove_member(engine):
    p = engine.create_project(
        name="rm-target", owner_id="alice", members=["bob", "carol"]
    )
    proj = engine.remove_member(p.id, "bob")
    assert "bob" not in proj.members
    assert "carol" in proj.members  # 其他人保留

    members = engine.list_members(p.id)
    assert not any(m["user_id"] == "bob" for m in members)


# ─────────────────────────────────────────────────────────────────────────────
# 8. test_status_transition_valid
# ─────────────────────────────────────────────────────────────────────────────
def test_status_transition_valid(engine):
    p = engine.create_project(name="transition-target", owner_id="alice", status="planning")
    assert p.status == "planning"

    # planning → active
    p2 = engine.transition_status(p.id, "active", reason="kickoff")
    assert p2.status == "active"

    # active → paused
    p3 = engine.transition_status(p.id, "paused", reason="awaiting input")
    assert p3.status == "paused"

    # paused → active (resume)
    p4 = engine.transition_status(p.id, "active", reason="resume")
    assert p4.status == "active"

    # active → closed (terminal)
    p5 = engine.transition_status(p.id, "closed", reason="done")
    assert p5.status == "closed"


# ─────────────────────────────────────────────────────────────────────────────
# 9. test_status_transition_invalid
# ─────────────────────────────────────────────────────────────────────────────
def test_status_transition_invalid(engine):
    p = engine.create_project(name="invalid-target", owner_id="alice", status="planning")

    # planning → paused 非法 (必须先 active)
    from engines.project_engine import ProjectStatusTransitionError
    with pytest.raises(ProjectStatusTransitionError) as exc_info:
        engine.transition_status(p.id, "paused")
    assert exc_info.value.old == "planning"
    assert exc_info.value.new == "paused"

    # 先 active, 再 closed
    p2 = engine.transition_status(p.id, "active")
    p3 = engine.transition_status(p.id, "closed")
    assert p3.status == "closed"

    # closed → active 非法 (terminal)
    with pytest.raises(ProjectStatusTransitionError):
        engine.transition_status(p.id, "active")


# ─────────────────────────────────────────────────────────────────────────────
# 10. test_stats
# ─────────────────────────────────────────────────────────────────────────────
def test_stats(engine):
    p = engine.create_project(
        name="stats-target", owner_id="alice", priority="P2",
        members=["bob", "carol", "diana"],
        tags=["t1", "t2", "t3"],
    )
    stats = engine.get_project_stats(p.id)
    assert stats["project_id"] == p.id
    assert stats["name"] == "stats-target"
    assert stats["status"] == "planning"
    assert stats["priority"] == "P2"
    assert stats["owner_id"] == "alice"
    assert stats["members_count"] >= 3
    assert stats["tags_count"] == 3
    assert "requirements_count" in stats
    assert "tasks_count" in stats
    assert "datasets_count" in stats
    assert "deliveries_count" in stats
    assert "progress" in stats
    assert 0.0 <= stats["progress"] <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# 11. test_timeline
# ─────────────────────────────────────────────────────────────────────────────
def test_timeline(engine):
    p = engine.create_project(name="timeline-target", owner_id="alice")
    engine.update_project(p.id, description="updated")
    engine.transition_status(p.id, "active")
    engine.add_member(p.id, "bob")

    events = engine.get_timeline(p.id)
    types = [e["event_type"] for e in events]

    assert "created" in types, f"missing 'created' in {types}"
    assert "updated" in types, f"missing 'updated' in {types}"
    assert "status_changed" in types, f"missing 'status_changed' in {types}"
    assert "member_added" in types, f"missing 'member_added' in {types}"

    # 时间倒序: 最新在前
    assert len(events) >= 4
    for i in range(len(events) - 1):
        assert events[i]["ts"] >= events[i + 1]["ts"], "timeline not sorted DESC"


# ─────────────────────────────────────────────────────────────────────────────
# 12. test_concurrent_create
# ─────────────────────────────────────────────────────────────────────────────
def test_concurrent_create(engine):
    """5 个线程并发创建项目 — 全部成功 + ID 唯一。"""
    results: list = []
    errors: list = []

    def _worker(idx: int):
        try:
            proj = engine.create_project(
                name=f"concurrent-{idx}",
                owner_id=f"user_{idx}",
                priority="P2",
            )
            results.append(proj.id)
        except Exception as exc:  # pragma: no cover
            errors.append((idx, str(exc)))

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"concurrent errors: {errors}"
    assert len(results) == 5
    assert len(set(results)) == 5, f"duplicate ids: {results}"
    for rid in results:
        assert rid.startswith("proj_")


# ─────────────────────────────────────────────────────────────────────────────
# Module-level cleanup
# ─────────────────────────────────────────────────────────────────────────────
def teardown_module(module):
    """关闭 engine, 删除临时 SQLite 文件。"""
    try:
        # 关闭所有 engine 连接
        from sqlalchemy import create_engine as _ce
        eng = _ce(f"sqlite:///{_TMP_DB.as_posix()}")
        eng.dispose()
    except Exception:
        pass

    for p in (_TMP_DB, _TMP_DB.with_suffix(".db-shm"), _TMP_DB.with_suffix(".db-wal")):
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))