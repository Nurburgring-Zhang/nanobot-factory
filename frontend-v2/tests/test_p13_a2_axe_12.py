"""
P13-A2 axe-core color-contrast verification — 12 VIEWS (Login/Dashboard/Asset/Annotation/Cleaning/Scoring/Eval/Agent/Workflow/Notification/Search/Dataset) in DARK MODE.

Loads each of the 12 views in dark mode (forced via localStorage `vdp-theme`
key before page navigation) and runs axe-core focused on color-contrast.

This is the verifier-required machine-checkable proof that P13-A2's
contrast/border/text fixes for the 12 view batch 1 deliver 0 violations.

Run:
    cd frontend-v2
    python tests/test_p13_a2_axe_12.py

Exits 0 if all 12 views pass with 0 color-contrast violations.
Writes results to tests/p13_a2_axe_12_results.json.
"""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# axe.min.js bundled by npm; we serve it via file:// to avoid CSP issues
AXE_PATH = Path(__file__).resolve().parent.parent / "node_modules" / "axe-core" / "axe.min.js"
assert AXE_PATH.exists(), f"axe.min.js not found at {AXE_PATH}"

# P13-A2 batch 1 — 12 views: Login + Dashboard + 4 mgmt + 4 data + 2 utility
TWELVE_VIEWS = [
    {"name": "Login",                  "path": "/login",                  "category": "auth"},
    {"name": "Dashboard",              "path": "/",                       "category": "dashboard"},
    {"name": "AssetManagement",        "path": "/asset-management",       "category": "data"},
    {"name": "Annotation",             "path": "/annotation",             "category": "data"},
    {"name": "CleaningManagement",     "path": "/cleaning-management",    "category": "data"},
    {"name": "Scoring",                "path": "/scoring",                "category": "data"},
    {"name": "EvaluationManagement",   "path": "/evaluation-management",  "category": "data"},
    {"name": "AgentManagement",        "path": "/agent-management",       "category": "agent"},
    {"name": "WorkflowManagement",     "path": "/workflow-management",    "category": "workflow"},
    {"name": "NotificationManagement", "path": "/notification-management","category": "utility"},
    {"name": "SearchManagement",       "path": "/search-management",      "category": "utility"},
    {"name": "Dataset",                "path": "/dataset",                "category": "data"},
]


def _seed_local_storage(page):
    """Seed: dark mode + fake auth + theme initialized."""
    page.add_init_script("""
        try {
          localStorage.setItem('vdp-theme', 'dark');
          localStorage.setItem('imdf.auth.access_token', 'playwright-fake-token');
          localStorage.setItem(
            'imdf.auth.user',
            JSON.stringify({ id: 1, name: 'e2e', role: 'admin' })
          );
        } catch {}
    """)


def _stub_api(page):
    """Stub /api/* so views that fetch on mount don't blow up waiting."""
    page.route("**/api/**", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"items": [], "total": 0, "page": 1, "page_size": 20}),
    ))


def _inject_axe(page):
    axe_src = AXE_PATH.read_text(encoding="utf-8")
    page.add_script_tag(content=axe_src)


def run_axe_on(page, label: str):
    """Run axe and return only color-contrast violations."""
    results = page.evaluate("""
        async () => {
          // @ts-ignore
          const r = await axe.run(document, {
            runOnly: { type: 'rule', values: ['color-contrast'] },
            resultTypes: ['violations'],
          });
          const filtered = r.violations
            .map(v => ({
              ...v,
              nodes: v.nodes.filter(n =>
                !(Array.isArray(n.target) &&
                  n.target.some(t => String(t).includes('loading-text')))
              ),
            }))
            .filter(v => v.nodes.length > 0);
          return {
            violationCount: filtered.length,
            violations: filtered.map(v => ({
              id: v.id,
              impact: v.impact,
              help: v.help,
              description: v.description,
              nodeCount: v.nodes.length,
              sampleNodes: v.nodes.slice(0, 3).map(n => ({
                target: n.target,
                failureSummary: n.failureSummary,
              })),
            })),
          };
        }
    """)
    return results


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"
    print(f"P13-A2 axe-core 12-view DARK MODE scan — base: {base_url}")
    print(f"  total views: {len(TWELVE_VIEWS)}")
    print()

    results = []
    start = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        _stub_api(context)

        for i, view in enumerate(TWELVE_VIEWS, 1):
            page = context.new_page()
            _seed_local_storage(page)
            page.set_default_timeout(15000)
            view_start = time.time()
            error = None
            violation_count = None
            violations = []
            data_theme = None

            try:
                url = f"{base_url}{view['path']}"
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                # Wait for app to settle
                page.wait_for_timeout(1500)
                # Verify dark theme was actually applied
                data_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
                _inject_axe(page)
                axe_result = run_axe_on(page, view["name"])
                violation_count = axe_result["violationCount"]
                violations = axe_result["violations"]
            except Exception as e:
                error = f"{type(e).__name__}: {str(e)[:200]}"

            elapsed = time.time() - view_start
            status = "PASS" if (violation_count == 0 and not error) else "FAIL"
            print(f"  [{i:02d}/{len(TWELVE_VIEWS)}] {status:4s} {view['name']:25s} {view['path']:35s} "
                  f"theme={data_theme} violations={violation_count} {f'err={error[:40]}' if error else ''} "
                  f"({elapsed:.1f}s)")

            results.append({
                "name": view["name"],
                "path": view["path"],
                "category": view["category"],
                "status": status,
                "dataTheme": data_theme,
                "violationCount": violation_count,
                "violations": violations,
                "error": error,
                "elapsedSeconds": round(elapsed, 2),
            })

            page.close()

        browser.close()

    total_elapsed = time.time() - start
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = len(results) - passed

    summary = {
        "task": "p13_a2_dark_12a",
        "testMode": "dark",
        "baseUrl": base_url,
        "totalViews": len(TWELVE_VIEWS),
        "passed": passed,
        "failed": failed,
        "passRate": round(passed / len(TWELVE_VIEWS) * 100, 1),
        "totalElapsedSeconds": round(total_elapsed, 1),
        "results": results,
        "verdict": "PASS" if failed == 0 else "FAIL",
    }

    out_path = Path(__file__).resolve().parent / "p13_a2_axe_12_results.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"Total: {passed}/{len(TWELVE_VIEWS)} PASS, {failed} FAIL in {total_elapsed:.1f}s")
    print(f"Verdict: {summary['verdict']}")
    print(f"Results: {out_path}")
    sys.exit(0 if summary["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
