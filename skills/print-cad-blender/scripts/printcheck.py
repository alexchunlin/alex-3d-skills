"""printcheck: layer-based support analysis of printed parts, on the exported STLs (print frame, bed at z = 0).

    cad printcheck <stl_dir | part.stl ...> [--manifest manifest.json] [--out printcheck.json] [--render DIR]
                   [--layer 0.2] [--px 0.1] [--only GLOB] [--config checks.json] [--where]
                   [--section Z[,Z..] | auto] [--cell MM] [--window X0,Y0,X1,Y1]

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
The face pass (face_regions) catches what the layer check cannot: it compares each layer with the one below only and
accepts sub-millimetre steps, so a gradual overhang never builds up (a 20 mm ramp 5-40 deg from horizontal: 0 fails).
Downward faces flatter than 45 deg from horizontal, off the bed, are grouped through shared vertices; each region's
boundary is anchored where material continues down from it one layer lower. A region anchored on two sides is a sloped
bridge (a horizontal bore's ceiling); otherwise overhang_mm is how far it reaches past the 45 deg cone of its nearest
anchor. Warn past face_warn_mm (2), fail past cantilever_mm (3) with face_fail_mm2 (20) or more projected, on
supports: no. All-flat regions are the layer check's. The STL's edges in more than two faces warn.
Locations are in the print frame (the STL) and, with a manifest (print_rot, bbox_world_home) or from cadcheck, the
world frame. --where lists every region that is not ok and every face region; --section prints layers as text (see
section_lines). Exit status 1 when any part fails.

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

_VERSION = "4"   # bump when analyze() changes what it reports (cache key)


def _source_key():
    """sha1 of this file: part of the cache key, so an edit to the analysis can't pass on results cached before it."""
    import hashlib
    try:
        with open(os.path.abspath(__file__), "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except (OSError, NameError):
        return "nosource"


_SOURCE = _source_key()

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
    # face pass: downward faces steeper than overhang_deg from vertical, grouped by shared edges, measured from their
    # anchored edges along the 45 deg cone (see face_regions). v2's sloped faces reach 1.6 mm past it at most (beam's
    # corner facets), the 40 deg ramp 3.3 and the grown 4-way node 8.9-12.5, so: warn past face_warn_mm, fail past
    # cantilever_mm on a region of face_fail_mm2 or more (half v2's smallest real miss, base_shell's 40 mm2 block)
    "face_flat_deg": 1.0,     # a region of faces all flatter than this is the layer check's: it tells bridge from cantilever
    "face_warn_mm": 2.0,
    "face_fail_mm2": 20.0,
    "face_min_mm2": 2.0,      # smaller face regions are listed, never flagged
    "face_probe_mm": 0.5,     # boundary edges are probed for an anchor every this many mm
    "face_probe_reach_mm": 2.0,  # and at most this far out (downhill edges of flat slopes; see face_regions)
    "nm_min_edge_mm": 0.01,   # STL edge count: shorter edges are slivers (v2 hood's nanometre edges)
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


# ------------------------------------------------------------------ face pass

def _weld(tris, tol=1e-4):
    """Vertex ids per triangle corner, merging corners within tol (float32 STL corners of one vertex agree exactly)."""
    q = np.round(tris.reshape(-1, 3) / tol).astype(np.int64)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    return inv.reshape(-1, 3)


def _edge_keys(F):
    """(3n,) sorted-edge keys and the face each comes from, corner order (0,1), (1,2), (2,0)."""
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    E = np.sort(E, 1)
    return E[:, 0] * (int(F.max()) + 1) + E[:, 1], np.tile(np.arange(len(F)), 3)


def _face_groups(F, idx):
    """Connected groups (lists of indices into idx) of the faces idx, joined through shared vertices."""
    key, fi = F[idx].reshape(-1), np.repeat(np.arange(len(idx)), 3)
    o = np.argsort(key, kind="stable")
    ks, fs = key[o], fi[o]
    parent = np.arange(len(idx))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for s in np.nonzero(ks[1:] == ks[:-1])[0]:
        a, b = find(fs[s]), find(fs[s + 1])
        if a != b:
            parent[a] = b
    roots = np.array([find(i) for i in range(len(idx))])
    order = np.argsort(roots, kind="stable")
    cut = np.nonzero(np.diff(roots[order]))[0] + 1
    return np.split(order, cut)


def _fill_tris(T, x0, y0, p, W, H):
    """Footprint of the 3D triangles T (n, 3, 3) on an (H, W) grid: pixels whose centres lie in a triangle's xy
    projection, plus each corner's, edge midpoint's and centroid's pixel so slivers narrower than a pixel still mark
    their path. Returns the mask and the lowest surface z per pixel (inf off the footprint)."""
    Z = np.full((H, W), np.inf)
    ij = lambda P: (np.clip(np.floor((P[..., 1] - y0) / p).astype(np.int64), 0, H - 1),
                    np.clip(np.floor((P[..., 0] - x0) / p).astype(np.int64), 0, W - 1))
    for P in (T[:, 0], T[:, 1], T[:, 2], T.mean(1), (T[:, 0] + T[:, 1]) / 2, (T[:, 1] + T[:, 2]) / 2, (T[:, 2] + T[:, 0]) / 2):
        np.minimum.at(Z, ij(P), P[:, 2])
    lo, hi = T[:, :, :2].min(1), T[:, :, :2].max(1)
    c0 = np.clip(np.ceil((lo[:, 0] - x0) / p - 0.5), 0, W).astype(np.int64)
    c1 = np.clip(np.floor((hi[:, 0] - x0) / p - 0.5) + 1, 0, W).astype(np.int64)
    r0 = np.clip(np.ceil((lo[:, 1] - y0) / p - 0.5), 0, H).astype(np.int64)
    r1 = np.clip(np.floor((hi[:, 1] - y0) / p - 0.5) + 1, 0, H).astype(np.int64)
    nw, nh = np.maximum(c1 - c0, 0), np.maximum(r1 - r0, 0)
    cnt = nw * nh
    for s in range(0, len(T), 20000):
        sl = slice(s, s + 20000)
        c = cnt[sl]
        tot = int(c.sum())
        if not tot:
            continue
        t = np.repeat(np.arange(len(c)), c)
        k = np.arange(tot) - np.repeat(np.cumsum(c) - c, c)
        w = nw[sl][t]
        cols, rows = c0[sl][t] + k % w, r0[sl][t] + k // w
        px, py = x0 + (cols + 0.5) * p, y0 + (rows + 0.5) * p
        A, B, Cc = T[sl][t, 0], T[sl][t, 1], T[sl][t, 2]
        e = lambda U, V: (V[:, 0] - U[:, 0]) * (py - U[:, 1]) - (V[:, 1] - U[:, 1]) * (px - U[:, 0])
        d0, d1, d2 = e(B, Cc), e(Cc, A), e(A, B)          # barycentric weights of A, B, C (times twice the area)
        inside = ((d0 >= 0) & (d1 >= 0) & (d2 >= 0)) | ((d0 <= 0) & (d1 <= 0) & (d2 <= 0))
        den = d0 + d1 + d2
        ok = inside & (np.abs(den) > 1e-12)
        z = (d0 * A[:, 2] + d1 * B[:, 2] + d2 * Cc[:, 2])[ok] / den[ok]
        np.minimum.at(Z, (rows[ok], cols[ok]), z)
    return np.isfinite(Z), Z


def _excess(R, Z, Az, p, tan, cap=3000):
    """Largest over R's pixels of the horizontal distance past the self-supporting cone of the nearest anchor: for a
    pixel at height z, min over anchors of (distance - (z - anchor z) * tan). A flat ledge gives its reach; a slope
    printed at the allowed angle gives 0, however its facets are cut."""
    fy, fx = np.nonzero(R)
    ay, ax = np.nonzero(np.isfinite(Az))
    if not len(fy) or not len(ay):
        return 0.0, None
    if len(fy) > cap:
        k = np.linspace(0, len(fy) - 1, cap).astype(int)
        fy, fx = fy[k], fx[k]
    if len(ay) > cap:
        k = np.linspace(0, len(ay) - 1, cap).astype(int)
        ay, ax = ay[k], ax[k]
    fz, az = Z[fy, fx], Az[ay, ax]
    best = np.full(len(fy), np.inf)
    for i in range(0, len(ay), 1000):
        d = np.hypot(fy[:, None] - ay[None, i:i + 1000], fx[:, None] - ax[None, i:i + 1000]) * p
        best = np.minimum(best, (d - np.maximum(fz[:, None] - az[None, i:i + 1000], 0.0) * tan).min(1))
    j = int(np.argmax(best))
    return max(0.0, float(best[j])), (fy[j], fx[j])


def face_regions(tris, C, zmin=0.0):
    """Downward faces flatter than overhang_deg from horizontal, off the bed (centroid above the first layer),
    grouped through shared vertices. Flat faces stay in a region with sloped ones, so a horizontal bore's ceiling
    stays one arch anchored on both sides, not two half-arches each anchored on one. The 45 deg line has cadcheck's 1e-3 margin on the normal (44.92 deg):
    float32 STLs carry up to 2,276 mm2 of exact 45 deg faces on one part (PR #6 review). Returns the regions and, by layer, the probes that ask for each piece of a region's
    boundary whether there is material just outside it one layer down (a wall or a self-supporting slope continues
    down from the edge: it is anchored). The layer loop answers them from its own sections."""
    h = C["layer_h"]
    nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    a2 = np.linalg.norm(nrm, axis=1)
    nz = nrm[:, 2] / np.maximum(a2, 1e-30)
    # angle of the face from horizontal: 0 = a flat ceiling, 90 = a wall
    fh = np.degrees(np.arccos(np.clip(-nz, -1.0, 1.0)))
    cos_o = math.cos(math.radians(C["overhang_deg"]))
    F = _weld(tris)
    # corners that weld together make a zero-area face whose doubled edge would hide a real boundary edge
    deg = (F[:, 0] == F[:, 1]) | (F[:, 1] == F[:, 2]) | (F[:, 2] == F[:, 0])
    sel = np.nonzero(~deg & (a2 > 1e-12) & (nz < -cos_o - 1e-3) & (tris[:, :, 2].mean(1) > h))[0]
    if not len(sel):
        return [], {}
    A = a2 / 2
    regions, probes = [], {}
    step = C["face_probe_mm"]
    for g in _face_groups(F, sel):
        fid = sel[g]
        ar = float(A[fid].sum())
        if ar < C["min_region_mm2"]:
            continue
        T = tris[fid]
        # boundary edges: in one face of the group only
        key, fi = _edge_keys(F[fid])
        uk, cnt = np.unique(key, return_counts=True)
        bnd = np.nonzero(cnt[np.searchsorted(uk, key)] == 1)[0]
        e0 = np.array([0, 1, 2])[bnd // len(fid)]
        f = fi[bnd]
        a, b = T[f, e0], T[f, (e0 + 1) % 3]
        c = T[f, (e0 + 2) % 3]
        d = b[:, :2] - a[:, :2]
        L = np.linalg.norm(d, axis=1)
        o = np.stack([d[:, 1], -d[:, 0]], 1) / np.maximum(L, 1e-9)[:, None]
        mid = (a[:, :2] + b[:, :2]) / 2
        flip = ((c[:, :2] - mid) * o).sum(1) > 0
        o[flip] *= -1                                       # outward: away from the face's third corner
        # how far out to look: one allowance past the layer's raster slack, or, across a downhill edge (where the slope
        # carries on down: a bed-side chamfer's foot, a bore's sides), as far as a slope this flat moves in 1.5 layers
        r = h * math.tan(math.radians(C["overhang_deg"]))
        nx = nrm[fid][f, :2] / np.maximum(a2[fid][f], 1e-30)[:, None]
        down = (o * -nx).sum(1) > 0.5 * np.maximum(np.linalg.norm(nx, axis=1), 1e-9)
        fhe = np.radians(np.maximum(fh[fid][f], 1.0))
        reach = np.where(down, np.clip(1.5 * h / np.tan(fhe), 2 * r, C["face_probe_reach_mm"]), 2 * r)
        n = np.maximum(1, np.ceil(L / step)).astype(np.int64)
        e = np.repeat(np.arange(len(a)), n)
        t = (np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n) + 0.5) / np.repeat(n, n)
        P = a[e] + t[:, None] * (b[e] - a[e])
        reg = {"_faces": fid, "_pts": P, "_out": o[e], "_seg": np.repeat(L / n, n), "_dir": d[e] / np.maximum(L[e], 1e-9)[:, None],
               "_sup": np.zeros(len(P), bool), "_reach": reach[e], "area_mm2": ar}
        # probe the layer whose mid-height is 0.5-1.5 layers below the edge point. Edges within the first layer border
        # the bed band (faces there are the bed's), so they are anchored: v1 A3 feeder_shroud's flare starts at z 0.2
        kp = np.floor((P[:, 2] - zmin - 0.75 * h) / h).astype(np.int64)
        kp[P[:, 2] - zmin <= h * 1.05] = -1
        reg["_sup"][kp < 0] = True
        for k in np.unique(kp[kp >= 0]):
            probes.setdefault(int(k), []).append((len(regions), np.nonzero(kp == k)[0]))
        reg["_fh"] = fh[fid]
        regions.append(reg)
    return regions, probes


def _probe(reg, ii, cur, x0, y0, p, W, H, C):
    """Mark the probes ii of reg anchored when this layer has material just outside the edge: from half an allowance
    out to the probe's reach, in half-allowance steps, plus half a raster pixel."""
    P, o, reach = reg["_pts"][ii], reg["_out"][ii], reg["_reach"][ii]
    r = C["layer_h"] * math.tan(math.radians(C["overhang_deg"]))
    hit = np.zeros(len(ii), bool)
    for s in np.arange(0.5 * r, float(reach.max()) + 1e-9, 0.5 * r):
        q = P[:, :2] + o * (s + 0.5 * p)
        cx = np.floor((q[:, 0] - x0) / p).astype(np.int64)
        cy = np.floor((q[:, 1] - y0) / p).astype(np.int64)
        inb = (cx >= 0) & (cx < W) & (cy >= 0) & (cy < H) & (s <= reach + 1e-9)
        hit[inb] |= cur[cy[inb], cx[inb]]
    reg["_sup"][ii] |= hit


def classify_face_region(reg, tris, p, C, zmin=0.0, print_to_world=None):
    """Footprint of the region as pixels, its anchored boundary as the pixels just outside it, and the layer check's
    measures on that pair: a bridge when straight lines in one direction end on anchors at both ends for at least
    bridge_frac of it (a horizontal hole's top, a drill-point roof, a tube's underside between two walls); else a
    cantilever whose overhang_mm is how far it reaches past the 45 deg cone of its nearest anchor (a ramp, a tube's
    underside off one wall, a ledge); floating when no edge is anchored."""
    fid = reg["_faces"]
    T = tris[fid]
    lo, hi = T.reshape(-1, 3).min(0), T.reshape(-1, 3).max(0)
    marg = 4
    x0, y0 = lo[0] - marg * p, lo[1] - marg * p
    W = int(math.ceil((hi[0] - lo[0]) / p)) + 2 * marg
    H = int(math.ceil((hi[1] - lo[1]) / p)) + 2 * marg
    R, Z = _fill_tris(T, x0, y0, p, W, H)
    S = reg["_sup"]
    Az = np.full((H, W), np.inf)
    if S.any():
        P, o, seg, dr = reg["_pts"][S], reg["_out"][S], reg["_seg"][S], reg["_dir"][S]
        k = np.maximum(1, np.ceil(seg / (0.5 * p))).astype(np.int64)
        e = np.repeat(np.arange(len(P)), k)
        t = (np.arange(int(k.sum())) - np.repeat(np.cumsum(k) - k, k) + 0.5) / np.repeat(k, k) - 0.5
        Q = P[e, :2] + dr[e] * (t * seg[e])[:, None]
        for s in (0.5, 1.0, 1.5):
            q = Q + o[e] * (s * p)
            cx = np.clip(np.floor((q[:, 0] - x0) / p).astype(np.int64), 0, W - 1)
            cy = np.clip(np.floor((q[:, 1] - y0) / p).astype(np.int64), 0, H - 1)
            np.minimum.at(Az, (cy, cx), P[e, 2])
        Az[R | ~_dilate(R, N8)] = np.inf
    A = np.isfinite(Az)
    fh = reg["_fh"]
    w = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1)
    out = {"area_mm2": round(reg["area_mm2"], 1), "projected_mm2": round(float((w * np.cos(np.radians(fh))).sum() / 2), 1),
           "deg_limit": C["overhang_deg"],
           "deg_from_vertical": [round(90 - float(fh.max()), 1), round(90 - float(fh.min()), 1)],
           "mean_deg_from_vertical": round(90 - float((fh * w).sum() / w.sum()), 1),
           "z_mm": [round(float(lo[2]), 2), round(float(hi[2]), 2)],
           "anchored_edge_mm": round(float(reg["_seg"][S].sum()), 1), "edge_mm": round(float(reg["_seg"].sum()), 1)}
    tan = math.tan(math.radians(C["overhang_deg"]))
    if not A.any():
        out.update(kind="floating", overhang_mm=round(float(max(hi[0] - lo[0], hi[1] - lo[1])), 1))
    else:
        ys, xs = np.nonzero(R)
        ch = _chords(R, A, ys.astype(float), xs.astype(float), p)
        frac, span, ang, both, sy, sx = max(ch, key=lambda c: (round(c[0], 2), -c[1]))
        if frac >= C["bridge_frac"]:
            out.update(kind="bridge", span_mm=round(span, 1), anchored_frac=round(frac, 2))
        else:
            ex, _ = _excess(R, Z, Az, p, tan)
            out.update(kind="cantilever", overhang_mm=round(ex, 1), anchored_frac=round(frac, 2))
    cen = (T.mean(1) * w[:, None]).sum(0) / w.sum()
    out["at_print"] = [round(float(v), 1) for v in cen]
    out["extent_mm"] = [round(float(v), 1) for v in (hi - lo)[:2]]
    if print_to_world is not None:
        Rw, tw = print_to_world
        out["at_world"] = [round(float(v), 1) for v in np.asarray(Rw) @ (cen + [0, 0, zmin]) + np.asarray(tw)]
    return out


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
    fregs, probes = face_regions(tris, C)
    thin_offs = _disk(C["min_feature_mm"] / 2 / p)
    for k in range(nl):
        z = min((k + 0.5) * h, hi[2] - 1e-4) + 1.37e-4
        cross = np.nonzero((tz > z).any(1) & ~(tz > z).all(1))[0]
        if prev is not None and np.array_equal(cross, last_cross) and vert[cross].all():
            cur = prev                     # same walls, all vertical: the section has not changed
        else:
            cur = _layer_mask(tris, tz, z, x0, y0, p, W, H)
        last_cross = cross
        for ri, ii in probes.get(k, ()):
            _probe(fregs[ri], ii, cur, x0, y0, p, W, H, C)
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
    faces = []
    for fr in fregs:
        g = classify_face_region(fr, tris, p, C, zmin, print_to_world)
        g["status"] = _face_status(g, C, nosup)
        if keep_pixels:
            g["_faces"] = fr["_faces"]
        faces.append(g)
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
    sev["layer"] = 4
    faces.sort(key=lambda g: (sev[g["status"]], -g.get("overhang_mm", g.get("span_mm", 0)), -g["area_mm2"]))
    nm = stl_edges(tris, C)
    findings = _findings(regions, faces, nm)
    by = lambda kind: [g for g in regions if g["kind"] == kind]
    fl = [g for g in faces if g["status"] in ("fail", "support", "warn")]
    out = {"layers": nl, "layer_h": h, "px_mm": round(p, 3), "allowance_mm": round(r_mm, 3), "height_mm": round(float(hi[2]), 2),
           "supports": supports, "needs_support": any(g["status"] in ("fail", "support") for g in regions + faces),
           "n_islands": sum(g["status"] in ("fail", "support") for g in by("island")),
           "n_cantilevers": sum(g["status"] in ("fail", "support") for g in by("cantilever")),
           "max_overhang_mm": max([g["overhang_mm"] for g in by("cantilever")] or [0.0]),
           "max_bridge_mm": max([g["span_mm"] for g in by("bridge")] or [0.0]),
           "n_regions": len(regions), "n_thin_dropped": n_thin, "regions": regions[:C["max_regions"]] if not keep_pixels else regions,
           "n_face_overhangs": sum(g["status"] in ("fail", "support") for g in faces),
           "max_face_overhang_mm": max([g["overhang_mm"] for g in faces if g["status"] != "layer" and "overhang_mm" in g] or [0.0]),
           "face_overhang_mm2": round(sum(g["projected_mm2"] for g in fl), 1), "n_face_regions": len(faces),
           "faces": [g for g in faces if g["projected_mm2"] >= C["face_min_mm2"]][:C["max_regions"]] if not keep_pixels else faces,
           "stl_nonmanifold_edges": nm["n"], "stl_nonmanifold_at": nm["at"], "findings": findings}
    return out


def _face_status(g, C, nosup):
    """Face-pass verdict. A flat region (all faces within face_flat_deg of horizontal, or all within one layer) is the
    layer check's call: it sees the whole region at its layer and tells a bridge from a cantilever, so the region is
    listed here as 'layer' and judged there."""
    sup = "fail" if nosup else "support"
    if g["z_mm"][1] - g["z_mm"][0] <= C["layer_h"] + 1e-6 or g["deg_from_vertical"][0] > 90 - C["face_flat_deg"]:
        return "layer"
    if g["projected_mm2"] < C["face_min_mm2"]:
        return "ok"
    if g["kind"] == "bridge":
        return "warn" if g["span_mm"] > C["bridge_warn_mm"] else "ok"
    if g["kind"] == "floating" or g["overhang_mm"] > C["cantilever_mm"]:
        return sup if g["projected_mm2"] >= C["face_fail_mm2"] else ("warn" if nosup else "support")
    if g["overhang_mm"] > C["face_warn_mm"]:
        return "warn" if nosup else "support"
    return "ok"


def stl_edges(tris, C):
    """Edges shared by more than two faces in the triangles as an STL stores them: float32 corners, welded only where
    they are equal (as a slicer's loader does), collapsed faces dropped, edges under nm_min_edge_mm ignored. v2
    base_shell has 7: r 5 mm cylinders touching the inner wall along a line. The model keeps those vertex pairs apart,
    so its own manifold test passes, and the export makes them one (PR #6 review). v2 hood's one 22.45 mm edge in 4
    faces is not counted: two of the faces are 4 nm wide (4e-5 mm2, opposite normals), a zero-volume sliver that slices
    to nothing, not two solids touching."""
    T = np.asarray(tris, np.float32).astype(np.float64)
    u, inv = np.unique(T.reshape(-1, 3), axis=0, return_inverse=True)
    F = inv.reshape(-1, 3)
    # collapsed faces and needles (under nm_min_edge_mm / 10 wide: v2 hood's 22 mm long, 5 um wide slivers) go first
    L = np.linalg.norm(T - T[:, [1, 2, 0]], axis=2).max(1)
    wide = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1) / np.maximum(L, 1e-30) >= C["nm_min_edge_mm"] / 10
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 2] != F[:, 0]) & wide]
    if not len(F):
        return {"n": 0, "at": []}
    key, _ = _edge_keys(F)
    uk, cnt = np.unique(key, return_counts=True)
    n1 = int(F.max()) + 1
    bad = uk[cnt > 2]
    a, b = u[bad // n1], u[bad % n1]
    keep = np.linalg.norm(a - b, axis=1) >= C["nm_min_edge_mm"]
    at = [[round(float(v), 1) for v in m] for m in ((a[keep] + b[keep]) / 2)[:5]]
    return {"n": int(keep.sum()), "at": at}


def _findings(regions, faces=(), nm=None):
    out = []
    for g in regions:
        if g["status"] in ("fail", "warn"):
            what = {"island": "an island starts in mid-air (%.1f mm2)" % g["area_mm2"],
                    "cantilever": "a %.1f mm cantilever (%.1f mm2, extent %s)" % (g.get("overhang_mm", 0), g["area_mm2"], g["extent_mm"]),
                    "bridge": "a %.1f mm bridge" % g.get("span_mm", 0)}[g["kind"]]
            out.append({"status": g["status"], "kind": g["kind"], "z_mm": g["z_mm"], "msg": "%s at z %.1f (print %s%s)" % (
                what, g["z_mm"], g["at_print"], ", world %s" % g["at_world"] if "at_world" in g else "")})
    for g in faces:
        if g["status"] in ("fail", "warn"):
            d0, d1 = g["deg_from_vertical"]
            what = ("a %.1f mm sloped bridge" % g["span_mm"] if g["kind"] == "bridge" else
                    "a sloped overhang anchored nowhere" if g["kind"] == "floating" else
                    "a %.1f mm sloped overhang past %g deg" % (g["overhang_mm"], g["deg_limit"]))
            out.append({"status": g["status"], "kind": "overhang", "z_mm": g["z_mm"][0], "msg": "%s (%.0f mm2 projected, faces %.0f-%.0f deg "
                        "from vertical, z %.1f-%.1f) at z %.1f (print %s%s)" % (what, g["projected_mm2"], d0, d1, g["z_mm"][0], g["z_mm"][1], g["z_mm"][0],
                        g["at_print"], ", world %s" % g["at_world"] if "at_world" in g else "")})
    if nm and nm["n"]:
        out.append({"status": "warn", "kind": "nonmanifold", "z_mm": None, "msg": "%d edges shared by more than 2 faces as exported (float32 STL: "
                    "solids touching along a line; a slicer's mesh check counts them; overlap them by 0.1 mm or more) at print %s" % (
                    nm["n"], "; ".join(str(a) for a in nm["at"][:3]))})
    return out


def analyze_cached(tris, cfg=None, supports="no", print_to_world=None):
    """analyze() with a result cache under $TMPDIR keyed on the triangles and the config: cadcheck re-runs `parts` on
    every check, and most parts have not changed. World coordinates are added after the lookup."""
    import hashlib
    C = dict(DEFAULTS)
    C.update(cfg or {})
    T = np.ascontiguousarray(np.asarray(tris, np.float32))
    key = hashlib.sha1(T.tobytes() + json.dumps(C, sort_keys=True).encode() + str(supports).encode() + _VERSION.encode() + _SOURCE.encode()).hexdigest()
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
        for g in res["regions"] + res["faces"]:
            g["at_world"] = [round(float(v), 1) for v in np.asarray(Rw) @ (np.array(g["at_print"]) + [0, 0, z0]) + np.asarray(tw)]
        res["findings"] = _findings(res["regions"], res["faces"], {"n": res["stl_nonmanifold_edges"], "at": res["stl_nonmanifold_at"]})
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


def run(paths, manifest=None, cfg=None, only=None, render_dir=None, out=None, where=None, sec_opt=None):
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
        r = analyze(tris, cfg, supports=sup if sup is not None else "no", print_to_world=wm, keep_pixels=bool(render_dir or where))
        r.update(stl=name, file=fp, objects=info.get("objects", []), supports=sup)
        if render_dir and (r["findings"] or any(g["status"] == "support" for g in r["regions"])):
            r["render"] = render_flags(tris, r, os.path.join(render_dir, name + "_printcheck.png"))
        if render_dir:
            maps = [layer_map(g, os.path.join(render_dir, "%s_z%05.1f_%s.png" % (name, g["z_mm"], g["kind"])))
                    for g in r["regions"] if g["status"] != "ok"][:8]
            if maps:
                r["layer_maps"] = maps
        if where:
            r["where"] = where_lines(name, r) + [l for z in _section_zs(r, where) for l in section_lines(tris, z, r, cfg, **sec_opt)]
        for g in r["regions"] + r["faces"]:
            g.pop("_px", None)
            g.pop("_map", None)
            g.pop("_faces", None)
        mr = (cfg or {}).get("max_regions", DEFAULTS["max_regions"])
        r["regions"] = r["regions"][:mr]
        r["faces"] = [g for g in r["faces"] if g["projected_mm2"] >= (cfg or {}).get("face_min_mm2", DEFAULTS["face_min_mm2"])][:mr]
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
            "%s %s" % (f["status"].upper(), f["msg"]) for f in r["findings"][:4]) or "ok (max bridge %.1f mm, max ledge %.1f mm, "
            "max sloped overhang %.1f mm)" % (r["max_bridge_mm"], r["max_overhang_mm"], r["max_face_overhang_mm"])))
        for l in r.get("where", []):
            print("    " + l)


# ------------------------------------------------------------------ where: region list and layer sections as text

def where_lines(name, r):
    """One line per region worth reading: every layer-check region that is not ok, every face-pass region (sloped
    overhangs and the flat ones the layer check judges), worst first."""
    out = ["%s: supports %s, h %.1f mm, %d layers of %g mm, raster %g mm; %d edges in more than 2 faces" % (
        name, r["supports"], r["height_mm"], r["layers"], r["layer_h"], r["px_mm"], r["stl_nonmanifold_edges"])]
    loc = lambda g: "print %s%s" % (g["at_print"], ", world %s" % g["at_world"] if "at_world" in g else "")
    for g in r["regions"]:
        if g["status"] == "ok":
            continue
        m = {"island": "island %.1f mm2" % g["area_mm2"], "cantilever": "cantilever %.1f mm, %.1f mm2" % (g.get("overhang_mm", 0), g["area_mm2"]),
             "bridge": "bridge span %.1f mm, %.1f mm2" % (g.get("span_mm", 0), g["area_mm2"])}[g["kind"]]
        out.append("%-7s layer z %5.1f        %-36s extent %s  %s" % (g["status"].upper(), g["z_mm"], m, g["extent_mm"], loc(g)))
    for g in r["faces"]:
        if g["projected_mm2"] < DEFAULTS["face_min_mm2"]:
            continue
        m = ("sloped bridge span %.1f mm" % g["span_mm"] if g["kind"] == "bridge" else
             "anchored nowhere" if g["kind"] == "floating" else "%.1f mm past %g deg" % (g["overhang_mm"], g["deg_limit"]))
        out.append("%-7s faces z %5.1f-%-5.1f %-36s %.0f mm2 projected, %.0f-%.0f deg from vertical, anchored %.0f of %.0f mm edge  %s" % (
            g["status"].upper(), g["z_mm"][0], g["z_mm"][1], m, g["projected_mm2"], g["deg_from_vertical"][0], g["deg_from_vertical"][1],
            g["anchored_edge_mm"], g["edge_mm"], loc(g)))
    return out


def _section_zs(r, where):
    """--section Z[,Z...] or auto (where each flagged region starts, up to 4), as (z, window) pairs."""
    if where in ("list", None):
        return []
    if where != "auto":
        return [(float(z), None) for z in str(where).split(",")]
    out = []
    for g in [g for g in r["regions"] if g["status"] != "ok"] + [g for g in r["faces"] if g["status"] in ("fail", "warn", "support")]:
        z = g["z_mm"] if not isinstance(g["z_mm"], list) else g["z_mm"][0] + r["layer_h"]
        c, e = g["at_print"], g["extent_mm"]
        win = [c[0] - e[0] / 2 - 6, c[1] - e[1] / 2 - 6, c[0] + e[0] / 2 + 6, c[1] + e[1] / 2 + 6]
        if not any(abs(z - z0) < r["layer_h"] / 2 and w0 == win for z0, w0 in out):
            out.append((z, win))
    return out[:4]


def section_lines(tris, zw, res, cfg=None, cell=None, window=None):
    """The layer at print height z as text, top row = +y (layer_ascii / roof_ascii in the push-assist reviews):
         #  solid, carried by the layer below        :  solid in the layer below only        .  air
         B C I  this layer's unsupported pixels the layer check calls a bridge / cantilever / island (lower case: ok)
         V      faces of a flagged sloped overhang that this layer prints over (v: a sloped region judged ok)
    Each character is a cell of cell mm (default: the window fits 100 x 50); the worst mark in it wins. Under the map,
    the layer's regions with their spans. res is analyze(..., keep_pixels=True) on the same triangles."""
    z, win = zw if isinstance(zw, tuple) else (zw, None)
    win = window or win
    C = dict(DEFAULTS)
    C.update(cfg or {})
    h = C["layer_h"]
    T = np.asarray(tris, np.float64)
    T = T[np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1) > 1e-12]
    T = T - [0, 0, T[:, :, 2].min()]
    lo, hi = T.reshape(-1, 3).min(0), T.reshape(-1, 3).max(0)
    k = max(0, min(res["layers"] - 1, int(math.floor(z / h + 1e-6))))
    x0, y0, x1, y1 = win if win else (lo[0] - 1, lo[1] - 1, hi[0] + 1, hi[1] + 1)
    c = cell or max(res["px_mm"], (x1 - x0) / 100.0, (y1 - y0) / 50.0)
    c = max(res["px_mm"], math.ceil(c / res["px_mm"] - 1e-9) * res["px_mm"])
    q = max(1, int(round(c / res["px_mm"])))
    p = c / q
    W, H = int(math.ceil((x1 - x0) / c)) * q, int(math.ceil((y1 - y0) / c)) * q
    tz = T[:, :, 2]
    cur = _layer_mask(T, tz, min((k + 0.5) * h, hi[2] - 1e-4) + 1.37e-4, x0, y0, p, W, H)
    prev = _layer_mask(T, tz, (k - 0.5) * h + 1.37e-4, x0, y0, p, W, H) if k else np.zeros_like(cur)
    rank = np.zeros((H, W), np.int8)            # . : # v V b c i B C I
    rank[prev & ~cur] = 1
    rank[cur] = 2
    pix = lambda xs, ys: (np.clip(((ys - y0) / p).astype(int), 0, H - 1), np.clip(((xs - x0) / p).astype(int), 0, W - 1),
                          (xs >= x0) & (xs < x0 + W * p) & (ys >= y0) & (ys < y0 + H * p))
    notes = []
    for g in res["faces"]:
        if "_faces" not in g or g["z_mm"][1] < k * h or g["z_mm"][0] > (k + 1) * h or g["status"] == "layer":
            continue
        F = T[g["_faces"]]
        F = F[(F[:, :, 2].max(1) >= k * h) & (F[:, :, 2].min(1) <= (k + 1) * h)]
        if not len(F):
            continue
        m, _ = _fill_tris(F, x0, y0, p, W, H)
        flag = g["status"] in ("fail", "warn", "support")
        rank[m & cur] = np.maximum(rank[m & cur], 4 if flag else 3)
        notes.append("%s faces z %.1f-%.1f: %s, %.0f mm2 projected, %.0f-%.0f deg from vertical, %s" % (
            "V" if flag else "v", g["z_mm"][0], g["z_mm"][1], "sloped bridge span %.1f mm" % g["span_mm"] if g["kind"] == "bridge" else
            "anchored nowhere" if g["kind"] == "floating" else "%.1f mm past %g deg" % (g["overhang_mm"], g["deg_limit"]),
            g["projected_mm2"], g["deg_from_vertical"][0], g["deg_from_vertical"][1], g["status"]))
    for g in res["regions"]:
        if g.get("layer") != k or "_px" not in g:
            continue
        xs, ys, _, _ = g["_px"]
        r_, c_, ok = pix(xs, ys)
        flag = g["status"] != "ok"
        v = {"bridge": 5, "cantilever": 6, "island": 7}[g["kind"]] + (3 if flag else 0)
        rank[r_[ok], c_[ok]] = np.maximum(rank[r_[ok], c_[ok]], v)
        what = {"island": "island", "cantilever": "cantilever %.1f mm" % g.get("overhang_mm", 0),
                "bridge": "bridge span %.1f mm, anchored %d%%" % (g.get("span_mm", 0), round(100 * g.get("anchored_frac", 0)))}[g["kind"]]
        notes.append("%s %s, %.1f mm2, extent %s, %s, print %s%s" % ("BCI"[v - 8] if flag else "bci"[v - 5], what, g["area_mm2"], g["extent_mm"],
                     g["status"], g["at_print"], ", world %s" % g["at_world"] if "at_world" in g else ""))
    cellr = rank.reshape(H // q, q, W // q, q).max((1, 3))
    ch = np.array(list(".:#vVbciBCI"))
    out = ["section z %.1f (layer %d, %.2f-%.2f) x %.1f..%.1f y %.1f..%.1f, cell %.2f mm" % (k * h + h / 2, k, k * h, (k + 1) * h, x0, x0 + W * p, y0, y0 + H * p, c)]
    for j in range(cellr.shape[0] - 1, -1, -1):
        out.append("%7.1f %s" % (y0 + (j + 0.5) * c, "".join(ch[cellr[j]])))
    return out + (notes or ["(no unsupported pixels or sloped overhangs in this layer)"])


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
        if a == "--where":
            opt["where"] = "list"
            i += 1
        elif a.startswith("--"):
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
    where = opt.get("section") or opt.get("where")
    sec = {"cell": float(opt["cell"]) if "cell" in opt else None,
           "window": [float(v) for v in opt["window"].split(",")] if "window" in opt else None}
    rep = run(pos, opt.get("manifest"), cfg, opt.get("only"), opt.get("render"), out, where=where, sec_opt=sec)
    print_summary(rep, out)
    return 1 if rep["summary"]["fails"] else 0


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    sys.exit(_main(a))
