"""Review regressions for features.fastener_joint (sourced by tools/verify.d/fastener_joint.sh).

    cad build tools/verify.d/fastener_joint_review.py -- --out /tmp/alex3d-verify/fj/review

The independent review's adversarial cases, each as one line "FJR <tag>: <result>":
  board        M2.5 through a purchased board with its own Ø2.7 hole into a printed boss (v2 MotorGo, 4 x M2.5):
               the board is a pre-drilled layer, counted in the grip and not cut
  sloped       head on a 12 deg sloped face, and on a flat face with a 10 deg axis: raise "not flat", suggest sink=;
               the suggested spot-face then builds
  blind        self-tap into a boss too shallow for a blind hole: raise "too shallow", through_ok=True builds;
               a deep enough boss keeps min_wall under the pilot (measured in the cut mesh)
  buy_selftap  style="selftap" into a purchased part: raise, pointing to style="tapped"
  gap          0.5 mm of air between the clamped plate and the host: raise; gap_ok=True builds
  csk          countersunk M5 in a 2 mm plate: raise "knife edge"
  reuse        a second joint whose window holds the first's length takes it; lengths= and a project checks.json
               stock_lengths / min_engagement are honoured
  m2_2d        M2 self-tap with exactly 2 d (4.0 mm) of thread, kept for the cadcheck run (no engagement warn)
  rules        the engagement table (2 d printed, 1.5 d tapped purchased) and the M2 / M2.5 holes
The kept joints are saved to fjr.blend for `cad check`; fjr_report.json has their records.
"""
import json, math, os, re, sys
import bpy
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, features as F, asm as A, export as E
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-fjr-test"
os.makedirs(OUT, exist_ok=True)
DOWN = (0, 0, -1)
INFO = dict(print_rot=A.R_ID, orient="flat", supports="no", infill=30)


def say(tag, ok, msg):
    print("FJR %s %s: %s" % ("PASS" if ok else "FAIL", tag, msg))


def raises(tag, want, **kw):
    """Run fastener_joint expecting a FastenerError whose message matches `want`; returns the message."""
    try:
        F.fastener_joint(**kw)
        say(tag, False, "NOT RAISED")
        return ""
    except F.FastenerError as e:
        say(tag, re.search(want, str(e)) is not None, str(e))
        return str(e)


def kill(*obs):
    for o in obs:
        G.kill(o)


A.new_scene()
F.use_checks(None)          # this script has no project checks.json; the project case sets one below
keep = {}                   # part name -> (object, kind) kept for the cadcheck run
cuts = {}

# ---- rules: the engagement table and the M2 / M2.5 holes
eng = {s: (F.size_rules(s)["min_engagement"], F.size_rules(s)["tapped_engagement"]) for s in F.SIZES}
want = {"M2": (4.0, 3.0), "M2.5": (5.0, 3.75), "M3": (6.0, 4.5), "M4": (8.0, 6.0), "M5": (10.0, 7.5)}
say("rules", eng == want, "engagement printed/tapped %s" % eng)
h = {s: (F.size_rules(s)["clear_d"], F.size_rules(s)["pilot_d"], F.size_rules(s)["pan"]) for s in ("M2", "M2.5")}
say("rules", h == {"M2": (2.4, 1.7, (4.0, 1.6)), "M2.5": (2.9, 2.1, (5.0, 2.1))}, "M2 / M2.5 clear, pilot, pan %s" % h)

# ---- board: purchased 1.6 mm board with Ø2.7 holes on printed bosses (MotorGo pattern, 4 x M2.5)
X = 0.0
base = G.box("PRT_fjr_mount", X - 20, X + 20, -15, 15, 0.0, 3.0)
bosses = [G.cyl("b%d" % i, (X + sx * 12, sy * 8), 3.0, 2.9, 12.0, 'Z') for i, (sx, sy) in
          enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1)))]
base = G.csg(base, add=bosses)
board = G.box("BUY_fjr_board", X - 16, X + 16, -11, 11, 12.0, 13.6)
board = G.csg(board, sub=[G.cyl("h%d" % i, (X + sx * 12, sy * 8), 1.35, 11, 15, 'Z') for i, (sx, sy) in
                          enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1)))])
for i, (sx, sy) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
    F.fastener_joint("FST_fjr_board_%d" % i, "M2.5", (X + sx * 12, sy * 8, 13.6), DOWN, [board, base], step="1", cuts=cuts)
r = A.PARTS["FST_fjr_board_0"]["fastener_joint"]
ok = (r["stack"][0][0] == "BUY_fjr_board" and r["stack"][0][-1] == "clear" and r["grip_mm"] == 1.6
      and cuts["BUY_fjr_board"] == [] and r["length"] == 8 and r["engagement_mm"] >= 5.0)
say("board", ok, "stack %s, grip %s, M2.5 x %g, thread %.2f, board cuts %d" % (
    r["stack"], r["grip_mm"], r["length"], r["engagement_mm"], len(cuts["BUY_fjr_board"])))
base = G.csg(base, sub=cuts.pop("PRT_fjr_mount"))
cuts.pop("BUY_fjr_board")
keep["PRT_fjr_mount"], keep["BUY_fjr_board"] = (base, "PRT"), (board, "BUY")

# ---- sloped: a 12 deg face, and a 10 deg axis on a flat face
X = 60.0
slab = G.box("PRT_fjr_slope", X - 15, X + 15, -10, 10, -6, 6)       # 12 mm slab, top face sloped 12 deg
G.xform(slab, Matrix.Translation((X, 0, 10)) @ Matrix.Rotation(math.radians(12), 4, 'Y') @ Matrix.Translation((-X, 0, 0)))
tree, _ = F._bvh(slab)
top = tree.ray_cast(Vector((X, 0, 50)), Vector((0, 0, -1)))[0]
msg = raises("sloped", r"not flat.*head buried.*pass sink=", name="FST_fjr_slope", size="M3", at=top, into=DOWN,
             parts=[slab])
m = re.search(r"move `at` ([\d.]+) mm along `into` and pass sink=([\d.]+)", msg)
if m:
    at2 = top + Vector(DOWN) * float(m.group(1))
    F.fastener_joint("FST_fjr_slope", "M3", at2, DOWN, [slab], sink=float(m.group(2)), step="1", cuts=cuts)
    r = A.PARTS["FST_fjr_slope"]["fastener_joint"]
    say("sloped", True, "suggested spot-face builds: at +%s, sink=%s, M3 x %g" % (m.group(1), m.group(2), r["length"]))
    slab = G.csg(slab, sub=cuts.pop(slab.name))
    keep[slab.name] = (slab, "PRT")
else:
    say("sloped", False, "no sink suggestion in the message")
flat = G.box("PRT_fjr_tilt", X - 15, X + 15, 30, 50, 0, 4)
tilt = Vector((math.sin(math.radians(10)), 0, -math.cos(math.radians(10))))
raises("tilted_axis", r"not flat", name="FST_fjr_tilt", size="M3", at=(X, 40, 4), into=tilt, parts=[flat])
kill(flat)

# ---- blind: plate 3 on an 8 mm boss (M3 needs 3 + 6 = 9, blind cap 11 - 2.6 = 8.4): raise; through_ok builds
X = 120.0
pl = G.box("PRT_fjr_bplate", X - 10, X + 10, -10, 10, 8, 11)
bs = G.box("PRT_fjr_bboss", X - 10, X + 10, -10, 10, 0, 8)
raises("blind", r"too shallow.*a blind hole.*through_ok=True", name="FST_fjr_blind", size="M3", at=(X, 0, 11), into=DOWN,
       parts=[pl, bs])
c2 = F.fastener_joint("FST_fjr_thru", "M3", (X, 0, 11), DOWN, [pl, bs], through_ok=True, cuts={})
r = A.PARTS["FST_fjr_thru"]["fastener_joint"]
say("blind", r["blind"] is False and r["length"] == 10, "through_ok=True: M3 x %g, window %s" % (r["length"], r["window_mm"]))
kill(pl, bs, *[c for v in c2.values() for c in v])
A.PARTS.pop("FST_fjr_thru")
bpy.data.objects.remove(bpy.data.objects["FST_fjr_thru"])
# a 10 mm boss: window 9-10.4, M3 x 10, and the cut mesh keeps min_wall under the pilot
pl = G.box("PRT_fjr_bplate", X - 10, X + 10, -10, 10, 10, 13)
bs = G.box("PRT_fjr_bboss", X - 10, X + 10, -10, 10, 0, 10)
F.fastener_joint("FST_fjr_blind", "M3", (X, 0, 13), DOWN, [pl, bs], step="1", cuts=cuts)
pl, bs = G.csg(pl, sub=cuts.pop(pl.name)), G.csg(bs, sub=cuts.pop(bs.name))
tree, _ = F._bvh(bs)
p0 = Vector((X + 0.0137, 0.0091, -1))
h1 = tree.ray_cast(p0, Vector((0, 0, 1)))[0]                       # the boss's bottom face
h2 = tree.ray_cast(h1 + Vector((0, 0, 1e-3)), Vector((0, 0, 1)))[0]  # the pilot's end
r = A.PARTS["FST_fjr_blind"]["fastener_joint"]
skin = h2.z - h1.z
say("blind", r["blind"] and r["length"] == 10 and skin >= F.RULES["min_wall"] - 0.01, "10 mm boss: M3 x %g, %.2f mm of PLA under the pilot (min_wall %.1f)" % (
    r["length"], skin, F.RULES["min_wall"]))
keep[pl.name], keep[bs.name] = (pl, "PRT"), (bs, "PRT")

# ---- buy_selftap: self-tap into a purchased part
X = 180.0
pl = G.box("PRT_fjr_bk", X - 10, X + 10, -10, 10, 10, 13)
mo = G.box("BUY_fjr_motor", X - 10, X + 10, -10, 10, 0, 10)
raises("buy_selftap", r"purchased part BUY_fjr_motor.*style='tapped'", name="FST_fjr_buy", size="M3", at=(X, 0, 13),
       into=DOWN, parts=[pl, mo])
raises("buy_insert", r"purchased part BUY_fjr_motor.*style='tapped'", name="FST_fjr_buy", size="M3", at=(X, 0, 13),
       into=DOWN, parts=[pl, mo], style="insert")
kill(pl, mo)

# ---- gap: 0.5 mm of air between the plate and the block
X = 240.0
pl = G.box("PRT_fjr_gplate", X - 10, X + 10, -10, 10, 12.5, 15.5)
bk = G.box("PRT_fjr_gblock", X - 10, X + 10, -10, 10, 0, 12)
raises("gap", r"0\.50 mm of air between PRT_fjr_gplate and PRT_fjr_gblock.*gap_ok=True", name="FST_fjr_gap", size="M3",
       at=(X, 0, 15.5), into=DOWN, parts=[pl, bk])
c2 = F.fastener_joint("FST_fjr_gap", "M3", (X, 0, 15.5), DOWN, [pl, bk], gap_ok=True, cuts={})
say("gap", A.PARTS["FST_fjr_gap"]["fastener_joint"]["length"] > 0, "gap_ok=True builds: M3 x %g" % A.PARTS["FST_fjr_gap"]["length"])
kill(pl, bk, *[c for v in c2.values() for c in v])
A.PARTS.pop("FST_fjr_gap")
bpy.data.objects.remove(bpy.data.objects["FST_fjr_gap"])

# ---- csk: countersunk M5 in a 2 mm plate
X = 300.0
pl = G.box("PRT_fjr_cplate", X - 10, X + 10, -10, 10, 20, 22)
bk = G.box("PRT_fjr_cblock", X - 10, X + 10, -10, 10, 0, 20)
raises("csk", r"knife edge", name="FST_fjr_csk", size="M5", at=(X, 0, 22), into=DOWN, parts=[pl, bk], head="csk")
kill(pl, bk)

# ---- reuse: the second joint (window 8.7-13.1) takes the first's 12 over its own shortest, 10
X = 360.0
pl = G.box("PRT_fjr_rplate", X - 10, X + 30, -10, 10, 11, 15.7)
bk = G.box("PRT_fjr_rblock", X - 10, X + 30, -10, 10, 0, 11)
pl2 = G.box("PRT_fjr_rplate2", X - 10, X + 30, 20, 40, 13, 15.7)
bk2 = G.box("PRT_fjr_rblock2", X - 10, X + 30, 20, 40, 0, 13)
F.fastener_joint("FST_fjr_r0", "M3", (X, 0, 15.7), DOWN, [pl, bk], head="pan", step="1", cuts=cuts)
F.fastener_joint("FST_fjr_r1", "M3", (X, 30, 15.7), DOWN, [pl2, bk2], head="pan", step="1", cuts=cuts)
r0, r1 = A.PARTS["FST_fjr_r0"]["fastener_joint"], A.PARTS["FST_fjr_r1"]["fastener_joint"]
say("reuse", r0["length"] == 12 and r1["length"] == 12 and r1["length_reused"] and r1["window_mm"][0] <= 10,
    "first M3 x %g (window %s); second M3 x %g (window %s, reused %s)" % (
        r0["length"], r0["window_mm"], r1["length"], r1["window_mm"], r1["length_reused"]))
F.fastener_joint("FST_fjr_r2", "M3", (X + 20, 30, 15.7), DOWN, [pl2, bk2], head="pan", lengths=[10], step="1", cuts=cuts)
say("reuse", A.PARTS["FST_fjr_r2"]["length"] == 10, "lengths=[10] gives M3 x %g" % A.PARTS["FST_fjr_r2"]["length"])
# a project checks.json: its stock list and its min_engagement (mm) are what the joint reads, as cadcheck would
proj = os.path.join(OUT, "checks.json")
with open(proj, "w") as f:
    json.dump({"fasteners": {"stock_lengths": {"3": [7, 9, 11, 13]}, "min_engagement": 4.0}}, f)
F.use_checks(proj)
F.fastener_joint("FST_fjr_r3", "M3", (X + 20, 0, 15.7), DOWN, [pl, bk], head="pan", step="1", cuts=cuts)
r3 = A.PARTS["FST_fjr_r3"]["fastener_joint"]
F.use_checks(None)
A.PARTS.pop("FST_fjr_r3")                         # built to another project's rules: not part of the cadcheck run
bpy.data.objects.remove(bpy.data.objects["FST_fjr_r3"])
say("reuse", r3["length"] == 9 and abs(r3["window_mm"][0] - 8.7) < 0.02,
    "project checks.json stock [7, 9, 11, 13] and min_engagement 4.0: M3 x %g, window %s" % (r3["length"], r3["window_mm"]))
for o in (pl, bk, pl2, bk2):
    o = G.csg(o, sub=cuts.pop(o.name))
    keep[o.name] = (o, "PRT")

# ---- m2_2d: M2 self-tap with exactly 2 d of thread (2 mm plate, window 6.0-...): cadcheck must not warn
X = 420.0
pl = G.box("PRT_fjr_m2plate", X - 8, X + 8, -8, 8, 10, 12)
bk = G.box("PRT_fjr_m2block", X - 8, X + 8, -8, 8, 0, 10)
F.fastener_joint("FST_fjr_m2", "M2", (X, 0, 12), DOWN, [pl, bk], head="pan", step="1", cuts=cuts)
r = A.PARTS["FST_fjr_m2"]["fastener_joint"]
say("m2_2d", r["length"] == 6 and r["engagement_mm"] == 4.0, "M2 x %g, %.2f mm of thread (2 d = 4.0)" % (r["length"], r["engagement_mm"]))
for o in (pl, bk):
    o = G.csg(o, sub=cuts.pop(o.name))
    keep[o.name] = (o, "PRT")

assert not any(cuts.values()), cuts
for n, (o, kind) in keep.items():
    if kind == "PRT":
        A.part(o, n, 'PRT', "pla_a", stl=n[4:], **INFO)
    else:
        A.part(o, n, 'BUY', "pcb", mass_g=10, src="test board, 1.6 mm, Ø2.7 holes")
rep = {n: A.PARTS[n]["fastener_joint"] for n in A.PARTS if "fastener_joint" in A.PARTS[n]}
with open(os.path.join(OUT, "fjr_report.json"), "w") as f:
    json.dump(rep, f, indent=1)
A.write_manifest(os.path.join(OUT, "manifest.json"))
E.save_blend(os.path.join(OUT, "fjr.blend"))
print("FJR_DONE %d joints kept" % len(rep))
