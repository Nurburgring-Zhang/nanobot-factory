"""
IMDF Workflow Templates — predefined workflow configurations
============================================================
Provides built-in workflow templates that can be loaded into the
canvas, including text-to-image, video enhancement, and PPT auto-generation.
"""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict


# ─── Workflow Template Schema ────────────────────────────────────────────────

WORKFLOW_TEMPLATE_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "description", "nodes", "connections", "params"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "category": {"type": "string"},
        "icon": {"type": "string"},
        "nodes": {"type": "object"},
        "connections": {"type": "array"},
        "params": {"type": "object"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


@dataclass
class WorkflowTemplate:
    """A reusable workflow template."""
    id: str
    name: str
    description: str
    category: str = "通用"
    icon: str = "📋"
    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    connections: List[Dict[str, Any]] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> List[str]:
        """Validate template data against schema. Returns list of errors."""
        errors = []
        for req in WORKFLOW_TEMPLATE_SCHEMA["required"]:
            if req not in data:
                errors.append(f"Missing required field: '{req}'")
        if "id" in data and not isinstance(data["id"], str):
            errors.append("Field 'id' must be a string")
        if "nodes" in data and not isinstance(data["nodes"], dict):
            errors.append("Field 'nodes' must be a dict")
        if "connections" in data and not isinstance(data["connections"], list):
            errors.append("Field 'connections' must be a list")
        return errors


# ─── Built-in Templates ──────────────────────────────────────────────────────

_BUILTIN_TEMPLATES: Dict[str, WorkflowTemplate] = {}


def _build_t2i_basic() -> WorkflowTemplate:
    """Text-to-Image basic workflow."""
    return WorkflowTemplate(
        id="t2i_basic",
        name="文本转图片",
        description="将文本描述转换为图片 — 基础文生图工作流",
        category="图像生成",
        icon="🖼",
        nodes={
            "n1": {
                "id": "n1", "type": "text",
                "data": {"content": "一只可爱的小猫，阳光下打盹，温馨氛围"},
                "x": 50, "y": 80,
            },
            "n2": {
                "id": "n2", "type": "llm",
                "data": {"prompt": "", "model": "auto"},
                "x": 300, "y": 60,
            },
            "n3": {
                "id": "n3", "type": "image",
                "data": {"src": ""},
                "x": 550, "y": 80,
            },
            "n4": {
                "id": "n4", "type": "output",
                "data": {"fmt": "png"},
                "x": 550, "y": 300,
            },
        },
        connections=[
            {"from": "n1", "fromP": 0, "to": "n2", "toP": 0},
            {"from": "n2", "fromP": 0, "to": "n3", "toP": 0},
            {"from": "n3", "fromP": 0, "to": "n4", "toP": 0},
        ],
        params={
            "prompt": "一只可爱的小猫，阳光下打盹，温馨氛围",
            "model": "auto",
            "output_format": "png",
        },
        tags=["t2i", "基础", "图像"],
    )


def _build_video_pipeline() -> WorkflowTemplate:
    """Video enhancement pipeline."""
    return WorkflowTemplate(
        id="video_pipeline",
        name="视频增强流水线",
        description="视频上传 → AI增强 → Topaz提质 → 输出 — 全流程视频增强",
        category="视频处理",
        icon="🎬",
        nodes={
            "n1": {
                "id": "n1", "type": "upload",
                "data": {"path": ""},
                "x": 50, "y": 120,
            },
            "n2": {
                "id": "n2", "type": "videoedit",
                "data": {"action": "裁剪"},
                "x": 300, "y": 60,
            },
            "n3": {
                "id": "n3", "type": "topazvid",
                "data": {"model": "standard"},
                "x": 300, "y": 200,
            },
            "n4": {
                "id": "n4", "type": "video",
                "data": {"src": ""},
                "x": 550, "y": 120,
            },
            "n5": {
                "id": "n5", "type": "output",
                "data": {"fmt": "mp4"},
                "x": 750, "y": 120,
            },
        },
        connections=[
            {"from": "n1", "fromP": 0, "to": "n2", "toP": 0},
            {"from": "n1", "fromP": 0, "to": "n3", "toP": 0},
            {"from": "n2", "fromP": 0, "to": "n4", "toP": 0},
            {"from": "n3", "fromP": 0, "to": "n4", "toP": 0},
            {"from": "n4", "fromP": 0, "to": "n5", "toP": 0},
        ],
        params={
            "edit_action": "裁剪",
            "topaz_model": "standard",
            "output_format": "mp4",
        },
        tags=["video", "enhancement", "pipeline"],
    )


def _build_ppt_auto() -> WorkflowTemplate:
    """PPT auto-generation workflow."""
    return WorkflowTemplate(
        id="ppt_auto",
        name="PPT自动生成",
        description="输入主题 → AI生成大纲 → PPT排版 → 输出HTML",
        category="文档生成",
        icon="📊",
        nodes={
            "n1": {
                "id": "n1", "type": "text",
                "data": {"content": "2026年度工作总结与规划"},
                "x": 50, "y": 100,
            },
            "n2": {
                "id": "n2", "type": "llm",
                "data": {"prompt": "", "model": "auto"},
                "x": 280, "y": 60,
            },
            "n3": {
                "id": "n3", "type": "textsplit",
                "data": {"delimiter": "\\n\\n"},
                "x": 280, "y": 200,
            },
            "n4": {
                "id": "n4", "type": "ppt",
                "data": {"title": "PPT", "tpl": "clean-business", "slides": 5},
                "x": 520, "y": 120,
            },
            "n5": {
                "id": "n5", "type": "output",
                "data": {"fmt": "html"},
                "x": 750, "y": 120,
            },
        },
        connections=[
            {"from": "n1", "fromP": 0, "to": "n2", "toP": 0},
            {"from": "n2", "fromP": 0, "to": "n3", "toP": 0},
            {"from": "n3", "fromP": 0, "to": "n4", "toP": 0},
            {"from": "n4", "fromP": 0, "to": "n5", "toP": 0},
        ],
        params={
            "title": "2026年度工作总结与规划",
            "template": "clean-business",
            "slide_count": 5,
        },
        tags=["ppt", "自动生成", "文档"],
    )


def _build_ai_prelabel() -> WorkflowTemplate:
    """AI prelabeling workflow."""
    return WorkflowTemplate(
        id="ai_prelabel",
        name="AI预标注流水线",
        description="上传图片 → AI自动标注 → 结果审核 → 导出",
        category="数据标注",
        icon="🎯",
        nodes={
            "n1": {
                "id": "n1", "type": "upload",
                "data": {"path": ""},
                "x": 50, "y": 100,
            },
            "n2": {
                "id": "n2", "type": "prelabel",
                "data": {"prompt": "", "task_type": "detection"},
                "x": 300, "y": 100,
            },
            "n3": {
                "id": "n3", "type": "output",
                "data": {"fmt": "json"},
                "x": 550, "y": 100,
            },
        },
        connections=[
            {"from": "n1", "fromP": 0, "to": "n2", "toP": 0},
            {"from": "n2", "fromP": 0, "to": "n3", "toP": 0},
        ],
        params={
            "task_type": "detection",
        },
        tags=["标注", "AI", "数据"],
    )


def _build_img_upscale() -> WorkflowTemplate:
    """Image upscale pipeline."""
    return WorkflowTemplate(
        id="img_upscale",
        name="图片放大增强",
        description="上传图片 → AI放大 → 品质增强 → 输出",
        category="图像处理",
        icon="🔍",
        nodes={
            "n1": {
                "id": "n1", "type": "upload",
                "data": {"path": ""},
                "x": 50, "y": 80,
            },
            "n2": {
                "id": "n2", "type": "upscale",
                "data": {"scale": 2},
                "x": 280, "y": 80,
            },
            "n3": {
                "id": "n3", "type": "topazimg",
                "data": {"model": "standard"},
                "x": 280, "y": 220,
            },
            "n4": {
                "id": "n4", "type": "image",
                "data": {"src": ""},
                "x": 520, "y": 80,
            },
            "n5": {
                "id": "n5", "type": "output",
                "data": {"fmt": "png"},
                "x": 520, "y": 280,
            },
        },
        connections=[
            {"from": "n1", "fromP": 0, "to": "n2", "toP": 0},
            {"from": "n2", "fromP": 0, "to": "n4", "toP": 0},
            {"from": "n4", "fromP": 0, "to": "n5", "toP": 0},
        ],
        params={
            "scale": 2,
            "model": "standard",
        },
        tags=["图片", "放大", "增强"],
    )


def _build_empty() -> WorkflowTemplate:
    """Empty workflow template."""
    return WorkflowTemplate(
        id="empty",
        name="空白工作流",
        description="从空白画布开始，自由搭建工作流",
        category="通用",
        icon="⬜",
        nodes={},
        connections=[],
        params={},
        tags=["空白", "通用"],
    )


# ─── Template Manager ────────────────────────────────────────────────────────

class TemplateManager:
    """
    Workflow template manager.
    
    Provides CRUD for built-in and custom templates.
    """

    def __init__(self):
        self._templates: Dict[str, WorkflowTemplate] = {}
        self._load_builtins()

    def _load_builtins(self):
        """Load all built-in templates."""
        builders = [
            _build_t2i_basic,
            _build_video_pipeline,
            _build_ppt_auto,
            _build_ai_prelabel,
            _build_img_upscale,
            _build_empty,
        ]
        for builder in builders:
            tpl = builder()
            self._templates[tpl.id] = tpl

    def list_templates(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all templates, optionally filtered by category."""
        result = []
        for tpl in self._templates.values():
            if category and tpl.category != category:
                continue
            result.append(tpl.to_dict())
        return result

    def get_template(self, template_id: str) -> Optional[WorkflowTemplate]:
        """Get a template by ID."""
        return self._templates.get(template_id)

    def add_template(self, template: WorkflowTemplate) -> bool:
        """Add a custom template."""
        if template.id in self._templates:
            return False
        self._templates[template.id] = template
        return True

    def delete_template(self, template_id: str) -> bool:
        """Delete a template (only custom ones)."""
        if template_id.startswith("builtin_") or template_id in (
            "t2i_basic", "video_pipeline", "ppt_auto",
            "ai_prelabel", "img_upscale", "empty",
        ):
            return False  # Cannot delete built-in
        if template_id in self._templates:
            del self._templates[template_id]
            return True
        return False

    def list_categories(self) -> List[str]:
        """Get unique categories from all templates."""
        cats = set()
        for tpl in self._templates.values():
            cats.add(tpl.category)
        return sorted(cats)

    def count(self) -> int:
        return len(self._templates)
