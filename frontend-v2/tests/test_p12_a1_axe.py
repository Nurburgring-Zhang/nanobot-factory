"""
P12-A1 axe-core color-contrast verification.

Loads 5 representative views in light mode (default) and runs axe-core
focused on the color-contrast rule. The SPA has been retuned in P11-C /
P12-A1 so the success/primary hues hit AA Normal Text; this script is the
machine-checkable proof.

Run:
    cd frontend-v2
    python tests/test_p12_a1_axe.py

Exits 0 if all 5 views pass with 0 color-contrast violations.
"""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# axe.min.js bundled by npm; we serve it via file:// to avoid CSP issues
AXE_PATH = Path(__file__).resolve().parent.parent / "node_modules" / "axe-core" / "axe.min.js"
assert AXE_PATH.exists(), f"axe.min.js not found at {AXE_PATH}"

# 5 representative views: spread across the SPA's major surfaces so we cover
# the most-used brand-tinted paths (primary CTA, success card, warning chip,
# table link, login gradient). All routes go through the SPA's auth-bypass
# localStorage seeding pattern.
SAMPLE_VIEWS = [
    {"name": "Dashboard",       "path": "/dashboard",       "expect_seen": "仪表盘"},
    {"name": "Tasks",           "path": "/tasks",           "expect_seen": "任务"},
    {"name": "Datasets",        "path": "/datasets",        "expect_seen": "数据集"},
    {"name": "Engines",         "path": "/engines",         "expect_seen": "引擎"},
    {"name": "Login",           "path": "/login",           "expect_seen": "登录"},
]


def _seed_local_storage(page):
    """Make the SPA render in light mode (default) and pretend authenticated."""
    page.add_init_script("""
        try {
          localStorage.setItem('vdp-theme', 'light');
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
    """Run axe and return only color-contrast violations (plus a summary).

    Note: we exclude elements tagged with `.loading-text` because that's the
    initial splash shown BEFORE Vue mounts — its colour is enforced by
    index.html, not by any view. The whole point of this test is to verify
    the SPA's own view tree (post-mount) has no contrast violations.
    """
    results = page.evaluate("""
        async () => {
          // @ts-ignore  -- axe is injected globally
          const r = await axe.run(document, {
            runOnly: { type: 'rule', values: ['color-contrast'] },
            resultTypes: ['violations'],
          });
          // Filter out the pre-mount splash element; its colour is verified
          // separately by tests/contrast_check.py at the hex-pair level.
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
              nodes: v.nodes.map(n => ({
                target: n.target,
                failureSummary: n.failureSummary,
                html: (n.html || '').slice(0, 240),
              })),
            })),
          };
        }
    """)
    return results


def main() -> int:
    axe_version = None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            executable_path=r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1155\chrome-win\chrome.exe",
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        _seed_local_storage(page)
        _stub_api(page)

        summary = []
        all_pass = True

        for view in SAMPLE_VIEWS:
            t0 = time.time()
            page.goto(f"http://127.0.0.1:5183{view['path']}",
                      wait_until="domcontentloaded", timeout=30_000)
            # Wait for app shell to mount (header).
            try:
                page.wait_for_selector("header", timeout=15_000)
            except Exception:
                pass
            # Give Vue a beat to render the view + run its onMounted fetches.
            page.wait_for_timeout(800)
            _inject_axe(page)
            res = run_axe_on(page, view["name"])
            elapsed = time.time() - t0

            pass_fail = "PASS" if res["violationCount"] == 0 else "FAIL"
            if res["violationCount"] > 0:
                all_pass = False
            summary.append({
                "view": view["name"],
                "path": view["path"],
                "violationCount": res["violationCount"],
                "elapsed_s": round(elapsed, 2),
                "result": pass_fail,
                "violations": res["violations"],
            })

        browser.close()

    print("\n=== P12-A1 axe-core color-contrast verification ===")
    print(f"{'View':<15} {'Path':<18} {'Violations':<12} {'Time':<8} {'Result'}")
    print("-" * 70)
    for s in summary:
        print(f"{s['view']:<15} {s['path']:<18} {s['violationCount']:<12} "
              f"{s['elapsed_s']:<8} {s['result']}")

    # Save full JSON for the report
    out_path = Path(__file__).resolve().parent / "p12_a1_axe_results.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"\nFull results: {out_path}")

    if not all_pass:
        print("\n--- VIOLATIONS ---")
        for s in summary:
            if s["violationCount"]:
                print(f"\n[{s['view']}] {s['violationCount']} color-contrast violation(s)")
                for v in s["violations"]:
                    print(f"  - {v['help']} (impact: {v['impact']})")
                    for n in v["nodes"][:3]:
                        print(f"      target={n['target']}")
                        print(f"      html={n['html']}")
        return 1

    print("\nAll 5 sample views: 0 color-contrast violations. PASS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())