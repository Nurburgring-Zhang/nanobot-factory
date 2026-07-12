# P10R4-1: 第三方面对 — Sentry + structlog (Attempt 2, 含 HIDDEN-3)

**Date**: 2026-06-26
**Status**: ✅ 全部完成 (含 HIDDEN-3 server.py 启动 init)

---

## 1. 设计原则

1. **永远不阻塞启动** — 库未装 / 配置缺失 → no-op 降级, 不抛异常
2. **PII 永远不泄露** — 自动 filter 敏感字段 (password/token/api_key/jwt)
3. **生产友好** — JSON 输出可直接被 SIEM (Splunk/ELK/Datadog) 采集
4. **开发友好** — Console 彩色输出易读

---

## 2. Sentry SDK 集成

### 2.1 功能矩阵

| 功能 | 实现 | 状态 |
|------|------|------|
| 异常捕获 | `capture_exception()` | ✅ |
| 消息上报 | `capture_message()` | ✅ |
| 用户上下文 | `set_user()` | ✅ |
| 性能监控 | `traces_sample_rate=0.1` | ✅ (需 DSN) |
| **重复 init bug 修复** | 修复 `_sentry_initialized` 误报 True | ✅ **Attempt 2** |
| 自动 PII filter | `_sentry_before_send_pii_filter` | ✅ |
| Release tracking | `release=git SHA` | ✅ (需 DSN) |
| 环境标签 | `environment=production` | ✅ (需 DSN) |
| No-op 降级 | 未配 DSN / SDK 未装 → graceful | ✅ |

### 2.2 关键代码 (Attempt 2 bug 修复)

```python
# backend/common/third_party.py
def init_sentry(
    dsn: str = "",
    environment: str = "development",
    release: str = "",
    traces_sample_rate: float = 0.1,
    enable_performance: bool = True,
    attach_stacktrace: bool = True,
    send_default_pii: bool = False,
    extra_context: Optional[Dict[str, Any]] = None,
) -> bool:
    """初始化 Sentry SDK."""
    
    if _sentry_initialized:
        # Attempt 2 修复: 返回实际状态, 而不是 True
        return _sentry_sdk is not None
    # ...
```

**修复说明**: 之前如果第一次 init 失败 (DSN 缺失), `_sentry_initialized=True` 但 `_sentry_sdk=None`. 第二次调用直接返回 `True` (错误). 修复后返回 `_sentry_sdk is not None` — 准确反映状态.

### 2.3 PII 自动 Filter

```python
def _sentry_before_send_pii_filter(event: Dict, hint: Dict) -> Optional[Dict]:
    """在发送前剔除敏感字段 — 防止密码/token 泄露到 Sentry."""
    # 字段名包含 password/token/secret/api_key/jwt/credential → [REDACTED]
    # Header: Authorization/Cookie/X-API-Key → [REDACTED]
    ...
```

### 2.4 用法示例

```python
from common.third_party import init_all_third_party, capture_exception, set_user

result = init_all_third_party(sentry_dsn=os.environ.get("SENTRY_DSN", ""))
# {"sentry": False, "structlog": True}  ← 当前环境

try:
    process_data(user_id)
except DatabaseError as e:
    set_user(user_id=user_id, email=user.email)
    capture_exception(e, request_id=req.id, endpoint="/api/v1/data")
    raise
```

---

## 3. structlog JSON Logging

### 3.1 功能矩阵

| 功能 | 实现 |
|------|------|
| JSON 输出 | `JSONRenderer()` |
| Console 输出 (开发) | `dev.ConsoleRenderer()` |
| ISO 8601 timestamp | `TimeStamper(fmt="iso")` |
| Level / Logger name | `add_log_level`, `add_logger_name` |
| Context vars (request_id) | `contextvars.merge_contextvars` |
| 自动绑定 stdlib logger | `ProcessorFormatter.wrap_for_formatter` |

### 3.2 输出对比

**JSON (生产)**:
```json
{"event": "Login failed for user alice", "timestamp": "2026-06-26T06:17:54.567644Z", "level": "warning", "logger": "unified_auth"}
```

**Console (开发)**:
```
2026-06-26 06:17:54 [warning] unified_auth   Login failed for user alice
```

### 3.3 SIEM 采集 (示例)

**Splunk**:
```spl
index=nanobot level=warning | stats count by event | sort -count
```

**ELK**:
```
filter {
  json { source => "message" }
  date { match => ["timestamp", "ISO8601"] }
}
```

---

## 4. Server 启动初始化 (HIDDEN-3, Attempt 2 修复)

**问题**: Attempt 1 实现了 `init_all_third_party()` 但**没有在 server.py 启动时调用**, 实际 Sentry/structlog 都没有被启用. Verifier 视为 HIDDEN-3 (P0).

**修复**: `backend/server.py:10804-10830` 在 `uvicorn.run()` 之前调用.

```python
# backend/server.py (在 __main__ 块)
if __name__ == "__main__":
    from common.third_party import init_all_third_party
    import os as _os
    _third_party_status = init_all_third_party(
        sentry_dsn=_os.environ.get("SENTRY_DSN", ""),
        sentry_environment=_os.environ.get("ENVIRONMENT", "development"),
        sentry_release=_os.environ.get("GIT_COMMIT", "unknown"),
        structlog_json=_os.environ.get("STRUCTLOG_JSON", "true").lower() in ("true", "1", "yes"),
        structlog_level=_os.environ.get("LOG_LEVEL", "INFO"),
    )
    logger.info(
        "Third-party integration initialized: sentry=%s structlog=%s",
        _third_party_status.get("sentry", False),
        _third_party_status.get("structlog", False),
    )
    # BRUTE_FORCE_PERSISTENCE 状态提示
    if _os.environ.get("BRUTE_FORCE_PERSISTENCE", "").lower() in ("true", "1", "yes", "on"):
        logger.info("BRUTE_FORCE_PERSISTENCE=true — brute force state will be persisted to SQLite")
    
    uvicorn.run(app, ...)
```

### 4.1 HIDDEN-3 测试

```
TestServerStartupThirdParty:
  - test_server_imports_init_all_third_party   ✅ (grep server.py 验证)
  - test_init_all_third_party_callable         ✅ (实际调用不抛)
```

---

## 5. 测试覆盖 (12 tests)

### 5.1 tests/test_third_party_integration.py (10 tests)

```
TestSentryIntegration (5):
  - test_init_sentry_no_dsn_returns_false         ✅
  - test_init_sentry_with_invalid_dsn_returns_false  ✅
  - test_capture_exception_does_not_raise         ✅
  - test_capture_message_does_not_raise           ✅
  - test_set_user_does_not_raise                  ✅

TestStructlogIntegration (3):
  - test_init_structlog_json_produces_json_output  ✅
  - test_init_structlog_console_produces_human_output  ✅
  - test_get_structlog_logger_returns_logger      ✅

TestCombinedInit (2):
  - test_init_all_third_party_no_dsn              ✅
  - test_init_all_third_party_with_dsn            ✅
```

### 5.2 auth/tests/test_hidden_fixes.py (2 tests 涉及 HIDDEN-3)

```
TestServerStartupThirdParty:
  - test_server_imports_init_all_third_party   ✅
  - test_init_all_third_party_callable         ✅
```

**Total: 12/12 PASS** ✅

---

## 6. 集成位置 (Attempt 2 完整)

### 6.1 应用入口 (server.py 启动)

```python
# backend/server.py (HIDDEN-3 修复)
init_all_third_party(
    sentry_dsn=os.environ.get("SENTRY_DSN", ""),
    sentry_environment=os.environ.get("ENVIRONMENT", "production"),
    structlog_json=True,
)
```

### 6.2 业务代码

```python
# 在 auth/unified_auth.py 等模块中
from common.third_party import get_structlog_logger
log = get_structlog_logger("unified_auth")
log.warning("login_failed", username=username, ip=ip, reason="wrong_password")
```

### 6.3 FastAPI 异常处理

```python
@app.exception_handler(Exception)
async def exception_handler(request, exc):
    capture_exception(exc, path=request.url.path, method=request.method)
    return JSONResponse(status_code=500, content={"detail": "Internal error"})
```

---

## 7. 依赖管理

### 7.1 requirements.txt (建议)

```python
sentry-sdk>=1.40.0           # Error monitoring (P0-6)
structlog>=24.1.0            # Structured JSON logging
```

### 7.2 当前状态

- `sentry-sdk`: **未装** → 自动 no-op ✅
- `structlog`: **已装** → JSON 输出 ✅

---

## 8. 与 OWASP 对标

| OWASP | 本集成贡献 |
|-------|----------|
| A09 Logging Failures | structlog JSON → SIEM 完整覆盖 |
| A05 Security Misconfiguration | PII filter 防止日志泄露 |
| A04 Insecure Design | Sentry capture_exception + 自动 breadcrumb |

---

## 9. 已知限制

| 限制 | 影响 | 后续 |
|------|------|------|
| sentry-sdk 未装 | no-op (不影响启动) | requirements.txt 加 |
| 无 SENTRY_DSN | no-op (本地开发) | 生产 env 配置 |
| structlog 配置替换 stdlib root logger | 已有 log 配置可能失效 | 谨慎评估迁移路径 |

---

**Status**: ✅ DONE — Sentry + structlog 完整集成 + HIDDEN-3 server.py 启动调用, 12 tests PASS