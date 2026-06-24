"""
Multi-Tenant Engine — 多租户与权限体系 (智影设计文档 §11)
=========================================================
角色权限矩阵:
  admin     = 全部权限
  annotator = 标注 + 查看
  reviewer  = 审核 + 查看
  viewer    = 仅查看
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json, os, logging, uuid
from collections import Counter

logger = logging.getLogger(__name__)


class Role(str, Enum):
    ADMIN = "admin"
    ANNOTATOR = "annotator"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    PENDING = "pending"


class Action(str, Enum):
    """系统可执行的动作"""
    # 项目管理
    CREATE_PROJECT = "create_project"
    EDIT_PROJECT = "edit_project"
    DELETE_PROJECT = "delete_project"
    VIEW_PROJECT = "view_project"
    # 数据操作
    ANNOTATE = "annotate"
    REVIEW = "review"
    EXPORT = "export"
    IMPORT = "import"
    # 标注任务
    ASSIGN_TASK = "assign_task"
    SUBMIT_TASK = "submit_task"
    APPROVE_TASK = "approve_task"
    REJECT_TASK = "reject_task"
    # 系统管理
    MANAGE_USERS = "manage_users"
    MANAGE_TENANTS = "manage_tenants"
    VIEW_STATS = "view_stats"
    MANAGE_QUOTA = "manage_quota"
    # 权限/角色管理
    MANAGE_ROLES = "manage_roles"


# 权限矩阵: role → set of allowed actions
PERMISSION_MATRIX: Dict[Role, List[Action]] = {
    Role.ADMIN: list(Action),  # 全部权限
    Role.ANNOTATOR: [
        Action.VIEW_PROJECT,
        Action.ANNOTATE,
        Action.SUBMIT_TASK,
        Action.VIEW_STATS,
    ],
    Role.REVIEWER: [
        Action.VIEW_PROJECT,
        Action.REVIEW,
        Action.APPROVE_TASK,
        Action.REJECT_TASK,
        Action.EXPORT,
        Action.VIEW_STATS,
    ],
    Role.VIEWER: [
        Action.VIEW_PROJECT,
        Action.VIEW_STATS,
    ],
}


@dataclass
class Tenant:
    """租户"""
    id: str = ""
    name: str = ""
    quota: Dict[str, int] = field(default_factory=lambda: {
        "max_projects": 10,
        "max_users": 50,
        "max_storage_gb": 100,
        "max_api_calls_per_day": 10000,
    })
    created_at: str = ""
    status: str = "active"

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "name": self.name,
            "quota": self.quota, "created_at": self.created_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Tenant":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            quota=data.get("quota", {}),
            created_at=data.get("created_at", ""),
            status=data.get("status", "active"),
        )


@dataclass
class User:
    """用户"""
    id: str = ""
    tenant_id: str = ""
    role: Role = Role.VIEWER
    status: UserStatus = UserStatus.ACTIVE
    name: str = ""
    email: str = ""
    workload: float = 0.0  # 当前负载 (任务数)
    skills: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "tenant_id": self.tenant_id,
            "role": self.role.value, "status": self.status.value,
            "name": self.name, "email": self.email,
            "workload": self.workload, "skills": self.skills,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "User":
        return cls(
            id=data.get("id", ""),
            tenant_id=data.get("tenant_id", ""),
            role=Role(data.get("role", "viewer")),
            status=UserStatus(data.get("status", "active")),
            name=data.get("name", ""),
            email=data.get("email", ""),
            workload=data.get("workload", 0.0),
            skills=data.get("skills", []),
        )


@dataclass
class Project:
    """项目"""
    id: str = ""
    tenant_id: str = ""
    name: str = ""
    description: str = ""
    members: List[User] = field(default_factory=list)
    quota_used: Dict[str, int] = field(default_factory=lambda: {
        "storage_gb": 0,
        "api_calls_today": 0,
    })
    created_at: str = ""
    status: str = "active"

    def add_member(self, user: User) -> None:
        """添加成员到项目"""
        if not any(m.id == user.id for m in self.members):
            self.members.append(user)
            logger.info(f"User {user.id} added to project {self.id}")

    def remove_member(self, user_id: str) -> bool:
        """从项目移除成员"""
        before = len(self.members)
        self.members = [m for m in self.members if m.id != user_id]
        return len(self.members) < before

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "tenant_id": self.tenant_id,
            "name": self.name, "description": self.description,
            "members": [m.to_dict() for m in self.members],
            "quota_used": self.quota_used,
            "created_at": self.created_at, "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Project":
        return cls(
            id=data.get("id", ""),
            tenant_id=data.get("tenant_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            members=[User.from_dict(m) for m in data.get("members", [])],
            quota_used=data.get("quota_used", {}),
            created_at=data.get("created_at", ""),
            status=data.get("status", "active"),
        )


class Permission:
    """权限控制"""

    def __init__(self):
        # 缓存: role → set of actions
        self._cache: Dict[str, set] = {}
        self._build_cache()

    def _build_cache(self) -> None:
        for role, actions in PERMISSION_MATRIX.items():
            self._cache[role.value] = set(actions)

    def check(self, role: Role, action: Action) -> bool:
        """
        检查角色是否有权限执行某操作
        返回: True if allowed, False otherwise
        """
        allowed_actions = self._cache.get(role.value, set())
        result = action in allowed_actions
        if not result:
            logger.debug(f"Permission denied: role={role.value}, action={action.value}")
        return result

    def get_allowed_actions(self, role: Role) -> List[str]:
        """获取角色允许的所有操作列表"""
        return sorted(a.value for a in self._cache.get(role.value, set()))

    def check_batch(self, role: Role, actions: List[Action]) -> Dict[str, bool]:
        """批量检查权限"""
        return {a.value: self.check(role, a) for a in actions}

    def describe_roles(self) -> Dict[str, List[str]]:
        """返回完整角色权限描述"""
        return {
            r.value: sorted(a.value for a in actions)
            for r, actions in PERMISSION_MATRIX.items()
        }


class MultiTenantManager:
    """多租户管理器 — 整合租户/用户/项目/权限管理"""

    def __init__(self):
        self.permission = Permission()
        # 存储 (实际场景对接数据库)
        self.tenants: Dict[str, Tenant] = {}
        self.users: Dict[str, User] = {}
        self.projects: Dict[str, Project] = {}

    # ──────────── 租户管理 ────────────

    def create_tenant(self, name: str, quota: Optional[Dict[str, int]] = None) -> Tenant:
        """
        创建新租户
        返回创建后的Tenant对象
        """
        tenant_id = f"tenant_{uuid.uuid4().hex[:8]}"
        tenant = Tenant(
            id=tenant_id,
            name=name,
            quota=quota or {
                "max_projects": 10,
                "max_users": 50,
                "max_storage_gb": 100,
                "max_api_calls_per_day": 10000,
            },
            created_at=datetime.now().isoformat(),
        )
        self.tenants[tenant_id] = tenant
        logger.info(f"Created tenant: {tenant.name} ({tenant_id})")
        return tenant

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        return self.tenants.get(tenant_id)

    def list_tenants(self) -> List[Tenant]:
        return list(self.tenants.values())

    def update_tenant_quota(self, tenant_id: str, quota: Dict[str, int]) -> bool:
        """更新租户配额"""
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            logger.warning(f"Tenant {tenant_id} not found")
            return False
        tenant.quota.update(quota)
        return True

    # ──────────── 用户管理 ────────────

    def add_user(
        self,
        tenant_id: str,
        name: str,
        email: str,
        role: Role = Role.VIEWER,
        skills: Optional[List[str]] = None,
    ) -> Optional[User]:
        """
        在指定租户下添加用户
        返回用户对象，如果租户不存在或用户已满则返回None
        """
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            logger.error(f"Cannot add user: tenant {tenant_id} not found")
            return None

        # 检查租户用户上限
        existing_users = [u for u in self.users.values() if u.tenant_id == tenant_id]
        if len(existing_users) >= tenant.quota.get("max_users", 50):
            logger.error(f"Tenant {tenant_id} user limit reached")
            return None

        user_id = f"user_{uuid.uuid4().hex[:8]}"
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            role=role,
            status=UserStatus.ACTIVE,
            name=name,
            email=email,
            skills=skills or [],
        )
        self.users[user_id] = user
        logger.info(f"Added user {user.name} ({user_id}) to tenant {tenant_id} as {role.value}")
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    def list_users(self, tenant_id: Optional[str] = None) -> List[User]:
        if tenant_id:
            return [u for u in self.users.values() if u.tenant_id == tenant_id]
        return list(self.users.values())

    def update_user_role(self, user_id: str, new_role: Role) -> bool:
        """更新用户角色"""
        user = self.users.get(user_id)
        if not user:
            return False
        user.role = new_role
        return True

    def disable_user(self, user_id: str) -> bool:
        """禁用用户"""
        user = self.users.get(user_id)
        if not user:
            return False
        user.status = UserStatus.DISABLED
        return True

    # ──────────── 项目管理 ────────────

    def create_project(
        self,
        tenant_id: str,
        name: str,
        description: str = "",
        members: Optional[List[User]] = None,
    ) -> Optional[Project]:
        """
        在指定租户下创建项目
        检查租户项目上限quota
        """
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            logger.error(f"Cannot create project: tenant {tenant_id} not found")
            return None

        # 检查租户项目上限
        existing_projects = [p for p in self.projects.values() if p.tenant_id == tenant_id]
        if len(existing_projects) >= tenant.quota.get("max_projects", 10):
            logger.error(f"Tenant {tenant_id} project limit reached")
            return None

        project_id = f"proj_{uuid.uuid4().hex[:8]}"
        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            members=members or [],
            created_at=datetime.now().isoformat(),
        )
        self.projects[project_id] = project
        logger.info(f"Created project {project.name} ({project_id}) for tenant {tenant_id}")
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        return self.projects.get(project_id)

    def list_projects(self, tenant_id: Optional[str] = None) -> List[Project]:
        if tenant_id:
            return [p for p in self.projects.values() if p.tenant_id == tenant_id]
        return list(self.projects.values())

    def add_project_member(self, project_id: str, user_id: str) -> bool:
        """添加项目成员"""
        project = self.projects.get(project_id)
        user = self.users.get(user_id)
        if not project or not user:
            return False
        if user.tenant_id != project.tenant_id:
            logger.warning(f"User {user_id} not in same tenant as project {project_id}")
            return False
        project.add_member(user)
        return True

    # ──────────── 权限检查 ────────────

    def check_permission(self, user_id: str, action: Action) -> bool:
        """
        检查用户是否有权限执行某操作
        综合检查: 用户状态 + 角色权限
        """
        user = self.users.get(user_id)
        if not user:
            logger.warning(f"User {user_id} not found")
            return False
        if user.status != UserStatus.ACTIVE:
            logger.warning(f"User {user_id} is not active (status={user.status.value})")
            return False
        return self.permission.check(user.role, action)

    def check_user_project_permission(
        self, user_id: str, project_id: str, action: Action
    ) -> bool:
        """检查用户是否在项目中拥有某权限"""
        # 先检查通用权限
        if not self.check_permission(user_id, action):
            return False
        # 再检查是否项目成员
        project = self.projects.get(project_id)
        if not project:
            return False
        return any(m.id == user_id for m in project.members)

    # ──────────── 用量统计 ────────────

    def get_usage_stats(self, tenant_id: str) -> Dict[str, Any]:
        """
        获取租户用量统计
        返回: {
            tenant_id, tenant_name,
            total_users, active_users,
            total_projects,
            quota 使用率
        }
        """
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            return {"error": f"Tenant {tenant_id} not found"}

        tenant_users = [u for u in self.users.values() if u.tenant_id == tenant_id]
        tenant_projects = [p for p in self.projects.values() if p.tenant_id == tenant_id]
        active_users = [u for u in tenant_users if u.status == UserStatus.ACTIVE]

        quota_usage = {}
        for k, limit in tenant.quota.items():
            if k == "max_users":
                used = len(tenant_users)
            elif k == "max_projects":
                used = len(tenant_projects)
            elif k == "max_storage_gb":
                used = sum(p.quota_used.get("storage_gb", 0) for p in tenant_projects)
            elif k == "max_api_calls_per_day":
                used = sum(p.quota_used.get("api_calls_today", 0) for p in tenant_projects)
            else:
                used = 0
            usage_pct = round((used / max(limit, 1)) * 100, 1) if limit > 0 else 0
            quota_usage[k] = {
                "limit": limit, "used": used, "usage_pct": usage_pct,
            }

        # 按角色统计用户
        role_stats = Counter(u.role.value for u in tenant_users)

        return {
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
            "total_users": len(tenant_users),
            "active_users": len(active_users),
            "total_projects": len(tenant_projects),
            "role_distribution": dict(role_stats),
            "quota_usage": quota_usage,
            "created_at": tenant.created_at,
            "status": tenant.status,
        }

    def to_dict(self) -> Dict:
        """导出全部状态"""
        return {
            "tenants": {k: v.to_dict() for k, v in self.tenants.items()},
            "users": {k: v.to_dict() for k, v in self.users.items()},
            "projects": {k: v.to_dict() for k, v in self.projects.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MultiTenantManager":
        mgr = cls()
        mgr.tenants = {k: Tenant.from_dict(v) for k, v in data.get("tenants", {}).items()}
        mgr.users = {k: User.from_dict(v) for k, v in data.get("users", {}).items()}
        mgr.projects = {k: Project.from_dict(v) for k, v in data.get("projects", {}).items()}
        return mgr
