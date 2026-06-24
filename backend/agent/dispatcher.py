"""
NanoBot Factory - Dispatcher Agent
智能任务分发与专家Agent路由
@author MiniMax Agent
@date 2026-04-13
"""
import asyncio, logging, time, uuid
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class TaskDomain(Enum):
    CODING = "coding"
    CONTENT_CREATION = "content_creation"
    DATA_ANALYSIS = "data_analysis"
    WEB_SEARCH = "web_search"
    FILE_OPERATIONS = "file_operations"
    IMAGE_GENERATION = "image_generation"
    VIDEO_PROCESSING = "video_processing"
    DATABASE = "database"
    MONITORING = "monitoring"
    AUTOMATION = "automation"
    REASONING = "reasoning"
    COMMUNICATION = "communication"
    MEMORY = "memory"
    GENERAL = "general"

class AgentStatus(Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"

class DispatchStrategy(Enum):
    BEST_MATCH = "best_match"
    ROUND_ROBIN = "round_robin"
    LEAST_BUSY = "least_busy"
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"

@dataclass
class ExpertAgentProfile:
    agent_id: str
    name: str
    description: str
    domains: List[TaskDomain]
    capabilities: List[str]
    priority: int = 5
    max_concurrent: int = 3
    avg_response_ms: float = 1000.0
    success_rate: float = 1.0
    current_tasks: int = 0
    status: AgentStatus = AgentStatus.AVAILABLE
    handler: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_available(self) -> bool:
        return self.status == AgentStatus.AVAILABLE and self.current_tasks < self.max_concurrent

    def load_score(self) -> float:
        if self.max_concurrent == 0:
            return float("inf")
        return self.current_tasks / self.max_concurrent

@dataclass
class DispatchTask:
    task_id: str
    description: str
    domain: TaskDomain
    priority: int = 5
    inputs: Dict[str, Any] = field(default_factory=dict)
    required_capabilities: List[str] = field(default_factory=list)
    timeout_seconds: float = 60.0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DispatchResult:
    task_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    agent_id: str = ""
    agent_name: str = ""
    execution_ms: float = 0.0
    domain: Optional[TaskDomain] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "execution_ms": self.execution_ms,
            "domain": self.domain.value if self.domain else None,
        }


class TaskIntentAnalyzer:
    """任务意图分析器 - 基于关键词快速分类任务领域"""
    DOMAIN_KEYWORDS = {
        TaskDomain.CODING: ["代码","编程","程序","函数","类","算法","bug","调试","debug","python","javascript","java","sql","api","接口","code","script"],
        TaskDomain.CONTENT_CREATION: ["写作","文章","内容","文案","博客","报告","总结","摘要","翻译","改写","创作","write","article","blog","summary","translate"],
        TaskDomain.DATA_ANALYSIS: ["分析","数据","统计","图表","可视化","趋势","excel","csv","pandas","analysis","data","statistics","chart"],
        TaskDomain.WEB_SEARCH: ["搜索","查找","找","搜","信息","新闻","资讯","最新","查询","search","find","lookup","browse","internet","web"],
        TaskDomain.FILE_OPERATIONS: ["文件","文档","读取","写入","保存","上传","下载","复制","移动","目录","file","document","read","write","save","upload","download"],
        TaskDomain.IMAGE_GENERATION: ["图片","图像","生成图","画","绘画","插图","image","photo","picture","generate","draw","stable diffusion","图片生成","文生图"],
        TaskDomain.VIDEO_PROCESSING: ["视频","video","mp4","剪辑","转换","字幕","视频生成","视频剪辑"],
        TaskDomain.DATABASE: ["数据库","database","mysql","postgresql","mongodb","redis","sqlite","查询","增删改查","crud","schema"],
        TaskDomain.MONITORING: ["监控","监测","告警","预警","跟踪","舆情","情感","monitor","track","alert","sentiment","trend"],
        TaskDomain.AUTOMATION: ["自动化","定时","批量","流程","工作流","触发","调度","automation","schedule","batch","workflow","cron"],
        TaskDomain.REASONING: ["推理","判断","评估","思考","规划","决策","建议","reasoning","analyze","evaluate","plan","decide"],
        TaskDomain.COMMUNICATION: ["发送","消息","邮件","通知","推送","提醒","聊天","send","message","email","notify","chat"],
        TaskDomain.MEMORY: ["记忆","记住","保存记录","历史","上下文","回忆","memory","remember","history","context","recall"],
    }

    @classmethod
    def analyze(cls, task_description: str) -> Tuple[TaskDomain, float]:
        text = task_description.lower()
        scores = {}
        for domain, keywords in cls.DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[domain] = score
        if not scores:
            return TaskDomain.GENERAL, 0.5
        best = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = min(scores[best] / max(total, 1) * 2, 1.0)
        return best, confidence

    @classmethod
    def analyze_multi(cls, task_description: str, top_k: int = 3) -> List[Tuple[TaskDomain, float]]:
        text = task_description.lower()
        scores = {}
        for domain, keywords in cls.DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[domain] = score
        if not scores:
            return [(TaskDomain.GENERAL, 0.5)]
        total = sum(scores.values())
        sorted_d = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(d, min(s/total*2, 1.0)) for d, s in sorted_d[:top_k]]


class ExpertAgentRouter:
    """专家Agent路由器 - 智能选择最优Agent"""
    def __init__(self):
        self._rr_index: Dict[str, int] = {}

    def select_agent(self, domain: TaskDomain, agents: List[ExpertAgentProfile], strategy: DispatchStrategy = DispatchStrategy.BEST_MATCH) -> Optional[ExpertAgentProfile]:
        candidates = [a for a in agents if domain in a.domains and a.is_available()]
        if not candidates:
            candidates = [a for a in agents if TaskDomain.GENERAL in a.domains and a.is_available()]
        if not candidates:
            return None
        if strategy == DispatchStrategy.ROUND_ROBIN:
            key = domain.value
            idx = self._rr_index.get(key, 0)
            agent = candidates[idx % len(candidates)]
            self._rr_index[key] = (idx + 1) % len(candidates)
            return agent
        elif strategy == DispatchStrategy.LEAST_BUSY:
            return min(candidates, key=lambda a: a.load_score())
        else:
            def score(a):
                return a.priority * 2 + a.success_rate * 3 - a.avg_response_ms/1000 - a.load_score()*2
            return max(candidates, key=score)


class DispatcherAgent:
    """调度Agent主控系统 - NanoBot Factory中央智能路由器"""

    def __init__(self, capability_manager=None, strategy: DispatchStrategy = DispatchStrategy.BEST_MATCH):
        self.capability_manager = capability_manager
        self.strategy = strategy
        self.intent_analyzer = TaskIntentAnalyzer()
        self.router = ExpertAgentRouter()
        self._agents: Dict[str, ExpertAgentProfile] = {}
        self._task_history: List[DispatchResult] = []
        self._stats = {"total_dispatched": 0, "total_success": 0, "total_failed": 0, "by_domain": {}}
        self._register_builtin_agents()
        logger.info(f"DispatcherAgent initialized with {len(self._agents)} expert agents")

    def _register_builtin_agents(self):
        cm = self.capability_manager

        async def coding_handler(task):
            if cm:
                r = await cm.execute_capability("openclaw_coding_agent", {"task": task.description, **task.inputs})
                return r.result if r.status == "success" else {"error": r.error}
            return {"domain": "coding", "task": task.description, "status": "completed"}

        async def content_handler(task):
            if cm:
                r = await cm.execute_capability("openclaw_text_summarizer", {"task": task.description, **task.inputs})
                return r.result if r.status == "success" else {"error": r.error}
            return {"domain": "content", "task": task.description, "status": "completed"}

        async def search_handler(task):
            if cm:
                r = await cm.execute_capability("openclaw_web_search", {"query": task.description, **task.inputs})
                return r.result if r.status == "success" else {"error": r.error}
            return {"domain": "search", "task": task.description, "status": "completed"}

        async def data_handler(task):
            return {"domain": "data_analysis", "task": task.description, "status": "completed"}

        async def file_handler(task):
            if cm:
                r = await cm.execute_capability("mcp_fs_read", {"path": task.inputs.get("path",""), **task.inputs})
                return r.result if r.status == "success" else {"error": r.error}
            return {"domain": "file", "task": task.description, "status": "completed"}

        async def image_handler(task):
            return {"domain": "image_generation", "task": task.description, "status": "completed"}

        async def general_handler(task):
            return {"domain": "general", "task": task.description, "status": "completed", "message": "通用Agent处理完成"}

        builtin = [
            ExpertAgentProfile("expert_coding_001", "编程专家Agent", "专注代码生成/调试/审查/重构",
                [TaskDomain.CODING, TaskDomain.DATABASE],
                ["openclaw_coding_agent","openclaw_code_generator","openclaw_code_reviewer","openclaw_debugger","openclaw_sql_generator"],
                priority=9, handler=coding_handler),
            ExpertAgentProfile("expert_content_001", "内容创作专家Agent", "专注写作/摘要/翻译",
                [TaskDomain.CONTENT_CREATION, TaskDomain.REASONING],
                ["openclaw_text_summarizer","openclaw_pdf_summarizer","openclaw_youtube_transcript"],
                priority=8, handler=content_handler),
            ExpertAgentProfile("expert_search_001", "搜索专家Agent", "专注网络搜索/信息检索",
                [TaskDomain.WEB_SEARCH, TaskDomain.MONITORING],
                ["openclaw_web_search","openclaw_github_search","monitor_news","analyze_trends"],
                priority=8, handler=search_handler),
            ExpertAgentProfile("expert_data_001", "数据分析专家Agent", "专注数据统计/趋势分析",
                [TaskDomain.DATA_ANALYSIS, TaskDomain.MONITORING],
                ["analyze_sentiment","analyze_trends","detect_emerging_topics","monitor_stock"],
                priority=8, handler=data_handler),
            ExpertAgentProfile("expert_file_001", "文件操作专家Agent", "专注文件读写/目录管理",
                [TaskDomain.FILE_OPERATIONS],
                ["mcp_fs_read","mcp_fs_write","mcp_fs_list","mcp_fs_search","mcp_fs_move"],
                priority=7, handler=file_handler),
            ExpertAgentProfile("expert_image_001", "图像生成专家Agent", "专注AI图像生成/编辑",
                [TaskDomain.IMAGE_GENERATION, TaskDomain.VIDEO_PROCESSING],
                ["ai_avatar_animate","ai_live2d_control","openclaw_image_resizer","openclaw_video_frame"],
                priority=7, handler=image_handler),
            ExpertAgentProfile("expert_general_001", "通用Agent", "处理所有无法分类的通用任务",
                [TaskDomain.GENERAL, TaskDomain.REASONING, TaskDomain.COMMUNICATION, TaskDomain.MEMORY],
                ["*"], priority=3, handler=general_handler),
        ]
        for agent in builtin:
            self.register_agent(agent)

    def register_agent(self, agent: ExpertAgentProfile):
        self._agents[agent.agent_id] = agent
        logger.info(f"Registered: {agent.name} [{', '.join(d.value for d in agent.domains)}]")

    def unregister_agent(self, agent_id: str) -> bool:
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    def list_agents(self) -> List[Dict[str, Any]]:
        return [{"id": a.agent_id, "name": a.name, "domains": [d.value for d in a.domains],
                 "status": a.status.value, "current_tasks": a.current_tasks,
                 "success_rate": round(a.success_rate, 4)} for a in self._agents.values()]

    async def dispatch(self, task_description: str, inputs: Dict[str, Any] = None,
                       task_id: str = None, force_domain: TaskDomain = None,
                       strategy: DispatchStrategy = None) -> DispatchResult:
        task_id = task_id or str(uuid.uuid4())
        inputs = inputs or {}
        strategy = strategy or self.strategy
        start = time.time()

        domain, confidence = (force_domain, 1.0) if force_domain else self.intent_analyzer.analyze(task_description)
        logger.info(f"Dispatch [{task_id[:8]}] domain={domain.value} confidence={confidence:.2f}")

        task = DispatchTask(task_id=task_id, description=task_description, domain=domain, inputs=inputs)
        agent = self.router.select_agent(domain, list(self._agents.values()), strategy)

        if not agent:
            result = DispatchResult(task_id=task_id, success=False,
                                    error=f"No available agent for domain: {domain.value}",
                                    execution_ms=(time.time()-start)*1000)
            self._record(result)
            return result

        result = await self._execute_on_agent(task, agent)
        result.execution_ms = (time.time()-start)*1000
        result.domain = domain
        self._record(result)
        return result

    async def dispatch_parallel(self, tasks: List[Dict[str, Any]]) -> List[DispatchResult]:
        coros = [self.dispatch(t.get("description",""), t.get("inputs",{}),
                               t.get("task_id"), t.get("domain")) for t in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)
        return [DispatchResult(task_id=tasks[i].get("task_id",""), success=False, error=str(r))
                if isinstance(r, Exception) else r for i, r in enumerate(results)]

    async def dispatch_pipeline(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        context = {}
        for i, step in enumerate(steps):
            merged = {**context, **step.get("inputs", {})}
            result = await self.dispatch(step["description"], merged, force_domain=step.get("domain"))
            key = step.get("output_key", f"step_{i}")
            context[key] = result.result if result.success else {"error": result.error}
        return context

    async def _execute_on_agent(self, task: DispatchTask, agent: ExpertAgentProfile) -> DispatchResult:
        agent.current_tasks += 1
        if agent.current_tasks >= agent.max_concurrent:
            agent.status = AgentStatus.BUSY
        start = time.time()
        try:
            if agent.handler:
                raw = await asyncio.wait_for(agent.handler(task), timeout=task.timeout_seconds)
            else:
                raw = {"agent": agent.name, "task": task.description, "status": "no_handler"}
            exec_ms = (time.time()-start)*1000
            self._update_agent_perf(agent, True, exec_ms)
            return DispatchResult(task_id=task.task_id, success=True, result=raw,
                                  agent_id=agent.agent_id, agent_name=agent.name, execution_ms=exec_ms)
        except asyncio.TimeoutError:
            exec_ms = (time.time()-start)*1000
            self._update_agent_perf(agent, False, exec_ms)
            return DispatchResult(task_id=task.task_id, success=False,
                                  error=f"Timeout ({task.timeout_seconds}s)",
                                  agent_id=agent.agent_id, agent_name=agent.name)
        except Exception as e:
            exec_ms = (time.time()-start)*1000
            self._update_agent_perf(agent, False, exec_ms)
            logger.error(f"Agent {agent.name} error: {e}", exc_info=True)
            return DispatchResult(task_id=task.task_id, success=False,
                                  error=f"{type(e).__name__}: {e}",
                                  agent_id=agent.agent_id, agent_name=agent.name)
        finally:
            agent.current_tasks = max(0, agent.current_tasks-1)
            if agent.current_tasks < agent.max_concurrent:
                agent.status = AgentStatus.AVAILABLE

    def _update_agent_perf(self, agent, success, exec_ms):
        agent.avg_response_ms = 0.1*exec_ms + 0.9*agent.avg_response_ms
        agent.success_rate = 0.05*(1.0 if success else 0.0) + 0.95*agent.success_rate

    def _record(self, result: DispatchResult):
        self._task_history.append(result)
        if len(self._task_history) > 1000:
            self._task_history.pop(0)
        self._stats["total_dispatched"] += 1
        if result.success:
            self._stats["total_success"] += 1
        else:
            self._stats["total_failed"] += 1
        if result.domain:
            d = result.domain.value
            if d not in self._stats["by_domain"]:
                self._stats["by_domain"][d] = {"success": 0, "failed": 0}
            self._stats["by_domain"][d]["success" if result.success else "failed"] += 1

    def get_stats(self) -> Dict[str, Any]:
        total = self._stats["total_dispatched"]
        return {
            "total_dispatched": total,
            "total_success": self._stats["total_success"],
            "total_failed": self._stats["total_failed"],
            "success_rate": round(self._stats["total_success"]/max(total,1), 4),
            "active_agents": len([a for a in self._agents.values() if a.status != AgentStatus.OFFLINE]),
            "by_domain": self._stats["by_domain"],
            "agents": [{"id": a.agent_id, "name": a.name, "status": a.status.value,
                        "success_rate": round(a.success_rate,4),
                        "avg_response_ms": round(a.avg_response_ms,2),
                        "current_tasks": a.current_tasks} for a in self._agents.values()]
        }

    def get_task_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._task_history[-limit:]]


def create_dispatcher(capability_manager=None, strategy: DispatchStrategy = DispatchStrategy.BEST_MATCH) -> DispatcherAgent:
    return DispatcherAgent(capability_manager, strategy)


__all__ = ["DispatcherAgent","ExpertAgentProfile","DispatchTask","DispatchResult",
           "TaskDomain","TaskIntentAnalyzer","DispatchStrategy","AgentStatus","create_dispatcher"]
