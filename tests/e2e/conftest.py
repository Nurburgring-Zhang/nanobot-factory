"""E2E conftest — 启动 uvicorn 后端 + 注入 base_url / api_client fixtures。

每个 pytest session:
  1. spawn uvicorn 子进程 (canvas_web.py, 端口 18900)
  2. 等待 /api/queue/health 返回 200 (canvas_web.py 自带 health 端点)
  3. yield base_url 给所有 e2e 测试
  4. teardown: 杀子进程

为什么用 live uvicorn 而非 FastAPI TestClient:
  - Playwright 需要真实 HTTP endpoint + cookie + CORS, TestClient 路径无浏览器语义。
  - canvas_web.py 启动 8-15s, session-scope 启动一次摊销到 5 个测试, 单测 <2s。
  - 端口 18900 高位避开 8000 (冲突多) 与 8900 (wslrelay 占)。

为什么不用 page.goto("/#dashboard") 的 SPA 渲染做主流程:
  - canvas_web.py 的前端是 hash-router 纯前端, 但 #dashboard 实际由 JS fetch /api/stats/overview 注入数据。
  - 我们用 `page.on("response")` 监听后端响应 + `page.locator(...)` 验证 DOM, 比硬编码 JS
    状态机更稳健 — JS 重构不会破坏 e2e 断言。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

# ── 全局路径 (与 tests/conftest.py 风格一致) ───────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BACKEND_IMDF = _PROJECT_ROOT / "backend" / "imdf"
if str(_BACKEND_IMDF) not in sys.path:
    sys.path.insert(0, str(_BACKEND_IMDF))

# ── 强制 test mode + JWT_SECRET (必须先于 canvas_web import) ────────────────
os.environ.setdefault("JWT_SECRET", "e2e-playwright-jwt-secret-32chars-pad!!")
os.environ.setdefault("IMDF_TEST_MODE", "1")

E2E_PORT = int(os.environ.get("E2E_PORT", "18900"))
E2E_BASE_URL = f"http://127.0.0.1:{E2E_PORT}"
# 把 e2e 端口加入 CSRF/CORS 白名单, 否则浏览器层 fetch 会触发 csrf_origin_untrusted
os.environ["CSRF_TRUSTED_ORIGINS"] = (
    f"http://127.0.0.1:{E2E_PORT},http://localhost:{E2E_PORT},"
    f"http://127.0.0.1:3000,http://127.0.0.1:5173,http://127.0.0.1:8765"
)


def _is_port_listening(port: int, timeout: float = 0.5) -> bool:
    """非阻塞探测端口 LISTEN, 比 socket.connect 慢响应更可靠。"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def _wait_for_http(url: str, timeout: float = 30.0) -> None:
    """轮询 GET 直到 2xx/4xx/5xx 任一响应 (404 也算后端活了)。"""
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=1.0)
            if r.status_code < 600:
                return
        except requests.RequestException as e:
            last_err = e
        time.sleep(0.3)
    raise RuntimeError(f"uvicorn @ {url} not ready in {timeout}s: {last_err}")


# ── session-scope: live uvicorn 后端 ────────────────────────────────────────
@pytest.fixture(scope="session")
def live_server():
    """session-scope 启动 uvicorn, 返回 base_url; 测试结束 kill 子进程。"""
    if _is_port_listening(E2E_PORT):
        # 已被占用 (上一个 session 残留), 复用即可
        yield E2E_BASE_URL
        return

    env = os.environ.copy()
    env["PYTHONPATH"] = str(_BACKEND_IMDF) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "api.canvas_web:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(E2E_PORT),
        "--log-level",
        "warning",
        "--no-access-log",
    ]
    log_file = _PROJECT_ROOT / "artifacts" / "test-results" / "uvicorn.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(log_file, "wb")

    # CREATE_NEW_PROCESS_GROUP 让 kill 能干净终止子进程
    proc = subprocess.Popen(
        cmd,
        cwd=str(_BACKEND_IMDF),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )

    try:
        _wait_for_http(f"{E2E_BASE_URL}/api/queue/health", timeout=45.0)
        yield E2E_BASE_URL
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        except Exception:
            pass
        log_handle.close()


# ── function-scope: 干净的 requests.Session (无 cookie 污染) ───────────────
@pytest.fixture
def api_client(live_server):
    """requests.Session 实例, base_url 已绑定。"""
    sess = requests.Session()
    sess.headers.update({"User-Agent": "nanobot-e2e/1.0"})
    sess.base_url = live_server  # type: ignore[attr-defined]
    yield sess
    sess.close()


# ── 公共工具: 注册 + 登录拿 token ──────────────────────────────────────────
@pytest.fixture
def make_user(api_client):
    """工厂 fixture: 创建唯一用户名 + 返回 (username, password, role, token)。

    复用 5 个测试之间避免用户冲突 (注册有 10/min 限流)。
    """
    created: list[dict] = []

    def _factory(role: str = "annotator", prefix: str = "e2e_user") -> dict:
        nonce = str(int(time.time() * 1000))[-9:]
        uname = f"{prefix}_{role}_{nonce}"
        pwd = "E2eP@ss" + nonce[-4:]
        # register
        r = api_client.post(
            f"{api_client.base_url}/auth/register",
            json={"username": uname, "password": pwd, "role": role},
            timeout=10,
        )
        # 429 = rate-limited, 跳过当前 fixture (但保留调用方返回 None 检测)
        if r.status_code == 429:
            return {"username": uname, "password": pwd, "role": role, "token": None, "_rate_limited": True}
        assert r.status_code in (200, 201, 400), (
            f"register failed: {r.status_code} {r.text[:300]}"
        )
        # login
        r = api_client.post(
            f"{api_client.base_url}/auth/login",
            json={"username": uname, "password": pwd},
            timeout=10,
        )
        if r.status_code == 429:
            return {"username": uname, "password": pwd, "role": role, "token": None, "_rate_limited": True}
        assert r.status_code in (200, 201), f"login failed: {r.status_code} {r.text[:300]}"
        body = r.json()
        token = body.get("access_token") or body.get("data", {}).get("access_token")
        assert token, f"no token in login response: {body}"
        info = {"username": uname, "password": pwd, "role": role, "token": token}
        created.append(info)
        return info

    yield _factory


# ── session-scope: 单一共享用户 (避开 5/min login + 10/min register 限流) ────
@pytest.fixture(scope="session")
def shared_user(live_server):
    """整 session 复用同一个用户 + token, 避免触发 register/login 限流。

    直接 inline register/login (不能依赖 make_user, 它是 function-scope)。
    5 个 e2e 测试全部使用这一个用户的 token 做 API 调用, rate limit 完全旁路。
    """
    sess = requests.Session()
    sess.base_url = live_server  # type: ignore[attr-defined]
    nonce = str(int(time.time() * 1000))[-9:]
    uname = f"e2e_shared_admin_{nonce}"
    pwd = "SharedP@ss" + nonce[-4:]

    # register
    r = sess.post(
        f"{live_server}/auth/register",
        json={"username": uname, "password": pwd, "role": "admin"},
        timeout=10,
    )
    assert r.status_code in (200, 201, 400), f"register failed: {r.status_code} {r.text[:300]}"

    # login
    r = sess.post(
        f"{live_server}/auth/login",
        json={"username": uname, "password": pwd},
        timeout=10,
    )
    if r.status_code == 429:
        pytest.skip("register/login rate-limited at session start — too many prior runs")
    assert r.status_code in (200, 201), f"login failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    token = body.get("access_token") or body.get("data", {}).get("access_token")
    assert token, f"no token in login response: {body}"
    info = {"username": uname, "password": pwd, "role": "admin", "token": token}
    yield info, sess
    sess.close()