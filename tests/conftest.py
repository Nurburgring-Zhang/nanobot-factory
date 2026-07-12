"""pytest conftest for tests/ root directory.

Global fixtures and sys.path configuration.

P12-B3: 通用测试隔离
- ``sys.path`` 注入: 让 root-level test 可单独 import ``backend.*`` / ``core.*``
  模块, 不依赖 cwd 必须是 backend/。
- ``mock_env`` fixture: 自动注入测试 ENV, 避免重复 ``os.environ.setdefault``
  散落在每个 test 文件头部。
- ``isolated_sys_path`` fixture: 临时隔离 sys.path, 防止 test 之间 sys.path
  污染 (imdf shadowing 之类)。
- 兼容 P11-D-3 (backend/tests/conftest.py) 与 P11-B (auth fixtures) 的既有
  行为; 此文件只做"补全", 不与 backend/tests/conftest.py 重复。
"""
import os
import sys
import pytest
from pathlib import Path

# ==== 路径注入 (P12-B3 §1) =================================================
# 1) backend/ 排第一: 让 ``from core.canvas_core import ...`` / ``from
#    server import X`` / ``from auth import X`` 在 root test 下也能解析
# 2) imdf/api, imdf/engines, imdf/common 单独加入, 让 ``from api import X``
#    也能解析 (P1 测试需要)
# 3) imdf/ 整体不加 (避免 imdf.core shadow backend.core)
_PROJECT_ROOT = Path(__file__).parent.resolve()
_BACKEND_DIR = _PROJECT_ROOT / "backend"
_IMDF_DIR = _BACKEND_DIR / "imdf"

# 1) backend/ 排第一
_backend_path = str(_BACKEND_DIR)
if _backend_path in sys.path:
    sys.path.remove(_backend_path)
sys.path.insert(0, _backend_path)

# 2) imdf 子包单独加入 (api/engines/common, 顺序: 通用 → 专用)
for sub in ("common", "engines", "api"):
    p = _IMDF_DIR / sub
    if p.exists() and (p / "__init__.py").exists():
        sp = str(p)
        if sp in sys.path:
            sys.path.remove(sp)
        sys.path.insert(0, sp)

# ==== 默认测试 ENV (P12-B3 §1, 防止 import-time 失败) =====================
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("CSRF_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "true")
os.environ.setdefault("JWT_SECRET", "x" * 64)  # 防止 auth 链 ValueError


# ==== 路径维护 hook (防止 test 文件自身 sys.path.insert 污染) =============
def pytest_collectstart(collector):
    """Pytest 收集每个 test 模块前调用, 校正 sys.path。

    与 backend/tests/conftest.py 中的同名 hook 协同: 此 hook 只在 ``tests/``
    根下生效, 负责把 imdf/ 从 sys.path 移除, 防止 ``from core import x`` 错误
    解析到 imdf/core/。imdf/api, imdf/engines, imdf/common 子包保留在最前。
    """
    imdf_root = str(_IMDF_DIR)
    while imdf_root in sys.path:
        sys.path.remove(imdf_root)
    # imdf 子包单独保留在最前 (倒序插入 → api 在最前)
    for sub in ("common", "engines", "api"):
        sp = str(_IMDF_DIR / sub)
        if sp not in sys.path:
            sys.path.insert(0, sp)
        else:
            sys.path.remove(sp)
            sys.path.insert(0, sp)
    # backend/ 在 imdf/* 之后
    if str(_BACKEND_DIR) in sys.path:
        sys.path.remove(str(_BACKEND_DIR))
    sys.path.insert(len([p for p in sys.path[:5] if "imdf" in p]), str(_BACKEND_DIR))


# ==== 通用 fixtures (P12-B3 §1) ===========================================

@pytest.fixture
def mock_env(monkeypatch):
    """P12-B3: 自动注入测试 ENV, 每个 test 拿到干净的 ENV 副本。

    使用方式::

        def test_foo(mock_env):
            assert os.environ["IMDF_TEST_MODE"] == "1"

    默认注入::
        - IMDF_TEST_MODE=1
        - CSRF_ENABLED=false
        - RATE_LIMIT_ENABLED=true
        - JWT_SECRET=<64 字符强 secret>
        - ADMIN_INITIAL_PASSWORD=<随机会话级>
        - API_KEY_MASTER_KEY=<32 字节 hex>

    Returns:
        dict: 注入的 ENV 副本, 便于 test 断言。
    """
    import secrets
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


@pytest.fixture
def isolated_sys_path():
    """P12-B3: 临时隔离 sys.path, 防止 test 之间 sys.path 污染。

    适用场景: test 需要临时改 sys.path 来测 import 行为, 又不能影响后续 test。
    用法::

        def test_foo(isolated_sys_path):
            sys.path.insert(0, "/some/path")
            # sys.path 在 test 结束后自动还原
    """
    original = list(sys.path)
    try:
        yield sys.path
    finally:
        sys.path[:] = original


@pytest.fixture
def test_data_dir(tmp_path):
    """创建临时测试数据目录 (兼容既有)."""
    return tmp_path


@pytest.fixture
def sample_annotations():
    """Fleiss Kappa 测试用的标注矩阵 (兼容既有)."""
    return [
        [1, 2, 2],
        [2, 2, 1],
        [3, 1, 3],
        [2, 1, 2],
    ]


@pytest.fixture
def sample_texts():
    """去重测试用的文本列表 (兼容既有)."""
    return [
        "这是一段测试文本",
        "这是另一段测试文本",
        "这是一段测试文本",  # 重复
        "完全不同的文本内容",
    ]


# ==== backend module 隔离导入 helpers (P12-B3 §2) =========================
# test_memory.py 的 ``from server import RateLimiter`` 触发 server.py 顶层
# 大量 import, 与 imdf 命名空间冲突。我们用 AST 提取 + 独立 exec 的方式,
# 加载只需要的类, 避免副作用。

@pytest.fixture
def rate_limiter_cls():
    """P12-B3: 独立加载 ``RateLimiter`` 类, 不触发 server.py 顶层 import。

    server.py 顶层 ``from task_queue import ...`` 在 imdf 命名空间下会冲突
    (imdf/engines/task_queue.py 没有 ``TaskExecutor``)。RateLimiter 类本身只
    用 stdlib (defaultdict, List, Dict, threading.Lock, time), 用 AST 切片 +
    独立 namespace exec 即可干净加载。
    """
    import ast
    import threading
    import time
    from collections import defaultdict
    from typing import Dict, List

    server_path = _BACKEND_DIR / "server.py"
    source = server_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    klass = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RateLimiter"),
        None,
    )
    if klass is None:
        pytest.skip("RateLimiter class not found in server.py")

    # 提取 class 节点源码 (含 decorator)
    lines = source.splitlines(keepends=True)
    class_src = "".join(lines[klass.lineno - 1: klass.end_lineno])
    # 用 ast.unparse 更安全, 但 python 3.9+ 可用
    try:
        class_src = ast.unparse(klass)
    except Exception:
        pass

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
