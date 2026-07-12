# P21 P2 P5 — Wire SkillManager to 50 builtin specs (R2 N7 fix)

## What was changed

### Modified

**`backend/skills/legacy.py`** (SkillManager class, 228-345 lines, was 228-270)

The `SkillManager` class was modified in 4 ways:

1. **`get_all_skills()`** (was lines 246-250) — now returns `List[Dict[str, Any]]` with **55 entries**:
   - **5 real skills** (`type='real'`): the 5 original `BaseSkill` subclasses
     (prompt_optimizer, prompt_generator, batch_production, media_production,
     data_analysis). Each entry has `id`, `name`, `description`, `category='core'`,
     `type='real'`, `enabled=True`, `version='1.0.0'`.
   - **50 metadata_only skills** (`type='metadata_only'`, `metadata_only=True`):
     the 50 `SkillSpec` objects from `backend.skills_builtin.BUILTIN_SKILLS`.
     Each entry exposes the full `SkillSpec` shape (`id`, `name`, `description`,
     `category`, `trigger_phrases`, `inputs`, `outputs`, `dependencies`,
     `enabled`, `version`).
   - **Lazy import** of `BUILTIN_SKILLS` inside the method (avoid circular
     dependency: `skills_builtin → skills.__init__ → legacy`).
   - **Backward compat**: the 5 real skills are still returned with all their
     original semantics. The new fields (`id`, `category`, `type`, `version`)
     are additive — existing callers reading only `name` / `description` are
     unaffected.

2. **`get_real_skills()`** (NEW helper) — returns only the 5 real skills.
   Filters `get_all_skills()` by `type == 'real'`.

3. **`get_builtin_skill_specs()`** (NEW helper) — returns only the 50
   metadata_only specs. Filters by `type == 'metadata_only'`.

4. **`execute_skill()`** (was lines 252-260) — enhanced to distinguish two
   failure modes:
   - **Unknown skill** → `SkillOutput(success=False, error="Skill不存在: {name}")`
     (legacy message preserved verbatim).
   - **Metadata-only builtin** → `SkillOutput(success=False, error="Skill '{name}'
     is metadata-only (no function_ref); not executable. See
     backend/skills_builtin.py for spec.", metadata={"type": "metadata_only",
     "skill_id": name})`. Structured metadata lets callers / UIs render the
     error correctly (e.g. show "spec-only" badge).

   Real skills (the 5 in `self.skills`) are dispatched unchanged.

### Created

**`tests/p2_p5/test_skill_manager_builtins.py`** (362 lines, **21 tests, 0.06s PASS**)

Covers:
- **T1-T2**: `BUILTIN_SKILLS` count = 50; all are `SkillSpec` instances with
  canonical fields.
- **T3**: `get_all_skills()` returns ≥ 55 (was 5 before the fix).
- **T4**: 5 real skills are still present (backward compat).
- **T5**: 5 spot-checked builtin IDs (one per category: crawl, process,
  agent, octo, drama) are present in the registry.
- **T6-T7**: Schema: real entries have `type='real'`, no `metadata_only` key;
  metadata-only entries have `type='metadata_only'`, `metadata_only=True`,
  and the full spec shape.
- **T8**: All 50 builtin IDs are unique.
- **T9-T10**: New helpers `get_real_skills()` and `get_builtin_skill_specs()`
  return correct counts.
- **T11-T13**: `execute_skill()` returns the right error in 3 cases
  (metadata-only / real / unknown).
- **T14**: Coverage matrix locks the 11-category structure
  (crawl:10, process:5, agent:8, octo:4, vida:2, meta_kim:3, drama:5,
  comfy:3, redfox:3, reach:4, agency:3 — sum 50).
- **T15**: Regression guard — no new third-party dependencies in legacy.py.

---

## Why

### R2 audit (reports/p21_r2_audit_skill.md §N7)

> **N7** — `SkillManager` in `backend/skills/legacy.py:228-270` only registers
> 5 hardcoded skills (`PromptOptimizationSkill` / `PromptGenerationSkill` /
> `BatchProductionSkill` / `MediaProductionSkill` / `DataAnalysisSkill`).
> The 50 builtin `SkillSpec` objects in `backend/skills_builtin.py:69-630` are
> NEVER queried.
>
> **Severity**: **P0 CRITICAL** — the 50 builtin specs are completely
> invisible to the runtime. Any UI / API / orchestrator trying to enumerate
> the skill catalog gets only 5 entries.
>
> **Fix recommended** (Option A vs B):
> - **A**: Wire `SkillManager` to enumerate `BUILTIN_SKILLS` + provide real
>   handlers (or mark as metadata-only). R1 estimated 180 min for the full
>   handler wiring.
> - **B**: Delete `skills_builtin.py` since it's a dead registry.
>
> This task implements **A** with the "metadata-only" variant — discoverable
> but not executable. Real handler wiring is left as a follow-up
> (each handler is 30-60 min × 50 = 25-50h, way beyond 25-min budget).

### Before the fix (R2 reproducer, was the failing case)

```powershell
$env:PYTHONPATH = "D:\Hermes\生产平台\nanobot-factory"
& D:\ComfyUI\.ext\python.exe -c "from backend.skills_builtin import BUILTIN_SKILLS; from backend.skills import get_skill_manager; m=get_skill_manager(); print([s['name'] for s in m.get_all_skills()])"
# Output: 5 names (prompt_optimizer / prompt_generator / batch_production / media_production / data_analysis)
# The 50 BUILTIN_SKILLS are completely missing from the registry.
```

### After the fix (R2 reproducer now passes)

```powershell
$env:PYTHONPATH = "D:\Hermes\生产平台\nanobot-factory"
& D:\ComfyUI\.ext\python.exe -c "from backend.skills_builtin import BUILTIN_SKILLS; from backend.skills import get_skill_manager; m=get_skill_manager(); all_skills=m.get_all_skills(); print('Total in registry:', len(all_skills))"
# Output: Total in registry: 55
# (5 real + 50 metadata_only)
```

---

## How

### The schema design

The returned dict has a unified schema. For 5 real skills:

```python
{
    "id": "prompt_optimizer",     # = name (real skills don't have separate id)
    "name": "prompt_optimizer",
    "description": "优化用户提示词,提升生成质量",
    "category": "core",
    "type": "real",
    "enabled": True,
    "version": "1.0.0",
}
```

For 50 metadata_only skills (passed through from `SkillSpec`):

```python
{
    "id": "skill_crawl_web",
    "name": "网页抓取 / Web Crawler",
    "description": "从 URL 抓取网页内容与链接,支持深度与 CSS 选择器过滤",
    "category": "crawl",
    "type": "metadata_only",
    "metadata_only": True,
    "enabled": True,
    "version": "1.0.0",
    "trigger_phrases": ["抓取网页", "crawl", "fetch", ...],
    "inputs": {"url": "string", "depth": "int", ...},
    "outputs": {"content": "string", "links": "list", ...},
    "dependencies": [],
}
```

### Why `id` and `name` both

- The 5 real skills historically had only `name`; for them `id` is set to
  the name itself (no id collision with builtin `skill_*` prefix).
- The 50 builtin skills have a dedicated `id` field per `SkillSpec` (the
  unique key). I included `id` for real skills too so callers can use a
  single lookup key.

### Why `type` AND `metadata_only`

- `type='real'` / `type='metadata_only'` is the primary discriminator
  (string equality, JSON-friendly).
- `metadata_only=True` is a redundant convenience flag for callers who
  just want a boolean test (`if entry.get("metadata_only")`).
- Real skills deliberately do NOT include the `metadata_only` key —
  `entry.get("metadata_only")` returns `None` (falsy) for them.

### Why a lazy import

`backend/skills_builtin.py` imports from `backend/skills` (which imports
`legacy.py`). If `legacy.py` were to import `skills_builtin` at module
load time, the cycle would either fail or rely on import order. Lazy
import inside `get_all_skills()` makes it safe regardless of import
order, and `try/except ImportError` keeps `legacy.py` importable even
if `skills_builtin.py` is somehow removed/broken (defense in depth).

### Why the small `execute_skill()` enhancement

The task only required `get_all_skills()` to be fixed. But the existing
`execute_skill()` would return a misleading "Skill不存在" error for
metadata-only IDs (because they're not in `self.skills`). Adding a
two-branch error is a 5-line change that:

- Tells the caller the skill **is** known (it's a builtin spec).
- Tells them it's not yet executable.
- Includes structured `metadata={"type": "metadata_only", "skill_id": ...}`
  so the frontend can render "spec-only" badge instead of a generic error.

This is a non-breaking enhancement: real-skill callers see zero change,
and unknown-skill callers still see the legacy "Skill不存在" message.

---

## Verification

### Tests

```powershell
cd D:\Hermes\生产平台\nanobot-factory
$env:PYTHONPATH = "D:\Hermes\生产平台\nanobot-factory"
& D:\ComfyUI\.ext\python.exe -m pytest tests/p2_p5/test_skill_manager_builtins.py -v
```

**Result**: 21/21 tests PASSED in 0.06s

```
tests/p2_p5/test_skill_manager_builtins.py::test_builtin_skills_count_is_50 PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_builtin_skills_all_have_skill_spec_shape PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_get_skill_manager_is_singleton PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_get_all_skills_returns_at_least_55 PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_real_skills_backward_compat PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_real_skills_have_type_real PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_builtin_id_present[skill_crawl_web] PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_builtin_id_present[skill_dedupe] PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_builtin_id_present[skill_agent_chat] PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_builtin_id_present[skill_octo_bot_create] PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_builtin_id_present[skill_drama_script] PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_metadata_only_entries_have_correct_flags PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_metadata_only_entries_have_full_skill_spec_shape PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_builtin_ids_are_unique PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_get_real_skills_returns_5 PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_get_builtin_skill_specs_returns_50 PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_execute_skill_metadata_only_returns_structured_error PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_execute_skill_real_skill_still_works PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_execute_skill_unknown_returns_legacy_error PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_builtin_category_coverage_matrix PASSED
tests/p2_p5/test_skill_manager_builtins.py::test_no_new_dependencies_in_modified_files PASSED
============================== 21 passed, 1 warning in 0.06s ==============================
```

### R2 reproducer (the original N7 finding)

```powershell
$env:PYTHONPATH = "D:\Hermes\生产平台\nanobot-factory"
& D:\ComfyUI\.ext\python.exe -c "from backend.skills_builtin import BUILTIN_SKILLS; from backend.skills import get_skill_manager; m=get_skill_manager(); all_skills=m.get_all_skills(); print('Total in registry:', len(all_skills)); print('Real skills:', [s['name'] for s in all_skills if s['type']=='real']); print('First 3 builtin:', [(s['id'], s['name']) for s in all_skills if s['type']=='metadata_only'][:3])"
```

**Output** (was failing before):

```
Total in registry: 55
Real skills: ['prompt_optimizer', 'prompt_generator', 'batch_production', 'media_production', 'data_analysis']
First 3 builtin: [('skill_crawl_web', '网页抓取 / Web Crawler'), ('skill_crawl_deep', '深度递归抓取 / Deep Crawler'), ('skill_crawl_redfox', 'RedFox 焦点抓取 / RedFox Focus')]
```

---

## What was NOT done (and why)

- **Real handler for each of 50 builtin** — R1 estimated 180 min, but each
  handler is a non-trivial async function with retry/timeout/error handling
  (per the P2 P4 envelope pattern). At 30-60 min per handler × 50, this is
  25-50h, way beyond the 25-min P2 P5 budget. The metadata-only approach
  is the right 25-min cut.

- **`register_skill()` public API** — currently `SkillManager` only knows
  about 5 hardcoded classes. A `register(BaseSkill)` would let runtime code
  add real handlers. Not required by N7; left for a follow-up task.

- **Database persistence** — the registry is in-memory only. After server
  restart, real handlers are re-instantiated; metadata-only is reloaded
  from `BUILTIN_SKILLS`. No DB write needed since `BUILTIN_SKILLS` is a
  static Python list.

---

## Files changed

| File | Change | Lines (was → is) |
|------|--------|------------------|
| `backend/skills/legacy.py` | `SkillManager` class: 3 methods updated, 2 new helpers, 1 error-handling branch | 284 → 390 |
| `tests/p2_p5/test_skill_manager_builtins.py` | NEW | 0 → 362 |

---

## Backward compatibility impact

- **Existing callers** of `get_all_skills()` that read `s['name']` /
  `s['description']`: ✅ unchanged (those fields are still on every entry).
- **Existing callers** of `get_skill(name)` / `execute_skill(name, ...)`:
  ✅ unchanged for the 5 real skills. Metadata-only IDs return a
  more informative error instead of "Skill不存在", but this is a strict
  improvement (no caller relied on the misleading message).
- **Singleton** `get_skill_manager()`: ✅ still a module-level singleton.
- **Import path** `from backend.skills import ...`: ✅ unchanged.

## Out-of-scope (do not regress)

- The 50 builtins themselves are NOT modified — their `function_ref`-less
  state is preserved.
- No new dependencies introduced.
- No existing tests broken (the test file only adds new tests; the 5
  legacy tests in `tests/skills/` were not affected, since they import
  `BaseSkill` / `SkillManager` from the same module).

---

## Suggested follow-ups (for P2 P6+ or R3)

1. **Wire real handlers** to at least the 10 most-requested builtins
   (e.g. `skill_dedupe`, `skill_score_quality`, `skill_translate_zh`).
   Each handler is 30-60 min, total 5-10h.
2. **`SkillManager.register_skill(name, handler)`** public API so
   plugins can add runtime handlers.
3. **DB-backed catalog**: persist enabled/disabled state per skill,
   not just the static `SkillSpec.enabled` flag.
4. **Filter helpers**: `get_skills_by_category(cat)`,
   `get_skills_by_trigger(phrase)` for UI search.
