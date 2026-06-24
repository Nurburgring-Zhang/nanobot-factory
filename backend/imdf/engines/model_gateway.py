"""
F0.3: 多模型网关 (Multi-Model Gateway)
=======================================
统一接口接入 DeepSeek / OpenAI / Anthropic / Google / Zhipu，
含自动路由、失败降级、熔断保护。

Usage:
    gateway = ModelGateway()
    response = await gateway.chat(messages, model="auto", temperature=0.7, max_tokens=4096)
    models = await gateway.list_models()
    health = await gateway.health_check("deepseek-chat")

Config: 从 .env 读取各厂商 API Key
    DEEPSEEK_API_KEY     — DeepSeek
    OPENAI_API_KEY       — OpenAI
    ANTHROPIC_API_KEY    — Anthropic
    GOOGLE_API_KEY       — Google (Gemini)
    ZHIPU_API_KEY        — Zhipu (GLM)
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from abc import ABC, abstractmethod
from enum import Enum

import httpx

logger = logging.getLogger(__name__)

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class ModelInfo:
    id: str
    provider: str               # deepseek / openai / anthropic / google / zhipu
    display_name: str = ""
    capabilities: List[str] = field(default_factory=lambda: ["chat"])
    max_tokens: int = 4096
    default: bool = False
    enabled: bool = True
    priority: int = 0           # 路由优先级，越低越优先

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "display_name": self.display_name or self.id,
            "capabilities": self.capabilities,
            "max_tokens": self.max_tokens,
            "default": self.default,
            "enabled": self.enabled,
            "priority": self.priority,
        }


@dataclass
class ChatResponse:
    success: bool
    content: str = ""
    model: str = ""
    provider: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    error: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
            "error": self.error,
            "latency_ms": self.latency_ms,
        }


class CircuitState(Enum):
    CLOSED = "closed"           # 正常
    OPEN = "open"               # 熔断中
    HALF_OPEN = "half_open"     # 半开（探测）


@dataclass
class CircuitBreaker:
    """熔断器：连续3次失败→暂停5分钟"""
    max_failures: int = 3
    cooldown_seconds: int = 300  # 5 minutes
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    opened_at: float = 0.0

    def record_success(self):
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info("Circuit breaker reset to CLOSED (half-open probe succeeded)")

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.max_failures:
            self.state = CircuitState.OPEN
            self.opened_at = time.time()
            logger.warning(
                f"Circuit breaker OPENED after {self.failure_count} failures, "
                f"cooldown {self.cooldown_seconds}s"
            )

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self.opened_at
            if elapsed >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker → HALF_OPEN (probing)")
                return True
            return False
        # HALF_OPEN — allow one probe
        return True


# ============================================================================
# Provider Interface
# ============================================================================

class ModelProvider(ABC):
    """模型厂商适配器抽象基类"""

    provider_name: str = ""

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        ...

    @abstractmethod
    def get_models(self) -> List[ModelInfo]:
        ...

    @abstractmethod
    async def health_check(self, model: str) -> Dict[str, Any]:
        ...


# ============================================================================
# Concrete Providers
# ============================================================================

class DeepSeekProvider(ModelProvider):
    provider_name = "deepseek"

    BASE_URL = "https://api.deepseek.com"
    DEFAULT_MODELS = [
        ModelInfo(id="deepseek-chat", provider="deepseek", display_name="DeepSeek Chat",
                  max_tokens=8192, default=True, priority=0),
        ModelInfo(id="deepseek-v4-pro", provider="deepseek", display_name="DeepSeek V4 Pro",
                  max_tokens=16384, priority=1),
        ModelInfo(id="deepseek-v4-flash", provider="deepseek", display_name="DeepSeek V4 Flash",
                  max_tokens=8192, priority=2),
        ModelInfo(id="deepseek-reasoner", provider="deepseek", display_name="DeepSeek Reasoner",
                  max_tokens=16384, priority=3),
    ]

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or self._load_key("DEEPSEEK_API_KEY")

    @staticmethod
    def _load_key(env_var: str) -> str:
        return os.environ.get(env_var, "")

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096):
        if not self.api_key:
            return ChatResponse(success=False, error="DeepSeek API Key 未配置", provider=self.provider_name)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                    return ChatResponse(
                        success=True, content=content, model=model,
                        provider=self.provider_name, usage=usage,
                    )
                return ChatResponse(
                    success=False,
                    error=f"DeepSeek HTTP {resp.status_code}: {resp.text[:300]}",
                    provider=self.provider_name,
                )
        except Exception as e:
            return ChatResponse(success=False, error=str(e), provider=self.provider_name)

    def get_models(self):
        return [m for m in self.DEFAULT_MODELS if self.api_key]

    async def health_check(self, model: str):
        t0 = time.time()
        resp = await self.chat([{"role": "user", "content": "ping"}], model=model, max_tokens=10)
        latency = (time.time() - t0) * 1000
        return {"status": "ok" if resp.success else "error", "latency_ms": round(latency, 1)}


class OpenAIProvider(ModelProvider):
    provider_name = "openai"

    BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODELS = [
        ModelInfo(id="gpt-4o", provider="openai", display_name="GPT-4o",
                  max_tokens=16384, priority=0, default=True),
        ModelInfo(id="gpt-4o-mini", provider="openai", display_name="GPT-4o Mini",
                  max_tokens=8192, priority=1),
        ModelInfo(id="gpt-4-turbo", provider="openai", display_name="GPT-4 Turbo",
                  max_tokens=4096, priority=2),
        ModelInfo(id="o1", provider="openai", display_name="o1",
                  max_tokens=32768, capabilities=["chat", "reasoning"], priority=3),
        ModelInfo(id="o1-mini", provider="openai", display_name="o1 Mini",
                  max_tokens=16384, capabilities=["chat", "reasoning"], priority=4),
    ]

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096):
        if not self.api_key:
            return ChatResponse(success=False, error="OpenAI API Key 未配置", provider=self.provider_name)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                    return ChatResponse(
                        success=True, content=content, model=model,
                        provider=self.provider_name, usage=usage,
                    )
                return ChatResponse(
                    success=False,
                    error=f"OpenAI HTTP {resp.status_code}: {resp.text[:300]}",
                    provider=self.provider_name,
                )
        except Exception as e:
            return ChatResponse(success=False, error=str(e), provider=self.provider_name)

    def get_models(self):
        return [m for m in self.DEFAULT_MODELS if self.api_key]

    async def health_check(self, model: str):
        t0 = time.time()
        resp = await self.chat([{"role": "user", "content": "ping"}], model=model, max_tokens=10)
        latency = (time.time() - t0) * 1000
        return {"status": "ok" if resp.success else "error", "latency_ms": round(latency, 1)}


class AnthropicProvider(ModelProvider):
    provider_name = "anthropic"

    BASE_URL = "https://api.anthropic.com/v1"
    DEFAULT_MODELS = [
        ModelInfo(id="claude-sonnet-4-20250514", provider="anthropic",
                  display_name="Claude Sonnet 4", max_tokens=8192, priority=0, default=True),
        ModelInfo(id="claude-3-5-sonnet-20241022", provider="anthropic",
                  display_name="Claude 3.5 Sonnet", max_tokens=8192, priority=1),
        ModelInfo(id="claude-3-haiku-20240307", provider="anthropic",
                  display_name="Claude 3 Haiku", max_tokens=4096, priority=2),
        ModelInfo(id="claude-opus-4-20250514", provider="anthropic",
                  display_name="Claude Opus 4", max_tokens=16384, priority=3),
    ]

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096):
        if not self.api_key:
            return ChatResponse(success=False, error="Anthropic API Key 未配置", provider=self.provider_name)
        try:
            # Separate system message if present
            system_msg = ""
            chat_messages = []
            for m in messages:
                if m.get("role") == "system":
                    system_msg = m.get("content", "")
                else:
                    chat_messages.append(m)

            body = {
                "model": model,
                "messages": chat_messages,
                "max_tokens": max_tokens,
            }
            if system_msg:
                body["system"] = system_msg
            if temperature > 0:
                body["temperature"] = temperature

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "Content-Type": "application/json",
                        "anthropic-version": "2023-06-01",
                    },
                    json=body,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content_blocks = data.get("content", [])
                    text = ""
                    for block in content_blocks:
                        if block.get("type") == "text":
                            text += block.get("text", "")
                    usage = data.get("usage", {})
                    return ChatResponse(
                        success=True, content=text, model=model,
                        provider=self.provider_name, usage=usage,
                    )
                return ChatResponse(
                    success=False,
                    error=f"Anthropic HTTP {resp.status_code}: {resp.text[:300]}",
                    provider=self.provider_name,
                )
        except Exception as e:
            return ChatResponse(success=False, error=str(e), provider=self.provider_name)

    def get_models(self):
        return [m for m in self.DEFAULT_MODELS if self.api_key]

    async def health_check(self, model: str):
        t0 = time.time()
        resp = await self.chat([{"role": "user", "content": "ping"}], model=model, max_tokens=10)
        latency = (time.time() - t0) * 1000
        return {"status": "ok" if resp.success else "error", "latency_ms": round(latency, 1)}


class GoogleProvider(ModelProvider):
    provider_name = "google"

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    DEFAULT_MODELS = [
        ModelInfo(id="gemini-2.5-pro", provider="google", display_name="Gemini 2.5 Pro",
                  max_tokens=16384, priority=0, default=True, capabilities=["chat", "vision"]),
        ModelInfo(id="gemini-2.5-flash", provider="google", display_name="Gemini 2.5 Flash",
                  max_tokens=8192, priority=1, capabilities=["chat", "vision"]),
        ModelInfo(id="gemini-2.0-flash", provider="google", display_name="Gemini 2.0 Flash",
                  max_tokens=8192, priority=2, capabilities=["chat", "vision"]),
    ]

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096):
        if not self.api_key:
            return ChatResponse(success=False, error="Google API Key 未配置", provider=self.provider_name)
        try:
            # Convert messages to Google format
            contents = []
            system_instruction = None
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "system":
                    system_instruction = {"parts": [{"text": content}]}
                else:
                    parts = [{"text": content}]
                    google_role = "model" if role == "assistant" else "user"
                    contents.append({"role": google_role, "parts": parts})

            body = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }
            if system_instruction:
                body["system_instruction"] = system_instruction

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/models/{model}:generateContent",
                    params={"key": self.api_key},
                    headers={"Content-Type": "application/json"},
                    json=body,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    text = ""
                    if candidates:
                        content = candidates[0].get("content", {})
                        for part in content.get("parts", []):
                            text += part.get("text", "")
                    usage = data.get("usageMetadata", {})
                    return ChatResponse(
                        success=True, content=text, model=model,
                        provider=self.provider_name, usage=usage,
                    )
                return ChatResponse(
                    success=False,
                    error=f"Google HTTP {resp.status_code}: {resp.text[:300]}",
                    provider=self.provider_name,
                )
        except Exception as e:
            return ChatResponse(success=False, error=str(e), provider=self.provider_name)

    def get_models(self):
        return [m for m in self.DEFAULT_MODELS if self.api_key]

    async def health_check(self, model: str):
        t0 = time.time()
        resp = await self.chat([{"role": "user", "content": "ping"}], model=model, max_tokens=10)
        latency = (time.time() - t0) * 1000
        return {"status": "ok" if resp.success else "error", "latency_ms": round(latency, 1)}


class ZhipuProvider(ModelProvider):
    provider_name = "zhipu"

    BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
    DEFAULT_MODELS = [
        ModelInfo(id="glm-4-plus", provider="zhipu", display_name="GLM-4 Plus",
                  max_tokens=8192, priority=0, default=True),
        ModelInfo(id="glm-4-flash", provider="zhipu", display_name="GLM-4 Flash",
                  max_tokens=4096, priority=1),
        ModelInfo(id="glm-4-air", provider="zhipu", display_name="GLM-4 Air",
                  max_tokens=4096, priority=2),
        ModelInfo(id="glm-4v-plus", provider="zhipu", display_name="GLM-4V Plus",
                  max_tokens=8192, capabilities=["chat", "vision"], priority=3),
    ]

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY", "")

    async def chat(self, messages, model, temperature=0.7, max_tokens=4096):
        if not self.api_key:
            return ChatResponse(success=False, error="Zhipu API Key 未配置", provider=self.provider_name)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                    return ChatResponse(
                        success=True, content=content, model=model,
                        provider=self.provider_name, usage=usage,
                    )
                return ChatResponse(
                    success=False,
                    error=f"Zhipu HTTP {resp.status_code}: {resp.text[:300]}",
                    provider=self.provider_name,
                )
        except Exception as e:
            return ChatResponse(success=False, error=str(e), provider=self.provider_name)

    def get_models(self):
        return [m for m in self.DEFAULT_MODELS if self.api_key]

    async def health_check(self, model: str):
        t0 = time.time()
        resp = await self.chat([{"role": "user", "content": "ping"}], model=model, max_tokens=10)
        latency = (time.time() - t0) * 1000
        return {"status": "ok" if resp.success else "error", "latency_ms": round(latency, 1)}


# ============================================================================
# Model Gateway — Unified Entry Point
# ============================================================================

@dataclass
class ProviderEntry:
    """Provider + its circuit breaker"""
    provider: ModelProvider
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)


class ModelGateway:
    """
    多模型网关 — 统一接口、路由、降级、熔断。

    Usage:
        gateway = ModelGateway()
        resp = await gateway.chat([{"role":"user","content":"Hello"}])
        models = await gateway.list_models()
    """

    def __init__(self):
        self._providers: Dict[str, ProviderEntry] = {}
        self._models: List[ModelInfo] = []
        self._default_model: Optional[str] = None
        self._init_providers()

    def _init_providers(self):
        """初始化所有可用的Provider"""
        provider_classes = [
            (DeepSeekProvider, "DEEPSEEK_API_KEY"),
            (OpenAIProvider, "OPENAI_API_KEY"),
            (AnthropicProvider, "ANTHROPIC_API_KEY"),
            (GoogleProvider, "GOOGLE_API_KEY"),
            (ZhipuProvider, "ZHIPU_API_KEY"),
        ]

        for cls, env_var in provider_classes:
            key = os.environ.get(env_var, "")
            if key:
                instance = cls(api_key=key)
                name = instance.provider_name
                self._providers[name] = ProviderEntry(provider=instance)
                logger.info(f"Provider [{name}] loaded with {len(instance.get_models())} models")

        # Build unified model list sorted by priority
        all_models: List[ModelInfo] = []
        for entry in self._providers.values():
            all_models.extend(entry.provider.get_models())

        all_models.sort(key=lambda m: (m.priority, m.provider))
        self._models = all_models

        # Pick first default-capable model as gateway default
        for m in self._models:
            if m.default:
                self._default_model = m.id
                break
        if not self._default_model and self._models:
            self._default_model = self._models[0].id

        logger.info(
            f"ModelGateway initialized: {len(self._providers)} providers, "
            f"{len(self._models)} models, default={self._default_model}"
        )

    def _get_provider_for_model(self, model_id: str) -> Optional[ProviderEntry]:
        """Find which provider owns a given model ID"""
        for entry in self._providers.values():
            for m in entry.provider.get_models():
                if m.id == model_id:
                    return entry
        return None

    def _resolve_model(self, requested: str) -> str:
        """Resolve model alias: 'auto' → default model"""
        if requested == "auto":
            return self._default_model or "deepseek-chat"
        return requested

    def _get_fallback_candidates(self, failed_model: str) -> List[str]:
        """Get fallback model candidates in priority order, excluding the failed one"""
        # Find the failed model's provider
        failed_provider = ""
        for entry in self._providers.values():
            for m in entry.provider.get_models():
                if m.id == failed_model:
                    failed_provider = entry.provider.provider_name
                    break

        candidates = []
        for m in self._models:
            if m.id == failed_model:
                continue
            # Prefer same-provider fallback first
            candidates.append(m.id)
        return candidates

    # ─── Public API ──────────────────────────────────────────────────────────

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        max_fallbacks: int = 3,
    ) -> ChatResponse:
        """
        统一聊天接口，含自动路由和降级。

        Args:
            messages: [{"role":"user","content":"..."}, ...]
            model: 模型ID或 "auto"（自动选择）
            temperature: 温度参数
            max_tokens: 最大输出token数
            max_fallbacks: 最大降级尝试次数

        Returns:
            ChatResponse
        """
        resolved = self._resolve_model(model)
        attempted: List[str] = [resolved]

        for attempt in range(max_fallbacks + 1):
            current_model = attempted[-1]

            # Find provider + model
            entry = self._get_provider_for_model(current_model)
            if not entry:
                return ChatResponse(
                    success=False,
                    error=f"模型 {current_model} 未找到可用Provider",
                    model=current_model,
                )

            # Check circuit breaker
            if not entry.breaker.allow_request():
                # Skip, try next fallback
                logger.warning(f"Circuit breaker OPEN for {current_model}, trying fallback")
                if attempt < max_fallbacks:
                    fallbacks = self._get_fallback_candidates(current_model)
                    # Find first not-yet-attempted and not in open circuit
                    for fb in fallbacks:
                        fb_entry = self._get_provider_for_model(fb)
                        if fb_entry and fb_entry.breaker.allow_request() and fb not in attempted:
                            attempted.append(fb)
                            break
                    else:
                        return ChatResponse(
                            success=False,
                            error=f"所有可用模型均已熔断或尝试完毕",
                            model=current_model,
                        )
                    continue
                else:
                    return ChatResponse(
                        success=False,
                        error=f"模型 {current_model} 熔断中（{entry.breaker.cooldown_seconds}s冷却）",
                        model=current_model,
                    )

            # Execute
            t0 = time.time()
            resp = await entry.provider.chat(messages, current_model, temperature, max_tokens)
            resp.latency_ms = (time.time() - t0) * 1000

            if resp.success:
                entry.breaker.record_success()
                # If we fell back, note it
                if attempt > 0:
                    resp.content = f"[从 {resolved} 降级到 {current_model}]\n{resp.content}"
                return resp

            # Failure — record and try fallback
            entry.breaker.record_failure()
            logger.warning(
                f"Model {current_model} failed (attempt {attempt+1}/{max_fallbacks+1}): {resp.error}"
            )

            if attempt < max_fallbacks:
                fallbacks = self._get_fallback_candidates(current_model)
                for fb in fallbacks:
                    fb_entry = self._get_provider_for_model(fb)
                    if fb_entry and fb_entry.breaker.allow_request() and fb not in attempted:
                        attempted.append(fb)
                        break
                else:
                    return ChatResponse(
                        success=False,
                        error=f"所有模型均失败或熔断: {resp.error}",
                        model=current_model,
                    )
            else:
                return resp  # Last attempt failure

        return ChatResponse(success=False, error="未知错误", model=resolved)

    async def list_models(self) -> List[Dict[str, Any]]:
        """返回所有可用模型列表"""
        return [m.to_dict() for m in self._models]

    async def health_check(self, model: Optional[str] = None) -> Dict[str, Any]:
        """
        健康检查：检测指定模型或所有Provider的首选模型。

        Returns:
            { "status": "ok|degraded|down", "models": {"model_id": {status, latency_ms}, ...} }
        """
        results = {}
        ok_count = 0
        total = 0

        if model:
            entry = self._get_provider_for_model(model)
            if not entry:
                return {"status": "error", "error": f"模型 {model} 未找到"}
            hc = await entry.provider.health_check(model)
            return {"status": hc["status"], "model": model, "latency_ms": hc["latency_ms"]}

        # Check each provider's default model
        for provider_name, entry in self._providers.items():
            default_models = [m for m in entry.provider.get_models() if m.default]
            if not default_models:
                continue
            m = default_models[0]
            hc = await entry.provider.health_check(m.id)
            results[m.id] = hc
            total += 1
            if hc["status"] == "ok":
                ok_count += 1

        if ok_count == total and total > 0:
            status = "ok"
        elif ok_count > 0:
            status = "degraded"
        else:
            status = "down"

        return {"status": status, "models": results}

    def get_providers_info(self) -> List[Dict[str, Any]]:
        """获取所有Provider信息"""
        info = []
        for name, entry in self._providers.items():
            info.append({
                "provider": name,
                "models": [m.to_dict() for m in entry.provider.get_models()],
                "circuit_state": entry.breaker.state.value,
                "failure_count": entry.breaker.failure_count,
            })
        return info


# ============================================================================
# Singleton
# ============================================================================

_gateway: Optional[ModelGateway] = None


def get_gateway() -> ModelGateway:
    """获取或创建全局ModelGateway单例"""
    global _gateway
    if _gateway is None:
        _gateway = ModelGateway()
    return _gateway
