"""Test assembly for cadcheck's driver-bit hint (sourced by tools/verify.d/fastener_access_hint.sh).

    cad build tools/verify.d/fastener_access_hint_build.py -- --out /tmp/alex3d-verify/ah

Push-assist PA-A3-T10: one M4 was moved four times by hand (13.7 min of full checks) because the access fail said
"L-key" but not where a straight bit would clear. Each case is an M4 self-tapped into the floor of a Ø16 well 18 mm
deep in a 40 x 40 block, 60 mm apart along x. The well stops an L-key (its long leg swings 15.8 mm up, inside the well)
and leaves a Ø6 straight bit clear.
  FST_ah_open  no lid: a straight bit reaches it (reach about 32 mm). No access finding, no hint.
  FST_ah_lid   PRT_ah_lid_lid covers the well 12 mm above its rim (z 30-33): blocked. The hint names the lid and the
               bit length through a hole in it, and finds no tilt up to 10 deg.
  FST_ah_edge  PRT_ah_edge_lid at the same height covers x < 1.8 mm short of the axis: two of the bit's six edge rays
               hit it. Tilted 2 deg toward +x the bit clears (0.9 mm across at the lid's 30 mm); 45 deg off +x it
               moves 0.74 and still hits.
  FST_ah_deep  a well 70 mm deep and no lid: reachable with a 92 mm+ bit (warn); no tilt clears inside the well.
  FST_ah_buy   as FST_ah_lid under a purchased board, BUY_ah_buy_lid: no hole suggested through it (a1's reversed motor
               screws point back through BUY_motor).
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, features as F, asm as A, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-ah-test"
DOWN = (0, 0, -1)
INFO = dict(print_rot=A.R_ID, orient="flat", supports="no", infill=30)
A.new_scene()
F.use_checks(None)
parts = []
for tag, x, well, lid in (("open", 0.0, 18.0, None), ("lid", 60.0, 18.0, (-20, 20)), ("edge", 120.0, 18.0, (-20, -1.8)),
                          ("deep", 180.0, 70.0, None), ("buy", 240.0, 18.0, (-20, 20))):
    block = G.csg(G.box("PRT_ah_%s_block" % tag, x - 20, x + 20, -20, 20, -14, well), sub=[G.cyl("well", (x, 0), 8.0, 0, well + 1)])
    cuts = F.fastener_joint("FST_ah_" + tag, "M4", (x, 0, 0), DOWN, [block])
    parts.append(G.csg(block, sub=cuts[block.name]))
    if lid and tag == "buy":
        A.part(G.box("BUY_ah_buy_lid", x + lid[0], x + lid[1], -20, 20, well + 12, well + 15), "BUY_ah_buy_lid", 'BUY', "pcb",
               mass_g=20, src="test board")
    elif lid:
        parts.append(G.box("PRT_ah_%s_lid" % tag, x + lid[0], x + lid[1], -20, 20, well + 12, well + 15))
for o in parts:
    A.part(o, o.name, 'PRT', "pla_a", stl=o.name[4:], **INFO)
os.makedirs(OUT, exist_ok=True)
E.save_blend(os.path.join(OUT, "ah.blend"))
with open(os.path.join(OUT, "checks.json"), "w") as f:
    json.dump({}, f)
print("AH_BUILT", len(parts), "parts")
