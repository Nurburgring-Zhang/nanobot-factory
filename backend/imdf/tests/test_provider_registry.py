"""
P5-W1: 真实 AI provider 连接测试
===============================
覆盖 4 主流 (openai / claude / qwen / volcengine) + 1 本地 (comfyui) provider 的
真实连接 (mock HTTP), 验证: 限流 + 重试 + 超时 + 降级 + cost 计量。

设计:
- HTTP 响应通过 respx (httpx mock) 拦截, 不发真实请求
- 限流/熔断/降级走 call_provider_smart 入口 (与 production 同代码路径)
- 用例数: ≥ 14, 覆盖 task 要求的全部 5 个 provider + 4 个集成维度
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 让 respx 可选 — 没装也能跑 (只用 unittest.mock 替代)
try:
    import respx
    from httpx import Response as HttpxResponse
    HAS_RESPX = True
except ImportError:
    HAS_RESPX = False

from engines import provider_registry as pr


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _reset_global_state(monkeypatch):
    """每个测试前重置限流/熔断, 避免状态污染."""
    pr._GLOBAL_LIMITER.reset()
    pr._GLOBAL_BREAKER.reset()
    # 默认高限额, 避免被其他测试夹带影响
    monkeypatch.setenv("AI_RATE_LIMIT_PER_HOUR", "10000")
    yield
    pr._GLOBAL_LIMITER.reset()
    pr._GLOBAL_BREAKER.reset()


def _openai_chat_response(model: str = "gpt-4o", pt: int = 10, ct: int = 20) -> dict:
    return {
        "id": f"chatcmpl-{model}",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
    }


def _openai_image_response(url: str = "https://x.test/img.png") -> dict:
    return {
        "created": int(time.time()),
        "data": [{"url": url}],
    }


def _volc_video_response() -> dict:
    return {"id": "cgt-video-1", "status": "queued"}


# ═══════════════════════════════════════════════════════════════════════════
# 1. OpenAI 兼容 — openai / claude / deepseek (3 个模型, 同一协议)
# ═══════════════════════════════════════════════════════════════════════════

class TestOpenAICompatible:
    """OpenAI 兼容协议覆盖: openai (gpt-4o), claude (claude-3-5-sonnet), deepseek."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_openai_chat_success(self):
        """openai gpt-4o chat 成功调用."""
        provider = {
            "id": "openai-compatible", "protocol": "openai-compatible",
            "baseUrl": "https://api.openai.com/v1",
            "apiKey": "sk-test123", "enabled": True,
            "chatModels": ["gpt-4o"],
        }
        with respx.mock(base_url="https://api.openai.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("gpt-4o", 12, 18))
            )
            res = await pr.call_openai_compatible(
                provider, {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
                kind="chat",
            )
        assert res["ok"] is True
        assert res["data"]["model"] == "gpt-4o"
        assert res["data"]["usage"]["total_tokens"] == 30

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_claude_via_openai_protocol(self):
        """claude-3-5-sonnet 通过 openai 兼容协议 (e.g. one-api / openrouter) 调用."""
        provider = {
            "id": "openai-compatible", "protocol": "openai-compatible",
            "baseUrl": "https://api.oneapi.com/v1",
            "apiKey": "sk-mock-claude", "enabled": True,
            "chatModels": ["claude-3-5-sonnet"],
        }
        with respx.mock(base_url="https://api.oneapi.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("claude-3-5-sonnet", 8, 25))
            )
            res = await pr.call_openai_compatible(
                provider, {"model": "claude-3-5-sonnet", "messages": [{"role": "user", "content": "hi"}]},
                kind="chat",
            )
        assert res["ok"] is True
        assert "claude" in res["data"]["model"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_deepseek_via_openai_protocol(self):
        """deepseek-chat 通过 openai 兼容协议 (官方即支持) 调用."""
        provider = {
            "id": "openai-compatible", "protocol": "openai-compatible",
            "baseUrl": "https://api.deepseek.com/v1",
            "apiKey": "sk-ds-mock", "enabled": True,
            "chatModels": ["deepseek-chat"],
        }
        with respx.mock(base_url="https://api.deepseek.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("deepseek-chat", 50, 100))
            )
            res = await pr.call_openai_compatible(
                provider, {"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}]},
                kind="chat",
            )
        assert res["ok"] is True
        assert res["data"]["usage"]["total_tokens"] == 150


# ═══════════════════════════════════════════════════════════════════════════
# 2. ModelScope — Qwen (通义千问)
# ═══════════════════════════════════════════════════════════════════════════

class TestModelScopeQwen:
    """ModelScope 协议 = openai 兼容, 覆盖 Qwen/Qwen3 / Qwen-Image / Qwen-Image-Edit."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_qwen_chat_success(self):
        """qwen3-235b chat 调用."""
        provider = {
            "id": "modelscope", "protocol": "modelscope",
            "baseUrl": "https://api-inference.modelscope.cn/v1",
            "apiKey": "ms-test-key", "enabled": True,
            "chatModels": ["Qwen/Qwen3-235B-A22B"],
            "imageModels": ["Qwen/Qwen-Image-2512"],
        }
        with respx.mock(base_url="https://api-inference.modelscope.cn") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("Qwen/Qwen3-235B-A22B", 200, 350))
            )
            res = await pr.call_openai_compatible(
                provider, {"model": "Qwen/Qwen3-235B-A22B",
                           "messages": [{"role": "user", "content": "介绍下杭州"}]},
                kind="chat",
            )
        assert res["ok"] is True
        assert "Qwen" in res["data"]["model"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_qwen_image_generation(self):
        """Qwen-Image-2512 文生图."""
        provider = {
            "id": "modelscope", "protocol": "modelscope",
            "baseUrl": "https://api-inference.modelscope.cn/v1",
            "apiKey": "ms-test-key", "enabled": True,
            "imageModels": ["Qwen/Qwen-Image-2512"],
        }
        with respx.mock(base_url="https://api-inference.modelscope.cn") as mock:
            mock.post("/v1/images/generations").mock(
                return_value=HttpxResponse(200, json=_openai_image_response("https://ms.x/qwen.png"))
            )
            res = await pr.call_openai_compatible(
                provider, {"model": "Qwen/Qwen-Image-2512", "prompt": "A cute cat", "n": 1},
                kind="image",
            )
        assert res["ok"] is True
        assert res["data"]["data"][0]["url"].startswith("https://")


# ═══════════════════════════════════════════════════════════════════════════
# 3. 火山引擎 (Volcengine / 方舟 Ark) — doubao
# ═══════════════════════════════════════════════════════════════════════════

class TestVolcengineDoubao:
    """火山引擎协议 — doubao seed / seedream / seedance."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_doubao_chat_missing_api_key(self):
        """没配 apiKey → 直接返回错误码 missing_api_key (不连真实网络)."""
        provider = {
            "id": "volcengine", "protocol": "volcengine",
            "baseUrl": "https://ark.cn-beijing.volces.com/api/v3",
            "apiKey": "", "enabled": True,
            "chatModels": ["doubao-seed-1-6-250615"],
        }
        res = await pr.call_volcengine(
            provider, {"model": "doubao-seed-1-6-250615", "messages": []}, kind="chat",
        )
        assert res["ok"] is False
        assert res["code"] == "missing_api_key"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_doubao_chat_success(self):
        """doubao-seed-1-6 chat 调用 (mock 火山方舟)."""
        provider = {
            "id": "volcengine", "protocol": "volcengine",
            "baseUrl": "https://ark.cn-beijing.volces.com/api/v3",
            "apiKey": "volc-mock-key", "enabled": True,
            "chatModels": ["doubao-seed-1-6-250615"],
        }
        with respx.mock(base_url="https://ark.cn-beijing.volces.com") as mock:
            mock.post("/api/v3/chat/completions").mock(
                return_value=HttpxResponse(200, json=_openai_chat_response("doubao-seed-1-6-250615", 30, 60))
            )
            res = await pr.call_volcengine(
                provider, {"model": "doubao-seed-1-6-250615",
                           "messages": [{"role": "user", "content": "hi"}]},
                kind="chat",
            )
        assert res["ok"] is True
        assert res["data"]["usage"]["total_tokens"] == 90

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_doubao_video_async_submit(self):
        """doubao-seedance 视频生成异步提交."""
        provider = {
            "id": "volcengine", "protocol": "volcengine",
            "baseUrl": "https://ark.cn-beijing.volces.com/api/v3",
            "apiKey": "volc-mock-key", "enabled": True,
            "videoModels": ["doubao-seedance-2-0-260128"],
        }
        with respx.mock(base_url="https://ark.cn-beijing.volces.com") as mock:
            mock.post("/api/v3/contents/generations/video").mock(
                return_value=HttpxResponse(200, json=_volc_video_response())
            )
            res = await pr.call_volcengine(
                provider, {"model": "doubao-seedance-2-0-260128", "prompt": "A dancing cat"},
                kind="video",
            )
        assert res["ok"] is True
        assert res["data"]["id"].startswith("cgt-")


# ═══════════════════════════════════════════════════════════════════════════
# 4. ComfyUI — 本地 GPU
# ═══════════════════════════════════════════════════════════════════════════

class TestComfyUILocal:
    """ComfyUI 协议 = 本地 HTTP, 走 /prompt endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_comfyui_submit_workflow_success(self):
        """ComfyUI 提交 prompt 成功 (mock 8188 端口)."""
        provider = {
            "id": "comfyui", "protocol": "comfyui",
            "baseUrl": "http://127.0.0.1:8188", "enabled": True,
            "comfyuiConfig": {"instances": ["http://127.0.0.1:8188"]},
        }
        workflow = {
            "1": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "PLACEHOLDER", "clip": ["2", 0]},
            },
            "2": {
                "class_type": "KSampler",
                "inputs": {"seed": 42, "steps": 20, "cfg": 7.0,
                           "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0},
            },
        }
        with respx.mock(base_url="http://127.0.0.1:8188") as mock:
            mock.post("/prompt").mock(
                return_value=HttpxResponse(200, json={"prompt_id": "abc-123"})
            )
            res = await pr.call_comfyui(
                provider, {"workflowJson": workflow, "prompt": "A beautiful sunset"},
            )
        assert res["ok"] is True
        assert res["prompt_id"] == "abc-123"
        # 验证 prompt 已被替换
        replaced = workflow["1"]["inputs"]["text"]
        assert replaced == "A beautiful sunset"

    @pytest.mark.asyncio
    async def test_comfyui_missing_workflow(self):
        """ComfyUI 没传 workflowJson → 错误码 no_workflow."""
        provider = {
            "id": "comfyui", "protocol": "comfyui",
            "baseUrl": "http://127.0.0.1:8188", "enabled": True,
            "comfyuiConfig": {"instances": ["http://127.0.0.1:8188"]},
        }
        res = await pr.call_comfyui(provider, {"prompt": "no workflow"})
        assert res["ok"] is False
        assert res["code"] == "no_workflow"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Provider 工厂路由 (call_provider / call_provider_smart)
# ═══════════════════════════════════════════════════════════════════════════

class TestProviderRouting:
    """验证 call_provider 工厂 + call_provider_smart 业务入口."""

    @pytest.mark.asyncio
    async def test_call_provider_routes_by_protocol(self):
        """call_provider 根据 protocol 路由到对应 adapter."""
        # modelscope 走 openai 兼容分支
        provider = {
            "id": "modelscope", "protocol": "modelscope",
            "baseUrl": "https://api-inference.modelscope.cn/v1",
            "apiKey": "k", "enabled": True,
            "chatModels": ["Qwen/Qwen3-235B-A22B"],
        }
        with patch.object(pr, "call_openai_compatible", new=AsyncMock(return_value={"ok": True, "data": {"x": 1}})) as m:
            res = await pr.call_provider(provider, {"model": "Qwen/Qwen3-235B-A22B"}, kind="chat")
        assert res["ok"] is True
        assert m.called

    @pytest.mark.asyncio
    async def test_call_provider_unsupported_protocol(self):
        """未知 protocol → 错误码 unsupported_protocol."""
        provider = {"id": "weird", "protocol": "unknown-thing", "enabled": True}
        res = await pr.call_provider(provider, {}, kind="chat")
        assert res["ok"] is False
        assert res["code"] == "unsupported_protocol"


# ═══════════════════════════════════════════════════════════════════════════
# 6. 集成 — 限流 / 熔断 / 降级 / cost 计量 (call_provider_smart)
# ═══════════════════════════════════════════════════════════════════════════

class TestProviderIntegration:
    """call_provider_smart 是 production 入口, 验证 4 维度集成行为."""

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_excess(self, monkeypatch):
        """触发限流: monkeypatch 小限额 → 第二次调用被拒."""
        monkeypatch.setenv("AI_RATE_LIMIT_PER_HOUR", "1")
        provider = {
            "id": "rl-test", "protocol": "openai-compatible",
            "baseUrl": "https://x.test/v1", "apiKey": "", "enabled": True,
            "chatModels": ["gpt-4o"],
        }
        # 第 1 次: mock 降级 (无 key → mock provider) 走通
        r1 = await pr.call_provider_smart(provider, {"model": "gpt-4o"}, kind="chat", user_id="u1")
        assert r1["ok"] is True
        # 第 2 次: 限流触发
        r2 = await pr.call_provider_smart(provider, {"model": "gpt-4o"}, kind="chat", user_id="u1")
        assert r2["ok"] is False
        assert r2["code"] == "rate_limited"
        assert r2.get("rate_limited") is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_errors(self):
        """连续错误 → 熔断器打开, 后续调用被拒 (不再发请求)."""
        # 手动注入 90% 错误率让熔断立即 open
        pr.circuit_breaker("cb-test", error_rate=0.9, cooldown_seconds=60)
        provider = {
            "id": "cb-test", "protocol": "openai-compatible",
            "baseUrl": "https://x.test/v1", "apiKey": "k", "enabled": True,
            "chatModels": ["gpt-4o"],
        }
        res = await pr.call_provider_smart(provider, {"model": "gpt-4o"}, kind="chat", user_id="u1")
        assert res["ok"] is False
        assert res["code"] == "circuit_open"

    @pytest.mark.asyncio
    async def test_no_apikey_degrades_to_mock(self):
        """没 apiKey → 自动降级到 mock provider (不连真实网络)."""
        provider = {
            "id": "mock-test", "protocol": "openai-compatible",
            "baseUrl": "https://x.test/v1", "apiKey": "", "enabled": True,
            "chatModels": ["gpt-4o-mini"],
        }
        res = await pr.call_provider_smart(provider, {"model": "gpt-4o-mini"}, kind="chat", user_id="u1")
        assert res["ok"] is True
        assert res.get("mock") is True
        # 验证 cost 已计算
        assert "cost_usd" in res
        assert res["cost_usd"] >= 0

    @pytest.mark.asyncio
    async def test_cost_metering_per_provider_model(self):
        """cost 计量: 不同 provider + 不同 model 价格不同."""
        # gpt-4o: input 0.005, output 0.015
        cost_gpt4o = pr.compute_cost_usd("openai-compatible", "gpt-4o", 1000, 1000)
        assert abs(cost_gpt4o - (0.005 + 0.015)) < 1e-6

        # gpt-4o-mini: input 0.00015, output 0.0006 (便宜 30x)
        cost_mini = pr.compute_cost_usd("openai-compatible", "gpt-4o-mini", 1000, 1000)
        assert cost_mini < cost_gpt4o / 10

        # volcengine doubao: 0.0008 / 0.002
        cost_voc = pr.compute_cost_usd("volcengine", "doubao-seed-1-6-250615", 1000, 1000)
        assert abs(cost_voc - (0.0008 + 0.002)) < 1e-6

        # 本地 comfyui / jimeng-cli: 0
        cost_comfy = pr.compute_cost_usd("comfyui", "anything", 1000, 1000)
        cost_jimeng = pr.compute_cost_usd("jimeng-cli", "seedream-4.7", 1000, 1000)
        assert cost_comfy == 0.0
        assert cost_jimeng == 0.0

    @pytest.mark.asyncio
    async def test_retry_via_circuit_breaker_half_open(self, monkeypatch):
        """熔断冷却后进入半开, 放行一次 (retry 入口)."""
        # 注入极短 cooldown
        pr.circuit_breaker("retry-test", error_rate=0.9, cooldown_seconds=0.05)
        # 立刻调用 → 熔断
        provider = {
            "id": "retry-test", "protocol": "openai-compatible",
            "baseUrl": "https://x.test/v1", "apiKey": "", "enabled": True,
            "chatModels": ["gpt-4o-mini"],
        }
        r1 = await pr.call_provider_smart(provider, {"model": "gpt-4o-mini"}, kind="chat", user_id="u1")
        assert r1["ok"] is False
        assert r1["code"] == "circuit_open"
        # 等过 cooldown
        await asyncio.sleep(0.1)
        # 再次 → 半开放行, mock 降级成功
        r2 = await pr.call_provider_smart(provider, {"model": "gpt-4o-mini"}, kind="chat", user_id="u1")
        assert r2["ok"] is True
        assert r2.get("mock") is True

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_http_timeout_degrades_gracefully(self):
        """HTTP 超时 → 返回 request_failed, 不抛异常 (优雅降级)."""
        provider = {
            "id": "timeout-test", "protocol": "openai-compatible",
            "baseUrl": "https://api.openai.com/v1",
            "apiKey": "sk-test", "enabled": True,
            "chatModels": ["gpt-4o"],
        }
        with respx.mock(base_url="https://api.openai.com") as mock:
            mock.post("/v1/chat/completions").mock(
                side_effect=asyncio.TimeoutError("simulated timeout")
            )
            res = await pr.call_openai_compatible(
                provider, {"model": "gpt-4o", "messages": []}, kind="chat",
            )
        # 应捕获异常并返回 ok=False, 而不是抛
        assert res["ok"] is False
        assert res["code"] == "request_failed"
        assert "timeout" in res["error"].lower()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_RESPX, reason="respx not installed")
    async def test_http_5xx_returns_api_error(self):
        """服务端 5xx → ok=False + code=api_error."""
        provider = {
            "id": "5xx-test", "protocol": "openai-compatible",
            "baseUrl": "https://api.openai.com/v1",
            "apiKey": "sk-test", "enabled": True,
            "chatModels": ["gpt-4o"],
        }
        with respx.mock(base_url="https://api.openai.com") as mock:
            mock.post("/v1/chat/completions").mock(
                return_value=HttpxResponse(500, json={"error": {"message": "internal error"}})
            )
            res = await pr.call_openai_compatible(
                provider, {"model": "gpt-4o", "messages": []}, kind="chat",
            )
        assert res["ok"] is False
        assert res["code"] == "api_error"

    @pytest.mark.asyncio
    async def test_usage_recorded_on_success(self):
        """call_provider_smart 成功 → usage_tracker 自动 record."""
        from engines.usage_tracker import get_tracker
        tracker = get_tracker()
        # 先清空 (每测试独立 DB 由 conftest 提供, 但 tracker 是单例, 用 user_id 区分)
        provider = {
            "id": "usage-test", "protocol": "openai-compatible",
            "baseUrl": "https://x.test/v1", "apiKey": "", "enabled": True,
            "chatModels": ["gpt-4o-mini"],
        }
        res = await pr.call_provider_smart(
            provider, {"model": "gpt-4o-mini"}, kind="chat", user_id="usage-u1",
        )
        assert res["ok"] is True
        # 查 usage summary 验证
        summary = tracker.user_summary("usage-u1")
        # 至少有一次成功调用
        assert summary.get("calls", 0) >= 1 or summary.get("total_calls", 0) >= 1

    @pytest.mark.asyncio
    async def test_audit_chain_records_provider_call(self, tmp_path):
        """call_provider_smart 成功 → audit_chain 自动 append 一条 HMAC 签名 entry."""
        from engines.audit_chain import reset_singleton_for_tests
        # 用 tmp_path 初始化 audit_chain
        db = tmp_path / "audit.db"
        chain = reset_singleton_for_tests(str(db), secret="test-secret-very-strong-random-32bytes")
        provider = {
            "id": "audit-test", "protocol": "openai-compatible",
            "baseUrl": "https://x.test/v1", "apiKey": "", "enabled": True,
            "chatModels": ["gpt-4o-mini"],
        }
        res = await pr.call_provider_smart(
            provider, {"model": "gpt-4o-mini"}, kind="chat", user_id="audit-u1",
        )
        assert res["ok"] is True
        # 验证 audit chain 至少有一条 entry
        all_entries = chain.load_all()
        matching = [e for e in all_entries if "audit-test" in (e.path or "")]
        assert len(matching) >= 1
        # 验证 chain 完整性 (HMAC 签名链)
        chain.assert_chain()
        # 验证 path 包含 provider 信息
        latest = matching[-1]
        assert latest.method == "AI_PROVIDER"
        assert "openai-compatible" in latest.path
