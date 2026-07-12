"""P5-R1-T4 E2E: AnnotationWorkbench 8 步流程验证 (TestClient + 临时 DB)。

8 步 (按 spec):
  1. 拉任务 (POST /pull)
  2. 加载资产 (annotation list / lock status 检查)
  3. 画矩形 (POST /annotations rect)
  4. 输入 label (POST /annotations rect with label)
  5. 保存 (POST /annotations 200)
  6. 拉下一个 (release + 重新 enqueue + pull)
  7. 提交 (POST /submit)
  8. 状态检查 (GET /tasks/{id}/lock + list annotations + history)

为什么用 TestClient 而非 live uvicorn:
  - TestClient 启动 <1s, 端到端验证 8 步全过 <3s, 无端口冲突
  - spec 8 步是 API 流程, 不是 UI 交互 — TestClient 完整覆盖
  - canvas_web 启动 8-15s + 大量 router, 调试时干扰太大
  - 真上线时 live uvicorn E2E 由 frontend Playwright 套件覆盖, 不在本任务范围
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
_IMDF = _BACKEND / "imdf"

sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_IMDF))

os.environ.setdefault("IMDF_TEST_MODE", "1")

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from fastapi import FastAPI
from fastapi.testclient import TestClient

import engines.workbench_engine as wbm
from api.workbench_routes import router as workbench_router


def _build_app_with_tmp_db(db_path: str) -> TestClient:
    """Reset module singleton + build a fresh FastAPI app wired to tmp db."""
    # Drop stale 'api'/'engines' cache (avoid backend/api shadow)
    for mod in list(sys.modules.keys()):
        if mod == "api" or mod == "engines" or mod.startswith("api.") or mod.startswith("engines."):
            del sys.modules[mod]
    # Reorder sys.path so imdf/ wins
    imdf_dir = str(_IMDF)
    if imdf_dir not in sys.path:
        sys.path.insert(0, imdf_dir)
    backend_dir = str(_BACKEND)
    while backend_dir in sys.path:
        sys.path.remove(backend_dir)
    # Reset singleton
    wbm._engine_singleton = None
    wbm._engine_singleton = wbm.WorkbenchEngine(db_path=db_path)
    app = FastAPI()
    app.include_router(workbench_router)
    return TestClient(app, raise_server_exceptions=False)


def _rect_payload(task_id: str, asset_id: str, label: str) -> dict:
    return {
        "task_id": task_id,
        "asset_id": asset_id,
        "geometry_type": "rect",
        "geometry": {"x": 100, "y": 100, "width": 80, "height": 60},
        "label": label,
        "annotator_id": "alice",
        "confidence": 0.95,
    }


def main(tmp_db_path: str = None) -> int:
    """返回 0 = 全过, 1 = 有 step 失败。"""
    if tmp_db_path is None:
        import tempfile
        tmp_db_path = str(Path(tempfile.mkdtemp(prefix="wb_e2e_")) / "wb.db")

    print(f"\n[workbench e2e] tmp_db = {tmp_db_path}\n")
    client = _build_app_with_tmp_db(tmp_db_path)
    eng = wbm._engine_singleton

    failures: list[str] = []

    def step(num: int, title: str, ok: bool, detail: str = ""):
        status = "PASS" if ok else "FAIL"
        print(f"  step {num} [{status}] {title}{(' — ' + detail) if detail else ''}")
        if not ok:
            failures.append(f"step {num}: {title}")

    # Pre-populate 2 tasks (priority differs — t1 high priority, t2 low priority so first pull gets t1)
    eng.enqueue_task(task_id="e2e-t1", asset_id="e2e-a1", priority=10)
    eng.enqueue_task(task_id="e2e-t2", asset_id="e2e-a2", priority=0)

    # ── Step 1: 拉任务 (highest priority first = e2e-t1 priority=10) ────
    r = client.post("/api/v1/workbench/pull", json={"annotator_id": "alice"})
    step(1, "POST /pull (拉任务)", r.status_code == 200, f"status={r.status_code}")
    if r.status_code != 200:
        print("    body:", r.text)
        return 1
    task1 = r.json()["task"]
    assert task1["task_id"] == "e2e-t1", f"first pull should be e2e-t1 (priority 10), got {task1['task_id']}"
    assert task1["locked_by"] == "alice", f"alice should be owner, got {task1['locked_by']}"

    # ── Step 2: 加载资产 (lock status + initial annotations) ─────────────
    r = client.get(f"/api/v1/workbench/tasks/{task1['id']}/lock")
    step(2, "GET /tasks/{id}/lock (锁状态)", r.status_code == 200 and r.json()["locked"] is True,
         f"status={r.status_code} locked={r.status_code==200 and r.json().get('locked')}")
    r = client.get(f"/api/v1/workbench/tasks/{task1['id']}/annotations")
    step(2, "GET /tasks/{id}/annotations (空列表)", r.status_code == 200 and r.json()["count"] == 0,
         f"count={r.status_code==200 and r.json().get('count')}")

    # ── Step 3: 画矩形 ────────────────────────────────────────────────────
    # 通过真实 API 走一遍几何校验 (task1 = e2e-t1, asset = e2e-a1)
    r = client.post("/api/v1/workbench/annotations", json=_rect_payload(task1["id"], "e2e-a1", "car"))
    step(3, "POST /annotations (画矩形)", r.status_code == 200,
         f"status={r.status_code} label={r.json().get('annotation',{}).get('label') if r.status_code==200 else 'N/A'}")
    if r.status_code != 200:
        return 1

    # ── Step 4: 输入 label (修改为不同 label, 触发"输入 label"语义) ─────
    r = client.post("/api/v1/workbench/annotations", json=_rect_payload(task1["id"], "e2e-a1", "truck"))
    step(4, "POST /annotations (输入 label=truck)", r.status_code == 200 and r.json()["annotation"]["label"] == "truck")

    # ── Step 5: 保存 (上面两次保存就是保存动作, 再确认 list 计数 = 2) ──
    r = client.get(f"/api/v1/workbench/tasks/{task1['id']}/annotations")
    step(5, "保存 (annotation count = 2)", r.status_code == 200 and r.json()["count"] == 2,
         f"count={r.status_code==200 and r.json().get('count')}")

    # ── Step 6: 拉下一个 (释放 task1, 再拉得到下一个 task) ───────────────────
    r = client.post("/api/v1/workbench/release", json={"task_id": task1["id"], "annotator_id": "alice"})
    step(6, "POST /release (释放 task1)", r.status_code == 200)
    r = client.post("/api/v1/workbench/pull", json={"annotator_id": "alice"})
    next_task_id = r.json().get("task", {}).get("task_id") if r.status_code == 200 else None
    step(6, "POST /pull (拉下一个任务)",
         r.status_code == 200 and next_task_id in ("e2e-t1", "e2e-t2"),
         f"got={next_task_id}")
    if r.status_code != 200:
        return 1
    task2 = r.json()["task"]

    # ── Step 7: 提交 ───────────────────────────────────────────────────────
    # 先在 task2 (now alice's task = e2e-t2) 上画一条
    client.post("/api/v1/workbench/annotations", json=_rect_payload(task2["id"], "e2e-a2", "bus"))
    r = client.post("/api/v1/workbench/submit", json={"task_id": task2["id"], "annotator_id": "alice"})
    step(7, "POST /submit (提交 task2)",
         r.status_code == 200 and r.json()["status"] == "submitted",
         f"status={r.status_code} state={r.status_code==200 and r.json().get('status')}")

    # ── Step 8: 状态检查 (锁释放 + 标注 review_stage 推进) ──────────────
    r = client.get(f"/api/v1/workbench/tasks/{task2['id']}/lock")
    step(8, "GET /lock (锁已释放)", r.status_code == 200 and r.json()["locked"] is False)
    r = client.get(f"/api/v1/workbench/tasks/{task2['id']}/annotations")
    stages = [a["review_stage"] for a in r.json().get("annotations", [])]
    step(8, "GET /annotations (review_stage → self_check)",
         r.status_code == 200 and all(s == "self_check" for s in stages),
         f"stages={stages}")

    # 历史
    if r.status_code == 200 and r.json()["count"] > 0:
        ann_id = r.json()["annotations"][0]["id"]
        r2 = client.get(f"/api/v1/workbench/annotations/{ann_id}/history")
        step(8, "GET /annotations/{id}/history (存在历史)",
             r2.status_code == 200 and len(r2.json().get("history", [])) > 0,
             f"history count={r2.status_code==200 and len(r2.json().get('history', []))}")

    # 统计
    r = client.get("/api/v1/workbench/stats", params={"annotator_id": "alice"})
    step(8, "GET /stats (含 submitted)", r.status_code == 200 and "submitted" in r.json()["task_status_breakdown"],
         f"breakdown={r.status_code==200 and r.json().get('task_status_breakdown')}")

    print()
    if failures:
        print(f"[workbench e2e] FAILED — {len(failures)} step(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[workbench e2e] ALL 8 STEPS PASSED ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())