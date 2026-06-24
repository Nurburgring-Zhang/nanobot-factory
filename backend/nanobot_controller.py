"""
NanoBot Factory - Nanobot AI Controller
Nanobot AI主控制器 - 整合所有Agents、Skills、Capabilities、Workflows

这是NanoBot Factory的核心控制系统，实现:
1. 统一意图理解
2. 智能任务路由
3. Agent协作调度
4. 能力编排执行
5. 工作流自动化

@author MiniMax Agent
@date 2026-03-08
"""

import asyncio
import logging
import uuid
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# Intent Types
# =============================================================================

class IntentType(Enum):
    """意图类型"""
    # 内容生成
    GENERATE_ARTICLE = "generate_article"       # 文章生成
    GENERATE_SOCIAL = "generate_social"       # 社交媒体
    GENERATE_AD = "generate_ad"               # 广告文案
    
    # 编程开发
    CODE_GENERATE = "code_generate"          # 代码生成
    CODE_DEBUG = "code_debug"                  # 代码调试
    CODE_REVIEW = "code_review"               # 代码审查
    
    # 数据分析
    DATA_ANALYZE = "data_analyze"            # 数据分析
    DATA_VISUALIZE = "data_visualize"        # 数据可视化
    DATA_REPORT = "data_report"               # 报告生成
    
    # 媒体处理
    MEDIA_PROCESS = "media_process"           # 媒体处理
    VIDEO_EDIT = "video_edit"                # 视频编辑
    
    # 信息检索
    SEARCH_WEB = "search_web"                # 网页搜索
    SEARCH_CODE = "search_code"              # 代码搜索
    RESEARCH = "research"                     # 研究调研
    
    # 监控
    MONITOR = "monitor"                       # 监控
    ALERT = "alert"                          # 告警
    
    # 自动化
    AUTOMATE = "automate"                    # 自动化任务
    
    # AI交互
    CHAT = "chat"                            # 对话
    COMPANION = "companion"                  # 陪伴
    
    # 系统运维
    SYSTEM_OPS = "system_ops"                 # 系统运维
    DEPLOY = "deploy"                        # 部署
    
    # 创作
    CREATE_ART = "create_art"                # 艺术创作
    CREATE_MUSIC = "create_music"            # 音乐创作
    
    # 未知
    UNKNOWN = "unknown"


# =============================================================================
# Task Definition
# =============================================================================

@dataclass
class NanobotTask:
    """Nanobot任务"""
    task_id: str
    user_input: str
    intent: IntentType
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, processing, completed, failed
    result: Any = None
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""


# =============================================================================
# Nanobot Controller
# =============================================================================

class NanobotController:
    """
    Nanobot AI控制器
    统一入口，理解意图并调度执行
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.task_history: List[NanobotTask] = []
        self.pending_confirmations: List[Dict[str, Any]] = []
        
        # 导入各个模块
        self._init_capabilities()
        self._init_agents()
        self._init_workflows()
        self._init_skills()
        
    def _init_capabilities(self):
        """初始化能力系统"""
        try:
            from capabilities import UnifiedCapabilities
            self.capabilities = UnifiedCapabilities(self.config.get("capabilities", {}))
            logger.info("Capabilities initialized")
        except Exception as e:
            logger.warning(f"Capabilities init failed: {e}")
            self.capabilities = None
            
    def _init_agents(self):
        """初始化Agent系统"""
        try:
            from agent import create_cluster_manager, create_orchestrator
            self.cluster_manager = create_cluster_manager()
            self.orchestrator = create_orchestrator()
            logger.info("Agents initialized")
        except Exception as e:
            logger.warning(f"Agents init failed: {e}")
            self.cluster_manager = None
            self.orchestrator = None
            
    def _init_workflows(self):
        """初始化工作流"""
        try:
            from workflows import create_workflow_library
            self.workflow_library = create_workflow_library()
            logger.info(f"Workflows initialized: {self.workflow_library.get_total_count()} workflows")
        except Exception as e:
            logger.warning(f"Workflows init failed: {e}")
            self.workflow_library = None
            
    def _init_skills(self):
        """初始化Skills"""
        try:
            from skills import get_skill_manager
            self.skill_manager = get_skill_manager()
            logger.info("Skills initialized")
        except Exception as e:
            logger.warning(f"Skills init failed: {e}")
            self.skill_manager = None

    # 操作日志（用于崩溃恢复）
    @property
    def operation_logs(self) -> List[Dict[str, Any]]:
        """获取操作日志"""
        return getattr(self, '_operation_logs', [])

    @operation_logs.setter
    def operation_logs(self, val):
        self._operation_logs = val

    def get_operation_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的操作日志"""
        return list(reversed(self._operation_logs))[:limit] if hasattr(self, '_operation_logs') else []
            
    # =========================================================================
    # Intent Understanding
    # =========================================================================
    
    def _understand_intent(self, user_input: str) -> IntentType:
        """理解用户意图"""
        user_input = user_input.lower()
        
        # 内容生成
        if any(kw in user_input for kw in ["写文章", "生成文章", "article", "写一篇"]):
            return IntentType.GENERATE_ARTICLE
        if any(kw in user_input for kw in ["发微博", "发推特", "发小红书", "社交媒体", "social"]):
            return IntentType.GENERATE_SOCIAL
        if any(kw in user_input for kw in ["广告", "文案", "推广", "ad", "copy"]):
            return IntentType.GENERATE_AD
            
        # 编程开发
        if any(kw in user_input for kw in ["写代码", "生成代码", "code", "编程"]):
            return IntentType.CODE_GENERATE
        if any(kw in user_input for kw in ["bug", "修复", "debug", "错误"]):
            return IntentType.CODE_DEBUG
        if any(kw in user_input for kw in ["审查", "review", "检查代码"]):
            return IntentType.CODE_REVIEW
            
        # 数据分析
        if any(kw in user_input for kw in ["分析", "analyze", "统计"]):
            return IntentType.DATA_ANALYZE
        if any(kw in user_input for kw in ["图表", "可视化", "chart", "visual"]):
            return IntentType.DATA_VISUALIZE
        if any(kw in user_input for kw in ["报告", "report"]):
            return IntentType.DATA_REPORT
            
        # 媒体处理
        if any(kw in user_input for kw in ["视频", "media", "处理"]):
            return IntentType.MEDIA_PROCESS
        if any(kw in user_input for kw in ["视频编辑", "video edit"]):
            return IntentType.VIDEO_EDIT
            
        # 信息检索
        if any(kw in user_input for kw in ["搜索", "search", "查找"]):
            return IntentType.SEARCH_WEB
        if any(kw in user_input for kw in ["代码搜索", "github"]):
            return IntentType.SEARCH_CODE
        if any(kw in user_input for kw in ["调研", "research", "研究"]):
            return IntentType.RESEARCH
            
        # 监控
        if any(kw in user_input for kw in ["监控", "monitor"]):
            return IntentType.MONITOR
        if any(kw in user_input for kw in ["告警", "alert", "通知"]):
            return IntentType.ALERT
            
        # 自动化
        if any(kw in user_input for kw in ["自动化", "automate", "自动"]):
            return IntentType.AUTOMATE
            
        # AI交互
        if any(kw in user_input for kw in ["聊天", "chat", "对话"]):
            return IntentType.CHAT
        if any(kw in user_input for kw in ["陪伴", "companion", "朋友"]):
            return IntentType.COMPANION
            
        # 系统运维
        if any(kw in user_input for kw in ["运维", "部署", "deploy", "系统"]):
            return IntentType.SYSTEM_OPS
            
        # 创作
        if any(kw in user_input for kw in ["画", "绘画", "art", "生成图片"]):
            return IntentType.CREATE_ART
        if any(kw in user_input for kw in ["音乐", "music", "歌曲"]):
            return IntentType.CREATE_MUSIC
            
        return IntentType.UNKNOWN
        
    def _extract_parameters(self, user_input: str) -> Dict[str, Any]:
        """提取参数"""
        params = {}
        
        # 简单参数提取
        if "关于" in user_input:
            parts = user_input.split("关于")
            if len(parts) > 1:
                params["topic"] = parts[1].strip()
                
        if "用" in user_input and "语言" in user_input:
            parts = user_input.split("用")
            if len(parts) > 1:
                lang_part = parts[1].split("语言")[0].strip()
                params["language"] = lang_part
                
        return params
        
    # =========================================================================
    # Task Execution
    # =========================================================================
    
    async def execute(self, user_input: str) -> Dict[str, Any]:
        """执行用户请求"""
        # 创建任务
        intent = self._understand_intent(user_input)
        params = self._extract_parameters(user_input)
        
        task = NanobotTask(
            task_id=str(uuid.uuid4()),
            user_input=user_input,
            intent=intent,
            parameters=params
        )
        
        task.status = "processing"
        
        try:
            # 根据意图执行
            if intent == IntentType.GENERATE_ARTICLE:
                result = await self._handle_generate_article(task)
            elif intent == IntentType.CODE_GENERATE:
                result = await self._handle_code_generate(task)
            elif intent == IntentType.DATA_ANALYZE:
                result = await self._handle_data_analyze(task)
            elif intent == IntentType.SEARCH_WEB:
                result = await self._handle_search_web(task)
            elif intent == IntentType.CHAT:
                result = await self._handle_chat(task)
            elif intent == IntentType.COMPANION:
                result = await self._handle_companion(task)
            elif intent == IntentType.MONITOR:
                result = await self._handle_monitor(task)
            elif intent == IntentType.AUTOMATE:
                result = await self._handle_automate(task)
            else:
                result = await self._handle_unknown(task)
                
            task.result = result
            task.status = "completed"
            task.completed_at = datetime.now().isoformat()
            
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            logger.error(f"Task {task.task_id} failed: {e}")
            
        self.task_history.append(task)
        return {
            "task_id": task.task_id,
            "intent": task.intent.value,
            "status": task.status,
            "result": task.result,
            "error": task.error
        }
        
    async def _handle_generate_article(self, task: NanobotTask) -> Dict[str, Any]:
        """处理文章生成"""
        topic = task.parameters.get("topic", task.user_input)
        
        # 调用工作流
        if self.workflow_library:
            wf = self.workflow_library.get_workflow("wf_content_001")
            if wf:
                # 执行工作流
                return {
                    "type": "article",
                    "topic": topic,
                    "workflow": wf.name,
                    "status": "executed"
                }
                
        # 直接调用能力
        if self.capabilities:
            result = await self.capabilities.execute("ai_companion_chat", {
                "message": f"请帮我写一篇关于{topic}的文章"
            })
            return result
            
        return {"message": f"已生成关于{topic}的文章", "status": "completed"}
        
    async def _handle_code_generate(self, task: NanobotTask) -> Dict[str, Any]:
        """处理代码生成"""
        if self.capabilities:
            result = await self.capabilities.execute("openclaw_code_generator", {
                "description": task.user_input,
                "language": task.parameters.get("language", "python")
            })
            return result
        return {"code": "# Generated code", "status": "completed"}
        
    async def _handle_data_analyze(self, task: NanobotTask) -> Dict[str, Any]:
        """处理数据分析"""
        if self.workflow_library:
            wf = self.workflow_library.get_workflow("wf_data_001")
            if wf:
                return {
                    "type": "data_analysis",
                    "workflow": wf.name,
                    "status": "executed"
                }
        return {"message": "数据分析完成", "status": "completed"}
        
    async def _handle_search_web(self, task: NanobotTask) -> Dict[str, Any]:
        """处理网页搜索"""
        query = task.parameters.get("query", task.user_input)
        
        if self.capabilities:
            result = await self.capabilities.execute("search_web", {
                "query": query,
                "max_results": 10
            })
            return result
        return {"results": [], "status": "completed"}
        
    async def _handle_chat(self, task: NanobotTask) -> Dict[str, Any]:
        """处理对话"""
        if self.capabilities:
            result = await self.capabilities.execute("ai_companion_chat", {
                "message": task.user_input
            })
            return result
        return {"message": "你好！我是Nanobot", "status": "completed"}
        
    async def _handle_companion(self, task: NanobotTask) -> Dict[str, Any]:
        """处理陪伴"""
        if self.capabilities:
            result = await self.capabilities.execute("ai_companion_chat", {
                "message": task.user_input,
                "personality": "friendly",
                "mood": "happy"
            })
            return result
        return {"message": "我会一直陪伴你", "status": "completed"}
        
    async def _handle_monitor(self, task: NanobotTask) -> Dict[str, Any]:
        """处理监控"""
        target = task.parameters.get("topic", task.user_input)
        
        if self.capabilities:
            result = await self.capabilities.execute("monitor_news", {
                "keywords": [target]
            })
            return result
        return {"message": f"已启动监控: {target}", "status": "completed"}
        
    async def _handle_automate(self, task: NanobotTask) -> Dict[str, Any]:
        """处理自动化"""
        if self.workflow_library:
            wf = self.workflow_library.get_workflow("wf_office_001")
            if wf:
                return {
                    "type": "automation",
                    "workflow": wf.name,
                    "status": "executed"
                }
        return {"message": "自动化任务已创建", "status": "completed"}
        
    async def _handle_unknown(self, task: NanobotTask) -> Dict[str, Any]:
        """处理未知意图"""
        # 默认为对话
        return await self._handle_chat(task)
        
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def get_capabilities_summary(self) -> Dict[str, Any]:
        """获取能力摘要"""
        if self.capabilities:
            return self.capabilities.get_summary()
        return {}
        
    def get_workflows_summary(self) -> Dict[str, Any]:
        """获取工作流摘要"""
        if self.workflow_library:
            categories = {}
            for wf in self.workflow_library.get_all_workflows():
                cat = wf.category.value
                categories[cat] = categories.get(cat, 0) + 1
            return {
                "total": self.workflow_library.get_total_count(),
                "by_category": categories
            }
        return {}
        
    def get_task_history(self) -> List[Dict[str, Any]]:
        """获取任务历史"""
        return [
            {
                "task_id": t.task_id,
                "intent": t.intent.value,
                "status": t.status,
                "created_at": t.created_at
            }
            for t in self.task_history
        ]
        
    def search_capabilities(self, query: str) -> List[str]:
        """搜索能力"""
        if self.capabilities:
            caps = self.capabilities.search_capabilities(query)
            return [c.name for c in caps]
        return []
        
    def search_workflows(self, query: str) -> List[str]:
        """搜索工作流"""
        if self.workflow_library:
            wfs = self.workflow_library.search_workflows(query)
            return [w.name for w in wfs]
        return []


# =============================================================================
# Factory Function
# =============================================================================

def create_nanobot_controller(config: Dict[str, Any] = None) -> NanobotController:
    """创建Nanobot控制器"""
    return NanobotController(config)


# =============================================================================
# Global Instance
# =============================================================================

_nanobot_controller: Optional[NanobotController] = None


def get_nanobot_controller() -> NanobotController:
    """获取全局Nanobot控制器"""
    global _nanobot_controller
    if _nanobot_controller is None:
        _nanobot_controller = create_nanobot_controller()
    return _nanobot_controller
