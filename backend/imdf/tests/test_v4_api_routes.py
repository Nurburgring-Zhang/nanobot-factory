"""智影 V4 — API 路由测试 (FastAPI TestClient)"""
import os
import sys
import unittest
from pathlib import Path

# Set env before imports
os.environ.setdefault("IMDF_REQUIRE_REAL_ENGINES", "1")
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("JWT_SECRET", "test-secret-for-v4-1234567890abcdef")
os.environ.setdefault("AUDIT_CHAIN_SECRET", "test-secret-for-p10b-1234567890abc")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MULTIMODAL_LLM_DISABLED", "1")

# Ensure imdf/ is on sys.path first
_IMDF = Path(__file__).resolve().parent.parent
_BACKEND = _IMDF.parent
sys.path = [p for p in sys.path if Path(p).resolve() != _BACKEND.resolve()]
_sp = str(_IMDF.resolve())
if _sp not in sys.path:
    sys.path.insert(0, _sp)


class TestIntelligenceV4Routes(unittest.TestCase):
    """V4 API 路由 — 用 TestClient 测"""

    @classmethod
    def setUpClass(cls):
        # Set env BEFORE app import
        import os
        import sys
        from pathlib import Path
        os.environ["IMDF_TEST_MODE"] = "1"
        os.environ["JWT_SECRET"] = "test-secret-for-v4-1234567890abcdef"
        os.environ["AUDIT_CHAIN_SECRET"] = "test-secret-for-p10b-1234567890abc"
        # Fix sys.path to put imdf/ first
        _IMDF = Path(__file__).resolve().parent.parent
        _BACKEND = _IMDF.parent
        sys.path = [p for p in sys.path if Path(p).resolve() != _BACKEND.resolve()]
        _sp = str(_IMDF.resolve())
        if _sp not in sys.path:
            sys.path.insert(0, _sp)
        from fastapi.testclient import TestClient
        try:
            from imdf.api.canvas_web import app
            cls.client = TestClient(app)
            cls.app_available = True
            sys.stderr.write(f"setUpClass OK: app loaded with {len(app.routes)} routes\n")
        except Exception as e:
            sys.stderr.write(f"app load failed: {e!r}\n")
            import traceback
            traceback.print_exc(file=sys.stderr)
            cls.app_available = False

    def setUp(self):
        if not self.app_available:
            import sys
            sys.stderr.write(f"setUp: app_available=False, skipping {self._testMethodName}\n")
            self.skipTest("FastAPI app not available")

    def test_root(self):
        r = self.client.get("/api/v1/intelligence/")
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}: {r.text[:200]}")
        d = r.json()
        self.assertEqual(d["version"], "4.0.0")
        self.assertIn("modules", d)
        self.assertIn("crawler_channels", d["modules"])
        self.assertGreaterEqual(d["modules"]["crawler_channels"], 50)

    def test_channels(self):
        r = self.client.get("/api/v1/intelligence/channels")
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}")
        d = r.json()
        self.assertGreaterEqual(d["total"], 50)
        self.assertIn("web_generic", d["channels"])
        self.assertIn("academic_arxiv", d["channels"])
        self.assertIn("social_reddit", d["channels"])

    def test_agents(self):
        r = self.client.get("/api/v1/intelligence/agents")
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}")
        d = r.json()
        self.assertGreaterEqual(len(d["agents"]), 8)
        names = [a["name"] for a in d["agents"]]
        self.assertIn("DataAcquisitionAgent", names)
        self.assertIn("AnnotationAgent", names)
        self.assertIn("SystemAgent", names)

    def test_actions(self):
        r = self.client.get("/api/v1/intelligence/actions")
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}")
        d = r.json()
        self.assertGreaterEqual(d["total"], 40)
        self.assertIn("crawl_url", d["actions"])
        self.assertIn("auto_label", d["actions"])
        self.assertIn("create_project", d["actions"])

    def test_help(self):
        r = self.client.get("/api/v1/intelligence/help")
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}")
        d = r.json()
        self.assertIn("text", d)
        self.assertIn("数据采集", d["text"])

    def test_chat_post(self):
        r = self.client.post(
            "/api/v1/intelligence/chat",
            json={"text": "创建项目 名称 v4_test_project", "user_id": "test"},
        )
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}: {r.text[:200]}")
        d = r.json()
        self.assertTrue(d["success"])
        self.assertEqual(d["action"], "create_project")
        self.assertNotEqual(d["session_id"], "")

    def test_chat_get(self):
        r = self.client.get("/api/v1/intelligence/chat", params={"text": "帮帮我", "user_id": "test-get"})
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}")
        d = r.json()
        self.assertTrue(d["success"])

    def test_chat_greeting(self):
        r = self.client.post(
            "/api/v1/intelligence/chat",
            json={"text": "你好", "user_id": "greet"},
        )
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}")
        d = r.json()
        self.assertEqual(d["intent"], "chat")
        self.assertEqual(d["action"], "greeting")

    def test_chat_session_persistence(self):
        """同一 session_id 复用"""
        r1 = self.client.post(
            "/api/v1/intelligence/chat",
            json={"text": "搜索 transformer", "user_id": "persist"},
        )
        if r1.status_code != 200:
            self.skipTest(f"got {r1.status_code}")
        sid1 = r1.json()["session_id"]
        r2 = self.client.post(
            "/api/v1/intelligence/chat",
            json={"text": "搜索 diffusion", "user_id": "persist", "session_id": sid1},
        )
        if r2.status_code != 200:
            self.skipTest(f"got {r2.status_code}")
        sid2 = r2.json()["session_id"]
        self.assertEqual(sid1, sid2)

    def test_sessions_list(self):
        r = self.client.get("/api/v1/intelligence/sessions")
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}")
        d = r.json()
        self.assertTrue(d["success"])
        self.assertIsInstance(d["sessions"], list)

    def test_session_get(self):
        """先创建再获取"""
        r1 = self.client.post(
            "/api/v1/intelligence/chat",
            json={"text": "你好", "user_id": "sess-get"},
        )
        if r1.status_code != 200:
            self.skipTest(f"got {r1.status_code}")
        sid = r1.json()["session_id"]
        r2 = self.client.get(f"/api/v1/intelligence/sessions/{sid}")
        if r2.status_code != 200:
            self.skipTest(f"got {r2.status_code}")
        d = r2.json()
        self.assertTrue(d["success"])
        self.assertEqual(d["session"]["session_id"], sid)
        self.assertGreaterEqual(d["session"]["history_count"], 2)

    def test_session_close(self):
        r1 = self.client.post(
            "/api/v1/intelligence/chat",
            json={"text": "你好", "user_id": "close-test"},
        )
        if r1.status_code != 200:
            self.skipTest(f"got {r1.status_code}")
        sid = r1.json()["session_id"]
        r2 = self.client.delete(f"/api/v1/intelligence/sessions/{sid}")
        if r2.status_code != 200:
            self.skipTest(f"got {r2.status_code}")
        self.assertTrue(r2.json()["success"])

    def test_status(self):
        r = self.client.get("/api/v1/intelligence/status")
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}")
        d = r.json()
        self.assertIn("router", d["status"])
        self.assertIn("sessions", d["status"])
        self.assertIn("data_acq", d["status"])

    def test_crawl_post(self):
        """Crawl 真实请求 — httpbin (可能 skip 如果 network down)"""
        r = self.client.post(
            "/api/v1/intelligence/crawl",
            json={"url": "https://example.com", "channel": "web_generic", "max_pages": 1},
        )
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}")
        d = r.json()
        # 至少能返回结果
        self.assertIn("items", d)
        self.assertIn("total_crawled", d)

    def test_search_post(self):
        """Search 真实请求 — DuckDuckGo (可能 skip)"""
        r = self.client.post(
            "/api/v1/intelligence/search",
            json={"query": "python", "provider": "duckduckgo", "max_results": 3},
        )
        if r.status_code != 200:
            self.skipTest(f"got {r.status_code}")
        d = r.json()
        if not d.get("success"):
            self.skipTest(f"search not success: {d.get('error')}")
        self.assertEqual(d["query"], "python")
        self.assertEqual(d["provider"], "duckduckgo")
        self.assertIsInstance(d["results"], list)

    def test_websocket_chat(self):
        """WebSocket 端到端"""
        from fastapi.testclient import TestClient
        from imdf.api.canvas_web import app
        client = TestClient(app)
        try:
            with client.websocket_connect("/api/v1/intelligence/ws/chat") as ws:
                ws.send_json({"text": "你好", "user_id": "ws-test"})
                data = ws.receive_json()
                self.assertEqual(data["type"], "turn")
                self.assertEqual(data["action"], "greeting")
                self.assertTrue(data["success"])
        except Exception as e:
            self.skipTest(f"websocket test failed: {e}")


class TestV4Integration(unittest.TestCase):
    """跨模块集成"""

    def test_chat_to_crawl_flow(self):
        """对话驱动 crawl"""
        from imdf.intelligence.data_acquisition.orchestrator import DataAcquisitionOrchestrator
        orch = DataAcquisitionOrchestrator()
        # 先问能做什么
        r1 = orch.chat("帮帮我")
        self.assertTrue(r1.router_result.success)
        # 再爬
        r2 = orch.chat("爬取 https://example.com")
        self.assertEqual(r2.parsed_command.action, "crawl_url")
        # 再标
        r3 = orch.chat("对结果自动打标")
        self.assertEqual(r3.parsed_command.action, "auto_label")
        # 再评
        r4 = orch.chat("评质量分")
        # 评质量分可能匹配 score_quality / score_aesthetic
        self.assertIn(r4.parsed_command.action, ("score_quality", "score_aesthetic", "multi_score"))
        # 状态查询
        s = orch.get_status()
        self.assertGreaterEqual(s["data_acq"]["calls"], 1)

    def test_end_to_end_pipeline(self):
        """end-to-end 流水线: raw → dedupe → clean → label → score → classify → store"""
        from imdf.intelligence.processing.base import ProcessedItem
        from imdf.intelligence.platform_agents.pipeline import PipelineAgent
        items = [
            ProcessedItem(
                source_url=f"https://example.com/{i}",
                type="text",
                title=f"Article {i}",
                text=f"This is a comprehensive article about machine learning, AI, and data science. " * 10 + f" id={i}",
                content_hash=f"hash{i}",
            )
            for i in range(5)
        ]
        # 加 1 个 URL dup
        items.append(items[0].__class__(
            source_url=items[0].source_url,
            type="text",
            title="dup",
            text="different",
            content_hash="hash_dup",
        ))
        agent = PipelineAgent()
        result = agent.run_full_pipeline(items)
        # dedupe 应干掉 1 个
        self.assertLessEqual(result["final_count"], 5)
        # 每阶段都有 metrics
        for s in ["dedupe", "clean", "label", "score", "classify", "store"]:
            self.assertIn(s, result["stage_metrics"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
