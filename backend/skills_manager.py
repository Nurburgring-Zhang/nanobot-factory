#!/usr/bin/env python3
"""
Nanobot Factory - Skills Manager Module
完整的Skills管理系统，集成来自Claude Skills、OpenClaw、ListenHub等的所有能力

功能：
- Skills注册与发现
- Skills自动执行
- Skills分类管理
- Skills依赖管理
- Skills版本控制
- 渐进式披露

@author MiniMax Agent
@date 2026-03-03
"""

import os
import json
import yaml
import logging
import asyncio
import hashlib
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Set, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import importlib.util
import inspect
import uuid

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

class SkillCategory(Enum):
    """技能分类"""
    DOCUMENT = "document"           # 文档处理
    MEDIA = "media"                 # 媒体生成
    DEVELOPMENT = "development"    # 开发工具
    DATA = "data"                  # 数据分析
    WRITING = "writing"            # 写作创作
    TRANSLATION = "translation"     # 翻译
    RESEARCH = "research"          # 研究搜索
    PRODUCTIVITY = "productivity"   # 效率工具
    COMMUNICATION = "communication" # 沟通协作
    SECURITY = "security"           # 安全测试
    CUSTOM = "custom"              # 自定义


class SkillStatus(Enum):
    """技能状态"""
    INSTALLED = "installed"
    AVAILABLE = "available"
    UPDATE_AVAILABLE = "update_available"
    ERROR = "error"
    DISABLED = "disabled"


class SkillType(Enum):
    """技能类型"""
    PROMPT = "prompt"              # 提示词技能
    SCRIPT = "script"              # 脚本技能
    MCP = "mcp"                   # MCP服务器技能
    AGENT = "agent"               # Agent技能
    HYBRID = "hybrid"             # 混合技能


@dataclass
class SkillMetadata:
    """技能元数据"""
    id: str
    name: str
    description: str
    category: SkillCategory
    skill_type: SkillType
    version: str = "1.0.0"
    author: str = "Nanobot Factory"
    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    required_apis: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=list)  # Claude.ai, Claude Code, API, etc.
    examples: List[str] = field(default_factory=list)
    icon: str = ""


@dataclass
class SkillDefinition:
    """技能定义"""
    metadata: SkillMetadata
    instructions: str = ""
    prompts: Dict[str, str] = field(default_factory=dict)
    scripts: Dict[str, str] = field(default_factory=dict)
    templates: Dict[str, str] = field(default_factory=dict)
    resources: Dict[str, str] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillExecutionResult:
    """技能执行结果"""
    success: bool
    result: Any = None
    error: str = ""
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Skills Registry
# =============================================================================

class SkillsRegistry:
    """技能注册中心"""

    def __init__(self, skills_dir: str = None):
        self.skills_dir = skills_dir or "./skills"
        self.skills: Dict[str, SkillDefinition] = {}
        self.categories: Dict[SkillCategory, List[str]] = {cat: [] for cat in SkillCategory}
        self.keywords_index: Dict[str, List[str]] = {}

    def register_skill(self, skill: SkillDefinition) -> bool:
        """注册技能"""
        try:
            skill_id = skill.metadata.id

            # 检查依赖
            for dep in skill.metadata.dependencies:
                if dep not in self.skills:
                    logger.warning(f"Skill {skill_id} requires {dep} which is not installed")

            # 注册技能
            self.skills[skill_id] = skill

            # 更新分类索引
            cat = skill.metadata.category
            if skill_id not in self.categories[cat]:
                self.categories[cat].append(skill_id)

            # 更新关键词索引
            for kw in skill.metadata.keywords:
                if kw not in self.keywords_index:
                    self.keywords_index[kw] = []
                if skill_id not in self.keywords_index[kw]:
                    self.keywords_index[kw].append(skill_id)

            logger.info(f"Registered skill: {skill_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to register skill: {e}")
            return False

    def get_skill(self, skill_id: str) -> Optional[SkillDefinition]:
        """获取技能"""
        return self.skills.get(skill_id)

    def search_skills(self, query: str, limit: int = 10) -> List[SkillDefinition]:
        """搜索技能"""
        results = []
        query_lower = query.lower()

        # 搜索关键词
        for skill_id, skill in self.skills.items():
            score = 0

            # 名称匹配
            if query_lower in skill.metadata.name.lower():
                score += 10

            # 描述匹配
            if query_lower in skill.metadata.description.lower():
                score += 5

            # 关键词匹配
            for kw in skill.metadata.keywords:
                if query_lower in kw.lower():
                    score += 3

            # 标签匹配
            for tag in skill.metadata.tags:
                if query_lower in tag.lower():
                    score += 2

            if score > 0:
                results.append((skill_id, skill, score))

        # 排序并返回
        results.sort(key=lambda x: x[2], reverse=True)
        return [r[1] for r in results[:limit]]

    def get_skills_by_category(self, category: SkillCategory) -> List[SkillDefinition]:
        """获取分类下的所有技能"""
        skill_ids = self.categories.get(category, [])
        return [self.skills[sid] for sid in skill_ids if sid in self.skills]

    def get_all_skills(self) -> Dict[str, SkillMetadata]:
        """获取所有技能元数据"""
        return {
            sid: skill.metadata
            for sid, skill in self.skills.items()
        }


# =============================================================================
# Skills Executor
# =============================================================================

class SkillsExecutor:
    """技能执行器"""

    def __init__(self, registry: SkillsRegistry):
        self.registry = registry
        self.execution_history: List[Dict[str, Any]] = []

    async def execute_skill(
        self,
        skill_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> SkillExecutionResult:
        """执行技能"""
        start_time = datetime.now()

        try:
            skill = self.registry.get_skill(skill_id)
            if not skill:
                return SkillExecutionResult(
                    success=False,
                    error=f"Skill not found: {skill_id}"
                )

            # 检查依赖
            for dep in skill.metadata.required_tools:
                if not self._check_tool_available(dep):
                    return SkillExecutionResult(
                        success=False,
                        error=f"Required tool not available: {dep}"
                    )

            # 执行技能
            result = await self._execute_skill_logic(skill, params, context or {})

            execution_time = (datetime.now() - start_time).total_seconds()

            # 记录执行历史
            self.execution_history.append({
                "skill_id": skill_id,
                "params": params,
                "result": result,
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            })

            return SkillExecutionResult(
                success=True,
                result=result,
                execution_time=execution_time
            )

        except Exception as e:
            logger.error(f"Skill execution error: {e}")
            return SkillExecutionResult(
                success=False,
                error=str(e),
                execution_time=(datetime.now() - start_time).total_seconds()
            )

    async def _execute_skill_logic(
        self,
        skill: SkillDefinition,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Any:
        """执行技能逻辑"""
        skill_type = skill.metadata.skill_type

        if skill_type == SkillType.PROMPT:
            return await self._execute_prompt_skill(skill, params, context)
        elif skill_type == SkillType.SCRIPT:
            return await self._execute_script_skill(skill, params, context)
        elif skill_type == SkillType.MCP:
            return await self._execute_mcp_skill(skill, params, context)
        elif skill_type == SkillType.AGENT:
            return await self._execute_agent_skill(skill, params, context)
        else:
            return await self._execute_hybrid_skill(skill, params, context)

    async def _execute_prompt_skill(
        self,
        skill: SkillDefinition,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行提示词技能"""
        # 获取主提示词
        main_prompt = skill.prompts.get("main", skill.instructions)

        # 替换参数
        for key, value in params.items():
            main_prompt = main_prompt.replace(f"{{{key}}}", str(value))

        return {
            "prompt": main_prompt,
            "skill_id": skill.metadata.id,
            "type": "prompt"
        }

    async def _execute_script_skill(
        self,
        skill: SkillDefinition,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行脚本技能"""
        # 这里会调用实际的脚本执行
        return {
            "script": skill.scripts,
            "params": params,
            "skill_id": skill.metadata.id,
            "type": "script"
        }

    async def _execute_mcp_skill(
        self,
        skill: SkillDefinition,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行MCP技能"""
        return {
            "mcp_config": skill.config.get("mcp", {}),
            "params": params,
            "skill_id": skill.metadata.id,
            "type": "mcp"
        }

    async def _execute_agent_skill(
        self,
        skill: SkillDefinition,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行Agent技能"""
        return {
            "agent_config": skill.config.get("agent", {}),
            "params": params,
            "skill_id": skill.metadata.id,
            "type": "agent"
        }

    async def _execute_hybrid_skill(
        self,
        skill: SkillDefinition,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行混合技能"""
        results = {}

        # 执行提示词部分
        if skill.prompts:
            results["prompts"] = await self._execute_prompt_skill(skill, params, context)

        # 执行脚本部分
        if skill.scripts:
            results["scripts"] = await self._execute_script_skill(skill, params, context)

        return results

    def _check_tool_available(self, tool: str) -> bool:
        """检查工具是否可用"""
        # 检查系统命令
        try:
            result = subprocess.run(
                ["which", tool],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"工具检测失败: {e}")
            return False


# =============================================================================
# Built-in Skills Definitions
# =============================================================================

class BuiltInSkills:
    """内置技能定义"""

    @staticmethod
    def get_document_skills() -> List[SkillDefinition]:
        """文档处理技能"""
        skills = []

        # Docx技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="docx",
                name="docx",
                description="创建、编辑和分析Word文档，支持追踪修订、评论、格式调整",
                category=SkillCategory.DOCUMENT,
                skill_type=SkillType.PROMPT,
                tags=["word", "document", "office", "microsoft"],
                keywords=["word", "docx", "document", "word文档", "创建文档"],
                required_tools=["python-docx"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个Word文档处理专家。请根据用户需求：
1. 创建新的Word文档
2. 编辑现有文档内容
3. 添加格式和样式
4. 插入表格、图片
5. 添加页眉页脚
6. 设置页面布局

请确保文档格式规范、内容准确。""",
            prompts={
                "create": "创建一个新的Word文档，包含以下内容：{content}",
                "edit": "编辑Word文档：{instructions}",
                "format": "格式化文档：{format_spec}"
            }
        ))

        # PDF技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="pdf",
                name="pdf",
                description="提取PDF文本、表格、元数据，合并和标注PDF",
                category=SkillCategory.DOCUMENT,
                skill_type=SkillType.PROMPT,
                tags=["pdf", "document", "extract", "merge"],
                keywords=["pdf", "提取文本", "PDF处理", "合并PDF"],
                required_tools=["PyPDF2", "pdfplumber"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个PDF处理专家。请根据用户需求：
1. 提取PDF文本内容
2. 提取表格数据
3. 提取元数据
4. 合并多个PDF
5. 拆分PDF
6. 添加注释和水印
7. 填写PDF表单

请使用适当的Python库完成任务。""",
            prompts={
                "extract_text": "从PDF中提取所有文本：{pdf_path}",
                "extract_tables": "从PDF中提取表格数据：{pdf_path}",
                "merge": "合并以下PDF文件：{pdf_list}"
            }
        ))

        # PPTX技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="pptx",
                name="pptx",
                description="读取、生成和调整PPT幻灯片、布局、模板",
                category=SkillCategory.DOCUMENT,
                skill_type=SkillType.PROMPT,
                tags=["powerpoint", "pptx", "presentation", "slides"],
                keywords=["ppt", "powerpoint", "幻灯片", "演示文稿"],
                required_tools=["python-pptx"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个PPT制作专家。请根据用户需求：
1. 创建新的PPT演示文稿
2. 设计幻灯片布局
3. 添加文本和图片
4. 设置动画效果
5. 调整配色方案
6. 应用主题模板

请确保幻灯片美观专业。""",
            prompts={
                "create": "创建一个{slide_count}页的PPT，主题：{topic}",
                "add_slide": "在PPT中添加新幻灯片：{slide_spec}",
                "apply_template": "应用模板：{template_name}"
            }
        ))

        # XLSX技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="xlsx",
                name="xlsx",
                description="电子表格操作：公式、图表、数据转换",
                category=SkillCategory.DOCUMENT,
                skill_type=SkillType.PROMPT,
                tags=["excel", "xlsx", "spreadsheet", "charts"],
                keywords=["excel", "xlsx", "表格", "图表", "数据分析"],
                required_tools=["openpyxl", "pandas"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个Excel处理专家。请根据用户需求：
1. 创建和编辑Excel工作簿
2. 使用公式计算
3. 创建图表
4. 数据筛选和排序
5. 透视表操作
6. 条件格式化

请确保数据准确、格式规范。""",
            prompts={
                "create": "创建一个Excel文件：{spec}",
                "add_formula": "添加公式：{formula_spec}",
                "create_chart": "创建图表：{chart_spec}"
            }
        ))

        return skills

    @staticmethod
    def get_media_skills() -> List[SkillDefinition]:
        """媒体生成技能"""
        skills = []

        # 图片生成技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="image_generation",
                name="Image Generation",
                description="使用AI生成高质量图片，支持多种风格和模型",
                category=SkillCategory.MEDIA,
                skill_type=SkillType.AGENT,
                tags=["image", "generation", "AI", "picture"],
                keywords=["生成图片", "AI绘图", "文生图", "图像生成"],
                required_apis=["seedream", "seedance", "doubao", "kling"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个AI图像生成专家。请根据用户需求：
1. 分析用户描述的图像内容
2. 优化生成提示词
3. 选择合适的AI模型
4. 生成高质量图片
5. 如果需要，进行图像后处理

支持的模型：Seedream 5.0, Seedance 2.0, Nano Banana, 豆包, 可灵, ComfyUI""",
            prompts={
                "generate": "生成图片：{description}",
                "optimize_prompt": "优化提示词：{original_prompt}"
            },
            config={
                "agent": {
                    "model_selection": "auto",
                    "providers": ["seedream", "seedance", "doubao", "kling", "comfyui"]
                }
            }
        ))

        # 视频生成技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="video_generation",
                name="Video Generation",
                description="使用AI生成视频，支持多种风格和时长",
                category=SkillCategory.MEDIA,
                skill_type=SkillType.AGENT,
                tags=["video", "generation", "AI", "movie"],
                keywords=["生成视频", "AI视频", "文生视频", "视频制作"],
                required_apis=["seedance", "kling", "runway"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个AI视频生成专家。请根据用户需求：
1. 分析用户描述的视频内容
2. 撰写视频脚本和分镜
3. 优化生成提示词
4. 生成高质量视频
5. 如果需要，进行视频后处理

支持的模型：Seedance 2.0, 可灵, Runway等""",
            prompts={
                "generate": "生成视频：{description}",
                "storyboard": "生成分镜：{script}"
            },
            config={
                "agent": {
                    "model_selection": "auto",
                    "providers": ["seedance", "kling"]
                }
            }
        ))

        # 语音合成技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="tts",
                name="Text-to-Speech",
                description="将文本转换为自然语音，支持多种声音和语言",
                category=SkillCategory.MEDIA,
                skill_type=SkillType.AGENT,
                tags=["tts", "voice", "audio", "speech"],
                keywords=["语音合成", "文字转语音", "TTS", "配音"],
                required_apis=["elevenlabs", "google_tts", "azure_tts"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个语音合成专家。请根据用户需求：
1. 将文本转换为语音
2. 选择合适的声音和语言
3. 调整语速和语调
4. 添加背景音乐
5. 生成高质量音频

支持的声音：ElevenLabs, Google TTS, Azure TTS等""",
            prompts={
                "synthesize": "合成语音：{text}",
                "voice_clone": "克隆声音：{voice_sample}"
            }
        ))

        # 播客生成技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="podcast_generation",
                name="Podcast Generation",
                description="生成播客节目，支持对话和单人讲解",
                category=SkillCategory.MEDIA,
                skill_type=SkillType.AGENT,
                tags=["podcast", "audio", "voice", "podcast生成"],
                keywords=["播客生成", "AI播客", "语音对话", "有声内容"],
                required_apis=["listenhub", "elevenlabs"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个播客制作专家。请根据用户需求：
1. 理解播客主题
2. 生成对话脚本
3. 选择合适的声音组合
4. 生成自然对话语音
5. 添加背景音乐和音效

支持的功能：双人对话、单人讲解、语音朗读""",
            prompts={
                "generate": "生成播客：{topic}",
                "dialogue": "生成对话脚本：{topic}"
            }
        ))

        return skills

    @staticmethod
    def get_development_skills() -> List[SkillDefinition]:
        """开发技能"""
        skills = []

        # MCP技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="mcp_builder",
                name="MCP Builder",
                description="创建MCP(Model Context Protocol)服务器",
                category=SkillCategory.DEVELOPMENT,
                skill_type=SkillType.PROMPT,
                tags=["mcp", "server", "development", "api"],
                keywords=["MCP", "模型上下文协议", "服务器开发", "API"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个MCP服务器开发专家。请根据用户需求：
1. 设计MCP服务器架构
2. 编写Python或TypeScript实现
3. 定义工具和资源
4. 实现认证和错误处理
5. 添加文档和测试

请遵循MCP协议规范。""",
            prompts={
                "create_server": "创建MCP服务器：{server_spec}",
                "add_tool": "添加工具：{tool_spec}"
            }
        ))

        # 数据库技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="database",
                name="Database Operations",
                description="执行安全的数据库查询和操作",
                category=SkillCategory.DATA,
                skill_type=SkillType.PROMPT,
                tags=["database", "sql", "query", "postgres", "mysql"],
                keywords=["数据库", "SQL查询", "数据操作", "PostgreSQL", "MySQL"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个数据库专家。请根据用户需求：
1. 编写SQL查询
2. 执行数据操作
3. 优化查询性能
4. 设计数据库结构
5. 处理事务和并发

注意安全：只执行只读查询，防止SQL注入。""",
            prompts={
                "query": "执行查询：{sql}",
                "optimize": "优化查询：{sql}"
            }
        ))

        # 测试技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="testing",
                name="Testing",
                description="编写和执行测试用例",
                category=SkillCategory.DEVELOPMENT,
                skill_type=SkillType.PROMPT,
                tags=["testing", "test", "pytest", "unittest"],
                keywords=["测试", "单元测试", "集成测试", "测试用例"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个测试工程师。请根据用户需求：
1. 编写单元测试
2. 编写集成测试
3. 使用pytest框架
4. 创建测试数据
5. 分析测试覆盖率

请确保测试全面、可靠。""",
            prompts={
                "unit_test": "编写单元测试：{function_spec}",
                "integration_test": "编写集成测试：{feature_spec}"
            }
        ))

        return skills

    @staticmethod
    def get_research_skills() -> List[SkillDefinition]:
        """研究搜索技能"""
        skills = []

        # 网络搜索技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="web_search",
                name="Web Search",
                description="全网搜索和信息检索",
                category=SkillCategory.RESEARCH,
                skill_type=SkillType.AGENT,
                tags=["search", "web", "research", "information"],
                keywords=["搜索", "全网检索", "信息收集", "网络搜索"],
                required_apis=["exa", "jina"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个信息检索专家。请根据用户需求：
1. 理解搜索意图
2. 执行全网搜索
3. 提取关键信息
4. 整理搜索结果
5. 提供信息来源

支持：Jina Reader, Exa搜索, 语义搜索""",
            prompts={
                "search": "搜索信息：{query}",
                "extract": "提取内容：{url}"
            }
        ))

        # GitHub技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="github",
                name="GitHub Operations",
                description="GitHub仓库搜索和内容获取",
                category=SkillCategory.RESEARCH,
                skill_type=SkillType.AGENT,
                tags=["github", "repository", "code", "search"],
                keywords=["GitHub", "代码搜索", "仓库检索", "开源"],
                required_tools=["gh"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个GitHub专家。请根据用户需求：
1. 搜索GitHub仓库
2. 获取仓库信息
3. 读取README
4. 获取代码内容
5. 分析项目结构

使用gh CLI进行操作。""",
            prompts={
                "search_repos": "搜索仓库：{query}",
                "get_readme": "获取README：{owner}/{repo}"
            }
        ))

        # YouTube技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="youtube",
                name="YouTube Operations",
                description="YouTube视频信息获取和字幕提取",
                category=SkillCategory.RESEARCH,
                skill_type=SkillType.AGENT,
                tags=["youtube", "video", "subtitle", "transcript"],
                keywords=["YouTube", "视频下载", "字幕提取", "B站"],
                required_tools=["yt-dlp"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个视频内容专家。请根据用户需求：
1. 获取视频信息
2. 提取字幕
3. 总结视频内容
4. 下载视频
5. 提取关键帧

使用yt-dlp进行操作。""",
            prompts={
                "get_info": "获取视频信息：{url}",
                "get_subtitle": "提取字幕：{url}"
            }
        ))

        return skills

    @staticmethod
    def get_writing_skills() -> List[SkillDefinition]:
        """写作技能"""
        skills = []

        # 中文写作技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="chinese_writing",
                name="Chinese Writing",
                description="专业中文写作辅助",
                category=SkillCategory.WRITING,
                skill_type=SkillType.PROMPT,
                tags=["writing", "chinese", "article", "content"],
                keywords=["中文写作", "文章撰写", "内容创作", "文案"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个专业的中文写作专家。请根据用户需求：
1. 撰写各类文章
2. 优化文案表达
3. 检查语法错误
4. 调整文章结构
5. 提升文章质量

请确保文章专业、流畅、符合中文规范。""",
            prompts={
                "write": "撰写文章：{topic}",
                "revise": "修改文章：{content}"
            }
        ))

        # 提示词工程技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="prompt_engineering",
                name="Prompt Engineering",
                description="提示词编写和优化",
                category=SkillCategory.WRITING,
                skill_type=SkillType.PROMPT,
                tags=["prompt", "engineering", "AI", "optimization"],
                keywords=["提示词", "prompt优化", "工程", "AI提示"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个提示词工程专家。请根据用户需求：
1. 分析需求
2. 编写高效提示词
3. 优化现有提示词
4. 添加约束条件
5. 测试提示词效果

请使用最佳实践创建高质量提示词。""",
            prompts={
                "create": "创建提示词：{task_description}",
                "optimize": "优化提示词：{existing_prompt}"
            }
        ))

        # 剧本撰写技能
        skills.append(SkillDefinition(
            metadata=SkillMetadata(
                id="script_writing",
                name="Script Writing",
                description="视频剧本和分镜撰写",
                category=SkillCategory.WRITING,
                skill_type=SkillType.PROMPT,
                tags=["script", "storyboard", "video", "movie"],
                keywords=["剧本", "分镜", "视频脚本", "文案"],
                platforms=["Claude.ai", "Claude Code", "API"]
            ),
            instructions="""你是一个剧本专家。请根据用户需求：
1. 理解视频主题
2. 撰写视频剧本
3. 设计分镜
4. 添加镜头说明
5. 优化叙事节奏

请确保剧本专业、拍摄可行。""",
            prompts={
                "write_script": "撰写剧本：{topic}",
                "create_storyboard": "创建分镜：{script}"
            }
        ))

        return skills


# =============================================================================
# API Interface
# =============================================================================

class SkillsAPI:
    """Skills API接口"""

    def __init__(self):
        self.registry = SkillsRegistry()
        self.executor = SkillsExecutor(self.registry)
        self._register_builtin_skills()

    def _register_builtin_skills(self):
        """注册内置技能"""
        # 文档处理技能
        for skill in BuiltInSkills.get_document_skills():
            self.registry.register_skill(skill)

        # 媒体技能
        for skill in BuiltInSkills.get_media_skills():
            self.registry.register_skill(skill)

        # 开发技能
        for skill in BuiltInSkills.get_development_skills():
            self.registry.register_skill(skill)

        # 研究技能
        for skill in BuiltInSkills.get_research_skills():
            self.registry.register_skill(skill)

        # 写作技能
        for skill in BuiltInSkills.get_writing_skills():
            self.registry.register_skill(skill)

        logger.info(f"Registered {len(self.registry.skills)} built-in skills")

    async def execute_skill(
        self,
        skill_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """执行技能"""
        result = await self.executor.execute_skill(skill_id, params, context)
        return {
            "success": result.success,
            "result": result.result,
            "error": result.error,
            "execution_time": result.execution_time
        }

    def search_skills(self, query: str, limit: int = 10) -> List[Dict]:
        """搜索技能"""
        skills = self.registry.search_skills(query, limit)
        return [
            {
                "id": s.metadata.id,
                "name": s.metadata.name,
                "description": s.metadata.description,
                "category": s.metadata.category.value,
                "tags": s.metadata.tags
            }
            for s in skills
        ]

    def get_skills_by_category(self, category: str) -> List[Dict]:
        """按分类获取技能"""
        try:
            cat = SkillCategory(category)
            skills = self.registry.get_skills_by_category(cat)
            return [
                {
                    "id": s.metadata.id,
                    "name": s.metadata.name,
                    "description": s.metadata.description,
                    "tags": s.metadata.tags
                }
                for s in skills
            ]
        except ValueError:
            return []

    def get_all_skills(self) -> Dict[str, Dict]:
        """获取所有技能"""
        return self.registry.get_all_skills()


# =============================================================================
# Global Instance
# =============================================================================

_skills_api: Optional[SkillsAPI] = None


def get_skills_api() -> SkillsAPI:
    """获取Skills API实例"""
    global _skills_api
    if _skills_api is None:
        _skills_api = SkillsAPI()
    return _skills_api


# =============================================================================
# V5.1 附录 D — SkillRegistry (P19 v5.1-B)
# 在已有 SkillsRegistry 的基础上,提供 V5.1 dataclass-based 风格的注册表
# 不与既有 SkillsRegistry 冲突,作为并列组件存在。
# =============================================================================

class SkillRegistryV51:
    """
    V5.1 SkillRegistry — 处理 SkillSpec 的注册 / 查询 / 触发匹配

    Methods:
        register(skill)           : 注册 SkillSpec
        get(skill_id)             : 取回 SkillSpec
        list_by_category(cat)     : 按 category 过滤
        search(query)             : 关键字模糊搜索
        trigger_match(phrase)     : 根据 trigger_phrases 匹配
        to_json() / from_json()   : 序列化 / 反序列化
    """

    def __init__(self) -> None:
        # skill_id -> SkillSpec
        self._skills: Dict[str, Any] = {}
        # category -> [skill_id]
        self._by_category: Dict[str, List[str]] = {}
        # 触发短语 lower -> skill_id (用于 trigger_match)
        self._trigger_index: Dict[str, str] = {}
        # 触发短语列表缓存(用于 in-place 查询)
        self._all_triggers: Dict[str, str] = {}

    # ---------- register ----------
    def register(self, skill: Any) -> bool:
        """注册一个 SkillSpec;重复 id 抛 ValueError"""
        if getattr(skill, "id", None) is None:
            raise ValueError("SkillSpec.id is required")
        if skill.id in self._skills:
            raise ValueError(f"Duplicate skill id: {skill.id}")
        self._skills[skill.id] = skill

        cat = getattr(skill, "category", "general") or "general"
        self._by_category.setdefault(cat, []).append(skill.id)

        for trig in getattr(skill, "trigger_phrases", []) or []:
            key = trig.lower().strip()
            if key:
                self._trigger_index[key] = skill.id
                self._all_triggers[key] = skill.id

        logger.info("SkillRegistryV51.register %s (cat=%s)", skill.id, cat)
        return True

    def register_all(self, skills) -> int:
        n = 0
        for s in skills:
            try:
                self.register(s)
                n += 1
            except ValueError:
                pass
        return n

    # ---------- 查询 ----------
    def get(self, skill_id: str) -> Optional[Any]:
        return self._skills.get(skill_id)

    def list_by_category(self, category: str) -> List[Any]:
        ids = self._by_category.get(category, [])
        return [self._skills[i] for i in ids if i in self._skills]

    def list_categories(self) -> List[str]:
        return sorted(self._by_category.keys())

    def all_ids(self) -> List[str]:
        return list(self._skills.keys())

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, skill_id: str) -> bool:
        return skill_id in self._skills

    # ---------- search ----------
    def search(self, query: str, limit: int = 10) -> List[Any]:
        """按 name / description / category / trigger phrase 模糊搜索"""
        if not query:
            return []
        q = query.lower().strip()
        results: List[tuple] = []
        for sid, skill in self._skills.items():
            score = 0
            name = (getattr(skill, "name", "") or "").lower()
            desc = (getattr(skill, "description", "") or "").lower()
            cat = (getattr(skill, "category", "") or "").lower()

            if q in name:
                score += 10
            if q in desc:
                score += 5
            if q in cat:
                score += 3
            for trig in getattr(skill, "trigger_phrases", []) or []:
                if q in trig.lower():
                    score += 7
                    break
            if score > 0:
                results.append((score, sid, skill))

        results.sort(key=lambda r: (-r[0], r[1]))
        return [r[2] for r in results[:limit]]

    # ---------- trigger_match ----------
    def trigger_match(self, trigger_phrase: str) -> Optional[Any]:
        """根据触发短语精确匹配(若不存在则子串模糊匹配第一个)"""
        if not trigger_phrase:
            return None
        key = trigger_phrase.lower().strip()
        # 1) 精确
        sid = self._trigger_index.get(key)
        if sid:
            return self._skills.get(sid)
        # 2) 子串匹配
        for trig, sid in self._all_triggers.items():
            if key in trig or trig in key:
                return self._skills.get(sid)
        return None

    # ---------- 序列化 ----------
    def to_json(self, indent: int = 2) -> str:
        import json
        data = {
            "version": "v5.1",
            "count": len(self._skills),
            "categories": self.list_categories(),
            "skills": [s.to_dict() if hasattr(s, "to_dict") else dict(s) for s in self._skills.values()],
        }
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def from_json(self, json_str: str) -> int:
        import json
        data = json.loads(json_str)
        n = 0
        for sd in data.get("skills", []):
            try:
                if hasattr(_skill_spec_factory(), "from_dict"):
                    skill = type(self._skills[next(iter(self._skills))]).from_dict(sd)
                else:
                    continue
            except Exception:
                # fallback: construct via kwargs
                try:
                    skill = next(iter(self._skills.values())).__class__(**{k: sd[k] for k in sd if k != "metadata"})
                except Exception:
                    continue
            try:
                self.register(skill)
                n += 1
            except ValueError:
                pass
        return n

    # ---------- 初始化 helper ----------
    @staticmethod
    def from_builtin(builtin_list) -> "SkillRegistryV51":
        """从 BUILTIN_SKILLS 列表构造一个注册表"""
        reg = SkillRegistryV51()
        for s in builtin_list:
            try:
                reg.register(s)
            except ValueError as e:
                logger.warning("skip duplicate: %s", e)
        return reg


# helper for from_json type reconstruction
def _skill_spec_factory():
    """返回示例 SkillSpec (用于推断 class)"""
    try:
        from backend.skills import SkillSpec
        return SkillSpec(id="__sample__", name="sample", category="sample")
    except Exception:
        return None


# Alias: 同时暴露 SkillRegistry 名字给任务调用方
SkillRegistry = SkillRegistryV51

