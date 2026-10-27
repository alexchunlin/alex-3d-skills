"""Hold naming and teardrop bores for cadlib.blend, run by blend_bracket.sh (not sourced).

    Blender -b --python blend_bracket_holds.py -- <skill scripts dir>

1. Two unnamed Tubes come back from measure() as tube0 and tube1. Both used to be "tube", and measure() returned one
   row (PR #4 review).
2. Two holds given the same name raise ValueError.
3. A horizontal Tube with print_up=(0, 0, 1) gets a teardrop bore: straight down it is the round bore, straight up it
   reaches r * sqrt(2) cut flat at 1.6 mm (RULES["min_wall"]) under the sleeve top, which stays closed; measure()
   still finds the 0.2 mm fit on the round part.
Prints HOLDS {...}.
"""
import json, math, sys
sys.path.insert(0, sys.argv[sys.argv.index("--") + 1])
from cadlib import asm as A, blend as B  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

A.new_scene()
out = {}
holds = [B.Tube((0, 0, 0), (40, 0, 0), 20, stop=14.2), B.Tube((0, 0, 0), (0, 40, 0), 20, stop=14.2)]
ob, _ = B.grow("names", holds, fillet=6)
m = B.measure(ob, holds)
out["names"] = sorted(m)
try:
    B.measure(ob, [B.Tube((0, 0, 0), (40, 0, 0), 20, name="t"), B.Tube((0, 0, 0), (0, 40, 0), 20, name="t")])
    out["duplicate"] = "accepted"
except ValueError as e:
    out["duplicate"] = str(e)

A.new_scene()
h = B.Tube((0, 0, 0), (40, 0, 0), 20, stop=None, print_up=(0, 0, 1))
ob, _ = B.grow("tear", [h], fillet=0)
me = ob.data
tree = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
p = Vector((20, 0, 0))
up, down = tree.ray_cast(p, Vector((0, 0, 1)), 100)[3], tree.ray_cast(p, Vector((0, 0, -1)), 100)[3]
m = B.measure(ob, [h])["tube0"]
top = tree.ray_cast(p + Vector((0, 0, up + 1e-3)), Vector((0, 0, 1)), 100)[3] if up else None   # sleeve material above the flat
out["teardrop"] = {"up_mm": round(up, 3) if up else None, "down_mm": round(down, 3), "wall_above_mm": round(top + 1e-3, 3) if top else None,
                   "expect_up": round(min(h.r_bore * math.sqrt(2), h.r_out - 1.6), 3),
                   "rays": m["rays"], "clearance": [m["clearance_min"], m["clearance_max"]], "fit_ok": m["fit_ok"]}
t = out["teardrop"]
out["ok"] = (out["names"] == ["tube0", "tube1"] and "two holds are named 't'" in out["duplicate"]
             and t["up_mm"] is not None and abs(t["up_mm"] - t["expect_up"]) < 0.05 and abs(t["down_mm"] - h.r_bore) < 0.02
             and t["wall_above_mm"] is not None and t["wall_above_mm"] >= 1.55 and t["fit_ok"])
print("HOLDS", json.dumps(out))
