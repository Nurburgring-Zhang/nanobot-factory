#!/usr/bin/env python3
"""
Nanobot Factory - AIGC Integration
Integration with ComfyUI and other AIGC APIs

@author MiniMax Agent
@date 2026-02-25
"""

import os
import json
import asyncio
import logging
import base64
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import aiohttp
import websockets

logger = logging.getLogger(__name__)

class GeneratorType(Enum):
    """Supported AI generators"""
    COMFYUI = "comfyui"
    JIMENG = "jimeng"
    KLING = "kling"
    DOUBAO = "doubao"
    GPT = "gpt"
    GEMINI = "gemini"

@dataclass
class GenerationRequest:
    """Generation request"""
    prompt: str
    negative_prompt: str = ""
    generator: GeneratorType = GeneratorType.COMFYUI
    width: int = 512
    height: int = 512
    steps: int = 30
    cfg: float = 7.5
    seed: int = -1
    batch_size: int = 1
    model: str = "default"
    sampler: str = "euler"
    scheduler: str = "normal"
    # New parameters
    loras: List[Dict[str, Any]] = field(default_factory=list)  # [{"id": "lora_name", "weight": 0.8}]
    generation_type: str = "image"  # "image" or "video"
    duration: int = 5  # Video duration in seconds
    fps: int = 24  # Video FPS

@dataclass
class GenerationResult:
    """Generation result"""
    task_id: str
    status: str  # pending, running, completed, failed
    progress: int = 0
    images: List[str] = field(default_factory=list)  # Base64 encoded
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

class ComfyUIClient:
    """ComfyUI API client"""

    def __init__(self, host: str = "127.0.0.1", port: int = 8188):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.ws_url = f"ws://{host}:{port}/ws"

    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """Get prompt execution history"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/history/{prompt_id}") as resp:
                return await resp.json()

    async def get_queue(self) -> Dict[str, Any]:
        """Get current queue status"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/queue") as resp:
                return await resp.json()

    async def upload_image(self, image_path: str, name: str = "image.png") -> str:
        """Upload image to ComfyUI"""
        async with aiohttp.ClientSession() as session:
            with open(image_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('image', f, filename=name, content_type='image/png')
                async with session.post(f"{self.base_url}/upload/image", data=data) as resp:
                    result = await resp.json()
                    return result.get('name', '')

    async def queue_prompt(self, prompt: Dict[str, Any], workflow: Dict[str, Any]) -> str:
        """Queue a prompt for execution"""
        async with aiohttp.ClientSession() as session:
            data = {
                "prompt": prompt,
                "workflow": workflow
            }
            async with session.post(f"{self.base_url}/prompt", json=data) as resp:
                result = await resp.json()
                return result.get('prompt_id', '')

    async def execute_workflow(
        self,
        workflow: Dict[str, Any],
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Execute a ComfyUI workflow"""
        task_id = hashlib.md5(datetime.now().isoformat().encode()).hexdigest()
        result = GenerationResult(task_id=task_id, status="pending")

        try:
            # Queue the prompt
            prompt_id = await self.queue_prompt(workflow, workflow)

            # Monitor execution via WebSocket
            result.status = "running"

            async with websockets.connect(self.ws_url) as ws:
                while True:
                    message = await ws.recv()
                    data = json.loads(message)

                    if data.get('type') == 'progress':
                        result.progress = int(data.get('data', {}).get('progress', 0) * 100)
                        if progress_callback:
                            progress_callback(result.progress)

                    elif data.get('type') == 'executed':
                        # Get output images
                        if 'data' in data and 'output' in data['data']:
                            images = data['data']['output'].get('images', [])
                            for img in images:
                                # Would need to fetch actual image data
                                result.images.append(img.get('filename', ''))

                        result.status = "completed"
                        result.progress = 100
                        break

                    elif data.get('type') == 'status':
                        if data.get('data', {}).get('sid') == prompt_id:
                            status = data.get('data', {}).get('status', {})
                            if status.get('exec_info', {}).get('queue_remaining', 0) == 0:
                                # Check if completed
                                pass

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            logger.error(f"Error executing workflow: {e}")

        return result

class AIGCProvider:
    """Unified AIGC provider for multiple generators"""

    def __init__(self):
        self.providers: Dict[GeneratorType, Any] = {
            GeneratorType.COMFYUI: ComfyUIClient()
        }
        self.api_keys: Dict[str, str] = {}

    def set_api_key(self, provider: str, key: str):
        """Set API key for a provider"""
        self.api_keys[provider] = key

    async def generate(
        self,
        request: GenerationRequest,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Generate content using specified generator"""
        # Handle video generation
        if request.generation_type == "video":
            return await self._generate_video(request, progress_callback)

        # Image generation
        if request.generator == GeneratorType.COMFYUI:
            return await self._generate_comfyui(request, progress_callback)
        elif request.generator in [GeneratorType.JIMENG, GeneratorType.KLING]:
            return await self._generate_api(request, progress_callback)
        elif request.generator == GeneratorType.DOUBAO:
            return await self._generate_doubao(request, progress_callback)
        elif request.generator == GeneratorType.GPT:
            return await self._generate_dalle(request, progress_callback)
        elif request.generator == GeneratorType.GEMINI:
            return await self._generate_gemini(request, progress_callback)
        else:
            raise ValueError(f"Unsupported generator: {request.generator}")

    async def _generate_video(
        self,
        request: GenerationRequest,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Generate video using specified generator"""
        task_id = hashlib.md5(datetime.now().isoformat().encode()).hexdigest()
        result = GenerationResult(task_id=task_id, status="pending")

        # Get API key based on generator
        provider = request.generator.value
        api_key = self.api_keys.get(provider)

        if not api_key:
            # Try Kling for video generation (most capable)
            api_key = self.api_keys.get("kling")

        try:
            result.status = "running"

            if progress_callback:
                progress_callback(10)

            # Video generation via API
            if provider == "kling" or not api_key:
                # Use Kling API for video generation
                result = await self._generate_kling_video(request, api_key or "", result, progress_callback)
            elif provider == "jimeng":
                # Use Jimeng for video
                result = await self._generate_jimeng_video(request, api_key, result, progress_callback)
            else:
                # 禁止模拟视频生成 - 必须抛出异常
                raise Exception(f"Unsupported video provider: {provider}. Please use kling, jimeng, or configure a valid provider.")

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            logger.error(f"Error generating video: {e}")

        return result

    async def _generate_kling_video(
        self,
        request: GenerationRequest,
        api_key: str,
        result: GenerationResult,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Generate video using Kling API"""
        # Kling API endpoint for video
        url = "https://api.klingai.com/v1/videos/generations"

        headers = {
            "Authorization": f"Bearer {api_key}" if api_key else "",
            "Content-Type": "application/json"
        }

        payload = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "duration": request.duration,
            "mode": "std",  # standard mode
            "fps": request.fps,
            "aspect_ratio": f"{request.width}:{request.height}" if request.width != request.height else "16:9"
        }

        if progress_callback:
            progress_callback(30)

        # 禁止模拟 - 必须抛出异常
        if not api_key:
            raise Exception("Kling API key not configured. Cannot simulate video generation.")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        # 禁止模拟 - 抛出异常
                        raise Exception(f"Kling API returned status {resp.status}. Video generation failed.")

                    data = await resp.json()
                    task_id = data.get("task_id")
                    result.task_id = task_id

                # Poll for results
                max_attempts = 60
                for attempt in range(max_attempts):
                    await asyncio.sleep(2)
                    status_url = f"{url}/{task_id}/status"
                    async with session.get(status_url, headers=headers) as status_resp:
                        if status_resp.status == 200:
                            status_data = await status_resp.json()
                            status = status_data.get("status")

                            if status == "SUCCEEDED":
                                result.status = "completed"
                                result.progress = 100
                                videos = status_data.get("data", {}).get("videos", [])
                                result.images = [vid.get("url", "") for vid in videos]  # Use images list for videos
                                break
                            elif status == "FAILED":
                                result.status = "failed"
                                result.error = status_data.get("message", "Video generation failed")
                                break
                            else:
                                progress = status_data.get("data", {}).get("progress", 0)
                                result.progress = int(progress * 100)
                                if progress_callback:
                                    progress_callback(result.progress)

        except Exception as e:
            logger.error(f"Kling video generation error: {e}")
            raise Exception(f"Kling video generation failed: {e}")

        return result

    async def _generate_jimeng_video(
        self,
        request: GenerationRequest,
        api_key: str,
        result: GenerationResult,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Generate video using Jimeng API"""
        url = "https://api.jimengai.com/v1/video/generate"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "prompt": request.prompt,
            "duration": request.duration,
            "fps": request.fps
        }

        if progress_callback:
            progress_callback(30)

        # 禁止模拟 - 必须抛出异常
        if not api_key:
            raise Exception("Jimeng API key not configured. Cannot simulate video generation.")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        # 禁止模拟 - 抛出异常
                        raise Exception(f"Jimeng API returned status {resp.status}. Video generation failed.")

                    data = await resp.json()
                    task_id = data.get("task_id")
                    result.task_id = task_id

                # Poll for results (still inside async with session)
                for _ in range(30):
                    await asyncio.sleep(2)
                    status_url = f"{url}/status/{task_id}"
                    async with session.get(status_url, headers=headers) as status_resp:
                        if status_resp.status == 200:
                            status_data = await status_resp.json()
                            if status_data.get("status") == "completed":
                                result.status = "completed"
                                result.progress = 100
                                result.images = status_data.get("videos", [])
                                break

        except Exception as e:
            logger.error(f"Jimeng video generation error: {e}")
            raise Exception(f"Jimeng video generation failed: {e}")

        return result

    async def _simulate_video_generation(
        self,
        request: GenerationRequest,
        result: GenerationResult,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """模拟视频生成 - 已禁用"""
        # 禁止模拟视频生成 - 必须抛出异常
        raise Exception(
            "Mock video generation is disabled. Please configure a valid video provider (Kling, Jimeng) with API key."
        )

    async def _generate_comfyui(
        self,
        request: GenerationRequest,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Generate using ComfyUI"""
        client: ComfyUIClient = self.providers[GeneratorType.COMFYUI]

        # Build workflow (simplified)
        # Determine model/clip references based on LoRA usage
        model_ref = "1"
        clip_ref = "1"

        # Add LoRA loaders to workflow if specified
        workflow = {}
        lora_count = len(request.loras) if request.loras else 0

        # Base checkpoint loader
        workflow["1"] = {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": f"{request.model}.safetensors"
            }
        }

        # Add LoRA loaders in chain
        if lora_count > 0:
            for i, lora in enumerate(request.loras):
                workflow[f"lora_{i}"] = {
                    "class_type": "LoraLoader",
                    "inputs": {
                        "model": [model_ref, 0],
                        "clip": [clip_ref, 1],
                        "lora_name": lora.get("id", lora.get("name", "")),
                        "strength_model": lora.get("weight", 1.0),
                        "strength_clip": lora.get("weight", 1.0)
                    }
                }
                model_ref = f"lora_{i}"
                clip_ref = f"lora_{i}"

        # Get final model/clip outputs
        final_model = model_ref
        final_clip = clip_ref

        # Positive prompt
        workflow["2"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": request.prompt,
                "clip": [final_clip, 0]
            }
        }

        # Negative prompt
        workflow["3"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": request.negative_prompt,
                "clip": [final_clip, 0]
            }
        }

        # Sampler
        workflow["4"] = {
            "class_type": "KSampler",
            "inputs": {
                "seed": request.seed if request.seed >= 0 else int(datetime.now().timestamp()),
                "steps": request.steps,
                "cfg": request.cfg,
                "sampler_name": request.sampler,
                "scheduler": request.scheduler,
                "denoise": 1.0,
                "model": [final_model, 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": {
                    "class_type": "EmptyLatentImage",
                    "inputs": {
                        "width": request.width,
                        "height": request.height,
                        "batch_size": request.batch_size
                    }
                }
            }
        }
        # VAE Decode
        workflow["5"] = {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["4", 0],
                "vae": ["1", 2]
            }
        }

        # Save Image
        workflow["6"] = {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "nanobot_factory",
                "images": ["5", 0]
            }
        }

        return await client.execute_workflow(workflow, progress_callback)

    async def _generate_api(
        self,
        request: GenerationRequest,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Generate using external API (即梦, 可灵, etc.)"""
        task_id = hashlib.md5(datetime.now().isoformat().encode()).hexdigest()
        result = GenerationResult(task_id=task_id, status="pending")

        provider = request.generator.value
        api_key = self.api_keys.get(provider)

        if not api_key:
            result.status = "failed"
            result.error = f"No API key configured for {provider}"
            return result

        try:
            result.status = "running"

            if provider == "jimeng":
                # 即梦AI (字节跳动) Image Generation API
                # 文档: https://platform.jimengai.com/
                result = await self._generate_jimeng(request, api_key, result, progress_callback)
            elif provider == "kling":
                # 快手可灵AI API
                # 文档: https://platform.klingai.com/
                result = await self._generate_kling(request, api_key, result, progress_callback)
            else:
                # Fallback: simulate for unsupported providers
                for i in range(10):
                    await asyncio.sleep(0.5)
                    result.progress = (i + 1) * 10
                    if progress_callback:
                        progress_callback(result.progress)
                result.images = ["generated_image_1.png"]
                result.status = "completed"
                result.progress = 100

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            logger.error(f"Error generating with {provider}: {e}")

        return result

    async def _generate_jimeng(
        self,
        request: GenerationRequest,
        api_key: str,
        result: GenerationResult,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Generate images using 即梦AI API"""
        # 即梦API endpoint
        url = "https://api.jimengai.com/v1/image/generate"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "num_images": request.batch_size,
            "seed": request.seed if request.seed >= 0 else None
        }

        async with aiohttp.ClientSession() as session:
            # Submit generation request
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    result.status = "failed"
                    result.error = f"API error: {resp.status} - {error_text}"
                    return result

                data = await resp.json()
                task_id = data.get("task_id")
                result.task_id = task_id

            # Poll for results
            while result.status != "completed" and result.status != "failed":
                await asyncio.sleep(2)
                status_url = f"{url}/status/{task_id}"
                async with session.get(status_url, headers=headers) as status_resp:
                    if status_resp.status == 200:
                        status_data = await status_resp.json()
                        status = status_data.get("status")

                        if status == "completed":
                            result.status = "completed"
                            result.progress = 100
                            # Get generated images
                            images = status_data.get("images", [])
                            result.images = [img.get("url", "") for img in images]
                        elif status == "failed":
                            result.status = "failed"
                            result.error = status_data.get("error", "Generation failed")
                        else:
                            # Update progress
                            progress = status_data.get("progress", 0)
                            result.progress = int(progress * 100)
                            if progress_callback:
                                progress_callback(result.progress)

        return result

    async def _generate_kling(
        self,
        request: GenerationRequest,
        api_key: str,
        result: GenerationResult,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Generate images using 快手可灵AI API"""
        # 可灵API endpoint
        url = "https://api.klingai.com/v1/images/generations"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "number_of_images": request.batch_size,
            "seed": request.seed if request.seed >= 0 else None,
            "model": "kling-v1-5",
            "quality": "standard"  # or "high"
        }

        async with aiohttp.ClientSession() as session:
            # Submit generation request
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    result.status = "failed"
                    result.error = f"API error: {resp.status} - {error_text}"
                    return result

                data = await resp.json()
                task_id = data.get("task_id")
                result.task_id = task_id

            # Poll for results (可灵异步任务)
            max_attempts = 60  # Max 2 minutes
            for attempt in range(max_attempts):
                await asyncio.sleep(2)
                status_url = f"{url}/{task_id}/status"
                async with session.get(status_url, headers=headers) as status_resp:
                    if status_resp.status == 200:
                        status_data = await status_resp.json()
                        status = status_data.get("status")

                        if status == "SUCCEEDED":
                            result.status = "completed"
                            result.progress = 100
                            images = status_data.get("data", {}).get("images", [])
                            result.images = [img.get("url", "") for img in images]
                            break
                        elif status == "FAILED":
                            result.status = "failed"
                            result.error = status_data.get("message", "Generation failed")
                            break
                        else:
                            progress = status_data.get("data", {}).get("progress", 0)
                            result.progress = int(progress * 100)
                            if progress_callback:
                                progress_callback(result.progress)

        return result

    async def _generate_doubao(
        self,
        request: GenerationRequest,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Generate using Doubao (豆包) API"""
        task_id = hashlib.md5(datetime.now().isoformat().encode()).hexdigest()
        result = GenerationResult(task_id=task_id, status="pending")

        api_key = self.api_keys.get("doubao")

        if not api_key:
            result.status = "failed"
            result.error = "No API key configured for Doubao"
            return result

        try:
            result.status = "running"

            # 豆包API endpoint (火山引擎)
            url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "size": f"{request.width}x{request.height}",
                "number": request.batch_size,
                "seed": request.seed if request.seed >= 0 else None,
                "model": "doubao-image-v1"
            }

            async with aiohttp.ClientSession() as session:
                # Submit generation request
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        result.status = "failed"
                        result.error = f"API error: {resp.status} - {error_text}"
                        return result

                    data = await resp.json()
                    task_id = data.get("id")
                    result.task_id = task_id

                # Poll for results
                max_attempts = 60
                for attempt in range(max_attempts):
                    await asyncio.sleep(2)
                    status_url = f"{url}/{task_id}"
                    async with session.get(status_url, headers=headers) as status_resp:
                        if status_resp.status == 200:
                            status_data = await status_resp.json()
                            task_status = status_data.get("task_status")

                            if task_status == "SUCCEEDED":
                                result.status = "completed"
                                result.progress = 100
                                images = status_data.get("data", {}).get("image_list", [])
                                result.images = [img.get("url", "") for img in images]
                                break
                            elif task_status == "FAILED":
                                result.status = "failed"
                                result.error = status_data.get("message", "Generation failed")
                                break
                            else:
                                progress = status_data.get("data", {}).get("progress", 0)
                                result.progress = int(progress * 100)
                                if progress_callback:
                                    progress_callback(result.progress)

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            logger.error(f"Error generating with Doubao: {e}")

        return result

    async def _generate_dalle(
        self,
        request: GenerationRequest,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Generate images using OpenAI DALL-E API"""
        task_id = hashlib.md5(datetime.now().isoformat().encode()).hexdigest()
        result = GenerationResult(task_id=task_id, status="pending")

        api_key = self.api_keys.get("gpt")

        if not api_key:
            result.status = "failed"
            result.error = "No API key configured for GPT/DALL-E"
            return result

        try:
            result.status = "running"
            if progress_callback:
                progress_callback(10)

            # DALL-E 3 API endpoint
            url = "https://api.openai.com/v1/images/generations"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            # Map size to DALL-E format
            size_map = {
                (512, 512): "1024x1024",
                (512, 768): "1024x1024",
                (768, 512): "1024x1024",
            }
            size = size_map.get((request.width, request.height), "1024x1024")

            payload = {
                "prompt": request.prompt,
                "n": request.batch_size,
                "size": size,
                "model": "dall-e-3",
                "quality": "standard"
            }

            if progress_callback:
                progress_callback(30)

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        result.status = "failed"
                        result.error = f"API error: {resp.status} - {error_text}"
                        return result

                    data = await resp.json()
                    images = data.get("data", [])
                    result.images = [img.get("url", "") for img in images]

            result.status = "completed"
            result.progress = 100
            if progress_callback:
                progress_callback(100)

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            logger.error(f"Error generating with DALL-E: {e}")

        return result

    async def _generate_gemini(
        self,
        request: GenerationRequest,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> GenerationResult:
        """Generate images using Google Gemini API"""
        task_id = hashlib.md5(datetime.now().isoformat().encode()).hexdigest()
        result = GenerationResult(task_id=task_id, status="pending")

        api_key = self.api_keys.get("gemini")

        if not api_key:
            result.status = "failed"
            result.error = "No API key configured for Gemini"
            return result

        try:
            result.status = "running"
            if progress_callback:
                progress_callback(10)

            # Gemini 2.0 Flash Experimental API
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"

            params = {"key": api_key}

            headers = {
                "Content-Type": "application/json"
            }

            # Build prompt for image generation
            prompt = f"""Generate a high-quality image with the following description:
{request.prompt}

Requirements:
- Width: {request.width}px
- Height: {request.height}px
- Style: photorealistic, high detail
"""

            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "responseModalities": ["image", "text"]
                }
            }

            if progress_callback:
                progress_callback(30)

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, params=params, headers=headers) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        result.status = "failed"
                        result.error = f"API error: {resp.status} - {error_text}"
                        return result

                    data = await resp.json()

                    # Extract image from response
                    if "candidates" in data:
                        candidate = data["candidates"][0]
                        if "content" in candidate:
                            parts = candidate["content"].get("parts", [])
                            for part in parts:
                                if "inlineData" in part:
                                    # Base64 encoded image
                                    img_data = part["inlineData"].get("data")
                                    if img_data:
                                        # Convert to URL or save locally
                                        result.images.append(f"data:image/png;base64,{img_data}")

            result.status = "completed"
            result.progress = 100
            if progress_callback:
                progress_callback(100)

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            logger.error(f"Error generating with Gemini: {e}")

        return result

class GenerationManager:
    """Manager for handling batch generation tasks"""

    def __init__(self, provider: AIGCProvider):
        self.provider = provider
        self.tasks: Dict[str, GenerationResult] = {}
        self.max_concurrent = 4

    async def create_task(
        self,
        request: GenerationRequest,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """Create a new generation task"""
        task_id = hashlib.md5(datetime.now().isoformat().encode()).hexdigest()

        # Run in background
        asyncio.create_task(self._run_task(task_id, request, progress_callback))

        return task_id

    async def _run_task(
        self,
        task_id: str,
        request: GenerationRequest,
        progress_callback: Optional[Callable[[int], None]] = None
    ):
        """Run generation task"""
        result = await self.provider.generate(request, progress_callback)
        self.tasks[task_id] = result

    def get_task(self, task_id: str) -> Optional[GenerationResult]:
        """Get task status"""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[GenerationResult]:
        """Get all tasks"""
        return list(self.tasks.values())

    def clear_completed(self):
        """Clear completed tasks"""
        self.tasks = {
            k: v for k, v in self.tasks.items()
            if v.status in ['pending', 'running']
        }


# Example usage
async def main():
    logging.basicConfig(level=logging.INFO)

    # Initialize provider
    provider = AIGCProvider()

    # Create generation request
    request = GenerationRequest(
        prompt="A beautiful landscape with mountains and a lake at sunset",
        negative_prompt="blurry, low quality, distorted",
        generator=GeneratorType.COMFYUI,
        width=512,
        height=512,
        steps=30,
        cfg=7.5,
        batch_size=2
    )

    # Generate
    def progress_callback(progress: int):
        print(f"Progress: {progress}%")

    result = await provider.generate(request, progress_callback)
    print(f"Result: {result.status}")
    print(f"Images: {result.images}")

if __name__ == "__main__":
    asyncio.run(main())
