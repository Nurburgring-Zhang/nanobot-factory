"""R2-Worker-5: 22 端点集成测试 — bad_params 应返回 4xx

测试策略:
  - 不启动完整 canvas_web (100+ 子模块加载太慢, 留给 final gate)
  - 直接 import 各路由模块, 用 FastAPI APIRouter 装载, 通过 TestClient 测试
  - 每个端点跑 1-3 个 bad_params 用例, 期望 4xx

依赖: 必须把 backend/imdf/ 放在 sys.path 第一位, 同时**移除** backend/
  (避免 backend/api/ 抢匹配 'api' 包 — 与 R1 路径设置一致)
"""
import os
import sys
import json
from pathlib import Path

# 关键路径修复: 跟 R1 test_p0_endpoints.py 同样的处理
_IMDF_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/imdf
_BACKEND_ROOT = str(_IMDF_ROOT.parent)                     # backend
sys.path[:] = [p for p in sys.path if p != _BACKEND_ROOT]
if str(_IMDF_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMDF_ROOT))

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

# 路由 imports
from api.routes_extended import stats_router
from api.monitor_routes import router as monitor_router
from api.ops_dashboard_routes import router as ops_router
from api.audit_routes import router as audit_router
from api.personnel_routes import router as personnel_router
from api.pe_routes import router as pe_router
from api.dam_routes import router as dam_router
from api.template_routes import router as template_router
from api.quality_v2_routes import router as quality_v2_router
from api.webhook_routes import router as webhook_router


# ============================================================
# Section 1: 构建测试 app — 装载 R2-5 涉及的 22 端点
# ============================================================


def _build_app():
    """构建一个 minimal FastAPI app, 装载 R2-5 涉及的 22 端点"""
    app = FastAPI()

    # 全局 RequestValidationError handler — Pydantic 自动 422
    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request, exc):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    app.include_router(stats_router)
    app.include_router(monitor_router)
    app.include_router(ops_router)
    app.include_router(audit_router)
    app.include_router(personnel_router)
    app.include_router(pe_router)
    app.include_router(dam_router)
    app.include_router(template_router)
    app.include_router(quality_v2_router)
    app.include_router(webhook_router)
    return app


@pytest.fixture(scope="module")
def client():
    app = _build_app()
    return TestClient(app, raise_server_exceptions=False)


# ============================================================
# Section 2: 22 端点 × bad_params 测试
# ============================================================


# 通用 422 输入:
INVALID_DATE = "not-a-date"
INVALID_DATE_FUTURE = "2099-01-01"
INVALID_PRESET = "5d"
INVALID_GRANULARITY = "second"  # 不在白名单 (hour/day/week/month/quarter/year)
INVALID_DIMENSION = "user.password"  # SQL 注入式
INVALID_PERIOD = "yearly"  # 不在白名单 (today/week/month/all)


# --- 1) /api/stats/daily / weekly / monthly / compare (4) ---

class TestStatsEndpoints:
    """routes_extended.py stats_router — 4 端点"""

    def test_stats_daily_rejects_invalid_granularity(self, client):
        r = client.get(f"/api/stats/daily?granularity={INVALID_GRANULARITY}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_stats_daily_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/stats/daily?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_stats_weekly_rejects_invalid_preset(self, client):
        r = client.get(f"/api/stats/weekly?preset={INVALID_PRESET}")
        # preset 不在 7d/30d/1d/90d/1y/custom → Pydantic ValidationError → 422
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_stats_monthly_rejects_invalid_granularity(self, client):
        r = client.get(f"/api/stats/monthly?granularity={INVALID_GRANULARITY}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_stats_compare_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/stats/compare?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_stats_daily_rejects_invalid_date_range(self, client):
        """custom + start > end → 422"""
        r = client.get(
            "/api/stats/daily?preset=custom&start=2024-01-10&end=2024-01-01"
        )
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_stats_daily_accepts_legal_request(self, client):
        """合法请求 200 (数据库可能无数据, 但 endpoint 不应该 5xx)"""
        r = client.get("/api/stats/daily?preset=7d&granularity=day&dimension=user")
        # 由于是真实 DB 调用, 200/500 都有可能, 但**不能**是 4xx (验证层没拒绝合法输入)
        assert r.status_code not in (400, 422), f"合法请求被 4xx 拒绝: {r.text[:200]}"


# --- 2) /api/monitor/pipeline / history (2) ---

class TestMonitorEndpoints:
    def test_monitor_pipeline_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/monitor/pipeline?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_monitor_pipeline_rejects_invalid_preset(self, client):
        r = client.get(f"/api/monitor/pipeline?preset={INVALID_PRESET}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_monitor_history_rejects_invalid_granularity(self, client):
        r = client.get(f"/api/monitor/history?granularity={INVALID_GRANULARITY}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_monitor_history_rejects_invalid_minutes(self, client):
        """minutes 已有 ge=1 le=1440, 超出范围 422"""
        r = client.get("/api/monitor/history?minutes=99999")
        assert r.status_code == 422, f"expected 422, got {r.status_code}"


# --- 3) /api/ops/overview / trend (2) ---

class TestOpsEndpoints:
    def test_ops_overview_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/ops/overview?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_ops_overview_rejects_invalid_preset(self, client):
        r = client.get(f"/api/ops/overview?preset={INVALID_PRESET}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_ops_trend_rejects_invalid_period(self, client):
        """period 已有 pattern=^(7d|30d)$, 非 7d/30d → 422"""
        r = client.get("/api/ops/trend?period=yearly")
        assert r.status_code == 422, f"expected 422, got {r.status_code}"

    def test_ops_trend_rejects_invalid_granularity(self, client):
        r = client.get(f"/api/ops/trend?granularity={INVALID_GRANULARITY}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"


# --- 4) /api/v1/audit-logs + /stats (2) ---

class TestAuditEndpoints:
    def test_audit_logs_rejects_invalid_method(self, client):
        """method 枚举白名单 GET/POST/PUT/PATCH/DELETE, 其它 → 422"""
        r = client.get("/api/v1/audit-logs?method=HACK")
        assert r.status_code == 422, f"expected 422, got {r.status_code}"

    def test_audit_logs_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/v1/audit-logs?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_audit_logs_rejects_invalid_date_range(self, client):
        """custom + start>end → 422"""
        r = client.get(
            "/api/v1/audit-logs?preset=custom&start=2024-06-01&end=2024-01-01"
        )
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_audit_stats_rejects_invalid_granularity(self, client):
        r = client.get(f"/api/v1/audit-logs/stats?granularity={INVALID_GRANULARITY}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_audit_stats_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/v1/audit-logs/stats?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"


# --- 5) /api/stats/personnel + log + /personnel/{name} (3) ---

class TestPersonnelEndpoints:
    def test_personnel_rejects_invalid_period(self, client):
        """period 不在 today/week/month/all → 422"""
        r = client.get("/api/stats/personnel?period=yearly")
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:200]}"

    def test_personnel_rejects_invalid_action(self, client):
        """action 不在白名单 → 400"""
        r = client.get("/api/stats/personnel?action=delete_all")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_personnel_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/stats/personnel?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_personnel_log_rejects_empty_name(self, client):
        """name 必填, 缺失 → 422"""
        r = client.post("/api/stats/personnel/log", json={"action": "annotate"})
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:200]}"

    def test_personnel_log_rejects_invalid_action(self, client):
        r = client.post(
            "/api/stats/personnel/log",
            json={"name": "alice", "action": "INVALID_ACTION"},
        )
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_personnel_log_rejects_huge_item_count(self, client):
        """item_count > 1_000_000 → 422"""
        r = client.post(
            "/api/stats/personnel/log",
            json={"name": "alice", "action": "annotate", "item_count": 9999999},
        )
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:200]}"

    def test_personnel_detail_rejects_invalid_period(self, client):
        r = client.get("/api/stats/personnel/alice?period=yearly")
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:200]}"


# --- 6) /api/pe/stats (1) ---

class TestPeEndpoints:
    def test_pe_stats_rejects_invalid_granularity(self, client):
        r = client.get(f"/api/pe/stats?granularity={INVALID_GRANULARITY}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_pe_stats_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/pe/stats?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_pe_stats_rejects_invalid_preset(self, client):
        r = client.get(f"/api/pe/stats?preset={INVALID_PRESET}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"


# --- 7) /api/dam/stats (1) ---

class TestDamEndpoints:
    def test_dam_stats_rejects_invalid_granularity(self, client):
        r = client.get(f"/api/dam/stats?granularity={INVALID_GRANULARITY}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_dam_stats_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/dam/stats?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"


# --- 8) /api/templates/{stats,popular,top-rated} (3) ---

class TestTemplatesEndpoints:
    def test_templates_stats_rejects_invalid_granularity(self, client):
        r = client.get(f"/api/templates/stats?granularity={INVALID_GRANULARITY}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_templates_stats_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/templates/stats?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_templates_popular_rejects_huge_limit(self, client):
        """limit 已有 ge=1 le=50, 超出 → 422"""
        r = client.get("/api/templates/popular?limit=99999")
        assert r.status_code == 422, f"expected 422, got {r.status_code}"

    def test_templates_popular_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/templates/popular?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_templates_top_rated_rejects_huge_limit(self, client):
        r = client.get("/api/templates/top-rated?limit=99999")
        assert r.status_code == 422, f"expected 422, got {r.status_code}"

    def test_templates_top_rated_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/templates/top-rated?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"


# --- 9) /api/quality/v2/review/queue-stats + /summary (2) ---

class TestQualityV2Endpoints:
    def test_queue_stats_rejects_invalid_granularity(self, client):
        r = client.get(f"/api/quality/v2/review/queue-stats?granularity={INVALID_GRANULARITY}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_queue_stats_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/quality/v2/review/queue-stats?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_summary_rejects_invalid_granularity(self, client):
        r = client.get(f"/api/quality/v2/summary?granularity={INVALID_GRANULARITY}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_summary_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/quality/v2/summary?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"


# --- 10) /api/v1/webhooks/deliveries/stats (1) ---

class TestWebhookStatsEndpoint:
    def test_deliveries_stats_rejects_invalid_granularity(self, client):
        r = client.get(f"/api/v1/webhooks/deliveries/stats?granularity={INVALID_GRANULARITY}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"

    def test_deliveries_stats_rejects_invalid_dimension(self, client):
        r = client.get(f"/api/v1/webhooks/deliveries/stats?dimension={INVALID_DIMENSION}")
        assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"
