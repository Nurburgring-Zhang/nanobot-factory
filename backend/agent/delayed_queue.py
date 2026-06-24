"""
NanoBot Factory - Delayed Queue & Dead Letter Queue
延迟队列与死信处理

@author MiniMax Agent
@date 2026-04-11
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import heapq
import threading

logger = logging.getLogger(__name__)


class DLQReason(Enum):
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    PROCESSING_TIMEOUT = "processing_timeout"
    INVALID_MESSAGE = "invalid_message"
    CONSUMER_ERROR = "consumer_error"
    EXPIRED = "expired"


@dataclass
class RetryPolicy:
    max_retries: int = 3
    initial_delay_ms: int = 1000
    backoff_multiplier: float = 2.0
    
    def get_delay(self, attempt: int) -> float:
        delay = self.initial_delay_ms * (self.backoff_multiplier ** attempt)
        return min(delay, 60000) / 1000.0


@dataclass
class MessageEnvelope:
    id: str
    content: Any
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    headers: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def is_ready(self) -> bool:
        if self.scheduled_at is None:
            return True
        return datetime.now() >= self.scheduled_at
    
    def should_retry(self) -> bool:
        return self.retry_count < self.max_retries


@dataclass
class DLQEntry:
    message: MessageEnvelope
    reason: DLQReason
    failed_at: datetime = field(default_factory=datetime.now)
    consumer_name: Optional[str] = None
    error: Optional[str] = None


class DelayedQueue:
    """延迟队列 - 基于堆的定时消息投递"""
    
    def __init__(self, name: str = "default", default_delay_ms: int = 1000, max_size: int = 100000):
        self.name = name
        self.default_delay_ms = default_delay_ms
        self.max_size = max_size
        self._delayed_heap: List[tuple] = []
        self._message_index: Dict[str, MessageEnvelope] = {}
        self._stats = {"scheduled": 0, "delivered": 0, "expired": 0}
        self._lock = threading.RLock()
        self._closed = False
        logger.info(f"DelayedQueue '{name}' initialized")
    
    def schedule(self, content: Any, delay_ms: Optional[int] = None, message_id: Optional[str] = None,
                 headers: Optional[Dict] = None, metadata: Optional[Dict] = None) -> str:
        if self._closed:
            raise RuntimeError("Queue is closed")
        
        msg_id = message_id or str(uuid.uuid4())
        delay = delay_ms if delay_ms is not None else self.default_delay_ms
        
        message = MessageEnvelope(
            id=msg_id, content=content,
            scheduled_at=datetime.now() + timedelta(milliseconds=delay),
            headers=headers or {}, metadata=metadata or {}
        )
        
        with self._lock:
            if len(self._message_index) >= self.max_size:
                raise RuntimeError(f"Queue '{self.name}' is full")
            
            self._message_index[msg_id] = message
            heapq.heappush(self._delayed_heap, (message.scheduled_at, msg_id, message))
            self._stats["scheduled"] += 1
        
        logger.debug(f"Message scheduled: {msg_id}")
        return msg_id
    
    def cancel(self, message_id: str) -> bool:
        with self._lock:
            if message_id in self._message_index:
                del self._message_index[message_id]
                return True
        return False
    
    def get_ready_messages(self) -> List[MessageEnvelope]:
        ready = []
        now = datetime.now()
        
        with self._lock:
            while self._delayed_heap:
                scheduled_time, msg_id, message = self._delayed_heap[0]
                
                if message.id not in self._message_index:
                    heapq.heappop(self._delayed_heap)
                    continue
                
                if scheduled_time <= now:
                    ready.append(message)
                    heapq.heappop(self._delayed_heap)
                else:
                    break
        
        return ready
    
    def get_pending_count(self) -> int:
        with self._lock:
            return len(self._message_index)
    
    def close(self) -> None:
        self._closed = True
        with self._lock:
            self._delayed_heap.clear()
            self._message_index.clear()
        logger.info(f"DelayedQueue '{self.name}' closed")


class DeadLetterQueue:
    """死信队列 - 存储处理失败的消息"""
    
    def __init__(self, name: str = "default", max_size: int = 10000):
        self.name = name
        self.max_size = max_size
        self._entries: List[DLQEntry] = []
        self._stats = {"total": 0}
        self._lock = threading.RLock()
        self._closed = False
        logger.info(f"DeadLetterQueue '{name}' initialized")
    
    def add(self, message: MessageEnvelope, reason: DLQReason,
            consumer_name: Optional[str] = None, error: Optional[str] = None) -> str:
        if self._closed:
            raise RuntimeError("DLQ is closed")
        
        entry = DLQEntry(message=message, reason=reason,
consumer_name=consumer_name, error=error)
        
        with self._lock:
            if len(self._entries) >= self.max_size:
                self._entries.pop(0)
            
            entry_id = len(self._entries)
            self._entries.append(entry)
            self._stats["total"] += 1
        
        logger.warning(f"Message {message.id} added to DLQ: {reason.value}")
        return str(entry_id)
    
    def get_entries(self, limit: int = 100) -> List[DLQEntry]:
        with self._lock:
            return self._entries[-limit:]
    
    def replay(self, index: int, target_queue: DelayedQueue) -> bool:
        with self._lock:
            if 0 <= index < len(self._entries):
                entry = self._entries[index]
                target_queue.schedule(entry.message.content)
                self._stats["total"] -= 1
                return True
        return False
    
    def analyze(self) -> Dict[str, Any]:
        with self._lock:
            reason_dist = defaultdict(int)
            for entry in self._entries:
                reason_dist[entry.reason.value] += 1
            return {"total": len(self._entries), "reason_distribution": dict(reason_dist)}
    
    def close(self) -> None:
        self._closed = True
        self._entries.clear()
        logger.info(f"DeadLetterQueue '{self.name}' closed")


class RetryManager:
    """重试管理器"""
    
    def __init__(self, delayed_queue: DelayedQueue, dlq: DeadLetterQueue,
                 retry_policy: Optional[RetryPolicy] = None):
        self.delayed_queue = delayed_queue
        self.dlq = dlq
        self.retry_policy = retry_policy or RetryPolicy()
        self._handlers: Dict[str, Callable] = {}
        logger.info("RetryManager initialized")
    
    def register_handler(self, topic: str, handler: Callable) -> None:
        self._handlers[topic] = handler
    
    async def process_with_retry(self, message: MessageEnvelope, handler: Callable, topic: str) -> bool:
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(message.content)
            else:
                result = handler(message.content)
            
            if result:
                return True
            raise Exception("Handler returned False")
        except Exception as e:
            return await self._handle_failure(message, topic, str(e))
    
    async def _handle_failure(self, message: MessageEnvelope, topic: str, error: str) -> bool:
        message.retry_count += 1
        message.last_error = error
        
        if message.should_retry():
            delay = self.retry_policy.get_delay(message.retry_count - 1)
            self.delayed_queue.schedule(
                content=message.content,
                delay_ms=int(delay * 1000),
                metadata={**message.metadata, "retry_count": message.retry_count, "topic": topic}
            )
            logger.info(f"Scheduled retry {message.retry_count} for {message.id}")
            return True
        else:
            self.dlq.add(message, DLQReason.MAX_RETRIES_EXCEEDED, consumer_name=topic, error=error)
            logger.error(f"Message {message.id} moved to DLQ after {message.retry_count} retries")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        return {
            "delayed_queue_pending": self.delayed_queue.get_pending_count(),
            "dlq_total": self.dlq._stats["total"],
            "handlers": list(self._handlers.keys())
        }


__all__ = ['DelayedQueue', 'DeadLetterQueue', 'RetryManager', 'RetryPolicy', 'MessageEnvelope', 'DLQEntry', 'DLQReason']
