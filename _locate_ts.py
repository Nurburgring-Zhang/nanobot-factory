"""Check where TS/TSX files are located."""
import os
import fnmatch

ROOT = r"D:\Hermes\生产平台\nanobot-factory"
EXCLUDE = {'node_modules', 'venv', '.venv', '__pycache__', '.pytest_cache',
           'omni_gen_studio', '.dvc', 'dist', 'build', 'egg-info',
           '.git', 'site-packages', '.next', 'lib64', 'include', 'research'}

# Where are .ts/.tsx files?
ts_locations = {}
tsx_locations = {}
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in EXCLUDE]
    for fname in filenames:
        if fname.endswith(".ts"):
            parent = os.path.relpath(dirpath, ROOT)
            ts_locations[parent] = ts_locations.get(parent, 0) + 1
        if fname.endswith(".tsx"):
            parent = os.path.relpath(dirpath, ROOT)
            tsx_locations[parent] = tsx_locations.get(parent, 0) + 1

print("=== .ts file locations (top 15) ===")
for p, c in sorted(ts_locations.items(), key=lambda x: -x[1])[:15]:
    print(f"  {c:3d}  {p}")
print(f"\nTotal .ts: {sum(ts_locations.values())}")

print("\n=== .tsx file locations (top 15) ===")
for p, c in sorted(tsx_locations.items(), key=lambda x: -x[1])[:15]:
    print(f"  {c:3d}  {p}")
print(f"\nTotal .tsx: {sum(tsx_locations.values())}")
