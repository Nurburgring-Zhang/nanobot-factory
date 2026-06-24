"""用户认证和数据生产Pipeline状态机"""
import os, json, hashlib, uuid, logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)

# ===== 用户认证 =====
class UserSession:
    """简单的内存用户会话（生产环境应替换为JWT+Redis）"""
    _sessions: Dict[str, dict] = {}
    
    @classmethod
    def create(cls, username: str) -> dict:
        session_id = hashlib.sha256(f"{username}{uuid.uuid4()}{datetime.now().isoformat()}".encode()).hexdigest()[:32]
        session = {
            "session_id": session_id,
            "username": username,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=24)).isoformat(),
            "role": "admin" if username == "admin" else "user"
        }
        cls._sessions[session_id] = session
        return session
    
    @classmethod
    def validate(cls, session_id: str) -> Optional[dict]:
        session = cls._sessions.get(session_id)
        if not session:
            return None
        if datetime.fromisoformat(session["expires_at"]) < datetime.now():
            del cls._sessions[session_id]
            return None
        return session
    
    @classmethod
    def get_or_create(cls, username: str) -> dict:
        """查找已有session或创建新的"""
        for sid, s in cls._sessions.items():
            if s["username"] == username:
                return s
        return cls.create(username)


# ===== 数据生产Pipeline状态机 =====
class PipelineStage(str, Enum):
    """数据生产管线生命周期阶段"""
    RAW_IMPORT = "raw_import"           # 原始数据导入
    FILTERING = "filtering"             # 质量过滤
    ANNOTATION = "annotation"           # 标注
    AI_GENERATION = "ai_generation"     # AI生成
    QUALITY_CHECK = "quality_check"     # 质量检查
    DATASET_BUILD = "dataset_build"     # 数据集构建
    EXPORT = "export"                   # 导出
    COMPLETED = "completed"             # 完成
    FAILED = "failed"                   # 失败

class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

class PipelineState:
    """数据生产管线的状态跟踪
    
    每条Pipeline包含：当前阶段、进度百分比、每个阶段的耗时、错误信息
    """
    def __init__(self, pipeline_id: str, name: str, creator: str):
        self.pipeline_id = pipeline_id
        self.name = name
        self.creator = creator
        self.current_stage: PipelineStage = PipelineStage.RAW_IMPORT
        self.status: PipelineStatus = PipelineStatus.PENDING
        self.progress: float = 0.0  # 0-100
        self.stages: Dict[str, dict] = {}
        self.errors: List[str] = []
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.completed_at: Optional[str] = None
        self.total_items: int = 0
        self.processed_items: int = 0
    
    def to_dict(self) -> dict:
        return {
            "pipeline_id": self.pipeline_id,
            "name": self.name,
            "creator": self.creator,
            "current_stage": self.current_stage.value,
            "status": self.status.value,
            "progress": self.progress,
            "stages": self.stages,
            "errors": self.errors,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
        }

class PipelineManager:
    """管线管理器，跟踪所有用户的数据生产管线"""
    _pipelines: Dict[str, PipelineState] = {}
    
    @classmethod
    def create(cls, name: str, creator: str) -> PipelineState:
        pid = f"pipeline_{uuid.uuid4().hex[:12]}"
        pipeline = PipelineState(pid, name, creator)
        cls._pipelines[pid] = pipeline
        return pipeline
    
    @classmethod
    def get(cls, pipeline_id: str) -> Optional[PipelineState]:
        return cls._pipelines.get(pipeline_id)
    
    @classmethod
    def list_by_user(cls, username: str) -> List[dict]:
        return [p.to_dict() for p in cls._pipelines.values() if p.creator == username]
    
    @classmethod
    def list_all(cls) -> List[dict]:
        return [p.to_dict() for p in cls._pipelines.values()]
    
    @classmethod
    def advance_stage(cls, pipeline_id: str, stage: PipelineStage) -> bool:
        pipeline = cls._pipelines.get(pipeline_id)
        if not pipeline:
            return False
        pipeline.current_stage = stage
        pipeline.updated_at = datetime.now().isoformat()
        pipeline.status = PipelineStatus.RUNNING
        if stage not in pipeline.stages:
            pipeline.stages[stage.value] = {
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
                "items_processed": 0
            }
        return True
    
    @classmethod
    def complete_stage(cls, pipeline_id: str, stage: PipelineStage, items: int = 0) -> bool:
        pipeline = cls._pipelines.get(pipeline_id)
        if not pipeline:
            return False
        if stage.value in pipeline.stages:
            pipeline.stages[stage.value]["completed_at"] = datetime.now().isoformat()
            pipeline.stages[stage.value]["items_processed"] = items
        pipeline.processed_items += items
        # 自动计算进度
        stage_order = list(PipelineStage)
        current_idx = stage_order.index(stage) if stage in stage_order else 0
        pipeline.progress = min(100, (current_idx + 1) / len(stage_order) * 100)
        pipeline.updated_at = datetime.now().isoformat()
        return True
    
    @classmethod
    def fail(cls, pipeline_id: str, error: str) -> bool:
        pipeline = cls._pipelines.get(pipeline_id)
        if not pipeline:
            return False
        pipeline.status = PipelineStatus.FAILED
        pipeline.errors.append(error)
        pipeline.updated_at = datetime.now().isoformat()
        return True
    
    @classmethod
    def complete(cls, pipeline_id: str) -> bool:
        pipeline = cls._pipelines.get(pipeline_id)
        if not pipeline:
            return False
        pipeline.status = PipelineStatus.COMPLETED
        pipeline.progress = 100.0
        pipeline.completed_at = datetime.now().isoformat()
        pipeline.current_stage = PipelineStage.COMPLETED
        pipeline.updated_at = datetime.now().isoformat()
        return True
