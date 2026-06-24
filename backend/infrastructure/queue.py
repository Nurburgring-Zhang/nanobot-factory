#!/usr/bin/env python3
"""
Nanobot Factory - RabbitMQ 消息队列模块
完整的异步 RabbitMQ 管理，支持任务队列、消息通信

@author MiniMax Agent
@date 2026-03-02
@description 基于 aio-pika 异步驱动的消息队列管理
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import uuid
import hashlib

# RabbitMQ 异步驱动
try:
    import aio_pika
    from aio_pika import Message, DeliveryMode, ExchangeType
    from aio_pika.abc import AbstractIncomingMessage
    import aiocouch
    RABBITMQ_AVAILABLE = True
except ImportError:
    try:
        import pika
        RABBITMQ_AVAILABLE = True
    except ImportError:
        RABBITMQ_AVAILABLE = False
        logging.warning("RabbitMQ 驱动未安装: pip install aio-pika pika")

logger = logging.getLogger(__name__)


# ============================================================================
# 队列和交换机配置
# ============================================================================

class QueueName:
    """队列名称"""
    # 优先级队列
    HIGH_PRIORITY = "nanobot.high_priority"
    NORMAL = "nanobot.normal"
    LOW_PRIORITY = "nanobot.low_priority"

    # 任务队列
    TASK_PROCESSING = "nanobot.task.processing"
    TASK_GENERATION = "nanobot.task.generation"
    TASK_ANALYSIS = "nanobot.task.analysis"

    # 死信队列
    DEAD_LETTER = "nanobot.dead_letter"

    # 事件队列
    EVENT_USER = "nanobot.event.user"
    EVENT_AGENT = "nanobot.event.agent"
    EVENT_SYSTEM = "nanobot.event.system"


class ExchangeName:
    """交换机名称"""
    DIRECT = "nanobot.direct"
    TOPIC = "nanobot.topic"
    FANOUT = "nanobot.fanout"
    HEADERS = "nanobot.headers"


class RoutingKey:
    """路由键"""
    TASK_NEW = "task.new"
    TASK_UPDATE = "task.update"
    TASK_COMPLETE = "task.complete"
    TASK_FAIL = "task.fail"

    AGENT_START = "agent.start"
    AGENT_STOP = "agent.stop"
    AGENT_HEARTBEAT = "agent.heartbeat"

    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"

    SYSTEM_NOTIFICATION = "system.notification"


class TaskPriority(Enum):
    """任务优先级"""
    HIGH = 1
    NORMAL = 5
    LOW = 10


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


@dataclass
class TaskMessage:
    """任务消息"""
    task_id: str
    task_type: str
    payload: Dict[str, Any]
    priority: int = TaskPriority.NORMAL.value
    retry_count: int = 0
    max_retries: int = 3
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: str = ""


@dataclass
class EventMessage:
    """事件消息"""
    event_type: str
    source: str
    data: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    correlation_id: str = ""


# ============================================================================
# RabbitMQ 管理器
# ============================================================================

class RabbitMQManager:
    """
    RabbitMQ 异步管理器
    支持任务队列、消息通信、事件驱动
    """

    def __init__(
        self,
        url: str = None,
        host: str = "localhost",
        port: int = 5672,
        username: str = "guest",
        password: str = "guest",
        virtual_host: str = "/",
        heartbeat: int = 30,
        connection_timeout: int = 10
    ):
        """
        初始化 RabbitMQ 管理器

        Args:
            url: RabbitMQ 连接 URL
            host: 主机地址
            port: 端口
            username: 用户名
            password: 密码
            virtual_host: 虚拟主机
            heartbeat: 心跳间隔
            connection_timeout: 连接超时
        """
        self.url = url or os.getenv(
            "RABBITMQ_URL",
            f"amqp://{username}:{password}@{host}:{port}/{virtual_host}"
        )
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.virtual_host = virtual_host
        self.heartbeat = heartbeat
        self.connection_timeout = connection_timeout

        self._connection = None
        self._channel = None
        self._is_connected = False

        # 交换机
        self._exchanges: Dict[str, any] = {}

        # 队列
        self._queues: Dict[str, any] = {}

        # 消费者
        self._consumers: Dict[str, asyncio.Task] = {}

        # 消息处理器
        self._handlers: Dict[str, Callable] = {}

    async def connect(self):
        """建立 RabbitMQ 连接"""
        if not RABBITMQ_AVAILABLE:
            raise RuntimeError("RabbitMQ 驱动未安装")

        try:
            # 建立连接
            self._connection = await aio_pika.connect_robust(
                self.url,
                heartbeat=self.heartbeat,
                connection_timeout=self.connection_timeout
            )

            # 创建通道
            self._channel = await self._connection.channel()

            # 设置 QoS
            await self._channel.set_qos(prefetch_count=10)

            self._is_connected = True
            logger.info(f"RabbitMQ 连接成功: {self.host}:{self.port}")

            # 初始化交换机和队列
            await self._setup_exchanges()
            await self._setup_queues()
            await self._setup_dead_letter()

        except Exception as e:
            logger.error(f"RabbitMQ 连接失败: {e}")
            raise

    async def disconnect(self):
        """关闭 RabbitMQ 连接"""
        # 取消所有消费者
        for consumer_id, task in self._consumers.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 关闭通道和连接
        if self._channel:
            await self._channel.close()
        if self._connection:
            await self._connection.close()

        self._is_connected = False
        logger.info("RabbitMQ 连接已关闭")

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._is_connected

    async def _setup_exchanges(self):
        """设置交换机"""
        # 直连交换机
        self._exchanges[ExchangeName.DIRECT] = await self._channel.declare_exchange(
            ExchangeName.DIRECT,
            ExchangeType.DIRECT,
            durable=True
        )

        # 主题交换机
        self._exchanges[ExchangeName.TOPIC] = await self._channel.declare_exchange(
            ExchangeName.TOPIC,
            ExchangeType.TOPIC,
            durable=True
        )

        # 广播交换机
        self._exchanges[ExchangeName.FANOUT] = await self._channel.declare_exchange(
            ExchangeName.FANOUT,
            ExchangeType.FANOUT,
            durable=True
        )

        # 头交换机
        self._exchanges[ExchangeName.HEADERS] = await self._channel.declare_exchange(
            ExchangeName.HEADERS,
            ExchangeType.HEADERS,
            durable=True
        )

        logger.info("交换机初始化完成")

    async def _setup_queues(self):
        """设置队列"""
        # 优先级队列
        self._queues[QueueName.HIGH_PRIORITY] = await self._channel.declare_queue(
            QueueName.HIGH_PRIORITY,
            durable=True,
            arguments={
                "x-max-priority": 10,
                "x-message-ttl": 86400000  # 24小时
            }
        )

        self._queues[QueueName.NORMAL] = await self._channel.declare_queue(
            QueueName.NORMAL,
            durable=True,
            arguments={
                "x-message-ttl": 86400000
            }
        )

        self._queues[QueueName.LOW_PRIORITY] = await self._channel.declare_queue(
            QueueName.LOW_PRIORITY,
            durable=True,
            arguments={
                "x-message-ttl": 86400000
            }
        )

        # 任务队列
        self._queues[QueueName.TASK_PROCESSING] = await self._channel.declare_queue(
            QueueName.TASK_PROCESSING,
            durable=True
        )

        self._queues[QueueName.TASK_GENERATION] = await self._channel.declare_queue(
            QueueName.TASK_GENERATION,
            durable=True
        )

        self._queues[QueueName.TASK_ANALYSIS] = await self._channel.declare_queue(
            QueueName.TASK_ANALYSIS,
            durable=True
        )

        # 事件队列
        self._queues[QueueName.EVENT_USER] = await self._channel.declare_queue(
            QueueName.EVENT_USER,
            durable=True
        )

        self._queues[QueueName.EVENT_AGENT] = await self._channel.declare_queue(
            QueueName.EVENT_AGENT,
            durable=True
        )

        logger.info("队列初始化完成")

    async def _setup_dead_letter(self):
        """设置死信队列"""
        self._queues[QueueName.DEAD_LETTER] = await self._channel.declare_queue(
            QueueName.DEAD_LETTER,
            durable=True
        )

        # 绑定死信交换机
        await self._queues[QueueName.DEAD_LETTER].bind(
            self._exchanges[ExchangeName.DIRECT],
            routing_key="dead.letter"
        )

    # =========================================================================
    # 消息发送
    # =========================================================================

    async def publish_task(
        self,
        task: TaskMessage,
        queue: str = QueueName.TASK_PROCESSING
    ) -> bool:
        """发布任务消息"""
        if not self._is_connected:
            logger.warning("RabbitMQ 未连接")
            return False

        try:
            # 根据优先级选择队列
            if task.priority == TaskPriority.HIGH.value:
                queue = QueueName.HIGH_PRIORITY
            elif task.priority == TaskPriority.LOW.value:
                queue = QueueName.LOW_PRIORITY

            # 创建消息
            message_body = json.dumps({
                "task_id": task.task_id,
                "task_type": task.task_type,
                "payload": task.payload,
                "priority": task.priority,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "created_at": task.created_at,
                "expires_at": task.expires_at,
                "correlation_id": task.correlation_id
            }, ensure_ascii=False)

            message = Message(
                message_body.encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
                priority=task.priority,
                correlation_id=task.correlation_id,
                reply_to=task.reply_to
            )

            # 发送消息
            await self._channel.default_exchange.publish(
                message,
                routing_key=queue
            )

            logger.info(f"任务已发布: {task.task_id} -> {queue}")
            return True

        except Exception as e:
            logger.error(f"发布任务失败: {e}")
            return False

    async def publish_event(
        self,
        event: EventMessage,
        exchange: str = ExchangeName.TOPIC,
        routing_key: str = ""
    ) -> bool:
        """发布事件消息"""
        if not self._is_connected:
            return False

        try:
            message_body = json.dumps({
                "event_type": event.event_type,
                "source": event.source,
                "data": event.data,
                "timestamp": event.timestamp,
                "correlation_id": event.correlation_id
            }, ensure_ascii=False)

            message = Message(
                message_body.encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
                correlation_id=event.correlation_id
            )

            # 发送事件
            await self._exchanges[exchange].publish(
                message,
                routing_key=routing_key or event.event_type
            )

            return True

        except Exception as e:
            logger.error(f"发布事件失败: {e}")
            return False

    async def publish_direct(
        self,
        message: Dict[str, Any],
        exchange: str = ExchangeName.DIRECT,
        routing_key: str = ""
    ) -> bool:
        """发布直连消息"""
        if not self._is_connected:
            return False

        try:
            message_body = json.dumps(message, ensure_ascii=False).encode()

            msg = Message(
                message_body,
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json"
            )

            await self._exchanges[exchange].publish(
                msg,
                routing_key=routing_key
            )

            return True

        except Exception as e:
            logger.error(f"发布消息失败: {e}")
            return False

    # =========================================================================
    # 消息消费
    # =========================================================================

    async def consume_tasks(
        self,
        queue: str,
        handler: Callable[[TaskMessage], Awaitable[None]]
    ):
        """消费任务消息"""
        if not self._is_connected:
            return

        # 注册处理器
        self._handlers[queue] = handler

        async def process_message(message: AbstractIncomingMessage):
            async with message.process():
                try:
                    # 解析消息
                    body = json.loads(message.body.decode())

                    task = TaskMessage(
                        task_id=body.get("task_id", ""),
                        task_type=body.get("task_type", ""),
                        payload=body.get("payload", {}),
                        priority=body.get("priority", TaskPriority.NORMAL.value),
                        retry_count=body.get("retry_count", 0),
                        max_retries=body.get("max_retries", 3),
                        created_at=body.get("created_at", ""),
                        correlation_id=body.get("correlation_id", "")
                    )

                    # 调用处理器
                    await handler(task)

                except Exception as e:
                    logger.error(f"处理消息失败: {e}")
                    # 可以选择重新入队或发送到死信队列
                    await self._send_to_dead_letter(message.body, str(e))

        # 开始消费
        queue_obj = self._queues.get(queue)
        if queue_obj:
            await queue_obj.consume(process_message)
            logger.info(f"开始消费队列: {queue}")

    async def consume_events(
        self,
        queue: str,
        handler: Callable[[EventMessage], Awaitable[None]]
    ):
        """消费事件消息"""
        if not self._is_connected:
            return

        self._handlers[queue] = handler

        async def process_message(message: AbstractIncomingMessage):
            async with message.process():
                try:
                    body = json.loads(message.body.decode())

                    event = EventMessage(
                        event_type=body.get("event_type", ""),
                        source=body.get("source", ""),
                        data=body.get("data", {}),
                        timestamp=body.get("timestamp", ""),
                        correlation_id=body.get("correlation_id", "")
                    )

                    await handler(event)

                except Exception as e:
                    logger.error(f"处理事件失败: {e}")

        queue_obj = self._queues.get(queue)
        if queue_obj:
            await queue_obj.consume(process_message)
            logger.info(f"开始消费事件队列: {queue}")

    async def _send_to_dead_letter(self, message_body: bytes, error: str):
        """发送消息到死信队列"""
        try:
            # 创建死信消息
            dead_letter = {
                "original_message": message_body.decode(),
                "error": error,
                "timestamp": datetime.now().isoformat()
            }

            message = Message(
                json.dumps(dead_letter, ensure_ascii=False).encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json"
            )

            await self._channel.default_exchange.publish(
                message,
                routing_key="dead.letter"
            )

            logger.warning("消息已发送到死信队列")

        except Exception as e:
            logger.error(f"发送死信失败: {e}")

    # =========================================================================
    # RPC 调用
    # =========================================================================

    async def rpc_call(
        self,
        queue: str,
        request: Dict[str, Any],
        timeout: int = 30
    ) -> Optional[Dict]:
        """RPC 调用"""
        if not self._is_connected:
            return None

        correlation_id = str(uuid.uuid4())
        reply_queue = await self._channel.declare_queue(
            f"rpc.reply.{correlation_id}",
            durable=False,
            auto_delete=True
        )

        # 创建未来对象
        future = asyncio.Future()

        # 存储回调
        callbacks = getattr(self, '_rpc_callbacks', {})
        callbacks[correlation_id] = future
        self._rpc_callbacks = callbacks

        # 发送请求
        message = Message(
            json.dumps(request, ensure_ascii=False).encode(),
            delivery_mode=DeliveryMode.PERSISTENT,
            correlation_id=correlation_id,
            reply_to=reply_queue.name
        )

        await self._channel.default_exchange.publish(
            message,
            routing_key=queue
        )

        # 等待响应
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.error(f"RPC 调用超时: {correlation_id}")
            return None
        finally:
            # 清理
            await reply_queue.delete()
            callbacks.pop(correlation_id, None)

    # =========================================================================
    # 队列管理
    # =========================================================================

    async def get_queue_status(self, queue_name: str) -> Dict[str, Any]:
        """获取队列状态"""
        try:
            queue = self._queues.get(queue_name)
            if not queue:
                return {}

            # 获取队列信息
            declare_ok = await queue.declare()

            return {
                "name": queue_name,
                "message_count": declare_ok.message_count,
                "consumer_count": declare_ok.consumer_count
            }
        except Exception as e:
            logger.error(f"获取队列状态失败: {e}")
            return {}

    async def purge_queue(self, queue_name: str) -> int:
        """清空队列"""
        try:
            queue = self._queues.get(queue_name)
            if queue:
                await queue.purge()
                logger.info(f"队列已清空: {queue_name}")
                return 1
            return 0
        except Exception as e:
            logger.error(f"清空队列失败: {e}")
            return 0

    async def get_queue_messages(self, queue_name: str, count: int = 10) -> List[Dict]:
        """获取队列消息（不消费）"""
        messages = []
        try:
            queue = self._queues.get(queue_name)
            if queue:
                async with queue.iterator() as queue_iter:
                    async for message in queue_iter:
                        if len(messages) >= count:
                            break
                        try:
                            body = json.loads(message.body.decode())
                            messages.append(body)
                        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                            pass
        except Exception as e:
            logger.error(f"获取队列消息失败: {e}")

        return messages

    # =========================================================================
    # 事务支持
    # =========================================================================

    async def confirm_delivery(self):
        """确认投递"""
        if self._channel:
            await self._channel.set_confirm_delivery()

    # =========================================================================
    # 监控
    # =========================================================================

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "connected": self._is_connected,
            "queues": {}
        }

        # 获取所有队列状态
        for name in self._queues.keys():
            status = await self.get_queue_status(name)
            stats["queues"][name] = status

        return stats


# ============================================================================
# 单例实例
# ============================================================================

_rabbitmq_manager: RabbitMQManager = None


def get_rabbitmq_manager() -> RabbitMQManager:
    """获取 RabbitMQ 管理器单例"""
    global _rabbitmq_manager
    if _rabbitmq_manager is None:
        _rabbitmq_manager = RabbitMQManager()
    return _rabbitmq_manager


def init_rabbitmq_manager(
    url: str = None,
    host: str = "localhost",
    port: int = 5672,
    username: str = "guest",
    password: str = "guest"
) -> RabbitMQManager:
    """初始化 RabbitMQ 管理器"""
    global _rabbitmq_manager
    _rabbitmq_manager = RabbitMQManager(
        url=url,
        host=host,
        port=port,
        username=username,
        password=password
    )
    return _rabbitmq_manager
