"""cadlib.route regressions from the PR #3 review's adversarial scenes (/tmp/rv-pr3-work/scenes.py), kept small.
Run by route_review.sh:

    Blender -b --factory-startup --python tools/verify.d/route_review_cases.py -- <skills/print-cad-blender/scripts> <out dir>

Every moving-part case is judged independently of the router: the routed tube is measured against the moving solid
at a fine sweep (0.5 deg / 0.5 mm), not at the poses the router sampled.
- slide:   a 0..40 mm drawer (prismatic). The router used to read 0..40 as degrees and run through the extended drawer.
- thread:  an arm on +-30 deg; the straight line crosses the sector. The router used to thread between its 15 deg
           samples (the review's `wedge` / `sweep` misses), so the fine sweep must keep the clearance.
- chain:   the same arm on a tilt joint riding a pan joint (the review's `pantilt`, where pan got 3 samples).
- wheel:   a paddle on a continuous joint (swept as its spin envelope).
- wedge:   the review's scene: an end lying in the arm's sweep must raise "swept path", not route through it.
- hinge_fold / hinge_axis: a via with "joint" crossed across the hinge axis must warn of the fold (0 / 55 / 109 deg at
           0 / 55 / 110); crossed along the axis it turns 0 and doesn't warn.
- slot_2.0_viadir: a 3 mm cable forced through a 2 mm slot by a via with dir: must report violations.
- slot_5.4_via: a point via in a 5.4 mm slot: the result reaches the asked clearance or reports where it doesn't.
Prints one line: RREV {json}; writes slot_2.0_viadir.blend (for the `cad q route` exit-status test).
"""
import json, math, os, sys, time, traceback
ARGS = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, ARGS[0])
OUT = ARGS[1]
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402
from cadlib import geom as G, asm as A, export as E, route as RT  # noqa: E402

flat = dict(print_rot=A.R_ID, orient="flat", supports="no", infill=20)
R = 1.5
out = {}


def floor(s=80):
    A.part(G.box("tray", -s, s, -s, s, -3, 0), "PRT_tray", 'PRT', "pla_a", stl="tray", **flat)


def world_bvh(o):
    me = o.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    vs = [o.matrix_world @ v.co for v in me.vertices]
    fs = [tuple(p.vertices) for p in me.polygons]
    return BVHTree.FromPolygons(vs, fs)


def tube_clearance(pts, r, solid, pose_list, skip_end=3.0):
    """Min surface distance from the cable's centre line (every 0.25 mm, ends excluded) to `solid`, minus r, over
    the poses (dicts for asm.set_pose). Negative: the tube cuts the solid."""
    P = [Vector(p) for p in pts]
    S = []
    for a, b in zip(P, P[1:]):
        n = max(1, int(math.ceil((b - a).length / 0.25)))
        S += [a.lerp(b, i / n) for i in range(n)]
    S = [p for p in S if (p - P[0]).length > skip_end and (p - P[-1]).length > skip_end]
    best = (1e9, None)
    for pose in pose_list:
        A.set_pose(**pose)
        t = world_bvh(solid)
        for p in S:
            h = t.find_nearest(p, 10.0)
            if h[0] is not None:
                # inside only when the offset runs against the face normal (boxes: an edge's nearest face may come
                # back as the side face, with a float-noise dot just under 0 for a point above the top)
                d = h[3] - r if (p - h[0]).dot(h[1]) >= -0.1 * h[3] else -h[3] - r
                if d < best[0]:
                    best = (d, pose)
    A.set_pose()
    return round(best[0], 3), best[1]


def run(key, fn):
    t0 = time.time()
    try:
        out[key] = fn() or {}
    except Exception as e:
        out[key] = {"error": "%s: %s" % (type(e).__name__, e)}
        traceback.print_exc()
    out[key]["wall_s"] = round(time.time() - t0, 1)


def frange(a, b, st):
    n = int(round((b - a) / st))
    return [a + (b - a) * i / n for i in range(n + 1)]


def slide():
    A.new_scene()
    A.joint("PIV_drw", (0, 0, 0), 'X', 0, 40, prismatic=True, step=5)
    floor()
    dr = A.part(G.box("drawer", -20, 20, -10, 10, 2, 20), "PRT_drawer", 'PRT', "pla_b", joint="PIV_drw", stl="drawer", **flat)
    obs, res = RT.cable("CAB_d", (40, -30, 10), (40, 30, 10), R, "cable_red")
    c, at = tube_clearance(res["pts"], R, dr, [{"PIV_drw": v} for v in frange(0, 40, 0.5)])
    return {"fine_clearance": c, "worst_pose": at, "length_mm": res["length_mm"], "violations": len(res["violations"])}


def arm_scene(tilt=False):
    A.new_scene()
    floor(100)
    if tilt:
        A.joint("PIV_pan", (0, 0, 0), 'Z', -30, 30)
        A.joint("PIV_tilt", (0, 0, 10), 'Y', -10, 10, parent="PIV_pan")
        j = "PIV_tilt"
    else:
        A.joint("PIV_arm", (0, 0, 0), 'Z', -30, 30)
        j = "PIV_arm"
    return A.part(G.box("arm", 8, 50, -1, 1, 0.5, 18), "PRT_arm", 'PRT', "pla_b", joint=j, stl="arm", **flat)


def thread():
    arm = arm_scene()
    t = math.radians(42)
    a, b = (40 * math.cos(t), -40 * math.sin(t), 9), (40 * math.cos(t), 40 * math.sin(t), 9)
    obs, res = RT.cable("CAB_t", a, b, R, "cable_red")
    c, at = tube_clearance(res["pts"], R, arm, [{"PIV_arm": v} for v in frange(-30, 30, 0.5)])
    return {"fine_clearance": c, "worst_pose": at, "length_mm": res["length_mm"], "straight_mm": res["straight_mm"],
            "violations": len(res["violations"]), "sweep": [lg.get("sweep") for lg in res["legs"]]}


def chain_case():
    arm = arm_scene(tilt=True)
    t = math.radians(42)
    a, b = (40 * math.cos(t), -40 * math.sin(t), 9), (40 * math.cos(t), 40 * math.sin(t), 9)
    obs, res = RT.cable("CAB_c", a, b, R, "cable_red")
    poses = [{"PIV_pan": p, "PIV_tilt": q} for p in frange(-30, 30, 1.0) for q in frange(-10, 10, 2.5)]
    c, at = tube_clearance(res["pts"], R, arm, poses)
    return {"fine_clearance": c, "worst_pose": at, "length_mm": res["length_mm"], "violations": len(res["violations"]),
            "sweep": [lg.get("sweep") for lg in res["legs"]]}


def wheel():
    """a paddle on a continuous joint: swept as its spin envelope (an annulus), not sampled"""
    A.new_scene()
    floor()
    A.joint("PIV_wheel", (0, 0, 0), 'Z', continuous=True)
    pad = A.part(G.box("paddle", 5, 30, -1, 1, 10, 16), "PRT_paddle", 'PRT', "pla_b", joint="PIV_wheel", stl="paddle", **flat)
    obs, res = RT.cable("CAB_w", (-40, 10, 13), (40, 10, 13), R, "cable_red")
    c, at = tube_clearance(res["pts"], R, pad, [{"PIV_wheel": v} for v in frange(0, 359, 1.0)])
    return {"fine_clearance": c, "worst_pose": at, "length_mm": res["length_mm"], "violations": len(res["violations"]),
            "sweep": [lg.get("sweep") for lg in res["legs"]]}


def wedge():
    A.new_scene()
    A.joint("PIV_arm", (0, 0, 0), 'Z', -90, 90)
    floor()
    A.part(G.cyl("hub", (0, 0), 8, 0.5, 40, 'Z'), "PRT_hub", 'PRT', "pla_a", joint="PIV_arm", stl="hub", **flat)
    A.part(G.box("arm", 8, 70, -1, 1, 0.5, 40), "PRT_arm", 'PRT', "pla_b", joint="PIV_arm", stl="arm", **flat)
    t = math.radians(7.5)
    try:
        RT.route((45 * math.cos(t), 45 * math.sin(t), 13), (64 * math.cos(t), 64 * math.sin(t), 13), R)
        return {"raised": None}
    except RuntimeError as e:
        return {"raised": str(e)}


def hinge(vdir):
    A.new_scene()
    A.joint("PIV_lid", (0, 0, 20), 'X', 0, 110, step=10)
    floor()
    A.part(G.box("base", -30, 30, -40, -4, 0, 18), "PRT_base", 'PRT', "pla_a", stl="base", **flat)
    A.part(G.box("lid", -30, 30, 4, 40, 18, 22), "PRT_lid", 'PRT', "pla_b", joint="PIV_lid", stl="lid", **flat)
    # 55 deg is a sample of its own, so the crossing row's limits plus 55 can be compared with the review's numbers
    via = {"at": (20, 0, 20), "joint": "PIV_lid", "dir": vdir, "len": 4}
    res = RT.route((20, -30, 21) if vdir[1] else (-20, -30, 21), (20, 30, 25), R, via=[via], quiet=True)
    cr = res["crossings"][0] if res["crossings"] else {}
    return {"turn_deg": cr.get("turn_deg"), "on_axis": cr.get("on_axis"), "warn": [w for w in res["warnings"] if "folds" in w],
            "slack": [s["slack_mm"] for s in res["slack"]]}


def slot(W, mode):
    A.new_scene()
    floor()
    wall = G.csg(G.box("wall", -2, 2, -60, 60, 0, 40), sub=[G.box("slot", -3, 3, 15 - W / 2, 15 + W / 2, -1, 8)])
    A.part(wall, "PRT_wall", 'PRT', "pla_b", stl="wall", **flat)
    via = [{"at": (0, 15, 4), "dir": (1, 0, 0), "len": 6}] if mode == "viadir" else [(0, 15, 4)]
    obs, res = RT.cable("CAB_s", (-40, 0, 4), (40, 0, 4), R, "cable_red", via=via, quiet=True)
    c, _ = tube_clearance(res["pts"], R, bpy.data.objects["PRT_wall"], [{}])
    return {"violations": len(res["violations"]), "worst": min([v["clearance_mm"] for v in res["violations"]] or [None], key=lambda x: x if x is not None else 1e9),
            "min_clearance_mm": res["min_clearance_mm"], "asked": res["clearance_asked_mm"], "fine_clearance": c,
            "warned": any("under the requested" in w for w in res["warnings"])}


run("slide", slide)
run("thread", thread)
run("chain", chain_case)
run("wheel", wheel)
run("wedge", wedge)
run("hinge_fold", lambda: hinge((0, 1, 0)))
run("hinge_axis", lambda: hinge((1, 0, 0)))
run("slot_5.4_via", lambda: slot(5.4, "via"))
run("slot_2.0_viadir", lambda: slot(2.0, "viadir"))
os.makedirs(OUT, exist_ok=True)
E.save_blend(os.path.join(OUT, "slot_2.0_viadir.blend"))
print("RREV " + json.dumps(out, default=str))
