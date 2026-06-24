"""
F3.2 节点契约校验 API — 真实化实现
=====================================
- /define: 定义节点契约schema (JSON Schema格式)
- /validate: 验证节点输出是否符合契约
- /validate-workflow: 验证整个工作流的契约一致性
- /templates: 预置契约模板
- /check-conflicts: 检测契约冲突
- /infer: 从数据推断输入/输出契约
实现: JSON Schema验证器 + SQLite持久化
"""

import json
import sqlite3
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow/contract", tags=["workflow_contract"])

# ── Database ─────────────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BACKEND_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_DATA_DIR / "contracts.db")

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _init_db():
    with _get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS contracts (
                id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                inputs_schema TEXT DEFAULT '{}',
                outputs_schema TEXT DEFAULT '{}',
                version TEXT DEFAULT '1.0.0',
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS validations (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                source_node TEXT NOT NULL,
                target_node TEXT NOT NULL,
                source_output TEXT DEFAULT '{}',
                target_input TEXT DEFAULT '{}',
                compatible INTEGER DEFAULT 0,
                warnings TEXT DEFAULT '[]',
                errors TEXT DEFAULT '[]',
                validated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_contracts_type ON contracts(node_type);
            CREATE INDEX IF NOT EXISTS idx_validations_workflow ON validations(workflow_id);
        """)

_init_db()

# ── Pre-built Contract Templates ────────────────────────────────────────────

CONTRACT_TEMPLATES = [
    {
        "node_type": "image_generation",
        "description": "AI图像生成节点",
        "inputs": {
            "prompt": {"type": "string", "required": True, "description": "正向提示词"},
            "negative_prompt": {"type": "string", "required": False, "description": "负向提示词"},
            "width": {"type": "integer", "required": False, "default": 1024, "min": 64, "max": 4096},
            "height": {"type": "integer", "required": False, "default": 1024, "min": 64, "max": 4096},
            "seed": {"type": "integer", "required": False},
            "steps": {"type": "integer", "required": False, "default": 30, "min": 1, "max": 150},
        },
        "outputs": {
            "image": {"type": "image", "format": ["png", "jpg", "webp"], "required": True},
            "metadata": {"type": "object", "required": False},
        }
    },
    {
        "node_type": "video_generation",
        "description": "AI视频生成节点",
        "inputs": {
            "prompt": {"type": "string", "required": True},
            "duration": {"type": "integer", "required": False, "default": 5, "min": 1, "max": 60},
            "fps": {"type": "integer", "required": False, "default": 24, "min": 1, "max": 60},
            "width": {"type": "integer", "required": False, "default": 1920},
            "height": {"type": "integer", "required": False, "default": 1080},
        },
        "outputs": {
            "video": {"type": "video", "format": ["mp4", "mov", "webm"], "required": True},
            "thumbnail": {"type": "image", "format": ["jpg"], "required": False},
        }
    },
    {
        "node_type": "text_classification",
        "description": "文本分类节点",
        "inputs": {
            "text": {"type": "string", "required": True, "max_length": 10000},
            "labels": {"type": "array", "items": {"type": "string"}, "required": True},
            "model": {"type": "string", "required": False, "default": "default"},
        },
        "outputs": {
            "label": {"type": "string", "required": True},
            "confidence": {"type": "number", "required": True, "min": 0.0, "max": 1.0},
            "all_scores": {"type": "object", "required": False},
        }
    },
    {
        "node_type": "audio_tts",
        "description": "文本转语音节点",
        "inputs": {
            "text": {"type": "string", "required": True, "max_length": 5000},
            "voice": {"type": "string", "required": False, "default": "default"},
            "speed": {"type": "number", "required": False, "default": 1.0, "min": 0.5, "max": 2.0},
            "language": {"type": "string", "required": False, "default": "zh-CN"},
        },
        "outputs": {
            "audio": {"type": "audio", "format": ["wav", "mp3", "ogg"], "required": True},
            "duration": {"type": "number", "required": True},
        }
    },
    {
        "node_type": "image_edit",
        "description": "图像编辑节点",
        "inputs": {
            "image": {"type": "image", "format": ["*"], "required": True},
            "instruction": {"type": "string", "required": True},
            "mask": {"type": "image", "format": ["png"], "required": False},
            "strength": {"type": "number", "required": False, "default": 0.8, "min": 0.0, "max": 1.0},
        },
        "outputs": {
            "image": {"type": "image", "format": ["png", "jpg"], "required": True},
        }
    },
    {
        "node_type": "data_filter",
        "description": "数据过滤/清洗节点",
        "inputs": {
            "data": {"type": "array", "required": True},
            "filter_rules": {"type": "object", "required": True},
            "min_quality_score": {"type": "number", "required": False, "default": 0.5},
        },
        "outputs": {
            "filtered_data": {"type": "array", "required": True},
            "filtered_count": {"type": "integer", "required": True},
            "total_count": {"type": "integer", "required": True},
        }
    },
    {
        "node_type": "format_converter",
        "description": "格式转换节点",
        "inputs": {
            "source": {"type": "any", "required": True},
            "target_format": {"type": "string", "required": True},
            "quality": {"type": "integer", "required": False, "default": 90, "min": 1, "max": 100},
        },
        "outputs": {
            "converted": {"type": "any", "required": True},
            "format": {"type": "string", "required": True},
        }
    },
]

# ── Pydantic Models ─────────────────────────────────────────────────────────

class DefineContractRequest(BaseModel):
    node_type: str = Field(..., min_length=1, max_length=128)
    inputs: Dict[str, Any] = Field(..., description="输入schema定义")
    outputs: Dict[str, Any] = Field(..., description="输出schema定义")
    description: str = Field(default="", max_length=512)
    version: str = Field(default="1.0.0", max_length=32)

class ValidateEdgeRequest(BaseModel):
    workflow_id: str = Field(default="", max_length=256)
    source_node: str = Field(..., min_length=1, max_length=128)
    target_node: str = Field(..., min_length=1, max_length=128)
    source_output: Dict[str, Any] = Field(..., description="源节点实际输出的数据")
    target_input: Dict[str, Any] = Field(..., description="目标节点需要接收的输入schema")

class ValidateWorkflowRequest(BaseModel):
    workflow_id: str = Field(..., min_length=1, max_length=256)
    edges: List[Dict[str, Any]] = Field(..., min_length=1, description="工作流边列表, 每边含source/target/output/input")

class CheckConflictsRequest(BaseModel):
    workflow_id: str = Field(..., min_length=1, max_length=256)
    contract_ids: Optional[List[str]] = Field(default=None)

class InferContractRequest(BaseModel):
    node_type: str = Field(..., min_length=1, max_length=128)
    sample_data: Dict[str, Any] = Field(default_factory=dict, description="节点样本数据，用于推断契约")

# ── JSON Schema Validation ──────────────────────────────────────────────────

def _validate_value_against_schema(value: Any, schema: Dict[str, Any]) -> List[str]:
    """Validate a single value against a simple schema definition. Returns list of errors."""
    errors = []
    expected_type = schema.get("type", "any")

    # Type checking
    type_map = {
        "string": str, "integer": int, "number": (int, float),
        "boolean": bool, "array": list, "object": dict,
    }
    if expected_type in type_map:
        expected = type_map[expected_type]
        if not isinstance(value, expected):
            errors.append(f"Type mismatch: expected {expected_type}, got {type(value).__name__}")

    # Numeric constraints
    if isinstance(value, (int, float)):
        if "min" in schema and value < schema["min"]:
            errors.append(f"Value {value} below minimum {schema['min']}")
        if "max" in schema and value > schema["max"]:
            errors.append(f"Value {value} above maximum {schema['max']}")

    # String constraints
    if isinstance(value, str):
        if "max_length" in schema and len(value) > schema["max_length"]:
            errors.append(f"String length {len(value)} exceeds max {schema['max_length']}")
        if "min_length" in schema and len(value) < schema["min_length"]:
            errors.append(f"String length {len(value)} below min {schema['min_length']}")
        if "pattern" in schema:
            import re
            if not re.match(schema["pattern"], value):
                errors.append(f"Value does not match pattern {schema['pattern']}")

    # Array constraints
    if isinstance(value, list):
        if "min_items" in schema and len(value) < schema["min_items"]:
            errors.append(f"Array length {len(value)} below min {schema['min_items']}")
        if "max_items" in schema and len(value) > schema["max_items"]:
            errors.append(f"Array length {len(value)} exceeds max {schema['max_items']}")

    return errors


def _validate_contract(output_data: Dict[str, Any], input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Validate output data against target's input schema."""
    compatible = True
    all_warnings = []
    all_errors = []

    for field_name, field_schema in input_schema.items():
        required = field_schema.get("required", False)

        if field_name not in output_data:
            if required:
                compatible = False
                all_errors.append(f"Missing required field: '{field_name}'")
            else:
                all_warnings.append(f"Optional field '{field_name}' not provided")
            continue

        field_errors = _validate_value_against_schema(output_data[field_name], field_schema)
        if field_errors:
            compatible = False
            all_errors.extend(f"Field '{field_name}': {e}" for e in field_errors)

    # Check for extra fields in output not expected by input
    extra_fields = set(output_data.keys()) - set(input_schema.keys())
    if extra_fields:
        all_warnings.append(f"Extra fields in output not consumed by target: {list(extra_fields)}")

    return {
        "compatible": compatible,
        "errors": all_errors,
        "warnings": all_warnings,
    }


def _infer_schema_from_data(data: Any, depth: int = 0) -> Dict[str, Any]:
    """Infer a JSON-like schema from sample data."""
    if depth > 5:
        return {"type": "any"}

    if isinstance(data, bool):
        return {"type": "boolean"}
    elif isinstance(data, int):
        return {"type": "integer"}
    elif isinstance(data, float):
        return {"type": "number"}
    elif isinstance(data, str):
        return {"type": "string", "max_length": len(data) * 2}
    elif isinstance(data, list):
        if len(data) > 0:
            item_schema = _infer_schema_from_data(data[0], depth + 1)
            return {"type": "array", "items": item_schema}
        return {"type": "array"}
    elif isinstance(data, dict):
        properties = {k: _infer_schema_from_data(v, depth + 1) for k, v in data.items()}
        return {"type": "object", "properties": properties}
    else:
        return {"type": "any"}


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health")
async def contract_health():
    try:
        with _get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "module": "workflow_contract", "version": "1.0.0", "db": "connected"}
    except Exception as e:
        return {"status": "degraded", "module": "workflow_contract", "version": "1.0.0", "db_error": str(e)}


@router.post("/define")
async def define_contract(req: DefineContractRequest):
    """
    定义节点契约: 输入/输出Schema定义，持久化到SQLite。
    """
    try:
        contract_id = f"contract_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with _get_db() as conn:
            conn.execute(
                "INSERT INTO contracts (id, node_type, inputs_schema, outputs_schema, version, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (contract_id, req.node_type,
                 json.dumps(req.inputs), json.dumps(req.outputs),
                 req.version, req.description, now, now)
            )
            conn.commit()

        logger.info(f"Contract defined: {contract_id} for node_type={req.node_type}")
        return {
            "ok": True,
            "data": {
                "contract_id": contract_id,
                "node_type": req.node_type,
                "inputs": req.inputs,
                "outputs": req.outputs,
                "version": req.version,
                "description": req.description,
                "created_at": now,
            }
        }
    except Exception as e:
        logger.exception(f"Define contract failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{contract_id}")
async def get_contract(contract_id: str):
    """获取指定契约"""
    try:
        with _get_db() as conn:
            row = conn.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")
        return {
            "ok": True,
            "data": {
                "contract_id": row["id"],
                "node_type": row["node_type"],
                "inputs": json.loads(row["inputs_schema"]),
                "outputs": json.loads(row["outputs_schema"]),
                "version": row["version"],
                "description": row["description"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Get contract failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_contract(req: ValidateEdgeRequest):
    """
    校验节点契约: 检查源节点输出与目标节点输入的兼容性。
    使用JSON Schema风格的逐字段验证。
    """
    try:
        result = _validate_contract(req.source_output, req.target_input)
        validation_id = f"val_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with _get_db() as conn:
            conn.execute(
                "INSERT INTO validations (id, workflow_id, source_node, target_node, source_output, target_input, "
                "compatible, warnings, errors, validated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (validation_id, req.workflow_id, req.source_node, req.target_node,
                 json.dumps(req.source_output), json.dumps(req.target_input),
                 1 if result["compatible"] else 0,
                 json.dumps(result["warnings"]), json.dumps(result["errors"]), now)
            )
            conn.commit()

        logger.info(f"Contract validated: {req.source_node}->{req.target_node}, compatible={result['compatible']}")
        return {
            "ok": True,
            "data": {
                "validation_id": validation_id,
                "workflow_id": req.workflow_id,
                "source_node": req.source_node,
                "target_node": req.target_node,
                "compatible": result["compatible"],
                "warnings": result["warnings"],
                "errors": result["errors"],
            }
        }
    except Exception as e:
        logger.exception(f"Validate contract failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate-workflow")
async def validate_workflow_contract(req: ValidateWorkflowRequest):
    """
    验证整个工作流的契约一致性: 遍历所有边，检查每一对的兼容性。
    """
    try:
        edge_validations = []
        all_valid = True
        total_errors = 0
        total_warnings = 0

        for edge in req.edges:
            source_node = edge.get("source_node", "unknown")
            target_node = edge.get("target_node", "unknown")
            source_output = edge.get("source_output", {})
            target_input = edge.get("target_input", {})

            result = _validate_contract(source_output, target_input)
            edge_validations.append({
                "source_node": source_node,
                "target_node": target_node,
                "compatible": result["compatible"],
                "warnings": result["warnings"],
                "errors": result["errors"],
            })

            if not result["compatible"]:
                all_valid = False
            total_errors += len(result["errors"])
            total_warnings += len(result["warnings"])

            # Persist
            validation_id = f"val_{uuid.uuid4().hex[:12]}"
            now = datetime.now(timezone.utc).isoformat()
            with _get_db() as conn:
                conn.execute(
                    "INSERT INTO validations (id, workflow_id, source_node, target_node, source_output, target_input, "
                    "compatible, warnings, errors, validated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (validation_id, req.workflow_id, source_node, target_node,
                     json.dumps(source_output), json.dumps(target_input),
                     1 if result["compatible"] else 0,
                     json.dumps(result["warnings"]), json.dumps(result["errors"]), now)
                )
                conn.commit()

        logger.info(f"Workflow validated: workflow={req.workflow_id}, edges={len(req.edges)}, valid={all_valid}, errors={total_errors}")
        return {
            "ok": True,
            "data": {
                "workflow_id": req.workflow_id,
                "edge_validations": edge_validations,
                "all_valid": all_valid,
                "total_edges": len(req.edges),
                "passed": sum(1 for e in edge_validations if e["compatible"]),
                "failed": sum(1 for e in edge_validations if not e["compatible"]),
                "total_errors": total_errors,
                "total_warnings": total_warnings,
            }
        }
    except Exception as e:
        logger.exception(f"Validate workflow failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
async def list_contract_templates():
    """
    列出预置的契约模板: 包含图像生成、视频生成、文本分类等常见节点类型。
    """
    return {
        "ok": True,
        "data": {
            "templates": CONTRACT_TEMPLATES,
            "total": len(CONTRACT_TEMPLATES),
        }
    }


@router.get("/templates/{node_type}")
async def get_contract_template(node_type: str):
    """获取指定类型节点的契约模板"""
    template = next((t for t in CONTRACT_TEMPLATES if t["node_type"] == node_type), None)
    if not template:
        raise HTTPException(status_code=404, detail=f"No template for node_type '{node_type}'")
    return {"ok": True, "data": template}


@router.post("/check-conflicts")
async def check_contract_conflicts(req: CheckConflictsRequest):
    """
    检测契约冲突: 查找同一工作流中多个版本的契约冲突。
    """
    try:
        conflicts = []

        with _get_db() as conn:
            if req.contract_ids:
                placeholders = ",".join("?" * len(req.contract_ids))
                rows = conn.execute(
                    f"SELECT * FROM contracts WHERE id IN ({placeholders})",
                    req.contract_ids
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM contracts ORDER BY node_type, created_at DESC"
                ).fetchall()

        # Group by node_type to find multi-version conflicts
        by_type = {}
        for row in rows:
            nt = row["node_type"]
            if nt not in by_type:
                by_type[nt] = []
            by_type[nt].append(dict(row))

        for node_type, records in by_type.items():
            if len(records) > 1:
                # Multiple contracts for same node type - potential conflict
                versions_present = [r["version"] for r in records]
                conflicts.append({
                    "type": "multi_version",
                    "node_type": node_type,
                    "versions": versions_present,
                    "contract_ids": [r["id"] for r in records],
                    "recommendation": "Consolidate to single contract or use version pinning",
                })

        logger.info(f"Contract conflict check: workflow={req.workflow_id}, conflicts={len(conflicts)}")
        return {
            "ok": True,
            "data": {
                "workflow_id": req.workflow_id,
                "conflicts": conflicts,
                "conflict_count": len(conflicts),
                "resolution_suggestions": [c["recommendation"] for c in conflicts],
            }
        }
    except Exception as e:
        logger.exception(f"Check conflicts failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/infer")
async def infer_contract(req: InferContractRequest):
    """
    自动推断契约: 从节点样本数据推断输入/输出契约schema。
    """
    try:
        inputs = req.sample_data.get("inputs", {})
        outputs = req.sample_data.get("outputs", {})

        inferred_inputs = _infer_schema_from_data(inputs) if inputs else {"type": "unknown"}
        inferred_outputs = _infer_schema_from_data(outputs) if outputs else {"type": "unknown"}

        # Check against templates
        template = next((t for t in CONTRACT_TEMPLATES if t["node_type"] == req.node_type), None)
        confidence = 0.5
        if template:
            # Higher confidence if template exists for this type
            confidence = 0.85

        logger.info(f"Contract inferred: node_type={req.node_type}, confidence={confidence}")
        return {
            "ok": True,
            "data": {
                "node_type": req.node_type,
                "inferred_inputs": inferred_inputs,
                "inferred_outputs": inferred_outputs,
                "confidence": confidence,
                "source": "template_match" if template else "data_analysis",
                "matching_template": template["description"] if template else None,
            }
        }
    except Exception as e:
        logger.exception(f"Infer contract failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
