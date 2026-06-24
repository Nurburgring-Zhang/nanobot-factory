"""Skill system routes — CRUD + toggle + import"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_state_and_skill():
    """Lazy import to avoid circular dependency"""
    from server import state, Skill
    return state, Skill


@router.get("/api/skills")
async def get_skills():
    """Get all skills"""
    state, _ = _get_state_and_skill()
    return [skill.model_dump() for skill in state.skills.values()]


@router.get("/api/skills/{skill_id}")
async def get_skill(skill_id: str):
    """Get specific skill"""
    state, _ = _get_state_and_skill()
    skills = state.skills
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skills[skill_id].dict()


@router.post("/api/skills/{skill_id}/toggle")
async def toggle_skill(skill_id: str):
    """Toggle skill enabled/disabled"""
    state, _ = _get_state_and_skill()
    skills = state.skills
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill = skills[skill_id]
    skill.enabled = not skill.enabled
    return {"enabled": skill.enabled}


@router.post("/api/skills")
async def create_skill(request: Dict[str, Any]):
    """Create a new skill"""
    state, Skill = _get_state_and_skill()
    skill_id = request.get("id", request.get("name", "").lower().replace(" ", "_"))
    skill = Skill(**{
        "id": skill_id,
        "name": request.get("name", ""),
        "description": request.get("description", ""),
        "enabled": request.get("enabled", True),
        "author": request.get("author", "User"),
        "version": request.get("version", "1.0.0"),
        "category": request.get("category", "其他"),
        "config": request.get("config", {}),
    })
    state._skills[skill_id] = skill
    return skill.dict()


@router.put("/api/skills/{skill_id}")
async def update_skill(skill_id: str, request: Dict[str, Any]):
    """Update an existing skill"""
    state, _ = _get_state_and_skill()
    skills = state._skills
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill = skills[skill_id]
    for field in ("name", "description", "enabled", "prompt_template"):
        if field in request:
            setattr(skill, field, request[field])
    if "config" in request:
        skill.config = request["config"]
    return skill.dict()


@router.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: str):
    """Delete a skill"""
    state, _ = _get_state_and_skill()
    skills = state._skills
    if skill_id not in skills:
        raise HTTPException(status_code=404, detail="Skill not found")
    del state._skills[skill_id]
    return {"success": True}


@router.post("/api/skills/import")
async def import_skill(request: Dict[str, Any]):
    """Import a skill from data"""
    state, Skill = _get_state_and_skill()
    skill_id = request.get("id", request.get("name", "").lower().replace(" ", "_"))
    skill = Skill(**{
        "id": skill_id,
        "name": request.get("name", ""),
        "description": request.get("description", ""),
        "enabled": request.get("enabled", True),
        "author": request.get("author", "User"),
        "version": request.get("version", "1.0.0"),
        "category": request.get("category", "其他"),
        "config": request.get("config", {}),
    })
    state._skills[skill_id] = skill
    return skill.dict()
