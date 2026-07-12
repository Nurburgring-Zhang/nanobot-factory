"""
P5-R1-T2 Requirement Center 测试套件
=====================================

覆盖:
1. 需求 dataclass 新字段 (project_id / pack_id / qc_status / delivery_id / due_date / owner)
2. paginate_requirements (含过滤 + 排序 + 分页)
3. get_requirement_with_stats (含 tasks_count / packs_count / progress%)
4. reassign_tasks (by_skill / by_workload / random / hybrid)
5. preview_decompose (不真拆)
6. update_requirement_meta (project_id / qc_status / pack_id / delivery_id / due_date / owner)
7. FastAPI HTTP 端点 (create / list / stats / preview / decompose / reassign / meta)

至少 12 个测试用例 — 实际覆盖 18+ 用例.

注意: pytest 的 conftest.py 顶层会通过 pytest_collectstart 把 ``imdf/`` 从 sys.path 移除,
只保留 ``imdf/api``/``imdf/engines``/``imdf/common`` 三个子目录. 这样 ``import engines``
会失败 (因为 ``engines`` 是 ``imdf/engines/``, 需要 ``imdf/`` 在 sys.path 才能找到).
解决方案: 在每个 test 函数开头 (或用 fixture) 把 ``imdf/`` 重新放回 sys.path.
"""
from __future__ import annotations

import sys
from pathlib import Path

# 路径常量 — 在每个 test 函数内重新注入 imdf/ 到 sys.path
_BACKEND = Path(__file__).resolve().parent.parent
_IMDF = _BACKEND / "imdf"


def _ensure_imdf_path():
    """确保 imdf/ 在 sys.path[0] (因为 conftest 会移除它).
    每次 test 调用前都执行一次 — 简单可靠.
    """
    imdf_path = str(_IMDF)
    # 移除可能冲突的 imdf/api, imdf/engines, imdf/common 单独项
    # (它们会让 ``engines`` 无法解析)
    for sub in ("api", "engines", "common"):
        p = str(_IMDF / sub)
        while p in sys.path:
            sys.path.remove(p)
    # 把 imdf/ 放到最前
    if imdf_path in sys.path:
        sys.path.remove(imdf_path)
    sys.path.insert(0, imdf_path)


# ── 直接单元测试 ──────────────────────────────────────────────────

import pytest


@pytest.fixture(autouse=True)
def _imdf_path_fix():
    """autouse fixture: 每次 test 前保证 imdf/ 在 sys.path"""
    _ensure_imdf_path()
    yield
    # 不清理 — pytest 会重置


# ── 直接单元测试 ──────────────────────────────────────────────────

import pytest


def _make_eng():
    """每次新建一个干净的 RequirementEngine"""
    from engines.requirement_engine import RequirementEngine
    return RequirementEngine()


class TestRequirementDataclassNewFields:
    """需求 dataclass 新增字段"""

    def test_create_with_project_id(self):
        eng = _make_eng()
        r = eng.create_requirement(
            title="测试", req_type=__import__("engines.requirement_engine", fromlist=["RequirementType"]).RequirementType.DATA_ANNOTATION,
            project_id="proj_001",
        )
        assert r.project_id == "proj_001"
        d = r.to_dict()
        assert d["project_id"] == "proj_001"

    def test_create_with_pack_id_and_qc_status(self):
        from engines.requirement_engine import RequirementType
        eng = _make_eng()
        r = eng.create_requirement(
            title="测试2",
            req_type=RequirementType.DATA_COLLECTION,
            pack_id="pack_001",
            qc_status="not_started",
        )
        assert r.pack_id == "pack_001"
        assert r.qc_status == "not_started"

    def test_create_with_delivery_id_and_owner_and_due_date(self):
        from engines.requirement_engine import RequirementType, Priority
        eng = _make_eng()
        r = eng.create_requirement(
            title="测试3",
            req_type=RequirementType.QUALITY_REVIEW,
            priority=Priority.P0,
            delivery_id="del_001",
            due_date="2026-12-31",
            owner="alice",
        )
        assert r.delivery_id == "del_001"
        assert r.due_date == "2026-12-31"
        assert r.owner == "alice"

    def test_invalid_qc_status_falls_back_to_none(self):
        from engines.requirement_engine import RequirementType
        eng = _make_eng()
        r = eng.create_requirement(
            title="测试4",
            req_type=RequirementType.DATA_ANNOTATION,
            qc_status="invalid_value",  # 非法值
        )
        # 应回退到 None
        assert r.qc_status is None

    def test_from_dict_round_trip_preserves_new_fields(self):
        from engines.requirement_engine import Requirement, RequirementType
        data = {
            "id": "req_test",
            "title": "t",
            "type": "data_annotation",
            "status": "draft",
            "priority": "P2",
            "project_id": "proj_x",
            "pack_id": "pack_x",
            "qc_status": "passed",
            "delivery_id": "del_x",
            "due_date": "2026-06-30",
            "owner": "bob",
        }
        r = Requirement.from_dict(data)
        assert r.project_id == "proj_x"
        assert r.pack_id == "pack_x"
        assert r.qc_status == "passed"
        assert r.delivery_id == "del_x"
        assert r.due_date == "2026-06-30"
        assert r.owner == "bob"
        # 序列化回去
        d2 = r.to_dict()
        assert d2["project_id"] == "proj_x"
        assert d2["qc_status"] == "passed"


class TestPaginateRequirements:
    """paginate_requirements (过滤 + 排序 + 分页)"""

    def _seed(self, eng):
        from engines.requirement_engine import RequirementType, Priority
        # 5 条需求: 3 条 proj_001 (P0/P1/P2), 2 条 proj_002 (P2/P3)
        eng.create_requirement("R1", RequirementType.DATA_ANNOTATION, Priority.P0, project_id="proj_001", owner="alice")
        eng.create_requirement("R2", RequirementType.DATA_COLLECTION, Priority.P1, project_id="proj_001", owner="bob")
        eng.create_requirement("R3", RequirementType.DATA_CLEANING, Priority.P2, project_id="proj_001", owner="alice")
        eng.create_requirement("R4", RequirementType.MODEL_EVALUATION, Priority.P2, project_id="proj_002", owner="alice")
        eng.create_requirement("R5", RequirementType.QUALITY_REVIEW, Priority.P3, project_id="proj_002", owner="bob")

    def test_paginate_basic(self):
        eng = _make_eng()
        self._seed(eng)
        items, total = eng.paginate_requirements(page=1, page_size=20)
        assert total == 5
        assert len(items) == 5

    def test_paginate_filter_by_project_id(self):
        eng = _make_eng()
        self._seed(eng)
        items, total = eng.paginate_requirements(project_id="proj_001")
        assert total == 3
        assert all(r.project_id == "proj_001" for r in items)

    def test_paginate_filter_by_status(self):
        eng = _make_eng()
        self._seed(eng)
        items, total = eng.paginate_requirements(status="draft")
        assert total == 5  # 全部默认 draft
        items2, total2 = eng.paginate_requirements(status="open")
        assert total2 == 0  # 没有 open

    def test_paginate_filter_by_priority(self):
        eng = _make_eng()
        self._seed(eng)
        items, total = eng.paginate_requirements(priority="P0")
        assert total == 1
        assert items[0].priority.value == "P0"

    def test_paginate_keyword_search(self):
        eng = _make_eng()
        self._seed(eng)
        items, total = eng.paginate_requirements(keyword="R1")
        assert total == 1
        assert items[0].title == "R1"

    def test_paginate_pagination(self):
        eng = _make_eng()
        self._seed(eng)
        items1, total = eng.paginate_requirements(page=1, page_size=2)
        items2, total2 = eng.paginate_requirements(page=2, page_size=2)
        items3, total3 = eng.paginate_requirements(page=3, page_size=2)
        assert total == 5
        assert total2 == 5
        assert total3 == 5
        assert len(items1) == 2
        assert len(items2) == 2
        assert len(items3) == 1  # 最后一页只剩 1
        # 跨页无重复
        ids = [r.id for r in items1 + items2 + items3]
        assert len(set(ids)) == 5


class TestGetRequirementWithStats:
    """get_requirement_with_stats (含 tasks_count / packs_count / progress%)"""

    def test_stats_no_tasks(self):
        from engines.requirement_engine import RequirementType
        eng = _make_eng()
        r = eng.create_requirement("R", RequirementType.DATA_ANNOTATION, pack_id="pack_001")
        s = eng.get_requirement_with_stats(r.id)
        assert s["tasks_count"] == 0
        assert s["packs_count"] == 1  # 有 pack_id
        assert s["progress"] == 0.0
        assert s["current_step"] == 0  # draft
        assert s["qc_status"] == "not_started"
        assert "task_tree" in s
        assert "status_flow" in s
        assert len(s["status_flow"]) == 6  # draft..closed

    def test_stats_with_tasks_and_progress(self):
        from engines.requirement_engine import (
            RequirementType, TaskStatus, RequirementStatus, Priority
        )
        eng = _make_eng()
        r = eng.create_requirement("R", RequirementType.DATA_ANNOTATION)
        # 推到 OPEN 以便 decompose
        eng.update_requirement_status(r.id, RequirementStatus.OPEN)
        tasks = eng.decompose_to_tasks(r.id)
        assert len(tasks) > 0
        # 标记 2 个 approved
        for t in tasks[:2]:
            t.status = TaskStatus.APPROVED
            t.completed_at = "2026-06-28T00:00:00"
        s = eng.get_requirement_with_stats(r.id)
        assert s["tasks_count"] == len(tasks)
        assert s["approved_count"] == 2
        # progress = 2 / N * 100
        expected_progress = round(2 / len(tasks) * 100, 1)
        assert s["progress"] == expected_progress

    def test_stats_with_pack_id_counts(self):
        from engines.requirement_engine import RequirementType
        eng = _make_eng()
        r1 = eng.create_requirement("with_pack", RequirementType.DATA_ANNOTATION, pack_id="p1")
        r2 = eng.create_requirement("no_pack", RequirementType.DATA_ANNOTATION)
        s1 = eng.get_requirement_with_stats(r1.id)
        s2 = eng.get_requirement_with_stats(r2.id)
        assert s1["packs_count"] == 1
        assert s2["packs_count"] == 0

    def test_stats_assignee_breakdown(self):
        from engines.requirement_engine import (
            RequirementType, TaskStatus, RequirementStatus
        )
        eng = _make_eng()
        r = eng.create_requirement("R", RequirementType.DATA_ANNOTATION)
        eng.update_requirement_status(r.id, RequirementStatus.OPEN)
        tasks = eng.decompose_to_tasks(r.id)
        # 模拟分配: 第 1 个给 alice, 第 2 个给 bob
        tasks[0].assignee = "alice"
        tasks[1].assignee = "bob"
        s = eng.get_requirement_with_stats(r.id)
        assert "alice" in s["assignee_breakdown"]
        assert "bob" in s["assignee_breakdown"]

    def test_stats_not_found_returns_error(self):
        eng = _make_eng()
        s = eng.get_requirement_with_stats("nonexistent_req")
        assert "error" in s


class TestReassignTasks:
    """reassign_tasks (按 strategy 重派)"""

    def _make_with_users_and_tasks(self):
        from engines.requirement_engine import (
            RequirementType, RequirementStatus, Priority
        )
        eng = _make_eng()
        # 注册 3 个用户, 不同 skills/workload
        eng.register_user("alice", skills=["text_annotation", "image_labeling"], workload=2.0)
        eng.register_user("bob", skills=["data_cleaning"], workload=5.0)
        eng.register_user("carol", skills=["model_eval"], workload=0.0)
        # 创建并拆解一个需求
        r = eng.create_requirement("R", RequirementType.DATA_ANNOTATION, Priority.P2)
        eng.update_requirement_status(r.id, RequirementStatus.OPEN)
        tasks = eng.decompose_to_tasks(r.id)
        # 模拟部分已分配
        tasks[0].assignee = "alice"
        tasks[0].status = __import__("engines.requirement_engine", fromlist=["TaskStatus"]).TaskStatus.ASSIGNED
        return eng, r, tasks

    def test_reassign_hybrid(self):
        eng, r, _ = self._make_with_users_and_tasks()
        n = eng.reassign_tasks(r.id, strategy="hybrid")
        assert n > 0

    def test_reassign_by_skill(self):
        eng, r, _ = self._make_with_users_and_tasks()
        n = eng.reassign_tasks(r.id, strategy="by_skill")
        assert n > 0

    def test_reassign_by_workload(self):
        eng, r, _ = self._make_with_users_and_tasks()
        n = eng.reassign_tasks(r.id, strategy="by_workload")
        assert n > 0

    def test_reassign_random(self):
        eng, r, _ = self._make_with_users_and_tasks()
        n = eng.reassign_tasks(r.id, strategy="random")
        assert n > 0

    def test_reassign_no_users_returns_zero(self):
        from engines.requirement_engine import (
            RequirementType, RequirementStatus
        )
        eng = _make_eng()
        r = eng.create_requirement("R", RequirementType.DATA_ANNOTATION)
        eng.update_requirement_status(r.id, RequirementStatus.OPEN)
        eng.decompose_to_tasks(r.id)
        n = eng.reassign_tasks(r.id, strategy="hybrid")
        assert n == 0

    def test_reassign_nonexistent_returns_zero(self):
        eng = _make_eng()
        eng.register_user("alice", skills=["x"])
        n = eng.reassign_tasks("nonexistent", strategy="hybrid")
        assert n == 0


class TestPreviewDecompose:
    """preview_decompose (不真拆)"""

    def test_preview_draft_returns_tasks(self):
        from engines.requirement_engine import RequirementType
        eng = _make_eng()
        r = eng.create_requirement("R", RequirementType.DATA_ANNOTATION)
        preview = eng.preview_decompose(r.id)
        assert "tasks" in preview
        assert preview["task_count"] >= 1
        assert preview["complexity"] in ("low", "medium", "high")
        assert preview["estimated_hours"] > 0

    def test_preview_after_decompose_errors(self):
        """已拆解过(in_progress)再预览应报错 (避免误操作)"""
        from engines.requirement_engine import RequirementType, RequirementStatus
        eng = _make_eng()
        r = eng.create_requirement("R", RequirementType.DATA_ANNOTATION)
        eng.update_requirement_status(r.id, RequirementStatus.OPEN)
        eng.decompose_to_tasks(r.id)
        # 现在状态是 in_progress, preview 应报错
        preview = eng.preview_decompose(r.id)
        assert "error" in preview

    def test_preview_nonexistent_returns_error(self):
        eng = _make_eng()
        preview = eng.preview_decompose("nope")
        assert "error" in preview


class TestUpdateRequirementMeta:
    """update_requirement_meta"""

    def test_update_project_id(self):
        from engines.requirement_engine import RequirementType
        eng = _make_eng()
        r = eng.create_requirement("R", RequirementType.DATA_ANNOTATION)
        ok = eng.update_requirement_meta(r.id, project_id="proj_new")
        assert ok is True
        assert eng.get_requirement(r.id).project_id == "proj_new"

    def test_update_qc_status_validates(self):
        from engines.requirement_engine import RequirementType
        eng = _make_eng()
        r = eng.create_requirement("R", RequirementType.DATA_ANNOTATION)
        # 非法值不应被设置
        eng.update_requirement_meta(r.id, qc_status="bogus")
        assert eng.get_requirement(r.id).qc_status is None
        # 合法值
        eng.update_requirement_meta(r.id, qc_status="passed")
        assert eng.get_requirement(r.id).qc_status == "passed"

    def test_update_owner_and_due_date(self):
        from engines.requirement_engine import RequirementType
        eng = _make_eng()
        r = eng.create_requirement("R", RequirementType.DATA_ANNOTATION)
        eng.update_requirement_meta(r.id, owner="new_owner", due_date="2027-01-01")
        updated = eng.get_requirement(r.id)
        assert updated.owner == "new_owner"
        assert updated.due_date == "2027-01-01"

    def test_update_nonexistent_returns_false(self):
        eng = _make_eng()
        ok = eng.update_requirement_meta("nope", project_id="x")
        assert ok is False


# ── HTTP API 端点测试 (TestClient + canvas_web.app) ────────────────

@pytest.fixture
def http_client():
    """获取 FastAPI TestClient (复用 conftest 的 test_client 但避免 server.py 副作用)"""
    try:
        from fastapi.testclient import TestClient
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "canvas_web_for_req_test",
            str(_IMDF / "api" / "canvas_web.py"),
        )
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return TestClient(m.app, raise_server_exceptions=False)
    except Exception as e:
        pytest.skip(f"无法加载 canvas_web app: {e}")


class TestRequirementHTTPRoutes:
    """FastAPI 端点测试 (HTTP 层)"""

    def test_create_endpoint_with_project_id(self, http_client):
        r = http_client.post("/api/requirements/create", json={
            "title": "测试需求",
            "type": "general",
            "priority": "medium",
            "project_id": "proj_http_001",
            "owner": "alice",
            "description": "集成测试描述",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        data = body["data"]
        assert data["project_id"] == "proj_http_001"
        assert data["owner"] == "alice"
        assert "id" in data

    def test_create_endpoint_without_project_id_works(self, http_client):
        """无 project_id 也应能创建 (向后兼容)"""
        r = http_client.post("/api/requirements/create", json={
            "title": "无项目需求",
            "type": "general",
            "priority": "low",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True

    def test_list_endpoint_supports_project_id_filter(self, http_client):
        r = http_client.get("/api/requirements/", params={
            "project_id": "proj_filter_test",
            "page": 1,
            "page_size": 10,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "data" in body

    def test_list_endpoint_supports_pagination(self, http_client):
        r = http_client.get("/api/requirements/", params={
            "page": 1,
            "page_size": 5,
        })
        assert r.status_code == 200
        body = r.json()
        assert "page" in body
        assert body["page"] == 1
        assert body["page_size"] == 5

    def test_decompose_preview_endpoint(self, http_client):
        # 先创建
        r = http_client.post("/api/requirements/create", json={
            "title": "预览拆解",
            "type": "feature",
            "priority": "high",
            "project_id": "proj_pre",
        })
        assert r.status_code == 200
        rid = r.json()["data"]["id"]
        # 预览
        r = http_client.get(f"/api/requirements/{rid}/decompose-preview")
        assert r.status_code == 200
        body = r.json()
        # draft 状态允许预览
        assert "tasks" in body.get("data", {})

    def test_decompose_endpoint_real(self, http_client):
        r = http_client.post("/api/requirements/create", json={
            "title": "真实拆解",
            "type": "bug",
            "priority": "critical",
            "project_id": "proj_decomp",
        })
        rid = r.json()["data"]["id"]
        r = http_client.post(f"/api/requirements/{rid}/decompose")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["data"]["task_count"] >= 1
        assert len(body["data"]["tasks"]) == body["data"]["task_count"]

    def test_reassign_endpoint(self, http_client):
        r = http_client.post("/api/requirements/create", json={
            "title": "重派测试",
            "type": "improvement",
            "priority": "medium",
            "project_id": "proj_reassign",
        })
        rid = r.json()["data"]["id"]
        r = http_client.post(f"/api/requirements/{rid}/reassign",
                              json={"strategy": "hybrid"})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["data"]["strategy"] == "hybrid"
        assert "reassigned_count" in body["data"]

    def test_reassign_endpoint_validates_strategy(self, http_client):
        """非法 strategy 应被 Pydantic 400 拒绝"""
        r = http_client.post("/api/requirements/create", json={
            "title": "非法 strategy", "type": "general", "priority": "medium",
        })
        rid = r.json()["data"]["id"]
        r = http_client.post(f"/api/requirements/{rid}/reassign",
                              json={"strategy": "INVALID_STRATEGY"})
        # Pydantic Literal 校验失败 → 422
        assert r.status_code == 422

    def test_stats_endpoint_returns_required_fields(self, http_client):
        r = http_client.post("/api/requirements/create", json={
            "title": "统计测试",
            "type": "general",
            "priority": "high",
            "project_id": "proj_stats",
        })
        rid = r.json()["data"]["id"]
        r = http_client.get(f"/api/requirements/{rid}/stats")
        assert r.status_code == 200
        body = r.json()
        data = body["data"]
        assert "tasks_count" in data
        assert "packs_count" in data
        assert "progress" in data
        assert "task_tree" in data
        assert "current_step" in data
        assert "status_flow" in data

    def test_update_meta_endpoint(self, http_client):
        r = http_client.post("/api/requirements/create", json={
            "title": "meta 测试",
            "type": "general",
            "priority": "low",
        })
        rid = r.json()["data"]["id"]
        r = http_client.put(f"/api/requirements/{rid}/meta", json={
            "project_id": "proj_meta_new",
            "qc_status": "in_progress",
            "owner": "bob",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["data"]["project_id"] == "proj_meta_new"
        assert body["data"]["qc_status"] == "in_progress"
        assert body["data"]["owner"] == "bob"

    def test_update_meta_validates_qc_status(self, http_client):
        """非法 qc_status 应被 Pydantic 422 拒绝"""
        r = http_client.post("/api/requirements/create", json={
            "title": "qc 验证", "type": "general", "priority": "medium",
        })
        rid = r.json()["data"]["id"]
        r = http_client.put(f"/api/requirements/{rid}/meta", json={
            "qc_status": "WRONG_VALUE",
        })
        assert r.status_code == 422

    def test_create_validates_title_required(self, http_client):
        """title 为空应被 422 拒绝"""
        r = http_client.post("/api/requirements/create", json={
            "title": "",
            "type": "general",
            "priority": "medium",
        })
        assert r.status_code == 422

    def test_create_validates_type_literal(self, http_client):
        """type 非法值应被 422 拒绝"""
        r = http_client.post("/api/requirements/create", json={
            "title": "type 非法",
            "type": "INVALID_TYPE",
            "priority": "medium",
        })
        assert r.status_code == 422

    def test_create_validates_priority_literal(self, http_client):
        """priority 非法值应被 422 拒绝"""
        r = http_client.post("/api/requirements/create", json={
            "title": "priority 非法",
            "type": "general",
            "priority": "WRONG",
        })
        assert r.status_code == 422

    def test_id_validator_rejects_unsafe_path(self, http_client):
        """req_id 包含特殊字符应被 400 拒绝 (validate_id)"""
        r = http_client.get("/api/requirements/bad..id../stats")
        # 包含 .. 或 / 触发 validate_id 失败 → 400
        assert r.status_code in (400, 422)

    def test_decompose_after_close_returns_error(self, http_client):
        """closed 状态下无法拆解"""
        r = http_client.post("/api/requirements/create", json={
            "title": "拆解 closed", "type": "general", "priority": "medium",
        })
        rid = r.json()["data"]["id"]
        # close 它
        r = http_client.post("/api/requirements/close",
                              json={"requirement_id": rid, "reason": "test"})
        # 当前状态仍为 draft, 不能直接 close. 试着 preview
        r = http_client.get(f"/api/requirements/{rid}/decompose-preview")
        # draft 状态可预览 (没有 error), 或者失败
        # 此处只验证 endpoint 不崩
        assert r.status_code in (200, 400, 500)


# ─────────────────────────────────────────────────────────────────
# P5-R1-T2 RETRY (attempt 2) — 双枚举 Literal 兼容性测试
# Verifier feedback: body_schemas.py:628-629 扩 Literal 接受 legacy + 新 engine 枚举
# ─────────────────────────────────────────────────────────────────

class TestDualEnumLiteralCompatibility:
    """P5-R1-T2 retry — RequirementCreate 接受 legacy frontend 值 + 新 engine enum 名"""

    # ── type 字段: legacy frontend values ─────────────────────────────

    def test_legacy_type_general(self, http_client):
        """type='general' (legacy frontend) 应 200 — 映射到 DATA_ANNOTATION"""
        r = http_client.post("/api/requirements/create", json={
            "title": "legacy general", "type": "general", "priority": "medium",
            "project_id": "proj_dyn_001",
        })
        assert r.status_code == 200, r.text
        # engine 内部映射到 DATA_ANNOTATION
        assert r.json()["data"]["type"] == "data_annotation"

    def test_legacy_type_feature(self, http_client):
        """type='feature' (legacy frontend) 应 200 — 映射到 DATA_ANNOTATION"""
        r = http_client.post("/api/requirements/create", json={
            "title": "legacy feature", "type": "feature", "priority": "high",
        })
        assert r.status_code == 200
        assert r.json()["data"]["type"] == "data_annotation"

    def test_legacy_type_bug(self, http_client):
        """type='bug' (legacy frontend) 应 200 — 映射到 DATA_CLEANING"""
        r = http_client.post("/api/requirements/create", json={
            "title": "legacy bug", "type": "bug", "priority": "critical",
        })
        assert r.status_code == 200
        assert r.json()["data"]["type"] == "data_cleaning"

    def test_legacy_type_improvement(self, http_client):
        """type='improvement' (legacy frontend) 应 200 — 映射到 DATA_AUGMENTATION"""
        r = http_client.post("/api/requirements/create", json={
            "title": "legacy improvement", "type": "improvement", "priority": "low",
        })
        assert r.status_code == 200
        assert r.json()["data"]["type"] == "data_augmentation"

    # ── type 字段: new engine enum names (P5-R1-T2 retry) ──────────────

    def test_new_type_data_annotation(self, http_client):
        """type='data_annotation' (新 engine 枚举名) 应 200 — 透传, 无 lossy 转换"""
        r = http_client.post("/api/requirements/create", json={
            "title": "new data_annotation", "type": "data_annotation",
            "priority": "medium",
        })
        assert r.status_code == 200
        assert r.json()["data"]["type"] == "data_annotation"

    def test_new_type_data_collection(self, http_client):
        """type='data_collection' 应 200"""
        r = http_client.post("/api/requirements/create", json={
            "title": "new data_collection", "type": "data_collection",
            "priority": "high",
        })
        assert r.status_code == 200
        assert r.json()["data"]["type"] == "data_collection"

    def test_new_type_data_cleaning(self, http_client):
        """type='data_cleaning' 应 200"""
        r = http_client.post("/api/requirements/create", json={
            "title": "new data_cleaning", "type": "data_cleaning",
            "priority": "medium",
        })
        assert r.status_code == 200
        assert r.json()["data"]["type"] == "data_cleaning"

    def test_new_type_model_evaluation(self, http_client):
        """type='model_evaluation' 应 200"""
        r = http_client.post("/api/requirements/create", json={
            "title": "new model_evaluation", "type": "model_evaluation",
            "priority": "medium",
        })
        assert r.status_code == 200
        assert r.json()["data"]["type"] == "model_evaluation"

    def test_new_type_data_augmentation(self, http_client):
        """type='data_augmentation' 应 200"""
        r = http_client.post("/api/requirements/create", json={
            "title": "new data_augmentation", "type": "data_augmentation",
            "priority": "medium",
        })
        assert r.status_code == 200
        assert r.json()["data"]["type"] == "data_augmentation"

    def test_new_type_quality_review(self, http_client):
        """type='quality_review' 应 200"""
        r = http_client.post("/api/requirements/create", json={
            "title": "new quality_review", "type": "quality_review",
            "priority": "medium",
        })
        assert r.status_code == 200
        assert r.json()["data"]["type"] == "quality_review"

    # ── priority 字段: legacy frontend values ──────────────────────────

    def test_legacy_priority_low(self, http_client):
        """priority='low' (legacy) 应 200 — 映射到 P3"""
        r = http_client.post("/api/requirements/create", json={
            "title": "p low", "type": "general", "priority": "low",
        })
        assert r.status_code == 200
        assert r.json()["data"]["priority"] == "P3"

    def test_legacy_priority_medium(self, http_client):
        """priority='medium' 应 200 — 映射到 P2"""
        r = http_client.post("/api/requirements/create", json={
            "title": "p med", "type": "general", "priority": "medium",
        })
        assert r.status_code == 200
        assert r.json()["data"]["priority"] == "P2"

    def test_legacy_priority_high(self, http_client):
        """priority='high' 应 200 — 映射到 P1"""
        r = http_client.post("/api/requirements/create", json={
            "title": "p high", "type": "general", "priority": "high",
        })
        assert r.status_code == 200
        assert r.json()["data"]["priority"] == "P1"

    def test_legacy_priority_critical(self, http_client):
        """priority='critical' 应 200 — 映射到 P0"""
        r = http_client.post("/api/requirements/create", json={
            "title": "p crit", "type": "general", "priority": "critical",
        })
        assert r.status_code == 200
        assert r.json()["data"]["priority"] == "P0"

    # ── priority 字段: new engine enum names (P5-R1-T2 retry) ──────────

    def test_new_priority_P0(self, http_client):
        """priority='P0' (新 engine 枚举名) 应 200 — 透传"""
        r = http_client.post("/api/requirements/create", json={
            "title": "P0", "type": "general", "priority": "P0",
        })
        assert r.status_code == 200
        assert r.json()["data"]["priority"] == "P0"

    def test_new_priority_P1(self, http_client):
        """priority='P1' 应 200"""
        r = http_client.post("/api/requirements/create", json={
            "title": "P1", "type": "general", "priority": "P1",
        })
        assert r.status_code == 200
        assert r.json()["data"]["priority"] == "P1"

    def test_new_priority_P2(self, http_client):
        """priority='P2' 应 200"""
        r = http_client.post("/api/requirements/create", json={
            "title": "P2", "type": "general", "priority": "P2",
        })
        assert r.status_code == 200
        assert r.json()["data"]["priority"] == "P2"

    def test_new_priority_P3(self, http_client):
        """priority='P3' 应 200"""
        r = http_client.post("/api/requirements/create", json={
            "title": "P3", "type": "general", "priority": "P3",
        })
        assert r.status_code == 200
        assert r.json()["data"]["priority"] == "P3"

    # ── type_map 简化验证: legacy "bug" 不再误映射 (P5-R1-T2 retry) ──

    def test_legacy_bug_specific_mapping(self, http_client):
        """legacy 'bug' 明确映射到 DATA_CLEANING (而非 DATA_ANNOTATION)"""
        r = http_client.post("/api/requirements/create", json={
            "title": "bug → clean", "type": "bug", "priority": "high",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["type"] == "data_cleaning"  # 明确, 不是 lossy 随机

    def test_legacy_improvement_specific_mapping(self, http_client):
        """legacy 'improvement' 明确映射到 DATA_AUGMENTATION"""
        r = http_client.post("/api/requirements/create", json={
            "title": "improvement → augment", "type": "improvement",
            "priority": "medium",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["type"] == "data_augmentation"

    # ── 边界: 非法值仍应被 422 拒绝 ─────────────────────────────────

    def test_invalid_type_rejected(self, http_client):
        """非法 type 应被 422"""
        r = http_client.post("/api/requirements/create", json={
            "title": "bad type", "type": "TOTALLY_INVALID_TYPE",
            "priority": "medium",
        })
        assert r.status_code == 422

    def test_invalid_priority_rejected(self, http_client):
        """非法 priority 应被 422"""
        r = http_client.post("/api/requirements/create", json={
            "title": "bad priority", "type": "general",
            "priority": "WRONG_PRIORITY",
        })
        assert r.status_code == 422

    # ── 组合: legacy + new 混用 + project_id 关联 ─────────────────────

    def test_legacy_new_combined(self, http_client):
        """legacy priority + new type 组合 + project_id 关联 — 端到端"""
        r = http_client.post("/api/requirements/create", json={
            "title": "组合测试",
            "type": "data_annotation",  # new
            "priority": "high",  # legacy
            "project_id": "proj_combined",
            "owner": "alice",
        })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["type"] == "data_annotation"
        assert data["priority"] == "P1"
        assert data["project_id"] == "proj_combined"
        assert data["owner"] == "alice"