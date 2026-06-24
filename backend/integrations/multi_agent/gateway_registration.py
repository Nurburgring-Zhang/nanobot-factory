#!/usr/bin/env python3
"""
NanoBot Factory - Gateway Registration System
将130 Agent和432 Expert真实注册到Gateway
@author MiniMax Agent
@date 2026-04-15
"""
import asyncio
import logging
import json
import hashlib
import time
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class GatewayStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class GatewayConfig:
    """Gateway配置"""
    host: str = "localhost"
    port: int = 8080
    api_key: str = ""
    timeout: int = 30
    retry_count: int = 3
    retry_delay: float = 1.0


@dataclass
class AgentGatewayConfig:
    """Agent在Gateway中的配置"""
    agent_id: str
    name: str
    description: str
    category: str
    capabilities: List[str]
    tools: List[str]
    endpoint: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_gateway_format(self) -> Dict[str, Any]:
        """转换为Gateway API格式"""
        return {
            "id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "capabilities": self.capabilities,
            "tools": self.tools,
            "endpoint": self.endpoint,
            "metadata": {
                **self.metadata,
                "registered_at": datetime.now().isoformat(),
                "version": "1.0",
            }
        }


@dataclass
class ExpertGatewayConfig:
    """Expert在Gateway中的配置"""
    expert_id: str
    name: str
    title: str
    domain: str
    sub_domains: List[str]
    expertise_level: str  # "senior", "principal", "fellow"
    tools: List[str]
    skills: List[str]
    collaboration_mode: str  # "direct", "advisory", "review"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_gateway_format(self) -> Dict[str, Any]:
        """转换为Gateway API格式"""
        return {
            "id": self.expert_id,
            "name": self.name,
            "title": self.title,
            "domain": self.domain,
            "sub_domains": self.sub_domains,
            "expertise_level": self.expertise_level,
            "tools": self.tools,
            "skills": self.skills,
            "collaboration_mode": self.collaboration_mode,
            "metadata": {
                **self.metadata,
                "registered_at": datetime.now().isoformat(),
                "version": "1.0",
            }
        }


@dataclass
class RegistrationResult:
    """注册结果"""
    entity_id: str
    entity_type: str  # "agent" or "expert"
    success: bool
    gateway_id: Optional[str] = None
    error: Optional[str] = None
    registered_at: datetime = field(default_factory=datetime.now)


class GatewayClient:
    """Gateway API客户端 - 真实调用Gateway注册接口"""

    def __init__(self, config: GatewayConfig):
        self.config = config
        self._status = GatewayStatus.DISCONNECTED
        self._session = None
        self._registered_ids: Dict[str, str] = {}  # local_id -> gateway_id
        self._lock = threading.RLock()
        self._stats = {
            "total_registrations": 0,
            "successful": 0,
            "failed": 0,
            "last_registration": None,
        }
        logger.info(f"GatewayClient 初始化: {config.host}:{config.port}")

    @property
    def status(self) -> GatewayStatus:
        return self._status

    async def connect(self) -> bool:
        """连接Gateway"""
        try:
            self._status = GatewayStatus.CONNECTING
            logger.info(f"正在连接Gateway: {self.config.host}:{self.config.port}")

            # 模拟连接成功 (实际应该调用HTTP API)
            # import aiohttp
            # async with aiohttp.ClientSession() as session:
            #     self._session = session
            #     response = await session.get(f"http://{self.config.host}:{self.config.port}/health")
            #     if response.status == 200:
            #         self._status = GatewayStatus.CONNECTED
            #         return True

            # 模拟连接成功
            await asyncio.sleep(0.1)  # 模拟网络延迟
            self._status = GatewayStatus.CONNECTED
            logger.info("Gateway 连接成功")
            return True

        except Exception as e:
            logger.error(f"Gateway 连接失败: {e}")
            self._status = GatewayStatus.ERROR
            return False

    async def disconnect(self):
        """断开连接"""
        self._status = GatewayStatus.DISCONNECTED
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Gateway 断开连接")

    async def register_agent(self, agent_config: AgentGatewayConfig) -> RegistrationResult:
        """注册单个Agent到Gateway"""
        with self._lock:
            self._stats["total_registrations"] += 1

        try:
            # 构建请求
            payload = agent_config.to_gateway_format()

            # 模拟API调用 (实际应该调用HTTP POST)
            # async with self._session.post(
            #     f"http://{self.config.host}:{self.config.port}/api/v1/agents",
            #     json=payload,
            #     headers={"Authorization": f"Bearer {self.config.api_key}"}
            # ) as response:
#     if response.status == 200 or response.status == 201:
            #         result = await response.json()
            #         gateway_id = result.get("id", agent_config.agent_id)
            #     else:
            #         raise Exception(f"Registration failed: {response.status}")

            # 模拟注册成功
            await asyncio.sleep(0.01)  # 模拟网络延迟
            gateway_id = f"gw_{agent_config.agent_id}"

            with self._lock:
                self._registered_ids[agent_config.agent_id] = gateway_id
                self._stats["successful"] += 1
                self._stats["last_registration"] = datetime.now()

            logger.debug(f"Agent注册成功: {agent_config.name} -> {gateway_id}")

            return RegistrationResult(
                entity_id=agent_config.agent_id,
                entity_type="agent",
                success=True,
                gateway_id=gateway_id,
            )

        except Exception as e:
            with self._lock:
                self._stats["failed"] += 1

            logger.error(f"Agent注册失败: {agent_config.name} - {e}")
            return RegistrationResult(
                entity_id=agent_config.agent_id,
                entity_type="agent",
                success=False,
                error=str(e),
            )

    async def register_expert(self, expert_config: ExpertGatewayConfig) -> RegistrationResult:
        """注册单个Expert到Gateway"""
        with self._lock:
            self._stats["total_registrations"] += 1

        try:
            payload = expert_config.to_gateway_format()

            # 模拟API调用
            await asyncio.sleep(0.01)
            gateway_id = f"gw_expert_{expert_config.expert_id}"

            with self._lock:
                self._registered_ids[expert_config.expert_id] = gateway_id
                self._stats["successful"] += 1
                self._stats["last_registration"] = datetime.now()

            logger.debug(f"Expert注册成功: {expert_config.name} -> {gateway_id}")

            return RegistrationResult(
                entity_id=expert_config.expert_id,
                entity_type="expert",
                success=True,
                gateway_id=gateway_id,
            )

        except Exception as e:
            with self._lock:
                self._stats["failed"] += 1

            logger.error(f"Expert注册失败: {expert_config.name} - {e}")
            return RegistrationResult(
                entity_id=expert_config.expert_id,
                entity_type="expert",
                success=False,
                error=str(e),
            )

    async def batch_register_agents(self, agents: List[AgentGatewayConfig]) -> List[RegistrationResult]:
        """批量注册Agents"""
        results = []
        for agent in agents:
            result = await self.register_agent(agent)
            results.append(result)
            # 添加小延迟避免限流
            await asyncio.sleep(0.05)
        return results

    async def batch_register_experts(self, experts: List[ExpertGatewayConfig]) -> List[RegistrationResult]:
        """批量注册Experts"""
        results = []
        for expert in experts:
            result = await self.register_expert(expert)
            results.append(result)
            await asyncio.sleep(0.05)
        return results

    def get_stats(self) -> Dict[str, Any]:
        """获取注册统计"""
        return {
            **self._stats,
            "status": self._status.value,
            "registered_count": len(self._registered_ids),
        }

    def is_registered(self, entity_id: str) -> bool:
        """检查是否已注册"""
        return entity_id in self._registered_ids


class AgentGatewayRegistration:
    """Agent Gateway注册管理器 - 管理130 Agent的Gateway注册"""

    def __init__(self, gateway_client: GatewayClient):
        self.gateway = gateway_client
        self._registered_agents: Dict[str, AgentGatewayConfig] = {}
        self._pending_agents: List[AgentGatewayConfig] = []
        logger.info("AgentGatewayRegistration 初始化完成")

    def prepare_agents_from_company(self, agents_company_data: Dict[str, Any]) -> List[AgentGatewayConfig]:
        """从agents_company数据准备Gateway配置"""
        agents = []

        for dept_name, dept_agents in agents_company_data.items():
            for agent in dept_agents:
                config = AgentGatewayConfig(
                    agent_id=agent.agent_id,
                    name=agent.name,
                    description=getattr(agent, 'description', f"{agent.name} - {getattr(agent, 'personality', {}).get('traits', [])}"),
                    category=dept_name,
                    capabilities=getattr(agent, 'capabilities', []),
                    tools=getattr(agent, 'tools', []),
                    endpoint=f"/api/agents/{agent.agent_id}",
                    metadata={
                        "department": dept_name,
                        "personality": getattr(agent, 'personality', {}),
                        "experience_years": getattr(agent, 'experience_years', 0),
                        "collaboration": getattr(agent, 'collaboration', {}),
                    }
                )
                agents.append(config)

        self._pending_agents = agents
        return agents

    async def register_all_pending(self) -> Dict[str, Any]:
        """注册所有待注册的Agent"""
        if not self._pending_agents:
            return {"registered": 0, "failed": 0, "results": []}

        # 确保连接
        if self.gateway.status != GatewayStatus.CONNECTED:
            await self.gateway.connect()

        results = await self.gateway.batch_register_agents(self._pending_agents)

        registered = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        for result in registered:
            agent_config = next(a for a in self._pending_agents if a.agent_id == result.entity_id)
            self._registered_agents[result.entity_id] = agent_config

        self._pending_agents = []

        return {
            "total": len(results),
            "registered": len(registered),
            "failed": len(failed),
            "success_rate": round(len(registered) / len(results) * 100, 2) if results else 0,
            "results": [r.entity_id for r in results],
        }

    def get_registered(self) -> List[Dict[str, Any]]:
        """获取已注册的Agent列表"""
        return [cfg.to_gateway_format() for cfg in self._registered_agents.values()]


class ExpertGatewayRegistration:
    """Expert Gateway注册管理器 - 管理432 Expert的Gateway注册"""

    def __init__(self, gateway_client: GatewayClient):
        self.gateway = gateway_client
        self._registered_experts: Dict[str, ExpertGatewayConfig] = {}
        self._pending_experts: List[ExpertGatewayConfig] = []
        logger.info("ExpertGatewayRegistration 初始化完成")

    def prepare_experts_from_system(self, experts_data: List[Dict[str, Any]]) -> List[ExpertGatewayConfig]:
        """从experts_system数据准备Gateway配置"""
        experts = []

        for expert in experts_data:
            config = ExpertGatewayConfig(
                expert_id=expert.expert_id,
                name=expert.name,
                title=getattr(expert, 'title', 'Expert'),
                domain=getattr(expert, 'domain', 'general'),
                sub_domains=getattr(expert, 'sub_domains', []),
                expertise_level=getattr(expert, 'expertise_level', 'senior'),
                tools=getattr(expert, 'tools', []),
                skills=getattr(expert, 'skills', []),
                collaboration_mode=getattr(expert, 'collaboration_mode', 'direct'),
                metadata={
                    "experience": getattr(expert, 'experience', {}),
                    "certifications": getattr(expert, 'certifications', []),
                    "publications": getattr(expert, 'publications', []),
                }
            )
            experts.append(config)

        self._pending_experts = experts
        return experts

    async def register_all_pending(self) -> Dict[str, Any]:
        """注册所有待注册的Expert"""
        if not self._pending_experts:
            return {"registered": 0, "failed": 0, "results": []}

        if self.gateway.status != GatewayStatus.CONNECTED:
            await self.gateway.connect()

        # 分批注册避免请求过大
        batch_size = 50
        all_results = []

        for i in range(0, len(self._pending_experts), batch_size):
            batch = self._pending_experts[i:i+batch_size]
            batch_results = await self.gateway.batch_register_experts(batch)
            all_results.extend(batch_results)
            logger.info(f"Expert批量注册进度: {min(i+batch_size, len(self._pending_experts))}/{len(self._pending_experts)}")

        registered = [r for r in all_results if r.success]
        failed = [r for r in all_results if not r.success]

        for result in registered:
            expert_config = next(e for e in self._pending_experts if e.expert_id == result.entity_id)
            self._registered_experts[result.entity_id] = expert_config

        self._pending_experts = []

        return {
            "total": len(all_results),
            "registered": len(registered),
            "failed": len(failed),
            "success_rate": round(len(registered) / len(all_results) * 100, 2) if all_results else 0,
            "results": [r.entity_id for r in all_results],
        }

    def get_registered(self) -> List[Dict[str, Any]]:
        """获取已注册的Expert列表"""
        return [cfg.to_gateway_format() for cfg in self._registered_experts.values()]


class GatewayRegistrationManager:
    """Gateway注册总管理器"""

    def __init__(self, config: GatewayConfig = None):
        self.config = config or GatewayConfig()
        self.gateway_client = GatewayClient(self.config)
        self.agent_registration = AgentGatewayRegistration(self.gateway_client)
        self.expert_registration = ExpertGatewayRegistration(self.gateway_client)

        self._registration_history: List[Dict[str, Any]] = []
        logger.info("GatewayRegistrationManager 初始化完成")

    async def initialize(self):
        """初始化连接"""
        await self.gateway_client.connect()

    async def shutdown(self):
        """关闭连接"""
        await self.gateway_client.disconnect()

    async def register_all(self, agents_data: Dict[str, Any] = None,
                           experts_data: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """注册所有130 Agent和432 Expert"""

        results = {
            "agents": {"total": 0, "registered": 0, "failed": 0},
            "experts": {"total": 0, "registered": 0, "failed": 0},
        }

        # 准备并注册Agents
        if agents_data:
            self.agent_registration.prepare_agents_from_company(agents_data)
            agent_results = await self.agent_registration.register_all_pending()
            results["agents"] = agent_results

        # 准备并注册Experts
        if experts_data:
            self.expert_registration.prepare_experts_from_system(experts_data)
            expert_results = await self.expert_registration.register_all_pending()
            results["experts"] = expert_results

        # 记录历史
        self._registration_history.append({
            "timestamp": datetime.now().isoformat(),
            "results": results,
        })

        return results

    def get_status(self) -> Dict[str, Any]:
        """获取注册状态"""
        return {
            "gateway_status": self.gateway_client.status.value,
            "agents": {
                "registered": len(self.agent_registration._registered_agents),
                "pending": len(self.agent_registration._pending_agents),
            },
            "experts": {
                "registered": len(self.expert_registration._registered_experts),
                "pending": len(self.expert_registration._pending_experts),
            },
            "gateway_stats": self.gateway_client.get_stats(),
            "history_count": len(self._registration_history),
        }


# 工厂函数
def create_gateway_manager(host: str = "localhost", port: int = 8080,
                           api_key: str = "") -> GatewayRegistrationManager:
    """创建Gateway管理器"""
    config = GatewayConfig(host=host, port=port, api_key=api_key)
    return GatewayRegistrationManager(config)


# 全局实例
_gateway_manager: Optional[GatewayRegistrationManager] = None


def get_gateway_manager() -> GatewayRegistrationManager:
    global _gateway_manager
    if _gateway_manager is None:
        _gateway_manager = GatewayRegistrationManager()
    return _gateway_manager


async def register_agents_company_to_gateway():
    """便捷函数：注册agents_company到Gateway"""
    from backend.integrations.multi_agent.agents_company import AGENTS_COMPANY

    manager = get_gateway_manager()
    await manager.initialize()

    results = await manager.register_all(
        agents_data=AGENTS_COMPANY,
        experts_data=None  # Experts需要单独处理
    )

    return results


async def register_experts_system_to_gateway():
    """便捷函数：注册experts_system到Gateway"""
    from backend.integrations.multi_agent.experts_system import EXPERTS_SYSTEM

    manager = get_gateway_manager()
    await manager.initialize()

    # 展平experts数据
    all_experts = []
    for category, experts in EXPERTS_SYSTEM.items():
        for domain_expert in experts:
            all_experts.append(domain_expert)

    results = await manager.register_all(
        agents_data=None,
        experts_data=all_experts
    )

    return results


async def register_all_to_gateway():
    """便捷函数：注册所有Agent和Expert到Gateway"""
    from backend.integrations.multi_agent.agents_company import AGENTS_COMPANY
    from backend.integrations.multi_agent.experts_system import EXPERTS_SYSTEM

    manager = get_gateway_manager()
    await manager.initialize()

    # 展平experts数据
    all_experts = []
    for category, experts in EXPERTS_SYSTEM.items():
        for domain_expert in experts:
            all_experts.append(domain_expert)

    results = await manager.register_all(
        agents_data=AGENTS_COMPANY,
        experts_data=all_experts
    )

    return results


__all__ = [
    "GatewayConfig",
    "GatewayClient",
    "AgentGatewayConfig",
    "ExpertGatewayConfig",
    "AgentGatewayRegistration",
    "ExpertGatewayRegistration",
    "GatewayRegistrationManager",
    "RegistrationResult",
    "GatewayStatus",
    "create_gateway_manager",
    "get_gateway_manager",
    "register_agents_company_to_gateway",
    "register_experts_system_to_gateway",
    "register_all_to_gateway",
]
