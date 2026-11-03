"""Demo: a tiny pan/tilt turret built with cadlib, used to prove the library and cadcheck.

    Blender -b --python build.py -- [--out /tmp/alex3d-demo] [--bug] [--render] [--glb [--no-draco]]

Screws go in with features.fastener_joint, which measures each stack and picks the stock length.
--bug plants the attempt-1 foot-guns on purpose: a reversed screw, a screw head under the moving
arm, and a tilt range that hits the base; and one from attempt 2: a through-bolt that stops short of its
nut (A2-F3, forced past fastener_joint with length=2, strict=False). cadcheck must flag all four.
"""
import bpy, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, features as F, asm as A, export as E, render as R
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-demo"
BUG = "--bug" in argv

# ---- parameters (mm, deg)
BASE = 80.0          # base is BASE x BASE
BASE_H = 30.0
WALL = 2.4
PAN_R = 30.0
PAN_T = 5.0
TILT_Z = 70.0        # tilt axis height
ARM_GAP = 30.0       # inside distance between yoke arms
ARM_T = 5.0
TILT_LO, TILT_HI = (0.0, 40.0) if not BUG else (-50.0, 40.0)   # bug: muzzle dips into the pan disc
CLR = 0.5            # running clearance between moving bodies

A.new_scene(params={k: v for k, v in globals().items() if k.isupper()})
A.joint("PIV_pan", (0, 0, BASE_H), 'Z', -90, 90, step=15)
A.joint("PIV_tilt", (0, 0, TILT_Z), 'X', TILT_LO, TILT_HI, parent="PIV_pan", step=5)

UP = (0, 0, 1)
FJ = {}              # cutters per part from F.fastener_joint, applied with one csg per part

# ---- base: hollow box with a lid deck, 4 self-tap bosses for the floor
h = BASE / 2
base = G.prism("PRT_base", G.rrect(-h, h, -h, h, 6), 0, BASE_H, 'Z')
cav = G.prism("cav", G.rrect(-h + WALL, h - WALL, -h + WALL, h - WALL, 4), -1, BASE_H - WALL, 'Z')
G.bevel(base, 0.8)
bosses = []
for sx in (-1, 1):
    for sy in (-1, 1):
        bosses += F.boss((sx * (h - 7), sy * (h - 7), 12.0), UP, 7.0, 12.0)
base = G.csg(base, sub=[cav])
base = G.csg(base, add=bosses)
for i, (sx, sy) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
    F.fastener_joint("FST_floor_%d" % i, "M3", (sx * (h - 7), sy * (h - 7), 0.0), UP, [base], head="pan", step="close base", cuts=FJ)
# side-wall bolt, nut on the wall's inside face; the bug build forces 2 mm so the tip stops 0.4 mm short of the nut
F.fastener_joint("FST_side", "M3", (h, 20.0, 15.0), (-1, 0, 0), [base], style="nut", trap=False, step="close base",
                 length=2 if BUG else None, strict=not BUG, cuts=FJ)
cuts = FJ["PRT_base"] + [G.cyl("pass", (0, 0), 4.0, BASE_H - WALL - 1, BASE_H + 1, 'Z')]   # + cable pass-through
base = G.csg(base, sub=cuts)
# deck on the bed puts the floor bosses' ends 18 mm up in mid-air (cad printcheck: 4 islands at z 18), so: supports
A.part(base, "PRT_base", 'PRT', "pla_a", stl="base", print_rot=A.R_FLIP, orient="deck on the bed; tree supports under the 4 floor bosses",
       supports="yes", infill=15)

# ---- pan disc on the deck (sits CLR above it), yoke arms on it
pan = G.cyl("PRT_pan", (0, 0), PAN_R, BASE_H + CLR, BASE_H + CLR + PAN_T, 'Z')
G.bevel(pan, 0.8)
SINK = 2.8           # arm screw heads sit in counterbores under the pan disc
z_bear = BASE_H + CLR + SINK
z0 = BASE_H + CLR + PAN_T
arms = {}
for s in (-1, 1):
    x0 = s * ARM_GAP / 2
    x1 = x0 + s * ARM_T
    prof = G.hull2d([(-14, z0), (14, z0), (-14, z0 + 3), (14, z0 + 3)] + G.circle((0, TILT_Z), 9.0))
    arms[s] = G.prism("PRT_arm_%s" % ("L" if s < 0 else "R"), prof, min(x0, x1), max(x0, x1), 'X')
# arm screws: head in a counterbore under the pan disc, up through the disc into the arm foot
for i, s in enumerate((-1, 1)):
    at = (s * (ARM_GAP / 2 + ARM_T / 2), 0.0, z_bear)
    if BUG and i == 0:   # planted A1-F10: hand-placed holes, screw reversed (head up inside the arm)
        FJ.setdefault("PRT_pan", []).extend(F.screw_hole(at, UP, 10, kind="clearance", head="pan", sink=SINK))
        FJ.setdefault(arms[s].name, []).extend(F.screw_hole(at, UP, 10, kind="selftap"))
        A.fastener("FST_arm_%d" % i, (at[0], 0.0, z0 + 8), (0, 0, -1), 10, "M3_pan", joint="PIV_pan", step="arms")
    else:
        F.fastener_joint("FST_arm_%d" % i, "M3", at, UP, [pan, arms[s]], head="pan", sink=SINK, joint="PIV_pan", step="arms", cuts=FJ)
pcuts = [G.cyl("pass", (0, 0), 4.0, BASE_H - 5, BASE_H + CLR + PAN_T + 1, 'Z')]   # cable pass-through
pan = G.csg(pan, sub=pcuts + FJ["PRT_pan"])
A.part(pan, "PRT_pan", 'PRT', "pla_b", joint="PIV_pan", stl="pan", print_rot=A.R_ID, orient="flat", supports="no", infill=25)
for s, arm in arms.items():
    x0, x1 = s * ARM_GAP / 2, s * (ARM_GAP / 2 + ARM_T)
    hole = F.bore("ah", (0, TILT_Z), 3.0, min(x0, x1) - 1, max(x0, x1) + 1, 'X')
    arm = G.csg(arm, sub=[hole] + FJ[arm.name])
    A.part(arm, arm.name, 'PRT', "pla_b", joint="PIV_pan", stl="arm", print_rot=A.R_PX_DOWN if s < 0 else A.R_NX_DOWN,
           orient="outer face on the bed", supports="no", infill=25)

# ---- tilting barrel between the arms, on a printed axle
L = ARM_GAP - 2 * CLR
barrel = G.cyl("barrel", (0, TILT_Z), 10.0, -L / 2, L / 2, 'X')
muzzle = G.prism("muzzle", G.rrect(-6, 6, TILT_Z - 6, TILT_Z + 6, 2), 0, 45, 'Y')
muzzle = G.csg(muzzle, sub=[G.cyl("bore", (0, TILT_Z), 4.0, -1, 50, 'Y')])
barrel = G.csg(barrel, add=[muzzle])
axle = G.cyl("axle", (0, TILT_Z), 3.0, -ARM_GAP / 2 - ARM_T - 1, ARM_GAP / 2 + ARM_T + 1, 'X')
barrel = G.csg(barrel, add=[axle])
# on its end face the muzzle is a 35 mm cantilever (cad printcheck), so: supports
A.part(barrel, "PRT_barrel", 'PRT', "pla_a", joint="PIV_tilt", stl="barrel", print_rot=A.R_PX_DOWN,
       orient="side face down; supports under the muzzle", supports="yes", infill=20)

# ---- purchased: a servo-sized block in the base, a battery that slides out +X
srv = G.box("srv", -30, -10, -20, 20, 5, 25)
A.part(srv, "BUY_servo_pan", 'BUY', "buy", mass_g=66, src="Hiwonder HTS-35H envelope (brief)")

# bug: a screw head proud of the pan disc top, inside the muzzle's swing
if BUG:
    A.fastener("FST_proud", (0, 25, z0), (0, 0, -1), 4, "M3_cap", joint="PIV_pan", host="PRT_pan", step="arms")

# ---- cable from the base up through the pan axis
A.cable("CAB_servo_bus", [(-10, 0, 15), (0, 0, 15), (0, 0, BASE_H + CLR + PAN_T + 4)], 1.2, "cable_wht", lead_len=150)

os.makedirs(OUT, exist_ok=True)
qty = E.export_stls(os.path.join(OUT, "stl"))
A.write_manifest(os.path.join(OUT, "manifest.json"))
if "--render" in argv:
    R.view_set(os.path.join(OUT, "renders"), poses={"pan+90_tilt%d" % TILT_HI: {"PIV_pan": 90, "PIV_tilt": TILT_HI}})
    R.section(os.path.join(OUT, "renders"), "section_x0.png", "x", 0.0, (300, 0, 50), (0, 0, 50), 140)
    R.exploded(os.path.join(OUT, "renders"))
if "--glb" in argv:   # model.glb: a node per part, a clip per joint and one for checks.json's assembly_order
    E.write_glb(os.path.join(OUT, "model.glb"), checks=os.path.join(HERE, "checks.json"),
                report=os.path.join(OUT, "cadcheck.json"), draco="--no-draco" not in argv)
E.save_blend(os.path.join(OUT, "demo.blend"))
print("BUILD_DONE stls=%s" % qty)
