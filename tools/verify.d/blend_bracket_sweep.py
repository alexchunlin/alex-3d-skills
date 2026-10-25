"""Containment check for geom.swept_envelope, run by blend_bracket.sh (not sourced: verify_all sources *.sh only).

    Blender -b [model.blend] --python blend_bracket_sweep.py -- <skill scripts dir> [OBJ,OBJ JOINT LO HI | union]

Without a blend it sweeps a synthetic L-shaped arm with sharp corners 30-70 mm off the axis ("union": the Manifold
union of poses 5 deg apart instead, a negative control the check must fail). With one, it sweeps the named objects
about the joint. Every vertex and edge midpoint of 25 seeded random poses must be inside the envelope
(3-ray parity vote). Prints SWEEPCHK {...}.
"""
import bpy, json, math, random, sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, argv[0])
from cadlib import geom as G  # noqa: E402

if len(argv) > 2:
    obs = [bpy.data.objects[n] for n in argv[1].split(",")]
    J = bpy.data.objects[argv[2]]
    LO, HI = float(argv[3]), float(argv[4])
    k = "XYZ".index(J.get("joint_axis", "X"))
    C, W = J.matrix_world.translation.copy(), Vector(J.matrix_world.col[k][:3]).normalized()
    env = G.swept_envelope(obs, J, lo=LO, hi=HI)
else:
    from cadlib import asm as A
    A.new_scene()
    arm = G.box("arm", 30, 70, -4, 4, 0, 6)
    fin = G.box("fin", 62, 70, -4, 4, -20, 0.01)
    obs = [G.csg(arm, add=[fin])]
    C, W, LO, HI = Vector((0, 0, 0)), Vector((0, 0, 1)), -30.0, 60.0
    union = len(argv) > 1 and argv[1] == "union"
    env = G.swept_envelope(obs, C, W, LO, HI, **(dict(method="union", step=5.0) if union else {}))
V, T = G._world_tris(obs)
pts = V + [(V[t[0]] + V[t[1]]) / 2 for t in T] + [(V[t[1]] + V[t[2]]) / 2 for t in T]
me = env.data
tree = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
dirs = [Vector(d).normalized() for d in ((0.31, 0.52, 0.79), (-0.6, 0.27, -0.75), (0.9, -0.4, 0.17))]


def inside(p):
    votes = 0
    for d in dirs:
        n, q = 0, p.copy()
        for _ in range(400):
            h = tree.ray_cast(q, d, 5000.0)
            if h[0] is None:
                break
            n += 1
            q = h[0] + d * 1e-4
        votes += n % 2
    return votes >= 2


rnd = random.Random(11)
n_out, worst, n = 0, 0.0, 0
for _ in range(25):
    a = rnd.uniform(LO, HI)
    M = Matrix.Translation(C) @ Matrix.Rotation(math.radians(a), 4, W) @ Matrix.Translation(-C)
    for p in pts:
        q = M @ p
        n += 1
        d = tree.find_nearest(q)[3]
        if d is not None and d < 0.01:
            continue
        if not inside(q):
            n_out += 1
            worst = max(worst, d or 0.0)
info = env["envelope"].to_dict()
print("SWEEPCHK", json.dumps({"points": n, "outside": n_out, "worst_mm": round(worst, 3), "pad": info["pad"], "poses": info["poses"],
                              "non_manifold_edges": info["non_manifold_edges"], "tris": info["tris"], "t_s": info["t_s"]}))
