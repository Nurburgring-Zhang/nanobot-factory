"""VDP-2026 R2 — Workflow Builder.

Composes the platform's `capabilities_v2` capabilities into executable workflows.

A workflow is a directed graph:

  {
    "id": "wf_<hash>",
    "name": "图像标注流",
    "nodes": [
      {
        "id": "n1",
        "capability_id": "project.create",
        "inputs": {"name": "demo"},  // optional, can be ${input.foo} var-refs
        "depends_on": [],             // optional override; we infer from edges
        "position": {"x": 0, "y": 0}  // canvas position
      },
      ...
    ],
    "edges": [
      {"source": "n1", "target": "n2", "kind": "data"}
    ]
  }

The runner walks a topological order, invokes each capability through the
`CapabilityRegistry`, threads outputs forward as `node_outputs[node_id]`, and
records the run result. Each node invocation also emits the capability's
domain event into `DataFlowTracker` so R1's lifecycle view auto-lights up.

Schema compatibility: we use a lightweight JSON-Schema check from
`workflow_contract_routes` already shipped in the v1.0 release — wired in by
the route layer.
"""
from .engine import (
    WorkflowEngine,
    WorkflowNode,
    WorkflowEdge,
    Workflow,
    WorkflowRun,
    StepResult,
    build_starter_templates,
    get_engine,
)
from .routes import router

# `WorkflowBuilder` is exposed as the public name of the engine for callers
# that prefer the more declarative API surface.
WorkflowBuilder = WorkflowEngine

__all__ = [
    "WorkflowBuilder",
    "WorkflowEngine",
    "WorkflowNode",
    "WorkflowEdge",
    "Workflow",
    "WorkflowRun",
    "StepResult",
    "build_starter_templates",
    "get_engine",
    "router",
] 
