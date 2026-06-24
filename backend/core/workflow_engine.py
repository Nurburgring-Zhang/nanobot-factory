"""模块化算子与工作流引擎 — DAG编排 + AI/手动模式切换"""

import uuid
import json
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from pydantic import BaseModel
from core.persistent_base import PersistentManager


class ExecMode(str, Enum):
    AI_AUTO = "ai_auto"
    SEMI_AUTO = "semi_auto"
    MANUAL = "manual"


class OperatorCategory(str, Enum):
    SOURCE = "source"
    FILTER = "filter"
    LABEL = "label"
    SCORE = "score"
    SELECT = "select"
    EXPORT = "export"
    EVAL = "eval"


class OperatorDef(BaseModel):
    id: str
    name: str
    category: OperatorCategory
    description: str = ""
    input_type: str = "any"
    output_type: str = "any"
    supports_ai: bool = False
    params_schema: Dict[str, Any] = {}
    default_params: Dict[str, Any] = {}


class WorkflowNode(BaseModel):
    id: str
    operator_id: str
    exec_mode: ExecMode = ExecMode.AI_AUTO
    params: Dict[str, Any] = {}
    x: float = 0
    y: float = 0


class WorkflowEdge(BaseModel):
    source_node: str
    target_node: str


class WorkflowStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class Workflow(BaseModel):
    id: str
    name: str
    description: str = ""
    project_id: str = ""
    nodes: List[WorkflowNode] = []
    edges: List[WorkflowEdge] = []
    status: WorkflowStatus = WorkflowStatus.DRAFT
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


# 预定义算子库
DEFAULT_OPERATORS = [
    OperatorDef(id="source.local_file", name="本地文件采集", category=OperatorCategory.SOURCE, supports_ai=False),
    OperatorDef(id="source.web", name="网页爬虫", category=OperatorCategory.SOURCE, supports_ai=True),
    OperatorDef(id="source.oss", name="OSS采集", category=OperatorCategory.SOURCE, supports_ai=False),
    OperatorDef(id="filter.resolution", name="分辨率过滤", category=OperatorCategory.FILTER),
    OperatorDef(id="filter.blur", name="模糊检测", category=OperatorCategory.FILTER, supports_ai=True),
    OperatorDef(id="filter.nsfw", name="NSFW过滤", category=OperatorCategory.FILTER, supports_ai=True),
    OperatorDef(id="filter.dedup", name="去重(MD5+Phash)", category=OperatorCategory.FILTER, supports_ai=True),
    OperatorDef(id="label.caption", name="图像描述生成", category=OperatorCategory.LABEL, supports_ai=True),
    OperatorDef(id="label.tagging", name="图像标签生成", category=OperatorCategory.LABEL, supports_ai=True),
    OperatorDef(id="label.detection", name="目标检测", category=OperatorCategory.LABEL, supports_ai=True),
    OperatorDef(id="label.classify", name="图像分类", category=OperatorCategory.LABEL, supports_ai=True),
    OperatorDef(id="score.aesthetic", name="美学评分", category=OperatorCategory.SCORE, supports_ai=True),
    OperatorDef(id="score.quality", name="技术质量评分", category=OperatorCategory.SCORE, supports_ai=True),
    OperatorDef(id="score.alignment", name="图文对齐度", category=OperatorCategory.SCORE, supports_ai=True),
    OperatorDef(id="select.threshold", name="阈值筛选", category=OperatorCategory.SELECT),
    OperatorDef(id="select.topk", name="Top-K选取", category=OperatorCategory.SELECT),
    OperatorDef(id="select.stratified", name="分层采样", category=OperatorCategory.SELECT, supports_ai=True),
    OperatorDef(id="export.llava", name="导出LLaVA格式", category=OperatorCategory.EXPORT),
    OperatorDef(id="export.coco", name="导出COCO格式", category=OperatorCategory.EXPORT),
    OperatorDef(id="export.jsonl", name="导出JSONL", category=OperatorCategory.EXPORT),
    OperatorDef(id="eval.fid", name="FID评测", category=OperatorCategory.EVAL, supports_ai=True),
    OperatorDef(id="eval.clip_score", name="CLIP Score", category=OperatorCategory.EVAL, supports_ai=True),
]


class WorkflowEngine(PersistentManager):
    _db_table = "workflows"
    _db_fields = ["id","name","description","project_id","nodes","edges","status","version","created_at","updated_at"]

    def __init__(self):
        self._workflows: Dict[str, Workflow] = {}
        self._operators: Dict[str, OperatorDef] = {op.id: op for op in DEFAULT_OPERATORS}
        self._executors: Dict[str, Callable] = {}
        super().__init__()
        self._load_workflows_from_db()

    def _load_workflows_from_db(self):
        for row in self._load_all():
            if isinstance(row.get("nodes"), list):
                row["nodes"] = [WorkflowNode(**n) if isinstance(n, dict) else n for n in row["nodes"]]
            if isinstance(row.get("edges"), list):
                row["edges"] = [WorkflowEdge(**e) if isinstance(e, dict) else e for e in row["edges"]]
            if isinstance(row.get("status"), str):
                row["status"] = WorkflowStatus(row["status"])
            wf = Workflow(**row)
            self._workflows[wf.id] = wf

    def register_operator(self, op: OperatorDef):
        self._operators[op.id] = op

    def register_executor(self, operator_id: str, executor: Callable):
        self._executors[operator_id] = executor

    def get_operators(self, category: Optional[OperatorCategory] = None) -> List[OperatorDef]:
        if category:
            return [op for op in self._operators.values() if op.category == category]
        return list(self._operators.values())

    def create_workflow(self, name: str, project_id: str = "", description: str = "") -> Workflow:
        wf = Workflow(
            id=f"wf-{uuid.uuid4().hex[:8]}",
            name=name,
            project_id=project_id,
            description=description,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        self._workflows[wf.id] = wf
        self._save(wf.id, wf.model_dump())
        return wf

    def add_node(self, workflow_id: str, operator_id: str, exec_mode: ExecMode = ExecMode.AI_AUTO, params: Dict = None) -> Optional[WorkflowNode]:
        wf = self._workflows.get(workflow_id)
        if not wf or operator_id not in self._operators:
            return None
        # 校验exec_mode是否合法
        valid_modes = {ExecMode.AI_AUTO, ExecMode.SEMI_AUTO, ExecMode.MANUAL}
        if exec_mode not in valid_modes:
            return None
        node = WorkflowNode(
            id=f"n-{uuid.uuid4().hex[:6]}",
            operator_id=operator_id,
            exec_mode=exec_mode,
            params=params or {},
        )
        wf.nodes.append(node)
        wf.updated_at = datetime.now().isoformat()
        self._save(wf.id, wf.model_dump())
        return node

    def add_edge(self, workflow_id: str, source: str, target: str) -> bool:
        wf = self._workflows.get(workflow_id)
        if not wf:
            return False
        nids = {n.id for n in wf.nodes}
        if source not in nids or target not in nids:
            return False
        wf.edges.append(WorkflowEdge(source_node=source, target_node=target))
        wf.updated_at = datetime.now().isoformat()
        self._save(wf.id, wf.model_dump())
        return True

    def get_topological_order(self, workflow_id: str) -> List[str]:
        wf = self._workflows.get(workflow_id)
        if not wf:
            return []
        from collections import deque
        in_degree = {n.id: 0 for n in wf.nodes}
        adj = {n.id: [] for n in wf.nodes}
        for e in wf.edges:
            adj[e.source_node].append(e.target_node)
            in_degree[e.target_node] = in_degree.get(e.target_node, 0) + 1
        q = deque([n for n, d in in_degree.items() if d == 0])
        result = []
        while q:
            n = q.popleft()
            result.append(n)
            for nei in adj[n]:
                in_degree[nei] -= 1
                if in_degree[nei] == 0:
                    q.append(nei)
        # 环检测
        if len(result) < len(wf.nodes):
            raise ValueError("DAG contains cycle")
        return result

    def export_to_json(self, workflow_id: str, filepath: str) -> bool:
        wf = self._workflows.get(workflow_id)
        if not wf:
            return False
        data = {
            "name": wf.name,
            "version": wf.version,
            "nodes": [
                {
                    "id": n.id,
                    "operator": n.operator_id,
                    "mode": n.exec_mode.value,
                    "params": n.params,
                    "x": n.x,
                    "y": n.y,
                }
                for n in wf.nodes
            ],
            "edges": [{"from": e.source_node, "to": e.target_node} for e in wf.edges],
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True

    def import_from_json(self, filepath: str, name: str = "") -> Optional[Workflow]:
        with open(filepath) as f:
            data = json.load(f)
        wf = self.create_workflow(name or data.get("name", "imported"))
        wf.version = data.get("version", 1)
        for nd in data.get("nodes", []):
            node = WorkflowNode(
                id=nd["id"],
                operator_id=nd["operator"],
                exec_mode=ExecMode(nd["mode"]),
                params=nd.get("params", {}),
                x=nd.get("x", 0),
                y=nd.get("y", 0),
            )
            wf.nodes.append(node)
        for ed in data.get("edges", []):
            wf.edges.append(WorkflowEdge(source_node=ed["from"], target_node=ed["to"]))
        wf.updated_at = datetime.now().isoformat()
        self._save(wf.id, wf.model_dump())
        return wf
