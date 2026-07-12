"""VDP-2026 v1.1 — Data Flow Tracker.

Traces the canonical 8-stage data production flow end-to-end:

  project → requirement → dataset → pack → annotation → review → qc
                                                                  ↓
                                                          acceptance → delivery → share

Capabilities emit domain events (subjects like `project.created`,
`pack.transitioned`, `delivery.shared`). The tracker records each event with
its caller-supplied `refs` (project_id / requirement_id / dataset_id /
pack_id / delivery_id) and reconstructs a per-stage snapshot.

The tracker is intentionally SQLite-backed so a flow can be exported as JSON
for audit chains / lineage tracing (already partly covered by lineage
engine — P4-4-W2).

This module is imported lazily by `engine.invoke` so an isolated unit test does
not pay SQLite cost unless it actually triggers an event.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = __import__("logging").getLogger(__name__)

_DB_PATH: Optional[Path] = None


def configure_db(path: Path) -> None:
    """Override the tracker DB path. Used by tests."""
    global _DB_PATH
    _DB_PATH = Path(path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _init_db()


def get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        backend_dir = Path(__file__).resolve().parent.parent.parent
        _DB_PATH = backend_dir / "data" / "dataflow.db"
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _init_db()
    return _DB_PATH


def _conn() -> sqlite3.Connection:
    p = get_db_path()
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS flow_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                payload_json TEXT DEFAULT '{}',
                actor TEXT DEFAULT 'system',
                project_id TEXT DEFAULT '',
                requirement_id TEXT DEFAULT '',
                dataset_id TEXT DEFAULT '',
                pack_id TEXT DEFAULT '',
                delivery_id TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_event_subject
                ON flow_events(subject, created_at);
            CREATE INDEX IF NOT EXISTS idx_event_project
                ON flow_events(project_id);
            CREATE INDEX IF NOT EXISTS idx_event_pack
                ON flow_events(pack_id);
            CREATE INDEX IF NOT EXISTS idx_event_delivery
                ON flow_events(delivery_id);
            """
        )


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


#: canonical 8-stage labels — also used by the frontend pipeline view
STAGES: List[Dict[str, str]] = [
    {"key": "project", "label": "项目", "color": "#5B8FF9"},
    {"key": "requirement", "label": "需求", "color": "#5AD8A6"},
    {"key": "dataset", "label": "数据集", "color": "#F6BD16"},
    {"key": "pack", "label": "数据包", "color": "#E8684A"},
    {"key": "annotation", "label": "标注", "color": "#6DC8EC"},
    {"key": "review", "label": "审核", "color": "#9270CA"},
    {"key": "qc", "label": "质检", "color": "#FF9D4D"},
    {"key": "acceptance", "label": "需求方验收", "color": "#269A99"},
    {"key": "delivery", "label": "交付", "color": "#FF99C3"},
]


#: map of subject -> stage, used to bucket domain events into the UI
SUBJECT_TO_STAGE: Dict[str, str] = {
    "project.created": "project",
    "project.updated": "project",
    "project.archived": "project",
    "requirement.created": "requirement",
    "requirement.updated": "requirement",
    "dataset.created": "dataset",
    "dataset.imported": "dataset",
    "dataset.exported": "dataset",
    "dataset.linked": "dataset",
    "pack.created": "pack",
    "pack.transitioned": "pack",
    "pack.routed": "pack",
    "collection.source_created": "pack",
    "collection.job_started": "pack",
    "collection.promoted": "pack",
    "annotation.task_pulled": "annotation",
    "annotation.submitted": "annotation",
    "review.started": "review",
    "review.decided": "review",
    "qc.started": "qc",
    "acceptance.created": "acceptance",
    "acceptance.decided": "acceptance",
    "delivery.shared": "delivery",
    "delivery.finalized": "delivery",
}


@dataclass
class DataFlowNode:
    """A single stage node in the lifecycle visualisation."""

    stage: str
    label: str
    color: str
    event_count: int = 0
    last_event_at: str = ""
    last_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DataFlowSnapshot:
    """A point-in-time rendering of one project/requirement/dataset flow."""

    project_id: Optional[str] = None
    requirement_id: Optional[str] = None
    dataset_id: Optional[str] = None
    pack_id: Optional[str] = None
    delivery_id: Optional[str] = None
    stages: List[DataFlowNode] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_events: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "requirement_id": self.requirement_id,
            "dataset_id": self.dataset_id,
            "pack_id": self.pack_id,
            "delivery_id": self.delivery_id,
            "stages": [s.to_dict() for s in self.stages],
            "timeline": self.timeline,
            "generated_at": self.generated_at,
            "total_events": self.total_events,
        }


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class DataFlowTracker:
    """Persist & query the canonical data-flow lifecycle."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def record_event(
        self,
        subject: str,
        payload: Dict[str, Any],
        actor: str = "system",
        refs: Optional[Dict[str, str]] = None,
    ) -> int:
        refs = refs or {}
        try:
            with _conn() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO flow_events (
                        subject, payload_json, actor,
                        project_id, requirement_id, dataset_id,
                        pack_id, delivery_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        subject,
                        json.dumps(payload or {}, ensure_ascii=False, default=str),
                        actor,
                        refs.get("project_id", "") or "",
                        refs.get("requirement_id", "") or "",
                        refs.get("dataset_id", "") or "",
                        refs.get("pack_id", "") or "",
                        refs.get("delivery_id", "") or "",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                return int(cur.lastrowid or 0)
        except sqlite3.Error as e:
            logger.warning("DataFlowTracker.record_event failed: %s", e)
            return 0

    def list_events(
        self,
        project_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM flow_events WHERE 1=1"
        args: List[Any] = []
        if project_id:
            sql += " AND project_id = ?"
            args.append(project_id)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with _conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json", "{}"))
            except (ValueError, TypeError):
                d["payload"] = {}
            out.append(d)
        return out

    def stages_summary(self) -> Dict[str, int]:
        """Return {stage_key: event_count} for the entire system — used by
        the high-level dashboard view.
        """
        rows = self.list_events(limit=10_000)
        bucket: Dict[str, int] = defaultdict(int)
        for r in rows:
            stage = SUBJECT_TO_STAGE.get(r["subject"], "project")
            bucket[stage] += 1
        return dict(bucket)

    def snapshot(
        self,
        project_id: Optional[str] = None,
        requirement_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        pack_id: Optional[str] = None,
        delivery_id: Optional[str] = None,
    ) -> DataFlowSnapshot:
        """Build a flow snapshot filtered by any combination of refs.

        The matching uses a strict precedence: when multiple refs are supplied,
        the narrowest one wins.
        """
        events = self.list_events(project_id=project_id, limit=10_000)

        def _matches(ev: Dict[str, Any]) -> bool:
            if project_id and ev.get("project_id") != project_id:
                return False
            if requirement_id and ev.get("requirement_id") != requirement_id:
                return False
            if dataset_id and ev.get("dataset_id") != dataset_id:
                return False
            if pack_id and ev.get("pack_id") != pack_id:
                return False
            if delivery_id and ev.get("delivery_id") != delivery_id:
                return False
            return True

        events = [e for e in events if _matches(e)]

        stage_nodes: Dict[str, DataFlowNode] = {}
        for stage in STAGES:
            stage_nodes[stage["key"]] = DataFlowNode(
                stage=stage["key"],
                label=stage["label"],
                color=stage["color"],
            )

        timeline: List[Dict[str, Any]] = []
        for ev in events:
            stage_key = SUBJECT_TO_STAGE.get(ev["subject"], "project")
            node = stage_nodes[stage_key]
            node.event_count += 1
            node.last_event_at = ev["created_at"]
            # list_events already JSON-decodes the payload into "payload"
            if isinstance(ev.get("payload"), dict):
                node.last_payload = ev["payload"]
            elif isinstance(ev.get("payload"), str):
                try:
                    node.last_payload = json.loads(ev["payload"])
                except (ValueError, TypeError):
                    pass
            timeline.append(
                {
                    "id": ev["id"],
                    "subject": ev["subject"],
                    "stage": stage_key,
                    "actor": ev["actor"],
                    "created_at": ev["created_at"],
                    "project_id": ev.get("project_id", ""),
                    "pack_id": ev.get("pack_id", ""),
                    "delivery_id": ev.get("delivery_id", ""),
                }
            )

        return DataFlowSnapshot(
            project_id=project_id,
            requirement_id=requirement_id,
            dataset_id=dataset_id,
            pack_id=pack_id,
            delivery_id=delivery_id,
            stages=[stage_nodes[s["key"]] for s in STAGES],
            timeline=sorted(timeline, key=lambda e: e["created_at"]),
            total_events=len(timeline),
        )

    def clear(self) -> None:
        with _conn() as conn:
            conn.execute("DELETE FROM flow_events")


_TRACKER: Optional[DataFlowTracker] = None


def get_tracker() -> DataFlowTracker:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = DataFlowTracker()
    return _TRACKER


def reset_tracker_for_test() -> None:
    global _TRACKER
    _TRACKER = None
