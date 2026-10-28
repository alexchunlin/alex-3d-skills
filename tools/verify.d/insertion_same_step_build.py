"""Test assembly for cadcheck's insertion order within a step (sourced by tools/verify.d/insertion_same_step.sh).

    cad build tools/verify.d/insertion_same_step_build.py -- --out /tmp/alex3d-verify/iss

The push-assist cartridge and load cell (PA-A7-T7, T19), reduced: a U-channel cartridge (base plate, two end walls)
and a cell (25 mm body, Ø5 studs out of both ends, 37 mm over the studs) standing on the base plate, its studs in the
end walls.
  a6  round Ø5.5 stud holes: no straight way in at all (the A6 cell nobody could fit)
  a7  45 deg stud slots that stop inside the wall (A7's slot ended 0.2 mm short of the face): still no way in
  a8  45 deg stud slots out through the wall's corner (A8): in only along [-1, 0, 1], up-inboard
Trays, a bought board on the floor of the tray's pocket and a lid over it:
  lid  listed tray, lid, board: only tray, board, lid works
  ok   listed tray, board, lid
  tie  tray and board on one glob ("*_tie_*")
Each case is its own bench group, so the lanes of one never reach another's parts.

checks.json is the A7 shape: each cartridge and its cell in one step, with the A7 allow (cartridge x cell, max_mm3 3)
that also hid the cell from slide rows; the trays without an "order". checks_order.json gives the tray steps an
"order": the lid's wrong, the tie's one glob, ok's with a typo'd glob. checks_fixed.json is the A8 shape: cartridge,
then the cell in its own step (a8 with "insert_dirs"), the lid step in its right "order".
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-iss-test"
INFO = dict(print_rot=A.R_ID, orient="flat", supports="no", infill=30)
A.new_scene()
R_STUD, R_HOLE = 2.5, 2.75


def cartridge(tag, x, hole):
    """Base plate under the cell and two 5 mm end walls (y 13..18 each side) with the stud holes cut by `hole`."""
    base = G.box("PRT_%s_cartridge" % tag, x - 10, x + 10, -18, 18, -10, -6.5)
    walls = [G.box("w%d" % k, x - 10, x + 10, y0, y0 + 5, -6.6, 10) for k, y0 in enumerate((-18, 13))]
    o = G.csg(base, add=walls)
    return G.csg(o, sub=hole(x))


def cell(tag, x):
    body = G.box("BUY_%s_cell" % tag, x - 6, x + 6, -12.5, 12.5, -6.5, 6.5)
    return G.csg(body, add=[G.cyl("stud_r", (x, 0), R_STUD, 12, 18.6, 'Y'), G.cyl("stud_f", (x, 0), R_STUD, -18.6, -12, 'Y')])


def slot(x, reach):
    """Ø5.5 stadium from the stud axis out along (-1, +1) in x, z for `reach` mm, through both walls."""
    e = reach / math.sqrt(2)
    return [G.prism("slot", G.hull_circles([((x, 0), R_HOLE), ((x - e, e), R_HOLE)]), -19, 19, 'Y')]


parts, buy = [], []
parts.append(cartridge("a6", 0.0, lambda x: [G.cyl("hole", (x, 0), R_HOLE, -19, 19, 'Y')]))
parts.append(cartridge("a7", 100.0, lambda x: slot(x, 9.0)))     # the end circle stays 2.4 mm inside the corner
parts.append(cartridge("a8", 200.0, lambda x: slot(x, 20.0)))    # past the wall's corner (14.1 along the slot)
buy += [cell("a6", 0.0), cell("a7", 100.0), cell("a8", 200.0)]
for tag, x in (("lid", 300.0), ("ok", 400.0), ("tie", 500.0)):
    parts.append(G.csg(G.box("PRT_%s_tray" % tag, x - 20, x + 20, -15, 15, 0, 10), sub=[G.box("pk", x - 16, x + 16, -11, 11, 3, 10.5)]))
    buy.append(G.box("BUY_%s_board" % tag, x - 15, x + 15, -10, 10, 3, 5))
    if tag != "tie":
        parts.append(G.box("PRT_%s_lid" % tag, x - 20, x + 20, -15, 15, 10, 12))
for o in parts:
    A.part(o, o.name, 'PRT', "pla_a", stl=o.name[4:], **INFO)
for o in buy:
    A.part(o, o.name, 'BUY', "buy", mass_g=20, src="test block")
os.makedirs(OUT, exist_ok=True)
E.save_blend(os.path.join(OUT, "iss.blend"))
allow = [{"a": "PRT_*_cartridge", "b": "BUY_*_cell", "max_mm3": 3.0, "why": "push-assist A7's seat allow (zero-gap seats)"}]
trays = lambda **o: [dict({"step": "%s tray, board, lid" % t, "bench": t, "objects": g}, **({"order": o[t]} if t in o else {}))
                     for t, g in (("lid", ["PRT_lid_tray", "PRT_lid_lid", "BUY_lid_board"]), ("ok", ["PRT_ok_tray", "BUY_ok_board", "PRT_ok_lid"]),
                                  ("tie", ["*_tie_*"]))]
a7 = {"allow": allow, "assembly_order": [
    {"step": "%s cartridge: cell, nuts, stops (bench)" % t, "bench": t, "objects": ["PRT_%s_cartridge" % t, "BUY_%s_cell" % t]}
    for t in ("a6", "a7", "a8")] + trays()}
order = {"assembly_order": [{"step": "cartridges", "objects": ["*_a?_*"], "insert_ok": "tested under checks.json"}] + trays(lid=["PRT_lid_tray", "PRT_lid_lid", "BUY_lid_board"], tie=["*_tie_*"],
                                 ok=["PRT_ok_tray", "BUY_ok_board", "PRT_ok_lid", "PRT_ok_lidd"])}
a8 = {"allow": allow, "assembly_order": [
    s for t in ("a6", "a7", "a8") for s in (
        {"step": "%s cartridge, empty (bench)" % t, "bench": t, "objects": ["PRT_%s_cartridge" % t]},
        dict({"step": "%s cell in along the stud slots" % t, "bench": t, "objects": ["BUY_%s_cell" % t]},
             **({"insert_dirs": [[-0.7071, 0, 0.7071]]} if t == "a8" else {})))] + trays(lid=["PRT_lid_tray", "BUY_lid_board", "PRT_lid_lid"])}
for fn, cfg in (("checks.json", a7), ("checks_order.json", order), ("checks_fixed.json", a8)):
    with open(os.path.join(OUT, fn), "w") as f:
        json.dump(cfg, f, indent=1)
print("ISS_BUILT", len(parts), "printed", len(buy), "bought")
