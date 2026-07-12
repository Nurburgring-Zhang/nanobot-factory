def lum(hex_color):
    h = hex_color.lstrip('#')
    r, g, b = [int(h[i:i+2], 16)/255 for i in (0, 2, 4)]
    def f(c):
        return c/12.92 if c <= 0.03928 else ((c+0.055)/1.055)**2.4
    return 0.2126*f(r) + 0.7152*f(g) + 0.0722*f(b)


def ratio(c1, c2):
    L1, L2 = lum(c1), lum(c2)
    if L1 < L2:
        L1, L2 = L2, L1
    return (L1 + 0.05) / (L2 + 0.05)


# Test proposed colors (WCAG 2.1 AA Normal Text >= 4.5:1, AAA >= 7:1)
print("=== Light mode (on #ffffff) ===")
# Try darker shades to hit 6.5/6.0 targets
for c in ['#0a5dc2', '#0959bc', '#0855b6', '#0750a8', '#064a9a']:
    print(f"Primary {c} on #ffffff: {ratio(c, '#ffffff'):.2f}:1")
print()
for c in ['#157a3e', '#137038', '#116730', '#0f5d2a', '#0d5424']:
    print(f"Success {c} on #ffffff: {ratio(c, '#ffffff'):.2f}:1")
print()
for c in ['#c87f0d', '#b8730c', '#a8680b', '#985c0a', '#885408']:
    print(f"Warning {c} on #ffffff: {ratio(c, '#ffffff'):.2f}:1")
print()
for c in ['#c81e3e', '#bc1c39', '#ae1a35', '#a01830', '#92162b']:
    print(f"Error {c} on #ffffff: {ratio(c, '#ffffff'):.2f}:1")
print()
print("=== Dark mode (on #18181c) ===")
print(f"Primary #5aa9ff on #18181c: {ratio('#5aa9ff', '#18181c'):.2f}:1")
print(f"Success #4cc07c on #18181c: {ratio('#4cc07c', '#18181c'):.2f}:1")
print(f"Warning #ffb340 on #18181c: {ratio('#ffb340', '#18181c'):.2f}:1")
print(f"Error #ff5a72 on #18181c: {ratio('#ff5a72', '#18181c'):.2f}:1")
print(f"Info #5aa9ff on #18181c: {ratio('#5aa9ff', '#18181c'):.2f}:1")
print()
print("=== Existing #2080f0 (current) ===")
print(f"#2080f0 on #ffffff: {ratio('#2080f0', '#ffffff'):.2f}:1")
print(f"#18a058 on #ffffff: {ratio('#18a058', '#ffffff'):.2f}:1")
print(f"#f0a020 on #ffffff: {ratio('#f0a020', '#ffffff'):.2f}:1")
print(f"#d03050 on #ffffff: {ratio('#d03050', '#ffffff'):.2f}:1")
print()
print("=== A11y focus ring ===")
print(f"#0a5dc2 on #ffffff: {ratio('#0a5dc2', '#ffffff'):.2f}:1")
print(f"#5aa9ff on #18181c: {ratio('#5aa9ff', '#18181c'):.2f}:1")