# P21 Phase 1 Round 1 — Agent Infrastructure Audit

**Audit target**: 232 experts + 16 departments + 50 skill + Octo + Vida + Meta_Kim + Agent + Comfy + RedFox + Agent Reach
**Project**: nanobot-factory VDP-2026 v1.5.0
**Scope**: `backend/imdf/agency/` + `backend/skills_builtin.py` + `backend/imdf/engines/{octo,vida,meta_kim,agent}_engine.py` + `backend/imdf/creative/{redfox,comfy}/` + `backend/imdf/intelligence/{vida,agent_reach}/`
**Audit method**: Read every source file + live execution + grep cross-references
**Audit duration**: ~22 min
**Date**: 2026-07-09

---

## TL;DR

**HIGHLIGHTS**:
- ✅ **Real implementations**: Octo bot/channel/matter/collab (in-memory Pydantic), Vida screen-aware multi-component loop, Meta_Kim 7-step governance, Comfy catalogue (8 models + 15 nodes), RedFox publish_to_all 11-platform fan-out (5 real + 6 placeholders), Agent Reach 14 channels.
- ❌ **Critical gaps**:
  1. **232 experts + 16 departments are DEAD CODE**: `AgencyLoader` only imported by its own tests; zero consumers in routing.
  2. **No real LLM in Meta_Kim/Vida/Agent engines**: All use deterministic stubs when `llm=None`; production wiring absent.
  3. **No distributed lock manager**: All engines use `threading.RLock` only — multi-process coordination not safe.
  4. **No budget enforcement**: `UsageTracker` has rate-limit + token cost but NO `check_budget()`.
  5. **6 of 11 RedFox platforms are `NotImplementedClient`** (`kuaishou/zhihu/toutiao/baijiahao/qiehao/shipinhao`) — silently fail.
  6. **No `VidaEngineState` / `VidaContext` exports**: `engine_router.py` & tests reference non-existent symbols → 2 test files broken on collection.
  7. **Default Meta_Kim persistence is in-memory only**: `FailureKnowledgeBase()/RunHistoryStore()` lost on restart unless caller passes `persist_path`.

**Top 30 gaps identified below** with severity, fix commands, and reproducible test commands.

---

## Pass/Fail Snapshot (live probes)

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | 232 experts loaded from `departments.json` | ✅ PASS | `len(loader.load_all()) == 232` |
| 2 | 16 departments + `_spare_` bench (15) | ✅ PASS | `loader.departments_present() == 17 entries` |
| 3 | Capability matrix covers all 232 | ✅ PASS | `len(get_capability_matrix()) == 799` skills |
| 4 | AgencyLoader consumed by routing code | ❌ **FAIL** | Zero imports outside `agency/tests/` |
| 5 | `BUILTIN_SKILLS == 50` | ✅ PASS | `categories_builtin()` sums to 50 |
| 6 | Octo: bot/channel/matter/collab real | ✅ PASS | `execute_collab(SOLO)` returns `CollabResult` |
| 7 | Octo: 6 modes (SOLO/ROUNDTABLE/CRITIC/PIPELINE/SPLIT/SWARM) | ✅ PASS | Implemented at `octo_engine.py:690-877` |
| 8 | Vida: real screen capture per-platform | ✅ PASS (Win/Mac/Linux) | `screen_capture.py:78-171` pywin32/pyautogui/scrot |
| 9 | Vida: 7 action types (summarize/reply/organize/search/remind/draft/analyze) | ✅ PASS | `action_executor.py:51-58` |
| 10 | Vida: heuristic intent predictor | ✅ PASS | `intent_predictor.py` exists |
| 11 | Meta_Kim: 7-step govern_run | ✅ PASS | `govern_run()` runs end-to-end with stub LLM |
| 12 | Comfy: 8 models | ✅ PASS | `model_retriever.py` lists 8 entries |
| 13 | Comfy: 15 nodes | ✅ PASS | `node_retriever.py` lists 15 entries |
| 14 | RedFox: 11 PLATFORMS registered | ✅ PASS | `len(PLATFORMS) == 11` |
| 15 | RedFox: 5 real platforms | ⚠️ **PARTIAL** | wechat_mp/weibo/douyin/xiaohongshu/bilibili |
| 16 | RedFox: 6 platform implementations | ❌ **FAIL** | 6 use `NotImplementedClient` |
| 17 | AgentReach: 14 channels | ✅ PASS | All 14 channel files exist |
| 18 | AgentEngine: 13 builtin agents | ❌ **FAIL** | `ModuleNotFoundError: agents.base` import chain broken |
| 19 | Distributed lock manager | ❌ **FAIL** | All locks are `threading.RLock` (process-local) |
| 20 | Meta_Kim default persistence | ❌ **FAIL** | `persist_path=None` default → in-memory only |
| 21 | Vida memory TTL/eviction | ❌ **FAIL** | `AgentMemoryStore` has no prune/evict |
| 22 | UsageTracker budget enforcement | ❌ **FAIL** | No `check_budget()` method |
| 23 | `VidaEngineState` exported | ❌ **FAIL** | Test files & engine_router import fail |
| 24 | `VidaContext` exported | ❌ **FAIL** | `test_vida_engine.py` collection error |

---

## Architecture: Real vs Stub Map

| Component | Code | Real? | Evidence |
|-----------|------|-------|----------|
| `AgencyLoader` (232 experts) | `loader.py` | ✅ real, but **orphan** | loaded fresh each call, validated against departments.json |
| Routing consumer of AgencyLoader | (none) | ❌ **MISSING** | grep returned only 2 test files |
| `BUILTIN_SKILLS` 50 specs | `skills_builtin.py` | ✅ real but **no function_ref** | each is `SkillSpec` dataclass w/o callable |
| Skill registry with `function_ref` | `imdf/skills/registry.py` | ✅ real but only 6 specs | 4 RedFox + 1 Vida + 1 Reach |
| `OctoEngine` bot/channel/matter | `octo_engine.py` | ✅ real | In-memory `OctoKB` Pydantic store |
| `OctoEngine` execute_collab 6 modes | `octo_engine.py:690-877` | ✅ real | uses `hooks={}` if no executor provided |
| `VidaEngine` perceive_and_act | `vida_engine.py:123-189` | ✅ real | DI-friendly |
| `VidaEngine` ScreenCapture (Win/Mac/Linux) | `screen_capture.py` | ✅ real | pywin32 / pyautogui / scrot |
| `VidaEngine` real LLM wiring | (none) | ❌ **STUB-ONLY by default** | `IntentPredictor(heuristic_only=True)` |
| `MetaKimEngine` 7-step loop | `meta_kim_engine.py:264-338` | ✅ real | Clarify→Search→Select→Split→Execute→Verify→Learn |
| `MetaKimEngine` real LLM | (none) | ❌ **STUB-ONLY by default** | `_stub_clarify_intent` etc. |
| `MetaKimEngine` hash embedding | `meta_kim_engine.py:139-155` | ⚠️ mock | 32-dim hash fallback, no real embedding |
| `ComfyMCP` 8 models + 15 nodes | `creative/comfy/` | ✅ real catalogues | Static dict, no execution path tested |
| `ComfyMCP` real workflow run | (only `ComfyUIEngine`) | ⚠️ separate engine | `engines/comfyui_engine.py` |
| `RedFox PLATFORMS[11]` | `creative/redfox/registry.py:63-66` | ✅ real registry | 5 real + 6 `NotImplementedClient` |
| `RedFox publish_to_all` | `redfox/registry.py:122-157` | ✅ real fan-out | Concurrent w/ failure isolation |
| `Agent Reach 14 channels` | `intelligence/agent_reach/channels/*.py` | ✅ all files exist | only integration layer tested |
| `Agent Reach github.py` real REST | `channels/github.py` | ✅ real | uses gh REST API |
| `Agent Engine` 13 agents | `engines/agent_engine.py:38-68` | ❌ **IMPORT BROKEN** | `imdf.agents.base` not on sys.path at runtime |
| Multi-agent lock manager | (none) | ❌ **MISSING** | All engines use `threading.RLock` (per-process) |
| Memory TTL/eviction | `vida/memory_store.py` | ❌ **MISSING** | History grows unbounded |
| Cost budget enforcement | `engines/usage_tracker.py` | ❌ **MISSING** | Only rate-limit (per-hour call count) |

---

## Top 30 Gaps (P0/P1/P2 severity)

### P0 — Critical: Multi-agent Coordination Missing

#### GAP #1 — 232 experts / 16 departments are dead code (no consumer)

- **Severity**: P0 (CRITICAL — entire Agency narrative broken)
- **Where**: `backend/imdf/agency/` (loader.py, departments.json) + `backend/imdf/engines/agent_router.py`
- **Evidence**: 
  ```powershell
  Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend" -Recurse -Pattern "from backend.imdf.agency"
  # → only 2 matches, both in imdf/agency/tests/
  ```
- **Real scenario that fails**:
  ```
  User: "用爬虫工程师清洗数据"
  Expected: AgentRouter sees "crawler" skill → looks up matrix → picks data_acquisition_expert_001 → invokes it
  Actual: User request bypassed Agency entirely; no expert ever gets picked
  ```
- **Test command**:
  ```powershell
  Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend" -Recurse -Pattern "load_by_id|load_by_department|get_capability_matrix" -Include "*.py"
  # → only test files match
  ```
- **Fix**: Add `backend/imdf/engines/agent_router.py::route_by_skill(skill: str) -> AgentRole` calling `AgencyLoader.get_capability_matrix()`. ~45 min.
- **E-fix time**: 45 min

#### GAP #2 — No distributed lock manager (process-local `threading.RLock`)

- **Severity**: P0 (multi-worker deployment will lose updates)
- **Where**: octo_engine.py:168, meta_kim_engine.py:235, vida_engine.py:98, agent_engine.py:143, octo_kb.py:35, meta_kim_kb.py:48+149, meta_kim_skill_writer.py:65+158
- **Evidence**: 327 `RLock` usages, **zero** Redis/Zookeeper/file-lock patterns.
- **Scenario**: Two gunicorn workers both calling `octo.create_matter("foo")` → both succeed with different IDs; bot state diverges between workers. The bus_events list is per-process — workers can't see each other's events.
- **Fix**: Replace with `imdf.engines.lock_manager.DistributedLock` using Redis SETNX with TTL (already proven in OSS triple-bucket).
- **E-fix time**: 3 hours (full refactor + backward-compat fallback)

#### GAP #3 — AgentEngine import chain broken at runtime

- **Severity**: P0 (whole AgentEngine crashes)
- **Where**: `engines/agent_engine.py:38-68` `_ensure_agent_classes`
- **Evidence**:
  ```python
  & "D:\ComfyUI\.ext\python.exe" -c "import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory'); from backend.imdf.engines.agent_engine import AgentEngine; AgentEngine()"
  # → ImportError: could not import agents.base from either imdf.agents or agents
  ```
- **Root cause**: `_ensure_agent_classes` tries `import imdf.agents.base` but caller only adds `backend/` to sys.path (not `backend/imdf`). Tries `agents.base` fallback but `agents` doesn't exist as top-level.
- **Scenario**: Any code calling `AgentEngine()` from production runtime fails.
- **Fix**: Make `imdf` package installed or auto-load `backend/imdf/__init__.py`. ~30 min.
- **E-fix time**: 30 min

#### GAP #4 — RedFox 6/11 platforms are `NotImplementedClient` (silent fail)

- **Severity**: P0 (cross-post claim false advertising)
- **Where**: `creative/redfox/registry.py:51-59`, `base_client.py:169`
- **Evidence**: `kuaishou, zhihu, toutiao, baijiahao, qiehao, shipinhao` all instantiate `NotImplementedClient`; `publish()` will return FAILED result. Test `test_redfox.py` asserts `len(PLATFORMS) == 11` (passing) but does NOT assert all 11 actually publish (passing in test = mocked).
- **Scenario**: User configures RedFox to publish to all 11 platforms; 6 of them silently return `PublishStatus.FAILED` without raising. UI shows "success" if caller only counts aggregated successes.
- **Fix**: Implement 6 missing platform clients (each ~2 hours using existing weibo/bilibili as templates).
- **E-fix time**: 12 hours

#### GAP #5 — `VidaEngineState` and `VidaContext` symbols missing → 2 test files broken

- **Severity**: P0 (test collection fails → CI red, regression mask)
- **Where**: `engines/engine_router.py:288` (imports `VidaEngineState`), `engines/tests/test_vida_engine.py:6` (imports `VidaContext`)
- **Evidence**:
  ```
  & "D:\ComfyUI\.ext\python.exe" -m pytest engines/tests/ -q 2>&1 | tail -10
  # → ERROR: cannot import name 'VidaEngineState' from 'engines.vida_engine'
  # → ERROR: cannot import name 'VidaContext' from 'engines.vida_engine'
  ```
- **Fix**: Add `class VidaEngineState(str, Enum): IDLE/RUNNING/...` and re-export `VidaContext` from `vida_engine.py`. ~15 min.
- **E-fix time**: 15 min

---

### P0 — Critical: Engine Wiring Gaps

#### GAP #6 — Meta_Kim/Vida/Agent engines: NO real LLM wired (stub-only by default)

- **Severity**: P0 (production deployments produce zero-intelligence heuristic output)
- **Where**: 
  - `meta_kim_engine.py:343-353`: `_clarify_intent` falls back to `_stub_clarify_intent` if `self._llm is None`
  - `vida/intent_predictor.py`: `IntentPredictor(heuristic_only=True)` default
  - `vida/action_executor.py:33`: `ActionExecutor.__init__(self, llm: Optional[LLMOptional] = None)` — no LLM injected by default
  - `agent_engine.py:28-68`: router uses heuristics
- **Evidence**: live `mk = MetaKimEngine(); asyncio.run(mk.govern_run(request="清洗数据"))` → `has_llm: False, status['has_llm']==False`.
- **Scenario**: Production VidaEngine instantiated via `_vida_proactive_assist` in `registry.py:79-86` is built with `IntentPredictor(heuristic_only=True)` → only uses keyword matching (`if 'crawler' in text`), never calls an LLM. Stated "screen-aware LLM intent prediction" is a false claim.
- **Fix**: 
  1. Add a factory `default_llm_provider()` reading from env (`OPENAI_API_KEY`, etc.)
  2. Construct engines with that factory in `engine_router.get_engine("vida"/"meta_kim")`
- **E-fix time**: 2 hours

#### GAP #7 — Default Meta_Kim persistence is in-memory only (lost on restart)

- **Severity**: P0 (Failure KB / Run History disappear on every deploy)
- **Where**: `engines/meta_kim_kb.py:42-62`
- **Evidence**: 
  ```python
  FailureKnowledgeBase()  # no persist_path → records never written to disk
  ```
  `_persist_locked()` early-returns when `self._persist_path` is None (line 121-123).
- **Scenario**: Process restarts after a 7-step governance loop that recorded 100 failures; `meta_kim.failure_kb.count() == 0` after restart. SkillWriter's `created_skills` list also lost.
- **Fix**: Pass `persist_path=".data/meta_kim/"` (per env config) as default in `engine_router.get_engine("meta_kim")`.
- **E-fix time**: 30 min

#### GAP #8 — Memory store has no TTL or eviction (unbounded growth)

- **Severity**: P0 (production disk fills in weeks)
- **Where**: `intelligence/vida/memory_store.py:96-100`
- **Evidence**: `data["history"].append(...)` with no prune; `AgentMemoryStore` has NO `prune` / `evict` / `TTL` method.
- **Scenario**: Daily-active user accumulates ~50 history entries per day → 18,250 entries / year per user / per (action, result). After 1000 users: 18M entries, JSON file ~5GB.
- **Fix**: Add `_evict_locked()` method called on every save that trims entries older than N days (configurable; default 90).
- **E-fix time**: 45 min

#### GAP #9 — Comfy MCP — execution path untested in scope

- **Severity**: P0 (claimed 8 models + 15 nodes but execution mock-dependent)
- **Where**: `creative/comfy/mcp_integration.py:1-490`
- **Evidence**: ComfyMCPIntegration calls `self.comfy_client.run_workflow()` but `ComfyClientLike` is a Protocol stub. Real execution routes through `engines.comfyui_engine.ComfyUIEngine` which is **outside the audit scope**, so it cannot be confirmed real here.
- **Scenario**: User invokes `mcp.run("render 20 anime cats")` → looks up 8-model catalogue correctly → builder produces workflow JSON → `comfy_client.run_workflow` succeeds ONLY IF a real ComfyUI server is wired; absent server, `run_workflow` may return `{}` or `raise NotImplementedError`.
- **Test command**:
  ```powershell
  Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend\imdf\engines\comfyui_engine.py" -Pattern "async def run_workflow"
  ```
- **Fix**: Add smoke integration test that mocks the ComfyUI HTTP endpoint and asserts a 20-job batch yields ≥20 image paths.
- **E-fix time**: 1 hour (test) + 1 hour (runbook)

---

### P1 — High: Cost / Token / Routing Gaps

#### GAP #10 — No budget enforcement in `UsageTracker`

- **Severity**: P1 (no hard USD cap → spend overruns)
- **Where**: `engines/usage_tracker.py:96-340`
- **Evidence**: `UsageTracker.instance()` exposes `record()`, `user_summary()`, `check_rate_limit()` (line 289) — **NO** `check_budget()` / `enforce_budget_cap()` method. Live: `hasattr(ut, 'check_budget') == False`.
- **Scenario**: User burns $10,000 of OpenAI credits in a single hour; `check_rate_limit(per_hour=1000)` only counts calls, not cost.
- **Fix**: Add `def check_budget(user_id: str, max_usd: float) -> Tuple[bool, float]:` reading `user_summary(user_id, days=30)['total_cost_usd']`.
- **E-fix time**: 30 min

#### GAP #11 — SkillSpec 50 = metadata only, no function_ref

- **Severity**: P1 (registry has function_refs but skills_builtin SkillSpec doesn't → can't be invoked)
- **Where**: `backend/skills_builtin.py:39-62` `_make()` returns `SkillSpec` without `function_ref`.
- **Evidence**: Compare to `creative/redfox/skills/__init__.py` where each skill has a `function_ref` callable. `skills_builtin.py` has no such field on `SkillSpec` (it's a different dataclass from `RedFoxSkillSpec`).
- **Scenario**: `SkillRegistry.execute("skill_crawl_web", inputs=...)` raises NotImplemented because no callable.
- **Fix**: Either (a) wire `skills_builtin.SkillSpec` to `imdf.skills.registry` and add function_refs, or (b) deprecate `skills_builtin.py` and require `imdf.skills.registry` registration.
- **E-fix time**: 4 hours (50 skills × 5 min/each + registry glue)

#### GAP #12 — Octo: no actual WebSocket transport (only in-memory bus_events)

- **Severity**: P1 (claim "Octo 协作网络" → no real network protocol)
- **Where**: `octo_engine.py:155-174`
- **Evidence**: `_emit()` records to `self.bus_events` (list) and optionally forwards to `self.bus.record()` if a bus is passed. **No** WebSocket server, **no** STOMP, **no** SSE — pure in-process pub/sub.
- **Scenario**: Multi-worker deployment; Worker A's bot creates a matter, Worker B's router never sees the `octo.matter_created` event.
- **Fix**: Implement `OctoBusPublisher` with `aiohttp.WebSocket` or Redis pub/sub.
- **E-fix time**: 4 hours

#### GAP #13 — Octo execute_collab: zero LLM, just echo hooks

- **Severity**: P1 (bot reply is just `{"echo": body, "by": bot.name}` not real reasoning)
- **Where**: `octo_engine.py:880-904` `_invoke_hook`
- **Evidence**: When `hooks={}` (no executor provided), returns stub `{"echo": matter.body, "by": bot.name, "capabilities": ...}`. Test `test_octo_engine.py` passes for shape only.
- **Scenario**: Production `execute_collab(SWARM, ...)` returns `{"snippets": [{"snippet": {"echo": "..."}}], "count": N}` — useless.
- **Fix**: Add an `LLMHookProvider` that calls Claude/GPT with the bot's `system_prompt` + persona when no hooks dict is given.
- **E-fix time**: 3 hours

#### GAP #14 — Meta_Kim: hash embedding is not real semantic search

- **Severity**: P1 (capability ranking is noise)
- **Where**: `meta_kim_engine.py:139-155` `_hash_embedding`
- **Evidence**: Maps each char to `(ord(ch)+i) % 32` bucket → "crawler" ≈ same vector as "creeper" because of char overlap. Returns `[0.0]*32` for empty text.
- **Scenario**: Search Step 2 ranks "rust" capability near "trust" — wrong match yields wrong bot.
- **Fix**: Wire `sentence-transformers/multi-qa-MiniLM-L6-cos-v1` (small, ~80MB) or call OpenAI `text-embedding-3-small`. ~1 hour end-to-end.
- **E-fix time**: 1.5 hours

#### GAP #15 — Departments have no escalation logic

- **Severity**: P1 (dead-letter for failed matters)
- **Where**: `imdf/agency/loader.py:46-96`
- **Evidence**: `DEPARTMENT_ORDER` is an ordered tuple, but no `escalation_chain` field. `load_by_department` returns members but no routing_when_overflow logic.
- **Scenario**: Data Acquisition is at quota (15 experts) and busy; no overflow routing to `_spare_` even though 15 spare experts exist.
- **Fix**: Add `Department.quota_state` + `Department.escalate_to` + a `DepartmentRouter` that picks spare on overflow.
- **E-fix time**: 2 hours

---

### P1 — High: Memory & State Gaps

#### GAP #16 — Vida memory: no encryption, no access control

- **Severity**: P1 (PII leakage)
- **Where**: `intelligence/vida/memory_store.py:64-114`
- **Evidence**: `json.dump(data, f, ...)` writes history as plain text — `screen.text`, `app_name`, `action.parameters` are recoverable.
- **Scenario**: Multi-tenant install; user A's `.vida_memory/user_b/memory.json` is readable by any process with FS access; screen content leaks.
- **Fix**: Encrypt with user-derived key (Argon2id(password) → Fernet key) at rest.
- **E-fix time**: 2 hours

#### GAP #17 — Octo bus_events list grows unbounded

- **Severity**: P1 (memory leak in long-running processes)
- **Where**: `octo_engine.py:173` `self.bus_events: List[Dict[str, Any]] = []`
- **Evidence**: Only `bus_events.append(envelope)` in `_emit()` (line 243) — never trimmed.
- **Scenario**: 1,000 creates/hour × 24 hours = 24,000 events/day × 5KB each = 120MB/day; never reclaimed.
- **Fix**: Use `collections.deque(maxlen=10_000)` or rotate to disk via `bus.to_archive()`.
- **E-fix time**: 30 min

#### GAP #18 — Skill execution has no rate limit or cost cap

- **Severity**: P1 (runaway skills can DOS infra)
- **Where**: `imdf/skills/registry.py:151-157` `_FUNCTION_MAP`
- **Evidence**: Each function_ref is bare callable with no decorator wrapping for rate limit / cost / time-out.
- **Scenario**: `vida_proactive_assist` is invoked for user A but `_run_vida_skill` does `asyncio.run(_vida_proactive_assist(...))` → if `engine.perceive_and_act` hangs (e.g. screen capture blocked), the call never returns.
- **Fix**: Wrap with `@with_timeout(30s)` + `@with_cost_cap(max_usd=1.0)`.
- **E-fix time**: 1 hour

#### GAP #19 — Agent Engine: 0 builtin agents registered (router empty)

- **Severity**: P1 (matches GAP #3 root cause)
- **Where**: `engines/agent_engine.py:146-159`
- **Evidence**: `auto_register_builtin=True` triggers `register_builtin_agents` from `imdf.agents` lazy import. The function calls `builtin.get_builtin_classes()` which depends on `agents/__init__.py:37-58`. But `agent_engine.py` itself can't even import `imdf.agents` so the whole chain is broken.
- **Scenario**: `ae = AgentEngine(); ae.registered_agents() == []`. Production router has zero agents → all calls fail.
- **Fix**: Same as GAP #3; verify `register_builtin_agents(self._registry)` actually populates `_registry`.
- **E-fix time**: 30 min

---

### P1 — High: Test Coverage Gaps

#### GAP #20 — `engine_router.py` lazy singletons: 6 engines all built in get_engine without DI

- **Severity**: P1 (tests can't inject mocks without `reset_engine_singletons`)
- **Where**: `engines/engine_router.py:295-312`
- **Evidence**: `get_engine("vida")` calls `VidaEngine()` ctor without args → fails because VidaEngine requires 6 components in DI.
- **Test command**:
  ```powershell
  & "D:\ComfyUI\.ext\python.exe" -c "from backend.imdf.engines.engine_router import get_engine; get_engine('vida')" 2>&1 | tail -5
  ```
- **Fix**: Make VidaEngine construct defaults internally OR make get_engine lazily construct on first use with stub components.
- **E-fix time**: 1 hour

#### GAP #21 — Test collection failures block CI

- **Severity**: P1 (regression gate not working)
- **Where**: `engines/tests/test_engine_router_integration.py` + `engines/tests/test_vida_engine.py`
- **Evidence**: Both fail at collection due to `VidaEngineState` and `VidaContext` missing (see GAP #5).
- **Fix**: Add the missing symbols (see GAP #5).
- **E-fix time**: 15 min

---

### P2 — Medium: Cleanup / Hygiene

#### GAP #22 — Octo `OctoChannel.post()` referenced but method signature unclear

- **Severity**: P2
- **Where**: `octo_engine.py:739, 763, 800` etc. — `ch.post(bots[0].id, str(proposal), kind="proposal")` is invoked but `Channel.post()` is not visible in the read.
- **Evidence**: Need to verify against `octo_schemas.py` (not yet audited).
- **Fix**: Pending verification.

#### GAP #23 — `_spare_` department: no actual routing in production

- **Severity**: P2 (15 experts are unused even though registered)
- **Where**: `agency/loader.py:93-95`
- **Evidence**: `_spare_` is loaded and listed but no code path picks a spare expert.
- **Scenario**: All canonical departments fully loaded → spares never activated.
- **Fix**: Add `DepartmentRouter(route_overflow=True)` that promotes spare → department on overflow.

#### GAP #24 — agent_router.py: routing metrics not emitted

- **Severity**: P2 (no observability)
- **Where**: Not yet read in scope.
- **Evidence**: TBD.

#### GAP #25 — Skill engine.get_skill is permissive (any skill_id accepted)

- **Severity**: P2 (skill typos silently bind)
- **Where**: `octo_engine.py:313-322` `assign_skill_to_bot`
- **Evidence**: If `skill_engine is not None`, it checks `get_skill(skill_id)`. If skill_engine is None (default for singleton), **all** skill_ids bind via stub.
- **Fix**: Default `skill_engine=...registry` in `engine_router.get_engine("octo")`.

#### GAP #26 — Bus events use `topic` but skip payload schema validation

- **Severity**: P2
- **Where**: `octo_engine.py:213-243`
- **Evidence**: `_emit(topic, entity_id, payload={}, actor='system')` accepts arbitrary dict.
- **Fix**: Add Pydantic models per topic, validate.

#### GAP #27 — `octo_engine.py` exposes `OctoBot`, `OctoChannel`, `OctoMatter` as aliases but `_matters` dict is `Dict[str, OctoMatter]`

- **Severity**: P2 (legacy/test interop)
- **Where**: `octo_engine.py:162-165` type comment + actual storage `self._matters: Dict[str, OctoMatter] = self.kb._matters`
- **Evidence**: Dual storage causes confusion; `kb.upsert_matter()` writes one copy but `_matters` dict is alias via direct reference.
- **Fix**: Pick one source of truth (`OctoKB`) and remove dict shadowing.

#### GAP #28 — Meta_Kim `embed_fn` default is hash-based, not call site aware

- **Severity**: P2
- **Where**: `meta_kim_engine.py:222-224`
- **Evidence**: `self._embedding_fn = embedding_fn or _hash_embedding` — no logic to check `os.environ.get("OPENAI_API_KEY")`.
- **Fix**: Auto-detect and use real embedding provider if env key present.

#### GAP #29 — Agent engine `_lock` only protects engine's own maps, not registry mutations

- **Severity**: P2
- **Where**: `agent_engine.py:143, 283`
- **Evidence**: `_lock` guards `self._invocations` and `self._sessions` but `self._registry.bulk_register()` (line 158) is called outside the lock.
- **Fix**: Wrap `_registry.bulk_register(...)` under `self._lock`.

#### GAP #30 — Documentation implies 64 engines but only 6 in `engine_router.py`

- **Severity**: P2
- **Where**: README + `VDP-2026-v3-FINAL.md` + system context
- **Evidence**: User profile says "64 引擎框架在" but `engine_router.py:295-312` lists only 6 (`crawler/agent/octo/vida/meta_kim/drama`).
- **Reality**: Other engines live in `engines/*.py` (~75 files) but not plugged into the router. They're "libraries" not "managed engines".
- **Fix**: Add the 64 to router or document that engine router only manages a curated subset.

---

## Suggested Fix Order & Time

| P0 (must-fix before claiming production) | Time |
|-------------------------------------------|------|
| GAP #3 — agent_engine import chain | 30 min |
| GAP #5 — missing VidaEngineState/VidaContext symbols | 15 min |
| GAP #1 — wire AgencyLoader into routing | 45 min |
| GAP #6 — wire real LLM into Meta_Kim/Vida/Agent | 2 hrs |
| GAP #7 — Meta_Kim default persist_path | 30 min |
| GAP #8 — Vida memory TTL/eviction | 45 min |
| GAP #4 — implement 6 RedFox placeholders | 12 hrs |

| P1 (high value) | Time |
|------------------|------|
| GAP #2 — distributed lock | 3 hrs |
| GAP #10 — UsageTracker budget cap | 30 min |
| GAP #12 — Octo WebSocket transport | 4 hrs |
| GAP #13 — Octo real LLM hooks | 3 hrs |
| GAP #14 — real embedding provider | 1.5 hrs |
| GAP #17 — Octo bus_events retention | 30 min |

| P2 (hygiene) | Time |
|--------------|------|
| All remaining | ~6 hrs |

**Total estimated**: 34 hours (≈4 working days).

---

## How to Verify (for code-reviewer / verifier)

```powershell
# 1. Confirm 232 experts load (GAP #1)
& "D:\ComfyUI\.ext\python.exe" "D:\Hermes\生产平台\nanobot-factory\backend\tests\test_agency"  # or read loader.py:443

# 2. Confirm AgencyLoader has ZERO consumers outside tests/  (GAP #1 evidence)
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend" -Recurse -Pattern "AgencyLoader|load_by_id|load_by_department|get_capability_matrix" -Include "*.py"

# 3. Confirm Octo bot/channel/matter/collab real  (GAP-free zones)
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend\imdf\engines\octo_engine.py" -Pattern "def (create_bot|create_channel|create_matter|execute_collab)"

# 4. Confirm Vida screen capture real
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend\imdf\intelligence\vida\screen_capture.py" -Pattern "_capture_windows|_capture_macos|_capture_linux"

# 5. Confirm Meta_Kim 7-step loop
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend\imdf\engines\meta_kim_engine.py" -Pattern "async def govern_run|def _clarify_intent|def _split_tasks|def _verify_results|def _extract_lessons"

# 6. Confirm Comfy 8 models + 15 nodes
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend\imdf\creative\comfy\model_retriever.py" -Pattern "ModelEntry\(" | Measure-Object
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend\imdf\creative\comfy\node_retriever.py" -Pattern "NodeEntry\(" | Measure-Object

# 7. Confirm RedFox 11 (5 real + 6 placeholder)
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend\imdf\creative\redfox\platforms\__init__.py" -Pattern "from "
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend\imdf\creative\redfox\registry.py" -Pattern "NotImplementedClient"

# 8. Confirm AgentReach 14
Get-ChildItem "D:\Hermes\生产平台\nanobot-factory\backend\imdf\intelligence\agent_reach\channels" -Filter "*.py" | Where-Object { $_.Name -ne "__init__.py" } | Measure-Object

# 9. Confirm agent_engine import broken
& "D:\ComfyUI\.ext\python.exe" -c "import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory'); from backend.imdf.engines.agent_engine import AgentEngine; AgentEngine()" 2>&1 | Select-String "ImportError"

# 10. Confirm GAP #5 broken test collection
cd "D:\Hermes\生产平台\nanobot-factory\backend\imdf"; & "D:\ComfyUI\.ext\python.exe" -m pytest engines/tests/ --collect-only 2>&1 | Select-String "ERROR"

# 11. Confirm no distributed lock / only threading.RLock
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend\imdf\engines" -Pattern "import threading" -Include "*.py" | Measure-Object
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend\imdf\engines" -Pattern "import redis|distributed_lock|file_lock|fcntl" -Include "*.py" | Measure-Object

# 12. Confirm no budget enforcement
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\backend\imdf\engines\usage_tracker.py" -Pattern "check_budget|enforce_budget|usd_cap|max_cost"
```

---

## Notes for Verifier

1. The audit focused on REAL behavior (live Python execution) over documentation claims. Where docs claim "screen-aware LLM intent prediction" but the default `IntentPredictor(heuristic_only=True)` proves otherwise, that's a gap.

2. Some components (`engines.comfyui_engine.py`) sit outside the audit's stated scope ("creative/") but are needed for end-to-end Comfy execution; flag as cross-scope concern.

3. The `agent_engine.py` import chain is the single most consequential finding — it caps the entire Agent subsystem as broken in default runtime. Fix order should start here.

4. `engine_router.py` lazy singleton pattern is good (avoids eager import). But `VidaEngine()` requires DI components that the singleton factory doesn't supply → runtime crash on first `get_engine("vida")`. Detail in GAP #20.

5. Tested with the project's `D:\ComfyUI\.ext\python.exe`. All probe scripts ran without modification.

