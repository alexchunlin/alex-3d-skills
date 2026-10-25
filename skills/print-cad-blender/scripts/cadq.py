"""cadq: one-shot measurements on a .blend (no daemon needed: Blender starts in 0.7 s, FINDINGS A1-T2).

    Blender -b model.blend --python cadq.py -- <command> [args] [--pose PIV_tilt=45,PIV_pan=90] [--config c.json]

Commands
  list [glob]                         objects: kind, body (joint), world bbox at the pose, vertex count
  dist A B                            minimum distance between two objects (negative = overlap volume mm3)
  sweep A B JOINT LO HI STEP          distance (or overlap) of A to B while JOINT moves: the tilt-sweep table
  ray X,Y,Z DX,DY,DZ [--frame PIV_x]  first solid hit along a ray; with --frame, origin and direction are in that
                                      joint's home-pose coordinates and move with it (a ray from a pod point at tilt 45)
  inside X,Y,Z                        which solids contain the point
  section AXIS VAL OUT.png CAMX,CAMY,CAMZ ORTHO [--scope PIV_tilt,static] [--keep -|+]
  render OUT.png CAMX,CAMY,CAMZ TX,TY,TZ [--ortho S] [--lens L]
  --lentil X,Y,Z[:NX,NY,NZ][;...]     (with section/render) M&M-size markers (normal = thickness axis, default 0,0,1)

Prints one JSON object per result line prefixed with CADQ, so agents can grep it. `cad q` with no arguments prints
this help. Rows you want re-checked on every run belong in checks.json (distances, sightlines, payload_fit), not here.
Objects match by exact name or glob (first match). Joint ranges come from PIV props or --config.
"""
import bpy, fnmatch, json, math, os, sys
os.environ["CADCHECK_NO_MAIN"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cadcheck as C   # noqa: E402  (shares pose logic, BVH helpers and inside test)
from mathutils import Vector  # noqa: E402

A = C.ARGV
FLAGS = {}
POS = []
i = 0
while i < len(A):
    if A[i].startswith("--"):
        FLAGS[A[i][2:]] = A[i + 1] if i + 1 < len(A) and not A[i + 1].startswith("--") else True
        i += 2 if FLAGS[A[i][2:]] is not True else 1
    else:
        POS.append(A[i])
        i += 1


def vec(s):
    return Vector(tuple(float(x) for x in s.split(",")))


def pose_from(s):
    out = {}
    if s and s is not True:
        for kv in s.split(","):
            k, v = kv.split("=")
            out[k if k.startswith("PIV_") else "PIV_" + k] = float(v)
    return out


def obj(name):
    if name in C.O:
        return C.O[name]
    for o in C.O:
        if fnmatch.fnmatch(o.name, name):
            return o
    sys.exit("cadq: no object %s" % name)


def emit(**kw):
    print("CADQ " + json.dumps(kw, default=lambda v: [round(x, 3) for x in v] if hasattr(v, "__len__") else str(v)))


POSE = pose_from(FLAGS.get("pose"))
C.set_pose(POSE)
cmd = POS[0] if POS else "list"
if os.environ.get("CADQ_DEBUG"):
    print("CADQ_DEBUG", A, POS, FLAGS)


def distance(a, b):
    ta, tb = C.bvh_world(a), C.bvh_world(b)
    if ta.overlap(tb):
        v, region, solver = C.inter_volume(a, b)
        if v >= 0.01:
            return -v, region
    d, p = C.min_dist(a, b, ta, tb)
    return d, [round(c, 2) for c in p] if p else None


def usage_of(c):
    """Exit with the help lines for command c, or the whole help for an unknown one. Prefixed "cadq:" because `cad q`
    passes only CADQ / cadq: lines (v2 A2: 8 of 9 agents read cadq.py for usage; `cad q m.blend ray` gave IndexError)."""
    lines = [ln for ln in __doc__.splitlines() if ln.strip().startswith(c + " ")] or __doc__.splitlines()
    sys.exit("\n".join("cadq: " + ln for ln in lines))


try:
    if cmd == "list":
        g = POS[1] if len(POS) > 1 else "*"
        for o in sorted(C.O, key=lambda x: x.name):
            if o.type != 'MESH' or not fnmatch.fnmatch(o.name, g):
                continue
            lo, hi = C.bbox_world(o)
            emit(name=o.name, kind=C.KIND.get(o.name, "-"), body=C.body(o), lo=lo, hi=hi, verts=len(o.data.vertices))
    elif cmd == "dist":
        a, b = obj(POS[1]), obj(POS[2])
        d, where = distance(a, b)
        emit(a=a.name, b=b.name, pose=C.pose_key(POSE), mm=round(d, 3), note="negative = overlap volume mm3", at=where)
    elif cmd == "sweep":
        a, b, j = obj(POS[1]), obj(POS[2]), POS[3]
        j = j if j.startswith("PIV_") else "PIV_" + j
        lo, hi, st = float(POS[4]), float(POS[5]), float(POS[6])
        for ang in C.frange(lo, hi, st):
            C.set_pose(dict(POSE, **{j: ang}))
            d, where = distance(a, b)
            emit(a=a.name, b=b.name, joint=j, deg=ang, mm=round(d, 3), at=where)
    elif cmd == "ray":
        p, d = vec(POS[1]), vec(POS[2]).normalized()
        if FLAGS.get("frame"):
            # v2 A2 progress.md "Tool issues": a ray from a pod point at tilt 45 had to be transformed by hand
            fr = FLAGS["frame"] if FLAGS["frame"].startswith("PIV_") else "PIV_" + FLAGS["frame"]
            posed = C.O[fr].matrix_world.copy()
            C.set_pose({})
            home = C.O[fr].matrix_world.copy()
            C.set_pose(POSE)
            M = posed @ home.inverted()
            p, d = M @ p, (M.to_3x3() @ d).normalized()
        best = None
        for o in C.SOLIDS + C.FASTENERS:
            h = C.bvh_world(o).ray_cast(p, d, 1e4)
            if h[0] is not None and (best is None or h[3] < best[0]):
                best = (h[3], o.name, h[0])
        emit(origin=p, dir=d, hit=best[1] if best else None, mm=round(best[0], 3) if best else None, at=best[2] if best else None)
    elif cmd == "inside":
        p = vec(POS[1])
        emit(point=p, inside=[o.name for o in C.SOLIDS + C.FASTENERS if C.inside(C.bvh_world(o), p, C.bbox_world(o))])
    elif cmd in ("section", "render"):
        sys.path.insert(0, HERE)
        from cadlib import render as R
        R.setup(final=FLAGS.get("final") is True)
        if "lentil" in FLAGS:
            for k, spec in enumerate(str(FLAGS["lentil"]).split(";")):
                c, n = (spec.split(":") + ["0,0,1"])[:2]   # v2 A2: the reviewer gave a bare point twice (ValueError)
                R.marker_lentil("MM_%d" % k, vec(c), vec(n))
        if cmd == "section":
            axis, val, out, cam, ortho = POS[1].lower(), float(POS[2]), POS[3], vec(POS[4]), float(POS[5])
            k = "xyz".index(axis)     # X or x (v2 A1: 3 agents hit ValueError on "X")
            tgt = cam.copy()
            tgt[k] = val
            scope = set(FLAGS["scope"].split(",")) if "scope" in FLAGS else None
            path = R.section(os.path.dirname(os.path.abspath(out)), os.path.basename(out), axis, val, cam, tgt, ortho,
                             keep_side=FLAGS.get("keep", "-"), scope=scope)
        else:
            out, cam, tgt = POS[1], vec(POS[2]), vec(POS[3])
            R.camera(cam, tgt, ortho=float(FLAGS["ortho"]) if "ortho" in FLAGS else None, lens=float(FLAGS.get("lens", 50)))
            path = R.shot(os.path.abspath(out))
        emit(render=path, pose=C.pose_key(POSE))
    else:
        usage_of(cmd)
except (IndexError, ValueError) as e:
    if cmd not in ("list", "dist", "sweep", "ray", "inside", "section", "render"):
        raise
    print("cadq: %s: %s" % (cmd, e))
    usage_of(cmd)
