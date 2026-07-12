"""
Debug a single view with full console capture.
"""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    context.route("**/api/**", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"items": [], "total": 0, "page": 1, "page_size": 20}),
    ))
    page = context.new_page()

    page.on("console", lambda msg: print(f"  [CONSOLE {msg.type[:3].upper()}] {msg.text[:300]}"))
    page.on("pageerror", lambda err: print(f"  [PAGEERROR] {err}"))

    page.add_init_script("""
        try {
          localStorage.setItem('vdp-theme', 'dark');
          localStorage.setItem('imdf.auth.access_token', 'playwright-fake-token');
          localStorage.setItem('imdf.auth.user', JSON.stringify({ id: 1, name: 'e2e', role: 'admin' }));
        } catch {}
    """)

    page.goto(f"http://127.0.0.1:5173/asset-management", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(3000)

    body = page.evaluate("document.body.innerHTML")
    print(f"\n=== BODY (last 2000) ===")
    print(body[-2000:])

    browser.close()
