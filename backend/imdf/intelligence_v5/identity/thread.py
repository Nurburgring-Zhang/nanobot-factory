"""智影 V5 — Thread (具体一件事)"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ThreadStatus(str, Enum):
    """Thread 状态"""
    OPEN = "open"            # 开放讨论中
    RESOLVED = "resolved"    # 已解决
    ARCHIVED = "archived"    # 已归档
    SUPERSEDED = "superseded"  # 被替代


@dataclass
class ThreadMessage:
    """Thread 内单条消息"""
    sender_id: str
    sender_type: str  # "user" / "bot"
    content: str
    message_id: str = field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:12]}")
    thread_id: str = ""
    timestamp: float = 0.0

    # 消息元数据
    role: str = "user"  # user/assistant/system/tool
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_call_id: str = ""
    parent_message_id: str = ""

    # 引用/附件
    attachments: List[Dict[str, Any]] = field(default_factory=list)  # file refs
    mentions: List[str] = field(default_factory=list)  # mentioned user/bot ids

    # 编辑
    edited_at: float = 0.0
    reactions: Dict[str, List[str]] = field(default_factory=dict)  # emoji → user_ids

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "sender_type": self.sender_type,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp or time.time(),
            "tool_calls": self.tool_calls,
            "parent_message_id": self.parent_message_id,
            "attachments": self.attachments,
            "mentions": self.mentions,
            "reactions": self.reactions,
        }


@dataclass
class Thread:
    """Thread — 一件具体的事

    Thread 的价值:把一件事的来龙去脉、讨论过程和最终结论留在同一个地方。
    即使消息流继续滚动,Thread 本身不被冲散。
    """

    title: str
    thread_id: str = field(default_factory=lambda: f"thr-{uuid.uuid4().hex[:12]}")
    channel_id: str = ""
    creator_id: str = ""
    status: ThreadStatus = ThreadStatus.OPEN

    # 内容
    summary: str = ""
    messages: List[ThreadMessage] = field(default_factory=list)

    # 关联
    matter_id: str = ""          # 关联的 Matter
    related_thread_ids: List[str] = field(default_factory=list)
    referenced_doc_ids: List[str] = field(default_factory=list)  # 关联的文档/数据

    # 标签
    tags: List[str] = field(default_factory=list)
    priority: str = "medium"  # low/medium/high/urgent

    # 决策/结论
    decision: str = ""
    decision_maker_id: str = ""
    decision_at: float = 0.0

    # 参与
    participants: List[str] = field(default_factory=list)

    # 统计
    view_count: int = 0
    last_activity: float = 0.0

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 时间戳
    created_at: float = 0.0
    updated_at: float = 0.0

    def add_message(
        self,
        sender_id: str,
        content: str,
        sender_type: str = "user",
        role: Optional[str] = None,
        parent_message_id: str = "",
        attachments: Optional[List[Dict[str, Any]]] = None,
        mentions: Optional[List[str]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> ThreadMessage:
        msg = ThreadMessage(
            sender_id=sender_id,
            sender_type=sender_type,
            content=content,
            thread_id=self.thread_id,
            role=role or sender_type,
            parent_message_id=parent_message_id,
            attachments=attachments or [],
            mentions=mentions or [],
            tool_calls=tool_calls or [],
            timestamp=time.time(),
        )
        self.messages.append(msg)
        if sender_id not in self.participants:
            self.participants.append(sender_id)
        self.last_activity = time.time()
        self.updated_at = time.time()
        return msg

    def resolve(self, decision: str, decision_maker_id: str = ""):
        self.status = ThreadStatus.RESOLVED
        self.decision = decision
        self.decision_maker_id = decision_maker_id
        self.decision_at = time.time()
        self.updated_at = time.time()

    def archive(self):
        self.status = ThreadStatus.ARCHIVED
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "channel_id": self.channel_id,
            "title": self.title,
            "status": self.status.value,
            "summary": self.summary,
            "matter_id": self.matter_id,
            "tags": self.tags,
            "priority": self.priority,
            "decision": self.decision,
            "decision_maker_id": self.decision_maker_id,
            "decision_at": self.decision_at,
            "participants": self.participants,
            "message_count": len(self.messages),
            "view_count": self.view_count,
            "last_activity": self.last_activity,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
        }
