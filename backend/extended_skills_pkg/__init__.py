# =============================================================================
# NanoBot Factory - Skills Package
# 完整的Skills生态系统 - 支持所有16个外部链接集成
# =============================================================================

"""
NanoBot Factory Skills Package
=============================

本包包含完整的Skills系统，支持：

1. 互联网搜索Skills (Agent-Reach)
   - Twitter, Reddit, YouTube, GitHub, Bilibili, 小红书等12+平台搜索

2. 舆情监控Skills (WorldMonitor)
   - 新闻监控、社交媒体监控、市场监控、趋势分析、情感分析

3. 虚拟角色Skills (AIRI)
   - 虚拟伴侣、语音聊天、角色扮演

4. Claude Skills集合
   - 代码生成、文档处理、数据分析等20+种技能

5. 微信接入Skills
   - 消息处理、朋友圈监控

6. 浏览器自动化Skills
   - GitHub操作、网页自动化

7. OpenClaw Skills
   - Mac自动化、检查点管理、B站视频转录等

8. 其他Awesome Lists
   - 各种生产力Skills

@author MiniMax Agent
@date 2026-03-08
"""

from .extended_skills import (
    ExtendedSkillManager,
    SkillExecutionEngine,
    SkillCategory,
    AIModel,
    SkillConfig,
    ExecutionResult,
    BaseExtendedSkill,
    # Document Skills
    DocxSkill,
    PdfSkill,
    PptxSkill,
    XlsxSkill,
    # Development Skills
    CodeReviewSkill,
    TddSkill,
    PlaywrightSkill,
    GitSkill,
    # Productivity Skills
    FileOrganizerSkill,
    CalendarSkill,
    EmailSkill,
    TodoistSkill,
    # Monitoring Skills
    NewsAggregatorSkill,
    DataAnalysisSkillExtended,
    PostgresSkill,
    # Communication Skills
    ArticleExtractorSkill,
    BrainstormingSkill,
    ResumeSkill,
    # Creative Skills
    ImageGenerationSkill,
    VideoGenerationSkill,
    YoutubeTranscriptSkill,
    # Security Skills
    SecurityScanSkill,
)

__all__ = [
    "ExtendedSkillManager",
    "SkillExecutionEngine",
    "SkillCategory",
    "AIModel",
    "SkillConfig",
    "ExecutionResult",
    "BaseExtendedSkill",
    # Document Skills
    "DocxSkill",
    "PdfSkill",
    "PptxSkill",
    "XlsxSkill",
    # Development Skills
    "CodeReviewSkill",
    "TddSkill",
    "PlaywrightSkill",
    "GitSkill",
    # Productivity Skills
    "FileOrganizerSkill",
    "CalendarSkill",
    "EmailSkill",
    "TodoistSkill",
    # Monitoring Skills
    "NewsAggregatorSkill",
    "DataAnalysisSkillExtended",
    "PostgresSkill",
    # Communication Skills
    "ArticleExtractorSkill",
    "BrainstormingSkill",
    "ResumeSkill",
    # Creative Skills
    "ImageGenerationSkill",
    "VideoGenerationSkill",
    "YoutubeTranscriptSkill",
    # Security Skills
    "SecurityScanSkill",
]

# 版本信息
__version__ = "2.0.0"
__author__ = "NanoBot Factory Team"
