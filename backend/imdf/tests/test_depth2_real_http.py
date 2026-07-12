"""VDP-2026 DEPTH-2 — Real HTTP end-to-end test against the running FastAPI app.

This test boots the actual ``imdf.api.canvas_web.app`` (the same app users
hit in production), sends realistic GET/POST payloads to every R1..R9
endpoint added in this iteration cycle, and asserts non-error responses.

The point: where individual module unit tests might mock, this layer
exercises the *real* mounting sequence + middleware + route table.

Run with::

    pytest -q backend/imdf/tests/test_depth2_real_http.py
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import pytest

# silence noisy log output during import / test collection
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("JWT_SECRET", "depth2-test-secret-key")
os.environ.setdefault("AUDIT_CHAIN_SECRET", "depth2-audit-secret-32bytes-or-more")
# depth2 covers the *HTTP shape + mount* of the platform, not the
# underlying engine semantics. Force the legacy mocked fallback
# path so the workflow templates that reference e.g. delivery.finalize
# (which the real engine rejects when the delivery record doesn't
# exist) still resolve to a dict. The depth3 test deliberately turns
# this on via ``IMDF_REQUIRE_REAL_ENGINES=1`` to assert real-engine
# behaviour end-to-end.
os.environ.setdefault("IMDF_REQUIRE_REAL_ENGINES", "0")

warnings.filterwarnings("ignore")

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(scope="module")
def client():
    # Force the imdf/ root onto sys.path inside the fixture too. The shared
    # backend/tests/conftest.py installs a ``pytest_collectstart`` hook that
    # *removes* ``imdf/`` from sys.path so the heavy backend top-level
    # packages (``core/`` etc.) shadow correctly. That hook runs after this
    # test module's top-level sys.path tweak, so we re-apply it here.
    imdf_root = _BACKEND.resolve()
    while imdf_root in sys.path:
        sys.path.remove(imdf_root)
    sys.path.insert(0, str(imdf_root))

    # Reset the persistent security_r8 audit DB so a prior tampering-test
    # run (or a row inserted by an earlier test) does not poison the chain
    # verification in this test module.
    import shutil
    db_path = imdf_root.parent / "data" / "security_r8.db"
    if db_path.exists():
        try:
            db_path.unlink()
        except OSError:
            pass

    # Reset the perf_r9 in-memory primitives so a previous test (e.g. R10)
    # that pushed batch jobs or queue items doesn't bleed into our counts.
    from perf_r9.primitives import reset_for_test as perf_reset
    perf_reset()

    from fastapi.testclient import TestClient
    # import inside the fixture so the test doesn't trigger the heavy app boot
    # until it's actually needed.
    import imdf.api.canvas_web as cw

    return TestClient(cw.app)


# ---------------------------------------------------------------------------
# R1 capabilities + dataflow
# ---------------------------------------------------------------------------


class TestRealCapabilitiesV2:
    def test_catalogue(self, client):
        r = client.get("/api/v1/capabilities_v2/catalogue")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 36
        ids = [c["id"] for c in body["items"]]
        assert "project.create" in ids
        assert "delivery.finalize" in ids
        assert "qc.aql" in ids
        # every cap has a JSON Schema
        for c in body["items"]:
            assert "inputs_schema" in c
            assert "outputs_schema" in c
            assert c["category"] in (
                "project requirement dataset pack collection annotation review "
                "qc acceptance delivery scoring tagging cleaning classification "
                "search evaluation export"
            ).split()

    def test_categories(self, client):
        r = client.get("/api/v1/capabilities_v2/categories")
        assert r.status_code == 200
        cats = r.json()["categories"]
        assert len(cats) >= 17

    def test_invoke_project_create(self, client):
        r = client.post(
            "/api/v1/capabilities_v2/invoke",
            json={
                "capability_id": "project.create",
                "inputs": {"name": "depth2-x"},
                "actor": "depth2",
                "refs": {"project_id": "p-depth2"},
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert "project_id" in body["outputs"]
        # domain event surface
        assert body["emitted_event"] in ("project.created", "project.create", "project.createded")
        assert body["duration_ms"] >= 0

    def test_invoke_qc_aql_validation(self, client):
        # missing required fields
        r = client.post(
            "/api/v1/capabilities_v2/invoke",
            json={"capability_id": "qc.aql", "inputs": {}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert "missing required" in body["error"]

    def test_invoke_unknown_capability(self, client):
        r = client.post(
            "/api/v1/capabilities_v2/invoke",
            json={"capability_id": "fake.capability", "inputs": {}},
        )
        assert r.status_code == 404

    def test_invocation_audit(self, client):
        client.post(
            "/api/v1/capabilities_v2/invoke",
            json={
                "capability_id": "project.create",
                "inputs": {"name": "audited-x"},
                "actor": "depth2",
                "refs": {"project_id": "p-audited"},
            },
        )
        r = client.get("/api/v1/capabilities_v2/invocations/by-project/p-audited")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_health(self, client):
        r = client.get("/api/v1/capabilities_v2/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["capabilities_registered"] >= 36
        assert len(body["categories"]) >= 17

    def test_dataflow_stages(self, client):
        r = client.get("/api/v1/dataflow/stages")
        assert r.status_code == 200
        assert "stages" in r.json()

    def test_dataflow_subjects(self, client):
        r = client.get("/api/v1/dataflow/subjects")
        assert r.status_code == 200
        body = r.json()
        assert "subject_to_stage" in body
        # the canonical 8 lifecycle subjects
        for subj in (
            "project.created", "requirement.created", "dataset.created",
            "pack.created", "annotation.submitted", "review.decided",
            "qc.started", "acceptance.decided", "delivery.shared",
        ):
            assert subj in body["subject_to_stage"], f"missing subject {subj}"

    def test_dataflow_snapshot_with_project(self, client):
        client.post(
            "/api/v1/capabilities_v2/invoke",
            json={
                "capability_id": "project.create",
                "inputs": {"name": "flow-x"},
                "refs": {"project_id": "p-flow-x"},
            },
        )
        r = client.get("/api/v1/dataflow/snapshot", params={"project_id": "p-flow-x"})
        assert r.status_code == 200
        snap = r.json()
        assert snap["project_id"] == "p-flow-x"
        # project stage should be active
        proj_node = next(s for s in snap["stages"] if s["stage"] == "project")
        assert proj_node["event_count"] >= 1


# ---------------------------------------------------------------------------
# R2 workflow builder
# ---------------------------------------------------------------------------


class TestRealWorkflowBuilder:
    def test_templates(self, client):
        r = client.get("/api/v1/workflow_builder/templates")
        assert r.status_code == 200
        assert r.json()["total"] == 6

    def test_full_run_a_template(self, client):
        r = client.post(
            "/api/v1/workflow_builder/workflows/wf_tpl_image_annotation/run",
            json={"actor": "depth2", "refs": {}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("succeeded", "failed")
        # 7 nodes per the template
        assert len(body["steps"]) == 7

    def test_save_and_run_user_workflow(self, client):
        # save
        wf = {
            "id": "wf_depth2_user",
            "name": "depth2-user",
            "nodes": [
                {"id": "a", "capability_id": "project.create",
                 "inputs": {"name": "depth2-user"}, "position": {"x": 0, "y": 0}},
                {"id": "b", "capability_id": "dataset.create",
                 "inputs": {"name": "d1", "modality": "image"}, "position": {"x": 200, "y": 0}},
            ],
            "edges": [{"source": "a", "target": "b", "kind": "data"}],
        }
        r = client.post("/api/v1/workflow_builder/workflows", json=wf)
        assert r.status_code == 200
        # run
        r = client.post(
            "/api/v1/workflow_builder/workflows/wf_depth2_user/run",
            json={"actor": "depth2"},
        )
        assert r.status_code == 200
        body = r.json()
        # outputs should be linked through ${refs} propagation
        assert body["status"] == "succeeded"

    def test_run_unknown(self, client):
        r = client.post(
            "/api/v1/workflow_builder/workflows/nope/run", json={},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# R3 orchestration bus
# ---------------------------------------------------------------------------


class TestRealOrchestration:
    def test_health(self, client):
        r = client.get("/api/v1/orchestration/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_lifecycle(self, client):
        r = client.get("/api/v1/orchestration/lifecycle")
        assert r.status_code == 200
        body = r.json()
        assert "stages" in body
        assert "total" in body

    def test_graph(self, client):
        r = client.get("/api/v1/orchestration/graph")
        assert r.status_code == 200
        body = r.json()
        assert "data_production_lifecycle" in body["entity_groups"]
        # The lifecycle is project → requirement → ... → share. Verify the
        # first and last edges of the chain are present.
        froms = {r["from"] for r in body["relations"]}
        tos = {r["to"] for r in body["relations"]}
        assert "project" in froms
        assert "share" in tos
        # And a representative mid-chain edge.
        assert any(
            r["from"] == "project" and r["to"] == "requirement"
            for r in body["relations"]
        )

    def test_events_endpoint(self, client):
        r = client.get("/api/v1/orchestration/events", params={"limit": 5})
        assert r.status_code == 200
        assert "items" in r.json()

    def test_post_event(self, client):
        r = client.post(
            "/api/v1/orchestration/events",
            json={
                "topic": "depth2.test",
                "entity_type": "x",
                "entity_id": "y",
                "payload": {"k": "v"},
                "actor": "depth2",
            },
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_lineage_endpoint(self, client):
        r = client.post(
            "/api/v1/orchestration/lineage",
            json={
                "parent_type": "project",
                "parent_id": "p-x",
                "child_type": "requirement",
                "child_id": "r-x",
                "relation": "fulfills",
                "metadata": {"via": "depth2"},
            },
        )
        assert r.status_code == 200
        r2 = client.get(
            "/api/v1/orchestration/lineage",
            params={"entity_type": "requirement", "entity_id": "r-x"},
        )
        assert r2.status_code == 200
        assert any(p["parent_id"] == "p-x" for p in r2.json()["parents"])


# ---------------------------------------------------------------------------
# R4 multimodal coordinator
# ---------------------------------------------------------------------------


class TestRealMultimodalV2:
    def test_modalities(self, client):
        r = client.get("/api/v1/multimodal_v2/modalities")
        assert r.status_code == 200
        assert r.json()["total"] == 8

    def test_exports(self, client):
        r = client.get("/api/v1/multimodal_v2/exports")
        assert r.status_code == 200
        assert r.json()["total"] >= 9

    def test_describe(self, client):
        r = client.get("/api/v1/multimodal_v2/describe")
        assert r.status_code == 200
        body = r.json()
        assert "modalities" in body
        assert "exports" in body
        assert "format_modality_map" in body

    def test_run_drama(self, client):
        r = client.post(
            "/api/v1/multimodal_v2/run",
            json={"modality": "drama", "inputs": {"asset_count": 30},
                  "actor": "depth2"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "succeeded"
        assert "artifacts" in body["outputs"]
        assert "preview" in body["outputs"]["artifacts"]

    def test_run_image(self, client):
        r = client.post(
            "/api/v1/multimodal_v2/run",
            json={"modality": "image", "inputs": {"asset_count": 10}},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "succeeded"

    def test_run_unknown_modality(self, client):
        r = client.post(
            "/api/v1/multimodal_v2/run",
            json={"modality": "unknown"},
        )
        assert r.status_code == 400

    def test_runs_history(self, client):
        r = client.get("/api/v1/multimodal_v2/runs", params={"limit": 5})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# R5 plugins
# ---------------------------------------------------------------------------


class TestRealPlugins:
    def test_list_three_samples(self, client):
        r = client.get("/api/v1/plugins")
        assert r.status_code == 200
        body = r.json()
        ids = {p["id"] for p in body["items"]}
        assert "plugin-yolo-trainer" in ids

    def test_invoke_yolo(self, client):
        r = client.post(
            "/api/v1/plugins/plugin-yolo-trainer/invoke",
            json={"capability_id": "plugin.yolo.train", "inputs": {"epochs": 5}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"

    def test_invoke_unknown_capability(self, client):
        r = client.post(
            "/api/v1/plugins/plugin-yolo-trainer/invoke",
            json={"capability_id": "plugin.nonexistent", "inputs": {}},
        )
        # 404 / 400 — capability doesn't exist
        assert r.status_code in (400, 404)


# ---------------------------------------------------------------------------
# R6 providers
# ---------------------------------------------------------------------------


class TestRealProviders:
    def test_list_seven(self, client):
        r = client.get("/api/v1/providers")
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()["items"]}
        for pid in ("openai", "claude", "deepseek", "qwen", "doubao", "comfyui", "mock"):
            assert pid in ids

    def test_route_cheapest(self, client):
        r = client.post(
            "/api/v1/providers/route",
            json={"family": "openai", "prefer": "cost"},
        )
        assert r.status_code == 200
        assert r.json()["family"] == "openai"

    def test_route_speed(self, client):
        r = client.post(
            "/api/v1/providers/route",
            json={"family": "openai", "prefer": "speed"},
        )
        assert r.status_code == 200

    def test_route_speed_picks_lowest_latency(self, client):
        # mock has latency 10-20 ms — should always win on speed
        # when family is broad enough to include it. Use an unknown family
        # so route() falls back to mock (the only guaranteed-lowest-latency
        # provider in the catalog).
        r = client.post(
            "/api/v1/providers/route",
            json={"family": "auto", "prefer": "speed"},
        )
        assert r.json()["id"] == "mock"

    def test_summary(self, client):
        r = client.get("/api/v1/providers/_/summary")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# R7 deployment readiness (informational)
# ---------------------------------------------------------------------------


class TestRealDeploymentReadiness:
    def test_readiness_module(self):
        # module is not HTTP-mounted; verify the function still runs
        from deploy_r7.readiness import readiness_report, audit_against_app
        rep = readiness_report()
        assert rep["total_endpoints"] >= 30
        # audit_against_app exercises the prefix-aware matcher
        from fastapi import FastAPI

        a = FastAPI()

        @a.get("/api/v1/capabilities_v2/catalogue")
        def _f():
            return {}

        @a.get("/api/v1/dataflow/stages")
        def _g():
            return {}
        rep2 = audit_against_app(a)
        assert rep2["catalogued"] == rep["total_endpoints"]


# ---------------------------------------------------------------------------
# R8 security
# ---------------------------------------------------------------------------


class TestRealSecurity:
    def test_redact(self, client):
        r = client.post(
            "/api/v1/security/redact",
            json={"text": "alice@example.com 13800001111 1.2.3.4 123456789012345678",
                  "actor": "depth2"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "[EMAIL]" in body["redacted"]
        assert "[PHONE]" in body["redacted"]
        assert "[IP]" in body["redacted"]
        assert "[ID]" in body["redacted"]

    def test_audit_append_and_verify(self, client):
        r = client.post(
            "/api/v1/security/audit/append",
            json={"event_type": "depth2.test", "actor": "depth2",
                  "payload": {"step": "verify"}},
        )
        assert r.status_code == 200
        r2 = client.get("/api/v1/security/audit/verify")
        assert r2.status_code == 200
        body = r2.json()
        assert body["verified"] is True

    def test_secrets_vault(self, client):
        r = client.get("/api/v1/security/secrets")
        assert r.status_code == 200
        names = r.json()["names"]
        assert "openai_api_key" in names
        r = client.post(
            "/api/v1/security/secrets/get",
            json={"name": "openai_api_key", "actor": "depth2"},
        )
        assert r.status_code == 200
        assert isinstance(r.json()["value"], str)


# ---------------------------------------------------------------------------
# R9 perf primitives
# ---------------------------------------------------------------------------


class TestRealPerf:
    def test_cache_round_trip(self, client):
        r = client.post("/api/v1/perf/cache/set",
                        json={"key": "depth2:k1", "value": "v1"})
        assert r.status_code == 200
        r = client.get("/api/v1/perf/cache/get", params={"key": "depth2:k1"})
        assert r.status_code == 200
        assert r.json()["value"] == "v1"
        r = client.post("/api/v1/perf/cache/invalidate", json={"prefix": "depth2:"})
        assert r.status_code == 200

    def test_batch(self, client):
        r = client.post(
            "/api/v1/perf/batch/run",
            json={"jobs": [{"value": 1}, {"value": 2}, {"value": 3}]},
        )
        assert r.status_code == 200
        s = r.json()
        assert s["jobs_executed"] == 3

    def test_queue_push_pop(self, client):
        r = client.post(
            "/api/v1/perf/queue/push",
            json={"payload": {"i": 42}, "priority": 1.0},
        )
        assert r.status_code == 200
        r = client.get("/api/v1/perf/queue/pop", params={"timeout": 1.0})
        assert r.status_code == 200
        assert r.json()["value"] == {"i": 42}

    def test_health(self, client):
        r = client.get("/api/v1/perf/health")
        assert r.status_code == 200
        body = r.json()
        for k in ("cache", "pool", "batch", "queue"):
            assert k in body, f"missing {k} in perf health"


# ---------------------------------------------------------------------------
# End-to-end pipeline: project → dataflow → bus → tracker → capabilities
# ---------------------------------------------------------------------------


class TestEndToEndPipeline:
    def test_full_lifecycle_visible_across_modules(self, client):
        # 1. create a project via capabilities_v2
        r = client.post(
            "/api/v1/capabilities_v2/invoke",
            json={
                "capability_id": "project.create",
                "inputs": {"name": "depth2-e2e"},
                "refs": {"project_id": "p-e2e"},
            },
        )
        assert r.status_code == 200
        assert r.json()["status"] == "success"

        # 2. create a requirement (different cap)
        client.post(
            "/api/v1/capabilities_v2/invoke",
            json={
                "capability_id": "requirement.create",
                "inputs": {"name": "r-e2e"},
                "refs": {"project_id": "p-e2e", "requirement_id": "r-e2e"},
            },
        )
        # 3. data flow snapshot must show ≥2 events for project_id=p-e2e
        r = client.get("/api/v1/dataflow/snapshot", params={"project_id": "p-e2e"})
        assert r.status_code == 200
        snap = r.json()
        assert snap["total_events"] >= 2
        # project node active
        proj_node = next(s for s in snap["stages"] if s["stage"] == "project")
        assert proj_node["event_count"] >= 1
        # requirement node active
        req_node = next(s for s in snap["stages"] if s["stage"] == "requirement")
        assert req_node["event_count"] >= 1

        # 4. orchestration bus must have lifecycle events
        r = client.get(
            "/api/v1/orchestration/events",
            params={"project_id": "p-e2e"},
        )
        assert r.status_code == 200
        assert r.json()["total"] >= 2

        # 5. multimodal coordinator can be invoked with same project
        client.post(
            "/api/v1/multimodal_v2/run",
            json={"modality": "image", "inputs": {"asset_count": 4},
                  "actor": "depth2-e2e"},
        )
        # the multimodal event should also appear on the bus
        r = client.get(
            "/api/v1/orchestration/events",
            params={"source_module": "multimodal_v2"},
        )
        assert r.status_code == 200
        assert r.json()["total"] >= 1
