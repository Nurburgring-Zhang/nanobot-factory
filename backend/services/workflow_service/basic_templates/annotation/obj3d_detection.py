"""Annotation template: 3D object detection (3D 目标检测).

Pipeline:
  1.  load_pcd      - 加载点云 (bin / ply / las)
  2.  ground_seg    - 地面分割 (Patchwork)
  3.  prelabel_3d   - PointPillars / CenterPoint 候选 3D bbox
  4.  track         - 跨帧跟踪 (AB3DMOT)
  5.  human_3d      - 人工校验 (SUSTechPOINTS / custom 工具)
  6.  export_kitti  - 输出 KITTI 格式
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-ann-005",
    "name": "3D Object Detection (3D 目标检测)",
    "category": "annotation",
    "description": (
        "点云加载 + 地面分割 + 3D 预标注 + 跨帧跟踪 + 人工校验, "
        "输出 KITTI 格式。"
    ),
    "tags": ["3d", "annotation", "detection", "lidar"],
    "version": "1.0.0",
    "inputs": {
        "input_manifest": {"type": "string", "required": True},
        "pcd_format": {"type": "string", "default": "bin",
                        "enum": ["bin", "ply", "las", "pcd"]},
        "lidar_model": {"type": "string",
                         "default": "centerpoint-pillar"},
        "tracker": {"type": "string", "default": "ab3dmot"},
        "class_set": {"type": "array<string>",
                       "default": ["car", "pedestrian", "cyclist"]},
        "reviewers_per_item": {"type": "int", "default": 2},
        "oss_bucket": {"type": "string", "default": "annotations-3d"},
    },
    "outputs": ["label_kitti/", "tracks.json", "stats.json"],
    "steps": [
        {"id": "ld", "name": "Load PointCloud",
         "operator": "pcd.load",
         "config": {"format": "$inputs.pcd_format"}},
        {"id": "gs", "name": "Ground Segmentation",
         "operator": "pcd.ground_segment",
         "config": {"method": "patchwork",
                    "threshold": 0.3}},
        {"id": "pl", "name": "3D Prelabel",
         "operator": "lidar.detect_3d",
         "config": {"model": "$inputs.lidar_model",
                    "classes": "$inputs.class_set"}},
        {"id": "tr", "name": "Track",
         "operator": "lidar.track",
         "config": {"tracker": "$inputs.tracker"}},
        {"id": "hu", "name": "Human 3D BBox",
         "operator": "annotation.bbox3d_human",
         "config": {"tool": "sustechpoints",
                    "reviewers_per_item":
                        "$inputs.reviewers_per_item",
                    "sla_hours": 72}},
        {"id": "ex", "name": "Export KITTI",
         "operator": "annotation.export_kitti",
         "config": {"bucket": "$inputs.oss_bucket",
                    "include_calib": True}},
    ],
    "metrics": ["frames_total", "boxes_3d_total",
                "tracks_total", "duration_hours"],
}


__all__ = ["TEMPLATE"]