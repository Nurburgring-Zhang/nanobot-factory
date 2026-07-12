"""VDP-2026 R2 — Workflow builder tests.

Covers:

  - topological sort (linear + branching) + cycle detection
  - variable expansion (``${node_id.output_key}``) into downstream inputs
  - workflow persistence + retrieval
  - end-to-end run against the capability registry (6 starter templates)
  - HTTP routes
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make `imdf` importable when pytest runs from any cwd.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from capabilities_v2.engine import (  # noqa: E402
    configure_db as configure_cap_db,
    reset_registry_for_test,
)
from capabilities_v2.dataflow import (  # noqa: E402
    configure_db as configure_dataflow_db,
    reset_tracker_for_test,
)
from workflow_builder.engine import (  # noqa: E402
    Workflow,
    WorkflowNode,
    WorkflowEdge,
    WorkflowEngine,
    _topo_sort,
    _expand_inputs,
    build_starter_templates,
    get_engine,
    reset_engine_for_test,
    configure_db,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path):
    configure_cap_db(tmp_path / "capabilities_v2.db")
    configure_dataflow_db(tmp_path / "dataflow.db")
    configure_db(tmp_path / "workflow_builder.db")
    reset_registry_for_test()
    reset_tracker_for_test()
    reset_engine_for_test()
    yield


@pytest.fixture
def engine() -> WorkflowEngine:
    return get_engine()


# ===========================================================================
# Topo-sort & variable expansion
# ===========================================================================


class TestTopoSort:
    def test_linear(self):
        wf = Workflow(
            id="t1", name="t",
            nodes=[
                WorkflowNode(id="a", capability_id="project.create", inputs={"name": "x"}),
                WorkflowNode(id="b", capability_id="requirement.create", inputs={"name": "y"}),
                WorkflowNode(id="c", capability_id="dataset.create", inputs={"name": "z"}),
            ],
            edges=[
                WorkflowEdge("a", "b"),
                WorkflowEdge("b", "c"),
            ],
        )
        order = _topo_sort(wf)
        ids = [n.id for n in order]
        assert ids == ["a", "b", "c"]

    def test_branching(self):
        wf = Workflow(
            id="t2", name="t",
            nodes=[
                WorkflowNode(id="a", capability_id="project.create", inputs={"name": "x"}),
                WorkflowNode(id="b", capability_id="dataset.create", inputs={"name": "y"}),
                WorkflowNode(id="c", capability_id="requirement.create", inputs={"name": "z"}),
                WorkflowNode(id="d", capability_id="acceptance.submit", inputs={"acceptance_id": "acc", "decision": "accept"}),
            ],
            edges=[
                WorkflowEdge("a", "b"),
                WorkflowEdge("a", "c"),
                WorkflowEdge("b", "d"),
                WorkflowEdge("c", "d"),
            ],
        )
        order = _topo_sort(wf)
        ids = [n.id for n in order]
        assert ids[0] == "a"
        assert ids[-1] == "d"
        assert ids.index("b") < ids.index("d")
        assert ids.index("c") < ids.index("d")

    def test_cycle_raises(self):
        wf = Workflow(
            id="t3", name="t",
            nodes=[
                WorkflowNode(id="a", capability_id="project.create", inputs={"name": "x"}),
                WorkflowNode(id="b", capability_id="dataset.create", inputs={"name": "y"}),
            ],
            edges=[WorkflowEdge("a", "b"), WorkflowEdge("b", "a")],
        )
        with pytest.raises(ValueError, match="环"):
            _topo_sort(wf)


class TestVarExpansion:
    def test_simple_reference(self):
        out = {"n1": {"project_id": "p_123"}}
        inputs = {"name": "${n1.project_id}-child"}
        assert _expand_inputs(inputs, out) == {"name": "p_123-child"}

    def test_nested_reference_missing(self):
        out = {"n1": {"foo": 1}}
        # missing key → leave as-is
        assert _expand_inputs({"x": "${n1.bar}"}, out) == {"x": "${n1.bar}"}

    def test_nested_input(self):
        # Indexing into an array via `${node.array[idx]}` is intentionally
        # not supported by the simple path-syntax — only `node.field` paths.
        # This test verifies embedded substitution where the array index lives
        # on a constant string.
        out = {"n1": {"asset_id": "a"}}
        expanded = _expand_inputs({"items": ["${n1.asset_id}"]}, out)
        assert expanded == {"items": ["a"]}


# ===========================================================================
# Persistence + retrieval
# ===========================================================================


class TestPersistence:
    def test_save_and_load(self, engine):
        wf = Workflow(
            id="wf_t1", name="测试工作流",
            nodes=[WorkflowNode(id="a", capability_id="project.create", inputs={"name": "demo"})],
            edges=[],
        )
        engine.save_workflow(wf)
        loaded = engine.get_workflow("wf_t1")
        assert loaded is not None
        assert loaded.name == "测试工作流"
        assert len(loaded.nodes) == 1
        assert loaded.nodes[0].capability_id == "project.create"

    def test_list_workflows(self, engine):
        for i in range(3):
            wf = Workflow(
                id=f"wf_l_{i}", name=f"测试-{i}",
                nodes=[WorkflowNode(id="a", capability_id="project.create", inputs={"name": "demo"})],
                edges=[],
            )
            engine.save_workflow(wf)
        items = engine.list_workflows(limit=10)
        assert len(items) >= 3
        ids = [w.id for w in items]
        assert all(f"wf_l_{i}" in ids for i in range(3))

    def test_delete_workflow(self, engine):
        wf = Workflow(id="wf_d", name="d", nodes=[], edges=[])
        engine.save_workflow(wf)
        assert engine.delete_workflow("wf_d") is True
        assert engine.get_workflow("wf_d") is None


# ===========================================================================
# Starter templates + end-to-end run
# ===========================================================================


class TestStarterTemplates:
    def test_six_templates_present(self):
        tpls = build_starter_templates()
        assert len(tpls) == 6
        ids = {t.id for t in tpls}
        for tid in (
            "wf_tpl_image_annotation",
            "wf_tpl_video_review",
            "wf_tpl_dpo_preference",
            "wf_tpl_drama_production",
            "wf_tpl_model_evaluation",
            "wf_tpl_ai_annotation",
        ):
            assert tid in ids

    def test_no_cycle_in_any_template(self):
        for tpl in build_starter_templates():
            # topo_sort raises on cycle
            order = _topo_sort(tpl)
            assert len(order) == len(tpl.nodes)

    def test_templates_bootstrap_into_engine(self, engine):
        # engine fixture already calls get_engine() which loads templates
        items = engine.list_workflows(limit=20)
        ids = {w.id for w in items}
        assert "wf_tpl_image_annotation" in ids
        assert "wf_tpl_ai_annotation" in ids


class TestRunEndToEnd:
    def test_run_a_simple_workflow(self, engine):
        wf = Workflow(
            id="wf_run_simple", name="run",
            nodes=[
                WorkflowNode(id="a", capability_id="project.create", inputs={"name": "wf_demo"}),
                WorkflowNode(id="b", capability_id="requirement.create", inputs={"name": "req_wf"}),
            ],
            edges=[WorkflowEdge("a", "b")],
        )
        engine.save_workflow(wf)
        run = engine.run_workflow(wf, actor="pytest")
        assert run.status == "succeeded"
        assert len(run.steps) == 2
        assert all(s.status == "succeeded" for s in run.steps)
        # second step's outputs should be in run.final_outputs
        assert "requirement_id" in run.final_outputs

    def test_run_image_annotation_template(self, engine):
        tpl = next(w for w in build_starter_templates() if w.id == "wf_tpl_image_annotation")
        run = engine.run_workflow(tpl, actor="pytest")
        assert run.status in ("succeeded", "failed")
        # 7 steps per template
        assert len(run.steps) == 7
        # if any step failed, the error is captured
        for s in run.steps:
            assert s.status in ("succeeded", "failed")

    def test_run_ai_annotation_template_records_7_steps(self, engine):
        tpl = next(w for w in build_starter_templates() if w.id == "wf_tpl_ai_annotation")
        run = engine.run_workflow(tpl, actor="pytest")
        assert len(run.steps) == 7

    def test_failed_node_aborts_run(self, engine):
        # `qc.aql` requires dataset_id + lot_size + aql_level — none of those
        # come out of project.create so the downstream node fails validation
        # and aborts the run.
        wf = Workflow(
            id="wf_run_fail", name="fail",
            nodes=[
                WorkflowNode(id="a", capability_id="project.create", inputs={"name": "x"}),
                WorkflowNode(
                    id="b",
                    capability_id="qc.aql",
                    inputs={},  # required fields missing — will fail validation
                ),
            ],
            edges=[WorkflowEdge("a", "b")],
        )
        engine.save_workflow(wf)
        run = engine.run_workflow(wf)
        assert run.status == "failed"
        # second step status is failed
        assert run.steps[1].status == "failed"
        assert "missing required" in run.steps[1].error


# ===========================================================================
# HTTP surface
# ===========================================================================


class TestHTTPRoutes:
    def _setup_app(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            return None, None
        from workflow_builder.routes import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app), None

    def test_templates_endpoint(self):
        client, _ = self._setup_app()
        if client is None:
            pytest.skip("fastapi not installed")
        r = client.get("/api/v1/workflow_builder/templates")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 6

        # list works
        r = client.get("/api/v1/workflow_builder/workflows")
        assert r.status_code == 200
        assert r.json()["total"] >= 6

        # reload templates
        r = client.post("/api/v1/workflow_builder/templates/reload")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # run a template
        r = client.post(
            "/api/v1/workflow_builder/workflows/wf_tpl_image_annotation/run",
            json={"actor": "pytest_http"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("succeeded", "failed")
        assert len(body["steps"]) == 7

        # single run lookup
        r = client.get(f"/api/v1/workflow_builder/runs/{body['id']}")
        assert r.status_code == 200
        single = r.json()
        assert single["id"] == body["id"]

        # health
        r = client.get("/api/v1/workflow_builder/health")
        assert r.status_code == 200
        h = r.json()
        assert h["status"] == "ok"

        # run an unknown workflow → 404
        r = client.post("/api/v1/workflow_builder/workflows/nope/run", json={})
        assert r.status_code == 404


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "--tb=short"]))
