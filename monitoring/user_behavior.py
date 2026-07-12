"""Layer 12 — User behavior analytics.

Two complementary views:

* **Heatmap** — per-page (route) cursor / click density. Collected via the
  :func:`record_heatmap_event` API (frontend calls POST /api/v1/monitoring/heatmap).
* **Funnel** — login → first action → first paid action conversion rates.

All records live in-memory (ring buffer). For persistence, hook in your own
warehouse (BigQuery / ClickHouse / Postgres) at the ``on_event`` boundary.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Deque, Dict, List, Optional, Set


# --------------------------------------------------------------------------- #
# Funnel stages (must match the canonical user journey)
# --------------------------------------------------------------------------- #
DEFAULT_FUNNEL = ["login", "first_action", "first_paid_action", "renewal"]


@dataclass
class HeatmapEvent:
    record_id: str
    timestamp: float
    user_id: str
    session_id: str
    route: str
    x: float            # 0..1 normalised
    y: float            # 0..1 normalised
    event_type: str = "click"   # click | move | scroll | focus
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["iso"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.timestamp))
        return d


@dataclass
class FunnelEvent:
    record_id: str
    timestamp: float
    user_id: str
    stage: str
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["iso"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.timestamp))
        return d


class UserBehaviorTracker:
    def __init__(
        self,
        *,
        heatmap_buffer_size: int = 20_000,
        funnel_buffer_size: int = 10_000,
        funnel_stages: Optional[List[str]] = None,
    ) -> None:
        self.heatmap: Deque[HeatmapEvent] = deque(maxlen=heatmap_buffer_size)
        self.funnel: Deque[FunnelEvent] = deque(maxlen=funnel_buffer_size)
        self._stages = list(funnel_stages or DEFAULT_FUNNEL)
        self._on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None

    def set_on_event(self, fn: Optional[Callable[[str, Dict[str, Any]], None]]) -> None:
        """Optional warehouse-export hook (BigQuery / ClickHouse / etc)."""
        self._on_event = fn

    # -- heatmap ------------------------------------------------------------ #
    def record_heatmap(
        self,
        *,
        user_id: str,
        session_id: str,
        route: str,
        x: float,
        y: float,
        event_type: str = "click",
        meta: Optional[Dict[str, Any]] = None,
    ) -> HeatmapEvent:
        ev = HeatmapEvent(
            record_id=str(uuid.uuid4()),
            timestamp=time.time(),
            user_id=user_id,
            session_id=session_id,
            route=route,
            x=float(x),
            y=float(y),
            event_type=event_type,
            meta=dict(meta or {}),
        )
        self.heatmap.append(ev)
        if self._on_event:
            try:
                self._on_event("heatmap", ev.to_dict())
            except Exception:  # noqa: BLE001
                pass
        return ev

    def heatmap_for_route(self, route: str, limit: int = 5000) -> List[Dict[str, Any]]:
        target = route.lstrip("/")
        return [ev.to_dict() for ev in list(self.heatmap)[-limit:]
                if ev.route == route or ev.route.lstrip("/") == target]

    def heatmap_routes(self) -> List[Dict[str, Any]]:
        agg: Dict[str, int] = defaultdict(int)
        for ev in self.heatmap:
            agg[ev.route] += 1
        return [
            {"route": r, "events": c}
            for r, c in sorted(agg.items(), key=lambda x: -x[1])
        ]

    # -- funnel ------------------------------------------------------------- #
    def record_funnel(
        self,
        *,
        user_id: str,
        stage: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> FunnelEvent:
        if stage not in self._stages:
            # unknown stages are stored verbatim but flagged in stats.
            self._stages.append(stage)
        ev = FunnelEvent(
            record_id=str(uuid.uuid4()),
            timestamp=time.time(),
            user_id=user_id,
            stage=stage,
            meta=dict(meta or {}),
        )
        self.funnel.append(ev)
        if self._on_event:
            try:
                self._on_event("funnel", ev.to_dict())
            except Exception:  # noqa: BLE001
                pass
        return ev

    def funnel_report(self) -> Dict[str, Any]:
        """Compute per-stage unique users + conversion rate.

        A user is considered to have *reached* stage N if there is at least one
        event with that stage. The conversion rate is users_at_stage_N /
        users_at_stage_0.
        """
        users_at: Dict[str, Set[str]] = {s: set() for s in self._stages}
        for ev in self.funnel:
            users_at.setdefault(ev.stage, set()).add(ev.user_id)

        first = self._stages[0] if self._stages else None
        base = len(users_at.get(first, set())) if first else 0

        rows = []
        for stage in self._stages:
            users = len(users_at.get(stage, set()))
            rate = (users / base) if base else 0.0
            rows.append({
                "stage": stage,
                "users": users,
                "conversion_from_first": round(rate, 4),
            })
        return {
            "stages": rows,
            "base_stage": first,
            "base_users": base,
            "total_events": len(self.funnel),
            "unique_users": len({ev.user_id for ev in self.funnel}),
        }

    # -- generic stats ------------------------------------------------------ #
    def stats(self) -> Dict[str, Any]:
        return {
            "heatmap": {
                "buffer_size": len(self.heatmap),
                "buffer_capacity": self.heatmap.maxlen,
                "routes": self.heatmap_routes(),
            },
            "funnel": {
                "buffer_size": len(self.funnel),
                "buffer_capacity": self.funnel.maxlen,
                "report": self.funnel_report(),
            },
        }


_TRACKER: Optional[UserBehaviorTracker] = None


def get_tracker() -> UserBehaviorTracker:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = UserBehaviorTracker()
    return _TRACKER
