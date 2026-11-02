"""Inline the alex-style CSS/JS and the evidence renders into one shareable dashboard.html.

python3 -I docs/dashboard/build.py   (needs sips, macOS)
"""
import base64, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE = os.environ.get("AX_STYLE", os.path.expanduser("~/code-stuff/alex-style-guide/web"))
EV = os.path.join(HERE, "..", "evidence-v2-supports")
IMGS = {
    "jar_valve": "jar_valve.png",
    "jar_valve_map": "printcheck/maps/jar_valve_z002.0_cantilever.png",
    "feeder_cover": "feeder_cover.png",
    "nacelle": "nacelle.png",
}

# ax-charts' axLine assumes every series has the same length; the loops ran 3, 7 and 8 attempts.
CHART_PATCHES = [
    ("{ series, yTicks, x = i => i,", "{ series, yTicks, digits = 2, padR = 46, x = i => i,"),
    ("const x0 = 58, y0 = 8, w = width - x0 - 46,", "const x0 = 58, y0 = 8, w = width - x0 - padR,"),
    ("const n = series[0].values.length,", "const n = Math.max(...series.map(s => s.values.length)),"),
    ("const ends = series.map((s, k) => ({ k, y: Y(s.values[n - 1]) + 4 }))",
     "const ends = series.map((s, k) => { const j = s.values.length - 1; return { k, j, y: Y(s.values[j]) + 4 }; })"),
    ("el('text', { x: X(n - 1) + 6, y: e.y,", "el('text', { x: X(e.j) + 6, y: e.y,"),
    ("`<span style=\"color:${s.color || color(k)}\">■</span> ${s.name} ${s.values[i].toFixed(2)} ${unit}`).join('<br>')",
     "s.values[i] == null ? '' : `<span style=\"color:${s.color || color(k)}\">■</span> ${s.name} ${s.values[i].toFixed(digits)} ${unit}`).filter(Boolean).join('<br>')"),
]

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def js(body):
    # A literal </script> in a comment would end the inline tag early
    return "<script>\n" + body.replace("</script", "<\\/script") + "\n</script>"

def jpeg_data_uri(src, tmp):
    out = os.path.join(tmp, os.path.basename(src) + ".jpg")
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82", "-Z", "520", src, "--out", out],
                   check=True, capture_output=True)
    with open(out, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()

def main():
    html = read(os.path.join(HERE, "src.html"))
    charts = read(os.path.join(STYLE, "ax-charts.js"))
    for old, new in CHART_PATCHES:
        if charts.count(old) != 1:
            sys.exit(f"ax-charts.js patch does not apply: {old[:60]}")
        charts = charts.replace(old, new)
    parts = {
        '<link rel="stylesheet" href="@style/tokens.css">': "<style>\n" + read(os.path.join(STYLE, "tokens.css")) + "\n</style>",
        '<script src="@style/ax-charts.js"></script>': js(charts),
        '<script src="@style/ax-fx.js"></script>': js(read(os.path.join(STYLE, "ax-fx.js"))),
    }
    for tag, body in parts.items():
        if tag not in html:
            sys.exit(f"missing in src.html: {tag}")
        html = html.replace(tag, body)
    with tempfile.TemporaryDirectory() as tmp:
        for key, rel in IMGS.items():
            html = html.replace(f'src="@img/{key}"', f'src="{jpeg_data_uri(os.path.join(EV, rel), tmp)}"')
    left = re.findall(r'@(?:img|style)/\w+', html)
    if left:
        sys.exit(f"unresolved: {left}")
    out = os.path.join(HERE, "dashboard.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(out, os.path.getsize(out) // 1024, "KB")

main()
