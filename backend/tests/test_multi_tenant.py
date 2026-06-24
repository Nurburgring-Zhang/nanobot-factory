"""Tests for multi-tenant user/project/role management"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from core.multi_tenant import UserManager, UserRole, User

def test_default_admin():
    um = UserManager()
    users = um.get_all_users()
    assert len(users) == 1
    assert users[0].username == "admin"
    assert users[0].role == UserRole.ADMIN

def test_create_user():
    um = UserManager()
    u = um.create_user("test_user", UserRole.OPERATOR)
    assert u.username == "test_user"
    assert u.role == UserRole.OPERATOR
    assert u.api_key.startswith("nbk-")

def test_authenticate():
    um = UserManager()
    u = um.create_user("auth_test")
    found = um.authenticate(u.api_key)
    assert found is not None
    assert found.username == "auth_test"

def test_authenticate_wrong_key():
    um = UserManager()
    found = um.authenticate("wrong_key")
    assert found is None

def test_create_project():
    um = UserManager()
    u = um.create_user("proj_user", UserRole.OPERATOR)
    p = um.create_project(u.id, "My Project", "Description")
    assert p is not None
    assert p.name == "My Project"
    assert p.user_id == u.id

def test_project_quota():
    um = UserManager()
    u = um.create_user("quota_user")
    for i in range(u.quota.max_projects):
        p = um.create_project(u.id, f"proj{i}")
        assert p is not None
    # 配额用尽，下一个应该失败
    p = um.create_project(u.id, "overflow")
    assert p is None

def test_get_user_projects():
    um = UserManager()
    u = um.create_user("list_user", UserRole.ADMIN)
    um.create_project(u.id, "A")
    um.create_project(u.id, "B")
    projects = um.get_user_projects(u.id)
    assert len(projects) == 2

def test_check_permission_admin():
    um = UserManager()
    admin = um.get_user("u-admin-001")
    p = um.create_project(admin.id, "admin_proj")
    # admin可以访问任何项目
    assert um.check_permission(admin.id, p.id, UserRole.ADMIN)

def test_check_permission_operator():
    um = UserManager()
    u = um.create_user("op_user", UserRole.OPERATOR)
    p = um.create_project(u.id, "op_proj")
    # operator可以访问自己项目
    assert um.check_permission(u.id, p.id, UserRole.OPERATOR)
    # 但不能做admin操作
    assert not um.check_permission(u.id, p.id, UserRole.ADMIN)

def test_cross_user_permission():
    um = UserManager()
    u1 = um.create_user("user1", UserRole.OPERATOR)
    u2 = um.create_user("user2", UserRole.OPERATOR)
    p = um.create_project(u1.id, "u1_proj")
    # u2不能访问u1的项目
    assert not um.check_permission(u2.id, p.id, UserRole.VIEWER)

def test_get_user():
    um = UserManager()
    u = um.create_user("get_test")
    found = um.get_user(u.id)
    assert found is not None
    assert found.id == u.id
    assert um.get_user("nonexistent") is None

def test_inactive_user():
    um = UserManager()
    u = um.create_user("inactive_user")
    u.is_active = False
    found = um.authenticate(u.api_key)
    assert found is None
