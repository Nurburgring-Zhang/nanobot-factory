"""
NanoBot Factory - Face Pipeline Tests
测试人脸数据处理管线

测试覆盖:
1. 人脸检测 (Haar Cascade)
2. 68点关键点估计
3. 人脸质量评估
4. 姿态估计
5. FaceSwap格式生成
6. IP-Adapter Face格式生成
7. ArcFace目录结构
8. 可视化辅助
"""

import pytest
import sys
import os
import json
import tempfile
from pathlib import Path
from PIL import Image
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFacePipeline:
    """人脸管线测试"""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """每个测试前的设置"""
        # 创建测试图像（包含人脸模拟区域）
        img = Image.new("RGB", (200, 200), (100, 100, 100))
        # 画一个椭圆模拟人脸
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.ellipse([50, 30, 150, 170], fill=(200, 150, 100))  # 肤色椭圆
        draw.ellipse([70, 60, 90, 80], fill=(0, 0, 0))  # 左眼
        draw.ellipse([110, 60, 130, 80], fill=(0, 0, 0))  # 右眼
        draw.ellipse([80, 100, 120, 130], fill=(0, 0, 0))  # 嘴巴
        self.test_image_path = str(tmp_path / "test_face.png")
        img.save(self.test_image_path)
        self.test_image = img

    def test_import(self):
        """测试模块导入"""
        from data_face_pipeline import FacePipeline, get_face_pipeline
        assert FacePipeline is not None
        pipeline = get_face_pipeline()
        assert isinstance(pipeline, FacePipeline)

    def test_detect_faces(self):
        """测试人脸检测"""
        from data_face_pipeline import FacePipeline
        pipeline = FacePipeline()
        faces = pipeline.detect_faces(self.test_image_path)
        # 至少能返回结果（可能因为图像太简单检测不到，但不应该抛异常）
        assert isinstance(faces, list)

    def test_detect_faces_invalid(self):
        """测试无效图像的人脸检测"""
        from data_face_pipeline import FacePipeline
        pipeline = FacePipeline()
        faces = pipeline.detect_faces("nonexistent.jpg")
        assert faces == []

    def test_face_detection_dataclass(self):
        """测试FaceDetection数据类"""
        from data_face_pipeline import FaceDetection, FaceLandmark68
        det = FaceDetection(
            id="face_test",
            bbox=(10, 20, 100, 120),
            confidence=0.95,
        )
        assert det.id == "face_test"
        assert det.bbox == (10, 20, 100, 120)
        assert det.confidence == 0.95

    def test_landmark_68_to_from_list(self):
        """测试68点关键点序列化"""
        from data_face_pipeline import FaceLandmark68
        # 创建68个测试点
        test_points = [(float(i), float(i * 2)) for i in range(68)]
        landmarks = FaceLandmark68.from_list(test_points)
        assert len(landmarks.jaw) == 17
        assert len(landmarks.left_eyebrow) == 5
        assert len(landmarks.right_eyebrow) == 5
        assert len(landmarks.nose_bridge) == 4
        assert len(landmarks.nose_tip) == 5
        assert len(landmarks.left_eye) == 6
        assert len(landmarks.right_eye) == 6
        assert len(landmarks.outer_lip) == 12
        assert len(landmarks.inner_lip) == 8

        # 转回list
        back = landmarks.to_list()
        assert len(back) == 68
        # 验证前几个点
        assert abs(back[0][0] - 0.0) < 0.01
        assert abs(back[0][1] - 0.0) < 0.01

    def test_landmark_padding(self):
        """测试关键点补齐"""
        from data_face_pipeline import FaceLandmark68
        # 少于68点
        short = [(1.0, 2.0)] * 10
        landmarks = FaceLandmark68.from_list(short)
        back = landmarks.to_list()
        assert len(back) == 68
        # 前10个应该有值，后面的为(0,0)
        assert back[0][0] == 1.0
        assert back[10][0] == 0.0

    def test_estimate_pose(self):
        """测试姿态估计"""
        from data_face_pipeline import FacePipeline
        pipeline = FacePipeline()
        # 用纯灰色图像测试姿态估计（不抛异常即可）
        gray_img = np.ones((100, 100), dtype=np.uint8) * 128
        yaw, pitch, roll = pipeline._estimate_pose(gray_img)
        assert isinstance(yaw, float)
        assert isinstance(pitch, float)
        assert isinstance(roll, float)

    def test_face_quality_score(self):
        """测试人脸质量评分"""
        from data_face_pipeline import FacePipeline
        pipeline = FacePipeline()
        face = np.ones((100, 100), dtype=np.uint8) * 128
        score = pipeline._face_quality_score(face, 100, 100)
        assert 0.0 <= score <= 1.0

    def test_create_faceswap_item(self):
        """测试FaceSwap条目创建"""
        from data_face_pipeline import FacePipeline
        pipeline = FacePipeline()
        item = pipeline.create_faceswap_item(
            self.test_image_path,
            self.test_image,
        )
        # 应该返回有效对象或None（如果人脸检测不到）
        if item is not None:
            assert item.id.startswith("faceswap_")
            assert item.source_image == self.test_image_path
            assert isinstance(item.landmarks_68, list)

    def test_faceswap_dataclass(self):
        """测试FaceSwap数据类"""
        from data_face_pipeline import FaceSwapItem
        item = FaceSwapItem(
            id="fs_test",
            source_image="src.jpg",
            target_image="tgt.jpg",
            landmarks_68=[0.0] * 136,  # 68*2
        )
        assert item.id == "fs_test"
        assert len(item.landmarks_68) == 136

    def test_ip_adapter_face_item(self):
        """测试IP-Adapter Face数据类"""
        from data_face_pipeline import IPAdapterFaceItem
        item = IPAdapterFaceItem(
            id="ip_test",
            person_image="person.jpg",
            style_images=["style1.jpg", "style2.jpg"],
            identity="person_001",
        )
        assert item.id == "ip_test"
        assert len(item.style_images) == 2

    def test_identity_entry(self):
        """测试IdentityEntry数据类"""
        from data_face_pipeline import IdentityEntry
        entry = IdentityEntry(
            identity_id="id_001",
            identity_name="Person A",
            image_paths=["img1.jpg", "img2.jpg"],
            num_images=2,
        )
        assert entry.identity_id == "id_001"
        assert entry.num_images == 2

    def test_create_identity_dirs(self, tmp_path):
        """测试ArcFace目录结构创建"""
        from data_face_pipeline import FacePipeline
        pipeline = FacePipeline()
        identity_images = {
            "person_001": [self.test_image_path],
            "person_002": [self.test_image_path, self.test_image_path],
        }
        base_dir = str(tmp_path / "arcface_test")
        result = pipeline.create_identity_dirs(base_dir, identity_images)
        assert os.path.exists(result)
        assert os.path.exists(os.path.join(result, "metadata.json"))
        assert os.path.exists(os.path.join(result, "identities", "person_001"))
        assert os.path.exists(os.path.join(result, "identities", "person_002"))

        with open(os.path.join(result, "metadata.json")) as f:
            meta = json.load(f)
        assert meta["num_identities"] == 2
        assert meta["total_images"] >= 2

    def test_align_face(self):
        """测试人脸对齐"""
        from data_face_pipeline import FacePipeline
        pipeline = FacePipeline()
        result = pipeline.align_face(self.test_image_path, target_size=(160, 160))
        # 可能检测不到人脸，不抛异常即可
        if result is not None:
            assert isinstance(result, Image.Image)
            assert result.size == (160, 160)

    def test_save_faceswap_jsonl(self, tmp_path):
        """测试FaceSwap JSONL保存"""
        from data_face_pipeline import FacePipeline
        pipeline = FacePipeline()
        item = pipeline.create_faceswap_item(self.test_image_path, self.test_image)
        if item is not None:
            output = str(tmp_path / "faceswap.jsonl")
            pipeline.save_faceswap_jsonl([item], output)
            assert os.path.exists(output)

    def test_save_ip_adapter_jsonl(self, tmp_path):
        """测试IP-Adapter JSONL保存"""
        from data_face_pipeline import FacePipeline, IPAdapterFaceItem
        pipeline = FacePipeline()
        item = IPAdapterFaceItem(
            id="ip_test",
            person_image="person.jpg",
            style_images=["style1.jpg"],
            identity="test_id",
        )
        output = str(tmp_path / "ipadapter.jsonl")
        pipeline.save_ip_adapter_jsonl([item], output)
        assert os.path.exists(output)
        with open(output) as f:
            data = json.loads(f.readline())
        assert data["person_image"] == "person.jpg"

    def test_save_detection_jsonl(self, tmp_path):
        """测试检测结果保存"""
        from data_face_pipeline import FacePipeline, FaceDetection
        pipeline = FacePipeline()
        det = FaceDetection(
            id="face_det",
            bbox=(10, 20, 50, 60),
            confidence=0.9,
            quality=0.8,
            landmarks_2d=[0.0] * 136,
        )
        output = str(tmp_path / "detection.jsonl")
        pipeline.save_detection_jsonl([det], self.test_image_path, output)
        assert os.path.exists(output)
        with open(output) as f:
            data = json.loads(f.readline())
        assert data["face_id"] == "face_det"
        assert data["image"] == self.test_image_path

    def test_draw_landmarks(self, tmp_path):
        """测试关键点绘制"""
        from data_face_pipeline import FacePipeline
        pipeline = FacePipeline()
        landmarks = [float(i) for i in range(136)]  # 68*2 dummy points
        output = str(tmp_path / "landmarks_viz.png")
        result = pipeline.draw_landmarks(self.test_image_path, landmarks, output)
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_draw_face_bbox(self, tmp_path):
        """测试人脸框绘制"""
        from data_face_pipeline import FacePipeline, FaceDetection
        pipeline = FacePipeline()
        faces = [FaceDetection(bbox=(10, 20, 50, 60), quality=0.9)]
        output = str(tmp_path / "bbox_viz.png")
        result = pipeline.draw_face_bbox(self.test_image_path, faces, output)
        assert result is not None
        assert isinstance(result, Image.Image)

    def test_batch_faceswap(self):
        """测试批量FaceSwap"""
        from data_face_pipeline import FacePipeline
        pipeline = FacePipeline()
        pairs = [(self.test_image_path, self.test_image)]
        results = pipeline.batch_faceswap(pairs)
        assert isinstance(results, list)
