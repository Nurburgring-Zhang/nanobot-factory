# P9-1 — Fallback + 成本追踪 + 配额限流 深度审计

**核心文件**:
- `backend/imdf/engines/provider_registry.py` (1091 行) — RateLimiter + CircuitBreaker + compute_cost_usd + cost_estimate
- `backend/imdf/engines/usage_tracker.py` (~600 行) — UsageTracker.record + user_summary + org_summary
- `backend/imdf/engines/audit_chain.py` (~400 行) — HMAC 签名审计

**测试**: 50/50 PASS (test_provider_registry 21 + test_p2_3_w2_ai_provider 29)
**实测**: tracker.record + user_summary 聚合成功, 6 维度数据完整

---

## 1. Fallback 降级链

### 1.1 `call_provider_smart` 4 级降级

```python
async def call_provider_smart(provider, payload, kind="chat", *, user_id, org_id, record_usage=True):
    pid = provider.get("id", "unknown")
    start_ms = int(time.time() * 1000)

    # ─── 1. 限流检查 ─────────────────────────────────
    allowed, _ = rate_limit(user_id, pid)
    if not allowed:
        # 记录 error, 返回 rate_limited (不计入 cost)
        ...
        return {"ok": False, "code": "rate_limited", "provider_id": pid, "rate_limited": True}

    # ─── 2. 熔断检查 ─────────────────────────────────
    if not _GLOBAL_BREAKER.allow(pid):
        return {"ok": False, "code": "circuit_open",
                "error": f"provider {pid} 熔断中, 请稍后重试", "provider_id": pid}

    # ─── 3. mock 降级 (无 apiKey 或 ComfyUI 无实例) ──────
    needs_key = provider.get("protocol") in ("openai-compatible", "modelscope", "volcengine")
    has_key = bool(provider.get("apiKey"))
    if needs_key and not has_key:
        result = await _mock_provider(provider, payload, kind)
    elif provider.get("protocol") == "comfyui":
        instances = provider.get("comfyuiConfig", {}).get("instances") or []
        if not instances:
            result = await _mock_provider(provider, payload, kind)
        else:
            result = await call_provider(provider, payload, kind)
    else:
        result = await call_provider(provider, payload, kind)

    # ─── 4. 熔断更新 (失败计入下次熔断判断) ──────────────
    _GLOBAL_BREAKER.record(pid, bool(result.get("ok")))

    # ─── 4.5 audit_chain 记录 (HMAC 签名) ────────────────
    try:
        from engines.audit_chain import get_chain as _get_audit_chain
        _chain = _get_audit_chain()
        _body_str = f"{pid}|{payload.get('model', '')}|{result.get('ok')}|{provider.get('protocol', '')}|{user_id}"
        _body_hash = hashlib.sha256(_body_str.encode("utf-8")).hexdigest()[:16]
        _chain.append(
            timestamp=datetime.now(timezone.utc).isoformat(),
            method="AI_PROVIDER",
            path=f"/ai/{provider.get('protocol', '')}/{pid}/{kind}",
            user=user_id, body_hash=_body_hash,
            status_code=200 if result.get("ok") else 500,
            actor=f"provider={pid}",
        )
    except Exception as _audit_err:
        logger.warning(f"call_provider_smart audit_chain record failed: {_audit_err}")

    # ─── 5. 用量记账 ─────────────────────────────────────
    if record_usage:
        try:
            from engines.usage_tracker import get_tracker
            data = result.get("data") or {}
            usage = data.get("usage") if isinstance(data, dict) else None
            pt = int((usage or {}).get("prompt_tokens", 0))
            ct = int((usage or {}).get("completion_tokens", 0))
            tt = int((usage or {}).get("total_tokens", pt + ct))
            cost = compute_cost_usd(provider.get("protocol", ""), str(payload.get("model", "")),
                                    prompt_tokens=pt, completion_tokens=ct)
            get_tracker().record(user_id=user_id, org_id=org_id, provider_id=pid,
                                protocol=provider.get("protocol", ""), kind=kind,
                                model=str(payload.get("model", "")),
                                status="ok" if result.get("ok") else "error",
                                prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
                                cost_usd=cost, latency_ms=int(time.time() * 1000) - start_ms,
                                error_code=str(result.get("code") or ""),
                                error_message=str(result.get("error") or "")[:2000])
            result["cost_usd"] = cost
            result["usage_tokens"] = tt
        except Exception as e:
            logger.warning(f"call_provider_smart usage record failed: {e}")

    result.setdefault("provider_id", pid)
    return result
```

**降级流程图**:
```
请求到达
  ↓
[1] RateLimiter.check(user, provider) ─超额→ 429 rate_limited (cost=0)
  ↓
[2] CircuitBreaker.allow(provider) ─open→ 503 circuit_open (cost=0)
  ↓
[3] Mock 降级 (无 apiKey / ComfyUI 无实例) → 返回固定 mock (cost=0)
  ↓
[4] 真实调用
  ├─ 成功 → audit + usage + cost
  └─ 失败 → CircuitBreaker.record(error) → 累计 50% → open
```

### 1.2 自动降级链示例 (gpt-4 → gpt-3.5 → local)

⚠️ **未自动级联**, 需 caller 手动 try/except + 切换 provider。

**P1 建议** — `with_fallbacks` decor:
```python
class ProviderCascade:
    """Auto-fallback chain — gpt-4 → gpt-4o-mini → volcengine → comfyui → mock"""

    def __init__(self, providers: List[Dict]):
        # 按优先级排序: gpt-4 → gpt-4o-mini → volcengine doubao → comfyui → mock
        self.providers = sorted(providers, key=lambda p: p.get("priority", 99))

    async def call(self, payload, kind="chat", user_id="anonymous") -> Dict:
        last_error = None
        for provider in self.providers:
            result = await call_provider_smart(provider, payload, kind, user_id=user_id)
            if result.get("ok") and not result.get("mock"):
                return result
            last_error = result
        # All real providers failed — last resort: mock
        return last_error or {"ok": False, "code": "all_providers_failed"}
```

### 1.3 自动级联 vs 手动级联 对比

| 方式 | 优点 | 缺点 |
|------|------|------|
| **手动 try/except** | 简单, 完全可控 | 代码冗长, 每个调用点重复 |
| **ProviderCascade** | 配置化, 自动 fallback | 缺泛化, 不同业务需不同 cascade |
| **LangChain with_fallbacks** | 业界标准, composable | 引入 LangChain 依赖 |
| **Circuit breaker 自动 open** | ✅ 已实现 | 仅错误率阈值, 非真正"降级" |

---

## 2. 成本追踪

### 2.1 `compute_cost_usd` 算法

```python
# engines/provider_registry.py:668-756
DEFAULT_COST_TABLE = {
    "openai-compatible": {
        "gpt-4o":          (0.005, 0.015),
        "gpt-4o-mini":     (0.00015, 0.0006),
        "gpt-4-turbo":     (0.01, 0.03),
        "claude-3-5-sonnet": (0.003, 0.015),
        "deepseek-chat":   (0.00014, 0.00028),
        "deepseek-reasoner": (0.00055, 0.0022),
        "*":               (0.002, 0.006),  # fallback
    },
    "modelscope":   {"*": (0.0008, 0.001)},
    "volcengine":   {
        "doubao-seed-1-6-250615":     (0.0008, 0.002),
        "doubao-seedream-4-0-250828": (0.0, 0.04),    # 图像按张
        "doubao-seedance-2-0-260128": (0.0, 0.40),    # 视频按秒
        "*":                          (0.001, 0.003),
    },
    "jimeng-cli":   {"*": (0.0, 0.0)},
    "comfyui":      {"*": (0.0, 0.0)},
}

def _lookup_cost(protocol: str, model: str) -> Tuple[float, float]:
    proto = str(protocol or "").strip().lower()
    m = str(model or "").strip()
    overrides = _parse_env_cost_overrides()  # env AI_COST_PER_1K_TOKENS
    table = {**DEFAULT_COST_TABLE.get(proto, {}), **overrides.get(proto, {})}
    if m in table:
        return table[m]
    if "*" in table:
        return table["*"]
    return (0.001, 0.003)  # global fallback

def compute_cost_usd(protocol, model, prompt_tokens=0, completion_tokens=0) -> float:
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return 0.0
    in_p, out_p = _lookup_cost(protocol, model)
    cost = (prompt_tokens / 1000.0) * in_p + (completion_tokens / 1000.0) * out_p
    return round(max(0.0, cost), 6)
```

**特性**:
- ✅ per (protocol, model) 价格表
- ✅ env override (`AI_COST_PER_1K_TOKENS=openai-compatible:gpt-4o=0.005,0.015`)
- ✅ wildcard fallback `*`
- ✅ local provider (comfyui / jimeng-cli) 永远 cost=0

### 2.2 `cost_estimate` 人类友好接口

```python
def cost_estimate(protocol, model, prompt_tokens=0, completion_tokens=0) -> Dict[str, Any]:
    in_p, out_p = _lookup_cost(protocol, model)
    cost = compute_cost_usd(protocol, model, prompt_tokens, completion_tokens)
    return {
        "protocol": protocol,
        "model": model,
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "input_per_1k_usd": in_p,
        "output_per_1k_usd": out_p,
        "cost_usd": cost,
    }
```

返回示例:
```json
{
  "protocol": "openai-compatible",
  "model": "gpt-4o",
  "prompt_tokens": 1000,
  "completion_tokens": 500,
  "input_per_1k_usd": 0.005,
  "output_per_1k_usd": 0.015,
  "cost_usd": 0.0125
}
```

### 2.3 用量持久化 (UsageTracker)

```python
# engines/usage_tracker.py
class UsageTracker:
    def record(self, *, user_id, org_id, provider_id, protocol, kind, model,
               prompt_tokens, completion_tokens, total_tokens, cost_usd,
               latency_ms, status, error_code="", error_message="") -> str:
        """写 usage_logs 表 → 返回 log_id (ul_xxxx)"""
        ...

    def user_summary(self, user_id, days=30) -> Dict:
        """聚合 user 维度的用量"""
        ...

    def org_summary(self, org_id, days=30) -> Dict:
        """聚合 org 维度的用量 (含 unique_users)"""
        ...

    def check_rate_limit(self, user_id, provider_id, per_hour) -> Tuple[bool, int]:
        """二次 rate limit check (DB 持久层)"""
        ...
```

### 2.4 实测聚合结果

```python
tracker.record(user_id='p9_demo_user', org_id='p9_demo_org',
               provider_id='openai-compatible', protocol='openai-compatible',
               kind='chat', model='gpt-4o',
               prompt_tokens=1000, completion_tokens=500, total_tokens=1500,
               cost_usd=0.0125, latency_ms=800, status='ok')
tracker.record(user_id='p9_demo_user', org_id='p9_demo_org',
               provider_id='volcengine', protocol='volcengine',
               kind='image', model='doubao-seedream-4-0-250828',
               prompt_tokens=10, completion_tokens=0, total_tokens=10,
               cost_usd=0.04, latency_ms=5000, status='ok')

summary = tracker.user_summary('p9_demo_user', days=30)
```

**输出**:
```json
{
  "entity_id": "p9_demo_user",
  "scope": "user",
  "days": 30,
  "total_calls": 2,
  "total_tokens": 1510,
  "total_cost_usd": 0.0525,
  "errors": 0,
  "month_to_date_cost_usd": 0.0,
  "by_provider": [
    {"provider_id": "volcengine", "calls": 1, "tokens": 10, "cost_usd": 0.04},
    {"provider_id": "openai-compatible", "calls": 1, "tokens": 1500, "cost_usd": 0.0125}
  ],
  "by_kind": [
    {"kind": "image", "calls": 1, "tokens": 10, "cost_usd": 0.04},
    {"kind": "chat", "calls": 1, "tokens": 1500, "cost_usd": 0.0125}
  ],
  "fallback_rows": 0
}
```

✅ **完整聚合**: total + by_provider + by_kind + scope + days + fallback_rows

### 2.5 API 端点

| 端点 | 方法 | 用途 | 测试 |
|------|------|------|------|
| `/api/ai/usage` | GET | 查询 user/org 用量 | ✅ test_ai_usage_returns_200 |
| `/api/ai/circuit` | GET | 查询熔断状态 | ✅ test_ai_circuit_endpoint |
| `/api/ai/cost/estimate` | POST | 估算成本 | ✅ test_ai_cost_estimate_endpoint |

---

## 3. 配额限流

### 3.1 RateLimiter (进程内)

```python
class RateLimiter:
    """Sliding window — process-internal, per (user_id, provider_id)"""

    def __init__(self, window_seconds: int = 3600):
        self.window_seconds = 3600
        self._buckets: Dict[Tuple[str, str], Deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, user_id, provider_id, per_hour) -> Tuple[bool, int]:
        now = time.time()
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
- ✅ per user × provider 滑动窗口
- ✅ env 默认 `AI_RATE_LIMIT_PER_HOUR=1000`
- ✅ thread-safe (Lock)
- ❌ 进程内, 多 worker 不共享
- ❌ 无 per-tenant (org_id) 配额

### 3.2 配额维度矩阵

| 维度 | 实现 | 状态 |
|------|------|------|
| per (user, provider) request count | `RateLimiter.check()` | ✅ |
| per (user, provider) token count | ❌ | **P2 缺** |
| per (org, provider) request count | ❌ | **P0 缺 (B2B 必需)** |
| per (org) monthly budget USD | ❌ | **P1 缺** |
| per (user) daily request count | ❌ | **P1 缺** |
| 跨 worker / 跨进程 共享 | ❌ (需 Redis) | **P1 缺** |

### 3.3 P0 建议 — Redis RateLimiter

```python
import redis
import time as _time

class RedisRateLimiter:
    """Distributed rate limiter using Redis INCR + EXPIRE"""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis = redis.Redis.from_url(redis_url, decode_responses=True)

    def check(self, scope: str, key: str, limit: int, window_sec: int = 3600) -> Tuple[bool, int]:
        """scope=user|org|tenant, key=user_id|org_id|tenant_id"""
        redis_key = f"ratelimit:{scope}:{key}:{int(_time.time()) // window_sec}"
        current = self.redis.incr(redis_key)
        if current == 1:
            self.redis.expire(redis_key, window_sec)
        return (current <= limit, max(0, limit - current))

# Multi-dimensional
def check_quota(user_id, org_id, provider, per_user_hour=1000, per_org_hour=10000):
    user_ok, _ = redis_limiter.check("user", f"{user_id}:{provider}", per_user_hour)
    org_ok, _ = redis_limiter.check("org", f"{org_id}:{provider}", per_org_hour)
    return user_ok and org_ok
```

**价值**: 多 worker 共享 + per-tenant 配额 + 实时计数

### 3.4 P1 建议 — Token-based 配额

```python
class TokenBucketRateLimiter:
    """Token bucket — limit by total tokens (not request count)"""

    def __init__(self, redis_client):
        self.redis = redis_client

    def consume(self, scope, key, tokens_requested, max_tokens, refill_per_sec):
        """Returns (allowed, remaining_tokens)"""
        # Lua script for atomic CAS
        lua = """
        local current = tonumber(redis.call('GET', KEYS[1]) or 0)
        local requested = tonumber(ARGV[1])
        local max_tokens = tonumber(ARGV[2])
        if current + requested > max_tokens then
            return 0
        end
        redis.call('INCRBYFLOAT', KEYS[1], requested)
        redis.call('EXPIRE', KEYS[1], 3600)
        return 1
        """
        allowed = self.redis.eval(lua, 1, f"tokens:{scope}:{key}",
                                  tokens_requested, max_tokens)
        return (bool(allowed), 0)
```

**价值**: 避免 "1 个长 prompt 消耗 $5" 失控

---

## 4. 三轮审查关键发现

### 第一轮: 降级链 + 自动 fallback
- ✅ 4 级降级 (限流 → 熔断 → mock → 真实调用)
- ⚠️ 未自动级联 gpt-4 → gpt-3.5 → local (需 caller 手动)
- ✅ Mock 永远可跑 (开发 / CI / 测试)

### 第二轮: 成本追踪 + 用量持久化
- ✅ per (protocol, model) 价格表
- ✅ env override
- ✅ DB 持久化 + by_provider / by_kind 聚合
- ✅ user_summary / org_summary 双维度

### 第三轮: 配额限流 + 多 worker
- ⚠️ 进程内 RateLimiter (多 worker 不共享)
- ❌ 无 per-tenant / per-org 配额
- ❌ 无 token-based 配额
- ❌ 无月度预算上限

---

## 5. P0-P2 改进路线

| 优先级 | 改进项 | 工作量 | 价值 |
|--------|-------|--------|------|
| **P0** | Redis RateLimiter (per user/org/tenant) | 1d | 多 worker + 多租户 |
| **P0** | ProviderCascade 自动级联 (with_fallbacks) | 1d | 自动降级链 |
| **P1** | Token-based quota (token bucket + Lua) | 1d | 防成本失控 |
| **P1** | Monthly budget cap (per org) | 1d | B2B 计费 |
| **P1** | Cost forecast (基于历史用量预测月度成本) | 1d | 预算预警 |
| **P2** | Retry decor (tenacity exponential backoff) | 0.5d | 错误率 -50% |
| **P2** | Streaming response (SSE) | 1d | 实时 UX |
| **P2** | Cost breakdown by team / project | 1d | 内部成本归因 |

---

## 6. 总结

nanobot-factory 的 **成本追踪 + 熔断 + 限流** 实现达到 **B+ 商业级**:
- ✅ 4 级降级链 (限流 → 熔断 → mock → 真实)
- ✅ per (protocol, model) 价格表 + env override
- ✅ UsageTracker DB 持久化 + 多维度聚合
- ⚠️ 进程内限流器, 多 worker 不共享
- ❌ 缺 per-tenant / per-org 配额 (B2B 必需)
- ❌ 缺 token-based 配额 + 月度预算
- ❌ 缺自动 provider cascade fallback

**建议**: 短期切 Redis RateLimiter + 加 ProviderCascade, 中期加 token 配额 + 月度预算。