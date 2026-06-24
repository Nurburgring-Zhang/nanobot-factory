"""
NanoBot Factory - External Skills Integration Module
完整的外部Skills集成模块 - 集成Agent-Reach、WorldMonitor、AIRI等

功能：
- 互联网搜索Skills (Agent-Reach)
- 舆情监控Skills (WorldMonitor)  
- 虚拟角色Skills (AIRI)
- Claude Skills集合
- 微信接入Skills
- 浏览器自动化Skills
- 各种生产力Skills

@author MiniMax Agent
@date 2026-03-08
"""

import os
import json
import asyncio
import logging
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import aiohttp

logger = logging.getLogger(__name__)


# =============================================================================
# Skill Categories
# =============================================================================

class ExternalSkillCategory(Enum):
    """外部Skill分类"""
    # 互联网搜索 (Agent-Reach)
    INTERNET_SEARCH = "internet_search"          # 通用互联网搜索
    TWITTER_SEARCH = "twitter_search"           # Twitter/X搜索
    REDDIT_SEARCH = "reddit_search"             # Reddit搜索
    YOUTUBE_SEARCH = "youtube_search"           # YouTube搜索
    GITHUB_SEARCH = "github_search"             # GitHub搜索
    BILIBILI_SEARCH = "bilibili_search"         # Bilibili搜索
    XIAOHONGSHU_SEARCH = "xiaohongshu_search"  # 小红书搜索
    
    # 舆情监控 (WorldMonitor)
    NEWS_MONITOR = "news_monitor"               # 新闻监控
    SOCIAL_MEDIA_MONITOR = "social_media_monitor"  # 社交媒体监控
    MARKET_MONITOR = "market_monitor"           # 市场监控
    TREND_ANALYSIS = "trend_analysis"           # 趋势分析
    SENTIMENT_ANALYSIS = "sentiment_analysis"  # 情感分析
    
    # 虚拟角色 (AIRI)
    VIRTUAL_COMPANION = "virtual_companion"     # 虚拟伴侣
    VOICE_CHAT = "voice_chat"                   # 语音聊天
    CHARACTER_ROLEPLAY = "character_roleplay"   # 角色扮演
    
    # 微信接入
    WECHAT_MESSAGE = "wechat_message"           # 微信消息
    WECHAT_MOMENTS = "wechat_moments"          # 朋友圈监控
    
    # 浏览器自动化
    BROWSER_CONTROL = "browser_control"         # 浏览器控制
    WEB_AUTOMATION = "web_automation"          # 网页自动化
    GITHUB_OPERATIONS = "github_operations"    # GitHub操作
    
    # 生产力和效率
    DOCUMENT_SUMMARY = "document_summary"       # 文档摘要
    EMAIL_MANAGEMENT = "email_management"       # 邮件管理
    CALENDAR_MANAGEMENT = "calendar_management" # 日历管理
    
    # 数据分析
    DATA_ANALYSIS = "data_analysis"             # 数据分析
    VISUALIZATION = "visualization"             # 数据可视化
    REPORT_GENERATION = "report_generation"     # 报告生成
    
    # 开发和运维
    CODE_GENERATION = "code_generation"         # 代码生成
    CODE_REVIEW = "code_review"                 # 代码审查
    CI_CD_AUTOMATION = "ci_cd_automation"    # CI/CD自动化
    
    # 媒体处理
    IMAGE_EDITING = "image_editing"             # 图像编辑
    VIDEO_EDITING = "video_editing"           # 视频编辑
    AUDIO_PROCESSING = "audio_processing"       # 音频处理
    
    # AI模型管理
    MODEL_MANAGEMENT = "model_management"      # 模型管理
    FINE_TUNING = "fine_tuning"                # 微调训练
    PROMPT_ENGINEERING = "prompt_engineering"  # 提示词工程


# =============================================================================
# Skill Definition
# =============================================================================

@dataclass
class ExternalSkill:
    """外部Skill定义"""
    id: str
    name: str
    description: str
    category: ExternalSkillCategory
    provider: str  # 来源: agent-reach, world-monitor, airi, claude, custom
    enabled: bool = True
    version: str = "1.0.0"
    author: str = "NanoBot Team"
    parameters: Dict[str, Any] = field(default_factory=dict)
    required_apis: List[str] = field(default_factory=list)
    implementation: Optional[str] = None  # 实现代码路径


# =============================================================================
# Agent-Reach Integration (互联网搜索)
# =============================================================================

class AgentReachIntegration:
    """
    Agent-Reach集成 - 让AI代理能够读取和搜索12+平台
    支持: Twitter/X, Reddit, YouTube, GitHub, Bilibili, 小红书等
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.base_url = self.config.get("base_url", "http://localhost:8080")
        self.api_key = self.config.get("api_key", "")
        self.enabled = self.config.get("enabled", True)
        
    async def search_twitter(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """搜索Twitter"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/twitter/search",
                    params={"q": query, "limit": limit},
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "results": []}
        except Exception as e:
            logger.error(f"Twitter search error: {e}")
            return {"error": str(e), "results": []}
    
    async def search_reddit(self, query: str, subreddit: str = None, limit: int = 10) -> Dict[str, Any]:
        """搜索Reddit"""
        try:
            params = {"q": query, "limit": limit}
            if subreddit:
                params["subreddit"] = subreddit
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/reddit/search",
                    params=params,
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "results": []}
        except Exception as e:
            logger.error(f"Reddit search error: {e}")
            return {"error": str(e), "results": []}
    
    async def search_youtube(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """搜索YouTube"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/youtube/search",
                    params={"q": query, "limit": limit},
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "results": []}
        except Exception as e:
            logger.error(f"YouTube search error: {e}")
            return {"error": str(e), "results": []}
    
    async def search_github(self, query: str, repo: str = None, limit: int = 10) -> Dict[str, Any]:
        """搜索GitHub"""
        try:
            params = {"q": query, "limit": limit}
            if repo:
                params["repo"] = repo
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/github/search",
                    params=params,
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "results": []}
        except Exception as e:
            logger.error(f"GitHub search error: {e}")
            return {"error": str(e), "results": []}
    
    async def search_bilibili(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """搜索Bilibili"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/bilibili/search",
                    params={"q": query, "limit": limit},
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "results": []}
        except Exception as e:
            logger.error(f"Bilibili search error: {e}")
            return {"error": str(e), "results": []}
    
    async def search_xiaohongshu(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """搜索小红书"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/xiaohongshu/search",
                    params={"q": query, "limit": limit},
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "results": []}
        except Exception as e:
            logger.error(f"Xiaohongshu search error: {e}")
            return {"error": str(e), "results": []}
    
    async def search_all(self, query: str, platforms: List[str] = None) -> Dict[str, Any]:
        """全平台搜索"""
        platforms = platforms or ["twitter", "reddit", "youtube", "github", "bilibili"]
        results = {}
        
        for platform in platforms:
            if platform == "twitter":
                results["twitter"] = await self.search_twitter(query)
            elif platform == "reddit":
                results["reddit"] = await self.search_reddit(query)
            elif platform == "youtube":
                results["youtube"] = await self.search_youtube(query)
            elif platform == "github":
                results["github"] = await self.search_github(query)
            elif platform == "bilibili":
                results["bilibili"] = await self.search_bilibili(query)
        
        return results


# =============================================================================
# WorldMonitor Integration (舆情监控)
# =============================================================================

class WorldMonitorIntegration:
    """
    WorldMonitor集成 - 实时全球情报仪表板
    功能: 新闻聚合、地缘政治监控、市场追踪、基础设施跟踪
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.base_url = self.config.get("base_url", "http://localhost:3000")
        self.api_key = self.config.get("api_key", "")
        self.enabled = self.config.get("enabled", True)
        
    async def get_news(self, category: str = None, limit: int = 20) -> Dict[str, Any]:
        """获取新闻"""
        try:
            params = {"limit": limit}
            if category:
                params["category"] = category
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/news",
                    params=params,
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "news": []}
        except Exception as e:
            logger.error(f"News fetch error: {e}")
            return {"error": str(e), "news": []}
    
    async def get_trending(self, region: str = "global", limit: int = 50) -> Dict[str, Any]:
        """获取趋势话题"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/trending",
                    params={"region": region, "limit": limit},
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "trending": []}
        except Exception as e:
            logger.error(f"Trending fetch error: {e}")
            return {"error": str(e), "trending": []}
    
    async def get_sentiment(self, topic: str) -> Dict[str, Any]:
        """获取话题情感分析"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/sentiment",
                    params={"topic": topic},
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "sentiment": {}}
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            return {"error": str(e), "sentiment": {}}
    
    async def get_market_data(self, symbols: List[str]) -> Dict[str, Any]:
        """获取市场数据"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/market",
                    params={"symbols": ",".join(symbols)},
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "data": {}}
        except Exception as e:
            logger.error(f"Market data error: {e}")
            return {"error": str(e), "data": {}}
    
    async def get_geopolitical_events(self, region: str = None) -> Dict[str, Any]:
        """获取地缘政治事件"""
        try:
            params = {}
            if region:
                params["region"] = region
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/geopolitical",
                    params=params,
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "events": []}
        except Exception as e:
            logger.error(f"Geopolitical events error: {e}")
            return {"error": str(e), "events": []}


# =============================================================================
# AIRI Integration (虚拟角色)
# =============================================================================

class AIRIIntegration:
    """
    AIRI集成 - 开源AI虚拟角色
    功能: 实时语音聊天、虚拟伴侣、角色扮演、游戏集成
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.base_url = self.config.get("base_url", "http://localhost:5173")
        self.api_key = self.config.get("api_key", "")
        self.enabled = self.config.get("enabled", True)
        self.llm_provider = self.config.get("llm_provider", "openai")
        self.llm_model = self.config.get("llm_model", "gpt-4")
        
    async def chat(self, message: str, character: str = "default", context: Dict[str, Any] = None) -> Dict[str, Any]:
        """与虚拟角色聊天"""
        try:
            payload = {
                "message": message,
                "character": character,
                "context": context or {},
                "llm_provider": self.llm_provider,
                "llm_model": self.llm_model
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "response": ""}
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return {"error": str(e), "response": ""}
    
    async def voice_chat(self, audio_data: bytes, character: str = "default") -> Dict[str, Any]:
        """语音聊天"""
        try:
            form = aiohttp.FormData()
            form.add_field('audio', audio_data, filename='audio.wav', content_type='audio/wav')
            form.add_field('character', character)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/voice/chat",
                    data=form,
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "response": "", "audio": None}
        except Exception as e:
            logger.error(f"Voice chat error: {e}")
            return {"error": str(e), "response": "", "audio": None}
    
    async def set_character(self, character_config: Dict[str, Any]) -> Dict[str, Any]:
        """设置角色配置"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/character",
                    json=character_config,
                    headers={"Authorization": f"Bearer {self.api_key}"}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        return {"error": f"HTTP {resp.status}", "success": False}
        except Exception as e:
            logger.error(f"Character set error: {e}")
            return {"error": str(e), "success": False}


# =============================================================================
# Claude Skills Integration
# =============================================================================

class ClaudeSkillsIntegration:
    """
    Claude Skills集成 - 完整的Claude Skills集合
    分类: 文档处理、开发工具、数据分析、商业营销、沟通写作、创意媒体、效率组织
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.skills_dir = self.config.get("skills_dir", "./external_skills/claude")
        self.enabled = self.config.get("enabled", True)
        
    def get_all_skills(self) -> List[ExternalSkill]:
        """获取所有Claude Skills"""
        skills = []
        
        # 文档处理Skills
        skills.extend([
            ExternalSkill(
                id="doc_summary",
                name="文档摘要",
                description="自动摘要长文档PDF、Word、文本",
                category=ExternalSkillCategory.DOCUMENT_SUMMARY,
                provider="claude",
                required_apis=["pdf_parser", "llm"]
            ),
            ExternalSkill(
                id="doc_translate",
                name="文档翻译",
                description="翻译整篇文档保持格式",
                category=ExternalSkillCategory.DOCUMENT_SUMMARY,
                provider="claude",
                required_apis=["translator", "llm"]
            ),
            ExternalSkill(
                id="doc_qa",
                name="文档问答",
                description="基于文档内容的问答系统",
                category=ExternalSkillCategory.DOCUMENT_SUMMARY,
                provider="claude",
                required_apis=["pdf_parser", "embedding", "llm"]
            ),
        ])
        
        # 开发工具Skills
        skills.extend([
            ExternalSkill(
                id="code_gen",
                name="代码生成",
                description="根据需求生成完整代码",
                category=ExternalSkillCategory.CODE_GENERATION,
                provider="claude",
                required_apis=["llm", "code_executor"]
            ),
            ExternalSkill(
                id="code_review",
                name="代码审查",
                description="自动审查代码问题并提供建议",
                category=ExternalSkillCategory.CODE_REVIEW,
                provider="claude",
                required_apis=["llm", "static_analyzer"]
            ),
            ExternalSkill(
                id="code_refactor",
                name="代码重构",
                description="重构代码提升质量",
                category=ExternalSkillCategory.CODE_GENERATION,
                provider="claude",
                required_apis=["llm"]
            ),
            ExternalSkill(
                id="test_gen",
                name="测试生成",
                description="自动生成单元测试和集成测试",
                category=ExternalSkillCategory.CODE_GENERATION,
                provider="claude",
                required_apis=["llm"]
            ),
            ExternalSkill(
                id="cicd_setup",
                name="CI/CD设置",
                description="自动配置持续集成和部署",
                category=ExternalSkillCategory.CI_CD_AUTOMATION,
                provider="claude",
                required_apis=["llm", "git"]
            ),
            ExternalSkill(
                id="dockerfile_gen",
                name="Docker配置",
                description="生成Dockerfile和docker-compose",
                category=ExternalSkillCategory.CI_CD_AUTOMATION,
                provider="claude",
                required_apis=["llm"]
            ),
        ])
        
        # 数据分析Skills
        skills.extend([
            ExternalSkill(
                id="data_analysis",
                name="数据分析",
                description="分析CSV、Excel、JSON数据",
                category=ExternalSkillCategory.DATA_ANALYSIS,
                provider="claude",
                required_apis=["pandas", "llm"]
            ),
            ExternalSkill(
                id="data_visualize",
                name="数据可视化",
                description="生成图表和数据可视化",
                category=ExternalSkillCategory.VISUALIZATION,
                provider="claude",
                required_apis=["matplotlib", "seaborn", "llm"]
            ),
            ExternalSkill(
                id="report_gen",
                name="报告生成",
                description="生成数据分析报告",
                category=ExternalSkillCategory.REPORT_GENERATION,
                provider="claude",
                required_apis=["llm", "pdf_generator"]
            ),
            ExternalSkill(
                id="sql_query",
                name="SQL查询",
                description="生成和优化SQL查询",
                category=ExternalSkillCategory.DATA_ANALYSIS,
                provider="claude",
                required_apis=["llm", "database"]
            ),
        ])
        
        # 商业营销Skills
        skills.extend([
            ExternalSkill(
                id="market_analysis",
                name="市场分析",
                description="分析市场趋势和竞争情况",
                category=ExternalSkillCategory.DATA_ANALYSIS,
                provider="claude",
                required_apis=["llm", "web_search"]
            ),
            ExternalSkill(
                id="content_marketing",
                name="内容营销",
                description="生成营销文案和内容",
                category=ExternalSkillCategory.REPORT_GENERATION,
                provider="claude",
                required_apis=["llm"]
            ),
            ExternalSkill(
                id="seo_optimize",
                name="SEO优化",
                description="优化网站SEO",
                category=ExternalSkillCategory.WEB_AUTOMATION,
                provider="claude",
                required_apis=["llm"]
            ),
            ExternalSkill(
                id="social_media",
                name="社交媒体",
                description="社交媒体内容生成和发布",
                category=ExternalSkillCategory.COMMUNICATION,
                provider="claude",
                required_apis=["llm", "social_apis"]
            ),
        ])
        
        # 沟通写作Skills
        skills.extend([
            ExternalSkill(
                id="email_write",
                name="邮件撰写",
                description="专业邮件撰写",
                category=ExternalSkillCategory.EMAIL_MANAGEMENT,
                provider="claude",
                required_apis=["llm"]
            ),
            ExternalSkill(
                id="meeting_notes",
                name="会议纪要",
                description="自动生成会议纪要",
                category=ExternalSkillCategory.DOCUMENT_SUMMARY,
                provider="claude",
                required_apis=["llm", "speech_to_text"]
            ),
            ExternalSkill(
                id="resume_builder",
                name="简历生成",
                description="生成专业简历",
                category=ExternalSkillCategory.WRITING,
                provider="claude",
                required_apis=["llm"]
            ),
        ])
        
        # 创意媒体Skills
        skills.extend([
            ExternalSkill(
                id="image_prompt",
                name="提示词生成",
                description="生成AI图像提示词",
                category=ExternalSkillCategory.PROMPT_ENGINEERING,
                provider="claude",
                required_apis=["llm"]
            ),
            ExternalSkill(
                id="video_script",
                name="视频脚本",
                description="生成视频脚本和分镜",
                category=ExternalSkillCategory.WRITING,
                provider="claude",
                required_apis=["llm"]
            ),
            ExternalSkill(
                id="podcast_script",
                name="播客脚本",
                description="生成播客内容脚本",
                category=ExternalSkillCategory.WRITING,
                provider="claude",
                required_apis=["llm"]
            ),
        ])
        
        # 效率组织Skills
        skills.extend([
            ExternalSkill(
                id="task_planning",
                name="任务规划",
                description="智能任务规划和优先级排序",
                category=ExternalSkillCategory.CALENDAR_MANAGEMENT,
                provider="claude",
                required_apis=["llm"]
            ),
            ExternalSkill(
                id="calendar_schedule",
                name="日程安排",
                description="自动安排会议和日程",
                category=ExternalSkillCategory.CALENDAR_MANAGEMENT,
                provider="claude",
                required_apis=["llm", "calendar_api"]
            ),
            ExternalSkill(
                id="note_organize",
                name="笔记整理",
                description="整理和管理笔记",
                category=ExternalSkillCategory.PRODUCTIVITY,
                provider="claude",
                required_apis=["llm", "storage"]
            ),
        ])
        
        return skills


# =============================================================================
# External Skills Manager
# =============================================================================

class ExternalSkillsManager:
    """
    外部Skills管理器 - 统一管理所有外部集成
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.agent_reach = AgentReachIntegration(self.config.get("agent_reach", {}))
        self.world_monitor = WorldMonitorIntegration(self.config.get("world_monitor", {}))
        self.airi = AIRIIntegration(self.config.get("airi", {}))
        self.claude_skills = ClaudeSkillsIntegration(self.config.get("claude_skills", {}))
        
    def get_all_skills(self) -> List[ExternalSkill]:
        """获取所有可用Skills"""
        skills = []
        skills.extend(self.claude_skills.get_all_skills())
        return skills
    
    async def execute_skill(self, skill_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行Skill"""
        # Agent-Reach Skills
        if skill_id == "twitter_search":
            return await self.agent_reach.search_twitter(
                params.get("query", ""),
                params.get("limit", 10)
            )
        elif skill_id == "reddit_search":
            return await self.agent_reach.search_reddit(
                params.get("query", ""),
                params.get("subreddit"),
                params.get("limit", 10)
            )
        elif skill_id == "youtube_search":
            return await self.agent_reach.search_youtube(
                params.get("query", ""),
                params.get("limit", 10)
            )
        elif skill_id == "github_search":
            return await self.agent_reach.search_github(
                params.get("query", ""),
                params.get("repo"),
                params.get("limit", 10)
            )
        elif skill_id == "bilibili_search":
            return await self.agent_reach.search_bilibili(
                params.get("query", ""),
                params.get("limit", 10)
            )
        elif skill_id == "internet_search":
            return await self.agent_reach.search_all(
                params.get("query", ""),
                params.get("platforms")
            )
        
        # WorldMonitor Skills
        elif skill_id == "news_monitor":
            return await self.world_monitor.get_news(
                params.get("category"),
                params.get("limit", 20)
            )
        elif skill_id == "trending":
            return await self.world_monitor.get_trending(
                params.get("region", "global"),
                params.get("limit", 50)
            )
        elif skill_id == "sentiment_analysis":
            return await self.world_monitor.get_sentiment(
                params.get("topic", "")
            )
        elif skill_id == "market_monitor":
            return await self.world_monitor.get_market_data(
                params.get("symbols", [])
            )
        
        # AIRI Skills
        elif skill_id == "virtual_chat":
            return await self.airi.chat(
                params.get("message", ""),
                params.get("character", "default"),
                params.get("context", {})
            )
        elif skill_id == "voice_chat":
            return await self.airi.voice_chat(
                params.get("audio_data", b""),
                params.get("character", "default")
            )
        
        return {"error": f"Unknown skill: {skill_id}"}


# =============================================================================
# Global Instance
# =============================================================================

_external_skills_manager: Optional[ExternalSkillsManager] = None


def get_external_skills_manager(config: Dict[str, Any] = None) -> ExternalSkillsManager:
    """获取外部Skills管理器单例"""
    global _external_skills_manager
    if _external_skills_manager is None:
        _external_skills_manager = ExternalSkillsManager(config)
    return _external_skills_manager


def init_external_skills(config: Dict[str, Any] = None):
    """初始化外部Skills"""
    manager = get_external_skills_manager(config)
    logger.info("External Skills initialized")
    return manager
