"""Cases for tools/drawing (run by drawing_tools.sh with /tmp/drawtools-venv). Prints one JSON object per line:
{"case": ..., ...}. Writes only under OUT.

Synthetic: an L-plate with three Ø8 holes and a Ø24 boss with a Ø12 bore, drawn on a 3072 x 2118 sheet from
build123d's exact hidden-line projection (not the overlay renderer) at 3 px/mm, with arrowed dimensions in a
TrueType font. Every answer is known: scale, dimension texts, hole sizes and positions, and which of the planted
flips (rotated 180, mirrored, turned over) each candidate STEP is.

Dev drawings (when /tmp/cgb-data is there; never the test set): text P/R on the hand labels, auto-scale vs a
two-point calibration on 102, circle diameters vs callouts on 145, and the planted flips of a part traced from
142's profile view.
"""
import json
import os
import subprocess
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "DRAWTOOLS_THREADS"):
    os.environ.setdefault(_v, "4")  # before numpy / build123d load; subprocesses inherit it

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DT = os.path.join(ROOT, "tools", "drawing")
sys.path.insert(0, DT)
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
DATA = "/tmp/cgb-data"
S = 3.0  # px/mm of the synthetic sheet
TOP0 = (700, 900)    # sheet px of model (0, 0) in the top view (x right, y up)
FRONT0 = (700, 1400)  # sheet px of model (x 0, z 0) in the front view


def emit(**k):
    print(json.dumps(k, default=float), flush=True)


def draw(*args):
    r = subprocess.run([sys.executable, "-I", os.path.join(DT, "drawtool.py"), *map(str, args)],
                       capture_output=True, text=True, env=dict(os.environ))
    return r.stdout + r.stderr


def font(size):
    from PIL import ImageFont
    for f in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size=size)


def synth():
    from build123d import BuildPart, BuildSketch, Polygon, extrude, Locations, Hole, Cylinder, Align, export_step, \
        export_stl, Axis, mirror, Plane
    from PIL import Image, ImageDraw
    with BuildPart() as p:
        with BuildSketch():
            Polygon((0, 0), (120, 0), (120, 30), (70, 30), (70, 80), (0, 80), align=None)
        extrude(amount=10)
        with Locations((20, 20, 10), (20, 60, 10), (100, 15, 10)):
            Hole(4)
        with Locations((45, 55, 10)):
            Cylinder(12, 25, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((45, 55, 35)):
            Hole(6)
    part = p.part
    export_step(part, f"{OUT}/ref.step")
    export_stl(part, f"{OUT}/ref.stl")
    export_step(part.rotate(Axis.Z, 180), f"{OUT}/rot180z.step")
    export_step(mirror(part, Plane.YZ), f"{OUT}/mirx.step")
    export_step(part.rotate(Axis.X, 180), f"{OUT}/flipx.step")   # base on the wrong side
    export_stl(part.rotate(Axis.Z, 180), f"{OUT}/rot180z.stl")

    img = Image.new("L", (3072, 2118), 255)
    d = ImageDraw.Draw(img)
    f = font(24)

    def proj(cam, up, origin, uv):
        c = part.bounding_box().center()
        vis, _ = part.project_to_viewport((c.X + cam[0] * 500, c.Y + cam[1] * 500, c.Z + cam[2] * 500), up,
                                          (c.X, c.Y, c.Z))
        for e in vis:
            pts = [e.position_at(t / 60) for t in range(61)]
            d.line([(origin[0] + uv(q)[0] * S, origin[1] - uv(q)[1] * S) for q in pts], fill=0, width=3)
    # project_to_viewport returns view-plane coordinates; offset so model x=0 / y=0 / z=0 land on the origins
    c = part.bounding_box().center()
    proj((0, 0, 1), (0, 1, 0), TOP0, lambda q: (q.X + c.X, q.Y + c.Y))
    proj((0, -1, 0), (0, 0, 1), FRONT0, lambda q: (q.X + c.X, q.Y + c.Z))

    def arrow(tip, direction):
        ux, uy = direction; L, W = 14, 4
        b = (tip[0] - ux * L, tip[1] - uy * L)
        d.polygon([tip, (b[0] - uy * W, b[1] + ux * W), (b[0] + uy * W, b[1] - ux * W)], fill=0)

    def hdim(x0, x1, y_obj, y, text):
        for x in (x0, x1):
            d.line([(x, y_obj + 6), (x, y + 10)], fill=0, width=1)
        d.line([(x0, y), (x1, y)], fill=0, width=1)
        arrow((x0, y), (-1, 0)); arrow((x1, y), (1, 0))
        w = d.textlength(text, font=f)
        d.text(((x0 + x1) / 2 - w / 2, y - 30), text, fill=0, font=f)

    def vdim(y0, y1, x_obj, x, text):
        for y in (y0, y1):
            d.line([(x_obj - 6, y), (x - 10, y)], fill=0, width=1)
        d.line([(x, y0), (x, y1)], fill=0, width=1)
        arrow((x, y0), (0, -1)); arrow((x, y1), (0, 1))
        w = int(d.textlength(text, font=f)) + 4
        t = Image.new("L", (w, 30), 255); ImageDraw.Draw(t).text((2, 0), text, fill=0, font=f)
        t = t.rotate(90, expand=True)
        img.paste(t, (int(x - 32), int((y0 + y1) / 2 - w / 2)))

    X = lambda mm: TOP0[0] + mm * S
    Y = lambda mm: TOP0[1] - mm * S
    hdim(X(0), X(120), Y(0), Y(0) + 70, "120")
    hdim(X(0), X(70), Y(0), Y(0) + 130, "70")
    vdim(Y(80), Y(0), X(0), X(0) - 70, "80")
    vdim(Y(30), Y(0), X(120), X(120) + 70, "30")
    Z = lambda mm: FRONT0[1] - mm * S
    vdim(Z(35), Z(0), X(120), X(120) + 70, "35")
    vdim(Z(10), Z(0), X(0), X(0) - 70, "10")
    # callouts with leaders
    d.line([(X(20) + 9, Y(60) - 9), (X(20) + 60, Y(60) - 120)], fill=0, width=1)
    d.text((X(20) + 64, Y(60) - 138), "3X Ø8 THRU", fill=0, font=f)
    d.line([(X(45) + 30, Y(55) - 22), (X(45) + 150, Y(55) - 110)], fill=0, width=1)
    d.text((X(45) + 154, Y(55) - 128), "Ø24", fill=0, font=f)
    img.save(f"{OUT}/sheet.png")
    return f"{OUT}/sheet.png"


def run_synth():
    from dtlib import sheet, ocr, geom, holes
    png = synth()
    g = sheet.load_gray(png)
    texts = ocr.read(g)
    got = {d["text"]: d for d in texts}
    want = ["120", "70", "80", "30", "35", "10", "3X Ø8 THRU", "Ø24"]
    emit(case="synth_text", found=[w for w in want if w in got], missing=[w for w in want if w not in got],
         extra=[d["text"] for d in texts if d["text"] not in want],
         callout=got.get("3X Ø8 THRU", {}))
    cl, cands = geom.auto_scale(g, texts)
    emit(case="synth_scale", clusters=[{k: c[k] for k in ("px_per_mm", "n", "dims")} for c in cl])
    box = (TOP0[0] - 40, TOP0[1] - 80 * S - 40, TOP0[0] + 120 * S + 40, TOP0[1] + 40)
    cs = holes.find_circles(g, box, text_boxes=[t["box"] for t in texts])
    pats = holes.patterns(holes.concentric(cs), S, TOP0)
    emit(case="synth_holes", patterns=[{k: p[k] for k in ("n", "dias", "centres")} for p in pats])
    out = draw("measure", png, "--scale", S, "--snap", "--dist", f"{X0()-3},{TOP0[1]+70},{X0()+360+4},{TOP0[1]+70}",
               "--circle", f"{TOP0[0] + 45 * S + 1},{TOP0[1] - 55 * S + 1}")
    emit(case="synth_measure", out=out)
    crop_top = ",".join(str(int(v)) for v in box)
    crop_front = f"{TOP0[0] - 40},{FRONT0[1] - 35 * S - 40},{TOP0[0] + 120 * S + 40},{FRONT0[1] + 40}"
    for m, view, crop in (("ref.step", "top", crop_top), ("rot180z.step", "top", crop_top), ("mirx.step", "top", crop_top),
                          ("flipx.step", "front", crop_front), ("ref.step", "front", crop_front),
                          ("rot180z.stl", "top", crop_top), ("ref.step", "all", crop_top)):
        o = draw("overlay", f"{OUT}/{m}", png, "--crop", crop, "--scale", S, "--view", view,
                 "--out", f"{OUT}/ov_{m}_{view}.png")
        verdict = [l for l in o.splitlines() if l.startswith(("OK", "MISMATCH", "AMBIGUOUS"))]
        views = [l for l in o.splitlines() if l.startswith("overlay")]
        emit(case=f"synth_overlay_{m}_{view}", verdict=verdict[0] if verdict else o[-400:], head=views[0] if views else "")


def X0():
    return TOP0[0]


def run_dev():
    if not os.path.exists(f"{DATA}/102/input.png"):
        emit(case="dev_skipped", why=f"{DATA} missing"); return
    from dtlib import sheet
    import numpy as np
    r = subprocess.run([sys.executable, "-I", os.path.join(DT, "eval_dev.py"), "text"], capture_output=True, text=True)
    js = [l for l in r.stdout.splitlines() if l.startswith("JSON ")]
    emit(case="dev_text", **(json.loads(js[0][5:]) if js else {"error": r.stdout[-500:] + r.stderr[-500:]}))
    r = subprocess.run([sys.executable, "-I", os.path.join(DT, "eval_dev.py"), "circles"], capture_output=True, text=True)
    emit(case="dev_circles", out=r.stdout)
    o = draw("scale", f"{DATA}/102/input.png", "--auto")
    man = draw("scale", f"{DATA}/102/input.png", "--p1", "376,1229", "--p2", "750,1229", "--mm", "220")
    emit(case="dev_scale_102", auto=o, manual=man)
    # a candidate traced from 142's profile view (thick outline, extruded 20 mm), then planted turns and mirrors
    p = f"{DATA}/142/input.png"; box = (227, 313, 1256, 1099); s = 3.0563
    import cv2
    from scipy import ndimage
    from build123d import Polygon, extrude, export_step, Axis, mirror, Plane
    g = sheet.load_gray(p); ink = sheet.ink_mask(g)[box[1]:box[3], box[0]:box[2]]
    op = ndimage.binary_opening(ink, structure=np.ones((3, 3)))
    fill = ndimage.binary_fill_holes(ndimage.binary_closing(op, iterations=6))
    lab, n = ndimage.label(fill); k = int(np.argmax(ndimage.sum(fill, lab, range(1, n + 1)))) + 1
    cs, _ = cv2.findContours((lab == k).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = cv2.approxPolyDP(max(cs, key=cv2.contourArea), 1.0, True)[:, 0, :].astype(float)
    pts = [((x + box[0]) / s, -(y + box[1]) / s) for x, y in c]
    mx = np.mean([q[0] for q in pts]); my = np.mean([q[1] for q in pts])
    part = extrude(Polygon(*[(x - mx, y - my) for x, y in pts], align=None), amount=20)
    plant = {"ref": part, "rot180": part.rotate(Axis.Z, 180), "mirlr": mirror(part, Plane.YZ), "rot90": part.rotate(Axis.Z, 90)}
    for name, prt in plant.items():
        export_step(prt, f"{OUT}/t142_{name}.step")
        o = draw("overlay", f"{OUT}/t142_{name}.step", p, "--crop", ",".join(map(str, box)), "--scale", s,
                 "--view", "top", "--out", f"{OUT}/ov142_{name}.png")
        verdict = [l for l in o.splitlines() if l.startswith(("OK", "MISMATCH", "AMBIGUOUS"))]
        emit(case=f"dev_overlay142_{name}", verdict=verdict[0] if verdict else o[-400:])


if __name__ == "__main__":
    which = sys.argv[2] if len(sys.argv) > 2 else "all"
    if which in ("all", "synth"):
        run_synth()
    if which in ("all", "dev"):
        run_dev()
