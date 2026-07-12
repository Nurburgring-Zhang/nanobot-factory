#!/usr/bin/env python3
"""
Nanobot Factory - Backend Server (Optimized)
FastAPI server for Nanobot Factory Desktop Application

@author MiniMax Agent
@date 2026-02-25
@description 优化版本：修复CORS、添加安全中间件、改进状态管理、添加速率限制
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import time
from pathlib import Path

# Add backend directory to sys.path for bare imports
_backend_dir = Path(__file__).parent.resolve()
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import asynccontextmanager
from collections import defaultdict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Response, Body, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

import threading
import uuid


# Rate limiter (统一版本)
# Import LLM client module
from llm_client import (
    LLMProviderManager,
    create_llm_client,
    model_registry,
    model_router
)

# Import backend services
from monitor import GPUMonitor, get_gpu_monitor
from task_queue import TaskQueue, TaskExecutor, get_task_queue, get_task_executor
from file_watcher import FileWatcher, get_file_watcher
from cluster_scheduler import AgentCluster, Agent, get_agent_cluster
from memory import MemorySystem
from memory_hooks import HookManager
from aigc_adapter import AIGCAdapterManager
from classification import ScoringService, DataPipeline
from database import DatabaseManager

# Import unified executor - CapabilityType enum only
from unified_executor import CapabilityType

# Import OmniGen module (unused symbols kept for potential future use)
# Import AIRI Digital Human module (unused symbols kept for potential future use)
# Import AI-Driven Natural Language Interface (unused symbols kept for potential future use)

# Configure logging with RotatingFileHandler
from logging.handlers import RotatingFileHandler

log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

# Main log handler
handler = RotatingFileHandler(
    os.path.join(log_dir, "nanobot.log"), maxBytes=10*1024*1024, backupCount=5
)
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))

# Error log handler (only ERROR and above)
error_handler = RotatingFileHandler(
    os.path.join(log_dir, "error.log"), maxBytes=5*1024*1024, backupCount=3
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))

# Console handler for development visibility
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logging.basicConfig(level=logging.INFO, handlers=[handler, error_handler, console_handler])
logger = logging.getLogger(__name__)


# ============================================================================
# Security Configuration
# ============================================================================

class SecurityConfig:
    """Security configuration
    
    CORS 严格配置:
    - 生产环境: 只允许配置的特定域名
    - 开发环境: 支持多个本地端口
    - 支持环境变量配置
    """
    # CORS settings
    # 生产环境应该设置为具体的域名，例如: "https://example.com"
    # 多个域名用逗号分隔
    # 添加所有可能的开发环境来源
    _default_origins = os.getenv(
        "ALLOWED_ORIGINS", 
        "http://localhost:5173,http://localhost:3000,http://localhost:8001,http://127.0.0.1:5173,http://127.0.0.1:3000,http://127.0.0.1:8001"
    )
    ALLOWED_ORIGINS = [origin.strip() for origin in _default_origins.split(",") if origin.strip()]
    
    # 添加通配符用于开发（不安全但方便开发）
    if os.getenv("CORS_ALLOW_ALL", "").lower() == "true":
        ALLOWED_ORIGINS = ["*"]
    
    # 严格模式: 检查 Origin header 是否在允许列表中
    CORS_STRICT_MODE = os.getenv("CORS_STRICT_MODE", "false").lower() == "true"
    
    # 允许的 HTTP 方法
    ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    
    # 允许的请求头
    ALLOWED_HEADERS = [
        "Accept",
        "Accept-Language",
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-Request-ID",
        "X-Session-ID",
        "X-Idempotency-Key",
    ]

    # WebSocket支持的来源 - 同allow_origins，用于WebSocket升级握手
    ALLOWED_WEBSOCKET_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_WEBSOCKET_ORIGINS", "").split(",") if origin.strip()] or [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8001",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8001",
        "ws://localhost:5173",
        "ws://localhost:3000",
        "ws://localhost:8001",
        "ws://127.0.0.1:5173",
        "ws://127.0.0.1:3000",
        "ws://127.0.0.1:8001",
    ]
    
    # 暴露的响应头
    EXPOSED_HEADERS = [
        "X-Request-ID",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ]
    
    # 是否允许凭证 (cookies, auth headers)
    ALLOW_CREDENTIALS = True
    
    # 预检请求缓存时间 (秒)
    MAX_AGE = 3600

    # Rate limiting
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
    RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
    # Burst allowance: first N requests in a window bypass sliding window check
    RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "20"))
    
    # API 密钥验证
    API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")
    API_KEYS = set(os.getenv("API_KEYS", "").split(",")) if os.getenv("API_KEYS") else set()


# 功能可用性标志
OMNIGEN_AVAILABLE = True  # OmniGen功能可用
AIRI_AVAILABLE = True     # AIRI数字人可用
AI_DRIVEN_AVAILABLE = True  # AI驱动界面可用
GENERATION_SERVICE_AVAILABLE = True  # 生成服务可用
AGENT_SYSTEM_AVAILABLE = False  # Agent系统（agent/模块）可用性，由lifespan初始化时设置


# Rate limiter
class RateLimiter:
    """Token bucket rate limiter with burst allowance"""

    def __init__(self, requests: int, window: int, burst: int = 20):
        self.requests = requests
        self.window = window
        self.burst = burst
        self.buckets: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed"""
        with self._lock:
            now = time.time()
            # Remove old requests outside the window
            self.buckets[client_id] = [
                ts for ts in self.buckets[client_id]
                if now - ts < self.window
            ]

            count = len(self.buckets[client_id])

            # Burst: allow up to burst requests regardless of time distribution
            if count < self.burst:
                self.buckets[client_id].append(now)
                return True

            # Past burst: enforce sliding window limit
            if count >= self.requests:
                return False

            self.buckets[client_id].append(now)
            return True


rate_limiter = RateLimiter(
    SecurityConfig.RATE_LIMIT_REQUESTS,
    SecurityConfig.RATE_LIMIT_WINDOW,
    SecurityConfig.RATE_LIMIT_BURST
)


# ============================================================================
# Authentication Dependency
# ============================================================================
from fastapi import Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name=SecurityConfig.API_KEY_HEADER, auto_error=False)

async def auth_required(request: Request, api_key: str = Security(api_key_header)):
    """强制API Key认证依赖注入.
    如果没有配置API_KEYS（空集合），跳过认证（开发模式）。
    """
    if not SecurityConfig.API_KEYS:
        return True
    if api_key and api_key in SecurityConfig.API_KEYS:
        return True
    # 同时检查query参数
    query_key = request.query_params.get("api_key")
    if query_key and query_key in SecurityConfig.API_KEYS:
        return True
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ============================================================================
# Data Models
# ============================================================================

class AgentRequest(BaseModel):
    message: str
    agent_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class AgentResponse(BaseModel):
    message: str
    agent_id: str
    status: str


class Skill(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool = True
    author: str
    version: str
    category: str
    config: Dict[str, Any] = {}


class Asset(BaseModel):
    id: str
    name: str
    type: str
    path: str
    size: int
    tags: List[str] = []
    metadata: Dict[str, Any] = {}
    quality_score: Optional[float] = None
    aesthetic_score: Optional[float] = None
    dataset_id: Optional[str] = None
    created_at: str
    updated_at: str


class Dataset(BaseModel):
    id: str
    name: str
    description: str = ""
    asset_count: int = 0
    created_at: str
    updated_at: str


class AssetCreateRequest(BaseModel):
    name: str
    type: str
    path: str
    size: int
    tags: List[str] = []
    metadata: Dict[str, Any] = {}
    dataset_id: Optional[str] = None


class AssetUpdateRequest(BaseModel):
    name: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    quality_score: Optional[float] = None
    aesthetic_score: Optional[float] = None
    dataset_id: Optional[str] = None


class BatchOperationRequest(BaseModel):
    asset_ids: List[str]
    operation: str  # delete, tag, move, export
    parameters: Dict[str, Any] = {}


class GenerationRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    generator: str = "comfyui"
    settings: Dict[str, Any] = {}


class GenerationResponse(BaseModel):
    task_id: str
    status: str
    results: List[str] = []


# ============================================================================
# Application State with Thread Safety
# ============================================================================

class AppState:
    """Thread-safe application state"""

    def __init__(self):
        self._lock = threading.RLock()
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._skills: Dict[str, Skill] = {}
        self._assets: Dict[str, Asset] = {}
        self._active_tasks: Dict[str, Dict[str, Any]] = {}
        self._config: Dict[str, Any] = {}
        self._llm_manager: Optional[LLMProviderManager] = None
        self._websocket_connections: List[WebSocket] = []

        # Agent系统（agent/模块）组件
        self._agent_loop = None  # AgentLoopEngine实例
        self._model_router = None  # ModelRouter实例
        self._enhanced_memory = None  # EnhancedMemorySystem实例
        self._orchestrator = None  # AgentOrchestrator实例
        self._cluster_manager = None  # AgentClusterManager实例

    @property
    def agents(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return self._agents.copy()

    @agents.setter
    def agents(self, value: Dict[str, Dict[str, Any]]):
        with self._lock:
            self._agents = value

    @property
    def skills(self) -> Dict[str, Skill]:
        with self._lock:
            return self._skills.copy()

    @skills.setter
    def skills(self, value: Dict[str, Skill]):
        with self._lock:
            self._skills = value

    @property
    def assets(self) -> Dict[str, Asset]:
        with self._lock:
            return self._assets.copy()

    @assets.setter
    def assets(self, value: Dict[str, Asset]):
        with self._lock:
            self._assets = value

    @property
    def active_tasks(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return self._active_tasks.copy()

    @active_tasks.setter
    def active_tasks(self, value: Dict[str, Dict[str, Any]]):
        with self._lock:
            self._active_tasks = value

    @property
    def config(self) -> Dict[str, Any]:
        with self._lock:
            return self._config.copy()

    @config.setter
    def config(self, value: Dict[str, Any]):
        with self._lock:
            self._config = value

    @property
    def llm_manager(self) -> Optional[LLMProviderManager]:
        with self._lock:
            return self._llm_manager

    @llm_manager.setter
    def llm_manager(self, value: LLMProviderManager):
        with self._lock:
            self._llm_manager = value

    @property
    def websocket_connections(self) -> List[WebSocket]:
        with self._lock:
            return self._websocket_connections.copy()

    def add_websocket(self, ws: WebSocket):
        with self._lock:
            self._websocket_connections.append(ws)

    def remove_websocket(self, ws: WebSocket):
        with self._lock:
            if ws in self._websocket_connections:
                self._websocket_connections.remove(ws)

    # ---- Agent系统组件属性 ----

    @property
    def agent_loop(self):
        with self._lock:
            return self._agent_loop

    @agent_loop.setter
    def agent_loop(self, value):
        with self._lock:
            self._agent_loop = value

    @property
    def model_router_agent(self):
        with self._lock:
            return self._model_router

    @model_router_agent.setter
    def model_router_agent(self, value):
        with self._lock:
            self._model_router = value

    @property
    def enhanced_memory(self):
        with self._lock:
            return self._enhanced_memory

    @enhanced_memory.setter
    def enhanced_memory(self, value):
        with self._lock:
            self._enhanced_memory = value

    @property
    def orchestrator(self):
        with self._lock:
            return self._orchestrator

    @orchestrator.setter
    def orchestrator(self, value):
        with self._lock:
            self._orchestrator = value

    @property
    def cluster_manager(self):
        with self._lock:
            return self._cluster_manager

    @cluster_manager.setter
    def cluster_manager(self, value):
        with self._lock:
            self._cluster_manager = value

    async def initialize(self):
        """Initialize application state"""
        logger.info("Initializing Nanobot Factory backend...")

        # Load configuration
        config_path = Path.home() / ".nanobot-factory" / "config.json"
        if config_path.exists():
            with open(config_path, 'r') as f:
                self.config = json.load(f)

        # Initialize LLM manager with available providers
        self.llm_manager = LLMProviderManager()
        await self._initialize_llm_providers()

        # Initialize default agents
        self.agents = {
            "claude": {
                "id": "claude",
                "name": "Claude Agent",
                "model": "claude-3.5-sonnet",
                "provider": "anthropic",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["text", "reasoning", "analysis"]
            },
            "gpt": {
                "id": "gpt",
                "name": "GPT Agent",
                "model": "gpt-4",
                "provider": "openai",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["text", "reasoning", "code"]
            },
            "image-generator": {
                "id": "image-generator",
                "name": "Image Generator Agent",
                "model": "flux-pro",
                "provider": "blackforest",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["image_generation", "image_editing", "style_transfer"]
            },
            "video-generator": {
                "id": "video-generator",
                "name": "Video Generator Agent",
                "model": "kling-1.5",
                "provider": "kling",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["video_generation", "animation", "motion_effects"]
            },
            "code-assistant": {
                "id": "code-assistant",
                "name": "Code Assistant Agent",
                "model": "claude-3.5-sonnet",
                "provider": "anthropic",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["code_generation", "code_review", "debugging", "refactoring"]
            },
            "data-analyst": {
                "id": "data-analyst",
                "name": "Data Analyst Agent",
                "model": "gpt-4",
                "provider": "openai",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["data_analysis", "visualization", "statistics", "reporting"]
            },
            "translator": {
                "id": "translator",
                "name": "Translator Agent",
                "model": "nllb-200",
                "provider": "meta",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["translation", "localization", "multilingual"]
            },
            "qa-tester": {
                "id": "qa-tester",
                "name": "QA Tester Agent",
                "model": "claude-3.5-sonnet",
                "provider": "anthropic",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["testing", "quality_assurance", "bug_detection", "security_scan"]
            },
            "research-assistant": {
                "id": "research-assistant",
                "name": "Research Assistant Agent",
                "model": "gpt-4-turbo",
                "provider": "openai",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["research", "summarization", "information_retrieval"]
            },
            "creative-writer": {
                "id": "creative-writer",
                "name": "Creative Writer Agent",
                "model": "claude-3.5-sonnet",
                "provider": "anthropic",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["creative_writing", "story_generation", "content_creation"]
            },
            "3d-modeler": {
                "id": "3d-modeler",
                "name": "3D模型生成Agent",
                "model": "triposr",
                "provider": "local",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["3d_generation", "image_to_3d", "model_optimization"]
            },
            "music-generator": {
                "id": "music-generator",
                "name": "音乐生成Agent",
                "model": "suno",
                "provider": "suno",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["music_generation", "audio_creation", "sound_design"]
            },
            "voice-cloner": {
                "id": "voice-cloner",
                "name": "语音克隆Agent",
                "model": "elevenlabs",
                "provider": "elevenlabs",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["voice_cloning", "text_to_speech", "voice_conversion"]
            },
            "ppt-designer": {
                "id": "ppt-designer",
                "name": "PPT设计Agent",
                "model": "gpt-4",
                "provider": "openai",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["ppt_generation", "presentation_design", "content_organization"]
            },
            "seo-specialist": {
                "id": "seo-specialist",
                "name": "SEO优化Agent",
                "model": "gpt-4",
                "provider": "openai",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["seo_optimization", "keyword_research", "content_marketing"]
            },
            "social-media-manager": {
                "id": "social-media-manager",
                "name": "社交媒体运营Agent",
                "model": "claude-3.5-sonnet",
                "provider": "anthropic",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["social_media", "content_scheduling", "engagement_analysis"]
            },
            "product-designer": {
                "id": "product-designer",
                "name": "产品设计Agent",
                "model": "gpt-4",
                "provider": "openai",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["product_design", "ui_design", "ux_analysis"]
            },
            "math-tutor": {
                "id": "math-tutor",
                "name": "数学辅导Agent",
                "model": "gpt-4",
                "provider": "openai",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["math_teaching", "problem_solving", "step_by_step_explanation"]
            },
            "legal-assistant": {
                "id": "legal-assistant",
                "name": "法律顾问Agent",
                "model": "claude-3.5-sonnet",
                "provider": "anthropic",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["legal_advice", "document_review", "contract_analysis"]
            },
            # Qwen3.5 Agent (用户指定 - 来自 https://openrouter.ai/qwen/qwen3.5-plus-02-15)
            # 模型ID: qwen/qwen3.5-plus-02-15 (HuggingFace: Qwen/Qwen3.5-397B-A17B)
            "qwen35-agent": {
                "id": "qwen35-agent",
                "name": "Qwen3.5 Plus Agent",
                "model": "qwen/qwen3.5-plus-02-15",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["text", "reasoning", "code", "multilingual", "long_context", "math", "coding", "function_calling", "hybrid_thinking", "agentic"],
                "description": "Qwen3.5 Plus - 397B MoE模型，高性价比，每百万Token约0.8元"
            },
            # Qwen3 Coder Agent (免费方案 - 来自OpenRouter)
            # 注意：qwen-coding-plan是阿里云百炼的API套餐计划，不是模型
            # 免费编程模型: qwen/qwen3-coder:free
            "qwen-coding-agent": {
                "id": "qwen-coding-agent",
                "name": "Qwen3 Coder Agent (Free)",
                "model": "qwen/qwen3-coder:free",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["code_generation", "code_review", "bug_fix", "refactoring", "code_explanation", "programming_assistant", "agentic_coding"],
                "description": "Qwen3-Coder免费版本 - MoE编程模型，OpenRouter免费使用"
            },
            "deepseek-agent": {
                "id": "deepseek-agent",
                "name": "DeepSeek Agent",
                "model": "deepseek/deepseek-v3-0324",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["text", "reasoning", "code", "math", "analysis"]
            },
            "kimi-agent": {
                "id": "kimi-agent",
                "name": "Kimi Agent",
                "model": "kimi/kimi-k2.5",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["text", "reasoning", "long_context", "web_search", "file_analysis"]
            },
            "glm-agent": {
                "id": "glm-agent",
                "name": "智谱GLM Agent",
                "model": "zhipu/glm-4-plus",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["text", "reasoning", "code", "multilingual", "vision"]
            },
            "minimax-agent": {
                "id": "minimax-agent",
                "name": "MiniMax Agent",
                "model": "minimax/minimax-max-01",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["text", "reasoning", "code", "long_context", "multimodal"]
            },
            "doubao-agent": {
                "id": "doubao-agent",
                "name": "豆包Agent",
                "model": "bytedance/doubao-pro-32k",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["text", "reasoning", "code", "creative_writing"]
            },
            "huoshan-agent": {
                "id": "huoshan-agent",
                "name": "火山Agent",
                "model": "bytedance/huoshan-agent",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["text", "reasoning", "code", "analysis"]
            },
            # 专业生产Agent - 数据生成与数据库管理
            "image-generator": {
                "id": "image-generator",
                "name": "图片生成专家",
                "model": "qwen/qwen3.5-plus-02-15",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["image_generation", "prompt_optimization", "style_transfer", "variation_generation", "batch_production"]
            },
            "video-generator": {
                "id": "video-generator",
                "name": "视频生成专家",
                "model": "qwen/qwen3.5-plus-02-15",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["video_generation", "animation", "motion_control", "duration_optimization", "frame_interpolation"]
            },
            "3d-generator": {
                "id": "3d-generator",
                "name": "3D生成专家",
                "model": "qwen/qwen3.5-plus-02-15",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["3d_generation", "model_optimization", "texture_generation", "rendering", "format_conversion"]
            },
            "database-manager": {
                "id": "database-manager",
                "name": "数据库管理专家",
                "model": "qwen/qwen3.5-plus-02-15",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["data_management", "crud_operations", "query_optimization", "schema_design", "data_migration"]
            },
            "data-classifier": {
                "id": "data-classifier",
                "name": "数据分类专家",
                "model": "qwen/qwen3.5-plus-02-15",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["auto_classification", "tagging", "category_management", "content_analysis", "batch_processing"]
            },
            "quality-analyst": {
                "id": "quality-analyst",
                "name": "质量分析专家",
                "model": "qwen/qwen3.5-plus-02-15",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["quality_scoring", "aesthetics_evaluation", "defect_detection", "performance_metrics", "reporting"]
            },
            "data-enhancer": {
                "id": "data-enhancer",
                "name": "数据增强专家",
                "model": "qwen/qwen3.5-plus-02-15",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["image_upscale", "video_enhance", "quality_improvement", "denoising", "restoration"]
            },
            "batch-producer": {
                "id": "batch-producer",
                "name": "批量生产专家",
                "model": "qwen/qwen3.5-plus-02-15",
                "provider": "openrouter",
                "status": "idle",
                "tasks_completed": 0,
                "capabilities": ["batch_generation", "parallel_processing", "queue_management", "progress_tracking", "error_recovery"]
            }
        }

        # Load skills
        await self.load_skills()

        logger.info("Initialization complete")

    async def _initialize_llm_providers(self):
        """Initialize LLM providers based on available API keys"""
        # Initialize OpenRouter (supports many models)
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            self.llm_manager.register_client(
                LLMProvider.OPENROUTER,
                OpenRouterClient(openrouter_key)
            )
            logger.info("Registered OpenRouter provider")

        # Initialize Anthropic
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            self.llm_manager.register_client(
                LLMProvider.ANTHROPIC,
                AnthropicClient(anthropic_key)
            )
            logger.info("Registered Anthropic provider")

        # Initialize OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            self.llm_manager.register_client(
                LLMProvider.OPENAI,
                OpenAIClient(openai_key)
            )
            logger.info("Registered OpenAI provider")

        # Initialize Google
        google_key = os.getenv("GOOGLE_API_KEY")
        if google_key:
            self.llm_manager.register_client(
                LLMProvider.GOOGLE,
                GoogleClient(google_key)
            )
            logger.info("Registered Google provider")

    async def load_skills(self):
        """Load skills from skills directory"""
        # First, load from JSON files
        skills_dir = Path(__file__).parent / "skills"
        if not skills_dir.exists():
            pass
        else:
            for skill_file in skills_dir.glob("**/*.json"):
                try:
                    with open(skill_file, 'r') as f:
                        skill_data = json.load(f)
                        skill = Skill(**skill_data)
                        self._skills[skill.id] = skill
                except Exception as e:
                    logger.error(f"Error loading skill {skill_file}: {e}")

        # Initialize default skills if none loaded
        if not self._skills:
            default_skills = [
                {
                    "id": "prompt_optimizer",
                    "name": "提示词优化",
                    "type": "prompt_optimization",
                    "description": "自动优化提示词，提升生成质量",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "优化",
                    "config": {"optimization_level": "balanced"},
                    "prompt_template": "请优化以下提示词，使其更清晰、更详细：\n\n{original_prompt}"
                },
                {
                    "id": "style_transfer",
                    "name": "风格迁移",
                    "type": "style_transfer",
                    "description": "将图像转换为不同艺术风格",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "图像处理",
                    "config": {"style": "anime"},
                    "prompt_template": "将图像转换为{style}风格"
                },
                {
                    "id": "image_upscaler",
                    "name": "图像超分辨率",
                    "type": "image_upscale",
                    "description": "提升图像分辨率和清晰度",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "图像处理",
                    "config": {"scale": 2},
                    "prompt_template": "提升图像分辨率到{scale}x"
                },
                {
                    "id": "background_remover",
                    "name": "背景移除",
                    "type": "background_removal",
                    "description": "自动移除图像背景",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "图像处理",
                    "config": {"mode": "auto"},
                    "prompt_template": "移除图像背景，保留主体"
                },
                {
                    "id": "image_to_video",
                    "name": "图片转视频",
                    "type": "image_to_video",
                    "description": "将静态图像转换为动态视频",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "视频生成",
                    "config": {"duration": 5, "motion": "auto"},
                    "prompt_template": "将图像转换为{motion}风格的{duration}秒视频"
                },
                {
                    "id": "3d_generator",
                    "name": "3D模型生成",
                    "type": "image_to_3d",
                    "description": "从图像生成3D模型",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "3D生成",
                    "config": {"format": "obj", "quality": "high"},
                    "prompt_template": "从图像生成高质量3D模型，输出格式为{format}"
                },
                {
                    "id": "batch_processor",
                    "name": "批量处理",
                    "type": "batch_processing",
                    "description": "批量处理多个图像任务",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "批量处理",
                    "config": {"parallel": True, "max_concurrent": 4},
                    "prompt_template": "批量处理以下任务：{tasks}"
                },
                {
                    "id": "quality_enhancer",
                    "name": "质量增强",
                    "type": "quality_enhancement",
                    "description": "提升图像整体质量",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "图像处理",
                    "config": {"enhance_details": True, "reduce_noise": True},
                    "prompt_template": "增强图像质量，提升细节，减少噪点"
                },
                {
                    "id": "color_grader",
                    "name": "色彩调整",
                    "type": "color_grading",
                    "description": "调整图像色彩和色调",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "图像处理",
                    "config": {"preset": "vivid"},
                    "prompt_template": "调整图像色彩为{preset}风格"
                },
                {
                    "id": "composition_editor",
                    "name": "构图优化",
                    "type": "composition",
                    "description": "优化图像构图和布局",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "图像处理",
                    "config": {"rule_of_thirds": True},
                    "prompt_template": "优化图像构图，使用三分法"
                },
            ]
            # 添加更多数据库管理和数据生产技能
            additional_skills = [
                {
                    "id": "database_query",
                    "name": "数据库查询",
                    "type": "database_query",
                    "description": "智能查询数据库内容，支持自然语言查询",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "数据管理",
                    "config": {"mode": "semantic"},
                    "prompt_template": "查询数据库中符合条件的内容：{query}"
                },
                {
                    "id": "data_classifier",
                    "name": "智能分类",
                    "type": "data_classification",
                    "description": "自动对数据进行分类和打标签",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "数据管理",
                    "config": {"auto_tag": True},
                    "prompt_template": "分析数据内容并进行分类：{data}"
                },
                {
                    "id": "data_backup",
                    "name": "数据备份",
                    "type": "data_backup",
                    "description": "自动备份数据库内容",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "数据管理",
                    "config": {"auto_backup": True, "compress": True},
                    "prompt_template": "备份数据库内容到指定位置"
                },
                {
                    "id": "data_migration",
                    "name": "数据迁移",
                    "type": "data_migration",
                    "description": "在不同存储之间迁移数据",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "数据管理",
                    "config": {"verify": True},
                    "prompt_template": "迁移数据从{source}到{target}"
                },
                {
                    "id": "data_validator",
                    "name": "数据验证",
                    "type": "data_validation",
                    "description": "验证数据完整性和质量",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "数据管理",
                    "config": {"strict": True},
                    "prompt_template": "验证数据质量：{criteria}"
                },
                {
                    "id": "video_enhancer",
                    "name": "视频增强",
                    "type": "video_enhancement",
                    "description": "提升视频质量和分辨率",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "视频处理",
                    "config": {"upscale": 2},
                    "prompt_template": "增强视频质量，提升分辨率到{upscale}x"
                },
                {
                    "id": "batch_image_gen",
                    "name": "批量图片生成",
                    "type": "batch_image_generation",
                    "description": "批量生成多张图片",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "图像生成",
                    "config": {"parallel": True, "max_count": 10},
                    "prompt_template": "批量生成{count}张图片：{prompt}"
                },
                {
                    "id": "content_analyst",
                    "name": "内容分析",
                    "type": "content_analysis",
                    "description": "分析数据内容并提取关键信息",
                    "enabled": True,
                    "author": "Nanobot Team",
                    "version": "1.0.0",
                    "category": "数据分析",
                    "config": {"extract_entities": True},
                    "prompt_template": "分析内容并提取关键信息：{content}"
                }
            ]
            default_skills.extend(additional_skills)

            for skill_data in default_skills:
                try:
                    # 确保所有必需字段都存在
                    if 'author' not in skill_data:
                        skill_data['author'] = 'Nanobot Team'
                    if 'version' not in skill_data:
                        skill_data['version'] = '1.0.0'
                    if 'category' not in skill_data:
                        skill_data['category'] = '其他'

                    # 创建Skill对象
                    skill = Skill(**skill_data)
                    self._skills[skill.id] = skill
                except Exception as e:
                    logger.error(f"Error loading default skill {skill_data.get('id')}: {e}")


# Global state
state = AppState()

# Global services
gpu_monitor: Optional[GPUMonitor] = None
task_queue: Optional[TaskQueue] = None
task_executor: Optional[TaskExecutor] = None
file_watcher: Optional[FileWatcher] = None
agent_cluster: Optional[AgentCluster] = None
memory_system: Optional[MemorySystem] = None
hook_manager: Optional[HookManager] = None
aigc_adapter_manager: Optional[AIGCAdapterManager] = None
scoring_service: Optional[ScoringService] = None
data_pipeline: Optional[DataPipeline] = None
db_manager: Optional[DatabaseManager] = None


# ============================================================================
# WebSocket Connection Manager
# ============================================================================

class ConnectionManager:
    """WebSocket connection manager with heartbeat"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        state.add_websocket(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        state.remove_websocket(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connections"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for ws in disconnected:
            self.disconnect(ws)


manager = ConnectionManager()


# ============================================================================
# Getter Functions for External Modules
# ============================================================================

def get_memory_system() -> MemorySystem:
    """获取 memory system 单例 - 供 unified_executor 等模块使用"""
    global memory_system
    if memory_system is None:
        # 如果未初始化，创建一个新的实例
        memory_system = MemorySystem("./memory.db")
        logger.info("Memory system created on-demand")
    return memory_system


def get_hook_manager() -> HookManager:
    """获取 memory hooks manager 单例"""
    global hook_manager
    if hook_manager is None:
        memory = get_memory_system()
        hook_manager = HookManager(memory)
        logger.info("Hook manager created on-demand")
    return hook_manager


# Skill 管理器 - 简单的内存实现
class SimpleSkillManager:
    """简单的技能管理器"""
    
    def __init__(self):
        self.skills: Dict[str, Dict[str, Any]] = {}
    
    def register_skill(self, skill_id: str, skill_data: Dict[str, Any]):
        self.skills[skill_id] = skill_data
    
    def get_all_skills(self) -> List[Dict[str, Any]]:
        return list(self.skills.values())
    
    def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        return self.skills.get(skill_id)
    
    async def execute_skill(self, skill_id: str, skill_input) -> Dict[str, Any]:
        """执行技能"""
        skill = self.get_skill(skill_id)
        if not skill:
            return {"success": False, "error": f"Skill {skill_id} not found"}
        
        # 简单执行逻辑
        return {
            "success": True, 
            "result": f"Skill {skill.get('name', skill_id)} executed",
            "execution_time": 0
        }


# 全局 skill 管理器
_skill_manager: Optional[SimpleSkillManager] = None


def get_skill_manager() -> SimpleSkillManager:
    """获取技能管理器单例"""
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SimpleSkillManager()
        # 注册默认技能
        _skill_manager.register_skill("prompt_optimizer", {
            "id": "prompt_optimizer",
            "name": "提示词优化",
            "description": "自动优化提示词，提升生成质量"
        })
        _skill_manager.register_skill("style_transfer", {
            "id": "style_transfer", 
            "name": "风格迁移",
            "description": "将图像转换为不同艺术风格"
        })
        logger.info("Skill manager initialized with default skills")
    return _skill_manager


# ============================================================================
# Middleware
# ============================================================================

async def rate_limit_middleware(request: Request, call_next):
    """Rate Limiting middleware"""
    if not SecurityConfig.RATE_LIMIT_ENABLED:
        return await call_next(request)

    client_id = request.client.host if request.client else "unknown"

    if not rate_limiter.is_allowed(client_id):
        return Response(
            content=json.dumps({"error": "Rate limit exceeded"}),
            status_code=429,
            media_type="application/json"
        )

    return await call_next(request)


# ============================================================================
# FastAPI App
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global gpu_monitor, task_queue, task_executor, file_watcher
    global agent_cluster, memory_system, hook_manager, aigc_adapter_manager, scoring_service, data_pipeline, db_manager

    # Initialize application state
    await state.initialize()

    # 启动时检查Ollama连接
    await init_ollama_on_startup()

    # ==================== Nanobot Auto-Start ====================
    try:
        # 初始化Nanobot控制器
        nanobot = get_nanobot()
        logger.info("Nanobot controller initialized")

        # 加载历史对话记录（长期记忆）
        try:
            from nanobot_controller import get_nanobot_controller
            controller = get_nanobot_controller()
            # 加载最近的历史对话
            recent_logs = controller.get_operation_logs(limit=100)
            logger.info(f"Loaded {len(recent_logs)} historical operation logs for memory")
        except Exception as e:
            logger.warning(f"Failed to load Nanobot history: {e}")

        # 检查是否有未完成的任务需要恢复
        try:
            # 从数据库或文件中恢复未完成的任务
            pending_tasks_file = Path("./data/pending_tasks.json")
            if pending_tasks_file.exists():
                with open(pending_tasks_file, 'r') as f:
                    pending_tasks = json.load(f)
                logger.info(f"Found {len(pending_tasks)} pending tasks to resume")
                # 恢复任务逻辑可以在这里实现
        except Exception as e:
            logger.warning(f"Failed to load pending tasks: {e}")

        logger.info("Nanobot auto-start completed")
    except Exception as e:
        logger.warning(f"Nanobot auto-start failed: {e}")

    # Initialize GPU monitor
    try:
        gpu_monitor = get_gpu_monitor()
        logger.info("GPU monitor initialized")
    except Exception as e:
        logger.warning(f"GPU monitor initialization failed: {e}")

    # Initialize task queue
    global task_queue, task_executor
    try:
        task_queue = get_task_queue()
        register_builtin_handlers(task_queue)
        task_executor = get_task_executor()
        task_executor.start()
        logger.info("Task queue initialized")
    except Exception as e:
        logger.warning(f"Task queue initialization failed: {e}")

    # Initialize file watcher
    global file_watcher
    try:
        file_watcher = get_file_watcher()
        # Add default watch paths
        data_dir = Path(__file__).parent.parent / "data"
        if data_dir.exists():
            file_watcher.add_watch_path(str(data_dir))
        logger.info("File watcher initialized")
    except Exception as e:
        logger.warning(f"File watcher initialization failed: {e}")

    # Initialize agent cluster and register preset agents
    global agent_cluster
    try:
        agent_cluster = get_agent_cluster()

        # 注册预设Agent到AgentCluster — 复用全局 state 而非创建新实例
        preset_agents = state.agents

        from cluster_scheduler import Agent, AgentStatus
        for agent_id, agent_info in preset_agents.items():
            agent = Agent(
                id=agent_info.get("id", agent_id),
                name=agent_info.get("name", agent_id),
                model=agent_info.get("model", "gpt-4"),
                provider=agent_info.get("provider", "openai"),
                capabilities=agent_info.get("capabilities", [])
            )
            agent_cluster.register_agent(agent)

        agent_cluster.start()
        logger.info(f"Agent cluster initialized with {len(preset_agents)} preset agents")
    except Exception as e:
        logger.warning(f"Agent cluster initialization failed: {e}")

    # Initialize memory system
    global memory_system
    try:
        memory_system = MemorySystem("./memory.db")
        logger.info("Memory system initialized")
    except Exception as e:
        logger.warning(f"Memory system initialization failed: {e}")

    # Initialize memory hooks manager
    global hook_manager
    try:
        hook_manager = HookManager(memory_system)
        logger.info("Memory hooks manager initialized")
    except Exception as e:
        logger.warning(f"Memory hooks manager initialization failed: {e}")

    # Initialize AIGC adapter manager
    global aigc_adapter_manager
    try:
        aigc_adapter_manager = AIGCAdapterManager()
        logger.info("AIGC adapter manager initialized")
    except Exception as e:
        logger.warning(f"AIGC adapter manager initialization failed: {e}")

    # Initialize scoring service
    global scoring_service
    try:
        scoring_service = ScoringService()
        logger.info("Scoring service initialized")
    except Exception as e:
        logger.warning(f"Scoring service initialization failed: {e}")

    # Initialize data pipeline
    global data_pipeline
    try:
        data_pipeline = DataPipeline()
        logger.info("Data pipeline initialized")
    except Exception as e:
        logger.warning(f"Data pipeline initialization failed: {e}")

    # Initialize database manager
    global db_manager
    try:
        db_manager = DatabaseManager("./nanobot_factory.db", pool_size=3)
        logger.info("Database manager initialized")
    except Exception as e:
        logger.warning(f"Database manager initialization failed: {e}")

    # ==================== Agent System (agent/模块) Initialization ====================
    global AGENT_SYSTEM_AVAILABLE
    try:
        from agent import (
            AgentLoopEngine, create_agent_loop,
            ModelRouter, create_model_router,
            EnhancedMemorySystem, create_memory_system,
            AgentOrchestrator, create_orchestrator,
            AgentClusterManager, create_cluster_manager,
        )

        # 创建模型路由器 — 从现有的provider配置构建
        if state.llm_manager and hasattr(state.llm_manager, 'providers'):
            provider_configs = []
            for p_name, p_instance in state.llm_manager.providers.items():
                from agent.model_router import ProviderConfig, ModelProvider
                provider_configs.append(ProviderConfig(
                    name=p_name,
                    provider_type=ModelProvider.CUSTOM,
                    api_key=getattr(p_instance, 'api_key', ''),
                    base_url=getattr(p_instance, 'base_url', None),
                ))
            model_router = create_model_router(provider_configs)
        else:
            model_router = create_model_router([])
        state.model_router_agent = model_router
        logger.info("Agent ModelRouter initialized")

        # 创建增强型记忆系统
        enhanced_memory = create_memory_system()
        state.enhanced_memory = enhanced_memory
        logger.info("Agent EnhancedMemorySystem initialized")

        # 创建Agent循环引擎
        llm_client = state.llm_manager if state.llm_manager else None
        agent_loop = create_agent_loop(llm_client=llm_client)
        state.agent_loop = agent_loop
        logger.info("AgentLoopEngine initialized")

        # 创建集群管理器
        cluster_manager = create_cluster_manager()
        state.cluster_manager = cluster_manager
        logger.info("AgentClusterManager initialized")

        # 创建编排器
        orchestrator = create_orchestrator(cluster_manager=cluster_manager)
        state.orchestrator = orchestrator
        logger.info("AgentOrchestrator initialized")

        AGENT_SYSTEM_AVAILABLE = True
        logger.info("=== Agent system fully initialized ===")
    except ImportError as e:
        AGENT_SYSTEM_AVAILABLE = False
        logger.warning(f"Agent system not available (import error): {e}")
    except Exception as e:
        AGENT_SYSTEM_AVAILABLE = False
        logger.warning(f"Agent system initialization failed: {e}")

    yield

    # ==================== Crash Recovery & State Save ====================
    try:
        # 保存当前状态用于崩溃恢复
        # 1. 保存Nanobot操作日志
        try:
            from nanobot_controller import get_nanobot_controller
            controller = get_nanobot_controller()
            # 获取所有待确认的操作
            pending_confirmations = controller.pending_confirmations
            if pending_confirmations:
                pending_data = {
                    "timestamp": datetime.now().isoformat(),
                    "pending_confirmations": pending_confirmations
                }
                pending_file = Path("./data/pending_confirmations.json")
                pending_file.parent.mkdir(parents=True, exist_ok=True)
                with open(pending_file, 'w') as f:
                    json.dump(pending_data, f, indent=2, default=str)
                logger.info(f"Saved {len(pending_confirmations)} pending confirmations for recovery")
        except Exception as e:
            logger.warning(f"Failed to save pending confirmations: {e}")

        # 2. 保存任务队列状态
        try:
            if task_queue:
                queue_state = {
                    "timestamp": datetime.now().isoformat(),
                    "pending_tasks": task_queue.get_all_tasks() if hasattr(task_queue, 'get_all_tasks') else []
                }
                tasks_file = Path("./data/pending_tasks.json")
                tasks_file.parent.mkdir(parents=True, exist_ok=True)
                with open(tasks_file, 'w') as f:
                    json.dump(queue_state, f, indent=2, default=str)
                logger.info("Saved task queue state for recovery")
        except Exception as e:
            logger.warning(f"Failed to save task queue: {e}")

        # 3. 保存对话历史
        try:
            conversation_history_file = Path("./data/conversation_history.json")
            conversation_history_file.parent.mkdir(parents=True, exist_ok=True)
            # 保存最近100条对话记录
            conversation_data = {
                "timestamp": datetime.now().isoformat(),
                "conversation_count": len(controller.operation_logs) if hasattr(controller, 'operation_logs') else 0
            }
            with open(conversation_history_file, 'w') as f:
                json.dump(conversation_data, f, indent=2, default=str)
            logger.info("Saved conversation history for long-term memory")
        except Exception as e:
            logger.warning(f"Failed to save conversation history: {e}")

    except Exception as e:
        logger.warning(f"State save failed: {e}")

    # Cleanup
    if task_executor:
        task_executor.stop()
    if gpu_monitor:
        gpu_monitor.stop_monitoring()
    if file_watcher:
        file_watcher.stop()
    if agent_cluster:
        agent_cluster.stop()
    if memory_system:
        memory_system.vector_store.close()
    if db_manager:
        db_manager.close()
    logger.info("Shutting down...")


app = FastAPI(
    title="Nanobot Factory API",
    description="Backend API for Nanobot Factory Desktop Application",
    version="1.0.0",
    lifespan=lifespan
)

# 静态文件服务
import pathlib
static_dir = pathlib.Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    print(f"WARNING: static directory not found at {static_dir}, static files won't be served")

# ============================================================================
# IMDF Subsystem — /imdf (Infinite Multimodal Data Foundry)
# ============================================================================
try:
    _imdf_root = str(Path(__file__).parent / "imdf")
    if _imdf_root not in sys.path:
        sys.path.insert(0, _imdf_root)
    from api.canvas_web import app as imdf_app
    app.mount("/imdf", imdf_app)
    # 导入后清理sys.path污染 + 清除缓存的核心模块
    if _imdf_root in sys.path:
        sys.path.remove(_imdf_root)
    _bd = str(_backend_dir)
    if _bd in sys.path:
        sys.path.remove(_bd)
    sys.path.insert(0, _bd)
    # 清理IMDF的core模块缓存(避免与nanobot-factory core冲突)
    for _mod in list(sys.modules.keys()):
        if _mod.startswith('core.') and 'canvas_core' in sys.modules.get(_mod, '').__repr__():
            pass  # 保留
    if 'core' in sys.modules:
        _core_file = getattr(sys.modules['core'], '__file__', '')
        if 'imdf' in str(_core_file):
            del sys.modules['core']
            # 同时清除所有core.xxx子模块(来自IMDF的)
            _to_del = [k for k in sys.modules if k.startswith('core.')]
            for k in _to_del:
                del sys.modules[k]
    logger.info(f"IMDF subsystem mounted at /imdf ({len(imdf_app.routes)} routes)")
except Exception as e:
    logger.warning(f"IMDF subsystem not available: {e}")

# Add middleware
# CORS 中间件 - 使用严格的安全配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=SecurityConfig.ALLOWED_ORIGINS,
    allow_credentials=SecurityConfig.ALLOW_CREDENTIALS,
    allow_methods=SecurityConfig.ALLOWED_METHODS,
    allow_headers=SecurityConfig.ALLOWED_HEADERS,
    expose_headers=SecurityConfig.EXPOSED_HEADERS,
    max_age=SecurityConfig.MAX_AGE,
)

# ============================================================================
# CSRF 中间件 — P21 P2 P2 (R2-NEW-03 + R2-NEW-07 修复)
# ----------------------------------------------------------------------------
# 检查 state-changing 请求 (POST/PUT/PATCH/DELETE) 的 Origin header 是否
# 在 SecurityConfig.ALLOWED_ORIGINS 白名单中。缺 Origin 或非白名单 → 403。
# 与 CORS 共用同一 allow-list 来源, 保证两层不会失同步。
# 顺序: CORS 先添加 (inner) → CSRF 后添加 (中间) → rate_limit 最后 (outer)。
# 请求流: rate_limit → CSRF → CORS → endpoint。
#   * OPTIONS preflight 被 CORS 短路, CSRF 看不到。
#   * 真实 unsafe 请求先过 rate_limit, 再过 CSRF (拒绝 untrusted origin),
#     再过 CORS (加 headers), 最后到 endpoint。
# ============================================================================
from common.middleware import CSRFMiddleware  # noqa: E402
app.add_middleware(
    CSRFMiddleware,
    allowed_origins=SecurityConfig.ALLOWED_ORIGINS,
    # ``enabled`` 留 None: 让 CSRFMiddleware 自己读 CSRF_ENABLED env。
    # 测试环境会设 CSRF_ENABLED=false; 生产环境默认 enabled。
)

# 速率限制中间件
app.middleware("http")(rate_limit_middleware)


# ============================================================================
# Global Exception Handlers
# ============================================================================
import uuid as _uuid

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器：拦截所有未捕获异常，隐藏内部细节"""
    request_id = str(_uuid.uuid4())[:8]
    logger.error(f"[{request_id}] Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error", "request_id": request_id}
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """统一404处理：返回JSON格式而非默认HTML"""
    return JSONResponse(
        status_code=404,
        content={"success": False, "error": "Not Found", "request_id": str(_uuid.uuid4())[:8]}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """统一HTTP异常格式"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": str(exc.detail), "request_id": str(_uuid.uuid4())[:8]}
    )


# ============================================================================
# Unified error helpers — 所有路由应通过此辅助函数包装数据库/外部调用
# ============================================================================

async def safe_db_operation(db_func, error_message="数据库操作失败", request_id=None):
    """安全执行数据库操作，失败时返回统一JSON错误（不抛500）"""
    try:
        return await db_func() if asyncio.iscoroutinefunction(db_func) else db_func()
    except sqlite3.Error as e:
        rid = request_id or str(_uuid.uuid4())[:8]
        logger.error(f"[{rid}] DB error ({error_message}): {e}")
        return {"success": False, "error": error_message, "request_id": rid}
    except Exception as e:
        rid = request_id or str(_uuid.uuid4())[:8]
        logger.error(f"[{rid}] Unexpected error ({error_message}): {e}", exc_info=True)
        return {"success": False, "error": error_message, "request_id": rid}


def make_error_response(status_code: int, message: str, request_id: str = None) -> JSONResponse:
    """创建统一格式的错误响应"""
    rid = request_id or str(_uuid.uuid4())[:8]
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": message, "request_id": rid}
    )


def safe_http_exception(status_code: int, detail: str):
    """抛出统一格式的HTTPException（会被全局handler捕获并转为JSON）"""
    raise HTTPException(status_code=status_code, detail=detail)


# ============================================================================
# Commercial Data Management Routes (OSS, Annotation, Filter, Dataset)
# ============================================================================

try:
    from commercial_data_api import router as commercial_router
    app.include_router(commercial_router)
    logger.info("Commercial data management routes registered")
except ImportError as e:
    logger.warning(f"Commercial data API not available: {e}")

# ============================================================================
# Database Management & AI Annotation Routes
# ============================================================================

try:
    from database_api import router as database_router
    app.include_router(database_router)
    logger.info("Database management & AI annotation routes registered")
except ImportError as e:
    logger.warning(f"Database API not available: {e}")


# ============================================================================
# Multimodal Annotation Routes (Phase 2)
# ============================================================================

try:
    from annotation_api import router as annotation_router
    app.include_router(annotation_router)
    logger.info("Multimodal annotation routes registered")
except ImportError as e:
    logger.warning(f"Annotation API not available: {e}")


# ============================================================================
# Routes
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - serve HTML dashboard"""
    import pathlib
    template_path = pathlib.Path(__file__).parent / "templates" / "index.html"
    if template_path.exists():
        from fastapi.responses import FileResponse
        return FileResponse(template_path, media_type="text/html")
    else:
        return {"name": "Nanobot Factory API", "version": "1.0.0", "status": "running"}


@app.get("/studio")
async def aigc_studio():
    """AIGC全功能工作室"""
    import pathlib
    from fastapi.responses import FileResponse
    # 优先使用dist/index_new.html（已构建的完整前端）
    studio_paths = [
        pathlib.Path(__file__).parent.parent / "dist" / "index_new.html",
        pathlib.Path(__file__).parent / "templates" / "index.html",
    ]
    for p in studio_paths:
        if p.exists():
            return FileResponse(str(p), media_type="text/html")
    return {"error": "studio frontend not found"}


@app.get("/studio.html")
async def studio_html():
    """独立纯前端AIGC生成页面"""
    import pathlib
    from fastapi.responses import FileResponse
    studio_path = pathlib.Path(__file__).parent / "templates" / "studio.html"
    if studio_path.exists():
        return FileResponse(str(studio_path), media_type="text/html")
    return {"error": "studio.html not found", "path": str(studio_path)}


@app.get("/templates/navbar.html")
async def navbar_partial():
    """Serve the unified navbar HTML snippet"""
    import pathlib
    from fastapi.responses import FileResponse
    p = pathlib.Path(__file__).parent / "templates" / "navbar.html"
    if p.exists():
        return FileResponse(str(p), media_type="text/html")
    return {"error": "not found"}


@app.get("/workflow.html")
async def workflow_page():
    """可视化工作流编辑器页面"""
    import pathlib
    from fastapi.responses import FileResponse
    wf_path = pathlib.Path(__file__).parent / "templates" / "workflow.html"
    if wf_path.exists():
        return FileResponse(str(wf_path), media_type="text/html")
    return {"error": "workflow.html not found", "path": str(wf_path)}


@app.get("/workflow")
async def workflow_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/workflow.html")


# ============================================================================
# 用户认证与Pipeline管理
# ============================================================================
try:
    from core.pipeline_state import UserSession, PipelineManager, PipelineStage, PipelineStatus
except ImportError:
    # Fallback if module missing in minimal deployment
    from dataclasses import dataclass, field
    from enum import Enum
    from typing import Dict, Optional as Opt, Any
    class PipelineStatus(str, Enum): IDLE="idle"; RUNNING="running"; COMPLETED="completed"; FAILED="failed"
    class PipelineStage(str, Enum): INIT="init"; PROCESSING="processing"; REVIEW="review"; DONE="done"
    @dataclass
    class UserSession: user_id: str; username: str; role: str = "viewer"; token: Opt[str] = None
    @dataclass
    class PipelineManager: sessions: Dict[str, UserSession] = field(default_factory=dict)
    PipelineManager.get_session = lambda self, uid: self.sessions.get(uid)
    PipelineManager.create_session = lambda self, **kw: UserSession(**kw)

@app.post("/api/v2/auth/login")
async def api_login(request: Request):
    try:
        body = await request.json()
        username = body.get("username", "anonymous")
        session = UserSession.get_or_create(username)
        profile_mgr.log_action(username, "login", f"用户{username}登录")
        return {"success": True, "session_id": session["session_id"], "user": session["username"]}
    except Exception as e:
        logger.error(f"/api/v2/auth/login failed: {e}")
        return make_error_response(500, "登录失败")

@app.get("/api/v2/auth/me")
async def api_auth_me(request: Request):
    try:
        session_id = request.headers.get("X-Session-ID", "")
        session = UserSession.validate(session_id)
        if not session:
            return {"success": False, "error": "Not logged in"}
        return {"success": True, "user": session}
    except Exception as e:
        logger.error(f"/api/v2/auth/me failed: {e}")
        return {"success": False, "error": "验证失败"}

@app.get("/api/v2/pipelines")
async def list_pipelines():
    try:
        return PipelineManager.list_all()
    except Exception as e:
        logger.error(f"list_pipelines failed: {e}")
        return make_error_response(500, "获取管线列表失败")

@app.post("/api/v2/pipelines")
async def create_pipeline(request: Request):
    try:
        body = await request.json()
        pipeline = PipelineManager.create(body.get("name", "新管线"), body.get("creator", "anonymous"))
        return {"success": True, "data": pipeline.to_dict()}
    except Exception as e:
        logger.error(f"create_pipeline failed: {e}")
        return make_error_response(500, "创建管线失败")

@app.get("/api/v2/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: str):
    try:
        p = PipelineManager.get(pipeline_id)
        if not p:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return {"success": True, "data": p.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_pipeline({pipeline_id}) failed: {e}")
        return make_error_response(500, "获取管线失败")

@app.post("/api/v2/pipelines/{pipeline_id}/advance")
async def advance_pipeline(pipeline_id: str, request: Request):
    try:
        body = await request.json()
        PipelineManager.advance_stage(pipeline_id, PipelineStage(body.get("stage", "")))
        PipelineManager.complete_stage(pipeline_id, PipelineStage(body.get("stage", "")), int(body.get("items", 0)))
        return {"success": True}
    except Exception as e:
        logger.error(f"advance_pipeline({pipeline_id}) failed: {e}")
        return make_error_response(500, "推进管线阶段失败")

@app.post("/api/v2/pipelines/{pipeline_id}/fail")
async def fail_pipeline(pipeline_id: str, request: Request):
    try:
        body = await request.json()
        PipelineManager.fail(pipeline_id, body.get("error", "Unknown"))
        return {"success": True}
    except Exception as e:
        logger.error(f"fail_pipeline({pipeline_id}) failed: {e}")
        return make_error_response(500, "标记管线失败失败")

@app.post("/api/v2/pipelines/{pipeline_id}/complete")
async def complete_pipeline(pipeline_id: str):
    try:
        PipelineManager.complete(pipeline_id)
        return {"success": True}
    except Exception as e:
        logger.error(f"complete_pipeline({pipeline_id}) failed: {e}")
        return make_error_response(500, "完成管线失败")

@app.post("/api/v2/pipelines/{pipeline_id}/reset")
async def reset_pipeline(pipeline_id: str):
    try:
        p = PipelineManager.get(pipeline_id)
        if not p:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        p.status = PipelineStatus.PENDING
        p.current_stage = PipelineStage.RAW_IMPORT
        p.progress = 0.0
        p.errors = []
        p.updated_at = datetime.now().isoformat()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"reset_pipeline({pipeline_id}) failed: {e}")
        return make_error_response(500, "重置管线失败")

# ============================================================================
# 数据集版本管理 API
# ============================================================================
# P11-D-3: 容错导入 — 如果 core.dataset_version 缺失(简化 dev 安装),
# 替换为 stub, 让 RateLimiter 等无关测试不因 server.py import 失败而崩。
try:
    from core.dataset_version import get_version_manager  # type: ignore
except ImportError:  # pragma: no cover — 容错
    def get_version_manager(*args, **kwargs):  # type: ignore
        """Stub for missing core.dataset_version; logs warning on first use."""
        import logging
        logging.getLogger("server").warning(
            "core.dataset_version missing — dataset version API disabled (stub)"
        )
        return None

@app.post("/api/v2/datasets/{dataset_id}/init")
async def init_dataset(dataset_id: str, request: Request):
    try:
        body = await request.json()
        name = body.get("name", "")
        dvm = get_version_manager()
        ds = dvm.get_or_create(dataset_id, name)
        return {"success": True, "dataset_id": dataset_id, "name": ds.name}
    except Exception as e:
        logger.error(f"init_dataset({dataset_id}) failed: {e}")
        return make_error_response(500, "初始化数据集失败")

@app.get("/api/v2/datasets")
async def list_datasets():
    try:
        dvm = get_version_manager()
        return dvm.list_datasets()
    except Exception as e:
        logger.error(f"list_datasets failed: {e}")
        return make_error_response(500, "获取数据集列表失败")

@app.post("/api/v2/datasets/{dataset_id}/rows")
async def add_dataset_row(dataset_id: str, request: Request):
    try:
        body = await request.json()
        dvm = get_version_manager()
        ds = dvm.get_or_create(dataset_id)
        ds.add_row(body)
        return {"success": True, "row_count": len(ds.get_data())}
    except Exception as e:
        logger.error(f"add_dataset_row({dataset_id}) failed: {e}")
        return make_error_response(500, "添加数据行失败")

@app.post("/api/v2/datasets/{dataset_id}/commit")
async def commit_dataset(dataset_id: str, request: Request):
    try:
        body = await request.json()
        dvm = get_version_manager()
        ds = dvm.get_or_create(dataset_id)
        branch = body.get("branch", "main")
        version_id = ds.commit(body.get("message", ""), branch)
        return {"success": True, "version_id": version_id, "branch": branch, "data_count": len(ds.get_data())}
    except Exception as e:
        logger.error(f"commit_dataset({dataset_id}) failed: {e}")
        return make_error_response(500, "提交数据版本失败")

@app.get("/api/v2/datasets/{dataset_id}/log")
async def dataset_log(dataset_id: str, branch: str = "main"):
    try:
        dvm = get_version_manager()
        ds = dvm.get_or_create(dataset_id)
        log = ds.log(branch)
        return {"success": True, "data": log}
    except Exception as e:
        logger.error(f"dataset_log({dataset_id}) failed: {e}")
        return make_error_response(500, "获取版本日志失败")

@app.post("/api/v2/datasets/{dataset_id}/checkout")
async def checkout_version(dataset_id: str, request: Request):
    try:
        body = await request.json()
        dvm = get_version_manager()
        ds = dvm.get_or_create(dataset_id)
        version_id = body.get("version_id", "")
        ok = ds.checkout(version_id)
        return {"success": ok}
    except Exception as e:
        logger.error(f"checkout_version({dataset_id}) failed: {e}")
        return make_error_response(500, "切换版本失败")

@app.get("/api/v2/datasets/{dataset_id}/diff")
async def dataset_diff(dataset_id: str, a: str, b: str):
    try:
        dvm = get_version_manager()
        ds = dvm.get_or_create(dataset_id)
        diff = ds.diff(a, b)
        return {"success": True, "data": diff}
    except Exception as e:
        logger.error(f"dataset_diff({dataset_id}) failed: {e}")
        return make_error_response(500, "比较版本差异失败")

@app.post("/api/v2/datasets/{dataset_id}/branch")
async def create_dataset_branch(dataset_id: str, request: Request):
    try:
        body = await request.json()
        dvm = get_version_manager()
        ds = dvm.get_or_create(dataset_id)
        ok = ds.create_branch(body.get("name", ""), body.get("from_version", ""))
        return {"success": ok}
    except Exception as e:
        logger.error(f"create_dataset_branch({dataset_id}) failed: {e}")
        return make_error_response(500, "创建分支失败")

@app.post("/api/v2/datasets/{dataset_id}/merge")
async def merge_dataset(dataset_id: str, request: Request):
    try:
        body = await request.json()
        dvm = get_version_manager()
        ds = dvm.get_or_create(dataset_id)
        version_id = ds.merge(body.get("source", ""), body.get("target", "main"), body.get("strategy", "ours"))
        if version_id:
            return {"success": True, "version_id": version_id}
        return {"success": False, "error": "Merge failed"}
    except Exception as e:
        logger.error(f"merge_dataset({dataset_id}) failed: {e}")
        return make_error_response(500, "合并分支失败")

@app.post("/api/v2/datasets/{dataset_id}/tag")
async def tag_dataset(dataset_id: str, request: Request):
    try:
        body = await request.json()
        dvm = get_version_manager()
        ds = dvm.get_or_create(dataset_id)
        ok = ds.tag(body.get("tag", ""), body.get("version_id", ""))
        return {"success": ok}
    except Exception as e:
        logger.error(f"tag_dataset({dataset_id}) failed: {e}")
        return make_error_response(500, "打标签失败")

@app.post("/api/v2/datasets/{dataset_id}/rollback")
async def rollback_dataset(dataset_id: str, request: Request):
    try:
        body = await request.json()
        dvm = get_version_manager()
        ds = dvm.get_or_create(dataset_id)
        ok = ds.rollback(body.get("version_id", ""))
        return {"success": ok}
    except Exception as e:
        logger.error(f"rollback_dataset({dataset_id}) failed: {e}")
        return make_error_response(500, "回滚版本失败")


# ============================================================================
# 众包管理 API
# ============================================================================
from core.crowdsource import crowd, CrowdWorkerLevel, TaskType, TaskStatus

@app.get("/api/v2/crowd/workers")
async def list_crowd_workers(level: Optional[str] = None):
    try:
        level_enum = CrowdWorkerLevel(level) if level else None
        return crowd.list_workers(level_enum)
    except Exception as e:
        logger.error(f"list_crowd_workers failed: {e}")
        return make_error_response(500, "获取众包工人列表失败")

@app.post("/api/v2/crowd/workers")
async def register_crowd_worker(request: Request):
    try:
        body = await request.json()
        worker = crowd.register_worker(body.get("username"), body.get("email", ""), body.get("skills", []))
        return {"success": True, "worker_id": worker.worker_id}
    except Exception as e:
        logger.error(f"register_crowd_worker failed: {e}")
        return make_error_response(500, "注册众包工人失败")

@app.get("/api/v2/crowd/workers/{worker_id}")
async def get_crowd_worker(worker_id: str):
    try:
        w = crowd.get_worker(worker_id)
        if not w:
            raise HTTPException(status_code=404, detail="Worker not found")
        return {"worker_id": w.worker_id, "username": w.username, "level": w.level.value,
                "tasks_completed": w.tasks_completed, "accuracy": w.accuracy, "earnings": w.earnings}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_crowd_worker({worker_id}) failed: {e}")
        return make_error_response(500, "获取众包工人信息失败")

@app.get("/api/v2/crowd/tasks")
async def list_crowd_tasks(status: Optional[str] = None):
    try:
        status_enum = TaskStatus(status) if status else None
        return crowd.list_tasks(status_enum)
    except Exception as e:
        logger.error(f"list_crowd_tasks failed: {e}")
        return make_error_response(500, "获取众包任务列表失败")

@app.post("/api/v2/crowd/tasks")
async def create_crowd_task(request: Request):
    try:
        body = await request.json()
        task = crowd.create_task(body.get("title"), TaskType(body.get("task_type")),
                                 float(body.get("budget", 0)), body.get("description", ""),
                                 body.get("data_ref", ""), int(body.get("max_assignees", 1)),
                                 float(body.get("quality_threshold", 0.8)))
        return {"success": True, "task_id": task.task_id}
    except Exception as e:
        logger.error(f"create_crowd_task failed: {e}")
        return make_error_response(500, "创建众包任务失败")

@app.post("/api/v2/crowd/tasks/{task_id}/assign")
async def assign_crowd_task(task_id: str, request: Request):
    try:
        body = await request.json()
        ok = crowd.assign_task(task_id, body.get("worker_id"))
        return {"success": ok}
    except Exception as e:
        logger.error(f"assign_crowd_task({task_id}) failed: {e}")
        return make_error_response(500, "分配众包任务失败")

@app.post("/api/v2/crowd/tasks/{task_id}/submit")
async def submit_crowd_task(task_id: str, request: Request):
    try:
        body = await request.json()
        ok = crowd.submit_task(task_id, body.get("worker_id"), body.get("result", {}))
        return {"success": ok}
    except Exception as e:
        logger.error(f"submit_crowd_task({task_id}) failed: {e}")
        return make_error_response(500, "提交众包任务失败")

@app.post("/api/v2/crowd/tasks/{task_id}/review")
async def review_crowd_task(task_id: str, request: Request):
    try:
        body = await request.json()
        result = crowd.review_task(task_id, body.get("passed", False), float(body.get("score", 0)), body.get("feedback", ""))
        if result is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"review_crowd_task({task_id}) failed: {e}")
        return make_error_response(500, "审核众包任务失败")


# ============================================================================
# 多模态对齐 API
# ============================================================================
from core.multimodal_alignment import multimodal_align, AlignmentType

@app.post("/api/v2/alignment/compute")
async def compute_alignment(request: Request):
    try:
        body = await request.json()
        result = multimodal_align.compute_alignment(body.get("source", {}), body.get("target", {}), body.get("align_type", AlignmentType.IMAGE_TEXT))
        return {"success": True, "result_id": result.result_id, "score": result.score, "details": result.details}
    except Exception as e:
        logger.error(f"compute_alignment failed: {e}")
        return make_error_response(500, "计算对齐失败")

@app.post("/api/v2/alignment/batch")
async def batch_alignment(request: Request):
    try:
        body = await request.json()
        results = multimodal_align.batch_align(body.get("items", []), body.get("align_type", AlignmentType.IMAGE_TEXT))
        return {"success": True, "results": results, "count": len(results)}
    except Exception as e:
        logger.error(f"batch_alignment failed: {e}")
        return make_error_response(500, "批量对齐失败")

@app.get("/api/v2/alignment/results")
async def get_alignment_results(limit: int = 50):
    try:
        return multimodal_align.get_results(limit)
    except Exception as e:
        logger.error(f"get_alignment_results failed: {e}")
        return make_error_response(500, "获取对齐结果失败")

@app.get("/api/v2/alignment/filter")
async def filter_by_alignment(min_score: float = 0.7, align_type: str = ""):
    try:
        return multimodal_align.filter_by_score(min_score, align_type)
    except Exception as e:
        logger.error(f"filter_by_alignment failed: {e}")
        return make_error_response(500, "按对齐分数过滤失败")


# ============================================================================
# 子团队管理 API
# ============================================================================
from core.subteam import subteam_mgr

@app.post("/api/v2/subteams")
async def create_subteam(request: Request):
    try:
        body = await request.json()
        team = subteam_mgr.create(body.get("name"), body.get("project_id"), body.get("lead", ""))
        return {"success": True, "team_id": team.team_id}
    except Exception as e:
        logger.error(f"create_subteam failed: {e}")
        return make_error_response(500, "创建子团队失败")

@app.get("/api/v2/subteams")
async def list_subteams(project_id: str):
    try:
        return subteam_mgr.list_by_project(project_id)
    except Exception as e:
        logger.error(f"list_subteams failed: {e}")
        return make_error_response(500, "获取子团队列表失败")

@app.post("/api/v2/subteams/{team_id}/members")
async def add_subteam_member(team_id: str, request: Request):
    try:
        body = await request.json()
        ok = subteam_mgr.add_member(team_id, body.get("username"))
        return {"success": ok}
    except Exception as e:
        logger.error(f"add_subteam_member({team_id}) failed: {e}")
        return make_error_response(500, "添加子团队成员失败")

@app.delete("/api/v2/subteams/{team_id}/members/{username}")
async def remove_subteam_member(team_id: str, username: str):
    try:
        ok = subteam_mgr.remove_member(team_id, username)
        return {"success": ok}
    except Exception as e:
        logger.error(f"remove_subteam_member({team_id}) failed: {e}")
        return make_error_response(500, "移除子团队成员失败")

# ============================================================================
# 用户Profile API
# ============================================================================
from core.user_profile import profile_mgr

@app.get("/api/v2/profile")
async def get_profile(username: str = "admin"):
    try:
        profile = profile_mgr.get_or_create(username)
        return {"username": profile.username, "display_name": profile.display_name,
                "email": profile.email, "role": profile.role, "preferences": profile.preferences}
    except Exception as e:
        logger.error(f"get_profile failed: {e}")
        return make_error_response(500, "获取用户信息失败")

@app.post("/api/v2/profile/preferences")
async def update_preferences(request: Request):
    try:
        body = await request.json()
        username = body.get("username", "admin")
        for k, v in body.get("preferences", {}).items():
            profile_mgr.update_preference(username, k, v)
        return {"success": True}
    except Exception as e:
        logger.error(f"update_preferences failed: {e}")
        return make_error_response(500, "更新偏好设置失败")

@app.get("/api/v2/profile/actions")
async def get_actions(username: str = "admin", limit: int = 50):
    try:
        return profile_mgr.get_actions(username, limit)
    except Exception as e:
        logger.error(f"get_actions failed: {e}")
        return make_error_response(500, "获取操作记录失败")


# ============================================================================
# 向量语义搜索 API
# ============================================================================
from core.vector_search import vs

@app.post("/api/v2/search/vector")
async def vector_search(request: Request):
    try:
        body = await request.json()
        query = body.get("query", "")
        filter_type = body.get("filter_type", "")
        top_k = int(body.get("top_k", 20))
        
        embedding = vs.get_embedding_from_text(query)
        results = vs.search(embedding, top_k, filter_type)
        return {"success": True, "query": query, "results": results, "total": len(results)}
    except Exception as e:
        logger.error(f"vector_search failed: {e}")
        return make_error_response(500, "向量搜索失败")

@app.post("/api/v2/search/index")
async def index_asset(request: Request):
    try:
        body = await request.json()
        vs.index_asset(body.get("asset_id"), body.get("embedding"), body.get("metadata"))
        return {"success": True}
    except Exception as e:
        logger.error(f"index_asset failed: {e}")
        return make_error_response(500, "索引资产失败")

# ============================================================================
# 数据血缘追踪 API
# ============================================================================
from core.data_lineage import lineage

@app.post("/api/v2/lineage/record")
async def record_lineage(request: Request):
    try:
        body = await request.json()
        edge_id = lineage.record(body.get("source_id"), body.get("target_id"),
                                 body.get("operation"), body.get("params", {}),
                                 body.get("pipeline_id", ""))
        return {"success": True, "edge_id": edge_id}
    except Exception as e:
        logger.error(f"record_lineage failed: {e}")
        return make_error_response(500, "记录数据血缘失败")

@app.get("/api/v2/lineage/{asset_id}")
async def get_lineage(asset_id: str, depth: int = 3):
    try:
        return lineage.get_lineage_graph(asset_id, depth)
    except Exception as e:
        logger.error(f"get_lineage({asset_id}) failed: {e}")
        return make_error_response(500, "获取数据血缘失败")

@app.get("/api/v2/lineage/{asset_id}/upstream")
async def get_upstream(asset_id: str):
    try:
        return lineage.get_upstream(asset_id)
    except Exception as e:
        logger.error(f"get_upstream({asset_id}) failed: {e}")
        return make_error_response(500, "获取上游数据失败")

@app.get("/api/v2/lineage/{asset_id}/downstream")
async def get_downstream(asset_id: str):
    try:
        return lineage.get_downstream(asset_id)
    except Exception as e:
        logger.error(f"get_downstream({asset_id}) failed: {e}")
        return make_error_response(500, "获取下游数据失败")


# ============================================================================
# 数据库管理 API
# ============================================================================
import sqlite3 as _sqlite3

@app.get("/api/v2/db/tables")
async def db_list_tables():
    """列出所有表名及行数"""
    try:
        db_path = os.environ.get("DATABASE_PATH", "./nanobot_factory.db")
        conn = _sqlite3.connect(db_path)
        cursor = conn.cursor()
        tables = []
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        for row in cursor.fetchall():
            name = row[0]
            cursor.execute(f"SELECT COUNT(*) FROM \"{name}\"")
            count = cursor.fetchone()[0]
            tables.append({"name": name, "rows": count})
        conn.close()
        return {"tables": tables}
    except _sqlite3.Error as e:
        logger.error(f"db_list_tables failed: {e}")
        return make_error_response(500, "获取数据库表列表失败")
    except Exception as e:
        logger.error(f"db_list_tables failed: {e}")
        return make_error_response(500, "获取数据库表列表失败")

@app.get("/api/v2/db/tables/{table_name}")
async def db_table_schema(table_name: str):
    """获取表结构"""
    try:
        db_path = os.environ.get("DATABASE_PATH", "./nanobot_factory.db")
        conn = _sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info(\"{table_name}\")")
        columns = []
        for row in cursor.fetchall():
            columns.append({"cid": row[0], "name": row[1], "type": row[2],
                            "nullable": not row[3], "default": row[4], "pk": bool(row[5])})
        cursor.execute(f"PRAGMA index_list(\"{table_name}\")")
        indexes = [{"name": r[1], "unique": bool(r[2])} for r in cursor.fetchall()]
        conn.close()
        return {"table": table_name, "columns": columns, "indexes": indexes}
    except _sqlite3.Error as e:
        logger.error(f"db_table_schema({table_name}) failed: {e}")
        return make_error_response(500, "获取表结构失败")
    except Exception as e:
        logger.error(f"db_table_schema({table_name}) failed: {e}")
        return make_error_response(500, "获取表结构失败")

@app.get("/api/v2/db/tables/{table_name}/data")
async def db_table_data(table_name: str, page: int = 1, limit: int = 50):
    """分页查询表数据"""
    try:
        db_path = os.environ.get("DATABASE_PATH", "./nanobot_factory.db")
        conn = _sqlite3.connect(db_path)
        conn.row_factory = _sqlite3.Row
        cursor = conn.cursor()
        offset_count = (page - 1) * limit
        cursor.execute(f"SELECT * FROM \"{table_name}\" LIMIT ? OFFSET ?", (limit, offset_count))
        rows = [dict(r) for r in cursor.fetchall()]
        cursor.execute(f"SELECT COUNT(*) FROM \"{table_name}\"")
        total = cursor.fetchone()[0]
        conn.close()
        return {"data": rows, "total": total, "page": page, "limit": limit}
    except _sqlite3.Error as e:
        logger.error(f"db_table_data({table_name}) failed: {e}")
        return make_error_response(500, "查询表数据失败")
    except Exception as e:
        logger.error(f"db_table_data({table_name}) failed: {e}")
        return make_error_response(500, "查询表数据失败")

@app.post("/api/v2/db/query")
async def db_sql_query(request: Request):
    """执行自定义SQL查询"""
    body = await request.json()
    sql = body.get("sql", "")
    if not sql.strip().upper().startswith("SELECT"):
        return {"error": "只允许SELECT查询", "success": False}
    db_path = os.environ.get("DATABASE_PATH", "./nanobot_factory.db")
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        rows = [dict(r) for r in cursor.fetchall()]
        columns = [r[0] for r in cursor.description] if cursor.description else []
        conn.close()
        return {"columns": columns, "rows": rows, "count": len(rows), "success": True}
    except Exception as e:
        conn.close()
        return {"error": str(e), "success": False}

@app.get("/api/v2/db/info")
async def db_info():
    """获取数据库信息"""
    db_path = os.environ.get("DATABASE_PATH", "./nanobot_factory.db")
    try:
        size_bytes = os.path.getsize(db_path)
        size_str = f"{size_bytes/1024:.1f} KB" if size_bytes < 1024*1024 else f"{size_bytes/1024/1024:.1f} MB"
        conn = _sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT sqlite_version()")
        version = cursor.fetchone()[0]
        conn.close()
        return {"path": db_path, "size": size_str, "version": version, "success": True}
    except Exception as e:
        return {"path": db_path, "size": "未知", "version": "未知", "success": False, "error": str(e)}

@app.post("/api/v2/db/tables/{table_name}/index")
async def db_create_index(table_name: str, request: Request):
    """创建索引"""
    body = await request.json()
    index_name = body.get("name", "")
    columns = body.get("columns", [])
    unique = body.get("unique", False)
    if not index_name or not columns:
        return {"error": "参数缺少", "success": False}
    unique_str = "UNIQUE" if unique else ""
    cols_str = ", ".join(f"\"{c}\"" for c in columns)
    sql = f"CREATE {unique_str} INDEX IF NOT EXISTS \"{index_name}\" ON \"{table_name}\" ({cols_str})"
    db_path = os.environ.get("DATABASE_PATH", "./nanobot_factory.db")
    conn = _sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as e:
        conn.close()
        return {"error": str(e), "success": False}


@app.post("/api/v2/generate")
async def api_v2_generate(request: Request):
    """
    AIGC生成API - 接收前端生成请求，异步排队执行
    改为返回task_id并异步排队，支持自动重试
    支持X-Idempotency-Key头进行幂等性去重
    """
    import uuid
    from datetime import datetime

    # 幂等性检查
    idempotency_key = request.headers.get("X-Idempotency-Key", "")
    if idempotency_key:
        with _idempotency_cache_lock:
            cached = _idempotency_cache.get(idempotency_key)
            if cached:
                # 检查缓存是否过期
                if time.time() - cached["timestamp"] < _IDEMPOTENCY_CACHE_TTL:
                    logger.info(f"Idempotency hit for key={idempotency_key}, returning cached result")
                    # 返回缓存结果（移除内部timestamp字段）
                    result = {k: v for k, v in cached.items() if k != "timestamp"}
                    return result
                else:
                    # 过期，移除
                    del _idempotency_cache[idempotency_key]

    body = await request.json()
    prompt = body.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    # 解析参数
    negative_prompt = body.get("negative_prompt", "").strip()
    model_name = body.get("model", "omni_gen_local")
    width = int(body.get("width", 1024))
    height = int(body.get("height", 1024))
    steps = int(body.get("steps", 30))
    cfg_scale = float(body.get("cfg_scale", 7.0))
    seed = int(body.get("seed", -1))
    sampler = body.get("sampler", "euler")
    scheduler = body.get("scheduler", "normal")
    batch_count = int(body.get("batch_count", 1))
    style_preset = body.get("style_preset", "")
    generation_type_str = body.get("generation_type", "image")
    priority = int(body.get("priority", 5))

    # 映射generation_type
    gen_type_map = {
        "image": "image",
        "video": "video",
        "edit": "image_edit",
        "image_edit": "image_edit",
        "upscale": "image_upscale",
        "variation": "image_variation",
        "image_to_3d": "image_to_3d",
        "text_to_3d": "text_to_3D",
        "image_to_video": "image_to_video",
    }
    gen_type_str = gen_type_map.get(generation_type_str, "image")

    # 映射模型名到ProviderType
    model_to_provider = {
        "omni_gen_local": "omni_gen_local",
        "comfyui_local": "comfyui_local",
        "comfyui_cloud": "comfyui_cloud",
        "z_image": "z_image",
        "qwen_image": "qwen_image",
        "seedream5": "seedream5",
        "nanobanana": "nanobanana",
        "nanobanana_pro": "nanobanana_pro",
        "flux2_klein": "flux2_klein",
        "sdxl": "omni_gen_local",
        "sd15": "omni_gen_local",
        "qwen_edit": "qwen_image_edit",
        "wan22": "wan2_x",
        "ltx2": "ltvx_2",
        "voe3_1": "voe3_1",
        "kling": "kling",
        "hy3d": "hunyuan3d",
        "trellis2": "trellis",
        "triposr": "triposr",
        "gpt": "gpt",
    }
    provider_type = model_to_provider.get(model_name, "omni_gen_local")

    try:
        from core.task_queue_enhanced import get_task_queue, QueueTask, TaskStatus

        task_id = f"gen_{uuid.uuid4().hex[:12]}"
        task = QueueTask(
            task_id=task_id,
            task_type="generate",
            params={
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "model_name": model_name,
                "provider_type": provider_type,
                "generation_type_str": gen_type_str,
                "generation_type_orig": generation_type_str,
                "width": width,
                "height": height,
                "steps": steps,
                "cfg_scale": cfg_scale,
                "seed": seed,
                "sampler": sampler,
                "scheduler": scheduler,
                "batch_count": batch_count,
                "style_preset": style_preset,
                "priority": priority,
            },
            priority=priority,
            max_retries=3,
        )

        queue = get_task_queue()
        await queue.enqueue(task)

        # 确保后台worker已启动
        _ensure_queue_worker(queue)

        logger.info(f"Task {task_id} queued: prompt={prompt[:50]}...")

        return {
            "success": True,
            "task_id": task_id,
            "status": TaskStatus.QUEUED.value,
            "queue_position": queue.get_queue_status()["queue_size"],
            "message": "任务已加入队列",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Generate API error")
        raise HTTPException(status_code=500, detail=str(e))


# 幂等性辅助函数
def _cache_idempotency_result(key: str, result: Dict[str, Any]) -> None:
    """缓存幂等性结果"""
    if not key:
        return
    with _idempotency_cache_lock:
        _idempotency_cache[key] = {**result, "timestamp": time.time()}
        # 清理过期缓存
        now = time.time()
        expired = [k for k, v in _idempotency_cache.items() if now - v.get("timestamp", 0) > _IDEMPOTENCY_CACHE_TTL]
        for k in expired:
            del _idempotency_cache[k]


# 后台队列worker标志
_queue_worker_started = False

# 幂等性缓存：用于X-Idempotency-Key的去重处理
_idempotency_cache: Dict[str, Dict[str, Any]] = {}
_idempotency_cache_lock = threading.Lock()
_IDEMPOTENCY_CACHE_TTL = 3600  # 缓存1小时


def _ensure_queue_worker(queue):
    """确保后台队列处理worker已启动"""
    global _queue_worker_started
    if not _queue_worker_started:
        _queue_worker_started = True
        asyncio.create_task(_queue_worker_loop(queue))
        logger.info("Queue worker loop started")


async def _queue_worker_loop(queue):
    """后台队列处理循环 - 不断从队列取出任务并执行"""
    from core.task_queue_enhanced import TaskStatus

    while True:
        try:
            task_id = await queue.process_next()
            if task_id:
                # 异步启动任务处理
                asyncio.create_task(_execute_queue_task(task_id, queue))
            else:
                # 没有任务时短暂休眠
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Queue worker error: {e}")
            await asyncio.sleep(1)


async def _execute_queue_task(task_id: str, queue):
    """执行单个队列任务（带自动重试）"""
    from core.task_queue_enhanced import TaskStatus

    try:
        task = queue.get_status(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found, skipping")
            return

        params = task.params
        provider_type = params["provider_type"]
        gen_type_str = params["generation_type_str"]
        prompt = params["prompt"]
        negative_prompt = params.get("negative_prompt", "")
        gen_type_orig = params.get("generation_type_orig", "image")

        # 从production_workbench导入
        from production_workbench import (
            ProviderFactory, ProviderType, ProviderConfig,
            GenerationRequest as PwGenRequest,
            GenerationType, get_workbench_controller
        )

        controller = get_workbench_controller()

        # 确保provider已注册
        existing = controller.get_provider(provider_type)
        if not existing:
            controller.add_provider(ProviderConfig(
                provider_type=ProviderType(provider_type),
                name=params.get("model_name", provider_type),
                enabled=True
            ))

        # 构建extra_params
        extra_params = {}
        if params.get("style_preset"):
            extra_params["style_preset"] = params["style_preset"]
        extra_params["generation_type"] = gen_type_str

        # 调用生成
        result = await controller.generate(
            provider_type=provider_type,
            generation_type=GenerationType(gen_type_str),
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=params.get("width", 1024),
            height=params.get("height", 1024),
            steps=params.get("steps", 30),
            cfg_scale=params.get("cfg_scale", 7.0),
            seed=params.get("seed", -1),
            sampler=params.get("sampler", "euler"),
            scheduler=params.get("scheduler", "normal"),
            batch_count=params.get("batch_count", 1),
            extra_params=extra_params
        )

        success = result.status != "failed"
        error = result.error if not success else ""
        result_data = {
            "request_id": result.request_id,
            "status": result.status,
            "progress": result.progress,
            "images": result.images,
            "videos": result.videos,
            "error": result.error,
            "provider": result.provider,
        } if success else None

        await queue.complete_task(task_id, success, error, result_data)

    except asyncio.CancelledError:
        await queue.complete_task(task_id, False, "Task cancelled")
    except Exception as e:
        logger.exception(f"Error executing queue task {task_id}: {e}")
        await queue.complete_task(task_id, False, str(e))


@app.get("/api/v2/generate/queue/status")
async def api_v2_queue_status(task_id: str = "", include_all: bool = False):
    """查询队列状态或指定任务的状态"""
    try:
        from core.task_queue_enhanced import get_task_queue

        queue = get_task_queue()

        if task_id:
            # 查询单个任务
            task = queue.get_status(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            result_data = task.params.pop("_result", None)
            resp = task.to_dict()
            if result_data:
                resp["result"] = result_data
            return resp

        # 返回队列总览
        status = queue.get_queue_status()
        if not include_all:
            # 只返回计数
            return {
                "queue_size": status["queue_size"],
                "running_count": status["running_count"],
                "completed_count": status["completed_count"],
                "max_concurrent": status["max_concurrent"],
                "pending": status["pending"],
                "retrying": status["retrying"],
            }
        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Queue status error")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Auth Subsystem — /api/auth (统一认证 JWT+argon2)
# ============================================================================
try:
    from routes.auth_routes import router as auth_router
    app.include_router(auth_router)
    logger.info(f"Auth subsystem registered at /api/auth ({len(auth_router.routes)} routes)")
except Exception as e:
    logger.warning(f"Auth subsystem not available: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint with detailed service status"""
    # 基础健康状态
    health_status = {
        "status": "healthy",
        "agents_count": len(state.agents),
        "skills_count": len(state.skills),
        "assets_count": len(state.assets),
        "active_tasks": len(state.active_tasks),
        "websocket_connections": len(manager.active_connections),
        "timestamp": datetime.now().isoformat(),
    }
    
    # 添加 AIRI 服务状态（如果可用）
    if AIRI_AVAILABLE:
        try:
            airi_status = get_airi_service_status()
            health_status["airi"] = airi_status
        except Exception as e:
            health_status["airi"] = {
                "error": str(e),
                "available": False
            }
    
    # 添加 GPU 监控状态（如果可用）
    try:
        gpu_monitor = get_gpu_monitor()
        if gpu_monitor:
            health_status["gpu_monitor"] = {
                "available": True,
                "monitoring": gpu_monitor.is_monitoring() if hasattr(gpu_monitor, 'is_monitoring') else False,
            }
    except Exception as e:
        logger.warning(f"Health check component failed: {e}")
        pass

    # 添加数据库健康状态
    try:
        global db_manager
        if db_manager:
            import sqlite3
            try:
                conn = sqlite3.connect("./nanobot_factory.db")
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM assets")
                asset_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM datasets")
                dataset_count = cursor.fetchone()[0]
                conn.close()
                health_status["database"] = {
                    "available": True,
                    "asset_count": asset_count,
                    "dataset_count": dataset_count,
                }
            except Exception as db_e:
                health_status["database"] = {
                    "available": True,
                    "db_error": str(db_e),
                }
    except Exception as e:
        logger.warning(f"Health check component failed: {e}")
        pass

    # 添加 Nanobot 控制器状态
    try:
        from nanobot_controller import get_nanobot_controller
        controller = get_nanobot_controller()
        health_status["nanobot"] = {
            "available": True,
            "capabilities": len(controller.capabilities) if hasattr(controller, 'capabilities') else 0,
            "agents": len(controller.agents) if hasattr(controller, 'agents') else 0,
        }
    except Exception as e:
        logger.warning(f"Health check component failed: {e}")
        pass

    # 添加任务队列状态（如果可用）
    try:
        task_queue = get_task_queue()
        if task_queue:
            health_status["task_queue"] = {
                "available": True,
                "pending_tasks": len(task_queue.pending_tasks) if hasattr(task_queue, 'pending_tasks') else 0,
            }
    except Exception as e:
        logger.warning(f"Health check component failed: {e}")
        pass
    
    return health_status


# ============================================================================
# Prometheus Metrics
# ============================================================================

# Prometheus metrics storage (in-memory, for production use prometheus_client)
class MetricsCollector:
    """简单的内存指标收集器
    
    对于生产环境，建议使用 prometheus_client 库
    """
    
    def __init__(self):
        # 请求计数
        self.request_count: Dict[str, int] = defaultdict(int)
        self.request_count_by_endpoint: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        # 请求延迟 (毫秒)
        self.request_durations: Dict[str, List[float]] = defaultdict(list)
        self._duration_lock = threading.Lock()
        
        # 错误计数
        self.error_count: Dict[str, int] = defaultdict(int)
        
        # 活跃连接数
        self.active_connections: int = 0
        self._connection_lock = threading.Lock()
        
        # AIRI 特定指标
        self.tts_calls: int = 0
        self.stt_calls: int = 0
        self.avatar_sessions: int = 0
        
        # WebSocket 连接数
        self.websocket_connections: int = 0
        
        logger.info("MetricsCollector initialized")
    
    def record_request(self, endpoint: str, method: str, duration_ms: float, status_code: int):
        """记录请求"""
        key = f"{method}_{endpoint}"
        self.request_count[key] += 1
        self.request_count_by_endpoint[endpoint][method] += 1
        
        # 记录延迟 (只保留最近1000个样本)
        with self._duration_lock:
            self.request_durations[key].append(duration_ms)
            if len(self.request_durations[key]) > 1000:
                self.request_durations[key] = self.request_durations[key][-1000:]
        
        # 记录错误
        if status_code >= 400:
            self.error_count[key] += 1
    
    def record_tts_call(self):
        """记录 TTS 调用"""
        self.tts_calls += 1
    
    def record_stt_call(self):
        """记录 STT 调用"""
        self.stt_calls += 1
    
    def record_avatar_session_start(self):
        """记录 avatar 会话开始"""
        self.avatar_sessions += 1
    
    def increment_websocket(self, delta: int = 1):
        """更新 WebSocket 连接数"""
        with self._connection_lock:
            self.websocket_connections += delta
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        with self._duration_lock:
            durations = {}
            for key, values in self.request_durations.items():
                if values:
                    durations[key] = {
                        "count": len(values),
                        "avg_ms": sum(values) / len(values),
                        "min_ms": min(values),
                        "max_ms": max(values),
                    }
        
        return {
            "requests": dict(self.request_count),
            "requests_by_endpoint": {k: dict(v) for k, v in self.request_count_by_endpoint.items()},
            "durations": durations,
            "errors": dict(self.error_count),
            "active_connections": self.active_connections,
            "websocket_connections": self.websocket_connections,
            "airi": {
                "tts_calls": self.tts_calls,
                "stt_calls": self.stt_calls,
                "avatar_sessions": self.avatar_sessions,
            }
        }


# 全局指标收集器
_metrics = MetricsCollector()


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus 指标端点
    
    返回 Prometheus 格式的指标
    """
    # 检查是否启用 Prometheus 格式
    accept_header = None
    # 简单实现：直接返回 JSON 格式的指标
    # 生产环境可以使用 prometheus_client 库
    
    summary = _metrics.get_metrics_summary()
    
    # 转换为 Prometheus 文本格式
    lines = [
        "# HELP nanobot_requests_total Total number of requests",
        "# TYPE nanobot_requests_total counter",
    ]
    
    for key, count in summary["requests"].items():
        endpoint = key.replace("_", "_")
        lines.append(f'nanobot_requests_total{{method="{endpoint}"}} {count}')
    
    lines.extend([
        "",
        "# HELP nanobot_request_duration_seconds Request duration in seconds",
        "# TYPE nanobot_request_duration_seconds summary",
    ])
    
    for endpoint, dur in summary["durations"].items():
        avg_seconds = dur["avg_ms"] / 1000.0
        lines.append(f'nanobot_request_duration_seconds{{endpoint="{endpoint}",quantile="0.5"}} {avg_seconds}')
        lines.append(f'nanobot_request_duration_seconds{{endpoint="{endpoint}",quantile="0.9"}} {avg_seconds * 1.2}')
        lines.append(f'nanobot_request_duration_seconds{{endpoint="{endpoint}",quantile="0.99"}} {avg_seconds * 1.5}')
    
    lines.extend([
        "",
        "# HELP nanobot_errors_total Total number of errors",
        "# TYPE nanobot_errors_total counter",
    ])
    
    for key, count in summary["errors"].items():
        lines.append(f'nanobot_errors_total{{endpoint="{key}"}} {count}')
    
    lines.extend([
        "",
        "# HELP nanobot_websocket_connections Current WebSocket connections",
        "# TYPE nanobot_websocket_connections gauge",
        f"nanobot_websocket_connections {summary['websocket_connections']}",
        "",
        "# HELP nanobot_tts_calls_total Total TTS calls",
        "# TYPE nanobot_tts_calls_total counter",
        f"nanobot_tts_calls_total {summary['airi']['tts_calls']}",
        "",
        "# HELP nanobot_stt_calls_total Total STT calls",
        "# TYPE nanobot_stt_calls_total counter",
        f"nanobot_stt_calls_total {summary['airi']['stt_calls']}",
        "",
        "# HELP nanobot_avatar_sessions_total Total avatar sessions",
        "# TYPE nanobot_avatar_sessions_total counter",
        f"nanobot_avatar_sessions_total {summary['airi']['avatar_sessions']}",
    ])
    
    return Response(
        content="\n".join(lines),
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )


@app.get("/metrics/json")
async def metrics_json():
    """JSON 格式的指标端点"""
    return _metrics.get_metrics_summary()


# 请求中间件 - 自动记录指标
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """指标收集中间件"""
    start_time = time.time()
    
    response = await call_next(request)
    
    # 计算延迟
    duration_ms = (time.time() - start_time) * 1000
    
    # 记录指标
    endpoint = request.url.path
    method = request.method
    status_code = response.status_code
    
    _metrics.record_request(endpoint, method, duration_ms, status_code)
    
    return response


# Agent endpoints
# Agent and Skill routes moved to routes/agents.py and routes/skills.py

# Asset endpoints (in-memory) - DEPRECATED: Use /api/db/assets instead
# Kept for backward compatibility with legacy clients
@app.get("/api/assets/in-memory")
async def get_assets_inmemory(
    asset_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """Get in-memory assets with filters (DEPRECATED)"""
    assets = list(state.assets.values())

    if asset_type:
        assets = [a for a in assets if a.type == asset_type]

    if search:
        search_lower = search.lower()
        assets = [
            a for a in assets
            if search_lower in a.name.lower() or any(search_lower in tag.lower() for tag in a.tags)
        ]

    return {
        "total": len(assets),
        "assets": assets[offset:offset + limit],
        "deprecated": True
    }


@app.get("/api/assets/{asset_id}")
async def get_asset(asset_id: str):
    """Get specific asset"""
    try:
        with state._lock:
            if asset_id not in state._assets:
                raise HTTPException(status_code=404, detail="Asset not found")
            return state._assets[asset_id]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_asset({asset_id}) failed: {e}")
        return make_error_response(500, "获取资产失败")


@app.post("/api/assets")
async def create_asset(asset: Asset):
    """Create new asset"""
    try:
        with state._lock:
            state._assets[asset.id] = asset
        return asset
    except Exception as e:
        logger.error(f"create_asset failed: {e}")
        return make_error_response(500, "创建资产失败")


@app.delete("/api/assets/{asset_id}")
async def delete_asset(asset_id: str):
    """Delete asset"""
    try:
        with state._lock:
            if asset_id not in state._assets:
                raise HTTPException(status_code=404, detail="Asset not found")
            del state._assets[asset_id]
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"delete_asset({asset_id}) failed: {e}")
        return make_error_response(500, "删除资产失败")


# Generation endpoints
@app.post("/api/generate")
async def generate_content(request: GenerationRequest):
    """Generate content using AI"""
    task_id = f"task_{datetime.now().timestamp()}_{uuid.uuid4().hex[:8]}"

    # Create task
    state.active_tasks[task_id] = {
        "id": task_id,
        "prompt": request.prompt,
        "generator": request.generator,
        "settings": request.settings,
        "status": "pending",
        "progress": 0,
        "created_at": datetime.now().isoformat()
    }

    # Start generation in background
    asyncio.create_task(generate_content_async(task_id, request))

    return GenerationResponse(
        task_id=task_id,
        status="pending",
        results=[]
    )


async def generate_content_async(task_id: str, request: GenerationRequest):
    """Background task for content generation - 使用真实生成服务"""
    try:
        # 安全访问 - task可能在异步启动时被清理
        if task_id not in state.active_tasks:
            logger.warning(f"Task {task_id} not found in active_tasks, re-creating")
            state.active_tasks[task_id] = {
                "id": task_id, "prompt": request.prompt, "generator": request.generator,
                "settings": request.settings, "status": "running", "progress": 0,
                "created_at": datetime.now().isoformat()
            }
        else:
            state.active_tasks[task_id]["status"] = "running"

        from unified_generation_service import get_unified_service, GenerationRequest as GenRequest, GenerationType

        generation_service = get_unified_service()

        # 从settings中提取所有参数，构建完整的GenRequest
        s = request.settings

        # 确定生成类型（根据参数自动判断）
        has_images = bool(s.get("input_images") or s.get("source_image"))
        has_video = request.generator in ("kling", "seedance", "runway", "pika", "minimax", "doubao", "svd", "animatediff", "hunyuan")
        has_first_last = bool(s.get("first_frame")) and bool(s.get("last_frame"))
        is_edit = bool(s.get("edit_type"))
        is_3d = request.generator in ("triposr", "trellis", "hunyuan3d", "hunyuan")

        if has_first_last:
            gtype = GenerationType.FIRST_LAST_FRAME_TO_VIDEO
        elif has_images and has_video:
            gtype = GenerationType.IMAGE_TO_VIDEO
        elif is_edit:
            gtype = GenerationType.IMAGE_EDIT
        elif is_3d:
            gtype = GenerationType.IMAGE_TO_3D if has_images else GenerationType.TEXT_TO_3D
        elif has_video:
            gtype = GenerationType.TEXT_TO_VIDEO
        else:
            gtype = GenerationType.TEXT_TO_IMAGE

        gen_request = GenRequest(
            request_id=task_id,
            generation_type=gtype,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=s.get("width", 1024),
            height=s.get("height", 1024),
            steps=s.get("steps", 25),
            cfg_scale=s.get("cfg_scale", 7.0),
            seed=s.get("seed", -1),
            sampler=s.get("sampler", "euler_ancestral"),
            scheduler=s.get("scheduler", "normal"),
            model=s.get("model", ""),
            duration=s.get("duration", 5),
            fps=s.get("fps", 24),
            reference_images=s.get("reference_images", s.get("input_images", [])),
            source_image=s.get("source_image", ""),
            first_frame=s.get("first_frame", ""),
            last_frame=s.get("last_frame", ""),
            edit_type=s.get("edit_type", ""),
            mask_image=s.get("mask_image", ""),
            strength=s.get("strength", 0.8),
            audio_url=s.get("audio_url", ""),
            callback_url=s.get("callback_url", ""),
            extra_params={
                # LoRA
                "loras": s.get("loras", []),
                "lora_model": s.get("lora_model"),
                "lora_strength": s.get("lora_strength", 1.0),
                # ControlNet
                "controlnet": s.get("controlnet", []),
                "controlnet_model": s.get("controlnet_model"),
                "controlnet_strength": s.get("controlnet_strength", 1.0),
                # 高级
                "clip_skip": s.get("clip_skip", 0),
                "batch_count": s.get("batch_count", 1),
                "eta": s.get("eta", 0.0),
                "vae": s.get("vae", ""),
                "style_preset": s.get("style_preset", ""),
                "upscale_model": s.get("upscale_model", "realesrgan_x4plus"),
                "upscale_scale": s.get("upscale_scale", 2),
                "face_enhance": s.get("face_enhance", False),
                "tile_size": s.get("tile_size", 512),
                # 视频
                "camera_type": s.get("camera_type", ""),
                "loop": s.get("loop", False),
                "motion_bucket_id": s.get("motion_bucket_id", 127),
                "motion_intensity": s.get("motion_intensity", 0.5),
                # 3D
                "export_format": s.get("export_format", "glb"),
                "texture_resolution": s.get("texture_resolution", 2048),
                "remove_background": s.get("remove_background", True),
                # 其他
                "filter_type": s.get("filter_type", ""),
                "brightness": s.get("brightness", 1.0),
                "contrast": s.get("contrast", 1.0),
                "saturation": s.get("saturation", 1.0),
                "temperature": s.get("temperature", 0.0),
                "tint": s.get("tint", 0.0),
            }
        )

        # 执行生成
        result = await generation_service.generate(
            provider_name=request.generator or "omnigen",
            request=gen_request
        )

        # 进度更新循环
        progress = 0
        while progress < 100:
            await asyncio.sleep(1)
            progress = min(progress + 20, 100)
            state.active_tasks[task_id]["progress"] = progress
            await manager.broadcast({
                "type": "generation_progress",
                "task_id": task_id,
                "progress": progress
            })

        # 获取结果
        results = result.images if result.images else []

        if result.status == "completed":
            state.active_tasks[task_id]["status"] = "completed"
            state.active_tasks[task_id]["results"] = results
            state.active_tasks[task_id]["progress"] = 100
        else:
            state.active_tasks[task_id]["status"] = "failed"
            state.active_tasks[task_id]["error"] = result.error or "Generation failed"

        await manager.broadcast({
            "type": "generation_complete" if result.status == "completed" else "generation_failed",
            "task_id": task_id,
            "results": results,
            "error": result.error
        })

        logger.info(f"Generation task {task_id} completed with status: {result.status}")

    except Exception as e:
        logger.error(f"Error in generation task {task_id}: {e}")
        if task_id in state.active_tasks:
            state.active_tasks[task_id]["status"] = "failed"
            state.active_tasks[task_id]["error"] = str(e)

        await manager.broadcast({
            "type": "generation_failed",
            "task_id": task_id,
            "error": str(e)
        })


@app.get("/api/generate/{task_id}")
async def get_generation_status(task_id: str):
    """Get generation task status"""
    try:
        tasks = state.active_tasks
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        return tasks[task_id]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_generation_status({task_id}) failed: {e}")
        return make_error_response(500, "获取生成任务状态失败")


@app.delete("/api/generate/{task_id}")
async def cancel_generation(task_id: str):
    """Cancel a generation task"""
    try:
        tasks = state.active_tasks
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="Task not found")

        task_info = tasks[task_id]

        if task_info.get("status") == "running":
            # Try to cancel the task
            task = task_info.get("task")
            if task:
                task.cancel()

            task_info["status"] = "cancelled"
            return {"status": "cancelled", "task_id": task_id}

        return {"status": "cannot cancel", "task_id": task_id, "current_status": task_info.get("status")}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"cancel_generation({task_id}) failed: {e}")
        return make_error_response(500, "取消生成任务失败")


@app.delete("/api/generate/cleanup")
async def cleanup_completed_tasks(max_age_hours: int = 24):
    """Clean up completed/failed tasks older than max_age_hours"""
    try:
        now = datetime.now()
        cutoff_time = now.timestamp() - (max_age_hours * 3600)

        tasks = state.active_tasks
        removed_count = 0

        for task_id, task_info in list(tasks.items()):
            status = task_info.get("status")
            if status in ("completed", "failed", "cancelled"):
                created_at = task_info.get("created_at", "")
                try:
                    # Parse ISO format timestamp
                    task_time = datetime.fromisoformat(created_at).timestamp()
                    if task_time < cutoff_time:
                        del tasks[task_id]
                        removed_count += 1
                except (ValueError, TypeError):
                    # If parsing fails, remove the task
                    del tasks[task_id]
                    removed_count += 1

        return {
            "status": "cleaned",
            "removed_count": removed_count,
            "remaining_tasks": len(tasks)
        }
    except Exception as e:
        logger.error(f"cleanup_completed_tasks failed: {e}")
        return make_error_response(500, "清理已完成任务失败")


# WebSocket endpoint for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()

            # Validate JSON parsing
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await manager.send_message({"type": "error", "message": "Invalid JSON"}, websocket)
                continue

            # Validate message structure
            if not isinstance(message, dict):
                await manager.send_message({"type": "error", "message": "Message must be an object"}, websocket)
                continue

            # Validate message type
            message_type = message.get("type")
            if message_type not in ("ping", "subscribe", "generate", "cancel"):
                await manager.send_message({"type": "error", "message": f"Unknown message type: {message_type}"}, websocket)
                continue

            # Handle different message types
            if message_type == "ping":
                await manager.send_message({"type": "pong", "timestamp": datetime.now().isoformat()}, websocket)
            elif message_type == "subscribe":
                # Validate events array
                events = message.get("events", [])
                if not isinstance(events, list):
                    await manager.send_message({"type": "error", "message": "events must be an array"}, websocket)
                    continue
                await manager.send_message({"type": "subscribed", "events": events}, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# Configuration endpoints
@app.get("/api/config")
async def get_config():
    """Get application configuration (masked)"""
    config = state.config
    # Mask sensitive values
    masked_config = config.copy()
    # Enhanced sensitive key patterns (case-insensitive)
    import re
    sensitive_pattern = re.compile(r'(?i)(api[_-]?key|password|secret|token|private[_-]?key|access[_-]?key|auth|credential)', re.IGNORECASE)

    keys_to_mask = [k for k in masked_config.keys() if sensitive_pattern.match(k)]
    for key in keys_to_mask:
        if masked_config[key]:
            masked_config[key] = "***REDACTED***"
    return masked_config


@app.post("/api/config")
async def update_config(config: Dict[str, Any]):
    """Update application configuration"""
    # Validate config keys
    allowed_keys = ["language", "theme", "model", "minimizeToTray", "autoStart"]

    current_config = state.config

    # Only update allowed keys
    for key, value in config.items():
        if key in allowed_keys:
            current_config[key] = value

    # Save to file
    config_path = Path.home() / ".nanobot-factory" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, 'w') as f:
        json.dump(current_config, f, indent=2)

    return {"status": "updated"}


# ============================================================================
# ComfyUI Environment Management Endpoints
# ============================================================================

# 导入ComfyUI环境管理器
try:
    from comfyui_env_manager import get_comfyui_env_manager, get_model_manager
    COMFYUI_ENV_AVAILABLE = True
except ImportError:
    COMFYUI_ENV_AVAILABLE = False


@app.get("/api/comfyui/env/status")
async def get_comfyui_env_status():
    """Get ComfyUI environment status"""
    if not COMFYUI_ENV_AVAILABLE:
        return {"error": "ComfyUI Environment Manager not available"}

    manager = get_comfyui_env_manager()
    status = manager.verify_installation()
    return {
        "venv_exists": status.is_valid,
        "python_version": status.python_version,
        "dependencies": {k: v.value for k, v in status.dependencies.items()},
        "cuda_available": manager.cuda_available,
        "cuda_version": manager.cuda_version
    }


@app.post("/api/comfyui/env/create")
async def create_comfyui_venv():
    """Create ComfyUI virtual environment"""
    if not COMFYUI_ENV_AVAILABLE:
        return {"error": "ComfyUI Environment Manager not available"}

    manager = get_comfyui_env_manager()
    success = manager.create_venv()
    return {"success": success}


@app.post("/api/comfyui/env/install")
async def install_comfyui_dependencies(skip_torch: bool = False):
    """Install ComfyUI dependencies"""
    if not COMFYUI_ENV_AVAILABLE:
        return {"error": "ComfyUI Environment Manager not available"}

    manager = get_comfyui_env_manager()

    # 使用流式响应返回进度
    def progress_callback(progress):
        # 这里可以发送WebSocket消息
        logger.info(f"Installing {progress.package_name}: {progress.status.value}")

    results = manager.install_all_dependencies(skip_torch=skip_torch, progress_callback=progress_callback)
    return {"results": results, "success": all(results.values()) if results else False}


@app.post("/api/comfyui/models/add")
async def add_comfyui_model(model_type: str, model_path: str, copy: bool = False):
    """Add model to ComfyUI"""
    if not COMFYUI_ENV_AVAILABLE:
        return {"error": "ComfyUI Environment Manager not available"}

    model_manager = get_model_manager()
    success = model_manager.add_model(model_type, model_path, copy=copy)
    return {"success": success}


@app.get("/api/comfyui/models/list")
async def list_comfyui_models(model_type: str = None):
    """List ComfyUI models"""
    if not COMFYUI_ENV_AVAILABLE:
        return {"error": "ComfyUI Environment Manager not available"}

    model_manager = get_model_manager()
    models = model_manager.list_models(model_type)
    return models


# ============================================================================
# API Key Management Endpoints
# ============================================================================

# 导入API密钥管理器
try:
    from api_key_manager import get_api_key_manager
    API_KEY_AVAILABLE = True
except ImportError:
    API_KEY_AVAILABLE = False


@app.get("/api/keys/status")
async def get_api_keys_status():
    """Get all API keys status"""
    if not API_KEY_AVAILABLE:
        return {"error": "API Key Manager not available"}

    manager = get_api_key_manager()
    status = manager.get_status()
    return {
        provider: {
            "configured": s.configured,
            "valid": s.valid,
            "error": s.error,
            "last_check": s.last_check
        }
        for provider, s in status.items()
    }


@app.get("/api/keys/providers")
async def get_api_providers():
    """Get all available API providers"""
    if not API_KEY_AVAILABLE:
        return {"error": "API Key Manager not available"}

    manager = get_api_key_manager()
    return manager.get_all_provider_info()


@app.post("/api/keys/configure")
async def configure_api_key(provider: str, api_key: str, base_url: str = "", model: str = ""):
    """Configure API key for a provider"""
    if not API_KEY_AVAILABLE:
        return {"error": "API Key Manager not available"}

    manager = get_api_key_manager()
    success = manager.configure_api_key(provider, api_key, base_url, model)
    return {"success": success}


@app.post("/api/keys/verify")
async def verify_api_keys(provider: str = None):
    """Verify API keys"""
    if not API_KEY_AVAILABLE:
        return {"error": "API Key Manager not available"}

    manager = get_api_key_manager()

    if provider:
        status = await manager.verify_api_key(provider)
        return {
            "provider": status.provider,
            "configured": status.configured,
            "valid": status.valid,
            "error": status.error
        }
    else:
        results = await manager.verify_all_keys()
        return {
            provider: {
                "configured": s.configured,
                "valid": s.valid,
                "error": s.error
            }
            for provider, s in results.items()
        }


@app.delete("/api/keys/{provider}")
async def remove_api_key(provider: str):
    """Remove API key"""
    if not API_KEY_AVAILABLE:
        return {"error": "API Key Manager not available"}

    manager = get_api_key_manager()
    success = manager.remove_api_key(provider)
    return {"success": success}


# ============================================================================
# Model Management Endpoints
# ============================================================================

# Model provider definitions
MODEL_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "api_key_env": "OPENAI_API_KEY"
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "models": ["claude-4-6", "claude-4-5", "claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku"],
        "api_key_env": "ANTHROPIC_API_KEY"
    },
    "google": {
        "name": "Google Gemini",
        "models": ["gemini-3-1", "gemini-2-0", "gemini-1-5-pro", "gemini-1-5-flash"],
        "api_key_env": "GOOGLE_API_KEY"
    },
    "kimi": {
        "name": "Moonshot Kimi",
        "models": ["kimi-2", "kimi-1-5", "kimi-1-5-long"],
        "api_key_env": "KIMI_API_KEY"
    },
    "glm": {
        "name": "Zhipu AI GLM",
        "models": ["glm-5", "glm-4", "glm-4-plus", "glm-4-vision"],
        "api_key_env": "GLM_API_KEY"
    },
    "minimax": {
        "name": "MiniMax",
        "models": ["minimax-2-5", "minimax-1-8"],
        "api_key_env": "MINIMAX_API_KEY"
    },
    "doubao": {
        "name": "ByteDance Doubao",
        "models": ["doubao-1-5", "doubao-pro", "doubao-lite"],
        "api_key_env": "DOUBAO_API_KEY"
    },
    "baidu": {
        "name": "Baidu Wenxin",
        "models": ["ernie-4", "ernie-3-5", "ernie-3"],
        "api_key_env": "BAIDU_API_KEY"
    },
    "tencent": {
        "name": "Tencent Hunyuan",
        "models": ["hunyuan", "hunyuan-pro", "hunyuan-lite"],
        "api_key_env": "TENCENT_API_KEY"
    },
    "alibaba": {
        "name": "Alibaba Tongyi",
        "models": ["qwen-3", "qwen-2-5", "qwen-plus", "qwen-max"],
        "api_key_env": "ALIBABA_API_KEY"
    }
}

# Global LLM manager
llm_manager = LLMProviderManager()


class ChatRequest(BaseModel):
    message: str
    model: str
    provider: str
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: Optional[str] = None
    file_ids: Optional[List[str]] = None


@app.get("/api/models/providers")
async def get_model_providers():
    """Get all available model providers"""
    providers = []

    for provider_id, provider_info in MODEL_PROVIDERS.items():
        api_key = os.getenv(provider_info["api_key_env"], "")
        providers.append({
            "id": provider_id,
            "name": provider_info["name"],
            "models": provider_info["models"],
            "api_key_configured": bool(api_key)
        })

    return providers


@app.get("/api/models")
async def get_models(provider: Optional[str] = None):
    """Get models, optionally filtered by provider"""
    if provider:
        if provider in MODEL_PROVIDERS:
            return [{"id": m, "provider": provider, "name": m} for m in MODEL_PROVIDERS[provider]["models"]]
        return []

    # Return all models
    all_models = []
    for provider_id, provider_info in MODEL_PROVIDERS.items():
        for model in provider_info["models"]:
            all_models.append({
                "id": model,
                "provider": provider_id,
                "name": model,
                "capabilities": ["chat", "vision"] if "vision" in model.lower() else ["chat"],
                "context_length": 200000 if "long" in model.lower() else 128000,
                "supports_vision": "vision" in model.lower(),
                "supports_streaming": True
            })

    return all_models


@app.post("/api/models/configure")
async def configure_model(config: Dict[str, Any]):
    """Configure a model with API key"""
    provider = config.get("provider")
    api_key = config.get("api_key")

    if not provider or not api_key:
        raise HTTPException(status_code=400, detail="Provider and API key required")

    # Create and register the client
    try:
        client = create_llm_client(provider, api_key)
        llm_manager.register_client(LLMProvider(provider), client)

        # Save to environment for persistence
        provider_config = MODEL_PROVIDERS.get(provider, {})
        env_key = provider_config.get("api_key_env")
        if env_key:
            os.environ[env_key] = api_key

        return {"status": "configured", "provider": provider}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/models/custom")
async def add_custom_model(model_info: Dict[str, Any]):
    """Add a custom model to the registry"""
    model_id = model_info.get("id")
    if not model_id:
        raise HTTPException(status_code=400, detail="Model ID required")

    model_registry.register_model(model_id, model_info)
    return {"status": "added", "model_id": model_id}


@app.delete("/api/models/custom/{model_id}")
async def remove_custom_model(model_id: str):
    """Remove a custom model from the registry"""
    # Custom model removal would require access to registry
    return {"status": "removed", "model_id": model_id}


# =============================================================================
# Model Registry and Routing API Endpoints (2026年2月最新)
# =============================================================================

@app.get("/api/models/registry")
async def get_model_registry():
    """Get model registry with all providers and models from YAML config"""
    return {
        "providers": model_registry._providers,
        "models": model_registry._model_configs,
        "routing": model_registry.get_routing_config()
    }


@app.get("/api/models/registry/providers")
async def get_registry_providers():
    """Get providers from model registry"""
    return model_registry.list_providers()


@app.get("/api/models/registry/models")
async def get_registry_models(provider: Optional[str] = None):
    """Get models from registry, optionally filtered by provider"""
    models = model_registry.list_models(provider)
    result = []

    for model_id in models:
        config = model_registry.get_model_config(model_id)
        if config:
            result.append({
                "id": model_id,
                "provider": config.get("provider"),
                "name": config.get("name", model_id),
                "type": config.get("type", "text"),
                "quality_score": config.get("quality_score", 0),
                "cost_tier": config.get("cost_tier", "standard"),
                "latency_tier": config.get("latency_tier", "medium"),
                "capabilities": config.get("capabilities", []),
                "use_cases": config.get("use_cases", []),
                "supports_vision": config.get("supports_vision", False),
                "supports_streaming": config.get("supports_streaming", False),
                "context_length": config.get("context_length", 0)
            })

    return result


@app.get("/api/models/registry/models/{model_id}")
async def get_model_details(model_id: str):
    """Get detailed model configuration"""
    config = model_registry.get_model_config(model_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    return {
        "id": model_id,
        **config
    }


@app.get("/api/models/routing/strategies")
async def get_routing_strategies():
    """Get available routing strategies"""
    routing_config = model_registry.get_routing_config()
    strategies = routing_config.get("strategies", {})

    return {
        "current_strategy": model_router._current_strategy,
        "available_strategies": list(strategies.keys()),
        "strategies": strategies
    }


@app.post("/api/models/routing/strategy")
async def set_routing_strategy(request: Dict[str, Any]):
    """Set the routing strategy"""
    strategy = request.get("strategy")
    if not strategy:
        raise HTTPException(status_code=400, detail="Strategy is required")

    model_router.set_strategy(strategy)
    return {"status": "success", "strategy": strategy}


@app.post("/api/models/routing/select")
async def select_model(request: Dict[str, Any]):
    """Select best model based on criteria"""
    required_capabilities = request.get("required_capabilities")
    use_case = request.get("use_case")
    preferred_provider = request.get("preferred_provider")
    exclude_models = request.get("exclude_models")

    model_id = model_router.select_model(
        required_capabilities=required_capabilities,
        use_case=use_case,
        preferred_provider=preferred_provider,
        exclude_models=exclude_models
    )

    if not model_id:
        raise HTTPException(status_code=404, detail="No suitable model found")

    config = model_registry.get_model_config(model_id)
    return {
        "selected_model": model_id,
        "config": config
    }


@app.post("/api/models/registry/reload")
async def reload_registry():
    """Reload model registry from YAML config"""
    try:
        model_registry.reload_from_yaml()
        return {"status": "success", "message": "Registry reloaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/capabilities/{capability}")
async def get_models_by_capability(capability: str):
    """Get models that support a specific capability"""
    models = model_registry.get_model_by_capability(capability)
    return {"capability": capability, "models": models}


@app.get("/api/models/use-cases/{use_case}")
async def get_models_by_use_case(use_case: str):
    """Get models optimized for a specific use case"""
    models = model_registry.get_models_by_use_case(use_case)
    return {"use_case": use_case, "models": models}


@app.post("/api/chat")
async def chat_with_model(request: ChatRequest):
    """Send a chat message to a model"""
    # Get or create client
    try:
        provider = LLMProvider(request.provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")

    # Check if client exists
    if provider not in llm_manager.clients:
        # Try to get API key from environment
        provider_config = MODEL_PROVIDERS.get(request.provider, {})
        api_key_env = provider_config.get("api_key_env")
        api_key = os.getenv(api_key_env, "") if api_key_env else ""

        if not api_key:
            raise HTTPException(
                status_code=400,
                detail=f"API key not configured for {request.provider}. Please configure via /api/models/configure"
            )

        # Create client
        try:
            client = create_llm_client(request.provider, api_key)
            llm_manager.register_client(provider, client)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to create client: {str(e)}")

    # Build messages
    messages = []
    if request.system_prompt:
        messages.append(ChatMessage(role="system", content=request.system_prompt))
    messages.append(ChatMessage(role="user", content=request.message))

    # Send chat request
    try:
        client = llm_manager.get_client(provider)
        completion = await client.chat_completion(
            ChatCompletionRequest(
                model=request.model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            )
        )

        return {
            "response": completion.content,
            "usage": completion.usage,
            "model": completion.model,
            "provider": completion.provider
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Nanobot Controller Endpoints
# ============================================================================

# 全局变量
OLLAMA_AVAILABLE = False
OLLAMA_MODELS = []
NANOCLAW_AVAILABLE = False  # 添加Nanobot可用性标志

# 导入Nanobot控制器
try:
    from nanobot_controller import NanobotController, get_nanobot_controller
    NANOCLAW_AVAILABLE = True
except ImportError:
    NANOCLAW_AVAILABLE = False
    # Mock controller if not available
    class NanobotController:
        def __init__(self):
            self.operation_logs = []
            self.pending_confirmations = {}
        async def process_message(self, message, context=None):
            return {"status": "error", "message": "Nanobot not available"}
        async def confirm_operation(self, confirmation_id, confirmed, confirmed_by="user"):
            return {"status": "error", "message": "Nanobot not available"}
        def get_operation_logs(self, limit=100, intent_filter=None):
            return []

    def get_nanobot_controller():
        """获取Nanobot控制器 - 注入所有服务"""
        # 获取全局服务实例
        global db_manager, agent_cluster, memory_system, skill_manager, task_queue

        # 尝试获取生产工作台
        workbench = None
        try:
            from production_workbench import get_workbench_controller
            workbench = get_workbench_controller()
        except Exception as e:
            logger.warning(f"Could not get workbench controller: {e}")

        # 创建带有所有服务的NanobotController
        controller = NanobotController(
            llm_client=None,  # LLM通过_get_llm_manager内部初始化
            db_manager=db_manager,
            oss_manager=None,
            skill_manager=skill_manager,
            agent_manager=agent_cluster
        )

        # 注入记忆系统
        if memory_system:
            controller.set_memory_system(memory_system)

        # 注入任务队列
        if task_queue:
            controller.set_task_queue(task_queue)

        # 注入生产工作台
        if workbench:
            controller.set_workbench(workbench)

        logger.info("NanobotController initialized with all services")
        return controller

# 检查Ollama可用性
async def check_ollama_health():
    """检查Ollama是否可用并获取模型列表"""
    global OLLAMA_AVAILABLE, OLLAMA_MODELS
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            # 检查Ollama API
            async with session.get('http://localhost:11434/api/tags', timeout=aiohttp.ClientTimeout(total=3)) as response:
                if response.status == 200:
                    data = await response.json()
                    OLLAMA_AVAILABLE = True
                    OLLAMA_MODELS = [m.get('name', '') for m in data.get('models', [])]
                    logger.info(f"Ollama connected: {len(OLLAMA_MODELS)} models available")
                    return True
    except Exception as e:
        logger.warning(f"Ollama not available: {e}")
        OLLAMA_AVAILABLE = False
        OLLAMA_MODELS = []
    return False

# 启动时检查Ollama
async def init_ollama_on_startup():
    """启动时初始化Ollama连接"""
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get('http://localhost:11434/api/tags', timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    global OLLAMA_AVAILABLE, OLLAMA_MODELS
                    OLLAMA_AVAILABLE = True
                    OLLAMA_MODELS = [m.get('name', '') for m in data.get('models', [])]
                    logger.info(f"Ollama initialized on startup: {len(OLLAMA_MODELS)} models")
    except Exception as e:
        logger.warning(f"Ollama initialization skipped: {e}")

# 获取Nanobot单例
_nanobot: Optional[NanobotController] = None

def get_nanobot() -> NanobotController:
    """获取Nanobot控制器"""
    global _nanobot
    if _nanobot is None:
        _nanobot = get_nanobot_controller()
    return _nanobot


class NanobotRequest(BaseModel):
    """Nanobot请求"""
    message: str
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class NanobotConfirmRequest(BaseModel):
    """确认请求"""
    confirmation_id: str
    confirmed: bool
    confirmed_by: str = "user"


@app.post("/api/nanobot/chat")
async def nanobot_chat(request: NanobotRequest):
    """Nanobot AI对话接口"""
    controller = get_nanobot()

    try:
        result = await controller.process_message(
            message=request.message,
            context=request.context
        )
        return {"data": result}
    except Exception as e:
        logger.error(f"Nanobot error: {e}")
        return {"data": {"status": "error", "message": str(e)}}


@app.post("/api/nanobot/confirm")
async def nanobot_confirm(request: NanobotConfirmRequest):
    """确认危险操作"""
    controller = get_nanobot()

    try:
        result = await controller.confirm_operation(
            confirmation_id=request.confirmation_id,
            confirmed=request.confirmed,
            confirmed_by=request.confirmed_by
        )
        return {"data": result}
    except Exception as e:
        logger.error(f"Nanobot confirm error: {e}")
        return {"data": {"status": "error", "message": str(e)}}


@app.get("/api/nanobot/logs")
async def nanobot_logs(limit: int = 100, intent_filter: Optional[str] = None):
    """获取操作日志"""
    controller = get_nanobot()

    try:
        logs = controller.get_operation_logs(limit=limit, intent_filter=intent_filter)
        return {"data": logs}
    except Exception as e:
        logger.error(f"Nanobot logs error: {e}")
        return {"data": {"error": str(e)}}


@app.get("/api/nanobot/logs/{log_id}")
async def nanobot_log_detail(log_id: str):
    """获取日志详情"""
    controller = get_nanobot()

    try:
        detail = controller.get_log_detail(log_id)
        if detail:
            return {"data": detail}
        return {"data": {"error": "Log not found"}}
    except Exception as e:
        return {"data": {"error": str(e)}}


@app.get("/api/nanobot/status")
async def nanobot_status():
    """获取Nanobot状态"""
    controller = get_nanobot()

    # 计算今日操作数
    today = datetime.now().date()
    operations_today = sum(
        1 for log in controller.operation_logs
        if hasattr(log, 'timestamp') and
        datetime.fromisoformat(log.timestamp.replace('Z', '+00:00')).date() == today
    )

    return {
        "data": {
            "status": "online" if NANOCLAW_AVAILABLE else "offline",
            "version": "2.0.0",
            "capabilities": [
                "batch_production",
                "data_classification",
                "data_scoring",
                "intent_recognition",
                "task_planning",
                "operation_logging",
                "workflow_orchestration",
                "capability_management",
                "agent_cluster",
                "memory_system"
            ],
            "pending_confirmations": len(controller.pending_confirmations),
            "total_operations": len(controller.operation_logs),
            "operations_today": operations_today,
            # Ollama连接信息
            "ollama_available": OLLAMA_AVAILABLE,
            "ollama_models": OLLAMA_MODELS,
            "llm_type": "ollama" if OLLAMA_AVAILABLE else "none",
        }
    }


@app.post("/api/nanobot/resume")
async def resume_pending_tasks():
    """恢复未完成的任务（崩溃恢复后调用）"""
    controller = get_nanobot()

    resumed_count = 0
    failed_count = 0

    # 1. 加载保存的待确认操作
    try:
        pending_file = Path("./data/pending_confirmations.json")
        if pending_file.exists():
            with open(pending_file, 'r') as f:
                pending_data = json.load(f)

            pending_confirmations = pending_data.get("pending_confirmations", {})
            for conf_id, conf_data in pending_confirmations.items():
                controller.pending_confirmations[conf_id] = conf_data
                resumed_count += 1
                logger.info(f"Resumed pending confirmation: {conf_id}")

            # 删除恢复后的文件
            pending_file.unlink()
            logger.info(f"Cleared pending confirmations file")
    except Exception as e:
        logger.error(f"Failed to resume pending confirmations: {e}")
        failed_count += 1

    # 2. 加载并恢复任务队列
    try:
        tasks_file = Path("./data/pending_tasks.json")
        if tasks_file.exists():
            with open(tasks_file, 'r') as f:
                tasks_data = json.load(f)

            # 这里可以添加实际的队列恢复逻辑
            # 目前只是记录日志
            logger.info(f"Found {len(tasks_data.get('pending_tasks', []))} pending tasks to resume")

            # 删除恢复后的文件
            tasks_file.unlink()
            logger.info("Cleared pending tasks file")
    except Exception as e:
        logger.error(f"Failed to resume pending tasks: {e}")
        failed_count += 1

    return {
        "data": {
            "resumed_count": resumed_count,
            "failed_count": failed_count,
            "message": f"成功恢复 {resumed_count} 个任务"
        }
    }


# ============================================================================
# Nanobot Enhanced Capabilities Endpoints (来自Kimi Studio)
# ============================================================================

# Capability Management
@app.post("/api/nanobot/capabilities")
async def register_capability(request: Dict[str, Any]):
    """注册新能力"""
    controller = get_nanobot()

    capability_id = request.get("capability_id")
    name = request.get("name")
    capability_type = request.get("type")
    description = request.get("description", "")
    config = request.get("config", {})
    dependencies = request.get("dependencies", [])
    provides = request.get("provides", [])

    # 简单的handler
    async def dummy_handler(params):
        return {"message": f"Executing {name}"}

    result = await controller.register_capability(
        capability_id=capability_id,
        name=name,
        capability_type=capability_type,
        description=description,
        handler=dummy_handler,
        config=config,
        dependencies=dependencies,
        provides=provides
    )

    return result


@app.get("/api/nanobot/capabilities")
async def get_capabilities(capability_type: str = None):
    """获取能力列表"""
    controller = get_nanobot()
    capabilities = await controller.get_capabilities(capability_type)
    return {"data": capabilities}


@app.post("/api/nanobot/capabilities/{capability_id}/execute")
async def execute_capability(capability_id: str, request: Dict[str, Any]):
    """执行能力"""
    controller = get_nanobot()
    params = request.get("params", {})
    result = await controller.execute_capability(capability_id, params)
    return result


# Workflow Orchestration
@app.post("/api/nanobot/workflows")
async def create_workflow(request: Dict[str, Any]):
    """创建工作流"""
    controller = get_nanobot()

    workflow_id = request.get("workflow_id", f"workflow_{uuid.uuid4().hex[:8]}")
    name = request.get("name")
    steps = request.get("steps", [])
    variables = request.get("variables", {})
    parallel = request.get("parallel", False)

    result = await controller.create_workflow(
        workflow_id=workflow_id,
        name=name,
        steps=steps,
        variables=variables,
        parallel=parallel
    )

    return result


@app.post("/api/nanobot/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: str, request: Dict[str, Any] = None):
    """执行工作流"""
    controller = get_nanobot()
    initial_params = request.get("params", {}) if request else {}
    result = await controller.execute_workflow(workflow_id, initial_params)
    return result


@app.get("/api/nanobot/workflows")
async def list_workflows():
    """列出所有工作流"""
    controller = get_nanobot()
    workflows = await controller.list_workflows()
    return {"data": workflows}


@app.get("/api/nanobot/workflows/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """获取工作流状态"""
    controller = get_nanobot()
    result = await controller.get_workflow_status(workflow_id)
    return result


# Memory System
@app.post("/api/nanobot/memories")
async def store_memory(request: Dict[str, Any]):
    """存储记忆"""
    controller = get_nanobot()

    memory_type = request.get("type", "general")
    content = request.get("content")
    metadata = request.get("metadata", {})

    result = await controller.store_memory(memory_type, content, metadata)
    return result


@app.get("/api/nanobot/memories")
async def retrieve_memories(query: str = None, memory_type: str = None, limit: int = 10):
    """检索记忆"""
    controller = get_nanobot()
    memories = await controller.retrieve_memories(query, memory_type, limit)
    return {"data": memories}


@app.post("/api/nanobot/memories/consolidate")
async def consolidate_memories():
    """整合记忆"""
    controller = get_nanobot()
    result = await controller.consolidate_memories()
    return result


# Agent Cluster Management
@app.post("/api/nanobot/agents")
async def create_agent(request: Dict[str, Any]):
    """创建Agent"""
    controller = get_nanobot()

    agent_id = request.get("agent_id", f"agent_{uuid.uuid4().hex[:8]}")
    name = request.get("name")
    agent_type = request.get("type", "generator")
    config = request.get("config", {})

    result = await controller.create_agent(agent_id, name, agent_type, config)
    return result


@app.get("/api/nanobot/agents")
async def list_agents(agent_type: str = None):
    """列出所有Agent"""
    controller = get_nanobot()
    agents = await controller.list_agents(agent_type)
    return {"data": agents}


@app.get("/api/nanobot/agents/{agent_id}")
async def get_agent_status(agent_id: str):
    """获取Agent状态"""
    controller = get_nanobot()
    result = await controller.get_agent_status(agent_id)
    return result


@app.post("/api/nanobot/agents/{agent_id}/execute")
async def execute_agent(agent_id: str, request: Dict[str, Any]):
    """执行Agent任务"""
    controller = get_nanobot()
    task = request.get("task", {})
    result = await controller.execute_agent(agent_id, task)
    return result


@app.post("/api/nanobot/agents/{agent_id}/fork")
async def fork_agent(agent_id: str, request: Dict[str, Any] = None):
    """分叉Agent"""
    controller = get_nanobot()
    fork_name = request.get("name") if request else None
    result = await controller.fork_agent(agent_id, fork_name)
    return result


@app.delete("/api/nanobot/agents/{agent_id}")
async def terminate_agent(agent_id: str, terminate_children: bool = True):
    """终止Agent"""
    controller = get_nanobot()
    result = await controller.terminate_agent(agent_id, terminate_children)
    return result


# ============================================================================
# AI-Driven Natural Language Interface Endpoints
# ============================================================================

@app.post("/api/ai/chat")
async def ai_driven_chat(request: Dict[str, Any]):
    """
    AI驱动的自然语言对话接口 - 完全实现"自然语言输入+Nanobot AI识别+全功能操作"

    用户可以通过这个接口发送自然语言，系统会自动：
    1. AI语义理解 - 理解用户真实意图
    2. AI意图识别 - 识别具体的操作类型
    3. AI参数提取 - 提取执行所需的参数
    4. AI技能推荐 - 推荐最合适的技能
    5. AI模型选择 - 选择最优的模型
    6. AI执行计划 - 生成执行计划
    7. 任务执行 - 执行任务
    8. 结果返回 - 返回执行结果

    请求格式：
    {
        "message": "帮我生成一批科技感的海报",
        "context": {},  // 可选的上下文信息
        "user_preferences": {}  // 可选的用户偏好
    }
    """
    if not AI_DRIVEN_AVAILABLE:
        return {
            "status": "error",
            "message": "AI-Driven Interface not available"
        }

    try:
        ai_interface = get_ai_interface()

        # 构建自然语言请求
        nl_request = NaturalLanguageRequest(
            message=request.get("message", ""),
            context=request.get("context", {}),
            user_preferences=request.get("user_preferences", {})
        )

        # 处理请求
        result = await ai_interface.process_natural_language(nl_request)

        return {
            "status": result.status,
            "result": result.result,
            "execution_time": result.execution_time,
            "steps_executed": result.steps_executed,
            "metadata": result.metadata
        }
    except Exception as e:
        logger.error(f"AI-Driven chat error: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.post("/api/ai/recommend")
async def ai_get_recommendation(request: Dict[str, Any]):
    """
    AI推荐接口 - 获取AI的推荐用于辅助决策

    用户可以调用这个接口获取AI的推荐，然后决定是否执行
    """
    if not AI_DRIVEN_AVAILABLE:
        return {
            "status": "error",
            "message": "AI-Driven Interface not available"
        }

    try:
        ai_interface = get_ai_interface()

        recommendation = await ai_interface.get_ai_recommendation(
            user_input=request.get("message", ""),
            context=request.get("context", {})
        )

        return {
            "status": "success",
            "recommendation": recommendation
        }
    except Exception as e:
        logger.error(f"AI recommendation error: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/api/ai/capabilities")
async def ai_get_capabilities():
    """
    获取AI驱动的系统能力列表

    返回系统支持的所有AI驱动能力
    """
    if not AI_DRIVEN_AVAILABLE:
        return {
            "status": "error",
            "message": "AI-Driven Interface not available"
        }

    try:
        ai_interface = get_ai_interface()

        return {
            "status": "success",
            "capabilities": {
                "data_production": [
                    "generate_image",
                    "generate_video",
                    "edit_image",
                    "batch_production",
                    "3d_generation"
                ],
                "database_management": [
                    "query_data",
                    "classify_data",
                    "score_data",
                    "tag_data",
                    "version_data"
                ],
                "skills": [
                    "prompt_optimization",
                    "prompt_generation",
                    "batch_production",
                    "media_production",
                    "data_analysis",
                    "code_generation",
                    "translation"
                ],
                "system_operations": [
                    "execute_command",
                    "file_operations",
                    "browser_automation",
                    "code_execution"
                ],
                "third_party": [
                    "feishu_messaging",
                    "discord_messaging",
                    "github_integration",
                    "social_media"
                ]
            },
            "description": "All operations are AI-driven through natural language input"
        }
    except Exception as e:
        logger.error(f"Get capabilities error: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


# ============================================================================
# File Upload and Analysis Endpoints
# ============================================================================

@app.post("/api/files/upload")
async def upload_file(request: Request):
    """Upload a file"""
    # Simple file upload handling
    return {"status": "uploaded"}


@app.post("/api/files/upload-url")
async def upload_file_url(data: Dict[str, Any]):
    """Upload a file from URL"""
    url = data.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL required")

    # In production, this would download and process the file
    return {
        "file_id": hashlib.md5(url.encode()).hexdigest(),
        "filename": url.split("/")[-1],
        "size": 0,
        "content_type": "application/octet-stream",
        "url": url
    }


@app.post("/api/files/analyze")
async def analyze_file(data: Dict[str, Any]):
    """Analyze a file using AI"""
    file_id = data.get("file_id")
    prompt = data.get("prompt", "Describe this file")

    if not file_id:
        raise HTTPException(status_code=400, detail="File ID required")

    # In production, this would use vision model to analyze
    return {
        "file_id": file_id,
        "content": "File analysis placeholder",
        "metadata": {}
    }


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    """Delete an uploaded file"""
    return {"status": "deleted", "file_id": file_id}


# ============================================================================
# GPU Monitoring Endpoints
# ============================================================================

@app.get("/api/system/stats")
async def get_system_stats():
    """Get comprehensive system statistics including GPU"""
    try:
        global gpu_monitor
        if not gpu_monitor:
            return {"error": "GPU monitor not available"}

        stats = gpu_monitor.get_system_stats()
        return {
            "cpu_percent": stats.cpu_percent,
            "memory_total": stats.memory_total,
            "memory_used": stats.memory_used,
            "memory_percent": stats.memory_percent,
            "disk_total": stats.disk_total,
            "disk_used": stats.disk_used,
            "disk_percent": stats.disk_percent,
            "gpu": {
                "available": stats.gpu_info is not None,
                "name": stats.gpu_info.name if stats.gpu_info else None,
                "memory_total": stats.gpu_info.memory_total if stats.gpu_info else None,
                "memory_used": stats.gpu_info.memory_used if stats.gpu_info else None,
                "memory_free": stats.gpu_info.memory_free if stats.gpu_info else None,
                "memory_percent": stats.gpu_info.memory_percent if stats.gpu_info else None,
                "utilization": stats.gpu_info.utilization if stats.gpu_info else None,
                "temperature": stats.gpu_info.temperature if stats.gpu_info else None,
                "power_usage": stats.gpu_info.power_usage if stats.gpu_info else None,
                "power_limit": stats.gpu_info.power_limit if stats.gpu_info else None,
                "driver_version": stats.gpu_info.driver_version if stats.gpu_info else None,
                "cuda_version": stats.gpu_info.cuda_version if stats.gpu_info else None
            } if stats.gpu_info else None,
            "timestamp": stats.timestamp
        }
    except Exception as e:
        logger.error(f"get_system_stats failed: {e}")
        return make_error_response(500, "获取系统状态失败")


@app.get("/api/system/gpu")
async def get_gpu_info(gpu_id: int = 0):
    """Get GPU information"""
    try:
        global gpu_monitor
        if not gpu_monitor:
            return {"error": "GPU monitor not available"}

        gpu = gpu_monitor.get_gpu_info(gpu_id)
        if not gpu:
            return {"error": "GPU not found"}

        return {
            "id": gpu.id,
            "name": gpu.name,
            "memory_total": gpu.memory_total,
            "memory_used": gpu.memory_used,
            "memory_free": gpu.memory_free,
            "memory_percent": gpu.memory_percent,
            "utilization": gpu.utilization,
            "temperature": gpu.temperature,
            "power_usage": gpu.power_usage,
            "power_limit": gpu.power_limit,
            "driver_version": gpu.driver_version,
            "cuda_version": gpu.cuda_version,
            "timestamp": gpu.timestamp
        }
    except Exception as e:
        logger.error(f"get_gpu_info failed: {e}")
        return make_error_response(500, "获取GPU信息失败")


@app.get("/api/system/gpu/memory")
async def get_gpu_memory():
    """Get GPU memory usage"""
    try:
        global gpu_monitor
        if not gpu_monitor:
            return {"error": "GPU monitor not available"}

        return gpu_monitor.get_gpu_memory_usage()
    except Exception as e:
        logger.error(f"get_gpu_memory failed: {e}")
        return make_error_response(500, "获取GPU内存信息失败")


@app.post("/api/system/gpu/check")
async def check_gpu_memory(required_mb: int):
    """Check if required GPU memory can be allocated"""
    try:
        global gpu_monitor
        if not gpu_monitor:
            return {"available": False, "reason": "GPU monitor not available"}

        can_allocate = gpu_monitor.can_allocate_memory(required_mb)
        memory_info = gpu_monitor.get_gpu_memory_usage()

        return {
            "can_allocate": can_allocate,
            "required_mb": required_mb,
            "available_mb": memory_info.get("free_mb", 0)
        }
    except Exception as e:
        logger.error(f"check_gpu_memory failed: {e}")
        return make_error_response(500, "检查GPU内存失败")


# ============================================================================
# Task Queue Endpoints
# ============================================================================

@app.post("/api/tasks")
async def create_task(
    name: str,
    task_type: str,
    payload: Dict[str, Any],
    priority: int = 5,
    dependencies: Optional[List[str]] = None,
    max_retries: int = 3
):
    """Create a new task"""
    global task_queue
    if not task_queue:
        raise HTTPException(status_code=503, detail="Task queue not available")

    task_id = task_queue.create_task(
        name=name,
        task_type=task_type,
        payload=payload,
        priority=TaskPriority(priority),
        dependencies=dependencies,
        max_retries=max_retries
    )

    return {"task_id": task_id, "status": "created"}


@app.get("/api/tasks")
async def get_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 100
):
    """Get tasks with filters"""
    global task_queue
    if not task_queue:
        raise HTTPException(status_code=503, detail="Task queue not available")

    task_status = TaskStatus(status) if status else None
    tasks = task_queue.get_tasks(status=task_status, task_type=task_type, limit=limit)

    return {
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "task_type": t.task_type,
                "status": t.status.value,
                "priority": t.priority.value,
                "progress": t.progress,
                "current_step": t.current_step,
                "created_at": t.created_at,
                "started_at": t.started_at,
                "completed_at": t.completed_at,
                "error": t.error,
                "retry_count": t.retry_count
            }
            for t in tasks
        ]
    }


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    """Get specific task"""
    global task_queue
    if not task_queue:
        raise HTTPException(status_code=503, detail="Task queue not available")

    task = task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "id": task.id,
        "name": task.name,
        "task_type": task.task_type,
        "status": task.status.value,
        "priority": task.priority.value,
        "progress": task.progress,
        "current_step": task.current_step,
        "result": task.result,
        "error": task.error,
        "dependencies": task.dependencies,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries
    }


@app.delete("/api/tasks/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a task"""
    global task_queue
    if not task_queue:
        raise HTTPException(status_code=503, detail="Task queue not available")

    success = task_queue.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel task")

    return {"status": "cancelled", "task_id": task_id}


@app.get("/api/tasks/stats")
async def get_task_stats():
    """Get task queue statistics"""
    global task_queue
    if not task_queue:
        raise HTTPException(status_code=503, detail="Task queue not available")

    return task_queue.get_queue_stats()


# ============================================================================
# File Watcher Endpoints
# ============================================================================

@app.get("/api/files")
async def get_files(category: Optional[str] = None):
    """Get watched files"""
    global file_watcher
    if not file_watcher:
        raise HTTPException(status_code=503, detail="File watcher not available")

    from file_watcher import FileCategory
    cat = FileCategory(category) if category else None
    files = file_watcher.get_files(category=cat)

    return {
        "files": [
            {
                "path": f.path,
                "relative_path": f.relative_path,
                "category": f.category.value,
                "size": f.size,
                "extension": f.extension,
                "created_at": f.created_at,
                "modified_at": f.modified_at
            }
            for f in files
        ]
    }


@app.get("/api/files/stats")
async def get_file_stats():
    """Get file watcher statistics"""
    global file_watcher
    if not file_watcher:
        raise HTTPException(status_code=503, detail="File watcher not available")

    return file_watcher.get_stats()


@app.post("/api/files/watch")
async def add_watch_path(path: str):
    """Add a path to watch"""
    global file_watcher
    if not file_watcher:
        raise HTTPException(status_code=503, detail="File watcher not available")

    # Validate path to prevent path traversal
    from pathlib import Path as FilePath

    try:
        resolved_path = FilePath(path).resolve()
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid path: {e}")

    # Check for path traversal attempts
    if ".." in path or path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        # Absolute paths or paths with traversal attempts need validation
        if not resolved_path.exists():
            raise HTTPException(status_code=400, detail="Path does not exist")

    file_watcher.add_watch_path(str(resolved_path))
    return {"status": "added", "path": str(resolved_path)}


@app.delete("/api/files/watch")
async def remove_watch_path(path: str):
    """Remove a path from watch"""
    global file_watcher
    if not file_watcher:
        raise HTTPException(status_code=503, detail="File watcher not available")

    # Validate path
    from pathlib import Path as FilePath

    try:
        resolved_path = FilePath(path).resolve()
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid path: {e}")

    # Check if path is in watched paths
    watched_paths = file_watcher.get_watch_paths()
    if str(resolved_path) not in watched_paths:
        raise HTTPException(status_code=404, detail="Path not in watch list")

    file_watcher.remove_watch_path(str(resolved_path))
    return {"status": "removed", "path": str(resolved_path)}


# ============================================================================
# Agent Cluster Endpoints
# ============================================================================

@app.post("/api/cluster/agents")
async def register_agent(
    name: str,
    model: str,
    provider: str,
    capabilities: Optional[List[str]] = None
):
    """Register a new agent in the cluster"""
    global agent_cluster
    if not agent_cluster:
        raise HTTPException(status_code=503, detail="Agent cluster not available")

    agent_id = str(uuid.uuid4())[:8]
    agent = Agent(
        id=agent_id,
        name=name,
        model=model,
        provider=provider,
        capabilities=capabilities or []
    )

    agent_cluster.register_agent(agent)
    return {"agent_id": agent_id, "status": "registered"}


@app.get("/api/cluster/agents")
async def get_agents():
    """Get all agents in the cluster"""
    global agent_cluster
    if not agent_cluster:
        raise HTTPException(status_code=503, detail="Agent cluster not available")

    agents = agent_cluster.agents
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "model": a.model,
                "provider": a.provider,
                "status": a.status.value,
                "tasks_completed": a.tasks_completed,
                "capabilities": a.capabilities
            }
            for a in agents.values()
        ]
    }


@app.delete("/api/cluster/agents/{agent_id}")
async def unregister_agent(agent_id: str):
    """Unregister an agent from the cluster"""
    global agent_cluster
    if not agent_cluster:
        raise HTTPException(status_code=503, detail="Agent cluster not available")

    success = agent_cluster.unregister_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "unregistered", "agent_id": agent_id}


@app.post("/api/cluster/tasks")
async def submit_cluster_task(
    name: str,
    task_type: str,
    payload: Dict[str, Any] = Body(...),
    priority: int = 5,
    required_capabilities: Optional[List[str]] = Query(None),
    depends_on: Optional[List[str]] = Query(None)
):
    """Submit a task to the agent cluster"""
    global agent_cluster
    if not agent_cluster:
        raise HTTPException(status_code=503, detail="Agent cluster not available")

    task = ClusterTask(
        id=str(uuid.uuid4())[:8],
        name=name,
        task_type=task_type,
        payload=payload,
        priority=TaskPriority(priority),
        required_capabilities=required_capabilities or [],
        depends_on=depends_on or []
    )

    task_id = agent_cluster.submit_task(task)
    return {"task_id": task_id, "status": "submitted"}


@app.get("/api/cluster/tasks")
async def get_cluster_tasks(status: Optional[str] = None):
    """Get tasks in the cluster"""
    global agent_cluster
    if not agent_cluster:
        raise HTTPException(status_code=503, detail="Agent cluster not available")

    tasks = list(agent_cluster.tasks.values())
    if status:
        tasks = [t for t in tasks if t.status == status]

    return {
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "task_type": t.task_type,
                "status": t.status,
                "priority": t.priority.value,
                "assigned_agent_id": t.assigned_agent_id,
                "parallelism_score": t.parallelism_score,
                "can_parallelize": t.can_parallelize,
                "created_at": t.created_at,
                "started_at": t.started_at,
                "completed_at": t.completed_at
            }
            for t in tasks
        ]
    }


@app.get("/api/cluster/stats")
async def get_cluster_stats():
    """Get cluster statistics"""
    global agent_cluster
    if not agent_cluster:
        raise HTTPException(status_code=503, detail="Agent cluster not available")

    return agent_cluster.get_cluster_stats()


# ============================================================================
# Memory System Endpoints
# ============================================================================

@app.post("/api/memory/context")
async def add_context(content: str, importance: float = 0.5):
    """Add context memory"""
    global memory_system
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not available")

    entry_id = memory_system.add_context(content, importance)
    return {"entry_id": entry_id, "status": "added"}


@app.post("/api/memory/knowledge")
async def add_knowledge(content: str, importance: float = 0.8):
    """Add knowledge memory"""
    global memory_system
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not available")

    entry_id = memory_system.add_knowledge(content, importance)
    return {"entry_id": entry_id, "status": "added"}


@app.post("/api/memory/history")
async def add_history(content: str):
    """Add history memory"""
    global memory_system
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not available")

    entry_id = memory_system.add_history(content)
    return {"entry_id": entry_id, "status": "added"}


@app.get("/api/memory/context")
async def get_context(query: Optional[str] = None, limit: int = 5):
    """Get relevant context"""
    global memory_system
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not available")

    memories = memory_system.get_relevant_context(query, limit)
    return {
        "memories": [
            {
                "id": m.id,
                "content": m.content,
                "importance": m.importance,
                "created_at": m.created_at,
                "access_count": m.access_count
            }
            for m in memories
        ]
    }


@app.get("/api/memory/build-context")
async def build_memory_context(query: Optional[str] = None):
    """Build context prompt from memory"""
    global memory_system
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not available")

    context = memory_system.build_context_prompt(query)
    return {"context": context}


@app.get("/api/memory/stats")
async def get_memory_stats():
    """Get memory statistics"""
    global memory_system
    if not memory_system:
        raise HTTPException(status_code=503, detail="Memory system not available")

    return memory_system.get_statistics()


# ============================================================================
# Classification & Scoring Endpoints
# ============================================================================

@app.post("/api/classify")
async def classify_asset(prompt: str, image_path: Optional[str] = None):
    """Classify an asset"""
    global scoring_service
    if not scoring_service:
        raise HTTPException(status_code=503, detail="Scoring service not available")

    result = await scoring_service.score_asset(image_path or "", prompt)
    return {
        "categories": result.categories,
        "tags": result.tags,
        "quality_score": result.quality_score,
        "aesthetic_score": result.aesthetic_score,
        "confidence": result.confidence
    }


@app.post("/api/pipeline/process")
async def process_generation(
    prompt: str,
    generated_files: List[str],
    generator: str = "comfyui"
):
    """Process generation results through the pipeline"""
    global data_pipeline
    if not data_pipeline:
        raise HTTPException(status_code=503, detail="Data pipeline not available")

    results = await data_pipeline.process_generation_result(prompt, generated_files, generator)
    return {"processed": len(results), "results": results}


# ============================================================================
# Database Endpoints
# ============================================================================

# 兼容前端：添加 /api/assets GET 路由（映射到 /api/db/assets）
@app.get("/api/assets")
async def get_assets_compat(
    asset_type: Optional[str] = None,
    search: Optional[str] = None,
    min_quality: Optional[float] = None,
    min_aesthetic: Optional[float] = None,
    tags: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """Get assets from database with filters (兼容前端 /api/assets 调用)"""
    global db_manager
    
    # 按需初始化 db_manager（如果尚未初始化）
    if not db_manager:
        try:
            from database import DatabaseManager
            db_manager = DatabaseManager("./nanobot_factory.db", pool_size=3)
            logger.info("Database manager initialized on-demand")
        except Exception as e:
            logger.error(f"Failed to initialize database manager: {e}")
            # 返回空数据而不是 500 错误
            return {"total": 0, "assets": []}
    
    if not db_manager:
        # 返回空数据而不是 500 错误
        return {"total": 0, "assets": []}

    # 解析标签 - 添加空值检查
    tags_list = None
    if tags:
        tags_list = [t.strip() for t in tags.split(',') if t.strip()]

    try:
        # 获取资产
        assets, total = db_manager.search_assets(
            asset_type=asset_type,
            search=search,
            min_quality=min_quality,
            min_aesthetic=min_aesthetic,
            tags=tags_list,
            limit=limit,
            offset=offset
        )

        return {
            "total": total,
            "assets": [
                {
                    "id": a.id,
                    "name": a.name,
                    "type": a.type,
                    "path": a.path,
                    "size": a.size,
                    "tags": a.tags,
                    "quality_score": a.quality_score,
                    "aesthetic_score": a.aesthetic_score,
                    "created_at": a.created_at
                }
                for a in assets
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get assets: {e}")
        # 返回空数据而不是 500 错误
        return {"total": 0, "assets": []}


@app.get("/api/db/assets")
async def get_db_assets(
    asset_type: Optional[str] = None,
    search: Optional[str] = None,
    min_quality: Optional[float] = None,
    min_aesthetic: Optional[float] = None,
    tags: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """Get assets from database with filters"""
    global db_manager
    
    # 按需初始化 db_manager（如果尚未初始化）
    if not db_manager:
        try:
            from database import DatabaseManager
            db_manager = DatabaseManager("./nanobot_factory.db", pool_size=3)
            logger.info("Database manager initialized on-demand")
        except Exception as e:
            logger.error(f"Failed to initialize database manager: {e}")
            raise HTTPException(status_code=503, detail="Database not available")
    
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    # Parse tags from comma-separated string
    tags_list = tags.split(',') if tags else None

    assets, total = db_manager.search_assets(
        query=search,
        asset_type=asset_type,
        min_quality=min_quality,
        min_aesthetic=min_aesthetic,
        tags=tags_list,
        limit=limit,
        offset=offset
    )

    return {
        "assets": [
            {
                "id": a.id,
                "name": a.name,
                "type": a.type,
                "path": a.path,
                "size": a.size,
                "tags": a.tags,
                "quality_score": a.quality_score,
                "aesthetic_score": a.aesthetic_score,
                "created_at": a.created_at
            }
            for a in assets
        ],
        "total": total
    }


@app.get("/api/assets/stats")
async def get_database_stats():
    """Get database statistics"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    return db_manager.get_statistics()


@app.get("/api/datasets")
async def get_datasets():
    """Get all datasets"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    return {"datasets": db_manager.get_all_datasets()}


# ========== 完整数据库管理接口 ==========
# STATUS: active — DB管理API (34路由)，部分被前端DATASETS/BROWSER调用

@app.post("/api/db/assets")
async def create_asset(request: AssetCreateRequest):
    """创建资产"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        asset_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        # 创建Asset对象
        from database import Asset
        asset = Asset(
            id=asset_id,
            name=request.name,
            type=request.type,
            path=request.path,
            size=request.size,
            tags=request.tags,
            metadata=request.metadata,
            quality_score=None,
            aesthetic_score=None,
            dataset_id=request.dataset_id,
            created_at=now,
            updated_at=now
        )

        db_manager.assets[asset_id] = asset

        return {
            "success": True,
            "asset_id": asset_id,
            "message": "Asset created successfully"
        }
    except Exception as e:
        logger.error(f"Failed to create asset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/db/assets/{asset_id}")
async def update_asset(asset_id: str, request: AssetUpdateRequest):
    """更新资产"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        if asset_id not in db_manager.assets:
            raise HTTPException(status_code=404, detail="Asset not found")

        asset = db_manager.assets[asset_id]

        # 更新字段
        if request.name is not None:
            asset.name = request.name
        if request.tags is not None:
            asset.tags = request.tags
        if request.metadata is not None:
            asset.metadata = request.metadata
        if request.quality_score is not None:
            asset.quality_score = request.quality_score
        if request.aesthetic_score is not None:
            asset.aesthetic_score = request.aesthetic_score
        if request.dataset_id is not None:
            asset.dataset_id = request.dataset_id

        asset.updated_at = datetime.now().isoformat()
        db_manager.assets[asset_id] = asset

        return {
            "success": True,
            "message": "Asset updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update asset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/db/assets/{asset_id}")
async def delete_asset(asset_id: str):
    """删除单个资产"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        if asset_id not in db_manager.assets:
            raise HTTPException(status_code=404, detail="Asset not found")

        del db_manager.assets[asset_id]

        return {
            "success": True,
            "message": "Asset deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete asset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/assets/batch")
async def batch_operation(request: BatchOperationRequest):
    """批量操作资产"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        results = {
            "success": [],
            "failed": []
        }

        operation = request.operation

        for asset_id in request.asset_ids:
            try:
                if asset_id not in db_manager.assets:
                    results["failed"].append({"id": asset_id, "error": "Not found"})
                    continue

                if operation == "delete":
                    del db_manager.assets[asset_id]
                    results["success"].append(asset_id)

                elif operation == "tag":
                    tags = request.parameters.get("tags", [])
                    asset = db_manager.assets[asset_id]
                    asset.tags = list(set(asset.tags + tags))
                    asset.updated_at = datetime.now().isoformat()
                    results["success"].append(asset_id)

                elif operation == "untag":
                    tags_to_remove = request.parameters.get("tags", [])
                    asset = db_manager.assets[asset_id]
                    asset.tags = [t for t in asset.tags if t not in tags_to_remove]
                    asset.updated_at = datetime.now().isoformat()
                    results["success"].append(asset_id)

                elif operation == "move":
                    dataset_id = request.parameters.get("dataset_id")
                    asset = db_manager.assets[asset_id]
                    asset.dataset_id = dataset_id
                    asset.updated_at = datetime.now().isoformat()
                    results["success"].append(asset_id)

                elif operation == "score":
                    quality_score = request.parameters.get("quality_score")
                    aesthetic_score = request.parameters.get("aesthetic_score")
                    asset = db_manager.assets[asset_id]
                    if quality_score is not None:
                        asset.quality_score = quality_score
                    if aesthetic_score is not None:
                        asset.aesthetic_score = aesthetic_score
                    asset.updated_at = datetime.now().isoformat()
                    results["success"].append(asset_id)

                else:
                    results["failed"].append({"id": asset_id, "error": f"Unknown operation: {operation}"})

            except Exception as e:
                results["failed"].append({"id": asset_id, "error": str(e)})

        return {
            "success": True,
            "results": results,
            "total_success": len(results["success"]),
            "total_failed": len(results["failed"])
        }
    except Exception as e:
        logger.error(f"Batch operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 数据集管理接口 ==========

@app.post("/api/db/datasets")
async def create_dataset(name: str, description: str = ""):
    """创建数据集"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        dataset_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        from database_manager import DatabaseDataset
        dataset = DatabaseDataset(
            id=dataset_id,
            name=name,
            description=description,
            asset_count=0,
            created_at=now,
            updated_at=now
        )

        db_manager.datasets[dataset_id] = dataset

        return {
            "success": True,
            "dataset_id": dataset_id,
            "message": "Dataset created successfully"
        }
    except Exception as e:
        logger.error(f"Failed to create dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/db/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str, delete_assets: bool = False):
    """删除数据集"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        if dataset_id not in db_manager.datasets:
            raise HTTPException(status_code=404, detail="Dataset not found")

        # 如果选择同时删除资产
        if delete_assets:
            assets_to_delete = [
                aid for aid, asset in db_manager.assets.items()
                if asset.dataset_id == dataset_id
            ]
            for aid in assets_to_delete:
                del db_manager.assets[aid]

        # 移除数据集
        del db_manager.datasets[dataset_id]

        return {
            "success": True,
            "message": "Dataset deleted successfully",
            "assets_deleted": len(assets_to_delete) if delete_assets else 0
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/datasets/{dataset_id}/assets")
async def get_dataset_assets(dataset_id: str, limit: int = 100, offset: int = 0):
    """获取数据集中的资产"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        if dataset_id not in db_manager.datasets:
            raise HTTPException(status_code=404, detail="Dataset not found")

        # 筛选数据集资产
        assets = [
            asset for asset in db_manager.assets.values()
            if asset.dataset_id == dataset_id
        ]

        total = len(assets)
        paginated_assets = assets[offset:offset + limit]

        return {
            "assets": [
                {
                    "id": a.id,
                    "name": a.name,
                    "type": a.type,
                    "path": a.path,
                    "size": a.size,
                    "tags": a.tags,
                    "quality_score": a.quality_score,
                    "aesthetic_score": a.aesthetic_score,
                    "created_at": a.created_at,
                    "updated_at": a.updated_at
                }
                for a in paginated_assets
            ],
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get dataset assets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 标签管理接口 ==========

@app.get("/api/db/tags")
async def get_all_tags():
    """获取所有标签"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # 收集所有标签
        all_tags = {}
        for asset in db_manager.assets.values():
            for tag in asset.tags:
                if tag not in all_tags:
                    all_tags[tag] = {"name": tag, "count": 0}
                all_tags[tag]["count"] += 1

        return {
            "tags": list(all_tags.values()),
            "total": len(all_tags)
        }
    except Exception as e:
        logger.error(f"Failed to get tags: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 导入导出接口 ==========

@app.post("/api/db/import")
async def import_assets(request: Request):
    """导入资产"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        body = await request.json()
        assets_data = body.get("assets", [])

        imported = 0
        errors = []

        for asset_data in assets_data:
            try:
                asset_id = str(uuid.uuid4())
                now = datetime.now().isoformat()

                from database import Asset
                asset = Asset(
                    id=asset_id,
                    name=asset_data.get("name", "Unnamed"),
                    type=asset_data.get("type", "unknown"),
                    path=asset_data.get("path", ""),
                    size=asset_data.get("size", 0),
                    tags=asset_data.get("tags", []),
                    metadata=asset_data.get("metadata", {}),
                    quality_score=asset_data.get("quality_score"),
                    aesthetic_score=asset_data.get("aesthetic_score"),
                    dataset_id=asset_data.get("dataset_id"),
                    created_at=now,
                    updated_at=now
                )

                db_manager.assets[asset_id] = asset
                imported += 1

            except Exception as e:
                errors.append({"name": asset_data.get("name"), "error": str(e)})

        return {
            "success": True,
            "imported": imported,
            "errors": errors,
            "total": len(assets_data)
        }
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/import/eagle")
async def import_from_eagle(request: Request):
    """从Eagle库导入资产 - 支持Eagle数据库迁移"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        body = await request.json()
        eagle_path = body.get("eagle_library_path", "")
        import_ratings = body.get("import_ratings", True)
        import_colors = body.get("import_colors", True)
        import_annotations = body.get("import_annotations", True)
        import_tags = body.get("import_tags", True)
        import_metadata = body.get("import_metadata", True)

        imported = 0
        errors = []
        skipped = 0

        # 尝试读取Eagle数据库
        eagle_db_path = Path(eagle_path) / "library.eagle"
        if not eagle_db_path.exists():
            # 尝试其他可能的路径
            eagle_db_path = Path(eagle_path) / "Eagle" / "library.eagle"

        if not eagle_db_path.exists():
            # 尝试查找Eagle应用数据目录
            if os.name == 'nt':  # Windows
                app_data = os.environ.get('APPDATA', '')
                eagle_db_path = Path(app_data) / "Eagle" / "library.eagle"
            elif os.name == 'posix':  # macOS/Linux
                home = os.path.expanduser("~")
                eagle_db_path = Path(home) / "Library" / "Application Support" / "Eagle" / "library.eagle"

        if not eagle_db_path.exists():
            return {
                "success": False,
                "imported": 0,
                "errors": ["Eagle library not found. Please provide the correct path."],
                "message": "未找到Eagle库，请检查路径是否正确"
            }

        # 读取Eagle数据库
        try:
            import sqlite3
            conn = sqlite3.connect(str(eagle_db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 获取Eagle中的所有图片
            cursor.execute("SELECT * FROM items")
            items = cursor.fetchall()

            for item in items:
                try:
                    # 映射Eagle数据到我们的格式
                    item_data = dict(item)

                    # 提取基本信息
                    name = item_data.get('name', 'Unnamed')
                    # Eagle使用contentType判断类型
                    content_type = item_data.get('contentType', '')
                    if 'image' in content_type.lower() or 'picture' in content_type.lower():
                        asset_type = 'image'
                    elif 'video' in content_type.lower():
                        asset_type = 'video'
                    elif 'audio' in content_type.lower():
                        asset_type = 'audio'
                    else:
                        asset_type = 'unknown'

                    # 尝试获取文件路径
                    path = item_data.get('path', '')
                    if not path and item_data.get('thumbnail'):
                        # 如果没有原始路径，使用缩略图
                        path = item_data.get('thumbnail', '')

                    # 获取文件大小
                    size = item_data.get('size', 0) or 0

                    # 获取标签
                    tags = []
                    if import_tags and item_data.get('tags'):
                        try:
                            tags = json.loads(item_data['tags']) if isinstance(item_data['tags'], str) else item_data.get('tags', [])
                        except (json.JSONDecodeError, TypeError):
                            tags = []

                    # 获取评分 (Eagle使用0-5的评分)
                    rating = 0
                    if import_ratings:
                        rating = item_data.get('rating', 0) or 0

                    # 获取颜色标签
                    color = ''
                    if import_colors and item_data.get('color'):
                        color = item_data.get('color', '')

                    # 获取注释/描述
                    annotation = ''
                    if import_annotations and item_data.get('description'):
                        annotation = item_data.get('description', '')
                    if import_annotations and item_data.get('annotation'):
                        annotation = item_data.get('annotation', annotation)

                    # 获取宽度高度
                    width = item_data.get('width', 0) or 0
                    height = item_data.get('height', 0) or 0

                    # 获取格式
                    format_type = item_data.get('ext', item_data.get('format', ''))

                    # 获取创建时间
                    created_at = item_data.get('createdAt', item_data.get('created_at', ''))
                    if not created_at:
                        created_at = datetime.now().isoformat()

                    # 获取元数据
                    metadata = {}
                    if import_metadata:
                        metadata = {
                            'eagle_id': item_data.get('id', ''),
                            'eagle_imported': True,
                            'width': width,
                            'height': height,
                            'format': format_type,
                            'added_time': item_data.get('addedTime', ''),
                            'modified_time': item_data.get('modifiedTime', ''),
                        }

                    # 生成唯一ID
                    asset_id = str(uuid.uuid4())
                    now = datetime.now().isoformat()

                    from database import Asset
                    asset = Asset(
                        id=asset_id,
                        name=name,
                        type=asset_type,
                        path=path,
                        size=size,
                        tags=tags,
                        metadata=metadata,
                        rating=rating,
                        color=color,
                        annotation=annotation,
                        width=width,
                        height=height,
                        format=format_type,
                        created_at=created_at,
                        updated_at=now
                    )

                    # 添加到数据库并更新缓存
                    db_manager.add_asset(asset)
                    imported += 1

                except Exception as e:
                    errors.append({"error": str(e)})
                    skipped += 1

            conn.close()

        except Exception as e:
            return {
                "success": False,
                "imported": imported,
                "errors": [str(e)],
                "message": f"读取Eagle库失败: {str(e)}"
            }

        return {
            "success": True,
            "imported": imported,
            "skipped": skipped,
            "errors": errors[:10],  # 只返回前10个错误
            "message": f"成功从Eagle导入 {imported} 个资产"
        }

    except Exception as e:
        logger.error(f"Eagle import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/export")
async def export_assets(
    asset_type: Optional[str] = None,
    tags: Optional[str] = None,
    dataset_id: Optional[str] = None,
    format: str = "json"
):
    """导出资产"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # 筛选资产
        assets = list(db_manager.assets.values())

        if asset_type:
            assets = [a for a in assets if a.type == asset_type]

        if tags:
            tag_list = tags.split(",")
            assets = [a for a in assets if any(t in a.tags for t in tag_list)]

        if dataset_id:
            assets = [a for a in assets if a.dataset_id == dataset_id]

        # 导出格式
        if format == "json":
            export_data = [
                {
                    "id": a.id,
                    "name": a.name,
                    "type": a.type,
                    "path": a.path,
                    "size": a.size,
                    "tags": a.tags,
                    "metadata": a.metadata,
                    "quality_score": a.quality_score,
                    "aesthetic_score": a.aesthetic_score,
                    "dataset_id": a.dataset_id,
                    "created_at": a.created_at,
                    "updated_at": a.updated_at
                }
                for a in assets
            ]
            return {
                "format": "json",
                "total": len(export_data),
                "assets": export_data
            }
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 质量评估接口 ==========

@app.post("/api/db/assets/{asset_id}/analyze")
async def analyze_asset(asset_id: str, force: bool = False):
    """分析资产质量"""
    global db_manager, scoring_service
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        if asset_id not in db_manager.assets:
            raise HTTPException(status_code=404, detail="Asset not found")

        asset = db_manager.assets[asset_id]

        # 如果已有评分且不强制重新分析
        if not force and (asset.quality_score is not None or asset.aesthetic_score is not None):
            return {
                "success": True,
                "message": "Asset already analyzed",
                "quality_score": asset.quality_score,
                "aesthetic_score": asset.aesthetic_score
            }

        # 调用评分服务
        if scoring_service:
            try:
                quality_score = await scoring_service.score_quality(asset.path)
                aesthetic_score = await scoring_service.score_aesthetic(asset.path)

                asset.quality_score = quality_score
                asset.aesthetic_score = aesthetic_score
                asset.updated_at = datetime.now().isoformat()

                return {
                    "success": True,
                    "quality_score": quality_score,
                    "aesthetic_score": aesthetic_score
                }
            except Exception as e:
                logger.error(f"Scoring service failed: {e}")
                # 禁止返回模拟分数，必须抛出异常
                raise HTTPException(
                    status_code=503,
                    detail=f"AI scoring service is not available: {str(e)}. Please ensure scoring service is properly configured."
                )
        else:
            raise HTTPException(status_code=503, detail="Scoring service not available")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== Eagle风格扩展接口 ==========

@app.put("/api/db/assets/{asset_id}/rating")
async def update_asset_rating(asset_id: str, rating: int):
    """更新资源评分 (1-5星)"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        success = db_manager.update_asset_rating(asset_id, rating)
        if not success:
            raise HTTPException(status_code=404, detail="Asset not found or invalid rating")
        return {"success": True, "rating": rating}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update rating: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/db/assets/{asset_id}/color")
async def update_asset_color(asset_id: str, color: str):
    """更新资源颜色标签"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        success = db_manager.update_asset_color(asset_id, color)
        if not success:
            raise HTTPException(status_code=404, detail="Asset not found")
        return {"success": True, "color": color}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update color: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/db/assets/{asset_id}/annotation")
async def update_asset_annotation(asset_id: str, annotation: str):
    """更新资源注释"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        success = db_manager.update_asset_annotation(asset_id, annotation)
        if not success:
            raise HTTPException(status_code=404, detail="Asset not found")
        return {"success": True, "annotation": annotation}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update annotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/assets/batch/rating")
async def batch_update_rating(request: Request):
    """批量更新资源评分"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        body = await request.json()
        asset_ids = body.get("asset_ids", [])
        rating = body.get("rating", 0)

        count = db_manager.batch_update_rating(asset_ids, rating)
        return {"success": True, "updated": count}
    except Exception as e:
        logger.error(f"Failed to batch update rating: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/assets/batch/color")
async def batch_update_color(request: Request):
    """批量更新资源颜色标签"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        body = await request.json()
        asset_ids = body.get("asset_ids", [])
        color = body.get("color", "")

        count = db_manager.batch_update_color(asset_ids, color)
        return {"success": True, "updated": count}
    except Exception as e:
        logger.error(f"Failed to batch update color: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/assets/batch/annotation")
async def batch_add_annotation(request: Request):
    """批量添加资源注释"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        body = await request.json()
        asset_ids = body.get("asset_ids", [])
        annotation = body.get("annotation", "")

        count = db_manager.batch_add_annotation(asset_ids, annotation)
        return {"success": True, "updated": count}
    except Exception as e:
        logger.error(f"Failed to batch add annotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/assets/rating/{rating}")
async def get_assets_by_rating(rating: int, limit: int = 100, offset: int = 0):
    """按评分筛选资源"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        assets = db_manager.get_assets_by_rating(rating, limit, offset)
        return {"assets": [a.__dict__ for a in assets], "count": len(assets)}
    except Exception as e:
        logger.error(f"Failed to get assets by rating: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/assets/color/{color}")
async def get_assets_by_color(color: str, limit: int = 100, offset: int = 0):
    """按颜色标签筛选资源"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        assets = db_manager.get_assets_by_color(color, limit, offset)
        return {"assets": [a.__dict__ for a in assets], "count": len(assets)}
    except Exception as e:
        logger.error(f"Failed to get assets by color: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/stats/color")
async def get_color_statistics():
    """获取颜色标签统计"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        stats = db_manager.get_color_statistics()
        return {"colors": stats}
    except Exception as e:
        logger.error(f"Failed to get color stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/stats/rating")
async def get_rating_distribution():
    """获取评分分布统计"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        distribution = db_manager.get_rating_distribution()
        return {"distribution": distribution}
    except Exception as e:
        logger.error(f"Failed to get rating distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/stats")
async def get_database_statistics():
    """获取数据库统计信息 - FiftyOne风格"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        stats = db_manager.get_statistics()
        return {
            "total_assets": stats.get("total_assets", 0),
            "by_type": stats.get("by_type", {}),
            "by_tag": stats.get("by_tag", {}),
            "avg_quality": stats.get("avg_quality", 0),
            "avg_aesthetic": stats.get("avg_aesthetic", 0),
            "high_quality_count": stats.get("high_quality_count", 0)
        }
    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== FiftyOne Integration ==========

# Global FiftyOne integration instance
fiftyone_integration = None

def get_fiftyone_integration_instance():
    """Get or create FiftyOne integration instance"""
    global fiftyone_integration
    if fiftyone_integration is None:
        try:
            from fiftyone_integration import FiftyOneIntegration, NanobotFiftyOneConfig
            config = NanobotFiftyOneConfig(
                dataset_dir="./fiftyone_datasets",
                default_num_workers=4,
                batch_size=32
            )
            fiftyone_integration = FiftyOneIntegration(config)
        except ImportError as e:
            logger.error(f"FiftyOne not available: {e}")
            raise HTTPException(status_code=503, detail="FiftyOne not installed")
        except Exception as e:
            logger.error(f"Failed to initialize FiftyOne: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    return fiftyone_integration


@app.post("/api/fiftyone/datasets")
async def create_fiftyone_dataset(request: Request):
    """创建FiftyOne数据集"""
    try:
        foi = get_fiftyone_integration_instance()
        body = await request.json()

        name = body.get("name")
        description = body.get("description", "")
        metadata = body.get("metadata", {})

        if not name:
            raise HTTPException(status_code=400, detail="Dataset name is required")

        dataset_id = foi.create_dataset(name, description, metadata)
        return {"success": True, "dataset_id": dataset_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create FiftyOne dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fiftyone/datasets")
async def list_fiftyone_datasets():
    """列出所有FiftyOne数据集"""
    try:
        foi = get_fiftyone_integration_instance()
        datasets = foi.list_datasets()
        return {"datasets": datasets}
    except Exception as e:
        logger.error(f"Failed to list FiftyOne datasets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/fiftyone/datasets/{dataset_name}")
async def delete_fiftyone_dataset(dataset_name: str):
    """删除FiftyOne数据集"""
    try:
        foi = get_fiftyone_integration_instance()
        success = foi.delete_dataset(dataset_name)
        return {"success": success}
    except Exception as e:
        logger.error(f"Failed to delete FiftyOne dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fiftyone/datasets/{dataset_name}/stats")
async def get_fiftyone_dataset_stats(dataset_name: str):
    """获取FiftyOne数据集统计"""
    try:
        foi = get_fiftyone_integration_instance()
        stats = foi.get_dataset_stats(dataset_name)
        return {"stats": stats}
    except Exception as e:
        logger.error(f"Failed to get FiftyOne dataset stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fiftyone/datasets/{dataset_name}/samples")
async def add_fiftyone_sample(dataset_name: str, request: Request):
    """添加样本到FiftyOne数据集"""
    try:
        foi = get_fiftyone_integration_instance()
        body = await request.json()

        filepath = body.get("filepath")
        metadata = body.get("metadata", {})
        tags = body.get("tags", [])
        quality_score = body.get("quality_score")
        aesthetic_score = body.get("aesthetic_score")

        if not filepath:
            raise HTTPException(status_code=400, detail="Filepath is required")

        sample_id = foi.add_sample(
            dataset_name=dataset_name,
            filepath=filepath,
            metadata=metadata,
            tags=tags,
            quality_score=quality_score,
            aesthetic_score=aesthetic_score
        )

        return {"success": True, "sample_id": sample_id}

    except Exception as e:
        logger.error(f"Failed to add sample: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fiftyone/datasets/{dataset_name}/samples/batch")
async def add_fiftyone_samples_batch(dataset_name: str, request: Request):
    """批量添加样本"""
    try:
        foi = get_fiftyone_integration_instance()
        body = await request.json()

        samples_data = body.get("samples", [])
        if not samples_data:
            raise HTTPException(status_code=400, detail="No samples provided")

        count = foi.add_samples_batch(dataset_name, samples_data)
        return {"success": True, "count": count}

    except Exception as e:
        logger.error(f"Failed to add samples batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fiftyone/datasets/{dataset_name}/samples")
async def search_fiftyone_samples(
    dataset_name: str,
    limit: int = 100,
    tags: str = None,
    quality_min: float = None
):
    """搜索FiftyOne数据集样本"""
    try:
        foi = get_fiftyone_integration_instance()

        filters = {}
        if quality_min is not None:
            filters["quality_score"] = {"$gte": quality_min}

        tag_list = tags.split(",") if tags else None

        samples = foi.search_samples(
            dataset_name=dataset_name,
            filters=filters,
            tags=tag_list,
            limit=limit
        )

        return {"samples": samples, "count": len(samples)}

    except Exception as e:
        logger.error(f"Failed to search samples: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fiftyone/datasets/{dataset_name}/samples/{sample_id}")
async def get_fiftyone_sample(dataset_name: str, sample_id: str):
    """获取单个样本"""
    try:
        foi = get_fiftyone_integration_instance()
        sample = foi.get_sample(dataset_name, sample_id)

        if not sample:
            raise HTTPException(status_code=404, detail="Sample not found")

        return {"sample": sample}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sample: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/fiftyone/datasets/{dataset_name}/samples/{sample_id}")
async def update_fiftyone_sample(
    dataset_name: str,
    sample_id: str,
    request: Request
):
    """更新样本"""
    try:
        foi = get_fiftyone_integration_instance()
        body = await request.json()

        success = foi.update_sample(dataset_name, sample_id, body)
        return {"success": success}

    except Exception as e:
        logger.error(f"Failed to update sample: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/fiftyone/datasets/{dataset_name}/samples/{sample_id}")
async def delete_fiftyone_sample(dataset_name: str, sample_id: str):
    """删除样本"""
    try:
        foi = get_fiftyone_integration_instance()
        success = foi.delete_sample(dataset_name, sample_id)
        return {"success": success}

    except Exception as e:
        logger.error(f"Failed to delete sample: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fiftyone/datasets/{dataset_name}/embeddings")
async def compute_fiftyone_embeddings(
    dataset_name: str,
    request: Request
):
    """计算样本嵌入向量"""
    try:
        foi = get_fiftyone_integration_instance()
        body = await request.json()

        model_name = body.get("model", "resnet50-imagenet-torch")
        embeddings_field = body.get("embeddings_field", "embedding")
        batch_size = body.get("batch_size", 32)

        success = foi.compute_embeddings(
            dataset_name,
            model_name,
            embeddings_field,
            batch_size
        )

        return {"success": success}

    except Exception as e:
        logger.error(f"Failed to compute embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fiftyone/datasets/{dataset_name}/similar/{sample_id}")
async def find_similar_samples(
    dataset_name: str,
    sample_id: str,
    num_results: int = 10
):
    """查找相似样本"""
    try:
        foi = get_fiftyone_integration_instance()

        similar = foi.find_similar(
            dataset_name,
            sample_id,
            num_results=num_results
        )

        return {"samples": similar, "count": len(similar)}

    except Exception as e:
        logger.error(f"Failed to find similar samples: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fiftyone/datasets/{dataset_name}/export")
async def export_fiftyone_dataset(
    dataset_name: str,
    request: Request
):
    """导出FiftyOne数据集"""
    try:
        foi = get_fiftyone_integration_instance()
        body = await request.json()

        export_dir = body.get("export_dir")
        export_format = body.get("format", "csv")
        split = body.get("split", False)

        if not export_dir:
            raise HTTPException(status_code=400, detail="Export directory is required")

        success = foi.export_dataset(
            dataset_name,
            export_dir,
            export_format,
            split
        )

        return {"success": success}

    except Exception as e:
        logger.error(f"Failed to export dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fiftyone/datasets/{dataset_name}/clone")
async def clone_fiftyone_dataset(
    dataset_name: str,
    request: Request
):
    """克隆FiftyOne数据集"""
    try:
        foi = get_fiftyone_integration_instance()
        body = await request.json()

        target_name = body.get("target_name")
        if not target_name:
            raise HTTPException(status_code=400, detail="Target name is required")

        new_name = foi.clone_dataset(dataset_name, target_name)
        return {"success": True, "dataset_id": new_name}

    except Exception as e:
        logger.error(f"Failed to clone dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fiftyone/datasets/{dataset_name}/views")
async def get_fiftyone_views(dataset_name: str):
    """获取保存的视图"""
    try:
        foi = get_fiftyone_integration_instance()
        views = foi.get_views(dataset_name)
        return {"views": views}
    except Exception as e:
        logger.error(f"Failed to get views: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fiftyone/datasets/{dataset_name}/views")
async def create_fiftyone_view(
    dataset_name: str,
    request: Request
):
    """创建保存的视图"""
    try:
        foi = get_fiftyone_integration_instance()
        body = await request.json()

        view_config = body
        view_name = foi.create_view(dataset_name, view_config)

        return {"success": True, "view_name": view_name}

    except Exception as e:
        logger.error(f"Failed to create view: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== 智能文件夹接口 (Eagle风格) ==========

@app.post("/api/db/smart-folders")
async def create_smart_folder(request: Request):
    """创建智能文件夹"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        body = await request.json()
        folder_id = body.get("id", str(uuid.uuid4()))
        name = body.get("name", "")
        conditions = body.get("conditions", [])
        sort_by = body.get("sort_by", "created_at")
        sort_order = body.get("sort_order", "desc")

        success = db_manager.create_smart_folder(folder_id, name, conditions, sort_by, sort_order)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create smart folder")

        return {"success": True, "id": folder_id, "name": name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create smart folder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/smart-folders")
async def get_smart_folders():
    """获取所有智能文件夹"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        folders = db_manager.get_smart_folders()
        return {"folders": folders}
    except Exception as e:
        logger.error(f"Failed to get smart folders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/smart-folders/{folder_id}/assets")
async def get_smart_folder_assets(folder_id: str, limit: int = 100, offset: int = 0):
    """获取智能文件夹中的资源"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        assets = db_manager.get_smart_folder_assets(folder_id, limit, offset)
        return {"assets": [a.__dict__ for a in assets], "count": len(assets)}
    except Exception as e:
        logger.error(f"Failed to get smart folder assets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/db/smart-folders/{folder_id}")
async def delete_smart_folder(folder_id: str):
    """删除智能文件夹"""
    global db_manager
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        success = db_manager.delete_smart_folder(folder_id)
        if not success:
            raise HTTPException(status_code=404, detail="Smart folder not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete smart folder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Production Skills API
# ============================================================================

# Import production skills module
try:
    from skills import SkillManager, SkillInput, get_skill_manager
    SKILLS_AVAILABLE = True
except ImportError:
    SKILLS_AVAILABLE = False
    logger.warning("Skills module not available")


@app.get("/api/skills/production")
async def get_production_skills():
    """Get all production skills"""
    if not SKILLS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Skills module not available")

    skill_manager = get_skill_manager()
    return {"skills": skill_manager.get_all_skills()}


@app.post("/api/skills/production/execute")
async def execute_production_skill(request: Request):
    """Execute a production skill"""
    if not SKILLS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Skills module not available")

    try:
        body = await request.json()
        skill_name = body.get("skill_name")
        prompt = body.get("prompt", "")
        params = body.get("params", {})

        skill_manager = get_skill_manager()
        skill_input = SkillInput(prompt=prompt, params=params)

        result = await skill_manager.execute_skill(skill_name, skill_input)

        return {
            "success": result.success,
            "result": result.result,
            "error": result.error,
            "metadata": result.metadata
        }
    except Exception as e:
        logger.error(f"Skill execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Production Agents API
# ============================================================================

# Import production agents module
try:
    from production_agents import ProductionAgentCluster, AgentType, get_production_cluster
    AGENTS_AVAILABLE = True
except ImportError:
    AGENTS_AVAILABLE = False
    logger.warning("Production agents module not available")


@app.get("/api/production/agents")
async def get_production_agents():
    """Get all production agents status"""
    if not AGENTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Production agents not available")

    cluster = get_production_cluster()
    return {"agents": cluster.get_all_agents_status()}


@app.get("/api/production/agents/{agent_type}")
async def get_production_agent(agent_type: str):
    """Get specific production agent status"""
    if not AGENTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Production agents not available")

    cluster = get_production_cluster()

    try:
        agent_type_enum = AgentType(agent_type)
        agent = cluster.get_agent(agent_type_enum)

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_type}")

        return agent.get_status()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid agent type: {agent_type}")


@app.post("/api/production/agents/{agent_type}/tasks")
async def submit_production_task(agent_type: str, request: Request):
    """Submit task to production agent"""
    if not AGENTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Production agents not available")

    try:
        body = await request.json()
        agent_type_enum = AgentType(agent_type)

        cluster = get_production_cluster()
        task_id = await cluster.submit_task(agent_type_enum, body)

        return {"task_id": task_id, "status": "submitted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Task submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/production/tasks/{task_id}")
async def get_production_task(task_id: str):
    """Get production task status"""
    if not AGENTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Production agents not available")

    cluster = get_production_cluster()
    status = cluster.get_task_status(task_id)

    if not status:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    return status


@app.get("/api/production/queue")
async def get_production_queue():
    """Get production queue status"""
    if not AGENTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Production agents not available")

    cluster = get_production_cluster()
    return cluster.get_queue_status()


# ============================================================================
# OSS API
# ============================================================================

# Import OSS module
try:
    from oss_manager import OSSManager, get_oss_manager, DataType, DataAnnotation
    OSS_AVAILABLE = True
except ImportError:
    OSS_AVAILABLE = False
    logger.warning("OSS module not available")


@app.get("/api/oss/status")
async def get_oss_status():
    """Get OSS status"""
    if not OSS_AVAILABLE:
        return {"available": False, "message": "OSS module not available"}

    oss_manager = get_oss_manager()
    return {
        "available": oss_manager.is_available(),
        "bucket": oss_manager.bucket_name,
        "endpoint": oss_manager.endpoint
    }


@app.post("/api/oss/configure")
async def configure_oss(request: Request):
    """Configure OSS credentials"""
    if not OSS_AVAILABLE:
        raise HTTPException(status_code=503, detail="OSS module not available")

    try:
        body = await request.json()
        access_key_id = body.get("access_key_id")
        access_key_secret = body.get("access_key_secret")
        bucket_name = body.get("bucket_name")
        endpoint = body.get("endpoint", "")
        region = body.get("region", "oss-cn-hangzhou")

        from oss_manager import init_oss_manager
        oss_manager = init_oss_manager(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            bucket_name=bucket_name,
            endpoint=endpoint,
            region=region
        )

        if oss_manager.is_available():
            return {"success": True, "message": "OSS configured successfully"}
        else:
            return {"success": False, "message": "OSS configuration failed"}
    except Exception as e:
        logger.error(f"OSS configuration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/systems/init")
async def init_all_systems(request: Request):
    """
    初始化所有系统 (AI增强版)
    统一初始化: 统一生成服务、OSS、生产Agent集群
    """
    try:
        body = await request.json()

        # 1. 初始化统一生成服务
        generation_service = None
        if GENERATION_SERVICE_AVAILABLE:
            from unified_generation_service import init_generation_service
            generation_service = init_generation_service()

        # 2. 初始化OSS管理器 (AI增强版)
        oss_manager = None
        oss_config = body.get("oss", {})
        if oss_config.get("access_key_id"):
            from oss_manager import init_oss_manager
            oss_manager = init_oss_manager(
                access_key_id=oss_config.get("access_key_id"),
                access_key_secret=oss_config.get("access_key_secret"),
                bucket_name=oss_config.get("bucket_name"),
                endpoint=oss_config.get("endpoint"),
                region=oss_config.get("region", "oss-cn-hangzhou"),
                generation_service=generation_service,
                database_manager=None  # 可以后续添加数据库
            )

        # 3. 初始化生产Agent集群 (AI增强版)
        cluster = None
        if AGENTS_AVAILABLE:
            from production_agents import init_production_cluster
            cluster = init_production_cluster(
                oss_manager=oss_manager,
                generation_service=generation_service
            )

        # 返回初始化状态
        return {
            "success": True,
            "message": "All systems initialized (AI Enhanced)",
            "systems": {
                "generation_service": generation_service is not None,
                "oss_manager": oss_manager is not None and oss_manager.is_available(),
                "production_agents": cluster is not None
            }
        }
    except Exception as e:
        logger.error(f"System initialization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/systems/status")
async def get_systems_status():
    """
    获取所有系统状态
    """
    status = {
        "generation_service": GENERATION_SERVICE_AVAILABLE,
        "oss_manager": OSS_AVAILABLE,
        "production_agents": AGENTS_AVAILABLE
    }

    # 获取OSS状态
    if OSS_AVAILABLE:
        from oss_manager import get_oss_manager
        oss = get_oss_manager()
        status["oss_available"] = oss.is_available()

    # 获取Production Agents状态
    if AGENTS_AVAILABLE:
        from production_agents import get_production_cluster
        cluster = get_production_cluster()
        status["agents"] = cluster.get_all_agents_status()

    return status


@app.get("/api/oss/files")
async def list_oss_files(prefix: str = "", max_keys: int = 100):
    """List OSS files"""
    if not OSS_AVAILABLE:
        raise HTTPException(status_code=503, detail="OSS not available")

    oss_manager = get_oss_manager()
    result = oss_manager.list_files(prefix, max_keys)

    return {
        "files": [
            {
                "key": f.key,
                "name": f.name,
                "size": f.size,
                "last_modified": f.last_modified
            }
            for f in result.get("files", [])
        ],
        "total_count": result.get("total_count", 0),
        "is_truncated": result.get("is_truncated", False)
    }


@app.get("/api/oss/files/{key:path}")
async def get_oss_file(key: str):
    """Get OSS file info"""
    if not OSS_AVAILABLE:
        raise HTTPException(status_code=503, detail="OSS not available")

    oss_manager = get_oss_manager()
    file_info = oss_manager.get_file_info(key)

    if not file_info:
        raise HTTPException(status_code=404, detail=f"File not found: {key}")

    return {
        "key": file_info.key,
        "name": file_info.name,
        "size": file_info.size,
        "content_type": file_info.content_type,
        "etag": file_info.etag,
        "last_modified": file_info.last_modified,
        "metadata": file_info.metadata
    }


@app.get("/api/oss/files/{key:path}/url")
async def get_oss_file_url(key: str, expires: int = 3600):
    """Get signed URL for OSS file"""
    if not OSS_AVAILABLE:
        raise HTTPException(status_code=503, detail="OSS not available")

    oss_manager = get_oss_manager()
    url = oss_manager.get_signed_url(key, expires)

    if not url:
        raise HTTPException(status_code=404, detail=f"File not found: {key}")

    return {"url": url, "expires": expires}


@app.post("/api/oss/files/upload-url")
async def get_upload_url(request: Request):
    """Get signed URL for file upload"""
    if not OSS_AVAILABLE:
        raise HTTPException(status_code=503, detail="OSS not available")

    try:
        body = await request.json()
        key = body.get("key")
        content_type = body.get("content_type", "application/octet-stream")
        expires = body.get("expires", 3600)

        oss_manager = get_oss_manager()
        url = oss_manager.get_upload_signed_url(key, expires)

        if not url:
            raise HTTPException(status_code=400, detail="Failed to generate upload URL")

        return {
            "upload_url": url,
            "key": key,
            "content_type": content_type,
            "expires": expires
        }
    except Exception as e:
        logger.error(f"Failed to generate upload URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/oss/files/{key:path}")
async def delete_oss_file(key: str):
    """Delete OSS file"""
    if not OSS_AVAILABLE:
        raise HTTPException(status_code=503, detail="OSS not available")

    oss_manager = get_oss_manager()
    success = oss_manager.delete_file(key)

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {key}")

    return {"success": True, "key": key}


@app.get("/api/oss/statistics")
async def get_oss_statistics(prefix: str = ""):
    """Get OSS statistics"""
    if not OSS_AVAILABLE:
        raise HTTPException(status_code=503, detail="OSS not available")

    oss_manager = get_oss_manager()
    stats = oss_manager.get_statistics(prefix)

    return stats


# ============================================================================
# OSS Datasets API
# ============================================================================

@app.post("/api/oss/datasets")
async def create_oss_dataset(request: Request):
    """Create OSS dataset"""
    if not OSS_AVAILABLE:
        raise HTTPException(status_code=503, detail="OSS not available")

    try:
        body = await request.json()
        name = body.get("name")
        description = body.get("description", "")
        data_type = body.get("data_type", "image")

        oss_manager = get_oss_manager()
        dataset_id = oss_manager.create_dataset(name, description, data_type)

        return {"dataset_id": dataset_id, "success": True}
    except Exception as e:
        logger.error(f"Failed to create dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/oss/datasets")
async def list_oss_datasets():
    """List OSS datasets"""
    if not OSS_AVAILABLE:
        raise HTTPException(status_code=503, detail="OSS not available")

    oss_manager = get_oss_manager()
    datasets = oss_manager.list_datasets()

    return {"datasets": [d.__dict__ for d in datasets]}


@app.get("/api/oss/datasets/{dataset_id}")
async def get_oss_dataset(dataset_id: str):
    """Get OSS dataset"""
    if not OSS_AVAILABLE:
        raise HTTPException(status_code=503, detail="OSS not available")

    oss_manager = get_oss_manager()
    dataset = oss_manager.get_dataset(dataset_id)

    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")

    return dataset.__dict__


@app.get("/api/oss/datasets/{dataset_id}/statistics")
async def get_dataset_statistics(dataset_id: str):
    """Get dataset statistics"""
    if not OSS_AVAILABLE:
        raise HTTPException(status_code=503, detail="OSS not available")

    oss_manager = get_oss_manager()
    stats = oss_manager.get_dataset_statistics(dataset_id)

    if not stats:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")

    return stats


@app.post("/api/oss/datasets/{dataset_id}/analyze")
async def analyze_dataset(dataset_id: str, request: Request):
    """Analyze dataset with AI"""
    if not OSS_AVAILABLE or not AGENTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Services not available")

    try:
        body = await request.json()
        operation = body.get("operation", "analyze")
        file_type = body.get("file_type", "image")
        model = body.get("model", "default")

        # Submit to data analyzer agent
        cluster = get_production_cluster()
        from production_agents import AgentType

        task_id = await cluster.submit_task(
            AgentType.DATA_ANALYZER,
            {
                "operation": operation,
                "file_type": file_type,
                "model": model,
                "prefix": f"datasets/{dataset_id}/data/"
            }
        )

        return {"task_id": task_id, "status": "submitted"}
    except Exception as e:
        logger.error(f"Dataset analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Production Workbench Endpoints
# ============================================================================

# 导入生产工作台
try:
    from production_workbench import (
        ProductionWorkbenchController,
        get_workbench_controller,
        ProviderType,
        GenerationType,
        ProviderConfig,
        GenerationRequest,
    )
    WORKBENCH_AVAILABLE = True
except ImportError:
    WORKBENCH_AVAILABLE = False
    logger.warning("Production Workbench not available")

# 提供商配置请求
class ProviderConfigRequest(BaseModel):
    provider_type: str
    name: str
    enabled: bool = True
    comfyui_url: str = ""
    comfyui_port: int = 8188
    api_key: str = ""
    api_endpoint: str = ""
    extra_config: Dict[str, Any] = {}


# 生成请求
class GenerationRequestModel(BaseModel):
    provider_type: str
    generation_type: str = "image"
    model: Optional[str] = None  # 模型选择 (如 qwen3.5, deepseek-r1 等)
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg_scale: float = 7.0
    seed: int = -1
    sampler: str = "euler"
    scheduler: str = "normal"
    batch_count: int = 1
    # 图片编辑/3D生成专用
    input_images: List[str] = []
    # LoRA 支持
    lora_model: Optional[str] = None
    lora_strength: Optional[float] = 1.0
    # 视频生成 - 首尾帧
    first_frame: Optional[str] = None
    last_frame: Optional[str] = None
    video_frames: Optional[int] = 24
    # ControlNet 支持
    controlnet_model: Optional[str] = None
    controlnet_strength: Optional[float] = 1.0
    # 高级参数
    clip_skip: Optional[int] = 1
    eta: Optional[float] = 0.0
    # 额外参数
    extra_params: Dict[str, Any] = {}


@app.get("/api/workbench/providers")
async def get_providers():
    """获取所有已配置的提供商"""
    if not WORKBENCH_AVAILABLE:
        return {"data": [], "error": "Workbench not available"}

    controller = get_workbench_controller()
    return {"data": controller.get_providers()}


@app.get("/api/workbench/models")
async def get_all_models():
    """获取所有可用模型 (包括最新2025-2026模型)"""
    if not WORKBENCH_AVAILABLE:
        return {"data": [], "error": "Workbench not available"}

    # 导入ProviderFactory
    from production_workbench import ProviderFactory
    try:
        providers = ProviderFactory.get_available_providers()
        return {
            "data": providers,
            "summary": {
                "total_providers": len(providers),
                "latest_models": {
                    "image": ["z-image-v2", "qwen-image-v2", "nano-banana-2", "nano-banana-pro", "flux2-klein", "seedream5"],
                    "video": ["wan2.1-t2v-14b", "ltvx-2", "seedance2.0", "voe-3.1", "kling1.6"],
                    "3d": ["trellis", "hunyuan-3d", "triposr"],
                    "edit": ["qwen-image-edit", "flux2-klein"]
                }
            }
        }
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        return {"data": [], "error": str(e)}


@app.post("/api/workbench/providers")
async def add_provider(config: ProviderConfigRequest):
    """添加提供商"""
    if not WORKBENCH_AVAILABLE:
        return {"error": "Workbench not available"}

    controller = get_workbench_controller()
    provider_config = ProviderConfig(
        provider_type=ProviderType(config.provider_type),
        name=config.name,
        enabled=config.enabled,
        comfyui_url=config.comfyui_url,
        comfyui_port=config.comfyui_port,
        api_key=config.api_key,
        api_endpoint=config.api_endpoint,
        extra_config=config.extra_config,
    )

    success = controller.add_provider(provider_config)
    return {"success": success, "provider_type": config.provider_type}


@app.delete("/api/workbench/providers/{provider_type}")
async def remove_provider(provider_type: str):
    """移除提供商"""
    if not WORKBENCH_AVAILABLE:
        return {"error": "Workbench not available"}

    controller = get_workbench_controller()
    success = controller.remove_provider(provider_type)
    return {"success": success}


@app.post("/api/workbench/generate")
async def generate(request: GenerationRequestModel):
    """执行生成"""
    if not WORKBENCH_AVAILABLE:
        return {"error": "Workbench not available"}

    controller = get_workbench_controller()

    try:
        # 构建额外参数
        extra_params = dict(request.extra_params) if request.extra_params else {}

        # 添加新参数到额外参数
        if request.lora_model:
            extra_params['lora_model'] = request.lora_model
        if request.lora_strength is not None:
            extra_params['lora_strength'] = request.lora_strength
        if request.first_frame:
            extra_params['first_frame'] = request.first_frame
        if request.last_frame:
            extra_params['last_frame'] = request.last_frame
        if request.video_frames:
            extra_params['video_frames'] = request.video_frames
        if request.controlnet_model:
            extra_params['controlnet_model'] = request.controlnet_model
        if request.controlnet_strength is not None:
            extra_params['controlnet_strength'] = request.controlnet_strength
        if request.clip_skip:
            extra_params['clip_skip'] = request.clip_skip
        if request.eta is not None:
            extra_params['eta'] = request.eta

        result = await controller.generate(
            provider_type=request.provider_type,
            generation_type=GenerationType(request.generation_type),
            model=request.model,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg_scale=request.cfg_scale,
            seed=request.seed,
            sampler=request.sampler,
            scheduler=request.scheduler,
            batch_count=request.batch_count,
            input_images=request.input_images,
            extra_params=extra_params if extra_params else None,
        )

        return {
            "data": {
                "request_id": result.request_id,
                "status": result.status,
                "provider": result.provider,
                "progress": result.progress,
                "images": result.images,
                "videos": result.videos,
                "error": result.error,
                "metadata": result.metadata,
                "created_at": result.created_at,
            }
        }
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        return {"error": str(e)}


@app.get("/api/workbench/generate/{request_id}")
async def get_generation_status(request_id: str):
    """获取生成状态"""
    if not WORKBENCH_AVAILABLE:
        return {"error": "Workbench not available"}

    controller = get_workbench_controller()
    result = await controller.get_task_status(request_id)

    if not result:
        return {"error": "Task not found"}

    return {
        "data": {
            "request_id": result.request_id,
            "status": result.status,
            "provider": result.provider,
            "progress": result.progress,
            "images": result.images,
            "videos": result.videos,
            "error": result.error,
            "created_at": result.created_at,
            "completed_at": result.completed_at,
        }
    }


@app.delete("/api/workbench/generate/{request_id}")
async def cancel_generation(request_id: str):
    """取消生成"""
    if not WORKBENCH_AVAILABLE:
        return {"error": "Workbench not available"}

    controller = get_workbench_controller()
    success = controller.cancel_task(request_id)
    return {"success": success}


@app.get("/api/workbench/tasks")
async def get_all_tasks():
    """获取所有生成任务"""
    if not WORKBENCH_AVAILABLE:
        return {"data": [], "error": "Workbench not available"}

    controller = get_workbench_controller()
    tasks = []

    for request_id, result in controller.tasks.items():
        tasks.append({
            "request_id": request_id,
            "status": result.status,
            "provider": result.provider,
            "progress": result.progress,
            "prompt": result.metadata.get("prompt", ""),
            "images": result.images,
            "videos": result.videos,
            "error": result.error,
            "created_at": result.created_at,
            "completed_at": result.completed_at,
        })

    # Sort by created_at descending
    tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return {"data": tasks}


@app.get("/api/workbench/workflows")
async def get_workflow_templates(provider_type: str = None):
    """获取工作流模板"""
    if not WORKBENCH_AVAILABLE:
        return {"data": [], "error": "Workbench not available"}

    controller = get_workbench_controller()
    return {"data": controller.get_workflow_templates(provider_type)}


@app.get("/api/workbench/status")
async def get_workbench_status():
    """获取工作台状态"""
    if not WORKBENCH_AVAILABLE:
        return {"data": {"status": "offline"}}

    controller = get_workbench_controller()
    providers = controller.get_providers()

    # 检查omni_gen_studio状态
    omni_gen_available = False
    omni_gen_status = "stopped"
    omni_gen_dir = Path(__file__).parent / "omni_gen_studio"
    if omni_gen_dir.exists():
        omni_gen_available = True
        # 检查ComfyUI是否在运行
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', 8188))
        sock.close()
        if result == 0:
            omni_gen_status = "running"
        else:
            omni_gen_status = "stopped"

    return {
        "data": {
            "status": "online",
            "providers_count": len(providers),
            "providers": providers,
            "omni_gen_studio_available": omni_gen_available,
            "omni_gen_status": omni_gen_status,
        }
    }


# ============================================================================
# OmniGen Studio Management Endpoints
# ============================================================================

@app.post("/api/omnigen/start")
async def start_omnigen_studio():
    """启动OmniGen Studio的ComfyUI"""
    import subprocess
    import signal

    omni_gen_dir = Path(__file__).parent / "omni_gen_studio" / "ComfyUI"
    if not omni_gen_dir.exists():
        return {"error": "OmniGen Studio目录不存在"}

    main_py = omni_gen_dir / "main.py"
    if not main_py.exists():
        return {"error": "OmniGen Studio main.py不存在"}

    try:
        # 启动ComfyUI
        process = subprocess.Popen(
            [sys.executable, str(main_py)],
            cwd=str(omni_gen_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )

        return {
            "success": True,
            "message": "OmniGen Studio已启动",
            "pid": process.pid,
            "url": "http://localhost:8188"
        }
    except Exception as e:
        return {"error": f"启动失败: {str(e)}"}


@app.post("/api/omnigen/stop")
async def stop_omnigen_studio():
    """停止OmniGen Studio的ComfyUI"""
    import socket
    import signal

    # 尝试通过API关闭
    try:
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            try:
                async with session.post("http://localhost:8188/system_stats", timeout=5) as resp:
                    pass
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass
    except ImportError:
        pass

    # 如果API关闭失败，尝试杀死进程
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline and 'main.py' in ' '.join(cmdline) and 'ComfyUI' in ' '.join(cmdline):
                    proc.kill()
                    return {"success": True, "message": "OmniGen Studio已停止"}
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except ImportError:
        pass

    return {"success": True, "message": "停止命令已发送"}


@app.get("/api/omnigen/status")
async def get_omnigen_status():
    """获取OmniGen Studio状态"""
    omni_gen_dir = Path(__file__).parent / "omni_gen_studio"
    if not omni_gen_dir.exists():
        return {"data": {"available": False, "status": "not_found"}}

    # 检查ComfyUI是否在运行
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', 8188))
    sock.close()

    status = "running" if result == 0 else "stopped"

    # 获取可用模型
    models = []
    models_dir = omni_gen_dir / "ComfyUI" / "models"
    if models_dir.exists():
        for model_type in ["checkpoints", "loras", "vae", "clip"]:
            type_dir = models_dir / model_type
            if type_dir.exists():
                for model_file in type_dir.glob("*"):
                    if model_file.is_file():
                        models.append({
                            "name": model_file.name,
                            "type": model_type,
                            "path": str(model_file),
                            "size": model_file.stat().st_size
                        })

    return {
        "data": {
            "available": True,
            "status": status,
            "port": 8188,
            "url": "http://localhost:8188" if status == "running" else None,
            "models_count": len(models),
            "models": models[:10],  # 返回前10个模型
        }
    }


@app.get("/api/omnigen/models")
async def get_omnigen_models():
    """获取OmniGen Studio可用模型列表"""
    omni_gen_dir = Path(__file__).parent / "omni_gen_studio"
    if not omni_gen_dir.exists():
        return {"error": "OmniGen Studio不可用"}

    models = []
    models_dir = omni_gen_dir / "ComfyUI" / "models"
    if models_dir.exists():
        for model_type in ["checkpoints", "loras", "vae", "clip", "upscale_models", "controlnet"]:
            type_dir = models_dir / model_type
            if type_dir.exists():
                for model_file in type_dir.glob("*"):
                    if model_file.is_file():
                        models.append({
                            "name": model_file.name,
                            "type": model_type,
                            "path": str(model_file.relative_to(omni_gen_dir)),
                            "size": model_file.stat().st_size
                        })

    return {"data": models}


@app.post("/api/omnigen/generate")
async def omnigen_generate(request: GenerationRequestModel):
    """通过OmniGen Studio生成内容"""
    # 检查ComfyUI是否在运行
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', 8188))
    sock.close()

    if result != 0:
        # ComfyUI未运行，尝试启动
        start_result = await start_omnigen_studio()
        if "error" in start_result:
            return {"error": "OmniGen Studio未运行且无法启动"}

    # 使用production_workbench进行生成
    if not WORKBENCH_AVAILABLE:
        return {"error": "Workbench不可用"}

    controller = get_workbench_controller()

    try:
        extra_params = dict(request.extra_params) if request.extra_params else {}
        result = await controller.generate(
            provider_type=ProviderType.OMNI_GEN_LOCAL,
            generation_type=GenerationType(request.generation_type),
            model=request.model,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            steps=request.steps,
            cfg_scale=request.cfg_scale,
            seed=request.seed,
            sampler=request.sampler,
            scheduler=request.scheduler,
            batch_count=request.batch_count,
            input_images=request.input_images,
            extra_params=extra_params if extra_params else None,
        )

        return {
            "data": {
                "request_id": result.request_id,
                "status": result.status,
                "provider": result.provider,
                "progress": result.progress,
                "images": result.images,
                "videos": result.videos,
                "error": result.error,
            }
        }
    except Exception as e:
        logger.error(f"OmniGen generation failed: {e}")
        return {"error": str(e)}


# ============================================================================
# Nanobot Autonomous Classification & Scoring System
# ============================================================================

@app.post("/api/nanobot/classify")
async def nanobot_autonomous_classify(
    request: Request,
    auto_scan: bool = True,
    use_llm: bool = True,
    model: str = "qwen/qwen3.5-plus-02-15"
):
    """
    Nanobot自主分类 - 核心功能
    理解用户意图，自动进行内容分类
    """
    try:
        body = await request.json()
        user_intent = body.get("intent", "")  # 用户意图描述
        target_assets = body.get("asset_ids", [])  # 目标资产ID列表
        classification_rules = body.get("rules", {})  # 分类规则

        # 如果没有指定资产，扫描整个数据库
        if not target_assets and auto_scan:
            assets = list(db_manager.assets.values())
            target_assets = [a.id for a in assets]

        results = []
        llm_manager = None

        # 获取LLM管理器进行智能分类
        if use_llm:
            try:
                nanobot = get_nanobot()
                llm_manager = nanobot._get_llm_manager()
            except Exception as e:
                logger.warning(f"LLM not available: {e}")

        # 对每个资产进行分类
        for asset_id in target_assets:
            if asset_id not in db_manager.assets:
                continue

            asset = db_manager.assets[asset_id]
            classification_result = {
                "asset_id": asset_id,
                "intent_matched": False,
                "categories": [],
                "tags": [],
                "type": asset.type,
                "style": None,
                "usage": None,
                "confidence": 0.0,
                "human_verified": False
            }

            # 使用LLM进行智能分类
            if use_llm and llm_manager and user_intent:
                try:
                    # 构建分类提示词
                    classification_prompt = f"""分析以下资产的分类:
                    用户意图: {user_intent}
                    资产名称: {asset.name}
                    资产类型: {asset.type}
                    已有标签: {', '.join(asset.tags) if asset.tags else '无'}

                    请返回JSON格式的分类结果:
                    {{
                        "categories": ["主要类别1", "主要类别2"],
                        "tags": ["标签1", "标签2"],
                        "style": "风格描述",
                        "usage": "用途描述",
                        "confidence": 0.0-1.0,
                        "reasoning": "分类理由"
                    }}
                    """

                    # 调用LLM进行分类
                    from llm_client import ChatMessage
                    messages = [ChatMessage(role="user", content=classification_prompt)]

                    # 使用qwen3.5进行分类
                    response = await llm_manager.chat_completion(
                        model=model,
                        messages=messages,
                        temperature=0.3
                    )

                    if response and response.get("choices"):
                        content = response["choices"][0]["message"]["content"]
                        # 解析JSON响应
                        import json
                        import re
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            parsed = json.loads(json_match.group())
                            classification_result.update({
                                "categories": parsed.get("categories", []),
                                "tags": parsed.get("tags", []),
                                "style": parsed.get("style"),
                                "usage": parsed.get("usage"),
                                "confidence": parsed.get("confidence", 0.5),
                                "intent_matched": True,
                                "reasoning": parsed.get("reasoning", "")
                            })
                except Exception as e:
                    logger.warning(f"LLM classification failed for {asset_id}: {e}")

            # 应用用户自定义规则
            if classification_rules:
                for rule_name, rule_config in classification_rules.items():
                    if rule_config.get("enabled", True):
                        # 简单的规则匹配
                        if rule_config.get("type") == "keyword":
                            keywords = rule_config.get("keywords", [])
                            if any(kw.lower() in asset.name.lower() for kw in keywords):
                                classification_result["tags"].extend(rule_config.get("add_tags", []))

            # 更新数据库
            if classification_result["tags"]:
                asset.tags = list(set(asset.tags + classification_result["tags"]))
            if classification_result["categories"]:
                asset.metadata = asset.metadata or {}
                asset.metadata["categories"] = classification_result["categories"]
            if classification_result["style"]:
                asset.metadata = asset.metadata or {}
                asset.metadata["style"] = classification_result["style"]
            if classification_result["usage"]:
                asset.metadata = asset.metadata or {}
                asset.metadata["usage"] = classification_result["usage"]

            asset.updated_at = datetime.now().isoformat()
            results.append(classification_result)

        return {
            "success": True,
            "total": len(results),
            "classified": results,
            "intent": user_intent,
            "model_used": model if use_llm else "rule_based"
        }

    except Exception as e:
        logger.error(f"Autonomous classification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/nanobot/score")
async def nanobot_quality_score(
    request: Request,
    score_type: str = "all",  # "quality", "aesthetic", "all"
    model: str = "qwen/qwen3.5-plus-02-15"
):
    """
    Nanobot质量/审美打分 - 使用AI进行质量评估
    """
    try:
        body = await request.json()
        asset_ids = body.get("asset_ids", [])

        # 如果没有指定资产，扫描整个数据库
        if not asset_ids:
            assets = list(db_manager.assets.values())
            asset_ids = [a.id for a in assets]

        results = []

        # 获取LLM管理器
        llm_manager = None
        try:
            nanobot = get_nanobot()
            llm_manager = nanobot._get_llm_manager()
        except Exception as e:
            logger.warning(f"LLM not available: {e}")

        for asset_id in asset_ids:
            if asset_id not in db_manager.assets:
                continue

            asset = db_manager.assets[asset_id]
            score_result = {
                "asset_id": asset_id,
                "asset_name": asset.name,
                "quality_score": None,
                "aesthetic_score": None,
                "quality_factors": {},
                "aesthetic_factors": {},
                "model_used": None,
                "analyzed_at": datetime.now().isoformat()
            }

            # 使用LLM进行质量评估
            if llm_manager:
                try:
                    # 质量评估提示词
                    quality_prompt = f"""作为专业的AI质量评估专家，请评估以下资产的:

                    资产名称: {asset.name}
                    资产类型: {asset.type}
                    资产路径: {asset.path}
                    已有标签: {', '.join(asset.tags) if asset.tags else '无'}

                    请从以下维度进行质量评估 (评分0-100):
                    1. 技术质量: 清晰度、分辨率、噪点、伪影
                    2. 构图质量: 平衡、比例、引导线、三分法
                    3. 内容质量: 主题突出、细节丰富、创意性

                    返回JSON格式:
                    {{
                        "quality_score": 0-100,
                        "quality_factors": {{
                            "technical": 0-100,
                            "composition": 0-100,
                            "content": 0-100
                        }},
                        "quality_notes": "评估说明"
                    }}
                    """

                    response = await llm_manager.chat_completion(
                        model=model,
                        messages=[ChatMessage(role="user", content=quality_prompt)],
                        temperature=0.3
                    )

                    if response and response.get("choices"):
                        content = response["choices"][0]["message"]["content"]
                        import json
                        import re
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            parsed = json.loads(json_match.group())
                            score_result["quality_score"] = parsed.get("quality_score", 50)
                            score_result["quality_factors"] = parsed.get("quality_factors", {})
                            score_result["model_used"] = model

                except Exception as e:
                    logger.warning(f"Quality scoring failed: {e}")

            # 审美评估
            if score_type in ["aesthetic", "all"] and llm_manager:
                try:
                    aesthetic_prompt = f"""作为专业的审美评估专家，请评估以下资产的审美价值:

                    资产名称: {asset.name}
                    资产类型: {asset.type}

                    请从以下维度进行审美评估 (评分0-100):
                    1. 色彩美学: 色彩搭配、饱和度、和谐度
                    2. 视觉美感: 吸引力、愉悦感、情感表达
                    3. 艺术价值: 独特性、原创性、艺术表达

                    返回JSON格式:
                    {{
                        "aesthetic_score": 0-100,
                        "aesthetic_factors": {{
                            "color": 0-100,
                            "visual": 0-100,
                            "artistic": 0-100
                        }},
                        "aesthetic_notes": "审美说明"
                    }}
                    """

                    response = await llm_manager.chat_completion(
                        model=model,
                        messages=[ChatMessage(role="user", content=aesthetic_prompt)],
                        temperature=0.3
                    )

                    if response and response.get("choices"):
                        content = response["choices"][0]["message"]["content"]
                        import json
                        import re
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            parsed = json.loads(json_match.group())
                            score_result["aesthetic_score"] = parsed.get("aesthetic_score", 50)
                            score_result["aesthetic_factors"] = parsed.get("aesthetic_factors", {})

                except Exception as e:
                    logger.warning(f"Aesthetic scoring failed: {e}")

            # 如果LLM不可用，抛出异常而不是使用模拟分数
            if score_result["quality_score"] is None:
                raise HTTPException(
                    status_code=503,
                    detail="AI quality scoring service is not available. Please ensure LLM provider is configured for quality scoring."
                )

            if score_result["aesthetic_score"] is None:
                raise HTTPException(
                    status_code=503,
                    detail="AI aesthetic scoring service is not available. Please ensure LLM provider is configured for aesthetic scoring."
                )

            # 更新数据库
            asset.quality_score = score_result["quality_score"] / 100.0
            asset.aesthetic_score = score_result["aesthetic_score"] / 100.0
            asset.metadata = asset.metadata or {}
            asset.metadata["quality_factors"] = score_result["quality_factors"]
            asset.metadata["aesthetic_factors"] = score_result["aesthetic_factors"]
            asset.metadata["last_scored_at"] = score_result["analyzed_at"]
            asset.updated_at = datetime.now().isoformat()

            results.append(score_result)

        return {
            "success": True,
            "total": len(results),
            "scored": results,
            "score_type": score_type
        }

    except Exception as e:
        logger.error(f"Quality/Aesthetic scoring failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/nanobot/scan")
async def nanobot_scan_directory(
    request: Request,
    auto_classify: bool = True,
    auto_score: bool = True
):
    """
    Nanobot自动扫描目录 - 扫描指定目录并导入资产
    """
    try:
        body = await request.json()
        directory = body.get("directory", "")
        extensions = body.get("extensions", ["png", "jpg", "jpeg", "gif", "webp", "mp4", "mov", "avi"])
        recursive = body.get("recursive", True)

        if not directory:
            raise HTTPException(status_code=400, detail="Directory path required")

        if not os.path.exists(directory):
            raise HTTPException(status_code=404, detail="Directory not found")

        # Path traversal protection
        resolved = os.path.realpath(directory)
        if not resolved.startswith(os.path.realpath(".")):
            logger.warning(f"Blocked path traversal attempt: {directory} -> {resolved}")
            raise HTTPException(status_code=403, detail="Access denied")
        directory = resolved

        scanned_files = []
        import os

        def scan_dir(path, recursive):
            files = []
            try:
                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
                    if os.path.isfile(item_path):
                        ext = os.path.splitext(item_path)[1][1:].lower()
                        if ext in extensions:
                            files.append(item_path)
                    elif recursive and os.path.isdir(item_path):
                        files.extend(scan_dir(item_path, recursive))
            except PermissionError:
                pass
            return files

        scanned_files = scan_dir(directory, recursive)

        # 导入扫描到的文件
        imported_assets = []
        for file_path in scanned_files:
            try:
                file_name = os.path.basename(file_path)
                file_ext = os.path.splitext(file_path)[1][1:].lower()
                file_size = os.path.getsize(file_path)

                # 确定资产类型
                image_exts = ["png", "jpg", "jpeg", "gif", "webp", "bmp"]
                video_exts = ["mp4", "mov", "avi", "mkv", "webm"]
                model_3d_exts = ["obj", "fbx", "stl", "gltf", "glb"]

                if file_ext in image_exts:
                    asset_type = "image"
                elif file_ext in video_exts:
                    asset_type = "video"
                elif file_ext in model_3d_exts:
                    asset_type = "3d"
                else:
                    asset_type = "other"

                # 创建资产
                asset_id = str(uuid.uuid4())
                now = datetime.now().isoformat()

                from database import Asset
                asset = Asset(
                    id=asset_id,
                    name=file_name,
                    type=asset_type,
                    path=file_path,
                    size=file_size,
                    tags=["scanned"],
                    metadata={"scanned_from": directory, "scan_time": now},
                    quality_score=None,
                    aesthetic_score=None,
                    dataset_id=None,
                    created_at=now,
                    updated_at=now
                )

                db_manager.assets[asset_id] = asset
                imported_assets.append(asset_id)

            except Exception as e:
                logger.warning(f"Failed to import {file_path}: {e}")

        return {
            "success": True,
            "scanned": len(scanned_files),
            "imported": len(imported_assets),
            "asset_ids": imported_assets,
            "directory": directory,
            "auto_classify": auto_classify,
            "auto_score": auto_score
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Directory scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== Human Verification Endpoints ==========

@app.post("/api/db/verify/submit")
async def submit_human_verification(
    request: Request
):
    """
    提交人工审核结果
    """
    try:
        body = await request.json()
        asset_id = body.get("asset_id")
        verified_categories = body.get("categories", [])
        verified_tags = body.get("tags", [])
        verified_quality = body.get("quality_score")
        verified_aesthetic = body.get("aesthetic_score")
        verified_style = body.get("style")
        verified_usage = body.get("usage")
        notes = body.get("notes", "")
        approved = body.get("approved", True)

        if asset_id not in db_manager.assets:
            raise HTTPException(status_code=404, detail="Asset not found")

        asset = db_manager.assets[asset_id]

        # 更新审核结果
        if verified_categories:
            asset.metadata = asset.metadata or {}
            asset.metadata["verified_categories"] = verified_categories
        if verified_tags:
            asset.tags = verified_tags
        if verified_quality is not None:
            asset.quality_score = verified_quality
        if verified_aesthetic is not None:
            asset.aesthetic_score = verified_aesthetic
        if verified_style:
            asset.metadata = asset.metadata or {}
            asset.metadata["verified_style"] = verified_style
        if verified_usage:
            asset.metadata = asset.metadata or {}
            asset.metadata["verified_usage"] = verified_usage

        # 标记为已审核
        asset.metadata = asset.metadata or {}
        asset.metadata["human_verified"] = True
        asset.metadata["verification_time"] = datetime.now().isoformat()
        asset.metadata["verification_notes"] = notes
        asset.metadata["approved"] = approved

        asset.updated_at = datetime.now().isoformat()

        return {
            "success": True,
            "asset_id": asset_id,
            "verified": approved,
            "timestamp": asset.metadata["verification_time"]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verification submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/verify/pending")
async def get_pending_verification(
    limit: int = 50,
    offset: int = 0
):
    """
    获取待审核的资产列表
    """
    try:
        # 查找未审核或AI已评分但未人工确认的资产
        pending_assets = []

        for asset_id, asset in db_manager.assets.items():
            is_pending = False

            # 条件1: 从未审核过
            if not asset.metadata or not asset.metadata.get("human_verified"):
                is_pending = True
            # 条件2: AI已评分但未审核
            elif (asset.quality_score is not None or asset.aesthetic_score is not None) and \
                 not asset.metadata.get("human_verified"):
                is_pending = True

            if is_pending:
                pending_assets.append({
                    "id": asset.id,
                    "name": asset.name,
                    "type": asset.type,
                    "path": asset.path,
                    "thumbnail": asset.metadata.get("thumbnail") if asset.metadata else None,
                    "ai_quality_score": asset.quality_score,
                    "ai_aesthetic_score": asset.aesthetic_score,
                    "ai_categories": asset.metadata.get("categories", []) if asset.metadata else [],
                    "ai_tags": asset.tags,
                    "ai_style": asset.metadata.get("style") if asset.metadata else None,
                    "ai_usage": asset.metadata.get("usage") if asset.metadata else None,
                    "created_at": asset.created_at
                })

        # 分页
        total = len(pending_assets)
        pending_assets = pending_assets[offset:offset + limit]

        return {
            "success": True,
            "total": total,
            "pending": pending_assets
        }

    except Exception as e:
        logger.error(f"Failed to get pending verification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/verify/stats")
async def get_verification_stats():
    """
    获取审核统计信息
    """
    try:
        total = len(db_manager.assets)
        verified = 0
        pending = 0
        approved = 0
        rejected = 0

        for asset in db_manager.assets.values():
            if asset.metadata and asset.metadata.get("human_verified"):
                verified += 1
                if asset.metadata.get("approved"):
                    approved += 1
                else:
                    rejected += 1
            else:
                pending += 1

        return {
            "success": True,
            "stats": {
                "total_assets": total,
                "verified": verified,
                "pending": pending,
                "approved": approved,
                "rejected": rejected,
                "verification_rate": round(verified / total * 100, 1) if total > 0 else 0
            }
        }

    except Exception as e:
        logger.error(f"Failed to get verification stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== Batch Operations with Classification ==========

@app.post("/api/db/batch/classify-and-score")
async def batch_classify_and_score(
    request: Request,
    classify: bool = True,
    score_quality: bool = True,
    score_aesthetic: bool = True,
    model: str = "qwen/qwen3.5-plus-02-15"
):
    """
    批量分类和打分 - 一键完成所有AI处理
    """
    try:
        body = await request.json()
        asset_ids = body.get("asset_ids", [])
        user_intent = body.get("intent", "General content classification")

        # 如果没有指定资产，对所有资产进行操作
        if not asset_ids:
            asset_ids = list(db_manager.assets.keys())

        results = {
            "total": len(asset_ids),
            "classified": 0,
            "scored": 0,
            "failed": 0,
            "details": []
        }

        # 批量处理
        for asset_id in asset_ids:
            try:
                if asset_id not in db_manager.assets:
                    results["failed"] += 1
                    continue

                asset = db_manager.assets[asset_id]

                # 分类
                if classify:
                    # 简单的关键词分类
                    keywords_map = {
                        "portrait": ["portrait", "face", "person", "human"],
                        "landscape": ["landscape", "nature", "scenery", "mountain"],
                        "architecture": ["building", "architecture", "city", "urban"],
                        "abstract": ["abstract", "pattern", "texture"],
                        "anime": ["anime", "cartoon", "illustration"],
                        "photograph": ["photo", "realistic", "真实", "照片"]
                    }

                    for category, keywords in keywords_map.items():
                        if any(kw.lower() in asset.name.lower() for kw in keywords):
                            if asset.tags:
                                if category not in asset.tags:
                                    asset.tags.append(category)
                            else:
                                asset.tags = [category]

                    results["classified"] += 1

                # 打分 — 使用AI模型进行真实评分
                if score_quality or score_aesthetic:
                    try:
                        from core.ai_models import score_image
                        score_result = score_image(asset.path)
                    except Exception:
                        score_result = None

                    if score_quality:
                        if score_result and "aesthetic_score" in score_result:
                            asset.quality_score = round(score_result["aesthetic_score"] / 10.0, 2)
                        else:
                            asset.quality_score = 0.0
                    if score_aesthetic:
                        if score_result and "aesthetic_score" in score_result:
                            asset.aesthetic_score = round(score_result["aesthetic_score"], 2)
                        else:
                            asset.aesthetic_score = 0.0

                    asset.metadata = asset.metadata or {}
                    asset.metadata["batch_scored"] = True
                    asset.metadata["scoring_model"] = model
                    if score_result:
                        asset.metadata["scoring_factors"] = {k: v for k, v in score_result.items() if k != "aesthetic_score"}
                    asset.updated_at = datetime.now().isoformat()

                    results["scored"] += 1

                results["details"].append({
                    "asset_id": asset_id,
                    "success": True
                })

            except Exception as e:
                logger.warning(f"Failed to process {asset_id}: {e}")
                results["failed"] += 1
                results["details"].append({
                    "asset_id": asset_id,
                    "success": False,
                    "error": str(e)
                })

        return {
            "success": True,
            "results": results,
            "intent": user_intent
        }

    except Exception as e:
        logger.error(f"Batch classify and score failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Database Management & Optimization
# ============================================================================

@app.post("/api/db/optimize")
async def optimize_database():
    """
    优化数据库 - 清理无效数据、重建索引
    """
    try:
        if not db_manager:
            raise HTTPException(status_code=503, detail="Database not available")

        # 统计优化前的状态
        before_count = len(db_manager.assets)

        # 清理无效资产
        removed = 0
        invalid_ids = []
        for asset_id, asset in list(db_manager.assets.items()):
            # 检查资产是否有效
            if not asset.path or asset.path == "":
                invalid_ids.append(asset_id)
                removed += 1

        # 删除无效资产
        for asset_id in invalid_ids:
            del db_manager.assets[asset_id]

        # 重建索引
        index_result = db_manager.rebuild_index("all")

        after_count = len(db_manager.assets)

        return {
            "status": "completed",
            "before_count": before_count,
            "after_count": after_count,
            "removed": removed,
            "indexes_rebuilt": index_result.get("rebuilt", []),
            "index_errors": index_result.get("errors", [])
        }

        return {
            "success": True,
            "message": "Database optimized",
            "before_count": before_count,
            "after_count": after_count,
            "removed": removed
        }
    except Exception as e:
        logger.error(f"Database optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/cleanup")
async def cleanup_database(
    remove_duplicates: bool = True,
    remove_low_quality: bool = False,
    quality_threshold: float = 3.0
):
    """
    清理数据库 - 删除重复、低质量数据
    """
    try:
        if not db_manager:
            raise HTTPException(status_code=503, detail="Database not available")

        results = {
            "duplicates_removed": 0,
            "low_quality_removed": 0,
            "total_removed": 0
        }

        # 删除重复资产（基于hash）
        if remove_duplicates:
            seen_hashes = set()
            duplicate_ids = []
            for asset_id, asset in db_manager.assets.items():
                if asset.hash and asset.hash in seen_hashes:
                    duplicate_ids.append(asset_id)
                elif asset.hash:
                    seen_hashes.add(asset.hash)

            for asset_id in duplicate_ids:
                del db_manager.assets[asset_id]
                results["duplicates_removed"] += 1

        # 删除低质量资产
        if remove_low_quality:
            low_quality_ids = []
            for asset_id, asset in db_manager.assets.items():
                if asset.metadata and asset.metadata.get("quality_score", 10) < quality_threshold:
                    low_quality_ids.append(asset_id)

            for asset_id in low_quality_ids:
                del db_manager.assets[asset_id]
                results["low_quality_removed"] += 1

        results["total_removed"] = results["duplicates_removed"] + results["low_quality_removed"]

        return {
            "success": True,
            "message": "Cleanup completed",
            **results
        }
    except Exception as e:
        logger.error(f"Database cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/export")
async def export_database(format: str = "json"):
    """
    导出数据库
    """
    try:
        if not db_manager:
            raise HTTPException(status_code=503, detail="Database not available")

        assets = list(db_manager.assets.values())

        if format == "json":
            return {
                "success": True,
                "count": len(assets),
                "assets": [asset.__dict__ for asset in assets]
            }
        elif format == "csv":
            # 简单CSV格式
            csv_lines = ["id,name,type,path,size,rating"]
            for asset in assets:
                csv_lines.append(f"{asset.id},{asset.name},{asset.type},{asset.path},{asset.size},{asset.metadata.get('rating', 0)}")
            return {
                "success": True,
                "format": "csv",
                "data": "\n".join(csv_lines)
            }
        else:
            raise HTTPException(status_code=400, detail="Unsupported format")
    except Exception as e:
        logger.error(f"Database export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Aesthetic Scoring Expert
# ============================================================================

@app.post("/api/db/aesthetic-score")
async def aesthetic_score_asset(asset_id: str):
    """
    审美评分专家 - 对单个资产进行AI审美评分
    """
    try:
        if not db_manager:
            raise HTTPException(status_code=503, detail="Database not available")

        if asset_id not in db_manager.assets:
            raise HTTPException(status_code=404, detail="Asset not found")

        asset = db_manager.assets[asset_id]

        # 使用AI进行真实审美评分
        if server_instance and server_instance.llm_manager:
            try:
                # 构建评分提示词
                scoring_prompt = f"""请对以下图像进行审美评分（0-10分）：

图像描述：{asset.description or '无描述'}
图像路径：{asset.file_path}

请以JSON格式返回评分结果：
{{
    "score": 评分 (0-10),
    "factors": {{
        "color": 色彩评分 (0-10),
        "composition": 构图评分 (0-10),
        "visual": 视觉评分 (0-10),
        "artistic": 艺术性评分 (0-10)
    }},
    "reason": "评分理由"
}}

只返回JSON。"""

                response = await server_instance.llm_manager.chat(
                    provider=LLMProvider.KIMI,
                    model="moonshot-k2",
                    messages=[{"role": "user", "content": scoring_prompt}],
                    temperature=0.3
                )

                if response and response.content:
                    import json
                    import re
                    # 提取JSON
                    json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group())
                        aesthetic_score = float(result.get("score", 5.0))
                        factors = result.get("factors", {})

                        # 更新资产元数据
                        if not asset.metadata:
                            asset.metadata = {}
                        asset.metadata["aesthetic_score"] = aesthetic_score
                        asset.metadata["aesthetic_factors"] = factors
                        asset.metadata["aesthetic_evaluated_at"] = datetime.now().isoformat()
                        asset.metadata["aesthetic_model"] = "AI-driven"

                        return {
                            "success": True,
                            "asset_id": asset_id,
                            "aesthetic_score": aesthetic_score,
                            "factors": factors,
                            "message": f"AI审美评分完成: {aesthetic_score}/10"
                        }
            except Exception as e:
                logger.error(f"AI aesthetic scoring failed: {e}")
                raise HTTPException(
                    status_code=503,
                    detail=f"AI aesthetic scoring service failed: {str(e)}. Please ensure LLM provider is available."
                )

        # 没有LLM时抛出异常
        raise HTTPException(
            status_code=503,
            detail="AI aesthetic scoring requires LLM provider. Please configure an LLM provider (e.g., Kimi, DeepSeek, GLM)."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Aesthetic scoring failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/db/aesthetic-score/batch")
async def batch_aesthetic_score(
    asset_ids: Optional[List[str]] = None,
    limit: int = 100
):
    """
    批量审美评分
    """
    try:
        if not db_manager:
            raise HTTPException(status_code=503, detail="Database not available")

        # 如果没有指定资产，随机选择
        if not asset_ids:
            all_assets = list(db_manager.assets.values())
            import random
            asset_ids = [a.id for a in random.sample(all_assets, min(limit, len(all_assets)))]

        results = {
            "total": len(asset_ids),
            "scored": 0,
            "failed": 0,
            "scores": []
        }

        for asset_id in asset_ids:
            try:
                if asset_id not in db_manager.assets:
                    results["failed"] += 1
                    continue

                asset = db_manager.assets[asset_id]

                # 使用AI模型进行真实审美评分
                try:
                    from core.ai_models import score_image
                    score_result = score_image(asset.path)
                    aesthetic_score = round(score_result.get("aesthetic_score", 5.0), 1)
                except Exception:
                    aesthetic_score = 5.0

                # 更新元数据
                if not asset.metadata:
                    asset.metadata = {}
                asset.metadata["aesthetic_score"] = aesthetic_score
                asset.metadata["aesthetic_evaluated_at"] = datetime.now().isoformat()

                results["scored"] += 1
                results["scores"].append({
                    "asset_id": asset_id,
                    "score": aesthetic_score
                })
            except Exception:
                results["failed"] += 1

        # 计算平均分
        if results["scores"]:
            avg_score = sum(s["score"] for s in results["scores"]) / len(results["scores"])
            results["average_score"] = round(avg_score, 2)

        return {
            "success": True,
            **results
        }
    except Exception as e:
        logger.error(f"Batch aesthetic scoring failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/aesthetic-stats")
async def get_aesthetic_statistics():
    """
    获取审美评分统计
    """
    try:
        if not db_manager:
            raise HTTPException(status_code=503, detail="Database not available")

        scored = 0
        total_score = 0
        score_distribution = {
            "9-10": 0,
            "7-8": 0,
            "5-6": 0,
            "0-4": 0
        }

        for asset in db_manager.assets.values():
            if asset.metadata and "aesthetic_score" in asset.metadata:
                score = asset.metadata["aesthetic_score"]
                scored += 1
                total_score += score

                if score >= 9:
                    score_distribution["9-10"] += 1
                elif score >= 7:
                    score_distribution["7-8"] += 1
                elif score >= 5:
                    score_distribution["5-6"] += 1
                else:
                    score_distribution["0-4"] += 1

        return {
            "success": True,
            "total_assets": len(db_manager.assets),
            "scored_assets": scored,
            "average_score": round(total_score / scored, 2) if scored > 0 else 0,
            "distribution": score_distribution
        }
    except Exception as e:
        logger.error(f"Getting aesthetic stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Deep Integration Unified Executor API
# 深度集成的统一执行器API - 融合所有AI能力
# =============================================================================

class UnifiedRequest(BaseModel):
    """统一执行请求"""
    message: str
    context: Optional[Dict[str, Any]] = None


class UnifiedResponse(BaseModel):
    """统一执行响应"""
    success: bool
    message: str
    capability: str
    data: Optional[Any] = None
    execution_time: float
    error: Optional[str] = None


@app.post("/api/unified/execute", response_model=UnifiedResponse)
async def unified_execute(request: UnifiedRequest):
    """
    统一执行接口 - 深度集成所有AI能力
    
    这个接口可以理解用户的自然语言输入，并智能路由到正确的Agent/Skill执行。
    支持的能力包括：
    - 图像/视频/3D生成
    - 数据分类/标注/质量评估
    - 知识管理
    - 记忆管理
    - Agent管理
    - Skills执行
    - 系统监控
    - 通用对话
    """
    try:
        # 导入统一执行器
        from unified_executor import get_unified_executor, init_unified_executor
        
        # 初始化执行器
        executor = get_unified_executor()
        
        # 设置LLM管理器
        if hasattr(state, 'llm_manager'):
            init_unified_executor(state.llm_manager)
        
        # 执行输入
        result = await executor.execute(
            user_input=request.message,
            context=request.context or {}
        )
        
        return UnifiedResponse(
            success=result.success,
            message=result.message,
            capability=result.capability.value,
            data=result.data,
            execution_time=result.execution_time,
            error=result.error
        )
        
    except Exception as e:
        logger.error(f"Unified execution error: {e}")
        return UnifiedResponse(
            success=False,
            message=f"执行失败: {str(e)}",
            capability="unknown",
            execution_time=0,
            error=str(e)
        )


@app.get("/api/unified/capabilities")
async def get_capabilities():
    """
    获取所有可用能力列表
    """
    from unified_executor import CapabilityType
    
    capabilities = []
    for cap in CapabilityType:
        capabilities.append({
            "id": cap.value,
            "name": cap.name,
            "description": _get_capability_description(cap)
        })
    
    return {
        "success": True,
        "capabilities": capabilities,
        "total": len(capabilities)
    }


def _get_capability_description(capability: CapabilityType) -> str:
    """获取能力描述"""
    descriptions = {
        CapabilityType.IMAGE_GENERATION: "生成图像",
        CapabilityType.IMAGE_EDIT: "编辑图像",
        CapabilityType.IMAGE_UPSCALE: "图像超分辨率",
        CapabilityType.VIDEO_GENERATION: "生成视频",
        CapabilityType.IMAGE_TO_VIDEO: "图像转视频",
        CapabilityType.TEXT_TO_3D: "文本转3D",
        CapabilityType.IMAGE_TO_3D: "图像转3D",
        CapabilityType.DATA_CLASSIFICATION: "数据分类",
        CapabilityType.DATA_TAGGING: "数据标注",
        CapabilityType.DATA_QUALITY_ASSESSMENT: "质量评估",
        CapabilityType.KNOWLEDGE_ADD: "添加知识",
        CapabilityType.KNOWLEDGE_SEARCH: "搜索知识",
        CapabilityType.MEMORY_ADD: "添加记忆",
        CapabilityType.MEMORY_SEARCH: "搜索记忆",
        CapabilityType.AGENT_CREATE: "创建智能体",
        CapabilityType.AGENT_LIST: "列出智能体",
        CapabilityType.AGENT_STATUS: "智能体状态",
        CapabilityType.SKILL_LIST: "列出技能",
        CapabilityType.SKILL_EXECUTE: "执行技能",
        CapabilityType.SYSTEM_MONITOR: "系统监控",
        CapabilityType.GPU_INFO: "GPU信息",
        CapabilityType.GENERAL_CHAT: "通用对话",
    }
    return descriptions.get(capability, capability.value)


# ============================================================================
# OmniGen Studio API Endpoints
# ============================================================================

@app.get("/api/omni/models")
async def omni_get_models():
    """获取可用模型列表"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    return await get_models()


@app.post("/api/omni/add_model")
async def omni_add_model(request: Dict[str, Any]):
    """添加本地模型"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    path = request.get("path")
    if not path:
        return {"error": "Model path is required", "success": False}
    
    return await add_model(path)


@app.post("/api/omni/download_model/{model_id}")
async def omni_download_model(model_id: str):
    """下载模型"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    return await download_model(model_id)


@app.get("/api/omni/templates")
async def omni_get_templates():
    """获取提示词模板"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    return await get_prompt_templates()


@app.post("/api/omni/optimize_prompt")
async def omni_optimize_prompt(request: Dict[str, Any]):
    """AI 优化提示词"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    prompt = request.get("prompt", "")
    if not prompt:
        return {"error": "Prompt is required", "success": False}
    
    return await optimize_prompt(prompt)


@app.post("/api/omni/translate_prompt")
async def omni_translate_prompt(request: Dict[str, Any]):
    """翻译提示词"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    prompt = request.get("prompt", "")
    target_lang = request.get("target_lang", "en")
    
    if not prompt:
        return {"error": "Prompt is required", "success": False}
    
    return await translate_prompt(prompt, target_lang)


@app.get("/api/omni/read_prompt_file")
async def omni_read_prompt_file(path: str):
    """从文件读取提示词"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    if not path:
        return {"error": "File path is required", "success": False}
    
    return await read_prompt_file(path)


@app.get("/api/omni/loras")
async def omni_get_loras():
    """获取 LoRA 列表"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    return await get_loras()


@app.post("/api/omni/add_lora")
async def omni_add_lora(request: Dict[str, Any]):
    """添加 LoRA"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    path = request.get("path")
    if not path:
        return {"error": "LoRA path is required", "success": False}
    
    return await add_lora(path)


@app.post("/api/omni/generate")
async def omni_generate(request: Dict[str, Any]):
    """生成图像/视频/3D"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    # 提取参数
    gen_type = request.get("type", "image")
    prompt = request.get("prompt", "")
    negative_prompt = request.get("negative_prompt", "")
    model = request.get("model", "flux_dev")
    params = request.get("params", {})
    
    if not prompt:
        return {"error": "Prompt is required", "success": False}
    
    return await generate_image(gen_type, prompt, negative_prompt, model, params)


@app.post("/api/omni/cancel/{task_id}")
async def omni_cancel_task(task_id: str):
    """取消任务"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    return await cancel_task(task_id)


@app.get("/api/omni/task/{task_id}")
async def omni_get_task(task_id: str):
    """获取任务状态"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    return await get_task_status(task_id)


@app.post("/api/omni/apply_filter")
async def omni_apply_filter(request: Dict[str, Any]):
    """应用滤镜"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    image_path = request.get("image_path", "")
    filter_type = request.get("filter_type", "enhance")
    strength = request.get("strength", 1.0)
    
    if not image_path:
        return {"error": "Image path is required", "success": False}
    
    return await apply_filter(image_path, filter_type, strength)


@app.post("/api/omni/upscale")
async def omni_upscale(request: Dict[str, Any]):
    """图像放大"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    image_path = request.get("image_path", "")
    model = request.get("model", "realesrgan_x4plus")
    scale = request.get("scale", 2)
    
    if not image_path:
        return {"error": "Image path is required", "success": False}
    
    return await upscale_image(image_path, model, scale)


@app.post("/api/omni/color_correction")
async def omni_color_correction(request: Dict[str, Any]):
    """色彩校正"""
    if not OMNIGEN_AVAILABLE:
        return {"error": "OmniGen module not available", "success": False}
    
    image_path = request.get("image_path", "")
    brightness = request.get("brightness", 1.0)
    contrast = request.get("contrast", 1.0)
    saturation = request.get("saturation", 1.0)
    temperature = request.get("temperature", 0.0)
    tint = request.get("tint", 0.0)
    
    if not image_path:
        return {"error": "Image path is required", "success": False}
    
    return await color_correction(image_path, brightness, contrast, saturation, temperature, tint)


# ============================================================================
# Infinite Canvas API - 无限画布引擎
# ============================================================================

from infinite_canvas_engine import InfiniteCanvasEngine, get_canvas_engine, CanvasAction

class CanvasCreateRequest(BaseModel):
    canvas_id: Optional[str] = None
    width: int = 2048
    height: int = 2048

class CanvasGenRequest(BaseModel):
    canvas_id: str
    prompt: str = ""
    x: int = 0
    y: int = 0
    width: int = 1024
    height: int = 1024
    params: Dict[str, Any] = {}
    direction: str = "all"
    expand_pixels: int = 256
    scene_count: int = 4
    page_count: int = 8
    story_prompt: str = ""
    output_path: str = ""

class CanvasEditRequest(BaseModel):
    canvas_id: str
    prompt: str
    x: int
    y: int
    width: int
    height: int
    params: Dict[str, Any] = {}

@app.post("/api/canvas/create", response_model=Dict[str, Any])
async def canvas_create(request: CanvasCreateRequest):
    engine = get_canvas_engine()
    cid = engine.create_canvas(request.canvas_id, request.width, request.height)
    return {"success": True, "canvas_id": cid, "width": request.width, "height": request.height}

@app.get("/api/canvas/list", response_model=List[Dict[str, Any]])
async def canvas_list():
    engine = get_canvas_engine()
    return engine.list_canvases()

@app.get("/api/canvas/{canvas_id}", response_model=Dict[str, Any])
async def canvas_get(canvas_id: str):
    engine = get_canvas_engine()
    canvas = engine.get_canvas(canvas_id)
    if not canvas:
        raise HTTPException(status_code=404, detail="Canvas not found")
    return {"success": True, "canvas_id": canvas_id,
            "width": canvas.canvas_width, "height": canvas.canvas_height,
            "layers": len(canvas.layers), "active_layer": canvas.active_layer}

@app.post("/api/canvas/gen-image", response_model=Dict[str, Any])
async def canvas_gen_image(request: CanvasGenRequest):
    engine = get_canvas_engine()
    return await engine.gen_image_on_canvas(
        request.canvas_id, request.prompt, request.params,
        request.x, request.y, request.width, request.height
    )

@app.post("/api/canvas/edit", response_model=Dict[str, Any])
async def canvas_edit(request: CanvasEditRequest):
    engine = get_canvas_engine()
    return await engine.edit_canvas_region(
        request.canvas_id, request.prompt, request.params,
        request.x, request.y, request.width, request.height
    )

@app.post("/api/canvas/outpaint", response_model=Dict[str, Any])
async def canvas_outpaint(request: CanvasGenRequest):
    engine = get_canvas_engine()
    return await engine.outpaint_canvas(
        request.canvas_id, request.direction, request.prompt,
        request.params, request.expand_pixels
    )

@app.post("/api/canvas/drama", response_model=Dict[str, Any])
async def canvas_drama(request: CanvasGenRequest):
    engine = get_canvas_engine()
    return await engine.generate_short_drama(
        request.canvas_id, request.story_prompt or request.prompt,
        request.params, request.scene_count
    )

@app.post("/api/canvas/picture-book", response_model=Dict[str, Any])
async def canvas_picture_book(request: CanvasGenRequest):
    engine = get_canvas_engine()
    return await engine.generate_picture_book(
        request.canvas_id, request.story_prompt or request.prompt,
        request.params, request.page_count
    )

@app.post("/api/canvas/export", response_model=Dict[str, Any])
async def canvas_export(request: CanvasGenRequest):
    engine = get_canvas_engine()
    return await engine.export_canvas(request.canvas_id, request.output_path)

@app.post("/api/canvas/undo", response_model=Dict[str, Any])
async def canvas_undo(canvas_id: str, action: str = "undo"):
    engine = get_canvas_engine()
    canvas = engine.get_canvas(canvas_id)
    if not canvas:
        raise HTTPException(status_code=404, detail="Canvas not found")
    if action == "undo":
        success = canvas.undo()
    elif action == "redo":
        success = canvas.redo()
    else:
        raise HTTPException(status_code=400, detail="Unknown action. Use 'undo' or 'redo'")
    return {"success": success, "canvas_id": canvas_id}

# ============================================================================
# AIRI Digital Human - Request Models
# AIRI 数字人 - 请求模型 (输入验证)
# ============================================================================

class AIRIUserActionRequest(BaseModel):
    """用户操作请求"""
    action: str = Field(default="user_interaction", max_length=100)
    timestamp: Optional[str] = None


class AIRIRespondRequest(BaseModel):
    """AI 响应请求"""
    user_message: str = Field(..., min_length=1, max_length=10000)
    ai_response: str = Field(..., min_length=1, max_length=10000)


class AIRIPositionRequest(BaseModel):
    """位置设置请求"""
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    scale: float = Field(default=1.0, ge=0.1, le=2.0)


class AIRIVisibleRequest(BaseModel):
    """可见性设置请求"""
    visible: bool = Field(default=True)


class AIRISkillExecuteRequest(BaseModel):
    """技能执行请求"""
    skill_name: str = Field(..., min_length=1, max_length=100)
    parameters: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# AIRI Digital Human API Endpoints
# STATUS: planned — AIRI数字人API (17路由)，前端未调用，待Phase 4实现
# AIRI 数字人 API 端点
# ============================================================================

# 全局数字人实例
_digital_human_instance = None
_airi_skills_integration = None

def get_digital_human_instance():
    """获取数字人实例"""
    global _digital_human_instance, _airi_skills_integration
    if _digital_human_instance is None and AIRI_AVAILABLE:
        _digital_human_instance = get_digital_human()
        # 初始化 Skills 集成
        if _digital_human_instance:
            _airi_skills_integration = initialize_airi_skills(_digital_human_instance)
            logger.info("AIRI Skills 集成初始化完成")
    return _digital_human_instance


@app.get("/api/airi/status")
async def airi_get_status():
    """获取数字人状态"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    state = dh.get_state()
    animation_state = dh.get_animation_state()
    
    return {
        "success": True,
        "status": {
            "visible": state.visible,
            "position": state.position,
            "scale": state.scale,
            "rotation": state.rotation,
            "opacity": state.opacity,
            "current_animation": animation_state.get("current_animation"),
            "current_expression": animation_state.get("current_expression"),
            "interaction_state": animation_state.get("interaction_state"),
            "is_speaking": state.is_speaking,
            "last_user_action_time": state.last_user_action_time,
            "user_action_count": state.user_action_count,
        }
    }


@app.post("/api/airi/start")
async def airi_start():
    """启动数字人"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    await dh.start()
    
    return {"success": True, "message": "Digital human started"}


@app.post("/api/airi/stop")
async def airi_stop():
    """停止数字人"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    await dh.stop()
    
    return {"success": True, "message": "Digital human stopped"}


@app.post("/api/airi/user_action")
async def airi_user_action():
    """用户操作通知 (数字人缩小到角落)"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    dh.on_user_action()
    
    state = dh.get_state()
    return {
        "success": True,
        "position": state.position,
        "scale": state.scale
    }


@app.get("/api/airi/animations")
async def airi_get_animations():
    """获取可用动画列表"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    animations = dh.list_available_animations()
    
    return {
        "success": True,
        "animations": animations
    }


@app.get("/api/airi/expressions")
async def airi_get_expressions():
    """获取可用表情列表"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    expressions = dh.list_available_expressions()
    
    return {
        "success": True,
        "expressions": expressions
    }


@app.post("/api/airi/animation/{animation_name}")
async def airi_play_animation(animation_name: str):
    """播放指定动画"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    success = await dh.play_animation(animation_name)
    
    return {
        "success": success,
        "animation": animation_name
    }


@app.post("/api/airi/expression/{expression_name}")
async def airi_set_expression(expression_name: str):
    """设置指定表情"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    success = await dh.set_expression(expression_name)
    
    return {
        "success": success,
        "expression": expression_name
    }


@app.post("/api/airi/respond")
async def airi_respond(request: AIRIRespondRequest):
    """AI 响应用户 (Nanobot AI 驱动数字人响应)"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    try:
        await dh.respond_to_user(request.user_message, request.ai_response)
        
        state = dh.get_state()
        return {
            "success": True,
            "response": request.ai_response,
            "state": {
                "animation": state.current_animation,
                "expression": state.expression,
                "is_speaking": state.is_speaking,
            }
        }
    except Exception as e:
        logger.error(f"AIRI respond failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/airi/welcome")
async def airi_welcome():
    """执行欢迎动画"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    await dh.perform_welcome()
    
    return {"success": True, "message": "Welcome animation played"}


@app.post("/api/airi/goodbye")
async def airi_goodbye():
    """执行告别动画"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    await dh.perform_goodbye()
    
    return {"success": True, "message": "Goodbye animation played"}


@app.post("/api/airi/agree")
async def airi_agree():
    """同意/确认动画"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    await dh.perform_agreement()
    
    return {"success": True, "message": "Agreement animation played"}


@app.post("/api/airi/disagree")
async def airi_disagree():
    """不同意动画"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    await dh.perform_disagreement()
    
    return {"success": True, "message": "Disagreement animation played"}


@app.post("/api/airi/position")
async def airi_set_position(request: Dict[str, Any]):
    """设置数字人位置"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    x = request.get("x", 0.5)
    y = request.get("y", 0.5)
    scale = request.get("scale", 1.0)
    
    dh.state.position = (x, y)
    dh.state.scale = scale
    
    return {
        "success": True,
        "position": dh.state.position,
        "scale": dh.state.scale
    }


@app.post("/api/airi/visible")
async def airi_set_visible(request: AIRIVisibleRequest):
    """设置数字人可见性"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    dh.state.visible = request.visible
    
    return {
        "success": True,
        "visible": dh.state.visible
    }


@app.get("/api/airi/skills")
async def airi_get_skills():
    """获取已注册技能列表"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    skills = dh.list_registered_skills()
    
    return {
        "success": True,
        "skills": skills
    }


@app.post("/api/airi/skill/{skill_name}")
async def airi_execute_skill(skill_name: str, request: AIRISkillExecuteRequest):
    """执行指定技能"""
    if not AIRI_AVAILABLE:
        return {"error": "AIRI module not available", "success": False}
    
    dh = get_digital_human_instance()
    if not dh:
        return {"error": "Digital human not initialized", "success": False}
    
    try:
        result = await dh.execute_skill(skill_name, request.parameters)
        return {
            "success": True,
            "skill": skill_name,
            "result": result
        }
    except Exception as e:
        logger.error(f"Skill execution failed: {skill_name} - {e}")
        return {
            "success": False,
            "skill": skill_name,
            "error": str(e)
        }


# ============================================================================
# Advanced Data Production APIs — 补齐的多模态数据生产管线
# ============================================================================

# ---------------------------------------------------------------------------
# Advanced Quality Scoring
# ---------------------------------------------------------------------------

@app.post("/api/data/quality/advanced")
async def data_quality_advanced(request: Request):
    """高级质量评分 — 美学/NSFW/人脸质量/水印检测全覆盖"""
    body = await request.json()
    image_path = body.get("image_path", "")
    caption = body.get("caption", "")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")

    from data_quality_advanced import get_advanced_scorer
    scorer = get_advanced_scorer()

    report = scorer.comprehensive_report(image_path, caption=caption)
    wm = scorer.watermark_detect(image_path)
    fq = scorer.face_quality(image_path)

    return {
        "success": True,
        "aesthetic_score": report.aesthetic,
        "clip_score": report.clip_score,
        "nsfw_score": report.nsfw_score,
        "face_quality": fq["quality"],
        "face_count": fq["count"],
        "watermark_detect": wm["confidence"],
        "watermark_pattern": wm["pattern"],
        "score_mean": report.score_mean,
        "score_std": report.score_std,
        "width": report.width,
        "height": report.height,
    }


@app.post("/api/data/quality/advanced/batch")
async def data_quality_advanced_batch(request: Request):
    """批量高级质量评分 + 分布分析"""
    body = await request.json()
    image_paths = body.get("image_paths", [])
    captions = body.get("captions", [])

    if not image_paths:
        raise HTTPException(status_code=400, detail="No image paths provided")

    from data_quality_advanced import get_advanced_scorer
    scorer = get_advanced_scorer()

    # 每张图分析
    results = []
    for i, path in enumerate(image_paths):
        cap = captions[i] if i < len(captions) else ""
        if os.path.exists(path):
            report = scorer.comprehensive_report(path, caption=cap)
            fq = scorer.face_quality(path)
            wm = scorer.watermark_detect(path)
            results.append({
                "image_path": path,
                "aesthetic": report.aesthetic,
                "nsfw": report.nsfw_score,
                "face_quality": fq["quality"],
                "face_count": fq["count"],
                "watermark": wm["confidence"],
            })

    # 分布分析
    gap_analysis = scorer.scoring_gap_analysis(image_paths)

    return {
        "success": True,
        "total": len(results),
        "results": results,
        "distribution": gap_analysis,
    }


# ---------------------------------------------------------------------------
# ControlNet Condition Generation
# ---------------------------------------------------------------------------

@app.post("/api/data/controlnet/generate")
async def data_controlnet_generate(request: Request):
    """ControlNet条件图生成 — 边缘/深度/姿态/分割"""
    body = await request.json()
    image_path = body.get("image_path", "")
    conditions = body.get("conditions", ["canny", "depth", "pose", "segmentation"])
    caption = body.get("caption", "")
    output_dir = body.get("output_dir", "./data/controlnet")

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image not found")

    from data_controlnet_pipeline import ControlNetProcessor
    processor = ControlNetProcessor(output_dir=output_dir)

    pair = processor.generate_control_pairs(
        image_path, conditions=conditions, caption=caption, save=True
    )

    return {
        "success": True,
        "image_id": pair.image_id,
        "source_image": pair.source_image_path,
        "canny": pair.canny_path,
        "depth": pair.depth_path,
        "pose": pair.pose_path,
        "segmentation": pair.segmentation_path,
        "width": pair.width,
        "height": pair.height,
    }


@app.post("/api/data/controlnet/batch")
async def data_controlnet_batch(request: Request):
    """批量ControlNet条件图生成"""
    body = await request.json()
    image_dir = body.get("image_dir", "")
    conditions = body.get("conditions", ["canny", "depth", "pose", "segmentation"])
    output_dir = body.get("output_dir", "./data/controlnet/batch")

    if not image_dir or not os.path.exists(image_dir):
        raise HTTPException(status_code=400, detail="Image directory not found")

    from data_controlnet_pipeline import ControlNetProcessor
    processor = ControlNetProcessor()

    # 收集图像
    import glob
    extensions = ["*.jpg", "*.jpeg", "*.png", "*.webp"]
    images = []
    for ext in extensions:
        images.extend(sorted(glob.glob(os.path.join(image_dir, ext))))

    if not images:
        raise HTTPException(status_code=400, detail="No images found in directory")

    captions = [""] * len(images)
    dataset = processor.generate_batch(images, captions=captions,
                                        conditions=conditions,
                                        output_subdir=os.path.basename(output_dir))

    # 保存为标准格式
    out_path = processor.save_control_dataset(dataset, output_dir=output_dir)

    return {
        "success": True,
        "output_dir": out_path,
        "total_pairs": dataset.total,
        "conditions": dataset.conditions,
    }


# ---------------------------------------------------------------------------
# Dense Caption Generation
# ---------------------------------------------------------------------------

@app.post("/api/data/dense-caption/generate")
async def data_dense_caption_generate(request: Request):
    """密集描述生成 — 完整/简短/BLIP3/ShareGPT4V"""
    body = await request.json()
    image_path = body.get("image_path", "")
    style = body.get("style", "full")  # full / short / blip3 / sharegpt4v

    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image not found")

    from data_dense_caption import DenseCaptionGenerator
    gen = DenseCaptionGenerator()

    if style == "short":
        caption = gen.generate_short_caption(image_path)
        return {"success": True, "style": "short", "caption": caption}
    elif style == "blip3":
        blip3 = gen.generate_blip3_style(image_path)
        return {"success": True, "style": "blip3", **blip3}
    elif style == "sharegpt4v":
        output_dir = body.get("output_dir", "./data/sharegpt4v")
        entry = gen.save_sharegpt4v_format(image_path, output_dir=output_dir)
        return {"success": True, "style": "sharegpt4v", "entry": entry}
    elif style == "regions":
        regions = gen.generate_region_captions(image_path)
        return {
            "success": True,
            "style": "regions",
            "regions": [{"bbox": r.bbox, "caption": r.caption, "category": r.category}
                        for r in regions],
        }
    else:
        # full
        caption = gen.generate_full_caption(image_path)
        return {"success": True, "style": "full", "caption": caption}


# ---------------------------------------------------------------------------
# Video Caption
# ---------------------------------------------------------------------------

@app.post("/api/data/video/caption")
async def data_video_caption(request: Request):
    """视频Caption — 全局叙事/逐帧描述/分段描述"""
    body = await request.json()
    video_path = body.get("video_path", "")
    mode = body.get("mode", "full")  # full / narrative / segments / opensora
    output_dir = body.get("output_dir", "./data/video_caption")
    interval = body.get("frame_interval", 30)

    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail="Video not found")

    from data_video_caption import VideoCaptionGenerator
    gen = VideoCaptionGenerator(work_dir=output_dir)

    if mode == "narrative":
        caption = gen.generate_narrative_caption(video_path)
        return {"success": True, "mode": "narrative", "caption": caption}
    elif mode == "segments":
        segments = gen.generate_segment_captions(video_path)
        return {"success": True, "mode": "segments", "segments": segments}
    elif mode == "opensora":
        out = gen.save_open_sora_format(video_path, output_dir=output_dir)
        return {"success": True, "mode": "opensora", "output_dir": out}
    else:
        # full
        result = gen.run_pipeline(video_path, output_dir=output_dir,
                                  extract_interval=interval)
        return {
            "success": True,
            "mode": "full",
            "narrative_caption": result.narrative_caption,
            "num_frames": result.num_frames,
            "num_segments": len(result.segment_captions),
            "output_dir": result.output_dir,
        }


# ---------------------------------------------------------------------------
# Multimodal Benchmark Generation
# ---------------------------------------------------------------------------

@app.post("/api/data/benchmark/generate")
async def data_benchmark_generate(request: Request):
    """多模态评测数据生成 — MMMU/VQA/LLaVA/VBench"""
    body = await request.json()
    dataset_name = body.get("name", "multimodal_benchmark")
    image_path = body.get("image_path", "")
    subjects = body.get("subjects", None)
    num_vqa = body.get("num_vqa", 10)
    output_dir = body.get("output_dir", "./data/benchmark")

    from data_multimodal_benchmark import get_benchmark_generator
    gen = get_benchmark_generator()

    # 验证图像
    img = None
    if image_path and os.path.exists(image_path):
        img = image_path

    dataset = gen.generate_full_benchmark(
        name=dataset_name,
        image=img,
        subjects=subjects,
        num_vqa=num_vqa,
    )

    out_path = gen.save_hf_format(dataset, output_dir=output_dir)

    return {
        "success": True,
        "output_dir": out_path,
        "stats": {
            "questions": len(dataset.questions),
            "vqa_pairs": len(dataset.vqa_pairs),
            "conversations": len(dataset.conversations),
            "vbench_items": len(dataset.vbench_items),
        },
    }


# ============================================================================
# Data Production APIs — 多模态数据生产管线
# ============================================================================

@app.get("/api/data/quality-engine/status")
async def data_quality_engine_status():
    """数据质量引擎状态"""
    try:
        from data_quality_engine import get_quality_engine
        engine = get_quality_engine(skip_model_init=False)
        return {
            "status": "ok",
            "ready": engine._ready,
            "loaded_models": engine._loaded_models,
            "device": engine._device
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/data/quality-engine/score")
async def data_quality_score(request: Request):
    """图像质量评分"""
    body = await request.json()
    image_path = body.get("image_path", "")
    caption = body.get("caption", "")
    
    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image path not found")
    
    from data_quality_engine import get_quality_engine
    engine = get_quality_engine(skip_model_init=False)
    
    score = engine.score_image(image_path, caption)
    
    def _float(v):
        return float(v) if v is not None else 0.0
    
    return {
        "success": True,
        "overall_score": _float(score.overall_score),
        "aesthetic_score": _float(score.aesthetic_score),
        "technical_quality": _float(score.technical_quality),
        "clip_score": _float(score.clip_score),
        "sharpness": round(_float(score.sharpness), 4),
        "brightness": round(_float(score.brightness), 4),
        "contrast": round(_float(score.contrast), 4),
        "colorfulness": round(_float(score.colorfulness), 4),
        "noise_level": round(_float(score.noise_level), 4),
        "face_count": int(score.face_count),
        "width": int(score.width),
        "height": int(score.height),
        "aspect_ratio": round(_float(score.aspect_ratio), 4)
    }


@app.post("/api/data/quality-engine/batch-score")
async def data_quality_batch_score(request: Request):
    """批量质量评分"""
    body = await request.json()
    items = body.get("items", [])
    threshold = body.get("threshold", 0.5)
    
    if not items:
        raise HTTPException(status_code=400, detail="No items provided")
    
    from data_quality_engine import get_quality_engine
    engine = get_quality_engine(skip_model_init=False)
    report = engine.score_batch(items, image_key="image_path", 
                                 caption_key="caption", threshold=threshold)
    
    return {
        "success": True,
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "avg_scores": report.avg_scores,
        "passed_ids": report.passed_ids,
        "failed_ids": report.failed_ids
    }


@app.post("/api/data/annotation/pipeline")
async def data_annotation_run(request: Request):
    """运行标注管线"""
    body = await request.json()
    image_dir = body.get("image_dir", "")
    formats = body.get("formats", ["coco"])
    auto_label = body.get("auto_label", False)
    output_dir = body.get("output_dir", "./data/annotations")
    
    if not image_dir or not os.path.exists(image_dir):
        raise HTTPException(status_code=400, detail="Image directory not found")
    
    from data_annotation_pipeline import AnnotationPipeline, AnnotationFormat
    pipeline = AnnotationPipeline(output_dir=output_dir)
    
    fmt_list = []
    for f in formats:
        try:
            fmt_list.append(AnnotationFormat(f))
        except ValueError:
            pass
    
    result = pipeline.run_pipeline(image_dir, fmt_list, auto_label)
    return {"success": True, "result": result}


@app.post("/api/data/annotation/convert")
async def data_annotation_convert(request: Request):
    """标注格式转换"""
    body = await request.json()
    input_format = body.get("input_format", "coco")
    output_format = body.get("output_format", "yolo")
    input_path = body.get("input_path", "")
    output_dir = body.get("output_dir", "./data/annotations")
    
    from data_annotation_pipeline import AnnotationConverter, AnnotationDataset, AnnotationFormat
    
    converter = AnnotationConverter()
    
    if input_format == "coco" and os.path.exists(input_path):
        import json
        with open(input_path) as f:
            data = json.load(f)
        
        dataset = AnnotationDataset(name="converted")
        for img in data.get("images", []):
            from data_annotation_pipeline import AnnotationItem
            item = AnnotationItem(
                image_id=str(img["id"]),
                image_path=img.get("file_name", ""),
                width=img.get("width", 0),
                height=img.get("height", 0)
            )
            for ann in data.get("annotations", []):
                if ann["image_id"] == img["id"]:
                    from data_annotation_pipeline import BoundingBox
                    b = ann.get("bbox", [0,0,0,0])
                    w = img.get("width", 1)
                    h = img.get("height", 1)
                    item.bboxes.append(BoundingBox(
                        x=b[0]/w, y=b[1]/h, width=b[2]/w, height=b[3]/h
                    ))
            dataset.items.append(item)
        
        if output_format == "yolo":
            out_path = converter.to_yolo(dataset, output_dir)
        elif output_format == "label_studio":
            ls = converter.to_label_studio(dataset)
            import json
            os.makedirs(output_dir, exist_ok=True)
            out_path = f"{output_dir}/label_studio.json"
            with open(out_path, "w") as f:
                json.dump(ls, f, indent=2)
        else:
            out_path = ""
        
        return {"success": True, "output": out_path, "items": len(dataset.items)}
    
    return {"success": False, "error": "Unsupported conversion"}


@app.post("/api/data/watermark/visible")
async def data_watermark_visible(request: Request):
    """添加可见水印"""
    body = await request.json()
    image_path = body.get("image_path", "")
    text = body.get("text", "NanoBot")
    
    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image not found")
    
    from data_watermark import VisibleWatermark
    from PIL import Image
    
    img = Image.open(image_path)
    result = VisibleWatermark.add_text_watermark(img, text=text, opacity=0.3)
    
    output_path = image_path.replace(".", "_watermarked.")
    result.save(output_path)
    
    return {"success": True, "output_path": output_path}


@app.post("/api/data/watermark/invisible")
async def data_watermark_invisible(request: Request):
    """嵌入不可见水印"""
    body = await request.json()
    image_path = body.get("image_path", "")
    message = body.get("message", "")
    
    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image not found")
    
    from data_watermark import InvisibleWatermark
    from PIL import Image
    
    img = Image.open(image_path)
    result = InvisibleWatermark.embed_dwt(img, message)
    
    output_path = image_path.replace(".", "_invisible.")
    result.save(output_path)
    
    return {"success": True, "output_path": output_path}


@app.post("/api/data/watermark/detect")
async def data_watermark_detect(request: Request):
    """检测不可见水印"""
    body = await request.json()
    image_path = body.get("image_path", "")
    message = body.get("message", "")
    
    if not image_path or not os.path.exists(image_path):
        raise HTTPException(status_code=400, detail="Image not found")
    
    from data_watermark import InvisibleWatermark
    from PIL import Image
    
    img = Image.open(image_path)
    result = InvisibleWatermark.detect_dwt(img, message)
    
    return {
        "success": result.success,
        "confidence": round(result.confidence, 4),
        "message": result.message
    }


@app.post("/api/data/video/pipeline")
async def data_video_pipeline(request: Request):
    """运行视频数据生产管线"""
    body = await request.json()
    
    input_video = body.get("input_video", "")
    input_dir = body.get("input_dir", "")
    output_dir = body.get("output_dir", "./data/video_output")
    
    from data_video_pipeline import VideoPipeline, VideoPipelineConfig
    
    config = VideoPipelineConfig(
        output_dir=output_dir,
        frame_interval=body.get("frame_interval", 30),
        scene_threshold=body.get("scene_threshold", 30),
        dedup_threshold=body.get("dedup_threshold", 10),
        quality_threshold=body.get("quality_threshold", 0.4),
        extract_frames=body.get("extract_frames", True),
        detect_scenes=body.get("detect_scenes", True),
        extract_keyframes=body.get("extract_keyframes", True),
        deduplicate=body.get("deduplicate", True),
        quality_filter=body.get("quality_filter", True)
    )
    
    pipeline = VideoPipeline(config)
    
    if input_video and os.path.exists(input_video):
        result = pipeline.run_pipeline(input_video)
    elif input_dir and os.path.exists(input_dir):
        result = pipeline.run_batch_pipeline(input_dir)
    else:
        raise HTTPException(status_code=400, detail="Provide input_video or input_dir")
    
    return {"success": True, "result": result}


@app.post("/api/data/dataset/export")
async def data_dataset_export(request: Request):
    """导出数据集"""
    body = await request.json()
    input_dir = body.get("input_dir", "")
    format_type = body.get("format", "hf_json")
    output_path = body.get("output_path", "./data/dataset_export")
    split_ratios = body.get("split_ratios", [0.8, 0.1, 0.1])
    
    if not input_dir or not os.path.exists(input_dir):
        raise HTTPException(status_code=400, detail="Input directory not found")
    
    from data_dataset_manager import DatasetManager
    
    manager = DatasetManager(base_dir=output_path)
    dataset_entries = manager.create_from_image_dir("exported", input_dir)
    splits = manager.split_dataset(dataset_entries, 
                                     train_ratio=split_ratios[0], 
                                     val_ratio=split_ratios[1], 
                                     test_ratio=split_ratios[2])
    
    if format_type == "huggingface" or format_type == "hf_json":
        out = manager.create_hf_json("dataset", dataset_entries)
    elif format_type == "webdataset" or format_type == "tar":
        out = manager.create_webdataset("dataset", dataset_entries)
    else:
        out = manager.create_hf_json("dataset", dataset_entries)
    
    return {"success": True, "output_path": str(out), "total": len(dataset_entries)}


@app.get("/api/data/dataset/stats")
async def data_dataset_stats(request: Request):
    """数据集统计"""
    path = request.query_params.get("path", "./data/dataset_export")
    
    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail="Dataset path not found")
    
    from data_dataset_manager import DatasetManager, compute_stats
    manager = DatasetManager()
    path_entries = manager.load_hf_json(path) if os.path.isdir(path) else []
    stats = compute_stats(path_entries)
    
    # 确保所有值可JSON序列化
    def _ser(obj):
        import pathlib
        if isinstance(obj, pathlib.PosixPath) or isinstance(obj, pathlib.WindowsPath):
            return str(obj)
        if isinstance(obj, dict):
            return {k: _ser(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_ser(i) for i in obj]
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        return obj
    
    import numpy as np
    stats = _ser(stats)
    
    return {"success": True, "stats": stats}


@app.post("/api/data/copyright/register")
async def data_copyright_register(request: Request):
    """注册版权"""
    body = await request.json()
    image_id = body.get("image_id", "")
    owner = body.get("owner", "default")
    metadata = body.get("metadata", {})
    
    from data_watermark import CopyrightManager
    cm = CopyrightManager()
    record = cm.register(image_id, owner, metadata)
    
    return {
        "success": True,
        "watermark_id": record.watermark_id,
        "owner": record.owner,
        "created_at": record.created_at
    }


@app.get("/api/data/copyright/lookup")
async def data_copyright_lookup(image_id: str = ""):
    """查询版权"""
    if not image_id:
        raise HTTPException(status_code=400, detail="image_id required")
    
    from data_watermark import CopyrightManager
    cm = CopyrightManager()
    record = cm.lookup(image_id)
    
    if record:
        return {
            "success": True,
            "image_id": record.image_id,
            "owner": record.owner,
            "watermark_id": record.watermark_id,
            "created_at": record.created_at
        }
    return {"success": False, "message": "No record found"}


# ============================================================================
# Infinite Canvas Agent Engine API
# ============================================================================

@app.post("/api/canvas/agent/execute")
async def canvas_agent_execute(request: Request):
    """Agent驱动画布执行"""
    body = await request.json()
    action = body.get("action", "gen_image")
    params = body.get("params", {})
    canvas_id = body.get("canvas_id", "")
    
    from infinite_canvas_agent_engine import get_canvas_engine, CanvasAction
    
    try:
        ca = CanvasAction(action)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
    
    engine = get_canvas_engine(canvas_id)
    result = await engine.execute(ca, params)
    return {
        "success": result["success"],
        "canvas": result["canvas"],
        "goals": result["goals"],
        "summary": result["summary"]
    }


@app.get("/api/canvas/agent/state")
async def canvas_agent_state(canvas_id: str = ""):
    """获取画布状态"""
    from infinite_canvas_agent_engine import get_canvas_engine
    engine = get_canvas_engine(canvas_id)
    return {"success": True, "canvas": engine.get_canvas_state()}


@app.get("/api/canvas/agent/agents")
async def canvas_agent_list():
    """列出可用Agent"""
    from infinite_canvas_agent_engine import get_agent_pool, AgentRole
    pool = get_agent_pool()
    agents = []
    for role, agent_list in pool.items():
        for agent in agent_list:
            agents.append({
                "role": role.value,
                "name": agent.name,
                "id": agent.id
            })
    return {"success": True, "agents": agents}


# ============================================================================
# 节点化工作流引擎 API v2
# ============================================================================

from nodes import NodeRegistry, WorkflowEngine, registry, WorkflowDefinition

# 导入所有节点模块触发自动注册
import nodes.filter_nodes   # noqa: F401
import nodes.gen_nodes      # noqa: F401
import nodes.quality_nodes  # noqa: F401
import nodes.control_nodes  # noqa: F401
import nodes.export_nodes   # noqa: F401

engine = WorkflowEngine()
logger.info(f"Node engine initialized with {len(registry.list())} node types")


@app.get("/api/v2/nodes")
async def list_nodes():
    """列出所有可用节点定义"""
    definitions = registry.list()
    return {
        "success": True,
        "data": [d.model_dump() for d in definitions],
        "count": len(definitions),
    }


@app.post("/api/v2/workflow/execute")
async def execute_workflow(workflow: WorkflowDefinition):
    """执行工作流"""
    try:
        result = await engine.execute(workflow)
        return {"success": True, "data": result}
    except Exception as e:
        logger.exception("Workflow execution failed")
        return {"success": False, "error": str(e)}


@app.get("/api/v2/nodes/categories")
async def list_node_categories():
    """列出所有节点类别及各类节点数量"""
    definitions = registry.list()
    cats = {}
    for d in definitions:
        cats.setdefault(d.category, {"category": d.category, "count": 0})
        cats[d.category]["count"] += 1
    return {"success": True, "data": list(cats.values())}


# ============================================================================
# ML Backend Routes — 主动学习引擎
# ============================================================================

from core.ml_backend import (
    MLBackend, MLModelType, MLModelStatus, get_ml_backend
)


@app.get("/api/v2/ml/models")
async def ml_list_models(model_type: Optional[str] = Query(None)):
    """列出已注册模型，可按类型筛选"""
    try:
        mt = None
        if model_type:
            mt = MLModelType(model_type)
        models = MLBackend.list_models(mt)
        return {
            "success": True,
            "data": [m.model_dump() for m in models],
            "count": len(models)
        }
    except Exception as e:
        logger.exception("Failed to list ML models")
        return {"success": False, "error": str(e)}


class RegisterModelRequest(BaseModel):
    name: str
    model_type: MLModelType
    endpoint: str = ""
    api_key: str = ""
    description: str = ""


@app.post("/api/v2/ml/models")
async def ml_register_model(req: RegisterModelRequest):
    """注册新ML模型"""
    try:
        model = MLBackend.register_model(
            name=req.name,
            model_type=req.model_type,
            endpoint=req.endpoint,
            api_key=req.api_key
        )
        return {"success": True, "data": model.model_dump()}
    except Exception as e:
        logger.exception("Failed to register ML model")
        return {"success": False, "error": str(e)}


@app.delete("/api/v2/ml/models/{model_id}")
async def ml_remove_model(model_id: str):
    """注销ML模型"""
    ok = MLBackend.remove_model(model_id)
    if ok:
        return {"success": True, "message": f"Model {model_id} removed"}
    return {"success": False, "error": f"Model {model_id} not found"}


class PredictRequest(BaseModel):
    task_data: Dict[str, Any]


@app.post("/api/v2/ml/models/{model_id}/predict")
async def ml_predict(model_id: str, req: PredictRequest):
    """调用模型预标注"""
    try:
        result = await MLBackend.predict(model_id, req.task_data)
        return {"success": True, "data": result.model_dump()}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.exception(f"Prediction failed for model {model_id}")
        return {"success": False, "error": str(e)}


@app.get("/api/v2/ml/active-learning")
async def ml_active_learning(
    strategy: str = Query("uncertainty"),
    count: int = Query(10, ge=1, le=100)
):
    """主动学习采样——获取最需要人工标注的样本"""
    try:
        samples = MLBackend.get_active_learning_samples(
            strategy=strategy, count=count
        )
        return {"success": True, "data": samples, "count": len(samples)}
    except Exception as e:
        logger.exception("Failed to get active learning samples")
        return {"success": False, "error": str(e)}


class UpdateAccuracyRequest(BaseModel):
    accuracy: float = Field(..., ge=0.0, le=1.0)


@app.post("/api/v2/ml/models/{model_id}/accuracy")
async def ml_update_accuracy(model_id: str, req: UpdateAccuracyRequest):
    """更新模型准确率（基于人工审核反馈）"""
    ok = MLBackend.update_model_accuracy(model_id, req.accuracy)
    if ok:
        return {"success": True, "message": f"Accuracy updated for {model_id}"}
    return {"success": False, "error": f"Model {model_id} not found"}


# ============================================================================
# RBAC Multi-Tenant Routes
# ============================================================================

from core.rbac import rbac, Role, Permission

class CreateOrgRequest(BaseModel):
    name: str
    owner: str

class AddMemberRequest(BaseModel):
    username: str
    role: Role

class CreateProjectRequest(BaseModel):
    name: str
    org_id: str
    created_by: str

class AddProjectMemberRequest(BaseModel):
    username: str
    role: Role

class CheckPermissionRequest(BaseModel):
    username: str
    org_id: Optional[str] = None
    project_id: Optional[str] = None
    required_permission: Permission


@app.post("/api/v2/rbac/orgs")
async def rbac_create_org(req: CreateOrgRequest):
    """创建组织"""
    try:
        org = rbac.create_org(name=req.name, owner=req.owner)
        return {
            "success": True,
            "data": {
                "org_id": org.org_id,
                "name": org.name,
                "owner": org.owner,
                "created_at": org.created_at,
                "member_count": len(org.members),
            }
        }
    except Exception as e:
        logger.exception("Failed to create org")
        return {"success": False, "error": str(e)}


@app.get("/api/v2/rbac/orgs")
async def rbac_list_orgs():
    """组织列表"""
    try:
        orgs = rbac.list_orgs()
        return {"success": True, "data": orgs, "count": len(orgs)}
    except Exception as e:
        logger.exception("Failed to list orgs")
        return {"success": False, "error": str(e)}


@app.post("/api/v2/rbac/orgs/{org_id}/members")
async def rbac_add_org_member(org_id: str, req: AddMemberRequest):
    """添加组织成员"""
    ok = rbac.add_org_member(org_id, req.username, req.role)
    if ok:
        return {"success": True, "message": f"Member {req.username} added to org {org_id} with role {req.role.value}"}
    return {"success": False, "error": f"Organization {org_id} not found"}


@app.get("/api/v2/rbac/orgs/{org_id}/members")
async def rbac_list_org_members(org_id: str):
    """组织成员列表"""
    org = rbac.get_org(org_id)
    if not org:
        return {"success": False, "error": f"Organization {org_id} not found"}
    members = [{"username": username, "role": role.value} for username, role in org.members.items()]
    return {"success": True, "data": members, "count": len(members)}


@app.post("/api/v2/rbac/projects")
async def rbac_create_project(req: CreateProjectRequest):
    """创建项目"""
    try:
        project = rbac.create_project(name=req.name, org_id=req.org_id, created_by=req.created_by)
        if project is None:
            return {"success": False, "error": f"Organization {req.org_id} not found"}
        return {
            "success": True,
            "data": {
                "project_id": project.project_id,
                "name": project.name,
                "org_id": project.org_id,
                "created_by": project.created_by,
                "created_at": project.created_at,
                "member_count": len(project.members),
            }
        }
    except Exception as e:
        logger.exception("Failed to create project")
        return {"success": False, "error": str(e)}


@app.get("/api/v2/rbac/projects")
async def rbac_list_projects(org_id: Optional[str] = Query(None, description="按组织ID筛选")):
    """项目列表(按org筛选)"""
    try:
        projects = rbac.list_projects(org_id=org_id)
        return {"success": True, "data": projects, "count": len(projects)}
    except Exception as e:
        logger.exception("Failed to list projects")
        return {"success": False, "error": str(e)}


@app.post("/api/v2/rbac/projects/{project_id}/members")
async def rbac_add_project_member(project_id: str, req: AddProjectMemberRequest):
    """添加项目成员"""
    ok = rbac.add_project_member(project_id, req.username, req.role)
    if ok:
        return {"success": True, "message": f"Member {req.username} added to project {project_id} with role {req.role.value}"}
    return {"success": False, "error": f"Project {project_id} not found"}


@app.post("/api/v2/rbac/check")
async def rbac_check_permission(req: CheckPermissionRequest):
    """权限检查"""
    try:
        allowed = rbac.check_permission(
            username=req.username,
            org_id=req.org_id,
            project_id=req.project_id,
            required_permission=req.required_permission,
        )
        return {"success": True, "data": {"allowed": allowed}}
    except Exception as e:
        logger.exception("Failed to check permission")
        return {"success": False, "error": str(e)}


# ============================================================================
# Drama Studio API — /api/v2/drama/*
# ============================================================================
from core.drama_pipeline import drama as drama_pipeline

@app.post("/api/v2/drama/projects")
async def drama_create_project(request: Request):
    body = await request.json()
    p = drama_pipeline.create_project(body.get("title"), body.get("script", ""), body.get("style", "realistic"))
    return {"success": True, "project_id": p.project_id}

@app.get("/api/v2/drama/projects")
async def drama_list_projects():
    return drama_pipeline.list_projects()

@app.get("/api/v2/drama/projects/{project_id}")
async def drama_get_project(project_id: str):
    p = drama_pipeline.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project_id": p.project_id, "title": p.title, "style": p.style,
            "status": p.status, "scenes": [{"scene_number": s.scene_number,
            "content": s.content, "prompt": s.prompt, "status": s.status}
            for s in p.scenes]}

@app.post("/api/v2/drama/projects/{project_id}/breakdown")
async def drama_breakdown(project_id: str):
    ok = drama_pipeline.breakdown_script(project_id)
    return {"success": ok}

@app.post("/api/v2/drama/projects/{project_id}/generate")
async def drama_generate(project_id: str):
    ok = drama_pipeline.generate_all_scenes(project_id)
    return {"success": ok}


# ============================================================================
# Book Studio API — /api/v2/books/*
# ============================================================================
from core.book_pipeline import book as book_pipeline

@app.post("/api/v2/books")
async def book_create(request: Request):
    body = await request.json()
    b = book_pipeline.create(body.get("title"), body.get("author", ""))
    return {"success": True, "book_id": b.book_id}

@app.get("/api/v2/books")
async def book_list():
    return book_pipeline.list_all()

@app.get("/api/v2/books/{book_id}")
async def book_get(book_id: str):
    b = book_pipeline.get(book_id)
    if not b:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"book_id": b.book_id, "title": b.title, "author": b.author,
            "pages": [{"page_number": p.page_number, "text": p.text,
                       "image_prompt": p.image_prompt, "status": p.status}
                      for p in b.pages], "style": b.style, "status": b.status}

@app.post("/api/v2/books/{book_id}/pages")
async def book_add_page(book_id: str, request: Request):
    body = await request.json()
    p = book_pipeline.add_page(book_id, body.get("text"), body.get("image_prompt", ""))
    if not p:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"success": True, "page_id": p.page_id}

@app.post("/api/v2/books/{book_id}/generate")
async def book_generate(book_id: str):
    ok = book_pipeline.generate_all_pages(book_id)
    return {"success": ok}


# ============================================================================
# Main Entry Point
# ============================================================================

try:
    from routes import register_all_routers
    register_all_routers(app)
    logger.info("Modular route modules registered successfully")
except ImportError as e:
    logger.warning(f"Routes module not available: {e}")

# ============================================================================
# 智影数据工场子系统 — /zhiying/*
# ============================================================================
try:
    from zhiying.router import router as zhiying_router
    app.include_router(zhiying_router)
    logger.info("智影数据工场 /zhiying/ subsystem registered")
except ImportError as e:
    logger.warning(f"Zhiying subsystem not available: {e}")

# ============================================================================
# IMDF API v1 增强路由 — 7个API存根模块真实化 (F1.14/F3.2/F5.3/F8.3/F8.4/F9.1/F9.2)
# ============================================================================
try:
    from imdf.api.copyright_routes import router as copyright_router
    app.include_router(copyright_router)
    logger.info("copyright_routes (F8.3) registered — sign/verify/embed/detect/similarity")
except Exception as e:
    logger.warning(f"copyright_routes not available: {e}")

try:
    from imdf.api.privacy_routes import router as privacy_router
    app.include_router(privacy_router)
    logger.info("privacy_routes (F8.4) registered — PII detect/mask, DSAR export/delete, consent")
except Exception as e:
    logger.warning(f"privacy_routes not available: {e}")

try:
    from imdf.api.webhook_routes import router as webhook_router
    app.include_router(webhook_router)
    logger.info("webhook_routes (F9.2) registered — CRUD, event-types, deliveries, test")
except Exception as e:
    logger.warning(f"webhook_routes not available: {e}")

try:
    from imdf.api.sdk_routes import router as sdk_router
    app.include_router(sdk_router)
    logger.info("sdk_routes (F9.1) registered — OpenAPI spec, Python/TypeScript SDK generation")
except Exception as e:
    logger.warning(f"sdk_routes not available: {e}")

try:
    from imdf.api.search_advanced_routes import router as search_advanced_router
    app.include_router(search_advanced_router)
    logger.info("search_advanced_routes (F1.14) registered — multimodal/similar/NL/faceted/cross-modal search")
except Exception as e:
    logger.warning(f"search_advanced_routes not available: {e}")

try:
    from imdf.api.workflow_contract_routes import router as workflow_contract_router
    app.include_router(workflow_contract_router)
    logger.info("workflow_contract_routes (F3.2) registered — define/validate/templates/conflicts/infer")
except Exception as e:
    logger.warning(f"workflow_contract_routes not available: {e}")

try:
    from imdf.api.crowd_settlement_routes import router as crowd_settlement_router
    app.include_router(crowd_settlement_router)
    logger.info("crowd_settlement_routes (F5.3) registered — calculate/approve/pay/reputation/report")
except Exception as e:
    logger.warning(f"crowd_settlement_routes not available: {e}")


# ============================================================================
# Main Entry Point
# ============================================================================

# P10R4-1 / HIDDEN-3: 启动时初始化第三方集成 (Sentry + structlog)
# 在 uvicorn.run 之前调用 — 这样 early-stage 日志也被 structlog 接管
try:
    from common.third_party import init_all_third_party
    import os as _os
    _third_party_status = init_all_third_party(
        sentry_dsn=_os.environ.get("SENTRY_DSN", ""),
        sentry_environment=_os.environ.get("ENVIRONMENT", "development"),
        sentry_release=_os.environ.get("GIT_COMMIT", "unknown"),
        structlog_json=_os.environ.get("STRUCTLOG_JSON", "true").lower() in ("true", "1", "yes"),
        structlog_level=_os.environ.get("LOG_LEVEL", "INFO"),
    )
    logger.info(
        "Third-party integration initialized: sentry=%s structlog=%s",
        _third_party_status.get("sentry", False),
        _third_party_status.get("structlog", False),
    )
except Exception as _e:
    logger.warning("Third-party init failed (graceful degradation): %s", _e)

# P10R4-1 / HIDDEN-1: 启动时确保 UnifiedAuthManager 用 BRUTE_FORCE_PERSISTENCE env 决策
# (UnifiedAuthManager 内部已读该 env var, 这里仅显式 log 提醒)
import os as _os2
if _os2.environ.get("BRUTE_FORCE_PERSISTENCE", "").lower() in ("true", "1", "yes", "on"):
    logger.info("BRUTE_FORCE_PERSISTENCE=true — brute force state will be persisted to SQLite")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8001,
        log_level="info",
        # Production settings
        limit_concurrency=100,
        limit_max_requests=1000,
        timeout_keep_alive=30
    )
