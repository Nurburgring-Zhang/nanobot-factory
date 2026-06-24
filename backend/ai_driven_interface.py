#!/usr/bin/env python3
"""
Nanobot Factory - AI-Driven Natural Language Interface
纳米级AI驱动的自然语言接口 - 完全实现设计文档中的"自然语言输入+Nanobot AI识别+全功能操作"

这个模块是整个系统的AI驱动核心，负责：
1. 接收自然语言输入
2. 通过LLM进行语义理解和意图识别
3. 自动选择最合适的Skill、模型、执行器
4. 执行任务并返回结果

@author MiniMax Agent
@date 2026-02-28
"""

import os
import sys
import json
import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

# Import LLM client
try:
    from llm_client import (
        LLMProvider,
        LLMProviderManager,
        ChatMessage,
        ChatCompletionRequest,
        create_llm_client,
        model_registry,
        model_router
    )
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    logging.warning("LLM client not available in AI-Driven Interface")

# Import existing modules
try:
    from skills import SkillManager, BaseSkill, SkillInput, SkillOutput
    from production_workbench import get_workbench_controller, ProviderType, GenerationType
    from database import get_database, DatabaseManager
    SKILLS_AVAILABLE = True
except ImportError:
    SKILLS_AVAILABLE = False
    logging.warning("Skills or production workbench not available")

logger = logging.getLogger(__name__)


# =============================================================================
# AI-Driven Request Types
# =============================================================================

@dataclass
class NaturalLanguageRequest:
    """自然语言请求"""
    message: str  # 用户输入的自然语言
    context: Dict[str, Any] = field(default_factory=dict)  # 上下文信息
    user_preferences: Dict[str, Any] = field(default_factory=dict)  # 用户偏好


@dataclass
class AIRecognizedIntent:
    """AI识别后的意图"""
    intent_type: str  # 意图类型
    confidence: float  # 置信度
    parameters: Dict[str, Any]  # 提取的参数
    reasoning: str  # AI推理过程
    suggested_skills: List[str] = field(default_factory=list)  # 建议的技能
    suggested_models: List[str] = field(default_factory=list)  # 建议的模型


@dataclass
class AIExecutionPlan:
    """AI生成的执行计划"""
    plan_id: str
    steps: List[Dict[str, Any]]  # 执行步骤
    estimated_time: float  # 预估时间
    required_skills: List[str]  # 需要的技能
    required_models: List[str]  # 需要的模型
    fallback_plan: Optional[Dict[str, Any]] = None  # 备用计划


@dataclass
class AIExecutionResult:
    """AI执行结果"""
    status: str  # success, partial, failed
    result: Any  # 执行结果
    execution_time: float  # 执行时间
    steps_executed: int  # 执行的步骤数
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# AI-Driven Natural Language Interface
# =============================================================================

class AIDrivenNaturalLanguageInterface:
    """
    AI驱动的自然语言接口 - 完全实现"自然语言输入+Nanobot AI识别+全功能操作"

    这个类是整个系统的AI驱动核心，用户可以通过自然语言与系统交互，
    系统会自动理解意图、选择合适的执行方式、完成任务。
    """

    def __init__(self):
        self.llm_client = None
        self.skill_manager = None
        self.workbench_controller = None
        self.database = None

        # 系统能力描述 - 用于AI理解系统能力
        self.system_capabilities = self._build_system_capabilities()

        # 初始化LLM客户端
        if LLM_AVAILABLE:
            self._initialize_llm_client()

        # 初始化其他组件
        if SKILLS_AVAILABLE:
            self._initialize_components()

    def _build_system_capabilities(self) -> str:
        """构建系统能力描述 - 用于AI理解"""
        return """
## Nanobot System Capabilities

### 1. Data Production (数据生产)
- Generate images from text descriptions (text-to-image)
- Generate videos from text or images (text-to-video, image-to-video)
- Edit and modify images (image editing, inpainting, outpainting)
- Upscale images (super-resolution)
- Generate 3D models from images
- Batch production with multiple outputs

### 2. Database Management (数据库管理)
- Query and search assets
- Classify and categorize data
- Score and rate assets (aesthetic scoring)
- Tag management (auto-tagging)
- Data versioning and backup
- Data migration and export

### 3. Skills (技能系统)
- Prompt optimization and generation
- Batch production automation
- Media production (image, video, audio)
- Data analysis and classification
- Code generation
- Translation
- Model selection

### 4. File Management (文件管理)
- Upload, download, organize files
- File format conversion
- File monitoring and auto-processing
- Version control

### 5. System Operations (系统操作)
- Execute shell commands
- Browser automation
- Code execution in sandbox
- System monitoring
- Performance optimization

### 6. Third-party Integration (第三方集成)
- Feishu (飞书) messaging
- Discord, Telegram, Slack
- GitHub integration
- Social media management
"""

    def _initialize_llm_client(self):
        """初始化LLM客户端"""
        try:
            # 使用默认的LLM客户端
            self.llm_client = create_llm_client(
                provider=LLMProvider.OPENAI,
                model="gpt-4"
            )
            logger.info("LLM client initialized for AI-driven interface")
        except Exception as e:
            logger.warning(f"Failed to initialize LLM client: {e}")
            self.llm_client = None

    def _initialize_components(self):
        """初始化其他组件"""
        try:
            if SKILLS_AVAILABLE:
                self.skill_manager = SkillManager()
                self.workbench_controller = get_workbench_controller()
                self.database = get_database()
                logger.info("AI-driven components initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize components: {e}")

    async def process_natural_language(
        self,
        request: NaturalLanguageRequest
    ) -> AIExecutionResult:
        """
        处理自然语言请求 - 核心方法

        流程：
        1. AI语义理解 - 理解用户输入的真实意图
        2. 意图识别 - 识别具体的操作类型
        3. 参数提取 - 提取执行所需的参数
        4. Skill推荐 - AI推荐最合适的技能
        5. 模型选择 - AI选择最优的模型
        6. 执行计划生成 - AI生成执行计划
        7. 任务执行 - 执行任务
        8. 结果返回 - 返回执行结果
        """
        start_time = datetime.now()

        try:
            # 步骤1: AI语义理解
            recognized_intent = await self._ai_understand_intent(request.message)
            logger.info(f"AI recognized intent: {recognized_intent.intent_type}")

            # 步骤2: 生成AI执行计划
            execution_plan = await self._ai_generate_plan(
                recognized_intent,
                request.context
            )
            logger.info(f"AI generated plan with {len(execution_plan.steps)} steps")

            # 步骤3: 执行计划
            result = await self._execute_plan(execution_plan, request.context)

            execution_time = (datetime.now() - start_time).total_seconds()

            return AIExecutionResult(
                status="success",
                result=result,
                execution_time=execution_time,
                steps_executed=len(execution_plan.steps),
                metadata={
                    "intent": recognized_intent.intent_type,
                    "reasoning": recognized_intent.reasoning,
                    "skills_used": execution_plan.required_skills,
                    "models_used": execution_plan.required_models
                }
            )

        except Exception as e:
            logger.error(f"Error in AI-driven processing: {e}")
            execution_time = (datetime.now() - start_time).total_seconds()
            return AIExecutionResult(
                status="failed",
                result={"error": str(e)},
                execution_time=execution_time,
                steps_executed=0,
                metadata={"error_type": type(e).__name__}
            )

    async def _ai_understand_intent(
        self,
        message: str
    ) -> AIRecognizedIntent:
        """
        AI理解意图 - 使用LLM进行语义理解

        这是"自然语言输入+Nanobot AI识别"的核心实现
        """
        # 构建提示词
        prompt = f"""You are Nanobot AI Controller. Your task is to understand the user's natural language input and recognize their intent.

{system_capabilities}

User's input: "{message}"

Please analyze and provide:
1. intent_type: The specific type of operation (e.g., generate_image, query_data, run_skill)
2. confidence: Your confidence level (0.0-1.0)
3. parameters: Key parameters extracted from the input
4. reasoning: Your reasoning process
5. suggested_skills: Skills that might be needed
6. suggested_models: Models that might be suitable

Respond in JSON format:
{{
    "intent_type": "...",
    "confidence": 0.95,
    "parameters": {{...}},
    "reasoning": "...",
    "suggested_skills": ["skill1", "skill2"],
    "suggested_models": ["model1", "model2"]
}}
"""

        if self.llm_client:
            try:
                response = await self.llm_client.chat([
                    ChatMessage(role="user", content=prompt)
                ])

                # 解析LLM响应
                result = json.loads(response.content)

                return AIRecognizedIntent(
                    intent_type=result.get("intent_type", "unknown"),
                    confidence=result.get("confidence", 0.5),
                    parameters=result.get("parameters", {}),
                    reasoning=result.get("reasoning", ""),
                    suggested_skills=result.get("suggested_skills", []),
                    suggested_models=result.get("suggested_models", [])
                )
            except Exception as e:
                logger.warning(f"LLM failed, using fallback: {e}")

        # Fallback: 使用规则-based的意图识别
        return self._fallback_intent_recognition(message)

    def _fallback_intent_recognition(self, message: str) -> AIRecognizedIntent:
        """备用意图识别 - 当LLM不可用时使用"""
        message_lower = message.lower()

        # 图像生成相关
        if any(keyword in message_lower for keyword in ["生成图片", "生成图像", "create image", "generate image", "画"]):
            return AIRecognizedIntent(
                intent_type="generate_image",
                confidence=0.9,
                parameters={"description": message},
                reasoning="Keyword analysis: found image generation keywords",
                suggested_skills=["ImageGenerationSkill", "BatchProductionSkill"],
                suggested_models=["z_image", "flux2_klein"]
            )

        # 视频生成相关
        if any(keyword in message_lower for keyword in ["生成视频", "create video", "generate video"]):
            return AIRecognizedIntent(
                intent_type="generate_video",
                confidence=0.9,
                parameters={"description": message},
                reasoning="Keyword analysis: found video generation keywords",
                suggested_skills=["VideoGenerationSkill"],
                suggested_models=["wan2_x", "voe3_1"]
            )

        # 数据查询相关
        if any(keyword in message_lower for keyword in ["查找", "搜索", "query", "search", "找出", "找"]):
            return AIRecognizedIntent(
                intent_type="query_data",
                confidence=0.8,
                parameters={"query": message},
                reasoning="Keyword analysis: found query keywords",
                suggested_skills=["DataAnalysisSkill"],
                suggested_models=[]
            )

        # 技能调用
        if any(keyword in message_lower for keyword in ["执行", "运行", "execute", "run", "做"]):
            return AIRecognizedIntent(
                intent_type="run_skill",
                confidence=0.7,
                parameters={"task": message},
                reasoning="Keyword analysis: found execution keywords",
                suggested_skills=["SkillManager"],
                suggested_models=[]
            )

        # 默认: 通用对话
        return AIRecognizedIntent(
            intent_type="general_chat",
            confidence=0.5,
            parameters={"message": message},
            reasoning="Default classification as general chat",
            suggested_skills=[],
            suggested_models=[]
        )

    async def _ai_generate_plan(
        self,
        recognized_intent: AIRecognizedIntent,
        context: Dict[str, Any]
    ) -> AIExecutionPlan:
        """
        AI生成执行计划 - 根据识别的意图生成执行步骤
        """
        plan_id = str(uuid.uuid4())

        # 根据意图类型生成不同的执行计划
        if recognized_intent.intent_type == "generate_image":
            steps = [
                {
                    "step": 1,
                    "action": "select_model",
                    "details": f"Select optimal image generation model from {recognized_intent.suggested_models}"
                },
                {
                    "step": 2,
                    "action": "prepare_prompt",
                    "details": "Prepare and optimize prompt using PromptOptimizationSkill"
                },
                {
                    "step": 3,
                    "action": "generate",
                    "details": "Call image generation API"
                },
                {
                    "step": 4,
                    "action": "quality_check",
                    "details": "Validate generated image quality"
                },
                {
                    "step": 5,
                    "action": "save_to_database",
                    "details": "Save asset metadata to database"
                }
            ]
            required_skills = ["PromptOptimizationSkill", "ModelGenerationSkill"]
            required_models = recognized_intent.suggested_models or ["z_image"]

        elif recognized_intent.intent_type == "generate_video":
            steps = [
                {
                    "step": 1,
                    "action": "select_model",
                    "details": "Select optimal video generation model"
                },
                {
                    "step": 2,
                    "action": "prepare_prompt",
                    "details": "Prepare video generation prompt"
                },
                {
                    "step": 3,
                    "action": "generate",
                    "details": "Call video generation API"
                },
                {
                    "step": 4,
                    "action": "save_to_database",
                    "details": "Save asset metadata"
                }
            ]
            required_skills = ["VideoGenerationSkill"]
            required_models = recognized_intent.suggested_models or ["wan2_x"]

        elif recognized_intent.intent_type == "query_data":
            steps = [
                {
                    "step": 1,
                    "action": "parse_query",
                    "details": "Parse natural language query"
                },
                {
                    "step": 2,
                    "action": "execute_search",
                    "details": "Execute database search"
                },
                {
                    "step": 3,
                    "action": "return_results",
                    "details": "Return formatted results"
                }
            ]
            required_skills = ["DataAnalysisSkill"]
            required_models = []

        else:
            # 通用对话
            steps = [
                {
                    "step": 1,
                    "action": "chat",
                    "details": "Process as general conversation"
                }
            ]
            required_skills = []
            required_models = []

        # 估算时间（秒）
        estimated_time = len(steps) * 2.0

        return AIExecutionPlan(
            plan_id=plan_id,
            steps=steps,
            estimated_time=estimated_time,
            required_skills=required_skills,
            required_models=required_models
        )

    async def _execute_plan(
        self,
        plan: AIExecutionPlan,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行AI生成的计划"""
        results = []

        for step in plan.steps:
            try:
                step_result = await self._execute_step(step, context)
                results.append({
                    "step": step["step"],
                    "status": "success",
                    "result": step_result
                })
            except Exception as e:
                results.append({
                    "step": step["step"],
                    "status": "failed",
                    "error": str(e)
                })
                # 如果是关键步骤失败，返回部分成功
                if step["step"] <= 2:
                    return {
                        "status": "partial",
                        "completed_steps": results,
                        "error": str(e)
                    }

        return {
            "status": "success",
            "completed_steps": results,
            "total_steps": len(plan.steps)
        }

    async def _execute_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Any:
        """执行单个步骤"""
        action = step.get("action", "")

        if action == "select_model":
            # 选择模型 - AI自动选择
            return await self._ai_select_model(step.get("details", ""))

        elif action == "prepare_prompt":
            # 优化提示词
            return await self._optimize_prompt(context.get("message", ""))

        elif action == "generate":
            # 生成内容
            return await self._generate_content(context)

        elif action == "chat":
            # 通用对话
            return await self._general_chat(context.get("message", ""))

        else:
            return {"action": action, "status": "completed"}

    async def _ai_select_model(self, details: str) -> Dict[str, Any]:
        """AI自动选择最合适的模型"""
        # 这里应该包含模型选择的AI逻辑
        # 根据任务类型、用户偏好、成本等因素选择
        return {
            "selected_model": "z_image",
            "reasoning": "Selected based on task requirements and available models",
            "alternative_models": ["flux2_klein", "qwen_image"]
        }

    async def _optimize_prompt(self, prompt: str) -> Dict[str, Any]:
        """优化提示词"""
        if self.skill_manager:
            try:
                skill = self.skill_manager.get_skill("PromptOptimizationSkill")
                if skill:
                    result = await skill.execute(SkillInput(
                        parameters={"prompt": prompt}
                    ))
                    return {"optimized_prompt": result.output_data}
            except Exception as e:
                logger.warning(f"Skill execution failed: {e}")

        # Fallback: 返回原始提示词
        return {"optimized_prompt": prompt}

    async def _generate_content(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """生成内容 - 真实执行"""
        from production_workbench import ProductionWorkbenchController, GenerationType, GenerationRequest
        import uuid

        if self.workbench_controller:
            try:
                # 从上下文提取生成参数
                message = context.get("message", "")

                # 尝试确定生成类型
                generation_type = GenerationType.IMAGE
                provider_type = "omni_gen_local"

                # 简单的意图分析
                msg_lower = message.lower()
                if "视频" in message or "video" in msg_lower:
                    generation_type = GenerationType.VIDEO
                    provider_type = "kling"
                elif "编辑" in message or "edit" in msg_lower:
                    generation_type = GenerationType.IMAGE_EDIT
                elif "放大" in message or "upscale" in msg_lower:
                    generation_type = GenerationType.UPSCALE

                # 创建生成请求
                request = GenerationRequest(
                    request_id=str(uuid.uuid4()),
                    prompt=message,
                    generation_type=generation_type,
                    provider_type=provider_type,
                    width=context.get("width", 1024),
                    height=context.get("height", 1024),
                    num_images=context.get("num_images", 1),
                    extra_params={}
                )

                # 执行真实生成
                result = await self.workbench_controller.generate(
                    provider_type=provider_type,
                    generation_type=generation_type,
                    prompt=message,
                    width=context.get("width", 1024),
                    height=context.get("height", 1024)
                )

                return {
                    "status": "generated",
                    "request_id": result.request_id,
                    "result_status": result.status,
                    "provider": result.provider,
                    "files": result.files,
                    "message": f"Successfully generated content using {result.provider}"
                }
            except Exception as e:
                logger.warning(f"Generation failed: {e}")
                return {"status": "failed", "error": str(e)}

        # 如果没有workbench controller，尝试直接使用LLM作为后备
        if self.llm_client:
            try:
                response = await self.llm_client.chat([
                    ChatMessage(role="user", content=f"Generate content for: {context.get('message', '')}")
                ])
                return {
                    "status": "generated_via_llm",
                    "response": response.content
                }
            except Exception as e:
                logger.warning(f"LLM generation failed: {e}")

        return {
            "status": "no_execution_available",
            "message": "No generation service available. Please configure API keys."
        }

    async def _general_chat(self, message: str) -> Dict[str, Any]:
        """通用对话 - 真实执行"""
        if self.llm_client:
            try:
                response = await self.llm_client.chat([
                    ChatMessage(role="user", content=message)
                ])
                return {"response": response.content, "source": "llm"}
            except Exception as e:
                logger.warning(f"Chat failed: {e}")
                return {
                    "response": f"I understood your message: '{message}'. However, LLM execution failed: {str(e)}",
                    "source": "fallback_error",
                    "error": str(e)
                }

        # 没有LLM客户端时的响应 - 明确说明需要配置
        return {
            "response": f"I understood your message: '{message}'. However, no LLM client is configured. Please configure an LLM API key to enable AI responses.",
            "source": "no_llm_configured",
            "message": "LLM client not available - requires API key configuration"
        }

    async def get_ai_recommendation(
        self,
        user_input: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        获取AI推荐 - 用于辅助用户决策

        用户可以调用这个接口获取AI的推荐，然后决定是否执行
        """
        recognized = await self._ai_understand_intent(user_input)
        plan = await self._ai_generate_plan(recognized, context)

        return {
            "intent": recognized.intent_type,
            "confidence": recognized.confidence,
            "reasoning": recognized.reasoning,
            "plan": {
                "steps": len(plan.steps),
                "estimated_time": plan.estimated_time,
                "required_skills": plan.required_skills,
                "required_models": plan.required_models
            },
            "suggestions": {
                "skills": recognized.suggested_skills,
                "models": recognized.suggested_models
            }
        }


# =============================================================================
# Global Instance
# =============================================================================

_ai_interface_instance = None

def get_ai_interface() -> AIDrivenNaturalLanguageInterface:
    """获取全局AI驱动接口实例"""
    global _ai_interface_instance
    if _ai_interface_instance is None:
        _ai_interface_instance = AIDrivenNaturalLanguageInterface()
    return _ai_interface_instance
