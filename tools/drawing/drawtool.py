"""Read engineering drawings with tools instead of by eye. Run through the `draw` wrapper (uses /tmp/drawtools-venv).

  draw views   IMG                                   view boxes (crop these instead of guessing pixels)
  draw text    IMG [--crop BOX] [--kind dia,radius]  dimension and note text with pixel boxes, parsed
  draw scale   IMG --auto [--crop BOX]               px/mm from the drawing's own linear dimensions
  draw scale   IMG --p1 X,Y --p2 X,Y --mm V          px/mm from two points of one known dimension (snapped)
  draw scale   IMG --circle X,Y --mm D               px/mm from a circle of known diameter
  draw measure IMG --scale S [--origin X,Y] --dist X1,Y1,X2,Y2 | --pt X,Y | --circle X,Y | --angle X1,Y1,XV,YV,X2,Y2
  draw holes   IMG --crop BOX --scale S [--origin X,Y]   circles in mm, concentric sets, patterns (PCD, grid, line)
  draw overlay MODEL IMG --crop BOX --scale S --view top|front|right|left|rear|bottom|all [--out PNG]

BOX is x0,y0,x1,y1 in sheet pixels (the full-size PNG, not a downscaled preview). S is px per mm.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dtlib import sheet  # noqa: E402



def _texts(img, crop, args):
    """OCR with a cache; crop None = whole drawing area."""
    from dtlib import cache, ocr
    k = cache.key(img, crop, ocr.VERSION, args.fast)
    hit = cache.get(k)
    if hit is not None:
        return ocr.reparse(hit)
    g = sheet.load_gray(img)
    r = ocr.read(g, box=crop, upscale=1.5 if args.fast else 2.0, vertical=not args.fast)
    cache.put(k, r)
    return r


def cmd_views(a):
    from dtlib import views
    g = sheet.load_gray(a.img)
    vs = views.find(g, gap=a.gap)
    if a.json:
        print(json.dumps(vs)); return
    print(f"views ({len(vs)}): box x0,y0,x1,y1 px incl. its dimensions; fill = ink fraction (>0.08: shaded/iso view)")
    for i, v in enumerate(vs, 1):
        x0, y0, x1, y1 = v["box"]
        print(f"v{i}  {x0},{y0},{x1},{y1}  {x1 - x0}x{y1 - y0}  fill {v['fill']:.2f}")


def cmd_text(a):
    crop = sheet.parse_box(a.crop) if a.crop else None
    r = _texts(a.img, crop, a)
    if a.kind:
        ks = set(a.kind.split(","))
        r = [d for d in r if d["kind"] in ks]
    if a.json:
        print(json.dumps(r)); return
    print(f"text: {len(r)} items{' in ' + a.crop if a.crop else ''} (sheet template skipped). "
          "kind value [count/flags] | read | box x0,y0,x1,y1 | rot (-90 = reads upward)")
    for d in r:
        extra = []
        if d.get("count"):
            extra.append(f"{d['count']}x")
        for k in ("pitch", "depth", "angle", "tol"):
            if k in d:
                extra.append(f"{k} {d[k]}")
        if d.get("flags"):
            extra.append("/".join(d["flags"]))
        if d.get("ref"):
            extra.append("ref")
        v = d.get("value")
        vs = "" if v is None else (str(int(v)) if float(v).is_integer() else str(v))
        b = d["box"]
        rot = f" rot {d['rot']}" if abs(d.get("rot") or 0) >= 5 else ""
        low = " low-conf" if d["score"] < 0.8 else ""
        print(f"{d['kind']:7s} {vs:>7s} {' '.join(extra):14s} | {d['text']} | {b[0]},{b[1]},{b[2]},{b[3]}{rot}{low}")


def cmd_scale(a):
    from dtlib import geom
    import numpy as np
    g = sheet.load_gray(a.img)
    if a.auto:
        crop = sheet.parse_box(a.crop) if a.crop else None
        texts = _texts(a.img, None, a)
        clusters, cands = geom.auto_scale(g, texts, box=crop)
        clusters = [c for c in clusters if len(set(c["dims"])) >= 2]
        if a.json:
            print(json.dumps({"clusters": clusters, "candidates": [{k: v for k, v in c.items() if k != "ends"} for c in cands]},
                             default=float)); return
        if not clusters:
            print(f"scale --auto: no two linear dimensions agree ({len(cands)} dimension lines found). "
                  "Use --p1/--p2/--mm or --circle on a dimension you trust.")
            return
        print("scale --auto: dimension-line length / value, clustered (views can differ in scale). "
              "Check the dims listed belong to the view you crop.")
        for c in clusters:
            b = c["bbox"]
            print(f"scale {c['px_per_mm']:.4f} px/mm  from {c['n']} dims (spread {100 * c['spread']:.2f}%) "
                  f"in {b[0]},{b[1]},{b[2]},{b[3]}: {' '.join(_num(v) for v in c['dims'])}")
        off = [c for c in cands if c["cluster"] is None]
        if off and a.verbose:
            print("not agreeing:", ", ".join(f"{_num(c['value'])} ({c['ratio']:.3f})" for c in off))
        return
    ink = sheet.ink_mask(g)
    if a.circle:
        c = geom.circle_at(ink, sheet.parse_pt(a.circle), r_max=a.rmax)
        if c is None:
            sys.exit("scale --circle: no circle found around that point (click inside it, near the centre)")
        s = 2 * c["r"] / a.mm
        print(f"scale {s:.4f} px/mm  (circle Ø{2 * c['r']:.1f} px = Ø{_num(a.mm)} mm, centre {c['cx']:.1f},{c['cy']:.1f}, "
              f"fit rms {c['rms']:.2f} px, ring {100 * c['support']:.0f}%)")
        return
    if not (a.p1 and a.p2 and a.mm):
        sys.exit("scale: give --auto, or --p1 X,Y --p2 X,Y --mm V, or --circle X,Y --mm D")
    p1, p2 = sheet.parse_pt(a.p1), sheet.parse_pt(a.p2)
    d = np.subtract(p2, p1); d = d / max(1e-9, np.linalg.norm(d))
    notes = []
    if not a.no_snap:
        q1, m1 = geom.snap(ink, p1, d); q2, m2 = geom.snap(ink, p2, d)
        notes.append(f"p1 {'snapped %.1f px to %.1f,%.1f' % (m1, *q1) if m1 is not None else 'no line within 8 px, kept'}")
        notes.append(f"p2 {'snapped %.1f px to %.1f,%.1f' % (m2, *q2) if m2 is not None else 'no line within 8 px, kept'}")
        p1, p2 = q1, q2
    L = math.dist(p1, p2)
    print(f"scale {L / a.mm:.4f} px/mm  ({L:.1f} px / {_num(a.mm)} mm; {'; '.join(notes) or 'not snapped'})")


def _num(v):
    return str(int(v)) if float(v).is_integer() else str(round(v, 3))


def _mm(p, origin, s):
    return ((p[0] - origin[0]) / s, -(p[1] - origin[1]) / s)


def cmd_measure(a):
    from dtlib import geom
    import numpy as np
    g = sheet.load_gray(a.img)
    ink = sheet.ink_mask(g)
    s = a.scale
    origin = sheet.parse_pt(a.origin) if a.origin else None
    if not (a.dist or a.pt or a.circle or a.angle):
        sys.exit("measure: give --dist, --pt, --circle or --angle (repeatable)")
    for spec in a.dist or []:
        v = [float(t) for t in spec.split(",")]
        p1, p2 = (v[0], v[1]), (v[2], v[3])
        if a.snap:
            d = np.subtract(p2, p1); d = d / max(1e-9, np.linalg.norm(d))
            p1 = geom.snap(ink, p1, d)[0]; p2 = geom.snap(ink, p2, d)[0]
        L = math.dist(p1, p2)
        print(f"dist {p1[0]:.1f},{p1[1]:.1f} -> {p2[0]:.1f},{p2[1]:.1f}: {L:.1f} px = {L / s:.2f} mm "
              f"(dx {(p2[0] - p1[0]) / s:+.2f}, dy {-(p2[1] - p1[1]) / s:+.2f} mm, y up)")
    for spec in a.pt or []:
        p = sheet.parse_pt(spec)
        if a.snap:
            p = geom.snap(ink, p)[0]
        if origin is None:
            sys.exit("measure --pt needs --origin X,Y")
        x, y = _mm(p, origin, s)
        print(f"pt {p[0]:.1f},{p[1]:.1f}: x {x:+.2f} y {y:+.2f} mm from origin {origin[0]:.0f},{origin[1]:.0f}")
    for spec in a.circle or []:
        c = geom.circle_at(ink, sheet.parse_pt(spec), r_max=a.rmax)
        if c is None:
            print(f"circle at {spec}: none found (point inside the circle, near its centre)"); continue
        pos = ""
        if origin is not None:
            x, y = _mm((c["cx"], c["cy"]), origin, s); pos = f" = x {x:+.2f} y {y:+.2f} mm"
        print(f"circle at {spec}: Ø {2 * c['r'] / s:.2f} mm (r {c['r']:.1f} px), centre {c['cx']:.1f},{c['cy']:.1f}{pos}; "
              f"fit rms {c['rms']:.2f} px, ring {100 * c['support']:.0f}%")
    for spec in a.angle or []:
        v = [float(t) for t in spec.split(",")]
        a1 = math.atan2(-(v[1] - v[3]), v[0] - v[2]); a2 = math.atan2(-(v[5] - v[3]), v[4] - v[2])
        ang = abs(math.degrees(a2 - a1)) % 360
        ang = min(ang, 360 - ang)
        print(f"angle at {v[2]:.0f},{v[3]:.0f}: {ang:.2f} deg")


def cmd_holes(a):
    from dtlib import holes
    g = sheet.load_gray(a.img)
    box = sheet.parse_box(a.crop, g.shape)
    s = a.scale
    from dtlib import cache, ocr
    tb = []
    if not a.no_text_mask:
        hit = cache.get(cache.key(a.img, None, ocr.VERSION, False)) or cache.get(cache.key(a.img, None, ocr.VERSION, True))
        if hit is None:
            hit = _texts(a.img, box, a)
        tb = [d["box"] for d in hit]
    cs = holes.find_circles(g, box, min_r=max(3, a.min_d * s / 2), max_r=a.max_d * s / 2 if a.max_d else None,
                            text_boxes=tb)
    groups = holes.concentric(cs)
    if not groups:
        print(f"holes: no circles in {a.crop}"); return
    if a.origin:
        origin = sheet.parse_pt(a.origin); why = "given"
    else:
        big = max(groups, key=lambda g_: max(g_["rs"]))
        origin = (big["cx"], big["cy"]); why = "centre of the largest circle"
    pats = holes.patterns(groups, s, origin)
    if a.json:
        print(json.dumps({"origin_px": origin, "scale": s, "patterns": pats})); return
    print(f"holes in {a.crop} at {s:.4f} px/mm; origin {origin[0]:.0f},{origin[1]:.0f} px ({why}); x right, y up, mm. "
          f"{len(cs)} circles, {len(groups)} centres. Ø sets on one line are concentric (bore/counterbore/rim).")
    for p in pats:
        dias = " / ".join(f"Ø{d:.2f}" for d in p["dias"])
        cen = "  ".join(f"({x:+.2f},{y:+.2f})" for x, y in p["centres"][:12])
        more = f" +{p['n'] - 12} more" if p["n"] > 12 else ""
        part = f"{p['n']}x {dias}"
        if "pcd" in p:
            q = p["pcd"]; st = q["step_deg"]
            steps = f"step {st}" if not isinstance(st, list) else "steps " + " ".join(str(x) for x in st)
            part += f"  PCD Ø{q['dia']:.2f} at ({q['centre'][0]:+.2f},{q['centre'][1]:+.2f}), start {q['start_deg']} deg, {steps} deg"
            if q.get("empty_at_deg"):
                part += f"; no circle found at {', '.join(str(x) for x in q['empty_at_deg'])} deg (check: hidden by a line, or really absent)"
        elif "grid" in p:
            q = p["grid"]; part += f"  grid {len(q['xs'])}x{len(q['ys'])}, span {q['pitch'][0]:.2f} x {q['pitch'][1]:.2f}"
        elif "line" in p:
            q = p["line"]; part += f"  line at {q['dir_deg']} deg, pitch {q['pitch']:.2f}{'' if q['even'] else ' (uneven)'}"
        weak = "" if p["support"] >= 0.9 else f"  [ring {100 * p['support']:.0f}%: partly hidden or an arc]"
        print(f"{part}{weak}\n    at {cen}{more}")


def cmd_overlay(a):
    from dtlib import overlay
    g = sheet.load_gray(a.img)
    box = sheet.parse_box(a.crop, g.shape)
    ink = sheet.ink_mask(g)[box[1]:box[3], box[0]:box[2]]
    V, F = overlay.load_mesh(a.model)
    views = list(overlay.PRESETS) if a.view == "all" else [a.view]
    scales = tuple(1 + k * a.scale_step for k in range(-a.scale_n, a.scale_n + 1))
    rows = []
    for v in views:
        e, _, _ = overlay.render_edges(V, F, v, a.scale)
        res = overlay.match(e, ink, scales=scales, tol_px=a.tol)
        bt = overlay.best_per_transform(res)
        rows.append((v, bt))
    rows.sort(key=lambda r: -r[1][0]["f"])
    v, bt = rows[0] if a.view == "all" else rows[0]
    ident = [r for r in bt if r["ti"] == 0][0]
    best = bt[0]
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.model)), f"overlay_{v}.png")
    overlay.draw(g[box[1]:box[3], box[0]:box[2]], ink, ident, best, out,
                 f"{os.path.basename(a.model)}  view {v}  {a.scale:.4f} px/mm  crop {a.crop}")
    print(f"overlay {os.path.basename(a.model)} on {a.crop}, view {v}, {a.scale:.4f} px/mm "
          f"(f = agreement of model edges and drawing lines, 0-1; P = model edges on ink, R = view lines covered)")
    if a.view == "all":
        print("views: " + ", ".join(f"{vv} {b[0]['f']:.3f} ({b[0]['transform']})" for vv, b in rows))
    for r in bt:
        print(f"  {r['transform']:27s} f {r['f']:.3f}  P {r['precision']:.3f}  R {r['recall']:.3f}  scale x{r['scale']:.3f}")
    margin = ident["f"] - max(r["f"] for r in bt if r is not ident)
    ties = [r["transform"] for r in bt if r is not ident and ident["f"] - r["f"] < 0.03]
    if best is ident and margin >= 0.03:
        verdict = f"OK: as modelled is the best reading of this view (margin {margin:.3f} over {bt[1]['transform']})"
    elif best is ident or ident["f"] >= best["f"] - 0.03:
        verdict = (f"AMBIGUOUS: as modelled ties with {', '.join(ties)} (within 0.03); the view is symmetric that way, "
                   "check a feature that breaks the symmetry or another view")
    else:
        verdict = (f"MISMATCH: best match is '{best['transform']}' (f {best['f']:.3f} vs {ident['f']:.3f} as modelled). "
                   "The part as modelled is turned or mirrored relative to this view: re-read the view's orientation. "
                   f"Fix: {overlay.fix_hint(v, best['ti'])}")
    if best["f"] < 0.5:
        verdict += f". Low agreement overall (best f {best['f']:.3f}): wrong view name, scale or crop, or the shape differs"
    if abs(best["scale"] - 1) >= a.scale_n * a.scale_step - 1e-9 and a.scale_n:
        verdict += f". Best size is at the edge of the search (x{best['scale']:.3f}): check the scale or the part's size"
    print(verdict)
    print(f"png: {out} (blue = as modelled, red = best other reading, grey = drawing)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="draw", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("views"); p.add_argument("img"); p.add_argument("--gap", type=int, default=40)
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_views)
    p = sub.add_parser("text"); p.add_argument("img"); p.add_argument("--crop"); p.add_argument("--kind")
    p.add_argument("--fast", action="store_true", help="1.5x and no 90 deg pass: about 3x faster, but vertical text comes out as single digits")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_text)
    p = sub.add_parser("scale"); p.add_argument("img"); p.add_argument("--auto", action="store_true")
    p.add_argument("--crop"); p.add_argument("--p1"); p.add_argument("--p2"); p.add_argument("--mm", type=float)
    p.add_argument("--circle"); p.add_argument("--rmax", type=float, default=600)
    p.add_argument("--no-snap", action="store_true"); p.add_argument("--fast", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_scale)
    p = sub.add_parser("measure"); p.add_argument("img"); p.add_argument("--scale", type=float, required=True)
    p.add_argument("--origin"); p.add_argument("--dist", action="append"); p.add_argument("--pt", action="append")
    p.add_argument("--circle", action="append"); p.add_argument("--angle", action="append")
    p.add_argument("--snap", action="store_true", help="move points onto the nearest line centre (8 px reach)")
    p.add_argument("--rmax", type=float, default=600); p.set_defaults(fn=cmd_measure)
    p = sub.add_parser("holes"); p.add_argument("img"); p.add_argument("--crop", required=True)
    p.add_argument("--scale", type=float, required=True); p.add_argument("--origin")
    p.add_argument("--min-d", type=float, default=1.0); p.add_argument("--max-d", type=float)
    p.add_argument("--no-text-mask", action="store_true", help="skip OCR (text glyphs may show up as small circles)")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_holes)
    p = sub.add_parser("overlay"); p.add_argument("model"); p.add_argument("img")
    p.add_argument("--crop", required=True); p.add_argument("--scale", type=float, required=True)
    p.add_argument("--view", default="all", choices=list(__import__("dtlib.overlay", fromlist=["x"]).PRESETS) + ["all"])
    p.add_argument("--out"); p.add_argument("--tol", type=int, default=2, help="px")
    p.add_argument("--scale-step", type=float, default=0.015); p.add_argument("--scale-n", type=int, default=2)
    p.set_defaults(fn=cmd_overlay)
    a = ap.parse_args(argv)
    a.fast = getattr(a, "fast", False)
    a.fn(a)


if __name__ == "__main__":
    main()
