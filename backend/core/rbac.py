"""RBAC多租户权限系统"""
import json, logging, uuid, hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)

class Role(str, Enum):
    ADMIN = "admin"           # 系统管理员——完全控制
    ORG_OWNER = "org_owner"   # 组织所有者——组织内完全控制
    ORG_ADMIN = "org_admin"   # 组织管理员——管理项目和用户
    PROJECT_MANAGER = "project_manager"  # 项目经理——管理标注任务
    ANNOTATOR = "annotator"   # 标注员——执行标注
    REVIEWER = "reviewer"     # 审核员——审核标注
    VIEWER = "viewer"         # 查看者——只读访问
    
class Permission(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    ADMIN = "admin"

# 角色→权限映射
ROLE_PERMISSIONS = {
    Role.ADMIN: [Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE, Permission.ADMIN],
    Role.ORG_OWNER: [Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE, Permission.ADMIN],
    Role.ORG_ADMIN: [Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE],
    Role.PROJECT_MANAGER: [Permission.CREATE, Permission.READ, Permission.UPDATE],
    Role.ANNOTATOR: [Permission.READ, Permission.UPDATE],
    Role.REVIEWER: [Permission.READ, Permission.UPDATE],
    Role.VIEWER: [Permission.READ],
}

class Organization:
    def __init__(self, name: str, owner: str):
        self.org_id = f"org_{uuid.uuid4().hex[:12]}"
        self.name = name
        self.owner = owner
        self.created_at = datetime.now().isoformat()
        self.members: Dict[str, Role] = {owner: Role.ORG_OWNER}

class Project:
    def __init__(self, name: str, org_id: str, created_by: str):
        self.project_id = f"proj_{uuid.uuid4().hex[:12]}"
        self.name = name
        self.org_id = org_id
        self.created_by = created_by
        self.created_at = datetime.now().isoformat()
        self.members: Dict[str, Role] = {}

class RBACManager:
    _orgs: Dict[str, Organization] = {}
    _projects: Dict[str, Project] = {}
    
    @classmethod
    def create_org(cls, name: str, owner: str) -> Organization:
        org = Organization(name, owner)
        cls._orgs[org.org_id] = org
        return org
    
    @classmethod
    def get_org(cls, org_id: str) -> Optional[Organization]:
        return cls._orgs.get(org_id)
    
    @classmethod
    def list_orgs(cls) -> List[dict]:
        return [{"org_id": o.org_id, "name": o.name, "owner": o.owner, "member_count": len(o.members)} 
                for o in cls._orgs.values()]
    
    @classmethod
    def add_org_member(cls, org_id: str, username: str, role: Role) -> bool:
        org = cls._orgs.get(org_id)
        if not org:
            return False
        org.members[username] = role
        return True
    
    @classmethod
    def get_user_role_in_org(cls, org_id: str, username: str) -> Optional[Role]:
        org = cls._orgs.get(org_id)
        if org and username in org.members:
            return org.members[username]
        return None
    
    @classmethod
    def create_project(cls, name: str, org_id: str, created_by: str) -> Optional[Project]:
        org = cls._orgs.get(org_id)
        if not org:
            return None
        project = Project(name, org_id, created_by)
        project.members[created_by] = Role.PROJECT_MANAGER
        cls._projects[project.project_id] = project
        return project
    
    @classmethod
    def list_projects(cls, org_id: Optional[str] = None) -> List[dict]:
        projects = cls._projects.values()
        if org_id:
            projects = [p for p in projects if p.org_id == org_id]
        return [{"project_id": p.project_id, "name": p.name, "org_id": p.org_id, 
                 "created_by": p.created_by, "member_count": len(p.members)} for p in projects]
    
    @classmethod
    def add_project_member(cls, project_id: str, username: str, role: Role) -> bool:
        project = cls._projects.get(project_id)
        if not project:
            return False
        project.members[username] = role
        return True
    
    @classmethod
    def check_permission(cls, username: str, org_id: Optional[str], project_id: Optional[str], 
                         required_permission: Permission) -> bool:
        # 系统级admin始终有权限
        if username == "admin":
            return True
        # 项目级权限检查
        if project_id:
            project = cls._projects.get(project_id)
            if project and username in project.members:
                role = project.members[username]
                return required_permission in ROLE_PERMISSIONS.get(role, [])
        # 组织级权限检查
        if org_id:
            org_role = cls.get_user_role_in_org(org_id, username)
            if org_role:
                return required_permission in ROLE_PERMISSIONS.get(org_role, [])
        return False

rbac = RBACManager()
