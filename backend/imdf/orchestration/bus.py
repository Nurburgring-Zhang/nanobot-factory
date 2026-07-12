"""VDP-2026 R3-R10 — Cross-Module Orchestration Bus.

The bus is the platform's *single* place where every data-flow event lands:

  - capability_v2 invocations      → bus.record(...)  (already wired in engine.invoke)
  - pack transitions                → bus.record(...)
  - qc / review / acceptance / del  → bus.record(...)
  - workflow_builder node runs      → bus.record(...)
  - scoring / tagging / cleaning    → bus.record(...)

This module exposes:

  - ``event_bus``: singleton with ``record()`` / ``query()`` / ``stats()``
  - ``LineageLink``: a strongly-typed lineage record between two entities
                     (project → requirement → dataset → pack → annotation →
                      review → qc → acceptance → delivery → share)
  - ``CrossModuleStats``: aggregated counters used by the dashboard
  - HTTP endpoints that let the frontend query the entire platform as one
    coherent graph (``/api/v1/orchestration/...``)

The implementation is intentionally small and SQLite-backed; its purpose is
**visibility**, not new business logic — every capability/module that is
already in the codebase can drop a single ``record_event(...)`` call into
its engine to register on the bus.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = __import__("logging").getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_DB_PATH: Optional[Path] = None


def configure_db(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _init_db()


def get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        backend = Path(__file__).resolve().parent.parent.parent
        _DB_PATH = backend / "data" / "orchestration.db"
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
            CREATE TABLE IF NOT EXISTS bus_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                entity_type TEXT DEFAULT '',
                entity_id TEXT DEFAULT '',
                payload_json TEXT DEFAULT '{}',
                actor TEXT DEFAULT 'system',
                project_id TEXT DEFAULT '',
                requirement_id TEXT DEFAULT '',
                dataset_id TEXT DEFAULT '',
                pack_id TEXT DEFAULT '',
                delivery_id TEXT DEFAULT '',
                source_module TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_bus_topic ON bus_events(topic, created_at);
            CREATE INDEX IF NOT EXISTS idx_bus_entity ON bus_events(entity_type, entity_id);
            CREATE INDEX IF NOT EXISTS idx_bus_project ON bus_events(project_id);
            CREATE INDEX IF NOT EXISTS idx_bus_dataset ON bus_events(dataset_id);
            CREATE INDEX IF NOT EXISTS idx_bus_pack ON bus_events(pack_id);
            CREATE INDEX IF NOT EXISTS idx_bus_delivery ON bus_events(delivery_id);

            CREATE TABLE IF NOT EXISTS lineage_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_type TEXT NOT NULL,
                parent_id TEXT NOT NULL,
                child_type TEXT NOT NULL,
                child_id TEXT NOT NULL,
                relation TEXT NOT NULL,         -- created_for / derived_from / annotated_by / reviewed_by / qc_by / accepted_by / delivered_as / shared_via
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_line_parent ON lineage_links(parent_type, parent_id);
            CREATE INDEX IF NOT EXISTS idx_line_child ON lineage_links(child_type, child_id);
            """
        )


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class EntityType(str, Enum):
    PROJECT = "project"
    REQUIREMENT = "requirement"
    DATASET = "dataset"
    PACK = "pack"
    ANNOTATION = "annotation"
    REVIEW = "review"
    QC = "qc"
    ACCEPTANCE = "acceptance"
    DELIVERY = "delivery"
    SHARE = "share"
    SCORE = "score"
    TAG = "tag"
    CLEAN = "clean"
    CLASSIFY = "classify"
    EVAL = "eval"
    EXPORT = "export"
    WORKFLOW = "workflow"
    WORKFLOW_RUN = "workflow_run"


ENTITY_GROUPS = {
    "data_production_lifecycle": [
        EntityType.PROJECT, EntityType.REQUIREMENT, EntityType.DATASET,
        EntityType.PACK, EntityType.ANNOTATION, EntityType.REVIEW,
        EntityType.QC, EntityType.ACCEPTANCE, EntityType.DELIVERY,
        EntityType.SHARE,
    ],
    "data_quality": [
        EntityType.SCORE, EntityType.TAG, EntityType.CLEAN,
        EntityType.CLASSIFY, EntityType.EVAL, EntityType.EXPORT,
    ],
    "automation": [EntityType.WORKFLOW, EntityType.WORKFLOW_RUN],
}


RELATION_GRAPH: List[Tuple[EntityType, EntityType, str]] = [
    (EntityType.PROJECT, EntityType.REQUIREMENT, "fulfills"),
    (EntityType.REQUIREMENT, EntityType.DATASET, "specifies"),
    (EntityType.DATASET, EntityType.PACK, "packed_into"),
    (EntityType.PACK, EntityType.ANNOTATION, "annotated_by"),
    (EntityType.ANNOTATION, EntityType.REVIEW, "reviewed_by"),
    (EntityType.REVIEW, EntityType.QC, "qc_passed_by"),
    (EntityType.QC, EntityType.ACCEPTANCE, "accepted_by"),
    (EntityType.ACCEPTANCE, EntityType.DELIVERY, "delivered_as"),
    (EntityType.DELIVERY, EntityType.SHARE, "shared_via"),
    (EntityType.DATASET, EntityType.EXPORT, "exported_via"),
    (EntityType.DATASET, EntityType.SCORE, "scored_by"),
    (EntityType.DATASET, EntityType.CLEAN, "cleaned_via"),
    (EntityType.DATASET, EntityType.CLASSIFY, "classified_by"),
    (EntityType.DATASET, EntityType.EVAL, "evaluated_by"),
]


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------


@dataclass
class BusEvent:
    id: int = 0
    topic: str = ""
    entity_type: str = ""
    entity_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    actor: str = "system"
    project_id: str = ""
    requirement_id: str = ""
    dataset_id: str = ""
    pack_id: str = ""
    delivery_id: str = ""
    source_module: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LineageLink:
    parent_type: str
    parent_id: str
    child_type: str
    child_id: str
    relation: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EventBus:
    """Append-only event log + lineage registry.

    Modules push events whenever they touch a domain entity; readers can then
    query the full timeline across modules. The bus is **idempotent-friendly**
    (a duplicate event is fine — it only inflates counters) and never raises.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ----- write ------------------------------------------------------
    def record(
        self,
        topic: str,
        entity_type: str = "",
        entity_id: str = "",
        payload: Optional[Dict[str, Any]] = None,
        actor: str = "system",
        refs: Optional[Dict[str, str]] = None,
        source_module: str = "",
    ) -> int:
        refs = refs or {}
        try:
            with _conn() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO bus_events (
                        topic, entity_type, entity_id, payload_json,
                        actor, project_id, requirement_id, dataset_id, pack_id,
                        delivery_id, source_module, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        topic,
                        entity_type,
                        entity_id,
                        json.dumps(payload or {}, ensure_ascii=False, default=str),
                        actor,
                        refs.get("project_id", "") or "",
                        refs.get("requirement_id", "") or "",
                        refs.get("dataset_id", "") or "",
                        refs.get("pack_id", "") or "",
                        refs.get("delivery_id", "") or "",
                        source_module,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                return int(cur.lastrowid or 0)
        except sqlite3.Error as e:
            logger.warning("EventBus.record failed: %s", e)
            return 0

    def record_lineage(
        self,
        parent_type: str,
        parent_id: str,
        child_type: str,
        child_id: str,
        relation: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        try:
            with _conn() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO lineage_links (
                        parent_type, parent_id, child_type, child_id, relation,
                        metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        parent_type,
                        parent_id,
                        child_type,
                        child_id,
                        relation,
                        json.dumps(metadata or {}, ensure_ascii=False, default=str),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                return int(cur.lastrowid or 0)
        except sqlite3.Error as e:
            logger.warning("EventBus.record_lineage failed: %s", e)
            return 0

    # ----- read -------------------------------------------------------
    def query(
        self,
        topic: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        project_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        pack_id: Optional[str] = None,
        delivery_id: Optional[str] = None,
        source_module: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM bus_events WHERE 1=1"
        args: List[Any] = []
        if topic:
            sql += " AND topic = ?"
            args.append(topic)
        if entity_type:
            sql += " AND entity_type = ?"
            args.append(entity_type)
        if entity_id:
            sql += " AND entity_id = ?"
            args.append(entity_id)
        if project_id:
            sql += " AND project_id = ?"
            args.append(project_id)
        if dataset_id:
            sql += " AND dataset_id = ?"
            args.append(dataset_id)
        if pack_id:
            sql += " AND pack_id = ?"
            args.append(pack_id)
        if delivery_id:
            sql += " AND delivery_id = ?"
            args.append(delivery_id)
        if source_module:
            sql += " AND source_module = ?"
            args.append(source_module)
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

    def lineage_for(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        """Return both parents and children for the given entity."""
        with _conn() as conn:
            parents = conn.execute(
                "SELECT * FROM lineage_links WHERE child_type = ? AND child_id = ?",
                (entity_type, entity_id),
            ).fetchall()
            children = conn.execute(
                "SELECT * FROM lineage_links WHERE parent_type = ? AND parent_id = ?",
                (entity_type, entity_id),
            ).fetchall()
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "parents": [dict(r) for r in parents],
            "children": [dict(r) for r in children],
        }

    def stats(self) -> Dict[str, Any]:
        """High-level stats for the platform dashboard.

        Returns:
          - ``topics``  — { topic: count } across the entire platform
          - ``modules`` — { source_module: count }
          - ``projects`` — distinct project_id count
          - ``datasets`` — distinct dataset_id count
          - ``packs`` — distinct pack_id count
          - ``deliveries`` — distinct delivery_id count
          - ``total_events``
        """
        sql = "SELECT topic, source_module, project_id, dataset_id, pack_id, delivery_id FROM bus_events"
        with _conn() as conn:
            rows = conn.execute(sql).fetchall()
        topics: Dict[str, int] = defaultdict(int)
        modules: Dict[str, int] = defaultdict(int)
        projects: set = set()
        datasets: set = set()
        packs: set = set()
        deliveries: set = set()
        for r in rows:
            topics[r["topic"]] += 1
            if r["source_module"]:
                modules[r["source_module"]] += 1
            if r["project_id"]:
                projects.add(r["project_id"])
            if r["dataset_id"]:
                datasets.add(r["dataset_id"])
            if r["pack_id"]:
                packs.add(r["pack_id"])
            if r["delivery_id"]:
                deliveries.add(r["delivery_id"])
        return {
            "topics": dict(topics),
            "modules": dict(modules),
            "projects": len(projects),
            "datasets": len(datasets),
            "packs": len(packs),
            "deliveries": len(deliveries),
            "total_events": len(rows),
        }

    def lifecycle_summary(self) -> Dict[str, Any]:
        """Convenience: returns the per-stage event counts in the data
        production lifecycle.
        """
        rows = self.query(limit=10_000)
        bucket: Dict[str, int] = defaultdict(int)
        for r in rows:
            topic = r["topic"] or ""
            # topic format like: "project.created" / "pack.transitioned" — bucket by root.
            root = topic.split(".", 1)[0] if topic else "unknown"
            bucket[root] += 1
        return {"stages": dict(bucket), "total": sum(bucket.values())}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_BUS: Optional[EventBus] = None


def get_bus() -> EventBus:
    global _BUS
    if _BUS is None:
        _BUS = EventBus()
        # Backfill: we don't import modules here to keep this lightweight.
        # Cross-module wiring happens in `orchestration.bootstrap()`.
    return _BUS


def reset_bus_for_test() -> None:
    global _BUS
    _BUS = None


# ---------------------------------------------------------------------------
# Cross-module wiring — emit on bus whenever a known engine changes state.
# ---------------------------------------------------------------------------


def wire_capability_bus() -> None:
    """Make ``CapabilityRegistry.invoke`` push onto the bus.

    The capability registry already records audit rows and emits domain
    events (into DataFlowTracker). Here we additionally mirror each event into
    the cross-module bus so dashboards can read a single timeline.
    """
    from capabilities_v2.engine import get_registry as _reg

    bus = get_bus()
    reg = _reg()

    # Avoid double-wiring: skip if the engine already had our hook installed.
    if getattr(reg, "_bus_hooked", False):
        return
    setattr(reg, "_bus_hooked", True)

    original_invoke = reg.invoke

    def invoke_with_bus(cap_id, inputs, actor="system", refs=None):
        result = original_invoke(cap_id, inputs, actor=actor, refs=refs)
        try:
            # decompose the capability id (e.g. "project.create" → topic "project.created")
            root, _, verb = cap_id.partition(".")
            topic = f"{root}.{verb}ed" if not verb.endswith("ed") else f"{root}.{verb}"
            entity_id = ""
            entity_type = root
            for key in ("id", "project_id", "requirement_id", "dataset_id",
                        "pack_id", "delivery_id", "asset_id", "task_id",
                        "review_id", "qc_id", "acceptance_id", "share_token",
                        "eval_id"):
                if isinstance(result.outputs, dict) and key in result.outputs:
                    entity_id = str(result.outputs[key])
                    if entity_id:
                        break
            bus.record(
                topic=topic,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=result.outputs,
                actor=actor,
                refs=refs,
                source_module="capabilities_v2",
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("bus hook err: %s", e)
        return result

    reg.invoke = invoke_with_bus


def wire_workflow_builder_bus() -> None:
    """Mirror workflow-node runs onto the bus.

    Each step's invoke() will go through ``capabilities_v2`` (already wired
    above), so a *single* bus event per invocation is enough. Here we add an
    extra event for ``workflow.run.started`` / ``workflow.run.finished``.
    """
    from workflow_builder.engine import get_engine as _eng_factory

    bus = get_bus()
    eng = _eng_factory()

    if getattr(eng, "_bus_hooked", False):
        return
    setattr(eng, "_bus_hooked", True)

    original_run = eng.run_workflow

    def run_with_bus(workflow, actor="system", refs=None):
        run = original_run(workflow, actor=actor, refs=refs)
        try:
            bus.record(
                topic="workflow.run.finished" if run.status != "failed" else "workflow.run.failed",
                entity_type="workflow_run",
                entity_id=run.id,
                payload={
                    "workflow_id": workflow.id,
                    "name": workflow.name,
                    "status": run.status,
                    "steps": len(run.steps),
                },
                actor=actor,
                refs=refs,
                source_module="workflow_builder",
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("workflow bus hook err: %s", e)
        return run

    eng.run_workflow = run_with_bus


def bootstrap() -> None:
    """Wire all known modules to the bus."""
    try:
        wire_capability_bus()
    except Exception as e:  # noqa: BLE001
        logger.warning("capability bus wire failed: %s", e)
    try:
        wire_workflow_builder_bus()
    except Exception as e:  # noqa: BLE001
        logger.warning("workflow bus wire failed: %s", e)
