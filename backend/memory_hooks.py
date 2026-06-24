#!/usr/bin/env python3
"""
Nanobot Factory - Memory Hooks System
Claude-Mem 5 lifecycle hooks implementation

@author MiniMax Agent
@date 2026-02-25
@description 实现5大生命周期钩子：context-hook, new-hook, save-hook, summary-hook, cleanup-hook
"""

import os
import json
import logging
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class HookType(str, Enum):
    """Memory hook types"""
    CONTEXT = "context"      # 会话启动时注入最近记忆
    NEW = "new"              # 用户提问时创建新会话
    SAVE = "save"            # 工具执行后捕获操作记录
    SUMMARY = "summary"       # 会话结束时生成AI摘要
    CLEANUP = "cleanup"       # 清理临时数据


@dataclass
class Conversation:
    """Represents a conversation/session"""
    id: str
    title: str
    user_id: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    ended_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecution:
    """Represents a tool execution record"""
    id: str
    tool_name: str
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    status: str = "pending"  # pending, success, failed
    error: Optional[str] = None
    execution_time: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class MemoryHooks:
    """
    Claude-Mem 5 lifecycle hooks implementation.
    Provides cross-session memory and long-term task execution.
    """

    def __init__(self, memory_system):
        self.memory_system = memory_system
        self.current_conversation: Optional[Conversation] = None
        self.pending_saves: List[ToolExecution] = []
        self._lock = threading.RLock()

        # Hook callbacks
        self._hooks: Dict[HookType, List[Callable]] = {
            HookType.CONTEXT: [],
            HookType.NEW: [],
            HookType.SAVE: [],
            HookType.SUMMARY: [],
            HookType.CLEANUP: []
        }

    def register_hook(self, hook_type: HookType, callback: Callable):
        """Register a hook callback"""
        self._hooks[hook_type].append(callback)
        logger.info(f"Registered hook: {hook_type.value}")

    def _trigger_hooks(self, hook_type: HookType, *args, **kwargs):
        """Trigger all registered hooks"""
        for callback in self._hooks[hook_type]:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Hook error in {hook_type.value}: {e}")

    # =========================================================================
    # Hook 1: Context Hook - 会话启动时注入最近记忆
    # =========================================================================

    async def context_hook(self, user_query: str = None) -> str:
        """
        Context Hook: 注入会话开始时的上下文记忆

        触发时机：每次新会话开始时
        用途：让Agent了解之前的上下文

        Returns:
            上下文提示词字符串
        """
        logger.info("Triggering context_hook")

        # 获取相关记忆
        context_parts = []

        # 1. 获取最近的重要上下文
        recent_contexts = self.memory_system.get_relevant_context(
            query=user_query,
            limit=3
        )

        if recent_contexts:
            context_parts.append("## Relevant Context")
            for ctx in recent_contexts:
                context_parts.append(f"- {ctx.content}")

        # 2. 获取相关知识
        if user_query:
            knowledge = self.memory_system.get_knowledge(
                query=user_query,
                limit=2
            )
            if knowledge:
                context_parts.append("\n## Relevant Knowledge")
                for kn in knowledge:
                    context_parts.append(f"- {kn.content}")

        # 3. 获取最近历史
        recent_history = self.memory_system.get_history(limit=5)
        if recent_history:
            context_parts.append("\n## Recent History")
            for hist in recent_history:
                context_parts.append(f"- {hist.content}")

        # 构建提示词
        context_prompt = "\n".join(context_parts)

        # 触发钩子
        self._trigger_hooks(HookType.CONTEXT, context_prompt)

        return context_prompt

    # =========================================================================
    # Hook 2: New Hook - 用户提问时创建新会话
    # =========================================================================

    async def new_hook(self, user_id: str, user_query: str) -> str:
        """
        New Hook: 创建新会话记录

        触发时机：用户开始新对话时
        用途：跟踪每个对话的生命周期

        Returns:
            会话ID
        """
        logger.info(f"Triggering new_hook for user: {user_id}")

        # 生成会话ID
        conversation_id = hashlib.md5(
            f"{user_id}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]

        # 创建会话记录
        self.current_conversation = Conversation(
            id=conversation_id,
            title=user_query[:50] if user_query else "New Conversation",
            user_id=user_id,
            messages=[{
                "role": "user",
                "content": user_query,
                "timestamp": datetime.now().isoformat()
            }]
        )

        # 添加到历史记忆
        history_entry = f"Conversation {conversation_id}: User started new session - {user_query[:100]}"
        self.memory_system.add_history(history_entry, metadata={
            "conversation_id": conversation_id,
            "type": "new_session"
        })

        # 触发钩子
        self._trigger_hooks(HookType.NEW, self.current_conversation)

        return conversation_id

    # =========================================================================
    # Hook 3: Save Hook - 工具执行后捕获操作记录
    # =========================================================================

    async def save_hook(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        output_data: Optional[Dict[str, Any]] = None,
        status: str = "success",
        error: Optional[str] = None
    ) -> str:
        """
        Save Hook: 保存工具执行记录

        触发时机：每次工具执行完成后
        用途：记录操作历史，用于后续检索和学习

        Returns:
            记录ID
        """
        logger.info(f"Triggering save_hook for tool: {tool_name}")

        # 创建执行记录
        execution_id = hashlib.md5(
            f"{tool_name}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]

        execution = ToolExecution(
            id=execution_id,
            tool_name=tool_name,
            input_data=input_data,
            output_data=output_data,
            status=status,
            error=error
        )

        # 保存到历史
        with self._lock:
            self.pending_saves.append(execution)

        # 保存到记忆系统
        if status == "success":
            summary = f"Executed {tool_name} with input: {json.dumps(input_data)[:100]}"
            self.memory_system.add_history(summary, metadata={
                "tool_name": tool_name,
                "execution_id": execution_id,
                "type": "tool_execution"
            })

            # 如果是重要操作，添加到上下文
            important_tools = ["generate", "create", "save", "delete", "update"]
            if any(t in tool_name.lower() for t in important_tools):
                self.memory_system.add_context(
                    f"Action: {tool_name} - {json.dumps(input_data)[:200]}",
                    importance=0.7,
                    metadata={
                        "execution_id": execution_id,
                        "conversation_id": self.current_conversation.id if self.current_conversation else None
                    }
                )

        # 触发钩子
        self._trigger_hooks(HookType.SAVE, execution)

        return execution_id

    # =========================================================================
    # Hook 4: Summary Hook - 会话结束时生成AI摘要
    # =========================================================================

    async def summary_hook(self, conversation_id: Optional[str] = None) -> str:
        """
        Summary Hook: 生成会话摘要

        触发时机：会话结束时
        用途：生成会话摘要，保存到知识库

        Returns:
            摘要内容
        """
        logger.info(f"Triggering summary_hook for conversation: {conversation_id}")

        # 收集会话信息
        summary_parts = []

        # 1. 会话标题
        if self.current_conversation:
            summary_parts.append(f"Conversation: {self.current_conversation.title}")

        # 2. 消息数量
        msg_count = len(self.current_conversation.messages) if self.current_conversation else 0
        summary_parts.append(f"Messages: {msg_count}")

        # 3. 执行的操作
        tool_executions = [s for s in self.pending_saves if s.tool_name]
        if tool_executions:
            summary_parts.append("\n## Actions Taken")
            for exec in tool_executions:
                summary_parts.append(f"- {exec.tool_name}: {exec.status}")

        # 4. 生成摘要
        summary = "\n".join(summary_parts)

        # 保存到知识库
        knowledge_id = self.memory_system.add_knowledge(
            summary,
            importance=0.8,
            metadata={
                "conversation_id": conversation_id or (self.current_conversation.id if self.current_conversation else None),
                "type": "conversation_summary",
                "created_at": datetime.now().isoformat()
            }
        )

        # 触发钩子
        self._trigger_hooks(HookType.SUMMARY, summary, knowledge_id)

        logger.info(f"Summary saved: {knowledge_id}")
        return summary

    # =========================================================================
    # Hook 5: Cleanup Hook - 清理临时数据
    # =========================================================================

    async def cleanup_hook(self, conversation_id: Optional[str] = None):
        """
        Cleanup Hook: 清理临时数据

        触发时机：会话结束后清理
        用途：删除临时数据，保留重要记忆

        保留：
        - 知识库内容（高重要性）
        - 操作摘要
        - 标记为重要的上下文

        清理：
        - 临时会话数据
        - 敏感输入数据
        - 过期的缓存
        """
        logger.info(f"Triggering cleanup_hook for conversation: {conversation_id}")

        cleaned_items = []

        # 1. 清理当前会话数据
        if self.current_conversation:
            self.current_conversation.ended_at = datetime.now().isoformat()
            cleaned_items.append(f"Conversation {self.current_conversation.id}")

        # 2. 清理待保存列表
        with self._lock:
            self.pending_saves.clear()
            cleaned_items.append(f"Pending saves: {len(self.pending_saves)}")

        # 3. 清理低优先级历史（可选）
        # 可以根据时间或重要性清理

        # 触发钩子
        self._trigger_hooks(HookType.CLEANUP, cleaned_items)

        logger.info(f"Cleanup completed: {cleaned_items}")
        return cleaned_items

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def add_message(self, role: str, content: str):
        """Add message to current conversation"""
        if self.current_conversation:
            self.current_conversation.messages.append({
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat()
            })
            self.current_conversation.updated_at = datetime.now().isoformat()

    def get_conversation_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get conversation history"""
        if self.current_conversation:
            return self.current_conversation.messages[-limit:]
        return []


class HookManager:
    """
    Hook管理器 - 协调所有生命周期钩子
    """

    def __init__(self, memory_system):
        self.memory_system = memory_system
        self.hooks = MemoryHooks(memory_system)

    async def on_session_start(self, user_id: str, query: str) -> str:
        """处理会话启动"""
        # 1. 创建新会话
        conversation_id = await self.hooks.new_hook(user_id, query)

        # 2. 注入上下文
        context = await self.hooks.context_hook(query)

        return conversation_id

    async def on_tool_execution(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        output_data: Optional[Dict[str, Any]] = None,
        status: str = "success",
        error: Optional[str] = None
    ):
        """处理工具执行"""
        await self.hooks.save_hook(
            tool_name=tool_name,
            input_data=input_data,
            output_data=output_data,
            status=status,
            error=error
        )

    async def on_session_end(self, conversation_id: Optional[str] = None):
        """处理会话结束"""
        # 1. 生成摘要
        summary = await self.hooks.summary_hook(conversation_id)

        # 2. 清理临时数据
        await self.hooks.cleanup_hook(conversation_id)

        return summary


# =========================================================================
# Example Usage
# =========================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    from memory import MemorySystem

    # 初始化
    memory = MemorySystem("./test_hooks.db")
    hook_manager = HookManager(memory)

    # 模拟会话流程
    async def simulate_session():
        # 1. 会话启动
        conv_id = await hook_manager.on_session_start(
            user_id="user123",
            query="帮我生成一些风景图片"
        )
        print(f"Session started: {conv_id}")

        # 获取上下文
        context = await hook_manager.hooks.context_hook("风景图片")
        print(f"\nContext:\n{context}")

        # 2. 工具执行
        await hook_manager.on_tool_execution(
            tool_name="generate_image",
            input_data={"prompt": "风景图片", "count": 5},
            output_data={"images": ["img1.png", "img2.png"]},
            status="success"
        )
        print("\nTool execution saved")

        # 3. 会话结束
        summary = await hook_manager.on_session_end(conv_id)
        print(f"\nSession summary:\n{summary}")

    asyncio.run(simulate_session())

    # 查看统计
    stats = memory.get_statistics()
    print(f"\nMemory stats: {stats}")
