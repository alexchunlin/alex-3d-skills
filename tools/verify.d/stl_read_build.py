"""Two printed boxes with exported STLs, for cadcheck's parts check on an unreadable STL (sourced by stl_read.sh).

    cad build tools/verify.d/stl_read_build.py -- --out DIR

Writes DIR/m.blend and DIR/stl/sr_a.stl, sr_b.stl; stl_read.sh then cuts sr_a.stl short. PR #17 review: an empty or
truncated STL took cadcheck down with a traceback; it is now a parts fail naming the file, and the part's model
triangles are checked instead.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-sr-test"
A.new_scene()
for n, x in (("a", 0.0), ("b", 40.0)):
    A.part(G.box("PRT_sr_" + n, x, x + 20, 0, 20, 0, 10), "PRT_sr_" + n, 'PRT', "pla_a", stl="sr_" + n,
           print_rot=A.R_ID, orient="flat", supports="no", infill=30)
E.export_stls(os.path.join(OUT, "stl"))
E.save_blend(os.path.join(OUT, "m.blend"))
print("SR_BUILT")
