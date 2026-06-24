"""
Enhanced Task Queue — 批量生成任务队列 + 自动重试

提供：
- 按优先级排序的任务队列
- 并发控制 (max_concurrent)
- 指数退避自动重试 (3s, 10s, 30s)
- 任务状态查询
- 后台 worker 循环
"""

import asyncio
import logging
import uuid
import time
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Awaitable
from collections import OrderedDict
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class QueueTask:
    """单个队列任务"""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        params: dict,
        priority: int = 5,
        max_retries: int = 3,
    ):
        self.id = task_id
        self.type = task_type  # "generate", "process", "export"
        self.status = TaskStatus.PENDING
        self.priority = max(1, min(10, priority))  # 1-10, 1 highest
        self.params = params
        self.retry_count = 0
        self.max_retries = max_retries
        self.error = ""
        self.created_at = datetime.now().isoformat()
        self.completed_at = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status.value,
            "priority": self.priority,
            "params": self.params,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class TaskQueue:
    """带优先级的任务队列，支持重试和并发控制"""

    def __init__(self, max_concurrent: int = 2, max_completed: int = 100):
        self._queue: List[QueueTask] = []  # sorted by priority
        self._running: Dict[str, QueueTask] = OrderedDict()
        self._completed: Dict[str, QueueTask] = OrderedDict()
        # Track tasks in retry delay window (not in queue, running, or completed)
        self._pending_retry: Dict[str, QueueTask] = OrderedDict()
        self._max_concurrent = max_concurrent
        self._max_completed = max_completed
        self._lock = asyncio.Lock()

    async def enqueue(self, task: QueueTask) -> str:
        """添加任务到队列"""
        async with self._lock:
            task.status = TaskStatus.QUEUED
            self._queue.append(task)
            # 按优先级排序 (数字越小优先级越高)
            self._queue.sort(key=lambda t: t.priority)
            logger.info(
                f"Task {task.id} enqueued (type={task.type}, priority={task.priority}). "
                f"Queue size: {len(self._queue)}, running: {len(self._running)}"
            )
        return task.id

    async def process_next(self) -> Optional[str]:
        """处理下一个待执行任务"""
        async with self._lock:
            if len(self._running) >= self._max_concurrent:
                return None
            if not self._queue:
                return None
            task = self._queue.pop(0)
            task.status = TaskStatus.RUNNING
            self._running[task.id] = task
            return task.id

    async def complete_task(self, task_id: str, success: bool, error: str = "", result_data: dict = None):
        """完成任务"""
        async with self._lock:
            task = self._running.pop(task_id, None)
            if not task:
                return
            if success:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now().isoformat()
                if result_data:
                    task.params["_result"] = result_data
                self._completed[task_id] = task
                # 限制已完成记录数量
                while len(self._completed) > self._max_completed:
                    self._completed.pop(next(iter(self._completed)), None)
                logger.info(f"Task {task_id} completed successfully")
            else:
                task.retry_count += 1
                task.error = error
                if task.retry_count < task.max_retries:
                    task.status = TaskStatus.RETRYING
                    delay = self._get_retry_delay(task.retry_count)
                    logger.info(
                        f"Task {task_id} failed (attempt {task.retry_count}/{task.max_retries}), "
                        f"retrying in {delay}s: {error}"
                    )
                    # 放入 pending_retry 以便查询
                    self._pending_retry[task_id] = task
                    # 重新入队（带延迟）
                    asyncio.create_task(self._delayed_requeue(task, delay))
                else:
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now().isoformat()
                    self._completed[task_id] = task
                    while len(self._completed) > self._max_completed:
                        self._completed.pop(next(iter(self._completed)), None)
                    logger.error(
                        f"Task {task_id} failed after {task.retry_count} retries: {error}"
                    )

    def _get_retry_delay(self, retry_count: int) -> int:
        """指数退避延迟：3s, 10s, 30s"""
        delays = {1: 3, 2: 10, 3: 30}
        return delays.get(retry_count, 30)

    async def _delayed_requeue(self, task: QueueTask, delay: int):
        """延迟重新入队"""
        await asyncio.sleep(delay)
        async with self._lock:
            # 从 pending_retry 移除
            self._pending_retry.pop(task.id, None)
            task.status = TaskStatus.QUEUED
            self._queue.append(task)
            self._queue.sort(key=lambda t: t.priority)
            logger.info(
                f"Task {task.id} re-queued after retry delay ({delay}s)"
            )

    async def retry(self, task_id: str) -> bool:
        """手动重试一个失败的任务"""
        async with self._lock:
            task = self._completed.get(task_id)
            if not task or task.status != TaskStatus.FAILED:
                return False
            # 重置重试计数
            task.retry_count = 0
            task.error = ""
            task.status = TaskStatus.QUEUED
            self._queue.append(task)
            self._queue.sort(key=lambda t: t.priority)
            # 从completed移到queue
            del self._completed[task_id]
            logger.info(f"Task {task_id} manually re-queued for retry")
            return True

    def get_status(self, task_id: str) -> Optional[QueueTask]:
        """查询任务状态"""
        # 检查队列中
        for t in self._queue:
            if t.id == task_id:
                return t
        # 检查运行中
        t = self._running.get(task_id)
        if t:
            return t
        # 检查已完成/失败
        t = self._completed.get(task_id)
        if t:
            return t
        # 检查 pending_retry (重试延迟窗口内)
        t = self._pending_retry.get(task_id)
        if t:
            return t
        return None

    def get_queue_status(self) -> dict:
        """队列状态总览"""
        return {
            "queue_size": len(self._queue),
            "running_count": len(self._running),
            "completed_count": len(self._completed),
            "pending_retry_count": len(self._pending_retry),
            "max_concurrent": self._max_concurrent,
            "pending": sum(1 for t in self._queue if t.status == TaskStatus.QUEUED),
            "retrying": sum(1 for t in self._queue if t.status == TaskStatus.RETRYING),
            "running": {tid: t.to_dict() for tid, t in self._running.items()},
        }

    def cancel_task(self, task_id: str) -> bool:
        """取消一个任务"""
        import asyncio

        async def _cancel():
            async with self._lock:
                # 检查队列中
                for i, t in enumerate(self._queue):
                    if t.id == task_id:
                        t.status = TaskStatus.CANCELLED
                        t.completed_at = datetime.now().isoformat()
                        self._completed[task_id] = t
                        self._queue.pop(i)
                        return True
                # 检查运行中
                t = self._running.get(task_id)
                if t:
                    t.status = TaskStatus.CANCELLED
                    t.completed_at = datetime.now().isoformat()
                    self._completed[task_id] = t
                    del self._running[task_id]
                    return True
                # 检查 pending_retry
                t = self._pending_retry.get(task_id)
                if t:
                    t.status = TaskStatus.CANCELLED
                    t.completed_at = datetime.now().isoformat()
                    self._completed[task_id] = t
                    del self._pending_retry[task_id]
                    return True
                return False

        fut = asyncio.run_coroutine_threadsafe(_cancel(), asyncio.get_event_loop())
        try:
            return fut.result(timeout=5)
        except Exception:
            return False


# =============================================================================
# 全局单例
# =============================================================================

_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue(max_concurrent=2)
    return _task_queue
