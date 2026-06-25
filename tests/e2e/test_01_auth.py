"""E2E path 1: auth — 注册 → 登录 → 拿到 token → /api/users/me 返回当前用户。

覆盖:
  - HTTP API 端到端: register/login/me
  - 浏览器层: page.goto(根路径) + Playwright fetch /auth/me (用 shared_user 凭证, 避免 5/min login 限流)
"""
from __future__ import annotations

import time

import pytest


@pytest.mark.e2e_playwright
class TestE2EAuth:
    """P2-2-W2 路径 1: 注册登录 + me 查询 + 浏览器 SPA 入口验证。"""

    def test_register_then_login_returns_token(self, api_client, make_user):
        """API 层: 注册 + 登录拿到 JWT。"""
        info = make_user(role="annotator")
        if info.get("_rate_limited"):
            pytest.skip("register/login rate-limited; test environment exhausted")
        assert info["token"], "login must yield non-empty access_token"
        assert len(info["token"]) > 20, "JWT must be reasonable length"

    def test_me_endpoint_returns_current_user(self, shared_user):
        """API 层: 拿 token 后 GET /auth/me 返回 200 + 用户名匹配。
        (注意: /api/users/me 是 p1_c_w1 的可选鉴权封装, 严格鉴权走 /auth/me。)
        """
        info, sess = shared_user
        r = sess.get(
            f"{sess.base_url}/auth/me",
            headers={"Authorization": f"Bearer {info['token']}"},
            timeout=10,
        )
        assert r.status_code == 200, f"me failed: {r.status_code} {r.text[:300]}"
        body = r.json()
        # /auth/me 返回 {success, data: {username, role, ...}}
        data = body.get("data") or body
        assert data.get("username") == info["username"], (
            f"me returned wrong user: {data} (expected {info['username']})"
        )

    def test_register_duplicate_rejected(self, api_client):
        """负向: 重复用户名第二次注册应被拒 (400 或 409)。"""
        nonce = str(int(time.time() * 1000))[-9:]
        uname = f"e2e_dup_{nonce}"
        pwd = "DupP@ss" + nonce[-4:]
        body = {"username": uname, "password": pwd, "role": "annotator"}
        first = api_client.post(f"{api_client.base_url}/auth/register", json=body, timeout=10)
        assert first.status_code in (200, 201), first.text[:300]
        second = api_client.post(f"{api_client.base_url}/auth/register", json=body, timeout=10)
        assert second.status_code in (400, 409, 422), (
            f"duplicate should be rejected, got {second.status_code}: {second.text[:300]}"
        )

    def test_browser_login_page_loads(self, page, live_server, shared_user):
        """浏览器层: 用 shared_user 凭证在浏览器 fetch 中验证 /auth/me 链路。
        (用 /auth/me 而不是 /auth/login, 避免 5/min login 限流叠加 + 注册新用户绕路)。
        """
        info, _sess = shared_user
        page.goto(live_server, wait_until="commit", timeout=15000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        page.wait_for_timeout(800)
        # 用浏览器 fetch 验证已登录用户访问 /auth/me — 这是真正的浏览器层 E2E
        result = page.evaluate(
            """async ({baseUrl, token}) => {
                const r = await fetch(baseUrl + '/auth/me', {
                    headers: {'Authorization': 'Bearer ' + token},
                    credentials: 'include',
                });
                const body = await r.json();
                return {
                    status: r.status,
                    username: (body.data && body.data.username) || body.username,
                };
            }""",
            {"baseUrl": live_server, "token": info["token"]},
        )
        assert result["status"] == 200, f"browser /auth/me failed: {result}"
        assert result["username"] == info["username"], (
            f"browser /auth/me wrong user: {result}"
        )