"""VDP-2026 R2 — Workflow builder engine.

The engine is intentionally small and focused: it composes capability_v2
invocations into a DAG, runs them in topological order, and emits lifecycle
events. Persistence is via SQLite so workflows can be saved + replayed.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = __import__("logging").getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_DB_PATH: Optional[Path] = None


def configure_db(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _init_db()


def get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        backend_dir = Path(__file__).resolve().parent.parent.parent
        _DB_PATH = backend_dir / "data" / "workflow_builder.db"
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _init_db()
    return _DB_PATH


def _conn() -> sqlite3.Connection:
    p = get_db_path()
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                nodes_json TEXT DEFAULT '[]',
                edges_json TEXT DEFAULT '[]',
                tags_csv TEXT DEFAULT '',
                project_id TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workflow_runs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                status TEXT NOT NULL,
                steps_json TEXT DEFAULT '[]',
                final_outputs_json TEXT DEFAULT '{}',
                started_at TEXT NOT NULL,
                finished_at TEXT DEFAULT '',
                actor TEXT DEFAULT 'system'
            );
            CREATE INDEX IF NOT EXISTS idx_run_workflow ON workflow_runs(workflow_id, started_at DESC);
            """
        )


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowNode:
    id: str
    capability_id: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    position: Dict[str, float] = field(default_factory=dict)
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowEdge:
    source: str
    target: str
    kind: str = "data"  # data | control

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Workflow:
    id: str
    name: str
    description: str = ""
    nodes: List[WorkflowNode] = field(default_factory=list)
    edges: List[WorkflowEdge] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    project_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "tags": self.tags,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        nodes = [
            WorkflowNode(
                id=n["id"],
                capability_id=n["capability_id"],
                inputs=n.get("inputs", {}),
                depends_on=n.get("depends_on", []),
                position=n.get("position", {}),
                label=n.get("label", ""),
            )
            for n in data.get("nodes", [])
        ]
        edges = [
            WorkflowEdge(
                source=e["source"],
                target=e["target"],
                kind=e.get("kind", "data"),
            )
            for e in data.get("edges", [])
        ]
        return cls(
            id=data.get("id") or f"wf_{uuid.uuid4().hex[:10]}",
            name=data.get("name", "未命名工作流"),
            description=data.get("description", ""),
            nodes=nodes,
            edges=edges,
            tags=data.get("tags", []),
            project_id=data.get("project_id", ""),
            created_at=data.get("created_at", "") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at", "") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass
class StepResult:
    node_id: str
    capability_id: str
    status: str
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowRun:
    id: str
    workflow_id: str
    status: str
    steps: List[StepResult] = field(default_factory=list)
    final_outputs: Dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str = ""
    actor: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "final_outputs": self.final_outputs,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "actor": self.actor,
        }


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------


def _topo_sort(workflow: Workflow) -> List[WorkflowNode]:
    """Return nodes in topological order (root-first), or raise ValueError on
    cycle detection.
    """
    incoming: Dict[str, List[str]] = defaultdict(list)
    outgoing: Dict[str, List[str]] = defaultdict(list)
    nodes_by_id: Dict[str, WorkflowNode] = {n.id: n for n in workflow.nodes}
    for e in workflow.edges:
        if e.source not in nodes_by_id or e.target not in nodes_by_id:
            continue
        outgoing[e.source].append(e.target)
        incoming[e.target].append(e.source)

    in_degree: Dict[str, int] = {nid: len(incoming[nid]) for nid in nodes_by_id}
    queue: deque[str] = deque([nid for nid, d in in_degree.items() if d == 0])
    out: List[WorkflowNode] = []
    while queue:
        nid = queue.popleft()
        out.append(nodes_by_id[nid])
        for tgt in outgoing[nid]:
            in_degree[tgt] -= 1
            if in_degree[tgt] == 0:
                queue.append(tgt)
    if len(out) != len(nodes_by_id):
        cyclic = [nid for nid in nodes_by_id if in_degree.get(nid, 0) > 0]
        raise ValueError(f"工作流存在环, 以下节点未被解析: {cyclic}")
    return out


# ---------------------------------------------------------------------------
# Variable substitution: ${node_id.output_key} expanded at run-time.
# Supports both whole-string references ('${n1.x}') and embedded references
# ('prefix-${n1.x}-suffix').
# ---------------------------------------------------------------------------

import re

_VAR_RE = re.compile(r"\$\{([a-zA-Z_][\w\.]*)\}")


def _resolve_ref(path: str, node_outputs: Dict[str, Dict[str, Any]]) -> Any:
    """Walk `node_id.foo.bar` against `node_outputs`. Returns ``None`` if any
    segment is missing — callers compare against the original `${...}` pattern
    to decide whether to substitute.
    """
    parts = path.split(".")
    if not parts:
        return None
    node_id = parts[0]
    ref = node_outputs.get(node_id)
    if not isinstance(ref, dict):
        return None
    cur: Any = ref
    for token in parts[1:]:
        if isinstance(cur, dict):
            cur = cur.get(token)
        else:
            return None
        if cur is None:
            return None
    return cur


def _expand_string(s: str, node_outputs: Dict[str, Dict[str, Any]]) -> Any:
    """Replace every ${...} pattern in a string.

    If no patterns are present, returns the string unchanged.
    If any reference cannot be resolved, the original `${...}` pattern is
    preserved (no partial replacement).
    If the entire string is a single ${...} reference, returns the resolved
    value (which may be a dict / list / number).
    Otherwise returns the string with all references substituted.
    """
    matches = list(_VAR_RE.finditer(s))
    if not matches:
        return s
    if len(matches) == 1 and matches[0].span() == (0, len(s)):
        resolved = _resolve_ref(matches[0].group(1), node_outputs)
        if resolved is None:
            return s  # leave unresolved pattern as-is
        return resolved
    # multi-reference case — string substitution
    out = s
    for m in matches:
        resolved = _resolve_ref(m.group(1), node_outputs)
        if resolved is None:
            # leave unresolved pattern untouched
            continue
        if isinstance(resolved, (dict, list)):
            resolved = json.dumps(resolved, ensure_ascii=False)
        out = out.replace(m.group(0), str(resolved))
    return out


def _expand_inputs(inputs: Any, node_outputs: Dict[str, Dict[str, Any]]) -> Any:
    if isinstance(inputs, dict):
        return {k: _expand_inputs(v, node_outputs) for k, v in inputs.items()}
    if isinstance(inputs, list):
        return [_expand_inputs(v, node_outputs) for v in inputs]
    if isinstance(inputs, str):
        return _expand_string(inputs, node_outputs)
    return inputs


# ---------------------------------------------------------------------------
# Workflow engine
# ---------------------------------------------------------------------------


class WorkflowEngine:
    """In-process + SQLite-backed workflow runner.

    Persisting workflows lets users save a visual composition and reload it
    later as a starting point for a new project.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ---- persistence -------------------------------------------------
    def save_workflow(self, wf: Workflow) -> Workflow:
        with self._lock:
            wf.updated_at = datetime.now(timezone.utc).isoformat()
            with _conn() as conn:
                conn.execute(
                    """
                    INSERT INTO workflows (id, name, description, nodes_json, edges_json, tags_csv, project_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        description=excluded.description,
                        nodes_json=excluded.nodes_json,
                        edges_json=excluded.edges_json,
                        tags_csv=excluded.tags_csv,
                        project_id=excluded.project_id,
                        updated_at=excluded.updated_at
                    """,
                    (
                        wf.id,
                        wf.name,
                        wf.description,
                        json.dumps([n.to_dict() for n in wf.nodes], ensure_ascii=False),
                        json.dumps([e.to_dict() for e in wf.edges], ensure_ascii=False),
                        ",".join(wf.tags),
                        wf.project_id,
                        wf.created_at,
                        wf.updated_at,
                    ),
                )
            return wf

    def get_workflow(self, wf_id: str) -> Optional[Workflow]:
        with _conn() as conn:
            row = conn.execute(
                "SELECT * FROM workflows WHERE id = ?", (wf_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        nodes = [WorkflowNode(**n) for n in json.loads(d.get("nodes_json") or "[]")]
        edges = [WorkflowEdge(**e) for e in json.loads(d.get("edges_json") or "[]")]
        return Workflow(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            nodes=nodes,
            edges=edges,
            tags=[t for t in (d.get("tags_csv") or "").split(",") if t],
            project_id=d.get("project_id", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )

    def list_workflows(self, project_id: Optional[str] = None, limit: int = 200) -> List[Workflow]:
        sql = "SELECT * FROM workflows"
        args: List[Any] = []
        if project_id:
            sql += " WHERE project_id = ?"
            args.append(project_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(limit)
        with _conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        out: List[Workflow] = []
        for row in rows:
            d = dict(row)
            nodes = [WorkflowNode(**n) for n in json.loads(d.get("nodes_json") or "[]")]
            edges = [WorkflowEdge(**e) for e in json.loads(d.get("edges_json") or "[]")]
            out.append(
                Workflow(
                    id=d["id"],
                    name=d["name"],
                    description=d.get("description", ""),
                    nodes=nodes,
                    edges=edges,
                    tags=[t for t in (d.get("tags_csv") or "").split(",") if t],
                    project_id=d.get("project_id", ""),
                    created_at=d.get("created_at", ""),
                    updated_at=d.get("updated_at", ""),
                )
            )
        return out

    def delete_workflow(self, wf_id: str) -> bool:
        with _conn() as conn:
            cur = conn.execute("DELETE FROM workflows WHERE id = ?", (wf_id,))
            return (cur.rowcount or 0) > 0

    # ---- run persistence --------------------------------------------
    def save_run(self, run: WorkflowRun) -> None:
        with _conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workflow_runs
                (id, workflow_id, status, steps_json, final_outputs_json, started_at, finished_at, actor)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.workflow_id,
                    run.status,
                    json.dumps([s.to_dict() for s in run.steps], ensure_ascii=False),
                    json.dumps(run.final_outputs, ensure_ascii=False, default=str),
                    run.started_at,
                    run.finished_at,
                    run.actor,
                ),
            )

    def list_runs(self, workflow_id: Optional[str] = None, limit: int = 50) -> List[WorkflowRun]:
        sql = "SELECT * FROM workflow_runs"
        args: List[Any] = []
        if workflow_id:
            sql += " WHERE workflow_id = ?"
            args.append(workflow_id)
        sql += " ORDER BY started_at DESC LIMIT ?"
        args.append(limit)
        with _conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        out: List[WorkflowRun] = []
        for row in rows:
            d = dict(row)
            steps = [StepResult(**s) for s in json.loads(d.get("steps_json") or "[]")]
            out.append(
                WorkflowRun(
                    id=d["id"],
                    workflow_id=d["workflow_id"],
                    status=d["status"],
                    steps=steps,
                    final_outputs=json.loads(d.get("final_outputs_json") or "{}"),
                    started_at=d.get("started_at", ""),
                    finished_at=d.get("finished_at", ""),
                    actor=d.get("actor", "system"),
                )
            )
        return out

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        runs = self.list_runs(limit=1000)
        for r in runs:
            if r.id == run_id:
                return r
        return None

    # ---- run ---------------------------------------------------------
    def run_workflow(
        self,
        workflow: Workflow,
        actor: str = "system",
        refs: Optional[Dict[str, str]] = None,
    ) -> WorkflowRun:
        """Walk the workflow in topological order, invoking each capability."""
        from capabilities_v2.engine import get_registry  # local import to avoid cycle

        order = _topo_sort(workflow)

        run = WorkflowRun(
            id=f"wfrun_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow.id,
            status=RunStatus.RUNNING.value,
            actor=actor,
        )
        self.save_run(run)

        node_outputs: Dict[str, Dict[str, Any]] = {}
        registry = get_registry()

        any_failed = False
        final: Dict[str, Any] = {}

        for idx, node in enumerate(order):
            step = StepResult(
                node_id=node.id,
                capability_id=node.capability_id,
                status=StepStatus.RUNNING.value,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            started = time.perf_counter()
            try:
                cap = registry.get(node.capability_id)
                if cap is None:
                    raise ValueError(f"未知能力: {node.capability_id}")

                # expand ${refs} against prior node outputs
                expanded_inputs = _expand_inputs(node.inputs or {}, node_outputs)

                # for convenience: auto-propagate prior outputs to fields
                # named after their capability verb (e.g. 'project_id' created
                # upstream gets fed downstream if the field is empty/missing)
                for prior_id, prior_out in node_outputs.items():
                    if not isinstance(prior_out, dict):
                        continue
                    for k, v in prior_out.items():
                        # do not overwrite user-supplied inputs
                        expanded_inputs.setdefault(k, v)

                result = registry.invoke(
                    node.capability_id,
                    expanded_inputs,
                    actor=actor,
                    refs=refs or {},
                )
                duration_ms = int((time.perf_counter() - started) * 1000)
                step.outputs = dict(result.outputs)
                step.duration_ms = duration_ms
                step.finished_at = datetime.now(timezone.utc).isoformat()
                if result.status == "success":
                    step.status = StepStatus.SUCCEEDED.value
                    node_outputs[node.id] = dict(result.outputs)
                    final = node_outputs[node.id]
                else:
                    step.status = StepStatus.FAILED.value
                    step.error = result.error
                    any_failed = True
                    run.steps.append(step)
                    self.save_run(run)
                    break
            except Exception as e:  # noqa: BLE001
                step.status = StepStatus.FAILED.value
                step.error = f"{type(e).__name__}: {e}"
                step.duration_ms = int((time.perf_counter() - started) * 1000)
                step.finished_at = datetime.now(timezone.utc).isoformat()
                any_failed = True
            run.steps.append(step)
            self.save_run(run)

        run.final_outputs = final
        run.finished_at = datetime.now(timezone.utc).isoformat()
        run.status = RunStatus.FAILED.value if any_failed else RunStatus.SUCCEEDED.value
        self.save_run(run)
        return run


# ---------------------------------------------------------------------------
# Starter templates — six production-grade flows composed of capability_v2 calls.
# ---------------------------------------------------------------------------


def build_starter_templates() -> List[Workflow]:
    """Return six ready-to-run workflow templates aligned with the canonical
    data-production pipeline.

    Each template uses capability_v2 ids exclusively, so the engine can run
    them with zero additional wiring.
    """
    return [
        # 1) image_annotation_flow
        Workflow(
            id="wf_tpl_image_annotation",
            name="图像标注生产流",
            description="项目→数据集→数据包→标注→提交→审核→质检的标准图像标注流水线。",
            tags=["图像", "标注", "审核", "质检"],
            nodes=[
                WorkflowNode(id="n1", capability_id="project.create", inputs={"name": "图像标注项目"}, position={"x": 0, "y": 0}),
                WorkflowNode(id="n2", capability_id="requirement.create", inputs={"name": "图像目标检测"}, position={"x": 220, "y": 0}),
                WorkflowNode(id="n3", capability_id="dataset.create", inputs={"name": "image-train-v1", "modality": "image"}, position={"x": 440, "y": 0}),
                WorkflowNode(id="n4", capability_id="pack.create_data", inputs={"name": "pack-1"}, position={"x": 660, "y": 0}),
                WorkflowNode(id="n5", capability_id="annotation.submit", inputs={"task_id": "task_demo"}, position={"x": 880, "y": 0}),
                WorkflowNode(id="n6", capability_id="review.decide", inputs={"review_id": "rev_demo", "decision": "approve"}, position={"x": 1100, "y": 0}),
                WorkflowNode(id="n7", capability_id="qc.full", inputs={"dataset_id": "ds_demo", "total": 1000}, position={"x": 1320, "y": 0}),
            ],
            edges=[
                WorkflowEdge("n1", "n2"),
                WorkflowEdge("n2", "n3"),
                WorkflowEdge("n3", "n4"),
                WorkflowEdge("n4", "n5"),
                WorkflowEdge("n5", "n6"),
                WorkflowEdge("n6", "n7"),
            ],
        ),
        # 2) video_review_flow
        Workflow(
            id="wf_tpl_video_review",
            name="视频审查流",
            description="采集→标注→视频评分(美学/技术)→审核质检流。",
            tags=["视频", "评分", "审核"],
            nodes=[
                WorkflowNode(id="v1", capability_id="collection.create_rss", inputs={"name": "rss-yt", "url": "https://example.com/feed.xml"}, position={"x": 0, "y": 0}),
                WorkflowNode(id="v2", capability_id="collection.start_job", inputs={"source_id": "src_demo"}, position={"x": 220, "y": 0}),
                WorkflowNode(id="v3", capability_id="collection.to_dataset", inputs={"job_id": "job_demo", "items_count": 50}, position={"x": 440, "y": 0}),
                WorkflowNode(id="v4", capability_id="pack.create_data", inputs={"name": "video-pack"}, position={"x": 660, "y": 0}),
                WorkflowNode(id="v5", capability_id="scoring.aggregate", inputs={"dataset_id": "ds_video"}, position={"x": 880, "y": 0}),
                WorkflowNode(id="v6", capability_id="review.decide", inputs={"review_id": "rev_v", "decision": "approve"}, position={"x": 1100, "y": 0}),
            ],
            edges=[
                WorkflowEdge("v1", "v2"),
                WorkflowEdge("v2", "v3"),
                WorkflowEdge("v3", "v4"),
                WorkflowEdge("v4", "v5"),
                WorkflowEdge("v5", "v6"),
            ],
        ),
        # 3) dpo_flow
        Workflow(
            id="wf_tpl_dpo_preference",
            name="DPO 偏好对生产流",
            description="为偏好对齐训练生成 chosen/rejected 对的标准流。",
            tags=["DPO", "偏好", "RLHF"],
            nodes=[
                WorkflowNode(id="d1", capability_id="project.create", inputs={"name": "DPO-项目"}, position={"x": 0, "y": 0}),
                WorkflowNode(id="d2", capability_id="requirement.create", inputs={"name": "preference-data", "type": "alignment"}, position={"x": 220, "y": 0}),
                WorkflowNode(id="d3", capability_id="dataset.create", inputs={"name": "ds-dpo", "modality": "text"}, position={"x": 440, "y": 0}),
                WorkflowNode(id="d4", capability_id="annotation.bulk", inputs={"items": [{"id": "i1"}, {"id": "i2"}, {"id": "i3"}]}, position={"x": 660, "y": 0}),
                WorkflowNode(id="d5", capability_id="tagging.bulk", inputs={"items": [{"id": "i1"}]}, position={"x": 880, "y": 0}),
                WorkflowNode(id="d6", capability_id="qc.aql", inputs={"dataset_id": "ds-dpo", "lot_size": 500, "aql_level": 1.0}, position={"x": 1100, "y": 0}),
                WorkflowNode(id="d7", capability_id="acceptance.submit", inputs={"acceptance_id": "acc-dpo", "decision": "accept"}, position={"x": 1320, "y": 0}),
            ],
            edges=[
                WorkflowEdge("d1", "d2"),
                WorkflowEdge("d2", "d3"),
                WorkflowEdge("d3", "d4"),
                WorkflowEdge("d4", "d5"),
                WorkflowEdge("d5", "d6"),
                WorkflowEdge("d6", "d7"),
            ],
        ),
        # 4) drama_production_flow
        Workflow(
            id="wf_tpl_drama_production",
            name="短剧分镜制作流",
            description="短剧题材 → 数据集(分镜) → 标注 → 多模态导出。",
            tags=["短剧", "分镜", "多模态"],
            nodes=[
                WorkflowNode(id="p1", capability_id="project.create", inputs={"name": "短剧-X"}, position={"x": 0, "y": 0}),
                WorkflowNode(id="p2", capability_id="dataset.create", inputs={"name": "ds-storyboard", "modality": "multimodal"}, position={"x": 220, "y": 0}),
                WorkflowNode(id="p3", capability_id="annotation.pull", inputs={"annotator": "alice"}, position={"x": 440, "y": 0}),
                WorkflowNode(id="p4", capability_id="annotation.submit", inputs={"task_id": "task_p"}, position={"x": 660, "y": 0}),
                WorkflowNode(id="p5", capability_id="export.internvl", inputs={"dataset_id": "ds-storyboard"}, position={"x": 880, "y": 0}),
            ],
            edges=[
                WorkflowEdge("p1", "p2"),
                WorkflowEdge("p2", "p3"),
                WorkflowEdge("p3", "p4"),
                WorkflowEdge("p4", "p5"),
            ],
        ),
        # 5) model_evaluation_flow
        Workflow(
            id="wf_tpl_model_evaluation",
            name="模型评测流",
            description="评测一个模型在某数据集上的能力,产出 accuracy / f1 / bleu。",
            tags=["模型", "评测"],
            nodes=[
                WorkflowNode(id="e1", capability_id="dataset.create", inputs={"name": "ds-eval", "modality": "text"}, position={"x": 0, "y": 0}),
                WorkflowNode(id="e2", capability_id="evaluation.run", inputs={"model": "default", "dataset_id": "ds-eval"}, position={"x": 220, "y": 0}),
                WorkflowNode(id="e3", capability_id="scoring.aggregate", inputs={"dataset_id": "ds-eval"}, position={"x": 440, "y": 0}),
                WorkflowNode(id="e4", capability_id="export.llava", inputs={"dataset_id": "ds-eval"}, position={"x": 660, "y": 0}),
            ],
            edges=[
                WorkflowEdge("e1", "e2"),
                WorkflowEdge("e2", "e3"),
                WorkflowEdge("e3", "e4"),
            ],
        ),
        # 6) ai_annotation_pipeline
        Workflow(
            id="wf_tpl_ai_annotation",
            name="AI 预标注 + 人审流",
            description="AI 预标注 → 人工审核 → QC → 验收,适合 50%+ AI 预标覆盖率的产线。",
            tags=["AI 预标", "审核", "QC"],
            nodes=[
                WorkflowNode(id="a1", capability_id="project.create", inputs={"name": "AI预标-项目"}, position={"x": 0, "y": 0}),
                WorkflowNode(id="a2", capability_id="dataset.create", inputs={"name": "ds-ai", "modality": "image"}, position={"x": 220, "y": 0}),
                WorkflowNode(id="a3", capability_id="classification.bulk", inputs={"items": [{"id": "i1"}, {"id": "i2"}], "labels": ["cat", "dog"]}, position={"x": 440, "y": 0}),
                WorkflowNode(id="a4", capability_id="review.start", inputs={"task_id": "task_ai", "mode": "sample"}, position={"x": 660, "y": 0}),
                WorkflowNode(id="a5", capability_id="qc.sample", inputs={"dataset_id": "ds-ai", "total": 200, "sample_rate": 0.1}, position={"x": 880, "y": 0}),
                WorkflowNode(id="a6", capability_id="acceptance.submit", inputs={"acceptance_id": "acc_ai", "decision": "accept"}, position={"x": 1100, "y": 0}),
                WorkflowNode(id="a7", capability_id="delivery.finalize", inputs={"delivery_id": "dlv_ai"}, position={"x": 1320, "y": 0}),
            ],
            edges=[
                WorkflowEdge("a1", "a2"),
                WorkflowEdge("a2", "a3"),
                WorkflowEdge("a3", "a4"),
                WorkflowEdge("a4", "a5"),
                WorkflowEdge("a5", "a6"),
                WorkflowEdge("a6", "a7"),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# Process-wide engine singleton
# ---------------------------------------------------------------------------

_ENGINE: Optional[WorkflowEngine] = None


def get_engine() -> WorkflowEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = WorkflowEngine()
        # Bootstrap starter templates if not already present
        for tpl in build_starter_templates():
            if _ENGINE.get_workflow(tpl.id) is None:
                _ENGINE.save_workflow(tpl)
    return _ENGINE


def reset_engine_for_test() -> None:
    global _ENGINE
    _ENGINE = None
