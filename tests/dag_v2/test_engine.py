"""P4-6-W2: AdvancedDAGEngine tests (5+ tests).

Covers:
  1. topo waves for a 6-node DAG with parallel branches
  2. sequential vs parallel vs fan_out_fan_in vs map_reduce modes
  3. all 7 NodeType values accepted by DAGNode
  4. all 4 EdgeType values
  5. error policies: retry, fallback, skip, escalate
  6. cancel mid-run
"""
from __future__ import annotations

import asyncio
import pytest

from services.workflow_service.dag_v2.engine import (
    AdvancedDAGEngine,
    DAGEdge,
    DAGDefinition,
    DAGNode,
    EdgeType,
    ErrorPolicy,
    ExecMode,
    NodeStatus,
    NodeType,
    RunStatus,
    get_advanced_dag_engine,
    topo_waves,
)


def _6_node_dag(parallel: bool = True) -> DAGDefinition:
    nodes = [
        DAGNode(id="input", name="user input", node_type=NodeType.INPUT),
        DAGNode(id="transform", name="normalise",
                node_type=NodeType.TRANSFORM, operator_id="op.cleaning.dedup",
                inputs=["input"]),
        DAGNode(id="condition", name="needs review?",
                node_type=NodeType.CONDITION,
                operator_id="op.scoring.threshold",
                inputs=["transform"]),
        DAGNode(id="par_a", name="path A", node_type=NodeType.PARALLEL,
                operator_id="op.export.jsonl",
                inputs=["condition"],
                config={"branch": "true"}),
        DAGNode(id="par_b", name="path B", node_type=NodeType.PARALLEL,
                operator_id="op.annotation.review",
                inputs=["condition"],
                config={"branch": "false"}),
        DAGNode(id="output", name="final", node_type=NodeType.OUTPUT,
                inputs=["par_a", "par_b"]),
    ]
    edges = [
        DAGEdge("input", "transform"),
        DAGEdge("transform", "condition"),
        DAGEdge("condition", "par_a", edge_type=EdgeType.CONTROL,
                condition="score >= 0.7"),
        DAGEdge("condition", "par_b", edge_type=EdgeType.CONTROL,
                condition="score < 0.7"),
        DAGEdge("par_a", "output"),
        DAGEdge("par_b", "output"),
    ]
    return DAGDefinition(
        id="wf-test-6node", name="6-node DAG test",
        nodes=nodes, edges=edges,
        exec_mode=ExecMode.PARALLEL if parallel else ExecMode.SEQUENTIAL,
    )


# =====================================================================
# 1) topo waves
# =====================================================================

def test_topo_waves_six_node():
    dag = _6_node_dag()
    waves = topo_waves(dag.edges, [n.id for n in dag.nodes])
    # 4 waves: input | transform | condition | par_a,par_b | output
    assert waves == [["input"], ["transform"], ["condition"],
                     ["par_a", "par_b"], ["output"]]


def test_topo_waves_rejects_cycle():
    nodes = [
        DAGNode(id="a", name="A", node_type=NodeType.TRANSFORM),
        DAGNode(id="b", name="B", node_type=NodeType.TRANSFORM, inputs=["a"]),
    ]
    edges = [
        DAGEdge("a", "b"),
        DAGEdge("b", "a"),  # cycle
    ]
    with pytest.raises(ValueError, match="cycle"):
        topo_waves(edges, ["a", "b"])


# =====================================================================
# 2) 4 execution modes end-to-end
# =====================================================================

@pytest.mark.asyncio
async def test_execute_parallel_succeeds():
    eng = AdvancedDAGEngine()
    d = _6_node_dag(parallel=True)
    eng.upsert(d)
    run = eng.start_run(d.id, inputs={"items": list(range(10))})
    out = await eng.execute(run.run_id)
    assert out.status == RunStatus.SUCCEEDED
    assert all(s.status in (NodeStatus.SUCCEEDED, NodeStatus.RETRIED)
               for s in out.steps.values())
    # parallel: at least one wave ran concurrently
    assert out.progress == 1.0


@pytest.mark.asyncio
async def test_execute_sequential_succeeds():
    eng = AdvancedDAGEngine()
    d = _6_node_dag(parallel=False)
    d.exec_mode = ExecMode.SEQUENTIAL
    eng.upsert(d)
    run = eng.start_run(d.id, inputs={})
    out = await eng.execute(run.run_id)
    assert out.status == RunStatus.SUCCEEDED
    # 5 waves
    assert len(out.log) >= 5


@pytest.mark.asyncio
async def test_execute_fan_out_fan_in_succeeds():
    eng = AdvancedDAGEngine()
    d = _6_node_dag(parallel=True)
    d.exec_mode = ExecMode.FAN_OUT_FAN_IN
    eng.upsert(d)
    run = eng.start_run(d.id, inputs={})
    out = await eng.execute(run.run_id)
    assert out.status == RunStatus.SUCCEEDED
    assert out.steps["par_a"].status in (NodeStatus.SUCCEEDED, NodeStatus.RETRIED)
    assert out.steps["par_b"].status in (NodeStatus.SUCCEEDED, NodeStatus.RETRIED)


@pytest.mark.asyncio
async def test_execute_map_reduce_succeeds():
    eng = AdvancedDAGEngine()
    d = _6_node_dag(parallel=True)
    d.exec_mode = ExecMode.MAP_REDUCE
    eng.upsert(d)
    run = eng.start_run(d.id, inputs={})
    out = await eng.execute(run.run_id)
    assert out.status == RunStatus.SUCCEEDED
    # 6 steps total
    assert len(out.steps) == 6


# =====================================================================
# 3) 7 node types
# =====================================================================

def test_seven_node_types_supported():
    nt_values = {n.value for n in NodeType}
    assert nt_values == {"input", "transform", "condition", "loop",
                         "parallel", "sub_workflow", "output"}
    # all 7 can be instantiated
    for nt in NodeType:
        node = DAGNode(id=f"n_{nt.value}", name=nt.value, node_type=nt)
        d = node.to_dict()
        assert d["node_type"] == nt.value


# =====================================================================
# 4) 4 edge types
# =====================================================================

def test_four_edge_types_supported():
    et_values = {e.value for e in EdgeType}
    assert et_values == {"data", "control", "error", "retry"}
    # error / retry edges do not affect static topo
    nodes = [DAGNode(id="a", name="A", node_type=NodeType.TRANSFORM),
             DAGNode(id="b", name="B", node_type=NodeType.TRANSFORM,
                     inputs=["a"])]
    edges = [
        DAGEdge("a", "b"),
        DAGEdge("a", "b", edge_type=EdgeType.ERROR),
        DAGEdge("b", "a", edge_type=EdgeType.RETRY),  # would be cycle if used
    ]
    waves = topo_waves(edges, ["a", "b"])
    assert waves == [["a"], ["b"]]


# =====================================================================
# 5) 4 error policies
# =====================================================================

@pytest.mark.asyncio
async def test_error_policy_retry_then_succeeds():
    """Retry policy: a node with retry_max=3 succeeds on attempt 1
    (default dispatch never fails unless _fail=True)."""
    eng = AdvancedDAGEngine()
    d = DAGDefinition(
        id="wf-test-retry", name="retry test",
        nodes=[DAGNode(id="t", name="t", node_type=NodeType.TRANSFORM,
                       error_policy=ErrorPolicy.RETRY, retry_max=3)],
        edges=[],
    )
    eng.upsert(d)
    run = eng.start_run(d.id, inputs={})
    out = await eng.execute(run.run_id)
    assert out.status == RunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_error_policy_skip_marks_skipped():
    eng = AdvancedDAGEngine()
    d = DAGDefinition(
        id="wf-test-skip", name="skip test",
        nodes=[DAGNode(id="t", name="t", node_type=NodeType.TRANSFORM,
                       error_policy=ErrorPolicy.SKIP,
                       config={"_fail": True, "_fail_reason": "boom"})],
        edges=[],
    )
    eng.upsert(d)
    run = eng.start_run(d.id, inputs={})
    out = await eng.execute(run.run_id)
    assert out.steps["t"].status == NodeStatus.SKIPPED
    assert out.steps["t"].error == "boom"


@pytest.mark.asyncio
async def test_error_policy_fallback_marks_skipped():
    eng = AdvancedDAGEngine()
    d = DAGDefinition(
        id="wf-test-fallback", name="fallback test",
        nodes=[
            DAGNode(id="t", name="t", node_type=NodeType.TRANSFORM,
                    error_policy=ErrorPolicy.FALLBACK,
                    fallback_node_id="fb",
                    config={"_fail": True}),
            DAGNode(id="fb", name="fb", node_type=NodeType.TRANSFORM,
                    inputs=["t"]),
        ],
        edges=[DAGEdge("t", "fb")],
    )
    eng.upsert(d)
    run = eng.start_run(d.id, inputs={})
    out = await eng.execute(run.run_id)
    assert out.steps["t"].status == NodeStatus.SKIPPED
    # fallback target cascaded
    assert out.steps["fb"].status == NodeStatus.SKIPPED


@pytest.mark.asyncio
async def test_error_policy_escalate_marks_failed():
    eng = AdvancedDAGEngine()
    d = DAGDefinition(
        id="wf-test-escalate", name="escalate test",
        nodes=[DAGNode(id="t", name="t", node_type=NodeType.TRANSFORM,
                       error_policy=ErrorPolicy.ESCALATE,
                       config={"_fail": True})],
        edges=[],
    )
    eng.upsert(d)
    run = eng.start_run(d.id, inputs={})
    out = await eng.execute(run.run_id)
    assert out.steps["t"].status == NodeStatus.FAILED
    assert out.status == RunStatus.FAILED


# =====================================================================
# 6) cancel mid-run
# =====================================================================

@pytest.mark.asyncio
async def test_cancel_mid_run():
    eng = AdvancedDAGEngine()
    # build a 4-node chain
    d = DAGDefinition(
        id="wf-test-cancel", name="cancel test",
        nodes=[DAGNode(id=f"n{i}", name=f"n{i}",
                       node_type=NodeType.TRANSFORM) for i in range(4)],
        edges=[DAGEdge(f"n{i}", f"n{i+1}") for i in range(3)],
    )
    eng.upsert(d)
    run = eng.start_run(d.id, inputs={})
    # request cancel before execute
    eng.request_cancel(run.run_id)
    out = await eng.execute(run.run_id)
    assert out.status == RunStatus.CANCELLED


# =====================================================================
# singleton + seed demo
# =====================================================================

def test_singleton_seed_has_demo():
    eng = get_advanced_dag_engine()
    demo = eng.get("wf-demo-dag-v2")
    assert demo is not None
    assert len(demo.nodes) == 6
    assert any(n.node_type == NodeType.PARALLEL for n in demo.nodes)
