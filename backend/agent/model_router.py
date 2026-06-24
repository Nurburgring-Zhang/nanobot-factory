#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nanobot Factory - Model Router & Provider Registry
模型路由器与提供者注册中心 - 实现多模型支持、智能路由、负载均衡

核心功能：
- 多模型提供者支持
- 智能路由选择
- 负载均衡
- 故障转移
- 成本优化

@author MiniMax Agent
@date 2026-03-03
"""

import asyncio
import logging
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
import hashlib
from collections import defaultdict

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    """模型提供者枚举"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    LOCAL = "local"
    CUSTOM = "custom"


class ModelSize(Enum):
    """模型规模"""
    MINI = "mini"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "xlarge"


class ProviderStatus(Enum):
    """提供者状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass
class ModelConfig:
    """模型配置"""
    provider: ModelProvider
    model_name: str
    display_name: str
    size: ModelSize
    max_tokens: int = 4096
    temperature: float = 0.7
    supports_streaming: bool = True
    supports_function_calling: bool = True
    context_window: int = 128000
    capabilities: List[str] = field(default_factory=list)


@dataclass
class ProviderConfig:
    """提供者配置"""
    name: str
    provider_type: ModelProvider
    api_key: str
    base_url: Optional[str] = None
    organization: Optional[str] = None
    default_model: Optional[str] = None
    max_requests_per_minute: int = 60
    timeout: float = 30.0
    retry_count: int = 3
    retry_delay: float = 1.0
    enabled: bool = True
    priority: int = 100


@dataclass
class RequestMetrics:
    """请求指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens: int = 0
    total_latency: float = 0.0


@dataclass
class ProviderMetrics:
    """提供者指标"""
    provider_name: str
    status: ProviderStatus = ProviderStatus.HEALTHY
    request_metrics: RequestMetrics = field(default_factory=RequestMetrics)
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    latency_p99: float = 0.0
    error_rate: float = 0.0
    consecutive_failures: int = 0


class BaseModelProvider(ABC):
    """模型提供者基类"""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.metrics = ProviderMetrics(provider_name=config.name)
        self._lock = asyncio.Lock()

    @abstractmethod
    async def generate(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        functions: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """生成内容"""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ):
        """流式生成内容"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass

    @abstractmethod
    def get_available_models(self) -> List[ModelConfig]:
        """获取可用模型"""
        pass

    async def update_metrics(
        self,
        success: bool,
        latency: float,
        tokens: int = 0,
        error: Optional[str] = None,
    ):
        """更新指标"""
        async with self._lock:
            self.metrics.request_metrics.total_requests += 1
            self.metrics.request_metrics.total_latency += latency
            self.metrics.request_metrics.total_tokens += tokens

            if success:
                self.metrics.request_metrics.successful_requests += 1
                self.metrics.consecutive_failures = 0
                self.metrics.status = ProviderStatus.HEALTHY
            else:
                self.metrics.request_metrics.failed_requests += 1
                self.metrics.consecutive_failures += 1

                if self.metrics.consecutive_failures >= 3:
                    self.metrics.status = ProviderStatus.DEGRADED
                if self.metrics.consecutive_failures >= 10:
                    self.metrics.status = ProviderStatus.UNAVAILABLE

            total = self.metrics.request_metrics.total_requests
            if total > 0:
                self.metrics.error_rate = (
                    self.metrics.request_metrics.failed_requests / total
                )


class OpenAIProvider(BaseModelProvider):
    """OpenAI提供者"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

        self._models = [
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_name="gpt-4o",
                display_name="GPT-4o",
                size=ModelSize.LARGE,
                max_tokens=16384,
                supports_streaming=True,
                supports_function_calling=True,
                context_window=128000,
                capabilities=["text", "vision", "function_calling"],
            ),
            ModelConfig(
                provider=ModelProvider.OPENAI,
                model_name="gpt-4o-mini",
                display_name="GPT-4o Mini",
                size=ModelSize.SMALL,
                max_tokens=16384,
                supports_streaming=True,
                supports_function_calling=True,
                context_window=128000,
                capabilities=["text", "vision", "function_calling"],
            ),
        ]

    async def _get_client(self):
        """获取OpenAI客户端"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url or "https://api.openai.com/v1",
                    organization=self.config.organization,
                    timeout=self.config.timeout,
                    max_retries=self.config.retry_count,
                )
            except ImportError:
                logger.error("openai package not installed")
                raise
        return self._client

    async def generate(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        functions: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """生成内容"""
        client = await self._get_client()

        request_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            request_params["max_tokens"] = max_tokens
        if stop:
            request_params["stop"] = stop
        if functions:
            request_params["tools"] = [
                {"type": "function", "function": f} for f in functions
            ]

        response = await client.chat.completions.create(**request_params)

        result = {
            "content": response.choices[0].message.content,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            "finish_reason": response.choices[0].finish_reason,
        }

        if response.choices[0].message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in response.choices[0].message.tool_calls
            ]

        return result

    async def generate_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ):
        """流式生成"""
        client = await self._get_client()

        request_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens:
            request_params["max_tokens"] = max_tokens
        if stop:
            request_params["stop"] = stop

        response = await client.chat.completions.create(**request_params)

        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            client = await self._get_client()
            await client.models.list()
            return True
        except Exception as e:
            logger.error(f"OpenAI health check failed: {e}")
            return False

    def get_available_models(self) -> List[ModelConfig]:
        """获取可用模型"""
        return self._models


class AnthropicProvider(BaseModelProvider):
    """Anthropic提供者"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

        self._models = [
            ModelConfig(
                provider=ModelProvider.ANTHROPIC,
                model_name="claude-sonnet-4-20250514",
                display_name="Claude Sonnet 4",
                size=ModelSize.LARGE,
                max_tokens=4096,
                supports_streaming=True,
                context_window=200000,
                capabilities=["text", "vision"],
            ),
        ]

    async def _get_client(self):
        """获取Anthropic客户端"""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url or "https://api.anthropic.com",
                    timeout=self.config.timeout,
                )
            except ImportError:
                logger.error("anthropic package not installed")
                raise
        return self._client

    async def generate(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """生成内容"""
        client = await self._get_client()

        system = None
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                anthropic_messages.append(msg)

        request_params = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
        }

        if system:
            request_params["system"] = system
        if stop:
            request_params["stop_sequences"] = stop

        response = await client.messages.create(**request_params)

        return {
            "content": response.content[0].text if response.content else "",
            "model": response.model,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }

    async def generate_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ):
        """流式生成"""
        client = await self._get_client()

        system = None
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                anthropic_messages.append(msg)

        request_params = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
            "stream": True,
        }

        if system:
            request_params["system"] = system

        async with client.messages.stream(**request_params) as stream:
            async for text in stream.text_stream:
                yield text

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            client = await self._get_client()
            await client.messages.create(
                model=self._models[0].model_name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            return True
        except Exception as e:
            logger.error(f"Anthropic health check failed: {e}")
            return False

    def get_available_models(self) -> List[ModelConfig]:
        """获取可用模型"""
        return self._models


class LocalProvider(BaseModelProvider):
    """本地模型提供者"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

        self._models = [
            ModelConfig(
                provider=ModelProvider.LOCAL,
                model_name="llama3",
                display_name="Llama 3",
                size=ModelSize.LARGE,
                max_tokens=4096,
                supports_streaming=True,
                context_window=8192,
                capabilities=["text"],
            ),
        ]

    async def _get_client(self):
        """获取本地客户端"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                base_url = self.config.base_url or "http://localhost:11434/v1"
                self._client = AsyncOpenAI(
                    api_key="not-needed",
                    base_url=base_url,
                    timeout=self.config.timeout,
                )
            except ImportError:
                logger.error("openai package not installed")
                raise
        return self._client

    async def generate(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """生成内容"""
        client = await self._get_client()

        request_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            request_params["max_tokens"] = max_tokens
        if stop:
            request_params["stop"] = stop

        response = await client.chat.completions.create(**request_params)

        return {
            "content": response.choices[0].message.content,
            "model": response.model,
            "usage": {
                "total_tokens": response.usage.total_tokens,
            },
        }

    async def generate_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ):
        """流式生成"""
        client = await self._get_client()

        request_params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens:
            request_params["max_tokens"] = max_tokens

        response = await client.chat.completions.create(**request_params)

        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            client = await self._get_client()
            await client.chat.completions.create(
                model=self._models[0].model_name,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            return True
        except Exception as e:
            logger.error(f"Local provider health check failed: {e}")
            return False

    def get_available_models(self) -> List[ModelConfig]:
        """获取可用模型"""
        return self._models


class ModelRouter:
    """模型路由器"""

    def __init__(
        self,
        default_provider: Optional[str] = None,
        routing_strategy: str = "priority",
    ):
        self.default_provider = default_provider
        self.routing_strategy = routing_strategy
        self._providers: Dict[str, BaseModelProvider] = {}
        self._model_to_provider: Dict[str, str] = {}
        self._model_configs: Dict[str, ModelConfig] = {}
        self._routing_rules: List[tuple] = []
        self._load_balancer_state: Dict[str, int] = defaultdict(int)

        logger.info(f"ModelRouter initialized (strategy={routing_strategy})")

    def register_provider(
        self,
        name: str,
        provider: BaseModelProvider,
    ):
        """注册提供者"""
        self._providers[name] = provider

        for model_config in provider.get_available_models():
            self._model_configs[model_config.model_name] = model_config
            self._model_to_provider[model_config.model_name] = name

        logger.info(f"Provider registered: {name}")

    def add_routing_rule(
        self,
        pattern: str,
        provider_name: str,
    ):
        """添加路由规则"""
        self._routing_rules.append((pattern, provider_name))
        logger.info(f"Routing rule added: {pattern} -> {provider_name}")

    def set_default_provider(self, name: str):
        """设置默认提供者"""
        self.default_provider = name

    def _select_provider(
        self,
        model: Optional[str] = None,
        requirements: Optional[Dict[str, Any]] = None,
    ) -> Optional[BaseModelProvider]:
        """选择提供者"""
        if model and model in self._model_to_provider:
            provider_name = self._model_to_provider[model]
            provider = self._providers.get(provider_name)
            if provider and provider.metrics.status != ProviderStatus.UNAVAILABLE:
                return provider

        for pattern, provider_name in self._routing_rules:
            if model and pattern.replace("*", "") in model:
                provider = self._providers.get(provider_name)
                if provider and provider.metrics.status != ProviderStatus.UNAVAILABLE:
                    return provider

        if self.default_provider:
            return self._providers.get(self.default_provider)

        return self._load_balance()

    def _load_balance(self) -> Optional[BaseModelProvider]:
        """负载均衡"""
        available = [
            (name, p)
            for name, p in self._providers.items()
            if p.config.enabled and p.metrics.status != ProviderStatus.UNAVAILABLE
        ]

        if not available:
            return None

        if self.routing_strategy == "round_robin":
            provider_name = list(self._providers.keys())[
                self._load_balancer_state["rr"] % len(self._providers)
            ]
            self._load_balancer_state["rr"] += 1
            return self._providers.get(provider_name)

        elif self.routing_strategy == "least_latency":
            available.sort(key=lambda x: x[1].metrics.latency_p50)
            return available[0][1]

        elif self.routing_strategy == "priority":
            available.sort(key=lambda x: x[1].config.priority, reverse=True)
            return available[0][1]

        return available[0][1] if available else None

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
        functions: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """生成内容（自动路由）"""
        start_time = datetime.now()

        selected_provider = None

        if provider and provider in self._providers:
            selected_provider = self._providers[provider]
        else:
            selected_provider = self._select_provider(model)

        if not selected_provider:
            raise ValueError("No available provider found")

        actual_model = model
        if not actual_model:
            if selected_provider.config.default_model:
                actual_model = selected_provider.config.default_model
            else:
                actual_model = selected_provider.get_available_models()[0].model_name

        providers_to_try = self._get_failover_providers(selected_provider)

        for p in providers_to_try:
            try:
                result = await p.generate(
                    model=actual_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stop=stop,
                    functions=functions,
                    **kwargs,
                )

                latency = (datetime.now() - start_time).total_seconds()
                await p.update_metrics(
                    success=True,
                    latency=latency,
                    tokens=result.get("usage", {}).get("total_tokens", 0),
                )

                result["_router"] = {
                    "provider": p.config.name,
                    "model": actual_model,
                    "latency": latency,
                }

                return result

            except Exception as e:
                logger.warning(f"Provider {p.config.name} failed: {e}")

                latency = (datetime.now() - start_time).total_seconds()
                await p.update_metrics(
                    success=False,
                    latency=latency,
                    error=str(e),
                )

                continue

        raise RuntimeError("All providers failed")

    def _get_failover_providers(
        self,
        primary: BaseModelProvider,
    ) -> List[BaseModelProvider]:
        """获取故障转移列表"""
        providers = [primary]

        others = [
            p for name, p in self._providers.items()
            if p != primary and p.config.enabled
        ]
        others.sort(key=lambda x: x.config.priority, reverse=True)

        providers.extend(others)
        return providers

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ):
        """流式生成"""
        selected_provider = None

        if provider and provider in self._providers:
            selected_provider = self._providers[provider]
        else:
            selected_provider = self._select_provider(model)

        if not selected_provider:
            raise ValueError("No available provider found")

        actual_model = model
        if not actual_model:
            if selected_provider.config.default_model:
                actual_model = selected_provider.config.default_model
            else:
                actual_model = selected_provider.get_available_models()[0].model_name

        async for chunk in selected_provider.generate_stream(
            model=actual_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            yield chunk

    async def health_check_all(self) -> Dict[str, bool]:
        """所有提供者健康检查"""
        results = {}
        for name, provider in self._providers.items():
            results[name] = await provider.health_check()
        return results

    def get_available_models(self) -> List[ModelConfig]:
        """获取所有可用模型"""
        return list(self._model_configs.values())

    def get_metrics(self) -> Dict[str, ProviderMetrics]:
        """获取所有提供者指标"""
        return {
            name: provider.metrics
            for name, provider in self._providers.items()
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取路由统计"""
        return {
            "total_providers": len(self._providers),
            "available_models": len(self._model_configs),
            "metrics": {
                name: {
                    "status": p.metrics.status.value,
                    "requests": p.metrics.request_metrics.total_requests,
                    "error_rate": p.metrics.error_rate,
                }
                for name, p in self._providers.items()
            },
        }


def create_provider(
    provider_type: ModelProvider,
    config: ProviderConfig,
) -> BaseModelProvider:
    """创建模型提供者"""
    if provider_type == ModelProvider.OPENAI:
        return OpenAIProvider(config)
    elif provider_type == ModelProvider.ANTHROPIC:
        return AnthropicProvider(config)
    elif provider_type == ModelProvider.LOCAL:
        return LocalProvider(config)
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")


def create_model_router(
    configs: List[ProviderConfig],
    default_provider: Optional[str] = None,
    routing_strategy: str = "priority",
) -> ModelRouter:
    """创建模型路由器"""
    router = ModelRouter(
        default_provider=default_provider,
        routing_strategy=routing_strategy,
    )

    for config in configs:
        if config.enabled:
            provider = create_provider(config.provider_type, config)
            router.register_provider(config.name, provider)

    if default_provider:
        router.set_default_provider(default_provider)

    return router


if __name__ == "__main__":
    import os

    openai_config = ProviderConfig(
        name="openai",
        provider_type=ModelProvider.OPENAI,
        api_key=os.getenv("OPENAI_API_KEY", "sk-test"),
        priority=100,
    )

    router = create_model_router(
        configs=[openai_config],
        default_provider="openai",
    )

    print(router.get_stats())
