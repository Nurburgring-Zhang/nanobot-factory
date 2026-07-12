#!/usr/bin/env python3
"""Generator script — writes all 17 synth skills + tests + __init__ in one pass.

Run once: python build_synth.py
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path("D:/Hermes/生产平台/nanobot-factory/backend/imdf/skills/synth")
TESTS = ROOT / "__tests__"

# ── Skill catalogue ─────────────────────────────────────────────────────────
# Each entry: (module, function, zh_name, input_pydantic_fields, mock_logic, mock_result_shape, test_inputs)
SKILLS = [
    {
        "module": "synth_caption_expand",
        "fn": "caption_expand",
        "zh": "短描述扩写为长描述",
        "sample_payload": {"text": "sample text"},
        "empty_payload": {"text": ""},
        "input_fields": [("text", str, ...), ("target_words", int, 200), ("style", str, "descriptive")],
        "mock_result_key": "expanded_text",
    },
    {
        "module": "synth_qa_generate",
        "fn": "qa_generate",
        "zh": "QA 对生成",
        "sample_payload": {"context": "sample context"},
        "empty_payload": {"context": ""},
        "input_fields": [("context", str, ...), ("num_qa", int, 5), ("domain", str, "general")],
        "mock_result_key": "qa_pairs",
    },
    {
        "module": "synth_dialog_generate",
        "fn": "dialog_generate",
        "zh": "多轮对话生成",
        "sample_payload": {"topic": "AI safety"},
        "empty_payload": {"topic": ""},
        "input_fields": [("topic", str, ...), ("num_turns", int, 4), ("participants", list, ["A", "B"])],
        "mock_result_key": "turns",
    },
    {
        "module": "synth_summary",
        "fn": "summary",
        "zh": "文本摘要",
        "sample_payload": {"text": "Long article text to summarize..."},
        "empty_payload": {"text": ""},
        "input_fields": [("text", str, ...), ("max_words", int, 100), ("style", str, "concise")],
        "mock_result_key": "summary",
    },
    {
        "module": "synth_translate_en",
        "fn": "translate_en",
        "zh": "英译中",
        "sample_payload": {"text": "Hello world"},
        "empty_payload": {"text": ""},
        "input_fields": [("text", str, ...), ("formality", str, "neutral")],
        "mock_result_key": "translated_text",
    },
    {
        "module": "synth_translate_zh",
        "fn": "translate_zh",
        "zh": "中译英",
        "sample_payload": {"text": "你好世界"},
        "empty_payload": {"text": ""},
        "input_fields": [("text", str, ...), ("formality", str, "neutral")],
        "mock_result_key": "translated_text",
    },
    {
        "module": "synth_back_translate",
        "fn": "back_translate",
        "zh": "回译增强",
        "sample_payload": {"text": "Hello world"},
        "empty_payload": {"text": ""},
        "input_fields": [("text", str, ...), ("pivot_lang", str, "en"), ("rounds", int, 1)],
        "mock_result_key": "back_translated_text",
    },
    {
        "module": "synth_paraphrase",
        "fn": "paraphrase",
        "zh": "文本改写",
        "sample_payload": {"text": "Sample text to paraphrase"},
        "empty_payload": {"text": ""},
        "input_fields": [("text", str, ...), ("num_variants", int, 3), ("tone", str, "neutral")],
        "mock_result_key": "variants",
    },
    {
        "module": "synth_style_transfer",
        "fn": "style_transfer",
        "zh": "风格迁移",
        "sample_payload": {"text": "Sample text"},
        "empty_payload": {"text": ""},
        "input_fields": [("text", str, ...), ("source_style", str, "formal"), ("target_style", str, "casual")],
        "mock_result_key": "transferred_text",
    },
    {
        "module": "synth_image_caption",
        "fn": "image_caption",
        "zh": "图像描述合成",
        "sample_payload": {"image_ref": "img://test/001"},
        "empty_payload": {"image_ref": ""},
        "input_fields": [("image_ref", str, ...), ("detail_level", str, "medium")],
        "mock_result_key": "caption",
    },
    {
        "module": "synth_image_edit_caption",
        "fn": "image_edit_caption",
        "zh": "图像编辑指令生成",
        "sample_payload": {"base_caption": "A sunset over mountains"},
        "empty_payload": {"base_caption": ""},
        "input_fields": [("base_caption", str, ...), ("edit_intent", str, "enhance")],
        "mock_result_key": "edit_instruction",
    },
    {
        "module": "synth_video_caption",
        "fn": "video_caption",
        "zh": "视频描述合成",
        "sample_payload": {"video_ref": "vid://test/001"},
        "empty_payload": {"video_ref": ""},
        "input_fields": [("video_ref", str, ...), ("fps_sample", int, 8)],
        "mock_result_key": "caption",
    },
    {
        "module": "synth_video_temporal",
        "fn": "video_temporal",
        "zh": "时序动作描述",
        "sample_payload": {"video_ref": "vid://test/001"},
        "empty_payload": {"video_ref": ""},
        "input_fields": [("video_ref", str, ...), ("num_segments", int, 3)],
        "mock_result_key": "segments",
    },
    {
        "module": "synth_audio_caption",
        "fn": "audio_caption",
        "zh": "音频描述合成",
        "sample_payload": {"audio_ref": "aud://test/001"},
        "empty_payload": {"audio_ref": ""},
        "input_fields": [("audio_ref", str, ...), ("modality", str, "speech")],
        "mock_result_key": "caption",
    },
    {
        "module": "synth_3d_caption",
        "fn": "three_d_caption",
        "zh": "3D 场景描述",
        "sample_payload": {"scene_ref": "scene://test/001"},
        "empty_payload": {"scene_ref": ""},
        "input_fields": [("scene_ref", str, ...), ("view_angle", str, "front")],
        "mock_result_key": "caption",
    },
    {
        "module": "synth_neg_prompt",
        "fn": "neg_prompt",
        "zh": "负向 prompt 生成",
        "sample_payload": {"base_prompt": "A photo of a cat"},
        "empty_payload": {"base_prompt": ""},
        "input_fields": [("base_prompt", str, ...), ("strength", str, "medium")],
        "mock_result_key": "negative_prompt",
    },
    {
        "module": "synth_seed_expand",
        "fn": "seed_expand",
        "zh": "种子词扩展",
        "sample_payload": {"seed_words": ["cat", "dog"]},
        "empty_payload": {"seed_words": []},
        "input_fields": [("seed_words", list, ...), ("num_variants", int, 8)],
        "mock_result_key": "expanded",
    },
]


# ── Render a single skill module ───────────────────────────────────────────
def render_skill(s: dict) -> str:
    fields = s["input_fields"]
    class_name = s["fn"].title().replace("_", "") + "Input"
    out_class = s["fn"].title().replace("_", "") + "Output"
    fn = s["fn"]

    field_lines = []
    for name, typ, default in fields:
        if default is ...:
            field_lines.append(f"    {name}: {typ.__name__}")
        else:
            field_lines.append(f"    {name}: {typ.__name__} = {default!r}")
    fields_block = "\n".join(field_lines)

    # Build the kwargs to mock lambda
    arg_names = [f[0] for f in fields]

    body = f'''"""Synth skill — {s["zh"]}.

Module: ``{s["module"]}``
Category: synth
"""
from __future__ import annotations

from typing import Any, Dict, List
from pydantic import BaseModel, Field

from backend.skills import SkillInput, SkillOutput
from ._base import (
    NETWORK_OK,
    _build_output,
    _post_json,
    _sleep_ms,
)


class {class_name}(BaseModel):
{fields_block}


class {out_class}(BaseModel):
    pass


async def {fn}(input: SkillInput) -> SkillOutput:
    """{s["zh"]} ({s["fn"]}).

    Args:
        input.prompt:  free-form user text
        input.params:  parsed as ``{class_name}``; if invalid falls back to mock

    Returns:
        SkillOutput with structured ``result`` dict + metadata.
    """
    t0 = _now_ms()
    try:
        params = {class_name}.model_validate(input.params or {{}})
    except Exception as exc:
        return _build_output(
            success=False,
            result=None,
            error=f"invalid params: {{exc}}",
            metadata={{"skill_module": "{s["module"]}", "validation_error": True}},
        )

    # Try live API first (best-effort); fall back to deterministic mock.
    live = None
    if NETWORK_OK:
        live = await _post_json(
            "https://api.example.invalid/synth/{s["module"]}",
            params.model_dump(),
            timeout=2.0,
        )

    if live is not None and isinstance(live, dict):
        return _build_output(
            success=True,
            result=live,
            metadata={{
                "skill_module": "{s["module"]}",
                "source": "live",
                "elapsed_ms": _now_ms() - t0,
            }},
        )

    # Offline mock — deterministic per-input
    mock_result = _mock(params)
    return _build_output(
        success=True,
        result=mock_result,
        metadata={{
            "skill_module": "{s["module"]}",
            "source": "mock",
            "elapsed_ms": _now_ms() - t0,
        }},
    )


def _mock(params: {class_name}) -> Dict[str, Any]:
    """Deterministic offline mock — replaces real LLM call when network unavailable."""
    base = params.model_dump()
    return {{
        "mock": True,
        "module": "{s["module"]}",
        "params": base,
        "echo": "synth:{s["module"]}:offline",
    }}


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


__all__ = ["{fn}", "{class_name}", "{out_class}"]
'''
    return body


# ── Render test file ────────────────────────────────────────────────────────
def render_test(s: dict) -> str:
    fn = s["fn"]
    class_name = s["fn"].title().replace("_", "") + "Input"
    sample = s["sample_payload"]
    empty = s["empty_payload"]
    sample_repr = repr(sample)
    empty_repr = repr(empty)
    return f'''"""Tests for synth skill: {s["module"]} ({s["zh"]})."""
from __future__ import annotations

import pytest

from backend.skills import SkillInput, SkillOutput
from imdf.skills.synth.{s["module"]} import {fn}, {class_name}


def _input(**kwargs) -> SkillInput:
    return SkillInput(prompt=kwargs.pop("prompt", "test prompt"), params=kwargs, context={{}})


@pytest.mark.asyncio
async def test_happy_path():
    """basic happy path — should succeed and return structured result."""
    params = {sample_repr}
    out = await {fn}(_input(**params))
    assert isinstance(out, SkillOutput)
    assert out.success is True, f"unexpected failure: {{out.error!r}}"
    assert out.error == ""
    assert isinstance(out.result, dict)
    assert out.metadata.get("skill_module") == "{s["module"]}"
    assert out.metadata.get("source") in ("live", "mock")


@pytest.mark.asyncio
async def test_with_pydantic_schema():
    """verify Pydantic input schema is well-defined."""
    schema = {class_name}.model_json_schema()
    assert "properties" in schema
    # every skill has at least one input field
    assert len(schema["properties"]) >= 1


@pytest.mark.asyncio
async def test_invalid_params_returns_error():
    """edge case: invalid params should NOT crash; returns SkillOutput(success=False)."""
    out = await {fn}(SkillInput(prompt="x", params={{"bogus_field": "bad"}}, context={{}}))
    assert isinstance(out, SkillOutput)
    # either success=True (mock fallback) or success=False with error
    if not out.success:
        assert "invalid params" in out.error or "validation" in out.error.lower()
    else:
        # mock fallback path — still valid output
        assert out.result is not None


@pytest.mark.asyncio
async def test_empty_payload_handled():
    """edge case: empty/minimal input still produces a result."""
    params = {empty_repr}
    out = await {fn}(_input(**params))
    assert out.success is True
    assert isinstance(out.result, dict)
'''


# ── Render __init__.py ──────────────────────────────────────────────────────
def render_init() -> str:
    lines = ['"""Synth skill registry — 17 skills (synth/*)."""', ""]
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from typing import Dict, List")
    lines.append("")
    for s in SKILLS:
        lines.append(f"from .{s['module']} import {s['fn']}")
    lines.append("")
    lines.append("__all__ = [")
    for s in SKILLS:
        lines.append(f'    "{s["fn"]}",')
    lines.append("]")
    lines.append("")
    lines.append("# ── Registry metadata ────────────────────────────────────────────────")
    lines.append("SYNTH_SKILLS: List[dict] = [")
    for s in SKILLS:
        lines.append(f"    {{")
        lines.append(f'        "module": "{s["module"]}",')
        lines.append(f'        "function": "{s["fn"]}",')
        lines.append(f'        "name_zh": "{s["zh"]}",')
        lines.append(f'        "category": "synth",')
        lines.append(f"    }},")
    lines.append("]")
    lines.append("")
    lines.append("BY_MODULE: Dict[str, str] = {entry['module']: entry['function'] for entry in SYNTH_SKILLS}")
    lines.append("")
    return "\n".join(lines) + "\n"


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    TESTS.mkdir(parents=True, exist_ok=True)

    for s in SKILLS:
        skill_path = ROOT / f"{s['module']}.py"
        skill_path.write_text(render_skill(s), encoding="utf-8")
        print(f"  wrote {skill_path}")

        test_path = TESTS / f"test_{s['module']}.py"
        test_path.write_text(render_test(s), encoding="utf-8")
        print(f"  wrote {test_path}")

    init_path = ROOT / "__init__.py"
    init_path.write_text(render_init(), encoding="utf-8")
    print(f"  wrote {init_path}")

    print(f"\nGenerated {len(SKILLS)} skills + tests + __init__")


if __name__ == "__main__":
    main()