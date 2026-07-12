"""
Debug DOM - with console logging.
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

    # Capture all console messages
    page.on("console", lambda msg: print(f"  [CONSOLE {msg.type}] {msg.text[:300]}"))
    page.on("pageerror", lambda err: print(f"  [PAGEERROR] {err}"))

    page.add_init_script("""
        try {
          localStorage.setItem('vdp-theme', 'dark');
          localStorage.setItem('imdf.auth.access_token', 'playwright-fake-token');
          localStorage.setItem('imdf.auth.user', JSON.stringify({ id: 1, name: 'e2e', role: 'admin' }));
        } catch {}
    """)
    page.set_default_timeout(15000)
    page.goto("http://127.0.0.1:5173/asset-management", wait_until="domcontentloaded", timeout=15000)
    page.wait_for_timeout(3000)

    # Check if there's any element with 'n-layout' class
    has_layout = page.evaluate("!!document.querySelector('.n-layout')")
    print(f"\n=== HAS N-LAYOUT: {has_layout} ===")

    # Check if there's an NCard
    ncard_count = page.evaluate("document.querySelectorAll('.n-card').length")
    print(f"=== N-CARD COUNT: {ncard_count} ===")

    # Check if there's a router-view
    rv = page.evaluate("!!document.querySelector('.n-config-provider')")
    print(f"=== HAS CONFIG PROVIDER: {rv} ===")

    body_html = page.evaluate("document.body.innerHTML")
    print(f"\n=== BODY HTML (last 1500) ===")
    print(body_html[-1500:])

    browser.close()
