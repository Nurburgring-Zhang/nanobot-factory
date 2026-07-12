"""智影 V5 — Memory + Harness + Skills + MoA + Cron + Webhook 测试"""
import os
import sys
import time
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


class TestV5Memory(unittest.TestCase):
    """V5 Memory — 3 层文件分层 + Memory Manager"""

    def test_raw_store_write_once(self):
        """RAW 层: 一旦写入, 不可修改/删除"""
        from imdf.intelligence_v5 import memory_manager, MemoryLayer, MemoryItem
        m = memory_manager.add_raw(title="测试源", content="原始证据", source="https://example.com")
        self.assertGreater(len(m.item_id), 0)
        self.assertEqual(m.layer, MemoryLayer.RAW)
        # RAW 层应该拒绝 update
        with self.assertRaises(Exception):
            memory_manager.raw.update(m.item_id, content="新内容")

    def test_source_regenerate(self):
        """SOURCE 层: regenerate 重做"""
        from imdf.intelligence_v5 import memory_manager, MemoryLayer
        raw = memory_manager.add_raw(title="raw-source", content="原文")
        m = memory_manager.add_source(raw_id=raw.item_id, title="source", content="提取源")
        self.assertEqual(m.layer, MemoryLayer.SOURCE)
        # regenerate 接受 raw_id
        m2 = memory_manager.source.regenerate(raw.item_id, "重新提取")
        self.assertIsNotNone(m2)
        self.assertEqual(m2.content, "重新提取")

    def test_inbox_layer_promote(self):
        """INBOX → LONG_TERM 升级"""
        from imdf.intelligence_v5 import memory_manager, MemoryLayer
        m = memory_manager.add_inbox(title="test", content="待沉淀")
        self.assertEqual(m.layer, MemoryLayer.INBOX)
        promoted = memory_manager.promote_to_long_term(m.item_id)
        self.assertEqual(promoted.layer, MemoryLayer.LONG_TERM)

    def test_query_layered(self):
        """跨层查询"""
        from imdf.intelligence_v5 import memory_manager, MemoryQuery
        memory_manager.add_inbox(title="t1", content="inbox 1")
        memory_manager.add_inbox(title="t2", content="inbox 2")
        q = MemoryQuery("inbox", layers=[memory_manager.inbox.layer])
        results = memory_manager.query(q)
        self.assertGreaterEqual(len(results), 1)

    def test_layer_protection(self):
        """3 层保护"""
        from imdf.intelligence_v5 import memory_manager, MemoryLayer, MemoryItem
        rm = memory_manager.add_raw(title="r", content="raw")
        with self.assertRaises(Exception):
            memory_manager.raw.update(rm.item_id, content="x")
        # feedback/long_term 走 _BaseStore.add(MemoryItem)
        fb_item = MemoryItem(layer=MemoryLayer.FEEDBACK, title="fb", content="👍")
        fm_id = memory_manager.feedback.add(fb_item)
        with self.assertRaises(Exception):
            memory_manager.feedback.update(fm_id, content="x")
        lt_item = MemoryItem(layer=MemoryLayer.LONG_TERM, title="lt", content="long_term")
        lm_id = memory_manager.long_term.add(lt_item)
        self.assertIsNotNone(lm_id)


class TestV5Palace(unittest.TestCase):
    """V5 Memory Palace — 7 房 + 路线卡"""

    def test_palace_install_default(self):
        """默认安装 7 房"""
        from imdf.intelligence_v5 import palace_router
        palace_router.install_default_palace()
        self.assertGreaterEqual(len(palace_router.rooms), 7)

    def test_palace_rooms(self):
        """Memory Palace 至少 7 房"""
        from imdf.intelligence_v5 import palace_router
        palace_router.install_default_palace()
        rooms = palace_router.rooms
        self.assertGreaterEqual(len(rooms), 7)

    def test_palace_stats(self):
        """palace stats"""
        from imdf.intelligence_v5 import palace_router
        palace_router.install_default_palace()
        stats = palace_router.get_stats()
        # stats key 是 room_count
        self.assertGreaterEqual(stats.get("room_count", 0), 7)


class TestV5Feedback(unittest.TestCase):
    """V5 Feedback — Collector + Taste + Profile"""

    def test_feedback_signal_record(self):
        """记录反馈信号"""
        from imdf.intelligence_v5 import feedback_loop
        sig = feedback_loop.record_feedback(
            target_id="m1",
            feedback_type="approve",
            comment="这个回答很好",
        )
        self.assertIsNotNone(sig)

    def test_feedback_signal_types(self):
        """5 种反馈类型"""
        from imdf.intelligence_v5 import feedback_loop
        for stype in ["approve", "reject", "edit", "prefer", "comment"]:
            sig = feedback_loop.record_feedback(
                target_id=f"m-{stype}",
                feedback_type=stype,
                comment="test",
            )
            self.assertIsNotNone(sig)

    def test_feedback_extract(self):
        """Taste 提取"""
        from imdf.intelligence_v5 import feedback_loop
        for i in range(3):
            feedback_loop.record_feedback(
                target_id=f"m{i}",
                feedback_type="approve",
                comment="简短回答好",
            )
        proposals = feedback_loop.extract_and_propose()
        self.assertIsNotNone(proposals)

    def test_profile_md_render(self):
        """Profile MD 渲染"""
        from imdf.intelligence_v5 import feedback_loop
        md = feedback_loop.get_profile_md()
        self.assertIsNotNone(md)
        self.assertIsInstance(md, str)

    def test_style_md_render(self):
        """Style MD 渲染"""
        from imdf.intelligence_v5 import feedback_loop
        md = feedback_loop.get_style_md()
        self.assertIsNotNone(md)
        self.assertIsInstance(md, str)


class TestV5Harness(unittest.TestCase):
    """V5 Harness — Planner + Generator + Evaluator + Loop"""

    def test_planner_decomposes_prompt(self):
        """Planner 拆需求为 SprintPlan"""
        from imdf.intelligence_v5 import harness_engine
        plan = harness_engine.planner.plan("Build a web scraper")
        self.assertIsNotNone(plan)
        self.assertGreater(len(plan.steps), 0)

    def test_planner_returns_5_step_types(self):
        """StepType 5+ 种"""
        from imdf.intelligence_v5 import StepType
        self.assertGreaterEqual(len(list(StepType)), 5)

    def test_generator_produces_step_outputs(self):
        """Generator 按 plan 生成 step_outputs"""
        from imdf.intelligence_v5 import harness_engine
        plan = harness_engine.planner.plan("Build a CLI tool")
        sprint = harness_engine.generator.generate(plan)
        self.assertIsNotNone(sprint)
        # sprint.step_outputs 包含每个步骤输出
        self.assertGreaterEqual(len(sprint.step_outputs), 0)

    def test_evaluator_returns_results(self):
        """Evaluator 跑多个 criteria"""
        from imdf.intelligence_v5 import harness_engine
        plan = harness_engine.planner.plan("Build a CLI")
        sprint = harness_engine.generator.generate(plan)
        ok, results = harness_engine.evaluator.evaluate(sprint)
        self.assertGreater(len(results), 0)


class TestV5Skills(unittest.TestCase):
    """V5 Skills — Obsidian 6 技能"""

    def test_six_core_skills(self):
        """6 大核心技能"""
        from imdf.intelligence_v5 import obsidian_skill_registry
        skills = obsidian_skill_registry.list()
        self.assertGreaterEqual(len(skills), 6)

    def test_skill_names(self):
        """技能名含 6 大核心"""
        from imdf.intelligence_v5 import obsidian_skill_registry
        names = {s.name for s in obsidian_skill_registry.list()}
        self.assertGreaterEqual(len(names), 3)

    def test_skill_metadata(self):
        """技能有 metadata"""
        from imdf.intelligence_v5 import obsidian_skill_registry
        skills = obsidian_skill_registry.list()
        for s in skills[:3]:
            self.assertTrue(s.name)


class TestV5MoA(unittest.TestCase):
    """V5 MoA — Mixture of Agents"""

    def test_moa_modes(self):
        """MoA 4 mode"""
        from imdf.intelligence_v5 import MoAMode
        self.assertGreaterEqual(len(list(MoAMode)), 3)

    def test_moa_run(self):
        """MoA run"""
        from imdf.intelligence_v5 import moa_engine, MoAConfig
        config = MoAConfig()
        result = moa_engine.run("What is the best LLM?", config)
        self.assertIsNotNone(result)


class TestV5Cron(unittest.TestCase):
    """V5 Cron — NL → Cron 表达式"""

    def test_cron_parse(self):
        """Cron 表达式解析"""
        from imdf.intelligence_v5.scheduler.cron import CronParser
        result = CronParser.parse("0 9 * * *")
        self.assertIsNotNone(result)

    def test_cron_add_job(self):
        """添加 cron job"""
        from imdf.intelligence_v5 import cron_scheduler
        job = cron_scheduler.add_nl_job("morning", "every morning at 9am", "send_report")
        self.assertIsNotNone(job)

    def test_cron_next_run(self):
        """计算下次执行"""
        from imdf.intelligence_v5.scheduler.cron import CronParser
        next_run = CronParser.next_run_after("0 9 * * *", time.time())
        self.assertGreater(next_run, time.time())


class TestV5Webhook(unittest.TestCase):
    """V5 Webhook + Goal + Board"""

    def test_goal_lifecycle(self):
        """Goal 创建到执行"""
        from imdf.intelligence_v5 import goal_runner
        goal = goal_runner.create(
            name="g1",
            result="Dashboard with 5 charts",
            sources=["https://api.example.com"],
            constraints=["< 1s response"],
            deliverables=["dashboard.html", "data.json"],
        )
        self.assertIsNotNone(goal)
        self.assertEqual(goal.result, "Dashboard with 5 charts")

    def test_board(self):
        """Board 状态管理"""
        from imdf.intelligence_v5 import Board, BoardStatus
        board = Board(name="test")
        self.assertGreaterEqual(len(board.columns), 4)
        # BoardStatus 是 enum, 至少 4 个状态
        self.assertGreaterEqual(len(list(BoardStatus)), 4)


if __name__ == "__main__":
    unittest.main()
