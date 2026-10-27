"""The demo turret again, placed through mates (cadlib.mates) instead of world coordinates: the same parts and screws
as build.py, each part modelled in its own frame with named connectors, and one assemble() call that places them,
makes PIV_pan and PIV_tilt and runs every fastener_joint. cadcheck must give the same rows as build.py's clean build.

    cad build examples/demo-turret/build_mates.py -- [--out /tmp/alex3d-demo-mates] [--bug-pattern]

--bug-pattern types the servo seat's peg pattern 0.5 mm off the servo's (rect(10, 30.5) against rect(10, 30)):
assemble() must refuse it and print both specs.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, features as F, asm as A, mates as M, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-demo-mates"
BUG_PATTERN = "--bug-pattern" in argv

# ---- parameters (mm, deg): as build.py
BASE = 80.0
BASE_H = 30.0
WALL = 2.4
PAN_R = 30.0
PAN_T = 5.0
TILT_Z = 70.0        # tilt axis height
ARM_GAP = 30.0       # inside distance between yoke arms
ARM_T = 5.0
TILT_LO, TILT_HI = 0.0, 40.0
CLR = 0.5            # running clearance between moving bodies
SINK = 2.8           # arm screw heads sit in counterbores under the pan disc
ARM_X = ARM_GAP / 2 + ARM_T / 2        # arm centre plane
ARM_PIVOT = TILT_Z - (BASE_H + CLR + PAN_T)   # tilt axis above the arm's foot

A.new_scene(params={k: v for k, v in globals().items() if k.isupper()})
UP, DOWN = (0, 0, 1), (0, 0, -1)

# ---- base (the ground): hollow box, deck on top, 4 floor bosses
h = BASE / 2
base = G.prism("base", G.rrect(-h, h, -h, h, 6), 0, BASE_H, 'Z')
cav = G.prism("cav", G.rrect(-h + WALL, h - WALL, -h + WALL, h - WALL, 4), -1, BASE_H - WALL, 'Z')
G.bevel(base, 0.8)
base = G.csg(base, sub=[cav])
base = G.csg(base, add=[b for sx in (-1, 1) for sy in (-1, 1) for b in F.boss((sx * (h - 7), sy * (h - 7), 12.0), UP, 7.0, 12.0)])
base = G.csg(base, sub=[G.cyl("pass", (0, 0), 4.0, BASE_H - WALL - 1, BASE_H + 1, 'Z')])   # cable pass-through
M.connector(base, "deck", (0, 0, BASE_H), UP)
# floor screws from below; x along +Y numbers them as build.py does (FST_floor_0 at -x -y, _1 at -x +y)
M.connector(base, "floor", (0, 0, 0), DOWN, x=(0, 1, 0), pattern=M.rect(2 * (h - 7), 2 * (h - 7)), hole="M3")
M.connector(base, "side", (h, 20.0, 15.0), (1, 0, 0), hole="M3")
M.connector(base, "servo_seat", (-20, 0, 5), UP, pattern=M.rect(10, 30.5 if BUG_PATTERN else 30), note="servo locating pegs")
M.part(base, "PRT_base", 'PRT', "pla_a", stl="base", print_rot=A.R_FLIP,
       orient="deck on the bed; tree supports under the 4 floor bosses", supports="yes", infill=15)

# ---- pan disc, modelled on its underside
pan = G.cyl("pan", (0, 0), PAN_R, 0, PAN_T, 'Z')
G.bevel(pan, 0.8)
pan = G.csg(pan, sub=[G.cyl("pass", (0, 0), 4.0, -5.5, PAN_T + 1, 'Z')])
M.connector(pan, "bottom", (0, 0, 0), DOWN)
for s, side in ((-1, "L"), (1, "R")):
    M.connector(pan, "arm_" + side, (s * ARM_X, 0, PAN_T), UP, hole="M3")
M.part(pan, "PRT_pan", 'PRT', "pla_b", stl="pan", print_rot=A.R_ID, orient="flat", supports="no", infill=25)

# ---- yoke arms, modelled about their foot centre
for s, side in ((-1, "L"), (1, "R")):
    prof = G.hull2d([(-14, 0), (14, 0), (-14, 3), (14, 3)] + G.circle((0, ARM_PIVOT), 9.0))
    arm = G.prism("arm_" + side, prof, -ARM_T / 2, ARM_T / 2, 'X')
    arm = G.csg(arm, sub=[F.bore("ah", (0, ARM_PIVOT), 3.0, -ARM_T / 2 - 1, ARM_T / 2 + 1, 'X')])
    M.connector(arm, "foot", (0, 0, 0), DOWN, hole="M3")
    M.connector(arm, "pivot", (-s * ARM_T / 2, 0, ARM_PIVOT), (-s, 0, 0))     # inner face, z toward the barrel
    M.part(arm, "PRT_arm_" + side, 'PRT', "pla_b", stl="arm", print_rot=A.R_PX_DOWN if s < 0 else A.R_NX_DOWN,
           orient="outer face on the bed", supports="no", infill=25)

# ---- barrel, modelled about its tilt axis (X)
L = ARM_GAP - 2 * CLR
barrel = G.cyl("barrel", (0, 0), 10.0, -L / 2, L / 2, 'X')
muzzle = G.prism("muzzle", G.rrect(-6, 6, -6, 6, 2), 0, 45, 'Y')
muzzle = G.csg(muzzle, sub=[G.cyl("bore", (0, 0), 4.0, -1, 50, 'Y')])
barrel = G.csg(barrel, add=[muzzle])
barrel = G.csg(barrel, add=[G.cyl("axle", (0, 0), 3.0, -ARM_GAP / 2 - ARM_T - 1, ARM_GAP / 2 + ARM_T + 1, 'X')])
M.connector(barrel, "end_L", (-L / 2, 0, 0), (-1, 0, 0))
M.part(barrel, "PRT_barrel", 'PRT', "pla_a", stl="barrel", print_rot=A.R_PX_DOWN,
       orient="side face down; supports under the muzzle", supports="yes", infill=20)

# ---- purchased: a servo-sized block, modelled on its underside
srv = G.box("srv", -10, 10, -20, 20, 0, 20)
M.connector(srv, "bottom", (0, 0, 0), DOWN, pattern=M.rect(10, 30), note="locating pegs")
M.part(srv, "BUY_servo_pan", 'BUY', "buy", mass_g=66, src="Hiwonder HTS-35H envelope (brief)")

# ---- the interfaces: one line each; assemble() does the placing, the joints and the screws
M.fasten("PRT_base:floor", name="FST_floor", size="M3", head="pan", step="close base")
M.fasten("PRT_base:side", name="FST_side", size="M3", style="nut", trap=False, step="close base")
M.mate("PRT_base:deck", "PRT_pan:bottom", "revolute", name="PIV_pan", lo=-90, hi=90, sweep_step=15, gap=CLR,
       fit="clearance")
for i, side in enumerate("LR"):
    M.mate("PRT_pan:arm_" + side, "PRT_arm_%s:foot" % side, "fastened", name="arm_" + side, step="arms",
           fastener=dict(name="FST_arm_%d" % i, size="M3", head="pan", sink=SINK, head_on="a"))
M.mate("PRT_arm_L:pivot", "PRT_barrel:end_L", "revolute", name="PIV_tilt", lo=TILT_LO, hi=TILT_HI, sweep_step=5,
       gap=CLR, fit="clearance", note="printed axle in both arm bores")
M.mate("PRT_base:servo_seat", "BUY_servo_pan:bottom", "rigid", name="servo", fit="press")
M.assemble("PRT_base")

# ---- cable from the base up through the pan axis (routed, not mated)
A.cable("CAB_servo_bus", [(-10, 0, 15), (0, 0, 15), (0, 0, BASE_H + CLR + PAN_T + 4)], 1.2, "cable_wht", lead_len=150)

os.makedirs(OUT, exist_ok=True)
qty = E.export_stls(os.path.join(OUT, "stl"))
A.write_manifest(os.path.join(OUT, "manifest.json"))
E.save_blend(os.path.join(OUT, "demo.blend"))
print("BUILD_DONE stls=%s" % qty)
