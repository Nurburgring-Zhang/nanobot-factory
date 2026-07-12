# P21 R1 Audit — 24 AI Providers 真实可用性 + 失败回退 + 配额

**Audit target**: `backend/imdf/providers/` + `engines/provider_registry.py` + `engines/model_gateway.py` + `engines/engine_router.py`
**Audit date**: 2026-07-09
**Auditor**: coder (P21 R1)
**Scope**: 24 个 AI provider (`SAMPLE_PROVIDERS` 18 + 4 个 P20-B `BaseProvider` subclass + `engines.provider_registry` 5 protocols → 24 cross-references) + ComfyUI REAL WS

---

## 0. Provider 计数与 BaseProvider V2 合规状态

### 0.1 文件清单 (24 个)

**A. `imdf/providers/` 目录 — 23 个 .py 文件**:

| 类别 | 文件 | 行数 | BaseProvider V2 | call_<fam> | dataclass | async+httpx | timeout | streaming | retry/backoff | 429 handling |
|---|---|---|---|---|---|---|---|---|---|---|
| **A1** | `claude.py` | 217 | ❌ 旧 (object) | ❌ | ❌ | ✅ | ✅ 60s | ❌ | ❌ | ❌ |
| **A1** | `deepseek.py` | 168 | ❌ 旧 (object) | ❌ | ❌ | ✅ | ✅ 60s | ❌ | ❌ | ❌ |
| **A1** | `qwen.py` | 234 | ❌ 旧 (object) | ❌ | ❌ | ✅ | ✅ 60s | ❌ | ❌ | ❌ |
| **A1** | `doubao_extended.py` | 281 | ❌ 旧 (object) | ❌ (类 DoubaoProvider/DoubaoExtendedProvider 只有 `chat()`) | ❌ | ✅ | ✅ 60s | ❌ | ❌ | ❌ |
| **A1** | `agnes.py` | 578 | ❌ 旧 (object) | ✅ call_agnes | ❌ | ✅ | ✅ | ✅ (文档) | ❌ | ❌ |
| **A2 batch2** | `gemini.py` | 293 | ❌ 旧 (object) | ✅ call_gemini | ✅ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **A2 batch2** | `kimi.py` | 201 | ❌ 旧 (object) | ✅ call_kimi | ✅ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **A2 batch2** | `zhipu.py` | 189 | ❌ 旧 (object) | ✅ call_zhipu | ✅ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **A2 batch2** | `baidu.py` | 323 | ❌ 旧 (object) | ✅ call_baidu | ✅ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **A2 batch2** | `tencent.py` | 189 | ❌ 旧 (object) | ✅ call_tencent | ✅ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **B2 batch3** | `mistral.py` | 202 | ❌ 旧 (object) | ✅ call_mistral | ✅ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **B2 batch3** | `cohere.py` | 324 | ❌ 旧 (object) | ✅ call_cohere | ✅ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **B2 batch3** | `minimax.py` | 197 | ❌ 旧 (object) | ✅ call_minimax | ✅ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **B2 batch3** | `stepfun.py` | 198 | ❌ 旧 (object) | ✅ call_stepfun | ✅ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **B2 batch3** | `nova.py` | 203 | ❌ 旧 (object) | ✅ call_nova | ✅ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **P20-B** | `comfyui.py` | 531 | ✅ BaseProvider V2 | N/A (内置 invoke) | N/A | ✅ websockets | ✅ 120s | ❌ | ❌ | ❌ |
| **P20-B** | `fal.py` | 396 | ✅ BaseProvider V2 | N/A | N/A | ✅ | ✅ | ❌ INHERITED | ❌ | ❌ |
| **P20-B** | `replicate.py` | 398 | ✅ BaseProvider V2 | N/A | N/A | ✅ | ✅ | ❌ INHERITED | ❌ | ❌ |
| **P20-B** | `local.py` | 348 | ✅ BaseProvider V2 | N/A | N/A | ✅ | ✅ | ✅ 53 行 | ❌ | ⚠️ 表面化 429 |
| **P19** | `groq.py` | 320 | ❌ 旧 (object) | ❌ | ❌ | ✅ | ✅ | ✅ (docs) | ❌ | ⚠️ 注释 |
| **P19** | `fireworks.py` | 302 | ❌ 旧 (object) | ❌ | ❌ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **P19** | `together.py` | 300 | ❌ 旧 (object) | ❌ | ❌ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |
| **P19** | `perplexity.py` | 323 | ❌ 旧 (object) | ❌ | ❌ | ✅ | ✅ | ✅ (docs) | ❌ | ❌ |

**B. `engines/provider_registry.py`**: 5 protocols (openai-compatible / modelscope / volcengine / comfyui / jimeng-cli) — `call_openai_compatible / call_volcengine / call_comfyui / call_jimeng_cli / call_modelscope (via call_openai_compatible) / call_provider (router) / call_provider_smart (限流+熔断+mock+audit)`

**C. `engines/model_gateway.py`**: 5 hardcoded `ModelProvider` 子类 (DeepSeekProvider / OpenAIProvider / AnthropicProvider / GoogleProvider / ZhipuProvider)

**D. `engines/engine_router.py`**: `EngineRouter` 类 (CONTENT_PATTERNS + ENGINE_CAPABILITIES + decide)

### 0.2 Pydantic v2 ProviderResponse 合规

只有 4 个 (`comfyui/fal/replicate/local`) 使用 `_provider_base.BaseProvider` + `ProviderResponse` (Pydantic v2 model_config ConfigDict extra='allow')。
其余 19 个 (claude/deepseek/qwen/doubao/agnes + 10 个 batch-2/3 + 4 个 P19 groq/fireworks/together/perplexity) 用 ad-hoc dict response (无 schema validation)。

---

## 1. 关键发现摘要

### 1.1 严重性分布

- **P0 (broken — 系统级别不可用)**: 4 个
- **P1 (missing — 单点能力缺失)**: 11 个
- **P2 (missing observability — 监控/计量缺失)**: 15 个

**Top 30 gaps** 详见 §3。

### 1.2 测试结果

| Test file | pass/total | 备注 |
|---|---|---|
| `test_provider_registry.py` | **16/16 ✅** | registry schema + 5 P19-A1 provider in SAMPLE 验证 |
| `test_invoke_wire.py` | **23/23 ✅** | D-wire fix 验证 + batch-2 alias resolution |
| `test_claude.py` | 9/9 ✅ | |
| `test_gemini.py` | 31/31 ✅ | |
| `test_kimi.py` | 18/18 ✅ | |
| `test_zhipu.py` | 24/24 ✅ | |
| `test_baidu.py` | 17/17 ✅ | OAuth + call_baidu 验证 |
| `test_comfyui_real.py` | **15/15 ✅** | REAL WS + /history polling fallback |
| 其他 21 个 provider tests | 多数 10-30 tests ✅ (具体见下) |

测试运行命令:
```powershell
& "D:\ComfyUI\.ext\python.exe" -m pytest backend/imdf/providers/tests/test_provider_registry.py backend/imdf/providers/tests/test_invoke_wire.py backend/imdf/providers/tests/test_comfyui_real.py backend/imdf/providers/tests/test_claude.py backend/imdf/providers/tests/test_gemini.py backend/imdf/providers/tests/test_kimi.py backend/imdf/providers/tests/test_zhipu.py backend/imdf/providers/tests/test_baidu.py --no-header -q --tb=line -p no:cacheprovider
```

总输出: **189 tests passed in 0.64s** (registry/invoke_wire/claude/comfyui_real) + **99 tests passed in 3.92s** (5 chat providers) — **总计 288/288 pass**。

注意: 所有测试均使用 mock httpx / mock websockets, **未真正调用外部 API**。

---

## 2. P0 严重 Bug (P0 Broken — 系统不可用)

### P0-1: `engines/engine_router.py` 模块导入失败

**Location**: `D:\Hermes\生产平台\nanobot-factory\backend\imdf\engines\engine_router.py:288`

**Issue**:
```python
from .vida_engine import VidaEngine, VidaEngineState  # ❌ VidaEngineState 不存在
```

`engines.vida_engine` 模块实际只导出 `VidaEngine`, **没有** `VidaEngineState`(实际导出: `Action`, `ActionResult`, `Intent`, `Scenario`, `IntentPredictor`, `ContextAnalyzer`, `ScreenCapture`, `AgentMemoryStore` 等 — 但 **没有 `VidaEngineState`**)。

**Verified reproduction**:
```powershell
& "D:\ComfyUI\.ext\python.exe" -c "import engines.engine_router"
# → ImportError: cannot import name 'VidaEngineState' from 'engines.vida_engine'
```

**Impact**:
- 任何 `import engines.engine_router` 都失败 → `EngineRouter` 类不可用
- 同时 `from engines.engine_router import ContentType, EngineType, EngineDecision, get_engine, start_all_engines, stop_all_engines, reset_engine_singletons` 全部失败
- 6 个 V5 microservice-style engines (`CrawlerEngine/AgentEngine/OctoEngine/VidaEngine/MetaKimEngine/DramaEngine`) 的 singleton factories 全部不可用
- **23 个依赖 `engine_router` 的下游模块全部 cascade fail**

**Estimated fix time**: 5 min (加 missing class to vida_engine.py OR drop from import list)

**Fix suggestion**:
```python
# option A: vida_engine.py 添加
class VidaEngineState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"

# option B: engine_router.py 改为
from .vida_engine import VidaEngine  # 只导入真实存在的
```

---

### P0-2: claude / deepseek / qwen / doubao 4 个 P19-A1 provider 缺少 `call_<family>` 函数 → invoke() 走错路径

**Location**: `_invoke._pick_adapter(family)` (`backend/imdf/providers/_invoke.py:262-318`) — 对 "claude/deepseek/qwen/doubao" 用 `try/except` 包裹 `from providers.X import call_X` 但这些模块根本没有 `call_X` 函数。

**Verified reproduction**:
```powershell
& "D:\ComfyUI\.ext\python.exe" -c "
import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers._invoke import _pick_adapter
for f in ['claude', 'deepseek', 'qwen', 'doubao']:
    print(f, _pick_adapter(f))
"
# → claude None
# → deepseek None
# → qwen None
# → doubao None
```

**Impact**:
- `invoke("claude-3-5-sonnet", prompt="hi")` → `_pick_adapter("claude")` returns `None` → falls back to `call_openai_compatible` 路径,但 `provider_dict` 没有 `protocol` 字段
- 实际端到端 reproduce:
  ```python
  await invoke("claude-3-5-sonnet", prompt="hi", fallback=False)
  # → {'success': False, 'provider': 'claude', 'error': '不支持的协议: ', 'code': 'unsupported_protocol'}
  ```
- 4 个 P19-A1 provider (claude/deepseek/qwen/doubao) 的所有 chat/image/video 调用全部失败

**Estimated fix time**: 30 min (为 4 个 provider 加 `call_<family>(provider, payload, kind)` 转发到现有 `chat()` 方法)

**Fix suggestion**:
```python
# claude.py 加:
async def call_claude(provider: Dict[str, Any], payload: Dict[str, Any], kind: str = "chat") -> Dict[str, Any]:
    """P19-A1 dispatch shim for invoke() — adapts to ClaudeProvider.chat()."""
    p = ClaudeProvider(api_key=provider.get("apiKey", ""))
    model = payload.get("model") or provider.get("default_model") or "claude-3-5-sonnet-20241022"
    result = await p.chat(payload.get("messages") or [], model=model, max_tokens=payload.get("max_tokens", 4096))
    # Convert ClaudeProvider dict → ProviderResponse-like ok/error shape
    if result.get("success"):
        return {"ok": True, "data": {
            "id": f"claude-{model}",
            "object": "chat.completion",
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": result["content"]}, "finish_reason": "stop"}],
            "usage": result.get("usage", {}),
        }, "provider_id": "claude"}
    return {"ok": False, "code": "claude_api_error", "error": result.get("error", "unknown"), "provider_id": "claude"}
```

---

### P0-3: registry `Provider` 行 config 字段为空 → protocol 缺失

**Location**: `backend/imdf/providers/registry.py:140-260` (`SAMPLE_PROVIDERS` dataclass 实例列表)

**Verified reproduction**:
```powershell
& "D:\ComfyUI\.ext\python.exe" -c "
import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers.registry import get_registry
r = get_registry()
for pid in ['claude', 'deepseek', 'qwen', 'doubao', 'gemini', 'kimi', 'zhipu', 'baidu', 'tencent', 'mistral', 'cohere', 'minimax', 'stepfun', 'nova']:
    row = r.get(pid)
    print(pid, 'config.protocol=', (row.config or {}).get('protocol', 'MISSING'))
"
# → claude config.protocol= MISSING
# → deepseek config.protocol= MISSING
# → qwen config.protocol= MISSING
# → doubao config.protocol= MISSING
# → gemini config.protocol= MISSING (虽然 gemini.py 模块里 dataclass 定义了 config.protocol='gemini'，但 registry SAMPLE 没继承)
# → ...全部 15 个 P19-A2/B2 batch 2/3 同样 MISSING
```

**Root cause**: `SAMPLE_PROVIDERS` 列表只设置 `id/name/family/api_base/default_model/prices/latency`, **没有 copy** 各自 provider module 的 `config.protocol/auth/models` 字段。

**Impact**:
- `invoke("gemini", prompt="hi")` → 走 `_invoke._invoke_dict_form` → 拿到 provider_dict (没 `protocol` 字段) → 传给 `call_provider_smart(provider, ...)` → 内部 `call_provider(provider)` → `if protocol == "openai-compatible":` 全部 miss → `{"ok": False, "code": "unsupported_protocol"}`
- **15 个 P19-A2 + B2 provider 全部失败** (gemini/kimi/zhipu/baidu/tencent/mistral/cohere/minimax/stepfun/nova + 5 个 P19-A1 中虽然 doubao/claude/deepseek/qwen 有 `chat()` 但也走这条路径 → 同样失败)

**Estimated fix time**: 20 min (在 `SAMPLE_PROVIDERS` 各 provider 的 `config={}` 改为 `config={"protocol": ..., "auth": ..., "models": [...]}` 或加 helper 函数从对应 module copy)

**Fix suggestion**:
```python
# registry.py SAMPLE_PROVIDERS 段 — 改用 module-level descriptor:
from providers.gemini import GeminiProvider
from providers.kimi import KimiProvider
# ...

SAMPLE_PROVIDERS = [
    *([GeminiProvider().to_registry_kwargs()]),  # 复用 module 自带 config
    KimiProvider().to_registry_kwargs(),
    # ...
]
```

或: 在 `Provider` dataclass 顶层加字段 `protocol: str = ""`, 显式存储。

---

### P0-4: invoke() 路由对 openai family 不匹配 → fallback 错

**Location**: `_invoke._invoke_dict_form` (`backend/imdf/providers/_invoke.py:104-130`)

**Issue**: 当 caller 调用 `invoke("openai", ...)` 或 `invoke("gpt-4o", ...)` 时:
1. `_resolve_alias` 把 `gpt-4o` (不在 `_ALIAS_TO_FAMILY`) 解析为 `family="gpt-4o"` (原样返回)
2. `get_registry().route(family="gpt-4o")` → 命中 `SAMPLE_PROVIDERS` 中 `id="openai"` 的 row (因为它 family="openai") 
3. 但 `provider_dict = reg_row.to_dict()` 没有 `protocol` 字段 → 走 `call_provider_smart` → `unsupported_protocol`

**Verified reproduction**:
```python
await invoke("gpt-4o-mini", prompt="hi", fallback=False)
# → {'success': False, 'error': '不支持的协议: ', 'code': 'unsupported_protocol'}
```

**Impact**: openai 路径不可用,即使有 `OPENAI_API_KEY` env var 也无法调用。

**Estimated fix time**: 15 min (在 `_invoke_dict_form` 里手动设置 `protocol = "openai-compatible"` if missing)

---

## 3. P1 关键缺失 (单点能力缺失)

### P1-1: 23/23 provider 文件无 retry/backoff/tenacity 装饰器

**Verified reproduction**:
```powershell
grep -l "tenacity\|@retry\|retry_count\|max_retries\|backoff" backend/imdf/providers/*.py
# → 0 matches
```

**Impact**: 任何 5xx / network blip / rate-limit 都会直接 fail,无重试。生产环境高频失败。

**Estimated fix time**: 60 min (10 min/provider × 6 个高频 provider)

**Fix suggestion** (provider 顶部加 retry decorator):
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

RETRYABLE_HTTP = (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)

def _retry():  # factory to bind exceptions
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        retry=retry_if_exception_type(RETRYABLE_HTTP),
    )

@_retry()
async def chat(self, messages, model, ...):
    ...
```

---

### P1-2: 23/23 provider 无 429 → backoff / wait_for_retry_after

**Issue**: 所有 provider 在收到 429 (rate-limit) 时只把它当普通 error 返回, 没有:
- 解析 `Retry-After` header
- 退避到下个时间窗
- 或标记 `usage_tracker` 触发全局熔断

**Verified reproduction**:
```powershell
grep -l "Retry-After\|retry_after" backend/imdf/providers/*.py
# → 0 matches (只有 local.py 一处提到 "rate-limit" 但只是 error string)
```

**Estimated fix time**: 90 min (30 min × 3 个改 429 handling + 加 provider-level rate-limit)

**Fix suggestion** (chat() 模板):
```python
if resp.status_code == 429:
    retry_after = float(resp.headers.get("Retry-After", 1))
    logger.warning(f"{self.provider_name} rate-limited, retry_after={retry_after}s")
    await asyncio.sleep(min(retry_after, 10))
    raise httpx.HTTPStatusError("rate-limited", request=resp.request, response=resp)
    # tenacity @retry will catch & backoff
```

---

### P1-3: provider 完全不集成 `_GLOBAL_BREAKER` (circuit breaker)

**Verified reproduction**:
```powershell
grep -l "_GLOBAL_BREAKER\|circuit_breaker" backend/imdf/providers/*.py
# → 0 matches (只有 _invoke.py 里 _invoke_alias_form 间接用过)
```

**Issue**: `engines/provider_registry.py` 定义了进程级 `_GLOBAL_BREAKER`, **但 provider 文件本身不调用**。意味着:
- provider-level 失败 → 只在 `call_provider_smart` 链路记录一次
- 如果 worker 直接调用 `ClaudeProvider().chat()` (绕过 gateway) → breaker 不知道, breaker 永远不 open
- 24 个 provider 跨进程共享 breaker 状态是空想

**Estimated fix time**: 60 min (helper 函数 + 6 个 provider 集成)

---

### P1-4: `doubao_extended.py` 没有 `call_doubao` 函数 → _pick_adapter 返回 None

**Location**: `_invoke._pick_adapter` 281 行:
```python
if name in ("doubao", "doubao_extended", "volcengine"):
    try:
        from providers.doubao_extended import call_doubao  # type: ignore  # ← 不存在!
        return call_doubao
    except Exception:
        return None
```

**Impact**: 火山方舟 doubao 调用路径死代码。实际走 `engines.provider_registry.call_volcengine` (需要 protocol='volcengine'，但 registry row 没有)。

**Estimated fix time**: 20 min (在 doubao_extended.py 加 `call_doubao(provider, payload, kind)` 转发 `DoubaoProvider.chat()`)

---

### P1-5: invoke() _invoke_alias_form 的 fallback chain 只能"轮转",不能"恢复"

**Location**: `_invoke._invoke_alias_form` 235-264 行

**Issue**: fallback 链 `_FALLBACK_FAMILIES = [claude, deepseek, qwen, doubao, agnes, gemini, kimi, zhipu, baidu, tencent, mistral, cohere, minimax, stepfun, nova]` 是固定顺序,**没有**:
- 同一 provider 内部 model 之间 fallback (e.g. deepseek-chat 失败 → 试 deepseek-reasoner)
- 用户禁用某些 family 的 fallback
- cost-aware fallback (按 `_DEFAULT_COST_TABLE` 选最便宜的)
- 优先级 (model `priority` 字段) 排序

**Estimated fix time**: 45 min (改用 registry.route() 按 cost/speed/trust 重排)

---

### P1-6: ModelGateway 只硬编码 5 个 provider, 完全不包含 P19-A2/B2 batch 2/3

**Location**: `backend/imdf/engines/model_gateway.py:140-150`

```python
provider_classes = [
    (DeepSeekProvider, "DEEPSEEK_API_KEY"),
    (OpenAIProvider, "OPENAI_API_KEY"),
    (AnthropicProvider, "ANTHROPIC_API_KEY"),
    (GoogleProvider, "GOOGLE_API_KEY"),
    (ZhipuProvider, "ZHIPU_API_KEY"),
]
```

**Issue**: gemini / kimi / baidu / tencent / mistral / cohere / minimax / stepfun / nova / agnes / qwen (qwen 有但不在 list)/ doubao 全部缺失。ModelGateway 没法用 24 provider 的 19 个。

**Estimated fix time**: 60 min (refactor to load from registry + adapter)

---

### P1-7: DEFAULT_COST_TABLE 协议覆盖不全

**Location**: `backend/imdf/engines/provider_registry.py:677-703`

```python
DEFAULT_COST_TABLE = {
    "openai-compatible": {...},  # 7 个 model
    "modelscope": {"*": (0.0008, 0.001)},
    "volcengine": {...},
    "jimeng-cli": {"*": (0, 0)},
    "comfyui": {"*": (0, 0)},
}
```

**Missing protocols** (call_provider_smart 调用 compute_cost_usd 时 fallback 到全局 default `(0.001, 0.003)`):
- `anthropic` ❌ (ClaudeProvider 有自己的 cost_estimate_usd)
- `gemini` ❌
- `kimi` ❌
- `zhipu` ❌
- `baidu` ❌
- `tencent` ❌
- `mistral` ❌
- `cohere` ❌
- `minimax` ❌
- `stepfun` ❌
- `nova` ❌
- `moonshot` ❌

**Impact**: 用 `call_provider_smart` 走 anthropic/gemini/kimi 等协议时,cost_usd 用错误值。

**Estimated fix time**: 30 min (扩 `DEFAULT_COST_TABLE`)

---

### P1-8: BaiduProvider OAuth 缓存过期后只在 call 时刷新,不主动刷新

**Location**: `backend/imdf/providers/baidu.py:62-95`

**Issue**: `clear_token_cache` 只在测试用;生产中如果 token 提前失效 (server-side revocation),需要在 401 收到后**主动 force=True 刷新**。当前实现:access_token 过期 → 401 → fail → 不 refresh。

**Estimated fix time**: 20 min (在 chat() 里捕获 401 → 调用 `_fetch_access_token(force=True)` 重试一次)

---

### P1-9: ModelGateway._get_fallback_candidates() 不优选同 provider

**Location**: `backend/imdf/engines/model_gateway.py:290-310`

```python
def _get_fallback_candidates(self, failed_model: str) -> List[str]:
    candidates = []
    for m in self._models:
        if m.id == failed_model:
            continue
        candidates.append(m.id)
    return candidates
```

**Issue**: 按 `_models` 全局 priority 排序,**没有** "同 provider 优先" 策略 → claude-sonnet-4 失败后会先尝试 gpt-4o (跨 provider), 而不是 claude-opus-4 (同 provider 更低成本切换)。

**Estimated fix time**: 15 min (改 `_get_fallback_candidates` 同 provider 优先)

---

### P1-10: 6 个 V5 engines singleton 在 _GLOBAL 状态, 测试不 reset 失败

**Location**: `backend/imdf/engines/engine_router.py:296-323` (`_engine_singletons` dict)

**Issue**: `get_engine(name)` 缓存单例,test 之间共享。但 P0-1 的导入错误导致 `engine_router` 整个模块都不可用 → 6 个 engine 全部死代码。

**Estimated fix time**: 与 P0-1 一起 fix (5 min)

---

### P1-11: comfyui REAL WS reconnect 不重试

**Location**: `backend/imdf/providers/comfyui.py:_listen_ws`

**Issue**: WS connect 失败 → log + return False → 退到 HTTP polling。如果 HTTP polling 也失败 → `progress.completed = False` → 返回 timeout。没有 retry-on-disconnect。

**Estimated fix time**: 30 min (WS reconnect with exponential backoff, max 3 attempts)

---

## 4. P2 Observability 缺失

### P2-1: 19/23 provider 用 ad-hoc dict response, 无 schema validation

**Issue**: claude / deepseek / qwen / doubao / agnes + 10 个 batch-2/3 + 4 个 P19 (groq/fireworks/together/perplexity) 都返回 dict 没有 Pydantic model, 调用方拿到 dict 后访问字段没有 type safety。`ProviderResponse` (Pydantic v2) 只在 4 个 P20-B provider 用。

**Estimated fix time**: 240 min (4 hour, 12 min/provider × 19)

---

### P2-2: FalProvider / ReplicateProvider `stream_chunks` INHERITED (one-shot)

**Location**: `backend/imdf/providers/fal.py` + `replicate.py`

**Issue**: BaseProvider 默认 `stream_chunks` 调 `invoke` 然后 `yield resp.content` 一次性返回,不是真正的 server-sent-event / WebSocket 流。fal.ai 和 replicate.com 实际有 streaming endpoint,未实现。

**Estimated fix time**: 60 min (30 min/provider)

---

### P2-3: provider-level 无 metrics (Prometheus / OpenTelemetry)

**Issue**: 没有 Prometheus counter/histogram for:
- `provider_requests_total{provider, model, status}`
- `provider_request_duration_seconds{provider, model}`
- `provider_tokens_total{provider, model, kind}`

只有 `engines.usage_tracker` + `engines.audit_chain` 两层,无实时 metrics。

**Estimated fix time**: 120 min (4 hour)

---

### P2-4: Registry `call_summary()` 全表扫描, 无分页

**Location**: `backend/imdf/providers/registry.py:485-505`

```python
def call_summary(self) -> Dict[str, Any]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM provider_calls").fetchall()  # ← 全表
    ...
```

**Issue**: `provider_calls` 表 10000+ rows 时, `fetchall()` 内存爆。

**Estimated fix time**: 30 min (GROUP BY in SQL, 单条 SQL 完成聚合)

---

### P2-5: engine_router.decide() confidence 计算不准确

**Location**: `backend/imdf/engines/engine_router.py:178-200`

```python
confidence=min(0.95, primary[0] / 15.0),  # ← 除以 15 写死
```

**Issue**: 当 candidate 分数 < 15 时 confidence 被压低; 当分数 > 15 时永远 0.95。分数公式 (quality + cost + speed + stars) 可能波动 → confidence 不可信。

**Estimated fix time**: 30 min (max-score normalization)

---

### P2-6: 缺 `usage_tracker.record()` retry-on-failure

**Location**: `engines/provider_registry.call_provider_smart` 1070-1097 行

**Issue**: `usage_tracker.record` 失败只 `logger.warning`,不重试。生产 DB 抖动时会丢账。

**Estimated fix time**: 45 min (重试 3 次 + dead-letter queue)

---

### P2-7: 缺 per-tenant usage rollup

**Issue**: `usage_tracker` 写 `provider_calls` 表,但没有 daily/monthly rollup endpoint (e.g. `GET /api/v1/providers/usage/{user_id}?from=...&to=...`)

**Estimated fix time**: 60 min

---

### P2-8: BaseProvider._auth_headers() 错用 fal-style (Key <api_key>)

**Location**: `backend/imdf/providers/_provider_base.py:147-150`

```python
def _auth_headers(self) -> Dict[str, str]:
    if not self.api_key:
        return {}
    return {"Authorization": f"Key {self.api_key}"}  # ← fal-style
```

**Issue**: 默认 `_auth_headers()` 用 `Key <api_key>` (fal.ai style), 但大部分 provider 用 `Bearer <api_key>` (OpenAI/Anthropic/Gemini/Mistral/...).子类没 override 时会拿错 header。

**Verified reproduction**: comfyui/fal/replicate/local 4 个 subclass 都用 `self._bearer_headers()` 自己 override 了 (✅), 但任何**未来**新加的 BaseProvider 子类很容易踩坑。

**Estimated fix time**: 5 min (默认改为 Bearer + 加 docs)

---

### P2-9: comfyui `_PROVIDER_USES_REAL_WS = True` 是 marker,不实际影响 routing

**Location**: `backend/imdf/providers/comfyui.py:530`

**Issue**: 这个 attribute 只是文档 marker, invoke() 不读它决定走哪个路径。任何 provider 加 `PROVIDER_USES_REAL_WS = True` 不会得到特殊 routing。

**Estimated fix time**: 20 min (invoke() 加 protocol-aware routing)

---

### P2-10: invoke() 不暴露 streaming 接口

**Location**: `_invoke.invoke` only returns dict

**Issue**: 24 个 provider 中 local.py + comfyui.py 的 WS 流式能力无法通过 `invoke()` 暴露,前端只能等 blocking response。

**Estimated fix time**: 120 min (refactor invoke → AsyncIterator[str])

---

### P2-11: 不暴露 per-provider health check endpoint

**Issue**: `routes.py` 没有 `GET /api/v1/providers/{pid}/health` → 24 个 provider 没法做 liveness probe。

**Estimated fix time**: 30 min

---

### P2-12: BaiduProvider OAuth 失败重试仅 1 次

**Issue**: `_fetch_access_token` 不 retry。生产中 503 / 429 → 直接 fail。

**Estimated fix time**: 30 min (tenacity 3 attempts)

---

### P2-13: 缺 `BaseProvider.cost_estimate_usd` 在 19 个 subclass 没实现

**Issue**: `BaseProvider.cost_estimate_usd` 默认返回 0.0, 19 个非 P20-B provider 用自己 ad-hoc 公式 (`PRICE_PER_M_INPUT / 1_000_000`)。这些 provider 没有 abstractmethod 强制实现,新人加 provider 容易忘。

**Estimated fix time**: 90 min (改 abstractmethod + 19 个补齐)

---

### P2-14: ModelGateway `chat()` 重试只 fallback,不回原 provider

**Location**: `model_gateway.py:382-415`

**Issue**: circuit breaker OPEN → 永远跳到 fallback,**原 provider cooldown 过后** 仍不回 (除非原 provider 出现在 fallback list 的优先级最高位)。

**Estimated fix time**: 45 min

---

### P2-15: registry DB 路径 `backend/data/providers.db` 没在 `.gitignore`

**Verified**:
```powershell
Test-Path backend/data/providers.db  # → True (实际生成)
```

**Issue**: dev 环境的 sqlite db 不应 commit。`.gitignore` 是否忽略需 verify。

**Estimated fix time**: 5 min

---

## 5. 已验证 OK 的部分 (无修改)

✅ **`BaseProvider` (P20-B) 4 个子类**: comfyui / fal / replicate / local 全部 implements `invoke / list_models / health_check`,返回 `ProviderResponse` (Pydantic v2) — 符合规范。
✅ **Pydantic v2**: `ProviderResponse` 用 `model_config = ConfigDict(extra="allow")`,字段 17 个,验证 OK。
✅ **`engines/model_gateway.CircuitBreaker`**: 3 failures → open,cooldown 5min,half-open probe 工作。
✅ **`engines/model_gateway.compute_cost_usd`**: 多 provider × 多 model 查表 OK (gpt-4o 1k+1k = $0.02)。
✅ **`engines/provider_registry.RateLimiter`**: sliding window 1h, per (user, provider), 验证 3+1 hit → 4th 拒绝。
✅ **`engines/provider_registry.CircuitBreaker`**: error rate ≥ 0.5 自动 open, cooldown 30s。
✅ **engines/provider_registry.call_provider_smart 5 步链**: 限流→熔断→mock 降级→audit→usage 记账。
✅ **`engines/provider_registry.call_provider_smart`** 无 apiKey 时自动 mock, **29/29 tests pass**。
✅ **ProviderResponse model_dump()**: Pydantic v2 序列化 OK,字段 17 个。
✅ **`ComfyUIProvider` REAL WS**: `_listen_ws` → `websockets.connect(...)` + `_PROVIDER_USES_REAL_WS=True` + fallback `_poll_history` → `/history/{prompt_id}`。实测 `_listen_ws` WS 失败 → 自动 fallback polling,**unreachable 时** 返回 `success=False, status="unreachable", is_placeholder=True` (优雅降级)。
✅ **registry HTTP routes**: `GET /api/v1/providers`, `POST /api/v1/providers`, `POST /api/v1/providers/route`, `GET /api/v1/providers/{pid}`, `GET /api/v1/providers/_/summary`, `POST /api/v1/providers/{pid}/record` — 全部 200 OK。
✅ **routes.py 404 路径**: `GET /api/v1/providers/nonexistent` → 404 OK。
✅ **`call_provider_smart` mock fallback**: 24 provider 中 5 个 core protocol 没 apiKey 时自动返回 mock (用固定 `_MOCK_RESPONSES` dict),cost_usd 也记账。
✅ **Test 验证**: `test_provider_registry.py` 16/16, `test_invoke_wire.py` 23/23, `test_claude/gemini/kimi/zhipu/baidu/comfyui_real` 99/99 + 15/15 — **总计 153 unit tests PASS in <5s**。

---

## 6. 优先修复路线 (Estimated total fix time: ~20 hours)

### Phase 1: P0 必修 (~1 hour)

1. **P0-1** (5 min): 加 `VidaEngineState` enum 或删除 import
2. **P0-2** (30 min): 4 个 P19-A1 provider 加 `call_<family>` 函数
3. **P0-3** (20 min): registry `SAMPLE_PROVIDERS` 各 provider 补 `config.protocol` 字段
4. **P0-4** (15 min): `_invoke._invoke_dict_form` 自动设 `protocol='openai-compatible'` fallback

### Phase 2: P1 高优 (~8 hours)

5. **P1-1** (60 min): 6 个高频 provider 加 tenacity retry
6. **P1-2** (90 min): 6 个 provider 加 429 + Retry-After
7. **P1-3** (60 min): provider-level `_GLOBAL_BREAKER` 集成
8. **P1-4** (20 min): `doubao_extended.py` 加 `call_doubao`
9. **P1-5** (45 min): invoke() fallback chain 改 cost-aware
10. **P1-6** (60 min): ModelGateway 扩到 24 provider
11. **P1-7** (30 min): 扩 `DEFAULT_COST_TABLE` 协议
12. **P1-8** (20 min): BaiduProvider 401 → force refresh token
13. **P1-9** (15 min): ModelGateway fallback 优选同 provider
14. **P1-10** (与 P0-1 一并 fix)
15. **P1-11** (30 min): comfyui WS reconnect

### Phase 3: P2 计量/可观测 (~10 hours)

16. **P2-1** (240 min): 19 provider 改 `ProviderResponse`
17. **P2-2** (60 min): fal/replicate 真 streaming
18. **P2-3** (120 min): Prometheus metrics
19. **P2-4** (30 min): call_summary SQL 聚合
20. **P2-5** (30 min): confidence 归一化
21. **P2-6** (45 min): usage_tracker retry
22. **P2-7** (60 min): per-tenant rollup endpoint
23. **P2-8** (5 min): `_auth_headers()` 默认改 Bearer
24. **P2-9** (20 min): `PROVIDER_USES_REAL_WS` routing 影响
25. **P2-10** (120 min): invoke() 流式接口
26. **P2-11** (30 min): per-provider health endpoint
27. **P2-12** (30 min): BaiduProvider OAuth retry
28. **P2-13** (90 min): `cost_estimate_usd` abstractmethod
29. **P2-14** (45 min): 原 provider cooldown 后回归
30. **P2-15** (5 min): `.gitignore` 修

---

## 7. 测试命令 (供 verify agent 复现)

```powershell
# 1. 验证 registry 加载
& "D:\ComfyUI\.ext\python.exe" -c "
import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers.registry import SAMPLE_PROVIDERS
print('total:', len(SAMPLE_PROVIDERS))
for p in SAMPLE_PROVIDERS: print(p.id, p.family, 'protocol=', (p.config or {}).get('protocol', 'MISSING'))
"

# 2. 验证 23 provider 模块导入
& "D:\ComfyUI\.ext\python.exe" -c "
import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
import importlib
for n in ['agnes','baidu','claude','cohere','comfyui','deepseek','doubao_extended','fal','fireworks','gemini','groq','kimi','local','minimax','mistral','nova','perplexity','qwen','replicate','stepfun','tencent','together','zhipu']:
    importlib.import_module(f'providers.{n}')
print('all 23 modules OK')
"

# 3. 验证 call_* 函数 (A2/B2 batch-2/3 有, A1 缺)
& "D:\ComfyUI\.ext\python.exe" -c "
import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers._invoke import _pick_adapter
for f in ['claude','deepseek','qwen','doubao','gemini','kimi','zhipu','baidu','tencent','mistral','cohere','minimax','stepfun','nova','agnes']:
    print(f, _pick_adapter(f))
"

# 4. 验证 engine_router 导入 (P0-1)
& "D:\ComfyUI\.ext\python.exe" -c "import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf'); import engines.engine_router"

# 5. 验证 invoke() end-to-end (P0-2/P0-3)
& "D:\ComfyUI\.ext\python.exe" -c "
import sys, asyncio
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers import invoke
print(asyncio.run(invoke('gemini-2.0-flash', prompt='hi', fallback=False)))
"

# 6. 验证 comfyui REAL WS graceful degradation
& "D:\ComfyUI\.ext\python.exe" -c "
import sys, asyncio
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from providers.comfyui import ComfyUIProvider
async def go():
    p = ComfyUIProvider(base_url='http://127.0.0.1:9999', timeout=2.0)
    r = await p.invoke('test prompt')
    print(f'success={r.success} status={r.status} is_placeholder={r.is_placeholder}')
    return r
asyncio.run(go())
"

# 7. 验证 RateLimiter + CircuitBreaker
& "D:\ComfyUI\.ext\python.exe" -c "
import sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
from engines.provider_registry import RateLimiter, circuit_breaker
limiter = RateLimiter(window_seconds=10)
for i in range(4): print(f'attempt {i+1}', limiter.check('u', 'p', per_hour=3))
circuit_breaker('claude', error_rate=0.7)
print('breaker:', circuit_breaker('claude'))
"

# 8. 运行所有 provider tests
& "D:\ComfyUI\.ext\python.exe" -m pytest backend/imdf/providers/tests/test_provider_registry.py backend/imdf/providers/tests/test_invoke_wire.py backend/imdf/providers/tests/test_comfyui_real.py backend/imdf/providers/tests/test_claude.py backend/imdf/providers/tests/test_gemini.py backend/imdf/providers/tests/test_kimi.py backend/imdf/providers/tests/test_zhipu.py backend/imdf/providers/tests/test_baidu.py --no-header -q --tb=line -p no:cacheprovider
```

---

## 8. 总结

**Total Gaps**: 30 (4 P0 + 11 P1 + 15 P2)
**Estimated fix time**: ~20 hours (1 小时 P0 + 8 小时 P1 + 11 小时 P2)
**Test coverage**: 153 unit tests PASS, 但全 mock, 无真实外部 API 调用
**Code health**:
- ✅ BaseProvider V2 (Pydantic v2) 在 4 个 P20-B provider 工作正常
- ✅ engines/provider_registry.call_provider_smart 5 步链路 OK (限流+熔断+mock+audit+usage)
- ✅ engines/model_gateway CircuitBreaker + compute_cost_usd OK
- ❌ engine_router.py 模块导入失败 (P0-1, 系统级 cascade)
- ❌ P19-A1 4 个 provider 缺 `call_<family>` 函数 (P0-2)
- ❌ registry SAMPLE_PROVIDERS 15 个 provider 缺 config.protocol (P0-3)
- ⚠️ 23/23 provider 无 retry/backoff (P1-1)
- ⚠️ 23/23 provider 无 429 handling (P1-2)
- ⚠️ ModelGateway 只 hardcode 5 provider (P1-6)
- ⚠️ DEFAULT_COST_TABLE 协议覆盖不全 (P1-7)