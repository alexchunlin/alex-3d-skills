"""Swept envelope of a moving part: geom.swept_envelope ("sdf") against the Manifold union of poses ("union").

    nice -n 10 Blender -b <copy of mm_launcher_a3.blend> --python tools/prior_art/sweep_compare.py -- \
        --out /tmp/alex3d-bb-sweep [--parts PRT_nacelle] [--lo -3 --hi 46] [--quick]

For each method: time, triangles, closed or not, and two accuracy numbers:
  outside_mm  the furthest any vertex or edge midpoint of an in-between pose sits outside the envelope
              (25 seeded random test angles, so no method is tested at its own poses)
  oversize_mm how far envelope vertices sit from the true swept solid (2000 vertices, 0.25 deg sweep), max and mean
Writes sweep_compare.json. Results: docs/features/blend-bracket.md.
"""
import bpy, json, math, os, random, sys, time
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
OUT = arg("--out", "/tmp/alex3d-bb-sweep")
PARTS = arg("--parts", "PRT_nacelle").split(",")
JOINT = arg("--joint", "PIV_tilt")
LO, HI = float(arg("--lo", -3)), float(arg("--hi", 46))
QUICK = "--quick" in argv
os.makedirs(OUT, exist_ok=True)

J = bpy.data.objects[JOINT]
k = "XYZ".index(J.get("joint_axis", "X"))
C = J.matrix_world.translation.copy()
W = Vector(J.matrix_world.col[k][:3]).normalized()
obs = [bpy.data.objects[p] for p in PARTS]
V, T = G._world_tris(obs)
EV = [(V[a] + V[b]) / 2 for t in T for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))]
PTS = V + EV[::3]
home_tree = BVHTree.FromPolygons(V, T)


def rot(a):
    return Matrix.Translation(C) @ Matrix.Rotation(math.radians(a), 4, W) @ Matrix.Translation(-C)


def inside(tree, p):
    votes = 0
    for d in (Vector((0.31, 0.52, 0.79)).normalized(), Vector((-0.6, 0.27, -0.75)).normalized(), Vector((0.9, -0.4, 0.17)).normalized()):
        n, q = 0, p.copy()
        for _ in range(400):
            h = tree.ray_cast(q, d, 5000.0)
            if h[0] is None:
                break
            n += 1
            q = h[0] + d * 1e-4
        votes += n % 2
    return votes >= 2


def accuracy(ob):
    me = ob.data
    tree = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    rnd = random.Random(7)
    angs = [rnd.uniform(LO, HI) for _ in range(25)]
    if QUICK:
        angs = angs[::4]
    worst, n_out = 0.0, 0
    for a in angs:
        M = rot(a)
        for p in PTS[::2] if QUICK else PTS:
            q = M @ p
            loc, nrm, idx, dist = tree.find_nearest(q)
            if dist is None or dist < 0.01:
                continue
            if (q - loc).dot(nrm) > 0 and inside(tree, q) is False:
                n_out += 1
                worst = max(worst, dist)
    # oversize: envelope vertex -> nearest point of any pose (0.25 deg)
    rv = random.Random(3)
    vs = [v.co.copy() for v in me.vertices]
    vs = rv.sample(vs, min(len(vs), 600 if QUICK else 2000))
    dense = [LO + 0.25 * i for i in range(int((HI - LO) / 0.25) + 1)]
    inv = [rot(a).inverted() for a in dense]
    over = []
    for v in vs:
        best = 1e9
        for Mi in inv:
            d = home_tree.find_nearest(Mi @ v)[3]
            if d is not None and d < best:
                best = d
        over.append(best)
    return {"outside_mm": round(worst, 3), "outside_points": n_out, "test_angles": len(angs),
            "oversize_max_mm": round(max(over), 3), "oversize_mean_mm": round(sum(over) / len(over), 3)}


rows = []
configs = [("sdf", dict(tol=0.25, voxel=0.5)), ("sdf", dict(tol=0.25, voxel=0.5, adaptivity=0.1)), ("sdf", dict(tol=0.5, voxel=1.0)),
           ("union", dict(step=5.0)), ("union", dict(step=2.0)), ("union", dict(step=1.0))]
for method, kw in configs:
    t0 = time.time()
    try:
        ob = G.swept_envelope(obs, J, lo=LO, hi=HI, method=method, name="KEEP_%s" % method, **kw)
    except Exception as e:  # noqa: BLE001  (record the failure as a result row)
        rows.append({"method": method, **kw, "error": str(e)[:200], "t_s": round(time.time() - t0, 2)})
        print("SWEEP", rows[-1], flush=True)
        continue
    info = dict(ob["envelope"].to_dict())
    info.update(method=method, **kw)
    info.update(accuracy(ob))
    rows.append(info)
    print("SWEEP", json.dumps(info), flush=True)
    G.kill(ob)
res = {"parts": PARTS, "verts": len(V), "tris": len(T), "joint": JOINT, "lo": LO, "hi": HI, "rows": rows}
with open(os.path.join(OUT, "sweep_compare.json"), "w") as f:
    json.dump(res, f, indent=1)
print("WROTE", os.path.join(OUT, "sweep_compare.json"))
