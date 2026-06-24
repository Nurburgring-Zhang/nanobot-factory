"""P3-6-W1: business export template — YOLO training.

Pipeline (Ultralytics YOLO training format export):
  1.  load_ann       - 加载 bbox 标注 dataset
  2.  cat_check      - 校验 class_names 非空且与标注一致
  3.  bbox_norm      - 归一化 bbox 到 YOLO xywhn (0~1, 相对宽高)
  4.  letterbox      - 等比 letterbox resize 到 img_size
  5.  small_drop     - 丢弃归一化后 box < min_norm_size
  6.  split          - train/val 切分 (默认 0.9/0.1)
  7.  write_yolo     - 写 data.yaml + labels/*.txt + train.txt + val.txt
  8.  write_card     - 渲染数据集 README + stats
  9.  oss_upload     - 上传到 det-yolo bucket

vs basic_templates/export.py::tpl-biz-exp-004: 本模板加入 cat_check +
  small_drop + 写 dataset README,适合 Ultralytics 直接训练。
"""
from __future__ import annotations
from typing import Any, Dict


TEMPLATE: Dict[str, Any] = {
    "id": "tpl-bz2-exp-004",
    "name": "YOLO Training Export (商业级)",
    "category": "export",
    "description": (
        "Ultralytics YOLO 训练格式导出:class 校验 + xywhn 归一化 + "
        "letterbox resize + 小 box 过滤 + data.yaml + README 写出。"
    ),
    "tags": ["yolo", "ultralytics", "detection", "txt",
             "letterbox", "export", "商业级"],
    "version": "1.1.0",
    "inputs": {
        "dataset_id": {"type": "string", "required": True},
        "class_names": {"type": "array<string>", "required": True,
                         "description": "class 名称数组, "
                                        "idx -> class_id"},
        "img_size": {"type": "int", "default": 640,
                     "description": "letterbox 目标尺寸"},
        "min_norm_size": {"type": "float", "default": 0.005,
                          "description": "归一化后 w/h < 此值丢弃"},
        "split_ratio": {"type": "array<float>", "default": [0.9, 0.1]},
        "write_data_yaml": {"type": "boolean", "default": True},
        "write_readme": {"type": "boolean", "default": True},
        "nc_names_top": {"type": "string", "default": "nc:",
                         "description": "data.yaml 的 nc 字段名"},
        "oss_bucket": {"type": "string", "default": "det-yolo"},
        "oss_key_prefix": {"type": "string", "default": "yolo/"},
    },
    "outputs": [
        "data.yaml",
        "labels/",
        "images/",
        "train.txt",
        "val.txt",
        "README.md",
        "stats.json",
    ],
    "steps": [
        {"id": "ld", "name": "Load Annotations",
         "operator": "dataset.load_annotations",
         "config": {"dataset_id": "$inputs.dataset_id"}},
        {"id": "cc", "name": "Class Name Consistency Check",
         "operator": "format.yolo_class_check",
         "config": {"class_names": "$inputs.class_names"}},
        {"id": "cn", "name": "BBox to YOLO XYWHN",
         "operator": "format.yolo_normalize",
         "config": {"to": "xywhn",
                    "class_names": "$inputs.class_names"}},
        {"id": "fd", "name": "Drop Tiny Boxes",
         "operator": "data.filter_yolo_small",
         "config": {"min_norm_size": "$inputs.min_norm_size"}},
        {"id": "rs", "name": "Letterbox Resize",
         "operator": "image.letterbox",
         "config": {"size": "$inputs.img_size",
                    "keep_ratio": True,
                    "pad_value": 114}},
        {"id": "sp", "name": "Train/Val Split",
         "operator": "data.split",
         "config": {"ratio": "$inputs.split_ratio"}},
        {"id": "wr", "name": "Write YOLO Files",
         "operator": "export.write_yolo",
         "config": {"write_data_yaml": "$inputs.write_data_yaml"}},
        {"id": "rd", "name": "Write Dataset README",
         "operator": "docs.render_card",
         "config": {"enabled": "$inputs.write_readme",
                    "format": "yolo_readme"}},
        {"id": "up", "name": "OSS Upload",
         "operator": "oss.upload",
         "config": {"bucket": "$inputs.oss_bucket",
                    "key_prefix": "$inputs.oss_key_prefix"}},
    ],
    "metrics": [
        "images_total", "labels_total",
        "avg_objs_per_image", "tiny_dropped",
        "split_train", "split_val", "duration_seconds",
    ],
}


__all__ = ["TEMPLATE"]