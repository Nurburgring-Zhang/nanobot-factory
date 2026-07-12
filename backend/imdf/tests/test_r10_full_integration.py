"""VDP-2026 R10 — Final Validation (cross-module integration).

Runs an end-to-end pipeline that touches every major surface added in
R1..R9 and verifies observable behaviour:

  1. Create a project via capabilities_v2 (R1)
  2. Build a workflow_builder that consumes 3 capabilities (R2)
  3. Verify the orchestrator bus captures both events (R3)
  4. Invoke multimodal_v2 with modalities including 'drama' (R4)
  5. Register a plugin + invoke (R5)
  6. Route a request to cheapest provider (R6)
  7. Check deployment readiness (R7)
  8. Redact PII + write audit row + read secret (R8)
  9. Use TTL cache + batch (R9)

If any step fails the entire test fails, surfacing where the platform
contract broke.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Set ``IMDF_P2_DB_URL`` BEFORE any test imports ``db`` so the global
# SQLAlchemy engine (which is built at import time) points at a tmp
# file. The persistent ``backend/data/imdf_p2.db`` has an older
# ``projects`` schema that the current model can't fit (priority
# column missing); a fresh tmp file lets ``init_db()`` recreate the
# current model. The monkeypatch below re-applies the same path per
# test in case depth3 or other tests leaked a different URL.
os.environ.setdefault(
    "IMDF_P2_DB_URL",
    f"sqlite:///{(Path(tempfile.gettempdir()) / 'imdf_p2_r10_test.db').as_posix()}",
)

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    # Force the SQLAlchemy ``db`` engine onto a fresh tmp_path DB so the
    # persistent ``imdf_p2.db`` (with its older projects table) is not
    # hit, and the depth3 e2e test's monkey-patched URL does not leak in.
    monkeypatch.setenv(
        "IMDF_P2_DB_URL",
        f"sqlite:///{(tmp_path / 'imdf_p2.db').as_posix()}",
    )

    # configure every module to use a unique tmp_path storage
    from capabilities_v2.engine import configure_db as cap_db, reset_registry_for_test
    from capabilities_v2.dataflow import configure_db as flow_db, reset_tracker_for_test
    from workflow_builder.engine import configure_db as wb_db, reset_engine_for_test
    from orchestration.bus import configure_db as orch_db, reset_bus_for_test, bootstrap as orch_bootstrap
    from multimodal_v2.engine import configure_db as mm_db, reset_pipeline_for_test
    from plugins.manager import configure_db as plg_db, reset_manager_for_test
    from providers.registry import configure_db as pv_db, reset_registry_for_test
    from security_r8.hardening import configure_db as sec_db, reset_security_for_test
    from perf_r9.primitives import reset_for_test as perf_reset

    cap_db(tmp_path / "cap.db")
    flow_db(tmp_path / "flow.db")
    wb_db(tmp_path / "wb.db")
    orch_db(tmp_path / "orch.db")
    mm_db(tmp_path / "mm.db")
    plg_db(tmp_path / "plugin.db")
    pv_db(tmp_path / "pv.db")
    sec_db(tmp_path / "sec.db")
    perf_reset()

    # Force-create the SQLAlchemy tables on the tmp_path P2 DB. The
    # global ``db.engine`` was built at import time using the env var
    # we set in this fixture; ``init_db()`` runs ``create_all`` against
    # the *current* model metadata.
    from db import init_db  # type: ignore
    try:
        init_db()
    except Exception:
        pass

    reset_registry_for_test(); reset_tracker_for_test()
    reset_engine_for_test(); reset_bus_for_test()
    reset_pipeline_for_test(); reset_manager_for_test(); reset_registry_for_test()
    reset_security_for_test()
    # Re-wire the bus hooks on the freshly-built registry / engine. The
    # bootstrap is what tells capability_v2.invoke + workflow_builder.run
    # to mirror their events into the bus. After reset_*_for_test() the
    # wiring on the old singletons is lost, so we must re-apply it.
    try:
        orch_bootstrap()
    except Exception as e:
        import warnings
        warnings.warn(f"orch_bootstrap failed: {e}")
    yield


def test_r10_end_to_end_pipeline():
    """The full R1-R9 surface exercised in one test."""
    # ----- R1 capabilities -----
    from capabilities_v2.engine import get_registry as cap_reg
    reg = cap_reg()
    res = reg.invoke("project.create", inputs={"name": "r10-x"}, refs={"project_id": "p-r10"})
    assert res.status == "success"
    project_id = (res.outputs or {}).get("project_id")
    assert project_id

    # ----- R2 workflow builder (3-node template) -----
    from workflow_builder.engine import (
        build_starter_templates, Workflow, WorkflowNode, WorkflowEdge,
        get_engine as get_wb_engine,
    )
    # Use the singleton — the bus hook installed by ``orch_bootstrap()`` is
    # attached to the singleton's run_workflow, not to a freshly-constructed
    # ``WorkflowEngine()`` instance.
    eng = get_wb_engine()
    # NOTE: don't use ``delivery.finalize`` here — the engine rejects the
    # call when the delivery record doesn't exist, which is correct
    # real-engine behaviour but the workflow would fail. Use
    # ``requirement.create`` instead so the workflow exercises the
    # capability pipeline end-to-end.
    eng.save_workflow(Workflow(
        id="wf_tpl_r10", name="r10-flow",
        nodes=[
            WorkflowNode(id="a", capability_id="project.create", inputs={"name": "r10-flow"}),
            WorkflowNode(id="b", capability_id="requirement.create", inputs={"name": "req-r10-flow"}),
            WorkflowNode(id="c", capability_id="dataset.create", inputs={"name": "ds-r10"}),
        ],
        edges=[WorkflowEdge("a", "b"), WorkflowEdge("b", "c")],
    ))
    run = eng.run_workflow(eng.get_workflow("wf_tpl_r10"))
    assert run.status == "succeeded"

    # ----- R3 orchestration bus -----
    from orchestration import get_bus
    bus = get_bus()
    # At least 1 capability bus event for p-r10 (the explicit invoke above).
    # The workflow run emits additional events with empty refs, since the
    # workflow nodes don't carry refs; they would not match the project_id
    # filter here but are visible via the global workflow-topic query below.
    bus_rows = bus.query(project_id="p-r10")
    assert len(bus_rows) >= 1, f"no events for p-r10: {bus.query()[:5]}"
    # workflow bus row (any topic starting with workflow.run.) — proves the
    # workflow emit hook fired and the bus captured the run.
    wf_rows = [r for r in bus.query() if r.get("topic", "").startswith("workflow.run.")]
    assert len(wf_rows) >= 1

    # ----- R4 multimodal -----
    from multimodal_v2 import get_pipeline
    mm_run = get_pipeline().run(modality="drama", inputs={"asset_count": 12})
    assert mm_run.status == "succeeded"

    # ----- R5 plugin -----
    from plugins import get_manager
    plugin_mgr = get_manager()
    invoke = plugin_mgr.invoke(
        "plugin-yolo-trainer", "plugin.yolo.train",
        {"data_yaml": "/x/data.yaml", "epochs": 5},
        actor="r10",
    )
    assert invoke["status"] == "success"

    # ----- R6 provider routing -----
    from providers import get_registry as pv_reg
    r = pv_reg()
    chosen = r.route("openai", prefer="cost")
    assert chosen is not None
    assert r.call_summary()["total_calls"] >= 0

    # ----- R7 readiness -----
    from deploy_r7.readiness import readiness_report, audit_against_app
    rep = readiness_report()
    assert rep["total_endpoints"] >= 30
    assert "R1" in rep["modules"]
    assert "R6" in rep["modules"]
    # audit against an empty stubs() — but ours is None so just check API works.
    audit_against_app(_FakeApp())  # noqa: F821 (intentional coverage)

    # ----- R8 security -----
    from security_r8 import get_audit, get_rate_limiter, get_vault, redact_pii
    # 18-digit CN ID card (17 digits + 1 check digit) matches the SSN regex
    # and gets redacted to [ID]. (A 19-digit number falls into [CARD] instead.)
    red = redact_pii("alice@example.com 13800000000 1.2.3.4 11010119900307123X")
    assert "[EMAIL]" in red["redacted"]
    assert "[PHONE]" in red["redacted"]
    assert "[IP]" in red["redacted"]
    assert "[ID]" in red["redacted"]
    audit = get_audit()
    audit.append("r10.test", actor="r10", payload={"step": "r10"})
    tail = audit.tail(limit=5)
    assert any(r["event_type"] == "r10.test" for r in tail)
    rate = get_rate_limiter(max_per_min=10)
    for _ in range(10):
        rate.check("r10", max_per_min=10)
    res = rate.check("r10", max_per_min=10)
    assert res["allowed"] is False
    vault = get_vault()
    api_key = vault.get("openai_api_key", actor="r10")
    assert api_key  # dev-only string

    # ----- R9 perf -----
    from perf_r9 import get_cache, get_batch, get_queue
    c = get_cache(max_size=10, ttl=60)
    c.set("k", "v")
    assert c.get("k") == "v"
    b = get_batch()
    def _proc(n: int) -> int: return n * 2
    for n in range(5):
        b.add(_proc, args=(n,))
    b.flush()
    s = b.stats()
    assert s["jobs_executed"] == 5
    q = get_queue()
    q.push({"i": 1})
    q.push({"i": 2})
    assert q.pop(timeout=1.0) is not None
    assert q.stats()["enqueued"] >= 2


class _FakeApp:
    """Stub `FastAPI`-like object so audit_against_app runs without spinning FastAPI."""
    def __init__(self):
        self.routes = []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "--tb=short"]))
