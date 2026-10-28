"""Test assembly for slide_out rows through allowed pairs (sourced by tools/verify.d/slide_allow.sh).

    cad build tools/verify.d/slide_allow_build.py -- --out /tmp/alex3d-verify/sa

The push-assist A7 load cell, reduced: a bought "cell" with a Ø4.9 stud seated with zero gap on a printed cartridge
block, the stud in a 5.5 mm slot that runs up-inboard at 45 deg. Every row slides the cell along the slot, (-1, 0, 1).
One case per 100 mm along x, all on the static body. Writes sa.blend and checks.json.
  short  the a7 slot: its end is offset by the stud's depth along both axes, so a wedge of material is left over the
         lower half of the exit; allowed 3 mm3 (the a7 config). Must fail past the allow (PA-A7-T19a)
  fixed  the a8 slot, run past the face by its half width plus 1 mm; the same allow. Must pass, and the allow, at
         0 mm3 everywhere, is listed as unused (PA-A8-T6)
  crush  no slot: a 4 x 4 mm crush pad 0.1 mm into the cartridge face (1.6 mm3), allowed 3 mm3. Must pass, riding
         within the allow, and the allow is used
  nut    a nut on the stud, bored to the stud, allowed with no max_mm3. Pulled off along the stud: must pass; moved
         sideways with the nut left behind: must be blocked by the nut
plus an allow that covers no pair (stale).
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-sa-test"
INFO = dict(print_rot=A.R_ID, orient="flat", supports="no", infill=30)
CZ, HALF, STUD_R = -15.0, 2.75, 2.45      # stud axis height, slot half width, M5 stud radius (4.9 / 2)
A.new_scene()
printed, bought = [], []


def cartridge(tag, x, d=None):
    """40 x 20 x 30 block, top face z 0, front face (the cell's seat) y 10; a slot from 3 mm behind the stud axis
    up-inboard at 45 deg, its end offset d from the axis in x and in z (none: no slot)."""
    o = G.box("PRT_sa_%s_cart" % tag, x - 20, x + 20, -10, 10, -30, 0)
    if d is not None:
        e, k = 3.0, HALF / math.sqrt(2)
        slot = G.prism("slot", [(x + k + e, CZ + k - e), (x - k + e, CZ - k - e), (x - k - d, CZ - k + d), (x + k - d, CZ + k + d)],
                       -11, 11, 'Y')
        o = G.csg(o, sub=[slot])
    printed.append(o)


def cell(tag, x, stud=True, y0=10.0, w=6.0):
    """The cell's end block in front of the seat face (y y0 .. 20), and its stud 15 mm into the cartridge."""
    o = G.box("BUY_sa_%s_cell" % tag, x - w, x + w, y0, 20, CZ - w, CZ + w)
    if stud:
        o = G.csg(o, add=[G.cyl("stud", (x, CZ), STUD_R, -5, y0 + 0.5, 'Y', n=32)])
    bought.append(o)


cartridge("short", 0.0, d=-CZ)                       # a7: 15 along each axis, a wedge over the lower half of the exit
cell("short", 0.0)
cartridge("fixed", 100.0, d=-CZ + HALF + 1.0)        # a8: past the face by the half width plus 1 mm
cell("fixed", 100.0)
cartridge("crush", 200.0)
cell("crush", 200.0, stud=False, y0=9.9, w=2.0)      # 4 x 4 pad, 0.1 into the face: 1.6 mm3
x = 300.0                                             # the nut case: a cell and its stud in free air, a nut on the stud
cell("nut", x)
r = 8.0 / 2 / math.cos(math.pi / 6)
bought.append(G.csg(G.cyl("BUY_sa_nut_nut", (x, CZ), r, 0, 4, 'Y', n=6), sub=[G.cyl("bore", (x, CZ), STUD_R, -1, 5, 'Y', n=32)]))
for o in printed:
    A.part(o, o.name, 'PRT', "pla_a", stl=o.name[4:], **INFO)
for o in bought:
    A.part(o, o.name, 'BUY', "buy", mass_g=20, src="test block")
os.makedirs(OUT, exist_ok=True)
E.save_blend(os.path.join(OUT, "sa.blend"))
UP = [-0.7071, 0, 0.7071]
row = lambda tag, **k: dict({"name": "%s: the cell out along the slot" % tag, "object": "BUY_sa_%s_cell" % tag, "dir": UP, "dist": 40,
                             "step": 1, "min_clearance": 0.0}, **k)
with open(os.path.join(OUT, "checks.json"), "w") as f:
    json.dump({"allow": [{"a": "PRT_sa_short_cart", "b": "BUY_sa_short_cell", "max_mm3": 3, "why": "zero-gap seat (the a7 allow)"},
                         {"a": "PRT_sa_fixed_cart", "b": "BUY_sa_fixed_cell", "max_mm3": 3, "why": "zero-gap seat"},
                         {"a": "PRT_sa_crush_cart", "b": "BUY_sa_crush_cell", "max_mm3": 3, "why": "crush pad, 1.6 mm3"},
                         {"a": "BUY_sa_nut_nut", "b": "BUY_sa_nut_cell", "why": "nut on its stud"},
                         {"a": "BUY_sa_gone", "b": "PRT_*", "why": "a part since removed"}],
               "slide_out": [row("short"), row("fixed"), row("crush"),
                             row("nut", name="nut: the cell pulled off its nut along the stud", dir=[0, 1, 0], dist=30),
                             row("nut", name="nut: the cell out sideways with its nut left on", dist=10)]}, f, indent=1)
print("SA_BUILT", len(printed) + len(bought), "parts")
