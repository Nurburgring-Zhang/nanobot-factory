"""智影 V5 — Identity 子包: Bot / AgentCard / Channel / Thread / Matter

迁移自 Octo (明略科技) + Hermes Agent 的 O.C.T.O 模型:
- Bot 身份卡:有 AgentCard、归属、能力边界、工作履历
- Channel:项目群/工作频道
- Thread:具体一件事
- Matter:从聊天→事项,带验收标准
"""
from .bot import (
    Bot,
    AgentCard,
    Capability as BotCapability,
    BotRegistry,
    BotStatus,
    BotRole,
    bot_registry,
)
from .channel import Channel, ChannelType as ChannelKind, ChannelMember
from .thread import Thread, ThreadMessage, ThreadStatus
from .matter import Matter, MatterStatus, AcceptanceCriteria, DeliveryRecord

__all__ = [
    "Bot",
    "AgentCard",
    "BotCapability",
    "BotRegistry",
    "BotStatus",
    "BotRole",
    "bot_registry",
    "Channel",
    "ChannelKind",
    "ChannelMember",
    "Thread",
    "ThreadMessage",
    "ThreadStatus",
    "Matter",
    "MatterStatus",
    "AcceptanceCriteria",
    "DeliveryRecord",
]
