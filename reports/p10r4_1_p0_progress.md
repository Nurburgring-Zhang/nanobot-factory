# P10R4-1 P0 进度: Token 吊销 + Brute Force 持久化 + SIEM (Attempt 2)

**Date**: 2026-06-26
**Status**: ✅ P0-4, P0-5, P0-6 全部完成 (含 HIDDEN-1..5 fixup)

---

## 1. P0 6 项状态 (Attempt 2 后)

| P0 | Finding | 状态 | 本任务范围 |
|----|---------|------|----------|
| P0-1 | MFA / WebAuthn | ❌ TODO | 后续 P11+ |
| P0-2 | OIDC SSO | ❌ TODO | 后续 P11+ |
| P0-3 | Vault 集成 | ❌ TODO | 后续 P11+ |
| **P0-4** | **Brute force 持久化** | ✅ **DONE** | 本任务 + HIDDEN-1 env flag |
| **P0-5** | **Token 吊销缺失** | ✅ **DONE** | 本任务 + HIDDEN-4/5 |
| **P0-6** | **SIEM/SOC 集成** | ✅ **DONE** | 本任务 + HIDDEN-3 server 启动 |

**本任务完成 P0-4, P0-5, P0-6 全部 ✅** (升级自 attempt 1, 当时 P0-6 为 partial)

---

## 2. P0-5 Token 吊销 (含 HIDDEN-4, HIDDEN-5)

详见 `reports/p10r4_1_token_revocation.md`.

**API 总览**:
```python
# Token-level
mgr.revoke_token(token, reason="logout")           # 吊销单个

# User-level
mgr.revoke_user(user_id, reason="password_changed") # 吊销某用户全部

# Global
mgr.revoke_all("compromised_secret")               # 全场吊销
mgr.clear_global_revocation()  # [HIDDEN-5] admin 解除封锁

# Verify
mgr.verify_token(token)  # 自动检查三层 revocation
```

**集成点** (Attempt 2 新增):
- `UnifiedAuthManager.verify_token()` — 3 层 revocation check
- `UnifiedAuthManager.change_password()` — auto revoke_user
- `UnifiedAuthManager.clear_global_revocation()` — [HIDDEN-5] admin API
- `TokenRevocationStore.start_background_gc()` — [HIDDEN-4] daemon thread
- `decode_token_unsafe()` 扩展支持 verify_exp/aud/iss=False (吊销场景)

**HIDDEN-4: 后台 GC** — env `TOKEN_REVOCATION_GC=true` 启用 (默认 off — 不污染单测)

**HIDDEN-5: admin clear** — `clear_global_revocation()` 返回 True 如果之前是 global 状态

**测试**: 22 (token_revocation) + 9 (HIDDEN-4/5 部分 in hidden_fixes) = 31 tests PASS

---

## 3. P0-4 Brute Force 持久化 (含 HIDDEN-1)

详见 `reports/p10r4_1_bruteforce_v2.md`.

**HIDDEN-1 修复**: UnifiedAuthManager 读 `BRUTE_FORCE_PERSISTENCE` env var

```python
# 优先级: 显式参数 > 环境变量 > 默认 False
mgr = UnifiedAuthManager(
    jwt_secret=...,
    enable_bruteforce_persistence=None,  # 显式 None = 读 env
)
# 或通过 env:
os.environ["BRUTE_FORCE_PERSISTENCE"] = "true"  # true/1/yes/on
```

**关键改动**:
- 启动时 `_load_persistent_state()` — 从 SQLite 恢复 lock state
- `record_failure()` → `_persist_state()` — 触发 lock 时同步
- `record_success()` → `_persist_clear()` — 清除持久化
- `gc_persistence()` — 定期清理

**测试**: 5 (HIDDEN-1 in hidden_fixes) + 47 (bruteforce 回归) = 52 tests PASS

---

## 4. P0-6 SIEM 集成 (含 HIDDEN-3)

详见 `reports/p10r4_1_third_party.md`.

**HIDDEN-3 修复**: server.py 启动时调 `init_all_third_party()`

```python
# backend/server.py (uvicorn.run 之前)
from common.third_party import init_all_third_party
_third_party_status = init_all_third_party(
    sentry_dsn=os.environ.get("SENTRY_DSN", ""),
    sentry_environment=os.environ.get("ENVIRONMENT", "development"),
    structlog_json=os.environ.get("STRUCTLOG_JSON", "true").lower() in ("true","1","yes"),
    structlog_level=os.environ.get("LOG_LEVEL", "INFO"),
)
```

**集成**:
- Sentry SDK: no-op when DSN missing, PII filter 自动
- structlog JSON: 生产模式输出 JSON 行 (SIEM-ready)

**测试**: 10 (third_party) + 2 (HIDDEN-3 in hidden_fixes) = 12 tests PASS

---

## 5. 未来 P0 路线图 (4-8 周)

| 任务 | 工作量 | 优先级 |
|------|-------|--------|
| P0-1 MFA (TOTP + WebAuthn) | 2-3 人天 | P1 |
| P0-2 OIDC SSO (authlib) | 3-5 人天 | P2 |
| P0-3 Vault (hvac) | 1-2 人天 | P1 |
| Redis 共享 lock state | 1-2 人天 | P1 |
| JWT rotation (kid + JWKS) | 1-2 人天 | P2 |

---

**Status**: ✅ DONE — P0-4/5/6 全部完成, 5 HIDDEN fixup 全部 PASS