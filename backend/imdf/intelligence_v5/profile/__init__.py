"""智影 V5 — Profile 子包: 用户画像/Agent Profile/团队 Profile"""
from .user_profile import UserProfile, ProfileManager, profile_manager
from .agent_profile import AgentProfileTemplate, AGENT_PROFILE_TEMPLATES

__all__ = [
    "UserProfile",
    "ProfileManager",
    "profile_manager",
    "AgentProfileTemplate",
    "AGENT_PROFILE_TEMPLATES",
]
