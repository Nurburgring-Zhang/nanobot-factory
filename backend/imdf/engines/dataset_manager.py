"""
数据集版本管理 — 版本控制 + 6种格式导出
========================================
基于智影数据工场设计文档第9章 + 开发文档实现。
"""
import json, os, time, hashlib, tarfile, io
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path


@dataclass
class DatasetFile:
    path: str = ""
    hash: str = ""
    size: int = 0
    data_type: str = "image"  # text/image/video/audio


@dataclass
class DatasetVersion:
    version: str = ""
    created_at: str = ""
    files: List[DatasetFile] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_version: str = ""
    tags: List[str] = field(default_factory=list)


class DatasetManager:
    def __init__(self, data_dir: str = "data/datasets"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._versions: Dict[str, DatasetVersion] = {}
        self._load_index()

    def _index_path(self) -> Path:
        return self.data_dir / "index.json"

    def _load_index(self):
        if self._index_path().exists():
            with open(self._index_path()) as f:
                data = json.load(f)
            for v in data.get("versions", []):
                ver = DatasetVersion(**v)
                self._versions[ver.version] = ver

    def _save_index(self):
        def _serialize(obj):
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)
        data = {"versions": [vars(v) for v in self._versions.values()]}
        with open(self._index_path(), "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=_serialize)

    def create_version(self, name: str = "", files: List[DatasetFile] = None,
                       parent: str = "", tags: List[str] = None) -> DatasetVersion:
        ts = int(time.time())
        ver_str = f"v{len(self._versions) + 1}_{ts}"
        ver = DatasetVersion(
            version=ver_str,
            created_at=datetime.now().isoformat(),
            files=files or [],
            parent_version=parent,
            tags=tags or [],
            metadata={"name": name or ver_str, "file_count": len(files or [])},
        )
        self._versions[ver_str] = ver
        self._save_index()
        return ver

    def get_version(self, version: str) -> Optional[DatasetVersion]:
        return self._versions.get(version)

    def list_versions(self, tags: List[str] = None) -> List[DatasetVersion]:
        versions = list(self._versions.values())
        if tags:
            versions = [v for v in versions if any(t in v.tags for t in tags)]
        return sorted(versions, key=lambda v: v.created_at, reverse=True)

    def rollback(self, version: str) -> Optional[DatasetVersion]:
        target = self.get_version(version)
        if not target:
            return None
        new_ver = self.create_version(
            name=f"rollback_from_{version}",
            files=target.files.copy(),
            parent=version,
            tags=["rollback"],
        )
        return new_ver

    def diff(self, v1: str, v2: str) -> Dict:
        ver1 = self.get_version(v1)
        ver2 = self.get_version(v2)
        if not ver1 or not ver2:
            return {"error": "版本不存在"}
        set1 = {f.path for f in ver1.files}
        set2 = {f.path for f in ver2.files}
        return {
            "added": list(set2 - set1),
            "removed": list(set1 - set2),
            "common": list(set1 & set2),
            "v1_count": len(ver1.files),
            "v2_count": len(ver2.files),
        }

    # ========== 格式导出 ==========

    def export_coco(self, version: str, output: str) -> str:
        ver = self.get_version(version)
        if not ver:
            return ""
        coco = {
            "images": [{"id": i, "file_name": f.path, "width": 0, "height": 0}
                       for i, f in enumerate(ver.files)],
            "annotations": [],
            "categories": [],
        }
        path = output or str(self.data_dir / f"{version}_coco.json")
        with open(path, "w") as f:
            json.dump(coco, f, ensure_ascii=False)
        return path

    def export_webdataset(self, version: str, output_dir: str) -> str:
        ver = self.get_version(version)
        if not ver:
            return ""
        out = Path(output_dir or self.data_dir / f"{version}_wds")
        out.mkdir(parents=True, exist_ok=True)
        shard_size = 1000
        for idx in range(0, len(ver.files), shard_size):
            shard_path = out / f"shard-{idx:06d}.tar"
            with tarfile.open(shard_path, "w") as tar:
                for i, df in enumerate(ver.files[idx:idx + shard_size]):
                    fpath = Path(df.path)
                    if fpath.exists():
                        tar.add(str(fpath), arcname=f"{idx + i:08d}{fpath.suffix}")
                        meta = io.BytesIO(json.dumps({"path": df.path, "hash": df.hash}).encode())
                        info = tarfile.TarInfo(name=f"{idx + i:08d}.json")
                        info.size = len(meta.getvalue())
                        tar.addfile(info, meta)
        return str(out)

    def export_jsonl(self, version: str, output: str) -> str:
        ver = self.get_version(version)
        if not ver:
            return ""
        path = output or str(self.data_dir / f"{version}.jsonl")
        with open(path, "w") as f:
            for df in ver.files:
                f.write(json.dumps({"path": df.path, "hash": df.hash, "type": df.data_type}, ensure_ascii=False) + "\n")
        return path

    def export_parquet(self, version: str, output: str) -> str:
        ver = self.get_version(version)
        if not ver:
            return ""
        path = output or str(self.data_dir / f"{version}.parquet")
        try:
            import pandas as pd
            records = [{"path": f.path, "hash": f.hash, "type": f.data_type, "size": f.size} for f in ver.files]
            df = pd.DataFrame(records)
            df.to_parquet(path)
        except ImportError:
            # fallback to JSONL
            base, _ = os.path.splitext(path)
            path = base + ".jsonl"
            self.export_jsonl(version, path)
        return path

    def export_llava(self, version: str, output: str) -> str:
        """LLaVA指令微调格式: [{\"id\":\"\",\"image\":\"\",\"conversations\":[{\"from\":\"human\",\"value\":\"\"},{\"from\":\"gpt\",\"value\":\"\"}]}]"""
        ver = self.get_version(version)
        if not ver:
            return ""
        path = output or str(self.data_dir / f"{version}_llava.json")
        data = [{"id": i, "image": f.path, "conversations": [{"from": "human", "value": ""}, {"from": "gpt", "value": ""}]}
                for i, f in enumerate(ver.files)]
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def export_internvl(self, version: str, output: str) -> str:
        """InternVL多模态对话格式"""
        ver = self.get_version(version)
        if not ver:
            return ""
        path = output or str(self.data_dir / f"{version}_internvl.json")
        data = [{"id": i, "image": f.path, "conversations": [{"role": "user", "content": ""}, {"role": "assistant", "content": ""}]}
                for i, f in enumerate(ver.files)]
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
