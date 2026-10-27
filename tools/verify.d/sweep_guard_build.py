"""Scenes for cadcheck's between-sample guard (tools/verify.d/sweep_guard.sh), from the PR #3 review's adversarial
scenes (/tmp/rv-pr3-work/scenes.py), where cadcheck was shown to miss a collision between two sampled poses:

    cad build tools/verify.d/sweep_guard_build.py --scene wedge|pantilt|clear|beside --out DIR      # writes DIR/scene.blend

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


if SC == "pantilt":
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
