"""tfrecord — TFRecord 导出器 (降级为 JSONL + manifest).

op_id: export.tfrecord
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any, Dict, List

OP_ID = "export.tfrecord"
NAME = "TFRecord 导出"
CATEGORY = "binary"
DESCRIPTION = "导出 dataset 到 TFRecord 格式 (无 tensorflow 时降级 JSONL + manifest)"
PARAMS: list = [
    {"name": "path", "type": "str", "default": "", "required": True},
    {"name": "image_field", "type": "str", "default": "image", "required": False,
     "description": "Field name containing image bytes/base64/path"},
]


def _encode_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        # Try base64 first
        try:
            return base64.b64decode(value, validate=True)
        except Exception:
            return value.encode("utf-8")
    if isinstance(value, dict) and "bytes" in value:
        return base64.b64decode(value["bytes"])
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _try_tensorflow(samples: List[Dict[str, Any]], path: str) -> Dict[str, Any]:
    try:
        import tensorflow as tf  # type: ignore
        with tf.io.TFRecordWriter(path) as w:
            for s in samples:
                feat: Dict[str, Any] = {}
                for k, v in s.items():
                    if isinstance(v, (bytes, bytearray)):
                        feat[k] = tf.train.Feature(bytes_list=tf.train.BytesList(value=[bytes(v)]))
                    elif isinstance(v, (int, float)):
                        feat[k] = tf.train.Feature(float_list=tf.train.FloatList(value=[float(v)]))
                    else:
                        feat[k] = tf.train.Feature(bytes_list=tf.train.BytesList(
                            value=[str(v).encode("utf-8")]))
                example = tf.train.Example(features=tf.train.Features(feature=feat))
                w.write(example.SerializeToString())
        return {"ok": True, "engine": "tensorflow"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "engine": "tensorflow", "error": str(e)}


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    path = str(params.get("path", "")).strip()
    if not path:
        return {"ok": False, "error": "missing_path"}
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    image_field = str(params.get("image_field", "image"))
    items = list(data) if isinstance(data, list) else [data]
    samples: List[Dict[str, Any]] = []
    for x in items:
        if isinstance(x, dict):
            samples.append(x)
        else:
            samples.append({"value": x})
    result = _try_tensorflow(samples, path)
    if result["ok"]:
        return {
            "ok": True,
            "format": "tfrecord",
            "path": os.path.abspath(path),
            "rows_written": len(samples),
            "engine": "tensorflow",
        }
    # Fallback: write JSONL + manifest
    base, _ = os.path.splitext(path)
    jsonl_path = base + ".jsonl"
    manifest_path = base + ".manifest.json"
    with open(jsonl_path, "w", encoding="utf-8") as fp:
        for s in samples:
            fp.write(json.dumps(s, ensure_ascii=False) + "\n")
    digest = hashlib.md5(open(jsonl_path, "rb").read()).hexdigest()
    manifest = {
        "format": "tfrecord-fallback",
        "tfrecord_error": result["error"],
        "data_path": jsonl_path,
        "image_field": image_field,
        "md5": digest,
        "rows": len(samples),
    }
    with open(manifest_path, "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2)
    return {
        "ok": True,
        "format": "tfrecord-fallback",
        "path": os.path.abspath(jsonl_path),
        "manifest_path": os.path.abspath(manifest_path),
        "rows_written": len(samples),
        "engine": "jsonl_fallback",
        "tfrecord_error": result["error"],
    }
