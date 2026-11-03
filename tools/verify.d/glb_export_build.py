"""glb_export.sh's Blender half: write a GLB from a blend (optional) and dump what cadlib.joints says every PRT_/BUY_
world matrix is at each key of each joint clip, for glb_export_check.py to compare with the GLB's own node maths.

    cad py glb_export_build.py OUT.json GLB [--blend B] [--checks C] [--report R] [--no-draco] [--write]

--write runs export.write_glb(GLB) first (on --blend, or the scene as loaded); without it GLB must exist. The expected
matrices come from the blend and the driver values stored in each clip's extras, never from the GLB's keyframes.
"""
import bpy, json, os, sys, time
from cadlib import export as E, joints as JT

a = sys.argv[1:]


def opt(k, default=None):
    return a[a.index(k) + 1] if k in a else default


out, glb = a[0], a[1]
if opt("--blend"):
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(opt("--blend")))
cfg = json.load(open(opt("--checks"))) if opt("--checks") else {}
info = {}
if "--write" in a:
    t = time.time()
    info = E.write_glb(glb, checks=cfg, report=opt("--report"), draco="--no-draco" not in a)
    info["seconds"] = round(time.time() - t, 2)
O = bpy.data.objects
J, CP = JT.read(O, cfg)
js, _ = E.read_glb(glb)
solids = sorted(o.name for o in O if o.type == 'MESH' and o.name.startswith(("PRT_", "BUY_")) and o.name in bpy.context.view_layer.objects)
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
roles = ("PRT_", "BUY_", "FST_", "CAB_", "PIV_")
named = [o for o in O if o.name.startswith(roles) and o.name in bpy.context.view_layer.objects and (o.type == 'MESH' or JT.is_joint(o))]
json.dump({"info": info, "expect": expect, "solids": solids,
           "objects": {o.name: o.parent.name if o.parent else None for o in named},
           "joints": {n: {"lo": s["lo"], "hi": s["hi"], "home": s.get("home") or 0.0, "continuous": bool(s.get("continuous")),
                          "coupled_to": (CP.get(n) or {}).get("to"), "ratio": (CP.get(n) or {}).get("ratio")} for n, s in J.items()},
           "assembly_steps": len(cfg.get("assembly_order") or [])}, open(out, "w"))
print("GLBEXPECT %s: %d clips, %d solids" % (out, len(expect), len(solids)))
