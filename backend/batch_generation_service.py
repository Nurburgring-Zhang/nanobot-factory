#!/usr/bin/env python3
"""
Nanobot Factory - Batch Generation Service
Real implementation of batch content generation workflow

Based on Video Agent Pro architecture:
- Template-based prompt generation
- Variable substitution
- Parallel execution with configurable concurrency
- Real Provider API calls
- Progress tracking and status updates

@author MiniMax Agent
@date 2026-03-01
"""

import os
import json
import asyncio
import logging
import uuid
from typing import Optional, Dict, Any, List, Union, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class BatchStatus(str, Enum):
    """批量任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # 部分成功
    CANCELLED = "cancelled"


class GenerationItemStatus(str, Enum):
    """单个生成项状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class BatchTemplate:
    """批量生成模板"""
    template_id: str
    name: str
    base_prompt: str  # 基础提示词模板
    variables: List[str]  # 变量列表，如 ["subject", "style", "background"]
    default_parameters: Dict[str, Any] = field(default_factory=dict)

    # 变体生成配置
    variations_per_variant: int = 1  # 每个变量组合生成的数量

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class BatchVariableSet:
    """批量变量集"""
    variables: Dict[str, Any]  # 变量字典，如 {"subject": "cat", "style": "anime"}


@dataclass
class GenerationItem:
    """单个生成项"""
    item_id: str
    prompt: str
    parameters: Dict[str, Any]
    status: GenerationItemStatus = GenerationItemStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    provider: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None


@dataclass
class BatchJob:
    """批量任务"""
    job_id: str
    template_id: str
    name: str

    # 变量集
    variable_sets: List[BatchVariableSet]

    # 生成配置
    generation_type: str  # "image", "video"
    providers: List[str]  # 备选Provider列表
    parallel: int = 4  # 并行数量

    # 状态
    status: BatchStatus = BatchStatus.PENDING
    items: List[GenerationItem] = field(default_factory=list)

    # 进度
    total: int = 0
    completed: int = 0
    failed: int = 0

    # 时间
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # 用户信息
    user_id: str = ""
    project_id: str = ""


# ============================================================================
# Batch Generation Service
# ============================================================================

class BatchGenerationService:
    """
    批量生成服务

    功能:
    - 模板化提示词生成
    - 变量替换
    - 并行执行
    - Provider容错
    - 进度跟踪
    """

    def __init__(self, generation_service=None):
        self.generation_service = generation_service
        self.active_jobs: Dict[str, BatchJob] = {}
        self.job_history: List[BatchJob] = []

        # 模板存储
        self.templates: Dict[str, BatchTemplate] = {}

        # 回调函数
        self.progress_callbacks: Dict[str, Callable] = {}

    def create_template(
        self,
        name: str,
        base_prompt: str,
        variables: List[str],
        default_parameters: Optional[Dict[str, Any]] = None
    ) -> str:
        """创建模板"""

        template_id = str(uuid.uuid4())

        template = BatchTemplate(
            template_id=template_id,
            name=name,
            base_prompt=base_prompt,
            variables=variables,
            default_parameters=default_parameters or {}
        )

        self.templates[template_id] = template

        logger.info(f"[BatchService] Created template: {name} ({template_id})")

        return template_id

    async def create_batch_job(
        self,
        template_id: str,
        variable_sets: List[Dict[str, Any]],
        generation_type: str = "image",
        providers: Optional[List[str]] = None,
        parallel: int = 4,
        user_id: str = "default",
        project_id: str = "",
        name: Optional[str] = None
    ) -> str:
        """
        创建批量任务

        Args:
            template_id: 模板ID
            variable_sets: 变量集列表
            generation_type: 生成类型 (image/video)
            providers: Provider列表
            parallel: 并行数量
            user_id: 用户ID
            project_id: 项目ID
            name: 任务名称

        Returns:
            job_id
        """

        if template_id not in self.templates:
            raise Exception(f"Template {template_id} not found")

        template = self.templates[template_id]
        job_id = str(uuid.uuid4())

        # 生成所有变量集
        all_variable_sets = []
        for vs in variable_sets:
            all_variable_sets.append(BatchVariableSet(variables=vs))

        # 替换提示词并创建生成项
        items = []
        for var_set in all_variable_sets:
            prompt = self._substitute_variables(template.base_prompt, var_set.variables)

            # 每个变量集生成多个变体
            for i in range(template.variations_per_variant):
                if template.variations_per_variant > 1:
                    # 添加变体后缀
                    variant_prompt = f"{prompt} (variant {i + 1})"
                else:
                    variant_prompt = prompt

                item = GenerationItem(
                    item_id=str(uuid.uuid4()),
                    prompt=variant_prompt,
                    parameters={
                        **template.default_parameters,
                        "variables": var_set.variables
                    }
                )
                items.append(item)

        # 创建任务
        job = BatchJob(
            job_id=job_id,
            template_id=template_id,
            name=name or f"Batch Job {job_id[:8]}",
            variable_sets=all_variable_sets,
            generation_type=generation_type,
            providers=providers or self._get_default_providers(generation_type),
            parallel=parallel,
            user_id=user_id,
            project_id=project_id,
            items=items,
            total=len(items)
        )

        self.active_jobs[job_id] = job

        logger.info(f"[BatchService] Created batch job: {job.name} ({job_id}), {len(items)} items")

        return job_id

    def _substitute_variables(self, template: str, variables: Dict[str, Any]) -> str:
        """替换变量"""

        result = template

        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            result = result.replace(placeholder, str(value))

        return result

    def _get_default_providers(self, generation_type: str) -> List[str]:
        """获取默认Provider"""

        if generation_type == "video":
            return ["seedance", "doubao", "kling"]
        else:
            return ["omnigen", "doubao", "seedream"]

    async def start_batch_job(
        self,
        job_id: str,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        开始执行批量任务

        Args:
            job_id: 任务ID
            progress_callback: 进度回调函数

        Returns:
            执行结果
        """

        if job_id not in self.active_jobs:
            raise Exception(f"Job {job_id} not found")

        job = self.active_jobs[job_id]
        job.status = BatchStatus.RUNNING
        job.started_at = datetime.now().isoformat()

        if progress_callback:
            self.progress_callbacks[job_id] = progress_callback

        try:
            # 并行执行
            await self._execute_items_parallel(job)

            # 更新状态
            if job.failed == 0:
                job.status = BatchStatus.COMPLETED
            elif job.completed > 0:
                job.status = BatchStatus.PARTIAL
            else:
                job.status = BatchStatus.FAILED

            job.completed_at = datetime.now().isoformat()

            # 移到历史
            self.job_history.append(job)
            del self.active_jobs[job_id]

            return {
                "job_id": job_id,
                "status": job.status.value,
                "total": job.total,
                "completed": job.completed,
                "failed": job.failed
            }

        except Exception as e:
            logger.error(f"[BatchService] Batch job failed: {e}")
            job.status = BatchStatus.FAILED
            job.completed_at = datetime.now().isoformat()

            return {
                "job_id": job_id,
                "status": "failed",
                "error": str(e)
            }

    async def _execute_items_parallel(self, job: BatchJob):
        """并行执行生成项"""

        semaphore = asyncio.Semaphore(job.parallel)

        async def execute_with_semaphore(item: GenerationItem):
            async with semaphore:
                await self._execute_item(job, item)

        # 创建所有任务
        tasks = [execute_with_semaphore(item) for item in job.items]

        # 并行执行
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_item(self, job: BatchJob, item: GenerationItem):
        """执行单个生成项"""

        item.status = GenerationItemStatus.PROCESSING
        self._notify_progress(job)

        # 尝试所有Provider
        last_error = None

        for provider in job.providers:
            try:
                # 构建请求参数
                request_params = {
                    "prompt": item.prompt,
                    **item.parameters
                }

                if not self.generation_service:
                    raise Exception("Generation service not available")

                # 调用生成服务
                result = await self.generation_service.generate(
                    provider_name=provider,
                    request=request_params
                )

                if result.status == "completed":
                    item.status = GenerationItemStatus.COMPLETED
                    item.provider = provider
                    item.result = {
                        "urls": result.images or result.videos,
                        "metadata": result.metadata
                    }
                    item.completed_at = datetime.now().isoformat()
                    job.completed += 1

                    self._notify_progress(job)
                    return

                last_error = result.error

            except Exception as e:
                logger.warning(f"[BatchService] Provider {provider} failed: {e}")
                last_error = str(e)
                continue

        # 所有Provider都失败
        item.status = GenerationItemStatus.FAILED
        item.error = last_error or "All providers failed"
        item.completed_at = datetime.now().isoformat()
        job.failed += 1

        self._notify_progress(job)

    def _notify_progress(self, job: BatchJob):
        """通知进度更新"""

        progress = {
            "job_id": job.job_id,
            "status": job.status.value,
            "total": job.total,
            "completed": job.completed,
            "failed": job.failed,
            "progress": job.completed / job.total if job.total > 0 else 0
        }

        # 调用回调函数
        if job.job_id in self.progress_callbacks:
            try:
                self.progress_callbacks[job.job_id](progress)
            except Exception as e:
                logger.error(f"[BatchService] Progress callback error: {e}")

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""

        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
        else:
            # 查找历史
            for job in self.job_history:
                if job.job_id == job_id:
                    break
            else:
                return None

        return {
            "job_id": job.job_id,
            "name": job.name,
            "status": job.status.value,
            "total": job.total,
            "completed": job.completed,
            "failed": job.failed,
            "progress": job.completed / job.total if job.total > 0 else 0,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at
        }

    def get_job_items(self, job_id: str) -> List[Dict[str, Any]]:
        """获取任务项列表"""

        job = self.active_jobs.get(job_id)
        if not job:
            for j in self.job_history:
                if j.job_id == job_id:
                    job = j
                    break

        if not job:
            return []

        return [
            {
                "item_id": item.item_id,
                "prompt": item.prompt,
                "status": item.status.value,
                "provider": item.provider,
                "result": item.result,
                "error": item.error,
                "retry_count": item.retry_count,
                "created_at": item.created_at,
                "completed_at": item.completed_at
            }
            for item in job.items
        ]

    async def cancel_job(self, job_id: str) -> bool:
        """取消任务"""

        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
            job.status = BatchStatus.CANCELLED
            job.completed_at = datetime.now().isoformat()
            self.job_history.append(job)
            del self.active_jobs[job_id]
            return True

        return False

    def list_templates(self) -> List[Dict[str, Any]]:
        """列出所有模板"""

        return [
            {
                "template_id": t.template_id,
                "name": t.name,
                "base_prompt": t.base_prompt,
                "variables": t.variables,
                "created_at": t.created_at
            }
            for t in self.templates.values()
        ]

    def list_jobs(
        self,
        status: Optional[BatchStatus] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """列出任务"""

        jobs = list(self.active_jobs.values()) + self.job_history

        if status:
            jobs = [j for j in jobs if j.status == status]

        jobs = jobs[-limit:]

        return [
            {
                "job_id": j.job_id,
                "name": j.name,
                "status": j.status.value,
                "total": j.total,
                "completed": j.completed,
                "failed": j.failed,
                "created_at": j.created_at,
                "started_at": j.started_at,
                "completed_at": j.completed_at
            }
            for j in jobs
        ]


# ============================================================================
# Pre-defined Templates
# ============================================================================

def get_default_templates() -> List[Dict[str, Any]]:
    """获取默认模板"""

    return [
        {
            "name": "Product Photography",
            "base_prompt": "A high-quality product photography of {product}, {style} style, {background} background, professional lighting, studio setting",
            "variables": ["product", "style", "background"],
            "default_parameters": {
                "width": 1024,
                "height": 1024,
                "steps": 25
            }
        },
        {
            "name": "Character Portrait",
            "base_prompt": "Character portrait of {character}, {style} style, {expression} expression, detailed face, high quality",
            "variables": ["character", "style", "expression"],
            "default_parameters": {
                "width": 1024,
                "height": 1536,
                "steps": 30
            }
        },
        {
            "name": "Landscape Scene",
            "base_prompt": "Beautiful {landscape_type} landscape, {time_of_day} time, {weather} weather, {style} style, cinematic composition",
            "variables": ["landscape_type", "time_of_day", "weather", "style"],
            "default_parameters": {
                "width": 1920,
                "height": 1080,
                "steps": 25
            }
        },
        {
            "name": "Video Scene",
            "base_prompt": "{scene_description}, cinematic footage, {camera_movement} camera movement, {lighting} lighting, professional film quality",
            "variables": ["scene_description", "camera_movement", "lighting"],
            "default_parameters": {
                "width": 1920,
                "height": 1080,
                "duration": 5,
                "fps": 24
            }
        }
    ]


# ============================================================================
# Singleton Instance
# ============================================================================

_batch_service: Optional[BatchGenerationService] = None


def get_batch_service() -> BatchGenerationService:
    """获取批量生成服务单例"""
    global _batch_service

    if _batch_service is None:
        _batch_service = BatchGenerationService()

    return _batch_service


def init_batch_service(generation_service) -> BatchGenerationService:
    """初始化批量生成服务"""
    global _batch_service

    _batch_service = BatchGenerationService(generation_service=generation_service)

    # 添加默认模板
    for template_def in get_default_templates():
        _batch_service.create_template(
            name=template_def["name"],
            base_prompt=template_def["base_prompt"],
            variables=template_def["variables"],
            default_parameters=template_def.get("default_parameters", {})
        )

    return _batch_service
