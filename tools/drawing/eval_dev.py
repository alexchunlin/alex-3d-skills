"""Accuracy of the drawing tools on CADGenBench dev drawings (generation samples 101-150 minus the test set).

  eval_dev.py text   [IDS]   OCR precision / recall against tools/verify.d/drawing_labels/<id>.json
  eval_dev.py scale  [IDS]   auto-scale: clusters per sheet, and leave-one-out error of each dimension in mm
  eval_dev.py circles        circle diameters vs their callouts (hand-picked views, scale from a linear dim)

Refuses the 10 test-set drawings. Uses the OCR cache (/tmp/drawtools-cache, or DRAWTOOLS_CACHE).
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dtlib import sheet, ocr, geom, holes, textscore, cache  # noqa: E402

DATA = os.environ.get("CGB_DATA", "/tmp/cgb-data")
TEST = {101, 106, 111, 116, 121, 126, 131, 136, 141, 146}
DEV = [i for i in range(101, 151) if i not in TEST and i != 144]
LABELS = os.path.join(HERE, "..", "verify.d", "drawing_labels")

# (id, view crop, scale source (p1, p2, mm) or px/mm, [(callout Ø, what)]) -- callouts read from the drawing
CIRCLES = [
    (145, (288, 206, 1319, 1027), ((805, 253), (955, 253), 27.5),
     [(116.0, "Ø116.00 outer"), (66.94, "Ø66.94 dash-dot"), (40.0, "Ø40.00"), (15.0, "Ø15.00 bore"),
      (10.0, "Ø10.00 (6X)"), (27.5, "PCD = 2 x 13.75")]),
    (102, (255, 198, 1156, 1102), ((719, 652), 120.0),
     [(175.3, "Ø175.3"), (230.0, "Ø230 hole PCD")]),
]


def guard(i):
    if int(i) in TEST:
        sys.exit(f"{i} is a test-set drawing")
    return int(i)


def texts(i):
    p = f"{DATA}/{i}/input.png"
    k = cache.key(p, None, ocr.VERSION, False)
    r = cache.get(k)
    if r is None:
        r = ocr.read(sheet.load_gray(p)); cache.put(k, r)
    return ocr.reparse(r)


def cmd_text(ids):
    ids = ids or sorted(int(f[:3]) for f in os.listdir(LABELS) if f.endswith(".json"))
    tot = dict(tp=0, n_pred=0, n_lab=0, dim_tp=0, dim_pred=0, dim_lab=0)
    out = {}
    for i in map(guard, ids):
        t = time.time(); r = texts(i); dt = time.time() - t
        s = textscore.score([{"t": d["raw"], "b": d["box"]} for d in r], json.load(open(f"{LABELS}/{i}.json"))["items"])
        for k in tot:
            tot[k] += s[k]
        out[i] = s
        print(f"{i}: P {s['P']:.3f} R {s['R']:.3f} (dims P {s['dim_P']:.3f} R {s['dim_R']:.3f}; {s['n_lab']} labels, {dt:.0f} s)"
              f"  missed: {', '.join(s['missed'][:8])}{' ...' if len(s['missed']) > 8 else ''}")
    P = tot["tp"] / max(1, tot["n_pred"]); R = tot["tp"] / max(1, tot["n_lab"])
    print(f"ALL: P {P:.3f} R {R:.3f}  dims P {tot['dim_tp'] / max(1, tot['dim_pred']):.3f} "
          f"R {tot['dim_tp'] / max(1, tot['dim_lab']):.3f}  ({tot['n_lab']} labels)")
    print("JSON " + json.dumps({"P": P, "R": R, "per": {k: [v["P"], v["R"]] for k, v in out.items()}}))


def cmd_scale(ids):
    import numpy as np
    ids = ids or DEV
    errs = []; rel = []; sheets = 0; multi = 0; n_cl = 0; n_cand = 0; n_in = 0
    for i in map(guard, ids):
        p = f"{DATA}/{i}/input.png"
        g = sheet.load_gray(p)
        cl, cands = geom.auto_scale(g, texts(i))
        cl = [c for c in cl if c["n"] >= 3 and len(set(c["dims"])) >= 2]
        n_cand += len(cands)
        if cl:
            sheets += 1
        if len(cl) >= 2:
            multi += 1
        line = []
        for ci, c in enumerate(cl):
            n_cl += 1
            mem = [x for x in cands if x["cluster"] is not None and abs(x["ratio"] / c["px_per_mm"] - 1) < 0.015]
            n_in += len(mem)
            for k, x in enumerate(mem):
                others = [y for j, y in enumerate(mem) if j != k]
                w = np.array([y["px"] for y in others]); r = np.array([y["ratio"] for y in others])
                s_ = (w * r).sum() / w.sum()
                e = x["px"] / s_ - x["value"]
                errs.append(e); rel.append(e / x["value"])
            line.append(f"{c['px_per_mm']:.4f} px/mm x{c['n']}")
        print(f"{i}: {len(cands)} dimension lines; scales: {'; '.join(line) or 'none with 3+ dims'}")
    a = np.abs(np.array(errs)); r_ = np.abs(np.array(rel))
    print(f"ALL: {sheets}/{len(ids)} sheets with a 3+ dim scale cluster, {multi} with two or more scales; "
          f"{n_in} of {n_cand} dimension lines in clusters")
    if len(a):
        print(f"leave-one-out error of in-cluster dims: median {np.median(a):.2f} mm, p90 {np.percentile(a, 90):.2f} mm, "
              f"max {a.max():.2f} mm; within 0.5 mm {100 * (a <= 0.5).mean():.0f}%, within 1% {100 * (r_ <= 0.01).mean():.0f}%")
    print("JSON " + json.dumps({"sheets": sheets, "multi": multi, "n": int(len(a)),
                                "median_mm": float(np.median(a)) if len(a) else None,
                                "p90_mm": float(np.percentile(a, 90)) if len(a) else None}))


def cmd_circles(_):
    import math
    rows = []
    for i, box, src, calls in CIRCLES:
        p = f"{DATA}/{guard(i)}/input.png"
        g = sheet.load_gray(p); ink = sheet.ink_mask(g)
        if len(src) == 3:
            d = (src[1][0] - src[0][0], src[1][1] - src[0][1]); n = math.hypot(*d); d = (d[0] / n, d[1] / n)
            q1 = geom.snap(ink, src[0], d)[0]; q2 = geom.snap(ink, src[1], d)[0]
            s = math.dist(q1, q2) / src[2]; how = f"from the {src[2]:g} dim"
        else:
            c = geom.circle_at(ink, src[0], r_max=600); s = 2 * c["r"] / src[1]; how = f"from the Ø{src[1]:g} circle"
        tb = [t["box"] for t in texts(i)]
        cs = holes.find_circles(g, box, text_boxes=tb, min_support=0.6)
        grp = holes.concentric(cs)
        pats = holes.patterns(grp, s, (0, 0))
        found = [2 * c_["r"] / s for c_ in cs] + [pp["pcd"]["dia"] for pp in pats if "pcd" in pp]
        for val, what in calls:
            best = min(found, key=lambda x: abs(x - val)) if found else None
            ok = best is not None and abs(best - val) < max(1.5, 0.03 * val)
            rows.append((i, what, val, best if ok else None))
            print(f"{i} {what:22s} callout {val:7.2f}  measured {('%.2f' % best) if ok else 'not found':>9s}"
                  f"{'  err %+.2f mm' % (best - val) if ok else ''}   (scale {s:.4f} px/mm {how})")
    e = [abs(b - v) for _, _, v, b in rows if b is not None]
    print(f"ALL: {len(e)}/{len(rows)} found, mean |err| {sum(e) / max(1, len(e)):.2f} mm, max {max(e) if e else 0:.2f} mm")


if __name__ == "__main__":
    {"text": cmd_text, "scale": cmd_scale, "circles": cmd_circles}[sys.argv[1]](sys.argv[2:])
