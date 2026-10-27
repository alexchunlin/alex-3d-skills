"""Measure a mates_task design against interfaces.json (Blender; score.py runs it).

    Blender -b model.blend --factory-startup --python measure_blend.py -- <skill>/scripts <kit> out.json

Each purchased part is found by its mesh: kit_parts.py rebuilds it in its local frame, and a rigid fit (Kabsch,
vertex for vertex) gives its world placement at home. Screws are read from their fst_head / fst_dir. Nothing here
reads connectors or mates, so the absolute and mates variants are measured the same way.
"""
import json, math, os, sys
import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SCRIPTS, KIT, OUT = argv[0], argv[1], argv[2]
sys.path[:0] = [SCRIPTS, KIT]
from cadlib import joints as JT  # noqa: E402
import kit_parts as K  # noqa: E402

I = json.load(open(os.path.join(KIT, "interfaces.json")))
TOL_MM, TOL_DEG = I["tol_mm"], I["tol_deg"]
J, CP = JT.read()
JT.apply(J, CP, {})                       # every joint at home
rows = []


def row(name, kind, ok, err_mm=None, err_deg=None, why="", **detail):
    rows.append(dict(name=name, kind=kind, ok=bool(ok), err_mm=None if err_mm is None else round(err_mm, 3),
                     err_deg=None if err_deg is None else round(err_deg, 3), why=why, **detail))


def ang(a, b, signless=False):
    c = max(-1.0, min(1.0, Vector(a).normalized().dot(Vector(b).normalized())))
    d = math.degrees(math.acos(c))
    return min(d, 180 - d) if signless else d


def kabsch(P, Q):
    """R, t with Q ~ R P + t (lists of Vector, same order)."""
    import numpy as np
    A = np.array([list(p) for p in P])
    B = np.array([list(q) for q in Q])
    ca, cb = A.mean(0), B.mean(0)
    H = (A - ca).T @ (B - cb)
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1, 1, d])
    R = Vt.T @ D @ U.T
    t = cb - R @ ca
    res = float(np.sqrt((((A @ R.T + t) - B) ** 2).sum(1).mean()))
    M = Matrix.Identity(4)
    for i in range(3):
        for j in range(3):
            M[i][j] = float(R[i][j])
        M[i][3] = float(t[i])
    return M, res


PLACED = {}


def locate(name):
    if name in PLACED:
        return PLACED[name]
    ob = bpy.data.objects.get(name)
    if ob is None or ob.type != 'MESH':
        PLACED[name] = (None, "no mesh object %s" % name)
        return PLACED[name]
    ref = K.BUILDERS[name]("_ref_" + name)
    lv = [v.co.copy() for v in ref.data.vertices]
    wv = [ob.matrix_world @ v.co for v in ob.data.vertices]
    if len(lv) != len(wv):
        PLACED[name] = (None, "%s has %d vertices, the kit placeholder %d: it was modified (cut or joined)" % (name, len(wv), len(lv)))
        return PLACED[name]
    M, res = kabsch(lv, wv)
    if res > 0.01:
        PLACED[name] = (None, "%s does not fit the kit placeholder rigidly (rms %.3f mm): modified" % (name, res))
        return PLACED[name]
    PLACED[name] = (M, None)
    return PLACED[name]


for name, f in I["frames"].items():
    M, err = locate(name)
    if M is None:
        row(name, "frame", False, why=f["why"], error=err)
        continue
    o, x, z = M.translation, M.to_3x3() @ Vector((1, 0, 0)), M.to_3x3() @ Vector((0, 0, 1))
    e_mm = (o - Vector(f["origin"])).length
    e_deg = max(ang(x, f["x"]), ang(z, f["z"]))
    row(name, "frame", e_mm <= TOL_MM and e_deg <= TOL_DEG, e_mm, e_deg, f["why"], at=[round(c, 3) for c in o])

for name, f in I["axial"].items():
    M, err = locate(name)
    P, perr = locate(f["of"])
    if M is None or P is None:
        row(name, "axial", False, why=f["why"], error=err or perr)
        continue
    want_o = P @ Vector(f["origin"])
    want_z = P.to_3x3() @ Vector(f["z"])
    o, z = M.translation, M.to_3x3() @ Vector((0, 0, 1))
    e_mm, e_deg = (o - want_o).length, ang(z, want_z)
    row(name, "axial", e_mm <= TOL_MM and e_deg <= TOL_DEG, e_mm, e_deg, f["why"], at=[round(c, 3) for c in o])

jf = I["joint"]
e = bpy.data.objects.get(jf["name"])
if e is None or jf["name"] not in J:
    row(jf["name"], "joint", False, why=jf["why"], error="no joint %s" % jf["name"])
else:
    s = J[jf["name"]]
    ax = e.matrix_world.to_3x3() @ Vector([1.0 if i == "XYZ".index(s["axis"]) else 0.0 for i in range(3)])
    o = e.matrix_world.translation
    want = Vector((0, 0, 1)) if jf["axis"] == "Z" else Vector([1.0 if i == "XYZ".index(jf["axis"]) else 0.0 for i in range(3)])
    e_deg = ang(ax, want, signless=True)
    p = Vector((jf["through"][0], jf["through"][1], o.z))
    e_mm = (o - p).length
    lo, hi = s.get("lo"), s.get("hi")
    rng = s.get("continuous") or (lo is not None and lo <= jf["range"][0] + 1e-6 and hi >= jf["range"][1] - 1e-6)

    def under(n):
        ob = bpy.data.objects.get(n)
        while ob is not None:
            if ob.name == jf["name"]:
                return True
            ob = ob.parent
        return False
    carried = {n: under(n) for n in jf["carries"]}
    row(jf["name"], "joint", e_mm <= TOL_MM and e_deg <= TOL_DEG and rng and all(carried.values()), e_mm, e_deg, jf["why"],
        range=[lo, hi], carries=carried)

def _tree(ob):
    from mathutils.bvhtree import BVHTree
    W = ob.matrix_world
    return BVHTree.FromPolygons([W @ v.co for v in ob.data.vertices], [tuple(p.vertices) for p in ob.data.polygons])


def _inside(tree, p):
    loc, nrm, idx, dist = tree.find_nearest(p)
    return loc is not None and (p - loc).dot(nrm) < 0


def _ring_inside(tree, head, d, L, sd):
    u = d.orthogonal().normalized()
    v = d.cross(u)
    r = sd / 2 + 0.6
    k = 0.3
    while k < L:
        for a in range(8):
            q = head + d * k + (u * math.cos(a * math.pi / 4) + v * math.sin(a * math.pi / 4)) * r
            if _inside(tree, q):
                return True
        k += 0.5
    return False


FST = []
for ob in bpy.data.objects:
    if ob.name.startswith("FST_") and "fst_head" in ob.keys() and ob.get("fst_kind", "screw") == "screw":
        W = ob.matrix_world
        h = W @ Vector(ob["fst_head"])
        d = (W.to_3x3() @ Vector(ob["fst_dir"])).normalized()
        FST.append(dict(name=ob.name, head=h, dir=d, d=float(ob.get("fst_d", 0)), host=str(ob.get("host", "")), ob=ob))
SIZE_D = {"M2": 2.0, "M2.5": 2.5, "M3": 3.0, "M4": 4.0}
used = set()
for key, f in I["screws"].items():
    if "part" in f:
        M, err = locate(f["part"])
        if M is None:
            row("screws:" + key, "screws", False, why=f["why"], error=err)
            continue
        worst_mm, worst_deg, miss = 0.0, 0.0, []
        for hx, hy in f["holes"]:
            p = M @ Vector((hx, hy, 0))
            a = M.to_3x3() @ Vector(f["axis"])
            best = None
            for s in FST:
                if s["name"] in used or abs(s["d"] - SIZE_D[f["size"]]) > 1e-6:
                    continue
                v = p - s["head"]
                lat = (v - s["dir"] * v.dot(s["dir"])).length
                da = ang(s["dir"], a, signless=True)
                if best is None or lat < best[0]:
                    best = (lat, da, s)
            if best is None:
                miss.append([hx, hy])
                continue
            used.add(best[2]["name"])
            worst_mm, worst_deg = max(worst_mm, best[0]), max(worst_deg, best[1])
            if f.get("joint"):
                ob, on = best[2]["ob"], False
                while ob is not None:
                    on = on or ob.name == f["joint"]
                    ob = ob.parent
                if not on:
                    miss.append("%s not on %s" % (best[2]["name"], f["joint"]))
        row("screws:" + key, "screws", not miss and worst_mm <= TOL_MM and worst_deg <= TOL_DEG, worst_mm, worst_deg,
            f["why"], missing=miss)
    else:
        # screws that join the listed parts, whichever way they go in: each part has material on a ring just outside
        # the shank somewhere along it (the shank's own hole is cut, so the axis itself is in air)
        obs = [bpy.data.objects.get(n) for n in f["joins"]]
        if None in obs:
            row("screws:" + key, "screws", False, why=f["why"], error="missing %s" % [n for n, o in zip(f["joins"], obs) if o is None])
            continue
        trees = [_tree(o) for o in obs]
        n = []
        for s in FST:
            if s["name"] in used or abs(s["d"] - SIZE_D[f["size"]]) > 1e-6:
                continue
            L = float(s["ob"].get("fst_len", 0))
            if all(_ring_inside(t, s["head"], s["dir"], L, s["d"]) for t in trees):
                n.append(s["name"])
        used.update(n)
        row("screws:" + key, "screws", len(n) == f["count"], why=f["why"], count=len(n), names=n)

json.dump({"rows": rows, "tol_mm": TOL_MM, "tol_deg": TOL_DEG}, open(OUT, "w"), indent=1)
print("MEASURED %d interfaces, %d off" % (len(rows), sum(not r["ok"] for r in rows)))
