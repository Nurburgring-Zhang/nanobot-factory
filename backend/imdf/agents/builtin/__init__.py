"""P6-Fix-P0-5: built-in concrete agent classes.

Every concrete :class:`BaseAgent` subclass lives in :mod:`_all`
(generated from the ``AGENT_META`` table that mirrors
``AGENT_REGISTRY`` in ``services/agent_service/agents.py``).  We
expose them at module scope so ``from imdf.agents.builtin import
CleaningAgent`` works just like importing any other symbol.

The :class:`AgentType` enum is imported lazily inside
:meth:`execute` to avoid the circular import between
``imdf.agents`` and ``services.agent_service.agents``.
"""
from ._all import (
    AGENT_META,
    BadcaseAnalysisAgent,
    CleaningAgent,
    DataCollectionAgent,
    EvaluationAgent,
    ExportAgent,
    FeedbackAgent,
    FilteringAgent,
    FineAnnotationAgent,
    GenerationCharacterAgent,
    GenerationDirectorAgent,
    GenerationImageAgent,
    GenerationQaAgent,
    GenerationStoryboardAgent,
    GenerationVideoAgent,
    GenerationVoiceAgent,
    MemoryAgent,
    PrelabelAgent,
    QualityAgent,
    RequirementParserAgent,
    ReviewAgent,
    SchedulingAgent,
    ScoringAgent,
    SkillOrchestratorAgent,
    get_builtin_classes,
    get_builtin_slugs,
)


# Stable export order — must match AGENT_REGISTRY in
# services/agent_service/agents.py so the registry binding is
# deterministic.
BUILTIN_AGENT_CLASSES = get_builtin_classes()


__all__ = [
    "AGENT_META",
    "BUILTIN_AGENT_CLASSES",
    "get_builtin_classes",
    "get_builtin_slugs",
    # Class names
    "RequirementParserAgent",
    "DataCollectionAgent",
    "CleaningAgent",
    "PrelabelAgent",
    "FineAnnotationAgent",
    "ReviewAgent",
    "ScoringAgent",
    "FilteringAgent",
    "ExportAgent",
    "EvaluationAgent",
    "BadcaseAnalysisAgent",
    "FeedbackAgent",
    "MemoryAgent",
    "SchedulingAgent",
    "QualityAgent",
    "GenerationDirectorAgent",
    "GenerationStoryboardAgent",
    "GenerationCharacterAgent",
    "GenerationImageAgent",
    "GenerationVideoAgent",
    "GenerationVoiceAgent",
    "GenerationQaAgent",
    "SkillOrchestratorAgent",
]
