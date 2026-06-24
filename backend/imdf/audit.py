#!/usr/bin/env python3
"""
IMDF 执行审计器 — 在每次提交/启动前自动检查
不允许: 静太展示/占位符/模拟数据/假装实现
"""
import sys, os, re, json
from pathlib import Path

BASE = Path(__file__).parent
ERRORS = []

def check_static_placeholder():
    """检查前端HTML中是否有纯展示占位符"""
    canvas_web = BASE / "api" / "canvas_web.py"
    if not canvas_web.exists():
        return
    
    content = canvas_web.read_text()
    
    # 检查HTML_TEMPLATE中是否有真正的JS交互
    if "addEventListener" not in content:
        ERRORS.append("❌ HTML_TEMPLATE 没有 addEventListener — 纯静态展示, 不是真实交互")
    if "ondrag" not in content.lower() and "draggable" not in content.lower():
        ERRORS.append("❌ HTML_TEMPLATE 没有拖拽支持 — 节点不能移动")
    if "fetch(" not in content:
        ERRORS.append("❌ HTML_TEMPLATE 没有 fetch() 调用 — 没连后端API")
    if "FileReader" not in content and "input type=\"file\"" not in content:
        ERRORS.append("❌ HTML_TEMPLATE 没有文件上传支持")

def check_mock_data():
    """检查所有Python文件中是否有模拟/假装数据"""
    for py_file in BASE.rglob("*.py"):
        if "node_modules" in str(py_file) or "__pycache__" in str(py_file):
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 占位符检测
            if re.search(r'placeholder|假的|假装|mock|TODO|FIXME|临时|先用', stripped, re.IGNORECASE):
                ERRORS.append(f"⚠️ 占位符残留: {py_file.name}:{i+1}: {stripped[:80]}")

def check_hardcoded_paths():
    """检查硬编码路径"""
    patterns = [r'/mnt/', r'D:\\', r'D:/', r'/home/']
    for py_file in BASE.rglob("*.py"):
        if "node_modules" in str(py_file) or "__pycache__" in str(py_file):
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for pat in patterns:
            if re.search(pat, content):
                ERRORS.append(f"❌ 硬编码路径: {py_file.name} — {pat}")

def main():
    print("=" * 50)
    print("  IMDF 执行审计器")
    print("  违反规则 = 阻断启动")
    print("=" * 50)
    
    check_static_placeholder()
    check_mock_data()
    check_hardcoded_paths()
    
    if ERRORS:
        print(f"\n❌ 发现 {len(ERRORS)} 个违规:\n")
        for err in ERRORS:
            print(f"  {err}")
        print("\n⚠️  修复所有违规后才能启动")
        sys.exit(1)
    else:
        print("\n✅ 审计通过, 无违规")
        sys.exit(0)

if __name__ == "__main__":
    main()
