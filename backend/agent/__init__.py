#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nanobot Factory - Agent Module
Agent模块包 - 包含Agent核心功能组件

模块：
- loop: Agent循环引擎
- context_builder: 上下文构建器
- memory: 增强型记忆系统
- message_bus: 消息总线与通道管理
- model_router: 模型路由器与提供者注册
- security_guard: 虚拟工具安全守卫
- timeout_manager: 统一超时管理器
- cluster_manager: Agent集群管理系统
- orchestration: Agent编排系统

@author MiniMax Agent
@date 2026-03-08
"""

from .loop import AgentLoopEngine, create_agent_loop, VirtualTool
from .context_builder import ContextBuilder, create_context_builder, DynamicPromptBuilder
from .memory import EnhancedMemorySystem, create_memory_system, Memory, MemoryType, ImportanceLevel
from .message_bus import MessageBus, create_message_bus, Channel, Message, MessageType, MessagePriority
from .model_router import ModelRouter, create_model_router, ModelProvider, BaseModelProvider
from .security_guard import VirtualToolSecurityGuard, create_security_guard, SecurityLevel
from .timeout_manager import UnifiedTimeoutManager, create_timeout_manager, TimeoutStrategy, TimeoutLevel
from .cluster_manager import (
    AgentCluster, 
    AgentClusterManager, 
    SubAgentCaller,
    SubAgent,
    AgentRole,
    AgentStatus,
    TaskPriority,
    create_cluster_manager,
    create_sub_agent_caller,
    create_sub_agent
)
from .orchestration import (
    AgentOrchestrator,
    OrchestrationPattern,
    OrchestrationStep,
    OrchestrationWorkflow,
    WorkflowTemplates,
    create_orchestrator
)

__all__ = [
    # Loop
    "AgentLoopEngine",
    "create_agent_loop",
    "VirtualTool",
    # Context Builder
    "ContextBuilder",
    "create_context_builder",
    "DynamicPromptBuilder",
    # Memory
    "EnhancedMemorySystem",
    "create_memory_system",
    "Memory",
    "MemoryType",
    "ImportanceLevel",
    # Message Bus
    "MessageBus",
    "create_message_bus",
    "Channel",
    "Message",
    "MessageType",
    "MessagePriority",
    # Model Router
    "ModelRouter",
    "create_model_router",
    "ModelProvider",
    "BaseModelProvider",
    # Security Guard
    "VirtualToolSecurityGuard",
    "create_security_guard",
    "SecurityLevel",
    # Timeout Manager
    "UnifiedTimeoutManager",
    "create_timeout_manager",
    "TimeoutStrategy",
    "TimeoutLevel",
    # Cluster Manager
    "AgentCluster",
    "AgentClusterManager",
    "SubAgentCaller",
    "SubAgent",
    "AgentRole",
    "AgentStatus",
    "TaskPriority",
    "create_cluster_manager",
    "create_sub_agent_caller",
    "create_sub_agent",
    # Orchestration
    "AgentOrchestrator",
    "OrchestrationPattern",
    "OrchestrationStep",
    "OrchestrationWorkflow",
    "WorkflowTemplates",
    "create_orchestrator",
]

# 新增模块导出 (2026-04-13)
try:
    from .dispatcher import (
        DispatcherAgent,
        ExpertAgentProfile,
        DispatchTask,
        DispatchResult,
        TaskDomain,
        TaskIntentAnalyzer,
        DispatchStrategy,
        create_dispatcher,
    )
    from .context_compressor import (
        ContextCompressor,
        ContextMessage,
        CompressionConfig,
        CompressionResult,
        MessageRole,
        MessageImportance,
        create_context_compressor,
    )
    from .self_evolution import (
        SelfEvolutionSystem,
        ExecutionRecord,
        PerformanceMetrics,
        ImprovementSuggestion,
        create_evolution_system,
    )
    from .react_engine import (
        AgentLoopEngine as ReactLoopEngine,
        ToolExecutor,
        LoopConfig,
        LoopResult,
        create_react_engine,
    )
    _NEW_MODULES_LOADED = True
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Some new agent modules could not be loaded: {e}")
    _NEW_MODULES_LOADED = False
