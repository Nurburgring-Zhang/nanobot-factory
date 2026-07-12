"""P5-R1-T3 测试 — Pack + Collection 引擎 / 路由 / 状态机

目标: 至少 15 个测试用例, 覆盖
- PackEngine CRUD
- 状态机合法 / 非法转换
- 智能路由 (空包 → collection, 数据包 → annotation)
- 状态转换审计
- Collection 引擎 — RSS / Crawler / API / Import / Backups

设计:
- 用临时 SQLite DB (避免污染 imdf.db)
- FastAPI TestClient 验证 HTTP 层 (但用临时 router instance)
- 路由器测试用 mini FastAPI app
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List

import pytest

# ===== Path setup =====
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMDF_ROOT = PROJECT_ROOT
sys.path.insert(0, str(IMDF_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

# ===== 导入 SUT =====
from engines.pack_engine import (
    PackEngine, PackStore, PackType, PackSource, PackStatus,
    PACK_TRANSITIONS, STATUS_PROGRESS, get_engine, reset_engine,
)
from engines import data_collection_engine as dce
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.pack_routes import router as pack_router
from api.collection_routes import router as collection_router


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def tmp_pack_db():
    """临时 SQLite DB for pack store."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def tmp_data_dir(monkeypatch):
    """临时 data/ 目录, 把 collection_state.json 隔离."""
    d = tempfile.mkdtemp(prefix="collection_test_")
    # Monkeypatch _data_dir in data_collection_engine
    orig_data_dir = dce._data_dir
    monkeypatch.setattr(dce, "_data_dir", lambda: d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def pack_eng(tmp_pack_db):
    """PackEngine 实例 (隔离 DB)."""
    store = PackStore(db_path=tmp_pack_db)
    return PackEngine(store=store)


@pytest.fixture
def client():
    """mini FastAPI app + TestClient (含 pack + collection router)."""
    app = FastAPI(title="pack-collection-test")
    app.include_router(pack_router)
    app.include_router(collection_router)
    return TestClient(app)


# ============================================================================
# A. Pack CRUD (5 tests)
# ============================================================================

class TestPackCRUD:
    """PackEngine 增删改查."""

    def test_create_data_pack_with_assets(self, pack_eng):
        """A1: 创建数据包, 含 3 个资产, 自动 ready."""
        pack = pack_eng.create_data_pack(
            name="测试数据包",
            asset_ids=["a1", "a2", "a3"],
            requirement_id="REQ-001",
            project_id="P-001",
            metadata={"source": "unit_test"},
        )
        assert pack.id.startswith("pack_")
        assert pack.type == "data_pack"
        assert pack.has_data is True
        assert pack.asset_count == 3
        # 自动转 ready
        assert pack.status == PackStatus.READY.value

    def test_create_task_pack(self, pack_eng):
        """A2: 创建任务包, has_data=False, 不自动 ready."""
        pack = pack_eng.create_task_pack(
            name="标注任务",
            task_type="annotation",
            asset_count=500,
            requirement_id="REQ-002",
        )
        assert pack.type == "task_pack"
        assert pack.has_data is False
        assert pack.task_type == "annotation"
        assert pack.status == PackStatus.CREATED.value  # task_pack 不自动 ready

    def test_list_packs_with_filter(self, pack_eng):
        """A3: 列表 + 过滤 (type / status / requirement_id)."""
        pack_eng.create_data_pack("p1", ["a1"], requirement_id="REQ-A")
        pack_eng.create_data_pack("p2", ["a2"], requirement_id="REQ-A")
        pack_eng.create_task_pack("t1", task_type="cleaning", asset_count=10,
                                  requirement_id="REQ-B")

        # 全部
        items, total = pack_eng.list_packs()
        assert total == 3

        # type 过滤
        items, total = pack_eng.list_packs(type="task_pack")
        assert total == 1
        assert items[0].name == "t1"

        # requirement_id 过滤
        items, total = pack_eng.list_packs(requirement_id="REQ-A")
        assert total == 2

    def test_delete_pack(self, pack_eng):
        """A4: 删除 pack (含 pack_assets 级联)."""
        pack = pack_eng.create_data_pack("del-pack", ["x1", "x2"])
        ok = pack_eng.delete_pack(pack.id)
        assert ok is True
        assert pack_eng.get_pack(pack.id) is None

    def test_update_pack_metadata(self, pack_eng):
        """A5: 更新 metadata 不影响 status."""
        pack = pack_eng.create_data_pack("u-pack", ["a"])
        updated = pack_eng.store.update(pack.id, {"metadata": {"new_key": "v"}})
        assert updated is not None
        assert updated.metadata.get("new_key") == "v"


# ============================================================================
# B. 状态机 (5 tests)
# ============================================================================

class TestPackStateMachine:
    """PackStatus 状态机."""

    def test_legal_forward_transitions(self, pack_eng):
        """B1: 合法正向转换 created → ready → in_annotation → annotated → reviewed → qc_passed → delivered."""
        # 创建一个 task_pack (避免自动 ready)
        pack = pack_eng.create_task_pack("sm-pack", "annotation", 10)
        # task_pack 初始 created
        assert pack.status == "created"

        # created → ready (合法)
        p = pack_eng.update_pack_status(pack.id, "ready")
        assert p.status == "ready"

        # ready → in_annotation (合法)
        p = pack_eng.update_pack_status(pack.id, "in_annotation")
        assert p.status == "in_annotation"

        # in_annotation → annotated
        p = pack_eng.update_pack_status(pack.id, "annotated")
        assert p.status == "annotated"

        # annotated → reviewed
        p = pack_eng.update_pack_status(pack.id, "reviewed")
        assert p.status == "reviewed"

        # reviewed → qc_passed
        p = pack_eng.update_pack_status(pack.id, "qc_passed")
        assert p.status == "qc_passed"

        # qc_passed → delivered
        p = pack_eng.update_pack_status(pack.id, "delivered")
        assert p.status == "delivered"

    def test_illegal_transition_raises(self, pack_eng):
        """B2: 非法转换 created → delivered 抛 ValueError."""
        pack = pack_eng.create_task_pack("illegal-pack", "scoring", 5)
        with pytest.raises(ValueError, match="非法状态转换"):
            pack_eng.update_pack_status(pack.id, "delivered")

    def test_delivered_is_terminal(self, pack_eng):
        """B3: delivered 是终态, 不能继续转换."""
        pack = pack_eng.create_task_pack("terminal", "review", 1)
        # 强行走到 delivered
        for s in ("ready", "in_annotation", "annotated", "reviewed", "qc_passed", "delivered"):
            pack_eng.update_pack_status(pack.id, s)
        # 任何后续转换都应失败
        with pytest.raises(ValueError):
            pack_eng.update_pack_status(pack.id, "reviewed")

    def test_backward_transition_in_annotation_to_ready(self, pack_eng):
        """B4: 状态机允许回退 (in_annotation → ready)."""
        pack = pack_eng.create_data_pack("back-pack", ["a"])  # 自动 ready
        pack_eng.update_pack_status(pack.id, "in_annotation")
        # 回退
        p = pack_eng.update_pack_status(pack.id, "ready")
        assert p.status == "ready"

    def test_transition_records_history(self, pack_eng):
        """B5: transition() 带 reason 时记录 route_history."""
        pack = pack_eng.create_data_pack("hist-pack", ["a"])
        p = pack_eng.transition(pack.id, "in_annotation", reason="开始标注")
        assert p.route_history
        last = p.route_history[-1]
        assert last["action"] == "transition"
        assert last["to_status"] == "in_annotation"
        assert last["reason"] == "开始标注"


# ============================================================================
# C. 智能路由 (3 tests)
# ============================================================================

class TestPackRouting:
    """route_pack 智能路由."""

    def test_data_pack_routes_to_annotation(self, pack_eng):
        """C1: 含数据 pack (has_data=True) → annotation 标注流."""
        pack = pack_eng.create_data_pack("data-pack", ["img1", "img2"])
        result = pack_eng.route_pack(pack.id)
        assert result["target_module"] == "annotation"
        assert result["target_endpoint"] == "/api/v1/annotation/assign"
        # 状态应进入 in_annotation
        p2 = pack_eng.get_pack(pack.id)
        assert p2.status == "in_annotation"

    def test_empty_pack_routes_to_collection(self, pack_eng):
        """C2: 空 pack (has_data=False) → collection 采集流."""
        pack = pack_eng.create_task_pack("empty-pack", "annotation", 100)
        result = pack_eng.route_pack(pack.id)
        assert result["target_module"] == "collection"
        assert result["target_endpoint"] == "/api/v1/collection/jobs"

    def test_route_records_history(self, pack_eng):
        """C3: route_pack 记录 route_history."""
        pack = pack_eng.create_data_pack("route-pack", ["a"])
        pack_eng.route_pack(pack.id)
        p = pack_eng.get_pack(pack.id)
        # 至少应有 1 条 route_history
        assert len(p.route_history) >= 1
        last = p.route_history[-1]
        assert last["action"] == "route"
        assert last["target_module"] == "annotation"


# ============================================================================
# D. 链接 + 统计 (2 tests)
# ============================================================================

class TestPackLinkAndStats:
    """link_to_dataset + get_pack_stats."""

    def test_link_to_dataset(self, pack_eng):
        """D1: 关联 dataset_id 并记录历史."""
        pack = pack_eng.create_data_pack("link-pack", ["a"])
        linked = pack_eng.link_to_dataset(pack.id, "ds_test_001")
        assert linked.dataset_id == "ds_test_001"
        # 历史中有 link_dataset
        actions = [h["action"] for h in linked.route_history]
        assert "link_dataset" in actions

    def test_stats_progress_and_completion(self, pack_eng):
        """D2: 统计 progress_pct + completion_rate 正确."""
        pack = pack_eng.create_data_pack("stats-pack", ["a"])  # 自动 ready
        stats = pack_eng.get_pack_stats(pack.id)
        assert stats["progress_pct"] == STATUS_PROGRESS[PackStatus.READY]  # 10
        assert stats["asset_count"] == 1
        assert stats["has_data"] is True
        # ready 是第 2 阶段, completion = 2/7
        assert abs(stats["completion_rate"] - 2/7) < 0.001


# ============================================================================
# E. Collection 引擎 (RSS / Crawler / API / Import / Backups) — 5 tests
# ============================================================================

class TestCollectionEngine:
    """data_collection_engine 直接调用."""

    def test_rss_feed_crud(self, tmp_data_dir):
        """E1: RSS feed 增删查."""
        result = dce.add_rss_feed({"name": "RSS1", "url": "https://example.com/feed"})
        assert result["success"] is True
        feed_id = result["feed_id"]
        feeds = dce.list_rss_feeds()
        assert any(f["id"] == feed_id for f in feeds)
        # 删除
        del_result = dce.delete_rss_feed(feed_id)
        assert del_result["success"] is True

    def test_rss_refresh(self, tmp_data_dir):
        """E2: RSS 刷新返回 items_refreshed > 0."""
        result = dce.add_rss_feed({"name": "RSS-refresh", "url": "https://example.com/rss2"})
        feed_id = result["feed_id"]
        ref = dce.refresh_rss_feed(feed_id)
        assert ref["success"] is True
        assert ref["items_refreshed"] > 0

    def test_crawler_create_and_list(self, tmp_data_dir):
        """E3: 爬虫任务创建 + 列表."""
        result = dce.create_crawler_job({
            "name": "Crawler1",
            "url": "https://example.com",
            "max_pages": 5,
        })
        assert result["success"] is True
        jobs = dce.list_crawler_jobs()
        assert any(j["id"] == result["job_id"] for j in jobs)

    def test_api_config_save(self, tmp_data_dir):
        """E4: API config 保存 + 列表."""
        result = dce.save_api_config({
            "name": "API-test",
            "endpoint": "https://api.example.com/data",
            "method": "GET",
            "page_size": 50,
        })
        assert result["success"] is True
        configs = dce.list_api_configs()
        assert any(c["id"] == result["config_id"] for c in configs)

    def test_import_history_records(self, tmp_data_dir):
        """E5: import_file 写入 history."""
        # 创建临时 CSV 文件
        csv_path = os.path.join(tmp_data_dir, "test_import.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("col1,col2\nv1,v2\nv3,v4\n")
        result = dce.import_file(csv_path, "csv", "test_dataset")
        # 成功导入
        assert result.get("success") is True or "rows_imported" in str(result.get("data", {}))
        # history 记录
        history = dce.get_ingest_history()
        assert any(h.get("name") == "test_dataset" or h.get("source") == csv_path
                   for h in history)


# ============================================================================
# F. HTTP API 端到端 (4 tests) — 用 FastAPI TestClient
# ============================================================================

class TestPackAPI:
    """pack_routes HTTP API."""

    def test_create_and_get_pack(self, client, monkeypatch, tmp_pack_db):
        """F1: POST /packs 创建, GET /packs/{id} 详情."""
        # 替换默认引擎用临时 DB
        from engines import pack_engine as pe
        monkeypatch.setattr(pe, "_default_engine", None)
        original_init = pe.PackStore.__init__
        def patched_init(self, db_path=None):
            original_init(self, db_path=tmp_pack_db)
        monkeypatch.setattr(pe.PackStore, "__init__", patched_init)
        # 强制重新构建
        pe.reset_engine()

        resp = client.post("/api/v1/packs", json={
            "name": "API-Pack",
            "type": "data_pack",
            "asset_ids": ["img1", "img2"],
            "requirement_id": "REQ-API-1",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        pack_id = data["id"]

        # GET 详情
        resp = client.get(f"/api/v1/packs/{pack_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == pack_id

    def test_route_endpoint(self, client, monkeypatch, tmp_pack_db):
        """F2: POST /packs/{id}/route 返回 target_module."""
        from engines import pack_engine as pe
        monkeypatch.setattr(pe, "_default_engine", None)
        original_init = pe.PackStore.__init__
        monkeypatch.setattr(pe.PackStore, "__init__",
                            lambda self, db_path=None: original_init(self, db_path=tmp_pack_db))
        pe.reset_engine()

        # 创建空 pack (task_pack)
        resp = client.post("/api/v1/packs", json={
            "name": "Route-Test",
            "type": "task_pack",
            "task_type": "annotation",
            "asset_count": 10,
        })
        assert resp.status_code == 201
        pack_id = resp.json()["data"]["id"]

        # route
        resp = client.post(f"/api/v1/packs/{pack_id}/route")
        assert resp.status_code == 200
        assert resp.json()["data"]["target_module"] == "collection"

    def test_transition_illegal_returns_400(self, client, monkeypatch, tmp_pack_db):
        """F3: 非法转换返回 400."""
        from engines import pack_engine as pe
        monkeypatch.setattr(pe, "_default_engine", None)
        original_init = pe.PackStore.__init__
        monkeypatch.setattr(pe.PackStore, "__init__",
                            lambda self, db_path=None: original_init(self, db_path=tmp_pack_db))
        pe.reset_engine()

        resp = client.post("/api/v1/packs", json={
            "name": "Trans-Test",
            "type": "task_pack",
            "task_type": "cleaning",
            "asset_count": 5,
        })
        pack_id = resp.json()["data"]["id"]

        # 非法转换 (task_pack 初始 created → delivered)
        resp = client.post(f"/api/v1/packs/{pack_id}/transition",
                           json={"new_status": "delivered", "reason": "test"})
        assert resp.status_code == 400

    def test_stats_endpoint(self, client, monkeypatch, tmp_pack_db):
        """F4: GET /packs/{id}/stats 返回 progress%."""
        from engines import pack_engine as pe
        monkeypatch.setattr(pe, "_default_engine", None)
        original_init = pe.PackStore.__init__
        monkeypatch.setattr(pe.PackStore, "__init__",
                            lambda self, db_path=None: original_init(self, db_path=tmp_pack_db))
        pe.reset_engine()

        resp = client.post("/api/v1/packs", json={
            "name": "Stats-Test",
            "type": "data_pack",
            "asset_ids": ["a"],
        })
        pack_id = resp.json()["data"]["id"]

        resp = client.get(f"/api/v1/packs/{pack_id}/stats")
        assert resp.status_code == 200
        stats = resp.json()["data"]
        assert "progress_pct" in stats
        assert stats["progress_pct"] >= 10  # 自动 ready


class TestCollectionAPI:
    """collection_routes HTTP API."""

    def test_sources_endpoint(self, client):
        """F5: GET /collection/sources 返回 4 类源结构."""
        resp = client.get("/api/v1/collection/sources")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "rss" in data
        assert "crawler" in data
        assert "api" in data
        assert "import" in data

    def test_create_rss_endpoint(self, client):
        """F6: POST /collection/sources/rss 创建 RSS."""
        resp = client.post("/api/v1/collection/sources/rss", json={
            "name": "TestRSS",
            "url": "https://example.com/feed.xml",
        })
        assert resp.status_code == 201
        assert resp.json()["data"]["name"] == "TestRSS"

    def test_create_crawler_endpoint(self, client):
        """F7: POST /collection/sources/crawler 创建爬虫."""
        resp = client.post("/api/v1/collection/sources/crawler", json={
            "name": "TestCrawler",
            "url": "https://example.com",
            "max_pages": 5,
        })
        assert resp.status_code == 201
        assert resp.json()["data"]["name"] == "TestCrawler"

    def test_backups_list_endpoint(self, client):
        """F8: GET /collection/backups 返回列表."""
        resp = client.get("/api/v1/collection/backups")
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    def test_jobs_list_endpoint(self, client):
        """F9: GET /collection/jobs 返回 jobs 列表."""
        resp = client.get("/api/v1/collection/jobs")
        assert resp.status_code == 200
        assert "jobs" in resp.json()["data"]


# ============================================================================
# G. 集成 (1 test) — pack.route → annotation 链路 + 空包 → collection 链路
# ============================================================================

class TestIntegration:
    """端到端集成测试."""

    def test_data_pack_to_annotation_pipeline(self, client, monkeypatch, tmp_pack_db):
        """G1: data_pack.route → annotation 链路端到端."""
        from engines import pack_engine as pe
        monkeypatch.setattr(pe, "_default_engine", None)
        original_init = pe.PackStore.__init__
        monkeypatch.setattr(pe.PackStore, "__init__",
                            lambda self, db_path=None: original_init(self, db_path=tmp_pack_db))
        pe.reset_engine()

        # 1) 创建数据包
        resp = client.post("/api/v1/packs", json={
            "name": "E2E-Data-Pack",
            "type": "data_pack",
            "asset_ids": ["img1", "img2", "img3", "img4"],
            "requirement_id": "REQ-E2E",
            "project_id": "P-E2E",
        })
        assert resp.status_code == 201
        pack_id = resp.json()["data"]["id"]
        assert resp.json()["data"]["has_data"] is True

        # 2) 智能路由 → annotation
        resp = client.post(f"/api/v1/packs/{pack_id}/route")
        assert resp.status_code == 200
        assert resp.json()["data"]["target_module"] == "annotation"
        assert resp.json()["data"]["target_endpoint"] == "/api/v1/annotation/assign"

        # 3) 状态机: route 已把 ready → in_annotation, 接下来 → annotated
        resp = client.post(f"/api/v1/packs/{pack_id}/transition",
                           json={"new_status": "annotated", "reason": "标注完成"})
        assert resp.status_code == 200

        # 4) 关联数据集
        resp = client.post(f"/api/v1/packs/{pack_id}/link-dataset",
                           json={"dataset_id": "ds_e2e_001"})
        assert resp.status_code == 200
        assert resp.json()["data"]["dataset_id"] == "ds_e2e_001"

        # 5) 统计
        resp = client.get(f"/api/v1/packs/{pack_id}/stats")
        assert resp.status_code == 200
        stats = resp.json()["data"]
        assert stats["progress_pct"] == STATUS_PROGRESS[PackStatus.ANNOTATED]  # 55
        assert stats["linked_dataset"] == "ds_e2e_001"

    def test_empty_pack_to_collection_pipeline(self, client, monkeypatch, tmp_pack_db):
        """G2: 空包 (task_pack).route → collection 链路端到端."""
        from engines import pack_engine as pe
        monkeypatch.setattr(pe, "_default_engine", None)
        original_init = pe.PackStore.__init__
        monkeypatch.setattr(pe.PackStore, "__init__",
                            lambda self, db_path=None: original_init(self, db_path=tmp_pack_db))
        pe.reset_engine()

        # 1) 创建空 task_pack
        resp = client.post("/api/v1/packs", json={
            "name": "E2E-Empty-Pack",
            "type": "task_pack",
            "task_type": "annotation",
            "asset_count": 1000,
            "requirement_id": "REQ-COL",
        })
        assert resp.status_code == 201
        pack_id = resp.json()["data"]["id"]
        assert resp.json()["data"]["has_data"] is False

        # 2) 智能路由 → collection
        resp = client.post(f"/api/v1/packs/{pack_id}/route")
        assert resp.status_code == 200
        assert resp.json()["data"]["target_module"] == "collection"
        assert resp.json()["data"]["target_endpoint"] == "/api/v1/collection/jobs"

        # 3) 创建 RSS 采集源作为采集目标
        resp = client.post("/api/v1/collection/sources/rss", json={
            "name": "E2E-RSS",
            "url": "https://example.com/e2e-feed",
        })
        assert resp.status_code == 201

        # 4) 创建采集 job (rss 类型)
        resp = client.post("/api/v1/collection/jobs", json={
            "source_type": "rss",
            "name": "E2E-Collect-Job",
            "rss": {"name": "E2E-Collect-RSS", "url": "https://example.com/collect"},
        })
        assert resp.status_code == 201

        # 5) 列出采集任务
        resp = client.get("/api/v1/collection/jobs")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1