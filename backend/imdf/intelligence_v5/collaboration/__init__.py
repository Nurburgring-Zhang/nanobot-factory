"""智影 V5 — Collaboration 子包: 6 种协作模式

迁移自 Octo (明略科技) 六种协作模式:
- Solo: 单人完成
- Roundtable: 圆桌讨论
- Critic: 独立审核
- Pipeline: 流水线
- Split: 分头干
- Swarm: 竞选择优
"""
from .modes import (
    CollaborationMode,
    CollaborationSession,
    SoloSession,
    RoundtableSession,
    CriticSession,
    PipelineSession,
    SplitSession,
    SwarmSession,
    CollaborationContext,
    CollaborationResult,
    CollaborationEngine,
    collaboration_engine,
)

__all__ = [
    "CollaborationMode",
    "CollaborationSession",
    "SoloSession",
    "RoundtableSession",
    "CriticSession",
    "PipelineSession",
    "SplitSession",
    "SwarmSession",
    "CollaborationContext",
    "CollaborationResult",
    "CollaborationEngine",
    "collaboration_engine",
]
