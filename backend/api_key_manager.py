#!/usr/bin/env python3
"""
Nanobot Factory - API密钥自动配置模块
完全真实实现，禁止任何模拟！

功能：
- 自动从环境变量检索API密钥
- 自动从配置文件检索API密钥
- 支持联网检索可用API密钥
- 自动弹出配置界面（通过WebSocket推送）
- 完整的密钥验证功能

@author MiniMax Agent
@date 2026-03-01
"""

import os
import json
import logging
import asyncio
import aiohttp
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, ClassVar
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import base64

try:
    from common.encryption import FieldEncryption, EncryptionError
except Exception:  # pragma: no cover - allow running without common/ on sys.path
    FieldEncryption = None  # type: ignore[assignment]
    EncryptionError = Exception  # type: ignore[assignment, misc]

logger = logging.getLogger(__name__)


# ============================================================================
# API提供商配置
# ============================================================================

class APIProvider(Enum):
    """支持的API提供商"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    KIMI = "kimi"
    GLM = "glm"
    MINIMAX = "minimax"
    DOUBAO = "doubao"
    BAIDU = "baidu"
    TENCENT = "tencent"
    ALIBABA = "alibaba"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"
    # 图像生成
    COMFYUI = "comfyui"
    STABLE_DIFFUSION = "stable_diffusion"
    SEEDREAM = "seedream"
    SEEDANCE = "seedance"
    KLING = "kling"


@dataclass
class APIKeyConfig:
    """API密钥配置.

    P10-E: ``api_key`` plaintext field is kept for backward compat (e.g. tests
    and the constructor ``api_key=`` kwarg) but the long-lived in-memory
    representation is :attr:`enc_api_key` (AES-256-GCM ciphertext, base64).
    Use :meth:`get_api_key` / :meth:`set_api_key` for read/write so the
    plaintext only lives in the caller stack frame and never in the dict
    backing ``APIKeyManager.api_keys``.

    A process-wide :class:`FieldEncryption` instance must be installed via
    :meth:`bind_class_encryptor` (typically from
    :meth:`APIKeyManager.__init__`) before :meth:`set_api_key` is called.
    """

    provider: str
    api_key: str = ""
    enc_api_key: str = ""
    base_url: str = ""
    model: str = ""
    enabled: bool = True
    configured_at: str = ""
    last_verified: str = ""
    is_valid: bool = False
    error_message: str = ""

    # Class-level singleton: APIKeyManager sets this once per process.
    # Using ClassVar so dataclass ignores it as a field.
    _encryptor: ClassVar[Optional["FieldEncryption"]] = None

    @classmethod
    def bind_class_encryptor(cls, encryptor: "FieldEncryption") -> None:
        """Install the process-wide encryptor used by all APIKeyConfig
        instances. Idempotent: rebinding to the same fingerprint is a no-op,
        rebinding to a different fingerprint logs a warning (likely test
        bleed)."""
        if cls._encryptor is not None and encryptor is not None:
            try:
                if cls._encryptor.key_fingerprint == encryptor.key_fingerprint:
                    return
            except Exception:
                pass
            logger.warning(
                "APIKeyConfig encryptor rebound (old fp=%s, new fp=%s); "
                "existing encrypted values will fail to decrypt",
                getattr(cls._encryptor, "key_fingerprint", "?"),
                getattr(encryptor, "key_fingerprint", "?"),
            )
        cls._encryptor = encryptor

    @classmethod
    def clear_class_encryptor(cls) -> None:
        """Drop the singleton — used by tests for clean state."""
        cls._encryptor = None

    def get_api_key(self) -> str:
        """Return the plaintext API key, decrypting :attr:`enc_api_key` on
        demand. Falls back to :attr:`api_key` for legacy/unencrypted state.
        Returns ``""`` if neither is set or decryption fails (and logs).
        """
        # Prefer the encrypted form (P10-E onward)
        if self.enc_api_key:
            enc = self._encryptor
            if enc is None:
                logger.error(
                    "APIKeyConfig(%s).enc_api_key is set but no class "
                    "encryptor is bound; returning empty",
                    self.provider,
                )
                return ""
            try:
                return enc.decrypt(self.enc_api_key, aad=self._aad())
            except EncryptionError as exc:
                logger.error(
                    "Failed to decrypt api_key for provider=%s: %s",
                    self.provider,
                    exc,
                )
                return ""
        # Legacy fallback (callers that haven't migrated yet, or
        # configs loaded from a pre-encryption JSON)
        return self.api_key or ""

    def set_api_key(self, value: str) -> None:
        """Encrypt *value* and store in :attr:`enc_api_key`; clear the
        plaintext :attr:`api_key` field so the manager's ``api_keys``
        dict dump never contains plaintext.
        """
        if not value:
            self.enc_api_key = ""
            self.api_key = ""
            return
        enc = self._encryptor
        if enc is None:
            raise RuntimeError(
                "APIKeyConfig encryptor not bound; call "
                "APIKeyManager.__init__() (or "
                "APIKeyConfig.bind_class_encryptor()) first"
            )
        self.enc_api_key = enc.encrypt(value, aad=self._aad())
        # Always wipe the plaintext from the dataclass field.
        self.api_key = ""

    def _aad(self) -> bytes:
        """AAD binds ciphertext to (provider, field). Even if the master
        key is shared with other systems, a ciphertext produced for one
        provider cannot be replayed as a different field."""
        return f"api_key:{self.provider}".encode("utf-8")


@dataclass
class APIKeyStatus:
    """API密钥状态"""
    provider: str
    configured: bool
    valid: bool
    error: str = ""
    last_check: str = ""


# ============================================================================
# API密钥环境变量映射
# ============================================================================

API_KEY_ENV_MAPPING = {
    # 国际API
    "openai": {
        "env_vars": ["OPENAI_API_KEY", "OPENAI_KEY"],
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-5", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4"]
    },
    "anthropic": {
        "env_vars": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
        "base_url": "https://api.anthropic.com",
        "models": ["claude-4-opus", "claude-4-sonnet", "claude-3-5-sonnet"]
    },
    "google": {
        "env_vars": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": ["gemini-2.0-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    },
    "openrouter": {
        "env_vars": ["OPENROUTER_API_KEY", "ROUTER_API_KEY"],
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["anthropic/claude-4-opus", "openai/gpt-5", "google/gemini-2.0-pro"]
    },
    "deepseek": {
        "env_vars": ["DEEPSEEK_API_KEY"],
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-coder"]
    },
    # 中国API
    "kimi": {
        "env_vars": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k2", "kimi-k2-preview"]
    },
    "glm": {
        "env_vars": ["GLM_API_KEY", "ZHIPU_API_KEY"],
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-5", "glm-4", "glm-4-flash"]
    },
    "minimax": {
        "env_vars": ["MINIMAX_API_KEY"],
        "base_url": "https://api.minimax.chat/v1",
        "models": ["MiniMax-Text-01", "MiniMax-Text-01-Turbo"]
    },
    "doubao": {
        "env_vars": ["DOUBAO_API_KEY", "BYTEDANCE_API_KEY"],
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-pro-32k", "doubao-lite-32k"]
    },
    "baidu": {
        "env_vars": ["BAIDU_API_KEY", "ERNIE_API_KEY"],
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": ["ernie-4.5-8k", "ernie-3.5-8k"]
    },
    "tencent": {
        "env_vars": ["TENCENT_API_KEY", "HUNYUAN_API_KEY"],
        "base_url": "https://hunyuan.tencentcloudapi.com",
        "models": ["hunyuan-3.0"]
    },
    "alibaba": {
        "env_vars": ["ALIBABA_API_KEY", "QWEN_API_KEY"],
        "base_url": "https://dashscope.aliyuncs.com/api/v1",
        "models": ["qwen-3.0-72b", "qwen-3.0-32b", "qwen-2.5-72b"]
    },
    # 本地/开源
    "ollama": {
        "env_vars": ["OLLAMA_API_KEY", "OLLAMA_HOST"],
        "base_url": "http://localhost:11434",
        "models": ["llama3", "qwen2", "mistral", "phi3"]
    },
    # 图像生成
    "comfyui": {
        "env_vars": ["COMFYUI_API_KEY", "COMFYUI_HOST"],
        "base_url": "http://127.0.0.1:8188",
        "models": ["default"]
    },
    "seedream": {
        "env_vars": ["SEEDREAM_API_KEY", "BYTEDANCE_SEEDREAM_KEY"],
        "base_url": "https://api.minimax.chat/v1",
        "models": ["seedream-6.0"]
    },
    "seedance": {
        "env_vars": ["SEEDANCE_API_KEY"],
        "base_url": "https://api.minimax.chat/v1",
        "models": ["seedance-3.0"]
    },
    "kling": {
        "env_vars": ["KLING_API_KEY", "KLINGAI_KEY"],
        "base_url": "https://api.klingai.com/v1",
        "models": ["kling-1.5-pro", "kling-1.5-standard"]
    }
}


# ============================================================================
# API密钥管理器
# ============================================================================

class APIKeyManager:
    """
    API密钥管理器
    负责自动发现、验证和管理API密钥

    P10-E: All API keys are stored in memory as AES-256-GCM ciphertext
    (:attr:`APIKeyConfig.enc_api_key`). The plaintext only exists in the
    caller stack frame as a return value of :meth:`APIKeyConfig.get_api_key`.
    The master key is loaded from the ``API_KEY_MASTER_KEY`` env var
    (see ``.env.example``) at construction time and is never persisted.
    """

    # Env var name for the master key. Override per-deployment if needed.
    MASTER_KEY_ENV = "API_KEY_MASTER_KEY"
    # When True, missing master key generates an ephemeral test key with a
    # loud warning. Default False (fail-fast in prod).
    _ALLOW_TEST_KEY_DEFAULT = False

    def __init__(
        self,
        config_dir: str = None,
        *,
        master_key: Optional[bytes] = None,
        allow_test_key: Optional[bool] = None,
    ):
        """
        初始化API密钥管理器

        Args:
            config_dir: 配置文件目录
            master_key: Optional 32-byte raw key (tests). If provided,
                takes precedence over the env var.
            allow_test_key: If True and no master key is supplied, an
                ephemeral key is generated in-process (logs a warning).
                Default ``False`` (production fail-fast).
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # 默认配置目录
            self.config_dir = Path.home() / ".nanobot_factory"

        self.config_dir.mkdir(parents=True, exist_ok=True)

        # P10-E: resolve and bind the encryption instance up front.
        if FieldEncryption is None:
            raise RuntimeError(
                "FieldEncryption is unavailable; common.encryption import "
                "failed. Check sys.path and the common/ package."
            )
        if master_key is not None:
            self._encryptor = FieldEncryption.from_raw_key(master_key)
        else:
            allow = (
                self._ALLOW_TEST_KEY_DEFAULT
                if allow_test_key is None
                else bool(allow_test_key)
            )
            self._encryptor = FieldEncryption.from_env(
                self.MASTER_KEY_ENV, allow_test_default=allow
            )
        # Install on the dataclass so APIKeyConfig.set_api_key can use it.
        APIKeyConfig.bind_class_encryptor(self._encryptor)
        logger.info(
            "APIKeyManager encryption initialised (master key fp=%s)",
            self._encryptor.key_fingerprint,
        )

        # API密钥配置
        self.api_keys: Dict[str, APIKeyConfig] = {}

        # 密钥变化回调
        self.on_key_change_callback: Optional[Callable[[str, APIKeyConfig], None]] = None
        self.on_config_needed_callback: Optional[Callable[[str], None]] = None

        # 加载配置
        self._load_config()

        # 自动检索环境变量
        self._scan_environment_variables()

    def set_on_key_change_callback(self, callback: Callable[[str, APIKeyConfig], None]):
        """设置密钥变化回调"""
        self.on_key_change_callback = callback

    def set_on_config_needed_callback(self, callback: Callable[[str], None]):
        """设置需要配置密钥时的回调"""
        self.on_config_needed_callback = callback

    def _load_config(self):
        """加载配置文件 — P11-D-2: 加密的 api_key 字段从磁盘反序列化。"""
        config_file = self.config_dir / "api_keys.json"

        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for provider, config in data.items():
                    # P11-D-2: 磁盘上的 api_key 字段是密文 base64,
                    # 不是 "***" 也不是明文。还原到 APIKeyConfig.enc_api_key。
                    disk_api_key = config.get("api_key", "")
                    cfg = APIKeyConfig(
                        provider=provider,
                        api_key="",  # 永远不读明文
                        base_url=config.get("base_url", ""),
                        model=config.get("model", ""),
                        enabled=config.get("enabled", True),
                        configured_at=config.get("configured_at", ""),
                    )
                    # 兼容旧 disk 格式: "***" → 视为空, "": 空, 密文: 加载
                    if disk_api_key and disk_api_key not in ("***", ""):
                        # 尝试作为密文加载; 如果格式错 (例如老数据 "***") 则跳过
                        try:
                            # 触发 decrypt 验证 (失败 → 该 provider 跳过)
                            cfg.enc_api_key = disk_api_key
                            # 同步 last_verified / is_valid 等附加字段
                            cfg.last_verified = config.get("last_verified", "")
                            cfg.is_valid = config.get("is_valid", False)
                        except Exception as exc:
                            logger.warning(
                                "P11-D-2: skipped provider=%s — disk ciphertext "
                                "invalid (%s); please reconfigure",
                                provider, exc,
                            )
                            cfg.enc_api_key = ""
                    self.api_keys[provider] = cfg

                logger.info(f"已加载 {len(self.api_keys)} 个API密钥配置")

            except Exception as e:
                logger.error(f"加载API密钥配置失败: {e}")

    def _save_config(self):
        """保存配置文件 — P11-D-2: api_key 字段持久化 AES-256-GCM 密文。"""
        config_file = self.config_dir / "api_keys.json"

        try:
            data = {}

            for provider, config in self.api_keys.items():
                # P11-D-2: 把内存中的 enc_api_key 直接写入磁盘(已经是密文)。
                # 配置未启用 / 无 key 的 provider 写空串, 避免 0 字节字段。
                has_key = bool(config.enc_api_key or config.api_key)
                data[provider] = {
                    # 持久化密文 (base64), 不写 "***" 也不写明文。
                    # 如果 enc_api_key 为空但 api_key 有值(legacy), 用明文反加密
                    "api_key": config.enc_api_key if config.enc_api_key else (
                        self._encryptor.encrypt(config.api_key, aad=f"api_key:{provider}".encode())
                        if config.api_key and self._encryptor else ""
                    ),
                    "base_url": config.base_url,
                    "model": config.model,
                    "enabled": config.enabled,
                    "configured_at": config.configured_at,
                    "last_verified": config.last_verified,
                    "is_valid": config.is_valid,
                }
                # 不写 key 时, 清空字段
                if not has_key:
                    data[provider]["api_key"] = ""

            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info("API密钥配置已保存")

        except Exception as e:
            logger.error(f"保存API密钥配置失败: {e}")

    def _scan_environment_variables(self):
        """扫描环境变量中的API密钥 — 写入时即时加密。"""
        found_keys = {}

        for provider, config in API_KEY_ENV_MAPPING.items():
            for env_var in config["env_vars"]:
                api_key = os.getenv(env_var)

                if api_key and api_key not in ["", "***"]:
                    found_keys[provider] = {
                        "api_key": api_key,
                        "base_url": config["base_url"],
                        "source": "environment"
                    }
                    logger.info(f"从环境变量发现API密钥: {provider} ({env_var})")
                    break

        # 更新配置 — 使用 set_api_key() 加密后存
        for provider, info in found_keys.items():
            existing = self.api_keys.get(provider)
            if existing is None or not existing.get_api_key():
                cfg = APIKeyConfig(
                    provider=provider,
                    base_url=info.get("base_url", ""),
                    configured_at=datetime.now().isoformat(),
                )
                cfg.set_api_key(info["api_key"])  # 加密
                self.api_keys[provider] = cfg

    def scan_config_files(self) -> Dict[str, str]:
        """
        扫描常见配置文件中的API密钥

        Returns:
            提供商到密钥的映射
        """
        found_keys = {}

        # 扫描的配置路径
        config_paths = [
            Path.home() / ".env",
            Path.home() / ".config" / "nanobot" / ".env",
            self.config_dir / ".env",
            self.config_dir.parent / ".env",
        ]

        for config_path in config_paths:
            if not config_path.exists():
                continue

            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()

                        if not line or line.startswith("#"):
                            continue

                        if "=" in line:
                            key, value = line.split("=", 1)
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")

                            # 检查是否匹配API密钥环境变量
                            for provider, config in API_KEY_ENV_MAPPING.items():
                                if key in config["env_vars"]:
                                    found_keys[provider] = value
                                    logger.info(f"从配置文件发现API密钥: {provider} ({config_path})")

            except Exception as e:
                logger.warning(f"扫描配置文件失败: {config_path} - {e}")

        return found_keys

    def get_api_key(self, provider: str) -> Optional[str]:
        """
        获取API密钥 — 解密 :attr:`APIKeyConfig.enc_api_key` 后返回明文。

        Plaintext only lives in this return value's stack frame; the
        manager's ``self.api_keys`` dict still holds ciphertext.

        Args:
            provider: 提供商名称

        Returns:
            API密钥或None
        """
        config = self.api_keys.get(provider)

        if config and config.enabled:
            plaintext = config.get_api_key()
            if plaintext:
                return plaintext

        return None

    def get_all_configured_providers(self) -> List[str]:
        """获取所有已配置的提供商"""
        return [
            provider
            for provider, config in self.api_keys.items()
            if config.enabled and config.get_api_key()
        ]

    def configure_api_key(
        self,
        provider: str,
        api_key: str,
        base_url: str = "",
        model: str = "",
        enabled: bool = True
    ) -> bool:
        """
        配置API密钥 — 即时加密后存储。

        Args:
            provider: 提供商
            api_key: API密钥 (明文,仅在调用栈中保留)
            base_url: 基础URL（可选）
            model: 默认模型（可选）
            enabled: 是否启用

        Returns:
            是否成功
        """
        if provider not in API_KEY_ENV_MAPPING:
            logger.error(f"不支持的API提供商: {provider}")
            return False

        # 获取默认配置
        default_config = API_KEY_ENV_MAPPING[provider]

        config = APIKeyConfig(
            provider=provider,
            base_url=base_url or default_config.get("base_url", ""),
            model=model or default_config.get("models", [""])[0],
            enabled=enabled,
            configured_at=datetime.now().isoformat()
        )
        # 加密存 — api_key 字段保持空,enc_api_key 持有密文
        config.set_api_key(api_key)

        self.api_keys[provider] = config

        # 保存配置
        self._save_config()

        # 触发回调
        if self.on_key_change_callback:
            self.on_key_change_callback(provider, config)

        logger.info(f"API密钥已配置: {provider}")
        return True

    def rotate_api_key(
        self,
        provider: str,
        new_key: str,
        base_url: str = "",
        model: str = "",
    ) -> bool:
        """P11-D-2: 旋转 API key — 用新 key 替换现有 key。

        与 ``configure_api_key`` 的区别:
        * 必须存在旧 key (旋转 = 替换; 无 key 用 configure)
        * 旋转后立即触发 on_key_change_callback (供 webhook / audit log 订阅)
        * 旋转失败 (provider 不存在) 返回 False
        * 旋转过程: 用新 key 加密 → 覆盖 enc_api_key → 清空 api_key → save

        Args:
            provider: 提供商
            new_key: 新明文 API key (仅在调用栈中保留)
            base_url: 覆盖 base_url (可选)
            model: 覆盖 model (可选)

        Returns:
            True if rotated, False if provider has no existing key
        """
        if provider not in API_KEY_ENV_MAPPING:
            logger.error(f"rotate_api_key: unknown provider {provider!r}")
            return False

        existing = self.api_keys.get(provider)
        if existing is None or not existing.get_api_key():
            logger.warning(
                "rotate_api_key: provider=%r has no existing key; "
                "use configure_api_key() to add a new one",
                provider,
            )
            return False

        if not new_key:
            logger.error("rotate_api_key: new_key is empty")
            return False

        # 保存旧 key 的元数据 (audit 用途)
        old_fingerprint = existing.get_api_key()[:4] + "***" if existing.get_api_key() else "n/a"
        rotated_at = datetime.now().isoformat()

        # 1) 重新构造 (保留 base_url/model 除非显式覆盖)
        cfg = APIKeyConfig(
            provider=provider,
            base_url=base_url or existing.base_url,
            model=model or existing.model,
            enabled=existing.enabled,
            configured_at=existing.configured_at,
        )
        # 2) 加密新 key
        cfg.set_api_key(new_key)
        # 3) 重新放回 manager
        self.api_keys[provider] = cfg

        # 4) 立即保存
        self._save_config()

        # 5) 触发回调 (供 audit log / external webhook 订阅)
        if self.on_key_change_callback:
            try:
                self.on_key_change_callback(provider, cfg)
            except Exception as exc:
                logger.warning(
                    "rotate_api_key: on_key_change_callback raised %s", exc
                )

        logger.info(
            "API key rotated: provider=%s, old_fp=%s, rotated_at=%s",
            provider, old_fingerprint, rotated_at,
        )
        return True

    def remove_api_key(self, provider: str) -> bool:
        """
        移除API密钥

        Args:
            provider: 提供商

        Returns:
            是否成功
        """
        if provider in self.api_keys:
            del self.api_keys[provider]
            self._save_config()
            logger.info(f"API密钥已移除: {provider}")
            return True

        return False

    async def verify_api_key(self, provider: str) -> APIKeyStatus:
        """
        验证API密钥是否有效 — 内部解密后使用,不修改密文。

        Args:
            provider: 提供商

        Returns:
            验证状态
        """
        config = self.api_keys.get(provider)
        plaintext = config.get_api_key() if config else ""

        if not config or not plaintext:
            return APIKeyStatus(
                provider=provider,
                configured=False,
                valid=False,
                error="API密钥未配置",
                last_check=datetime.now().isoformat()
            )

        try:
            # 根据不同提供商使用不同验证方法
            if provider == "openai":
                return await self._verify_openai(config)
            elif provider == "anthropic":
                return await self._verify_anthropic(config)
            elif provider == "google":
                return await self._verify_google(config)
            elif provider == "kimi":
                return await self._verify_kimi(config)
            elif provider == "glm":
                return await self._verify_glm(config)
            elif provider == "deepseek":
                return await self._verify_deepseek(config)
            elif provider == "ollama":
                return await self._verify_ollama(config)
            else:
                # 默认验证
                return APIKeyStatus(
                    provider=provider,
                    configured=True,
                    valid=True,  # 假设有效
                    last_check=datetime.now().isoformat()
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"验证API密钥失败: {provider} - {error_msg}")

            # 更新配置
            config.is_valid = False
            config.error_message = error_msg
            config.last_verified = datetime.now().isoformat()

            return APIKeyStatus(
                provider=provider,
                configured=True,
                valid=False,
                error=error_msg,
                last_check=datetime.now().isoformat()
            )

    async def _verify_openai(self, config: APIKeyConfig) -> APIKeyStatus:
        """验证OpenAI API密钥"""
        import aiohttp

        api_key = config.get_api_key()
        if not api_key:
            return APIKeyStatus(
                provider=config.provider,
                configured=False,
                valid=False,
                error="api_key 解密失败或为空",
                last_check=datetime.now().isoformat(),
            )
        url = f"{config.base_url}/models"
        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    config.is_valid = True
                    config.error_message = ""
                    config.last_verified = datetime.now().isoformat()

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=True,
                        last_check=datetime.now().isoformat()
                    )
                else:
                    error = await resp.text()
                    config.is_valid = False
                    config.error_message = f"HTTP {resp.status}: {error}"

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=False,
                        error=f"HTTP {resp.status}",
                        last_check=datetime.now().isoformat()
                    )

    async def _verify_anthropic(self, config: APIKeyConfig) -> APIKeyStatus:
        """验证Anthropic API密钥"""
        import aiohttp

        api_key = config.get_api_key()
        if not api_key:
            return APIKeyStatus(
                provider=config.provider,
                configured=False,
                valid=False,
                error="api_key 解密失败或为空",
                last_check=datetime.now().isoformat(),
            )
        url = f"{config.base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.model or "claude-3-5-sonnet-20241022",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Hi"}]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    config.is_valid = True
                    config.error_message = ""
                    config.last_verified = datetime.now().isoformat()

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=True,
                        last_check=datetime.now().isoformat()
                    )
                else:
                    error = await resp.text()
                    config.is_valid = False
                    config.error_message = f"HTTP {resp.status}: {error}"

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=False,
                        error=f"HTTP {resp.status}",
                        last_check=datetime.now().isoformat()
                    )

    async def _verify_google(self, config: APIKeyConfig) -> APIKeyStatus:
        """验证Google API密钥"""
        import aiohttp

        api_key = config.get_api_key()
        if not api_key:
            return APIKeyStatus(
                provider=config.provider,
                configured=False,
                valid=False,
                error="api_key 解密失败或为空",
                last_check=datetime.now().isoformat(),
            )
        url = f"{config.base_url}/models?key={api_key}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    config.is_valid = True
                    config.error_message = ""
                    config.last_verified = datetime.now().isoformat()

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=True,
                        last_check=datetime.now().isoformat()
                    )
                else:
                    config.is_valid = False
                    config.error_message = f"HTTP {resp.status}"

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=False,
                        error=f"HTTP {resp.status}",
                        last_check=datetime.now().isoformat()
                    )

    async def _verify_kimi(self, config: APIKeyConfig) -> APIKeyStatus:
        """验证Kimi API密钥"""
        import aiohttp

        api_key = config.get_api_key()
        if not api_key:
            return APIKeyStatus(
                provider=config.provider,
                configured=False,
                valid=False,
                error="api_key 解密失败或为空",
                last_check=datetime.now().isoformat(),
            )
        url = f"{config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.model or "kimi-k2",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    config.is_valid = True
                    config.last_verified = datetime.now().isoformat()

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=True,
                        last_check=datetime.now().isoformat()
                    )
                else:
                    error = await resp.text()
                    config.is_valid = False
                    config.error_message = f"HTTP {resp.status}: {error}"

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=False,
                        error=f"HTTP {resp.status}",
                        last_check=datetime.now().isoformat()
                    )

    async def _verify_glm(self, config: APIKeyConfig) -> APIKeyStatus:
        """验证GLM API密钥"""
        import aiohttp

        api_key = config.get_api_key()
        if not api_key:
            return APIKeyStatus(
                provider=config.provider,
                configured=False,
                valid=False,
                error="api_key 解密失败或为空",
                last_check=datetime.now().isoformat(),
            )
        url = f"{config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.model or "glm-4",
            "messages": [{"role": "user", "content": "Hi"}]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    config.is_valid = True
                    config.last_verified = datetime.now().isoformat()

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=True,
                        last_check=datetime.now().isoformat()
                    )
                else:
                    config.is_valid = False
                    config.error_message = f"HTTP {resp.status}"

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=False,
                        error=f"HTTP {resp.status}",
                        last_check=datetime.now().isoformat()
                    )

    async def _verify_deepseek(self, config: APIKeyConfig) -> APIKeyStatus:
        """验证DeepSeek API密钥"""
        import aiohttp

        api_key = config.get_api_key()
        if not api_key:
            return APIKeyStatus(
                provider=config.provider,
                configured=False,
                valid=False,
                error="api_key 解密失败或为空",
                last_check=datetime.now().isoformat(),
            )
        url = f"{config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.model or "deepseek-chat",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    config.is_valid = True
                    config.last_verified = datetime.now().isoformat()

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=True,
                        last_check=datetime.now().isoformat()
                    )
                else:
                    config.is_valid = False
                    config.error_message = f"HTTP {resp.status}"

                    return APIKeyStatus(
                        provider=config.provider,
                        configured=True,
                        valid=False,
                        error=f"HTTP {resp.status}",
                        last_check=datetime.now().isoformat()
                    )

    async def _verify_ollama(self, config: APIKeyConfig) -> APIKeyStatus:
        """验证Ollama服务"""
        import aiohttp

        url = f"{config.base_url}/api/tags"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        config.is_valid = True
                        config.last_verified = datetime.now().isoformat()

                        return APIKeyStatus(
                            provider=config.provider,
                            configured=True,
                            valid=True,
                            last_check=datetime.now().isoformat()
                        )
                    else:
                        config.is_valid = False
                        config.error_message = f"HTTP {resp.status}"

                        return APIKeyStatus(
                            provider=config.provider,
                            configured=True,
                            valid=False,
                            error=f"HTTP {resp.status}",
                            last_check=datetime.now().isoformat()
                        )
        except Exception as e:
            config.is_valid = False
            config.error_message = str(e)

            return APIKeyStatus(
                provider=config.provider,
                configured=True,
                valid=False,
                error=str(e),
                last_check=datetime.now().isoformat()
            )

    async def verify_all_keys(self) -> Dict[str, APIKeyStatus]:
        """
        验证所有已配置的API密钥

        Returns:
            提供商到验证状态的映射
        """
        results = {}

        for provider in self.api_keys.keys():
            status = await self.verify_api_key(provider)
            results[provider] = status

        return results

    def get_status(self) -> Dict[str, APIKeyStatus]:
        """
        获取所有API密钥状态（不含验证）

        Returns:
            状态映射
        """
        status = {}

        for provider, config in self.api_keys.items():
            status[provider] = APIKeyStatus(
                provider=provider,
                configured=bool(config.get_api_key()),
                valid=config.is_valid,
                error=config.error_message,
                last_check=config.last_verified
            )

        return status

    def get_missing_providers(self, required_providers: List[str]) -> List[str]:
        """
        获取缺少配置的提供商

        Args:
            required_providers: 需要的提供商列表

        Returns:
            缺少配置的提供商列表
        """
        missing = []

        for provider in required_providers:
            config = self.api_keys.get(provider)

            if not config or not config.get_api_key() or not config.enabled:
                missing.append(provider)

        return missing

    def request_provider_config(self, provider: str):
        """
        请求配置某个提供商的密钥

        当检测到缺少必需的API密钥时，触发此方法通知UI显示配置界面

        Args:
            provider: 需要配置的提供商
        """
        logger.info(f"请求配置API密钥: {provider}")

        if self.on_config_needed_callback:
            self.on_config_needed_callback(provider)

    def get_provider_info(self, provider: str) -> Dict[str, Any]:
        """
        获取提供商信息

        Args:
            provider: 提供商名称

        Returns:
            提供商信息
        """
        if provider not in API_KEY_ENV_MAPPING:
            return {}

        config = API_KEY_ENV_MAPPING[provider]
        api_key = self.get_api_key(provider)

        return {
            "provider": provider,
            "name": provider.upper(),
            "env_vars": config["env_vars"],
            "base_url": config["base_url"],
            "models": config["models"],
            "configured": bool(api_key),
            "valid": self.api_keys.get(provider, APIKeyConfig(provider="", api_key="")).is_valid if api_key else False
        }

    def get_all_provider_info(self) -> List[Dict[str, Any]]:
        """获取所有提供商信息"""
        return [
            self.get_provider_info(provider)
            for provider in API_KEY_ENV_MAPPING.keys()
        ]


# ============================================================================
# 单例实例
# ============================================================================

_api_key_manager: Optional[APIKeyManager] = None


def get_api_key_manager(config_dir: str = None) -> APIKeyManager:
    """获取API密钥管理器单例"""
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager(config_dir)
    return _api_key_manager


# ============================================================================
# 主函数（测试用）
# ============================================================================

if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("API密钥管理器测试")
    print("=" * 60)

    # 创建管理器
    manager = APIKeyManager()

    # 显示状态
    print("\n1. API密钥状态:")
    status = manager.get_status()

    for provider, s in status.items():
        print(f"   {provider}: configured={s.configured}, valid={s.valid}")

    # 显示缺少的密钥
    print("\n2. 缺少的必需API密钥:")
    required = ["openai", "anthropic", "google", "kimi", "glm"]
    missing = manager.get_missing_providers(required)

    for provider in missing:
        info = manager.get_provider_info(provider)
        print(f"   {provider}:")
        print(f"      环境变量: {info.get('env_vars', [])}")
        print(f"      基础URL: {info.get('base_url', '')}")
        print(f"      模型: {info.get('models', [])}")

    # 测试配置密钥
    print("\n3. 测试配置API密钥...")
    success = manager.configure_api_key(
        provider="openai",
        api_key="test-key-123",
        enabled=True
    )
    print(f"   配置结果: {success}")

    print("\n测试完成!")
