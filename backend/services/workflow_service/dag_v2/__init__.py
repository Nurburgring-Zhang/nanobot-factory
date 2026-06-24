"""P4-6-W2: workflow_service dag_v2 — Advanced DAG engine + visual editor + operator marketplace.

Submodules
==========
* :mod:`.engine`   — AdvancedDAGEngine (7 node types, 4 edge types, 4 execution modes)
* :mod:`.visual`   — DAG → Vue Flow JSON + auto-layout (dagre / elk compatible)
* :mod:`.operators` — Operator marketplace registry (200+ operators)
* :mod:`.routes`   — FastAPI router mounted on the workflow-service app

The 7 node types
================
* ``input``         — workflow entry (no upstream)
* ``transform``     — generic operator (1→1 data)
* ``condition``     — branch (1→N, picks one branch)
* ``loop``          — iterate over collection (1→N, fan-out)
* ``parallel``      — fan-out / fan-in wrapper (1→N, 1→1)
* ``sub_workflow``  — nested workflow call (1→1)
* ``output``        — terminal (no downstream)

The 4 edge types
================
* ``data``    — passes payload forward
* ``control`` — gates execution (e.g. condition outcome)
* ``error``   — failure flow (skip / fallback)
* ``retry``   — explicit retry back-edge

The 4 execution modes
=====================
* ``sequential``      — strict serial topo
* ``parallel``        — concurrent within each wave
* ``fan_out_fan_in``  — explicitly N producers → 1 collector
* ``map_reduce``      — map step → shuffle → reduce step
"""

from .engine import (
    AdvancedDAGEngine,
    DAGDefinition,
    DAGNode,
    DAGEdge,
    EdgeType,
    ErrorPolicy,
    ExecMode,
    NodeStatus,
    NodeType,
    RunStepState,
    WorkflowRunState,
    get_advanced_dag_engine,
)
from .operators import (
    CATEGORIES,
    OPERATOR_REGISTRY,
    OperatorDef,
    OperatorVersion,
    SearchIndex,
    get_operator,
    list_operators,
    market_summary,
    search_operators,
)
from .visual import (
    auto_layout,
    dagre_layout,
    dag_to_flow_json,
    flow_json_to_dag,
    LayoutEngine,
)

__all__ = [
    "AdvancedDAGEngine",
    "DAGDefinition",
    "DAGNode",
    "DAGEdge",
    "EdgeType",
    "ErrorPolicy",
    "ExecMode",
    "NodeStatus",
    "NodeType",
    "RunStepState",
    "WorkflowRunState",
    "get_advanced_dag_engine",
    "CATEGORIES",
    "OPERATOR_REGISTRY",
    "OperatorDef",
    "OperatorVersion",
    "SearchIndex",
    "get_operator",
    "list_operators",
    "market_summary",
    "search_operators",
    "auto_layout",
    "dagre_layout",
    "dag_to_flow_json",
    "flow_json_to_dag",
    "LayoutEngine",
]
