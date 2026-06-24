#!/usr/bin/env python3
"""
Nanobot Factory - Unified AIGC Adapter Interface
Abstract base class and implementations for various AI generation services

@author MiniMax Agent
@date 2026-02-25
@description 统一适配器接口，支持ComfyUI、即梦、可灵、豆包、GPT等
"""

import os
import json
import asyncio
import logging
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from abc import ABC, abstractmethod
from enum import Enum
import aiohttp
import base64

logger = logging.getLogger(__name__)


class GeneratorType(Enum):
    """Supported generator types"""
    COMFYUI = "comfyui"
    JIMENG = "jimeng"      # 即梦
    KLING = "kling"        # 可灵
    DOUBAO = "doubao"      # 豆包
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


class TaskStatus(Enum):
    """Generation task status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class GenerationTask:
    """Represents a generation task"""
    task_id: str
    generator: GeneratorType
    prompt: str
    negative_prompt: str = ""
    settings: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    results: List[str] = field(default_factory=list)
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class GenerationResult:
    """Represents generation result"""
    success: bool
    files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    generation_time: float = 0.0


# ============================================================================
# Abstract Base Adapter
# ============================================================================

class AIGCAdapter(ABC):
    """
    Abstract base class for AI generation adapters.
    All generator implementations should inherit from this class.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = self.__class__.__name__
        self.is_available = False
        self._session: Optional[aiohttp.ClientSession] = None

    async def initialize(self) -> bool:
        """
        Initialize the adapter. Override in subclasses.
        Returns True if initialization successful.
        """
        try:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=300),
                connector=aiohttp.TCPConnector(limit=10)
            )
            self.is_available = await self.check_health()
            logger.info(f"{self.name} initialized: available={self.is_available}")
            return self.is_available
        except Exception as e:
            logger.error(f"Error initializing {self.name}: {e}")
            return False

    async def close(self):
        """Cleanup resources"""
        if self._session:
            await self._session.close()
            self._session = None

    @abstractmethod
    async def check_health(self) -> bool:
        """
        Check if the service is available.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        settings: Dict[str, Any] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> GenerationResult:
        """
        Generate content based on prompt.
        Must be implemented by subclasses.

        Args:
            prompt: Positive prompt
            negative_prompt: Negative prompt
            settings: Generator-specific settings
            progress_callback: Callback for progress updates (0-100)

        Returns:
            GenerationResult with files and metadata
        """
        pass

    @abstractmethod
    async def get_task_status(self, task_id: str) -> TaskStatus:
        """
        Get status of a generation task.
        For async generators that return task IDs.
        """
        pass

    @property
    def supported_settings(self) -> Dict[str, Any]:
        """
        Return supported settings for this adapter.
        Override in subclasses to provide custom settings.
        """
        return {
            "width": {"type": "int", "default": 1024, "min": 256, "max": 4096},
            "height": {"type": "int", "default": 1024, "min": 256, "max": 4096},
            "steps": {"type": "int", "default": 20, "min": 1, "max": 150},
            "cfg_scale": {"type": "float", "default": 7.0, "min": 1.0, "max": 30.0},
            "seed": {"type": "int", "default": -1},
            "batch_size": {"type": "int", "default": 1, "min": 1, "max": 16}
        }


# ============================================================================
# ComfyUI Adapter
# ============================================================================

class ComfyUIAdapter(AIGCAdapter):
    """
    Adapter for ComfyUI local generation.
    Supports custom nodes and workflows.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.host = config.get("host", "127.0.0.1")
        self.port = config.get("port", 8188)

        # SSRF protection: Only allow localhost connections
        allowed_hosts = ("127.0.0.1", "localhost", "::1", "0.0.0.0")
        if self.host not in allowed_hosts:
            raise ValueError(f"SSRF protection: ComfyUI host must be localhost, got: {self.host}")

        # Port validation
        if not (1 <= self.port <= 65535):
            raise ValueError(f"Invalid port: {self.port}")

        self.workflow_dir = config.get("workflow_dir", "./workflows")
        self.output_dir = config.get("output_dir", "./outputs")
        self._current_history_id: Optional[str] = None

    async def check_health(self) -> bool:
        """Check if ComfyUI is running"""
        try:
            if not self._session:
                return False

            async with self._session.get(f"http://{self.host}:{self.port}/system_stats") as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"ComfyUI health check failed: {e}")
            return False

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        settings: Dict[str, Any] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> GenerationResult:
        """
        Generate image using ComfyUI default workflow.
        """
        start_time = time.time()
        settings = settings or {}

        try:
            # Build workflow prompt
            workflow = self._build_workflow(prompt, negative_prompt, settings)

            # Queue the prompt
            async with self._session.post(
                f"http://{self.host}:{self.port}/prompt",
                json={"prompt": workflow}
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return GenerationResult(success=False, error=f"Queue failed: {error}")

                result = await resp.json()
                self._current_history_id = result.get("prompt_id")

            # Poll for completion
            files = await self._wait_for_completion(progress_callback)

            generation_time = time.time() - start_time

            return GenerationResult(
                success=True,
                files=files,
                metadata={
                    "generator": "comfyui",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "settings": settings
                },
                generation_time=generation_time
            )

        except Exception as e:
            logger.error(f"ComfyUI generation error: {e}")
            return GenerationResult(success=False, error=str(e))

    def _build_workflow(self, prompt: str, negative_prompt: str, settings: Dict[str, Any]) -> Dict:
        """Build ComfyUI workflow JSON"""
        width = settings.get("width", 1024)
        height = settings.get("height", 1024)
        steps = settings.get("steps", 20)
        cfg_scale = settings.get("cfg_scale", 7.0)
        seed = settings.get("seed", -1)
        batch_size = settings.get("batch_size", 1)

        # Simplified default workflow
        return {
            "1": {
                "inputs": {
                    "text": prompt,
                    "clip": ["3", 0]
                },
                "class_type": "CLIPTextEncode"
            },
            "2": {
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["3", 0]
                },
                "class_type": "CLIPTextEncode"
            },
            "3": {
                "inputs": {
                    "model_name": "sd15_default"
                },
                "class_type": "CheckpointLoaderSimple"
            },
            "4": {
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg_scale,
                    "sampler_name": "euler",
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                    "model": ["3", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            },
            "5": {
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": batch_size
                },
                "class_type": "EmptyLatentImage"
            },
            "6": {
                "inputs": {
                    "filename_prefix": "nanobot",
                    "images": ["4", 0]
                },
                "class_type": "SaveImage"
            }
        }

    async def _wait_for_completion(
        self,
        progress_callback: Optional[Callable[[float], None]] = None,
        timeout: int = 300
    ) -> List[str]:
        """Wait for generation to complete"""
        start = time.time()
        files = []

        while time.time() - start < timeout:
            # Check history
            if self._current_history_id:
                async with self._session.get(
                    f"http://{self.host}:{self.port}/history/{self._current_history_id}"
                ) as resp:
                    if resp.status == 200:
                        history = await resp.json()
                        if self._current_history_id in history:
                            status = history[self._current_history_id]
                            if status.get("status", {}).get("completed"):
                                # Get output images
                                outputs = status.get("outputs", {})
                                for node_id, node_data in outputs.items():
                                    if "images" in node_data:
                                        for img in node_data["images"]:
                                            files.append(
                                                f"{self.output_dir}/{img['subfolder']}/{img['filename']}"
                                            )
                                return files

            # Report progress (simplified)
            if progress_callback:
                progress_callback(min(90.0, (time.time() - start) / 3))

            await asyncio.sleep(1)

        return files

    async def get_task_status(self, task_id: str) -> TaskStatus:
        """Get task status from ComfyUI history"""
        try:
            async with self._session.get(
                f"http://{self.host}:{self.port}/history/{task_id}"
            ) as resp:
                if resp.status == 200:
                    history = await resp.json()
                    if task_id in history:
                        status = history[task_id].get("status", {})
                        if status.get("completed"):
                            return TaskStatus.COMPLETED
                        elif status.get("running"):
                            return TaskStatus.RUNNING
        except Exception as e:
            logger.error(f"Error getting task status: {e}")

        return TaskStatus.PENDING


# ============================================================================
# Jimeng (即梦) Adapter
# ============================================================================

class JimengAdapter(AIGCAdapter):
    """
    Adapter for Jimeng (即梦) AI image generation.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.endpoint = config.get("endpoint", "https://api.jimeng.io/v1")

    async def check_health(self) -> bool:
        """Check if Jimeng API is available"""
        if not self.api_key:
            return False

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with self._session.get(
                f"{self.endpoint}/models",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"Jimeng health check failed: {e}")
            return False

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        settings: Dict[str, Any] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> GenerationResult:
        """Generate image using Jimeng API"""
        start_time = time.time()
        settings = settings or {}

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": settings.get("width", 1024),
                "height": settings.get("height", 1024),
                "steps": settings.get("steps", 20),
                "cfg_scale": settings.get("cfg_scale", 7.0),
                "seed": settings.get("seed", -1),
                "num_images": settings.get("batch_size", 1)
            }

            async with self._session.post(
                f"{self.endpoint}/txt2img",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return GenerationResult(success=False, error=f"API error: {error}")

                result = await resp.json()
                files = result.get("data", [])

                return GenerationResult(
                    success=True,
                    files=files,
                    metadata={"generator": "jimeng", "prompt": prompt},
                    generation_time=time.time() - start_time
                )

        except asyncio.TimeoutError:
            return GenerationResult(success=False, error="Generation timeout")
        except Exception as e:
            logger.error(f"Jimeng generation error: {e}")
            return GenerationResult(success=False, error=str(e))

    async def get_task_status(self, task_id: str) -> TaskStatus:
        """Get task status (Jimeng is sync, so just return completed)"""
        return TaskStatus.COMPLETED


# ============================================================================
# Kling (可灵) Adapter
# ============================================================================

class KlingAdapter(AIGCAdapter):
    """
    Adapter for Kling (可灵) AI video generation.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.endpoint = config.get("endpoint", "https://api.klingai.com/v1")

    async def check_health(self) -> bool:
        """Check if Kling API is available"""
        if not self.api_key:
            return False

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with self._session.get(
                f"{self.endpoint}/models",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"Kling health check failed: {e}")
            return False

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        settings: Dict[str, Any] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> GenerationResult:
        """Generate video using Kling API"""
        start_time = time.time()
        settings = settings or {}

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "duration": settings.get("duration", 5),
                "mode": settings.get("mode", "std"),  # std or pro
                "aspect_ratio": settings.get("aspect_ratio", "16:9"),
                "fps": settings.get("fps", 24)
            }

            # Submit generation task
            async with self._session.post(
                f"{self.endpoint}/generations",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return GenerationResult(success=False, error=f"API error: {error}")

                result = await resp.json()
                task_id = result.get("task_id")

            # Poll for completion
            files = await self._poll_task_status(task_id, headers, progress_callback)

            return GenerationResult(
                success=True,
                files=files,
                metadata={"generator": "kling", "prompt": prompt},
                generation_time=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"Kling generation error: {e}")
            return GenerationResult(success=False, error=str(e))

    async def _poll_task_status(
        self,
        task_id: str,
        headers: Dict[str, str],
        progress_callback: Optional[Callable[[float], None]] = None,
        timeout: int = 300
    ) -> List[str]:
        """Poll task status until completion"""
        start = time.time()
        files = []

        while time.time() - start < timeout:
            try:
                async with self._session.get(
                    f"{self.endpoint}/generations/{task_id}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        status = result.get("status")

                        if status == "completed":
                            files = result.get("output", {}).get("videos", [])
                            return files
                        elif status == "failed":
                            return []

                        if progress_callback:
                            progress = result.get("progress", 0) * 100
                            progress_callback(progress)

            except Exception as e:
                logger.error(f"Error polling task status: {e}")

            await asyncio.sleep(2)

        return files

    async def get_task_status(self, task_id: str) -> TaskStatus:
        """Get task status"""
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with self._session.get(
                f"{self.endpoint}/generations/{task_id}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    status = result.get("status")
                    if status == "completed":
                        return TaskStatus.COMPLETED
                    elif status == "failed":
                        return TaskStatus.FAILED
                    elif status == "processing":
                        return TaskStatus.RUNNING
        except Exception as e:
            logger.error(f"Error getting task status for {task_id}: {e}")

        return TaskStatus.PENDING


# ============================================================================
# Doubao (豆包) Adapter
# ============================================================================

class DoubaoAdapter(AIGCAdapter):
    """
    Adapter for Doubao (豆包) AI generation.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.endpoint = config.get("endpoint", "https://ark.cn-beijing.volces.com/api/v3")

    async def check_health(self) -> bool:
        """Check if Doubao API is available"""
        if not self.api_key:
            return False
        return True

    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        settings: Dict[str, Any] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> GenerationResult:
        """Generate using Doubao API"""
        start_time = time.time()
        settings = settings or {}

        try:
            # Doubao uses OpenAI-compatible API
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": settings.get("model", "doubao-image-v1"),
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": settings.get("width", 1024),
                "height": settings.get("height", 1024),
                "num_images": settings.get("batch_size", 1)
            }

            async with self._session.post(
                f"{self.endpoint}/images/generations",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    return GenerationResult(success=False, error=f"API error: {error}")

                result = await resp.json()
                files = [img.get("url") for img in result.get("data", [])]

                return GenerationResult(
                    success=True,
                    files=files,
                    metadata={"generator": "doubao", "prompt": prompt},
                    generation_time=time.time() - start_time
                )

        except Exception as e:
            logger.error(f"Doubao generation error: {e}")
            return GenerationResult(success=False, error=str(e))

    async def get_task_status(self, task_id: str) -> TaskStatus:
        """Get task status"""
        return TaskStatus.COMPLETED


# ============================================================================
# Adapter Manager
# ============================================================================

class AIGCAdapterManager:
    """
    Manager for all AIGC adapters.
    Handles lifecycle and provides unified interface.
    """

    def __init__(self):
        self.adapters: Dict[GeneratorType, AIGCAdapter] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._config: Dict[str, Dict[str, Any]] = {}

    async def initialize(self, config: Dict[str, Dict[str, Any]]):
        """
        Initialize all adapters from configuration.

        Args:
            config: Dictionary mapping generator types to their configs
                {
                    "comfyui": {"host": "127.0.0.1", "port": 8188},
                    "jimeng": {"api_key": "..."},
                    ...
                }
        """
        self._config = config
        self._session = aiohttp.ClientSession()

        # Initialize each adapter
        adapter_classes = {
            GeneratorType.COMFYUI: ComfyUIAdapter,
            GeneratorType.JIMENG: JimengAdapter,
            GeneratorType.KLING: KlingAdapter,
            GeneratorType.DOUBAO: DoubaoAdapter
        }

        for gen_type, adapter_class in adapter_classes.items():
            if gen_type.value in config:
                adapter = adapter_class(config[gen_type.value])
                adapter._session = self._session
                await adapter.initialize()
                self.adapters[gen_type] = adapter
                logger.info(f"Registered adapter: {gen_type.value}")

    async def close(self):
        """Cleanup all adapters"""
        for adapter in self.adapters.values():
            await adapter.close()

        if self._session:
            await self._session.close()

    def get_adapter(self, generator: GeneratorType) -> Optional[AIGCAdapter]:
        """Get adapter for specific generator"""
        return self.adapters.get(generator)

    def get_available_generators(self) -> List[GeneratorType]:
        """Get list of available generators"""
        return [
            gen_type for gen_type, adapter in self.adapters.items()
            if adapter.is_available
        ]

    async def generate(
        self,
        generator: GeneratorType,
        prompt: str,
        negative_prompt: str = "",
        settings: Dict[str, Any] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> GenerationResult:
        """
        Generate content using specified generator.
        Provides unified interface across all adapters.
        """
        adapter = self.get_adapter(generator)

        if not adapter:
            return GenerationResult(
                success=False,
                error=f"Generator {generator.value} not available"
            )

        if not adapter.is_available:
            return GenerationResult(
                success=False,
                error=f"Generator {generator.value} is not available (check API key/connection)"
            )

        return await adapter.generate(
            prompt=prompt,
            negative_prompt=negative_prompt,
            settings=settings,
            progress_callback=progress_callback
        )


# ============================================================================
# Factory Function
# ============================================================================

def create_adapter(generator_type: str, config: Dict[str, Any]) -> Optional[AIGCAdapter]:
    """
    Factory function to create adapter from type string.

    Args:
        generator_type: String like "comfyui", "jimeng", "kling", "doubao"
        config: Configuration dictionary

    Returns:
        AIGCAdapter instance or None if type not recognized
    """
    type_map = {
        "comfyui": ComfyUIAdapter,
        "jimeng": JimengAdapter,
        "kling": KlingAdapter,
        "doubao": DoubaoAdapter
    }

    adapter_class = type_map.get(generator_type.lower())
    if adapter_class:
        return adapter_class(config)

    return None


# ============================================================================
# Example Usage
# ============================================================================

async def main():
    """Example usage"""
    logging.basicConfig(level=logging.INFO)

    # Initialize manager
    manager = AIGCAdapterManager()

    await manager.initialize({
        "comfyui": {
            "host": "127.0.0.1",
            "port": 8188,
            "output_dir": "./outputs"
        },
        "jimeng": {
            "api_key": os.getenv("JIMENG_API_KEY", "")
        }
    })

    # List available generators
    available = manager.get_available_generators()
    print(f"Available generators: {[g.value for g in available]}")

    # Generate with ComfyUI (if available)
    if GeneratorType.COMFYUI in available:
        result = await manager.generate(
            GeneratorType.COMFYUI,
            "a beautiful landscape with mountains",
            "ugly, blurry, low quality",
            {"width": 512, "height": 512, "steps": 20}
        )
        print(f"Generation result: {result.success}")
        if result.files:
            print(f"Files: {result.files}")

    # Cleanup
    await manager.close()


if __name__ == "__main__":
    asyncio.run(main())
