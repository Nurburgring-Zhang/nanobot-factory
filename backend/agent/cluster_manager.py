"""
NanoBot Factory - Agent Cluster System
Agent集群管理系统 - 支持多Agent协作和子Agent调用

功能:
1. Agent集群管理
2. 子Agent调用
3. Agent任务分配
4. Agent协作与通信
5. Agent状态监控

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


class AgentRole(Enum):
    """Agent角色"""
    LEADER = "leader"           # 领导者Agent
    WORKER = "worker"          # 工作Agent
    SPECIALIST = "specialist"   # 专家Agent
    COORDINATOR = "coordinator" # 协调Agent
    MONITOR = "monitor"        # 监控Agent


class AgentStatus(Enum):
    """Agent状态"""
    IDLE = "idle"              # 空闲
    BUSY = "busy"              # 忙碌
    WORKING = "working"        #工作中
    WAITING = "waiting"         # 等待中
    ERROR = "error"            # 错误


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class AgentCapability:
    """Agent能力定义"""
    name: str
    description: str
    category: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubAgent:
    """子Agent定义"""
    agent_id: str
    name: str
    role: AgentRole
    capabilities: List[AgentCapability]
    status: AgentStatus = AgentStatus.IDLE
    current_task: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def can_handle(self, capability: str) -> bool:
        """检查是否能处理某能力"""
        for cap in self.capabilities:
            if cap.name == capability or cap.category == capability:
                return True
        return False


@dataclass
class ClusterTask:
    """集群任务"""
    task_id: str
    description: str
    required_capabilities: List[str]
    assigned_agents: List[str] = field(default_factory=list)
    status: str = "pending"
    priority: TaskPriority = TaskPriority.NORMAL
    result: Any = None
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""
    parent_task_id: Optional[str] = None


@dataclass
class AgentResult:
    """Agent执行结果"""
    agent_id: str
    task_id: str
    status: str
    result: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentCluster:
    """
    Agent集群管理器
    管理多Agent协作和子Agent调用
    """
    
    def __init__(self, cluster_id: str = None):
        self.cluster_id = cluster_id or str(uuid.uuid4())
        self.agents: Dict[str, SubAgent] = {}
        self.tasks: Dict[str, ClusterTask] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.results: Dict[str, AgentResult] = {}
        
    def register_agent(self, agent: SubAgent):
        """注册Agent到集群"""
        self.agents[agent.agent_id] = agent
        logger.info(f"Agent {agent.name} registered to cluster {self.cluster_id}")
        
    def unregister_agent(self, agent_id: str):
        """注销Agent"""
        if agent_id in self.agents:
            del self.agents[agent_id]
            logger.info(f"Agent {agent_id} unregistered from cluster {self.cluster_id}")
            
    def get_agent(self, agent_id: str) -> Optional[SubAgent]:
        """获取Agent"""
        return self.agents.get(agent_id)
    
    def get_available_agents(self, capability: str = None) -> List[SubAgent]:
        """获取可用Agent"""
        available = []
        for agent in self.agents.values():
            if agent.status == AgentStatus.IDLE:
                if capability is None or agent.can_handle(capability):
                    available.append(agent)
        return available
    
    def get_agents_by_role(self, role: AgentRole) -> List[SubAgent]:
        """按角色获取Agent"""
        return [a for a in self.agents.values() if a.role == role]
    
    def get_leader(self) -> Optional[SubAgent]:
        """获取领导者Agent"""
        leaders = self.get_agents_by_role(AgentRole.LEADER)
        return leaders[0] if leaders else None
    
    async def assign_task(self, task: ClusterTask) -> str:
        """分配任务"""
        # 查找合适的Agent
        suitable_agents = []
        for agent in self.agents.values():
            if agent.status == AgentStatus.IDLE:
                for cap in task.required_capabilities:
                    if agent.can_handle(cap):
                        suitable_agents.append(agent)
                        break
        
        if not suitable_agents:
            # 没有空闲Agent，等待
            await self.task_queue.put(task)
            return ""
            
        # 选择第一个合适的Agent
        selected_agent = suitable_agents[0]
        task.assigned_agents = [selected_agent.agent_id]
        selected_agent.status = AgentStatus.BUSY
        selected_agent.current_task = task.task_id
        
        self.tasks[task.task_id] = task
        logger.info(f"Task {task.task_id} assigned to agent {selected_agent.name}")
        
        return selected_agent.agent_id
    
    async def execute_task(self, agent_id: str, task: ClusterTask) -> AgentResult:
        """执行任务"""
        import time
        start_time = time.time()
        
        agent = self.get_agent(agent_id)
        if not agent:
            return AgentResult(
                agent_id=agent_id,
                task_id=task.task_id,
                status="error",
                result=None,
                error="Agent not found"
            )
            
        try:
            agent.status = AgentStatus.WORKING
            task.status = "running"
            
            # 执行任务逻辑（这里会根据任务类型调用相应能力）
            result = await self._execute_agent_task(agent, task)
            
            execution_time = time.time() - start_time
            
            agent.status = AgentStatus.IDLE
            agent.current_task = None
            task.status = "completed"
            task.completed_at = datetime.now().isoformat()
            
            agent_result = AgentResult(
                agent_id=agent_id,
                task_id=task.task_id,
                status="success",
                result=result,
                execution_time=execution_time
            )
            
            self.results[task.task_id] = agent_result
            
            return agent_result
            
        except Exception as e:
            agent.status = AgentStatus.ERROR
            task.status = "failed"
            task.error = str(e)
            
            execution_time = time.time() - start_time
            
            return AgentResult(
                agent_id=agent_id,
                task_id=task.task_id,
                status="error",
                result=None,
                error=str(e),
                execution_time=execution_time
            )
            
    async def _execute_agent_task(self, agent: SubAgent, task: ClusterTask) -> Any:
        """执行具体任务"""
        # 这里会根据任务类型调用相应的处理函数
        # 实际实现会调用 capabilities 或 skills
        return {
            "agent": agent.name,
            "task": task.description,
            "capabilities": task.required_capabilities,
            "executed": True
        }
    
    def get_task_status(self, task_id: str) -> Optional[ClusterTask]:
        """获取任务状态"""
        return self.tasks.get(task_id)
    
    def get_cluster_status(self) -> Dict[str, Any]:
        """获取集群状态"""
        status_counts = {
            "idle": 0,
            "busy": 0,
            "working": 0,
            "waiting": 0,
            "error": 0
        }
        
        for agent in self.agents.values():
            status_counts[agent.status.value] += 1
            
        return {
            "cluster_id": self.cluster_id,
            "total_agents": len(self.agents),
            "status_counts": status_counts,
            "total_tasks": len(self.tasks),
            "pending_tasks": len(self.task_queue),
            "completed_tasks": len([t for t in self.tasks.values() if t.status == "completed"])
        }


class AgentClusterManager:
    """
    Agent集群管理器
    管理多个Agent集群
    """
    
    def __init__(self):
        self.clusters: Dict[str, AgentCluster] = {}
        self.default_cluster: Optional[AgentCluster] = None
        
    def create_cluster(self, cluster_id: str = None) -> AgentCluster:
        """创建集群"""
        cluster = AgentCluster(cluster_id)
        self.clusters[cluster.cluster_id] = cluster
        
        if self.default_cluster is None:
            self.default_cluster = cluster
            
        logger.info(f"Cluster {cluster.cluster_id} created")
        return cluster
    
    def get_cluster(self, cluster_id: str) -> Optional[AgentCluster]:
        """获取集群"""
        return self.clusters.get(cluster_id)
    
    def get_default_cluster(self) -> AgentCluster:
        """获取默认集群"""
        if self.default_cluster is None:
            self.default_cluster = self.create_cluster("default")
        return self.default_cluster
    
    def delete_cluster(self, cluster_id: str):
        """删除集群"""
        if cluster_id in self.clusters:
            del self.clusters[cluster_id]
            logger.info(f"Cluster {cluster_id} deleted")
    
    def list_clusters(self) -> List[str]:
        """列出所有集群"""
        return list(self.clusters.keys())


# =============================================================================
# 子Agent调用系统
# =============================================================================

class SubAgentCaller:
    """
    子Agent调用器
    支持动态调用子Agent进行任务处理
    """
    
    def __init__(self, cluster: AgentCluster):
        self.cluster = cluster
        self.call_history: List[Dict[str, Any]] = []
        
    async def call_sub_agent(
        self,
        capability: str,
        parameters: Dict[str, Any],
        timeout: float = 30.0
    ) -> AgentResult:
        """调用子Agent"""
        # 查找合适的Agent
        available_agents = self.cluster.get_available_agents(capability)
        
        if not available_agents:
            # 创建新任务等待处理
            task = ClusterTask(
                task_id=str(uuid.uuid4()),
                description=f"Task requiring {capability}",
                required_capabilities=[capability]
            )
            await self.cluster.assign_task(task)
            
            return AgentResult(
                agent_id="",
                task_id=task.task_id,
                status="pending",
                result=None,
                error="No available agent, task queued"
            )
        
        # 选择Agent并执行
        agent = available_agents[0]
        
        task = ClusterTask(
            task_id=str(uuid.uuid4()),
            description=f"Task for {capability}",
            required_capabilities=[capability],
            assigned_agents=[agent.agent_id]
        )
        
        self.cluster.tasks[task.task_id] = task
        
        result = await asyncio.wait_for(
            self.cluster.execute_task(agent.agent_id, task),
            timeout=timeout
        )
        
        # 记录调用历史
        self.call_history.append({
            "agent_id": agent.agent_id,
            "capability": capability,
            "result": result.status,
            "timestamp": datetime.now().isoformat()
        })
        
        return result
    
    async def call_multiple_agents(
        self,
        capabilities: List[str],
        parameters: Dict[str, Any]
    ) -> List[AgentResult]:
        """并行调用多个子Agent"""
        tasks = []
        for cap in capabilities:
            task = self.call_sub_agent(cap, parameters)
            tasks.append(task)
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤异常
        valid_results = []
        for r in results:
            if isinstance(r, Exception):
                valid_results.append(AgentResult(
                    agent_id="",
                    task_id="",
                    status="error",
                    result=None,
                    error=str(r)
                ))
            else:
                valid_results.append(r)
                
        return valid_results
    
    def get_call_history(self) -> List[Dict[str, Any]]:
        """获取调用历史"""
        return self.call_history


# =============================================================================
# Agent工厂函数
# =============================================================================

def create_cluster_manager() -> AgentClusterManager:
    """创建集群管理器"""
    return AgentClusterManager()


def create_sub_agent_caller(cluster: AgentCluster = None) -> SubAgentCaller:
    """创建子Agent调用器"""
    if cluster is None:
        manager = create_cluster_manager()
        cluster = manager.get_default_cluster()
    return SubAgentCaller(cluster)


def create_sub_agent(
    agent_id: str,
    name: str,
    role: AgentRole,
    capabilities: List[Dict[str, Any]]
) -> SubAgent:
    """创建子Agent"""
    agent_capabilities = [
        AgentCapability(
            name=cap["name"],
            description=cap.get("description", ""),
            category=cap.get("category", "general"),
            parameters=cap.get("parameters", {})
        )
        for cap in capabilities
    ]
    
    return SubAgent(
        agent_id=agent_id,
        name=name,
        role=role,
        capabilities=agent_capabilities
    )
