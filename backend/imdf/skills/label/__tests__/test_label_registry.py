"""Tests for the label package __init__.py — registry integrity."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import (
    LABEL_SKILLS,
    get_label_skill,
    label_asr_transcribe,
    label_blip2_vqa,
    label_blip_caption,
    label_clip_multi,
    label_clip_zero,
    label_depth_estimate,
    label_entity_ner,
    label_glm4v,
    label_gpt4v_label,
    label_keyword_extract,
    label_llava_chat,
    label_ocr_text,
    label_pose_detect,
    label_qwen_vl,
    label_sam_segment,
    label_sentiment,
    label_yolo_detect,
    list_label_skills,
    run_label_skill,
)
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_registry_count_17():
    assert len(LABEL_SKILLS) == 17
    assert len(list_label_skills()) == 17


def test_all_skill_ids_unique():
    ids = [s.skill_id for s in LABEL_SKILLS]
    assert len(set(ids)) == 17


def test_get_label_skill_known_and_unknown():
    s = get_label_skill("label_clip_zero")
    assert s.skill_id == "label_clip_zero"
    assert s.handler is label_clip_zero
    try:
        get_label_skill("label_unknown")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for unknown skill")


def test_run_label_skill_unknown_returns_failure():
    out = _run(run_label_skill("label_does_not_exist", SkillInput(params={})))
    assert out.success is False


def test_run_label_skill_dispatch():
    out = _run(run_label_skill("label_clip_zero", SkillInput(params={
        "image": "img.png", "candidates": ["a", "b"],
    })))
    assert out.success is True


def test_star_import_via_package():
    """Smoke test: every handler is importable from the package."""
    handlers = [
        label_clip_zero, label_clip_multi, label_blip_caption, label_blip2_vqa,
        label_llava_chat, label_gpt4v_label, label_qwen_vl, label_glm4v,
        label_yolo_detect, label_sam_segment, label_depth_estimate, label_pose_detect,
        label_ocr_text, label_asr_transcribe,
        label_sentiment, label_entity_ner, label_keyword_extract,
    ]
    assert len(handlers) == 17
    for h in handlers:
        assert callable(h)


def test_each_skill_has_inputs_and_outputs_schema():
    for s in LABEL_SKILLS:
        assert s.inputs_schema, f"{s.skill_id} missing inputs_schema"
        assert s.outputs_schema, f"{s.skill_id} missing outputs_schema"
        assert s.category, f"{s.skill_id} missing category"


def test_categories_unique_distribution():
    cats = {s.category for s in LABEL_SKILLS}
    # Should cover >= 6 categories
    assert len(cats) >= 6