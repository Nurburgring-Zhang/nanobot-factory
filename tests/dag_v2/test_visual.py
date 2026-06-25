"""P4-6-W2: visual editor tests (3 tests).

Covers:
  1. dag_to_flow_json round-trip with a 6-node DAG
  2. dagre_layout assigns monotonic x positions
  3. flow_json_to_dag accepts a Vue Flow payload
"""
from __future__ import annotations

import pytest

from services.workflow_service.dag_v2.engine import (
    DAGEdge,
    DAGDefinition,
    DAGNode,
    EdgeType,
    NodeType,
)
from services.workflow_service.dag_v2.visual import (
    LayoutEngine,
    auto_layout,
    dag_to_flow_json,
    dagre_layout,
    flow_json_to_dag,
)


def _demo_dag() -> DAGDefinition:
    return DAGDefinition(
        id="wf-visual-test", name="visual test",
        nodes=[
            DAGNode(id="input", name="user input", node_type=NodeType.INPUT),
            DAGNode(id="transform", name="normalise",
                    node_type=NodeType.TRANSFORM, inputs=["input"]),
            DAGNode(id="condition", name="needs review?",
                    node_type=NodeType.CONDITION, inputs=["transform"]),
            DAGNode(id="par_a", name="path A", node_type=NodeType.PARALLEL,
                    inputs=["condition"]),
            DAGNode(id="par_b", name="path B", node_type=NodeType.PARALLEL,
                    inputs=["condition"]),
            DAGNode(id="output", name="final", node_type=NodeType.OUTPUT,
                    inputs=["par_a", "par_b"]),
        ],
        edges=[
            DAGEdge("input", "transform"),
            DAGEdge("transform", "condition"),
            DAGEdge("condition", "par_a", edge_type=EdgeType.CONTROL),
            DAGEdge("condition", "par_b", edge_type=EdgeType.CONTROL),
            DAGEdge("par_a", "output"),
            DAGEdge("par_b", "output"),
        ],
    )


# =====================================================================
# 1) round-trip
# =====================================================================

def test_dag_to_flow_json_round_trip():
    d = _demo_dag()
    flow = dag_to_flow_json(d, layout=True, direction="LR")
    assert flow["workflowId"] == d.id
    assert len(flow["nodes"]) == 6
    assert len(flow["edges"]) == 6
    # every node has a position
    for n in flow["nodes"]:
        assert "position" in n
        assert "x" in n["position"] and "y" in n["position"]
    # node type mapping covers the 3 types we used
    types_used = {n["type"] for n in flow["nodes"]}
    assert "input" in types_used
    assert "transform" in types_used
    assert "condition" in types_used
    assert "parallel" in types_used
    assert "output" in types_used

    # round-trip
    back = flow_json_to_dag(flow)
    assert back.id == d.id
    assert {n.id for n in back.nodes} == {n.id for n in d.nodes}
    assert {(e.source, e.target) for e in back.edges
            if e.edge_type in (EdgeType.DATA, EdgeType.CONTROL)} == \
           {(e.source, e.target) for e in d.edges}


# =====================================================================
# 2) layout
# =====================================================================

def test_dagre_layout_monotonic_x():
    d = _demo_dag()
    pos = dagre_layout(d, direction="LR")
    # input/transform/condition are in different waves → x strictly increasing
    assert pos["input"][0] < pos["transform"][0] < pos["condition"][0]
    # parallel branch: par_a & par_b share the same wave
    assert pos["par_a"][0] == pos["par_b"][0]
    # output is the rightmost
    assert pos["output"][0] > pos["par_a"][0]


def test_layout_engine_registry():
    assert "dagre" in LayoutEngine.list()
    assert "elk" in LayoutEngine.list()
    pos = auto_layout(_demo_dag(), engine="dagre", direction="TB")
    # TB: y strictly increases with wave index
    assert pos["input"][1] < pos["transform"][1] < pos["condition"][1]


# =====================================================================
# 3) flow import
# =====================================================================

def test_flow_json_to_dag_accepts_payload():
    payload = {
        "workflowId": "wf-import-test",
        "nodes": [
            {"id": "n1", "type": "input", "position": {"x": 0, "y": 0},
             "data": {"name": "in", "nodeType": "input",
                      "operatorId": "op.generator.sdxl_txt2img"}},
            {"id": "n2", "type": "output", "position": {"x": 200, "y": 0},
             "data": {"name": "out", "nodeType": "output"}},
        ],
        "edges": [
            {"source": "n1", "target": "n2", "sourceHandle": "out",
             "targetHandle": "in", "data": {"edgeType": "data"}},
        ],
    }
    d = flow_json_to_dag(payload)
    assert d.id == "wf-import-test"
    assert {n.id for n in d.nodes} == {"n1", "n2"}
    # n2 should pick up n1 as an upstream (inferred from edges)
    assert "n1" in next(n for n in d.nodes if n.id == "n2").inputs
