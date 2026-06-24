"""P3-3-W1: Agent dispatch router (imdf/engines/ side).

Thin engine that lets the monolith (canvas_web.py) talk to the new
agent-service via the :class:`AgentRouter`.  Used by the master agent
planner to dispatch the 15 agent types when the monolith owns the request.

The router does NOT execute agents; it forwards ``agent_tasks`` to the
configured agent-service URL (env override → default ``http://127.0.0.1:8008``).
The agent-service owns execution + status reporting; this engine just
shuttles payloads.

Usage in monolith::

    from engines.agent_router import get_agent_router
    router = get_agent_router()
    decision = router.route("cleaning", {"items": [...]})
    # decision.service -> "cleaning-service" (logical)
    task = router.dispatch("cleaning", {"items": [...]}, mode="full_auto")
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentRoutingDecision:
    """Outcome of routing a request to one of the 15 agent types."""

    agent_type: str
    downstream_service: str
    mode: str
    eligible: bool
    reason: str = ""
    task_id: Optional[str] = None  # populated when the task is dispatched
    submitted_at: float = 0.0


# 15 agent type → downstream service mapping (kept in sync with
# services/agent_service/agents.py — duplicated intentionally so the
# monolith doesn't need to import services/*).
_AGENT_TO_SERVICE: Dict[str, str] = {
    "requirement_parser": "user-service",
    "data_collection": "asset-service",
    "cleaning": "cleaning-service",
    "prelabel": "annotation-service",
    "fine_annotation": "annotation-service",
    "review": "annotation-service",
    "scoring": "scoring-service",
    "filtering": "cleaning-service",
    "export": "dataset-service",
    "evaluation": "evaluation-service",
    "badcase_analysis": "evaluation-service",
    "feedback": "annotation-service",
    "memory": "agent-service",
    "scheduling": "agent-service",
    "quality": "evaluation-service",
}


class AgentRouter:
    """Routes agent-type requests to the matching downstream service.

    The router can either return a routing decision (synchronous, no I/O)
    or actually dispatch the task to the agent-service via HTTP / an
    in-process bus.  By default it returns a *logical* decision; the
    monolith can choose to also forward the call to the agent-service.
    """

    def __init__(
        self,
        *,
        agent_service_url: Optional[str] = None,
        default_mode: str = "full_auto",
        timeout: float = 5.0,
    ) -> None:
        self._url = (
            agent_service_url
            or os.environ.get("AGENT_SERVICE_URL")
            or "http://127.0.0.1:8008"
        )
        self._default_mode = default_mode
        self._timeout = timeout
        self._in_flight: Dict[str, AgentRoutingDecision] = {}

    @property
    def url(self) -> str:
        return self._url

    # ── Routing ────────────────────────────────────────────────────────────
    def route(self, agent_type: str, payload: Optional[Dict[str, Any]] = None,
              mode: Optional[str] = None) -> AgentRoutingDecision:
        """Return a routing decision (no I/O)."""
        service = _AGENT_TO_SERVICE.get(agent_type)
        if not service:
            return AgentRoutingDecision(
                agent_type=agent_type,
                downstream_service="unknown",
                mode=mode or self._default_mode,
                eligible=False,
                reason=f"unknown_agent_type:{agent_type}",
            )
        return AgentRoutingDecision(
            agent_type=agent_type,
            downstream_service=service,
            mode=mode or self._default_mode,
            eligible=True,
        )

    def dispatch(
        self,
        agent_type: str,
        payload: Dict[str, Any],
        *,
        mode: Optional[str] = None,
        priority: int = 5,
        run_inline: bool = False,
    ) -> AgentRoutingDecision:
        """Dispatch a task to agent-service via HTTP.  Returns a decision
        enriched with ``task_id`` on success, or ``eligible=False`` on
        failure (network down, service missing, etc.).
        """
        decision = self.route(agent_type, payload, mode=mode)
        if not decision.eligible:
            return decision

        task_id = f"agt-monolith-{uuid.uuid4().hex[:10]}"
        # Optional: forward to the agent-service.
        # httpx is optional — the test suite can use the in-process bus.
        try:
            import httpx  # type: ignore
            url = f"{self._url.rstrip('/')}/api/v1/agent_tasks"
            body = {
                "agent_type": agent_type,
                "payload": payload,
                "mode": decision.mode,
                "priority": priority,
                "run_inline": run_inline,
            }
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, json=body)
                if resp.status_code < 400:
                    try:
                        data = resp.json()
                        task_id = data.get("task", {}).get("task_id", task_id)
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    decision.eligible = False
                    decision.reason = (
                        f"agent_service_status:{resp.status_code}"
                    )
        except ImportError:
            # No httpx — keep the decision valid, just don't track a remote task.
            logger.debug("httpx not installed; dispatch is logical-only")
        except Exception as e:  # noqa: BLE001
            logger.warning("agent-service dispatch failed (%s): %s", agent_type, e)
            decision.eligible = False
            decision.reason = f"agent_service_unreachable:{e}"

        decision.task_id = task_id
        decision.submitted_at = time.time()
        self._in_flight[task_id] = decision
        return decision

    def list_routes(self) -> Dict[str, str]:
        """Return the 15-route map (used by /api/v1/agents/types in monolith)."""
        return dict(_AGENT_TO_SERVICE)

    def state(self) -> Dict[str, Any]:
        return {
            "url": self._url,
            "default_mode": self._default_mode,
            "routes": self.list_routes(),
            "in_flight": len(self._in_flight),
        }


# ── Module-level singleton ───────────────────────────────────────────────────
_router: Optional[AgentRouter] = None


def get_agent_router() -> AgentRouter:
    global _router
    if _router is None:
        _router = AgentRouter()
    return _router


def reset_agent_router_for_test() -> None:
    global _router
    _router = None


__all__ = [
    "AgentRouter",
    "AgentRoutingDecision",
    "get_agent_router",
    "reset_agent_router_for_test",
]
