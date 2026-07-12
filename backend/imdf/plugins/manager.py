"""VDP-2026 R5 — Plugin Ecosystem.

Platform extensions register into the bus and become first-class capabilities:

  POST /api/v1/plugins                 — register a plugin (id, name, owner, manifest_url, capabilities, hooks)
  GET  /api/v1/plugins                  — list (filter by tag / status / owner)
  GET  /api/v1/plugins/{id}             — fetch manifest
  POST /api/v1/plugins/{id}/invoke      — invoke a plugin endpoint
  POST /api/v1/plugins/{id}/enable      — enable/disable
  GET  /api/v1/plugins/categories

Each plugin contributes *additional capabilities* on top of the 47 R1
modules. Plugins can be sourced from internal teams, third-party vendors, or
the open-source community.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = __import__("logging").getLogger(__name__)


_DB_PATH: Optional[Path] = None


def configure_db(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _init_db()


def get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        backend = Path(__file__).resolve().parent.parent.parent
        _DB_PATH = backend / "data" / "plugins.db"
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _init_db()
    return _DB_PATH


def _conn() -> sqlite3.Connection:
    p = get_db_path()
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plugins (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1.0.0',
                owner TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT 'community',
                manifest_json TEXT DEFAULT '{}',
                capabilities_json TEXT DEFAULT '[]',
                hooks_json TEXT DEFAULT '[]',
                tags_csv TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                trust_level TEXT NOT NULL DEFAULT 'verified',
                install_path TEXT DEFAULT '',
                registered_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plugin_invocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_id TEXT NOT NULL,
                capability_id TEXT NOT NULL,
                inputs_json TEXT DEFAULT '{}',
                outputs_json TEXT DEFAULT '{}',
                status TEXT NOT NULL,
                duration_ms INTEGER DEFAULT 0,
                actor TEXT DEFAULT 'system',
                created_at TEXT NOT NULL
            );
            """
        )


class PluginStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    PENDING_REVIEW = "pending_review"
    DEPRECATED = "deprecated"


class TrustLevel(str, Enum):
    VERIFIED = "verified"   # signed by us
    OFFICIAL = "official"   # first-party
    COMMUNITY = "community"
    EXPERIMENTAL = "experimental"


@dataclass
class Plugin:
    id: str
    name: str
    version: str
    owner: str
    description: str
    category: str
    manifest: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[Dict[str, Any]] = field(default_factory=list)
    hooks: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    status: str = PluginStatus.ACTIVE.value
    trust_level: str = TrustLevel.VERIFIED.value
    install_path: str = ""
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Sample plugin registry (3 starter plugins)
SAMPLE_PLUGINS = [
    {
        "id": "plugin-yolo-trainer",
        "name": "YOLO Trainer",
        "version": "0.9.0",
        "owner": "ultralytics-vendor",
        "description": "在 COCO / YOLO 数据集上微调 YOLOv8 / YOLOv11,导出 ONNX。",
        "category": "training",
        "manifest": {"repo": "github.com/ultralytics/ultralytics", "license": "AGPL-3.0"},
        "capabilities": [
            {"id": "plugin.yolo.train", "name": "训练 YOLO 模型", "input_schema": {"data_yaml": "string", "epochs": "integer"}},
            {"id": "plugin.yolo.export", "name": "导出 ONNX", "input_schema": {"weights": "string", "format": "string"}},
        ],
        "hooks": ["on_dataset.linked"],
        "tags": ["yolo", "训练", "导出"],
        "trust_level": "verified",
    },
    {
        "id": "plugin-llava-finetune",
        "name": "LLaVA 微调框架",
        "version": "1.4.0",
        "owner": "haotian-vendor",
        "description": "LLaVA-1.5 / 1.6 多模态指令微调 + LoRA。",
        "category": "training",
        "manifest": {"repo": "github.com/haotian-liu/LLaVA", "license": "Apache-2.0"},
        "capabilities": [
            {"id": "plugin.llava.train", "name": "微调 LLaVA", "input_schema": {"model_path": "string", "data_path": "string"}},
            {"id": "plugin.llava.eval", "name": "LLaVA-Bench 评测", "input_schema": {"model_path": "string"}},
        ],
        "hooks": ["on_dataset.exported", "on_dataset.linked"],
        "tags": ["llava", "多模态", "指令微调"],
        "trust_level": "verified",
    },
    {
        "id": "plugin-coda-eval",
        "name": "CoDet / Coverage 评测",
        "version": "0.3.0",
        "owner": "third-party-eval",
        "description": "细粒度类别覆盖度评估 + 训练-测试偏差检测。",
        "category": "evaluation",
        "manifest": {"repo": "github.com/3rd-eval/coda", "license": "MIT"},
        "capabilities": [
            {"id": "plugin.coda.coverage", "name": "类别覆盖度", "input_schema": {"dataset_id": "string"}},
            {"id": "plugin.coda.shift", "name": "分布漂移", "input_schema": {"dataset_id_a": "string", "dataset_id_b": "string"}},
        ],
        "hooks": ["on_dataset.exported", "on_qc.completed"],
        "tags": ["评测", "覆盖度", "分布漂移"],
        "trust_level": "community",
    },
]


class PluginManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    def ensure_samples(self) -> None:
        with _conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM plugins").fetchone()[0]
            if count > 0:
                return
        for sample in SAMPLE_PLUGINS:
            self.register(Plugin(
                id=sample["id"],
                name=sample["name"],
                version=sample["version"],
                owner=sample["owner"],
                description=sample["description"],
                category=sample["category"],
                manifest=sample["manifest"],
                capabilities=sample["capabilities"],
                hooks=sample["hooks"],
                tags=sample["tags"],
                trust_level=sample["trust_level"],
            ))

    def register(self, plugin: Plugin) -> Plugin:
        with self._lock:
            plugin.updated_at = datetime.now(timezone.utc).isoformat()
            with _conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO plugins (
                        id, name, version, owner, description, category,
                        manifest_json, capabilities_json, hooks_json,
                        tags_csv, status, trust_level, install_path,
                        registered_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        plugin.id, plugin.name, plugin.version, plugin.owner,
                        plugin.description, plugin.category,
                        json.dumps(plugin.manifest, ensure_ascii=False, default=str),
                        json.dumps(plugin.capabilities, ensure_ascii=False, default=str),
                        json.dumps(plugin.hooks, ensure_ascii=False, default=str),
                        ",".join(plugin.tags), plugin.status, plugin.trust_level,
                        plugin.install_path, plugin.registered_at, plugin.updated_at,
                    ),
                )
            return plugin

    def list(self, tag: Optional[str] = None, status: Optional[str] = None,
             owner: Optional[str] = None, limit: int = 200) -> List[Plugin]:
        sql = "SELECT * FROM plugins WHERE 1=1"
        args: List[Any] = []
        if status:
            sql += " AND status = ?"
            args.append(status)
        if owner:
            sql += " AND owner = ?"
            args.append(owner)
        sql += " ORDER BY registered_at DESC LIMIT ?"
        args.append(limit)
        with _conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        out = []
        for r in rows:
            p = self._row_to_plugin(r)
            if tag and tag not in p.tags:
                continue
            out.append(p)
        return out

    def _row_to_plugin(self, r: sqlite3.Row) -> Plugin:
        return Plugin(
            id=r["id"], name=r["name"], version=r["version"], owner=r["owner"],
            description=r["description"], category=r["category"],
            manifest=json.loads(r["manifest_json"] or "{}"),
            capabilities=json.loads(r["capabilities_json"] or "[]"),
            hooks=json.loads(r["hooks_json"] or "[]"),
            tags=[t for t in (r["tags_csv"] or "").split(",") if t],
            status=r["status"], trust_level=r["trust_level"],
            install_path=r["install_path"] or "",
            registered_at=r["registered_at"], updated_at=r["updated_at"],
        )

    def get(self, pid: str) -> Optional[Plugin]:
        with _conn() as conn:
            row = conn.execute("SELECT * FROM plugins WHERE id = ?", (pid,)).fetchone()
        if not row:
            return None
        return self._row_to_plugin(row)

    def set_status(self, pid: str, status: str) -> bool:
        with _conn() as conn:
            cur = conn.execute(
                "UPDATE plugins SET status = ?, updated_at = ? WHERE id = ?",
                (status, datetime.now(timezone.utc).isoformat(), pid),
            )
            return (cur.rowcount or 0) > 0

    def invoke(self, pid: str, capability_id: str, inputs: Dict[str, Any],
               actor: str = "system") -> Dict[str, Any]:
        plugin = self.get(pid)
        if plugin is None or plugin.status != PluginStatus.ACTIVE.value:
            raise ValueError(f"插件 {pid} 不存在或未启用")
        cap = next((c for c in plugin.capabilities if c["id"] == capability_id), None)
        if cap is None:
            raise ValueError(f"插件 {pid} 不暴露能力 {capability_id}")

        started = time.perf_counter()
        try:
            outputs = self._safe_execute(plugin, cap, inputs)
            duration = int((time.perf_counter() - started) * 1000)
            status = "success"
            error = ""
        except Exception as e:
            outputs = {"echo": inputs}
            duration = int((time.perf_counter() - started) * 1000)
            status = "error"
            error = f"{type(e).__name__}: {e}"

        inv_id = uuid.uuid4().hex
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO plugin_invocations (
                    plugin_id, capability_id, inputs_json, outputs_json,
                    status, duration_ms, actor, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid, capability_id,
                    json.dumps(inputs or {}, ensure_ascii=False, default=str),
                    json.dumps(outputs or {}, ensure_ascii=False, default=str),
                    status, duration, actor, datetime.now(timezone.utc).isoformat(),
                ),
            )

        # emit bus event
        try:
            from orchestration import get_bus
            get_bus().record(
                topic=f"plugin.{status}",
                entity_type="plugin_invocation",
                entity_id=inv_id,
                payload={"plugin_id": pid, "capability_id": capability_id, "status": status},
                actor=actor,
                source_module="plugins",
            )
        except Exception:  # noqa: BLE001
            pass

        return {
            "invocation_id": inv_id,
            "plugin_id": pid,
            "capability_id": capability_id,
            "status": status,
            "outputs": outputs,
            "duration_ms": duration,
            "error": error,
        }

    def _safe_execute(self, plugin: Plugin, capability: Dict[str, Any],
                       inputs: Dict[str, Any]) -> Dict[str, Any]:
        # Fallback: in a real deployment we'd invoke plugin.install_path via
        # subprocess / gRPC / HTTP. Here we return a structured echo so the
        # pipeline still flows end-to-end.
        return {
            "plugin_id": plugin.id,
            "capability_id": capability["id"],
            "echo_inputs": inputs,
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "license": plugin.manifest.get("license", "unknown"),
        }


_MANAGER: Optional[PluginManager] = None


def get_manager() -> PluginManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = PluginManager()
        _MANAGER.ensure_samples()
    return _MANAGER


def reset_manager_for_test() -> None:
    global _MANAGER
    _MANAGER = None
