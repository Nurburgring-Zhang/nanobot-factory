"""Layer 9 — Cost tracking.

Tracks spend per (model, task, user) so finance can answer:

* how much did GPT-4o-mini cost this week?
* what did task_id ``t-abc`` actually cost?
* what is the cumulative spend per user (for billing reconciliation)?

Records can be ingested from:

* the legacy ``usage_tracker`` (P5-W3) — automatic on import if available
* direct calls to :func:`record` (preferred for new code)
* batch import via :func:`import_from_usage_tracker`
"""

from __future__ import annotations

import os
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from typing import Any, Deque, Dict, List, Optional


# Cost table (USD per 1K tokens). Conservative defaults — overridable at runtime.
DEFAULT_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI
    "gpt-4o":            {"input": 0.005,  "output": 0.015},
    "gpt-4o-mini":       {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo":       {"input": 0.010,  "output": 0.030},
    "gpt-3.5-turbo":     {"input": 0.0005, "output": 0.0015},
    # Anthropic
    "claude-3-5-sonnet": {"input": 0.003,  "output": 0.015},
    "claude-3-opus":     {"input": 0.015,  "output": 0.075},
    "claude-3-haiku":    {"input": 0.00025, "output": 0.00125},
    # Local / free
    "local-llama":       {"input": 0.0,    "output": 0.0},
    "mock":              {"input": 0.0,    "output": 0.0},
}


@dataclass
class CostRecord:
    record_id: str
    timestamp: float
    user_id: str
    task_id: str
    agent_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    trace_id: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    tenant_id: str = "default"  # P19-D1: tenant attribution for cost aggregation

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["iso"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.timestamp))
        return d


def price_for(model: str, *, override: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, float]:
    table = override or DEFAULT_MODEL_PRICING
    return table.get(model, table.get("mock", {"input": 0.0, "output": 0.0}))


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int,
                     *, override: Optional[Dict[str, Dict[str, float]]] = None) -> float:
    p = price_for(model, override=override)
    return round(
        (input_tokens / 1000.0) * p["input"] + (output_tokens / 1000.0) * p["output"],
        8,
    )


class CostTracker:
    def __init__(self, *, buffer_size: int = 10_000) -> None:
        self.buffer: Deque[CostRecord] = deque(maxlen=buffer_size)
        self._pricing = dict(DEFAULT_MODEL_PRICING)

    def set_pricing(self, model: str, input_per_1k: float, output_per_1k: float) -> None:
        self._pricing[model] = {"input": input_per_1k, "output": output_per_1k}

    # -- record ------------------------------------------------------------- #
    def record(
        self,
        *,
        user_id: str = "anonymous",
        task_id: Optional[str] = None,
        agent_id: str = "agent",
        provider: str = "unknown",
        model: str = "unknown",
        input_tokens: int = 0,
        output_tokens: int = 0,
        trace_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        cost_usd: Optional[float] = None,
        tenant_id: str = "default",
    ) -> CostRecord:
        cost = cost_usd if cost_usd is not None else compute_cost_usd(
            model, input_tokens, output_tokens, override=self._pricing,
        )
        rec = CostRecord(
            record_id=str(uuid.uuid4()),
            timestamp=time.time(),
            user_id=user_id,
            task_id=task_id or str(uuid.uuid4()),
            agent_id=agent_id,
            provider=provider,
            model=model,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            cost_usd=float(cost),
            trace_id=trace_id,
            meta=dict(meta or {}),
            tenant_id=tenant_id,
        )
        self.buffer.append(rec)
        return rec

    def import_from_usage_tracker(self, since_ts: Optional[float] = None) -> int:
        """Best-effort ingest from the P5-W3 ``usage_tracker`` if present."""
        try:
            from backend.services.billing_service.usage_tracker import (  # type: ignore
                iter_records,
            )
        except Exception:  # noqa: BLE001
            return 0
        count = 0
        for ur in iter_records(since=since_ts):
            try:
                self.record(
                    user_id=ur.user_id,
                    task_id=ur.task_id,
                    provider=ur.provider,
                    model=ur.model,
                    input_tokens=ur.input_tokens,
                    output_tokens=ur.output_tokens,
                    cost_usd=ur.cost_usd,
                )
                count += 1
            except Exception:  # noqa: BLE001
                continue
        return count

    # -- query -------------------------------------------------------------- #
    def recent(self, limit: int = 100, *, user_id: Optional[str] = None,
               model: Optional[str] = None) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for rec in reversed(self.buffer):
            if user_id and rec.user_id != user_id:
                continue
            if model and rec.model != model:
                continue
            out.append(rec.to_dict())
            if len(out) >= limit:
                break
        return out

    def per_user(self, limit: int = 50) -> List[Dict[str, Any]]:
        agg: Dict[str, Dict[str, float]] = defaultdict(lambda: {
            "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0,
        })
        for rec in self.buffer:
            a = agg[rec.user_id]
            a["cost_usd"] += rec.cost_usd
            a["input_tokens"] += rec.input_tokens
            a["output_tokens"] += rec.output_tokens
            a["calls"] += 1
        rows = [
            {"user_id": uid, **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in d.items()}}
            for uid, d in agg.items()
        ]
        rows.sort(key=lambda r: r["cost_usd"], reverse=True)
        return rows[:limit]

    def per_model(self, limit: int = 50) -> List[Dict[str, Any]]:
        agg: Dict[str, Dict[str, float]] = defaultdict(lambda: {
            "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0,
        })
        for rec in self.buffer:
            a = agg[rec.model]
            a["cost_usd"] += rec.cost_usd
            a["input_tokens"] += rec.input_tokens
            a["output_tokens"] += rec.output_tokens
            a["calls"] += 1
        rows = [
            {"model": m, **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in d.items()}}
            for m, d in agg.items()
        ]
        rows.sort(key=lambda r: r["cost_usd"], reverse=True)
        return rows[:limit]

    def per_task(self, limit: int = 50) -> List[Dict[str, Any]]:
        agg: Dict[str, Dict[str, float]] = defaultdict(lambda: {
            "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0, "user_id": "",
        })
        for rec in self.buffer:
            a = agg[rec.task_id]
            a["cost_usd"] += rec.cost_usd
            a["input_tokens"] += rec.input_tokens
            a["output_tokens"] += rec.output_tokens
            a["calls"] += 1
            a["user_id"] = rec.user_id
        rows = [
            {"task_id": t, **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in d.items()}}
            for t, d in agg.items()
        ]
        rows.sort(key=lambda r: r["cost_usd"], reverse=True)
        return rows[:limit]

    def stats(self) -> Dict[str, Any]:
        return {
            "buffer_size": len(self.buffer),
            "buffer_capacity": self.buffer.maxlen,
            "total_cost_usd": round(sum(r.cost_usd for r in self.buffer), 6),
            "total_input_tokens": sum(r.input_tokens for r in self.buffer),
            "total_output_tokens": sum(r.output_tokens for r in self.buffer),
            "pricing_table": self._pricing,
        }

    def per_tenant(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Aggregate cost / token usage grouped by ``tenant_id``.

        Returns the top-``limit`` tenants by ``cost_usd`` descending. Tenants
        with no records in the current buffer are omitted — callers that need
        a stable tenant list should join against the tenant catalogue.
        """
        agg: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "cost_usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "calls": 0,
            "unique_users": set(),
        })
        for rec in self.buffer:
            a = agg[rec.tenant_id]
            a["cost_usd"] += rec.cost_usd
            a["input_tokens"] += rec.input_tokens
            a["output_tokens"] += rec.output_tokens
            a["calls"] += 1
            a["unique_users"].add(rec.user_id)
        rows = []
        for tid, d in agg.items():
            row = {
                "tenant_id": tid,
                "cost_usd": round(d["cost_usd"], 6),
                "input_tokens": d["input_tokens"],
                "output_tokens": d["output_tokens"],
                "calls": d["calls"],
                "unique_users": len(d["unique_users"]),
            }
            rows.append(row)
        rows.sort(key=lambda r: r["cost_usd"], reverse=True)
        return rows[:limit]


_TRACKER: Optional[CostTracker] = None


def get_tracker() -> CostTracker:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = CostTracker()
    return _TRACKER
