"""
Pytest configuration for NanoBot Factory backend tests
Shared fixtures for all test modules

P11-D-3: 通用测试隔离
- 自动把 ``backend/`` 和 ``backend/imdf/`` 加入 sys.path, 让 ``from api.xxx`` /
  ``from engines.xxx`` / ``from common.xxx`` 等 import 在所有 test 下都能解析
- 默认 test env (IMDF_TEST_MODE=1, CSRF_ENABLED=false, RATE_LIMIT_ENABLED=true)
- 隔离临时 ``auth.db`` / master key 注入, 避免污染生产配置
"""
import os
import sys
import io
import uuid
import tempfile
import shutil
import secrets
from pathlib import Path
from typing import Dict, Any, List, Optional

import pytest
import numpy as np
from PIL import Image

# ── P11-D-3: 路径注入 — 避免 imdf/ 顶层 shadow backend/ 的 core/ 等 ────
# imdf/ 暴露 ``api/``/``engines/``/``common/`` 顶层包, 跟 backend/ 的同名空目录
# 或其它模块同名冲突。简单地把 imdf/ 放 sys.path 前面会让 ``from core import x``
# 错误地解析到 imdf/core/ (不同于 backend/core/)。所以策略是:
# 1) backend/ 在 sys.path 前 (覆盖 core/ common/ 等 backend 模块)
# 2) imdf/api/ 和 imdf/engines/ 也加进去 (P1 测试需要 from api import X)
# 3) imdf/common/ 已被 backend/common/ 覆盖 (FieldEncryption 必须在 backend/common)
# 4) imdf/ 整体不加入 sys.path (避免 imdf.core shadow backend.core)
_backend_dir = Path(__file__).parent.parent.resolve()
_imdf_dir = _backend_dir / "imdf"

# 1) backend/ 排第一
if str(_backend_dir) in sys.path:
    sys.path.remove(str(_backend_dir))
sys.path.insert(0, str(_backend_dir))

# 2) imdf/api/ 和 imdf/engines/ 单独加入, 让 P1 测试能 ``from api import X``
for sub in ("api", "engines", "common"):
    p = _imdf_dir / sub
    if p.exists() and (p / "__init__.py").exists():
        sp = str(p)
        if sp in sys.path:
            sys.path.remove(sp)
        sys.path.insert(0, sp)

# ── P11-D-3: 默认 test env (在 import 任何 auth 模块前设置) ──────────────
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("CSRF_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "true")
# 防止测试 import 时无 ADMIN_INITIAL_PASSWORD 触发 fail-fast
os.environ.setdefault("ADMIN_INITIAL_PASSWORD", "test-fixture-" + secrets.token_urlsafe(8))
# API key manager 加密 master key (测试模式允许 ephemeral, 但显式给一个稳定 key 更可靠)
os.environ.setdefault("API_KEY_MASTER_KEY", secrets.token_hex(32))


# ── P11-D-3: 防止某些 test 文件的 sys.path.insert(0, imdf) shadow backend/core
# 在每个 test 模块收集前重新校准 sys.path (覆盖它们自己加的 imdf/ 项)
def pytest_collectstart(collector):
    """Pytest 收集每个 test 模块前调用 — 把 imdf/ 从 sys.path 移走, 避免 shadow
    backend/core 等同名包。imdf/api/, imdf/engines/, imdf/common/ 单独保留
    在最前 (供 P1 测试 import 用)。
    """
    # 把 imdf/ (不是 imdf/api 等子目录) 从 sys.path 移除
    imdf_root = str(_backend_dir / "imdf")
    while imdf_root in sys.path:
        sys.path.remove(imdf_root)
    # 确保 imdf/api, imdf/engines, imdf/common 在最前
    for sub in ("common", "engines", "api"):  # reverse order to get api on top
        sp = str(_imdf_dir / sub)
        if sp not in sys.path:
            sys.path.insert(0, sp)
        else:
            # 把它移到最前
            sys.path.remove(sp)
            sys.path.insert(0, sp)
    # backend/ 在 imdf/* 之后
    if str(_backend_dir) in sys.path:
        sys.path.remove(str(_backend_dir))
    sys.path.insert(len([p for p in sys.path[:5] if "imdf" in p]), str(_backend_dir))


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


# ============================================================================
# P11-B: Auth / JWT fixtures (test isolation)
# ============================================================================

@pytest.fixture(autouse=True)
def _strong_jwt_secret(monkeypatch):
    """P11-B: autouse — 让每个 test 默认都有 >= 16 字符的 JWT_SECRET。

    这样 ``common.auth._secret()`` 不会因为 env 里没有 / 弱 secret 而抛
    ValueError, 保护调用链。需要测 _secret() 自身的边界 (短 secret raise)
    的 test, 在自己的 test body 里用 ``monkeypatch.setenv("JWT_SECRET", "x")``
    覆盖即可。
    """
    monkeypatch.setenv("JWT_SECRET", "x" * 64)
    yield


@pytest.fixture
def strong_jwt_secret() -> str:
    """P11-B: 返回一个 >= 16 字符的 secret (给显式构造 ``JWTManager(...)`` 用)."""
    return "test_jwt_secret_32chars_long_aaaa"


@pytest.fixture
def jwt_manager_strong(strong_jwt_secret):
    """P11-B: 直接构造 unified_auth.JWTManager, secret >= 16 字符."""
    from auth.unified_auth import JWTManager as UnifiedJWTManager
    return UnifiedJWTManager(secret_key=strong_jwt_secret)


@pytest.fixture
def legacy_jwt_manager_strong(strong_jwt_secret):
    """P11-B: 直接构造 security.auth.JWTManager, secret >= 16 字符."""
    from security.auth import JWTManager as LegacyJWTManager
    return LegacyJWTManager(secret_key=strong_jwt_secret)


# ============================================================================
# P12-B3: server.RateLimiter 隔离加载
# ============================================================================
# test_memory.py 的 ``from server import RateLimiter`` 触发 server.py 顶层
# ``from task_queue import TaskExecutor`` 等, 在 imdf 命名空间下会冲突
# (imdf/engines/task_queue.py 没有 ``TaskExecutor``)。RateLimiter 类本身只
# 用 stdlib (defaultdict, List, Dict, threading.Lock, time), 用 AST 切片 +
# 独立 namespace exec 即可干净加载, 不触发 server.py 的副作用 import。

@pytest.fixture
def rate_limiter_cls():
    """P12-B3: 独立加载 ``RateLimiter`` 类, 不触发 server.py 顶层 import。

    用法::

        def test_rate_limit(rate_limiter_cls):
            limiter = rate_limiter_cls(requests=60, window=60)
            assert limiter.is_allowed("client-1") is True

    Returns:
        type: ``RateLimiter`` 类, 可直接实例化。
    """
    import ast
    import threading
    import time
    from collections import defaultdict
    from typing import Dict, List

    server_path = _backend_dir / "server.py"
    if not server_path.exists():
        pytest.skip(f"server.py not found at {server_path}")

    source = server_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    klass = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RateLimiter"),
        None,
    )
    if klass is None:
        pytest.skip("RateLimiter class not found in server.py")

    # 用 ast.unparse 提取类源码 (python 3.9+, 安全)
    try:
        class_src = ast.unparse(klass)
    except Exception:
        # 退化: 切片源码
        lines = source.splitlines(keepends=True)
        class_src = "".join(lines[klass.lineno - 1: klass.end_lineno])

    namespace = {
        "defaultdict": defaultdict,
        "Dict": Dict,
        "List": List,
        "threading": threading,
        "time": time,
        "__builtins__": __builtins__,
    }
    exec(class_src, namespace)
    return namespace["RateLimiter"]


@pytest.fixture
def mock_env(monkeypatch):
    """P12-B3: 自动注入测试 ENV, 每个 test 拿到干净的 ENV 副本。

    用法::

        def test_foo(mock_env):
            assert os.environ["IMDF_TEST_MODE"] == "1"

    默认注入:
        - IMDF_TEST_MODE=1
        - CSRF_ENABLED=false
        - RATE_LIMIT_ENABLED=true
        - JWT_SECRET=<64 字符强 secret>
        - ADMIN_INITIAL_PASSWORD=<随机会话级>
        - API_KEY_MASTER_KEY=<32 字节 hex>

    Returns:
        dict: 注入的 ENV 副本, 便于 test 断言。
    """
    env = {
        "IMDF_TEST_MODE": "1",
        "CSRF_ENABLED": "false",
        "RATE_LIMIT_ENABLED": "true",
        "JWT_SECRET": "x" * 64,
        "ADMIN_INITIAL_PASSWORD": "test-fixture-" + secrets.token_urlsafe(8),
        "API_KEY_MASTER_KEY": secrets.token_hex(32),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return dict(env)
