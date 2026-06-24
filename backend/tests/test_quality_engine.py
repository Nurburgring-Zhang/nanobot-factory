"""
Tests for Data Quality Engine (data_quality_engine.py)

Covers:
- QualityScore data structure
- score_image basic property analysis (sharpness/brightness/contrast/colorfulness)
- Batch scoring
- Perceptual hashing (phash/hamming_distance/find_duplicates)
- Boundary conditions (empty images, missing captions)
- Duplicate image detection
"""
import os
import sys
import io
import json
from pathlib import Path
from typing import List, Tuple

import pytest
import numpy as np
from PIL import Image

# Add backend to path
_backend_dir = Path(__file__).parent.parent.resolve()
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# Module-level skip if imports fail
pytest.importorskip("data_quality_engine")

from data_quality_engine import (
    QualityScore,
    BatchQualityReport,
    DataQualityEngine,
    PerceptualHasher,
    get_quality_engine,
)


# ============================================================================
# QualityScore Data Structure Tests
# ============================================================================

class TestQualityScore:
    """Tests for QualityScore dataclass"""

    def test_default_values(self):
        """QualityScore should initialize with all default values"""
        score = QualityScore()
        assert score.overall_score == 0.0
        assert score.aesthetic_score == 0.0
        assert score.technical_quality == 0.0
        assert score.clip_score == 0.0
        assert score.sharpness == 0.0
        assert score.brightness == 0.0
        assert score.contrast == 0.0
        assert score.colorfulness == 0.0
        assert score.noise_level == 0.0
        assert score.face_count == 0
        assert score.nsfw_probability == 0.0
        assert score.watermark_probability == 0.0
        assert score.width == 0
        assert score.height == 0
        assert score.aspect_ratio == 0.0
        assert score.timestamp != ""

    def test_custom_values(self):
        """QualityScore should accept custom values"""
        score = QualityScore(
            overall_score=0.85,
            sharpness=0.75,
            brightness=0.6,
            contrast=0.8,
            colorfulness=0.9,
            width=1920,
            height=1080,
        )
        assert score.overall_score == 0.85
        assert score.sharpness == 0.75
        assert score.aspect_ratio == 0.0  # Not auto-calculated
        assert score.width == 1920
        assert score.height == 1080

    def test_field_types(self):
        """All fields should be correct types"""
        score = QualityScore()
        assert isinstance(score.overall_score, float)
        assert isinstance(score.face_count, int)
        assert isinstance(score.width, int)
        assert isinstance(score.timestamp, str)
        assert score.saturation is None  # Optional
        assert score.video_fps is None

    def test_as_dict(self):
        """QualityScore should be convertible to dict"""
        score = QualityScore(overall_score=0.9, sharpness=0.8)
        d = score.__dict__
        assert isinstance(d, dict)
        assert d["overall_score"] == 0.9
        assert d["sharpness"] == 0.8
        assert "timestamp" in d


class TestBatchQualityReport:
    """Tests for BatchQualityReport dataclass"""

    def test_default_values(self):
        report = BatchQualityReport()
        assert report.total == 0
        assert report.passed == 0
        assert report.failed == 0
        assert report.avg_scores == {}
        assert report.distribution == {}
        assert report.passed_ids == []
        assert report.failed_ids == []
        assert report.threshold == 0.5

    def test_custom_values(self):
        report = BatchQualityReport(
            total=10, passed=7, failed=3,
            threshold=0.6
        )
        assert report.total == 10
        assert report.passed == 7
        assert report.failed == 3
        assert report.threshold == 0.6


# ============================================================================
# DataQualityEngine Tests
# ============================================================================

class TestDataQualityEngine:
    """Tests for DataQualityEngine scoring methods"""

    @pytest.fixture
    def engine(self):
        """Create a quality engine with model loading skipped"""
        return get_quality_engine(skip_model_init=True, force_reinit=True)

    def test_engine_init(self, engine):
        """Engine should initialize without crashing"""
        assert engine is not None
        assert engine._initialized is True

    def test_score_image_with_pil(self, engine, test_image_pil):
        """score_image should work with PIL Image input"""
        result = engine.score_image(test_image_pil)
        assert isinstance(result, QualityScore)
        assert result.width > 0
        assert result.height > 0
        assert result.aspect_ratio > 0

    def test_score_image_properties_sharpness(self, engine, test_image_sharp):
        """Sharp image should have higher sharpness score"""
        result = engine.score_image(test_image_sharp)
        # Checkerboard pattern should give non-zero sharpness
        assert result.sharpness > 0.1

    def test_score_image_properties_brightness(self, engine, test_image_solid):
        """Solid gray image should have ~0.5 brightness"""
        result = engine.score_image(test_image_solid)
        assert 0.45 <= result.brightness <= 0.55

    def test_score_image_properties_blank(self, engine, test_image_blank):
        """Blank (black) image should have 0 brightness"""
        result = engine.score_image(test_image_blank)
        assert result.brightness < 0.05
        assert result.contrast < 0.05

    def test_score_image_properties_random(self, engine, test_image_pil):
        """Random image should have non-zero colorfulness"""
        result = engine.score_image(test_image_pil)
        # Gradient image has color variation
        assert result.colorfulness > 0

    def test_score_image_with_caption(self, engine, test_image_pil):
        """score_image should accept and handle caption gracefully"""
        result = engine.score_image(test_image_pil, caption="A test image")
        assert isinstance(result, QualityScore)
        # Without CLIP model, clip_score should be 0
        assert result.clip_score == 0.0
        assert result.caption_quality == 0.0

    def test_score_image_empty_caption(self, engine, test_image_pil):
        """score_image with empty caption should not crash"""
        result = engine.score_image(test_image_pil, caption="")
        assert isinstance(result, QualityScore)

    def test_score_image_no_caption(self, engine, test_image_pil):
        """score_image with no caption argument should work"""
        result = engine.score_image(test_image_pil)
        assert isinstance(result, QualityScore)

    def test_score_image_bytes_input(self, engine, test_image_bytes):
        """score_image should work with bytes input"""
        result = engine.score_image(test_image_bytes)
        assert isinstance(result, QualityScore)
        assert result.width > 0

    def test_score_image_invalid_path(self, engine):
        """score_image with invalid path should return default score"""
        result = engine.score_image("/nonexistent/path/to/image.jpg")
        assert isinstance(result, QualityScore)
        assert result.width == 0  # Default

    def test_score_image_empty_bytes(self, engine):
        """score_image with empty bytes should not crash"""
        result = engine.score_image(b"")
        assert isinstance(result, QualityScore)

    def test_overall_score_calculation(self, engine, test_image_pil):
        """Overall score should be a weighted combination"""
        result = engine.score_image(test_image_pil)
        assert 0.0 <= result.overall_score <= 1.0

    def test_aspect_ratio(self, engine, test_image_pil):
        """Aspect ratio should be correctly calculated"""
        w, h = test_image_pil.size
        result = engine.score_image(test_image_pil)
        expected_ratio = round(w / max(h, 1), 4)
        assert result.aspect_ratio == expected_ratio

    def test_contrast_range(self, engine, test_image_pil):
        """Contrast should be in [0, 1] range"""
        result = engine.score_image(test_image_pil)
        assert 0.0 <= result.contrast <= 1.0

    def test_noise_level(self, engine, test_image_pil):
        """Noise level should be in [0, 1] range"""
        result = engine.score_image(test_image_pil)
        assert 0.0 <= result.noise_level <= 1.0

    def test_score_batch_empty(self, engine):
        """score_batch with empty list should return empty report"""
        report = engine.score_batch([])
        assert isinstance(report, BatchQualityReport)
        assert report.total == 0

    def test_score_batch_with_items(self, engine, temp_image_with_captions):
        """score_batch should process multiple items"""
        report = engine.score_batch(temp_image_with_captions)
        assert report.total == 3
        assert len(report.passed_ids) + len(report.failed_ids) == 3

    def test_score_batch_avg_scores(self, engine, temp_image_with_captions):
        """score_batch should compute average scores"""
        report = engine.score_batch(temp_image_with_captions)
        assert "overall_score" in report.avg_scores
        assert "sharpness" in report.avg_scores
        assert "colorfulness" in report.avg_scores

    def test_score_batch_distribution(self, engine, temp_image_with_captions):
        """score_batch should include score distributions"""
        report = engine.score_batch(temp_image_with_captions)
        assert "overall_score" in report.distribution
        assert len(report.distribution["overall_score"]) == 3

    def test_score_batch_threshold(self, engine, temp_image_with_captions):
        """score_batch should use threshold for pass/fail"""
        report = engine.score_batch(temp_image_with_captions, threshold=0.0)
        assert report.passed == 3
        report2 = engine.score_batch(temp_image_with_captions, threshold=1.0)
        assert report2.failed == 3

    @pytest.mark.timeout(5)
    def test_score_image_small_image(self, engine, test_image_small):
        """score_image with very small (2x2) image should not crash"""
        result = engine.score_image(test_image_small)
        assert isinstance(result, QualityScore)
        assert result.width >= 0


# ============================================================================
# PerceptualHasher Tests
# ============================================================================

class TestPerceptualHasher:
    """Tests for PerceptualHasher"""

    def test_phash_returns_string(self, test_image_pil):
        """phash should return a hex-like string"""
        h = PerceptualHasher.phash(test_image_pil)
        assert isinstance(h, str)
        assert len(h) == 64  # 8x8 hash

    def test_phash_consistent(self, test_image_pil):
        """phash should be consistent for same image"""
        h1 = PerceptualHasher.phash(test_image_pil)
        h2 = PerceptualHasher.phash(test_image_pil)
        assert h1 == h2

    def test_phash_different_images(self, test_image_pil, test_image_blank):
        """Different images should have different hashes"""
        h1 = PerceptualHasher.phash(test_image_pil)
        h2 = PerceptualHasher.phash(test_image_blank)
        assert h1 != h2

    def test_phash_from_path(self, temp_image_dir):
        """phash should work with file paths"""
        img_path = os.path.join(temp_image_dir, "test_0.jpg")
        h = PerceptualHasher.phash(img_path)
        assert isinstance(h, str)
        assert len(h) == 64

    def test_hamming_distance_zero(self, test_image_pil):
        """hamming_distance to self should be 0"""
        h = PerceptualHasher.phash(test_image_pil)
        assert PerceptualHasher.hamming_distance(h, h) == 0

    def test_hamming_distance_nonzero(self, test_image_pil, test_image_blank):
        """Different images should have non-zero hamming distance"""
        h1 = PerceptualHasher.phash(test_image_pil)
        h2 = PerceptualHasher.phash(test_image_blank)
        dist = PerceptualHasher.hamming_distance(h1, h2)
        assert dist > 0

    def test_hamming_distance_different_lengths(self, test_image_pil):
        """hamming_distance with different length hashes should return max length"""
        h = PerceptualHasher.phash(test_image_pil)
        dist = PerceptualHasher.hamming_distance(h, "short")
        assert dist == len(h)

    def test_find_duplicates_empty(self):
        """find_duplicates with empty list should return empty"""
        result = PerceptualHasher.find_duplicates([])
        assert result == []

    def test_find_duplicates_same_image(self, test_image_pil):
        """find_duplicates should detect identical images"""
        result = PerceptualHasher.find_duplicates([test_image_pil, test_image_pil])
        assert len(result) >= 1
        i, j, ratio = result[0]
        assert ratio <= 0.2  # Very similar

    def test_find_duplicates_different(self, test_image_pil, test_image_blank):
        """find_duplicates with very strict threshold should return no duplicates"""
        result = PerceptualHasher.find_duplicates([test_image_pil, test_image_blank],
                                                   threshold=0)
        # With threshold=0, only identical hashes match
        assert len(result) == 0

    def test_phash_gray_image(self):
        """phash should work with grayscale images"""
        img = Image.new("L", (64, 64), 128)
        h = PerceptualHasher.phash(img)
        assert isinstance(h, str)
        assert len(h) == 64
