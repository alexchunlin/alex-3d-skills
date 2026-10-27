"""Scale and measurement on a drawing: px/mm calibration, point snapping, circle fits, auto-scale from dimensions."""
from __future__ import annotations
import math
import numpy as np
from . import sheet


def _runs_centres(ts, v):
    runs = []; i = 0
    while i < len(v):
        if v[i]:
            j = i
            while j + 1 < len(v) and v[j + 1]:
                j += 1
            runs.append((ts[i] + ts[j]) / 2.0); i = j + 1
        else:
            i += 1
    return runs


def _at(ink, xs, ys):
    xs = np.round(xs).astype(int); ys = np.round(ys).astype(int)
    ok = (xs >= 0) & (ys >= 0) & (xs < ink.shape[1]) & (ys < ink.shape[0])
    v = np.zeros(len(xs), bool); v[ok] = ink[ys[ok], xs[ok]]
    return v


def snap(ink, p, direction=None, reach=8):
    """Move p onto the centre of the nearest line crossing the search direction (sub-pixel): with a direction
    (from p1 to p2 of a dimension), the nearest extension/object line perpendicular to it, ignoring the
    dimension line p lies on; without one, the nearest ink along x or y. Returns (point, moved_px), or
    (p, None) when nothing is within reach."""
    x, y = p
    ts = np.arange(-reach, reach + 0.01, 1.0)
    if direction is not None:
        d = np.asarray(direction, float); d = d / np.linalg.norm(d); n = np.array([-d[1], d[0]])
        best = []
        for side in (1, -1):
            hits = np.zeros(len(ts))
            ks = np.arange(3, 9) * side
            for k in ks:
                hits += _at(ink, x + ts * d[0] + k * n[0], y + ts * d[1] + k * n[1])
            best.append(hits / len(ks))
        perp = np.maximum(best[0], best[1]) >= 0.8
        runs = _runs_centres(ts, perp)
        if runs:
            t = min(runs, key=abs)
            return (x + t * d[0], y + t * d[1]), abs(t)
        dirs = [d]
    else:
        dirs = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    best = None
    for d in dirs:
        runs = _runs_centres(ts, _at(ink, x + ts * d[0], y + ts * d[1]))
        if not runs:
            continue
        t = min(runs, key=abs)
        if best is None or abs(t) < abs(best[1]):
            best = ((x + t * d[0], y + t * d[1]), t)
    if best is None:
        return (x, y), None
    return best[0], abs(best[1])


def fit_circle(pts):
    """Algebraic (Kasa) fit, then RMS radial residual."""
    pts = np.asarray(pts, float)
    A = np.c_[2 * pts[:, 0], 2 * pts[:, 1], np.ones(len(pts))]
    b = (pts ** 2).sum(1)
    c, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = c[0], c[1]
    r = math.sqrt(max(1e-9, c[2] + cx * cx + cy * cy))
    res = np.sqrt(((pts - [cx, cy]) ** 2).sum(1)) - r
    return cx, cy, r, float(np.sqrt((res ** 2).mean()))


def ray_runs(ink, c, r_max, n=180, r_min=2):
    """For each of n rays from c: centres of the ink runs crossed, as (angle_index, radius)."""
    cx, cy = c
    out = []
    rs = np.arange(r_min, r_max, 0.5)
    for k in range(n):
        a = 2 * math.pi * k / n
        xs = np.round(cx + rs * math.cos(a)).astype(int); ys = np.round(cy + rs * math.sin(a)).astype(int)
        ok = (xs >= 0) & (ys >= 0) & (xs < ink.shape[1]) & (ys < ink.shape[0])
        v = np.zeros(len(rs), bool); v[ok] = ink[ys[ok], xs[ok]]
        i = 0
        while i < len(v):
            if v[i]:
                j = i
                while j + 1 < len(v) and v[j + 1]:
                    j += 1
                out.append((k, (rs[i] + rs[j]) / 2.0, rs[j] - rs[i])); i = j + 1
            else:
                i += 1
    return out


def circle_at(ink, c, r_max=400, r_min=3, n=180, r_hint=None):
    """Fit the circle around the point c (inside it, near its centre). The radius is the most common ink-crossing
    distance over n rays (centre marks and other lines cross only a few rays); then a refit on those crossings.
    Returns dict(cx, cy, r, rms, support) in px, or None."""
    runs = ray_runs(ink, c, r_max, n, r_min)
    if not runs:
        return None
    rr = np.array([r for _, r, _ in runs])
    if r_hint is None:
        hist, edges = np.histogram(rr, bins=np.arange(r_min, r_max + 2, 1.0))
        # count each ray once per bin, smoothed over +-1 px
        sm = np.convolve(hist, [1, 1, 1], "same")
        r0 = edges[int(np.argmax(sm))] + 0.5
    else:
        r0 = r_hint
    cx, cy = c
    for _ in range(4):
        pts = []
        for k, r, w in runs:
            a = 2 * math.pi * k / n
            px, py = c[0] + r * math.cos(a), c[1] + r * math.sin(a)
            if abs(math.hypot(px - cx, py - cy) - r0) < max(2.5, 0.06 * r0):
                pts.append((px, py))
        if len(pts) < 8:
            return None
        cx, cy, r0, rms = fit_circle(pts)
    rays = len({k for k, r, _ in runs if abs(math.hypot(c[0] + r * math.cos(2 * math.pi * k / n) - cx,
                                                       c[1] + r * math.sin(2 * math.pi * k / n) - cy) - r0) < 2.5})
    return {"cx": cx, "cy": cy, "r": r0, "rms": rms, "support": rays / n}


def ring_support(ink, cx, cy, r, n=None, tol=2.0):
    """Fraction of points on the circle with ink within +-tol px radially."""
    n = n or max(36, int(2 * math.pi * r / 3))
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    hit = np.zeros(n, bool)
    for dr in np.arange(-tol, tol + 0.01, 0.5):
        xs = np.round(cx + (r + dr) * np.cos(a)).astype(int); ys = np.round(cy + (r + dr) * np.sin(a)).astype(int)
        ok = (xs >= 0) & (ys >= 0) & (xs < ink.shape[1]) & (ys < ink.shape[0])
        hit[ok] |= ink[ys[ok], xs[ok]]
    return float(hit.mean()), hit


def _walk(ink, x, y, dx, dy, gap=2, limit=4000):
    """Walk from (x, y) along (dx, dy) while ink continues (gaps up to `gap` px). Returns last ink position."""
    last = None; miss = 0; i = 0
    while i < limit:
        xi, yi = x + dx * i, y + dy * i
        if not (0 <= xi < ink.shape[1] and 0 <= yi < ink.shape[0]):
            break
        if ink[yi, xi]:
            last = (xi, yi); miss = 0
        else:
            miss += 1
            if miss > gap and last is not None:
                break
            if last is None and miss > 3 * gap + 2:
                break
        i += 1
    return last


def _vrun(m, x, y, cap):
    """Length of the vertical ink run through (x, y), capped."""
    if not m[y, x]:
        return 0
    a = y
    while a > 0 and m[a - 1, x] and y - a < cap:
        a -= 1
    b = y
    while b + 1 < m.shape[0] and m[b + 1, x] and b - y < cap:
        b += 1
    return b - a + 1


def _scan(m, x, y, dx, h, limit=4000):
    """Follow a horizontal line from (x, y) in direction dx (1 px row drift allowed, gaps up to 2 px).
    Returns (end_x, events) with events (x, kind): 'arrow' where the line thickens to an arrowhead
    (4 px .. 2.2 h), 'ext' where a long perpendicular line crosses (extension or object line)."""
    last = None; miss = 0; ev = []; i = 0
    while i < limit:
        xi = x + dx * i
        if not (0 <= xi < m.shape[1]):
            break
        yy = y if m[y, xi] else (y - 1 if y > 0 and m[y - 1, xi] else (y + 1 if y + 1 < m.shape[0] and m[y + 1, xi] else None))
        if yy is None:
            miss += 1
            if miss > 2 and last is not None:
                break
            if last is None and miss > 8:
                break
        else:
            miss = 0; y = yy
            run = _vrun(m, xi, y, int(3 * h))
            if run > 2.2 * h:
                ev.append((xi, "ext"))
            elif run >= 4:
                ev.append((xi, "arrow"))
            last = xi
        i += 1
    return last, ev


def _terminals(ev, ends, h):
    """Dimension ends on one line: an extension line next to an arrowhead, or a line end next to one."""
    arrows = [x for x, k in ev if k == "arrow"]
    exts = sorted({x for x, k in ev if k == "ext"})
    # one extension line spans a few px: collapse runs of adjacent columns to their centre
    groups = []
    for x in exts:
        if groups and x - groups[-1][-1] <= 3:
            groups[-1].append(x)
        else:
            groups.append([x])
    t = [sum(g) / len(g) for g in groups if any(abs(a - sum(g) / len(g)) < 2.5 * h for a in arrows)]
    for e in ends:
        if e is not None and any(abs(a - e) < 1.5 * h for a in arrows) and all(abs(e - x) > 3 for x in t):
            t.append(float(e))
    return sorted(t)


def dim_line_length(ink, box, vertical=False, text_mask=None):
    """Length in px of the dimension that a dimension text box labels: the nearest line by the text (through a
    gap in it, under it, or beside its end), followed both ways; the dimension runs between two terminals
    (an arrowhead touching an extension line), choosing the pair that brackets the text, else the nearest pair.
    Returns (length, (p0, p1)) or None."""
    if vertical:
        r = dim_line_length(ink.T, (box[1], box[0], box[3], box[2]), False,
                            None if text_mask is None else text_mask.T)
        if r is None:
            return None
        L, (p0, p1) = r
        return L, ((p0[1], p0[0]), (p1[1], p1[0]))
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    h = max(4, y1 - y0)
    m = ink.copy()
    if text_mask is not None:
        m &= ~text_mask
    cx = (x0 + x1) / 2
    rows = range(max(0, y0 - h // 2), min(ink.shape[0], y1 + int(1.3 * h)))
    rows = sorted(rows, key=lambda y: (0 if y0 + h // 4 <= y <= y1 - h // 4 else 1, abs(y - (y1 + 0.3 * h))))
    for y in rows:
        inside = y0 + h // 4 <= y <= y1 - h // 4
        if inside:
            starts = [(x0 - 2, -1), (x1 + 2, 1)]
            if not m[y, max(0, x0 - 2 - 2 * h):max(0, x0 - 1)].any() and not m[y, x1 + 1:x1 + 2 + 2 * h].any():
                continue
        else:
            xs = [x for x in range(max(0, x0 - h), min(m.shape[1], x1 + h)) if m[y, x]]
            if len(xs) < 3:
                continue
            starts = [(xs[0], -1), (xs[0], 1)]
        lo, evl = _scan(m, starts[0][0], y, -1, h)
        hi, evr = _scan(m, starts[1][0], y, 1, h)
        if lo is None and hi is None:
            continue
        lo = lo if lo is not None else starts[0][0]; hi = hi if hi is not None else starts[1][0]
        if hi - lo < h:
            continue
        t = _terminals(evl + evr, (lo, hi), h)
        if len(t) < 2:
            continue
        pairs = list(zip(t[:-1], t[1:]))
        br = [p for p in pairs if p[0] - h <= cx <= p[1] + h]
        p = br[0] if br else min(pairs, key=lambda q: min(abs(cx - q[0]), abs(cx - q[1])))
        if p[1] - p[0] < h:
            continue
        return p[1] - p[0], ((p[0], y), (p[1], y))
    return None


def auto_scale(gray, texts, box=None, tol=0.015):
    """Scales on a sheet from its linear dimensions: each dimension-line length / value is a px/mm candidate;
    candidates that agree within tol form a cluster (views can have different scales). texts: ocr.read() output.
    Returns (clusters, candidates); clusters sorted by size, each with px_per_mm, n, spread and the dims' bbox."""
    ink = sheet.ink_mask(gray)
    tm = np.zeros_like(ink)
    for t in texts:
        b = t["box"]; tm[b[1]:b[3] + 1, b[0]:b[2] + 1] = True
    cands = []
    for t in texts:
        if t.get("kind") != "linear" or not t.get("value") or t.get("ref"):
            continue
        b = t["box"]
        if box is not None and not (box[0] <= b[0] and b[2] <= box[2] and box[1] <= b[1] and b[3] <= box[3]):
            continue
        vert = abs(t.get("rot", 0)) > 45
        r = dim_line_length(ink, b, vertical=vert, text_mask=tm)
        if r is None:
            continue
        L, ends = r
        cands.append({"value": t["value"], "px": L, "ratio": L / t["value"], "box": b, "ends": ends,
                      "vertical": vert, "cluster": None})
    clusters = []
    left = list(range(len(cands)))
    while left:
        ratios = np.array([cands[i]["ratio"] for i in left])
        support = [(np.abs(ratios / r - 1) < tol).sum() for r in ratios]
        k = int(np.argmax(support))
        if support[k] < 2:
            break
        members = [left[j] for j in range(len(left)) if abs(ratios[j] / ratios[k] - 1) < tol]
        w = np.array([cands[i]["px"] for i in members]); rr = np.array([cands[i]["ratio"] for i in members])
        s_ = float((rr * w).sum() / w.sum())  # long dimensions weigh more: their end error matters less
        bb = np.array([cands[i]["box"] for i in members])
        clusters.append({"px_per_mm": s_, "n": len(members), "spread": float(rr.std() / s_),
                         "bbox": [int(bb[:, 0].min()), int(bb[:, 1].min()), int(bb[:, 2].max()), int(bb[:, 3].max())],
                         "dims": [cands[i]["value"] for i in members]})
        for i in members:
            cands[i]["cluster"] = len(clusters) - 1
        left = [i for i in left if i not in members]
    return clusters, cands
