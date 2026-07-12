"""
P10-E: API Key Manager 加密存储测试套件
========================================

覆盖维度:
1. 加密存储 (ciphertext != plaintext)
2. 解密还原 (get_api_key 返回明文)
3. 磁盘 JSON 持久化无明文
4. Master key 缺失启动失败
5. 错误 master key 解密失败 (GCM auth 失败 → 返回 None)
6. 内存 dict dump 0 plaintext
7. AAD 绑定 (跨 provider ciphertext 不能互用)
8. Nonce 唯一性 (同 key 多次加密不重复)
9. .env 重新加载 — master key 变更后旧的 ciphertext 无法解密
10. FieldEncryption 单元 — hex/base64 格式 + passphrase 派生

目标: >=10 用例 PASS
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

# ── 让 backend 目录可 import ──────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest  # noqa: E402

from api_key_manager import APIKeyConfig, APIKeyManager  # noqa: E402
from common.encryption import (  # noqa: E402
    EncryptionError,
    FieldEncryption,
)


# ── Fixtures ──────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_config_dir():
    """Per-test temp dir for api_keys.json so tests don't pollute real config."""
    with tempfile.TemporaryDirectory(prefix="apikey_enc_test_") as td:
        yield td


@pytest.fixture
def master_key_hex() -> str:
    """Fresh random 32-byte master key as 64-char hex."""
    return secrets.token_bytes(32).hex()


@pytest.fixture
def manager(tmp_config_dir, master_key_hex):
    """Fresh APIKeyManager with a random master key, isolated per test."""
    # Reset class-level encryptor (in case a previous test bound something)
    APIKeyConfig.clear_class_encryptor()
    m = APIKeyManager(
        config_dir=tmp_config_dir,
        master_key=bytes.fromhex(master_key_hex),
    )
    yield m
    APIKeyConfig.clear_class_encryptor()


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Strip ALL provider API key env vars + master key env so tests are
    hermetic. The parent shell often has OPENAI_API_KEY etc. set, which
    would otherwise be picked up by ``_scan_environment_variables`` and
    contaminate the manager state.
    """
    # Master key (encryption)
    monkeypatch.delenv("API_KEY_MASTER_KEY", raising=False)
    # All provider env vars in the APIKeyManager mapping
    for provider, mapping in {
        "openai": ["OPENAI_API_KEY", "OPENAI_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
        "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "openrouter": ["OPENROUTER_API_KEY", "ROUTER_API_KEY"],
        "kimi": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
        "glm": ["GLM_API_KEY", "ZHIPU_API_KEY"],
        "minimax": ["MINIMAX_API_KEY"],
        "doubao": ["DOUBAO_API_KEY", "BYTEDANCE_API_KEY"],
        "baidu": ["BAIDU_API_KEY", "ERNIE_API_KEY"],
        "tencent": ["TENCENT_API_KEY", "HUNYUAN_API_KEY"],
        "alibaba": ["ALIBABA_API_KEY", "QWEN_API_KEY"],
        "deepseek": ["DEEPSEEK_API_KEY"],
        "ollama": ["OLLAMA_API_KEY", "OLLAMA_HOST"],
        "comfyui": ["COMFYUI_API_KEY", "COMFYUI_HOST"],
        "seedream": ["SEEDREAM_API_KEY", "BYTEDANCE_SEEDREAM_KEY"],
        "seedance": ["SEEDANCE_API_KEY"],
        "kling": ["KLING_API_KEY", "KLINGAI_KEY"],
    }.items():
        for var in mapping:
            monkeypatch.delenv(var, raising=False)


# ── TEST 1: 配置后 ciphertext != plaintext ────────────────────────────────
def test_configure_api_key_stores_ciphertext_not_plaintext(manager):
    """P10-E 核心: api_keys dict value 中的 api_key 字段不能含明文。"""
    plaintext = "sk-test-plaintext-12345-abcdef"
    manager.configure_api_key("openai", plaintext)

    cfg = manager.api_keys["openai"]

    # 明文字段必须为空
    assert cfg.api_key == "", (
        f"plaintext field should be empty after set_api_key; got {cfg.api_key!r}"
    )

    # ciphertext 必须非空且 ≠ plaintext
    assert cfg.enc_api_key, "enc_api_key must be set"
    assert plaintext not in cfg.enc_api_key, (
        f"plaintext leaked into ciphertext: {cfg.enc_api_key[:80]}"
    )
    # base64 字符集
    import string
    b64_chars = set(string.ascii_letters + string.digits + "+/=")
    assert all(c in b64_chars for c in cfg.enc_api_key), (
        f"enc_api_key not valid base64: {cfg.enc_api_key!r}"
    )


# ── TEST 2: 解密还原 (get_api_key 返回明文) ─────────────────────────────
def test_get_api_key_decrypts_to_plaintext(manager):
    """get_api_key(provider) 必须返回原始明文。"""
    plaintext = "sk-anthropic-secret-9f8e7d6c5b4a3210"
    manager.configure_api_key("anthropic", plaintext)

    decrypted = manager.get_api_key("anthropic")
    assert decrypted == plaintext, (
        f"get_api_key returned {decrypted!r}, expected {plaintext!r}"
    )


# ── TEST 3: 磁盘 JSON 持久化无明文 ──────────────────────────────────────
def test_disk_json_contains_no_plaintext(tmp_config_dir, master_key_hex):
    """save 到 api_keys.json 后,磁盘文件不能含明文。

    P11-D-2: 磁盘现在是 AES-256-GCM 密文 (P10-E 用 "***" 屏蔽; 现在持久化
    真正密文, 这样 reload 后能解密还原)。
    """
    mgr = APIKeyManager(
        config_dir=tmp_config_dir,
        master_key=bytes.fromhex(master_key_hex),
    )
    secrets_to_set = {
        "openai": "sk-openai-disk-leak-test-1",
        "anthropic": "sk-ant-disk-leak-test-2",
        "google": "AIza-disk-leak-test-3",
    }
    for provider, key in secrets_to_set.items():
        mgr.configure_api_key(provider, key)

    config_file = Path(tmp_config_dir) / "api_keys.json"
    assert config_file.exists(), "config file not written"
    raw = config_file.read_text(encoding="utf-8")

    for plaintext in secrets_to_set.values():
        assert plaintext not in raw, (
            f"plaintext leaked to disk: {plaintext!r}"
        )

    # P11-D-2: 磁盘字段是密文 (base64), 不是 "***"
    import base64
    data = json.loads(raw)
    for provider in secrets_to_set:
        disk_value = data[provider]["api_key"]
        assert disk_value != "***", (
            f"expected ciphertext, not legacy '***' mask; got {disk_value!r}"
        )
        # 必须能 base64 解码且长度 >= 28 字节 (nonce 12 + tag 16 + ct)
        decoded = base64.b64decode(disk_value, validate=True)
        assert len(decoded) >= 28, (
            f"ciphertext too short for {provider}: {len(decoded)}"
        )


# ── TEST 4: Master key 缺失启动失败 (production mode) ────────────────────
def test_missing_master_key_raises_at_init(tmp_config_dir, monkeypatch):
    """没有 API_KEY_MASTER_KEY env 也没有 master_key= 参数 → EncryptionError。"""
    monkeypatch.delenv("API_KEY_MASTER_KEY", raising=False)

    with pytest.raises(EncryptionError) as exc_info:
        APIKeyManager(config_dir=tmp_config_dir)
    assert "API_KEY_MASTER_KEY" in str(exc_info.value) or "master key" in str(
        exc_info.value
    ).lower()


# ── TEST 5: 错误 master key 解密失败 → 返回 None ─────────────────────────
def test_wrong_master_key_returns_none(tmp_config_dir, master_key_hex):
    """用 key1 加密,绑定到 key2 后再读 → 解密失败,get_api_key 返回 None。"""
    key1 = bytes.fromhex(master_key_hex)
    key2 = secrets.token_bytes(32)

    mgr = APIKeyManager(config_dir=tmp_config_dir, master_key=key1)
    mgr.configure_api_key("openai", "sk-real-secret-xyz-9999")

    # 模拟运维误操作:用错的 key 重新绑定 class encryptor
    wrong_enc = FieldEncryption.from_raw_key(key2)
    APIKeyConfig.bind_class_encryptor(wrong_enc)

    # get_api_key 必须返回 None(绝不能泄露明文)
    leaked = mgr.get_api_key("openai")
    assert leaked is None, (
        f"plaintext leaked with wrong key! got {leaked!r}"
    )

    # cfg.get_api_key() 直接调用也必须返回空字符串
    cfg = mgr.api_keys["openai"]
    assert cfg.get_api_key() == "", (
        f"cfg.get_api_key() leaked plaintext with wrong key: {cfg.get_api_key()!r}"
    )

    # 错误密钥 rebind 时应有 warning 日志(可选,断言不强求)


# ── TEST 6: 内存 dict dump 0 plaintext ───────────────────────────────────
def test_memory_dict_dump_has_no_plaintext(manager):
    """对 manager.api_keys 做 repr / str / json.dumps,都不应含明文。"""
    plaintexts = {
        "openai": "sk-memdump-1",
        "anthropic": "sk-memdump-2",
        "google": "sk-memdump-3",
    }
    for p, k in plaintexts.items():
        manager.configure_api_key(p, k)

    # 6.1 repr() 不含明文
    dump = repr(manager.api_keys)
    for plain in plaintexts.values():
        assert plain not in dump, (
            f"plaintext {plain!r} leaked in repr(api_keys)"
        )

    # 6.2 str() 不含明文
    s = str(manager.api_keys)
    for plain in plaintexts.values():
        assert plain not in s

    # 6.3 直接访问每个 cfg 的 __dict__ 不含明文
    for provider, cfg in manager.api_keys.items():
        cfg_dict = cfg.__dict__.copy()
        cfg_dict.pop("api_key", None)  # 应当为空
        cfg_dict.pop("enc_api_key", None)  # 是密文,不检查
        for plain in plaintexts.values():
            assert plain not in repr(cfg_dict)


# ── TEST 7: AAD 绑定 — 跨 provider ciphertext 不能互用 ──────────────────
def test_aad_binds_ciphertext_to_provider(manager):
    """openai 加密的 ciphertext 用 anthropic 的 AAD 解密 → 失败。"""
    manager.configure_api_key("openai", "sk-aad-test-1")
    enc_openai = manager.api_keys["openai"].enc_api_key

    # 手动用 anthropic 的 AAD 尝试解密
    wrong_aad = b"api_key:anthropic"
    with pytest.raises(EncryptionError) as exc_info:
        manager._encryptor.decrypt(enc_openai, aad=wrong_aad)
    assert "GCM authentication failed" in str(exc_info.value) or "wrong" in str(
        exc_info.value
    ).lower()


# ── TEST 8: Nonce 唯一性 ─────────────────────────────────────────────────
def test_nonce_uniqueness_no_ciphertext_reuse(manager):
    """同 master key + 同 plaintext + 同 provider,多次加密的 ciphertext 必须
    不同(防 nonce reuse 灾难)。"""
    plaintext = "sk-nonce-uniqueness-test"
    cts = set()
    for _ in range(20):
        manager.configure_api_key("openai", plaintext)
        cts.add(manager.api_keys["openai"].enc_api_key)
        # 每次 configure 是覆盖,但 ciphertext 由随机 nonce 决定 → 应不同

    assert len(cts) == 20, f"nonce reuse detected! only {len(cts)} unique ciphertexts"


# ── TEST 9: FieldEncryption from_env 支持 hex / base64 ──────────────────
def test_field_encryption_from_env_supports_hex_and_base64(monkeypatch):
    """环境变量同时支持 64-char hex 和 base64 格式。"""
    key_bytes = secrets.token_bytes(32)

    # hex 格式
    monkeypatch.setenv("TEST_KEY_HEX", key_bytes.hex())
    fe1 = FieldEncryption.from_env("TEST_KEY_HEX")
    assert fe1._key == key_bytes

    # base64 格式
    import base64
    monkeypatch.setenv("TEST_KEY_B64", base64.b64encode(key_bytes).decode())
    fe2 = FieldEncryption.from_env("TEST_KEY_B64")
    assert fe2._key == key_bytes


# ── TEST 10: FieldEncryption from_passphrase 派生确定性 ──────────────────
def test_field_encryption_from_passphrase_is_deterministic():
    """同 passphrase + 同 salt → 同 key(可重现)。"""
    passphrase = "this-is-a-very-strong-test-passphrase-1234!@#"
    salt = b"x" * 16  # 固定 salt
    fe1 = FieldEncryption.from_passphrase(passphrase, salt=salt)
    fe2 = FieldEncryption.from_passphrase(passphrase, salt=salt)
    assert fe1._key == fe2._key
    assert fe1.key_fingerprint == fe2.key_fingerprint

    # 不同 salt → 不同 key
    fe3 = FieldEncryption.from_passphrase(passphrase, salt=b"y" * 16)
    assert fe1._key != fe3._key


# ── TEST 11: 完整 roundtrip — configure → save → reload manager → 解密 ──
def test_full_roundtrip_persistence_and_decrypt(tmp_config_dir, master_key_hex):
    """P10-E / P11-D-2 端到端: configure → save_config → 新 manager 加载 →
    get_api_key 还原。P11-D-2 起磁盘存的是密文, reload 后能解密。"""
    key = bytes.fromhex(master_key_hex)
    plaintext = "sk-roundtrip-secret-v2"

    # 第一次:configure + save(磁盘存密文)
    mgr1 = APIKeyManager(config_dir=tmp_config_dir, master_key=key)
    mgr1.configure_api_key("openai", plaintext)

    # 第二次:新 manager 实例 + 同 master key → 从磁盘加载密文, 解密还原
    mgr2 = APIKeyManager(config_dir=tmp_config_dir, master_key=key)
    assert "openai" in mgr2.api_keys
    # P11-D-2: 磁盘密文被解密, get_api_key 返回原明文
    assert mgr2.get_api_key("openai") == plaintext, (
        "P11-D-2: reloaded manager should decrypt disk ciphertext and "
        "return original plaintext"
    )

    # 第三次:在 mgr2 上重新 configure + 立即读 → 仍正常
    mgr2.configure_api_key("openai", plaintext)
    assert mgr2.get_api_key("openai") == plaintext


# ── TEST 12: remove_api_key 正确清理(密文消失)───────────────────────────
def test_remove_api_key_clears_ciphertext(manager):
    """remove 后,dict 中不再有该 provider 的 entry(包括密文)。"""
    manager.configure_api_key("openai", "sk-remove-test-1")
    assert "openai" in manager.api_keys
    assert manager.api_keys["openai"].enc_api_key

    ok = manager.remove_api_key("openai")
    assert ok is True
    assert "openai" not in manager.api_keys


# ── TEST 13: 多个 provider 独立加密,互不干扰 ───────────────────────────
def test_multiple_providers_encrypt_independently(manager):
    """10 个已知 provider 同时配置,每个 get_api_key 都还原自己。

    Uses real provider names from ``API_KEY_ENV_MAPPING`` because
    ``configure_api_key`` rejects unknown providers. (The encryption
    layer itself has no concept of 'provider' — only AAD — so the
    underlying behavior is the same; we just exercise the manager's
    provider validation path while checking ciphertext independence.)
    """
    real_providers = [
        "openai", "anthropic", "google", "openrouter", "kimi",
        "glm", "deepseek", "minimax", "doubao", "baidu",
    ]
    test_data = {p: f"sk-{p}-" + secrets.token_hex(8) for p in real_providers}
    for p, k in test_data.items():
        assert manager.configure_api_key(p, k) is True, f"failed to configure {p}"

    for p, expected in test_data.items():
        actual = manager.get_api_key(p)
        assert actual == expected, f"{p}: got {actual!r}, expected {expected!r}"


# ── TEST 14: 错误格式的 master key → EncryptionError ─────────────────────
def test_malformed_master_key_raises(tmp_config_dir):
    """既不是 hex 也不是 base64 的字符串 → EncryptionError。

    Note: ``cryptography`` raises a low-level ``ValueError`` when the
    key length is wrong; our ``from_raw_key`` wraps that into
    ``EncryptionError`` for the hex/base64 decode paths, and the
    cryptography ``ValueError`` propagates for the raw-bytes path. We
    accept either to keep the test focused on the user-facing behavior
    (garbage in → loud failure, not silent corruption).
    """
    with pytest.raises((EncryptionError, ValueError)):
        FieldEncryption.from_raw_key("not-a-key-at-all!@#$%^")

    # 长度不对的 hex 字符串(64 char 但只解码 16 字节,余下丢弃)— 应失败
    with pytest.raises((EncryptionError, ValueError)):
        FieldEncryption.from_raw_key("aabbccdd" * 4)  # 32 hex chars = 16 bytes
    with pytest.raises((EncryptionError, ValueError)):
        FieldEncryption.from_raw_key("aabbccddee" * 4)  # 40 hex chars = 20 bytes


# ── TEST 15: allow_test_key=True 在缺 env 时生成 ephemeral key ──────────
def test_allow_test_key_generates_ephemeral_key_when_env_missing(
    tmp_config_dir, monkeypatch
):
    """allow_test_key=True + 无 env → 生成临时 key,manager 正常工作。"""
    monkeypatch.delenv("API_KEY_MASTER_KEY", raising=False)
    mgr = APIKeyManager(config_dir=tmp_config_dir, allow_test_key=True)
    mgr.configure_api_key("openai", "sk-ephemeral-test")
    assert mgr.get_api_key("openai") == "sk-ephemeral-test"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
