"""6-way tube node: three 20 mm tubes on X, Y and Z, held by one blended printed connector (cadlib.blend).

    cad build examples/blend-node/build.py -- [--out /tmp/alex3d-bb-node] [--render] [--organic]

--organic: the look of the user's reference, one smooth body with large concave faces between short grips
(fillet 15 and sleeves to 36 mm, against 6 and 40: 21.8 mm sockets, about 4 mm of plain sleeve showing). Writes
node_organic.*, report_organic.json and stl_organic/ next to the default files. --arm and --fillet override either setting.

Each tube line is two stubs that end in blind sockets: three solid tubes can't share the centre point, so the core
between the sockets is the tube stop. Writes node.blend, stl/node.stl, report.json and, with --render, node.png.
Evidence: docs/features/blend-bracket.md.
"""
import bpy, json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, blend as B, export as E, render as R
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-bb-node"
ORGANIC = "--organic" in argv
TAG = "node_organic" if ORGANIC else "node"
opt = lambda k, d: float(argv[argv.index(k) + 1]) if k in argv else d   # --arm / --fillet override either setting

# ---- parameters (mm)
TUBE_D = 20.0        # tube outside diameter
TUBE_ID = 16.0       # only for the tube placeholders
WALL = 4.0
CLR = 0.2            # fit clearance, radial
ARM = opt("--arm", 36.0 if ORGANIC else 40.0)     # sleeve reaches this far from the centre
STOP = TUBE_D / 2 + CLR + WALL   # socket floor: keeps WALL * sqrt(2) between neighbouring sockets
FILLET = opt("--fillet", 15.0 if ORGANIC else 6.0)
EDGE = 2.0 if ORGANIC else 1.0     # sleeve rim round
LEAD = 0.5           # socket mouth chamfer
TUBE_LEN = 90.0      # placeholder tube stub length from the centre
VOXEL = 0.5

A.new_scene(params={k: v for k, v in globals().items() if k.isupper()})
holds = []
for i, ax in enumerate("XYZ"):
    for sg in (1, -1):
        b = [0.0, 0.0, 0.0]
        b[i] = sg * ARM
        holds.append(B.Tube((0, 0, 0), b, TUBE_D, WALL, CLR, stop=STOP, edge=EDGE, lead_in=LEAD,
                            name="%s%s" % ("p" if sg > 0 else "n", ax.lower())))
node, rep = B.grow(TAG, holds, fillet=FILLET, voxel=VOXEL)
meas = B.measure(node, holds)

# print orientation: printcheck on the -Z sleeve rim and on a corner along (1, 1, 1) (the six rims are alike)
ranked = B.best_orientation(node, {"-z sleeve rim down": (0, 0, -1), "corner (1,1,1) up": (-1, -1, -1)})
best = ranked[0]
orient = {o["label"]: {k: o[k] for k in ("fails", "warns", "bed_mm2", "overhang_mm2", "findings")} for o in ranked}
A.part(node, "PRT_" + TAG, 'PRT', (0.89, 0.14, 0.11, 1.0), stl=TAG, print_rot=Matrix(best["print_rot"]), orient=best["label"],
       supports="no" if best["fails"] == 0 else "yes: tree supports under the 4 horizontal sleeves and in their sockets",
       infill=30)

for h in holds:
    w = (h.b - h.a).normalized()
    t = G.cyl("t", (0, 0), TUBE_D / 2, STOP, TUBE_LEN, 'Z', n=64)
    t = G.csg(t, sub=[G.cyl("ti", (0, 0), TUBE_ID / 2, STOP - 1, TUBE_LEN + 1, 'Z', n=64)])
    G.xform(t, h.M)
    A.part(t, "BUY_tube_%s" % h.name, 'BUY', (0.06, 0.06, 0.07, 1.0), mass_g=round(math.pi * (TUBE_D ** 2 - TUBE_ID ** 2) / 4 * (TUBE_LEN - STOP) * 1.24e-3, 1),
           src="placeholder: 20 x 16 mm tube stub")

os.makedirs(OUT, exist_ok=True)
qty = E.export_stls(os.path.join(OUT, "stl_organic" if ORGANIC else "stl"))
report = {"grow": rep, "holds": meas, "orientation": orient, "params": {k: v for k, v in A.PARAMS.items()}}
with open(os.path.join(OUT, "report%s.json" % ("_organic" if ORGANIC else "")), "w") as f:
    json.dump(report, f, indent=1)
if "--render" in argv:
    R.setup(res=(960, 720))
    R.camera((190, -235, 165), (0, 0, 0), lens=55)
    R.shot(os.path.join(OUT, TAG + ".png"))
E.save_blend(os.path.join(OUT, TAG + ".blend"))
print("NODE", json.dumps({"tris": rep["tris"], "non_manifold_edges": rep["non_manifold_edges"], "t_total_s": rep["t_total_s"],
                          "fit_ok": all(m["fit_ok"] for m in meas.values()),
                          "clearance": [min(m["clearance_min"] for m in meas.values()), max(m["clearance_max"] for m in meas.values())],
                          "wall_min": min(m["wall_min"] for m in meas.values()), "orientation": orient}))
print("BUILD_DONE stls=%s" % qty)
