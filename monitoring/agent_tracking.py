"""Layer 8 — Agent behavior tracking.

Records each agent invocation (entry/exit, latency, model, tool calls) and
provides:

* ``record_invocation`` — append to in-process ring buffer (max 5_000 entries)
* ``/api/v1/monitoring/agent/activity`` — last N records (filterable)
* WebSocket broadcaster — frontends subscribed to ``/ws/monitoring/agents``
  receive every event in near real-time.

The records intentionally piggy-back on the audit-chain payload so compliance
can replay agent activity end-to-end.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any, Deque, Dict, List, Optional, Set


@dataclass
class AgentActivity:
    agent_id: str
    task_id: str
    user_id: str = "anonymous"
    model: str = "unknown"
    provider: str = "unknown"
    action: str = "invoke"          # invoke / tool_call / fallback / error
    tool: Optional[str] = None
    status: str = "ok"              # ok / error / timeout
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: float = field(default_factory=time.time)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["iso"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.timestamp))
        return d


class AgentTracker:
    """Process-wide agent activity recorder + websocket broadcaster."""

    def __init__(self, *, buffer_size: int = 5_000) -> None:
        self.buffer: Deque[AgentActivity] = deque(maxlen=buffer_size)
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    # -- record ------------------------------------------------------------- #
    def record(
        self,
        *,
        agent_id: str,
        task_id: Optional[str] = None,
        user_id: str = "anonymous",
        model: str = "unknown",
        provider: str = "unknown",
        action: str = "invoke",
        tool: Optional[str] = None,
        status: str = "ok",
        latency_ms: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> AgentActivity:
        rec = AgentActivity(
            agent_id=agent_id,
            task_id=task_id or str(uuid.uuid4()),
            user_id=user_id,
            model=model,
            provider=provider,
            action=action,
            tool=tool,
            status=status,
            latency_ms=float(latency_ms),
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            cost_usd=float(cost_usd),
            trace_id=trace_id,
            span_id=span_id,
            meta=dict(meta or {}),
        )
        self.buffer.append(rec)
        self._broadcast_sync(rec)
        return rec

    # -- query -------------------------------------------------------------- #
    def recent(self, limit: int = 100, *, agent_id: Optional[str] = None,
               user_id: Optional[str] = None, status: Optional[str] = None,
               since: Optional[float] = None) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for rec in reversed(self.buffer):
            if agent_id and rec.agent_id != agent_id:
                continue
            if user_id and rec.user_id != user_id:
                continue
            if status and rec.status != status:
                continue
            if since and rec.timestamp < since:
                continue
            out.append(rec.to_dict())
            if len(out) >= limit:
                break
        return out

    def stats(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        by_agent: Dict[str, int] = {}
        by_model: Dict[str, int] = {}
        total_cost = 0.0
        total_in_tok = 0
        total_out_tok = 0
        for rec in self.buffer:
            by_status[rec.status] = by_status.get(rec.status, 0) + 1
            by_agent[rec.agent_id] = by_agent.get(rec.agent_id, 0) + 1
            by_model[rec.model] = by_model.get(rec.model, 0) + 1
            total_cost += rec.cost_usd
            total_in_tok += rec.input_tokens
            total_out_tok += rec.output_tokens
        return {
            "buffer_size": len(self.buffer),
            "buffer_capacity": self.buffer.maxlen,
            "by_status": by_status,
            "by_agent": by_agent,
            "by_model": by_model,
            "total_cost_usd": round(total_cost, 6),
            "total_input_tokens": total_in_tok,
            "total_output_tokens": total_out_tok,
        }

    # -- websocket fan-out -------------------------------------------------- #
    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        async with self._lock:
            self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    def _broadcast_sync(self, rec: AgentActivity) -> None:
        # Best-effort: drop on slow subscriber.
        for q in list(self._subscribers):
            try:
                q.put_nowait(rec.to_dict())
            except asyncio.QueueFull:
                pass


# --------------------------------------------------------------------------- #
# Singleton + audit-chain hook
# --------------------------------------------------------------------------- #
_TRACKER: Optional[AgentTracker] = None


def get_tracker() -> AgentTracker:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = AgentTracker()
    return _TRACKER


def install_audit_chain_hook() -> None:
    """Wrap ``AuditChain.append`` so every entry also lands in the tracker.

    Safe to call multiple times — duplicates are avoided via a module-level flag.
    """
    global _HOOK_INSTALLED
    if _HOOK_INSTALLED:
        return
    try:
        from backend.imdf.engines.audit_chain import get_chain  # type: ignore
        chain = get_chain()
        original = chain.append

        def wrapped(*args: Any, **kw: Any):
            result = original(*args, **kw)
            try:
                user = kw.get("user") or (args[3] if len(args) > 3 else "anonymous")
                method = kw.get("method") or (args[0] if args else "unknown")
                path = kw.get("path") or (args[1] if len(args) > 1 else "unknown")
                get_tracker().record(
                    agent_id="audit-chain",
                    user_id=str(user),
                    action="audit.append",
                    status="ok",
                    trace_id=kw.get("trace_id") or os.getenv("TRACE_ID"),
                    meta={"method": method, "path": path},
                )
            except Exception:  # noqa: BLE001
                pass
            return result

        chain.append = wrapped  # type: ignore[assignment]
        _HOOK_INSTALLED = True
    except Exception:  # noqa: BLE001
        # audit-chain not importable — hook is optional.
        pass


_HOOK_INSTALLED = False
