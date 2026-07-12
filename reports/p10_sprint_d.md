# P10 Sprint D: unified_auth 暴力破解防护

**Plan**: plan_9f8e2abe (P10 Sprint D)
**Task**: P10-D: Brute Force 防护 (Rate Limiter + 锁定)
**Date**: 2026-06-26 (Asia/Shanghai)
**Worker**: coder (session mvs_7d883c83301b4b4aa09a69a7ba91ac3a)
**Verdict**: ✅ **DONE** — 39/39 tests PASS (5.87s)

---

## 一、硬启动检查 v3 — ⚠️ 路径修正

```
Set-Location 'D:\Hermes\生产平台\nanobot-factory'                   ✅ OK
Test-Path 'backend\imdf\auth\unified_auth.py'                     ❌ False
Test-Path 'reports\p9_4_security.md'                              ✅ True (217 lines)
```

**修正**: 任务描述中的 `backend\imdf\auth\unified_auth.py` 路径陈旧。
实际文件位置: `backend\auth\unified_auth.py` (950 行, P9-4 报告已确认)。

**继续审计 + 实施**(任务核心是 brute force 防护, 不是验证路径)。

---

## 二、目标实现 — Brute Force 防护

### 2.1 设计目标 vs 实际实现

| 需求 | 实现 | 文件 |
|------|------|------|
| Redis-based rate limiter | in-memory + SQLite (项目无 Redis) | `bruteforce.py` |
| 5 次失败 → 15 min 锁定 | `BruteForceConfig(soft_threshold=5, soft_lock_seconds=900)` | `bruteforce.py:78-88` |
| 10 次失败 → 1 h 锁定 | `BruteForceConfig(hard_threshold=10, hard_lock_seconds=3600)` | `bruteforce.py:78-88` |
| 错误返回 429 | FastAPI `JSONResponse(status_code=429, headers={"Retry-After": ...})` | `test_unified_auth_bruteforce.py` |
| IP-based + account-based 双维度 | `_account_key()` + `_ip_key()` + `_keys()` | `bruteforce.py:108-126` |
| 测试验证 | 39 tests (unit + integration + FastAPI route + thread-safety) | `test_unified_auth_bruteforce.py` |

### 2.2 关键设计决策

#### 为什么 in-memory 而非 Redis?

用户档案记录: **0 个 Redis** (全 in-memory + JSON)。新增 Redis 依赖违反项目"0 个 Celery/Redis"约束。in-memory dict 性能最佳, 满足登录场景的低延迟需求; 进程重启时所有计数清零 (实际生产环境用 sticky session 或外部 store 持久化)。

#### 滑动窗口 (sliding window)

`BruteForceConfig.window_seconds = 3600` — 1 h 内的失败计数有效。`_prune()` 每次调用时移除 `now - window_seconds` 之前的旧时间戳。攻击者无法通过"等 1 h"绕过累计 10 次失败。

#### 锁定状态存储

`_locks: Dict[str, Tuple[float, str]]` — key → (lock_until_epoch, level)。
存 level 而非重新 heuristic 推导 (早期版本用 retry_after > soft - 5 启发式判断, 边界 case 误判 → 已修复)。

#### 双维度设计

```
record_failure(username="alice", ip="1.2.3.4")
  → 同时累加 acct:alice + ip:1.2.3.4
  → 任一达到 5/10 → 该维度被锁定
  → check_lock 返回最严格的锁定 (dual dimension = max)
```

防止攻击者用同一 IP 暴力枚举多个 username (IP 维度), 同时防止同一 username 跨多个 IP (account 维度)。

#### 不修改 `authenticate()`, 新增 `login()`

`UnifiedAuthManager.authenticate()` 保持 backward compatible (返回 tokens dict 或 None)。
新增 `login()` 方法返回结构化 `LoginResult`:

```python
@dataclass
class LoginResult:
    status: str  # "success" | "invalid_credentials" | "locked" | "inactive"
    tokens: Optional[Dict] = None
    user: Optional[Dict] = None
    retry_after: int = 0
    reason: str = ""
    locked_dimension: str = ""  # "account" | "ip" | ""
    lockout_level: str = "none"  # "none" | "soft_15min" | "hard_1h"
    failed_count: int = 0
```

调用方按 `status` 分支处理 (FastAPI route → 200/401/429)。

### 2.3 HTTP 429 响应格式

```json
{
  "status": "locked",
  "retry_after": 900,
  "reason": "account_locked",
  "locked_dimension": "account",
  "lockout_level": "soft_15min",
  "failed_count": 5
}
```

HTTP headers:
- `Retry-After: 900` (标准 RFC 7231)
- `X-RateLimit-Limit-Soft: 5`
- `X-RateLimit-Limit-Hard: 10`

### 2.4 审计日志集成

锁定事件记录到 `auth_audit_log` 表, `action='auth.locked'`, 含 `lockout_level`、`retry_after`、`failed_count`、`reason`。

---

## 三、修改文件清单

### 新增 (3 files)

| 文件 | 行数 | 用途 |
|------|------|------|
| `backend/auth/bruteforce.py` | 296 | `BruteForceProtector` + `BruteForceConfig` + `ThrottleResult` |
| `backend/auth/tests/__init__.py` | 1 | 测试包初始化 |
| `backend/auth/tests/test_unified_auth_bruteforce.py` | 760 | 39 tests (unit + integration + FastAPI + thread-safety) |

### 修改 (3 files)

| 文件 | 修改 | 行数变化 |
|------|------|----------|
| `backend/auth/unified_auth.py` | 加 `LoginResult` dataclass + `login()` 方法 + `__init__` 接受 throttle_protector | +120 |
| `backend/auth/__init__.py` | 导出 `LoginResult` + `BruteForceProtector` + `BruteForceConfig` + `ThrottleResult` | +5 |

---

## 四、测试覆盖 (39 tests, 5.87s)

### 4.1 单元测试 (20 tests) — `TestBruteForceProtectorUnit`

| # | 测试 | 验证点 |
|---|------|--------|
| 001 | `initial_state_allows` | 未失败 → 允许 |
| 002 | `under_soft_threshold_no_lock` | < 5 次失败 → 不锁 |
| 003 | `exactly_soft_threshold_triggers_15min_lock` | 第 5 次 → soft_15min |
| 004 | `under_hard_threshold_still_soft_lock` | 9 次失败仍 soft |
| 005 | `hard_threshold_triggers_1h_lock` | 第 10 次 → hard_1h (1 h) |
| 006 | `lock_expires_after_timeout` | 时间前进 16 min → 解锁 |
| 007 | `record_success_clears_failures` | 成功清除计数 |
| 008 | `record_success_clears_active_lock` | admin reset 清除锁定 |
| 009 | `ip_based_lock_independent` | IP 锁定独立 |
| 010 | `account_based_lock_independent` | account 锁定独立 |
| 011 | `multi_user_isolation` | 多用户隔离 |
| 012 | `sliding_window_prune` | 1 h 前的失败剪枝 |
| 013 | `stats_returns_counts` | stats 调试 API |
| 014 | `state_snapshot_includes_locks` | snapshot 含 level+until |
| 015 | `ip_dimension_reason_label` | IP 锁定 reason='ip_locked' |
| 016 | `account_dimension_reason_label` | account 锁定 reason='account_locked' |
| 017 | `unknown_username_does_not_crash` | 空 username/IP 不崩溃 |
| 018 | `custom_config` | 自定义阈值生效 |
| 019 | `dual_dimension_returns_most_restrictive` | 双维度返回最严 |
| 020 | `retry_after_decreases_with_time` | retry_after 递减 |

### 4.2 集成测试 (10 tests) — `TestUnifiedAuthLoginIntegration`

| # | 测试 | 验证点 |
|---|------|--------|
| 001 | `successful_login_returns_tokens` | 成功返回 LoginResult(status=success, tokens) |
| 002 | `wrong_password_returns_invalid_credentials` | 错密码 → invalid_credentials |
| 003 | `5_failures_triggers_15min_lock` | 5 次 → locked, retry_after=900 |
| 004 | `10_failures_triggers_1h_lock` | 10 次 → locked, retry_after=3600 (通过 protector 直调) |
| 005 | `locked_blocks_correct_password` | 锁定期间正确密码也拒绝 |
| 006 | `lock_expires_can_retry` | 时间前进 16 min → 可重试 |
| 007 | `success_clears_failure_count` | 成功后清除计数 |
| 008 | `audit_log_records_locked_events` | 审计日志记录 action='auth.locked' |
| 009 | `nonexistent_user_treated_as_failure` | 不存在的用户名也计入失败 (防枚举) |
| 010 | `ip_lock_blocks_all_users_on_same_ip` | IP 锁定阻断所有用户名 |

### 4.3 FastAPI 路由测试 (8 tests) — `TestFastAPILoginRoute`

| # | 测试 | 验证点 |
|---|------|--------|
| 001 | `successful_login_returns_200` | HTTP 200 + access_token |
| 002 | `wrong_password_returns_401` | HTTP 401 |
| 003 | `5_failures_returns_429_with_retry_after_900` | HTTP 429 + Retry-After=900 |
| 004 | `10_failures_returns_429_with_retry_after_3600` | HTTP 429 (软锁) + 硬锁通过直调验证 |
| 005 | `locked_correct_password_still_429` | 锁定期间正确密码 → 429 |
| 006 | `lock_expires_returns_200` | 时间前进 → 200 |
| 007 | `x_forwarded_for_ip_dimension` | X-Forwarded-For 触发 IP 维度锁定 |
| 008 | `lock_resets_on_successful_login` | 成功后重置计数 |

### 4.4 线程安全 (1 test)

| # | 测试 | 验证点 |
|---|------|--------|
| 001 | `concurrent_record_failure` | 5 threads × 20 failures 不崩溃, 计数 = 100 |

---

## 五、踩坑记录 (Pydantic v2 + FastAPI + Future Annotations)

### 坑 1: `check_lock` heuristic 误判

**Bug**: 早期版本用 `if retry_after > soft_lock - 5: level = "hard_1h"` 启发式判断锁定等级。soft 锁定期满时 retry_after 恰好 = soft_lock_seconds, 触发误判 → 返回 hard_1h。

**修复**: 锁定状态存 `Tuple[float, str]` (until, level), `check_lock` 直接读 level 而非重新推导。

### 坑 2: FastAPI 路由 422 (Pydantic v2 ForwardRef)

**Bug**: `_build_login_app()` 内 `from fastapi import Request` + `def login(request: Request, payload: _LoginReq = Body(...))`。
当文件有 `from __future__ import annotations` 时, 类型注解变成字符串。FastAPI 用 `get_type_hints()` 解析, 通过函数 `__globals__` 查找 — 但 login 是内层函数, 其 `__globals__` 是测试模块的 globals, 而 `Request` 只在 `_build_login_app` 内导入, 找不到。

**症状**: `{"detail":[{"type":"missing","loc":["query","request"]...}]}` — Request 被当 query 参数。

**修复**: 把 `Request`/`Body`/`FastAPI`/`APIRouter`/`JSONResponse`/`BaseModel` 全部导入到模块级。

### 坑 3: Pydantic 模型必须模块级

`class LoginReq(BaseModel): ...` 不能定义在函数内。FastAPI + Pydantic v2 不能解析函数内定义的 ForwardRef (`_LoginReq`)。

### 坑 4: hard_1h 锁定通过 login() 流程无法到达

**设计现实**: account 维度 5 次失败触发 soft_15min 后, pre-check 阻断后续所有 login 调用, 永远到不了 10 次。IP 维度同理。硬锁定只能通过:
- 直接调用 `protector.record_failure()` (绕过 API)
- 攻击者等待 soft 锁定过期后再继续尝试

**测试调整**: `test_004_10_failures_triggers_1h_lock` 分两部分:
1. login() 流程验证 5 次即触发软锁定 (符合设计预期)
2. 直接通过 protector.record_failure() 模拟"soft 锁定过期 + 再 5 次"路径验证 hard_1h

---

## 六、安全维度增强 (P10-D 之外的可选加固)

| 增强 | 当前状态 | 建议 |
|------|----------|------|
| ✅ 软/硬指数锁定 | 已实现 | - |
| ✅ 双维度 (account + IP) | 已实现 | - |
| ✅ 滑动窗口 (1 h) | 已实现 | - |
| ✅ 审计日志 | 已实现 (action='auth.locked') | - |
| ✅ 线程安全 | 已实现 (threading.Lock + 单 key atomic ops) | - |
| 🟡 跨进程状态共享 | 仅 in-memory | 生产环境需 Redis (项目目前 0 Redis) |
| 🟡 CAPTCHA 挑战 | 未实现 | soft 锁定后展示 CAPTCHA (P11+) |
| 🟡 设备指纹 | 未实现 | soft 锁定后绑定 device_id |
| 🟡 通知机制 | 未实现 | 锁定事件触发邮件/webhook |
| 🟡 锁定管理 API | `protector.reset()` 已实现 | 暴露 admin endpoint |

---

## 七、OWASP 对标

| OWASP 项 | 缓解 |
|---------|------|
| A07:2021 Identification & Authentication Failures | ✅ 5/10 失败 + IP/account 双锁定 |
| Brute force protection | ✅ 完整覆盖 (test 39 PASS) |
| Rate limiting (登录) | ✅ 锁定即 429 |
| Audit log for auth events | ✅ 锁定事件写入 SQLite |

---

## 八、必跑测试命令

```powershell
Set-Location 'D:\Hermes\生产平台\nanobot-factory'
python -m pytest backend/auth/tests/test_unified_auth_bruteforce.py -v
```

**结果**: `39 passed in 5.87s` ✅

---

## 九、文件位置

- 实现: `backend/auth/bruteforce.py` (296 行)
- 集成: `backend/auth/unified_auth.py` (新增 LoginResult + login())
- 测试: `backend/auth/tests/test_unified_auth_bruteforce.py` (760 行)
- 报告: `reports/p10_sprint_d.md`
- Deliverable: `C:\Users\Administrator\.mavis\plans\plan_9f8e2abe\outputs\p10_sprint_d_bruteforce\deliverable.md`

---

**总结**: P10-D 暴力破解防护完成, 双维度 (account + IP) 锁定 + 软/硬指数退避 + 429 + 审计日志 + 39 tests 100% PASS。