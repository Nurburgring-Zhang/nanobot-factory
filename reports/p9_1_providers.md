# P9-1 — 5 Provider 深度审计

**范围**: nanobot-factory 接入的 5+ Provider 全景 + 配置 + 限流 + 熔断 + 错误码
**文件**: `backend/imdf/engines/provider_registry.py` (1091 lines) + `model_gateway.py` (783 lines)
**测试**: `tests/test_provider_registry.py` 21/21 PASS, `tests/test_p2_3_w2_ai_provider.py` 29/29 PASS

---

## 1. Provider 总览

### 1.1 双网关架构

```
                   ┌───────────────────────────────┐
                   │  application code (RAG/Agent) │
                   └─────────┬─────────────────────┘
                             │
                ┌────────────┴────────────┐
                ▼                         ▼
       provider_registry.py       model_gateway.py
       (P2-3-W2, 1091 行)          (F0.3, 783 行)
       ⭐ 首选入口                  备用入口
                │                         │
    ┌─────┬─────┼─────┬─────┐    ┌─────┬─────┬─────┬─────┐
    │     │     │     │     │    │     │     │     │     │
   OAI  MS   Vole Comfy Jimeng DeepSeek OAI Ant Google Zhipu
   Comp                              (5 类)
   (5 协议)
```

### 1.2 provider_registry 5 协议详解

| Protocol | 入口函数 | 默认 baseUrl | 默认模型 | 协议特点 |
|----------|---------|-------------|---------|---------|
| **openai-compatible** | `call_openai_compatible()` | (用户自填) | 无默认 | OpenAI 兼容协议, 适配 Claude/DeepSeek/混元等 |
| **modelscope** | `call_openai_compatible()` 复用 | `api-inference.modelscope.cn/v1` | Qwen3-235B / Qwen-Image-2512 / Z-Image-Turbo | OpenAI 兼容 + LoRA 配置 |
| **volcengine** | `call_volcengine()` | `ark.cn-beijing.volces.com/api/v3` | Doubao seed / seedream / seedance | 方舟 Ark, video 走 `/contents/generations/video` |
| **comfyui** | `call_comfyui()` | `http://127.0.0.1:8188` | 任意 workflow | 本地 HTTP, `/prompt` 提交 workflow JSON |
| **jimeng-cli** | `call_jimeng_cli()` | (本地可执行) | seedream-4.7 / 5.0 / jimeng-image-4k | 子进程调用, 路径回传 |

### 1.3 默认模型清单 (provider_registry)

```python
# engines/provider_registry.py:47-69
DEFAULT_MODELSCOPE_IMAGE_MODELS = [
    "Tongyi-MAI/Z-Image-Turbo", "Qwen/Qwen-Image-2512",
    "Qwen/Qwen-Image-Edit-2511", "black-forest-labs/FLUX.2-klein-9B",
]
DEFAULT_MODELSCOPE_CHAT_MODELS = [
    "Qwen/Qwen3-235B-A22B", "Qwen/Qwen3-VL-235B-A22B-Instruct",
    "MiniMax/MiniMax-M2.7:MiniMax",  # 注意: 引用了一个明显非真实模型
]
DEFAULT_VOLC_IMAGE_MODELS = ["doubao-seedream-4-0-250828"]
DEFAULT_VOLC_VIDEO_MODELS = [
    "doubao-seedance-2-0-260128", "doubao-seedance-2-0-fast-260128",
    "doubao-seedance-1-5-pro-251215", "doubao-seedance-1-0-pro-250528",
    "doubao-seedance-1-0-lite-t2v-250428", "doubao-seedance-1-0-lite-i2v-250428",
]
DEFAULT_VOLC_CHAT_MODELS = ["doubao-seed-1-6-250615"]
DEFAULT_JIMENG_IMAGE_MODELS = [
    "seedream-4.7", "seedream-4.6", "seedream-4.5", "seedream-5.0",
    "jimeng-image-2k", "jimeng-image-4k",
]
DEFAULT_JIMENG_VIDEO_MODELS = [
    "seedance2.0fast_vip", "seedance2.0_vip", "seedance2.0fast",
    "seedance2.0", "jimeng-video-720p", "jimeng-video-1080p",
]
```

### 1.4 model_gateway 5 Provider 类

```python
# engines/model_gateway.py
class ModelProvider(ABC):
    """Abstract base for all providers"""

class DeepSeekProvider(ModelProvider):
    """DeepSeek API — deepseek-chat / deepseek-reasoner"""

class OpenAIProvider(ModelProvider):
    """OpenAI native SDK — gpt-4o / gpt-4-turbo / gpt-4o-mini"""

class AnthropicProvider(ModelProvider):
    """Anthropic native — claude-3-5-sonnet / claude-3-opus / claude-3-haiku"""

class GoogleProvider(ModelProvider):
    """Google AI Studio — gemini-1.5-pro / gemini-1.5-flash"""

class ZhipuProvider(ModelProvider):
    """Zhipu GLM — glm-4-plus / glm-4-flash"""

class ModelGateway:
    """Multi-model gateway with auto-routing + fallback + circuit breaker"""
```

---

## 2. 调用流程 (call_provider_smart)

### 2.1 主入口

```python
# engines/provider_registry.py:975-1091
async def call_provider_smart(
    provider: Dict, payload: Dict, kind: str = "chat",
    *, user_id: str = "anonymous", org_id: str = "", record_usage: bool = True,
) -> Dict:
    """生产入口 — 自动: 限流 → 熔断 → mock → 调用 → 审计 → 用量"""
    pid = provider.get("id", "unknown")
    start_ms = int(time.time() * 1000)

    # 1. 限流 (env AI_RATE_LIMIT_PER_HOUR, 默认 1000)
    allowed, _ = rate_limit(user_id, pid)
    if not allowed:
        # 记录 error, 返回 rate_limited
        ...

    # 2. 熔断 (process-global CircuitBreaker)
    if not _GLOBAL_BREAKER.allow(pid):
        return {"ok": False, "code": "circuit_open", ...}

    # 3. mock 降级 (无 apiKey + comfyui 无实例)
    needs_key = protocol in ("openai-compatible", "modelscope", "volcengine")
    has_key = bool(apiKey)
    if needs_key and not has_key:
        result = await _mock_provider(provider, payload, kind)
    elif protocol == "comfyui":
        result = await _mock_provider(...) if not instances else await call_provider(...)
    else:
        result = await call_provider(provider, payload, kind)

    # 4. 熔断更新
    _GLOBAL_BREAKER.record(pid, bool(result.get("ok")))

    # 4.5 audit_chain 记录 (HMAC 签名)
    try:
        from engines.audit_chain import get_chain
        _chain.append(timestamp, method="AI_PROVIDER",
                      path=f"/ai/{protocol}/{pid}/{kind}",
                      user=user_id, body_hash=sha256(...),
                      status_code=200 if ok else 500,
                      actor=f"provider={pid}")
    except Exception:
        pass  # audit 失败不阻塞主调用

    # 5. 用量记账
    try:
        from engines.usage_tracker import get_tracker
        get_tracker().record(user_id, org_id, pid, protocol, kind,
                            model, status, prompt_tokens, completion_tokens,
                            cost_usd, latency_ms, error_code, error_message)
    except Exception:
        pass

    result.setdefault("provider_id", pid)
    return result
```

### 2.2 Provider Adapter 详解

#### 2.2.1 OpenAI 兼容协议 (call_openai_compatible)

```python
async def call_openai_compatible(provider, payload, kind="chat"):
    base = provider.get("baseUrl", "")
    api_key = provider.get("apiKey", "")
    if not base:
        return {"ok": False, "code": "missing_base_url", "error": "Base URL 为空"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if kind == "chat":
        model = payload.get("model", chatModels[0] or "gpt-4o")
        endpoint = f"{base}/chat/completions"
        body = {"model": model, "messages": payload.get("messages", [])}
        if "temperature" in payload: body["temperature"] = payload["temperature"]
        if "max_tokens" in payload: body["max_tokens"] = payload["max_tokens"]
    elif kind == "image":
        endpoint = f"{base}/images/generations"
        body = {"model": model, "prompt": payload.get("prompt", ""), "n": payload.get("n", 1)}
    elif kind == "video":
        endpoint = f"{base}/videos/generations" if "videos" in base else f"{base}/images/generations"
        body = {"model": model, "prompt": payload.get("prompt", ""), "n": payload.get("n", 1)}

    timeout_val = max(30, (payload.get("timeout_ms") or 120000) / 1000)
    async with httpx.AsyncClient(timeout=timeout_val) as client:
        resp = await client.post(endpoint, json=body, headers=headers)
        data = resp.json()
        if resp.status_code >= 400:
            return {"ok": False, "code": "api_error", "error": str(data)}
        return {"ok": True, "data": data}
```

#### 2.2.2 火山引擎 (call_volcengine)

```python
async def call_volcengine(provider, payload, kind="chat"):
    base = provider.get("baseUrl", DEFAULT_VOLC_BASE)
    api_key = provider.get("apiKey", "")
    if not api_key:
        return {"ok": False, "code": "missing_api_key", "error": "请先填写方舟 Ark API Key"}

    if kind == "chat":
        model = payload.get("model", defaults.get("chatModel", "doubao-seed-1-6"))
        endpoint = f"{base}/chat/completions"
        body = {"model": model, "messages": payload.get("messages", [])}
    elif kind == "image":
        endpoint = f"{base}/images/generations"
    elif kind == "video":
        endpoint = f"{base}/contents/generations/video"  # 火山专用 video endpoint
        body = {"model": model, "content": payload.get("prompt", "")}

    timeout_val = max(30, (payload.get("timeout_ms") or 3600000) / 1000)  # 视频 1h
    ...
```

#### 2.2.3 ComfyUI (call_comfyui)

```python
async def call_comfyui(provider, payload):
    instances = provider.get("comfyuiConfig", {}).get("instances", [])
    base = instances[0] if instances else provider.get("baseUrl", "http://127.0.0.1:8188")
    workflow = payload.get("workflowJson") or payload.get("workflow")
    prompt_text = payload.get("prompt", "")

    # 加载 workflow + 替换 CLIPTextEncode 节点的 text 字段
    wf = json.loads(workflow) if isinstance(workflow, str) else workflow
    for node_id, node in (wf or {}).items():
        if isinstance(node, dict):
            ct = str(node.get("class_type", "")).lower()
            if "cliptextencode" in ct and "text" in node.get("inputs", {}):
                node["inputs"]["text"] = prompt_text

    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(f"{base}/prompt", json={"prompt": wf})
        return {"ok": True, "prompt_id": data.get("prompt_id", "")}
```

#### 2.2.4 即梦 CLI (call_jimeng_cli)

```python
async def call_jimeng_cli(provider, payload, kind="image"):
    jc = provider.get("jimengConfig") or {}
    exe = jc.get("executablePath", "dreamina")
    use_wsl = jc.get("useWsl", False)
    model = payload.get("model", imageModels[0] or "seedream-4.7")
    cmd = [exe, "--model", model, "--prompt", prompt_text]
    if kind == "video":
        cmd.extend(["--mode", "video"])
    if payload.get("size"):
        cmd.extend(["--size", payload["size"]])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, shell=use_wsl)
    if result.returncode == 0:
        output_path = result.stdout.strip()
        if output_path and os.path.exists(output_path):
            return {"ok": True, "localPath": output_path,
                    "url": f"/imdf/media/output/{os.path.basename(output_path)}"}
        return {"ok": True, "message": output_path or "即梦 CLI 生成完成, 但未返回路径"}
    return {"ok": False, "error": result.stderr[:2000]}
```

---

## 3. API Key 轮换 + 限流 + 熔断 + 重试

### 3.1 API Key 轮换

❌ **未显式实现 key 轮换**, 但 provider 配置支持多 provider 切换 (用户可在 admin UI 配置多 provider 实现"轮换")。

**P1 建议**: 增加 `ProviderKeyPool` 类 — 同一 provider_id 配置 N 个 apiKey, 轮询 / 失败转移:
```python
class ProviderKeyPool:
    """Same provider, multiple keys — round-robin or fallback"""
    def __init__(self, keys: List[str], strategy: str = "round-robin"):
        self.keys = keys
        self.strategy = strategy

    def pick(self) -> str:
        if self.strategy == "round-robin":
            key = self.keys[self._idx % len(self.keys)]
            self._idx += 1
            return key
        elif self.strategy == "least-used":
            return min(self.keys, key=lambda k: self._usage[k])
```

### 3.2 限流 (RateLimiter)

```python
# engines/provider_registry.py:599-659
class RateLimiter:
    """Sliding window — process-internal, per (user_id, provider_id)"""

    def __init__(self, window_seconds: int = 3600):
        self.window_seconds = 3600
        self._buckets: Dict[Tuple[str, str], Deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, user_id: str, provider_id: str, per_hour: int) -> Tuple[bool, int]:
        """Returns (allowed, remaining). Records hit if allowed."""
        now = time.time()
        uid = str(user_id or "anonymous")[:60]
        pid = str(provider_id or "*")[:60]
        with self._lock:
            bucket = self._buckets.setdefault((uid, pid), deque())
            cutoff = now - self.window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False, 0
            bucket.append(now)
            return True, max(0, limit - len(bucket))

_GLOBAL_LIMITER = RateLimiter(window_seconds=3600)
```

**特性**:
- ✅ per user 隔离
- ✅ per provider 隔离
- ✅ env 配置 `AI_RATE_LIMIT_PER_HOUR=1000` 默认
- ❌ 多 worker 不共享 (进程内 dict)
- ❌ 无 per-org / per-tenant 配额
- ❌ 无 token-based 配额 (仅 request count)

### 3.3 熔断 (CircuitBreaker)

```python
# engines/provider_registry.py:787-883
class _CircuitState:
    """Single provider circuit state — sliding window + open/half-open"""

    def __init__(self, window_size=20, error_threshold=0.5, cooldown_seconds=30.0):
        self._calls: Deque[bool] = deque(maxlen=window_size)
        self._opened_at: Optional[float] = None

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if (time.time() - self._opened_at) >= self.cooldown_seconds:
                self._opened_at = None  # half-open
                self._calls.clear()
                return True
            return False

    def record(self, ok: bool) -> None:
        with self._lock:
            self._calls.append(bool(ok))
            if len(self._calls) < max(5, self.window_size // 2):
                return
            errors = sum(1 for x in self._calls if not x)
            if errors / len(self._calls) >= self.error_threshold and self._opened_at is None:
                self._opened_at = time.time()  # open!

class CircuitBreaker:
    """Process-internal circuit breaker — per provider"""

    def __init__(self, window_size=20, error_threshold=0.5, cooldown_seconds=30.0):
        self._states: Dict[str, _CircuitState] = {}

    def allow(self, provider_id: str) -> bool: ...
    def record(self, provider_id: str, ok: bool) -> None: ...
    def snapshot(self, provider_id=None) -> Dict: ...

_GLOBAL_BREAKER = CircuitBreaker()
```

**状态机**:
```
closed ──50% errors in window──> open ──30s cooldown──> half-open ──test──> closed|open
```

**特性**:
- ✅ per provider 独立
- ✅ 自动 open/half-open/closed 转换
- ✅ 数据不足 (calls < window_size/2) 不决策 — 防止启动期误判
- ❌ 进程内 state, 多 worker 不共享

### 3.4 重试 (Retry)

⚠️ **未显式 retry**, 仅 circuit breaker half-open 隐式重试 (cooldown 30s 后放行一次)。

**P1 建议**: 集成 `tenacity`:
```python
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True,
)
async def _call_with_retry(client, endpoint, body, headers):
    resp = await client.post(endpoint, json=body, headers=headers)
    resp.raise_for_status()
    return resp
```

或 httpx 自带 retry:
```python
client = httpx.AsyncClient(
    timeout=30,
    transport=httpx.AsyncHTTPTransport(retries=3),
)
```

---

## 4. 错误码映射

| 错误码 | 触发条件 | HTTP 语义 | 测试覆盖 |
|--------|---------|---------|---------|
| `missing_api_key` | volcengine/api_key 为空 | 401 Unauthorized | ✅ test_doubao_chat_missing_api_key |
| `missing_base_url` | openai-compatible baseUrl 为空 | 422 Unprocessable | (无显式测试) |
| `unsupported_protocol` | protocol 不在 SUPPORTED_PROTOCOLS | 400 Bad Request | ✅ test_call_provider_unsupported_protocol |
| `invalid_kind` | kind 不在 chat/image/video | 400 Bad Request | (无显式测试) |
| `api_error` | HTTP status >= 400 | 4xx/5xx Provider Response | ✅ test_http_5xx_returns_api_error |
| `request_failed` | 网络异常/超时 | 502 Bad Gateway | ✅ test_http_timeout_degrades_gracefully |
| `rate_limited` | RateLimiter 拒绝 | 429 Too Many Requests | ✅ test_rate_limit_blocks_excess |
| `circuit_open` | CircuitBreaker open | 503 Service Unavailable | ✅ test_circuit_breaker_opens_on_errors |
| `no_workflow` | ComfyUI 无 workflowJson | 400 Bad Request | ✅ test_comfyui_missing_workflow |
| `not_found` | 即梦 CLI 不存在 | 500 Internal | (无显式测试) |
| `timeout` | 即梦 CLI subprocess 超时 | 504 Gateway Timeout | (无显式测试) |

**统一返回结构**:
```python
{
    "ok": bool,
    "code": str,        # 错误码 (None on success)
    "error": str,       # 错误描述
    "data": dict,       # Provider 原始响应
    "provider_id": str, # 哪个 provider
    "mock": bool,       # 是否 mock 降级
    "cost_usd": float,  # 成本 (新增于 call_provider_smart)
    "usage_tokens": int, # 总 token (新增)
    "rate_limited": bool, # 是否触发限流
}
```

---

## 5. 测试覆盖矩阵 (50/50 PASS)

### 5.1 `tests/test_provider_registry.py` (21/21)

| TestClass | 测试 | 覆盖 |
|-----------|------|------|
| TestOpenAICompatible | test_openai_chat_success | openai gpt-4o chat mock HTTP 200 |
| TestOpenAICompatible | test_claude_via_openai_protocol | claude-3-5 通过 one-api 代理 |
| TestOpenAICompatible | test_deepseek_via_openai_protocol | deepseek-chat via OpenAI 协议 |
| TestModelScopeQwen | test_qwen_chat_success | qwen3-235b chat |
| TestModelScopeQwen | test_qwen_image_generation | Qwen-Image-2512 文生图 |
| TestVolcengineDoubao | test_doubao_chat_missing_api_key | 缺 key → missing_api_key |
| TestVolcengineDoubao | test_doubao_chat_success | doubao-seed chat mock |
| TestVolcengineDoubao | test_doubao_video_async_submit | doubao-seedance video 异步 |
| TestComfyUILocal | test_comfyui_submit_workflow_success | workflow 提交 + text 字段替换 |
| TestComfyUILocal | test_comfyui_missing_workflow | missing workflowJson |
| TestProviderRouting | test_call_provider_routes_by_protocol | 工厂路由 |
| TestProviderRouting | test_call_provider_unsupported_protocol | 错误码 |
| TestProviderIntegration | test_rate_limit_blocks_excess | env override 触发限流 |
| TestProviderIntegration | test_circuit_breaker_opens_on_errors | 90% error → open |
| TestProviderIntegration | test_no_apikey_degrades_to_mock | 无 key → mock |
| TestProviderIntegration | test_cost_metering_per_provider_model | gpt-4o vs mini vs volc vs local |
| TestProviderIntegration | test_retry_via_circuit_breaker_half_open | 冷却后半开放行 |
| TestProviderIntegration | test_http_timeout_degrades_gracefully | asyncio.TimeoutError |
| TestProviderIntegration | test_http_5xx_returns_api_error | HTTP 500 |
| TestProviderIntegration | test_usage_recorded_on_success | usage_tracker.record |
| TestProviderIntegration | test_audit_chain_records_provider_call | HMAC 签名 audit |

### 5.2 `tests/test_p2_3_w2_ai_provider.py` (29/29)

| TestClass | 测试数 | 覆盖 |
|-----------|-------|------|
| TestUsageTracker | 4 | record DB write / user_summary / org_summary / fallback jsonl |
| TestRateLimit | 4 | within / per-user / per-provider / env fallback |
| TestCostEstimate | 8 | 0 token / gpt-4o / deepseek / wildcard / unknown / dict / env override / local=0 |
| TestCircuitBreaker | 6 | default / below / above / allow false / reset / snapshot all |
| TestMockProvider | 4 | mock / call_provider_smart / rate limit / circuit |
| TestUsageEndpoint | 3 | /api/ai/usage 200 + /api/ai/circuit + /api/ai/cost/estimate |

---

## 6. 关键结论

| 维度 | 评级 | 备注 |
|------|------|------|
| Provider 覆盖 | **A** | 5 协议 + 5 SDK class, 涵盖 OpenAI/Claude/Qwen/Doubao/DeepSeek 等 |
| 默认模型覆盖 | **A-** | 28+ 默认模型, 但 Baidu/Tencent 需用户自定义 baseUrl |
| 调用流程 | **A** | 限流→熔断→mock→调用→audit→usage 单点驱动 |
| 限流 | **A-** | sliding window, 缺 Redis 跨 worker |
| 熔断 | **A** | 50% 错误率 + 30s cooldown + half-open |
| 重试 | **B-** | 仅 half-open 隐式重试, 缺 tenacity/httpx retry |
| 错误码 | **A** | 11 种错误码, 统一返回结构 |
| 测试覆盖 | **A** | 50/50 PASS, 覆盖 HTTP mock + 限流 + 熔断 + cost + audit |
| **综合** | **B+** | 商业级 ready, 缺 P0 streaming + P1 retry decor |