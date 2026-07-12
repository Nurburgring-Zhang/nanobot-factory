"""智影 V5 — Harness 子包: Full Harness (Planner+Generator+Evaluator Loop)

迁移自 Anthropic 演示的 Full Harness + Loop Engineering:
- Planner: 把模糊需求扩展成详细步骤计划
- Generator: 按 Sprint 实现
- Evaluator: 用 Playwright/真实验证, 任一阈值不通过则 sprint 失败
- 循环直到所有 criteria met
"""
from .planner import Planner, SprintPlan, PlannerStep, StepType
from .generator import (
    Generator,
    GeneratorOutput,
    ImplementationSprint,
    FileArtifact,
    SprintStatus,
)
from .evaluator import (
    Evaluator,
    EvaluationResult,
    EvaluationCriteria,
    CriterionStatus,
    CriterionType,
)
from .loop_engine import (
    HarnessEngine,
    HarnessConfig,
    HarnessRun,
    HarnessState,
    harness_engine,
)

__all__ = [
    "Planner",
    "SprintPlan",
    "PlannerStep",
    "StepType",
    "Generator",
    "GeneratorOutput",
    "ImplementationSprint",
    "FileArtifact",
    "SprintStatus",
    "Evaluator",
    "EvaluationResult",
    "EvaluationCriteria",
    "CriterionStatus",
    "CriterionType",
    "HarnessEngine",
    "HarnessConfig",
    "HarnessRun",
    "HarnessState",
    "harness_engine",
]
