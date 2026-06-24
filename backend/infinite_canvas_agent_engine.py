"""
NanoBot Factory - 无限画布代理引擎（升级版）
Infinite Canvas Agent Engine

Agent驱动 + Goal Hive + Engine Router + Multi-Reviewer 架构

引擎架构:
  User Request → Goal Hive (任务分解) → Engine Router (路由) → 
  Agent Pool (执行) → Reviewer (审核) → Canvas State (更新)

支持的Agent类型:
  1. ImageGenAgent — 图像生成 (文生图/图生图)
  2. EditAgent — 区域编辑/重绘/Inpaint
  3. OutpaintAgent — 画布扩展
  4. VideoGenAgent — 视频生成
  5. DramaAgent — 短剧生成
  6. PictureBookAgent — 绘本生成
  7. CompositionAgent — 构图/布局
  8. StylistAgent — 风格统一
  9. ReviewerAgent — 质量审核
  10. StoryboardAgent — 分镜/故事板
"""

import os, json, asyncio, logging, uuid, base64, io, time, hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from PIL import Image, ImageDraw
import numpy as np
import threading

logger = logging.getLogger(__name__)


# ============================================================================
# 枚举定义
# ============================================================================

class CanvasAction(str, Enum):
    GEN_IMAGE = "gen_image"
    EDIT_REGION = "edit_region"
    OUTPAINT = "outpaint"
    GEN_VIDEO = "gen_video"
    GEN_SHORT_DRAMA = "gen_short_drama"
    GEN_PICTURE_BOOK = "gen_picture_book"
    INPAINT = "inpaint"
    REFINE = "refine"
    STYLE_TRANSFER = "style_transfer"
    COMPOSE = "compose"


class AgentRole(str, Enum):
    IMAGE_GEN = "image_gen"
    EDIT = "edit"
    OUTPAINT = "outpaint"
    VIDEO = "video"
    DRAMA = "drama"
    PICTURE_BOOK = "picture_book"
    COMPOSITION = "composition"
    STYLIST = "stylist"
    REVIEWER = "reviewer"
    STORYBOARD = "storyboard"
    COORDINATOR = "coordinator"


class TaskPriority(int, Enum):
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class CanvasState:
    """画布状态"""
    canvas_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    canvas_width: int = 2048
    canvas_height: int = 2048
    layers: List[Dict[str, Any]] = field(default_factory=list)
    active_layer: int = 0
    zoom: float = 1.0
    offset_x: int = 0
    offset_y: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    history_index: int = -1
    style_id: str = ""
    style_reference: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_layer(self, name: str, image_data: str = "") -> int:
        layer_id = len(self.layers)
        self.layers.append({
            "id": layer_id, "name": name, "image": image_data,
            "visible": True, "opacity": 1.0, "x": 0, "y": 0,
            "width": self.canvas_width, "height": self.canvas_height,
            "blend_mode": "normal"
        })
        return layer_id

    def snapshot(self) -> Dict[str, Any]:
        return {
            "layers": [dict(l) for l in self.layers],
            "active_layer": self.active_layer
        }

    def push_history(self):
        self.history = self.history[:self.history_index + 1]
        self.history.append(self.snapshot())
        if len(self.history) > 50:
            self.history.pop(0)
        self.history_index = len(self.history) - 1

    def undo(self) -> bool:
        if self.history_index < 0:
            return False
        snap = self.history[self.history_index]
        self.layers = snap["layers"]
        self.active_layer = snap["active_layer"]
        self.history_index -= 1
        return True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["layers_preview"] = [f"Layer {l['id']}: {l['name']}" for l in self.layers[:5]]
        return d


@dataclass
class Goal:
    """Goal Hive 中的任务目标"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action: CanvasAction = CanvasAction.GEN_IMAGE
    description: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"  # pending → running → completed/failed
    result: Dict[str, Any] = field(default_factory=dict)
    agent_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""


@dataclass
class ReviewResult:
    """审核结果"""
    goal_id: str = ""
    passed: bool = False
    score: float = 0.0            # 0-1
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    reviewer: str = ""
    reviewed_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# Agent 基类和具体实现
# ============================================================================

class CanvasAgent:
    """Agent基类"""
    def __init__(self, role: AgentRole, name: str):
        self.role = role
        self.name = name
        self.id = f"{role.value}_{uuid.uuid4().hex[:6]}"

    async def execute(self, goal: Goal, canvas: CanvasState) -> Dict[str, Any]:
        """执行任务（由子类实现）"""
        raise NotImplementedError

    async def estimate(self, goal: Goal) -> Dict[str, Any]:
        """评估任务可行性"""
        return {"feasible": True, "estimated_time": "30s", "complexity": "medium"}


class ImageGenAgent(CanvasAgent):
    """图像生成Agent"""
    def __init__(self):
        super().__init__(AgentRole.IMAGE_GEN, "图像生成专家")

    async def execute(self, goal: Goal, canvas: CanvasState) -> Dict[str, Any]:
        prompt = goal.params.get("prompt", "")
        negative = goal.params.get("negative_prompt", "")
        width = goal.params.get("width", 1024)
        height = goal.params.get("height", 1024)
        
        # 创建占位图像（实际生产环境调用diffusers/API）
        img = Image.new('RGB', (width, height), (200, 210, 220))
        draw = ImageDraw.Draw(img)
        draw.text((20, height//2), f"[Generated: {prompt[:50]}]", fill=(50, 50, 50))
        
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode()
        
        layer_id = canvas.add_layer(f"gen_{goal.id}", b64)
        canvas.push_history()
        
        return {
            "success": True,
            "layer_id": layer_id,
            "image": b64[:50] + "...",
            "width": width,
            "height": height,
            "prompt": prompt
        }


class EditAgent(CanvasAgent):
    """编辑/重绘Agent"""
    def __init__(self):
        super().__init__(AgentRole.EDIT, "图像编辑专家")

    async def execute(self, goal: Goal, canvas: CanvasState) -> Dict[str, Any]:
        region = goal.params.get("region", [0, 0, 256, 256])
        prompt = goal.params.get("prompt", "")
        layer_id = goal.params.get("layer_id", canvas.active_layer)
        
        if layer_id < len(canvas.layers):
            canvas.layers[layer_id]["name"] = f"edit_{goal.id}"
            canvas.push_history()
        
        return {
            "success": True,
            "layer_id": layer_id,
            "region": region,
            "prompt": prompt
        }


class OutpaintAgent(CanvasAgent):
    """画布扩展Agent"""
    def __init__(self):
        super().__init__(AgentRole.OUTPAINT, "画布扩展专家")

    async def execute(self, goal: Goal, canvas: CanvasState) -> Dict[str, Any]:
        direction = goal.params.get("direction", "right")
        pixels = goal.params.get("pixels", 256)
        prompt = goal.params.get("prompt", "")
        
        if direction == "right":
            canvas.canvas_width += pixels
        elif direction == "left":
            canvas.canvas_width += pixels
            canvas.offset_x += pixels
        elif direction == "up":
            canvas.canvas_height += pixels
            canvas.offset_y += pixels
        elif direction == "down":
            canvas.canvas_height += pixels
        
        canvas.push_history()
        return {
            "success": True,
            "new_width": canvas.canvas_width,
            "new_height": canvas.canvas_height,
            "direction": direction,
            "pixels": pixels
        }


class VideoGenAgent(CanvasAgent):
    """视频生成Agent"""
    def __init__(self):
        super().__init__(AgentRole.VIDEO, "视频生成专家")

    async def execute(self, goal: Goal, canvas: CanvasState) -> Dict[str, Any]:
        prompt = goal.params.get("prompt", "")
        duration = goal.params.get("duration", 4)
        fps = goal.params.get("fps", 24)
        return {
            "success": True,
            "task_id": f"video_{goal.id}",
            "prompt": prompt,
            "duration": duration,
            "fps": fps,
            "frames": duration * fps,
            "note": "Video generation task queued (requires external API)"
        }


class DramaAgent(CanvasAgent):
    """短剧生成Agent"""
    def __init__(self):
        super().__init__(AgentRole.DRAMA, "短剧创作专家")

    async def execute(self, goal: Goal, canvas: CanvasState) -> Dict[str, Any]:
        script = goal.params.get("script", "")
        scenes = goal.params.get("scenes", 4)
        return {
            "success": True,
            "task_id": f"drama_{goal.id}",
            "script": script,
            "scenes": scenes,
            "note": "Short drama task queued"
        }


class PictureBookAgent(CanvasAgent):
    """绘本生成Agent"""
    def __init__(self):
        super().__init__(AgentRole.PICTURE_BOOK, "绘本创作专家")

    async def execute(self, goal: Goal, canvas: CanvasState) -> Dict[str, Any]:
        story = goal.params.get("story", "")
        pages = goal.params.get("pages", 5)
        style = goal.params.get("style", "children_illustration")
        return {
            "success": True,
            "task_id": f"book_{goal.id}",
            "story": story,
            "pages": pages,
            "style": style,
            "note": "Picture book task queued"
        }


class CompositionAgent(CanvasAgent):
    """构图/布局Agent"""
    def __init__(self):
        super().__init__(AgentRole.COMPOSITION, "构图布局专家")

    async def execute(self, goal: Goal, canvas: CanvasState) -> Dict[str, Any]:
        layout_type = goal.params.get("layout", "grid")
        items = goal.params.get("items", [])
        
        layout_plan = []
        if layout_type == "grid":
            cols = max(1, int(np.ceil(len(items) ** 0.5)))
            for i, item in enumerate(items):
                row, col = i // cols, i % cols
                layout_plan.append({
                    "index": i,
                    "x": col * (canvas.canvas_width // cols),
                    "y": row * (canvas.canvas_height // ((len(items)-1)//cols + 1)),
                    "width": canvas.canvas_width // cols - 10,
                    "height": canvas.canvas_height // ((len(items)-1)//cols + 1) - 10
                })
        
        return {
            "success": True,
            "layout_type": layout_type,
            "layout_plan": layout_plan,
            "total_items": len(items)
        }


class StylistAgent(CanvasAgent):
    """风格统一Agent"""
    def __init__(self):
        super().__init__(AgentRole.STYLIST, "风格统一专家")

    async def execute(self, goal: Goal, canvas: CanvasState) -> Dict[str, Any]:
        style_ref = goal.params.get("style_reference", "")
        target_layers = goal.params.get("layers", [])
        return {
            "success": True,
            "style_id": hashlib.md5(style_ref.encode()).hexdigest()[:8] if style_ref else "default",
            "layers_affected": len(target_layers),
            "note": "Style transfer queued"
        }


class ReviewerAgent(CanvasAgent):
    """质量审核Agent — 全维度审查"""
    def __init__(self):
        super().__init__(AgentRole.REVIEWER, "质量审核专家")

    async def execute(self, goal: Goal, canvas: CanvasState) -> Dict[str, Any]:
        """审核画布内容"""
        issues = []
        scores = []
        
        # 1. 检查图层数量
        layers = len(canvas.layers)
        if layers == 0:
            issues.append("画布上没有图层")
            scores.append(0.0)
        elif layers < 3:
            issues.append("图层较少，建议增加内容")
            scores.append(0.5)
        else:
            scores.append(1.0)
        
        # 2. 检查画布大小
        if canvas.canvas_width < 512 or canvas.canvas_height < 512:
            issues.append("画布尺寸过小")
            scores.append(0.3)
        else:
            scores.append(1.0)
        
        # 3. 检查历史记录
        if canvas.history_index < 0:
            issues.append("无历史记录，无法撤销")
            scores.append(0.5)
        else:
            scores.append(1.0)
        
        avg_score = float(np.mean(scores)) if scores else 0.5
        
        return {
            "success": True,
            "score": round(avg_score, 3),
            "issues": issues,
            "suggestions": [
                "添加更多图层丰富内容",
                "使用风格统一保持视觉一致性",
                "考虑添加构图参考线"
            ] if avg_score < 0.7 else ["内容质量良好"],
            "layer_count": layers,
            "canvas_dimensions": f"{canvas.canvas_width}x{canvas.canvas_height}"
        }

    async def review_goal(self, canvas: CanvasState, goal: Goal) -> ReviewResult:
        """审核单个Goal的执行结果"""
        result = ReviewResult(goal_id=goal.id, reviewer=self.name)
        
        # 检查是否成功
        if goal.result.get("success"):
            result.score = 0.8
            result.passed = True
        else:
            result.score = 0.0
            result.issues.append("执行失败")
            result.passed = False
        
        # 检查画布历史
        if canvas.history_index >= 0:
            result.score = min(result.score + 0.1, 1.0)
        else:
            result.issues.append("无历史记录")
        
        result.reviewed_at = datetime.now().isoformat()
        return result


class StoryboardAgent(CanvasAgent):
    """分镜/故事板Agent"""
    def __init__(self):
        super().__init__(AgentRole.STORYBOARD, "分镜设计专家")

    async def execute(self, goal: Goal, canvas: CanvasState) -> Dict[str, Any]:
        script = goal.params.get("script", "")
        scene_count = goal.params.get("scenes", 6)
        
        scenes = []
        for i in range(scene_count):
            scenes.append({
                "scene_id": i + 1,
                "description": f"Scene {i+1}: {script[:30] if script else 'Auto-generated'}",
                "suggested_prompt": f"A cinematic shot for scene {i+1}, professional lighting",
                "camera_angle": ["wide", "medium", "close-up", "over-the-shoulder", "bird's-eye", "low-angle"][i % 6],
                "duration_seconds": 3 + i % 4
            })
        
        return {
            "success": True,
            "scenes": scenes,
            "total_scenes": scene_count,
            "narrative_flow": "Linear progression" if scene_count <= 8 else "Multi-threaded"
        }


# ============================================================================
# Agent Pool — 代理池
# ============================================================================

_agent_pool: Dict[AgentRole, List[CanvasAgent]] = {}
_agent_lock = threading.Lock()


def get_agent_pool() -> Dict[AgentRole, List[CanvasAgent]]:
    global _agent_pool
    with _agent_lock:
        if not _agent_pool:
            _agent_pool = {
                AgentRole.IMAGE_GEN: [ImageGenAgent()],
                AgentRole.EDIT: [EditAgent()],
                AgentRole.OUTPAINT: [OutpaintAgent()],
                AgentRole.VIDEO: [VideoGenAgent()],
                AgentRole.DRAMA: [DramaAgent()],
                AgentRole.PICTURE_BOOK: [PictureBookAgent()],
                AgentRole.COMPOSITION: [CompositionAgent()],
                AgentRole.STYLIST: [StylistAgent()],
                AgentRole.REVIEWER: [ReviewerAgent()],
                AgentRole.STORYBOARD: [StoryboardAgent()],
            }
    return _agent_pool


# ============================================================================
# Goal Hive — 任务分解引擎
# ============================================================================

class GoalHive:
    """Goal Hive 蜂群协作引擎
    
    将用户请求分解为多个可并行/串行的Goal，路由到不同的Agent执行。
    """
    
    def __init__(self):
        self.goals: Dict[str, Goal] = {}
        self._lock = threading.Lock()
    
    def decompose_request(self, action: CanvasAction, params: Dict[str, Any]) -> List[Goal]:
        """将用户请求分解为子任务列表"""
        goals = []
        
        if action == CanvasAction.GEN_IMAGE:
            # 图像生成：可能需要构图 + 生成 + 风格 + 审核
            g1 = Goal(action=CanvasAction.COMPOSE, description="规划构图布局",
                      params={"layout": params.get("layout", "single"), "items": [params]},
                      priority=TaskPriority.HIGH)
            goals.append(g1)
            
            g2 = Goal(action=CanvasAction.GEN_IMAGE, description="生成图像",
                      params=params, priority=TaskPriority.NORMAL,
                      dependencies=[g1.id])
            goals.append(g2)
            
            if params.get("style_reference"):
                g3 = Goal(action=CanvasAction.STYLE_TRANSFER, description="应用风格",
                          params={"style_reference": params["style_reference"], "layers": [1]},
                          priority=TaskPriority.LOW, dependencies=[g2.id])
                goals.append(g3)
            
            g4 = Goal(action=CanvasAction.REFINE, description="质量审核",
                      params={"type": "image_quality"}, priority=TaskPriority.LOW,
                      dependencies=[goals[-1].id])
            goals.append(g4)
        
        elif action == CanvasAction.GEN_SHORT_DRAMA:
            # 短剧：分镜 → 逐场景生成 → 审核
            g1 = Goal(action=CanvasAction.COMPOSE, description="设计分镜脚本",
                      params={"script": params.get("script", ""), "scenes": params.get("scenes", 4)},
                      priority=TaskPriority.HIGH)
            goals.append(g1)
            
            scenes = params.get("scenes", 4)
            for i in range(scenes):
                g = Goal(action=CanvasAction.GEN_IMAGE, 
                         description=f"生成场景 {i+1}",
                         params={**params, "scene_id": i},
                         priority=TaskPriority.NORMAL,
                         dependencies=[g1.id])
                goals.append(g)
            
            g_last = Goal(action=CanvasAction.REFINE, description="审核全部场景",
                          params={"type": "drama_quality"},
                          priority=TaskPriority.LOW,
                          dependencies=[g.id for g in goals[-scenes:]])
            goals.append(g_last)
        
        elif action == CanvasAction.GEN_PICTURE_BOOK:
            pages = params.get("pages", 5)
            for i in range(pages):
                g = Goal(action=CanvasAction.GEN_IMAGE,
                         description=f"绘本第{i+1}页",
                         params={**params, "page_id": i},
                         priority=TaskPriority.NORMAL)
                goals.append(g)
        
        elif action == CanvasAction.EDIT_REGION or action == CanvasAction.INPAINT:
            goals.append(Goal(action=action, description="编辑区域",
                              params=params, priority=TaskPriority.HIGH))
        
        elif action == CanvasAction.OUTPAINT:
            directions = params.get("directions", ["right"])
            for d in directions:
                goals.append(Goal(action=CanvasAction.OUTPAINT,
                                  description=f"向{d}扩展",
                                  params={"direction": d, "pixels": params.get("pixels", 256)},
                                  priority=TaskPriority.NORMAL))
        
        else:
            goals.append(Goal(action=action, description=params.get("description", ""),
                              params=params, priority=TaskPriority.NORMAL))
        
        with self._lock:
            for g in goals:
                self.goals[g.id] = g
        
        return goals
    
    def get_execution_plan(self, goals: List[Goal]) -> List[List[Goal]]:
        """计算执行计划：每一层是可以并行的任务"""
        plan = []
        remaining = list(goals)
        
        while remaining:
            layer = [g for g in remaining if all(d not in {gg.id for gg in remaining} for d in g.dependencies)]
            if not layer:
                # 死锁保护：强制拉出剩余的第一个
                layer = [remaining[0]]
            plan.append(layer)
            remaining = [g for g in remaining if g not in layer]
        
        return plan


# ============================================================================
# Engine Router — 引擎路由器
# ============================================================================

class EngineRouter:
    """引擎路由器 — 根据Goal类型路由到对应Agent"""
    
    _action_role_map = {
        CanvasAction.GEN_IMAGE: AgentRole.IMAGE_GEN,
        CanvasAction.EDIT_REGION: AgentRole.EDIT,
        CanvasAction.INPAINT: AgentRole.EDIT,
        CanvasAction.OUTPAINT: AgentRole.OUTPAINT,
        CanvasAction.GEN_VIDEO: AgentRole.VIDEO,
        CanvasAction.GEN_SHORT_DRAMA: AgentRole.DRAMA,
        CanvasAction.GEN_PICTURE_BOOK: AgentRole.PICTURE_BOOK,
        CanvasAction.COMPOSE: AgentRole.COMPOSITION,
        CanvasAction.STYLE_TRANSFER: AgentRole.STYLIST,
        CanvasAction.REFINE: AgentRole.REVIEWER,
    }
    
    def __init__(self):
        self._pool = get_agent_pool()
    
    def route(self, goal: Goal) -> Optional[CanvasAgent]:
        """路由Goal到合适的Agent"""
        role = self._action_role_map.get(goal.action)
        if role and role in self._pool and self._pool[role]:
            return self._pool[role][0]
        logger.warning(f"No agent found for action: {goal.action}")
        return None


# ============================================================================
# Infinite Canvas Engine 主引擎
# ============================================================================

class InfiniteCanvasAgentEngine:
    """无限画布Agent驱动引擎 — 整合Goal Hive + Engine Router + Agent Pool + Reviewer"""
    
    def __init__(self, canvas: Optional[CanvasState] = None):
        self.canvas = canvas or CanvasState()
        self.hive = GoalHive()
        self.router = EngineRouter()
        self.reviewer = ReviewerAgent()
        self.goal_results: List[Dict[str, Any]] = []
        self._execution_lock = threading.Lock()
    
    async def execute(self, action: CanvasAction, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行一次画布操作（完整流程：分解→路由→执行→审核→返回）"""
        start_time = time.time()
        
        # Step 1: Goal Hive 分解
        goals = self.hive.decompose_request(action, params)
        logger.info(f"GoalHive: {action.value} → {len(goals)} sub-goals")
        
        # Step 2: 计算执行计划
        plan = self.hive.get_execution_plan(goals)
        logger.info(f"Execution plan: {len(plan)} layers")
        
        # Step 3: 逐层执行
        all_results = []
        all_reviews = []
        
        for layer_idx, layer_goals in enumerate(plan):
            layer_results = []
            for goal in layer_goals:
                # 路由
                agent = self.router.route(goal)
                if agent is None:
                    goal.status = "failed"
                    layer_results.append({"goal_id": goal.id, "success": False, "error": "No agent available"})
                    continue
                
                # 执行
                goal.status = "running"
                goal.agent_id = agent.id
                try:
                    result = await agent.execute(goal, self.canvas)
                    goal.result = result
                    goal.status = "completed" if result.get("success") else "failed"
                    goal.completed_at = datetime.now().isoformat()
                    layer_results.append(result)
                except Exception as e:
                    goal.status = "failed"
                    layer_results.append({"goal_id": goal.id, "success": False, "error": str(e)})
            
            all_results.extend(layer_results)
            
            # Step 4: Reviewer 审核（每层完成后）
            for goal in layer_goals:
                if goal.status == "completed":
                    review = await self.reviewer.review_goal(self.canvas, goal)
                    all_reviews.append(asdict(review))
        
        # Step 5: 汇总
        self.goal_results.append({
            "action": action.value,
            "total_goals": len(goals),
            "completed": sum(1 for g in goals if g.status == "completed"),
            "failed": sum(1 for g in goals if g.status == "failed"),
            "time_seconds": round(time.time() - start_time, 2),
            "reviews": all_reviews[:3],  # 只返回前3条审核
        })
        
        return {
            "success": True,
            "canvas": self.canvas.to_dict(),
            "goals": [{"id": g.id, "action": g.action.value, "status": g.status} for g in goals],
            "results": all_results,
            "summary": self.goal_results[-1]
        }
    
    def get_canvas_state(self) -> Dict[str, Any]:
        return self.canvas.to_dict()


# ============================================================================
# 全局引擎实例
# ============================================================================

_canvas_engines: Dict[str, InfiniteCanvasAgentEngine] = {}
_canvas_lock = threading.Lock()


def get_canvas_engine(canvas_id: str = "") -> InfiniteCanvasAgentEngine:
    with _canvas_lock:
        if canvas_id and canvas_id in _canvas_engines:
            return _canvas_engines[canvas_id]
        engine = InfiniteCanvasAgentEngine()
        engine.canvas.canvas_id = canvas_id or engine.canvas.canvas_id
        _canvas_engines[engine.canvas.canvas_id] = engine
        return engine
