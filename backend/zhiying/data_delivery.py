"""数据交付与血缘追踪

功能:
- 数据血缘: 行级来源追踪、上下游图、溯源分析
- 数据交付: 格式导出、打包下载、交付清单
- 数据安全: 水印注入、访问审计
"""

from core.data_lineage import (
    LineageNode,
    LineageManager,
)

from core.data_manager import (
    DataManager,
    ExportFormat,
)

import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DeliveryPackage:
    """数据交付包"""
    id: str
    name: str
    dataset_ids: List[str] = field(default_factory=list)
    format: ExportFormat = ExportFormat.JSONL
    watermark: bool = False
    encryption: bool = False
    size_mb: float = 0.0
    status: str = "pending"  # pending/processing/ready/delivered/expired
    download_url: str = ""
    expires_at: str = ""
    created_at: str = ""
    delivered_at: str = ""


class DeliveryManager:
    """数据交付管理器"""

    def __init__(self):
        self._packages: Dict[str, DeliveryPackage] = {}

    def create_package(self, name: str, dataset_ids: List[str],
                        format: ExportFormat = ExportFormat.JSONL,
                        watermark: bool = False,
                        encryption: bool = False) -> DeliveryPackage:
        pkg = DeliveryPackage(
            id=f"dlv_{uuid.uuid4().hex[:12]}",
            name=name,
            dataset_ids=dataset_ids,
            format=format,
            watermark=watermark,
            encryption=encryption,
            status="pending",
            created_at=datetime.now().isoformat(),
        )
        self._packages[pkg.id] = pkg
        logger.info(f"Delivery package created: {pkg.id}")
        return pkg

    def get_package(self, pkg_id: str) -> Optional[DeliveryPackage]:
        return self._packages.get(pkg_id)

    def list_packages(self) -> List[DeliveryPackage]:
        return list(self._packages.values())

    def mark_ready(self, pkg_id: str, download_url: str, size_mb: float):
        pkg = self._packages.get(pkg_id)
        if pkg:
            pkg.status = "ready"
            pkg.download_url = download_url
            pkg.size_mb = size_mb

    def mark_delivered(self, pkg_id: str):
        pkg = self._packages.get(pkg_id)
        if pkg:
            pkg.status = "delivered"
            pkg.delivered_at = datetime.now().isoformat()

    def get_lineage(self, asset_id: str, depth: int = 3) -> dict:
        """获取数据血缘图"""
        return LineageManager.get_lineage_graph(asset_id, depth)


__all__ = [
    "DeliveryPackage", "DeliveryManager",
    "LineageNode", "LineageManager", "ExportFormat",
]
