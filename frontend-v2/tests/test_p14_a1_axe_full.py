"""
P14-A1 axe-core full-rules verification — 12 VIEWS (batch 2) DARK MODE
Boundary check: run ALL axe rules, not just color-contrast.
If full-rules == 0 violations, P14-A1 is bulletproof.
If full-rules != 0, identify which violations are dark-mode-introduced
(only present in dark, not light) — those are scope. Pre-existing a11y
issues (Naive UI library, DefaultLayout, page-has-heading-one) are out of scope.

Run:
    cd frontend-v2
    python tests/test_p14_a1_axe_full.py

Writes results to tests/p14_a1_axe_full_12_results.json.
"""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

AXE_PATH = Path(__file__).resolve().parent.parent / "node_modules" / "axe-core" / "axe.min.js"
assert AXE_PATH.exists(), f"axe.min.js not found at {AXE_PATH}"

TWELVE_VIEWS = [
    {"name": "CanvasDesigner",  "path": "/canvas-designer"},
    {"name": "UserManagement",  "path": "/user-management"},
    {"name": "Billing",         "path": "/billing"},
    {"name": "Tickets",         "path": "/tickets"},
    {"name": "CRM",             "path": "/crm"},
    {"name": "Invoices",        "path": "/invoices"},
    {"name": "Contracts",       "path": "/contracts"},
    {"name": "MemoryPalace",    "path": "/obsidian/wiki"},
    {"name": "KnowledgeGraph",  "path": "/obsidian/graph"},
    {"name": "Skill",           "path": "/skills"},
    {"name": "IterativeStudio", "path": "/assets/storyboard"},
    {"name": "CharacterAsset",  "path": "/obsidian/wiki/memory-palace"},
]


def _seed_local_storage(page):
    page.add_init_script("""
        try {
          localStorage.setItem('vdp-theme', 'dark');
          localStorage.setItem('imdf.auth.access_token', 'playwright-fake-token');
          localStorage.setItem('imdf.auth.user',
            JSON.stringify({ id: 1, name: 'e2e', role: 'admin' }));
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


def run_full_axe(page):
    """Run ALL axe rules (not just color-contrast)."""
    return page.evaluate("""
        async () => {
          // @ts-ignore
          const r = await axe.run(document, {
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
              sampleNodes: v.nodes.slice(0, 2).map(n => ({
                target: n.target,
                failureSummary: n.failureSummary,
              })),
            })),
          };
        }
    """)


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"
    print(f"P14-A1 axe-core FULL-RULES 12-view DARK scan (batch 2) — base: {base_url}")
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
            axe_result = None
            data_theme = None

            try:
                url = f"{base_url}{view['path']}"
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1500)
                data_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
                _inject_axe(page)
                axe_result = run_full_axe(page)
            except Exception as e:
                error = f"{type(e).__name__}: {str(e)[:200]}"

            elapsed = time.time() - view_start
            vcount = axe_result["violationCount"] if axe_result else None
            status = "PASS" if (vcount == 0 and not error) else "FAIL"
            print(f"  [{i:02d}/{len(TWELVE_VIEWS)}] {status:4s} {view['name']:20s} {view['path']:35s} "
                  f"theme={data_theme} violations={vcount} ({elapsed:.1f}s)")

            results.append({
                "name": view["name"],
                "path": view["path"],
                "status": status,
                "dataTheme": data_theme,
                "violationCount": vcount,
                "violations": axe_result["violations"] if axe_result else [],
                "error": error,
                "elapsedSeconds": round(elapsed, 2),
            })
            page.close()

        browser.close()

    total = time.time() - start
    passed = sum(1 for r in results if r["status"] == "PASS")
    summary = {
        "task": "p14_a1_dark_12b_full",
        "testMode": "dark",
        "baseUrl": base_url,
        "totalViews": len(TWELVE_VIEWS),
        "passed": passed,
        "failed": len(TWELVE_VIEWS) - passed,
        "passRate": round(passed / len(TWELVE_VIEWS) * 100, 1),
        "totalElapsedSeconds": round(total, 1),
        "results": results,
        "verdict": "PASS" if passed == len(TWELVE_VIEWS) else "FAIL",
    }
    out_path = Path(__file__).resolve().parent / "p14_a1_axe_full_12_results.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"Total: {passed}/{len(TWELVE_VIEWS)} PASS in {total:.1f}s")
    print(f"Verdict: {summary['verdict']}")
    print(f"Results: {out_path}")
    sys.exit(0 if summary["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()