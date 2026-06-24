"""P3-2-W2 dataset-service in-memory store.

Persists to JSON files under ``data_dir``. Thread-unsafe (single-process FastAPI
worker is fine). On boot, loads any existing ``*.json`` files.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class DatasetStore:
    """Tiny key-value store for datasets + versions + samples.

    Layout on disk::

        data_dir/
          datasets.json          # { "name": { metadata, versions: [] } }
          samples/<name>/<v>.jsonl   # one sample per line

    In-memory cache mirrors the on-disk state.
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.samples_dir = self.data_dir / "samples"
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self._datasets: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────────────
    def _index_path(self) -> Path:
        return self.data_dir / "datasets.json"

    def _load(self):
        if self._index_path().exists():
            try:
                with self._index_path().open("r", encoding="utf-8") as fp:
                    self._datasets = json.load(fp) or {}
            except Exception:
                self._datasets = {}

    def _save(self):
        with self._index_path().open("w", encoding="utf-8") as fp:
            json.dump(self._datasets, fp, ensure_ascii=False, indent=2)

    def _sample_path(self, name: str, version: str) -> Path:
        p = self.samples_dir / name
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{version}.jsonl"

    # ── datasets ─────────────────────────────────────────────────────────
    def create_dataset(
        self,
        name: str,
        description: str = "",
        data_type: str = "image",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if name in self._datasets:
            raise ValueError(f"dataset_already_exists: {name}")
        if not name.replace("_", "").replace("-", "").isalnum():
            raise ValueError("invalid_name: only alphanum / _ / -")
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ds = {
            "name": name,
            "description": description,
            "data_type": data_type,
            "tags": tags or [],
            "created_at": now,
            "updated_at": now,
            "version_count": 0,
            "versions": [],
        }
        self._datasets[name] = ds
        self._save()
        return ds

    def list_datasets(self) -> List[Dict[str, Any]]:
        return list(self._datasets.values())

    def count_datasets(self) -> int:
        return len(self._datasets)

    def get_dataset(self, name: str) -> Optional[Dict[str, Any]]:
        return self._datasets.get(name)

    def delete_dataset(self, name: str) -> bool:
        if name not in self._datasets:
            return False
        del self._datasets[name]
        self._save()
        # Remove samples dir
        sd = self.samples_dir / name
        if sd.exists():
            import shutil
            shutil.rmtree(sd, ignore_errors=True)
        return True

    # ── versions ─────────────────────────────────────────────────────────
    def create_version(
        self,
        dataset_name: str,
        version: str,
        parent: Optional[str] = None,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        ds = self._datasets.get(dataset_name)
        if not ds:
            raise ValueError(f"dataset_not_found: {dataset_name}")
        if any(v["version"] == version for v in ds["versions"]):
            raise ValueError(f"version_already_exists: {version}")
        if parent and not any(v["version"] == parent for v in ds["versions"]):
            raise ValueError(f"parent_version_not_found: {parent}")
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        v = {
            "version": version,
            "parent_version": parent or "",
            "description": description,
            "tags": tags or [],
            "created_at": now,
            "sample_count": 0,
        }
        ds["versions"].append(v)
        ds["version_count"] = len(ds["versions"])
        ds["updated_at"] = now
        self._save()
        # Create empty sample file
        self._sample_path(dataset_name, version).touch()
        return v

    def list_versions(self, dataset_name: str) -> List[Dict[str, Any]]:
        ds = self._datasets.get(dataset_name)
        if not ds:
            return []
        return list(ds["versions"])

    def get_version(self, dataset_name: str, version: str) -> Optional[Dict[str, Any]]:
        ds = self._datasets.get(dataset_name)
        if not ds:
            return None
        for v in ds["versions"]:
            if v["version"] == version:
                return v
        return None

    # ── samples ──────────────────────────────────────────────────────────
    def add_samples(self, dataset_name: str, version: str, samples: List[Dict[str, Any]]) -> int:
        ds = self._datasets.get(dataset_name)
        if not ds:
            raise KeyError(f"dataset_not_found: {dataset_name}")
        v = self.get_version(dataset_name, version)
        if not v:
            raise KeyError(f"version_not_found: {dataset_name}@{version}")
        path = self._sample_path(dataset_name, version)
        added = 0
        with path.open("a", encoding="utf-8") as fp:
            for s in samples:
                if "id" not in s:
                    s = {**s, "id": uuid.uuid4().hex[:16]}
                fp.write(json.dumps(s, ensure_ascii=False) + "\n")
                added += 1
        v["sample_count"] += added
        ds["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save()
        return added

    def list_samples(
        self, dataset_name: str, version: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        path = self._sample_path(dataset_name, version)
        if not path.exists():
            return []
        out: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fp:
            for i, line in enumerate(fp):
                if i < offset:
                    continue
                if len(out) >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out
