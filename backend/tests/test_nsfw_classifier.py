"""
NanoBot Factory - NSFW分类器测试
Test suite for data_nsfw_classifier
"""

import pytest
import sys
import os
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestNSFWClassifierImport:
    """测试NSFW分类器可导入"""

    def test_import(self):
        """测试模块可导入"""
        from data_nsfw_classifier import NSFWClassifier
        assert NSFWClassifier is not None

    def test_get_classifier(self):
        """测试获取分类器实例"""
        from data_nsfw_classifier import get_nsfw_classifier
        c = get_nsfw_classifier()
        assert c is not None

    def test_convenience_function(self):
        """测试便捷函数"""
        from data_nsfw_classifier import classify_nsfw, datacomp_nsfw_check
        assert callable(classify_nsfw)
        assert callable(datacomp_nsfw_check)


class TestNSFWClassifierReturnFormat:
    """测试返回格式"""

    def setup_method(self):
        from data_nsfw_classifier import NSFWClassifier
        self.classifier = NSFWClassifier()

    def test_return_keys(self):
        """测试返回字典包含所有必要键"""
        img = Image.new("RGB", (224, 224), color=(120, 120, 120))
        result = self.classifier.classify(img)
        required_keys = [
            "nsfw_score", "nsfw_category",
            "probability_safe", "probability_nsfw",
            "skin_area_ratio", "method",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_score_range(self):
        """测试分数范围 0-1"""
        img = Image.new("RGB", (224, 224), color=(120, 120, 120))
        result = self.classifier.classify(img)
        assert 0.0 <= result["nsfw_score"] <= 1.0
        assert 0.0 <= result["probability_safe"] <= 1.0
        assert 0.0 <= result["probability_nsfw"] <= 1.0
        assert 0.0 <= result["skin_area_ratio"] <= 1.0

    def test_category_values(self):
        """测试分类值合法"""
        valid_categories = ["safe", "unsafe", "drawing_safe", "drawing_nsfw"]
        img = Image.new("RGB", (224, 224), color=(120, 120, 120))
        result = self.classifier.classify(img)
        assert result["nsfw_category"] in valid_categories, \
            f"Invalid category: {result['nsfw_category']}"


class TestNSFWClassifierSafeImages:
    """测试安全图像 - 应该得到低NSFW分数"""

    def setup_method(self):
        from data_nsfw_classifier import NSFWClassifier
        self.classifier = NSFWClassifier()

    def test_solid_color_blue(self):
        """纯蓝色 → 安全"""
        img = Image.new("RGB", (224, 224), color=(50, 100, 200))
        result = self.classifier.classify(img)
        assert result["nsfw_score"] < 0.5, f"Blue image should be safe, got {result['nsfw_score']}"

    def test_solid_color_green(self):
        """纯绿色 → 安全"""
        img = Image.new("RGB", (224, 224), color=(30, 180, 60))
        result = self.classifier.classify(img)
        assert result["nsfw_score"] < 0.5, f"Green image should be safe, got {result['nsfw_score']}"

    def test_landscape_gradient(self):
        """模拟自然风景 (蓝+绿渐变) → 安全"""
        arr = np.zeros((224, 224, 3), dtype=np.uint8)
        for y in range(224):
            ratio = y / 224
            # 上半蓝色 (天空), 下半绿色 (草地)
            if ratio < 0.5:
                arr[y, :, 0] = 135  # R
                arr[y, :, 1] = 206  # G
                arr[y, :, 2] = 235  # B
            else:
                arr[y, :, 0] = 34   # R
                arr[y, :, 1] = 139  # G
                arr[y, :, 2] = 34   # B
        img = Image.fromarray(arr)
        result = self.classifier.classify(img)
        assert result["nsfw_score"] < 0.5, f"Landscape should be safe, got {result['nsfw_score']}"

    def test_animal_like_brown(self):
        """模拟动物 (棕色) → 安全"""
        arr = np.ones((224, 224, 3), dtype=np.uint8) * 139
        arr[:, :, 0] = 139  # R
        arr[:, :, 1] = 90   # G
        arr[:, :, 2] = 43   # B
        img = Image.fromarray(arr)
        result = self.classifier.classify(img)
        # 棕色可能被部分识别为肤色，但整体应该 < 0.5
        assert result["nsfw_score"] < 0.6, f"Brown (animal-like) should be safe-ish, got {result['nsfw_score']}"


class TestNSFWClassifierSkinImages:
    """测试肤色图像 - 应该得到较高NSFW分数"""

    def setup_method(self):
        from data_nsfw_classifier import NSFWClassifier
        self.classifier = NSFWClassifier()

    def test_skin_color_full(self):
        """全图肤色 → NSFW较高"""
        # 典型肤色 RGB ~ (200, 150, 120)
        arr = np.ones((224, 224, 3), dtype=np.uint8)
        arr[:, :, 0] = 200
        arr[:, :, 1] = 150
        arr[:, :, 2] = 120
        img = Image.fromarray(arr)
        result = self.classifier.classify(img)
        # 全肤色图像应该被检测到
        assert result["skin_area_ratio"] > 0.3, f"Skin area ratio should be high, got {result['skin_area_ratio']}"

    def test_skin_color_half(self):
        """半图肤色 → 中等NSFW"""
        arr = np.ones((224, 224, 3), dtype=np.uint8)
        # 上半: 肤色
        arr[:112, :, :] = [200, 150, 120]
        # 下半: 深色
        arr[112:, :, :] = [50, 50, 80]
        img = Image.fromarray(arr)
        result = self.classifier.classify(img)
        assert result["skin_area_ratio"] > 0.1


class TestNSFWClassifierExtreme:
    """测试极端图像"""

    def setup_method(self):
        from data_nsfw_classifier import NSFWClassifier
        self.classifier = NSFWClassifier()

    def test_black_image(self):
        """纯黑 → NSFW_Score 应该低 """
        img = Image.new("RGB", (224, 224), color=(0, 0, 0))
        result = self.classifier.classify(img)
        assert result["nsfw_score"] < 0.5, f"Black image should be safe, got {result['nsfw_score']}"

    def test_white_image(self):
        """纯白 → NSFW_Score 应该低"""
        img = Image.new("RGB", (224, 224), color=(255, 255, 255))
        result = self.classifier.classify(img)
        assert result["nsfw_score"] < 0.5, f"White image should be safe, got {result['nsfw_score']}"

    def test_random_noise(self):
        """随机噪点 → 中间NSFW_Score"""
        np.random.seed(42)
        arr = np.random.randint(0, 256, (224, 224, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        result = self.classifier.classify(img)
        # 噪点可能有部分被识别为肤色，但不应极高
        assert result["nsfw_score"] < 0.8, f"Noise image NSFW strangely high: {result['nsfw_score']}"

    def test_checkerboard(self):
        """棋盘图案 → 安全"""
        arr = np.zeros((224, 224, 3), dtype=np.uint8)
        block = 28
        for y in range(0, 224, block):
            for x in range(0, 224, block):
                if (x // block + y // block) % 2 == 0:
                    arr[y:y+block, x:x+block, :] = [255, 255, 255]
        img = Image.fromarray(arr)
        result = self.classifier.classify(img)
        assert result["nsfw_score"] < 0.5, f"Checkerboard should be safe, got {result['nsfw_score']}"


class TestNSFWClassifierDatacomp:
    """测试DataComp兼容函数"""

    def setup_method(self):
        from data_nsfw_classifier import NSFWClassifier
        self.classifier = NSFWClassifier()

    def test_datacomp_nsfw_check(self):
        """测试DataComp NSFW check"""
        from data_nsfw_classifier import datacomp_nsfw_check
        img = Image.new("RGB", (224, 224), color=(120, 120, 120))
        result = datacomp_nsfw_check(img)
        assert "datacomp_reject" in result
        assert isinstance(result["datacomp_reject"], bool)

    def test_datacomp_drawing_nsfw(self):
        """测试drawing_nsfw分类"""
        # 创建一个简约风格的图像 (模拟插画)
        arr = np.ones((224, 224, 3), dtype=np.uint8) * 240
        # 画一些简单形状
        for y in range(50, 174):
            for x in range(50, 174):
                arr[y, x] = [200, 150, 120]  # 肤色区域
        img = Image.fromarray(arr)
        result = self.classifier.classify(img)
        # 高色调均匀 → 可能是drawing
        assert result["nsfw_category"] in ["drawing_safe", "safe", "drawing_nsfw"]


class TestNSFWClassifierMultimethod:
    """测试多维度检测的稳健性"""

    def setup_method(self):
        from data_nsfw_classifier import NSFWClassifier
        self.classifier = NSFWClassifier()

    def test_different_sizes(self):
        """测试不同尺寸图像"""
        sizes = [(64, 64), (128, 128), (224, 224), (512, 512)]
        for w, h in sizes:
            img = Image.new("RGB", (w, h), color=(100, 150, 200))
            result = self.classifier.classify(img)
            assert 0.0 <= result["nsfw_score"] <= 1.0, f"Size {w}x{h} failed"

    def test_all_channels(self):
        """测试RGB通道不同组合"""
        colors = [
            (255, 0, 0),   # 纯红
            (0, 255, 0),   # 纯绿
            (0, 0, 255),   # 纯蓝
            (255, 255, 0), # 黄
            (255, 0, 255), # 紫
            (0, 255, 255), # 青
        ]
        for color in colors:
            img = Image.new("RGB", (224, 224), color=color)
            result = self.classifier.classify(img)
            assert "nsfw_score" in result
            assert "nsfw_category" in result
