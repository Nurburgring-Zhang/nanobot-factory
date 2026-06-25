"""E2E path 4: assets — 登录 → 上传小图片 → 列表 → 下载 → 200。

覆盖:
  - API 层: POST /api/assets/upload (multipart) 返回 200 + asset id
  - API 层: GET /api/assets 列表含刚上传的资产
  - API 层: GET /api/assets/{id}/download 返回 200 + 字节流
"""
from __future__ import annotations

import io
import uuid

import pytest


# 1x1 PNG (transparent) 的最小合法字节流
TINY_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
    b"\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa3"
    b"\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.e2e_playwright
class TestE2EAssets:
    """P3-6.5-W2 路径 4: 资产上传 + 列表 + 下载链路验证。"""

    def _upload_png(self, sess, base_url: str, token: str,
                    filename: str = "tiny.png",
                    tags: str = "e2e,test") -> dict:
        """POST /api/assets/upload 返回 parsed JSON dict (含 asset id)。"""
        files = {"file": (filename, io.BytesIO(TINY_PNG_BYTES), "image/png")}
        data = {"type": "image", "tags": tags}
        r = sess.post(
            f"{base_url}/api/assets/upload",
            files=files,
            data=data,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert r.status_code in (200, 201), (
            f"asset upload failed: {r.status_code} {r.text[:300]}"
        )
        body = r.json()
        return body.get("data") or body

    def test_api_upload_returns_asset_id(self, shared_user):
        """API 层: 上传 1x1 PNG 返回 200/201 + asset id。"""
        info, sess = shared_user
        asset = self._upload_png(
            sess, sess.base_url, info["token"],
            filename=f"e2e_{uuid.uuid4().hex[:6]}.png",
            tags="e2e,upload",
        )
        assert "id" in asset, f"upload response missing id: {asset}"
        assert asset.get("type") == "image", f"wrong asset type: {asset}"
        assert asset.get("size", 0) > 0, f"zero size: {asset}"
        assert asset.get("name", "").endswith(".png"), (
            f"uploaded filename not preserved: {asset.get('name')}"
        )

    def test_api_assets_list_contains_uploaded(self, shared_user):
        """API 层: 上传后, 列表 GET /api/assets 能找到该资产。"""
        info, sess = shared_user
        nonce_tag = f"e2e_list_{uuid.uuid4().hex[:6]}"
        uploaded = self._upload_png(
            sess, sess.base_url, info["token"],
            filename=f"list_{nonce_tag}.png",
            tags=f"e2e,{nonce_tag}",
        )
        asset_id = uploaded["id"]

        r = sess.get(
            f"{sess.base_url}/api/assets",
            params={"page": 1, "page_size": 50, "type": "image"},
            headers={"Authorization": f"Bearer {info['token']}"},
            timeout=10,
        )
        assert r.status_code == 200, f"list failed: {r.status_code} {r.text[:300]}"
        body = r.json()
        data = body.get("data") or body
        assets = data.get("assets", [])
        ids = {a.get("id") for a in assets}
        assert asset_id in ids, (
            f"uploaded asset {asset_id} not found in list of {len(assets)} assets"
        )

    def test_api_assets_download_returns_200(self, shared_user):
        """API 层: GET /api/assets/{id}/download 返回 200 + 二进制字节流。"""
        info, sess = shared_user
        uploaded = self._upload_png(
            sess, sess.base_url, info["token"],
            filename=f"dl_{uuid.uuid4().hex[:6]}.png",
            tags="e2e,download",
        )
        asset_id = uploaded["id"]

        r = sess.get(
            f"{sess.base_url}/api/assets/{asset_id}/download",
            headers={"Authorization": f"Bearer {info['token']}"},
            timeout=15,
        )
        assert r.status_code == 200, (
            f"download failed: {r.status_code} {r.text[:300]}"
        )
        # Content 长度应 > 0
        body = r.content
        assert len(body) > 0, f"download returned empty body (status={r.status_code})"
        # 至少 PNG magic bytes 开头
        assert body.startswith(b"\x89PNG"), (
            f"downloaded body not PNG: {body[:8]!r}"
        )

    def test_browser_asset_upload_and_list(self, page, live_server, shared_user):
        """浏览器层: 用 page.evaluate + FormData 模拟前端上传, 然后列表确认。

        复用 shared_user 凭证避免 register/login 限流。
        """
        info, _sess = shared_user

        page.goto(live_server, wait_until="commit", timeout=15000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        page.wait_for_timeout(500)

        result = page.evaluate(
            """async ({baseUrl, token}) => {
                // 1x1 transparent PNG
                const pngB64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABXvMqOgAAAABJRU5ErkJggg==';
                const bin = Uint8Array.from(atob(pngB64), c => c.charCodeAt(0));
                const blob = new Blob([bin], {type: 'image/png'});
                const fd = new FormData();
                fd.append('file', blob, 'e2e_browser.png');
                fd.append('type', 'image');
                fd.append('tags', 'e2e,browser');

                const r1 = await fetch(baseUrl + '/api/assets/upload', {
                    method: 'POST',
                    headers: {'Authorization': 'Bearer ' + token},
                    body: fd,
                });
                const upload = await r1.json();
                const assetId = (upload.data || upload).id;

                // 列表校验
                const r2 = await fetch(
                    baseUrl + '/api/assets?type=image&page=1&page_size=10',
                    {headers: {'Authorization': 'Bearer ' + token}},
                );
                const list = await r2.json();
                const assets = ((list.data || list).assets) || [];
                const found = assets.some(a => a.id === assetId);

                // 下载校验
                const r3 = await fetch(baseUrl + '/api/assets/' + assetId + '/download', {
                    headers: {'Authorization': 'Bearer ' + token},
                });
                const dl = await r3.arrayBuffer();

                return {
                    uploadStatus: r1.status,
                    assetId: assetId,
                    listStatus: r2.status,
                    listCount: assets.length,
                    found: found,
                    downloadStatus: r3.status,
                    downloadBytes: dl.byteLength,
                };
            }""",
            {"baseUrl": live_server, "token": info["token"]},
        )
        assert result["uploadStatus"] in (200, 201), (
            f"browser upload failed: {result}"
        )
        assert result["assetId"], f"no asset id returned: {result}"
        assert result["listStatus"] == 200, f"browser list failed: {result}"
        assert result["found"], (
            f"uploaded asset {result['assetId']} not in browser list ({result['listCount']})"
        )
        assert result["downloadStatus"] == 200, (
            f"browser download failed: {result}"
        )
        assert result["downloadBytes"] > 0, (
            f"download returned 0 bytes: {result}"
        )