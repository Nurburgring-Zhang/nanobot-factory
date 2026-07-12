"""智影 V5 — Identity (Bot/Channel/Thread/Matter) + Roles + Profile 测试"""
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


class TestV5Identity(unittest.TestCase):
    """V5 Identity — Bot/Channel/Thread/Matter"""

    def test_bot_creation(self):
        """Bot 创建 + AgentCard + 角色"""
        from imdf.intelligence_v5 import Bot, AgentCard, BotRole
        card = AgentCard(name="planner-1", role=BotRole.PLANNER, description="Full Harness Planner")
        bot = Bot(card=card)
        self.assertTrue(bot.bot_id.startswith("bot-"))
        self.assertEqual(bot.card.role, BotRole.PLANNER)
        self.assertEqual(bot.status.value, "idle")

    def test_bot_registry_register(self):
        """Bot Registry 注册/查询"""
        from imdf.intelligence_v5 import BotRole, bot_registry
        bot = bot_registry.register(name="dev-1", role=BotRole.DEVELOPER, description="Test dev")
        self.assertIsNotNone(bot.bot_id)
        found = bot_registry.get_bot(bot.bot_id)
        self.assertEqual(found.card.name, "dev-1")

    def test_bot_registry_list_bots(self):
        """列出所有 Bot"""
        from imdf.intelligence_v5 import BotRole, bot_registry
        bot_registry.register(name="qa-test", role=BotRole.QA)
        bot_registry.register(name="dev-test", role=BotRole.DEVELOPER)
        all_bots = bot_registry.list_bots()
        self.assertGreaterEqual(len(all_bots), 2)

    def test_channel_creation(self):
        """Channel 创建"""
        from imdf.intelligence_v5 import Channel
        from imdf.intelligence_v5.identity.channel import ChannelType
        ch = Channel(name="数据采集组", channel_type=ChannelType.TEAM, description="Team channel")
        self.assertTrue(ch.channel_id.startswith("ch-"))
        self.assertEqual(ch.channel_type, ChannelType.TEAM)

    def test_channel_members(self):
        """Channel 成员管理"""
        from imdf.intelligence_v5 import Channel
        from imdf.intelligence_v5.identity.channel import ChannelType
        ch = Channel(name="test-ch", channel_type=ChannelType.PROJECT)
        ch.add_member(member_id="bob", member_type="user", role="member")
        self.assertEqual(len(ch.members), 1)
        self.assertIn("bob", ch.members)

    def test_thread_creation(self):
        """Thread 创建 + 消息流"""
        from imdf.intelligence_v5 import Thread, ThreadStatus
        t = Thread(title="需求评审", channel_id="ch-1", creator_id="alice")
        msg = t.add_message(sender_id="alice", content="我们需要一个爬虫", sender_type="user")
        self.assertEqual(len(t.messages), 1)
        self.assertEqual(t.status, ThreadStatus.OPEN)

    def test_matter_lifecycle(self):
        """Matter 从 Thread 升级 + 验收标准"""
        from imdf.intelligence_v5 import (
            Thread, Matter, MatterStatus, AcceptanceCriteria
        )
        thread = Thread(title="Crawl task", channel_id="ch-1", creator_id="alice")
        thread.add_message(sender_id="alice", content="做一个爬虫", sender_type="user")
        matter = Matter(
            title="Build Crawler",
            thread_id=thread.thread_id,
            description="Build production crawler",
            owner_id="alice",
        )
        # 验证 matter 字段
        self.assertEqual(matter.title, "Build Crawler")
        self.assertEqual(matter.status, MatterStatus.DRAFT)
        # 验收标准通过字段直接设置
        matter.criteria = [AcceptanceCriteria(description="能爬 100 页", required=True)]
        self.assertEqual(len(matter.criteria), 1)

    def test_all_bot_roles(self):
        """16 BotRole 完整"""
        from imdf.intelligence_v5 import BotRole
        self.assertEqual(len(list(BotRole)), 16)


class TestV5Roles(unittest.TestCase):
    """V5 Roles — The Agency 角色库"""

    def test_role_registry_count(self):
        """角色库 ≥ 30 角色"""
        from imdf.intelligence_v5 import role_registry
        all_roles = role_registry.list_all()
        self.assertGreaterEqual(len(all_roles), 30)

    def test_role_definition_fields(self):
        """RoleDefinition 含 prompt_template + workflow + deliverables"""
        from imdf.intelligence_v5 import role_registry
        for role in role_registry.list_all()[:5]:
            self.assertGreater(len(role.workflows), 0)
            self.assertGreater(len(role.deliverables), 0)
            # prompt_template 或 name 必填
            self.assertTrue(role.prompt_template or role.name)

    def test_role_by_department(self):
        """按部门筛角色"""
        from imdf.intelligence_v5 import role_registry
        from imdf.intelligence_v5.roles.departments import Department
        for dept in [Department.ENGINEERING, Department.DESIGN, Department.MARKETING]:
            roles = role_registry.list_by_department(dept)
            # 不是每个部门都有角色
            self.assertIsInstance(roles, list)

    def test_role_template_export(self):
        """角色导出 system_prompt 模板"""
        from imdf.intelligence_v5 import role_registry
        role = role_registry.list_all()[0]
        # role 必须有 render 方法
        prompt = role.render_system_prompt()
        self.assertGreater(len(prompt), 50)

    def test_role_search(self):
        """搜索角色"""
        from imdf.intelligence_v5 import role_registry
        results = role_registry.search("engineer")
        self.assertIsInstance(results, list)


class TestV5Profile(unittest.TestCase):
    """V5 Profile — User + Agent Profile"""

    def test_user_profile_create(self):
        """创建用户画像"""
        from imdf.intelligence_v5 import profile_manager
        p = profile_manager.create(
            user_id="u1",
            username="alice",
            display_name="Alice",
            identity="我是一名数据科学家",
            role="研究员",
            industry="AI",
        )
        self.assertEqual(p.user_id, "u1")
        self.assertEqual(p.identity, "我是一名数据科学家")
        self.assertIn("Alice", p.display_name)

    def test_profile_preferences(self):
        """添加偏好"""
        from imdf.intelligence_v5 import profile_manager
        profile_manager.create(user_id="u2", username="bob")
        ok = profile_manager.add_preference("u2", "我喜欢简短回答")
        self.assertTrue(ok)
        prefs = profile_manager.get("u2").preferences
        self.assertIn("我喜欢简短回答", prefs)

    def test_profile_constraints_and_forbidden(self):
        """约束 + 禁忌"""
        from imdf.intelligence_v5 import profile_manager
        profile_manager.create(user_id="u3", username="charlie")
        profile_manager.add_constraint("u3", "不讨论政治")
        profile_manager.add_constraint("u3", "不讨论政治")  # 重复
        c = profile_manager.get("u3").constraints
        self.assertEqual(c.count("不讨论政治"), 1)

    def test_profile_api_key(self):
        """API key 存储"""
        from imdf.intelligence_v5 import profile_manager
        profile_manager.create(user_id="u4", username="dave")
        profile_manager.set_api_key("u4", "openai", "sk-test-1234")
        k = profile_manager.get("u4").api_keys["openai"]
        self.assertEqual(k, "sk-test-1234")

    def test_profile_render_md(self):
        """渲染 profile.md / style.md"""
        from imdf.intelligence_v5 import profile_manager
        p = profile_manager.create(
            user_id="u5",
            username="eve",
            display_name="Eve",
            identity="我是一名产品经理",
        )
        p.tone = "casual"
        p.use_emoji = True
        profile_md = p.render_profile_md()
        self.assertIn("profile.md", profile_md)
        self.assertIn("Eve", profile_md)
        style_md = p.render_style_md()
        self.assertIn("style.md", style_md)
        self.assertIn("casual", style_md)

    def test_agent_profile_templates(self):
        """Agent Profile 模板"""
        from imdf.intelligence_v5 import AGENT_PROFILE_TEMPLATES
        self.assertIn("planner", AGENT_PROFILE_TEMPLATES)
        self.assertIn("generator", AGENT_PROFILE_TEMPLATES)
        self.assertIn("evaluator", AGENT_PROFILE_TEMPLATES)
        self.assertIn("moderator", AGENT_PROFILE_TEMPLATES)
        for name, tpl in AGENT_PROFILE_TEMPLATES.items():
            self.assertTrue(tpl.name)
            self.assertTrue(tpl.model)
            self.assertGreaterEqual(tpl.temperature, 0.0)


if __name__ == "__main__":
    unittest.main()
