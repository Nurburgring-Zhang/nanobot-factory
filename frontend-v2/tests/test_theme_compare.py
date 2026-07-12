"""
Quick test: do these violations exist in LIGHT mode too?
"""
import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

AXE_PATH = Path(__file__).resolve().parent.parent / "node_modules" / "axe-core" / "axe.min.js"

VIEWS = [
    {"name": "AssetManagement",        "path": "/asset-management"},
    {"name": "Annotation",             "path": "/annotation"},
]


def _seed(page, theme):
    page.add_init_script(f"""
        try {{
          localStorage.setItem('vdp-theme', '{theme}');
          localStorage.setItem('imdf.auth.access_token', 'playwright-fake-token');
          localStorage.setItem('imdf.auth.user', JSON.stringify({{ id: 1, name: 'e2e', role: 'admin' }}));
        }} catch {{}}
    """)

def _stub_api(context):
    context.route("**/api/**", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"items": [], "total": 0, "page": 1, "page_size": 20}),
    ))

def _inject_axe(page):
    page.add_script_tag(content=AXE_PATH.read_text(encoding="utf-8"))


def main():
    for theme in ["light", "dark"]:
        print(f"\n=== THEME: {theme.upper()} ===")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            _stub_api(context)
            for v in VIEWS:
                page = context.new_page()
                _seed(page, theme)
                page.goto(f"http://127.0.0.1:5173{v['path']}", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1500)
                _inject_axe(page)
                result = page.evaluate("""
                    async () => {
                        const r = await axe.run(document, { resultTypes: ['violations'] });
                        return {
                            count: r.violations.length,
                            ids: r.violations.map(v => v.id)
                        };
                    }
                """)
                print(f"  {v['name']:25s} violations={result['count']} ids={result['ids']}")
                page.close()
            browser.close()


if __name__ == "__main__":
    main()
