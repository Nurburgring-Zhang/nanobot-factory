# `filter_quality` — 筛选质量评估引擎

> **Status: DECLARATIVE** — This module is an evaluation/reference engine, **not**
> a runtime filter. It does **not** drop rows, redact text, or block content.
> Use it to measure how well your existing filter pipeline performs against a
> golden set; pair it with a real filter (e.g. `services/cleaning_service/`,
> `services/scoring_service/`) to do the actual filtering.
>
> Source: `backend/imdf/engines/filter_quality.py` (~531 lines, 0 runtime deps)

## Scope

`FilterQualityEngine` answers four questions about a filter pipeline:

| Question | Method |
|---|---|
| "Is my filter accurate on a known-good set?" | `add_golden_item` / `load_golden_set` / `evaluate_on_golden` |
| "Which of two filter variants is better?" | `start_ab_test` / `record_ab_result` / `conclude_ab_test` |
| "How does each filter dimension contribute?" | `multi_dimension_evaluate` |
| "What's a good enough F1 to ship?" | `_quality_rating` / `_industry_benchmark` |

It is pure evaluation: **no I/O**, **no HTTP**, **no LLM calls**, **no DB writes**.
Golden sets live in-memory on the engine instance; persist them yourself if needed.

## Core types

### `FilterMetrics` (dataclass)

```python
@dataclass
class FilterMetrics:
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
```

Derived properties (all return `0.0` on zero denominator, **never raise**):

| Property | Formula | Meaning |
|---|---|---|
| `precision` | `TP / (TP + FP)` | Of items the filter let through, how many should it have? |
| `recall` | `TP / (TP + FN)` | Of items that should pass, how many did the filter let through? |
| `f1` | `2·P·R / (P + R)` | Harmonic mean of precision and recall |
| `accuracy` | `(TP + TN) / total` | Overall agreement |
| `specificity` | `TN / (TN + FP)` | True-negative rate (filter correctly rejects) |

`to_dict()` returns the raw counts + 4-decimal-rounded derived values for JSON
serialization (e.g. when emitting an eval report to `imdf/routes.py`).

### `FilterQualityEngine`

In-memory registry of golden items + A/B tests. One instance per filter pipeline
is typical (lifecycle scoped to the request or to the worker process).

## Golden-set workflow

```python
from imdf.engines.filter_quality import FilterQualityEngine

engine = FilterQualityEngine()

# 1. Build a golden set — items with KNOWN expected outcomes
engine.add_golden_item(
    item={"id": "img-001", "size_kb": 412},
    expected_pass=True,         # this image SHOULD pass your filter
    filter_name="resolution",   # tag for per-filter reporting
)
engine.add_golden_item(
    item={"id": "img-002", "size_kb": 8},
    expected_pass=False,        # this image should be REJECTED
    filter_name="resolution",
)

# 2. Define your actual filter (lives elsewhere)
def my_resolution_filter(item):
    return item.get("size_kb", 0) >= 100

# 3. Evaluate
report = engine.evaluate_on_golden(my_resolution_filter, filter_name="resolution")
```

### `evaluate_on_golden` return shape

```json
{
  "filter_name": "resolution",
  "golden_items_tested": 2,
  "metrics": {"precision": 0.5, "recall": 1.0, "f1": 0.667, ...},
  "errors": [{"index": 1, "item_id": "img-002",
              "expected": "filter", "actual": "pass",
              "error_type": "false_positive"}],
  "error_summary": {"false_positives": 1, "false_negatives": 0},
  "industry_benchmark": {
      "商用数据筛选": {"precision": 0.95, "recall": 0.95, "f1": 0.95},
      "当前表现":     {"precision": 0.5,  "recall": 1.0,  "f1": 0.667}
  },
  "quality_rating": "needs_improvement",
  "status": "complete"
}
```

Notes:
- Errors are capped at the first 20; counts continue beyond that in `error_summary`.
- A filter function returning `bool`, `dict`, or any truthy/falsy is accepted; for
  `dict`, the engine reads `result["pass"]` then `result["keep"]` (default `True`).
- Exceptions inside `filter_func(item)` are logged and treated as `passed=True`
  (fail-open on eval — the **filter itself** is what you want to harden, not this).

### Quality rating thresholds

| F1 | Rating |
|---|---|
| `>= 0.95` | `excellent` |
| `>= 0.85` | `good` |
| `>= 0.75` | `acceptable` |
| `>= 0.60` | `needs_improvement` |
| `<  0.60` | `poor` |

## A/B test workflow

```python
test_id = engine.start_ab_test(
    test_id="exp_2026_q3_resolution_v2",
    filter_a_config={"min_kb": 100, "min_dim": 512},
    filter_b_config={"min_kb": 80,  "min_dim": 512},
    test_items=[{"id": f"img-{i:03d}"} for i in range(100)],
)

# Stream results in as items flow through both filters
for item_id, res_a, res_b in stream_results():
    engine.record_ab_result(test_id, res_a, res_b, item_id,
                            ground_truth=gold[item_id])

report = engine.conclude_ab_test(test_id,
                                 ground_truth=[...])  # optional
```

`conclude_ab_test` returns:

- per-filter metrics (`metrics_a`, `metrics_b`) when `ground_truth` is supplied
- `agreement_rate` / `disagreement_rate` always
- `winner`: `"A"`, `"B"`, `"tie"` (delta < 0.01), or `"unknown"` (no GT)
- human-readable `recommendation` string

If no `ground_truth` is provided, only **pass-rate** differences are reported;
you still get the disagreement rate but not F1 / winner.

## Multi-dimension evaluation

When a pipeline has multiple orthogonal filter dimensions (resolution + NSFW +
language + length + ...), evaluate each independently:

```python
report = FilterQualityEngine.multi_dimension_evaluate(
    filter_results={
        "resolution_check": [True, False, True, ...],
        "nsfw_check":       [True, True,  False, ...],
        "language_check":   [False, True, True, ...],
    },
    ground_truth=[True, True, False, ...],
)
```

The `overall` metric is computed under **AND semantics**: an item passes overall
only if **all** dimensions pass. If you want OR semantics, pre-aggregate your
predictions before calling.

## Boundaries — what this engine does NOT do

- **Not a filter.** It never blocks/rejects/keeps anything in real data flow.
- **No persistence.** Golden set + A/B tests live on the Python instance; the
  process restarts and they're gone. Persist externally (JSON / DB) before
  shutdown if you need them.
- **No concurrency guards.** `_ab_tests` and `_golden_set` are plain dicts/lists.
  If you share an engine instance across threads, wrap calls with a `Lock`.
- **No LLM dependency.** Despite a docstring mention of "LLM-as-Judge", the
  current implementation is purely rule-based; the LLM-as-Judge surface is left
  for a future module so the engine stays hermetic and test-friendly.
- **No HTTP/JSON Schema.** This file does not declare a request/response model;
  the FastAPI layer (`imdf/api/canvas_web.py` or `routes.py`) is responsible for
  converting HTTP payloads to `FilterQualityEngine` calls.

## When to use

- Regression-testing a filter before deploying a config change.
- Comparing two filter configurations on the same golden set.
- Reporting per-dimension quality metrics for an offline training-set QA pass.
- Building a `/admin/filters/evaluate` debug endpoint.

## When NOT to use

- Inline during data ingest — use `services/cleaning_service/` for that.
- On untrusted user input — this engine is an internal QA tool, not a sandbox.
- For production traffic routing — see `services/scoring_service/` instead.
