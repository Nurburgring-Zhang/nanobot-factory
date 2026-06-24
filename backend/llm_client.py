#!/usr/bin/env python3
"""
Nanobot Factory - LLM Client Integration
Production-ready LLM client implementations for multi-agent cluster
Supports 2026年2月最新模型: GPT-5, Claude 4 Opus/Sonnet, Gemini 2.0 Pro/Ultra,
Seedream 6.0, Seedance 3.0, Qwen 3.0, Kimi K2, GLM-5, MiniMax-3

@author MiniMax Agent
@date 2026-02-26
"""

import os
import json
import asyncio
import logging
import hashlib
import yaml
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod

# Optional watchdog import for file monitoring
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    Observer = None
    FileSystemEventHandler = None

import aiohttp

# Optional websockets import for WebSocket connections
try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    websockets = None

# Import GenerationResult from aigc_adapter if available
try:
    from aigc_adapter import GenerationResult
except ImportError:
    # Define locally if aigc_adapter not available
    @dataclass
    class GenerationResult:
        """Represents generation result"""
        success: bool
        files: List[str] = field(default_factory=list)
        metadata: Dict[str, Any] = field(default_factory=dict)
        error: Optional[str] = None
        generation_time: float = 0.0

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers - Updated 2026年2月"""
    # International providers
    OPENAI = "openai"           # GPT-5 series
    ANTHROPIC = "anthropic"     # Claude 4 Opus/Sonnet
    GOOGLE = "google"           # Gemini 2.0 Pro/Ultra
    OPENROUTER = "openrouter"   # Meta-model routing
    GROQ = "groq"               # Groq inference
    VLLM = "vllm"               # Local vLLM
    LOCAL = "local"             # Local models
    OLLAMA = "ollama"           # Local Ollama models
    DEEPSEEK = "deepseek"       # DeepSeek R1/V3 series

    # Chinese providers (2026年2月最新)
    KIMI = "kimi"               # Moonshot AI - Kimi K2
    GLM = "glm"                 # Zhipu AI - GLM-5 series
    MINIMAX = "minimax"         # MiniMax - MiniMax-3
    DOUBAO = "doubao"           # ByteDance - Doubao series
    BAIDU = "baidu"             # Baidu - ERNIE 4.5
    TENCENT = "tencent"         # Tencent - Hunyuan 3.0
    ALIBABA = "alibaba"         # Alibaba - Qwen 3.0 series

    # Media generation (2026年2月最新)
    SEEDREAM = "seedream"       # ByteDance Seedream 6.0
    SEEDANCE = "seedance"       # ByteDance Seedance 3.0


@dataclass
class ChatMessage:
    """Chat message"""
    role: str  # system, user, assistant
    content: str


@dataclass
class ChatCompletion:
    """Chat completion response"""
    id: str
    provider: str
    model: str
    content: str
    finish_reason: str
    usage: Dict[str, int] = field(default_factory=dict)
    created: int = 0


@dataclass
class ChatCompletionRequest:
    """Chat completion request"""
    model: str
    messages: List[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None


class LLMClientBase(ABC):
    """Base class for LLM clients"""

    def __init__(self, api_key: str, base_url: Optional[str] = None, default_model: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model

    @abstractmethod
    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion request"""
        pass

    @abstractmethod
    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Send chat completion request with streaming"""
        pass

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }


class OpenAIClient(LLMClientBase):
    """OpenAI API client - Supports GPT-5 series (2026年2月最新)"""

    # 2026年2月最新模型映射
    GPT_MODELS = {
        # GPT-5 series
        "gpt-5": "gpt-5",
        "gpt-5-turbo": "gpt-5-turbo",
        "gpt-5-preview": "gpt-5-preview",
        "gpt-5-flash": "gpt-5-flash",
        # GPT-4 series (legacy)
        "gpt-4o": "gpt-4o",
        "gpt-4o-mini": "gpt-4o-mini",
        "gpt-4-turbo": "gpt-4-turbo",
        "gpt-4": "gpt-4",
        "gpt-4-32k": "gpt-4-32k",
        "gpt-3.5-turbo": "gpt-3.5-turbo",
    }

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        super().__init__(api_key, base_url)
        self.default_model = "gpt-5"  # 2026年2月最新默认模型

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion to OpenAI"""
        url = f"{self.base_url}/chat/completions"

        headers = self._build_headers()
        headers["OpenAI-Organization"] = os.getenv("OPENAI_ORG", "")

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": False
        }

        if request.tools:
            payload["tools"] = request.tools
            if request.tool_choice:
                payload["tool_choice"] = request.tool_choice

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"OpenAI API error: {resp.status} - {error_text}")

                data = await resp.json()

                return ChatCompletion(
                    id=data.get("id", ""),
                    provider="openai",
                    model=data.get("model", ""),
                    content=data["choices"][0]["message"]["content"],
                    finish_reason=data["choices"][0].get("finish_reason", ""),
                    usage=data.get("usage", {}),
                    created=data.get("created", 0)
                )

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Stream chat completion from OpenAI"""
        url = f"{self.base_url}/chat/completions"

        headers = self._build_headers()

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": True
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"OpenAI API error: {resp.status} - {error_text}")

                async for line in resp.content:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('choices'):
                            delta = data['choices'][0].get('delta', {})
                            if delta.get('content'):
                                yield delta['content']


class AnthropicClient(LLMClientBase):
    """Anthropic Claude API client - Supports Claude 4 Opus/Sonnet (2026年2月最新)"""

    # 2026年2月最新模型映射
    CLAUDE_MODELS = {
        # Claude 4 series
        "claude-4-opus": "claude-opus-4-20250514",
        "claude-4-sonnet": "claude-sonnet-4-20250514",
        "claude-4": "claude-sonnet-4-20250514",
        "claude-4-6": "claude-sonnet-4-20250514",
        "claude-4-5": "claude-sonnet-4-20250514",
        # Claude 3 series (legacy)
        "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
        "claude-3-5": "claude-3-5-sonnet-20241022",
        "claude-3-opus": "claude-3-opus-20240229",
        "claude-3-sonnet": "claude-3-sonnet-20240229",
        "claude-3-haiku": "claude-3-haiku-20240307",
    }

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com"):
        super().__init__(api_key, base_url)
        self.default_model = "claude-opus-4-20250514"  # Default to Claude 4 Opus

    def _build_headers(self, extra: Dict[str, str] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        if extra:
            headers.update(extra)
        return headers

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion to Anthropic"""
        url = f"{self.base_url}/v1/messages"

        # Convert messages to Anthropic format
        system_message = None
        other_messages = []

        for msg in request.messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                other_messages.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": request.model or self.default_model,
            "messages": other_messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p
        }

        if system_message:
            payload["system"] = system_message

        headers = self._build_headers()

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Anthropic API error: {resp.status} - {error_text}")

                data = await resp.json()

                return ChatCompletion(
                    id=data.get("id", ""),
                    provider="anthropic",
                    model=data.get("model", ""),
                    content=data["content"][0]["text"],
                    finish_reason=data.get("stop_reason", ""),
                    usage=data.get("usage", {}),
                    created=int(datetime.now().timestamp())
                )

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Stream chat completion from Anthropic"""
        url = f"{self.base_url}/v1/messages"

        system_message = None
        other_messages = []

        for msg in request.messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                other_messages.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": request.model or self.default_model,
            "messages": other_messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": True
        }

        if system_message:
            payload["system"] = system_message

        headers = self._build_headers()

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Anthropic API error: {resp.status} - {error_text}")

                async for line in resp.content:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get("type") == "content_block_delta":
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield delta.get("text", "")


class GoogleClient(LLMClientBase):
    """Google Gemini API client - Supports Gemini 2.0 Pro/Ultra (2026年2月最新)"""

    # 2026年2月最新模型映射
    GEMINI_MODELS = {
        # Gemini 2.0 series
        "gemini-2-0-ultra": "gemini-2.0-ultra",
        "gemini-2-0-pro": "gemini-2.0-pro",
        "gemini-2-0-flash": "gemini-2.0-flash",
        "gemini-2-0-flash-exp": "gemini-2.0-flash-exp",
        # Gemini 1.5 series (legacy)
        "gemini-1-5-pro": "gemini-1.5-pro",
        "gemini-1-5-flash": "gemini-1.5-flash",
        "gemini-1-5-flash-8b": "gemini-1.5-flash-8b",
        "gemini-1-5": "gemini-1.5-flash",
        # Legacy
        "gemini-pro": "gemini-pro",
        "gemini-pro-vision": "gemini-pro-vision",
    }

    def __init__(self, api_key: str, base_url: str = "https://generativelanguage.googleapis.com/v1beta"):
        super().__init__(api_key, base_url)
        self.default_model = "gemini-2.0-pro"  # Default to Gemini 2.0 Pro

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion to Google Gemini"""
        model = request.model or self.default_model
        url = f"{self.base_url}/models/{model}:generateContent"

        # Convert messages to Gemini format
        contents = []
        for msg in request.messages:
            if msg.role == "user":
                contents.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role == "model":
                contents.append({"role": "model", "parts": [{"text": msg.content}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
                "topP": request.top_p
            }
        }

        params = {"key": self.api_key}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, params=params) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Google API error: {resp.status} - {error_text}")

                data = await resp.json()

                content = ""
                if data.get("candidates"):
                    candidate = data["candidates"][0]
                    if candidate.get("content") and candidate["content"].get("parts"):
                        content = candidate["content"]["parts"][0].get("text", "")

                return ChatCompletion(
                    id=hashlib.md5(str(datetime.now()).encode()).hexdigest(),
                    provider="google",
                    model=model,
                    content=content,
                    finish_reason="stop",
                    usage={},
                    created=int(datetime.now().timestamp())
                )

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Stream chat completion from Google Gemini"""
        model = request.model or self.default_model
        url = f"{self.base_url}/models/{model}:streamGenerateContent"

        contents = []
        for msg in request.messages:
            if msg.role == "user":
                contents.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role == "model":
                contents.append({"role": "model", "parts": [{"text": msg.content}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
                "topP": request.top_p,
                "stream": True
            }
        }

        params = {"key": self.api_key}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, params=params) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Google API error: {resp.status} - {error_text}")

                async for line in resp.content:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get("candidates"):
                            candidate = data["candidates"][0]
                            if candidate.get("content") and candidate["content"].get("parts"):
                                yield candidate["content"]["parts"][0].get("text", "")


class OpenRouterClient(LLMClientBase):
    """OpenRouter API client - supports many models"""

    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        super().__init__(api_key, base_url)
        self.default_model = "anthropic/claude-3.5-sonnet"

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion to OpenRouter"""
        url = f"{self.base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": os.getenv("APP_URL", "https://nanobot.factory"),
            "X-Title": "Nanobot Factory"
        }

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": False
        }

        if request.tools:
            payload["tools"] = request.tools

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"OpenRouter API error: {resp.status} - {error_text}")

                data = await resp.json()

                return ChatCompletion(
                    id=data.get("id", ""),
                    provider="openrouter",
                    model=data.get("model", ""),
                    content=data["choices"][0]["message"]["content"],
                    finish_reason=data["choices"][0].get("finish_reason", ""),
                    usage=data.get("usage", {}),
                    created=data.get("created", 0)
                )

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Stream chat completion from OpenRouter"""
        url = f"{self.base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": os.getenv("APP_URL", "https://nanobot.factory"),
            "X-Title": "Nanobot Factory"
        }

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": True
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"OpenRouter API error: {resp.status} - {error_text}")

                async for line in resp.content:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('choices'):
                            delta = data['choices'][0].get('delta', {})
                            if delta.get('content'):
                                yield delta['content']


# ============================================================================
# Kimi (Moonshot AI) Client
# ============================================================================

class KimiClient(LLMClientBase):
    """Kimi API client - Moonshot AI (月之暗面) - Supports Kimi K2 (2026年2月最新)"""

    # 2026年2月最新模型映射
    KIMI_MODELS = {
        # Kimi K2 series (2026年2月最新)
        "kimi-k2": "moonshot-k2",
        "kimi-k2-preview": "moonshot-k2-preview",
        "kimi-k2-thinking": "moonshot-k2-thinking",
        # Kimi V2 series
        "kimi-v2": "moonshot-v2",
        "kimi-v2-8k": "moonshot-v2-8k",
        "kimi-v2-32k": "moonshot-v2-32k",
        "kimi-v2-200k": "moonshot-v2-200k",
        # Kimi V1.5 series (legacy)
        "kimi-1-5": "moonshot-v1.5",
        "kimi-1-5-long": "moonshot-v1.5-200k",
        "kimi-pro": "moonshot-v1-pro",
        "kimi": "moonshot-v1.5",
    }

    def __init__(self, api_key: str, base_url: str = "https://api.moonshot.cn/v1"):
        super().__init__(api_key, base_url)
        self.default_model = "moonshot-k2"  # Default to Kimi K2

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion to Kimi"""
        url = f"{self.base_url}/chat/completions"

        headers = self._build_headers()

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": False
        }

        if request.tools:
            payload["tools"] = request.tools

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Kimi API error: {resp.status} - {error_text}")

                data = await resp.json()

                return ChatCompletion(
                    id=data.get("id", ""),
                    provider="kimi",
                    model=data.get("model", ""),
                    content=data["choices"][0]["message"]["content"],
                    finish_reason=data["choices"][0].get("finish_reason", ""),
                    usage=data.get("usage", {}),
                    created=data.get("created", 0)
                )

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Stream chat completion from Kimi"""
        url = f"{self.base_url}/chat/completions"

        headers = self._build_headers()

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": True
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Kimi API error: {resp.status} - {error_text}")

                async for line in resp.content:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('choices'):
                            delta = data['choices'][0].get('delta', {})
                            if delta.get('content'):
                                yield delta['content']


# ============================================================================
# GLM (Zhipu AI) Client
# ============================================================================

class GLMClient(LLMClientBase):
    """GLM API client - Zhipu AI (智谱AI) - Supports GLM-5 (2026年2月最新)"""

    # 2026年2月最新模型映射
    GLM_MODELS = {
        # GLM-5 series (2026年2月最新)
        "glm-5": "glm-5",
        "glm-5-flash": "glm-5-flash",
        "glm-5-plus": "glm-5-plus",
        "glm-5-vision": "glm-5-vision",
        # GLM-4 series (legacy)
        "glm-4": "glm-4-flash",
        "glm-4-plus": "glm-4-plus",
        "glm-4-vision": "glm-4v-flash",
        "glm-4-long": "glm-4-long-context",
        "glm-4-code": "glm-4-code",
        "glm-3": "glm-3-turbo",
    }

    def __init__(self, api_key: str, base_url: str = "https://open.bigmodel.cn/api/paas/v4"):
        super().__init__(api_key, base_url)
        self.default_model = "glm-5"  # Default to GLM-5

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion to GLM"""
        url = f"{self.base_url}/chat/completions"

        headers = self._build_headers()

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p
        }

        if request.tools:
            payload["tools"] = request.tools

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"GLM API error: {resp.status} - {error_text}")

                data = await resp.json()

                return ChatCompletion(
                    id=data.get("id", ""),
                    provider="glm",
                    model=data.get("model", ""),
                    content=data["choices"][0]["message"]["content"],
                    finish_reason=data["choices"][0].get("finish_reason", ""),
                    usage=data.get("usage", {}),
                    created=data.get("created", 0)
                )

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Stream chat completion from GLM"""
        url = f"{self.base_url}/chat/completions"

        headers = self._build_headers()

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": True
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"GLM API error: {resp.status} - {error_text}")

                async for line in resp.content:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('choices'):
                            delta = data['choices'][0].get('delta', {})
                            if delta.get('content'):
                                yield delta['content']


# ============================================================================
# MiniMax Client
# ============================================================================

class MiniMaxClient(LLMClientBase):
    """MiniMax API client - Supports MiniMax-3 (2026年2月最新)"""

    # 2026年2月最新模型映射
    MINIMAX_MODELS = {
        # MiniMax-3 series (2026年2月最新)
        "minimax-3": "MiniMax-Text-03",
        "minimax-3-flash": "MiniMax-Text-03-flash",
        "minimax-3-plus": "MiniMax-Text-03-plus",
        # MiniMax-2 series
        "minimax-2-5": "MiniMax-Text-01",
        "minimax-2": "MiniMax-Text-01",
        "minimax-1-8": "abab6.5s-chat",
        "minimax-1-5": "abab5.5s-chat",
    }

    def __init__(self, api_key: str, base_url: str = "https://api.minimax.chat/v1"):
        super().__init__(api_key, base_url)
        self.default_model = "MiniMax-Text-03"  # Default to MiniMax-3

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion to MiniMax"""
        url = f"{self.base_url}/text/chatcompletion_v2"

        headers = self._build_headers()

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"MiniMax API error: {resp.status} - {error_text}")

                data = await resp.json()

                return ChatCompletion(
                    id=data.get("id", ""),
                    provider="minimax",
                    model=data.get("model", ""),
                    content=data["choices"][0]["message"]["content"],
                    finish_reason=data["choices"][0].get("finish_reason", ""),
                    usage=data.get("usage", {}),
                    created=data.get("created", 0)
                )

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Stream chat completion from MiniMax"""
        url = f"{self.base_url}/text/chatcompletion_v2"

        headers = self._build_headers()

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": True
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"MiniMax API error: {resp.status} - {error_text}")

                async for line in resp.content:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('choices'):
                            delta = data['choices'][0].get('delta', {})
                            if delta.get('content'):
                                yield delta['content']


# ============================================================================
# Doubao (ByteDance) Client
# ============================================================================

class DoubaoClient(LLMClientBase):
    """Doubao API client - ByteDance (字节跳动)"""

    DOUBAO_MODELS = {
        "doubao-1-5": "doubao-pro-32k",
        "doubao-pro": "doubao-pro-32k",
        "doubao-lite": "doubao-lite-32k",
        "doubao-vision": "doubao-pro-vision-32k",
    }

    def __init__(self, api_key: str, base_url: str = "https://ark.cn-beijing.volces.com/api/v3"):
        super().__init__(api_key, base_url)
        self.default_model = "doubao-pro-32k"

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion to Doubao"""
        url = f"{self.base_url}/chat/completions"

        headers = self._build_headers()

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p
        }

        if request.tools:
            payload["tools"] = request.tools

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Doubao API error: {resp.status} - {error_text}")

                data = await resp.json()

                return ChatCompletion(
                    id=data.get("id", ""),
                    provider="doubao",
                    model=data.get("model", ""),
                    content=data["choices"][0]["message"]["content"],
                    finish_reason=data["choices"][0].get("finish_reason", ""),
                    usage=data.get("usage", {}),
                    created=data.get("created", 0)
                )

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Stream chat completion from Doubao"""
        url = f"{self.base_url}/chat/completions"

        headers = self._build_headers()

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": True
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Doubao API error: {resp.status} - {error_text}")

                async for line in resp.content:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('choices'):
                            delta = data['choices'][0].get('delta', {})
                            if delta.get('content'):
                                yield delta['content']


# ============================================================================
# Baidu (Wenxin) Client
# ============================================================================

class BaiduClient(LLMClientBase):
    """Baidu Wenxin API client - Baidu (百度文心一言)"""

    BAIDU_MODELS = {
        "ernie-4": "ernie-4.0-8k",
        "ernie-3-5": "ernie-3.5-8k",
        "ernie-3": "ernie-bot-3",
        "ernie-bot": "ernie-bot",
        "ernie-vilg": "ernie-vilg-v2",
    }

    def __init__(self, api_key: str, base_url: str = "https://qianfan.baidubce.com/v2"):
        super().__init__(api_key, base_url)
        self.default_model = "ernie-4.0-8k"

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion to Baidu Wenxin"""
        url = f"{self.base_url}/chat/completions"

        headers = self._build_headers()

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
            "top_p": request.top_p
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Baidu API error: {resp.status} - {error_text}")

                data = await resp.json()

                return ChatCompletion(
                    id=data.get("id", ""),
                    provider="baidu",
                    model=data.get("model", ""),
                    content=data["choices"][0]["message"]["content"],
                    finish_reason=data["choices"][0].get("finish_reason", ""),
                    usage=data.get("usage", {}),
                    created=data.get("created", 0)
                )

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Stream chat completion from Baidu Wenxin"""
        url = f"{self.base_url}/chat/completions"

        headers = self._build_headers()

        payload = {
            "model": request.model or self.default_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": True
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Baidu API error: {resp.status} - {error_text}")

                async for line in resp.content:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get('choices'):
                            delta = data['choices'][0].get('delta', {})
                            if delta.get('content'):
                                yield delta['content']


# ============================================================================
# Tencent (Hunyuan) Client
# ============================================================================

class TencentClient(LLMClientBase):
    """Tencent Hunyuan API client - Tencent (腾讯混元)"""

    TENCENT_MODELS = {
        "hunyuan": "hunyuan",
        "hunyuan-pro": "hunyuan-pro",
        "hunyuan-lite": "hunyuan-lite",
    }

    def __init__(self, api_key: str, base_url: str = "https://hunyuan.tencentcloudapi.com"):
        super().__init__(api_key, base_url)
        self.default_model = "hunyuan"

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion to Tencent Hunyuan"""
        url = self.base_url

        headers = {
            "Content-Type": "application/json"
        }

        # Convert messages to Hunyuan format
        messages_data = []
        for msg in request.messages:
            messages_data.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": request.model or self.default_model,
            "messages": messages_data,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Tencent API error: {resp.status} - {error_text}")

                data = await resp.json()

                return ChatCompletion(
                    id=data.get("id", ""),
                    provider="tencent",
                    model=data.get("model", ""),
                    content=data["choices"][0]["message"]["content"],
                    finish_reason=data["choices"][0].get("finish_reason", ""),
                    usage=data.get("usage", {}),
                    created=data.get("created", 0)
                )

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Stream chat completion from Tencent Hunyuan"""
        # Tencent doesn't support streaming in the same way
        result = await self.chat_completion(request)
        yield result.content


# ============================================================================
# Alibaba (Tongyi) Client
# ============================================================================

class AlibabaClient(LLMClientBase):
    """Alibaba Tongyi API client - Alibaba (阿里通义千问) - Supports Qwen 3.0 (2026年2月最新)"""

    # 2026年2月最新模型映射
    ALIBABA_MODELS = {
        # Qwen 3.0 series (2026年2月最新)
        "qwen-3": "qwen3-72b",
        "qwen-3-72b": "qwen3-72b",
        "qwen-3-32b": "qwen3-32b",
        "qwen-3-8b": "qwen3-8b",
        "qwen-3-4b": "qwen3-4b",
        "qwen-3-thinking": "qwen3-72b-thinking",
        "qwen-3-ultra": "qwen3-ultra",
        # Qwen 2.5 series (legacy)
        "qwen-2-5": "qwen2.5-72b-instruct",
        "qwen-2-5-72b": "qwen2.5-72b-instruct",
        "qwen-2-5-32b": "qwen2.5-32b-instruct",
        "qwen-2-5-14b": "qwen2.5-14b-instruct",
        "qwen-2-5-7b": "qwen2.5-7b-instruct",
        # Qwen 2 series
        "qwen-2": "qwen-turbo",
        "qwen-plus": "qwen-plus",
        "qwen-max": "qwen-max",
        "qwen-max-long": "qwen-max-long",
        # Vision models
        "qwen-vl": "qwen-vl-plus",
        "qwen-vl-max": "qwen-vl-max",
        "qwen2.5-vl": "qwen2.5-vl-72b-instruct",
    }

    def __init__(self, api_key: str, base_url: str = "https://dashscope.aliyuncs.com/api/v1"):
        super().__init__(api_key, base_url)
        self.default_model = "qwen3-72b"  # Default to Qwen 3.0 72B

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        """Send chat completion to Alibaba Tongyi"""
        url = f"{self.base_url}/services/aigc/text-generation/generation"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": request.model or self.default_model,
            "input": {
                "messages": [{"role": m.role, "content": m.content} for m in request.messages]
            },
            "parameters": {
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "top_p": request.top_p
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Alibaba API error: {resp.status} - {error_text}")

                data = await resp.json()

                return ChatCompletion(
                    id=data.get("request_id", ""),
                    provider="alibaba",
                    model=request.model or self.default_model,
                    content=data["output"]["text"],
                    finish_reason="stop",
                    usage=data.get("usage", {}),
                    created=int(datetime.now().timestamp())
                )

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Stream chat completion from Alibaba Tongyi"""
        url = f"{self.base_url}/services/aigc/text-generation/generation"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": request.model or self.default_model,
            "input": {
                "messages": [{"role": m.role, "content": m.content} for m in request.messages]
            },
            "parameters": {
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "top_p": request.top_p,
                "incremental_output": True
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Alibaba API error: {resp.status} - {error_text}")

                async for line in resp.content:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        if data.get("output") and data["output"].get("text"):
                            yield data["output"]["text"]


# ============================================================================
# Video Generation Clients (Seedream, Seedance)
# ============================================================================

@dataclass
class VideoGenerationTask:
    """Video generation task"""
    task_id: str
    status: str
    progress: float = 0.0
    video_url: Optional[str] = None
    error: Optional[str] = None


class SeedreamClient(LLMClientBase):
    """ByteDance Seedream (即梦/海螺) image generation client - Supports Seedream 6.0 (2026年2月最新)"""

    # 2026年2月最新模型映射
    SEEDREAM_MODELS = {
        # Seedream 6.0 series (2026年2月最新)
        "seedream-6-0": "seedream-6.0",
        "seedream-6": "seedream-6.0",
        "seedream-5-0": "seedream-5.0",
        "seedream-5": "seedream-5.0",
        "seedream-3-0": "seedream-3.0",
        "seedream": "seedream-6.0",
    }

    def __init__(self, api_key: str, base_url: str = "https://api.minimax.chat/v1"):
        super().__init__(api_key, base_url)
        self.default_model = "seedream-6.0"  # Default to Seedream 6.0

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        settings: Dict[str, Any] = None
    ) -> GenerationResult:
        """Generate image using Seedream"""
        settings = settings or {}

        url = f"{self.base_url}/text2image_v2"

        headers = self._build_headers()

        payload = {
            "model": self.default_model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": settings.get("width", 1024),
            "height": settings.get("height", 1024),
            "steps": settings.get("steps", 25),
            "cfg_scale": settings.get("cfg_scale", 7.0),
            "seed": settings.get("seed", -1),
            "batch_size": settings.get("batch_size", 1)
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Seedream API error: {resp.status} - {error_text}")

                data = await resp.json()

                images = data.get("images", [])

                return GenerationResult(
                    success=True,
                    files=[img.get("url") for img in images],
                    metadata={"generator": "seedream", "prompt": prompt},
                    generation_time=data.get("generation_time", 0.0)
                )

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        raise NotImplementedError("Use generate_image instead")

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        raise NotImplementedError("Use generate_image instead")


class SeedanceClient(LLMClientBase):
    """ByteDance Seedance (即梦/视频) video generation client - Supports Seedance 3.0 (2026年2月最新)"""

    # 2026年2月最新模型映射
    SEEDANCE_MODELS = {
        # Seedance 3.0 series (2026年2月最新)
        "seedance-3-0": "seedance-3.0",
        "seedance-3": "seedance-3.0",
        "seedance-2-0": "seedance-2.0",
        "seedance-2": "seedance-2.0",
        "seedance-1-0": "seedance-1.0",
    }

    def __init__(self, api_key: str, base_url: str = "https://api.minimax.chat/v1"):
        super().__init__(api_key, base_url)
        self.default_model = "seedance-3.0"  # Default to Seedance 3.0

    async def generate_video(
        self,
        prompt: str,
        negative_prompt: str = "",
        settings: Dict[str, Any] = None
    ) -> VideoGenerationTask:
        """Generate video using Seedance"""
        settings = settings or {}

        url = f"{self.base_url}/video_generation"

        headers = self._build_headers()

        payload = {
            "model": self.default_model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration": settings.get("duration", 5),
            "aspect_ratio": settings.get("aspect_ratio", "16:9"),
            "fps": settings.get("fps", 24)
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Seedance API error: {resp.status} - {error_text}")

                data = await resp.json()

                return VideoGenerationTask(
                    task_id=data.get("task_id", ""),
                    status=data.get("status", "pending"),
                    progress=data.get("progress", 0.0),
                    video_url=data.get("video_url")
                )


# =============================================================================
# Local Ollama Client (本地Ollama模型)
# =============================================================================

class OllamaClient(LLMClientBase):
    """Ollama local LLM client - Supports all Ollama models (llama3, qwen2.5, mistral, etc.)"""

    # 支持的模型列表
    OLLAMA_MODELS = {
        "llama3": "llama3",
        "llama3.1": "llama3.1",
        "llama3.2": "llama3.2",
        "llama2": "llama2",
        "qwen2.5": "qwen2.5",
        "qwen2.5-coder": "qwen2.5-coder",
        "qwen2.5-math": "qwen2.5-math",
        "mistral": "mistral",
        "mixtral": "mixtral",
        "phi3": "phi3",
        "phi3.5": "phi3.5",
        "gemma2": "gemma2",
        "gemma": "gemma",
        "codellama": "codellama",
        "orca-mini": "orca-mini",
        "neural-chat": "neural-chat",
        # 用户自定义模型
        "kimi-k2.5": "kimi-k2.5",
    }

    def __init__(self, api_key: str = "", base_url: str = "http://localhost:11434"):
        # Ollama不需要API key，但保留api_key参数以保持接口一致性
        import os
        super().__init__(api_key, base_url)
        # 优先从环境变量读取默认模型
        self.default_model = os.getenv("OLLAMA_MODEL", "llama3")

    async def chat_completion(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> ChatCompletion:
        """Send chat completion request to Ollama"""
        model = model or self.default_model

        # 构建Ollama格式的messages
        ollama_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        url = f"{self.base_url}/api/chat"

        payload = {
            "model": model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"Ollama API error: {resp.status} - {error_text}")

                    result = await resp.json()

                    return ChatCompletion(
                        id=result.get("id", f"ollama-{datetime.now().timestamp()}"),
                        provider="ollama",
                        model=model,
                        content=result.get("message", {}).get("content", ""),
                        finish_reason=result.get("done_reason", "stop"),
                        usage={
                            "prompt_tokens": result.get("prompt_eval_count", 0),
                            "completion_tokens": result.get("eval_count", 0),
                            "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0)
                        },
                        created=int(datetime.now().timestamp())
                    )
        except Exception as e:
            logger.error(f"Ollama chat completion error: {e}")
            raise

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """Simple generate request (non-chat)"""
        model = model or self.default_model

        url = f"{self.base_url}/api/generate"

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"Ollama API error: {resp.status} - {error_text}")

                    result = await resp.json()
                    return result.get("response", "")
        except Exception as e:
            logger.error(f"Ollama generate error: {e}")
            raise

    def list_models(self) -> List[Dict[str, Any]]:
        """List available Ollama models"""
        try:
            import requests
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return [{"name": m["name"], "size": m.get("size", 0)} for m in data.get("models", [])]
        except Exception as e:
            logger.warning(f"Failed to list Ollama models: {e}")
        return []

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        """Send chat completion request with streaming to Ollama"""
        model = request.model or self.default_model

        # 构建Ollama格式的messages
        ollama_messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        url = f"{self.base_url}/api/chat"

        payload = {
            "model": model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"Ollama API error: {resp.status} - {error_text}")

                    async for line in resp.content:
                        if line:
                            line = line.decode('utf-8').strip()
                            if line.startswith('data: '):
                                data = json.loads(line[6:])
                                if 'message' in data:
                                    yield ChatCompletion(
                                        id=data.get("id", f"ollama-{datetime.now().timestamp()}"),
                                        provider="ollama",
                                        model=model,
                                        content=data.get("message", {}).get("content", ""),
                                        finish_reason=data.get("done_reason", "stop"),
                                        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                                        created=int(datetime.now().timestamp())
                                    )
        except Exception as e:
            logger.error(f"Ollama stream error: {e}")
            raise


# =============================================================================
# DeepSeek Client
# =============================================================================

class DeepSeekClient(LLMClientBase):
    """DeepSeek AI client - Supports DeepSeek R1, V3, Coder series"""

    # DeepSeek模型映射
    DEEPSEEK_MODELS = {
        "deepseek-r1": "deepseek-reasoner",
        "deepseek-v3": "deepseek-chat",
        "deepseek-coder": "deepseek-coder",
        "deepseek-math": "deepseek-math",
    }

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        super().__init__(api_key, base_url)
        self.default_model = "deepseek-chat"  # Default to V3

    async def chat_completion(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs
    ) -> ChatCompletion:
        """Send chat completion request to DeepSeek"""
        model = model or self.default_model

        # Map model name
        model = self.DEEPSEEK_MODELS.get(model, model)

        url = f"{self.base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"DeepSeek API error: {resp.status} - {error_text}")

                    result = await resp.json()

                    choice = result.get("choices", [{}])[0]
                    message = choice.get("message", {})

                    return ChatCompletion(
                        id=result.get("id", f"deepseek-{datetime.now().timestamp()}"),
                        provider="deepseek",
                        model=model,
                        content=message.get("content", ""),
                        finish_reason=choice.get("finish_reason", "stop"),
                        usage=result.get("usage", {}),
                        created=result.get("created", int(datetime.now().timestamp()))
                    )
        except Exception as e:
            logger.error(f"DeepSeek chat completion error: {e}")
            raise

    async def get_task_status(self, task_id: str) -> VideoGenerationTask:
        """Get video generation task status"""
        url = f"{self.base_url}/video_generation/{task_id}"

        headers = self._build_headers()

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Seedance API error: {resp.status} - {error_text}")

                data = await resp.json()

                return VideoGenerationTask(
                    task_id=task_id,
                    status=data.get("status", "pending"),
                    progress=data.get("progress", 0.0),
                    video_url=data.get("video_url")
                )

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletion:
        raise NotImplementedError("Use generate_video instead")

    async def chat_completion_stream(self, request: ChatCompletionRequest):
        raise NotImplementedError("Use generate_video instead")


# ============================================================================
# Dynamic Model Registry with YAML Configuration and Hot-Reload
# ============================================================================

# Define a fallback class if watchdog is not available
if HAS_WATCHDOG and FileSystemEventHandler:
    class ModelRegistryFileHandler(FileSystemEventHandler):
        """File system event handler for hot-reload"""

        def __init__(self, registry: 'ModelRegistry'):
            self.registry = registry
            self._last_modified = 0

        def on_modified(self, event):
            if event.is_directory:
                return
            if event.src_path.endswith('.yaml') or event.src_path.endswith('.yml'):
                current_time = datetime.now().timestamp()
                # Debounce: only reload if modified after 1 second
                if current_time - self._last_modified > 1:
                    self._last_modified = current_time
                    logger.info(f"Detected config change: {event.src_path}")
                    self.registry.reload_from_yaml(event.src_path)
else:
    # Fallback - no-op handler when watchdog is not available
    class ModelRegistryFileHandler:
        """Fallback file system event handler when watchdog not available"""

        def __init__(self, registry: 'ModelRegistry'):
            self.registry = registry


class ModelRegistry:
    """
    Dynamic model registry with YAML configuration and hot-reload support
    Supports 2026年2月最新 models
    """

    def __init__(self, config_path: Optional[str] = None):
        self._providers: Dict[str, Dict[str, Any]] = {}
        self._model_configs: Dict[str, Dict[str, Any]] = {}
        self._routing_config: Dict[str, Any] = {}
        self._observer = None  # Type depends on HAS_WATCHDOG
        self._config_path = config_path
        self._reload_callbacks: List[Callable] = []

        # Load config if provided
        if config_path:
            self.load_from_yaml(config_path)
            self.start_hot_reload(config_path)

    def register_provider(self, provider: str, config: Dict[str, Any]):
        """Register a new provider with its config"""
        self._providers[provider] = config

    def register_model(self, model_id: str, config: Dict[str, Any]):
        """Register a new model"""
        self._model_configs[model_id] = config

    def get_provider_config(self, provider: str) -> Optional[Dict[str, Any]]:
        """Get provider configuration"""
        return self._providers.get(provider)

    def get_model_config(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get model configuration"""
        return self._model_configs.get(model_id)

    def list_providers(self) -> List[str]:
        """List all registered providers"""
        return list(self._providers.keys())

    def list_models(self, provider: Optional[str] = None) -> List[str]:
        """List all models, optionally filtered by provider"""
        if provider:
            return [
                model_id for model_id, config in self._model_configs.items()
                if config.get("provider") == provider
            ]
        return list(self._model_configs.keys())

    def get_available_models(self) -> Dict[str, List[str]]:
        """Get available models grouped by provider"""
        result = {}
        for model_id, config in self._model_configs.items():
            provider = config.get("provider", "unknown")
            if provider not in result:
                result[provider] = []
            result[provider].append(model_id)
        return result

    def load_from_yaml(self, config_path: str):
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # Load providers
            if 'providers' in config:
                self._providers.clear()
                for provider_id, provider_config in config['providers'].items():
                    self._providers[provider_id] = provider_config

            # Load models
            if 'models' in config:
                self._model_configs.clear()
                for model_id, model_config in config['models'].items():
                    self._model_configs[model_id] = model_config

            # Load routing config
            if 'routing' in config:
                self._routing_config = config['routing']

            logger.info(f"Loaded {len(self._providers)} providers and {len(self._model_configs)} models from {config_path}")

            # Notify callbacks
            for callback in self._reload_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in reload callback: {e}")

        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise

    def reload_from_yaml(self, config_path: Optional[str] = None):
        """Reload configuration from YAML file"""
        path = config_path or self._config_path
        if path:
            self.load_from_yaml(path)
            logger.info(f"Configuration reloaded from {path}")

    def start_hot_reload(self, config_path: str):
        """Start hot-reload file watcher"""
        if not HAS_WATCHDOG:
            logger.debug("Hot-reload not available - watchdog not installed")
            return

        if self._observer is not None:
            self._observer.stop()

        config_dir = os.path.dirname(os.path.abspath(config_path))
        event_handler = ModelRegistryFileHandler(self)

        self._observer = Observer()
        self._observer.schedule(event_handler, config_dir, recursive=False)
        self._observer.start()
        logger.info(f"Started hot-reload watcher for {config_path}")

    def stop_hot_reload(self):
        """Stop hot-reload file watcher"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("Stopped hot-reload watcher")

    def on_reload(self, callback: Callable):
        """Register a callback to be called when config is reloaded"""
        self._reload_callbacks.append(callback)

    def get_routing_config(self) -> Dict[str, Any]:
        """Get routing configuration"""
        return self._routing_config

    def get_model_by_capability(self, capability: str) -> List[str]:
        """Get models that support a specific capability"""
        return [
            model_id for model_id, config in self._model_configs.items()
            if capability in config.get("capabilities", [])
        ]

    def get_models_by_use_case(self, use_case: str) -> List[str]:
        """Get models optimized for a specific use case"""
        return [
            model_id for model_id, config in self._model_configs.items()
            if use_case in config.get("use_cases", [])
        ]


# ============================================================================
# Model Router with Multiple Routing Strategies
# ============================================================================

class ModelRouter:
    """
    Smart model router with multiple routing strategies
    Supports: quality_optimized, cost_optimized, latency_optimized, balanced
    """

    def __init__(self, registry: Optional[ModelRegistry] = None):
        self.registry = registry  # 如果未提供registry，则在运行时动态设置
        self._current_strategy = "balanced"
        self._provider_clients: Dict[str, Any] = {}

    def set_strategy(self, strategy: str):
        """Set the routing strategy"""
        valid_strategies = ["quality_optimized", "cost_optimized", "latency_optimized", "balanced"]
        if strategy not in valid_strategies:
            logger.warning(f"Invalid strategy: {strategy}, using 'balanced'")
            strategy = "balanced"
        self._current_strategy = strategy
        logger.info(f"Routing strategy set to: {strategy}")

    def select_model(
        self,
        required_capabilities: Optional[List[str]] = None,
        use_case: Optional[str] = None,
        preferred_provider: Optional[str] = None,
        exclude_models: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Select the best model based on routing strategy

        Args:
            required_capabilities: Required capabilities (e.g., ['vision', 'code'])
            use_case: Specific use case (e.g., 'code_generation')
            preferred_provider: Preferred provider
            exclude_models: Models to exclude from selection

        Returns:
            Selected model ID or None
        """
        # Get candidate models
        candidates = []

        if required_capabilities:
            for cap in required_capabilities:
                candidates.extend(self.registry.get_model_by_capability(cap))
            candidates = list(set(candidates))
        else:
            candidates = self.registry.list_models()

        if use_case:
            use_case_models = self.registry.get_models_by_use_case(use_case)
            candidates = list(set(candidates) & set(use_case_models))

        if preferred_provider:
            provider_models = self.registry.list_models(preferred_provider)
            candidates = list(set(candidates) & set(provider_models))

        if exclude_models:
            candidates = [m for m in candidates if m not in exclude_models]

        if not candidates:
            return None

        # Apply routing strategy
        if self._current_strategy == "quality_optimized":
            return self._select_by_quality(candidates)
        elif self._current_strategy == "cost_optimized":
            return self._select_by_cost(candidates)
        elif self._current_strategy == "latency_optimized":
            return self._select_by_latency(candidates)
        else:  # balanced
            return self._select_balanced(candidates)

    def _select_by_quality(self, candidates: List[str]) -> Optional[str]:
        """Select highest quality model"""
        best_model = None
        best_score = -1

        for model_id in candidates:
            config = self.registry.get_model_config(model_id)
            if config:
                score = config.get("quality_score", 0)
                if score > best_score:
                    best_score = score
                    best_model = model_id

        return best_model

    def _select_by_cost(self, candidates: List[str]) -> Optional[str]:
        """Select lowest cost model"""
        cost_tier_order = {"budget": 0, "standard": 1, "premium": 2}
        best_model = None
        best_tier = 999

        for model_id in candidates:
            config = self.registry.get_model_config(model_id)
            if config:
                tier = config.get("cost_tier", "standard")
                tier_value = cost_tier_order.get(tier, 999)
                if tier_value < best_tier:
                    best_tier = tier_value
                    best_model = model_id

        return best_model

    def _select_by_latency(self, candidates: List[str]) -> Optional[str]:
        """Select lowest latency model"""
        latency_tier_order = {"fastest": 0, "fast": 1, "medium": 2, "slow": 3}
        best_model = None
        best_tier = 999

        for model_id in candidates:
            config = self.registry.get_model_config(model_id)
            if config:
                tier = config.get("latency_tier", "medium")
                tier_value = latency_tier_order.get(tier, 999)
                if tier_value < best_tier:
                    best_tier = tier_value
                    best_model = model_id

        return best_model

    def _select_balanced(self, candidates: List[str]) -> Optional[str]:
        """Select balanced model (quality, cost, latency)"""
        best_model = None
        best_score = -1

        cost_tier_order = {"budget": 0, "standard": 1, "premium": 2}
        latency_tier_order = {"fastest": 0, "fast": 1, "medium": 2, "slow": 3}

        for model_id in candidates:
            config = self.registry.get_model_config(model_id)
            if config:
                # Calculate weighted score
                quality = config.get("quality_score", 50)

                cost_tier = config.get("cost_tier", "standard")
                cost_score = (2 - cost_tier_order.get(cost_tier, 1)) * 30

                latency_tier = config.get("latency_tier", "medium")
                latency_score = (3 - latency_tier_order.get(latency_tier, 2)) * 20

                total_score = quality + cost_score + latency_score

                if total_score > best_score:
                    best_score = total_score
                    best_model = model_id

        return best_model

    def register_client(self, provider: str, client: Any):
        """Register a provider client for actual API calls"""
        self._provider_clients[provider] = client

    async def route_and_call(
        self,
        messages: List[ChatMessage],
        required_capabilities: Optional[List[str]] = None,
        use_case: Optional[str] = None,
        preferred_provider: Optional[str] = None,
        **kwargs
    ) -> ChatCompletion:
        """
        Route to the best model and execute the request
        """
        model_id = self.select_model(
            required_capabilities=required_capabilities,
            use_case=use_case,
            preferred_provider=preferred_provider
        )

        if not model_id:
            raise ValueError("No suitable model found for the request")

        model_config = self.registry.get_model_config(model_id)
        provider = model_config.get("provider")

        # Get or create client
        if provider in self._provider_clients:
            client = self._provider_clients[provider]
        else:
            raise ValueError(f"No client registered for provider: {provider}")

        # Create request
        request = ChatCompletionRequest(
            model=model_id,
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 4096),
            top_p=kwargs.get("top_p", 1.0),
            stream=kwargs.get("stream", False)
        )

        # Execute request
        return await client.chat_completion(request)


# Global model registry - initialized with YAML config if available (MUST be before model_router!)
config_path = os.path.join(os.path.dirname(__file__), "..", "config", "models.yaml")
if os.path.exists(config_path):
    model_registry = ModelRegistry(config_path)
else:
    model_registry = ModelRegistry()

# Global model router (now model_registry is defined)
model_router = ModelRouter(registry=model_registry)


class LLMProviderManager:
    """Manager for multiple LLM providers"""

    def __init__(self):
        self.clients: Dict[LLMProvider, LLMClientBase] = {}
        self.default_provider: Optional[LLMProvider] = None

    def register_client(self, provider: LLMProvider, client: LLMClientBase):
        """Register a client for a provider"""
        self.clients[provider] = client
        if self.default_provider is None:
            self.default_provider = provider

    def get_client(self, provider: Optional[LLMProvider] = None) -> LLMClientBase:
        """Get client for provider"""
        if provider is None:
            provider = self.default_provider

        if provider not in self.clients:
            raise ValueError(f"No client registered for provider: {provider}")

        return self.clients[provider]

    async def chat(self, message: str, provider: Optional[LLMProvider] = None,
                   model: Optional[str] = None, **kwargs) -> ChatCompletion:
        """Send chat message"""
        client = self.get_client(provider)

        request = ChatCompletionRequest(
            model=model or client.default_model,
            messages=[ChatMessage(role="user", content=message)],
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 4096),
            top_p=kwargs.get("top_p", 1.0)
        )

        return await client.chat_completion(request)

    async def chat_with_history(self, messages: List[ChatMessage],
                                 provider: Optional[LLMProvider] = None,
                                 model: Optional[str] = None, **kwargs) -> ChatCompletion:
        """Send chat with message history"""
        client = self.get_client(provider)

        request = ChatCompletionRequest(
            model=model or client.default_model,
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 4096),
            top_p=kwargs.get("top_p", 1.0)
        )

        return await client.chat_completion(request)

    async def chat_with_tools(self, message: str, tools: List[Dict[str, Any]],
                              provider: Optional[LLMProvider] = None,
                              model: Optional[str] = None, **kwargs) -> ChatCompletion:
        """Send chat with tools/functions"""
        client = self.get_client(provider)

        request = ChatCompletionRequest(
            model=model or client.default_model,
            messages=[ChatMessage(role="user", content=message)],
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 4096),
            top_p=kwargs.get("top_p", 1.0),
            tools=tools
        )

        return await client.chat_completion(request)

    # Domestic AI Priority Selection
    # Priority: Ollama (local) > Alibaba (百炼) > DeepSeek > Kimi > GLM > MiniMax > Doubao > Baidu > Others
    DOMESTIC_PROVIDER_PRIORITY = [
        LLMProvider.OLLAMA,       # 本地Ollama优先
        LLMProvider.ALIBABA,      # 阿里百炼(Qwen3.5)
        LLMProvider.DEEPSEEK,     # DeepSeek
        LLMProvider.KIMI,         # Kimi (Moonshot)
        LLMProvider.GLM,          # 智谱GLM-5
        LLMProvider.MINIMAX,      # MiniMax
        LLMProvider.DOUBAO,       # 豆包
        LLMProvider.BAIDU,        # 百度文心
        LLMProvider.TENCENT,      # 腾讯混元
        LLMProvider.OPENROUTER,   # OpenRouter (备选)
        LLMProvider.OPENAI,       # OpenAI (最后备选)
    ]

    async def chat_with_domestic_priority(
        self,
        message: str,
        model: Optional[str] = None,
        prefer_local: bool = True,
        **kwargs
    ) -> ChatCompletion:
        """
        使用国产AI优先策略发送聊天请求

        优先级顺序:
        1. Ollama (本地) - 如果prefer_local=True
        2. 阿里百炼 (Qwen3.5)
        3. DeepSeek
        4. Kimi (Moonshot)
        5. GLM-5 (智谱)
        6. MiniMax
        7. 豆包
        8. 百度文心
        9. 腾讯混元
        10. OpenRouter (国际备选)

        Args:
            message: 聊天消息
            model: 指定模型（可选）
            prefer_local: 是否优先使用本地模型
            **kwargs: 其他参数

        Returns:
            ChatCompletion响应
        """
        last_error = None

        for provider in self.DOMESTIC_PROVIDER_PRIORITY:
            # 如果不优先本地，跳过Ollama
            if not prefer_local and provider == LLMProvider.OLLAMA:
                continue

            # 检查是否有该provider的客户端
            if provider not in self.clients:
                continue

            try:
                client = self.clients[provider]
                request = ChatCompletionRequest(
                    model=model or client.default_model,
                    messages=[ChatMessage(role="user", content=message)],
                    temperature=kwargs.get("temperature", 0.7),
                    max_tokens=kwargs.get("max_tokens", 4096),
                    top_p=kwargs.get("top_p", 1.0)
                )

                response = await client.chat_completion(request)
                logger.info(f"Successfully used domestic provider: {provider.value}")
                return response

            except Exception as e:
                logger.warning(f"Provider {provider.value} failed: {e}")
                last_error = e
                continue

        # 所有国产提供商都失败
        raise Exception(
            f"All domestic AI providers failed. Last error: {last_error}. "
            f"Available providers: {list(self.clients.keys())}"
        )

    async def chat_completion(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        messages: Optional[List[ChatMessage]] = None,
        **kwargs
    ) -> ChatCompletion:
        """
        统一的chat completion接口

        Args:
            provider: 指定提供商 (如 "domestic" 则使用国产优先)
            model: 模型名称
            messages: 消息列表
            **kwargs: 其他参数

        Returns:
            ChatCompletion响应
        """
        # 如果指定了"domestic"，使用国产优先策略
        if provider == "domestic" or provider == "china" or provider == "国产":
            if not messages:
                raise ValueError("messages is required")
            if len(messages) == 0:
                raise ValueError("messages cannot be empty")

            # 将多消息合并为一个字符串
            message_text = "\n".join([f"{m.role}: {m.content}" for m in messages])
            return await self.chat_with_domestic_priority(
                message_text,
                model=model,
                prefer_local=kwargs.get("prefer_local", True),
                **kwargs
            )

        # 正常模式
        provider_enum = LLMProvider(provider.lower()) if provider else self.default_provider
        client = self.get_client(provider_enum)

        if not messages:
            messages = [ChatMessage(role="user", content=kwargs.get("message", ""))]

        request = ChatCompletionRequest(
            model=model or client.default_model,
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 4096),
            top_p=kwargs.get("top_p", 1.0),
            stream=kwargs.get("stream", False)
        )

        return await client.chat_completion(request)


# Factory function
def create_llm_client(provider: str, api_key: str, base_url: Optional[str] = None) -> LLMClientBase:
    """Factory function to create LLM client"""
    provider_enum = LLMProvider(provider.lower())

    if provider_enum == LLMProvider.OPENAI:
        return OpenAIClient(api_key, base_url or "https://api.openai.com/v1")
    elif provider_enum == LLMProvider.ANTHROPIC:
        return AnthropicClient(api_key, base_url or "https://api.anthropic.com")
    elif provider_enum == LLMProvider.GOOGLE:
        return GoogleClient(api_key, base_url or "https://generativelanguage.googleapis.com/v1beta")
    elif provider_enum == LLMProvider.OPENROUTER:
        return OpenRouterClient(api_key, base_url or "https://openrouter.ai/api/v1")
    elif provider_enum == LLMProvider.KIMI:
        return KimiClient(api_key, base_url or "https://api.moonshot.cn/v1")
    elif provider_enum == LLMProvider.GLM:
        return GLMClient(api_key, base_url or "https://open.bigmodel.cn/api/paas/v4")
    elif provider_enum == LLMProvider.MINIMAX:
        return MiniMaxClient(api_key, base_url or "https://api.minimax.chat/v1")
    elif provider_enum == LLMProvider.DOUBAO:
        return DoubaoClient(api_key, base_url or "https://ark.cn-beijing.volces.com/api/v3")
    elif provider_enum == LLMProvider.BAIDU:
        return BaiduClient(api_key, base_url or "https://qianfan.baidubce.com/v2")
    elif provider_enum == LLMProvider.TENCENT:
        return TencentClient(api_key, base_url or "https://hunyuan.tencentcloudapi.com")
    elif provider_enum == LLMProvider.ALIBABA:
        return AlibabaClient(api_key, base_url or "https://dashscope.aliyuncs.com/api/v1")
    elif provider_enum == LLMProvider.SEEDREAM:
        return SeedreamClient(api_key, base_url or "https://api.minimax.chat/v1")
    elif provider_enum == LLMProvider.SEEDANCE:
        return SeedanceClient(api_key, base_url or "https://api.minimax.chat/v1")
    elif provider_enum == LLMProvider.OLLAMA:
        # 优先从环境变量读取配置
        import os
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return OllamaClient(api_key, base_url or ollama_url)
    elif provider_enum == LLMProvider.DEEPSEEK:
        return DeepSeekClient(api_key, base_url or "https://api.deepseek.com")
    else:
        raise ValueError(f"Unsupported provider: {provider}")


# Example usage
async def main():
    logging.basicConfig(level=logging.INFO)

    # Initialize manager
    manager = LLMProviderManager()

    # Register clients
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    if openrouter_key:
        manager.register_client(LLMProvider.OPENROUTER, OpenRouterClient(openrouter_key))

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        manager.register_client(LLMProvider.ANTHROPIC, AnthropicClient(anthropic_key))

    # Test chat
    try:
        response = await manager.chat(
            "What is the capital of France?",
            provider=LLMProvider.OPENROUTER,
            model="anthropic/claude-3.5-sonnet"
        )
        print(f"Response: {response.content}")
        print(f"Model: {response.model}")
        print(f"Provider: {response.provider}")
        print(f"Usage: {response.usage}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
