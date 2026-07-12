# P20 L — Label Skills (17 skills)

**Status:** DONE — 17 skills implemented, **104 tests passing** (all 17 modules + 1 registry test).

**Date:** 2026-07-09
**Task:** Build 17 label skills for the nanobot-factory platform.

---

## Skill List (17 total)

| # | skill_id | Category | Description |
|---|----------|----------|-------------|
| 1 | `label_clip_zero`       | classify | CLIP zero-shot image classification |
| 2 | `label_clip_multi`      | classify | CLIP multi-label classification (sigmoid) |
| 3 | `label_blip_caption`    | caption  | BLIP image captioning with style control |
| 4 | `label_blip2_vqa`       | vqa      | BLIP-2 visual question answering |
| 5 | `label_llava_chat`      | chat     | LLaVA multi-turn multimodal chat |
| 6 | `label_gpt4v_label`     | label    | GPT-4V multimodal labeling (caption + tags + JSON schema) |
| 7 | `label_qwen_vl`         | label    | Qwen-VL bilingual captioning + tagging (en/zh) |
| 8 | `label_glm4v`           | label    | GLM-4V labeling (caption / classify / extract) |
| 9 | `label_yolo_detect`     | detect   | YOLO object detection with bounding boxes |
| 10 | `label_sam_segment`    | segment  | SAM (Segment Anything) — auto/box/point masks |
| 11 | `label_depth_estimate` | depth    | Monocular depth estimation + stats |
| 12 | `label_pose_detect`    | pose     | Human pose estimation (COCO 17 / Body 18 / Body 25) |
| 13 | `label_ocr_text`       | ocr      | OCR text recognition with regions |
| 14 | `label_asr_transcribe` | asr      | ASR speech-to-text transcription (Whisper) |
| 15 | `label_sentiment`      | nlp      | Sentiment analysis (positive/neutral/negative) |
| 16 | `label_entity_ner`     | nlp      | Named Entity Recognition (PERSON / ORG / LOC / DATE / MONEY / PERCENT) |
| 17 | `label_keyword_extract`| nlp      | Keyword + keyphrase extraction (en/zh) |

---

## File Layout

```
backend/imdf/skills/label/
├── _base.py                   — shared utilities (network probe, SkillOutput builder, mock helpers)
├── __init__.py                — registry: LABEL_SKILLS + handlers + dispatch
├── label_clip_zero.py         (skill 1)
├── label_clip_multi.py        (skill 2)
├── label_blip_caption.py      (skill 3)
├── label_blip2_vqa.py         (skill 4)
├── label_llava_chat.py        (skill 5)
├── label_gpt4v_label.py       (skill 6)
├── label_qwen_vl.py           (skill 7)
├── label_glm4v.py             (skill 8)
├── label_yolo_detect.py       (skill 9)
├── label_sam_segment.py       (skill 10)
├── label_depth_estimate.py    (skill 11)
├── label_pose_detect.py       (skill 12)
├── label_ocr_text.py          (skill 13)
├── label_asr_transcribe.py    (skill 14)
├── label_sentiment.py         (skill 15)
├── label_entity_ner.py        (skill 16)
└── label_keyword_extract.py   (skill 17)

backend/imdf/skills/label/__tests__/
├── conftest.py                                  — path bootstrap (mirrors synth/__tests__/conftest.py)
├── test_label_clip_zero_test.py                 — 5 tests
├── test_label_clip_multi_test.py                — 5 tests
├── test_label_blip_caption_test.py              — 5 tests
├── test_label_blip2_vqa_test.py                 — 5 tests
├── test_label_llava_chat_test.py                — 6 tests
├── test_label_gpt4v_label_test.py               — 5 tests
├── test_label_qwen_vl_test.py                   — 5 tests
├── test_label_glm4v_test.py                     — 6 tests
├── test_label_yolo_detect_test.py               — 6 tests
├── test_label_sam_segment_test.py               — 6 tests
├── test_label_depth_estimate_test.py            — 5 tests
├── test_label_pose_detect_test.py               — 6 tests
├── test_label_ocr_text_test.py                  — 5 tests
├── test_label_asr_transcribe_test.py            — 6 tests
├── test_label_sentiment_test.py                 — 7 tests
├── test_label_entity_ner_test.py                — 6 tests
├── test_label_keyword_extract_test.py           — 7 tests
└── test_label_registry.py                       — 8 registry tests
```

**Total: 104 tests across 18 test files.**

---

## Per-Skill Function Signature

Every skill module exposes:

```python
async def label_<name>(input: SkillInput) -> SkillOutput
```

* **Input:** `SkillInput(prompt="", params={...}, context={...})` (from `backend.skills.legacy.SkillInput`)
* **Output:** `SkillOutput(success: bool, result: Any, error: str, metadata: Dict)` (from `backend.skills.legacy.SkillOutput`)
* **Validation:** Each skill has a `XxxInput(BaseModel)` Pydantic model with strict field constraints (`min_length`, `ge`, `le`, `Literal[...]`, `field_validator`).
* **HTTP:** Live mode calls a remote endpoint via `httpx.AsyncClient(timeout=5-10s)`. On failure or `LABEL_OFFLINE=1`, falls back to deterministic offline mock.
* **Metadata envelope:** Every successful output embeds `{timestamp, source, confidence, elapsed_ms}` via the shared `build_output()` helper.

---

## Sample Inputs / Outputs

### label_clip_zero
```python
SkillInput(params={
    "image": "https://example.com/cat.jpg",
    "candidates": ["cat", "dog", "car"],
})
```
```python
SkillOutput(success=True,
    result={"label": "cat", "score": 0.42,
            "scores": {"cat": 0.42, "dog": 0.31, "car": 0.27},
            "top_k": [{"label": "cat", "score": 0.42}, ...],
            "model": "clip-vit-l14"},
    metadata={"skill_module": "label", "source": "mock",
              "confidence": 0.42, "elapsed_ms": 0.04})
```

### label_blip_caption
```python
SkillInput(params={"image": "https://example.com/scene.jpg", "style": "factual", "max_length": 80})
```
```python
SkillOutput(success=True,
    result={"caption": "An image showing a quiet alley, with rich detail and balanced composition.",
            "style": "factual", "model": "blip-base"},
    metadata={"source": "mock", "confidence": 0.75, ...})
```

### label_yolo_detect
```python
SkillInput(params={"image": "/tmp/street.jpg", "conf_threshold": 0.5})
```
```python
SkillOutput(success=True,
    result={
      "boxes": [
        {"label": "person", "score": 0.78, "bbox": [120, 80, 240, 280]},
        {"label": "car", "score": 0.62, "bbox": [340, 180, 480, 320]},
      ],
      "count": 2, "classes": ["person", "bicycle", "car", ...],
    },
    metadata={"source": "mock", "confidence": 0.75})
```

### label_sentiment
```python
SkillInput(params={"text": "I love this product. It is amazing!", "lang": "en", "granularity": "sentence"})
```
```python
SkillOutput(success=True,
    result={
      "label": "positive", "score": 0.667,
      "sentences": [
        {"text": "I love this product.", "label": "positive", "score": 0.5},
        {"text": "It is amazing!", "label": "positive", "score": 1.0},
      ],
      "lang": "en",
    },
    metadata={"source": "mock", "confidence": 0.667})
```

---

## Test Count Summary

| Test file | # tests |
|-----------|--------:|
| test_label_clip_zero_test.py        | 5 |
| test_label_clip_multi_test.py       | 5 |
| test_label_blip_caption_test.py     | 5 |
| test_label_blip2_vqa_test.py        | 5 |
| test_label_llava_chat_test.py       | 6 |
| test_label_gpt4v_label_test.py      | 5 |
| test_label_qwen_vl_test.py          | 5 |
| test_label_glm4v_test.py            | 6 |
| test_label_yolo_detect_test.py      | 6 |
| test_label_sam_segment_test.py      | 6 |
| test_label_depth_estimate_test.py   | 5 |
| test_label_pose_detect_test.py      | 6 |
| test_label_ocr_text_test.py         | 5 |
| test_label_asr_transcribe_test.py   | 6 |
| test_label_sentiment_test.py        | 7 |
| test_label_entity_ner_test.py       | 6 |
| test_label_keyword_extract_test.py  | 7 |
| test_label_registry.py              | 8 |
| **Total**                           | **104** |

---

## Test Run

```bash
$ cd backend/imdf/skills/label/__tests__
$ "D:\ComfyUI\.ext\python.exe" -m pytest -v \
    --override-ini="python_files=*_test.py test_*.py" \
    --override-ini="testpaths=" -p no:cacheprovider
...
======================== 104 passed, 2 warnings in 0.23s ========================
```

All 104 tests pass. The two warnings are Pydantic `UserWarning: Field name "schema" in "Gpt4VLabelInput" shadows an attribute in parent "BaseModel"` (harmless — `schema()` is the JSON-schema generator method).

---

## Imports

The package is importable as:

```python
from imdf.skills.label import (
    LABEL_SKILLS, list_label_skills, get_label_skill, run_label_skill,
    label_clip_zero, label_clip_multi,
    label_blip_caption, label_blip2_vqa, label_llava_chat,
    label_gpt4v_label, label_qwen_vl, label_glm4v,
    label_yolo_detect, label_sam_segment, label_depth_estimate, label_pose_detect,
    label_ocr_text, label_asr_transcribe,
    label_sentiment, label_entity_ner, label_keyword_extract,
)
```

Note: The actual import path is `imdf.skills.label` (not `backend.imdf.skills.label` as the task spec mentioned). The `backend.imdf.skills` chain triggers a heavy `__init__.py` that pulls in redfox / vida / meta-kim engines; the conftest.py in `__tests__/` stubs that chain so tests can resolve `imdf.skills.label.<module>` cleanly.

---

## Constraints Met

* ✅ All 17 skill .py files in `backend/imdf/skills/label/`
* ✅ All 17 test files + 1 registry test in `backend/imdf/skills/label/__tests__/`
* ✅ `__init__.py` exposes registry with `LABEL_SKILLS` list + `list_label_skills()` + `get_label_skill()` + `run_label_skill()`
* ✅ Each skill: ~150-line module + ~80-line test
* ✅ Pydantic models for all input/output validation
* ✅ `httpx` for live calls with deterministic offline fallback
* ✅ Offline mode (`LABEL_OFFLINE=1`) works for all 17 skills
* ✅ **No new dependencies added** (only stdlib + already-listed pydantic/httpx)
* ✅ All 104 tests pass
* ✅ Files confined to `backend/imdf/skills/label/` scope (no other files modified)