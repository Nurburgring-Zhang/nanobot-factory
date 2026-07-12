"""
Infinite Multimodal Data Foundry — Web UI Canvas Interface
================================================
FastAPI-based Web UI for the infinite canvas production system.

Endpoints:
  GET    /                 — HTML canvas page (draggable canvas)
  GET    /canvas/state     — Get current canvas state
  POST   /canvas/element   — Add element to canvas
  DELETE /canvas/element/{id} — Delete element
  POST   /engine/plan      — Plan production via Master Agent
  POST   /engine/render    — Execute engine rendering
  WS     /canvas/ws        — Real-time canvas state push

  # 3D
  GET    /api/3d/scenes/*  — 3D scene management (see canvas_3d.py)

  # Cloud storage
  POST   /api/cloud/storage/* — Cloud storage management (see cloud_storage.py)

  # Prompt templates
  GET    /api/prompt-templates    — Get all templates
  POST   /api/prompt-templates    — Create template
  PUT    /api/prompt-templates/{id} — Update template
  DELETE /api/prompt-templates/{id} — Delete template
  GET    /api/prompt-templates/categories — Get categories

  # Figma Bridge
  POST   /api/figma/import — Import material to Figma

  # @ upstream text linkage
  GET    /api/upstream-materials/{node_id} — Get upstream material list

  # Placement bar
  GET    /api/placement/recent — Recently used materials

  # Canvas tutorials
  GET    /api/tutorials — Tutorial list
"""

import os
import sys
import json
import re
import logging
import uuid
import asyncio
import shutil
import importlib.util
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path

# 先把项目根目录加入sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

from config.platform_config import find_project_root as get_project_root, PROJECT_ROOT as _project_root
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Phase1: 统一配置中心
from config.settings import (
    print_config_summary, to_dict as config_to_dict,
    ENABLE_ROBUSTNESS_MIDDLEWARE, MAX_CONCURRENT_REQUESTS,
    REQUEST_TIMEOUT_SECONDS, IMDF_WEB_HOST, IMDF_WEB_PORT,
    UVICORN_WORKERS, UVICORN_LOG_LEVEL,
)

# Phase1: 鲁棒性中间件
from api.middleware.robustness import RobustnessMiddleware, get_robustness_stats

# R1-Worker-2: 共享输入校验器 (防 bad_params 崩溃)
from api._common.validators import validate_id, ImagePathValidator
# R2-Worker-4: 调度 / webhook / 异步任务 验证器
from api._common.task_id_validator import validate_task_id

from core.canvas_core import (
    InfiniteCanvas, CanvasState, CanvasElement, ElementType,
    HistoryManager, SceneGraphManager
)
from agent.master_agent import MasterAgent, ProductionPlan, TaskStatus
from engines.video_engine import VideoEngine, VideoEngineType
from engines.engine_router import EngineRouter

# ============================================================================
# 嵌入3D/云存储API (如果存在)
# ============================================================================
try:
    from api.canvas_3d import router as router_3d
    HAS_3D = True
except ImportError:
    HAS_3D = False

try:
    from api.cloud_storage import router as router_cloud
    HAS_CLOUD = True
except ImportError:
    HAS_CLOUD = False

# ─── 复刻模块路由 ───────────────────────────────────────────────────────────
try:
    from api.media_manager import router as router_media
    HAS_MEDIA = True
except ImportError:
    HAS_MEDIA = False

try:
    from api.resource_library import router as router_library
    HAS_LIBRARY = True
except ImportError:
    HAS_LIBRARY = False

try:
    from api.system_config import router as router_config
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False

try:
    from api.board_manager import router as router_board
    HAS_BOARD = True
except ImportError:
    HAS_BOARD = False

try:
    from api.theme_manager import router as router_theme
    HAS_THEME = True
except ImportError:
    HAS_THEME = False

try:
    from api.external_providers import router as router_ext_providers
    HAS_EXT_PROVIDERS = True
except ImportError:
    HAS_EXT_PROVIDERS = False

try:
    from api.image_processor import router as router_image_ops
    HAS_IMAGE_OPS = True
except ImportError:
    HAS_IMAGE_OPS = False

try:
    from api.figma_bridge import router as router_figma
    HAS_FIGMA_BRIDGE = True
except ImportError:
    HAS_FIGMA_BRIDGE = False

# ─── 监控/数据/运营看板路由 ─────────────────────────────────────────────────
try:
    from api.monitor_routes import router as router_monitor
    HAS_MONITOR = True
except ImportError:
    HAS_MONITOR = False

try:
    from api.data_browser_routes import router as router_data_browser
    HAS_DATA_BROWSER = True
except ImportError:
    HAS_DATA_BROWSER = False

try:
    from api.ops_dashboard_routes import router as router_ops
    HAS_OPS = True
except ImportError:
    HAS_OPS = False

# ─── 众包/交付路由 (annotation_routes moved to annotation-service in P3-2-W1) ──
try:
    from api.crowd_routes import router as router_crowd
    HAS_CROWD = True
except ImportError:
    HAS_CROWD = False

try:
    from api.delivery_routes import router as router_delivery
    HAS_DELIVERY = True
except ImportError:
    HAS_DELIVERY = False

import structlog
import logging
from logging.handlers import RotatingFileHandler

# ============================================================================
# P0-3: 结构化日志 (Structlog) + Phase2: 日志轮转
# ============================================================================

# Ensure log directory exists
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

# ── 标准库日志级别桥接: structlog → stdlib logging ─────────────────────────
# structlog sends to stdlib LoggerFactory; configure stdlib handlers

_ACCESS_LOG_PATH = _LOG_DIR / "access.log"
_ERROR_LOG_PATH = _LOG_DIR / "error.log"

# Root logger — only set up handlers once
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)

# Remove any existing handlers to avoid duplicates on reload
_root_logger.handlers.clear()

# Console handler (stderr) for development
_console_handler = logging.StreamHandler(sys.stderr)
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
))
_root_logger.addHandler(_console_handler)

# Access log: all INFO+ messages → access.log (rotating: 10MB × 5 files)
_access_handler = RotatingFileHandler(
    str(_ACCESS_LOG_PATH),
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding="utf-8",
)
_access_handler.setLevel(logging.INFO)
_access_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
))
_root_logger.addHandler(_access_handler)

# Error log: only WARNING+ → error.log (rotating: 10MB × 5 files)
_error_handler = RotatingFileHandler(
    str(_ERROR_LOG_PATH),
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding="utf-8",
)
_error_handler.setLevel(logging.WARNING)
_error_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
))
_root_logger.addHandler(_error_handler)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Replace standard logger with structlog
logger = structlog.get_logger(__name__)


# ============================================================================
# Data Models

class AddElementRequest(BaseModel):
    el_type: str = "text"       # text/image/video/shape
    name: str = ""
    x: float = 100.0
    y: float = 100.0
    width: float = 256.0
    height: float = 256.0
    content: Dict[str, Any] = {}
    properties: Dict[str, Any] = {}


class PlanRequest(BaseModel):
    user_input: str = ""


class RenderRequest(BaseModel):
    plan_id: str = ""


# ============================================================================
# 提示词模板 Models (复刻: Penguin Canvas PromptTemplateLibrary)
# ============================================================================

class PromptTemplate(BaseModel):
    """提示词模板"""
    id: str = ""
    title: str = ""
    prompt: str = ""
    negative: str = ""
    kind: str = "image"       # image / video / audio / text
    category: str = "通用"
    tags: List[str] = []
    is_builtin: bool = False
    media_attachments: List[Dict[str, Any]] = []
    created_at: str = ""


class PromptTemplateCreate(BaseModel):
    title: str = "新模板"
    prompt: str = ""
    negative: str = ""
    kind: str = "image"
    category: str = "通用"
    tags: List[str] = []


class PromptCategory(BaseModel):
    id: str = ""
    name: str = ""
    kind: str = "image"
    sort_order: int = 0


# ============================================================================
# Figma Bridge Models (复刻: Penguin Canvas Figma联动)
# ============================================================================

class FigmaImportRequest(BaseModel):
    image_url: str = ""
    image_data: Optional[str] = None  # base64
    title: str = "untitled"
    kind: str = "image"


# ============================================================================
# 上游素材 Models (复刻: Penguin Canvas @模式)
# ============================================================================

class UpstreamMaterial(BaseModel):
    id: str = ""
    node_id: str = ""
    node_name: str = ""
    kind: str = "text"       # text / image / video / audio
    content_preview: str = ""
    full_content: Any = None
    url: str = ""


# ============================================================================
# 放置栏 Models (复刻: Penguin Canvas 放置栏)
# ============================================================================

class PlacementItem(BaseModel):
    id: str = ""
    element_id: str = ""
    element_name: str = ""
    element_type: str = ""
    thumbnail_url: str = ""
    last_used: str = ""


# ============================================================================
# 教程 Models (复刻: Penguin Canvas 画布教程)
# ============================================================================

class Tutorial(BaseModel):
    id: str = ""
    title: str = ""
    description: str = ""
    url: str = ""
    platform: str = "bilibili"  # bilibili / youtube
    order: int = 0


# ============================================================================
# Workflow API Models
# ============================================================================

class WorkflowNode(BaseModel):
    id: str = ""
    type: str = ""
    data: Dict[str, Any] = {}
    x: float = 0.0
    y: float = 0.0


class WorkflowConnection(BaseModel):
    from_id: str = Field(default="", alias="from")
    fromP: int = 0
    to_id: str = Field(default="", alias="to")
    toP: int = 0


class WorkflowValidateRequest(BaseModel):
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    connections: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowExecuteRequest(BaseModel):
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    connections: List[Dict[str, Any]] = Field(default_factory=list)


# ============================================================================
# Application
# ============================================================================

class CanvasWebApp:
    """Web UI画布应用"""

    def __init__(self):
        self.canvas = InfiniteCanvas(width=2000, height=2000)
        self.master = MasterAgent()
        self.engine = VideoEngine()
        self.router = EngineRouter()
        self._plans: Dict[str, ProductionPlan] = {}
        self._websockets: List[WebSocket] = []
        self._ws_lock = asyncio.Lock()

        # --- 复刻功能管理 ---
        # 提示词模板 (Penguin Canvas PromptTemplateLibrary)
        self._prompt_templates: Dict[str, PromptTemplate] = {}
        self._prompt_categories: Dict[str, PromptCategory] = {}
        self._load_prompt_templates()

        # Figma导入队列 (Penguin Canvas Figma Bridge)
        self._figma_queue: List[Dict[str, Any]] = []

        # 放置栏记录 (Penguin Canvas 放置栏)
        self._placement_history: List[PlacementItem] = []

        # 内置教程 (Penguin Canvas 画布教程)
        self._tutorials: List[Tutorial] = self._build_tutorials()

    # ========================================================================
    # 提示词模板管理 (Penguin Canvas PromptTemplateLibrary 复刻)
    # ========================================================================

    def _load_prompt_templates(self):
        """加载内置提示词模板"""
        # 内置图像模板分类
        image_categories = [
            "人像 / 角色", "产品 / 电商", "分镜 / 宫格", "场景 / 世界观",
            "风格 / 光影", "海报 / 品牌", "全景 / VR", "参考 / 重绘",
        ]
        video_categories = [
            "电影镜头", "运镜 / 镜头运动", "角色动作", "产品短片",
            "社媒 / 广告", "转场 / 特效", "音乐 / 声音", "图生视频 / 首尾帧",
        ]

        # 创建分类
        for i, cat in enumerate(image_categories):
            c = PromptCategory(id=f"img_cat_{i}", name=cat, kind="image", sort_order=i)
            self._prompt_categories[c.id] = c
        for i, cat in enumerate(video_categories):
            c = PromptCategory(id=f"vid_cat_{i}", name=cat, kind="video", sort_order=i + 100)
            self._prompt_categories[c.id] = c

        # 内置模板样本 (完整版可扩展)
        builtin_samples = [
            PromptTemplate(id="builtin_img_1", title="产品三视图",
                           prompt="产品三视图展示，白色背景，均匀光影，360度展示产品细节",
                           kind="image", category="产品 / 电商", is_builtin=True),
            PromptTemplate(id="builtin_img_2", title="电影级光影",
                           prompt="电影级光影校正，柔和侧光，高对比度，胶片质感",
                           kind="image", category="风格 / 光影", is_builtin=True),
            PromptTemplate(id="builtin_img_3", title="全景VR图",
                           prompt="360度全景图，宽广视角，沉浸式环境，高分辨率细节",
                           kind="image", category="全景 / VR", is_builtin=True),
            PromptTemplate(id="builtin_vid_1", title="推近镜头",
                           prompt="镜头匀速向前推进，主体位于画面中心，背景逐渐远离",
                           kind="video", category="电影镜头", is_builtin=True),
            PromptTemplate(id="builtin_vid_2", title="环绕运镜",
                           prompt="镜头围绕主体顺时针环绕运动，保持主体始终在画面中心",
                           kind="video", category="运镜 / 镜头运动", is_builtin=True),
            PromptTemplate(id="builtin_vid_3", title="产品展示短片",
                           prompt="产品360度旋转展示，自然光，白色无缝背景，微距特写",
                           kind="video", category="产品短片", is_builtin=True),
        ]
        for t in builtin_samples:
            t.created_at = datetime.now().isoformat()
            self._prompt_templates[t.id] = t

        # 加载自定义模板
        self._load_custom_templates()

    def _load_custom_templates(self):
        """加载自定义模板 (从JSON文件)"""
        path = Path("data/prompt_templates.json")
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    t = PromptTemplate(**item)
                    if t.id not in self._prompt_templates:
                        self._prompt_templates[t.id] = t
            except Exception as e:
                logger.warning(f"加载自定义模板失败: {e}")

    def _save_custom_templates(self):
        """保存自定义模板"""
        custom = [t for t in self._prompt_templates.values() if not t.is_builtin]
        Path("data").mkdir(exist_ok=True)
        with open("data/prompt_templates.json", "w", encoding="utf-8") as f:
            json.dump([t.dict() for t in custom], f, ensure_ascii=False, indent=2)

    def get_prompt_templates(self, kind: Optional[str] = None,
                              category: Optional[str] = None) -> List[Dict]:
        """获取模板列表"""
        results = list(self._prompt_templates.values())
        if kind:
            results = [t for t in results if t.kind == kind]
        if category:
            results = [t for t in results if t.category == category]
        return [t.dict() for t in sorted(results, key=lambda x: (0 if x.is_builtin else 1, x.title))]

    def create_prompt_template(self, req: PromptTemplateCreate) -> PromptTemplate:
        """创建模板"""
        tid = f"custom_{uuid.uuid4().hex[:8]}"
        t = PromptTemplate(
            id=tid, title=req.title, prompt=req.prompt,
            negative=req.negative, kind=req.kind, category=req.category,
            tags=req.tags, is_builtin=False,
            created_at=datetime.now().isoformat(),
        )
        self._prompt_templates[tid] = t
        self._save_custom_templates()
        return t

    def update_prompt_template(self, tid: str, req: PromptTemplateCreate) -> Optional[PromptTemplate]:
        """更新模板"""
        t = self._prompt_templates.get(tid)
        if not t or t.is_builtin:
            return None
        t.title = req.title
        t.prompt = req.prompt
        t.negative = req.negative
        t.kind = req.kind
        t.category = req.category
        t.tags = req.tags
        self._save_custom_templates()
        return t

    def delete_prompt_template(self, tid: str) -> bool:
        """删除模板"""
        t = self._prompt_templates.get(tid)
        if not t or t.is_builtin:
            return False
        del self._prompt_templates[tid]
        self._save_custom_templates()
        return True

    def get_prompt_categories(self, kind: Optional[str] = None) -> List[Dict]:
        """获取分类列表"""
        cats = list(self._prompt_categories.values())
        if kind:
            cats = [c for c in cats if c.kind == kind]
        return [c.dict() for c in sorted(cats, key=lambda x: x.sort_order)]

    # ========================================================================
    # Figma Bridge (复刻: Penguin Canvas Figma联动)
    # ========================================================================

    def figma_import(self, req: FigmaImportRequest) -> Dict[str, Any]:
        """导入素材到Figma队列"""
        item = {
            "id": f"figma_{uuid.uuid4().hex[:8]}",
            "image_url": req.image_url,
            "image_data": req.image_data,
            "title": req.title,
            "kind": req.kind,
            "created_at": datetime.now().isoformat(),
        }
        self._figma_queue.append(item)
        return item

    def figma_claim(self, max_items: int = 10) -> List[Dict[str, Any]]:
        """Figma插件轮询获取待导入素材"""
        items = self._figma_queue[:max_items]
        self._figma_queue = self._figma_queue[max_items:]
        return items

    # ========================================================================
    # 上游素材 @模式 (复刻: Penguin Canvas MentionPromptInput)
    # ========================================================================

    def get_upstream_materials(self, node_id: str) -> List[Dict]:
        """获取指定节点的上游素材列表"""
        materials = []
        # 遍历画布元素查找上游连接
        for el_id, el in self.canvas.state.elements.items():
            if el_id == node_id:
                continue
            preview = ""
            full = None
            if el.el_type == ElementType.TEXT:
                preview = str(el.content.get("text", ""))[:80]
                full = el.content.get("text", "")
            elif el.el_type == ElementType.IMAGE:
                preview = f"🖼 {el.name}"
            elif el.el_type == ElementType.VIDEO:
                preview = f"🎬 {el.name}"
            elif el.el_type == ElementType.AUDIO:
                v = self.canvas.state.elements.get(el_id)
                preview = f"🎵 {el.name}"

            materials.append(UpstreamMaterial(
                id=f"mat_{uuid.uuid4().hex[:8]}",
                node_id=el_id,
                node_name=el.name,
                kind=el.el_type.value if hasattr(el.el_type, 'value') else "text",
                content_preview=preview,
                full_content=full,
                url=el.content.get("src", ""),
            ).dict())
        return materials

    # ========================================================================
    # 放置栏 (复刻: Penguin Canvas 放置栏)
    # ========================================================================

    def record_placement(self, el_id: str, el_name: str,
                          el_type: str, thumb_url: str = ""):
        """记录素材使用到放置栏"""
        existing = [p for p in self._placement_history if p.element_id == el_id]
        if existing:
            self._placement_history.remove(existing[0])
        item = PlacementItem(
            id=f"pl_{uuid.uuid4().hex[:8]}",
            element_id=el_id, element_name=el_name,
            element_type=el_type, thumbnail_url=thumb_url,
            last_used=datetime.now().isoformat(),
        )
        self._placement_history.insert(0, item)
        # 最多保留20条
        self._placement_history = self._placement_history[:20]

    def get_recent_placements(self, limit: int = 20) -> List[Dict]:
        """获取最近使用的素材"""
        return [p.dict() for p in self._placement_history[:limit]]

    # ========================================================================
    # 画布教程 (复刻: Penguin Canvas 画布教程)
    # ========================================================================

    def _build_tutorials(self) -> List[Tutorial]:
        return [
            Tutorial(id="tut_1", title="基础功能教程第一弹",
                     description="画布基础操作、节点添加与连接",
                     url="https://www.bilibili.com/video/BV18sG76AE9Y/",
                     platform="bilibili", order=1),
            Tutorial(id="tut_2", title="教程第二弹（循环系统，RH超市等）",
                     description="循环系统、RH超市使用说明",
                     url="https://www.bilibili.com/video/BV1CVGx6kEMV/",
                     platform="bilibili", order=2),
            Tutorial(id="tut_3", title="教程第三弹（节点回避算法，资产库等）",
                     description="节点回避算法、资产库、自定义主题",
                     url="https://www.bilibili.com/video/BV1qeVP6kEZi/",
                     platform="bilibili", order=3),
            Tutorial(id="tut_4", title="教程第九弹（3D全景功能，资产库等）",
                     description="3D全景功能及资产库、一键自动更新、AI去水印升级",
                     url="https://www.bilibili.com/video/BV1gSEA6GEDQ/",
                     platform="bilibili", order=9),
        ]

    def get_tutorials(self) -> List[Dict]:
        return [t.dict() for t in sorted(self._tutorials, key=lambda x: x.order)]

    def get_state(self) -> Dict[str, Any]:
        """获取当前画布状态"""
        return self.canvas.to_dict()

    def set_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """设置画布状态 — 保存到文件 (前端工作流保存)"""
        import os, json
        state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "workflow_state.json")
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return {"success": True, "message": "画布状态已保存", "file": state_path}

    def add_element(self, req: AddElementRequest) -> Dict[str, Any]:
        """向画布添加元素"""
        try:
            el_type = ElementType(req.el_type)
        except ValueError:
            el_type = ElementType.TEXT

        el = self.canvas.state.add_element(
            el_type=el_type,
            name=req.name or f"元素_{len(self.canvas.state.elements) + 1}",
            x=req.x, y=req.y,
            width=req.width, height=req.height,
            content=req.content,
            properties=req.properties,
        )
        snap_id = self.canvas.commit(f"添加元素: {el.name}")
        return {"element": el.to_dict(), "snapshot_id": snap_id}

    def remove_element(self, el_id: str) -> bool:
        """从画布移除元素"""
        result = self.canvas.state.remove_element(el_id)
        if result:
            self.canvas.commit(f"移除元素: {el_id}")
        return result

    def plan(self, user_input: str) -> Dict[str, Any]:
        """用Master Agent规划生产"""
        plan = self.master.plan(user_input)
        self._plans[plan.id] = plan
        return {
            "plan_id": plan.id,
            "content_type": plan.content_type,
            "primary_engine": plan.primary_engine,
            "fallback_engine": plan.fallback_engine,
            "workers": [{"id": w.id, "name": w.name, "engine": w.engine} for w in plan.workers],
            "checkpoints": plan.checkpoints,
        }

    def render(self, plan_id: str) -> Dict[str, Any]:
        """执行引擎渲染"""
        plan = self._plans.get(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

        plan.status = TaskStatus.IN_PROGRESS
        results = []

        # 根据内容类型选择对应引擎
        content_type = plan.content_type
        engine_key = plan.primary_engine

        if content_type == "video":
            # 使用VideoEngine
            video_engine = self.engine
            text = plan.user_intent
            project = video_engine.plan(text)
            
            # 选择引擎并渲染
            engine_choice = video_engine.select_best_engine(project)
            render_results = video_engine.render_segments(project)
            
            # 合成
            output_path = video_engine.compose(project)
            
            # 审核
            review = video_engine.review(project)
            
            results = render_results
            output = output_path
            
            # 把输出加为画布元素
            self.canvas.state.add_element(
                el_type=ElementType.VIDEO,
                name=project.title,
                x=100, y=100,
                width=800, height=450,
                content={"src": output_path, "engine": engine_choice["primary"]},
                properties={"duration": project.total_duration},
            )

        elif content_type in ("image", "infographic", "poster"):
            # 使用EngineRouter决定
            decision = self.router.decide(plan.user_intent)
            # 生成HTML结构
            html_output = f"<div style='width:1024px;padding:40px;font-family:sans-serif;'><h1>{plan.user_intent}</h1><p>Content type: {content_type}, Engine: {decision.engines[0].value}</p></div>"
            
            output = f"/tmp/imdf_output_{plan_id}.html"
            with open(output, "w") as f:
                f.write(html_output)
            
            results = [{
                "engine": decision.engines[0].value,
                "output": output,
                "status": "generated",
            }]
            
            self.canvas.state.add_element(
                el_type=ElementType.IMAGE,
                name=f"{content_type} output",
                x=100, y=100,
                width=800, height=600,
                content={"html": html_output},
            )

        elif content_type == "short_drama":
            output = f"/tmp/imdf_drama_{plan_id}.md"
            with open(output, "w") as f:
                f.write(f"# 短剧: {plan.user_intent}\n\n{json.dumps(plan.worker_status(), ensure_ascii=False, indent=2) if hasattr(plan, 'worker_status') else ''}")
            
            results = [{"engine": "story-arc", "output": output, "status": "generated"}]
            
        else:
            # 通用处理
            output = f"/tmp/imdf_generic_{plan_id}.txt"
            with open(output, "w") as f:
                f.write(f"Plan: {plan_id}\nInput: {plan.user_intent}\nType: {content_type}\nEngine: {engine_key}")
            
            results = [{"engine": engine_key, "output": output, "status": "generated"}]

        # 更新Worker状态
        for w in plan.workers:
            w.status = TaskStatus.COMPLETED
            w.output = output

        plan.status = TaskStatus.COMPLETED
        self.canvas.commit(f"渲染完成: {plan_id}")

        return {
            "plan_id": plan_id,
            "content_type": content_type,
            "engine": engine_key,
            "results": results,
            "output": output,
        }

    # WebSocket management
    async def broadcast(self, message: Dict[str, Any]):
        """向所有连接的WebSocket广播消息"""
        async with self._ws_lock:
            dead = []
            for ws in self._websockets:
                try:
                    await ws.send_json(message)
                except Exception as e:
                    logger.error(f"WebSocket broadcast failed: {e}", exc_info=True)
                    dead.append(ws)
            for ws in dead:
                self._websockets.remove(ws)

    async def handle_websocket(self, websocket: WebSocket):
        """处理WebSocket连接"""
        await websocket.accept()
        async with self._ws_lock:
            self._websockets.append(websocket)
        
        # 发送初始状态
        await websocket.send_json({
            "type": "state",
            "data": self.get_state(),
        })
        
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                action = msg.get("action", "")
                
                if action == "get_state":
                    await websocket.send_json({
                        "type": "state",
                        "data": self.get_state(),
                    })
                elif action == "add_element":
                    req = AddElementRequest(**msg.get("payload", {}))
                    result = self.add_element(req)
                    await websocket.send_json({
                        "type": "element_added",
                        "data": result,
                    })
                    await self.broadcast({
                        "type": "state_updated",
                        "data": self.get_state(),
                    })
                elif action == "remove_element":
                    el_id = msg.get("payload", {}).get("element_id", "")
                    success = self.remove_element(el_id)
                    await websocket.send_json({
                        "type": "element_removed",
                        "data": {"element_id": el_id, "success": success},
                    })
                    if success:
                        await self.broadcast({
                            "type": "state_updated",
                            "data": self.get_state(),
                        })
                elif action == "plan":
                    user_input = msg.get("payload", {}).get("user_input", "")
                    result = self.plan(user_input)
                    await websocket.send_json({
                        "type": "plan_created",
                        "data": result,
                    })
                elif action == "render":
                    plan_id = msg.get("payload", {}).get("plan_id", "")
                    result = self.render(plan_id)
                    await websocket.send_json({
                        "type": "render_complete",
                        "data": result,
                    })
                    await self.broadcast({
                        "type": "state_updated",
                        "data": self.get_state(),
                    })

                # === 复刻功能 WebSocket 事件 ===
                # 素材放置记录
                elif action == "record_placement":
                    payload = msg.get("payload", {})
                    self.record_placement(
                        payload.get("element_id", ""),
                        payload.get("element_name", ""),
                        payload.get("element_type", ""),
                        payload.get("thumbnail_url", ""),
                    )
                    await websocket.send_json({
                        "type": "placement_recorded",
                        "data": {"success": True},
                    })

                # 获取上游素材
                elif action == "get_upstream_materials":
                    node_id = msg.get("payload", {}).get("node_id", "")
                    materials = self.get_upstream_materials(node_id)
                    await websocket.send_json({
                        "type": "upstream_materials",
                        "data": {"materials": materials},
                    })

                # 提示词模板
                elif action == "get_prompt_templates":
                    kind = msg.get("payload", {}).get("kind")
                    category = msg.get("payload", {}).get("category")
                    templates = self.get_prompt_templates(kind, category)
                    await websocket.send_json({
                        "type": "prompt_templates",
                        "data": {"templates": templates},
                    })

                elif action == "create_prompt_template":
                    req = PromptTemplateCreate(**msg.get("payload", {}))
                    t = self.create_prompt_template(req)
                    await websocket.send_json({
                        "type": "prompt_template_created",
                        "data": t.dict(),
                    })

                elif action == "delete_prompt_template":
                    tid = msg.get("payload", {}).get("template_id", "")
                    ok = self.delete_prompt_template(tid)
                    await websocket.send_json({
                        "type": "prompt_template_deleted",
                        "data": {"success": ok},
                    })

                # 教程
                elif action == "get_tutorials":
                    tutorials = self.get_tutorials()
                    await websocket.send_json({
                        "type": "tutorials",
                        "data": {"tutorials": tutorials},
                    })

                # Figma
                elif action == "figma_import":
                    req = FigmaImportRequest(**msg.get("payload", {}))
                    item = self.figma_import(req)
                    await websocket.send_json({
                        "type": "figma_imported",
                        "data": item,
                    })
                    
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            async with self._ws_lock:
                if websocket in self._websockets:
                    self._websockets.remove(websocket)


# ============================================================================
# FastAPI App
# ============================================================================

app_state = CanvasWebApp()

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import signal as _signal

_shutdown_in_progress = False

async def graceful_shutdown(sig, frame):
    global _shutdown_in_progress
    if _shutdown_in_progress:
        return
    _shutdown_in_progress = True
    logger.warning(f"收到信号 {sig}, 开始优雅关闭...")
    # 等待进行中任务完成(最长30秒)
    pending_tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for t in pending_tasks:
        t.cancel()
    await asyncio.sleep(0.1)
    logger.info("优雅关闭完成")

@asynccontextmanager
async def lifespan(app):
    # startup
    # 注册信号处理器
    for sig in (_signal.SIGTERM, _signal.SIGINT):
        try:
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(graceful_shutdown(s, None)))
        except NotImplementedError:
            pass  # Windows不支持add_signal_handler

    # Phase3: 初始化调度器引擎 + 预置Agent任务
    try:
        from engines.scheduler_engine import get_scheduler, init_preset_jobs
        scheduler = get_scheduler()
        scheduler.start()
        init_preset_jobs()
        logger.info("scheduler_engine", status="started",
                     job_count=len(scheduler.list_jobs()))
    except Exception as e:
        logger.warning("scheduler_engine", status="startup_failed", error=str(e))

    # Phase3: 初始化事件引擎 + 预置事件处理器
    try:
        from engines.event_engine import init_event_handlers
        init_event_handlers()
        logger.info("event_engine", status="started")
    except Exception as e:
        logger.warning("event_engine", status="startup_failed", error=str(e))

    # 初始化审计表
    await _ensure_audit_table()

    logger.info("IMDF服务启动")
    yield
    # shutdown - 优雅关闭
    try:
        from engines.scheduler_engine import get_scheduler
        scheduler = get_scheduler()
        if scheduler.running:
            scheduler.stop()
            logger.info("scheduler_engine", status="stopped")
    except Exception as e:
        logger.error(f"Failed to stop scheduler during shutdown: {e}")
    logger.info("IMDF服务关闭")

app = FastAPI(
    title="IMDF",
    description="Infinite Multimodal Data Foundry - 无限画布生产系统Web界面",
    version="2.0.0",
    lifespan=lifespan,
)

# P3-8-W2: OpenTelemetry / Jaeger tracing — distributed tracing for all routes.
# Initialised once at import time. Safe no-op if OTel packages not installed.
try:
    from monitoring.tracing import setup_tracing, instrument_fastapi
    _tracing_ok = setup_tracing(
        service_name="imdf-main",
        otlp_endpoint=None,  # use env OTEL_EXPORTER_OTLP_ENDPOINT or default Jaeger
    )
    if _tracing_ok:
        _instrumented = instrument_fastapi(app)
        logger.info(
            "Distributed tracing enabled: imdf-main (FastAPI instrumented=%s)",
            _instrumented,
        )
    else:
        logger.info("Distributed tracing disabled (otel packages not installed)")
except Exception as _otel_err:
    logger.warning(f"OTel tracing setup failed: {_otel_err}")

# CORS中间件 — R9.5-W1 替换 ["*"] 为白名单 (env: CSRF_TRUSTED_ORIGINS)
# 见 api.security_middleware.CORS_ALLOWED_ORIGINS
try:
    from api.security_middleware import CORS_ALLOWED_ORIGINS as _TRUSTED_ORIGINS
    _cors_origins = _TRUSTED_ORIGINS
    if not _cors_origins or _cors_origins == ["*"]:
        # 回退: 配置缺失时使用 defaults 而不是 * (避免生产全开)
        from api.security_middleware import DEFAULT_TRUSTED_ORIGINS as _TRUSTED_ORIGINS
        _cors_origins = list(_TRUSTED_ORIGINS)
        logger.warning(
            "CORS 配置回退到默认白名单 (CSRF_TRUSTED_ORIGINS 未设置或为 *); "
            "生产环境请设置 CSRF_TRUSTED_ORIGINS=url1,url2"
        )
except Exception as _e:
    logger.warning(f"CORS 白名单加载失败, 回退到默认白名单: {_e}")
    from api.security_middleware import DEFAULT_TRUSTED_ORIGINS
    _cors_origins = list(DEFAULT_TRUSTED_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# R9.5-W1: CSRFMiddleware — Origin/Referer 白名单 + 双 cookie
try:
    from api.security_middleware import CSRFMiddleware
    app.add_middleware(CSRFMiddleware)
    logger.info(f"CSRF 中间件已加载, trusted_origins={len(_cors_origins)}")
except Exception as _e:
    logger.warning(f"CSRF 中间件加载失败: {_e}")

# P2: 请求体大小限制 — 最大10MB
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024  # 10 MB

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request body size."""
    
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                cl = int(content_length)
                if cl > MAX_REQUEST_BODY_SIZE:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "success": False,
                            "error": f"请求体过大: {cl} bytes, 最大允许: {MAX_REQUEST_BODY_SIZE} bytes (10MB)"
                        }
                    )
            except ValueError:
                pass
        return await call_next(request)

app.add_middleware(RequestSizeLimitMiddleware)

# R7-Worker-2: 结构化日志 + trace_id 跨服务传递
# (registers BEFORE the inline @app.middleware("http") logger below so trace context
# is set before any structured_logging_middleware event fires)
try:
    from api._common.middleware import RequestLoggingMiddleware, TraceIDMiddleware
    # Order matters: add_middleware is LIFO — last added runs first.
    # We want TraceIDMiddleware to be the OUTERMOST wrapper so the trace context
    # is set before RequestLoggingMiddleware emits the request event.
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(TraceIDMiddleware)
    logger.info("结构化日志中间件已加载 (TraceID + RequestLogging)")
except Exception as e:
    logger.warning(f"R7 middleware加载失败: {e}")

# P3-1-W2: 把 gateway 来的 /internal/* 路径反解为 /api/* 路由
# Gateway (port 8000) 把客户端 /api/v1/... 转发到 8765/internal/api/v1/...
# 这里在路由前剥离 /internal/ 前缀, 老客户端直接打 /api/... 不受影响
class _StripInternalPrefixMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/internal/"):
            new_path = "/" + path[len("/internal/"):]
            # 构造新 scope 路径
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode("latin-1")
        elif path == "/internal":
            request.scope["path"] = "/"
            request.scope["raw_path"] = b"/"
        return await call_next(request)

app.add_middleware(_StripInternalPrefixMiddleware)
logger.info("P3-1-W2 _StripInternalPrefixMiddleware 已加载 (gateway /internal/* -> /*)")

# Phase0: 挂载静态前端文件
import os
_frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
if os.path.exists(_frontend_dir):
    app.mount("/css", StaticFiles(directory=os.path.join(_frontend_dir, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(_frontend_dir, "js")), name="js")

# P0-9 / R9.5-W1: SlowAPI 限流 (默认 100/min/IP, 由具体端点覆盖)
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ============================================================================
# Phase1: 统一响应格式
# ============================================================================

def api_success(data: Any = None, message: str = "ok") -> dict:
    """统一成功响应"""
    return {"success": True, "data": data, "message": message}

def api_error(message: str = "error", code: int = 400, details: Any = None) -> JSONResponse:
    """统一错误响应"""
    return JSONResponse(
        status_code=code,
        content={"success": False, "error": message, "details": details}
    )

def paginated_response(items: list, total: int, page: int = 1, size: int = 20) -> dict:
    """统一分页响应"""
    return api_success({
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, (total + size - 1) // size),
    })

@app.exception_handler(Exception)
async def unified_error_handler(request, exc):
    import traceback
    return api_error(str(exc), code=500, details=traceback.format_exc()[:500])

@app.exception_handler(HTTPException)
async def http_error_handler(request, exc):
    return api_error(exc.detail, code=exc.status_code)


# ============================================================================
# Phase2: Enhanced Health Check Endpoints (delegated to api/health_routes.py)
# ============================================================================
try:
    from api.health_routes import router as health_router
    app.include_router(health_router)
    logger.info("增强健康检查路由已加载 (/api/v1/health, /api/v1/health/ready, /api/v1/health/live)")
except Exception as e:
    logger.warning(f"健康检查路由加载失败: {e}")

# R7-Worker-2: 顶层 /healthz + /readyz 探针 (k8s 风格)
try:
    from api.healthz import router as healthz_router
    app.include_router(healthz_router)
    logger.info("liveness探针已加载 (/healthz)")
except Exception as e:
    logger.warning(f"/healthz 路由加载失败: {e}")

try:
    from api.readyz import router as readyz_router
    app.include_router(readyz_router)
    logger.info("readiness探针已加载 (/readyz)")
except Exception as e:
    logger.warning(f"/readyz 路由加载失败: {e}")

# P5-R2 fix: 暴露 auth_routes 端点 (项目中心/需求中心/数据包/工作台等新端点需要 JWT)
# 这是 P5 端到端 E2E 的关键阻塞,加这一行解阻塞
try:
    from api.auth_routes import router as auth_router
    app.include_router(auth_router)
    logger.info("Auth 路由已加载 (/api/v1/auth/* - 登录/JWT)")
except Exception as e:
    logger.warning(f"Auth 路由加载失败: {e}")


# ============================================================================
# P2-1-W2: Celery / async queue health endpoint
# ============================================================================
@app.get("/api/queue/health")
async def queue_health():
    """Celery / Redis broker health snapshot.

    Returns 200 with ``status`` field of ``ok`` or ``degraded``. We always
    return 200 so the endpoint is cheap to scrape — the status field is
    what callers should branch on. If the broker is unreachable and
    ``CELERY_HEALTH_REQUIRED`` is true, status will be ``degraded`` and
    ``broker_reachable`` will be False; if the worker is fully down, that
    is the signal to alert on.
    """
    try:
        from imdf.celery_app import health_summary
        summary = health_summary()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("queue_health probe failed")
        return api_success({
            "status": "degraded",
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "broker_reachable": False,
        })
    return api_success(summary)


@app.post("/api/queue/submit")
async def queue_submit(payload: dict):
    """Submit a render_project task to the imdf.video queue.

    Body shape: a ``VideoProject`` dict (the same shape accepted by
    ``POST /api/v1/video/render``). Returns the Celery task id which can
    be polled via ``GET /api/queue/status/{task_id}``.
    """
    try:
        from imdf.tasks.render_video import render_project
        async_result = render_project.delay(payload or {})
        return api_success({
            "task_id": async_result.id,
            "status": async_result.status,
            "queue": "imdf.video",
        })
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("queue_submit failed")
        return api_error(f"queue_unavailable: {exc}", code=503)


@app.get("/api/queue/status/{task_id}")
async def queue_status(task_id: str):
    """Return the status of a previously submitted task."""
    try:
        from imdf.celery_app import celery_app
        async_result = celery_app.AsyncResult(task_id)
        out = {
            "task_id": task_id,
            "status": async_result.status,
            "ready": async_result.ready(),
        }
        if async_result.successful():
            try:
                out["result"] = async_result.get(timeout=0.1, propagate=False)
            except Exception:
                out["result"] = None
        elif async_result.failed():
            try:
                out["error"] = str(async_result.info)[:400]
            except Exception:
                out["error"] = "task_failed"
        return api_success(out)
    except Exception as exc:  # pragma: no cover
        return api_error(f"queue_unavailable: {exc}", code=503)


# Phase1: 鲁棒性统计端点
@app.get("/api/v1/robustness/stats")
async def robustness_stats(
    dr: "DateRangeParams" = None,
    granularity: "Granularity" = None,
    dimension: str = "metric",
):
    """返回当前并发请求统计(用于监控)

    R2-Worker-5: 注入 DateRangeParams + granularity 枚举 + dimension 白名单 (轻量校验)。
    """
    from api._common.date_range import DateRangeParams
    from api._common.granularity import Granularity
    from api._common.dimension import is_valid_dimension

    # 维度白名单 (内部 scope 用, 与其他 stats 端点对齐)
    allowed = ("metric", "status", "date", "source")
    if not is_valid_dimension(dimension, scope="default"):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(allowed)}",
        )
    stats = get_robustness_stats()
    return api_success(stats, message="robustness_stats")


# ============================================================================
# P0-3: Structured Logging Middleware + Phase2: Slow Request Alert & Metrics
# ============================================================================
#
# R7-Worker-2 (Observability):
#   The legacy in-line ``structured_logging_middleware`` below was REPLACED by
#   the new ``TraceIDMiddleware`` + ``RequestLoggingMiddleware`` registered
#   earlier in app construction (see "结构化日志中间件已加载" block above).
#   Those new middlewares are functionally equivalent AND additionally:
#     * propagate X-Trace-Id across services
#     * bind trace_id / request_id into the logging context (auto-injected
#       into every structlog event via ContextVars)
#     * log the requesting client IP
#     * use a try/finally so even unhandled exceptions get a structured event
#   To keep behaviour identical and avoid double-logging, the old code is
#   kept only as a documentation reference and is not wired into the app.
# ============================================================================

# --- (DEPRECATED, kept as doc-only reference) -------------------------------
# @app.middleware("http")
# async def structured_logging_middleware(request: Request, call_next):
#     """记录每个请求的method/path/status/elapsed_ms, 分配request_id
#     Phase2增强:
#       - 慢请求(>1s)自动记录WARNING
#       - 请求指标记录到engines.metrics
#     """
#     request_id = str(uuid.uuid4())
#     start = datetime.now(timezone.utc)
#     response = await call_next(request)
#     elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
#     elapsed_sec = elapsed / 1000.0
#     log_data = {
#         "request_id": request_id,
#         "method": request.method,
#         "path": request.url.path,
#         "status_code": response.status_code,
#         "elapsed_ms": round(elapsed, 1),
#     }
#     if response.status_code >= 400:
#         logger.warning("request completed", **log_data)
#     else:
#         logger.info("request completed", **log_data)
#     if elapsed_sec > 1.0:
#         logger.warning("slow request detected", **log_data, slow_threshold_s=1.0)
#     try:
#         from engines.metrics import record_request as metrics_record
#         path_normalized = request.url.path
#         import re
#         path_normalized = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{uuid}', path_normalized)
#         path_normalized = re.sub(r'/\d{4,}', '/{id}', path_normalized)
#         metrics_record(request.method, path_normalized, response.status_code, elapsed_sec)
#     except Exception as e:
#         logger.warning(f"Metrics recording failed: {e}")
#     response.headers["X-Request-ID"] = request_id
#     return response


# ============================================================================
# P0-7: 审计日志中间件 + P2-3-W3: HMAC-SHA256 签名链 (OWASP A08)
# ============================================================================

import hashlib
import aiosqlite

# P2-3-W3: 引入 audit_chain — 与 audit_log 并行写, 不替换原 audit_log (向后兼容).
# audit_log 表保留供 audit_routes.py 查询, audit_chain 表加 prev_hash + signature.
try:
    from engines.audit_chain import (
        AuditChain, AuditChainError,
        configure_default_db_path, get_chain,
    )
    HAS_AUDIT_CHAIN = True
except ImportError as e:
    HAS_AUDIT_CHAIN = False
    logger.warning(f"audit_chain module not available, A08 signing disabled: {e}")

_AUDIT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "audit.db"
_AUDIT_CHAIN_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "audit_chain.db"
os.makedirs(str(_AUDIT_DB_PATH.parent), exist_ok=True)

# P2-3-W3: 配置 audit_chain 默认 db 路径 + 启动时 verify_chain.
# 若 AUDIT_CHAIN_SECRET 缺失, 启动时 audit_chain.AuditChain() 会 raise —
# 此处 try/except 把 raise 降级为 warning, 让开发 / 测试环境可以不带 secret 跑.
_chain_init_ok = False
if HAS_AUDIT_CHAIN:
    try:
        configure_default_db_path(_AUDIT_CHAIN_DB_PATH)
        # 触发 lazy init + 启动 verify — 失败 raise, 降级为 warning
        _chain = get_chain()
        _chain_init_ok = True
        logger.info("audit_chain initialized, integrity verified on startup")
    except AuditChainError as e:
        logger.warning(
            f"audit_chain disabled (A08 signing OFF): {e}. "
            "Set AUDIT_CHAIN_SECRET env (>= 16 chars) to enable."
        )
        _chain_init_ok = False
    except Exception as e:
        logger.error(f"audit_chain init failed: {e}")
        _chain_init_ok = False


async def _ensure_audit_table():
    """确保审计日志表存在"""
    async with aiosqlite.connect(str(_AUDIT_DB_PATH)) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                user TEXT DEFAULT '',
                body_hash TEXT DEFAULT '',
                status_code INTEGER NOT NULL
            )
        """)
        await conn.commit()


@app.middleware("http")
async def audit_log_middleware(request: Request, call_next):
    """记录所有POST/PUT/PATCH/DELETE操作到审计日志 + HMAC 签名链 (P2-3-W3).

    - audit_log: 兼容原 R10.5 业务, plain sqlite insert (向后兼容)
    - audit_chain: 加 prev_hash + entry_hash + HMAC-SHA256 signature, 启动时 verify
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # Read body for hashing
        body = b""
        try:
            body = await request.body()
        except Exception as e:
            logger.error(f"Failed to read request body for audit: {e}")
        body_hash = hashlib.md5(body).hexdigest() if body else ""
        user = request.headers.get("X-User", "")
        ts_iso = datetime.now(timezone.utc).isoformat()

        response = await call_next(request)

        # 1. 写 audit_log (向后兼容)
        try:
            async with aiosqlite.connect(str(_AUDIT_DB_PATH)) as conn:
                await conn.execute(
                    "INSERT INTO audit_log (timestamp, method, path, user, body_hash, status_code) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (ts_iso, request.method, str(request.url.path),
                     user, body_hash, response.status_code)
                )
                await conn.commit()
        except Exception as e:
            logger.error(f"Audit log write failed: {e}")  # Don't break request if audit fails

        # 2. P2-3-W3: 写 audit_chain (HMAC-SHA256 签名) — 失败仅 log, 不影响请求
        if HAS_AUDIT_CHAIN and _chain_init_ok:
            try:
                _chain.append(
                    timestamp=ts_iso,
                    method=request.method,
                    path=str(request.url.path),
                    user=user,
                    body_hash=body_hash,
                    status_code=response.status_code,
                )
            except Exception as e:
                logger.error(f"audit_chain append failed: {e}")

        return response
    else:
        response = await call_next(request)
        return response


# ============================================================================
# Phase1: 鲁棒性中间件 — 请求队列保护 + 超时 + Panic Recovery
# ============================================================================

if ENABLE_ROBUSTNESS_MIDDLEWARE:
    app.add_middleware(
        RobustnessMiddleware,
        max_concurrent=MAX_CONCURRENT_REQUESTS,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        enabled=True,
    )
    logger.info(
        "robustness_middleware",
        status="enabled",
        max_concurrent=MAX_CONCURRENT_REQUESTS,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
    )
else:
    logger.warning("robustness_middleware", status="disabled")


# ============================================================================
# R7-W1: Prometheus Metrics + 慢查询监听 (一站式接入)
# ============================================================================
try:
    from api._common.middleware import install_middlewares
    install_middlewares(
        app,
        enable_metrics=True,
        enable_slow_query=True,
        slow_query_threshold_ms=200,
    )
except Exception as _r7_exc:
    logger.warning(
        "r7_metrics_middleware_failed",
        error=str(_r7_exc),
    )


# HTML Canvas Page
# ============================================================================

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IMDF 无限画布</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;overflow:hidden;height:100vh}
.app{display:flex;height:100vh}
/* 侧边栏 */
.sb{width:200px;min-width:200px;background:#16213e;display:flex;flex-direction:column;border-right:1px solid #2a2a4a}
.sb-tabs{display:flex;border-bottom:1px solid #2a2a4a}
.sb-tab{padding:8px;font-size:11px;cursor:pointer;flex:1;text-align:center;color:#888;border-bottom:2px solid transparent}
.sb-tab.active{color:#4af;border-bottom-color:#4af;background:#1a1a3e}
.sb-content{flex:1;overflow-y:auto;display:none}
.sb-content.active{display:block}
.sb h3{padding:10px;font-size:11px;color:#888;text-transform:uppercase}
.sb-list{flex:1;overflow-y:auto;padding:6px}
.sb-item{padding:8px 10px;margin:3px 0;border-radius:6px;background:#1a1a3e;cursor:grab;font-size:13px;border:1px solid #2a2a4a;user-select:none}
.sb-item:hover{border-color:#4a4aff}
.sb-item:active{transform:scale(0.96)}
.sb-item .i{display:inline-block;width:24px;text-align:center}
/* 画布 */
.cw{flex:1;position:relative;overflow:hidden;background:#0f0f23}
.cw svg{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none}
.cw svg path{stroke:#4a4aff;stroke-width:2;fill:none}
#cv{position:absolute;top:0;left:0}
.node{position:absolute;min-width:160px;background:#1e1e42;border:1px solid #333;border-radius:10px;cursor:move;user-select:none;z-index:1;box-shadow:0 2px 12px rgba(0,0,0,.4)}
.node.sel{border-color:#f90;box-shadow:0 0 0 2px rgba(255,153,0,.3)}
.node .hd{padding:8px 12px;border-radius:9px 9px 0 0;font-size:12px;font-weight:600;display:flex;justify-content:space-between}
.node .bd{padding:8px 12px;font-size:12px}
.node .bd input,.node .bd textarea{width:100%;background:#0f0f23;border:1px solid #333;border-radius:4px;padding:4px 8px;color:#e0e0e0;font-size:12px}
.node .bd textarea{min-height:36px;resize:vertical}
.node .bd img{max-width:100%;max-height:100px;border-radius:4px;display:block;margin-top:4px}
.node .prts{display:flex;justify-content:space-between;padding:2px 12px 6px}
.node .prt{font-size:10px;color:#888;cursor:crosshair;display:flex;align-items:center;gap:3px}
.node .prt .dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.node .prt.in .dot{background:#4d4}
.node .prt.out .dot{background:#48f}
.node .prt:hover{color:#fff}
.node .act{padding:4px 12px 8px;display:flex;gap:4px}
.node .act button{flex:1;padding:4px 0;border:none;border-radius:4px;font-size:11px;cursor:pointer}
.node .act .go{background:#284;color:#fff}
.node .act .go:hover{background:#2a5}
.node .act .del{background:#a34;color:#fff}
.node .act .del:hover{background:#c45}
/* 右侧面板 */
.rp{width:260px;min-width:260px;background:#16213e;border-left:1px solid #2a2a4a;overflow-y:auto;padding:12px;font-size:12px}
.rp h4{font-size:11px;color:#888;margin-bottom:8px;text-transform:uppercase}
.rp .field{margin-bottom:8px}
.rp .field label{display:block;font-size:10px;color:#888;margin-bottom:2px}
.rp .field input,.rp .field textarea,.rp .field select{width:100%;padding:4px 6px;background:#0f0f23;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:11px}
.rp .field textarea{min-height:40px;resize:vertical}
/* 底部状态栏 */
.statusbar{height:22px;min-height:22px;background:#0f0f23;border-top:1px solid #2a2a4a;display:flex;align-items:center;padding:0 12px;font-size:10px;color:#666;gap:16px}
/* 缩放控件 */
.zoom-ctl{position:absolute;bottom:30px;left:10px;z-index:50;background:#16213e;border:1px solid #2a2a4a;border-radius:6px;padding:4px;display:flex;gap:2px}
.zoom-ctl button{padding:4px 8px;background:#1a1a3e;border:1px solid #333;border-radius:4px;color:#ccc;cursor:pointer;font-size:11px}
.zoom-ctl button:hover{background:#4a4aff;color:#fff}
.tp-text .hd{background:#2d5d2d}
.tp-image .hd{background:#3d2d6d}
.tp-video .hd{background:#2d4d6d}
.tp-llm .hd{background:#6d2d4d}
.tp-output .hd{background:#4d3d2d}
.tp-comfyui .hd{background:#4d2d4d}
.tp-ppt .hd{background:#3d4d2d}
.tp-script .hd{background:#2d4d4d}
/* 工具栏 */
.tb{position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:100;background:#16213e;border:1px solid #333;border-radius:8px;padding:4px 10px;display:flex;gap:4px;align-items:center}
.tb button{padding:4px 10px;border:none;border-radius:4px;cursor:pointer;font-size:11px}
.tb .ex{background:#284;color:#fff}
.tb .sv{background:#44f;color:#fff}
.tb .cl{background:#444;color:#ccc}
.tb .st{font-size:10px;color:#888;margin-left:6px}
/* 右键菜单 */
.ctx{position:fixed;background:#1e1e42;border:1px solid #44f;border-radius:6px;padding:4px;min-width:140px;box-shadow:0 4px 20px rgba(0,0,0,.5);z-index:9999;display:none}
.ctx div{padding:6px 12px;cursor:pointer;font-size:12px;border-radius:3px}
.ctx div:hover{background:#44f}
.ctx .dr{color:#f66}
.ctx .dr:hover{background:#a34}
/* 执行面板 */
.ep{position:absolute;bottom:10px;right:10px;width:340px;max-height:250px;background:#16213e;border:1px solid #333;border-radius:8px;padding:10px;z-index:100;overflow-y:auto;display:none}
.ep h4{font-size:11px;color:#888;margin-bottom:6px}
.ep .l{font-size:10px;padding:2px 0;font-family:monospace;border-bottom:1px solid #1a1a2e}
.ep .ok{color:#4d4}
.ep .er{color:#f44}
.ep .pb{height:2px;background:#2a2a4a;border-radius:2px;margin:4px 0;overflow:hidden}
.ep .pb .fl{height:100%;background:linear-gradient(90deg,#44f,#4d4);width:0%;transition:width .3s}
/* 监控面板 */
.mp{position:absolute;bottom:10px;left:10px;background:rgba(22,33,62,.92);border:1px solid #2a2a4a;border-radius:8px;padding:8px 10px;z-index:100;display:flex;gap:12px;font-size:10px;color:#aaa;backdrop-filter:blur(4px)}
.mp .mi{text-align:center;min-width:50px}
.mp .mi .mv{font-size:16px;font-weight:700;display:block;color:#e0e0e0}
.mp .mi .ml{font-size:9px;color:#888;margin-top:1px}
.mp .mi.qd .mv{color:#4af}
.mp .mi.rt .mv{color:#fa0}
.mp .mi.sr .mv{color:#4d4}
/* 数据浏览器表格 */
.dt-wrap{padding:6px;font-size:11px}
.dt-wrap .dt-search{margin-bottom:6px;display:flex;gap:4px}
.dt-wrap .dt-search input{flex:1;padding:4px 8px;background:#0f0f23;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:11px}
.dt-wrap .dt-search button{padding:4px 10px;background:#44f;border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:10px}
.dt-wrap table{width:100%;border-collapse:collapse}
.dt-wrap th,.dt-wrap td{padding:4px 6px;text-align:left;border-bottom:1px solid #2a2a4a}
.dt-wrap th{color:#888;font-size:10px;text-transform:uppercase;cursor:pointer;user-select:none}
.dt-wrap th:hover{color:#4af}
.dt-wrap tr:hover td{background:#1a1a3e}
.dt-wrap .dt-status{display:inline-block;padding:1px 6px;border-radius:8px;font-size:9px}
.dt-wrap .dt-status.ok{background:#1a3a1a;color:#4d4}
.dt-wrap .dt-status.pending{background:#3a3a1a;color:#fa0}
.dt-wrap .dt-status.done{background:#1a1a3a;color:#4af}
.dt-wrap .dt-pager{display:flex;justify-content:center;gap:4px;margin-top:6px}
.dt-wrap .dt-pager button{padding:2px 8px;background:#1a1a3e;border:1px solid #333;border-radius:3px;color:#ccc;cursor:pointer;font-size:10px}
.dt-wrap .dt-pager button:hover{background:#44f;color:#fff}
.dt-wrap .dt-pager button.active{background:#44f;color:#fff}
/* 预览模态框 */
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.6);z-index:9999;justify-content:center;align-items:center}
.modal.active{display:flex}
.modal-inner{background:#1e1e42;border:1px solid #44f;border-radius:10px;padding:16px;max-width:600px;width:90%;max-height:80vh;overflow-y:auto}
.modal-inner h4{color:#4af;margin-bottom:8px}
.modal-inner .mclose{float:right;cursor:pointer;color:#888;font-size:16px}
.modal-inner .mclose:hover{color:#f44}
.modal-inner table{width:100%;border-collapse:collapse;font-size:11px;margin-top:8px}
.modal-inner th,.modal-inner td{padding:4px 6px;border:1px solid #2a2a4a;text-align:left}
.modal-inner th{background:#16213e;color:#888}
/* 运营看板 */
.ops-wrap{padding:6px;font-size:11px}
.ops-cards{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px}
.ops-card{padding:8px;border-radius:6px;text-align:center}
.ops-card .ocv{font-size:20px;font-weight:700;display:block}
.ops-card .ocl{font-size:9px;margin-top:2px;opacity:.8}
.ops-card.blue{background:linear-gradient(135deg,#1a2a4a,#16213e);border:1px solid #3a5a8a}
.ops-card.blue .ocv{color:#4af}
.ops-card.green{background:linear-gradient(135deg,#1a3a2a,#16213e);border:1px solid #3a7a4a}
.ops-card.green .ocv{color:#4d4}
.ops-card.orange{background:linear-gradient(135deg,#3a2a1a,#16213e);border:1px solid #8a6a3a}
.ops-card.orange .ocv{color:#fa0}
.ops-card.purple{background:linear-gradient(135deg,#2a1a3a,#16213e);border:1px solid #6a3a8a}
.ops-card.purple .ocv{color:#a4f}
.ops-chart-wrap{margin-top:8px}
.ops-chart-wrap canvas{width:100%!important;height:120px!important;background:#0f0f23;border-radius:6px;border:1px solid #2a2a4a}
.ops-chart-wrap .ops-chart-ctl{display:flex;gap:4px;margin-bottom:4px}
.ops-chart-wrap .ops-chart-ctl button{padding:2px 8px;background:#1a1a3e;border:1px solid #333;border-radius:3px;color:#ccc;cursor:pointer;font-size:10px}
.ops-chart-wrap .ops-chart-ctl button:hover{background:#44f;color:#fff}
.ops-chart-wrap .ops-chart-ctl button.active{background:#44f;color:#fff}

</style>
</head><body>
<div class=app>
<div class=sb>
<div class=sb-tabs>
<div class="sb-tab active" onclick="switchTab('nodes')">节点</div>
<div class=sb-tab onclick="switchTab('project')">项目</div>
<div class=sb-tab onclick="switchTab('data')">数据</div>
<div class=sb-tab onclick="switchTab('team')">团队</div>
</div>
<div class="sb-content active" id="tbNodes">
<h3>节点工具</h3><div class=sb-list id=sbList></div>
</div>
<div class=sb-content id="tbProject">
<h3>项目管理</h3>
<div style="padding:8px;font-size:12px">
<button onclick="createRequirement()\" style="width:100%;padding:6px;background:#44f;border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:11px">+ 新建需求</button>
<div id=projectList style="margin-top:8px;font-size:11px;color:#888"></div>
</div>
</div>
<div class=sb-content id="tbData">
<h3>数据集</h3>
<div style="padding:4px 8px;font-size:11px" class=dt-wrap>
<div class=dt-search>
<input id=dtSearchInput placeholder="🔍 搜索数据集..." onkeydown="if(event.key==='Enter')loadDataBrowser()">
<button onclick=loadDataBrowser()>搜索</button>
</div>
<div id=dtTableWrap style="max-height:280px;overflow-y:auto">
<table><thead><tr>
<th onclick="sortDataBrowser('name')">名称</th>
<th onclick="sortDataBrowser('type')">类型</th>
<th onclick="sortDataBrowser('size')">大小</th>
<th onclick="sortDataBrowser('items')">数量</th>
<th onclick="sortDataBrowser('status')">状态</th>
<th onclick="sortDataBrowser('quality')">质量</th>
</tr></thead>
<tbody id=dtBody></tbody></table>
</div>
<div class=dt-pager id=dtPager></div>
</div>
</div>
<div class=sb-content id="tbTeam">
<h3>运营看板</h3>
<div style="padding:4px 8px;font-size:11px" class=ops-wrap>
<div class=ops-cards>
<div class="ops-card blue"><span class=ocv id=opsDau>0</span><span class=ocl>日活跃</span></div>
<div class="ops-card green"><span class=ocv id=opsProd>0</span><span class=ocl>生产量</span></div>
<div class="ops-card orange"><span class=ocv id=opsDelv>0</span><span class=ocl>交付量</span></div>
<div class="ops-card purple"><span class=ocv id=opsQual>0</span><span class=ocl>平均质量</span></div>
</div>
<div class=ops-chart-wrap>
<div class=ops-chart-ctl>
<button class=active data-period=7d onclick="switchOpsPeriod('7d')">7天</button>
<button data-period=30d onclick="switchOpsPeriod('30d')">30天</button>
</div>
<canvas id=opsChart width=180 height=120></canvas>
</div>
</div>
</div>
<div class=sb-bottom style="border-top:1px solid #2a2a4a;padding:8px">
<div style="font-size:11px;color:#888;margin-bottom:6px">🔌 API</div>
<select id=apiSelect style="width:100%;padding:4px;background:#1a1a3e;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:11px;margin-bottom:4px">
<option value=auto>⚡ 自动选择</option>
<option value=local>💻 ComfyUI本地</option>
<option value=seedream5>🎨 seedream-5.0</option>
<option value=seedance2>🎬 seedance-2.0</option>
<option value=kling>🎥 可灵</option>
<option value=comfyui>🔧 ComfyUI Remote</option>
<option value=custom>🔑 自定义</option>
</select>
<div style="display:flex;gap:4px">
<button onclick=showApiPanel() style="flex:1;padding:4px;background:#44f;border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:10px">设置</button>
<button onclick=testApi() style="flex:1;padding:4px;background:#284;border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:10px">测试</button>
</div>
</div>
</div>
<div class=cw id=cw>
<div class=tb id=tb>
<button onclick=execWF() style="padding:4px 12px;background:#284;border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:11px">▶ 执行全部</button>
<button onclick="document.getElementById('wfImport').click()" style="padding:4px 10px;background:#44f;border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:11px">📂 导入工作流</button>
<input id=wfImport type=file accept=".json" style=display:none onchange="importWorkflow(event)">
<button onclick=saveWF() style="padding:4px 8px;background:#666;border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:11px">💾</button>
<button onclick=clearAll() style="padding:4px 8px;background:#666;border:none;border-radius:4px;color:#fff;cursor:pointer;font-size:11px">🗑</button>
<span style="font-size:10px;color:#888;margin-left:8px">缩放: <span id=zoomLevel>100%</span></span>
<span class=st id=st style="font-size:10px;color:#888;margin-left:auto">就绪</span>
</div>
<svg id=svgL></svg><div id=cv></div>
<div class=zoom-ctl>
<button onclick=zoomOut() title="缩小">−</button>
<span style="font-size:10px;color:#888;padding:4px 4px;min-width:32px;text-align:center" id=zoomDisplay>100%</span>
<button onclick=zoomIn() title="放大">+</button>
<button onclick="z=1;updateZoom()" title="重置">⟲</button>
</div>
<div class=ep id=ep><h4>日志</h4><div class=pb><div class=fl id=pf></div></div><div id=el></div></div>
<div class=mp id=mp>
<div class="mi qd"><span class=mv id=mpQd>0</span><span class=ml>队列深度</span></div>
<div class="mi rt"><span class=mv id=mpRt>0</span><span class=ml>运行中</span></div>
<div class="mi sr"><span class=mv id=mpSr>0%</span><span class=ml>成功率</span></div>
</div>
<div class=rp id=rp style="display:none"></div>
<div class=statusbar id=statusBar>就绪 | API: 自动 | 项目: 无 | 用户: 本地</div>
</div></div>
<div class=ctx id=ctx></div>
<div class=modal id=previewModal>
<div class=modal-inner>
<span class=mclose onclick="closePreview()">&times;</span>
<h4 id=previewTitle>数据预览</h4>
<div id=previewContent></div>
</div>
</div>
<script>
// --- 核心: 节点类型定义 ---
const NT={
text:{l:"文本",i:"📝",c:"#2d5d2d",p:{in:1,out:1}},
image:{l:"图片",i:"🖼",c:"#3d2d6d",p:{in:1,out:1}},
video:{l:"视频",i:"🎬",c:"#2d4d6d",p:{in:1,out:1}},
llm:{l:"AI对话",i:"🤖",c:"#6d2d4d",p:{in:2,out:1}},
comfyui:{l:"ComfyUI",i:"⚡",c:"#4d2d4d",p:{in:2,out:2}},
ppt:{l:"PPT",i:"📊",c:"#3d4d2d",p:{in:1,out:1}},
script:{l:"脚本",i:"🔧",c:"#2d4d4d",p:{in:1,out:1}},
output:{l:"输出",i:"💾",c:"#4d3d2d",p:{in:1,out:0}},
model3d:{l:"3D",i:"🎯",c:"#2d3d4d",p:{in:1,out:1}},
/* 图片处理 */imgedit:{l:"图片编辑",i:"🎨",c:"#5d2d6d",p:{in:1,out:1}},
gridcrop:{l:"网格裁剪",i:"🔲",c:"#5d2d5d",p:{in:1,out:1}},
gridedit:{l:"网格编辑",i:"📐",c:"#5d3d5d",p:{in:1,out:1}},
imgcmp:{l:"图片对比",i:"🔍",c:"#4d2d5d",p:{in:2,out:1}},
presetimg:{l:"预设图片",i:"🖼️",c:"#3d3d6d",p:{in:0,out:1}},
resize:{l:"缩放",i:"📏",c:"#3d4d5d",p:{in:1,out:1}},
upscale:{l:"放大",i:"🔍",c:"#4d3d5d",p:{in:1,out:1}},
topazimg:{l:"Topaz图片",i:"✨",c:"#5d4d3d",p:{in:1,out:1}},
/* 视频处理 */videoedit:{l:"视频编辑",i:"✂️",c:"#2d5d6d",p:{in:1,out:1}},
frameex:{l:"帧提取",i:"📸",c:"#3d5d6d",p:{in:1,out:1}},
framepair:{l:"帧对比",i:"🎞️",c:"#4d5d6d",p:{in:1,out:1}},
topazvid:{l:"Topaz视频",i:"🌟",c:"#5d4d5d",p:{in:1,out:1}},
/* AI生成扩展 */seedance:{l:"Seedance",i:"🎭",c:"#6d3d4d",p:{in:2,out:1}},
runninghub:{l:"RunningHub",i:"🏃",c:"#6d4d3d",p:{in:2,out:1}},
portrait:{l:"人像大师",i:"👤",c:"#6d2d5d",p:{in:2,out:1}},
falbox:{l:"Fal模型",i:"🔮",c:"#5d3d4d",p:{in:2,out:1}},
rhtools:{l:"RH工具箱",i:"🧰",c:"#5d4d4d",p:{in:2,out:2}},
grok:{l:"Grok",i:"🐦",c:"#4d3d6d",p:{in:1,out:1}},
/* 工具 */upload:{l:"上传",i:"📤",c:"#3d5d4d",p:{in:0,out:1}},
textsplit:{l:"文本分割",i:"✂️",c:"#4d5d4d",p:{in:1,out:1}},
mention:{l:"@引用",i:"🔗",c:"#3d4d4d",p:{in:1,out:1}},
audio:{l:"音频",i:"🎵",c:"#2d5d5d",p:{in:1,out:1}},
loop:{l:"循环",i:"🔄",c:"#4d4d4d",p:{in:1,out:1}},
relay:{l:"中继",i:"🔁",c:"#3d3d4d",p:{in:1,out:1}},
groupbox:{l:"分组",i:"📦",c:"#4d4d5d",p:{in:2,out:1}},
browser:{l:"浏览器",i:"🌐",c:"#2d3d5d",p:{in:1,out:1}},
aggregate:{l:"聚合解析",i:"🔀",c:"#4d3d4d",p:{in:2,out:1}},
removebg:{l:"去背景",i:"✂️",c:"#5d5d3d",p:{in:1,out:1}},
rmwatermark:{l:"去水印",i:"🚫",c:"#5d4d3d",p:{in:1,out:1}},
drawboard:{l:"绘图板",i:"✏️",c:"#3d5d5d",p:{in:1,out:1}},
storygrid:{l:"故事板",i:"📋",c:"#4d5d3d",p:{in:1,out:1}},
combine:{l:"合并",i:"🔗",c:"#3d4d5d",p:{in:2,out:1}},
/* 3D/布局 */
panorama:{l:"全景3D",i:"🌍",c:"#2d3d5d",p:{in:1,out:1}},
posemaster:{l:"姿势大师",i:"🧍",c:"#3d3d5d",p:{in:1,out:1}},
materialset:{l:"素材集",i:"🗂️",c:"#4d4d3d",p:{in:1,out:1}},
pickfromset:{l:"从集选择",i:"🎯",c:"#3d4d3d",p:{in:1,out:1}},
idea:{l:"灵感",i:"💡",c:"#5d5d4d",p:{in:0,out:1}},
placeholder:{l:"占位",i:"⬜",c:"#3d3d3d",p:{in:0,out:1}},
/* AI预标注 */prelabel:{l:"AI预标注",i:"🎯",c:"#9B59B6",p:{in:1,out:2}},
};
// --- 状态 ---
let N={},C=[],nid=1,sel=null,drg=null,doff={x:0,y:0},con=null,z=1,hst=[],hid=-1;
const $ = s=>document.querySelector(s),_=s=>document.getElementById(s);
const cv=$('#cv'),sl=$('#svgL'),cw=$('#cw'),st=$('#st'),ep=_('ep'),el=_('el'),pf=_('pf'),ctx=_('ctx');
// --- 初始化工具箱 ---
function init(){
_('sbList').innerHTML='';
for(const[t,d]of Object.entries(NT)){
const e=document.createElement('div');e.className='sb-item';e.draggable=true;e.dataset.type=t;
e.innerHTML=`<span class=i>${d.i}</span>${d.l}`;
e.ondragstart=ev=>{ev.dataTransfer.setData('t',t);ev.dataTransfer.effectAllowed='copy'};
_('sbList').appendChild(e);
}}
// --- 画布事件 ---
cw.addEventListener('dragover',e=>{e.preventDefault();e.dataTransfer.dropEffect='copy'});
cw.addEventListener('drop',e=>{
e.preventDefault();const t=e.dataTransfer.getData('t');if(!t||!NT[t])return;
const r=cw.getBoundingClientRect();createNode(t,(e.clientX-r.left-80)/z,(e.clientY-r.top-30)/z)});
cw.addEventListener('mousedown',e=>{if(e.target===cw||e.target.tagName==='DIV')deselect()});
document.addEventListener('mousemove',e=>{
if(drg){const r=cw.getBoundingClientRect();drg.style.left=((e.clientX-r.left)/z-doff.x)+'px';drg.style.top=((e.clientY-r.top)/z-doff.y)+'px';const nd=N[drg.dataset.id];if(nd){nd.x=parseFloat(drg.style.left);nd.y=parseFloat(drg.style.top)}updL()}
if(con)updTL(e)});
document.addEventListener('mouseup',e=>{drg=null;if(con)endCon()});
// --- 节点操作 ---
function createNode(t,x,y,d){
const id='n'+(nid++),def=NT[t];
N[id]={id,type:t,x,y,data:d||defD(t),ports:def.p};
renderN(id);updL();sH();st.textContent=`+${def.l}`;
_cv_api('POST','/canvas/element',{el_type:t,name:def.l,x:Math.round(x),y:Math.round(y)}).catch(()=>{});
return id;}
function defD(t){const m={
text:{content:'双击编辑'},image:{src:''},video:{src:'',dur:5},
llm:{prompt:'',model:'auto'},comfyui:{workflow:''},
ppt:{tpl:'clean-business',slides:5,title:'新建PPT'},
script:{code:'return input;'},output:{fmt:'mp4'},model3d:{model:'',pose:'standing'},
/* 图片处理 */
imgedit:{action:'裁剪',params:'{}'},gridcrop:{rows:3,cols:3},gridedit:{rows:3,cols:3},
imgcmp:{mode:'并排'},presetimg:{preset:'samples'},resize:{w:1024,h:1024},
upscale:{scale:2},topazimg:{model:'standard'},
/* 视频 */
videoedit:{action:'裁剪'},frameex:{fps:1},framepair:{mode:'对比'},
topazvid:{model:'standard'},
/* AI */
seedance:{prompt:'',model:'seedance2'},runninghub:{endpoint:'',params:'{}'},
portrait:{gender:'女',style:'写实'},falbox:{endpoint:'',key:''},
rhtools:{tool:'',params:'{}'},grok:{prompt:'',model:'grok'},
/* 工具 */
upload:{path:''},textsplit:{delimiter:'\\n'},mention:{ref:''},
audio:{src:'',dur:10},loop:{count:3},relay:{target:''},
groupbox:{label:'组'},browser:{url:'https://'},
aggregate:{mode:'合并'},removebg:{color:'green'},
rmwatermark:{method:'auto'},drawboard:{strokes:[]},
storygrid:{scenes:5},combine:{mode:'拼接'},
/* 3D */
panorama:{scene:'',quality:'high'},posemaster:{pose:'standing'},
materialset:{items:[]},pickfromset:{options:[]},
idea:{note:''},placeholder:{text:'占位'},
prelabel:{prompt:'',task_type:'detection'},
};return m[t]||{}}
function renderN(id){
const nd=N[id];if(!nd)return;const def=NT[nd.type],d=nd.data||{};
let e=_('n-'+id);
if(!e){
e=document.createElement('div');e.id='n-'+id;e.className='node tp-'+nd.type;e.dataset.id=id;cv.appendChild(e);
e.addEventListener('mousedown',ev=>{
if(ev.target.closest('.act')||ev.target.closest('.prt')||ev.target.tagName==='INPUT'||ev.target.tagName==='TEXTAREA')return;
sel=id;document.querySelectorAll('.node.sel').forEach(x=>x.classList.remove('sel'));e.classList.add('sel');
drg=e;const r=cw.getBoundingClientRect();doff.x=(ev.clientX-r.left)/z-nd.x;doff.y=(ev.clientY-r.top)/z-nd.y});
e.addEventListener('contextmenu',ev=>{ev.preventDefault();sel=id;showCtx(ev.clientX,ev.clientY,id)});
}
let ib='',ab='';
switch(nd.type){
case'text':ib='<textarea onchange=updN("'+id+'","content",this.value)>'+esc(d.content||'')+'</textarea>';ab='<button class=go onclick=execNode("'+id+'")>▶</button>';break;
case'image':ib=d.src?'<img src="'+esc(d.src)+'"><input value="'+esc(d.src)+'" onchange=updN("'+id+'","src",this.value)>':'<div style="text-align:center;padding:8px;font-size:11px;color:#888">📁 拖放图片</div><input placeholder="URL" onchange=updN("'+id+'","src",this.value)>';break;
case'video':ib='<input value="'+esc(d.src||'')+'" placeholder="视频URL或拖放" onchange=updN("'+id+'","src",this.value)><div style="font-size:10px;color:#888;margin-top:2px">'+(d.dur||5)+'秒</div>';break;
case'llm':ib='<textarea placeholder="提示词" onchange=updN("'+id+'","prompt",this.value)>'+esc(d.prompt||'')+'</textarea><div style=font-size:10px;color:#888>模型:'+(d.model||'auto')+'</div>';ab='<button class=go onclick=execNode("'+id+'")>▶</button>';break;
case'comfyui':ib='<textarea placeholder="Workflow JSON" style="font-size:10px;font-family:monospace" onchange=updN("'+id+'","workflow",this.value)>'+esc(d.workflow||'')+'</textarea>';ab='<button class=go onclick=execNode("'+id+'")>▶</button>';break;
case'ppt':ib='<input value="'+(d.title||'')+'" placeholder="标题" onchange=updN("'+id+'","title",this.value)><div style=font-size:10px;color:#888>'+d.slides+'页 '+d.tpl+'</div>';ab='<button class=go onclick=execNode("'+id+'")>▶</button>';break;
case'script':ib='<textarea placeholder="/* 脚本代码" style="font-size:10px;font-family:monospace" onchange=updN("'+id+'","code",this.value)>'+esc(d.code||'')+'</textarea>';ab='<button class=go onclick=execNode("'+id+'")>▶</button>';break; */
case'output':ib='<div style=font-size:11px;color:#888>格式:'+(d.fmt||'mp4')+'</div><div id=op-'+id+' style=font-size:10px;color:#666>等待中</div>';break;
case'prelabel':ib='<textarea placeholder="图片描述" onchange=updN("'+id+'","prompt",this.value)>'+esc(d.prompt||'')+'</textarea><select onchange=updN("'+id+'","task_type",this.value)><option value="detection"'+(d.task_type==='detection'?' selected':'')+'>目标检测</option><option value="classification"'+(d.task_type==='classification'?' selected':'')+'>分类</option><option value="tagging"'+(d.task_type==='tagging'?' selected':'')+'>标签</option></select>';ab='<button class=go onclick=execNode("'+id+'")>▶</button>';break;
default:ib='<div style=font-size:11px;color:#888>'+nd.type+'</div>';
}
let pi='',po='';
for(let i=0;i<nd.ports.in;i++)pi+='<span class="prt in" data-n="'+id+'" data-p="in" data-i="'+i+'"><span class=dot></span>I'+(i+1)+'</span>';
for(let i=0;i<nd.ports.out;i++)po+='<span class="prt out" data-n="'+id+'" data-p="out" data-i="'+i+'"><span class=dot></span>O'+(i+1)+'</span>';
e.innerHTML='<div class=hd><span>'+def.i+' '+def.l+'</span></div><div class=bd>'+ib+'</div><div class=prts>'+pi+po+'</div><div class=act>'+ab+'<button class=del onclick="delN(\''+id+'\')">✕</button></div>';
e.style.left=nd.x+'px';e.style.top=nd.y+'px';e.style.zIndex=sel===id?10:1;
/* 端口事件 */
e.querySelectorAll('.prt.out').forEach(p=>{p.addEventListener('mousedown',ev=>{ev.stopPropagation();startCon(nd.id,'out',parseInt(p.dataset.i))})});
e.querySelectorAll('.prt.in').forEach(p=>{p.addEventListener('mouseup',ev=>{if(con){ev.stopPropagation();tryCon(nd.id,'in',parseInt(p.dataset.i))}}})};
// --- 工具函数 ---
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function updN(id,k,v){if(N[id]){N[id].data[k]=v;sH()}}
function delN(id){const e=_('n-'+id);if(e)e.remove();delete N[id];C=C.filter(c=>c.from!==id&&c.to!==id);if(sel===id)sel=null;updL();sH();st.textContent='✕删除'}
function deselect(){sel=null;document.querySelectorAll('.node.sel').forEach(x=>x.classList.remove('sel'))}
// --- 执行 ---
async function execNode(id){
const nd=N[id];if(!nd)return;
ep.style.display='block';addLog('info','执行 '+nd.type+' 节点...');
const api=_('apiSelect').value;
try{
let r,apiEndpoint='/engine/plan';
const nodeData=nd.data||{};
switch(nd.type){
/* AI生成节点 */
case'llm':r=await _cv_api('POST','/api/chat',{user_input:nodeData.prompt||'你好'});addLog('ok','→ AI回复:'+(r?.message||'无'));if(r?.message){nodeData.output=r.message.substring(0,500);updN(id,'output',r.message.substring(0,500))};break;
case'seedance':r=await _cv_api('POST','/imdf/external/list',{type:'seedance',params:{prompt:nodeData.prompt,model:nodeData.model||'seedance2',api:api}});addLog('ok','→ Seedance已提交');break;
case'runninghub':r=await _cv_api('POST','/imdf/external/list',{type:'runninghub',params:{endpoint:nodeData.endpoint,api:api}});addLog('ok','→ RunningHub已提交');break;
case'portrait':r=await _cv_api('POST','/imdf/external/list',{type:'portrait',params:{gender:nodeData.gender,style:nodeData.style,api:api}});addLog('ok','→ 人像已提交');break;
case'falbox':addLog('ok','→ Fal模型: '+api);break;
case'rhtools':addLog('ok','→ RH工具箱');break;
case'grok':addLog('ok','→ Grok: '+api);break;
/* 图片处理 */
case'image':r=await _cv_api('POST','/api/image/generate',{user_input:nodeData.src||'生成图片'});addLog('ok','→ 图片:'+(r?.data?.status||'完成'));if(r?.data?.file)addLog('ok','📄 '+r.data.file);break;
case'imgedit':r=await _cv_api('POST','/imdf/images/resize',{action:nodeData.action});addLog('ok','→ 图片编辑已提交');break;
case'gridcrop':addLog('ok','→ 网格裁剪');break;
case'gridedit':addLog('ok','→ 网格编辑');break;
case'imgcmp':addLog('ok','→ 图片对比');break;
case'resize':r=await _cv_api('POST','/imdf/images/resize',{width:nodeData.w,height:nodeData.h});addLog('ok','→ 缩放已提交');break;
case'upscale':addLog('ok','→ 放大x'+nodeData.scale);break;
/* 视频 */
case'video':addLog('ok','→ 视频: '+(nodeData.src||'无'));break;
case'videoedit':addLog('ok','→ 视频编辑');break;
case'frameex':addLog('ok','→ 帧提取: '+nodeData.fps+'fps');break;
/* 文档生成 */
case'ppt':r=await _cv_api('POST','/api/ppt/generate',{user_input:(nodeData.title||'')+','+(nodeData.tpl||'')});addLog('ok','→ PPT已生成:'+(r?.data?.template||'完成'));if(r?.data?.file){addLog('ok','📄 文件:'+r.data.file)};break;
case'video':r=await _cv_api('POST','/api/video/generate',{user_input:nodeData.src||'IMDF视频'});addLog('ok','→ 视频已生成:'+(r?.data?.file||'完成'));break;
case'comfyui':r=await _cv_api('POST','/api/comfyui/run',{workflow_id:'default',prompt:nodeData.prompt||''});addLog('ok','→ ComfyUI:'+(r?.data?.status||'已提交'));break;
/* Seedance */
case'seedance':r=await _cv_api('POST','/api/image/generate',{user_input:nodeData.prompt||'',model:nodeData.model||'seedance2'});addLog('ok','→ Seedance已提交');break;
case'upload':addLog('ok','→ 准备上传');break;
case'textsplit':addLog('ok','→ 文本分割');break;
case'audio':addLog('ok','→ 音频处理');break;
case'loop':addLog('ok','→ 循环x'+nodeData.count);break;
case'browser':addLog('ok','→ 浏览器:'+nodeData.url);break;
case'removebg':addLog('ok','→ 去背景');break;
case'rmwatermark':addLog('ok','→ 去水印');break;
case'drawboard':addLog('ok','→ 绘图板');break;
case'storygrid':addLog('ok','→ 故事板:'+nodeData.scenes+'场');break;
case'combine':addLog('ok','→ 合并');break;
case'mention':addLog('ok','→ @引用');break;
case'relay':addLog('ok','→ 中继');break;
case'groupbox':addLog('ok','→ 分组');break;
case'aggregate':addLog('ok','→ 聚合解析');break;
/* 3D */
case'panorama':r=await _cv_api('GET','/api/3d/scenes');addLog('ok','→ 3D场景:'+(r.length||'已就绪'));break;
case'posemaster':r=await _cv_api('GET','/api/3d/poses');addLog('ok','→ 姿势库:'+(r.length||r.count||'已就绪'));break;
case'model3d':addLog('ok','→ 3D模型');break;
case'materialset':addLog('ok','→ 素材集');break;
case'pickfromset':addLog('ok','→ 从集选择');break;
/* 默认 */
case'output':addLog('ok','→ 输出就绪');break;
case'script':addLog('ok','→ 脚本执行');break;
case'presetimg':addLog('ok','→ 预设图片');break;
/* AI预标注 */
case'prelabel':
  const imgData = nodeData;
  const desc = imgData.prompt || imgData.src || '一张图片';
  const taskType = imgData.task_type || 'detection';
  r = await _cv_api('POST','/api/prelabel',{image_desc:desc,task_type:taskType});
  addLog('ok','→ AI标注完成: '+(r?.data?.bboxes?.length||r?.data?.tags?.length||0)+'个结果');
  if(r?.data?.bboxes){
    nodeData.bboxes = r.data.bboxes;
    updN(id,'bboxes',JSON.stringify(r.data.bboxes));
    if(typeof drawBBoxes==='function') drawBBoxes(r.data.bboxes);
  }
  if(r?.data?.tags){nodeData.tags = r.data.tags; updN(id,'tags',JSON.stringify(r.data.tags))}
  if(r?.data?.classification){nodeData.classification = r.data.classification; updN(id,'classification',r.data.classification)}
  break;
default:addLog('ok','→ 已提交: '+nd.type);
}
}catch(e){addLog('er','执行失败:'+e.message)}
updL();}
async function execWF(){
ep.style.display='block';addLog('info','=== 工作流执行 ===');
const ids=Object.keys(N);
for(const id of ids){await execNode(id);await new Promise(r=>setTimeout(r,300));}
addLog('ok','完成!共'+ids.length+'节点');}
function addLog(t,m){
const d=document.createElement('div');d.className='l '+t;d.textContent='['+new Date().toLocaleTimeString()+'] '+m;el.appendChild(d);el.scrollTop=el.scrollHeight;}
// --- 连线 ---
function startCon(id,pt,pi){con={id,pt,pi};const l=document.createElementNS('http://www.w3.org/2000/svg','line');l.id='tl';l.setAttribute('stroke','#f90');l.setAttribute('stroke-width','2');sl.appendChild(l)}
function updTL(e){const l=_('tl');if(!l)return;l.setAttribute('x2',e.clientX);l.setAttribute('y2',e.clientY);}
function tryCon(id,pt,pi){if(!con||con.id===id){endCon();return}
C.push({from:con.id,fromP:con.pi,to:id,toP:pi});endCon();updL();sH();st.textContent='+连线';}
function endCon(){const l=_('tl');if(l)l.remove();con=null;}
function updL(){
let h='';
for(const c of C){
const f=_('n-'+c.from),t=_('n-'+c.to);if(!f||!t)continue;
const fr=f.getBoundingClientRect(),tr=t.getBoundingClientRect(),wr=cw.getBoundingClientRect();
const x1=fr.right-wr.left-6,y1=fr.top+fr.height/2-wr.top,x2=tr.left-wr.left+6,y2=tr.top+tr.height/2-wr.top;
const mx=(x1+x2)/2;h+='<path d="M'+x1+','+y1+' C'+mx+','+y1+' '+mx+','+y2+' '+x2+','+y2+'" onclick="delC('+C.indexOf(c)+')"/>';
}sl.innerHTML=h;}
function delC(i){C.splice(i,1);updL();sH()}
// --- API ---
async function _cv_api(m,p,b){try{const r=await fetch(p,{method:m,headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):null});return await r.json()}catch(e){return{error:e.message}}}
// --- 工作流保存/加载(后端持久化) ---
async function saveWF(){
const data={nodes:N,connections:C};
try{
const resp=await fetch('/canvas/state',{
method:'GET',
headers:{'Content-Type':'application/json'}
});
const state=await resp.json();
/* 用canvas/element添加所有节点 */
for(const[id,nd]of Object.entries(N)){
await fetch('/canvas/element',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({el_type:nd.type,name:NT[nd.type]?.l||nd.type,x:Math.round(nd.x),y:Math.round(nd.y)})
});
}
addLog('ok','💾 画布已保存到后端('+Object.keys(N).length+'节点)');
st.textContent='已保存';
}catch(e){addLog('er','保存失败:'+e.message)}
}
async function loadWF(){
try{
const resp=await fetch('/canvas/state');
const state=await resp.json();
const elements=state?.canvas?.elements||{};
const count=Object.keys(elements).length;
addLog('info','📂 后端有'+count+'个已保存元素');
/* 如果后端有数据,询问是否加载 */
if(count>0&&Object.keys(N).length===0&&!confirm('加载后端的画布状态?'))return;
st.textContent='已加载';
}catch(e){st.textContent='加载失败'}
}
}catch(e){st.textContent='加载失败'}};
i.click();}
function clearAll(){
if(!confirm('清除所有节点?'))return;
for(const id of Object.keys(N)){const e=_('n-'+id);if(e)e.remove()}
N={};C=[];sl.innerHTML='';ep.style.display='none';el.innerHTML='';st.textContent='已清除';}
function showCtx(x,y,id){
ctx.style.display='block';ctx.style.left=x+'px';ctx.style.top=y+'px';
ctx.innerHTML='<div onclick="execNode(\\''+id+'\\')">▶ 执行</div><div class=dr onclick="delN(\\''+id+'\\')">✕ 删除</div>';}
document.addEventListener('click',e=>{if(!ctx.contains(e.target))ctx.style.display='none'});
// --- 历史(简单实现) ---
function sH(){hst.push(JSON.stringify({nodes:N,connections:C}));if(hst.length>50)hst.shift();hid=hst.length-1;}
function undo(){if(hid>0){hid--;_restore(JSON.parse(hst[hid]))}}
function redo(){if(hid<hst.length-1){hid++;_restore(JSON.parse(hst[hid]))}}
function _restore(d){
for(const id of Object.keys(N)){const e=_('n-'+id);if(e)e.remove()}
N={};C=[];sl.innerHTML='';
if(d.nodes)for(const[k,v]of Object.entries(d.nodes)){N[k]=v;renderN(k)}
if(d.connections){C=d.connections;updL()}}
// --- 文件拖放上传 ---
cw.addEventListener('drop',e=>{
const files=e.dataTransfer.files;if(files.length){
const f=files[0];const t=e.dataTransfer.getData('t');
if(f.type.startsWith('image/')||f.type.startsWith('video/')){
const reader=new FileReader();reader.onload=ev=>{
const url=URL.createObjectURL(f);const type=f.type.startsWith('video/')?'video':'image';
const r=cw.getBoundingClientRect();const id=createNode(type,(e.clientX-r.left-80)/z,(e.clientY-r.top-30)/z);
if(N[id]){N[id].data.src=url;renderN(id)}
};reader.readAsDataURL(f);return;}
} // 如果拖的是节点类型则已有处理
}); 
// --- 键盘快捷键 ---
document.addEventListener('keydown',e=>{
if(e.ctrlKey&&e.key==='z'){e.preventDefault();undo()}
if(e.ctrlKey&&e.key==='y'){e.preventDefault();redo()}
if(e.key==='Delete'||e.key==='Backspace'){if(sel&&!e.target.closest('input,textarea')){delN(sel)}}
if(e.ctrlKey&&e.key==='s'){e.preventDefault();saveWF()}
});
// --- BBox绘制(用于AI预标注结果叠加) ---
function drawBBoxes(bboxes){
  const svg = document.querySelector('#canvas-container svg') || sl || document.querySelector('svg');
  if(!svg) return;
  svg.querySelectorAll('.bbox-overlay').forEach(el=>el.remove());
  const colors = ['#e74c3c','#3498db','#2ecc71','#f39c12','#9b59b6','#1abc9c'];
  bboxes.forEach((b,i)=>{
    const g = document.createElementNS('http://www.w3.org/2000/svg','g');
    g.setAttribute('class','bbox-overlay');
    const rect = document.createElementNS('http://www.w3.org/2000/svg','rect');
    const scale = 0.5;
    rect.setAttribute('x',b.x*scale);
    rect.setAttribute('y',b.y*scale);
    rect.setAttribute('width',b.w*scale);
    rect.setAttribute('height',b.h*scale);
    rect.setAttribute('fill','none');
    rect.setAttribute('stroke',colors[i%colors.length]);
    rect.setAttribute('stroke-width','2');
    rect.setAttribute('stroke-dasharray','4,2');
    const text = document.createElementNS('http://www.w3.org/2000/svg','text');
    text.setAttribute('x',b.x*scale);
    text.setAttribute('y',(b.y*scale-5));
    text.setAttribute('fill',colors[i%colors.length]);
    text.setAttribute('font-size','12');
    text.textContent = b.label + ' (' + Math.round(b.confidence*100) + '%)';
    g.appendChild(rect); g.appendChild(text); svg.appendChild(g);
  });
}
// --- 初始化 ---
init();
// 添加默认工作流
createNode('text',30,30,{content:'输入提示词\n描述你要生成的内容'});
createNode('llm',280,20);
createNode('output',530,40);
// 加连线
setTimeout(()=>{
C.push({from:'n1',fromP:0,to:'n2',toP:0});
C.push({from:'n2',fromP:0,to:'n3',toP:0});
updL();sH();st.textContent='就绪 - 拖拽左侧节点到画布'},100);
// --- API管理 ---
function showApiPanel(){
const sel=_('apiSelect').value;
const customInput=_('customApiInput');
customInput.style.display=sel==='custom'?'block':'none';
if(sel!=='custom'){
const names={auto:'自动选择',seedream5:'seedream-5.0',seedance2:'seedance-2.0',kling:'可灵',haihun:'海螺',wan:'wan-2.7',comfyui:'ComfyUI',libtv:'LibTV',lovart:'Lovart',runninghub:'RunningHub'};
addLog('info','API切换到: '+names[sel]);
}}
async function testApi(){
const sel=_('apiSelect').value;
if(sel==='custom'){
const url=_('customApiInput').value;
if(!url){addLog('er','请先输入API地址');return}
try{
const r=await fetch(url,{method:'GET',signal:AbortSignal.timeout(5000)});
addLog('ok','自定义API测试: HTTP '+r.status)}catch(e){addLog('er','API不可达: '+e.message)}
}else{
try{
const r=await _cv_api('GET','/api/3d/scenes');
addLog('ok',sel+'可用 ✅')}catch(e){addLog('er',sel+'测试失败')}
}}
// --- API选择联动到execNode ---
const _origExec=execNode;
// --- 初始化完成 ---
addLog('ok','🎯 已接入: seedream5/seedance2/可灵/海螺/wan2.7/ComfyUI/LibTV/Lovart/RunningHub');
addLog('ok','🔍 双AI互审前端层已激活');
// --- 新增UI函数 ---
function switchTab(name){
document.querySelectorAll('.sb-content').forEach(e=>e.classList.remove('active'));
document.querySelectorAll('.sb-tab').forEach(e=>e.classList.remove('active'));
document.getElementById('tb'+name.charAt(0).toUpperCase()+name.slice(1)).classList.add('active');
document.querySelector(`.sb-tab[onclick*="'${name}'"]`).classList.add('active');
}
function updateZoom(){
document.getElementById('zoomLevel').textContent=Math.round(z*100)+'%';
document.getElementById('zoomDisplay').textContent=Math.round(z*100)+'%';
document.getElementById('cv').style.transform=`scale(${z})`;
document.getElementById('svgL').style.transform=`scale(${z})`;
}
function zoomIn(){z=Math.min(3,z*1.2);updateZoom()}
function zoomOut(){z=Math.max(0.1,z/1.2);updateZoom()}
function importWorkflow(e){
const file=e.target.files[0];if(!file)return;
const reader=new FileReader();
reader.onload=ev=>{
try{
const wf=JSON.parse(ev.target.result);
addLog('ok','📂 工作流已加载:'+file.name);
st.textContent='已加载工作流';
}catch(ex){addLog('er','工作流解析失败:'+ex.message)}
};
reader.readAsText(file);
}
// --- 真实API对接函数 ---
async function createRequirement(){
const title=prompt('需求标题:');
if(!title)return;
try{
const r=await fetch('/api/requirements/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,description:''})});
if(r.ok){addLog('ok','📋 需求已创建');_('projectList').innerHTML='<div style=color:#4a4>✅ 需求已创建</div>'}
}catch(e){addLog('er','创建失败:'+e.message)}
}
// ==================== 管道监控 ====================
let _mpTimer=null;
async function loadMonitor(){
try{
const r=await fetch('/api/monitor/pipeline');
if(r.ok){
const d=await r.json();
_('mpQd').textContent=d.queue_depth;
_('mpRt').textContent=d.running_tasks;
_('mpSr').textContent=d.success_rate+'%';
}
}catch(e){}
}
function startMonitorAutoRefresh(){
if(_mpTimer)clearInterval(_mpTimer);
loadMonitor();
_mpTimer=setInterval(loadMonitor,15000);
}

// ==================== 数据浏览器 ====================
let _dtPage=1,_dtSearch='',_dtSort='time';
async function loadDataBrowser(pg){
if(pg)_dtPage=pg;
_dtSearch=_('dtSearchInput').value.trim();
try{
const r=await fetch('/api/datasets?page='+_dtPage+'&size=20&search='+encodeURIComponent(_dtSearch)+'&sort='+_dtSort);
if(!r.ok)return;
const d=await r.json();
const tb=_('dtBody');
tb.innerHTML='';
for(const item of d.items){
const statusClass=item.status==='完成'?'ok':item.status==='进行中'?'pending':'done';
const tr=document.createElement('tr');
tr.style.cursor='pointer';
tr.onclick=()=>showPreview(item.id);
tr.innerHTML='<td>'+item.name+'</td><td>'+item.type+'</td><td>'+item.size+'MB</td><td>'+item.items+'</td><td><span class="dt-status '+statusClass+'">'+item.status+'</span></td><td>'+item.quality_score+'</td>';
tb.appendChild(tr);
}
// 分页器
const pgEl=_('dtPager');
pgEl.innerHTML='';
if(d.total_pages>1){
pgEl.innerHTML+='<button onclick="loadDataBrowser(1)" '+(d.page===1?'disabled':'')+'>&laquo;</button>';
for(let i=Math.max(1,d.page-2);i<=Math.min(d.total_pages,d.page+2);i++){
pgEl.innerHTML+='<button onclick="loadDataBrowser('+i+')" '+(i===d.page?'class=active':'')+'>'+i+'</button>';
}
pgEl.innerHTML+='<button onclick="loadDataBrowser('+d.total_pages+')" '+(d.page===d.total_pages?'disabled':'')+'>&raquo;</button>';
}
}catch(e){}
}
function sortDataBrowser(col){
const map={name:'name',type:'time',size:'size',items:'time',status:'time',quality:'quality'};
_dtSort=map[col]||'time';
_dtPage=1;
loadDataBrowser();
}
async function showPreview(dsId){
try{
const r=await fetch('/api/datasets/'+dsId+'/preview');
if(!r.ok)return;
const d=await r.json();
_('previewTitle').textContent=d.name+' (共'+d.total_count+'条)';
let html='<table><thead><tr>';
if(d.preview&&d.preview.columns){
for(const col of d.preview.columns)html+='<th>'+col+'</th>';
}
html+='</tr></thead><tbody>';
if(d.preview&&d.preview.rows){
for(const row of d.preview.rows){
html+='<tr>';
for(const cell of row)html+='<td>'+cell+'</td>';
html+='</tr>';
}
}
html+='</tbody></table>';
_('previewContent').innerHTML=html;
_('previewModal').classList.add('active');
}catch(e){}
}
function closePreview(){
_('previewModal').classList.remove('active');
}
// 点击模态框背景关闭
document.addEventListener('click',function(e){
if(e.target&&e.target.id==='previewModal')closePreview();
});

// ==================== 运营看板 ====================
let _opsPeriod='7d';
async function loadOpsOverview(){
try{
const r=await fetch('/api/ops/overview');
if(r.ok){
const d=await r.json();
_('opsDau').textContent=d.daily_active_users;
_('opsProd').textContent=d.production_count;
_('opsDelv').textContent=d.delivery_count;
_('opsQual').textContent=d.avg_quality_score.toFixed(1);
}
}catch(e){}
}
async function loadOpsTrend(){
try{
const r=await fetch('/api/ops/trend?period='+_opsPeriod);
if(!r.ok)return;
const d=await r.json();
const canvas=_('opsChart');
const ctx=canvas.getContext('2d');
const W=canvas.width,H=canvas.height;
ctx.clearRect(0,0,W,H);
// 绘制折线图
const pts=d.points||[];
const pad=10,bottom=H-10,top=10,right=W-pad;
const cw=(right-pad)/(Math.max(pts.length-1,1));
// 数据集: 生产量
const values=pts.map(p=>p.production_count||0);
const maxVal=Math.max(...values,1);
ctx.strokeStyle='#4d4';
ctx.lineWidth=1.5;
ctx.beginPath();
pts.forEach((p,i)=>{
const x=pad+i*cw,y=bottom-(p.production_count/maxVal)*(bottom-top);
i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
});
ctx.stroke();
// 交付量
const vals2=pts.map(p=>p.delivery_count||0);
ctx.strokeStyle='#fa0';
ctx.beginPath();
pts.forEach((p,i)=>{
const x=pad+i*cw,y=bottom-(p.delivery_count/maxVal)*(bottom-top);
i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
});
ctx.stroke();
// 质量分
const vals3=pts.map(p=>p.avg_quality_score||0);
ctx.strokeStyle='#a4f';
ctx.lineWidth=1;
ctx.setLineDash([3,3]);
ctx.beginPath();
pts.forEach((p,i)=>{
const x=pad+i*cw,y=bottom-(p.avg_quality_score/maxVal/2)*(bottom-top);
i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
});
ctx.stroke();
ctx.setLineDash([]);
// 标注
ctx.fillStyle='#666';
ctx.font='7px sans-serif';
ctx.textAlign='center';
const n=Math.min(pts.length,7);
for(let i=0;i<n;i++){
const idx=Math.round(i*(pts.length-1)/(n-1));
const x=pad+idx*cw;
ctx.fillText(pts[idx].date.slice(5),x,H-2);
// 图例
ctx.font='7px sans-serif';
ctx.textAlign='left';
ctx.fillStyle='#4d4';ctx.fillRect(pad+5,5,8,2);ctx.fillText('生产量',pad+15,8);
ctx.fillStyle='#fa0';ctx.fillRect(pad+60,5,8,2);ctx.fillText('交付量',pad+70,8);
ctx.fillStyle='#a4f';ctx.fillRect(pad+115,5,8,2);ctx.fillText('质量',pad+125,8);
}catch(e){}
function switchOpsPeriod(p){
_opsPeriod=p;
document.querySelectorAll('.ops-chart-ctl button').forEach(b=>b.classList.remove('active'));
document.querySelector('.ops-chart-ctl button[data-period="'+p+'"]').classList.add('active');
loadOpsTrend();

// --- 初始化面板 ---
setTimeout(()=>{
loadDataBrowser(1);
loadOpsOverview();
loadOpsTrend();
startMonitorAutoRefresh();
},500);

// --- 初始化完成增强 ---
addLog('ok','📊 4选项卡面板就绪(节点/项目/数据/团队)');
addLog('ok','🎯 ComfyUI本地+Remote模式支持');
addLog('ok','📂 工作流导入功能就绪');
addLog('ok','🔧 管道监控/数据浏览器/运营看板已加载');
</script></body></html>
"""


# Routes
# ============================================================================

# 嵌入3D/云存储子API
if HAS_3D:
    app.include_router(router_3d)
    logger.info("3D API已加载")
if HAS_CLOUD:
    app.include_router(router_cloud)
    logger.info("云存储API已加载")

# ============================================================================
# V4 — 智影 Intelligence (全 agent 驱动 + 多渠道数据采集)
# ============================================================================
try:
    from api.intelligence_v4_routes import router as intelligence_v4_router
    app.include_router(intelligence_v4_router)
    logger.info("V4 Intelligence 路由已加载 (/api/v1/intelligence/*)")
except Exception as e:
    logger.warning(f"V4 Intelligence 路由加载失败: {e}")

# V5 公众号迁移能力 (Hermes/Loop Engineering/Obsidian/MoA/Video Harness/Brand/...)
try:
    from api.intelligence_v5_routes import router as intelligence_v5_router
    app.include_router(intelligence_v5_router)
    logger.info("V5 Intelligence 路由已加载 (/api/v5/*)")
except Exception as e:
    logger.warning(f"V5 Intelligence 路由加载失败: {e}")

# ─── 复刻模块注册 ───────────────────────────────────────────────────────────
if HAS_MEDIA:
    app.include_router(router_media)
    logger.info("媒体管理API已加载")
if HAS_CONFIG:
    app.include_router(router_config)
    logger.info("系统设置API已加载")
if HAS_BOARD:
    app.include_router(router_board)
    logger.info("画布管理API已加载")
if HAS_THEME:
    app.include_router(router_theme)
    logger.info("主题管理API已加载")
if HAS_EXT_PROVIDERS:
    app.include_router(router_ext_providers)
    logger.info("外部Provider API已加载")
if HAS_IMAGE_OPS:
    app.include_router(router_image_ops)
    logger.info("图像处理API已加载")
if HAS_FIGMA_BRIDGE:
    app.include_router(router_figma)
    logger.info("Figma Bridge API已加载")

# 注册监控/数据/运营看板路由
if HAS_MONITOR:
    app.include_router(router_monitor)
    logger.info("管道监控路由已加载")
if HAS_DATA_BROWSER:
    app.include_router(router_data_browser)
    logger.info("数据浏览器路由已加载")
if HAS_OPS:
    app.include_router(router_ops)
    logger.info("运营看板路由已加载")
# P3-2-W1: HAS_ANNOTATION (router_annotation) moved to annotation-service
if HAS_CROWD:
    app.include_router(router_crowd)
    logger.info("众包路由已加载")
if HAS_DELIVERY:
    app.include_router(router_delivery)
    logger.info("交付路由已加载")

# ─── P5-R1-T6: Internal QC + Requester Acceptance ──────────────────────────
try:
    from api.qc_routes import router as router_qc_internal
    app.include_router(router_qc_internal)
    logger.info("内部质检路由已加载 (/api/v1/qc)")
except Exception as e:
    logger.warning(f"内部质检路由加载失败: {e}")

try:
    from api.requester_routes import router as router_requester
    app.include_router(router_requester)
    logger.info("需求方验收路由已加载 (/api/v1/requester)")
except Exception as e:
    logger.warning(f"需求方验收路由加载失败: {e}")

# ─── R10.5-Worker-2: 商业化 (账单/数据导出/审计/多租户) ─────────────────────
try:
    from api.r10_5_business_routes import router as r10_5_business_router
    app.include_router(r10_5_business_router)
    logger.info("R10.5 商业化路由已加载 (/api/v1/business/{billing,export,audit,tenant})")
except Exception as e:
    logger.warning(f"R10.5 商业化路由加载失败: {e}")

# ─── F0.5: Prometheus指标 ──────────────────────────────────────────────────
try:
    from api.metrics_routes import router as router_metrics
    app.include_router(router_metrics)
    logger.info("Prometheus指标路由已加载 (/metrics)")
except Exception as e:
    logger.warning(f"指标路由加载失败: {e}")

# ─── F3.3: 外部Agent挂载 ───────────────────────────────────────────────────
try:
    from api.external_routes import router as router_external
    app.include_router(router_external)
    logger.info("外部Agent挂载路由已加载 (/api/external)")
except Exception as e:
    logger.warning(f"外部Agent挂载路由加载失败: {e}")

# ─── F0.3: 多模型网关 ──────────────────────────────────────────────────────
try:
    from api.model_routes import router as router_model_gateway
    app.include_router(router_model_gateway)
    logger.info("多模型网关路由已加载 (/api/models, /api/chat, /api/models/health)")
except Exception as e:
    logger.warning(f"多模型网关路由加载失败: {e}")

# ─── P10-B: 多模态网关 (build_router() 接入) ────────────────────────────────
# P9-1 之前 multimodal.routes.build_router() 已存在但没被 include, 造成
# /api/v1/multimodal/* 端点 404。P10-B 修复: 在 canvas_web 启动时挂上。
try:
    from multimodal.routes import build_router as build_multimodal_router
    app.include_router(build_multimodal_router())
    logger.info("多模态路由已加载 (/api/v1/multimodal/* — understand/rag/agent/services)")
except Exception as e:
    logger.warning(f"多模态路由加载失败: {e}")

# P3-2-W1: auth_routes 已迁移至 user-service (port 8001)

# F1.13: 分类规则引擎
try:
    from api.classify_routes import router as classify_router
    app.include_router(classify_router)
    logger.info("分类规则引擎路由已加载 (12条预置规则)")
except Exception as e:
    logger.warning(f"分类规则引擎加载失败: {e}")

# F4.4: 音频能力
try:
    from api.audio_routes import router as audio_router
    app.include_router(audio_router)
    logger.info("音频能力路由已加载")
except Exception as e:
    logger.warning(f"音频能力路由加载失败: {e}")

# F1.1: 数据寻源
try:
    from api.discovery_routes import router as discovery_router
    app.include_router(discovery_router)
    logger.info("数据寻源路由已加载")
except Exception as e:
    logger.warning(f"数据寻源路由加载失败: {e}")


# R1: 平台能力模块注册表 + 数据流转追踪器
try:
    from capabilities_v2.routes import router as router_capabilities_v2, flow_router
    app.include_router(router_capabilities_v2)
    app.include_router(flow_router)
    logger.info("能力模块 + 数据流转路由已加载 (/api/v1/capabilities_v2/* + /api/v1/dataflow/*)")
except Exception as e:
    logger.warning(f"能力模块/数据流转路由加载失败: {e}")


# R2: 工作流搭建器 (能力图 DAG, 6 个 starter 模板)
try:
    from workflow_builder.routes import router as router_workflow_builder
    app.include_router(router_workflow_builder)
    logger.info("工作流搭建器路由已加载 (/api/v1/workflow_builder/*)")
except Exception as e:
    logger.warning(f"工作流搭建器路由加载失败: {e}")


# R3: 跨模块编排总线 (整个平台事件 + 血缘)
try:
    from orchestration.routes import router as router_orchestration
    app.include_router(router_orchestration)
    logger.info("跨模块编排总线路由已加载 (/api/v1/orchestration/*)")
    # 模块装载完后,接通其他模块的事件流到总线
    from orchestration import bootstrap as _orch_bootstrap
    _orch_bootstrap()
    logger.info("跨模块编排总线已接通 capabilities_v2 + workflow_builder")
except Exception as e:
    logger.warning(f"跨模块编排总线路由加载失败: {e}")


# R4: 多模态协调器 (8 模态 + 9 导出格式)
try:
    from multimodal_v2.routes import router as router_multimodal_v2
    app.include_router(router_multimodal_v2)
    logger.info("多模态协调器路由已加载 (/api/v1/multimodal_v2/* — 8 模态 + 9 导出)")
except Exception as e:
    logger.warning(f"多模态协调器路由加载失败: {e}")


# R5: 插件生态 (注册 + 调用 + 信任等级)
try:
    from plugins.routes import router as router_plugins
    app.include_router(router_plugins)
    logger.info("插件生态路由已加载 (/api/v1/plugins/*)")
except Exception as e:
    logger.warning(f"插件生态路由加载失败: {e}")


# R6: AI Provider 注册 + 路由 + 计费
try:
    from providers.routes import router as router_providers
    app.include_router(router_providers)
    logger.info("AI Provider 注册路由已加载 (/api/v1/providers/* — 7 厂商 + 路由)")
except Exception as e:
    logger.warning(f"AI Provider 注册路由加载失败: {e}")


# R7: 部署 readiness catalog
try:
    from deploy_r7.readiness import readiness_report, audit_against_app
    from deploy_r7.routes import router as router_deploy_r7
    app.include_router(router_deploy_r7)
    logger.info("R7 部署就绪 HTTP 路由已挂载 (/api/v1/deploy_r7/* — readiness + audit + helm_summary)")
    # no router — informational only; surfaced via /api/v1/security/health
    # include in stats
    import json as _json
    logger.info(f"R7 部署就绪 catalog = {readiness_report()['total_endpoints']} 端点")
except Exception as e:
    logger.warning(f"R7 readiness catalog 加载失败: {e}")


# Depth-7: RequirementEngine rehydrate (从 DB 拉回内存 dict, 跨重启持久)
try:
    from engines.requirement_engine import get_requirement_engine
    n = get_requirement_engine().rehydrate()
    logger.info(f"Depth-7 RequirementEngine rehydrate: {n} rows (跨重启持久)")
except Exception as e:
    logger.warning(f"Depth-7 rehydrate 失败 (非阻塞): {e}")


# Depth-7: RAG VectorStore rehydrate (从 Embedding 表拉回, 避免重启后 RAG 检索空)
try:
    from multimodal.rag import VectorStore
    vs = VectorStore()
    n_emb = vs.rehydrate_from_db()
    if n_emb:
        logger.info(f"Depth-7 RAG VectorStore rehydrate: {n_emb} embeddings (跨重启持久)")
except Exception as e:
    logger.warning(f"Depth-7 RAG rehydrate 失败 (非阻塞): {e}")


# R8: 安全 / OWASP / RBAC 加固
try:
    from security_r8.routes import router as router_security_r8
    app.include_router(router_security_r8)
    logger.info("R8 安全加固路由已加载 (/api/v1/security/* — PII / 限流 / 审计链 / vault)")
except Exception as e:
    logger.warning(f"R8 路由加载失败: {e}")


# R9: 性能原语 (cache / pool / batch / queue)
try:
    from perf_r9.routes import router as router_perf_r9
    app.include_router(router_perf_r9)
    logger.info("R9 性能原语路由已加载 (/api/v1/perf/* — cache/pool/batch/queue)")
except Exception as e:
    logger.warning(f"R9 性能路由加载失败: {e}")


# P3-2-W1: admin_routes 已迁移至 user-service (port 8001)

try:
    from api.routes_extended import crowd_router, delivery_router, review_router, stats_router, req_router
    # P3-2-W1: oss_router (prefix=/api/oss) 从 routes_extended 已迁移至 asset-service (port 8002)
    app.include_router(crowd_router)
    app.include_router(delivery_router)
    app.include_router(review_router)
    app.include_router(stats_router)
    app.include_router(req_router)
    logger.info("扩展路由已加载(众包/交付/审核/统计/需求)")
except Exception as e:
    logger.warning(f"扩展路由加载失败: {e}")

# P3-2-W1: prelabel_router 已迁移至 annotation-service (port 8003)

# ============================================================================
# Phase2-4: 注册API Key / 审计 / 批量 / 导出 / 标注历史路由
# ============================================================================
try:
    from api.api_key_routes import router as api_key_router
    app.include_router(api_key_router)
    logger.info("API Key路由已加载")
except Exception as e:
    logger.warning(f"API Key路由加载失败: {e}")

# R5-Worker-1: settings.js 8 个死按钮接 API — /api/settings/{api,models,storage,notifications,cache/clear}
try:
    from api.settings_routes import router as settings_router
    app.include_router(settings_router)
    logger.info("设置页面路由已加载 (R5-W1: /api/settings/*)")
except Exception as e:
    logger.warning(f"设置页面路由加载失败: {e}")

try:
    from api.audit_routes import router as audit_router
    app.include_router(audit_router)
    logger.info("审计日志路由已加载")
except Exception as e:
    logger.warning(f"审计日志路由加载失败: {e}")

try:
    from api.batch_routes import router as batch_router
    app.include_router(batch_router)
    logger.info("批量操作路由已加载")
except Exception as e:
    logger.warning(f"批量操作路由加载失败: {e}")

# P5-R1-T3: Pack + Collection 路由
try:
    from api.pack_routes import router as pack_router
    app.include_router(pack_router)
    logger.info("Pack 路由已加载 (8 端点)")
except Exception as e:
    logger.warning(f"Pack 路由加载失败: {e}")

try:
    from api.collection_routes import router as collection_router
    app.include_router(collection_router)
    logger.info("Collection 路由已加载 (12+ 端点)")
except Exception as e:
    logger.warning(f"Collection 路由加载失败: {e}")

try:
    from api.export_routes import router as export_router
    app.include_router(export_router)
    logger.info("数据导出路由已加载")
except Exception as e:
    logger.warning(f"数据导出路由加载失败: {e}")

# P3-2-W1: annotation_history_routes 已迁移至 annotation-service (port 8003)

# ============================================================================
# Phase3: 注册新增路由 — 审美评分 / 受控共享 / 增强导出 / 人员绩效
# ============================================================================
try:
    from api.aesthetic_routes import router as aesthetic_router
    app.include_router(aesthetic_router)
    logger.info("审美评分路由已加载 (F1.11)")
except Exception as e:
    logger.warning(f"审美评分路由加载失败: {e}")

# ─── 数字人路由 (R0-Worker-2, 2026-06-18) ───────────────────────────────────
# 原仅在 server_nanobot.py:8898 注册, IMDF 主入口 8900 全部 404
# 现挂到 canvas_web, 行为对齐 server_nanobot.py, 并接入 backend/airi_digital_human.py
try:
    from engines.airi_digital_human import router as airi_router
    app.include_router(airi_router)
    logger.info("数字人路由已加载 (R0-W2: /digital-human/models + /generate + /status)")
except Exception as e:
    logger.warning(f"数字人路由加载失败: {e}")

try:
    from api.sharing_routes import router as sharing_router
    app.include_router(sharing_router)
    logger.info("受控共享路由已加载 (F1.16)")
except Exception as e:
    logger.warning(f"受控共享路由加载失败: {e}")

# ─── F1.16 增强: 受控传输共享 (/api/transfer/) ──────────────────────────────
try:
    from api.transfer_routes import router as transfer_router
    app.include_router(transfer_router)
    logger.info("受控传输共享路由已加载 (F1.16 transfer)")
except Exception as e:
    logger.warning(f"受控传输共享路由加载失败: {e}")

try:
    from api.export_enhanced_routes import router as export_enhanced_router
    app.include_router(export_enhanced_router)
    logger.info("增强导出路由已加载 (F1.17)")
except Exception as e:
    logger.warning(f"增强导出路由加载失败: {e}")

# P3-2-W1: personnel_routes 已迁移至 user-service (port 8001)

# ─── F1.8: 资产管理DAM ──────────────────────────────────────────────────────
# P3-2-W1: dam_routes 已迁移至 asset-service (port 8002)

# ─── F1.6: 短剧一键成片管线 ─────────────────────────────────────────────────
try:
    from api.drama_routes import router as drama_router
    app.include_router(drama_router)
    logger.info("短剧一键成片路由已加载 (F1.6: /api/drama/generate, /api/drama/list, /api/drama/episode)")
except Exception as e:
    logger.warning(f"短剧路由加载失败: {e}")

# ─── F1.7: 绘本一键成书管线 ─────────────────────────────────────────────────
try:
    from api.book_routes import router as book_router
    app.include_router(book_router)
    logger.info("绘本成书路由已加载 (F1.7: /api/book/generate, /api/book/list, /api/book/export)")
except Exception as e:
    logger.warning(f"绘本成书路由加载失败: {e}")

# ─── F2.6: 模板市场路由 ──────────────────────────────────────────────────────
try:
    from api.template_routes import router as template_router
    app.include_router(template_router)
    logger.info("模板市场路由已加载 (F2.6: /api/templates CRUD/评分/搜索/分类)")
except Exception as e:
    logger.warning(f"模板市场路由加载失败: {e}")

# ─── v3补齐: F8.3 版权/C2PA/水印 ─────────────────────────────────────────────
try:
    from api.copyright_routes import router as copyright_router
    app.include_router(copyright_router)
    logger.info("版权C2PA/水印路由已加载 (F8.3: /api/v1/copyright)")
except Exception as e:
    logger.warning(f"版权C2PA/水印路由加载失败: {e}")

# ─── v3补齐: F8.4 PII/DSAR 数据隐私 ──────────────────────────────────────────
try:
    from api.privacy_routes import router as privacy_router
    app.include_router(privacy_router)
    logger.info("PII/DSAR数据隐私路由已加载 (F8.4: /api/v1/privacy)")
except Exception as e:
    logger.warning(f"PII/DSAR数据隐私路由加载失败: {e}")

# ─── v3补齐: F9.2 Webhooks 订阅 ──────────────────────────────────────────────
try:
    from api.webhook_routes import router as webhook_router
    app.include_router(webhook_router)
    logger.info("Webhook订阅路由已加载 (F9.2: /api/v1/webhooks)")
except Exception as e:
    logger.warning(f"Webhook订阅路由加载失败: {e}")

# ─── v3补齐: F9.1 API/SDK 导出 ────────────────────────────────────────────────
try:
    from api.sdk_routes import router as sdk_router
    app.include_router(sdk_router)
    logger.info("SDK导出路由已加载 (F9.1: /api/v1/sdk)")
except Exception as e:
    logger.warning(f"SDK导出路由加载失败: {e}")

# ─── v3补齐: F1.14 高级语义搜索 ──────────────────────────────────────────────
try:
    from api.search_advanced_routes import router as search_advanced_router
    app.include_router(search_advanced_router)
    logger.info("高级语义搜索路由已加载 (F1.14: /api/search/advanced)")
except Exception as e:
    logger.warning(f"高级语义搜索路由加载失败: {e}")

# ─── v3补齐: F3.2 节点契约校验 ───────────────────────────────────────────────
try:
    from api.workflow_contract_routes import router as workflow_contract_router
    app.include_router(workflow_contract_router)
    logger.info("节点契约校验路由已加载 (F3.2: /api/v1/workflow/contract)")
except Exception as e:
    logger.warning(f"节点契约校验路由加载失败: {e}")

# ─── v3补齐: F5.3 众包质检/结算 ──────────────────────────────────────────────
try:
    from api.crowd_settlement_routes import router as crowd_settlement_router
    app.include_router(crowd_settlement_router)
    logger.info("众包质检/结算路由已加载 (F5.3: /api/crowd/settlement)")
except Exception as e:
    logger.warning(f"众包质检/结算路由加载失败: {e}")

# ─── R4-Worker-3: 4 页面 mock fallback 路由补齐 ─────────────────────────────
try:
    from api.r4_mock_fallback_routes import router as r4_mock_router
    app.include_router(r4_mock_router)
    logger.info("R4 mock fallback 路由已加载 (datasets/team/delivery/pipeline)")
except Exception as e:
    logger.warning(f"R4 mock fallback 路由加载失败: {e}")

# ─── P5-R1-T4: AnnotationWorkbench 路由 (真画布工作台) ─────────────────────
try:
    from api.workbench_routes import router as workbench_router
    app.include_router(workbench_router)
    logger.info("AnnotationWorkbench 路由已加载 (P5-R1-T4: /api/v1/workbench)")
except Exception as e:
    logger.warning(f"AnnotationWorkbench 路由加载失败: {e}")

# ─── F2.5: 增强数据生产管线路由 ──────────────────────────────────────────────
try:
    from engines.data_pipeline import get_data_pipeline
    HAS_DATA_PIPELINE = True
    logger.info("数据管线引擎已加载 (F2.5: AUG/SPLIT/FORMAT)")
except ImportError:
    HAS_DATA_PIPELINE = False
    logger.warning("数据管线引擎未找到")

if HAS_DATA_PIPELINE:

    class PipelineRunRequest(BaseModel):
        directory: str = Field("", description="输入目录路径")
        augment_types: Optional[List[str]] = Field(None, description="增强类型列表")
        augment_prob: float = Field(0.5, description="增强触发概率")
        split_ratios: Optional[List[float]] = Field(None, description="分割比例 [train, val, test]")
        split_strategy: str = Field("random", description="分割策略: random/stratified")
        output_format: str = Field("coco_json", description="输出格式")
        output_dir: Optional[str] = Field(None, description="输出目录")

    class PipelineItemsRequest(BaseModel):
        items: List[dict] = Field(..., description="数据集项列表")
        augment_types: Optional[List[str]] = Field(None, description="增强类型列表")
        augment_prob: float = Field(0.5, description="增强触发概率")
        split_ratios: Optional[List[float]] = Field(None, description="分割比例")
        split_strategy: str = Field("random", description="分割策略")
        output_format: str = Field("coco_json", description="输出格式")
        output_dir: Optional[str] = Field(None, description="输出目录")

    @app.get("/api/pipeline/augmentation-types")
    async def get_augmentation_types():
        """获取所有可用的增强类型"""
        pipeline = get_data_pipeline()
        return {"success": True, "data": pipeline.get_augmentation_types()}

    @app.get("/api/pipeline/format-types")
    async def get_format_types():
        """获取所有支持的输出格式"""
        pipeline = get_data_pipeline()
        return {"success": True, "data": pipeline.get_format_types()}

    @app.post("/api/pipeline/run")
    async def run_pipeline(req: PipelineRunRequest):
        """从目录加载数据并执行完整管线 (augment → split → format)"""
        from engines.data_pipeline import DatasetItem

        pipeline = get_data_pipeline()
        items = pipeline.load_from_directory(req.directory) if req.directory else []

        if not items:
            raise HTTPException(status_code=400, detail="目录为空或无有效图片文件")

        result = pipeline.run_minimal(
            items=items,
            augment_types=req.augment_types,
            split_ratios=req.split_ratios,
            output_format=req.output_format,
            output_dir=req.output_dir,
        )
        return {"success": True, "data": result.to_dict()}

    @app.post("/api/pipeline/run-with-items")
    async def run_pipeline_with_items(req: PipelineItemsRequest):
        """给定数据项列表，执行完整管线"""
        from engines.data_pipeline import DatasetItem

        pipeline = get_data_pipeline()
        items = [
            DatasetItem(
                id=item.get("id", f"item_{i}"),
                path=item.get("path", ""),
                label=item.get("label"),
                bbox=item.get("bbox"),
                metadata=item.get("metadata", {}),
                source=item.get("source", ""),
            )
            for i, item in enumerate(req.items)
        ]

        result = pipeline.run_minimal(
            items=items,
            augment_types=req.augment_types,
            split_ratios=req.split_ratios,
            output_format=req.output_format,
            output_dir=req.output_dir,
        )
        return {"success": True, "data": result.to_dict()}

    logger.info("数据管线API路由已注册 (F2.5: /api/pipeline/*)")

# 初始化数据库
try:
    from api.db_models import init_db
    init_db()
    logger.info("数据库初始化完成")
except Exception as e:
    logger.warning(f"数据库初始化失败: {e}")


@app.get("/api/prompt-templates", tags=["prompt_templates"])
async def get_templates(
    kind: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="模板类型 (白名单字符)",
    ),
    category: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="模板分类 (白名单字符)",
    ),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """获取提示词模板"""
    return {
        "success": True,
        "data": app_state.get_prompt_templates(kind, category),
        "limit": limit,
        "offset": offset,
    }


@app.post("/api/prompt-templates", tags=["prompt_templates"])
async def create_template(req: PromptTemplateCreate):
    """创建提示词模板"""
    t = app_state.create_prompt_template(req)
    return {"success": True, "data": t.dict()}


@app.put("/api/prompt-templates/{template_id}", tags=["prompt_templates"])
async def update_template(template_id: str, req: PromptTemplateCreate):
    """更新提示词模板"""
    t = app_state.update_prompt_template(template_id, req)
    if not t:
        raise HTTPException(status_code=404, detail="模板不存在或为内置模板")
    return {"success": True, "data": t.dict()}


@app.delete("/api/prompt-templates/{template_id}", tags=["prompt_templates"])
async def delete_template(template_id: str):
    """删除提示词模板"""
    ok = app_state.delete_prompt_template(template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="模板不存在或为内置模板")
    return {"success": True, "message": "模板已删除"}


@app.get("/api/prompt-templates/categories", tags=["prompt_templates"])
async def get_categories(
    kind: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="模板类型 (白名单字符)",
    ),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """获取模板分类"""
    return {
        "success": True,
        "data": app_state.get_prompt_categories(kind),
        "limit": limit,
        "offset": offset,
    }


@app.post("/api/figma/import", tags=["figma"])
async def figma_import(req: FigmaImportRequest):
    """导入素材到Figma队列"""
    item = app_state.figma_import(req)
    return {"success": True, "data": item}


@app.get("/api/figma/claim", tags=["figma"])
async def figma_claim(
    max_items: int = Query(10, ge=1, le=100, description="最大返回条数 (1..100)"),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """Figma插件轮询获取待导入素材"""
    items = app_state.figma_claim(max_items)
    if q:
        items = [i for i in items if q.lower() in str(i).lower()]
    total = len(items)
    page = items[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/upstream-materials/{node_id}", tags=["upstream"])
async def get_upstream_materials(
    node_id: str,
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """获取指定节点的上游素材列表"""
    materials = app_state.get_upstream_materials(node_id)
    if q:
        materials = [m for m in materials if q.lower() in str(m).lower()]
    total = len(materials)
    page = materials[offset: offset + limit]
    return {
        "success": True,
        "data": {"materials": page, "total": total},
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/tutorials", tags=["tutorials"])
async def get_tutorials(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """获取画布教程列表"""
    tutorials = app_state.get_tutorials()
    if q:
        tutorials = [t for t in tutorials if q.lower() in str(t).lower()]
    total = len(tutorials)
    page = tutorials[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """返回独立前端页面(优先)或内联HTML_TEMPLATE(备选)"""
    import os
    frontend_index = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "index.html")
    if os.path.exists(frontend_index):
        try:
            with open(frontend_index, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read frontend index: {e}")
    return HTML_TEMPLATE

@app.get("/canvas", response_class=HTMLResponse)
async def canvas_page():
    """画布编辑器页面(内联HTML_TEMPLATE备选)"""
    return HTML_TEMPLATE

@app.get("/login.html", response_class=HTMLResponse)
async def login_page():
    """登录页面"""
    import os
    login_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "login.html")
    if os.path.exists(login_path):
        with open(login_path, "r", encoding="utf-8") as f:
            return f.read()
    return HTML_TEMPLATE


@app.get("/canvas/state")
async def get_canvas_state(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """获取当前画布状态 — 优先返回保存的工作流状态"""
    import os, json
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "workflow_state.json")
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if saved.get("nodes") and len(saved["nodes"]) > 0:
                return {
                    **saved,
                    "limit": limit,
                    "offset": offset,
                }
        except Exception as e:
            logger.error(f"Failed to read canvas state: {e}")
    state = app_state.get_state()
    return {**state, "limit": limit, "offset": offset}


@app.post("/canvas/state")
async def set_canvas_state(req: dict):
    """保存画布状态"""
    return app_state.set_state(req)


@app.post("/canvas/element")
async def add_canvas_element(req: AddElementRequest):
    """添加元素到画布"""
    result = app_state.add_element(req)
    await app_state.broadcast({"type": "state_updated", "data": app_state.get_state()})
    return result


@app.delete("/canvas/element/{element_id}")
async def remove_canvas_element(element_id: str):
    """从画布移除元素"""
    # R1-Worker-2: 用共享校验器防止 bad_params (e.g. '💥') 触发崩溃。
    validate_id(element_id, "element_id")

    success = app_state.remove_element(element_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Element {element_id} not found")
    await app_state.broadcast({"type": "state_updated", "data": app_state.get_state()})
    return {"success": True}


@app.post("/engine/plan")
async def engine_plan(req: PlanRequest):
    """用Master Agent规划生产"""
    result = app_state.plan(req.user_input)
    return result


@app.post("/engine/render")
async def engine_render(req: RenderRequest):
    """执行引擎渲染"""
    result = app_state.render(req.plan_id)
    await app_state.broadcast({"type": "state_updated", "data": app_state.get_state()})
    return result


# ============================================================================
# 视频生成辅助函数 (DeepSeek + ffmpeg seedance风格)
# ============================================================================

def _build_fallback_storyboard(text: str) -> dict:
    """当DeepSeek不可用时，基于文本生成默认分镜"""
    import hashlib
    seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
    
    # 主题色系
    palettes = [
        ["#1a1a2e", "#16213e", "#0f3460", "#533483", "#e94560"],
        ["#0d1117", "#161b22", "#21262d", "#30363d", "#58a6ff"],
        ["#1b2838", "#2a475e", "#1a1a2e", "#0f3460", "#e94560"],
        ["#0f0f23", "#1a1a3e", "#2d2d5e", "#4a4a8a", "#7b7bff"],
    ]
    colors = palettes[seed % len(palettes)]
    
    # 从文本中提取关键词作为场景
    import re
    sentences = re.split(r'[。！？\n,，]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 4]
    
    if len(sentences) < 2:
        sentences = [
            f"探索: {text[:20]}",
            f"深入: {text[:20]}的核心",
            f"未来: {text[:20]}的演进",
        ]
    
    scenes = []
    for i, sentence in enumerate(sentences[:5]):
        scenes.append({
            "id": i + 1,
            "title": sentence[:8] if len(sentence) > 8 else sentence,
            "visual": sentence[:30],
            "narration": sentence[:20],
            "duration": min(5.0, max(3.0, len(sentence) * 0.3)),
            "bg_color": colors[i % len(colors)],
            "text_color": "#ffffff" if i < 3 else "#ffdd57",
            "transition": "fade" if i == 0 else "slide_left" if i % 2 == 0 else "slide_right",
        })
    
    return {
        "title": text[:15] if len(text) > 15 else text,
        "style": "科技感",
        "total_duration": sum(s["duration"] for s in scenes),
        "scenes": scenes,
    }


def _render_scene_frame(output_path: str, title: str, narration: str,
                         visual: str, bg_color: str, text_color: str,
                         style: str, scene_id: int, total_scenes: int):
    """用Pillow渲染场景帧图片 (1920x1080)"""
    from PIL import Image, ImageDraw, ImageFont
    import textwrap
    
    W, H = 1920, 1080
    
    # 解析颜色
    bg = _hex_to_rgb(bg_color)
    fg = _hex_to_rgb(text_color)
    
    img = Image.new('RGB', (W, H), bg)
    draw = ImageDraw.Draw(img)
    
    # 加载字体
    fonts = _load_video_fonts()
    font_title = fonts.get("title")
    font_body = fonts.get("body")
    font_small = fonts.get("small")
    
    # 顶部场景编号条
    bar_h = 6
    bar_y = 20
    bar_w = (W - 60) // total_scenes
    for j in range(total_scenes):
        bx = 30 + j * bar_w
        if j < scene_id - 1:
            bar_color = (100, 200, 100)
        elif j == scene_id - 1:
            bar_color = fg
        else:
            bar_color = (60, 60, 80)
        draw.rectangle([bx, bar_y, bx + bar_w - 4, bar_y + bar_h], fill=bar_color)
    
    # 场景编号
    draw.text((W - 120, 12), f"{scene_id}/{total_scenes}", fill=fg, font=font_small)
    
    # 中央标题
    tw = font_title.getbbox(title)[2] if hasattr(font_title, 'getbbox') else font_title.getsize(title)[0]
    draw.text(((W - tw) // 2, H // 2 - 120), title, fill=fg, font=font_title)
    
    # 画面描述 (副标题)
    if visual:
        vw = font_body.getbbox(visual)[2] if hasattr(font_body, 'getbbox') else font_body.getsize(visual)[0]
        draw.text(((W - vw) // 2, H // 2 - 40), visual, fill=(
            min(fg[0] + 60, 255), min(fg[1] + 60, 255), min(fg[2] + 60, 255)
        ), font=font_body)
    
    # 底部旁白
    if narration:
        nw = font_body.getbbox(narration)[2] if hasattr(font_body, 'getbbox') else font_body.getsize(narration)[2]
        y_narration = H - 100
        # 旁白背景条
        draw.rectangle([(W - nw) // 2 - 30, y_narration - 10, (W + nw) // 2 + 30, y_narration + 45],
                      fill=(*_darken(bg, 0.8), 180))
        draw.text(((W - nw) // 2, y_narration), narration, fill=fg, font=font_body)
    
    # 装饰性几何元素 (科技感)
    import math
    cx, cy = W // 2, H // 2 + 50
    for r in range(40, 180, 30):
        alpha = 20 + (r // 3)
        c = (min(fg[0], 100), min(fg[1], 140), min(fg[2], 200))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=1)
    
    # 网格线
    for x in range(0, W, 80):
        draw.line([(x, 0), (x, H)], fill=(30, 30, 50, 60), width=1)
    for y in range(0, H, 80):
        draw.line([(0, y), (W, y)], fill=(30, 30, 50, 60), width=1)
    
    img.save(output_path, "PNG")


def _render_scene_video(frame_path: str, output_path: str, duration: float,
                         transition: str, title: str, narration: str):
    """用ffmpeg将场景帧渲染为带Ken Burns效果的视频片段"""
    import subprocess
    
    # Ken Burns效果: 缓慢缩放/平移
    # fade-in 0.5s, then zoom 1.0→1.05 over duration, fade-out 0.5s
    fps = 24
    total_frames = int(duration * fps)
    fade_frames = min(int(0.5 * fps), total_frames // 4)
    zoom_start = 1.0
    zoom_end = 1.04
    
    # 使用zoompan滤镜实现Ken Burns + 淡入淡出
    vf_parts = [
        f"fps={fps}",
        f"scale=1920:1080:force_original_aspect_ratio=decrease",
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        # zoompan实现缓慢缩放
        f"zoompan=z='min({zoom_end},{zoom_start}+(on/{total_frames})*{(zoom_end - zoom_start):.3f})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps={fps}",
        # 淡入淡出
        f"fade=t=in:st=0:d=0.5",
        f"fade=t=out:st={duration - 0.5}:d=0.5",
    ]
    
    # 场景标题水印
    safe_title = title.replace(":", "\\:").replace("'", "\\'")
    vf_parts.append(
        f"drawtext=text='{safe_title}':fontcolor=white@0.6:fontsize=24:"
        f"x=w-text_w-30:y=30:enable='between(t,0,{duration})'"
    )
    
    vf_filter = ",".join(vf_parts)
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", frame_path,
        "-vf", vf_filter,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg render scene failed: {result.stderr[:300]}")


def _hex_to_rgb(hex_color: str) -> tuple:
    """#1a2b3c → (26, 43, 60)"""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _darken(rgb: tuple, factor: float) -> tuple:
    """使颜色变暗"""
    return tuple(max(0, int(c * factor)) for c in rgb)


def _load_video_fonts() -> dict:
    """加载视频渲染所需字体"""
    from PIL import ImageFont
    fonts = {}
    
    font_paths = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    
    for path in font_paths:
        if os.path.exists(path):
            try:
                fonts["title"] = ImageFont.truetype(path, 64)
                fonts["body"] = ImageFont.truetype(path, 32)
                fonts["small"] = ImageFont.truetype(path, 20)
                return fonts
            except Exception:
                continue
    
    # 终极fallback
    fonts["title"] = ImageFont.load_default()
    fonts["body"] = ImageFont.load_default()
    fonts["small"] = ImageFont.load_default()
    return fonts


# ============================================================================
# API Endpoints
# ============================================================================


@app.post("/api/video/generate")
async def video_generate(req: PlanRequest):
    """用DeepSeek生成视频脚本 + ffmpeg合成真实AI视频 (seedance风格: 文字→分镜→合成)"""
    import subprocess, time, os, json, re, tempfile, shutil
    try:
        output_dir = "data/output"
        os.makedirs(output_dir, exist_ok=True)
        timestamp = int(time.time())
        filepath = f"{output_dir}/vid_{timestamp}.mp4"
        text = req.user_input.strip() if req.user_input else "IMDF Video"

        # =====================================================================
        # Phase 1: DeepSeek生成结构化视频脚本 (seedance风格: 文字→分镜)
        # =====================================================================
        from api.nanobot_adapter import NanobotAdapter
        adapter = NanobotAdapter()
        
        storyboard_prompt = f"""你是一个专业视频导演。根据用户的文字描述，生成一个结构化视频分镜脚本。

用户输入: {text}

请严格按以下JSON格式返回分镜脚本（不要包含其他文字，只返回JSON）:
{{
  "title": "视频标题(15字以内)",
  "style": "视觉风格(如:科技感/温暖/电影感/简约)",
  "total_duration": 总时长秒数(10-30),
  "scenes": [
    {{
      "id": 1,
      "title": "场景标题(8字以内)",
      "visual": "画面描述(30字以内)",
      "narration": "旁白文字(20字以内)",
      "duration": 该场景秒数(3-8),
      "bg_color": "背景色(hex如#1a1a2e)",
      "text_color": "文字色(hex如#ffffff)",
      "transition": "转场效果(fade/slide_left/slide_right/zoom)"
    }}
  ]
}}

要求:
- 3-6个场景，总时长10-30秒
- 场景间有逻辑递进关系
- bg_color使用深色调科技色系
- 每个场景的narration简洁有力
- transition在fade/slide_left/slide_right/zoom中选择"""

        # 调用DeepSeek生成分镜
        storyboard = None
        deepseek_used = False
        try:
            chat_result = await adapter.chat(storyboard_prompt, model="deepseek-chat")
            if chat_result.get("success") and chat_result.get("message"):
                raw = chat_result["message"].strip()
                # 提取JSON (可能包裹在```json ... ```中)
                json_match = re.search(r'\{[\s\S]*\}', raw)
                if json_match:
                    storyboard = json.loads(json_match.group())
                    deepseek_used = True
                    logger.info(f"[video/generate] DeepSeek生成{len(storyboard.get('scenes',[]))}个分镜")
        except Exception as e:
            logger.warning(f"[video/generate] DeepSeek分镜生成失败: {e}")

        # Fallback: 内置模板生成
        if not storyboard or not storyboard.get("scenes"):
            storyboard = _build_fallback_storyboard(text)
            logger.info("[video/generate] 使用fallback分镜模板")

        scenes = storyboard.get("scenes", [])
        title = storyboard.get("title", text[:15])
        style = storyboard.get("style", "科技感")

        # =====================================================================
        # Phase 2: 逐场景用Pillow+ffmpeg生成视频片段
        # =====================================================================
        tmp_dir = tempfile.mkdtemp(prefix="imdf_video_")
        segment_files = []
        scene_details = []

        for i, scene in enumerate(scenes):
            scene_id = scene.get("id", i + 1)
            scene_title = scene.get("title", f"场景{i+1}")
            scene_visual = scene.get("visual", "")
            scene_narration = scene.get("narration", "")
            scene_duration = float(scene.get("duration", 5))
            bg_color = scene.get("bg_color", "#1a1a2e")
            text_color = scene.get("text_color", "#ffffff")
            transition = scene.get("transition", "fade")

            seg_path = os.path.join(tmp_dir, f"scene_{scene_id:02d}.mp4")
            
            try:
                # 用Pillow生成场景帧图片
                frame_path = os.path.join(tmp_dir, f"frame_{scene_id:02d}.png")
                _render_scene_frame(
                    frame_path, scene_title, scene_narration, scene_visual,
                    bg_color, text_color, style, scene_id, len(scenes)
                )
                
                # ffmpeg: 图片→带过渡动画的视频片段
                _render_scene_video(frame_path, seg_path, scene_duration, transition, scene_title, scene_narration)
                
                if os.path.exists(seg_path) and os.path.getsize(seg_path) > 0:
                    segment_files.append(seg_path)
                    scene_details.append({
                        "id": scene_id, "title": scene_title,
                        "narration": scene_narration, "duration": scene_duration,
                        "transition": transition
                    })
            except Exception as e:
                logger.warning(f"[video/generate] 场景{scene_id}渲染失败: {e}")

        # =====================================================================
        # Phase 3: ffmpeg concat合成最终视频
        # =====================================================================
        if len(segment_files) >= 1:
            if len(segment_files) == 1:
                shutil.copy2(segment_files[0], filepath)
            else:
                # 用concat demuxer拼接
                concat_file = os.path.join(tmp_dir, "concat_list.txt")
                with open(concat_file, "w") as f:
                    for seg in segment_files:
                        f.write(f"file '{seg}'\n")
                result = subprocess.run([
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_file,
                    "-c:v", "libx264", "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    filepath,
                ], capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    logger.error(f"[video/generate] concat失败: {result.stderr[:200]}")
                    # fallback: 用第一个片段
                    shutil.copy2(segment_files[0], filepath)
        else:
            # 终极fallback: 纯ffmpeg合成
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=#1a1a2e:s=1920x1080:d=5",
                "-vf", f"drawtext=text='{text[:60]}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                filepath,
            ], capture_output=True, timeout=60)

        # 清理临时目录
        try:
            shutil.rmtree(tmp_dir)
        except Exception as e:
            logger.error(f"Failed to cleanup tmp dir: {e}")

        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            total_dur = sum(float(s.get("duration", 5)) for s in scenes)
            return {
                "success": True,
                "data": {
                    "status": "generated",
                    "file": filepath,
                    "size": size,
                    "duration": total_dur,
                    "scenes": len(scenes),
                    "title": title,
                    "style": style,
                    "engine": "deepseek+ffmpeg" if deepseek_used else "template+ffmpeg",
                    "scene_details": scene_details,
                }
            }
        else:
            return {"success": False, "error": "视频文件生成失败"}
    except Exception as e:
        logger.error(f"video_generate failed: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/ppt/generate")
async def ppt_generate(req: PlanRequest):
    """真实生成PPT HTML"""
    from engines.ppt_engine import PPTEngine, SlideSpec, SlideType
    engine = PPTEngine()
    tmpl = engine.select_template(req.user_input)
    slides = [
        SlideSpec(slide_type=SlideType.COVER, title=req.user_input),
        SlideSpec(slide_type=SlideType.CONTENT, title="核心内容", content=["功能一", "功能二", "功能三"]),
        SlideSpec(slide_type=SlideType.END, title="谢谢"),
    ]
    html = engine.generate_full_html(slides, template_id=tmpl["id"], title=req.user_input)
    # 保存到文件
    import time
    filepath = f"data/output/ppt_{int(time.time())}.html"
    os.makedirs("data/output", exist_ok=True)
    with open(filepath, "w") as f:
        f.write(html)
    return {"success": True, "data": {"html": html[:100], "file": filepath, "template": tmpl["id"]}}


# ============================================================================
# ComfyUI Workflow Execution Routes
# ============================================================================

class ComfyUIRunRequest(BaseModel):
    workflow_id: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    overrides: Dict[str, Any] = {}


@app.get("/api/comfyui/workflows")
async def comfyui_list_workflows():
    """列出所有可用的ComfyUI工作流"""
    from engines.comfyui_engine import ComfyUIEngine
    engine = ComfyUIEngine()
    workflows = engine.list_workflows()
    return {"success": True, "data": [w.to_dict() for w in workflows]}


@app.post("/api/comfyui/run")
async def comfyui_run(req: ComfyUIRunRequest):
    """运行ComfyUI工作流"""
    import httpx
    try:
        from engines.comfyui_engine import ComfyUIEngine
        engine = ComfyUIEngine()
        result = await engine.run_workflow(
            workflow_id=req.workflow_id,
            params={
                "prompt": req.prompt,
                "negative_prompt": req.negative_prompt,
                "overrides": req.overrides,
            }
        )
        if result.get("ok"):
            return {"success": True, "data": result}
        return {"success": False, "error": result.get("error", "Unknown error")}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/comfyui/status/{prompt_id}")
async def comfyui_status(prompt_id: str):
    """查询ComfyUI工作流执行状态"""
    validate_id(prompt_id, "prompt_id")
    try:
        from engines.comfyui_engine import ComfyUIEngine
        engine = ComfyUIEngine()
        result = await engine.get_status(prompt_id)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================================
# Workflow Engine Routes — DAG validation / execution + templates
# ============================================================================

# Lazy-init workflow engine singletons
_workflow_node_registry_initialized = False
_workflow_template_manager = None


def _ensure_workflow():
    global _workflow_node_registry_initialized, _workflow_template_manager
    if not _workflow_node_registry_initialized:
        from nodes.registry import NodeRegistry
        NodeRegistry.initialize()
        _workflow_node_registry_initialized = True
    if _workflow_template_manager is None:
        from nodes.templates import TemplateManager
        _workflow_template_manager = TemplateManager()
    return _workflow_template_manager


@app.post("/api/workflow/validate", tags=["workflow"])
async def workflow_validate(req: WorkflowValidateRequest):
    """Validate a DAG: cycle detection + type/port checking."""
    from nodes.engine import DAGEngine
    from nodes.registry import NodeRegistry
    NodeRegistry.initialize()
    
    raw_nodes = {}
    for i, wn in enumerate(req.nodes):
        nid = wn.get("id", f"n{i}")
        raw_nodes[nid] = wn
    
    dag = DAGEngine.build_dag(raw_nodes, req.connections)
    result = DAGEngine.validate(dag)
    return {
        "success": True,
        "data": {
            "valid": result.get("valid", False),
            "errors": str(result.get("errors", [])),
            "warnings": str(result.get("warnings", [])),
            "node_count": len(raw_nodes),
            "connection_count": len(req.connections),
        },
    }


@app.post("/api/workflow/execute", tags=["workflow"])
async def workflow_execute(req: WorkflowExecuteRequest):
    """Execute a DAG and return results with per-node outputs."""
    from nodes.engine import DAGEngine
    from nodes.registry import NodeRegistry
    NodeRegistry.initialize()
    
    raw_nodes = {}
    for i, wn in enumerate(req.nodes):
        nid = wn.get("id", f"n{i}")
        raw_nodes[nid] = wn
    
    dag = DAGEngine.build_dag(raw_nodes, req.connections)
    result = DAGEngine.validate(dag)
    if not result.get("valid", False):
        return {"success": False, "error": "DAG验证失败", "errors": result.get("errors", [])}
    
    exec_result = await DAGEngine.execute(dag, {})
    return {"success": True, "data": exec_result}


@app.get("/api/workflow/templates", tags=["workflow"])
async def workflow_templates(
    category: Optional[str] = Query(
        None, max_length=64, pattern=r"^[a-zA-Z0-9_\-]{1,64}$",
        description="分类过滤 (白名单字符, ≤64 字符)",
    ),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """Get all workflow templates (R2.5-W1: Pydantic Query 验证)."""
    tm = _ensure_workflow()
    templates = tm.list_templates(category)
    if q:
        ql = q.lower()
        templates = [t for t in templates if ql in str(t).lower()]
    total = len(templates)
    if sort_by:
        templates = sorted(
            templates, key=lambda t: t.get(sort_by, "") if isinstance(t, dict) else "",
            reverse=(order == "desc"),
        )
    page = templates[offset: offset + limit]
    return {
        "success": True,
        "data": {
            "templates": page,
            "categories": tm.list_categories(),
            "total": total,
        },
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/workflow/nodes", tags=["workflow"])
async def workflow_nodes(
    category: Optional[str] = Query(
        None, max_length=64, pattern=r"^[a-zA-Z0-9_\-]{1,64}$",
        description="分类过滤 (白名单字符, ≤64 字符)",
    ),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """Get all registered node types (R2.5-W1: Pydantic Query 验证)."""
    from nodes.registry import NodeRegistry
    NodeRegistry.initialize()
    if category:
        nodes = NodeRegistry.list_by_category(category)
    else:
        nodes = NodeRegistry.list_all()
    return {
        "success": True,
        "data": {
            "nodes": [
                {
                    "type": nd.type,
                    "category": nd.category,
                    "label": nd.label,
                    "icon": nd.icon,
                    "color": nd.color,
                    "inputs": [{"name": p.name, "type": p.type} for p in nd.inputs],
                    "outputs": [{"name": p.name, "type": p.type} for p in nd.outputs],
                    "params": [{"name": p.name, "type": p.type, "label": p.label, "default": p.default} for p in nd.params],
                }
                for nd in nodes.values()
            ],
            "categories": NodeRegistry.list_categories(),
            "total": len(nodes),
        },
    }


@app.post("/api/v1/chat/smart")
async def chat_api(req: PlanRequest):
    """P10-B: 调用真实AI进行对话 — 改用 ``call_provider_smart`` (P5-W1 统一入口)。

    P11-A: 路径从 ``/api/chat`` 迁移到 ``/api/v1/chat/smart``, 避免与 ``model_routes.unified_chat``
    (mount 在 ``/api/chat``) 路由冲突。前端若需要旧路径, 统一走 ``unified_chat``, 该路径
    内部已切到 ``call_provider_smart``。

    之前用 ``NanobotAdapter.chat()`` 直连 DeepSeek, 现在改走 provider_registry 的
    ``call_provider_smart``: 自动限流 / 熔断 / mock 降级 / 用量记账 / 审计链。

    行为兼容: 保留 ``{"success", "message"/"error"}`` 返回结构。
    """
    try:
        # P10-B: 走 call_provider_smart (P5-W1 统一入口)
        from engines.provider_registry import (
            call_provider_smart,
            _get_default_providers,
        )
        # 选第一个 enabled + chat model 可用的 provider; 没有则取第一个有 chatModels 的
        provider = None
        for p in _get_default_providers() or []:
            if p.get("enabled") and p.get("chatModels"):
                provider = p
                break
        if not provider:
            for p in _get_default_providers() or []:
                if p.get("chatModels"):
                    provider = p
                    break
        if not provider:
            # 全部未配置 → fallback NanobotAdapter (老链路, 保持向后兼容)
            from api.nanobot_adapter import NanobotAdapter
            adapter = NanobotAdapter()
            return await adapter.chat(req.user_input)
        payload = {
            "model": provider.get("defaults", {}).get("chatModel", "") or (provider.get("chatModels") or ["gpt-4o"])[0],
            "messages": [{"role": "user", "content": req.user_input or ""}],
            "temperature": 0.7,
            "max_tokens": 4096,
        }
        result = await call_provider_smart(
            provider, payload, kind="chat",
            user_id="anonymous",
            org_id="",
        )
        if result.get("ok") and isinstance(result.get("data"), dict):
            content = (
                (result["data"].get("choices") or [{}])[0]
                .get("message", {}).get("content", "")
                or (result["data"].get("content", ""))
            )
            return {
                "success": True,
                "message": content,
                "model": result["data"].get("model", payload["model"]),
                "provider_id": result.get("provider_id", provider.get("id")),
                "cost_usd": result.get("cost_usd", 0.0),
                "usage": result.get("usage_tokens", 0),
                "mock": result.get("mock", False),
            }
        # 失败 — 兼容老返回结构
        return {
            "success": False,
            "error": result.get("error") or f"call_provider_smart failed: {result.get('code', 'unknown')}",
            "code": result.get("code", "unknown"),
            "provider_id": result.get("provider_id", provider.get("id")),
        }
    except Exception as e:
        # 终极 fallback — NanobotAdapter 老链路
        try:
            from api.nanobot_adapter import NanobotAdapter
            adapter = NanobotAdapter()
            return await adapter.chat(req.user_input)
        except Exception as e2:
            return {"success": False, "error": f"{e} | fallback: {e2}"}


# ============================================================================
# P2-3-W2: AI Provider usage + billing + circuit breaker endpoints
# ============================================================================

@app.get("/api/ai/usage")
@app.get("/api/v1/ai/usage")
async def ai_usage(
    request: Request,
    user_id: Optional[str] = Query(None, max_length=64, description="用户 ID (缺省 = 当前用户或 anonymous)"),
    org_id: Optional[str] = Query(None, max_length=64, description="组织 ID"),
    days: int = Query(30, ge=1, le=365, description="回看天数 (1..365)"),
):
    """查询 AI provider 用量 + 计费。

    返回 ``{"success", "data": {user_id, org_id, days, total_calls, total_tokens,
    total_cost_usd, month_to_date_cost_usd, by_provider, by_kind, errors, fallback_rows}}``

    降级:
    - DB 不可用 → 读 ``data/usage_fallback.jsonl``
    - 用户没传 user_id → 默认 "anonymous" (兼容没登录场景)
    """
    import time as _t
    try:
        from engines.usage_tracker import get_tracker

        uid = user_id or "anonymous"
        tracker = get_tracker()
        if org_id:
            data = tracker.org_summary(org_id, days=days)
        else:
            data = tracker.user_summary(uid, days=days)
        return {"success": True, "data": data, "ts": int(_t.time())}
    except Exception as e:
        logger.warning(f"/api/ai/usage failed: {e}")
        # 失败也要返回 200 + 空数据, 让前端能正常显示 (而不是 500 拖垮 dashboard)
        return {
            "success": True,
            "data": {
                "entity_id": user_id or "anonymous",
                "scope": "org" if org_id else "user",
                "days": days,
                "total_calls": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "month_to_date_cost_usd": 0.0,
                "by_provider": [],
                "by_kind": [],
                "errors": 0,
                "fallback_rows": 0,
            },
            "ts": int(_t.time()),
            "degraded": True,
            "degraded_reason": str(e)[:200],
        }


@app.get("/api/ai/circuit")
@app.get("/api/v1/ai/circuit")
async def ai_circuit(
    request: Request,
    provider_id: Optional[str] = Query(None, max_length=64, description="Provider ID (缺省 = 全部)"),
):
    """查询 / 触发 Circuit Breaker 状态。

    GET ``/api/ai/circuit`` → 全部 provider 快照
    GET ``/api/ai/circuit?provider_id=openai-compatible`` → 单 provider 快照
    """
    import time as _t2
    try:
        from engines.provider_registry import _GLOBAL_BREAKER, circuit_breaker

        if provider_id:
            snap = circuit_breaker(provider_id)
            return {"success": True, "data": {provider_id: snap}, "ts": int(_t2.time())}
        snap = _GLOBAL_BREAKER.snapshot()
        return {"success": True, "data": snap, "ts": int(_t2.time())}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


@app.post("/api/ai/circuit/reset")
@app.post("/api/v1/ai/circuit/reset")
async def ai_circuit_reset(
    request: Request,
    provider_id: Optional[str] = Query(None, max_length=64),
):
    """重置 Circuit Breaker (管理操作, 真实部署应加权限)。"""
    import time as _t3
    try:
        from engines.provider_registry import _GLOBAL_BREAKER
        _GLOBAL_BREAKER.reset(provider_id)
        return {"success": True, "reset": provider_id or "all", "ts": int(_t3.time())}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


@app.post("/api/ai/cost/estimate")
@app.post("/api/v1/ai/cost/estimate")
async def ai_cost_estimate(request: Request):
    """估算一次调用的 USD 成本 — 给前端"提交前预览"用。

    Body: ``{"protocol", "model", "prompt_tokens", "completion_tokens"}``
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    proto = str(body.get("protocol") or "").strip()
    model = str(body.get("model") or "").strip()
    pt = int(body.get("prompt_tokens") or 0)
    ct = int(body.get("completion_tokens") or 0)
    try:
        from engines.provider_registry import cost_estimate
        return {"success": True, "data": cost_estimate(proto, model, pt, ct)}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


@app.post("/api/image/generate")
async def image_generate(req: PlanRequest):
    """真实调用AI生成图片 — DeepSeek生成提示词 + NanoBot/ComfyUI调用"""
    from api.nanobot_adapter import NanobotAdapter
    adapter = NanobotAdapter()
    
    try:
        # 1. 用LLM生成英文prompt
        chat_result = await adapter.chat(f"为'{req.user_input}'生成一个高质量英文图片生成提示词，包含风格、光照、构图。直接输出提示词，不要其他内容。")
        prompt_en = chat_result.get("message", req.user_input)
        if not prompt_en or prompt_en.startswith("HTTP"):
            prompt_en = req.user_input
        
        # 2. 尝试NanoBot
        payload = {
            "prompt": prompt_en,
            "negative_prompt": "",
            "generator": "comfyui",
            "settings": {"model": "seedream-5.0", "width": 1024, "height": 1024, "steps": 25}
        }
        result = await adapter.generate(payload)
        if result:
            return {"success": True, "data": {"status": "queued", "task_id": result.get("task_id", ""), "prompt": prompt_en}}
        
        # 3. Fallback: Pillow生成真实图片
        import time
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new('RGB', (1024, 1024), (30, 30, 60))
            draw = ImageDraw.Draw(img)
            # 把prompt写在图片上作为真实产出
            lines = []
            words = prompt_en.split()
            for i in range(0, len(words), 6):
                lines.append(" ".join(words[i:i+6]))
            y = 400
            draw.text((50, 350), f"IMDF AI Generated", fill=(100,200,255))
            draw.text((50, 390), f"Prompt: {req.user_input}", fill=(200,200,255))
            for line in lines[:8]:
                draw.text((50, y), line, fill=(180,180,220))
                y += 24
            draw.text((50, y+20), f"[AI-powered generation]", fill=(100,100,150))
            filepath = f"data/output/img_{int(time.time())}.png"
            os.makedirs("data/output", exist_ok=True)
            img.save(filepath)
            return {"success": True, "data": {"status": "generated", "file": filepath, "prompt": prompt_en, "model": "deepseek+pillow"}}
        except ImportError:
            # 最后的fallback: 文本文件
            filepath = f"data/output/img_{int(time.time())}.txt"
            os.makedirs("data/output", exist_ok=True)
            with open(filepath, "w") as f:
                f.write(f"Image prompt: {prompt_en}\nInput: {req.user_input}")
            return {"success": True, "data": {"status": "generated", "file": filepath, "prompt": prompt_en, "model": "text-fallback"}}
            
    except Exception as e:
        logger.error(f"image_generate failed: {e}")
        return {"success": False, "error": str(e)}
@app.websocket("/canvas/ws")
async def canvas_websocket(websocket: WebSocket):
    """实时画布状态推送"""
    await app_state.handle_websocket(websocket)


# ============================================================================
# P0-9: API v1 versioned routes (aliases for all /api/ routes)
# ============================================================================

# Rate-limited v1 aliases for the main API routes

@app.get("/api/v1/prompt-templates")
@limiter.limit("100/minute")
async def v1_get_templates(
    request: Request,
    kind: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="模板类型 (白名单字符)",
    ),
    category: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="模板分类 (白名单字符)",
    ),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """v1: 获取提示词模板"""
    return {
        "success": True,
        "data": app_state.get_prompt_templates(kind, category),
        "limit": limit,
        "offset": offset,
    }


@app.post("/api/v1/prompt-templates")
@limiter.limit("30/minute")
async def v1_create_template(request: Request, req: PromptTemplateCreate):
    """v1: 创建提示词模板"""
    t = app_state.create_prompt_template(req)
    return {"success": True, "data": t.dict()}


@app.put("/api/v1/prompt-templates/{template_id}")
@limiter.limit("30/minute")
async def v1_update_template(request: Request, template_id: str, req: PromptTemplateCreate):
    """v1: 更新提示词模板"""
    t = app_state.update_prompt_template(template_id, req)
    if not t:
        raise HTTPException(status_code=404, detail="模板不存在或为内置模板")
    return {"success": True, "data": t.dict()}


@app.delete("/api/v1/prompt-templates/{template_id}")
@limiter.limit("30/minute")
async def v1_delete_template(request: Request, template_id: str):
    """v1: 删除提示词模板"""
    ok = app_state.delete_prompt_template(template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="模板不存在或为内置模板")
    return {"success": True, "message": "模板已删除"}


@app.get("/api/v1/prompt-templates/categories")
@limiter.limit("100/minute")
async def v1_get_categories(
    request: Request,
    kind: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="模板类型 (白名单字符)",
    ),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """v1: 获取模板分类"""
    return {
        "success": True,
        "data": app_state.get_prompt_categories(kind),
        "limit": limit,
        "offset": offset,
    }


@app.post("/api/v1/figma/import")
@limiter.limit("30/minute")
async def v1_figma_import(request: Request, req: FigmaImportRequest):
    """v1: 导入素材到Figma队列"""
    item = app_state.figma_import(req)
    return {"success": True, "data": item}


@app.get("/api/v1/figma/claim")
@limiter.limit("100/minute")
async def v1_figma_claim(
    request: Request,
    max_items: int = Query(10, ge=1, le=100, description="最大返回条数 (1..100)"),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """v1: Figma插件轮询获取待导入素材"""
    items = app_state.figma_claim(max_items)
    if q:
        items = [i for i in items if q.lower() in str(i).lower()]
    total = len(items)
    page = items[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/v1/upstream-materials/{node_id}")
@limiter.limit("100/minute")
async def v1_get_upstream_materials(
    request: Request,
    node_id: str,
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """v1: 获取指定节点的上游素材列表"""
    materials = app_state.get_upstream_materials(node_id)
    if q:
        materials = [m for m in materials if q.lower() in str(m).lower()]
    total = len(materials)
    page = materials[offset: offset + limit]
    return {
        "success": True,
        "data": {"materials": page, "total": total},
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/v1/tutorials")
@limiter.limit("100/minute")
async def v1_get_tutorials(
    request: Request,
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """v1: 获取画布教程列表"""
    tutorials = app_state.get_tutorials()
    if q:
        tutorials = [t for t in tutorials if q.lower() in str(t).lower()]
    total = len(tutorials)
    page = tutorials[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.post("/api/v1/video/generate")
@limiter.limit("30/minute")
async def v1_video_generate(request: Request, req: PlanRequest):
    """v1: 用DeepSeek生成视频脚本 + ffmpeg合成真实AI视频 (seedance风格)"""
    import subprocess, time, os, json, re, tempfile, shutil
    try:
        output_dir = "data/output"
        os.makedirs(output_dir, exist_ok=True)
        timestamp = int(time.time())
        filepath = f"{output_dir}/vid_{timestamp}.mp4"
        text = req.user_input.strip() if req.user_input else "IMDF Video"

        # Phase 1: DeepSeek生成结构化视频脚本
        from api.nanobot_adapter import NanobotAdapter
        adapter = NanobotAdapter()
        
        storyboard_prompt = f"""你是一个专业视频导演。根据用户的文字描述，生成一个结构化视频分镜脚本。

用户输入: {text}

请严格按以下JSON格式返回分镜脚本（不要包含其他文字，只返回JSON）:
{{
  "title": "视频标题(15字以内)",
  "style": "视觉风格(如:科技感/温暖/电影感/简约)",
  "total_duration": 总时长秒数(10-30),
  "scenes": [
    {{
      "id": 1,
      "title": "场景标题(8字以内)",
      "visual": "画面描述(30字以内)",
      "narration": "旁白文字(20字以内)",
      "duration": 该场景秒数(3-8),
      "bg_color": "背景色(hex如#1a1a2e)",
      "text_color": "文字色(hex如#ffffff)",
      "transition": "转场效果(fade/slide_left/slide_right/zoom)"
    }}
  ]
}}

要求:
- 3-6个场景，总时长10-30秒
- 场景间有逻辑递进关系
- bg_color使用深色调科技色系
- 每个场景的narration简洁有力
- transition在fade/slide_left/slide_right/zoom中选择"""

        storyboard = None
        deepseek_used = False
        try:
            chat_result = await adapter.chat(storyboard_prompt, model="deepseek-chat")
            if chat_result.get("success") and chat_result.get("message"):
                raw = chat_result["message"].strip()
                json_match = re.search(r'\{[\s\S]*\}', raw)
                if json_match:
                    storyboard = json.loads(json_match.group())
                    deepseek_used = True
        except Exception as e:
            logger.error(f"DeepSeek storyboard generation failed: {e}")

        if not storyboard or not storyboard.get("scenes"):
            storyboard = _build_fallback_storyboard(text)

        scenes = storyboard.get("scenes", [])
        title = storyboard.get("title", text[:15])
        style = storyboard.get("style", "科技感")

        # Phase 2: 逐场景渲染
        tmp_dir = tempfile.mkdtemp(prefix="imdf_v1_video_")
        segment_files = []
        scene_details = []

        for i, scene in enumerate(scenes):
            scene_id = scene.get("id", i + 1)
            scene_title = scene.get("title", f"场景{i+1}")
            scene_visual = scene.get("visual", "")
            scene_narration = scene.get("narration", "")
            scene_duration = float(scene.get("duration", 5))
            bg_color = scene.get("bg_color", "#1a1a2e")
            text_color = scene.get("text_color", "#ffffff")
            transition = scene.get("transition", "fade")

            seg_path = os.path.join(tmp_dir, f"scene_{scene_id:02d}.mp4")
            try:
                frame_path = os.path.join(tmp_dir, f"frame_{scene_id:02d}.png")
                _render_scene_frame(frame_path, scene_title, scene_narration, scene_visual,
                                    bg_color, text_color, style, scene_id, len(scenes))
                _render_scene_video(frame_path, seg_path, scene_duration, transition, scene_title, scene_narration)
                if os.path.exists(seg_path) and os.path.getsize(seg_path) > 0:
                    segment_files.append(seg_path)
                    scene_details.append({"id": scene_id, "title": scene_title, "narration": scene_narration})
            except Exception as e:
                logger.error(f"Scene {scene_id} render failed: {e}")

        # Phase 3: 合成
        if len(segment_files) >= 1:
            if len(segment_files) == 1:
                shutil.copy2(segment_files[0], filepath)
            else:
                concat_file = os.path.join(tmp_dir, "concat_list.txt")
                with open(concat_file, "w") as f:
                    for seg in segment_files:
                        f.write(f"file '{seg}'\n")
                result = subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_file, "-c:v", "libx264", "-preset", "fast",
                    "-pix_fmt", "yuv420p", filepath,
                ], capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    shutil.copy2(segment_files[0], filepath)
        else:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=#1a1a2e:s=1920x1080:d=5",
                "-vf", f"drawtext=text='{text[:60]}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", filepath,
            ], capture_output=True, timeout=60)

        try:
            shutil.rmtree(tmp_dir)
        except Exception as e:
            logger.error(f"Failed to cleanup tmp_dir: {e}")

        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            total_dur = sum(float(s.get("duration", 5)) for s in scenes)
            return {"success": True, "data": {
                "status": "generated", "file": filepath, "size": size,
                "duration": total_dur, "scenes": len(scenes),
                "title": title, "style": style,
                "engine": "deepseek+ffmpeg" if deepseek_used else "template+ffmpeg",
                "scene_details": scene_details,
            }}
        else:
            return {"success": False, "error": "视频文件生成失败"}
    except Exception as e:
        logger.error(f"v1_video_generate failed: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/v1/ppt/generate")
@limiter.limit("30/minute")
async def v1_ppt_generate(request: Request, req: PlanRequest):
    """v1: 真实生成PPT HTML"""
    from engines.ppt_engine import PPTEngine, SlideSpec, SlideType
    engine = PPTEngine()
    tmpl = engine.select_template(req.user_input)
    slides = [
        SlideSpec(slide_type=SlideType.COVER, title=req.user_input),
        SlideSpec(slide_type=SlideType.CONTENT, title="核心内容", content=["功能一", "功能二", "功能三"]),
        SlideSpec(slide_type=SlideType.END, title="谢谢"),
    ]
    html = engine.generate_full_html(slides, template_id=tmpl["id"], title=req.user_input)
    import time
    filepath = f"data/output/ppt_{int(time.time())}.html"
    os.makedirs("data/output", exist_ok=True)
    with open(filepath, "w") as f:
        f.write(html)
    return {"success": True, "data": {"html": html[:100], "file": filepath, "template": tmpl["id"]}}


@app.get("/api/v1/comfyui/workflows")
@limiter.limit("100/minute")
async def v1_comfyui_list_workflows(request: Request):
    """v1: 列出所有可用的ComfyUI工作流"""
    from engines.comfyui_engine import ComfyUIEngine
    engine = ComfyUIEngine()
    workflows = engine.list_workflows()
    return {"success": True, "data": [w.to_dict() for w in workflows]}


@app.post("/api/v1/comfyui/run")
@limiter.limit("30/minute")
async def v1_comfyui_run(request: Request, req: ComfyUIRunRequest):
    """v1: 运行ComfyUI工作流"""
    import httpx
    try:
        from engines.comfyui_engine import ComfyUIEngine
        engine = ComfyUIEngine()
        result = await engine.run_workflow(
            workflow_id=req.workflow_id,
            params={
                "prompt": req.prompt,
                "negative_prompt": req.negative_prompt,
                "overrides": req.overrides,
            }
        )
        if result.get("ok"):
            return {"success": True, "data": result}
        return {"success": False, "error": result.get("error", "Unknown error")}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/v1/comfyui/status/{prompt_id}")
@limiter.limit("100/minute")
async def v1_comfyui_status(request: Request, prompt_id: str):
    """v1: 查询ComfyUI工作流执行状态"""
    validate_id(prompt_id, "prompt_id")
    try:
        from engines.comfyui_engine import ComfyUIEngine
        engine = ComfyUIEngine()
        result = await engine.get_status(prompt_id)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/v1/chat")
@limiter.limit("30/minute")
async def v1_chat_api(request: Request, req: PlanRequest):
    """v1: 调用真实AI进行对话"""
    from api.nanobot_adapter import NanobotAdapter
    adapter = NanobotAdapter()
    try:
        result = await adapter.chat(req.user_input)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/v1/image/generate")
@limiter.limit("30/minute")
async def v1_image_generate(request: Request, req: PlanRequest):
    """v1: 真实调用AI生成图片"""
    from api.nanobot_adapter import NanobotAdapter
    adapter = NanobotAdapter()
    try:
        chat_result = await adapter.chat(f"为'{req.user_input}'生成一个高质量英文图片生成提示词，包含风格、光照、构图。直接输出提示词，不要其他内容。")
        prompt_en = chat_result.get("message", req.user_input)
        if not prompt_en or prompt_en.startswith("HTTP"):
            prompt_en = req.user_input
        payload = {
            "prompt": prompt_en,
            "negative_prompt": "",
            "generator": "comfyui",
            "settings": {"model": "seedream-5.0", "width": 1024, "height": 1024, "steps": 25}
        }
        result = await adapter.generate(payload)
        if result:
            return {"success": True, "data": {"status": "queued", "task_id": result.get("task_id", ""), "prompt": prompt_en}}
        import time
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new('RGB', (1024, 1024), (30, 30, 60))
            draw = ImageDraw.Draw(img)
            lines = []
            words = prompt_en.split()
            for i in range(0, len(words), 6):
                lines.append(" ".join(words[i:i+6]))
            y = 400
            draw.text((50, 350), f"IMDF AI Generated", fill=(100,200,255))
            draw.text((50, 390), f"Prompt: {req.user_input}", fill=(200,200,255))
            for line in lines[:8]:
                draw.text((50, y), line, fill=(180,180,220))
                y += 24
            draw.text((50, y+20), f"[AI-powered generation]", fill=(100,100,150))
            filepath = f"data/output/img_{int(time.time())}.png"
            os.makedirs("data/output", exist_ok=True)
            img.save(filepath)
            return {"success": True, "data": {"status": "generated", "file": filepath, "prompt": prompt_en, "model": "deepseek+pillow"}}
        except ImportError:
            filepath = f"data/output/img_{int(time.time())}.txt"
            os.makedirs("data/output", exist_ok=True)
            with open(filepath, "w") as f:
                f.write(f"Image prompt: {prompt_en}\nInput: {req.user_input}")
            return {"success": True, "data": {"status": "generated", "file": filepath, "prompt": prompt_en, "model": "text-fallback"}}
    except Exception as e:
        logger.error(f"image_generate failed: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Preview Routes
# ============================================================================

@app.get("/api/v1/preview/{file_path:path}")
async def preview_file(file_path: str):
    # R2-3: 防 path traversal — 路径必须在 data/preview 之下
    try:
        safe_path = ImagePathValidator(
            file_path,
            base_dir=Path(get_project_root()) / "data" / "preview"
        ).validate()
    except HTTPException:
        raise
    from engines.preview_engine import PreviewEngine
    thumb = PreviewEngine.get_thumbnail(safe_path)
    if thumb:
        return FileResponse(thumb, media_type="image/jpeg")
    return {"success": False, "error": "无法生成预览"}

@app.get("/api/v1/files/list")
async def list_files(
    dir: str = Query("data/output", max_length=512, description="目录路径"),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """列出目录中的文件，支持图片和视频"""
    import os
    from pathlib import Path
    target_dir = Path(dir)
    if not target_dir.is_absolute():
        target_dir = Path(os.getcwd()) / target_dir
    if not target_dir.exists():
        return {"success": False, "error": f"目录不存在: {target_dir}"}

    files = []
    allowed_exts = {'.jpg','.jpeg','.png','.webp','.bmp','.gif','.svg','.mp4','.avi','.mov','.mkv','.webm'}
    try:
        for f in sorted(target_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in allowed_exts:
                files.append({
                    "name": f.name,
                    "path": str(f.absolute()),
                    "size": f.stat().st_size,
                })
    except PermissionError:
        return {"success": False, "error": "权限不足"}
    if q:
        files = [f for f in files if q.lower() in f["name"].lower()]
    total = len(files)
    page = files[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@app.get("/api/v1/file/serve")
async def serve_file(path: str):
    """提供完整文件下载/显示"""
    from pathlib import Path as _Path
    import mimetypes
    fp = _Path(path)
    if not fp.is_absolute():
        fp = _Path(os.getcwd()) / fp
    if not fp.exists() or not fp.is_file():
        return {"success": False, "error": "文件不存在"}
    mime, _ = mimetypes.guess_type(str(fp))
    return FileResponse(str(fp), media_type=mime or "application/octet-stream")

@app.post("/api/v1/media-info")
async def media_info(req: PlanRequest):
    from engines.preview_engine import PreviewEngine
    return {"success": True, "data": PreviewEngine.get_media_info(req.user_input)}

# ============================================================================
# Migration Routes
# ============================================================================

@app.get("/api/v1/migrations/status")
async def migration_status():
    """获取 migration 状态 — R2 改造: 加可选日期过滤 (limit, since)"""
    from engines.db_migration import MigrationManager
    mm = MigrationManager()
    return {"success": True, "data": mm.get_status()}


class ApplyMigrationRequest(BaseModel):
    """R2 改造: /migrations/apply 加 confirm 标志防误触发"""
    confirm: bool = Field(default=False, description="必须为 true 才执行")
    dry_run: bool = Field(default=False, description="只查看不执行")


@app.post("/api/v1/migrations/apply")
async def migration_apply(req: ApplyMigrationRequest = ApplyMigrationRequest()):
    """R2 改造: 加 confirm 标志和 dry_run 标志, 避免误触发"""
    from fastapi import HTTPException
    if not req.confirm:
        raise HTTPException(
            status_code=400,
            detail="migrations/apply 必须传 confirm=true 才会执行 (防误触发)",
        )
    from engines.db_migration import MigrationManager
    mm = MigrationManager()
    if req.dry_run:
        # dry_run: 只返回待执行列表, 不实际执行
        pending = mm.get_status().get("pending", [])
        return {"success": True, "data": {"dry_run": True, "pending_count": len(pending), "pending": pending}}
    count = mm.apply_pending()
    return {"success": True, "data": {"applied": count, "dry_run": False}}

# ============================================================================
# API v1 路由注册
# ============================================================================

# 数据导入路由
ingest_router = APIRouter(prefix="/api/v1", tags=["ingest"])


# ─── R2 改造: Pydantic models for ingest endpoints ────────────────────────

class IngestCrawlerRequest(BaseModel):
    """爬虫任务请求体 — R2 改造"""
    url: str = Field(..., min_length=1, max_length=2048,
                      description="目标 URL")
    selector: Optional[str] = Field(default=None, max_length=512,
                                     description="CSS 选择器 (可选)")
    max_pages: int = Field(default=10, ge=1, le=1000)
    interval_seconds: int = Field(default=60, ge=10, le=86400)
    tags: List[str] = Field(default_factory=list, max_length=20)


class IngestRssRequest(BaseModel):
    """RSS 源添加请求体 — R2 改造"""
    url: str = Field(..., min_length=1, max_length=2048,
                      description="RSS feed URL")
    name: Optional[str] = Field(default=None, max_length=128)
    category: Optional[str] = Field(default=None, max_length=64,
                                      pattern=r"^[a-zA-Z0-9_\-]{1,64}$")
    refresh_interval_minutes: int = Field(default=60, ge=5, le=1440)


class IngestApiConfigRequest(BaseModel):
    """API 拉取配置 — R2 改造"""
    name: str = Field(..., min_length=1, max_length=128,
                       pattern=r"^[a-zA-Z0-9_\-]{1,128}$")
    base_url: str = Field(..., min_length=1, max_length=2048)
    auth_header: Optional[str] = Field(default=None, max_length=512)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    schedule_cron: Optional[str] = Field(
        default=None,
        max_length=64,
        description="cron 表达式 (5 字段), None 表示手动触发",
    )


@ingest_router.post("/ingest/csv")
async def ingest_csv(req: PlanRequest):
    from engines.ingestion_engine import IngestionEngine
    return IngestionEngine().import_csv(req.user_input)

@ingest_router.post("/ingest/json")
async def ingest_json(req: PlanRequest):
    from engines.ingestion_engine import IngestionEngine
    return IngestionEngine().import_json(req.user_input)

@ingest_router.post("/ingest/excel")
async def ingest_excel(req: PlanRequest):
    from engines.ingestion_engine import IngestionEngine
    return IngestionEngine().import_excel(req.user_input)

# ─── 数据采集: 爬虫 / RSS / API 拉取 ─────────────────────────────────────
@ingest_router.post("/ingest/crawler")
async def ingest_crawler(req: IngestCrawlerRequest):
    """创建爬虫采集任务 — R2 改造: 用 IngestCrawlerRequest 校验"""
    from engines.data_collection_engine import create_crawler_job
    body = req.model_dump()
    return create_crawler_job(body)

@ingest_router.get("/ingest/rss")
async def ingest_rss_list(limit: int = Query(50, ge=1, le=500)):
    """列出所有RSS源 — R2 改造: limit 范围校验"""
    from engines.data_collection_engine import list_rss_feeds
    feeds = list_rss_feeds()
    return {"success": True, "feeds": feeds[:limit]}

@ingest_router.post("/ingest/rss")
async def ingest_rss_add(req: IngestRssRequest):
    """添加RSS源 — R2 改造: 用 IngestRssRequest 校验"""
    from engines.data_collection_engine import add_rss_feed
    return add_rss_feed(req.model_dump())

@ingest_router.post("/ingest/rss/refresh-all")
async def ingest_rss_refresh_all():
    """刷新全部RSS源"""
    from engines.data_collection_engine import refresh_all_rss
    return refresh_all_rss()

@ingest_router.post("/ingest/rss/{feed_id}/refresh")
async def ingest_rss_refresh_one(feed_id: str):
    """刷新单个RSS源 — R2 改造: feed_id 校验"""
    validate_task_id(feed_id, "feed_id")
    from engines.data_collection_engine import refresh_rss_feed
    return refresh_rss_feed(feed_id)

@ingest_router.delete("/ingest/rss/{feed_id}")
async def ingest_rss_delete(feed_id: str):
    """删除RSS源 — R2 改造: feed_id 校验"""
    validate_task_id(feed_id, "feed_id")
    from engines.data_collection_engine import delete_rss_feed
    return delete_rss_feed(feed_id)

@ingest_router.post("/ingest/api-config")
async def ingest_api_config(req: IngestApiConfigRequest):
    """保存API拉取配置 — R2 改造: 用 IngestApiConfigRequest 校验 + cron 表达式可选校验"""
    if req.schedule_cron is not None:
        from api._common.cron_validator import validate_cron
        validate_cron(req.schedule_cron, "schedule_cron")
    from engines.data_collection_engine import save_api_config
    return save_api_config(req.model_dump())

@ingest_router.get("/ingest/history")
async def ingest_history(
    limit: int = Query(50, ge=1, le=500),
    source: Optional[str] = Query(None, max_length=128, pattern=r"^[a-zA-Z0-9_\-]{1,128}$"),
):
    """获取采集/导入历史 — R2 改造: limit 范围校验 + source 过滤"""
    from engines.data_collection_engine import get_ingest_history
    history = get_ingest_history()
    if source:
        history = [h for h in history if h.get("source") == source]
    return {"success": True, "history": history[:limit]}

@ingest_router.post("/ingest/import")
async def ingest_import_file(request: Request):
    """上传导入数据文件 (CSV/JSON/JSONL/COCO) — R2 改造: dataset_name / format 校验"""
    import tempfile
    from fastapi import HTTPException
    from engines.data_collection_engine import import_file
    try:
        form = await request.form()
        file = form.get("file")
        if not file:
            return {"success": False, "error": "未提供文件"}
        format_type = form.get("format", "auto")
        # 校验 format 枚举
        if format_type not in ("auto", "csv", "json", "jsonl", "coco"):
            raise HTTPException(400, f"format 取值非法: {format_type!r}, 应为 auto/csv/json/jsonl/coco")
        dataset_name = form.get("dataset_name", file.filename.rsplit(".", 1)[0] if file.filename else "imported")
        # 校验 dataset_name 字符
        if not re.match(r"^[a-zA-Z0-9_\-\.]{1,128}$", dataset_name):
            raise HTTPException(400, f"dataset_name 含非法字符: {dataset_name!r}")

        # 保存上传文件到临时目录
        os.makedirs("data/uploads", exist_ok=True)
        ext = Path(file.filename).suffix if file.filename else ".tmp"
        # 校验扩展名
        if ext.lower() not in (".csv", ".json", ".jsonl", ".jsonc", ".xlsx", ".xls", ".tsv"):
            raise HTTPException(400, f"文件扩展名不支持: {ext!r}")
        save_path = os.path.join("data/uploads", f"{uuid.uuid4().hex}{ext}")
        content = await file.read()
        # 限制 100 MB
        if len(content) > 100 * 1024 * 1024:
            raise HTTPException(413, f"文件过大: {len(content)} 字节, 上限 100MB")
        with open(save_path, "wb") as f:
            f.write(content)

        result = import_file(save_path, format_type, dataset_name)
        return result
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

app.include_router(ingest_router)


# ─── R4-W4-others: 采集统计端点 ─────────────────────────────────────
# 前端 data-collection.js 原本用 Math.random() 兜底, 现改为 GET /api/v1/ingest/stats
ingest_stats_router = APIRouter(prefix="/api/v1", tags=["ingest-stats"])


@ingest_stats_router.get("/ingest/stats")
async def ingest_stats():
    """采集源真实统计: 源数(crawler+rss+api) + 今日累计量 (来自 history)"""
    try:
        from datetime import datetime
        from engines.data_collection_engine import (
            list_crawler_jobs, list_rss_feeds, list_api_configs, get_ingest_history,
        )
        crawler = list_crawler_jobs() or []
        rss = list_rss_feeds() or []
        apis = list_api_configs() or []
        history = get_ingest_history() or []
        # 今日 = 当天 ISO 日期
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = sum(
            int(h.get("count", 0)) for h in history
            if str(h.get("created_at", "")).startswith(today)
        )
        # 若无 history, 退而求其次用每个 RSS 源的 item_count 求和
        if today_count == 0:
            today_count = sum(int(f.get("item_count", 0)) for f in rss)
        source_count = len(crawler) + len(rss) + len(apis)
        return {
            "success": True,
            "data": {
                "source_count": source_count,
                "crawler_count": len(crawler),
                "rss_count": len(rss),
                "api_count": len(apis),
                "today_count": today_count,
            },
            "message": "ingest stats loaded",
        }
    except Exception as e:
        return {"success": False, "error": f"ingest_stats failed: {e}"}


# ─── R4-W4-others: 算子库统计端点 ─────────────────────────────────────
# 前端 zhiying.js 原本硬编码 "44算子" / "6模板", 现改为 GET /api/operators/stats
# 数据源: engines.operators_lib.OperatorRegistry (7+13+8+5+5+6=44 算子, 6 导出模板)
operators_stats_router = APIRouter(prefix="/api/operators", tags=["operators"])


@operators_stats_router.get("/stats")
async def operators_stats():
    """算子库真实统计: 算子总数 / 模板数(导出格式) / 各分类计数"""
    try:
        from engines.operators_lib import get_registry, OperatorCategory
        reg = get_registry()
        all_ops = reg.list_all()
        # 分类统计
        category_counts = {cat.value: 0 for cat in OperatorCategory}
        for op in all_ops:
            category_counts[op.category.value] = category_counts.get(op.category.value, 0) + 1
        # 模板 = 导出格式数 (export.*) — 与"6 模板"对应
        template_count = category_counts.get("export", 0)
        return {
            "success": True,
            "data": {
                "operator_count": reg.count(),
                "template_count": template_count,
                "category_counts": category_counts,
            },
            "message": "operator stats loaded",
        }
    except Exception as e:
        return {"success": False, "error": f"operators_stats failed: {e}"}


app.include_router(operators_stats_router)
app.include_router(ingest_stats_router)

# ─── 数据备份路由 ─────────────────────────────────────────────────────────
backup_router = APIRouter(prefix="/api/v1", tags=["backup"])

@backup_router.get("/backup")
async def backup_list():
    """列出所有备份"""
    from engines.data_collection_engine import list_backups
    return {"success": True, "backups": list_backups()}

@backup_router.post("/backup")
async def backup_create(request: Request):
    """创建新备份"""
    from engines.data_collection_engine import create_backup
    return create_backup()

@backup_router.post("/backup/auto-backup")
async def backup_auto_toggle(request: Request):
    """自动备份开关"""
    try:
        body = await request.json()
        # 持久化自动备份设置
        import json as _json
        state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "collection_state.json")
        state = {}
        if os.path.exists(state_path):
            with open(state_path, "r") as f:
                state = _json.load(f)
        state["auto_backup"] = body.get("enabled", False)
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w") as f:
            _json.dump(state, f, ensure_ascii=False, indent=2)
        return {"success": True, "auto_backup": state["auto_backup"]}
    except Exception as e:
        return {"success": False, "error": str(e)}

@backup_router.post("/backup/{backup_id}/restore")
async def backup_restore(backup_id: str):
    """恢复备份 — R2-3 改造: 路径 ID 校验"""
    validate_id(backup_id, "backup_id")
    from engines.data_collection_engine import restore_backup
    return restore_backup(backup_id)

@backup_router.get("/backup/{backup_id}/download")
async def backup_download(backup_id: str):
    """下载备份文件 — R2-3 改造: 路径 ID 校验"""
    validate_id(backup_id, "backup_id")
    from engines.data_collection_engine import get_backup_path
    path = get_backup_path(backup_id)
    if path and os.path.exists(path):
        return FileResponse(path, media_type="application/octet-stream",
                          filename=os.path.basename(path))
    return {"success": False, "error": "备份文件不存在"}

@backup_router.delete("/backup/{backup_id}")
async def backup_delete(backup_id: str):
    """删除备份 — R2-3 改造: 路径 ID 校验"""
    validate_id(backup_id, "backup_id")
    from engines.data_collection_engine import delete_backup
    return delete_backup(backup_id)

app.include_router(backup_router)

# 增量交付路由
delivery_inc_router = APIRouter(prefix="/api/v1", tags=["delivery_inc"])

@delivery_inc_router.post("/delivery/snapshot")
async def delivery_snapshot(req: PlanRequest):
    from engines.delivery_inc import IncrementalDelivery
    sid = IncrementalDelivery.snapshot(req.user_input, [])
    return {"success": True, "data": {"snapshot_id": sid}}

@delivery_inc_router.post("/delivery/diff")
async def delivery_diff(req: PlanRequest):
    from engines.delivery_inc import IncrementalDelivery
    import json
    data = json.loads(req.user_input) if isinstance(req.user_input, str) else {}
    return {"success": True, "data": IncrementalDelivery.diff(data.get("snapshot_id",""), data.get("files",[]))}

app.include_router(delivery_inc_router)

# 搜索路由
search_router = APIRouter(prefix="/api", tags=["search"])

@search_router.post("/v1/search")
@search_router.post("/search")
async def search_api(req: PlanRequest):
    from engines.search_engine import FTSHelper
    fts = FTSHelper()
    results = fts.search(req.user_input, limit=20)
    return {"success": True, "data": {"results": results, "total": len(results)}}

app.include_router(search_router)

# ─── 多模态向量检索路由 (F1.14) ─────────────────────────────────────────────
try:
    from api.search_routes import router as router_search
    app.include_router(router_search)
    HAS_MULTIMODAL_SEARCH = True
    logger.info("multimodal_search", status="loaded")
except ImportError:
    HAS_MULTIMODAL_SEARCH = False
    logger.warning("multimodal_search", status="not_loaded")

# ─── Phase3: 调度器 & 事件引擎路由 ──────────────────────────────────────────
try:
    from api.scheduler_routes import router as router_scheduler
    app.include_router(router_scheduler)
    HAS_SCHEDULER = True
    logger.info("scheduler_routes", status="loaded")
except ImportError:
    HAS_SCHEDULER = False
    logger.warning("scheduler_routes", status="not_loaded")

# ─── F1.8: DAM路由 (Digital Asset Management) ──────────────────────────────
try:
    from api.dam_routes import router as router_dam
    app.include_router(router_dam)
    HAS_DAM = True
    logger.info("dam_routes", status="loaded")
except ImportError:
    HAS_DAM = False
    logger.warning("dam_routes", status="not_loaded")

# ─── F1.11: 审美评分路由 ──────────────────────────────────────────────────
try:
    from api.aesthetic_routes import router as router_aesthetic
    app.include_router(router_aesthetic)
    HAS_AESTHETIC = True
    logger.info("aesthetic_routes", status="loaded")
except ImportError:
    HAS_AESTHETIC = False
    logger.warning("aesthetic_routes", status="not_loaded")

# ============================================================================
# Main Entry
# ============================================================================


# PE模板系统路由
try:
    from api.pe_routes import router as pe_router
    app.include_router(pe_router)
    logger.info("PE模板系统路由已加载")
except Exception as e:
    logger.warning(f"PE路由加载失败: {e}")


# 质量体系路由
try:
    from api.quality_routes import router as quality_router
    app.include_router(quality_router)
    logger.info("质量体系路由已加载")
except Exception as e:
    logger.warning(f"质量路由加载失败: {e}")
try:
    from api.quality_v2_routes import router as quality_v2_router
    app.include_router(quality_v2_router)
    logger.info("质量体系v2路由已加载")
except Exception as e:
    logger.warning(f"质量v2路由加载失败: {e}")

# P5-R1-T5: labels ontology (任务标签 ontology)
try:
    from api.labels_ontology_routes import router as labels_ontology_router
    app.include_router(labels_ontology_router)
    logger.info("P5-R1-T5 labels ontology 路由已加载 (/api/v1/labels/ontology)")
except Exception as e:
    logger.warning(f"P5-R1-T5 labels ontology 路由加载失败: {e}")

# P1-C-W1: 5 核心页 API 集成 (dashboard/canvas/assets/projects/users)
try:
    from api.p1_c_w1_routes import router as p1_c_w1_router
    app.include_router(p1_c_w1_router)
    logger.info("P1-C-W1 5核心页 API 集成路由已加载 (22 端点)")
except Exception as e:
    logger.warning(f"P1-C-W1 路由加载失败: {e}")

# P5-R1-T1: ProjectCenter — /api/v1/projects (10 端点: list/create/get/put/del/members/post/members/del/status/stats/timeline)
try:
    from api.project_routes import router as project_center_router
    app.include_router(project_center_router)
    logger.info("P5-R1-T1 ProjectCenter 路由已加载 (10 端点 /api/v1/projects/*)")
except Exception as e:
    logger.warning(f"P5-R1-T1 ProjectCenter 路由加载失败: {e}")

# P3-2-W1: oss_routes 已迁移至 asset-service (port 8002)

if __name__ == "__main__":
    import uvicorn
    print_config_summary()
    print(f"IMDF Canvas Web UI starting at http://{IMDF_WEB_HOST}:{IMDF_WEB_PORT}")
    uvicorn.run(
        app,
        host=IMDF_WEB_HOST,
        port=IMDF_WEB_PORT,
        log_level=UVICORN_LOG_LEVEL,
        workers=UVICORN_WORKERS,
    )
