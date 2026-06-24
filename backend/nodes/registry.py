"""
节点系统模块 — 单独放置 registry 单例，避免循环导入。

NodeRegistry 单例在此定义，__init__.py 和各个节点模块均可安全引用。
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base import NodeDefinition, BaseNode

logger = logging.getLogger(__name__)


class NodeRegistry:
    """全局节点注册表（单例），管理所有节点类的注册、查找和执行。"""

    _instance = None
    _nodes: Dict[str, type] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._nodes = {}
        return cls._instance

    def register(self, node_cls: type):
        """注册一个节点类（须继承 BaseNode）"""
        inst = node_cls()
        self._nodes[inst.definition.node_id] = node_cls

    def get(self, node_id: str) -> Optional[type]:
        """根据 node_id 获取节点类"""
        return self._nodes.get(node_id)

    def list(self) -> List[NodeDefinition]:
        """列出所有已注册节点的定义"""
        return [cls().definition for cls in self._nodes.values()]

    def execute_step(self, node_id: str, inputs: Dict[str, Any],
                     params: Dict[str, Any]) -> Dict[str, Any]:
        """直接执行一个已注册节点（同步包装）"""
        cls = self._nodes.get(node_id)
        if not cls:
            raise ValueError(f"Node '{node_id}' not registered")
        node = cls()
        return asyncio.run(node.execute(inputs, params))


# 全局单例
registry = NodeRegistry()
