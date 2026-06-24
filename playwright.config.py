"""Playwright E2E test config — nanobot-factory.

启动本地 chromium 浏览器; 测试启动 uvicorn 子进程作为后端 (conftest.py)。

为什么用 pytest-playwright 而非纯 playwright:
  1. 复用项目已有的 pytest runner + 测试目录结构。
  2. 自动注入 `page` fixture, 每个用例拿到独立 browser context。
  3. 与已有 tests/e2e/test_full_workflow.py (TestClient 风格) 形成
     互补: 那是 API 层的端到端, 这是浏览器层的端到端。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ── pytest 配置 ────────────────────────────────────────────────────────────
# 测试目录统一放在 tests/e2e/, 复用 tests/ 的 conftest.py (JWT_SECRET + sys.path)。
# pytest-playwright 默认从 pytest.ini / pyproject.toml / playwright.config.py 读取
# 这些配置, 把 tests_dir 指过去即可让它找到 tests/e2e/test_*.py。

# Playwright 用 chromium (Windows 默认 headless 通道)。
# 浏览器二进制从 C:\Users\<u>\AppData\Local\ms-playwright\chromium-1155\ 读取,
# 由 `playwright install chromium` 预装 (本仓库已预装)。
HEADLESS = True
SLOW_MO_MS = 0  # 调试时改为 200 看动画

# ── HTML 报告输出 ──────────────────────────────────────────────────────────
REPORT_DIR = ROOT / "artifacts" / "test-results"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def pytest_configure(config):
    """session 级钩子: 把 artifacts/test-results 加入 sys.path 方便调试报告。"""
    # 标记自定义 marker — 避免 pytest "unknown marker" 警告
    config.addinivalue_line("markers", "e2e_playwright: Playwright 浏览器层 E2E 测试")


# ── 提示给 pytest-playwright ──────────────────────────────────────────────
# 注意: 这里不覆盖 browser 启动参数; 全部走 pytest-playwright 默认的 chromium headless。
# 如需浏览器可视化调试:  `pytest tests/e2e/ --headed --browser chromium --slowmo 200`