"""Circles in a view crop (holes, bosses, bores), concentric sets merged, equal sets grouped into patterns."""
from __future__ import annotations
import math
import numpy as np
import cv2
from . import sheet, geom


def find_circles(gray, box, min_r=4, max_r=None, min_support=0.8, text_boxes=()):
    """Circles drawn in `box`: Hough (OpenCV HOUGH_GRADIENT_ALT) proposals, each refitted on the ink and kept if
    at least min_support of its circumference is inked. Text boxes are blanked first ("0", "8", "6" are rings)."""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    g = sheet.normalise(gray)
    ink = sheet.ink_mask(gray)
    if len(text_boxes):
        g = g.copy(); ink = ink.copy()
        for b in text_boxes:
            g[b[1] - 1:b[3] + 2, b[0] - 1:b[2] + 2] = 255; ink[b[1] - 1:b[3] + 2, b[0] - 1:b[2] + 2] = False
    sub = g[y0:y1, x0:x1]
    max_r = int(max_r or min(x1 - x0, y1 - y0) / 2)
    blur = cv2.GaussianBlur(sub, (5, 5), 1.0)
    found = []
    for p2 in (0.85,):
        cs = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT_ALT, dp=1.0, minDist=2, param1=120, param2=p2,
                              minRadius=int(min_r), maxRadius=max_r)
        if cs is not None:
            found += [tuple(c) for c in cs[0]]
    out = []
    for cx, cy, r in found:
        cx += x0; cy += y0
        fit = geom.circle_at(ink, (cx, cy), r_max=r * 1.3 + 4, r_min=max(2, r * 0.7 - 3), r_hint=r)
        if fit is None or abs(fit["r"] - r) > max(3, 0.15 * r):
            continue
        sup, _ = geom.ring_support(ink, fit["cx"], fit["cy"], fit["r"], tol=1.5)
        if sup < min_support or fit["rms"] > max(0.6 if fit["r"] < 8 else 1.2, 0.04 * fit["r"]):
            continue
        fit["support"] = sup
        out.append(fit)
    # dedupe (inner/outer edges of one drawn line give two Hough circles)
    out.sort(key=lambda c: -c["support"])
    keep = []
    for c in out:
        if any(math.hypot(c["cx"] - k["cx"], c["cy"] - k["cy"]) < 2.5 and abs(c["r"] - k["r"]) < 2.5 for k in keep):
            continue
        keep.append(c)
    return keep


def concentric(circles, tol=2.5):
    groups = []
    for c in sorted(circles, key=lambda c: c["r"]):
        for g in groups:
            if math.hypot(c["cx"] - g["cx"], c["cy"] - g["cy"]) < max(tol, 0.02 * c["r"]):
                g["rs"].append(c["r"]); g["sup"].append(c["support"]); break
        else:
            groups.append({"cx": c["cx"], "cy": c["cy"], "rs": [c["r"]], "sup": [c["support"]]})
    return groups


def _same_sig(a, b, s, tol_mm=0.6):
    if len(a["rs"]) != len(b["rs"]):
        return False
    return all(abs(2 * (ra - rb) / s) < max(tol_mm, 0.04 * 2 * ra / s) for ra, rb in zip(a["rs"], b["rs"]))


def patterns(groups, s, origin):
    """Group features with the same diameter set; describe each set as PCD, rect grid, line or list.
    s: px/mm; origin: (x, y) px. Coordinates in mm, +y up."""
    pts = lambda g: ((g["cx"] - origin[0]) / s, -(g["cy"] - origin[1]) / s)
    sets = []
    for g in groups:
        for st in sets:
            if _same_sig(st[0], g, s):
                st.append(g); break
        else:
            sets.append([g])
    out = []
    for st in sets:
        dias = [round(2 * r / s, 2) for r in st[0]["rs"]]
        P = np.array([pts(g) for g in st])
        d = {"n": len(st), "dias": dias, "centres": [[round(float(x), 2), round(float(y), 2)] for x, y in P],
             "px": [[round(g["cx"]), round(g["cy"])] for g in st], "support": round(float(min(min(g["sup"]) for g in st)), 2)}
        if len(st) >= 3:
            cx, cy, R, rms = geom.fit_circle(P)
            ang = np.degrees(np.arctan2(P[:, 1] - cy, P[:, 0] - cx)) % 360
            a = np.sort(ang); steps = np.diff(np.r_[a, a[0] + 360])
            if rms < max(0.3, 0.01 * R) and R < 1e4:
                d["pcd"] = {"centre": [round(float(cx), 2), round(float(cy), 2)], "dia": round(float(2 * R), 2),
                            "start_deg": round(float(a[0]), 1),
                            "step_deg": round(float(np.median(steps)), 1) if steps.std() < 1.0 else
                            [round(float(x), 1) for x in steps]}
                med = float(np.median(steps))
                gaps = [round(float(a[i] + med * k) % 360, 1) for i, st_ in enumerate(steps)
                        for k in range(1, int(round(st_ / med))) if abs(st_ / med - round(st_ / med)) < 0.05 and round(st_ / med) >= 2]
                if gaps:
                    d["pcd"]["empty_at_deg"] = gaps  # an even pattern with a position not found: look there
        if "pcd" not in d and len(st) >= 4:
            xs = np.unique(np.round(P[:, 0], 0)); ys = np.unique(np.round(P[:, 1], 0))
            if len(xs) * len(ys) == len(st) and len(xs) >= 2 and len(ys) >= 2:
                d["grid"] = {"xs": [round(float(x), 2) for x in sorted(set(np.round(P[:, 0], 2)))][:len(xs)],
                             "ys": [round(float(y), 2) for y in sorted(set(np.round(P[:, 1], 2)))][:len(ys)],
                             "pitch": [round(float(np.ptp(P[:, 0])), 2), round(float(np.ptp(P[:, 1])), 2)]}
        if "pcd" not in d and "grid" not in d and len(st) >= 3:
            c = P.mean(0); u, sv, vt = np.linalg.svd(P - c)
            if sv[1] / max(sv[0], 1e-9) < 0.02:
                t = np.sort((P - c) @ vt[0]); gaps = np.diff(t)
                d["line"] = {"dir_deg": round(float(np.degrees(np.arctan2(vt[0][1], vt[0][0]))) % 180, 1),
                             "pitch": round(float(np.median(gaps)), 2), "even": bool(gaps.std() < 0.3)}
        out.append(d)
    out.sort(key=lambda d: (-d["n"], -max(d["dias"])))
    return out
