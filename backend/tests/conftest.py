"""
Pytest configuration for NanoBot Factory backend tests
Shared fixtures for all test modules
"""
import os
import sys
import io
import uuid
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

import pytest
import numpy as np
from PIL import Image

# Add backend directory to sys.path
_backend_dir = Path(__file__).parent.parent.resolve()
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_session_id():
    """Fixture for test session ID"""
    return "test_session_001"


@pytest.fixture
def test_user_id():
    """Fixture for test user ID"""
    return "test_user_001"


@pytest.fixture
def mock_message():
    """Fixture for mock message"""
    return {
        "content": "Test message content",
        "role": "user",
        "session_id": "test_session_001"
    }


# ============================================================================
# Shared fixtures for data module tests
# ============================================================================

@pytest.fixture
def test_image_bytes() -> bytes:
    """Generate a small PNG test image in RGB format as bytes"""
    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    # Add some variation
    pixels = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    img = Image.fromarray(pixels, "RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def test_image_pil() -> Image.Image:
    """Generate a PIL Image test fixture with pattern content"""
    arr = np.zeros((200, 200, 3), dtype=np.uint8)
    # Create a gradient pattern
    for y in range(200):
        for x in range(200):
            arr[y, x] = [x, y, (x + y) // 2]
    return Image.fromarray(arr, "RGB")


@pytest.fixture
def test_image_solid() -> Image.Image:
    """Generate a solid-color PIL Image for brightness/contrast tests"""
    arr = np.full((100, 100, 3), 128, dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


@pytest.fixture
def test_image_sharp() -> Image.Image:
    """Generate a high-contrast sharp image for sharpness tests"""
    arr = np.zeros((100, 100, 3), dtype=np.uint8)
    # Checkerboard pattern
    for y in range(100):
        for x in range(100):
            if (x // 10 + y // 10) % 2 == 0:
                arr[y, x] = [255, 255, 255]
    return Image.fromarray(arr, "RGB")


@pytest.fixture
def test_image_blank() -> Image.Image:
    """Generate a completely blank (black) image"""
    return Image.new("RGB", (64, 64), (0, 0, 0))


@pytest.fixture
def test_image_small() -> Image.Image:
    """Generate a very small image for edge case testing"""
    return Image.new("RGB", (2, 2), (255, 0, 0))


@pytest.fixture
def temp_dir() -> str:
    """Create a temporary directory for test outputs"""
    d = tempfile.mkdtemp(prefix="nanobot_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_image_dir(temp_dir: str) -> str:
    """Create a temporary directory with test images"""
    img_dir = os.path.join(temp_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    for i in range(5):
        arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
        img = Image.fromarray(arr, "RGB")
        img.save(os.path.join(img_dir, f"test_{i}.jpg"), quality=85)
        # Also save a PNG for format variety
        img.save(os.path.join(img_dir, f"test_{i}.png"))

    return img_dir


@pytest.fixture
def temp_image_with_captions(temp_dir: str) -> List[Dict[str, Any]]:
    """Create test images with captions for batch testing"""
    items = []
    for i in range(3):
        arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
        img = Image.fromarray(arr, "RGB")
        path = os.path.join(temp_dir, f"batch_{i}.jpg")
        img.save(path, quality=85)
        items.append({
            "id": f"img_{i}",
            "image": path,
            "caption": f"A test image number {i}"
        })
    return items


@pytest.fixture
def test_client():
    """Create a FastAPI TestClient"""
    try:
        from fastapi.testclient import TestClient
        # Import server module which creates the app
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "server",
            os.path.join(_backend_dir, "server.py")
        )
        server_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server_mod)
        app = getattr(server_mod, 'app', None)
        if app:
            return TestClient(app)
    except Exception as e:
        pytest.skip(f"FastAPI server not available: {e}")

    # If server can't be imported, create a minimal test app
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        return TestClient(app)
    except Exception as e:
        pytest.skip(f"Cannot create TestClient: {e}")
