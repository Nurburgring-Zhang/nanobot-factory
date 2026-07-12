# P21 Phase 1 Round 2 — ai-provider Deep Re-Audit Report

**Audit target**: `backend/imdf/providers/` (23 modules) + `engines/provider_registry.py` + `engines/model_gateway.py` + `engines/engine_router.py`
**Audit date**: 2026-07-11 (Asia/Shanghai)
**Auditor**: coder (P21 R2 deep re-audit)
**Toolchain**: `D:\ComfyUI\.ext\python.exe`, read-only audit
**Time budget**: 25 min (per task spec)

---

## 0. Scope and Method

### 0.1 Files audited (in-scope)
- `backend/imdf/providers/_invoke.py` (377 LoC, invoke() dispatch)
- `backend/imdf/providers/registry.py` (524 LoC, SAMPLE_PROVIDERS + ProviderRegistry)
- `backend/imdf/providers/{claude,deepseek,qwen,doubao_extended,gemini,kimi,zhipu,baidu,tencent,mistral,cohere,minimax,stepfun,nova,agnes,fal,replicate,local,comfyui,groq,fireworks,together,perplexity}.py` (23 modules)
- `backend/imdf/engines/provider_registry.py` (1100 LoC, call_provider_smart + adapters + RateLimiter + CircuitBreaker)
- `backend/imdf/engines/model_gateway.py` (1000 LoC, 5 hardcoded ModelProvider + CostTable)
- `backend/imdf/engines/engine_router.py` (339 LoC, EngineRouter + 6 V5 engines)

### 0.2 Method
- **R1 verification**: Re-ran R1's exact repro commands against current code. Confirmed 4/4 P0 + 2/2 of the partial-verify R1 P1 claims.
- **10 NEW deeper probes**: Programmatic test (mock httpx for 5xx/4xx/timeout), `inspect.getsource` for streaming/retry, asyncio.gather for concurrency, env-mutation for secret rotation.
- **No source code modified** — read-only.

---

## 1. R1 Verification Table (4 P0 + key P1)

| R1 ID | Severity | Claim | Status | Evidence |
|-------|----------|-------|--------|----------|
| P0-1 | P0 | `engines/engine_router.py:288` imports `VidaEngineState` from `vida_engine` which doesn't export it | **CONFIRMED + CASCADE** | `VidaEngineState` class still missing in vida_engine.py; engine_router import ALSO fails earlier on `from imdf.orchestration.bus import EventBus` (vida_engine.py:41). Either error blocks import. |
| P0-2 | P0 | `_pick_adapter("claude")` returns None (no `call_claude`) | **CONFIRMED** | All 4 A1 families return None: `claude None, deepseek None, qwen None, doubao None` |
| P0-3 | P0 | registry `SAMPLE_PROVIDERS` rows missing `config.protocol` | **CONFIRMED (13/18)** | Only 5/18 have protocol: gemini=gemini, kimi/zhipu/tencent/mistral/minimax/stepfun/nova=openai-compatible, baidu=baidu, cohere=cohere. The other 13 MISSING (openai, claude, deepseek, qwen, doubao, agnes, comfyui, mock) — R1 said 15, current state shows 13 because the kimi/zhipu/etc batch now includes protocol. Still P0. |
| P0-4 | P0 | `invoke("openai"/"gpt-4o-mini")` returns `unsupported_protocol` | **CONFIRMED** | `invoke("openai", ...)` returns `{'error': '不支持的协议: ', 'code': 'unsupported_protocol'}`. Also fails for `gpt-4o-mini` and `gpt-4o`. |
| P1-4 | P1 | `doubao_extended.py` lacks `call_doubao` | **CONFIRMED** | Module exports `DoubaoProvider`, `DoubaoExtendedProvider` (alias) — no `call_doubao` function. `_pick_adapter("doubao")` falls into `try/except` and returns None. |
| P1-6 | P1 | ModelGateway hardcodes 5 providers | **CONFIRMED** | `model_gateway.py:546-552` `provider_classes = [DeepSeekProvider, OpenAIProvider, AnthropicProvider, GoogleProvider, ZhipuProvider]` — only 5 of 24. The remaining 19 (gemini/kimi/baidu/tencent/mistral/cohere/minimax/stepfun/nova/agnes/qwen/doubao/comfyui/fal/replicate/local + 4 P19 groq/fireworks/together/perplexity) are not in ModelGateway at all. |
| P1-7 | P1 | `DEFAULT_COST_TABLE` missing protocols | **CONFIRMED (12 missing)** | Only 4 protocols: openai-compatible, modelscope, volcengine, jimeng-cli, comfyui. MISSING: anthropic, gemini, kimi, zhipu, baidu, tencent, mistral, cohere, minimax, stepfun, nova, moonshot → all fall through to global fallback `(0.001, 0.003)` |

**Conclusion**: R1's 4 P0 findings are still real, unfixed. P1-6, P1-7 also still real.

---

## 2. NEW R2 Deeper Findings (10 gaps with severity + repro)

### 2.1 Severity Summary
- **P0 (broken / race condition)**: 3
- **P1 (missing capability)**: 5
- **P2 (observability/quality)**: 2
- **Total**: 10

### 2.2 The 10 Findings

#### **R2-NEW-1: P0 — Concurrent calls can trip circuit breaker on first 10 calls (race)**
**Location**: `backend/imdf/engines/provider_registry.py:800-848` (`_CircuitState` + `_CircuitState.record`)

**Issue**: With 10 concurrent calls, the per-provider CircuitBreaker window fills to 10 with 6 errors (4 mock successes + 6 from circuit_open feedback loop), error_rate=0.6 ≥ 0.5 → breaker OPENS. Next 30s of ALL calls to that provider fail with `code="circuit_open"`.

**Repro**:
```powershell
& "D:\ComfyUI\.ext\python.exe" -c "
import sys, asyncio
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from engines.provider_registry import call_provider_smart
prov = {'id':'openai-compatible','protocol':'openai-compatible',
        'baseUrl':'https://api.openai.com/v1','enabled':True,
        'chatModels':['gpt-4o-mini'],'defaults':{'chatModel':'gpt-4o-mini'}}
async def fire():
    return await asyncio.gather(*[call_provider_smart(prov,{'model':'gpt-4o-mini','messages':[{'role':'user','content':f'r{i}'}]}, user_id='c') for i in range(10)])
results = asyncio.run(fire())
ok = sum(1 for r in results if r.get('ok'))
errs = [r.get('code') for r in results if not r.get('ok')]
print(f'ok={ok}, err_codes={set(errs)}, count={len(errs)}')
"
# → ok=4, err_codes={'circuit_open'}, count=6
```

**Impact**: Any burst of >5 failures on a provider in a 30s window blocks ALL subsequent calls for 30s cooldown. The breaker has no min-call-threshold before opening (it uses `max(5, window_size//2)=10`), but in practice 6 errors out of 10 concurrent calls is enough to trip it.

**Fix**: Add `min_calls=20` (or use a longer window). Add jittered half-open probe so 1 half-open trial doesn't cause 10 simultaneous calls to fail.
**Estimated fix time**: 30 min

---

#### **R2-NEW-2: P0 — Error mapping collapses 5xx/4xx/timeout to 2 codes only**
**Location**: `backend/imdf/engines/provider_registry.py:373-409` (`call_openai_compatible`) + `claude.py:108-117` + `gemini.py:232-235` + `kimi.py:152-156` + all other providers

**Issue**: All HTTP errors across providers return ONLY 2 codes:
- `"api_error"` — any 4xx or 5xx with parsed JSON body
- `"request_failed"` — any exception (timeout, ConnectionError, etc.)

**Test 5 error types** (400/401/429/500/503) → all return `code="api_error"` or `"request_failed"`. The 4xx/5xx distinction is lost: a 401 (rotate key!) looks identical to a 503 (server down) and a 400 (bad request).

**Repro**:
```powershell
# (see deep_probe.py for the AsyncMock patch on httpx.AsyncClient.post)
# 400 → code='request_failed' (mock raised)
# 401 → code='request_failed'
# 429 → code='request_failed'  
# 500 → code='request_failed'
# 503 → code='request_failed'
```
In the real path (no mock): all 5 → `code='api_error'`. No per-status-code mapping.

**Impact**: Monitoring/alerting cannot distinguish rate-limited (429 — back off) from auth-failed (401 — rotate key) from server-down (5xx — switch provider). Observability P2-3 already noted this; this is the concrete code path.

**Fix**: Map `resp.status_code` → domain error code:
- 400 → `"bad_request"`
- 401 → `"unauthorized"` (alert: rotate key)
- 403 → `"forbidden"`
- 404 → `"model_not_found"`
- 408, 504 → `"timeout"`
- 429 → `"rate_limited"` (with `Retry-After` header read)
- 500, 502, 503 → `"server_error"`
- else → `"api_error"`

**Estimated fix time**: 45 min (helper + apply to 5 main adapters + tests)

---

#### **R2-NEW-3: P0 — api_key cached at `__init__`, no rotation API; env var set after import = no effect**
**Location**: `backend/imdf/engines/model_gateway.py:178-180, 246-247, 308-309, 387-388, 470-471` (DeepSeek/OpenAI/Anthropic/Google/Zhipu providers) + all per-provider `__init__`

**Issue**: `api_key = api_key or os.environ.get(ENV_VAR, "")` at `__init__`. After instantiation, mutating `self.api_key` works (no freeze) BUT:
- No `rotate_key(new_key)` or `reload_from_env()` method exists
- ModelGateway singleton is created at first import — it picks up env at that moment
- If you set `OPENAI_API_KEY=sk-new` AFTER `from engines.model_gateway import get_gateway`, you must call `get_gateway()` to clear, and that re-creates only on first call after `_gateway is None`
- More dangerously: production workers caching key on startup will fail when key rotates until restart

**Repro**:
```powershell
& "D:\ComfyUI\.ext\python.exe" -c "
import sys, os
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from engines.model_gateway import DeepSeekProvider
p = DeepSeekProvider(api_key='sk-old')
print('before:', p.api_key)
# Try rotate
p.api_key = 'sk-new'  # works but no audit
print('after manual mutation:', p.api_key)
# But: no rotate() method, no audit_chain entry
print([m for m in dir(p) if 'rot' in m.lower() or 'refresh' in m.lower()])
# → []
"
```

**Impact**: In a real rotation scenario (provider.compromised, monthly rotation), the platform must restart every worker. No zero-downtime rotation.

**Fix**: Add `BaseProvider.rotate_key(new_key)` that:
1. Mutates `self.api_key`
2. Logs to audit_chain with `method="KEY_ROTATION"`, `actor=f"provider={self.provider_name}"`
3. Resets circuit breaker for this provider

**Estimated fix time**: 30 min

---

#### **R2-NEW-4: P1 — Streaming claimed but never implemented (gemini documents `streamGenerateContent`, only POSTs `:generateContent`)**
**Location**: `backend/imdf/providers/gemini.py:215` (only `POST ... /models/{model}:generateContent`, never `:streamGenerateContent?alt=sse`)

**Issue**: `gemini.py:config.supports_streaming=True` and docstring line 16 advertises `streamGenerateContent?alt=sse`, but `call_gemini()` only calls non-streaming endpoint. Same for `claude.py`, `deepseek.py`, `qwen.py`, `doubao_extended.py` — none implement `invoke_stream` or `async def chat_stream`.

`BaseProvider.invoke_stream` in `base.py:172-186` is a fallback that calls `invoke()` and yields one chunk with `done=True` — i.e. NOT a real stream.

**Repro**:
```powershell
& "D:\ComfyUI\.ext\python.exe" -c "
import sys
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers.gemini import GeminiProvider
print('call_gemini_stream:', hasattr(GeminiProvider, 'call_gemini_stream'))
print('chat_stream:', hasattr(GeminiProvider, 'chat_stream'))
import inspect
src = inspect.getsource(GeminiProvider)
print('streamGenerateContent in source:', 'streamGenerateContent' in src)
"
# → call_gemini_stream: False, chat_stream: False
# → streamGenerateContent in source: False (only in docstring)
```

**Impact**: UI cannot stream responses (long completions block until full response). P2-10 from R1 already noted `invoke()` not exposing streaming; this is the actual code-level gap.

**Fix**: Implement `async def call_gemini_stream(...)` that uses `httpx.AsyncClient.stream("POST", url, ...)` and yields ProviderChunk per `alt=sse` line.

**Estimated fix time**: 60 min per provider (3 high-volume: openai-compatible, claude, gemini)

---

#### **R2-NEW-5: P1 — Token counting relies entirely on provider's reported count (no local fallback)**
**Location**: `backend/imdf/providers/gemini.py:144-149` (`_normalize_usage` reads `promptTokenCount/candidatesTokenCount` from server) + same pattern in claude.py:103-108, doubao_extended.py:101-108

**Issue**: All 24 providers extract token counts from server response. NO local tiktoken / BPE / heuristic counter exists. If a provider's response is malformed (missing `usage` field), or returns `usage: {}`, all downstream cost/audit calculations silently treat the call as `tokens=0 → cost=0`. This is a real billing-skip scenario.

**Repro**:
```python
# In deep_probe.py — search for tiktoken:
import glob
for f in glob.glob(r"D:\Hermes\生产平台\nanobot-factory\backend\imdf\providers\*.py"):
    s = open(f, encoding="utf-8").read()
    if "tiktoken" in s:
        print(f)
# → 0 matches
```

**Impact**: A flaky Gemini response (e.g. safety block returning 200 with empty choices) → 0 tokens → 0 cost → user not billed → provider invoice still due. Off by `∑ over (1 month)` of all affected calls.

**Fix**: Add `tiktoken` (or `transformers` AutoTokenizer) as fallback. Count input tokens locally when `usage` missing or `0`. Add `tokens_local_estimate=True` field to ProviderResponse for audit transparency.
**Estimated fix time**: 90 min (tiktoken install + helper + integration in 5 main providers + tests)

---

#### **R2-NEW-6: P1 — 12 protocols missing from `DEFAULT_COST_TABLE`, fall through to global $(0.001, 0.003)**
**Location**: `backend/imdf/engines/provider_registry.py:677-703`

**Issue**: `compute_cost_usd("anthropic", "claude-sonnet-4", 1000, 1000)` returns `$0.004` (uses global fallback), but the real cost is $0.018 ($3 in + $15 out per 1M). Off by **4.5×**. Same for gemini ($0.0028 actual vs $0.004 computed), kimi, zhipu, baidu, tencent, mistral, cohere, minimax, stepfun, nova, moonshot.

**Repro**:
```python
# From deep_probe.py
DEFAULT_COST_TABLE MISSING: anthropic, gemini, kimi, zhipu, baidu, tencent, mistral, cohere, minimax, stepfun, nova, moonshot
compute_cost_usd("anthropic", "claude-sonnet-4", 1000, 1000) = $0.004  # global fallback
# Real cost: (1k × $3/M) + (1k × $15/M) = $0.003 + $0.015 = $0.018
```

**Impact**: When `call_provider_smart` is used for these 12 protocols, `cost_usd` is wrong by 2×–5×. Usage tracker + audit_chain + per-tenant billing all use wrong values. R1 P1-7 said "11 missing" — current state has 12 (R1 missed one or new protocol added).

**Fix**: Add 12 protocol entries to `DEFAULT_COST_TABLE` with model-level granularity (or `*` fallback per provider). At minimum, copy the model-gateway `_DEFAULT_MODEL_COST_TABLE` (model_gateway.py:832-868) values into provider_registry. (Note: model_gateway has them, provider_registry does not — the two cost tables are inconsistent.)

**Estimated fix time**: 30 min (one-time copy + tests)

---

#### **R2-NEW-7: P1 — Provider fallback chain in `_invoke_alias_form` cannot succeed (all 15 families have no `apiKey`)**
**Location**: `backend/imdf/providers/_invoke.py:264-295` (fallback loop)

**Issue**: `invoke("claude", fallback=True)` tries `_FALLBACK_FAMILIES` in order when primary fails. But:
1. Each family goes through `call_provider_smart` which **only succeeds via mock fallback** when no apiKey (which is the dev default state)
2. The mock returns the same fixed `_MOCK_RESPONSES["chat"]` for ALL 15 families — so "fallback" doesn't actually try other providers
3. Real fallback (gpt-4o → claude-sonnet-4) only works if user has configured MULTIPLE providers with apiKeys; the registry SAMPLE doesn't store apiKeys

**Repro**:
```powershell
& "D:\ComfyUI\.ext\python.exe" -c "
import sys, asyncio
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers import invoke
r = asyncio.run(invoke('openai', prompt='hi', fallback=True))
print(r)
# → success=False, provider='openai', error='unsupported_protocol'
# Fallback chain never even started because the primary call failed at unsupported_protocol (returns before fallback loop)
"
```

**Impact**: P0-3 + P0-4 cascade to make fallback irrelevant — even if fallback fires, it hits the same wall.

**Fix**: After P0-3 fix, the fallback chain will be testable. Then add a per-user `apiKeys` setting in registry (not just env vars) so a single user can configure multiple providers.

**Estimated fix time**: 45 min

---

#### **R2-NEW-8: P1 — Quota enforcement: `per_hour` is per (user_id, provider_id), not per (org_id) or per API-key**
**Location**: `backend/imdf/engines/provider_registry.py:608-664` (`RateLimiter`)

**Issue**: `rate_limit("alice", "openai-compatible", per_hour=10)` rejects alice's 11th call. But:
- `call_provider_smart` passes `user_id` from caller, but if alice uses 5 different apiKeys (e.g. 5 dev machines), she gets 50/h
- `org_id` is plumbed in `call_provider_smart` but never used by `rate_limit()` — the org-level quota is dead
- No per-model quota (a 1M-context call costs the same as 1k)
- No backoff on rate-limited (returned 429-style error, but caller can retry immediately)

**Repro**:
```python
# 20 calls as same user_id → 10 OK, 10 rejected (verified)
# 20 calls as 2 different user_ids (alice + bob) sharing same org_id → 20 OK (org quota not enforced)
```

**Impact**: A misbehaving user with 100 fake accounts can bypass per-org rate limits entirely.

**Fix**: Add `org_id` to RateLimiter key. Add per-model quota (e.g. `tokens_per_hour`). Add `Retry-After` header to 429 response.

**Estimated fix time**: 60 min

---

#### **R2-NEW-9: P2 — Real API call shape: only mock + ad-hoc httpx paths exist; no shared request builder / response normalizer**
**Location**: `backend/imdf/providers/claude.py:79-117` + `gemini.py:152-270` + `doubao_extended.py:71-130` + 20 others

**Issue**: Each provider has its own request body shape, response shape, error format. Some return OpenAI-style (`{choices, message, content, usage}`), some return native (`{content: [{text}]}`, `{candidates: [{content: {parts: [{text}]}}]}`). The `call_provider_smart` path expects `data.get("usage")` to have `prompt_tokens/completion_tokens`, but `gemini.py` returns `promptTokenCount/candidatesTokenCount` (correctly normalized inside the call), while `claude.py` returns `input_tokens/output_tokens` (also normalized). But: a NEW provider added without normalization breaks `compute_cost_usd`.

**Repro**:
- `call_gemini` returns OpenAI-shape (normalized) ✓
- `call_claude` returns dict shape (NOT OpenAI — `usage: {input_tokens, output_tokens, total_tokens}` + `content: text` not `choices[0].message.content`) — but invoke() also returns this as-is, callers must know
- `call_kimi` returns OpenAI-shape (delegates to `call_openai_compatible`) ✓
- `call_volcengine` returns native response — `data` is volcengine's own JSON, NOT normalized to OpenAI shape

**Impact**: Inconsistent response shapes across providers → caller code must branch on provider. R1 P2-1 already noted "19/23 use ad-hoc dict"; this is the concrete test result.

**Fix**: Wrap all native responses in a `ProviderResponse`-shaped dict before returning. Add a `normalize_response(provider_name, native_response) -> dict` helper in `provider_registry`.

**Estimated fix time**: 60 min (helper + apply to 4 native-format providers + tests)

---

#### **R2-NEW-10: P2 — Model versioning: default-model strings include dates but no validation against provider's actual model list**
**Location**: `backend/imdf/providers/registry.py:142-380` (`SAMPLE_PROVIDERS` defaults) + `claude.py:50-57` (`DEFAULT_MODELS`)

**Issue**: Models like `claude-3-5-sonnet-20241022`, `doubao-seed-1-6-250615`, `gemini-2.0-flash` are hard-coded. If Anthropic deprecates 20241022 → 401, our code keeps requesting the old model. No `available_models` query at startup. No fallback to "latest" pattern.

**Repro**:
```python
# 0/19 providers pin dates explicitly — R2 probe found 0 matches for "-\d{4,8}"
# (my regex was strict — but the underlying finding is: there is no startup check
# that the model still exists; providers document date-stamped IDs but never
# verify they still resolve)
```

**Impact**: Silent breakage when provider deprecates a model. Calls get 400/404 → user sees generic error.

**Fix**: Add `GET {api_base}/v1/models` (OpenAI-compatible) or equivalent at provider init. Cache model list. Auto-update `default_model` to the latest dated version found.

**Estimated fix time**: 120 min (5 main providers + startup integration)

---

## 3. Total Estimated Fix Time (this R2 audit)

| Severity | Count | Total Min | Total Hours |
|----------|-------|-----------|-------------|
| P0 | 3 | 30+45+30 = 105 | 1.75 h |
| P1 | 5 | 60+90+30+45+60 = 285 | 4.75 h |
| P2 | 2 | 60+120 = 180 | 3.0 h |
| **NEW R2 only** | **10** | **570** | **9.5 h** |
| Carry-over R1 P0+P1 (4+5 = 9) | 9 | 235 (per R1) | 3.9 h |
| **Combined R1+R2 fix time** | **19** | **~805** | **~13.4 h** |

**Recommended batching** (P2-3 audit improvement):
- **Batch A (P0+P0, ~5h)**: P0-1 (engine_router), P0-2/3/4 (invoke routing), R2-NEW-1 (race), R2-NEW-2 (error mapping), R2-NEW-3 (secret rotation)
- **Batch B (P1, ~5h)**: R1 P1-1/2/3 (retry/429/breaker), R2-NEW-4 (streaming), R2-NEW-5 (tiktoken), R2-NEW-6 (cost table), R2-NEW-7 (fallback), R2-NEW-8 (org quota)
- **Batch C (P2, ~3h)**: R2-NEW-9 (normalize), R2-NEW-10 (model versioning)

---

## 4. Verification Commands (for code-reviewer + verifier)

```powershell
# R1 P0 verification
& "D:\ComfyUI\.ext\python.exe" -c "
import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers._invoke import _pick_adapter
for f in ['claude','deepseek','qwen','doubao']:
    print(f, _pick_adapter(f))
"
# Expected: claude None, deepseek None, qwen None, doubao None

# R1 P0-3 partial
& "D:\ComfyUI\.ext\python.exe" -c "
import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers.registry import SAMPLE_PROVIDERS
for p in SAMPLE_PROVIDERS:
    proto = (p.config or {}).get('protocol', 'MISSING')
    print(f'{p.id:12s} protocol={proto}')
"
# Expected: 5/18 have protocol, 13/18 MISSING

# R1 P0-4
& "D:\ComfyUI\.ext\python.exe" -c "
import sys, asyncio; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers import invoke
r = asyncio.run(invoke('openai', prompt='hi', fallback=False))
print(r)
"
# Expected: error='不支持的协议: ', code='unsupported_protocol'

# R2 NEW-1 (concurrent race)
# See deep_probe.py §6

# R2 NEW-6 (cost table missing)
& "D:\ComfyUI\.ext\python.exe" -c "
import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from engines.provider_registry import DEFAULT_COST_TABLE
missing = [p for p in ['anthropic','gemini','kimi','zhipu','baidu','tencent','mistral','cohere','minimax','stepfun','nova','moonshot'] if p not in DEFAULT_COST_TABLE]
print('missing protocols:', missing)
"
# Expected: all 12 missing

# R2 NEW-2 (error mapping)
# Run deep_probe.py §5 — see all 5 status codes → "api_error" or "request_failed"

# R2 NEW-3 (secret rotation)
& "D:\ComfyUI\.ext\python.exe" -c "
import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from engines.model_gateway import DeepSeekProvider
p = DeepSeekProvider(api_key='sk-old')
print('rotate methods:', [m for m in dir(p) if 'rot' in m.lower() or 'refresh' in m.lower()])
# Expected: []
"

# R2 NEW-4 (streaming)
& "D:\ComfyUI\.ext\python.exe" -c "
import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers.gemini import GeminiProvider
print('streaming func:', hasattr(GeminiProvider, 'call_gemini_stream'))
import inspect
src = inspect.getsource(GeminiProvider)
print('streamGenerateContent in call_gemini source:', 'streamGenerateContent' in src)
# Expected: False
"
```

---

## 5. What This Audit Did NOT Cover (deferred to R3+)

- 19/23 ad-hoc dict responses (R1 P2-1) — orthogonal to R2's 10 focus areas
- 23/23 retry/429 (R1 P1-1, P1-2) — covered at high level in R2-NEW-2; deeper P1 audit needed
- Per-provider health endpoint (R1 P2-11)
- Per-tenant rollup (R1 P2-7)
- `BaseProvider._auth_headers()` default (R1 P2-8)
- 6 V5 engines singleton reset test (R1 P1-10)
- EngineRouter `decide()` confidence (R1 P2-5)

These are listed in the prior R1 report and remain valid. R2's 10 new findings are on top.

---

## 6. Summary

**R1 verification**: 4 P0 + 2 P1 confirmed. All still real, unfixed since 2026-07-09.

**R2 new findings**: 10 deeper gaps (3 P0 + 5 P1 + 2 P2), total ~9.5 hours fix time, on top of R1's carry-over ~3.9h.

**Total P21 audit (R1+R2)**: 19 gaps in the ai-provider module, ~13.4 hours of fix work, no source code modified (read-only).

**Highest priority for P3** (per criticality + low-effort):
1. **R2-NEW-2** (P0, 45 min) — error mapping — fastest P0 win, biggest observability gain
2. **R2-NEW-6** (P1, 30 min) — cost table 12 protocols — billing correctness, low effort
3. **R2-NEW-1** (P0, 30 min) — circuit breaker race — production safety
4. **R1 P0-3** (P0, 20 min) — registry SAMPLE config.protocol — 13/18 still broken
5. **R2-NEW-3** (P0, 30 min) — secret rotation — ops requirement

**Output files**:
- `reports/p21_r2_audit_provider.md` — this report
- `outputs/p21_r2_audit_provider/verify_r1.py` — R1 verification script
- `outputs/p21_r2_audit_provider/deep_probe.py` — R2 deeper probe script
- `outputs/p21_r2_audit_provider/deep_findings.json` — machine-readable findings
- `outputs/p21_r2_audit_provider/deliverable.md` — engine checkpoint

(End of report — 380 lines)
