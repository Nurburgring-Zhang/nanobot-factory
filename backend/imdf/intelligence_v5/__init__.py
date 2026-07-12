"""智影 V5 — 完整能力包: Identity / Memory / Collaboration / Harness / Skills / MoA / Scheduler / Video / Brand / Data / Roles / MCP / Proactive / Monitor / Geo / Profile / Perf

迁移自 8 大开源项目:
1. Meta Kim — 模糊意图决策
2. Claude Code — Agentic Loop (看上下文→做动作→验证)
3. Hermes Agent — Bot/Channel/Thread/Matter + 6 协作 + MoA + Cron/Webhook
4. Loop Engineering (Anthropic) — Full Harness Planner+Generator+Evaluator
5. Obsidian-cc — 6 大技能 + Memory Palace + 3 层文件分层
6. Agnes AI / Pavo — 全模态免费 + 短剧 Harness
7. Gooseworks — 4 广告研究技能 + 100+ 数据源
8. The Agency — 232 Agent 角色
9. Vida (Proactive Agent) — 持续上下文 + 主动建议
10. Bugu — macOS 状态监控
11. Octo — 6 协作模式 + O.C.T.O
12. China Pins — MapLibre + Terrarium DEM
13. Hermes setup --portal — User/Agent Profile
14. Hermes perf — 上下文压缩 + 提示缓存 (10s → 1s)
15. RedFox — 13 平台数据 API
16. Comfy MCP — MCP 协议接入
"""
__version__ = "5.0.0"

# Identity
from .identity import (
    Bot, AgentCard, BotCapability, BotRegistry, BotStatus, BotRole, bot_registry,
    Channel, ChannelKind, ChannelMember,
    Thread, ThreadMessage, ThreadStatus,
    Matter, MatterStatus, AcceptanceCriteria, DeliveryRecord,
)

# Memory
from .memory import (
    MemoryLayer, RawStore, SourceStore, LongTermStore, InboxStore, FeedbackStore,
    TrustLevel, MemoryItem, MemoryQuery, memory_manager,
    PalaceRoom, PalaceCard, PalaceRouter, palace_router,
    FeedbackSignal, FeedbackType, FeedbackCollector, TasteExtractor, ProfileUpdater, feedback_loop,
)

# Collaboration
from .collaboration import (
    CollaborationMode, CollaborationSession,
    SoloSession, RoundtableSession, CriticSession, PipelineSession, SplitSession, SwarmSession,
    CollaborationContext, CollaborationResult, CollaborationEngine, collaboration_engine,
)

# Harness (Loop Engineering)
from .harness import (
    Planner, SprintPlan, PlannerStep, StepType,
    Generator, GeneratorOutput, ImplementationSprint, FileArtifact, SprintStatus,
    Evaluator, EvaluationResult, EvaluationCriteria, CriterionStatus, CriterionType,
    HarnessEngine, HarnessConfig, HarnessRun, HarnessState, harness_engine,
)

# Skills (Obsidian 6)
from .skills import (
    ObsidianSkill, SkillResult,
    DigestNoteSkill, ReviewInboxSkill, ApplyMemorySkill,
    UpdateProfileSkill, VaultDoctorSkill, CreateSkillSkill,
    obsidian_skill_registry,
)

# MoA
from .moa import (
    MoAEngine, MoAConfig, MoAReference, MoAResult, MoAMode, moa_engine,
)

# Scheduler (Cron + Webhook)
from .scheduler import (
    CronParser, CronJob, CronScheduler, cron_scheduler,
    WebhookServer, WebhookEndpoint, WebhookEvent, webhook_server,
    GoalRunner, GoalDefinition, GoalStatus, goal_runner,
    Board, BoardColumn, BoardItem, BoardStatus,
)

# Video Harness (Pavo + 剧大虾)
from .video_harness import (
    ProjectCard, ProjectType, CardSection,
    CharacterDesigner, Character, Scene, Prop,
    StoryboardEngine, Storyboard, Shot, ShotType, CameraMovement,
    ModelRouter, ModelInfo, ModelCapability, RoutingDecision,
    VideoHarness, HarnessStep, HarnessPhase, VideoProject, video_harness,
)

# Brand Research (Gooseworks 4)
from .brand_research import (
    AdSource, MetaAdLibrary, GoogleAdsTransparency, XMonitor, RedditMonitor,
    TrendingHookSpotter, HookCategory, TrendingHook,
    CompetitorAdIntelligence, CompetitorAd, AdCluster,
    AdAngleMiner, ConversionAngle, MiningSource,
    BrandResearcher, BrandProfile, BrandContext,
)

# Data Gateway (RedFox 13 平台)
from .data_gateway import (
    Platform, PlatformRegistry, platform_registry, DataCategory, DataItem,
    DataGatewayClient, DataGatewayConfig, data_gateway,
)

# Roles (The Agency 232)
from .roles import (
    Department, DEPARTMENTS, ROLES_DATABASE,
    RoleDefinition, RoleCategory, RoleExpressionTone,
    RoleWorkflow, RoleDeliverable, RoleMetrics, role_registry,
)

# MCP (Comfy MCP)
from .mcp import (
    MCPServer, MCPTool, MCPResource, MCPPrompt, MCPMessage,
    JSONRPCRequest, JSONRPCResponse, mcp_server,
    MCPToolRegistry, ToolParameter, ToolResult, tool_registry,
)

# Proactive (Vida)
from .proactive import (
    ProactiveEngine, ProactiveContext, ProactiveAction, ContextSnapshot, DailyReport, proactive_engine,
)

# Monitor (Bugu)
from .monitor import (
    AgentStatus, TaskMonitor, HeartbeatEvent, HeartbeatSound, StatusMonitor, status_monitor,
)

# Geo (MapLibre + Terrarium DEM)
from .geo import (
    DEMTileFetcher, terrarium_decode, terrarium_encode, TerrainBaker, ElevationStops, HillshadeGenerator, LandMaskGenerator,
    TileExporter, WebPTile, TileBounds, tile_exporter,
    GeoProject, MapStyle, PinPoint, Chapter, geo_engine,
)

# Profile (Hermes setup --portal)
from .profile import (
    UserProfile, ProfileManager, profile_manager,
    AgentProfileTemplate, AGENT_PROFILE_TEMPLATES,
)

# Perf (Hermes 10s → 1s)
from .perf import (
    CompressionStrategy, CompressionResult, PromptCache, CacheEntry, ContextCompressor,
    prompt_cache, context_compressor,
)

__all__ = [
    # Identity
    "Bot", "AgentCard", "BotCapability", "BotRegistry", "BotStatus", "BotRole", "bot_registry",
    "Channel", "ChannelKind", "ChannelMember",
    "Thread", "ThreadMessage", "ThreadStatus",
    "Matter", "MatterStatus", "AcceptanceCriteria", "DeliveryRecord",
    # Memory
    "MemoryLayer", "RawStore", "SourceStore", "LongTermStore", "InboxStore", "FeedbackStore",
    "TrustLevel", "MemoryItem", "MemoryQuery", "memory_manager",
    "PalaceRoom", "PalaceCard", "PalaceRouter", "palace_router",
    "FeedbackSignal", "FeedbackType", "FeedbackCollector", "TasteExtractor", "ProfileUpdater", "feedback_loop",
    # Collaboration
    "CollaborationMode", "CollaborationSession",
    "SoloSession", "RoundtableSession", "CriticSession", "PipelineSession", "SplitSession", "SwarmSession",
    "CollaborationContext", "CollaborationResult", "CollaborationEngine", "collaboration_engine",
    # Harness
    "Planner", "SprintPlan", "PlannerStep", "StepType",
    "Generator", "GeneratorOutput", "ImplementationSprint", "FileArtifact", "SprintStatus",
    "Evaluator", "EvaluationResult", "EvaluationCriteria", "CriterionStatus", "CriterionType",
    "HarnessEngine", "HarnessConfig", "HarnessRun", "HarnessState", "harness_engine",
    # Skills
    "ObsidianSkill", "SkillResult",
    "DigestNoteSkill", "ReviewInboxSkill", "ApplyMemorySkill",
    "UpdateProfileSkill", "VaultDoctorSkill", "CreateSkillSkill",
    "obsidian_skill_registry",
    # MoA
    "MoAEngine", "MoAConfig", "MoAReference", "MoAResult", "MoAMode", "moa_engine",
    # Scheduler
    "CronParser", "CronJob", "CronScheduler", "cron_scheduler",
    "WebhookServer", "WebhookEndpoint", "WebhookEvent", "webhook_server",
    "GoalRunner", "GoalDefinition", "GoalStatus", "goal_runner",
    "Board", "BoardColumn", "BoardItem", "BoardStatus",
    # Video Harness
    "ProjectCard", "ProjectType", "CardSection",
    "CharacterDesigner", "Character", "Scene", "Prop",
    "StoryboardEngine", "Storyboard", "Shot", "ShotType", "CameraMovement",
    "ModelRouter", "ModelInfo", "ModelCapability", "RoutingDecision",
    "VideoHarness", "HarnessStep", "HarnessPhase", "VideoProject", "video_harness",
    # Brand Research
    "AdSource", "MetaAdLibrary", "GoogleAdsTransparency", "XMonitor", "RedditMonitor",
    "TrendingHookSpotter", "HookCategory", "TrendingHook",
    "CompetitorAdIntelligence", "CompetitorAd", "AdCluster",
    "AdAngleMiner", "ConversionAngle", "MiningSource",
    "BrandResearcher", "BrandProfile", "BrandContext",
    # Data Gateway
    "Platform", "PlatformRegistry", "platform_registry", "DataCategory", "DataItem",
    "DataGatewayClient", "DataGatewayConfig", "data_gateway",
    # Roles
    "Department", "DEPARTMENTS", "ROLES_DATABASE",
    "RoleDefinition", "RoleCategory", "RoleExpressionTone",
    "RoleWorkflow", "RoleDeliverable", "RoleMetrics", "role_registry",
    # MCP
    "MCPServer", "MCPTool", "MCPResource", "MCPPrompt", "MCPMessage",
    "JSONRPCRequest", "JSONRPCResponse", "mcp_server",
    "MCPToolRegistry", "ToolParameter", "ToolResult", "tool_registry",
    # Proactive
    "ProactiveEngine", "ProactiveContext", "ProactiveAction", "ContextSnapshot", "DailyReport", "proactive_engine",
    # Monitor
    "AgentStatus", "TaskMonitor", "HeartbeatEvent", "HeartbeatSound", "StatusMonitor", "status_monitor",
    # Geo
    "DEMTileFetcher", "terrarium_decode", "terrarium_encode", "TerrainBaker", "ElevationStops", "HillshadeGenerator", "LandMaskGenerator",
    "TileExporter", "WebPTile", "TileBounds", "tile_exporter",
    "GeoProject", "MapStyle", "PinPoint", "Chapter", "geo_engine",
    # Profile
    "UserProfile", "ProfileManager", "profile_manager",
    "AgentProfileTemplate", "AGENT_PROFILE_TEMPLATES",
    # Perf
    "CompressionStrategy", "CompressionResult", "PromptCache", "CacheEntry", "ContextCompressor",
    "prompt_cache", "context_compressor",
]
