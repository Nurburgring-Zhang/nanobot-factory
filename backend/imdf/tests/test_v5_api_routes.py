"""智影 V5 — API 路由测试 (FastAPI TestClient)"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("IMDF_REQUIRE_REAL_ENGINES", "1")
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("JWT_SECRET", "test-secret-for-v5-1234567890abcdef")
os.environ.setdefault("AUDIT_CHAIN_SECRET", "test-secret-for-v5-p11b-1234567890")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MULTIMODAL_LLM_DISABLED", "1")

_IMDF = Path(__file__).resolve().parent.parent
_BACKEND = _IMDF.parent
sys.path = [p for p in sys.path if Path(p).resolve() != _BACKEND.resolve()]
_sp = str(_IMDF.resolve())
if _sp not in sys.path:
    sys.path.insert(0, _sp)


class TestIntelligenceV5Routes(unittest.TestCase):
    """V5 API 路由 — 用 TestClient 测"""

    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from imdf.api.intelligence_v5_routes import router

        cls.app = FastAPI()
        cls.app.include_router(router)
        cls.client = TestClient(cls.app)

    def test_health(self):
        """V5 健康检查"""
        r = self.client.get("/api/v5/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["version"], "5.0.0")

    def test_stats(self):
        """V5 全局统计"""
        r = self.client.get("/api/v5/stats")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("identity", data)
        self.assertIn("memory", data)
        self.assertIn("roles", data)

    # Identity
    def test_register_bot(self):
        """注册 Bot"""
        r = self.client.post("/api/v5/bots/register", json={
            "name": "test-bot-1",
            "role": "developer",
            "description": "test",
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("bot_id", r.json())

    def test_list_bots(self):
        """列出 Bot"""
        self.client.post("/api/v5/bots/register", json={"name": "list-bot", "role": "qa"})
        r = self.client.get("/api/v5/bots")
        self.assertEqual(r.status_code, 200)
        self.assertIn("bots", r.json())

    def test_register_bot_invalid_role(self):
        """无效角色 400"""
        r = self.client.post("/api/v5/bots/register", json={"name": "x", "role": "invalid_role"})
        self.assertEqual(r.status_code, 400)

    def test_create_channel(self):
        """创建 Channel"""
        r = self.client.post("/api/v5/channels", json={"name": "test-ch", "channel_type": "team"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("channel_id", r.json())

    def test_create_thread(self):
        """创建 Thread"""
        r = self.client.post("/api/v5/threads", json={"title": "需求评审"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("thread_id", r.json())

    def test_create_matter(self):
        """创建 Matter"""
        r = self.client.post("/api/v5/matters", json={"title": "Build Crawler", "description": "..."})
        self.assertEqual(r.status_code, 200)
        self.assertIn("matter_id", r.json())

    # Memory
    def test_memory_raw(self):
        """添加 RAW 记忆"""
        r = self.client.post("/api/v5/memory/raw", json={"title": "raw1", "content": "原始证据", "source": "test"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["layer"], "raw")

    def test_memory_query(self):
        """Memory 查询"""
        self.client.post("/api/v5/memory/inbox", json={"title": "q1", "content": "测试"})
        r = self.client.get("/api/v5/memory/query?q=测试")
        self.assertEqual(r.status_code, 200)
        self.assertIn("items", r.json())

    def test_palace_install(self):
        """安装默认 Palace"""
        r = self.client.post("/api/v5/palace/install")
        self.assertEqual(r.status_code, 200)
        self.assertIn("room_count", r.json())

    def test_feedback_record(self):
        """记录反馈"""
        r = self.client.post("/api/v5/feedback", json={"target_id": "m1", "feedback_type": "approve", "comment": "好"})
        self.assertEqual(r.status_code, 200)

    # Harness
    def test_harness_plan(self):
        """Harness 计划"""
        r = self.client.post("/api/v5/harness/plan", json={"prompt": "Build a CLI"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreater(data["steps_count"], 0)

    def test_harness_run(self):
        """Harness 完整 loop"""
        r = self.client.post("/api/v5/harness/run", json={"prompt": "Build a web scraper"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("plan_id", data)
        self.assertIn("sprint_id", data)

    # Skills
    def test_list_skills(self):
        """列出技能"""
        r = self.client.get("/api/v5/skills")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 6)

    # MoA
    def test_moa_ask(self):
        """MoA 询问"""
        r = self.client.post("/api/v5/moa/ask", json={"query": "What is the best LLM?"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("answer", r.json())

    # Cron
    def test_cron_add_job(self):
        """添加 cron"""
        r = self.client.post("/api/v5/cron/jobs", json={"name": "test", "schedule": "0 9 * * *", "action": "send"})
        self.assertEqual(r.status_code, 200)

    def test_cron_nl(self):
        """Cron NL"""
        r = self.client.post("/api/v5/cron/jobs", json={"name": "nl-test", "schedule": "every morning at 9am", "action": "send"})
        self.assertEqual(r.status_code, 200)

    # Goals
    def test_create_goal(self):
        """创建 Goal"""
        r = self.client.post("/api/v5/goals", json={"name": "g1", "result": "完成 X", "deliverables": ["x.py"]})
        self.assertEqual(r.status_code, 200)

    # Video
    def test_create_video_project(self):
        """创建视频项目"""
        r = self.client.post("/api/v5/video/projects", json={"prompt": "赛博朋克短剧"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("project_id", r.json())

    # Brand
    def test_brand_research(self):
        """品牌研究"""
        r = self.client.post("/api/v5/brand/research", json={"brand": "Acme"})
        self.assertEqual(r.status_code, 200)

    # Data Gateway
    def test_list_platforms(self):
        """列出平台"""
        r = self.client.get("/api/v5/data/platforms")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 10)

    # Roles
    def test_list_roles(self):
        """列出角色"""
        r = self.client.get("/api/v5/roles")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 30)

    def test_list_roles_by_dept(self):
        """按部门列角色"""
        r = self.client.get("/api/v5/roles?department=engineering")
        self.assertEqual(r.status_code, 200)

    def test_list_roles_bad_dept(self):
        """无效部门 400"""
        r = self.client.get("/api/v5/roles?department=invalid")
        self.assertEqual(r.status_code, 400)

    def test_get_role_404(self):
        """角色不存在 404"""
        r = self.client.get("/api/v5/roles/non-existent-role-id")
        self.assertEqual(r.status_code, 404)

    # MCP
    def test_list_mcp_tools(self):
        """MCP 工具列表"""
        r = self.client.get("/api/v5/mcp/tools")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 5)

    def test_mcp_rpc(self):
        """MCP JSON-RPC"""
        r = self.client.post("/api/v5/mcp/rpc", json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
        })
        self.assertEqual(r.status_code, 200)

    # Proactive
    def test_proactive_daily_report(self):
        """Proactive 战报"""
        r = self.client.post("/api/v5/proactive/daily-report")
        self.assertEqual(r.status_code, 200)

    # Monitor
    def test_monitor_heartbeat(self):
        """Monitor 心跳"""
        r = self.client.post("/api/v5/monitor/heartbeat", json={"bot_id": "b1", "status": "working"})
        self.assertEqual(r.status_code, 200)

    # Geo
    def test_geo_decode(self):
        """Terrarium RGB → 米"""
        r = self.client.post("/api/v5/geo/decode", json={"r": 128, "g": 0, "b": 0})
        self.assertEqual(r.status_code, 200)
        # 海平面 RGB(128,0,0) → 0m
        self.assertAlmostEqual(r.json()["elevation_m"], 0.0, delta=1.0)

    def test_geo_encode(self):
        """米 → RGB"""
        r = self.client.post("/api/v5/geo/encode", json={"elevation": 100.0})
        self.assertEqual(r.status_code, 200)
        self.assertIn("rgb", r.json())

    # Profile
    def test_create_user_profile(self):
        """创建用户画像"""
        r = self.client.post("/api/v5/profile/users", json={"user_id": "u-test", "username": "test", "identity": "test"})
        self.assertEqual(r.status_code, 200)

    def test_get_user_profile(self):
        """获取用户画像"""
        self.client.post("/api/v5/profile/users", json={"user_id": "u-g", "username": "g"})
        r = self.client.get("/api/v5/profile/users/u-g")
        self.assertEqual(r.status_code, 200)

    def test_get_user_profile_404(self):
        """画像不存在 404"""
        r = self.client.get("/api/v5/profile/users/non-existent")
        self.assertEqual(r.status_code, 404)

    def test_profile_md(self):
        """Profile.md 渲染"""
        self.client.post("/api/v5/profile/users", json={"user_id": "u-md", "username": "md"})
        r = self.client.get("/api/v5/profile/users/u-md/profile-md")
        self.assertEqual(r.status_code, 200)
        self.assertIn("profile.md", r.json()["md"])

    def test_agent_templates(self):
        """Agent 模板"""
        r = self.client.get("/api/v5/profile/agent-templates")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 4)

    # Perf
    def test_cache_put_get(self):
        """缓存 put/get"""
        self.client.post("/api/v5/perf/cache/put", json={"key": "k1", "value": "v1"})
        r = self.client.get("/api/v5/perf/cache/get?key=k1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["value"], "v1")

    def test_cache_invalidate(self):
        """缓存失效"""
        self.client.post("/api/v5/perf/cache/put", json={"key": "k2", "value": "v2"})
        r = self.client.delete("/api/v5/perf/cache/k2")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["invalidated"])

    def test_cache_stats(self):
        """缓存统计"""
        r = self.client.get("/api/v5/perf/cache/stats")
        self.assertEqual(r.status_code, 200)
        self.assertIn("hits", r.json())

    def test_compress_messages(self):
        """消息压缩"""
        r = self.client.post("/api/v5/perf/compress", json={"messages": [{"role": "user", "content": "x" * 1000}] * 5})
        self.assertEqual(r.status_code, 200)
        self.assertIn("compression_ratio", r.json())


if __name__ == "__main__":
    unittest.main()
