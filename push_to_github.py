#!/usr/bin/env python3
"""
Nanobot Factory — GitHub 一键发布脚本
==============================
本地代码已全部提交 (580 files, 804K lines, commit ac71116)
只需提供 GitHub Personal Access Token (classic, repo权限)
然后运行此脚本即可自动创建仓库并推送。

获取 Token: https://github.com/settings/tokens → Generate new token (classic)
权限: repo (全部勾选)
"""

import sys, os, json, urllib.request, subprocess

PROJECT_DIR = r"/mnt/d/Hermes/生产平台/nanobot-factory"
REPO_NAME = "nanobot-factory"
REPO_DESC = "Nanobot Factory — Full-modal AI data production platform. 12-quality-stage pipeline, IMDF multi-user, multi-agent orchestration. Backend: FastAPI+Celery, Frontend: Vue3+Vite ComfyUI-style nodes."
GITHUB_USER = "Nurburgring-Zhang"

def main():
    if len(sys.argv) < 2:
        print("❌ 用法: python3 push_to_github.py <GITHUB_TOKEN>")
        print("   去 https://github.com/settings/tokens 创建 classic token (repo 权限)")
        sys.exit(1)
    
    token = sys.argv[1]
    os.chdir(PROJECT_DIR)
    
    # 1. 创建 GitHub 仓库
    print("=== 1. 创建 GitHub 仓库 ===")
    data = json.dumps({
        "name": REPO_NAME,
        "description": REPO_DESC,
        "private": False,
        "has_issues": True,
        "has_wiki": True,
        "has_projects": True
    }).encode()
    
    req = urllib.request.Request(
        "https://api.github.com/user/repos",
        data=data,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            if "full_name" in result:
                print(f"✅ 仓库已创建: https://github.com/{result['full_name']}")
            else:
                print(f"ℹ️ 响应: {result.get('html_url', result)}")
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        if "already exists" in str(err):
            print(f"⚠️ 仓库已存在，将推送到已有仓库")
        else:
            print(f"❌ 创建失败: {err}")
            # 继续尝试推送（仓库可能已存在）
    
    # 2. 设置 remote 并推送
    print("\n=== 2. 推送代码 ===")
    remote_url = f"https://{token}@github.com/{GITHUB_USER}/{REPO_NAME}.git"
    
    subprocess.run(["git", "remote", "remove", "origin"], capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", remote_url], check=True)
    
    print("🚀 推送到 GitHub...")
    result = subprocess.run(["git", "push", "-u", "origin", "main"], capture_output=True, text=True)
    
    # 隐藏 token
    output = result.stdout.replace(token, "***TOKEN***")
    err_output = result.stderr.replace(token, "***TOKEN***")
    
    if result.returncode == 0:
        print("✅ 推送成功！")
    else:
        # 可能是 403，尝试强制推送
        print(f"⚠️ 推送输出: {output}")
        print(f"⚠️ 错误: {err_output}")
        
        if "403" in err_output or "denied" in err_output.lower():
            print("   token 可能权限不足，需要 repo 权限")
            print("   尝试 SSH 方式...")
            subprocess.run(["git", "remote", "remove", "origin"], capture_output=True)
            ssh_url = f"git@github.com:{GITHUB_USER}/{REPO_NAME}.git"
            subprocess.run(["git", "remote", "add", "origin", ssh_url], check=True)
            result2 = subprocess.run(["git", "push", "-u", "origin", "main"], capture_output=True, text=True)
            print(result2.stdout)
            if result2.returncode != 0:
                print(f"SSH 也失败: {result2.stderr}")
                sys.exit(1)
    
    # 3. 清理：将 remote URL 改为公开的 SSH URL（不包含 token）
    subprocess.run(["git", "remote", "set-url", "origin", f"git@github.com:{GITHUB_USER}/{REPO_NAME}.git"], check=True)
    
    print(f"\n✅ 发布完成！")
    print(f"仓库地址: https://github.com/{GITHUB_USER}/{REPO_NAME}")
    print(f"克隆命令: git clone git@github.com:{GITHUB_USER}/{REPO_NAME}.git")


if __name__ == "__main__":
    main()