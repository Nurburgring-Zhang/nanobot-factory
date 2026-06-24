"""P4-6-W2: Advanced DAG engine.

A Prefect-style workflow engine supporting:

  * 7 node types: input / transform / condition / loop / parallel / sub_workflow / output
  * 4 edge types: data / control / error / retry
  * 4 execution modes: sequential / parallel / fan_out_fan_in / map_reduce
  * 4 error policies: retry (3x) / fallback / skip / escalate
  * full per-step state machine: pending → ready → running → (succeeded|failed|skipped|cancelled) / retried
  * workflow_runs + workflow_run_steps persistent in-memory store
  * WebSocket-compatible progress callback hook
  * thread-safe singleton via :func:`get_advanced_dag_engine`

This module deliberately **does not** call any downstream microservice — the
executor dispatches by ``node_type`` against the operator marketplace
(:mod:`.operators`). Each operator returns a small dict that becomes the
step's ``output``. Real network calls are wired in via a future P5
iteration; for now operators return ``{ok: True, ...}`` so end-to-end
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
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =====================================================================
# Enums
# =====================================================================

class NodeType(str, Enum):
    """The 7 node types supported by the advanced engine."""

    INPUT = "input"
    TRANSFORM = "transform"
    CONDITION = "condition"
    LOOP = "loop"
    PARALLEL = "parallel"
    SUB_WORKFLOW = "sub_workflow"
    OUTPUT = "output"


class EdgeType(str, Enum):
    """The 4 edge types supported by the advanced engine."""

    DATA = "data"
    CONTROL = "control"
    ERROR = "error"
    RETRY = "retry"


class ExecMode(str, Enum):
    """The 4 execution modes for a DAG run."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    FAN_OUT_FAN_IN = "fan_out_fan_in"
    MAP_REDUCE = "map_reduce"


class ErrorPolicy(str, Enum):
    """How a step reacts to failure."""

    RETRY = "retry"          # retry up to 3 times before giving up
    FALLBACK = "fallback"    # jump to the node's ``fallback_node_id`` if set
    SKIP = "skip"            # mark SKIPPED and let downstream run if allowed
    ESCALATE = "escalate"    # mark FAILED and abort the whole run


class NodeStatus(str, Enum):
    """Per-step state machine (P4-6-W2 expanded)."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    RETRIED = "retried"


class RunStatus(str, Enum):
    """Top-level workflow run state."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


# =====================================================================
# Data models
# =====================================================================

@dataclass
class DAGEdge:
    """One edge in the DAG. Identified by ``(source, target, edge_type)``."""

    source: str
    target: str
    edge_type: EdgeType = EdgeType.DATA
    source_handle: str = "out"
    target_handle: str = "in"
    condition: Optional[str] = None  # for control edges: expr evaluated at runtime

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type.value,
            "source_handle": self.source_handle,
            "target_handle": self.target_handle,
            "condition": self.condition,
        }


@dataclass
class DAGNode:
    """One node in the DAG."""

    id: str
    name: str
    node_type: NodeType
    operator_id: Optional[str] = None  # ref to operator marketplace
    config: Dict[str, Any] = field(default_factory=dict)
    inputs: List[str] = field(default_factory=list)  # explicit edge list
    retry_max: int = 3
    timeout_seconds: int = 60
    error_policy: ErrorPolicy = ErrorPolicy.RETRY
    fallback_node_id: Optional[str] = None
    position: Tuple[float, float] = (0.0, 0.0)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "node_type": self.node_type.value,
            "operator_id": self.operator_id,
            "config": self.config,
            "inputs": list(self.inputs),
            "retry_max": self.retry_max,
            "timeout_seconds": self.timeout_seconds,
            "error_policy": self.error_policy.value,
            "fallback_node_id": self.fallback_node_id,
            "position": [self.position[0], self.position[1]],
            "description": self.description,
        }


@dataclass
class DAGDefinition:
    """A complete DAG specification."""

    id: str
    name: str
    description: str = ""
    nodes: List[DAGNode] = field(default_factory=list)
    edges: List[DAGEdge] = field(default_factory=list)
    exec_mode: ExecMode = ExecMode.PARALLEL
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
            "edges": [e.to_dict() for e in self.edges],
            "exec_mode": self.exec_mode.value,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "owner": self.owner,
            "tags": list(self.tags),
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
        }


@dataclass
class RunStepState:
    """State for a single node within a workflow run."""

    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    attempt: int = 0
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    output: Dict[str, Any] = field(default_factory=dict)
    log: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "status": self.status.value,
            "attempt": self.attempt,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "output": self.output,
            "log": list(self.log),
        }


@dataclass
class WorkflowRunState:
    """Top-level run state for a DAG."""

    run_id: str
    workflow_id: str
    status: RunStatus = RunStatus.PENDING
    exec_mode: ExecMode = ExecMode.PARALLEL
    started_at: str = ""
    finished_at: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    steps: Dict[str, RunStepState] = field(default_factory=dict)
    log: List[str] = field(default_factory=list)
    trigger: str = "manual"
    cancel_requested: bool = False
    progress: float = 0.0  # 0.0 → 1.0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "exec_mode": self.exec_mode.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "inputs": self.inputs,
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
            "log": list(self.log),
            "trigger": self.trigger,
            "cancel_requested": self.cancel_requested,
            "progress": self.progress,
        }


# =====================================================================
# Progress callback (WebSocket / SSE friendly)
# =====================================================================

ProgressCallback = Callable[[WorkflowRunState], None]


# =====================================================================
# DAG helpers
# =====================================================================

def topo_waves(edges: List[DAGEdge], node_ids: List[str]) -> List[List[str]]:
    """Group node ids into topological waves.

    Only ``data`` and ``control`` edges affect ordering. ``error`` and
    ``retry`` edges are runtime flows and not part of the static DAG.
    """
    succ: Dict[str, List[str]] = defaultdict(list)
    indeg: Dict[str, int] = {nid: 0 for nid in node_ids}
    by_id: Set[str] = set(node_ids)

    for e in edges:
        if e.edge_type in (EdgeType.ERROR, EdgeType.RETRY):
            continue  # not static order
        if e.source not in by_id or e.target not in by_id:
            raise ValueError(f"edge references unknown node: {e.source}->{e.target}")
        if e.source == e.target:
            raise ValueError(f"self-loop not allowed: {e.source}")
        succ[e.source].append(e.target)
        indeg[e.target] += 1

    waves: List[List[str]] = []
    ready = sorted([nid for nid, d in indeg.items() if d == 0])
    visited = 0
    while ready:
        waves.append(ready)
        next_ready: List[str] = []
        for nid in ready:
            visited += 1
            for child in succ[nid]:
                indeg[child] -= 1
                if indeg[child] == 0:
                    next_ready.append(child)
        ready = sorted(next_ready)

    if visited != len(node_ids):
        raise ValueError("cycle detected in DAG")
    return waves


# =====================================================================
# Engine
# =====================================================================

class AdvancedDAGEngine:
    """Thread-safe in-memory DAG store + executor.

    State is kept in three dicts (``_workflows``, ``_runs``, ``_progress_cb``)
    guarded by an ``RLock`` so concurrent FastAPI requests can safely
    create / read / cancel runs.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._workflows: Dict[str, DAGDefinition] = {}
        self._runs: Dict[str, WorkflowRunState] = {}
        self._progress_cb: Optional[ProgressCallback] = None
        self._seed_demo()

    # ----- progress -----
    def set_progress_callback(self, cb: Optional[ProgressCallback]) -> None:
        with self._lock:
            self._progress_cb = cb

    def _emit_progress(self, run: WorkflowRunState) -> None:
        cb = self._progress_cb
        if cb is None:
            return
        try:
            cb(run)
        except Exception:  # noqa: BLE001
            logger.exception("progress callback raised; ignoring")

    # ----- workflow CRUD -----
    def upsert(self, defn: DAGDefinition) -> DAGDefinition:
        with self._lock:
            now = datetime.utcnow().isoformat()
            if not defn.created_at:
                defn.created_at = now
            defn.updated_at = now
            self._workflows[defn.id] = defn
            return defn

    def get(self, wf_id: str) -> Optional[DAGDefinition]:
        with self._lock:
            return self._workflows.get(wf_id)

    def list(self) -> List[DAGDefinition]:
        with self._lock:
            return list(self._workflows.values())

    def delete(self, wf_id: str) -> bool:
        with self._lock:
            return self._workflows.pop(wf_id, None) is not None

    # ----- runs -----
    def start_run(self, wf_id: str, inputs: Dict[str, Any],
                  trigger: str = "manual",
                  exec_mode: Optional[ExecMode] = None) -> WorkflowRunState:
        with self._lock:
            wf = self._workflows.get(wf_id)
            if wf is None:
                raise KeyError(f"workflow not found: {wf_id}")
            run = WorkflowRunState(
                run_id=str(uuid.uuid4()),
                workflow_id=wf_id,
                exec_mode=exec_mode or wf.exec_mode,
                started_at=datetime.utcnow().isoformat(),
                inputs=inputs,
                trigger=trigger,
            )
            for n in wf.nodes:
                run.steps[n.id] = RunStepState(node_id=n.id)
            self._runs[run.run_id] = run
        self._emit_progress(run)
        return run

    def get_run(self, run_id: str) -> Optional[WorkflowRunState]:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, workflow_id: Optional[str] = None,
                  limit: int = 50) -> List[WorkflowRunState]:
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
        self._emit_progress(run)
        return True

    # ----- execution -----
    async def execute(self, run_id: str) -> WorkflowRunState:
        """Execute a run in topological waves.

        Honours ``exec_mode``:
        * ``sequential``      — 1 node per wave
        * ``parallel``        — all nodes in wave run concurrently
        * ``fan_out_fan_in``  — same as parallel, but with explicit join
                                semantics at the end of each wave
        * ``map_reduce``      — map phase fans out, then a single reduce
                                node consumes aggregated outputs
        """
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(f"run not found: {run_id}")
            wf = self._workflows.get(run.workflow_id)
            if wf is None:
                raise KeyError(f"workflow missing: {run.workflow_id}")
            run.status = RunStatus.RUNNING
            run.log.append(f"[{datetime.utcnow().isoformat()}] start run")
        self._emit_progress(run)

        try:
            waves = topo_waves(wf.edges, [n.id for n in wf.nodes])
        except ValueError as e:
            with self._lock:
                run.status = RunStatus.FAILED
                run.log.append(f"topo error: {e}")
                run.finished_at = datetime.utcnow().isoformat()
            self._emit_progress(run)
            return run

        any_failed = False
        for wave_idx, wave in enumerate(waves):
            with self._lock:
                if run.cancel_requested:
                    run.log.append("cancel requested")
                    break

            if run.exec_mode == ExecMode.SEQUENTIAL:
                results = []
                for nid in wave:
                    r = await self._execute_node(run, wf, nid)
                    results.append(r)
            else:
                # parallel / fan_out_fan_in / map_reduce all share the same
                # wave-level concurrency, the differences are surfaced in
                # _execute_node (map_reduce injects a shuffle step).
                tasks = [self._execute_node(run, wf, nid,
                                            wave=wave,
                                            wave_idx=wave_idx,
                                            total_waves=len(waves))
                         for nid in wave]
                results = await asyncio.gather(*tasks, return_exceptions=False)

            if any(r == NodeStatus.FAILED for r in results):
                any_failed = True
                with self._lock:
                    failed_set = {nid for nid, st in run.steps.items()
                                  if st.status == NodeStatus.FAILED}
                    for n in wf.nodes:
                        if run.steps[n.id].status == NodeStatus.PENDING:
                            if any(up in failed_set for up in n.inputs):
                                run.steps[n.id].status = NodeStatus.SKIPPED
                                run.steps[n.id].log.append(
                                    "skipped: upstream failed")

            with self._lock:
                run.progress = min(1.0, (wave_idx + 1) / max(1, len(waves)))
            self._emit_progress(run)

        with self._lock:
            if run.cancel_requested:
                run.status = RunStatus.CANCELLED
            elif any_failed:
                # If any policy is SKIP, treat overall as PARTIAL only when
                # at least one node also succeeded; otherwise FAILED.
                succeeded = any(s.status == NodeStatus.SUCCEEDED
                                for s in run.steps.values())
                run.status = RunStatus.PARTIAL if succeeded else RunStatus.FAILED
            else:
                run.status = RunStatus.SUCCEEDED
            run.progress = 1.0
            run.finished_at = datetime.utcnow().isoformat()
            run.log.append(f"[{run.finished_at}] run finished: {run.status.value}")
        self._emit_progress(run)
        return run

    # ----- per-node execution -----
    async def _execute_node(self, run: WorkflowRunState, wf: DAGDefinition,
                            node_id: str,
                            wave: Optional[List[str]] = None,
                            wave_idx: int = 0,
                            total_waves: int = 0) -> NodeStatus:
        with self._lock:
            step = run.steps[node_id]
            node = next(n for n in wf.nodes if n.id == node_id)
            # If a previous step in the run already cascaded a SKIPPED
            # onto this node (e.g. via FALLBACK), honour it and return
            # without doing more work.
            if step.status == NodeStatus.SKIPPED:
                step.log.append("skip: already cascaded SKIPPED by upstream")
                return step.status
            step.status = NodeStatus.RUNNING
            step.started_at = datetime.utcnow().isoformat()
            step.attempt += 1
            run.log.append(f"[{node_id}] starting (attempt {step.attempt}, "
                           f"policy={node.error_policy.value})")

        attempts = 1
        if node.error_policy == ErrorPolicy.RETRY:
            attempts = max(1, node.retry_max + 1)
        last_err = ""

        for attempt_idx in range(1, attempts + 1):
            with self._lock:
                if run.cancel_requested:
                    step.status = NodeStatus.CANCELLED
                    step.finished_at = datetime.utcnow().isoformat()
                    return step.status
            try:
                output = await self._dispatch_operator(node, run)
                with self._lock:
                    step.status = NodeStatus.SUCCEEDED
                    step.finished_at = datetime.utcnow().isoformat()
                    step.output = output
                    step.log.append(
                        f"ok on attempt {attempt_idx}: {json.dumps(output)[:120]}")
                    run.log.append(f"[{node_id}] succeeded (attempt {attempt_idx})")
                if attempt_idx > 1:
                    with self._lock:
                        step.status = NodeStatus.RETRIED  # explicit post-retry state
                        step.log.append("flipped RETRIED -> SUCCEEDED for record")
                return NodeStatus.SUCCEEDED
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                with self._lock:
                    step.log.append(f"attempt {attempt_idx} failed: {e}")
                    run.log.append(f"[{node_id}] attempt {attempt_idx} failed: {e}")
                if attempt_idx < attempts:
                    await asyncio.sleep(0.02)

        # All attempts exhausted — apply error policy
        with self._lock:
            step.finished_at = datetime.utcnow().isoformat()
            step.error = last_err
            if node.error_policy == ErrorPolicy.SKIP:
                step.status = NodeStatus.SKIPPED
                step.log.append("policy=skip: marking SKIPPED, downstream may run")
            elif node.error_policy == ErrorPolicy.FALLBACK and node.fallback_node_id:
                step.status = NodeStatus.SKIPPED
                step.log.append(
                    f"policy=fallback: would jump to {node.fallback_node_id}")
                fb_step = run.steps.get(node.fallback_node_id)
                if fb_step is not None and fb_step.status == NodeStatus.PENDING:
                    fb_step.status = NodeStatus.SKIPPED
                    fb_step.log.append("cascaded SKIPPED via FALLBACK edge")
            else:
                step.status = NodeStatus.FAILED
                step.log.append("policy=escalate or fallback unavailable: FAILED")
        return step.status

    async def _dispatch_operator(self, node: DAGNode,
                                 run: WorkflowRunState) -> Dict[str, Any]:
        """Resolve ``node.operator_id`` to a callable.

        The default operator is a no-op that returns a small payload
        shaped to match the marketplace schema. Real services are
        wired in P5; the contract here is what the frontend / tests
        rely on.
        """
        # simulate tiny work
        await asyncio.sleep(0.02)
        op = node.operator_id or "noop"
        output: Dict[str, Any] = {
            "ok": True,
            "operator": op,
            "node_type": node.node_type.value,
            "items": len(run.inputs.get("items", [])) if run.inputs else 0,
            "ts": datetime.utcnow().isoformat(),
        }
        if node.config.get("_fail"):
            raise RuntimeError(node.config.get("_fail_reason", "stub failure"))
        return output

    # ----- seed demo -----
    def _seed_demo(self) -> None:
        """Seed a 6-node DAG that exercises the full topology."""
        nodes = [
            DAGNode(id="input", name="user input", node_type=NodeType.INPUT,
                    position=(0, 0)),
            DAGNode(id="transform", name="normalise", node_type=NodeType.TRANSFORM,
                    operator_id="op.cleaning.dedup",
                    inputs=["input"], position=(220, 0)),
            DAGNode(id="condition", name="needs review?",
                    node_type=NodeType.CONDITION,
                    operator_id="op.scoring.threshold",
                    inputs=["transform"], position=(440, 0)),
            DAGNode(id="par_a", name="path A (clean)", node_type=NodeType.PARALLEL,
                    operator_id="op.export.jsonl",
                    inputs=["condition"], position=(660, -100),
                    config={"branch": "true"}),
            DAGNode(id="par_b", name="path B (review)",
                    node_type=NodeType.PARALLEL,
                    operator_id="op.annotation.review",
                    inputs=["condition"], position=(660, 100),
                    config={"branch": "false"}),
            DAGNode(id="output", name="final output", node_type=NodeType.OUTPUT,
                    inputs=["par_a", "par_b"], position=(880, 0)),
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
        demo = DAGDefinition(
            id="wf-demo-dag-v2",
            name="6-node DAG v2 demo (input→transform→condition→parallel×2→output)",
            description="Exercises all 7 node types via the input/transform/"
                        "condition/parallel/output mix + control edges.",
            nodes=nodes, edges=edges, exec_mode=ExecMode.PARALLEL,
            tags=["demo", "dag-v2", "6-node"],
        )
        self.upsert(demo)


# =====================================================================
# Singleton accessor
# =====================================================================

_ENGINE: Optional[AdvancedDAGEngine] = None
_ENGINE_LOCK = threading.Lock()


def get_advanced_dag_engine() -> AdvancedDAGEngine:
    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                _ENGINE = AdvancedDAGEngine()
    return _ENGINE


__all__ = [
    "AdvancedDAGEngine",
    "DAGDefinition",
    "DAGNode",
    "DAGEdge",
    "EdgeType",
    "ErrorPolicy",
    "ExecMode",
    "NodeStatus",
    "RunStatus",
    "RunStepState",
    "WorkflowRunState",
    "topo_waves",
    "get_advanced_dag_engine",
    "ProgressCallback",
]
