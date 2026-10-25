"""Test assembly for features.fastener_joint (sourced by tools/verify.d/fastener_joint.sh).

    cad build tools/verify.d/fastener_joint_build.py -- --size M3 --out /tmp/alex3d-verify/fj/M3 [--errors]

A 4.7 mm plate on an 11 mm block, plus a 3 mm bracket on a purchased motor block, all screwed from the top (-Z):
  FST_fj_nut     through-bolt, nut in a trap at the block's far face (A2-F3: the length is picked, not guessed)
  FST_fj_tap     self-tap, countersunk, into the block
  FST_fj_ins     heat-set insert in the block
  FST_fj_motor   machine screw into the motor's tapped hole (8 mm deep)
Writes fj_report.json: each joint's record plus hole diameters measured by radial rays in the cut parts.
--errors first runs the four mistakes the joint must refuse (reversed screw, thin host, short bolt, buried head)
and prints one FJ_ERR line each.
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, features as F, asm as A, export as E
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SIZE = argv[argv.index("--size") + 1] if "--size" in argv else "M3"
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-fj-test"
DOWN = (0, 0, -1)
Z_TOP = 15.7          # plate 11 .. 15.7 on block 0 .. 11
J = {"FST_fj_nut": (-20.0, 0.0), "FST_fj_tap": (-5.0, 0.0), "FST_fj_ins": (10.0, 0.0)}


def solids():
    plate = G.box("PRT_fj_plate", -30, 30, -10, 10, 11.0, Z_TOP)
    block = G.box("PRT_fj_block", -30, 30, -10, 10, 0.0, 11.0)
    brk = G.box("PRT_fj_bracket", 30, 54, -10, 10, 12.0, 15.0)
    motor = G.box("BUY_fj_motor", 32, 52, -8, 8, 0.0, 12.0)
    return plate, block, brk, motor


def errors():
    A.new_scene()
    plate, block, brk, motor = solids()
    x, y = J["FST_fj_nut"]
    cases = [
        ("reversed", dict(name="FST_e0", at=(x, y, Z_TOP), into=(0, 0, 1), parts=[plate, block], style="nut")),
        ("thin_host", dict(name="FST_e1", at=(x, y, Z_TOP), into=DOWN, parts=[plate], style="selftap")),
        ("short_bolt", dict(name="FST_e2", at=(x, y, Z_TOP), into=DOWN, parts=[plate, block], style="nut", length=12)),
        ("buried_head", dict(name="FST_e3", at=(x, y, Z_TOP - 1.0), into=DOWN, parts=[plate, block], style="nut")),
    ]
    for tag, kw in cases:
        try:
            F.fastener_joint(size=SIZE, **kw)
            print("FJ_ERR %s: NOT RAISED" % tag)
        except F.FastenerError as e:
            print("FJ_ERR %s: %s" % (tag, e))
    # 31 mm stack: no stock bolt fits with the nut at the far face (M3 needs 31.2-33.7; stock 30, 35), so the
    # trap goes deeper and the 30 mm bolt is used
    tall = G.box("PRT_fj_tall", -30, 30, 20, 40, Z_TOP - 31.0, 11.0)
    pl2 = G.box("PRT_fj_plate2", -30, 30, 20, 40, 11.0, Z_TOP)
    F.fastener_joint("FST_deep", SIZE, (0, 30, Z_TOP), DOWN, [pl2, tall], style="nut")
    r = A.PARTS["FST_deep"]["fastener_joint"]
    print("FJ_DEEP length=%g deepened=%s protrusion=%s" % (r["length"], r.get("trap_deepened_mm"), r["protrusion_mm"]))


def hole_d(ob, at, t, n=360):
    """Diameter of the hole in `ob` at depth t below `at` (DOWN axis): 2 x the farthest radial ray hit (round
    holes, vertices on the circle) and 2 x the nearest (hex traps: across flats)."""
    M = ob.matrix_world
    tree = BVHTree.FromPolygons([M @ v.co for v in ob.data.vertices], [tuple(f.vertices) for f in ob.data.polygons])
    c = Vector((at[0], at[1], at[2] - t))
    rs = []
    for k in range(n):
        a = 2 * math.pi * (k + 0.37) / n          # off the polygon vertices, so no ray slips through an edge
        h = tree.ray_cast(c, Vector((math.cos(a), math.sin(a), 0)), 50.0)
        if h[0] is not None:
            rs.append(h[3])
    return {"max_d": round(2 * max(rs), 3), "min_d": round(2 * min(rs), 3)} if rs else None


if "--errors" in argv:
    errors()

A.new_scene(params={"SIZE": SIZE})
plate, block, brk, motor = solids()
cuts = {}
x, y = J["FST_fj_nut"]
F.fastener_joint("FST_fj_nut", SIZE, (x, y, Z_TOP), DOWN, [block, plate], style="nut", head="cap", step="1", cuts=cuts)
x, y = J["FST_fj_tap"]
F.fastener_joint("FST_fj_tap", SIZE, (x, y, Z_TOP), DOWN, [plate, block], style="selftap", head="csk", step="1", cuts=cuts)
x, y = J["FST_fj_ins"]
F.fastener_joint("FST_fj_ins", SIZE, (x, y, Z_TOP), DOWN, [plate, block], style="insert", head="cap", step="1", cuts=cuts)
F.fastener_joint("FST_fj_motor", SIZE, (42.0, 0.0, 15.0), DOWN, [brk, motor], style="tapped", head="pan", depth=8.0,
                 step="1", cuts=cuts)
for ob in (plate, block, brk):
    G.csg(ob, sub=cuts[ob.name])
assert cuts["BUY_fj_motor"] == [], "a tapped purchased part gets no cut"
info = dict(stl=None, print_rot=A.R_ID, orient="flat", supports="no", infill=30)
A.part(plate, "PRT_fj_plate", 'PRT', "pla_a", **dict(info, stl="fj_plate"))
A.part(block, "PRT_fj_block", 'PRT', "pla_b", **dict(info, stl="fj_block"))
A.part(brk, "PRT_fj_bracket", 'PRT', "pla_a", **dict(info, stl="fj_bracket"))
A.part(motor, "BUY_fj_motor", 'BUY', "buy", mass_g=50, src="test block with an 8 mm deep tapped hole")

S = F.size_rules(SIZE)
rep = {"size": SIZE, "joints": {n: A.PARTS[n]["fastener_joint"] for n in ("FST_fj_nut", "FST_fj_tap", "FST_fj_ins", "FST_fj_motor")}}
L = {n: r["length"] for n, r in rep["joints"].items()}
nut_t = rep["joints"]["FST_fj_nut"]["grip_mm"]
top = lambda n: (J[n][0], J[n][1], Z_TOP)
rep["holes"] = {
    "nut_plate_clear": hole_d(plate, top("FST_fj_nut"), 2.0),
    "nut_block_clear": hole_d(block, top("FST_fj_nut"), 8.0),
    "nut_trap": hole_d(block, top("FST_fj_nut"), nut_t + 1.0),
    "tap_plate_clear": hole_d(plate, top("FST_fj_tap"), 3.5),
    "tap_block_pilot": hole_d(block, top("FST_fj_tap"), 8.0),
    "ins_block_pocket": hole_d(block, top("FST_fj_ins"), 4.7 + S["insert_len"] / 2),
    "ins_block_tip": hole_d(block, top("FST_fj_ins"), L["FST_fj_ins"] - 0.3),
    "motor_bracket_clear": hole_d(brk, (42.0, 0.0, 15.0), 1.5),
}
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "fj_report.json"), "w") as f:
    json.dump(rep, f, indent=1)
E.export_stls(os.path.join(OUT, "stl"))
A.write_manifest(os.path.join(OUT, "manifest.json"))
E.save_blend(os.path.join(OUT, "fj.blend"))
print("FJ_DONE %s %s" % (SIZE, json.dumps(L)))
