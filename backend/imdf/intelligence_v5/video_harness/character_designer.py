"""智影 V5 — 角色/场景/道具 设计师

迁移自 Pavo + 剧大虾: 角色、场景、道具 → 资产管理 → 跨集一致
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Character:
    """角色 — 跨集一致的资产"""

    name: str
    character_id: str = field(default_factory=lambda: f"ch-{uuid.uuid4().hex[:8]}")
    role: str = "supporting"  # protagonist / antagonist / supporting / extra
    description: str = ""
    appearance: str = ""  # 外貌描述
    personality: str = ""  # 性格
    voice_style: str = ""  # 声音风格
    reference_image_prompt: str = ""  # 用于生成参考图的 prompt
    reference_image_url: str = ""
    reference_seed: int = 0  # 一致性种子
    age: str = ""
    gender: str = ""
    project_id: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "character_id": self.character_id,
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "appearance": self.appearance,
            "personality": self.personality,
            "voice_style": self.voice_style,
            "reference_image_prompt": self.reference_image_prompt,
            "reference_image_url": self.reference_image_url,
            "reference_seed": self.reference_seed,
            "age": self.age,
            "gender": self.gender,
            "project_id": self.project_id,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Scene:
    """场景"""

    name: str
    scene_id: str = field(default_factory=lambda: f"sc-{uuid.uuid4().hex[:8]}")
    description: str = ""
    location_type: str = ""  # "indoor" | "outdoor" | "abstract" | "fantasy"
    lighting: str = ""  # "natural" | "warm" | "cold" | "dramatic" | "neon"
    time_of_day: str = ""  # "morning" | "noon" | "evening" | "night" | "twilight"
    reference_image_prompt: str = ""
    reference_image_url: str = ""
    reference_seed: int = 0
    project_id: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "name": self.name,
            "description": self.description,
            "location_type": self.location_type,
            "lighting": self.lighting,
            "time_of_day": self.time_of_day,
            "reference_image_prompt": self.reference_image_prompt,
            "reference_image_url": self.reference_image_url,
            "project_id": self.project_id,
            "tags": self.tags,
            "created_at": self.created_at,
        }


@dataclass
class Prop:
    """道具"""

    name: str
    prop_id: str = field(default_factory=lambda: f"pr-{uuid.uuid4().hex[:8]}")
    description: str = ""
    category: str = "object"  # "weapon" | "tool" | "document" | "food" | "vehicle" | "object"
    reference_image_prompt: str = ""
    reference_image_url: str = ""
    project_id: str = ""
    created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prop_id": self.prop_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "reference_image_prompt": self.reference_image_prompt,
            "reference_image_url": self.reference_image_url,
            "project_id": self.project_id,
            "created_at": self.created_at,
        }


class CharacterDesigner:
    """角色/场景/道具 设计师 — 项目资产管理"""

    def __init__(self):
        self.characters: Dict[str, Character] = {}
        self.scenes: Dict[str, Scene] = {}
        self.props: Dict[str, Prop] = {}

    def add_character(
        self,
        name: str,
        role: str = "supporting",
        description: str = "",
        appearance: str = "",
        personality: str = "",
        age: str = "",
        gender: str = "",
        project_id: str = "",
        tags: Optional[List[str]] = None,
        reference_image_prompt: str = "",
    ) -> Character:
        c = Character(
            name=name,
            role=role,
            description=description,
            appearance=appearance,
            personality=personality,
            age=age,
            gender=gender,
            project_id=project_id,
            tags=tags or [],
            reference_image_prompt=reference_image_prompt,
            reference_seed=hash(name) & 0x7FFFFFFF,  # 稳定 seed
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.characters[c.character_id] = c
        return c

    def add_scene(
        self,
        name: str,
        description: str = "",
        location_type: str = "",
        lighting: str = "",
        time_of_day: str = "",
        project_id: str = "",
        reference_image_prompt: str = "",
    ) -> Scene:
        s = Scene(
            name=name,
            description=description,
            location_type=location_type,
            lighting=lighting,
            time_of_day=time_of_day,
            project_id=project_id,
            reference_image_prompt=reference_image_prompt,
            reference_seed=hash(name) & 0x7FFFFFFF,
            created_at=time.time(),
        )
        self.scenes[s.scene_id] = s
        return s

    def add_prop(
        self,
        name: str,
        description: str = "",
        category: str = "object",
        project_id: str = "",
        reference_image_prompt: str = "",
    ) -> Prop:
        p = Prop(
            name=name,
            description=description,
            category=category,
            project_id=project_id,
            reference_image_prompt=reference_image_prompt,
            created_at=time.time(),
        )
        self.props[p.prop_id] = p
        return p

    def get_character(self, character_id: str) -> Optional[Character]:
        return self.characters.get(character_id)

    def list_characters(self, project_id: str = "") -> List[Character]:
        if project_id:
            return [c for c in self.characters.values() if c.project_id == project_id]
        return list(self.characters.values())

    def list_scenes(self, project_id: str = "") -> List[Scene]:
        if project_id:
            return [s for s in self.scenes.values() if s.project_id == project_id]
        return list(self.scenes.values())

    def list_props(self, project_id: str = "") -> List[Prop]:
        if project_id:
            return [p for p in self.props.values() if p.project_id == project_id]
        return list(self.props.values())

    def get_stats(self) -> Dict[str, Any]:
        return {
            "characters": len(self.characters),
            "scenes": len(self.scenes),
            "props": len(self.props),
            "total": len(self.characters) + len(self.scenes) + len(self.props),
        }
