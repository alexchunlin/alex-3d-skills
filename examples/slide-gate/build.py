"""Slide-gate example: proves the cadcheck features added after v2 attempt 3 (FINDINGS V2A3).

    Blender -b --python build.py -- [--out /tmp/alex3d-gate] [--bug]

A gate slides 0..GATE_TRAVEL on a prismatic joint (PIV_gate) between two rails, up to a printed end stop, under a
spring detent whose bump drops into a notch at each end. Two cables meet in free space, and a separate test block
has a 40 x 5 slot cut at 45 deg under a ceiling (a 5 mm bridge; a bbox reads 31.8).

--bug plants: the end stop moved 5 mm inside the gate's travel (a collision inside the slide sweep), and an
M3 x 9 stop screw (not a stock length).
"""
import math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, features as F, asm as A, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-gate"
BUG = "--bug" in argv

# ---- parameters (mm)
GATE_L, GATE_W, GATE_T = 30.0, 18.0, 4.0
GATE_TRAVEL = 20.0
CLR = 1.0                     # gate to plate and rails
PLATE_T = 5.0
STOP_X = GATE_L + GATE_TRAVEL - (5.0 if BUG else 0.0)   # bug: the stop sits 5 mm inside the travel
BUMP_X = 25.0                 # detent bump centre, world x
BUMP_DIP = 0.4                # bump below the gate top between the notches
NOTCH_D = 0.6
STOP_SCREW_L = 9.0 if BUG else 10.0

A.new_scene(params={k: v for k, v in globals().items() if k.isupper()})
A.joint("PIV_gate", (0, 0, 0), 'X', 0, GATE_TRAVEL, step=2, prismatic=True)

z0, z1 = PLATE_T + CLR, PLATE_T + CLR + GATE_T                   # gate bottom and top
rail_y = GATE_W / 2 + CLR
housing = G.box("housing", -10, 62, -rail_y - 5, rail_y + 5, 0, PLATE_T)
rails = [G.box("rl", -10, 62, -rail_y - 5, -rail_y, PLATE_T - 0.01, z1 + 2), G.box("rr", -10, 62, rail_y, rail_y + 5, PLATE_T - 0.01, z1 + 2)]
housing = G.csg(housing, add=rails)
SC_AT = (STOP_X + 5.0, 0.0, z1)                                    # head clear of the gate end
housing = G.csg(housing, sub=F.screw_hole(SC_AT, (0, 0, -1), STOP_SCREW_L, kind="clamp", clamp=GATE_T + CLR))
A.part(housing, "PRT_housing", 'PRT', "pla_a", stl="housing", print_rot=A.R_ID, orient="plate on the bed", supports="no", infill=20)

stop = G.box("stop", STOP_X, STOP_X + 9, -GATE_W / 2, GATE_W / 2, PLATE_T, z1)
stop = G.csg(stop, sub=F.screw_hole(SC_AT, (0, 0, -1), STOP_SCREW_L, kind="clamp", clamp=GATE_T + CLR))
A.part(stop, "PRT_stop", 'PRT', "pla_b", stl="stop", print_rot=A.R_ID, orient="flat", supports="no", infill=40)
A.fastener("FST_stop", SC_AT, (0, 0, -1), STOP_SCREW_L, "M3_pan", host="PRT_housing", step="stop")

gate = G.box("gate", 0, GATE_L, -GATE_W / 2, GATE_W / 2, z0, z1)
notches = [G.box("n", x - 1.5, x + 1.5, -3, 3, z1 - NOTCH_D, z1 + 1) for x in (BUMP_X, BUMP_X - GATE_TRAVEL)]
gate = G.csg(gate, sub=notches)
A.part(gate, "PRT_gate", 'PRT', "pla_b", joint="PIV_gate", stl="gate", print_rot=A.R_ID, orient="flat", supports="no", infill=30)

arm = G.box("arm", BUMP_X - 1, BUMP_X + 1, -2, rail_y + 4, z1 + 2, z1 + 3.6)       # rests on the +Y rail top
bump = G.box("bump", BUMP_X - 1, BUMP_X + 1, -2, 2, z1 - BUMP_DIP, z1 + 2.01)
detent = G.csg(arm, add=[bump])
A.part(detent, "PRT_detent", 'PRT', "pla_a", stl="detent", print_rot=A.R_FLIP, orient="arm top on the bed", supports="no", infill=100)

board = G.box("board", -8, -2, -rail_y - 4, -rail_y - 1, z1 + 2, z1 + 4)          # sits on the -Y rail
A.part(board, "BUY_board", 'BUY', "pcb", mass_g=5, src="placeholder board")
P = (30.0, -rail_y - 2.5, 30.0)                                                      # the cables meet here, in free space
A.cable("CAB_a", [(-5, -rail_y - 2.5, z1 + 4.5), (-5, -rail_y - 2.5, 30), P], 1.0, "cable_blk", lead_len=100)
A.cable("CAB_b", [P, (40, -rail_y - 2.5, 35)], 1.0, "cable_blk", lead_len=100)

# a 40 x 5 slot at 45 deg cut from below a 6 mm-high ceiling: the bridge is 5 mm wide
c, s = math.cos(math.radians(45)), math.sin(math.radians(45))
slot = [(150 + x * c - y * s, y * c + x * s) for x, y in ((-20, -2.5), (20, -2.5), (20, 2.5), (-20, 2.5))]
blk = G.csg(G.box("blk", 120, 180, -30, 30, 0, 10), sub=[G.prism("slot", slot, -1, 6, 'Z')])
A.part(blk, "PRT_bridge_test", 'PRT', "pla_a", stl="bridge_test", print_rot=A.R_ID, orient="flat", supports="no", infill=20)

os.makedirs(OUT, exist_ok=True)
E.export_stls(os.path.join(OUT, "stl"))
A.write_manifest(os.path.join(OUT, "manifest.json"))
E.save_blend(os.path.join(OUT, "gate.blend"))
