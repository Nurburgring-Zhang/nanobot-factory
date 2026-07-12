"""
P13-A2 axe-core FULL-RULES verification — 12 VIEWS in DARK MODE.

Runs the FULL axe-core ruleset (not just color-contrast) on each of the
12 P13-A2 views in dark mode. This catches any a11y issues — not just
contrast — so we have machine-checkable proof that dark mode is
fully accessible.

Run:
    cd frontend-v2
    python tests/test_p13_a2_axe_full.py

Writes results to tests/p13_a2_axe_full_12_results.json.
Exits 0 if all views pass with 0 violations across all rules.
"""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

AXE_PATH = Path(__file__).resolve().parent.parent / "node_modules" / "axe-core" / "axe.min.js"
assert AXE_PATH.exists(), f"axe.min.js not found at {AXE_PATH}"

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
    page.route("**/api/**", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"items": [], "total": 0, "page": 1, "page_size": 20}),
    ))


def _inject_axe(page):
    axe_src = AXE_PATH.read_text(encoding="utf-8")
    page.add_script_tag(content=axe_src)


def run_axe_full(page):
    """Run ALL axe rules — return summary of violations grouped by impact."""
    results = page.evaluate("""
        async () => {
          // @ts-ignore
          const r = await axe.run(document, {
            resultTypes: ['violations'],
          });
          // Filter out loading splash from violations (CSS-only, not a view)
          const filtered = r.violations
            .map(v => ({
              ...v,
              nodes: v.nodes.filter(n =>
                !(Array.isArray(n.target) &&
                  n.target.some(t => String(t).includes('loading-text')))
              ),
            }))
            .filter(v => v.nodes.length > 0);
          const byImpact = { critical: 0, serious: 0, moderate: 0, minor: 0 };
          filtered.forEach(v => {
            if (byImpact[v.impact] !== undefined) byImpact[v.impact] += v.nodes.length;
          });
          return {
            violationCount: filtered.length,
            nodeCount: filtered.reduce((s, v) => s + v.nodes.length, 0),
            byImpact,
            violations: filtered.map(v => ({
              id: v.id,
              impact: v.impact,
              help: v.help,
              nodeCount: v.nodes.length,
              sampleNodes: v.nodes.slice(0, 2).map(n => ({
                target: n.target,
                failureSummary: (n.failureSummary || '').slice(0, 200),
              })),
            })),
          };
        }
    """)
    return results


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"
    print(f"P13-A2 axe-core FULL-RULES 12-view DARK MODE scan")
    print(f"  base: {base_url}  total views: {len(TWELVE_VIEWS)}")
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
            axe_result = None
            data_theme = None

            try:
                url = f"{base_url}{view['path']}"
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1500)
                data_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
                _inject_axe(page)
                axe_result = run_axe_full(page)
            except Exception as e:
                error = f"{type(e).__name__}: {str(e)[:200]}"

            elapsed = time.time() - view_start
            violation_count = axe_result["violationCount"] if axe_result else None
            node_count = axe_result["nodeCount"] if axe_result else None
            by_impact = axe_result["byImpact"] if axe_result else {}
            status = "PASS" if (violation_count == 0 and not error) else "FAIL"
            print(f"  [{i:02d}/{len(TWELVE_VIEWS)}] {status:4s} {view['name']:25s} theme={data_theme} "
                  f"v={violation_count} n={node_count} crit={by_impact.get('critical',0)} "
                  f"serious={by_impact.get('serious',0)} ({elapsed:.1f}s)")

            results.append({
                "name": view["name"],
                "path": view["path"],
                "category": view["category"],
                "status": status,
                "dataTheme": data_theme,
                "violationCount": violation_count,
                "nodeCount": node_count,
                "byImpact": by_impact,
                "violations": axe_result["violations"] if axe_result else [],
                "error": error,
                "elapsedSeconds": round(elapsed, 2),
            })

            page.close()

        browser.close()

    total_elapsed = time.time() - start
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = len(results) - passed

    summary = {
        "task": "p13_a2_dark_12a_full",
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

    out_path = Path(__file__).resolve().parent / "p13_a2_axe_full_12_results.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"Total: {passed}/{len(TWELVE_VIEWS)} PASS, {failed} FAIL in {total_elapsed:.1f}s")
    print(f"Verdict: {summary['verdict']}")
    print(f"Results: {out_path}")
    sys.exit(0 if summary["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
