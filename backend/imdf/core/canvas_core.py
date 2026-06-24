"""
Infinite Multimodal Data Foundry — Infinite Canvas Core
=============================================
Event-level canvas state management + scene graph + edit history

Responsibilities:
  Manage all canvas elements (id/type/position/content/properties/engine)
  Multi-scene/multi-shot timeline organization
  Edit history with checkpoints (undo/redo/version branching/auto-save every 5 steps)
"""

import uuid
import json
import copy
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum


class ElementType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    TEXT = "text"
    SLIDE = "slide"
    SHOT = "shot"
    AUDIO = "audio"
    SHAPE = "shape"
    LAYER = "layer"
    STORYBOARD = "storyboard"
    CHARACTER = "character"


class SceneTransition(str, Enum):
    CUT = "cut"
    FADE_IN = "fade_in"
    FADE_OUT = "fade_out"
    DISSOLVE = "dissolve"
    WIPE = "wipe"
    SLIDE = "slide"


@dataclass
class CanvasElement:
    id: str = field(default_factory=lambda: f"el_{uuid.uuid4().hex[:8]}")
    el_type: ElementType = ElementType.IMAGE
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 512.0
    height: float = 512.0
    rotation: float = 0.0
    z_index: int = 0
    opacity: float = 1.0
    visible: bool = True
    content: Dict[str, Any] = field(default_factory=dict)
    properties: Dict[str, Any] = field(default_factory=dict)
    attached_engine: str = ""  # 哪个引擎生成的这个元素
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["el_type"] = self.el_type.value
        return d


@dataclass
class Shot:
    """镜头 — 场景的基本单位"""
    id: str = field(default_factory=lambda: f"shot_{uuid.uuid4().hex[:8]}")
    name: str = ""
    duration: float = 5.0  # 秒
    camera_angle: str = "medium"  # wide/medium/closeup/dutch
    camera_movement: str = "static"  # static/pan/tilt/zoom/track
    elements: List[CanvasElement] = field(default_factory=list)
    narration: str = ""  # 口播文本
    subtitle: str = ""  # 字幕
    transition_out: SceneTransition = SceneTransition.CUT
    bgm_cue: str = ""  # 背景音乐提示
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["transition_out"] = self.transition_out.value
        d["elements"] = [e.to_dict() for e in self.elements]
        return d


@dataclass
class Scene:
    """场景 — 由多个镜头组成"""
    id: str = field(default_factory=lambda: f"scene_{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    shots: List[Shot] = field(default_factory=list)
    order: int = 0
    state: Dict[str, Any] = field(default_factory=dict)
    # 场景级状态快照（角色位置/道具/环境）
    character_positions: Dict[str, List[float]] = field(default_factory=dict)
    prop_states: Dict[str, Any] = field(default_factory=dict)
    environment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["shots"] = [s.to_dict() for s in self.shots]
        return d


@dataclass
class CanvasSnapshot:
    """画布快照 — 用于undo/redo和版本管理"""
    id: str = field(default_factory=lambda: f"snap_{uuid.uuid4().hex[:8]}")
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    elements: List[CanvasElement] = field(default_factory=list)
    scenes: List[Scene] = field(default_factory=list)
    active_scene_id: str = ""
    canvas_width: int = 2048
    canvas_height: int = 2048
    zoom: float = 1.0
    offset_x: int = 0
    offset_y: int = 0
    description: str = ""


class CanvasState:
    """
    画布状态管理器
    
    管理画布上的所有元素、场景、镜头。
    支持多层操作、元素选择、区域管理。
    """

    def __init__(self, width: int = 2048, height: int = 2048):
        self.canvas_width = width
        self.canvas_height = height
        self.elements: Dict[str, CanvasElement] = {}
        self.scenes: Dict[str, Scene] = {}
        self.active_scene_id: str = ""
        self.zoom: float = 1.0
        self.offset_x: int = 0
        self.offset_y: int = 0
        self._next_z = 0

    def add_element(self, el_type: ElementType, name: str = "",
                    x: float = 0, y: float = 0,
                    width: float = 512, height: float = 512,
                    content: Dict = None, properties: Dict = None,
                    scene_id: str = "") -> CanvasElement:
        """在画布上添加元素"""
        el = CanvasElement(
            el_type=el_type, name=name,
            x=x, y=y, width=width, height=height,
            z_index=self._next_z,
            content=content or {},
            properties=properties or {},
        )
        self.elements[el.id] = el
        self._next_z += 1
        
        # 如果指定了场景，加入场景的当前镜头
        if scene_id and scene_id in self.scenes:
            scene = self.scenes[scene_id]
            if scene.shots:
                scene.shots[-1].elements.append(el)
        
        return el

    def remove_element(self, el_id: str) -> bool:
        """移除元素"""
        if el_id in self.elements:
            del self.elements[el_id]
            # 从所有场景的镜头中移除
            for scene in self.scenes.values():
                for shot in scene.shots:
                    shot.elements = [e for e in shot.elements if e.id != el_id]
            return True
        return False

    def get_element(self, el_id: str) -> Optional[CanvasElement]:
        return self.elements.get(el_id)

    def add_scene(self, name: str = "", description: str = "") -> Scene:
        """添加场景"""
        scene = Scene(name=name, description=description, order=len(self.scenes))
        self.scenes[scene.id] = scene
        if not self.active_scene_id:
            self.active_scene_id = scene.id
        return scene

    def add_shot(self, scene_id: str, duration: float = 5.0,
                 camera_angle: str = "medium",
                 narration: str = "") -> Optional[Shot]:
        """在场景中添加镜头"""
        if scene_id not in self.scenes:
            return None
        shot = Shot(
            duration=duration,
            camera_angle=camera_angle,
            narration=narration,
        )
        self.scenes[scene_id].shots.append(shot)
        return shot

    def to_snapshot(self, description: str = "") -> CanvasSnapshot:
        """创建当前画布的快照(深拷贝)"""
        return CanvasSnapshot(
            elements=copy.deepcopy(list(self.elements.values())),
            scenes=copy.deepcopy(list(self.scenes.values())),
            active_scene_id=self.active_scene_id,
            canvas_width=self.canvas_width,
            canvas_height=self.canvas_height,
            zoom=self.zoom,
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            description=description,
        )

    def restore_snapshot(self, snap: CanvasSnapshot):
        """从快照恢复"""
        self.elements = {e.id: e for e in snap.elements}
        self.scenes = {s.id: s for s in snap.scenes}
        self.active_scene_id = snap.active_scene_id
        self.canvas_width = snap.canvas_width
        self.canvas_height = snap.canvas_height
        self.zoom = snap.zoom
        self.offset_x = snap.offset_x
        self.offset_y = snap.offset_y

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "zoom": self.zoom,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "active_scene_id": self.active_scene_id,
            "elements": {k: v.to_dict() for k, v in self.elements.items()},
            "scenes": {k: v.to_dict() for k, v in self.scenes.items()},
        }


class HistoryManager:
    """
    编辑历史管理器
    
    Supported: undo/redo / 检查点(自动每5步) / 版本分支
    """

    def __init__(self, max_history: int = 100):
        self._undo_stack: List[CanvasSnapshot] = []
        self._redo_stack: List[CanvasSnapshot] = []
        self._checkpoints: Dict[str, CanvasSnapshot] = {}
        self._branches: Dict[str, List[CanvasSnapshot]] = {}
        self._max_history = max_history
        self._step_count = 0

    def commit(self, canvas: CanvasState, description: str = "") -> str:
        """提交当前状态到历史栈"""
        # 创建当前状态的快照
        snap = canvas.to_snapshot(description)
        snap_id = snap.id
        
        # 移除与上一次完全相同的快照(用哈希比较避免漏掉元素内容变化)
        if self._undo_stack:
            last = self._undo_stack[-1]
            last_hash = json.dumps({e.id: asdict(e) for e in last.elements}, sort_keys=True)
            curr_hash = json.dumps({e.id: asdict(e) for e in snap.elements}, sort_keys=True)
            if last_hash == curr_hash:
                return last.id  # 无变化，不提交
        
        self._undo_stack.append(snap)
        self._redo_stack.clear()
        self._step_count += 1

        # 自动检查点: 每5步
        if self._step_count % 5 == 0:
            self._checkpoints[snap_id] = snap

        # 限制历史长度
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)

        return snap_id

    def undo(self, canvas: CanvasState) -> bool:
        """撤销 — 回到上一步"""
        if len(self._undo_stack) < 2:
            return False
        # 当前状态入redo
        current = canvas.to_snapshot()
        self._redo_stack.append(current)
        # pop两次: 第一次是当前状态,第二次才是要恢复的上一个状态
        self._undo_stack.pop()  # 当前
        previous = self._undo_stack[-1]  # 上一个(不pop,保留)
        canvas.restore_snapshot(previous)
        return True

    def redo(self, canvas: CanvasState) -> bool:
        """重做 — 回到撤销前"""
        if not self._redo_stack:
            return False
        current = canvas.to_snapshot()
        self._undo_stack.append(current)
        next_snap = self._redo_stack.pop()
        canvas.restore_snapshot(next_snap)
        return True

    def create_checkpoint(self, canvas: CanvasState, name: str) -> str:
        """创建命名检查点(版本分支)"""
        snap = canvas.to_snapshot(f"checkpoint: {name}")
        self._checkpoints[snap.id] = snap
        
        # 版本分支
        if name not in self._branches:
            self._branches[name] = []
        self._branches[name].append(snap)
        
        return snap.id

    def restore_checkpoint(self, canvas: CanvasState, snap_id: str) -> bool:
        """恢复到指定检查点"""
        if snap_id in self._checkpoints:
            canvas.restore_snapshot(self._checkpoints[snap_id])
            return True
        return False

    def get_checkpoints(self) -> List[Dict[str, str]]:
        """获取所有检查点列表"""
        return [
            {"id": sid, "desc": snap.description, "timestamp": snap.timestamp}
            for sid, snap in self._checkpoints.items()
        ]

    def get_stats(self) -> Dict[str, int]:
        return {
            "undo_stack": len(self._undo_stack),
            "redo_stack": len(self._redo_stack),
            "checkpoints": len(self._checkpoints),
            "branches": len(self._branches),
            "total_steps": self._step_count,
        }


class SceneGraphManager:
    """
    场景图管理器
    
    管理多场景/多镜头的结构、切换规则、故事状态
    """

    def __init__(self, canvas: CanvasState):
        self.canvas = canvas

    def create_scene_sequence(self, names: List[str]) -> List[str]:
        """批量创建场景序列"""
        scene_ids = []
        for i, name in enumerate(names):
            scene = self.canvas.add_scene(name=name)
            scene.order = i
            scene_ids.append(scene.id)
        return scene_ids

    def link_scenes(self, from_scene_id: str, to_scene_id: str,
                    transition: SceneTransition = SceneTransition.CUT):
        """链接两个场景(定义切换)"""
        # 为from_scene的最后一个镜头设置转场
        if from_scene_id in self.canvas.scenes:
            scene = self.canvas.scenes[from_scene_id]
            if scene.shots:
                scene.shots[-1].transition_out = transition

    def get_timeline(self) -> List[Dict[str, Any]]:
        """获取扁平化时间线(所有镜头按场景顺序排列)"""
        timeline = []
        sorted_scenes = sorted(
            self.canvas.scenes.values(), key=lambda s: s.order
        )
        for scene in sorted_scenes:
            for shot in scene.shots:
                timeline.append({
                    "scene_id": scene.id,
                    "scene_name": scene.name,
                    "shot_id": shot.id,
                    "shot_name": shot.name,
                    "duration": shot.duration,
                    "narration": shot.narration,
                    "camera_angle": shot.camera_angle,
                    "transition": shot.transition_out.value,
                })
        return timeline

    def total_duration(self) -> float:
        """计算总时长(所有镜头时长之和)"""
        total = 0.0
        for scene in self.canvas.scenes.values():
            for shot in scene.shots:
                total += shot.duration
        return total

    def propagate_state(self, from_scene_id: str, to_scene_id: str):
        """传播场景状态(角色位置/道具/环境)"""
        if from_scene_id in self.canvas.scenes and to_scene_id in self.canvas.scenes:
            from_scene = self.canvas.scenes[from_scene_id]
            to_scene = self.canvas.scenes[to_scene_id]
            to_scene.character_positions = dict(from_scene.character_positions)
            to_scene.prop_states = dict(from_scene.prop_states)
            to_scene.environment = from_scene.environment


class InfiniteCanvas:
    """
    无限画布 — 顶层管理器
    
    整合 CanvasState + HistoryManager + SceneGraphManager
    """

    def __init__(self, width: int = 2048, height: int = 2048):
        self.state = CanvasState(width, height)
        self.history = HistoryManager()
        self.scene_graph = SceneGraphManager(self.state)

    def commit(self, description: str = "") -> str:
        """提交当前状态到历史"""
        return self.history.commit(self.state, description)

    def undo(self) -> bool:
        return self.history.undo(self.state)

    def redo(self) -> bool:
        return self.history.redo(self.state)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canvas": self.state.to_dict(),
            "history": self.history.get_stats(),
            "timeline": self.scene_graph.get_timeline(),
            "total_duration_seconds": self.scene_graph.total_duration(),
        }
