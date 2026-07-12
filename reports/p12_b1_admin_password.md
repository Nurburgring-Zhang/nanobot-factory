# P12-B1: Admin 密码硬编码移除 — 完整审计与加固报告

**Plan**: plan_fabb60b5 (P12 Sprint B)
**Task**: P12-B1: Admin 密码硬编码移除 (P9-4 finding #10)
**Date**: 2026-06-26 11:28-13:10 (Asia/Shanghai)
**Worker**: coder (session mvs_d4c51a34e419455f887e76e099af4a87)
**Status**: ✅ **DONE (15/15 pytest + 5/5 manual = 20/20 PASS)**

---

## 一、硬启动检查 v3

```
Set-Location 'D:\Hermes\生产平台\nanobot-factory'         ✅ OK
Test-Path 'backend\imdf\auth'                            ❌ False (旧路径, 实际在 backend\auth\)
Test-Path 'reports\p9_4_security.md'                     ✅ True
Test-Path 'reports\p10_sprint_e.md'                      ✅ True
```

---

## 二、问题重新审计 (本任务扩展)

P11-D-1 修复仅覆盖 `backend/auth/` 模块。本任务 P12-B1 在前次审计的基础上,
扩大扫描范围到**整个项目**,发现 P11-D-1 漏掉了 5 处硬编码位置:

### 2.1 发现的新硬编码位置 (审计后)

| # | 文件 | 行 | 内容 | 类别 |
|---|------|-----|------|------|
| 1 | `scripts/rbac_test.py` | 16-26 | 11 个账号的密码 (含 Admin@2026!, Prod@2026!, QC@20261!, Crowd@2026!, Client@2026!) | **P0 active code** |
| 2 | `backend/scripts/init_accounts.py` | 42-55 | 10 个非 admin 账号的密码 (Prod@2026!, Crowd@2026! 等) | **P0 active code** |
| 3 | `完整部署.bat` | 83 | `echo 预设账号: admin / Admin@2026!` | P0 deployment script |
| 4 | `启动.bat` | 29 | `echo 预设账号: admin / Admin@2026!` | P0 deployment script |
| 5 | `backend/scripts/init_accounts.py` | 269 | `IndentationError` (P11-D-1 引入的回归) | P1 regression |

P11-D-1 报告 ("Active code 0 violations") 仅基于 `backend/` 范围扫描,
本次 P12-B1 把范围扩大到 **整个项目根** + **全部扩展名** 才暴露全部问题。

---

## 三、本任务实际修改

### 3.1 修改文件清单 (5 个)

| 文件 | 改动 | 行号 |
|------|------|------|
| `backend/scripts/init_accounts.py` | 11 个账号全部改用 `ENV:<VARNAME>` 占位符 + `_resolve_env_password()` 通用解析 + 修 IndentationError 回归 | L42-55, L82-104, L122-133, L269-283 |
| `scripts/rbac_test.py` | ACCOUNTS 列表全部改用 ENV: 占位符 + `_resolve_account_password()` + 打印时隐藏密码 | L14-58, L137-149 |
| `完整部署.bat` | 第 83 行不再显示密码,改为 `.env` 提示 | L83-85 |
| `启动.bat` | 第 29 行不再显示密码,改为 `.env` 提示 | L29-30 |
| `.env.example` | 新增 10 个非 admin 账号 env var + 生成建议 | L94-114 |

### 3.2 新建/扩展文件清单 (3 个)

| 文件 | 用途 |
|------|------|
| `backend/tests/test_admin_password_env.py` | 扩展到 15 个测试 (含非 admin + .bat + rbac_test + 全项目 grep) |
| `reports/p12_b1_admin_password_verify.py` | 5 项端到端 fail-fast/inject/ephemeral 验证脚本 |
| `reports/p12_b1_admin_password.md` | 本报告 |

---

## 四、grep 验证 — 全项目 0 硬编码 (active code)

### 4.1 Admin@2026! 剩余位置 (全为允许)

| 文件 | 行 | 类别 | 是否允许 |
|------|-----|------|----------|
| `backend/auth/unified_auth.py:725` | docstring: "防止硬编码 ``Admin@2026!`` 残留" | 文档说明 | ✅ 允许 |
| `backend/auth/tests/conftest.py:31` | `monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "TestAdmin@2026!StrongSecret32chars")` | 测试 fixture | ✅ 允许 |
| `backend/tests/test_admin_password_env.py` × 13 | docstring / assert msg / grep helper | 测试文件 | ✅ 允许 |
| `reports/*.md` × 8 | 历史 P9-4 finding 报告 | 历史文档 | ✅ 允许 (md 不在扫描范围) |
| `scripts/init_accounts.py:97` | `RuntimeError msg` | 错误消息 | ✅ 允许 |
| `reports/p12_b1_admin_password_verify.py:23` | 测试 assertion logic | 验证脚本 | ✅ 允许 |

**Active code 硬编码违规数: 0** (经 `test_no_hardcoded_admin_password_in_source` 自动验证)

### 4.2 非 admin 密码剩余位置 (全为允许)

| 文件 | 行 | 类别 | 是否允许 |
|------|-----|------|----------|
| `backend/tests/test_admin_password_env.py:198-201` | `FORBIDDEN_PATTERNS` 列表 (用于 grep 验证) | 测试文件 | ✅ 允许 |

**Active code 硬编码违规数: 0** (经 `test_no_hardcoded_preset_passwords_in_source` 自动验证)

---

## 五、测试结果

### 5.1 pytest 套件 — 15/15 PASS (扩展后)

```
$ python -m pytest tests/test_admin_password_env.py -v --tb=short
============================= test session starts =============================
platform win32 -- Python 3.11.6, pytest-8.4.2
collected 15 items

tests/test_admin_password_env.py::test_admin_password_loaded_from_env PASSED [  6%]
tests/test_admin_password_env.py::test_missing_admin_password_raises_in_production PASSED [ 13%]
tests/test_admin_password_env.py::test_missing_admin_password_uses_ephemeral_in_test_mode PASSED [ 20%]
tests/test_admin_password_env.py::test_existing_admin_not_overwritten PASSED [ 26%]
tests/test_admin_password_env.py::test_env_example_documents_admin_password PASSED [ 33%]
tests/test_admin_password_env.py::test_no_hardcoded_admin_password_in_source PASSED [ 40%]   ← 扩展到全项目
tests/test_admin_password_env.py::test_no_hardcoded_preset_passwords_in_source PASSED [ 46%] ← 新增, 检测 10 个非 admin 密码
tests/test_admin_password_env.py::test_admin_config_error_is_runtime_error_subclass PASSED [ 53%]
tests/test_admin_password_env.py::test_init_accounts_uses_env_for_admin PASSED [ 60%]
tests/test_admin_password_env.py::test_admin_config_error_message_mentions_remediation PASSED [ 66%]
tests/test_admin_password_env.py::test_non_admin_accounts_use_env_passwords PASSED [ 73%] ← 新增, 10 个非 admin env inject
tests/test_admin_password_env.py::test_non_admin_missing_env_fails_fast PASSED [ 80%] ← 新增, fail-fast on missing env
tests/test_admin_password_env.py::test_non_admin_test_mode_uses_ephemeral PASSED [ 86%] ← 新增, IMDF_TEST_MODE 降级
tests/test_admin_password_env.py::test_rbac_test_uses_env PASSED [ 93%] ← 新增, rbac_test.py 验证
tests/test_admin_password_env.py::test_batch_scripts_no_password PASSED [ 100%] ← 新增, .bat 验证

============================= 15 passed in 2.06s =============================
```

### 5.2 独立 fail-fast 端到端验证 — 5/5 PASS

```
$ python reports/p12_b1_admin_password_verify.py
=== Admin Password Hardening Verification ===

[1] UnifiedAuthManager fail-fast:        [PASS] AdminConfigError raised, env=True, remediation=True
[2] UnifiedAuthManager env injection:   [PASS] admin created from env, login=success
[3] init_accounts fail-fast:            [PASS] RuntimeError raised, env_mentioned=True, remediation=True
[4] init_accounts env injection:        [PASS] env injection: returned='TestInitPassword_abc123def456'
[5] IMDF_TEST_MODE ephemeral:           [PASS] test mode created ephemeral admin, role=admin

=== Result: 5/5 PASS ===
```

---

## 六、修复前后对比

### 6.1 全项目硬编码分布

| 位置 | P11-D-1 完成时 | P12-B1 完成后 |
|------|----------------|---------------|
| `backend/auth/unified_auth.py` | 已修复 | ✅ 保持 |
| `backend/auth/tests/conftest.py` | 测试 fixture | ✅ 允许 |
| `backend/scripts/init_accounts.py` admin 部分 | 已修复 | ✅ 保持 |
| `backend/scripts/init_accounts.py` 非 admin 部分 | 🔴 10 处硬编码 | ✅ 全部 ENV: |
| `scripts/rbac_test.py` | 🔴 11 处硬编码 | ✅ 全部 ENV: |
| `完整部署.bat` | 🔴 显示密码 | ✅ 提示 .env |
| `启动.bat` | 🔴 显示密码 | ✅ 提示 .env |
| `backend/scripts/init_accounts.py:269` | 🔴 IndentationError | ✅ 已修 |

### 6.2 错误消息质量 (admin / non-admin 共享)

```python
raise RuntimeError(
    f"{env_name} env var is required to bootstrap {purpose} "
    f"via init_accounts.py. Set it in .env (e.g. `python -c "
    f"'import secrets; print(secrets.token_urlsafe(24))'` to generate a "
    f"32+ char random secret) or set IMDF_TEST_MODE=1 for ephemeral "
    f"test password. The legacy hardcoded passwords have been removed "
    f"for security reasons (P12-B1)."
)
```

---

## 七、.env.example 文档

```
# === 初始 admin 密码 (P11-D-1) ===
ADMIN_INITIAL_PASSWORD=

# === 预设账号密码 (P12-B1) ===
PROD_LEAD_PASSWORD=
QC_LEAD_PASSWORD=
PROD_USER1_PASSWORD=
PROD_USER2_PASSWORD=
PROD_USER3_PASSWORD=
CROWD_LEAD_PASSWORD=
CROWD_MGR_PASSWORD=
CROWD_QC_PASSWORD=
CROWD_USER1_PASSWORD=
CLIENT1_PASSWORD=
```

✅ 11 个账号的密码全部从 env 注入,有完整生成建议和缺省行为说明。

---

## 八、OWASP / P9-4 finding 对账

| P9-4 finding #10 | 状态 |
|------------------|------|
| 默认 admin `Admin@2026!` hardcode 在 source | ✅ FIXED (P11-D-1) + ✅ 验证 (P12-B1) |

OWASP A07 (认证失败) 维度从 P9-4 的 "🟡 PARTIAL" 升级为 **✅ PASS**。

---

## 九、未完成的 P9-4 其他 finding (供后续 sprint)

| # | P9-4 finding | 状态 | 后续 sprint |
|---|---------------|------|--------------|
| 1 | `.env.example` 默认 JWT_SECRET_KEY | 🔴 | P12-B2 |
| 2 | `AUDIT_CHAIN_SECRET` 无轮换 | 🔴 | P12-B3 |
| 3 | API Key SHA-256 缺 HMAC | 🟡 (P10-E 改 AES-256-GCM) | P12-B4 |
| 4 | UnifiedAuth + Legacy Auth 双实现 | 🟡 | P12-B5 |
| 5 | MCP server 缺 OAuth | 🔴 | P12-B6 |
| 6 | RBAC 拒绝事件无审计 | 🔴 | P12-B7 |
| 7 | 字段级加密 (PII) | 🟡 | P12-B8 |
| 9 | JWT_SECRET 无最小长度校验 | 🔴 | P12-B2 |
| **10** | **默认 admin 密码硬编码** | **✅ P12-B1 DONE** | — |

---

## 十、结论

P12-B1 任务 **100% 完成**:

- ✅ Active code 硬编码 `Admin@2026!` 0 处 (含全项目扫描)
- ✅ Active code 硬编码非 admin 密码 0 处
- ✅ `ADMIN_INITIAL_PASSWORD` + 10 个非 admin env 注入 + fail-fast
- ✅ `.env.example` 完整文档化 (11 个 env var + 生成建议)
- ✅ pytest 15/15 PASS (扩展了 6 个新测试用例)
- ✅ 独立端到端验证 5/5 PASS
- ✅ 修复 P11-D-1 引入的 `init_accounts.py:269` 缩进回归
- ✅ `rbac_test.py` + `完整部署.bat` + `启动.bat` 全部去硬编码

**P9-4 finding #10 完全闭环**: 默认 admin + 10 个非 admin 预设账号的密码
全部从源码硬编码升级为 env 注入 + fail-fast + 文档化 + 测试覆盖**四重防护**。

---

**Worker**: coder (session mvs_d4c51a34e419455f887e76e099af4a87) @ 2026-06-26 11:28-13:10

— Deliverable: `outputs/p12_b1_admin_password/deliverable.md`