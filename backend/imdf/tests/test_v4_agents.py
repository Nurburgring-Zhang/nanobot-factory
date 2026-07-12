"""智影 V4 — Agent Commands + Platform Agents + Orchestrator 集成测试"""
import os
import unittest

os.environ.setdefault("IMDF_REQUIRE_REAL_ENGINES", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MULTIMODAL_LLM_DISABLED", "1")

from imdf.intelligence.agent_commands.intent import (
    IntentClassifier, Intent, IntentCategory
)
from imdf.intelligence.agent_commands.parser import (
    CommandParser, ParsedCommand, CommandParameter
)
from imdf.intelligence.agent_commands.router import (
    CommandRouter, RouterResult, ACTION_ROUTES
)
from imdf.intelligence.agent_commands.session import (
    SessionManager, AgentSession, SessionContext
)
from imdf.intelligence.platform_agents.data_acquisition import DataAcquisitionAgent
from imdf.intelligence.platform_agents.annotation import AnnotationAgent
from imdf.intelligence.platform_agents.review import ReviewAgent
from imdf.intelligence.platform_agents.workflow import WorkflowAgent
from imdf.intelligence.platform_agents.project import ProjectAgent
from imdf.intelligence.platform_agents.user import UserAgent
from imdf.intelligence.platform_agents.pipeline import PipelineAgent
from imdf.intelligence.platform_agents.quality import QualityAgent
from imdf.intelligence.data_acquisition.orchestrator import DataAcquisitionOrchestrator, TurnResult


class TestIntentClassifier(unittest.TestCase):
    def test_crawl_intent(self):
        c = IntentClassifier()
        result = c.classify_top1("帮我爬取 https://example.com")
        self.assertIn(result.category, [IntentCategory.CRAWL, IntentCategory.PROCESS])

    def test_search_intent(self):
        c = IntentClassifier()
        result = c.classify_top1("搜索一下机器学习")
        # 中文搜索意图
        self.assertIsNotNone(result)

    def test_label_intent(self):
        c = IntentClassifier()
        result = c.classify_top1("对采集的数据自动打标")
        self.assertEqual(result.category, IntentCategory.LABEL)
        self.assertEqual(result.action, "auto_label")

    def test_score_intent(self):
        c = IntentClassifier()
        result = c.classify_top1("给数据评个质量分")
        self.assertIn(result.category, [IntentCategory.SCORE, IntentCategory.PROCESS])

    def test_dedupe_intent(self):
        c = IntentClassifier()
        result = c.classify_top1("去除重复数据")
        self.assertEqual(result.category, IntentCategory.PROCESS)

    def test_create_project_intent(self):
        c = IntentClassifier()
        result = c.classify_top1("创建一个新项目")
        self.assertEqual(result.action, "create_project")

    def test_approve_intent(self):
        c = IntentClassifier()
        result = c.classify_top1("通过审核")
        self.assertEqual(result.action, "approve")

    def test_help_intent(self):
        c = IntentClassifier()
        result = c.classify_top1("帮帮我")
        # 帮帮我 → 帮 → help / chat
        self.assertIn(result.category, [IntentCategory.SYSTEM, IntentCategory.CHAT])

    def test_greeting_intent(self):
        c = IntentClassifier()
        result = c.classify_top1("你好")
        self.assertEqual(result.action, "greeting")

    def test_url_extraction(self):
        c = IntentClassifier()
        result = c.classify_top1("爬 https://example.com/path")
        self.assertIn("urls", result.entities)
        self.assertIn("https://example.com/path", result.entities["urls"])

    def test_channel_extraction(self):
        c = IntentClassifier()
        result = c.classify_top1("爬取 arxiv 论文")
        # 至少能识别一些 channel
        self.assertIsNotNone(result.entities)

    def test_top_k(self):
        c = IntentClassifier()
        results = c.classify("自动打标并评分")
        self.assertGreaterEqual(len(results), 1)
        # 第一个 confidence 最高
        self.assertGreaterEqual(results[0].confidence, 0.5)


class TestCommandParser(unittest.TestCase):
    def setUp(self):
        self.parser = CommandParser()

    def test_crawl_url_parse(self):
        cmd = self.parser.parse("爬取 https://example.com")
        self.assertEqual(cmd.action, "crawl_url")
        self.assertEqual(cmd.get("url"), "https://example.com")

    def test_search_parse(self):
        cmd = self.parser.parse("搜索 机器学习")
        self.assertEqual(cmd.action, "web_search")
        self.assertIn("机器学习", cmd.get("query", ""))

    def test_auto_label_parse(self):
        cmd = self.parser.parse("对数据自动打标")
        self.assertEqual(cmd.action, "auto_label")

    def test_dedupe_parse(self):
        cmd = self.parser.parse("去重")
        self.assertEqual(cmd.action, "dedupe")

    def test_create_project_parse(self):
        cmd = self.parser.parse("创建一个项目")
        self.assertEqual(cmd.action, "create_project")

    def test_pipeline_inference(self):
        cmd = self.parser.parse("爬取 https://example.com")
        self.assertIn("crawl", cmd.pipeline)
        self.assertIn("dedupe", cmd.pipeline)
        self.assertIn("store", cmd.pipeline)

    def test_missing_required_param(self):
        # manual_label 需要 item_id + labels
        cmd = self.parser.parse("人工标注")
        # 至少一个 missing (item_id 或 labels)
        self.assertTrue(any("missing" in n for n in cmd.notes))

    def test_arxiv_query(self):
        cmd = self.parser.parse("搜索 arxiv 关于 transformer 的论文")
        self.assertEqual(cmd.action, "academic_search")
        self.assertEqual(cmd.get("source"), "arxiv")
        self.assertIn("transformer", cmd.get("query", ""))

    def test_depth_param(self):
        cmd = self.parser.parse("深度爬 https://example.com 深度3")
        self.assertEqual(cmd.get("max_depth"), 3)

    def test_strategy_param(self):
        cmd = self.parser.parse("深度 BFS 爬 https://example.com")
        # 深度 + BFS 应触发 deep_crawl + strategy=bfs
        self.assertIn(cmd.action, ("deep_crawl", "crawl_url"))
        if cmd.action == "deep_crawl":
            self.assertEqual(cmd.get("strategy"), "bfs")


class TestCommandRouter(unittest.TestCase):
    def setUp(self):
        # 注册 mock agents
        self.mock_agents = {
            "DataAcquisitionAgent": self._mock_agent(),
            "PipelineAgent": self._mock_agent(),
            "ProjectAgent": self._mock_agent(),
            "QualityAgent": self._mock_agent(),
            "AnnotationAgent": self._mock_agent(),
            "ReviewAgent": self._mock_agent(),
            "WorkflowAgent": self._mock_agent(),
            "UserAgent": self._mock_agent(),
        }
        self.router = CommandRouter(self.mock_agents)

    def _mock_agent(self):
        class MockAgent:
            def __getattr__(self, name):
                def fn(cmd):
                    return {"mock": True, "action": name}
                return fn
        return MockAgent()

    def test_route_known_action(self):
        cmd = ParsedCommand(intent=Intent(IntentCategory.CRAWL, "crawl_url"), action="crawl_url", raw_text="test")
        result = self.router.route_sync(cmd)
        self.assertTrue(result.success)
        self.assertEqual(result.action, "crawl_url")

    def test_route_unknown_action(self):
        # unknown action 但 mock agents 都注册了 → SystemAgent 处理
        cmd = ParsedCommand(intent=Intent(IntentCategory.CHAT, "completely_nonexistent_xyz"), action="completely_nonexistent_xyz", raw_text="test")
        result = self.router.route_sync(cmd)
        # unknown action 应有失败 error
        self.assertFalse(result.success)
        self.assertIn("unknown", result.error.lower())

    def test_routes_count(self):
        """至少 40 个路由"""
        self.assertGreaterEqual(len(ACTION_ROUTES), 40)

    def test_metrics(self):
        cmd = ParsedCommand(intent=Intent(IntentCategory.CRAWL, "crawl_url"), action="crawl_url", raw_text="test")
        self.router.route_sync(cmd)
        m = self.router.get_metrics()
        self.assertGreaterEqual(m["total"], 1)
        self.assertGreaterEqual(m["success"], 1)


class TestSessionManager(unittest.TestCase):
    def setUp(self):
        self.sm = SessionManager()

    def test_create_session(self):
        s = self.sm.create_session(user_id="alice")
        self.assertIsNotNone(s)
        self.assertEqual(s.context.user_id, "alice")
        self.assertEqual(s.status, "active")

    def test_get_or_create(self):
        s1 = self.sm.get_or_create(user_id="bob")
        s2 = self.sm.get_or_create(session_id=s1.session_id, user_id="bob")
        self.assertEqual(s1.session_id, s2.session_id)

    def test_get_or_create_new(self):
        s1 = self.sm.get_or_create(session_id="nonexistent", user_id="bob")
        # 不存在 → 用 given id 创建
        self.assertEqual(s1.session_id, "nonexistent")

    def test_close_session(self):
        s = self.sm.create_session(user_id="x")
        self.sm.close_session(s.session_id)
        # 再 get → None
        self.assertIsNone(self.sm.get_session(s.session_id))

    def test_user_sessions(self):
        self.sm.create_session(user_id="u1")
        self.sm.create_session(user_id="u1")
        self.sm.create_session(user_id="u2")
        u1 = self.sm.get_user_sessions("u1")
        self.assertEqual(len(u1), 2)

    def test_add_turn(self):
        s = self.sm.create_session(user_id="t")
        s.context.add_turn("user", "hello")
        s.context.add_turn("assistant", "hi there")
        self.assertEqual(len(s.context.history), 2)

    def test_working_set(self):
        s = self.sm.create_session(user_id="w")
        s.context.add_to_working_set({"id": "1", "hash": "h1", "title": "A"})
        s.context.add_to_working_set({"id": "1", "hash": "h1", "title": "A"})  # dup
        s.context.add_to_working_set({"id": "2", "hash": "h2", "title": "B"})
        self.assertEqual(len(s.context.working_set), 2)

    def test_update_context(self):
        s = self.sm.create_session(user_id="x")
        intent = Intent(IntentCategory.CRAWL, "crawl_url", confidence=0.9)
        self.sm.update_context(s.session_id, intent=intent)
        self.assertEqual(s.context.last_intent["action"], "crawl_url")

    def test_metrics(self):
        self.sm.create_session()
        m = self.sm.get_metrics()
        self.assertGreaterEqual(m["total_created"], 1)
        self.assertGreaterEqual(m["active_sessions"], 1)


class TestPlatformAgents(unittest.TestCase):
    def test_data_acquisition_agent(self):
        agent = DataAcquisitionAgent()
        self.assertEqual(agent.name, "DataAcquisitionAgent")
        m = agent.get_metrics()
        self.assertEqual(m["calls"], 0)

    def test_annotation_agent(self):
        agent = AnnotationAgent()
        self.assertEqual(agent.name, "AnnotationAgent")
        # get_candidate_labels
        labels = agent.get_candidate_labels()
        self.assertIn("tech", labels)

    def test_review_agent(self):
        agent = ReviewAgent()
        self.assertEqual(agent.name, "ReviewAgent")

    def test_workflow_agent(self):
        agent = WorkflowAgent()
        self.assertEqual(agent.name, "WorkflowAgent")

    def test_project_agent(self):
        agent = ProjectAgent()
        self.assertEqual(agent.name, "ProjectAgent")

    def test_user_agent(self):
        agent = UserAgent()
        self.assertEqual(agent.name, "UserAgent")

    def test_pipeline_agent(self):
        agent = PipelineAgent()
        self.assertEqual(agent.name, "PipelineAgent")

    def test_quality_agent(self):
        agent = QualityAgent()
        self.assertEqual(agent.name, "QualityAgent")

    def test_all_agents_have_capabilities(self):
        """8 个 agent 都声明了 capability"""
        agents = [
            DataAcquisitionAgent(), AnnotationAgent(), ReviewAgent(),
            WorkflowAgent(), ProjectAgent(), UserAgent(),
            PipelineAgent(), QualityAgent(),
        ]
        for a in agents:
            self.assertGreater(len(a.capabilities), 0, f"{a.name} has no capability")

    def test_auto_label_command(self):
        """AnnotationAgent 处理 auto_label 命令"""
        from imdf.intelligence.agent_commands.parser import ParsedCommand, CommandParameter
        from imdf.intelligence.agent_commands.intent import Intent, IntentCategory
        agent = AnnotationAgent()
        intent = Intent(category=IntentCategory.LABEL, action="auto_label", confidence=0.9)
        cmd = ParsedCommand(intent=intent, action="auto_label", raw_text="打标")
        result = agent.handle(cmd)
        self.assertTrue(result["success"])
        self.assertIn("models", result)


class TestDataAcquisitionOrchestrator(unittest.TestCase):
    def setUp(self):
        self.orch = DataAcquisitionOrchestrator()

    def test_orchestrator_init(self):
        self.assertIsNotNone(self.orch.router)
        self.assertIsNotNone(self.orch.session_manager)
        # 9 个 agent (含 SystemAgent)
        self.assertEqual(len(self.orch.router.agents), 9)

    def test_chat_crawl(self):
        result = self.orch.chat("爬取 https://example.com")
        self.assertIsInstance(result, TurnResult)
        self.assertEqual(result.parsed_command.action, "crawl_url")
        self.assertTrue(result.router_result.success or "missing" in (result.router_result.error or ""))

    def test_chat_search(self):
        result = self.orch.chat("搜索 机器学习 教程")
        self.assertEqual(result.parsed_command.action, "web_search")

    def test_chat_create_project(self):
        result = self.orch.chat("创建项目 名称 test_project")
        self.assertEqual(result.parsed_command.action, "create_project")
        self.assertTrue(result.router_result.success)

    def test_chat_greeting(self):
        result = self.orch.chat("你好")
        self.assertEqual(result.parsed_command.action, "greeting")
        self.assertTrue(result.router_result.success)

    def test_chat_response_text(self):
        result = self.orch.chat("创建项目 test_xyz")
        self.assertNotEqual(result.response_text, "")

    def test_chat_suggestions(self):
        result = self.orch.chat("搜索 人工智能")
        self.assertGreater(len(result.suggestions), 0)

    def test_session_persistence(self):
        """同一 session 复用"""
        r1 = self.orch.chat("搜索 A", session_id="sess-test-1")
        r2 = self.orch.chat("搜索 B", session_id="sess-test-1")
        self.assertEqual(r1.session_id, r2.session_id)

    def test_status(self):
        status = self.orch.get_status()
        self.assertIn("router", status)
        self.assertIn("sessions", status)
        self.assertIn("data_acq", status)
        self.assertIn("pipeline", status)
        self.assertIn("annotation", status)
        self.assertIn("review", status)
        self.assertIn("workflow", status)
        self.assertIn("project", status)
        self.assertIn("user", status)
        self.assertIn("quality", status)

    def test_chat_with_context(self):
        """session 上下文跨轮"""
        s = self.orch.session_manager.create_session(user_id="ctx-test")
        r1 = self.orch.chat("创建项目", session_id=s.session_id)
        r2 = self.orch.chat("再创建一个", session_id=s.session_id)
        self.assertEqual(r1.session_id, r2.session_id)
        # history 应有累积
        self.assertGreaterEqual(len(s.context.history), 4)


class TestEndToEndChatFlow(unittest.TestCase):
    """端到端: 5 轮对话模拟用户操作"""

    def test_5_turn_conversation(self):
        orch = DataAcquisitionOrchestrator()
        session_id = None
        conversation = [
            "你好",
            "搜索 关于 transformer 的最新论文",
            "对结果自动打标",
            "按质量分过滤 0.6 以上的",
            "创建项目 名称 transformer_research",
        ]
        for text in conversation:
            result = orch.chat(text, session_id=session_id)
            self.assertIsNotNone(result)
            if session_id is None:
                session_id = result.session_id
            self.assertTrue(result.router_result.success, f"failed: {text} → {result.router_result.error}")
        # 最后 session 有完整 history
        s = orch.session_manager.get_session(session_id)
        self.assertGreaterEqual(len(s.context.history), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
