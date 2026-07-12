"""
P12-A1 AUDIT: Extended axe-core color-contrast scan on views that use
type="info" (Naive UI's default infoColor = #2080f0, NOT overridden by
App.vue themeOverrides — see auditor's hidden-issue finding #1).
"""
import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

AXE_PATH = Path(__file__).resolve().parent.parent / "node_modules" / "axe-core" / "axe.min.js"

# Views known to render type="info" Naive UI components
INFO_VIEWS = [
    {"name": "StoryboardEditor", "path": "/assets/storyboard", "expect_seen": "Storyboard"},
    {"name": "VisualEditor",     "path": "/workflow/visual-editor", "expect_seen": "工作流"},
    {"name": "Marketplace",      "path": "/skills", "expect_seen": "Skill"},
    {"name": "WikiList",         "path": "/obsidian/wiki", "expect_seen": "Wiki"},
    {"name": "Lineage",          "path": "/lineage", "expect_seen": "lineage"},
    {"name": "CanvasDesigner",   "path": "/canvas-designer", "expect_seen": "Canvas"},
    {"name": "MultimodalChat",   "path": "/agent/multimodal", "expect_seen": "模型"},
]


def seed(page):
    page.add_init_script("""
        try {
          localStorage.setItem('vdp-theme', 'light');
          localStorage.setItem('imdf.auth.access_token', 'playwright-fake-token');
          localStorage.setItem('imdf.auth.user', JSON.stringify({id:1, name:'e2e', role:'admin'}));
        } catch {}
    """)


def stub(page):
    page.route("**/api/**", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"items": [], "total": 0, "page": 1, "page_size": 20})
    ))


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(
            headless=True,
            executable_path=r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1155\chrome-win\chrome.exe",
        )
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        seed(page)
        stub(page)

        results = []
        for v in INFO_VIEWS:
            t0 = time.time()
            try:
                page.goto(f"http://127.0.0.1:5183{v['path']}", wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_selector("header", timeout=10_000)
                page.wait_for_timeout(1200)
                # Inject axe
                page.add_script_tag(content=AXE_PATH.read_text(encoding="utf-8"))
                res = page.evaluate("""async () => {
                  // @ts-ignore
                  const r = await axe.run(document, {runOnly:{type:'rule',values:['color-contrast']}, resultTypes:['violations']});
                  return {
                    count: r.violations.length,
                    violations: r.violations.map(v => ({
                      id: v.id, impact: v.impact, help: v.help,
                      nodes: v.nodes.slice(0, 5).map(n => ({
                        target: n.target,
                        summary: n.failureSummary?.slice(0, 200),
                        html: (n.html || '').slice(0, 200),
                      }))
                    }))
                  };
                }""")
            except Exception as e:
                import traceback
                res = {"count": -1, "error": str(e)[:200], "tb": traceback.format_exc()[:500]}
            results.append({"view": v["name"], "path": v["path"], "elapsed_s": round(time.time()-t0,2), **res})
        b.close()

    print("\n=== AUDIT: info-views color-contrast ===")
    for r in results:
        c = r.get("count", -1)
        tag = "PASS" if c == 0 else f"FAIL ({c} violations)" if c > 0 else "ERROR"
        print(f"  {r['view']:<20} {r['path']:<28} {tag}")
        if r.get("error"):
            print(f"    ERROR: {r['error']}")
            if r.get("tb"):
                print(f"    TB: {r['tb']}")
        for v in r.get("violations", []):
            print(f"    [{v['impact']}] {v['help']}")
            for n in v.get("nodes", [])[:3]:
                print(f"      target={n['target']}")
                print(f"      html={n['html']}")
                if n.get('summary'):
                    print(f"      summary={n['summary']}")
    print()
    total_fail = sum(1 for r in results if r.get("count", 0) > 0)
    print(f"Total views with violations: {total_fail}/{len(results)}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
