"""Data management — dataset versioning, format conversion, storage backend"""

import os
import json
import uuid
import shutil
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel
from core.persistent_base import PersistentManager


class DataType(str, Enum):
    IMAGE_TEXT = "image_text"
    CONVERSATION = "conversation"
    INTERLEAVED = "interleaved"
    VIDEO_TEXT = "video_text"
    DOCUMENT = "document"
    DETECTION = "detection"
    VIDEO_DETECTION = "video_detection"
    UNKNOWN = "unknown"


class ExportFormat(str, Enum):
    LLAVA_JSON = "llava_json"
    INTERNVL_META = "internvl_meta"
    MMC4_JSON = "mmc4_json"
    COCO_JSON = "coco_json"
    YOLO_TXT = "yolo_txt"
    HF_DATASET = "hf_dataset"
    PARQUET = "parquet"
    JSONL = "jsonl"


class DatasetVersion(BaseModel):
    version: str
    created_at: str
    row_count: int
    file_count: int
    total_size_mb: float
    checksum: str = ""
    notes: str = ""


class Dataset(BaseModel):
    id: str
    project_id: str
    name: str
    data_type: DataType
    description: str = ""
    root_path: str
    row_count: int = 0
    versions: List[DatasetVersion] = []
    current_version: str = "v0.0.0"
    created_at: str = ""
    updated_at: str = ""
    tags: List[str] = []


class DataManager(PersistentManager):
    """数据管理核心"""
    _db_table = "datasets"
    _db_fields = ["id","project_id","name","data_type","description","root_path","row_count","versions","current_version","created_at","updated_at","tags"]

    def __init__(self, base_path: str = ""):
        self._base_path = base_path or os.path.join(os.path.dirname(__file__), "..", "data")
        self._datasets: Dict[str, Dataset] = {}
        self._version_lock = threading.Lock()
        os.makedirs(self._base_path, exist_ok=True)
        super().__init__()
        self._load_datasets_from_db()

    def _load_datasets_from_db(self):
        for row in self._load_all():
            if isinstance(row.get("data_type"), str):
                row["data_type"] = DataType(row["data_type"])
            if isinstance(row.get("versions"), list):
                row["versions"] = [DatasetVersion(**v) if isinstance(v, dict) else v for v in row["versions"]]
            ds = Dataset(**row)
            self._datasets[ds.id] = ds

    def create_dataset(self, project_id: str, name: str, data_type: DataType,
                       description: str = "", tags: Optional[List[str]] = None) -> Dataset:
        ds_id = f"ds-{uuid.uuid4().hex[:8]}"
        ds_path = os.path.join(self._base_path, project_id, ds_id)
        os.makedirs(ds_path, exist_ok=True)

        dataset = Dataset(
            id=ds_id,
            project_id=project_id,
            name=name,
            data_type=data_type,
            description=description,
            root_path=ds_path,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            tags=tags or [],
        )
        self._datasets[ds_id] = dataset
        self._save(dataset.id, dataset.model_dump())
        return dataset

    def get_dataset(self, dataset_id: str) -> Optional[Dataset]:
        return self._datasets.get(dataset_id)

    def get_project_datasets(self, project_id: str) -> List[Dataset]:
        return [ds for ds in self._datasets.values() if ds.project_id == project_id]

    def add_data(self, dataset_id: str, data: List[Dict[str, Any]], filename: str = "data.jsonl") -> int:
        """向数据集追加数据"""
        ds = self._datasets.get(dataset_id)
        if not ds:
            return 0

        filepath = os.path.join(ds.root_path, filename)
        with open(filepath, "a") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        ds.row_count += len(data)
        ds.updated_at = datetime.now().isoformat()
        self._save(ds.id, ds.model_dump())
        return len(data)

    def create_version(self, dataset_id: str, notes: str = "") -> Optional[DatasetVersion]:
        """创建数据集快照版本"""
        ds = self._datasets.get(dataset_id)
        if not ds:
            return None

        with self._version_lock:
            # 计算版本号
            parts = [int(x) for x in ds.current_version.lstrip("v").split(".")]
            parts[-1] += 1
            new_version = f"v{'.'.join(str(p) for p in parts)}"
            ds.current_version = new_version

        # 统计文件（不需要锁，读操作）
        total_size = 0
        file_count = 0
        for root, dirs, files in os.walk(ds.root_path):
            for f in files:
                fp = os.path.join(root, f)
                total_size += os.path.getsize(fp)
                file_count += 1

        version = DatasetVersion(
            version=new_version,
            created_at=datetime.now().isoformat(),
            row_count=ds.row_count,
            file_count=file_count,
            total_size_mb=round(total_size / (1024*1024), 2),
            notes=notes,
        )
        ds.versions.append(version)
        self._save(ds.id, ds.model_dump())
        return version

    def export_dataset(self, dataset_id: str, export_format: ExportFormat, output_path: str) -> str:
        """导出为MLLM训练格式"""
        ds = self._datasets.get(dataset_id)
        if not ds:
            return ""

        parent_dir = os.path.dirname(output_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        # 递归读取所有jsonl文件
        records = []
        data_dir = ds.root_path
        for root, dirs, files in os.walk(data_dir):
            for fname in files:
                if fname.endswith(".jsonl"):
                    with open(os.path.join(root, fname)) as f:
                        for line in f:
                            if line.strip():
                                records.append(json.loads(line))

        if export_format == ExportFormat.LLAVA_JSON:
            return self._to_llava(records, output_path)
        elif export_format == ExportFormat.INTERNVL_META:
            return self._to_internvl(records, output_path)
        elif export_format == ExportFormat.MMC4_JSON:
            return self._to_mmc4(records, output_path)
        elif export_format == ExportFormat.COCO_JSON:
            return self._to_coco(records, output_path)
        elif export_format == ExportFormat.JSONL:
            return self._to_jsonl(records, output_path)
        else:
            return self._to_jsonl(records, output_path)

    def _to_llava(self, records: List[Dict], output_path: str) -> str:
        """LLaVA格式: [{id, image, conversations: [{from, value}]}]"""
        output = []
        for r in records:
            convs = r.get("conversations", r.get("messages", []))
            output.append({
                "id": r.get("id", str(uuid.uuid4().hex[:8])),
                "image": r.get("image", r.get("file_path", "")),
                "conversations": convs
            })
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        return output_path

    def _to_internvl(self, records: List[Dict], output_path: str) -> str:
        """InternVL格式: meta_path指向的JSON"""
        # InternVL使用meta_path结构
        with open(output_path, "w") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        return output_path

    def _to_mmc4(self, records: List[Dict], output_path: str) -> str:
        """MMC4图文交错格式"""
        output = []
        for r in records:
            output.append({
                "id": r.get("id", ""),
                "images": r.get("images", []),
                "texts": r.get("texts", []),
                "urls": r.get("urls", []),
            })
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        return output_path

    def _to_coco(self, records: List[Dict], output_path: str) -> str:
        """COCO检测格式"""
        coco = {
            "images": [],
            "annotations": [],
            "categories": []
        }
        seen_cats = {}
        for r in records:
            img_info = r.get("image_info", {})
            anns = r.get("annotations", [])
            coco["images"].append({
                "id": img_info.get("id", 0),
                "file_name": img_info.get("file_name", ""),
                "width": img_info.get("width", 0),
                "height": img_info.get("height", 0),
            })
            for ann in anns:
                cat_name = ann.get("category", "unknown")
                if cat_name not in seen_cats:
                    seen_cats[cat_name] = len(seen_cats) + 1
                coco["annotations"].append({
                    "id": ann.get("id", 0),
                    "image_id": img_info.get("id", 0),
                    "category_id": seen_cats[cat_name],
                    "bbox": ann.get("bbox", [0, 0, 0, 0]),
                    "area": ann.get("area", 0),
                    "iscrowd": ann.get("iscrowd", 0),
                })
        for name, cid in seen_cats.items():
            coco["categories"].append({"id": cid, "name": name, "supercategory": "object"})
        with open(output_path, "w") as f:
            json.dump(coco, f, indent=2)
        return output_path

    def _to_jsonl(self, records: List[Dict], output_path: str) -> str:
        with open(output_path, "w") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return output_path

    def delete_dataset(self, dataset_id: str) -> bool:
        ds = self._datasets.pop(dataset_id, None)
        if ds:
            shutil.rmtree(ds.root_path, ignore_errors=True)
            self._delete(dataset_id)
            return True
        return False

    def get_project_stats(self, project_id: str) -> Dict[str, Any]:
        datasets = self.get_project_datasets(project_id)
        total_rows = sum(ds.row_count for ds in datasets)
        total_size = 0
        for ds in datasets:
            for root, dirs, files in os.walk(ds.root_path):
                total_size += sum(os.path.getsize(os.path.join(root, f)) for f in files)
        return {
            "datasets": len(datasets),
            "total_rows": total_rows,
            "total_size_mb": round(total_size / (1024*1024), 2),
            "data_types": list(set(ds.data_type.value for ds in datasets)),
        }
