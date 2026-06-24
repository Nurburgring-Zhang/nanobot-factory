"""Debug: try to import the test app to see what fails"""
import os
import sys

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
_IMDF = os.path.join(_BACKEND, "imdf")
sys.path[:] = [p for p in sys.path if p not in (_BACKEND, _IMDF)]
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _IMDF)

print(f"sys.path[0:3]: {sys.path[0:3]}")
print(f"backend exists: {os.path.exists(_BACKEND)}")
print(f"imdf exists: {os.path.exists(_IMDF)}")
print(f"imdf/api/_common: {os.path.exists(os.path.join(_IMDF, 'api', '_common'))}")

# Try simple import
try:
    from api._common.date_range import DateRangeParams
    print("[OK] from api._common.date_range")
except Exception as e:
    print(f"[FAIL] from api._common.date_range: {e!r}")

# Try routes_extended
try:
    from api.routes_extended import stats_router
    print("[OK] from api.routes_extended")
except Exception as e:
    print(f"[FAIL] from api.routes_extended: {e!r}")
    import traceback
    traceback.print_exc()

# Try each module that test imports
modules_to_test = [
    "api.monitor_routes",
    "api.ops_dashboard_routes",
    "api.audit_routes",
    "api.personnel_routes",
    "api.pe_routes",
    "api.dam_routes",
    "api.template_routes",
    "api.quality_v2_routes",
    "api.webhook_routes",
]
for m in modules_to_test:
    try:
        __import__(m)
        print(f"[OK] {m}")
    except Exception as e:
        print(f"[FAIL] {m}: {e!r}")
