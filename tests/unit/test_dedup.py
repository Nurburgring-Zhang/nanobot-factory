"""Unit tests for DedupEngine: MD5 exact, pHash perceptual, CLIP semantic dedup layers.

Tests the engines/enhanced_engines.py DedupEngine class.
"""
import os
import sys
import hashlib
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-32chars!!")

from engines.enhanced_engines import DedupEngine, DedupLevel, DedupResult


@pytest.fixture
def engine():
    """Create a fresh DedupEngine."""
    return DedupEngine()


@pytest.fixture
def unique_files(tmp_path):
    """Create 5 files with completely different content."""
    paths = []
    for i in range(5):
        p = tmp_path / f"unique_{i}.bin"
        p.write_bytes(f"UNIQUE_FILE_CONTENT_NUMBER_{i}_XYZ_{'Z' * 200}".encode())
        paths.append(str(p))
    return paths


@pytest.fixture
def duplicate_files(tmp_path):
    """Create files with intentional duplicates.

    Returns:
        paths: list of all file paths
        expected_exact_dups: number of exact duplicates (beyond the first of each group)
    """
    paths = []
    # Group 1: 3 identical files
    content_a = b"A" * 500
    for i in range(3):
        p = tmp_path / f"dup_a_{i}.bin"
        p.write_bytes(content_a)
        paths.append(str(p))

    # Group 2: 2 identical files (different from group 1)
    content_b = b"B" * 500
    for i in range(2):
        p = tmp_path / f"dup_b_{i}.bin"
        p.write_bytes(content_b)
        paths.append(str(p))

    # Group 3: 1 unique file
    p = tmp_path / "unique_c.bin"
    p.write_bytes(b"C" * 500)
    paths.append(str(p))

    # expected exact duplicates: (3-1) + (2-1) = 3
    return paths, 3


@pytest.fixture
def named_dup_files(tmp_path):
    """Create 2 identical files with different names."""
    p1 = tmp_path / "image_copy1.png"
    p2 = tmp_path / "image_copy2.png"
    content = b"IDENTICAL_IMAGE_DATA" * 100
    p1.write_bytes(content)
    p2.write_bytes(content)
    return [str(p1), str(p2)]


@pytest.mark.unit
@pytest.mark.dedup
class TestMD5ExactDedup:
    """Tests for Level 1: MD5 exact deduplication."""

    def test_md5_hash_computation(self, engine, tmp_path):
        """MD5 hash should be computed correctly for a file."""
        p = tmp_path / "test.bin"
        p.write_bytes(b"hello world")
        expected = hashlib.md5(b"hello world").hexdigest()
        result = engine._md5_hash(str(p))
        assert result == expected

    def test_md5_same_content_same_hash(self, engine, tmp_path):
        """Two files with identical content should have same MD5 hash."""
        p1 = tmp_path / "a.bin"
        p2 = tmp_path / "b.bin"
        p1.write_bytes(b"same content")
        p2.write_bytes(b"same content")
        assert engine._md5_hash(str(p1)) == engine._md5_hash(str(p2))

    def test_md5_different_content_different_hash(self, engine, tmp_path):
        """Two files with different content should have different MD5 hashes."""
        p1 = tmp_path / "a.bin"
        p2 = tmp_path / "b.bin"
        p1.write_bytes(b"content one")
        p2.write_bytes(b"content two")
        assert engine._md5_hash(str(p1)) != engine._md5_hash(str(p2))

    def test_exact_dedup_finds_duplicates(self, engine, duplicate_files):
        """Exact dedup should find byte-identical files."""
        paths, expected_exact = duplicate_files
        result = engine.deduplicate(paths, DedupLevel.EXACT)
        assert result.total == len(paths)
        assert result.exact_dups == expected_exact
        assert result.unique < result.total

    def test_exact_dedup_no_false_positives(self, engine, unique_files):
        """Unique files should produce no exact duplicates."""
        result = engine.deduplicate(unique_files, DedupLevel.EXACT)
        assert result.exact_dups == 0
        assert result.unique == len(unique_files)

    def test_exact_dedup_identical_named_files(self, engine, named_dup_files):
        """Files with different names but identical content are duplicates."""
        result = engine.deduplicate(named_dup_files, DedupLevel.EXACT)
        assert result.exact_dups == 1
        assert result.unique == 1

    def test_exact_dedup_empty_list(self, engine):
        """Empty file list should produce zero results."""
        result = engine.deduplicate([], DedupLevel.EXACT)
        assert result.total == 0
        assert result.unique == 0


@pytest.mark.unit
@pytest.mark.dedup
class TestPerceptualDedup:
    """Tests for Level 2: pHash perceptual deduplication."""

    def test_phash_returns_string_or_empty(self, engine, sample_image_paths):
        """pHash should return a string hash or empty string on failure."""
        for p in sample_image_paths:
            ph = engine._phash(p)
            assert isinstance(ph, str)

    def test_ssim_hash_returns_tuple_or_empty(self, engine, sample_image_paths):
        """SSIM hash should return a tuple or empty tuple."""
        for p in sample_image_paths:
            sh = engine._ssim_hash(p)
            assert isinstance(sh, tuple)

    def test_perceptual_dedup_unique_files(self, engine, unique_files):
        """Unique files should have few perceptual duplicates."""
        result = engine.deduplicate(unique_files, DedupLevel.PERCEPTUAL)
        # Unique files should mostly remain unique
        assert result.unique >= len(unique_files) - 1

    def test_perceptual_dedup_with_exact_dups(self, engine, duplicate_files):
        """Perceptual dedup should find exact duplicates and potentially more."""
        paths, _ = duplicate_files
        result = engine.deduplicate(paths, DedupLevel.PERCEPTUAL)
        # At minimum, exact duplicates should be found
        assert result.exact_dups >= 2  # Group A:3 has 2 dup, Group B:2 has 1 dup
        assert result.unique <= result.total


@pytest.mark.unit
@pytest.mark.dedup
class TestSemanticDedup:
    """Tests for Level 3: CLIP embedding semantic deduplication."""

    def test_clip_embedding_returns_list(self, engine, sample_image_paths):
        """CLIP embedding should return a list of floats (or fallback)."""
        for p in sample_image_paths:
            emb = engine._clip_embedding(p)
            assert isinstance(emb, list)
            assert len(emb) > 0

    def test_semantic_dedup_unique_files(self, engine, unique_files):
        """Semantic dedup on unique files should keep most unique."""
        result = engine.deduplicate(unique_files, DedupLevel.SEMANTIC)
        assert result.total == len(unique_files)
        assert 1 <= result.unique <= result.total


@pytest.mark.unit
@pytest.mark.dedup
class TestDedupLevelProgression:
    """Tests verifying that higher levels find >= duplicates of lower levels."""

    def test_level_progression(self, engine, duplicate_files):
        """Exact ⊂ Perceptual ⊂ Semantic in terms of duplicates found."""
        paths, _ = duplicate_files

        exact_result = engine.deduplicate(paths, DedupLevel.EXACT)
        perc_result = engine.deduplicate(paths, DedupLevel.PERCEPTUAL)
        sem_result = engine.deduplicate(paths, DedupLevel.SEMANTIC)

        # Exact duplicates ≤ total removed at perceptual (perceptual finds exact + more)
        assert exact_result.exact_dups <= perc_result.exact_dups
        # Unique count decreases or stays same as we go deeper
        assert sem_result.unique <= perc_result.unique


@pytest.mark.unit
@pytest.mark.dedup
class TestCleaningQualityReport:
    """Tests for the cleaning_quality_report method."""

    def test_report_structure(self, engine, unique_files):
        """Report should have all required fields."""
        report = engine.cleaning_quality_report(unique_files, DedupLevel.EXACT)
        assert "before_cleaning" in report
        assert "after_cleaning" in report
        assert "removed_count" in report
        assert "cleaning_rate" in report
        assert "layer_breakdown" in report
        assert "industry_benchmark" in report

    def test_report_with_duplicates(self, engine, duplicate_files):
        """Report on duplicate files should show positive cleaning rate."""
        paths, _ = duplicate_files
        report = engine.cleaning_quality_report(paths, DedupLevel.EXACT)
        assert report["before_cleaning"] == len(paths)
        assert report["after_cleaning"] < report["before_cleaning"]
        assert report["removed_count"] > 0
        assert report["cleaning_rate"] > 0

    def test_report_empty_list(self, engine):
        """Report on empty list should handle gracefully."""
        report = engine.cleaning_quality_report([], DedupLevel.EXACT)
        assert report["before_cleaning"] == 0
        assert report["after_cleaning"] == 0


@pytest.mark.unit
@pytest.mark.dedup
class TestGoldenValidation:
    """Tests for validate_with_golden method."""

    def test_golden_validation_structure(self, engine, named_dup_files):
        """Golden validation should return metrics structure."""
        golden_pairs = [
            (named_dup_files[0], named_dup_files[1], True),  # should be dup
        ]
        result = engine.validate_with_golden(named_dup_files, golden_pairs)
        assert "true_positives" in result or "tp" in str(result)
        assert "false_positives" in result or "fp" in str(result)

    def test_golden_empty(self, engine):
        """Empty golden pairs should return valid but minimal result."""
        result = engine.validate_with_golden([], [])
        assert isinstance(result, dict)

    def test_dedup_result_dataclass(self):
        """DedupResult should be instantiable with defaults."""
        result = DedupResult(total=10, unique=8, exact_dups=1, perceptual_dups=1)
        assert result.total == 10
        assert result.unique == 8
        assert result.semantic_dups == 0
