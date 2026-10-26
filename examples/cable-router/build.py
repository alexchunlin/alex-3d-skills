"""Synthetic scene for cadlib.route: a tray split by a wall with one floor slot, a block in the way, and a
turntable whose centre bore a second cable must use to cross the joint.

    Blender -b --python build.py -- [--out /tmp/alex3d-cr-demo]

Writes route.blend and route.json (both route() results). The straight line from A to B runs through the
block and the wall, so a route that clears them with the asked clearance and passes the slot via is a router,
not a straight-line fallback. tools/verify.d/cable_router.sh asserts on route.json and runs cadcheck.
"""
import bpy, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, export as E, route as RT

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-cr-demo"
R_CAB = 1.5
CLEAR = 1.0
SLOT = (10.0, 20.0, 8.0)          # y0, y1, height of the slot in the wall at x = 0
TT = (70.0, 0.0, 20.0)            # turntable axis (x, y) and deck height

A.new_scene(params={k: v for k, v in globals().items() if k.isupper()})
A.joint("PIV_turn", (TT[0], TT[1], 0), 'Z', -90, 90, step=15)
flat = dict(stl="x", print_rot=A.R_ID, orient="flat", supports="no", infill=20)
A.part(G.box("tray", -60, 100, -40, 40, -3, 0), "PRT_tray", 'PRT', "pla_a", **dict(flat, stl="tray"))
wall = G.box("wall", -2, 2, -40, 40, 0, 40)
wall = G.csg(wall, sub=[G.box("slot", -3, 3, SLOT[0], SLOT[1], -1, SLOT[2])])
A.part(wall, "PRT_wall", 'PRT', "pla_b", **dict(flat, stl="wall"))
A.part(G.box("block", -35, -15, -18, 18, 0, 30), "BUY_block", 'BUY', "buy", mass_g=50, src="synthetic obstacle")
deck = G.cyl("deck", (TT[0], TT[1]), 25, TT[2], TT[2] + 4, 'Z')
deck = G.csg(deck, sub=[G.cyl("bore", (TT[0], TT[1]), 6, TT[2] - 1, TT[2] + 5, 'Z')])
A.part(deck, "PRT_deck", 'PRT', "pla_b", joint="PIV_turn", **dict(flat, stl="deck"))
A.part(G.cyl("post", (TT[0], TT[1] - 18), 4, 1, TT[2], 'Z'), "PRT_post", 'PRT', "pla_a", joint="PIV_turn", **dict(flat, stl="post"))

out = {}
# 1: around the block and through the slot (via with a direction: a straight run through the wall)
obs, out["slot"] = RT.cable("CAB_slot", (-50, 0, 3), (40, -20, 3), R_CAB, "cable_red",
                            via=[{"at": (0, 15, 4), "dir": (1, 0, 0), "len": 6}], clearance=CLEAR)
# 2: from the tray up through the turntable bore onto the deck: one piece per body, slack across PIV_turn
obs, out["bore"] = RT.cable("CAB_bore", (40, 25, 3), (85, -10, TT[2] + 6), R_CAB, "cable_wht",
                            via=[{"at": (TT[0], TT[1], TT[2] + 2), "dir": (0, 0, 1), "len": 8, "joint": "PIV_turn"}],
                            clearance=CLEAR)
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "route.json"), "w") as f:
    json.dump(out, f, indent=1)
E.save_blend(os.path.join(OUT, "route.blend"))
for k, v in out.items():
    print("ROUTE", k, json.dumps({x: v[x] for x in ("length_mm", "straight_mm", "min_clearance_mm", "bend_r_min",
                                                      "sharp_corners", "exposed_mm", "stubs", "slack", "time_s")}))
