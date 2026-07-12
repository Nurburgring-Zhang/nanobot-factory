"""P5-R2-T3 P0 修复测试 — 修 T3 4 个 P0 bug

目标: 4 个 P0 契约 bug 的回归测试
- Bug 1: route_pack 非法转换必须抛 InvalidPackTransitionError (HTTP 400)
- Bug 2: job_to_dataset 空采集必须 400 / 非空必须真有 files
- Bug 3: CollectionCenter 实时进度 (前端, 手动验证)
- Bug 4: pack_routes keyword 后端 LIKE 查询

设计:
- 复用现有 T3 测试的临时 SQLite 隔离模式
- mini FastAPI app 验证 HTTP 层
- 临时 data/datasets 目录隔离
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ===== Path setup =====
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMDF_ROOT = PROJECT_ROOT
sys.path.insert(0, str(IMDF_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

# ===== 导入 SUT =====
from engines.pack_engine import (
    PackEngine, PackStore, PackStatus,
    InvalidPackTransitionError, PACK_TRANSITIONS,
    get_engine, reset_engine,
)
from engines import data_collection_engine as dce
from engines.data_collection_engine import (
    get_ingest_history, _log_history,
)
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
    """临时 data/ 目录 (隔离 collection_state.json + dataset storage)."""
    d = tempfile.mkdtemp(prefix="p0_fix_test_")
    orig_data_dir = dce._data_dir
    monkeypatch.setattr(dce, "_data_dir", lambda: d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def tmp_dataset_dir(monkeypatch, tmp_path):
    """临时 data/datasets 目录 — 隔离 DatasetManager."""
    ds_dir = tmp_path / "datasets"
    ds_dir.mkdir(parents=True, exist_ok=True)

    import engines.dataset_manager as dm
    orig_init = dm.DatasetManager.__init__

    def patched_init(self, data_dir: str = "data/datasets"):
        orig_init(self, data_dir=str(ds_dir))

    monkeypatch.setattr(dm.DatasetManager, "__init__", patched_init)
    yield ds_dir


@pytest.fixture
def pack_eng(tmp_pack_db):
    """PackEngine 实例 (隔离 DB)."""
    store = PackStore(db_path=tmp_pack_db)
    return PackEngine(store=store)


@pytest.fixture
def client(tmp_pack_db, tmp_data_dir, tmp_dataset_dir):
    """mini FastAPI app + TestClient (含 pack + collection router)."""
    # 重置默认 engine 让它用 tmp DB
    reset_engine()
    import engines.pack_engine as pe
    pe._default_engine = PackEngine(store=PackStore(db_path=tmp_pack_db))

    app = FastAPI(title="p0-fix-test")
    app.include_router(pack_router)
    app.include_router(collection_router)
    return TestClient(app)


# ============================================================================
# Bug 1: route_pack 非法转换必须抛 InvalidPackTransitionError (HTTP 400)
# ============================================================================

class TestRoutePackInvalidTransition:
    """Bug 1 P0: route_pack 在非法状态机跳转时不能静默 return 200 OK.

    必须显式抛出 InvalidPackTransitionError, API 返回 400 + 详细错误信息.
    """

    def test_delivered_pack_route_raises(self, pack_eng):
        """delivered 是终态, route_pack 必须抛 InvalidPackTransitionError."""
        pack = pack_eng.create_task_pack("terminal", "review", 1)
        # 走到 delivered
        for s in ("ready", "in_annotation", "annotated", "reviewed", "qc_passed", "delivered"):
            pack_eng.update_pack_status(pack.id, s)
        # 现在 route 必须抛
        with pytest.raises(InvalidPackTransitionError) as exc_info:
            pack_eng.route_pack(pack.id)
        err = exc_info.value
        assert err.current == "delivered"
        assert err.target in ("in_annotation", "ready")
        assert "delivered" in err.allowed or len(err.allowed) == 0

    def test_route_pack_api_returns_400_on_illegal(self, client, tmp_pack_db):
        """HTTP 层: route_pack 非法转换 → 400 + error=invalid_transition."""
        # 创建一个 pack
        r = client.post("/api/v1/packs", json={
            "name": "test-route-illegal",
            "type": "task_pack",
            "task_type": "review",
        })
        assert r.status_code == 201, r.text
        pack_id = r.json()["data"]["id"]

        # 走到 delivered
        for s in ("ready", "in_annotation", "annotated", "reviewed", "qc_passed", "delivered"):
            r2 = client.post(
                f"/api/v1/packs/{pack_id}/transition",
                json={"new_status": s, "reason": "test"},
            )
            assert r2.status_code == 200, f"transition to {s} failed: {r2.text}"

        # 现在 route 必须 400
        r3 = client.post(f"/api/v1/packs/{pack_id}/route")
        assert r3.status_code == 400, f"expected 400, got {r3.status_code}: {r3.text}"
        body = r3.json()
        # FastAPI HTTPException detail
        detail = body.get("detail", body)
        assert detail.get("error") == "invalid_transition"
        assert "current" in detail
        assert "target" in detail
        assert "allowed" in detail


# ============================================================================
# Bug 2: job_to_dataset 空采集 → 400, 非空 → 真有 files
# ============================================================================

class TestJobToDatasetEmptyAndReal:
    """Bug 2 P0: job_to_dataset 必须拒绝空采集 + 非空真写文件.

    - items_collected == 0 → 400 + error=empty_job
    - items_collected > 0 → storage_dir 真有 item_NNNNNN.json 文件
    """

    def test_empty_job_returns_400(self, client, tmp_data_dir):
        """空采集 job → HTTP 400 + error=empty_job."""
        # 构造一个空采集历史 (items_collected=0)
        _log_history({
            "id": "job_empty_001",
            "type": "rss",
            "name": "empty_rss",
            "source": "https://example.com/empty.rss",
            "status": "added",
            "items_collected": 0,
        })

        r = client.post("/api/v1/collection/jobs/job_empty_001/to-dataset")
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
        body = r.json()
        detail = body.get("detail", body)
        assert detail.get("error") == "empty_job"
        assert "采集为空" in detail.get("message", "")
        assert detail.get("items_collected") == 0

    def test_non_empty_job_writes_real_files(self, client, tmp_data_dir, tmp_dataset_dir):
        """非空 job → 真有 files 写到 storage."""
        _log_history({
            "id": "job_full_001",
            "type": "rss",
            "name": "full_rss",
            "source": "https://example.com/full.rss",
            "status": "refreshed",
            "items_collected": 12,
        })

        r = client.post("/api/v1/collection/jobs/job_full_001/to-dataset")
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("success") is True
        data = body.get("data", {})
        assert data.get("items_collected") == 12
        assert data.get("items_written") == 12

        # storage_dir 真有文件
        storage_dir = Path(data["storage_dir"])
        assert storage_dir.exists(), f"storage dir not created: {storage_dir}"
        item_files = list(storage_dir.glob("item_*.json"))
        assert len(item_files) == 12, f"expected 12 item files, got {len(item_files)}"
        # manifest
        manifest = storage_dir / "_manifest.json"
        assert manifest.exists()
        m = json.loads(manifest.read_text(encoding="utf-8"))
        assert m["items_collected"] == 12
        assert m["items_written"] == 12
        assert m["job_id"] == "job_full_001"


# ============================================================================
# Bug 4: pack_routes keyword 后端 LIKE 查询
# ============================================================================

class TestListPacksWithKeyword:
    """Bug 4 P0: GET /packs?keyword=xxx 走 LIKE 模糊查询."""

    def test_list_packs_with_keyword_match(self, client, tmp_pack_db):
        """keyword 命中部分 name → 仅返回匹配项."""
        # 创 3 个 pack
        for name, ptype in [
            ("alpha-data-pack", "data_pack"),
            ("beta-image-pack", "data_pack"),
            ("gamma-task-pack", "task_pack"),
        ]:
            body = {"name": name, "type": ptype}
            if ptype == "task_pack":
                body["task_type"] = "annotation"
            r = client.post("/api/v1/packs", json=body)
            assert r.status_code == 201, r.text

        # 全量
        r = client.get("/api/v1/packs")
        assert r.status_code == 200
        assert r.json()["total"] == 3

        # keyword="alpha" → 1
        r = client.get("/api/v1/packs", params={"keyword": "alpha"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "alpha-data-pack"

        # keyword="pack" → 3 (all)
        r = client.get("/api/v1/packs", params={"keyword": "pack"})
        assert r.json()["total"] == 3

        # keyword="notexist" → 0
        r = client.get("/api/v1/packs", params={"keyword": "notexist_xyz"})
        assert r.json()["total"] == 0

    def test_list_packs_keyword_with_status_filter(self, client, tmp_pack_db):
        """keyword + status 组合过滤."""
        # data_pack with assets → 自动 ready
        r = client.post("/api/v1/packs", json={
            "name": "alpha-dp", "type": "data_pack", "asset_ids": ["a1"],
        })
        assert r.status_code == 201
        # task_pack → 初始 created
        r2 = client.post("/api/v1/packs", json={
            "name": "alpha-tp", "type": "task_pack", "task_type": "annotation",
        })
        assert r2.status_code == 201

        # alpha + ready (data_pack 自动 ready) → 1
        r = client.get("/api/v1/packs", params={"keyword": "alpha", "status": "ready"})
        assert r.status_code == 200
        assert r.json()["total"] == 1
        # alpha + created (task_pack 初始 created) → 1
        r = client.get("/api/v1/packs", params={"keyword": "alpha", "status": "created"})
        assert r.json()["total"] == 1

    def test_list_packs_keyword_engine_level(self, pack_eng):
        """Engine 层: list_packs(keyword=...) 直接走 LIKE."""
        pack_eng.create_data_pack("hello-world", ["a1"])
        pack_eng.create_data_pack("foo-bar", ["a2"])
        pack_eng.create_task_pack("hello-task", "annotation", 5)

        # keyword="hello" → 2
        items, total = pack_eng.list_packs(keyword="hello")
        assert total == 2
        names = sorted(p.name for p in items)
        assert names == ["hello-task", "hello-world"]

        # 无 keyword → 3
        items, total = pack_eng.list_packs()
        assert total == 3


# ============================================================================
# Bug 3 占位: 实时进度为前端 setInterval, 单元测试不覆盖
# (前端 vue-tsc + 浏览器手动验证, 见 deliverable.md)
# ============================================================================
