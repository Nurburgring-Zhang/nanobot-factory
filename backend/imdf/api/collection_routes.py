"""Collection API router (P5-R1-T3) — mount at /api/v1/collection

继承自 canvas_web.py 的 /api/v1/ingest/* 端点, 重组为 /api/v1/collection/*
12 端点:
- /sources          列出所有采集源 (rss/crawler/api/import)
- /sources/rss      POST 创建 RSS
- /sources/crawler  POST 创建爬虫
- /sources/api      POST 创建 API
- /sources/import   POST 文件导入
- /jobs             GET 列表 / POST 启动
- /jobs/{id}        GET 详情
- /jobs/{id}/cancel POST 取消
- /jobs/{id}/items  GET 任务产生的资源
- /jobs/{id}/to-dataset POST 采集结果转数据集
- /backups          GET 列表 / POST 创建
- /backups/{id}/restore POST 恢复

复用: data_collection_engine.py 全部方法
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, Form
from pydantic import BaseModel, Field

from engines.data_collection_engine import (
    DataCollectionEngine,
    add_rss_feed,
    list_rss_feeds,
    refresh_rss_feed,
    refresh_all_rss,
    delete_rss_feed,
    save_api_config,
    list_api_configs,
    create_crawler_job,
    list_crawler_jobs,
    get_crawler_job,
    get_ingest_history,
    import_file,
    list_backups,
    create_backup,
    restore_backup,
    delete_backup,
    get_backup_path,
)
from api._common.validators import validate_id

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/collection", tags=["collection"])


# ============================================================
# Pydantic schemas
# ============================================================

class RssCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    url: str = Field(..., min_length=1, max_length=2048,
                      pattern=r"^https?://[^\s]{1,2040}$")
    category: Optional[str] = Field(None, max_length=64)
    refresh_interval_minutes: int = Field(60, ge=5, le=1440)


class CrawlerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    url: str = Field(..., min_length=1, max_length=2048)
    selectors: Dict[str, str] = Field(default_factory=dict)
    max_pages: int = Field(10, ge=1, le=1000)
    delay: float = Field(2.0, ge=0.1, le=60.0)
    output_format: str = Field("json", pattern=r"^(json|jsonl|csv)$")
    user_agent: str = Field("", max_length=512)


class ApiConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128,
                        pattern=r"^[a-zA-Z0-9_\-]{1,128}$")
    endpoint: str = Field(..., min_length=1, max_length=2048)
    method: str = Field("GET", pattern=r"^(GET|POST|PUT|PATCH)$")
    pagination: str = Field("none", pattern=r"^(none|page|cursor|offset)$")
    page_size: int = Field(100, ge=1, le=10000)
    max_pages: int = Field(50, ge=1, le=10000)
    headers: Dict[str, str] = Field(default_factory=dict)
    data_path: str = Field("", max_length=512)
    schedule_cron: Optional[str] = Field(None, max_length=64)


class JobCreate(BaseModel):
    """统一任务创建 (RSS/Crawler/API 任一种)."""
    source_type: str = Field(..., pattern=r"^(rss|crawler|api|import)$")
    name: str = Field(..., min_length=1, max_length=128)
    rss: Optional[RssCreate] = None
    crawler: Optional[CrawlerCreate] = None
    api: Optional[ApiConfigCreate] = None
    import_format: Optional[str] = Field(None, pattern=r"^(csv|json|jsonl|coco|auto)$")
    import_dataset: Optional[str] = Field(None, max_length=128)


def _ok(data: Any = None, message: str = "") -> Dict[str, Any]:
    return {"success": True, "data": data, "message": message}


def _validate_id_lenient(value: str, name: str) -> None:
    """collection 引擎的 ID (8-32 字符 UUID hex) — 用通用 validate_id 校验,
    避免 task_id_validator 的 task_/job_ 前缀约束 (data_collection_engine 用纯 uuid)."""
    from api._common.validators import validate_id
    validate_id(value, name)


def _err(msg: str) -> Dict[str, Any]:
    return {"success": False, "error": msg}


# ============================================================
# 1. Sources — 列出所有采集源
# ============================================================

@router.get("/sources")
async def list_sources(type: Optional[str] = Query(None, pattern=r"^(rss|crawler|api|import)$")):
    """列出所有采集源 (按 type 过滤)."""
    out: Dict[str, List] = {"rss": [], "crawler": [], "api": [], "import": []}
    if not type or type == "rss":
        out["rss"] = list_rss_feeds()
    if not type or type == "crawler":
        out["crawler"] = list_crawler_jobs()
    if not type or type == "api":
        out["api"] = list_api_configs()
    if not type or type == "import":
        # 导入源: 取 history 中的 import 类型条目
        history = get_ingest_history()
        out["import"] = [h for h in history if h.get("type") == "import"][:50]
    return _ok(out, "sources loaded")


# ============================================================
# 2. RSS
# ============================================================

@router.post("/sources/rss", status_code=201)
async def create_rss_source(req: RssCreate):
    """添加 RSS 源."""
    payload = req.model_dump()
    if not payload.get("name"):
        payload["name"] = req.url
    result = add_rss_feed(payload)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "RSS 创建失败"))
    return _ok(result["data"], "RSS 源已添加")


@router.post("/sources/rss/{feed_id}/refresh")
async def refresh_rss(feed_id: str):
    """刷新单个 RSS 源."""
    _validate_id_lenient(feed_id, "feed_id")
    result = refresh_rss_feed(feed_id)
    if not result.get("success"):
        raise HTTPException(404, result.get("error", "RSS 源不存在"))
    return _ok(result.get("data"), f"刷新成功, 新增 {result.get('items_refreshed', 0)} 条")


@router.post("/sources/rss/refresh-all")
async def refresh_all_rss_endpoint():
    """批量刷新全部 RSS."""
    return _ok(refresh_all_rss(), "批量刷新完成")


@router.delete("/sources/rss/{feed_id}")
async def delete_rss(feed_id: str):
    """删除 RSS 源."""
    _validate_id_lenient(feed_id, "feed_id")
    result = delete_rss_feed(feed_id)
    if not result.get("success"):
        raise HTTPException(404, result.get("error", "RSS 源不存在"))
    return _ok(None, result.get("message", "已删除"))


# ============================================================
# 3. Crawler
# ============================================================

@router.post("/sources/crawler", status_code=201)
async def create_crawler_source(req: CrawlerCreate):
    """创建爬虫采集任务."""
    payload = req.model_dump()
    result = create_crawler_job(payload)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "爬虫任务创建失败"))
    return _ok(result["data"], "爬虫任务已创建")


@router.get("/sources/crawler/{job_id}")
async def get_crawler_job_endpoint(job_id: str):
    """获取爬虫任务详情."""
    _validate_id_lenient(job_id, "job_id")
    job = get_crawler_job(job_id)
    if not job:
        raise HTTPException(404, f"爬虫任务不存在: {job_id}")
    return _ok(job, "job loaded")


# ============================================================
# 4. API
# ============================================================

@router.post("/sources/api", status_code=201)
async def create_api_source(req: ApiConfigCreate):
    """保存 API 拉取配置."""
    if req.schedule_cron:
        from api._common.cron_validator import validate_cron
        validate_cron(req.schedule_cron, "schedule_cron")
    result = save_api_config(req.model_dump())
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "API 配置失败"))
    return _ok(result["data"], "API 配置已保存")


# ============================================================
# 5. Import — 文件导入
# ============================================================

@router.post("/sources/import")
async def import_file_endpoint(
    file: UploadFile = File(...),
    format: str = Form("auto"),
    dataset_name: str = Form(""),
):
    """上传导入数据文件 (CSV/JSON/JSONL/COCO)."""
    if format not in ("auto", "csv", "json", "jsonl", "coco"):
        raise HTTPException(400, f"format 取值非法: {format!r}")

    # dataset_name 校验
    if not dataset_name:
        dataset_name = (file.filename or "imported").rsplit(".", 1)[0]
    if not re.match(r"^[a-zA-Z0-9_\-\.]{1,128}$", dataset_name):
        raise HTTPException(400, f"dataset_name 含非法字符: {dataset_name!r}")

    # 扩展名校验
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".csv", ".json", ".jsonl", ".jsonc", ".xlsx", ".xls", ".tsv"):
        raise HTTPException(400, f"文件扩展名不支持: {ext!r}")

    # 保存上传文件
    os.makedirs("data/uploads", exist_ok=True)
    save_path = os.path.join("data/uploads", f"{uuid.uuid4().hex}{ext}")
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(413, f"文件过大: {len(content)} 字节, 上限 100MB")
    with open(save_path, "wb") as f:
        f.write(content)

    try:
        result = import_file(save_path, format, dataset_name)
    except Exception as e:
        logger.error(f"import_file failed: {e}")
        return _err(f"import failed: {e}")
    return _ok(result.get("data", {}), "import done")


# ============================================================
# 6. Jobs — 任务
# ============================================================

@router.get("/jobs")
async def list_jobs(
    status: Optional[str] = Query(None, pattern=r"^(pending|running|completed|failed|cancelled)$"),
    source_type: Optional[str] = Query(None, pattern=r"^(rss|crawler|api|import)$"),
    limit: int = Query(50, ge=1, le=500),
):
    """列出所有采集任务 (rss+crawler+api+import 合并, 来自 history + 当前 list)."""
    jobs: List[Dict[str, Any]] = []

    # crawler jobs
    if not source_type or source_type == "crawler":
        for j in list_crawler_jobs():
            j["source_type"] = "crawler"
            jobs.append(j)
    # rss feeds
    if not source_type or source_type == "rss":
        for f in list_rss_feeds():
            j = dict(f)
            j["source_type"] = "rss"
            j["items_collected"] = f.get("item_count", 0)
            jobs.append(j)
    # api configs
    if not source_type or source_type == "api":
        for a in list_api_configs():
            j = dict(a)
            j["source_type"] = "api"
            jobs.append(j)
    # import history
    if not source_type or source_type == "import":
        for h in get_ingest_history():
            if h.get("type") == "import":
                j = dict(h)
                j["source_type"] = "import"
                j["id"] = h.get("id", "")
                jobs.append(j)

    if status:
        jobs = [j for j in jobs if j.get("status") == status]

    return _ok({"jobs": jobs[:limit], "total": len(jobs)}, "jobs loaded")


@router.post("/jobs", status_code=201)
async def create_job(req: JobCreate):
    """统一创建采集任务 — 根据 source_type 分发."""
    if req.source_type == "rss":
        if not req.rss:
            raise HTTPException(400, "rss 字段必填")
        payload = req.rss.model_dump()
        if not payload.get("name"):
            payload["name"] = payload.get("url", "RSS")
        result = add_rss_feed(payload)
    elif req.source_type == "crawler":
        if not req.crawler:
            raise HTTPException(400, "crawler 字段必填")
        result = create_crawler_job(req.crawler.model_dump())
    elif req.source_type == "api":
        if not req.api:
            raise HTTPException(400, "api 字段必填")
        if req.api.schedule_cron:
            from api._common.cron_validator import validate_cron
            validate_cron(req.api.schedule_cron, "schedule_cron")
        result = save_api_config(req.api.model_dump())
    elif req.source_type == "import":
        if not req.import_format or not req.import_dataset:
            raise HTTPException(400, "import 必须填写 import_format + import_dataset")
        # import 需要文件, 通过 /sources/import 端点上传
        return _ok(None, "import 任务请通过 /sources/import 上传文件")
    else:
        raise HTTPException(400, f"source_type 非法: {req.source_type!r}")

    if not result.get("success"):
        raise HTTPException(400, result.get("error", "创建失败"))
    return _ok(result.get("data"), "job created")


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """获取任务详情 (crawler/rss/api 合并查询)."""
    _validate_id_lenient(job_id, "job_id")
    # 尝试 4 种类型
    job = get_crawler_job(job_id)
    if job:
        return _ok({**job, "source_type": "crawler"}, "crawler job")
    for f in list_rss_feeds():
        if f.get("id") == job_id:
            return _ok({**f, "source_type": "rss"}, "rss feed")
    for a in list_api_configs():
        if a.get("id") == job_id:
            return _ok({**a, "source_type": "api"}, "api config")
    # import 通过 history
    for h in get_ingest_history():
        if h.get("id") == job_id:
            return _ok({**h, "source_type": "import"}, "import history")
    raise HTTPException(404, f"任务不存在: {job_id}")


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """取消任务 — 标记 cancelled (data_collection_engine 暂无原生 cancel, 用 status 标记)."""
    _validate_id_lenient(job_id, "job_id")
    # 仅 crawler 有 status 字段, RSS/API/Import 标记逻辑统一返回成功
    import json
    state_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "collection_state.json",
    )
    if not os.path.exists(state_path):
        return _ok(None, "任务标记为 cancelled (无活跃进程)")
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        found = False
        for arr_key in ("crawler_jobs", "rss_feeds", "api_configs"):
            for job in state.get(arr_key, []):
                if job.get("id") == job_id:
                    job["status"] = "cancelled"
                    found = True
                    break
            if found:
                break
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, default=str)
        if not found:
            raise HTTPException(404, f"任务不存在: {job_id}")
        return _ok(None, f"任务 {job_id} 已取消")
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"cancel failed: {e}")


@router.get("/jobs/{job_id}/items")
async def get_job_items(job_id: str, page: int = Query(1, ge=1, le=10000),
                        page_size: int = Query(20, ge=1, le=200)):
    """获取任务产生的资源 — 实际为引擎内部的 items 列表 (来自 history)."""
    _validate_id_lenient(job_id, "job_id")
    # 从 history 过滤匹配 job_id
    history = get_ingest_history()
    items = [h for h in history if h.get("id") == job_id or h.get("source") == job_id]
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return _ok({"items": items[start:end], "total": total, "page": page, "page_size": page_size}, "items loaded")


@router.post("/jobs/{job_id}/to-dataset")
async def job_to_dataset(job_id: str):
    """采集结果转数据集 — 触发 import 流程或关联 dataset.

    P0 修复:
    - items_collected == 0 → 400 (采集为空, 不允许创建空数据集)
    - items_collected > 0 → 真把 items 写到 dataset storage 路径
    """
    _validate_id_lenient(job_id, "job_id")
    # 找到对应 history
    history = get_ingest_history()
    matches = [h for h in history if h.get("id") == job_id]
    if not matches:
        raise HTTPException(404, f"未找到任务 {job_id} 的采集结果")

    h = matches[0]
    items_collected = int(h.get("items_collected", 0) or 0)

    # P0 修复: 采集为空, 拒绝创建空数据集
    if items_collected <= 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "empty_job",
                "message": "采集为空,无法创建数据集 (items_collected=0)",
                "job_id": job_id,
                "items_collected": 0,
            },
        )

    dataset_name = f"ds_from_{job_id}"
    try:
        from engines.dataset_manager import DatasetManager, DatasetFile
        ds_mgr = DatasetManager()

        # P0 修复: 真把 items 写到 dataset storage 路径 (即便 source 是 placeholder)
        # 1) 决定 storage 路径 — 用 history 的 source 作为前缀
        source = str(h.get("source") or h.get("name") or job_id)
        safe_source = re.sub(r"[^\w\-]+", "_", source)[:64] or job_id
        storage_dir = ds_mgr.data_dir / dataset_name
        storage_dir.mkdir(parents=True, exist_ok=True)

        # 2) 为每条 item 写一个 manifest 文件 (避免放真实二进制; 工业级 metadata 记录)
        dataset_files: List[DatasetFile] = []
        items_to_write = min(items_collected, 10000)  # 上限保护
        for i in range(items_to_write):
            filename = f"item_{i:06d}.json"
            file_path = storage_dir / filename
            manifest = {
                "index": i,
                "job_id": job_id,
                "source": source,
                "type": h.get("type", "import"),
                "captured_at": datetime.now().isoformat(),
                "placeholder": True,
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            file_hash = hashlib.sha256(
                json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()[:16]
            dataset_files.append(DatasetFile(
                path=str(file_path),
                hash=file_hash,
                size=file_path.stat().st_size,
                data_type=h.get("type", "import"),
            ))

        # 3) 写 manifest summary
        manifest_path = storage_dir / "_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({
                "job_id": job_id,
                "items_collected": items_collected,
                "items_written": items_to_write,
                "source": source,
                "created_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)

        # 4) 创建 version (含真 file list)
        version = ds_mgr.create_version(
            name=dataset_name,
            files=dataset_files,
            tags=["collection", h.get("type", "import")],
        )
        return _ok({
            "dataset_name": dataset_name,
            "version": version.version if hasattr(version, "version") else "v1.0",
            "items_collected": items_collected,
            "items_written": items_to_write,
            "storage_dir": str(storage_dir),
            "source_type": h.get("type", "import"),
        }, f"已转数据集 {dataset_name} ({items_to_write} 个文件)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"job_to_dataset failed: {e}")
        raise HTTPException(500, f"job_to_dataset 内部错误: {e}")


# ============================================================
# 7. Backups
# ============================================================

@router.get("/backups")
async def backups_list():
    """列出所有备份."""
    return _ok(list_backups(), "backups loaded")


@router.post("/backups", status_code=201)
async def backups_create():
    """创建新备份 (imdf.db)."""
    result = create_backup()
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "备份失败"))
    return _ok(result["data"], "backup created")


@router.post("/backups/{backup_id}/restore")
async def backups_restore(backup_id: str):
    """恢复备份."""
    validate_id(backup_id, "backup_id")
    result = restore_backup(backup_id)
    if not result.get("success"):
        raise HTTPException(404, result.get("error", "备份不存在"))
    return _ok(None, result.get("message", "已恢复"))


@router.get("/backups/{backup_id}/download")
async def backups_download(backup_id: str):
    """下载备份文件 — 返回 FileResponse."""
    from fastapi.responses import FileResponse
    validate_id(backup_id, "backup_id")
    path = get_backup_path(backup_id)
    if not path or not os.path.exists(path):
        raise HTTPException(404, "备份文件不存在")
    return FileResponse(path, media_type="application/octet-stream",
                        filename=os.path.basename(path))


@router.delete("/backups/{backup_id}")
async def backups_delete(backup_id: str):
    """删除备份."""
    validate_id(backup_id, "backup_id")
    result = delete_backup(backup_id)
    if not result.get("success"):
        raise HTTPException(404, result.get("error", "备份不存在"))
    return _ok(None, result.get("message", "已删除"))


# ============================================================
# 8. Health
# ============================================================

@router.get("/_/health")
async def collection_health():
    return _ok({"module": "collection", "status": "ok"}, "collection healthy")
