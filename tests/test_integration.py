"""全链路集成测试 — 所有引擎 + Master Agent"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestVideoEngine:
    def test_plan_from_text(self):
        from engines.video_engine import VideoEngine
        eng = VideoEngine()
        project = eng.plan("这是一篇关于AI技术的文章。它讲述了深度学习的最新进展。值得关注的是Transformer架构。")
        assert len(project.segments) >= 2
        assert project.total_duration > 0

    def test_select_best_engine(self):
        from engines.video_engine import VideoEngine
        eng = VideoEngine()
        decision = eng.select_best_engine(
            eng.plan("把这篇公众号文章做成短视频")
        )
        assert "primary" in decision

    def test_render_segments(self):
        from engines.video_engine import VideoEngine
        eng = VideoEngine()
        project = eng.plan("测试内容。分三段。每段不同。")
        results = eng.render_segments(project)
        assert len(results) == len(project.segments)

    def test_compose_and_review(self):
        from engines.video_engine import VideoEngine
        eng = VideoEngine()
        project = eng.plan("完整流程测试。")
        eng.render_segments(project)
        path = eng.compose(project)
        assert path.endswith(".mp4")
        review = eng.review(project)
        assert "score" in review

    def test_available_engines(self):
        from engines.video_engine import VideoEngine
        engines = VideoEngine.get_available_engines()
        assert len(engines) >= 4


class TestShortDramaEngine:
    def test_full_pipeline(self):
        from engines.drama_engine import ShortDramaEngine, Character
        eng = ShortDramaEngine()
        chars = [
            Character(name="小明", appearance="戴眼镜的学生", personality="聪明好奇"),
            Character(name="老师", appearance="和蔼的中年人", personality="耐心"),
        ]
        project = eng.run_full_pipeline(
            "一个学生发现了一个秘密", chars, total_shots=10
        )
        assert len(project.shots) == 10
        assert len(project.characters) == 2
        assert project.status == "completed"

    def test_phase_requirement(self):
        from engines.drama_engine import ShortDramaEngine
        eng = ShortDramaEngine()
        project = eng.phase_requirement("校园故事")
        assert project.logline == "校园故事"

    def test_phase_script(self):
        from engines.drama_engine import ShortDramaEngine
        eng = ShortDramaEngine()
        p = eng.phase_requirement("科幻故事")
        p = eng.phase_script(p)
        assert p.script_full != ""

    def test_phase_review(self):
        from engines.drama_engine import ShortDramaEngine, Character
        eng = ShortDramaEngine()
        chars = [Character(name="A"), Character(name="B")]
        p = eng.run_full_pipeline("测试", chars, total_shots=7)
        review = eng.phase_review(p)
        assert "verdict" in review

    def test_phase_storyboard(self):
        from engines.drama_engine import ShortDramaEngine
        eng = ShortDramaEngine()
        p = eng.phase_requirement("冒险故事")
        p = eng.phase_storyboard(p, total_shots=20)
        assert len(p.shots) == 20


class TestWebDesignEngine:
    def test_analyze_landing(self):
        from engines.web_engine import WebDesignEngine
        eng = WebDesignEngine()
        project = eng.analyze("做一个SaaS官网", "landing")
        assert project.design_system.primary_color != ""

    def test_declare_design_system(self):
        from engines.web_engine import WebDesignEngine
        eng = WebDesignEngine()
        project = eng.analyze("科技产品")
        eng.declare_design_system(project, "dark-tech")
        assert project.design_system.font_heading == "Space Grotesk"

    def test_build_v0(self):
        from engines.web_engine import WebDesignEngine
        eng = WebDesignEngine()
        project = eng.analyze("我的作品集")
        v0 = eng.build_v0(project)
        assert "<!DOCTYPE html>" in v0
        assert "%%%" in v0  # 有占位符

    def test_fill_content(self):
        from engines.web_engine import WebDesignEngine
        eng = WebDesignEngine()
        project = eng.analyze("产品页")
        eng.build_v0(project)
        result = eng.fill_content(project, {
            "hero": "<h1>欢迎</h1>",
            "features": "<h2>功能</h2>",
        })
        # 只检查填入了内容
        assert "<h1>欢迎</h1>" in result

    def test_review(self):
        from engines.web_engine import WebDesignEngine
        eng = WebDesignEngine()
        project = eng.analyze("测试")
        eng.build_v0(project)
        review = eng.review(project)
        assert "score" in review

    def test_export(self):
        from engines.web_engine import WebDesignEngine
        eng = WebDesignEngine()
        project = eng.analyze("导出测试")
        eng.build_v0(project)
        path = eng.export(project)
        assert path.endswith(".html")

    def test_style_selection_keyword(self):
        from engines.web_engine import WebDesignEngine
        eng = WebDesignEngine()
        project = eng.analyze("时尚美妆品牌网站")
        # 应匹配到"时尚"风格
        assert project.design_system.primary_color is not None


class TestIntegration:
    """全链路集成测试: 从MasterAgent → 引擎 → Reviewer"""

    def test_master_to_video(self):
        from agent.master_agent import MasterAgent
        from engines.video_engine import VideoEngine
        agent = MasterAgent()
        plan = agent.plan("把这篇技术文章做成短视频")
        assert plan.primary_engine == "html-video"
        
        # 引擎执行
        eng = VideoEngine()
        project = eng.plan("文章内容。技术分享。三分钟讲解。")
        eng.render_segments(project)
        
        # 质量门禁
        review = agent.execute_quality_gate(plan.id, "/tmp/test.mp4")
        assert "score" in review

    def test_master_to_drama(self):
        from agent.master_agent import MasterAgent
        from engines.drama_engine import ShortDramaEngine, Character
        agent = MasterAgent()
        plan = agent.plan("做一个校园短剧")
        assert plan.primary_engine == "story-arc" or plan.primary_engine == "html-video"
        
        chars = [Character(name="小明"), Character(name="小红")]
        eng = ShortDramaEngine()
        project = eng.run_full_pipeline("校园故事", chars, total_shots=8)
        assert project.status == "completed"

    def test_master_to_ppt(self):
        from agent.master_agent import MasterAgent
        agent = MasterAgent()
        plan = agent.plan("做一份季度汇报PPT")
        assert plan.primary_engine == "frontend-slides"

    def test_router_classify_all_types(self):
        from engines.engine_router import EngineRouter
        router = EngineRouter()
        tests = [
            ("帮我做一张信息图", True),
            ("做一个PPT汇报", True),
            ("生成短视频", True),
        ]
        for text, _ in tests:
            decision = router.decide(text)
            assert len(decision.engines) >= 1

    def test_fallback_chain(self):
        from engines.engine_router import EngineRouter
        router = EngineRouter()
        decision = router.decide("做一张科技感海报", prefer_cost="free")
        # free成本的首选引擎应该是HTML截图
        first_engine = decision.engines[0].value
        assert first_engine in ("html-screenshot", "gpt-image-2")
