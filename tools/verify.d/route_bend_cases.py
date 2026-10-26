"""cadlib.route fillets vs cadcheck's kink test. Run in Blender:

    Blender -b --factory-startup --python tools/verify.d/route_bend_cases.py -- <skills/print-cad-blender/scripts>

cadcheck's `cables` kink test (_bends) skips turns under 20 deg, so it never sees an arc the router drew in 10 deg
steps, however tight. The router must therefore draw no arc under min_bend_od x OD and start no arc within one OD
of an end at a plug; such a corner stays sharp, where the kink test sees it. Prints one IBEND JSON line.
"""
import json, math, sys
sys.path.insert(0, sys.argv[sys.argv.index("--") + 1])
from mathutils import Vector
from cadlib import route as RT

r = 1.5
od, floor = 2 * r, 0.75 * 2 * r
P = [Vector(p) for p in ((0, 0, 0), (20, 0, 0), (20, 20, 0), (40, 20, 0))]   # two 90 deg corners, 20 mm legs


def true_min_radius(pts):
    rs = []
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        A = (b - a).cross(c - a).length / 2
        if A > 1e-9:
            rs.append((b - a).length * (c - b).length * (c - a).length / (4 * A))
    return min(rs) if rs else None


def sharp(pts):
    """vertices cadcheck's _bends would test (turn >= 20 deg)"""
    return sum(1 for i in range(1, len(pts) - 1) if (pts[i] - pts[i - 1]).angle(pts[i + 1] - pts[i]) >= math.radians(20))


out = {}
for bend in (7.5, 1.0):     # the default 5 r, and one asked under the floor
    pts, R = RT.fillet(P, bend, lambda q, i: True, r_min=floor, lead=(od, od))
    out["bend_%g" % bend] = {"radii": [round(x, 2) for x in R], "true_min": true_min_radius(pts), "sharp": sharp(pts)}
# an end corner with a 2 mm first leg: no room for one OD of lead plus an arc, so it stays sharp
pts, R = RT.fillet([Vector(p) for p in ((0, 0, 0), (2, 0, 0), (2, 30, 0))], 7.5, lambda q, i: True, r_min=floor, lead=(od, od))
out["end_corner"] = {"radii": [round(x, 2) for x in R], "sharp": sharp(pts)}
# a corner whose arc cannot keep clearance at any radius >= the floor: shrinks to sharp, not to 0.5 mm
pts, R = RT.fillet(P, 7.5, lambda q, i: False, r_min=floor, lead=(od, od))
out["no_clearance"] = {"radii": [round(x, 2) for x in R], "sharp": sharp(pts)}
out["floor"] = floor
print("IBEND " + json.dumps(out))
