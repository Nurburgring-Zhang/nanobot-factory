"""P4-5-W2: Tiny JSON-file persistence for the iteration module.

This deliberately avoids sqlite / a new table — P3-1 already gave us a
shared ``imdf.db`` but the iteration data is fast-evolving and we want
to ship without a migration. The store serialises dataclasses to JSON
under ``backend/services/asset_service/iteration/store/data/``.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _data_root() -> Path:
    """Resolve the JSON-data directory.

    Order:
      1. ``IMDF_DATA_DIR`` / iteration sub-directory if set.
      2. ``backend/services/asset_service/iteration/store/data/`` (created if absent).
    """
    env = os.environ.get("ITERATION_DATA_DIR")
    base = Path(env) if env else Path(__file__).resolve().parent / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


class JsonTable:
    """Append/load JSON lines with a coarse in-process cache.

    Suitable for low-volume iteration metadata (sessions, agents, reports).
    For high-throughput asset binaries the OSS path is used; this table only
    tracks metadata, never pixel/audio data.
    """

    def __init__(self, name: str, root: Optional[Path] = None) -> None:
        self.name = name
        self.root = root or _data_root()
        self.path = self.root / f"{name}.jsonl"
        self._cache: Optional[List[Dict[str, Any]]] = None

    # ── IO helpers ────────────────────────────────────────────────────
    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out: List[Dict[str, Any]] = []
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        # skip corrupt line rather than crash
                        continue
        except OSError:
            return []
        return out

    def _flush(self) -> None:
        assert self._cache is not None
        tmp = self.path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for row in self._cache:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(self.path)

    # ── Public API ────────────────────────────────────────────────────
    def all(self) -> List[Dict[str, Any]]:
        with _LOCK:
            if self._cache is None:
                self._cache = self._load()
            return list(self._cache)

    def find(self, **filters: Any) -> List[Dict[str, Any]]:
        rows = self.all()
        if not filters:
            return rows
        out: List[Dict[str, Any]] = []
        for r in rows:
            if all(r.get(k) == v for k, v in filters.items()):
                out.append(r)
        return out

    def find_one(self, **filters: Any) -> Optional[Dict[str, Any]]:
        for r in self.all():
            if all(r.get(k) == v for k, v in filters.items()):
                return r
        return None

    def insert(self, row: Dict[str, Any]) -> Dict[str, Any]:
        with _LOCK:
            if self._cache is None:
                self._cache = self._load()
            row = dict(row)
            row.setdefault("created_at", _now_iso())
            self._cache.append(row)
            self._flush()
            return row

    def update(self, key: str, value: Any, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with _LOCK:
            if self._cache is None:
                self._cache = self._load()
            for i, row in enumerate(self._cache):
                if row.get(key) == value:
                    row.update(patch)
                    row["updated_at"] = _now_iso()
                    self._cache[i] = row
                    self._flush()
                    return row
            return None

    def delete(self, key: str, value: Any) -> int:
        with _LOCK:
            if self._cache is None:
                self._cache = self._load()
            kept = [r for r in self._cache if r.get(key) != value]
            removed = len(self._cache) - len(kept)
            if removed:
                self._cache = kept
                self._flush()
            return removed

    def clear(self) -> None:
        with _LOCK:
            self._cache = []
            self._flush()


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue