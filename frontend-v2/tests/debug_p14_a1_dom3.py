"""Screenshot + detailed DOM dump."""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SAMPLE = [
    {"name": "Billing",        "path": "/billing"},
    {"name": "Contracts",      "path": "/contracts"},
    {"name": "Skill",          "path": "/skills"},
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
    print(f"Screenshot+DOM — base: {base_url}")

    out_dir = Path(__file__).resolve().parent / "screenshots"
    out_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for view in SAMPLE:
            for theme in ('light', 'dark'):
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                stub_api(context)
                page = context.new_page()
                seed(page, theme)
                page.on("console", lambda msg: print(f"  [console.{msg.type}] {msg.text}") if msg.type in ('error', 'warning') else None)
                page.on("pageerror", lambda exc: print(f"  [pageerror] {exc}"))
                try:
                    page.goto(f"{base_url}{view['path']}", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(3000)
                    fname = f"{view['name'].lower()}_{theme}.png"
                    page.screenshot(path=str(out_dir / fname), full_page=True)
                    counts = page.evaluate("""
                        () => ({
                          appChildren: document.querySelector('#app')?.children?.length || 0,
                          appInnerStart: document.querySelector('#app')?.innerHTML?.substring(0, 500) || '(none)',
                          htmlLen: document.documentElement.outerHTML.length,
                        })
                    """)
                    print(f"  {view['name']:18s} {theme:5s} appChildren={counts['appChildren']} htmlLen={counts['htmlLen']}")
                    print(f"    appInner: {counts['appInnerStart'][:200]!r}")
                except Exception as e:
                    print(f"  ERR: {str(e)[:200]}")
                page.close()
                context.close()
        browser.close()


if __name__ == "__main__":
    main()