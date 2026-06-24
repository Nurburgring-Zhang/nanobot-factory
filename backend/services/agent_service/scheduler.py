"""P3-3-W1: Agent task scheduler.

Responsibilities:
  * Route an :class:`AgentTask` to the appropriate downstream service
    (``agent.downstream_service`` in :mod:`agents`).
  * Apply the execution mode policy (full_auto / semi_auto / manual).
  * Retry policy: exponential backoff up to ``max_retries``.
  * Resource allocation: token-bucket style concurrency limit per
    downstream service.

The scheduler is deliberately decoupled from the executor — the executor
runs the actual agent logic; the scheduler chooses *which* agent to run,
*when*, and *with how much concurrency*.  Both share the :class:`AgentTaskStore`.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

from .agents import (
    AGENT_REGISTRY,
    AgentType,
    ExecutionMode,
    get_agent_config,
)
from .store import AgentTask, AgentTaskStore, TaskStatus

logger = logging.getLogger(__name__)


# ── Resource token bucket ───────────────────────────────────────────────────
@dataclass
class ResourceBucket:
    """Simple per-service token-bucket concurrency limiter."""

    service: str
    capacity: int = 4
    in_flight: int = 0
    queue: Deque[str] = field(default_factory=deque)

    def try_acquire(self) -> bool:
        if self.in_flight < self.capacity:
            self.in_flight += 1
            return True
        return False

    def release(self) -> None:
        self.in_flight = max(0, self.in_flight - 1)


# ── Scheduler ────────────────────────────────────────────────────────────────
class AgentScheduler:
    """Routes tasks → services with concurrency caps + retry policy."""

    def __init__(
        self,
        store: AgentTaskStore,
        *,
        default_concurrency: int = 4,
    ) -> None:
        self._store = store
        self._default_concurrency = default_concurrency
        self._buckets: Dict[str, ResourceBucket] = {}
        self._lock = threading.RLock()

    # ── Bucket management ───────────────────────────────────────────────────
    def _bucket(self, service: str) -> ResourceBucket:
        with self._lock:
            b = self._buckets.get(service)
            if b is None:
                b = ResourceBucket(
                    service=service, capacity=self._default_concurrency
                )
                self._buckets[service] = b
            return b

    def set_concurrency(self, service: str, capacity: int) -> None:
        with self._lock:
            b = self._bucket(service)
            b.capacity = max(1, int(capacity))

    def bucket_state(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            return {
                b.service: {
                    "capacity": b.capacity,
                    "in_flight": b.in_flight,
                    "queued": len(b.queue),
                }
                for b in self._buckets.values()
            }

    # ── Routing ────────────────────────────────────────────────────────────
    def route(self, task: AgentTask) -> Dict[str, Any]:
        """Decide which downstream service should run this task.

        Returns a routing decision:
          ``{"service": str, "agent_type": str, "mode": str, "eligible": bool}``

        A task is ``eligible=False`` when the agent_type is unknown.
        """
        try:
            cfg = get_agent_config(task.agent_type)
        except KeyError:
            return {
                "service": "unknown",
                "agent_type": task.agent_type,
                "mode": task.mode,
                "eligible": False,
                "reason": f"unknown_agent_type:{task.agent_type}",
            }
        return {
            "service": cfg["downstream_service"],
            "agent_type": cfg["id"],
            "mode": task.mode,
            "eligible": True,
        }

    # ── Scheduling decisions ───────────────────────────────────────────────
    def can_run(self, task: AgentTask) -> bool:
        """Return True if the task can start right now (resource + mode)."""
        decision = self.route(task)
        if not decision["eligible"]:
            return False
        # Manual mode never auto-runs; it requires explicit user action.
        if task.mode == ExecutionMode.MANUAL.value:
            return False
        bucket = self._bucket(decision["service"])
        return bucket.try_acquire()

    def acquire(self, task: AgentTask) -> bool:
        """Reserve a concurrency slot for the task.  Returns True on success."""
        decision = self.route(task)
        if not decision["eligible"]:
            return False
        if task.mode == ExecutionMode.MANUAL.value:
            return False
        bucket = self._bucket(decision["service"])
        return bucket.try_acquire()

    def release(self, task: AgentTask) -> None:
        decision = self.route(task)
        if decision["eligible"]:
            self._bucket(decision["service"]).release()

    # ── Retry policy ───────────────────────────────────────────────────────
    def should_retry(self, task: AgentTask) -> bool:
        return task.retry_count < task.max_retries

    def backoff_seconds(self, task: AgentTask) -> float:
        """Exponential backoff: 1s, 2s, 4s, 8s, ... (capped at 60s)."""
        return min(60.0, 2 ** max(0, task.retry_count - 1))

    def schedule_retry(self, task: AgentTask, error: str) -> Optional[AgentTask]:
        """Bump retry_count and reset to PENDING.  Returns None if no more retries."""
        if not self.should_retry(task):
            return None
        task.retry_count += 1
        task.error = error
        task.status = TaskStatus.PENDING.value
        task.started_at = None
        task.finished_at = None
        self._store.update(task)
        return task


# ── Module-level singleton ───────────────────────────────────────────────────
_scheduler: Optional[AgentScheduler] = None
_sched_lock = threading.Lock()


def get_scheduler(store: Optional[AgentTaskStore] = None) -> AgentScheduler:
    global _scheduler
    with _sched_lock:
        if _scheduler is None:
            # Late import to avoid circular dep
            from .store import get_store
            _scheduler = AgentScheduler(store=store or get_store())
        return _scheduler


def reset_scheduler_for_test() -> None:
    global _scheduler
    with _sched_lock:
        _scheduler = None


__all__ = [
    "ResourceBucket",
    "AgentScheduler",
    "get_scheduler",
    "reset_scheduler_for_test",
]
