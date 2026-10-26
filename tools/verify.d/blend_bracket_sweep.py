"""Containment check for geom.swept_envelope, run by blend_bracket.sh (not sourced: verify_all sources *.sh only).

    Blender -b [model.blend] --python blend_bracket_sweep.py -- <skill scripts dir> [MODE ...]

MODE:
  (none)            synthetic L-shaped arm with sharp corners 30-70 mm off the axis, default tol and voxel
  union             the Manifold union of poses 5 deg apart instead: a negative control the check must fail
  dense VOXEL TOL   the L arm at that voxel and tol, checked at every mid-angle between the envelope's own poses (where
                    a pose is farthest from the samples). voxel 1 / tol 0.05 left points 0.65 mm outside with the old
                    voxel / 4 pad (PR #4 review)
  slide             a 20 x 10 x 4 block on a prismatic joint (asm.joint(prismatic=True)), 0..50 mm along X
  wheel             a spoke on a continuous joint about Z: no lo/hi, swept 0..360
  OBJ,OBJ JOINT LO HI   named objects of the loaded blend about the joint

Every vertex, 7 points along every edge and every triangle centroid of the moving parts, at 25 seeded random poses
plus the mid-poses, must be inside the envelope: nearest-face sign test, confirmed by a 3-ray parity vote.
Prints SWEEPCHK {...}.
"""
import bpy, json, math, random, sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, argv[0])
from cadlib import geom as G, asm as A  # noqa: E402

mode = argv[1] if len(argv) > 1 else ""
SLIDE = False
extra = {}
if len(argv) > 4:
    obs = [bpy.data.objects[n] for n in argv[1].split(",")]
    J = bpy.data.objects[argv[2]]
    LO, HI = float(argv[3]), float(argv[4])
    k = "XYZ".index(J.get("joint_axis", "X"))
    C, W = J.matrix_world.translation.copy(), Vector(J.matrix_world.col[k][:3]).normalized()
    env = G.swept_envelope(obs, J, lo=LO, hi=HI)
elif mode == "slide":
    A.new_scene()
    J = A.joint("PIV_slide", (0, 0, 0), 'X', lo=0, hi=50, prismatic=True)
    obs = [G.box("gate", -10, 10, -5, 5, 0, 4)]
    C, W, LO, HI, SLIDE = Vector((0, 0, 0)), Vector((1, 0, 0)), 0.0, 50.0, True
    env = G.swept_envelope(obs, J)
    bb = [env.matrix_world @ Vector(c) for c in env.bound_box]
    extra["env_x"] = [round(min(v.x for v in bb), 2), round(max(v.x for v in bb), 2)]   # must cover -10..60, not rotate
elif mode == "wheel":
    A.new_scene()
    J = A.joint("PIV_wheel", (0, 0, 0), 'Z', continuous=True)
    obs = [G.box("spoke", 5, 30, -2, 2, 0, 4)]
    C, W, LO, HI = Vector((0, 0, 0)), Vector((0, 0, 1)), 0.0, 360.0
    env = G.swept_envelope(obs, J)
else:
    A.new_scene()
    arm = G.box("arm", 30, 70, -4, 4, 0, 6)
    fin = G.box("fin", 62, 70, -4, 4, -20, 0.01)
    obs = [G.csg(arm, add=[fin])]
    C, W, LO, HI = Vector((0, 0, 0)), Vector((0, 0, 1)), -30.0, 60.0
    if mode == "union":
        extra = dict(method="union", step=5.0)
    elif mode == "dense":
        extra = dict(voxel=float(argv[2]), tol=float(argv[3]))
    env = G.swept_envelope(obs, C, W, LO, HI, **extra)
    extra = {}
info = env["envelope"].to_dict()

V, T = G._world_tris(obs)
pts = list(V)
for t in T:
    for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
        pts += [V[a].lerp(V[b], i / 8) for i in range(1, 8)]
    pts.append((V[t[0]] + V[t[1]] + V[t[2]]) / 3)
me = env.data
tree = BVHTree.FromPolygons([env.matrix_world @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
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
vals = [rnd.uniform(LO, HI) for _ in range(25)]
if mode == "dense":
    st = (HI - LO) / (info["poses"] - 1)
    vals += [LO + st * (i + 0.5) for i in range(info["poses"] - 1)]
n_out, worst, n = 0, 0.0, 0
for a in vals:
    M = Matrix.Translation(W * a) if SLIDE else Matrix.Translation(C) @ Matrix.Rotation(math.radians(a), 4, W) @ Matrix.Translation(-C)
    for p in pts:
        q = M @ p
        n += 1
        loc, nrm, _, d = tree.find_nearest(q)
        if loc is None or d < 1e-3 or (q - loc).dot(nrm) <= 0:
            continue
        if not inside(q):
            n_out += 1
            worst = max(worst, d)
out = {"mode": mode or "L arm", "points": n, "outside": n_out, "worst_mm": round(worst, 3), "pad": info["pad"], "poses": info["poses"],
       "kind": info.get("kind"), "voxel": info.get("voxel"), "non_manifold_edges": info["non_manifold_edges"], "tris": info["tris"],
       "t_s": info["t_s"]}
out.update(extra)
print("SWEEPCHK", json.dumps(out))
