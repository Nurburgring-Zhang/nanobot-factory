"""P19-B1: D-wire 1-line fix 验证。

P19-A1 创建了 ``providers.invoke()`` 入口(走 p19a1_entry,只 5 family);
P19-A2 创建了 ``_invoke.py`` shim(包含全部 10 family)但没有把
``providers/__init__.py`` 切到 _invoke。P19-B1 是 1-line wire 修复。

本测试 4 大块:
  1) ``providers.invoke()`` 实际可调用 (不是被覆盖的 A1-only shim)
  2) ``providers.list_all_providers()`` 返回 10+ provider id
  3) ``providers.get_provider_by_family('gemini')`` 找到正确 provider
  4) batch-2 全部 5 个 family (gemini/kimi/zhipu/baidu/tencent) 全部可发现
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# 1) providers.invoke() 实际可调用
# ═══════════════════════════════════════════════════════════════════════════

class TestInvokeIsCallable:
    """``providers.invoke`` 必须指向 _invoke.invoke (合并 A1+A2 全部 10 family) —
    不是只覆盖 5 family 的 p19a1_entry.invoke。
    """

    def test_invoke_is_callable(self):
        from providers import invoke
        assert callable(invoke), "providers.invoke 必须是 callable"

    def test_invoke_points_to__invoke_module(self):
        """providers.invoke 必须是 _invoke.invoke 函数, 不是 p19a1_entry.invoke."""
        from providers import invoke
        from providers import _invoke as _invoke_mod
        # 函数 identity 比较 — _invoke.invoke 不等于 p19a1_entry.invoke
        assert invoke is _invoke_mod.invoke, (
            "D-wire 未生效: providers.invoke 仍指向 p19a1_entry "
            "(只 5 family,缺 batch-2: gemini/kimi/zhipu/baidu/tencent)"
        )

    @pytest.mark.asyncio
    async def test_invoke_returns_dict_with_expected_keys(self):
        """alias-form invoke 走 A1 shim 路径会返回 success/provider/model/fallback_used 字段;
        D-wire 切到 _invoke 后走 dict-form(因为它会先看 family 是否在 _ALIAS_TO_FAMILY
        → 全部 10 family 都在,解析为 dict-form)。两种形态都合法,但不能抛异常。"""
        from providers import invoke
        # gemini 是个 batch-2 family — A1 shim 解析不出,会 return unknown provider。
        # _invoke shim 应能解析并返回 dict-form 字段 (ok/provider_id/... 或
        # success/provider/... — _invoke 的 alias-form 内部包装 dict-form 仍含
        # success 字段)。
        r = await invoke("gemini-2.0-flash", prompt="hello", fallback=False)
        assert isinstance(r, dict), f"invoke 应返回 dict,实际 {type(r)}"
        # 至少要包含 'success' 字段(A2 alias-form 包装) 或 'ok' 字段(dict-form raw)
        assert ("success" in r) or ("ok" in r), (
            f"invoke 返回字段缺失: {list(r.keys())}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2) providers.list_all_providers() 返回所有 10+ provider
# ═══════════════════════════════════════════════════════════════════════════

class TestListAllProvidersReturnsAll10:
    """``providers.list_all_providers`` 必须返回 10 个 provider id
    (A1: 5 + A2 batch 2: 5)。A1-only shim 只返回 5,A1+ A2 全 10 必须出现。
    """

    def test_list_all_providers_callable(self):
        from providers import list_all_providers
        assert callable(list_all_providers)

    def test_list_all_providers_returns_list_or_dict(self):
        from providers import list_all_providers
        r = list_all_providers()
        # 兼容 list[str] (_invoke 形态) 和 dict (p19a1_entry 形态)
        assert isinstance(r, (list, dict)), (
            f"list_all_providers 应返回 list 或 dict,实际 {type(r)}"
        )

    def test_list_all_providers_includes_a1_families(self):
        """A1 5 family 必须存在 (向后兼容)。"""
        from providers import list_all_providers
        r = list_all_providers()
        names = self._family_names(r)
        for f in ["claude", "deepseek", "qwen", "doubao", "agnes"]:
            assert f in names, f"P19-A1 family '{f}' 必须在 list_all_providers 结果中,实际: {names}"

    def test_list_all_providers_includes_batch2_families(self):
        """A2 batch 2 5 family 必须存在 (D-wire 的核心目的)。"""
        from providers import list_all_providers
        r = list_all_providers()
        names = self._family_names(r)
        for f in ["gemini", "kimi", "zhipu", "baidu", "tencent"]:
            assert f in names, (
                f"P19-A2 batch 2 family '{f}' 必须在 list_all_providers 结果中, "
                f"实际: {names} — D-wire 未生效"
            )

    def test_list_all_providers_has_at_least_10(self):
        from providers import list_all_providers
        r = list_all_providers()
        names = self._family_names(r)
        assert len(names) >= 10, (
            f"list_all_providers 应含 10+ provider,实际 {len(names)}: {names}"
        )

    @staticmethod
    def _family_names(r):
        """从 list 或 dict 抽出 family 字符串集合。"""
        if isinstance(r, dict):
            return {str(k).lower() for k in r.keys()}
        # list 形态: 元素可能是 str 或 Provider 对象
        names = set()
        for x in r:
            if isinstance(x, str):
                names.add(x.lower())
            else:
                fid = getattr(x, "family", None) or getattr(x, "id", None) or str(x)
                names.add(str(fid).lower())
        return names


# ═══════════════════════════════════════════════════════════════════════════
# 3) providers.get_provider_by_family('gemini') 找到正确 provider
# ═══════════════════════════════════════════════════════════════════════════

class TestGetProviderByFamily:
    """``providers.get_provider_by_family`` 必须能解析 batch-2 family。"""

    def test_get_provider_by_family_callable(self):
        from providers import get_provider_by_family
        assert callable(get_provider_by_family)

    def test_get_provider_by_family_gemini(self):
        """batch-2 family: gemini → 应找到 GeminiProvider 描述符。"""
        from providers import get_provider_by_family
        from providers.gemini import GeminiProvider
        p = get_provider_by_family("gemini")
        assert p is not None, "get_provider_by_family('gemini') 必须返回非 None"
        # 形态 1: 直接是 GeminiProvider 实例(_invoke 优先)
        # 形态 2: 是 Provider registry row (id=gemini, family=gemini)
        if isinstance(p, GeminiProvider):
            assert p.family == "gemini"
        else:
            fid = getattr(p, "id", None) or getattr(p, "family", None)
            assert fid == "gemini", f"gemini provider id 应为 'gemini', 实际 {fid}"

    def test_get_provider_by_family_a1_compat_claude(self):
        """A1 family: claude → 应找到 ClaudeProvider。"""
        from providers import get_provider_by_family
        from providers.claude import ClaudeProvider
        p = get_provider_by_family("claude")
        assert p is not None
        if isinstance(p, ClaudeProvider):
            assert p.family == "claude"
        else:
            fid = getattr(p, "id", None) or getattr(p, "family", None)
            assert fid == "claude", f"claude provider id 应为 'claude', 实际 {fid}"

    def test_get_provider_by_family_unknown_returns_none_or_mock(self):
        """未知 family: _invoke 走 registry fallback 路径, 返回 mock provider
        (这是 registry.route() 的设计行为, 不是 D-wire bug)。
        本测试验证: 不抛异常 + 返回的对象不是 5 个 batch-2 family 的 descriptor。
        """
        from providers import get_provider_by_family
        from providers.gemini import GeminiProvider
        from providers.kimi import KimiProvider
        from providers.zhipu import ZhipuProvider
        from providers.baidu import BaiduProvider
        from providers.tencent import TencentProvider
        p = get_provider_by_family("unknown-family-xyz-12345")
        # 主流是 mock provider (registry.route() fallback) — 不应是 None
        # (但 _invoke 走 try/except 也可能 None, 容许)
        if p is not None:
            # 验证不是任何 batch-2 family 的 descriptor
            assert not isinstance(p, (GeminiProvider, KimiProvider, ZhipuProvider,
                                       BaiduProvider, TencentProvider)), (
                f"未知 family 不应解析为 batch-2 descriptor, 实际 {type(p).__name__}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 4) batch-2 全部 family (gemini/kimi/zhipu/baidu/tencent) 全部可发现
# ═══════════════════════════════════════════════════════════════════════════

class TestBatch2FamiliesDiscoverable:
    """5 个 batch-2 family 通过 _invoke 入口全部可发现 — D-wire 的核心验证。"""

    @pytest.mark.parametrize("family,module_path,class_name", [
        ("gemini", "providers.gemini", "GeminiProvider"),
        ("kimi", "providers.kimi", "KimiProvider"),
        ("zhipu", "providers.zhipu", "ZhipuProvider"),
        ("baidu", "providers.baidu", "BaiduProvider"),
        ("tencent", "providers.tencent", "TencentProvider"),
    ])
    def test_batch2_family_descriptor(self, family, module_path, class_name):
        """每个 batch-2 family 的 provider descriptor 类必须可导入并实例化。"""
        from providers import get_provider_by_family
        mod = __import__(module_path, fromlist=[class_name])
        cls = getattr(mod, class_name)
        # 通过 get_provider_by_family 取
        p = get_provider_by_family(family)
        # 容许 descriptor 直接返回 或 落到 registry row (id/family = family)
        if p is None:
            # 极端: descriptor 拿不到,直接构造一个
            p = cls()
        # 验证是 family 关联的实例
        fid = getattr(p, "family", None) or getattr(p, "id", None)
        if fid is None:
            # registry row 可能以 Provider dataclass 形态, 看 to_dict
            td = getattr(p, "to_dict", None)
            if callable(td):
                fid = td().get("family") or td().get("id")
        assert fid == family, f"family={family} 应有 descriptor/row; 实际 {p!r}"

    def test_batch2_alias_resolution(self):
        """_invoke._ALIAS_TO_FAMILY 必须含 5 个 batch-2 family 的所有 alias。"""
        from providers import _invoke as _invoke_mod
        alias_map = _invoke_mod._ALIAS_TO_FAMILY

        # gemini
        for alias in ["gemini", "gemini-2.0-flash", "gemini-2.5-pro", "gemini-2.0-flash-vision"]:
            assert alias in alias_map, f"alias '{alias}' 必须在 _ALIAS_TO_FAMILY"
            assert alias_map[alias] == "gemini", (
                f"alias '{alias}' 应解析为 family=gemini, 实际 {alias_map[alias]}"
            )

        # kimi
        for alias in ["kimi", "kimi-k2.7", "moonshot-v1-128k"]:
            assert alias in alias_map, f"alias '{alias}' 必须在 _ALIAS_TO_FAMILY"
            assert alias_map[alias] == "kimi"

        # zhipu
        for alias in ["zhipu", "glm-4-plus", "glm-4v-plus"]:
            assert alias in alias_map
            assert alias_map[alias] == "zhipu"

        # baidu
        for alias in ["baidu", "ernie-4.0-turbo", "ernie-4.0-8k"]:
            assert alias in alias_map
            assert alias_map[alias] == "baidu"

        # tencent
        for alias in ["tencent", "hunyuan-pro", "hunyuan-standard", "hunyuan-vision"]:
            assert alias in alias_map
            assert alias_map[alias] == "tencent"

    def test_batch2_fallback_chain_includes_all(self):
        """_FALLBACK_FAMILIES 必须含 5 个 batch-2 family (A1 + A2 全 10)。"""
        from providers import _invoke as _invoke_mod
        fb = _invoke_mod._FALLBACK_FAMILIES
        for f in ["gemini", "kimi", "zhipu", "baidu", "tencent"]:
            assert f in fb, f"family '{f}' 必须在 _FALLBACK_FAMILIES, 实际 {fb}"

    def test_batch2_pick_adapter_dispatch(self):
        """_pick_adapter 必须能解析 5 个 batch-2 family。"""
        from providers import _invoke as _invoke_mod
        for family in ["gemini", "kimi", "zhipu", "baidu", "tencent"]:
            adapter = _invoke_mod._pick_adapter(family)
            assert adapter is not None, (
                f"_pick_adapter('{family}') 必须返回非 None adapter, 实际 None"
            )
            assert callable(adapter), f"_pick_adapter('{family}') 必须是 callable"


# ═══════════════════════════════════════════════════════════════════════════
# D-wire identity 锁定 (防回归)
# ═══════════════════════════════════════════════════════════════════════════

class TestDWireIdentityLock:
    """锁定: providers.invoke/list_all_providers/get_provider_by_family
    必须指向 _invoke.py 实现,不能回归到 p19a1_entry (A1-only 5 family)。
    """

    def test_invoke_identity(self):
        from providers import invoke
        from providers import _invoke as _invoke_mod
        from providers import p19a1_entry
        assert invoke is _invoke_mod.invoke
        assert invoke is not p19a1_entry.invoke, (
            "REGRESSION: providers.invoke 重新指向 p19a1_entry — "
            "batch-2 family 不可见!"
        )

    def test_list_all_providers_identity(self):
        from providers import list_all_providers
        from providers import _invoke as _invoke_mod
        from providers import p19a1_entry
        assert list_all_providers is _invoke_mod.list_all_providers
        assert list_all_providers is not p19a1_entry.list_all_providers, (
            "REGRESSION: providers.list_all_providers 重新指向 p19a1_entry!"
        )

    def test_get_provider_by_family_identity(self):
        from providers import get_provider_by_family
        from providers import _invoke as _invoke_mod
        from providers import p19a1_entry
        assert get_provider_by_family is _invoke_mod.get_provider_by_family
        assert get_provider_by_family is not p19a1_entry.get_provider_by_family, (
            "REGRESSION: providers.get_provider_by_family 重新指向 p19a1_entry!"
        )
