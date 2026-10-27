"""Exact mesh-to-mesh distance at a joint angle, against the vertex-sampled distance cadcheck's `min_dist` measures.

    python3 -I tri_dist.py <parts_dir> <fixed> <moving> <PIV_name> <deg> [--reach 1.0]

<parts_dir> is mech_export.py's output (STLs in world home coordinates plus scene.json). <moving> turns by <deg> about
the pivot's local X through its origin. Prints:
- `exact`: the true minimum distance between the two triangle meshes near each other (vertex-triangle both ways and
  edge-edge for every triangle pair whose boxes come within `reach`), as mech's OCC distance measures it.
- `sampled`: cadcheck's `min_dist` (cadcheck.py, `sample_pts` + BVH `find_nearest`): each part's vertices and
  triangle centres, capped at 4000 by stride, measured to the other part's surface. The closest points of two meshes
  are often on two edges, which a vertex sample misses, so this reads high. The cap's stride picks other points than
  Blender's vertex order would, so `sampled_uncapped` (every vertex and centre) is the bound it can reach at best.

A1-F5 at tilt 45 (feeder_plate / launcher_cover, hopper / launcher_body): exact 0.2736 / 0.2121 mm, mech 0.274 /
0.212, cadcheck 0.373 / 0.212.
"""
import argparse, json, math, os, struct
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("parts_dir")
ap.add_argument("fixed")
ap.add_argument("moving")
ap.add_argument("pivot")
ap.add_argument("deg", type=float)
ap.add_argument("--reach", type=float, default=1.0)
args = ap.parse_args()


def read(path):
    d = open(path, "rb").read()
    n = struct.unpack("<I", d[80:84])[0]
    r = np.frombuffer(d, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=n, offset=84)
    return r["v"].astype(np.float64)


def rot(T, origin, axis, deg):
    a = np.asarray(axis, float)
    a /= np.linalg.norm(a)
    t = math.radians(deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    R = np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K
    return (T - origin) @ R.T + origin


def pt_seg(p, X, Y):
    d = Y - X
    t = np.clip(((p - X) * d).sum(1) / np.maximum((d * d).sum(1), 1e-300), 0, 1)
    return np.linalg.norm(p - (X + d * t[:, None]), axis=1)


def pt_tri(p, A, B, C):
    """Distance from points p to triangles ABC, row by row: the face when p projects inside, else the nearest edge."""
    n = np.cross(B - A, C - A)
    nn = np.linalg.norm(n, axis=1)
    n = n / np.maximum(nn, 1e-300)[:, None]
    q = p - ((p - A) * n).sum(1)[:, None] * n
    inside = np.ones(len(p), bool)
    for X, Y in ((A, B), (B, C), (C, A)):
        inside &= (np.cross(Y - X, q - X) * n).sum(1) >= 0
    d = np.where(inside & (nn > 0), np.abs(((p - A) * n).sum(1)), np.inf)
    for X, Y in ((A, B), (B, C), (C, A)):
        d = np.minimum(d, pt_seg(p, X, Y))
    return d


def seg_seg(P1, Q1, P2, Q2):
    d1, d2, r = Q1 - P1, Q2 - P2, P1 - P2
    a, e, f = (d1 * d1).sum(1), (d2 * d2).sum(1), (d2 * r).sum(1)
    c, b = (d1 * r).sum(1), (d1 * d2).sum(1)
    den = a * e - b * b
    s = np.where(den > 1e-12, np.clip((b * f - c * e) / np.where(den > 1e-12, den, 1), 0, 1), 0)
    t = (b * s + f) / np.maximum(e, 1e-300)
    s = np.where(t < 0, np.clip(-c / np.maximum(a, 1e-300), 0, 1),
                 np.where(t > 1, np.clip((b - c) / np.maximum(a, 1e-300), 0, 1), s))
    t = np.clip((b * s + f) / np.maximum(e, 1e-300), 0, 1)
    return np.linalg.norm((P1 + d1 * s[:, None]) - (P2 + d2 * t[:, None]), axis=1)


scene = json.load(open(os.path.join(args.parts_dir, "scene.json")))
piv = scene["pivots"][args.pivot]
A = read(os.path.join(args.parts_dir, args.fixed + ".stl"))
B = rot(read(os.path.join(args.parts_dir, args.moving + ".stl")), np.array(piv["origin"]), piv["x"], args.deg)
reach = args.reach
la, ha, lb, hb = A.min(1), A.max(1), B.min(1), B.max(1)
gl = np.maximum(la.min(0), lb.min(0)) - reach
gh = np.minimum(ha.max(0), hb.max(0)) + reach
ia = np.where(((ha >= gl) & (la <= gh)).all(1))[0]
ib = np.where(((hb >= gl) & (lb <= gh)).all(1))[0]

exact = np.inf
for i in ia:
    m = ib[((hb[ib] >= la[i] - reach) & (lb[ib] <= ha[i] + reach)).all(1)]
    if not len(m):
        continue
    TB, ta = B[m], A[i]
    rep = lambda x: np.repeat(x[None], len(m), 0)
    for k in range(3):
        exact = min(exact, pt_tri(rep(ta[k]), TB[:, 0], TB[:, 1], TB[:, 2]).min())
        exact = min(exact, pt_tri(TB[:, k], rep(ta[0]), rep(ta[1]), rep(ta[2])).min())
        for l in range(3):
            exact = min(exact, seg_seg(rep(ta[k]), rep(ta[(k + 1) % 3]), TB[:, l], TB[:, (l + 1) % 3]).min())


def samples(T, cap):
    pts = np.concatenate([np.unique(T.reshape(-1, 3), axis=0), T.mean(1)])
    if cap and len(pts) > cap:
        st = len(pts) / cap
        pts = pts[(np.arange(cap) * st).astype(int)]
    return pts


def sampled(cap):
    best = np.inf
    for P, T, lo, hi in ((samples(A, cap), B, lb, hb), (samples(B, cap), A, la, ha)):
        P = P[((P >= gl) & (P <= gh)).all(1)]
        for p in P:
            m = ((hi >= p - reach) & (lo <= p + reach)).all(1)
            if m.any():
                best = min(best, pt_tri(np.repeat(p[None], m.sum(), 0), T[m, 0], T[m, 1], T[m, 2]).min())
    return best


print(json.dumps({"fixed": args.fixed, "moving": args.moving, "pivot": args.pivot, "deg": args.deg,
                  "exact_mm": round(float(exact), 4), "sampled_mm": round(float(sampled(4000)), 4),
                  "sampled_uncapped_mm": round(float(sampled(None)), 4)}))
