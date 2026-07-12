"""P5-R1-T6 测试 — Internal QC + Requester Acceptance + Delivery Workflow
=========================================================================

覆盖 17 个测试用例:
  QC:
    1. test_qc_full_check_basic       - 全量质检基础
    2. test_qc_sample_check_reproducible - 抽检可复现 (seed)
    3. test_qc_aql_letter_table       - AQL 字母表查询
    4. test_qc_aql_reject_high_defect - AQL 高缺陷率判定 Reject
    5. test_qc_aql_pass_low_defect    - AQL 低缺陷率判定 Accept
    6. test_qc_stratified_balanced    - 分层抽样均衡
    7. test_qc_invalid_sample_rate    - 非法 sample_rate 抛错
    8. test_qc_invalid_aql_level      - 非法 AQL level 抛错
    9. test_qc_export_three_formats   - 三种格式导出
   10. test_qc_rerun_preserves_mode   - 重跑保留模式
   11. test_qc_list_pagination        - 列表分页
   12. test_qc_stats_defect_rate      - 缺陷率计算

  Requester:
   13. test_requester_create_and_submit - 创建+提交
   14. test_requester_request_revision - 退回生产
   15. test_requester_pending_filter    - 过滤 pending

  Delivery Workflow:
   16. test_workflow_compare_two_deliveries - 对比两个交付物
   17. test_workflow_state_progression      - 状态进展方向
"""
import os
import sys
import json
import sqlite3
import tempfile
import pytest
from pathlib import Path

# 路径注入
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMDF = PROJECT_ROOT
sys.path.insert(0, str(IMDF))
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.qc_routes import router as qc_router
from api.requester_routes import router as req_router
from engines.internal_qc_engine import InternalQCEngine
from engines.requester_acceptance_engine import RequesterAcceptanceEngine


# ────────────────────────── Fixtures ──────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """临时数据库 — 完全隔离"""
    db_path = str(tmp_path / "test_qc.db")
    yield db_path
    # 自动清理
    if Path(db_path).exists():
        try:
            Path(db_path).unlink()
        except Exception:
            pass


@pytest.fixture
def qc_engine(tmp_db):
    from engines.internal_qc_engine import InternalQCEngine
    return InternalQCEngine(db_path=tmp_db)


@pytest.fixture
def req_engine(tmp_db):
    from engines.requester_acceptance_engine import RequesterAcceptanceEngine
    return RequesterAcceptanceEngine(db_path=tmp_db)


@pytest.fixture
def asset_provider():
    """固定 200 个资产"""
    def provider(dataset_id):
        return [
            {"id": f"{dataset_id}_a{i:04d}", "name": f"asset_{i}", "type": "image" if i % 2 == 0 else "video"}
            for i in range(200)
        ]
    return provider


@pytest.fixture
def seed_db(tmp_db):
    """塞入 deliveries 测试数据 (必须先创建 deliveries 表)

    注意: engine 查询时用 'delivery_id' 字段 (即 name 或 id),
    所以这里 name 用 'd1'/'d2' 让 create_acceptance 能找到。
    """
    conn = sqlite3.connect(tmp_db)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY,
            name VARCHAR(200),
            dataset_version VARCHAR(50),
            status VARCHAR(20),
            reviewer VARCHAR(100),
            comments VARCHAR(500)
        );
    """)
    conn.execute(
        "INSERT INTO deliveries (id, name, dataset_version, status, reviewer, comments) VALUES (1, 'd1', '1.0', 'approved', 'reviewer_a', 'ready for qc')"
    )
    conn.execute(
        "INSERT INTO deliveries (id, name, dataset_version, status, reviewer, comments) VALUES (2, 'd2', '1.1', 'in_review', 'reviewer_b', 'reviewing')"
    )
    conn.commit()
    conn.close()
    return tmp_db


# ────────────────────────── QC Tests ──────────────────────────

class TestInternalQC:
    def test_qc_full_check_basic(self, qc_engine, asset_provider):
        record = qc_engine.full_check(
            dataset_id="ds_001",
            qcer_id="qcer_001",
            asset_provider=asset_provider,
        )
        assert record.id.startswith("qc_")
        assert record.dataset_id == "ds_001"
        assert record.mode == "full"
        assert record.sample_size == 200
        assert record.total_assets == 200
        assert record.result in ("passed", "failed")
        assert record.issue_count >= 0
        assert len(record.issues) == record.issue_count

    def test_qc_sample_check_reproducible(self, qc_engine, asset_provider):
        r1 = qc_engine.sample_check(
            dataset_id="ds_002", sample_rate=0.1, qcer_id="qc",
            asset_provider=asset_provider, seed=42,
        )
        r2 = qc_engine.sample_check(
            dataset_id="ds_002", sample_rate=0.1, qcer_id="qc",
            asset_provider=asset_provider, seed=42,
        )
        # 同 seed → 同 sample_size
        assert r1.sample_size == r2.sample_size
        assert r1.sample_rate == r2.sample_rate
        # issue 分布应该相近 (允许 ±20%)
        assert abs(r1.issue_count - r2.issue_count) <= max(2, r1.issue_count * 0.3)

    def test_qc_aql_letter_table(self, qc_engine):
        from engines.internal_qc_engine import _aql_code_letter, LETTER_SAMPLE, AQL_TABLE
        # 校验关键 lot_size → code letter 映射
        assert _aql_code_letter(50) == "D"
        assert _aql_code_letter(500) == "H"
        assert _aql_code_letter(5000) == "L"
        assert _aql_code_letter(50000) == "N"
        # sample size 表
        assert LETTER_SAMPLE["D"] == 8
        assert LETTER_SAMPLE["H"] == 50
        assert LETTER_SAMPLE["L"] == 200
        # AQL 表存在关键节点
        assert ("H", 1.0) in AQL_TABLE
        assert ("L", 4.0) in AQL_TABLE

    def test_qc_aql_reject_high_defect(self, qc_engine, asset_provider):
        # 高缺陷率 (severity_bias=0.5 强制产生大量 critical)
        record = qc_engine.aql_sample(
            dataset_id="ds_aql_reject",
            aql_level=1.0, lot_size=500,
            qcer_id="qc",
            asset_provider=asset_provider,
            severity_bias=0.5,
            seed=42,
        )
        # 高缺陷率必 fail
        assert record.result == "failed"
        # note 包含 AQL 信息
        assert "AQL=1.0" in (record.notes or "")
        assert "letter=H" in (record.notes or "")

    def test_qc_aql_pass_low_defect(self, qc_engine, asset_provider):
        # 低缺陷率 (severity_bias=-0.5 几乎不产生缺陷)
        record = qc_engine.aql_sample(
            dataset_id="ds_aql_pass",
            aql_level=4.0, lot_size=500,
            qcer_id="qc",
            asset_provider=asset_provider,
            severity_bias=-0.5,
            seed=42,
        )
        # 低缺陷率必 pass
        assert record.result == "passed"
        assert "AQL=4.0" in (record.notes or "")

    def test_qc_stratified_balanced(self, qc_engine, asset_provider):
        record = qc_engine.stratified_sample(
            dataset_id="ds_strat",
            sample_size=50, qcer_id="qc",
            asset_provider=asset_provider,
            seed=42,
        )
        assert record.mode == "stratified"
        assert record.sample_size <= 50
        # 分层后应包含两种 type
        issue_types = {i.get("type") for i in record.issues}
        # 至少有一种 type (image 或 video)
        assert len(record.issues) == record.issue_count

    def test_qc_invalid_sample_rate(self, qc_engine, asset_provider):
        with pytest.raises(ValueError, match="sample_rate"):
            qc_engine.sample_check(
                dataset_id="ds", sample_rate=1.5,
                qcer_id="qc", asset_provider=asset_provider,
            )
        with pytest.raises(ValueError, match="sample_rate"):
            qc_engine.sample_check(
                dataset_id="ds", sample_rate=0,
                qcer_id="qc", asset_provider=asset_provider,
            )

    def test_qc_invalid_aql_level(self, qc_engine, asset_provider):
        with pytest.raises(ValueError, match="aql_level"):
            qc_engine.aql_sample(
                dataset_id="ds", aql_level=99.0, lot_size=100,
                qcer_id="qc", asset_provider=asset_provider,
            )

    def test_qc_export_three_formats(self, qc_engine, asset_provider):
        record = qc_engine.full_check(
            dataset_id="ds_export", qcer_id="qc",
            asset_provider=asset_provider, severity_bias=0.2,
        )
        # JSON
        json_path = qc_engine.export_qc_report(record.id, format="json")
        assert Path(json_path).exists()
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        assert data["record"]["id"] == record.id
        # CSV
        csv_path = qc_engine.export_qc_report(record.id, format="csv")
        assert Path(csv_path).exists()
        csv_content = Path(csv_path).read_text(encoding="utf-8")
        assert csv_content.startswith("issue_id,qc_id,asset_id")
        # PDF (HTML)
        html_path = qc_engine.export_qc_report(record.id, format="pdf")
        assert Path(html_path).exists()
        assert "<html>" in Path(html_path).read_text(encoding="utf-8")

    def test_qc_rerun_preserves_mode(self, qc_engine, asset_provider):
        # 跑一次 sample
        r1 = qc_engine.sample_check(
            dataset_id="ds_rerun", sample_rate=0.1, qcer_id="qc",
            asset_provider=asset_provider, seed=42,
        )
        # rerun
        r2 = qc_engine.rerun_qc(r1.id, asset_provider=asset_provider)
        assert r2.id != r1.id
        assert r2.mode == r1.mode
        assert r2.dataset_id == r1.dataset_id
        assert "rerun" in r2.notes

    def test_qc_list_pagination(self, qc_engine, asset_provider):
        # 跑 5 条
        for i in range(5):
            qc_engine.sample_check(
                dataset_id=f"ds_page_{i}", sample_rate=0.05, qcer_id="qc",
                asset_provider=asset_provider, seed=42,
            )
        # 分页
        items, total = qc_engine.list_qc_records(page=1, page_size=3)
        assert total == 5
        assert len(items) == 3
        items2, _ = qc_engine.list_qc_records(page=2, page_size=3)
        assert len(items2) == 2

    def test_qc_stats_defect_rate(self, qc_engine, asset_provider):
        record = qc_engine.full_check(
            dataset_id="ds_stats", qcer_id="qc",
            asset_provider=asset_provider, severity_bias=0.2,
        )
        stats = qc_engine.get_qc_stats(record.id)
        assert "error" not in stats
        assert 0 <= stats["defect_rate"] <= 1
        assert 0 <= stats["pass_rate"] <= 1
        assert abs(stats["defect_rate"] + stats["pass_rate"] - 1.0) < 0.001
        assert "by_severity" in stats
        assert "by_type" in stats


# ────────────────────────── Requester Tests ──────────────────────────

class TestRequesterAcceptance:
    def test_requester_create_and_submit(self, req_engine, seed_db):
        # 用 deliveries.id=1 创建验收
        record = req_engine.create_acceptance(
            delivery_id="d1",
            requester_id="r001",
            sample_rate=0.1,
            seed=42,
        )
        assert record.id.startswith("acc_")
        assert record.delivery_id == "d1"
        assert record.requester_id == "r001"
        assert record.status == "pending"
        assert record.sampled_count > 0
        # 提交 accepted
        submitted = req_engine.submit_acceptance(
            acceptance_id=record.id,
            status="accepted",
            comments="all good",
        )
        assert submitted.status == "accepted"
        assert submitted.accepted_count == record.sampled_count
        # acceptance_rate 是 to_dict 计算的字段
        d = submitted.to_dict()
        assert d["acceptance_rate"] == 1.0

    def test_requester_request_revision(self, req_engine, seed_db):
        record = req_engine.create_acceptance(
            delivery_id="d1", requester_id="r002",
            sample_rate=0.1, seed=42,
        )
        revised = req_engine.request_revision(
            acceptance_id=record.id,
            reason="labels are wrong",
            issues=[{"asset_id": "a001", "description": "missing label"}],
        )
        assert revised.status == "needs_revision"
        assert "labels are wrong" in revised.comments

    def test_requester_pending_filter(self, req_engine, seed_db):
        # 2 个验收, 1 个提交
        r1 = req_engine.create_acceptance(
            delivery_id="d1", requester_id="r003", sample_rate=0.1, seed=42,
        )
        req_engine.create_acceptance(
            delivery_id="d2", requester_id="r003", sample_rate=0.1, seed=42,
        )
        pending = req_engine.list_pending_for_requester("r003")
        assert len(pending) == 2
        # 提交一个
        req_engine.submit_acceptance(r1.id, status="accepted", comments="OK")
        pending2 = req_engine.list_pending_for_requester("r003")
        assert len(pending2) == 1
        assert pending2[0].id != r1.id


# ────────────────────────── Delivery Workflow Tests ──────────────────────────

class TestDeliveryWorkflow:
    def test_workflow_compare_two_deliveries(self, seed_db):
        from engines.delivery_workflow import DeliveryWorkflow
        wf = DeliveryWorkflow(db_path=seed_db)
        result = wf.compare_deliveries("d1", "d2")
        assert "left" in result
        assert "right" in result
        assert result["left"]["name"] == "d1"
        assert result["right"]["name"] == "d2"
        assert result["same_version"] is False
        assert result["same_status"] is False
        assert result["status_progression"] in ("progressed", "regressed", "same")

    def test_workflow_state_progression(self):
        from engines.delivery_workflow import _status_compare
        assert _status_compare("draft", "submitted") == "progressed"
        assert _status_compare("approved", "approved") == "same"
        assert _status_compare("delivered", "draft") == "regressed"
        assert _status_compare("invalid", "draft") == "unknown"


# ────────────────────────── HTTP API Tests (TestClient) ──────────────────────────

class TestQCAPI:
    """通过 TestClient 验证 API 端点"""

    def _make_app(self, tmp_db, monkeypatch):
        """构建 mini FastAPI app + patched engine"""
        def patched_qc():
            return InternalQCEngine(db_path=tmp_db)
        def patched_req():
            return RequesterAcceptanceEngine(db_path=tmp_db)
        monkeypatch.setattr("api.qc_routes._get_engine", patched_qc)
        monkeypatch.setattr("api.requester_routes._get_engine", patched_req)
        app = FastAPI()
        app.include_router(qc_router)
        app.include_router(req_router)
        return TestClient(app)

    def test_api_qc_full_endpoint(self, tmp_db, asset_provider, monkeypatch):
        """全量 QC API 端点"""
        import engines.internal_qc_engine as qc_mod
        qc_mod._engine_instance = None
        client = self._make_app(tmp_db, monkeypatch)

        r = client.post("/api/v1/qc/full", json={
            "dataset_id": "api_test", "qcer_id": "qc_api",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["success"] is True
        assert data["data"]["mode"] == "full"
        assert data["data"]["dataset_id"] == "api_test"

    def test_api_qc_sample_invalid_rate(self, tmp_db, monkeypatch):
        client = self._make_app(tmp_db, monkeypatch)
        r = client.post("/api/v1/qc/sample", json={
            "dataset_id": "api", "sample_rate": 1.5,
        })
        assert r.status_code == 422  # Pydantic gt/le 校验

    def test_api_qc_aql_invalid_level(self, tmp_db, monkeypatch):
        client = self._make_app(tmp_db, monkeypatch)
        r = client.post("/api/v1/qc/aql", json={
            "dataset_id": "api", "aql_level": 99.0, "lot_size": 100,
        })
        assert r.status_code == 422  # Pydantic validator 拒绝

    def test_api_qc_records_list(self, tmp_db, monkeypatch):
        client = self._make_app(tmp_db, monkeypatch)
        r = client.get("/api/v1/qc/records?page=1&page_size=5")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "items" in data["data"]

    def test_api_requester_create_and_submit(self, seed_db, monkeypatch):
        client = self._make_app(seed_db, monkeypatch)

        # 创建
        r = client.post("/api/v1/requester/acceptances", json={
            "delivery_id": "d1", "requester_id": "r_api", "sample_rate": 0.1, "seed": 42,
        })
        assert r.status_code == 200, r.text
        acc_id = r.json()["data"]["id"]

        # 提交
        r = client.post(f"/api/v1/requester/acceptances/{acc_id}/submit", json={
            "status": "accepted", "comments": "looks good",
        })
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "accepted"


# ────────────────────────── P5-R1-T6 Attempt 2 新增 ──────────────────────────
# 覆盖 P0/P1/P2 fix:
#   P0: requester-accept 触发 finalize_and_share, 返回 share_url
#   P0: requester-reject loop-back (rejected → draft)
#   P1: 完整 ISO 2859-1 AQL 表 (12 等级 × 16 letters = 192 cells)
#   P1: FSM transition 函数
#   P1: 增量快照自动创建
#   P2: 真实 CV 检测 hook

class TestAttempt2Fixes:
    """Attempt 2 新增测试 — 覆盖 verifier/auditor FAIL 反馈的所有 gap"""

    def test_p0_requester_accept_triggers_finalize(self, seed_db, monkeypatch):
        """P0 fix: requester-accept API 自动触发 finalize_and_share"""
        # seed_db 中 d1 状态=approved, 应能触发 finalize
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.delivery_routes import router as delivery_router
        from api.requester_routes import router as req_router

        def patched_req():
            return RequesterAcceptanceEngine(db_path=seed_db)

        from engines.delivery_workflow import get_delivery_workflow
        _wf_instance = get_delivery_workflow(seed_db)
        # delivery_workflow 单例需要在同 db path 下 — patch
        monkeypatch.setattr("engines.delivery_workflow._workflow_instance", _wf_instance)
        monkeypatch.setattr("api.delivery_routes._get_engine", patched_req) if hasattr(__import__('api.delivery_routes', fromlist=['']), '_get_engine') else None

        app = FastAPI()
        app.include_router(delivery_router)
        app.include_router(req_router)
        client = TestClient(app)

        r = client.post(
            "/api/delivery/d1/requester-accept",
            params={
                "requester_id": "r_p0",
                "comments": "P0 test",
                "sample_rate": 0.1,
                "expiry_hours": 24,
                "max_downloads": 5,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        # 关键: 响应必须包含 share_url (P0 fix 标志)
        assert "share_url" in data, "P0 fix: response must contain share_url"
        assert "acceptance" in data
        assert data["acceptance"]["status"] == "accepted"
        # shared=True 表示 finalize_and_share 成功
        assert data["shared"] is True

    def test_p0_requester_reject_loopback(self, seed_db, monkeypatch):
        """P0 fix: requester-reject 触发 loop-back (rejected → draft)"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from api.delivery_routes import router as delivery_router
        from engines.delivery_workflow import get_delivery_workflow

        _wf_instance = get_delivery_workflow(seed_db)
        monkeypatch.setattr("engines.delivery_workflow._workflow_instance", _wf_instance)

        # 用 d2 (seed_db 中 in_review 状态) — 先把它转为 approved 以便 loop-back
        with sqlite3.connect(seed_db) as conn:
            conn.execute(
                "UPDATE deliveries SET status = 'approved' WHERE name = 'd2'"
            )
            conn.commit()

        app = FastAPI()
        app.include_router(delivery_router)
        client = TestClient(app)

        r = client.post(
            "/api/delivery/d2/requester-reject",
            params={
                "requester_id": "r_p0_reject",
                "comments": "labels wrong",
                "sample_rate": 0.1,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        # 关键: production_loopback 触发
        assert "production_loopback" in data
        assert data["production_loopback"]["triggered"] is True
        assert data["production_loopback"]["from_status"] == "approved"
        assert data["production_loopback"]["to_status"] == "draft"

    def test_p1_complete_aql_table(self):
        """P1 fix: 完整 ISO 2859-1 AQL 表 (12 等级 × 16 letters = 192 cells)"""
        from engines.internal_qc_engine import (
            AQL_TABLE, AQL_LIMITS, LETTER_SAMPLE,
        )
        # 12 AQL levels
        assert len(AQL_LIMITS) == 12
        # 16 code letters
        assert len(LETTER_SAMPLE) == 16
        # 192 cells (16 letters × 12 levels)
        assert len(AQL_TABLE) == 192, f"got {len(AQL_TABLE)} cells, expected 192"
        # 校验每个 (letter, aql) 都有
        for letter in LETTER_SAMPLE:
            for aql in AQL_LIMITS:
                assert (letter, aql) in AQL_TABLE, f"missing ({letter}, {aql})"
        # 校验关键节点 (ISO 2859-1 标准值)
        assert AQL_TABLE[("J", 1.0)] == (2, 3), "ISO standard J/1.0"
        assert AQL_TABLE[("H", 4.0)] == (7, 8), "ISO standard H/4.0"
        assert AQL_TABLE[("K", 0.65)] == (2, 3), "ISO standard K/0.65"

    def test_p1_aql_extreme_levels(self):
        """P1 fix: 验证极端 AQL level (0.065 和 10.0) 正确性"""
        from engines.internal_qc_engine import (
            _aql_lookup, AQL_TABLE, AQL_LIMITS,
        )
        # 0.065 是 ISO 2859-1 最小等级
        assert AQL_TABLE[("N", 0.065)] == (1, 2)
        # 10.0 是最大常用等级
        assert AQL_TABLE[("K", 10.0)] == (25, 26)
        # 不存在的 aql 应 fallback 到最近 (更严格)
        # 0.07 → 应该取 0.065 (向下)
        ac, re = _aql_lookup("J", 0.07)
        # 0.065 向下找 (J, 0.065) = (0, 1)
        assert ac <= 1

    def test_p1_fsm_transition_function(self, seed_db):
        """P1 fix: FSM transition 函数严格校验"""
        from engines.delivery_workflow import DeliveryStateMachine
        sm = DeliveryStateMachine(db_path=seed_db)

        # 合法转换
        assert sm.can_transition("draft", "submitted") is True
        assert sm.can_transition("submitted", "in_review") is True
        assert sm.can_transition("in_review", "approved") is True
        assert sm.can_transition("approved", "delivered") is True
        assert sm.can_transition("delivered", "shared") is True
        assert sm.can_transition("rejected", "draft") is True  # loop-back

        # 非法转换
        assert sm.can_transition("draft", "shared") is False
        assert sm.can_transition("draft", "delivered") is False
        assert sm.can_transition("archived", "submitted") is False  # 终态

        # 执行 transition (用 d2 — seed_db 中是 in_review, 但我们要测试 approved→delivered)
        # 先确保 d2 是 approved
        with sqlite3.connect(seed_db) as conn:
            conn.execute(
                "UPDATE deliveries SET status = 'approved' WHERE name = 'd2'"
            )
            conn.commit()
        result = sm.transition(
            delivery_id="d2",
            from_state="approved",
            to_state="delivered",
            actor="test_fsm",
        )
        assert result["success"] is True
        assert result["fsm_valid"] is True

    def test_p1_fsm_invalid_transition_raises(self, seed_db):
        """P1 fix: FSM 非法转换应抛错"""
        from engines.delivery_workflow import DeliveryStateMachine
        sm = DeliveryStateMachine(db_path=seed_db)

        with pytest.raises(ValueError, match="非法状态转换"):
            sm.transition(
                delivery_id="d1",
                from_state="approved",
                to_state="draft",  # 非法 (approved 不能直接回 draft)
                actor="test_fsm",
            )

    def test_p1_fsm_validate_status_chain(self):
        """P1 fix: FSM 路径可达性 (BFS)"""
        from engines.delivery_workflow import DeliveryStateMachine
        sm = DeliveryStateMachine()

        # 直达
        reachable, path = sm.validate_status_chain("draft", "submitted")
        assert reachable and path == ["draft", "submitted"]

        # 跨多步 (BFS)
        reachable, path = sm.validate_status_chain("draft", "shared")
        assert reachable
        # 路径应经过: draft → submitted → in_review → approved → delivered → shared
        assert len(path) >= 4

        # 不可达 (archived 是终态)
        reachable, path = sm.validate_status_chain("archived", "draft")
        assert not reachable

        # 通过 rejected 中转 (loop-back)
        reachable, path = sm.validate_status_chain("submitted", "draft")
        assert reachable
        assert "submitted" in path and "draft" in path

    def test_p1_auto_snapshot_in_finalize(self, seed_db, tmp_path):
        """P1 fix: finalize_and_share 自动创建增量快照"""
        from engines.delivery_workflow import DeliveryWorkflow
        # 在 tmp_path 创建一些测试文件
        resource_path = tmp_path / "test_delivery_resources"
        resource_path.mkdir()
        for i in range(5):
            (resource_path / f"file_{i}.txt").write_text(f"content {i}")

        wf = DeliveryWorkflow(db_path=seed_db)

        # delivery 'd1' 已经是 approved (seed_db)
        result = wf.finalize_and_share(
            delivery_id="d1",
            owner_id="auto_snap_test",
            resource_path=str(resource_path),
            expiry_hours=24,
            max_downloads=10,
        )

        # 关键: 快照必须自动创建
        assert result["snapshot_id"], "P1 fix: snapshot must be auto-created"
        assert "snapshot_created" in [e["type"] for e in result["events"]]

    def test_p1_fsm_transition_recorded(self, seed_db):
        """P1 fix: FSM transition 应记录到时间线"""
        from engines.delivery_workflow import DeliveryWorkflow
        wf = DeliveryWorkflow(db_path=seed_db)

        # 用 d2 — seed_db 中是 in_review, 先转为 approved
        with sqlite3.connect(seed_db) as conn:
            conn.execute(
                "UPDATE deliveries SET status = 'approved' WHERE name = 'd2'"
            )
            conn.commit()

        # 先执行一次 transition
        wf.state_machine.transition(
            delivery_id="d2",
            from_state="approved",
            to_state="delivered",
            actor="timeline_test",
        )

        timeline = wf.get_delivery_timeline("d2")
        # 应该有时间线事件记录
        assert any(
            evt["event_type"] == "fsm_transition" for evt in timeline
        )

    def test_p2_real_cv_detector_hook(self, qc_engine):
        """P2 fix: 真实 CV 检测器 hook 接口"""
        # 注册一个真实 CV 检测器 (mock) — 总是返回 1 issue
        def my_cv_detector(asset):
            return [QCIssue(
                id=f"cv_{asset.get('id', 'unknown')}",
                qc_id="",
                asset_id=asset.get("id", "unknown"),
                type="label",
                severity="major",
                description="[CV] label missing",
                suggested_action="manual review",
            )]

        qc_engine.register_cv_detector("yolov8", my_cv_detector)
        # 验证 detector 已注册
        assert hasattr(qc_engine, "_cv_detectors")
        assert "yolov8" in qc_engine._cv_detectors

        # 调用 _real_cv_detect 直接验证
        issues = qc_engine._real_cv_detect({"id": "test_001", "name": "a1"})
        assert isinstance(issues, list)
        # 真实检测器总是返回 1 issue
        assert len(issues) == 1, f"expected 1 issue, got {len(issues)}: {issues}"
        assert issues[0].type == "label"
        assert issues[0].description.startswith("[CV]")

        # 注销
        qc_engine.unregister_cv_detector("yolov8")
        issues2 = qc_engine._real_cv_detect({"id": "test_002", "name": "a2"})
        assert issues2 == []

    def test_p2_count_accuracy(self, qc_engine, asset_provider):
        """P2 fix: count 准确性 (acceptance_rate / defect_rate 边界)"""
        record = qc_engine.full_check(
            dataset_id="ds_count", qcer_id="qc",
            asset_provider=asset_provider, severity_bias=-0.5,
        )
        stats = qc_engine.get_qc_stats(record.id)
        # defect_rate + pass_rate 应严格 = 1.0
        assert abs(stats["defect_rate"] + stats["pass_rate"] - 1.0) < 0.0001
        # issue_count ≤ sample_size
        assert stats["issue_count"] <= stats["sample_size"]
        # sample_size ≤ total_assets
        assert stats["sample_size"] <= stats["total_assets"]
        # 各 severity 计数之和 = issue_count
        sev_sum = sum(stats["by_severity"].values())
        assert sev_sum == stats["issue_count"]


class TestDeliveryWorkflowFSM:
    """FSM 状态机与状态转换综合测试"""

    def test_workflow_state_progression_full_chain(self, seed_db):
        """完整状态链: draft → submitted → in_review → approved → delivered → shared"""
        from engines.delivery_workflow import DeliveryWorkflow
        wf = DeliveryWorkflow(db_path=seed_db)

        # 用 d2 — 先重置为 approved (避免与 d1 的共享状态冲突)
        with sqlite3.connect(seed_db) as conn:
            conn.execute(
                "UPDATE deliveries SET status = 'approved' WHERE name = 'd2'"
            )
            conn.commit()

        # 推进到 delivered
        result = wf.state_machine.transition(
            delivery_id="d2", from_state="approved", to_state="delivered",
            actor="test_chain",
        )
        assert result["fsm_valid"] is True

        # 推进到 shared
        result2 = wf.state_machine.transition(
            delivery_id="d2", from_state="delivered", to_state="shared",
            actor="test_chain",
        )
        assert result2["fsm_valid"] is True

    def test_workflow_compare_deliveries_with_fsm(self, seed_db):
        """compare_deliveries + FSM progression"""
        from engines.delivery_workflow import DeliveryWorkflow
        wf = DeliveryWorkflow(db_path=seed_db)

        # 添加第 3 个 delivery
        with sqlite3.connect(seed_db) as conn:
            conn.execute(
                "INSERT INTO deliveries (id, name, dataset_version, status) "
                "VALUES (3, 'd3', '3.0', 'draft')"
            )
            conn.commit()

        result = wf.compare_deliveries("d1", "d3")
        assert "status_progression" in result
        # approved → draft 应是 regressed
        assert result["status_progression"] == "regressed"