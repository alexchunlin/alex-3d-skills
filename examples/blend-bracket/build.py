"""Place the parts, grow the bracket: a servo and its controller board held by one blended printed part, with the
swept envelope of the servo's output arm as a keep-out.

    cad build examples/blend-bracket/build.py -- [--out /tmp/alex3d-bb-bracket] [--render]

- The servo (components/placeholders.py) drops into a cradle that grips the lower 18 mm of its body.
- The controller board sits on 4 posts with self-tap pilots. The post tops are cut flat and exact at the board's
  underside.
- A fin braces the cradle to the base plate. The horn and its L-shaped arm swing -90..90 deg about the spline, and the
  arm's finger passes through the fin: geom.swept_envelope makes that keep-out, and the fin gets a notch with 1 mm
  clearance.
Writes bracket.blend, stl/bracket.stl, report.json and, with --render, bracket.png and bracket_keepout.png (a
section at y = 0 through the keep-out, the fin and the servo).
Evidence: docs/features/blend-bracket.md.
"""
import bpy, json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "skills", "print-cad-blender", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "components"))
from cadlib import geom as G, asm as A, blend as B, export as E, features as F, render as R
from mathutils import Matrix, Vector
import placeholders as PH

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-bb-bracket"

# ---- parameters (mm, deg)
SPLINE = (0.0, 0.0, 48.0)     # servo spline top: body z 8..48, centre x -10
PCB_C = (-66.0, 0.0, 12.0)    # controller board underside centre
PLATE_T = 5.0
WALL = 3.0
CLR = 0.2
FILLET = 5.0
KEEP_CLR = 1.0                # arm sweep to bracket
SWING = (-90.0, 90.0)
FINGER = (40.0, 48.0, 8.0)    # arm finger x range and lowest z
POST_R = 3.5
VOXEL = 0.5

A.new_scene(params={k: v for k, v in globals().items() if k.isupper()})
S = PH.C["hiwonder_bus_servo"]
SL, SW, SH = S["body"]
off = S["spline"]["offset_from_body_centre"]
sx, sy, sz = SPLINE

# ---- purchased parts at their poses
servo = G.xform(PH.servo("BUY_servo"), Matrix.Translation(SPLINE))
A.part(servo, "BUY_servo", 'BUY', "buy", mass_g=S["mass_g"], src="components.json hiwonder_bus_servo")
horn = G.xform(PH.horn("BUY_horn"), Matrix.Translation((sx, sy, sz + S["spline"]["protrudes"])))
A.part(horn, "BUY_horn", 'BUY', "buy_metal", mass_g=PH.C["servo_horn_disc"]["mass_g"], src="components.json servo_horn_disc")
h_top = sz + S["spline"]["protrudes"] + PH.C["servo_horn_disc"]["hub"]["h"] + PH.C["servo_horn_disc"]["disc"]["t"]
bar = G.box("BUY_arm", -6, FINGER[1], -5, 5, h_top, h_top + 4)
link = G.csg(bar, add=[G.box("finger", FINGER[0], FINGER[1], -5, 5, FINGER[2], h_top + 0.01)])
A.part(link, "BUY_arm", 'BUY', "pla_a", mass_g=12, src="placeholder: the arm this servo swings")
pcb = G.xform(PH.servo_controller("BUY_controller"), Matrix.Translation(PCB_C))
A.part(pcb, "BUY_controller", 'BUY', "pcb", mass_g=PH.C["hiwonder_servo_controller"]["mass_g"], src="components.json hiwonder_servo_controller")

# ---- keep-out: horn and arm over the full swing
env = G.swept_envelope([horn, link], SPLINE, (0, 0, 1), SWING[0], SWING[1], tol=0.25, voxel=VOXEL, name="KEEP_arm_sweep")
env_info = env["envelope"].to_dict()

# ---- what to grip and what to grow
grip_top = 18.0                               # cradle grips the lowest 18 mm of the body
cradle = B.Block((sx - off, sy, sz - SH / 2), (SL, SW, SH), wall=WALL, clearance=CLR,
                 grip=((-SL, -SW, -SH / 2 - WALL - 2), (SL, SW, -SH / 2 + grip_top)), open=("+z",), edge=1.5, name="servo")
pl0, pl1 = -105.0, 56.0
plate = B.rbox(((pl0 + pl1) / 2, 0, PLATE_T / 2 - 2), (pl1 - pl0, 58, PLATE_T + 4), r=2.5, name="plate")
P = PH.C["hiwonder_servo_controller"]
hx, hy = P["holes"]["rect"][0] / 2, P["holes"]["rect"][1] / 2
posts_at = [(PCB_C[0] + a * hx, PCB_C[1] + b * hy) for a in (-1, 1) for b in (-1, 1)]
posts = [B.rod((x, y, -2), (x, y, PCB_C[2] + 0.6), POST_R, edge=0.5, name="post") for x, y in posts_at]
p0, p1 = Vector((12, 0, 14)), Vector((54, 0, -1))
u = (p1 - p0).normalized()
fin = B.rbox(G.frame((p0 + p1) / 2, u, Vector((0, 1, 0)), u.cross(Vector((0, 1, 0)))), ((p1 - p0).length, 5, 20), r=1.5, name="fin")

# ---- exact cuts: idler boss pocket, board seat, pilots, mounting holes
pcb_l, pcb_w, pcb_t = P["pcb"]
holes = [G.cyl("idler", (sx, sy), S["spline"]["boss_d"] / 2 + 0.4, sz - SH - S["idler_boss"]["protrudes"] - 0.5, sz - SH + 0.5, 'Z')]
holes.append(G.box("seat", PCB_C[0] - pcb_l / 2 - 2, PCB_C[0] + pcb_l / 2 + 2, -pcb_w / 2 - 2, pcb_w / 2 + 2, PCB_C[2], 80))
for x, y in posts_at:
    holes += F.screw_hole((x, y, PCB_C[2] + pcb_t), (0, 0, -1), 10, kind="selftap")
mounts = [(-98.0, -22.0), (-98.0, 22.0), (24.0, -22.0), (24.0, 22.0)]
for x, y in mounts:
    holes += F.screw_hole((x, y, PLATE_T), (0, 0, -1), PLATE_T, kind="clearance")

bracket, rep = B.grow("bracket", [cradle], fillet=FILLET, extra=[plate, fin] + posts, keepout=[env], keepout_clear=KEEP_CLR,
                      keepout_edge=1.0, clip=((-300, -300, 0), (300, 300, 300)), holes=holes, voxel=VOXEL)
meas = B.measure(bracket, [cradle])
# print orientation: printcheck on the clip face and the 6 world axes, best first (the plate on the bed wins)
ranked = B.best_orientation(bracket)
best = ranked[0]
orient = {"best": best["label"], "ranked": [{k: o[k] for k in ("label", "fails", "warns", "bed_mm2", "overhang_mm2")} for o in ranked]}
A.part(bracket, "PRT_bracket", 'PRT', (0.89, 0.14, 0.11, 1.0), stl="bracket", print_rot=Matrix(best["print_rot"]), orient=best["label"],
       supports="no" if best["fails"] == 0 else "yes", infill=25)

os.makedirs(OUT, exist_ok=True)
qty = E.export_stls(os.path.join(OUT, "stl"))
report = {"grow": rep, "holds": meas, "orientation": orient, "envelope": env_info,
          "params": {k: v for k, v in A.PARAMS.items()}}
with open(os.path.join(OUT, "report.json"), "w") as f:
    json.dump(report, f, indent=1)
if "--render" in argv:
    R.setup(res=(960, 720))
    R.camera((150, -190, 170), (-25, 0, 18), lens=50)
    env.hide_render = True
    R.shot(os.path.join(OUT, "bracket.png"))
    # section at y = 0 (keep y > 0, look from -Y): the keep-out's profile over the fin and its notch
    shown = []
    for ob, col in ((env, (0.70, 0.75, 0.85, 1.0)), (bracket, None), (bpy.data.objects["BUY_servo"], None)):
        c = ob.copy()
        c.data = ob.data.copy()
        c.data.transform(ob.matrix_world)
        c.matrix_world = Matrix.Identity(4)
        c.parent = None
        G.scratch().objects.link(c)
        G.csg(c, sub=[G.box("half", -500, 500, -500, 0, -500, 500)], check=False)
        if col:
            c.data.materials.clear()
            c.data.materials.append(A.mat(col))
        c.hide_render = False
        shown.append(c)
    for o in bpy.data.objects:
        if o.type == 'MESH' and o not in shown:
            o.hide_render = True
    R.camera((10, -400, 34), (10, 0, 34), ortho=175)
    R.shot(os.path.join(OUT, "bracket_keepout.png"))
    for o in shown:
        G.kill(o)
    for o in bpy.data.objects:
        o.hide_render = o.type == 'EMPTY'
E.save_blend(os.path.join(OUT, "bracket.blend"))
print("BRACKET", json.dumps({"tris": rep["tris"], "non_manifold_edges": rep["non_manifold_edges"], "t_total_s": rep["t_total_s"],
                             "servo": meas["servo"], "orientation": orient, "envelope": env_info}))
print("BUILD_DONE stls=%s" % qty)
