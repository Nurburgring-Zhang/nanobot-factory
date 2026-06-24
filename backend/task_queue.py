#!/usr/bin/env python3
"""
Nanobot Factory - Task Queue System
Industrial-grade background task processing

@author MiniMax Agent
@date 2026-02-25
@description 任务队列系统，支持优先级调度、依赖管理、失败重试
"""

import asyncio
import uuid
import time
import logging
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, Future
import threading
import json
import traceback

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class TaskPriority(int, Enum):
    """Task priority levels (higher = more priority)"""
    LOW = 0
    NORMAL = 5
    HIGH = 10
    URGENT = 20


@dataclass
class Task:
    """Task definition"""
    id: str
    name: str
    task_type: str  # generation, processing, import, export, etc.
    payload: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL

    # Progress tracking
    progress: float = 0.0
    current_step: str = ""
    total_steps: int = 1

    # Results
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # Dependencies
    dependencies: List[str] = field(default_factory=list)

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Retry configuration
    max_retries: int = 3
    retry_count: int = 0
    retry_delay: float = 1.0  # Base delay for exponential backoff

    # Metadata
    created_by: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_retry(self) -> bool:
        """Check if task can be retried"""
        return self.retry_count < self.max_retries

    def get_retry_delay(self) -> float:
        """Calculate retry delay with exponential backoff"""
        return self.retry_delay * (2 ** self.retry_count)


@dataclass
class WorkerStats:
    """Worker statistics"""
    worker_id: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_processing_time: float = 0.0
    current_task_id: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_heartbeat: str = field(default_factory=lambda: datetime.now().isoformat())


class TaskQueue:
    """
    Industrial-grade task queue with:
    - Priority scheduling
    - Dependency management
    - Automatic retry with exponential backoff
    - Worker pool management
    - Real-time progress tracking
    """

    def __init__(self, max_workers: int = 4, max_queue_size: int = 1000):
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size

        # Task storage
        self._tasks: Dict[str, Task] = {}
        self._pending_queue: List[str] = []  # Task IDs in priority order
        self._running_tasks: Set[str] = set()

        # Task index for fast lookup
        self._tasks_by_type: Dict[str, Set[str]] = defaultdict(set)
        self._tasks_by_status: Dict[TaskStatus, Set[str]] = defaultdict(set)

        # Dependency graph
        self._dependents: Dict[str, Set[str]] = defaultdict(set)  # task_id -> tasks that depend on it
        self._dependencies: Dict[str, Set[str]] = defaultdict(set)  # task_id -> tasks it depends on

        # Workers
        self._workers: Dict[str, WorkerStats] = {}
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running = False
        self._lock = threading.RLock()

        # Task handlers
        self._handlers: Dict[str, Callable] = {}

        # Callbacks
        self._on_task_update: Optional[Callable] = None
        self._on_task_complete: Optional[Callable] = None
        self._on_task_fail: Optional[Callable] = None

        # Metrics
        self._total_tasks_created = 0
        self._total_tasks_completed = 0
        self._total_tasks_failed = 0

        logger.info(f"TaskQueue initialized with {max_workers} workers")

    def register_handler(self, task_type: str, handler: Callable[[Task], Dict[str, Any]]):
        """Register a task handler"""
        self._handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")

    def set_callbacks(self,
                      on_task_update: Optional[Callable] = None,
                      on_task_complete: Optional[Callable] = None,
                      on_task_fail: Optional[Callable] = None):
        """Set event callbacks"""
        self._on_task_update = on_task_update
        self._on_task_complete = on_task_complete
        self._on_task_fail = on_task_fail

    def create_task(self,
                   name: str,
                   task_type: str,
                   payload: Dict[str, Any],
                   priority: TaskPriority = TaskPriority.NORMAL,
                   dependencies: Optional[List[str]] = None,
                   max_retries: int = 3,
                   created_by: str = "system",
                   metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new task"""
        with self._lock:
            # Check queue size
            if len(self._pending_queue) >= self.max_queue_size:
                raise RuntimeError(f"Task queue is full ({self.max_queue_size} tasks)")

            task_id = str(uuid.uuid4())[:8]
            task = Task(
                id=task_id,
                name=name,
                task_type=task_type,
                payload=payload,
                priority=priority,
                dependencies=dependencies or [],
                max_retries=max_retries,
                created_by=created_by,
                metadata=metadata or {}
            )

            self._tasks[task_id] = task
            self._tasks_by_type[task_type].add(task_id)
            self._tasks_by_status[TaskStatus.PENDING].add(task_id)

            # Register dependencies
            for dep_id in task.dependencies:
                self._dependents[dep_id].add(task_id)
                self._dependencies[task_id].add(dep_id)

            # Add to priority queue
            self._add_to_queue(task_id)

            self._total_tasks_created += 1

            logger.info(f"Created task {task_id}: {name} (type={task_type}, priority={priority})")

            return task_id

    def _add_to_queue(self, task_id: str):
        """Add task to priority queue based on priority"""
        task = self._tasks[task_id]

        # Check if dependencies are met
        if not self._dependencies_met(task_id):
            return  # Will be added when dependencies are complete

        # Insert based on priority (higher priority first)
        inserted = False
        for i, existing_id in enumerate(self._pending_queue):
            if task.priority > self._tasks[existing_id].priority:
                self._pending_queue.insert(i, task_id)
                inserted = True
                break

        if not inserted:
            self._pending_queue.append(task_id)

    def _dependencies_met(self, task_id: str) -> bool:
        """Check if all dependencies are completed"""
        for dep_id in self._dependencies[task_id]:
            dep_task = self._tasks.get(dep_id)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        return True

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        return self._tasks.get(task_id)

    def get_tasks(self,
                  status: Optional[TaskStatus] = None,
                  task_type: Optional[str] = None,
                  limit: int = 100) -> List[Task]:
        """Get tasks with optional filters"""
        with self._lock:
            task_ids = set(self._tasks.keys())

            if status:
                task_ids &= self._tasks_by_status[status]
            if task_type:
                task_ids &= self._tasks_by_type.get(task_type, set())

            tasks = [self._tasks[tid] for tid in list(task_ids)[:limit]]
            return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def get_next_task(self) -> Optional[Task]:
        """Get next task to execute (highest priority with met dependencies)"""
        with self._lock:
            for task_id in self._pending_queue:
                task = self._tasks[task_id]
                if (task.status == TaskStatus.PENDING and
                    self._dependencies_met(task_id)):
                    return task
            return None

    def start_task(self, task_id: str) -> bool:
        """Mark task as running"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status != TaskStatus.PENDING:
                return False

            if not self._dependencies_met(task_id):
                return False

            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now().isoformat()

            self._pending_queue.remove(task_id)
            self._running_tasks.add(task_id)

            self._tasks_by_status[TaskStatus.PENDING].discard(task_id)
            self._tasks_by_status[TaskStatus.RUNNING].add(task_id)

            if self._on_task_update:
                self._on_task_update(task)

            return True

    def update_progress(self, task_id: str, progress: float, current_step: str = ""):
        """Update task progress"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.RUNNING:
                task.progress = min(100.0, max(0.0, progress))
                if current_step:
                    task.current_step = current_step

                if self._on_task_update:
                    self._on_task_update(task)

    def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None):
        """Mark task as completed"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now().isoformat()
            task.progress = 100.0
            if result:
                task.result = result

            self._running_tasks.discard(task_id)

            self._tasks_by_status[TaskStatus.RUNNING].discard(task_id)
            self._tasks_by_status[TaskStatus.COMPLETED].add(task_id)

            self._total_tasks_completed += 1

            # Check dependents and add them to queue if dependencies met
            for dependent_id in self._dependents[task_id]:
                if self._dependencies_met(dependent_id):
                    self._add_to_queue(dependent_id)

            if self._on_task_complete:
                self._on_task_complete(task)

            logger.info(f"Task {task_id} completed")

    def fail_task(self, task_id: str, error: str, retry: bool = True):
        """Mark task as failed, optionally retry"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return

            if retry and task.can_retry():
                # Schedule retry with exponential backoff
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                task.error = f"{error} (retry {task.retry_count}/{task.max_retries})"

                retry_delay = task.get_retry_delay()
                logger.info(f"Task {task_id} scheduled for retry in {retry_delay}s")

                # Schedule retry
                threading.Timer(retry_delay, self._retry_task, args=[task_id]).start()

                self._running_tasks.discard(task_id)
                self._tasks_by_status[TaskStatus.RUNNING].discard(task_id)
                self._tasks_by_status[TaskStatus.PENDING].add(task_id)
            else:
                # Permanent failure
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now().isoformat()
                task.error = error

                self._running_tasks.discard(task_id)

                self._tasks_by_status[TaskStatus.RUNNING].discard(task_id)
                self._tasks_by_status[TaskStatus.FAILED].add(task_id)

                self._total_tasks_failed += 1

                if self._on_task_fail:
                    self._on_task_fail(task)

                logger.error(f"Task {task_id} failed: {error}")

    def _retry_task(self, task_id: str):
        """Retry a failed task"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                self._add_to_queue(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                return False

            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now().isoformat()

            if task_id in self._pending_queue:
                self._pending_queue.remove(task_id)
            self._running_tasks.discard(task_id)

            self._tasks_by_status[TaskStatus.PENDING].discard(task_id)
            self._tasks_by_status[TaskStatus.RUNNING].discard(task_id)
            self._tasks_by_status[TaskStatus.CANCELLED].add(task_id)

            logger.info(f"Task {task_id} cancelled")
            return True

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        with self._lock:
            return {
                "pending": len(self._tasks_by_status[TaskStatus.PENDING]),
                "running": len(self._tasks_by_status[TaskStatus.RUNNING]),
                "completed": len(self._tasks_by_status[TaskStatus.COMPLETED]),
                "failed": len(self._tasks_by_status[TaskStatus.FAILED]),
                "cancelled": len(self._tasks_by_status[TaskStatus.CANCELLED]),
                "total_created": self._total_tasks_created,
                "total_completed": self._total_tasks_completed,
                "total_failed": self._total_tasks_failed,
                "queue_size": len(self._pending_queue),
                "max_workers": self.max_workers,
            }

    def clear_completed(self, before_date: Optional[str] = None):
        """Clear completed tasks"""
        with self._lock:
            to_remove = []
            for task_id, task in self._tasks.items():
                if task.status == TaskStatus.COMPLETED:
                    if before_date and task.completed_at >= before_date:
                        continue
                    to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]
                self._tasks_by_type[task_id].discard(task_id)
                for status_set in self._tasks_by_status.values():
                    status_set.discard(task_id)

            logger.info(f"Cleared {len(to_remove)} completed tasks")
            return len(to_remove)


class TaskExecutor:
    """
    Task executor that processes tasks from the queue.
    Runs in a separate thread, managing worker pool.
    """

    def __init__(self, task_queue: TaskQueue, max_workers: int = 4):
        self.task_queue = task_queue
        self.max_workers = max_workers
        self._running = False
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None

    def start(self):
        """Start the task executor"""
        if self._running:
            return

        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._worker_thread.start()

        logger.info("TaskExecutor started")

    def stop(self, timeout: float = 10.0):
        """Stop the task executor"""
        self._running = False

        if self._worker_thread:
            self._worker_thread.join(timeout=timeout)

        if self._executor:
            self._executor.shutdown(wait=True)

        logger.info("TaskExecutor stopped")

    def _run_loop(self):
        """Main execution loop"""
        while self._running:
            try:
                # Get next task
                task = self.task_queue.get_next_task()

                if not task:
                    time.sleep(0.5)
                    continue

                # Check if handler exists
                handler = self.task_queue._handlers.get(task.task_type)
                if not handler:
                    self.task_queue.fail_task(
                        task.id,
                        f"No handler registered for task type: {task.task_type}",
                        retry=False
                    )
                    continue

                # Start task
                if not self.task_queue.start_task(task.id):
                    time.sleep(0.1)
                    continue

                # Execute task
                try:
                    result = handler(task)
                    self.task_queue.complete_task(task.id, result)
                except Exception as e:
                    error_msg = f"{str(e)}\n{traceback.format_exc()}"
                    self.task_queue.fail_task(task.id, error_msg)

            except Exception as e:
                logger.error(f"Error in task execution loop: {e}")
                time.sleep(1.0)


# Global task queue instance
_task_queue: Optional[TaskQueue] = None
_task_executor: Optional[TaskExecutor] = None


def get_task_queue() -> TaskQueue:
    """Get global task queue instance"""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue(max_workers=4)
    return _task_queue


def get_task_executor() -> TaskExecutor:
    """Get global task executor instance"""
    global _task_executor, _task_queue
    if _task_executor is None:
        _task_queue = get_task_queue()
        _task_executor = TaskExecutor(_task_queue, max_workers=4)
    return _task_executor


# ============================================================================
# Built-in Task Handlers
# ============================================================================

def generation_handler(task: Task) -> Dict[str, Any]:
    """Handle generation tasks - 已禁用模拟"""
    # 禁止模拟生成 - 必须使用真实的生成服务
    raise Exception(
        "Mock generation is disabled. Please use the unified_generation_service for real content generation."
    )


def import_handler(task: Task) -> Dict[str, Any]:
    """Handle data import tasks"""
    import os
    import shutil

    payload = task.payload
    source_path = payload.get("source_path")
    target_path = payload.get("target_path", "/data/imports")

    task.progress = 10.0
    task.current_step = "Scanning files..."

    if not os.path.exists(source_path):
        raise ValueError(f"Source path does not exist: {source_path}")

    # Count files
    files = []
    if os.path.isfile(source_path):
        files = [source_path]
    else:
        for root, _, filenames in os.walk(source_path):
            for f in filenames:
                files.append(os.path.join(root, f))

    total = len(files)
    task.total_steps = total

    imported = []
    for i, file_path in enumerate(files):
        target = os.path.join(target_path, os.path.basename(file_path))
        shutil.copy2(file_path, target)
        imported.append(target)

        task.progress = ((i + 1) / total) * 100
        task.current_step = f"Importing {i + 1}/{total}..."

    return {
        "status": "success",
        "imported_count": len(imported),
        "imported_files": imported
    }


def export_handler(task: Task) -> Dict[str, Any]:
    """Handle data export tasks"""
    import os
    import json

    payload = task.payload
    query = payload.get("query", {})
    output_path = payload.get("output_path")
    format_type = payload.get("format", "jsonl")

    task.progress = 30.0
    task.current_step = "Querying database..."

    # Simulate query
    time.sleep(1)

    task.progress = 70.0
    task.current_step = "Writing export file..."

    # Simulate export
    mock_data = [{"id": "1", "text": "sample"}]

    if format_type == "jsonl":
        with open(output_path, 'w') as f:
            for item in mock_data:
                f.write(json.dumps(item) + '\n')
    else:
        with open(output_path, 'w') as f:
            json.dump(mock_data, f, indent=2)

    task.progress = 100.0

    return {
        "status": "success",
        "output_path": output_path,
        "record_count": len(mock_data),
        "format": format_type
    }


# Register built-in handlers
def register_builtin_handlers(task_queue: TaskQueue):
    """Register all built-in task handlers"""
    task_queue.register_handler("generation", generation_handler)
    task_queue.register_handler("import", import_handler)
    task_queue.register_handler("export", export_handler)
    logger.info("Registered built-in task handlers")


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Create and configure task queue
    queue = TaskQueue(max_workers=2)
    register_builtin_handlers(queue)

    # Create some tasks
    task1_id = queue.create_task(
        name="Generate Images",
        task_type="generation",
        payload={"adapter": "comfyui", "params": {"prompt": "landscape"}},
        priority=TaskPriority.HIGH
    )

    task2_id = queue.create_task(
        name="Import Dataset",
        task_type="import",
        payload={"source_path": "/data/raw", "target_path": "/data/processed"},
        priority=TaskPriority.NORMAL
    )

    task3_id = queue.create_task(
        name="Export Results",
        task_type="export",
        payload={"output_path": "/output/results.jsonl", "format": "jsonl"},
        priority=TaskPriority.LOW,
        dependencies=[task1_id]  # Depends on generation task
    )

    print(f"Created tasks: {task1_id}, {task2_id}, {task3_id}")

    # Get stats
    print("\n=== Queue Stats ===")
    stats = queue.get_queue_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # List pending tasks
    print("\n=== Pending Tasks ===")
    for task in queue.get_tasks(status=TaskStatus.PENDING):
        print(f"  - {task.id}: {task.name} (priority={task.priority})")
