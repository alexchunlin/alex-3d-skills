"""Prior art for features.fastener_joint: the v2 designer's screw() wrapper on the pre-fastener_joint cadlib.

    cad build tools/prior_art/fastener_joint_prior.py -- --lib <scripts dir of the old cadlib> --out DIR
        [--size M3|M4] [--nut-len 16] [--tap-len 12]

Same stack as tools/verify.d/fastener_joint_build.py (4.7 mm plate on an 11 mm block, from the top). The wrapper is
copied from mm-launch-hw/v2/blender/parts/base.py:64 (also launcher.py:43, pan_stage.py:19); the nut handling is
the v2 hinge pattern (launcher.py:455-458). Every number the old API needs is worked out by hand here, as the v2
designer had to. Prints PRIOR lines: what built, the hole diameters it cut, and any error.
"""
import json, math, os, sys
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
sys.path.insert(0, arg("--lib"))
from cadlib import geom as G, features as F, asm as A, export as E
from mathutils import Vector
from mathutils.bvhtree import BVHTree

SIZE, OUT = arg("--size", "M3"), arg("--out", "/tmp/alex3d-fj-prior/out")
NUT_L, TAP_L = float(arg("--nut-len", 16)), float(arg("--tap-len", 12))
DOWN, Z_TOP, PLATE_T = (0, 0, -1), 15.7, 4.7


def screw(name, at, into, length, spec, host, step, joint=None, cut=()):
    """One fastener: the same at/into for every part it passes and for asm.fastener.
    cut = [(kind, kwargs, sink_list)]: features.screw_hole cutters appended to each list."""
    for kind, kw, lst in cut:
        lst += F.screw_hole(at, into, length, kind=kind, name=name, **kw)
    A.fastener(name, at, into, length, spec=spec, joint=joint, host=host, step=step)


def hole_d(ob, c):
    tree = BVHTree.FromPolygons([ob.matrix_world @ v.co for v in ob.data.vertices], [tuple(f.vertices) for f in ob.data.polygons])
    rs = [h[3] for k in range(360) for h in [tree.ray_cast(Vector(c), Vector((math.cos(math.radians(k + 0.37)), math.sin(math.radians(k + 0.37)), 0)), 50)] if h[0]]
    return round(2 * max(rs), 3)


A.new_scene()
plate = G.box("plate", -30, 30, -10, 10, 11.0, Z_TOP)
block = G.box("block", -30, 30, -10, 10, 0.0, 11.0)
pl, bl = [], []
try:
    # through-bolt + nut trap at the block's far face: nut face, trap depth and length all by hand
    at = (-20.0, 0.0, Z_TOP)
    screw("FST_fj_nut", at, DOWN, NUT_L, "%s_cap" % SIZE, None, "1",
          cut=[("clearance", dict(), pl), ("clearance", dict(), bl)])
    nh = F.RULES["m3_nut_h"]
    nf = (at[0], at[1], 0.0 + nh + 0.3)
    bl += F.nut_trap(nf, DOWN, depth=nh + 0.3 + 0.6, name="hgn")
    A.nut("FST_fj_nut_nut", nf, DOWN, step="1")
    # self-tap through the plate into the block (clamp = plate thickness, by hand)
    screw("FST_fj_tap", (-5.0, 0.0, Z_TOP), DOWN, TAP_L, "%s_csk" % SIZE, "PRT_fj_block", "1",
          cut=[("clamp", dict(clamp=PLATE_T, head="csk"), pl), ("clamp", dict(clamp=PLATE_T), bl)])
    print("PRIOR built %s: nut bolt %g, self-tap %g (lengths given by hand)" % (SIZE, NUT_L, TAP_L))
except Exception as e:
    print("PRIOR error %s: %s: %s" % (SIZE, type(e).__name__, e))
G.csg(plate, sub=pl)
G.csg(block, sub=bl)
print("PRIOR holes %s: plate clearance %.2f, block pilot %.2f" % (SIZE, hole_d(plate, (-20, 0, 13)), hole_d(block, (-5, 0, 8))))
info = dict(print_rot=A.R_ID, orient="flat", supports="no", infill=30)
A.part(plate, "PRT_fj_plate", 'PRT', "pla_a", stl="fj_plate", **info)
A.part(block, "PRT_fj_block", 'PRT', "pla_b", stl="fj_block", **info)
os.makedirs(OUT, exist_ok=True)
E.save_blend(os.path.join(OUT, "prior.blend"))
