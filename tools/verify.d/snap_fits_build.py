"""Snap fits and print-in-place hinges, for snap_fits.sh: one blend with each kind, plus the builds that must refuse.

    cad build tools/verify.d/snap_fits_build.py -- --out DIR

PRT_hk_base / PRT_hk_cover   snap_hook, arm along +X in the layer plane, sized (pass)
PRT_st_post / PRT_st_cap     snap_hook, arm along +Z: standing across layers in print (cadcheck fails it)
PRT_an_boss / PRT_an_cap     annular_snap, cap on a boss, axis upright (pass)
PRT_ts_frame / PRT_ts_cover  torsion_snap, bar along X across a window in the frame (pass)
PRT_cg_cage / PRT_cg_inner   snap_hook on a part sealed in a closed box (insertion must not call it free)
PRT_hg_a / PRT_hg_b          pip_hinge, 0.4 mm clearances, axis along Y flat on the bed (pass, swept)
PRT_hb_a / PRT_hb_b          pip_hinge, 0.2 mm clearances (strict=False; cadcheck fails it)
PRT_leaf, PRT_leaf2          plain leaves for hand-written flexures rows with dimensions
Prints SNAP_ERR <case>: <message> for each SnapError it expects (a hook too short for its undercut, an annular
interference over the allowable, a hinge under 0.3 mm with strict, a hook with no ledge in its catch, and bad inputs).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, export as E, features as F

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/alex3d-snap-test"
A.new_scene()
flat = dict(print_rot=A.R_ID, orient="flat", supports="no")


def expect_err(case, fn):
    try:
        fn()
        print("SNAP_NOERR %s" % case)
    except F.SnapError as e:
        print("SNAP_ERR %s: %s" % (case, e))


def done(ob, name, stl, joint=None, **kw):
    return A.part(ob, name, 'PRT', "pla_a", joint=joint, stl=stl, material="PLA", walls=3, infill=40, **dict(flat, **kw))


# hook (off on its own at y -100, so +X is clear to infinity): the arm comes off the base's +X face and goes into the cover, barb up (+Z)
base = G.box("PRT_hk_base", 0, 30, -110, -90, 0, 10)
cover = G.box("PRT_hk_cover", 32, 52, -110, -90, 0, 12)
expect_err("short", lambda: F.snap_hook("hk_short", base, cover, (30, -100, 5), (1, 0, 0), (0, 0, 1), length=4, width=6, undercut=1.5))
far = G.box("PRT_far", 70, 80, -110, -90, 0, 12)
expect_err("noledge", lambda: F.snap_hook("hk_far", base, far, (30, -100, 5), (1, 0, 0), (0, 0, 1), length=14, width=6, undercut=0.8))
G.kill(far)
ops = F.snap_hook("hk", base, cover, (30, -100, 5), (1, 0, 0), (0, 0, 1), length=14, width=6, undercut=0.8)
# standing: the same hook off the post's top, along +Z; sized without print_up (in-plane allowable), printed flat
post = G.box("PRT_st_post", 0, 20, 40, 60, 0, 10)
cap = G.box("PRT_st_cap", 0, 20, 40, 60, 12, 32)
F.snap_hook("st", post, cap, (10, 50, 10), (0, 0, 1), (1, 0, 0), length=14, width=6, undercut=0.8, ops=ops)
# annular: a d 10 boss, a cap with a 10.2 bore and od 13
boss = G.cyl("PRT_an_boss", (100, 10), 5.0, 0, 12, 'Z', 64)
capa = G.cyl("PRT_an_cap", (100, 10), 6.5, 6, 15, 'Z', 64)
G.csg(capa, sub=[G.cyl("bore", (100, 10), 5.1, 5, 12, 'Z', 64)])
expect_err("annular_over", lambda: F.annular_snap("an_x", boss, capa, (100, 10, 9), (0, 0, 1), 10.0, 13.0, interference=0.5))
F.annular_snap("an", boss, capa, (100, 10, 9), (0, 0, 1), 10.0, 13.0, uses="once", ops=ops)
# torsion: a frame with a window, the bar along X at y 10 across it, the lever along +Y, barb up
frame = G.box("PRT_ts_frame", 0, 40, 80, 110, 0, 4)
G.csg(frame, sub=[G.box("win", 10, 30, 85, 105, -1, 5)])
tcov = G.box("PRT_ts_cover", 12, 28, 92, 104, 3.2, 9)
F.torsion_snap("ts", frame, tcov, (20, 90, 2), (0, 1, 0), (0, 0, 1), bar_len=20, lever=10, width=6, undercut=0.6,
               bar_d_max=3.0, ops=ops)
# captive (PR #22 review): a hooked part sealed inside a closed box can't go in, whatever the snap
cage = G.box("PRT_cg_cage", 400, 440, 0, 30, 0, 30)
G.csg(cage, sub=[G.box("cv", 403, 437, 3, 27, 3, 27)])
inner = G.box("PRT_cg_inner", 405, 415, 8, 22, 8, 22)
F.snap_hook("cg", inner, cage, (415, 15, 15), (1, 0, 0), (0, 0, 1), length=23.5, width=6, undercut=0.8, ops=ops)
# bad inputs raise SnapError before any arithmetic (PR #22 review)
b0, c0 = G.box("d_b", 500, 520, 0, 30, 0, 10), G.box("d_c", 500, 520, 32, 52, 0, 12)
expect_err("undercut0", lambda: F.snap_hook("d1", b0, c0, (510, 30, 5), (0, 1, 0), (0, 0, 1), length=15, width=6, undercut=0))
expect_err("length0", lambda: F.snap_hook("d2", b0, c0, (510, 30, 5), (0, 1, 0), (0, 0, 1), length=0, width=6, undercut=0.8, thickness=2))
expect_err("stubby", lambda: F.snap_hook("d3", b0, c0, (510, 30, 5), (0, 1, 0), (0, 0, 1), length=8, width=6, undercut=0.3, thickness=2))
expect_err("axisW", lambda: F.pip_hinge("d4", (b0, c0), (510, 31, 5), "W", 20, 3, 3.0))
expect_err("hub_small", lambda: F.annular_snap("d5", b0, c0, (510, 15, 5), (0, 0, 1), 10.0, 8.0, interference=0.1))
G.kill(b0)
G.kill(c0)
for ob in (base, cover, post, cap, boss, capa, frame, tcov, cage, inner):
    G.csg(ob, **ops[ob.name])
done(base, "PRT_hk_base", "hk_base")
done(cover, "PRT_hk_cover", "hk_cover")
done(post, "PRT_st_post", "st_post")
done(cap, "PRT_st_cap", "st_cap")
done(boss, "PRT_an_boss", "an_boss")
done(capa, "PRT_an_cap", "an_cap")
done(frame, "PRT_ts_frame", "ts_frame")
done(tcov, "PRT_ts_cover", "ts_cover")
done(cage, "PRT_cg_cage", "cg_cage")
done(inner, "PRT_cg_inner", "cg_inner")


def hinge(tag, x0, **kw):
    # leaves 3 thick on the bed, the axis along +Y at z 3.1 so the knuckles (od 6.2) touch the bed too
    a = G.box("PRT_%s_a" % tag, x0 - 30, x0 - 2.6, 0, 30, 0, 3)
    b = G.box("PRT_%s_b" % tag, x0 + 2.6, x0 + 30, 0, 30, 0, 3)
    o = F.pip_hinge(tag, (a, b), (x0, 0, 3.1), "Y", 30, 5, 3.0, lo=-120, hi=0, step=10, print_up=(0, 0, 1), **kw)
    G.csg(a, **o[a.name])
    G.csg(b, **o[b.name])
    done(a, "PRT_%s_a" % tag, "%s_a" % tag)
    done(b, "PRT_%s_b" % tag, "%s_b" % tag, joint="PIV_%s" % tag)


hinge("hg", 0.0 + 200)
a0, b0 = G.box("ta", 297.4, 310, 0, 30, 0, 3), G.box("tb", 312.6, 340, 0, 30, 0, 3)
expect_err("hinge_strict", lambda: F.pip_hinge("hx", (a0, b0), (310, 0, 3.1), "Y", 30, 5, 3.0, clearance=0.2, gap=0.2))
G.kill(a0)
G.kill(b0)
hinge("hb", 300.0, clearance=0.2, gap=0.2, strict=False)
done(G.box("l1", 0, 30, 150, 158, 0, 1.5), "PRT_leaf", "leaf")
done(G.box("l2", 40, 70, 150, 158, 0, 1.5), "PRT_leaf2", "leaf2")
E.export_stls(os.path.join(OUT, "stl"))
A.write_manifest(os.path.join(OUT, "manifest.json"))
E.save_blend(os.path.join(OUT, "m.blend"))
print("SNAP_BUILT")
