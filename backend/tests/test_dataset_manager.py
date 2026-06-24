"""
Tests for Data Dataset Manager (data_dataset_manager.py)

Covers:
- create_from_image_dir
- split_dataset train/val/test split
- create_hf_json export and reload
- create_webdataset export (TAR)
- compute_stats statistics
- DatasetEntry / DatasetMetadata dataclasses
- Format detection
"""
import os
import sys
import json
import tarfile
import io
from pathlib import Path
from typing import List

import pytest
from PIL import Image

# Add backend to path
_backend_dir = Path(__file__).parent.parent.resolve()
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

pytest.importorskip("data_dataset_manager")

from data_dataset_manager import (
    DatasetFormat,
    DatasetEntry,
    DatasetSplit,
    DatasetMetadata,
    DatasetStats,
    DatasetManager,
    get_dataset_manager,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_entries() -> List[DatasetEntry]:
    """Create a list of sample DatasetEntry objects"""
    entries = []
    for i in range(10):
        entry = DatasetEntry(
            entry_id=f"entry_{i:04d}",
            image_path=f"/tmp/images/img_{i:04d}.jpg",
            caption=f"A sample caption number {i}" if i < 8 else "",
            width=1920,
            height=1080,
            file_size=1024 * 50 + i * 100,
            split="train",
            metadata={"index": i, "source": "test"},
        )
        entries.append(entry)
    return entries


@pytest.fixture
def manager(temp_dir) -> DatasetManager:
    """Create a DatasetManager with temp directory"""
    return DatasetManager(base_dir=os.path.join(temp_dir, "datasets"))


# ============================================================================
# DatasetEntry / DatasetSplit / DatasetMetadata Tests
# ============================================================================

class TestDatasetEntry:
    """Tests for DatasetEntry dataclass"""

    def test_default_values(self):
        entry = DatasetEntry(entry_id="test")
        assert entry.entry_id == "test"
        assert entry.image_path == ""
        assert entry.caption == ""
        assert entry.text == ""
        assert entry.metadata == {}
        assert entry.split == "train"
        assert entry.file_size == 0
        assert entry.width == 0
        assert entry.height == 0

    def test_custom_values(self):
        entry = DatasetEntry(
            entry_id="e1", image_path="/x.jpg", caption="test",
            width=100, height=200, split="val",
            metadata={"key": "value"}
        )
        assert entry.width == 100
        assert entry.height == 200
        assert entry.split == "val"
        assert entry.metadata["key"] == "value"

    def test_timestamp_auto(self):
        entry = DatasetEntry(entry_id="ts")
        assert entry.timestamp != ""


class TestDatasetSplit:
    def test_defaults(self):
        s = DatasetSplit(name="train")
        assert s.name == "train"
        assert s.num_entries == 0
        assert s.file_paths == []


class TestDatasetMetadata:
    def test_defaults(self):
        m = DatasetMetadata(name="test")
        assert m.name == "test"
        assert m.format == "hf_json"
        assert m.total_entries == 0
        assert m.splits == []
        assert m.created_at != ""


# ============================================================================
# DatasetManager Tests
# ============================================================================

class TestDatasetManagerCreateFromImageDir:
    """Tests for create_from_image_dir"""

    def test_create_from_directory(self, manager, temp_image_dir):
        entries = manager.create_from_image_dir("test_ds", temp_image_dir)
        assert len(entries) >= 5
        for e in entries:
            assert e.entry_id != ""
            assert e.image_path != ""
            assert e.width > 0
            assert e.height > 0
            assert e.split == "train"

    def test_create_metadata_file(self, manager, temp_image_dir):
        entries = manager.create_from_image_dir("meta_ds", temp_image_dir)
        meta = manager.load_metadata("meta_ds")
        assert meta is not None
        assert meta.name == "meta_ds"
        assert meta.total_entries == len(entries)

    def test_create_nonexistent_dir(self, manager):
        with pytest.raises(FileNotFoundError):
            manager.create_from_image_dir("bad", "/nonexistent/xyz")

    def test_create_empty_dir(self, manager, temp_dir):
        empty = os.path.join(temp_dir, "empty")
        os.makedirs(empty)
        entries = manager.create_from_image_dir("empty_ds", empty)
        assert len(entries) == 0


class TestDatasetManagerSplitDataset:
    """Tests for split_dataset"""

    def test_default_split(self, sample_entries):
        manager = DatasetManager()
        result = manager.split_dataset(sample_entries,
                                        train_ratio=0.8, val_ratio=0.1, test_ratio=0.1)
        assert len(result["train"]) == 8
        assert len(result["val"]) == 1
        assert len(result["test"]) == 1

    def test_split_sums_to_total(self, sample_entries):
        manager = DatasetManager()
        result = manager.split_dataset(sample_entries,
                                        train_ratio=0.7, val_ratio=0.2, test_ratio=0.1)
        total = len(result["train"]) + len(result["val"]) + len(result["test"])
        assert total == len(sample_entries)

    def test_split_updates_field(self, sample_entries):
        manager = DatasetManager()
        result = manager.split_dataset(sample_entries)
        for e in result["train"]:
            assert e.split == "train"
        for e in result["val"]:
            assert e.split == "val"
        for e in result["test"]:
            assert e.split == "test"

    def test_split_all_train(self, sample_entries):
        manager = DatasetManager()
        result = manager.split_dataset(sample_entries,
                                        train_ratio=1.0, val_ratio=0.0, test_ratio=0.0)
        assert len(result["train"]) == 10
        assert len(result["val"]) == 0
        assert len(result["test"]) == 0

    def test_split_invalid_ratios(self, sample_entries):
        manager = DatasetManager()
        with pytest.raises(AssertionError):
            manager.split_dataset(sample_entries,
                                   train_ratio=0.5, val_ratio=0.3, test_ratio=0.3)

    def test_split_empty_list(self):
        manager = DatasetManager()
        result = manager.split_dataset([])
        assert len(result["train"]) == 0
        assert len(result["val"]) == 0
        assert len(result["test"]) == 0

    def test_split_shuffle_seed(self, sample_entries):
        """Same seed should produce same split"""
        manager = DatasetManager()
        r1 = manager.split_dataset(sample_entries, seed=42)
        r2 = manager.split_dataset(sample_entries, seed=42)
        # Same order within each split (train entries should be the same IDs)
        assert [e.entry_id for e in r1["train"]] == [e.entry_id for e in r2["train"]]


class TestDatasetManagerHfJson:
    """Tests for HuggingFace JSON format"""

    def test_create_hf_json(self, manager, sample_entries, temp_dir):
        ds_dir = manager.create_hf_json("hf_test", sample_entries)
        assert os.path.isdir(ds_dir)
        split_dir = os.path.join(ds_dir, "train")
        assert os.path.isdir(split_dir)
        assert os.path.isfile(os.path.join(split_dir, "train.json"))

    def test_create_hf_json_metadata(self, manager, sample_entries):
        ds_dir = manager.create_hf_json("hf_meta", sample_entries)
        meta_path = os.path.join(ds_dir, "dataset_metadata.json")
        assert os.path.exists(meta_path)
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "hf_meta"
        assert meta["total_entries"] == 10

    def test_load_hf_json(self, manager, sample_entries):
        ds_dir = manager.create_hf_json("hf_load", sample_entries)
        loaded = manager.load_hf_json(os.path.join(ds_dir, "train"))
        assert len(loaded) == 10
        for entry in loaded:
            assert isinstance(entry, DatasetEntry)
            assert entry.entry_id.startswith("entry_")

    def test_load_hf_json_full_path(self, manager, sample_entries):
        ds_dir = manager.create_hf_json("hf_full", sample_entries)
        loaded = manager.load_hf_json(os.path.join(ds_dir, "train", "train.json"))
        assert len(loaded) == 10

    def test_hf_json_round_trip(self, manager, sample_entries):
        ds_dir = manager.create_hf_json("hf_round", sample_entries)
        loaded = manager.load_hf_json(os.path.join(ds_dir, "train"))
        assert loaded[0].entry_id == sample_entries[0].entry_id
        assert loaded[0].caption == sample_entries[0].caption
        assert loaded[0].width == sample_entries[0].width

    def test_create_hf_json_with_shards(self, manager, sample_entries):
        ds_dir = manager.create_hf_json("hf_shard", sample_entries, shard_size=3)
        split_dir = os.path.join(ds_dir, "train")
        json_files = [f for f in os.listdir(split_dir) if f.endswith(".json")]
        assert len(json_files) > 1  # Multiple shards

    def test_load_hf_json_nonexistent(self, manager):
        with pytest.raises(FileNotFoundError):
            manager.load_hf_json("/nonexistent/path")


class TestDatasetManagerWebdataset:
    """Tests for WebDataset TAR format"""

    def test_create_webdataset(self, manager, sample_entries, temp_dir):
        # Use entries without real images paths (no_image mode)
        ds_dir = manager.create_webdataset("wd_test", sample_entries,
                                            shard_size=5, include_images=False)
        assert os.path.isdir(ds_dir)
        tar_files = sorted(os.listdir(ds_dir))
        # Filter only tar files
        tar_files = [f for f in tar_files if f.endswith(".tar")]
        assert len(tar_files) >= 2  # 10 entries / 5 shard_size

    def test_create_webdataset_manifest(self, manager, sample_entries):
        ds_dir = manager.create_webdataset("wd_manifest", sample_entries,
                                            shard_size=5, include_images=False)
        manifest_path = os.path.join(ds_dir, "_manifest.json")
        assert os.path.exists(manifest_path)
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["format"] == "webdataset"
        assert manifest["num_entries"] == 10

    def test_webdataset_tar_contents(self, manager, sample_entries):
        ds_dir = manager.create_webdataset("wd_tar", sample_entries[:2],
                                            shard_size=2, include_images=False)
        tar_path = os.path.join(ds_dir, "shard-000000.tar")
        with tarfile.open(tar_path, "r") as tar:
            names = tar.getnames()
        # Each entry should have .json and .txt
        assert any(n.endswith(".json") for n in names)
        # At least entry_0000 should have .txt (caption exists)
        assert any(n.endswith(".txt") for n in names)

    def test_webdataset_json_in_tar(self, manager, sample_entries):
        ds_dir = manager.create_webdataset("wd_json", sample_entries[:1],
                                            shard_size=1, include_images=False)
        tar_path = os.path.join(ds_dir, "shard-000000.tar")
        with tarfile.open(tar_path, "r") as tar:
            json_member = [m for m in tar.getmembers() if m.name.endswith(".json")][0]
            f = tar.extractfile(json_member)
            data = json.loads(f.read().decode("utf-8"))
        assert data["entry_id"] == sample_entries[0].entry_id
        assert data["caption"] == sample_entries[0].caption

    def test_create_webdataset_with_images(self, manager, temp_image_dir):
        """WebDataset should include images when requested"""
        entries = [DatasetEntry(
            entry_id="img_entry",
            image_path=os.path.join(temp_image_dir, "test_0.jpg"),
            caption="test image",
        )]
        ds_dir = manager.create_webdataset("wd_img", entries,
                                            shard_size=1, include_images=True,
                                            image_base_dir="")
        tar_path = os.path.join(ds_dir, "shard-000000.tar")
        with tarfile.open(tar_path, "r") as tar:
            names = tar.getnames()
        # Should have an image file (jpg or png)
        img_names = [n for n in names if n.endswith((".jpg", ".jpeg", ".png"))]
        assert len(img_names) >= 1

    def test_create_webdataset_empty(self, manager):
        """Empty entries list should produce 0 shards or a single empty tar"""
        ds_dir = manager.create_webdataset("wd_empty", [],
                                            shard_size=5, include_images=False)
        tar_files = [f for f in os.listdir(ds_dir) if f.endswith(".tar")]
        # At minimum, should not crash
        assert isinstance(ds_dir, str)


class TestDatasetManagerStats:
    """Tests for DatasetStats"""

    def test_compute_stats_basic(self, sample_entries):
        stats = DatasetStats.compute_stats(sample_entries)
        assert stats["total_entries"] == 10
        assert stats["num_images"] == 10
        assert stats["num_captions"] == 8  # entries 8,9 have empty caption

    def test_compute_stats_dimensions(self, sample_entries):
        stats = DatasetStats.compute_stats(sample_entries)
        assert stats["width"]["min"] == 1920
        assert stats["width"]["max"] == 1920
        assert stats["height"]["min"] == 1080
        assert stats["height"]["max"] == 1080

    def test_compute_stats_caption_length(self, sample_entries):
        stats = DatasetStats.compute_stats(sample_entries)
        assert stats["caption_length"]["min"] >= 4
        assert stats["caption_length"]["max"] >= 4

    def test_compute_stats_empty(self):
        stats = DatasetStats.compute_stats([])
        assert stats["total"] == 0

    def test_compute_stats_split_distribution(self, sample_entries):
        stats = DatasetStats.compute_stats(sample_entries)
        assert "train" in stats["splits"]
        assert stats["splits"]["train"] == 10

    def test_compute_stats_image_formats(self, sample_entries):
        stats = DatasetStats.compute_stats(sample_entries)
        assert ".jpg" in stats["image_formats"]

    def test_print_summary(self, sample_entries):
        stats = DatasetStats.compute_stats(sample_entries)
        summary = DatasetStats.print_summary(stats)
        assert "Dataset Summary:" in summary
        assert "10" in summary  # total entries
        assert "1920" in summary  # width average

    def test_print_summary_empty(self):
        summary = DatasetStats.print_summary({"total": 0})
        assert "Empty" in summary


class TestDatasetManagerUtils:
    """Tests for utility methods"""

    def test_detect_format_hf_json(self, manager, sample_entries):
        ds_dir = manager.create_hf_json("detect_hf", sample_entries)
        fmt = manager.detect_format(ds_dir)
        assert fmt in ("hf_json", "raw_image")

    def test_detect_format_webdataset(self, manager, sample_entries):
        ds_dir = manager.create_webdataset("detect_wd", sample_entries[:2],
                                            shard_size=2, include_images=False)
        fmt = manager.detect_format(ds_dir)
        assert fmt == "webdataset"

    def test_detect_format_nonexistent(self, manager):
        fmt = manager.detect_format("/nonexistent")
        assert fmt is None

    def test_detect_format_tar_file(self, manager, sample_entries):
        ds_dir = manager.create_webdataset("detect_tar", sample_entries[:2],
                                            shard_size=2, include_images=False)
        tar_path = os.path.join(ds_dir, "shard-000000.tar")
        fmt = manager.detect_format(tar_path)
        assert fmt == "webdataset"

    def test_list_datasets_empty(self, manager):
        datasets = manager.list_datasets()
        assert datasets == []

    def test_list_datasets_with_data(self, manager, sample_entries):
        manager.create_hf_json("list_test", sample_entries)
        datasets = manager.list_datasets()
        assert "list_test" in datasets

    def test_create_from_memory(self, manager):
        data = [
            {"entry_id": "mem_1", "caption": "hello", "width": 100, "height": 200},
            {"entry_id": "mem_2", "caption": "world"},
        ]
        entries = DatasetManager.create_from_memory(data)
        assert len(entries) == 2
        assert entries[0].entry_id == "mem_1"
        assert entries[0].width == 100
        assert entries[1].caption == "world"
