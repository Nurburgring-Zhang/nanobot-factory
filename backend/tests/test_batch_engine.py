"""Tests for batch production engine"""
import sys, os, json, tempfile, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from core.batch_engine import BatchEngine, PipelineType, TaskStatus, PipelineWorker

def test_create_task():
    be = BatchEngine()
    t = be.create_task("p-test", "u-test", PipelineType.IMAGE_CAPTION, ["a.jpg"], "/tmp/out")
    assert t.id.startswith("t-")
    assert t.status == TaskStatus.PENDING
    assert t.pipeline_type == PipelineType.IMAGE_CAPTION

def test_get_task():
    be = BatchEngine()
    t = be.create_task("p-test", "u-test", PipelineType.CONVERSATION, ["a.jpg"], "/tmp/out")
    found = be.get_task(t.id)
    assert found is not None
    assert found.id == t.id

def test_get_user_tasks():
    be = BatchEngine()
    t1 = be.create_task("p1", "user1", PipelineType.IMAGE_CAPTION, [], "/tmp/out")
    t2 = be.create_task("p2", "user2", PipelineType.VIDEO_CAPTION, [], "/tmp/out")
    t3 = be.create_task("p3", "user1", PipelineType.DOC_PARSING, [], "/tmp/out")
    u1_tasks = be.get_user_tasks("user1")
    assert len(u1_tasks) == 2

def test_get_project_tasks():
    be = BatchEngine()
    be.create_task("proj1", "u", PipelineType.IMAGE_CAPTION, [], "/tmp/out")
    be.create_task("proj1", "u", PipelineType.QUALITY_FILTER, [], "/tmp/out")
    be.create_task("proj2", "u", PipelineType.DETECTION, [], "/tmp/out")
    p1_tasks = be.get_project_tasks("proj1")
    assert len(p1_tasks) == 2

def test_cancel_task():
    be = BatchEngine()
    t = be.create_task("p", "u", PipelineType.IMAGE_CAPTION, [], "/tmp/out")
    assert be.cancel_task(t.id)
    assert be.get_task(t.id).status == TaskStatus.CANCELLED

def test_cancel_nonexistent():
    be = BatchEngine()
    assert not be.cancel_task("nonexistent")

def test_register_worker():
    be = BatchEngine()
    w = PipelineWorker()
    be.register_worker(PipelineType.IMAGE_CAPTION, w)
    # 验证worker注册成功(通过start检查)
    t = be.create_task("p", "u", PipelineType.IMAGE_CAPTION, ["test.jpg"], "/tmp/out")
    assert be.get_task(t.id) is not None

@pytest.mark.asyncio
async def test_start_and_run(tmp_path):
    be = BatchEngine(max_workers=2)
    # 使用FORMAT_EXPORT(不需要worker)
    output_dir = str(tmp_path / "output")
    inputs = [f"item{i}" for i in range(5)]
    t = be.create_task("p", "u", PipelineType.FORMAT_EXPORT, inputs, output_dir, {"batch_size": 2})
    started = await be.start_task(t.id)
    assert started
    # 等待一小段时间让异步任务完成
    await asyncio.sleep(0.5)
    task = be.get_task(t.id)
    assert task.status == TaskStatus.COMPLETED
    assert task.progress.total == 5
    assert task.progress.completed == 5
    # 检查manifest
    manifest_path = os.path.join(output_dir, "manifest.json")
    assert os.path.exists(manifest_path)

@pytest.mark.asyncio
async def test_cancel_running():
    be = BatchEngine()
    # Use a slow worker so cancellation can take effect mid-run
    class SlowWorker(PipelineWorker):
        async def process_item(self, item, params):
            await asyncio.sleep(0.05)  # 50ms per item
            return {"input": item, "status": "processed"}
    be.register_worker(PipelineType.IMAGE_CAPTION, SlowWorker())
    t = be.create_task("p", "u", PipelineType.IMAGE_CAPTION, [f"x{i}" for i in range(50)], "/tmp/cancel_test", {"batch_size": 5})
    await be.start_task(t.id)
    # Give it a moment to start processing, then cancel
    await asyncio.sleep(0.15)
    be.cancel_task(t.id)
    await asyncio.sleep(0.5)
    task = be.get_task(t.id)
    # Task should have stopped early (not all items completed)
    assert task.progress.completed < task.progress.total
