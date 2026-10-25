"""Builds a small scene for cadcheck's cable kink and shared-run tests (FINDINGS V2A7-F2). Run in Blender:

    Blender -b --factory-startup --python tools/test_cable_shapes.py -- --out /tmp/alex3d-verify/cables

then `cad check OUT/cables.blend OUT/checks.json --only cables`. v2 A7 laid the tilt and feeder bus leads in one tube
for 16 mm and turned both 90 deg onto the splice face 1.5 mm below. Expected warns: exactly
- CAB_kink kinks (90 deg 1.5 above the plug, radius 0);
- CAB_x and CAB_y lie in one tube for about 20 mm.
Not warned: CAB_round (same plug, 4 mm straight out of it and a 10-chord arc of radius 4), and CAB_h1 / CAB_h2, which
hand over in free space as one chained conductor, so CAB_h2 may turn 3 mm after it.
"""
import json, math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-cables"
os.makedirs(OUT, exist_ok=True)
A.new_scene()
A.part(G.box("plug", -5, 25, -5, 5, 0, 10), "BUY_plug", 'BUY', "pcb", mass_g=2, src="test block")
# 90 deg turn 1.5 mm above the plug's top face: the bus leads of v2 A7 (A7-02)
A.cable("CAB_kink", [(-30, 0, 11.5), (0, 0, 11.5), (0, 0, 10)], 1.4, "cable_blk", lead_len=100)
# the same turn done properly: a radius-4 arc, then 4 mm straight down into the plug
arc = [(20 - 4 + 4 * math.sin(math.radians(a)), 0, 18 - 4 + 4 * math.cos(math.radians(a))) for a in range(0, 91, 9)]
A.cable("CAB_round", [(-30, 0, 18)] + [(p[0], 0, p[2]) for p in arc] + [(20, 0, 10)], 1.4, "cable_blk", lead_len=100)
# two leads coincident for 20 mm
A.cable("CAB_x", [(0, 40, 5), (40, 40, 5)], 1.4, "cable_blk", lead_len=100)
A.cable("CAB_y", [(20, 60, 5), (20, 40, 5), (40, 40, 5), (40, 20, 5)], 1.4, "cable_blk", lead_len=100)
# one conductor split into two routes that meet in free space: CAB_h2 turns 3 mm after the hand-over (radius 3), which
# would read as a kink 3 mm out of a plug, where the first OD must run straight
A.cable("CAB_h1", [(0, 80, 5), (30, 80, 5)], 1.4, "cable_blk", lead_len=100)
A.cable("CAB_h2", [(30, 80, 5), (30, 80, 8), (30, 100, 8)], 1.4, "cable_blk", lead_len=100)
A.write_manifest(os.path.join(OUT, "manifest.json"))
E.save_blend(os.path.join(OUT, "cables.blend"))
json.dump({"cable_chains": [{"name": "h", "cables": ["CAB_h1", "CAB_h2"], "lead": 100}], "exposure": {"cables_ok": ["CAB_*"]}}, open(os.path.join(OUT, "checks.json"), "w"))
print("CABLES built", OUT)
