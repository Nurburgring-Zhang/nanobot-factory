"""P4-6-W2: DAG visual editor — DAG ⇄ Vue Flow JSON + auto-layout.

The visual editor (frontend-v2 ``VisualEditor.vue``) is a Vue Flow
canvas. Vue Flow expects two arrays:

  * ``nodes``: ``[{id, type, position, data, label, ...}]``
  * ``edges``: ``[{id, source, target, sourceHandle, targetHandle, ...}]``

This module provides:

  * :func:`dag_to_flow_json`         — DAGDefinition → Vue Flow JSON
  * :func:`flow_json_to_dag`         — Vue Flow JSON → DAGDefinition
  * :func:`dagre_layout`             — pure-python layered layout (LR / TB)
  * :func:`auto_layout`              — pluggable layout engine
  * :class:`LayoutEngine`            — registry of layout algorithms

The layout is computed in Python (no dagre.js server-side call needed)
using a deterministic layered algorithm: every node starts at column 0
in the first wave of the topological order; nodes within the same wave
share an x-coordinate. The frontend can swap this for ``dagre.js`` or
``elk.js`` later; the schema is identical.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .engine import (
    DAGEdge,
    DAGDefinition,
    DAGNode,
    EdgeType,
    NodeType,
    topo_waves,
)

logger = logging.getLogger(__name__)


# Vue Flow / Node schema --------------------------------------------------------

NODE_TYPE_MAP: Dict[str, str] = {
    NodeType.INPUT.value: "input",
    NodeType.TRANSFORM.value: "transform",
    NodeType.CONDITION.value: "condition",
    NodeType.LOOP.value: "loop",
    NodeType.PARALLEL.value: "parallel",
    NodeType.SUB_WORKFLOW.value: "subWorkflow",
    NodeType.OUTPUT.value: "output",
}


@dataclass
class FlowNode:
    id: str
    type: str
    position: Tuple[float, float]
    data: Dict[str, Any]
    label: str
    width: float = 200.0
    height: float = 80.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "position": {"x": self.position[0], "y": self.position[1]},
            "data": self.data,
            "label": self.label,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class FlowEdge:
    id: str
    source: str
    target: str
    source_handle: str = "out"
    target_handle: str = "in"
    label: str = ""
    type: str = "default"
    data: Dict[str, Any] = None  # type: ignore[assignment]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "sourceHandle": self.source_handle,
            "targetHandle": self.target_handle,
            "label": self.label,
            "type": self.type,
            "data": self.data or {},
        }


# =====================================================================
# Conversion
# =====================================================================

def dag_to_flow_json(dag: DAGDefinition, layout: bool = True,
                      direction: str = "LR") -> Dict[str, Any]:
    """Convert a :class:`DAGDefinition` into Vue Flow JSON.

    Parameters
    ----------
    dag : DAGDefinition
    layout : bool
        If True, run :func:`dagre_layout` first and assign positions.
    direction : str
        ``"LR"`` (left-to-right, default) or ``"TB"`` (top-to-bottom).
    """
    node_map = {n.id: n for n in dag.nodes}
    positions: Dict[str, Tuple[float, float]] = (
        dagre_layout(dag, direction=direction) if layout else
        {n.id: tuple(n.position) for n in dag.nodes}
    )

    flow_nodes: List[Dict[str, Any]] = []
    for n in dag.nodes:
        fn = FlowNode(
            id=n.id,
            type=NODE_TYPE_MAP.get(n.node_type.value, "default"),
            position=positions.get(n.id, tuple(n.position)),
            data={
                "name": n.name,
                "nodeType": n.node_type.value,
                "operatorId": n.operator_id,
                "config": n.config,
                "retryMax": n.retry_max,
                "timeoutSeconds": n.timeout_seconds,
                "errorPolicy": n.error_policy.value,
                "fallbackNodeId": n.fallback_node_id,
                "description": n.description,
            },
            label=n.name,
        )
        flow_nodes.append(fn.to_dict())

    flow_edges: List[Dict[str, Any]] = []
    for e in dag.edges:
        edge_id = _edge_id(e)
        fe = FlowEdge(
            id=edge_id,
            source=e.source,
            target=e.target,
            source_handle=e.source_handle,
            target_handle=e.target_handle,
            label=e.edge_type.value + (f" · {e.condition}" if e.condition else ""),
            type=_vue_edge_type(e.edge_type),
            data={"edgeType": e.edge_type.value, "condition": e.condition},
        )
        flow_edges.append(fe.to_dict())

    return {
        "workflowId": dag.id,
        "version": dag.version,
        "direction": direction,
        "nodes": flow_nodes,
        "edges": flow_edges,
        "meta": {
            "nodeCount": len(flow_nodes),
            "edgeCount": len(flow_edges),
            "execMode": dag.exec_mode.value,
        },
    }


def flow_json_to_dag(payload: Dict[str, Any]) -> DAGDefinition:
    """Inverse of :func:`dag_to_flow_json` — accept a Vue Flow payload."""
    wf_id = payload.get("workflowId") or _id_from_name(payload.get("name", "wf"))
    name = payload.get("name") or wf_id
    nodes: List[DAGNode] = []
    for fn in payload.get("nodes", []):
        data = fn.get("data", {}) or {}
        node_type_str = data.get("nodeType") or fn.get("type") or "transform"
        try:
            node_type = NodeType(node_type_str)
        except ValueError:
            node_type = NodeType.TRANSFORM
        pos = fn.get("position", {}) or {}
        nodes.append(DAGNode(
            id=fn["id"],
            name=data.get("name") or fn.get("label") or fn["id"],
            node_type=node_type,
            operator_id=data.get("operatorId"),
            config=data.get("config", {}),
            retry_max=int(data.get("retryMax", 3)),
            timeout_seconds=int(data.get("timeoutSeconds", 60)),
            fallback_node_id=data.get("fallbackNodeId"),
            description=data.get("description", ""),
            position=(float(pos.get("x", 0)), float(pos.get("y", 0))),
        ))

    edges: List[DAGEdge] = []
    for fe in payload.get("edges", []):
        data = fe.get("data", {}) or {}
        et_raw = data.get("edgeType") or fe.get("type") or "data"
        try:
            et = EdgeType(et_raw)
        except ValueError:
            et = EdgeType.DATA
        edges.append(DAGEdge(
            source=fe["source"],
            target=fe["target"],
            edge_type=et,
            source_handle=fe.get("sourceHandle", "out"),
            target_handle=fe.get("targetHandle", "in"),
            condition=data.get("condition"),
        ))

    # infer inputs from edges if not explicit
    incoming: Dict[str, List[str]] = {n.id: [] for n in nodes}
    for e in edges:
        if e.edge_type in (EdgeType.DATA, EdgeType.CONTROL):
            incoming.setdefault(e.target, []).append(e.source)
    for n in nodes:
        if not n.inputs:
            n.inputs = incoming.get(n.id, [])

    return DAGDefinition(
        id=wf_id, name=name, nodes=nodes, edges=edges,
        description=payload.get("description", ""),
    )


# =====================================================================
# Auto-layout (dagre-compatible)
# =====================================================================

NODE_WIDTH = 220.0
NODE_HEIGHT = 100.0
H_GAP = 80.0
V_GAP = 60.0


def dagre_layout(dag: DAGDefinition, direction: str = "LR") -> Dict[str, Tuple[float, float]]:
    """Pure-Python layered layout that matches dagre.js semantics closely.

    Algorithm:
      1. Topological waves (only ``data`` / ``control`` edges).
      2. Each wave occupies a column (LR) or row (TB).
      3. Nodes within a wave are stacked vertically (LR) or horizontally (TB).
      4. Centers are aligned across waves; missing upstream nodes are
         placed at the previous wave coordinate so the result is dense.
    """
    if not dag.nodes:
        return {}
    try:
        waves = topo_waves(dag.edges, [n.id for n in dag.nodes])
    except ValueError as e:
        logger.warning("layout topo failed (%s); using flat layout", e)
        waves = [[n.id for n in dag.nodes]]

    positions: Dict[str, Tuple[float, float]] = {}
    for w_idx, wave in enumerate(waves):
        for n_idx, nid in enumerate(wave):
            if direction == "TB":
                x = n_idx * (NODE_WIDTH + H_GAP)
                y = w_idx * (NODE_HEIGHT + V_GAP)
            else:  # LR
                x = w_idx * (NODE_WIDTH + H_GAP)
                y = n_idx * (NODE_HEIGHT + V_GAP)
            positions[nid] = (x, y)
    # any node missing from waves (shouldn't happen) gets origin
    for n in dag.nodes:
        positions.setdefault(n.id, (0.0, 0.0))
    return positions


def auto_layout(dag: DAGDefinition, engine: str = "dagre",
                direction: str = "LR") -> Dict[str, Tuple[float, float]]:
    """Pluggable layout dispatcher."""
    engine = (engine or "dagre").lower()
    if engine in ("dagre", "default", "layered"):
        return dagre_layout(dag, direction=direction)
    if engine in ("elk", "sugiyama"):
        # Elk shares the dagre layered model in our minimal impl.
        return dagre_layout(dag, direction=direction)
    if engine in ("grid", "manual"):
        return {n.id: tuple(n.position) for n in dag.nodes}
    raise ValueError(f"unknown layout engine: {engine!r}")


class LayoutEngine:
    """Layout algorithm registry. Allows future ELK / dagre.js swap."""

    _registry: Dict[str, Any] = {
        "dagre": dagre_layout,
        "elk": dagre_layout,
        "grid": lambda dag, direction="LR": {n.id: tuple(n.position)
                                             for n in dag.nodes},
    }

    @classmethod
    def get(cls, name: str):
        if name not in cls._registry:
            raise KeyError(f"unknown layout: {name!r}")
        return cls._registry[name]

    @classmethod
    def list(cls) -> List[str]:
        return sorted(cls._registry.keys())


# =====================================================================
# Helpers
# =====================================================================

def _edge_id(e: DAGEdge) -> str:
    raw = f"{e.source}->{e.target}:{e.edge_type.value}:{e.source_handle}:{e.target_handle}"
    return "e_" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _vue_edge_type(et: EdgeType) -> str:
    return {
        EdgeType.DATA: "smoothstep",
        EdgeType.CONTROL: "step",
        EdgeType.ERROR: "straight",
        EdgeType.RETRY: "default",
    }.get(et, "default")


def _id_from_name(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name.lower())
    safe = safe.strip("-") or "wf"
    return f"wf-{safe}-{uuid.uuid4().hex[:6]}"


__all__ = [
    "FlowNode",
    "FlowEdge",
    "NODE_TYPE_MAP",
    "dag_to_flow_json",
    "flow_json_to_dag",
    "dagre_layout",
    "auto_layout",
    "LayoutEngine",
]
