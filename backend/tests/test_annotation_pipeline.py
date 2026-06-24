"""
Tests for Data Annotation Pipeline (data_annotation_pipeline.py)

Covers:
- COCO format conversion
- YOLO format conversion
- LabelStudio format conversion
- CVAT XML format conversion
- BatchLabeler create_dataset_from_images
- AnnotationPipeline run_pipeline
- Format round-trip consistency
"""
import os
import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any

import pytest

# Add backend to path
_backend_dir = Path(__file__).parent.parent.resolve()
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

pytest.importorskip("data_annotation_pipeline")

from data_annotation_pipeline import (
    AnnotationFormat,
    BoundingBox,
    AnnotationItem,
    AnnotationDataset,
    AnnotationConverter,
    BatchLabeler,
    AnnotationPipeline,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_dataset() -> AnnotationDataset:
    """Create a sample dataset with 2 images and several annotations"""
    dataset = AnnotationDataset(
        name="test_dataset",
        description="Test dataset for unit tests",
        categories=[
            {"name": "cat", "supercategory": "animal"},
            {"name": "dog", "supercategory": "animal"},
        ]
    )
    # Image 1: cat and dog
    item1 = AnnotationItem(
        image_id="img_001",
        image_path="/tmp/test_images/img_001.jpg",
        width=800,
        height=600,
        bboxes=[
            BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4, category="cat", category_id=1),
            BoundingBox(x=0.5, y=0.3, width=0.2, height=0.3, category="dog", category_id=2),
        ],
        caption="A cat and a dog",
        tags=["animal", "pet"],
    )
    # Image 2: cat only
    item2 = AnnotationItem(
        image_id="img_002",
        image_path="/tmp/test_images/img_002.jpg",
        width=1024,
        height=768,
        bboxes=[
            BoundingBox(x=0.2, y=0.3, width=0.5, height=0.4, category="cat", category_id=1),
        ],
        caption="A cat",
        tags=["animal"],
    )
    dataset.items = [item1, item2]
    return dataset


@pytest.fixture
def sample_dataset_no_categories() -> AnnotationDataset:
    """Dataset with no predefined categories (auto-extract)"""
    dataset = AnnotationDataset(name="auto_cat_test")
    item = AnnotationItem(
        image_id="img_auto",
        image_path="/tmp/auto.jpg",
        width=100,
        height=100,
        bboxes=[
            BoundingBox(x=0.1, y=0.1, width=0.5, height=0.5, category="person"),
            BoundingBox(x=0.6, y=0.6, width=0.3, height=0.3, category="car"),
        ]
    )
    dataset.items = [item]
    return dataset


# ============================================================================
# AnnotationConverter Tests
# ============================================================================

class TestAnnotationConverter:
    """Tests for AnnotationConverter format conversion methods"""

    def test_to_coco_structure(self, sample_dataset):
        """COCO output should have required keys"""
        coco = AnnotationConverter.to_coco(sample_dataset)
        assert "info" in coco
        assert "licenses" in coco
        assert "categories" in coco
        assert "images" in coco
        assert "annotations" in coco

    def test_to_coco_categories(self, sample_dataset):
        """COCO categories should match input"""
        coco = AnnotationConverter.to_coco(sample_dataset)
        cat_names = [c["name"] for c in coco["categories"]]
        assert "cat" in cat_names
        assert "dog" in cat_names
        assert len(coco["categories"]) == 2

    def test_to_coco_images(self, sample_dataset):
        """COCO images should have correct IDs"""
        coco = AnnotationConverter.to_coco(sample_dataset)
        assert len(coco["images"]) == 2
        assert coco["images"][0]["id"] == "img_001"
        assert coco["images"][1]["width"] == 1024

    def test_to_coco_annotations(self, sample_dataset):
        """COCO annotations should have correct bbox format"""
        coco = AnnotationConverter.to_coco(sample_dataset)
        assert len(coco["annotations"]) == 3  # 2 + 1 boxes

        # First annotation: cat, pixel coords
        ann = coco["annotations"][0]
        assert len(ann["bbox"]) == 4
        # x, y, w, h in pixels
        assert ann["bbox"][0] == 80.0   # 0.1 * 800
        assert ann["bbox"][1] == 120.0  # 0.2 * 600
        assert ann["bbox"][2] == 240.0  # 0.3 * 800
        assert ann["bbox"][3] == 240.0  # 0.4 * 600
        assert "area" in ann
        assert "iscrowd" in ann
        assert "attributes" in ann

    def test_to_coco_no_categories(self, sample_dataset_no_categories):
        """COCO should auto-extract categories from bboxes if not provided"""
        coco = AnnotationConverter.to_coco(sample_dataset_no_categories)
        cat_names = [c["name"] for c in coco["categories"]]
        assert "person" in cat_names
        assert "car" in cat_names

    def test_to_yolo_creates_files(self, sample_dataset, temp_dir):
        """YOLO conversion should create files on disk"""
        output_dir = os.path.join(temp_dir, "yolo_out")
        result_dir = AnnotationConverter.to_yolo(sample_dataset, output_dir)
        assert os.path.isdir(result_dir)
        assert os.path.exists(os.path.join(result_dir, "data.yaml"))
        assert os.path.exists(os.path.join(result_dir, "train", "labels"))
        assert os.path.exists(os.path.join(result_dir, "train", "images"))

    def test_to_yolo_data_yaml(self, sample_dataset, temp_dir):
        """YOLO data.yaml should have correct structure"""
        output_dir = os.path.join(temp_dir, "yolo_yaml")
        AnnotationConverter.to_yolo(sample_dataset, output_dir)
        with open(os.path.join(output_dir, "data.yaml")) as f:
            content = f.read()
        assert "train: train/images" in content
        assert "nc: 2" in content
        assert "cat" in content and "dog" in content

    def test_to_yolo_label_format(self, sample_dataset, temp_dir):
        """YOLO label files should have correct format"""
        output_dir = os.path.join(temp_dir, "yolo_labels")
        AnnotationConverter.to_yolo(sample_dataset, output_dir)
        label_path = os.path.join(output_dir, "train", "labels", "img_001.txt")
        with open(label_path) as f:
            lines = f.read().strip().split("\n")
        assert len(lines) == 2
        # Format: class_id x_center y_center width height
        parts = lines[0].split()
        assert len(parts) == 5
        assert float(parts[0]) in [0, 1]  # valid class id
        assert 0 <= float(parts[1]) <= 1  # normalized coords
        assert 0 <= float(parts[2]) <= 1
        assert 0 <= float(parts[3]) <= 1
        assert 0 <= float(parts[4]) <= 1

    def test_to_label_studio_structure(self, sample_dataset):
        """Label Studio output should be a list"""
        ls = AnnotationConverter.to_label_studio(sample_dataset)
        assert isinstance(ls, list)
        assert len(ls) == 2

    def test_to_label_studio_format(self, sample_dataset):
        """Label Studio items should have required fields"""
        ls = AnnotationConverter.to_label_studio(sample_dataset)
        first = ls[0]
        assert "id" in first
        assert "data" in first
        assert "image" in first["data"]
        assert "annotations" in first
        assert "result" in first["annotations"][0]

        # Check bbox format (percentage * 100)
        result = first["annotations"][0]["result"][0]
        assert "value" in result
        assert "x" in result["value"]
        assert "y" in result["value"]
        assert "width" in result["value"]
        assert "height" in result["value"]
        # Should be 0-100 range
        assert 0 <= result["value"]["x"] <= 100
        assert 0 <= result["value"]["y"] <= 100

    def test_to_label_studio_rectangle_labels(self, sample_dataset):
        """Label Studio should have rectanglelabels"""
        ls = AnnotationConverter.to_label_studio(sample_dataset)
        labels = ls[0]["annotations"][0]["result"][0]["value"]["rectanglelabels"]
        assert isinstance(labels, list)
        assert "cat" in labels

    def test_to_cvat_xml_string(self, sample_dataset):
        """CVAT XML should be a valid XML string"""
        xml_str = AnnotationConverter.to_cvat_xml(sample_dataset)
        assert isinstance(xml_str, str)
        assert xml_str.startswith("<?xml") or xml_str.strip().startswith("<annotations")

    def test_to_cvat_xml_structure(self, sample_dataset):
        """CVAT XML should have annotations > image > box structure"""
        xml_str = AnnotationConverter.to_cvat_xml(sample_dataset)
        root = ET.fromstring(xml_str)
        assert root.tag == "annotations"
        images = root.findall("image")
        assert len(images) == 2
        boxes = images[0].findall("box")
        assert len(boxes) == 2

    def test_to_cvat_xml_box_attributes(self, sample_dataset):
        """CVAT XML boxes should have correct attributes"""
        xml_str = AnnotationConverter.to_cvat_xml(sample_dataset)
        root = ET.fromstring(xml_str)
        box = root.findall("image")[0].findall("box")[0]
        assert "label" in box.attrib
        assert "xtl" in box.attrib
        assert "ytl" in box.attrib
        assert "xbr" in box.attrib
        assert "ybr" in box.attrib

    def test_to_cvat_xml_pixel_coords(self, sample_dataset):
        """CVAT XML should use pixel coordinates"""
        xml_str = AnnotationConverter.to_cvat_xml(sample_dataset)
        root = ET.fromstring(xml_str)
        image = root.findall("image")[0]
        box = image.findall("box")[0]
        # img_001 is 800x600, first bbox is 0.1, 0.2, 0.3, 0.4
        assert float(box.attrib["xtl"]) == pytest.approx(80.0)
        assert float(box.attrib["ytl"]) == pytest.approx(120.0)
        assert float(box.attrib["xbr"]) == pytest.approx(320.0)   # (0.1+0.3)*800
        assert float(box.attrib["ybr"]) == pytest.approx(360.0)   # (0.2+0.4)*600

    def test_from_cvat_json(self):
        """from_cvat_json should reconstruct dataset"""
        cvat_items = [
            {
                "id": "img_001",
                "file_name": "test.jpg",
                "width": 800,
                "height": 600,
                "annotations": [
                    {"type": "rectangle", "category_id": "cat",
                     "bbox": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
                     "score": 0.95}
                ]
            }
        ]
        dataset = AnnotationConverter.from_cvat_json(cvat_items)
        assert isinstance(dataset, AnnotationDataset)
        assert len(dataset.items) == 1
        assert len(dataset.items[0].bboxes) == 1
        assert dataset.items[0].bboxes[0].category == "cat"
        assert dataset.items[0].bboxes[0].confidence == 0.95

    def test_coco_round_trip(self, sample_dataset):
        """to_coco output should be valid JSON-serializable"""
        coco = AnnotationConverter.to_coco(sample_dataset)
        json_str = json.dumps(coco)
        parsed = json.loads(json_str)
        assert parsed["info"]["description"] == "Test dataset for unit tests"


# ============================================================================
# BatchLabeler Tests
# ============================================================================

class TestBatchLabeler:
    """Tests for BatchLabeler"""

    def test_create_dataset_from_images(self, temp_image_dir):
        """create_dataset_from_images should scan directory"""
        labeler = BatchLabeler()
        dataset = labeler.create_dataset_from_images(temp_image_dir)
        assert isinstance(dataset, AnnotationDataset)
        assert len(dataset.items) >= 5  # 5 jpg + 5 png = 10 total

    def test_create_dataset_from_images_name(self, temp_image_dir):
        """Dataset name should include directory name"""
        labeler = BatchLabeler()
        dataset = labeler.create_dataset_from_images(temp_image_dir)
        dir_name = os.path.basename(temp_image_dir)
        assert dir_name in dataset.name

    def test_create_dataset_from_images_no_images(self, temp_dir):
        """Empty directory should produce empty dataset"""
        empty_dir = os.path.join(temp_dir, "empty")
        os.makedirs(empty_dir)
        labeler = BatchLabeler()
        dataset = labeler.create_dataset_from_images(empty_dir)
        assert len(dataset.items) == 0

    def test_create_dataset_from_images_image_props(self, temp_image_dir):
        """Images should have width/height populated"""
        labeler = BatchLabeler()
        dataset = labeler.create_dataset_from_images(temp_image_dir)
        for item in dataset.items:
            assert item.width > 0
            assert item.height > 0
            assert item.image_path != ""

    def test_merge_datasets(self, sample_dataset):
        """merge_datasets should combine items and categories"""
        ds2 = AnnotationDataset(
            name="second", categories=[{"name": "bird"}],
            items=[AnnotationItem(image_id="img_003", image_path="/x.jpg", width=1, height=1)]
        )
        merged = BatchLabeler.merge_datasets([sample_dataset, ds2], new_name="merged_ds")
        assert merged.name == "merged_ds"
        assert len(merged.items) == 3  # 2 + 1
        # Categories should be deduped
        assert len(merged.categories) == 3  # cat, dog, bird

    def test_auto_label_dataset_no_fn(self, sample_dataset):
        """auto_label_dataset with no function should return unchanged"""
        labeler = BatchLabeler()
        result = labeler.auto_label_dataset(sample_dataset)
        assert len(result.items) == len(sample_dataset.items)
        assert result.items[0].bboxes == sample_dataset.items[0].bboxes

    def test_auto_label_dataset_with_fn(self, sample_dataset):
        """auto_label_dataset should call the function"""
        def dummy_label_fn(path):
            return [BoundingBox(x=0.5, y=0.5, width=0.2, height=0.2, category="auto")]
        # Start with empty bboxes
        ds = AnnotationDataset(
            name="test",
            items=[AnnotationItem(image_id="1", image_path="/tmp/x.jpg", width=100, height=100)]
        )
        labeler = BatchLabeler(auto_label_fn=dummy_label_fn)
        result = labeler.auto_label_dataset(ds)
        assert len(result.items[0].bboxes) == 1
        assert result.items[0].bboxes[0].category == "auto"


# ============================================================================
# AnnotationPipeline Tests
# ============================================================================

class TestAnnotationPipeline:
    """Tests for AnnotationPipeline"""

    def test_run_pipeline_no_images(self, temp_dir):
        """run_pipeline with empty dir should return no_images status"""
        empty_dir = os.path.join(temp_dir, "no_imgs")
        os.makedirs(empty_dir)
        pipeline = AnnotationPipeline(output_dir=os.path.join(temp_dir, "output"))
        result = pipeline.run_pipeline(empty_dir)
        assert result["status"] == "no_images"

    def test_run_pipeline_with_images(self, temp_image_dir, temp_dir):
        """run_pipeline should process images and export formats"""
        output_dir = os.path.join(temp_dir, "output")
        pipeline = AnnotationPipeline(output_dir=output_dir)
        result = pipeline.run_pipeline(
            temp_image_dir,
            formats=[AnnotationFormat.COCO, AnnotationFormat.LABEL_STUDIO]
        )
        assert result["status"] == "completed"
        assert result["total_images"] >= 5
        assert "coco" in result["output_formats"]
        assert "label_studio" in result["output_formats"]

    def test_run_pipeline_creates_files(self, temp_image_dir, temp_dir):
        """run_pipeline should create output files on disk"""
        output_dir = os.path.join(temp_dir, "output_files")
        pipeline = AnnotationPipeline(output_dir=output_dir)
        pipeline.run_pipeline(
            temp_image_dir,
            formats=[AnnotationFormat.COCO]
        )
        # Check that annotations.json was created
        ds_name = f"dataset_{os.path.basename(temp_image_dir)}"
        ann_path = os.path.join(output_dir, ds_name, "annotations.json")
        assert os.path.exists(ann_path)

    def test_run_pipeline_stats(self, temp_image_dir, temp_dir):
        """run_pipeline should write pipeline_stats.json"""
        output_dir = os.path.join(temp_dir, "output_stats")
        pipeline = AnnotationPipeline(output_dir=output_dir)
        pipeline.run_pipeline(temp_image_dir, formats=[AnnotationFormat.COCO])
        stats_path = os.path.join(output_dir, "pipeline_stats.json")
        assert os.path.exists(stats_path)
        with open(stats_path) as f:
            stats = json.load(f)
        assert stats["status"] == "completed"
        assert "total_images" in stats
