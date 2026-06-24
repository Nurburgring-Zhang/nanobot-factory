"""
节点系统基类 — NodePort / NodeParam / NodeDefinition / BaseNode / Workflow api
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# 节点端口定义
# =============================================================================

class NodePort(BaseModel):
    """节点输入/输出端口"""
    name: str
    type: str = "any"  # "image", "image[]", "text", "text[]", "video", "dataset", "metadata", "any"
    required: bool = True


class NodeParam(BaseModel):
    """节点可调参数"""
    name: str
    type: str = "string"  # "string", "int", "float", "bool", "select"
    default: Any = None
    min: Optional[float] = None
    max: Optional[float] = None
    options: Optional[List[str]] = None  # for select type


# =============================================================================
# 节点定义元数据
# =============================================================================

class NodeDefinition(BaseModel):
    """节点完整定义（id/名称/类别/输入输出/参数）"""
    node_id: str
    name: str
    category: str  # "source", "filter", "label", "score", "select", "export", "generate", "quality", "control", "output"
    description: str = ""
    inputs: List[NodePort] = Field(default_factory=list)
    outputs: List[NodePort] = Field(default_factory=list)
    params: List[NodeParam] = Field(default_factory=list)


# =============================================================================
# 节点抽象基类
# =============================================================================

class BaseNode(ABC):
    """所有节点的抽象基类。"""

    definition: NodeDefinition

    @abstractmethod
    async def execute(
        self,
        inputs: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        异步执行节点。

        参数
        ----
        inputs : dict
            由上游节点或全局输入提供的端口值。key = 端口名称。
        params : dict
            用户或系统设置的参数。key = 参数名称。

        返回
        ----
        dict: {output_port_name: value, ...}
        """
        ...

    def __init_subclass__(cls, **kwargs):
        """确保子类设置了 definition"""
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, 'definition'):
            raise TypeError(
                f"{cls.__name__} must define a 'definition' class attribute "
                f"of type NodeDefinition"
            )


# =============================================================================
# 工作流定义模型
# =============================================================================

class WorkflowStep(BaseModel):
    """工作流中的一个步骤（节点实例）"""
    id: str
    node_id: str
    inputs: Dict[str, str] = Field(default_factory=dict)  # {port_name: "step_id.output_port"}
    params: Dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    """完整工作流定义"""
    id: str = ""
    name: str = ""
    steps: List[WorkflowStep] = Field(default_factory=list)
    output_step_id: Optional[str] = None
