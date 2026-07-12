"""
P12-A1 AUDIT: Direct DOM probe of rendered NTag/elements to detect OLD info color.
"""
import json, sys, time
from playwright.sync_api import sync_playwright

PROBE_PAGES = [
    ("/assets/storyboard",  "StoryboardEditor"),
    ("/skills",             "Marketplace"),
    ("/lineage",            "Lineage"),
]


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(
            headless=True,
            executable_path=r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1155\chrome-win\chrome.exe",
        )
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.add_init_script("""
            try {
              localStorage.setItem('vdp-theme', 'light');
              localStorage.setItem('imdf.auth.access_token', 'playwright-fake-token');
              localStorage.setItem('imdf.auth.user', JSON.stringify({id:1, name:'e2e', role:'admin'}));
            } catch {}
        """)
        page.route("**/api/**", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"items": [], "total": 0, "page": 1, "page_size": 20})
        ))

        page.goto("http://127.0.0.1:5183/dashboard", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2000)

        for path, name in PROBE_PAGES:
            print(f"\n=== {name} ({path}) ===")
            page.goto(f"http://127.0.0.1:5183{path}", wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3000)
            probe = page.evaluate("""() => {
              // Find ANY Naive UI element with computed --n-*-color or textColorInfo
              const all = Array.from(document.querySelectorAll('*'));
              const interesting = [];
              for (const el of all) {
                const cs = getComputedStyle(el);
                const cls = el.className || '';
                const text = (el.innerText || '').trim().slice(0, 40);
                // Check if this element has info color reference
                if (cls.includes && (cls.includes('n-tag') || cls.includes('n-button') || cls.includes('n-alert'))) {
                  interesting.push({
                    tag: el.tagName,
                    text,
                    cls: typeof cls === 'string' ? cls.slice(0, 80) : '',
                    color: cs.color,
                    background: cs.backgroundColor,
                    borderColor: cs.borderColor,
                  });
                }
                if (interesting.length >= 20) break;
              }
              // Also dump root-level CSS vars on :root
              const rootStyle = getComputedStyle(document.documentElement);
              const allVars = {};
              for (const prop of ['--primary-color', '--info-color', '--success-color', '--warning-color', '--error-color']) {
                allVars[prop] = rootStyle.getPropertyValue(prop).trim();
              }
              return { interesting, allVars, bodyHTML_len: document.body.innerHTML.length };
            }""")
            print(f"  body HTML length: {probe['bodyHTML_len']}")
            print(f"  root CSS vars: {probe['allVars']}")
            print(f"  found {len(probe['interesting'])} Naive UI elements:")
            for el in probe['interesting'][:10]:
                print(f"    {el['tag']} text='{el['text']}' color={el['color']} bg={el['background']}")
        b.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
