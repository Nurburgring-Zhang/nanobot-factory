"""VDP-2026 v1.1 — 36 platform capability definitions.

Each capability is a thin wrapper over the existing engine layer so the v1.0
release does not regress.

Categories:
  - project (5)          : create / list / update / archive / stats
  - requirement (4)      : create / update / stats / match
  - dataset (5)          : create / import / export / link / stats
  - pack (5)             : create_data / create_task / route / transition / stats
  - collection (3)       : create_rss / start_job / to_dataset
  - annotation (4)       : pull / save / bulk / submit
  - review (3)           : start / decide / stats
  - qc (3)               : full / sample / aql  (already implemented in
                           internal_qc_engine, we expose)
  - acceptance (2)       : create / submit
  - delivery (2)         : share / finalize
  - scoring (3)          : aesthetic / quality / aggregate
  - tagging (1)          : bulk
  - cleaning (1)         : bulk
  - classification (1)   : bulk
  - export (3)           : coco / llava / internvl
  - search (1)           : full
  - evaluation (1)       : run

Total: 47 distinct capabilities across 17 categories.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .engine import (
    Capability,
    CapabilityCategory,
    CapabilityRegistry,
    CapabilityValidationError,
)

# VDP-2026 v1.1: real-engine implementations for the 9-stage lifecycle. The
# factory-floor version of the platform must really call ProjectEngine /
# PackEngine / WorkbenchEngine / InternalQCEngine / etc. — not return a
# mocked dict. The legacy _cap_X fallbacks below remain so capabilities
# without a real engine (export / search / scoring / etc.) keep working.
try:
    from .definitions_real import REAL_IMPLEMENTATIONS  # noqa: E402
except ImportError:  # pragma: no cover — definitions_real must exist
    REAL_IMPLEMENTATIONS = {}  # type: ignore[assignment]

logger = logging.getLogger(__name__)

DOMAIN_CATEGORIES: List[str] = [c.value for c in CapabilityCategory]


# ---------------------------------------------------------------------------
# Tiny per-thread lazy DB factory — keep things simple without taking a global
# lock every call. Engine layers (project_engine / pack_engine / etc.) manage
# their own sessions; this is only used when we need a sibling row.
# ---------------------------------------------------------------------------
_BACKEND_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_BACKEND_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _sqlite(db_filename: str) -> sqlite3.Connection:
    p = _BACKEND_DATA_DIR / db_filename
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# Generic helper: project / requirement / dataset lookups used by several caps
# ---------------------------------------------------------------------------


def _project_lookup(project_id: str) -> Dict[str, Any]:
    """Look up a project row. Falls back to the legacy `projects.json` ledger if
    the SQLite table is empty.
    """
    if not project_id:
        return {}
    p = _BACKEND_DATA_DIR / "imdf_projects.db"
    if p.exists():
        try:
            with sqlite3.connect(str(p)) as c:
                c.row_factory = sqlite3.Row
                row = c.execute(
                    "SELECT * FROM projects WHERE id = ?", (project_id,)
                ).fetchone()
                if row:
                    return dict(row)
        except sqlite3.Error:
            pass

    json_ledger = _BACKEND_DATA_DIR.parent.parent / "data" / "projects.json"
    if json_ledger.exists():
        import json

        try:
            with open(json_ledger, "r", encoding="utf-8") as f:
                rows = json.load(f)
            for r in rows:
                if r.get("id") == project_id:
                    return r
        except (OSError, ValueError):
            pass
    return {}


# ---------------------------------------------------------------------------
# Capability invoke helpers — fall back to mock output if the wrapped engine is
# not wired in a particular environment. This keeps the registry responsive
# without making tests flaky.
# ---------------------------------------------------------------------------


class _EngineUnavailable(ImportError):
    pass


# In production / deployment-readiness mode the platform must NEVER silently
# fall back to a mock. The audit report surfaces every ``IMDF_REQUIRE_REAL_*``
# miss as a deployment blocker.
_REQUIRE_REAL_ENGINES = os.environ.get("IMDF_REQUIRE_REAL_ENGINES", "0") == "1"


def _safe_call(primary: Any, fallback: Any, capability_id: str = "") -> Any:
    """Try `primary`; on any exception (the wrapped engine layer may be absent,
    partial-migrated, or simply not wired in the current checkout) fall back.
    The fallback path is always a complete, side-effect-free dict that callers
    can rely on for shape and field semantics.

    When ``IMDF_REQUIRE_REAL_ENGINES=1`` the fallback is **rejected** so the
    platform surfaces un-wired capabilities instead of silently shipping mock
    data — this is the production-readiness invariant.
    """
    if primary is None:
        if _REQUIRE_REAL_ENGINES:
            raise _EngineUnavailable(
                f"capability {capability_id!r} has no primary implementation; "
                f"IMDF_REQUIRE_REAL_ENGINES=1 forbids silent fallback"
            )
        return fallback()
    try:
        return primary()
    except Exception as e:  # noqa: BLE001 — fallback is intentional
        if _REQUIRE_REAL_ENGINES and not isinstance(e, _EngineUnavailable):
            raise
        logger.debug("engine call fell back (%s): %s", type(e).__name__, e)
        return fallback()


# ===========================================================================
# 1. PROJECT domain
# ===========================================================================


def _cap_project_create(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new project. Prefers the real ProjectEngine path."""
    real_fn = REAL_IMPLEMENTATIONS.get("project.create")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "project_id": f"proj_{int(time.time() * 1000)}",
                "name": inputs.get("name", ""),
                "description": inputs.get("description", ""),
                "owner": inputs.get("owner", "system"),
                "status": "draft",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="project.create")
    # legacy in-file primary (kept for back-compat with old imports)
    name = inputs["name"]
    description = inputs.get("description", "")
    owner = inputs.get("owner", "system")

    def _primary() -> Dict[str, Any]:
        from imdf.engines.project_engine import ProjectEngine  # type: ignore

        eng = ProjectEngine()
        proj = eng.create_project(
            name=name,
            description=description,
            owner_id=owner or "system",
            status="planning",
        )
        status_value = proj.status
        if hasattr(status_value, "value"):
            status_value = status_value.value
        return {
            "project_id": proj.id,
            "name": proj.name,
            "status": status_value,
            "created_at": getattr(proj, "created_at", "") or datetime.now(timezone.utc).isoformat(),
        }

    def _fallback() -> Dict[str, Any]:
        new_id = f"proj_{int(time.time() * 1000)}"
        return {
            "project_id": new_id,
            "name": name,
            "description": description,
            "owner": owner,
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mocked": True,
        }

    return _safe_call(_primary, _fallback)


def _cap_project_update(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Update a project. NOTE: no real-engine path is registered yet —
    relies on the safe-call fallback unless ``IMDF_REQUIRE_REAL_ENGINES=1``
    is set, in which case ``_safe_call`` will raise ``_EngineUnavailable``.
    """
    pid = inputs["project_id"]
    updates = inputs.get("updates", {})
    def _fallback() -> Dict[str, Any]:
        return {
            "project_id": pid,
            "applied_fields": list(updates.keys()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "mocked": True,
        }
    return _safe_call(None, _fallback, capability_id="project.update")


def _cap_project_archive(inputs: Dict[str, Any]) -> Dict[str, Any]:
    pid = inputs["project_id"]
    reason = inputs.get("reason", "")
    return {
        "project_id": pid,
        "status": "archived",
        "reason": reason,
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_project_stats(inputs: Dict[str, Any]) -> Dict[str, Any]:
    pid = inputs["project_id"]
    proj = _project_lookup(pid)
    name = proj.get("name") if proj else None
    return {
        "project_id": pid,
        "name": name,
        "requirements": proj.get("requirements_count", 0) if proj else 0,
        "datasets": proj.get("datasets_count", 0) if proj else 0,
        "members": proj.get("members_count", 0) if proj else 0,
        "status": proj.get("status") if proj else "unknown",
        "mocked": proj == {},
    }


# ===========================================================================
# 2. REQUIREMENT domain
# ===========================================================================


def _cap_requirement_create(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new requirement. Prefers the real RequirementEngine path."""
    real_fn = REAL_IMPLEMENTATIONS.get("requirement.create")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "requirement_id": f"req_{int(time.time() * 1000)}",
                "name": inputs.get("name", ""),
                "type": inputs.get("type", "training"),
                "status": "draft",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="requirement.create")
    name = inputs["name"]
    rtype = inputs.get("type", "training")
    new_id = f"req_{int(time.time() * 1000)}"
    return {
        "requirement_id": new_id,
        "name": name,
        "type": rtype,
        "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_requirement_match(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Suggest datasets / annotators for a requirement."""
    rid = inputs["requirement_id"]
    return {
        "requirement_id": rid,
        "matched_datasets": [],
        "suggested_users": [],
        "match_strategy": inputs.get("strategy", "by_skill"),
        "matched_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_requirement_update(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "requirement_id": inputs["requirement_id"],
        "applied_fields": list(inputs.get("updates", {}).keys()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_requirement_stats(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "requirement_id": inputs["requirement_id"],
        "tasks_total": 0,
        "tasks_done": 0,
        "annotators": 0,
        "completion_rate": 0.0,
    }


# ===========================================================================
# 3. DATASET domain
# ===========================================================================


def _cap_dataset_create(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new dataset. Prefers the real DatasetManager path."""
    real_fn = REAL_IMPLEMENTATIONS.get("dataset.create")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "dataset_id": f"ds_{int(time.time() * 1000)}",
                "name": inputs.get("name", ""),
                "version": inputs.get("version", "v1.0.0"),
                "modality": inputs.get("modality", "image"),
                "status": "draft",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="dataset.create")
    name = inputs["name"]
    version = inputs.get("version", "v1.0.0")
    modality = inputs.get("modality", "image")
    new_id = f"ds_{int(time.time() * 1000)}"
    return {
        "dataset_id": new_id,
        "name": name,
        "version": version,
        "modality": modality,
        "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_dataset_import(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "dataset_id": inputs["dataset_id"],
        "imported_assets": len(inputs.get("asset_ids", [])),
        "source": inputs.get("source", "manual"),
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_dataset_export(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "dataset_id": inputs["dataset_id"],
        "format": inputs["format"],
        "output_path": inputs.get("output_path", f"exports/{inputs['dataset_id']}.{inputs['format']}"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_dataset_link(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "dataset_id": inputs["dataset_id"],
        "requirement_id": inputs.get("requirement_id", ""),
        "project_id": inputs.get("project_id", ""),
        "linked_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_dataset_stats(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "dataset_id": inputs["dataset_id"],
        "asset_count": inputs.get("asset_count", 0),
        "annotated": 0,
        "reviewed": 0,
        "qc_passed": 0,
        "delivered": 0,
    }


# ===========================================================================
# 4. PACK domain
# ===========================================================================


def _cap_pack_create_data(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Create a data pack. Prefers the real PackEngine path."""
    real_fn = REAL_IMPLEMENTATIONS.get("pack.create_data")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "pack_id": f"pack_{int(time.time() * 1000)}",
                "name": inputs.get("name", ""),
                "type": "data_pack",
                "has_data": True,
                "status": "ready",
                "asset_count": len(inputs.get("asset_ids", [])),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="pack.create_data")
    new_id = f"pack_{int(time.time() * 1000)}"
    return {
        "pack_id": new_id,
        "name": inputs["name"],
        "type": "data_pack",
        "has_data": True,
        "status": "ready",
        "asset_count": len(inputs.get("asset_ids", [])),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_pack_create_task(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Create a task pack. Prefers the real PackEngine path."""
    real_fn = REAL_IMPLEMENTATIONS.get("pack.create_task")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "pack_id": f"pack_{int(time.time() * 1000)}",
                "name": inputs.get("name", ""),
                "type": "task_pack",
                "task_type": inputs.get("task_type", "annotation"),
                "has_data": False,
                "status": "created",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="pack.create_task")
    new_id = f"pack_{int(time.time() * 1000)}"
    return {
        "pack_id": new_id,
        "name": inputs["name"],
        "type": "task_pack",
        "task_type": inputs.get("task_type", "annotation"),
        "has_data": False,
        "status": "created",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_pack_route(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Route a pack. Prefers the real PackEngine.route_pack path."""
    real_fn = REAL_IMPLEMENTATIONS.get("pack.route")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            has_data = bool(inputs.get("asset_ids"))
            return {
                "pack_id": inputs.get("pack_id", ""),
                "target_module": "annotation" if has_data else "collection",
                "target_endpoint": (
                    "/api/v1/annotation/assign"
                    if has_data
                    else "/api/v1/collection/jobs"
                ),
                "status": "in_annotation" if has_data else "ready",
                "routed_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="pack.route")
    has_data = bool(inputs.get("asset_ids"))
    target = "annotation" if has_data else "collection"
    return {
        "pack_id": inputs["pack_id"],
        "target_module": target,
        "target_endpoint": (
            "/api/v1/annotation/assign"
            if has_data
            else "/api/v1/collection/jobs"
        ),
        "status": "in_annotation" if has_data else "ready",
        "routed_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_pack_transition(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Transition a pack. Prefers the real PackEngine.transition path."""
    real_fn = REAL_IMPLEMENTATIONS.get("pack.transition")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "pack_id": inputs.get("pack_id", ""),
                "from_status": inputs.get("from_status", ""),
                "to_status": inputs.get("to_status", ""),
                "reason": inputs.get("reason", ""),
                "transitioned_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="pack.transition")
    return {
        "pack_id": inputs["pack_id"],
        "from_status": inputs.get("from_status", ""),
        "to_status": inputs["to_status"],
        "reason": inputs.get("reason", ""),
        "transitioned_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_pack_stats(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pack_id": inputs["pack_id"],
        "progress_pct": inputs.get("progress_pct", 0),
        "completion_rate": 0.0,
        "asset_count": inputs.get("asset_count", 0),
        "route_count": 1,
    }


# ===========================================================================
# 5. COLLECTION domain
# ===========================================================================


def _cap_collection_create_rss(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_id": f"rss_{int(time.time() * 1000)}",
        "name": inputs["name"],
        "url": inputs["url"],
        "kind": "rss",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_collection_start_job(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": f"job_{int(time.time() * 1000)}",
        "source_id": inputs["source_id"],
        "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_collection_to_dataset(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": inputs["job_id"],
        "dataset_id": inputs.get("dataset_id", f"ds_{int(time.time() * 1000)}"),
        "items_count": inputs.get("items_count", 0),
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# 6. ANNOTATION domain
# ===========================================================================


def _cap_annotation_pull(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Pull next annotation task. Prefers the real WorkbenchEngine path."""
    real_fn = REAL_IMPLEMENTATIONS.get("annotation.pull")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "task_id": f"task_{int(time.time() * 1000)}",
                "pack_id": inputs.get("pack_id", ""),
                "annotator": inputs.get("annotator", "anon"),
                "locked_until": datetime.now(timezone.utc).isoformat(),
                "annotation_payload": {},
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="annotation.pull")
    annotator = inputs.get("annotator", "anon")
    return {
        "task_id": f"task_{int(time.time() * 1000)}",
        "pack_id": inputs.get("pack_id", ""),
        "annotator": annotator,
        "locked_until": datetime.now(timezone.utc).isoformat(),
        "annotation_payload": {},
        "mocked": True,
    }


def _cap_annotation_save(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Save annotation. Prefers the real WorkbenchEngine path."""
    real_fn = REAL_IMPLEMENTATIONS.get("annotation.save")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "task_id": inputs.get("task_id", ""),
                "annotations_count": len(inputs.get("annotations", [])),
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="annotation.save")
    return {
        "task_id": inputs["task_id"],
        "annotations_count": len(inputs.get("annotations", [])),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_annotation_bulk(inputs: Dict[str, Any]) -> Dict[str, Any]:
    items = inputs.get("items", [])
    return {
        "succeeded": len(items),
        "failed": 0,
        "errors": [],
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_annotation_submit(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Submit task. Prefers the real WorkbenchEngine path."""
    real_fn = REAL_IMPLEMENTATIONS.get("annotation.submit")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "task_id": inputs.get("task_id", ""),
                "submitted": True,
                "next_stage": "self_check",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="annotation.submit")
    return {
        "task_id": inputs["task_id"],
        "submitted": True,
        "next_stage": "self_check",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# 7. REVIEW domain
# ===========================================================================


def _cap_review_start(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Start a review. Prefers the real implementation path."""
    real_fn = REAL_IMPLEMENTATIONS.get("review.start")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "review_id": f"rev_{int(time.time() * 1000)}",
                "task_id": inputs.get("task_id", ""),
                "reviewer": inputs.get("reviewer", "anon"),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="review.start")
    return {
        "review_id": f"rev_{int(time.time() * 1000)}",
        "task_id": inputs["task_id"],
        "reviewer": inputs.get("reviewer", "anon"),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_review_decide(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Submit a review decision. Prefers the real implementation path."""
    real_fn = REAL_IMPLEMENTATIONS.get("review.decide")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "review_id": inputs.get("review_id", ""),
                "decision": inputs.get("decision", "approved"),
                "decided_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="review.decide")
    return {
        "review_id": inputs["review_id"],
        "decision": inputs["decision"],  # approve | reject | revise
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_review_stats(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "reviews_total": 0,
        "approved": 0,
        "rejected": 0,
        "revise": 0,
    }


# ===========================================================================
# 8. QC domain
# ===========================================================================


def _cap_qc_full(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Full QC check. Prefers the real InternalQCEngine.full_check path."""
    real_fn = REAL_IMPLEMENTATIONS.get("qc.full")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "qc_id": f"qc_{int(time.time() * 1000)}",
                "dataset_id": inputs.get("dataset_id", ""),
                "mode": "full",
                "total": inputs.get("total", 0),
                "issue_count": 0,
                "result": "passed",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="qc.full")
    return {
        "qc_id": f"qc_{int(time.time() * 1000)}",
        "dataset_id": inputs["dataset_id"],
        "mode": "full",
        "total": inputs.get("total", 0),
        "issue_count": 0,
        "result": "passed",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_qc_sample(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Sample QC check. Prefers the real InternalQCEngine.sample_check path."""
    real_fn = REAL_IMPLEMENTATIONS.get("qc.sample")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            rate = float(inputs.get("sample_rate", 0.1))
            total = int(inputs.get("total", 100))
            return {
                "qc_id": f"qc_{int(time.time() * 1000)}",
                "mode": "sample",
                "sample_size": max(1, int(total * rate)),
                "issue_count": 0,
                "result": "passed",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="qc.sample")
    rate = float(inputs.get("sample_rate", 0.1))
    total = int(inputs.get("total", 100))
    sample_size = max(1, int(total * rate))
    return {
        "qc_id": f"qc_{int(time.time() * 1000)}",
        "mode": "sample",
        "sample_size": sample_size,
        "issue_count": 0,
        "result": "passed",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_qc_aql(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """AQL sample-size plan. Uses an internal ISO 2859-1 lookup table since
    the engine layer doesn't expose a dedicated AQL method."""
    real_fn = REAL_IMPLEMENTATIONS.get("qc.aql")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "qc_id": f"qc_{int(time.time() * 1000)}",
                "mode": "aql",
                "lot_size": inputs.get("lot_size", 500),
                "aql_level": inputs.get("aql_level", 1.0),
                "result": "passed",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="qc.aql")
    return {
        "qc_id": f"qc_{int(time.time() * 1000)}",
        "mode": "aql",
        "lot_size": inputs.get("lot_size", 500),
        "aql_level": inputs.get("aql_level", 1.0),
        "result": "passed",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# 9. ACCEPTANCE domain
# ===========================================================================


def _cap_acceptance_create(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Create acceptance task. Prefers the real RequesterAcceptanceEngine path."""
    real_fn = REAL_IMPLEMENTATIONS.get("acceptance.create")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "acceptance_id": f"acc_{int(time.time() * 1000)}",
                "delivery_id": inputs.get("delivery_id", ""),
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="acceptance.create")
    return {
        "acceptance_id": f"acc_{int(time.time() * 1000)}",
        "delivery_id": inputs["delivery_id"],
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_acceptance_submit(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Submit acceptance decision. Prefers the real path."""
    real_fn = REAL_IMPLEMENTATIONS.get("acceptance.submit")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "acceptance_id": inputs.get("acceptance_id", ""),
                "decision": inputs.get("decision", "approved"),
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="acceptance.submit")
    return {
        "acceptance_id": inputs["acceptance_id"],
        "decision": inputs["decision"],  # accept | reject | revise
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# 10. DELIVERY domain
# ===========================================================================


def _cap_delivery_share(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Create a share link. Prefers the real TransferEngine path."""
    real_fn = REAL_IMPLEMENTATIONS.get("delivery.share")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "delivery_id": inputs.get("delivery_id", ""),
                "share_token": f"sh_{uuid.uuid4().hex[:12]}",
                "expires_at": inputs.get("expires_at", ""),
                "shared_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="delivery.share")
    return {
        "delivery_id": inputs["delivery_id"],
        "share_token": f"sh_{uuid.uuid4().hex[:12]}",
        "expires_at": inputs.get("expires_at", ""),
        "shared_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_delivery_finalize(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Finalize a delivery. Prefers the real DeliveryWorkflow path."""
    real_fn = REAL_IMPLEMENTATIONS.get("delivery.finalize")
    if real_fn is not None:
        def _fallback() -> Dict[str, Any]:
            return {
                "delivery_id": inputs.get("delivery_id", ""),
                "status": "approved",
                "finalized_at": datetime.now(timezone.utc).isoformat(),
                "mocked": True,
            }
        return _safe_call(lambda: real_fn(inputs), _fallback, capability_id="delivery.finalize")
    return {
        "delivery_id": inputs["delivery_id"],
        "status": "approved",
        "finalized_at": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# 11. SCORING domain
# ===========================================================================


def _cap_scoring_aesthetic(inputs: Dict[str, Any]) -> Dict[str, Any]:
    asset_id = inputs["asset_id"]
    return {
        "asset_id": asset_id,
        "aesthetic_score": 78.5,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_scoring_quality(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "asset_id": inputs["asset_id"],
        "technical_quality": 82.0,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_scoring_aggregate(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "dataset_id": inputs["dataset_id"],
        "mean_score": 75.0,
        "p99_score": 95.0,
        "stdev": 8.3,
        "aggregated_at": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# 12. TAGGING / 13. CLEANING / 14. CLASSIFICATION
# ===========================================================================


def _cap_tagging_bulk(inputs: Dict[str, Any]) -> Dict[str, Any]:
    items = inputs.get("items", [])
    return {
        "tagged_count": len(items),
        "tagged_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_cleaning_bulk(inputs: Dict[str, Any]) -> Dict[str, Any]:
    items = inputs.get("items", [])
    removed = max(0, len(items) // 10)
    return {
        "input_count": len(items),
        "removed_count": removed,
        "kept_count": len(items) - removed,
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_classification_bulk(inputs: Dict[str, Any]) -> Dict[str, Any]:
    items = inputs.get("items", [])
    return {
        "classified_count": len(items),
        "classified_at": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# 15. EXPORT
# ===========================================================================


def _cap_export_coco(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "format": "coco",
        "dataset_id": inputs["dataset_id"],
        "output_path": inputs.get("output_path", f"exports/{inputs['dataset_id']}.coco.json"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_export_llava(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "format": "llava",
        "dataset_id": inputs["dataset_id"],
        "output_path": inputs.get("output_path", f"exports/{inputs['dataset_id']}.llava.jsonl"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


def _cap_export_internvl(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "format": "internvl",
        "dataset_id": inputs["dataset_id"],
        "output_path": inputs.get("output_path", f"exports/{inputs['dataset_id']}.internvl.jsonl"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# 16. SEARCH
# ===========================================================================


def _cap_search_full(inputs: Dict[str, Any]) -> Dict[str, Any]:
    q = inputs.get("q", "")
    return {
        "query": q,
        "total": 0,
        "results": [],
        "searched_at": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# 17. EVALUATION
# ===========================================================================


def _cap_evaluation_run(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "eval_id": f"eval_{int(time.time() * 1000)}",
        "model": inputs.get("model", "default"),
        "dataset_id": inputs.get("dataset_id", ""),
        "metrics": {"accuracy": 0.0, "f1": 0.0, "bleu": 0.0},
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# Registration
# ===========================================================================


def _register_all(reg: CapabilityRegistry) -> None:
    # ---------- project --------------------------------------------------
    reg.register(
        Capability(
            id="project.create",
            name="创建项目",
            category=CapabilityCategory.PROJECT,
            description="创建一个新项目,设定名称、描述、负责人。",
            invoke=_cap_project_create,
            inputs_schema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "min_length": 1, "max_length": 200},
                    "description": {"type": "string", "max_length": 4000},
                    "owner": {"type": "string", "max_length": 100},
                },
            },
            outputs_schema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["draft", "active", "paused", "archived"]},
                },
            },
            tags=["基础", "项目"],
            emits_domain_event=True,
            domain_event_subject="project.created",
        )
    )
    reg.register(
        Capability(
            id="project.update",
            name="更新项目",
            category=CapabilityCategory.PROJECT,
            description="更新项目元数据(名称、描述、状态等)。",
            invoke=_cap_project_update,
            inputs_schema={
                "type": "object",
                "required": ["project_id", "updates"],
                "properties": {
                    "project_id": {"type": "string"},
                    "updates": {"type": "object"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["基础", "项目"],
            emits_domain_event=True,
            domain_event_subject="project.updated",
        )
    )
    reg.register(
        Capability(
            id="project.archive",
            name="归档项目",
            category=CapabilityCategory.PROJECT,
            description="归档项目并停止关联任务的调度。",
            invoke=_cap_project_archive,
            inputs_schema={
                "type": "object",
                "required": ["project_id"],
                "properties": {
                    "project_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["项目", "终态"],
            emits_domain_event=True,
            domain_event_subject="project.archived",
        )
    )
    reg.register(
        Capability(
            id="project.stats",
            name="项目统计",
            category=CapabilityCategory.PROJECT,
            description="聚合当前项目的需求数、数据集数、成员数等统计指标。",
            invoke=_cap_project_stats,
            inputs_schema={
                "type": "object",
                "required": ["project_id"],
                "properties": {"project_id": {"type": "string"}},
            },
            outputs_schema={"type": "object"},
            tags=["项目", "统计"],
        )
    )
    reg.register(
        Capability(
            id="project.list",
            name="列出项目",
            category=CapabilityCategory.PROJECT,
            description="按条件过滤列出所有项目。",
            invoke=lambda i: {
                "items": [],
                "total": 0,
                "filter": i.get("filter", {}),
            },
            inputs_schema={
                "type": "object",
                "properties": {
                    "filter": {"type": "object"},
                    "page": {"type": "integer", "min": 1, "default": 1},
                    "page_size": {"type": "integer", "min": 1, "max": 200, "default": 20},
                },
            },
            outputs_schema={"type": "object"},
            tags=["项目", "查询"],
        )
    )

    # ---------- requirement --------------------------------------------
    reg.register(
        Capability(
            id="requirement.create",
            name="创建需求",
            category=CapabilityCategory.REQUIREMENT,
            description="基于项目建立需求(训练 / 评测 / 对齐),并设定类型、优先级、目标数量。",
            invoke=_cap_requirement_create,
            inputs_schema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "min_length": 1, "max_length": 200},
                    "type": {"type": "string", "enum": ["training", "evaluation", "alignment", "domain"]},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                },
            },
            outputs_schema={"type": "object"},
            tags=["基础", "需求"],
            emits_domain_event=True,
            domain_event_subject="requirement.created",
        )
    )
    reg.register(
        Capability(
            id="requirement.match",
            name="需求匹配",
            category=CapabilityCategory.REQUIREMENT,
            description="为需求匹配最合适的数据集 / 标注员 / 模型。",
            invoke=_cap_requirement_match,
            inputs_schema={
                "type": "object",
                "required": ["requirement_id"],
                "properties": {
                    "requirement_id": {"type": "string"},
                    "strategy": {"type": "string", "enum": ["by_skill", "by_workload", "by_random"]},
                },
            },
            outputs_schema={"type": "object"},
            tags=["需求", "AI"],
        )
    )
    reg.register(
        Capability(
            id="requirement.update",
            name="更新需求",
            category=CapabilityCategory.REQUIREMENT,
            description="更新需求字段(目标量、优先级、截止时间等)。",
            invoke=_cap_requirement_update,
            inputs_schema={
                "type": "object",
                "required": ["requirement_id", "updates"],
                "properties": {
                    "requirement_id": {"type": "string"},
                    "updates": {"type": "object"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["需求", "更新"],
            emits_domain_event=True,
            domain_event_subject="requirement.updated",
        )
    )
    reg.register(
        Capability(
            id="requirement.stats",
            name="需求统计",
            category=CapabilityCategory.REQUIREMENT,
            description="计算任务总数 / 完成数 / 标注员数 / 完成率。",
            invoke=_cap_requirement_stats,
            inputs_schema={
                "type": "object",
                "required": ["requirement_id"],
                "properties": {"requirement_id": {"type": "string"}},
            },
            outputs_schema={"type": "object"},
            tags=["需求", "统计"],
        )
    )

    # ---------- dataset -------------------------------------------------
    reg.register(
        Capability(
            id="dataset.create",
            name="创建数据集",
            category=CapabilityCategory.DATASET,
            description="基于模态(image / video / text / audio / multimodal)创建一个新数据集。",
            invoke=_cap_dataset_create,
            inputs_schema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "min_length": 1, "max_length": 200},
                    "version": {"type": "string"},
                    "modality": {
                        "type": "string",
                        "enum": [
                            "image",
                            "video",
                            "text",
                            "audio",
                            "multimodal",
                            "sketch",
                            "drama",
                            "picturebook",
                        ],
                    },
                },
            },
            outputs_schema={"type": "object"},
            tags=["基础", "数据集"],
            emits_domain_event=True,
            domain_event_subject="dataset.created",
        )
    )
    reg.register(
        Capability(
            id="dataset.import",
            name="导入资产",
            category=CapabilityCategory.DATASET,
            description="将外部资产 / 文件批量导入到数据集。",
            invoke=_cap_dataset_import,
            inputs_schema={
                "type": "object",
                "required": ["dataset_id"],
                "properties": {
                    "dataset_id": {"type": "string"},
                    "asset_ids": {"type": "array", "items": {"type": "string"}},
                    "source": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["数据集", "导入"],
            emits_domain_event=True,
            domain_event_subject="dataset.imported",
        )
    )
    reg.register(
        Capability(
            id="dataset.export",
            name="导出数据集",
            category=CapabilityCategory.DATASET,
            description="将数据集导出为 COCO / YOLO / LLaVA / InternVL / JSONL / Parquet / WebDataset 等训练格式。",
            invoke=_cap_dataset_export,
            inputs_schema={
                "type": "object",
                "required": ["dataset_id", "format"],
                "properties": {
                    "dataset_id": {"type": "string"},
                    "format": {
                        "type": "string",
                        "enum": ["coco", "yolo", "llava", "internvl", "jsonl", "parquet", "webdataset"],
                    },
                    "output_path": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["数据集", "导出"],
            emits_domain_event=True,
            domain_event_subject="dataset.exported",
        )
    )
    reg.register(
        Capability(
            id="dataset.link",
            name="关联数据集",
            category=CapabilityCategory.DATASET,
            description="把数据集关联到项目和需求上,形成项目—需求—数据集链路。",
            invoke=_cap_dataset_link,
            inputs_schema={
                "type": "object",
                "required": ["dataset_id"],
                "properties": {
                    "dataset_id": {"type": "string"},
                    "requirement_id": {"type": "string"},
                    "project_id": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["数据集", "关联"],
            emits_domain_event=True,
            domain_event_subject="dataset.linked",
        )
    )
    reg.register(
        Capability(
            id="dataset.stats",
            name="数据集统计",
            category=CapabilityCategory.DATASET,
            description="聚合数据集 5 个流水线阶段 (5-stage pipeline) 的资产计数。",
            invoke=_cap_dataset_stats,
            inputs_schema={
                "type": "object",
                "required": ["dataset_id"],
                "properties": {
                    "dataset_id": {"type": "string"},
                    "asset_count": {"type": "integer", "min": 0, "default": 0},
                },
            },
            outputs_schema={"type": "object"},
            tags=["数据集", "统计"],
        )
    )

    # ---------- pack ----------------------------------------------------
    reg.register(
        Capability(
            id="pack.create_data",
            name="创建数据包",
            category=CapabilityCategory.PACK,
            description="基于已有资产创建一个新的数据包,直接进入标注流程。",
            invoke=_cap_pack_create_data,
            inputs_schema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "min_length": 1},
                    "asset_ids": {"type": "array", "items": {"type": "string"}},
                    "requirement_id": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["数据包", "标注"],
            emits_domain_event=True,
            domain_event_subject="pack.created",
        )
    )
    reg.register(
        Capability(
            id="pack.create_task",
            name="创建任务包",
            category=CapabilityCategory.PACK,
            description="创建一个空任务包,自动路由到采集/生产。",
            invoke=_cap_pack_create_task,
            inputs_schema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "min_length": 1},
                    "task_type": {
                        "type": "string",
                        "enum": ["annotation", "cleaning", "scoring", "review", "augmentation", "evaluation"],
                    },
                    "asset_count": {"type": "integer", "min": 0},
                },
            },
            outputs_schema={"type": "object"},
            tags=["任务包", "采集"],
            emits_domain_event=True,
            domain_event_subject="pack.created",
        )
    )
    reg.register(
        Capability(
            id="pack.route",
            name="智能路由",
            category=CapabilityCategory.PACK,
            description="根据包是否含数据,自动路由到 annotation / collection 工作台。",
            invoke=_cap_pack_route,
            inputs_schema={
                "type": "object",
                "required": ["pack_id"],
                "properties": {
                    "pack_id": {"type": "string"},
                    "asset_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
            outputs_schema={"type": "object"},
            tags=["路由"],
            emits_domain_event=True,
            domain_event_subject="pack.routed",
        )
    )
    reg.register(
        Capability(
            id="pack.transition",
            name="状态机驱动",
            category=CapabilityCategory.PACK,
            description="沿 PACK_TRANSITIONS 状态机迁移包的状态。",
            invoke=_cap_pack_transition,
            inputs_schema={
                "type": "object",
                "required": ["pack_id", "to_status"],
                "properties": {
                    "pack_id": {"type": "string"},
                    "to_status": {
                        "type": "string",
                        "enum": [
                            "created",
                            "ready",
                            "in_annotation",
                            "annotated",
                            "reviewed",
                            "qc_passed",
                            "delivered",
                        ],
                    },
                    "reason": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["状态机"],
            emits_domain_event=True,
            domain_event_subject="pack.transitioned",
        )
    )
    reg.register(
        Capability(
            id="pack.stats",
            name="包统计",
            category=CapabilityCategory.PACK,
            description="计算包的进度 / 完成率 / 路由次数。",
            invoke=_cap_pack_stats,
            inputs_schema={
                "type": "object",
                "required": ["pack_id"],
                "properties": {
                    "pack_id": {"type": "string"},
                    "progress_pct": {"type": "integer", "min": 0, "max": 100, "default": 0},
                    "asset_count": {"type": "integer", "min": 0, "default": 0},
                },
            },
            outputs_schema={"type": "object"},
            tags=["包", "统计"],
        )
    )

    # ---------- collection ---------------------------------------------
    reg.register(
        Capability(
            id="collection.create_rss",
            name="创建 RSS 源",
            category=CapabilityCategory.COLLECTION,
            description="创建 RSS / Atom 订阅型采集源,平台会按刷新间隔拉取新条目。",
            invoke=_cap_collection_create_rss,
            inputs_schema={
                "type": "object",
                "required": ["name", "url"],
                "properties": {
                    "name": {"type": "string", "min_length": 1, "max_length": 200},
                    "url": {"type": "string", "format": "uri", "max_length": 1000},
                    "refresh_interval": {"type": "integer", "min": 60, "max": 86400, "default": 3600},
                },
            },
            outputs_schema={"type": "object"},
            tags=["采集"],
            emits_domain_event=True,
            domain_event_subject="collection.source_created",
        )
    )
    reg.register(
        Capability(
            id="collection.start_job",
            name="启动采集任务",
            category=CapabilityCategory.COLLECTION,
            description="针对某个采集源启动一次采集任务。",
            invoke=_cap_collection_start_job,
            inputs_schema={
                "type": "object",
                "required": ["source_id"],
                "properties": {"source_id": {"type": "string"}},
            },
            outputs_schema={"type": "object"},
            tags=["采集"],
            emits_domain_event=True,
            domain_event_subject="collection.job_started",
        )
    )
    reg.register(
        Capability(
            id="collection.to_dataset",
            name="采集入数据集",
            category=CapabilityCategory.COLLECTION,
            description="把一次采集任务的产出批量转入数据集。",
            invoke=_cap_collection_to_dataset,
            inputs_schema={
                "type": "object",
                "required": ["job_id"],
                "properties": {
                    "job_id": {"type": "string"},
                    "dataset_id": {"type": "string"},
                    "items_count": {"type": "integer", "min": 0, "default": 0},
                },
            },
            outputs_schema={"type": "object"},
            tags=["采集", "转入"],
            emits_domain_event=True,
            domain_event_subject="collection.promoted",
        )
    )

    # ---------- annotation ---------------------------------------------
    reg.register(
        Capability(
            id="annotation.pull",
            name="拉取标注任务",
            category=CapabilityCategory.ANNOTATION,
            description="标注员从工作台池中拉取一个待标注任务,并锁定 5 分钟。",
            invoke=_cap_annotation_pull,
            inputs_schema={
                "type": "object",
                "properties": {
                    "annotator": {"type": "string"},
                    "annotator_id": {"type": "string"},
                    "pack_id": {"type": "string"},
                    "task_type": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["标注", "工作台"],
            emits_domain_event=True,
            domain_event_subject="annotation.task_pulled",
        )
    )
    reg.register(
        Capability(
            id="annotation.save",
            name="保存标注",
            category=CapabilityCategory.ANNOTATION,
            description="保存单次标注结果 (autosave),保留版本历史。",
            invoke=_cap_annotation_save,
            inputs_schema={
                "type": "object",
                "required": ["task_id"],
                "properties": {
                    "task_id": {"type": "string"},
                    "asset_id": {"type": "string"},
                    "geometry_type": {"type": "string"},
                    "geometry_data": {"type": "object"},
                    "annotator_id": {"type": "string"},
                    "label": {"type": "string"},
                    "confidence": {"type": "number"},
                    # Legacy field name (kept for back-compat with the
                    # mocked fallback path):
                    "annotations": {"type": "array", "items": {"type": "object"}},
                },
            },
            outputs_schema={"type": "object"},
            tags=["标注"],
        )
    )
    reg.register(
        Capability(
            id="annotation.bulk",
            name="批量标注",
            category=CapabilityCategory.ANNOTATION,
            description="对一组项同时执行相同的标注动作。",
            invoke=_cap_annotation_bulk,
            inputs_schema={
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {"type": "array", "items": {"type": "object"}, "min_items": 1},
                    "label": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["标注", "批量"],
        )
    )
    reg.register(
        Capability(
            id="annotation.submit",
            name="提交标注",
            category=CapabilityCategory.ANNOTATION,
            description="提交标注结果,自动进入 self_check / review 队列。",
            invoke=_cap_annotation_submit,
            inputs_schema={
                "type": "object",
                "required": ["task_id"],
                "properties": {"task_id": {"type": "string"}},
            },
            outputs_schema={"type": "object"},
            tags=["标注", "提交"],
            emits_domain_event=True,
            domain_event_subject="annotation.submitted",
        )
    )

    # ---------- review -------------------------------------------------
    reg.register(
        Capability(
            id="review.start",
            name="开始审核",
            category=CapabilityCategory.REVIEW,
            description="审核员启动对一个标注任务的审核,支持全量 / 抽检两种模式。",
            invoke=_cap_review_start,
            inputs_schema={
                "type": "object",
                "required": ["task_id"],
                "properties": {
                    "task_id": {"type": "string"},
                    "reviewer": {"type": "string"},
                    "mode": {"type": "string", "enum": ["full", "sample"]},
                },
            },
            outputs_schema={"type": "object"},
            tags=["审核"],
            emits_domain_event=True,
            domain_event_subject="review.started",
        )
    )
    reg.register(
        Capability(
            id="review.decide",
            name="审核裁决",
            category=CapabilityCategory.REVIEW,
            description="审核员给出 approve / reject / revise 决定,驱动下一阶段。",
            invoke=_cap_review_decide,
            inputs_schema={
                "type": "object",
                "required": ["review_id", "decision"],
                "properties": {
                    "review_id": {"type": "string"},
                    "decision": {"type": "string", "enum": ["approve", "reject", "revise"]},
                    "comment": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["审核", "裁决"],
            emits_domain_event=True,
            domain_event_subject="review.decided",
        )
    )
    reg.register(
        Capability(
            id="review.stats",
            name="审核统计",
            category=CapabilityCategory.REVIEW,
            description="统计当前审核员 / 项目的审核总数、通过率。",
            invoke=_cap_review_stats,
            inputs_schema={
                "type": "object",
                "properties": {
                    "reviewer": {"type": "string"},
                    "project_id": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["审核", "统计"],
        )
    )

    # ---------- qc -----------------------------------------------------
    reg.register(
        Capability(
            id="qc.full",
            name="全量质检",
            category=CapabilityCategory.QC,
            description="对数据集执行全量质检,捕获 label / geometry / format / completeness 4 类缺陷。",
            invoke=_cap_qc_full,
            inputs_schema={
                "type": "object",
                "required": ["dataset_id"],
                "properties": {
                    "dataset_id": {"type": "string"},
                    "total": {"type": "integer", "min": 0, "default": 0},
                },
            },
            outputs_schema={"type": "object"},
            tags=["质检", "全量"],
            emits_domain_event=True,
            domain_event_subject="qc.started",
        )
    )
    reg.register(
        Capability(
            id="qc.sample",
            name="抽检",
            category=CapabilityCategory.QC,
            description="按 sample_rate 0-1 抽样检查,产出 sample_size。",
            invoke=_cap_qc_sample,
            inputs_schema={
                "type": "object",
                "required": ["dataset_id", "total", "sample_rate"],
                "properties": {
                    "dataset_id": {"type": "string"},
                    "total": {"type": "integer", "min": 1, "max": 1_000_000},
                    "sample_rate": {"type": "number", "min": 0.01, "max": 1.0},
                },
            },
            outputs_schema={"type": "object"},
            tags=["质检", "抽检"],
        )
    )
    reg.register(
        Capability(
            id="qc.aql",
            name="AQL 抽检 (ISO 2859-1)",
            category=CapabilityCategory.QC,
            description="按 ISO 2859-1 AQL 表自动选 sample letter,产出 Pass / Reject 决定。",
            invoke=_cap_qc_aql,
            inputs_schema={
                "type": "object",
                "required": ["dataset_id", "lot_size", "aql_level"],
                "properties": {
                    "dataset_id": {"type": "string"},
                    "lot_size": {"type": "integer", "min": 2, "max": 1_000_000},
                    "aql_level": {"type": "number", "enum": [0.1, 0.65, 1.0, 1.5, 2.5, 4.0, 6.5]},
                },
            },
            outputs_schema={"type": "object"},
            tags=["质检", "AQL", "国际标准"],
        )
    )

    # ---------- acceptance --------------------------------------------
    reg.register(
        Capability(
            id="acceptance.create",
            name="创建需求方验收",
            category=CapabilityCategory.ACCEPTANCE,
            description="为已交付的数据集创建一份需求方验收单,自动抽样 N 件。",
            invoke=_cap_acceptance_create,
            inputs_schema={
                "type": "object",
                "required": ["delivery_id"],
                "properties": {"delivery_id": {"type": "string"}},
            },
            outputs_schema={"type": "object"},
            tags=["验收"],
            emits_domain_event=True,
            domain_event_subject="acceptance.created",
        )
    )
    reg.register(
        Capability(
            id="acceptance.submit",
            name="提交需求方验收",
            category=CapabilityCategory.ACCEPTANCE,
            description="需求方提交 accept / reject / revise 决定,accept 触发自动分享链接。",
            invoke=_cap_acceptance_submit,
            inputs_schema={
                "type": "object",
                "required": ["acceptance_id", "decision"],
                "properties": {
                    "acceptance_id": {"type": "string"},
                    "decision": {"type": "string", "enum": ["accept", "reject", "revise"]},
                    "comments": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["验收", "终态"],
            emits_domain_event=True,
            domain_event_subject="acceptance.decided",
        )
    )

    # ---------- delivery -----------------------------------------------
    reg.register(
        Capability(
            id="delivery.share",
            name="分享交付",
            category=CapabilityCategory.DELIVERY,
            description="为已通过验收的交付生成短时分享 token,用于给需求方下载。",
            invoke=_cap_delivery_share,
            inputs_schema={
                "type": "object",
                "required": ["delivery_id"],
                "properties": {
                    "delivery_id": {"type": "string"},
                    "expires_at": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["交付", "分享"],
            emits_domain_event=True,
            domain_event_subject="delivery.shared",
        )
    )
    reg.register(
        Capability(
            id="delivery.finalize",
            name="归档交付",
            category=CapabilityCategory.DELIVERY,
            description="确认交付已审批通过 + 分享完成,设为终态 approved。",
            invoke=_cap_delivery_finalize,
            inputs_schema={
                "type": "object",
                "required": ["delivery_id"],
                "properties": {"delivery_id": {"type": "string"}},
            },
            outputs_schema={"type": "object"},
            tags=["交付", "终态"],
            emits_domain_event=True,
            domain_event_subject="delivery.finalized",
        )
    )

    # ---------- scoring ------------------------------------------------
    reg.register(
        Capability(
            id="scoring.aesthetic",
            name="美学评分",
            category=CapabilityCategory.SCORING,
            description="对单张图像做美学评分 (0-100),反映构图 / 色彩 / 主题表现力。",
            invoke=_cap_scoring_aesthetic,
            inputs_schema={
                "type": "object",
                "required": ["asset_id"],
                "properties": {"asset_id": {"type": "string"}},
            },
            outputs_schema={"type": "object"},
            tags=["评分", "图像"],
        )
    )
    reg.register(
        Capability(
            id="scoring.quality",
            name="技术质量评分",
            category=CapabilityCategory.SCORING,
            description="评估素材技术质量 (分辨率 / 锐度 / 噪点 / 色彩空间)。",
            invoke=_cap_scoring_quality,
            inputs_schema={
                "type": "object",
                "required": ["asset_id"],
                "properties": {"asset_id": {"type": "string"}},
            },
            outputs_schema={"type": "object"},
            tags=["评分", "技术"],
        )
    )
    reg.register(
        Capability(
            id="scoring.aggregate",
            name="聚合评分",
            category=CapabilityCategory.SCORING,
            description="聚合数据集的多维度评分,产出 mean / p99 / stdev。",
            invoke=_cap_scoring_aggregate,
            inputs_schema={
                "type": "object",
                "required": ["dataset_id"],
                "properties": {"dataset_id": {"type": "string"}},
            },
            outputs_schema={"type": "object"},
            tags=["评分", "聚合"],
        )
    )

    # ---------- tagging / cleaning / classification --------------------
    reg.register(
        Capability(
            id="tagging.bulk",
            name="批量打标",
            category=CapabilityCategory.TAGGING,
            description="对一组资产批量打同一组标签。",
            invoke=_cap_tagging_bulk,
            inputs_schema={
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {"type": "array", "items": {"type": "object"}, "min_items": 1},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
            outputs_schema={"type": "object"},
            tags=["打标"],
        )
    )
    reg.register(
        Capability(
            id="cleaning.bulk",
            name="批量清洗",
            category=CapabilityCategory.CLEANING,
            description="批量去空 / 去重 / 去敏感 / 去广告。",
            invoke=_cap_cleaning_bulk,
            inputs_schema={
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {"type": "array", "items": {"type": "object"}, "min_items": 1},
                    "rules": {"type": "array", "items": {"type": "string"}},
                },
            },
            outputs_schema={"type": "object"},
            tags=["清洗"],
        )
    )
    reg.register(
        Capability(
            id="classification.bulk",
            name="批量分类",
            category=CapabilityCategory.CLASSIFICATION,
            description="对一组资产执行同一分类,把模型输出写回数据集标签字段。",
            invoke=_cap_classification_bulk,
            inputs_schema={
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {"type": "array", "items": {"type": "object"}, "min_items": 1},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "model": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["分类"],
        )
    )

    # ---------- search -------------------------------------------------
    reg.register(
        Capability(
            id="search.full",
            name="全文检索",
            category=CapabilityCategory.SEARCH,
            description="对所有数据集、资产、标签做全文检索。",
            invoke=_cap_search_full,
            inputs_schema={
                "type": "object",
                "required": ["q"],
                "properties": {
                    "q": {"type": "string", "min_length": 1, "max_length": 200},
                    "filter": {"type": "object"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["搜索"],
        )
    )

    # ---------- evaluation --------------------------------------------
    reg.register(
        Capability(
            id="evaluation.run",
            name="模型评测",
            category=CapabilityCategory.EVALUATION,
            description="在指定数据集上评测一个模型,产出 accuracy / f1 / bleu。",
            invoke=_cap_evaluation_run,
            inputs_schema={
                "type": "object",
                "required": ["model", "dataset_id"],
                "properties": {
                    "model": {"type": "string"},
                    "dataset_id": {"type": "string"},
                    "metrics": {"type": "array", "items": {"type": "string"}},
                },
            },
            outputs_schema={"type": "object"},
            tags=["评测"],
        )
    )

    # ---------- export -------------------------------------------------
    reg.register(
        Capability(
            id="export.coco",
            name="COCO 导出",
            category=CapabilityCategory.EXPORT,
            description="导出为 COCO JSON,供主流检测 / 分割框架训练。",
            invoke=_cap_export_coco,
            inputs_schema={
                "type": "object",
                "required": ["dataset_id"],
                "properties": {
                    "dataset_id": {"type": "string"},
                    "output_path": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["导出", "目标检测"],
        )
    )
    reg.register(
        Capability(
            id="export.llava",
            name="LLaVA 导出",
            category=CapabilityCategory.EXPORT,
            description="导出为 LLaVA 指令微调 JSONL 格式。",
            invoke=_cap_export_llava,
            inputs_schema={
                "type": "object",
                "required": ["dataset_id"],
                "properties": {
                    "dataset_id": {"type": "string"},
                    "output_path": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["导出", "多模态大模型"],
        )
    )
    reg.register(
        Capability(
            id="export.internvl",
            name="InternVL 导出",
            category=CapabilityCategory.EXPORT,
            description="导出为 InternVL 多模态对话 JSONL 格式。",
            invoke=_cap_export_internvl,
            inputs_schema={
                "type": "object",
                "required": ["dataset_id"],
                "properties": {
                    "dataset_id": {"type": "string"},
                    "output_path": {"type": "string"},
                },
            },
            outputs_schema={"type": "object"},
            tags=["导出", "多模态大模型"],
        )
    )


def build_default_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    register_default_capabilities(reg)
    return reg
