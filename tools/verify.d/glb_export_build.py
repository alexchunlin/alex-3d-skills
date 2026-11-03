"""glb_export.sh's Blender half: write a GLB from a blend (optional) and dump what cadlib.joints says every PRT_/BUY_
world matrix is at each key of each joint clip, for glb_export_check.py to compare with the GLB's own node maths.

    cad py glb_export_build.py OUT.json GLB [--blend B] [--checks C] [--report R] [--no-draco] [--write] [--flip PIV_x]

--write runs gltf.write_glb(GLB) first (on --blend, or the scene as loaded); without it GLB must exist. The expected
matrices come from the blend and the driver values stored in each clip's extras, never from the GLB's keyframes.
--flip PIV_x is the negative control: joints.values is patched during the write only, so that joint's value is
mirrored about home in the clips (a sign error in the export), then restored before the expected matrices are taken.
"""
import bpy, json, os, sys, time
from cadlib import gltf as G, joints as JT

a = sys.argv[1:]


def opt(k, default=None):
    return a[a.index(k) + 1] if k in a else default


out, glb = a[0], a[1]
if opt("--blend"):
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(opt("--blend")))
cfg = json.load(open(opt("--checks"))) if opt("--checks") else {}
info = {}
if "--write" in a:
    values, flip = JT.values, opt("--flip")
    if flip:
        def flipped(J, CP, pose):
            v = values(J, CP, pose)
            v[flip] = 2 * (J[flip].get("home") or 0.0) - v[flip]
            return v
        JT.values = flipped
    try:
        t = time.time()
        info = G.write_glb(glb, checks=cfg, report=opt("--report"), draco="--no-draco" not in a)
        info["seconds"] = round(time.time() - t, 2)
    finally:
        JT.values = values
O = bpy.data.objects
vl = bpy.context.view_layer
J, CP = JT.read(O, cfg)
js, _ = G.read_glb(glb)
solids = sorted(o.name for o in O if o.type == 'MESH' and o.name.startswith(G.ROLES[:2]) and o.name in vl.objects)
expect = {}
for an in js.get("animations", []):
    ex = an.get("extras") or {}
    d = ex.get("joint")
    if not d:
        continue
    rows = []
    for v in ex["values"]:
        vals = JT.values(J, CP, {d: v})
        cache = {}
        rows.append({n: [JT.world_at(n, J, vals, cache)[i][j] for i in range(4) for j in range(4)] for n in solids})
    expect[an["name"]] = rows
named = [o for o in O if o.name in vl.objects and ((o.type == 'MESH' and o.name.startswith(G.ROLES)) or JT.is_joint(o))]
json.dump({"info": info, "expect": expect, "solids": solids,
           "objects": {o.name: o.parent.name if o.parent else None for o in named},
           "joints": {n: {"lo": s["lo"], "hi": s["hi"], "home": s.get("home") or 0.0, "continuous": bool(s.get("continuous")),
                          "coupled_to": (CP.get(n) or {}).get("to"), "ratio": (CP.get(n) or {}).get("ratio")} for n, s in J.items()},
           "assembly_order": [st.get("objects", []) for st in cfg.get("assembly_order") or []]}, open(out, "w"))
print("GLBEXPECT %s: %d clips, %d solids" % (out, len(expect), len(solids)))
