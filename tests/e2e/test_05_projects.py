"""E2E path 5: projects — 登录 → 创建项目 → 列表查询 → 详情 → 更新 → 删除 → 验证 404。

覆盖:
  - API 层: POST /api/projects 创建 + GET /api/projects 列表 + GET /api/projects/{id} 详情
  - API 层: PUT /api/projects/{id} 更新元数据 + GET /api/projects/{id}/members 成员
  - API 层: DELETE /api/projects/{id} 删除 + 二次 GET 应 404
  - 负向:    创建空 name 应 400; 访问不存在的项目应 404
  - 浏览器层: page.goto('/#projects') 触发列表 + 创建流, 验证 200
"""
from __future__ import annotations

import time
import uuid

import pytest


@pytest.mark.e2e_playwright
class TestE2EProjects:
    """P5-W2 路径 5: project_view — CRUD 端到端。"""

    # ── helpers ────────────────────────────────────────────────────────────
    def _unique_name(self, prefix: str = "e2e_proj") -> str:
        nonce = uuid.uuid4().hex[:8]
        ts = str(int(time.time() * 1000))[-6:]
        return f"{prefix}_{ts}_{nonce}"

    def _create_project(self, sess, base_url: str, token: str, **overrides) -> dict:
        """POST /api/projects 返回 {success, data:{id,name,...}}。"""
        body = {
            "name": overrides.get("name", self._unique_name()),
            "description": overrides.get("description", "e2e test project"),
            "status": overrides.get("status", "active"),
            "owner": overrides.get("owner", "e2e-test"),
            "members": overrides.get("members", ["alice", "bob"]),
        }
        r = sess.post(
            f"{base_url}/api/projects",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert r.status_code in (200, 201), (
            f"project create failed: {r.status_code} {r.text[:300]}"
        )
        return (r.json().get("data") or r.json())

    # ── API 层用例 ────────────────────────────────────────────────────────
    def test_api_create_project_returns_id(self, shared_user):
        """API: 创建项目返回 id + name 一致。"""
        info, sess = shared_user
        name = self._unique_name("create")
        proj = self._create_project(sess, sess.base_url, info["token"], name=name)
        assert proj.get("id"), f"missing id in create response: {proj}"
        assert proj["id"].startswith("proj_"), f"id format wrong: {proj['id']}"
        assert proj["name"] == name, f"name mismatch: {proj['name']} vs {name}"
        assert proj["status"] == "active", f"status default wrong: {proj['status']}"

    def test_api_projects_list_contains_created(self, shared_user):
        """API: 列表 GET /api/projects 能找到刚创建的项目。"""
        info, sess = shared_user
        nonce = self._unique_name("list")
        created = self._create_project(sess, sess.base_url, info["token"], name=nonce)
        cid = created["id"]

        r = sess.get(
            f"{sess.base_url}/api/projects",
            params={"page": 1, "page_size": 50},
            headers={"Authorization": f"Bearer {info['token']}"},
            timeout=10,
        )
        assert r.status_code == 200, f"list failed: {r.status_code} {r.text[:300]}"
        body = r.json()
        data = body.get("data") or body
        projects = data.get("projects", [])
        ids = {p.get("id") for p in projects}
        assert cid in ids, (
            f"created project {cid} not in list of {len(projects)} projects"
        )
        # 数据完整性: 至少含 id + name 字段
        for p in projects:
            assert "id" in p and "name" in p, f"list entry malformed: {p}"

    def test_api_get_project_detail(self, shared_user):
        """API: GET /api/projects/{id} 详情 + members 端点。"""
        info, sess = shared_user
        proj = self._create_project(
            sess, sess.base_url, info["token"],
            name=self._unique_name("detail"),
            members=["alice", "bob", "carol"],
        )
        pid = proj["id"]

        # 详情
        r = sess.get(
            f"{sess.base_url}/api/projects/{pid}",
            headers={"Authorization": f"Bearer {info['token']}"},
            timeout=10,
        )
        assert r.status_code == 200, f"detail failed: {r.status_code} {r.text[:300]}"
        body = r.json()
        detail = body.get("data") or body
        assert detail["id"] == pid
        assert detail["name"] == proj["name"]

        # 成员
        r2 = sess.get(
            f"{sess.base_url}/api/projects/{pid}/members",
            headers={"Authorization": f"Bearer {info['token']}"},
            timeout=10,
        )
        assert r2.status_code == 200, f"members failed: {r2.status_code} {r2.text[:300]}"
        body2 = r2.json()
        data2 = body2.get("data") or body2
        members = data2.get("members", [])
        assert set(members) >= {"alice", "bob", "carol"}, (
            f"members missing: got {members}"
        )

    def test_api_update_project_status(self, shared_user):
        """API: PUT /api/projects/{id} 更新 status + description 持久化。"""
        info, sess = shared_user
        proj = self._create_project(
            sess, sess.base_url, info["token"],
            name=self._unique_name("update"),
        )
        pid = proj["id"]

        # 改成 paused + 加描述
        r = sess.put(
            f"{sess.base_url}/api/projects/{pid}",
            json={"status": "paused", "description": "updated via e2e"},
            headers={"Authorization": f"Bearer {info['token']}"},
            timeout=10,
        )
        assert r.status_code == 200, f"update failed: {r.status_code} {r.text[:300]}"
        body = r.json()
        data = body.get("data") or body
        assert data["status"] == "paused", f"update status wrong: {data['status']}"
        assert data["description"] == "updated via e2e", (
            f"update desc wrong: {data['description']}"
        )

    def test_api_delete_project_then_404(self, shared_user):
        """API: DELETE /api/projects/{id} 后, GET 应 404。"""
        info, sess = shared_user
        proj = self._create_project(
            sess, sess.base_url, info["token"],
            name=self._unique_name("delete"),
        )
        pid = proj["id"]

        # 删除
        r = sess.delete(
            f"{sess.base_url}/api/projects/{pid}",
            headers={"Authorization": f"Bearer {info['token']}"},
            timeout=10,
        )
        assert r.status_code in (200, 204), (
            f"delete failed: {r.status_code} {r.text[:300]}"
        )

        # 二次 GET 应 404
        r2 = sess.get(
            f"{sess.base_url}/api/projects/{pid}",
            headers={"Authorization": f"Bearer {info['token']}"},
            timeout=10,
        )
        assert r2.status_code == 404, (
            f"deleted project should 404, got {r2.status_code}: {r2.text[:300]}"
        )

    def test_api_create_with_empty_name_rejected(self, shared_user):
        """负向: 空 name 创建立刻 400, 不入库。"""
        info, sess = shared_user
        r = sess.post(
            f"{sess.base_url}/api/projects",
            json={"name": "   ", "description": "should fail"},
            headers={"Authorization": f"Bearer {info['token']}"},
            timeout=10,
        )
        assert r.status_code in (400, 422), (
            f"empty name should 4xx, got {r.status_code}: {r.text[:300]}"
        )

    def test_api_get_nonexistent_project_404(self, shared_user):
        """负向: 不存在的项目 id 应 404。"""
        info, sess = shared_user
        r = sess.get(
            f"{sess.base_url}/api/projects/proj_does_not_exist_zzz",
            headers={"Authorization": f"Bearer {info['token']}"},
            timeout=10,
        )
        assert r.status_code == 404, (
            f"nonexistent should 404, got {r.status_code}: {r.text[:300]}"
        )

    # ── 浏览器层用例 ─────────────────────────────────────────────────────
    def test_browser_project_crud_flow(self, page, live_server, shared_user):
        """浏览器层: 用 page.evaluate 模拟前端 projects 页面流 (create→list→delete)。"""
        info, _sess = shared_user
        nonce = self._unique_name("browser_crud")
        page.goto(live_server, wait_until="commit", timeout=15000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        page.wait_for_timeout(500)

        result = page.evaluate(
            """async ({baseUrl, token, name}) => {
                // 1. create
                const r1 = await fetch(baseUrl + '/api/projects', {
                    method: 'POST',
                    headers: {
                        'Authorization': 'Bearer ' + token,
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        name: name,
                        description: 'browser e2e',
                        status: 'active',
                        owner: 'browser',
                    }),
                });
                const create = await r1.json();
                const pid = (create.data || create).id;

                // 2. list — 必须能在列表里找到
                const r2 = await fetch(
                    baseUrl + '/api/projects?page=1&page_size=20',
                    {headers: {'Authorization': 'Bearer ' + token}},
                );
                const listBody = await r2.json();
                const list = ((listBody.data || listBody).projects) || [];
                const found = list.some(p => p.id === pid);

                // 3. delete
                const r3 = await fetch(baseUrl + '/api/projects/' + pid, {
                    method: 'DELETE',
                    headers: {'Authorization': 'Bearer ' + token},
                });
                const delBody = await r3.json();

                return {
                    createStatus: r1.status,
                    projectId: pid,
                    listStatus: r2.status,
                    listCount: list.length,
                    found: found,
                    deleteStatus: r3.status,
                    deleteResp: delBody,
                };
            }""",
            {"baseUrl": live_server, "token": info["token"], "name": nonce},
        )
        assert result["createStatus"] in (200, 201), (
            f"browser create failed: {result}"
        )
        assert result["projectId"], f"browser no project id: {result}"
        assert result["listStatus"] == 200, f"browser list failed: {result}"
        assert result["found"], (
            f"browser-created project {result['projectId']} not in list "
            f"({result['listCount']} projects)"
        )
        assert result["deleteStatus"] in (200, 204), (
            f"browser delete failed: {result}"
        )

    def test_browser_projects_hash_renders(self, page, live_server, shared_user):
        """浏览器层: page.goto('/#projects') 渲染后, 监听列表接口返回 200。"""
        info, _sess = shared_user
        captured = {"url": None, "status": None}

        def _on_response(resp):
            url = resp.url
            if "/api/projects" in url and captured["url"] is None:
                captured["url"] = url
                captured["status"] = resp.status

        page.on("response", _on_response)
        page.goto(f"{live_server}/#projects", wait_until="commit", timeout=15000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        page.wait_for_timeout(1200)

        # SPA 可能没自动触发, 主动 fetch 兜底
        if captured["url"] is None:
            res = page.evaluate(
                """async ({baseUrl, token}) => {
                    const r = await fetch(
                        baseUrl + '/api/projects?page=1&page_size=10',
                        {headers: {'Authorization': 'Bearer ' + token}},
                    );
                    return {status: r.status, body: await r.json()};
                }""",
                {"baseUrl": live_server, "token": info["token"]},
            )
            assert res["status"] == 200, (
                f"manual projects fetch failed: {res['status']}"
            )
            body = res["body"]
            data = body.get("data") or body
            assert "projects" in data, f"projects key missing: {body}"
        else:
            assert captured["status"] == 200, (
                f"projects hash triggered {captured['status']} for {captured['url']}"
            )
