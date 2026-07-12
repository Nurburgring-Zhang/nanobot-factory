"""P5-R1-T4: AnnotationWorkbench engine + routes 测试。

覆盖范围 (≥15 个测试用例):
- 引擎基础:
  1. enqueue + pull 流程
  2. pull 为空时返回 None
  3. release 正常
  4. heartbeat 延长 TTL
  5. lock_status 查询
  6. save rect / polygon / point / obb / keypoint (5 个用例)
  7. 几何校验失败
  8. bulk save 批量
  9. submit 流转
 10. submit 无锁禁止
 11. get_task_annotations
 12. get_annotation_history 版本链
 13. stats
- HTTP 路由 (TestClient + raise_server_exceptions=False):
 14. POST /pull 200
 15. POST /pull 404 (空队列)
 16. POST /annotations 422 (几何校验失败)
 17. POST /annotations 200
 18. POST /submit 403 (非锁拥有者)
 19. POST /submit 200 (正常)
 20. GET /tasks/{id}/lock
 21. GET /stats
 22. POST /annotations/bulk
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_ROOT))

# 强制 in-memory 风格 + 测试模式
os.environ.setdefault("IMDF_TEST_MODE", "1")


@pytest.fixture
def tmp_db(tmp_path) -> Iterator[str]:
    """每个测试一个隔离的 SQLite 文件。"""
    db = str(tmp_path / "workbench_test.db")
    yield db
    # 清理
    try:
        os.unlink(db)
    except OSError:
        pass


@pytest.fixture
def engine(tmp_db):
    # 直接构造,绕过 module-level singleton
    from engines.workbench_engine import WorkbenchEngine
    return WorkbenchEngine(db_path=tmp_db)


# =============================================================================
# 引擎单元测试
# =============================================================================

def test_01_enqueue_and_pull(engine):
    t = engine.enqueue_task(task_id="t-001", asset_id="a-1", priority=5)
    assert t.id
    assert t.status == "pending"
    pulled = engine.pull_next_task("alice")
    assert pulled is not None
    assert pulled.id == t.id
    assert pulled.status == "in_progress"
    assert pulled.locked_by == "alice"


def test_02_pull_empty_returns_none(engine):
    assert engine.pull_next_task("alice") is None


def test_03_release_task(engine):
    t = engine.enqueue_task(task_id="t-002", asset_id="a-2")
    pulled = engine.pull_next_task("alice")
    assert engine.release_task(pulled.id, "alice") is True
    # 释放后,另一个 annotator 可以拉
    next_p = engine.pull_next_task("bob")
    assert next_p is not None
    assert next_p.locked_by == "bob"


def test_04_heartbeat_extends_lock(engine):
    t = engine.enqueue_task(task_id="t-003", asset_id="a-3")
    pulled = engine.pull_next_task("alice")
    assert engine.heartbeat(pulled.id, "alice") is True
    # 别人的心跳被拒
    assert engine.heartbeat(pulled.id, "bob") is False


def test_05_lock_status(engine):
    t = engine.enqueue_task(task_id="t-004", asset_id="a-4")
    pulled = engine.pull_next_task("alice")
    s = engine.lock_status(pulled.id)
    assert s["locked"] is True
    assert s["locked_by"] == "alice"
    assert s["lock_remaining_seconds"] > 0
    assert s["status"] == "in_progress"


def test_06a_save_rect(engine):
    t = engine.enqueue_task(task_id="t-5a", asset_id="a-5a")
    pulled = engine.pull_next_task("alice")
    rec = engine.save_annotation(
        task_id=pulled.id, asset_id="a-5a",
        geometry_type="rect", geometry={"x": 10, "y": 20, "width": 100, "height": 50},
        label="car", annotator_id="alice",
    )
    assert rec.id
    assert rec.geometry_type == "rect"
    assert rec.label == "car"
    assert rec.geometry["width"] == 100


def test_06b_save_polygon(engine):
    t = engine.enqueue_task(task_id="t-5b", asset_id="a-5b")
    pulled = engine.pull_next_task("alice")
    rec = engine.save_annotation(
        task_id=pulled.id, asset_id="a-5b",
        geometry_type="polygon",
        geometry={"points": [[0, 0], [100, 0], [100, 100], [0, 100]]},
        label="building", annotator_id="alice",
    )
    assert rec.geometry_type == "polygon"
    assert len(rec.geometry["points"]) == 4


def test_06c_save_point(engine):
    t = engine.enqueue_task(task_id="t-5c", asset_id="a-5c")
    pulled = engine.pull_next_task("alice")
    rec = engine.save_annotation(
        task_id=pulled.id, asset_id="a-5c",
        geometry_type="point", geometry={"x": 50, "y": 50},
        label="sign", annotator_id="alice",
    )
    assert rec.geometry["x"] == 50


def test_06d_save_obb(engine):
    t = engine.enqueue_task(task_id="t-5d", asset_id="a-5d")
    pulled = engine.pull_next_task("alice")
    rec = engine.save_annotation(
        task_id=pulled.id, asset_id="a-5d",
        geometry_type="obb",
        geometry={"cx": 100, "cy": 100, "w": 60, "h": 20, "angle": 0.5},
        label="plate", annotator_id="alice",
    )
    assert rec.geometry["angle"] == 0.5


def test_06e_save_keypoint(engine):
    t = engine.enqueue_task(task_id="t-5e", asset_id="a-5e")
    pulled = engine.pull_next_task("alice")
    rec = engine.save_annotation(
        task_id=pulled.id, asset_id="a-5e",
        geometry_type="keypoint",
        geometry={"points": [[10, 10], [20, 20], [30, 30]], "labels": ["nose", "eye", "eye"]},
        label="face", annotator_id="alice",
    )
    assert len(rec.geometry["points"]) == 3


def test_07_geometry_validation(engine):
    t = engine.enqueue_task(task_id="t-6", asset_id="a-6")
    pulled = engine.pull_next_task("alice")
    with pytest.raises(ValueError):
        engine.save_annotation(
            task_id=pulled.id, asset_id="a-6",
            geometry_type="rect", geometry={"x": 0, "y": 0, "width": -10, "height": 0},
            label="bad", annotator_id="alice",
        )
    with pytest.raises(ValueError):
        engine.save_annotation(
            task_id=pulled.id, asset_id="a-6",
            geometry_type="polygon", geometry={"points": [[0, 0]]},  # < 3 points
            label="bad", annotator_id="alice",
        )


def test_08_bulk_save(engine):
    t = engine.enqueue_task(task_id="t-7", asset_id="a-7")
    pulled = engine.pull_next_task("alice")
    recs = engine.bulk_save_annotations(
        task_id=pulled.id,
        annotator_id="alice",
        annotations=[
            {"asset_id": "a-7", "geometry_type": "rect",
             "geometry": {"x": 0, "y": 0, "width": 50, "height": 50}, "label": "obj1"},
            {"asset_id": "a-7", "geometry_type": "point",
             "geometry": {"x": 30, "y": 30}, "label": "obj2"},
            {"asset_id": "a-7", "geometry_type": "polygon",
             "geometry": {"points": [[0, 0], [10, 0], [10, 10]]}, "label": "obj3"},
        ],
    )
    assert len(recs) == 3
    assert {r.label for r in recs} == {"obj1", "obj2", "obj3"}


def test_09_submit_flow(engine):
    t = engine.enqueue_task(task_id="t-8", asset_id="a-8")
    pulled = engine.pull_next_task("alice")
    engine.save_annotation(
        task_id=pulled.id, asset_id="a-8",
        geometry_type="rect", geometry={"x": 0, "y": 0, "width": 50, "height": 50},
        label="obj", annotator_id="alice",
    )
    res = engine.submit_task(pulled.id, "alice")
    assert res["status"] == "submitted"
    assert res["annotation_count"] == 1
    # 锁释放
    s = engine.lock_status(pulled.id)
    assert s["locked"] is False
    # 标注 review_stage 从 draft → self_check
    anns = engine.get_task_annotations(pulled.id)
    assert all(a.review_stage == "self_check" for a in anns)


def test_10_submit_requires_lock_owner(engine):
    t = engine.enqueue_task(task_id="t-9", asset_id="a-9")
    pulled = engine.pull_next_task("alice")
    with pytest.raises(PermissionError):
        engine.submit_task(pulled.id, "bob")


def test_11_get_task_annotations(engine):
    t = engine.enqueue_task(task_id="t-10", asset_id="a-10")
    pulled = engine.pull_next_task("alice")
    for i in range(3):
        engine.save_annotation(
            task_id=pulled.id, asset_id="a-10",
            geometry_type="point", geometry={"x": i * 10, "y": i * 10},
            label=f"p{i}", annotator_id="alice",
        )
    anns = engine.get_task_annotations(pulled.id)
    assert len(anns) == 3


def test_12_get_annotation_history_version_chain(engine):
    t = engine.enqueue_task(task_id="t-11", asset_id="a-11")
    pulled = engine.pull_next_task("alice")
    rec1 = engine.save_annotation(
        task_id=pulled.id, asset_id="a-11",
        geometry_type="rect", geometry={"x": 0, "y": 0, "width": 50, "height": 50},
        label="v1", annotator_id="alice",
    )
    # 编辑: 通过 annotation_id 创建新版本
    rec2 = engine.save_annotation(
        task_id=pulled.id, asset_id="a-11",
        geometry_type="rect", geometry={"x": 0, "y": 0, "width": 80, "height": 80},
        label="v2", annotator_id="alice",
        annotation_id=rec1.id,
    )
    assert rec2.parent_annotation_id == rec1.id
    hist = engine.get_annotation_history(rec2.id)
    # 至少应包含: create (rec1), update (rec1)
    actions = {h["action"] for h in hist}
    assert "create" in actions
    assert "update" in actions


def test_13_stats(engine):
    for i in range(3):
        engine.enqueue_task(task_id=f"t-{i}", asset_id=f"a-{i}")
    engine.pull_next_task("alice")
    s = engine.stats("alice")
    assert s["annotator_id"] == "alice"
    assert s["task_status_breakdown"]["pending"] + s["task_status_breakdown"]["in_progress"] == 3
    assert "generated_at" in s


# =============================================================================
# HTTP 路由测试 (FastAPI TestClient)
# =============================================================================

@pytest.fixture
def client(tmp_db):
    """用临时 DB 启动 FastAPI app + workbench router。"""
    import sys
    import os
    import importlib
    # Drop stale 'api' / 'engines' cache (might point at backend/api shadow)
    for mod in list(sys.modules.keys()):
        if mod == "api" or mod == "engines" or mod.startswith("api.") or mod.startswith("engines."):
            del sys.modules[mod]
    # Insert backend/imdf directly into sys.path (workbench_routes lives at backend/imdf/api/)
    imdf_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "imdf"))
    if imdf_dir not in sys.path:
        sys.path.insert(0, imdf_dir)
    # Drop backend/ to avoid shadowing from backend/api
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
    while backend_dir in sys.path:
        sys.path.remove(backend_dir)
    # Drop tests/ root to avoid tests/api shadow
    tests_dir = os.path.abspath(os.path.dirname(__file__))
    while tests_dir in sys.path:
        sys.path.remove(tests_dir)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    # 重置 module singleton 以使用临时 DB
    import engines.workbench_engine as wbm
    wbm._engine_singleton = None
    wbm._engine_singleton = wbm.WorkbenchEngine(db_path=tmp_db)

    from api.workbench_routes import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_14_pull_http_200(client):
    # 触发 singleton 重新初始化 (重置到当前 tmp_db)
    import engines.workbench_engine as wbm
    eng = wbm._engine_singleton
    eng.enqueue_task(task_id="http-1", asset_id="a-http-1")

    res = client.post("/api/v1/workbench/pull", json={"annotator_id": "alice"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert "task" in body
    assert body["task"]["locked_by"] == "alice"


def test_15_pull_http_404_when_empty(client):
    res = client.post("/api/v1/workbench/pull", json={"annotator_id": "ghost"})
    assert res.status_code == 404


def test_16_annotation_http_422_validation(client):
    import engines.workbench_engine as wbm
    eng = wbm._engine_singleton
    eng.enqueue_task(task_id="http-2", asset_id="a-http-2")
    pull_res = client.post("/api/v1/workbench/pull", json={"annotator_id": "alice"})
    task_id = pull_res.json()["task"]["id"]
    # 坏 rect
    res = client.post("/api/v1/workbench/annotations", json={
        "task_id": task_id, "asset_id": "a-http-2",
        "geometry_type": "rect",
        "geometry": {"x": 0, "y": 0, "width": -10, "height": 5},
        "label": "bad",
    })
    assert res.status_code == 422, res.text


def test_17_annotation_http_200(client):
    import engines.workbench_engine as wbm
    eng = wbm._engine_singleton
    eng.enqueue_task(task_id="http-3", asset_id="a-http-3")
    pull_res = client.post("/api/v1/workbench/pull", json={"annotator_id": "alice"})
    task_id = pull_res.json()["task"]["id"]
    res = client.post("/api/v1/workbench/annotations", json={
        "task_id": task_id, "asset_id": "a-http-3",
        "geometry_type": "rect",
        "geometry": {"x": 10, "y": 10, "width": 50, "height": 50},
        "label": "car", "annotator_id": "alice",
    })
    assert res.status_code == 200, res.text
    assert res.json()["annotation"]["label"] == "car"


def test_18_submit_http_403(client):
    import engines.workbench_engine as wbm
    eng = wbm._engine_singleton
    eng.enqueue_task(task_id="http-4", asset_id="a-http-4")
    pull_res = client.post("/api/v1/workbench/pull", json={"annotator_id": "alice"})
    task_id = pull_res.json()["task"]["id"]
    # bob 尝试提交 alice 锁定的任务
    res = client.post("/api/v1/workbench/submit", json={"task_id": task_id, "annotator_id": "bob"})
    assert res.status_code == 403


def test_19_submit_http_200(client):
    import engines.workbench_engine as wbm
    eng = wbm._engine_singleton
    eng.enqueue_task(task_id="http-5", asset_id="a-http-5")
    pull_res = client.post("/api/v1/workbench/pull", json={"annotator_id": "alice"})
    task_id = pull_res.json()["task"]["id"]
    client.post("/api/v1/workbench/annotations", json={
        "task_id": task_id, "asset_id": "a-http-5",
        "geometry_type": "rect",
        "geometry": {"x": 0, "y": 0, "width": 50, "height": 50},
        "label": "x", "annotator_id": "alice",
    })
    res = client.post("/api/v1/workbench/submit", json={"task_id": task_id, "annotator_id": "alice"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "submitted"
    assert body["annotation_count"] == 1


def test_20_lock_status_http(client):
    import engines.workbench_engine as wbm
    eng = wbm._engine_singleton
    eng.enqueue_task(task_id="http-6", asset_id="a-http-6")
    pull_res = client.post("/api/v1/workbench/pull", json={"annotator_id": "alice"})
    task_id = pull_res.json()["task"]["id"]
    res = client.get(f"/api/v1/workbench/tasks/{task_id}/lock")
    assert res.status_code == 200
    body = res.json()
    assert body["locked"] is True
    assert body["locked_by"] == "alice"


def test_21_stats_http(client):
    import engines.workbench_engine as wbm
    eng = wbm._engine_singleton
    eng.enqueue_task(task_id="http-7", asset_id="a-http-7")
    res = client.get("/api/v1/workbench/stats", params={"annotator_id": "alice"})
    assert res.status_code == 200
    body = res.json()
    assert body["annotator_id"] == "alice"
    assert "task_status_breakdown" in body


def test_22_bulk_save_http(client):
    import engines.workbench_engine as wbm
    eng = wbm._engine_singleton
    eng.enqueue_task(task_id="http-8", asset_id="a-http-8")
    pull_res = client.post("/api/v1/workbench/pull", json={"annotator_id": "alice"})
    task_id = pull_res.json()["task"]["id"]
    res = client.post("/api/v1/workbench/annotations/bulk", json={
        "task_id": task_id,
        "annotator_id": "alice",
        "annotations": [
            {"asset_id": "a-http-8", "geometry_type": "rect",
             "geometry": {"x": 0, "y": 0, "width": 50, "height": 50}, "label": "a"},
            {"asset_id": "a-http-8", "geometry_type": "rect",
             "geometry": {"x": 100, "y": 100, "width": 30, "height": 30}, "label": "b"},
        ],
    })
    assert res.status_code == 200
    assert res.json()["saved"] == 2