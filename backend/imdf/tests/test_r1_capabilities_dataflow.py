"""VDP-2026 R1 — Capabilities & DataFlow tests.

Covers:

  * registry bootstrap (47 capabilities across 17 categories)
  * input validation against the declared JSON Schema
  * invocation + audit persistence
  * domain-event emission into DataFlowTracker
  * dataflow snapshot reconstruction across the 8-stage lifecycle
  * HTTP routes (using FastAPI TestClient)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# -- bootstrap: make `imdf` importable when pytest runs from any cwd ---
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from capabilities_v2.engine import (  # noqa: E402  (after sys.path tweak)
    CapabilityRegistry,
    build_default_registry,
    Capability,
    CapabilityCategory,
    CapabilityResult,
    configure_db,
    _validate_inputs,
    reset_registry_for_test,
)
from capabilities_v2.dataflow import (  # noqa: E402
    DataFlowTracker,
    STAGES,
    SUBJECT_TO_STAGE,
    configure_db as configure_dataflow_db,
    reset_tracker_for_test,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    db_cap = tmp_path / "capabilities_v2.db"
    db_flow = tmp_path / "dataflow.db"
    configure_db(db_cap)
    configure_dataflow_db(db_flow)
    reset_registry_for_test()
    reset_tracker_for_test()
    yield
    # teardown — nothing to do, tmp_path is wiped


@pytest.fixture
def reg() -> CapabilityRegistry:
    return build_default_registry()


@pytest.fixture
def tracker() -> DataFlowTracker:
    return DataFlowTracker()


# ===========================================================================
# Registry & catalogue
# ===========================================================================


class TestRegistryBootstrap:
    def test_default_registry_has_at_least_36_capabilities(self, reg):
        assert reg.count() >= 36, f"only {reg.count()} caps registered"

    def test_all_categories_present(self, reg):
        cats = set(reg.list_categories())
        # 17 categories defined
        for cat in (
            "project",
            "requirement",
            "dataset",
            "pack",
            "collection",
            "annotation",
            "review",
            "qc",
            "acceptance",
            "delivery",
            "scoring",
            "tagging",
            "cleaning",
            "classification",
            "search",
            "evaluation",
            "export",
        ):
            assert cat in cats, f"missing category '{cat}'"

    def test_required_invokes_present(self, reg):
        # spot-check the eight canonical flow anchors
        for cid in (
            "project.create",
            "requirement.create",
            "dataset.create",
            "pack.create_data",
            "annotation.submit",
            "review.decide",
            "qc.full",
            "acceptance.submit",
            "delivery.finalize",
        ):
            cap = reg.get(cid)
            assert cap is not None, f"missing capability {cid}"
            assert callable(cap.invoke)

    def test_describe_round_trip(self, reg):
        cap = reg.get("project.create")
        d = cap.describe()
        assert d["id"] == "project.create"
        assert "inputs_schema" in d
        assert "name" in d["inputs_schema"]["properties"]

    def test_catalogue_shape(self, reg):
        c = reg.catalogue()
        assert "items" in c
        assert "categories" in c
        assert c["total"] >= 36
        assert all("id" in i for i in c["items"])

    def test_search_by_query(self, reg):
        out = reg.search("annotation")
        ids = {c.id for c in out}
        assert "annotation.pull" in ids
        assert "annotation.submit" in ids


class TestInputValidation:
    def test_required_field_missing_returns_error_message(self, reg):
        res = reg.invoke("project.create", inputs={})
        assert res.status == "error"
        assert "missing required input 'name'" in res.error

    def test_wrong_type_returns_error_message(self, reg):
        res = reg.invoke(
            "project.create",
            inputs={"name": "demo", "owner": 123},  # owner must be string
        )
        assert res.status == "error"
        assert "expected string" in res.error

    def test_min_length_enforced(self, reg):
        res = reg.invoke("project.create", inputs={"name": ""})
        assert res.status == "error"
        assert "shorter than min_length" in res.error

    def test_enum_enforced(self, reg):
        res = reg.invoke(
            "requirement.create",
            inputs={"name": "demo", "type": "invalid_type"},
        )
        assert res.status == "error"
        assert "must be one of" in res.error

    def test_min_max_for_numbers(self, reg):
        res = reg.invoke(
            "qc.sample",
            inputs={"dataset_id": "ds1", "total": 100, "sample_rate": 2.0},
        )
        assert res.status == "error"
        assert "above max" in res.error

    def test_min_items_for_arrays(self, reg):
        res = reg.invoke("annotation.bulk", inputs={"items": []})
        assert res.status == "error"
        assert "min_items" in res.error

    def test_unknown_capability_returns_error(self, reg):
        res = reg.invoke("totally.fake", inputs={})
        assert res.status == "error"
        assert "unknown capability" in res.error


# ===========================================================================
# Invocation & domain-event fan-out
# ===========================================================================


class TestInvocation:
    def test_success_returns_outputs(self, reg):
        res = reg.invoke("project.create", inputs={"name": "demo"})
        assert res.status == "success"
        assert "project_id" in res.outputs
        # domain event emitted
        assert res.emitted_event == "project.created"

    def test_audit_row_persisted(self, reg):
        res = reg.invoke(
            "dataset.create",
            inputs={"name": "ds1", "modality": "image"},
            actor="alice",
            refs={"project_id": "proj_1"},
        )
        assert res.status == "success"
        rows = reg.list_invocations(ref_project_id="proj_1")
        assert len(rows) == 1
        assert rows[0]["actor"] == "alice"
        assert rows[0]["capability_id"] == "dataset.create"

    def test_failed_invocation_also_persisted(self, reg):
        res = reg.invoke("project.create", inputs={})
        assert res.status == "error"
        rows = reg.list_invocations(cap_id="project.create")
        assert any(r["status"] == "error" for r in rows)


# ===========================================================================
# DataFlowTracker
# ===========================================================================


class TestDataFlowTracker:
    def test_record_and_list_events(self, tracker):
        tracker.record_event(
            "project.created",
            {"project_id": "p1"},
            refs={"project_id": "p1"},
        )
        rows = tracker.list_events(project_id="p1")
        assert len(rows) == 1
        assert rows[0]["subject"] == "project.created"

    def test_snapshot_reconstructs_8_stages(self, tracker):
        # simulate the canonical 8-stage flow for project=p-demo
        seq = [
            ("project.created", "project", {"project_id": "p-demo"}),
            ("requirement.created", "requirement", {"project_id": "p-demo"}),
            ("dataset.created", "dataset", {"project_id": "p-demo"}),
            ("pack.created", "pack", {"project_id": "p-demo"}),
            ("annotation.submitted", "annotation", {"project_id": "p-demo"}),
            ("review.decided", "review", {"project_id": "p-demo"}),
            ("qc.started", "qc", {"project_id": "p-demo"}),
            ("acceptance.decided", "acceptance", {"project_id": "p-demo"}),
            ("delivery.finalized", "delivery", {"project_id": "p-demo"}),
        ]
        for subj, _stage, payload in seq:
            tracker.record_event(subj, payload, refs={"project_id": "p-demo"})

        snap = tracker.snapshot(project_id="p-demo")
        assert snap.total_events == 9

        # stage buckets — every canonical stage should have ≥ 1 event
        for stage in STAGES:
            node = next(s for s in snap.stages if s.stage == stage["key"])
            assert node.event_count >= 1, f"stage {stage['key']} has no events"

        # timeline ordering: oldest first
        for i in range(1, len(snap.timeline)):
            assert (
                snap.timeline[i - 1]["created_at"]
                <= snap.timeline[i]["created_at"]
            )

    def test_subject_to_stage_map_complete(self):
        # Every key in our emitter set must map to a known stage
        for subj, stage in SUBJECT_TO_STAGE.items():
            assert stage in {s["key"] for s in STAGES}, f"{subj} → {stage}"


# ===========================================================================
# End-to-end: capability invoke → tracker snapshot
# ===========================================================================


class TestIntegrationFlow:
    def test_full_flow_through_registry(self, reg, tracker):
        refs = {"project_id": "p-flow"}

        r1 = reg.invoke("project.create", inputs={"name": "flow-test"}, refs=refs)
        assert r1.status == "success" and r1.outputs["status"] == "draft"

        r2 = reg.invoke(
            "requirement.create", inputs={"name": "req-1"}, refs=refs
        )
        assert r2.status == "success"

        r3 = reg.invoke(
            "dataset.create",
            inputs={"name": "ds-1", "modality": "image"},
            refs=refs,
        )
        assert r3.status == "success"

        r4 = reg.invoke(
            "pack.create_data",
            inputs={"name": "pack-1", "asset_ids": ["a1", "a2"]},
            refs=refs,
        )
        assert r4.status == "success"

        r5 = reg.invoke(
            "pack.route",
            inputs={"pack_id": r4.outputs["pack_id"], "asset_ids": ["a1", "a2"]},
            refs=refs,
        )
        assert r5.status == "success"
        assert r5.outputs["target_module"] == "annotation"

        r6 = reg.invoke(
            "annotation.submit",
            inputs={"task_id": "task_x"},
            refs=refs,
        )
        assert r6.status == "success"

        r7 = reg.invoke(
            "review.decide",
            inputs={"review_id": "rev_x", "decision": "approve"},
            refs=refs,
        )
        assert r7.status == "success"

        r8 = reg.invoke(
            "qc.full",
            inputs={"dataset_id": "ds-1", "total": 50},
            refs=refs,
        )
        assert r8.status == "success"

        r9 = reg.invoke(
            "acceptance.submit",
            inputs={"acceptance_id": "acc_x", "decision": "accept"},
            refs=refs,
        )
        assert r9.status == "success"

        r10 = reg.invoke(
            "delivery.finalize",
            inputs={"delivery_id": "dlv_x"},
            refs=refs,
        )
        assert r10.status == "success"

        snap = tracker.snapshot(project_id="p-flow")
        assert snap.total_events == 10
        assert any(s.stage == "annotation" and s.event_count > 0 for s in snap.stages)
        assert any(s.stage == "acceptance" and s.event_count > 0 for s in snap.stages)
        assert any(s.stage == "delivery" and s.event_count > 0 for s in snap.stages)


# ===========================================================================
# HTTP surface — skip if fastapi is not available
# ===========================================================================


class TestHTTPRoutes:
    @pytest.fixture(autouse=True)
    def _setup(self, isolated_storage):
        pass

    def test_catalogue_endpoint(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not installed")
        from capabilities_v2.routes import router, flow_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        app.include_router(flow_router)

        client = TestClient(app)
        # /api/v1/capabilities_v2/catalogue
        r = client.get("/api/v1/capabilities_v2/catalogue")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 36
        # /api/v1/capabilities_v2/capabilities/project.create
        r = client.get("/api/v1/capabilities_v2/capabilities/project.create")
        assert r.status_code == 200
        assert r.json()["id"] == "project.create"

        # POST /api/v1/capabilities_v2/invoke
        r = client.post(
            "/api/v1/capabilities_v2/invoke",
            json={
                "capability_id": "project.create",
                "inputs": {"name": "http-test"},
                "actor": "pytest",
                "refs": {"project_id": "p-http"},
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["capability_id"] == "project.create"

        # /api/v1/dataflow/snapshot
        r = client.get(
            "/api/v1/dataflow/snapshot", params={"project_id": "p-http"}
        )
        assert r.status_code == 200
        snap = r.json()
        assert snap["total_events"] >= 1
        # the project stage should be active
        proj_node = next(s for s in snap["stages"] if s["stage"] == "project")
        assert proj_node["event_count"] >= 1

        # /api/v1/dataflow/stages
        r = client.get("/api/v1/dataflow/stages")
        assert r.status_code == 200
        body = r.json()
        assert body["total_events"] >= 1

        # invalid invoke
        r = client.post(
            "/api/v1/capabilities_v2/invoke",
            json={"capability_id": "project.create", "inputs": {}},
        )
        assert r.status_code == 200  # we surface errors in body, not 4xx
        assert r.json()["status"] == "error"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "--tb=short"]))
