#!/usr/bin/env python3
"""
NanoBot Factory - Agent Registry & Spawn System
Agent注册与Spawn系统 - 实现真实的Agent生命周期管理
@author MiniMax Agent
@date 2026-04-14
"""
import asyncio
import logging
import uuid
import time
import threading
from typing import Dict, List, Any, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AgentType(Enum):
    OPERATIONS = "operations"
    DESIGN = "design"
    PRODUCT = "product"
    RND = "rnd"
    PROJECT_MANAGEMENT = "pm"
    PROJECT_DEVELOPMENT = "pjd"
    PROJECT_SUPPORT = "ps"
    ENGINEERING = "engineering"
    TESTING = "testing"
    MEDIA = "media"
    SUPPORT = "support"
    SALES = "sales"
    TECHNICAL_EXPERT = "technical"
    DOMAIN_EXPERT = "domain"
    INDUSTRY_EXPERT = "industry"
    DISPATCHER = "dispatcher"
    COORDINATOR = "coordinator"
    MONITOR = "monitor"
    CUSTOM = "custom"
    DEVELOPER = "developer"
    ARCHITECT = "architect"
    DEVOPS = "devops"
    QA = "qa"
    SECURITY = "security"
    PERFORMANCE = "performance"
    DATA = "data"
    PLATFORM = "platform"
    INFRA = "infra"


class AgentState(Enum):
    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentProfile:
    agent_id: str
    name: str
    agent_type: AgentType
    personality: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    experience: List[Dict[str, Any]] = field(default_factory=list)
    workflow: Dict[str, Any] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    collaboration: Dict[str, Any] = field(default_factory=dict)
    system_prompt: str = ""
    state: AgentState = AgentState.UNREGISTERED

    def to_dict(self) -> Dict[str, Any]:
        return {"agent_id": self.agent_id, "name": self.name, "type": self.agent_type.value,
                "caps": self.capabilities, "skills": self.skills, "state": self.state.value}


@dataclass
class AgentInstance:
    instance_id: str
    profile: AgentProfile
    context: Dict[str, Any] = field(default_factory=dict)
    current_task: Optional[str] = None
    state: AgentState = AgentState.IDLE
    stats: Dict[str, Any] = field(default_factory=dict)
    last_active: datetime = field(default_factory=datetime.now)


class AgentRegistry:
    """Agent注册表"""
    def __init__(self):
        self._profiles: Dict[str, AgentProfile] = {}
        self._instances: Dict[str, AgentInstance] = {}
        self._cap_index: Dict[str, Set[str]] = {}
        self._type_index: Dict[AgentType, Set[str]] = {}
        self._lock = threading.RLock()
        self._stats = {"total_registered": 0, "total_spawned": 0}
        logger.info("Agent Registry 初始化完成")

    def register(self, profile: AgentProfile) -> bool:
        with self._lock:
            if profile.agent_id in self._profiles:
                return False
            profile.state = AgentState.REGISTERED
            self._profiles[profile.agent_id] = profile
            self._update_indices(profile)
            self._stats["total_registered"] += 1
            logger.info(f"Agent {profile.name} ({profile.agent_id}) 注册成功")
            return True

    def get(self, agent_id: str) -> Optional[AgentProfile]:
        return self._profiles.get(agent_id)

    def get_by_cap(self, cap: str) -> List[AgentProfile]:
        ids = self._cap_index.get(cap, set())
        return [self._profiles[i] for i in ids if i in self._profiles]

    def get_available(self, caps: List[str] = None) -> List[AgentProfile]:
        available = []
        for p in self._profiles.values():
            if p.state == AgentState.IDLE:
                if caps is None or any(c in p.capabilities for c in caps):
                    available.append(p)
        return available

    def spawn(self, agent_id: str, ctx: Dict[str, Any] = None) -> Optional[AgentInstance]:
        with self._lock:
            profile = self._profiles.get(agent_id)
            if not profile:
                return None
            inst_id = f"{agent_id}_{uuid.uuid4().hex[:8]}"
            inst = AgentInstance(instance_id=inst_id, profile=profile, context=ctx or {},
                                state=AgentState.IDLE, stats={"ok": 0, "fail": 0})
            self._instances[inst_id] = inst
            self._stats["total_spawned"] += 1
            logger.info(f"Spawned: {inst_id}")
            return inst

    def assign(self, inst_id: str, task_id: str) -> bool:
        inst = self._instances.get(inst_id)
        if inst:
            inst.current_task = task_id
            inst.state = AgentState.RUNNING
            inst.last_active = datetime.now()
            return True
        return False

    def complete(self, inst_id: str, result: Any = None):
        if inst_id in self._instances:
            inst = self._instances[inst_id]
            inst.state = AgentState.IDLE
            inst.current_task = None
            inst.stats["ok"] += 1
            inst.last_active = datetime.now()

    def _update_indices(self, profile: AgentProfile):
        if profile.agent_type not in self._type_index:
            self._type_index[profile.agent_type] = set()
        self._type_index[profile.agent_type].add(profile.agent_id)
        for cap in profile.capabilities:
            if cap not in self._cap_index:
                self._cap_index[cap] = set()
            self._cap_index[cap].add(profile.agent_id)

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats, "profiles": len(self._profiles), "instances": len(self._instances)}

    def list_all(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self._profiles.values()]


class AgentSpawner:
    """Agent Spawner"""
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._executors: Dict[str, Callable] = {}
        logger.info("Agent Spawner 初始化完成")

    def register_executor(self, agent_type: str, executor: Callable):
        self._executors[agent_type] = executor
        logger.info(f"注册执行器: {agent_type}")

    async def spawn_and_execute(self, agent_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        instance = self.registry.spawn(agent_id)
        if not instance:
            return {"success": False, "error": f"无法spawn {agent_id}"}
        self.registry.assign(instance.instance_id, task_data.get("task_id", ""))
        try:
            executor = self._executors.get(instance.profile.agent_type.value)
            if executor:
                result = await executor(instance, task_data)
            else:
                result = await self._default_execute(instance, task_data)
            self.registry.complete(instance.instance_id, result)
            return {"success": True, "instance_id": instance.instance_id, "result": result}
        except Exception as e:
            logger.error(f"执行失败: {instance.instance_id} - {e}")
            return {"success": False, "error": str(e)}

    async def _default_execute(self, instance: AgentInstance, task_data: Dict[str, Any]) -> Dict[str, Any]:
        return {"executed": True, "agent": instance.profile.name, "task": task_data.get("description", ""),
                "caps": instance.profile.capabilities[:3], "ts": datetime.now().isoformat()}


# 全局实例
_registry: Optional[AgentRegistry] = None
_spawner: Optional[AgentSpawner] = None


def get_agent_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry


def get_agent_spawner() -> AgentSpawner:
    global _spawner
    if _spawner is None:
        _spawner = AgentSpawner(get_agent_registry())
    return _spawner
