"""Write all V5 files at once. Imports content from sibling .py modules."""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))

from _ic_content import INFINITE_CANVAS_VUE
from _cc_content import COMMAND_CENTER_VUE
from _ic_test_content import IC_TEST as INFINITE_CANVAS_TEST
from _cc_test_content import CC_TEST as COMMAND_CENTER_TEST
from _modifications_content import (
    ROUTER_ADDITION, LAYOUT_ADDITION, REPORT_MD, DELIVERABLE_MD
)

BASE = r"D:\Hermes\生产平台\nanobot-factory\frontend-v2"
REPORTS = r"D:\Hermes\生产平台\nanobot-factory\reports"
OUT = r"C:\Users\Administrator\.mavis\plans\plan_218c7f26\outputs\p19_v56_canvas_command"


def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"OK  {len(content):>6}  {path}")


if __name__ == "__main__":
    w(os.path.join(BASE, "src", "components", "InfiniteCanvas.vue"), INFINITE_CANVAS_VUE)
    w(os.path.join(BASE, "src", "components", "CommandCenter.vue"), COMMAND_CENTER_VUE)
    w(os.path.join(BASE, "src", "components", "__tests__", "InfiniteCanvas.spec.ts"), INFINITE_CANVAS_TEST)
    w(os.path.join(BASE, "src", "components", "__tests__", "CommandCenter.spec.ts"), COMMAND_CENTER_TEST)
    w(os.path.join(REPORTS, "p19_v56_canvas_command.md"), REPORT_MD)
    w(os.path.join(OUT, "deliverable.md"), DELIVERABLE_MD)
    # Modifications
    rpath = os.path.join(BASE, "src", "router", "index.ts")
    with open(rpath, encoding="utf-8") as f:
        router_src = f.read()
    if "infinite-canvas" not in router_src:
        marker = "      // ===== P5-R1-T1 ProjectCenter"
        router_src = router_src.replace(marker, ROUTER_ADDITION + "\n" + marker)
        with open(rpath, "w", encoding="utf-8", newline="\n") as f:
            f.write(router_src)
        print("OK        MOD  router/index.ts")
    lpath = os.path.join(BASE, "src", "layouts", "DefaultLayout.vue")
    with open(lpath, encoding="utf-8") as f:
        lay_src = f.read()
    if "infinite-canvas" not in lay_src:
        marker = "menuOptions.push(p5r1t6Submenu)"
        lay_src = lay_src.replace(marker, marker + "\n\n" + LAYOUT_ADDITION)
        with open(lpath, "w", encoding="utf-8", newline="\n") as f:
            f.write(lay_src)
        print("OK        MOD  layouts/DefaultLayout.vue")
    vpath = os.path.join(BASE, "vite.config.ts")
    with open(vpath, encoding="utf-8") as f:
        v_src = f.read()
    if "src/**/*.spec.ts" not in v_src:
        v_src = v_src.replace(
            "include: ['tests/**/*.spec.ts'],",
            "include: ['tests/**/*.spec.ts', 'src/**/*.spec.ts'],"
        )
        with open(vpath, "w", encoding="utf-8", newline="\n") as f:
            f.write(v_src)
        print("OK        MOD  vite.config.ts")
    print("DONE")