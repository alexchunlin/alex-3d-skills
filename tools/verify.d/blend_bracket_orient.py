"""best_orientation check on the PR #4 review's three connectors, run by blend_bracket.sh (not sourced).

    Blender -b --python blend_bracket_orient.py -- <skill scripts dir> [n3,n4,brc]

n3: three 20 mm sleeves at uneven angles; n4: three sleeves tilted 20 deg down plus one straight up; brc: a servo
cradle over a through tube at 25 deg, clipped flat at z = -12.5. The review chose each one's orientation by least
overhang area (over 102 directions): n3 and n4 then balanced on a point and failed printcheck with a mid-air island.
Here that least-overhang direction is added to blend.best_orientation's default candidates (tube rims, clip faces,
world axes), and the pick must stand on the bed (50 mm2 or more) with the fewest printcheck fails of any standing
candidate. brc's pick (cradle rim down) and n3's (tube2's rim) have 0 fails: under the user's two bands their sleeves'
undersides between 30 and 45 deg from horizontal only warn. n4 has none without: the face pass fails its 20 deg sleeves'
undersides in every orientation (on tube1's rim two regions, 6.0-7.6 mm past 30 deg from horizontal; before the face
pass, 0 fails there, docs/features/blend-bracket.md "The printcheck gap"), so its pick must need support.
Prints ORIENT {...} per connector.
"""
import json, math, sys
argv = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, argv[0])
from cadlib import asm as A, blend as B, geom as G  # noqa: E402
from mathutils import Vector  # noqa: E402
import numpy as np  # noqa: E402

D, WALL, CLR = 20.0, 4.0, 0.2


def dir_ae(az, el):
    az, el = math.radians(az), math.radians(el)
    return Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))


def node(dirs, arm=40.0):
    th = min(math.acos(max(-1, min(1, a.dot(b)))) for i, a in enumerate(dirs) for b in dirs[i + 1:])
    R = D / 2 + CLR + WALL
    stop = max(R, R / math.tan(th / 2) + 1.0)   # socket floors far enough apart that the bores don't meet
    return [B.Tube((0, 0, 0), tuple(d * arm), D, WALL, CLR, stop=stop) for d in dirs]


def build(which):
    extra, clip = [], None
    if which == "n3":
        holds = node([dir_ae(0, 0), dir_ae(115, 10), dir_ae(235, -25)])
    elif which == "n4":
        holds = node([dir_ae(0, -20), dir_ae(115, -20), dir_ae(250, -20), dir_ae(0, 90)])
    else:
        L, W, H = 40.0, 20.14, 40.0
        zc = 14.2 + 2.0 + H / 2
        cradle = B.Block((0, 0, zc), (L, W, H), wall=3.0, clearance=CLR, grip=((-L, -W, -H / 2 - 5), (L, W, -H / 2 + 15)),
                         open=("+z",), edge=1.5, name="servo")
        a = Vector((math.cos(math.radians(25)), math.sin(math.radians(25)), 0))
        holds = [cradle, B.Tube(tuple(-a * 30), tuple(a * 30), D, WALL, CLR, stop=None)]
        extra = [B.rbox((0, 0, 14.2), (30, 14, 6), r=2, name="web")]
        clip = ((-200, -200, -12.5), (200, 200, 200))
    return B.grow(which, holds, fillet=6.0, extra=extra, clip=clip, voxel=0.5)


def least_overhang(ob, n=96):
    """The review's chooser: the direction (fibonacci sphere + 6 axes) with the least area steeper than 45 deg."""
    me = ob.data
    me.calc_loop_triangles()
    V = np.array([tuple(v.co) for v in me.vertices])
    T = np.array([tuple(t.vertices) for t in me.loop_triangles])
    dirs = []
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n
        r = math.sqrt(1 - y * y)
        t = math.pi * (3 - math.sqrt(5)) * i
        dirs.append(Vector((r * math.cos(t), y, r * math.sin(t))))
    dirs += [Vector(v) for v in ((0, 0, -1), (0, 0, 1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0))]
    best = None
    for d in dirs:
        P = V @ np.array(d.rotation_difference(Vector((0, 0, -1))).to_matrix()).T
        tri = P[T]
        nn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        a = np.linalg.norm(nn, axis=1) / 2
        nz = np.where(a > 1e-9, nn[:, 2] / np.maximum(2 * a, 1e-30), 0)
        zc = tri[:, :, 2].mean(1) - P[:, 2].min()
        bed = (nz < -0.999) & (zc < 0.05)
        ov = float(a[(nz < -math.cos(math.radians(45)) - 1e-3) & (zc > 0.25) & ~bed].sum())
        if best is None or ov < best[0]:
            best = (ov, d)
    return best


ok_all = True
for which in (argv[1] if len(argv) > 1 else "n3,n4,brc").split(","):
    A.new_scene()
    ob, rep = build(which)
    ov, d = least_overhang(ob)
    ranked = B.best_orientation(ob, {**B.orientation_candidates(ob), "least overhang area (review)": tuple(d)})
    low = [o for o in ranked if o["label"].startswith("least overhang")]
    best = min(o["fails"] for o in ranked if o["stands"])
    ok = (ranked[0]["stands"] and ranked[0]["fails"] == best and rep["non_manifold_edges"] == 0
          and (best == 0 if which in ("brc", "n3") else best > 0 and ranked[0]["needs_support"] and "rim" in ranked[0]["label"]))
    ok_all &= ok
    print("ORIENT", json.dumps({"part": which, "ok": ok, "pick": ranked[0]["label"], "pick_down": ranked[0]["down"],
                                "pick_fails": ranked[0]["fails"], "pick_warns": ranked[0]["warns"], "pick_bed_mm2": ranked[0]["bed_mm2"],
                                "least_overhang": {k: low[0][k] for k in ("down", "stands", "fails", "warns", "bed_mm2", "overhang_mm2", "findings")} if low else "deduplicated",
                                "ranked": [(o["label"], o["fails"], o["warns"], o["bed_mm2"]) for o in ranked],
                                "t_s": round(sum(o["t_s"] for o in ranked), 1)}))
print("ORIENT_ALL", json.dumps({"ok": ok_all}))
