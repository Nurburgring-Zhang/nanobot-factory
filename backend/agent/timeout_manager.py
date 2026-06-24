#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nanobot Factory - Unified Timeout Manager
统一超时管理器 - 实现全局超时控制、任务级超时

核心功能：
- 全局超时配置
- 任务级超时
- 超时策略（取消/回退/延长）
- 超时监控与指标
- 软超时警告

@author MiniMax Agent
@date 2026-03-03
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
import uuid

logger = logging.getLogger(__name__)


class TimeoutStrategy(Enum):
    """超时策略"""
    CANCEL = "cancel"
    FALLBACK = "fallback"
    RETRY = "retry"
    GRACEFUL = "graceful"


class TimeoutLevel(Enum):
    """超时级别"""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


@dataclass
class TimeoutConfig:
    """超时配置"""
    level: TimeoutLevel
    timeout: float
    strategy: TimeoutStrategy = TimeoutStrategy.CANCEL
    max_retries: int = 0
    retry_delay: float = 1.0
    fallback: Optional[Callable] = None
    enable_soft_timeout: bool = True
    soft_timeout_ratio: float = 0.8


@dataclass
class TimeoutTask:
    """超时任务"""
    id: str
    name: str
    level: TimeoutLevel
    start_time: datetime
    timeout: float
    strategy: TimeoutStrategy
    status: str = "running"
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    soft_timeout_triggered: bool = False
    completed_at: Optional[datetime] = None


@dataclass
class TimeoutMetrics:
    """超时指标"""
    total_tasks: int = 0
    completed_on_time: int = 0
    timed_out: int = 0
    cancelled: int = 0
    retried: int = 0
    fallback_used: int = 0
    total_execution_time: float = 0.0
    avg_execution_time: float = 0.0


class TimeoutHandler(ABC):
    """超时处理抽象基类"""

    @abstractmethod
    async def handle_timeout(
        self,
        task: TimeoutTask,
        exception: asyncio.TimeoutError,
    ) -> Any:
        """处理超时"""
        pass


class CancelOnTimeout(TimeoutHandler):
    """超时取消策略"""

    async def handle_timeout(
        self,
        task: TimeoutTask,
        exception: asyncio.TimeoutError,
    ) -> Any:
        """直接抛出超时异常"""
        task.status = "cancelled"
        task.error = f"Task {task.name} timed out after {task.timeout}s"
        raise asyncio.TimeoutError(task.error)


class FallbackOnTimeout(TimeoutHandler):
    """超时回退策略"""

    def __init__(self, fallback_func: Callable):
        self.fallback_func = fallback_func

    async def handle_timeout(
        self,
        task: TimeoutTask,
        exception: asyncio.TimeoutError,
    ) -> Any:
        """使用回退函数"""
        task.status = "fallback"
        task.error = f"Task {task.name} timed out, using fallback"

        if asyncio.iscoroutinefunction(self.fallback_func):
            return await self.fallback_func(task)
        return self.fallback_func(task)


class RetryOnTimeout(TimeoutHandler):
    """超时重试策略"""

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def handle_timeout(
        self,
        task: TimeoutTask,
        exception: asyncio.TimeoutError,
    ) -> Any:
        """重试任务"""
        if task.retry_count >= self.max_retries:
            task.status = "max_retries_exceeded"
            task.error = f"Task {task.name} exceeded max retries"
            raise asyncio.TimeoutError(task.error)

        task.retry_count += 1
        task.status = "retrying"

        logger.info(f"Retrying task {task.name} (attempt {task.retry_count})")
        await asyncio.sleep(self.retry_delay)

        raise exception


class GracefulTimeout(TimeoutHandler):
    """优雅降级策略"""

    def __init__(self, partial_result: Any = None):
        self.partial_result = partial_result

    async def handle_timeout(
        self,
        task: TimeoutTask,
        exception: asyncio.TimeoutError,
    ) -> Any:
        """返回部分结果"""
        task.status = "graceful"
        task.result = self.partial_result
        task.error = f"Task {task.name} timed out but returned partial result"

        return self.partial_result


class UnifiedTimeoutManager:
    """
    统一超时管理器

    核心功能：
    - 全局超时配置
    - 任务级超时控制
    - 多种超时策略
    - 超时监控与指标
    - 软超时警告
    """

    def __init__(
        self,
        default_timeout: float = 30.0,
        enable_metrics: bool = True,
    ):
        self.default_timeout = default_timeout
        self.enable_metrics = enable_metrics

        # 超时配置
        self._level_configs: Dict[TimeoutLevel, TimeoutConfig] = {
            TimeoutLevel.CRITICAL: TimeoutConfig(
                level=TimeoutLevel.CRITICAL,
                timeout=300.0,
                strategy=TimeoutStrategy.RETRY,
                max_retries=3,
            ),
            TimeoutLevel.HIGH: TimeoutConfig(
                level=TimeoutLevel.HIGH,
                timeout=60.0,
                strategy=TimeoutStrategy.FALLBACK,
            ),
            TimeoutLevel.NORMAL: TimeoutConfig(
                level=TimeoutLevel.NORMAL,
                timeout=30.0,
                strategy=TimeoutStrategy.CANCEL,
            ),
            TimeoutLevel.LOW: TimeoutConfig(
                level=TimeoutLevel.LOW,
                timeout=60.0,
                strategy=TimeoutStrategy.GRACEFUL,
            ),
            TimeoutLevel.BACKGROUND: TimeoutConfig(
                level=TimeoutLevel.BACKGROUND,
                timeout=300.0,
                strategy=TimeoutStrategy.CANCEL,
            ),
        }

        # 任务注册表
        self._tasks: Dict[str, TimeoutTask] = {}

        # 指标
        self._metrics = TimeoutMetrics()

        # 软超时回调
        self._soft_timeout_callbacks: Dict[str, List[Callable]] = {}

        # 监控任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

        # 锁
        self._lock = asyncio.Lock()

        logger.info(f"UnifiedTimeoutManager initialized (default={default_timeout}s)")

    async def start(self):
        """启动超时管理器"""
        self._running = True
        logger.info("UnifiedTimeoutManager started")

    async def stop(self):
        """停止超时管理器"""
        self._running = False
        logger.info("UnifiedTimeoutManager stopped")

    def set_level_config(self, level: TimeoutLevel, config: TimeoutConfig):
        """设置级别配置"""
        self._level_configs[level] = config

    def get_config(self, level: TimeoutLevel) -> TimeoutConfig:
        """获取级别配置"""
        return self._level_configs.get(level, TimeoutConfig(
            level=level,
            timeout=self.default_timeout,
        ))

    async def run_with_timeout(
        self,
        coro: Callable,
        level: TimeoutLevel = TimeoutLevel.NORMAL,
        task_name: Optional[str] = None,
        timeout: Optional[float] = None,
        strategy: Optional[TimeoutStrategy] = None,
        fallback: Optional[Callable] = None,
        *args,
        **kwargs,
    ) -> Any:
        """使用超时控制运行协程"""
        config = self.get_config(level)
        task_timeout = timeout or config.timeout
        task_strategy = strategy or config.strategy

        task_id = f"task_{uuid.uuid4().hex[:8]}"
        task = TimeoutTask(
            id=task_id,
            name=task_name or f"task_{task_id}",
            level=level,
            start_time=datetime.now(),
            timeout=task_timeout,
            strategy=task_strategy,
        )

        async with self._lock:
            self._tasks[task_id] = task

        handler = self._create_handler(task_strategy, config, fallback)

        soft_timeout = task_timeout * config.soft_timeout_ratio

        try:
            result = await asyncio.wait_for(
                coro(*args, **kwargs),
                timeout=task_timeout,
            )

            task.status = "completed"
            task.result = result
            task.completed_at = datetime.now()

            execution_time = (task.completed_at - task.start_time).total_seconds()
            await self._update_metrics(task, execution_time, success=True)

            return result

        except asyncio.TimeoutError:
            execution_time = (datetime.now() - task.start_time).total_seconds()

            if config.enable_soft_timeout and execution_time >= soft_timeout:
                task.soft_timeout_triggered = True

            return await handler.handle_timeout(task, asyncio.TimeoutError())

        except Exception as e:
            task.status = "error"
            task.error = str(e)
            task.completed_at = datetime.now()

            execution_time = (task.completed_at - task.start_time).total_seconds()
            await self._update_metrics(task, execution_time, success=False)

            raise

        finally:
            async with self._lock:
                if task_id in self._tasks:
                    del self._tasks[task_id]

    def _create_handler(
        self,
        strategy: TimeoutStrategy,
        config: TimeoutConfig,
        fallback: Optional[Callable] = None,
    ) -> TimeoutHandler:
        """创建超时处理器"""
        if strategy == TimeoutStrategy.CANCEL:
            return CancelOnTimeout()
        elif strategy == TimeoutStrategy.FALLBACK:
            fallback_func = fallback or config.fallback
            if not fallback_func:
                raise ValueError("Fallback strategy requires a fallback function")
            return FallbackOnTimeout(fallback_func)
        elif strategy == TimeoutStrategy.RETRY:
            return RetryOnTimeout(
                max_retries=config.max_retries,
                retry_delay=config.retry_delay,
            )
        elif strategy == TimeoutStrategy.GRACEFUL:
            return GracefulTimeout()
        else:
            return CancelOnTimeout()

    async def _update_metrics(
        self,
        task: TimeoutTask,
        execution_time: float,
        success: bool,
    ):
        """更新指标"""
        if not self.enable_metrics:
            return

        self._metrics.total_tasks += 1

        if success:
            self._metrics.completed_on_time += 1
        else:
            if task.status == "cancelled":
                self._metrics.cancelled += 1
            elif task.status == "retrying":
                self._metrics.retried += 1
            elif task.status == "fallback":
                self._metrics.fallback_used += 1
            else:
                self._metrics.timed_out += 1

        self._metrics.total_execution_time += execution_time
        self._metrics.avg_execution_time = (
            self._metrics.total_execution_time / self._metrics.total_tasks
        )

    def get_task(self, task_id: str) -> Optional[TimeoutTask]:
        """获取任务"""
        return self._tasks.get(task_id)

    def get_running_tasks(self) -> List[TimeoutTask]:
        """获取运行中的任务"""
        return [
            task for task in self._tasks.values()
            if task.status == "running"
        ]

    def get_metrics(self) -> Dict[str, Any]:
        """获取指标"""
        return {
            "total_tasks": self._metrics.total_tasks,
            "completed_on_time": self._metrics.completed_on_time,
            "timed_out": self._metrics.timed_out,
            "cancelled": self._metrics.cancelled,
            "retried": self._metrics.retried,
            "fallback_used": self._metrics.fallback_used,
            "avg_execution_time": self._metrics.avg_execution_time,
            "running_tasks": len(self.get_running_tasks()),
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self._metrics.total_tasks
        if total == 0:
            return {"status": "no_data"}

        return {
            "total_tasks": total,
            "success_rate": self._metrics.completed_on_time / total,
            "timeout_rate": self._metrics.timed_out / total,
            "avg_execution_time": self._metrics.avg_execution_time,
            "running_tasks": len(self.get_running_tasks()),
        }


def with_timeout(
    timeout: float = 30.0,
    level: TimeoutLevel = TimeoutLevel.NORMAL,
    strategy: TimeoutStrategy = TimeoutStrategy.CANCEL,
):
    """超时装饰器"""
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            manager = _global_timeout_manager
            return await manager.run_with_timeout(
                func,
                level=level,
                task_name=func.__name__,
                timeout=timeout,
                strategy=strategy,
                *args,
                **kwargs,
            )
        return wrapper
    return decorator


_global_timeout_manager: Optional[UnifiedTimeoutManager] = None


def get_timeout_manager() -> UnifiedTimeoutManager:
    """获取全局超时管理器"""
    global _global_timeout_manager
    if _global_timeout_manager is None:
        _global_timeout_manager = UnifiedTimeoutManager()
    return _global_timeout_manager


def create_timeout_manager(
    default_timeout: float = 30.0,
    enable_metrics: bool = True,
) -> UnifiedTimeoutManager:
    """创建超时管理器实例"""
    return UnifiedTimeoutManager(
        default_timeout=default_timeout,
        enable_metrics=enable_metrics,
    )


if __name__ == "__main__":
    import asyncio

    async def main():
        manager = create_timeout_manager(default_timeout=30.0)
        await manager.start()

        async def my_task(x: int):
            await asyncio.sleep(x)
            return x * 2

        # 正常执行
        result = await manager.run_with_timeout(
            my_task,
            level=TimeoutLevel.NORMAL,
            task_name="my_task",
            timeout=5.0,
            x=1,
        )
        print(f"Result: {result}")

        # 超时执行
        try:
            result = await manager.run_with_timeout(
                my_task,
                level=TimeoutLevel.NORMAL,
                task_name="my_task_timeout",
                timeout=1.0,
                strategy=TimeoutStrategy.FALLBACK,
                fallback=lambda t: "fallback_result",
                x=10,
            )
        except asyncio.TimeoutError:
            print("Task timed out")

        print(manager.get_stats())
        await manager.stop()

    asyncio.run(main())
