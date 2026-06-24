"""
IMDF Node-based Workflow Engine
================================
Provides:
  - NodeRegistry: auto-registers 47 node types
  - DAGEngine: build/validate/execute node workflows
  - TemplateManager: built-in workflow templates
"""

from nodes.registry import NodeRegistry, NodeDef, PortDef, ParamDef
from nodes.engine import DAGEngine, DAG, DAGNode, Connection, ExecutionContext
from nodes.templates import TemplateManager, WorkflowTemplate

__all__ = [
    "NodeRegistry", "NodeDef", "PortDef", "ParamDef",
    "DAGEngine", "DAG", "DAGNode", "Connection", "ExecutionContext",
    "TemplateManager", "WorkflowTemplate",
]
