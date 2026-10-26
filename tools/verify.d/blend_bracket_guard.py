"""Size guard check for blend.grow and geom.swept_envelope, run by blend_bracket.sh (not sourced).

    Blender -b --python blend_bracket_guard.py -- <skill scripts dir>

Asks for a 300 x 250 x 250 mm grown part at voxel 0.5 (190M cells) and a 300 mm arm swept at voxel 0.25 (76M).
Both must raise blend.GridTooLarge, naming the smallest voxel that fits, before anything big is allocated: peak RSS
may grow by at most 150 MB and each refusal must take under 2 s. Prints GUARD {...}.
"""
import json, resource, sys, time
sys.path.insert(0, sys.argv[sys.argv.index("--") + 1])
from cadlib import asm as A, blend as B, geom as G  # noqa: E402

A.new_scene()
rss = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2 ** 20   # macOS: bytes
out = {}
r0 = rss()
t0 = time.time()
try:
    B.grow("big", [B.Tube((0, 0, 0), (300, 0, 0), 20, stop=20)], extra=[B.rbox((150, 0, 0), (300, 250, 250), r=5)], voxel=0.5)
    out["grow"] = "built (guard missing)"
except B.GridTooLarge as e:
    out["grow"] = str(e)
out["grow_t_s"] = round(time.time() - t0, 2)
arm = G.box("arm", 0, 300, -5, 5, 0, 10)
t0 = time.time()
try:
    G.swept_envelope([arm], (0, 0, 0), (0, 0, 1), 0, 90, voxel=0.25)
    out["sweep"] = "built (guard missing)"
except B.GridTooLarge as e:
    out["sweep"] = str(e)
out["sweep_t_s"] = round(time.time() - t0, 2)
out["rss_growth_MB"] = round(rss() - r0, 1)
out["ok"] = ("GridTooLarge" not in out["grow"] and "smallest voxel that fits" in out["grow"] and "smallest voxel that fits" in out["sweep"]
             and out["rss_growth_MB"] < 150 and out["grow_t_s"] < 2 and out["sweep_t_s"] < 2)
print("GUARD", json.dumps(out))
