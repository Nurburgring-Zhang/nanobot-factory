"""数据集管理器

功能:
- 数据集 CRUD + 版本管理 (git-like)
- 格式转换 (LLaVA/InternVL/COCO/YOLO/Parquet/HF)
- 数据类型检测 (图文/对话/交错/视频/文档)
- 存储后端管理
"""

from core.data_manager import (
    DataType,
    ExportFormat,
    Dataset,
    DatasetVersion as DataManagerVersion,
    DataManager,
)

from core.dataset_version import (
    DatasetVersion,
)

__all__ = [
    "DataType", "ExportFormat", "Dataset",
    "DataManagerVersion", "DataManager",
    "DatasetVersion",
]
