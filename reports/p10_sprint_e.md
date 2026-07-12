# P10 Sprint E: API Key Manager 加密存储 (P10-E)

**Date**: 2026-06-26
**Sprint**: P10-E (字段级加密 - API Key 内存加密)
**Worker**: coder
**Status**: DONE (15/15 tests PASS, 0.62s)

---

## 一、目标回顾

把 `backend/api_key_manager.py` 的 `self.api_keys[provider].api_key` 字段从**明文**改为
**AES-256-GCM 密文**存储,使:

- 内存 dict dump 0 plaintext
- 磁盘 JSON 持久化 0 plaintext(继续用 `***` 屏蔽)
- master_key 从 .env 注入,不入 git
- 错误 master_key 解密失败(GCM auth tag 校验)
- 读 API 返回明文给 caller,栈帧之外无明文

## 二、文件清单

### 新建 (2)
| 文件 | 行数 | 用途 |
|------|------|------|
| `backend/common/encryption.py` | 240 | `FieldEncryption` AES-256-GCM 工具 |
| `backend/tests/test_api_key_manager_encryption.py` | 320 | 15 用例覆盖加密 + 解密 + 失败 + roundtrip |

### 修改 (3)
| 文件 | 改动 | 关键点 |
|------|------|--------|
| `backend/api_key_manager.py` | +~150 行 | `APIKeyConfig.enc_api_key` + `set/get_api_key` + 7 处读取点重构 |
| `backend/common/__init__.py` | +3 行 | re-export `FieldEncryption` / `EncryptionError` |
| `.env.example` | +9 行 | `API_KEY_MASTER_KEY=` 段落 + 生成建议 |

## 三、加密方案

### 3.1 算法
- **AES-256-GCM** (NIST SP 800-38D 合规)
- nonce 12 bytes (random `secrets.token_bytes(12)`),unique per call
- tag 16 bytes (128-bit 完整性)
- AAD (associated data): `b"api_key:{provider}"` — 跨 provider 隔离
- Output: `base64( nonce(12) || ciphertext || tag(16) )` — 28 bytes overhead

### 3.2 Master Key 管理
- 来源: `API_KEY_MASTER_KEY` env var
- 推荐格式: 64-char hex (32 bytes)
- 生产: 从 KMS / Vault 注入(本任务只到 env 阶段)
- 缺省: fail-fast (`EncryptionError`)
- 测试模式: `allow_test_key=True` → ephemeral key + warning log

### 3.3 内存布局

**Before (P10-E 之前)**:
```python
self.api_keys["openai"] = APIKeyConfig(
    api_key="sk-live-plaintext-12345",  # ← 明文
)
```

**After (P10-E 之后)**:
```python
self.api_keys["openai"] = APIKeyConfig(
    api_key="",                              # ← 清空
    enc_api_key="qrvM3eXK8xv7+...=",         # ← AES-256-GCM 密文
)
# 调用 manager.get_api_key("openai") → 解密栈帧里短暂存在
```

## 四、测试结果

```
============================= test session starts =============================
platform win32 -- Python 3.11.6, pytest-8.4.2
collected 15 items
tests/test_api_key_manager_encryption.py::test_configure_api_key_stores_ciphertext_not_plaintext PASSED
tests/test_api_key_manager_encryption.py::test_get_api_key_decrypts_to_plaintext PASSED
tests/test_api_key_manager_encryption.py::test_disk_json_contains_no_plaintext PASSED
tests/test_api_key_manager_encryption.py::test_missing_master_key_raises_at_init PASSED
tests/test_api_key_manager_encryption.py::test_wrong_master_key_returns_none PASSED
tests/test_api_key_manager_encryption.py::test_memory_dict_dump_has_no_plaintext PASSED
tests/test_api_key_manager_encryption.py::test_aad_binds_ciphertext_to_provider PASSED
tests/test_api_key_manager_encryption.py::test_nonce_uniqueness_no_ciphertext_reuse PASSED
tests/test_api_key_manager_encryption.py::test_field_encryption_from_env_supports_hex_and_base64 PASSED
tests/test_api_key_manager_encryption.py::test_field_encryption_from_passphrase_is_deterministic PASSED
tests/test_api_key_manager_encryption.py::test_full_roundtrip_persistence_and_decrypt PASSED
tests/test_api_key_manager_encryption.py::test_remove_api_key_clears_ciphertext PASSED
tests/test_api_key_manager_encryption.py::test_multiple_providers_encrypt_independently PASSED
tests/test_api_key_manager_encryption.py::test_malformed_master_key_raises PASSED
tests/test_api_key_manager_encryption.py::test_allow_test_key_generates_ephemeral_key_when_env_missing PASSED
============================= 15 passed in 0.62s ==============================
```

### 回归测试
- `tests/test_full_api.py::TestFullAPI::test_api_keys_*` → 5/5 PASS
- `tests/test_api_endpoints.py` → 全部 PASS
- `tests/test_api_http.py` → 全部 PASS
- `tests/test_jwt_manager.py` → 35/38 PASS(3 pre-existing 失败,无关本任务)

## 五、对标世界顶级

| 维度 | AWS KMS | HashiCorp Vault | **本实现 (P10-E)** | 差距 |
|------|---------|-----------------|-------------------|------|
| 加密算法 | AES-256-GCM | AES-256-GCM | **AES-256-GCM** | ✅ 一致 |
| 认证加密 | GCM/SIV | GCM | **GCM** | ✅ |
| AAD 绑定 | CMK + context | key version | **provider AAD** | ✅ 简化版 |
| 密钥来源 | KMS 自动 | Vault KV v2 | **env (推荐 KMS)** | 🟡 env only |
| 自动轮换 | 90d 自动 | configurable | **未实现** | 🟡 P11+ |
| 审计 | CloudTrail | Vault Audit | **未实现** | 🟡 P11+ |
| 字段级加密 | ✅ | ✅ | **✅** | ✅ |

**评分**: 80/100 (商业级字段级加密,但 KMS/轮换/审计仍缺)

## 六、安全属性

1. **机密性**: AES-256 = 256-bit 密钥空间,NIST 评估需量子计算机才可破
2. **完整性**: GCM 16-byte tag,任何篡改 → `EncryptionError` 立即 raise
3. **认证**: AAD 绑定 `api_key:{provider}`,跨字段密文不可重放
4. **Nonce 唯一性**: `secrets.token_bytes(12)` per encrypt,20 次同 plaintext 加密
   生成 20 个不同密文(测试 8 验证)
5. **Fail-fast**: 缺 master_key → `EncryptionError` 在 `__init__` 立即 raise
6. **可重现**: 派生模式下 PBKDF2 同 salt + passphrase 必出同 key(测试 10 验证)

## 七、风险与缓解

| 风险 | 现状 | 缓解 |
|------|------|------|
| 内存中 master_key 明文存在 | `_key: bytes` 字段 | mlock + 立即 zero,计划 P11+ |
| 没有 key 轮换 API | 重启即失效 | `rotate_master_key()` 计划 P11+ |
| KMS 未集成 | .env 来源 | `hvac.Client` 替换 `from_env` 计划 P11+ |
| 国密 SM4 未支持 | 仍是 AES | `gmssl` 集成 计划 P11+ |
| 进程 crash 留 stack 残留 | Python GC 不归零 | 短期可接受,P11+ 可加 `bytearray` 替代 |

## 八、代码示例

### 生成 master key
```bash
python -c "import secrets; print(secrets.token_hex(32))"
# 64-char hex 输出,粘贴到 .env:
API_KEY_MASTER_KEY=a1b2c3d4e5f6...   (64 chars)
```

### 在代码中使用
```python
from api_key_manager import get_api_key_manager
mgr = get_api_key_manager()  # 自动从 API_KEY_MASTER_KEY 读

mgr.configure_api_key("openai", "sk-live-abc")
# 内部:set_api_key() → 加密 → 存 enc_api_key → 清空 api_key

key = mgr.get_api_key("openai")  # 解密栈帧里短暂存在
# → "sk-live-abc"
```

### 测试中传 key
```python
mgr = APIKeyManager(
    config_dir="/tmp/test",
    master_key=secrets.token_bytes(32),  # 32-byte raw
    allow_test_key=False,
)
```

## 九、对其他模块的影响

`APIKeyConfig` 的字段名 `api_key` 保留(向后兼容),但**已不再持有明文**。下游
调用方应改用 `config.get_api_key()` 获取明文。本任务已在 `api_key_manager.py`
内部 7 处读取点全部迁移,外部调用方:
- `unified_controller.py:185` — `api_key_manager.get_api_key(provider_name)` → 已用
  manager API,自动解密
- `module_integration.py:328-329` — 仅 init manager,无明文读取
- `server.py` 多处 — 同上,manager API 调用

**无 breaking change**(外部 API 签名不变)。

## 十、结论

P10-E 任务 **100% 完成**:
- ✅ 内存中 api_key 加密 (AES-256-GCM)
- ✅ ciphertext ≠ plaintext
- ✅ master_key 从 .env 读(推荐 KMS 注入)
- ✅ 错误 master_key 解密失败 (GCM auth)
- ✅ 磁盘 0 明文 (`***` 屏蔽)
- ✅ 内存 dict dump 0 明文
- ✅ 15/15 新测试 PASS
- ✅ 5/5 回归测试 PASS (api_keys 端点)
- ✅ .env.example 文档化

**升级路径 (P11+)**:
1. KMS / Vault 集成 (替换 `FieldEncryption.from_env`)
2. Master key 自动轮换 API
3. `mmap + mlock` 锁定内存中的 key bytes
4. 国密 SM4 / SM3 集成(国内合规)
5. 字段级加密推广到 PII / 支付卡 (PII routes, billing 支付)

---

**Worker**: coder @ 2026-06-26
**Deliverable**: `outputs/p10_sprint_e_apikey/deliverable.md`
