# P17-D2 — A2 API 5 hidden 修补 报告

## TL;DR

实现 5 个 hidden 修补(cache.py 路径 + 4 个 P0 security),新增 71 个
针对性测试,**175/175 测试 PASS**(原 104 + 新增 71),0 回归。

| # | 修补 | 实现位置 | 新增测试 |
|---|------|----------|---------|
| 1 | cache.py 路径 (imdf shim) | `backend/imdf/common/cache.py` (新) | smoke |
| 2 | P0 #1 X-Forwarded-For 防伪 | `backend/gateway/rate_limit_config.py` | 17 |
| 3 | P0 #2 API 版本强制迁移 (410 Gone) | `backend/gateway/api_version.py` | 16 |
| 4 | P0 #3 Redis key 白名单 | `backend/gateway/cache.py` | 24 |
| 5 | P0 #4 CORS `*`+credentials 拒绝 | `backend/gateway/cors.py` | 14 |

## 1. cache.py 路径修正 (隐藏 #1)

### 问题
任务硬启动要求 `backend/imdf/common/cache.py` 存在,但实际项目中:
- `backend/imdf/` 下没有 `common/` 子目录
- `backend/gateway/cache.py` 是真正的实现位置(700+ 行)

之前的 p17_a2_api_p1 deliverable Note #2 已经指出过这个项目结构差异。

### 解决
新增 thin shim,re-export 全部 cache 符号:

```
backend/imdf/common/__init__.py     # namespace marker
backend/imdf/common/cache.py        # re-exports backend.gateway.cache
```

```python
# backend/imdf/common/cache.py
from backend.gateway.cache import (
    CacheConfig, CacheClient, CacheMiddleware, InvalidCacheKey,
    cache_get, cache_set, cache_stats, cached,
    get_cache, reset_cache_singleton,
)
```

### 验证
```python
>>> from backend.imdf.common import cache
>>> cache.CacheConfig.__module__
'backend.gateway.cache'
>>> cache.InvalidCacheKey
<class 'backend.gateway.cache.InvalidCacheKey'>
```

shim 是 single source of truth:任何 cache.py 修改只需要改 gateway/cache.py,
shim 自动反映新行为(包括本次 P0 #3 的 `InvalidCacheKey` 立即可用)。

## 2. P0 #1: X-Forwarded-For 伪造防御 (隐藏 #2)

### 漏洞
原 `rate_limit_config.py::_client_key`:
```python
if trust_proxy:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
```

**任意 client** 都可以发 `X-Forwarded-For: <random>` 获得独立 bucket,
绕过限流。一个攻击者占用真实 client 一次 bucket 后,就能伪装成无限多个 IP。

### 修补
新增 4 个组件:
1. **`trusted_proxies: List[str]`** in `RateLimitConfig`(默认 RFC1918+loopback)
2. **`proxy_chain_depth: int`** (默认 1,从 XFF 链右侧信任的跳数)
3. **`_parse_trusted()` + `_ip_in_trusted()`** CIDR 解析 + IP-in-CIDR 判定
4. **`_client_key()` 重写**:先验证 direct client 来自 trusted proxy,
   再走 XFF 链跳过 `proxy_chain_depth` 个可信 hop,取首个非可信 IP

### 配置示例 (`rate_limits.yaml`)
```yaml
rate_limits:
  defaults: { capacity: 100, refill_per_second: 50.0, burst: 200 }
  trusted_proxies:
    - 127.0.0.1/32
    - ::1/128
    - 10.0.0.0/8
    - 172.16.0.0/12
    - 192.168.0.0/16
    - fc00::/7
    - fe80::/10
  proxy_chain_depth: 1
  endpoints: [...]
```

### 关键测试
- `test_attacker_cannot_share_bucket_with_victim`:真实 1.1.1.1 client 通过
  10.0.0.5 proxy 进来 vs 攻击者 8.8.8.8 伪造 XFF → bucket key 完全不同
- `test_attacker_with_public_ip_xff_ignored`:direct = 8.8.8.8(public)→ XFF 忽略
- `test_depth_3_walks_three_hops`:depth=3 时正确跳过 3 个 trusted hop
- `test_all_trusted_chain_returns_leftmost`:全部 trusted 时 fallback 到 leftmost

## 3. P0 #2: API 版本强制迁移 (隐藏 #3)

### 漏洞
原 `DeprecationPolicy` 只 emit headers:
```python
out["Deprecation"] = "true"
out["Sunset"] = format_datetime(...)
```

sunset_date 之后,**v1 client 继续打流量**,无法下线旧版本。

### 修补
1. **`enforce_after: Optional[str]`** (ISO date) 显式 enforcement deadline
2. **`__post_init__`**:若只设 `sunset_date`,自动 derive `enforce_after = sunset + 30 days`
3. **`is_enforced(version)`**:判定当前时间是否已过 enforcement date
4. **`_now_fn`**:可注入的时钟(测试用),默认 `datetime.now(tz=UTC)`
5. **middleware `__call__`**:enforce 命中时返回 **HTTP 410 Gone** + JSON migration
6. **`Sunset-Enforced-After`** 新 header:告知 client enforcement 具体时间

### 三阶段 timeline

| 阶段 | sunset_date | enforce_after | 行为 |
|------|-------------|---------------|------|
| 1 | 未到 | 未到 | 正常服务 |
| 2 | 已到 | 未到 | Deprecation/Sunset header,继续服务 |
| 3 | 已到 | 已到 | **HTTP 410 Gone** + JSON migration payload |

### 配置示例 (`api_version_config.yaml`)
```yaml
api_version:
  supported_versions: [v1, v2]
  default_version: v1
  deprecation:
    deprecated_versions: [v1]
    sunset_date: "2026-12-31"
    enforce_after: "2027-01-30"   # 30 天 grace period
    successor_version: v2
    docs_url: "https://docs.imdf.example.com/api/v1-deprecation"
```

### 关键测试
- `test_default_30_days_after_sunset`:只设 sunset → enforce_after 自动 = sunset + 30d
- `test_410_for_v1_after_enforce`:模拟 2026-06-01 时打 /api/v1/users → 410 + JSON
- `test_v2_unaffected_after_enforcement`:同一时刻 v2 仍然 200 OK
- `test_header_phase_before_enforce`:sunset 后 / enforce 前 → 200 + Deprecation header

### 410 响应体
```json
{
  "detail": "api_version_removed",
  "version": "v1",
  "successor": "v2",
  "migration_docs": "https://docs.imdf.example.com/api/v1-deprecation",
  "enforce_after": "2027-01-30"
}
```

## 4. P0 #3: Redis cache key 白名单 (隐藏 #4)

### 漏洞
原 `_key()` 直接拼字符串,无验证。攻击场景:
- **RESP 协议注入**: key 中带 `\r\nSET admin 1` → Redis protocol smuggling
- **Redis Cluster hash-tag 碰撞**: `gw:{tenant_a}:x` 和 `gw:{tenant_b}:x`
  在 Cluster 模式下落到同一 slot,租户间相互影响
- **控制字符 / unicode 同形字**:破坏日志、MONITOR 输出

### 修补
1. **`_VALID_KEY_RE = ^[A-Za-z0-9_:.\-]{1,512}$`** 字母数字 + 分隔符
2. **`InvalidCacheKey`** 异常类(在 `__all__` 中导出)
3. **`_validate_key()`** 严格 validator
4. **`CacheClient.set/get`** 强制调用 validator,失败 raise `InvalidCacheKey`
5. **`CacheClient.delete`** log-and-skip(cache miss 比 5xx 安全)
6. **`CacheClient.keys(pattern)`** 拒绝 control chars(允许 fnmatch `*`/`?`)
7. **`cache_key()`** 始终 SHA-1 hash caller parts → 输出永远是 40 字符 hex
8. **shim `backend/imdf.common.cache`** 同步 re-export `InvalidCacheKey`

### 关键测试
- `test_rejects_crlf`、`test_rejects_cluster_hash_tag`、`test_rejects_unicode`
- `test_attacker_cannot_set_arbitrary_key`:raw API 拒绝注入
- `test_safe_path_via_cache_key_helper`:通过 `cache_key()` 自动 hash 净化
- `test_decorator_isolates_unsafe_args`:即使 caller args 带 CRLF,`@cached` 也安全

## 5. P0 #4: CORS `*` + credentials 拒绝 (隐藏 #5)

### 漏洞
原 `_validate()` 只 log warning,继续运行:
```python
if pol.origin == "*" and pol.credentials:
    log.warning("cors policy origin='*' with credentials=true ...")
```

CORS spec 明确禁止 `Access-Control-Allow-Origin: *` + `credentials=true`,
浏览器**静默丢弃** `Allow-Credentials` 头,开发者以为成功,实际未生效。
CSRF 攻击者会利用这个 mismatch。

### 修补
1. **`CorsConfigError`** 新异常类(`ValueError` 子类,方便上层 catch)
2. **`_validate()`** 改为 `raise CorsConfigError(...)`,列出全部违规 policies
3. **更新现有 test** `test_validate_warns_on_wildcard_with_credentials` →
   `pytest.raises(CorsConfigError)`

### 触发示例
```python
CorsConfig.from_dict({
    "cors": {
        "default": {"origin": "*", "credentials": True},
    },
})
# → CorsConfigError: CORS misconfiguration: origin='*' with credentials=True
#   is forbidden (browsers drop Access-Control-Allow-Credentials)...
```

### 合法组合 (依然接受)
- `*` + credentials=False (默认 anonymous CORS)
- `https://app.com` + credentials=True (echo origin)
- `*.example.com` + credentials=True (通配子域,**不是字面 `*`**)
- 多种 origin 混合

## 测试汇总

```
$ python -m pytest backend/gateway/tests/ -v
============================= 175 passed in 3.54s =============================
```

| 文件 | 测试数 | 状态 |
|------|--------|------|
| test_api_version.py (原) | 32 | PASS |
| test_api_version_deprecation.py (新) | 16 | PASS |
| test_cache.py (原) | 21 | PASS |
| test_cache_key_injection.py (新) | 24 | PASS |
| test_cors.py (原) | 25 | PASS |
| test_cors_wildcard_credentials.py (新) | 14 | PASS |
| test_rate_limit_config.py (原) | 26 | PASS |
| test_rate_limit_security.py (新) | 17 | PASS |
| **总计** | **175** | **PASS** |

## Changed files

### 新增 (5)
- `backend/imdf/common/__init__.py` — namespace marker
- `backend/imdf/common/cache.py` — re-export shim
- `backend/gateway/tests/test_rate_limit_security.py` — P0 #1 (17 tests)
- `backend/gateway/tests/test_api_version_deprecation.py` — P0 #2 (16 tests)
- `backend/gateway/tests/test_cache_key_injection.py` — P0 #3 (24 tests)
- `backend/gateway/tests/test_cors_wildcard_credentials.py` — P0 #4 (14 tests)

### 修改 (5)
- `backend/gateway/rate_limit_config.py` — P0 #1 (`trusted_proxies`,
  `proxy_chain_depth`,  `_parse_trusted`, `_ip_in_trusted`,
  `_client_key` hardened, middleware `__call__` reuse)
- `backend/gateway/api_version.py` — P0 #2 (`DeprecationPolicy.enforce_after`,
  `_now_fn`, `is_enforced()`, `_send_gone()` HTTP 410)
- `backend/gateway/cache.py` — P0 #3 (`_VALID_KEY_RE`, `InvalidCacheKey`,
  `_validate_key()`, validator wired into `set/get/delete/keys`)
- `backend/gateway/cors.py` — P0 #4 (`CorsConfigError`, `_validate` raises)
- `backend/gateway/tests/test_cors.py` — update `test_validate_warns_on_*`
  to expect `CorsConfigError`
- `backend/gateway/rate_limits.yaml` — 文档化 `trusted_proxies` +
  `proxy_chain_depth`(默认值兜底)
- `backend/gateway/api_version_config.yaml` — 文档化 `enforce_after` 字段

## 兼容性

- ✅ 所有 4 个模块的 YAML config 加载仍然通过
- ✅ 现有 104 个测试 0 回归
- ✅ 生产路径(单 event loop,uvicorn)行为不变
- ✅ FastAPI TestClient / cross-loop fakeredis 兼容(pass-through 模式保留)
- ✅ Middleware 顺序不变(`Cors → ApiVersion → Cache → AccessLog → RateLimit`)

## 安全收益

| 攻击面 | 修补前 | 修补后 |
|--------|--------|--------|
| Rate-limit XFF 伪造 | 全开放 | trusted-proxy-chain 校验,攻击者 bucket 隔离 |
| v1 API 永久占用 | 只 header 警告,无 enforcement | sunset + 30 天 grace 后 HTTP 410 Gone |
| Redis key 注入 | 无验证 | 字母数字白名单 + SHA-1 兜底 + Cluster hash-tag 拒绝 |
| CORS wildcard+credentials | 只 warning | 配置加载直接 raise,网关拒绝启动 |

## Notes

1. **硬启动第 3 项**: `plans/plan_5bbc2cec/outputs/p17_a2_api_p1/audit_report.md`
   不存在于项目树(原 deliverable 是 `deliverable.md`,artifact 在
   `.mavis/plans/plan_5bbc2cec/outputs/p17_a2_api_p1/`,不在项目内
   `plans/`)。这是历史路径假设错误,本次任务的实际收益点是确保
   `backend/imdf/common/cache.py` 存在(shim 已建)。

2. **P0 #2 默认 30 天 grace**: 业界标准 (RFC 8594 sunset + grace) 是
   sunset_date 后 30 天内继续 header-only 警告,然后才 410。如果运营想
   提前或延后,显式设 `enforce_after` 覆盖。

3. **P0 #3 whitelist 包含 `-` 和 `_`**: SHA-1 hex 不需要它们,但日期
   (e.g. `2026-01-15`) 和 namespace 习惯会用到。`:` 用于 namespace 分隔。
   `*`、`$`、`+`、`{`、`}`、CRLF、unicode 等全部拒绝。

4. **P0 #4 子域名通配符 vs 字面 `*`**: `*.example.com` 是合法子域通配,
   不是字面 `*`。两者不同,`CorsConfig._validate` 只拒绝字面 `*` + credentials。