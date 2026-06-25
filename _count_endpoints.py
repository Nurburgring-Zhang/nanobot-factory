"""Count API endpoints in backend."""
import os
import re

routes_dir = r'D:\Hermes\生产平台\nanobot-factory\backend\routes'
api_dir = r'D:\Hermes\生产平台\nanobot-factory\backend\api'

total_endpoints = 0
endpoints_by_method = {}
all_endpoints = []

# Match @router.METHOD("path", ...) or @app.METHOD(...)
pattern = re.compile(r'@(?P<obj>router|app|api)\.(?P<method>get|post|put|delete|patch|websocket|head|options)\s*\(\s*["\'](?P<path>[^"\']+)["\']')

for root_dir in [routes_dir, api_dir]:
    if not os.path.exists(root_dir):
        continue
    for fname in sorted(os.listdir(root_dir)):
        if not fname.endswith('.py'):
            continue
        path = os.path.join(root_dir, fname)
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            continue
        # Find all @router.METHOD("path")
        for m in pattern.finditer(content):
            method = m.group('method').upper()
            url = m.group('path')
            total_endpoints += 1
            endpoints_by_method[method] = endpoints_by_method.get(method, 0) + 1
            all_endpoints.append((method, url, fname))

# Also check other directories for FastAPI routes
other_dirs = [r'D:\Hermes\生产平台\nanobot-factory\backend\zhiying',
              r'D:\Hermes\生产平台\nanobot-factory\backend\imdf',
              r'D:\Hermes\生产平台\nanobot-factory\backend\billing',
              r'D:\Hermes\生产平台\nanobot-factory\backend\tickets',
              r'D:\Hermes\生产平台\nanobot-factory\backend\invoices',
              r'D:\Hermes\生产平台\nanobot-factory\backend\crm',
              r'D:\Hermes\生产平台\nanobot-factory\backend\contracts',
              r'D:\Hermes\生产平台\nanobot-factory\backend\monitor',
              r'D:\Hermes\生产平台\nanobot-factory\backend\gateway',
              r'D:\Hermes\生产平台\nanobot-factory\backend\auth',
              r'D:\Hermes\生产平台\nanobot-factory\backend\annotations_enhanced',
              r'D:\Hermes\生产平台\nanobot-factory\backend\services',
              r'D:\Hermes\生产平台\nanobot-factory\backend\nanobot_factory']
for root_dir in other_dirs:
    if not os.path.exists(root_dir):
        continue
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for fname in filenames:
            if not fname.endswith('.py'):
                continue
            if any(d in dirpath for d in ['imdf/vendor', 'imdf/frontend', 'imdf/.venv', 'venv', 'tests', '__pycache__']):
                continue
            path = os.path.join(dirpath, fname)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue
            for m in pattern.finditer(content):
                method = m.group('method').upper()
                url = m.group('path')
                total_endpoints += 1
                endpoints_by_method[method] = endpoints_by_method.get(method, 0) + 1
                all_endpoints.append((method, url, fname))

print(f"Total endpoint definitions: {total_endpoints}")
unique_paths = set((m, p) for m, p, _ in all_endpoints)
print(f"Unique (method, path) pairs: {len(unique_paths)}")
print("\nBy HTTP method (total occurrences):")
for m, c in sorted(endpoints_by_method.items(), key=lambda x: -x[1]):
    print(f"  {m:8s}: {c}")
print(f"\nFirst 30 endpoints:")
for ep in all_endpoints[:30]:
    print(f"  {ep[0]:6s} {ep[1]:50s} ({ep[2]})")
