"""Multi-tenant user, project, role, and quota management"""

import uuid
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel
from core.persistent_base import PersistentManager


class UserRole(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Quota(BaseModel):
    max_projects: int = 5
    max_dataset_size_mb: int = 10240  # 10GB
    max_concurrent_tasks: int = 3
    max_api_calls_per_day: int = 10000


class User(BaseModel):
    id: str
    username: str
    email: str = ""
    role: UserRole = UserRole.VIEWER
    quota: Quota = Quota()
    api_key: str = ""
    created_at: str = ""
    last_active: str = ""
    is_active: bool = True


class Project(BaseModel):
    id: str
    user_id: str
    name: str
    description: str = ""
    storage_used_mb: float = 0.0
    dataset_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    is_archived: bool = False


class UserManager(PersistentManager):
    """多用户管理"""
    _db_table = "users"
    _db_fields = ["id","username","email","role","quota","api_key","created_at","last_active","is_active"]
    _project_db_table = "projects"
    _project_db_fields = ["id","user_id","name","description","storage_used_mb","dataset_count","created_at","updated_at","is_archived"]

    def __init__(self, db_path: str = ""):
        self._users: Dict[str, User] = {}
        self._projects: Dict[str, Project] = {}
        self._user_projects: Dict[str, List[str]] = {}  # user_id -> [project_id]
        self._api_key_index: Dict[str, str] = {}  # api_key -> user_id
        if db_path:
            self._db_path = db_path
        super().__init__()
        self._ensure_project_table()
        self._load_users_from_db()
        self._load_projects_from_db()
        self._default_admin()

    def _ensure_project_table(self):
        if not self._project_db_table or not self._project_db_fields:
            return
        fields_def = ", ".join(f + " TEXT" for f in self._project_db_fields)
        with self._local_lock:
            conn = self._get_conn()
            try:
                # Safe concatenation: table name is class constant
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS " + self._project_db_table + " (" + fields_def + ", "
                    "PRIMARY KEY (id))"
                )
                conn.commit()
            finally:
                conn.close()

    def _save_project(self, key: str, data: dict):
        if not self._project_db_table:
            return
        # Whitelist field names against allowed _project_db_fields
        ALLOWED_FIELDS = set(self._project_db_fields)
        fields = [k for k in data.keys() if k in ALLOWED_FIELDS]
        if not fields:
            return
        placeholders = ", ".join("?" for _ in fields)
        col_names = ", ".join(fields)
        values = []
        for k in fields:
            v = data.get(k)
            if k == "id":
                values.append(str(v) if not isinstance(v, str) else v)
            else:
                values.append(json.dumps(v, ensure_ascii=False))
        # Safe concatenation: table name is class constant, fields are whitelist-validated
        sql = "INSERT OR REPLACE INTO " + self._project_db_table + " (" + col_names + ") VALUES (" + placeholders + ")"
        with self._local_lock:
            conn = self._get_conn()
            try:
                conn.execute(sql, values)
                conn.commit()
            finally:
                conn.close()

    def _delete_project(self, key: str):
        if not self._project_db_table:
            return
        with self._local_lock:
            conn = self._get_conn()
            try:
                # Safe concatenation: table name is class constant
                conn.execute(
                    "DELETE FROM " + self._project_db_table + " WHERE id = ?",
                    (key,),
                )
                conn.commit()
            finally:
                conn.close()

    def _load_users_from_db(self):
        for row in self._load_all():
            # row里的quota是dict, role是string, is_active可能是bool/string
            row["role"] = UserRole(row["role"]) if isinstance(row["role"], str) else row["role"]
            if isinstance(row.get("quota"), dict):
                row["quota"] = Quota(**row["quota"])
            user = User(**row)
            self._users[user.id] = user
            self._api_key_index[user.api_key] = user.id
            self._user_projects.setdefault(user.id, [])

    def _load_projects_from_db(self):
        if not self._project_db_table:
            return
        with self._local_lock:
            conn = self._get_conn()
            try:
                # Safe concatenation: table name is class constant
                cursor = conn.execute("SELECT * FROM " + self._project_db_table)
                rows = [dict(row) for row in cursor.fetchall()]
                for row in rows:
                    parsed = {}
                    for k, v in row.items():
                        if v is None:
                            parsed[k] = None
                        else:
                            try:
                                parsed[k] = json.loads(v)
                            except (json.JSONDecodeError, TypeError):
                                parsed[k] = v
                    project = Project(**parsed)
                    self._projects[project.id] = project
                    self._user_projects.setdefault(project.user_id, []).append(project.id)
            finally:
                conn.close()

    def _default_admin(self):
        """创建默认admin用户"""
        admin_id = "u-admin-001"
        if admin_id in self._users:
            return  # already exists
        admin = User(
            id=admin_id,
            username="admin",
            email="admin@nanobot.local",
            role=UserRole.ADMIN,
            api_key=f"nbk-{uuid.uuid4().hex[:16]}",
            created_at=datetime.now().isoformat(),
        )
        self._users[admin_id] = admin
        self._api_key_index[admin.api_key] = admin_id
        self._user_projects[admin_id] = []
        self._save(admin.id, admin.model_dump())

    def create_user(
        self,
        username: str,
        role: UserRole = UserRole.VIEWER,
        quota: Optional[Quota] = None,
    ) -> User:
        user_id = f"u-{uuid.uuid4().hex[:8]}"
        user = User(
            id=user_id,
            username=username,
            role=role,
            quota=quota or Quota(),
            api_key=f"nbk-{uuid.uuid4().hex[:16]}",
            created_at=datetime.now().isoformat(),
        )
        self._users[user_id] = user
        self._api_key_index[user.api_key] = user_id
        self._user_projects[user_id] = []
        self._save(user.id, user.model_dump())
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    def authenticate(self, api_key: str) -> Optional[User]:
        """使用哈希索引O(1)查找api_key"""
        user_id = self._api_key_index.get(api_key)
        if user_id:
            user = self._users.get(user_id)
            if user and user.is_active:
                return user
        return None

    def create_project(
        self, user_id: str, name: str, description: str = ""
    ) -> Optional[Project]:
        user = self.get_user(user_id)
        if not user:
            return None
        # 检查配额
        if len(self._user_projects.get(user_id, [])) >= user.quota.max_projects:
            return None
        project_id = f"p-{uuid.uuid4().hex[:8]}"
        project = Project(
            id=project_id,
            user_id=user_id,
            name=name,
            description=description,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        self._projects[project_id] = project
        self._user_projects.setdefault(user_id, []).append(project_id)
        self._save_project(project.id, project.model_dump())
        return project

    def get_user_projects(self, user_id: str) -> List[Project]:
        pids = self._user_projects.get(user_id, [])
        return [self._projects[pid] for pid in pids if pid in self._projects]

    def get_project(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def check_permission(
        self, user_id: str, project_id: str, required_role: UserRole
    ) -> bool:
        """检查用户是否有权访问项目"""
        user = self.get_user(user_id)
        if not user:
            return False
        # admin有全部权限
        if user.role == UserRole.ADMIN:
            return True
        # 检查角色等级
        roles = [UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER]
        user_level = roles.index(user.role)
        required_level = roles.index(required_role)
        if user_level > required_level:
            return False
        # 检查用户是否有项目权限（去掉project.user_id != user_id的限制）
        project = self.get_project(project_id)
        if not project:
            return False
        user_pids = self._user_projects.get(user_id, [])
        if project_id not in user_pids:
            return False
        return True

    def get_all_users(self) -> List[User]:
        return list(self._users.values())

    def get_all_projects(self) -> List[Project]:
        return list(self._projects.values())
