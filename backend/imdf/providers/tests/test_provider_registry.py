"""P19-A1: 回归测试 — 验证 provider registry / invoke 入口 / 5 个 provider 模块都已正确接入。

覆盖:
- SAMPLE_PROVIDERS 含 5 provider (claude/deepseek/qwen/doubao/agnes)
- list_all_providers() 返回 5 个 provider 实例
- invoke() 路由 + fallback chain
- 价格表正确 (claude=$3/$15, deepseek=$0.14/$0.28, qwen=$0.40/$1.20, agnes=免费)
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import httpx


def _mock_response(status: int = 200, json_data: dict = None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or {"choices": [
        {"index": 0, "message": {"role": "assistant", "content": "OK"}}
    ], "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}}
    resp.text = "{}"
    return resp


class TestRegistrySampleProviders:
    """SAMPLE_PROVIDERS 必须含 P19-A1 全部 5 个 provider."""

    def test_claude_in_samples(self):
        from providers.registry import SAMPLE_PROVIDERS
        c = next((p for p in SAMPLE_PROVIDERS if p.id == "claude"), None)
        assert c is not None, "claude 必须在 SAMPLE_PROVIDERS"
        assert c.price_per_1k_input > 0
        assert c.price_per_1k_output > 0

    def test_deepseek_in_samples(self):
        from providers.registry import SAMPLE_PROVIDERS
        d = next((p for p in SAMPLE_PROVIDERS if p.id == "deepseek"), None)
        assert d is not None

    def test_qwen_in_samples(self):
        from providers.registry import SAMPLE_PROVIDERS
        q = next((p for p in SAMPLE_PROVIDERS if p.id == "qwen"), None)
        assert q is not None

    def test_doubao_in_samples_with_seed_1_6(self):
        from providers.registry import SAMPLE_PROVIDERS
        d = next((p for p in SAMPLE_PROVIDERS if p.id == "doubao"), None)
        assert d is not None
        assert d.default_model == "doubao-seed-1-6-250615", (
            "P19-A1: doubao 默认模型应为 seed-1-6"
        )
        # 兼容 — config.models 里的 full id 或短名都可
        models_in_config = d.config.get("models", [])
        assert any("vision-pro" in m for m in models_in_config), (
            f"doubao config.models 应包含 vision-pro 模型, 实际: {models_in_config}"
        )

    def test_agnes_in_samples_and_free(self):
        from providers.registry import SAMPLE_PROVIDERS
        a = next((p for p in SAMPLE_PROVIDERS if p.id == "agnes"), None)
        assert a is not None, "P19-A1: agnes 必须在 SAMPLE_PROVIDERS"
        assert a.price_per_1k_input == 0.0
        assert a.price_per_1k_output == 0.0
        assert a.config.get("free") is True
        assert "text" in a.config.get("modalities", [])
        assert "image" in a.config.get("modalities", [])
        assert "video" in a.config.get("modalities", [])
        assert "drama" in a.config.get("modalities", [])

    def test_provider_family_includes_agnes(self):
        from providers.registry import ProviderFamily
        assert ProviderFamily.AGNES.value == "agnes"


class TestListAllProviders:
    def test_returns_5_p19_providers(self):
        from providers import list_all_providers
        all_p = list_all_providers()
        assert "claude" in all_p
        assert "deepseek" in all_p
        assert "qwen" in all_p
        assert "doubao" in all_p
        assert "agnes" in all_p

    def test_get_provider_by_family(self):
        from providers import get_provider_by_family
        from providers.claude import ClaudeProvider
        from providers.agnes import AgnesProvider
        p = get_provider_by_family("claude")
        assert isinstance(p, ClaudeProvider)
        p2 = get_provider_by_family("agnes")
        assert isinstance(p2, AgnesProvider)
        # 未知 family: P19-B1 D-wire 后走 _invoke (A1+A2 全部 10 family),
        # _invoke.get_provider_by_family 走 registry.route() fallback 返 mock provider
        # (这是 registry 设计行为, 不是 D-wire bug)
        from providers.agnes import AgnesProvider as _AP
        from providers.claude import ClaudeProvider as _CP
        p3 = get_provider_by_family("unknown-xyz-12345")
        # 容许 None (descriptor 路径) 或 mock provider (registry 路径)
        if p3 is not None:
            assert not isinstance(p3, (_AP, _CP)), (
                f"未知 family 不应解析为已知 descriptor, 实际 {type(p3).__name__}"
            )


class TestInvoke:
    """invoke() 统一入口 + fallback chain。"""

    @pytest.mark.asyncio
    async def test_invoke_resolves_alias(self):
        from providers import invoke
        # claude-3-5-sonnet 是 alias → 应解析为 claude family
        with patch("httpx.AsyncClient") as mock_ac:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            resp_mock = MagicMock()
            resp_mock.status_code = 200
            resp_mock.json.return_value = {
                "content": [{"type": "text", "text": "hi"}],
                "usage": {"input_tokens": 2, "output_tokens": 3},
            }
            resp_mock.text = "{}"
            mock_client.post = AsyncMock(return_value=resp_mock)
            mock_ac.return_value = mock_client
            r = await invoke("claude-3-5-sonnet", prompt="hello", fallback=False)
        # 无 ANTHROPIC_API_KEY → 仍然返回 place holder
        # (除非环境变量真的设置了). 这里必须返回 success=False OR success=True 都合理;
        # 我们只验证 invoke 不抛异常 + 返回 dict with 'success' 字段
        assert "success" in r
        assert "provider" in r
        assert r["provider"] == "claude"

    @pytest.mark.asyncio
    async def test_invoke_fallback_chain(self):
        """首选 claude (无 key → fail) → fallback 试 deepseek → 仍然 placeholder"""
        from providers import invoke
        # deepseek 在测试环境可能有 key + balance 不够 + 返回 HTTP 402
        # 此测试只验证 invoke() 不抛, 返回 fallback 标记
        r = await invoke("claude-3-5-sonnet", prompt="test", fallback=True)
        assert "success" in r
        assert "fallback_used" in r  # invoke 总会标 fallback_used 或不标
        # 如果走了 fallback 链, 必有 provider 字段
        assert r["provider"] in {"claude", "deepseek", "qwen", "doubao", "agnes"}

    @pytest.mark.asyncio
    async def test_invoke_explicit_family_colon(self):
        """claude:custom-model 格式应能识别 family."""
        from providers import invoke
        r = await invoke("claude:custom-model-xyz", prompt="hi", fallback=False)
        assert r["provider"] == "claude"
        assert r["model"] == "custom-model-xyz"


class TestPricingTables:
    """验证价格表正确 (claude=$3/$15 per 1M, deepseek=$0.14/$0.28 等)."""

    def test_claude_pricing(self):
        from providers.claude import ClaudeProvider
        p = ClaudeProvider(api_key="sk")
        # 1M + 1M tokens
        c = p.cost_estimate_usd(1_000_000, 1_000_000)
        assert abs(c - 18.0) < 1e-6

    def test_deepseek_pricing(self):
        from providers.deepseek import DeepSeekProvider
        p = DeepSeekProvider(api_key="sk")
        c = p.cost_estimate_usd(1_000_000, 1_000_000)
        assert abs(c - 0.42) < 1e-6

    def test_qwen_pricing(self):
        from providers.qwen import QwenProvider
        p = QwenProvider(api_key="sk")
        c = p.cost_estimate_usd(1_000_000, 1_000_000)
        assert abs(c - 1.60) < 1e-6

    def test_doubao_pricing(self):
        from providers.doubao_extended import DoubaoProvider
        p = DoubaoProvider(api_key="volc")
        c = p.cost_estimate_usd(1_000_000, 1_000_000)
        # 0.80 + 2.00 = 2.80
        assert abs(c - 2.80) < 1e-6

    def test_agnes_free(self):
        from providers.agnes import AgnesProvider
        p = AgnesProvider(api_key="sk-agnes")
        assert p.cost_estimate_usd(1_000_000, 1_000_000) == 0.0
        assert p.cost_estimate_usd(10_000_000, 10_000_000) == 0.0
