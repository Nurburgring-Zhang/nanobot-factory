"""
P14-A1 light vs dark mode comparison — verify `region` violation is PRE-EXISTING.

Loads each of the 12 views in BOTH light and dark modes and compares violation counts.
If light == dark for a given view, the violation is structural (pre-existing),
not dark-mode-introduced. That's the boundary proof.

Run:
    cd frontend-v2
    python tests/test_p14_a1_theme_compare.py

Writes results to tests/p14_a1_theme_compare.json.
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


def seed(page, theme):
    page.add_init_script(f"""
        try {{
          localStorage.setItem('vdp-theme', '{theme}');
          localStorage.setItem('imdf.auth.access_token', 'playwright-fake-token');
          localStorage.setItem('imdf.auth.user',
            JSON.stringify({{ id: 1, name: 'e2e', role: 'admin' }}));
        }} catch {{}}
    """)


def stub_api(context):
    context.route("**/api/**", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"items": [], "total": 0, "page": 1, "page_size": 20}),
    ))


def run_full_axe(page):
    return page.evaluate("""
        async () => {
          // @ts-ignore
          const r = await axe.run(document, { resultTypes: ['violations'] });
          const filtered = r.violations
            .map(v => ({
              ...v,
              nodes: v.nodes.filter(n =>
                !(Array.isArray(n.target) &&
                  n.target.some(t => String(t).includes('loading-text')))
              ),
            }))
            .filter(v => v.nodes.length > 0);
          return filtered.map(v => ({
            id: v.id, impact: v.impact, nodeCount: v.nodes.length,
          }));
        }
    """)


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"
    print(f"P14-A1 LIGHT vs DARK comparison — base: {base_url}")
    print(f"  total views: {len(TWELVE_VIEWS)} x 2 themes = {len(TWELVE_VIEWS)*2}")
    print()

    results = []
    start = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for theme in ('light', 'dark'):
            print(f"=== THEME: {theme.upper()} ===")
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            stub_api(context)

            for i, view in enumerate(TWELVE_VIEWS, 1):
                page = context.new_page()
                seed(page, theme)
                page.set_default_timeout(15000)
                vs = time.time()
                error = None
                vlist = []
                try:
                    page.goto(f"{base_url}{view['path']}", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(1500)
                    page.add_script_tag(content=AXE_PATH.read_text(encoding="utf-8"))
                    vlist = run_full_axe(page)
                except Exception as e:
                    error = str(e)[:120]
                vids = [v["id"] for v in vlist]
                elapsed = time.time() - vs
                print(f"  {view['name']:20s} violations={len(vlist):2d} ids={vids} ({elapsed:.1f}s)")
                results.append({
                    "theme": theme,
                    "name": view["name"],
                    "path": view["path"],
                    "violations": vlist,
                    "error": error,
                    "elapsedSeconds": round(elapsed, 2),
                })
                page.close()
            context.close()
        browser.close()

    total = time.time() - start
    # Compare per-view
    by_view = {}
    for r in results:
        by_view.setdefault(r["name"], {})[r["theme"]] = r["violations"]
    print()
    print("=== Theme diff summary ===")
    for view_name, themes in by_view.items():
        light_ids = sorted({v["id"] for v in themes.get("light", [])})
        dark_ids = sorted({v["id"] for v in themes.get("dark", [])})
        same = light_ids == dark_ids
        print(f"  {view_name:20s} light={light_ids} dark={dark_ids} same={same}")

    summary = {
        "task": "p14_a1_theme_compare",
        "baseUrl": base_url,
        "totalRuns": len(results),
        "totalElapsedSeconds": round(total, 1),
        "results": results,
        "byView": by_view,
    }
    out_path = Path(__file__).resolve().parent / "p14_a1_theme_compare.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults: {out_path}")


if __name__ == "__main__":
    main()