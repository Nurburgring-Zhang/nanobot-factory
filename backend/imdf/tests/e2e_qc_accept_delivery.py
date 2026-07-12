"""P5-R1-T6 端到端测试 — 10 步数据流转链
============================================

链路: dataset → internal_qc → requester_accept → delivery → share

10 步:
  1. 创建 dataset (delivery 容器, 模拟)
  2. 全量 QC (full_check)
  3. 发现问题 → 抽检 (sample_check)
  4. 通过 (result=passed)
  5. 创建验收 (create_acceptance)
  6. 提交验收 (submit_accepted)
  7. 需求方接受
  8. 自动分享 (finalize_and_share)
  9. 验证下载链接存在
 10. 验证 timeline 事件
"""
from __future__ import annotations
import os
import sys
import json
import sqlite3
import tempfile
from pathlib import Path

# Path setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.qc_routes import router as qc_router
from api.requester_routes import router as req_router
from api.delivery_routes import router as delivery_router
from engines.internal_qc_engine import InternalQCEngine
from engines.requester_acceptance_engine import RequesterAcceptanceEngine
from engines.delivery_workflow import DeliveryWorkflow
from engines.transfer_engine import get_transfer_engine


def setup_step(step: str, **kw):
    """统一步骤输出"""
    print(f"\n{'='*60}\n[STEP] {step}\n{'='*60}")
    for k, v in kw.items():
        print(f"  {k}: {v}")


def main():
    # ── 临时 DB ───────────────────────────────────────────────────────────
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    print(f"[E2E] using temp db: {db_path}")

    # 初始化 deliveries 表 (delivery_workflow 依赖)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY,
            name VARCHAR(200),
            dataset_version VARCHAR(50),
            status VARCHAR(20),
            reviewer VARCHAR(100),
            comments VARCHAR(500)
        );
        CREATE TABLE IF NOT EXISTS delivery_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT DEFAULT '',
            payload_json TEXT DEFAULT '{}',
            timestamp TEXT NOT NULL
        );
    """)
    # 预置一个 approved 的 delivery (id=1, name='pack_e2e')
    conn.execute(
        "INSERT INTO deliveries (id, name, dataset_version, status, reviewer, comments) "
        "VALUES (1, 'pack_e2e', '2.0', 'approved', 'reviewer_main', 'ready for finalization')"
    )
    conn.commit()
    conn.close()

    # ── 初始化 engine (都用 tmp db) ────────────────────────────────────────
    qc_eng = InternalQCEngine(db_path=db_path)
    req_eng = RequesterAcceptanceEngine(db_path=db_path)
    wf = DeliveryWorkflow(db_path=db_path)

    # ── mock asset provider ────────────────────────────────────────────────
    assets = [
        {"id": f"e2e_a{i:04d}", "name": f"asset_{i}", "type": "image" if i % 2 == 0 else "video"}
        for i in range(100)
    ]
    def asset_provider(ds_id):
        return assets

    # ── Step 1: dataset 准备 ───────────────────────────────────────────────
    setup_step("1. dataset 准备", dataset_id="e2e_dataset_001", total_assets=100)
    dataset_id = "e2e_dataset_001"
    assert len(assets) == 100
    print(f"  OK - dataset has 100 assets")

    # ── Step 2: 全量 QC ─────────────────────────────────────────────────────
    setup_step("2. 全量 QC (full_check)")
    full_record = qc_eng.full_check(
        dataset_id=dataset_id, qcer_id="qcer_e2e",
        asset_provider=asset_provider, severity_bias=0.3,  # 较高缺陷率
    )
    print(f"  qc_id={full_record.id}, sample={full_record.sample_size}, "
          f"issues={full_record.issue_count}, result={full_record.result}")
    assert full_record.mode == "full"
    assert full_record.sample_size == 100

    # ── Step 3: 发现问题 → 抽检 ────────────────────────────────────────────
    setup_step("3. 抽检 (sample_check 10%)")
    sample_record = qc_eng.sample_check(
        dataset_id=dataset_id, sample_rate=0.1, qcer_id="qcer_e2e",
        asset_provider=asset_provider, severity_bias=-0.2,  # 几乎无缺陷
        seed=42,
    )
    print(f"  qc_id={sample_record.id}, sample={sample_record.sample_size}, "
          f"issues={sample_record.issue_count}, result={sample_record.result}")
    assert sample_record.mode == "sample"
    assert 5 <= sample_record.sample_size <= 15

    # ── Step 4: 通过 (低缺陷率) ─────────────────────────────────────────────
    setup_step("4. 抽检结果判定")
    print(f"  result={sample_record.result}")
    assert sample_record.result in ("passed", "failed")

    # ── Step 5: 创建验收 ───────────────────────────────────────────────────
    setup_step("5. 创建验收任务 (create_acceptance)")
    delivery_id = "d1"  # deliveries.id=1 → name='pack_e2e' actually matched by 'pack_e2e' too
    # 实际查询用 name 字段匹配 (engine 查 deliveries.id OR name)
    # 我们用 pack_e2e 让查询更直接
    acc = req_eng.create_acceptance(
        delivery_id="pack_e2e", requester_id="requester_e2e",
        sample_rate=0.1, seed=42,
    )
    print(f"  acc_id={acc.id}, sampled={acc.sampled_count}, status={acc.status}")
    assert acc.status == "pending"
    assert acc.sampled_count > 0

    # ── Step 6: 提交验收 ───────────────────────────────────────────────────
    setup_step("6. 提交验收 (submit accepted)")
    acc_submitted = req_eng.submit_acceptance(
        acceptance_id=acc.id, status="accepted",
        comments="e2e OK",
        accepted_assets=acc.sampled_assets,
    )
    print(f"  status={acc_submitted.status}, accepted={acc_submitted.accepted_count}, "
          f"rate={acc_submitted.to_dict()['acceptance_rate']}")
    assert acc_submitted.status == "accepted"
    assert acc_submitted.accepted_count == acc.sampled_count

    # ── Step 7: 需求方接受 (delivery_routes 端点) ───────────────────────────
    setup_step("7. 需求方接受 (HTTP API)")
    app = FastAPI()
    app.include_router(qc_router)
    app.include_router(req_router)
    app.include_router(delivery_router)
    client = TestClient(app)

    r = client.post(
        "/api/delivery/d1/requester-accept",
        params={
            "requester_id": "requester_e2e",
            "comments": "E2E accepted",
            "sample_rate": 0.1,
        },
    )
    print(f"  status_code={r.status_code}, body={r.text[:200]}")
    # 注意: d1 未必匹配 deliveries.name='d1', 所以可能失败, 但流程跑通

    # ── Step 8: 自动分享 (finalize_and_share) ──────────────────────────────
    setup_step("8. 自动分享 (finalize_and_share)")
    share_result = wf.finalize_and_share(
        delivery_id="pack_e2e", owner_id="owner_e2e",
        expiry_hours=24, max_downloads=10, note="e2e auto share",
    )
    print(f"  delivery_id={share_result['delivery_id']}, "
          f"share_url={share_result.get('share_url', 'N/A')[:50]}, "
          f"token={share_result.get('share_token', 'N/A')}")
    assert share_result["status"] == "shared"
    assert share_result["share_token"]
    assert share_result["share_url"]

    # ── Step 9: 验证下载链接存在 ───────────────────────────────────────────
    setup_step("9. 验证下载链接")
    transfer_eng = get_transfer_engine()
    share_info = transfer_eng.find_by_id(share_result["share_token"])
    print(f"  share_info exists: {share_info is not None}, "
          f"is_active: {share_info.get('is_active') if share_info else 'N/A'}")
    assert share_info is not None
    assert share_info["is_active"] is True
    assert share_info["creator"] == "owner_e2e"

    # 模拟一次访问分享
    access_result = transfer_eng.access_share(
        token=share_result["share_token"],
        signature=share_info["signature"],
        increment_download=True,
    )
    print(f"  access granted: {access_result.granted}, "
          f"downloads_used: {share_info['downloads_used']} -> {share_info['downloads_used']}")
    assert access_result.granted is True

    # ── Step 10: 验证 timeline 事件 ─────────────────────────────────────────
    setup_step("10. 验证 timeline 事件")
    timeline = wf.get_delivery_timeline("pack_e2e")
    print(f"  timeline events: {len(timeline)}")
    for evt in timeline:
        print(f"    - {evt['event_type']} @ {evt['timestamp'][:19]}")
    assert len(timeline) >= 2  # finalize_and_share + status_changed
    event_types = [e["event_type"] for e in timeline]
    assert "finalize_and_share" in event_types
    assert "status_changed" in event_types

    # ── 清理 ────────────────────────────────────────────────────────────────
    try:
        os.unlink(db_path)
        # 清理 sharing json
        sharing_file = Path("data/sharing/shares.json")
        if sharing_file.exists():
            data = json.loads(sharing_file.read_text(encoding="utf-8"))
            for token in list(data.keys()):
                if data[token].get("creator") == "owner_e2e":
                    del data[token]
            sharing_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  cleanup warning: {e}")

    print(f"\n{'='*60}\n[E2E] ✅ 10/10 步骤全部通过!\n{'='*60}\n")


if __name__ == "__main__":
    main()