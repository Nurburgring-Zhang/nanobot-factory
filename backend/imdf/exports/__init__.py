"""P19 v5.1-D3: 18 训练格式导出中心 (Export engine).

支持的训练格式 (18 总 = 12 既有 + 6 新增):

  3D 几何 (3) — 全部 NEW:
    - glb      : GLB (binary glTF)
    - gltf     : glTF (JSON 2.0)
    - obj      : Wavefront OBJ (text)

  图像 (6):
    - coco             : COCO Detection JSON
    - coco_panoptic    : COCO Panoptic Segmentation JSON + PNG masks (NEW)
    - yolo             : YOLO TXT + classes.names
    - pascal_voc       : Pascal VOC XML
    - createml         : CreateML JSON
    - clip             : CLIP JSONL (image-text pairs)

  视频 (1):
    - webdataset       : WebDataset tar shards

  多模态对话 (3):
    - llava            : LLaVA SFT JSON
    - internvl         : InternVL JSON
    - diffusiondb      : DiffusionDB Parquet

  表格 / log (3):
    - jsonl            : JSON Lines
    - parquet          : Apache Parquet
    - csv              : RFC4180 CSV

  音频 (2) — 全部 NEW:
    - wav              : WAVE PCM
    - mp3              : MP3 (lameenc)

注: PLY 是 multimodal.three_d 的 parse 格式 (3D 点云解析), 但不在 18 训练格式
export 注册表内 — PLY 文件会被 GLB/glTF/OBJ exporter 自动消费.

导出统一入口: ``ExportEngine.export(format, dataset, output)``.

每个 format exporter 都是一个简单的函数::

    def export_X(dataset: DatasetVersion, output: str) -> str:
        ...

DatasetVersion 由 ``engines.dataset_manager.DatasetManager`` 提供。
"""

from __future__ import annotations

from typing import Callable, Dict, List

# 每个 exporter 必须实现协议:
#   def exporter(dataset, output: str, **kwargs) -> str
ExportFn = Callable[..., str]


# ============================================================================
# 18 format registry
# ============================================================================
# P19 v5.1-D3 增加的 6 个 (标 NEW): glb, gltf, obj, coco_panoptic, wav, mp3
# 既有 12 个 (走 engines.dataset_manager 已有实现, 或本仓 internal helper):
#   coco, yolo, pascal_voc, createml, clip, webdataset,
#   llava, internvl, diffusiondb, jsonl, parquet, csv, ply
# 注意: 之前 multimodal 已经实现 PLY 输入解析, 但 export 端需要补成可写模块 —
# ply 走 ``exports.ply`` (兼容, 文本格式 export)
# ============================================================================

REGISTRY: Dict[str, Dict[str, object]] = {
    # ---------- 3D ----------
    "glb": {
        "label": "GLB",
        "mime": "model/gltf-binary",
        "ext": ".glb",
        "category": "3d",
        "description": "Binary glTF 2.0 (.glb) for 3D meshes.",
        "exporter": "exports.glb:export",
    },
    "gltf": {
        "label": "glTF",
        "mime": "model/gltf+json",
        "ext": ".gltf",
        "category": "3d",
        "description": "glTF 2.0 JSON for 3D meshes (Khronos).",
        "exporter": "exports.gltf:export",
    },
    "obj": {
        "label": "Wavefront OBJ",
        "mime": "model/obj",
        "ext": ".obj",
        "category": "3d",
        "description": "Wavefront OBJ text format (vertices + faces).",
        "exporter": "exports.obj:export",
    },
    # NOTE: PLY is supported as an *input* (parse) format by multimodal.three_d,
    # but is NOT registered as a separate training-format export here — PLY
    # inputs are consumed by GLB/glTF/OBJ exporters. The 18-format registry
    # stays at exactly 18 (12 existing + 6 new in P19 v5.1-D3).
    # ---------- image ----------
    "coco": {
        "label": "COCO Detection",
        "mime": "application/json",
        "ext": ".json",
        "category": "image",
        "description": "COCO object detection/annotation JSON.",
        "exporter": "engines.dataset_manager:DatasetManager.export_coco",
    },
    "coco_panoptic": {
        "label": "COCO Panoptic",
        "mime": "application/json",
        "ext": ".json",
        "category": "image",
        "description": "COCO Panoptic Segmentation (JSON + PNG masks).",
        "exporter": "exports.coco_panoptic:export",
    },
    "yolo": {
        "label": "YOLO TXT",
        "mime": "text/plain",
        "ext": ".zip",
        "category": "image",
        "description": "YOLOv5/v8 TXT labels + classes.names.",
        "exporter": "exports.yolo:export",
    },
    "pascal_voc": {
        "label": "Pascal VOC",
        "mime": "application/xml",
        "ext": ".xml",
        "category": "image",
        "description": "Pascal VOC XML per image.",
        "exporter": "exports.pascal_voc:export",
    },
    "createml": {
        "label": "CreateML",
        "mime": "application/json",
        "ext": ".json",
        "category": "image",
        "description": "Apple CreateML annotation JSON.",
        "exporter": "exports.createml:export",
    },
    "clip": {
        "label": "CLIP",
        "mime": "application/jsonl",
        "ext": ".jsonl",
        "category": "image",
        "description": "CLIP image-text pair JSONL.",
        "exporter": "exports.clip_fmt:export",
    },
    # ---------- video / multimodal ----------
    "webdataset": {
        "label": "WebDataset",
        "mime": "application/x-tar",
        "ext": ".tar",
        "category": "video",
        "description": "WebDataset tar shards (image+caption pairs).",
        "exporter": "engines.dataset_manager:DatasetManager.export_webdataset",
    },
    "llava": {
        "label": "LLaVA",
        "mime": "application/json",
        "ext": ".json",
        "category": "multimodal",
        "description": "LLaVA instruction-tuning JSON.",
        "exporter": "engines.dataset_manager:DatasetManager.export_llava",
    },
    "internvl": {
        "label": "InternVL",
        "mime": "application/json",
        "ext": ".json",
        "category": "multimodal",
        "description": "InternVL multi-modal dialog JSON.",
        "exporter": "engines.dataset_manager:DatasetManager.export_internvl",
    },
    "diffusiondb": {
        "label": "DiffusionDB",
        "mime": "application/octet-stream",
        "ext": ".parquet",
        "category": "multimodal",
        "description": "DiffusionDB style Parquet (prompt+image metadata).",
        "exporter": "exports.diffusiondb:export",
    },
    # ---------- table / log ----------
    "jsonl": {
        "label": "JSON Lines",
        "mime": "application/jsonl",
        "ext": ".jsonl",
        "category": "table",
        "description": "JSON Lines (one record per line).",
        "exporter": "engines.dataset_manager:DatasetManager.export_jsonl",
    },
    "parquet": {
        "label": "Apache Parquet",
        "mime": "application/octet-stream",
        "ext": ".parquet",
        "category": "table",
        "description": "Apache Parquet columnar storage.",
        "exporter": "engines.dataset_manager:DatasetManager.export_parquet",
    },
    "csv": {
        "label": "CSV",
        "mime": "text/csv",
        "ext": ".csv",
        "category": "table",
        "description": "RFC4180 CSV (UTF-8 BOM for Excel).",
        "exporter": "exports.csv_fmt:export",
    },
    # ---------- audio ----------
    "wav": {
        "label": "WAV PCM",
        "mime": "audio/wav",
        "ext": ".wav",
        "category": "audio",
        "description": "RIFF WAVE PCM audio.",
        "exporter": "exports.wav:export",
    },
    "mp3": {
        "label": "MP3",
        "mime": "audio/mpeg",
        "ext": ".mp3",
        "category": "audio",
        "description": "MP3 (MPEG-1 Layer 3) via lameenc.",
        "exporter": "exports.mp3:export",
    },
}


SUPPORTED_FORMATS: List[str] = sorted(REGISTRY.keys())


def get_format_info(fmt: str) -> Dict[str, object]:
    """Return the registry entry for ``fmt``. Raises ``KeyError`` if missing."""
    return REGISTRY[fmt]


def list_formats(category: str = "") -> List[str]:
    """List supported format IDs, optionally filtered by ``category``."""
    if not category:
        return SUPPORTED_FORMATS
    return [k for k, v in REGISTRY.items() if v.get("category") == category]


__all__ = [
    "REGISTRY",
    "SUPPORTED_FORMATS",
    "ExportFn",
    "get_format_info",
    "list_formats",
]