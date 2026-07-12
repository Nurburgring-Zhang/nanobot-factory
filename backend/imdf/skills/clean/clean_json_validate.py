"""clean_json_validate — JSON Schema validation.

Validates a JSON document against a JSON Schema (subset of the spec).
Offline mode runs a tiny structural validator for type/required/enum.

Skill function: ``clean_json_validate(input) -> SkillOutput``.
"""

import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata, safe_httpx_call


SKILL_ID = "skill_clean_json_validate"


class JsonValidateInput(BaseModel):
    model_config = {"populate_by_name": True}

    document: Dict[str, Any] = Field(default_factory=dict)
    json_schema: Dict[str, Any] = Field(default_factory=dict, alias="schema")


class JsonValidateOutput(BaseModel):
    valid: bool
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    offline: bool = False


def _validate_offline(doc: Dict[str, Any], schema: Dict[str, Any], path: str = "$",
                      errs: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    errs = errs or []

    expected_type = schema.get("type")
    if expected_type:
        type_map = {
            "object": dict, "array": list, "string": str,
            "integer": int, "number": (int, float), "boolean": bool, "null": type(None),
        }
        py = type_map.get(expected_type)
        if py and not isinstance(doc, py):
            errs.append({"path": path, "message": f"expected type {expected_type}"})
            return errs

    if "required" in schema and isinstance(doc, dict):
        for key in schema["required"]:
            if key not in doc:
                errs.append({"path": f"{path}.{key}", "message": "missing required field"})

    if "enum" in schema:
        if doc not in schema["enum"]:
            errs.append({"path": path, "message": f"value not in enum {schema['enum']}"})

    if expected_type == "object" and isinstance(doc, dict):
        for key, sub_schema in (schema.get("properties") or {}).items():
            if key in doc:
                _validate_offline(doc[key], sub_schema, f"{path}.{key}", errs)
    elif expected_type == "array" and isinstance(doc, list):
        for i, item in enumerate(doc):
            _validate_offline(item, schema.get("items", {}), f"{path}[{i}]", errs)
    return errs


async def clean_json_validate(input: SkillInput) -> SkillOutput:
    payload = JsonValidateInput(**(input.params or {}))
    schema = payload.json_schema

    remote = await safe_httpx_call(
        "https://example.invalid/api/v1/clean/json/validate",
        payload=payload.model_dump(),
        mock={"valid": True, "errors": []},
    )
    if remote["status"] == "ok" and "valid" in remote["data"]:
        out = JsonValidateOutput(
            valid=bool(remote["data"]["valid"]),
            errors=list(remote["data"].get("errors", [])),
            offline=False,
        )
    else:
        errs = _validate_offline(payload.document, schema)
        out = JsonValidateOutput(valid=not errs, errors=errs, offline=True)

    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_json_validate", offline=out.offline),
    )


__all__ = ["JsonValidateInput", "JsonValidateOutput", "clean_json_validate"]
