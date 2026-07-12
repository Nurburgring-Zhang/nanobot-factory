# P21 P2 P3 (revised) — Synth Skill Required-Field Defaults

**Date:** 2026-07-11
**Worker:** coder (skill-expert, mvs_e7d46362ec8642b09f56e4d283606bae)
**Audit finding closed:** R2 skill **N2** — 7/17 synth skills have required fields with NO defaults

## 1. Summary

Closed the R2 audit finding N2 by adding `Field(default=...)` to the listed required
field in each of the 7 synth skill input models. All 7 skills now accept `params={}`
(or minimal valid params) and run to mock-fallback without `ValidationError`. Verified
with a new parametrized regression-guard test (23 cases) that the audit fields have
defaults, the input models validate, and the skill functions run end-to-end.

## 2. Changed files

### 2.1 Skill source files (7)

| # | File | Field | Old | New |
|---|------|-------|-----|-----|
| 1 | `backend/imdf/skills/synth/synth_back_translate.py` | `rounds` | `int = 1` | `int = Field(default=2)` |
| 2 | `backend/imdf/skills/synth/synth_dialog_generate.py` | `num_turns` | `int = 4` | `int = Field(default=3)` |
| 3 | `backend/imdf/skills/synth/synth_qa_generate.py` | `num_qa` | `int = 5` | `int = Field(default=5)` |
| 4 | `backend/imdf/skills/synth/synth_seed_expand.py` | `seed_words` | `list` (no default) | `list = Field(default_factory=lambda: [...10 words...])` |
| 5 | `backend/imdf/skills/synth/synth_summary.py` | `max_words` | `int = 100` | `int = Field(default=50)` |
| 6 | `backend/imdf/skills/synth/synth_video_caption.py` | `fps_sample` | `int = 8` | `int = Field(default=1)` |
| 7 | `backend/imdf/skills/synth/synth_video_temporal.py` | `num_segments` | `int = 3` | `int = Field(default=4)` |

All 7 files already had `from pydantic import BaseModel, Field` at the top, so the
`Field` symbol was importable without further changes.

`Field` is already imported in all 7 files. No new imports added.

### 2.2 Test file (1 new)

| File | Purpose |
|------|---------|
| `tests/p2_p3_revised/test_synth_defaults.py` | 23 regression-guard tests (21 parametrized + 2 standalone) covering all 7 skills |

### 2.3 Reports / deliverables (2 new)

| File | Purpose |
|------|---------|
| `reports/p21_p2_p3r_synth.md` | This report |
| `C:\Users\Administrator\.mavis\plans\plan_a15a5e66\outputs\p2_p3r_skill_synth_defaults\deliverable.md` | Engine summary |

## 3. What was changed (per file)

### 3.1 synth_summary.py (max_words: 100 → Field(default=50))

```diff
 class SummaryInput(BaseModel):
     text: str
-    max_words: int = 100
+    max_words: int = Field(default=50)
     style: str = 'concise'
```

### 3.2 synth_back_translate.py (rounds: 1 → Field(default=2))

```diff
 class BackTranslateInput(BaseModel):
     text: str
     pivot_lang: str = 'en'
-    rounds: int = 1
+    rounds: int = Field(default=2)
```

### 3.3 synth_dialog_generate.py (num_turns: 4 → Field(default=3))

```diff
 class DialogGenerateInput(BaseModel):
     topic: str
-    num_turns: int = 4
+    num_turns: int = Field(default=3)
     participants: list = ['A', 'B']
```

### 3.4 synth_qa_generate.py (num_qa: 5 → Field(default=5))

```diff
 class QaGenerateInput(BaseModel):
     context: str
-    num_qa: int = 5
+    num_qa: int = Field(default=5)
     domain: str = 'general'
```

### 3.5 synth_seed_expand.py (seed_words: list → Field(default_factory=...))

`seed_words` was the only field in the 7 audit list that genuinely had no default.
Since `list` is mutable, using `Field(default=...)` with a literal list would risk
shared-mutable-default bugs. Used `Field(default_factory=lambda: [...])` with a
10-element list of common English words, matching the audit's "10 seed words"
intent:

```diff
 class SeedExpandInput(BaseModel):
-    seed_words: list
+    seed_words: list = Field(
+        default_factory=lambda: [
+            "cat", "dog", "sun", "tree", "house",
+            "car", "book", "water", "fire", "mountain",
+        ]
+    )
     num_variants: int = 8
```

### 3.6 synth_video_caption.py (fps_sample: 8 → Field(default=1))

```diff
 class VideoCaptionInput(BaseModel):
     video_ref: str
-    fps_sample: int = 8
+    fps_sample: int = Field(default=1)
```

### 3.7 synth_video_temporal.py (num_segments: 3 → Field(default=4))

```diff
 class VideoTemporalInput(BaseModel):
     video_ref: str
-    num_segments: int = 3
+    num_segments: int = Field(default=4)
```

## 4. Test design

`tests/p2_p3_revised/test_synth_defaults.py` has 5 test functions (4 parametrized
× 7 cases + 1 standalone factory + 1 standalone empty-params = 23 cases total):

1. `test_audit_field_has_default[×7]` — every audit field has a default or
   default_factory, and the literal default matches the suggested value
2. `test_input_model_validates_with_minimal_params[×7]` —
   `InputClass.model_validate(<minimal params>)` does not raise
3. `test_skill_runs_with_minimal_params[×7]` —
   `await skill_fn(SkillInput(params=<minimal params>))` returns success=True
   (mock data)
4. `test_seed_words_default_factory_runs` — `seed_words` factory returns a
   10-element list
5. `test_seed_expand_with_completely_empty_params` — the headline N2 claim
   "`params={}` raises ValidationError" is closed for the only field that
   actually had no default

`_COVERAGE` matrix is locked at 7 rows via `assert len(_COVERAGE) == 7` —
any future worker who adds a 8th audit row must update this assertion.

## 5. Test results

| Suite | Result |
|-------|--------|
| `tests/p2_p3_revised/test_synth_defaults.py` (23 cases) | **23 passed** in 0.47s |
| `backend/imdf/skills/synth/__tests__/*` (68 cases, existing) | **68 passed** in 0.25s — no regression |

## 6. Verifier checklist

```powershell
# 1. Confirm all 7 audit fields now have defaults
$env:PYTHONPATH = "D:\Hermes\生产平台\nanobot-factory"
& D:\ComfyUI\.ext\python.exe -c "
import sys
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from pydantic_core import PydanticUndefined as U
from imdf.skills.synth.synth_summary import SummaryInput
from imdf.skills.synth.synth_back_translate import BackTranslateInput
from imdf.skills.synth.synth_dialog_generate import DialogGenerateInput
from imdf.skills.synth.synth_qa_generate import QaGenerateInput
from imdf.skills.synth.synth_seed_expand import SeedExpandInput
from imdf.skills.synth.synth_video_caption import VideoCaptionInput
from imdf.skills.synth.synth_video_temporal import VideoTemporalInput
for cls, field in [(SummaryInput,'max_words'), (BackTranslateInput,'rounds'),
                   (DialogGenerateInput,'num_turns'), (QaGenerateInput,'num_qa'),
                   (SeedExpandInput,'seed_words'), (VideoCaptionInput,'fps_sample'),
                   (VideoTemporalInput,'num_segments')]:
    f = cls.model_fields[field]
    has_d = f.default is not U or f.default_factory is not None
    print(f'{cls.__name__}.{field}: has_default={has_d} default={f.default!r}')"

# 2. Confirm headline N2 reproducer (synth_seed_expand with params={}) is closed
& D:\ComfyUI\.ext\python.exe -c "
import sys
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from imdf.skills.synth.synth_seed_expand import seed_expand, SeedExpandInput
from backend.skills import SkillInput
import asyncio
# model_validate({}) must succeed
inst = SeedExpandInput.model_validate({})
print('seed_words default count:', len(inst.seed_words))
# function call with params={} must succeed
out = asyncio.run(seed_expand(SkillInput(prompt='x', params={})))
print('success:', out.success, 'source:', out.metadata.get('source'))"

# 3. Run the new test suite
cd D:\Hermes\生产平台\nanobot-factory
& D:\ComfyUI\.ext\python.exe -m pytest tests/p2_p3_revised/test_synth_defaults.py -v
```

Expected output:
- Step 1: all 7 rows print `has_default=True`
- Step 2: `seed_words default count: 10`, `success: True source: mock`
- Step 3: `23 passed`

## 7. Notes for the verifier

1. **Audit was partially outdated** — at the time of the R2 audit (2026-07-11 01:42),
   6 of the 7 listed fields already had defaults (added in a prior fix that
   wasn't fully reported). Only `seed_words` was actually missing a default.
   This task updates all 7 to use `Field(default=N)` for uniformity and aligns
   defaults to the task spec.

2. **`seed_words` uses `default_factory`, not `Field(default=10)`** — the
   suggested default of `10` is interpreted as "10 seed words" (a 10-element
   list), not the literal integer 10. The factory returns
   `["cat", "dog", "sun", "tree", "house", "car", "book", "water", "fire", "mountain"]`
   so the skill has realistic default input. A standalone test
   `test_seed_words_default_factory_runs` asserts the factory returns 10 items.

3. **Other required fields are intentionally not changed** — the audit listed
   only the 7 fields above. The other truly-required fields in these skills
   (`text`, `topic`, `context`, `video_ref`) are still required by design
   (the skill can't summarize "nothing"). The task hard rules say "Do NOT
   change other field types" — so I did not touch them. Tests use "minimal
   valid params" (the OTHER required fields) to exercise the audit-field
   default path.

4. **`_COVERAGE` matrix size assertion** — `assert len(_COVERAGE) == 7` is
   the drift-guard. Any future worker who adds an 8th audit row to the matrix
   must update the assert (or vice-versa, remove the entry). This prevents
   silent desync between the fix and the test.

5. **No new dependencies** — `Field` is already imported in all 7 files
   via `from pydantic import BaseModel, Field`. `pydantic_core.PydanticUndefined`
   is used in the test for the "default is set" check; this is stdlib-style
   (comes with pydantic v2 which is already a hard dependency).

6. **No semantic regressions for callers** — the only behavior change is the
   default value of 6 fields (`rounds: 1→2`, `num_turns: 4→3`, `max_words:
   100→50`, `fps_sample: 8→1`, `num_segments: 3→4`) per the task spec.
   `num_qa: 5` unchanged. `seed_words` was added (was missing). Callers that
   pass explicit values are unaffected; callers that relied on the implicit
   default would see different mock output (lower fps sample, fewer
   segments, etc.) but the structure of `SkillOutput` is unchanged.

## 8. Time accounting

- File inventory + audit read: 2 min
- Verified 7 files actually needed fixing vs. audit drift: 3 min
- Applied 7 edits: 3 min
- Wrote 23-case test file: 6 min
- Ran tests + verified no regression on existing 68 cases: 2 min
- Wrote report + deliverable + board: 4 min
- **Total: ~20 min** (under the 25 min budget)

— end of report —
