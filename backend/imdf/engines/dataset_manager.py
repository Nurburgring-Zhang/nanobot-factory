"""
Dataset Version Management - Version control + 6 format exports.

Based on ZhiYing Data Factory design document chapter 9 + development doc.
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
    modality_id: str = ""  # P19 v5.1: business modality tag (3d_pointcloud/lidar/medical_dicom/panoptic_segmentation)


@dataclass
class DatasetVersion:
    version: str = ""
    created_at: str = ""
    files: List[DatasetFile] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_version: str = ""
    tags: List[str] = field(default_factory=list)


# P19 v5.1: 4 business modality IDs supported by the registry.  These are
# the same IDs returned by ``multimodal.{three_d,lidar,medical,panoptic}.install()``.
SUPPORTED_BUSINESS_MODALITIES: List[str] = [
    "three_d_pointcloud",
    "lidar",
    "medical_dicom",
    "panoptic_segmentation",
]


def _detect_modality_id(path: str) -> str:
    """Best-effort: classify a file path via the business-modality registry.

    Returns an empty string if no business modality matches (caller falls back
    to legacy classification by extension).
    """
    try:
        from multimodal.business_modalities import detect_business_modality as _d
        m = _d(os.path.basename(path))
        if m is not None:
            return m.id
    except Exception:
        pass
    ext = os.path.splitext(path)[1].lower()
    if ext in {".glb", ".gltf", ".obj", ".ply"}:
        return "three_d_pointcloud"
    if ext in {".las", ".laz", ".e57"}:
        return "lidar"
    if ext in {".dcm", ".dicom"}:
        return "medical_dicom"
    return ""


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
                # P19-E2: when version is reloaded from JSON, files comes back
                # as a list of dict (not list of DatasetFile objects). This coerce
                # step ensures that both manager-bound exporters
                # (coco/webdataset/jsonl/parquet/llava/internvl) and the 6 NEW
                # format exporters (GLB/glTF/OBJ/COCO Panoptic/WAV/MP3) can
                # correctly access .path / .modality_id / .hash / .size attributes
                # when iterating ver.files. (Pre-fix: getattr(dict, "path", "")
                # silently returns "" leading to empty output files.)
                ver.files = [
                    DatasetFile(**f) if isinstance(f, dict) else f
                    for f in (ver.files or [])
                ]
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
        # P19-D1 - Prometheus counter.inc() on every dataset version creation.
        try:
            from monitoring.observability import record_request
            record_request("imdf_dataset_manager", status="ok")
        except Exception:  # noqa: BLE001
            pass
        ver = DatasetVersion(
            version=ver_str,
            created_at=datetime.now().isoformat(),
            files=files or [],
            parent_version=parent,
            tags=tags or [],
            metadata={
                "name": name or ver_str,
                "file_count": len(files or []),
                "modality_breakdown": self._modality_breakdown(files or []),
            },
        )
        self._versions[ver_str] = ver
        self._save_index()
        return ver

    @staticmethod
    def _modality_breakdown(files: List[DatasetFile]) -> Dict[str, int]:
        """P19 v5.1: tally the 4 business modalities + legacy bucket."""
        out: Dict[str, int] = {"image": 0, "video": 0, "audio": 0, "text": 0, "document": 0}
        for f in files:
            dt = (f.data_type or "").lower() or "document"
            out[dt] = out.get(dt, 0) + 1
            mid = (f.modality_id or "").lower()
            if mid:
                out[f"biz:{mid}"] = out.get(f"biz:{mid}", 0) + 1
        return {k: v for k, v in out.items() if v > 0}

    def add_file(self, path: str, data_type: str = "document",
                 modality_id: str = "") -> DatasetFile:
        """P19 v5.1: register a single file as a ``DatasetFile`` with auto-detected
        ``modality_id``.  Returns the new ``DatasetFile`` (caller must wrap it
        in a version via ``create_version``).
        """
        try:
            size = os.path.getsize(path) if os.path.exists(path) else 0
        except OSError:
            size = 0
        try:
            with open(path, "rb") as fh:
                h = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            h = ""
        if not modality_id:
            modality_id = _detect_modality_id(path)
        return DatasetFile(
            path=path,
            hash=h,
            size=size,
            data_type=data_type,
            modality_id=modality_id,
        )

    def create_version_from_paths(self, name: str, paths: List[str],
                                   data_type: str = "document",
                                   parent: str = "",
                                   tags: List[str] = None) -> DatasetVersion:
        """P19 v5.1: convenience constructor - auto-build ``DatasetFile`` list
        from raw paths and run the 4-modality detection for each entry.
        """
        files: List[DatasetFile] = []
        for p in paths:
            files.append(self.add_file(p, data_type=data_type))
        return self.create_version(name=name, files=files, parent=parent, tags=tags)

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
            return {"error": "version not found"}
        set1 = {f.path for f in ver1.files}
        set2 = {f.path for f in ver2.files}
        return {
            "added": list(set2 - set1),
            "removed": list(set1 - set2),
            "common": list(set1 & set2),
            "v1_count": len(ver1.files),
            "v2_count": len(ver2.files),
        }

    # ========== Format Exports ==========

    def export_coco(self, version: str, output: str) -> str:
        ver = self.get_version(version)
        if not ver:
            return ""
        coco = {
            "images": [
                {
                    "id": i,
                    "file_name": f.path,
                    "width": 0,
                    "height": 0,
                    "modality_id": f.modality_id,
                    "data_type": f.data_type,
                }
                for i, f in enumerate(ver.files)
            ],
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
                        meta = io.BytesIO(json.dumps({
                            "path": df.path,
                            "hash": df.hash,
                            "data_type": df.data_type,
                            "modality_id": df.modality_id,
                        }).encode())
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
                f.write(json.dumps({
                    "path": df.path,
                    "hash": df.hash,
                    "type": df.data_type,
                    "size": df.size,
                    "modality_id": df.modality_id,
                }, ensure_ascii=False) + "\n")
        return path

    def export_parquet(self, version: str, output: str) -> str:
        ver = self.get_version(version)
        if not ver:
            return ""
        path = output or str(self.data_dir / f"{version}.parquet")
        try:
            import pandas as pd
            records = [
                {
                    "path": f.path,
                    "hash": f.hash,
                    "type": f.data_type,
                    "size": f.size,
                    "modality_id": f.modality_id,
                }
                for f in ver.files
            ]
            df = pd.DataFrame(records)
            df.to_parquet(path)
        except ImportError:
            # fallback to JSONL
            base, _ = os.path.splitext(path)
            path = base + ".jsonl"
            self.export_jsonl(version, path)
        return path

    def export_llava(self, version: str, output: str) -> str:
        """LLaVA instruction-tuning format: [{"id":"","image":"","conversations":[{"from":"human","value":""},{"from":"gpt","value":""}]}]"""
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
        """InternVL multi-modal dialog format"""
        ver = self.get_version(version)
        if not ver:
            return ""
        path = output or str(self.data_dir / f"{version}_internvl.json")
        data = [{"id": i, "image": f.path, "conversations": [{"role": "user", "content": ""}, {"role": "assistant", "content": ""}]}
                for i, f in enumerate(ver.files)]
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    # ========== P19 v5.1: business-modality operations ==========

    def list_business_modalities(self) -> List[str]:
        """Return the 4 supported business modality IDs (constant)."""
        return list(SUPPORTED_BUSINESS_MODALITIES)

    def filter_by_modality(self, version: str, modality_id: str) -> List[DatasetFile]:
        """Return files in ``version`` matching the given business modality."""
        ver = self.get_version(version)
        if not ver:
            return []
        return [f for f in ver.files if (f.modality_id or "") == modality_id]

    def modality_summary(self, version: str) -> Dict[str, int]:
        """Return the per-modality file count for ``version``."""
        ver = self.get_version(version)
        if not ver:
            return {}
        return self._modality_breakdown(ver.files)