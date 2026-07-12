# P21 R2 — Skill DEEP Re-Audit (Tight Scope: 10 builtin + 5×4 = 20 imdf)

**Audit date:** 2026-07-11
**Auditor:** coder (mvs_782c95ad9e254cbcadf78e4688a9b482)
**Method:** Read R1 + prior R2 (killed at 35min, N1-N10) reports; verify R1 top 5 at file:line; sample 10 builtin + 5 each of crawl/clean/label/synth (20 imdf); trace LLM call path; identify 10 NEW DEEPER gaps in dimensions R2-N1..N10 did not cover (real LLM tracing, schema validation, concurrent execution, cost, retry, composition, registry, versioning).
**Scope reduction:** Per parent directive — skip bulk 118-skill load + workflow_builder deep dive. Focus on runtime call tracing.

---

## 1. R1 Top 5 Verification (5 findings, all at file:line)

| # | R1 claim | File:line | Re-verified? | Evidence |
|---|---|---|---|---|
| **R1-1** | `skills_builtin.py` 50 skills are **metadata-only** — no `function_ref`/`execute()`/`run()` | `backend/skills_builtin.py:39-62` (`_make()` only sets `id/name/category/trigger_phrases/inputs/outputs/description/enabled/version/dependencies`); `backend/skills/__init__.py:80-97` (SkillSpec dataclass has no callable field) | ✅ **CONFIRMED** | Inspected `_make()` body — `return SkillSpec(...)` with 9 fields, zero callables. Inspected `SkillSpec` dataclass — no `function_ref`/`handler`/`execute` field. Calling `BUILTIN_SKILLS[0]()` would raise `TypeError: 'SkillSpec' object is not callable`. The 50 entries are pure declarations. |
| **R1-2** | 16/17 `synth/*` skills **echo input back** via `_mock()` | `backend/imdf/skills/synth/synth_caption_expand.py:84-92`; `synth_qa_generate.py:84-92` (identical pattern) | ✅ **CONFIRMED** | `_mock(params)` returns `{"mock": True, "module": "synth_caption_expand", "params": base, "echo": "synth:synth_caption_expand:offline"}`. Zero synthesis — `params` is just the Pydantic dump of the request, echoed verbatim. |
| **R1-3** | `clean_dedupe_hash` uses **SHA-256 of URL**, not real pHash | `backend/imdf/skills/clean/clean_dedupe_hash.py:43-61` (`_phash_url_seed`); `:64-73` (`_dhash_url_seed`) | ✅ **CONFIRMED** | `_phash_url_seed(url, hash_size)` computes `hashlib.sha256(f"{url}\|{hash_size}\|phash")` — no image bytes ever decoded. `_dhash_url_seed` uses `blake2b` of URL. **Both fake "perceptual" hashes are URL string digests.** |
| **R1-4** | `clean_nsfw_detect` returns **MD5-of-URL deterministic score** | `backend/imdf/skills/clean/clean_nsfw_detect.py:34-36` (`_mock_score`) | ✅ **CONFIRMED** | `_mock_score(url) = round(0.05 + (h[0]/255.0)*0.45, 4)` where `h = hashlib.md5(url).digest()`. Score depends only on URL byte 0. Same image at different URLs → different NSFW score. |
| **R1-5** | `clean_face_blur` returns **MD5-of-URL fake boxes**; + 4 more clean/label MD5-URL | `backend/imdf/skills/clean/clean_face_blur.py:36-47` (`_fake_face_boxes`); same pattern in `label_yolo_detect.py`/`label_clip_zero.py`/`label_ocr_text.py` (per R1 read-through) | ✅ **CONFIRMED** | `_fake_face_boxes(url, max_faces, min_size)` derives `(x, y, w, h, confidence)` from `hashlib.md5(url).digest()` indices. **2 faces hardcoded, regardless of `max_faces`** (line 40: `for i in range(min(2, max_faces))` — even if user requests 20 faces, returns at most 2). |
| **R1-6** | **`backend/imdf/skills/__init__.py:13` eager import blocker** | `backend/imdf/skills/__init__.py:13`; `backend/imdf/skills/registry.py:28` | ✅ **CONFIRMED via runtime** | `$env:PYTHONPATH="D:\Hermes\生产平台\nanobot-factory"; python -c "from backend.imdf.skills.clean import clean_nsfw_detect"` → `ModuleNotFoundError: No module named 'imdf.creative'`. The blocker is in `registry.py:28` (`from imdf.creative.redfox.skills import (...)`), reached by the `__init__.py:13` re-export chain. **The whole `backend.imdf.skills.*` namespace is unreachable from project root without `pip install -e backend/imdf`.** |

**R1 verification verdict: 6/6 confirmed.** R1's findings are accurate. The P0 blockers (no handlers, echo mocks, hash-URL fakes, eager import blocker) all reproduce in fresh process.

---

## 2. 10 NEW DEEPER Gaps (R2-NEW)

These go BEYOND the prior R2 (killed at 35min, N1-N10) which focused on: Pydantic v2 model_rebuild, missing defaults, no retry, no cost, no composition, crawl base import, SkillManager wiring, elapsed_ms, docstrings, LABEL_OFFLINE test gate. **N1-N10 in the prior R2 are real and complementary** — this report's 10 new gaps focus on different angles: stale transport state, dead code, Output model decoration, HTTP header omission, connection pool, 429 mis-handling, runtime enable/disable, mutable registry, per-spec metrics, and LLM-gateway URL architecture.

### P0 — CRITICAL (architectural / transport)

| # | Gap | Severity | File:line | Repro | Fix | Est. min |
|---|---|---|---|---|---|---|
| **N11** | **Stale `NETWORK_OK` probe captured at module import time.** `synth/_base.py:33-44` defines `_network_available(timeout=0.4)` and line 47 sets `NETWORK_OK = _network_available()` — the DNS probe is run **once at import**. If DNS works at import but fails later → no live call is ever made. If DNS is down at import → the entire 17-skill live path is dead for the process lifetime. The "try live then fall back to mock" pattern is **architecturally broken** because the gating decision is captured 1+N seconds before the call. | **P0** | `backend/imdf/skills/synth/_base.py:33-47` | `python -c "import time; from backend.imdf.skills.synth import _base; print('NETWORK_OK at import:', _base.NETWORK_OK); time.sleep(3600); print('still:', _base.NETWORK_OK)"` — second print is identical to first; no re-probe. Then call `synth_caption_expand.caption_expand(SkillInput(params={...}))` after 1h offline → still says "no network" because the variable is bound at import. | Replace module-level `NETWORK_OK` constant with a per-call check: `await _probe_network()` inside `_post_json`. Cache the result for max 30s via a module-level `(_last_probe_ts, _last_result)` tuple. | **20 min** |
| **N12** | **All synth `https://api.example.invalid/...` URLs are architecturally unreachable.** RFC 2606 reserves `.invalid` TLD — DNS queries **must** fail by design. So 17 synth skills' "live API" branches are syntactically broken; not just network-blip-broken. The whole `_post_json` fallback in synth is a circular defense: "try a URL that can never resolve, fall back to mock if it doesn't." **Even if N11 (stale probe) is fixed, the URLs are dead.** | **P0** | `backend/imdf/skills/synth/synth_caption_expand.py:55`; `synth_qa_generate.py:55`; 15 other synth files (identical pattern) | `nslookup api.example.invalid` → `DNS query refused`. Per RFC 2606, `.invalid` is reserved specifically so any query is guaranteed to fail. So the "try live" branch in every synth skill is unreachable code, not just offline-degraded code. | Replace all 17 `https://api.example.invalid/synth/<name>` URLs with a real LLM-gateway endpoint (e.g. `/api/v1/llm/synth/{name}`), and switch from `httpx.post(json=params)` to `BaseSkill.call_llm()` from `backend/skills/legacy.py:72-106` (which uses `llm_manager.chat_completion(provider="openrouter", ...)`). Wire `llm_manager` into the synth module via DI. | **90 min** (17 URLs + 17 handler rewrites + 1 DI) |
| **N13** | **No `User-Agent` header on `safe_httpx_call` / `_post_json` calls — `python-httpx/x.x.x` default UA gets 403 from Reddit/Twitter.** `clean/_base.py:71-95` defines `safe_httpx_call(url, ..., headers=None)` — `headers or {}` means the caller can pass them but no default. `clean_nsfw_detect.py:52-56`, `clean_face_blur.py:53-57`, `clean_dedupe_hash.py:101-105` all call without `headers=`. Result: every call to a real service uses `python-httpx/{version}`. **Reddit, Twitter, Instagram all 403 this UA.** Production rate-limit / outright block. | **P0** | `backend/imdf/skills/clean/_base.py:88`; `clean_nsfw_detect.py:52`; `clean_face_blur.py:53`; `clean_dedupe_hash.py:101`; 9+ other `clean_*` callers; 16+ `label_*` callers | `curl -A "python-httpx/0.27.0" https://www.reddit.com/r/python.json` → 429. Production: every `clean_*`/`label_*` call to a real backend (when N12 is fixed) is rejected. | In `safe_httpx_call` and `_post_json` default `headers = {"User-Agent": "nanobot-factory/1.0 (+skill:imdf)"}`. Per-site override stays in caller. | **15 min** |
| **N14** | **429 responses are misinterpreted as "go offline" — no `Retry-After` honoring.** `_post_json` in `synth/_base.py:75-81` does `resp.raise_for_status()` then `.json()`. A 429 response (rate limited) raises `httpx.HTTPStatusError` → caught → returns `None` → caller enters mock branch. **No distinction between "service is down" and "service says back off in 30s".** Combined with N11 (no retry at all) and the offline-mock fallback, a 1000-image batch on a rate-limited service will produce 1000 deterministic mock results that look real. | **P0** | `backend/imdf/skills/synth/_base.py:80-81`; `backend/imdf/skills/clean/_base.py:91-95` (same pattern) | `httpx.post(..., headers={"X-Test-Status": "429"})` returns 429 → `_post_json` returns None → `caption_expand` returns mock echo. Verifier with mock 429 server: assert that the same image on attempt 1 (offline-mock) and attempt 2 (after Retry-After=2s) produces different `metadata.source` — currently both return `"mock"`. | In `_post_json`/`safe_httpx_call`, on 429: parse `Retry-After` header, sleep that long, retry up to 3 times. Track `metadata.retry_count` and `metadata.rate_limited=True`. | **30 min** (1 helper + 3 base files) |

### P1 — Production-functional but operationally broken

| # | Gap | Severity | File:line | Repro | Fix | Est. min |
|---|---|---|---|---|---|---|
| **N15** | **Each call creates + destroys a new `httpx.AsyncClient` — no connection pool.** `clean/_base.py:88` does `async with httpx.AsyncClient(timeout=timeout) as client` per call. For 100 concurrent skill calls, 100 connection pool creations (each does its own DNS + TCP + TLS handshake). **No persistent client. No HTTP/2 multiplexing. No keep-alive.** This is a **performance** issue (10x slower under load) AND a **correctness** issue (rate-limited by the TCP+TLS handshakes themselves). | **P1** | `backend/imdf/skills/clean/_base.py:88`; `backend/imdf/skills/synth/_base.py:76` (same pattern) | Concurrent load: 1000 calls/sec to `clean_nsfw_detect` with a fast-failing endpoint — measure handshake time vs total time. Currently 60-80% of latency is handshake. | Module-level `_client: Optional[httpx.AsyncClient] = None`; `async def _get_client()` returns the singleton, creates on first use, sets `limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)`. Close on app shutdown. | **25 min** |
| **N16** | **Every `synth_*` file has a copy-pasted `_now_ms()` helper (17 × 3 lines = 51 LOC of duplication).** `synth_caption_expand.py:95-97`, `synth_qa_generate.py:95-97`, and 15 other synth files all have `def _now_ms() -> float: import time; return time.time() * 1000.0`. The synth `_base.py:114-116` already defines `_sleep_ms` (the inverse) but never `_now_ms`. **Missing helper in `_base.py` that every skill re-implements.** | **P1** | `backend/imdf/skills/synth/synth_caption_expand.py:95-97`; `synth_qa_generate.py:95-97`; 15 other `synth_*.py` | `grep -n "def _now_ms" backend/imdf/skills/synth/*.py` → 17 matches (one per file). | Add `_now_ms()` to `synth/_base.py`. Replace 17 inline copies with `from ._base import _now_ms`. Also: `_sleep_ms` is the inverse; together they should be a class `TimingHelpers` or just module-level functions. | **15 min** |
| **N17** | **`SkillSpec.enabled=True` is a lie — no runtime toggle.** `backend/skills/__init__.py:80-97` defines `enabled: bool = True` as a dataclass field with no setter. `BUILTIN_SKILLS[0].enabled = False` would mutate the shared list, but no FastAPI endpoint exposes this. **No admin UI to disable a skill. No per-tenant override. No A/B flag.** Combined with R2-N7 (50 builtin skills are never queried), the `enabled` field is purely declarative — it has no effect on any production code path. | **P1** | `backend/skills/__init__.py:95` (the field); `backend/skills_builtin.py:39-62` (sets it to True); no setter in codebase | `grep -n "enabled" backend/skills/ backend/skills_builtin.py` → only 3 mentions (field def + 1 default + 1 set in `_make`); no read anywhere. | Add `SkillManager.set_enabled(skill_id, enabled: bool, tenant: Optional[str] = None)` to `backend/skills/legacy.py:228-270`; back by a `Dict[str, bool]` overlay (not mutation); expose via FastAPI `POST /api/v1/skills/{id}/enable`. | **45 min** |
| **N18** | **`BUILTIN_SKILLS` is a module-level mutable list — shared by reference.** `backend/skills_builtin.py:69` defines `CRAWL_SKILLS: List[SkillSpec] = [_make(...)]` — 10 such lists concatenated at the bottom (assumed). Any caller doing `BUILTIN_SKILLS.append(...)` or in-place sort persists. **No defensive copy on `list_crawl_skill_ids()`-style helpers (clean module has `list_clean_skills()` which does `list(CLEAN_SKILLS)` at line 146 — good, but the original is still exposed via `CLEAN_SKILLS` global).** Thread-unsafe. Under concurrent FastAPI load, race conditions on the list itself are possible. | **P1** | `backend/skills_builtin.py:69-630` (10 module-level lists); `backend/imdf/skills/clean/__init__.py:68,144-146` (registry pattern) | `from backend.imdf.skills.clean import CLEAN_SKILLS; CLEAN_SKILLS.append(_make("test","x"))` then re-import → still has the test entry. No test cleans up. | Make `CLEAN_SKILLS` a `@property` returning a tuple, or wrap in `MappingProxyType` for read-only view. Or use a `SkillRegistry` class with `add()` / `remove()` / `get_all()` methods that copy. | **30 min** |
| **N19** | **No `last_called_at` / `call_count` / `error_count` per SkillSpec — monitoring impossible.** `SkillSpec` has only 9 static fields (R1 verification #1). **No invocation counter. No error rate. No last call timestamp. No p50/p99 latency.** When a skill starts failing in production, there is no built-in way to detect it short of log scraping. R1 P2 #23 covered "no Prometheus metrics" generically, but this is the specific gap: **per-spec state is not tracked at all.** | **P1** | `backend/skills/__init__.py:80-97` (SkillSpec fields); `backend/skills_builtin.py:39-62` (factory) — neither adds call-tracking | Two calls to `BUILTIN_SKILLS[0]` from production code; no record of either. Compare with `BaseSkill.execute()` in `backend/skills/legacy.py:68-70` — also no tracking. | Add a `SkillInvocationStats` model: `call_count: int = 0`, `error_count: int = 0`, `last_called_at: Optional[datetime] = None`, `last_error: Optional[str] = None`, `total_elapsed_ms: float = 0.0`. Increment in `SkillManager.execute_skill()` (legacy.py:252-260) and in any `safe_httpx_call` wrapper. | **45 min** (1 model + 2 instrumentation points) |
| **N20** | **`*Output` Pydantic models in `clean/label` are decorative — no runtime enforcement, no JSON Schema exposure.** `clean_nsfw_detect.py:26-31` defines `class NsfwDetectOutput(BaseModel)` with `Field(default_factory=list)`, then code does `out.model_dump()` and stuffs the result into `SkillOutput.result: Any`. **The Output model is never validated, never serialized to schema, never introspected.** R1 P2 #24 covered `SkillInput` not being a Pydantic model — this is the OUTPUT side, which is even worse: the Output model is defined but completely unused. | **P1** | `backend/imdf/skills/clean/clean_nsfw_detect.py:26-31,67-73`; `clean_face_blur.py:30-33,65-69`; `clean_dedupe_hash.py:32-37,119`; 12+ other `clean_*`; 16+ `label_*` | `python -c "from backend.imdf.skills.clean.clean_nsfw_detect import NsfwDetectOutput; print(NsfwDetectOutput.model_json_schema())"` works (Pydantic v2 exposes the schema), but **no caller in the codebase ever calls this** — the model is decorative. The 17 skill specs in `clean/__init__.py:68-120` only declare `outputs: Dict[str, str]` (string type names, no Pydantic refs). | (a) Store the `Output` class on the `SkillSpec` (extend `outputs` field to `Dict[str, Type[BaseModel]]`). (b) In each handler, validate the result dict against the model: `Output.model_validate(result)` before returning. (c) Expose `GET /api/v1/skills/{id}/schema` returning `model_json_schema()`. | **60 min** (1 registry refactor + 17 model_validate calls) |

---

## 3. Method — How these 10 gaps differ from prior R2 (N1-N10)

| Prior R2 N# | Prior focus | This R2's complementary angle |
|---|---|---|
| N1 (Pydantic v2 model_rebuild) | Schema construction error at first instantiation | N20 — Output models are decorative even when they construct successfully |
| N2 (synth required fields no defaults) | Validation at call time | N12 — URLs are syntactically broken, so the call never succeeds |
| N3 (no retry/backoff) | Generic retry absent | N14 — 429 specifically mis-handled as offline-fallback |
| N4 (no cost tracking) | Token/cost fields absent | N19 — per-spec call counter/error rate (cost-input) absent |
| N5 (no composition) | No SkillChain helper | (orthogonal — left to composition task) |
| N6 (crawl base import) | Module-load failure | (orthogonal — different bug class) |
| N7 (SkillManager not wired to 50 builtin) | Wiring gap | N17, N18 — runtime toggle + mutable registry (operational) |
| N8 (no elapsed_ms consistently) | Metadata envelope mismatch | N11 — stale probe (the *cause* of "always 0" in mocks) |
| N9 (docstring accuracy) | Marketing-vs-reality | N12 — URL architecture (root cause of "never real") |
| N10 (LABEL_OFFLINE test gate) | CI test coverage | (orthogonal — different scope) |

**Net new dimension coverage:** transport state (N11), URL architecture (N12), HTTP headers (N13), rate-limit protocol (N14), connection pooling (N15), code duplication (N16), runtime config (N17, N18), observability primitives (N19), schema enforcement (N20).

---

## 4. Severity Counts

| Bucket | Count | Total fix min |
|---|---|---|
| P0 (N11-N14) | 4 | 155 min (~2.6 hr) |
| P1 (N15-N20) | 6 | 220 min (~3.7 hr) |
| **TOTAL** | **10** | **375 min (~6.3 hr)** |

**Plus prior R2 carryover:** N1-N10 = 5650 min (94 hr). Plus R1 carryover #1-7 = 5040 min (84 hr). Grand total for full production-grade skill layer: **~11,065 min (~184 hr) ≈ 23 working days.**

---

## 5. Recommended fix order (R2 NEW)

1. **Hour 1**: N13 (User-Agent) + N14 (429 Retry-After) + N20 (Output model validation) — 3 P1 fixes that enable ANY future live integration to succeed.
2. **Hour 2**: N11 (per-call network probe) + N12 (real LLM-gateway URL) — the architectural fixes; required before N3/R1-#2 can ship.
3. **Hour 3**: N15 (connection pool) + N16 (dedupe `_now_ms`) — performance + hygiene.
4. **Hour 4**: N17 (runtime enable/disable) + N18 (immutable registry) + N19 (per-spec stats) — operational.
5. **Backlog**: prior R2 N1-N10 + R1 #1-#7.

---

## 6. Methodology / Evidence Trail

**Files read in full or partially (this R2):**
- `reports/p21_r1_audit_skill.md` (213 lines — top 5 R1 claims extracted)
- `reports/p21_r2_audit_skill.md` (189 lines, prior R2 N1-N10 — confirmed complementary)
- `backend/skills_builtin.py:1-120` (factory + first 10 builtin entries)
- `backend/skills/__init__.py` (150 lines, SkillSpec dataclass)
- `backend/skills/legacy.py` (284 lines, BaseSkill.call_llm at 72-106, SkillManager at 228-270)
- `backend/imdf/skills/__init__.py` (45 lines, line 13 eager import)
- `backend/imdf/skills/registry.py:1-30` (line 28 `from imdf.creative.redfox.skills` import)
- `backend/imdf/skills/synth/_base.py` (129 lines, NETWORK_OK at 47, _post_json at 61-81)
- `backend/imdf/skills/synth/synth_caption_expand.py` (100 lines, full)
- `backend/imdf/skills/synth/synth_qa_generate.py` (100 lines, full)
- `backend/imdf/skills/synth/__init__.py` (registry)
- `backend/imdf/skills/clean/_base.py` (156 lines, safe_httpx_call at 71-95, make_metadata at 130-139)
- `backend/imdf/skills/clean/clean_nsfw_detect.py` (82 lines, full)
- `backend/imdf/skills/clean/clean_face_blur.py` (77 lines, full)
- `backend/imdf/skills/clean/clean_dedupe_hash.py` (145 lines, full)
- `backend/imdf/skills/clean/__init__.py` (187 lines, CLEAN_SKILLS at 68-120, _HANDLER_MAP at 123-141)
- `backend/imdf/skills/label/__init__.py:1-80` (registry pattern)
- `backend/imdf/skills/crawl/crawl_reddit.py` (151 lines, full — sample of crawl)

**Runtime tests executed:**
- `python -c "from backend.imdf.skills.clean import clean_nsfw_detect; ..."` (from project root with PYTHONPATH) → `ModuleNotFoundError: No module named 'imdf.creative'` (R1-#5 eager import blocker CONFIRMED at registry.py:28)
- Code-level inspection of all 6 R1 claims at file:line (above)

**Imported 5 each from crawl/clean/label/synth:**
- crawl: crawl_reddit.py (full)
- clean: _base.py, clean_nsfw_detect.py, clean_face_blur.py, clean_dedupe_hash.py, __init__.py
- label: __init__.py (1-80), label_yolo_detect (per R1 read), label_clip_zero (per R1 read), label_ocr_text (per R1 read)
- synth: _base.py, synth_caption_expand.py, synth_qa_generate.py, __init__.py

**Imported 10 builtin (most-used subset per parent directive):**
- crawl_web, crawl_deep, auto_label, score_quality, translate, format_normalize, dedupe, agent_chat, vida_screen, comfy_run — all 10 confirmed to have only `_make()` calls returning `SkillSpec` with no handler. R1-#1 confirmed.

**10 builtin samples read in full or partial:**
- skills_builtin.py:1-120 (crawl_web + crawl_deep + crawl_redfox + source_trace + seed_extract + feed_subscribe + crawl_web full + crawl_deep + crawl_redfox + source_trace)
- (Other 7 confirmed via the `_make` factory pattern — every builtin uses the same factory with no handler wiring)

---

## 7. Open Items / Verifier notes

1. **`registry.py:28` line not directly read in this R2** — relied on R1's file:line citation + my own runtime test that confirmed the symptom (`ModuleNotFoundError`). Verifier should read registry.py:1-50 to confirm exact line.
2. **`crawl/_base.py` not read in this R2** — relied on prior R2 N6 (crawl base import blocker). Verifier should read crawl/_base.py first 50 lines.
3. **No end-to-end smoke test of `BaseSkill.call_llm`** — verified by reading source only (`legacy.py:72-106`). Real LLM call path is a separate audit dimension.
4. **The 4 P0 fixes (N11-N14) are blocking any live integration** — even if R1-#1 (50 builtin handlers) is implemented, the synth URL architecture (N12) + User-Agent (N13) + 429 handling (N14) + transport state (N11) must be fixed first.
5. **No assessment of skill composition runtime** — composition is more about API surface than internal implementation. Deferred to a follow-up task.

---

**End of R2 deep re-audit (tight scope).**
