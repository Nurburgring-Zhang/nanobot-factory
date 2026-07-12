"""P5-R1-T1 ProjectCenter — ProjectEngine (项目中心核心引擎)

设计原则 (智影 §7):
1. **数据层**: 使用 ``backend/imdf.db`` 的 SQLAlchemy 双模 (SQLite 开发 / PostgreSQL 生产),
   直接复用 ``models.Project`` (已扩展 priority/tags/start_date/due_date),
   ``models.ProjectMember`` (成员关联) + ``models.ProjectTimelineEvent`` (事件流)。
2. **状态机**: ``planning → active → paused → closed``, 严格按 ``PROJECT_VALID_TRANSITIONS``
   校验; 非法转换抛 ``ProjectStatusTransitionError`` (HTTP 4xx)。
3. **进度计算**: requirements / tasks / datasets / deliveries 数量来自其它表
   (跨子系统的统计, 当前 P5 阶段先给 stub, 后续 P6+ 接入真实表)。
4. **可注入 SessionLocal**: 便于测试用 ``tmp_db`` 替换 + ``init_db`` 走临时 SQLite。

API 接口 (面向调用方):
    from engines.project_engine import ProjectEngine, Project, ProjectStatusTransitionError

    engine = ProjectEngine()
    proj = engine.create_project(name="...", owner_id="alice")
    proj = engine.transition_status(proj.id, "active", reason="kickoff")
    stats = engine.get_project_stats(proj.id)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 1. 状态机 + 错误
# ════════════════════════════════════════════════════════════════════════════

PROJECT_STATUSES = ("planning", "active", "paused", "closed")
PROJECT_PRIORITIES = ("P0", "P1", "P2", "P3")
PROJECT_MEMBER_ROLES = ("owner", "admin", "member", "viewer")

# 合法转换: planning → active/closed; active ↔ paused; * → closed
PROJECT_VALID_TRANSITIONS: Dict[str, set] = {
    "planning": {"active", "closed"},
    "active": {"paused", "closed"},
    "paused": {"active", "closed"},
    "closed": set(),  # terminal — 任何转换都非法
}


class ProjectStatusTransitionError(ValueError):
    """项目状态机非法转换 — 映射到 HTTP 4xx。"""

    def __init__(self, message: str, *, project_id: str = "", old: str = "", new: str = ""):
        super().__init__(message)
        self.project_id = project_id
        self.old = old
        self.new = new


class ProjectNotFoundError(KeyError):
    """项目不存在 — 映射到 HTTP 404。"""

    def __init__(self, project_id: str):
        super().__init__(f"Project {project_id!r} not found")
        self.project_id = project_id


class ProjectValidationError(ValueError):
    """入参校验失败 — 映射到 HTTP 400。"""

    pass


# ════════════════════════════════════════════════════════════════════════════
# 2. Project dataclass (Python-level, 独立于 ORM row)
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class Project:
    """项目 — 业务侧 ID 形如 ``proj_<8-hex>``。"""

    id: str = ""
    name: str = ""
    description: str = ""
    status: str = "planning"
    priority: str = "P1"
    owner_id: str = ""
    members: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    start_date: str = ""  # ISO date YYYY-MM-DD, 空表示未设置
    due_date: str = ""    # ISO date YYYY-MM-DD
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # owner_id 同步到 owner (向后兼容 legacy clients)
        d["owner"] = self.owner_id
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            status=str(data.get("status") or "planning"),
            priority=str(data.get("priority") or "P1"),
            owner_id=str(data.get("owner_id") or data.get("owner") or ""),
            members=list(data.get("members") or []),
            tags=list(data.get("tags") or []),
            start_date=str(data.get("start_date") or ""),
            due_date=str(data.get("due_date") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )


def _now_iso() -> str:
    """UTC ISO-8601, 秒级精度。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_date(s: str, field_name: str) -> str:
    """校验 YYYY-MM-DD 格式, 空字符串视为 None。"""
    if not s:
        return ""
    try:
        date.fromisoformat(s)
    except (ValueError, TypeError) as exc:
        raise ProjectValidationError(
            f"{field_name} must be ISO date YYYY-MM-DD, got {s!r}"
        ) from exc
    return s


def _validate_priority(p: str) -> str:
    if p not in PROJECT_PRIORITIES:
        raise ProjectValidationError(
            f"priority must be one of {PROJECT_PRIORITIES}, got {p!r}"
        )
    return p


def _validate_status(s: str) -> str:
    if s not in PROJECT_STATUSES:
        raise ProjectValidationError(
            f"status must be one of {PROJECT_STATUSES}, got {s!r}"
        )
    return s


def _validate_member_role(r: str) -> str:
    if r not in PROJECT_MEMBER_ROLES:
        raise ProjectValidationError(
            f"role must be one of {PROJECT_MEMBER_ROLES}, got {r!r}"
        )
    return r


# ════════════════════════════════════════════════════════════════════════════
# 3. ProjectEngine — 业务核心
# ════════════════════════════════════════════════════════════════════════════

class ProjectEngine:
    """项目中心引擎 — CRUD + 状态机 + 成员 + 时间线 + 统计。

    用法::

        engine = ProjectEngine()
        proj = engine.create_project(name="...", owner_id="alice", priority="P1")

    测试覆盖见 ``backend/imdf/tests/test_p5_r1_t1_project.py``。
    """

    def __init__(self, session_factory=None, actor: str = "system"):
        """``session_factory`` 可注入 (测试用临时 SQLite); ``actor`` 写入 timeline 事件。"""
        # 延后 import, 避免 module-level 循环 (project_engine → db → models)
        if session_factory is None:
            from db import SessionLocal  # type: ignore
            session_factory = SessionLocal
        self._session_factory = session_factory
        self._actor = actor or "system"

    # ──────────────── session helper ────────────────
    def _session(self):
        """开一个新 Session (caller 负责 close)。"""
        return self._session_factory()

    @staticmethod
    def _row_to_project(row) -> Project:
        """ORM row → Project dataclass。容忍空值。"""
        members = list(row.members or [])
        tags = list(row.tags or [])
        return Project(
            id=row.id,
            name=row.name or "",
            description=row.description or "",
            status=row.status or "planning",
            priority=row.priority or "P1",
            owner_id=row.owner or "",
            members=members,
            tags=tags,
            start_date=row.start_date or "",
            due_date=row.due_date or "",
            created_at=row.created_at.isoformat() if row.created_at else "",
            updated_at=row.updated_at.isoformat() if row.updated_at else "",
        )

    # ──────────────── 辅助: 记录 timeline 事件 ────────────────
    def _record_event(
        self,
        db,
        project_id: str,
        event_type: str,
        payload: Dict[str, Any],
        message: str = "",
    ) -> None:
        """向 ``project_timeline_events`` 追加事件 (best-effort, 失败 log 但不抛)。"""
        try:
            from models import ProjectTimelineEvent  # type: ignore

            event = ProjectTimelineEvent(
                id=f"pte_{uuid.uuid4().hex[:12]}",
                project_id=project_id,
                event_type=event_type,
                actor=self._actor,
                payload=payload or {},
                message=message or "",
            )
            db.add(event)
            # 不在这里 commit — 由 caller 统一 commit/rollback
        except Exception as exc:  # pragma: no cover
            logger.warning(f"failed to record timeline event {event_type} for {project_id}: {exc}")

    # ══════════════════════════════════════════════════════════════════════
    # A. CRUD
    # ══════════════════════════════════════════════════════════════════════

    def create_project(
        self,
        name: str,
        description: str = "",
        owner_id: str = "",
        members: Optional[List[str]] = None,
        priority: str = "P1",
        tags: Optional[List[str]] = None,
        start_date: str = "",
        due_date: str = "",
        status: str = "planning",
        actor: str = "",
    ) -> Project:
        """创建项目 — 初始状态 = planning (or given)。"""
        name = (name or "").strip()
        if not name:
            raise ProjectValidationError("name is required")
        if len(name) > 200:
            raise ProjectValidationError(f"name too long ({len(name)} > 200)")
        owner_id = (owner_id or "").strip() or "unknown"
        priority = _validate_priority(priority)
        status = _validate_status(status)
        start_date = _validate_date(start_date, "start_date")
        due_date = _validate_date(due_date, "due_date")
        member_list = [str(m) for m in (members or []) if m]
        tag_list = [str(t) for t in (tags or []) if t]

        from db import init_db  # type: ignore  # noqa: F401  # 触发注册

        proj_id = f"proj_{uuid.uuid4().hex[:8]}"
        now_iso = _now_iso()

        db = self._session()
        try:
            from models import Project, ProjectMember  # type: ignore

            row = Project(
                id=proj_id,
                name=name,
                description=description or "",
                status=status,
                owner=owner_id,
                members=member_list,
                priority=priority,
                tags=tag_list,
                start_date=start_date,
                due_date=due_date,
            )
            db.add(row)

            # 写 owner 进 ProjectMember 表 (role=owner)
            if owner_id and owner_id != "unknown":
                db.add(ProjectMember(
                    id=f"pm_{uuid.uuid4().hex[:12]}",
                    project_id=proj_id,
                    user_id=owner_id,
                    role="owner",
                ))

            # 写附加成员进 ProjectMember
            for uid in member_list:
                if uid == owner_id:
                    continue  # 已用 owner 写入
                db.add(ProjectMember(
                    id=f"pm_{uuid.uuid4().hex[:12]}",
                    project_id=proj_id,
                    user_id=uid,
                    role="member",
                ))

            # timeline 事件
            self._record_event(
                db, proj_id, "created",
                payload={
                    "name": name, "owner_id": owner_id,
                    "members": member_list, "priority": priority,
                    "tags": tag_list,
                    "start_date": start_date, "due_date": due_date,
                    "status": status,
                },
                message=f"project {name} created",
            )

            db.commit()
            db.refresh(row)
            return self._row_to_project(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_projects(
        self,
        status: Optional[str] = None,
        owner_id: Optional[str] = None,
        keyword: Optional[str] = None,
        priority: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Project], int]:
        """分页列表 + 过滤。返回 ``(items, total)``。"""
        status = _validate_status(status) if status else None
        priority = _validate_priority(priority) if priority else None
        page = max(int(page or 1), 1)
        page_size = max(int(page_size or 20), 1)

        db = self._session()
        try:
            from models import Project  # type: ignore

            q = db.query(Project)
            if status:
                q = q.filter(Project.status == status)
            if owner_id:
                q = q.filter(Project.owner == owner_id)
            if priority:
                q = q.filter(Project.priority == priority)
            if keyword:
                kw = f"%{keyword.lower()}%"
                from sqlalchemy import func as sql_func, or_
                q = q.filter(or_(
                    sql_func.lower(Project.name).like(kw),
                    sql_func.lower(Project.description).like(kw),
                ))
            total = q.count()
            rows = (
                q.order_by(Project.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
                .all()
            )
            return [self._row_to_project(r) for r in rows], total
        finally:
            db.close()

    def get_project(self, project_id: str) -> Project:
        """按 ID 取项目; 不存在抛 ``ProjectNotFoundError``。"""
        if not project_id:
            raise ProjectValidationError("project_id required")
        db = self._session()
        try:
            from models import Project  # type: ignore

            row = db.query(Project).filter(Project.id == project_id).first()
            if not row:
                raise ProjectNotFoundError(project_id)
            return self._row_to_project(row)
        finally:
            db.close()

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        due_date: Optional[str] = None,
        members: Optional[List[str]] = None,
        actor: str = "",
    ) -> Project:
        """更新项目元数据 (status 转换走 ``transition_status``)。"""
        if not project_id:
            raise ProjectValidationError("project_id required")

        changes: Dict[str, Any] = {}

        db = self._session()
        try:
            from models import Project, ProjectMember  # type: ignore

            row = db.query(Project).filter(Project.id == project_id).first()
            if not row:
                raise ProjectNotFoundError(project_id)

            if name is not None:
                new_name = (name or "").strip()
                if not new_name:
                    raise ProjectValidationError("name cannot be empty")
                if len(new_name) > 200:
                    raise ProjectValidationError("name too long")
                if new_name != row.name:
                    changes["name"] = {"old": row.name, "new": new_name}
                    row.name = new_name
            if description is not None:
                if description != row.description:
                    changes["description"] = {"old": row.description, "new": description}
                row.description = description or ""
            if priority is not None:
                p = _validate_priority(priority)
                if p != row.priority:
                    changes["priority"] = {"old": row.priority, "new": p}
                row.priority = p
            if tags is not None:
                tag_list = [str(t) for t in tags if t]
                if tag_list != (row.tags or []):
                    changes["tags"] = {"old": list(row.tags or []), "new": tag_list}
                row.tags = tag_list
            if start_date is not None:
                sd = _validate_date(start_date, "start_date")
                if sd != (row.start_date or ""):
                    changes["start_date"] = {"old": row.start_date or "", "new": sd}
                row.start_date = sd
            if due_date is not None:
                dd = _validate_date(due_date, "due_date")
                if dd != (row.due_date or ""):
                    changes["due_date"] = {"old": row.due_date or "", "new": dd}
                row.due_date = dd
            if members is not None:
                ml = [str(m) for m in members if m]
                if ml != (row.members or []):
                    changes["members"] = {"old": list(row.members or []), "new": ml}
                row.members = ml

                # 同步 ProjectMember 表 — 删多余 + 加新的
                existing = {
                    pm.user_id: pm
                    for pm in db.query(ProjectMember)
                    .filter(ProjectMember.project_id == project_id).all()
                }
                owner_user_id = row.owner
                new_set = set(ml) | ({owner_user_id} if owner_user_id and owner_user_id != "unknown" else set())
                # 删多余
                for uid, pm in list(existing.items()):
                    if uid not in new_set:
                        db.delete(pm)
                # 加新的
                for uid in ml:
                    if uid not in existing:
                        db.add(ProjectMember(
                            id=f"pm_{uuid.uuid4().hex[:12]}",
                            project_id=project_id,
                            user_id=uid,
                            role="member",
                        ))

            if changes:
                self._record_event(
                    db, project_id, "updated",
                    payload=changes,
                    message=f"project {row.name} updated ({len(changes)} fields)",
                )

            db.commit()
            db.refresh(row)
            return self._row_to_project(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def delete_project(self, project_id: str) -> bool:
        """删除项目 + 关联 members / timeline events。返回是否成功。"""
        if not project_id:
            raise ProjectValidationError("project_id required")
        db = self._session()
        try:
            from models import Project, ProjectMember, ProjectTimelineEvent  # type: ignore

            row = db.query(Project).filter(Project.id == project_id).first()
            if not row:
                return False
            # 删关联 members + timeline
            db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete()
            db.query(ProjectTimelineEvent).filter(
                ProjectTimelineEvent.project_id == project_id
            ).delete()
            db.delete(row)
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ══════════════════════════════════════════════════════════════════════
    # B. 成员管理
    # ══════════════════════════════════════════════════════════════════════

    def add_member(
        self,
        project_id: str,
        user_id: str,
        role: str = "member",
        actor: str = "",
    ) -> Project:
        """添加成员 (写 ProjectMember + 同步 Project.members JSON)。"""
        if not project_id or not user_id:
            raise ProjectValidationError("project_id and user_id required")
        role = _validate_member_role(role)

        db = self._session()
        try:
            from models import Project, ProjectMember  # type: ignore

            row = db.query(Project).filter(Project.id == project_id).first()
            if not row:
                raise ProjectNotFoundError(project_id)

            # 查重
            existing = (
                db.query(ProjectMember)
                .filter(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == user_id,
                )
                .first()
            )
            if existing:
                # 更新 role
                if existing.role != role:
                    old_role = existing.role
                    existing.role = role
                    changes = {"role": {"old": old_role, "new": role}}
                    self._record_event(
                        db, project_id, "member_role_changed",
                        payload={"user_id": user_id, **changes},
                        message=f"{user_id} role {old_role} → {role}",
                    )
                    db.commit()
                    db.refresh(row)
                return self._row_to_project(row)

            # 新增
            db.add(ProjectMember(
                id=f"pm_{uuid.uuid4().hex[:12]}",
                project_id=project_id,
                user_id=user_id,
                role=role,
            ))

            # 同步 JSON members (去重 + 保持顺序)
            members = list(row.members or [])
            if user_id not in members:
                members.append(user_id)
                row.members = members

            self._record_event(
                db, project_id, "member_added",
                payload={"user_id": user_id, "role": role},
                message=f"member {user_id} added as {role}",
            )

            db.commit()
            db.refresh(row)
            return self._row_to_project(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def remove_member(self, project_id: str, user_id: str) -> Project:
        """移除成员 (ProjectMember + Project.members JSON 同步)。"""
        if not project_id or not user_id:
            raise ProjectValidationError("project_id and user_id required")

        db = self._session()
        try:
            from models import Project, ProjectMember  # type: ignore

            row = db.query(Project).filter(Project.id == project_id).first()
            if not row:
                raise ProjectNotFoundError(project_id)

            pm = (
                db.query(ProjectMember)
                .filter(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == user_id,
                )
                .first()
            )
            if pm:
                old_role = pm.role
                db.delete(pm)

            # 同步 JSON
            members = list(row.members or [])
            if user_id in members:
                members.remove(user_id)
                row.members = members

            self._record_event(
                db, project_id, "member_removed",
                payload={"user_id": user_id, "old_role": pm.role if pm else "member"},
                message=f"member {user_id} removed (was {pm.role if pm else 'member'})",
            )

            db.commit()
            db.refresh(row)
            return self._row_to_project(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_members(self, project_id: str) -> List[Dict[str, Any]]:
        """列出项目所有成员 (ProjectMember 表的权威数据)。"""
        if not project_id:
            raise ProjectValidationError("project_id required")
        db = self._session()
        try:
            from models import ProjectMember  # type: ignore

            rows = (
                db.query(ProjectMember)
                .filter(ProjectMember.project_id == project_id)
                .order_by(ProjectMember.joined_at.asc())
                .all()
            )
            return [r.to_dict() for r in rows]
        finally:
            db.close()

    # ══════════════════════════════════════════════════════════════════════
    # C. 状态机
    # ══════════════════════════════════════════════════════════════════════

    def transition_status(
        self,
        project_id: str,
        new_status: str,
        reason: str = "",
        actor: str = "",
    ) -> Project:
        """状态机转换。非法转换抛 ``ProjectStatusTransitionError``。"""
        new_status = _validate_status(new_status)

        db = self._session()
        try:
            from models import Project  # type: ignore

            row = db.query(Project).filter(Project.id == project_id).first()
            if not row:
                raise ProjectNotFoundError(project_id)

            old_status = row.status
            allowed = PROJECT_VALID_TRANSITIONS.get(old_status, set())
            if new_status not in allowed:
                allowed_str = ", ".join(sorted(allowed)) if allowed else "(terminal — no transition allowed)"
                raise ProjectStatusTransitionError(
                    f"cannot transition project {project_id} from {old_status!r} to {new_status!r}; "
                    f"allowed: {allowed_str}",
                    project_id=project_id,
                    old=old_status,
                    new=new_status,
                )

            row.status = new_status
            self._record_event(
                db, project_id, "status_changed",
                payload={"old_status": old_status, "new_status": new_status, "reason": reason},
                message=f"status {old_status} → {new_status}" + (f" ({reason})" if reason else ""),
            )
            db.commit()
            db.refresh(row)
            return self._row_to_project(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ══════════════════════════════════════════════════════════════════════
    # D. 时间线
    # ══════════════════════════════════════════════════════════════════════

    def get_timeline(
        self,
        project_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """返回项目所有事件, 按 ts DESC。"""
        if not project_id:
            raise ProjectValidationError("project_id required")
        limit = max(int(limit or 100), 1)

        db = self._session()
        try:
            from models import ProjectTimelineEvent  # type: ignore

            rows = (
                db.query(ProjectTimelineEvent)
                .filter(ProjectTimelineEvent.project_id == project_id)
                .order_by(ProjectTimelineEvent.ts.desc())
                .limit(limit)
                .all()
            )
            return [r.to_dict() for r in rows]
        finally:
            db.close()

    # ══════════════════════════════════════════════════════════════════════
    # E. 统计
    # ══════════════════════════════════════════════════════════════════════

    def get_project_stats(self, project_id: str) -> Dict[str, Any]:
        """返回项目统计 — requirements/tasks/datasets/deliveries 数量 + progress。

        P5-R2-T2 修复: requirements_count 之前错误复用 Task 计数
        (SQL `_safe_count("models.Task", project_id=...)` — Task 模型根本没
        project_id 列, filter 静默跳过, 实际返回 owner=user 的所有 task,
        且与 tasks_count 完全相等). 改用 RequirementEngine.count_requirements_by_project
        真实统计项目下需求数. tasks_count 改为 SQL Task 表 + owner 过滤
        (Task 表只有 owner 列, 暂以 project owner 近似代表项目任务).
        """
        if not project_id:
            raise ProjectValidationError("project_id required")

        # 1. 项目元数据
        proj = self.get_project(project_id)

        # 2. 子统计 (跨子系统, best-effort)
        # P5-R2-T2 fix: 真实需求数 — 走 RequirementEngine 单例的 in-memory dict
        try:
            from engines.requirement_engine import get_requirement_engine
            req_engine = get_requirement_engine()
            requirements_count = req_engine.count_requirements_by_project(project_id)
        except Exception as exc:  # pragma: no cover
            logger.debug(f"get_project_stats: requirement count failed: {exc}")
            requirements_count = 0

        # P5-R2-T2 fix: 任务数走 RequirementEngine (join via Requirement.project_id)
        # 原 SQL _safe_count("models.Task", owner=proj.owner_id) 把 owner 全部项目
        # 的 task 都算进来, 与单项目 stats 语义不符. 改为 req_engine 内部 join 统计.
        try:
            tasks_count = req_engine.count_tasks_by_project(project_id)
        except Exception as exc:  # pragma: no cover
            logger.debug(f"get_project_stats: task count failed: {exc}")
            tasks_count = 0
        dataset_count = self._safe_count("models.Dataset", project_id=project_id)
        delivery_count = 0  # deliveries 表尚未建立 (P5-R1-T5 之后才有)

        # 3. 进度 = 已完成 task / 总 task (有 task 时) — 同样走 req_engine join
        try:
            total_tasks = tasks_count
            done_tasks = req_engine.count_done_tasks_by_project(project_id)
        except Exception as exc:  # pragma: no cover
            logger.debug(f"get_project_stats: done-task count failed: {exc}")
            total_tasks = 0
            done_tasks = 0
        progress_pct = round(done_tasks * 100.0 / total_tasks, 1) if total_tasks else 0.0

        return {
            "project_id": project_id,
            "name": proj.name,
            "status": proj.status,
            "priority": proj.priority,
            "owner_id": proj.owner_id,
            "members_count": len(proj.members or []),
            "requirements_count": requirements_count,  # P5-R2-T2 fix: 真实需求数
            "tasks_count": tasks_count,
            "datasets_count": dataset_count,
            "deliveries_count": delivery_count,
            "progress": progress_pct,
            "tags_count": len(proj.tags or []),
            "due_date": proj.due_date or "",
            "created_at": proj.created_at,
            "updated_at": proj.updated_at,
        }

    # ── safe count helpers ──
    @staticmethod
    def _safe_count(model_path: str, **filters) -> int:
        """best-effort 查询, 失败返回 0。"""
        try:
            from db import SessionLocal  # type: ignore
            import importlib

            mod_path, _, cls_name = model_path.rpartition(".")
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name)
            db = SessionLocal()
            try:
                q = db.query(cls)
                for k, v in filters.items():
                    if hasattr(cls, k):
                        q = q.filter(getattr(cls, k) == v)
                return q.count()
            finally:
                db.close()
        except Exception as exc:  # pragma: no cover
            logger.debug(f"_safe_count({model_path}) failed: {exc}")
            return 0

    @staticmethod
    def _safe_count_total(model_path: str, **filters) -> int:
        return ProjectEngine._safe_count(model_path, **filters)

    @staticmethod
    def _safe_count_done(model_path: str, **filters) -> int:
        """count rows with status='done' / 'completed'."""
        try:
            from db import SessionLocal  # type: ignore
            import importlib

            mod_path, _, cls_name = model_path.rpartition(".")
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name)
            db = SessionLocal()
            try:
                q = db.query(cls)
                for k, v in filters.items():
                    if hasattr(cls, k):
                        q = q.filter(getattr(cls, k) == v)
                if hasattr(cls, "status"):
                    from sqlalchemy import or_
                    q = q.filter(or_(cls.status == "done", cls.status == "completed"))
                return q.count()
            finally:
                db.close()
        except Exception:  # pragma: no cover
            return 0


# ════════════════════════════════════════════════════════════════════════════
# 4. 工具: 临时 SQLite 工厂 (测试用)
# ════════════════════════════════════════════════════════════════════════════

def make_sqlite_session_factory(db_path: str | Path):
    """创建临时 SQLite Engine + SessionLocal, 触发 ``init_db()`` 建表。

    用法::

        from engines.project_engine import ProjectEngine, make_sqlite_session_factory

        SessionLocal, engine = make_sqlite_session_factory("/tmp/test.db")
        engine_inst = ProjectEngine(session_factory=SessionLocal)
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = str(db_path)
    url = f"sqlite:///{db_path}"
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
    )

    # 触发表创建 — 必须先 import models
    from db import Base  # type: ignore
    from models import register_all  # type: ignore
    register_all()
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, expire_on_commit=False,
    )
    return SessionLocal, engine


__all__ = [
    "Project",
    "ProjectEngine",
    "PROJECT_STATUSES",
    "PROJECT_PRIORITIES",
    "PROJECT_MEMBER_ROLES",
    "PROJECT_VALID_TRANSITIONS",
    "ProjectStatusTransitionError",
    "ProjectNotFoundError",
    "ProjectValidationError",
    "make_sqlite_session_factory",
]