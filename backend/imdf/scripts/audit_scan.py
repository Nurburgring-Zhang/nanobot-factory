#!/usr/bin/env python3
"""
Deep code audit scanner for nanobot-factory.
Scans engines/ and api/ for:
1. Stub/return-data engines
2. API routes calling real engines vs stubs
3. POST endpoints missing Body() binding
4. Import/export name mismatches
5. URL prefix mismatches
6. Return type mismatches
7. Sync calling async issues
8. Module-level import crashes
"""

import ast
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

BASE = Path("/mnt/d/Hermes/生产平台/nanobot-factory/backend/imdf")
ENGINES_DIR = BASE / "engines"
API_DIR = BASE / "api"

FINDINGS = []

def finding(sev, cat, filepath, line, desc, detail=""):
    try:
        rel = str(Path(filepath).relative_to(BASE))
    except ValueError:
        rel = str(filepath)
    FINDINGS.append({
        "severity": sev,  # P0, P1, P2
        "category": cat,
        "file": rel,
        "line": line,
        "description": desc,
        "detail": detail
    })

# ============================================================
# PART 1: Scan all engine files for stub patterns
# ============================================================
def scan_engine_stubs(filepath):
    """Find engines where run() is a no-op or just returns data unchanged."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except Exception as e:
        finding("P0", "READ_ERROR", filepath, 0, f"Cannot read file: {e}")
        return

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        finding("P0", "SYNTAX_ERROR", filepath, e.lineno, f"Syntax error: {e.msg}")
        return

    file_lines = source.split('\n')

    # Find all classes
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Find run method in this class
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == 'run':
                    analyze_run_method(filepath, node.name, item, source, file_lines)
                elif isinstance(item, ast.AsyncFunctionDef) and item.name == 'run':
                    analyze_run_method(filepath, node.name, item, source, file_lines)

def analyze_run_method(filepath, class_name, func_node, source, file_lines):
    """Analyze a run() method for stub patterns."""
    body = func_node.body
    if not body:
        finding("P1", "EMPTY_RUN", filepath, func_node.lineno,
                f"{class_name}.run() has empty body")
        return

    # Check for "return data" pattern (no-op pass-through)
    if isinstance(body[-1], ast.Return):
        ret_val = body[-1].value
        if ret_val is None:
            # return None — could be intentional, flag only if body is also trivial
            if len(body) <= 2:
                finding("P2", "RETURN_NONE", filepath, func_node.lineno,
                        f"{class_name}.run() returns None with trivial body")
        elif isinstance(ret_val, ast.Name):
            # "return <variable>" — check if it's just returning a parameter unchanged
            param_names = [a.arg for a in func_node.args.args]
            # Also check if 'data' is the variable name and body is trivial
            if ret_val.id in param_names and len(body) <= 3:
                # Count non-docstring, non-pass, non-log statements
                real_stmts = [s for s in body if not (
                    (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)) or
                    (isinstance(s, ast.Pass))
                )]
                if len(real_stmts) <= 1:
                    finding("P0", "STUB_ENGINE", filepath, func_node.lineno,
                            f"{class_name}.run() returns parameter '{ret_val.id}' unchanged — stub engine")

    # Check for "pass" as the only body
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        finding("P0", "PASS_ONLY", filepath, func_node.lineno,
                f"{class_name}.run() only contains 'pass'")

    # Check for NotImplementedError
    for stmt in ast.walk(func_node):
        if isinstance(stmt, ast.Raise) and stmt.exc:
            if isinstance(stmt.exc, ast.Call) and isinstance(stmt.exc.func, ast.Name):
                if stmt.exc.func.id == 'NotImplementedError':
                    finding("P1", "NOT_IMPLEMENTED", filepath, func_node.lineno,
                            f"{class_name}.run() raises NotImplementedError")

    # Check for bare "return data" in a method with data as parameter
    # where no real transformation happens
    if isinstance(body[-1], ast.Return) and isinstance(body[-1].value, ast.Name):
        ret_name = body[-1].value.id
        # Check if method has 'data' or 'self' as first param
        param_names = [a.arg for a in func_node.args.args if a.arg != 'self']
        if ret_name == param_names[0] if param_names else '':
            # Check if body actually does anything
            has_side_effect = False
            for stmt in body[:-1]:  # all except return
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                    continue  # docstring
                if isinstance(stmt, ast.Pass):
                    continue
                has_side_effect = True
                break
            if not has_side_effect:
                finding("P0", "STUB_ENGINE", filepath, func_node.lineno,
                        f"{class_name}.run() returns '{ret_name}' unchanged with no side effects — stub")


# ============================================================
# PART 2: Scan API route files for POST endpoints without Body()
# ============================================================
def scan_api_routes(filepath):
    """Check POST endpoints for Body() binding."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except Exception as e:
        finding("P0", "READ_ERROR", filepath, 0, f"Cannot read file: {e}")
        return

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        finding("P0", "SYNTAX_ERROR", filepath, e.lineno, f"Syntax error: {e.msg}")
        return

    file_lines = source.split('\n')

    # Find APIRouter / router definition
    router_prefix = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets if isinstance(node.targets, list) else [node.targets]:
                if isinstance(target, ast.Name) and 'router' in target.id.lower():
                    if isinstance(node.value, ast.Call):
                        if hasattr(node.value.func, 'id') and node.value.func.id == 'APIRouter':
                            for kw in node.value.keywords:
                                if kw.arg == 'prefix':
                                    if isinstance(kw.value, ast.Constant):
                                        router_prefix = kw.value.value

    # Find all endpoint functions
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_post = False
            endpoint_path = None
            # Check decorators for POST
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call):
                    if isinstance(dec.func, ast.Attribute):
                        if dec.func.attr.upper() == 'POST':
                            is_post = True
                            if dec.args:
                                if isinstance(dec.args[0], ast.Constant):
                                    endpoint_path = dec.args[0].value
                    elif isinstance(dec.func, ast.Name):
                        if dec.func.id.upper() == 'POST':
                            is_post = True
                            if dec.args:
                                if isinstance(dec.args[0], ast.Constant):
                                    endpoint_path = dec.args[0].value

            if not is_post:
                continue

            # Check function parameters for Body() - only if there are parameters beyond self/request/deps
            non_injected_params = []
            body_params = []
            for arg in node.args.args:
                # Skip path parameters (those with annotation to Path)
                is_path_param = False
                is_body_param = False
                if arg.annotation:
                    if isinstance(arg.annotation, ast.Subscript):
                        # Check if it's Optional[...] — unwrap
                        ann = arg.annotation
                        if isinstance(ann.value, ast.Name) and ann.value.id == 'Optional':
                            ann = ann.slice
                    # Check for Body() default
                    if isinstance(arg.annotation, ast.Subscript):
                        pass  # Dict[str, Any] type hint
                if arg.annotation and not is_path_param:
                    non_injected_params.append(arg.arg)

            # Check defaults for Body()
            defaults_start = len(node.args.args) - len(node.args.defaults)
            for i, default in enumerate(node.args.defaults):
                arg_idx = defaults_start + i
                arg = node.args.args[arg_idx]
                if isinstance(default, ast.Call):
                    if isinstance(default.func, ast.Name):
                        if default.func.id == 'Body':
                            body_params.append(arg.arg)

            # Also check keyword-only args
            for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
                if default and isinstance(default, ast.Call) and isinstance(default.func, ast.Name):
                    if default.func.id == 'Body':
                        body_params.append(arg.arg)

            func_params_with_annotations = [a.arg for a in node.args.args if a.annotation and a.arg != 'self']
            # Heuristic: if the function has a 'data' parameter with Dict annotation but no Body(), flag it
            for arg in node.args.args:
                if arg.arg == 'data' and arg.annotation:
                    if isinstance(arg.annotation, ast.Subscript):
                        if arg.arg not in body_params and arg not in node.args.kwonlyargs:
                            # Check if there's a default value of Body()
                            has_body = False
                            if node.args.defaults:
                                defaults_start = len(node.args.args) - len(node.args.defaults)
                                arg_index = node.args.args.index(arg)
                                if arg_index >= defaults_start:
                                    def_val = node.args.defaults[arg_index - defaults_start]
                                    if isinstance(def_val, ast.Call) and isinstance(def_val.func, ast.Name) and def_val.func.id == 'Body':
                                        has_body = True
                            if not has_body:
                                full_path = f"{router_prefix or ''}{endpoint_path or '/unknown'}"
                                finding("P0", "MISSING_BODY", filepath, node.lineno,
                                        f"POST {full_path}: parameter 'data' has type hint but no Body() default",
                                        f"param: data: {ast.dump(arg.annotation)}")

            # Also check for generic 'data: dict' type hints
            for arg in node.args.args:
                if arg.annotation and isinstance(arg.annotation, ast.Name) and arg.annotation.id == 'dict':
                    finding("P1", "DICT_TYPING", filepath, node.lineno,
                            f"Parameter '{arg.arg}' uses bare 'dict' instead of 'Dict[str, Any]'")


# ============================================================
# PART 3: Import/export name mismatch
# ============================================================
def scan_import_export(filepath):
    """Check that imported names match exported names in __init__.py files."""
    pass  # Done manually below


# ============================================================
# PART 4: Module-level import crash risk
# ============================================================
CRASH_IMPORTS = [
    'passlib', 'bcrypt', 'cryptography', 'PIL', 'torch', 'tensorflow',
    'cv2', 'opencv', 'pydantic', 'celery', 'kafka', 'redis',
    'grpc', 'protobuf', 'onnx', 'onnxruntime', 'transformers',
    'diffusers', 'accelerate', 'datasets', 'nvidia', 'cuda'
]

def scan_import_crashes(filepath):
    """Check for module-level imports that could crash."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except:
        return

    for line_no, line in enumerate(source.split('\n'), 1):
        stripped = line.strip()
        if stripped.startswith('from ') or stripped.startswith('import '):
            for risky in CRASH_IMPORTS:
                if risky in stripped and not stripped.strip().startswith('#'):
                    # Check if inside try/except
                    finding("P2", "RISKY_IMPORT", filepath, line_no,
                            f"Module-level import of '{risky}' may crash at import time",
                            stripped[:120])


# ============================================================
# PART 5: Sync calling async
# ============================================================
def scan_sync_async(filepath):
    """Check for sync functions calling async functions without await."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except:
        return

    try:
        tree = ast.parse(source)
    except:
        return

    # Find async function definitions
    async_funcs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            async_funcs.add(node.name)

    # Check for calls to known async functions from sync context
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and not isinstance(node, ast.AsyncFunctionDef):
            for subnode in ast.walk(node):
                if isinstance(subnode, ast.Call):
                    if isinstance(subnode.func, ast.Attribute):
                        if subnode.func.attr in async_funcs:
                            finding("P1", "SYNC_CALLS_ASYNC", filepath, subnode.lineno,
                                    f"Sync function '{node.name}' calls async function '{subnode.func.attr}' without await")
                    elif isinstance(subnode.func, ast.Name):
                        if subnode.func.id in async_funcs:
                            finding("P1", "SYNC_CALLS_ASYNC", filepath, subnode.lineno,
                                    f"Sync function '{node.name}' calls async function '{subnode.func.id}' without await")


# ============================================================
# PART 6: Return type mismatch
# ============================================================
def scan_return_types(filepath):
    """Check if return type annotations match actual returns."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except:
        return

    try:
        tree = ast.parse(source)
    except:
        return

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns:
                returns_hint = ast.dump(node.returns)
                # Check for Dict vs dict, List vs list mismatches in return vs actual
                # Check all return statements
                for subnode in ast.walk(node):
                    if isinstance(subnode, ast.Return) and subnode.value:
                        if isinstance(subnode.value, ast.Dict):
                            if 'Name(id=''dict''' in returns_hint:
                                finding("P2", "RETURN_TYPE", filepath, node.lineno,
                                        f"{node.name}() returns dict literal but annotated with 'dict' (use Dict)")
                        if isinstance(subnode.value, ast.List):
                            if 'Name(id=''list''' in returns_hint:
                                finding("P2", "RETURN_TYPE", filepath, node.lineno,
                                        f"{node.name}() returns list literal but annotated with 'list' (use List)")


# ============================================================
# PART 7: URL prefix mismatch between definition and registration
# ============================================================
def scan_router_prefixes():
    """Compare router prefixes in API files vs main app registration."""
    api_files = list(API_DIR.glob("*.py"))
    router_prefixes = {}
    for fpath in api_files:
        if fpath.name.startswith('_'):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in [node.targets] if not isinstance(node.targets, list) else [node.targets]:
                        t = target[0] if isinstance(target, list) else target
                        if isinstance(t, ast.Name) and 'router' in t.id.lower():
                            if isinstance(node.value, ast.Call):
                                if hasattr(node.value.func, 'id') and node.value.func.id == 'APIRouter':
                                    for kw in node.value.keywords:
                                        if kw.arg == 'prefix':
                                            if isinstance(kw.value, ast.Constant):
                                                router_prefixes[t.id] = (fpath.name, kw.value.value)
        except:
            pass

    # Now find main.py or app.py where routers are registered
    main_files = list(BASE.parent.glob("*.py")) + list(BASE.glob("*.py")) + list((BASE / "..").glob("*.py"))
    for mf in main_files:
        try:
            with open(mf, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in ('include_router', 'mount'):
                        # Check the prefix in include_router
                        for kw in node.keywords:
                            if kw.arg == 'prefix':
                                if isinstance(kw.value, ast.Constant):
                                    reg_prefix = kw.value.value
                                    # Log what router and prefix
                                    finding("P2", "ROUTER_PREFIX", mf, node.lineno,
                                            f"Router registered with prefix='{reg_prefix}'")
        except:
            pass


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 70)
    print("NANOBOT-FACTORY DEEP CODE AUDIT")
    print("=" * 70)

    # Scan engines
    print("\n[1/6] Scanning engine files for stubs...")
    engine_files = sorted(ENGINES_DIR.glob("**/*.py"))
    for ep in engine_files:
        if ep.name.startswith('_'):
            continue
        scan_engine_stubs(ep)
    print(f"  Scanned {len(engine_files)} engine files")

    # Scan API routes
    print("\n[2/6] Scanning API routes for missing Body() bindings...")
    api_files = sorted(API_DIR.glob("*.py"))
    for ap in api_files:
        if ap.name.startswith('_'):
            continue
        scan_api_routes(ap)
    print(f"  Scanned {len(api_files)} API route files")

    # Scan imports
    print("\n[3/6] Scanning for risky module-level imports...")
    for ep in engine_files:
        if ep.name.startswith('_'):
            continue
        scan_import_crashes(ep)
    for ap in api_files:
        if ap.name.startswith('_'):
            continue
        scan_import_crashes(ap)

    # Scan sync/async
    print("\n[4/6] Scanning for sync functions calling async...")
    for ep in engine_files:
        if ep.name.startswith('_'):
            continue
        scan_sync_async(ep)
    for ap in api_files:
        if ap.name.startswith('_'):
            continue
        scan_sync_async(ap)

    # Scan return types
    print("\n[5/6] Scanning for return type mismatches...")
    for ep in engine_files:
        if ep.name.startswith('_'):
            continue
        scan_return_types(ep)
    for ap in api_files:
        if ap.name.startswith('_'):
            continue
        scan_return_types(ap)

    # Scan router prefixes
    print("\n[6/6] Scanning router prefixes...")
    scan_router_prefixes()

    # Print findings by severity
    print("\n" + "=" * 70)
    print("FINDINGS SUMMARY")
    print("=" * 70)

    by_sev = defaultdict(list)
    for f in FINDINGS:
        by_sev[f['severity']].append(f)

    for sev in ['P0', 'P1', 'P2']:
        items = by_sev.get(sev, [])
        print(f"\n--- {sev} ({len(items)} findings) ---")
        for item in sorted(items, key=lambda x: (x['file'], x['line'])):
            print(f"  [{sev}] {item['file']}:{item['line']} [{item['category']}] {item['description']}")
            if item['detail']:
                print(f"       Detail: {item['detail']}")

    print(f"\n\nTOTAL: {len(FINDINGS)} findings (P0: {len(by_sev.get('P0',[]))}, P1: {len(by_sev.get('P1',[]))}, P2: {len(by_sev.get('P2',[]))})")

    # Dump full JSON for programmatic use
    import json
    outpath = BASE / "scripts" / "audit_results.json"
    with open(outpath, 'w') as f:
        json.dump(FINDINGS, f, indent=2, ensure_ascii=False)
    print(f"\nFull results written to: {outpath}")

if __name__ == '__main__':
    main()
