# P9-2.4 — Hindsight 反思系统 三次审查 (CORRECTED)

**Status correction**: Attempt 1 incorrectly attributed Hindsight to `backend/agent/self_evolution.py`. **Hindsight IS a separate module at `backend/services/agent_service/hindsight.py`** (638 LOC). The `self_evolution.py` file exists but is the **performance/self-evolution overlay** system, not Hindsight itself.

**Files**:
| File | LOC | Role |
|---|---:|---|
| `backend/services/agent_service/hindsight.py` | 638 | 4-layer verbatim memory (THE Hindsight) |
| `backend/agent/self_evolution.py` | 658 | Performance tracker + suggestion engine (overlay) |

---

## 1. The 4 Hindsight layers (per hindsight.py docstring)

```
L0 Identity          — SOUL.md / user identity (immutable for a session)
L1 Essential Story   — project-level core info (compressible)
L2 Wing trigger      — light-weight keyword trigger (matches 1 wing)
L3 Full semantic     — vector / full-text search of the verbatim log
```

**Inspired by the Hermes Hindsight design.**

---

## 2. Pluggable backends

```python
class HindsightBackend(str, Enum):
    SQLITE_EXACT = "sqlite_exact"   # default — hermetic, no deps
    PGVECTOR = "pgvector"           # production
    CHROMADB = "chromadb"
    QDRANT = "qdrant"
```

Production-ready: 4 backend options. Default is `sqlite_exact` for tests.

---

## 3. Three design disciplines (Hermes "verbatim" discipline)

### 3.1 Verbatim
"We never summarise / rewrite what the user or the agent said. We always store the raw text."

→ `retain()` method (line 234) stores raw content + metadata, never rewrites

### 3.2 Lazy L1 compression
"L1 entries are generated from L3 by an LLM; the LLM never mutates the source L3 entry, so the verbatim property survives."

→ `_maybe_compress_l1()` (line 369-420) — triggers when L3 log for a source crosses `l1_compress_threshold` (default 20)
→ Calls configured LLM to compress last N items into a 3-5 sentence essential story
→ Stores result in `hindsight_l1_story` table with `parent_id` linking back to source L3 item
→ L3 entry NEVER mutated

### 3.3 Pluggable backends
→ 4 backends selectable via `HindsightConfig.backend`
→ `embedder` and `llm` are optional callables — if None, falls back to LIKE/metadata-only search

---

## 4. Three-pass audit

### 4.1 Verbatim + L1 compression (Pass 1)

**✅ Strengths**:
- Verbatim storage — `retain()` never modifies content (line 234-251)
- `_retain()` always uses the raw content (line 253-290)
- L1 auto-compress triggers only when count crosses threshold AND is multiple (idempotent) — line 386
- L1 stores `parent_id` linking to source L3 — preserves provenance
- LLM errors caught + logged, never break retain (line 397-401)

**⚠ Concerns**:
- L1 summary depends on configured LLM quality — no quality check
- If `l1_compress_threshold=0` → infinite loop (always multiple of 0) — need validation
- L1 summary is one-shot, no incremental update — if LLM improves, summaries don't

### 4.2 Search strategy (Pass 2)

**4-layer priority search** (`search()` line 440-545):

| Layer | Method | Score |
|---|---|---|
| L0_identity | `_layer_substring` (LIKE on content) | 1.0 |
| L2_wing | `trigger_wings` (LIKE on trigger_kw) | 0.85 |
| L1_essential_story | LIKE on summary | 0.7 |
| L3_full | LIKE on content + cosine re-rank (if embedder) | 0.3-1.0 |

**Returns de-duplicated, sorted by score, truncated to k.**

**✅ Strengths**:
- Multi-layer fallback — query never returns empty unless all layers empty
- Layer parameter allows caller to restrict (e.g., `layer="L3_full"`)
- Cosine re-rank when embedder available — automatic graceful degradation
- `since` / `until` time-range filter (line 446-447)

**⚠ Concerns**:
- LIKE substring — "L0 substring on content" catches `user_name="Alice"` AND `mention="Alice"` (false positives)
- L1 search doesn't include embeddings — text-only
- L2 wing search returns wing descriptors, NOT the items under the wing (asymmetric)

### 4.3 Stats + reset (Pass 3)

**stats()** (line 575-588):
```python
{
  "backend": "sqlite_exact",
  "L0_identity": <count>,
  "L1_essential_story": <count>,
  "L3_full": <count>,
  "L1_summaries": <count>,
  "L2_wings": <count>
}
```

**reset()** (line 591-600) — drops all 3 tables for test isolation

**✅ Strengths**:
- Clean stats method — used by MCP `mempalace_wake_up` tool
- reset() is idempotent + atomic (single transaction)

**⚠ Concerns**:
- reset() is "drop everything" — no per-user reset, no per-session reset
- stats() does 5 separate COUNT queries — could be optimized to 1

---

## 5. Integration with MCP

`backend/services/agent_service/mcp/tools.py` exposes 2 Hindsight tools:
- `hindsight_search` (line 141-158) → wraps `HindsightMemory.search(query, layer, k)`
- `hindsight_retain` (line 161-184) → wraps `retain_identity` (L0) or `retain` (L3)

Plus 1 Hindsight resource (`soul://current` → `HindsightMemory.list_identity`) in resources.py

So Hindsight is **fully exposed to external MCP clients** — Claude Code / Cursor can directly read SOUL.md-derived identity + search the verbatim log.

---

## 6. The `self_evolution.py` overlay (separate concern)

`backend/agent/self_evolution.py` (658 LOC) is NOT Hindsight — it's a performance overlay:

### 6.1 What it does
- `PerformanceTracker` (windowed stats: success_rate / duration / tokens)
- `FailureAnalyzer` (regex-based 7-category classification)
- `SuggestionEngine` (6 rule-based improvement suggestions)
- `KnowledgeBase` (success pattern storage)
- `SelfEvolutionSystem` (orchestrator with adaptive params: timeout, max_iter, ctx_threshold)

### 6.2 What it does NOT do
- ❌ Does NOT actually mutate prompts (only suggests)
- ❌ Does NOT A/B test improvements
- ❌ Does NOT integrate with Hindsight (separate from the verbatim memory system)
- ❌ Does NOT auto-execute improvements except timeout + ctx_threshold

### 6.3 Issues (carried over from attempt 1 — verified)
- ❌ FailureAnalyzer regex too loose (`tool timeout` matches both TOOL_TIMEOUT and TOOL_ERROR)
- ❌ KnowledgeBase only learns from success — failures discarded
- ❌ SuggestionEngine hardcoded thresholds — no adaptive improvement
- ❌ `_auto_apply_improvements()` only handles TIMEOUT_TUNING and CONTEXT_MANAGEMENT — others marked pending
- ❌ No health_score delta tracking (only current snapshot)

---

## 7. P0/P1 Fix list

### Hindsight (real)

| # | Issue | Effort |
|---|---|---|
| P0-1 | Validate `l1_compress_threshold > 0` (prevent infinite loop) | 5min |
| P1-1 | Add embeddings to L1 search (cosine over summary embeddings) | 4h |
| P1-2 | Optimize stats() to 1 query (single SELECT with CASE) | 30min |
| P1-3 | Add per-user reset / per-session reset | 1d |
| P1-4 | Add quality check on LLM-generated L1 summary | 1d |

### Self-evolution (overlay)

| # | Issue | Effort |
|---|---|---|
| P0-1 | Add `learn_from_failure` to KnowledgeBase | 2h |
| P0-2 | Disambiguate FailureAnalyzer regex (priority order + multi-pattern penalty) | 1d |
| P1-1 | Integrate with Hindsight (store failures in L3 verbatim) | 1d |
| P1-2 | Add A/B testing framework for auto-applied improvements | 2d |
| P1-3 | Auto-apply PROMPT_OPTIMIZATION via DSPy integration | 1w |

---

## 8. World-class comparison

| Dimension | Hindsight (nanobot) | MemGPT (letta) | LangGraph Memory | Reflexion |
|---|---|---|---|---|
| Verbatim storage | ✅ Yes | ⚠ Optional | ❌ | ❌ |
| Layered model | ✅ 4 layers | ✅ 3 (core/recall/archival) | ⚠ Custom | ❌ |
| L1 auto-compress | ✅ LLM-driven | ✅ Background | ❌ | ❌ Verbal |
| Pluggable backend | ✅ 4 options | ✅ Postgres/SQLite | ⚠ Custom | ❌ |
| Vector search | ✅ Optional | ✅ Always | ✅ Optional | ❌ |
| Cross-session | ⚠ Manual via metadata | ✅ Blocks | ⚠ Custom | ❌ |
| **Score** | **8/10** | **9.5/10** | **7/10** | **7.5/10** |

---

## 9. Score

| Dimension | Score |
|---|---|
| Verbatim discipline | 9/10 |
| Layered model | 9/10 |
| Pluggable backend | 9/10 |
| Search quality | 7/10 (no L1 embeddings, LIKE only) |
| Test coverage | 2/10 (no Hindsight-specific tests) |
| **Total** | **7.2/10** |

---

## 10. Honest correction from attempt 1

Attempt 1 conflated two separate modules:
- ❌ Called `backend/agent/self_evolution.py` "Hindsight"
- ❌ Said "real but rule-based" implying Hindsight was performance-tracker-only

**Reality**:
- `hindsight.py` IS the real Hindsight — verbatim 4-layer memory with LLM-driven compression
- `self_evolution.py` IS a separate performance overlay system

I apologize for the conflation. This report correctly identifies both modules and their distinct roles.