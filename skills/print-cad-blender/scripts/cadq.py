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
  printcheck PART                     layer support check of one printed part (its exported STL if on disk, else the
                                      model in print orientation): one line per bridge / cantilever / island region
  route CAB_a[,CAB_b] [--via 'X,Y,Z[@DX,DY,DZ[:LEN]][>PIV_x];...'] [--clearance C] [--cell H] [--bend R]
        [--from X,Y,Z --to X,Y,Z] [--save OUT.blend] [--json OUT.json]
                                      re-route existing cables (cadlib.route) between their own endpoints and
                                      compare with the hand route: length, overlap mm3, visible mm, bend radius
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


def overlaps(ob):
    """{solid: mm3} for the solids and fasteners a cable object overlaps at the current pose (cadcheck's volume)."""
    out, tc, bc = {}, C.bvh_world(ob), C.bbox_world(ob)
    for s in C.SOLIDS + C.FASTENERS:
        if C.bb_gap(bc, C.bbox_world(s)) <= 0.01 and tc.overlap(C.bvh_world(s)):
            v = C.inter_volume(ob, s)[0]
            if v >= 0.01:
                out[s.name] = round(v, 1)
    return out


def boxes(s):
    return [tuple(tuple(float(x) for x in c.split(",")) for c in b.split(":")) for b in str(s).split(";") if b]


def route_cmd():
    """route CAB_a[,CAB_b] [--from X,Y,Z --to X,Y,Z] [--via 'X,Y,Z[@DX,DY,DZ[:LEN]][>PIV_x];...'] [--r R]
    [--clearance C] [--cell H] [--bend R] [--margin M] [--w_open W] [--w_exposed W] [--w_turn W]
    [--prefer 'x0,y0,z0:x1,y1,z1;...'] [--avoid ...] [--save OUT.blend] [--json OUT.json]
    Re-routes existing cables between their own endpoints (or --from/--to), compares with the hand route
    (length, overlap volume, visible length, corners) and with --save writes a copy with the new geometry."""
    import time as _t
    from cadlib import route as RT, asm
    num = {k: float(FLAGS[k]) for k in ("clearance", "cell", "margin", "w_open", "w_exposed", "w_turn", "lead_in") if k in FLAGS}
    if "bend" in FLAGS:
        num["bend_r"] = float(FLAGS["bend"])
    for k in ("prefer", "avoid"):
        if k in FLAGS:
            num[k] = boxes(FLAGS[k])
    if "no-exposure" in FLAGS:
        num["exposure"] = False
    via = []
    for v in str(FLAGS.get("via", "")).split(";"):
        if not v:
            continue
        spec = {}
        if ">" in v:
            v, spec["joint"] = v.split(">")
        if "@" in v:
            v, d = v.split("@")
            if ":" in d:
                d, spec["len"] = d.split(":")
                spec["len"] = float(spec["len"])
            spec["dir"] = tuple(vec(d))
        spec["at"] = tuple(vec(v))
        via.append(spec)
    C.set_pose({})
    tv = C.scene_bvh(C.SOLIDS)
    rows = []
    for nm in POS[1].split(","):
        ob = obj(nm)
        path, rad = RT.path_of(ob)
        if path is None and not ("from" in FLAGS and "to" in FLAGS):
            sys.exit("cadq: cannot read the path of %s; give --from and --to" % ob.name)
        a = vec(FLAGS["from"]) if "from" in FLAGS else Vector(path[0])
        b = vec(FLAGS["to"]) if "to" in FLAGS else Vector(path[-1])
        r = float(FLAGS.get("r", rad or 1.5))
        jb = C.body(ob)
        opt = dict(RT.DEFAULTS, **num)

        def stats(pts):
            pts = [Vector(p) for p in pts]
            ex = 0.0
            for i in range(len(pts) - 1):
                L = (pts[i + 1] - pts[i]).length
                m = max(1, int(math.ceil(L / 2.0)))
                ex += sum(L / m for s in range(m) if RT.exposed(tv, pts[i].lerp(pts[i + 1], (s + 0.5) / m), opt))
            corners = sum(1 for i in range(1, len(pts) - 1) if RT._turn(pts, i) > 1.0)
            return {"length_mm": round(RT._plen(pts), 1), "exposed_mm": round(ex, 1), "corners": corners}
        before = dict(stats(path) if path else {}, overlap_mm3=overlaps(ob))
        t0 = _t.time()
        res = RT.route(a, b, r, via=via, joint=None if jb == "static" else jb, obstacles=C.SOLIDS + C.FASTENERS,
                       joints=C.JOINTS, couplings=C.COUPLE, **num)
        dt = _t.time() - t0
        row = {"cable": ob.name, "r": round(r, 2), "from": list(a), "to": list(b), "hand": before, "routed": res, "route_s": round(dt, 1)}
        if "save" in FLAGS:
            made = []
            for k, pc in enumerate(res["pieces"]):
                me = asm.tube_mesh(ob.name, pc["pts"], r)
                if k == 0:
                    tgt = ob
                else:
                    tgt = C.O.new("%s_%d" % (ob.name, k), me)
                    for c in ob.users_collection:
                        c.objects.link(tgt)
                    if pc["joint"] != "static":
                        tgt.parent = C.O[pc["joint"]]
                        tgt.matrix_parent_inverse = tgt.parent.matrix_world.inverted()
                    C.KIND[tgt.name] = "CAB"
                    bpy.context.view_layer.update()
                me.transform(tgt.matrix_world.inverted())
                for m in ob.data.materials:
                    me.materials.append(m)
                old = tgt.data
                tgt.data = me
                if k == 0:
                    bpy.data.meshes.remove(old)
                # the props asm.cable writes (world at home: route_cmd posed home), so cadcheck's length, junction,
                # end drift, kink and shared-run tests read the new route, not the hand one
                tgt["cab_path"] = [float(c) for p in pc["pts"] for c in p]
                tgt["cab_r"], tgt["path_len"] = float(r), float(RT._plen(pc["pts"]))
                tgt["cab_ends"] = [float(c) for c in list(pc["pts"][0]) + list(pc["pts"][-1])]
                for k_old in ("path", "r"):
                    if k_old in tgt.keys():
                        del tgt[k_old]
                C.MANIFOLD_OK.pop(tgt.name, None)
                made.append(tgt)
            row["after_overlap_mm3"] = {t.name: overlaps(t) for t in made}
        rows.append(row)
        emit(cable=ob.name, hand_mm=before.get("length_mm"), routed_mm=res["length_mm"], hand_overlap_mm3=round(sum(before["overlap_mm3"].values()), 1),
             after_overlap_mm3=round(sum(v for d in row.get("after_overlap_mm3", {}).values() for v in d.values()), 1) if "save" in FLAGS else None,
             min_clearance=res["min_clearance_mm"], bend_r_min=res["bend_r_min"], sharp=res["sharp_corners"],
             hand_exposed_mm=before.get("exposed_mm"), exposed_mm=res["exposed_mm"], stubs=res["stubs"], slack=res["slack"], s=round(dt, 1),
             cable_chain=[ob.name] + ["%s_%d" % (ob.name, k) for k in range(1, len(res["pieces"]))] if len(res["pieces"]) > 1 else None)
    if "json" in FLAGS:
        with open(FLAGS["json"], "w") as f:
            json.dump(rows, f, indent=1, default=str)
    if "save" in FLAGS:
        out = os.path.abspath(FLAGS["save"])
        if out == os.path.abspath(bpy.data.filepath):
            sys.exit("cadq: --save must not overwrite the input blend")
        for n, p in C.CARRIED.items():       # undo cadcheck's carry re-parenting before writing the copy
            o = C.O[n]
            mw = o.matrix_world.copy()
            o.parent = p
            o.matrix_world = mw
        for cn in ("CADCHECK_TMP", "TMP"):
            c = bpy.data.collections.get(cn)
            if c:
                for o in list(c.objects):
                    bpy.data.objects.remove(o)
                bpy.data.collections.remove(c)
        bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)
        emit(saved=out)


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
    elif cmd == "printcheck":
        o = obj(POS[1])
        res, src, note = C.layer_check(o, C.stl_dirs())
        emit(part=o.name, source=src, supports=o.get("supports"), needs_support=res["needs_support"], layers=res["layers"],
             max_overhang_mm=res["max_overhang_mm"], max_bridge_mm=res["max_bridge_mm"], note=note,
             findings=[f["status"] + ": " + f["msg"] for f in res["findings"]])
        for g in res["regions"]:
            if g["status"] != "ok" or "--all" in A:
                emit(**{k: v for k, v in g.items() if not k.startswith("_")})
    elif cmd == "route":
        route_cmd()
    else:
        usage_of(cmd)
except (IndexError, ValueError) as e:
    if cmd not in ("list", "dist", "sweep", "ray", "inside", "section", "render", "printcheck", "route"):
        raise
    print("cadq: %s: %s" % (cmd, e))
    usage_of(cmd)
