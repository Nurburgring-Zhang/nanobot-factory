"""alpaca — Alpaca SFT 格式导出器 (instruction/input/output).

op_id: export.alpaca
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

OP_ID = "export.alpaca"
NAME = "Alpaca 导出"
CATEGORY = "llm_sft"
DESCRIPTION = "导出 LLM SFT dataset 到 Alpaca 格式 (instruction/input/output JSONL)"
PARAMS: list = [
    {"name": "path", "type": "str", "default": "", "required": True},
    {"name": "instruction_field", "type": "str", "default": "instruction", "required": False},
    {"name": "input_field", "type": "str", "default": "input", "required": False},
    {"name": "output_field", "type": "str", "default": "output", "required": False},
]


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    path = str(params.get("path", "")).strip()
    if not path:
        return {"ok": False, "error": "missing_path"}
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    inst_f = str(params.get("instruction_field", "instruction"))
    inp_f = str(params.get("input_field", "input"))
    out_f = str(params.get("output_field", "output"))
    items = list(data) if isinstance(data, list) else [data]
    written = 0
    with open(path, "w", encoding="utf-8") as fp:
        for x in items:
            if isinstance(x, dict):
                instruction = str(x.get(inst_f, x.get("prompt", "")))
                input_ = str(x.get(inp_f, x.get("context", "")))
                output = str(x.get(out_f, x.get("response", "")))
            else:
                instruction = str(x)
                input_ = ""
                output = ""
            rec = {"instruction": instruction, "input": input_, "output": output}
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
    return {
        "ok": True,
        "format": "alpaca",
        "path": os.path.abspath(path),
        "rows_written": written,
    }
