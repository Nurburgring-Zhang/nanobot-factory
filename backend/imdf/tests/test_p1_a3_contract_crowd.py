"""P1-A3-W2: 节点契约校验 + 众包结算 测试套件

目标: ≥ 22 用例
- Contract:  10 用例 (单测引擎 + 路由)
- Crowd:     12 用例 (单测引擎 + 路由)

覆盖:
  Contract (10):
   1. register_node 存储契约
   2. validate_inputs 通过
   3. validate_inputs 失败 (缺字段)
   4. validate_inputs 失败 (类型错)
   5. validate_outputs 通过
   6. validate_outputs 失败
   7. validate_workflow 通过
   8. validate_workflow 失败 (节点类型不兼容)
   9. 未注册节点 → 404
  10. 复杂 workflow 嵌套

  Crowd (12):
   1. price_task 返回合理范围
   2. 难度 +1 价格 +20%
   3. 截止时间紧价格 +30%
   4. lock_price 锁定后 price 不变
   5. settle passed=True 钱包增加
   6. settle passed=False 钱包不变
   7. 重复 settle 幂等
   8. withdraw 申请扣减钱包
   9. 提现 > 余额 → 422
  10. 提现历史记录
  11. 跨 worker 钱包隔离
  12. 提现 ≤ 0 → 422
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── Path setup ─────────────────────────────────────────────────────────
# 重要: backend/ 下另有 api/ 包, 会与 backend/imdf/api/ 冲突.
# conftest.py 把 imdf/ 加到 sys.path 但位置在 backend/ 之后,
# 导致 `import api` 解析到 backend/api/__init__.py 而非 imdf/api/.
# 这里移除 backend/ 并把 imdf/ 强制放到 sys.path[0] 解决冲突.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
_IMDF_ROOT = _BACKEND_ROOT / "imdf"
sys.path[:] = [p for p in sys.path if str(_BACKEND_ROOT) != p]
if str(_IMDF_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMDF_ROOT))

from engines.contract_validator import ContractValidator, register_preset_nodes, PRESET_NODES  # noqa: E402
from engines.crowd_settlement import CrowdSettlementEngine  # noqa: E402

# Lazy imports for API routers (TestClient fixtures)
# 必须在 sys.path 修正之后导入
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
try:
    from api.workflow_contract import router as contract_router  # noqa: E402
    from api.crowd_settlement import router as crowd_router  # noqa: E402
    _API_IMPORT_OK = True
except ModuleNotFoundError as _e:
    _API_IMPORT_OK = False
    _API_IMPORT_ERR = str(_e)


# ──────────────────────────────────────────────────────────────────────────
# Contract Validator — Engine unit tests (10)
# ──────────────────────────────────────────────────────────────────────────

class TestContractValidatorEngine:
    """直接测 ContractValidator 类 (10 用例)."""

    def _make_validator(self) -> ContractValidator:
        v = ContractValidator()
        v.register_node(
            "img_gen",
            inputs={
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {"type": "string", "minLength": 1, "maxLength": 1000},
                    "width": {"type": "integer", "min": 64, "max": 4096},
                },
            },
            outputs={
                "type": "object",
                "required": ["image"],
                "properties": {
                    "image": {"type": "string"},
                    "metadata": {"type": "object"},
                },
            },
        )
        v.register_node(
            "img_edit",
            inputs={
                "type": "object",
                "required": ["image", "instruction"],
                "properties": {
                    "image": {"type": "string"},
                    "instruction": {"type": "string", "minLength": 1},
                    "strength": {"type": "number", "min": 0.0, "max": 1.0},
                },
            },
            outputs={
                "type": "object",
                "required": ["image"],
                "properties": {
                    "image": {"type": "string"},
                },
            },
        )
        v.register_node(
            "tts",
            inputs={
                "type": "object",
                "required": ["text"],
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "voice": {"type": "string"},
                },
            },
            outputs={
                "type": "object",
                "required": ["audio"],
                "properties": {
                    "audio": {"type": "string"},
                    # 不输出 "image" — 与 img_edit image 字段类型不冲突 (都是 string), 但字段名差异
                },
            },
        )
        return v

    # 1. register_node 存储契约
    def test_register_node_stores_schema(self):
        v = ContractValidator()
        v.register_node(
            "n1",
            inputs={"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}},
            outputs={"type": "object", "required": ["y"], "properties": {"y": {"type": "integer"}}},
            description="test node",
        )
        entry = v.get_node("n1")
        assert entry is not None
        assert entry["node_id"] == "n1"
        assert "x" in entry["inputs"]["properties"]
        assert "y" in entry["outputs"]["properties"]
        assert entry["description"] == "test node"
        assert "n1" in v.list_nodes()

    # 2. validate_inputs 通过
    def test_validate_inputs_ok(self):
        v = self._make_validator()
        ok, msg = v.validate_inputs("img_gen", {"prompt": "cat", "width": 1024})
        assert ok is True
        assert msg == "ok"

    # 3. validate_inputs 失败 (缺字段)
    def test_validate_inputs_missing_required(self):
        v = self._make_validator()
        ok, msg = v.validate_inputs("img_gen", {})
        assert ok is False
        assert "prompt" in msg
        assert "required" in msg.lower() or "missing" in msg.lower()

    # 4. validate_inputs 失败 (类型错)
    def test_validate_inputs_type_mismatch(self):
        v = self._make_validator()
        ok, msg = v.validate_inputs("img_gen", {"prompt": "cat", "width": "not_a_number"})
        assert ok is False
        assert "width" in msg
        assert "integer" in msg or "type" in msg.lower()

    # 5. validate_outputs 通过
    def test_validate_outputs_ok(self):
        v = self._make_validator()
        ok, msg = v.validate_outputs("img_gen", {"image": "http://x/y.png", "metadata": {}})
        assert ok is True
        assert msg == "ok"

    # 6. validate_outputs 失败
    def test_validate_outputs_missing(self):
        v = self._make_validator()
        ok, msg = v.validate_outputs("img_gen", {"metadata": {}})
        assert ok is False
        assert "image" in msg

    # 7. validate_workflow 通过
    def test_validate_workflow_ok(self):
        v = self._make_validator()
        workflow = {
            "nodes": [
                {"id": "n1", "type": "img_gen", "inputs": {"prompt": "cat"}},
                {"id": "n2", "type": "img_edit", "inputs": {"image": "x.png", "instruction": "blur"}},
            ],
            "edges": [{"source": "n1", "target": "n2"}],
        }
        ok, errors = v.validate_workflow(workflow)
        assert ok is True
        assert errors == []

    # 8. validate_workflow 失败 (节点类型不兼容 + 未注册类型)
    def test_validate_workflow_type_incompatible(self):
        v = self._make_validator()
        # 子用例 A: source output 字段类型与 target input 字段类型不兼容
        # 注册两个节点, 一个输出 'data' (integer), 一个需要 'data' (string)
        v.register_node(
            "int_producer",
            inputs={"type": "object", "properties": {}},
            outputs={
                "type": "object",
                "required": ["data"],
                "properties": {"data": {"type": "integer"}},
            },
        )
        v.register_node(
            "str_consumer",
            inputs={
                "type": "object",
                "required": ["data"],
                "properties": {"data": {"type": "string"}},
            },
            outputs={"type": "object", "properties": {}},
        )
        wf_incompat = {
            "nodes": [
                {"id": "p", "type": "int_producer", "inputs": {}},
                {"id": "c", "type": "str_consumer", "inputs": {"data": "x"}},
            ],
            "edges": [{"source": "p", "target": "c"}],
        }
        ok, errors = v.validate_workflow(wf_incompat)
        assert ok is False
        assert any("type mismatch" in e for e in errors), errors

        # 子用例 B: 节点 type 未注册
        wf_unreg = {
            "nodes": [
                {"id": "x", "type": "unknown_node_type", "inputs": {}},
                {"id": "y", "type": "tts", "inputs": {"text": "hi"}},
            ],
            "edges": [{"source": "x", "target": "y"}],
        }
        ok2, errors2 = v.validate_workflow(wf_unreg)
        assert ok2 is False
        assert any("not registered" in e for e in errors2), errors2

    # 9. 未注册节点 → False
    def test_unregistered_node(self):
        v = self._make_validator()
        ok, msg = v.validate_inputs("does_not_exist", {"prompt": "x"})
        assert ok is False
        assert "not registered" in msg

    # 10. 复杂 workflow 嵌套 (嵌套 object properties 校验)
    def test_complex_workflow_nested_schema(self):
        v = ContractValidator()
        v.register_node(
            "complex_in",
            inputs={
                "type": "object",
                "required": ["config"],
                "properties": {
                    "config": {
                        "type": "object",
                        "required": ["model_name"],
                        "properties": {
                            "model_name": {"type": "string", "enum": ["a", "b", "c"]},
                            "batch_size": {"type": "integer", "min": 1, "max": 64},
                        },
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id"],
                            "properties": {
                                "id": {"type": "string"},
                                "score": {"type": "number", "min": 0.0, "max": 1.0},
                            },
                        },
                        "minItems": 1,
                    },
                },
            },
            outputs={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        )
        # 通过
        ok, msg = v.validate_inputs("complex_in", {
            "config": {"model_name": "a", "batch_size": 8},
            "items": [
                {"id": "1", "score": 0.95},
                {"id": "2", "score": 0.42},
            ],
        })
        assert ok is True
        # 失败: model_name 不在 enum
        ok2, msg2 = v.validate_inputs("complex_in", {
            "config": {"model_name": "z"},
            "items": [],
        })
        assert ok2 is False
        assert "model_name" in msg2 or "enum" in msg2
        # 失败: items 缺 id
        ok3, msg3 = v.validate_inputs("complex_in", {
            "config": {"model_name": "a"},
            "items": [{"score": 0.1}],
        })
        assert ok3 is False
        assert "id" in msg3 or "missing" in msg3.lower()


# ──────────────────────────────────────────────────────────────────────────
# API layer integration tests (FastAPI TestClient on mini-app)
# ──────────────────────────────────────────────────────────────────────────

@pytest.fixture
def contract_client():
    """Mini FastAPI app with workflow_contract router (4 endpoints exercised)."""
    if not _API_IMPORT_OK:
        pytest.skip(f"api router import failed: {_API_IMPORT_ERR}")
    app = FastAPI()
    app.include_router(contract_router)
    return TestClient(app)


class TestContractAPI:
    """验证 Pydantic + FastAPI 路由层 (额外覆盖, 算入 10 个 contract 用例里 2-3 个)."""

    def test_register_and_get_node(self, contract_client):
        """9. 未注册 → 404 (走 API 层)."""
        r = contract_client.get("/api/v1/workflow/contract/nodes/never_registered_xyz")
        assert r.status_code == 404

    def test_register_and_validate_workflow_ok(self, contract_client):
        """API: 注册 + 校验 workflow 通过."""
        r1 = contract_client.post(
            "/api/v1/workflow/contract/nodes",
            json={
                "node_id": "api_node_a",
                "inputs": {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}},
                "outputs": {"type": "object", "required": ["y"], "properties": {"y": {"type": "string"}}},
            },
        )
        assert r1.status_code == 201
        assert r1.json()["ok"] is True

        # 校验 workflow (用预设 img_gen -> img_edit 链)
        r2 = contract_client.post(
            "/api/v1/workflow/contract/validate",
            json={
                "nodes": [
                    {"id": "a", "type": "image_generation", "inputs": {"prompt": "cat"}},
                    {"id": "b", "type": "image_edit", "inputs": {"image": "x.png", "instruction": "blur"}},
                ],
                "edges": [{"source": "a", "target": "b"}],
            },
        )
        assert r2.status_code == 200
        body = r2.json()
        assert body["ok"] is True
        assert body["data"]["valid"] is True


# ──────────────────────────────────────────────────────────────────────────
# Crowd Settlement Engine — unit tests (12)
# ──────────────────────────────────────────────────────────────────────────

class TestCrowdSettlementEngine:

    # 1. price_task 返回合理范围
    def test_price_task_returns_positive(self):
        eng = CrowdSettlementEngine()
        p = eng.price_task("text_classification", difficulty=2, deadline_hours=48)
        assert p > 0
        # base=1.0, diff_factor=1.2, urgency=0.1 → 1.0 * 1.2 * 1.03 = 1.236
        assert 1.0 < p < 2.0

    # 2. 难度 +1 价格 +20%
    def test_price_scales_with_difficulty(self):
        eng = CrowdSettlementEngine()
        # 用 168h (1 周) 让 urgency = 0
        p1 = eng.price_task("image_annotation", difficulty=1, deadline_hours=200)
        p2 = eng.price_task("image_annotation", difficulty=2, deadline_hours=200)
        # 难度 2 = 难度 1 * 1.2
        assert abs(p2 / p1 - 1.2) < 0.01

    # 3. 截止时间紧 (urgency=0.3) vs 松 (urgency=0)
    def test_price_urgent_deadline(self):
        eng = CrowdSettlementEngine()
        p_relaxed = eng.price_task("text_classification", difficulty=3, deadline_hours=200)
        p_urgent = eng.price_task("text_classification", difficulty=3, deadline_hours=1)
        # 紧迫 → *1.09 (1+0.3*0.3), relaxed → *1.0
        assert abs(p_urgent / p_relaxed - 1.09) < 0.01

    # 4. lock_price 锁定后 price 不变 (即使外部重新定价)
    def test_locked_price_immutable(self):
        eng = CrowdSettlementEngine()
        task = eng.create_task("text_classification", difficulty=2, deadline_hours=100)
        original_price = task.price
        eng.lock_price(task.task_id, "worker_1")
        # 重新用不同参数定价 — 不影响已锁定的 task
        new_price = eng.price_task("text_classification", difficulty=5, deadline_hours=1)
        assert task.price == original_price
        assert task.status == "locked"
        assert task.locked_by == "worker_1"

    # 5. settle passed=True 钱包增加
    def test_settle_passed_credits_wallet(self):
        eng = CrowdSettlementEngine()
        task = eng.create_task("text_classification", difficulty=2, deadline_hours=100)
        eng.lock_price(task.task_id, "w_pass")
        before = eng.get_wallet("w_pass")["balance"]
        eng.settle(task.task_id, passed=True)
        after = eng.get_wallet("w_pass")["balance"]
        assert after - before == task.price

    # 6. settle passed=False 钱包不变
    def test_settle_failed_no_credit(self):
        eng = CrowdSettlementEngine()
        task = eng.create_task("text_classification", difficulty=2, deadline_hours=100)
        eng.lock_price(task.task_id, "w_fail")
        before = eng.get_wallet("w_fail")["balance"]
        result = eng.settle(task.task_id, passed=False)
        after = eng.get_wallet("w_fail")["balance"]
        assert after == before == 0.0
        assert result["amount"] == 0.0
        assert task.status == "failed"

    # 7. 重复 settle 幂等
    def test_settle_idempotent(self):
        eng = CrowdSettlementEngine()
        task = eng.create_task("text_classification", difficulty=2, deadline_hours=100)
        eng.lock_price(task.task_id, "w_idem")
        r1 = eng.settle(task.task_id, passed=True)
        wallet1 = eng.get_wallet("w_idem")["balance"]
        r2 = eng.settle(task.task_id, passed=True)
        wallet2 = eng.get_wallet("w_idem")["balance"]
        assert r1["idempotent"] is False
        assert r2["idempotent"] is True
        assert wallet1 == wallet2 == task.price  # 没重复发钱

    # 8. withdraw 申请扣减钱包
    def test_withdraw_decreases_balance(self):
        eng = CrowdSettlementEngine()
        task = eng.create_task("image_annotation", difficulty=3, deadline_hours=100)
        eng.lock_price(task.task_id, "w_withdraw")
        eng.settle(task.task_id, passed=True)
        before = eng.get_wallet("w_withdraw")["balance"]
        wd_amount = before * 0.5
        eng.withdraw("w_withdraw", wd_amount)
        after = eng.get_wallet("w_withdraw")["balance"]
        assert abs(after - (before - wd_amount)) < 0.001

    # 9. 提现 > 余额 → 抛 ValueError (路由层 → 422)
    def test_withdraw_insufficient_balance(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.crowd_settlement import router

        eng = CrowdSettlementEngine()
        # 先让 w_poor 有 0 余额
        # eng.wallets 默认空, w_poor balance = 0
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        r = client.post("/api/v1/crowd/withdraw", json={"worker_id": "w_poor", "amount": 100.0})
        assert r.status_code == 422
        assert "insufficient" in r.json()["detail"]

    # 10. 提现历史记录
    def test_withdraw_history(self):
        eng = CrowdSettlementEngine()
        # 创建任务并结算, 让 worker 有钱
        task = eng.create_task("image_annotation", difficulty=3, deadline_hours=100)
        eng.lock_price(task.task_id, "w_hist")
        eng.settle(task.task_id, passed=True)
        # 两次提现
        eng.withdraw("w_hist", 0.5)
        eng.withdraw("w_hist", 0.3)
        hist = eng.withdraw_history("w_hist")
        assert len(hist) == 2
        amounts = [h["amount"] for h in hist]
        assert abs(amounts[0] - 0.5) < 0.001
        assert abs(amounts[1] - 0.3) < 0.001

    # 11. 跨 worker 钱包隔离
    def test_wallet_isolation(self):
        eng = CrowdSettlementEngine()
        task = eng.create_task("text_classification", difficulty=3, deadline_hours=100)
        eng.lock_price(task.task_id, "w_alice")
        eng.settle(task.task_id, passed=True)

        task2 = eng.create_task("text_classification", difficulty=3, deadline_hours=100)
        eng.lock_price(task2.task_id, "w_bob")
        eng.settle(task2.task_id, passed=True)

        bal_a = eng.get_wallet("w_alice")["balance"]
        bal_b = eng.get_wallet("w_bob")["balance"]
        assert bal_a == bal_b == task.price
        # 互不影响: alice 提现不应影响 bob
        eng.withdraw("w_alice", bal_a)
        assert eng.get_wallet("w_bob")["balance"] == bal_b

    # 12. 提现 ≤ 0 → 422
    def test_withdraw_nonpositive_amount(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.crowd_settlement import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # amount = 0 → Pydantic gt=0 拒绝
        r1 = client.post("/api/v1/crowd/withdraw", json={"worker_id": "w_neg", "amount": 0})
        assert r1.status_code == 422

        # amount = -1 → Pydantic 拒绝
        r2 = client.post("/api/v1/crowd/withdraw", json={"worker_id": "w_neg", "amount": -5.0})
        assert r2.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
# Smoke: preset nodes
# ──────────────────────────────────────────────────────────────────────────

class TestPresets:
    def test_presets_registered(self):
        v = ContractValidator()
        register_preset_nodes(v)
        for t in PRESET_NODES:
            assert v.get_node(t) is not None

    def test_preset_image_gen_valid(self):
        v = ContractValidator()
        register_preset_nodes(v)
        ok, msg = v.validate_inputs("image_generation", {"prompt": "a cat"})
        assert ok is True
        # 缺 prompt → 失败
        ok2, _ = v.validate_inputs("image_generation", {})
        assert ok2 is False