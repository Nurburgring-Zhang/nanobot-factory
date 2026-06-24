"""P1-A3-W2: 工作流节点契约校验 API (使用 ContractValidator 引擎)

端点 (均为 P1-A3 新增, 不与现有 workflow_contract_routes.py 冲突):
- POST /api/v1/workflow/contract/nodes           — 注册节点契约
- GET  /api/v1/workflow/contract/nodes/{id}      — 获取契约
- POST /api/v1/workflow/contract/validate        — 校验 workflow
- GET  /api/v1/workflow/contract/list            — 列出已注册节点

注意: 这个文件提供的是任务 P1-A3-W2 新设计的契约校验 API, 与既有的
api/workflow_contract_routes.py (基于 SQLite 持久化) 并存. 两个 router
均可在 canvas_web 中独立 include_router; 路径前缀都是 /api/v1/workflow/contract
但 endpoint path 不同 (本文件是 /nodes, 既有是 /define, /templates 等),
不会冲突.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel, Field, field_validator

from engines.contract_validator import (
    ContractValidator,
    register_preset_nodes,
    PRESET_NODES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow/contract", tags=["workflow_contract_v2"])

# 单例 validator (进程内共享, 与既有 routes 的 SQLite 存储隔离)
_validator = ContractValidator()
register_preset_nodes(_validator)


# ── Pydantic models ────────────────────────────────────────────────────────

class RegisterNodeRequest(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=128, description="节点 ID (唯一)")
    inputs: Optional[Dict[str, Any]] = Field(default=None, description="输入 schema (JSON Schema 子集)")
    outputs: Optional[Dict[str, Any]] = Field(default=None, description="输出 schema")
    description: str = Field(default="", max_length=512)
    version: str = Field(default="1.0.0", max_length=32)

    @field_validator("node_id")
    @classmethod
    def _check_node_id(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("node_id 只能包含字母/数字/下划线/连字符")
        return v


class ValidateWorkflowRequest(BaseModel):
    nodes: List[Dict[str, Any]] = Field(..., min_length=1, description="节点列表, 每项 {id, type, inputs?, outputs?}")
    edges: List[Dict[str, Any]] = Field(default_factory=list, description="边列表, 每项 {source, target}")


class ValidateInputsRequest(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=128)
    inputs: Dict[str, Any] = Field(..., description="待校验的输入数据")


class ValidateOutputsRequest(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=128)
    outputs: Dict[str, Any] = Field(..., description="待校验的输出数据")


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/nodes", status_code=201)
async def register_node(req: RegisterNodeRequest):
    """注册一个节点契约."""
    if req.inputs is None and req.outputs is None:
        raise HTTPException(status_code=422, detail="inputs 或 outputs 至少提供一个")
    entry = _validator.register_node(
        node_id=req.node_id,
        inputs=req.inputs,
        outputs=req.outputs,
        description=req.description,
        version=req.version,
    )
    logger.info(f"Node contract registered: {req.node_id}")
    return {
        "ok": True,
        "data": {
            "node_id": entry["node_id"],
            "inputs": entry["inputs"],
            "outputs": entry["outputs"],
            "description": entry["description"],
            "version": entry["version"],
        },
    }


@router.get("/nodes/{node_id}")
async def get_node(node_id: str):
    """获取已注册的节点契约."""
    entry = _validator.get_node(node_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"node '{node_id}' not registered")
    return {
        "ok": True,
        "data": {
            "node_id": entry["node_id"],
            "inputs": entry["inputs"],
            "outputs": entry["outputs"],
            "description": entry["description"],
            "version": entry["version"],
        },
    }


@router.get("/list")
async def list_nodes():
    """列出所有已注册的节点契约."""
    nodes = _validator.list_nodes()
    items = []
    for nid in nodes:
        entry = _validator.get_node(nid)
        items.append({
            "node_id": entry["node_id"],
            "description": entry["description"],
            "version": entry["version"],
            "input_fields": list(entry["inputs"].get("properties", {}).keys()),
            "output_fields": list(entry["outputs"].get("properties", {}).keys()),
        })
    return {"ok": True, "data": {"nodes": items, "total": len(items)}}


@router.post("/validate")
async def validate_workflow(req: ValidateWorkflowRequest):
    """校验完整 workflow (节点 + 连线兼容性)."""
    workflow = {"nodes": req.nodes, "edges": req.edges}
    ok, errors = _validator.validate_workflow(workflow)
    return {
        "ok": ok,
        "data": {
            "valid": ok,
            "errors": errors,
            "node_count": len(req.nodes),
            "edge_count": len(req.edges),
        },
    }


@router.post("/validate-inputs")
async def validate_inputs_endpoint(req: ValidateInputsRequest):
    """校验节点输入数据."""
    ok, message = _validator.validate_inputs(req.node_id, req.inputs)
    if not ok and "not registered" in message:
        raise HTTPException(status_code=404, detail=message)
    return {
        "ok": ok,
        "data": {
            "valid": ok,
            "node_id": req.node_id,
            "message": message,
        },
    }


@router.post("/validate-outputs")
async def validate_outputs_endpoint(req: ValidateOutputsRequest):
    """校验节点输出数据."""
    ok, message = _validator.validate_outputs(req.node_id, req.outputs)
    if not ok and "not registered" in message:
        raise HTTPException(status_code=404, detail=message)
    return {
        "ok": ok,
        "data": {
            "valid": ok,
            "node_id": req.node_id,
            "message": message,
        },
    }


@router.get("/presets")
async def list_presets():
    """列出预置节点模板 (无需注册)."""
    return {
        "ok": True,
        "data": {
            "presets": [
                {"node_type": k, "inputs": v["inputs"], "outputs": v["outputs"]}
                for k, v in PRESET_NODES.items()
            ],
            "total": len(PRESET_NODES),
        },
    }