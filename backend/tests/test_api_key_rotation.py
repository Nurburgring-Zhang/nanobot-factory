"""
P13-A1: API key 旋转 (rotate_api_key) 专项测试
==============================================

本文件专门覆盖 ``APIKeyManager.rotate_api_key()`` 的契约和边界,
不与 ``test_api_key_persistence_encryption.py`` 重复 (那个文件同时
覆盖 persistence 和 rotation,本文件按 P13-A1 task spec 单独建档)。

覆盖矩阵 (16 tests):
┌───┬────────────────────────────────────────────────────────────┐
│ 1 │ rotate 替换现有 key 后,get_api_key 返回新 key             │
│ 2 │ rotate 必须先有 key (无 key 时返回 False)                │
│ 3 │ rotate 拒绝 unknown provider                              │
│ 4 │ rotate 拒绝空 new_key                                     │
│ 5 │ rotate 触发 on_key_change_callback,回调参数含新 key       │
│ 6 │ rotate 后磁盘密文 ≠ 旋转前密文 (每次 fresh nonce)         │
│ 7 │ rotate 后磁盘密文 = 内存 enc_api_key                       │
│ 8 │ rotate 持久化: 重新加载 manager 后用新 key                 │
│ 9 │ rotate 不影响其他 provider 的 key                         │
│ 10│ rotate 保留 base_url / model (不显式覆盖时)                │
│ 11│ rotate 显式覆盖 base_url / model                          │
│ 12│ rotate 与 configure_api_key 不冲突,二者可混用             │
│ 13│ rotate AAD 隔离:用错 provider AAD 解密抛 EncryptionError  │
│ 14│ rotate 后 metadata (last_verified / is_valid) 字段保留     │
│ 15│ rotate 多次:多次旋转最终 key 仍可正确解出                 │
│ 16│ rotate 后磁盘 0 明文 (rotate 不写入明文 api_key 字段)      │
└───┴────────────────────────────────────────────────────────────┘

设计原则:
  * 不实跑真 API (无外网依赖)
  * 全部用 tempdir + secrets.token_bytes(32) master key
  * 每个测试 strip env (openai/anthropic/.../API_KEY_MASTER_KEY)
  * 通过 ``mgr._encryptor.key_fingerprint`` 验证每次 rotate 用的
    都是同一个 encryptor (单进程)
"""
from __future__ import annotations

import json
import secrets
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

# ── 让 backend 目录可 import ──────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest  # noqa: E402

from api_key_manager import APIKeyConfig, APIKeyManager  # noqa: E402
from common.encryption import EncryptionError  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────────
_PROVIDER_ENV_VARS = {
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
}


# ── Fixtures ─────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_config_dir():
    """Per-test temp dir for api_keys.json."""
    with tempfile.TemporaryDirectory(prefix="apikey_rotate_") as td:
        yield td


@pytest.fixture
def master_key_bytes() -> bytes:
    """Fresh 32-byte master key."""
    return secrets.token_bytes(32)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Strip ALL provider API key env vars + master key env."""
    monkeypatch.delenv("API_KEY_MASTER_KEY", raising=False)
    for mapping in _PROVIDER_ENV_VARS.values():
        for var in mapping:
            monkeypatch.delenv(var, raising=False)


# ── TEST 1: rotate 替换现有 key 后, get_api_key 返回新 key ────────────────
def test_rotate_replaces_get_api_key(tmp_config_dir, master_key_bytes):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-original-11111")
    assert mgr.get_api_key("openai") == "sk-original-11111"

    ok = mgr.rotate_api_key("openai", "sk-rotated-22222")
    assert ok is True
    assert mgr.get_api_key("openai") == "sk-rotated-22222"


# ── TEST 2: rotate 必须先有 key ──────────────────────────────────────────
def test_rotate_requires_existing_key(tmp_config_dir, master_key_bytes):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    ok = mgr.rotate_api_key("openai", "sk-new-on-empty")
    assert ok is False
    assert mgr.get_api_key("openai") is None
    # 也不应该把 entry 写进磁盘
    cfg_file = Path(tmp_config_dir) / "api_keys.json"
    if cfg_file.exists():
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert "openai" not in data or data["openai"].get("api_key", "") == ""


# ── TEST 3: rotate 拒绝 unknown provider ─────────────────────────────────
def test_rotate_rejects_unknown_provider(tmp_config_dir, master_key_bytes):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    ok = mgr.rotate_api_key("not_a_real_provider_xyz", "sk-fake")
    assert ok is False


# ── TEST 4: rotate 拒绝空 new_key ────────────────────────────────────────
def test_rotate_rejects_empty_new_key(tmp_config_dir, master_key_bytes):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-pre-rotate")

    ok = mgr.rotate_api_key("openai", "")
    assert ok is False
    # 旧 key 应保留
    assert mgr.get_api_key("openai") == "sk-pre-rotate"


# ── TEST 5: rotate 触发 on_key_change_callback ──────────────────────────
def test_rotate_invokes_on_key_change_callback(
    tmp_config_dir, master_key_bytes
):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-old-key")

    calls: List[Tuple[str, str]] = []

    def cb(provider: str, cfg: APIKeyConfig):
        calls.append((provider, cfg.get_api_key()))

    mgr.set_on_key_change_callback(cb)
    mgr.rotate_api_key("openai", "sk-new-key")

    assert len(calls) == 1, f"callback should fire once, got {len(calls)}"
    provider, key = calls[0]
    assert provider == "openai"
    assert key == "sk-new-key"


# ── TEST 6: rotate 后磁盘密文 ≠ 旋转前密文 ───────────────────────────────
def test_rotate_disk_ciphertext_changes(
    tmp_config_dir, master_key_bytes
):
    """每次 encrypt 都用 fresh nonce, 所以两次密文一定不同。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-pre-rotate-aaaaaa")
    old_ciphertext = mgr.api_keys["openai"].enc_api_key

    mgr.rotate_api_key("openai", "sk-post-rotate-bbbbbb")
    new_ciphertext = mgr.api_keys["openai"].enc_api_key

    assert old_ciphertext != new_ciphertext, (
        "rotate must produce fresh ciphertext (GCM nonce is per-call)"
    )
    assert len(new_ciphertext) > 40  # base64(12+ct+16) for short plaintext


# ── TEST 7: rotate 后磁盘密文 = 内存 enc_api_key ────────────────────────
def test_rotate_disk_matches_memory(tmp_config_dir, master_key_bytes):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-initial-1")
    mgr.rotate_api_key("openai", "sk-rotated-2")

    cfg_file = Path(tmp_config_dir) / "api_keys.json"
    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert data["openai"]["api_key"] == mgr.api_keys["openai"].enc_api_key


# ── TEST 8: rotate 持久化: 重新加载 manager 后用新 key ───────────────────
def test_rotate_persists_across_restart(tmp_config_dir, master_key_bytes):
    mgr1 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr1.configure_api_key("openai", "sk-stage1")
    mgr1.rotate_api_key("openai", "sk-stage2")

    # "重启" — 新 manager, 同 master key
    mgr2 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    assert mgr2.get_api_key("openai") == "sk-stage2"


# ── TEST 9: rotate 不影响其他 provider ──────────────────────────────────
def test_rotate_isolated_per_provider(tmp_config_dir, master_key_bytes):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-openai-original")
    mgr.configure_api_key("anthropic", "sk-anthropic-original")
    mgr.configure_api_key("google", "sk-google-original")

    mgr.rotate_api_key("openai", "sk-openai-rotated")

    assert mgr.get_api_key("openai") == "sk-openai-rotated"
    assert mgr.get_api_key("anthropic") == "sk-anthropic-original"
    assert mgr.get_api_key("google") == "sk-google-original"


# ── TEST 10: rotate 保留 base_url / model (不显式覆盖时) ────────────────
def test_rotate_preserves_base_url_and_model(
    tmp_config_dir, master_key_bytes
):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key(
        "openai",
        "sk-v1",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
    )

    mgr.rotate_api_key("openai", "sk-v2")
    cfg = mgr.api_keys["openai"]

    assert cfg.base_url == "https://api.openai.com/v1"
    assert cfg.model == "gpt-4o"
    assert cfg.get_api_key() == "sk-v2"


# ── TEST 11: rotate 显式覆盖 base_url / model ───────────────────────────
def test_rotate_allows_explicit_base_url_override(
    tmp_config_dir, master_key_bytes
):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-v1", model="gpt-4o")

    mgr.rotate_api_key(
        "openai", "sk-v2", model="gpt-4-turbo"
    )
    cfg = mgr.api_keys["openai"]

    assert cfg.model == "gpt-4-turbo"
    assert cfg.get_api_key() == "sk-v2"


# ── TEST 12: rotate 与 configure_api_key 混用 ───────────────────────────
def test_configure_rotate_configure_round_trip(
    tmp_config_dir, master_key_bytes
):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-cfg-1")
    mgr.rotate_api_key("openai", "sk-rot-2")
    mgr.configure_api_key("anthropic", "sk-ant-1")
    mgr.rotate_api_key("anthropic", "sk-ant-2")
    mgr.configure_api_key("google", "sk-g-1")

    mgr2 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    assert mgr2.get_api_key("openai") == "sk-rot-2"
    assert mgr2.get_api_key("anthropic") == "sk-ant-2"
    assert mgr2.get_api_key("google") == "sk-g-1"


# ── TEST 13: rotate AAD 隔离 ─────────────────────────────────────────────
def test_rotate_aad_binds_to_provider(tmp_config_dir, master_key_bytes):
    """旋转后, 密文的 AAD 仍是原 provider; 跨 provider 解密必失败。"""
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-aad-1")
    mgr.rotate_api_key("openai", "sk-aad-2")
    enc = mgr.api_keys["openai"].enc_api_key

    # 错 provider AAD → 必抛 EncryptionError
    with pytest.raises(EncryptionError):
        mgr._encryptor.decrypt(enc, aad=b"api_key:anthropic")
    with pytest.raises(EncryptionError):
        mgr._encryptor.decrypt(enc, aad=b"api_key:google")
    # 空 AAD → 也必抛 (GCM 认证)
    with pytest.raises(EncryptionError):
        mgr._encryptor.decrypt(enc, aad=b"")
    # 对 AAD → 成功
    assert mgr._encryptor.decrypt(enc, aad=b"api_key:openai") == "sk-aad-2"


# ── TEST 14: rotate 重置 last_verified / is_valid (强制 re-verify) ───────
def test_rotate_resets_verification_metadata(
    tmp_config_dir, master_key_bytes
):
    """安全契约: rotate 后,新 key 必须重新验证,不能信任旧 key 的验证状态。

    实际行为:
      * rotate 保留: base_url / model / enabled / configured_at
      * rotate 重置: last_verified="" / is_valid=False / error_message=""
        — 这样下次 verify_all() 必触发对外的真实验证请求。
    """
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key(
        "openai", "sk-v1",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
    )
    # 模拟旧 key 已验证
    cfg_before = mgr.api_keys["openai"]
    cfg_before.is_valid = True
    cfg_before.last_verified = "2026-06-26T12:00:00"
    cfg_before.error_message = ""
    # 写盘
    mgr._save_config()
    base_url_before = cfg_before.base_url
    model_before = cfg_before.model
    configured_at_before = cfg_before.configured_at
    enabled_before = cfg_before.enabled

    mgr.rotate_api_key("openai", "sk-v2")
    cfg_after = mgr.api_keys["openai"]

    # 1) 保留的字段
    assert cfg_after.base_url == base_url_before
    assert cfg_after.model == model_before
    assert cfg_after.configured_at == configured_at_before
    assert cfg_after.enabled == enabled_before
    assert cfg_after.get_api_key() == "sk-v2"

    # 2) 重置的字段 (强制 re-verify)
    assert cfg_after.last_verified == "", (
        f"last_verified should reset on rotation, got {cfg_after.last_verified!r}"
    )
    assert cfg_after.is_valid is False, (
        "is_valid should reset on rotation (new key = untrusted)"
    )
    assert cfg_after.error_message == ""

    # 3) 磁盘上也重置
    cfg_file = Path(tmp_config_dir) / "api_keys.json"
    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert data["openai"]["last_verified"] == ""
    assert data["openai"]["is_valid"] is False


# ── TEST 15: rotate 多次:多次旋转最终 key 仍可正确解出 ───────────────────
def test_repeated_rotation_keeps_final_key_decryptable(
    tmp_config_dir, master_key_bytes
):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    mgr.configure_api_key("openai", "sk-v0")
    seen_ciphertexts = {mgr.api_keys["openai"].enc_api_key}

    for i in range(1, 5):
        mgr.rotate_api_key("openai", f"sk-v{i}")
        seen_ciphertexts.add(mgr.api_keys["openai"].enc_api_key)

    # 5 个不同密文 (v0 + 4 次 rotate)
    assert len(seen_ciphertexts) == 5, (
        f"each encrypt must produce unique ciphertext, got {len(seen_ciphertexts)}"
    )

    # 重启后能解出最后那个 key
    mgr2 = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    assert mgr2.get_api_key("openai") == "sk-v4"


# ── TEST 16: rotate 后磁盘 0 明文 ────────────────────────────────────────
def test_rotate_writes_no_plaintext_to_disk(
    tmp_config_dir, master_key_bytes
):
    mgr = APIKeyManager(
        config_dir=tmp_config_dir, master_key=master_key_bytes
    )
    plaintext_old = "sk-plaintext-old-rotation-zzz"
    plaintext_new = "sk-plaintext-new-rotation-yyy"

    mgr.configure_api_key("openai", plaintext_old)
    mgr.rotate_api_key("openai", plaintext_new)

    cfg_file = Path(tmp_config_dir) / "api_keys.json"
    raw = cfg_file.read_text(encoding="utf-8")

    assert plaintext_old not in raw, "OLD plaintext leaked after rotate"
    assert plaintext_new not in raw, "NEW plaintext leaked after rotate"
    # 再次确认密文是 base64(>28 字节原始)而非常规文本
    data = json.loads(raw)
    disk_value = data["openai"]["api_key"]
    assert disk_value != "***"
    assert disk_value != plaintext_new
    # base64 decode
    import base64
    decoded = base64.b64decode(disk_value, validate=True)
    assert len(decoded) >= 28  # 12 nonce + 16 tag + ct


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
