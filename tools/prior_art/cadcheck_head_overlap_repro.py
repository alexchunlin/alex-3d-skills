"""Repro for a cadcheck gap: a neighbouring part overlapping a screw head above the bearing face is not flagged.

    cad build tools/prior_art/cadcheck_head_overlap_repro.py -- --out DIR
    cad check DIR/repro.blend "" DIR/cadcheck.json        # 0 fails, 0 warns (it should fail)

docs/features/fastener-joint.md, "cadcheck gap found in review", has the cadcheck lines involved.
"""
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, features as F, asm as A, export as E
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-head-overlap"
A.new_scene()
F.use_checks(None)
plate = G.box("PRT_plate", -20, 20, -10, 10, 11, 15)
block = G.box("PRT_block", -20, 20, -10, 10, 0, 11)
# a rib beside the screw: from 3.2 mm off the axis (the M4 cap head is 3.5 in radius), 0.5 mm above the bearing face
rib = G.box("PRT_rib", 3.2, 12, -6, 6, 15.5, 22)
cuts = F.fastener_joint("FST_m4", "M4", (0, 0, 15), (0, 0, -1), [plate, block], step="1")
plate = G.csg(plate, sub=cuts["PRT_plate"]); block = G.csg(block, sub=cuts["PRT_block"])
info = dict(print_rot=A.R_ID, orient="flat", supports="no", infill=30)
for o in (plate, block, rib):
    A.part(o, o.name, 'PRT', "pla_a", stl=o.name[4:], **info)
os.makedirs(OUT, exist_ok=True)
E.save_blend(os.path.join(OUT, "repro.blend"))
