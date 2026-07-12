"""
P12-A1 AUDIT: Verify infoColor is actually overridden in App.vue
Probe rendered NTag with type=info across multiple views to detect
the OLD Naive UI default (#2080f0) bleeding through.
"""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

INFO_VIEWS = [
    {"name": "StoryboardEditor", "path": "/assets/storyboard"},
    {"name": "VisualEditor",     "path": "/workflow/visual-editor"},
    {"name": "Marketplace",      "path": "/skills"},
    {"name": "WikiList",         "path": "/obsidian/wiki"},
    {"name": "Lineage",          "path": "/lineage"},
    {"name": "CanvasDesigner",   "path": "/canvas-designer"},
    {"name": "MultimodalChat",   "path": "/agent/multimodal"},
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

        # First, navigate once to warm up
        page.goto("http://127.0.0.1:5183/dashboard", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2000)

        results = []
        for v in INFO_VIEWS:
            try:
                page.goto(f"http://127.0.0.1:5183{v['path']}", wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(2500)
                probe = page.evaluate("""() => {
                  const all = Array.from(document.querySelectorAll('.n-tag'));
                  const info = all.filter(el => (el.className || '').includes('--info-type') || (el.className || '').includes('tag--info'));
                  const samples = info.slice(0, 3).map(el => {
                    const cs = getComputedStyle(el);
                    return {
                      text: (el.innerText || '').slice(0, 30),
                      color: cs.color,
                      background: cs.backgroundColor,
                      borderColor: cs.borderColor,
                      cls: el.className,
                    };
                  });
                  return { count: info.length, samples };
                }""")
                # Also check the actual computed CSS variable for info
                theme_var = page.evaluate("""() => {
                  // Naive UI sets CSS vars like --info-color on body when override active
                  const root = document.documentElement;
                  const style = getComputedStyle(root);
                  return {
                    primaryColor: style.getPropertyValue('--primary-color'),
                    infoColor: style.getPropertyValue('--info-color'),
                    successColor: style.getPropertyValue('--success-color'),
                  };
                }""")
                results.append({"view": v["name"], "path": v["path"], "probe": probe, "theme_var": theme_var})
            except Exception as e:
                results.append({"view": v["name"], "path": v["path"], "error": str(e)[:200]})
        b.close()

    print("=== P12-A1 AUDIT: info-color probe ===")
    print()
    for r in results:
        print(f"[{r['view']}] {r['path']}")
        if r.get("error"):
            print(f"  ERROR: {r['error']}")
            continue
        print(f"  info-tag count: {r['probe']['count']}")
        for s in r["probe"]["samples"]:
            print(f"    text='{s['text']}' color={s['color']} bg={s['background']} cls={s['cls'][:80]}")
        print(f"  CSS vars: {r['theme_var']}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
