"""智影 V5 — Channel (项目群/工作频道)"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ChannelType(str, Enum):
    """Channel 类型"""
    PROJECT = "project"           # 项目群
    WORK = "work"                 # 工作频道
    TEAM = "team"                 # 团队
    TOPIC = "topic"               # 主题讨论
    INBOX = "inbox"               # 收件箱
    ANNOUNCEMENT = "announcement"  # 公告
    DIRECT = "direct"             # 1:1 私聊


@dataclass
class ChannelMember:
    """Channel 成员 — 可能是用户或 Bot"""
    member_id: str  # user id or bot id
    member_type: str  # "user" | "bot"
    role: str = "member"  # owner / admin / member / guest
    joined_at: float = 0.0
    last_read_at: float = 0.0
    notification_enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Channel:
    """Channel — 项目群/工作频道

    Channel 解决"在哪里协作"的问题。
    人和 Bot 在同一个频道里对齐意图、讨论方案、派发任务、看进展。
    """

    name: str
    channel_type: ChannelType = ChannelType.PROJECT
    description: str = ""
    channel_id: str = field(default_factory=lambda: f"ch-{uuid.uuid4().hex[:12]}")

    # 成员
    members: Dict[str, ChannelMember] = field(default_factory=dict)

    # 配置
    is_private: bool = False
    is_archived: bool = False
    pinned_thread_ids: List[str] = field(default_factory=list)

    # 主题标签
    topic: str = ""
    tags: List[str] = field(default_factory=list)

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 统计
    thread_count: int = 0
    message_count: int = 0
    last_activity: float = 0.0

    # 时间戳
    created_at: float = 0.0
    updated_at: float = 0.0

    def add_member(
        self,
        member_id: str,
        member_type: str = "user",
        role: str = "member",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChannelMember:
        if member_id in self.members:
            return self.members[member_id]
        m = ChannelMember(
            member_id=member_id,
            member_type=member_type,
            role=role,
            joined_at=time.time(),
            metadata=metadata or {},
        )
        self.members[member_id] = m
        self.updated_at = time.time()
        logger.info(f"Channel[{self.name}] member added: {member_id} ({member_type}/{role})")
        return m

    def remove_member(self, member_id: str) -> bool:
        if member_id in self.members:
            del self.members[member_id]
            self.updated_at = time.time()
            return True
        return False

    def has_bot(self, bot_id: str) -> bool:
        m = self.members.get(bot_id)
        return m is not None and m.member_type == "bot"

    def list_bots(self) -> List[ChannelMember]:
        return [m for m in self.members.values() if m.member_type == "bot"]

    def list_users(self) -> List[ChannelMember]:
        return [m for m in self.members.values() if m.member_type == "user"]

    def pin_thread(self, thread_id: str):
        if thread_id not in self.pinned_thread_ids:
            self.pinned_thread_ids.append(thread_id)

    def unpin_thread(self, thread_id: str):
        if thread_id in self.pinned_thread_ids:
            self.pinned_thread_ids.remove(thread_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "name": self.name,
            "type": self.channel_type.value,
            "description": self.description,
            "is_private": self.is_private,
            "is_archived": self.is_archived,
            "topic": self.topic,
            "tags": self.tags,
            "member_count": len(self.members),
            "bot_count": len(self.list_bots()),
            "user_count": len(self.list_users()),
            "pinned_threads": self.pinned_thread_ids,
            "thread_count": self.thread_count,
            "message_count": self.message_count,
            "last_activity": self.last_activity,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "members": [
                {
                    "member_id": m.member_id,
                    "type": m.member_type,
                    "role": m.role,
                    "joined_at": m.joined_at,
                }
                for m in self.members.values()
            ],
        }
