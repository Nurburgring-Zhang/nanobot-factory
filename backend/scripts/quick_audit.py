#!/usr/bin/env python3
"""Quick Audit Test"""
import sys, os, py_compile
from pathlib import Path
os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent.parent))
print("=" * 60)
print("PYTHON MODULE SYNTAX CHECK")
print("=" * 60)
modules = ["backend/skills.py","backend/production_agents.py","backend/agent_reach.py","backend/world_monitor.py","backend/omni_gen.py","backend/database_manager.py","backend/annotation_system_enhanced.py","backend/ai_annotation_service.py"]
passed = 0; failed = 0
for mod in modules:
    try:
        py_compile.compile(mod, doraise=True)
        print(f"[OK] {mod}")
        passed += 1
    except Exception as e:
        print(f"[FAIL] {mod}: {e}")
        failed += 1
print(f"\nResults: {passed} passed, {failed} failed")
print("\n" + "=" * 60)
print("IMPORT TEST")
print("=" * 60)
import_tests = [("backend.skills","SkillManager"),("backend.omni_gen","get_omni_gen"),("backend.database_manager","DatabaseManager")]
for module_name, class_name in import_tests:
    try:
        module = __import__(module_name, fromlist=[class_name])
        cls = getattr(module, class_name, None)
        if cls:
            print(f"[OK] {module_name}.{class_name}")
        else:
            print(f"[FAIL] {module_name}.{class_name} - Not found")
    except Exception as e:
        print(f"[FAIL] {module_name}.{class_name}: {e}")
print("\n" + "=" * 60)
print("CHECK MISSING FUNCTIONS")
print("=" * 60)
try:
    with open("backend/omni_gen.py","r",encoding="utf-8") as f: content = f.read()
    if "def text_to_video" in content: print("[OK] text_to_video method found")
    else: print("[WARN] text_to_video method NOT found")
    if "MeshData" in content or "export_mesh" in content: print("[OK] 3D export MeshData found")
    else: print("[WARN] 3D export MeshData NOT found")
except Exception as e: print(f"[ERROR] {e}")
try:
    with open("backend/database_manager.py","r",encoding="utf-8") as f: db_content = f.read()
    if "pymysql" in db_content: print("[OK] MySQL (pymysql) support found")
    else: print("[WARN] MySQL (pymysql) NOT found")
    if "pymongo" in db_content: print("[OK] MongoDB (pymongo) support found")
    else: print("[WARN] MongoDB (pymongo) NOT found")
except Exception as e: print(f"[ERROR] {e}")
print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
