"""P5-R2-T2 ProjectCenter stats counter bug fix — 4 pytest 用例.

Bug 背景:
  project_engine.get_project_stats 旧实现里:
    - requirements_count 走 req_engine.count_requirements_by_project (正确, 按 project_id)
    - tasks_count       走 self._safe_count("models.Task", owner=proj.owner_id) (错误)
                        当 owner 有多个项目时, 把 owner 名下所有项目的 task 都算上,
                        与单项目 stats 语义严重不符
  而且 RequirementEngine.count_tasks_by_project 原实现用
    ``getattr(t, "project_id", None)``, 但 Task dataclass 没有 project_id 字段,
    永远返回 0 — 完全失效.

修复策略 (推荐选项 c: join via Requirement):
  1. RequirementEngine.count_tasks_by_project 改为两步:
     a) 收集该项目下所有 requirement_id
     b) 统计 task.requirement_id 命中数
  2. project_engine.get_project_stats 改用 req_engine.count_tasks_by_project
     与 count_done_tasks_by_project 替代 SQL owner 过滤.

测试覆盖 (4 用例):
  1. test_count_tasks_by_project_joins_via_requirement
     — req_engine 自身单测, 验证 join 逻辑 (A 项目 req → A 项目 task)
  2. test_count_tasks_by_project_isolates_projects
     — 同一 owner 两个项目, A 项目 task 不应被 B 项目 stats 算入
  3. test_get_project_stats_uses_project_id_not_owner
     — project_engine.get_project_stats 端到端: 2 项目同 owner, stats 应分开统计
  4. test_get_project_stats_progress_uses_join
     — 验证 done/total 进度计算也走 join, 不再被 owner 过滤污染
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest


# ── sys.path ────────────────────────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
_IMDF = _BACKEND  # 当前测试位于 backend/imdf/tests/, parent.parent = backend/imdf


def _ensure_imdf_path():
    """imdf/ 必须在 sys.path[0] — conftest 会动 sys.path, 每个 test 前重置"""
    p = str(_IMDF)
    for sub in ("api", "engines", "common"):
        sp = str(_IMDF / sub)
        while sp in sys.path:
            sys.path.remove(sp)
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)


@pytest.fixture(autouse=True)
def _imdf_path_fix():
    _ensure_imdf_path()
    yield


# ── 临时 SQLite ─────────────────────────────────────────────────────────────
_TMP_DB_DIR = _IMDF / "data" / "test_p5_r2_t2"
_TMP_DB_DIR.mkdir(parents=True, exist_ok=True)
_TMP_DB = _TMP_DB_DIR / f"project_stats_{os.getpid()}_{int(time.time())}.db"


@pytest.fixture(scope="module")
def engine_factory():
    os.environ["IMDF_P2_DB_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"

    for _bad in ("db", "models", "models.project",
                 "engines.project_engine", "engines.requirement_engine"):
        if _bad in sys.modules:
            del sys.modules[_bad]

    from engines.project_engine import (
        ProjectEngine, make_sqlite_session_factory,
    )
    SessionLocal, _eng = make_sqlite_session_factory(_TMP_DB)
    return ProjectEngine(session_factory=SessionLocal)


@pytest.fixture(scope="module")
def req_engine_singleton():
    """复用 project_engine 内的 RequirementEngine 单例 — 跨模块共享"""
    from engines.requirement_engine import get_requirement_engine
    return get_requirement_engine()


@pytest.fixture()
def fresh_req_engine():
    """每个用例一份独立 RequirementEngine (避免用例间污染)"""
    from engines.requirement_engine import RequirementEngine
    return RequirementEngine()


# ─────────────────────────────────────────────────────────────────────────────
# 1. test_count_tasks_by_project_joins_via_requirement
# ─────────────────────────────────────────────────────────────────────────────
def test_count_tasks_by_project_joins_via_requirement(fresh_req_engine):
    """验证 count_tasks_by_project 通过 requirement_id → project_id 链 join.

    Bug 复现条件:
      - 项目 proj_A 下有 1 个 requirement (req_1)
      - req_1 下有 3 个 task
      - 项目 proj_B 下 0 个 requirement
      - 另 1 个游离 task (requirement_id 不属于 proj_A 的任何 req)
    期望: proj_A 返回 3, proj_B 返回 0, 游离 task 不污染 A.
    """
    eng = fresh_req_engine
    # 创建项目 A 的需求
    req_a = eng.create_requirement(
        title="A的需求", project_id="proj_A",
    )
    # 创建游离需求 (不属于任何项目) + task (不应被 proj_A 计入)
    req_orphan = eng.create_requirement(title="游离需求", project_id=None)

    # 直接构造 task (dataclass 简化路径)
    from engines.requirement_engine import Task, TaskStatus
    for i in range(3):
        t = Task(
            id=f"task_a_{i}",
            requirement_id=req_a.id,
            title=f"A任务{i}",
            status=TaskStatus.PENDING,
        )
        eng.tasks[t.id] = t
    t_orphan = Task(
        id="task_orphan_0",
        requirement_id=req_orphan.id,
        title="游离任务",
        status=TaskStatus.PENDING,
    )
    eng.tasks[t_orphan.id] = t_orphan

    # 修复后: join 正确
    assert eng.count_tasks_by_project("proj_A") == 3, (
        "proj_A 应只统计 requirement_id 命中 proj_A.req_id 的 task"
    )
    assert eng.count_tasks_by_project("proj_B") == 0
    assert eng.count_tasks_by_project("") == 0  # 容错


# ─────────────────────────────────────────────────────────────────────────────
# 2. test_count_tasks_by_project_isolates_projects
# ─────────────────────────────────────────────────────────────────────────────
def test_count_tasks_by_project_isolates_projects(fresh_req_engine):
    """同一 owner 两个项目, 项目 A 的 task 不应被项目 B 算入.

    这正是 SQL owner=proj.owner_id 过滤无法区分的场景.
    """
    eng = fresh_req_engine
    from engines.requirement_engine import Task, TaskStatus

    # 项目 A: 1 req, 2 task
    req_a = eng.create_requirement(title="A", project_id="proj_X")
    for i in range(2):
        eng.tasks[f"xa_{i}"] = Task(
            id=f"xa_{i}", requirement_id=req_a.id,
            title=f"A任务{i}", status=TaskStatus.PENDING,
        )

    # 项目 B (同 owner 都叫 "alice" — 模拟真实场景): 1 req, 5 task
    req_b = eng.create_requirement(title="B", project_id="proj_Y")
    for i in range(5):
        eng.tasks[f"yb_{i}"] = Task(
            id=f"yb_{i}", requirement_id=req_b.id,
            title=f"B任务{i}", status=TaskStatus.PENDING,
        )

    # 旧实现 (用 owner 过滤) 会把 7 全算进两个项目, 修复后应严格隔离
    assert eng.count_tasks_by_project("proj_X") == 2
    assert eng.count_tasks_by_project("proj_Y") == 5


# ─────────────────────────────────────────────────────────────────────────────
# 3. test_get_project_stats_uses_project_id_not_owner
# ─────────────────────────────────────────────────────────────────────────────
def test_get_project_stats_uses_project_id_not_owner(
    engine_factory, req_engine_singleton,
):
    """project_engine.get_project_stats 端到端: 2 项目同 owner, stats 应分开统计."""
    proj_engine = engine_factory
    req_eng = req_engine_singleton

    from engines.requirement_engine import (
        Task, TaskStatus, RequirementType,
    )

    # 清空单例 (避免之前用例残留 — 测试隔离)
    req_eng.requirements.clear()
    req_eng.tasks.clear()

    # 创建 2 个项目, 同 owner (触发 owner 过滤 bug 的关键条件)
    p_a = proj_engine.create_project(name="项目A", owner_id="alice")
    p_b = proj_engine.create_project(name="项目B", owner_id="alice")

    # 项目 A: 2 需求, 4 task (1 done)
    for i in range(2):
        req = req_eng.create_requirement(
            title=f"A需求{i}",
            req_type=RequirementType.DATA_ANNOTATION,
            project_id=p_a.id,
            created_by="alice",
        )
        for j in range(2):
            req_eng.tasks[f"a_{i}_{j}"] = Task(
                id=f"a_{i}_{j}", requirement_id=req.id,
                title=f"A任务{i}-{j}",
                status=TaskStatus.APPROVED if (i == 0 and j == 0) else TaskStatus.PENDING,
            )

    # 项目 B: 3 需求, 9 task (2 done)
    for i in range(3):
        req = req_eng.create_requirement(
            title=f"B需求{i}",
            req_type=RequirementType.DATA_ANNOTATION,
            project_id=p_b.id,
            created_by="alice",
        )
        for j in range(3):
            req_eng.tasks[f"b_{i}_{j}"] = Task(
                id=f"b_{i}_{j}", requirement_id=req.id,
                title=f"B任务{i}-{j}",
                status=TaskStatus.APPROVED if (i < 2 and j == 0) else TaskStatus.PENDING,
            )

    stats_a = proj_engine.get_project_stats(p_a.id)
    stats_b = proj_engine.get_project_stats(p_b.id)

    # requirements_count: 走 join, 应严格按 project_id
    assert stats_a["requirements_count"] == 2, (
        f"A 应只有 2 个需求, 实际 {stats_a['requirements_count']}"
    )
    assert stats_b["requirements_count"] == 3, (
        f"B 应只有 3 个需求, 实际 {stats_b['requirements_count']}"
    )

    # tasks_count: 关键断言 — 旧 SQL owner 过滤会把 13 个全算, 修复后应分别 4 / 9
    assert stats_a["tasks_count"] == 4, (
        f"A 应只有 4 个 task, 实际 {stats_a['tasks_count']} (若 13 则 owner 过滤污染)"
    )
    assert stats_b["tasks_count"] == 9, (
        f"B 应只有 9 个 task, 实际 {stats_b['tasks_count']}"
    )

    # 修复后 stats_a 和 stats_b 的 tasks_count 必须不同 (口径已隔离)
    assert stats_a["tasks_count"] != stats_b["tasks_count"], (
        "tasks_count 在两项目间必须不同, 否则说明仍走 owner 全局过滤"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. test_get_project_stats_progress_uses_join
# ─────────────────────────────────────────────────────────────────────────────
def test_get_project_stats_progress_uses_join(
    engine_factory, req_engine_singleton,
):
    """进度 (done / total) 也必须走 join, 不被 owner 过滤污染."""
    proj_engine = engine_factory
    req_eng = req_engine_singleton

    from engines.requirement_engine import (
        Task, TaskStatus, RequirementType,
    )

    req_eng.requirements.clear()
    req_eng.tasks.clear()

    p_a = proj_engine.create_project(name="进度A", owner_id="bob")
    p_b = proj_engine.create_project(name="进度B", owner_id="bob")

    # A: 1 req, 4 task (1 done) → 25%
    req_a = req_eng.create_requirement(
        title="A", req_type=RequirementType.DATA_ANNOTATION,
        project_id=p_a.id, created_by="bob",
    )
    for i in range(4):
        req_eng.tasks[f"pa_{i}"] = Task(
            id=f"pa_{i}", requirement_id=req_a.id,
            title=f"t{i}",
            status=TaskStatus.APPROVED if i == 0 else TaskStatus.PENDING,
        )

    # B: 1 req, 2 task (1 done) → 50%
    req_b = req_eng.create_requirement(
        title="B", req_type=RequirementType.DATA_ANNOTATION,
        project_id=p_b.id, created_by="bob",
    )
    for i in range(2):
        req_eng.tasks[f"pb_{i}"] = Task(
            id=f"pb_{i}", requirement_id=req_b.id,
            title=f"t{i}",
            status=TaskStatus.APPROVED if i == 0 else TaskStatus.PENDING,
        )

    stats_a = proj_engine.get_project_stats(p_a.id)
    stats_b = proj_engine.get_project_stats(p_b.id)

    # A: 1 done / 4 total = 25.0%
    assert stats_a["progress"] == 25.0, (
        f"A 进度应 25.0%, 实际 {stats_a['progress']} "
        f"(done 估算: {stats_a['tasks_count']})"
    )
    # B: 1 done / 2 total = 50.0%
    assert stats_b["progress"] == 50.0, (
        f"B 进度应 50.0%, 实际 {stats_b['progress']} "
        f"(若变成 {stats_a['progress']} 或 16.7 则 owner 污染)"
    )

    # 验证 done_tasks 数 (间接通过 progress 反推 — A 1/4, B 1/2)
    assert stats_a["tasks_count"] == 4
    assert stats_b["tasks_count"] == 2
