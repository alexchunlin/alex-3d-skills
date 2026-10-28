"""Two printed parts with print settings, for calcs_materials.sh: the manifest, 3MF and STL header carry them, and
cadcheck's calcs read them.

    cad build tools/verify.d/calcs_materials_build.py -- --out DIR

PRT_leaf_0/1 (one STL, qty 2) declare material PETG, 3 walls, 40 % infill, 0.16 mm layers; PRT_base declares none
(the slicer defaults apply). Also asserts asm.part refuses a material not in cadmat.MATERIALS and a fractional wall
count (prints CM_REFUSED for each).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-cm-test"
A.new_scene(params={"LOAD": 50.0, "ARM": 20.0, "B": 10.0, "H": 4.0})
flat = dict(print_rot=A.R_ID, orient="flat", supports="no")
for i in range(2):
    A.part(G.box("l%d" % i, 0, 40, 20 * i, 20 * i + 10, 20, 24), "PRT_leaf_%d" % i, 'PRT', "pla_b", stl="leaf",
           material="PETG", walls=3, infill=40, layer_h=0.16, **flat)
A.part(G.box("b", -50, -10, 0, 40, 0, 10), "PRT_base", 'PRT', "pla_a", stl="base", **flat)
for bad in (dict(material="ABS"), dict(walls=2.5)):
    try:
        A.part(G.box("x", 100, 110, 0, 10, 0, 10), "PRT_x", 'PRT', "pla_a", stl="x", **dict(flat, **bad))
        print("CM_ACCEPTED %s" % bad)
    except AssertionError as e:
        print("CM_REFUSED %s: %s" % (list(bad)[0], e))
E.export_stls(os.path.join(OUT, "stl"))
A.write_manifest(os.path.join(OUT, "manifest.json"))
E.save_blend(os.path.join(OUT, "m.blend"))
print("CM_BUILT")
