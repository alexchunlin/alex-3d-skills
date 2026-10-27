"""Test assembly for cadcheck's head and nut overlap test (sourced by tools/verify.d/fastener_overlap.sh).

    cad build tools/verify.d/fastener_overlap_build.py -- --out /tmp/alex3d-verify/fo

M4 joints through a 4 mm plate on an 11 mm block, one per 40 mm along x, all on the static body. Writes fo.blend and
checks.json (one captive nut, nuts_ok for every nut here so the visible-nut warn stays out of the counts).
Must fail:
  FST_fo_nut_nut   nut on the block's far face; PRT_fo_piston beside it, 3.0 mm off the axis (the nut's flats are at
                   3.5): the push-assist A2 stop nut in the piston (PA-A2-T12)
  FST_fo_buried    a nut inside a solid printed block with no pocket
  FST_fo_press_nut a nut in a hex pocket 0.3 mm under its width across flats; passes only through its captive entry
                   (fails in the run without checks.json)
Must warn:
  FST_fo_graze     cap head with a rib 3.4 mm off the axis, 0.5 mm above the bearing face: 0.2 mm3 at one corner
Must pass (no overlap finding):
  FST_fo_cb        cap head counterbored 3 mm into an 8 mm plate, with a rib 0.2 mm clear of the head above it
  FST_fo_trap      through-bolt, nut in the hex trap fastener_joint cuts
  FST_fo_rot       the same with nut_rot_deg=30: asm.nut is not turned with the trap, so its corners stand 0.44 mm
                   into the pocket's walls (as the v2 flywheel and thumbwheel nuts); the nut probe is its inscribed
                   cylinder, which any hex pocket at least its width across flats clears
  FST_fo_slot      nut dropped into a side-entry slot (features.nut_trap slot_dir), not declared captive
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, features as F, asm as A, export as E

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-fo-test"
DOWN = (0, 0, -1)
INFO = dict(print_rot=A.R_ID, orient="flat", supports="no", infill=30)
A.new_scene()
F.use_checks(None)
parts = []


def stack(tag, x, plate_t=4.0):
    plate = G.box("PRT_fo_%s_plate" % tag, x - 15, x + 15, -10, 10, 11, 11 + plate_t)
    block = G.box("PRT_fo_%s_block" % tag, x - 15, x + 15, -10, 10, 0, 11)
    return plate, block


def done(cuts, *obs):
    for o in obs:
        o = G.csg(o, sub=cuts.get(o.name, []))
        parts.append(o)


# counterbored cap head, and a rib 0.2 mm clear of the head's rim above the plate
x = 0.0
plate, block = stack("cb", x, 8.0)
done(F.fastener_joint("FST_fo_cb", "M4", (x, 0, 16.0), DOWN, [plate, block], sink=3.0, through_ok=True), plate, block)
parts.append(G.box("PRT_fo_cb_rib", x + 3.7, x + 12, -6, 6, 19.0, 24))
# through-bolt, nut in its trap; the same with the trap turned 30 deg
for tag, x, rot in (("trap", 40.0, 0.0), ("rot", 80.0, 30.0)):
    plate, block = stack(tag, x)
    done(F.fastener_joint("FST_fo_" + tag, "M4", (x, 0, 15), DOWN, [plate, block], style="nut", nut_rot_deg=rot), plate, block)
# nut on the block's far face, a piston 3.0 mm off the axis beside it (the nut runs z 0 .. -3.2)
x = 120.0
plate, block = stack("nut", x)
done(F.fastener_joint("FST_fo_nut", "M4", (x, 0, 15), DOWN, [plate, block], style="nut", trap=False), plate, block)
parts.append(G.box("PRT_fo_piston", x + 3.0, x + 12, -6, 6, -2.8, -0.4))
# a nut inside a solid block, no pocket
x = 160.0
parts.append(G.box("PRT_fo_solid", x - 10, x + 10, -10, 10, 0, 11))
A.nut("FST_fo_buried", (x, 0, 7.0), DOWN, size="M4")
# cap head grazed by a rib at one corner of its 16-gon
x = 200.0
plate, block = stack("graze", x)
done(F.fastener_joint("FST_fo_graze", "M4", (x, 0, 15), DOWN, [plate, block]), plate, block)
parts.append(G.box("PRT_fo_graze_rib", x + 3.4, x + 12, -6, 6, 15.5, 22))
# side-entry slot (captive by shape) and a pressed nut (captive by declaration): bolt from the top, nut bearing
# face 6 mm (slot) / 3.5 mm (press) above the block's bottom, facing down
for tag, x, nf, af, slot in (("slot", 240.0, 6.0, None, (1, 0, 0)), ("press", 280.0, 3.5, 6.7, None)):
    plate, block = stack(tag, x)
    L = 14 if tag == "slot" else 16
    hole = lambda: F.screw_hole((x, 0, 15), DOWN, L, "clearance", head="cap", size="M4", name="fo_%s" % tag)
    trap = F.nut_trap((x, 0, nf), DOWN, depth=nf + 0.6 if tag == "press" else 3.5, af=af, slot_dir=slot,
                      slot_len=16.0 if slot else 0.0, size="M4", name="fo_%s_nut" % tag)
    parts += [G.csg(plate, sub=hole()), G.csg(block, sub=hole() + trap)]
    A.fastener("FST_fo_%s" % tag, (x, 0, 15), DOWN, L, spec="M4_cap")
    A.nut("FST_fo_%s_nut" % tag, (x, 0, nf), DOWN, size="M4")
for o in parts:
    A.part(o, o.name, 'PRT', "pla_a", stl=o.name[4:], **INFO)
os.makedirs(OUT, exist_ok=True)
E.save_blend(os.path.join(OUT, "fo.blend"))
with open(os.path.join(OUT, "checks.json"), "w") as f:
    json.dump({"fasteners": {"captive": {"FST_fo_press_nut": "pressed into a hex pocket 0.3 mm under its width; the screw turns"}},
               "exposure": {"nuts_ok": ["FST_fo_*"]}}, f, indent=1)
print("FO_BUILT", len(parts), "parts")
