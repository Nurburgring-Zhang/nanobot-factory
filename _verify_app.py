import sys
sys.path.insert(0, "backend")
from services.dataset_service.main import app
routes = [(r.path, getattr(r, "methods", None)) for r in app.routes if hasattr(r, "path")]
metadata_routes = [r for r in routes if "/metadata" in r[0]]
print("total_routes:", len(routes))
print("metadata_routes:", len(metadata_routes))
for p, m in metadata_routes[:8]:
    print("  ", sorted(m) if m else "-", p)
print("---")
print("sample metadata routes (last 5):")
for p, m in metadata_routes[-5:]:
    print("  ", sorted(m) if m else "-", p)
