"""智影 V5 — Harness Loop Engine: Planner+Generator+Evaluator 完整循环"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .planner import Planner, SprintPlan
from .generator import Generator, ImplementationSprint, SprintStatus, GeneratorOutput
from .evaluator import Evaluator, EvaluationResult, CriterionStatus

logger = logging.getLogger(__name__)


class HarnessState(str, Enum):
    """Harness 状态"""
    IDLE = "idle"
    PLANNING = "planning"
    GENERATING = "generating"
    EVALUATING = "evaluating"
    ITERATING = "iterating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class HarnessConfig:
    """Harness 配置"""
    max_iterations: int = 3
    min_pass_rate: float = 0.9  # 通过率阈值
    fail_fast: bool = False  # 任一 required fail 立即停止
    save_artifacts: bool = True
    use_real_llm: bool = True
    evaluator_criteria_override: Optional[List] = None


@dataclass
class HarnessRun:
    """一次 Harness 完整运行"""

    run_id: str = field(default_factory=lambda: f"hr-{uuid.uuid4().hex[:12]}")
    requirement: str = ""
    config: HarnessConfig = field(default_factory=HarnessConfig)
    state: HarnessState = HarnessState.IDLE

    # 各阶段产物
    plan: Optional[SprintPlan] = None
    sprints: List[ImplementationSprint] = field(default_factory=list)
    evaluations: List[List[EvaluationResult]] = field(default_factory=list)
    final_artifacts: List[Any] = field(default_factory=list)

    # 迭代
    current_iteration: int = 0
    final_pass_rate: float = 0.0
    success: bool = False
    failure_reason: str = ""

    # 时间
    started_at: float = 0.0
    completed_at: float = 0.0
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "requirement": self.requirement,
            "state": self.state.value,
            "iterations": self.current_iteration,
            "sprint_count": len(self.sprints),
            "final_pass_rate": round(self.final_pass_rate, 3),
            "success": self.success,
            "failure_reason": self.failure_reason,
            "duration_ms": (self.completed_at - self.started_at) * 1000 if self.completed_at else 0,
            "artifact_count": len(self.final_artifacts),
            "history": self.history,
        }


class HarnessEngine:
    """Harness 主循环引擎

    借鉴 Anthropic Full Harness + Loop Engineering:
    - Planner 写计划
    - Generator 实现 (按 Sprint)
    - Evaluator 验证
    - 任一 required 不通过 → 重做 (最多 max_iterations 次)
    - 不要迷信三 Agent: Harness 随模型升级调整
    """

    def __init__(self):
        self.planner = Planner()
        self.generator = Generator()
        self.evaluator = Evaluator()
        self.runs: Dict[str, HarnessRun] = {}
        self.metrics: Dict[str, int] = {"total": 0, "success": 0, "failed": 0}

    def run(
        self,
        requirement: str,
        config: Optional[HarnessConfig] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> HarnessRun:
        """主循环"""
        cfg = config or HarnessConfig()
        run = HarnessRun(
            requirement=requirement,
            config=cfg,
            started_at=time.time(),
        )
        self.runs[run.run_id] = run
        self.metrics["total"] += 1

        # Phase 1: Planning
        run.state = HarnessState.PLANNING
        run.plan = self.planner.plan(requirement, context)
        run.history.append({"phase": "planning", "plan": run.plan.to_dict()})

        # Loop: Generator → Evaluator
        for iteration in range(1, cfg.max_iterations + 1):
            run.current_iteration = iteration
            # Phase 2: Generating
            run.state = HarnessState.GENERATING
            sprint = self.generator.generate(run.plan, context)
            run.sprints.append(sprint)
            run.history.append({"phase": "generating", "iteration": iteration, "sprint": sprint.to_dict()})

            # Phase 3: Evaluating
            run.state = HarnessState.EVALUATING
            # 收集所有 artifacts
            artifacts = []
            for s in run.sprints:
                for out in s.step_outputs.values():
                    artifacts.extend(out.artifacts)
            passed, results = self.evaluator.evaluate(sprint, artifacts)
            run.evaluations.append(results)
            summary = self.evaluator.get_summary(results)
            run.history.append(
                {
                    "phase": "evaluating",
                    "iteration": iteration,
                    "passed": passed,
                    "summary": summary,
                    "results": [r.to_dict() for r in results],
                }
            )
            run.final_pass_rate = summary["pass_rate"]

            # 决策
            if passed and run.final_pass_rate >= cfg.min_pass_rate:
                # 通过
                run.state = HarnessState.COMPLETED
                run.success = True
                run.final_artifacts = artifacts
                self.metrics["success"] += 1
                logger.info(
                    f"Harness {run.run_id} COMPLETED at iter {iteration} pass_rate {run.final_pass_rate:.2%}"
                )
                break

            # 失败
            if cfg.fail_fast:
                # 立即停止
                run.state = HarnessState.FAILED
                run.success = False
                run.failure_reason = "fail_fast triggered"
                self.metrics["failed"] += 1
                break

            # 准备下一轮迭代
            if iteration < cfg.max_iterations:
                run.state = HarnessState.ITERATING
                # 把 Evaluator 反馈注入下次 Generator 的 context
                feedback_summary = self._format_feedback(results)
                if context is None:
                    context = {}
                context["evaluator_feedback"] = feedback_summary
                run.history.append(
                    {
                        "phase": "iterating",
                        "iteration": iteration,
                        "feedback_to_generator": feedback_summary,
                    }
                )

        # 循环结束未通过
        if not run.success and run.state not in (HarnessState.FAILED, HarnessState.COMPLETED):
            run.state = HarnessState.FAILED
            run.failure_reason = f"max_iterations ({cfg.max_iterations}) exhausted, pass_rate {run.final_pass_rate:.2%}"
            self.metrics["failed"] += 1

        run.completed_at = time.time()
        logger.info(
            f"Harness {run.run_id} finished: success={run.success}, "
            f"iter={run.current_iteration}, pass_rate={run.final_pass_rate:.2%}"
        )
        return run

    def _format_feedback(self, results: List[EvaluationResult]) -> str:
        """把 Evaluator 反馈格式化成 Generator 可读字符串"""
        lines = ["# Evaluator 反馈 (上一轮)\n"]
        for r in results:
            status_icon = "✓" if r.status == CriterionStatus.PASS else ("⚠" if r.status == CriterionStatus.WARN else "✗")
            lines.append(f"{status_icon} {r.criterion_name} (score={r.score:.2f}): {r.feedback}")
        return "\n".join(lines)

    def get_run(self, run_id: str) -> Optional[HarnessRun]:
        return self.runs.get(run_id)

    def get_stats(self) -> Dict[str, Any]:
        success_rate = self.metrics["success"] / max(self.metrics["total"], 1)
        avg_iter = sum(r.current_iteration for r in self.runs.values()) / max(len(self.runs), 1)
        return {
            "total_runs": self.metrics["total"],
            "success_runs": self.metrics["success"],
            "failed_runs": self.metrics["failed"],
            "success_rate": round(success_rate, 3),
            "avg_iterations": round(avg_iter, 2),
        }


harness_engine = HarnessEngine()
