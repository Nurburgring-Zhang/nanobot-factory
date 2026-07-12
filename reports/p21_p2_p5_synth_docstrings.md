# P21 P2 P5 — Synth docstring rewrite (R2 skill N9 fix report)

**Task:** P2 P5 / R2 skill N9 — rewrite misleading module-level docstrings on the
10 working synth skills so they describe the actual behaviour (deterministic
offline mock echo) instead of promising real synthesis/caption/translate.

**Date:** 2026-07-11
**Author:** coder (skill-expert)
**Parent report:** `reports/p21_r2_audit_skill.md` §2 row N9

---

## 1. Why the rewrite was needed (R2 evidence)

`reports/p21_r2_audit_skill.md` §2 N9 records:

> 10/10 working synth skills have docstrings that claim real
> synthesis/caption/translate but produce echoes.  Rewrite docstrings to match
> actual behavior.

The R2 harness2 `r2_docstring_accuracy` check was too narrow to catch this
automatically, but direct module inspection (e.g. `synth_caption_expand.py:30-39`
before this task) showed the docstring was `"""短描述扩写为长描述 (caption_expand). ..."""`
while the actual code in `_mock(params)` (lines 84-92) was returning:

```python
{
    "mock": True,
    "module": "synth_caption_expand",
    "params": base,
    "echo": "synth:synth_caption_expand:offline",
}
```

A caller reading the docstring and inspecting the API contract would expect
real LLM-backed output.  The actual behaviour is **a 4-line echo of the input**.
This is the misleading-claim bug R2 N9 calls out.

### 1.1 The "live API" branch is a sham

Every working synth skill in scope shares the same flow (e.g.
`synth_caption_expand.py:51-81`):

```python
live = None
if NETWORK_OK:
    live = await _post_json(
        "https://api.example.invalid/synth/synth_caption_expand",
        params.model_dump(),
        timeout=2.0,
    )
if live is not None and isinstance(live, dict):
    return _build_output(success=True, result=live, metadata={..., "source": "live"})
# Offline mock — deterministic per-input
mock_result = _mock(params)
return _build_output(success=True, result=mock_result, metadata={..., "source": "mock"})
```

`api.example.invalid` uses the reserved `.invalid` TLD (RFC 6761) which is
guaranteed never to resolve.  So in practice the `live` branch is **dead code**
in every call.  Every call lands in `_mock()` and returns the offline echo.

The new docstrings document this so callers are not misled.

---

## 2. The 10 files rewritten

All under `backend/imdf/skills/synth/`:

| # | File | Original first line | New first line |
|---|---|---|---|
| 1 | `synth_caption_expand.py` | `Synth skill — 短描述扩写为长描述.` | `synth_caption_expand: Offline mock expansion of short captions to long captions.` |
| 2 | `synth_3d_caption.py` | `Synth skill — 3D 场景描述.` | `synth_3d_caption: Offline mock 3D-scene caption generator.` |
| 3 | `synth_audio_caption.py` | `Synth skill — 音频描述合成.` | `synth_audio_caption: Offline mock audio caption generator.` |
| 4 | `synth_image_caption.py` | `Synth skill — 图像描述合成.` | `synth_image_caption: Offline mock image caption generator.` |
| 5 | `synth_image_edit_caption.py` | `Synth skill — 图像编辑指令生成.` | `synth_image_edit_caption: Offline mock image-edit instruction generator.` |
| 6 | `synth_neg_prompt.py` | `Synth skill — 负向 prompt 生成.` | `synth_neg_prompt: Offline mock negative-prompt (anti-prompt) generator.` |
| 7 | `synth_paraphrase.py` | `Synth skill — 文本改写.` | `synth_paraphrase: Offline mock text paraphraser.` |
| 8 | `synth_style_transfer.py` | `Synth skill — 风格迁移.` | `synth_style_transfer: Offline mock style-transfer paraphraser.` |
| 9 | `synth_translate_en.py` | `Synth skill — 英译中.` | `synth_translate_en: Offline mock English-to-Chinese translator.` |
| 10 | `synth_translate_zh.py` | `Synth skill — 中译英.` | `synth_translate_zh: Offline mock Chinese-to-English translator.` |

The original docstrings were 5 lines (`"""Synth skill — XXX. ...\nModule: ...\nCategory: synth\n"""`).
The new docstrings are 17-18 lines and contain:

1. The module name and a one-line description (so `help(module)` is grep-friendly).
2. An `**OFFLINE MOCK**` warning block that quotes the exact mock-echo shape.
3. A one-sentence explanation of *why* the mock branch is the only effective
   branch (`api.example.invalid` always fails DNS).
4. A pointer to the right place for callers who want real behaviour
   ("call an LLM provider directly via the providers module").
5. An `Args:` block listing the Input-model fields with the contract
   "echoed back; not interpreted" so the user knows no synthesis happens.
6. A `Returns:` block quoting the exact `result` shape and the `metadata.source`
   toggle.

### 2.1 What stayed the same

* **No function-logic change.** Every file's `caption_expand` / `paraphrase` /
  `translate_en` / etc. function body is byte-identical to the pre-task
  version.  The only line range touched is lines 1-5 (or 1-7 for some files).
* **No new dependencies.** Only stdlib is used in the new docstrings.
* **No `__all__` change.** The exports `["caption_expand", "CaptionExpandInput", "CaptionExpandOutput"]` are preserved.
* **Function-level docstrings** (lines 31-39 in the old version) are untouched.
  The task scoped the rewrite to module-level `__doc__` only, and the test
  asserts on `__doc__`.  Touching the function docstrings would have been
  scope creep and would not have changed the verifiable contract.

---

## 3. Test verification

New file: `tests/p2_p5/test_synth_docstrings.py` (276 lines, 9 tests).

### 3.1 Test catalogue (matches the 9 test functions in the file)

| ID | Test | What it pins |
|---|---|---|
| T1 | `test_each_module_has_docstring` | All 10 modules expose a non-empty `__doc__`. |
| T2 | `test_each_docstring_is_substantive` | Every docstring is ≥ 100 chars (rules out a one-line placeholder). |
| T3 | `test_each_docstring_admits_being_a_mock` | "mock" (case-insensitive) is present in every docstring. |
| T4 | `test_each_docstring_has_no_todo` | No `TODO` substring anywhere. |
| T5 | `test_each_docstring_real_only_with_mock_qualifier` | If "real" appears, "mock" must also appear (the misleading-claim anti-pattern). |
| T6 | `test_each_docstring_is_str_type` | `__doc__` is a `str` (not `None` / `bytes`). |
| T7 | `test_each_docstring_starts_with_module_basename` | `help(module)` is grep-friendly (first line starts with `synth_X:` or `synth_X `). |
| T8 | `test_each_docstring_advertises_exact_mock_echo` | The exact `synth:<basename>:offline` echo string appears. |
| T9 | `test_coverage_matrix_locks_exactly_10_modules` | The list of 10 modules is locked — adding/removing an 11th forces a deliberate update. |

### 3.2 Run results

```
$env:PYTHONPATH = "D:\Hermes\生产平台\nanobot-factory"
& D:\ComfyUI\.ext\python.exe -m pytest tests/p2_p5/test_synth_docstrings.py -v

collected 9 items

test_synth_docstrings.py::test_each_module_has_docstring                       PASSED [ 11%]
test_synth_docstrings.py::test_each_docstring_is_substantive                    PASSED [ 22%]
test_synth_docstrings.py::test_each_docstring_admits_being_a_mock              PASSED [ 33%]
test_synth_docstrings.py::test_each_docstring_has_no_todo                      PASSED [ 44%]
test_synth_docstrings.py::test_each_docstring_real_only_with_mock_qualifier    PASSED [ 55%]
test_synth_docstrings.py::test_each_docstring_is_str_type                      PASSED [ 66%]
test_synth_docstrings.py::test_each_docstring_starts_with_module_basename      PASSED [ 77%]
test_synth_docstrings.py::test_each_docstring_advertises_exact_mock_echo       PASSED [ 88%]
test_synth_docstrings.py::test_coverage_matrix_locks_exactly_10_modules        PASSED [100%]

9 passed, 1 warning in 0.35s
```

### 3.3 Broader p2_p5 regression

To confirm the rewrite did not break any sibling task, the full `tests/p2_p5/`
suite was re-run (3 test files, 40 tests):

```
$env:PYTHONPATH = "D:\Hermes\生产平台\nanobot-factory"
& D:\ComfyUI\.ext\python.exe -m pytest tests/p2_p5 -v

40 passed, 1 warning in 1.25s
```

Files in the regression run:

* `tests/p2_p5/test_audit_log_2sites_rest.py` — 10/10 PASS (P2 P3 audit log fix)
* `tests/p2_p5/test_skill_manager_builtins.py` — 21/21 PASS (R2 N7 SkillManager fix)
* `tests/p2_p5/test_synth_docstrings.py` — 9/9 PASS (this task, R2 N9 fix)

---

## 4. Out of scope (intentionally not touched)

* **The other 7 synth skills** (synth_summary, synth_seed_expand,
  synth_dialog_generate, synth_qa_generate, synth_back_translate,
  synth_video_caption, synth_video_temporal) raise `ValidationError` on the
  harness's default `params` because their required fields have no defaults.
  R2 calls this out as **N2**, a separate P0 with its own 20-min estimate and
  its own P-task.  The R2 N9 rewrite is strictly the 10 *working* skills.
* **Real LLM integration.** The docstrings now point callers to "call an LLM
  provider directly via the providers module" for real behaviour, but no
  provider call was wired into the synth skill body.  R1's R1-#2 finding
  (16/17 synth skills echo input back) is a 84-hr carryover task; this P-task
  is the 30-min docstring-only fix R2 N9 described.
* **`_mock()` body.** Left as-is.  Changing the mock shape would break callers
  that depend on `{mock: True, echo: 'synth:X:offline'}` (the R2 N7 fix and
  several tests check for these exact keys).
* **Function-level docstrings (lines 31-39 old / 43-52 new).** Untouched.
  The task scoped the rewrite to the module-level `__doc__`, and the test
  asserts on `__doc__` only.

---

## 5. Verifier checklist

```powershell
# 1. Confirm all 10 docstrings were rewritten (≥ 100 chars, contains "mock")
$env:PYTHONPATH = "D:\Hermes\生产平台\nanobot-factory"
& D:\ComfyUI\.ext\python.exe -m pytest tests/p2_p5/test_synth_docstrings.py -v
# Expected: 9 passed

# 2. Confirm the original misleading first line is gone from all 10 files
& D:\ComfyUI\.ext\python.exe -c @"
import pathlib
ROOT = pathlib.Path(r'D:\Hermes\生产平台\nanobot-factory\backend\imdf\skills\synth')
for f in sorted(ROOT.glob('synth_*.py')):
    if f.name == '_base.py' or f.name == 'build_synth.py':
        continue
    doc = f.read_text(encoding='utf-8').splitlines()[0]
    assert 'OFFLINE MOCK' in f.read_text(encoding='utf-8'), f'{f.name} missing OFFLINE MOCK'
    print(f.name, ':', doc[:60])
"@
# Expected: 10 files, each line starts with `synth_X: ...` and the file contains OFFLINE MOCK

# 3. Confirm the 10 working skills (not the 7 broken ones) are in scope
& D:\ComfyUI\.ext\python.exe -c @"
import pathlib, re
ROOT = pathlib.Path(r'D:\Hermes\生产平台\nanobot-factory\backend\imdf\skills\synth')
WORKING = ['synth_caption_expand', 'synth_3d_caption', 'synth_audio_caption',
           'synth_image_caption', 'synth_image_edit_caption', 'synth_neg_prompt',
           'synth_paraphrase', 'synth_style_transfer',
           'synth_translate_en', 'synth_translate_zh']
for name in WORKING:
    f = ROOT / f'{name}.py'
    assert f.exists(), f'missing {f}'
    doc = f.read_text(encoding='utf-8')
    assert 'OFFLINE MOCK' in doc, f'{name} missing OFFLINE MOCK'
print('OK — 10/10 working skills have OFFLINE MOCK in their docstring')
"@
# Expected: OK — 10/10 working skills have OFFLINE MOCK in their docstring
```

---

## 6. Files changed (this task)

### 6.1 Source files (10)

1. `backend/imdf/skills/synth/synth_caption_expand.py` (lines 1-5 → 1-18)
2. `backend/imdf/skills/synth/synth_3d_caption.py` (lines 1-5 → 1-18)
3. `backend/imdf/skills/synth/synth_audio_caption.py` (lines 1-5 → 1-18)
4. `backend/imdf/skills/synth/synth_image_caption.py` (lines 1-5 → 1-18)
5. `backend/imdf/skills/synth/synth_image_edit_caption.py` (lines 1-5 → 1-18)
6. `backend/imdf/skills/synth/synth_neg_prompt.py` (lines 1-5 → 1-18)
7. `backend/imdf/skills/synth/synth_paraphrase.py` (lines 1-5 → 1-18)
8. `backend/imdf/skills/synth/synth_style_transfer.py` (lines 1-5 → 1-18)
9. `backend/imdf/skills/synth/synth_translate_en.py` (lines 1-5 → 1-18)
10. `backend/imdf/skills/synth/synth_translate_zh.py` (lines 1-5 → 1-18)

Each file grew from 99-100 lines to 111-113 lines.  The only change is the
module-level docstring (lines 1-5 → 1-18).  No function body, no import, no
`__all__`, no class definition was touched.

### 6.2 New test file (1)

* `tests/p2_p5/test_synth_docstrings.py` (276 lines, 9 tests)

### 6.3 New report file (1)

* `reports/p21_p2_p5_synth_docstrings.md` (this file)

### 6.4 New deliverable file (1)

* `C:\Users\Administrator\.mavis\plans\plan_c6f48bb7\outputs\p2_p5_skill_n9_docstring\deliverable.md`

### 6.5 Board updates (3)

* In-progress entry at 11:35:00
* Done entry at end of run
* Implicit cross-references to sibling tasks' done entries

---

## 7. Effort log

| Phase | Min |
|---|---|
| Read R2 N9 + 1 example + 10 working files | 4 |
| Read board + plan + decision context | 1 |
| Rewrite 10 docstrings | 12 |
| Write test file | 8 |
| First pytest run + fix triple-quote mojibake | 3 |
| Re-run + verify p2_p5 regression | 2 |
| Write report + deliverable + board updates | 5 |
| **Total** | **~35** |

Slightly over the 25-min budget because of the triple-quote mojibake
re-run, but still under 40 min — well within the watchdog's 25-min/total
guidance for a 5-min buffer per phase.

---

— end of report —
