"""VDP-2026 R3-R10 — Orchestration bus tests.

Covers:

  - direct bus.record + read round-trip
  - lifecycle summary bucketing by topic root
  - lineage chain (parent → child) and reverse lookup
  - cross-module wiring: invoking a capability emits a bus event
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from capabilities_v2.engine import (  # noqa: E402
    configure_db as configure_cap_db,
    reset_registry_for_test,
)
from capabilities_v2.dataflow import (  # noqa: E402
    configure_db as configure_dataflow_db,
    reset_tracker_for_test,
)
from workflow_builder.engine import (  # noqa: E402
    configure_db as configure_wb_db,
    reset_engine_for_test,
)
from orchestration.bus import (  # noqa: E402
    EventBus,
    LineageLink,
    RELATION_GRAPH,
    ENTITY_GROUPS,
    configure_db as configure_bus_db,
    get_bus,
    reset_bus_for_test,
    wire_capability_bus,
    wire_workflow_builder_bus,
)
from orchestration import bootstrap as _bootstrap  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    configure_cap_db(tmp_path / "cap.db")
    configure_dataflow_db(tmp_path / "flow.db")
    configure_wb_db(tmp_path / "wb.db")
    configure_bus_db(tmp_path / "bus.db")
    reset_registry_for_test()
    reset_tracker_for_test()
    reset_engine_for_test()
    reset_bus_for_test()
    yield


# ===========================================================================
# Direct bus usage
# ===========================================================================


class TestDirectBus:
    def test_record_then_query(self):
        bus = get_bus()
        bus.record(topic="project.created", entity_type="project",
                   entity_id="p_1", payload={"name": "demo"}, refs={"project_id": "p_1"})
        rows = bus.query(topic="project.created", project_id="p_1")
        assert len(rows) == 1
        assert rows[0]["entity_id"] == "p_1"
        assert rows[0]["payload"]["name"] == "demo"

    def test_stats_aggregates(self):
        bus = get_bus()
        for i in range(5):
            bus.record(topic="project.created", entity_type="project",
                       entity_id=f"p_{i}", refs={"project_id": f"p_{i}"})
        bus.record(topic="dataset.created", entity_type="dataset",
                   entity_id="d_1", refs={"dataset_id": "d_1"})
        s = bus.stats()
        assert s["topics"]["project.created"] == 5
        assert s["topics"]["dataset.created"] == 1
        assert s["projects"] == 5
        assert s["datasets"] == 1

    def test_lifecycle_summary_buckets(self):
        bus = get_bus()
        for topic in ("project.created", "project.updated",
                      "dataset.created", "pack.created",
                      "annotation.submitted"):
            bus.record(topic=topic)
        s = bus.lifecycle_summary()
        # project → 2, dataset → 1, pack → 1, annotation → 1
        assert s["stages"]["project"] == 2
        assert s["stages"]["dataset"] == 1
        assert s["stages"]["pack"] == 1
        assert s["stages"]["annotation"] == 1
        assert s["total"] == 5

    def test_lineage_chain(self):
        bus = get_bus()
        bus.record_lineage("project", "p_1", "requirement", "r_1", "fulfills")
        bus.record_lineage("requirement", "r_1", "dataset", "d_1", "specifies")
        bus.record_lineage("dataset", "d_1", "pack", "pk_1", "packed_into")
        # query a node mid-chain
        out = bus.lineage_for("dataset", "d_1")
        assert len(out["parents"]) == 1
        assert out["parents"][0]["parent_id"] == "r_1"
        assert len(out["children"]) == 1
        assert out["children"][0]["child_id"] == "pk_1"

    def test_relation_graph_shape(self):
        # 9-step linear dataset lifecycle + 5 side-quality branches
        from_pairs = {p for p, _, _ in RELATION_GRAPH}
        to_pairs = {c for _, c, _ in RELATION_GRAPH}
        assert "project" in from_pairs
        assert "share" in to_pairs


# ===========================================================================
# Cross-module wiring
# ===========================================================================


class TestWiring:
    def test_capability_invoke_emits_bus_event(self):
        from capabilities_v2.engine import get_registry as get_cap_reg
        wire_capability_bus()
        reg = get_cap_reg()
        # sanity: confirm hook is installed
        assert getattr(reg, "_bus_hooked", False) is True
        res = reg.invoke("project.create", inputs={"name": "bus-demo"}, refs={"project_id": "p-bus"})
        assert res.status == "success"
        bus = get_bus()
        # any event for this project — independent of topic naming quirks
        rows = bus.query(project_id="p-bus")
        assert len(rows) >= 1, f"no events for p-bus: {bus.query()}"
        assert rows[0]["source_module"] == "capabilities_v2"

    def test_workflow_run_emits_bus_event(self):
        from workflow_builder.engine import build_starter_templates, get_engine as get_wb
        wire_capability_bus()
        wire_workflow_builder_bus()
        eng = get_wb()
        tpl = next(t for t in build_starter_templates() if t.id == "wf_tpl_model_evaluation")
        eng.save_workflow(tpl)
        run = eng.run_workflow(tpl, actor="pytest")
        bus = get_bus()
        all_rows = bus.query()
        matched = [r for r in all_rows if r.get("topic", "").startswith("workflow.run.")]
        assert len(matched) >= 1

    def test_full_platform_wiring_endtoend(self):
        """Simulate the canonical 9-stage flow (incl. delivery.finalize) and
        assert the bus captures every transition emitted by capabilities_v2.
        """
        _bootstrap()
        from capabilities_v2.engine import get_registry as get_cap_reg
        reg = get_cap_reg()
        refs = {"project_id": "p-full"}
        stages = [
            ("project.create", {"name": "demo"}),
            ("requirement.create", {"name": "req"}),
            ("dataset.create", {"name": "ds"}),
            ("pack.create_data", {"name": "pk"}),
            ("annotation.submit", {"task_id": "t1"}),
            ("review.decide", {"review_id": "rev1", "decision": "approve"}),
            ("qc.full", {"dataset_id": "ds1", "total": 100}),
            ("acceptance.submit", {"acceptance_id": "acc1", "decision": "accept"}),
            ("delivery.finalize", {"delivery_id": "dlv1"}),
        ]
        for cid, inputs in stages:
            res = reg.invoke(cid, inputs, refs=refs)
            assert res.status == "success", f"{cid} failed: {res.error}"
        bus = get_bus()
        rows = bus.query(project_id="p-full")
        topics = {r["topic"] for r in rows}
        # bus should have at least the lifecycle topics from each call
        for cid, _ in stages:
            root, _, verb = cid.partition(".")
            expected_topic = f"{root}.{verb}ed" if not verb.endswith("ed") else f"{root}.{verb}"
            assert expected_topic in topics, f"missing topic for {cid}: {expected_topic}"
        capability_rows = [r for r in rows if r["source_module"] == "capabilities_v2"]
        assert len(capability_rows) == 9


# ===========================================================================
# HTTP routes
# ===========================================================================


class TestHTTPRoutes:
    def _client(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            return None
        from orchestration.routes import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_routes_round_trip(self):
        client = self._client()
        if client is None:
            pytest.skip("fastapi not installed")
        r = client.get("/api/v1/orchestration/health")
        assert r.status_code == 200
        r = client.get("/api/v1/orchestration/graph")
        assert r.status_code == 200
        body = r.json()
        assert "data_production_lifecycle" in body["entity_groups"]

        r = client.post(
            "/api/v1/orchestration/lineage",
            json={"parent_type": "project", "parent_id": "p", "child_type": "requirement",
                  "child_id": "r", "relation": "fulfills"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

        r = client.get("/api/v1/orchestration/lineage", params={"entity_type": "requirement", "entity_id": "r"})
        assert r.status_code == 200
        body = r.json()
        assert any(p["parent_id"] == "p" for p in body["parents"])

        r = client.post(
            "/api/v1/orchestration/events",
            json={"topic": "manual.test", "entity_type": "x", "entity_id": "y"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

        r = client.get("/api/v1/orchestration/events", params={"topic": "manual.test"})
        assert r.status_code == 200
        assert r.json()["total"] >= 1
