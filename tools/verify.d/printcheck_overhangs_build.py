"""Adversarial parts for printcheck's face pass, built with cadlib the way an agent would; float32 STLs.
From the PR #11 independent review (its build_cases.py), unchanged but for this header. printcheck_overhangs_cases.py
reads them with the verdict each must get.

    Blender -b --factory-startup --python printcheck_overhangs_build.py -- <skill scripts dir> <out dir>"""
import math, os, struct, sys
argv = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, argv[0])
OUT = argv[1]
os.makedirs(OUT, exist_ok=True)
from cadlib import geom as G, features as F, blend as B  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

T10, T20 = math.tan(math.radians(10)), math.tan(math.radians(20))


def save(name, ob):
    if os.path.exists(os.path.join(OUT, name + '.stl')):
        G.kill(ob); return
    V, T = G._world_tris([ob])
    with open(os.path.join(OUT, name + ".stl"), "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(T)))
        for t in T:
            f.write(struct.pack("<3f", 0, 0, 0))
            for i in t:
                f.write(struct.pack("<3f", *V[i]))
            f.write(b"\0\0")
    G.kill(ob)
    print("BUILT", name, len(T))


def u(base, *add, sub=()):
    return G.csg(base, add=list(add), sub=list(sub))


# A corner: 21 mm slab, underside rising 10 deg along +x, walls on -x and -y (adjacent). A0: wall on -x only (a ramp)
for nm, walls in (("A_corner_10deg", 2), ("A0_ramp_one_wall_10deg", 1)):
    b = G.box("w1", -5, 0, -5, 20, 0, 30)
    adds = [G.prism("slab", [(-1, 20 - T10), (20, 20 + 20 * T10), (20, 28), (-1, 28)], -1 if walls == 2 else 0, 20, 'Y')]
    if walls == 2:
        adds.append(G.box("w2", -5, 20, -5, 0, 0, 30))
    save(nm, u(b, *adds))

# B pillars at different heights: slab underside rises 20 deg from pillar A (x 0) to pillar B (x 20), open sides
b = G.box("pa", -5, 0, 0, 10, 0, 30)
save("B_pillars_rise20", u(b, G.box("pb", 20, 25, 0, 10, 0, 30),
                           G.prism("s", [(-1, 10 - T20), (21, 10 + 21 * T20), (21, 24), (-1, 24)], 0, 10, 'Y')))
# B2 the same, 10 deg over 30 mm
b = G.box("pa", -5, 0, 0, 10, 0, 30)
save("B2_pillars_rise10_30mm", u(b, G.box("pb", 30, 35, 0, 10, 0, 30),
                                 G.prism("s", [(-1, 10 - T10), (31, 10 + 31 * T10), (31, 24), (-1, 24)], 0, 10, 'Y')))

# C gable roofs over channels (sloped 'bridges'): 20 and 40 mm wide, roof 20 deg; and a 40 mm horizontal hole
for w in (20, 40):
    b = G.box("blk", 0, 20, -w / 2 - 5, w / 2 + 5, 0, 10 + w / 2 * T20 + 8)
    cut = G.prism("ch", [(-w / 2, -1), (w / 2, -1), (w / 2, 10), (0, 10 + w / 2 * T20), (-w / 2, 10)], -1, 21, 'X')
    save("C_gable20deg_%dmm" % w, u(b, sub=[cut]))
b = G.box("blk", 0, 20, -26, 26, 0, 52)
save("C_hole40", u(b, sub=[G.cyl("h", (0, 26), 20, -1, 21, 'X')]))

# D needle: the 10 deg ramp off one wall (21 mm) with a 0.8 mm pin under its far edge
b = G.box("w", -10, 0, 0, 20, 0, 30)
save("D_ramp10_needle", u(b, G.prism("s", [(-1, 5 - T10), (20, 5 + 20 * T10), (20, 15), (-1, 15)], 0, 20, 'Y'),
                          G.cyl("pin", (19, 10), 0.4, 0, 6, 'Z', n=12)))
# D2 thin-wall anchor: slab between a wall at x 0 and a fin at x 20, underside rising 10 deg along y (both ends level)
for t in (0.05, 1.2):
    b = G.box("w", -10, 0, 0, 20, 0, 20)
    save("D2_wall_and_fin_%gmm" % t, u(b, G.box("fin", 20, 20 + t, 0, 20, 0, 20),
                                      G.prism("s", [(-1, 5 - T10), (20, 5 + 20 * T10), (20, 15), (-1, 15)], -0.5, 20, 'X')))

# E sloped underside from the bed: 20 deg, 20 mm; and horizontal cylinders lying on the bed
b = G.box("base", -10, 0, 0, 20, 0, 12)
save("E_bed_wedge20", u(b, G.prism("s", [(-0.5, 0), (20, 20 * T20), (20, 12), (-0.5, 12)], 0, 20, 'Y')))
for r in (5, 10, 15):
    save("E2_lying_cyl_r%d" % r, G.cyl("c", (0, r), r, 0, 40, 'X'))

# F teardrops: geom.teardrop holes (d 6, 20), one with its axis at 30 deg in xy; Tube(print_up=) horizontal 20 mm
for d in (6, 20):
    b = G.box("blk", 0, 20, -15, 15, 0, 30)
    save("F_teardrop_%d" % d, u(b, sub=[G.prism("h", G.teardrop((0, 15), d / 2, up=(0, 1)), -1, 21, 'X')]))
b = G.box("blk", 0, 20, -15, 15, 0, 30)
ob = u(b, sub=[G.prism("h", G.teardrop((0, 15), 10, up=(0, 1)), -1, 21, 'X')])
save("F_teardrop_20_rot30", G.xform(ob, Matrix.Rotation(math.radians(30), 4, 'Z')))
for pu, nm in (((0, 0, 1), "F_tube20_print_up"), (None, "F0_tube20_round_bore")):
    tb = B.Tube((0, 0, 0), (40, 0, 0), 20, print_up=pu)
    ob, _ = B.grow("t", holds=[tb], extra=[B.rbox(Matrix.Translation((20, 0, -12)), (44, 28.4, 4), 0.5)], clip=((-5, -20, -12), (45, 20, 20)))
    save(nm, ob)
b = G.box("blk", 0, 20, -10, 10, 0, 20)
save("F_screw_hole_print_up", u(b, sub=F.screw_hole((0, 0, 10), (1, 0, 0), 20, "clearance", print_up=(0, 0, 1))))

# G chamfers at exactly 45 deg: a shelf on a 45 deg gusset; a box with every edge bevelled 1.5 mm
b = G.box("w", -10, 0, 0, 20, 0, 30)
save("G_shelf_on_45_gusset", u(b, G.box("sh", -1, 10, 0, 20, 20, 25), G.prism("gu", [(-1, 9), (10, 20.0), (-1, 20.0)], 0, 20, 'Y')))
b = G.box("bx", 0, 30, 0, 20, 0, 15)
save("G_box_bevel_1p5", G.bevel(b, 1.5))

# H fillets under cantilevers: 8 mm shelf with r 4 fillet (should fail); 2 mm ledge with r 2 fillet (should pass)
for reach, r in ((8, 4), (2, 2)):
    b = G.box("w", -10, 0, 0, 20, 0, 30)
    fil = G.csg(G.box("fb", -0.5, r, 0, 20, 20 - r, 20.5), sub=[G.cyl("fc", (r, 20 - r), r, -1, 21, 'Y', n=48)])
    save("H_shelf%d_fillet%d" % (reach, r), u(b, G.box("sh", -1, reach, 0, 20, 20, 23), fil))

# I domes: hollow hemispherical caps on their rim, inner r 9 and 18
for ri in (9, 18):
    ro = ri + 2
    prof = [(ro * math.cos(math.radians(a)), ro * math.sin(math.radians(a))) for a in range(0, 91, 3)]
    prof += [(ri * math.cos(math.radians(a)), ri * math.sin(math.radians(a))) for a in range(90, -1, -3)]
    prof = [(max(x, 0.0), z) for x, z in prof]
    save("I_dome_ri%d" % ri, G.revolve("dome", prof, (0, 0, 0), n=96))

# J narrow sloped ribs off a wall: 6 mm reach, 10 deg underside, 3 and 4 mm wide; the 3 mm one flat
for wdt, sl in ((3, T10), (4, T10), (3, 0.0)):
    b = G.box("w", -10, 0, -5, 10, 0, 20)
    save("J_rib_w%d_%s" % (wdt, "10deg" if sl else "flat"),
         u(b, G.prism("rib", [(-1, 10 - sl), (6, 10 + 6 * sl), (6, 13), (-1, 13)], 0, wdt, 'Y')))
