# P19 v5.5 — AQL Sampling + 4-Strategy Auto-Labeling

**Worker**: coder
**Date**: 2026-07-06
**Spec**: V5 Chapter 8 (FR-8.3) + Chapter 6 (FR-6.3) — Data Quality Layer
**Status**: COMPLETE — 40/40 tests pass

---

## 1. Scope

| Task | Spec | Implementation | Test |
|---|---|---|---|
| **AQL 7 levels** | ISO 2859-1 normal inspection (0.1/0.65/1.0/1.5/2.5/4.0/6.5) | `AQLLevel` enum (7 values) | 21 tests |
| **AQL Table II-A** | (lot_size, aql) -> (sample_size, Ac, Re) | `SAMPLE_TABLE` dict (70 cells = 10 buckets × 7 levels) | covered |
| **AQLSampling** | sample() + inspect() + plan_summary() | `AQLSampling` class | covered |
| **4 strategies** | CLIP / Rule / Active / Consensus | 4 classes + abstract base | 18 tests |
| **Orchestrator** | asyncio.gather + consensus aggregation | `AutoLabelingOrchestrator` | covered |
| **Skill registration** | 2 skills in registry | `aql_inspect` + `auto_label_consensus` | smoke-tested |

## 2. Files Created / Modified

| File | LOC | Purpose |
|---|---|---|
| `backend/imdf/quality/aql_sampling.py` | 184 | AQL sampler + inspector |
| `backend/imdf/labeling/auto_strategy_schemas.py` | 220 | Pydantic v2 schemas (Asset, AQLLevel, InspectionResult, LabelResult, StrategyVote, DefectRecord, SAMPLE_TABLE) |
| `backend/imdf/labeling/auto_strategy.py` | 290 | 4 strategies + orchestrator |
| `backend/imdf/quality/tests/test_aql.py` | 280 | 21 AQL tests |
| `backend/imdf/labeling/tests/test_auto_strategy.py` | 280 | 19 strategy tests (incl. 2 e2e) |
| `backend/imdf/skills/registry.py` | +200 | 2 new SkillSpec + QUALITY_SKILLS list + helpers |
| `__init__.py` files | 4 | package init for `quality`, `labeling`, `quality.tests`, `labeling.tests` |
| **Total** | **~1458** | **40 tests** |

## 3. Architecture

### 3.1 AQL Sampling (FR-8.3)

```
AQLSampling(level, lot_size, seed)
  ├─ _resolve_bucket(lot_size) -> (table_key, clamped)   [10 buckets: 26-50 .. 35001-50000]
  ├─ _lookup_plan(bucket, aql) -> (sample_size, Ac, Re)   [SAMPLE_TABLE: 70 cells]
  ├─ async sample(lot) -> SampledLot                     [Fisher-Yates partial shuffle]
  └─ async inspect(sample, defect_count) -> InspectionResult  [defects <= Ac -> ACCEPT]
```

ISO 2859-1 Table II-A subset (10 lot buckets × 7 AQL levels):

| Lot bucket | Letter | Sample sizes (across 7 AQL levels) |
|---|---|---|
| 26-50    | D | 8, 8, 13, 13, 13, 20, 20 |
| 51-90    | E | 13, 13, 20, 20, 20, 32, 32 |
| 91-150   | F | 13, 20, 32, 32, 32, 32, 50 |
| 151-280  | G | 20, 32, 50, 50, 50, 50, 50 |
| 281-500  | H | 32, 50, 80, 80, 80, 80, 80 |
| 501-1200 | J | 50, 80, 80, 80, 80, 80, 125 |
| 1201-3200 | K | 50, 80, 125, 125, 125, 125, 200 |
| 3201-10000 | L | 80, 125, 200, 200, 200, 200, 315 |
| 10001-35000 | M | 80, 125, 315, 315, 315, 315, 500 |
| 35001-50000 | N | 125, 200, 315, 315, 500, 500, 800 |

Spec required 5 minimum buckets → we ship **10 buckets** (full 26-50000 range).

### 3.2 Auto-Labeling (FR-6.3)

```
AutoLabelingOrchestrator
  ├─ CLIPZeroShotStrategy       (foundation model, mock: hash-deterministic top-3)
  ├─ RuleBasedStrategy          (12 default keyword/regex rules, configurable)
  ├─ ActiveLearningStrategy     (text-length entropy mock -> human review queue)
  └─ ConsensusStrategy          (weighted vote, default threshold 0.8)
       ↑
  asyncio.gather(clip, rule, active)  ── parallel
       ↓
  consensus.label(asset, votes=base_votes)
       ↓
  LabelResult{strategy_votes[4], final_label, needs_human_review}
```

Threshold semantics with 3 base strategies:
* All 3 agree on same category → normalized score = 1.0 ≥ 0.8 → ACCEPT
* 2 of 3 agree → score = 0.667 < 0.8 → routed to human
* Active learning with `uncertainty > 0.7` → always routes to human (independent flag)

## 4. Test Summary (40 tests)

### 4.1 AQL Tests (21 tests in `test_aql.py`)

| # | Test | What it verifies |
|---|---|---|
| 1 | test_bucket_resolution_in_range | 10 lot buckets → correct key |
| 2 | test_bucket_clamps_out_of_range | clamp < 26 and > 50000 |
| 3 | test_lot_50_all_seven_aql_levels | lot=50, all 7 AQLs return correct (n, Ac) |
| 4 | test_lot_150_all_seven_aql_levels | lot=150, all 7 AQLs |
| 5 | test_lot_280_all_seven_aql_levels | lot=280, all 7 AQLs |
| 6 | test_sample_draws_correct_count | sample() draws n assets |
| 7 | test_sample_under_sampled_when_lot_smaller | under-sample flag |
| 8 | test_sample_rejects_empty_lot | ValueError on empty |
| 9 | test_inspect_boundary_at_accept_count | defects == Ac → ACCEPT |
| 10 | test_inspect_boundary_above_accept_count | defects > Ac → REJECT |
| 11 | test_inspect_zero_defects_accepted | 0 defects → ACCEPT |
| 12 | test_inspect_rejects_negative_defects | ValueError on negative |
| 13 | test_plan_summary_contains_all_keys | full plan dict |
| 14 | test_at_least_5_lot_buckets_defined | 10 buckets ≥ 5 |
| 15 | test_e2e_batch_1000_aql_1_0_two_defects_accepted | **spec e2e example #1** |
| 16 | test_e2e_batch_1000_aql_1_0_three_defects_rejected | boundary at Ac+1 |
| 17 | test_defect_rate_computed | 8/80 = 0.1 |
| 18 | test_string_level_coerced | str → AQLLevel |
| 19 | test_invalid_lot_size_raises | lot=0/-5 → ValueError |
| 20 | test_sample_deterministic_with_seed | same seed → same sample |
| 21 | test_lookup_plan_all_buckets_and_levels | full 70-cell coverage |

### 4.2 Auto-Strategy Tests (19 tests in `test_auto_strategy.py`)

| # | Test | Strategy |
|---|---|---|
| 1 | test_clip_returns_deterministic_top_3 | CLIP |
| 2 | test_clip_confidence_in_valid_range | CLIP |
| 3 | test_rule_animal_keyword_match | Rule |
| 4 | test_rule_person_keyword_match | Rule |
| 5 | test_rule_no_match_routes_to_other | Rule |
| 6 | test_rule_custom_rules | Rule |
| 7 | test_active_learning_high_uncertainty_routes_to_human | Active |
| 8 | test_active_learning_low_uncertainty_no_review | Active |
| 9 | test_active_learning_invalid_threshold_raises | Active |
| 10 | test_consensus_combines_three_votes | Consensus |
| 11 | test_consensus_threshold_0_8_requires_all_agree | Consensus |
| 12 | test_consensus_empty_votes_routes_to_human | Consensus |
| 13 | test_orchestrator_returns_complete_label_result | Orchestrator |
| 14 | test_orchestrator_label_batch_parallel | Orchestrator |
| 15 | test_e2e_1000_assets_some_routed_to_human_review | Orchestrator e2e |
| 16 | test_e2e_aligned_captions_high_auto_label_rate | Orchestrator e2e |
| 17 | test_all_strategies_return_valid_confidence | All |
| 18 | test_strategy_names | All |
| 19 | test_consensus_invalid_threshold_raises | Consensus |

## 5. End-to-End Examples (from spec)

### Example 1: AQL inspect on 1000-image lot

```
sampler = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=1000, seed=42)
sample  = await sampler.sample(lot_1000)        # draws 80 assets (bucket J, AQL 1.0)
result  = await sampler.inspect(sample, 2)      # 2 defects ≤ Ac=2

# Plan: sample_size=80, accept_count=2, reject_count=3, bucket=1200
# Decision: ACCEPT
# Rationale: "defects 2 <= Ac 2 - lot accepted"
```

Smoke-tested live: `decision=accept, plan={sample_size:80, accept_count:2, ...}`.

### Example 2: Auto-label 1000 assets with 4 strategies

```
orch = AutoLabelingOrchestrator(
    consensus=ConsensusStrategy(consensus_threshold=0.8),
    active=ActiveLearningStrategy(uncertainty_threshold=0.7),
)
results = await orch.label_batch(assets_1000)
# Each result: LabelResult{strategy_votes[4], final_label, confidence,
#                            uncertainty, needs_human_review}
```

With mixed data (250 long-caption / 750 short-caption):
* All 250 long → high uncertainty → routed to human review via active learning
* Remaining 750 → pass active; consensus at 0.8 requires 3/3 agreement which is
  rare with hash-based CLIP mock; majority routed to human review

For real production: swap CLIP mock for actual `transformers.CLIPModel` and the
consensus agreement rate will track real inter-strategy correlation.

## 6. Skill Registration

Two new skills added to `backend/imdf/skills/registry.py`:

| skill_id | category | function | version |
|---|---|---|---|
| `aql_inspect` | quality | `_run_aql_inspect` | 5.5.0 |
| `auto_label_consensus` | labeling | `_run_auto_label_consensus` | 5.5.0 |

Both expose typed inputs_schema + outputs_schema and are queryable via:
```python
from imdf.skills.registry import (
    QUALITY_SKILLS, list_quality_skills, get_quality_skill,
)
assert len(QUALITY_SKILLS) == 2
aql = get_quality_skill("aql_inspect")
label = get_quality_skill("auto_label_consensus")
```

## 7. Verification Command

```powershell
D:\ComfyUI\.ext\python.exe -m pytest `
    backend/imdf/quality/tests/test_aql.py `
    backend/imdf/labeling/tests/test_auto_strategy.py `
    -v --tb=short
```

Result:
```
==================== 40 passed, 1 warning in 0.37s ====================
```

(Lone warning: `Unknown config option: timeout` — pre-existing pytest.ini issue,
unrelated to this work.)

## 8. Notes for Verifier

* All async code is properly `await`-able and runnable via `asyncio.run` (used
  in tests and skill entry points).
* Pydantic v2 syntax throughout: `model_config = ConfigDict(extra="allow")`,
  `Field(default_factory=...)`, no `class Config`.
* AQL Table II-A values are the canonical ISO 2859-1 single-sampling normal
  inspection numbers (Ac/Re at the AQL operating point). For reduced/tightened
  inspection (not required by spec), the `AQLSampling` class would need an
  `inspection_level` parameter — out of scope for FR-8.3.
* The CLIP / ActiveLearning strategies use deterministic mock logic (SHA256
  hash of asset_id + caption) to avoid GPU dependencies in CI. Real production
  deployment swaps in `transformers.CLIPModel` and `transformers.Blip2ForConditionalGeneration`.
* `SAMPLE_TABLE` exposes the full 70-cell lookup; for production auditing we
  recommend pinning it to a SHA-verified JSON snapshot.