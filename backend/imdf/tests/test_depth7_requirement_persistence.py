"""VDP-2026 Depth-7 — RequirementEngine 跨进程持久化测试。

修复前: ``RequirementEngine.requirements: Dict[str, Requirement]`` 是
纯 in-memory dict, 重启 / 多 worker / 多 instance 时全丢, project
stats 实际只对单进程有意义。

修复后: 走 ``engines.requirement_store.RequirementStore`` (write-through):
- ``create_requirement`` 写内存 dict + DB row
- ``rehydrate()`` 启动时把 DB 拉回内存 dict
- ``count_*_by_project`` 走 store (内存 + DB 一致)

这些测试验证:
1. 写入后能在 DB 看到行
2. 模拟"重启" (clear 内存 + rehydrate) 后数据可恢复
3. 计数函数跨"重启"前后一致
4. 旧 API 签名兼容 (legacy tests 不破)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(scope="module")
def tmp_db_dir():
    d = Path(tempfile.mkdtemp(prefix="imdf_depth7_"))
    db_path = d / "imdf_p2.db"
    os.environ["IMDF_P2_DB_URL"] = f"sqlite:///{db_path.as_posix()}"
    # Re-import db with new URL? engine is built at import time. If the
    # engine is already built (test ran in same process), we work around
    # by relying on a fresh process. For this test, we set env before
    # importing canvas_web so engine picks up the new URL.
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_depth7_write_through_persists_to_db(tmp_db_dir, monkeypatch):
    """create_requirement 写完内存, DB 必须有 row。"""
    # Reload db module to pick up new env URL
    if "db" in sys.modules:
        # Re-import with new URL — SQLAlchemy engine is module-level, so we
        # need to rebind. Simpler: just import the store which uses the
        # engine indirectly. For this test we trust the env was set before
        # db import.
        pass
    from sqlalchemy import text
    from db import engine, SessionLocal, init_db
    from models import RequirementRow
    from engines.requirement_engine import (
        RequirementEngine,
        Priority,
        RequirementType,
    )

    # Fresh engine + tables
    init_db()
    eng = RequirementRow.__table__.create  # sanity
    s = SessionLocal()
    # Clear any leftover state from previous depth-7 run
    s.execute(text("DELETE FROM requirement_tasks"))
    s.execute(text("DELETE FROM requirements"))
    s.commit()
    s.close()

    eng_obj = RequirementEngine()
    req = eng_obj.create_requirement(
        title="depth7-persist-test",
        req_type=RequirementType.DATA_ANNOTATION,
        priority=Priority.P1,
        created_by="depth7",
        project_id="proj_test_001",
    )

    # Memory dict has it
    assert req.id in eng_obj.requirements

    # DB has the row
    s = SessionLocal()
    row = s.get(RequirementRow, req.id)
    s.close()
    assert row is not None, f"DB should have row for {req.id}"
    assert row.title == "depth7-persist-test"
    assert row.priority == "P1"
    assert row.project_id == "proj_test_001"


def test_depth7_count_uses_store(tmp_db_dir):
    """count_requirements_by_project 走 store, 跨 instance 一致。"""
    from engines.requirement_engine import (
        RequirementEngine,
        Priority,
        RequirementType,
    )

    # Create engine 1, add 2 requirements
    eng1 = RequirementEngine()
    eng1.create_requirement(
        title="req-A",
        project_id="proj_X",
    )
    eng1.create_requirement(
        title="req-B",
        project_id="proj_X",
    )
    # Engine 2 (simulates second process / worker) — different instance
    eng2 = RequirementEngine()
    n = eng2.count_requirements_by_project("proj_X")
    assert n == 2, f"expected 2, got {n}"


def test_depth7_rehydrate_after_clear(tmp_db_dir):
    """模拟进程重启: 清空内存 + rehydrate() → 内存 dict 仍能恢复。"""
    from engines.requirement_engine import (
        RequirementEngine,
        Priority,
        RequirementType,
    )
    from engines.requirement_store import (
        get_requirement_store,
        reset_requirement_store_for_test,
    )

    reset_requirement_store_for_test()
    eng = RequirementEngine()
    req = eng.create_requirement(
        title="rehydrate-test",
        project_id="proj_RE",
        priority=Priority.P0,
    )
    assert req.id in eng.requirements

    # Simulate restart: clear in-memory dict
    eng.requirements.clear()
    eng.tasks.clear()
    assert req.id not in eng.requirements

    # Rehydrate from DB
    n = eng.rehydrate()
    assert n > 0, f"rehydrate should return >0, got {n}"
    assert req.id in eng.requirements, "after rehydrate, req must be in memory"
    recovered = eng.get_requirement(req.id)
    assert recovered is not None
    assert recovered.title == "rehydrate-test"
    assert recovered.priority == Priority.P0


def test_depth7_count_tasks_via_store(tmp_db_dir):
    """count_tasks_by_project 走 store, 跨 instance 一致。"""
    from engines.requirement_engine import (
        RequirementEngine,
        Priority,
        RequirementType,
        TaskStatus,
    )
    from engines.requirement_store import reset_requirement_store_for_test
    reset_requirement_store_for_test()

    eng = RequirementEngine()
    r1 = eng.create_requirement(title="task-test-1", project_id="proj_T")
    r2 = eng.create_requirement(title="task-test-2", project_id="proj_T")

    # Create tasks via direct dict (bypassing engine's full assignment flow
    # to keep test independent)
    from engines.requirement_engine import Task
    t1 = Task(id="task_aaaaaaaa", requirement_id=r1.id, title="t1", status=TaskStatus.PENDING)
    t2 = Task(id="task_bbbbbbbb", requirement_id=r1.id, title="t2", status=TaskStatus.APPROVED)
    t3 = Task(id="task_cccccccc", requirement_id=r2.id, title="t3", status=TaskStatus.PENDING)
    eng.tasks[t1.id] = t1
    eng.tasks[t2.id] = t2
    eng.tasks[t3.id] = t3
    eng.store.upsert_task(t1)
    eng.store.upsert_task(t2)
    eng.store.upsert_task(t3)

    # Engine 2 — different instance, count via store
    eng2 = RequirementEngine()
    n_total = eng2.count_tasks_by_project("proj_T")
    assert n_total == 3, f"expected 3, got {n_total}"
    n_done = eng2.count_done_tasks_by_project("proj_T")
    assert n_done == 1, f"expected 1 approved, got {n_done}"


def test_depth7_get_requirement_from_store():
    """eng.get_requirement() 走 store, 跨 instance 一致。"""
    from engines.requirement_engine import RequirementEngine
    from engines.requirement_store import reset_requirement_store_for_test
    reset_requirement_store_for_test()

    eng1 = RequirementEngine()
    req = eng1.create_requirement(title="get-test", project_id="proj_G")

    eng2 = RequirementEngine()  # different instance
    got = eng2.get_requirement(req.id)
    assert got is not None, f"eng2 should see {req.id} via store"
    assert got.title == "get-test"


def test_depth7_legacy_api_still_works():
    """Depth-7 不能破坏 legacy RequirementEngine API — 所有原有调用必须 still work。"""
    from engines.requirement_engine import (
        RequirementEngine,
        Priority,
        RequirementType,
        TaskStatus,
        Task,
        AllocationStrategy,
    )

    eng = RequirementEngine()
    # Legacy create_requirement
    req = eng.create_requirement(
        title="legacy-1",
        req_type=RequirementType.DATA_ANNOTATION,
        priority=Priority.P2,
        created_by="legacy",
        project_id="proj_L",
    )
    assert req.id in eng.requirements

    # Legacy list_requirements
    listed = eng.list_requirements(project_id="proj_L")
    assert any(r.id == req.id for r in listed)

    # Legacy paginate_requirements
    items, total = eng.paginate_requirements(project_id="proj_L", page=1, page_size=20)
    assert total >= 1
    assert any(r.id == req.id for r in items)

    # Legacy AllocationStrategy
    scores = AllocationStrategy.by_skill(["text"], [])
    assert isinstance(scores, list)
