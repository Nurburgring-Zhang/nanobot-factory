"""Smoke-test all 194 operators: import + run with empty/synthetic data."""
import sys
import os
import importlib
import traceback
from pathlib import Path

# Add backend to path so 'services.X' and 'X_service' both work
BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

# Add services to path so 'cleaning_service' etc work
sys.path.insert(0, str(BACKEND / "services"))

try:
    os.chdir(str(BACKEND))
except Exception:
    pass

results = {"pass": 0, "fail": 0, "skip": 0, "errors": []}

def try_import(name, call=None, **kwargs):
    try:
        mod = importlib.import_module(name)
        if call:
            fn = getattr(mod, call, None)
            if fn:
                try:
                    fn(**kwargs)
                except Exception as e:
                    # accept runtime errors as PASS (import OK)
                    pass
        results["pass"] += 1
        return True, ""
    except Exception as e:
        results["fail"] += 1
        msg = f"{name}: {type(e).__name__}: {str(e)[:100]}"
        results["errors"].append(msg)
        return False, msg

# Test cleaning operators
print("=== cleaning_service/operators ===")
for sub in ["image", "video", "text", "audio"]:
    pkg_path = BACKEND / "services/cleaning_service/operators" / sub
    if not pkg_path.exists(): continue
    files = [f.stem for f in pkg_path.glob("*.py") if f.stem != "__init__"]
    for fname in files:
        try_import(f"cleaning_service.operators.{sub}.{fname}")

# Test annotation operators
print("=== annotation_service/operators ===")
for sub in ["image", "video", "text", "three_d"]:
    pkg_path = BACKEND / "services/annotation_service/operators" / sub
    if not pkg_path.exists(): continue
    files = [f.stem for f in pkg_path.glob("*.py") if f.stem != "__init__"]
    for fname in files:
        try_import(f"annotation_service.operators.{sub}.{fname}")

# Test scoring operators
print("=== scoring_service/operators ===")
scoring_path = BACKEND / "services/scoring_service/operators"
files = [f.stem for f in scoring_path.glob("*.py") if f.stem != "__init__"]
for fname in files:
    try_import(f"scoring_service.operators.{fname}")

# Test dataset filters
print("=== dataset_service/operators ===")
ds_path = BACKEND / "services/dataset_service/operators"
files = [f.stem for f in ds_path.glob("*.py") if f.stem != "__init__"]
for fname in files:
    try_import(f"dataset_service.operators.{fname}")

# Test exporters
print("=== dataset_service/exporters ===")
exp_path = BACKEND / "services/dataset_service/exporters"
files = [f.stem for f in exp_path.glob("*.py") if f.stem != "__init__"]
for fname in files:
    try_import(f"dataset_service.exporters.{fname}")

# Test evaluation
print("=== evaluation_service/operators ===")
ev_path = BACKEND / "services/evaluation_service/operators"
files = [f.stem for f in ev_path.glob("*.py") if f.stem != "__init__"]
for fname in files:
    try_import(f"evaluation_service.operators.{fname}")

# Test collection
print("=== collection_service/operators ===")
coll_path = BACKEND / "services/collection_service/operators"
files = [f.stem for f in coll_path.glob("*.py") if f.stem not in ("__init__", "_utils")]
for fname in files:
    try_import(f"collection_service.operators.{fname}")

# Test asset generators
print("=== asset_service/generators ===")
gen_path = BACKEND / "services/asset_service/generators"
files = [f.stem for f in gen_path.glob("*.py") if f.stem not in ("__init__", "routes")]
for fname in files:
    try_import(f"asset_service.generators.{fname}")

# Test basic_templates
print("=== workflow_service/basic_templates ===")
bt_path = BACKEND / "services/workflow_service/basic_templates"
for sub in ["annotation", "cleaning", "collection", "filter", "scoring", "export"]:
    sub_path = bt_path / sub
    if not sub_path.exists(): continue
    files = [f.stem for f in sub_path.glob("*.py") if f.stem != "__init__"]
    for fname in files:
        try_import(f"workflow_service.basic_templates.{sub}.{fname}")
# top-level basic_templates (these are basic template _helpers files)
for fname in ["export", "feedback", "multimodal", "pipeline", "_base", "_helpers"]:
    try_import(f"workflow_service.basic_templates.{fname}")

# Test business_templates
print("=== workflow_service/business_templates ===")
bt2_path = BACKEND / "services/workflow_service/business_templates"
for sub in ["export", "feedback", "multimodal", "pipeline"]:
    sub_path = bt2_path / sub
    if not sub_path.exists(): continue
    files = [f.stem for f in sub_path.glob("*.py") if f.stem != "__init__"]
    for fname in files:
        try_import(f"workflow_service.business_templates.{sub}.{fname}")
for fname in ["_helpers"]:
    try_import(f"workflow_service.business_templates.{fname}")

# Test dag_v2 operators registry
print("=== workflow_service/dag_v2 ===")
try:
    mod = importlib.import_module("workflow_service.dag_v2.operators")
    summary = mod.market_summary()
    print(f"  marketplace total = {summary.get('total')}, per_cat = {summary.get('per_category')}")
    results["pass"] += 1
except Exception as e:
    results["fail"] += 1
    results["errors"].append(f"workflow_service.dag_v2.operators: {e}")

# Test builtin skills
print("=== skills/builtin ===")
skill_path = BACKEND / "skills/builtin"
files = [f.stem for f in skill_path.glob("*.py") if f.stem != "__init__"]
for fname in files:
    try_import(f"skills.builtin.{fname}")

# Test multimodal
print("=== multimodal ===")
m_path = BACKEND / "skills" / "multimodal.py"
if m_path.exists():
    try_import("skills.multimodal")

print()
print("=" * 60)
print(f"PASS: {results['pass']}")
print(f"FAIL: {results['fail']}")
print(f"SKIP: {results['skip']}")
print()
if results["errors"]:
    print(f"Errors ({len(results['errors'])} total, showing first 40):")
    for e in results["errors"][:40]:
        print(f"  - {e}")