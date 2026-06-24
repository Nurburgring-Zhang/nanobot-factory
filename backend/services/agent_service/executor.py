"""P3-3-W1: Agent executor — 3 execution modes.

The executor is the runnable boundary of the dispatch framework.  Given an
:class:`AgentTask`, it:

  1. Looks up the agent's default config in :mod:`agents`.
  2. Branches on the task's ``mode``:
     - ``full_auto``  — runs synchronously in-process; returns the result
       payload (stub: the heavy lifting still lives in the downstream
       service; this executor only proves the lifecycle + records).
     - ``semi_auto``  — produces a plan (list of steps) and waits for the
       caller to approve each step.  Returns the plan + checkpoints.
     - ``manual``     — does NOT run; returns a draft for human execution.
  3. Persists status transitions to the store.

The executor is a *thin* layer; it does NOT replace the actual agent
implementations living in the downstream services.  It exists to give
the platform a uniform entry point + uniform status reporting.
"""
from __future__ import annotations

import logging
import time
import traceback
from typing import Any, Dict, List, Optional

from .agents import (
    AGENT_REGISTRY,
    AgentType,
    ExecutionMode,
    get_agent_config,
)
from .memory import get_long_term, get_short_term, remember
from .scheduler import AgentScheduler, get_scheduler
from .store import AgentTask, AgentTaskStore, TaskStatus, get_store

logger = logging.getLogger(__name__)


# ── Per-agent skeletons ─────────────────────────────────────────────────────
# Each function returns a *plan* for the agent.  Real downstream service
# calls would replace the stub body.  The skeletons exist so the 15 agent
# types are all wired into the dispatch framework from day 1.
AGENT_SKELETONS: Dict[AgentType, Dict[str, Any]] = {
    AgentType.REQUIREMENT_PARSER: {
        "summary": "Parse user brief → structured plan",
        "steps": [
            "extract_content_type",
            "extract_style_prefs",
            "estimate_volume",
            "build_production_plan",
        ],
    },
    AgentType.DATA_COLLECTION: {
        "summary": "Crawl + ingest sources",
        "steps": ["deduplicate_sources", "fetch_batch", "store_in_dam"],
    },
    AgentType.CLEANING: {
        "summary": "Run 32 cleaning operators",
        "steps": ["dedup", "nsfw_filter", "blur_filter", "ocr_normalize", "tag"],
    },
    AgentType.PRELABEL: {
        "summary": "Model-assisted pre-annotation",
        "steps": ["select_model", "run_inference", "store_prelabels"],
    },
    AgentType.FINE_ANNOTATION: {
        "summary": "Manual fine annotation",
        "steps": ["assign_annotators", "collect_labels", "consensus"],
    },
    AgentType.REVIEW: {
        "summary": "Reviewer approval",
        "steps": ["queue_for_review", "reviewer_decision", "publish"],
    },
    AgentType.SCORING: {
        "summary": "Run 15 scoring operators + composite rank",
        "steps": ["aesthetic", "quality", "compose"],
    },
    AgentType.FILTERING: {
        "summary": "Apply threshold-based filters",
        "steps": ["load_thresholds", "apply", "emit"],
    },
    AgentType.EXPORT: {
        "summary": "Materialise dataset to target format",
        "steps": ["pick_format", "write", "verify"],
    },
    AgentType.EVALUATION: {
        "summary": "Model evaluation run",
        "steps": ["load_dataset", "run_model", "aggregate_metrics"],
    },
    AgentType.BADCASE_ANALYSIS: {
        "summary": "Cluster + summarise bad cases",
        "steps": ["cluster", "summarise", "tag_root_cause"],
    },
    AgentType.FEEDBACK: {
        "summary": "Push feedback to labelling pipeline",
        "steps": ["collect_signals", "rank", "schedule"],
    },
    AgentType.MEMORY: {
        "summary": "Read / write long-term memory",
        "steps": ["lookup_scope", "upsert"],
    },
    AgentType.SCHEDULING: {
        "summary": "Fan-out / fan-in scheduling",
        "steps": ["decompose", "enqueue", "wait_for_completion"],
    },
    AgentType.QUALITY: {
        "summary": "Cross-cutting quality gates",
        "steps": ["sla", "accuracy", "consistency"],
    },
}


# ── Executor ────────────────────────────────────────────────────────────────
class AgentExecutor:
    """Runs an :class:`AgentTask` according to its mode."""

    def __init__(
        self,
        store: Optional[AgentTaskStore] = None,
        scheduler: Optional[AgentScheduler] = None,
    ) -> None:
        self._store = store or get_store()
        self._scheduler = scheduler or get_scheduler(self._store)
        self._short = get_short_term()
        self._long = get_long_term()

    # ── Public API ─────────────────────────────────────────────────────────
    def run(self, task_id: str) -> Dict[str, Any]:
        """Execute a task end-to-end.  Returns a result dict.

        Side-effects:
          - transitions task status (PENDING → RUNNING → SUCCEEDED/FAILED)
          - writes to short-term memory (task plan + result)
          - writes to long-term memory (agent_type:result:*)
        """
        task = self._store.get(task_id)
        if task is None:
            return {"ok": False, "error": "task_not_found", "task_id": task_id}

        if task.status == TaskStatus.CANCELLED.value:
            return {"ok": False, "error": "task_cancelled", "task_id": task_id}

        if task.status in (TaskStatus.SUCCEEDED.value,):
            return {
                "ok": True,
                "task_id": task_id,
                "status": task.status,
                "result": task.result,
                "note": "already_completed",
            }

        # Manual mode never acquires a scheduler slot — it returns a draft
        # immediately for human execution.
        if task.mode != ExecutionMode.MANUAL.value:
            if not self._scheduler.acquire(task):
                return {
                    "ok": False,
                    "task_id": task_id,
                    "error": "no_resource",
                    "decision": self._scheduler.route(task),
                }
        acquired = task.mode != ExecutionMode.MANUAL.value

        try:
            self._store.transition(task_id, TaskStatus.RUNNING.value)
            if task.mode == ExecutionMode.FULL_AUTO.value:
                result = self._run_full_auto(task)
            elif task.mode == ExecutionMode.SEMI_AUTO.value:
                result = self._run_semi_auto(task)
            elif task.mode == ExecutionMode.MANUAL.value:
                result = self._run_manual(task)
            else:
                result = {
                    "ok": False,
                    "error": f"unknown_mode:{task.mode}",
                }
            # Persist outcome
            ok = bool(result.get("ok"))
            self._store.transition(
                task_id,
                TaskStatus.SUCCEEDED.value if ok else TaskStatus.FAILED.value,
                result=result if ok else None,
                error=None if ok else result.get("error", "unknown_error"),
            )
            if ok:
                # Stash a copy in long-term memory
                try:
                    remember(
                        scope=f"agent:{task.agent_type}:result",
                        key=task_id,
                        value=result,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.debug("remember failed: %s", e)
            return result
        except Exception as e:  # noqa: BLE001
            err = f"executor_exception:{e}"
            logger.exception("executor run failed: %s", err)
            self._store.transition(
                task_id,
                TaskStatus.FAILED.value,
                error=err + "\n" + traceback.format_exc(limit=4),
            )
            # Auto-retry if budget remains
            task = self._store.get(task_id)
            if task is not None and self._scheduler.should_retry(task):
                self._scheduler.schedule_retry(task, error=err)
            return {"ok": False, "task_id": task_id, "error": err}
        finally:
            if acquired:
                self._scheduler.release(task)

    def cancel(self, task_id: str) -> Optional[AgentTask]:
        task = self._store.get(task_id)
        if task is None:
            return None
        if task.status in (
            TaskStatus.SUCCEEDED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        ):
            return task
        return self._store.transition(task_id, TaskStatus.CANCELLED.value)

    def retry(self, task_id: str) -> Optional[AgentTask]:
        task = self._store.get(task_id)
        if task is None:
            return None
        if task.status not in (TaskStatus.FAILED.value, TaskStatus.CANCELLED.value):
            return None
        task.retry_count = 0
        task.status = TaskStatus.PENDING.value
        task.error = None
        task.started_at = None
        task.finished_at = None
        self._store.update(task)
        return task

    # ── Mode implementations ───────────────────────────────────────────────
    def _plan(self, task: AgentTask) -> Dict[str, Any]:
        """Build the canonical plan dict for a task (used by all modes)."""
        skeleton: Dict[str, Any] = {}
        cfg: Dict[str, Any] = {}
        try:
            cfg = get_agent_config(task.agent_type)
            at_enum = AgentType(task.agent_type)
            skeleton = AGENT_SKELETONS.get(at_enum, {})
        except (KeyError, ValueError):
            skeleton = {}
        return {
            "agent_type": task.agent_type,
            "agent_name": cfg.get("name", task.agent_type),
            "summary": skeleton.get("summary", ""),
            "steps": list(skeleton.get("steps", [])),
            "mode": task.mode,
        }

    def _run_full_auto(self, task: AgentTask) -> Dict[str, Any]:
        plan = self._plan(task)
        # Stub body — in production this would call the downstream service.
        # We still touch short-term memory so callers can verify the dispatch
        # framework is wired up.
        self._short.set(f"plan:{task.task_id}", plan, owner=task.task_id, ttl_seconds=3600)
        result = {
            "ok": True,
            "task_id": task.task_id,
            "agent_type": task.agent_type,
            "mode": task.mode,
            "plan": plan,
            "executed_steps": plan["steps"],
            "executed_at": time.time(),
        }
        self._short.set(f"result:{task.task_id}", result, owner=task.task_id, ttl_seconds=3600)
        return result

    def _run_semi_auto(self, task: AgentTask) -> Dict[str, Any]:
        plan = self._plan(task)
        # Build a checkpoint per step; only step 0 is "ready" — the rest
        # need explicit approval.
        checkpoints = [
            {"step": s, "status": "pending" if i > 0 else "ready"}
            for i, s in enumerate(plan["steps"])
        ]
        plan["checkpoints"] = checkpoints
        plan["awaiting_approval"] = checkpoints[1:] if len(checkpoints) > 1 else []
        self._short.set(f"plan:{task.task_id}", plan, owner=task.task_id, ttl_seconds=3600)
        # semi_auto returns the plan; downstream orchestrator advances it.
        return {
            "ok": True,
            "task_id": task.task_id,
            "agent_type": task.agent_type,
            "mode": task.mode,
            "plan": plan,
            "awaiting_human": True,
            "executed_at": time.time(),
        }

    def _run_manual(self, task: AgentTask) -> Dict[str, Any]:
        plan = self._plan(task)
        return {
            "ok": True,
            "task_id": task.task_id,
            "agent_type": task.agent_type,
            "mode": task.mode,
            "plan": plan,
            "draft_only": True,
            "executed_at": time.time(),
        }


# ── Module-level singleton ───────────────────────────────────────────────────
_executor: Optional[AgentExecutor] = None
_exec_lock = __import__("threading").RLock()


def get_executor() -> AgentExecutor:
    global _executor
    with _exec_lock:
        if _executor is None:
            _executor = AgentExecutor()
        return _executor


def reset_executor_for_test() -> None:
    global _executor
    with _exec_lock:
        _executor = None


__all__ = [
    "AGENT_SKELETONS",
    "AgentExecutor",
    "get_executor",
    "reset_executor_for_test",
]
