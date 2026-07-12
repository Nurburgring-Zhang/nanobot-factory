"""Pydantic v2 schemas for the Comfy MCP layer (V5 ch.30).

These types are deliberately framework-agnostic — they describe the
shape of data flowing between the natural-language parser, the model /
node retrievers, the workflow builder, and the ComfyClient.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _PositionalModel(BaseModel):
    """Mixin allowing ``Model(arg1, arg2, ...)`` style construction.

    Pydantic v2's :meth:`BaseModel.__init__` accepts ``**data`` only.
    Several of the test fixtures and helpers build graph edges like
    ``Connection("a", "b", "c", "d")`` for terseness, so we map
    positional arguments onto the declared field order before calling
    through.
    """

    model_config = ConfigDict(from_attributes=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        if args:
            field_names = list(self.__class__.model_fields.keys())
            for idx, value in enumerate(args):
                if idx >= len(field_names):
                    raise TypeError(
                        f"{self.__class__.__name__}.__init__() takes "
                        f"at most {len(field_names)} positional arguments "
                        f"but {len(args)} were given"
                    )
                kwargs.setdefault(field_names[idx], value)
        super().__init__(**kwargs)


class Connection(_PositionalModel):
    """An edge between two nodes in a workflow graph.

    Attributes:
        source_node: Node id providing the output.
        source_slot: Output slot name on the source node.
        target_node: Node id consuming the input.
        target_slot: Input slot name on the target node.
    """

    model_config = ConfigDict(from_attributes=True)

    source_node: str
    source_slot: str
    target_node: str
    target_slot: str


class Node(_PositionalModel):
    """A ComfyUI graph node.

    Attributes:
        id: Stable identifier used inside the workflow JSON.
        class_type: ComfyUI node class, e.g. ``KSampler``.
        inputs: Slot name -> literal value or a connection reference.
        meta: Free-form metadata (title, position, comments).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    class_type: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class Workflow(_PositionalModel):
    """A high-level workflow template.

    Distinct from :class:`FullWorkflow`: a template only lists nodes
    plus named connection slots, while a FullWorkflow is the
    concrete, runnable graph.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str = ""
    nodes: List[Node] = Field(default_factory=list)
    connections: List[Connection] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FullWorkflow(_PositionalModel):
    """A workflow ready for execution.

    Attributes:
        workflow_id: Stable identifier (uuid-like).
        graph: ``node_id -> Node`` mapping in ComfyUI JSON shape.
        models: Model ids referenced by the workflow.
        nodes_used: Class types referenced.
        estimated_vram_mb: Rough VRAM estimate (0 if unknown).
    """

    model_config = ConfigDict(from_attributes=True)

    workflow_id: str
    name: str
    graph: Dict[str, Node] = Field(default_factory=dict)
    models: List[str] = Field(default_factory=list)
    nodes_used: List[str] = Field(default_factory=list)
    estimated_vram_mb: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ModelMatch(_PositionalModel):
    """A search hit returned by :class:`ModelRetriever`."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    type: str
    score: float = 1.0
    reason: str = ""
    capabilities: List[str] = Field(default_factory=list)


class NodeMatch(_PositionalModel):
    """A search hit returned by :class:`NodeRetriever`."""

    model_config = ConfigDict(from_attributes=True)

    class_type: str
    score: float = 1.0
    reason: str = ""
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)


class GenerationResult(_PositionalModel):
    """A single output from running a workflow.

    Attributes:
        result_id: Persisted result identifier.
        workflow_id: Workflow that produced this result.
        status: ``success`` / ``failed`` / ``partial``.
        image_paths: Filesystem paths of saved images.
        metadata: Prompt, model, seed, etc.
        error: Optional error string for failed runs.
        duration_ms: Wall-clock latency for the run.
    """

    model_config = ConfigDict(from_attributes=True)

    result_id: str
    workflow_id: str
    status: Literal["success", "failed", "partial"] = "success"
    image_paths: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: int = 0


__all__ = [
    "Connection",
    "Node",
    "Workflow",
    "FullWorkflow",
    "ModelMatch",
    "NodeMatch",
    "GenerationResult",
]