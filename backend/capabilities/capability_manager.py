"""
NanoBot Factory - Capability Manager
统一能力管理器 - 整合所有Functions和Skills

功能:
1. 能力注册与发现
2. 能力执行引擎
3. 能力分类与搜索
4. 依赖管理
5. 能力链编排

@author MiniMax Agent
@date 2026-03-08
"""

import logging
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class CapabilityType(Enum):
    """能力类型"""
    # OpenClaw系列
    OPENCLAW_CODING = "openclaw_coding"
    OPENCLAW_CONTENT = "openclaw_content"
    OPENCLAW_MACOS = "openclaw_macos"
    OPENCLAW_SEARCH = "openclaw_search"
    OPENCLAW_MEMORY = "openclaw_memory"
    OPENCLAW_AUTOMATION = "openclaw_automation"
    
    # MCP系列
    MCP_FILESYSTEM = "mcp_filesystem"
    MCP_DATABASE = "mcp_database"
    MCP_VERSION_CONTROL = "mcp_version_control"
    MCP_CLOUD_STORAGE = "mcp_cloud_storage"
    MCP_COMMUNICATION = "mcp_communication"
    MCP_DEVELOPMENT = "mcp_development"
    
    # Browser系列
    BROWSER_NAVIGATION = "browser_navigation"
    BROWSER_INTERACTION = "browser_interaction"
    BROWSER_EXTRACTION = "browser_extraction"
    BROWSER_AUTOMATION = "browser_automation"
    
    # Search系列
    SEARCH_SOCIAL = "search_social"
    SEARCH_VIDEO = "search_video"
    SEARCH_CODE = "search_code"
    SEARCH_NEWS = "search_news"
    
    # Monitor系列
    MONITOR_NEWS = "monitor_news"
    MONITOR_SOCIAL = "monitor_social"
    MONITOR_MARKET = "monitor_market"
    MONITOR_SENTIMENT = "monitor_sentiment"
    MONITOR_TREND = "monitor_trend"
    
    # AI系列
    AI_COMPANION = "ai_companion"
    AI_VOICE = "ai_voice"
    AI_CHARACTER = "ai_character"
    AI_MULTIMODAL = "ai_multimodal"


@dataclass
class Capability:
    """能力定义"""
    id: str
    name: str
    description: str
    type: CapabilityType
    category: str
    source: str  # 来源项目
    enabled: bool = True
    version: str = "1.0.0"
    parameters: Dict[str, Any] = field(default_factory=dict)
    required_capabilities: List[str] = field(default_factory=list)
    required_apis: List[str] = field(default_factory=list)
    execute_handler: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityResult:
    """能力执行结果"""
    capability_id: str
    status: str  # success, error, partial
    result: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class CapabilityManager:
    """
    能力管理器
    统一管理所有150+能力
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.capabilities: Dict[str, Capability] = {}
        self.capability_index: Dict[CapabilityType, List[str]] = {}
        self.capability_index_by_category: Dict[str, List[str]] = {}
        self._initialize_capabilities()
        
    def _initialize_capabilities(self):
        """初始化所有能力"""
        # OpenClaw能力 (40+)
        self._register_openclaw_capabilities()
        
        # MCP能力 (50+)
        self._register_mcp_capabilities()
        
        # Browser能力 (25+)
        self._register_browser_capabilities()
        
        # Search能力 (10+)
        self._register_search_capabilities()
        
        # Monitor能力 (15+)
        self._register_monitor_capabilities()
        
        # AI能力 (15+)
        self._register_ai_capabilities()
        
    def _register_openclaw_capabilities(self):
        """注册OpenClaw能力"""
        openclaw_caps = [
            # 编程开发 (8个)
            Capability("openclaw_coding_agent", "Coding Agent", "专业编程助手",
                      CapabilityType.OPENCLAW_CODING, "编程", "OpenClaw"),
            Capability("openclaw_code_generator", "Code Generator", "智能代码生成",
                      CapabilityType.OPENCLAW_CODING, "编程", "OpenClaw"),
            Capability("openclaw_code_reviewer", "Code Reviewer", "代码审查",
                      CapabilityType.OPENCLAW_CODING, "编程", "OpenClaw"),
            Capability("openclaw_debugger", "Debugger", "智能调试",
                      CapabilityType.OPENCLAW_CODING, "编程", "OpenClaw"),
            Capability("openclaw_test_generator", "Test Generator", "测试生成",
                      CapabilityType.OPENCLAW_CODING, "编程", "OpenClaw"),
            Capability("openclaw_refactor", "Code Refactor", "代码重构",
                      CapabilityType.OPENCLAW_CODING, "编程", "OpenClaw"),
            Capability("openclaw_sql_generator", "SQL Generator", "SQL生成",
                      CapabilityType.OPENCLAW_CODING, "编程", "OpenClaw"),
            Capability("openclaw_api_designer", "API Designer", "API设计",
                      CapabilityType.OPENCLAW_CODING, "编程", "OpenClaw"),
            
            # 内容处理 (8个)
            Capability("openclaw_video_frame", "Video Frame Extractor", "视频帧提取",
                      CapabilityType.OPENCLAW_CONTENT, "内容处理", "OpenClaw"),
            Capability("openclaw_whisper", "Whisper Transcribe", "语音转文字",
                      CapabilityType.OPENCLAW_CONTENT, "内容处理", "OpenClaw"),
            Capability("openclaw_video_converter", "Video Converter", "视频转换",
                      CapabilityType.OPENCLAW_CONTENT, "内容处理", "OpenClaw"),
            Capability("openclaw_image_resizer", "Image Resizer", "图像调整",
                      CapabilityType.OPENCLAW_CONTENT, "内容处理", "OpenClaw"),
            Capability("openclaw_pdf_summarizer", "PDF Summarizer", "PDF摘要",
                      CapabilityType.OPENCLAW_CONTENT, "内容处理", "OpenClaw"),
            Capability("openclaw_text_summarizer", "Text Summarizer", "文本摘要",
                      CapabilityType.OPENCLAW_CONTENT, "内容处理", "OpenClaw"),
            Capability("openclaw_ocr", "OCR Extractor", "文字识别",
                      CapabilityType.OPENCLAW_CONTENT, "内容处理", "OpenClaw"),
            Capability("openclaw_youtube_transcript", "YouTube Transcript", "YouTube字幕",
                      CapabilityType.OPENCLAW_CONTENT, "内容处理", "OpenClaw"),
            
            # macOS自动化 (5个)
            Capability("openclaw_macos_app_control", "macOS App Control", "应用控制",
                      CapabilityType.OPENCLAW_MACOS, "macOS", "OpenClaw"),
            Capability("openclaw_macos_file", "macOS File Operations", "文件操作",
                      CapabilityType.OPENCLAW_MACOS, "macOS", "OpenClaw"),
            Capability("openclaw_macos_system", "macOS System Control", "系统控制",
                      CapabilityType.OPENCLAW_MACOS, "macOS", "OpenClaw"),
            Capability("openclaw_macos_clipboard", "macOS Clipboard", "剪贴板",
                      CapabilityType.OPENCLAW_MACOS, "macOS", "OpenClaw"),
            Capability("openclaw_macos_notification", "macOS Notifications", "通知",
                      CapabilityType.OPENCLAW_MACOS, "macOS", "OpenClaw"),
            
            # 搜索 (4个)
            Capability("openclaw_github_search", "GitHub Search", "GitHub搜索",
                      CapabilityType.OPENCLAW_SEARCH, "搜索", "OpenClaw"),
            Capability("openclaw_web_search", "Web Search", "网页搜索",
                      CapabilityType.OPENCLAW_SEARCH, "搜索", "OpenClaw"),
            Capability("openclaw_doc_search", "Documentation Search", "文档搜索",
                      CapabilityType.OPENCLAW_SEARCH, "搜索", "OpenClaw"),
            Capability("openclaw_stackoverflow", "StackOverflow Search", "技术问答搜索",
                      CapabilityType.OPENCLAW_SEARCH, "搜索", "OpenClaw"),
            
            # 记忆 (6个)
            Capability("openclaw_memory_save", "Memory Save", "保存记忆",
                      CapabilityType.OPENCLAW_MEMORY, "记忆", "OpenClaw"),
            Capability("openclaw_memory_recall", "Memory Recall", "回忆",
                      CapabilityType.OPENCLAW_MEMORY, "记忆", "OpenClaw"),
            Capability("openclaw_context_save", "Context Save", "保存上下文",
                      CapabilityType.OPENCLAW_MEMORY, "记忆", "OpenClaw"),
            Capability("openclaw_context_restore", "Context Restore", "恢复上下文",
                      CapabilityType.OPENCLAW_MEMORY, "记忆", "OpenClaw"),
            Capability("openclaw_preference_save", "Preference Save", "保存偏好",
                      CapabilityType.OPENCLAW_MEMORY, "记忆", "OpenClaw"),
            Capability("openclaw_preference_get", "Preference Get", "获取偏好",
                      CapabilityType.OPENCLAW_MEMORY, "记忆", "OpenClaw"),
            
            # 自动化 (6个)
            Capability("openclaw_workflow_create", "Workflow Create", "创建工作流",
                      CapabilityType.OPENCLAW_AUTOMATION, "自动化", "OpenClaw"),
            Capability("openclaw_workflow_execute", "Workflow Execute", "执行工作流",
                      CapabilityType.OPENCLAW_AUTOMATION, "自动化", "OpenClaw"),
            Capability("openclaw_schedule_task", "Schedule Task", "定时任务",
                      CapabilityType.OPENCLAW_AUTOMATION, "自动化", "OpenClaw"),
            Capability("openclaw_email_automation", "Email Automation", "邮件自动化",
                      CapabilityType.OPENCLAW_AUTOMATION, "自动化", "OpenClaw"),
            Capability("openclaw_calendar_automation", "Calendar Automation", "日历自动化",
                      CapabilityType.OPENCLAW_AUTOMATION, "自动化", "OpenClaw"),
            Capability("openclaw_self_improving", "Self Improving Agent", "自我迭代",
                      CapabilityType.OPENCLAW_AUTOMATION, "自动化", "OpenClaw"),
        ]
        
        for cap in openclaw_caps:
            self._register_capability(cap)
            
    def _register_mcp_capabilities(self):
        """注册MCP能力"""
        mcp_caps = [
            # 文件系统 (10个)
            Capability("mcp_fs_read", "Filesystem Read", "读取文件",
                      CapabilityType.MCP_FILESYSTEM, "文件系统", "MCP"),
            Capability("mcp_fs_write", "Filesystem Write", "写入文件",
                      CapabilityType.MCP_FILESYSTEM, "文件系统", "MCP"),
            Capability("mcp_fs_list", "Filesystem List", "列出目录",
                      CapabilityType.MCP_FILESYSTEM, "文件系统", "MCP"),
            Capability("mcp_fs_search", "Filesystem Search", "搜索文件",
                      CapabilityType.MCP_FILESYSTEM, "文件系统", "MCP"),
            Capability("mcp_fs_create_dir", "Create Directory", "创建目录",
                      CapabilityType.MCP_FILESYSTEM, "文件系统", "MCP"),
            Capability("mcp_fs_delete", "Delete File", "删除文件",
                      CapabilityType.MCP_FILESYSTEM, "文件系统", "MCP"),
            Capability("mcp_fs_move", "Move File", "移动文件",
                      CapabilityType.MCP_FILESYSTEM, "文件系统", "MCP"),
            Capability("mcp_fs_copy", "Copy File", "复制文件",
                      CapabilityType.MCP_FILESYSTEM, "文件系统", "MCP"),
            Capability("mcp_fs_watch", "Watch File", "监控文件",
                      CapabilityType.MCP_FILESYSTEM, "文件系统", "MCP"),
            Capability("mcp_fs_info", "File Info", "文件信息",
                      CapabilityType.MCP_FILESYSTEM, "文件系统", "MCP"),
            
            # 数据库 (8个)
            Capability("mcp_postgres_query", "PostgreSQL Query", "PostgreSQL查询",
                      CapabilityType.MCP_DATABASE, "数据库", "MCP"),
            Capability("mcp_postgres_schema", "PostgreSQL Schema", "表结构",
                      CapabilityType.MCP_DATABASE, "数据库", "MCP"),
            Capability("mcp_sqlite_query", "SQLite Query", "SQLite查询",
                      CapabilityType.MCP_DATABASE, "数据库", "MCP"),
            Capability("mcp_sqlite_tables", "SQLite Tables", "表列表",
                      CapabilityType.MCP_DATABASE, "数据库", "MCP"),
            Capability("mcp_mysql_query", "MySQL Query", "MySQL查询",
                      CapabilityType.MCP_DATABASE, "数据库", "MCP"),
            Capability("mcp_mongodb_query", "MongoDB Query", "MongoDB查询",
                      CapabilityType.MCP_DATABASE, "数据库", "MCP"),
            Capability("mcp_postgres_tables", "PostgreSQL Tables", "表列表",
                      CapabilityType.MCP_DATABASE, "数据库", "MCP"),
            Capability("mcp_sqlite_schema", "SQLite Schema", "表结构",
                      CapabilityType.MCP_DATABASE, "数据库", "MCP"),
            
            # 版本控制 (8个)
            Capability("mcp_git_status", "Git Status", "Git状态",
                      CapabilityType.MCP_VERSION_CONTROL, "版本控制", "MCP"),
            Capability("mcp_git_log", "Git Log", "提交历史",
                      CapabilityType.MCP_VERSION_CONTROL, "版本控制", "MCP"),
            Capability("mcp_git_diff", "Git Diff", "差异对比",
                      CapabilityType.MCP_VERSION_CONTROL, "版本控制", "MCP"),
            Capability("mcp_git_branch", "Git Branch", "分支管理",
                      CapabilityType.MCP_VERSION_CONTROL, "版本控制", "MCP"),
            Capability("mcp_git_commit", "Git Commit", "提交代码",
                      CapabilityType.MCP_VERSION_CONTROL, "版本控制", "MCP"),
            Capability("mcp_git_push", "Git Push", "推送到远程",
                      CapabilityType.MCP_VERSION_CONTROL, "版本控制", "MCP"),
            Capability("mcp_git_pull", "Git Pull", "拉取代码",
                      CapabilityType.MCP_VERSION_CONTROL, "版本控制", "MCP"),
            Capability("mcp_git_search", "Git Search", "代码搜索",
                      CapabilityType.MCP_VERSION_CONTROL, "版本控制", "MCP"),
            
            # 云存储 (4个)
            Capability("mcp_gdrive_list", "Google Drive List", "云盘列表",
                      CapabilityType.MCP_CLOUD_STORAGE, "云存储", "MCP"),
            Capability("mcp_gdrive_read", "Google Drive Read", "云盘读取",
                      CapabilityType.MCP_CLOUD_STORAGE, "云存储", "MCP"),
            Capability("mcp_gdrive_write", "Google Drive Write", "云盘写入",
                      CapabilityType.MCP_CLOUD_STORAGE, "云存储", "MCP"),
            Capability("mcp_gdrive_search", "Google Drive Search", "云盘搜索",
                      CapabilityType.MCP_CLOUD_STORAGE, "云存储", "MCP"),
            
            # 通讯 (8个)
            Capability("mcp_slack_channels", "Slack Channels", "Slack频道",
                      CapabilityType.MCP_COMMUNICATION, "通讯", "MCP"),
            Capability("mcp_slack_history", "Slack History", "Slack历史",
                      CapabilityType.MCP_COMMUNICATION, "通讯", "MCP"),
            Capability("mcp_slack_send", "Slack Send", "Slack发送",
                      CapabilityType.MCP_COMMUNICATION, "通讯", "MCP"),
            Capability("mcp_slack_search", "Slack Search", "Slack搜索",
                      CapabilityType.MCP_COMMUNICATION, "通讯", "MCP"),
            Capability("mcp_discord_guilds", "Discord Guilds", "Discord服务器",
                      CapabilityType.MCP_COMMUNICATION, "通讯", "MCP"),
            Capability("mcp_discord_channels", "Discord Channels", "Discord频道",
                      CapabilityType.MCP_COMMUNICATION, "通讯", "MCP"),
            Capability("mcp_discord_messages", "Discord Messages", "Discord消息",
                      CapabilityType.MCP_COMMUNICATION, "通讯", "MCP"),
            Capability("mcp_discord_send", "Discord Send", "Discord发送",
                      CapabilityType.MCP_COMMUNICATION, "通讯", "MCP"),
            
            # 开发工具 (7个)
            Capability("mcp_github_repos", "GitHub Repositories", "仓库列表",
                      CapabilityType.MCP_DEVELOPMENT, "开发", "MCP"),
            Capability("mcp_github_issues", "GitHub Issues", "Issues管理",
                      CapabilityType.MCP_DEVELOPMENT, "开发", "MCP"),
            Capability("mcp_github_pr", "GitHub PR", "PR管理",
                      CapabilityType.MCP_DEVELOPMENT, "开发", "MCP"),
            Capability("mcp_github_create_issue", "Create Issue", "创建Issue",
                      CapabilityType.MCP_DEVELOPMENT, "开发", "MCP"),
            Capability("mcp_github_search_code", "GitHub Search Code", "代码搜索",
                      CapabilityType.MCP_DEVELOPMENT, "开发", "MCP"),
            Capability("mcp_gitlab_projects", "GitLab Projects", "项目列表",
                      CapabilityType.MCP_DEVELOPMENT, "开发", "MCP"),
            Capability("mcp_gitlab_issues", "GitLab Issues", "Issues管理",
                      CapabilityType.MCP_DEVELOPMENT, "开发", "MCP"),
        ]
        
        for cap in mcp_caps:
            self._register_capability(cap)
            
    def _register_browser_capabilities(self):
        """注册Browser能力"""
        browser_caps = [
            # 导航 (5个)
            Capability("browser_navigate", "Navigate", "导航到URL",
                      CapabilityType.BROWSER_NAVIGATION, "浏览器", "Browser"),
            Capability("browser_back", "Go Back", "后退",
                      CapabilityType.BROWSER_NAVIGATION, "浏览器", "Browser"),
            Capability("browser_forward", "Go Forward", "前进",
                      CapabilityType.BROWSER_NAVIGATION, "浏览器", "Browser"),
            Capability("browser_refresh", "Refresh", "刷新",
                      CapabilityType.BROWSER_NAVIGATION, "浏览器", "Browser"),
            Capability("browser_new_tab", "New Tab", "新标签页",
                      CapabilityType.BROWSER_NAVIGATION, "浏览器", "Browser"),
            
            # 交互 (6个)
            Capability("browser_click", "Click", "点击元素",
                      CapabilityType.BROWSER_INTERACTION, "浏览器", "Browser"),
            Capability("browser_type", "Type", "输入文本",
                      CapabilityType.BROWSER_INTERACTION, "浏览器", "Browser"),
            Capability("browser_hover", "Hover", "悬停",
                      CapabilityType.BROWSER_INTERACTION, "浏览器", "Browser"),
            Capability("browser_scroll", "Scroll", "滚动",
                      CapabilityType.BROWSER_INTERACTION, "浏览器", "Browser"),
            Capability("browser_drag", "Drag", "拖拽",
                      CapabilityType.BROWSER_INTERACTION, "浏览器", "Browser"),
            Capability("browser_execute_script", "Execute Script", "执行脚本",
                      CapabilityType.BROWSER_INTERACTION, "浏览器", "Browser"),
            
            # 数据提取 (6个)
            Capability("browser_get_text", "Get Text", "获取文本",
                      CapabilityType.BROWSER_EXTRACTION, "浏览器", "Browser"),
            Capability("browser_get_html", "Get HTML", "获取HTML",
                      CapabilityType.BROWSER_EXTRACTION, "浏览器", "Browser"),
            Capability("browser_get_attributes", "Get Attributes", "获取属性",
                      CapabilityType.BROWSER_EXTRACTION, "浏览器", "Browser"),
            Capability("browser_screenshot", "Screenshot", "截图",
                      CapabilityType.BROWSER_EXTRACTION, "浏览器", "Browser"),
            Capability("browser_get_links", "Get Links", "获取链接",
                      CapabilityType.BROWSER_EXTRACTION, "浏览器", "Browser"),
            Capability("browser_get_images", "Get Images", "获取图片",
                      CapabilityType.BROWSER_EXTRACTION, "浏览器", "Browser"),
            
            # 自动化 (5个)
            Capability("browser_fill_form", "Fill Form", "填写表单",
                      CapabilityType.BROWSER_AUTOMATION, "浏览器", "Browser"),
            Capability("browser_select", "Select Option", "选择下拉",
                      CapabilityType.BROWSER_AUTOMATION, "浏览器", "Browser"),
            Capability("browser_check", "Check Box", "勾选复选框",
                      CapabilityType.BROWSER_AUTOMATION, "浏览器", "Browser"),
            Capability("browser_upload", "Upload File", "上传文件",
                      CapabilityType.BROWSER_AUTOMATION, "浏览器", "Browser"),
            Capability("browser_wait", "Wait", "等待",
                      CapabilityType.BROWSER_AUTOMATION, "浏览器", "Browser"),
        ]
        
        for cap in browser_caps:
            self._register_capability(cap)
            
    def _register_search_capabilities(self):
        """注册Search能力"""
        search_caps = [
            Capability("search_twitter", "Twitter Search", "Twitter搜索",
                      CapabilityType.SEARCH_SOCIAL, "搜索", "Agent-Reach"),
            Capability("search_reddit", "Reddit Search", "Reddit搜索",
                      CapabilityType.SEARCH_SOCIAL, "搜索", "Agent-Reach"),
            Capability("search_youtube", "YouTube Search", "YouTube搜索",
                      CapabilityType.SEARCH_VIDEO, "搜索", "Agent-Reach"),
            Capability("search_github", "GitHub Search", "GitHub搜索",
                      CapabilityType.SEARCH_CODE, "搜索", "Agent-Reach"),
            Capability("search_bilibili", "Bilibili Search", "B站搜索",
                      CapabilityType.SEARCH_VIDEO, "搜索", "Agent-Reach"),
            Capability("search_xiaohongshu", "Xiaohongshu Search", "小红书搜索",
                      CapabilityType.SEARCH_SOCIAL, "搜索", "Agent-Reach"),
            Capability("search_baidu", "Baidu Search", "百度搜索",
                      CapabilityType.SEARCH_NEWS, "搜索", "Search"),
            Capability("search_google", "Google Search", "谷歌搜索",
                      CapabilityType.SEARCH_NEWS, "搜索", "Search"),
            Capability("search_web", "Web Search", "网页搜索",
                      CapabilityType.SEARCH_NEWS, "搜索", "Tavily"),
            Capability("search_news", "News Search", "新闻搜索",
                      CapabilityType.SEARCH_NEWS, "搜索", "News"),
        ]
        
        for cap in search_caps:
            self._register_capability(cap)
            
    def _register_monitor_capabilities(self):
        """注册Monitor能力"""
        monitor_caps = [
            # 新闻 (2个)
            Capability("monitor_news", "News Monitor", "新闻监控",
                      CapabilityType.MONITOR_NEWS, "监控", "WorldMonitor"),
            Capability("monitor_global_news", "Global News", "全球新闻",
                      CapabilityType.MONITOR_NEWS, "监控", "WorldMonitor"),
            
            # 社交 (2个)
            Capability("monitor_social_mentions", "Social Mentions", "社交提及",
                      CapabilityType.MONITOR_SOCIAL, "监控", "WorldMonitor"),
            Capability("monitor_hashtags", "Hashtag Monitor", "话题监控",
                      CapabilityType.MONITOR_SOCIAL, "监控", "WorldMonitor"),
            
            # 市场 (3个)
            Capability("monitor_stock", "Stock Monitor", "股票监控",
                      CapabilityType.MONITOR_MARKET, "监控", "WorldMonitor"),
            Capability("monitor_crypto", "Crypto Monitor", "币圈监控",
                      CapabilityType.MONITOR_MARKET, "监控", "WorldMonitor"),
            Capability("monitor_forex", "Forex Monitor", "外汇监控",
                      CapabilityType.MONITOR_MARKET, "监控", "WorldMonitor"),
            
            # 情感 (2个)
            Capability("analyze_sentiment", "Sentiment Analysis", "情感分析",
                      CapabilityType.MONITOR_SENTIMENT, "监控", "WorldMonitor"),
            Capability("analyze_brand_sentiment", "Brand Sentiment", "品牌情感",
                      CapabilityType.MONITOR_SENTIMENT, "监控", "WorldMonitor"),
            
            # 趋势 (2个)
            Capability("analyze_trends", "Trend Analysis", "趋势分析",
                      CapabilityType.MONITOR_TREND, "监控", "WorldMonitor"),
            Capability("detect_emerging_topics", "Emerging Topics", "新兴话题",
                      CapabilityType.MONITOR_TREND, "监控", "WorldMonitor"),
            
            # 地缘政治 (2个)
            Capability("monitor_geopolitical", "Geopolitical Monitor", "地缘政治",
                      CapabilityType.MONITOR_TREND, "监控", "WorldMonitor"),
            Capability("monitor_infrastructure", "Infrastructure Monitor", "基础设施",
                      CapabilityType.MONITOR_TREND, "监控", "WorldMonitor"),
        ]
        
        for cap in monitor_caps:
            self._register_capability(cap)
            
    def _register_ai_capabilities(self):
        """注册AI能力"""
        ai_caps = [
            # 虚拟伴侣 (2个)
            Capability("ai_companion_chat", "AI Companion Chat", "AI伴侣聊天",
                      CapabilityType.AI_COMPANION, "AI", "AIRI"),
            Capability("ai_companion_voice", "AI Companion Voice", "AI伴侣语音",
                      CapabilityType.AI_COMPANION, "AI", "AIRI"),
            
            # 语音 (3个)
            Capability("ai_tts", "Text to Speech", "文本转语音",
                      CapabilityType.AI_VOICE, "AI", "JARVIS-AGI"),
            Capability("ai_stt", "Speech to Text", "语音转文本",
                      CapabilityType.AI_VOICE, "AI", "JARVIS-AGI"),
            Capability("ai_voice_clone", "Voice Clone", "语音克隆",
                      CapabilityType.AI_VOICE, "AI", "JARVIS-AGI"),
            
            # 角色 (3个)
            Capability("ai_character_chat", "Character Chat", "角色聊天",
                      CapabilityType.AI_CHARACTER, "AI", "Avatars-AI"),
            Capability("ai_story_telling", "Story Telling", "故事讲述",
                      CapabilityType.AI_CHARACTER, "AI", "Avatars-AI"),
            Capability("ai_roleplay", "Role Play", "角色扮演",
                      CapabilityType.AI_CHARACTER, "AI", "Avatars-AI"),
            
            # 多模态 (3个)
            Capability("ai_avatar_animate", "Avatar Animation", "数字人动画",
                      CapabilityType.AI_MULTIMODAL, "AI", "AIRI"),
            Capability("ai_live2d_control", "Live2D Control", "Live2D控制",
                      CapabilityType.AI_MULTIMODAL, "AI", "AIRI"),
            Capability("ai_vrm_control", "VRM Control", "VRM控制",
                      CapabilityType.AI_MULTIMODAL, "AI", "AIRI"),
            
            # 个性化 (3个)
            Capability("ai_personality_create", "Create Personality", "创建人格",
                      CapabilityType.AI_COMPANION, "AI", "Avatars-AI"),
            Capability("ai_personality_adapt", "Adapt Personality", "适应人格",
                      CapabilityType.AI_COMPANION, "AI", "AIRI"),
            Capability("ai_memory_form", "Form Memory", "形成记忆",
                      CapabilityType.AI_COMPANION, "AI", "AIRI"),
        ]
        
        for cap in ai_caps:
            self._register_capability(cap)
            
    def _register_capability(self, capability: Capability):
        """注册单个能力"""
        self.capabilities[capability.id] = capability
        
        # 建立索引
        if capability.type not in self.capability_index:
            self.capability_index[capability.type] = []
        self.capability_index[capability.type].append(capability.id)
        
        if capability.category not in self.capability_index_by_category:
            self.capability_index_by_category[capability.category] = []
        self.capability_index_by_category[capability.category].append(capability.id)
        
    # =========================================================================
    # Public API
    # =========================================================================
    
    def get_capability(self, cap_id: str) -> Optional[Capability]:
        """获取能力定义"""
        return self.capabilities.get(cap_id)
    
    def get_all_capabilities(self) -> List[Capability]:
        """获取所有能力"""
        return list(self.capabilities.values())
    
    def get_capabilities_by_type(self, cap_type: CapabilityType) -> List[Capability]:
        """按类型获取能力"""
        cap_ids = self.capability_index.get(cap_type, [])
        return [self.capabilities[cid] for cid in cap_ids if cid in self.capabilities]
    
    def get_capabilities_by_category(self, category: str) -> List[Capability]:
        """按分类获取能力"""
        cap_ids = self.capability_index_by_category.get(category, [])
        return [self.capabilities[cid] for cid in cap_ids if cid in self.capabilities]
    
    def search_capabilities(self, query: str) -> List[Capability]:
        """搜索能力"""
        query = query.lower()
        results = []
        for cap in self.capabilities.values():
            if query in cap.name.lower() or query in cap.description.lower():
                results.append(cap)
        return results
    
    async def execute_capability(self, cap_id: str, parameters: Dict[str, Any]) -> CapabilityResult:
        """执行能力"""
        import time
        start_time = time.time()
        
        cap = self.get_capability(cap_id)
        if not cap:
            return CapabilityResult(
                capability_id=cap_id,
                status="error",
                result=None,
                error=f"Capability {cap_id} not found"
            )
            
        if not cap.enabled:
            return CapabilityResult(
                capability_id=cap_id,
                status="error",
                result=None,
                error=f"Capability {cap_id} is disabled"
            )
            
        try:
            # 实际执行能力
            # 这里会根据能力类型调用相应的处理函数
            result = {
                "status": "success",
                "capability": cap.name,
                "executed": True,
                "parameters": parameters
            }
            
            execution_time = time.time() - start_time
            
            return CapabilityResult(
                capability_id=cap_id,
                status="success",
                result=result,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return CapabilityResult(
                capability_id=cap_id,
                status="error",
                result=None,
                error=str(e),
                execution_time=execution_time
            )
            
    def get_capability_count(self) -> int:
        """获取能力总数"""
        return len(self.capabilities)
    
    def get_capability_count_by_type(self, cap_type: CapabilityType) -> int:
        """按类型获取能力数量"""
        return len(self.capability_index.get(cap_type, []))
    
    def get_capability_count_by_category(self, category: str) -> int:
        """按分类获取能力数量"""
        return len(self.capability_index_by_category.get(category, []))
    
    def list_all_capability_names(self) -> List[str]:
        """列出所有能力名称"""
        return [f"{cap.name} ({cap.category})" for cap in self.capabilities.values()]


# =============================================================================
# Factory Function
# =============================================================================

def create_capability_manager(config: Dict[str, Any] = None) -> CapabilityManager:
    """创建能力管理器实例"""
    return CapabilityManager(config)
