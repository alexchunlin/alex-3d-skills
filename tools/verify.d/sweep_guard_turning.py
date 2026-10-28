"""cadcheck.turning: the subdivision the PR #21 review asked a case for (run by sweep_guard.sh).

    Blender -b --factory-startup --python tools/verify.d/sweep_guard_turning.py -- <skills/print-cad-blender/scripts>

A 2 mm blade (r 8..60, two triangles a face) turns 0..2 deg about Z; a r 1.4 post stands at 9 deg, r 40. The blade's
coarse triangles span 7.1 deg each side of it (their corners at r 8), so their boxes meet the post's (7..11 deg) once
widened by the turn; cut four times, the pieces near r 40 span about 1.5 deg and clear it (the real gap is about 3.5 mm).
Prints TURN {json}: depth 0 must leave the turn unproven, depth 4 must prove it; a post moved to 2.5 deg (inside the
blade's path) must stay unproven at any depth.
"""
import json, math, os, sys
ARGS = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, ARGS[0])
os.environ["CADCHECK_NO_MAIN"] = "1"
import bpy  # noqa: E402
from cadlib import geom as G, asm as A  # noqa: E402

flat = dict(print_rot=A.R_ID, orient="flat", supports="no", infill=20)
A.new_scene()
A.part(G.box("blade", 8, 60, -1, 1, 0, 10), "PRT_blade", 'PRT', "pla_b", stl="blade", **flat)
out = {}
for deg in (9.0, 2.5):
    t = math.radians(deg)
    A.part(G.cyl("post", (40 * math.cos(t), 40 * math.sin(t)), 1.4, 2, 8, n=24), "PRT_post_%g" % deg, 'PRT', "pla_a", stl="post%g" % deg, **flat)
bpy.context.view_layer.update()
import cadcheck as C  # noqa: E402
O = bpy.data.objects
for deg in (9.0, 2.5):
    p = O["PRT_post_%g" % deg]
    for depth in (0, 4):
        out["post%g_depth%d" % (deg, depth)] = C.turning(O["PRT_blade"], p, (0, 0, 0), (0, 0, 1), depth=depth)(0.0, math.radians(2.0))
print("TURN " + json.dumps(out))
