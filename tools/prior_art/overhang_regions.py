"""Overhang faces by angle and by connected region, on STLs (numpy; printcheck.read_stl): the follow-up's per-region judgement.

    python3 -I overhang_regions.py [--lo 1] [--hi 44.9] [--printcheck pc.json] [--top 3] a.stl [b.stl ...] > out.json

Angles as dfam-check measures them: the face's angle from horizontal, 90 - asin(-n.z), from float32 vertices in
float64; only downward faces (n.z < -1e-6) whose centroid is 0.1 mm or more above the part's lowest point count.

Per part:
- `bins_mm2`: face area by angle band [0, 1), [1, 10), [10, 44.99), [44.99, 45.01) (the nominal 45 deg chamfers),
  [45.01, 90). `at_45_counted_mm2` is the part of the 45 deg band that computes below 45.0 and so is counted by a
  `< 45` limit (float32 rounding decides which side each face lands on).
- `regions`: faces with lo <= angle < hi joined into connected regions (shared vertices on a 1 um grid), largest
  projected area first: area, projected area on the bed (area * -n.z), run along the region's mean downhill direction,
  width across it, area-weighted mean angle, z range above the part's lowest point, face count.

Default band 1..44.9 deg: the sloped faces only, without flat ceilings (printcheck's bridges) or the 45 deg chamfers.
"""
import argparse, json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "skills", "print-cad-blender", "scripts"))
from printcheck import read_stl as read  # noqa: E402  (ASCII or binary)

ap = argparse.ArgumentParser()
ap.add_argument("stl", nargs="+")
ap.add_argument("--lo", type=float, default=1.0)
ap.add_argument("--hi", type=float, default=44.9)
ap.add_argument("--printcheck", help="printcheck JSON: adds each part's verdict")
ap.add_argument("--top", type=int, default=3, help="regions listed per part")
args = ap.parse_args()

verdict = {}
if args.printcheck:
    for p in json.load(open(args.printcheck))["parts"]:
        st = [x.get("status") for x in p.get("findings") or []]
        verdict[p["stl"]] = "fail" if "fail" in st else ("warn" if st else "ok")


def find(par, i):
    while par[i] != i:
        par[i] = par[par[i]]
        i = par[i]
    return i


EDGES = (0, 1, 10, 44.99, 45.01, 90.01)
out = []
for path in args.stl:
    name = os.path.splitext(os.path.basename(path))[0]
    T = read(path)
    c = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    a = np.linalg.norm(c, axis=1) / 2
    N = c / np.maximum(2 * a, 1e-300)[:, None]
    ang = 90 - np.degrees(np.arcsin(np.clip(-N[:, 2], 0, 1)))
    zc, zmin = T[:, :, 2].mean(1), T[:, :, 2].min()
    off = (N[:, 2] < -1e-6) & (zc >= zmin + 0.1) & (a > 0)
    bins = {f"{lo}-{hi}": round(float(a[off & (ang >= lo) & (ang < hi)].sum()), 1) for lo, hi in zip(EDGES, EDGES[1:])}
    at45 = off & (ang >= 44.99) & (ang < 45.01)
    sel = np.where(off & (ang >= args.lo) & (ang < args.hi))[0]
    regs = []
    if len(sel):
        V = np.round(T[sel].reshape(-1, 3) / 1e-3).astype(np.int64)
        _, vid = np.unique(V, axis=0, return_inverse=True)
        vid = vid.reshape(-1, 3)
        par, owner = list(range(len(sel))), {}
        for f in range(len(sel)):
            for v in vid[f]:
                if v in owner:
                    ra, rb = find(par, f), find(par, owner[v])
                    if ra != rb:
                        par[ra] = rb
                else:
                    owner[v] = f
        roots = np.array([find(par, f) for f in range(len(sel))])
        for r in np.unique(roots):
            F = sel[roots == r]
            h = (a[F, None] * N[F, :2]).sum(0)
            h = h / max(np.linalg.norm(h), 1e-12)
            pts = T[F].reshape(-1, 3)
            regs.append({"area_mm2": round(float(a[F].sum()), 1), "projected_mm2": round(float((a[F] * -N[F, 2]).sum()), 1),
                         "run_mm": round(float(np.ptp(pts[:, :2] @ h)), 2),
                         "width_mm": round(float(np.ptp(pts[:, :2] @ np.array([-h[1], h[0]]))), 2),
                         "mean_angle_deg": round(float(np.average(ang[F], weights=a[F])), 1),
                         "z_mm": [round(float(pts[:, 2].min() - zmin), 1), round(float(pts[:, 2].max() - zmin), 1)],
                         "faces": int(len(F))})
        regs.sort(key=lambda r: -r["projected_mm2"])
    out.append({"part": name, "printcheck": verdict.get(name, "n/a"), "bins_mm2": bins,
                "at_45_counted_mm2": round(float(a[at45 & (ang < 45.0)].sum()), 1),
                "largest_region_projected_mm2": regs[0]["projected_mm2"] if regs else 0.0,
                "n_regions": len(regs), "regions": regs[:args.top]})

out.sort(key=lambda r: -r["largest_region_projected_mm2"])
print(json.dumps({"band_deg": [args.lo, args.hi], "n": len(out), "parts": out}, indent=1))
