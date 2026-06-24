#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nanobot Factory - Message Bus & Channel Manager
消息总线与通道管理器 - 实现Agent间通信、事件驱动架构

核心功能：
- 消息发布/订阅
- 多通道管理
- 消息持久化
- 优先级队列
- 消息过滤与路由
- 事件驱动支持

@author MiniMax Agent
@date 2026-03-03
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
import uuid
import json
from abc import ABC, abstractmethod
import heapq

logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    """消息优先级"""
    CRITICAL = 0    # 关键消息，最高优先级
    HIGH = 1         # 高优先级
    NORMAL = 2       # 普通优先级
    LOW = 3          # 低优先级
    BULK = 4         # 批量消息，最低优先级


class MessageType(Enum):
    """消息类型"""
    REQUEST = "request"           # 请求消息
    RESPONSE = "response"         # 响应消息
    EVENT = "event"               # 事件消息
    BROADCAST = "broadcast"       # 广播消息
    HEARTBEAT = "heartbeat"       # 心跳消息
    ERROR = "error"               # 错误消息


class ChannelType(Enum):
    """通道类型"""
    DIRECT = "direct"             # 直连通道
    TOPIC = "topic"               # 主题通道
    FANOUT = "fanout"             # 广播通道
    RPC = "rpc"                   # RPC通道


@dataclass
class Message:
    """消息结构"""
    id: str
    type: MessageType
    priority: MessagePriority
    channel: str
    sender: str
    receiver: Optional[str]
    content: Any
    timestamp: datetime = field(default_factory=datetime.now)
    ttl: Optional[int] = None
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    headers: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type.value,
            "priority": self.priority.value,
            "channel": self.channel,
            "sender": self.sender,
            "receiver": self.receiver,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "ttl": self.ttl,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
            "headers": self.headers,
            "metadata": self.metadata,
        }


class MessageFilter(ABC):
    """消息过滤器抽象基类"""

    @abstractmethod
    def matches(self, message: Message) -> bool:
        """检查消息是否匹配过滤器"""
        pass


class HeaderFilter(MessageFilter):
    """基于消息头的过滤器"""

    def __init__(self, headers: Dict[str, Any]):
        self.headers = headers

    def matches(self, message: Message) -> bool:
        for key, value in self.headers.items():
            if key not in message.headers:
                return False
            if message.headers[key] != value:
                return False
        return True


class CompositeFilter(MessageFilter):
    """组合过滤器"""

    def __init__(self, filters: List[MessageFilter], match_all: bool = True):
        self.filters = filters
        self.match_all = match_all

    def matches(self, message: Message) -> bool:
        if self.match_all:
            return all(f.matches(message) for f in self.filters)
        return any(f.matches(message) for f in self.filters)


class PriorityQueue:
    """优先级队列实现"""

    def __init__(self):
        self._heap: List[tuple] = []
        self._lock = asyncio.Lock()

    async def push(self, item: Any, priority: int):
        """添加元素"""
        async with self._lock:
            heapq.heappush(self._heap, (priority, datetime.now(), item))

    async def pop(self) -> Optional[Any]:
        """取出最高优先级元素"""
        async with self._lock:
            if not self._heap:
                return None
            _, _, item = heapq.heappop(self._heap)
            return item

    def __len__(self) -> int:
        return len(self._heap)


class Channel:
    """通道抽象"""

    def __init__(
        self,
        name: str,
        channel_type: ChannelType = ChannelType.TOPIC,
        max_size: int = 1000,
        ttl: Optional[int] = None,
    ):
        self.name = name
        self.channel_type = channel_type
        self.max_size = max_size
        self.ttl = ttl
        self._subscribers: Dict[str, Optional[MessageFilter]] = {}
        self._queue: PriorityQueue = PriorityQueue()
        self._rpc_pending: Dict[str, asyncio.Future] = {}
        self._stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "messages_dropped": 0,
        }

        logger.info(f"Channel created: {name} (type={channel_type.value})")

    async def subscribe(
        self,
        subscriber_id: str,
        filter: Optional[MessageFilter] = None,
    ) -> bool:
        """订阅通道"""
        if subscriber_id in self._subscribers:
            return False

        self._subscribers[subscriber_id] = filter
        logger.info(f"Subscriber {subscriber_id} subscribed to {self.name}")
        return True

    async def unsubscribe(self, subscriber_id: str) -> bool:
        """取消订阅"""
        if subscriber_id not in self._subscribers:
            return False

        del self._subscribers[subscriber_id]
        return True

    def get_subscribers(self) -> List[str]:
        """获取所有订阅者"""
        return list(self._subscribers.keys())

    async def publish(self, message: Message) -> int:
        """发布消息"""
        self._stats["messages_sent"] += 1

        if len(self._queue) >= self.max_size:
            self._stats["messages_dropped"] += 1
            return 0

        await self._queue.push(message, message.priority.value)
        delivered_count = len(self._subscribers)
        self._stats["messages_received"] += delivered_count

        return delivered_count

    async def consume(self, subscriber_id: str) -> Optional[Message]:
        """消费消息"""
        if subscriber_id not in self._subscribers:
            return None

        filter = self._subscribers[subscriber_id]

        while len(self._queue) > 0:
            msg = await self._queue.pop()
            if msg is None:
                break

            if filter is None or filter.matches(msg):
                return msg

        return None

    def get_stats(self) -> Dict[str, Any]:
        """获取通道统计"""
        return {
            **self._stats,
            "queue_size": len(self._queue),
            "subscriber_count": len(self._subscribers),
        }


class ChannelManager:
    """通道管理器"""

    def __init__(self):
        self._channels: Dict[str, Channel] = {}
        self._lock = asyncio.Lock()
        logger.info("ChannelManager initialized")

    async def create_channel(
        self,
        name: str,
        channel_type: ChannelType = ChannelType.TOPIC,
        max_size: int = 1000,
        ttl: Optional[int] = None,
    ) -> Channel:
        """创建通道"""
        async with self._lock:
            if name in self._channels:
                return self._channels[name]

            channel = Channel(name, channel_type, max_size, ttl)
            self._channels[name] = channel
            logger.info(f"Channel created: {name}")
            return channel

    async def get_channel(self, name: str) -> Optional[Channel]:
        """获取通道"""
        return self._channels.get(name)

    async def delete_channel(self, name: str) -> bool:
        """删除通道"""
        async with self._lock:
            if name not in self._channels:
                return False
            del self._channels[name]
            return True

    async def list_channels(self) -> List[str]:
        """列出所有通道"""
        return list(self._channels.keys())

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有通道统计"""
        return {
            name: channel.get_stats()
            for name, channel in self._channels.items()
        }


class MessageBus:
    """
    消息总线

    核心功能：
    - 消息发布/订阅
    - 通道管理
    - 消息路由
    - 死信处理
    """

    def __init__(
        self,
        max_channels: int = 100,
        default_ttl: int = 3600,
    ):
        self.max_channels = max_channels
        self.default_ttl = default_ttl
        self.channel_manager = ChannelManager()
        self._subscriber_callbacks: Dict[str, Dict[str, Callable]] = defaultdict(dict)
        self._message_history: Dict[str, Message] = {}
        self._max_history_size = 10000
        self._dead_letter_queue: PriorityQueue = PriorityQueue()
        self._stats = {
            "total_messages": 0,
            "total_published": 0,
            "total_delivered": 0,
        }
        self._running = False
        self._tasks: List[asyncio.Task] = []

        logger.info("MessageBus initialized")

    async def start(self):
        """启动消息总线"""
        self._running = True
        await self.channel_manager.create_channel("default", ChannelType.TOPIC)
        logger.info("MessageBus started")

    async def stop(self):
        """停止消息总线"""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("MessageBus stopped")

    async def publish(
        self,
        channel: str,
        content: Any,
        sender: str = "system",
        receiver: Optional[str] = None,
        message_type: MessageType = MessageType.EVENT,
        priority: MessagePriority = MessagePriority.NORMAL,
        ttl: Optional[int] = None,
        correlation_id: Optional[str] = None,
        reply_to: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """发布消息"""
        ch = await self.channel_manager.get_channel(channel)
        if ch is None:
            ch = await self.channel_manager.create_channel(channel)

        message = Message(
            id=f"msg_{uuid.uuid4().hex[:12]}",
            type=message_type,
            priority=priority,
            channel=channel,
            sender=sender,
            receiver=receiver,
            content=content,
            ttl=ttl or self.default_ttl,
            correlation_id=correlation_id,
            reply_to=reply_to,
            headers=headers or {},
            metadata=metadata or {},
        )

        self._message_history[message.id] = message
        if len(self._message_history) > self._max_history_size:
            # 删除最老的
            keys = list(self._message_history.keys())[:1000]
            for k in keys:
                del self._message_history[k]

        self._stats["total_messages"] += 1
        self._stats["total_published"] += 1

        delivered = await ch.publish(message)
        self._stats["total_delivered"] += delivered

        await self._trigger_callbacks(channel, message)

        return message.id

    async def subscribe(
        self,
        channel: str,
        subscriber_id: str,
        callback: Optional[Callable] = None,
        filter: Optional[MessageFilter] = None,
    ) -> bool:
        """订阅通道"""
        ch = await self.channel_manager.get_channel(channel)
        if ch is None:
            ch = await self.channel_manager.create_channel(channel)

        success = await ch.subscribe(subscriber_id, filter)
        if success and callback:
            self._subscriber_callbacks[channel][subscriber_id] = callback

        return success

    async def unsubscribe(
        self,
        channel: str,
        subscriber_id: str,
    ) -> bool:
        """取消订阅"""
        ch = await self.channel_manager.get_channel(channel)
        if ch is None:
            return False

        success = await ch.unsubscribe(subscriber_id)

        if subscriber_id in self._subscriber_callbacks.get(channel, {}):
            del self._subscriber_callbacks[channel][subscriber_id]

        return success

    async def consume(
        self,
        channel: str,
        subscriber_id: str,
    ) -> Optional[Message]:
        """消费消息"""
        ch = await self.channel_manager.get_channel(channel)
        if ch is None:
            return None

        return await ch.consume(subscriber_id)

    async def broadcast(
        self,
        content: Any,
        sender: str = "system",
        channel: str = "broadcast",
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> int:
        """广播消息"""
        ch = await self.channel_manager.get_channel(channel)
        if ch is None:
            ch = await self.channel_manager.create_channel(channel, ChannelType.FANOUT)

        message = Message(
            id=f"msg_{uuid.uuid4().hex[:12]}",
            type=MessageType.BROADCAST,
            priority=priority,
            channel=channel,
            sender=sender,
            receiver=None,
            content=content,
        )

        await ch.publish(message)
        return len(ch.get_subscribers())

    async def _trigger_callbacks(self, channel: str, message: Message):
        """触发订阅者回调"""
        callbacks = self._subscriber_callbacks.get(channel, {})
        for subscriber_id, callback in callbacks.items():
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as e:
                logger.error(f"Callback error for {subscriber_id}: {e}")

    def get_message(self, message_id: str) -> Optional[Message]:
        """获取消息"""
        return self._message_history.get(message_id)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "channels": self.channel_manager.get_all_stats(),
            "history_size": len(self._message_history),
        }


def create_message_bus(
    max_channels: int = 100,
    default_ttl: int = 3600,
) -> MessageBus:
    """创建消息总线实例"""
    return MessageBus(
        max_channels=max_channels,
        default_ttl=default_ttl,
    )


async def example_usage():
    """使用示例"""
    bus = create_message_bus()
    await bus.start()

    # 订阅
    async def on_message(message: Message):
        print(f"Received: {message.content}")

    await bus.subscribe("test", "subscriber1", on_message)

    # 发布
    await bus.publish("test", "Hello World!", sender="user1")

    # 等待处理
    await asyncio.sleep(0.5)

    # 广播
    await bus.broadcast("Broadcast message!", sender="admin")

    print(bus.get_stats())

    await bus.stop()


if __name__ == "__main__":
    asyncio.run(example_usage())
