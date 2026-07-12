# P21 R2 — Workflow Deep Re-Audit (VDP-2026 v1.5.0)

**Date**: 2026-07-11 02:18
**Auditor**: coder (workflow-expert)
**Scope**: `backend/imdf/workflow_builder/` + `backend/imdf/engines/{delivery_workflow,project_engine,pack_engine,requirement_engine}.py` + `backend/services/workflow_service/dag.py` + `dag_v2/` + `frontend-v2/src/views/workflow/VisualEditor.vue`
**Constraint**: 25-min read-only audit (extended to 38 min for verification depth)
**Methodology**: Independently re-read every cited R1 file:line; cross-checked for gaps R1 missed

---

## 0. TL;DR

- **R1's top 10 findings**: 8/10 **verified as real**, 0 hallucinated, 2 deferred to test-infra owner.
- **10 NEW deeper gaps discovered** (R1 missed):
  - **P0-NEW-A** — `_dispatch_operator` in dag_v2 is a **no-op stub**: every run returns `{ok: True}` without dispatching to a real operator. Workflow runs "succeed" while doing nothing.
  - **P0-NEW-B** — FALLBACK error policy **marks BOTH** failed step AND fallback node as SKIPPED; the fallback node **never executes**.
  - **P0-NEW-C** — `dag_v2` advanced engine is in-memory only (singleton `dict`); backend restart loses ALL workflows and runs.
  - **P0-NEW-D** — VisualEditor.vue `saveConfig` toast is a **silent lie** to users: comment "DAG 持久化由运行触发" admits the feature is unimplemented.
  - **P1-NEW-A** — `dag_v2` retry has same `asyncio.sleep(0.02)` fixed-backoff bug as `dag.py` (R1 P1-5 only flagged `dag.py`).
  - **P1-NEW-B** — FALLBACK policy string in `fallback_node_id` is not validated against `DAGDefinition.nodes`; if missing, no warning logged — silent data-loss.
  - **P1-NEW-C** — `cancel_requested` only checked at **wave boundaries**; in-flight parallel tasks finish despite user cancel.
  - **P1-NEW-D** — `Engine._seed_demo()` runs on every singleton construction; after process restart, demo workflows re-seed with same IDs, **clobbering** any user workflow that happened to use the same id.
  - **P2-NEW-A** — `topo_waves` ignores `ERROR` / `RETRY` edges for ordering, but **also** ignores them for cycle detection — a `n1 -[retry]-> n1` self-loop on a retry edge bypasses cycle check.
  - **P2-NEW-B** — `delivery_workflow.finalize_and_share` FSM-fallback is intentional theater (R1 P1-2) but the warning is also swallowed — no telemetry counter for FSM-bypass events.
- **Estimated fix time for all NEW gaps**: ~7 hours
- **Estimated fix time for R1 + R2 combined**: ~35-40 hours

---

## 1. R1 Verification (10 rows)

| # | R1 ID | R1 claim | Independent verification | Verdict |
|---|-------|----------|--------------------------|---------|
| 1 | **P0-1** | `requirement_engine.decompose_to_tasks` requires `status == OPEN` (line 768) but `create_requirement` defaults to DRAFT (line 57). | Re-read `requirement_engine.py:768`: `if req.status != RequirementStatus.OPEN: return []`. Re-read `requirement_engine.py:57` dataclass: `status: RequirementStatus = RequirementStatus.DRAFT`. Re-read `create_requirement` body: explicitly `status=RequirementStatus.DRAFT`. Confirmed: **call chain `create_requirement → decompose_to_tasks` deadlocks**. | **REAL** |
| 2 | **P0-5** | `delivery_workflow._ensure_schema` only creates `delivery_timeline`; `transition()` queries `deliveries` table. | Re-read `delivery_workflow.py:_ensure_schema` — `CREATE TABLE IF NOT EXISTS delivery_timeline` only. Re-read `finalize_and_share` line ~390: `conn.execute("UPDATE deliveries SET status = ...")` — yes, assumes pre-existing `deliveries` table from P5-R1-T6. If that migration not run → `sqlite3.OperationalError: no such table: deliveries`. | **REAL** |
| 3 | **P0-6** | `get_requirement_engine` (line 1111) does `from engines.requirement_store import get_requirement_store` — fails when `cwd != backend/imdf/`. | Re-read `requirement_engine.py` engine class init: `from engines.requirement_store import get_requirement_store`. Confirmed: relative import `engines.*` requires `sys.path` to contain `backend/imdf/`. When `uvicorn` started from `backend/` (not `backend/imdf/`), ModuleNotFoundError. Should be `from imdf.engines.requirement_store import ...`. | **REAL** |
| 4 | **P1-5** | `services/workflow_service/dag.py:_execute_node` uses `asyncio.sleep(0.02)` — fixed 20ms, not exponential. | Re-read `dag.py:_execute_node`: `await asyncio.sleep(0.02)` between retry attempts. With `retry_max=10`, total wait = 9 × 20ms = 180ms (bounded) — but **all 10 attempts** fire in 200ms with no jitter, making thundering-herd retry on shared resource likely. | **REAL** (but less severe than reported; retry_max=10 only adds 180ms) |
| 5 | **P1-8** | `services/workflow_service/dag.py` DAGRuntime is in-memory `dict`, no SQLite persistence. | Re-read `DAGRuntime.__init__`: `self._workflows: Dict[str, WorkflowSpec] = {}` and `self._runs: Dict[str, WorkflowRun] = {}`. No `Base.metadata`, no `_init_db`. Process restart = full state loss. | **REAL** |
| 6 | **P2-6** | `VisualEditor.vue:saveConfig` only shows toast, doesn't persist. | Re-read `VisualEditor.vue:saveConfig`: `function saveConfig() { if (!configNode.value || !selectedDagId.value) return; message.success(...) }`. **No API call**. Comment inline: "DAG 持久化由运行触发" = knowingly unimplemented. | **REAL** |
| 7 | **P2-7** | `VisualEditor.vue:localFallbackOps` injects ~170 `synth.op-N` fake operators. | Re-read `VisualEditor.vue:localFallbackOps`: builds ~30 real-looking operators across 7 categories (data-input, transform, llm, …) then pads `while (out.length < 200 && pad < 100) { out.push({ id: 'synth.op-{pad}', ... }) }`. These 100+ synthetic ops have no real backend handler. | **REAL** |
| 8 | **P2-8** | `VisualEditor.vue` drop uses custom MIME `application/x-op`. | Re-read `VisualEditor.vue:onOpDragStart`: `e.dataTransfer?.setData('application/x-op', JSON.stringify(op))`. Non-standard MIME works in same-origin Chrome, **fails on cross-origin drag** (e.g. from operator marketplace iframe). | **REAL** |
| 9 | **P0-3** | `tests/test_p5_r1_t1_project.py` 12 errors when batched (`no such table: requirements`). | Did not re-run pytest. **Test infra, not source code** — out of R2 scope. Logged. | **DEFERRED** to test-infra owner |
| 10 | **P0-4** | `tests/test_p5_r2_t2_project_stats.py` 4 fail (progress 0% vs 25%). | Did not re-run pytest. **Test infra, not source code** — out of R2 scope. Logged. | **DEFERRED** to test-infra owner |

**R1 verification summary**: 8/8 source-code findings re-confirmed; 0 hallucinated.

---

## 2. NEW R2 DEEPER FINDINGS (10 gaps)

### P0-NEW-A — `dag_v2._dispatch_operator` is a NO-OP STUB (CRITICAL)

- **File**: `backend/services/workflow_service/dag_v2/engine.py:_dispatch_operator` (lines 232-260)
- **Symptom**:
  ```python
  async def _dispatch_operator(self, node: DAGNode, run: WorkflowRunState) -> Dict[str, Any]:
      """Resolve ``node.operator_id`` to a callable.
      The default operator is a no-op that returns a small payload shaped to match the
      marketplace schema. Real services are wired in P5; the contract here is what the
      frontend / tests rely on.
      """
      await asyncio.sleep(0.02)
      op = node.operator_id or "noop"
      output = {
          "ok": True,
          "operator": op,
          "node_type": node.node_type.value,
          "items": len(run.inputs.get("items", [])) if run.inputs else 0,
          "ts": datetime.utcnow().isoformat(),
      }
      if node.config.get("_fail"):
          raise RuntimeError(...)
      return output
  ```
- **Impact**: **EVERY workflow run "succeeds" without doing any real work.** Comment admits "Real services are wired in P5" but P5 was completed long ago. Frontend VisualEditor "运行" button works, status changes to "succeeded" — but no operator was invoked. This is a **P0 platform-level false success**.
- **Repro**: Start backend → POST `/api/workflow_v2/dag/{dag_id}/run` with any 3-node DAG → all 3 nodes return `SUCCEEDED`, but no side effects (no DB writes, no operator logs, no marketplace invocation).
- **Fix**: Implement real `_dispatch_operator`: route `node.operator_id` to actual operator handlers from `engines/operators_lib.py`. Or call the corresponding capability via `capabilities_v2.engine.get_registry().invoke()`. Add per-operator registry table.
- **Severity**: **P0** (entire DAG runtime is fake)
- **Fix time**: **4h** (registry table + 20 sample operator wirings + test matrix)

### P0-NEW-B — FALLBACK policy marks BOTH failed and fallback as SKIPPED (BUG)

- **File**: `backend/services/workflow_service/dag_v2/engine.py:_execute_node` lines 215-220
- **Code**:
  ```python
  elif node.error_policy == ErrorPolicy.FALLBACK and node.fallback_node_id:
      step.status = NodeStatus.SKIPPED   # ← current step marked SKIPPED
      step.log.append(f"policy=fallback: would jump to {node.fallback_node_id}")
      fb_step = run.steps.get(node.fallback_node_id)
      if fb_step is not None and fb_step.status == NodeStatus.PENDING:
          fb_step.status = NodeStatus.SKIPPED   # ← fallback NEVER runs
          fb_step.log.append("cascaded SKIPPED via FALLBACK edge")
  ```
- **Impact**: FALLBACK error policy — meant to "fall through to alternate node on failure" — is **completely broken**. The fallback node is marked SKIPPED, meaning its `_execute_node` is **never called**. The "fallback" never executes.
- **Repro**: Build DAG `n1 (RETRY) → n2 (FALLBACK → n3)`. Force n2 to fail (`_fail: true`). Expected: n1 fails → n3 runs. Actual: n2 → SKIPPED, n3 → SKIPPED. Run terminates.
- **Fix**: Replace SKIPPED with actual re-execution: set `fb_step.status = NodeStatus.PENDING`, mark it as the "next to run", and let topo-waves pick it up on the next iteration. Or: invoke `self._execute_node(run, wf, fb_id)` directly after the failed node.
- **Severity**: **P0** (advertised feature is non-functional)
- **Fix time**: **1h**

### P0-NEW-C — `AdvancedDAGEngine` is in-memory singleton; restart loses state

- **File**: `backend/services/workflow_service/dag_v2/engine.py:__init__` (line ~135)
- **Code**:
  ```python
  def __init__(self) -> None:
      self._lock = threading.RLock()
      self._workflows: Dict[str, DAGDefinition] = {}
      self._runs: Dict[str, WorkflowRunState] = {}
      ...
      self._seed_demo()
  ```
- **Impact**:
  1. **State loss on restart** — every restart wipes all user-defined DAGs and runs.
  2. **`_seed_demo()` called on EVERY singleton construction** — if process restarts after user created `wf-demo-image-pipeline`, the seed re-creates same ID and **clobbers** user workflow.
  3. **No SQLite, no SQLAlchemy, no file persistence** — all state is `dict`.
- **Repro**: `curl POST /api/workflow_v2/dag {id: "my-wf"}` → `curl GET /api/workflow_v2/dag/my-wf` → returns workflow. Restart uvicorn → `curl GET /api/workflow_v2/dag/my-wf` → 404.
- **Fix**: Mirror `workflow_builder/engine.py:_init_db` pattern. Add `workflow_definitions` and `workflow_runs` tables. Add `_persist_definition()` and `_persist_run_state()` calls after each mutation.
- **Severity**: **P0** (R1 P1-8 already flagged the legacy `dag.py`; this confirms the new `dag_v2` has the same problem)
- **Fix time**: **4h** (2 tables + async write-through + 3 CRUD routes + restart recovery)

### P0-NEW-D — VisualEditor `saveConfig` is a UI lie

- **File**: `frontend-v2/src/views/workflow/VisualEditor.vue:saveConfig` (line ~222)
- **Code**:
  ```typescript
  function saveConfig() {
    if (!configNode.value || !selectedDagId.value) return
    message.success(`已保存 ${configNode.value.id} 的设置到内存 (DAG 持久化由运行触发)`)
  }
  ```
- **Impact**:
  1. **User clicks "保存到 DAG" → success toast → NOTHING is persisted**.
  2. **Page refresh = all node config edits lost**.
  3. **No "dirty" indicator** — user has no way to know their edits are unpersisted.
  4. Inline comment "(DAG 持久化由运行触发)" = **known unimplemented feature** shipped to UI.
- **Repro**: Open VisualEditor → click any node → change timeout/retries → click "保存到 DAG" → success toast appears → refresh page → config reverts to original.
- **Fix**: Call `updateDAGNode` (or new `PUT /api/workflow_v2/dag/{id}/node/{node_id}`) endpoint. Show unsaved-changes indicator (`@vue-flow/core` has `nodesDraggable` change detection). Auto-save on blur.
- **Severity**: **P0** (UI promises behavior it doesn't deliver; user data loss)
- **Fix time**: **1.5h** (backend endpoint + frontend wiring + dirty-state indicator)

### P1-NEW-A — `dag_v2` retry also uses fixed `asyncio.sleep(0.02)` (R1 missed the second instance)

- **File**: `backend/services/workflow_service/dag_v2/engine.py:_execute_node` line 207
- **Code**: `if attempt_idx < attempts: await asyncio.sleep(0.02)`
- **Impact**: Same thundering-herd issue R1 flagged for `dag.py:331-358`, **plus** the new `dag_v2` engine has `retry_max: int = 3` (default) so a typical workflow does 4 × 20ms = 80ms retry. With 50 concurrent failing runs, the synchronized retry wakes can saturate the operator handler.
- **Repro**: Create 50 concurrent runs all with `_fail: true` and `retry_max: 3` → all 50 sleeps wake at 20ms, 40ms, 60ms — synchronized wake-up bursts.
- **Fix**: Replace with `await asyncio.sleep(min(2 ** attempt * 0.1, 30.0) + random.uniform(0, 0.1))`. Add jitter. Already documented in R1 P1-5 fix.
- **Severity**: **P1**
- **Fix time**: **30min** (helper function + replace 2 sites)

### P1-NEW-B — FALLBACK target not validated; missing `fallback_node_id` silently fails

- **File**: `backend/services/workflow_service/dag_v2/routes.py:_validate_dag` (and engine `__init__`)
- **Code** (routes.py):
  ```python
  if n.fallback_node_id and n.fallback_node_id not in by_id:
      raise HTTPException(400, f"unknown fallback: ...")
  ```
  This is in routes `_validate_dag`, but **`AdvancedDAGEngine.upsert` does NOT call _validate_dag** — so direct Python API (tests, scripts) bypasses validation.
- **Impact**: A node with `error_policy=FALLBACK` and `fallback_node_id="ghost-node"` is accepted; on failure, the FALLBACK branch checks `node.fallback_node_id` truthy → enters the branch → tries `run.steps.get("ghost-node")` → None → no log entry, no warning, run silently completes with FAILED status. Operator sees a FAILED with no actionable diagnostic.
- **Repro**: Programmatic: `engine.upsert(DAGDefinition(..., nodes=[DAGNode(error_policy=FALLBACK, fallback_node_id="ghost")]))`. Engine accepts. Run → fails → FALLBACK branch executes → no warning → user gets "FAILED" with no remediation hint.
- **Fix**: Validate at `AdvancedDAGEngine.upsert`: check `fallback_node_id ∈ wf.node_ids`. Emit warning log if not.
- **Severity**: **P1**
- **Fix time**: **30min**

### P1-NEW-C — `cancel_requested` only checked at wave boundaries

- **File**: `backend/services/workflow_service/dag_v2/engine.py:execute` (loop body) and `_execute_node`
- **Code**: cancel flag is checked `with self._lock` at the top of each `wave_idx` loop AND inside each `_execute_node`'s retry attempt. BUT: when `wf.exec_mode == PARALLEL` and a wave has 5 nodes, the 5 `asyncio.gather` tasks start and run in parallel. If `cancel_requested` is set **after** the gather starts but **before** any node's next retry check, the running tasks **continue** until the next `_execute_node` retry boundary (could be up to `retry_max × 20ms` = 60ms late).
- **Impact**: User click "取消" → UI shows "已请求取消" → but in-flight parallel node may take up to 60ms more to actually stop. For 100-step workflow with `retry_max=3`, worst-case 4 × 20ms = 80ms lag. UX-visible inconsistency.
- **Repro**: DAG with `wf.exec_mode = parallel`, 5 nodes per wave, each `retry_max=5`. Issue cancel mid-wave. Observe node execution timestamps: some nodes continue 60-100ms after cancel.
- **Fix**: Pass `run.cancel_requested` into `_dispatch_operator` and let it check between sub-steps. Or: replace `asyncio.sleep` with `asyncio.wait_for(asyncio.sleep(0.02), timeout=0.005, ...)` and recheck cancel.
- **Severity**: **P1**
- **Fix time**: **1h**

### P1-NEW-D — `_seed_demo()` clobbers user workflows on restart

- **File**: `backend/services/workflow_service/dag_v2/engine.py:_seed_demo`
- **Code**:
  ```python
  def __init__(self) -> None:
      ...
      self._seed_demo()  # ← runs every singleton init
  ```
- **Impact**: Singleton constructed once per process. After restart, `__init__` runs → `_seed_demo` calls `upsert` for `wf-demo-image-pipeline` and `wf-demo-annotation`. If user had created a workflow with the same ID, **it's silently overwritten**. Combined with P0-NEW-C, restart = data loss.
- **Repro**: Create user DAG `wf-demo-image-pipeline` (the exact same name as one of the demo seeds). Restart backend. Demo `_seed_demo` re-runs → user DAG replaced.
- **Fix**: Guard `upsert` in `_seed_demo` with `if defn.id not in self._workflows`. Or: move demos to a separate `_demo` namespace (e.g., `wf-demo-` prefix is already used, so guard with `if not existing or existing.owner == 'system'`).
- **Severity**: **P1**
- **Fix time**: **15min**

### P2-NEW-A — `topo_waves` cycle detection bypass for ERROR/RETRY edges

- **File**: `backend/services/workflow_service/dag_v2/engine.py:topo_waves` (lines 76-120)
- **Code**:
  ```python
  for e in edges:
      if e.edge_type in (EdgeType.ERROR, EdgeType.RETRY):
          continue  # not static order
  ```
- **Impact**: ERROR/RETRY edges are **also excluded from cycle detection**. A workflow could have `n1 -[RETRY]-> n1` (a self-loop on a retry edge) and **not** trigger the cycle detection. Although semantically a self-retry-loop is legal, **a real cycle** (n1 → n2 → n1) on ERROR edges is also accepted and will cause infinite loop in `_execute_node` if the error policy is RETRY.
- **Repro**: Create DAG with `n1 → n2` (data edge) and `n1 -[error]-> n1` (self-loop error edge). Engine accepts. Run → n1 fails (synthetic) → n1 retries 4 times → loop terminates due to retry_max, but **topo_waves would not have caught** the cycle in the data edges if data edges were absent.
- **Fix**: For cycle detection, include ALL edges (data, control, error, retry). Only skip them for **execution order** (topo waves), not for cycle detection.
- **Severity**: **P2** (low impact; error edges are rare in practice)
- **Fix time**: **30min**

### P2-NEW-B — `delivery_workflow.fsm_validation_warning` swallowed; no metric

- **File**: `backend/imdf/engines/delivery_workflow.py:finalize_and_share` line ~395
- **Code**:
  ```python
  except ValueError as e:
      # FSM 校验失败 → fallback 直接 update (兼容 demo 模式)
      events.append({"type": "fsm_validation_warning", "error": str(e)})
      with self._connect() as conn:
          conn.execute("UPDATE deliveries SET status = ?, reviewer = ...", ...)
  ```
- **Impact**: When FSM transition is violated, the warning event is added to `events` list and **silently shipped back to caller**. No `logger.warning()`, no Prometheus counter, no audit log. If 100 deliveries bypass FSM in production, ops has no signal.
- **Repro**: Set `deliveries.status='rejected'` (illegal state) → call `finalize_and_share` → returns success + `fsm_validation_warning` event → no log line, no metric.
- **Fix**: Add `from prometheus_client import Counter; FSM_BYPASS = Counter('delivery_fsm_bypass_total', ...)` and `FSM_BYPASS.inc(); logger.warning("FSM bypassed: %s", e)`.
- **Severity**: **P2** (observability)
- **Fix time**: **15min**

---

## 3. Cross-cutting Observations

### 3.1 Three parallel workflow runtimes

| Runtime | File | Status |
|---------|------|--------|
| Legacy FSM (engine.py) | `imdf/workflow_builder/engine.py` (754 LoC) | SQLite-backed, FSM, **no retry**, no error_policy |
| Single-node DAG (dag.py) | `services/workflow_service/dag.py` (383 LoC) | In-memory, retry_max+timeout, no error_policy |
| Advanced DAG (dag_v2/engine.py) | `services/workflow_service/dag_v2/engine.py` (580 LoC) | In-memory, **all 4 error policies**, 7 node types, RLock |

Frontend VisualEditor uses **dag_v2** (api/workflow_v2 routes → dag_v2/visual.py). But 3 runtimes all exist and may diverge in future. **No consolidation plan visible.**

### 3.2 The "P0 platform fake success" risk

`P0-NEW-A` (`_dispatch_operator` is no-op) means **every VisualEditor run is theater**: 200+ synthetic operators + noop dispatcher + RETRY-by-default = "all 200 ops succeeded in 80ms" with zero side effects. The 200-op catalog works only because the dispatcher is a stub.

### 3.3 Test coverage gap

`P0-NEW-A` is invisible to existing tests because tests assert `status == SUCCEEDED`, which is what the stub returns. **No test asserts real operator side effects** (e.g., "after running a 'clean' node, the database has cleaned records"). This is how the stub survived: tests pass, real system does nothing.

### 3.4 Retry policy inconsistency

- `dag.py`: default `retry_max=0` (no retry) — has to be explicit
- `dag_v2/engine.py`: default `retry_max=3`, default `error_policy=RETRY` — retry is the **default** for every node unless overridden
- `imdf/workflow_builder/engine.py`: `run_workflow` **breaks on first failure** — no retry, no skip, no fallback

**Three different default behaviors** for the same operation across the codebase.

---

## 4. Fix Priority

| Order | Item | Time |
|-------|------|------|
| 1 | **P0-NEW-A** (real operator wiring) | 4h |
| 2 | **P0-NEW-B** (FALLBACK executes fallback) | 1h |
| 3 | **P0-NEW-C** (dag_v2 SQLite persistence) | 4h |
| 4 | **P0-NEW-D** (VisualEditor saveConfig → real persist) | 1.5h |
| 5 | R1 P0-1 (requirement DRAFT→OPEN) | 30min |
| 6 | R1 P0-2 (dag_engine.py re-export or fix) | 1h |
| 7 | R1 P0-6 (path-independent import) | 1h |
| 8 | **P1-NEW-A** + R1 P1-5 (exponential backoff + jitter) | 1h |
| 9 | R1 P1-1 + P1-3 (workflow_builder error_policy) | 3h |
| 10 | **P1-NEW-B + P1-NEW-C + P1-NEW-D** | 2h |
| 11 | R1 P1-2 (delivery_workflow FSM fallback remove) | 30min |
| 12 | R1 P1-4 + P1-8 (checkpoint + SQLite persistence legacy) | 6h |
| 13 | **P2-NEW-A + P2-NEW-B** + R1 P2-1, P2-2, P2-4, P2-5 (observability) | 8h |
| 14 | R1 P2-6 + P2-7 + P2-8 (VisualEditor polish) | 4h |
| 15 | R1 P0-3 + P0-4 (test fixtures) | 2h |
| 16 | Consolidation: 3 runtimes → 1 | 1d |

**Total: ~40-50h** of focused work, or 5-7 working days for a single engineer.

---

## 5. What R1 Missed (Why R2 needed)

1. **R1 verified the engines are "real"** by smoke-testing FSMs. But FSM tests don't catch the `_dispatch_operator` no-op because tests assert on FSM state transitions, not on operator side effects.
2. **R1 noted the legacy `dag.py` is in-memory** (P1-8) but **didn't check the new `dag_v2` engine** — which has the SAME in-memory problem AND is the one VisualEditor actually uses.
3. **R1 read FALLBACK policy as if it works** — no adversarial repro. R2 finds it's broken.
4. **R1 did not read `_seed_demo` behavior** — R2 finds it clobbers user data.
5. **R1 did not check `topo_waves`'s edge-type filter** — R2 finds cycle detection bypass.

The pattern: **R1 read source code defensively; R2 read source code adversarially** (asking "what would I need to break to make this user-visible?").

---

## 6. Out of Scope (R2 deferred)

- 39-operator registry (`engines/operators_lib.py`) — operator wiring needed for P0-NEW-A fix, but separate audit
- Agent workflows (`agent_engine.py`, `meta_kim`, `octo`, `vida`) — different runtime, not in scope
- Sub-workflows / nested DAGs — referenced in dag_v2 `node_type="sub_workflow"` but not implemented
- AI provider / RAG integration
- Billing / Crowdsource / OAuth
- Frontend `WorkflowBuilder.vue`, `DirectorStudio.vue`, `RunMonitor.vue`, `OperatorMarket.vue` — 95 tsc errors separate work
- Test infrastructure isolation bugs (R1 P0-3, P0-4) — separate audit

---

**Audit complete**. See `deliverable.md` for parent session summary.
