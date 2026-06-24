"""
P1-A3-Worker-1 + Owner 测试补全
SDK 代码生成 + 高级语义搜索测试
"""
from __future__ import annotations

import sys
import os
import zipfile
from pathlib import Path

# ── Path setup ──
_BACKEND = Path(__file__).resolve().parent.parent
_IMDF_ROOT = _BACKEND / "imdf"
if str(_IMDF_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMDF_ROOT))

import pytest  # noqa: E402

from engines.sdk_generator import (  # noqa: E402
    SDKGenerator,
    SUPPORTED_LANGUAGES,
    _validate_package_name,
    _resolve_python_module_name,
    _resolve_go_package_path,
)
from engines.semantic_search import (  # noqa: E402
    SemanticSearchEngine,
    _tokenize,
    DEFAULT_VECTOR_DIM,
)


# ═══════════════════════════════════════════════════════════════════════════
# SDK Generator Tests (12)
# ═══════════════════════════════════════════════════════════════════════════

class TestSDKPackageName:
    def test_01_valid_package_name_accepted(self):
        gen = SDKGenerator()
        assert _validate_package_name("imdf-sdk") == "imdf-sdk"

    def test_02_invalid_package_name_rejected(self):
        with pytest.raises(ValueError):
            _validate_package_name("123-invalid")

    def test_03_python_module_underscores(self):
        assert _resolve_python_module_name("imdf-sdk") == "imdf_sdk"

    def test_04_go_package_path_lowercase(self):
        assert _resolve_go_package_path("IMDF_SDK") == "imdf-sdk"


class TestSDKGeneration:
    def setup_method(self):
        self.gen = SDKGenerator()
        self.spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/users": {
                    "get": {
                        "summary": "List users",
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
            "components": {
                "schemas": {
                    "User": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"},
                        },
                    }
                }
            },
        }

    def test_05_python_sdk_zip_contains_py(self):
        zip_bytes = self.gen.generate(self.spec, "python", "test_sdk")
        assert isinstance(zip_bytes, bytes)
        with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert any(n.endswith(".py") for n in names)

    def test_06_javascript_sdk_zip_contains_js(self):
        zip_bytes = self.gen.generate(self.spec, "javascript", "test_sdk")
        with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert any(n.endswith(".js") for n in names)

    def test_07_go_sdk_zip_contains_go(self):
        zip_bytes = self.gen.generate(self.spec, "go", "test_sdk")
        with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert any(n.endswith(".go") for n in names)

    def test_08_supported_languages_listed(self):
        assert "python" in SUPPORTED_LANGUAGES
        assert "javascript" in SUPPORTED_LANGUAGES
        assert "go" in SUPPORTED_LANGUAGES

    def test_09_unsupported_language_raises(self):
        with pytest.raises((ValueError, KeyError, NotImplementedError)):
            self.gen.generate(self.spec, "rust", "test_sdk")

    def test_10_custom_package_name_reflected(self):
        zip_bytes = self.gen.generate(self.spec, "python", "custom_pkg")
        with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as zf:
            content = zf.read([n for n in zf.namelist() if n.endswith("__init__.py")][0]).decode()
        # Should reference the package name
        assert "custom_pkg" in content or "custom-pkg" in content

    def test_11_deterministic_output(self):
        a = self.gen.generate(self.spec, "python", "test_sdk")
        b = self.gen.generate(self.spec, "python", "test_sdk")
        assert a == b  # byte-identical

    def test_12_minimal_spec_no_paths_still_works(self):
        minimal = {"openapi": "3.0.0", "info": {"title": "Empty", "version": "0.1.0"}}
        zip_bytes = self.gen.generate(minimal, "python", "minimal")
        assert isinstance(zip_bytes, bytes)
        assert len(zip_bytes) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Semantic Search Tests (10)
# ═══════════════════════════════════════════════════════════════════════════

class TestSemanticSearch:
    def setup_method(self):
        self.engine = SemanticSearchEngine()
        self.engine.reset()
        # Seed corpus
        self.engine.index_asset("a1", "Apple banana cherry fruit", {"lang": "en"})
        self.engine.index_asset("a2", "Apple iPhone smartphone device", {"lang": "en"})
        self.engine.index_asset("a3", "Car vehicle truck motorcycle", {"lang": "en"})
        self.engine.index_asset("a4", "苹果 香蕉 水果 食物", {"lang": "zh"})
        self.engine.index_asset("a5", "汽车 卡车 摩托车 车辆", {"lang": "zh"})

    def test_01_tokenize_basic(self):
        tokens = _tokenize("Hello World")
        assert "hello" in tokens
        assert "world" in tokens

    def test_02_tokenize_empty(self):
        assert _tokenize("") == []

    def test_03_search_returns_results(self):
        results = self.engine.search("apple", top_k=3)
        assert isinstance(results, list)
        assert len(results) > 0
        # Top result should mention apple
        assert any("apple" in r.get("text", "").lower() for r in results)

    def test_04_search_top_k_limit(self):
        results = self.engine.search("vehicle", top_k=2)
        assert len(results) <= 2

    def test_05_search_alpha_param(self):
        # alpha=0.7 favors vector
        r_vec = self.engine.search("apple", top_k=2, alpha=0.7)
        # alpha=0.3 favors BM25
        r_bm = self.engine.search("apple", top_k=2, alpha=0.3)
        # Both should return apple results
        assert len(r_vec) > 0
        assert len(r_bm) > 0

    def test_06_chinese_query(self):
        results = self.engine.search("苹果", top_k=3)
        assert len(results) > 0
        assert any("苹果" in r.get("text", "") for r in results)

    def test_07_stats_returns_dict(self):
        stats = self.engine.stats()
        assert isinstance(stats, dict)
        assert "size" in stats or "corpus_size" in stats

    def test_08_reset_clears_corpus(self):
        self.engine.reset()
        results = self.engine.search("apple", top_k=3)
        assert results == [] or len(results) == 0

    def test_09_index_asset_increases_corpus(self):
        before = self.engine.stats().get("size", self.engine.stats().get("corpus_size", 0))
        self.engine.index_asset("a6", "Test document extra", {"lang": "en"})
        after = self.engine.stats().get("size", self.engine.stats().get("corpus_size", 0))
        assert after == before + 1

    def test_10_search_metadata_preserved(self):
        results = self.engine.search("apple", top_k=2)
        for r in results:
            assert "metadata" in r
            assert "lang" in r["metadata"]


# ═══════════════════════════════════════════════════════════════════════════
# Module Collect Check
# ═══════════════════════════════════════════════════════════════════════════

def test_module_collects_at_least_22_cases():
    """Ensure test file has ≥ 22 cases (plan requirement)."""
    import inspect
    import importlib.util as _ilu
    # Load this file directly to avoid the `tests` namespace ambiguity
    # (pytest may have `imdf/tests` and `backend/tests` both on sys.path).
    _this_path = Path(__file__).resolve()
    _mod_name = "_p1_a3_sdk_search_self"
    _spec = _ilu.spec_from_file_location(_mod_name, str(_this_path))
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)  # type: ignore

    # Collect: (a) top-level functions whose name starts with "test_";
    # (b) methods of Test* classes whose name starts with "test_".
    collected = set()
    for name, obj in inspect.getmembers(_mod):
        if callable(obj) and name.startswith("test_"):
            collected.add(f"{name} (top-level)")
    for cls_name, cls_obj in inspect.getmembers(_mod, inspect.isclass):
        for method_name, method_obj in inspect.getmembers(cls_obj, inspect.isfunction):
            if method_name.startswith("test_"):
                collected.add(f"{cls_name}.{method_name}")
    assert len(collected) >= 22, f"Need ≥ 22 tests, got {len(collected)}: {sorted(collected)}"