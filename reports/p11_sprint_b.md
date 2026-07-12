# P11-B: P10-C JWT 4 P1 修正 — 交付报告

**Plan**: plan_d0803a33
**Task**: P11-B: P10-C JWT 4 修正 (common/auth silent → raise + iss/aud enforce + 6 regression + RFC 7519)
**Date**: 2026-06-26 10:55-11:25 (Asia/Shanghai, ~30 min)
**Worker**: coder (session mvs_226c8515dcf44766a92ae3d043d53f87)
**Verdict**: ✅ **PASS** — 145/145 JWT+auth tests, 0 回归

---

## 一、硬启动检查 v3 (路径修正)

```
Test-Path 'backend\imdf\auth\jwt_manager.py'        → False (子目录不存在)
Test-Path 'backend\imdf\auth\unified_auth.py'       → False (子目录不存在)
Test-Path 'backend\common\auth.py'                   → True ✓
Test-Path 'tests\advanced\test_advanced_modules.py' → False (路径错误)
Test-Path 'reports\p10_sprint_c.md'                  → True ✓
```

**路径修正** (与 P10-C / P9-4 一致):
- `backend/imdf/auth/jwt_manager.py` 不存在 — 实际 JWTManager 在 `backend/auth/unified_auth.py`
- `tests/advanced/test_advanced_modules.py` 不存在 — 实际在 `backend/tests/test_advanced_modules.py`

**真实 JWT 代码分布** (与 P10-C 报告一致):

| 文件 | 行数 | 角色 | 改动 |
|------|------|------|------|
| `backend/auth/unified_auth.py` | 1194 | 主用 `JWTManager` (P3+) | verify_token enforce iss/aud + docstring |
| `backend/security/auth.py` | ~487 | Legacy `JWTManager` (P3-) | verify_token enforce iss/aud + docstring |
| `backend/common/auth.py` | ~290 | `_decode_token` + `issue_access_token` | **silent warning → raise** + enforce iss/aud + docstring |
| `backend/auth/unified_auth.py` | 1194 | `JWTManager.__init__` | docstring RFC 7519 enforce |

---

## 二、4 Fix Diff

### Fix 1: common/auth.py silent warning → raise (P11-B-1) ✅

**变更前** (silent warning, 启动不中断):
```python
# P10-C: 启动时校验 secret 强度 (与 AuditChain / unified_auth 一致)
if len(sec) < JWT_MIN_SECRET_LENGTH:
    # 不 raise — 保持原函数签名; 但 record warning 便于诊断
    logger.warning(
        "JWT_SECRET is too short (%d chars, min %d). "
        "Set JWT_SECRET to a strong random value >= %d chars.",
        len(sec), JWT_MIN_SECRET_LENGTH, JWT_MIN_SECRET_LENGTH,
    )
return sec
```

**变更后** (fail-fast raise, 与 unified_auth 一致):
```python
# P11-B: 启动时校验 secret 强度 (与 AuditChain / unified_auth 一致)
# 短路 raise ValueError — 不再静默 warning, fail-fast 防止弱密钥被部署。
if len(sec) < JWT_MIN_SECRET_LENGTH:
    raise ValueError(
        f"JWT_SECRET is too short ({len(sec)} chars, min "
        f"{JWT_MIN_SECRET_LENGTH}). Set JWT_SECRET to a strong random "
        f"value >= {JWT_MIN_SECRET_LENGTH} chars. (RFC 7519 §3 / OWASP A02)"
    )
return sec
```

**覆盖文件**: `backend/common/auth.py:62-72`

---

### Fix 2: iss/aud 强制校验 (从写入 → 启动 enforce) (P11-B-2) ✅

**变更前** (3 个 JWTManager verify_token 都 disable verify_aud / verify_iss):
```python
# unified_auth.py:391-417
payload = jwt.decode(
    token, self.secret_key, algorithms=[self.algorithm],
    options={"verify_aud": False, "verify_iss": False},   # ← 不 enforce
)
```

**变更后** (3 个 verify_token 全部 enforce, + 显式 audience/issuer 参数):
```python
# unified_auth.py:391-419
payload = jwt.decode(
    token, self.secret_key, algorithms=[self.algorithm],
    audience=JWT_AUDIENCE,                               # ← enforce
    issuer=JWT_ISSUER,                                   # ← enforce
    options={"verify_aud": True, "verify_iss": True},    # ← enforce
)
```

**额外保护**: python-jose `verify_aud` 在 token 缺 aud claim 时静默通过
(已知 lib 行为), `_decode_token` 显式补一段:
```python
# common/auth.py:108-117
if "aud" not in payload:
    logger.warning("jwt decode failed: missing aud claim")
    raise HTTPException(status_code=401, detail="invalid_token")
if "iss" not in payload:
    logger.warning("jwt decode failed: missing iss claim")
    raise HTTPException(status_code=401, detail="invalid_token")
```

**覆盖文件**:
- `backend/auth/unified_auth.py:391-419` — 主用
- `backend/security/auth.py:208-225` — Legacy
- `backend/common/auth.py:77-120` — FastAPI 路径 + jose 兜底

---

### Fix 3: 6 test_advanced_modules.py 回归修复 (P11-B-3) ✅

**变更前** (6 个 test 用 < 16 字符 secret, P10-C-1 启动 raise 后失败):
```python
manager = JWTManager("test_secret_key")           # 15 字符 → 拒
auth = AuthManager("jwt_secret_123")              # 14 字符 → 拒
auth = AuthManager("secret")                      # 6 字符 → 拒
```

**变更后** (替换为 >= 16 字符 secret):
```python
manager = JWTManager("test_secret_key_32chars_long_aaaa")   # 32 字符
auth = AuthManager("jwt_secret_32chars_test_aaaa")          # 28 字符
auth = AuthManager("access_controller_secret_32")           # 28 字符
```

**额外加 fixture**: `backend/tests/conftest.py` 新增 autouse fixture `_strong_jwt_secret`
+ 显式 fixture `strong_jwt_secret` / `jwt_manager_strong` / `legacy_jwt_manager_strong`,
让任何 test 调用 `common.auth._secret()` 时都有默认强 secret (无需在每个 test 重复
monkeypatch)。

**覆盖文件**:
- `backend/tests/test_advanced_modules.py:235-296` — 6 处 secret 长度修复
- `backend/tests/conftest.py:181-220` — 新增 4 fixtures
- `backend/auth/tests/conftest.py` — 新增 autouse fixture (含 ADMIN_INITIAL_PASSWORD)

**回归验证**: `pytest backend/tests/test_advanced_modules.py` → **40/40 PASS** (含原 34 + 修复 6)

---

### Fix 4: RFC 7519 合规声明修正 (P11-B-4) ✅

**变更前**: docstring 说 "RFC 7519 合规" 但只 declare 未 enforce (容易误导)

**变更后**: docstring 明确说明 enforce 行为:
- `backend/common/auth.py:25-37` (module docstring) — P11-B RFC 7519 enforce section
- `backend/auth/unified_auth.py:324-343` (JWTManager docstring) — "P11-B 强化"
- `backend/security/auth.py:168-181` (JWTManager docstring) — "P11-B 强化"

**统一说明模板** (3 处 docstring 一致):
> * P11-B 强化 (RFC 7519 合规 + OWASP A02):
>   * 启动校验 secret_key 长度 >= JWT_MIN_SECRET_LENGTH (16 字符)
>     (P10-C-1 — secret < 16 字符直接 raise ``ValueError``)
>   * 签发 token 强制写入 iss / aud / jti 三标准声明
>     (RFC 7519 §4.1.1 / §4.1.3 / §4.1.7), jti 用 uuid4().hex 全局唯一
>   * verify_token 强制校验 iss + aud (P11-B-2):
>     - iss 必须等于 ``JWT_ISSUER`` ("nanobot-factory")
>     - aud 必须等于 ``JWT_AUDIENCE`` ("nanobot-factory-api")
>   * secret 强度校验 + iss/aud 强制 + jti 唯一 = RFC 7519 §4.1.1 / §4.1.3 /
>     §4.1.7 三项标准声明 enforce, 对应 OWASP A02:2021 + A07:2021

**一致性验证**: `grep "RFC 7519" backend/{common,auth,security}/auth.py` → 3 文件均含
RFC 7519 引用 + "enforce" 关键字, 文档与实现一致。

---

## 三、必跑测试结果

| 测试套件 | 文件 | PASS | FAIL | 备注 |
|----------|------|------|------|------|
| **新: test_common_auth.py** | `backend/tests/test_common_auth.py` | **22/22** | 0 | P11-B 新写, 覆盖 silent→raise + FastAPI Depends |
| **新: test_jwt_iss_aud_enforced.py** | `backend/auth/tests/test_jwt_iss_aud_enforced.py` | **19/19** | 0 | P11-B 新写, 覆盖 3 个 verify_token enforce iss/aud |
| **回归: test_jwt_manager.py** | `backend/tests/test_jwt_manager.py` | **23/23** | 0 | P10-C baseline 完整保留 |
| **回归: test_advanced_modules.py** | `backend/tests/test_advanced_modules.py` | **40/40** | 0 | 6 FAILED → 0 (P11-B-3 修复) |
| **回归: test_unified_auth_bruteforce.py** | `backend/auth/tests/test_unified_auth_bruteforce.py` | **39/39** | 0 | P11-D-1 env 兼容修复 (conftest 加 ADMIN_INITIAL_PASSWORD) |
| **回归: test_r9_5_auth_compliance.py** | `backend/tests/test_r9_5_auth_compliance.py` | **41/41** | 0 | R9.5 验证 iss/aud enforce 不破坏 GDPR / CSRF / Pwd |
| **总计** | (6 测试套件) | **184/184** | **0** | ✅ 100% PASS |

**任务指定 4 个核心测试套件**: `pytest backend/tests/test_common_auth.py backend/tests/test_jwt_manager.py backend/tests/test_advanced_modules.py backend/auth/tests/test_jwt_iss_aud_enforced.py -v` → **104/104 PASS in 2.11s**

**扩展开 1 个 (R9.5 regression)**: `pytest backend/tests/test_r9_5_auth_compliance.py -v` → **41/41 PASS in 2.56s**

**扩展开 2 个 (auth/tests regression)**: `pytest backend/auth/tests/ -v` → **58/58 PASS in 5.90s** (含 bruteforce + iss_aud)

**综合 consolidated run**: `pytest backend/tests/test_r9_5_auth_compliance.py backend/tests/test_common_auth.py backend/tests/test_jwt_manager.py backend/tests/test_advanced_modules.py backend/auth/tests/test_jwt_iss_aud_enforced.py` → **145/145 PASS in 4.51s**

---

## 四、改动文件清单

### 源码 (3 文件)
1. `backend/common/auth.py` (290 行) — **核心改动**: silent warning → raise + enforce iss/aud + 手动 aud/iss 兜底
2. `backend/auth/unified_auth.py` (1194 行) — `JWTManager.verify_token()` enforce iss/aud + docstring P11-B 强化
3. `backend/security/auth.py` (487 行) — `JWTManager.verify_token()` enforce iss/aud + docstring P11-B 强化

### 测试 (4 文件)
4. `backend/tests/test_common_auth.py` (新, 333 行) — 22 tests, 覆盖 _secret raise + _decode_token enforce + FastAPI Depends
5. `backend/auth/tests/test_jwt_iss_aud_enforced.py` (新, 290 行) — 19 tests, 覆盖 3 个 verify_token enforce + 端到端 round-trip
6. `backend/tests/test_advanced_modules.py` (363 行, 改 6 处 secret) — 6 回归修复
7. `backend/tests/conftest.py` (220 行, +40 行) — 新增 4 fixtures: `_strong_jwt_secret` (autouse), `strong_jwt_secret`, `jwt_manager_strong`, `legacy_jwt_manager_strong`
8. `backend/auth/tests/conftest.py` (新, 35 行) — autouse fixture 设强 JWT_SECRET + ADMIN_INITIAL_PASSWORD

### 报告 (1 文件)
9. `reports/p11_sprint_b.md` — 本文件

### 进度 (2 文件)
10. `C:\Users\Administrator\.mavis\plans\plan_d0803a33\board.md` — 进度 board 追加
11. `C:\Users\Administrator\.mavis\plans\plan_d0803a33\outputs\p11_sprint_b_jwt\deliverable.md` — 本交付

---

## 五、关键技术点

### 5.1 python-jose verify_aud 静默通过问题
python-jose `jwt.decode(..., audience=X, verify_aud=True)` 在 token 缺 aud claim 时
**静默返回 payload** (lib 已知 bug, 不同于 PyJWT)。我加了显式 claim 存在检查作为兜底:
```python
if "aud" not in payload:
    raise HTTPException(status_code=401, detail="invalid_token")
```
PyJWT 行为正确 (token 缺 aud claim 时直接 raise), 所以 unified_auth + security.auth
无需额外兜底。

### 5.2 关键 type 验证
- `JWT_ISSUER = "nanobot-factory"` (常量, RFC 7519 §4.1.1)
- `JWT_AUDIENCE = "nanobot-factory-api"` (常量, RFC 7519 §4.1.3)
- `JWT_MIN_SECRET_LENGTH = 16` (与 `audit_chain.py:153` 一致)

### 5.3 verify_token 错误处理
verify_token **不 raise** (返回 None) — 保持调用方兼容性:
- unified_auth: 旧调用 `verify_token(token, type="access")` 检查 None
- security: 同上
- common/auth: _decode_token raise HTTPException(401) — FastAPI 标准

### 5.4 测试 isolation 模式
3 层 fixtures 防护 (从宽到严):
1. `backend/auth/tests/conftest.py` — autouse 设强 JWT_SECRET + ADMIN_INITIAL_PASSWORD
2. `backend/tests/conftest.py` — autouse 设强 JWT_SECRET, 显式 fixture 提供 jwt_manager_strong
3. test body — 用 `monkeypatch.setenv("JWT_SECRET", "x")` 主动覆盖测边界 (短 secret raise)

---

## 六、Diff Stats (regex 统计)

```powershell
# verify "RFC 7519" + "enforce" 跨 3 个 auth.py 出现次数
Select-String -Path 'backend\common\auth.py','backend\auth\unified_auth.py','backend\security\auth.py' `
  -Pattern 'RFC 7519|enforce|verify_aud|verify_iss'
```

| 关键字 | common/auth.py | unified_auth.py | security/auth.py | 合计 |
|--------|----------------|-----------------|------------------|------|
| RFC 7519 | 5 | 6 | 4 | 15 |
| enforce | 3 | 3 | 3 | 9 |
| verify_aud | 2 | 2 | 2 | 6 |
| verify_iss | 2 | 2 | 2 | 6 |
| iss / aud 声明 | 6 / 6 | 8 / 8 | 4 / 4 | 18 / 18 |

文档与实现一致 ✅

---

## 七、Notes for Verifier

### 7.1 Pre-existing failure 已修复 (非本任务范围)
`backend/auth/tests/test_unified_auth_bruteforce.py` 启动时需要 `ADMIN_INITIAL_PASSWORD` env var
(P11-D-1 引入的安全约束)。本任务通过 `backend/auth/tests/conftest.py` autouse fixture 注入此
env var, 让 39 个 bruteforce 测试 100% PASS。如果 verifier 单独跑此测试文件不通过 conftest,
需手动 `set ADMIN_INITIAL_PASSWORD=TestAdmin@2026!StrongSecret32chars` 后运行。

### 7.2 验证命令
```powershell
# 任务指定 4 套核心测试 (104 PASS)
python -m pytest backend/tests/test_common_auth.py `
  backend/tests/test_jwt_manager.py `
  backend/tests/test_advanced_modules.py `
  backend/auth/tests/test_jwt_iss_aud_enforced.py -v

# 含 R9.5 regression (145 PASS)
python -m pytest backend/tests/test_r9_5_auth_compliance.py `
  backend/tests/test_common_auth.py `
  backend/tests/test_jwt_manager.py `
  backend/tests/test_advanced_modules.py `
  backend/auth/tests/test_jwt_iss_aud_enforced.py -v

# 全部 auth/tests/ (58 PASS)
python -m pytest backend/auth/tests/ -v
```

### 7.3 没破坏的回归
- R9.5 auth compliance 41 tests (GDPR / CSRF / Password) → 41/41 PASS
- P10-C JWT 23 tests (原 baseline) → 23/23 PASS
- P10-D bruteforce 39 tests → 39/39 PASS

### 7.4 与其它 plan 的接口
- **P10-C**: JWT secret + iss/aud/jti declare, **已 strengthen** (P11-B 把 verify 端的
  enforce 也补上, 不再只是声明)。
- **P11-D-1**: ADMIN_INITIAL_PASSWORD env 强制, **已隔离** (auth/tests/conftest.py)。
- **P9-4 OWASP Top 10**: A02 (Cryptographic Failures) + A07 (Auth Failures) 强化。

### 7.5 部署注意
升级本任务后, 任何使用 **旧 token (无 iss/aud)** 的系统都会因为 verify 拒绝而 401。
所有 token 都必须重新签发 (本项目所有 token 都由 unified_auth / security / common
issue_access_token 签发, 已自动带正确的 iss/aud, 所以项目内部不受影响)。

---

**完成时间**: 2026-06-26 11:25
**总耗时**: ~30 min
**完成度**: 100% (4/4 fix + 4/4 test suites + 145/145 tests PASS)
**Verdict**: ✅ PASS — engine 可确认任务完成
