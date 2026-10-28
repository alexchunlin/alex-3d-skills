"""Scenes for cadcheck's between-sample guard (tools/verify.d/sweep_guard.sh), from the PR #3 review's adversarial
scenes (/tmp/rv-pr3-work/scenes.py), where cadcheck was shown to miss a collision between two sampled poses:

    cad build tools/verify.d/sweep_guard_build.py --scene wedge|pantilt|clear|beside|blade_box|blade_cyl|multishell_a|multishell_b|fit_hide|fit_journal --out DIR      # writes DIR/scene.blend

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


if SC in ("blade_box", "blade_cyl"):
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
