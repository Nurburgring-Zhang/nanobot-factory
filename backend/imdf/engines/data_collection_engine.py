"""
数据采集引擎 - Web爬虫/RSS/API拉取/备份/导入管理
==============================================
为 data-collection.js 前端页面提供后端支持。
状态持久化到 JSON 文件，采集历史记录到 imdf.db。
"""
import os
import json
import time
import uuid
import shutil
import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


# ===== 持久化文件路径 =====
def _data_dir():
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(d, exist_ok=True)
    return d


_STATE_FILE = os.path.join(_data_dir(), "collection_state.json")
_BACKUP_DIR = os.path.join(_data_dir(), "backups")


def _load_state() -> dict:
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"crawler_jobs": [], "rss_feeds": [], "api_configs": [], "history": []}


def _save_state(state: dict):
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, default=str)


def _get_db_path():
    return os.path.join(_data_dir(), "imdf.db")


def _log_history(entry: dict):
    """记录采集历史到 state + SQLite"""
    state = _load_state()
    entry.setdefault("id", str(uuid.uuid4())[:8])
    entry.setdefault("created_at", datetime.now().isoformat())
    state.setdefault("history", []).insert(0, entry)
    # 只保留最近500条
    if len(state["history"]) > 500:
        state["history"] = state["history"][:500]
    _save_state(state)
    # 同时写入 SQLite (如果存在)
    try:
        db_path = _get_db_path()
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            conn.execute(
                """CREATE TABLE IF NOT EXISTS collection_history (
                    id TEXT PRIMARY KEY, type TEXT, source TEXT, status TEXT,
                    items_collected INTEGER, duration TEXT, created_at TEXT,
                    extra TEXT
                )"""
            )
            conn.execute(
                "INSERT OR REPLACE INTO collection_history VALUES (?,?,?,?,?,?,?,?)",
                (
                    entry.get("id", ""),
                    entry.get("type", ""),
                    entry.get("source", entry.get("name", "")),
                    entry.get("status", "pending"),
                    entry.get("items_collected", 0),
                    entry.get("duration", ""),
                    entry.get("created_at", datetime.now().isoformat()),
                    json.dumps(entry, ensure_ascii=False),
                ),
            )
            conn.commit()
            conn.close()
    except Exception as e:
        logger.error(f"Operation failed: {e}")


# ============================================================
#   Crawler 爬虫任务
# ============================================================
def create_crawler_job(job: dict) -> dict:
    """创建新的爬虫任务"""
    job_id = str(uuid.uuid4())[:8]
    record = {
        "id": job_id,
        "name": job.get("name", "未命名"),
        "url": job.get("url", ""),
        "selectors": job.get("selectors", {}),
        "max_pages": job.get("max_pages", 10),
        "delay": job.get("delay", 2.0),
        "output_format": job.get("output_format", "json"),
        "user_agent": job.get("user_agent", ""),
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "items_collected": 0,
    }

    state = _load_state()
    state.setdefault("crawler_jobs", []).insert(0, record)
    if len(state["crawler_jobs"]) > 200:
        state["crawler_jobs"] = state["crawler_jobs"][:200]
    _save_state(state)

    # 模拟异步执行
    _log_history({
        "id": job_id,
        "type": "crawler",
        "name": record["name"],
        "source": record["url"],
        "status": "created",
        "items_collected": 0,
    })

    return {"success": True, "job_id": job_id, "data": record}


def list_crawler_jobs() -> List[dict]:
    state = _load_state()
    return state.get("crawler_jobs", [])


def get_crawler_job(job_id: str) -> Optional[dict]:
    for job in list_crawler_jobs():
        if job.get("id") == job_id:
            return job
    return None


# ============================================================
#   RSS 源管理
# ============================================================
def add_rss_feed(feed: dict) -> dict:
    """添加RSS源"""
    feed_id = str(uuid.uuid4())[:8]
    record = {
        "id": feed_id,
        "name": feed.get("name", "未命名"),
        "url": feed.get("url", ""),
        "status": "active",
        "item_count": 0,
        "created_at": datetime.now().isoformat(),
        "last_refreshed": None,
    }

    state = _load_state()
    state.setdefault("rss_feeds", []).insert(0, record)
    _save_state(state)

    _log_history({
        "id": feed_id,
        "type": "rss",
        "name": record["name"],
        "source": record["url"],
        "status": "added",
        "items_collected": 0,
    })

    return {"success": True, "feed_id": feed_id, "data": record}


def list_rss_feeds() -> List[dict]:
    state = _load_state()
    return state.get("rss_feeds", [])


def refresh_rss_feed(feed_id: str) -> dict:
    """刷新单个RSS源 (模拟)"""
    state = _load_state()
    for feed in state.get("rss_feeds", []):
        if feed.get("id") == feed_id:
            # 模拟采集5-50条
            import random
            count = random.randint(5, 50)
            feed["item_count"] = feed.get("item_count", 0) + count
            feed["last_refreshed"] = datetime.now().isoformat()
            feed["status"] = "active"
            _save_state(state)

            _log_history({
                "type": "rss",
                "name": feed.get("name", ""),
                "source": feed.get("url", ""),
                "status": "refreshed",
                "items_collected": count,
                "duration": f"{random.uniform(1, 5):.1f}s",
            })
            return {"success": True, "data": feed, "items_refreshed": count}
    return {"success": False, "error": f"RSS源不存在: {feed_id}"}


def refresh_all_rss() -> dict:
    """刷新全部RSS源"""
    state = _load_state()
    total = 0
    for feed in state.get("rss_feeds", []):
        import random
        count = random.randint(3, 30)
        feed["item_count"] = feed.get("item_count", 0) + count
        feed["last_refreshed"] = datetime.now().isoformat()
        total += count
    _save_state(state)

    _log_history({
        "type": "rss",
        "name": "批量刷新",
        "source": f"{len(state.get('rss_feeds', []))} 个源",
        "status": "refreshed",
        "items_collected": total,
    })
    return {"success": True, "feeds_refreshed": len(state.get("rss_feeds", [])), "total_items": total}


def delete_rss_feed(feed_id: str) -> dict:
    state = _load_state()
    before = len(state.get("rss_feeds", []))
    state["rss_feeds"] = [f for f in state.get("rss_feeds", []) if f.get("id") != feed_id]
    if len(state["rss_feeds"]) == before:
        return {"success": False, "error": f"RSS源不存在: {feed_id}"}
    _save_state(state)
    return {"success": True, "message": "RSS源已删除"}


# ============================================================
#   API 拉取配置
# ============================================================
def save_api_config(config: dict) -> dict:
    """保存API拉取配置"""
    config_id = str(uuid.uuid4())[:8]
    record = {
        "id": config_id,
        "name": config.get("name", "未命名"),
        "endpoint": config.get("endpoint", ""),
        "method": config.get("method", "GET"),
        "pagination": config.get("pagination", "none"),
        "page_size": config.get("page_size", 100),
        "max_pages": config.get("max_pages", 50),
        "headers": config.get("headers", {}),
        "data_path": config.get("data_path", ""),
        "created_at": datetime.now().isoformat(),
    }

    state = _load_state()
    state.setdefault("api_configs", []).insert(0, record)
    _save_state(state)

    _log_history({
        "type": "api_pull",
        "name": record["name"],
        "source": record["endpoint"],
        "status": "configured",
        "items_collected": 0,
    })

    return {"success": True, "config_id": config_id, "data": record}


def list_api_configs() -> List[dict]:
    state = _load_state()
    return state.get("api_configs", [])


# ============================================================
#   采集历史
# ============================================================
def get_ingest_history() -> List[dict]:
    """获取所有采集/导入历史"""
    state = _load_state()
    return state.get("history", [])


# ============================================================
#   文件导入 (复用 IngestionEngine)
# ============================================================
def import_file(file_path: str, format_type: str, dataset_name: str) -> dict:
    """导入文件到数据库"""
    from engines.ingestion_engine import IngestionEngine
    engine = IngestionEngine()

    if format_type == "csv":
        result = engine.import_csv(file_path, dataset_name)
    elif format_type == "jsonl":
        # JSONL 按行解析
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}
        with open(file_path, "r", encoding="utf-8") as f:
            rows = []
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        if not rows:
            return {"success": False, "error": "JSONL文件无有效数据"}
        result = engine._insert_rows(rows, dataset_name)
    elif format_type in ("json", "coco"):
        result = engine.import_json(file_path, dataset_name)
    else:
        # auto-detect
        ext = Path(file_path).suffix.lower()
        if ext == ".csv":
            result = engine.import_csv(file_path, dataset_name)
        elif ext == ".jsonl":
            return import_file(file_path, "jsonl", dataset_name)
        else:
            result = engine.import_json(file_path, dataset_name)

    # 记录历史
    if result.get("success"):
        _log_history({
            "type": "import",
            "name": dataset_name,
            "source": file_path,
            "format": format_type,
            "status": "completed",
            "items_collected": result.get("data", {}).get("rows_imported", 0),
        })
    else:
        _log_history({
            "type": "import",
            "name": dataset_name,
            "source": file_path,
            "format": format_type,
            "status": "failed",
            "items_collected": 0,
        })

    return result


# ============================================================
#   数据备份
# ============================================================
def _ensure_backup_dir():
    os.makedirs(_BACKUP_DIR, exist_ok=True)


def list_backups() -> List[dict]:
    """列出所有备份"""
    _ensure_backup_dir()
    backups = []
    if os.path.exists(_BACKUP_DIR):
        for fname in sorted(os.listdir(_BACKUP_DIR), reverse=True):
            fpath = os.path.join(_BACKUP_DIR, fname)
            if os.path.isfile(fpath) and fname.endswith(".db"):
                stat = os.stat(fpath)
                backups.append({
                    "id": hashlib.md5(fname.encode()).hexdigest()[:8],
                    "filename": fname,
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "status": "completed",
                    "item_count": 0,
                })
    return backups


def create_backup() -> dict:
    """创建数据备份 (备份 imdf.db)"""
    _ensure_backup_dir()
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        return {"success": False, "error": "数据库文件不存在，无法备份"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}.db"
    backup_path = os.path.join(_BACKUP_DIR, backup_name)

    try:
        shutil.copy2(db_path, backup_path)
        # 也备份状态文件
        if os.path.exists(_STATE_FILE):
            state_backup = os.path.join(_BACKUP_DIR, f"state_{timestamp}.json")
            shutil.copy2(_STATE_FILE, state_backup)

        return {
            "success": True,
            "data": {
                "filename": backup_name,
                "size": os.path.getsize(backup_path),
                "created_at": datetime.now().isoformat(),
                "status": "completed",
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def restore_backup(backup_id: str) -> dict:
    """恢复备份"""
    _ensure_backup_dir()
    for fname in os.listdir(_BACKUP_DIR):
        if fname.endswith(".db") and hashlib.md5(fname.encode()).hexdigest()[:8] == backup_id:
            backup_path = os.path.join(_BACKUP_DIR, fname)
            db_path = _get_db_path()
            try:
                shutil.copy2(backup_path, db_path)
                return {"success": True, "message": f"已从 {fname} 恢复"}
            except Exception as e:
                return {"success": False, "error": str(e)}
    return {"success": False, "error": f"备份不存在: {backup_id}"}


def delete_backup(backup_id: str) -> dict:
    """删除备份"""
    _ensure_backup_dir()
    for fname in os.listdir(_BACKUP_DIR):
        if fname.endswith(".db") and hashlib.md5(fname.encode()).hexdigest()[:8] == backup_id:
            os.remove(os.path.join(_BACKUP_DIR, fname))
            return {"success": True, "message": f"备份 {fname} 已删除"}
    return {"success": False, "error": f"备份不存在: {backup_id}"}


def get_backup_path(backup_id: str) -> Optional[str]:
    """根据ID获取备份文件路径"""
    _ensure_backup_dir()
    for fname in os.listdir(_BACKUP_DIR):
        if fname.endswith(".db") and hashlib.md5(fname.encode()).hexdigest()[:8] == backup_id:
            return os.path.join(_BACKUP_DIR, fname)
    return None


class DataCollectionEngine:
    """统一入口类 (兼容旧调用方式)"""

    def __init__(self):
        pass

    # Crawler
    def create_crawler_job(self, job: dict) -> dict:
        return create_crawler_job(job)

    def list_crawler_jobs(self) -> List[dict]:
        return list_crawler_jobs()

    # RSS
    def add_rss_feed(self, feed: dict) -> dict:
        return add_rss_feed(feed)

    def list_rss_feeds(self) -> List[dict]:
        return list_rss_feeds()

    def refresh_rss_feed(self, feed_id: str) -> dict:
        return refresh_rss_feed(feed_id)

    def refresh_all_rss(self) -> dict:
        return refresh_all_rss()

    def delete_rss_feed(self, feed_id: str) -> dict:
        return delete_rss_feed(feed_id)

    # API config
    def save_api_config(self, config: dict) -> dict:
        return save_api_config(config)

    def list_api_configs(self) -> List[dict]:
        return list_api_configs()

    # History
    def get_ingest_history(self) -> List[dict]:
        return get_ingest_history()

    # Import
    def import_file(self, file_path: str, format_type: str, dataset_name: str) -> dict:
        return import_file(file_path, format_type, dataset_name)

    # Backup
    def list_backups(self) -> List[dict]:
        return list_backups()

    def create_backup(self) -> dict:
        return create_backup()

    def restore_backup(self, backup_id: str) -> dict:
        return restore_backup(backup_id)

    def delete_backup(self, backup_id: str) -> dict:
        return delete_backup(backup_id)

    def get_backup_path(self, backup_id: str) -> Optional[str]:
        return get_backup_path(backup_id)
