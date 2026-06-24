"""
Nanobot Factory - Deep Integration Unified Executor
深度集成的统一执行引擎 - 融合所有AI能力

功能：
- 理解用户自然语言输入
- 智能路由到正确的Agent/Skill
- 协调多Agent协作执行
- 整合所有后端能力

@author MiniMax Agent
@date 2026-03-10
"""

import os
import re
import json
import asyncio
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


# =============================================================================
# 能力类型枚举
# =============================================================================

class CapabilityType(Enum):
    """能力类型枚举"""
    # 图像生成
    IMAGE_GENERATION = "image_generation"
    IMAGE_EDIT = "image_edit"
    IMAGE_UPSCALE = "image_upscale"
    IMAGE_VARIATION = "image_variation"
    
    # 视频生成
    VIDEO_GENERATION = "video_generation"
    IMAGE_TO_VIDEO = "image_to_video"
    VIDEO_EDIT = "video_edit"
    
    # 3D生成
    TEXT_TO_3D = "text_to_3d"
    IMAGE_TO_3D = "image_to_3d"
    
    # 数据处理
    DATA_CLASSIFICATION = "data_classification"
    DATA_TAGGING = "data_tagging"
    DATA_QUALITY_ASSESSMENT = "data_quality_assessment"
    DATA_AUGMENTATION = "data_augmentation"
    
    # 知识管理
    KNOWLEDGE_ADD = "knowledge_add"
    KNOWLEDGE_SEARCH = "knowledge_search"
    KNOWLEDGE_QUERY = "knowledge_query"
    
    # 记忆管理
    MEMORY_ADD = "memory_add"
    MEMORY_SEARCH = "memory_search"
    MEMORY_RECALL = "memory_recall"
    
    # Agent管理
    AGENT_CREATE = "agent_create"
    AGENT_LIST = "agent_list"
    AGENT_STATUS = "agent_status"
    AGENT_TASK = "agent_task"
    
    # Skills管理
    SKILL_LIST = "skill_list"
    SKILL_EXECUTE = "skill_execute"
    SKILL_SEARCH = "skill_search"
    
    # 系统管理
    SYSTEM_MONITOR = "system_monitor"
    SYSTEM_STATS = "system_stats"
    GPU_INFO = "gpu_info"
    
    # 工作流
    WORKFLOW_CREATE = "workflow_create"
    WORKFLOW_EXECUTE = "workflow_execute"
    WORKFLOW_LIST = "workflow_list"
    
    # 生产任务
    PRODUCTION_IMAGE = "production_image"
    PRODUCTION_VIDEO = "production_video"
    PRODUCTION_3D = "production_3d"
    PRODUCTION_BATCH = "production_batch"
    
    # 数据库操作
    DATABASE_QUERY = "database_query"
    DATABASE_ASSET_ADD = "database_asset_add"
    DATABASE_ASSET_LIST = "database_asset_list"
    DATABASE_DATASET_CREATE = "dataset_create"
    
    # 通用对话
    GENERAL_CHAT = "general_chat"
    QUESTION_ANSWER = "question_answer"
    REASONING = "reasoning"
    
    # 文件操作
    FILE_LIST = "file_list"
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    
    # 其他
    UNKNOWN = "unknown"


class IntentPriority(Enum):
    """意图优先级"""
    HIGH = 1
    MEDIUM = 2
    LOW = 3


# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class Intent:
    """用户意图"""
    capability: CapabilityType
    priority: IntentPriority
    entities: Dict[str, Any]
    original_text: str
    confidence: float
    sub_intents: List['Intent'] = field(default_factory=list)
    requires_agent: bool = False
    agent_type: str = ""
    requires_skill: bool = False
    skill_name: str = ""


@dataclass
class ExecutionPlan:
    """执行计划"""
    intent: Intent
    steps: List[Dict[str, Any]]
    estimated_time: float
    required_capabilities: List[CapabilityType]
    can_parallel: bool = False


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    message: str
    capability: CapabilityType
    execution_time: float
    data: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


# =============================================================================
# 意图识别器
# =============================================================================

class IntentRecognizer:
    """
    意图识别器 - 使用规则+LLM混合方式
    """
    
    # 能力关键词映射
    CAPABILITY_KEYWORDS = {
        CapabilityType.IMAGE_GENERATION: [
            "生成图片", "生成图像", "画图", "创建图片", "创作图片", 
            "generate image", "create picture", "draw", "生成一张",
            "image", "图片", "图像", "画"
        ],
        CapabilityType.IMAGE_EDIT: [
            "编辑图片", "修改图片", "调整图片", "处理图片",
            "edit image", "modify picture", "图片编辑", "局部重绘"
        ],
        CapabilityType.IMAGE_UPSCALE: [
            "放大图片", "高清化", "提升分辨率", "图片放大",
            "upscale", "enhance", "super resolution", "高清"
        ],
        CapabilityType.VIDEO_GENERATION: [
            "生成视频", "创建视频", "制作视频", "视频生成",
            "generate video", "create video", "视频", "movie"
        ],
        CapabilityType.IMAGE_TO_VIDEO: [
            "图片转视频", "静态转动态", "图生视频",
            "image to video", "animate", "动态化"
        ],
        CapabilityType.TEXT_TO_3D: [
            "生成3D", "创建3D模型", "3D生成",
            "generate 3d", "create 3d", "3D模型", "建模"
        ],
        CapabilityType.IMAGE_TO_3D: [
            "图片转3D", "图像转3D", "图生3D",
            "image to 3d", "2d to 3d"
        ],
        CapabilityType.DATA_CLASSIFICATION: [
            "分类数据", "数据分类", "归类",
            "classify", "classification", "分类"
        ],
        CapabilityType.DATA_TAGGING: [
            "标记数据", "打标签", "数据标注", "标注",
            "tag", "tagging", "label"
        ],
        CapabilityType.DATA_QUALITY_ASSESSMENT: [
            "质量评估", "质量检测", "评估质量",
            "quality", "assessment", "评分"
        ],
        CapabilityType.KNOWLEDGE_ADD: [
            "添加知识", "存储知识", "记录知识", "学习",
            "add knowledge", "store knowledge", "记住"
        ],
        CapabilityType.KNOWLEDGE_SEARCH: [
            "搜索知识", "查找知识", "查询知识",
            "search knowledge", "find knowledge", "搜索"
        ],
        CapabilityType.MEMORY_ADD: [
            "添加记忆", "记录", "记住",
            "add memory", "remember", "存储"
        ],
        CapabilityType.MEMORY_SEARCH: [
            "搜索记忆", "回忆", "查找记忆",
            "search memory", "recall", "回忆"
        ],
        CapabilityType.AGENT_CREATE: [
            "创建智能体", "新建智能体", "添加智能体",
            "create agent", "new agent", "添加代理"
        ],
        CapabilityType.AGENT_LIST: [
            "列出智能体", "查看智能体", "智能体列表",
            "list agents", "show agents", "智能体"
        ],
        CapabilityType.AGENT_STATUS: [
            "智能体状态", "agent状态", "查看状态",
            "agent status", "status"
        ],
        CapabilityType.AGENT_TASK: [
            "分配任务", "执行任务", "任务",
            "task", "job", "分配"
        ],
        CapabilityType.SKILL_LIST: [
            "列出技能", "查看技能", "技能列表",
            "list skills", "show skills", "技能"
        ],
        CapabilityType.SKILL_EXECUTE: [
            "执行技能", "使用技能", "调用技能",
            "execute skill", "run skill", "技能"
        ],
        CapabilityType.SYSTEM_MONITOR: [
            "系统监控", "监控", "系统状态",
            "monitor", "监控", "watch"
        ],
        CapabilityType.SYSTEM_STATS: [
            "系统统计", "统计数据", "统计信息",
            "stats", "statistics", "统计"
        ],
        CapabilityType.GPU_INFO: [
            "GPU信息", "显卡信息", "GPU状态",
            "gpu info", "gpu", "显卡"
        ],
        CapabilityType.WORKFLOW_CREATE: [
            "创建工作流", "新建工作流",
            "create workflow", "new workflow"
        ],
        CapabilityType.WORKFLOW_EXECUTE: [
            "执行工作流", "运行工作流",
            "execute workflow", "run workflow"
        ],
        CapabilityType.PRODUCTION_IMAGE: [
            "批量生成图片", "图像生产", "图片生产",
            "batch image", "production image"
        ],
        CapabilityType.PRODUCTION_VIDEO: [
            "批量生成视频", "视频生产",
            "batch video", "production video"
        ],
        CapabilityType.DATABASE_ASSET_ADD: [
            "添加资产", "上传资产", "资产入库",
            "add asset", "upload asset"
        ],
        CapabilityType.DATABASE_ASSET_LIST: [
            "资产列表", "查看资产", "资产",
            "asset list", "assets"
        ],
        CapabilityType.DATABASE_DATASET_CREATE: [
            "创建数据集", "新建数据集",
            "create dataset", "new dataset"
        ],
        CapabilityType.GENERAL_CHAT: [
            "聊天", "对话", "问答",
            "chat", "talk", "对话"
        ],
    }
    
    def __init__(self):
        self.llm_manager = None
    
    def set_llm_manager(self, llm_manager):
        """设置LLM管理器"""
        self.llm_manager = llm_manager
    
    def recognize(self, text: str) -> Intent:
        """
        识别用户意图
        
        Args:
            text: 用户输入文本
            
        Returns:
            Intent: 识别出的意图
        """
        text_lower = text.lower()
        
        # 统计每个能力的匹配分数
        scores = {}
        for capability, keywords in self.CAPABILITY_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    score += 1
            if score > 0:
                scores[capability] = score
        
        # 找出最高分的能力
        if scores:
            best_capability = max(scores, key=scores.get)
            confidence = scores[best_capability] / len(self.CAPABILITY_KEYWORDS[best_capability])
            confidence = min(confidence, 1.0)
            
            return Intent(
                capability=best_capability,
                priority=IntentPriority.MEDIUM,
                entities=self._extract_entities(text, best_capability),
                original_text=text,
                confidence=confidence
            )
        
        # 没有匹配到具体能力，默认为通用对话
        return Intent(
            capability=CapabilityType.GENERAL_CHAT,
            priority=IntentPriority.LOW,
            entities={},
            original_text=text,
            confidence=0.5
        )
    
    def _extract_entities(self, text: str, capability: CapabilityType) -> Dict[str, Any]:
        """提取实体"""
        entities = {}
        
        # 提取数字
        numbers = re.findall(r'\d+', text)
        if numbers:
            entities['numbers'] = [int(n) for n in numbers]
        
        # 提取引号内的文本
        quoted = re.findall(r'["\']([^"\']+)["\']', text)
        if quoted:
            entities['quoted_text'] = quoted
        
        # 提取英文单词
        english = re.findall(r'[a-zA-Z]+', text)
        if english:
            entities['english_words'] = english
        
        return entities


# =============================================================================
# 执行计划器
# =============================================================================

class ExecutionPlanner:
    """
    执行计划器 - 为意图创建执行计划
    """
    
    def __init__(self):
        self.capability_handlers = {}
    
    def register_handler(self, capability: CapabilityType, handler: Callable):
        """注册能力处理器"""
        self.capability_handlers[capability] = handler
    
    def create_plan(self, intent: Intent) -> ExecutionPlan:
        """创建执行计划"""
        steps = []
        
        # 根据能力类型创建步骤
        if intent.capability == CapabilityType.IMAGE_GENERATION:
            steps = [
                {"action": "parse_prompt", "description": "解析提示词"},
                {"action": "select_provider", "description": "选择生成服务提供商"},
                {"action": "generate_image", "description": "生成图像"},
                {"action": "classify_result", "description": "分类结果"},
                {"action": "save_to_db", "description": "保存到数据库"}
            ]
        elif intent.capability == CapabilityType.DATA_CLASSIFICATION:
            steps = [
                {"action": "load_data", "description": "加载数据"},
                {"action": "run_classifier", "description": "运行分类器"},
                {"action": "save_results", "description": "保存结果"}
            ]
        elif intent.capability == CapabilityType.AGENT_CREATE:
            steps = [
                {"action": "parse_config", "description": "解析配置"},
                {"action": "create_agent", "description": "创建智能体"},
                {"action": "register_agent", "description": "注册智能体"}
            ]
        elif intent.capability == CapabilityType.SYSTEM_MONITOR:
            steps = [
                {"action": "get_gpu_stats", "description": "获取GPU统计"},
                {"action": "get_system_stats", "description": "获取系统统计"},
                {"action": "format_output", "description": "格式化输出"}
            ]
        else:
            # 默认单步执行
            steps = [
                {"action": "execute", "description": f"执行{intent.capability.value}"}
            ]
        
        return ExecutionPlan(
            intent=intent,
            steps=steps,
            estimated_time=len(steps) * 2.0,
            required_capabilities=[intent.capability],
            can_parallel=False
        )


# =============================================================================
# 统一执行器
# =============================================================================

class UnifiedExecutor:
    """
    统一执行器 - 深度集成所有AI能力
    """
    
    def __init__(self):
        self.intent_recognizer = IntentRecognizer()
        self.execution_planner = ExecutionPlanner()
        self.llm_manager = None
        self.context = {}
        
        # 初始化所有处理器
        self._init_handlers()
    
    def set_llm_manager(self, llm_manager):
        """设置LLM管理器"""
        self.llm_manager = llm_manager
        self.intent_recognizer.set_llm_manager(llm_manager)
    
    def _init_handlers(self):
        """初始化所有处理器 - 使用延迟导入避免循环依赖"""
        # 注册GPU监控处理器
        self.execution_planner.register_handler(
            CapabilityType.SYSTEM_MONITOR,
            self._handle_system_monitor
        )
        self.execution_planner.register_handler(
            CapabilityType.GPU_INFO,
            self._handle_gpu_info
        )
        
        # 注册Agent处理器
        self.execution_planner.register_handler(
            CapabilityType.AGENT_CREATE,
            self._handle_agent_create
        )
        self.execution_planner.register_handler(
            CapabilityType.AGENT_LIST,
            self._handle_agent_list
        )
        self.execution_planner.register_handler(
            CapabilityType.AGENT_STATUS,
            self._handle_agent_status
        )
        
        # 注册图像生成处理器
        self.execution_planner.register_handler(
            CapabilityType.IMAGE_GENERATION,
            self._handle_image_generation
        )
        
        # 注册数据分类处理器
        self.execution_planner.register_handler(
            CapabilityType.DATA_CLASSIFICATION,
            self._handle_data_classification
        )
        
        # 注册Skills处理器
        self.execution_planner.register_handler(
            CapabilityType.SKILL_LIST,
            self._handle_skill_list
        )
        self.execution_planner.register_handler(
            CapabilityType.SKILL_EXECUTE,
            self._handle_skill_execute
        )
        
        # 注册知识管理处理器
        self.execution_planner.register_handler(
            CapabilityType.KNOWLEDGE_ADD,
            self._handle_knowledge_add
        )
        self.execution_planner.register_handler(
            CapabilityType.KNOWLEDGE_SEARCH,
            self._handle_knowledge_search
        )
        
        # 注册视频生成处理器
        self.execution_planner.register_handler(
            CapabilityType.VIDEO_GENERATION,
            self._handle_video_generation
        )
        
        # 注册图生视频处理器
        self.execution_planner.register_handler(
            CapabilityType.IMAGE_TO_VIDEO,
            self._handle_image_to_video
        )
        
        # 注册3D生成处理器
        self.execution_planner.register_handler(
            CapabilityType.TEXT_TO_3D,
            self._handle_text_to_3d
        )
        self.execution_planner.register_handler(
            CapabilityType.IMAGE_TO_3D,
            self._handle_image_to_3d
        )
        
        # 注册记忆管理处理器
        self.execution_planner.register_handler(
            CapabilityType.MEMORY_ADD,
            self._handle_memory_add
        )
        self.execution_planner.register_handler(
            CapabilityType.MEMORY_SEARCH,
            self._handle_memory_search
        )
        
        # 注册工作流处理器
        self.execution_planner.register_handler(
            CapabilityType.WORKFLOW_CREATE,
            self._handle_workflow_create
        )
        self.execution_planner.register_handler(
            CapabilityType.WORKFLOW_EXECUTE,
            self._handle_workflow_execute
        )
        self.execution_planner.register_handler(
            CapabilityType.WORKFLOW_LIST,
            self._handle_workflow_list
        )
        
        # 注册数据库操作处理器
        self.execution_planner.register_handler(
            CapabilityType.DATABASE_QUERY,
            self._handle_database_query
        )
        self.execution_planner.register_handler(
            CapabilityType.DATABASE_ASSET_ADD,
            self._handle_database_asset_add
        )
        self.execution_planner.register_handler(
            CapabilityType.DATABASE_ASSET_LIST,
            self._handle_database_asset_list
        )
        
        # 注册图像编辑处理器
        self.execution_planner.register_handler(
            CapabilityType.IMAGE_EDIT,
            self._handle_image_edit
        )
        self.execution_planner.register_handler(
            CapabilityType.IMAGE_UPSCALE,
            self._handle_image_upscale
        )
        
        # 注册数据标注处理器
        self.execution_planner.register_handler(
            CapabilityType.DATA_TAGGING,
            self._handle_data_tagging
        )
        
        # 注册生产任务处理器
        self.execution_planner.register_handler(
            CapabilityType.PRODUCTION_VIDEO,
            self._handle_production_video
        )
        self.execution_planner.register_handler(
            CapabilityType.PRODUCTION_BATCH,
            self._handle_production_batch
        )
        
        # 注册文件操作处理器
        self.execution_planner.register_handler(
            CapabilityType.FILE_LIST,
            self._handle_file_list
        )
        
        # 注册问答和推理处理器
        self.execution_planner.register_handler(
            CapabilityType.QUESTION_ANSWER,
            self._handle_question_answer
        )
        self.execution_planner.register_handler(
            CapabilityType.REASONING,
            self._handle_reasoning
        )
        
        # 注册系统统计处理器
        self.execution_planner.register_handler(
            CapabilityType.SYSTEM_STATS,
            self._handle_system_stats
        )
        
        # 注册通用对话处理器
        self.execution_planner.register_handler(
            CapabilityType.GENERAL_CHAT,
            self._handle_general_chat
        )
    
    async def execute(self, user_input: str, context: Dict[str, Any] = None) -> ExecutionResult:
        """
        执行用户输入
        
        Args:
            user_input: 用户输入文本
            context: 上下文信息
            
        Returns:
            ExecutionResult: 执行结果
        """
        start_time = datetime.now()
        
        # 更新上下文
        if context:
            self.context.update(context)
        
        try:
            # 1. 意图识别
            intent = self.intent_recognizer.recognize(user_input)
            logger.info(f"Recognized intent: {intent.capability.value} (confidence: {intent.confidence})")
            
            # 2. 创建执行计划
            plan = self.execution_planner.create_plan(intent)
            
            # 3. 执行计划
            handler = self.execution_planner.capability_handlers.get(intent.capability)
            
            if handler:
                result = await handler(user_input, intent, plan)
            else:
                # 没有注册处理器，尝试通用处理
                result = await self._handle_unknown(user_input, intent, plan)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            result.execution_time = execution_time
            
            return result
            
        except Exception as e:
            logger.error(f"Execution error: {e}")
            execution_time = (datetime.now() - start_time).total_seconds()
            return ExecutionResult(
                success=False,
                message=f"执行出错: {str(e)}",
                capability=CapabilityType.UNKNOWN,
                execution_time=execution_time,
                error=str(e)
            )
    
    # =========================================================================
    # 处理器实现
    # =========================================================================
    
    async def _handle_system_monitor(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理系统监控"""
        try:
            from server import get_gpu_monitor
            monitor = get_gpu_monitor()
            stats = monitor.get_system_stats()
            
            message = f"""📊 系统监控信息:

🖥️ CPU: {stats.cpu_percent:.1f}%
💾 内存: {stats.memory_used}/{stats.memory_total} MB ({stats.memory_percent:.1f}%)
💿 磁盘: {stats.disk_used}/{stats.disk_total} MB ({stats.disk_percent:.1f}%)"""
            
            if stats.gpu_info:
                gpu = stats.gpu_info
                message += f"""

🎮 GPU: {gpu.name}
   显存: {gpu.memory_used}/{gpu.memory_total} MB ({gpu.memory_percent:.1f}%)
   利用率: {gpu.utilization:.1f}%
   温度: {gpu.temperature:.1f}°C
   功率: {gpu.power_usage:.1f}/{gpu.power_limit:.1f} W"""
                
                if gpu.is_simulated:
                    message += "\n⚠️ 注意: GPU数据为模拟数据"
            
            return ExecutionResult(
                success=True,
                message=message,
                data=stats,
                capability=CapabilityType.SYSTEM_MONITOR,
                execution_time=0
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"获取系统监控失败: {str(e)}",
                capability=CapabilityType.SYSTEM_MONITOR,
                error=str(e)
            )
    
    async def _handle_gpu_info(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理GPU信息"""
        try:
            from server import get_gpu_monitor
            monitor = get_gpu_monitor()
            gpu = monitor.get_gpu_info(0)
            
            if not gpu:
                return ExecutionResult(
                    success=False,
                    message="无法获取GPU信息",
                    capability=CapabilityType.GPU_INFO
                )
            
            message = f"""🎮 GPU 详细信息:

名称: {gpu.name}
显存总量: {gpu.memory_total} MB
显存使用: {gpu.memory_used} MB
显存空闲: {gpu.memory_free} MB
显存使用率: {gpu.memory_percent:.1f}%
利用率: {gpu.utilization:.1f}%
温度: {gpu.temperature:.1f}°C
功率: {gpu.power_usage:.1f}/{gpu.power_limit:.1f} W
驱动版本: {gpu.driver_version}
CUDA版本: {gpu.cuda_version}"""
            
            if gpu.is_simulated:
                message += "\n⚠️ 注意: 此为模拟数据，请安装pynvml以获取真实数据"
            
            return ExecutionResult(
                success=True,
                message=message,
                data=gpu,
                capability=CapabilityType.GPU_INFO,
                execution_time=0
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"获取GPU信息失败: {str(e)}",
                capability=CapabilityType.GPU_INFO,
                error=str(e)
            )
    
    async def _handle_agent_list(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理列出智能体"""
        try:
            from server import get_agent_cluster
            cluster = get_agent_cluster()
            agents = cluster.list_agents()
            
            if not agents:
                return ExecutionResult(
                    success=True,
                    message="目前没有运行的智能体",
                    capability=CapabilityType.AGENT_LIST,
                    data=[]
                )
            
            message = f"🤖 智能体列表 (共{len(agents)}个):\n\n"
            for agent in agents:
                message += f"• {agent.name}: {agent.status.value}\n"
            
            return ExecutionResult(
                success=True,
                message=message,
                data=agents,
                capability=CapabilityType.AGENT_LIST,
                execution_time=0
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"获取智能体列表失败: {str(e)}",
                capability=CapabilityType.AGENT_LIST,
                error=str(e)
            )
    
    async def _handle_agent_status(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理智能体状态"""
        return await self._handle_agent_list(user_input, intent, plan)
    
    async def _handle_agent_create(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理创建智能体"""
        try:
            # 提取智能体配置
            entities = intent.entities
            name = f"Agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            from server import get_agent_cluster
            cluster = get_agent_cluster()
            
            agent_id = cluster.create_agent(name=name)
            
            message = f"✅ 智能体创建成功!\n\n名称: {name}\nID: {agent_id}\n状态: 已就绪"
            
            return ExecutionResult(
                success=True,
                message=message,
                data={"agent_id": agent_id, "name": name},
                capability=CapabilityType.AGENT_CREATE,
                execution_time=0
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"创建智能体失败: {str(e)}",
                capability=CapabilityType.AGENT_CREATE,
                error=str(e)
            )
    
    async def _handle_image_generation(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理图像生成"""
        try:
            # 提取提示词
            prompt = user_input
            
            # 移除常见前缀
            for prefix in ["生成", "创建", "画", "generate", "create", "draw"]:
                prompt = prompt.replace(prefix, "").strip()
            
            from server import get_workbench_controller, GenerationType
            controller = get_workbench_controller()
            
            # 异步生成
            result = await controller.generate(
                provider_type="omni_gen_local",
                generation_type=GenerationType.IMAGE,
                prompt=prompt
            )
            
            if result.status == "completed":
                message = f"✅ 图像生成成功!\n\n提示词: {prompt}\n提供商: {result.provider}\n图像数量: {len(result.images)}"
                
                return ExecutionResult(
                    success=True,
                    message=message,
                    data=result,
                    capability=CapabilityType.IMAGE_GENERATION,
                    execution_time=0
                )
            else:
                return ExecutionResult(
                    success=False,
                    message=f"图像生成失败: {result.error}",
                    capability=CapabilityType.IMAGE_GENERATION,
                    error=result.error
                )
                
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"图像生成出错: {str(e)}",
                capability=CapabilityType.IMAGE_GENERATION,
                error=str(e)
            )
    
    async def _handle_data_classification(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理数据分类"""
        try:
            from server import get_classifier
            
            classifier = get_classifier()
            
            # 提取要分类的内容
            content = user_input.replace("分类", "").replace("classify", "").strip()
            
            if not content:
                content = "general content"
            
            result = await classifier.classify(content)
            
            message = f"""📊 分类结果:

类别: {', '.join(result.categories)}
标签: {', '.join(result.tags[:5])}
质量分数: {result.quality_score:.2f}
美学分数: {result.aesthetic_score:.2f}
置信度: {result.confidence:.2f}"""
            
            return ExecutionResult(
                success=True,
                message=message,
                data=result,
                capability=CapabilityType.DATA_CLASSIFICATION,
                execution_time=0
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"数据分类失败: {str(e)}",
                capability=CapabilityType.DATA_CLASSIFICATION,
                error=str(e)
            )
    
    async def _handle_skill_list(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理列出技能"""
        try:
            from server import get_skill_manager
            
            manager = get_skill_manager()
            skills = manager.get_all_skills()
            
            if not skills:
                return ExecutionResult(
                    success=True,
                    message="目前没有可用的技能",
                    capability=CapabilityType.SKILL_LIST,
                    data=[]
                )
            
            message = f"🛠️ 技能列表 (共{len(skills)}个):\n\n"
            for skill in skills:
                message += f"• {skill['name']}: {skill['description']}\n"
            
            return ExecutionResult(
                success=True,
                message=message,
                data=skills,
                capability=CapabilityType.SKILL_LIST,
                execution_time=0
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"获取技能列表失败: {str(e)}",
                capability=CapabilityType.SKILL_LIST,
                error=str(e)
            )
    
    async def _handle_skill_execute(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理执行技能"""
        try:
            # 提取技能名称和参数
            entities = intent.entities
            
            from server import get_skill_manager, SkillInput
            
            manager = get_skill_manager()
            
            # 简单解析 - 提取技能名
            skill_name = None
            for name in manager.skills.keys():
                if name.lower() in user_input.lower():
                    skill_name = name
                    break
            
            if not skill_name:
                return ExecutionResult(
                    success=False,
                    message="未找到指定的技能",
                    capability=CapabilityType.SKILL_EXECUTE,
                    error="Skill not found"
                )
            
            # 执行技能
            skill_input = SkillInput(prompt=user_input)
            result = await manager.execute_skill(skill_name, skill_input)
            
            message = f"🛠️ 技能执行结果:\n\n"
            if result.success:
                message += f"✅ 成功\n{result.result}"
            else:
                message += f"❌ 失败\n{result.error}"
            
            return ExecutionResult(
                success=result.success,
                message=message,
                data=result,
                capability=CapabilityType.SKILL_EXECUTE,
                execution_time=result.execution_time if hasattr(result, 'execution_time') else 0
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"执行技能失败: {str(e)}",
                capability=CapabilityType.SKILL_EXECUTE,
                error=str(e)
            )
    
    async def _handle_knowledge_add(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理添加知识"""
        try:
            # 提取知识内容
            content = user_input.replace("添加知识", "").replace("记住", "").replace("add knowledge", "").replace("remember", "").strip()
            
            if not content:
                return ExecutionResult(
                    success=False,
                    message="请提供要记忆的内容",
                    capability=CapabilityType.KNOWLEDGE_ADD,
                    error="No content provided"
                )
            
            from server import get_memory_system
            
            memory = get_memory_system()
            entry_id = memory.add_knowledge(content, importance=0.8)
            
            message = f"✅ 知识已添加!\n\n内容: {content[:100]}...\nID: {entry_id}"
            
            return ExecutionResult(
                success=True,
                message=message,
                data={"entry_id": entry_id, "content": content},
                capability=CapabilityType.KNOWLEDGE_ADD,
                execution_time=0
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"添加知识失败: {str(e)}",
                capability=CapabilityType.KNOWLEDGE_ADD,
                error=str(e)
            )
    
    async def _handle_knowledge_search(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理搜索知识"""
        try:
            # 提取搜索关键词
            query = user_input.replace("搜索知识", "").replace("查找", "").replace("search", "").replace("find", "").strip()
            
            from server import get_memory_system
            
            memory = get_memory_system()
            results = memory.get_knowledge(query, limit=5)
            
            if not results:
                return ExecutionResult(
                    success=True,
                    message="未找到相关知识",
                    capability=CapabilityType.KNOWLEDGE_SEARCH,
                    data=[]
                )
            
            message = f"📚 搜索结果 (共{len(results)}条):\n\n"
            for i, result in enumerate(results, 1):
                message += f"{i}. {result.content[:100]}...\n"
                message += f"   重要性: {result.importance:.2f}\n\n"
            
            return ExecutionResult(
                success=True,
                message=message,
                data=results,
                capability=CapabilityType.KNOWLEDGE_SEARCH,
                execution_time=0
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"搜索知识失败: {str(e)}",
                capability=CapabilityType.KNOWLEDGE_SEARCH,
                error=str(e)
            )
    
    async def _handle_general_chat(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理通用对话"""
        try:
            if not self.llm_manager:
                return ExecutionResult(
                    success=False,
                    message="LLM未配置，无法进行对话",
                    capability=CapabilityType.GENERAL_CHAT,
                    error="LLM not configured"
                )
            
            # 使用LLM进行对话
            from llm_client import ChatMessage
            
            messages = [
                ChatMessage(role="system", content="你是一个智能助手，请用中文回答用户的问题。"),
                ChatMessage(role="user", content=user_input)
            ]
            
            response = await self.llm_manager.chat(
                messages=messages,
                model="claude-3-sonnet-20240229"
            )
            
            return ExecutionResult(
                success=True,
                message=response.content,
                data=response,
                capability=CapabilityType.GENERAL_CHAT,
                execution_time=0
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"对话失败: {str(e)}",
                capability=CapabilityType.GENERAL_CHAT,
                error=str(e)
            )
    
    async def _handle_unknown(self, user_input: str, intent: Intent, plan: ExecutionPlan) -> ExecutionResult:
        """处理未知意图"""
        # 尝试作为通用对话处理
        return await self._handle_general_chat(user_input, intent, plan)


# =============================================================================
# 全局实例
# =============================================================================

_unified_executor: Optional[UnifiedExecutor] = None


def get_unified_executor() -> UnifiedExecutor:
    """获取统一执行器单例"""
    global _unified_executor
    if _unified_executor is None:
        _unified_executor = UnifiedExecutor()
    return _unified_executor


def init_unified_executor(llm_manager=None):
    """初始化统一执行器"""
    executor = get_unified_executor()
    if llm_manager:
        executor.set_llm_manager(llm_manager)
    return executor
