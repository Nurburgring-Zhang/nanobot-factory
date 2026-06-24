"""P3-3-W2: workflow-service DAG execution engine.

A lightweight in-memory DAG runtime that:
  * Stores workflow definitions (nodes + edges)
  * Tracks workflow runs (status, per-node status, logs)
  * Computes topological execution order
  * Provides failure-retry per node
  * Exposes a singleton ``DAGRuntime`` via ``get_dag_runtime()``

It is deliberately decoupled from any specific worker service - each
``NodeSpec.node_type`` maps to a logical capability (e.g. ``"cleaning"``,
``"scoring"``, ``"export"``) and the executor dispatches by string. Real
service calls happen in a future P3-4 iteration; for now each node
returns a stubbed success after a short delay so the DAG ordering
behaviour is observable in tests.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =====================================================================
# Enums
# =====================================================================

class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"  # some nodes failed, workflow continues


class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


# =====================================================================
# Data models
# =====================================================================

@dataclass
class NodeSpec:
    """One node in the DAG."""
    id: str
    name: str
    node_type: str  # "cleaning" / "scoring" / "annotation" / "export" / ...
    config: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    retry_max: int = 0
    timeout_seconds: int = 60

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "node_type": self.node_type,
            "config": self.config,
            "depends_on": list(self.depends_on),
            "retry_max": self.retry_max,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class WorkflowSpec:
    id: str
    name: str
    description: str = ""
    nodes: List[NodeSpec] = field(default_factory=list)
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    owner: str = "system"
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nodes": [n.to_dict() for n in self.nodes],
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "owner": self.owner,
            "tags": list(self.tags),
            "node_count": len(self.nodes),
        }


@dataclass
class NodeRunState:
    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    attempt: int = 0
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    output: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "status": self.status.value,
            "attempt": self.attempt,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "output": self.output,
        }


@dataclass
class WorkflowRun:
    run_id: str
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    started_at: str = ""
    finished_at: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    nodes: Dict[str, NodeRunState] = field(default_factory=dict)
    log: List[str] = field(default_factory=list)
    trigger: str = "manual"  # "manual" / "schedule" / "event" / "api"
    cancel_requested: bool = False

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "inputs": self.inputs,
            "nodes": {nid: st.to_dict() for nid, st in self.nodes.items()},
            "log": list(self.log),
            "trigger": self.trigger,
            "cancel_requested": self.cancel_requested,
        }


# =====================================================================
# DAG helpers
# =====================================================================

def topo_sort(nodes: List[NodeSpec]) -> List[List[str]]:
    """Group nodes into topological waves (batches of independent nodes).

    Returns a list of lists - each inner list is one wave that can be
    executed in parallel once all upstream waves complete.
    """
    indeg: Dict[str, int] = {n.id: 0 for n in nodes}
    succ: Dict[str, List[str]] = defaultdict(list)
    by_id: Dict[str, NodeSpec] = {n.id: n for n in nodes}

    for n in nodes:
        for upstream in n.depends_on:
            if upstream not in by_id:
                raise ValueError(f"unknown upstream node: {upstream!r}")
            indeg[n.id] += 1
            succ[upstream].append(n.id)

    # Cycles detection
    visited = 0
    waves: List[List[str]] = []
    ready = [nid for nid, d in indeg.items() if d == 0]
    while ready:
        waves.append(ready)
        next_ready: List[str] = []
        for nid in ready:
            visited += 1
            for child in succ[nid]:
                indeg[child] -= 1
                if indeg[child] == 0:
                    next_ready.append(child)
        ready = next_ready

    if visited != len(nodes):
        raise ValueError("cycle detected in DAG")
    return waves


# =====================================================================
# DAG runtime (singleton)
# =====================================================================

class DAGRuntime:
    """Thread-safe in-memory DAG store + executor."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._workflows: Dict[str, WorkflowSpec] = {}
        self._runs: Dict[str, WorkflowRun] = {}

    # ----- workflow CRUD -----
    def upsert_workflow(self, spec: WorkflowSpec) -> WorkflowSpec:
        with self._lock:
            now = datetime.utcnow().isoformat()
            if not spec.created_at:
                spec.created_at = now
            spec.updated_at = now
            self._workflows[spec.id] = spec
            return spec

    def get_workflow(self, wf_id: str) -> Optional[WorkflowSpec]:
        with self._lock:
            return self._workflows.get(wf_id)

    def list_workflows(self) -> List[WorkflowSpec]:
        with self._lock:
            return list(self._workflows.values())

    def delete_workflow(self, wf_id: str) -> bool:
        with self._lock:
            return self._workflows.pop(wf_id, None) is not None

    # ----- runs -----
    def start_run(self, wf_id: str, inputs: Dict[str, Any],
                  trigger: str = "manual") -> WorkflowRun:
        wf = self.get_workflow(wf_id)
        if wf is None:
            raise KeyError(f"workflow not found: {wf_id}")
        run = WorkflowRun(
            run_id=str(uuid.uuid4()),
            workflow_id=wf_id,
            status=WorkflowStatus.PENDING,
            started_at=datetime.utcnow().isoformat(),
            inputs=inputs,
            trigger=trigger,
        )
        for n in wf.nodes:
            run.nodes[n.id] = NodeRunState(node_id=n.id)
        with self._lock:
            self._runs[run.run_id] = run
        return run

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, workflow_id: Optional[str] = None,
                  limit: int = 50) -> List[WorkflowRun]:
        with self._lock:
            runs = list(self._runs.values())
        if workflow_id:
            runs = [r for r in runs if r.workflow_id == workflow_id]
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[:limit]

    def request_cancel(self, run_id: str) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return False
            run.cancel_requested = True
            return True

    # ----- execution -----
    async def execute(self, run_id: str) -> WorkflowRun:
        """Execute a run in topological waves."""
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        wf = self.get_workflow(run.workflow_id)
        if wf is None:
            raise KeyError(f"workflow missing: {run.workflow_id}")
        run.status = WorkflowStatus.RUNNING
        run.log.append(f"[{datetime.utcnow().isoformat()}] start run")

        try:
            waves = topo_sort(wf.nodes)
        except ValueError as e:
            run.status = WorkflowStatus.FAILED
            run.log.append(f"topo error: {e}")
            run.finished_at = datetime.utcnow().isoformat()
            return run

        any_failed = False
        for wave_idx, wave in enumerate(waves):
            if run.cancel_requested:
                run.log.append("cancel requested")
                break
            tasks = [self._execute_node(run, wf, nid) for nid in wave]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            if any(r == NodeStatus.FAILED for r in results):
                any_failed = True
                # cascade: skip downstream nodes that depend on a failed one
                failed_set = {nid for nid, st in run.nodes.items()
                              if st.status == NodeStatus.FAILED}
                # mark any READY/PENDING node whose upstream failed as SKIPPED
                by_id = {n.id: n for n in wf.nodes}
                for n in wf.nodes:
                    if run.nodes[n.id].status == NodeStatus.PENDING:
                        if any(up in failed_set for up in n.depends_on):
                            run.nodes[n.id].status = NodeStatus.SKIPPED
                            run.log.append(
                                f"[{n.id}] skipped (upstream failed)")
                # don't break: keep running independent branches

        if run.cancel_requested:
            run.status = WorkflowStatus.CANCELLED
        elif any_failed:
            run.status = WorkflowStatus.PARTIAL
        else:
            run.status = WorkflowStatus.SUCCEEDED
        run.finished_at = datetime.utcnow().isoformat()
        run.log.append(f"[{run.finished_at}] run finished: {run.status.value}")
        return run

    async def _execute_node(self, run: WorkflowRun, wf: WorkflowSpec,
                            node_id: str) -> NodeStatus:
        state = run.nodes[node_id]
        node = next(n for n in wf.nodes if n.id == node_id)
        state.status = NodeStatus.RUNNING
        state.started_at = datetime.utcnow().isoformat()
        state.attempt += 1
        run.log.append(f"[{node_id}] starting (attempt {state.attempt})")

        last_err = ""
        for attempt in range(1, max(1, node.retry_max + 2)):
            if run.cancel_requested:
                state.status = NodeStatus.CANCELLED
                state.finished_at = datetime.utcnow().isoformat()
                return state.status
            try:
                # Simulate work - real dispatch would happen here
                await asyncio.sleep(0.05)  # 50 ms stub
                # Inject a deterministic failure if config has _fail=True
                if node.config.get("_fail"):
                    raise RuntimeError(
                        node.config.get("_fail_reason", "stub failure"))
                state.output = {
                    "ok": True,
                    "node_type": node.node_type,
                    "processed": len(run.inputs) if run.inputs else 0,
                }
                state.status = NodeStatus.SUCCEEDED
                state.finished_at = datetime.utcnow().isoformat()
                run.log.append(f"[{node_id}] succeeded (attempt {attempt})")
                return NodeStatus.SUCCEEDED
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                run.log.append(f"[{node_id}] attempt {attempt} failed: {e}")
                state.attempt = attempt
                if attempt > node.retry_max:
                    break
                await asyncio.sleep(0.02)

        state.status = NodeStatus.FAILED
        state.error = last_err
        state.finished_at = datetime.utcnow().isoformat()
        run.log.append(f"[{node_id}] failed after {state.attempt} attempts")
        return NodeStatus.FAILED


# =====================================================================
# Singleton accessor
# =====================================================================

_RUNTIME: Optional[DAGRuntime] = None
_RUNTIME_LOCK = threading.Lock()


def get_dag_runtime() -> DAGRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        with _RUNTIME_LOCK:
            if _RUNTIME is None:
                _RUNTIME = DAGRuntime()
                _seed_demo_workflows(_RUNTIME)
    return _RUNTIME


def _seed_demo_workflows(rt: DAGRuntime) -> None:
    """Seed a handful of demo workflows so the service has visible data
    on first boot (matches the templates in templates.py).
    """
    demo = [
        {
            "id": "wf-demo-image-pipeline",
            "name": "Image Generation Pipeline (demo)",
            "description": "generate -> clean -> score",
            "nodes": [
                {"id": "n1", "name": "generate", "node_type": "generation",
                 "depends_on": []},
                {"id": "n2", "name": "clean", "node_type": "cleaning",
                 "depends_on": ["n1"], "retry_max": 1},
                {"id": "n3", "name": "score", "node_type": "scoring",
                 "depends_on": ["n2"]},
            ],
            "tags": ["image", "demo"],
        },
        {
            "id": "wf-demo-annotation",
            "name": "Annotation Workflow (demo)",
            "description": "prelabel -> annotate -> review",
            "nodes": [
                {"id": "n1", "name": "prelabel", "node_type": "prelabel",
                 "depends_on": []},
                {"id": "n2", "name": "annotate", "node_type": "annotation",
                 "depends_on": ["n1"]},
                {"id": "n3", "name": "review", "node_type": "review",
                 "depends_on": ["n2"]},
            ],
            "tags": ["annotation", "demo"],
        },
    ]
    for d in demo:
        wf = WorkflowSpec(
            id=d["id"], name=d["name"], description=d["description"],
            tags=d["tags"], owner="system",
        )
        for nd in d["nodes"]:
            wf.nodes.append(NodeSpec(**nd))
        rt.upsert_workflow(wf)


__all__ = [
    "DAGRuntime", "NodeSpec", "NodeStatus", "WorkflowRun",
    "WorkflowSpec", "WorkflowStatus", "get_dag_runtime", "topo_sort",
]
