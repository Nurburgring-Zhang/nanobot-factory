"""智影 V5 — Memory 子包: 3层文件分层 + Memory Palace

迁移自 obsidian-cc:
- 3 层文件分层: raw (原始证据, 永不删除) / sources (影子 MD, 可重做) / 长期记忆 (确认写入)
- 信任等级: 原始证据 > 抽取结果 > 长期记忆
- Memory Palace: 不存知识, 存路线 (触发场景/必读/条件读/输出位置/坑禁区)
- 反馈闭环: 👍/👎 → memory/feedback → 提炼 → profile/style
"""
from .layers import (
    MemoryLayer,
    RawStore,
    SourceStore,
    LongTermStore,
    InboxStore,
    FeedbackStore,
    TrustLevel,
    MemoryItem,
    MemoryQuery,
    memory_manager,
)
from .palace import (
    PalaceRoom,
    PalaceCard,
    PalaceRouter,
    palace_router,
)
from .feedback import (
    FeedbackSignal,
    FeedbackType,
    FeedbackCollector,
    TasteExtractor,
    ProfileUpdater,
    feedback_loop,
)

__all__ = [
    "MemoryLayer",
    "RawStore",
    "SourceStore",
    "LongTermStore",
    "InboxStore",
    "FeedbackStore",
    "TrustLevel",
    "MemoryItem",
    "MemoryQuery",
    "memory_manager",
    "PalaceRoom",
    "PalaceCard",
    "PalaceRouter",
    "palace_router",
    "FeedbackSignal",
    "FeedbackType",
    "FeedbackCollector",
    "TasteExtractor",
    "ProfileUpdater",
    "feedback_loop",
]
