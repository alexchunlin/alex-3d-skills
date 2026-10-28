"""Scenes for cadcheck's between-sample guard (tools/verify.d/sweep_guard.sh), from the PR #3 review's adversarial
scenes (/tmp/rv-pr3-work/scenes.py), where cadcheck was shown to miss a collision between two sampled poses:

    cad build tools/verify.d/sweep_guard_build.py --scene NAME --out DIR   (NAME: below)      # writes DIR/scene.blend

- wedge:   a 2 mm arm on PIV_arm (Z, -90..90, no step) reaching 8..70 mm; a static cable (r 1.5) lies radially at
           7.5 deg from r 45 to 64 at z 13. cadcheck sampled every 15 deg and reported 3.386 mm at arm=15; the arm
           overlaps the cable from 4.5 to 10.5 deg, 100.5 mm3 at 7.5.
- pantilt: the same arm on a tilt joint (Y, -10..10) riding a pan joint (Z, -90..90); the cable lies at pan 45, where
           the thinned pan x tilt lattice has no sample.
- clear:   negative control: the wedge arm, the cable at 7.5 deg but past the arm's reach (r 72..90), 2 mm from the
           arm's tip at arm=7.5. Must stay clean; the broad phase (ring sector) settles it.
- beside:  negative control for the narrow phase: the cable radial at 100 deg (r 45..64), past the arm's 92.5 deg
           overtravel by about 3 mm. The arm's box corners near the hub widen its sector to 99.6 deg, so the broad
           phase can't settle it; the swept envelope must, and it must stay clean.
PR #14 review's scenes (/tmp/rv-pr14-work/adv_build.py):
- blade_box / blade_cyl: a 2 x 4 mm blade reaching 5..100 mm on Z -90..90 past a static 2 x 2 (or r 1.4) post at
           37.5 deg, r 50. min_dist (vertices and triangle centres) read 12.64 mm at 30 deg where the gap is about 4.2,
           so refinement "proved" the cell clear; the collision is 14.7 (20.0) mm3 at 37.5.
- multishell_a / _b: a purchased placeholder of two shells (a far block, a small pin in the blade's path at 7.5 deg):
           the pin lies wholly inside the blade's envelope, so no surfaces cross; _a puts the far block first.
- fit_hide: an arm hub on a static shaft (a declared running fit, checks fits) and a lug pin on the same static part in
           the arm's path at 7.5 deg: the fit must not hide the lug.
- fit_journal: the same without the lug: the declared journal stays clean (the turning test proves it).
PR #21 review's scenes (/tmp/rv-pr21-work/adv_build.py): a 2 mm blade (r 8..60) and a r 1.4 post.
- ring_inside / ring_cross / ring_outside: the blade spins on continuous PIV_spin carried by coaxial PIV_carrier; a
           static post wholly inside its solid of revolution (r 40: a collision between samples, which the ring hid),
           across the ring's rim (r 60) or past it (r 66, clean).
- opp_axis: two joints on the Z line 30 mm apart, b's axis -Z (relative angle a + b): collision at a + b = 22.5.
  opp_flip: the same with b under an unranged PIV_flip joint (it used to leave the guard no cells).
- coupled2 / coupledm2: b follows a's driver at ratio +2 / -2: collision at driver 7.5.
- tilt0p05: b's axis 0.05 deg off a's: collision at a - b = 7.5 (the near-coaxial pad must not hide it).
- coax_clear: a hub + lug (r <= 25) and a tooth (r >= 26.2) on coaxial joints, same heights: proven clear.
"""
import math, os, sys
import bpy  # noqa: F401
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, asm as A, export as E  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SC = argv[argv.index("--scene") + 1]
OUT = argv[argv.index("--out") + 1]
os.makedirs(OUT, exist_ok=True)
flat = dict(print_rot=A.R_ID, orient="flat", supports="no", infill=20)
A.new_scene(params={"scene": SC})


def radial(name, deg, r0, r1, z):
    t = math.radians(deg)
    A.cable(name, [(r0 * math.cos(t), r0 * math.sin(t), z), (r1 * math.cos(t), r1 * math.sin(t), z)], 1.5, "cable_red")


def at(deg, r):
    t = math.radians(deg)
    return r * math.cos(t), r * math.sin(t)


def under(name, base, axis_deg, base_axis, lo, hi, step, loc=(0, 0, 0), ranged_base=False):
    """PIV_<name> (Z, lo..hi) under a frame `base` turned axis_deg about base_axis at the origin (identity parent
    inverse, so its world axis is the base's turned Z). ranged_base=False: the base is a plain empty; "joint": an
    unranged PIV_ joint under that turned empty."""
    m = bpy.data.objects.new(base.replace("PIV_", "MNT_"), None)
    bpy.context.scene.collection.objects.link(m)
    m.rotation_euler = [math.radians(axis_deg) if a == base_axis else 0.0 for a in "XYZ"]
    bpy.context.view_layer.update()
    par = m
    if ranged_base == "joint":
        par = A.joint(base, (0, 0, 0), 'Z')        # no lo/hi: a joint with no range
        par.parent = m
        par.matrix_parent_inverse.identity()
        par.location = (0, 0, 0)
    e = A.joint(name, (0, 0, 0), 'Z', lo, hi, step=step)
    e.parent = par
    e.matrix_parent_inverse.identity()
    e.location = loc
    bpy.context.view_layer.update()
    return e


def blade(name, joint):     # 2 mm radial blade, r 8..60, z 0..10, at angle 0
    A.part(G.box(name, 8, 60, -1, 1, 0, 10), name, 'PRT', "pla_b", joint=joint, stl=name[4:], **flat)


def post(name, deg, joint=None, r=40, z0=2, z1=8):
    x, y = at(deg, r)
    A.part(G.cyl(name, (x, y), 1.4, z0, z1, n=24), name, 'PRT', "pla_a", joint=joint, stl=name[4:], **flat)


if SC in ("ring_inside", "ring_outside", "ring_cross"):
    A.joint("PIV_carrier", (0, 0, 0), 'Z', -30, 30, step=15)
    A.joint("PIV_spin", (0, 0, 0), 'Z', parent="PIV_carrier", continuous=True, step=15)
    blade("PRT_blade", "PIV_spin")
    post("PRT_post", 7.5, r={"ring_inside": 40, "ring_outside": 66, "ring_cross": 60}[SC])
elif SC in ("opp_axis", "opp_flip"):
    A.joint("PIV_a", (0, 0, 0), 'Z', 0, 15, step=15)
    under("PIV_b", "PIV_flip", 180, 'X', 0, 15, 15, loc=(0, 0, -30), ranged_base="joint" if SC == "opp_flip" else False)
    blade("PRT_blade", "PIV_a")
    post("PRT_post", 22.5, joint="PIV_b")
elif SC in ("coupled2", "coupledm2"):
    A.joint("PIV_d", (0, 0, 0), 'Z', 0, 15, step=15)
    k = 2.0 if SC == "coupled2" else -2.0
    A.joint("PIV_g", (0, 0, 30), 'Z', couple_to="PIV_d", couple_ratio=k)
    blade("PRT_blade", "PIV_d")
    post("PRT_post", -7.5 if k > 0 else 22.5, joint="PIV_g")
elif SC == "tilt0p05":
    A.joint("PIV_a", (0, 0, 0), 'Z', 0, 15, step=15)
    under("PIV_b", "PIV_tb", 0.05, 'X', 0, 15, 15)
    blade("PRT_blade", "PIV_a")
    post("PRT_post", 7.5, joint="PIV_b")
elif SC == "coax_clear":
    A.joint("PIV_a", (0, 0, 0), 'Z', -60, 60, step=15)
    under("PIV_b", "PIV_flip", 180, 'X', -60, 60, 15, loc=(0, 0, -30))
    hub = G.csg(G.cyl("hub", (0, 0), 12, 0, 6, n=48), add=[G.box("lug", 10, 25, -2, 2, 0, 6)], sub=[G.cyl("bore", (0, 0), 5, -1, 7, n=32)])
    A.part(hub, "PRT_hub", 'PRT', "pla_b", joint="PIV_a", stl="hub", **flat)
    A.part(G.box("tooth", 26.2, 40, -3, 3, 0, 6), "PRT_tooth", 'PRT', "pla_a", joint="PIV_b", stl="tooth", **flat)
elif SC in ("blade_box", "blade_cyl"):
    A.joint("PIV_b", (0, 0, 0), 'Z', -90, 90)
    A.part(G.box("blade", 5, 100, -1, 1, 48, 52), "PRT_blade", 'PRT', "pla_b", joint="PIV_b", stl="blade", **flat)
    x, y = at(37.5, 50)
    post = G.box("post", x - 1, x + 1, y - 1, y + 1, 0, 100) if SC == "blade_box" else G.cyl("post", (x, y), 1.4, 0, 100)
    A.part(post, "PRT_post", 'PRT', "pla_a", stl="post", **flat)
elif SC in ("multishell_a", "multishell_b"):
    A.joint("PIV_b", (0, 0, 0), 'Z', -90, 90)
    A.part(G.box("blade", 5, 100, -1, 1, 48, 52), "PRT_blade", 'PRT', "pla_b", joint="PIV_b", stl="blade", **flat)
    x, y = at(7.5, 50)
    far = G.box("far", -140, -120, -10, 10, 0, 20)
    pin = G.cyl("pin", (x, y), 0.8, 49, 51, n=16)
    A.part(G.join("motor", [far, pin] if SC == "multishell_a" else [pin, far]), "BUY_motor", 'BUY', "buy", mass_g=10, src="test")
elif SC in ("fit_hide", "fit_journal"):
    A.joint("PIV_a", (0, 0, 0), 'Z', -90, 90)
    hub = G.csg(G.cyl("hub", (0, 0), 8, 0, 10, n=64), add=[G.box("arm", 6, 70, -1, 1, 0, 10)], sub=[G.cyl("b", (0, 0), 4.2, -1, 11, n=64)])
    A.part(hub, "PRT_arm", 'PRT', "pla_b", joint="PIV_a", stl="arm", **flat)
    x, y = at(7.5, 50)
    add = [G.box("plate", -10, 60, -40, -20, -12, -10)]
    if SC == "fit_hide":
        add += [G.box("lug", 40, 60, -40, y + 0, -10, -8), G.cyl("lugpin", (x, y), 1.5, -10, 8, n=24)]
    A.part(G.csg(G.cyl("shaft", (0, 0), 4.0, -10, 20, n=64), add=add), "PRT_base", 'PRT', "pla_a", stl="base", **flat)
elif SC == "pantilt":
    A.joint("PIV_pan", (0, 0, 0), 'Z', -90, 90)
    A.joint("PIV_tilt", (0, 0, 25), 'Y', -10, 10, parent="PIV_pan")
    A.part(G.box("arm", 8, 70, -1, 1, 0.5, 40), "PRT_arm", 'PRT', "pla_b", joint="PIV_tilt", stl="arm", **flat)
    radial("CAB_w", 45, 40, 64, 13)
else:
    A.joint("PIV_arm", (0, 0, 0), 'Z', -90, 90)
    A.part(G.box("arm", 8, 70, -1, 1, 0.5, 40), "PRT_arm", 'PRT', "pla_b", joint="PIV_arm", stl="arm", **flat)
    if SC == "wedge":
        radial("CAB_w", 7.5, 45, 64, 13)
    elif SC == "beside":
        radial("CAB_w", 100, 45, 64, 13)
    else:
        radial("CAB_w", 7.5, 72, 90, 13)
E.save_blend(os.path.join(OUT, "scene.blend"))
