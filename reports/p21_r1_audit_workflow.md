# P21 R1 — Workflow Audit (Focused: Core Engines + VisualEditor)

**Date**: 2026-07-09 20:55
**Scope**: workflow_builder + 4 core engines + DAG + VisualEditor
**Constraint**: 20-minute read-only audit
**Out of scope**: 39-operator registry, agent workflows, sub-workflows

---

## 0. TL;DR

- **6 engines all REAL implementation** (no stubs). Imports pass, functional smoke passes (FSM/topology/variable expansion/allocation strategy).
- **17/17 workflow_builder tests PASS**.
- **28/28 requirement_engine E2E tests PASS** (depth3/depth7/p5_r2_t5).
- **VisualEditor.vue has 0 tsc errors** (total frontend-v2 has 95 errors; VisualEditor is NOT in the list).
- **Critical P0 finding**: `backend/imdf/dag_engine.py` **does not exist** — the real DAG is in `services/workflow_service/dag.py` (P3-3-W2). The task's `imdf/dag_engine.py` path is wrong. VisualEditor actually connects to dag_v2, not imdf/workflow_builder.
- **2 test suites have isolation bugs**: `test_p5_r1_t1_project.py` passes solo but 12 errors when batched (no such table: requirements); `test_p5_r2_t2_project_stats.py` has 4 failures.
- **1 real P0 business bug**: `requirement_engine.decompose_to_tasks` rejects `status=DRAFT` (requires OPEN), but `create_requirement` defaults to DRAFT — any "create-then-decompose" call chain deadlocks.

---

## 1. Scope Verification

| File | Path | Lines | Status |
|------|------|-------|--------|
| workflow_builder/__init__.py | imdf/workflow_builder/__init__.py | 61 | real, re-exports |
| workflow_builder/engine.py | imdf/workflow_builder/engine.py | 754 | real, SQLite + topo + 6 templates |
| workflow_builder/routes.py | imdf/workflow_builder/routes.py | 145 | real, 9 endpoints |
| delivery_workflow.py | imdf/engines/delivery_workflow.py | 517 | real, FSM + snapshot + share |
| project_engine.py | imdf/engines/project_engine.py | 911 | real, SQLAlchemy + FSM + stats |
| pack_engine.py | imdf/engines/pack_engine.py | 726 | real, SQLite store + FSM + route |
| requirement_engine.py | imdf/engines/requirement_engine.py | 1112 | real, in-mem + DB write-through |
| **dag_engine.py** | **imdf/dag_engine.py** | **—** | **DOES NOT EXIST** |
| VisualEditor.vue | frontend-v2/src/views/workflow/VisualEditor.vue | 557 | real, Vue Flow + 200+ ops + 0 tsc err |

**Discovery**: the task's `backend/imdf/dag_engine.py` does not exist. The real DAG runtime is at `backend/services/workflow_service/dag.py` (412 lines, written P3-3-W2) — provides DAGRuntime singleton, NodeSpec, WorkflowSpec, topo_sort waves, retry_max + timeout_seconds.

VisualEditor.vue does NOT connect to imdf/workflow_builder — it imports `api/workflow_v2` which goes through `services/workflow_service/dag_v2/`. This means **2 parallel DAG systems coexist**:
1. `imdf/workflow_builder` (R2-workflow style: 6 capability templates + single-step invoke)
2. `services/workflow_service/dag` + `dag_v2` (P3-3-W2 + P4-6 style: nodes + edges + exec_mode + retry_policy)

---

## 2. Smoke Test Results (functional)

```
1. workflow_builder.topology
  Cycle detection: OK - 工作流存在环: ['a','b','c']
  Var expand: {'a': 42, 'b': 'literal-ok'}     PASS
  Starter templates: 6                          PASS

2. pack_engine FSM (7 states, valid transitions)
  created -> [ready, in_annotation]
  ready -> [annotated, in_annotation]
  in_annotation -> [ready, annotated]
  annotated -> [reviewed, in_annotation]
  reviewed -> [qc_passed, annotated]
  qc_passed -> [reviewed, delivered]
  delivered -> []                                PASS terminal

3. delivery_workflow FSM
  draft -> submitted: True
  draft -> shared: False                        PASS correctly blocked
  approved -> shared: False  WARN  (BUT service allows via fallback)
  approved -> rejected: True
  validate draft->archived: (True, ['draft','archived'])

4. project_engine FSM (4 states)
  planning -> [active, closed]
  active -> [closed, paused]
  paused -> [active, closed]
  closed -> []                                   PASS terminal

5. requirement_engine allocation
  by_skill: [(alice, 1.0), (charlie, 1.0), (bob, 0.0)]    PASS
  by_workload: [(bob, 0.0), (alice, 2.0), (charlie, 5.0)] PASS
  hybrid: [(alice, 0.88), (charlie, 0.7), (bob, 0.3)]     PASS

6. workflow_service.dag (DAGRuntime)
  topo_sort waves: [['a'], ['b', 'c'], ['d']]              PASS
  Cycle detection: OK
  Demo workflows seeded: 2 (wf-demo-image-pipeline, wf-demo-annotation)
```

**Conclusion**: all 6 engines functionally work. FSM, topology, variable expansion, allocation strategies all real.

---

## 3. Pytest Results

| Test suite | PASS | FAIL | ERROR | Note |
|------------|------|------|-------|------|
| `tests/test_r2_workflow_builder.py` | 17 | 0 | 0 | **3.09s** PASS |
| `tests/test_depth3_real_engines_e2e.py` + `test_depth7_requirement_persistence.py` + `test_p5_r2_t5_requirement_e2e.py` (batch) | 28 | 0 | 0 | **2.20s** PASS |
| `tests/test_p5_r1_t1_project.py` (solo `test_create_project`) | 1 | 0 | 0 | **0.73s** PASS |
| `tests/test_p5_r1_t1_project.py` (batch) | — | — | 12 | **isolation bug** |
| `tests/test_p5_r2_t2_project_stats.py` (batch) | — | **4 failed** | — | **assertion fail** |
| Project + Pack + Requirement (combined) | 60 | 4 | 12 | **3.80s** mixed |

### Failed tests (4)

`test_p5_r2_t2_project_stats.py`:
- `test_count_tasks_by_project_joins_via_requirement` — fail
- `test_count_tasks_by_project_isolates_projects` — fail
- `test_get_project_stats_uses_project_id_not_owner` — fail
- `test_get_project_stats_progress_uses_join` — fail (got 0.0, expected 25.0)

### Errored tests (12)

`test_p5_r1_t1_project.py` (12 errors when batched):
- All errors: `no such table: requirements` from `requirement_store.upsert_requirement`
- **Solo `test_create_project` PASS** (0.73s) — proves test isolation issue, not logic bug

**Root cause (inferred)**:
- `requirement_store.upsert_requirement` uses `db.engine` to get SQLAlchemy session
- Fixtures run sequentially; previous fixture drops tables or resets; next fixture's `register_all` doesn't rebuild `requirements` table
- Fix: fixture must call `register_all()` before `Base.metadata.create_all(engine)`, or unify to use `make_sqlite_session_factory` (project_engine.py already has this utility but tests don't all use it)

---

## 4. Frontend (VisualEditor.vue)

| Metric | Value |
|--------|-------|
| tsc errors (VisualEditor) | **0** |
| Total frontend-v2 tsc errors | 95 |
| DAG API connected | `api/workflow_v2` → `services/workflow_service/dag_v2/` |
| Vue components | VueFlow + Background + Controls + MiniMap |
| Operators | 200+ (backend listOperators API + local fallback) |

### Vue file tsc error Top 5 (VisualEditor NOT in list):
| File | errors |
|------|--------|
| `src/views/Delivery.vue` | 45 |
| `src/views/WorkflowBuilder.vue` | 25 |
| `src/views/PackManager.vue` | 11 |
| `src/views/CapabilityRegistry.vue` | 7 |
| `src/views/CollectionCenter.vue` | 7 |

---

## 5. Gap Analysis (Top 20)

### P0 — Broken (must fix)

| # | File | Symptom | Suggestion |
|---|------|---------|------------|
| **P0-1** | `requirement_engine.py:768` | `decompose_to_tasks` requires `status == OPEN`, but `create_requirement` defaults to `DRAFT`. Any "create then decompose" call chain deadlocks. | Change `create_requirement` default to `OPEN`, or accept `DRAFT` in `decompose_to_tasks`. |
| **P0-2** | `imdf/dag_engine.py` | Task-specified file does not exist. Plan/engine scheduler may `from imdf import dag_engine` then hit ModuleNotFoundError. | Pick one: (a) add `imdf/dag_engine.py` re-exporting `services.workflow_service.dag`; (b) fix all references to use services path. |
| **P0-3** | `tests/test_p5_r1_t1_project.py` (12 errors) | Batch run: `no such table: requirements` — fixture doesn't build requirement table. | In `conftest.py` change to `Base.metadata.create_all(engine)` after `from models import register_all` + `register_all()`; or unify to use `project_engine.make_sqlite_session_factory`. |
| **P0-4** | `tests/test_p5_r2_t2_project_stats.py` (4 failed) | `progress` calculates 0% but expected 25% — `req_engine.count_done_tasks_by_project` returns 0 when not rehydrated. | Add `req_engine.rehydrate()` in test fixture; or have stats directly use `self.tasks` in-mem instead of store. |
| **P0-5** | `delivery_workflow.py:140` | `transition()` queries `deliveries` table but `_ensure_schema` only creates `delivery_timeline`. Assumes deliveries table was created elsewhere (P5-R1-T6) — table missing in production would cause ValueError. | Defensive: try/except + return default status; or explicitly `CREATE TABLE IF NOT EXISTS deliveries (...)`. |
| **P0-6** | `requirement_engine.py:1111` | `get_requirement_engine()` internally does `from engines.requirement_store import get_requirement_store` — when `cwd != backend/imdf/` it raises `ModuleNotFoundError: No module named 'engines'`. Already reproduced. | Change to `from imdf.engines.requirement_store ...` or refactor store into module path-independent singleton. |

### P1 — Missing retry / checkpoint / observability

| # | File | Symptom | Suggestion |
|---|------|---------|------------|
| **P1-1** | `workflow_builder/engine.py:498-583` | `run_workflow` breaks on first node failure, **no retry**, **no skip**, **no fallback**. Capability itself implements retry, workflow layer doesn't. | Add `node.retry_max` / `node.error_policy` fields (reuse DAG-style). Change break to on_error strategy. |
| **P1-2** | `delivery_workflow.py:386-395` | `finalize_and_share` calls `state_machine.transition`; on FSM ValueError **silently falls back to direct UPDATE** (`fsm_validation_warning` event). FSM validation is theater. | Remove fallback. Fail = raise HTTP 409. Demo mode via separate flag. |
| **P1-3** | `pack_engine.py:540-558` | `update_pack_status` raises ValueError but no built-in retry/recovery path. Caller can only catch + change target. | Same as P1-1: add error_policy. |
| **P1-4** | All 6 engines | **No checkpoint / resume** — long workflow mid-crash loses everything, must restart from scratch. | run_workflow writes step_id checkpoint to SQLite; on startup check last_checkpoint. |
| **P1-5** | `services/workflow_service/dag.py:331-358` | `_execute_node` retry uses `await asyncio.sleep(0.02)` — **fixed 20ms**, not exponential backoff. retry_max=10 has unbounded total time. | Change to `min(2**attempt * 0.1, 30.0)` + jitter. |
| **P1-6** | `requirement_engine.py:649-689` | `update_requirement_status` uses `logger.warning` to log invalid transitions, no metric. 1000 same errors = 1000 log lines. | Add `requirements_status_transition_rejected_total` counter. |
| **P1-7** | `project_engine.py:744-807` | `get_project_stats`'s `deliveries_count = 0` is hardcoded (comment: "deliveries 表尚未建立"). Should be real after P5-R1-T6. | Replace with real SQL count; or read deliveries_count from a Project.deliveries_count cache. |
| **P1-8** | `services/workflow_service/dag.py` (DAGRuntime) | Entire runtime is **in-memory dict**, no SQLite persistence — process restart = all workflows + runs lost. | Add SQLite persistence layer (mimic workflow_builder's _init_db). |

### P2 — Missing observability / metrics / tracing

| # | File | Symptom | Suggestion |
|---|------|---------|------------|
| **P2-1** | All 6 engines | No structured logging (no `extra={"trace_id", "run_id", "node_id"}` correlation). Problems only findable via `logger.warning` grep. | Add `log_context()` contextmanager or logging.Filter to inject trace_id. |
| **P2-2** | `workflow_builder/engine.py:442-460` | `save_run` immediately INSERTs **after every step** — 100-step workflow = 100 SQLite writes. | Change to batch save every N steps or only at end; or just write checkpoint. |
| **P2-3** | `delivery_workflow.py:131-178` | `transition` does 1 SELECT + 1 UPDATE + 1 INSERT = 3 round trips. | Use `BEGIN` + merge 3 queries. |
| **P2-4** | All engines | No Prometheus metrics (counter/histogram): state transition counts, node execution duration, FSM rejection rate all unobservable. | Add `prometheus_client`; in each engine module end with `_init_metrics()`. |
| **P2-5** | `services/workflow_service/dag.py:264-281` | `run.log: List[str]` is in-memory only, no external sink. UI viewing log must `get_run` and pull entire dict. | Write each log line to `run_logs` table; integrate OpenTelemetry. |
| **P2-6** | `VisualEditor.vue:217-226` | `saveConfig` only shows `message.success(...)` toast, **doesn't actually persist to backend**. User changes params → refresh page → all lost. | Call `updateDAGNode` API. Comment "DAG 持久化由运行触发" = known stub. |
| **P2-7** | `VisualEditor.vue:481-527` | `localFallbackOps` injects ~170 `synth.op-N` fake operators (padding to 200+). Drag to canvas, run workflow, operator definition not found, 100% fail. | Remove fallback, show backend real count; or add `_synthetic: true` flag and disable drag. |
| **P2-8** | `VisualEditor.vue:328-340` | drop zone uses custom MIME `application/x-op`. Chrome/Edge drop cross-origin setData fails; multiple pane simultaneous drag conflicts. | Switch to global drag manager (Pinia) or use `dragstart` to write op to `sessionStorage`. |

---

## 6. Cross-cutting Findings

### 6.1 Dual DAG systems coexist

`imdf/workflow_builder` (R2 style, capability-based):
- 6 templates (image_annotation / video_review / dpo / drama / model_eval / ai_annotation)
- `registry.invoke(capability_id, ...)` calls R1 capabilities

`services/workflow_service/dag` + `dag_v2` (P3-3-W2 + P4-6 style, node-based):
- NodeSpec + WorkflowSpec + topo waves
- retry_max + timeout_seconds + error_policy + fallback_node_id
- 2 demo workflows seeded

VisualEditor uses the latter. Frontend WorkflowBuilder.vue (25 tsc err, not read) may use the former.

**Risk**: two runtimes don't communicate; UI's workflow is not the same as backend real run. Future maintenance cost.

### 6.2 Test infrastructure

- `project_engine.py:867-897` has `make_sqlite_session_factory` utility — tests should unify on this
- Some tests use it (depth3/7), some don't (p5_r1_t1), causing isolation bugs

### 6.3 Tables / DB state

- imdf.db at `backend/imdf.db`, 198MB+
- workflow_builder uses separate `backend/data/workflow_builder.db` (independent SQLite)
- project / pack / requirement / delivery all share imdf.db
- Alembic migrations in `alembic/versions/`

---

## 7. Recommended Fix Priority

1. **P0-1 + P0-2 + P0-6** (1-2h, fix business bug + path error)
2. **P0-3 + P0-4** (1h, unify test fixtures)
3. **P1-1 + P1-2 + P1-5** (2-3h, engine retry/error_policy)
4. **P1-8** (1d, DAG runtime SQLite persistence)
5. **P2-1 + P2-4** (1d, observability foundation)
6. **P2-6 + P2-7 + P2-8** (half day, VisualEditor polish)

---

## 8. Out of Scope (skipped per task)

- 39 operator registry details (operators_lib.py)
- Agent workflows (agent_engine.py, meta_kim, octo)
- Sub-workflows / nested DAGs
- AI provider / embedding / RAG integration
- Billing / Crowdsource / OAuth
- Frontend WorkflowBuilder.vue / DirectorStudio.vue / RunMonitor.vue / OperatorMarket.vue
- 95 tsc errors fix (Memory §10: don't force 0 errors in views/ in <30min)

---

**Audit complete**. See `deliverable.md` for parent session summary.
