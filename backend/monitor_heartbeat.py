#!/usr/bin/env python3
"""
Nanobot Factory - 监控心跳与任务调度系统
Monitor Heartbeat and Task Scheduler System

功能：
1. 周期性检查任务安排与进度
2. 定期执行功能
3. 长任务连续执行功能
4. 未完成任务自动继续功能
5. 休眠检测、自动唤醒、自动执行功能

@author MiniMax Agent
@date 2026-03-15
"""

import os
import sys
import json
import time
import asyncio
import logging
import hashlib
import threading
import subprocess
import psutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
import uuid
import signal

logger = logging.getLogger(__name__)


# =============================================================================
# 数据模型
# =============================================================================

class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"          # 待执行
    RUNNING = "running"          # 执行中
    PAUSED = "paused"           # 暂停
    COMPLETED = "completed"      # 完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"     # 取消
    WAITING = "waiting"          # 等待中


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


class TaskType(Enum):
    """任务类型"""
    GENERATION = "generation"           # 生成任务
    EDIT = "edit"                      # 编辑任务
    UPSCALE = "upscale"                # 放大任务
    SCHEDULED = "scheduled"            # 定时任务
    BATCH = "batch"                    # 批量任务
    CONTINUE = "continue"               # 继续任务
    WAKEUP = "wakeup"                  # 唤醒任务


@dataclass
class Task:
    """任务"""
    id: str
    name: str
    task_type: TaskType
    status: TaskStatus
    priority: TaskPriority
    progress: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    scheduled_at: Optional[str] = None  # 定时执行时间
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    dependencies: List[str] = field(default_factory=list)
    on_complete: Optional[Callable] = None
    on_fail: Optional[Callable] = None


@dataclass
class ScheduledTask:
    """定时任务配置"""
    task_id: str
    cron_expression: str  # cron 表达式
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0


@dataclass
class SystemState:
    """系统状态"""
    is_running: bool = True
    is_awake: bool = True
    is_busy: bool = False
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    gpu_usage: float = 0.0
    gpu_memory: float = 0.0
    active_tasks: int = 0
    completed_tasks_today: int = 0
    failed_tasks_today: int = 0


# =============================================================================
# 心跳监控器
# =============================================================================

class HeartbeatMonitor:
    """
    心跳监控器
    定期检测系统状态和任务进度
    """
    
    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable] = []
        self.last_heartbeat = datetime.now()
        self.heartbeat_count = 0
        
        # 系统状态
        self.system_state = SystemState()
        self._state_lock = threading.RLock()
        
        # 历史记录
        self.heartbeat_history: deque = deque(maxlen=1000)
        
    def start(self):
        """启动心跳监控"""
        if self.is_running:
            return
            
        self.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Heartbeat monitor started")
        
    def stop(self):
        """停止心跳监控"""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Heartbeat monitor stopped")
        
    def _run(self):
        """心跳监控主循环"""
        while self.is_running:
            try:
                self._perform_heartbeat()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                time.sleep(self.check_interval)
                
    def _perform_heartbeat(self):
        """执行心跳检测"""
        # 更新系统状态
        self._update_system_state()
        
        # 记录心跳
        self.heartbeat_count += 1
        self.last_heartbeat = datetime.now()
        
        heartbeat_data = {
            "timestamp": self.last_heartbeat.isoformat(),
            "count": self.heartbeat_count,
            "system_state": {
                "cpu_usage": self.system_state.cpu_usage,
                "memory_usage": self.system_state.memory_usage,
                "gpu_usage": self.system_state.gpu_usage,
                "is_busy": self.system_state.is_busy,
                "active_tasks": self.system_state.active_tasks
            }
        }
        
        self.heartbeat_history.append(heartbeat_data)
        
        # 执行回调
        for callback in self._callbacks:
            try:
                callback(heartbeat_data)
            except Exception as e:
                logger.error(f"Heartbeat callback error: {e}")
                
    def _update_system_state(self):
        """更新系统状态"""
        with self._state_lock:
            # CPU 使用率
            self.system_state.cpu_usage = psutil.cpu_percent(interval=0.1)
            
            # 内存使用率
            memory = psutil.virtual_memory()
            self.system_state.memory_usage = memory.percent
            
            # GPU 状态 (如果可用)
            try:
                import torch
                if torch.cuda.is_available():
                    self.system_state.gpu_usage = torch.cuda.utilization()
                    self.system_state.gpu_memory = torch.cuda.memory_allocated() / torch.cuda.max_memory_allocated() * 100
            except (ImportError, RuntimeError, AttributeError):
                pass
                
    def add_callback(self, callback: Callable):
        """添加心跳回调"""
        self._callbacks.append(callback)
        
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        with self._state_lock:
            return {
                "is_running": self.is_running,
                "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
                "heartbeat_count": self.heartbeat_count,
                "system_state": {
                    "cpu_usage": self.system_state.cpu_usage,
                    "memory_usage": self.system_state.memory_usage,
                    "gpu_usage": self.system_state.gpu_usage,
                    "gpu_memory": self.system_state.gpu_memory,
                    "is_busy": self.system_state.is_busy,
                    "is_awake": self.system_state.is_awake,
                    "active_tasks": self.system_state.active_tasks,
                    "completed_tasks_today": self.system_state.completed_tasks_today,
                    "failed_tasks_today": self.system_state.failed_tasks_today
                }
            }


# =============================================================================
# 任务调度器
# =============================================================================

class TaskScheduler:
    """
    任务调度器
    管理任务队列、定时执行、优先级调度
    """
    
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._lock = threading.RLock()
        
        # 定时任务
        self.scheduled_tasks: Dict[str, ScheduledTask] = {}
        
        # 长任务连续执行
        self.continuation_tasks: Dict[str, Task] = {}
        self.continuation_enabled = True
        
        # 任务历史
        self.task_history: deque = deque(maxlen=10000)
        
        # 回调
        self.task_callbacks: Dict[str, List[Callable]] = {
            "on_submit": [],
            "on_start": [],
            "on_progress": [],
            "on_complete": [],
            "on_fail": [],
            "on_cancel": []
        }
        
    def submit_task(
        self,
        name: str,
        task_type: TaskType,
        parameters: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        scheduled_at: Optional[str] = None,
        dependencies: List[str] = None,
        max_retries: int = 3
    ) -> str:
        """提交任务"""
        task_id = hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:12]
        
        task = Task(
            id=task_id,
            name=name,
            task_type=task_type,
            status=TaskStatus.PENDING,
            priority=priority,
            parameters=parameters,
            scheduled_at=scheduled_at,
            dependencies=dependencies or [],
            max_retries=max_retries
        )
        
        with self._lock:
            self.tasks[task_id] = task
            
        # 触发回调
        for callback in self.task_callbacks["on_submit"]:
            try:
                callback(task)
            except Exception as e:
                logger.error(f"Task submit callback error: {e}")
                
        logger.info(f"Task submitted: {task_id} - {name}")
        return task_id
        
    def start_task(self, task_id: str) -> bool:
        """启动任务"""
        with self._lock:
            if task_id not in self.tasks:
                return False
                
            task = self.tasks[task_id]
            
            # 检查依赖
            for dep_id in task.dependencies:
                if dep_id in self.tasks:
                    dep_task = self.tasks[dep_id]
                    if dep_task.status != TaskStatus.COMPLETED:
                        logger.warning(f"Task {task_id} waiting for dependency {dep_id}")
                        return False
            
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now().isoformat()
            task.updated_at = datetime.now().isoformat()
            
        # 触发回调
        for callback in self.task_callbacks["on_start"]:
            try:
                callback(task)
            except Exception as e:
                logger.error(f"Task start callback error: {e}")
                
        logger.info(f"Task started: {task_id}")
        return True
        
    def update_progress(self, task_id: str, progress: float):
        """更新任务进度"""
        with self._lock:
            if task_id not in self.tasks:
                return
                
            task = self.tasks[task_id]
            task.progress = max(0, min(100, progress))
            task.updated_at = datetime.now().isoformat()
            
        # 触发回调
        for callback in self.task_callbacks["on_progress"]:
            try:
                callback(task)
            except Exception as e:
                logger.error(f"Task progress callback error: {e}")
                
    def complete_task(self, task_id: str, result: Dict[str, Any] = None):
        """完成任务"""
        with self._lock:
            if task_id not in self.tasks:
                return
                
            task = self.tasks[task_id]
            task.status = TaskStatus.COMPLETED
            task.progress = 100.0
            task.completed_at = datetime.now().isoformat()
            task.updated_at = datetime.now().isoformat()
            task.result = result
            
        # 触发回调
        for callback in self.task_callbacks["on_complete"]:
            try:
                callback(task)
            except Exception as e:
                logger.error(f"Task complete callback error: {e}")
                
        logger.info(f"Task completed: {task_id}")
        
    def fail_task(self, task_id: str, error: str):
        """任务失败"""
        with self._lock:
            if task_id not in self.tasks:
                return
                
            task = self.tasks[task_id]
            task.status = TaskStatus.FAILED
            task.error_message = error
            task.updated_at = datetime.now().isoformat()
            
            # 重试
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                logger.info(f"Task {task_id} will retry ({task.retry_count}/{task.max_retries})")
            else:
                # 触发失败回调
                for callback in self.task_callbacks["on_fail"]:
                    try:
                        callback(task)
                    except Exception as e:
                        logger.error(f"Task fail callback error: {e}")
                        
        logger.error(f"Task failed: {task_id} - {error}")
        
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._lock:
            if task_id not in self.tasks:
                return False
                
            task = self.tasks[task_id]
            if task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
                return False
                
            task.status = TaskStatus.CANCELLED
            task.updated_at = datetime.now().isoformat()
            
        # 触发回调
        for callback in self.task_callbacks["on_cancel"]:
            try:
                callback(task)
            except Exception as e:
                logger.error(f"Task cancel callback error: {e}")
                
        logger.info(f"Task cancelled: {task_id}")
        return True
        
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        with self._lock:
            return self.tasks.get(task_id)
            
    def get_all_tasks(self, status: TaskStatus = None) -> List[Task]:
        """获取所有任务"""
        with self._lock:
            if status:
                return [t for t in self.tasks.values() if t.status == status]
            return list(self.tasks.values())
            
    def get_pending_tasks(self) -> List[Task]:
        """获取待执行任务"""
        with self._lock:
            return [
                t for t in self.tasks.values() 
                if t.status == TaskStatus.PENDING
            ]
            
    def get_running_tasks(self) -> List[Task]:
        """获取正在执行的任务"""
        with self._lock:
            return [
                t for t in self.tasks.values() 
                if t.status == TaskStatus.RUNNING
            ]
            
    def get_continuation_tasks(self) -> List[Task]:
        """获取需要继续执行的长任务"""
        if not self.continuation_enabled:
            return []
            
        with self._lock:
            return [
                t for t in self.tasks.values()
                if t.task_type == TaskType.CONTINUE and t.status == TaskStatus.PAUSED
            ]
            
    def register_callback(self, event: str, callback: Callable):
        """注册回调"""
        if event in self.task_callbacks:
            self.task_callbacks[event].append(callback)
            
    def schedule_task(self, task_id: str, cron_expression: str):
        """添加定时任务"""
        scheduled = ScheduledTask(
            task_id=task_id,
            cron_expression=cron_expression
        )
        self.scheduled_tasks[task_id] = scheduled
        logger.info(f"Task scheduled: {task_id} with cron: {cron_expression}")
        
    def process_scheduled_tasks(self):
        """处理定时任务"""
        now = datetime.now()
        
        for task_id, scheduled in self.scheduled_tasks.items():
            if not scheduled.enabled:
                continue
                
            # 检查是否到达执行时间
            if scheduled.next_run:
                next_run = datetime.fromisoformat(scheduled.next_run)
                if now >= next_run:
                    # 执行任务
                    if task_id in self.tasks:
                        task = self.tasks[task_id]
                        if task.status == TaskStatus.PENDING:
                            self.start_task(task_id)
                            
                    scheduled.last_run = now.isoformat()
                    scheduled.run_count += 1
                    # 计算下次执行时间 (简化实现)
                    scheduled.next_run = (now + timedelta(hours=1)).isoformat()


# =============================================================================
# 自动执行引擎
# =============================================================================

class AutoExecutionEngine:
    """
    自动执行引擎
    负责长任务连续执行、未完成任务自动继续、休眠检测、自动唤醒
    """
    
    def __init__(self, scheduler: TaskScheduler, monitor: HeartbeatMonitor):
        self.scheduler = scheduler
        self.monitor = monitor
        
        # 休眠检测
        self.idle_threshold = 300  # 5分钟无操作视为休眠
        self.last_activity = time.time()
        self.is_sleeping = False
        
        # 自动执行
        self.auto_execute_enabled = True
        self.auto_continue_enabled = True
        self.continue_interval = 60  # 每60秒检查一次继续任务
        
        # 长任务配置
        self.max_consecutive_tasks = 10  # 最大连续执行任务数
        self.consecutive_task_count = 0
        self.consecutive_task_limit = 10
        
        # 线程
        self._thread: Optional[threading.Thread] = None
        self._running = False
        
        # 任务执行器
        self._executor_task: Optional[asyncio.Task] = None
        
    def start(self):
        """启动自动执行引擎"""
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        
        # 注册心跳回调
        self.monitor.add_callback(self._on_heartbeat)
        
        logger.info("Auto execution engine started")
        
    def stop(self):
        """停止自动执行引擎"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Auto execution engine stopped")
        
    def _run(self):
        """自动执行主循环"""
        while self._running:
            try:
                # 检测休眠
                self._check_sleep()
                
                # 自动执行待处理任务
                if self.auto_execute_enabled and not self.is_sleeping:
                    self._execute_pending_tasks()
                    
                # 自动继续长任务
                if self.auto_continue_enabled and not self.is_sleeping:
                    self._continue_long_tasks()
                    
                # 更新活动时间
                self.last_activity = time.time()
                
                time.sleep(self.continue_interval)
                
            except Exception as e:
                logger.error(f"Auto execution error: {e}")
                time.sleep(self.continue_interval)
                
    def _on_heartbeat(self, heartbeat_data: Dict[str, Any]):
        """心跳回调"""
        # 检测系统是否忙碌
        system_state = heartbeat_data.get("system_state", {})
        cpu_usage = system_state.get("cpu_usage", 0)
        gpu_usage = system_state.get("gpu_usage", 0)
        
        # CPU > 90% 或 GPU > 95% 视为忙碌
        is_busy = cpu_usage > 90 or gpu_usage > 95
        
        with self.monitor._state_lock:
            self.monitor.system_state.is_busy = is_busy
            
    def _check_sleep(self):
        """检测休眠状态"""
        current_time = time.time()
        idle_time = current_time - self.last_activity
        
        if idle_time > self.idle_threshold and not self.is_sleeping:
            # 进入休眠
            self.is_sleeping = True
            self.monitor.system_state.is_awake = False
            logger.info(f"System entering sleep mode after {idle_time:.0f}s idle")
            
        elif idle_time < self.idle_threshold and self.is_sleeping:
            # 唤醒
            self.is_sleeping = False
            self.monitor.system_state.is_awake = True
            logger.info("System waking up from sleep mode")
            # 唤醒后自动执行待处理任务
            self._execute_pending_tasks()
            
    def _execute_pending_tasks(self):
        """执行待处理任务"""
        # 检查系统是否忙碌
        with self.monitor._state_lock:
            if self.monitor.system_state.is_busy:
                logger.debug("System busy, skipping task execution")
                return
                
        # 获取待处理任务
        pending_tasks = self.scheduler.get_pending_tasks()
        
        if not pending_tasks:
            return
            
        # 按优先级排序
        pending_tasks.sort(key=lambda t: t.priority.value, reverse=True)
        
        # 执行任务
        for task in pending_tasks[:3]:  # 每次最多执行3个
            # 检查依赖
            can_run = True
            for dep_id in task.dependencies:
                dep_task = self.scheduler.get_task(dep_id)
                if dep_task and dep_task.status != TaskStatus.COMPLETED:
                    can_run = False
                    break
                    
            if can_run:
                success = self.scheduler.start_task(task.id)
                if success:
                    self.consecutive_task_count += 1
                    logger.info(f"Auto-executed task: {task.id}")
                    
    def _continue_long_tasks(self):
        """继续执行长任务"""
        continuation_tasks = self.scheduler.get_continuation_tasks()
        
        for task in continuation_tasks:
            # 检查是否可以继续
            if task.progress < 100:
                # 恢复任务执行
                success = self.scheduler.start_task(task.id)
                if success:
                    logger.info(f"Continued long task: {task.id} (progress: {task.progress}%)")
                    
    def record_activity(self):
        """记录用户活动"""
        self.last_activity = time.time()
        if self.is_sleeping:
            self.is_sleeping = False
            self.monitor.system_state.is_awake = True
            logger.info("User activity detected, waking up system")
            
    def set_idle_threshold(self, seconds: int):
        """设置休眠阈值"""
        self.idle_threshold = seconds
        
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "auto_execute_enabled": self.auto_execute_enabled,
            "auto_continue_enabled": self.auto_continue_enabled,
            "is_sleeping": self.is_sleeping,
            "consecutive_task_count": self.consecutive_task_count,
            "idle_threshold": self.idle_threshold,
            "last_activity": datetime.fromtimestamp(self.last_activity).isoformat()
        }


# =============================================================================
# 任务执行器 (异步)
# =============================================================================

class TaskExecutor:
    """
    异步任务执行器
    实际执行任务的逻辑
    """
    
    def __init__(self, scheduler: TaskScheduler):
        self.scheduler = scheduler
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # 任务处理器映射
        self.handlers: Dict[TaskType, Callable] = {}
        
    def register_handler(self, task_type: TaskType, handler: Callable):
        """注册任务处理器"""
        self.handlers[task_type] = handler
        
    async def start(self):
        """启动执行器"""
        if self._running:
            return
            
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Task executor started")
        
    async def stop(self):
        """停止执行器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Task executor stopped")
        
    async def _run(self):
        """执行循环"""
        while self._running:
            try:
                # 获取待执行任务
                pending = self.scheduler.get_pending_tasks()
                
                for task in pending[:5]:  # 每次最多处理5个
                    await self._execute_task(task)
                    
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Executor error: {e}")
                await asyncio.sleep(1)
                
    async def _execute_task(self, task: Task):
        """执行单个任务"""
        if task.task_type not in self.handlers:
            self.scheduler.fail_task(task.id, f"No handler for task type: {task.task_type}")
            return
            
        try:
            # 启动任务
            self.scheduler.start_task(task.id)
            
            # 执行任务
            handler = self.handlers[task.task_type]
            result = await handler(task)
            
            # 完成任务
            self.scheduler.complete_task(task.id, result)
            
        except Exception as e:
            logger.error(f"Task execution error: {e}")
            self.scheduler.fail_task(task.id, str(e))


# =============================================================================
# 全局实例
# =============================================================================

_heartbeat_monitor: Optional[HeartbeatMonitor] = None
_task_scheduler: Optional[TaskScheduler] = None
_auto_executor: Optional[AutoExecutionEngine] = None
_task_executor: Optional[TaskExecutor] = None


def get_heartbeat_monitor() -> HeartbeatMonitor:
    """获取心跳监控器"""
    global _heartbeat_monitor
    if _heartbeat_monitor is None:
        _heartbeat_monitor = HeartbeatMonitor(check_interval=5.0)
    return _heartbeat_monitor


def get_task_scheduler() -> TaskScheduler:
    """获取任务调度器"""
    global _task_scheduler
    if _task_scheduler is None:
        _task_scheduler = TaskScheduler()
    return _task_scheduler


def get_auto_executor() -> AutoExecutionEngine:
    """获取自动执行引擎"""
    global _auto_executor
    if _auto_executor is None:
        monitor = get_heartbeat_monitor()
        scheduler = get_task_scheduler()
        _auto_executor = AutoExecutionEngine(scheduler, monitor)
    return _auto_executor


def get_task_executor() -> TaskExecutor:
    """获取任务执行器"""
    global _task_executor
    if _task_executor is None:
        scheduler = get_task_scheduler()
        _task_executor = TaskExecutor(scheduler)
    return _task_executor


# =============================================================================
# 便捷函数
# =============================================================================

def submit_generation_task(
    name: str,
    parameters: Dict[str, Any],
    priority: TaskPriority = TaskPriority.NORMAL,
    scheduled_at: Optional[str] = None
) -> str:
    """提交生成任务"""
    scheduler = get_task_scheduler()
    return scheduler.submit_task(
        name=name,
        task_type=TaskType.GENERATION,
        parameters=parameters,
        priority=priority,
        scheduled_at=scheduled_at
    )


def submit_scheduled_task(
    name: str,
    task_type: TaskType,
    parameters: Dict[str, Any],
    cron_expression: str
) -> str:
    """提交定时任务"""
    scheduler = get_task_scheduler()
    task_id = scheduler.submit_task(
        name=name,
        task_type=task_type,
        parameters=parameters,
        scheduled_at=datetime.now().isoformat()
    )
    scheduler.schedule_task(task_id, cron_expression)
    return task_id


def start_monitoring():
    """启动所有监控和执行系统"""
    monitor = get_heartbeat_monitor()
    scheduler = get_task_scheduler()
    auto_exec = get_auto_executor()
    task_exec = get_task_executor()
    
    monitor.start()
    auto_exec.start()
    
    # 启动异步任务执行器
    try:
        asyncio.run(task_exec.start())
    except RuntimeError:
        # 已在事件循环中
        pass
        
    logger.info("All monitoring systems started")


def stop_monitoring():
    """停止所有监控和执行系统"""
    global _heartbeat_monitor, _task_scheduler, _auto_executor, _task_executor
    
    if _heartbeat_monitor:
        _heartbeat_monitor.stop()
        
    if _auto_executor:
        _auto_executor.stop()
        
    if _task_executor:
        asyncio.run(_task_executor.stop())
        
    logger.info("All monitoring systems stopped")


def get_system_status() -> Dict[str, Any]:
    """获取系统状态"""
    monitor = get_heartbeat_monitor()
    scheduler = get_task_scheduler()
    auto_exec = get_auto_executor()
    
    return {
        "heartbeat": monitor.get_status(),
        "tasks": {
            "total": len(scheduler.tasks),
            "pending": len(scheduler.get_pending_tasks()),
            "running": len(scheduler.get_running_tasks()),
            "completed": len(scheduler.get_all_tasks(TaskStatus.COMPLETED)),
            "failed": len(scheduler.get_all_tasks(TaskStatus.FAILED))
        },
        "auto_execution": auto_exec.get_status()
    }


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 启动监控
    start_monitoring()
    
    # 提交测试任务
    task_id = submit_generation_task(
        name="测试图片生成",
        parameters={
            "prompt": "A beautiful sunset",
            "model": "flux-pro",
            "width": 1024,
            "height": 1024
        }
    )
    
    print(f"Submitted task: {task_id}")
    
    # 获取状态
    status = get_system_status()
    print(json.dumps(status, indent=2, default=str))
    
    # 运行一段时间
    try:
        while True:
            time.sleep(10)
            status = get_system_status()
            print(f"Active tasks: {status['tasks']['running']}")
    except KeyboardInterrupt:
        stop_monitoring()
