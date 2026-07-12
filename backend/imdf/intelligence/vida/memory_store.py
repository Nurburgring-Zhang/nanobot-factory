"""P19-V53: Vida memory_store — Agent 历史行动持久化.

V5 第 26 章:
  * load(user_id) — 读 user 历史 (今日 actions + 偏好 + 习惯)
  * save(user_id, action, result) — 追加一条记录
  * JSON 文件存储 (轻量; 任务约束: SQLite 不要求, JSON 即可)
  * 异步 IO (asyncio.to_thread), 不阻塞事件循环
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import Action, ActionResult

logger = logging.getLogger(__name__)


class AgentMemoryStore:
    """用户级 memory store — JSON-backed.

    存储结构:
        <root>/<user_id>/memory.json
        {
            "user_id": "...",
            "preferences": {...},
            "history": [
                {"timestamp": "...", "action": {...}, "result": {...}},
                ...
            ]
        }
    """

    DEFAULT_ROOT = ".vida_memory"

    def __init__(self, root_dir: Optional[str] = None) -> None:
        self.root = Path(root_dir or self.DEFAULT_ROOT).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _user_dir(self, user_id: str) -> Path:
        safe = "".join(c for c in user_id if c.isalnum() or c in "-_.") or "anonymous"
        d = self.root / safe
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _memory_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "memory.json"

    async def load(self, user_id: str) -> Dict[str, Any]:
        """加载用户 memory — 不存在返回空结构."""
        path = self._memory_path(user_id)
        if not path.exists():
            return {"user_id": user_id, "preferences": {}, "history": []}

        def _read() -> Dict[str, Any]:
            with self._lock:
                try:
                    raw = path.read_text(encoding="utf-8")
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        return {"user_id": user_id, "preferences": {}, "history": []}
                    data.setdefault("user_id", user_id)
                    data.setdefault("preferences", {})
                    data.setdefault("history", [])
                    return data
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Vida memory load failed for %s: %s", user_id, exc)
                    return {"user_id": user_id, "preferences": {}, "history": []}

        return await asyncio.to_thread(_read)

    async def save(self, user_id: str, action: Action,
                   result: ActionResult, *, timestamp: Optional[datetime] = None) -> None:
        """追加一条 action + result 到 history."""
        ts = (timestamp or datetime.now(timezone.utc)).isoformat()
        path = self._memory_path(user_id)

        def _write() -> None:
            with self._lock:
                data: Dict[str, Any] = {"user_id": user_id, "preferences": {}, "history": []}
                if path.exists():
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        data.setdefault("preferences", {})
                        data.setdefault("history", [])
                    except json.JSONDecodeError:
                        pass
                data["history"].append({
                    "timestamp": ts,
                    "action": action.model_dump(mode="json"),
                    "result": result.model_dump(mode="json"),
                })
                # atomic write — write tmp + replace
                fd, tmp_name = tempfile.mkstemp(prefix=".memory.", dir=str(path.parent))
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                    os.replace(tmp_name, path)
                except Exception:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass
                    raise

        await asyncio.to_thread(_write)

    async def get_today_actions(self, user_id: str) -> List[Dict[str, Any]]:
        """返回今天的所有 history entries (含 action + result).

        使用 UTC 日期匹配 — 与 save() 的 datetime.now(timezone.utc) 一致.
        """
        from datetime import timezone as _tz
        data = await self.load(user_id)
        today = datetime.now(_tz.utc).date().isoformat()
        out: List[Dict[str, Any]] = []
        for entry in data.get("history", []):
            ts = str(entry.get("timestamp", ""))
            if ts.startswith(today):
                out.append(entry)
        return out

    async def set_preferences(self, user_id: str, prefs: Dict[str, Any]) -> None:
        """覆盖式设置用户偏好."""
        path = self._memory_path(user_id)

        def _write() -> None:
            with self._lock:
                data: Dict[str, Any] = {"user_id": user_id, "preferences": {}, "history": []}
                if path.exists():
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        pass
                data["preferences"] = dict(prefs)
                fd, tmp_name = tempfile.mkstemp(prefix=".memory.", dir=str(path.parent))
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                    os.replace(tmp_name, path)
                except Exception:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass
                    raise

        await asyncio.to_thread(_write)


__all__ = ["AgentMemoryStore"]