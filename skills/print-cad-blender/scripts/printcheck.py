"""printcheck: layer-based support analysis of printed parts, on the exported STLs (print frame, bed at z = 0).

    cad printcheck <stl_dir | part.stl ...> [--manifest manifest.json] [--out printcheck.json] [--render DIR]
                   [--layer 0.2] [--px 0.1] [--only GLOB]

Each STL is sliced at the layer height (mid-layer, like a slicer) into a raster. A pixel of layer k is supported when
it lies within the self-supporting allowance of layer k-1 (h * tan(overhang_deg): 0.2 mm per 0.2 mm layer at 45 deg,
plus half a pixel of raster slack each side). Each connected unsupported region is classified:
  bridge      touches supported material on opposite sides: straight lines in one direction end on supported material at
              both ends for at least half of it (a hole through a roof cuts the rest); `span_mm` is the longest such
              line, `residual_mm` how far the rest reaches from it. Warn above `bridge_warn_mm` (25).
  cantilever  touches supported material on one side only: `overhang_mm` is the farthest pixel's straight distance to
              the anchor (or to a bridged part of it).
              Warn above `cantilever_warn_mm` (1.0), fail above `cantilever_mm` (3.0) on a part marked supports: no.
  island      touches nothing below it (starts in mid-air). Fail above `island_mm2` (0.5) on supports: no.
Locations are in the print frame (the STL) and, with a manifest (print_rot, bbox_world_home) or from cadcheck, the
world frame. Exit status 1 when any part fails.

Why: v2 shipped "supports: no" on every part; jar_valve's three bayonet tabs start 2.1 mm above the bed, cantilevered
about 10 mm, and feeder_cover's top screw ear is a 10.5 mm cantilever at z 32. cadcheck missed both: it measured every
flat downward face as a bridge, never asked whether the face was anchored on two sides, only warned, and looked at the
model rather than the STLs (FINDINGS "v2 post-freeze", docs/evidence-v2-supports/).

Plain numpy. Runs under Blender's Python (cadcheck, `cad q printcheck`, `cad printcheck`) or any python3 with numpy;
--render needs Blender.
"""
import fnmatch, glob, json, math, os, struct, sys
from collections import deque
import numpy as np

_VERSION = "3"   # bump when analyze() changes what it reports (cache key)

DEFAULTS = {
    "layer_h": 0.2,           # mm
    "px": 0.1,                # raster pixel, mm; grown for big parts so a layer stays under max_cells
    "max_cells": 1.5e6,
    "overhang_deg": 45.0,     # self-supporting angle from vertical
    "bridge_warn_mm": 25.0,   # FINDINGS / features.RULES: PLA bridges to 25 mm
    "bridge_frac": 0.5,       # share of a region one bridge direction anchors at both ends (holes in a roof cut the rest)
    "cantilever_warn_mm": 1.0,  # beyond the 45 deg allowance: past about two perimeters a ledge sags
    "cantilever_mm": 3.0,       # fail: v2's real misses are 5.5 (jar_valve tabs) to 11.7 mm; short ledges to 2.9 print
    "island_mm2": 0.5,
    "min_region_mm2": 0.05,   # raster noise
    "min_feature_mm": 0.4,    # one extrusion line: an unsupported sliver with no core this wide is not printed (v1 A1/A3
                              # base_shell 0.2 mm fins, hopper's 0.1 mm funnel-lip hairline), so it neither fails nor supports
    "max_regions": 25,        # per part, in the report (counts stay complete)
}


# ------------------------------------------------------------------ input

def read_stl(path):
    """Triangles (n, 3, 3) float64 from a binary or ASCII STL."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) >= 84:
        n = struct.unpack("<I", data[80:84])[0]
        if 84 + 50 * n == len(data):
            rec = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=n, offset=84)
            return rec["v"].astype(np.float64)
    vs = [list(map(float, l.split()[1:4])) for l in data.decode("ascii", "replace").splitlines() if l.strip().startswith("vertex")]
    return np.array(vs, dtype=np.float64).reshape(-1, 3, 3)


# ------------------------------------------------------------------ slicing

def _layer_mask(tris, tz, z, x0, y0, p, W, H):
    """Solid pixels at height z: nonzero winding of the section. Each crossing triangle adds +1 or -1 at the first pixel
    centre right of where its section segment crosses a pixel row, by the sign of its normal's x (material lies on the
    -normal side), so overlapping shells union and inverted ones still fill. Vertices exactly at z count as below."""
    above = tz > z
    cross = above.any(1) & ~above.all(1)
    if not cross.any():
        return np.zeros((H, W), bool)
    T = tris[cross]
    A = above[cross]
    nx = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])[:, 0]
    pts = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        a, b = T[:, i], T[:, j]
        m = A[:, i] != A[:, j]
        t = np.where(m, (z - a[:, 2]) / np.where(m, b[:, 2] - a[:, 2], 1.0), np.nan)
        pts.append(a[:, :2] + t[:, None] * (b[:, :2] - a[:, :2]))
    P = np.stack(pts, 1)                                   # (n, 3 edges, xy), NaN where the edge does not cross
    ok = ~np.isnan(P[:, :, 0])
    order = np.argsort(~ok, axis=1, kind="stable")[:, :2]
    S = np.take_along_axis(P, order[:, :, None], 1)        # (n, 2, xy)
    sign = np.where(nx < 0, 1, np.where(nx > 0, -1, 0)).astype(np.int32)
    ya, yb = S[:, 0, 1], S[:, 1, 1]
    ylo, yhi = np.minimum(ya, yb), np.maximum(ya, yb)
    j0 = np.clip(np.ceil((ylo - y0) / p - 0.5), 0, H).astype(np.int64)
    j1 = np.clip(np.ceil((yhi - y0) / p - 0.5), 0, H).astype(np.int64)
    cnt = np.where(sign != 0, j1 - j0, 0)
    cnt = np.maximum(cnt, 0)
    tot = int(cnt.sum())
    if not tot:
        return np.zeros((H, W), bool)
    diff = np.zeros((H, W + 1), np.int16)
    if tot:
        seg = np.repeat(np.arange(len(cnt)), cnt)
        start = np.repeat(np.cumsum(cnt) - cnt, cnt)
        rows = np.repeat(j0, cnt) + (np.arange(tot) - start)
        yr = y0 + (rows + 0.5) * p
        xa, xb = S[seg, 0, 0], S[seg, 1, 0]
        yA, yB = S[seg, 0, 1], S[seg, 1, 1]
        x = xa + (yr - yA) * (xb - xa) / (yB - yA)
        cols = np.clip(np.ceil((x - x0) / p - 0.5), 0, W).astype(np.int64)
        np.add.at(diff, (rows, cols), sign[seg])
    out = np.zeros((H, W), bool)
    r0, r1 = int(j0[cnt > 0].min()), int(j1[cnt > 0].max())
    out[r0:r1] = np.cumsum(diff[r0:r1], 1, dtype=np.int16)[:, :W] != 0
    return out


def _disk(r):
    r = max(0.0, r)
    n = int(math.floor(r))
    return [(dy, dx) for dy in range(-n, n + 1) for dx in range(-n, n + 1) if dy * dy + dx * dx <= r * r + 1e-9]


def _dilate(m, offs):
    out = m.copy()
    H, W = m.shape
    for dy, dx in offs:
        if dy == 0 and dx == 0:
            continue
        ys, yd = (slice(0, H - dy), slice(dy, H)) if dy >= 0 else (slice(-dy, H), slice(0, H + dy))
        xs, xd = (slice(0, W - dx), slice(dx, W)) if dx >= 0 else (slice(-dx, W), slice(0, W + dx))
        out[yd, xd] |= m[ys, xs]
    return out


N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _components(m):
    """8-connected components of a boolean window: list of (ys, xs) index arrays."""
    H, W = m.shape
    seen = np.zeros_like(m)
    out = []
    for y, x in zip(*np.nonzero(m)):
        if seen[y, x]:
            continue
        seen[y, x] = True
        q, ys, xs = deque([(y, x)]), [], []
        while q:
            cy, cx = q.popleft()
            ys.append(cy)
            xs.append(cx)
            for dy, dx in N8:
                ny, nx_ = cy + dy, cx + dx
                if 0 <= ny < H and 0 <= nx_ < W and m[ny, nx_] and not seen[ny, nx_]:
                    seen[ny, nx_] = True
                    q.append((ny, nx_))
        out.append((np.array(ys), np.array(xs)))
    return out


def _fill_holes(R, S):
    """R plus the air pockets of this layer that R alone encloses (8-neighbour ring entirely in R, off the window edge)."""
    ys, xs = np.nonzero(R)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    air = ~S[y0:y1, x0:x1]
    if not air.any():
        return R
    out = R.copy()
    Rw = R[y0:y1, x0:x1]
    for hy, hx in _components(air):
        if hy.min() == 0 or hx.min() == 0 or hy.max() == y1 - y0 - 1 or hx.max() == x1 - x0 - 1:
            continue
        m = np.zeros_like(air)
        m[hy, hx] = True
        ring = _dilate(m, N8) & ~m
        if (Rw | ~ring).all():
            out[hy + y0, hx + x0] = True
    return out


def _nearest(free, seed, cap=4000):
    """Largest straight-line distance (pixels) from a pixel of `free` to the nearest pixel of `seed` (its edge)."""
    fy, fx = np.nonzero(free)
    if not len(fy):
        return 0.0
    edge = seed & _dilate(free, N8)
    sy, sx = np.nonzero(edge if edge.any() else seed)
    if not len(sy):
        return float("inf")
    if len(fy) > cap:
        k = np.linspace(0, len(fy) - 1, cap).astype(int)
        fy, fx = fy[k], fx[k]
    best = np.full(len(fy), np.inf)
    for i in range(0, len(sy), 2000):
        d = (fy[:, None] - sy[None, i:i + 2000]) ** 2 + (fx[:, None] - sx[None, i:i + 2000]) ** 2
        best = np.minimum(best, d.min(1))
    return float(np.sqrt(best.max())) + 0.5


def _chords(R, P, ys, xs, p, ndir=12, cap=800, dirs=None):
    """For each of ndir directions: share of R's pixels whose straight line through R ends on supported material P at
    both ends, and the longest such line (mm). Lines are marched in 0.7 pixel steps."""
    if cap and len(ys) > cap:
        k = np.linspace(0, len(ys) - 1, cap).astype(int)
        ys, xs = ys[k], xs[k]
    H, W = R.shape
    ry, rx = np.nonzero(R)
    maxst = int(1.5 * math.hypot(ry.max() - ry.min() + 1, rx.max() - rx.min() + 1)) + 4   # 0.7 px steps across R
    res = []
    for deg in (dirs if dirs is not None else [180.0 * i / ndir for i in range(ndir)]):
        th = math.radians(deg)
        dy, dx = math.sin(th) * 0.7, math.cos(th) * 0.7
        st = np.arange(1, maxst + 1, dtype=np.float64)
        ends, lens = [], []
        for sgn in (1, -1):
            hitP = np.zeros(len(ys), bool)
            L = np.zeros(len(ys))
            for c0 in range(0, len(ys), 4000):
                yy, xx = ys[c0:c0 + 4000, None], xs[c0:c0 + 4000, None]
                cy = np.floor(yy + 0.5 + sgn * dy * st).astype(np.int64)
                cx = np.floor(xx + 0.5 + sgn * dx * st).astype(np.int64)
                inb = (cy >= 0) & (cy < H) & (cx >= 0) & (cx < W)
                cyc, cxc = np.clip(cy, 0, H - 1), np.clip(cx, 0, W - 1)
                inR = inb & R[cyc, cxc]
                first = np.argmin(inR, 1)                   # first step outside R (R is bounded, so one exists)
                rows = np.arange(len(first))
                hitP[c0:c0 + 4000] = inb[rows, first] & P[cyc[rows, first], cxc[rows, first]]
                L[c0:c0 + 4000] = st[first] * 0.7
            ends.append(hitP)
            lens.append(L)
        both = ends[0] & ends[1]
        span = float((lens[0] + lens[1])[both].max()) * p if both.any() else 0.0
        res.append((float(both.mean()), span, deg, both, ys, xs))
    return res


def analyze(tris, cfg=None, supports="no", print_to_world=None, keep_pixels=False):
    """Layer analysis of one part in print orientation (z up, bed at the lowest vertex). print_to_world: (R3x3, t3)
    with world = R @ p + t. Returns a dict: counts, worst values, regions (largest first), findings (fail/warn)."""
    C = dict(DEFAULTS)
    C.update(cfg or {})
    h, tan = C["layer_h"], math.tan(math.radians(C["overhang_deg"]))
    tris = np.asarray(tris, np.float64)
    tris = tris[np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1) > 1e-12]
    zmin = tris[:, :, 2].min()
    tris = tris - np.array([0, 0, zmin])
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    p = max(C["px"], math.sqrt(max(1e-9, (hi[0] - lo[0]) * (hi[1] - lo[1])) / C["max_cells"]))
    r_mm = h * tan + 0.5 * p                          # allowance plus raster slack
    offs = _disk(r_mm / p)
    marg = int(math.ceil(r_mm / p)) + 3
    x0, y0 = lo[0] - marg * p, lo[1] - marg * p
    W = int(math.ceil((hi[0] - lo[0]) / p)) + 2 * marg
    H = int(math.ceil((hi[1] - lo[1]) / p)) + 2 * marg
    tz = tris[:, :, 2]
    nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    vert = np.abs(nrm[:, 2]) <= 1e-5 * np.linalg.norm(nrm, axis=1)   # float32 STL walls
    last_cross = None
    nl = int(math.ceil(hi[2] / h - 1e-6))
    px2 = p * p
    regions = []
    prev = None
    n_thin = 0
    thin_offs = _disk(C["min_feature_mm"] / 2 / p)
    for k in range(nl):
        z = min((k + 0.5) * h, hi[2] - 1e-4) + 1.37e-4
        cross = np.nonzero((tz > z).any(1) & ~(tz > z).all(1))[0]
        if prev is not None and np.array_equal(cross, last_cross) and vert[cross].all():
            cur = prev                     # same walls, all vertical: the section has not changed
        else:
            cur = _layer_mask(tris, tz, z, x0, y0, p, W, H)
        last_cross = cross
        if prev is None:
            prev = cur
            continue
        new = cur & ~prev
        if new.sum() * px2 >= C["min_region_mm2"]:
            ys_, xs_ = np.nonzero(new)
            pad = marg + 2
            wy0, wy1 = max(0, ys_.min() - pad), min(H, ys_.max() + pad + 1)
            wx0, wx1 = max(0, xs_.min() - pad), min(W, xs_.max() + pad + 1)
            S, Sp = cur[wy0:wy1, wx0:wx1], prev[wy0:wy1, wx0:wx1]
            D = _dilate(Sp, offs)
            U = S & ~D
            Pm = S & D
            for ys, xs in _components(U):
                area = len(ys) * px2
                if area < C["min_region_mm2"]:
                    continue
                # this region's own box (plus a margin for its anchors): the window can span the whole part
                cy0, cx0 = max(0, ys.min() - 3), max(0, xs.min() - 3)
                cy1, cx1 = min(U.shape[0], ys.max() + 4), min(U.shape[1], xs.max() + 4)
                ys, xs = ys - cy0, xs - cx0
                Sl, Pl = S[cy0:cy1, cx0:cx1], Pm[cy0:cy1, cx0:cx1]
                R = np.zeros_like(Sl)
                R[ys, xs] = True
                A = Pl & _dilate(R, N8)
                reg = {"z_mm": round(k * h, 2), "layer": k, "area_mm2": round(area, 2)}
                if not (~_dilate(~R, thin_offs)).any():
                    n_thin += 1                      # thinner than a line: drop it, so it carries nothing above it
                    if cur is prev:
                        cur = cur.copy()
                    cur[wy0 + cy0 + ys, wx0 + cx0 + xs] = False
                    continue
                near = _nearest(R, A) * p if A.any() else None
                if near is None:
                    reg["kind"] = "island"
                elif near <= C["cantilever_warn_mm"]:
                    reg.update(kind="cantilever", overhang_mm=round(near, 1), anchored_frac=0.0)   # a short ledge
                else:
                    Rb = _fill_holes(R, Sl)    # a counterbore roof: lines cross its screw hole to the far wall
                    ch = _chords(Rb, Pl, ys.astype(float), xs.astype(float), p)
                    frac, span, ang, both, sy, sx = max(ch, key=lambda c: (round(c[0], 2), -c[1]))
                    if frac > 0 and len(sy) < len(ys):     # the best direction again on every pixel, for the seeds below
                        frac, span, ang, both, sy, sx = _chords(Rb, Pl, ys.astype(float), xs.astype(float), p, dirs=[ang], cap=12000)[0]
                    seed = A.copy()                         # bridged pixels anchor the rest, as the anchors do
                    if both.any():
                        seed[sy[both].astype(int), sx[both].astype(int)] = True
                    free = R & ~seed
                    reach = _nearest(free, seed) * p
                    if frac >= C["bridge_frac"]:
                        reg.update(kind="bridge", span_mm=round(span, 1), bridge_dir_deg=round(ang), anchored_frac=round(frac, 2),
                                   residual_mm=round(reach, 1))
                    else:
                        reg.update(kind="cantilever", overhang_mm=round(reach, 1), anchored_frac=round(frac, 2))
                oy, ox = wy0 + cy0, wx0 + cx0
                cy, cx = ys.mean() + oy, xs.mean() + ox
                c = [x0 + (cx + 0.5) * p, y0 + (cy + 0.5) * p, k * h]
                ext = [(xs.max() - xs.min() + 1) * p, (ys.max() - ys.min() + 1) * p]
                reg["at_print"] = [round(float(v), 1) for v in c]
                reg["extent_mm"] = [round(float(v), 1) for v in ext]
                if print_to_world is not None:
                    Rw, tw = print_to_world
                    reg["at_world"] = [round(float(v), 1) for v in np.asarray(Rw) @ (np.array(c) + [0, 0, zmin]) + np.asarray(tw)]
                if keep_pixels:
                    reg["_px"] = (x0 + (xs + ox + 0.5) * p, y0 + (ys + oy + 0.5) * p, k * h, p)
                    m = max(cy1 - cy0, cx1 - cx0) // 2      # some context around the region
                    my0, mx0 = max(0, oy - m), max(0, ox - m)
                    my1, mx1 = min(H, oy + (cy1 - cy0) + m), min(W, ox + (cx1 - cx0) + m)
                    Rm = np.zeros((my1 - my0, mx1 - mx0), bool)
                    Am = Rm.copy()
                    Rm[oy - my0:oy - my0 + R.shape[0], ox - mx0:ox - mx0 + R.shape[1]] = R
                    Am[oy - my0:oy - my0 + R.shape[0], ox - mx0:ox - mx0 + R.shape[1]] = A
                    reg["_map"] = (prev[my0:my1, mx0:mx1].copy(), cur[my0:my1, mx0:mx1] & ~Rm, Rm, Am)
                regions.append(reg)
        prev = cur
    nosup = str(supports or "").lower() in ("no", "none", "false", "")
    for g in regions:
        if g["kind"] == "island" and g["area_mm2"] >= C["island_mm2"]:
            g["status"] = "fail" if nosup else "support"
        elif g["kind"] == "cantilever" and g["overhang_mm"] > C["cantilever_mm"]:
            g["status"] = "fail" if nosup else "support"
        elif g["kind"] == "cantilever" and g["overhang_mm"] > C["cantilever_warn_mm"]:
            g["status"] = "warn" if nosup else "support"
        elif g["kind"] == "bridge" and g["span_mm"] > C["bridge_warn_mm"]:
            g["status"] = "warn"
        else:
            g["status"] = "ok"
    sev = {"fail": 0, "support": 1, "warn": 2, "ok": 3}
    regions.sort(key=lambda g: (sev[g["status"]], -g.get("overhang_mm", g.get("span_mm", 0)), -g["area_mm2"]))
    findings = _findings(regions)
    by = lambda kind: [g for g in regions if g["kind"] == kind]
    out = {"layers": nl, "layer_h": h, "px_mm": round(p, 3), "allowance_mm": round(r_mm, 3), "height_mm": round(float(hi[2]), 2),
           "supports": supports, "needs_support": any(g["status"] in ("fail", "support") for g in regions),
           "n_islands": sum(g["status"] in ("fail", "support") for g in by("island")),
           "n_cantilevers": sum(g["status"] in ("fail", "support") for g in by("cantilever")),
           "max_overhang_mm": max([g["overhang_mm"] for g in by("cantilever")] or [0.0]),
           "max_bridge_mm": max([g["span_mm"] for g in by("bridge")] or [0.0]),
           "n_regions": len(regions), "n_thin_dropped": n_thin, "regions": regions[:C["max_regions"]] if not keep_pixels else regions,
           "findings": findings}
    return out


def _findings(regions):
    out = []
    for g in regions:
        if g["status"] in ("fail", "warn"):
            what = {"island": "an island starts in mid-air (%.1f mm2)" % g["area_mm2"],
                    "cantilever": "a %.1f mm cantilever (%.1f mm2, extent %s)" % (g.get("overhang_mm", 0), g["area_mm2"], g["extent_mm"]),
                    "bridge": "a %.1f mm bridge" % g.get("span_mm", 0)}[g["kind"]]
            out.append({"status": g["status"], "kind": g["kind"], "z_mm": g["z_mm"], "msg": "%s at z %.1f (print %s%s)" % (
                what, g["z_mm"], g["at_print"], ", world %s" % g["at_world"] if "at_world" in g else "")})
    return out


def analyze_cached(tris, cfg=None, supports="no", print_to_world=None):
    """analyze() with a result cache under $TMPDIR keyed on the triangles and the config: cadcheck re-runs `parts` on
    every check, and most parts have not changed. World coordinates are added after the lookup."""
    import hashlib
    C = dict(DEFAULTS)
    C.update(cfg or {})
    T = np.ascontiguousarray(np.asarray(tris, np.float32))
    key = hashlib.sha1(T.tobytes() + json.dumps(C, sort_keys=True).encode() + str(supports).encode() + _VERSION.encode()).hexdigest()
    d = os.path.join(os.environ.get("TMPDIR", "/tmp"), "cad-printcheck-cache")
    fp = os.path.join(d, key + ".json")
    res = None
    if os.path.isfile(fp):
        try:
            with open(fp) as f:
                res = json.load(f)
        except (OSError, ValueError):
            res = None
    if res is None:
        res = analyze(tris, cfg, supports=supports)
        try:
            os.makedirs(d, exist_ok=True)
            with open(fp + ".tmp", "w") as f:
                json.dump(res, f)
            os.replace(fp + ".tmp", fp)
        except OSError:
            pass
    if print_to_world is not None:
        Rw, tw = print_to_world
        z0 = float(np.asarray(tris)[:, :, 2].min())
        for g in res["regions"]:
            g["at_world"] = [round(float(v), 1) for v in np.asarray(Rw) @ (np.array(g["at_print"]) + [0, 0, z0]) + np.asarray(tw)]
        res["findings"] = _findings(res["regions"])
    return res


# ------------------------------------------------------------------ manifests, world frame, files

def manifest_parts(path):
    """stl name -> {objects, supports, print_rot, bbox_world_home} from a cadlib manifest.json."""
    if not path or not os.path.isfile(path):
        return {}
    with open(path) as f:
        m = json.load(f)
    out = {}
    for name, v in (m.get("parts") or {}).items():
        if v.get("kind") != "PRT" or not v.get("stl"):
            continue
        e = out.setdefault(v["stl"], {"objects": [], "supports": v.get("supports"), "print_rot": v.get("print_rot"),
                                      "bbox_world_home": v.get("bbox_world_home")})
        e["objects"].append(name)
    return out


def world_map(tris, print_rot, bbox_world_home):
    """(R, t) with world = R @ stl_point + t. The STL is R_print @ world + offset, so R_print^T @ stl is the world point
    set shifted by a constant; its bbox minimum against the manifest's world bbox gives the shift (to its 0.1 rounding)."""
    if not print_rot or not bbox_world_home:
        return None
    Rt = np.array(print_rot, np.float64).T
    q = tris.reshape(-1, 3) @ Rt.T
    return Rt, np.array(bbox_world_home[0], np.float64) - q.min(0)


def find_manifest(stl_path):
    d = os.path.dirname(os.path.abspath(stl_path if os.path.isdir(stl_path) is False else os.path.join(stl_path, "x")))
    for c in (os.path.join(d, "manifest.json"), os.path.join(d, "..", "manifest.json"), os.path.join(d, "..", "blender", "manifest.json")):
        if os.path.isfile(c):
            return os.path.normpath(c)
    return None


def run(paths, manifest=None, cfg=None, only=None, render_dir=None, out=None):
    files = []
    for pth in paths:
        files += sorted(glob.glob(os.path.join(pth, "*.stl"))) if os.path.isdir(pth) else [pth]
    if only:
        files = [f for f in files if any(fnmatch.fnmatch(os.path.basename(f)[:-4], g) for g in only.split(","))]
    man_path = manifest or (find_manifest(files[0]) if files else None)
    man = manifest_parts(man_path)
    rows = []
    for fp in files:
        name = os.path.basename(fp)[:-4]
        tris = read_stl(fp)
        info = man.get(name, {})
        sup = info.get("supports", "no" if not man else None)
        wm = world_map(tris - [0, 0, tris[:, :, 2].min()], info.get("print_rot"), info.get("bbox_world_home"))
        r = analyze(tris, cfg, supports=sup if sup is not None else "no", print_to_world=wm, keep_pixels=bool(render_dir))
        r.update(stl=name, file=fp, objects=info.get("objects", []), supports=sup)
        if render_dir and (r["findings"] or any(g["status"] == "support" for g in r["regions"])):
            r["render"] = render_flags(tris, r, os.path.join(render_dir, name + "_printcheck.png"))
        if render_dir:
            maps = [layer_map(g, os.path.join(render_dir, "%s_z%05.1f_%s.png" % (name, g["z_mm"], g["kind"])))
                    for g in r["regions"] if g["status"] != "ok"][:8]
            if maps:
                r["layer_maps"] = maps
        for g in r["regions"]:
            g.pop("_px", None)
            g.pop("_map", None)
        r["regions"] = r["regions"][:(cfg or {}).get("max_regions", DEFAULTS["max_regions"])]
        rows.append(r)
    fails = [(r["stl"], f["msg"]) for r in rows for f in r["findings"] if f["status"] == "fail"]
    warns = [(r["stl"], f["msg"]) for r in rows for f in r["findings"] if f["status"] == "warn"]
    rep = {"tool": "printcheck", "manifest": man_path, "config": dict(DEFAULTS, **(cfg or {})), "parts": rows,
           "summary": {"parts": len(rows), "fails": len(fails), "warns": len(warns),
                       "need_support": sorted(r["stl"] for r in rows if r["needs_support"]),
                       "fail_list": ["%s: %s" % x for x in fails], "warn_list": ["%s: %s" % x for x in warns]}}
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        with open(out, "w") as f:
            json.dump(rep, f, indent=1)
    return rep


def print_summary(rep, out=None):
    s = rep["summary"]
    print("PRINTCHECK %s: %d parts, %d fail, %d warn%s%s" % ("PASS" if not s["fails"] else "FAIL", s["parts"], s["fails"], s["warns"],
          "; need support: %s" % ", ".join(s["need_support"]) if s["need_support"] else "", " -> %s" % out if out else ""))
    if not rep.get("manifest"):
        print("  no manifest found: every part checked as supports: no, print frame only (pass --manifest for world coordinates)")
    for r in rep["parts"]:
        print("  %-22s h %5.1f  %s" % (r["stl"], r["height_mm"], "; ".join(
            "%s %s" % (f["status"].upper(), f["msg"]) for f in r["findings"][:4]) or "ok (max bridge %.1f mm, max ledge %.1f mm)" % (
            r["max_bridge_mm"], r["max_overhang_mm"])))


# ------------------------------------------------------------------ renders

def write_png(path, rgb):
    """(H, W, 3) uint8 to PNG, stdlib only."""
    import zlib
    H, W, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[H - 1 - y].tobytes() for y in range(H))     # print-frame +y up
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
    return path


def layer_map(g, path, scale=4):
    """Top view of one flagged layer around the region: layer below (dark grey), supported part of this layer (light
    grey), the unsupported region (red: fail or needs support, amber: long bridge, blue: within allowances) and the
    pixels it is anchored on (green)."""
    if "_map" not in g:
        return None
    Sp, Pm, R, A = g["_map"]
    img = np.full(R.shape + (3,), 255, np.uint8)
    img[Sp] = (90, 90, 90)
    img[Pm & ~Sp] = (190, 190, 190)
    img[R] = {"fail": (220, 30, 30), "support": (240, 120, 0), "warn": (240, 190, 0)}.get(g["status"], (60, 110, 220))
    img[A & ~Sp] = (40, 170, 60)
    img[A & Sp] = (30, 120, 45)
    return write_png(path, np.repeat(np.repeat(img, scale, 0), scale, 1))


# ------------------------------------------------------------------ render (Blender only)

def render_flags(tris, res, out_png):
    """Workbench render from below of the part in print orientation, flagged regions as coloured layer pixels:
    red = fail (island / cantilever on supports: no), orange = would need support (supports: yes), amber = long bridge."""
    try:
        import bpy
        from mathutils import Vector
    except ImportError:
        return None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    T = np.asarray(tris, np.float64) - [0, 0, np.asarray(tris)[:, :, 2].min()]
    me = bpy.data.meshes.new("part")
    me.from_pydata([tuple(v) for v in T.reshape(-1, 3)], [], [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(T))])
    ob = bpy.data.objects.new("part", me)
    sc.collection.objects.link(ob)
    col = {"fail": (0.9, 0.1, 0.1, 1), "support": (1.0, 0.45, 0.0, 1), "warn": (1.0, 0.75, 0.0, 1)}
    mats = {}
    for st, c in col.items():
        m = bpy.data.materials.new(st)
        m.diffuse_color = c
        mats[st] = m
    base = bpy.data.materials.new("base")
    base.diffuse_color = (0.78, 0.78, 0.78, 1)
    ob.data.materials.append(base)
    for g in res["regions"]:
        if g["status"] not in col or "_px" not in g:
            continue
        xs, ys, z, p = g["_px"]
        if len(xs) > 6000:
            k = np.linspace(0, len(xs) - 1, 6000).astype(int)
            xs, ys = xs[k], ys[k]
        vs, fs = [], []
        for x, y in zip(xs, ys):
            i = len(vs)
            vs += [(x - p / 2, y - p / 2, z - 0.02), (x + p / 2, y - p / 2, z - 0.02), (x + p / 2, y + p / 2, z - 0.02), (x - p / 2, y + p / 2, z - 0.02)]
            fs.append((i, i + 3, i + 2, i + 1))
        m2 = bpy.data.meshes.new("flag")
        m2.from_pydata(vs, [], fs)
        o2 = bpy.data.objects.new("flag", m2)
        o2.data.materials.append(mats[g["status"]])
        sc.collection.objects.link(o2)
    lo, hi = T.reshape(-1, 3).min(0), T.reshape(-1, 3).max(0)
    c = Vector(((lo + hi) / 2).tolist())
    d = float(max(hi - lo))
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.light = "STUDIO"
    sc.render.resolution_x = sc.render.resolution_y = 700
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = d * 1.5
    cam.data.clip_end = d * 10
    cam.location = c + Vector((1.0, 0.35, -0.6)).normalized() * d * 3   # from below and to the side: the undersides
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    sc.render.filepath = out_png
    bpy.ops.render.render(write_still=True)
    return out_png


def _main(argv):
    pos, opt = [], {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            opt[a[2:]] = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        else:
            pos.append(a)
            i += 1
    if not pos:
        print(__doc__.split("\n\n")[0])
        return 2
    cfg = {}
    if "layer" in opt:
        cfg["layer_h"] = float(opt["layer"])
    if "px" in opt:
        cfg["px"] = float(opt["px"])
    if "config" in opt:
        with open(opt["config"]) as f:
            cfg.update(json.load(f).get("printcheck", {}))
    out = opt.get("out") or os.path.join(pos[0] if os.path.isdir(pos[0]) else os.path.dirname(os.path.abspath(pos[0])), "printcheck.json")
    rep = run(pos, opt.get("manifest"), cfg, opt.get("only"), opt.get("render"), out)
    print_summary(rep, out)
    return 1 if rep["summary"]["fails"] else 0


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    sys.exit(_main(a))
