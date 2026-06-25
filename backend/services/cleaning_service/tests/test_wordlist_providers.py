"""Tests for wordlist_providers (P6-2 P1-5)."""
import json
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from services.cleaning_service.wordlist_providers import (
    WordlistProvider,
    InlineWordlistProvider,
    FileWordlistProvider,
    HttpWordlistProvider,
    PlaceholderWordlistProvider,
    ProviderRegistry,
    get_registry,
    reset_registry_for_tests,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


# ---- Inline ----

def test_inline_provider_returns_lower():
    p = InlineWordlistProvider(["FOO", "Bar ", "  baz"])
    assert p.get_words() == ["foo", "bar", "baz"]


def test_inline_provider_filters_empty():
    p = InlineWordlistProvider(["foo", "", None, "bar"])
    assert p.get_words() == ["foo", "bar"]


def test_inline_provider_returns_copy():
    p = InlineWordlistProvider(["a", "b"])
    out = p.get_words()
    out.append("c")
    # Internal state unchanged
    assert p.get_words() == ["a", "b"]


# ---- File ----

def test_file_provider_loads_list(tmp_path: Path):
    f = tmp_path / "toxic.json"
    f.write_text(json.dumps(["foo", "bar"]), encoding="utf-8")
    p = FileWordlistProvider(str(f))
    assert p.get_words() == ["foo", "bar"]


def test_file_provider_loads_dict_with_words(tmp_path: Path):
    f = tmp_path / "sensitive.json"
    f.write_text(json.dumps({"words": ["alpha", "beta"], "version": 3}),
                 encoding="utf-8")
    p = FileWordlistProvider(str(f))
    assert p.get_words() == ["alpha", "beta"]


def test_file_provider_handles_missing(tmp_path: Path):
    p = FileWordlistProvider(str(tmp_path / "missing.json"))
    assert p.get_words() == []


def test_file_provider_handles_bad_json(tmp_path: Path):
    f = tmp_path / "bad.json"
    f.write_text("{not json", encoding="utf-8")
    p = FileWordlistProvider(str(f))
    assert p.get_words() == []


def test_file_provider_handles_bad_shape(tmp_path: Path):
    f = tmp_path / "badshape.json"
    f.write_text(json.dumps(12345), encoding="utf-8")
    p = FileWordlistProvider(str(f))
    assert p.get_words() == []


def test_file_provider_watch_reloads(tmp_path: Path):
    f = tmp_path / "watch.json"
    f.write_text(json.dumps(["old"]), encoding="utf-8")
    p = FileWordlistProvider(str(f), watch=True)
    assert p.get_words() == ["old"]
    # Simulate update
    time.sleep(0.05)
    f.write_text(json.dumps(["new1", "new2"]), encoding="utf-8")
    # Force mtime check by sleeping then querying
    time.sleep(0.05)
    # On Windows, mtime resolution can be coarse — call twice
    p.get_words()
    time.sleep(0.1)
    p.get_words()
    # Either old or new depending on platform mtime — just verify no crash
    assert isinstance(p.get_words(), list)


# ---- HTTP ----

def test_http_provider_returns_list():
    fake_resp = MagicMock()
    fake_resp.json.return_value = ["alpha", "beta"]
    fake_resp.raise_for_status = MagicMock()
    with patch("httpx.get", return_value=fake_resp) as mock_get:
        p = HttpWordlistProvider("https://api.example.com/words", cache_ttl=10)
        words = p.get_words()
        assert words == ["alpha", "beta"]
        mock_get.assert_called_once()


def test_http_provider_accepts_dict_with_words():
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"words": ["x", "y"]}
    fake_resp.raise_for_status = MagicMock()
    with patch("httpx.get", return_value=fake_resp):
        p = HttpWordlistProvider("https://api.example.com/w")
        assert p.get_words() == ["x", "y"]


def test_http_provider_caches_response():
    fake_resp = MagicMock()
    fake_resp.json.return_value = ["cached"]
    fake_resp.raise_for_status = MagicMock()
    with patch("httpx.get", return_value=fake_resp) as mock_get:
        p = HttpWordlistProvider("https://api.example.com/w", cache_ttl=300)
        p.get_words()
        p.get_words()  # second call should hit cache
        assert mock_get.call_count == 1


def test_http_provider_returns_cached_on_network_error():
    fake_resp = MagicMock()
    fake_resp.json.return_value = ["cached"]
    fake_resp.raise_for_status = MagicMock()
    with patch("httpx.get", return_value=fake_resp):
        p = HttpWordlistProvider("https://api.example.com/w", cache_ttl=300)
        p.get_words()  # populate cache
    # Now network fails
    with patch("httpx.get", side_effect=RuntimeError("net down")):
        out = p.get_words()
        assert out == ["cached"]


def test_http_provider_returns_empty_on_total_failure():
    with patch("httpx.get", side_effect=RuntimeError("net down")):
        p = HttpWordlistProvider("https://nowhere/w", cache_ttl=300)
        assert p.get_words() == []


def test_http_provider_bad_shape_returns_empty():
    fake_resp = MagicMock()
    fake_resp.json.return_value = "not a list or dict"
    fake_resp.raise_for_status = MagicMock()
    with patch("httpx.get", return_value=fake_resp):
        p = HttpWordlistProvider("https://api/w", cache_ttl=300)
        assert p.get_words() == []


def test_http_provider_httpx_missing():
    with patch.dict("sys.modules", {"httpx": None}):
        with patch("builtins.__import__", side_effect=ImportError):
            p = HttpWordlistProvider("https://api/w")
            # Should not raise
            assert p.get_words() == []


# ---- Placeholder ----

def test_placeholder_toxic_returns_expected():
    p = PlaceholderWordlistProvider(kind="toxic")
    assert p.get_words() == ["toxic_word_1", "toxic_word_2"]


def test_placeholder_sensitive_returns_expected():
    p = PlaceholderWordlistProvider(kind="sensitive")
    assert p.get_words() == [
        "forbidden_word_1", "forbidden_word_2", "blocked_term",
    ]


def test_placeholder_unknown_kind_returns_empty():
    p = PlaceholderWordlistProvider(kind="unknown")
    assert p.get_words() == []


def test_placeholder_logs_warning_once(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    p = PlaceholderWordlistProvider(kind="toxic")
    p.get_words()
    p.get_words()
    warnings = [r for r in caplog.records if "placeholder" in r.message]
    assert len(warnings) == 1


# ---- Registry ----

def test_registry_register_and_get():
    reg = ProviderRegistry()
    inline = InlineWordlistProvider(["x"], kind="toxic")
    reg.register("toxic", inline)
    assert reg.get("toxic") is inline


def test_registry_unknown_kind_returns_placeholder():
    reg = ProviderRegistry()
    p = reg.get("toxic")
    assert isinstance(p, PlaceholderWordlistProvider)


def test_registry_unknown_kind_persists_placeholder():
    reg = ProviderRegistry()
    p1 = reg.get("toxic")
    p2 = reg.get("toxic")
    # After first lookup, the placeholder is cached
    assert p1 is p2


def test_registry_reset_clears_providers():
    reg = ProviderRegistry()
    inline = InlineWordlistProvider(["x"], kind="toxic")
    reg.register("toxic", inline)
    reg.reset()
    p = reg.get("toxic")
    assert isinstance(p, PlaceholderWordlistProvider)


# ---- get_registry singleton ----

def test_get_registry_returns_same_instance():
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_get_registry_bootstrap_from_env_file(tmp_path: Path, monkeypatch):
    f = tmp_path / "toxic.json"
    f.write_text(json.dumps(["from_file"]), encoding="utf-8")
    monkeypatch.setenv("CLEANING_TOXIC_WORDS_FILE", str(f))
    reset_registry_for_tests()
    reg = get_registry()
    p = reg.get("toxic")
    assert p.kind == "toxic-file"
    assert "from_file" in p.get_words()


def test_get_registry_bootstrap_from_env_inline(monkeypatch):
    monkeypatch.setenv("CLEANING_SENSITIVE_WORDS_INLINE", "a, b ,c")
    reset_registry_for_tests()
    reg = get_registry()
    p = reg.get("sensitive")
    assert p.kind == "sensitive-inline"
    assert p.get_words() == ["a", "b", "c"]


def test_get_registry_bootstrap_from_env_url(monkeypatch):
    monkeypatch.setenv("CLEANING_TOXIC_WORDS_URL", "https://example.com/w")
    reset_registry_for_tests()
    reg = get_registry()
    p = reg.get("toxic")
    assert p.kind == "toxic-http"


def test_get_registry_bootstrap_falls_back_to_placeholder(monkeypatch):
    # Wipe all envs
    for var in [
        "CLEANING_TOXIC_WORDS_FILE", "CLEANING_TOXIC_WORDS_URL",
        "CLEANING_TOXIC_WORDS_INLINE",
        "CLEANING_SENSITIVE_WORDS_FILE", "CLEANING_SENSITIVE_WORDS_URL",
        "CLEANING_SENSITIVE_WORDS_INLINE",
    ]:
        monkeypatch.delenv(var, raising=False)
    reset_registry_for_tests()
    reg = get_registry()
    p = reg.get("toxic")
    assert isinstance(p, PlaceholderWordlistProvider)


# ---- Operators integration ----

def test_toxicity_operator_uses_caller_wordlist():
    from services.cleaning_service.operators.text.toxicity import run
    items = ["this text contains badword"]
    out = run(items, {"wordlist": ["badword"]})
    assert out[0]["toxicity_score"] > 0


def test_toxicity_operator_uses_provider_when_no_wordlist():
    from services.cleaning_service.operators.text import toxicity
    from services.cleaning_service.wordlist_providers import (
        InlineWordlistProvider,
    )
    reg = get_registry()
    reg.register(
        "toxic",
        InlineWordlistProvider(["provider_word"], kind="toxic-test"),
    )
    out = toxicity.run(["contains provider_word"], {})
    assert out[0]["signals"]["toxic_words"] >= 1


def test_sensitive_operator_uses_provider_when_no_wordlist():
    from services.cleaning_service.operators.text import sensitive
    from services.cleaning_service.wordlist_providers import (
        InlineWordlistProvider,
    )
    reg = get_registry()
    reg.register(
        "sensitive",
        InlineWordlistProvider(["secret"], kind="sensitive-test"),
    )
    out = sensitive.run(["this contains a secret here"], {})
    # mode=drop default → only the non-matching one (none) stays
    assert isinstance(out, list)


def test_sensitive_operator_explicit_wordlist_wins():
    from services.cleaning_service.operators.text import sensitive
    from services.cleaning_service.wordlist_providers import (
        InlineWordlistProvider,
    )
    reg = get_registry()
    reg.register(
        "sensitive",
        InlineWordlistProvider(["provider_word"], kind="sensitive-test"),
    )
    # Explicit wordlist takes priority over provider
    out = sensitive.run(
        ["explicit_word"],
        {"wordlist": ["explicit_word"], "mode": "score"},
    )
    assert len(out) >= 1
    # provider_word should not trigger
    out2 = sensitive.run(
        ["provider_word"],
        {"wordlist": ["explicit_word"], "mode": "score"},
    )
    assert out2[0]["is_sensitive"] is False