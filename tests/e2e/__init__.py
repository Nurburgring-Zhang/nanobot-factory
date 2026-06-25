"""E2E 套件入口 — pytest-playwright 集成。

只做一件事: 收集 tests/e2e/ 下所有 test_*.py + 把 __init__.py 当 package。

运行命令:
    # 需要先 `playwright install chromium` (本仓库已预装, 见 artifacts/uvicorn.log 同目录)
    pytest tests/e2e/ -v --browser chromium
    pytest tests/e2e/ -v --browser chromium --headed   # 浏览器可视化
"""
import os

import pytest

# 在 pytest collection 时强设置 test 模式 + JWT_SECRET, 防止 canvas_web.py 启动时 import 阶段报错
os.environ.setdefault("JWT_SECRET", "e2e-playwright-jwt-secret-32chars-pad!!")
os.environ.setdefault("IMDF_TEST_MODE", "1")