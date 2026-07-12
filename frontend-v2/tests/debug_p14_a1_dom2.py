"""More thorough DOM check — count rendered elements after longer wait."""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AXE_PATH = Path(__file__).resolve().parent.parent / "node_modules" / "axe-core" / "axe.min.js"

SAMPLE = [
    {"name": "Contracts",      "path": "/contracts"},
    {"name": "Skill",          "path": "/skills"},
    {"name": "KnowledgeGraph", "path": "/obsidian/graph"},
    {"name": "Billing",        "path": "/billing"},
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


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"
    print(f"DOM v2 — base: {base_url}")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for theme in ('light', 'dark'):
            print(f"=== THEME: {theme.upper()} ===")
            for view in SAMPLE:
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                stub_api(context)
                page = context.new_page()
                seed(page, theme)
                try:
                    page.goto(f"{base_url}{view['path']}", wait_until="domcontentloaded", timeout=15000)
                    # Wait for some content
                    try:
                        page.wait_for_selector(".n-card, .billing-view, .skill-marketplace, .page-root", timeout=10000)
                    except Exception:
                        pass
                    page.wait_for_timeout(2000)
                    data_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
                    counts = page.evaluate("""
                        () => ({
                          h1: document.querySelectorAll('h1').length,
                          h2: document.querySelectorAll('h2').length,
                          main: document.querySelectorAll('main').length,
                          nav: document.querySelectorAll('nav').length,
                          ncard: document.querySelectorAll('.n-card').length,
                          ndatatable: document.querySelectorAll('.n-data-table').length,
                          pageRoot: document.querySelectorAll('.page-root, .billing-view, .skill-marketplace').length,
                          bodyTextLen: document.body.innerText.length,
                          bodyText: document.body.innerText.substring(0, 300),
                          url: location.pathname,
                          title: document.title,
                        })
                    """)
                    print(f"  {view['name']:18s} theme={data_theme} url={counts['url']} title={counts['title']!r}")
                    print(f"    h1={counts['h1']} h2={counts['h2']} main={counts['main']} nav={counts['nav']} ncard={counts['ncard']} bodyTextLen={counts['bodyTextLen']}")
                    print(f"    bodyText={counts['bodyText']!r}")
                except Exception as e:
                    print(f"  {view['name']:18s} ERR: {str(e)[:100]}")
                page.close()
                context.close()
        browser.close()


if __name__ == "__main__":
    main()