"""测试套件 — 无限画布核心 + 各引擎 + Master Agent + Nanobot Adapter"""

import pytest
import sys
import os
import json
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent
IMDF_ROOT = PROJECT_ROOT / "backend" / "imdf"
sys.path.insert(0, str(IMDF_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from core.canvas_core import (
    InfiniteCanvas, CanvasState, HistoryManager, SceneGraphManager,
    CanvasElement, ElementType, Scene, Shot, SceneTransition,
)


class TestCanvasCore:
    """无限画布核心测试"""

    def test_canvas_create_element(self):
        canvas = CanvasState()
        el = canvas.add_element(ElementType.IMAGE, "测试图片", x=100, y=100)
        assert el.id in canvas.elements
        assert canvas.elements[el.id].name == "测试图片"
        assert canvas.elements[el.id].x == 100

    def test_canvas_remove_element(self):
        canvas = CanvasState()
        el = canvas.add_element(ElementType.TEXT, "删除测试")
        assert canvas.remove_element(el.id) == True
        assert el.id not in canvas.elements

    def test_canvas_add_scene_and_shot(self):
        canvas = CanvasState()
        scene = canvas.add_scene("第一幕", "开场")
        assert scene.id in canvas.scenes
        
        shot = canvas.add_shot(scene.id, duration=5.0, camera_angle="wide")
        assert shot is not None
        assert len(canvas.scenes[scene.id].shots) == 1

    def test_canvas_snapshot_restore(self):
        canvas = CanvasState()
        canvas.add_element(ElementType.IMAGE, "原图")
        snap = canvas.to_snapshot("测试快照")
        
        canvas.add_element(ElementType.TEXT, "新增元素")
        assert len(canvas.elements) == 2
        
        canvas.restore_snapshot(snap)
        assert len(canvas.elements) == 1
        assert canvas.elements[list(canvas.elements.keys())[0]].name == "原图"

    def test_history_undo_redo(self):
        ic = InfiniteCanvas()
        ic.state.add_element(ElementType.IMAGE, "第一版")
        ic.commit("第一版")
        
        ic.state.add_element(ElementType.TEXT, "第二版")
        ic.commit("第二版")
        
        assert len(ic.state.elements) == 2
        
        ic.undo()
        assert len(ic.state.elements) == 1
        
        ic.redo()
        assert len(ic.state.elements) == 2


class TestMasterAgent:
    """Master Agent测试"""

    def test_content_analysis_image(self):
        from agent.master_agent import ContentAnalyzer
        analyzer = ContentAnalyzer()
        result = analyzer.analyze("帮我生成一张科技感海报")
        # 海报可能是poster或image,接受任何一种
        assert result["content_type"] in ("image", "infographic", "poster")

    def test_content_analysis_ppt(self):
        from agent.master_agent import ContentAnalyzer
        analyzer = ContentAnalyzer()
        result = analyzer.analyze("做一份公司季度汇报PPT")
        assert result["content_type"] == "ppt"

    def test_master_plan_ppt(self):
        from agent.master_agent import MasterAgent
        agent = MasterAgent()
        plan = agent.plan("做一份项目总结PPT")
        assert plan.primary_engine == "frontend-slides"
        assert len(plan.workers) >= 3
        assert plan.status.value == "pending"

    def test_master_plan_video(self):
        from agent.master_agent import MasterAgent
        agent = MasterAgent()
        plan = agent.plan("把这篇公众号文章做成短视频")
        assert plan.primary_engine == "html-video"
        assert plan.content_type in ("video", "mixed")

    def test_quality_gate(self):
        from agent.master_agent import QualityGate, ProductionPlan, TaskStatus
        gate = QualityGate()
        plan = ProductionPlan(content_type="image")
        plan.workers = []  # 空worker列表
        review = gate.review_output("image", "/tmp/test.png", plan)
        assert "score" in review
        assert "verdict" in review


class TestEngineRouter:
    """Engine Router测试"""

    def test_router_decision(self):
        from engines.engine_router import EngineRouter
        router = EngineRouter()
        decision = router.decide("帮我做一份信息图")
        assert len(decision.engines) >= 1
        assert decision.confidence > 0

    def test_router_classify_ppt(self):
        from engines.engine_router import EngineRouter
        router = EngineRouter()
        content_type = router.classify_content("做个PPT汇报")
        assert content_type.value == "ppt"

    def test_router_template_list(self):
        from engines.engine_router import EngineRouter, EngineType
        router = EngineRouter()
        templates = router.get_template_list(EngineType.FRONTEND_SLIDES)
        assert len(templates) >= 10


class TestStoryArcEngine:
    """故事弧引擎测试"""

    def test_list_archetypes(self):
        from engines.story_arc_engine import StoryArcEngine
        engine = StoryArcEngine()
        archetypes = engine.list_archetypes()
        assert len(archetypes) >= 4

    def test_plan_scene(self):
        from engines.story_arc_engine import StoryArcEngine
        engine = StoryArcEngine()
        archetypes = engine.list_archetypes()
        
        # 用第一个总纲规划场景
        arch_result = engine.select_archetype("温暖")
        # select_archetype返回的是{'archetype': {...}, 'reasoning': '...'}
        raw = arch_result["archetype"]
        # 如果没有defined beats, 创建默认的
        if "beats" not in raw or not raw["beats"]:
            raw["beats"] = [{"name": "开场", "emotion": 0.50, "duration_ratio": 0.14},
                           {"name": "发展", "emotion": 0.40, "duration_ratio": 0.16},
                           {"name": "冲突", "emotion": 0.30, "duration_ratio": 0.18},
                           {"name": "转折", "emotion": 0.50, "duration_ratio": 0.12},
                           {"name": "高潮", "emotion": 0.80, "duration_ratio": 0.14},
                           {"name": "闭环", "emotion": 0.65, "duration_ratio": 0.08}]
        plan = engine.plan_scene(
            raw,
            total_shots=7,
            total_duration=120,
            characters=["小明", "老师"],
            locations=["教室", "操场"],
        )
        assert plan.total_shots == 7
        assert len(plan.shots) == 7
        assert plan.continuity_log is not None

    def test_review_and_optimize(self):
        from engines.story_arc_engine import StoryArcEngine
        engine = StoryArcEngine()
        arch_result = engine.select_archetype()
        raw = arch_result["archetype"]
        if "beats" not in raw or not raw["beats"]:
            raw["beats"] = [{"name": "节拍", "emotion": 0.50, "duration_ratio": 1.0}]
        plan = engine.plan_scene(raw, total_shots=5)
        reviewed = engine.review_and_optimize(plan)
        assert len(reviewed.continuity_log) > 0


class TestPPTEngine:
    """PPT引擎测试"""

    def test_select_template(self):
        from engines.ppt_engine import PPTEngine
        engine = PPTEngine()
        result = engine.select_template("科技产品发布会")
        assert "id" in result
        assert "config" in result

    def test_design_token(self):
        from engines.ppt_engine import PPTEngine, SlideSpec, SlideType
        engine = PPTEngine()
        tmpl = engine.select_template("商务汇报")
        token = engine.generate_design_token(tmpl)
        assert token.primary_color != ""
        assert token.font_heading != ""

    def test_generate_html(self):
        from engines.ppt_engine import PPTEngine, SlideSpec, SlideType, DesignToken
        engine = PPTEngine()
        slides = [
            SlideSpec(slide_type=SlideType.COVER, title="测试标题"),
            SlideSpec(slide_type=SlideType.CONTENT, title="内容页", content=["第一点", "第二点"]),
            SlideSpec(slide_type=SlideType.END, title="谢谢"),
        ]
        html = engine.generate_full_html(slides, template_id="clean-business", title="测试")
        assert "<!DOCTYPE html>" in html
        assert "</body></html>" in html
        assert "slide" in html
