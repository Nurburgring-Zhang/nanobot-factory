#!/usr/bin/env python3
"""
Nanobot Factory - 生产Agent集群模块 (AI增强版)
包含5个真实可用的生产Agent

@author MiniMax Agent
@date 2026-03-01
@description 5个真实Agent集群: 提示词优化、提示词生成、批量生产、媒体生产、数据分析
               所有Agent由 Nanobot+AI 驱动，深度集成统一生成服务
"""

import os
import json
import asyncio
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod

from backend.skills import SkillManager, SkillInput, get_skill_manager
from backend.oss_manager import OSSManager, get_oss_manager

# 导入统一生成服务
try:
    from unified_generation_service import UnifiedGenerationService, get_generation_service
    GENERATION_SERVICE_AVAILABLE = True
except ImportError:
    GENERATION_SERVICE_AVAILABLE = False
    logging.warning("统一生成服务未安装")

logger = logging.getLogger(__name__)


# ============================================================================
# Agent状态枚举
# ============================================================================

class AgentType(Enum):
    """Agent类型"""
    PROMPT_OPTIMIZER = "prompt_optimizer"      # 提示词优化
    PROMPT_GENERATOR = "prompt_generator"      # 提示词生成
    BATCH_PRODUCER = "batch_producer"          # 批量生产
    MEDIA_PRODUCER = "media_producer"          # 媒体生产
    DATA_ANALYZER = "data_analyzer"            # 数据分析


class AgentTaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============================================================================
# Agent任务模型
# ============================================================================

@dataclass
class AgentTask:
    """Agent任务"""
    task_id: str
    agent_type: AgentType
    input_data: Dict[str, Any]
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    result: Any = None
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str = ""
    completed_at: str = ""
    progress: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 生产Agent基类
# ============================================================================

class BaseProductionAgent(ABC):
    """
    生产Agent基类 (AI增强版)
    所有生产Agent继承此基类
    深度集成统一生成服务，实现真正的AI驱动
    """

    def __init__(
        self,
        agent_type: AgentType,
        name: str,
        description: str,
        skill_manager: SkillManager,
        oss_manager: OSSManager = None,
        generation_service=None
    ):
        self.agent_type = agent_type
        self.name = name
        self.description = description
        self.skill_manager = skill_manager
        self.oss_manager = oss_manager or get_oss_manager()
        self.generation_service = generation_service

        # 如果没有传入，尝试获取全局的生成服务
        if not self.generation_service and GENERATION_SERVICE_AVAILABLE:
            try:
                self.generation_service = get_generation_service()
            except Exception as e:
                logger.warning(f"获取全局生成服务失败: {e}")
                pass

        self.is_running = False
        self.current_task: Optional[AgentTask] = None
        self.task_history: List[AgentTask] = []

    def set_generation_service(self, generation_service):
        """设置生成服务"""
        self.generation_service = generation_service
        logger.info(f"{self.name} 已设置生成服务")

    async def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        """
        执行任务

        Args:
            task: Agent任务

        Returns:
            执行结果
        """
        self.is_running = True
        self.current_task = task
        task.status = AgentTaskStatus.RUNNING
        task.started_at = datetime.now().isoformat()

        try:
            # 执行具体任务逻辑
            result = await self._execute(task)

            # 更新任务状态
            task.status = AgentTaskStatus.COMPLETED
            task.result = result
            task.completed_at = datetime.now().isoformat()
            task.progress = 1.0

            self.task_history.append(task)

            return {
                "success": True,
                "result": result,
                "task_id": task.task_id
            }

        except Exception as e:
            logger.error(f"Agent执行任务失败: {e}")

            task.status = AgentTaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now().isoformat()

            self.task_history.append(task)

            return {
                "success": False,
                "error": str(e),
                "task_id": task.task_id
            }

        finally:
            self.is_running = False
            self.current_task = None

    @abstractmethod
    async def _execute(self, task: AgentTask) -> Any:
        """执行具体逻辑(子类实现)"""
        pass

    def get_status(self) -> Dict[str, Any]:
        """获取Agent状态"""
        return {
            "name": self.name,
            "type": self.agent_type.value,
            "description": self.description,
            "is_running": self.is_running,
            "current_task": {
                "task_id": self.current_task.task_id,
                "progress": self.current_task.progress
            } if self.current_task else None,
            "history_count": len(self.task_history)
        }


# ============================================================================
# Agent 1: 提示词优化Agent (AI增强版)
# ============================================================================

class PromptOptimizerAgent(BaseProductionAgent):
    """
    提示词优化Agent (AI增强版)
    功能: 自动优化用户提示词，提升生成质量
    使用LLM进行智能提示词优化
    """

    def __init__(self, skill_manager: SkillManager, oss_manager: OSSManager = None, generation_service=None):
        super().__init__(
            agent_type=AgentType.PROMPT_OPTIMIZER,
            name="Prompt Optimizer Agent",
            description="专业提示词优化Agent，自动优化提示词以获得更好的生成效果（AI驱动）",
            skill_manager=skill_manager,
            oss_manager=oss_manager,
            generation_service=generation_service
        )

    async def _execute(self, task: AgentTask) -> Any:
        """执行提示词优化"""
        input_data = task.input_data

        # 获取原始提示词
        original_prompt = input_data.get("prompt", "")
        style = input_data.get("style", "realistic")
        quality = input_data.get("quality", "high")

        # 调用Skill执行优化
        skill_input = SkillInput(
            prompt=original_prompt,
            params={
                "style": style,
                "quality": quality,
                "detail_level": "detailed"
            }
        )

        skill_output = await self.skill_manager.execute_skill(
            "prompt_optimizer",
            skill_input
        )

        if not skill_output.success:
            raise Exception(skill_output.error)

        result = skill_output.result

        # 如果配置了OSS，保存优化结果
        if self.oss_manager.is_available():
            output_key = f"optimization_results/{task.task_id}.json"
            self.oss_manager.upload_data(
                json.dumps(result, ensure_ascii=False, indent=2).encode(),
                output_key,
                "application/json"
            )
            result["oss_key"] = output_key

        # 更新进度
        task.progress = 1.0

        return result


# ============================================================================
# Agent 2: 提示词生成Agent (AI增强版)
# ============================================================================

class PromptGeneratorAgent(BaseProductionAgent):
    """
    提示词生成Agent (AI增强版)
    功能: 根据主题生成多个变体提示词
    使用LLM进行智能提示词生成
    """

    def __init__(self, skill_manager: SkillManager, oss_manager: OSSManager = None, generation_service=None):
        super().__init__(
            agent_type=AgentType.PROMPT_GENERATOR,
            name="Prompt Generator Agent",
            description="创意提示词生成Agent，根据主题生成多样化的提示词（AI驱动）",
            skill_manager=skill_manager,
            oss_manager=oss_manager,
            generation_service=generation_service
        )

    async def _execute(self, task: AgentTask) -> Any:
        """执行提示词生成"""
        input_data = task.input_data

        topic = input_data.get("topic", "")
        count = input_data.get("count", 5)
        style = input_data.get("style", "realistic")
        variation = input_data.get("variation", "diverse")

        # 调用Skill执行生成
        skill_input = SkillInput(
            prompt=topic,
            params={
                "count": count,
                "style": style,
                "variation": variation
            }
        )

        skill_output = await self.skill_manager.execute_skill(
            "prompt_generator",
            skill_input
        )

        if not skill_output.success:
            raise Exception(skill_output.error)

        result = skill_output.result

        # 如果配置了OSS，保存生成结果
        if self.oss_manager.is_available():
            output_key = f"prompt_results/{task.task_id}.json"
            self.oss_manager.upload_data(
                json.dumps(result, ensure_ascii=False, indent=2).encode(),
                output_key,
                "application/json"
            )
            result["oss_key"] = output_key

        return result


# ============================================================================
# Agent 3: 批量生产Agent (AI增强版)
# ============================================================================

class BatchProducerAgent(BaseProductionAgent):
    """
    批量生产Agent (AI增强版)
    功能: 批量生成图像，支持大规模生产
    深度集成统一生成服务，支持真正的AI驱动批量生成
    """

    def __init__(self, skill_manager: SkillManager, oss_manager: OSSManager = None, generation_service=None):
        super().__init__(
            agent_type=AgentType.BATCH_PRODUCER,
            name="Batch Producer Agent",
            description="批量生产Agent，支持大规模批量生成任务（AI驱动）",
            skill_manager=skill_manager,
            oss_manager=oss_manager,
            generation_service=generation_service
        )
        self.max_parallel = 10

    async def _execute(self, task: AgentTask) -> Any:
        """执行批量生产"""
        input_data = task.input_data

        template = input_data.get("template", "")
        variables = input_data.get("variables", [])
        generator = input_data.get("generator", "comfyui")
        parallel = min(input_data.get("parallel", 3), self.max_parallel)

        total = len(variables)
        task.progress = 0.0

        # 调用Skill执行批量生产
        skill_input = SkillInput(
            prompt=template,
            params={
                "template": template,
                "variables": variables,
                "generator": generator,
                "parallel": parallel
            }
        )

        # 分批处理
        batch_results = []
        batch_size = parallel
        for i in range(0, total, batch_size):
            batch = variables[i:i+batch_size]

            skill_input.params["variables"] = batch
            skill_output = await self.skill_manager.execute_skill(
                "batch_producer",
                skill_input
            )

            if skill_output.success:
                batch_results.extend(skill_output.result.get("results", []))

            # 更新进度
            task.progress = min(1.0, (i + batch_size) / total)

        result = {
            "template": template,
            "total": total,
            "generator": generator,
            "results": batch_results
        }

        # 如果配置了OSS，保存结果到OSS
        if self.oss_manager.is_available():
            output_key = f"batch_results/{task.task_id}.json"
            self.oss_manager.upload_data(
                json.dumps(result, ensure_ascii=False, indent=2).encode(),
                output_key,
                "application/json"
            )
            result["oss_key"] = output_key

        return result


# ============================================================================
# Agent 4: 媒体生产Agent (AI增强版)
# ============================================================================

class MediaProducerAgent(BaseProductionAgent):
    """
    媒体生产Agent (AI增强版)
    功能: 图片生成、图片编辑、视频生成、画面优化
    深度集成统一生成服务，实现真正的AI驱动
    """

    def __init__(self, skill_manager: SkillManager, oss_manager: OSSManager = None, generation_service=None):
        super().__init__(
            agent_type=AgentType.MEDIA_PRODUCER,
            name="Media Producer Agent",
            description="媒体生产Agent，支持图片和视频的生成与编辑（AI驱动）",
            skill_manager=skill_manager,
            oss_manager=oss_manager,
            generation_service=generation_service
        )

    async def _execute(self, task: AgentTask) -> Any:
        """
        执行媒体生产
        优先使用统一生成服务进行真正的AI驱动生成
        """
        input_data = task.input_data

        prompt = input_data.get("prompt", "")
        media_type = input_data.get("type", "image")
        provider = input_data.get("provider", "doubao")
        source_image = input_data.get("source_image", "")
        settings = input_data.get("settings", {})

        result = None

        # 优先使用统一生成服务（真正的AI驱动）
        if self.generation_service and GENERATION_SERVICE_AVAILABLE:
            try:
                result = await self._generate_with_service(
                    prompt=prompt,
                    media_type=media_type,
                    provider=provider,
                    source_image=source_image,
                    settings=settings
                )
            except Exception as e:
                logger.warning(f"统一生成服务调用失败，回退到Skill: {e}")

        # 如果生成服务不可用，使用Skill
        if result is None:
            result = await self._generate_with_skill(
                prompt=prompt,
                media_type=media_type,
                provider=provider,
                source_image=source_image,
                settings=settings
            )

        # 如果配置了OSS，上传生成的内容
        if self.oss_manager.is_available() and result.get("output", {}).get("url"):
            output_url = result["output"]["url"]
            result["output"]["oss_path"] = output_url

        return result

    async def _generate_with_service(
        self,
        prompt: str,
        media_type: str,
        provider: str,
        source_image: str,
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        使用统一生成服务进行AI驱动生成
        """
        # 构建生成请求
        request_params = {
            "prompt": prompt,
            **settings
        }

        # 根据媒体类型选择合适的Provider
        if media_type == "image":
            # 图像生成
            if source_image:
                # 图像编辑
                request_params["source_image"] = source_image
                request_params["edit_type"] = settings.get("edit_type", "style_transfer")
                provider = "nanobanana_pro"  # 使用NanoBanana Pro进行编辑
            else:
                # 图像生成
                provider = settings.get("provider", "doubao")

        elif media_type == "video":
            # 视频生成
            provider = settings.get("provider", "seedance")
            request_params["duration"] = settings.get("duration", 5)
            request_params["fps"] = settings.get("fps", 24)

        # 调用统一生成服务
        generation_result = await self.generation_service.generate(
            provider_name=provider,
            request=request_params
        )

        # 转换结果格式
        if generation_result.status == "completed":
            output_urls = generation_result.images or generation_result.videos or []

            return {
                "success": True,
                "output": {
                    "urls": output_urls,
                    "provider": provider,
                    "media_type": media_type
                },
                "metadata": generation_result.metadata,
                "generation_method": "unified_service"
            }
        else:
            raise Exception(generation_result.error or "生成失败")

    async def _generate_with_skill(
        self,
        prompt: str,
        media_type: str,
        provider: str,
        source_image: str,
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        使用Skill进行生成（备选方案）
        """
        # 调用Skill执行媒体生产
        skill_input = SkillInput(
            prompt=prompt,
            params={
                "type": media_type,
                "provider": provider,
                "source_image": source_image,
                "settings": settings
            }
        )

        skill_output = await self.skill_manager.execute_skill(
            "media_producer",
            skill_input
        )

        if not skill_output.success:
            raise Exception(skill_output.error)

        result = skill_output.result
        result["generation_method"] = "skill"

        return result


# ============================================================================
# Agent 5: 数据分析Agent (AI增强版)
# ============================================================================

class DataAnalyzerAgent(BaseProductionAgent):
    """
    数据分析Agent (AI增强版)
    功能: 数据分类、质量评分、审美评分、批量管理
    深度集成OSS的AI服务，支持真正的AI驱动数据分析
    """

    def __init__(self, skill_manager: SkillManager, oss_manager: OSSManager = None, generation_service=None):
        super().__init__(
            agent_type=AgentType.DATA_ANALYZER,
            name="Data Analyzer Agent",
            description="数据分析Agent，支持数据分类、评分和批量管理（AI驱动）",
            skill_manager=skill_manager,
            oss_manager=oss_manager,
            generation_service=generation_service
        )

    async def _execute(self, task: AgentTask) -> Any:
        """执行数据分析"""
        input_data = task.input_data

        operation = input_data.get("operation", "analyze")
        file_type = input_data.get("file_type", "image")
        model = input_data.get("model", "default")

        # 如果是批量操作，从OSS获取文件列表
        if operation == "batch" and self.oss_manager.is_available():
            prefix = input_data.get("prefix", "")
            files = self.oss_manager.list_all_files(prefix)
            batch_files = [f.key for f in files[:100]]  # 限制100个

            input_data["batch_files"] = batch_files

        # 调用Skill执行分析
        skill_input = SkillInput(
            prompt=input_data.get("file_path", ""),
            params=input_data
        )

        skill_output = await self.skill_manager.execute_skill(
            "data_analyzer",
            skill_input
        )

        if not skill_output.success:
            raise Exception(skill_output.error)

        result = skill_output.result

        # 如果配置了OSS，保存分析结果
        if self.oss_manager.is_available():
            output_key = f"analysis_results/{task.task_id}.json"
            self.oss_manager.upload_data(
                json.dumps(result, ensure_ascii=False, indent=2).encode(),
                output_key,
                "application/json"
            )
            result["oss_key"] = output_key

        return result


# ============================================================================
# Agent集群管理器
# ============================================================================

class ProductionAgentCluster:
    """
    生产Agent集群管理器 (AI增强版)
    统一管理所有生产Agent

    深度集成:
    - 统一生成服务 (AI驱动的内容生成)
    - 数据库管理 (数据存储、查询)
    - 生产工作台 (内容生成)
    - Skills (任务执行)
    - OSS管理 (文件存储)
    """

    def __init__(self, oss_manager: OSSManager = None, generation_service=None):
        self.skill_manager = get_skill_manager()
        self.oss_manager = oss_manager or get_oss_manager()

        # 统一生成服务 (AI驱动核心)
        self.generation_service = generation_service
        if not self.generation_service and GENERATION_SERVICE_AVAILABLE:
            try:
                self.generation_service = get_generation_service()
            except Exception as e:
                logger.warning(f"获取全局生成服务失败: {e}")
                pass

        # 数据库管理器
        self.database = None

        # 生产工作台
        self.workbench = None

        # LLM管理器
        self.llm_manager = None

        # 初始化所有Agent
        self.agents: Dict[AgentType, BaseProductionAgent] = {
            AgentType.PROMPT_OPTIMIZER: PromptOptimizerAgent(
                self.skill_manager, self.oss_manager, self.generation_service
            ),
            AgentType.PROMPT_GENERATOR: PromptGeneratorAgent(
                self.skill_manager, self.oss_manager, self.generation_service
            ),
            AgentType.BATCH_PRODUCER: BatchProducerAgent(
                self.skill_manager, self.oss_manager, self.generation_service
            ),
            AgentType.MEDIA_PRODUCER: MediaProducerAgent(
                self.skill_manager, self.oss_manager, self.generation_service
            ),
            AgentType.DATA_ANALYZER: DataAnalyzerAgent(
                self.skill_manager, self.oss_manager, self.generation_service
            )
        }

        # 任务队列
        self.task_queue: List[AgentTask] = []
        self.completed_tasks: List[AgentTask] = []

        logger.info(f"已初始化 {len(self.agents)} 个生产Agent (AI增强版)")

    def set_database(self, database):
        """设置数据库管理器"""
        self.database = database
        # 传递给所有Agent
        for agent in self.agents.values():
            if hasattr(agent, 'set_database'):
                agent.set_database(database)
        logger.info("Database connected to Agent Cluster")

    def set_workbench(self, workbench):
        """设置生产工作台"""
        self.workbench = workbench
        # 传递给所有Agent
        for agent in self.agents.values():
            if hasattr(agent, 'set_workbench'):
                agent.set_workbench(workbench)
        logger.info("Workbench connected to Agent Cluster")

    def set_llm_manager(self, llm_manager):
        """设置LLM管理器"""
        self.llm_manager = llm_manager
        # 传递给所有Agent
        for agent in self.agents.values():
            if hasattr(agent, 'set_llm_manager'):
                agent.set_llm_manager(llm_manager)
        logger.info("LLM Manager connected to Agent Cluster")

    def set_skill_manager(self, skill_manager):
        """设置Skill管理器"""
        self.skill_manager = skill_manager
        # 传递给所有Agent
        for agent in self.agents.values():
            if hasattr(agent, 'set_skill_manager'):
                agent.set_skill_manager(skill_manager)
        logger.info("Skill Manager connected to Agent Cluster")

    def set_generation_service(self, generation_service):
        """设置统一生成服务 (AI驱动核心)"""
        self.generation_service = generation_service
        # 传递给所有Agent
        for agent in self.agents.values():
            if hasattr(agent, 'set_generation_service'):
                agent.set_generation_service(generation_service)
        logger.info("Generation Service connected to Agent Cluster (AI驱动核心)")

    def get_agent(self, agent_type: AgentType) -> Optional[BaseProductionAgent]:
        """获取Agent"""
        return self.agents.get(agent_type)

    def get_all_agents_status(self) -> List[Dict[str, Any]]:
        """获取所有Agent状态"""
        return [
            agent.get_status()
            for agent in self.agents.values()
        ]

    async def submit_task(
        self,
        agent_type: AgentType,
        input_data: Dict[str, Any]
    ) -> str:
        """
        提交任务

        Args:
            agent_type: Agent类型
            input_data: 输入数据

        Returns:
            任务ID
        """
        # 获取Agent
        agent = self.get_agent(agent_type)
        if not agent:
            raise ValueError(f"未知的Agent类型: {agent_type}")

        # 创建任务
        task_id = f"{agent_type.value}_{int(time.time() * 1000)}"
        task = AgentTask(
            task_id=task_id,
            agent_type=agent_type,
            input_data=input_data
        )

        # 添加到队列
        self.task_queue.append(task)

        # 执行任务
        asyncio.create_task(self._process_task(agent, task))

        return task_id

    async def _process_task(self, agent: BaseProductionAgent, task: AgentTask):
        """处理任务"""
        result = await agent.execute_task(task)

        # 移动到已完成
        if task in self.task_queue:
            self.task_queue.remove(task)
        self.completed_tasks.append(task)

        # 保持历史记录不超过1000条
        if len(self.completed_tasks) > 1000:
            self.completed_tasks = self.completed_tasks[-1000:]

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        # 检查队列中的任务
        for task in self.task_queue:
            if task.task_id == task_id:
                return {
                    "task_id": task.task_id,
                    "agent_type": task.agent_type.value,
                    "status": task.status.value,
                    "progress": task.progress,
                    "created_at": task.created_at
                }

        # 检查已完成的任务
        for task in self.completed_tasks:
            if task.task_id == task_id:
                return {
                    "task_id": task.task_id,
                    "agent_type": task.agent_type.value,
                    "status": task.status.value,
                    "result": task.result,
                    "error": task.error,
                    "created_at": task.created_at,
                    "completed_at": task.completed_at
                }

        return None

    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        return {
            "pending_tasks": len(self.task_queue),
            "completed_tasks": len(self.completed_tasks),
            "agents": self.get_all_agents_status()
        }


# ============================================================================
# 单例实例
# ============================================================================

_production_cluster: Optional[ProductionAgentCluster] = None


def get_production_cluster() -> ProductionAgentCluster:
    """获取生产Agent集群单例"""
    global _production_cluster
    if _production_cluster is None:
        _production_cluster = ProductionAgentCluster()
    return _production_cluster


def init_production_cluster(
    oss_manager: OSSManager = None,
    generation_service=None
) -> ProductionAgentCluster:
    """
    初始化生产Agent集群 (AI增强版)

    Args:
        oss_manager: OSS管理器
        generation_service: 统一生成服务

    Returns:
        ProductionAgentCluster实例
    """
    global _production_cluster
    _production_cluster = ProductionAgentCluster(
        oss_manager=oss_manager,
        generation_service=generation_service
    )
    logger.info("生产Agent集群(AI增强版)初始化完成")
    return _production_cluster
