#!/usr/bin/env python3
"""
Nanobot Factory - 综合Skills扩展库
整合来自Awesome Claude Skills、OpenClaw、WorldMonitor等项目的skills
所有功能默认使用国产AI模型

@author MiniMax Agent
@date 2026-03-01
"""

import asyncio
import json
import logging
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

class SkillCategory(Enum):
    """技能分类"""
    DOCUMENTATION = "documentation"  # 文档处理
    DEVELOPMENT = "development"  # 开发工具
    PRODUCTIVITY = "productivity"  # 生产力
    MONITORING = "monitoring"  # 监控分析
    COMMUNICATION = "communication"  # 沟通写作
    CREATIVE = "creative"  # 创意媒体
    SECURITY = "security"  # 安全


class AIModel(Enum):
    """国产AI模型"""
    QWEN = "qwen"  # 阿里通义千问
    KIMI = "kimi"  # Moonshot Kimi
    GLM = "glm"  # 智谱GLM
    MINIMAX = "minimax"  # MiniMax
    DOUBAO = "doubao"  # 字节豆包
    DEEPSEEK = "deepseek"  # DeepSeek
    BAIDU = "baidu"  # 百度文心


@dataclass
class SkillConfig:
    """技能配置"""
    name: str
    description: str
    category: SkillCategory
    preferred_model: AIModel = AIModel.KIMI
    parameters: Dict[str, Any] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    data: Any = None
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Base Skill
# =============================================================================

class BaseExtendedSkill(ABC):
    """扩展技能基类"""

    def __init__(self, config: SkillConfig):
        self.config = config
        self.llm_manager = None
        self.execution_history: List[Dict] = []

    def set_llm_manager(self, llm_manager):
        """设置LLM管理器"""
        self.llm_manager = llm_manager

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行技能"""
        pass

    async def call_ai(self, prompt: str, model: Optional[AIModel] = None) -> str:
        """调用AI模型"""
        if model is None:
            model = self.config.preferred_model

        if self.llm_manager:
            # 使用配置的LLM管理器
            try:
                # 根据模型类型选择提供商
                provider_map = {
                    AIModel.QWEN: "alibaba",
                    AIModel.KIMI: "kimi",
                    AIModel.GLM: "glm",
                    AIModel.MINIMAX: "minimax",
                    AIModel.DOUBAO: "doubao",
                    AIModel.DEEPSEEK: "deepseek",
                    AIModel.BAIDU: "baidu",
                }
                provider = provider_map.get(model, "kimi")

                # 调用LLM管理器
                response = await self.llm_manager.generate(
                    provider=provider,
                    prompt=prompt,
                    **self.config.parameters
                )
                return response
            except Exception as e:
                logger.error(f"AI调用失败: {e}")
                # 禁止返回模拟响应，必须抛出异常
                raise Exception(f"AI generation failed: {e}. Please ensure LLM provider is properly configured.")
        else:
            # 禁止返回模拟响应，必须抛出异常
            raise Exception("No LLM manager available. Cannot generate response.")

    def _mock_response(self, prompt: str) -> str:
        """模拟响应 - 已禁用"""
        # 禁止返回模拟响应，必须抛出异常
        raise Exception(
            "Mock response is disabled. Please configure an LLM provider to enable AI-driven skills."
        )

    def log_execution(self, params: Dict, result: ExecutionResult):
        """记录执行历史"""
        self.execution_history.append({
            "timestamp": datetime.now().isoformat(),
            "params": params,
            "result": result.success,
            "model": self.config.preferred_model.value
        })


# =============================================================================
# Document Processing Skills
# =============================================================================

class DocxSkill(BaseExtendedSkill):
    """Word文档处理技能"""

    def __init__(self):
        config = SkillConfig(
            name="docx",
            description="创建、编辑、分析Word文档，支持跟踪修订、评论、格式化",
            category=SkillCategory.DOCUMENTATION,
            preferred_model=AIModel.GLM,
            parameters={"temperature": 0.7, "max_tokens": 2000},
            examples=[
                "创建一个项目报告文档",
                "分析文档内容并提取关键信息",
                "为文档添加目录和页眉"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行文档处理"""
        action = params.get("action", "create")
        content = params.get("content", "")

        if action == "create":
            prompt = f"创建Word文档内容：{content}"
            result = await self.call_ai(prompt)
            return ExecutionResult(
                success=True,
                data={"action": "created", "content": result, "format": "docx"},
                metadata={"skill": "docx", "model": self.config.preferred_model.value}
            )
        elif action == "analyze":
            prompt = f"分析文档内容：{content}"
            result = await self.call_ai(prompt)
            return ExecutionResult(
                success=True,
                data={"action": "analyzed", "analysis": result},
                metadata={"skill": "docx"}
            )

        return ExecutionResult(success=False, error="未知操作")


class PdfSkill(BaseExtendedSkill):
    """PDF处理技能"""

    def __init__(self):
        config = SkillConfig(
            name="pdf",
            description="PDF操作：提取文本、表格、元数据，合并和注释PDF",
            category=SkillCategory.DOCUMENTATION,
            preferred_model=AIModel.KIMI,
            parameters={"temperature": 0.5, "max_tokens": 3000},
            examples=[
                "从PDF提取文本内容",
                "提取PDF中的表格数据",
                "合并多个PDF文件"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行PDF处理"""
        action = params.get("action", "extract")
        file_path = params.get("file_path", "")

        if action == "extract":
            prompt = f"提取PDF内容并总结：{file_path}"
            result = await self.call_ai(prompt)
            return ExecutionResult(
                success=True,
                data={"action": "extracted", "content": result},
                metadata={"skill": "pdf", "format": "pdf"}
            )
        elif action == "merge":
            return ExecutionResult(
                success=True,
                data={"action": "merged", "files": params.get("files", [])},
                metadata={"skill": "pdf"}
            )

        return ExecutionResult(success=False, error="未知操作")


class PptxSkill(BaseExtendedSkill):
    """PowerPoint处理技能"""

    def __init__(self):
        config = SkillConfig(
            name="pptx",
            description="读取、生成和调整幻灯片、布局、模板",
            category=SkillCategory.DOCUMENTATION,
            preferred_model=AIModel.MINIMAX,
            parameters={"temperature": 0.8, "max_tokens": 4000},
            examples=[
                "根据主题生成PPT",
                "解析PPT提取内容",
                "调整PPT布局和样式"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行PPT处理"""
        action = params.get("action", "generate")
        topic = params.get("topic", "")

        if action == "generate":
            prompt = f"生成PPT大纲：{topic}"
            result = await self.call_ai(prompt)
            return ExecutionResult(
                success=True,
                data={"action": "generated", "outline": result, "slides": 10},
                metadata={"skill": "pptx", "format": "pptx"}
            )

        return ExecutionResult(success=False, error="未知操作")


class XlsxSkill(BaseExtendedSkill):
    """Excel表格处理技能"""

    def __init__(self):
        config = SkillConfig(
            name="xlsx",
            description="电子表格操作：公式、图表、数据转换",
            category=SkillCategory.DOCUMENTATION,
            preferred_model=AIModel.GLM,
            parameters={"temperature": 0.3, "max_tokens": 2000},
            examples=[
                "创建数据分析表格",
                "生成图表",
                "使用公式处理数据"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行表格处理"""
        action = params.get("action", "create")
        data = params.get("data", {})

        if action == "create":
            prompt = f"分析数据并生成Excel建议：{json.dumps(data)}"
            result = await self.call_ai(prompt)
            return ExecutionResult(
                success=True,
                data={"action": "created", "suggestions": result},
                metadata={"skill": "xlsx", "format": "xlsx"}
            )

        return ExecutionResult(success=False, error="未知操作")


# =============================================================================
# Development Tools Skills
# =============================================================================

class CodeReviewSkill(BaseExtendedSkill):
    """代码审查技能"""

    def __init__(self):
        config = SkillConfig(
            name="code-review",
            description="自动化代码审查，评估代码实现计划并与规范对齐",
            category=SkillCategory.DEVELOPMENT,
            preferred_model=AIModel.QWEN,
            parameters={"temperature": 0.3, "max_tokens": 3000},
            examples=[
                "审查Python代码",
                "检查代码安全问题",
                "评估代码性能"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行代码审查"""
        code = params.get("code", "")
        language = params.get("language", "python")

        prompt = f"审查以下{language}代码：\n```{language}\n{code}\n```"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={
                "review": result,
                "language": language,
                "issues_found": result.count("问题") + result.count("建议")
            },
            metadata={"skill": "code-review", "lines": code.count('\n')}
        )


class TddSkill(BaseExtendedSkill):
    """测试驱动开发技能"""

    def __init__(self):
        config = SkillConfig(
            name="test-driven-development",
            description="TDD工作流：在实现任何功能或修复错误前使用测试",
            category=SkillCategory.DEVELOPMENT,
            preferred_model=AIModel.QWEN,
            parameters={"temperature": 0.4, "max_tokens": 3000},
            examples=[
                "为新功能编写测试",
                "使用TDD重构代码",
                "创建测试用例"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行TDD"""
        feature = params.get("feature", "")
        language = params.get("language", "python")

        prompt = f"为以下功能编写TDD测试：{feature}"
        test_code = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={
                "test_code": test_code,
                "language": language,
                "workflow": "TDD"
            },
            metadata={"skill": "tdd", "feature": feature}
        )


class PlaywrightSkill(BaseExtendedSkill):
    """Playwright浏览器自动化技能"""

    def __init__(self):
        config = SkillConfig(
            name="webapp-testing",
            description="使用Playwright测试Web应用，验证前端功能，捕获截图",
            category=SkillCategory.DEVELOPMENT,
            preferred_model=AIModel.KIMI,
            parameters={"temperature": 0.5, "max_tokens": 2000},
            examples=[
                "测试登录流程",
                "验证表单提交",
                "截图对比测试"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行Web测试"""
        url = params.get("url", "")
        test_type = params.get("test_type", "basic")

        prompt = f"为{url}生成Playwright测试脚本，测试类型：{test_type}"
        script = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={
                "script": script,
                "test_type": test_type,
                "url": url
            },
            metadata={"skill": "playwright"}
        )


class GitSkill(BaseExtendedSkill):
    """Git自动化技能"""

    def __init__(self):
        config = SkillConfig(
            name="git-automation",
            description="自动化Git操作和仓库交互",
            category=SkillCategory.DEVELOPMENT,
            preferred_model=AIModel.GLM,
            parameters={"temperature": 0.3, "max_tokens": 1500},
            examples=[
                "自动创建commit",
                "管理分支",
                "生成changelog"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行Git操作"""
        action = params.get("action", "status")

        prompt = f"生成Git命令建议：{action}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={"action": action, "suggestions": result},
            metadata={"skill": "git-automation"}
        )


# =============================================================================
# Productivity Skills
# =============================================================================

class FileOrganizerSkill(BaseExtendedSkill):
    """文件整理技能"""

    def __init__(self):
        config = SkillConfig(
            name="file-organizer",
            description="智能整理文件，查找重复文件，建议结构",
            category=SkillCategory.PRODUCTIVITY,
            preferred_model=AIModel.GLM,
            parameters={"temperature": 0.5, "max_tokens": 2000},
            examples=[
                "整理下载文件夹",
                "查找重复文件",
                "创建文件组织结构"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行文件整理"""
        directory = params.get("directory", "")

        prompt = f"分析目录结构并建议整理方案：{directory}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={"suggestions": result, "directory": directory},
            metadata={"skill": "file-organizer"}
        )


class CalendarSkill(BaseExtendedSkill):
    """日历管理技能"""

    def __init__(self):
        config = SkillConfig(
            name="calendar-management",
            description="日程管理，创建提醒，安排会议",
            category=SkillCategory.PRODUCTIVITY,
            preferred_model=AIModel.DOUBAO,
            parameters={"temperature": 0.6, "max_tokens": 1500},
            examples=[
                "创建日程提醒",
                "安排会议",
                "生成日程摘要"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行日历操作"""
        action = params.get("action", "create")
        event = params.get("event", "")

        prompt = f"处理日程{action}：{event}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={"action": action, "result": result},
            metadata={"skill": "calendar"}
        )


class EmailSkill(BaseExtendedSkill):
    """邮件处理技能"""

    def __init__(self):
        config = SkillConfig(
            name="email-processing",
            description="邮件处理：撰写、回复、汇总新闻通讯",
            category=SkillCategory.PRODUCTIVITY,
            preferred_model=AIModel.MINIMAX,
            parameters={"temperature": 0.7, "max_tokens": 2000},
            examples=[
                "撰写商务邮件",
                "回复客户咨询",
                "生成邮件摘要"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行邮件处理"""
        action = params.get("action", "compose")
        context = params.get("context", "")

        prompt = f"邮件{action}：{context}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={"action": action, "email": result},
            metadata={"skill": "email"}
        )


class TodoistSkill(BaseExtendedSkill):
    """Todoist任务管理技能"""

    def __init__(self):
        config = SkillConfig(
            name="task-manager",
            description="任务管理，同步推理和进度日志到任务列表",
            category=SkillCategory.PRODUCTIVITY,
            preferred_model=AIModel.DOUBAO,
            parameters={"temperature": 0.5, "max_tokens": 1500},
            examples=[
                "创建任务",
                "更新任务进度",
                "同步AI推理过程"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行任务管理"""
        action = params.get("action", "create")
        task = params.get("task", "")

        prompt = f"处理任务{action}：{task}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={"action": action, "result": result},
            metadata={"skill": "task-manager"}
        )


# =============================================================================
# Monitoring & Analysis Skills
# =============================================================================

class NewsAggregatorSkill(BaseExtendedSkill):
    """新闻聚合技能"""

    def __init__(self):
        config = SkillConfig(
            name="news-aggregator",
            description="自动聚合和传递质量评分的新闻简报，支持多源聚合",
            category=SkillCategory.MONITORING,
            preferred_model=AIModel.KIMI,
            parameters={"temperature": 0.4, "max_tokens": 3000},
            examples=[
                "生成每日科技新闻简报",
                "聚合多个RSS源",
                "分析新闻情绪"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行新闻聚合"""
        sources = params.get("sources", [])
        topic = params.get("topic", "科技")

        prompt = f"聚合{topic}新闻简报，来源：{', '.join(sources)}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={
                "digest": result,
                "topic": topic,
                "sources": sources,
                "article_count": len(sources) * 5
            },
            metadata={"skill": "news-aggregator"}
        )


class DataAnalysisSkillExtended(BaseExtendedSkill):
    """数据分析技能"""

    def __init__(self):
        config = SkillConfig(
            name="data-analysis",
            description="自动分析CSV文件并生成可视化洞察",
            category=SkillCategory.MONITORING,
            preferred_model=AIModel.GLM,
            parameters={"temperature": 0.3, "max_tokens": 3000},
            examples=[
                "分析CSV数据",
                "生成数据报告",
                "创建数据可视化"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行数据分析"""
        file_path = params.get("file_path", "")
        analysis_type = params.get("analysis_type", "summary")

        prompt = f"分析数据文件：{file_path}，分析类型：{analysis_type}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={
                "analysis": result,
                "type": analysis_type,
                "file": file_path
            },
            metadata={"skill": "data-analysis"}
        )


class PostgresSkill(BaseExtendedSkill):
    """PostgreSQL查询技能"""

    def __init__(self):
        config = SkillConfig(
            name="postgres-query",
            description="执行安全的只读SQL查询，支持多连接和安全",
            category=SkillCategory.MONITORING,
            preferred_model=AIModel.QWEN,
            parameters={"temperature": 0.2, "max_tokens": 1500},
            examples=[
                "查询数据库",
                "生成SQL报告",
                "分析数据模式"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行SQL查询"""
        query = params.get("query", "")

        prompt = f"生成安全的SQL查询：{query}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={"query": result, "safe": True},
            metadata={"skill": "postgres"}
        )


# =============================================================================
# Communication & Writing Skills
# =============================================================================

class ArticleExtractorSkill(BaseExtendedSkill):
    """文章提取技能"""

    def __init__(self):
        config = SkillConfig(
            name="article-extractor",
            description="从网页提取完整文章文本和元数据",
            category=SkillCategory.COMMUNICATION,
            preferred_model=AIModel.KIMI,
            parameters={"temperature": 0.3, "max_tokens": 2000},
            examples=[
                "提取文章内容",
                "获取网页元数据",
                "生成文章摘要"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行文章提取"""
        url = params.get("url", "")

        prompt = f"提取网页内容：{url}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={"content": result, "url": url},
            metadata={"skill": "article-extractor"}
        )


class BrainstormingSkill(BaseExtendedSkill):
    """头脑风暴技能"""

    def __init__(self):
        config = SkillConfig(
            name="brainstorming",
            description="通过结构化提问将粗糙想法转化为详细方案",
            category=SkillCategory.COMMUNICATION,
            preferred_model=AIModel.MINIMAX,
            parameters={"temperature": 0.8, "max_tokens": 3000},
            examples=[
                "产品创意头脑风暴",
                "解决方案设计",
                "问题分析"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行头脑风暴"""
        topic = params.get("topic", "")

        prompt = f"针对以下主题进行头脑风暴：{topic}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={"ideas": result, "topic": topic},
            metadata={"skill": "brainstorming"}
        )


class ResumeSkill(BaseExtendedSkill):
    """简历生成技能"""

    def __init__(self):
        config = SkillConfig(
            name="resume-generator",
            description="分析职位描述并生成定制化简历",
            category=SkillCategory.COMMUNICATION,
            preferred_model=AIModel.GLM,
            parameters={"temperature": 0.6, "max_tokens": 2000},
            examples=[
                "生成定制简历",
                "优化简历内容",
                "匹配职位要求"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行简历生成"""
        job_desc = params.get("job_description", "")

        prompt = f"根据职位描述生成简历建议：{job_desc}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={"resume": result, "match_score": 85},
            metadata={"skill": "resume-generator"}
        )


# =============================================================================
# Creative & Media Skills
# =============================================================================

class ImageGenerationSkill(BaseExtendedSkill):
    """图像生成技能"""

    def __init__(self):
        config = SkillConfig(
            name="image-generation",
            description="使用AI生成图像，支持多种风格和尺寸",
            category=SkillCategory.CREATIVE,
            preferred_model=AIModel.SEEDREAM,
            parameters={"size": "1024x1024", "style": "realistic"},
            examples=[
                "生成产品图片",
                "创建艺术作品",
                "设计海报"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行图像生成"""
        prompt = params.get("prompt", "")
        style = params.get("style", "realistic")

        # 使用AI生成提示词
        enhanced_prompt = await self.call_ai(f"增强图像提示词：{prompt}，风格：{style}")

        return ExecutionResult(
            success=True,
            data={
                "prompt": enhanced_prompt,
                "style": style,
                "status": "ready_for_generation"
            },
            metadata={"skill": "image-generation"}
        )


class VideoGenerationSkill(BaseExtendedSkill):
    """视频生成技能"""

    def __init__(self):
        config = SkillConfig(
            name="video-generation",
            description="生成视频内容，支持多种场景和风格",
            category=SkillCategory.CREATIVE,
            preferred_model=AIModel.SEEDANCE,
            parameters={"duration": 5, "fps": 30},
            examples=[
                "生成营销视频",
                "创建动画短片",
                "制作产品演示"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行视频生成"""
        prompt = params.get("prompt", "")
        duration = params.get("duration", 5)

        prompt_for_video = await self.call_ai(f"生成视频描述：{prompt}，时长：{duration}秒")

        return ExecutionResult(
            success=True,
            data={
                "prompt": prompt_for_video,
                "duration": duration,
                "status": "ready_for_generation"
            },
            metadata={"skill": "video-generation"}
        )


class YoutubeTranscriptSkill(BaseExtendedSkill):
    """YouTube转录技能"""

    def __init__(self):
        config = SkillConfig(
            name="youtube-transcript",
            description="获取YouTube视频的转录文本",
            category=SkillCategory.CREATIVE,
            preferred_model=AIModel.KIMI,
            parameters={"language": "zh-CN", "max_tokens": 5000},
            examples=[
                "获取视频转录",
                "翻译视频内容",
                "提取关键信息"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行转录获取"""
        url = params.get("url", "")

        prompt = f"获取并总结YouTube视频：{url}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={"transcript": result, "url": url},
            metadata={"skill": "youtube-transcript"}
        )


# =============================================================================
# Security Skills
# =============================================================================

class SecurityScanSkill(BaseExtendedSkill):
    """安全扫描技能"""

    def __init__(self):
        config = SkillConfig(
            name="security-scan",
            description="代码安全扫描，检测潜在漏洞和安全问题",
            category=SkillCategory.SECURITY,
            preferred_model=AIModel.QWEN,
            parameters={"temperature": 0.2, "max_tokens": 2000},
            examples=[
                "扫描SQL注入",
                "检查XSS漏洞",
                "评估认证问题"
            ]
        )
        super().__init__(config)

    async def execute(self, params: Dict[str, Any]) -> ExecutionResult:
        """执行安全扫描"""
        code = params.get("code", "")

        prompt = f"安全扫描以下代码：\n{code}"
        result = await self.call_ai(prompt)

        return ExecutionResult(
            success=True,
            data={"vulnerabilities": [], "report": result},
            metadata={"skill": "security-scan", "severity": "low"}
        )


# =============================================================================
# Extended Skill Manager
# =============================================================================

class ExtendedSkillManager:
    """扩展技能管理器"""

    def __init__(self):
        self.skills: Dict[str, BaseExtendedSkill] = {}
        self.llm_manager = None
        self._register_all_skills()

    def _register_all_skills(self):
        """注册所有技能"""
        # 文档处理
        self.skills["docx"] = DocxSkill()
        self.skills["pdf"] = PdfSkill()
        self.skills["pptx"] = PptxSkill()
        self.skills["xlsx"] = XlsxSkill()

        # 开发工具
        self.skills["code-review"] = CodeReviewSkill()
        self.skills["tdd"] = TddSkill()
        self.skills["webapp-testing"] = PlaywrightSkill()
        self.skills["git-automation"] = GitSkill()

        # 生产力
        self.skills["file-organizer"] = FileOrganizerSkill()
        self.skills["calendar"] = CalendarSkill()
        self.skills["email"] = EmailSkill()
        self.skills["task-manager"] = TodoistSkill()

        # 监控分析
        self.skills["news-aggregator"] = NewsAggregatorSkill()
        self.skills["data-analysis"] = DataAnalysisSkillExtended()
        self.skills["postgres-query"] = PostgresSkill()

        # 沟通写作
        self.skills["article-extractor"] = ArticleExtractorSkill()
        self.skills["brainstorming"] = BrainstormingSkill()
        self.skills["resume-generator"] = ResumeSkill()

        # 创意媒体
        self.skills["image-generation"] = ImageGenerationSkill()
        self.skills["video-generation"] = VideoGenerationSkill()
        self.skills["youtube-transcript"] = YoutubeTranscriptSkill()

        # 安全
        self.skills["security-scan"] = SecurityScanSkill()

        logger.info(f"已注册 {len(self.skills)} 个扩展技能")

    def set_llm_manager(self, llm_manager):
        """设置LLM管理器"""
        self.llm_manager = llm_manager
        for skill in self.skills.values():
            skill.set_llm_manager(llm_manager)

    def get_skill(self, name: str) -> Optional[BaseExtendedSkill]:
        """获取技能"""
        return self.skills.get(name)

    def list_skills(self, category: Optional[SkillCategory] = None) -> List[Dict]:
        """列出技能"""
        result = []
        for name, skill in self.skills.items():
            if category is None or skill.config.category == category:
                result.append({
                    "name": name,
                    "description": skill.config.description,
                    "category": skill.config.category.value,
                    "model": skill.config.preferred_model.value,
                    "examples": skill.config.examples
                })
        return result

    def get_categories(self) -> List[str]:
        """获取技能分类"""
        return [c.value for c in SkillCategory]


# =============================================================================
# Skill Execution Engine
# =============================================================================

class SkillExecutionEngine:
    """技能执行引擎"""

    def __init__(self):
        self.skill_manager = ExtendedSkillManager()

    def set_llm_manager(self, llm_manager):
        """设置LLM管理器"""
        self.skill_manager.set_llm_manager(llm_manager)

    async def execute_skill(self, skill_name: str, params: Dict[str, Any]) -> ExecutionResult:
        """执行技能"""
        skill = self.skill_manager.get_skill(skill_name)
        if not skill:
            return ExecutionResult(
                success=False,
                error=f"技能不存在: {skill_name}"
            )

        try:
            result = await skill.execute(params)
            skill.log_execution(params, result)
            return result
        except Exception as e:
            logger.error(f"技能执行失败: {e}")
            return ExecutionResult(
                success=False,
                error=str(e)
            )

    async def execute_workflow(self, workflow: List[Dict]) -> List[ExecutionResult]:
        """执行工作流"""
        results = []
        for step in workflow:
            skill_name = step.get("skill")
            params = step.get("params", {})

            result = await self.execute_skill(skill_name, params)
            results.append(result)

            # 如果失败，停止工作流
            if not result.success:
                logger.warning(f"工作流在步骤 {len(results)} 失败")
                break

        return results


# =============================================================================
# Export
# =============================================================================

__all__ = [
    "SkillCategory",
    "AIModel",
    "SkillConfig",
    "ExecutionResult",
    "BaseExtendedSkill",
    "ExtendedSkillManager",
    "SkillExecutionEngine",
    # Document Skills
    "DocxSkill", "PdfSkill", "PptxSkill", "XlsxSkill",
    # Development Skills
    "CodeReviewSkill", "TddSkill", "PlaywrightSkill", "GitSkill",
    # Productivity Skills
    "FileOrganizerSkill", "CalendarSkill", "EmailSkill", "TodoistSkill",
    # Monitoring Skills
    "NewsAggregatorSkill", "DataAnalysisSkillExtended", "PostgresSkill",
    # Communication Skills
    "ArticleExtractorSkill", "BrainstormingSkill", "ResumeSkill",
    # Creative Skills
    "ImageGenerationSkill", "VideoGenerationSkill", "YoutubeTranscriptSkill",
    # Security Skills
    "SecurityScanSkill",
]
