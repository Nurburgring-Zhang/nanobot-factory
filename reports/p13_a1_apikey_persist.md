# P13-A1: API Key 磁盘 JSON 加密 + rotate_api_key() 旋转

**Date**: 2026-06-26
**Sprint**: P13-A1 (P10-E 持久化层补全 + 旋转 API)
**Worker**: coder
**Status**: DONE (34/34 tests PASS, 0.64s)

---

## 一、目标回顾

`backend/api_key_manager.py` 的 API key 持久化层在 P10-E 阶段完成了
**内存字段级加密** (AES-256-GCM in `backend/common/encryption.py`),
但**磁盘 JSON dump 仍是明文** (用 `"***"` 屏蔽,实际字段在内存里有,
写盘时 dump 整 dataclass → 明文泄漏)。

P13-A1 目标:

1. **磁盘 JSON 加密**: `configure_api_key` / `rotate_api_key` 写盘前
   加密,`_load_config` 启动时解密还原;dump 0 明文。
2. **rotate_api_key() API**: 用新 key 替换现有 key,保留 base_url/model,
   重置 last_verified/is_valid (强制 re-verify),触发
   on_key_change_callback,持久化到磁盘。
3. **P11-D-2 既有实现经验证仍然正确** (18 用例全部 PASS),本任务在
   既有基础上: (a) 增 `test_api_key_rotation.py` 16 用例专项覆盖
   rotate 契约, (b) 全目录 plaintext grep 确认无残留。

---

## 二、文件清单

### 新建 (1)

| 文件 | 行数 | 用途 |
|------|------|------|
| `backend/tests/test_api_key_rotation.py` | 412 | 16 用例专项覆盖 `rotate_api_key()` 契约 |

### 修改 (0)

无源码修改。磁盘加密 + rotate API 在 P11-D-2 阶段已经完成,
P13-A1 仅做**验证 + 增补专项测试**。

### 已存在 (复用, P11-D-2 产物)

| 文件 | 角色 |
|------|------|
| `backend/api_key_manager.py` | `APIKeyConfig.enc_api_key` (密文) + `_save_config`/`_load_config` 密文往返 + `rotate_api_key()` |
| `backend/common/encryption.py` | `FieldEncryption` (AES-256-GCM, 12B nonce, 16B tag) |
| `backend/tests/test_api_key_persistence_encryption.py` | 18 用例 (P11-D-2 已 PASS) |

---

## 三、API key 旋转契约 (`rotate_api_key`)

```python
def rotate_api_key(
    self,
    provider: str,
    new_key: str,
    base_url: str = "",
    model: str = "",
) -> bool:
    """P11-D-2: 旋转 API key — 用新 key 替换现有 key。

    行为契约:
      1. provider 不在 API_KEY_ENV_MAPPING → False (拒绝)
      2. 无现有 key (新 provider)        → False (用 configure_api_key)
      3. new_key 为空                    → False (拒绝)
      4. 重建 APIKeyConfig: 保留 base_url/model/enabled/configured_at
      5. set_api_key(new_key) → 加密 → 写 enc_api_key
      6. _save_config()       → 磁盘密文 (base64)
      7. on_key_change_callback(provider, new_cfg) 触发 (audit hook)
      8. logger.info 含 old_fingerprint[:4] (audit log)
      9. 安全契约: 重置 last_verified="" + is_valid=False + error_message=""
         → 下次 verify_all 必触发对外验证,新 key 不可信
    """
```

---

## 四、磁盘 JSON 加密 验证

### 4.1 dump 格式 (实测)

```json
{
  "openai": {
    "api_key": "e5gKs4plMTApv15QSfIBOdatstikCWuCSY9ttnOjmYYjKLQ22R7q3TsFhmzk4Tt2OfI9xziWyQ==",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-5",
    "enabled": true,
    "configured_at": "2026-06-26T17:05:36.098062",
    "last_verified": "",
    "is_valid": false
  },
  ...
}
```

- `api_key` 字段是 base64(12B nonce || ciphertext || 16B tag)
- 没有 `"***"` 占位符
- 没有任何明文片段

### 4.2 启动时解密还原 (实测)

```python
# mgr1: configure → save (写密文)
mgr1 = APIKeyManager(config_dir=td, master_key=key1)
mgr1.configure_api_key("openai", "sk-OPENAI-PLAINTEXT-LEAK-CHECK-12345")

# mgr2: 新进程启动 → load → decrypt → 明文可用
mgr2 = APIKeyManager(config_dir=td, master_key=key1)
assert mgr2.get_api_key("openai") == "sk-OPENAI-PLAINTEXT-LEAK-CHECK-12345"
```

### 4.3 错 master_key 加载 (实测)

```python
# 用 key1 写盘
mgr1.configure_api_key("openai", "sk-master-key-1-secret")

# 用 key2 加载 → 不崩, get_api_key 返回 None (GCM 认证失败)
mgr2 = APIKeyManager(config_dir=td, master_key=key2)
assert mgr2.get_api_key("openai") is None
```

### 4.4 AAD 隔离 (实测)

```python
mgr.api_keys["openai"].enc_api_key  # AAD = "api_key:openai"

# 用错 AAD → 必抛 EncryptionError (GCM 认证)
with pytest.raises(EncryptionError):
    mgr._encryptor.decrypt(enc, aad=b"api_key:anthropic")
with pytest.raises(EncryptionError):
    mgr._encryptor.decrypt(enc, aad=b"")  # 空 AAD 也必抛
```

---

## 五、测试结果

### 5.1 test_api_key_persistence_encryption.py (P11-D-2 既有)

```
collected 18 items
============================= 18 passed in 0.57s ==============================
```

(覆盖磁盘密文 dump、reload 解密、错 key 静默失败、"***" 旧格式兼容、
remove 清空字段、0 明文泄漏、rotate replace/require/unknown/callback/
persists/independent/round-trip/AAD/metadata/legacy、错 key init)

### 5.2 test_api_key_rotation.py (P13-A1 新建, 16 用例)

```
collected 16 items
============================= 16 passed in 0.54s ==============================
```

| # | Test | 验证 |
|---|------|------|
| 1 | `test_rotate_replaces_get_api_key` | 旋转后 get_api_key 返回新 key |
| 2 | `test_rotate_requires_existing_key` | 无 key 时 rotate 拒绝 |
| 3 | `test_rotate_rejects_unknown_provider` | unknown provider 拒绝 |
| 4 | `test_rotate_rejects_empty_new_key` | 空 new_key 拒绝 + 旧 key 保留 |
| 5 | `test_rotate_invokes_on_key_change_callback` | 回调触发,参数含新 key |
| 6 | `test_rotate_disk_ciphertext_changes` | 旋转前后密文不同 (GCM nonce per-call) |
| 7 | `test_rotate_disk_matches_memory` | 磁盘密文 == 内存 enc_api_key |
| 8 | `test_rotate_persists_across_restart` | 重启后能解出新 key |
| 9 | `test_rotate_isolated_per_provider` | 旋转一 provider 不影响其他 |
| 10 | `test_rotate_preserves_base_url_and_model` | base_url/model 保留 |
| 11 | `test_rotate_allows_explicit_base_url_override` | 显式 base_url/model 覆盖生效 |
| 12 | `test_configure_rotate_configure_round_trip` | configure ↔ rotate 混用正常 |
| 13 | `test_rotate_aad_binds_to_provider` | 错 AAD 解密必抛 |
| 14 | `test_rotate_resets_verification_metadata` | **新 key 强制 re-verify** (安全契约) |
| 15 | `test_repeated_rotation_keeps_final_key_decryptable` | 多次旋转最终 key 仍可解 |
| 16 | `test_rotate_writes_no_plaintext_to_disk` | 旋转不写明文 |

### 5.3 合计

```
============================== 34 passed in 0.64s ==============================
```

---

## 六、全目录 plaintext grep 验证

> P11-D-1 教训: 验证必须全目录扫,含 `.env`/`.bat`/`.sh`。
> 见 `agent_memory_tail` "analyzed 145 failures one-by-one — should have skipped"。

| 模式 | 文件类型 | hits |
|------|---------|------|
| `sk-(openai\|ant\|google\|moonshot\|api\|test\|live\|prod)[a-zA-Z0-9_-]{16,}` | `*.json` | **0** |
| `api_key.*=.*sk-[a-zA-Z0-9_-]{16,}` | `*.env*` | **0** |
| `api_key.*=.*sk-[a-zA-Z0-9_-]{16,}` | `*.bat` | **0** |
| `api_key.*=.*sk-[a-zA-Z0-9_-]{16,}` | `*.sh` | **0** |
| `sk-[a-zA-Z0-9_-]{20,}` | `*.json` | **0** |
| `AIza[a-zA-Z0-9_-]{20,}` | `*.json` | **0** |
| `sk-[a-zA-Z0-9_-]{20,}` | `*.ts` | **0** |
| `sk-[a-zA-Z0-9_-]{20,}` | `*.tsx` | **0** |
| `sk-[a-zA-Z0-9_-]{20,}` | `*.md` | 2 (P10-E/P10R4-1 报告 code-snippet 示例,非真实 secret) |
| `sk-[a-zA-Z0-9_-]{20,}` | `*.py` | 13 (test 夹具 plaintext 字符串,验证"不泄漏到磁盘") |

**结论**: 实际配置文件 (`.env`/`.bat`/`.sh`/`.json`/`.ts`/`.tsx`) **0 plaintext
sk-/AIza 串**。`.md` 里的 2 hits 是 P10-E 报告"加密前后对比"的 code snippet
示例 (标记为 `sk-live-plaintext-12345`);`.py` 里的 13 hits 全是 test 夹具,
这些字符串输入到 manager 后断言"在磁盘上找不到" (TEST 6 / TEST 16)。

---

## 七、安全设计要点

1. **Fail-fast on missing master key**: 生产 `allow_test_key=False` →
   启动直接 `RuntimeError`,禁止 ephemeral test key。
2. **AAD = `api_key:<provider>`**: 跨 provider 密文不能互用,即使共享
   master key 也不能把 openai 密文当 anthropic 用。
3. **GCM auth tag 校验**: 任何 tampering / 错 key / 错 AAD → 抛
   `EncryptionError`,无静默错误。
4. **rotate 重置 verification state**: 新 key 不可信,必须 re-verify。
5. **AESGCM nonce 12B random per-call**: 同一 key + 同一 plaintext
   → 每次密文都不同 (TEST 6 验证 5 次旋转产出 5 个不同密文)。
6. **plaintext only in caller stack frame**: `get_api_key()` 返回的
   明文是返回值, `api_keys[provider].api_key` 字段恒为 `""`,
   `enc_api_key` 恒为密文。

---

## 八、待办 (后续 sprint)

- [ ] `api_keys.json` 的文件权限 (chmod 600) 在 Windows 上验证 + Linux 上加
- [ ] `_save_config` 加 atomic write (写 .tmp + rename) 防止半写状态
- [ ] `rotate_api_key` 加 audit log 落盘 (rotation_event.log)
- [ ] `API_KEY_MASTER_KEY` 集成 Vault / KMS 注入
