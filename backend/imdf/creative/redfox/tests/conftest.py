"""RedFox 测试 conftest — 把 backend/ 加入 sys.path.

注意: backend/imdf/tests/conftest.py 故意把 backend/ 从 sys.path 移除,
以防止 backend/api 影子 imdf/api。我们的 RedFox 测试用绝对路径
'from backend.imdf.creative.redfox import ...', 因此这里反着做 —
把 BACKEND (nanobot-factory/backend/) 加到 sys.path[0]。

parent imdf/tests/conftest.py 在 module load 时清掉了 backend。
我们用 pytest_configure (test session 启动时) 重新加 — 比 parent 晚。
"""
import sys
from pathlib import Path


def pytest_configure(config):
    """在 parent conftest 之后重新把 backend 加到 sys.path."""
    BACKEND = Path(__file__).resolve().parents[4]
    sp = str(BACKEND.resolve())
    # 移除已存在的 backend 条目,确保插到最前
    sys.path[:] = [p for p in sys.path if Path(p).resolve() != BACKEND.resolve()]
    sys.path.insert(0, sp)