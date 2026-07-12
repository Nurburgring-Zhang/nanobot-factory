"""
P11-D-2: API key 磁盘 JSON 持久化加密 + 旋转 API 测试
======================================================

覆盖维度:
1. 磁盘 JSON 持久化密文(非明文,非 "***")
2. 磁盘 JSON 持久化: 重新加载 manager 后, get_api_key 仍能解出明文
3. 不同 master key 加载 → ciphertext 无法解密(兼容 P10-E)
4. AAD 隔离: 跨 provider 密文不能互用
5. configure_api_key 写盘 → 密文存在
6. remove_api_key 写盘 → 字段清空
7. 旧格式 "***" 仍能加载 (向后兼容)
8. 磁盘 0 明文(grep plaintext not in file)
9. rotate_api_key 替换现有 key
10. rotate_api_key 必须先有 key (空 key 拒绝)
11. rotate_api_key unknown provider 拒绝
12. rotate_api_key 触发 on_key_change_callback
13. rotate_api_key 写盘 → 新密文存在
14. rotate_api_key 持久化: 重新加载后用新 key
15. rotate_api_key 与 configure_api_key 不冲突
16. 多个 provider 独立旋转
17. 错误 master key 加载 → 静默失败 + warning (不抛)
18. 旧 disk 格式 "***" + 新 disk 密文 共存

目标: >= 16 用例 PASS
"""
from __future__ import annotations

import json
import os
import re
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
from common.encryption import EncryptionError, FieldEncryption  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_config_dir():
    """Per-test temp dir for api_keys.json."""
    with tempfile.TemporaryDirectory(prefix="apikey_persist_") as td:
        yield td


@pytest.fixture
def master_key_bytes() -> bytes:
    """Fresh 32-byte master key."""
    return secrets.token_bytes(32)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Strip ALL provider API key env vars + master key env."""
    monkeypatch.delenv("API_KEY_MASTER_KEY", raising=False)
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


# ── TEST 1: 磁盘 JSON 持久化是密文(非明文,非 "***") ─────────────────────
def test_disk_persistence_stores_ciphertext(tmp_config_dir, master_key_bytes):
    """configure 后, 磁盘 api_keys.json 中的 api_key 字段是 AES-256-GCM 密文 (base64)。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    plaintext = "sk-persist-encryption-test-12345"
    mgr.configure_api_key("openai", plaintext)

    config_file = Path(tmp_config_dir) / "api_keys.json"
    assert config_file.exists()

    raw = config_file.read_text(encoding="utf-8")
    data = json.loads(raw)
    disk_value = data["openai"]["api_key"]

    # 必须是 base64 字符串(密文), 不含 "***"
    assert disk_value, "api_key field is empty"
    assert disk_value != "***", f"api_key should be ciphertext, not placeholder: {disk_value!r}"
    assert plaintext not in disk_value, f"plaintext leaked: {disk_value[:80]}"
    # 必须是 base64
    import base64
    try:
        decoded = base64.b64decode(disk_value, validate=True)
        # nonce(12) + tag(16) + ct 至少 28 字节
        assert len(decoded) >= 28, f"ciphertext too short: {len(decoded)}"
    except Exception as exc:
        pytest.fail(f"disk api_key is not valid base64: {exc}")


# ── TEST 2: 磁盘密文 reload 后能解出原明文 ───────────────────────────────
def test_disk_persistence_reload_decrypts_to_plaintext(
    tmp_config_dir, master_key_bytes
):
    """configure → save → 新 manager 加载 → get_api_key 返回明文。"""
    mgr1 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    plaintext = "sk-reload-decrypt-test-67890"
    mgr1.configure_api_key("openai", plaintext)

    # 新 manager 加载 (同 master key)
    mgr2 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    assert mgr2.get_api_key("openai") == plaintext, (
        f"reloaded manager should decrypt the disk ciphertext, got {mgr2.get_api_key('openai')!r}"
    )


# ── TEST 3: 错误 master key 加载 → 静默失败(不抛) ────────────────────────
def test_disk_persistence_wrong_master_key_silent_failure(
    tmp_config_dir, master_key_bytes
):
    """用 key1 写盘, 用 key2 加载 → 加载成功 (manager 不崩), 但 get_api_key 返回 None。"""
    mgr1 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr1.configure_api_key("openai", "sk-master-key-1-secret")

    # 用不同 master key 加载
    other_key = secrets.token_bytes(32)
    mgr2 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=other_key
    )
    # 不应崩
    assert "openai" in mgr2.api_keys
    # 但 api_key 解密失败
    assert mgr2.get_api_key("openai") is None, (
        "wrong master key should not return plaintext"
    )


# ── TEST 4: 旧格式 "***" 仍能加载(向后兼容) ─────────────────────────────
def test_disk_persistence_backward_compat_with_star_mask(tmp_config_dir, master_key_bytes):
    """老版本磁盘的 "***" 字段加载不应崩, 视为空 key。"""
    config_file = Path(tmp_config_dir) / "api_keys.json"
    config_file.write_text(
        json.dumps({
            "openai": {
                "api_key": "***",  # P10-E 时代的占位
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o",
                "enabled": True,
                "configured_at": "2026-01-01T00:00:00",
            },
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    assert "openai" in mgr.api_keys
    # "***" 不应被解释为密文
    assert mgr.get_api_key("openai") is None


# ── TEST 5: remove 后磁盘清空字段 ───────────────────────────────────────
def test_remove_clears_disk_field(tmp_config_dir, master_key_bytes):
    """remove_api_key → 磁盘 api_key 字段应为空, 不残留密文。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-remove-test")

    # 移除
    mgr.remove_api_key("openai")
    config_file = Path(tmp_config_dir) / "api_keys.json"
    data = json.loads(config_file.read_text(encoding="utf-8"))

    # provider entry 应保留 metadata, 但 api_key 字段为空
    if "openai" in data:
        assert data["openai"]["api_key"] == "", (
            f"removed key still on disk: {data['openai']['api_key'][:80]}"
        )


# ── TEST 6: 磁盘 0 明文(grep plaintext) ─────────────────────────────────
def test_disk_no_plaintext_leak(tmp_config_dir, master_key_bytes):
    """所有配置的 provider, 明文 API key 都不应出现在磁盘任何位置。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    secrets_to_set = {
        "openai": "sk-openai-no-leak-aaaaaaaa",
        "anthropic": "sk-ant-no-leak-bbbbbbbb",
        "google": "AIza-google-no-leak-cccccccc",
        "kimi": "sk-kimi-no-leak-dddddddd",
    }
    for p, k in secrets_to_set.items():
        mgr.configure_api_key(p, k)

    config_file = Path(tmp_config_dir) / "api_keys.json"
    raw = config_file.read_text(encoding="utf-8")
    for plain in secrets_to_set.values():
        assert plain not in raw, f"plaintext leaked to disk: {plain!r}"


# ── TEST 7: 旋转 API key - 正常流程 ─────────────────────────────────────
def test_rotate_api_key_replaces_existing_key(tmp_config_dir, master_key_bytes):
    """rotate_api_key 必须用新 key 替换现有 key, get_api_key 返回新值。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    old_key = "sk-old-key-original"
    new_key = "sk-new-key-rotated"

    mgr.configure_api_key("openai", old_key)
    assert mgr.get_api_key("openai") == old_key

    ok = mgr.rotate_api_key("openai", new_key)
    assert ok is True
    assert mgr.get_api_key("openai") == new_key


# ── TEST 8: rotate 必须先有 key (空拒绝) ────────────────────────────────
def test_rotate_api_key_requires_existing_key(tmp_config_dir, master_key_bytes):
    """无现有 key 时 rotate 应返回 False (建议用 configure_api_key)。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    ok = mgr.rotate_api_key("openai", "sk-new-on-empty")
    assert ok is False
    # 不应被错误地创建出来
    assert mgr.get_api_key("openai") is None


# ── TEST 9: rotate unknown provider 拒绝 ────────────────────────────────
def test_rotate_api_key_rejects_unknown_provider(tmp_config_dir, master_key_bytes):
    """rotate unknown provider → False, 不写盘。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    ok = mgr.rotate_api_key("not_a_real_provider_xyz", "sk-fake")
    assert ok is False


# ── TEST 10: rotate 触发 on_key_change_callback ──────────────────────────
def test_rotate_api_key_invokes_callback(tmp_config_dir, master_key_bytes):
    """旋转后, on_key_change_callback 应被调用, 接收新 config。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-old")

    calls = []

    def cb(provider, cfg):
        calls.append((provider, cfg.get_api_key()))

    mgr.set_on_key_change_callback(cb)
    mgr.rotate_api_key("openai", "sk-new")

    assert len(calls) == 1
    provider, key = calls[0]
    assert provider == "openai"
    assert key == "sk-new"


# ── TEST 11: rotate 写盘 → 新密文存在 ───────────────────────────────────
def test_rotate_api_key_persists_new_ciphertext(tmp_config_dir, master_key_bytes):
    """旋转后, 磁盘 api_keys.json 含新密文(不是旧密文,不是明文)。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-rotation-old-12345")
    old_ciphertext = mgr.api_keys["openai"].enc_api_key

    mgr.rotate_api_key("openai", "sk-rotation-new-67890")
    new_ciphertext = mgr.api_keys["openai"].enc_api_key

    # 两次密文不同
    assert old_ciphertext != new_ciphertext
    # 都不含明文
    assert "sk-rotation-old" not in new_ciphertext
    assert "sk-rotation-new" not in new_ciphertext

    # 磁盘密文 = 内存密文
    config_file = Path(tmp_config_dir) / "api_keys.json"
    data = json.loads(config_file.read_text(encoding="utf-8"))
    assert data["openai"]["api_key"] == new_ciphertext


# ── TEST 12: rotate 持久化: 重新加载后用新 key ───────────────────────────
def test_rotate_api_key_persists_across_reload(tmp_config_dir, master_key_bytes):
    """rotate → 重新加载 manager → get_api_key 返回新 key。"""
    mgr1 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr1.configure_api_key("openai", "sk-pre-rotate-11111")
    mgr1.rotate_api_key("openai", "sk-post-rotate-22222")

    mgr2 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    assert mgr2.get_api_key("openai") == "sk-post-rotate-22222"


# ── TEST 13: 多个 provider 独立旋转 ─────────────────────────────────────
def test_rotate_independent_per_provider(tmp_config_dir, master_key_bytes):
    """旋转一个 provider 不影响其他 provider。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-openai-v1")
    mgr.configure_api_key("anthropic", "sk-anthropic-v1")

    mgr.rotate_api_key("openai", "sk-openai-v2")

    assert mgr.get_api_key("openai") == "sk-openai-v2"
    assert mgr.get_api_key("anthropic") == "sk-anthropic-v1", (
        "rotating one provider must not affect another"
    )


# ── TEST 14: rotate 不与 configure 冲突 ─────────────────────────────────
def test_configure_then_rotate_round_trip(tmp_config_dir, master_key_bytes):
    """configure → rotate → 重新加载 → configure 新 provider → reload 全部正常。"""
    mgr1 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr1.configure_api_key("openai", "sk-1")
    mgr1.rotate_api_key("openai", "sk-2")
    mgr1.configure_api_key("anthropic", "sk-ant-1")

    mgr2 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    assert mgr2.get_api_key("openai") == "sk-2"
    assert mgr2.get_api_key("anthropic") == "sk-ant-1"


# ── TEST 15: AAD 隔离 — 旋转的密文 AAD 仍是原 provider ─────────────────
def test_rotation_preserves_aad_binding(tmp_config_dir, master_key_bytes):
    """rotate 后, enc_api_key 的 AAD 仍绑定到原 provider。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-aad-v1")
    mgr.rotate_api_key("openai", "sk-aad-v2")

    enc = mgr.api_keys["openai"].enc_api_key

    # 用 anthropic 的 AAD 尝试解 → 失败
    with pytest.raises(EncryptionError):
        mgr._encryptor.decrypt(enc, aad=b"api_key:anthropic")

    # 用 openai 的 AAD 成功
    assert mgr._encryptor.decrypt(enc, aad=b"api_key:openai") == "sk-aad-v2"


# ── TEST 16: 错误 master key rotate 拒绝 (仍然 fail-fast 在 init 时) ───
def test_wrong_master_key_blocks_rotation_init(tmp_config_dir, monkeypatch):
    """用错 master key init manager → 仍 fail-fast (如果 env 模式)。"""
    # 不设置 master key, 也不允许 ephemeral
    monkeypatch.delenv("API_KEY_MASTER_KEY", raising=False)
    with pytest.raises((EncryptionError, RuntimeError)):
        APIKeyManager(config_dir=tmp_config_dir, allow_test_key=False)


# ── TEST 17: 磁盘格式包含元数据 (last_verified / is_valid) ───────────────
def test_disk_persistence_includes_metadata(tmp_config_dir, master_key_bytes):
    """磁盘 JSON 应包含 last_verified / is_valid 字段(为 P11+ audit 做准备)。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-meta-test")

    config_file = Path(tmp_config_dir) / "api_keys.json"
    data = json.loads(config_file.read_text(encoding="utf-8"))

    assert "last_verified" in data["openai"]
    assert "is_valid" in data["openai"]


# ── TEST 18: 旧 disk 格式 ("***" + 缺字段) 加载后调用 rotate 应正常工作 ─
def test_legacy_disk_then_rotate(tmp_config_dir, master_key_bytes):
    """旧版 "***" 加载(视为空) → configure → rotate → 磁盘密文正确。"""
    config_file = Path(tmp_config_dir) / "api_keys.json"
    config_file.write_text(
        json.dumps({
            "openai": {
                "api_key": "***",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o",
                "enabled": True,
            },
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    mgr1 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    # "***" 视为空, 所以先 configure
    mgr1.configure_api_key("openai", "sk-from-legacy-1")
    mgr1.rotate_api_key("openai", "sk-from-legacy-2")

    mgr2 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    assert mgr2.get_api_key("openai") == "sk-from-legacy-2"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
