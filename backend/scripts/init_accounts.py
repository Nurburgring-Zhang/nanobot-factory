#!/usr/bin/env python3
"""
Nanobot Factory - 预设账号初始化脚本
文件: scripts/init_accounts.py
功能: 批量创建11类预设账号，输出确认表
用法: python scripts/init_accounts.py
      python scripts/init_accounts.py --reset   (重置所有账号)
作者: Hermes Agent
版本: v1.0.0
"""

import os
import sys
import argparse

# 确保 backend 目录在 sys.path 中
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(SCRIPT_DIR, "..")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from auth.unified_auth import (
    UnifiedAuthManager,
    UnifiedRole,
    get_unified_auth,
    reset_unified_auth,
)


# ============================================================================
# 11 类预设账号定义
# ============================================================================

PRESET_ACCOUNTS = [
    # (username, password, role, display_name, team, email)
    # ---- 管理员 ----
    ("admin",       "Admin@2026!",  "admin",      "系统管理员",     "system",       "admin@nanobot.local"),

    # ---- 生产团队 ----
    ("prod_lead",   "Prod@2026!",   "team_lead",  "生产负责人",     "production",   "prod_lead@nanobot.local"),
    ("qc_lead",     "QC@20261!",    "reviewer",   "质检负责人",     "production",   "qc_lead@nanobot.local"),
    ("prod_user1",  "Prod1@2026!",  "annotator",  "生产人员-01",    "production",   "prod_user1@nanobot.local"),
    ("prod_user2",  "Prod2@2026!",  "annotator",  "生产人员-02",    "production",   "prod_user2@nanobot.local"),
    ("prod_user3",  "Prod3@2026!",  "annotator",  "生产人员-03",    "production",   "prod_user3@nanobot.local"),

    # ---- 众包团队 ----
    ("crowd_lead",  "Crowd@2026!",  "team_lead",  "众包负责人",     "crowdsource",  "crowd_lead@nanobot.local"),
    ("crowd_mgr",   "CrowdM@2026!", "reviewer",   "众包管理员",     "crowdsource",  "crowd_mgr@nanobot.local"),
    ("crowd_qc",    "CrowdQ@2026!", "reviewer",   "众包质检",       "crowdsource",  "crowd_qc@nanobot.local"),
    ("crowd_user1", "Crowd1@2026!", "annotator",  "众包生产人员",   "crowdsource",  "crowd_user1@nanobot.local"),

    # ---- 需求方 ----
    ("client1",     "Client@2026!", "viewer",     "需求方代表",     "client",       "client1@nanobot.local"),
]

# 角色描述映射
ROLE_DESCRIPTIONS = {
    "admin":     "超级管理员 (全部权限)",
    "team_lead": "团队负责人 (管理团队/分配任务/审核)",
    "reviewer":  "审核员 (质检/审核交付)",
    "annotator": "标注员 (执行生产/标注任务)",
    "viewer":    "查看者 (提需求/查看进度/审核交付)",
}

# 团队描述映射
TEAM_DESCRIPTIONS = {
    "system":      "系统管理",
    "production":  "生产团队",
    "crowdsource": "众包团队",
    "client":      "需求方",
}


# ============================================================================
# 初始化逻辑
# ============================================================================

def init_accounts(auth: UnifiedAuthManager, reset: bool = False) -> dict:
    """
    批量初始化预设账号
    Returns: {"created": [...], "skipped": [...], "errors": [...]}
    """
    result = {"created": [], "skipped": [], "errors": [], "total": 0}

    for username, password, role_str, display_name, team, email in PRESET_ACCOUNTS:
        existing = auth.get_user(username=username)
        if existing:
            if reset:
                # 删除旧用户后重新创建
                auth.delete_user(existing.user_id)
                print(f"  [RESET] Deleted existing user: {username}")
            else:
                result["skipped"].append({
                    "username": username,
                    "reason": "already exists",
                    "role": existing.role,
                    "user_id": existing.user_id,
                })
                print(f"  [SKIP]  {username} already exists (role={existing.role})")
                result["total"] += 1
                continue

        # 创建用户
        user = auth.register_user(
            username=username,
            password=password,
            role=role_str,
            email=email,
            display_name=display_name,
            team=team,
            metadata={
                "source": "init_accounts.py",
                "team": team,
                "role_description": ROLE_DESCRIPTIONS.get(role_str, ""),
            },
        )

        if user:
            result["created"].append({
                "username": username,
                "role": user.role,
                "team": user.team,
                "user_id": user.user_id,
                "display_name": user.display_name,
            })
            print(f"  [OK]    {username} created (role={user.role}, team={team})")
            result["total"] += 1
        else:
            result["errors"].append({
                "username": username,
                "reason": "creation failed",
            })
            print(f"  [FAIL]  {username} creation failed")

    return result


def print_confirmation_table(result: dict):
    """输出确认表"""
    print("\n" + "=" * 90)
    print("  统一认证系统 — 预设账号确认表")
    print("=" * 90)

    created = {u["username"]: u for u in result["created"]}
    skipped = {u["username"]: u for u in result["skipped"]}

    fmt = "  {:<15s} {:<18s} {:<12s} {:<12s} {:<25s}"
    print(fmt.format("用户名", "密码", "角色", "团队", "说明"))
    print("  " + "-" * 85)

    for username, password, role_str, display_name, team, email in PRESET_ACCOUNTS:
        info = created.get(username) or skipped.get(username)
        if not info:
            status_icon = "✗"
            role_display = role_str
        else:
            status_icon = "✓"
            role_display = info.get("role", role_str)

        desc = ROLE_DESCRIPTIONS.get(role_str, "")
        team_desc = TEAM_DESCRIPTIONS.get(team, team)

        print(fmt.format(
            f"{status_icon} {username}",
            password,
            role_display,
            team_desc,
            desc,
        ))

    print("  " + "-" * 85)
    print(f"  合计: {result['total']}/11 账号就绪"
          f"  (新建: {len(result['created'])},"
          f" 已存在: {len(result['skipped'])},"
          f" 失败: {len(result['errors'])})")

    if result["errors"]:
        print(f"\n  ❌ 失败账号: {', '.join(e['username'] for e in result['errors'])}")

    print("=" * 90)

    # 打印 JWT 测试信息 (仅用于验证)
    print("\n  💡 测试登录: POST /api/auth/login {\"username\":\"admin\",\"password\":\"Admin@2026!\"}")
    print("  💡 查看用户: GET /api/auth/users?token=<access_token>")
    print("  💡 重置所有: python scripts/init_accounts.py --reset")
    print()


def print_permission_summary():
    """打印角色权限摘要"""
    from auth.unified_auth import ROLE_PERMISSIONS
    print("\n" + "-" * 90)
    print("  角色权限摘要")
    print("-" * 90)
    for role in [UnifiedRole.ADMIN, UnifiedRole.TEAM_LEAD, UnifiedRole.REVIEWER,
                 UnifiedRole.ANNOTATOR, UnifiedRole.VIEWER]:
        perms = ROLE_PERMISSIONS.get(role, [])
        desc = ROLE_DESCRIPTIONS.get(role.value, "")
        print(f"  {role.value:12s} ({len(perms):2d}权限) {desc}")
        print(f"              {', '.join(perms)}")
    print("-" * 90)


# ============================================================================
# 主入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Nanobot Factory — 预设账号初始化脚本"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="删除并重建所有已存在的预设账号"
    )
    parser.add_argument(
        "--db-path", type=str, default="",
        help="认证数据库路径 (默认: backend/data/unified_auth.db)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅预览，不实际创建"
    )
    args = parser.parse_args()

    print("\n" + "█" * 90)
    print("  Nanobot Factory — 统一认证系统 · 预设账号初始化")
    print("█" * 90)

    if args.dry_run:
        print("\n  ⚠ DRY RUN MODE — 仅预览，不实际创建账号\n")
        print_permission_summary()
        fmt = "  {:<15s} {:<18s} {:<12s} {:<12s} {:<25s}"
        print("\n  " + fmt.format("用户名", "密码", "角色", "团队", "说明"))
        print("  " + "-" * 85)
        for username, password, role_str, display_name, team, email in PRESET_ACCOUNTS:
            desc = ROLE_DESCRIPTIONS.get(role_str, "")
            team_desc = TEAM_DESCRIPTIONS.get(team, team)
            print("  " + fmt.format(username, password, role_str, team_desc, desc))
        print("  " + "-" * 85)
        print(f"  共 {len(PRESET_ACCOUNTS)} 个预设账号\n")
        return

    # 初始化认证系统
    print(f"\n  初始化统一认证系统...")
    reset_unified_auth()  # 确保使用新的数据库路径
    auth = UnifiedAuthManager(db_path=args.db_path)
    print(f"  数据库路径: {auth.db.db_path}")
    print(f"  加密方式: {'Argon2id' if auth.password_manager._argon2 else 'PBKDF2-SHA256'}")

    # 执行初始化
    print(f"\n  开始初始化预设账号 (reset={args.reset})...\n")
    result = init_accounts(auth, reset=args.reset)

    # 输出确认表
    print_confirmation_table(result)

    # 权限摘要
    print_permission_summary()

    # 最终验证
    print("\n  最终验证...")
    all_users = auth.list_users()
    print(f"  数据库中现有 {len(all_users)} 个用户:")
    for u in sorted(all_users, key=lambda x: (x["team"], x["role"], x["username"])):
        print(f"    {u['username']:15s} | role={u['role']:10s} | team={u['team']:12s} | {u['display_name']}")

    print("\n  ✅ 预设账号初始化完成!\n")


if __name__ == "__main__":
    main()
