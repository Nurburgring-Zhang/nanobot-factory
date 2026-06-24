"""P4-5-W2: Iterative creation + consistency workflow + multi-Agent collaboration.

Modules:
    session       — IterativeSession: draft→review→final/discarded multi-turn + A/B test
    agents        — MultiAgent Generator: 7 collaborating Agents with shared blackboard
    consistency   — Project-wide consistency + 5-round auto-refinement
    routes        — FastAPI router exposed under /api/v1/assets/{sessions,agents,multi_generate,consistency}
    store         — In-memory + JSON persistence (P4-5-W2 starts without DB; W1 will provide)
"""
from .session import (
    IterativeSession,
    SessionState,
    PromptVersion,
    GeneratedAsset,
    FeedbackEntry,
    ABTest,
    SessionStore,
    get_session_store,
)
from .agents import (
    AgentRole,
    AgentStatus,
    AgentMessage,
    Blackboard,
    DirectorAgent,
    StoryboardAgent,
    CharacterAgent,
    ImageAgent,
    VideoAgent,
    VoiceAgent,
    QAAgent,
    MultiAgentOrchestrator,
    get_orchestrator,
)
from .consistency import (
    ConsistencyConfig,
    ConsistencyReport,
    IterationRound,
    ConsistencyWorkflow,
    get_workflow,
)

__all__ = [
    # session
    "IterativeSession",
    "SessionState",
    "PromptVersion",
    "GeneratedAsset",
    "FeedbackEntry",
    "ABTest",
    "SessionStore",
    "get_session_store",
    # agents
    "AgentRole",
    "AgentStatus",
    "AgentMessage",
    "Blackboard",
    "DirectorAgent",
    "StoryboardAgent",
    "CharacterAgent",
    "ImageAgent",
    "VideoAgent",
    "VoiceAgent",
    "QAAgent",
    "MultiAgentOrchestrator",
    "get_orchestrator",
    # consistency
    "ConsistencyConfig",
    "ConsistencyReport",
    "IterationRound",
    "ConsistencyWorkflow",
    "get_workflow",
]