"""Shared fixtures and configuration for all IMDF tests."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is in sys.path for imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ── Environment helpers ──────────────────────────────────────────────────

@pytest.fixture(scope="session")
def project_root():
    """Absolute path to IMDF project root."""
    return _PROJECT_ROOT


@pytest.fixture(scope="session")
def temp_db_dir():
    """Create a temporary directory for SQLite databases used in tests."""
    with tempfile.TemporaryDirectory(prefix="imdf_test_") as tmp:
        yield tmp


@pytest.fixture(autouse=True)
def isolate_imdf_db(monkeypatch, tmp_path):
    """Redirect IMDF data paths to temporary directories per test.

    Ensures tests never touch the real production databases.
    """
    # Point data and logs to temp
    monkeypatch.setenv("IMDF_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IMDF_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("IMDF_DEBUG", "true")

    # Pre-create directories
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)


@pytest.fixture
def sample_user_data():
    """Return valid user registration data."""
    return {
        "username": "testuser1",
        "password": "StrongPass1",
        "role": "viewer",
    }


@pytest.fixture
def sample_weak_passwords():
    """Collection of weak passwords that should fail validation."""
    return [
        "short",
        "nouppercase1",
        "NOLOWERCASE1",
        "NoDigitsNeeded",
        "123456",
        "password",
        "qwerty",
        "admin",
        "test123",
    ]


@pytest.fixture
def sample_strong_passwords():
    """Collection of strong passwords that should pass validation."""
    return [
        "MyStr0ngP@ss!",
        "XyZ_2024_Secure",
        "Th1sIsAVeryL0ngP@ssw0rd",
        "CorrectHorseBatteryStaple1",
        "B3nchmark-T3st!ng",
    ]


@pytest.fixture
def sample_image_paths(tmp_path):
    """Create dummy image files for dedup / classification tests."""
    paths = []
    for i in range(5):
        p = tmp_path / f"test_image_{i}.png"
        # Write unique content
        p.write_bytes(f"IMAGE_CONTENT_{i}_{'A' * 100}".encode())
        paths.append(str(p))
    return paths


@pytest.fixture
def sample_classification_items():
    """Sample data items for classification engine tests."""
    return [
        {
            "id": "img001",
            "tags": "人物, 户外",
            "resolution": "1920",
            "aspect_ratio": "16:9",
            "quality_score": "90",
            "format": "image.png",
        },
        {
            "id": "img002",
            "tags": "场景, 室内",
            "resolution": "640",
            "aspect_ratio": "4:3",
            "quality_score": "35",
            "format": "image.jpg",
        },
        {
            "id": "img003",
            "tags": "Logo, Brand, 文字",
            "resolution": "2560",
            "aspect_ratio": "16:9",
            "quality_score": "95",
            "format": "image.webp",
        },
        {
            "id": "vid001",
            "tags": "场景, 户外, 人物",
            "resolution": "3840",
            "aspect_ratio": "21:9",
            "quality_score": "88",
            "format": "video.mp4",
        },
        {
            "id": "doc001",
            "tags": "文字, 说明书",
            "resolution": "0",
            "aspect_ratio": "",
            "quality_score": "50",
            "format": "document.pdf",
        },
    ]


@pytest.fixture
def sample_annotations():
    """Sample annotation data for IAA tests."""
    return [
        {"id": "item1", "label": "cat", "confidence": 0.95},
        {"id": "item2", "label": "dog", "confidence": 0.88},
        {"id": "item3", "label": "cat", "confidence": 0.91},
        {"id": "item4", "label": "bird", "confidence": 0.72},
        {"id": "item5", "label": "cat", "confidence": 0.97},
        {"id": "item6", "label": "dog", "confidence": 0.84},
        {"id": "item7", "label": "bird", "confidence": 0.65},
        {"id": "item8", "label": "cat", "confidence": 0.93},
        {"id": "item9", "label": "dog", "confidence": 0.79},
        {"id": "item10", "label": "cat", "confidence": 0.99},
    ]
