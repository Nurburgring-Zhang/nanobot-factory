"""
Infinite Multimodal Data Foundry — NanoBot Factory 适配器
========================================================
# STATUS: active — HTTP客户端适配器（非路由），被引擎层调用生成能力

接入NanoBot Factory的ComfyUI/生成API/批量管线作为底层能力提供方。

架构原则:
  NanoBot Factory = 能力提供方(ComfyUI/生成API/批量管线)
  IMDF = 能力编排方(Agent驱动/引擎调度/质量审计)

通过HTTP API调用NanoBot Factory，不耦合代码。

NanoBot Factory实际API分析(基于backend/server.py):
  - /health                          GET    健康检查
  - /api/generate                    POST   统一生成入口(所有生成类型)
  - /api/generate/{task_id}          GET    查询生成任务状态
  - /api/generate/{task_id}          DELETE 取消生成任务
  - /api/generate/cleanup            DELETE 清理已完成任务
  - /api/agents                      GET    获取Agent列表
  - /api/agents/{agent_id}           GET    获取Agent详情
  - /api/chat                        POST   通用聊天
  - /api/ai/chat                     POST   AI聊天
  - /api/files/upload                POST   File upload
  - /api/comfyui/env/status          GET    ComfyUI环境状态
  - /api/comfyui/models/list         GET    模型列表
  - /api/keys/status                 GET    密钥状态
  - /api/models                      GET    模型列表
  - /api/tasks                       GET    任务列表
  - /api/tasks/{task_id}             GET    任务详情
  - /ws                              WS    WebSocket
"""

import os
import json
import logging
import httpx
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

NANOBOT_HOST = os.environ.get("NANOBOT_HOST", "http://127.0.0.1")
# 确保有协议头
if NANOBOT_HOST and not NANOBOT_HOST.startswith("http://") and not NANOBOT_HOST.startswith("https://"):
    NANOBOT_HOST = f"http://{NANOBOT_HOST}"
NANOBOT_PORT = int(os.environ.get("NANOBOT_PORT", "8899"))
NANOBOT_BASE = f"{NANOBOT_HOST}:{NANOBOT_PORT}"
API_TIMEOUT = int(os.environ.get("NANOBOT_API_TIMEOUT", "120"))


@dataclass
class NanobotStatus:
    connected: bool = False
    version: str = ""
    message: str = ""


class NanobotAdapter:
    """NanoBot Factory 适配器 — 调通实际API
    
    基于对backend/server.py实际端点的分析:
      - 没有 /api/inference/generate-image (应使用 POST /api/generate)
      - 没有 /api/inference/generate-video (应使用 POST /api/generate)
      - 没有 /api/comfyui/run-workflow (应使用 POST /api/generate, generator=comfyui)
      - 没有 /api/models/latest/list (应使用 GET /api/models)
      - 没有 /api/batch/generate (可以用多次 POST /api/generate)
    """

    def __init__(self, base_url: str = NANOBOT_BASE):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            timeout=API_TIMEOUT,
            headers={"Content-Type": "application/json"},
        )

    async def check_health(self) -> NanobotStatus:
        """GET /health — 实际存在的端点"""
        try:
            resp = await self.client.get(f"{self.base_url}/health", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return NanobotStatus(
                    connected=True,
                    version=data.get("version", data.get("status", "unknown")),
                )
            return NanobotStatus(connected=False, message=f"HTTP {resp.status_code}")
        except Exception as e:
            return NanobotStatus(connected=False, message=str(e))

    async def list_models(self) -> list:
        """GET /api/models — 实际存在的端点"""
        try:
            resp = await self.client.get(f"{self.base_url}/api/models", timeout=10)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            logger.warning(f"list_models failed: {e}")
            return []

    async def generate(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        POST /api/generate — 统一生成入口(实际端点)
        
        Payload结构:
        {
            "prompt": "生成提示词",
            "negative_prompt": "",
            "generator": "comfyui | kling | seedance | runway | pika | minimax | flux | sdxl | triposr ...",
            "settings": {
                "width": 1024, "height": 1024, "steps": 25,
                "duration": 5, "fps": 24,
                "input_images": [], "source_image": "",
                "first_frame": "", "last_frame": "",
                "model": "", "loras": [], "controlnet": [],
                ...
            }
        }
        
        返回:
        {
            "task_id": "...",
            "status": "pending",
            "results": []
        }
        用 task_id 查询 GET /api/generate/{task_id} 获取结果
        """
        if "generator" not in payload:
            payload["generator"] = "comfyui"
        if "settings" not in payload:
            payload["settings"] = {}
        
        try:
            resp = await self.client.post(
                f"{self.base_url}/api/generate", json=payload
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"generate failed: HTTP {resp.status_code} - {resp.text[:500]}")
                return None
        except Exception as e:
            logger.error(f"generate failed: {e}")
            return None

    async def generate_image(self, prompt: str, model: str = "",
                              width: int = 1024, height: int = 1024,
                              negative_prompt: str = "",
                              generator: str = "comfyui") -> Optional[str]:
        """
        图片生成 — 使用 POST /api/generate (generator=comfyui or flux or sdxl)
        
        轮询任务直到完成，返回图片URL/路径
        """
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "generator": generator,
            "settings": {
                "width": width,
                "height": height,
                "steps": 25,
                "cfg_scale": 7.0,
                "model": model or "",
            }
        }
        
        try:
            task_resp = await self.generate(payload)
            if not task_resp:
                return None
            
            task_id = task_resp.get("task_id")
            if not task_id:
                # 同步返回的结果
                return (task_resp.get("results") or [None])[0]
            
            # 轮询等待结果
            import asyncio
            for i in range(60):  # 最多等60秒
                await asyncio.sleep(1)
                status_resp = await self.get_generation_status(task_id)
                if not status_resp:
                    continue
                
                status = status_resp.get("status", "")
                if status == "completed":
                    results = status_resp.get("results", [])
                    return results[0] if results else None
                elif status == "failed":
                    logger.error(f"generate_image task {task_id} failed: {status_resp.get('error', '')}")
                    return None
            
            logger.warning(f"generate_image task {task_id} timeout")
            return None
            
        except Exception as e:
            logger.error(f"generate_image failed: {e}")
            return None

    async def generate_video(self, prompt: str, model: str = "",
                              duration: int = 5, fps: int = 24,
                              generator: str = "comfyui",
                              width: int = 1024, height: int = 1024) -> Optional[str]:
        """
        视频生成 — 使用 POST /api/generate (generator=kling|seedance|comfyui...)
        
        轮询任务直到完成，返回视频URL/路径
        """
        payload = {
            "prompt": prompt,
            "generator": generator,
            "settings": {
                "width": width,
                "height": height,
                "duration": duration,
                "fps": fps,
                "model": model or "",
            }
        }
        
        try:
            task_resp = await self.generate(payload)
            if not task_resp:
                return None
            
            task_id = task_resp.get("task_id")
            if not task_id:
                return (task_resp.get("results") or [None])[0]
            
            # 轮询等待结果
            import asyncio
            for i in range(120):  # 最多等120秒
                await asyncio.sleep(1)
                status_resp = await self.get_generation_status(task_id)
                if not status_resp:
                    continue
                
                status = status_resp.get("status", "")
                if status == "completed":
                    results = status_resp.get("results", [])
                    return results[0] if results else None
                elif status == "failed":
                    logger.error(f"generate_video task {task_id} failed: {status_resp.get('error', '')}")
                    return None
            
            logger.warning(f"generate_video task {task_id} timeout")
            return None
            
        except Exception as e:
            logger.error(f"generate_video failed: {e}")
            return None

    async def get_generation_status(self, task_id: str) -> Optional[Dict]:
        """GET /api/generate/{task_id} — 查询生成任务状态(实际端点)"""
        try:
            resp = await self.client.get(
                f"{self.base_url}/api/generate/{task_id}", timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.error(f"get_generation_status failed: {e}")
            return None

    async def cancel_generation(self, task_id: str) -> bool:
        """DELETE /api/generate/{task_id} — 取消生成任务(实际端点)"""
        try:
            resp = await self.client.delete(
                f"{self.base_url}/api/generate/{task_id}", timeout=10
            )
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.error(f"cancel_generation failed: {e}")
            return False

    async def execute_comfyui(self, workflow_json: Dict[str, Any],
                                input_images: Dict[str, str] = None) -> Optional[Dict]:
        """
        ComfyUI工作流执行 — 通过 POST /api/generate (generator=comfyui) 实现
        
        实际server.py没有 /api/comfyui/run-workflow 端点
        统一走 /api/generate 入口
        """
        payload = {
            "prompt": workflow_json.get("prompt", "ComfyUI workflow"),
            "generator": "comfyui",
            "settings": {
                "workflow": workflow_json,
                "input_images": input_images or {},
                "width": workflow_json.get("width", 1024),
                "height": workflow_json.get("height", 1024),
                "steps": workflow_json.get("steps", 25),
            }
        }
        
        try:
            result = await self.generate(payload)
            if result:
                return result
            return None
        except Exception as e:
            logger.error(f"comfyui workflow failed: {e}")
            return None

    async def batch_generate(self, prompts: List[str], engine: str = "comfyui",
                              concurrency: int = 3) -> List[Dict]:
        """
        批量生成 — 并发调用多次 POST /api/generate
        
        实际server.py没有 /api/batch/generate 端点
        这里用 asyncio.gather 并发调用
        """
        import asyncio
        semaphore = asyncio.Semaphore(concurrency)
        
        async def _single(prompt: str) -> Dict:
            async with semaphore:
                payload = {
                    "prompt": prompt,
                    "generator": engine,
                    "settings": {"width": 1024, "height": 1024, "steps": 25}
                }
                result = await self.generate(payload)
                return {"prompt": prompt, "result": result}
        
        tasks = [_single(p) for p in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = []
        for r in results:
            if isinstance(r, Exception):
                output.append({"error": str(r)})
            else:
                output.append(r)
        return output

    async def chat(self, message: str, model: str = "auto") -> Dict[str, Any]:
        """调用真实AI API进行对话"""
        if not message:
            return {"success": False, "error": "消息为空"}
        
        # 模型选择
        model_map = {
            "auto": "deepseek-chat",
            "deepseek-chat": "deepseek-chat",
            "deepseek-v4-flash": "deepseek-v4-flash",
            "deepseek-v4-pro": "deepseek-v4-pro",
            "gpt-4o": "gpt-4o",
        }
        use_model = model_map.get(model, "deepseek-chat")
        
        # 调用DeepSeek API
        import os, httpx
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            # 尝试Hermes的.env
            env_path = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / ".env"
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("DEEPSEEK_API_KEY=") or line.startswith("DEEPSEEK_API_KEY="):
                            api_key = line.strip().split("=", 1)[1].strip().strip("'\"")
                            break
        
        if not api_key:
            return {"success": False, "error": "未配置API Key"}
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": use_model,
                        "messages": [{"role": "user", "content": message}],
                        "temperature": 0.7,
                        "max_tokens": 4096,
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return {"success": True, "message": content, "model": use_model}
                else:
                    return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_agents(self) -> list:
        """GET /api/agents — 实际存在的端点"""
        try:
            resp = await self.client.get(f"{self.base_url}/api/agents", timeout=10)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            logger.warning(f"list_agents failed: {e}")
            return []

    async def upload_file(self, file_path: str) -> Optional[Dict]:
        """POST /api/files/upload — 实际存在的端点"""
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                resp = await self.client.post(
                    f"{self.base_url}/api/files/upload", files=files, timeout=60
                )
                if resp.status_code == 200:
                    return resp.json()
                return None
        except Exception as e:
            logger.error(f"upload_file failed: {e}")
            return None

    async def get_system_stats(self) -> Optional[Dict]:
        """GET /api/system/stats — 实际存在的端点"""
        try:
            resp = await self.client.get(f"{self.base_url}/api/system/stats", timeout=10)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.warning(f"get_system_stats failed: {e}")
            return None

    async def close(self):
        await self.client.aclose()
