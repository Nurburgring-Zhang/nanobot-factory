"""Generate final VDP-2026 stats summary."""
import json
import pathlib
import os
import fnmatch

ROOT = pathlib.Path(r"D:\Hermes\生产平台\nanobot-factory")
EXCLUDE_DIRS = {
    "node_modules", "venv", ".venv", "__pycache__", ".pytest_cache",
    "omni_gen_studio", ".dvc", "dist", "build", "egg-info",
    ".git", "site-packages", ".next", "lib64", "include",
    "research",  # external GitHub clones (Bernini, OpenMetadata, OpenMontage)
}

def count_files(root, globs):
    total_files = 0
    total_lines = 0
    total_bytes = 0
    breakdown = {}
    for glob in globs:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for fname in filenames:
                if not fnmatch.fnmatch(fname, glob):
                    continue
                path = pathlib.Path(dirpath) / fname
                try:
                    stat = path.stat()
                except (OSError, PermissionError):
                    continue
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    total_files += 1
                    total_lines += content.count("\n") + 1
                    total_bytes += stat.st_size
                    key = glob
                    breakdown.setdefault(key, [0, 0, 0])
                    breakdown[key][0] += 1
                    breakdown[key][1] += content.count("\n") + 1
                    breakdown[key][2] += stat.st_size
                except Exception:
                    pass
    return total_files, total_lines, total_bytes, breakdown

# === Backend Python ===
f, l, b, _ = count_files(ROOT / "backend", ["*.py"])
print(f"backend/*.py: {f} files, {l} lines, {b/1024/1024:.2f} MB")

# === Frontend v2 ===
f, l, b, breakdown = count_files(ROOT / "frontend-v2" / "src", ["*.vue", "*.ts", "*.tsx", "*.js", "*.css", "*.html"])
print(f"frontend-v2/src/*: {f} files, {l} lines, {b/1024/1024:.2f} MB")
for k, v in breakdown.items():
    print(f"  {k:10s}: {v[0]:4d} files, {v[1]:6d} lines")

# === Tests ===
for p_dir, label in [(ROOT / "backend" / "tests", "backend/tests"),
                      (ROOT / "frontend-v2" / "tests", "frontend-v2/tests"),
                      (ROOT / "tests", "tests (root)")]:
    f, l, b, _ = count_files(p_dir, ["test_*.py"])
    if f > 0:
        print(f"{label}: {f} files, {l} lines")

# === Infrastructure ===
for sub in ["monitoring", "deploy", "scripts", "docs", "helm", "k8s", ".github", "config"]:
    p = ROOT / sub
    if p.exists():
        f, l, b, _ = count_files(p, ["*"])
        if f > 0:
            print(f"{sub}: {f} files, {l} lines, {b/1024/1024:.2f} MB")

# === Reports ===
p = ROOT / "reports"
if p.exists():
    f, l, b, _ = count_files(p, ["*.md"])
    print(f"reports/*.md: {f} files, {l} lines")

# === Total ===
all_globs = ["*.py", "*.ts", "*.tsx", "*.vue", "*.js", "*.md", "*.yaml", "*.yml", "*.json", "*.sh"]
f, l, b, breakdown = count_files(ROOT, all_globs)
print(f"\n=== TOTAL (excl. research/ venvs/ node_modules/ dist) ===")
print(f"  {f} files, {l} lines, {b/1024/1024:.2f} MB")
print(f"\n=== Per-language ===")
for lang, (ff, ll, bb) in sorted(breakdown.items(), key=lambda x: -x[1][1]):
    print(f"  {lang:8s}: {ff:5d} files, {ll:8d} lines, {bb/1024/1024:6.2f} MB")
