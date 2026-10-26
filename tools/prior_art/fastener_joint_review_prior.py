"""Prior art for the review's cases: hand-placed screws on the pre-fastener_joint cadlib, judged by cadcheck.

    cad build tools/prior_art/fastener_joint_review_prior.py -- --lib <scripts dir of the old cadlib> --out DIR
    cad check DIR/prior_review.blend "" DIR/cadcheck.json

Each case is what a designer writes with features.screw_hole + asm.fastener (the v2 screw() wrapper pattern), with
the hand numbers a designer would pick. The question is which of the review's cases cadcheck catches one check later
without fastener_joint:
  P_gap     M3 x 12 self-tap through a 3 mm plate standing 0.5 mm off its block
  P_buy     M3 x 10 self-tap into a purchased motor block (should be a machine screw into a tapped hole)
  P_thru    M3 x 10 self-tap into an 8 mm boss under a 3 mm plate: the pilot (tip + 1 mm) breaks through the far face
  P_slope   M3 cap on a 12 deg sloped face
  P_csk     M5 countersunk in a 2 mm plate
  P_board   M3 x 8 through a purchased board's own Ø3.4 hole into a printed boss (clamp=1.6 by hand; the old
            screw_hole is M3 only)
"""
import math, os, sys
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
sys.path.insert(0, arg("--lib"))
from cadlib import geom as G, features as F, asm as A, export as E
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

OUT = arg("--out", "/tmp/alex3d-fj-prior/review")
DOWN = (0, 0, -1)
INFO = dict(print_rot=A.R_ID, orient="flat", supports="no", infill=30)
A.new_scene()


def screw(name, at, length, spec, host, cut):
    """The v2 wrapper: one at/into for every cut and for the fastener. cut = [(object, kind, kwargs)]."""
    out = {}
    for ob, kind, kw in cut:
        out.setdefault(ob.name, []).extend(F.screw_hole(at, DOWN, length, kind=kind, name=name, **kw))
    A.fastener(name, at, DOWN, length, spec=spec, host=host, step="1")
    return out


def done(objs, cuts, kinds):
    for o in objs:
        o = G.csg(o, sub=cuts.get(o.name, []))
        if kinds.get(o.name) == "BUY":
            A.part(o, o.name, 'BUY', "buy", mass_g=10, src="test")
        else:
            A.part(o, o.name, 'PRT', "pla_a", stl=o.name[4:], **INFO)


# P_gap
pl, bk = G.box("PRT_gap_plate", -10, 10, -10, 10, 12.5, 15.5), G.box("PRT_gap_block", -10, 10, -10, 10, 0, 12)
done([pl, bk], screw("FST_gap", (0, 0, 15.5), 12, "M3_cap", "PRT_gap_block",
                     [(pl, "clearance", {}), (bk, "clamp", dict(clamp=3.5))]), {})
# P_buy
pl, mo = G.box("PRT_buy_plate", 30, 50, -10, 10, 10, 13), G.box("BUY_buy_motor", 30, 50, -10, 10, 0, 10)
done([pl, mo], screw("FST_buy", (40, 0, 13), 10, "M3_cap", "BUY_buy_motor",
                     [(pl, "clearance", {})]), {"BUY_buy_motor": "BUY"})
# P_thru
pl, bs = G.box("PRT_thru_plate", 60, 80, -10, 10, 8, 11), G.box("PRT_thru_boss", 60, 80, -10, 10, 0, 8)
done([pl, bs], screw("FST_thru", (70, 0, 11), 10, "M3_cap", "PRT_thru_boss",
                     [(pl, "clearance", {}), (bs, "clamp", dict(clamp=3.0))]), {})
# P_slope
sl = G.box("PRT_slope", 90, 120, -10, 10, -6, 6)
G.xform(sl, Matrix.Translation((105, 0, 10)) @ Matrix.Rotation(math.radians(12), 4, 'Y') @ Matrix.Translation((-105, 0, 0)))
M = sl.matrix_world
tree = BVHTree.FromPolygons([M @ v.co for v in sl.data.vertices], [tuple(f.vertices) for f in sl.data.polygons])
top = tree.ray_cast(Vector((105, 0, 50)), Vector((0, 0, -1)))[0]
done([sl], screw("FST_slope", top, 6, "M3_cap", "PRT_slope", [(sl, "selftap", {})]), {})
# P_csk (the old screw_hole is M3 only: an M5 countersink is cut by hand, as a designer would)
pl, bk = G.box("PRT_csk_plate", 130, 150, -10, 10, 20, 22), G.box("PRT_csk_block", 130, 150, -10, 10, 0, 20)
c = {"PRT_csk_plate": [G.cone("csk", (140, 0), 4.85 + 0.6, 2.75, 22.6, 22 - 2.1, 'Z'), G.cyl("clr", (140, 0), 2.75, 19, 23, 'Z')],
     "PRT_csk_block": [G.cyl("pil", (140, 0), 2.1, 7, 21, 'Z')]}
A.fastener("FST_csk", (140, 0, 22), DOWN, 14, spec="M3_csk", host="PRT_csk_block", step="1")   # no M5 spec in the old asm
done([pl, bk], c, {})
# P_board
bd = G.csg(G.box("BUY_board", 160, 180, -10, 10, 12, 13.6), sub=[G.cyl("h", (170, 0), 1.7, 11, 15, 'Z')])
bo = G.csg(G.box("PRT_board_mount", 160, 180, -10, 10, 0, 3), add=[G.cyl("b", (170, 0), 3, 2.9, 12, 'Z')])
done([bd, bo], screw("FST_board", (170, 0, 13.6), 8, "M3_cap", "PRT_board_mount",
                     [(bo, "clamp", dict(clamp=1.6))]), {"BUY_board": "BUY"})
os.makedirs(OUT, exist_ok=True)
E.save_blend(os.path.join(OUT, "prior_review.blend"))
print("PRIOR_REVIEW_DONE")
