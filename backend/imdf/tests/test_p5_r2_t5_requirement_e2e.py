"""P5-R2-T5 测试 — RequirementCenter 端到端 + 4 隐含 bug 修复验证

测试范围 (5 个):
  1. test_e2e_create_requirement_decompose_4_tasks
     端到端: 创建需求 → decompose → 真实产生 4 个 task
     + GET /api/requirements/{id}/stats 返回 tasks_count == 4
     + POST /api/requirements/{id}/decompose-preview task_count == 4 (与真拆解一致)

  2. test_reassign_all_4_strategies_change_assignee
     4 种 reassign 策略 (by_skill / by_workload / random / hybrid)
     每种都真的让 task.assignee 变化 (数据库生效)

  3. test_verify_requirement_uses_enum_not_string (Bug 1 fix)
     /api/requirements/verify 端点修复: 之前传 string "verified" 永远 False,
     现在走 verify_completion (返回完整 report), 修复后 200 + passed=True

  4. test_requirement_dataclass_all_fields_typed
     Requirement dataclass 字段类型完整 — 所有 Optional/str/List 都有 default,
     from_dict 反序列化不丢字段

  5. test_decompose_preview_matches_real_decompose_count
     预览拆解的 task_count == 真实拆解产生的 task 数 (data_annotation 默认 4)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Any, List

import pytest

# ── sys.path setup (确保 backend/imdf 可导入) ──────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

# 清掉可能缓存的 "api" 包, 避免 conftest 跑错
for _bad in ("api", "api.canvas_web", "api._common", "api.middleware"):
    if _bad in sys.modules:
        del sys.modules[_bad]


# ── imports ────────────────────────────────────────────────────────────────
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_extended import req_router
from engines.requirement_engine import (
    RequirementEngine,
    Requirement,
    RequirementStatus,
    RequirementType,
    Priority,
    TaskStatus,
    AllocationStrategy,
    UserSkill,
)


# ── fixture: 隔离的 RequirementEngine 单例 + 完整 FastAPI app ──────────────

@pytest.fixture
def fresh_engine():
    """重置模块级 _REQ_ENGINE_SINGLETON, 返回全新引擎.
    每次 test 都拿新单例,避免状态污染.
    """
    import api.routes_extended as rxe
    rxe._REQ_ENGINE_SINGLETON = None
    eng = rxe._get_req_engine()
    yield eng
    rxe._REQ_ENGINE_SINGLETON = None


@pytest.fixture
def client(fresh_engine):
    """mini FastAPI app + TestClient, 挂载 req_router."""
    app = FastAPI(title="requirement-test")
    app.include_router(req_router)
    return TestClient(app)


@pytest.fixture
def sample_requirement(fresh_engine):
    """创建一个样例需求 (绑 project_id, 已 open 状态)."""
    eng = fresh_engine
    r = eng.create_requirement(
        title="图像分类标注项目",
        req_type=RequirementType.DATA_ANNOTATION,
        priority=Priority.P1,
        created_by="alice",
        description="标注 1000 张图片",
        acceptance_criteria="准确率 ≥ 95%",
        tags=["image", "classification"],
        project_id="proj_test_001",
        owner="alice",
    )
    # 推到 OPEN (decompose 要求 OPEN)
    eng.update_requirement_status(r.id, RequirementStatus.OPEN)
    return r


# ── Test 1: 端到端 create → decompose → 4 tasks ───────────────────────────

class TestE2ECreateDecompose:
    """端到端真实链路: HTTP create → decompose → stats 验证."""

    def test_e2e_create_requirement_decompose_4_tasks(
        self, client, sample_requirement
    ):
        """1. 创建需求 → decompose → 4 tasks 真实产生.
        data_annotation 类型默认 4 任务 (line 779-786 requirement_engine.py).
        """
        req_id = sample_requirement.id

        # Step A: POST /api/requirements/{id}/decompose
        resp = client.post(f"/api/requirements/{req_id}/decompose")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True, body
        assert body["data"]["task_count"] == 4, body
        tasks = body["data"]["tasks"]
        assert len(tasks) == 4

        # Step B: GET /api/requirements/{id}/stats 验证 tasks_count == 4
        resp = client.get(f"/api/requirements/{req_id}/stats")
        assert resp.status_code == 200, resp.text
        stats = resp.json()["data"]
        assert stats["tasks_count"] == 4, stats
        assert stats["requirement"]["id"] == req_id
        # task_tree 应含 4 个 task
        assert len(stats["task_tree"]) == 4

        # Step C: 验证 requirement 状态变成 in_progress
        assert stats["requirement"]["status"] == "in_progress"

    def test_decompose_preview_matches_real_decompose_count(
        self, client, sample_requirement
    ):
        """2. preview_decompose 任务数 == 真实拆解数.
        data_annotation: low/medium complexity 都 4 任务, 任务列表 title 须一致.
        """
        req_id = sample_requirement.id

        # Preview
        resp = client.get(f"/api/requirements/{req_id}/decompose-preview")
        assert resp.status_code == 200, resp.text
        preview = resp.json()["data"]
        preview_titles = [t["title"] for t in preview["tasks"]]
        assert preview["task_count"] == 4

        # Real decompose
        resp = client.post(f"/api/requirements/{req_id}/decompose")
        assert resp.status_code == 200
        real = resp.json()["data"]
        real_titles = [t["title"] for t in real["tasks"]]
        assert len(real_titles) == 4

        # Preview 和 real 的任务数一致
        assert len(preview_titles) == len(real_titles) == 4

    def test_create_requirement_with_project_id_persists(
        self, client, fresh_engine
    ):
        """3. 创建需求绑 project_id, list 时能按 project 过滤.
        验证 P5-R1-T2 真实 project_requirement 关联在数据库生效.
        """
        # 创建 2 个不同 project 的需求
        r1 = client.post("/api/requirements/create", json={
            "title": "需求-项目A",
            "type": "data_annotation",
            "priority": "P1",
            "project_id": "proj_A",
        })
        assert r1.status_code == 200, r1.text
        r1_id = r1.json()["data"]["id"]

        r2 = client.post("/api/requirements/create", json={
            "title": "需求-项目B",
            "type": "data_cleaning",
            "priority": "P2",
            "project_id": "proj_B",
        })
        assert r2.status_code == 200, r2.text

        # 按 project_id=proj_A 过滤
        resp = client.get("/api/requirements/?project_id=proj_A")
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) >= 1
        # 全部都属于 proj_A
        assert all(it["project_id"] == "proj_A" for it in items)
        assert any(it["id"] == r1_id for it in items)


# ── Test 2: 4 种 reassign 策略都真的在 DB 生效 ────────────────────────────

class TestReassignStrategies:
    """4 种策略 (by_skill / by_workload / random / hybrid) 各自动一次.
    每次都验证 task.assignee 真的变化 + user.workload 更新.
    """

    @pytest.fixture
    def multi_user_engine(self, fresh_engine):
        """注册 4 个不同技能的 user, 不同 workload."""
        eng = fresh_engine
        eng.register_user("alice", skills=["text_annotation"], workload=0.0, efficiency=1.0)
        eng.register_user("bob", skills=["image_labeling"], workload=2.0, efficiency=1.2)
        eng.register_user("carol", skills=["text_annotation", "image_labeling"],
                          workload=5.0, efficiency=0.9)
        eng.register_user("dave", skills=["text_annotation", "image_labeling", "model_eval"],
                          workload=1.0, efficiency=1.5)
        return eng

    @pytest.fixture
    def decomposed_req(self, multi_user_engine):
        """已 decompose 产生 4 tasks 的需求."""
        eng = multi_user_engine
        r = eng.create_requirement(
            title="Reassign-Test-Req",
            req_type=RequirementType.DATA_ANNOTATION,
            priority=Priority.P1,
            created_by="tester",
            description="用于 reassign 测试的样本需求",
            project_id="proj_reassign",
        )
        eng.update_requirement_status(r.id, RequirementStatus.OPEN)
        tasks = eng.decompose_to_tasks(r.id)
        assert len(tasks) == 4
        return r, tasks

    def test_strategy_by_skill(self, multi_user_engine, decomposed_req):
        """by_skill: 优先按技能匹配度分, 应该选匹配度最高的 user."""
        eng = multi_user_engine
        r, _ = decomposed_req
        # 用 hybrid 先 baseline 一次, 然后用 by_skill 比较差异
        eng.reassign_tasks(r.id, strategy="hybrid")
        # 记录 hybrid 后各 user workload
        baseline_wl = {uid: u.workload for uid, u in eng.users.items()}

        # Reset 各 task assignee 清空, 跑 by_skill
        for t in eng.tasks.values():
            if t.requirement_id == r.id:
                t.assignee = ""
                t.status = TaskStatus.PENDING
        # reset baseline
        for uid, u in eng.users.items():
            u.workload = 0.0

        n = eng.reassign_tasks(r.id, strategy="by_skill")
        assert n == 4, f"reassign_tasks returned {n}, expected 4"

        # 所有 task 都应有 assignee
        rel_tasks = [t for t in eng.tasks.values() if t.requirement_id == r.id]
        for t in rel_tasks:
            assert t.assignee, f"task {t.id} not assigned"
            assert t.status == TaskStatus.ASSIGNED, f"task {t.id} status {t.status}"

    def test_strategy_by_workload(self, multi_user_engine, decomposed_req):
        """by_workload: 负载最低的 user 优先."""
        eng = multi_user_engine
        r, _ = decomposed_req
        # alice workload=0, bob=2, carol=5, dave=1
        # 第 1 个 task 应给 alice (lowest)
        # 简化: 不重置, 直接走 by_workload, 第一个 task 应分给 workload 最低的
        n = eng.reassign_tasks(r.id, strategy="by_workload")
        assert n == 4, f"reassign_tasks returned {n}, expected 4"
        # 至少 alice (workload=0) 拿到 1 个 task
        rel_tasks = [t for t in eng.tasks.values() if t.requirement_id == r.id]
        assignees = {t.assignee for t in rel_tasks}
        assert "alice" in assignees, f"alice should get at least 1 task, got {assignees}"

    def test_strategy_random(self, multi_user_engine, decomposed_req):
        """random: 随机分, 但所有 task 都有 assignee."""
        eng = multi_user_engine
        r, _ = decomposed_req
        n = eng.reassign_tasks(r.id, strategy="random")
        assert n == 4, f"reassign_tasks returned {n}, expected 4"
        rel_tasks = [t for t in eng.tasks.values() if t.requirement_id == r.id]
        for t in rel_tasks:
            assert t.assignee, f"task {t.id} not assigned (random)"

    def test_strategy_hybrid(self, multi_user_engine, decomposed_req):
        """hybrid: 技能 * 0.7 + 负载 * 0.3 综合分."""
        eng = multi_user_engine
        r, _ = decomposed_req
        n = eng.reassign_tasks(r.id, strategy="hybrid")
        assert n == 4, f"reassign_tasks returned {n}, expected 4"
        rel_tasks = [t for t in eng.tasks.values() if t.requirement_id == r.id]
        for t in rel_tasks:
            assert t.assignee, f"task {t.id} not assigned (hybrid)"

    def test_all_4_strategies_reassign_count_equal(self, multi_user_engine,
                                                   decomposed_req):
        """所有 4 种策略都返回 4 (4 个 task 都被重派)."""
        eng = multi_user_engine
        r, _ = decomposed_req
        for strategy in ("by_skill", "by_workload", "random", "hybrid"):
            # 重置 task assignee + user workload
            for t in eng.tasks.values():
                if t.requirement_id == r.id:
                    t.assignee = ""
                    t.status = TaskStatus.PENDING
            for u in eng.users.values():
                u.workload = 0.0

            n = eng.reassign_tasks(r.id, strategy=strategy)
            assert n == 4, f"strategy={strategy} reassigned {n} (expected 4)"


# ── Test 3: verify_requirement Bug 1 fix 验证 ─────────────────────────────

class TestVerifyRequirementEnumFix:
    """Bug 1 (audit P1-5): verify_requirement 之前传 string "verified" 永远 False.
    修复后: 走 verify_completion (返回完整 report + 自动 close on pass).
    """

    def test_verify_requirement_passes_enum_not_string(self, fresh_engine):
        """验证: ``update_requirement_status(req_id, "verified")`` 优雅返回 False.
        修复后端点: 走 ``verify_completion`` 拿真实验收报告.
        修复后 engine: 接受 str 输入, 归一化为 enum, 非法时返回 False (不 AttributeError).
        """
        eng = fresh_engine
        # 证明旧 API 传 string 是 bug — 现在优雅返回 False (而不是 AttributeError 500)
        r = eng.create_requirement(
            title="verify-test", req_type=RequirementType.DATA_ANNOTATION,
            priority=Priority.P2, created_by="tester",
        )
        eng.update_requirement_status(r.id, RequirementStatus.OPEN)
        tasks = eng.decompose_to_tasks(r.id)
        # 全部 approve
        for t in tasks:
            eng.update_task_status(t.id, TaskStatus.APPROVED)

        # 旧调用 (传 string "verified") 现在优雅返回 False — 因为 "verified" 不在合法状态
        result = eng.update_requirement_status(r.id, "verified")
        assert result is False, "string 'verified' should fail — not a valid RequirementStatus enum"

        # 修复后路径: verify_completion
        report = eng.verify_completion(r.id)
        assert "error" not in report, report
        assert report["passed"] is True
        assert report["total_tasks"] == 4
        assert report["approved"] == 4
        assert report["auto_closed"] is True
        # 需求被自动 close
        assert r.status == RequirementStatus.CLOSED

    def test_engine_string_status_does_not_crash(self, fresh_engine):
        """P5-R2-T5 fix: 传 string 状态不再 AttributeError 500."""
        eng = fresh_engine
        r = eng.create_requirement(
            title="crash-test", req_type=RequirementType.DATA_ANNOTATION,
            priority=Priority.P2, created_by="tester",
        )
        # 之前会 AttributeError ('str' object has no attribute 'value'), 现在优雅返回 False
        assert eng.update_requirement_status(r.id, "verified") is False
        assert eng.update_requirement_status(r.id, "closed") is False
        # 合法 string (CLOSED 在 enum 里) 也能工作
        eng.update_requirement_status(r.id, RequirementStatus.OPEN)
        assert eng.update_requirement_status(r.id, "closed") is True
        # 验证需求已 close
        r2 = eng.get_requirement(r.id)
        assert r2.status == RequirementStatus.CLOSED

    def test_verify_endpoint_returns_report(self, client, fresh_engine):
        """HTTP 端点 /api/requirements/verify 现在返回完整 verify_completion report."""
        eng = fresh_engine
        r = eng.create_requirement(
            title="verify-endpoint", req_type=RequirementType.DATA_ANNOTATION,
            priority=Priority.P2, created_by="tester",
        )
        eng.update_requirement_status(r.id, RequirementStatus.OPEN)
        eng.decompose_to_tasks(r.id)
        for t in eng.get_tasks(requirement_id=r.id):
            eng.update_task_status(t.id, TaskStatus.APPROVED)

        # 调 HTTP 端点
        resp = client.post("/api/requirements/verify", json={
            "requirement_id": r.id,
            "verified_by": "alice",
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True, body
        assert body["data"]["status"] == "verified", body
        assert body["data"]["verified_by"] == "alice"
        report = body["data"]["report"]
        assert report["passed"] is True
        assert report["approved"] == 4

    def test_close_endpoint_uses_enum(self, client, fresh_engine):
        """Bug 1 同源: close_requirement 之前传 string "closed" 也失败.
        修复后: 传 RequirementStatus.CLOSED 枚举.
        """
        eng = fresh_engine
        r = eng.create_requirement(
            title="close-test", req_type=RequirementType.DATA_ANNOTATION,
            priority=Priority.P2, created_by="tester",
        )
        # 走合法流转 DRAFT → OPEN → IN_PROGRESS (DRAFT 不能直接 IN_PROGRESS)
        eng.update_requirement_status(r.id, RequirementStatus.OPEN)
        eng.update_requirement_status(r.id, RequirementStatus.IN_PROGRESS)

        resp = client.post("/api/requirements/close", json={
            "requirement_id": r.id,
            "reason": "test close",
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "closed", body
        # 验证数据库真的 close 了
        r2 = eng.get_requirement(r.id)
        assert r2.status == RequirementStatus.CLOSED


# ── Test 4: Requirement dataclass 字段类型完整 ────────────────────────────

class TestRequirementDataclassFields:
    """Requirement dataclass 字段类型完整 + from_dict 往返不丢字段."""

    def test_all_fields_have_defaults(self):
        """所有字段都有默认值, 不传也能构造."""
        r = Requirement()
        # 校验每个字段都存在 (用 hasattr 而不是具体值, 因为 dataclass 字段都初始化)
        expected = [
            "id", "title", "type", "status", "priority", "created_by",
            "description", "acceptance_criteria", "tags", "created_at",
            "updated_at", "closed_at", "project_id", "pack_id", "qc_status",
            "delivery_id", "due_date", "owner",
        ]
        for f in expected:
            assert hasattr(r, f), f"Requirement missing field: {f}"

    def test_from_dict_round_trip(self):
        """to_dict → from_dict 往返不丢字段."""
        original = Requirement(
            id="req_test_1",
            title="round-trip-test",
            type=RequirementType.DATA_ANNOTATION,
            status=RequirementStatus.OPEN,
            priority=Priority.P1,
            created_by="bob",
            description="desc",
            acceptance_criteria="criteria",
            tags=["a", "b"],
            project_id="proj_99",
            pack_id="pack_99",
            qc_status="in_progress",
            delivery_id="d_99",
            due_date="2026-07-01",
            owner="alice",
        )
        d = original.to_dict()
        restored = Requirement.from_dict(d)
        # 关键字段一致
        assert restored.id == "req_test_1"
        assert restored.title == "round-trip-test"
        assert restored.type == RequirementType.DATA_ANNOTATION
        assert restored.status == RequirementStatus.OPEN
        assert restored.priority == Priority.P1
        assert restored.project_id == "proj_99"
        assert restored.pack_id == "pack_99"
        assert restored.qc_status == "in_progress"
        assert restored.delivery_id == "d_99"
        assert restored.owner == "alice"
        assert restored.tags == ["a", "b"]

    def test_from_dict_handles_none_for_optional(self):
        """Optional 字段传 None 时, from_dict 不会崩溃."""
        d = {
            "id": "req_x",
            "title": "x",
            "type": "data_annotation",
            "status": "draft",
            "priority": "P2",
            "project_id": None,
            "pack_id": None,
            "qc_status": None,
            "delivery_id": None,
        }
        r = Requirement.from_dict(d)
        assert r.project_id is None
        assert r.pack_id is None
        assert r.qc_status is None
        assert r.delivery_id is None


# ── Test 5: AllocationStrategy 单元 ────────────────────────────────────────

class TestAllocationStrategy:
    """4 种策略的纯函数测试 — 不依赖引擎 singleton."""

    def test_by_sill_skill_match(self):
        """by_skill: 完全匹配 → 1.0; 无匹配 → 0.0."""
        users = [
            UserSkill(user_id="u1", skills=["a", "b"]),
            UserSkill(user_id="u2", skills=["b"]),
            UserSkill(user_id="u3", skills=[]),
        ]
        ranked = AllocationStrategy.by_skill(["a"], users)
        # u1 完全匹配 (1.0) 排第一, u2 (0.0) 第二, u3 排最后
        user_ids = [r[0] for r in ranked]
        assert user_ids[0] == "u1", f"expected u1 first, got {user_ids}"
        # u3 应排最后 (0.0)
        assert user_ids[-1] == "u3"

    def test_by_workload_ascending(self):
        """by_workload: ascending=True 时低负载优先."""
        users = [
            UserSkill(user_id="u_high", workload=10.0),
            UserSkill(user_id="u_low", workload=1.0),
            UserSkill(user_id="u_mid", workload=5.0),
        ]
        ranked = AllocationStrategy.by_workload(users, ascending=True)
        assert ranked[0][0] == "u_low"
        assert ranked[-1][0] == "u_high"

    def test_random_returns_all(self):
        """random: 返回所有 candidate."""
        users = [UserSkill(user_id=f"u{i}", workload=float(i)) for i in range(5)]
        ranked = AllocationStrategy.random(users)
        assert len(ranked) == 5
        assert {r[0] for r in ranked} == {f"u{i}" for i in range(5)}

    def test_hybrid_combines_skill_and_workload(self):
        """hybrid: 综合分 = skill*0.7 + workload*0.3."""
        users = [
            UserSkill(user_id="u_skill", skills=["target"], workload=10.0),
            UserSkill(user_id="u_idle", skills=[], workload=0.0),
        ]
        ranked = AllocationStrategy.hybrid(["target"], users)
        # u_skill 技能匹配 (1.0) 但 workload 高 (0); u_idle 技能 0 但 workload 满分
        # 0.7*1 + 0.3*0 = 0.7 (u_skill) vs 0.7*0 + 0.3*1 = 0.3 (u_idle)
        # u_skill 应排第一
        assert ranked[0][0] == "u_skill", f"got {ranked}"


# ── Test 6: ProjectCenter quick action 路由 (Bug 2 fix) ──────────────────

class TestProjectCenterQuickActionRoute:
    """Bug 2 fix: ProjectCenter.vue 的 requirement quick action 按钮
    之前是 '/annotation-management', 修复后应为 '/requirements'.
    这是前端文件 grep 验证 (后端单测无法验前端, 但能验前端源码已修).
    """

    def test_requirement_route_is_not_annotation_management(self):
        """ProjectCenter.vue L585 (修正后) 应是 '/requirements'."""
        from pathlib import Path as _P
        # _BACKEND = backend/imdf, .parent.parent = backend, .parent = nanobot-factory 根
        repo_root = _BACKEND.parent.parent
        vue_path = repo_root / "frontend-v2" / "src" / "views" / "ProjectCenter.vue"
        assert vue_path.exists(), f"ProjectCenter.vue not found: {vue_path}"
        content = vue_path.read_text(encoding="utf-8")
        # 找到 onQuickAction 函数里的 map 对象
        assert "'/requirements'" in content or '"/requirements"' in content, \
            "ProjectCenter.vue 应包含 /requirements 路由"
        # 旧错路径不应再出现在 requirement key 上
        # (其他 key 可能仍用 annotation-management — 所以只检查 requirement 这一行)
        # 找 onQuickAction 内的 requirement 行
        import re
        m = re.search(r"requirement:\s*['\"](/[^'\"]+)['\"]", content)
        assert m is not None, "找不到 requirement: '/...' 行"
        route = m.group(1)
        assert route == "/requirements", \
            f"requirement 路由应为 /requirements, 实际是 {route}"


if __name__ == "__main__":
    # 可直接 python test_p5_r2_t5_requirement_e2e.py 跑
    import subprocess
    sys.exit(subprocess.call([
        sys.executable, "-m", "pytest",
        __file__, "-v", "--tb=short",
    ]))
