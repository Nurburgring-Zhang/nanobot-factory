"""用户个人管理——Profile/偏好/操作历史"""
import uuid, logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class UserProfile:
    def __init__(self, username: str):
        self.username = username
        self.display_name = username
        self.email = ""
        self.avatar = ""
        self.role = "member"
        self.preferences = {
            "theme": "dark",
            "language": "zh-CN",
            "page_size": 50,
            "notifications": True,
        }
        self.created_at = datetime.now().isoformat()

class UserAction:
    def __init__(self, username: str, action: str, detail: str = "", ref_type: str = "", ref_id: str = ""):
        self.action_id = f"ua_{uuid.uuid4().hex[:12]}"
        self.username = username
        self.action = action
        self.detail = detail
        self.ref_type = ref_type
        self.ref_id = ref_id
        self.timestamp = datetime.now().isoformat()

class UserProfileManager:
    _profiles: Dict[str, UserProfile] = {}
    _actions: List[UserAction] = []  # 最多保留1000条
    
    @classmethod
    def get_or_create(cls, username: str) -> UserProfile:
        if username not in cls._profiles:
            cls._profiles[username] = UserProfile(username)
        return cls._profiles[username]
    
    @classmethod
    def update_preference(cls, username: str, key: str, value: Any) -> bool:
        profile = cls.get_or_create(username)
        profile.preferences[key] = value
        return True
    
    @classmethod
    def update_profile(cls, username: str, **kwargs) -> bool:
        profile = cls.get_or_create(username)
        for k, v in kwargs.items():
            if hasattr(profile, k):
                setattr(profile, k, v)
        return True
    
    @classmethod
    def log_action(cls, username: str, action: str, detail: str = "", ref_type: str = "", ref_id: str = "") -> str:
        act = UserAction(username, action, detail, ref_type, ref_id)
        cls._actions.append(act)
        if len(cls._actions) > 1000:
            cls._actions = cls._actions[-500:]
        return act.action_id
    
    @classmethod
    def get_actions(cls, username: str, limit: int = 50) -> List[dict]:
        return [{"action_id": a.action_id, "action": a.action, "detail": a.detail,
                 "ref_type": a.ref_type, "ref_id": a.ref_id, "timestamp": a.timestamp}
                for a in cls._actions if a.username == username][-limit:]

profile_mgr = UserProfileManager()
