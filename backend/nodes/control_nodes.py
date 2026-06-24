"""
控制流节点 — Loop / Condition / Batch / Merge / Split / Sequence

用于在 WorkflowEngine 中实现分支、循环、并行分片等控制逻辑。
"""
import logging
from typing import Any, Dict, List

from .base import BaseNode, NodeDefinition, NodePort, NodeParam
from .registry import registry

logger = logging.getLogger(__name__)


class LoopNode(BaseNode):
    """循环节点：对输入列表中的每个元素重复执行子节点（此处直接循环返回）。"""
    definition = NodeDefinition(
        node_id="control.loop",
        name="循环处理",
        category="control",
        description="对列表中的每个元素执行相同的处理逻辑",
        inputs=[NodePort(name="items", type="any", required=True)],
        outputs=[NodePort(name="results", type="any")],
        params=[
            NodeParam(name="max_iterations", type="int", default=100, min=1),
        ],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            items = inputs.get("items", [])
            if not isinstance(items, list):
                items = [items]
            max_iter = params.get("max_iterations", 100)
            results = items[:max_iter]
            return {"results": results}
        except Exception as e:
            logger.error(f"LoopNode failed: {e}")
            return {"results": []}


class ConditionNode(BaseNode):
    """条件节点：根据条件表达式选择输出路径。"""
    definition = NodeDefinition(
        node_id="control.condition",
        name="条件分支",
        category="control",
        description="根据条件判断选择不同的输出路径",
        inputs=[NodePort(name="value", type="any", required=True)],
        outputs=[
            NodePort(name="true", type="any"),
            NodePort(name="false", type="any"),
        ],
        params=[
            NodeParam(name="operator", type="select", default="gt",
                      options=["gt", "gte", "lt", "lte", "eq", "neq", "is_empty", "is_not_empty"]),
            NodeParam(name="threshold", type="float", default=0.0),
            NodeParam(name="field", type="string", default=""),
        ],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            value = inputs.get("value")
            field = params.get("field", "")
            if field and isinstance(value, dict):
                value = value.get(field, value)

            op = params.get("operator", "gt")
            threshold = params.get("threshold", 0.0)

            if isinstance(value, (int, float)):
                if op == "gt":
                    result = value > threshold
                elif op == "gte":
                    result = value >= threshold
                elif op == "lt":
                    result = value < threshold
                elif op == "lte":
                    result = value <= threshold
                elif op == "eq":
                    result = value == threshold
                elif op == "neq":
                    result = value != threshold
                else:
                    result = bool(value)
            elif op == "is_empty":
                result = value is None or value == "" or value == []
            elif op == "is_not_empty":
                result = value is not None and value != "" and value != []
            else:
                result = bool(value)

            return {
                "true": inputs.get("value") if result else None,
                "false": inputs.get("value") if not result else None,
            }
        except Exception as e:
            logger.error(f"ConditionNode failed: {e}")
            return {"true": None, "false": None}


class BatchNode(BaseNode):
    """批处理节点：将输入列表拆分为多个批次。"""
    definition = NodeDefinition(
        node_id="control.batch",
        name="分批处理",
        category="control",
        description="将列表拆分为指定大小的批次",
        inputs=[NodePort(name="items", type="any", required=True)],
        outputs=[NodePort(name="batches", type="any")],
        params=[
            NodeParam(name="batch_size", type="int", default=8, min=1),
        ],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            items = inputs.get("items", [])
            if not isinstance(items, list):
                items = [items]
            batch_size = params.get("batch_size", 8)
            batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
            return {"batches": batches}
        except Exception as e:
            logger.error(f"BatchNode failed: {e}")
            return {"batches": []}


class MergeNode(BaseNode):
    """合并节点：将多个输入合并为单个列表。"""
    definition = NodeDefinition(
        node_id="control.merge",
        name="合并",
        category="control",
        description="将多个输入源合并为一个列表",
        inputs=[
            NodePort(name="source_1", type="any"),
            NodePort(name="source_2", type="any"),
            NodePort(name="source_3", type="any"),
        ],
        outputs=[NodePort(name="merged", type="any")],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            merged = []
            for key in sorted(inputs.keys()):
                val = inputs[key]
                if val is not None:
                    if isinstance(val, list):
                        merged.extend(val)
                    else:
                        merged.append(val)
            return {"merged": merged}
        except Exception as e:
            logger.error(f"MergeNode failed: {e}")
            return {"merged": []}


class SplitNode(BaseNode):
    """拆分节点：将列表按比例拆分为训练/验证/测试集。"""
    definition = NodeDefinition(
        node_id="control.split",
        name="数据拆分",
        category="control",
        description="按比例拆分数据为训练/验证/测试集",
        inputs=[NodePort(name="items", type="any", required=True)],
        outputs=[
            NodePort(name="train", type="any"),
            NodePort(name="validation", type="any"),
            NodePort(name="test", type="any"),
        ],
        params=[
            NodeParam(name="train_ratio", type="float", default=0.7, min=0, max=1),
            NodeParam(name="val_ratio", type="float", default=0.15, min=0, max=1),
        ],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            items = inputs.get("items", [])
            if not isinstance(items, list):
                items = [items]
            n = len(items)
            if n == 0:
                return {"train": [], "validation": [], "test": []}

            train_r = params.get("train_ratio", 0.7)
            val_r = params.get("val_ratio", 0.15)
            test_r = max(0, 1.0 - train_r - val_r)

            train_n = max(1, int(n * train_r))
            val_n = max(0, int(n * val_r))

            train = items[:train_n]
            val = items[train_n:train_n + val_n]
            test = items[train_n + val_n:]

            return {"train": train, "validation": val, "test": test}
        except Exception as e:
            logger.error(f"SplitNode failed: {e}")
            return {"train": [], "validation": [], "test": []}


class SequenceNode(BaseNode):
    """序列节点：确保子步骤按顺序执行（占位/透传）。"""
    definition = NodeDefinition(
        node_id="control.sequence",
        name="顺序执行",
        category="control",
        description="保证下游步骤在前序步骤完成后依次执行",
        inputs=[NodePort(name="input", type="any")],
        outputs=[NodePort(name="output", type="any")],
        params=[],
    )

    async def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        return {"output": inputs.get("input")}


# ---- 注册 ----
registry.register(LoopNode)
registry.register(ConditionNode)
registry.register(BatchNode)
registry.register(MergeNode)
registry.register(SplitNode)
registry.register(SequenceNode)
