"""智影 V4 — 平台 Agent 子包: 8 个 Agent 接管所有平台功能"""
from .base import PlatformAgent, AgentCapability
from .data_acquisition import DataAcquisitionAgent
from .annotation import AnnotationAgent
from .review import ReviewAgent
from .workflow import WorkflowAgent
from .project import ProjectAgent
from .user import UserAgent
from .pipeline import PipelineAgent
from .quality import QualityAgent
from .system import SystemAgent

__all__ = [
    "PlatformAgent",
    "AgentCapability",
    "DataAcquisitionAgent",
    "AnnotationAgent",
    "ReviewAgent",
    "WorkflowAgent",
    "ProjectAgent",
    "UserAgent",
    "PipelineAgent",
    "QualityAgent",
    "SystemAgent",
]
