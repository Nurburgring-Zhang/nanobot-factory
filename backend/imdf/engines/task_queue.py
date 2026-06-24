"""
P0-8: Task Queue (APScheduler)
===============================
Async task queue using APScheduler AsyncIOScheduler + SQLiteJobStore.
Supports enqueue, status, list, cancel, start, stop with retry logic.
"""

import uuid
import json
import importlib
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.date import DateTrigger
from apscheduler.executors.pool import ThreadPoolExecutor


# Module-level registry for task execution
_task_registry: Dict[str, dict] = {}


def _execute_task(job_id: str) -> dict:
    """Module-level function called by APScheduler to execute a task.

    Loads task details from the registry, resolves the callable, and runs it
    with retry logic.
    """
    task = _task_registry.get(job_id)
    if not task:
        return {"status": "failed", "error": f"Task {job_id} not found in registry"}

    func_path = task["func_path"]
    args = task.get("args", [])
    kwargs = task.get("kwargs", {})
    max_retries = task.get("max_retries", 3)
    retry_delay = task.get("retry_delay", 60)

    attempts = 0
    while attempts < max_retries:
        try:
            parts = func_path.split(".")
            if len(parts) < 2:
                raise ValueError(f"Invalid func_path: {func_path}")
            module_path = ".".join(parts[:-1])
            attr_name = parts[-1]
            module = importlib.import_module(module_path)
            func = getattr(module, attr_name)
            result = func(*args, **kwargs)
            return {"status": "completed", "result": str(result)[:500]}
        except Exception as e:
            attempts += 1
            if attempts >= max_retries:
                return {"status": "failed", "error": str(e), "attempts": attempts}
            import time
            time.sleep(retry_delay)


class TaskQueue:
    """异步任务队列

    基于APScheduler, 支持延迟执行/重试/状态查询
    """

    def __init__(self, db_path: str = "data/task_queue.db"):
        self._scheduler = AsyncIOScheduler(
            jobstores={
                'default': SQLAlchemyJobStore(url=f'sqlite:///{db_path}')
            },
            executors={
                'default': ThreadPoolExecutor(10),
            },
            job_defaults={
                'coalesce': False,
                'max_instances': 3,
                'misfire_grace_time': 300,
            }
        )
        self._max_retries = 3
        self._retry_delay = 60  # seconds

    def _resolve_func(self, func_path: str) -> Callable:
        """解析 'module.ClassName.method' 路径到可调用函数"""
        parts = func_path.split(".")
        if len(parts) < 2:
            raise ValueError(f"Invalid func_path: {func_path}")

        module_path = ".".join(parts[:-1])
        attr_name = parts[-1]
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)

    def enqueue(self, name: str, func_path: str,
                args: Optional[list] = None,
                kwargs: Optional[dict] = None,
                delay: int = 0) -> str:
        """将任务加入队列

        Args:
            name: 任务名称
            func_path: 函数路径, e.g. 'engines.dataset_manager.DatasetManager.export_coco'
            args: 位置参数
            kwargs: 关键字参数
            delay: 延迟执行秒数 (0=立即)

        Returns:
            job_id: 任务ID (uuid)
        """
        job_id = str(uuid.uuid4())

        # Register task metadata globally so _execute_task can find it
        _task_registry[job_id] = {
            "func_path": func_path,
            "args": args or [],
            "kwargs": kwargs or {},
            "max_retries": self._max_retries,
            "retry_delay": self._retry_delay,
        }

        if delay > 0:
            run_date = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=delay)
            trigger = DateTrigger(run_date=run_date)
        else:
            trigger = DateTrigger(run_date=datetime.now(timezone.utc).replace(tzinfo=None))

        self._scheduler.add_job(
            _execute_task,
            trigger=trigger,
            id=job_id,
            name=name,
            args=[job_id],
            replace_existing=True,
        )
        return job_id

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """查询任务状态

        Returns:
            {"job_id": str, "status": str, "name": str, ...}
        """
        job = self._scheduler.get_job(job_id)
        if job is None:
            return {"job_id": job_id, "status": "unknown", "name": "not_found"}
        return {
            "job_id": job_id,
            "status": "scheduled" if job.next_run_time else "paused",
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        """列出所有已调度任务"""
        jobs = self._scheduler.get_jobs()
        return [
            {
                "job_id": j.id,
                "name": j.name,
                "status": "scheduled" if j.next_run_time else "paused",
                "next_run": str(j.next_run_time) if j.next_run_time else None,
            }
            for j in jobs
        ]

    def cancel(self, job_id: str) -> bool:
        """取消任务

        Returns:
            True if cancelled, False if not found
        """
        job = self._scheduler.get_job(job_id)
        if job:
            self._scheduler.remove_job(job_id)
            _task_registry.pop(job_id, None)
            return True
        return False

    def start(self) -> None:
        """启动调度器"""
        if not self._scheduler.running:
            self._scheduler.start()

    def stop(self) -> None:
        """停止调度器"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
