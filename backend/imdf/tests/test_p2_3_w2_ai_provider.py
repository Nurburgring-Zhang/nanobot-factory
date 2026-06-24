"""P2-3-W2 — AI provider usage / rate limit / circuit breaker / cost tests.

测试范围 (4 大块):
1. **UsageTracker.record + user_summary** — DB 写入 → summary 聚合
2. **rate_limit** — sliding window 限流, 超额拒绝
3. **compute_cost_usd / cost_estimate** — 按 protocol+model 算 USD
4. **circuit_breaker** — 错误率 > 50% 自动 open

降级: DB 不可用 → fallback jsonl, 测试只验 SQLite (没 postgres)。

执行:
    pytest tests/test_p2_3_w2_ai_provider.py -v --tb=short
"""
from __future__ import annotations

import os
import sys
import time
import json
import tempfile
from pathlib import Path

import pytest

# ── sys.path ────────────────────────────────────────────────────────────────
# 关键: backend/tests/conftest.py 已经把 ``backend/`` 加到 sys.path, 这导致
# 它**先于** ``backend/imdf/`` 被搜索, 进而把 ``backend/api/__init__.py`` (空包)
# 加载为 ``api`` 模块, 遮蔽了我们真正的 ``backend/imdf/api/`` 包。
# 修复: 显式把 imdf/ 放在 sys.path 第 0 位, 并清掉已缓存的错误 ``api``。
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) in sys.path:
    sys.path.remove(str(_BACKEND))
sys.path.insert(0, str(_BACKEND))

# 清掉可能被错误 conftest 提前 import 的 ``api`` 包缓存
for _bad in ("api", "api.canvas_web", "api._common", "api.middleware"):
    if _bad in sys.modules:
        del sys.modules[_bad]  # 强制下次 import 重新走 sys.path


@pytest.fixture(autouse=True)
def _clean_api_module_cache():
    """每个测试前重新清掉被错误 conftest 缓存的 ``api`` 包 + 把 imdf/ 移到 sys.path[0]。

    必须在 test body 之前运行, 否则 ``from api.canvas_web import app`` 仍会拿到
    错误的 ``backend/api/__init__.py``。
    """
    # 1. 把 imdf/ 移到 sys.path 第 0 位, 覆盖错误的 backend/
    for _bad in ("api", "api.canvas_web", "api._common", "api.middleware"):
        if _bad in sys.modules:
            del sys.modules[_bad]
    _imdf = str(_BACKEND)
    while _imdf in sys.path:
        sys.path.remove(_imdf)
    sys.path.insert(0, _imdf)
    yield


def _import_canvas_web_app():
    """显式从 backend/imdf/api/canvas_web.py 加载, 绕过 sys.modules 缓存冲突。

    ``backend/tests/conftest.py`` 把 ``backend/`` 加到 sys.path 第 0 位,
    导致 ``backend/api/__init__.py`` (空包) 遮蔽 ``backend/imdf/api/``。
    用 importlib 走绝对路径最稳。
    """
    import importlib.util
    import types

    spec = importlib.util.spec_from_file_location(
        "imdf_api_canvas_web",
        str(_BACKEND / "api" / "canvas_web.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["imdf_api_canvas_web"] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod.app

# ── DB 走临时文件, 不污染 prod imdf_p2.db ────────────────────────────────
_TMP_DB = _BACKEND / "data" / f"test_p2_3_w2_{os.getpid()}.db"
_TMP_DB.parent.mkdir(parents=True, exist_ok=True)
os.environ["IMDF_P2_DB_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
# 强制覆盖, 即使 default 是空


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    from db import init_db, engine
    init_db()
    yield
    # 清理临时 DB
    try:
        engine.dispose()
        for p in (_TMP_DB, _TMP_DB.with_suffix(".db-shm"), _TMP_DB.with_suffix(".db-wal")):
            if p.exists():
                p.unlink()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_global_state():
    """每个测试重置 limiter + breaker + fallback jsonl。"""
    from engines.provider_registry import _GLOBAL_LIMITER, _GLOBAL_BREAKER
    _GLOBAL_LIMITER.reset()
    _GLOBAL_BREAKER.reset()
    fallback = _BACKEND / "data" / "usage_fallback.jsonl"
    if fallback.exists():
        try:
            fallback.unlink()
        except Exception:
            pass
    yield


# ═══════════════════════════════════════════════════════════════════════════
# 1. UsageTracker record + summary
# ═══════════════════════════════════════════════════════════════════════════
class TestUsageTracker:
    def test_record_writes_to_db(self):
        from engines.usage_tracker import UsageTracker
        tracker = UsageTracker.instance()
        log_id = tracker.record(
            user_id="user_alice",
            provider_id="openai-compatible",
            protocol="openai-compatible",
            kind="chat",
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            cost_usd=0.0035,
            latency_ms=1234,
            status="ok",
        )
        assert log_id is not None
        assert log_id.startswith("ul_")
        assert len(log_id) == 3 + 12

    def test_user_summary_aggregates_by_provider(self):
        from engines.usage_tracker import UsageTracker
        tracker = UsageTracker.instance()

        # 2 calls to openai-compatible, 1 to volcengine
        tracker.record(
            user_id="user_bob", provider_id="openai-compatible",
            protocol="openai-compatible", kind="chat", model="gpt-4o",
            prompt_tokens=100, completion_tokens=200, total_tokens=300,
            cost_usd=0.0035, latency_ms=1000, status="ok",
        )
        tracker.record(
            user_id="user_bob", provider_id="openai-compatible",
            protocol="openai-compatible", kind="chat", model="gpt-4o",
            prompt_tokens=50, completion_tokens=80, total_tokens=130,
            cost_usd=0.0014, latency_ms=800, status="ok",
        )
        tracker.record(
            user_id="user_bob", provider_id="volcengine",
            protocol="volcengine", kind="image", model="doubao-seedream-4-0-250828",
            prompt_tokens=10, completion_tokens=0, total_tokens=10,
            cost_usd=0.04, latency_ms=5000, status="ok",
        )

        summary = tracker.user_summary("user_bob", days=30)
        assert summary["total_calls"] == 3
        assert summary["total_tokens"] == 440
        # cost 是浮点累加, 容差 1e-4
        assert abs(summary["total_cost_usd"] - 0.0449) < 1e-3
        # by_provider 至少有 2 个条目
        provs = {p["provider_id"]: p for p in summary["by_provider"]}
        assert "openai-compatible" in provs
        assert "volcengine" in provs
        assert provs["openai-compatible"]["calls"] == 2

    def test_org_summary_aggregates_with_unique_users(self):
        from engines.usage_tracker import UsageTracker
        tracker = UsageTracker.instance()

        for u in ("user_x", "user_y", "user_x"):
            tracker.record(
                user_id=u, org_id="org_acme", provider_id="modelscope",
                protocol="modelscope", kind="chat", model="qwen",
                prompt_tokens=10, completion_tokens=20, total_tokens=30,
                cost_usd=0.0001, latency_ms=500, status="ok",
            )

        summary = tracker.org_summary("org_acme", days=30)
        assert summary["total_calls"] == 3
        assert summary["unique_users"] == 2
        assert summary["scope"] == "org"

    def test_fallback_writes_when_db_fails(self, monkeypatch):
        """DB 不可用 → 写 fallback jsonl。"""
        from engines import usage_tracker as ut

        # 替换 db.SessionLocal 抛异常 (因为 usage_tracker.py 用 ``from db import SessionLocal``)
        import db as _db_mod

        def _broken_session_local():
            raise RuntimeError("simulated DB outage")

        monkeypatch.setattr(_db_mod, "SessionLocal", _broken_session_local)

        log_id = ut.get_tracker().record(
            user_id="user_z", provider_id="openai-compatible",
            protocol="openai-compatible", kind="chat", model="gpt-4o",
            prompt_tokens=10, completion_tokens=20, total_tokens=30,
            cost_usd=0.0001, latency_ms=100, status="ok",
        )
        # 返回 None 表示 DB 写入失败, fallback jsonl 应有数据
        assert log_id is None
        fallback = _BACKEND / "data" / "usage_fallback.jsonl"
        assert fallback.exists()
        content = fallback.read_text(encoding="utf-8").strip()
        assert content  # 非空
        row = json.loads(content.split("\n")[-1])
        assert row["user_id"] == "user_z"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Rate Limit
# ═══════════════════════════════════════════════════════════════════════════
class TestRateLimit:
    def test_within_limit(self):
        from engines.provider_registry import rate_limit
        for i in range(5):
            ok, remaining = rate_limit("user_a", "openai-compatible", per_hour=10)
            assert ok is True
        # 第 6 次 (limit=5 已用 5 次) 应被拒
        ok, remaining = rate_limit("user_a", "openai-compatible", per_hour=5)
        assert ok is False
        assert remaining == 0

    def test_per_user_isolation(self):
        from engines.provider_registry import rate_limit
        for _ in range(3):
            rate_limit("user_one", "p1", per_hour=3)
        # user_one 满了, user_two 不影响
        ok, _ = rate_limit("user_two", "p1", per_hour=3)
        assert ok is True

    def test_per_provider_isolation(self):
        from engines.provider_registry import rate_limit
        for _ in range(3):
            rate_limit("user_c", "pA", per_hour=3)
        # user_c + pA 满了, user_c + pB 不影响
        ok, _ = rate_limit("user_c", "pB", per_hour=3)
        assert ok is True

    def test_env_default_fallback(self, monkeypatch):
        monkeypatch.setenv("AI_RATE_LIMIT_PER_HOUR", "3")
        from engines.provider_registry import rate_limit
        for _ in range(3):
            ok, _ = rate_limit("user_d", "p1")
            assert ok is True
        ok, _ = rate_limit("user_d", "p1")
        assert ok is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. Cost Estimation
# ═══════════════════════════════════════════════════════════════════════════
class TestCostEstimate:
    def test_zero_tokens_zero_cost(self):
        from engines.provider_registry import compute_cost_usd
        assert compute_cost_usd("openai-compatible", "gpt-4o", 0, 0) == 0.0

    def test_known_model_gpt4o(self):
        from engines.provider_registry import compute_cost_usd
        # gpt-4o: input 0.005/1k, output 0.015/1k
        cost = compute_cost_usd("openai-compatible", "gpt-4o", 1000, 1000)
        assert abs(cost - 0.020) < 1e-6  # 0.005 + 0.015

    def test_known_model_deepseek(self):
        from engines.provider_registry import compute_cost_usd
        # deepseek-chat: input 0.00014/1k, output 0.00028/1k
        cost = compute_cost_usd("openai-compatible", "deepseek-chat", 1000, 1000)
        assert abs(cost - 0.00042) < 1e-6

    def test_unknown_model_falls_back_to_wildcard(self):
        from engines.provider_registry import compute_cost_usd
        cost = compute_cost_usd("openai-compatible", "unknown-model-xyz", 1000, 0)
        # openai-compatible *: 0.002/1k → 0.002
        assert abs(cost - 0.002) < 1e-6

    def test_unknown_protocol_falls_back_global(self):
        from engines.provider_registry import compute_cost_usd
        cost = compute_cost_usd("nonexistent", "m", 1000, 1000)
        # global fallback 0.001 + 0.003 = 0.004
        assert abs(cost - 0.004) < 1e-6

    def test_cost_estimate_returns_full_dict(self):
        from engines.provider_registry import cost_estimate
        result = cost_estimate("volcengine", "doubao-seed-1-6-250615", 1000, 500)
        assert "protocol" in result
        assert "model" in result
        assert "input_per_1k_usd" in result
        assert "output_per_1k_usd" in result
        assert "cost_usd" in result
        assert result["cost_usd"] > 0

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("AI_COST_PER_1K_TOKENS", "openai-compatible:custom-model=0.10,0.20")
        from engines.provider_registry import compute_cost_usd
        cost = compute_cost_usd("openai-compatible", "custom-model", 1000, 1000)
        assert abs(cost - 0.30) < 1e-6

    def test_local_providers_free(self):
        from engines.provider_registry import compute_cost_usd
        # comfyui / jimeng-cli 默认 * = (0, 0)
        assert compute_cost_usd("comfyui", "any", 9999, 9999) == 0.0
        assert compute_cost_usd("jimeng-cli", "any", 9999, 9999) == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 4. Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════════
class TestCircuitBreaker:
    def test_default_state_closed(self):
        from engines.provider_registry import circuit_breaker
        snap = circuit_breaker("test-provider-1")
        assert snap["state"] == "closed"
        assert snap["calls"] == 0
        assert snap["errors"] == 0

    def test_below_threshold_stays_closed(self):
        from engines.provider_registry import _GLOBAL_BREAKER, circuit_breaker
        # 10 ok, 2 error → error_rate = 0.2, < 0.5 → 保持 closed
        for _ in range(10):
            _GLOBAL_BREAKER.record("test-p2", True)
        for _ in range(2):
            _GLOBAL_BREAKER.record("test-p2", False)
        snap = circuit_breaker("test-p2")
        assert snap["state"] == "closed"
        assert snap["calls"] == 12

    def test_above_threshold_opens(self):
        from engines.provider_registry import circuit_breaker
        # 手动注入 70% 错误率, 应该触发 open
        snap = circuit_breaker("test-p3", error_rate=0.7)
        assert snap["state"] == "open"
        assert snap["error_rate"] >= 0.5

    def test_allow_returns_false_when_open(self):
        from engines.provider_registry import _GLOBAL_BREAKER, circuit_breaker
        circuit_breaker("test-p4", error_rate=0.8)
        # open 状态下 allow 应返回 False
        assert _GLOBAL_BREAKER.allow("test-p4") is False

    def test_reset_clears_state(self):
        from engines.provider_registry import _GLOBAL_BREAKER, circuit_breaker
        circuit_breaker("test-p5", error_rate=0.9)
        assert _GLOBAL_BREAKER.allow("test-p5") is False
        _GLOBAL_BREAKER.reset("test-p5")
        assert _GLOBAL_BREAKER.allow("test-p5") is True

    def test_snapshot_all_providers(self):
        from engines.provider_registry import _GLOBAL_BREAKER, circuit_breaker
        circuit_breaker("test-p6", error_rate=0.6)
        snap = circuit_breaker(None)  # type: ignore
        assert "test-p6" in snap
        assert snap["test-p6"]["state"] == "open"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Mock provider + call_provider_smart
# ═══════════════════════════════════════════════════════════════════════════
class TestMockProvider:
    def test_no_apikey_returns_mock(self):
        from engines.provider_registry import _mock_provider
        import asyncio

        provider = {"id": "openai-compatible", "protocol": "openai-compatible", "apiKey": ""}
        result = asyncio.run(_mock_provider(provider, {"model": "gpt-4o", "prompt": "hi"}, "chat"))
        assert result["ok"] is True
        assert result["mock"] is True
        assert "data" in result

    def test_call_provider_smart_records_usage(self):
        from engines.usage_tracker import get_tracker
        from engines.provider_registry import call_provider_smart
        import asyncio

        provider = {"id": "openai-compatible", "protocol": "openai-compatible", "apiKey": ""}
        result = asyncio.run(call_provider_smart(
            provider, {"model": "gpt-4o", "prompt": "hello"}, "chat",
            user_id="user_mock_test",
        ))
        assert result["ok"] is True
        assert result.get("mock") is True
        # cost_usd 字段被加上去
        assert "cost_usd" in result

        # 检查 usage 已记录
        summary = get_tracker().user_summary("user_mock_test", days=1)
        assert summary["total_calls"] >= 1

    def test_call_provider_smart_blocks_when_rate_limited(self, monkeypatch):
        from engines.provider_registry import call_provider_smart, _GLOBAL_LIMITER
        import asyncio

        _GLOBAL_LIMITER.reset()
        monkeypatch.setenv("AI_RATE_LIMIT_PER_HOUR", "1")

        provider = {"id": "openai-compatible", "protocol": "openai-compatible", "apiKey": ""}
        # 第一次: 通过
        r1 = asyncio.run(call_provider_smart(provider, {"model": "gpt-4o"}, "chat", user_id="user_rl"))
        assert r1["ok"] is True
        # 第二次: 被限流
        r2 = asyncio.run(call_provider_smart(provider, {"model": "gpt-4o"}, "chat", user_id="user_rl"))
        assert r2["ok"] is False
        assert r2["code"] == "rate_limited"

    def test_call_provider_smart_blocks_when_circuit_open(self):
        from engines.provider_registry import call_provider_smart, circuit_breaker
        import asyncio

        circuit_breaker("openai-compatible", error_rate=0.95)
        provider = {"id": "openai-compatible", "protocol": "openai-compatible", "apiKey": ""}
        result = asyncio.run(call_provider_smart(provider, {"model": "gpt-4o"}, "chat", user_id="user_cb"))
        assert result["ok"] is False
        assert result["code"] == "circuit_open"


# ═══════════════════════════════════════════════════════════════════════════
# 6. 端到端: /api/ai/usage endpoint (TestClient)
# ═══════════════════════════════════════════════════════════════════════════
class TestUsageEndpoint:
    def test_ai_usage_returns_200(self):
        from fastapi.testclient import TestClient
        app = _import_canvas_web_app()

        client = TestClient(app, raise_server_exceptions=False)
        # 先记录一笔, 然后查
        from engines.usage_tracker import get_tracker
        get_tracker().record(
            user_id="user_endpoint", provider_id="openai-compatible",
            protocol="openai-compatible", kind="chat", model="gpt-4o",
            prompt_tokens=10, completion_tokens=20, total_tokens=30,
            cost_usd=0.0005, latency_ms=100, status="ok",
        )

        r = client.get("/api/ai/usage?user_id=user_endpoint&days=30")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["data"]["total_calls"] >= 1
        assert body["data"]["total_tokens"] >= 30
        assert "by_provider" in body["data"]

    def test_ai_circuit_endpoint(self):
        from fastapi.testclient import TestClient
        app = _import_canvas_web_app()
        from engines.provider_registry import circuit_breaker

        circuit_breaker("openai-compatible", error_rate=0.6)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/api/ai/circuit?provider_id=openai-compatible")
        assert r.status_code == 200, r.text
        body = r.json()
        if not body.get("success"):
            print(f"DEBUG circuit endpoint body: {body}")
        assert body["success"] is True, f"circuit endpoint failed: {body}"
        assert "openai-compatible" in body["data"]
        assert body["data"]["openai-compatible"]["state"] == "open"

    def test_ai_cost_estimate_endpoint(self):
        from fastapi.testclient import TestClient
        app = _import_canvas_web_app()

        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/api/ai/cost/estimate",
            json={"protocol": "openai-compatible", "model": "gpt-4o",
                  "prompt_tokens": 1000, "completion_tokens": 500},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        # gpt-4o 1000+500 = 1000*0.005 + 500*0.015 = 0.005 + 0.0075 = 0.0125
        assert abs(body["data"]["cost_usd"] - 0.0125) < 1e-6
