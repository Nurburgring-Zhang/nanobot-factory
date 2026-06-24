"""
NanoBot Factory - 数据集管理系统
Data Dataset Manager

支持 HuggingFace Datasets 格式 (通过本地JSON/Parquet实现)
支持 WebDataset (TAR分片格式)
支持数据集切分 (train/val/test)
数据集元数据管理
数据集统计

无外部依赖，只用 Python 标准库 + PIL + json + tarfile
"""

import os, sys, io, json, logging, uuid, hashlib, tarfile, struct, math, random
import gzip
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union, Iterator
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from collections import Counter, defaultdict
from PIL import Image

logger = logging.getLogger(__name__)

# ============================================================================
# 数据集格式定义
# ============================================================================

class DatasetFormat(str, Enum):
    """支持的数据集格式"""
    HF_JSON = "hf_json"         # HuggingFace JSON 格式 (每行一个JSON)
    HF_PARQUET = "hf_parquet"   # HuggingFace Parquet 格式 (本地模拟)
    WEBDATASET = "webdataset"   # WebDataset TAR分片格式
    RAW_IMAGE = "raw_image"     # 原始图像目录


@dataclass
class DatasetEntry:
    """单条数据集条目"""
    entry_id: str
    image_path: str = ""
    caption: str = ""
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    split: str = "train"  # train / val / test
    file_size: int = 0
    width: int = 0
    height: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DatasetSplit:
    """数据集切分信息"""
    name: str
    num_entries: int = 0
    file_paths: List[str] = field(default_factory=list)


@dataclass
class DatasetMetadata:
    """数据集元数据"""
    name: str
    description: str = ""
    version: str = "1.0"
    format: str = "hf_json"
    total_entries: int = 0
    splits: List[DatasetSplit] = field(default_factory=list)
    num_images: int = 0
    num_captions: int = 0
    image_formats: Dict[str, int] = field(default_factory=dict)
    avg_image_size: Tuple[float, float] = (0.0, 0.0)
    caption_length_stats: Dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 数据集统计
# ============================================================================

class DatasetStats:
    """数据集统计计算器"""

    @staticmethod
    def compute_stats(entries: List[DatasetEntry]) -> Dict[str, Any]:
        """计算数据集统计信息"""
        total = len(entries)
        if total == 0:
            return {"total": 0}

        # 图像统计
        widths = [e.width for e in entries if e.width > 0]
        heights = [e.height for e in entries if e.height > 0]
        file_sizes = [e.file_size for e in entries if e.file_size > 0]

        # 格式分布
        formats = defaultdict(int)
        for e in entries:
            ext = os.path.splitext(e.image_path)[1].lower() if e.image_path else ""
            if ext:
                formats[ext] += 1

        # 切分分布
        split_dist = defaultdict(int)
        for e in entries:
            split_dist[e.split] += 1

        # 描述文本统计
        captions = [e.caption for e in entries if e.caption]
        caption_lens = [len(c.split()) for c in captions]

        stats = {
            "total_entries": total,
            "num_images": sum(1 for e in entries if e.image_path and e.width > 0),
            "num_captions": len(captions),
            "splits": dict(split_dist),
            "image_formats": dict(formats),
            "width": {
                "min": min(widths) if widths else 0,
                "max": max(widths) if widths else 0,
                "avg": round(sum(widths) / len(widths), 1) if widths else 0.0,
            },
            "height": {
                "min": min(heights) if heights else 0,
                "max": max(heights) if heights else 0,
                "avg": round(sum(heights) / len(heights), 1) if heights else 0.0,
            },
            "file_size": {
                "min": min(file_sizes) if file_sizes else 0,
                "max": max(file_sizes) if file_sizes else 0,
                "avg": round(sum(file_sizes) / len(file_sizes), 1) if file_sizes else 0.0,
                "total_gb": round(sum(file_sizes) / (1024**3), 4) if file_sizes else 0.0,
            },
            "caption_length": {
                "min": min(caption_lens) if caption_lens else 0,
                "max": max(caption_lens) if caption_lens else 0,
                "avg": round(sum(caption_lens) / len(caption_lens), 1) if caption_lens else 0.0,
            },
            "aspect_ratios": {},
        }

        # 宽高比分布
        if widths and heights:
            ratios = [round(w / max(h, 1), 2) for w, h in zip(widths, heights)]
            ratio_counter = Counter(ratios)
            stats["aspect_ratios"] = {
                str(k): v for k, v in sorted(ratio_counter.items(), key=lambda x: -x[1])[:10]
            }

        return stats

    @staticmethod
    def print_summary(stats: Dict[str, Any]) -> str:
        """打印统计摘要"""
        if not stats or stats.get("total_entries", 0) == 0:
            return "Empty dataset"

        lines = [
            f"Dataset Summary:",
            f"  Total entries:     {stats['total_entries']}",
            f"  Images:            {stats.get('num_images', 0)}",
            f"  Captions:          {stats.get('num_captions', 0)}",
            f"  Splits:            {stats.get('splits', {})}",
            f"  Image sizes:       {stats['width']['avg']:.0f}x{stats['height']['avg']:.0f} (avg)",
            f"  File size:         {stats['file_size']['total_gb']:.4f} GB",
            f"  Caption length:    {stats['caption_length']['avg']:.1f} words (avg)",
            f"  Image formats:     {stats.get('image_formats', {})}",
        ]
        return "\n".join(lines)


# ============================================================================
# 数据集管理器
# ============================================================================

class DatasetManager:
    """
    数据集管理器 - 支持多种格式的读写、切分、统计

    支持格式:
    - hf_json: HuggingFace JSON (每行一个JSON对象)
    - hf_parquet: 本地Parquet模拟 (使用JSON + 分片)
    - webdataset: WebDataset TAR分片格式
    - raw_image: 原始图像目录
    """

    def __init__(self, base_dir: str = "./data/datasets"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # HuggingFace JSON 格式
    # ========================================================================

    def create_hf_json(self, name: str, entries: List[DatasetEntry],
                       split: str = "train", shard_size: int = 0) -> str:
        """
        创建 HuggingFace JSON 格式数据集
        每行一个JSON对象，可选的切分文件

        Args:
            name: 数据集名称
            entries: 数据条目
            split: 切分名称 (train/val/test)
            shard_size: 每个分片的条目数 (0=不分片)

        Returns:
            数据集目录路径
        """
        ds_dir = self.base_dir / name
        split_dir = ds_dir / split
        split_dir.mkdir(parents=True, exist_ok=True)

        self._write_hf_json(split_dir, entries, name, split, shard_size)

        # 写元数据
        meta = DatasetMetadata(
            name=name,
            format="hf_json",
            total_entries=len(entries),
            splits=[DatasetSplit(name=split, num_entries=len(entries),
                                 file_paths=[str(split_dir / f"{split}.json")])],
            updated_at=datetime.now().isoformat(),
        )
        self._write_metadata(ds_dir, meta)

        return str(ds_dir)

    def _write_hf_json(self, output_dir: Path, entries: List[DatasetEntry],
                       name: str, split: str, shard_size: int):
        """写入HF JSON文件"""
        if shard_size > 0:
            # 分片写入
            for i in range(0, len(entries), shard_size):
                shard_id = i // shard_size
                shard_path = output_dir / f"{split}-{shard_id:05d}-of-{max(1, len(entries)//shard_size):05d}.json"
                with open(shard_path, "w") as f:
                    for entry in entries[i:i + shard_size]:
                        f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        else:
            # 单文件
            file_path = output_dir / f"{split}.json"
            with open(file_path, "w") as f:
                for entry in entries:
                    f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def load_hf_json(self, path: str) -> List[DatasetEntry]:
        """
        加载 HuggingFace JSON 格式数据集
        支持目录（自动查找所有.json文件）或单文件
        """
        entries = []
        p = Path(path)

        if p.is_dir():
            json_files = sorted(p.rglob("*.json"))
        elif p.is_file():
            json_files = [p]
        else:
            raise FileNotFoundError(f"Path not found: {path}")

        for jf in json_files:
            # 跳过元数据文件
            if jf.name == "dataset_metadata.json":
                continue
            with open(jf, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entry = DatasetEntry(**{k: v for k, v in data.items()
                                                 if k in DatasetEntry.__dataclass_fields__})
                        # 填充额外字段到metadata
                        for k, v in data.items():
                            if k not in DatasetEntry.__dataclass_fields__:
                                entry.metadata[k] = v
                        entries.append(entry)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Skipping malformed line in {jf}: {e}")

        return entries

    # ========================================================================
    # HF Parquet 模拟 (JSON + 分片 + 列式存储模拟)
    # ========================================================================

    def create_hf_parquet(self, name: str, entries: List[DatasetEntry],
                          split: str = "train") -> str:
        """
        创建 HuggingFace Parquet 模拟格式

        使用多个分片JSON文件 + 列式元数据文件模拟Parquet结构
        """
        ds_dir = self.base_dir / name
        split_dir = ds_dir / split
        split_dir.mkdir(parents=True, exist_ok=True)

        # 分片写入 (每片5000条)
        shard_size = 5000
        for i in range(0, len(entries), shard_size):
            shard_id = i // shard_size
            shard = entries[i:i + shard_size]

            # JSON数据文件
            data_path = split_dir / f"data-{shard_id:05d}-of-{max(1, len(entries)//shard_size):05d}.json"
            with open(data_path, "w") as f:
                for entry in shard:
                    f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

        # 列式元数据（列名+类型）
        if entries:
            sample = asdict(entries[0])
            columns = {k: type(v).__name__ for k, v in sample.items()}
            meta_path = split_dir / "_metadata.json"
            with open(meta_path, "w") as f:
                json.dump({
                    "format": "hf_parquet_sim",
                    "num_entries": len(entries),
                    "num_shards": max(1, len(entries) // shard_size) + (1 if len(entries) % shard_size else 0),
                    "columns": columns,
                    "created_at": datetime.now().isoformat(),
                }, f, indent=2)

        # 写元数据
        meta = DatasetMetadata(
            name=name,
            format="hf_parquet",
            total_entries=len(entries),
            splits=[DatasetSplit(name=split, num_entries=len(entries))],
            updated_at=datetime.now().isoformat(),
        )
        self._write_metadata(ds_dir, meta)

        return str(ds_dir)

    # ========================================================================
    # WebDataset (TAR分片格式)
    # ========================================================================

    def create_webdataset(self, name: str, entries: List[DatasetEntry],
                          shard_size: int = 1000,
                          include_images: bool = True,
                          image_base_dir: str = "") -> str:
        """
        创建 WebDataset TAR分片格式

        WebDataset 格式约定:
        - shard-000000.tar, shard-000001.tar, ...
        - 每个TAR内: {key}.jpg, {key}.json, {key}.txt
        """
        ds_dir = self.base_dir / name
        ds_dir.mkdir(parents=True, exist_ok=True)

        for i in range(0, len(entries), shard_size):
            shard_id = i // shard_size
            shard_path = ds_dir / f"shard-{shard_id:06d}.tar"

            with tarfile.open(shard_path, "w") as tar:
                for entry in entries[i:i + shard_size]:
                    key = entry.entry_id or str(uuid.uuid4())

                    # 写入JSON元数据
                    meta_bytes = json.dumps(asdict(entry), ensure_ascii=False).encode("utf-8")
                    meta_info = tarfile.TarInfo(name=f"{key}.json")
                    meta_info.size = len(meta_bytes)
                    tar.addfile(meta_info, io.BytesIO(meta_bytes))

                    # 写入文本（如果有caption）
                    if entry.caption:
                        text_bytes = entry.caption.encode("utf-8")
                        text_info = tarfile.TarInfo(name=f"{key}.txt")
                        text_info.size = len(text_bytes)
                        tar.addfile(text_info, io.BytesIO(text_bytes))

                    # 写入图像
                    if include_images and entry.image_path:
                        img_path = entry.image_path
                        if image_base_dir:
                            img_path = os.path.join(image_base_dir, entry.image_path)
                        if os.path.exists(img_path):
                            try:
                                img = Image.open(img_path)
                                ext = os.path.splitext(img_path)[1].lower() or ".jpg"
                                img_bytes = io.BytesIO()
                                if ext in (".jpg", ".jpeg"):
                                    img.save(img_bytes, format="JPEG", quality=95)
                                elif ext == ".png":
                                    img.save(img_bytes, format="PNG")
                                else:
                                    img.save(img_bytes, format="JPEG", quality=95)
                                    ext = ".jpg"

                                img_data = img_bytes.getvalue()
                                img_info = tarfile.TarInfo(name=f"{key}{ext}")
                                img_info.size = len(img_data)
                                tar.addfile(img_info, io.BytesIO(img_data))
                            except Exception as e:
                                logger.warning(f"Failed to add image {img_path}: {e}")

        # 写入分片索引
        num_shards = max(1, (len(entries) + shard_size - 1) // shard_size)
        manifest = {
            "format": "webdataset",
            "name": name,
            "num_entries": len(entries),
            "num_shards": num_shards,
            "shard_size": shard_size,
            "shards": [f"shard-{i:06d}.tar" for i in range(num_shards)],
            "created_at": datetime.now().isoformat(),
        }
        with open(ds_dir / "_manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)

        # 写元数据
        meta = DatasetMetadata(
            name=name,
            format="webdataset",
            total_entries=len(entries),
            splits=[DatasetSplit(name="all", num_entries=len(entries))],
            updated_at=datetime.now().isoformat(),
        )
        self._write_metadata(ds_dir, meta)

        return str(ds_dir)

    def load_webdataset(self, path: str, max_shards: int = 0) -> List[DatasetEntry]:
        """
        加载 WebDataset TAR格式

        Args:
            path: TAR文件路径或目录
            max_shards: 最大加载分片数 (0=全部)
        """
        entries = []
        p = Path(path)

        if p.is_dir():
            tar_files = sorted(p.glob("shard-*.tar"))
        elif p.is_file() and p.suffix == ".tar":
            tar_files = [p]
        else:
            raise FileNotFoundError(f"WebDataset path not found: {path}")

        if max_shards > 0:
            tar_files = tar_files[:max_shards]

        for tar_path in tar_files:
            try:
                with tarfile.open(tar_path, "r") as tar:
                    # 按key分组TAR成员
                    members_by_key: Dict[str, Dict[str, tarfile.TarInfo]] = {}
                    for member in tar.getmembers():
                        if member.isfile():
                            key, ext = os.path.splitext(member.name)
                            if key not in members_by_key:
                                members_by_key[key] = {}
                            members_by_key[key][ext] = member

                    for key, ext_map in members_by_key.items():
                        entry = DatasetEntry(entry_id=key)

                        # 读取JSON元数据
                        if ".json" in ext_map:
                            try:
                                m = ext_map[".json"]
                                f = tar.extractfile(m)
                                if f:
                                    data = json.loads(f.read().decode("utf-8"))
                                    entry = DatasetEntry(**{k: v for k, v in data.items()
                                                             if k in DatasetEntry.__dataclass_fields__})
                            except Exception as e:
                                logger.warning(f"Failed to read JSON for {key}: {e}")

                        # 读取文本
                        if ".txt" in ext_map:
                            try:
                                m = ext_map[".txt"]
                                f = tar.extractfile(m)
                                if f:
                                    entry.caption = f.read().decode("utf-8").strip()
                            except Exception:
                                pass

                        # 读取图像路径（从TAR中提取到临时位置）
                        for ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
                            if ext in ext_map:
                                m = ext_map[ext]
                                # 记录为临时路径以便后续处理
                                try:
                                    f = tar.extractfile(m)
                                    if f:
                                        img_data = f.read()
                                        # 检查图像有效性
                                        img = Image.open(io.BytesIO(img_data))
                                        entry.width, entry.height = img.size
                                        entry.file_size = len(img_data)
                                except Exception:
                                    pass
                                break

                        entries.append(entry)
            except Exception as e:
                logger.error(f"Failed to read tar {tar_path}: {e}")

        return entries

    # ========================================================================
    # 原始图像目录
    # ========================================================================

    def create_from_image_dir(self, name: str, image_dir: str,
                               recursive: bool = True,
                               extensions: Tuple[str] = (".jpg", ".jpeg", ".png", ".webp", ".bmp"),
                               split: str = "train") -> List[DatasetEntry]:
        """
        从图像目录创建数据集条目
        """
        entries = []
        img_dir = Path(image_dir)

        if not img_dir.exists():
            raise FileNotFoundError(f"Image directory not found: {image_dir}")

        if recursive:
            files = sorted(img_dir.rglob("*"))
        else:
            files = sorted(img_dir.glob("*"))

        for fpath in files:
            if fpath.suffix.lower() in extensions:
                try:
                    img = Image.open(fpath)
                    w, h = img.size
                    entry = DatasetEntry(
                        entry_id=str(uuid.uuid4()),
                        image_path=str(fpath),
                        width=w,
                        height=h,
                        file_size=fpath.stat().st_size,
                        split=split,
                    )
                    # 文件名去后缀作为默认caption（如果有分隔符）
                    stem = fpath.stem
                    if "_" in stem or "-" in stem:
                        entry.caption = stem.replace("_", " ").replace("-", " ")
                    entries.append(entry)
                except Exception as e:
                    logger.warning(f"Cannot open {fpath}: {e}")

        # 保存元数据
        meta = DatasetMetadata(
            name=name,
            format="raw_image",
            total_entries=len(entries),
            splits=[DatasetSplit(name=split, num_entries=len(entries))],
            source=str(image_dir),
            updated_at=datetime.now().isoformat(),
        )
        self._write_metadata(self.base_dir / name, meta)

        logger.info(f"Created {len(entries)} entries from {image_dir}")
        return entries

    # ========================================================================
    # 数据集切分
    # ========================================================================

    def split_dataset(self, entries: List[DatasetEntry],
                      train_ratio: float = 0.8,
                      val_ratio: float = 0.1,
                      test_ratio: float = 0.1,
                      shuffle: bool = True,
                      seed: int = 42) -> Dict[str, List[DatasetEntry]]:
        """
        将数据集切分为 train/val/test

        Args:
            entries: 数据条目列表
            train_ratio: 训练集比例
            val_ratio: 验证集比例
            test_ratio: 测试集比例
            shuffle: 是否打乱
            seed: 随机种子

        Returns:
            {"train": [...], "val": [...], "test": [...]}
        """
        assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-6, \
            f"Ratios must sum to 1.0, got {train_ratio}+{val_ratio}+{test_ratio}"

        total = len(entries)
        indices = list(range(total))

        if shuffle:
            import random
            rng = random.Random(seed)
            rng.shuffle(indices)

        train_end = int(total * train_ratio)
        val_end = train_end + int(total * val_ratio)

        train_indices = indices[:train_end]
        val_indices = indices[train_end:val_end]
        test_indices = indices[val_end:]

        result = {
            "train": [entries[i] for i in train_indices],
            "val": [entries[i] for i in val_indices],
            "test": [entries[i] for i in test_indices],
        }

        # 更新split字段
        for e in result["train"]:
            e.split = "train"
        for e in result["val"]:
            e.split = "val"
        for e in result["test"]:
            e.split = "test"

        logger.info(
            f"Dataset split: train={len(result['train'])}, "
            f"val={len(result['val'])}, test={len(result['test'])}"
        )
        return result

    # ========================================================================
    # 元数据管理
    # ========================================================================

    def _write_metadata(self, ds_dir: Path, meta: DatasetMetadata):
        """写入数据集元数据"""
        ds_dir.mkdir(parents=True, exist_ok=True)
        meta_path = ds_dir / "dataset_metadata.json"
        with open(meta_path, "w") as f:
            json.dump(asdict(meta), f, indent=2, ensure_ascii=False)

    def load_metadata(self, name_or_path: str) -> Optional[DatasetMetadata]:
        """加载数据集元数据"""
        p = Path(name_or_path)
        if not p.is_absolute():
            p = self.base_dir / name_or_path

        meta_path = p / "dataset_metadata.json"
        if not meta_path.exists():
            return None

        with open(meta_path, "r") as f:
            data = json.load(f)

        # 重建splits
        if "splits" in data:
            data["splits"] = [DatasetSplit(**s) for s in data["splits"]]

        return DatasetMetadata(**data)

    def list_datasets(self) -> List[str]:
        """列出所有数据集"""
        if not self.base_dir.exists():
            return []
        datasets = []
        for d in sorted(self.base_dir.iterdir()):
            if d.is_dir() and (d / "dataset_metadata.json").exists():
                datasets.append(d.name)
        return datasets

    # ========================================================================
    # 工具方法
    # ========================================================================

    def detect_format(self, path: str) -> Optional[str]:
        """检测数据集格式"""
        p = Path(path)
        if not p.exists():
            return None

        if p.is_dir():
            # 检查是否有TAR文件
            if list(p.glob("shard-*.tar")):
                return "webdataset"
            # 检查是否有JSON数据文件
            if list(p.glob("*.json")) or list(p.rglob("*.json")):
                return "hf_json"
            # 检查是否有图像文件
            if list(p.glob("*.[jJ][pP][gG]")) or list(p.glob("*.[pP][nN][gG]")):
                return "raw_image"
        elif p.is_file():
            if p.suffix == ".tar":
                return "webdataset"
            if p.suffix == ".json":
                return "hf_json"

        return None

    @staticmethod
    def create_from_memory(entries: List[Dict[str, Any]]) -> List[DatasetEntry]:
        """从内存字典列表创建DatasetEntry列表"""
        result = []
        for data in entries:
            if "entry_id" not in data:
                data["entry_id"] = str(uuid.uuid4())
            result.append(DatasetEntry(**{k: v for k, v in data.items()
                                           if k in DatasetEntry.__dataclass_fields__}))
        return result


# ============================================================================
# ResolutionBucket — SD3/FLUX标准多分辨率桶系统
# ============================================================================

# SD3/FLUX标准桶配置（宽高比 + 目标总像素 ~1M）
BUCKET_CONFIGS_FLUX = [
    # (name, width, height, aspect_ratio)
    ("1024x1024", 1024, 1024, 1.0),
    ("1152x896",  1152, 896,  1.2857),
    ("896x1152",  896,  1152, 0.7778),
    ("1216x832",  1216, 832,  1.4615),
    ("832x1216",  832,  1216, 0.6842),
    ("1344x768",  1344, 768,  1.75),
    ("768x1344",  768,  1344, 0.5714),
    ("1536x640",  1536, 640,  2.4),
    ("640x1536",  640,  1536, 0.4167),
]

# SDXL标准桶配置（总像素~1M）
BUCKET_CONFIGS_SDXL = [
    ("1024x1024", 1024, 1024, 1.0),
    ("1152x896",  1152, 896,  1.2857),
    ("896x1152",  896,  1152, 0.7778),
    ("1216x832",  1216, 832,  1.4615),
    ("832x1216",  832,  1216, 0.6842),
    ("1344x768",  1344, 768,  1.75),
    ("768x1344",  768,  1344, 0.5714),
    ("1536x640",  1536, 640,  2.4),
    ("640x1536",  640,  1536, 0.4167),
]

# SD1.5/2.0标准桶配置（总像素~512K）
BUCKET_CONFIGS_SD15 = [
    ("512x512",   512,  512,  1.0),
    ("576x448",   576,  448,  1.2857),
    ("448x576",   448,  576,  0.7778),
    ("640x384",   640,  384,  1.6667),
    ("384x640",   384,  640,  0.6),
    ("704x352",   704,  352,  2.0),
    ("352x704",   352,  704,  0.5),
    ("768x320",   768,  320,  2.4),
    ("320x768",   320,  768,  0.4167),
]


@dataclass
class BucketAssignment:
    """单张图像的桶分配结果"""
    bucket_id: str = ""
    target_width: int = 0
    target_height: int = 0
    original_width: int = 0
    original_height: int = 0
    aspect_ratio: float = 0.0
    bucket_aspect_ratio: float = 0.0
    scale_factor: float = 0.0  # 缩放因子
    pad_width: int = 0         # 需要填充的像素
    pad_height: int = 0


class ResolutionBucket:
    """
    分辨率桶系统 — 对齐SD3/FLUX/SDXL/SD1.5标准

    支持:
    - 多桶配置: FLUX (1M), SDXL (1M), SD15 (512K)
    - 按宽高比自动分配图像到最近桶
    - 返回bucket_id + 目标分辨率
    - 自动估算缩放和填充量
    """

    def __init__(self, bucket_type: str = "flux"):
        """
        Args:
            bucket_type: "flux" | "sdxl" | "sd15"
        """
        configs = {
            "flux": BUCKET_CONFIGS_FLUX,
            "sdxl": BUCKET_CONFIGS_SDXL,
            "sd15": BUCKET_CONFIGS_SD15,
        }
        if bucket_type not in configs:
            logger.warning(f"Unknown bucket type '{bucket_type}', defaulting to flux")
            bucket_type = "flux"

        self.bucket_type = bucket_type
        self.buckets = []
        for name, w, h, ar in configs[bucket_type]:
            self.buckets.append({
                "id": name,
                "width": w,
                "height": h,
                "aspect_ratio": round(ar, 4),
                "total_pixels": w * h,
            })

        # 桶的宽高比列表，用于快速查找
        self._bucket_ratios = sorted(
            [(b["aspect_ratio"], b["id"], b["width"], b["height"]) for b in self.buckets],
            key=lambda x: x[0]
        )

    def assign(self, width: int, height: int) -> BucketAssignment:
        """
        将图像分配到最近的桶

        策略: 找到宽高比最接近的桶，返回bucket_id和目标分辨率。

        Args:
            width: 图像宽度
            height: 图像高度

        Returns:
            BucketAssignment
        """
        aspect = round(width / max(height, 1), 4)

        # 找到最接近的桶
        closest = min(self._bucket_ratios, key=lambda b: abs(aspect - b[0]))
        bucket_id, bw, bh = closest[1], closest[2], closest[3]
        bucket_ar = closest[0]

        # 缩放因子
        # 保持宽高比缩放到目标总像素数
        target_pixels = bw * bh
        current_pixels = width * height
        if current_pixels > 0:
            scale_factor = math.sqrt(target_pixels / current_pixels)
        else:
            scale_factor = 1.0

        # 估算填充量（如果缩放后尺寸与桶不匹配）
        scaled_w = int(width * scale_factor)
        scaled_h = int(height * scale_factor)
        pad_w = max(0, bw - scaled_w)
        pad_h = max(0, bh - scaled_h)

        return BucketAssignment(
            bucket_id=bucket_id,
            target_width=bw,
            target_height=bh,
            original_width=width,
            original_height=height,
            aspect_ratio=aspect,
            bucket_aspect_ratio=bucket_ar,
            scale_factor=round(scale_factor, 4),
            pad_width=pad_w,
            pad_height=pad_h,
        )

    def batch_assign(self, images: List[Tuple[int, int]]) -> List[BucketAssignment]:
        """批量分配"""
        return [self.assign(w, h) for w, h in images]

    def bucket_stats(self, assignments: List[BucketAssignment]) -> Dict[str, Any]:
        """桶分配统计"""
        from collections import Counter
        counts = Counter(a.bucket_id for a in assignments)
        return {
            "total": len(assignments),
            "num_buckets_used": len(counts),
            "bucket_distribution": dict(counts.most_common()),
            "bucket_type": self.bucket_type,
        }

    def list_buckets(self) -> List[Dict[str, Any]]:
        """列出所有桶"""
        return self.buckets


# ============================================================================
# Caption Dropout — 随机丢弃部分caption用于CFG训练
# ============================================================================

@dataclass
class CaptionDropoutResult:
    """Caption Dropout结果"""
    original_caption: str = ""
    training_caption: str = ""
    dropout_type: str = "none"  # "none" | "full" | "partial" | "token"
    dropout_rate: float = 0.0
    strategy: str = ""  # description of what was done


class CaptionDropout:
    """
    随机丢弃部分caption用于CFG训练

    策略:
    - full_drop: 丢弃整个caption (rate=0.1)
    - partial_drop: 丢弃部分描述 (rate=0.1)
    - token_drop: 随机丢弃某些token (rate=0.05)

    对齐SD3/FLUX训练中的CFG dropout机制。
    """

    def __init__(self, full_drop_rate: float = 0.1,
                 partial_drop_rate: float = 0.1,
                 token_drop_rate: float = 0.05,
                 seed: Optional[int] = None):
        """
        Args:
            full_drop_rate: 完全丢弃caption的概率
            partial_drop_rate: 部分丢弃caption的概率
            token_drop_rate: 随机丢弃token的概率
            seed: 随机种子 (None=不固定)
        """
        self.full_drop_rate = full_drop_rate
        self.partial_drop_rate = partial_drop_rate
        self.token_drop_rate = token_drop_rate
        self.rng = random.Random(seed) if seed is not None else random

    def apply(self, caption: str) -> CaptionDropoutResult:
        """
        对caption应用dropout

        Args:
            caption: 原始caption文本

        Returns:
            CaptionDropoutResult
        """
        if not caption:
            return CaptionDropoutResult(
                original_caption="",
                training_caption="",
                dropout_type="none",
                dropout_rate=0.0,
                strategy="empty_caption",
            )

        rand = self.rng.random()

        # 1. Full dropout: 完全丢弃
        if rand < self.full_drop_rate:
            return CaptionDropoutResult(
                original_caption=caption,
                training_caption="",
                dropout_type="full",
                dropout_rate=self.full_drop_rate,
                strategy="full_dropout",
            )

        # 2. Partial dropout: 丢弃部分描述
        if rand < self.full_drop_rate + self.partial_drop_rate:
            words = caption.split()
            if len(words) <= 3:
                # 太短不做partial，做full
                return CaptionDropoutResult(
                    original_caption=caption,
                    training_caption="",
                    dropout_type="full",
                    dropout_rate=self.full_drop_rate,
                    strategy="full_dropout_short_caption",
                )
            # 随机丢弃25%-75%的词
            drop_ratio = self.rng.uniform(0.25, 0.75)
            num_drop = max(1, int(len(words) * drop_ratio))
            drop_indices = set(self.rng.sample(range(len(words)), num_drop))
            remaining = [w for i, w in enumerate(words) if i not in drop_indices]
            training = " ".join(remaining)
            return CaptionDropoutResult(
                original_caption=caption,
                training_caption=training,
                dropout_type="partial",
                dropout_rate=self.partial_drop_rate,
                strategy=f"partial_dropout_{num_drop}_of_{len(words)}_words",
            )

        # 3. Token dropout: 随机丢弃单个token
        if rand < self.full_drop_rate + self.partial_drop_rate + self.token_drop_rate:
            words = caption.split()
            if len(words) <= 2:
                return CaptionDropoutResult(
                    original_caption=caption,
                    training_caption=caption,
                    dropout_type="none",
                    dropout_rate=0.0,
                    strategy="too_short_for_token_drop",
                )
            # 随机丢弃5-15%的token
            drop_ratio = self.rng.uniform(0.05, 0.15)
            num_drop = max(1, int(len(words) * drop_ratio))
            drop_indices = set(self.rng.sample(range(len(words)), num_drop))
            remaining = [w for i, w in enumerate(words) if i not in drop_indices]
            training = " ".join(remaining)
            return CaptionDropoutResult(
                original_caption=caption,
                training_caption=training,
                dropout_type="token",
                dropout_rate=self.token_drop_rate,
                strategy=f"token_dropout_{num_drop}_of_{len(words)}_tokens",
            )

        # 4. No dropout
        return CaptionDropoutResult(
            original_caption=caption,
            training_caption=caption,
            dropout_type="none",
            dropout_rate=0.0,
            strategy="no_dropout",
        )

    def batch_apply(self, captions: List[str]) -> List[CaptionDropoutResult]:
        """批量应用dropout"""
        return [self.apply(c) for c in captions]

    def stats(self, results: List[CaptionDropoutResult]) -> Dict[str, Any]:
        """dropout统计"""
        counts = Counter(r.dropout_type for r in results)
        total = len(results)
        return {
            "total": total,
            "full_drop": counts.get("full", 0),
            "partial_drop": counts.get("partial", 0),
            "token_drop": counts.get("token", 0),
            "no_drop": counts.get("none", 0),
            "full_rate": round(counts.get("full", 0) / max(total, 1), 4),
            "partial_rate": round(counts.get("partial", 0) / max(total, 1), 4),
            "token_rate": round(counts.get("token", 0) / max(total, 1), 4),
            "effective_drop_rate": round(1 - counts.get("none", 0) / max(total, 1), 4),
        }


# ============================================================================
# 简便入口
# ============================================================================

def get_dataset_manager(base_dir: str = "./data/datasets") -> DatasetManager:
    return DatasetManager(base_dir=base_dir)
