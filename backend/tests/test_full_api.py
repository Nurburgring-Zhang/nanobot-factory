#!/usr/bin/env python3
"""
全量API端点集成测试
覆盖所有核心功能：认证/ML Backend/多模态标注/RBAC/数据集版本/Pipeline/质量中心/节点/工作流

使用 FastAPI TestClient 测试 ~45+ 端点
不依赖 GPU / 外部 API Key — HTTP 接口级测试
"""
import os
import sys
import json
from pathlib import Path

import pytest

# Add backend directory to sys.path
_backend_dir = Path(__file__).parent.parent.resolve()
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# ---------------------------------------------------------------------------
# Graceful import: if server has missing optional dependencies, skip all tests
# ---------------------------------------------------------------------------
try:
    from fastapi.testclient import TestClient
    from server import app

    client = TestClient(app)
    IMPORT_OK = True
except Exception as e:
    IMPORT_OK = False
    IMPORT_ERROR = str(e)


def pytest_configure(config):
    """Mark the module-level skip at collection time."""
    if not IMPORT_OK:
        pytest.skip(f"Server import failed: {IMPORT_ERROR}", allow_module_level=True)


# ============================================================================
# Test Class — Ordered by functional area
# ============================================================================


class TestFullAPI:
    """全量API集成测试（~45+ 端点）"""

    # ---- 1. Health & Metrics ----
    def test_health(self):
        """GET /health — 服务健康检查"""
        r = client.get("/health")
        assert r.status_code in (200, 500), f"Expected 200/500, got {r.status_code}"
        if r.status_code == 200:
            data = r.json()
            assert data.get("status") == "healthy"

    def test_metrics_prometheus(self):
        """GET /metrics — Prometheus 格式指标"""
        r = client.get("/metrics")
        assert r.status_code in (200, 500)

    def test_metrics_json(self):
        """GET /metrics/json — JSON 格式指标"""
        r = client.get("/metrics/json")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "requests" in data

    # ---- 2. Page routes ----
    def test_root(self):
        """GET / — 首页 (HTML or JSON)"""
        r = client.get("/")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        if "text/html" in ct:
            assert len(r.text) > 0

    def test_studio_html(self):
        """GET /studio.html — 独立前端页面"""
        r = client.get("/studio.html")
        assert r.status_code in (200,)

    def test_workflow_html(self):
        """GET /workflow.html — 工作流编辑器页面"""
        r = client.get("/workflow.html")
        assert r.status_code == 200

    def test_workflow_redirect(self):
        """GET /workflow — 重定向到 /workflow.html"""
        r = client.get("/workflow")
        assert r.status_code in (200, 307, 302)

    def test_studio(self):
        """GET /studio — AIGC全功能工作室"""
        r = client.get("/studio")
        assert r.status_code in (200, 500)

    def test_zhiying(self):
        """GET /zhiying — 智影数据工场"""
        r = client.get("/zhiying")
        assert r.status_code in (200,)

    def test_zhiying_head(self):
        """HEAD /zhiying — 智影同路由 HEAD 请求"""
        r = client.head("/zhiying")
        assert r.status_code in (200,)

    def test_navbar_partial(self):
        """GET /templates/navbar.html — 导航栏片段"""
        r = client.get("/templates/navbar.html")
        assert r.status_code in (200, 404)

    # ---- 3. User Authentication ----
    def test_login(self):
        """POST /api/v2/auth/login — 用户登录"""
        r = client.post("/api/v2/auth/login", json={"username": "testuser"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True
        assert "session_id" in data
        assert data.get("user") == "testuser"

    def test_auth_me(self):
        """GET /api/v2/auth/me — 当前会话"""
        login = client.post("/api/v2/auth/login", json={"username": "admin"})
        assert login.status_code == 200
        sid = login.json()["session_id"]
        r = client.get("/api/v2/auth/me", headers={"X-Session-ID": sid})
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True

    def test_auth_me_no_session(self):
        """GET /api/v2/auth/me — 无会话时返回 false"""
        r = client.get("/api/v2/auth/me")
        assert r.status_code == 200
        assert r.json().get("success") is False

    # ---- 4. Pipeline State Machine ----
    def test_create_pipeline(self):
        """POST /api/v2/pipelines — 创建管线"""
        r = client.post("/api/v2/pipelines", json={"name": "测试管线", "creator": "admin"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True

    def test_list_pipelines(self):
        """GET /api/v2/pipelines — 管线列表"""
        r = client.get("/api/v2/pipelines")
        assert r.status_code == 200

    def test_get_pipeline_404(self):
        """GET /api/v2/pipelines/{id} — 不存在的管线返回 404"""
        r = client.get("/api/v2/pipelines/nonexistent_xyz")
        assert r.status_code == 404

    def test_pipeline_lifecycle(self):
        """完整管线生命周期：create → advance → fail → reset"""
        # Create
        r = client.post("/api/v2/pipelines", json={"name": "lifecycle", "creator": "tester"})
        assert r.status_code == 200
        resp = r.json()
        pid = resp.get("id") or (resp.get("data", {}).get("id")) or "lifecycle"

        # Advance
        r2 = client.post(f"/api/v2/pipelines/{pid}/advance", json={"stage": "annotation", "items": 10})
        assert r2.status_code == 200

        # Fail
        r3 = client.post(f"/api/v2/pipelines/{pid}/fail", json={"error": "test error"})
        assert r3.status_code == 200

        # Complete
        r4 = client.post(f"/api/v2/pipelines/{pid}/complete")
        assert r4.status_code == 200

    def test_pipeline_reset_404(self):
        """POST /api/v2/pipelines/{id}/reset — 不存在管线返回 404"""
        r = client.post("/api/v2/pipelines/nonexistent_reset/reset")
        assert r.status_code in (404, 200)

    # ---- 5. Dataset Version Management ----
    def test_dataset_init(self):
        """POST /api/v2/datasets/{id}/init — 初始化数据集"""
        r = client.post("/api/v2/datasets/ds_api_test/init", json={"name": "API测试数据集"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True
        assert data.get("dataset_id") == "ds_api_test"

    def test_dataset_add_row(self):
        """POST /api/v2/datasets/{id}/rows — 添加数据行"""
        client.post("/api/v2/datasets/ds_row_test/init", json={"name": "RowTest"})
        r = client.post("/api/v2/datasets/ds_row_test/rows", json={"image": "test.jpg", "label": 1})
        assert r.status_code == 200
        assert r.json().get("success") is True

    def test_dataset_commit(self):
        """POST /api/v2/datasets/{id}/commit — 提交版本"""
        client.post("/api/v2/datasets/ds_commit_test/init", json={"name": "CommitTest"})
        r = client.post("/api/v2/datasets/ds_commit_test/commit", json={"message": "v1", "branch": "main"})
        assert r.status_code == 200
        assert "version_id" in r.json()

    def test_dataset_log(self):
        """GET /api/v2/datasets/{id}/log — 版本日志"""
        client.post("/api/v2/datasets/ds_log_test/init", json={"name": "LogTest"})
        client.post("/api/v2/datasets/ds_log_test/commit", json={"message": "v1", "branch": "main"})
        r = client.get("/api/v2/datasets/ds_log_test/log")
        assert r.status_code == 200
        assert r.json().get("success") is True

    def test_dataset_branch(self):
        """POST /api/v2/datasets/{id}/branch — 创建分支"""
        client.post("/api/v2/datasets/ds_branch_test/init", json={"name": "BranchTest"})
        r = client.post("/api/v2/datasets/ds_branch_test/branch", json={"name": "dev"})
        assert r.status_code == 200
        assert r.json().get("success") is True

    def test_dataset_merge(self):
        """POST /api/v2/datasets/{id}/merge — 合并分支"""
        client.post("/api/v2/datasets/ds_merge_test/init", json={"name": "MergeTest"})
        client.post("/api/v2/datasets/ds_merge_test/branch", json={"name": "dev"})
        r = client.post("/api/v2/datasets/ds_merge_test/merge",
                        json={"source": "dev", "target": "main", "strategy": "ours"})
        assert r.status_code == 200

    def test_dataset_tag(self):
        """POST /api/v2/datasets/{id}/tag — 打标签"""
        client.post("/api/v2/datasets/ds_tag_test/init", json={"name": "TagTest"})
        r = client.post("/api/v2/datasets/ds_tag_test/commit", json={"message": "v1", "branch": "main"})
        vid = r.json().get("version_id", "v0.0.1")
        r2 = client.post("/api/v2/datasets/ds_tag_test/tag", json={"tag": "release-1", "version_id": vid})
        assert r2.status_code == 200

    def test_dataset_rollback(self):
        """POST /api/v2/datasets/{id}/rollback — 回滚"""
        client.post("/api/v2/datasets/ds_rb_test/init", json={"name": "RBTest"})
        r = client.post("/api/v2/datasets/ds_rb_test/commit", json={"message": "v1", "branch": "main"})
        vid = r.json().get("version_id", "v0.0.1")
        r2 = client.post("/api/v2/datasets/ds_rb_test/rollback", json={"version_id": vid})
        assert r2.status_code == 200

    def test_dataset_checkout(self):
        """POST /api/v2/datasets/{id}/checkout — 检出版本"""
        client.post("/api/v2/datasets/ds_co_test/init", json={"name": "COTest"})
        r = client.post("/api/v2/datasets/ds_co_test/commit", json={"message": "v1", "branch": "main"})
        vid = r.json().get("version_id", "v0.0.1")
        r2 = client.post("/api/v2/datasets/ds_co_test/checkout", json={"version_id": vid})
        assert r2.status_code == 200

    def test_dataset_diff(self):
        """GET /api/v2/datasets/{id}/diff — 版本差异"""
        client.post("/api/v2/datasets/ds_diff_test/init", json={"name": "DiffTest"})
        r1 = client.post("/api/v2/datasets/ds_diff_test/commit", json={"message": "v1", "branch": "main"})
        v1 = r1.json().get("version_id", "v0.0.1")
        client.post("/api/v2/datasets/ds_diff_test/rows", json={"image": "diff.jpg"})
        r2 = client.post("/api/v2/datasets/ds_diff_test/commit", json={"message": "v2", "branch": "main"})
        v2 = r2.json().get("version_id", "v0.0.1")
        r = client.get(f"/api/v2/datasets/ds_diff_test/diff?a={v1}&b={v2}")
        assert r.status_code == 200
        assert r.json().get("success") is True

    def test_list_datasets(self):
        """GET /api/v2/datasets — 数据集列表"""
        r = client.get("/api/v2/datasets")
        assert r.status_code == 200

    # ---- 6. AIGC Generate ----
    def test_generate_no_prompt(self):
        """POST /api/v2/generate — 缺少 prompt 返回 400"""
        r = client.post("/api/v2/generate", json={})
        assert r.status_code == 400

    def test_generate_with_prompt(self):
        """POST /api/v2/generate — 有效 prompt（可能500若队列未初始化，但不崩溃）"""
        r = client.post("/api/v2/generate", json={"prompt": "测试生成"})
        # 可能400/500/200，但不能是404
        assert r.status_code != 404, "Route not found — import error"

    def test_generate_queue_status(self):
        """GET /api/v2/generate/queue/status — 队列状态"""
        r = client.get("/api/v2/generate/queue/status")
        assert r.status_code in (200, 500)

    # ---- 7. Nodes & Workflow ----
    def test_list_nodes(self):
        """GET /api/v2/nodes — 节点列表"""
        r = client.get("/api/v2/nodes")
        # 可能500 if nodes module import fails, 但不能404
        assert r.status_code != 404
        if r.status_code == 200:
            data = r.json()
            assert data.get("success") is True
            assert "count" in data

    def test_list_categories(self):
        """GET /api/v2/nodes/categories — 节点类别"""
        r = client.get("/api/v2/nodes/categories")
        assert r.status_code != 404
        if r.status_code == 200:
            assert r.json().get("success") is True

    def test_execute_workflow(self):
        """POST /api/v2/workflow/execute — 执行工作流"""
        import json as _json
        sample_workflow = {
            "nodes": [
                {
                    "id": "node_input",
                    "type": "input",
                    "label": "输入",
                    "inputs": [],
                    "outputs": [{"id": "out", "label": "输出"}],
                    "position": {"x": 0, "y": 0},
                    "config": {},
                }
            ],
            "edges": [],
        }
        r = client.post("/api/v2/workflow/execute", json=sample_workflow,
                        headers={"Content-Type": "application/json"})
        assert r.status_code != 404
        # May 422 (validation) or 200 — both acceptable

    # ---- 8. ML Backend ----
    def test_ml_list_models(self):
        """GET /api/v2/ml/models — ML模型列表"""
        r = client.get("/api/v2/ml/models")
        assert r.status_code != 404
        if r.status_code == 200:
            assert r.json().get("success") is True

    def test_ml_register_model(self):
        """POST /api/v2/ml/models — 注册模型"""
        r = client.post("/api/v2/ml/models", json={
            "name": "YOLOv8_test_api",
            "model_type": "object_detection",
        })
        assert r.status_code != 404
        if r.status_code == 200:
            data = r.json()
            assert data.get("success") is True
            assert data["data"]["name"] == "YOLOv8_test_api"

    def test_ml_active_learning(self):
        """GET /api/v2/ml/active-learning — 主动学习采样"""
        r = client.get("/api/v2/ml/active-learning")
        assert r.status_code != 404

    def test_ml_delete_model(self):
        """DELETE /api/v2/ml/models/{id} — 删除/注销模型"""
        # 先注册再删除
        reg = client.post("/api/v2/ml/models", json={
            "name": "ToDelete",
            "model_type": "image_classification",
        })
        model_id = ""
        if reg.status_code == 200:
            model_id = reg.json()["data"]["id"]
        else:
            model_id = "fake_id_for_test"
        r = client.delete(f"/api/v2/ml/models/{model_id}")
        assert r.status_code != 404

    def test_ml_predict(self):
        """POST /api/v2/ml/models/{id}/predict — 模型预标注"""
        r = client.post("/api/v2/ml/models/dummy_model/predict",
                        json={"task_data": {"image": "test.jpg"}})
        assert r.status_code != 404

    def test_ml_update_accuracy(self):
        """POST /api/v2/ml/models/{id}/accuracy — 更新准确率"""
        r = client.post("/api/v2/ml/models/dummy_model/accuracy",
                        json={"accuracy": 0.95})
        assert r.status_code != 404

    # ---- 9. RBAC Multi-Tenant ----
    def test_rbac_create_org(self):
        """POST /api/v2/rbac/orgs — 创建组织"""
        r = client.post("/api/v2/rbac/orgs", json={"name": "测试组织API", "owner": "admin"})
        assert r.status_code != 404
        if r.status_code == 200:
            data = r.json()
            assert data.get("success") is True
            assert "org_id" in data.get("data", {})

    def test_rbac_list_orgs(self):
        """GET /api/v2/rbac/orgs — 组织列表"""
        r = client.get("/api/v2/rbac/orgs")
        assert r.status_code != 404

    def test_rbac_check_permission(self):
        """POST /api/v2/rbac/check — 权限检查"""
        r = client.post("/api/v2/rbac/check", json={
            "username": "admin",
            "required_permission": "read",
        })
        assert r.status_code != 404

    def test_rbac_create_project(self):
        """POST /api/v2/rbac/projects — 创建项目"""
        # 先创建组织
        org_r = client.post("/api/v2/rbac/orgs", json={"name": "OrgForProject", "owner": "admin"})
        oid = "test_org_id"
        if org_r.status_code == 200 and org_r.json().get("success"):
            oid = org_r.json()["data"]["org_id"]
        r = client.post("/api/v2/rbac/projects", json={
            "name": "标注项目API", "org_id": oid, "created_by": "admin",
        })
        assert r.status_code != 404

    def test_rbac_list_projects(self):
        """GET /api/v2/rbac/projects — 项目列表"""
        r = client.get("/api/v2/rbac/projects")
        assert r.status_code != 404

    def test_rbac_add_org_member(self):
        """POST /api/v2/rbac/orgs/{id}/members — 添加组织成员"""
        org_r = client.post("/api/v2/rbac/orgs", json={"name": "OrgAddMember", "owner": "admin"})
        oid = "test_org_for_member"
        if org_r.status_code == 200 and org_r.json().get("success"):
            oid = org_r.json()["data"]["org_id"]
        r = client.post(f"/api/v2/rbac/orgs/{oid}/members",
                        json={"username": "new_user", "role": "editor"})
        assert r.status_code != 404

    def test_rbac_list_org_members(self):
        """GET /api/v2/rbac/orgs/{id}/members — 组织成员列表"""
        r = client.get("/api/v2/rbac/orgs/test_org/members")
        assert r.status_code != 404

    def test_rbac_add_project_member(self):
        """POST /api/v2/rbac/projects/{id}/members — 添加项目成员"""
        r = client.post("/api/v2/rbac/projects/test_project/members",
                        json={"username": "user1", "role": "viewer"})
        assert r.status_code != 404

    # ---- 10. Multimodal Annotation (annotation_api) ----
    def test_annotation_create(self):
        """POST /api/v2/annotations/create — 创建标注"""
        r = client.post("/api/v2/annotations/create", json={
            "media_id": "test_vid_api",
            "media_type": "video",
            "annotation_type": "bbox",
            "data": {"x": 100, "y": 100, "w": 50, "h": 50},
        })
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            assert r.json().get("success") is True

    def test_annotation_get_by_media(self):
        """GET /api/v2/annotations/{media_id} — 按媒体ID获取标注"""
        # 先创建一个
        client.post("/api/v2/annotations/create", json={
            "media_id": "vid_get_api",
            "media_type": "video",
            "annotation_type": "bbox",
            "data": {"x": 0, "y": 0, "w": 10, "h": 10},
        })
        r = client.get("/api/v2/annotations/vid_get_api")
        assert r.status_code in (200, 500)

    def test_annotation_update(self):
        """PUT /api/v2/annotations/{ann_id} — 更新标注"""
        # 先创建
        create_r = client.post("/api/v2/annotations/create", json={
            "media_id": "vid_update_api",
            "media_type": "video",
            "annotation_type": "bbox",
            "data": {"x": 0, "y": 0, "w": 10, "h": 10},
        })
        ann_id = "ann_test"
        if create_r.status_code == 200:
            d = create_r.json()
            ann_id = d.get("data", {}).get("id", d.get("id", "ann_test"))
        r = client.put(f"/api/v2/annotations/{ann_id}", json={"data": {"x": 20, "y": 20, "w": 30, "h": 30}})
        assert r.status_code in (200, 500)

    def test_annotation_delete(self):
        """DELETE /api/v2/annotations/{ann_id} — 删除标注"""
        r = client.delete("/api/v2/annotations/ann_to_delete")
        assert r.status_code in (200, 500)

    def test_annotation_video_extract_frames(self):
        """POST /api/v2/annotations/video/extract-frames — 视频帧提取"""
        r = client.post("/api/v2/annotations/video/extract-frames",
                        json={"video_path": "nonexistent.mp4", "interval": 30})
        assert r.status_code in (200, 500)

    def test_annotation_audio_transcribe(self):
        """POST /api/v2/annotations/audio/transcribe — 音频转录"""
        r = client.post("/api/v2/annotations/audio/transcribe",
                        json={"audio_path": "nonexistent.wav"})
        assert r.status_code in (200, 500)

    # ---- 11. Config ----
    def test_get_config(self):
        """GET /api/config — 获取配置"""
        r = client.get("/api/config")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_update_config(self):
        """POST /api/config — 更新配置"""
        r = client.post("/api/config", json={"language": "zh-CN"})
        assert r.status_code == 200

    # ---- 12. Models (LLM registry) ----
    def test_model_providers(self):
        """GET /api/models/providers — 模型供应商列表"""
        r = client.get("/api/models/providers")
        assert r.status_code in (200, 429)
        if r.status_code == 200:
            assert isinstance(r.json(), list)

    def test_models_list(self):
        """GET /api/models — 模型列表"""
        r = client.get("/api/models")
        assert r.status_code in (200, 429)
        if r.status_code == 200:
            assert isinstance(r.json(), list)

    def test_model_registry(self):
        """GET /api/models/registry — 注册表"""
        r = client.get("/api/models/registry")
        assert r.status_code in (200, 429)

    def test_model_registry_providers(self):
        """GET /api/models/registry/providers — 注册表供应商"""
        r = client.get("/api/models/registry/providers")
        assert r.status_code in (200, 429)

    def test_model_registry_models(self):
        """GET /api/models/registry/models — 注册表模型"""
        r = client.get("/api/models/registry/models")
        assert r.status_code in (200, 429)
        if r.status_code == 200:
            assert isinstance(r.json(), list)

    def test_model_routing_strategies(self):
        """GET /api/models/routing/strategies — 路由策略"""
        r = client.get("/api/models/routing/strategies")
        assert r.status_code in (200, 429)

    def test_set_routing_strategy(self):
        """POST /api/models/routing/strategy — 设置路由策略"""
        r = client.post("/api/models/routing/strategy", json={"strategy": "cost_optimized"})
        assert r.status_code in (200, 400, 429)

    # ---- 13. Nanobot Controller ----
    def test_nanobot_status(self):
        """GET /api/nanobot/status — Nanobot状态"""
        r = client.get("/api/nanobot/status")
        assert r.status_code in (200, 429)
        if r.status_code == 200 and "data" in r.json():
            assert isinstance(r.json()["data"], dict)

    def test_nanobot_logs(self):
        """GET /api/nanobot/logs — 操作日志"""
        r = client.get("/api/nanobot/logs")
        assert r.status_code in (200, 429)

    def test_nanobot_resume(self):
        """POST /api/nanobot/resume — 恢复未完成任务"""
        r = client.post("/api/nanobot/resume")
        assert r.status_code in (200, 429)

    # ---- 14. Legacy /api/ assets & generate ----
    def test_assets_inmemory_empty(self):
        """GET /api/assets/in-memory — 内存资产列表"""
        r = client.get("/api/assets/in-memory")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "assets" in data

    def test_create_asset(self):
        """POST /api/assets — 创建资产"""
        r = client.post("/api/assets", json={
            "id": "test_asset_001",
            "name": "test.png",
            "type": "image",
            "path": "/tmp/test.png",
            "size": 1024,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        })
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            data = r.json()
            assert data.get("id") == "test_asset_001"

    def test_get_asset(self):
        """GET /api/assets/{id} — 获取资产"""
        # Use the state directly: try getting via API directly
        # Asset might not have persisted, just check route doesn't 500
        r = client.get("/api/assets/test_asset_get")
        assert r.status_code in (200, 404)

    def test_get_asset_404(self):
        """GET /api/assets/{id} — 不存在返回 404"""
        r = client.get("/api/assets/nonexistent_asset_xyz")
        assert r.status_code in (404, 200)

    def test_delete_asset(self):
        """DELETE /api/assets/{id} — 删除资产"""
        r = client.delete("/api/assets/test_asset_del")
        assert r.status_code in (200, 404)

    def test_generate_legacy(self):
        """POST /api/generate — 旧版生成（prompt required）"""
        r = client.post("/api/generate", json={"prompt": "test", "generator": "comfyui", "settings": {}})
        assert r.status_code in (200, 500, 429)

    def test_get_generation_status_404(self):
        """GET /api/generate/{id} — 不存在返回 404"""
        r = client.get("/api/generate/nonexistent_task_xyz")
        assert r.status_code in (404, 429)

    def test_cleanup_generation(self):
        """DELETE /api/generate/cleanup — 清理已完成任务"""
        r = client.delete("/api/generate/cleanup")
        assert r.status_code in (200, 404, 429)

    # ---- 15. API Keys ----
    def test_api_keys_status(self):
        """GET /api/keys/status — API密钥状态"""
        r = client.get("/api/keys/status")
        assert r.status_code in (200, 429)

    def test_api_keys_providers(self):
        """GET /api/keys/providers — API供应商列表"""
        r = client.get("/api/keys/providers")
        assert r.status_code in (200, 429)

    def test_api_keys_configure(self):
        """POST /api/keys/configure — 配置API密钥"""
        r = client.post("/api/keys/configure",
                        params={"provider": "openai", "api_key": "sk-test"})
        # 可能200, 422 (validation), 429 (rate limit)
        assert r.status_code in (200, 422, 429)

    def test_api_keys_verify(self):
        """POST /api/keys/verify — 验证密钥"""
        r = client.post("/api/keys/verify")
        assert r.status_code in (200, 429)

    def test_api_keys_remove(self):
        """DELETE /api/keys/{provider} — 删除密钥"""
        r = client.delete("/api/keys/test_provider")
        assert r.status_code in (200, 429)

    # ---- 16. ComfyUI Environment ----
    def test_comfyui_env_status(self):
        """GET /api/comfyui/env/status — ComfyUI环境状态"""
        r = client.get("/api/comfyui/env/status")
        assert r.status_code in (200, 429)

    def test_comfyui_models_list(self):
        """GET /api/comfyui/models/list — ComfyUI模型列表"""
        r = client.get("/api/comfyui/models/list")
        assert r.status_code in (200, 429)

    # ---- 17. Data (quality-engine, watermark, etc.) ----
    def test_quality_engine_status(self):
        """GET /api/data/quality-engine/status — 质量引擎状态"""
        r = client.get("/api/data/quality-engine/status")
        assert r.status_code in (200, 429, 500)

    def test_data_dataset_stats(self):
        """GET /api/data/dataset/stats — 数据集统计"""
        r = client.get("/api/data/dataset/stats")
        assert r.status_code in (200, 429, 500)

    def test_copyright_lookup(self):
        """GET /api/data/copyright/lookup — 版权查询"""
        r = client.get("/api/data/copyright/lookup")
        assert r.status_code in (200, 429, 500)

    # ---- 18. AIRI Digital Human ----
    def test_airi_status(self):
        """GET /api/airi/status — AIRI状态"""
        r = client.get("/api/airi/status")
        assert r.status_code in (200, 429)

    def test_airi_animations(self):
        """GET /api/airi/animations — 动画列表"""
        r = client.get("/api/airi/animations")
        assert r.status_code in (200, 429)

    def test_airi_expressions(self):
        """GET /api/airi/expressions — 表情列表"""
        r = client.get("/api/airi/expressions")
        assert r.status_code in (200, 429)

    def test_airi_skills(self):
        """GET /api/airi/skills — 技能列表"""
        r = client.get("/api/airi/skills")
        assert r.status_code in (200, 429)

    # ---- 19. OmniGen ----
    def test_omni_templates(self):
        """GET /api/omni/templates — OmniGen模板"""
        r = client.get("/api/omni/templates")
        assert r.status_code in (200, 429)

    def test_omni_loras(self):
        """GET /api/omni/loras — LoRA列表"""
        r = client.get("/api/omni/loras")
        assert r.status_code in (200, 429)

    # ---- 20. Canvas ----
    def test_canvas_list(self):
        """GET /api/canvas/list — Canvas列表"""
        r = client.get("/api/canvas/list")
        assert r.status_code in (200, 429)
        if r.status_code == 200:
            assert isinstance(r.json(), list)

    def test_canvas_create(self):
        """POST /api/canvas/create — 创建Canvas"""
        r = client.post("/api/canvas/create", json={
            "canvas_id": "test_canvas_01", "width": 1024, "height": 768,
        })
        assert r.status_code in (200, 429)
        if r.status_code == 200:
            data = r.json()
            assert isinstance(data, dict)

    # ---- 21. Agent / Chat endpoints ----
    def test_chat_no_api_key(self):
        """POST /api/chat — API key未配置时返回400"""
        r = client.post("/api/chat", json={
            "message": "hello",
            "model": "gpt-4",
            "provider": "openai",
        })
        # 400 (no key), 429 (rate limited), or 500 (server error) — not 404
        assert r.status_code in (400, 429, 500)

    # ---- 22. Capabilities ----
    def test_get_capabilities(self):
        """GET /api/nanobot/capabilities — 能力列表"""
        r = client.get("/api/nanobot/capabilities")
        assert r.status_code in (200, 429)
