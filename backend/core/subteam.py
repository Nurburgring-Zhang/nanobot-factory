"""子团队管理——项目内小组层级"""
import uuid, logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class SubTeam:
    def __init__(self, name: str, project_id: str, lead: str = ""):
        self.team_id = f"st_{uuid.uuid4().hex[:12]}"
        self.name = name
        self.project_id = project_id
        self.lead = lead
        self.members: List[str] = []  # username列表
        self.created_at = datetime.now().isoformat()

class SubTeamManager:
    _teams: Dict[str, SubTeam] = {}
    
    @classmethod
    def create(cls, name: str, project_id: str, lead: str = "") -> SubTeam:
        team = SubTeam(name, project_id, lead)
        if lead:
            team.members.append(lead)
        cls._teams[team.team_id] = team
        return team
    
    @classmethod
    def get(cls, team_id: str) -> Optional[SubTeam]:
        return cls._teams.get(team_id)
    
    @classmethod
    def list_by_project(cls, project_id: str) -> List[dict]:
        return [{"team_id": t.team_id, "name": t.name, "project_id": t.project_id,
                 "lead": t.lead, "member_count": len(t.members)} 
                for t in cls._teams.values() if t.project_id == project_id]
    
    @classmethod
    def add_member(cls, team_id: str, username: str) -> bool:
        team = cls._teams.get(team_id)
        if not team or username in team.members:
            return False
        team.members.append(username)
        return True
    
    @classmethod
    def remove_member(cls, team_id: str, username: str) -> bool:
        team = cls._teams.get(team_id)
        if not team or username not in team.members:
            return False
        team.members.remove(username)
        return True

subteam_mgr = SubTeamManager()
