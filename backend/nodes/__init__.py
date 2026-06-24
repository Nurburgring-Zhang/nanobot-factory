"""
节点引擎入口 — NodeRegistry + NodeDefinition + BaseNode + WorkflowEngine

全局节点注册表，类似于 operators_lib.OPERATOR_REGISTRY 的升级方案。
导入此模块即自动注册所有内建节点。

使用方法::

    from nodes import NodeRegistry, WorkflowEngine, registry

    engine = WorkflowEngine()
    nodes = engine.list_nodes()
    result = await engine.execute(workflow_def)
"""
import asyncio
import logging
from collections import deque
from typing import Any, Dict, List, Optional

from .base import (
    BaseNode,
    NodeDefinition,
    NodeParam,
    NodePort,
    WorkflowDefinition,
    WorkflowStep,
)
from .registry import NodeRegistry, registry

logger = logging.getLogger(__name__)


# =============================================================================
# WorkflowEngine
# =============================================================================

class WorkflowEngine:
    """
    节点化工作流执行引擎。

    接收 WorkflowDefinition（DAG 图），通过拓扑排序 + 并行执行可并行节点
    来执行整个工作流。
    """

    def __init__(self):
        self.registry = registry

    # ------------------------------------------------------------------
    # 注册相关
    # ------------------------------------------------------------------

    def register(self, node_cls: type):
        """注册节点类到全局注册表"""
        self.registry.register(node_cls)

    def list_nodes(self) -> List[NodeDefinition]:
        """列出所有受支持的节点定义"""
        return self.registry.list()

    # ------------------------------------------------------------------
    # DAG 执行
    # ------------------------------------------------------------------

    async def execute(
        self,
        workflow: WorkflowDefinition,
        global_inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        执行工作流。

        参数
        ----
        workflow : WorkflowDefinition
            包含 steps 列表的工作流定义。
        global_inputs : dict, optional
            全局输入数据，可通过 step.inputs 中的 ``_global`` 前缀引用。

        返回
        ----
        dict: {step_id: {output_port: value, ...}, ...}
        """
        if not workflow.steps:
            return {"_empty": True}

        global_inputs = global_inputs or {}

        # 1. 校验所有 node_id 是否已注册
        for step in workflow.steps:
            if step.node_id not in self.registry._nodes:
                raise ValueError(
                    f"Step '{step.id}' references unknown node "
                    f"'{step.node_id}'"
                )

        # 2. 构建依赖图 & 输入引用映射
        step_map: Dict[str, WorkflowStep] = {s.id: s for s in workflow.steps}
        # 出边: parent -> children
        out_edges: Dict[str, List[str]] = {s.id: [] for s in workflow.steps}
        # 入度
        in_degree: Dict[str, int] = {s.id: 0 for s in workflow.steps}

        for step in workflow.steps:
            # 检查每个 input 的引用
            for port_name, ref in step.inputs.items():
                if "." in ref and not ref.startswith("_global"):
                    src_step_id = ref.split(".")[0]
                    if src_step_id in step_map:
                        out_edges.setdefault(src_step_id, []).append(step.id)
                        in_degree[step.id] = in_degree.get(step.id, 0) + 1

        # 3. 拓扑排序 (Kahn's algorithm)
        q: deque = deque(
            [sid for sid, deg in in_degree.items() if deg == 0]
        )
        topo_order: List[str] = []
        while q:
            sid = q.popleft()
            topo_order.append(sid)
            for child in out_edges.get(sid, []):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    q.append(child)

        if len(topo_order) < len(workflow.steps):
            raise ValueError(
                "Workflow graph contains a cycle — topological sort "
                f"completed {len(topo_order)}/{len(workflow.steps)} steps"
            )

        # 4. 按拓扑序分组（并行层）
        layer: Dict[str, int] = {sid: 0 for sid in topo_order}
        for sid in topo_order:
            step = step_map[sid]
            for port_name, ref in step.inputs.items():
                if "." in ref and not ref.startswith("_global"):
                    src_id = ref.split(".")[0]
                    if src_id in step_map:
                        layer[sid] = max(layer[sid], layer[src_id] + 1)

        max_layer = max(layer.values()) if layer else 0
        layers: List[List[str]] = [[] for _ in range(max_layer + 1)]
        for sid, l in layer.items():
            layers[l].append(sid)

        # 5. 逐层执行（每层内并行）
        outputs: Dict[str, Dict[str, Any]] = {}

        for layer_steps in layers:
            tasks = []
            for sid in layer_steps:
                tasks.append(self._execute_step(
                    sid, step_map[sid], outputs, global_inputs
                ))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for sid, result in zip(layer_steps, results):
                if isinstance(result, Exception):
                    raise RuntimeError(
                        f"Step '{sid}' failed: {result}"
                    ) from result
                outputs[sid] = result

        return outputs

    async def _execute_step(
        self,
        step_id: str,
        step: WorkflowStep,
        previous_outputs: Dict[str, Dict[str, Any]],
        global_inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """解析输入引用 → 实例化节点 → 执行"""
        # 1. 解析输入
        resolved_inputs: Dict[str, Any] = {}
        for port_name, ref in step.inputs.items():
            if ref.startswith("_global."):
                key = ref[len("_global."):]
                resolved_inputs[port_name] = global_inputs.get(key)
            elif "." in ref:
                src_step, src_port = ref.split(".", 1)
                src_out = previous_outputs.get(src_step, {})
                resolved_inputs[port_name] = src_out.get(src_port)
            else:
                # 直接值 — 可能是 literal
                resolved_inputs[port_name] = ref

        # 2. 获取节点类并执行
        node_cls = self.registry._nodes.get(step.node_id)
        if not node_cls:
            raise ValueError(f"Node '{step.node_id}' not registered")
        node = node_cls()
        try:
            result = await node.execute(resolved_inputs, step.params)
            return result
        except Exception as e:
            logger.exception(
                f"Step '{step_id}' ({step.node_id}) execution error"
            )
            raise


# =============================================================================
# 自动注册所有内建节点（导入即注册）
# =============================================================================

from . import filter_nodes   # noqa: F401
from . import gen_nodes      # noqa: F401
from . import quality_nodes  # noqa: F401
from . import control_nodes  # noqa: F401
from . import export_nodes   # noqa: F401
