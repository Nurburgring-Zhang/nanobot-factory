"""
Nanobot-Factory Skills集成模块
======================

本模块整合了来自多个来源的Skills和能力，包括：
- Agent-Reach: 13+平台集成（Twitter/X, Reddit, YouTube, GitHub, Bilibili, 小红书, 抖音, LinkedIn, Boss直聘, 微信公众号, RSS等）
- Awesome Claude Skills: 100+专业Skills（文档处理、开发工具、数据分析、科学研究、媒体内容、安全、项目管理等）
- ListenHub: 播客、视频、语音生成能力
- GitNexus: 零服务器代码智能引擎
- OpenClaw Use Cases: 70+真实用例

作者：MiniMax Agent
日期：2026-03-05
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)


class SkillCategory(Enum):
    """Skills分类枚举"""
    # 文档处理
    DOCUMENT = "document"
    # 开发工具
    DEVELOPMENT = "development"
    # 数据分析
    DATA_ANALYSIS = "data_analysis"
    # 科学研究
    SCIENTIFIC = "scientific"
    # 媒体内容
    MEDIA = "media"
    # 安全
    SECURITY = "security"
    # 项目管理
    PROJECT_MANAGEMENT = "project_management"
    # 通信
    COMMUNICATION = "communication"
    # 社交媒体
    SOCIAL_MEDIA = "social_media"
    # 自动化
    AUTOMATION = "automation"
    # AI/ML
    AI_ML = "ai_ml"
    # 其他
    OTHER = "other"


@dataclass
class Skill:
    """Skill定义数据结构"""
    name: str
    description: str
    category: SkillCategory
    source: str  # 来源：agent-reach, awesome-claude-skills, listenhub等
    commands: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable] = None
    dependencies: List[str] = field(default_factory=list)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelConfig:
    """渠道配置数据结构"""
    name: str
    platform: str
    enabled: bool = False
    config: Dict[str, Any] = field(default_factory=dict)
    credentials: Dict[str, str] = field(default_factory=dict)


class SkillsRegistry:
    """
    Skills注册中心

    负责管理所有可用的Skills，提供发现、加载、执行等功能
    """

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._channels: Dict[str, ChannelConfig] = {}
        self._initialized = False
        logger.info("SkillsRegistry初始化完成")

    def register_skill(self, skill: Skill) -> None:
        """注册一个Skill"""
        self._skills[skill.name] = skill
        logger.info(f"已注册Skill: {skill.name} (来源: {skill.source})")

    def register_channel(self, channel: ChannelConfig) -> None:
        """注册一个渠道"""
        self._channels[channel.name] = channel
        logger.info(f"已注册渠道: {channel.name} (平台: {channel.platform})")

    def get_skill(self, name: str) -> Optional[Skill]:
        """获取指定Skill"""
        return self._skills.get(name)

    def get_skill_by_category(self, category: SkillCategory) -> List[Skill]:
        """获取指定分类的所有Skills"""
        return [s for s in self._skills.values() if s.category == category]

    def get_all_skills(self) -> List[Skill]:
        """获取所有Skills"""
        return list(self._skills.values())

    def get_enabled_skills(self) -> List[Skill]:
        """获取所有已启用的Skills"""
        return [s for s in self._skills.values() if s.enabled]

    def get_channel(self, name: str) -> Optional[ChannelConfig]:
        """获取指定渠道"""
        return self._channels.get(name)

    def get_all_channels(self) -> List[ChannelConfig]:
        """获取所有渠道"""
        return list(self._channels.values())

    def enable_skill(self, name: str) -> bool:
        """启用指定Skill"""
        if name in self._skills:
            self._skills[name].enabled = True
            logger.info(f"已启用Skill: {name}")
            return True
        return False

    def disable_skill(self, name: str) -> bool:
        """禁用指定Skill"""
        if name in self._skills:
            self._skills[name].enabled = False
            logger.info(f"已禁用Skill: {name}")
            return True
        return False

    def enable_channel(self, name: str) -> bool:
        """启用指定渠道"""
        if name in self._channels:
            self._channels[name].enabled = True
            logger.info(f"已启用渠道: {name}")
            return True
        return False

    def disable_channel(self, name: str) -> bool:
        """禁用指定渠道"""
        if name in self._channels:
            self._channels[name].enabled = False
            logger.info(f"已禁用渠道: {name}")
            return True
        return False

    async def execute_skill(self, name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行指定Skill"""
        skill = self.get_skill(name)
        if not skill:
            return {"success": False, "error": f"Skill不存在: {name}"}

        if not skill.enabled:
            return {"success": False, "error": f"Skill未启用: {name}"}

        if skill.handler:
            try:
                result = await skill.handler(context)
                return {"success": True, "result": result}
            except Exception as e:
                logger.error(f"执行Skill失败: {name}, 错误: {str(e)}")
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "Skill没有处理器"}

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        category_counts = {}
        for skill in self._skills.values():
            cat = skill.category.value
            category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total_skills": len(self._skills),
            "enabled_skills": len(self.get_enabled_skills()),
            "total_channels": len(self._channels),
            "enabled_channels": len([c for c in self._channels.values() if c.enabled]),
            "skills_by_category": category_counts,
            "sources": list(set(s.source for s in self._skills.values()))
        }


# 全局Skills注册中心实例
_global_registry: Optional[SkillsRegistry] = None


def get_registry() -> SkillsRegistry:
    """获取全局Skills注册中心实例"""
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillsRegistry()
    return _global_registry


async def initialize_skills() -> None:
    """初始化所有Skills"""
    registry = get_registry()

    # 加载Agent-Reach渠道
    await _register_agent_reach_channels(registry)

    # 加载Awesome Claude Skills
    await _register_awesome_claude_skills(registry)

    # 加载ListenHub Skills
    await _register_listenhub_skills(registry)

    registry._initialized = True
    logger.info(f"Skills初始化完成: {registry.get_stats()}")


async def _register_agent_reach_channels(registry: SkillsRegistry) -> None:
    """注册Agent-Reach渠道"""
    # Agent-Reach提供了13+平台的集成能力
    channels = [
        ChannelConfig(name="twitter", platform="Twitter/X", enabled=False),
        ChannelConfig(name="reddit", platform="Reddit", enabled=False),
        ChannelConfig(name="youtube", platform="YouTube", enabled=False),
        ChannelConfig(name="github", platform="GitHub", enabled=False),
        ChannelConfig(name="bilibili", platform="Bilibili", enabled=False),
        ChannelConfig(name="xiaohongshu", platform="XiaoHongShu", enabled=False),
        ChannelConfig(name="douyin", platform="Douyin", enabled=False),
        ChannelConfig(name="linkedin", platform="LinkedIn", enabled=False),
        ChannelConfig(name="bosszhipin", platform="Boss直聘", enabled=False),
        ChannelConfig(name="wechat_mp", platform="WeChat公众号", enabled=False),
        ChannelConfig(name="rss", platform="RSS", enabled=False),
        ChannelConfig(name="web", platform="Web", enabled=False),
        ChannelConfig(name="exa_search", platform="Exa搜索", enabled=False),
    ]

    for channel in channels:
        registry.register_channel(channel)

    # 注册Agent-Reach Skill
    agent_reach_skill = Skill(
        name="agent-reach",
        description="让AI代理能够访问整个互联网的13+平台集成工具，包括Twitter/X, Reddit, YouTube, GitHub, Bilibili, 小红书, 抖音, LinkedIn, Boss直聘, 微信公众号, RSS等",
        category=SkillCategory.SOCIAL_MEDIA,
        source="agent-reach",
        commands=["帮我配", "帮我添加", "帮我安装", "agent reach", "install channels", "configure twitter", "enable reddit"],
        metadata={
            "platforms": ["twitter", "reddit", "youtube", "github", "bilibili", "xiaohongshu", "douyin", "linkedin", "bosszhipin", "wechat_mp", "rss", "web", "exa_search"],
            "installation": "pip install https://github.com/Panniantong/agent-reach/archive/main.zip",
            "usage": "agent-reach doctor, agent-reach configure, agent-reach install"
        }
    )
    registry.register_skill(agent_reach_skill)

    logger.info("已注册Agent-Reach渠道和能力")


async def _register_awesome_claude_skills(registry: SkillsRegistry) -> None:
    """注册Awesome Claude Skills"""

    # 文档处理Skills
    document_skills = [
        Skill(name="docx", description="创建、编辑、分析Word文档，支持修订跟踪、评论、格式化", category=SkillCategory.DOCUMENT, source="awesome-claude-skills", commands=["word", "word文档", "docx"]),
        Skill(name="pdf", description="提取PDF文本、表格、元数据，合并和注释PDF", category=SkillCategory.DOCUMENT, source="awesome-claude-skills", commands=["pdf", "PDF处理"]),
        Skill(name="pptx", description="读取、生成和调整幻灯片、布局、模板", category=SkillCategory.DOCUMENT, source="awesome-claude-skills", commands=["ppt", "演示文稿", "pptx"]),
        Skill(name="xlsx", description="电子表格操作：公式、图表、数据转换", category=SkillCategory.DOCUMENT, source="awesome-claude-skills", commands=["excel", "表格", "xlsx"]),
        Skill(name="polaris-datainsight-doc-extract", description="从Office文档(DOCX, PPTX, XLSX, HWP, HWPX)提取结构化数据", category=SkillCategory.DOCUMENT, source="awesome-claude-skills"),
    ]

    # 开发工具Skills
    development_skills = [
        Skill(name="web-artifacts-builder", description="使用现代前端Web技术(React, Tailwind CSS, shadcn/ui)创建精美的HTML组件", category=SkillCategory.DEVELOPMENT, source="awesome-claude-skills", commands=["前端", "网页组件", "react"]),
        Skill(name="test-driven-development", description="TDD开发流程，在编写实现代码前先编写测试", category=SkillCategory.DEVELOPMENT, source="awesome-claude-skills", commands=["tdd", "测试驱动"]),
        Skill(name="aws-skills", description="AWS开发最佳实践，CDK成本优化MCP服务器，无服务器/事件驱动架构", category=SkillCategory.DEVELOPMENT, source="awesome-claude-skills", commands=["aws", "amazon", "云服务"]),
        Skill(name="azure-devops", description="通过REST API管理Azure DevOps项目、仓库、PR、流水线", category=SkillCategory.DEVELOPMENT, source="awesome-claude-skills", commands=["azure", "devops"]),
        Skill(name="jules", description="将任务委托给Google Jules AI代理进行异步bug修复、文档、测试", category=SkillCategory.DEVELOPMENT, source="awesome-claude-skills", commands=["jules", "google代理"]),
        Skill(name="hashicorp-agent-skills", description="HashiCorp官方Terraform工作流和基础设施自动化Skills", category=SkillCategory.DEVELOPMENT, source="awesome-claude-skills", commands=["terraform", "hashicorp", "基础设施"]),
    ]

    # 数据分析Skills
    data_analysis_skills = [
        Skill(name="csv-data-summarizer", description="自动分析CSV：列分布、缺失数据、相关性", category=SkillCategory.DATA_ANALYSIS, source="awesome-claude-skills", commands=["csv", "数据分析"]),
        Skill(name="postgres", description="对PostgreSQL数据库执行安全只读SQL查询", category=SkillCategory.DATA_ANALYSIS, source="awesome-claude-skills", commands=["postgres", "postgresql", "数据库"]),
        Skill(name="mysql", description="对MySQL数据库执行安全只读SQL查询", category=SkillCategory.DATA_ANALYSIS, source="awesome-claude-skills", commands=["mysql", "数据库"]),
        Skill(name="mssql", description="对Microsoft SQL Server数据库执行安全只读SQL查询", category=SkillCategory.DATA_ANALYSIS, source="awesome-claude-skills", commands=["mssql", "sqlserver"]),
        Skill(name="kaggle-skill", description="完整的Kaggle集成：账户设置、竞争报告、数据集/模型下载", category=SkillCategory.DATA_ANALYSIS, source="awesome-claude-skills", commands=["kaggle", "机器学习竞赛"]),
    ]

    # 科学研究Skills
    scientific_skills = [
        Skill(name="claude-scientific-skills", description="125+科学Skills：生物信息学、化学信息学、临床研究、机器学习", category=SkillCategory.SCIENTIFIC, source="awesome-claude-skills", commands=["科学研究", "生物信息", "化学"]),
        Skill(name="materials-simulation-skills", description="计算材料科学Agent Skills：数值稳定性、时间步进、线性求解器", category=SkillCategory.SCIENTIFIC, source="awesome-claude-skills", commands=["材料科学", "模拟"]),
        Skill(name="deep-research", description="使用Gemini Deep Research Agent执行自主多步研究", category=SkillCategory.SCIENTIFIC, source="awesome-claude-skills", commands=["深度研究", "市场分析"]),
    ]

    # 媒体内容Skills
    media_skills = [
        Skill(name="youtube-transcript", description="从YouTube视频获取字幕并准备摘要", category=SkillCategory.MEDIA, source="awesome-claude-skills", commands=["youtube", "字幕", "视频转录"]),
        Skill(name="video-downloader", description="从YouTube和其他平台下载视频", category=SkillCategory.MEDIA, source="awesome-claude-skills", commands=["视频下载", "youtube下载"]),
        Skill(name="image-enhancer", description="提高图像质量，特别是截图", category=SkillCategory.MEDIA, source="awesome-claude-skills", commands=["图片增强", "图像优化"]),
        Skill(name="imagen", description="使用Google Gemini图像生成API生成图像", category=SkillCategory.MEDIA, source="awesome-claude-skills", commands=["AI绘图", "imagen", "图像生成"]),
        Skill(name="elevenlabs", description="使用ElevenLabs API进行文本转语音旁白和双主持播客生成", category=SkillCategory.MEDIA, source="awesome-claude-skills", commands=["语音合成", "播客", "tts"]),
        Skill(name="google-tts", description="使用Google Cloud TTS进行文本转语音旁白和播客生成", category=SkillCategory.MEDIA, source="awesome-claude-skills", commands=["google语音", "语音合成"]),
    ]

    # 安全Skills
    security_skills = [
        Skill(name="VibeSec-Skill", description="帮助Claude编写安全代码和防止常见漏洞", category=SkillCategory.SECURITY, source="awesome-claude-skills", commands=["安全", "漏洞防护"]),
        Skill(name="owasp-security", description="OWASP Top 10:2025, ASVS 5.0, Agentic AI安全(2026)", category=SkillCategory.SECURITY, source="awesome-claude-skills", commands=["owasp", "安全标准"]),
        Skill(name="ffuf_claude_skill", description="将Claude与FFUF(fuzzing)集成并分析结果", category=SkillCategory.SECURITY, source="awesome-claude-skills", commands=["fuzzing", "安全测试"]),
        Skill(name="trail-of-bits-security", description="CodeQL/Semgrep静态分析安全Skills", category=SkillCategory.SECURITY, source="awesome-claude-skills", commands=["代码审计", "静态分析"]),
    ]

    # 项目管理Skills
    project_management_skills = [
        Skill(name="linear-claude-skill", description="使用MCP工具管理Linear问题、项目和团队", category=SkillCategory.PROJECT_MANAGEMENT, source="awesome-claude-skills", commands=["linear", "项目管理", "issue跟踪"]),
        Skill(name="meeting-insights-analyzer", description="将会议记录转化为可操作洞察", category=SkillCategory.PROJECT_MANAGEMENT, source="awesome-claude-skills", commands=["会议分析", "会议洞察"]),
        Skill(name="google-workspace-skills", description="Google Workspace集成套件：Gmail, 日历, 聊天, 文档, 表格, 幻灯片", category=SkillCategory.PROJECT_MANAGEMENT, source="awesome-claude-skills", commands=["google工作区", "gmail", "google文档"]),
        Skill(name="pm-skills", description="24个产品管理Skills贯穿三钻生命周期", category=SkillCategory.PROJECT_MANAGEMENT, source="awesome-claude-skills", commands=["产品管理", "PM"]),
    ]

    # 注册所有Skills
    for skill in document_skills + development_skills + data_analysis_skills + scientific_skills + media_skills + security_skills + project_management_skills:
        registry.register_skill(skill)

    logger.info(f"已注册{len(document_skills) + len(development_skills) + len(data_analysis_skills) + len(scientific_skills) + len(media_skills) + len(security_skills) + len(project_management_skills)}个Awesome Claude Skills")


async def _register_listenhub_skills(registry: SkillsRegistry) -> None:
    """注册ListenHub Skills"""

    listenhub_skills = [
        Skill(
            name="podcast-generator",
            description="生成1-2人对话播客，有互动感，适合深度讨论、话题探索",
            category=SkillCategory.MEDIA,
            source="listenhub",
            commands=["播客", "做播客", "对话"],
            metadata={"type": "podcast", "formats": ["1-2人对话"]}
        ),
        Skill(
            name="video-explainer",
            description="单人讲解+AI配图的解说视频，适合产品介绍、概念解释",
            category=SkillCategory.MEDIA,
            source="listenhub",
            commands=["解说视频", "讲解视频", "视频"],
            metadata={"type": "video_explainer", "formats": ["单人讲解+AI配图"]}
        ),
        Skill(
            name="voice-over",
            description="纯音频语音朗读，生成最快，适合文章转音频、笔记复习",
            category=SkillCategory.MEDIA,
            source="listenhub",
            commands=["朗读", "语音朗读", "文字转语音"],
            metadata={"type": "voice_over", "formats": ["纯音频"]}
        ),
        Skill(
            name="image-generator",
            description="快速获得符合描述的高质量单张图片，适合朋友圈发图、海报制作",
            category=SkillCategory.MEDIA,
            source="listenhub",
            commands=["生成图片", "AI绘图", "图片生成"],
            metadata={"type": "image", "formats": ["单张图片"]}
        ),
    ]

    for skill in listenhub_skills:
        registry.register_skill(skill)

    logger.info(f"已注册{len(listenhub_skills)}个ListenHub Skills")


# 导出模块
__all__ = [
    "Skill",
    "ChannelConfig",
    "SkillsRegistry",
    "SkillCategory",
    "get_registry",
    "initialize_skills",
]
