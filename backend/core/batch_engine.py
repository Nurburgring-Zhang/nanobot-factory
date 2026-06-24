"""Batch production engine — task scheduling, worker pool, progress tracking"""

import uuid
import time
import json
import asyncio
import logging
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineType(str, Enum):
    IMAGE_CAPTION = "image_caption"
    CONVERSATION = "conversation"
    INTERLEAVED = "interleaved"
    VIDEO_CAPTION = "video_caption"
    DOC_PARSING = "doc_parsing"
    DETECTION = "detection"
    QUALITY_FILTER = "quality_filter"
    FORMAT_EXPORT = "format_export"
    CUSTOM = "custom"


@dataclass
class TaskProgress:
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    start_time: float = 0.0
    elapsed: float = 0.0
    eta_seconds: float = 0.0


@dataclass
class ProductionTask:
    id: str
    project_id: str
    user_id: str
    pipeline_type: PipelineType
    params: Dict[str, Any]
    input_paths: List[str]
    output_dir: str
    status: TaskStatus = TaskStatus.PENDING
    progress: TaskProgress = field(default_factory=TaskProgress)
    created_at: str = ""
    completed_at: str = ""
    output_manifest: Dict[str, Any] = field(default_factory=dict)
    worker_count: int = 1


class PipelineWorker:
    """单个worker执行管线的具体操作"""
    async def process_item(self, item: Any, params: Dict[str, Any]) -> Any:
        """处理单个item，子类重写"""
        raise NotImplementedError


class BatchEngine:
    """批量生产核心引擎"""

    def __init__(self, max_workers: int = 4):
        self._tasks: Dict[str, ProductionTask] = {}
        self._workers: Dict[PipelineType, PipelineWorker] = {}
        self._max_workers = max_workers
        self._running: Dict[str, asyncio.Task] = {}

    def register_worker(self, pipeline_type: PipelineType, worker: PipelineWorker):
        self._workers[pipeline_type] = worker

    def create_task(
        self,
        project_id: str,
        user_id: str,
        pipeline_type: PipelineType,
        input_paths: List[str],
        output_dir: str,
        params: Optional[Dict[str, Any]] = None,
        worker_count: int = 1,
    ) -> ProductionTask:
        task = ProductionTask(
            id=f"t-{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            user_id=user_id,
            pipeline_type=pipeline_type,
            params=params or {},
            input_paths=input_paths,
            output_dir=output_dir,
            worker_count=min(worker_count, self._max_workers),
            created_at=datetime.now().isoformat(),
        )
        self._tasks[task.id] = task
        return task

    async def start_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status != TaskStatus.PENDING:
            return False

        worker = self._workers.get(task.pipeline_type)
        if not worker and task.pipeline_type != PipelineType.FORMAT_EXPORT:
            logger.warning(f"No worker registered for {task.pipeline_type}")
            return False

        task.status = TaskStatus.RUNNING
        task.progress.start_time = time.time()
        task.progress.total = len(task.input_paths)

        # 异步执行
        run_task = asyncio.create_task(self._run_batch(task, worker))
        self._running[task_id] = run_task
        return True

    async def _run_batch(self, task: ProductionTask, worker: Optional[PipelineWorker]):
        """分批执行"""
        import os

        os.makedirs(task.output_dir, exist_ok=True)

        batch_size = task.params.get("batch_size", 10)
        results = []

        sem = asyncio.Semaphore(task.worker_count)

        for i in range(0, len(task.input_paths), batch_size):
            if task.status == TaskStatus.CANCELLED:
                logger.info(f"Task {task.id} was cancelled, aborting")
                return

            batch = task.input_paths[i : i + batch_size]
            batch_results = []

            async def process_one(item):
                async with sem:
                    try:
                        if worker:
                            return await worker.process_item(item, task.params)
                        return {"input": item, "status": "processed"}
                    except Exception as e:
                        logger.error(f"Item failed: {item}: {e}")
                        task.progress.failed += 1
                        task.progress.errors.append(str(e)[:100])
                        return None

            batch_tasks = [process_one(item) for item in batch]
            batch_results = await asyncio.gather(*batch_tasks)

            # 收集有效结果
            for r in batch_results:
                if r is not None:
                    results.append(r)
                    task.progress.completed += 1
                else:
                    task.progress.skipped += 1

            # 更新进度
            elapsed = time.time() - task.progress.start_time
            task.progress.elapsed = elapsed
            if task.progress.completed > 0:
                rate = task.progress.completed / elapsed
                task.progress.eta_seconds = (
                    (task.progress.total - task.progress.completed) / rate
                    if rate > 0
                    else 0
                )

        # 写入结果
        manifest_path = os.path.join(task.output_dir, "manifest.json")
        task.output_manifest = {
            "task_id": task.id,
            "total": task.progress.total,
            "completed": task.progress.completed,
            "failed": task.progress.failed,
            "skipped": task.progress.skipped,
            "elapsed_seconds": task.progress.elapsed,
            "output_files": [
                os.path.join(task.output_dir, f)
                for f in os.listdir(task.output_dir)
                if f != "manifest.json"
            ],
        }
        with open(manifest_path, "w") as f:
            json.dump(task.output_manifest, f, indent=2, ensure_ascii=False)

        task.status = (
            TaskStatus.COMPLETED
            if task.progress.failed == 0
            else TaskStatus.FAILED
        )
        task.completed_at = datetime.now().isoformat()
        logger.info(
            f"Task {task.id} completed: {task.progress.completed}/{task.progress.total}"
        )

    def get_task(self, task_id: str) -> Optional[ProductionTask]:
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            task.status = TaskStatus.CANCELLED
            return True
        return False

    def get_user_tasks(self, user_id: str) -> List[ProductionTask]:
        return [t for t in self._tasks.values() if t.user_id == user_id]

    def get_project_tasks(self, project_id: str) -> List[ProductionTask]:
        return [t for t in self._tasks.values() if t.project_id == project_id]
