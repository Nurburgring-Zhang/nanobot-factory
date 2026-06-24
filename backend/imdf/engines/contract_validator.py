"""P1-A3-W2: 工作流节点契约校验引擎 (JSON Schema 风格)

职责:
- 节点契约注册 (输入/输出 schema)
- 单节点 input/output 校验
- 工作流整体校验 (节点 + 连线兼容性)

设计:
- 纯内存 registry (无 DB 副作用), 方便测试
- 支持 JSON Schema 子集: type / required / min / max / minLength / maxLength / enum / items / properties
- 类型兼容检查: source output type 与 target input type 是否可连接
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ── 类型映射 ────────────────────────────────────────────────────────────────

_TYPE_MAP: Dict[str, type] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


# ── 核心校验函数 ────────────────────────────────────────────────────────────

def _check_type(value: Any, expected: str) -> Optional[str]:
    """Return None if type matches, else error message."""
    if expected == "any":
        return None
    py_type = _TYPE_MAP.get(expected)
    if py_type is None:
        return None  # unknown type, skip
    # 重要: bool 是 int 子类, 必须先检查
    if expected == "integer" and isinstance(value, bool):
        return f"expected integer, got boolean"
    if not isinstance(value, py_type):
        return f"expected {expected}, got {type(value).__name__}"
    return None


def _validate_field(value: Any, schema: Dict[str, Any], field_path: str = "") -> List[str]:
    """递归校验单个字段值, 返回错误列表."""
    errors: List[str] = []
    path = field_path or "<root>"

    # 1) type
    expected_type = schema.get("type", "any")
    type_err = _check_type(value, expected_type)
    if type_err:
        errors.append(f"{path}: {type_err}")
        return errors  # type 错就不继续, 后续检查无意义

    # 2) 数值约束
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "min" in schema and value < schema["min"]:
            errors.append(f"{path}: value {value} below min {schema['min']}")
        if "max" in schema and value > schema["max"]:
            errors.append(f"{path}: value {value} above max {schema['max']}")

    # 3) 字符串约束
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: string length {len(value)} below minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: string length {len(value)} above maxLength {schema['maxLength']}")
        if "pattern" in schema:
            try:
                if not re.search(schema["pattern"], value):
                    errors.append(f"{path}: value does not match pattern {schema['pattern']}")
            except re.error:
                errors.append(f"{path}: invalid regex pattern {schema['pattern']}")
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: value not in enum {schema['enum']}")

    # 4) 数组约束
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: array length {len(value)} below minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: array length {len(value)} above maxItems {schema['maxItems']}")
        items_schema = schema.get("items")
        if items_schema and isinstance(items_schema, dict):
            for idx, item in enumerate(value):
                errors.extend(_validate_field(item, items_schema, f"{path}[{idx}]"))

    # 5) object 约束
    if isinstance(value, dict):
        required = schema.get("required", [])
        for req_field in required:
            if req_field not in value:
                errors.append(f"{path}: missing required field '{req_field}'")
        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name in value and isinstance(prop_schema, dict):
                errors.extend(_validate_field(value[prop_name], prop_schema, f"{path}.{prop_name}"))

    return errors


def _validate_against_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    """校验 dict 数据是否符合 schema, 返回错误列表."""
    errors: List[str] = []

    if not isinstance(data, dict):
        return [f"data must be dict, got {type(data).__name__}"]

    required = schema.get("required", [])
    properties = schema.get("properties", {})

    # 必填字段
    for req_field in required:
        if req_field not in data:
            errors.append(f"missing required field '{req_field}'")

    # 字段类型校验
    for field_name, field_schema in properties.items():
        if field_name in data and isinstance(field_schema, dict):
            errors.extend(_validate_field(data[field_name], field_schema, field_name))

    return errors


def _types_compatible(source_type: str, target_type: str) -> bool:
    """检查 source_output 类型是否兼容 target_input 类型."""
    if source_type == target_type:
        return True
    if target_type == "any" or source_type == "any":
        return True
    # number 兼容 integer
    if {source_type, target_type} == {"integer", "number"}:
        return True
    # object 与 dict 互转
    if source_type == "object" and target_type == "object":
        return True
    return False


# ── 主类 ────────────────────────────────────────────────────────────────────

class ContractValidator:
    """工作流节点契约校验器.

    用法:
        v = ContractValidator()
        v.register_node("img_gen", inputs_schema={...}, outputs_schema={...})
        ok, err = v.validate_inputs("img_gen", {"prompt": "cat"})
        ok, errs = v.validate_workflow({"nodes": [...], "edges": [...]})
    """

    def __init__(self) -> None:
        # node_id (or node_type) -> {inputs, outputs, description, version}
        self.registry: Dict[str, Dict[str, Any]] = {}

    def register_node(
        self,
        node_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        description: str = "",
        version: str = "1.0.0",
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """注册节点契约.

        支持两种调用:
        1. 显式 inputs + outputs
        2. 整体 schema={"inputs": {...}, "outputs": {...}}
        """
        if schema is not None:
            inputs = schema.get("inputs", {}) or {}
            outputs = schema.get("outputs", {}) or {}
        inputs = inputs or {}
        outputs = outputs or {}

        entry = {
            "node_id": node_id,
            "inputs": inputs,
            "outputs": outputs,
            "description": description,
            "version": version,
        }
        self.registry[node_id] = entry
        return entry

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.registry.get(node_id)

    def list_nodes(self) -> List[str]:
        return sorted(self.registry.keys())

    def validate_inputs(self, node_id: str, inputs: Dict[str, Any]) -> Tuple[bool, str]:
        """校验节点输入. 返回 (ok, message)."""
        entry = self.registry.get(node_id)
        if entry is None:
            return False, f"node '{node_id}' not registered"
        errors = _validate_against_schema(inputs, entry["inputs"])
        if errors:
            return False, "; ".join(errors)
        return True, "ok"

    def validate_outputs(self, node_id: str, outputs: Dict[str, Any]) -> Tuple[bool, str]:
        """校验节点输出. 返回 (ok, message)."""
        entry = self.registry.get(node_id)
        if entry is None:
            return False, f"node '{node_id}' not registered"
        errors = _validate_against_schema(outputs, entry["outputs"])
        if errors:
            return False, "; ".join(errors)
        return True, "ok"

    def validate_workflow(self, workflow: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """校验完整 workflow.

        workflow 格式:
        {
            "nodes": [
                {"id": "n1", "type": "img_gen", "inputs": {...}, "outputs": {...}},
                ...
            ],
            "edges": [
                {"source": "n1", "target": "n2"},
                ...
            ]
        }
        """
        errors: List[str] = []

        nodes = workflow.get("nodes", [])
        edges = workflow.get("edges", [])

        if not isinstance(nodes, list):
            return False, ["workflow.nodes must be list"]
        if not isinstance(edges, list):
            return False, ["workflow.edges must be list"]

        # 1) 节点 ID 唯一性
        node_ids = []
        for node in nodes:
            if not isinstance(node, dict) or "id" not in node:
                errors.append("node missing 'id'")
                continue
            node_ids.append(node["id"])
        if len(set(node_ids)) != len(node_ids):
            errors.append(f"duplicate node ids: {node_ids}")

        # 2) 节点契约校验
        node_map: Dict[str, Dict[str, Any]] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id")
            ntype = node.get("type")
            if nid is None:
                continue
            node_map[nid] = node

            # 若节点声明 inputs, 校验之
            if "inputs" in node and ntype:
                entry = self.registry.get(ntype)
                if entry is None:
                    errors.append(f"node '{nid}': type '{ntype}' not registered")
                else:
                    inp_errs = _validate_against_schema(node["inputs"], entry["inputs"])
                    for e in inp_errs:
                        errors.append(f"node '{nid}' inputs: {e}")

            # 若节点声明 outputs, 校验之
            if "outputs" in node and ntype:
                entry = self.registry.get(ntype)
                if entry is None:
                    pass  # already reported
                else:
                    out_errs = _validate_against_schema(node["outputs"], entry["outputs"])
                    for e in out_errs:
                        errors.append(f"node '{nid}' outputs: {e}")

        # 3) 边兼容性
        for edge in edges:
            if not isinstance(edge, dict):
                errors.append("edge must be dict")
                continue
            src = edge.get("source")
            tgt = edge.get("target")
            if src is None or tgt is None:
                errors.append(f"edge missing source/target: {edge}")
                continue
            if src not in node_map:
                errors.append(f"edge source '{src}' not in nodes")
                continue
            if tgt not in node_map:
                errors.append(f"edge target '{tgt}' not in nodes")
                continue
            src_node = node_map[src]
            tgt_node = node_map[tgt]
            src_type = src_node.get("type")
            tgt_type = tgt_node.get("type")
            if src_type and tgt_type:
                src_entry = self.registry.get(src_type)
                tgt_entry = self.registry.get(tgt_type)
                if src_entry and tgt_entry:
                    # 检查所有 output field 是否与 target 任意 input field 类型兼容
                    src_outputs = src_entry["outputs"].get("properties", {})
                    tgt_inputs = tgt_entry["inputs"].get("properties", {})
                    for out_name, out_schema in src_outputs.items():
                        if out_name in tgt_inputs:
                            src_t = out_schema.get("type", "any")
                            tgt_t = tgt_inputs[out_name].get("type", "any")
                            if not _types_compatible(src_t, tgt_t):
                                errors.append(
                                    f"edge {src}->{tgt}: type mismatch on field '{out_name}': "
                                    f"{src_t} -> {tgt_t}"
                                )

        return (len(errors) == 0), errors


# ── 预置节点模板 ────────────────────────────────────────────────────────────

PRESET_NODES: Dict[str, Dict[str, Any]] = {
    "image_generation": {
        "inputs": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string", "minLength": 1, "maxLength": 4000},
                "negative_prompt": {"type": "string", "maxLength": 4000},
                "width": {"type": "integer", "min": 64, "max": 4096},
                "height": {"type": "integer", "min": 64, "max": 4096},
                "steps": {"type": "integer", "min": 1, "max": 150},
            },
        },
        "outputs": {
            "type": "object",
            "required": ["image"],
            "properties": {
                "image": {"type": "string"},
                "metadata": {"type": "object"},
            },
        },
    },
    "text_classification": {
        "inputs": {
            "type": "object",
            "required": ["text", "labels"],
            "properties": {
                "text": {"type": "string", "maxLength": 10000},
                "labels": {"type": "array", "items": {"type": "string"}},
                "model": {"type": "string"},
            },
        },
        "outputs": {
            "type": "object",
            "required": ["label", "confidence"],
            "properties": {
                "label": {"type": "string"},
                "confidence": {"type": "number", "min": 0.0, "max": 1.0},
            },
        },
    },
    "image_edit": {
        "inputs": {
            "type": "object",
            "required": ["image", "instruction"],
            "properties": {
                "image": {"type": "string"},
                "instruction": {"type": "string", "minLength": 1},
                "strength": {"type": "number", "min": 0.0, "max": 1.0},
            },
        },
        "outputs": {
            "type": "object",
            "required": ["image"],
            "properties": {
                "image": {"type": "string"},
            },
        },
    },
}


def register_preset_nodes(validator: ContractValidator) -> None:
    """将内置节点模板注册到 validator."""
    for node_type, schema in PRESET_NODES.items():
        validator.register_node(node_type, schema=schema)