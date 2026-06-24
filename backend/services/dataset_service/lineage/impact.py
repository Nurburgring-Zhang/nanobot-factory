"""P4-4-W2 impact analysis.

Three things to know about an asset change:

  1. **Upstream** (ancestors) — "Where does this come from?"
     Answered via the asset graph's predecessors.

  2. **Downstream** (descendants) — "What breaks if I change this?"
     Answered via the asset graph's successors.

  3. **Risk score** — combines:
       * count of downstream descendants
       * count of distinct teams / owners affected
       * presence of any ``model`` in downstream (a model retraining
         is a *big* deal)
       * presence of any ``pipeline`` with a long chain behind it
       * edge sources (``operator``/``sql`` weight more than ``manual``)

     The score is 0-100. > 70 → "high", > 40 → "medium", else "low".

  4. **Notify** — collects owner/team of every downstream asset and
     returns a ready-to-send notification plan. The actual delivery
     plugs into ``notification_service`` (HTTP) — we just build the
     envelope here so the API can return it.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from .graph import AssetGraph, get_graph
from .models import (
    AssetORM,
    EdgeORM,
    get_lineage_session,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Risk weights — tuneable
# ═════════════════════════════════════════════════════════════════════════════
WEIGHT_DOWNSTREAM_NODE = 1.5
WEIGHT_DOWNSTREAM_TEAM = 8.0
WEIGHT_DOWNSTREAM_MODEL = 25.0
WEIGHT_DOWNSTREAM_PIPELINE = 12.0
WEIGHT_SOURCE_OPERATOR = 1.0
WEIGHT_SOURCE_SQL = 0.5
WEIGHT_SOURCE_AST = 0.5
WEIGHT_SOURCE_MANUAL = 0.2
RISK_HIGH = 70
RISK_MEDIUM = 40


def _weight_for_source(source: str) -> float:
    return {
        "operator": WEIGHT_SOURCE_OPERATOR,
        "sql": WEIGHT_SOURCE_SQL,
        "ast": WEIGHT_SOURCE_AST,
        "manual": WEIGHT_SOURCE_MANUAL,
        "scan": 0.3,
    }.get(source, 0.1)


# ═════════════════════════════════════════════════════════════════════════════
# Result objects
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class ImpactReport:
    entity: str
    upstream_count: int = 0
    downstream_count: int = 0
    upstream: List[Dict[str, Any]] = field(default_factory=list)
    downstream: List[Dict[str, Any]] = field(default_factory=list)
    risk_score: int = 0
    risk_level: str = "low"  # low/medium/high
    reasons: List[str] = field(default_factory=list)
    affected_teams: List[str] = field(default_factory=list)
    affected_owners: List[str] = field(default_factory=list)
    has_model: bool = False
    has_pipeline: bool = False
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity": self.entity,
            "upstream_count": self.upstream_count,
            "downstream_count": self.downstream_count,
            "upstream": list(self.upstream),
            "downstream": list(self.downstream),
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "reasons": list(self.reasons),
            "affected_teams": list(self.affected_teams),
            "affected_owners": list(self.affected_owners),
            "has_model": self.has_model,
            "has_pipeline": self.has_pipeline,
            "generated_at": self.generated_at,
        }


@dataclass
class NotificationPlan:
    entity: str
    notification_id: str
    recipients: List[Dict[str, str]] = field(default_factory=list)
    message: str = ""
    channel: str = "inbox"
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity": self.entity,
            "notification_id": self.notification_id,
            "recipients": list(self.recipients),
            "message": self.message,
            "channel": self.channel,
            "created_at": self.created_at,
        }


# ═════════════════════════════════════════════════════════════════════════════
# Impact analyzer
# ═════════════════════════════════════════════════════════════════════════════
class ImpactAnalyzer:
    """Stateless analyzer; safe to share across requests."""

    def __init__(self, graph: Optional[AssetGraph] = None) -> None:
        self._graph = graph or get_graph()

    def upstream(self, entity: str, *, depth: int = -1) -> List[Dict[str, Any]]:
        return self._graph.neighbors_upstream(entity, depth=depth)

    def downstream(self, entity: str, *, depth: int = -1) -> List[Dict[str, Any]]:
        return self._graph.neighbors_downstream(entity, depth=depth)

    def full_impact(
        self,
        entity: str,
        *,
        depth: int = -1,
        db: Optional[Session] = None,
    ) -> ImpactReport:
        """Return a complete impact report for *entity*."""
        up = self.upstream(entity, depth=depth)
        down = self.downstream(entity, depth=depth)
        score, reasons, has_model, has_pipeline = self._score(
            entity, up, down, db=db
        )
        teams: Set[str] = {d.get("team", "") for d in down if d.get("team")}
        teams.discard("")
        owners: Set[str] = {d.get("owner", "") for d in down if d.get("owner")}
        owners.discard("")
        if score >= RISK_HIGH:
            level = "high"
        elif score >= RISK_MEDIUM:
            level = "medium"
        else:
            level = "low"
        return ImpactReport(
            entity=entity,
            upstream_count=len(up),
            downstream_count=len(down),
            upstream=up,
            downstream=down,
            risk_score=min(score, 100),
            risk_level=level,
            reasons=reasons,
            affected_teams=sorted(teams),
            affected_owners=sorted(owners),
            has_model=has_model,
            has_pipeline=has_pipeline,
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def build_notification(
        self,
        entity: str,
        change_description: str = "",
        *,
        db: Optional[Session] = None,
    ) -> NotificationPlan:
        """Build a notification plan for owners / teams affected by *entity*.

        The plan includes one ``recipient`` per (owner, team) and a
        ready-to-send message body. Actual delivery plugs into
        ``notification_service``; this method only builds the envelope.
        """
        report = self.full_impact(entity, db=db)
        recipients: List[Dict[str, str]] = []
        seen: Set[str] = set()
        for d in report.downstream:
            owner = d.get("owner", "")
            team = d.get("team", "")
            key = f"{owner}|{team}"
            if key in seen:
                continue
            seen.add(key)
            recipients.append(
                {
                    "owner": owner or "unknown",
                    "team": team or "unknown",
                    "asset": d.get("qualified_name", ""),
                }
            )
        # Fallback: notify known asset owner of the changed asset
        if not recipients:
            close_db = False
            if db is None:
                db = get_lineage_session()
                close_db = True
            try:
                a = (
                    db.query(AssetORM)
                    .filter(AssetORM.qualified_name == entity)
                    .one_or_none()
                )
                if a and (a.owner or a.team):
                    recipients.append(
                        {
                            "owner": a.owner or "unknown",
                            "team": a.team or "unknown",
                            "asset": entity,
                        }
                    )
            finally:
                if close_db:
                    try:
                        db.close()
                    except Exception:
                        pass
        msg = (
            f"[Lineage] Asset `{entity}` is about to change.\n"
            f"Risk: {report.risk_level} ({report.risk_score}/100).\n"
            f"Downstream affected: {report.downstream_count} node(s), "
            f"models: {report.has_model}, pipelines: {report.has_pipeline}.\n"
            f"Reason(s): {', '.join(report.reasons) or 'n/a'}.\n"
            + (f"Note: {change_description}" if change_description else "")
        )
        return NotificationPlan(
            entity=entity,
            notification_id=uuid.uuid4().hex,
            recipients=recipients,
            message=msg,
            channel="inbox",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    # ── Scoring ─────────────────────────────────────────────────────────
    def _score(
        self,
        entity: str,
        upstream: List[Dict[str, Any]],
        downstream: List[Dict[str, Any]],
        *,
        db: Optional[Session] = None,
    ) -> tuple:
        score = 0.0
        reasons: List[str] = []
        has_model = False
        has_pipeline = False
        # Downstream weight
        score += len(downstream) * WEIGHT_DOWNSTREAM_NODE
        if len(downstream) >= 5:
            reasons.append(
                f"{len(downstream)} downstream asset(s) — broad blast radius"
            )
        # Distinct teams
        teams: Set[str] = {d.get("team", "") for d in downstream if d.get("team")}
        teams.discard("")
        if teams:
            score += len(teams) * WEIGHT_DOWNSTREAM_TEAM
            reasons.append(f"affects {len(teams)} team(s): {', '.join(sorted(teams))}")
        # Distinct owners
        owners: Set[str] = {d.get("owner", "") for d in downstream if d.get("owner")}
        owners.discard("")
        if owners:
            score += min(len(owners), 5) * 3.0
        # Has model
        for d in downstream:
            et = d.get("entity_type", "")
            if et == "model":
                has_model = True
                score += WEIGHT_DOWNSTREAM_MODEL
                reasons.append("feeds a model — retraining required")
                break
        # Has pipeline
        for d in downstream:
            et = d.get("entity_type", "")
            if et == "pipeline":
                has_pipeline = True
                score += WEIGHT_DOWNSTREAM_PIPELINE
                reasons.append("downstream pipeline(s) may re-execute")
                break
        # Edge source weighting
        close_db = False
        if db is None:
            db = get_lineage_session()
            close_db = True
        try:
            out_edges = (
                db.query(EdgeORM).filter(EdgeORM.from_entity == entity).all()
            )
            for e in out_edges:
                score += _weight_for_source(e.source)
        finally:
            if close_db:
                try:
                    db.close()
                except Exception:
                    pass
        if not downstream and not upstream:
            reasons.append("isolated asset — no upstream or downstream")
        if not reasons:
            reasons.append("no special risks detected")
        return int(score), reasons, has_model, has_pipeline


_ANALYZER_SINGLETON: Optional[ImpactAnalyzer] = None


def get_analyzer() -> ImpactAnalyzer:
    global _ANALYZER_SINGLETON
    if _ANALYZER_SINGLETON is None:
        _ANALYZER_SINGLETON = ImpactAnalyzer()
    return _ANALYZER_SINGLETON


def reset_analyzer() -> None:
    global _ANALYZER_SINGLETON
    _ANALYZER_SINGLETON = None


__all__ = [
    "ImpactAnalyzer",
    "ImpactReport",
    "NotificationPlan",
    "get_analyzer",
    "reset_analyzer",
    "RISK_HIGH",
    "RISK_MEDIUM",
]
