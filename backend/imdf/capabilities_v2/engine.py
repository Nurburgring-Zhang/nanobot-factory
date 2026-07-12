"""VDP-2026 v1.1 — Capability engine: registry, invocation, audit.

This module defines the core registry. Each Capability wraps an existing engine
method (or a thin adapter for it) and exposes a stable JSON-Schema description of
its inputs / outputs so that:

  - the Capability Registry UI can render an "operator catalogue" view;
  - the Workflow Builder v2 (R2) can compose capabilities into a DAG;
  - tests can validate inputs / outputs without calling the engine layer.

Thread-safety: the registry is read-mostly after bootstrap so we use a single
RLock for invocation log appends. SQLite is opened per-invocation against a
shared connection pool (Lazy init via the routes module).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH: Optional[Path] = None


def configure_db(path: Path) -> None:
    """Override the default invocation-log DB path. Used by API routes & tests."""
    global _DB_PATH
    _DB_PATH = Path(path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _init_db()


def get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        # default to <backend>/data/capabilities_v2.db
        backend_dir = Path(__file__).resolve().parent.parent.parent
        _DB_PATH = backend_dir / "data" / "capabilities_v2.db"
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _init_db()
    return _DB_PATH


def _conn() -> sqlite3.Connection:
    """Open a short-lived SQLite connection with WAL."""
    p = get_db_path()
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS invocations (
                id TEXT PRIMARY KEY,
                capability_id TEXT NOT NULL,
                inputs_json TEXT DEFAULT '{}',
                outputs_json TEXT DEFAULT '{}',
                status TEXT NOT NULL,
                error TEXT DEFAULT '',
                actor TEXT DEFAULT 'system',
                duration_ms INTEGER DEFAULT 0,
                ref_project_id TEXT DEFAULT '',
                ref_requirement_id TEXT DEFAULT '',
                ref_dataset_id TEXT DEFAULT '',
                ref_pack_id TEXT DEFAULT '',
                ref_delivery_id TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_invocation_cap
                ON invocations(capability_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_invocation_project
                ON invocations(ref_project_id, created_at);
            """
        )


class CapabilityCategory(str, Enum):
    PROJECT = "project"
    REQUIREMENT = "requirement"
    DATASET = "dataset"
    PACK = "pack"
    COLLECTION = "collection"
    ANNOTATION = "annotation"
    REVIEW = "review"
    QC = "qc"
    ACCEPTANCE = "acceptance"
    DELIVERY = "delivery"
    SCORING = "scoring"
    TAGGING = "tagging"
    CLEANING = "cleaning"
    CLASSIFICATION = "classification"
    SEARCH = "search"
    EVALUATION = "evaluation"
    EXPORT = "export"


@dataclass
class Capability:
    """A platform capability module."""

    id: str
    name: str
    category: CapabilityCategory
    description: str
    invoke: Callable[..., Dict[str, Any]]
    # JSON Schema for inputs — draft 2020-12 style (subset: type/required/properties)
    inputs_schema: Dict[str, Any] = field(default_factory=dict)
    # JSON Schema for outputs
    outputs_schema: Dict[str, Any] = field(default_factory=dict)
    # free-form keys used for catalogue filters
    tags: List[str] = field(default_factory=list)
    owner: str = "platform"
    version: str = "1.0.0"
    rate_limit_per_min: Optional[int] = None
    cost_unit: str = "call"
    # whether this cap emits a "domain event" the data-flow tracker can subscribe to
    emits_domain_event: bool = False
    # which domain event subject it emits (e.g. project.created / pack.transition)
    domain_event_subject: Optional[str] = None

    def describe(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value if isinstance(self.category, CapabilityCategory) else str(self.category),
            "description": self.description,
            "inputs_schema": self.inputs_schema,
            "outputs_schema": self.outputs_schema,
            "tags": self.tags,
            "owner": self.owner,
            "version": self.version,
            "rate_limit_per_min": self.rate_limit_per_min,
            "cost_unit": self.cost_unit,
            "emits_domain_event": self.emits_domain_event,
            "domain_event_subject": self.domain_event_subject,
        }


@dataclass
class CapabilityResult:
    capability_id: str
    status: str  # success | error | partial
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0
    invocation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    emitted_event: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class CapabilityValidationError(ValueError):
    """Raised when inputs fail the declared JSON-Schema."""


def _validate_inputs(cap: Capability, inputs: Dict[str, Any]) -> List[str]:
    """Lightweight JSON-Schema validator (covers type / required / properties).

    Returns a list of human-readable error messages. Empty list = valid.
    """
    errors: List[str] = []
    schema = cap.inputs_schema or {}
    required = schema.get("required", [])
    for key in required:
        if key not in inputs or inputs[key] is None:
            errors.append(f"missing required input '{key}'")

    props = schema.get("properties", {})
    for key, value in inputs.items():
        if key not in props:
            # allow extra keys — could become a strict policy later
            continue
        spec = props[key]
        expected_type = spec.get("type")
        if expected_type is None or value is None:
            continue
        py_type_match = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "object": dict,
            "array": list,
        }
        expected_py = py_type_match.get(expected_type)
        if expected_py is not None and not isinstance(value, expected_py):
            # bool isinstance int is True in Python — guard against it
            if expected_type == "integer" and isinstance(value, bool):
                errors.append(f"input '{key}' expected integer, got boolean")
            elif expected_type == "string" and not isinstance(value, str):
                errors.append(f"input '{key}' expected string, got {type(value).__name__}")
            elif expected_type != "string":
                errors.append(f"input '{key}' expected {expected_type}, got {type(value).__name__}")

        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"input '{key}' must be one of {spec['enum']}")
        if expected_type == "string" and isinstance(value, str):
            if "min_length" in spec and len(value) < spec["min_length"]:
                errors.append(f"input '{key}' shorter than min_length={spec['min_length']}")
            if "max_length" in spec and len(value) > spec["max_length"]:
                errors.append(f"input '{key}' longer than max_length={spec['max_length']}")
        if expected_type in ("integer", "number") and isinstance(value, (int, float)) and not isinstance(value, bool):
            if "min" in spec and value < spec["min"]:
                errors.append(f"input '{key}' below min={spec['min']}")
            if "max" in spec and value > spec["max"]:
                errors.append(f"input '{key}' above max={spec['max']}")
        if expected_type == "array" and isinstance(value, list):
            if "min_items" in spec and len(value) < spec["min_items"]:
                errors.append(f"input '{key}' has fewer items than min_items={spec['min_items']}")
            if "max_items" in spec and len(value) > spec["max_items"]:
                errors.append(f"input '{key}' has more items than max_items={spec['max_items']}")
    return errors


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class CapabilityRegistry:
    """In-memory + persisted registry of capability modules.

    The registry supports:

      - bootstrap (register built-in capabilities at startup)
      - discovery (list / get / search / filter)
      - invocation (validate inputs, call wrapped engine, persist audit row,
        emit domain event when applicable)
    """

    def __init__(self) -> None:
        self._caps: Dict[str, Capability] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self, cap: Capability) -> None:
        with self._lock:
            if not cap.id or not cap.invoke:
                raise ValueError("Capability requires both id and invoke callable")
            self._caps[cap.id] = cap

    def get(self, cap_id: str) -> Optional[Capability]:
        return self._caps.get(cap_id)

    def list_all(self) -> List[Capability]:
        with self._lock:
            return list(self._caps.values())

    def list_by_category(self, cat: CapabilityCategory) -> List[Capability]:
        with self._lock:
            return [c for c in self._caps.values() if c.category == cat]

    def list_categories(self) -> List[str]:
        seen = []
        with self._lock:
            for c in self._caps.values():
                tag = c.category.value if isinstance(c.category, CapabilityCategory) else str(c.category)
                if tag not in seen:
                    seen.append(tag)
        return seen

    def search(self, q: str) -> List[Capability]:
        q = (q or "").lower().strip()
        if not q:
            return self.list_all()
        out: List[Capability] = []
        with self._lock:
            for c in self._caps.values():
                if (
                    q in c.id.lower()
                    or q in c.name.lower()
                    or q in c.description.lower()
                    or any(q in t.lower() for t in c.tags)
                ):
                    out.append(c)
        return out

    def count(self) -> int:
        return len(self._caps)

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------
    def invoke(
        self,
        cap_id: str,
        inputs: Dict[str, Any],
        actor: str = "system",
        refs: Optional[Dict[str, str]] = None,
    ) -> CapabilityResult:
        cap = self.get(cap_id)
        if cap is None:
            return CapabilityResult(
                capability_id=cap_id,
                status="error",
                error=f"unknown capability '{cap_id}'",
            )

        # validate
        errs = _validate_inputs(cap, inputs)
        refs = refs or {}
        if errs:
            res = CapabilityResult(
                capability_id=cap_id,
                status="error",
                error="; ".join(errs),
            )
            # persist the validation error so audit is complete
            self._record(cap, inputs, res, actor=actor, refs=refs)
            return res

        started = time.perf_counter()
        try:
            outputs = cap.invoke(inputs) or {}
            if not isinstance(outputs, dict):
                outputs = {"value": outputs}
            duration_ms = int((time.perf_counter() - started) * 1000)
            emitted_subject = cap.domain_event_subject if cap.emits_domain_event else None
            res = CapabilityResult(
                capability_id=cap_id,
                status="success",
                outputs=outputs,
                duration_ms=duration_ms,
                emitted_event=emitted_subject,
            )
            self._record(cap, inputs, res, actor=actor, refs=refs)
            # fan out a domain event for the data-flow tracker
            if emitted_subject:
                from .dataflow import get_tracker

                get_tracker().record_event(
                    subject=emitted_subject,
                    payload=outputs,
                    actor=actor,
                    refs=refs,
                )
            return res
        except Exception as e:  # noqa: BLE001
            duration_ms = int((time.perf_counter() - started) * 1000)
            err = f"{type(e).__name__}: {e}"
            res = CapabilityResult(
                capability_id=cap_id,
                status="error",
                error=err,
                duration_ms=duration_ms,
            )
            self._record(cap, inputs, res, actor=actor, refs=refs)
            logger.warning("Capability %s failed: %s", cap_id, err)
            return res

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def _record(
        self,
        cap: Capability,
        inputs: Dict[str, Any],
        res: CapabilityResult,
        actor: str,
        refs: Dict[str, str],
    ) -> None:
        try:
            with _conn() as conn:
                conn.execute(
                    """
                    INSERT INTO invocations (
                        id, capability_id, inputs_json, outputs_json,
                        status, error, actor, duration_ms,
                        ref_project_id, ref_requirement_id, ref_dataset_id,
                        ref_pack_id, ref_delivery_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        res.invocation_id,
                        cap.id,
                        json.dumps(inputs, ensure_ascii=False, default=str),
                        json.dumps(res.outputs, ensure_ascii=False, default=str),
                        res.status,
                        res.error,
                        actor,
                        res.duration_ms,
                        refs.get("project_id", ""),
                        refs.get("requirement_id", ""),
                        refs.get("dataset_id", ""),
                        refs.get("pack_id", ""),
                        refs.get("delivery_id", ""),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
        except sqlite3.Error as e:
            logger.warning("Failed to persist invocation: %s", e)

    def list_invocations(
        self,
        cap_id: Optional[str] = None,
        ref_project_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM invocations WHERE 1=1"
        args: List[Any] = []
        if cap_id:
            sql += " AND capability_id = ?"
            args.append(cap_id)
        if ref_project_id:
            sql += " AND ref_project_id = ?"
            args.append(ref_project_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with _conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Catalogue (for the Capability Registry UI)
    # ------------------------------------------------------------------
    def catalogue(self) -> Dict[str, Any]:
        caps = [c.describe() for c in self.list_all()]
        by_cat: Dict[str, int] = {}
        for c in caps:
            by_cat[c["category"]] = by_cat.get(c["category"], 0) + 1
        return {
            "total": len(caps),
            "categories": by_cat,
            "items": caps,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_REGISTRY: Optional[CapabilityRegistry] = None


def get_registry() -> CapabilityRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CapabilityRegistry()
        register_default_capabilities(_REGISTRY)
    return _REGISTRY


def register_default_capabilities(reg: CapabilityRegistry) -> None:
    """Idempotently wire default capabilities into a registry.

    Definitions live in `definitions.py` so this file stays small.
    """
    from .definitions import _register_all  # noqa: WPS433 (lazy local)

    _register_all(reg)


def reset_registry_for_test() -> None:
    global _REGISTRY
    _REGISTRY = None


def build_default_registry() -> CapabilityRegistry:
    """Public alias — returns a freshly-bootstrapped registry without using the
    process-global singleton. Useful for tests / multi-process workers.
    """
    from .definitions import _register_all  # noqa: WPS433 (lazy local)

    reg = CapabilityRegistry()
    _register_all(reg)
    return reg
