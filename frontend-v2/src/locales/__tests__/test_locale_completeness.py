"""
P20-N extension of test_locale_completeness.py.

Adds assertions:
1. Each locale has the workflowBuilder.t000-t033 block (34 keys)
2. Each locale has balanced braces
3. workflowBuilder translations are non-empty for each locale
4. ar-SA (RTL) has Arabic-script content
5. Each locale parses cleanly (export default + closing brace)

Run with: pytest frontend-v2/src/locales/__tests__/test_locale_completeness.py -v
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]
FRONTEND_ROOT = REPO_ROOT / "frontend-v2"
LOCALES_ROOT = FRONTEND_ROOT / "src" / "locales"

EXPECTED_LOCALES = [
    "zh-CN", "en-US", "ja-JP", "ko-KR",
    "fr-FR", "de-DE", "es-ES", "ru-RU", "ar-SA",
]

EXPECTED_WORKFLOW_BUILDER_KEYS = [f"t{n:03d}" for n in range(34)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _read_locale(name: str) -> str:
    fp = LOCALES_ROOT / f"{name}.ts"
    assert fp.exists(), f"{fp} not found"
    return fp.read_text(encoding="utf-8")


def _extract_workflow_builder_block(text: str) -> str | None:
    """Extract the workflowBuilder: { ... } block from a locale file."""
    m = re.search(r"workflowBuilder:\s*\{(.*?)\n\s*\},", text, re.DOTALL)
    return m.group(1) if m else None


def _extract_keys(block: str) -> list[str]:
    """Return ordered list of tNNN keys in a workflowBuilder block."""
    return re.findall(r"\b(t\d{3}):", block)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestWorkflowBuilder:
    """P20-N: workflowBuilder.t000-t033 must exist in all 9 locales."""

    @pytest.mark.parametrize("locale", EXPECTED_LOCALES)
    def test_workflow_builder_block_present(self, locale: str) -> None:
        text = _read_locale(locale)
        block = _extract_workflow_builder_block(text)
        assert block is not None, (
            f"{locale}.ts missing workflowBuilder block. "
            f"Run recovery script or manually add the block."
        )

    @pytest.mark.parametrize("locale", EXPECTED_LOCALES)
    def test_workflow_builder_has_all_34_keys(self, locale: str) -> None:
        text = _read_locale(locale)
        block = _extract_workflow_builder_block(text)
        assert block is not None, f"{locale}: workflowBuilder block missing"
        keys = _extract_keys(block)
        assert len(keys) == 34, (
            f"{locale}: expected 34 workflowBuilder keys (t000-t033), got {len(keys)}: {keys}"
        )
        for expected in EXPECTED_WORKFLOW_BUILDER_KEYS:
            assert expected in keys, f"{locale}: missing workflowBuilder.{expected}"

    @pytest.mark.parametrize("locale", EXPECTED_LOCALES)
    def test_workflow_builder_values_non_empty(self, locale: str) -> None:
        text = _read_locale(locale)
        block = _extract_workflow_builder_block(text)
        assert block is not None, f"{locale}: workflowBuilder block missing"
        # Extract every key:value pair
        pairs = re.findall(r"(t\d{3}):\s*'([^']*)'", block)
        assert pairs, f"{locale}: no key:value pairs found in workflowBuilder block"
        for key, value in pairs:
            assert value.strip(), (
                f"{locale}: workflowBuilder.{key} has empty value"
            )

    def test_workflow_builder_translations_differ_across_locales(self) -> None:
        """zh-CN and en-US translations must differ (proves they're translated)."""
        zh_block = _extract_workflow_builder_block(_read_locale("zh-CN")) or ""
        en_block = _extract_workflow_builder_block(_read_locale("en-US")) or ""
        # Compare at least 5 keys for difference
        zh_pairs = dict(re.findall(r"(t\d{3}):\s*'([^']*)'", zh_block))
        en_pairs = dict(re.findall(r"(t\d{3}):\s*'([^']*)'", en_block))
        diff_count = sum(
            1 for k in zh_pairs
            if k in en_pairs and zh_pairs[k] != en_pairs[k]
        )
        assert diff_count >= 10, (
            f"zh-CN vs en-US workflowBuilder should differ in at least 10 keys, "
            f"got {diff_count}. Did the translations get reverted?"
        )


class TestLocaleFileStructure:
    """All 9 locale files must be valid TS modules."""

    @pytest.mark.parametrize("locale", EXPECTED_LOCALES)
    def test_locale_file_exists(self, locale: str) -> None:
        fp = LOCALES_ROOT / f"{locale}.ts"
        assert fp.exists(), f"{fp} not found"

    @pytest.mark.parametrize("locale", EXPECTED_LOCALES)
    def test_locale_has_export_default(self, locale: str) -> None:
        text = _read_locale(locale)
        assert "export default" in text, f"{locale}: missing `export default`"

    @pytest.mark.parametrize("locale", EXPECTED_LOCALES)
    def test_locale_has_as_const_close(self, locale: str) -> None:
        text = _read_locale(locale)
        assert re.search(r"\}\s*as\s+const\s*$", text.strip()), (
            f"{locale}: file does not end with `}} as const`"
        )

    @pytest.mark.parametrize("locale", EXPECTED_LOCALES)
    def test_locale_braces_balanced(self, locale: str) -> None:
        text = _read_locale(locale)
        # Brace balance check (string-aware)
        depth = 0
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch in '"\'':
                quote = ch
                i += 1
                while i < n and text[i] != quote:
                    if text[i] == '\\':
                        i += 2
                        continue
                    i += 1
                i += 1
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth < 0:
                    pytest.fail(f"{locale}: unmatched closing brace at offset {i}")
            i += 1
        assert depth == 0, f"{locale}: unbalanced braces (depth={depth} at end)"

    @pytest.mark.parametrize("locale", EXPECTED_LOCALES)
    def test_locale_minimum_size(self, locale: str) -> None:
        """A properly-populated locale should be > 4KB."""
        text = _read_locale(locale)
        assert len(text) > 4000, (
            f"{locale}: file too small ({len(text)} bytes). "
            f"Expected workflowBuilder block + baseline keys."
        )


class TestRtlArabic:
    """ar-SA must contain Arabic-script content (RTL verification)."""

    def test_arabic_locale_has_arabic_script(self) -> None:
        text = _read_locale("ar-SA")
        # Arabic Unicode block: U+0600-U+06FF
        arabic_chars = re.findall(r"[\u0600-\u06FF]", text)
        assert len(arabic_chars) >= 10, (
            f"ar-SA.ts should contain Arabic-script characters, found {len(arabic_chars)}. "
            f"Arabic translations may be missing or replaced with placeholders."
        )

    def test_arabic_locale_workflow_builder_is_arabic(self) -> None:
        text = _read_locale("ar-SA")
        block = _extract_workflow_builder_block(text)
        assert block is not None
        pairs = dict(re.findall(r"(t\d{3}):\s*'([^']*)'", block))
        assert len(pairs) >= 30, f"ar-SA: only {len(pairs)} workflowBuilder keys found"
        # Count keys with Arabic content
        arabic_count = sum(
            1 for v in pairs.values() if re.search(r"[\u0600-\u06FF]", v)
        )
        assert arabic_count >= 20, (
            f"ar-SA: only {arabic_count}/34 workflowBuilder keys have Arabic content. "
            f"Expected most keys to be in Arabic script."
        )


class TestLocaleCoverage:
    """Per-locale coverage report."""

    def test_all_locales_have_workflow_builder(self) -> None:
        missing = []
        for loc in EXPECTED_LOCALES:
            block = _extract_workflow_builder_block(_read_locale(loc))
            if not block or len(_extract_keys(block)) != 34:
                missing.append(loc)
        assert not missing, f"workflowBuilder incomplete in: {missing}"

    def test_total_workflow_builder_keys_count(self) -> None:
        """Sum of workflowBuilder.tNNN across all locales = 34 * 9 = 306."""
        total = 0
        for loc in EXPECTED_LOCALES:
            block = _extract_workflow_builder_block(_read_locale(loc)) or ""
            total += len(_extract_keys(block))
        assert total == 34 * 9, f"Expected 306 total workflowBuilder keys, got {total}"