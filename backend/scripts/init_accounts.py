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
import secrets

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
    # ---- 管理员 (P11-D-1: 密码从 ADMIN_INITIAL_PASSWORD 注入) ----
    # 注意: 在运行时会被 _resolve_admin_password() 替换为 env 提供的值
    ("admin",       "ENV:ADMIN_INITIAL_PASSWORD",  "admin",      "系统管理员",     "system",       "admin@nanobot.local"),

    # ---- 生产团队 (P12-B1: 全部从 env 注入,严禁硬编码) ----
    ("prod_lead",   "ENV:PROD_LEAD_PASSWORD",     "team_lead",  "生产负责人",     "production",   "prod_lead@nanobot.local"),
    ("qc_lead",     "ENV:QC_LEAD_PASSWORD",       "reviewer",   "质检负责人",     "production",   "qc_lead@nanobot.local"),
    ("prod_user1",  "ENV:PROD_USER1_PASSWORD",    "annotator",  "生产人员-01",    "production",   "prod_user1@nanobot.local"),
    ("prod_user2",  "ENV:PROD_USER2_PASSWORD",    "annotator",  "生产人员-02",    "production",   "prod_user2@nanobot.local"),
    ("prod_user3",  "ENV:PROD_USER3_PASSWORD",    "annotator",  "生产人员-03",    "production",   "prod_user3@nanobot.local"),

    # ---- 众包团队 ----
    ("crowd_lead",  "ENV:CROWD_LEAD_PASSWORD",    "team_lead",  "众包负责人",     "crowdsource",  "crowd_lead@nanobot.local"),
    ("crowd_mgr",   "ENV:CROWD_MGR_PASSWORD",     "reviewer",   "众包管理员",     "crowdsource",  "crowd_mgr@nanobot.local"),
    ("crowd_qc",    "ENV:CROWD_QC_PASSWORD",      "reviewer",   "众包质检",       "crowdsource",  "crowd_qc@nanobot.local"),
    ("crowd_user1", "ENV:CROWD_USER1_PASSWORD",   "annotator",  "众包生产人员",   "crowdsource",  "crowd_user1@nanobot.local"),

    # ---- 需求方 ----
    ("client1",     "ENV:CLIENT1_PASSWORD",       "viewer",     "需求方代表",     "client",       "client1@nanobot.local"),
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

def _resolve_admin_password() -> str:
    """P11-D-1: 从 env ``ADMIN_INITIAL_PASSWORD`` 解析 admin 密码。

    优先: env ``ADMIN_INITIAL_PASSWORD``
    回退: 测试模式 ``IMDF_TEST_MODE=1`` 时生成 ephemeral random 密码
    """
    return _resolve_env_password(
        "ADMIN_INITIAL_PASSWORD",
        purpose="admin account",
    )


def _resolve_env_password(env_name: str, purpose: str = "account") -> str:
    """P12-B1: 通用 env 密码解析函数 (替代所有硬编码密码)。

    优先: env ``env_name``
    回退: 测试模式 ``IMDF_TEST_MODE=1`` 时生成 ephemeral random 密码
    """
    pw = os.environ.get(env_name, "").strip()
    if pw:
        return pw
    if os.environ.get("IMDF_TEST_MODE", "").strip() == "1":
        return secrets.token_urlsafe(16)
    # 强制 fail-fast (生产模式)
    raise RuntimeError(
        f"{env_name} env var is required to bootstrap {purpose} "
        f"via init_accounts.py. Set it in .env (e.g. `python -c "
        f"'import secrets; print(secrets.token_urlsafe(24))'` to generate a "
        f"32+ char random secret) or set IMDF_TEST_MODE=1 for ephemeral "
        f"test password. The legacy hardcoded passwords have been removed "
        f"for security reasons (P12-B1)."
    )


def init_accounts(auth: UnifiedAuthManager, reset: bool = False) -> dict:
    """
    批量初始化预设账号
    Returns: {"created": [...], "skipped": [...], "errors": [...]}

    P11-D-1: admin 密码从 env ``ADMIN_INITIAL_PASSWORD`` 注入, 不再硬编码。
    """
    result = {"created": [], "skipped": [], "errors": [], "total": 0}

    for username, password, role_str, display_name, team, email in PRESET_ACCOUNTS:
        # P11-D-1 / P12-B1: 解析 env 占位符
        if password.startswith("ENV:"):
            env_name = password[4:]
            try:
                password = _resolve_env_password(env_name, purpose=username)
            except RuntimeError as e:
                result["errors"].append({
                    "username": username,
                    "reason": str(e),
                })
                print(f"  [FAIL]  {username}: {e}")
                continue
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

    # 打印 JWT 测试信息 (仅用于验证) — P11-D-1: 不再硬编码密码
    print("\n  💡 测试登录: POST /api/auth/login {\"username\":\"admin\",\"password\":\"<ADMIN_INITIAL_PASSWORD>\"}")
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
            # P11-D-1: DRY RUN 中也隐藏 admin 真实密码
            display_pw = password if not password.startswith("ENV:") else "<env:ADMIN_INITIAL_PASSWORD>"
            desc = ROLE_DESCRIPTIONS.get(role_str, "")
            team_desc = TEAM_DESCRIPTIONS.get(team, team)
            print("  " + fmt.format(username, display_pw, role_str, team_desc, desc))
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
