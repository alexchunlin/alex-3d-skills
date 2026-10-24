"""cadcheck: evidence-producing checks for a printable Blender assembly.

    Blender -b model.blend --python cadcheck.py -- [--config checks.json] [--out report.json]
                                                   [--only parts,interference,...] [--quick]

Works on any .blend that follows the conventions in ../SKILL.md (collections Printed / Purchased /
Fasteners / Cables, moving links parented under PIV_* empties). Joint ranges come from PIV_* custom
properties written by cadlib.asm.joint() or from the "joints" block of the config.

Checks (each one writes evidence into the JSON report, with an explicit `coverage` list):
  parts         manifold, volume, print-orientation bed fit, overhang area, min wall, bed contact
  interference  every pair in ALL four collections, swept over the joints that separate the two bodies,
                including overtravel past each limit; contacts between different bodies are failures
  clearance     min distance between parts on different bodies over the same sweep
  fasteners     head not buried, tip in material, driver access (ray bundle + open-space test) per pose
  drop          ray-grid drop tests from config ("drop_tests") with landing angle windows
  slide         slide-out sweeps from config ("slide_out")
  distances     min/max distance assertions from config ("distances")
  stability     centre of mass and static tip angle over a coarse pose grid
  cables        path length vs. lead length (when cables carry path_len / lead_len)

Evidence for the rules here: docs/FINDINGS.md A1-F1, F3, F4, F5, F9, F10, F11, F13, F14.
"""
import bpy, bmesh, json, math, os, sys, time, fnmatch, itertools
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _arg(name, default=None):
    return ARGV[ARGV.index(name) + 1] if name in ARGV else default


DEFAULTS = {
    "collections": {"printed": "Printed", "purchased": "Purchased", "fasteners": "Fasteners", "cables": "Cables"},
    "printers": {"P1S": [256, 256, 256], "H2D": [325, 320, 325]},
    "prefer_printer": "P1S",
    "min_wall": 1.6,
    "overhang_deg": 45.0,
    "joints": {},
    "couplings": {},
    "overtravel_deg": 2.5,
    "max_poses_per_group": 48,
    "allow": [],
    "vol_tol": 0.5,
    "moving_min_clearance": 0.5,
    "moving_warn_clearance": 1.0,
    "fasteners": {"driver_r": 3.0, "hand_r": 14.0, "max_reach": 60.0, "max_reach_ext": 150.0},
    "drop_tests": [],
    "slide_out": [],
    "distances": [],
    "masses_g": {},
    "pla_density": 1.24e-3,
    "flow_mm3_s": 12.0,
    "cable_leads": {},
}

T0 = time.time()
CFG = json.loads(json.dumps(DEFAULTS))
if _arg("--config"):
    with open(_arg("--config")) as f:
        user = json.load(f)
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(CFG.get(k), dict):
            CFG[k].update(v)
        else:
            CFG[k] = v
QUICK = "--quick" in ARGV
ONLY = set(_arg("--only", "").split(",")) - {""}
OUT = _arg("--out") or os.path.join(os.path.dirname(bpy.data.filepath) or ".", "cadcheck.json")
O = bpy.data.objects
COLL = CFG["collections"]


def want(check):
    return not ONLY or check in ONLY


def log(*a):
    print("[cadcheck %5.1fs]" % (time.time() - T0), *a, flush=True)


# ------------------------------------------------------------------ scene model

def coll_objs(key):
    c = bpy.data.collections.get(COLL[key])
    return [o for o in c.all_objects if o.type == 'MESH'] if c else []


PRINTED, PURCHASED, FASTENERS, CABLES = (coll_objs(k) for k in ("printed", "purchased", "fasteners", "cables"))
KIND = {}
for o in PRINTED: KIND[o.name] = "PRT"
for o in PURCHASED: KIND[o.name] = "BUY"
for o in FASTENERS: KIND[o.name] = "FST"
for o in CABLES: KIND[o.name] = "CAB"
SOLIDS = PRINTED + PURCHASED
ALL = SOLIDS + FASTENERS + CABLES


def is_joint(o):
    return o is not None and o.type == 'EMPTY' and o.name.startswith("PIV_")


JOINTS = {}  # name -> spec dict
for e in O:
    if not is_joint(e):
        continue
    spec = {"axis": None, "lo": None, "hi": None, "home": 0.0, "step": None, "continuous": False}
    # cadlib props, then legacy "axis" prop (attempt-1 blends), then config overrides
    for k_src, k in (("joint_axis", "axis"), ("joint_lo", "lo"), ("joint_hi", "hi"), ("joint_home", "home"),
                     ("joint_step", "step"), ("joint_continuous", "continuous")):
        if k_src in e.keys():
            spec[k] = e[k_src]
    if spec["axis"] is None and "axis" in e.keys():
        spec["axis"] = str(e["axis"]).strip()[:1].upper()
    spec.update(CFG["joints"].get(e.name, {}))
    if spec["axis"] not in ("X", "Y", "Z"):
        spec["axis"] = None
    spec["base_rot"] = tuple(e.rotation_euler)
    JOINTS[e.name] = spec
COUPLE = dict(CFG["couplings"])
for e in O:
    if is_joint(e) and "couple_to" in e.keys() and e.name not in COUPLE:
        COUPLE[e.name] = {"to": e["couple_to"], "ratio": float(e.get("couple_ratio", 1.0))}


def joint_chain(o):
    """Joint ancestors of o, nearest first."""
    out, p = [], (o if is_joint(o) else o.parent)
    while p is not None:
        if is_joint(p):
            out.append(p.name)
        p = p.parent
    return out


def body(o):
    ch = joint_chain(o)
    return ch[0] if ch else "static"


def drivers(names):
    """Free variables behind a set of joints (coupled joints map to their driver)."""
    out = set()
    for n in names:
        while n in COUPLE:
            n = COUPLE[n]["to"]
        out.add(n)
    return frozenset(out)


def relevant_joints(a, b):
    return drivers(set(joint_chain(a)) ^ set(joint_chain(b)))


def set_pose(pose):
    """pose: {driver_joint: deg}. Unlisted joints go to home. Couplings applied."""
    vals = {}
    for n, s in JOINTS.items():
        vals[n] = pose.get(n, s.get("home", 0.0) or 0.0)
    for n, c in COUPLE.items():
        src = c["to"]
        vals[n] = vals.get(src, 0.0) * c["ratio"] + c.get("offset", 0.0)
    for n, s in JOINTS.items():
        if s["axis"] is None:
            continue
        e = O[n]
        r = list(s["base_rot"])
        r["XYZ".index(s["axis"])] = math.radians(vals[n])
        e.rotation_euler = r
    bpy.context.view_layer.update()


HOME = {}


def samples(jn, quick=False):
    """Angles to visit for one joint, with overtravel tagged."""
    s = JOINTS.get(jn)
    if not s or s["axis"] is None:
        return [(0.0, False)]
    if s.get("continuous"):
        st = s.get("step") or 45.0
        return [(a, False) for a in frange(0, 360 - 1e-6, st * (2 if quick else 1))]
    if s["lo"] is None or s["hi"] is None:
        return [(s.get("home", 0.0) or 0.0, False)]
    lo, hi = float(s["lo"]), float(s["hi"])
    st = s.get("step") or max(2.5, (hi - lo) / 12.0)
    if quick:
        st *= 2
    vals = [(a, False) for a in frange(lo, hi, st)]
    if abs(vals[-1][0] - hi) > 1e-6:
        vals.append((hi, False))
    ot = CFG["overtravel_deg"]
    if ot:
        vals = [(lo - ot, True)] + vals + [(hi + ot, True)]
    return vals


def frange(a, b, st):
    out, x = [], a
    while x <= b + 1e-9:
        out.append(round(x, 4))
        x += st
    return out


def thin(lst, k):
    if len(lst) <= k:
        return lst
    idx = sorted(set(round(i * (len(lst) - 1) / (k - 1)) for i in range(k)))
    return [lst[i] for i in idx]


def pose_grid(drv, quick=False, cap=None):
    drv = sorted(drv)
    if not drv:
        return [({}, False)]
    per = [samples(j, quick) for j in drv]
    cap = cap or CFG["max_poses_per_group"]
    while math.prod(len(p) for p in per) > cap:
        i = max(range(len(per)), key=lambda k: len(per[k]))
        if len(per[i]) <= 3:
            break
        per[i] = thin(per[i], max(3, len(per[i]) - 2))
    out = []
    for combo in itertools.product(*per):
        out.append(({j: a for j, (a, _) in zip(drv, combo)}, any(ot for _, ot in combo)))
    return out


def pose_key(p):
    return ", ".join("%s=%g" % (k.replace("PIV_", ""), v) for k, v in sorted(p.items())) or "home"


# ------------------------------------------------------------------ geometry helpers

def world_bm(o):
    bm = bmesh.new()
    if o.type == 'MESH':
        bm.from_mesh(o.data)
    bm.transform(o.matrix_world)
    return bm


def bvh_world(o):
    bm = world_bm(o)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


def bbox_world(o):
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return (Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb))),
            Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb))))


def bb_gap(A, B):
    (la, ha), (lb, hb) = A, B
    g = 0.0
    for k in range(3):
        d = max(lb[k] - ha[k], la[k] - hb[k], 0.0)
        g = max(g, d)
    return g


MANIFOLD_OK = {}


def manifold_ok(o):
    if o.name not in MANIFOLD_OK:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        MANIFOLD_OK[o.name] = all(e.is_manifold for e in bm.edges) and bm.calc_volume(signed=True) > 0
        bm.free()
    return MANIFOLD_OK[o.name]


_TMPC = None


def tmpcoll():
    global _TMPC
    if _TMPC is None or _TMPC.name not in bpy.data.collections:
        _TMPC = bpy.data.collections.new("CADCHECK_TMP")
        bpy.context.scene.collection.children.link(_TMPC)
    return _TMPC


def inter_volume(a, b):
    """Intersection volume (mm^3) and region bbox using a world-space copy; Manifold when both are manifold."""
    def wcopy(o):
        me = bpy.data.meshes.new(o.name + "_w")
        bm = world_bm(o)
        bm.to_mesh(me)
        bm.free()
        c = bpy.data.objects.new(o.name + "_w", me)
        tmpcoll().objects.link(c)
        return c
    A, B = wcopy(a), wcopy(b)
    m = A.modifiers.new("i", 'BOOLEAN')
    m.operation = 'INTERSECT'
    m.solver = 'MANIFOLD' if (manifold_ok(a) and manifold_ok(b)) else 'EXACT'
    m.object = B
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(A.evaluated_get(dg))
    bm = bmesh.new()
    bm.from_mesh(me)
    v = abs(bm.calc_volume())
    region = None
    if len(bm.verts):
        cs = [x.co for x in bm.verts]
        region = [[round(min(c[i] for c in cs), 1) for i in range(3)], [round(max(c[i] for c in cs), 1) for i in range(3)]]
    bm.free()
    solver = m.solver
    for o in (A, B):
        d = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(d)
    bpy.data.meshes.remove(me)
    return v, region, solver


def sample_pts(o, cap=4000):
    me = o.data
    mw = o.matrix_world
    pts = [mw @ v.co for v in me.vertices]
    me.calc_loop_triangles()
    pts += [mw @ t.center for t in me.loop_triangles]
    if len(pts) > cap:
        st = len(pts) / cap
        pts = [pts[int(i * st)] for i in range(cap)]
    return pts


def min_dist(a, b, ta, tb):
    best = (1e9, None)
    for p in sample_pts(a):
        r = tb.find_nearest(p)
        if r[0] is not None and r[3] < best[0]:
            best = (r[3], p)
    for p in sample_pts(b):
        r = ta.find_nearest(p)
        if r[0] is not None and r[3] < best[0]:
            best = (r[3], p)
    return best


_DIRS = (Vector((0.0123, 0.0071, 1)).normalized(), Vector((1, 0.0137, 0.0059)).normalized(), Vector((-0.577, 0.611, -0.541)).normalized())


def _parity(t, p, d, maxn=200):
    n, q = 0, p.copy()
    for _ in range(maxn):
        h = t.ray_cast(q, d, 1e5)
        if h[0] is None:
            break
        n += 1
        q = h[0] + d * 1e-4
    return n % 2 == 1


def inside(t, p, bb=None):
    """Point-in-solid by ray parity in three skewed directions (majority vote).
    Normal-sign tests (find_nearest) misfire near edges and concave corners."""
    if bb is not None and any(p[k] < bb[0][k] - 1e-3 or p[k] > bb[1][k] + 1e-3 for k in range(3)):
        return False
    return sum(_parity(t, p, d) for d in _DIRS) >= 2


def rule_for(a, b):
    """First matching rule in "allow" (designed overlap, skipped entirely) or "fits"
    (designed running fit: its own min_clearance, optional contact=true for thrust/bearing faces)."""
    for key in ("allow", "fits"):
        for rule in CFG.get(key, []):
            pa, pb = rule.get("a", "*"), rule.get("b", "*")
            if (fnmatch.fnmatch(a, pa) and fnmatch.fnmatch(b, pb)) or (fnmatch.fnmatch(b, pa) and fnmatch.fnmatch(a, pb)):
                return dict(rule, kind=key)
    return None


def allowed(a, b):
    r = rule_for(a, b)
    return r.get("why", "allowed") if r and r["kind"] == "allow" else None


REPORT = {"tool": "cadcheck", "blend": bpy.data.filepath, "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
          "config": {k: v for k, v in CFG.items() if k not in ("drop_tests",)}, "checks": {}, "coverage": [], "not_checked": []}
FAILS, WARNS = [], []


def finding(check, status, msg, **data):
    rec = {"status": status, "msg": msg, **data}
    REPORT["checks"].setdefault(check, {"findings": []})["findings"].append(rec)
    (FAILS if status == "fail" else WARNS if status == "warn" else []).append("%s: %s" % (check, msg))


# ------------------------------------------------------------------ parts

def bridge_span(tris):
    """Largest 'short side' over connected ceiling regions = the bridge length a slicer would need."""
    if not tris:
        return None
    key = lambda p: (round(p.x, 2), round(p.y, 2), round(p.z, 2))
    parent = list(range(len(tris)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    owner = {}
    for i, t in enumerate(tris):
        for p in t:
            k = key(p)
            if k in owner:
                parent[find(i)] = find(owner[k])
            else:
                owner[k] = i
    groups = {}
    for i, t in enumerate(tris):
        groups.setdefault(find(i), []).extend(t)
    best = 0.0
    for pts in groups.values():
        xs, ys = [p.x for p in pts], [p.y for p in pts]
        best = max(best, min(max(xs) - min(xs), max(ys) - min(ys)))
    return round(best, 1)


def check_parts():
    P = CFG["printers"]
    pref = CFG["prefer_printer"]
    cos_o = math.cos(math.radians(CFG["overhang_deg"]))
    set_pose({})
    rows = []
    seen = set()
    tot_g = tot_h = 0.0
    for o in sorted(PRINTED, key=lambda x: x.name):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        nm = sum(1 for e in bm.edges if not e.is_manifold)
        vol = bm.calc_volume(signed=True)
        area = sum(f.calc_area() for f in bm.faces)
        bm.free()
        R = Matrix(o["print_rot"]) if "print_rot" in o.keys() else Matrix.Identity(3)
        vs = [R @ (o.matrix_world @ v.co) for v in o.data.vertices]
        zmin = min(v.z for v in vs)
        dims = [max(v[i] for v in vs) - min(v[i] for v in vs) for i in range(3)]
        o.data.calc_loop_triangles()
        over = bed = ceil = 0.0
        ceil_tris = []
        for t in o.data.loop_triangles:
            a, b, c = (vs[i] for i in t.vertices)
            n = (b - a).cross(c - a)
            A = n.length / 2
            if A < 1e-9:
                continue
            n.normalize()
            zc = (a.z + b.z + c.z) / 3 - zmin
            if n.z < -0.999 and zc < 0.05:
                bed += A
            elif n.z < -0.985 and zc > 0.25:
                ceil += A          # horizontal ceiling: printable only as a bridge
                ceil_tris.append((a, b, c))
            elif n.z < -cos_o - 1e-3 and zc > 0.25:
                over += A          # sloped overhang steeper than the limit: needs support
        span = bridge_span(ceil_tris)
        # wall probe: ray from each face centre inward along -normal, opposite-facing hits only
        t = BVHTree.FromObject(o, bpy.context.evaluated_depsgraph_get())
        thin_n, samples_n, tmin, where = 0, 0, None, []
        for tri in o.data.loop_triangles:
            if tri.area < 0.3:
                continue
            n = tri.normal
            hit = t.ray_cast(tri.center - n * 0.01, -n, 50.0)
            if hit[0] is None or hit[1].dot(n) > -0.5:
                continue
            d = hit[3] + 0.01
            samples_n += 1
            tmin = d if tmin is None else min(tmin, d)
            if d < CFG["min_wall"] - 0.05:
                thin_n += 1
                w = o.matrix_world @ tri.center
                where.append([round(d, 2), [round(w.x, 1), round(w.y, 1), round(w.z, 1)]])
        sd = sorted(dims[:2])
        fits = {k: sd[0] <= sorted(v[:2])[0] and sd[1] <= sorted(v[:2])[1] and dims[2] <= v[2] for k, v in P.items()}
        infill = float(o.get("infill", 20))
        shell = min(abs(vol), area * 0.84)
        used = shell + max(0.0, abs(vol) - shell) * infill / 100.0
        g, h = used * CFG["pla_density"], used / CFG["flow_mm3_s"] / 3600 + 0.1
        stl = o.get("stl")
        if stl not in seen:
            tot_g += g
            tot_h += h
        seen.add(stl)
        row = {"object": o.name, "stl": stl, "non_manifold_edges": nm, "volume_mm3": round(vol, 1),
               "print_bbox_mm": [round(d, 1) for d in dims], "fits": fits, "has_print_rot": "print_rot" in o.keys(),
               "bed_contact_mm2": round(bed, 1), "overhang_gt_%g_mm2" % CFG["overhang_deg"]: round(over, 1),
               "ceiling_mm2": round(ceil, 1), "max_bridge_span_mm": span,
               "supports": o.get("supports"), "min_wall_mm": round(tmin, 2) if tmin else None,
               "thin_wall_samples": thin_n, "thin_wall_where": sorted(where)[:5], "est_g": round(g, 1), "est_h": round(h, 2)}
        rows.append(row)
        if nm or vol <= 0:
            finding("parts", "fail", "%s not a closed manifold solid (%d bad edges, vol %.1f)" % (o.name, nm, vol), object=o.name)
        if not any(fits.values()):
            finding("parts", "fail", "%s %s mm does not fit any printer" % (o.name, row["print_bbox_mm"]), object=o.name)
        elif not fits.get(pref, True):
            finding("parts", "warn", "%s does not fit %s" % (o.name, pref), object=o.name)
        if thin_n:
            finding("parts", "warn", "%s: %d wall samples < %.1f mm (min %.2f)" % (o.name, thin_n, CFG["min_wall"], tmin), object=o.name, where=row["thin_wall_where"])
        if bed < 20:
            finding("parts", "warn", "%s: only %.0f mm2 flat on the bed in print orientation" % (o.name, bed), object=o.name)
        nosup = str(o.get("supports", "")).lower() in ("no", "none", "false", "")
        if over > CFG.get("overhang_warn_mm2", 150) and nosup:
            finding("parts", "warn", "%s: %.0f mm2 of sloped overhang steeper than %g deg, supports=no" % (o.name, over, CFG["overhang_deg"]), object=o.name)
        if span and span > CFG.get("max_bridge_mm", 25) and nosup:
            finding("parts", "warn", "%s: ceiling region needs a %.0f mm bridge (limit %g)" % (o.name, span, CFG.get("max_bridge_mm", 25)), object=o.name)
        if "print_rot" not in o.keys():
            finding("parts", "warn", "%s has no print_rot; checked as modelled" % o.name, object=o.name)
    REPORT["checks"].setdefault("parts", {"findings": []}).update(
        {"rows": rows, "unique_stls": len(seen), "est_total_g": round(tot_g), "est_total_h": round(tot_h, 1)})
    REPORT["coverage"].append("parts: %d printed objects (%d unique STLs): manifold, bed fit %s, overhang, wall probe, bed contact" % (len(PRINTED), len(seen), list(P)))


# ------------------------------------------------------------------ interference + clearance over sweeps

def pair_class(a, b):
    ka, kb = KIND[a.name], KIND[b.name]
    same = body(a) == body(b)
    kinds = {ka, kb}
    if same:
        if kinds <= {"PRT", "BUY"}:
            return "solid"
        if kinds == {"FST"}:
            return "fst_fst"
        if "FST" in kinds and kinds & {"PRT", "BUY"}:
            return None  # threads bite into the part they hold; fastener check covers heads
        if kinds == {"CAB"}:
            return None
        return "cable"
    if kinds == {"CAB"}:
        return None
    return "moving"


def check_interference():
    groups = {}
    for a, b in itertools.combinations(ALL, 2):
        cls = pair_class(a, b)
        if cls is None:
            continue
        rule = rule_for(a.name, b.name)
        groups.setdefault(relevant_joints(a, b), []).append((a, b, cls, rule))
    res = {"groups": [], "collisions": [], "contacts": [], "solid_overlaps": [], "cable_overlaps": [], "min_clearance": []}
    worst = {}
    tested_pairs = 0
    for drv, pairs in sorted(groups.items(), key=lambda kv: len(kv[0])):
        grid = pose_grid(drv, QUICK)
        objs = {o.name: o for p in pairs for o in p[:2]}
        moving = {n for n, o in objs.items() if drivers(joint_chain(o)) & drv}
        static_cache = {}
        set_pose({})
        for n in objs:
            if n not in moving:
                static_cache[n] = (bvh_world(objs[n]), bbox_world(objs[n]))
        res["groups"].append({"joints": sorted(drv), "poses": len(grid), "pairs": len(pairs)})
        log("interference group %s: %d pairs x %d poses" % (sorted(drv) or "static", len(pairs), len(grid)))
        for pose, over in grid:
            set_pose(pose)
            cache = dict(static_cache)
            for n in moving:
                cache[n] = (bvh_world(objs[n]), bbox_world(objs[n]))
            for a, b, cls, rule in pairs:
                why = rule if rule and rule["kind"] == "allow" else None
                fit = rule if rule and rule["kind"] == "fits" else None
                (ta, ba), (tb, bb) = cache[a.name], cache[b.name]
                gap = bb_gap(ba, bb)
                margin = CFG["moving_warn_clearance"] if cls == "moving" else 0.01
                if gap > margin:
                    continue
                tested_pairs += 1
                ov = ta.overlap(tb)
                key = (a.name, b.name)
                if ov:
                    if why:
                        continue
                    vol, region, solver = inter_volume(a, b)
                    rec = {"a": a.name, "b": b.name, "pose": pose_key(pose), "overtravel": over, "tri_overlaps": len(ov),
                           "volume_mm3": round(vol, 2), "region": region, "solver": solver}
                    if cls == "moving":
                        tag = "collisions" if vol >= CFG["vol_tol"] else ("contacts" if not (fit and fit.get("contact")) else None)
                    elif cls == "cable":
                        tag = "cable_overlaps" if vol >= CFG["vol_tol"] else None
                    else:
                        tag = "solid_overlaps" if vol >= CFG["vol_tol"] else None
                    if tag:
                        prev = worst.get((tag, key))
                        if prev is None or rec["volume_mm3"] > prev["volume_mm3"] or (prev["overtravel"] and not over):
                            rec["n_poses"] = (prev or {}).get("n_poses", 0) + 1
                            rec["in_range_poses"] = (prev or {}).get("in_range_poses", 0) + (0 if over else 1)
                            worst[(tag, key)] = rec
                        else:
                            prev["n_poses"] += 1
                            prev["in_range_poses"] += 0 if over else 1
                elif cls == "moving" and not why and not (fit and fit.get("contact")):
                    d, p = min_dist(a, b, ta, tb)
                    prev = worst.get(("min_clearance", key))
                    if prev is None or d < prev["mm"]:
                        worst[("min_clearance", key)] = {"a": a.name, "b": b.name, "mm": round(d, 3), "pose": pose_key(pose),
                                                         "overtravel": over, "at": [round(c, 1) for c in p] if p else None,
                                                         "fit": fit.get("why") if fit else None,
                                                         "min": fit.get("min_clearance", CFG["moving_min_clearance"]) if fit else CFG["moving_min_clearance"]}
    set_pose({})
    for (tag, key), rec in worst.items():
        res[tag].append(rec)
    for tag in res:
        if tag != "groups":
            res[tag].sort(key=lambda r: -r.get("volume_mm3", 0) if "volume_mm3" in r else r.get("mm", 0))
    for r in res["collisions"]:
        if r["in_range_poses"]:
            finding("interference", "fail", "%s x %s collide on different bodies: %.1f mm3 at %s" % (r["a"], r["b"], r["volume_mm3"], r["pose"]), **r)
        else:
            finding("interference", "warn", "%s x %s collide only %.1f deg past the joint limit (%s): no margin" % (r["a"], r["b"], CFG["overtravel_deg"], r["pose"]), **r)
    for r in res["contacts"]:
        if r["in_range_poses"]:
            finding("interference", "fail", "%s x %s touch with zero clearance across a joint (rubbing) at %d poses, e.g. %s" % (r["a"], r["b"], r["in_range_poses"], r["pose"]), **r)
        else:
            finding("interference", "warn", "%s x %s touch just past the joint limit (%s)" % (r["a"], r["b"], r["pose"]), **r)
    for r in res["solid_overlaps"]:
        finding("interference", "fail", "%s x %s overlap %.1f mm3 on the same body" % (r["a"], r["b"], r["volume_mm3"]), **r)
    for r in res["cable_overlaps"]:
        finding("interference", "warn", "cable %s x %s overlap %.1f mm3 (route through solid?)" % (r["a"], r["b"], r["volume_mm3"]), **r)
    for r in res["min_clearance"]:
        lim = r["min"]
        if r["mm"] < lim and not r["overtravel"]:
            finding("clearance", "fail", "%s to %s only %.2f mm across a joint at %s (min %.2f%s)" % (
                r["a"], r["b"], r["mm"], r["pose"], lim, "; declared fit: " + r["fit"] if r["fit"] else "; declare it under fits if it is a running fit"), **r)
        elif r["mm"] < lim:
            finding("clearance", "warn", "%s to %s %.2f mm just past the limit (%s)" % (r["a"], r["b"], r["mm"], r["pose"]), **r)
        elif r["mm"] < CFG["moving_warn_clearance"] and not r["fit"]:
            finding("clearance", "warn", "%s to %s %.2f mm at %s" % (r["a"], r["b"], r["mm"], r["pose"]), **r)
    REPORT["checks"].setdefault("interference", {"findings": []}).update(res)
    swept = sorted({j for g in res["groups"] for j in g["joints"]})
    REPORT["coverage"].append("interference/clearance: %d objects in %s, %d pair-pose tests, joints swept %s with %.1f deg overtravel" % (
        len(ALL), list(COLL.values()), tested_pairs, swept, CFG["overtravel_deg"]))
    unswept = [n for n, s in JOINTS.items() if n not in COUPLE and (s["axis"] is None or (not s.get("continuous") and (s["lo"] is None or s["hi"] is None)))]
    if unswept:
        REPORT["not_checked"].append("joints with no range (home pose only): %s" % unswept)


# ------------------------------------------------------------------ fasteners

def fastener_axis(o):
    """(head_end, tip_end, into_dir, head_r, shank_r). Uses cadlib props, else infers from geometry."""
    if "fst_head" in o.keys() and "fst_dir" in o.keys():
        M = o.matrix_world
        h = M @ Vector(o["fst_head"])
        d = (M.to_3x3() @ Vector(o["fst_dir"])).normalized()
        L = float(o.get("fst_len", 10))
        return h, h + d * L, d, float(o.get("fst_head_d", 5.5)) / 2, float(o.get("fst_d", 3.0)) / 2
    vs = [o.matrix_world @ v.co for v in o.data.vertices]
    c = sum(vs, Vector()) / len(vs)
    # principal axis by power iteration on the covariance
    C = [[sum((v[i] - c[i]) * (v[j] - c[j]) for v in vs) for j in range(3)] for i in range(3)]
    e = Vector((1, 0.3, 0.1)).normalized()
    for _ in range(60):
        e = Vector([sum(C[i][j] * e[j] for j in range(3)) for i in range(3)])
        if e.length < 1e-12:
            e = Vector((0, 0, 1))
            break
        e.normalize()
    ts = [(v - c).dot(e) for v in vs]
    rs = [((v - c) - e * t).length for v, t in zip(vs, ts)]
    t0, t1 = min(ts), max(ts)
    big = max(rs)
    r_lo = max((r for r, t in zip(rs, ts) if t < t0 + 0.15 * (t1 - t0)), default=0)
    r_hi = max((r for r, t in zip(rs, ts) if t > t1 - 0.15 * (t1 - t0)), default=0)
    if r_lo > r_hi:   # head at the t0 end
        head, tip, d = c + e * t0, c + e * t1, e
    else:
        head, tip, d = c + e * t1, c + e * t0, -e
    shank = min(r_lo, r_hi)
    return head, tip, d, big, shank


def scene_bvh(objs, skip=()):
    bm = bmesh.new()
    for o in objs:
        if o.name in skip:
            continue
        t = world_bm(o)
        me = bpy.data.meshes.new("_t")
        t.to_mesh(me)
        t.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    return tree


def perp_basis(d):
    a = Vector((1, 0, 0)) if abs(d.x) < 0.9 else Vector((0, 1, 0))
    u = d.cross(a).normalized()
    return u, d.cross(u).normalized()


def access(head, out, tree, solids_trees, fc):
    """Drive a screw from `head` along `out`: ray bundle at driver radius until open space (hand_r) is reached."""
    u, v = perp_basis(out)
    rays = [Vector((0, 0, 0))] + [(u * math.cos(k * math.pi / 3) + v * math.sin(k * math.pi / 3)) * fc["driver_r"] for k in range(6)]
    start = head + out * 0.3
    hits = []
    for off in rays:
        h = tree.ray_cast(start + off, out, fc["max_reach_ext"] + 50)
        hits.append(h[3] if h[0] is not None else 1e9)
    blocked_at = min(hits)
    depth = None
    s = 0.0
    while s <= fc["max_reach_ext"]:
        p = start + out * s
        r = tree.find_nearest(p)
        if r[0] is None or r[3] >= fc["hand_r"]:
            depth = s
            break
        s += 2.0
    if depth is not None and blocked_at > depth:
        return {"reach_mm": round(depth, 1), "blocked": False}
    who = None
    if blocked_at < 1e8:
        p = start + out * blocked_at
        best = 1e9
        for n, t in solids_trees.items():
            r = t.find_nearest(p)
            if r[0] is not None and r[3] < best:
                best, who = r[3], n
    return {"reach_mm": None, "blocked": True, "blocked_at_mm": round(blocked_at, 1) if blocked_at < 1e8 else None, "blocked_by": who}


def assembly_present():
    """object name -> set of solids present when it is installed (None = unknown, assume all).

    assembly_order: [{"step": "...", "objects": [globs], "bench": "<group>"?, "merge": "<group>"?}, ...]
    A bench step builds a sub-assembly away from the rest; a later step with merge=<group> brings it in.
    """
    steps = CFG.get("assembly_order") or []
    if not steps:
        return {}
    names = [o.name for o in ALL]
    step_of = {}
    for i, st in enumerate(steps):
        for n in names:
            if n not in step_of and any(fnmatch.fnmatch(n, g) for g in st["objects"]):
                step_of[n] = i
    unordered = sorted(n for n in names if n not in step_of and KIND[n] in ("PRT", "BUY"))
    REPORT.setdefault("assembly", {})["unordered_solids_assumed_present"] = unordered
    merged_at = {st["merge"]: i for i, st in enumerate(steps) if st.get("merge")}
    out = {}
    solids = [o.name for o in SOLIDS]
    for n in names:
        if n not in step_of:
            continue
        i = step_of[n]
        grp = steps[i].get("bench")
        pres = set(unordered)
        for m in solids:
            j = step_of.get(m)
            if j is None or j > i:
                continue
            g2 = steps[j].get("bench")
            if grp:
                if g2 == grp:
                    pres.add(m)
            elif g2 is None or merged_at.get(g2, 1e9) <= i:
                pres.add(m)
        out[n] = pres
    return out


def check_fasteners():
    fc = CFG["fasteners"]
    if not FASTENERS:
        REPORT["not_checked"].append("fasteners: Fasteners collection is empty; screws are not modelled")
        return
    rows = []
    # poses: home plus each driver joint at its limits (coarse); access may need the mechanism moved
    poses = [({}, "home")]
    for jn, s in JOINTS.items():
        if jn in COUPLE or s["axis"] is None or s.get("continuous") or s["lo"] is None:
            continue
        for a in (s["lo"], s["hi"]):
            if abs(a - (s.get("home") or 0)) > 1e-6:
                poses.append(({jn: a}, pose_key({jn: a})))
    geo = {}
    set_pose({})
    for o in FASTENERS:
        geo[o.name] = fastener_axis(o)
    per = {o.name: {} for o in FASTENERS}
    present = assembly_present()
    for pose, pk in poses:
        set_pose(pose)
        trees = {o.name: (bvh_world(o), bbox_world(o)) for o in SOLIDS}
        tree_cache = {}
        for o in FASTENERS:
            head, tip, d, hr, sr = fastener_axis(o) if pose else geo[o.name]
            if not pose:
                u, v = perp_basis(d)
                L = (tip - head).length
                # thread engagement: walk back from the tip, ring of points at 92% of the shank radius
                ring = [(u * math.cos(k * math.pi / 3) + v * math.sin(k * math.pi / 3)) * sr * 0.92 for k in range(6)]
                eng, host, s_ = 0.0, None, 0.5
                while s_ < L - 0.5:
                    c = tip - d * s_
                    hits = {}
                    for n, (t, bb) in trees.items():
                        k = sum(1 for r in ring if inside(t, c + r, bb))
                        if k >= 4:
                            hits[n] = k
                    if host is None and hits:
                        host = max(hits, key=hits.get)
                    if host is not None:
                        if host in hits:
                            eng += 0.5
                        elif eng:
                            break
                    s_ += 0.5
                # points inside the head (just behind its bearing face), on axis and at 80% radius
                hring = [(u * math.cos(k * math.pi / 2) + v * math.sin(k * math.pi / 2)) * hr * 0.8 for k in range(4)]
                head_pts = [head - d * 0.6 + r for r in hring] + [head - d * 0.6]
                buried = sorted({n for n, (t, bb) in trees.items() for p in head_pts if inside(t, p, bb)})
                per[o.name].update({"head": [round(c, 1) for c in head], "into": [round(c, 3) for c in d],
                                    "length_mm": round(L, 1), "thread_host": host, "engagement_mm": eng,
                                    "head_buried_in": buried, "body": body(o)})
            pres = present.get(o.name)
            key = frozenset(pres) if pres is not None else None
            if key not in tree_cache:
                objs = [x for x in SOLIDS if pres is None or x.name in pres]
                tree_cache[key] = scene_bvh(objs)
            acc = access(head, -d, tree_cache[key], {n: t for n, (t, bb) in trees.items() if pres is None or n in pres}, fc)
            per[o.name].setdefault("access", {})[pk] = acc
    set_pose({})
    for n, r in per.items():
        acc = r["access"]
        ok = {pk: a for pk, a in acc.items() if not a["blocked"]}
        best = min(ok.items(), key=lambda kv: kv[1]["reach_mm"]) if ok else None
        r["access_best"] = {"pose": best[0], **best[1]} if best else None
        rows.append({"object": n, **r})
        if r["head_buried_in"]:
            finding("fasteners", "fail", "%s head is inside %s (reversed, or a missing counterbore)" % (n, r["head_buried_in"]), object=n)
        if not r["thread_host"]:
            finding("fasteners", "warn", "%s: no material grips the thread (floating screw, or every hole is clearance)" % n, object=n)
        elif r["engagement_mm"] < fc.get("min_engagement", 4.0):
            finding("fasteners", "warn", "%s: only %.1f mm of thread in %s" % (n, r["engagement_mm"], r["thread_host"]), object=n)
        if not ok:
            h = acc["home"]
            finding("fasteners", "fail", "%s cannot be driven: tool path blocked by %s at %s mm (all %d poses tried)" % (
                n, h.get("blocked_by"), h.get("blocked_at_mm"), len(acc)), object=n)
        elif "home" not in ok:
            finding("fasteners", "warn", "%s reachable only at %s (blocked at home pose)" % (n, best[0]), object=n)
        elif best[1]["reach_mm"] > fc["max_reach_ext"]:
            finding("fasteners", "fail", "%s sits %.0f mm deep" % (n, best[1]["reach_mm"]), object=n)
        elif best[1]["reach_mm"] > fc["max_reach"]:
            finding("fasteners", "warn", "%s needs a %.0f mm+ bit/extension (head %.0f mm below open space)" % (n, best[1]["reach_mm"] + 10, best[1]["reach_mm"]), object=n)
    REPORT["checks"].setdefault("fasteners", {"findings": []})["rows"] = rows
    REPORT["coverage"].append("fasteners: %d screws; head-buried, thread engagement, driver access (Ø%.0f bit, %.0f mm hand clearance) at %d poses, %s" % (
        len(FASTENERS), 2 * fc["driver_r"], fc["hand_r"], len(poses),
        "parts present per assembly_order (%d steps)" % len(CFG.get("assembly_order", [])) if CFG.get("assembly_order") else "ALL parts present (no assembly_order: later parts may block falsely)"))
    if not CFG.get("assembly_order"):
        REPORT["not_checked"].append("fasteners: assembly order (declare assembly_order so access is tested against the parts present at that step)")
    REPORT["not_checked"].append("fasteners: pilot/clearance hole diameters (use cadlib.features for those)")


# ------------------------------------------------------------------ drop tests

def frame_point(frame, p_home, home_mats):
    if not frame or frame == "world":
        return Vector(p_home)
    return O[frame].matrix_world @ home_mats[frame].inverted() @ Vector(p_home)


def check_drop():
    tests = CFG["drop_tests"]
    if not tests:
        REPORT["not_checked"].append("drop: no drop_tests configured (feed paths unsimulated)")
        return
    set_pose({})
    home_mats = {n: O[n].matrix_world.copy() for n in JOINTS}
    out = []
    for T in tests:
        em = T["emit"]
        g = Vector(T.get("dir", [0, 0, -1])).normalized()
        poses = []
        if "poses" in T:
            keys = sorted(T["poses"])
            for combo in itertools.product(*[T["poses"][k] for k in keys]):
                poses.append(dict(zip(keys, combo)))
        else:
            poses = [p for p, _ in pose_grid(frozenset(T.get("sweep", [])), QUICK)]
        r_emit, st = em.get("radius", 6.0), em.get("step", 2.0)
        n_e = Vector(em.get("normal", [0, 0, 1]))
        u, v = perp_basis(n_e.normalized())
        offs = [(i, j) for i in frange(-r_emit, r_emit, st) for j in frange(-r_emit, r_emit, st) if i * i + j * j <= r_emit * r_emit + 1e-6]
        exp = T.get("expect", {})
        rows = []
        for pose in poses:
            set_pose(pose)
            trees = {o.name: (bvh_world(o), o) for o in SOLIDS + FASTENERS if o.name not in T.get("ignore", [])}
            hits = {}
            angles = []
            for (i, j) in offs:
                p_home = Vector(em["center"]) + u * i + v * j
                p = frame_point(em.get("frame"), p_home, home_mats)
                best = None
                for n, (t, o) in trees.items():
                    h = t.ray_cast(p, g, T.get("max_mm", 400))
                    if h[0] is not None and (best is None or h[3] < best[0]):
                        best = (h[3], n, h[0])
                name = best[1] if best else None
                hits[name] = hits.get(name, 0) + 1
                ang = exp.get("angle")
                if best and ang and name in exp.get("hit", [name]):
                    c = O[ang["center"]].matrix_world.translation
                    F = O[ang.get("frame", ang["center"])].matrix_world.to_3x3()
                    loc = F.inverted() @ (best[2] - c)
                    ax = "XYZ".index(ang.get("axis", "X"))
                    zero = "XYZ".index(ang.get("zero", "Z"))
                    pos_s = ang.get("positive", "-Y")
                    sg = -1 if pos_s.startswith("-") else 1
                    pk = "XYZ".index(pos_s[-1])
                    angles.append(math.degrees(math.atan2(sg * loc[pk], loc[zero])))
            row = {"pose": pose_key(pose), "rays": len(offs), "first_hit": hits}
            if angles:
                row["angle_deg"] = [round(min(angles), 1), round(max(angles), 1)]
            rows.append(row)
            want_hit = exp.get("hit")
            bad = sum(c for n, c in hits.items() if want_hit and n not in want_hit)
            if bad:
                finding("drop", "fail", "%s at %s: %d/%d rays first hit %s, not %s" % (
                    T["name"], row["pose"], bad, len(offs), sorted(n for n in hits if n not in want_hit), want_hit), test=T["name"], pose=row["pose"])
            if angles and exp.get("angle", {}).get("range"):
                lo, hi = exp["angle"]["range"]
                if min(angles) < lo or max(angles) > hi:
                    finding("drop", "fail", "%s at %s: lands %.0f..%.0f deg, window %g..%g" % (
                        T["name"], row["pose"], min(angles), max(angles), lo, hi), test=T["name"], pose=row["pose"])
        out.append({"name": T["name"], "rows": rows})
    set_pose({})
    REPORT["checks"].setdefault("drop", {"findings": []})["tests"] = out
    REPORT["coverage"].append("drop: %d tests (first-contact straight rays; no bounce/slide dynamics)" % len(tests))


# ------------------------------------------------------------------ slide-out, distances

def check_slide():
    for S in CFG["slide_out"]:
        set_pose(S.get("pose", {}))
        ob = O[S["object"]]
        d = Vector(S["dir"]).normalized()
        others = {o.name: bvh_world(o) for o in SOLIDS if o.name != ob.name and not allowed(o.name, ob.name)}
        bm0 = world_bm(ob)
        free_until, blocker = None, None
        minclr = (1e9, None)
        M0 = ob.matrix_world.copy()
        for s in frange(0, S["dist"], S.get("step", 5)):
            bm = bm0.copy()
            bmesh.ops.translate(bm, verts=bm.verts, vec=d * s)
            t = BVHTree.FromBMesh(bm)
            pts = [v.co.copy() for v in bm.verts][:: max(1, len(bm.verts) // 1500)]
            bm.free()
            hit = []
            for n, ot in others.items():
                if t.overlap(ot):
                    ob.matrix_world = Matrix.Translation(d * s) @ M0
                    bpy.context.view_layer.update()
                    vol, _, _ = inter_volume(ob, O[n])
                    ob.matrix_world = M0
                    bpy.context.view_layer.update()
                    if vol >= CFG["vol_tol"]:
                        hit.append(n)
            if hit:
                free_until, blocker = s, hit
                break
            for n, ot in others.items():
                for p in pts:
                    r = ot.find_nearest(p, 3.0)
                    if r[0] is not None and r[3] < minclr[0]:
                        minclr = (r[3], n)
        bm0.free()
        rec = {"object": ob.name, "dir": list(d), "dist": S["dist"], "blocked_at_mm": free_until, "blocked_by": blocker,
               "min_clearance_mm": round(minclr[0], 2) if minclr[1] else None, "closest": minclr[1]}
        REPORT["checks"].setdefault("slide", {"findings": []}).setdefault("rows", []).append(rec)
        if blocker:
            finding("slide", "fail", "%s slide-out blocked by %s at %g mm" % (ob.name, blocker, free_until), **rec)
        elif minclr[1] and minclr[0] < S.get("min_clearance", 1.5):
            finding("slide", "warn", "%s slides out but with only %.2f mm to %s" % (ob.name, minclr[0], minclr[1]), **rec)
    set_pose({})
    if CFG["slide_out"]:
        REPORT["coverage"].append("slide: %d slide-out sweeps" % len(CFG["slide_out"]))


def check_distances():
    for D in CFG["distances"]:
        poses = D.get("poses", [D.get("pose", {})])
        for pose in poses:
            set_pose(pose)
            a, b = O[D["a"]], O[D["b"]]
            d, p = min_dist(a, b, bvh_world(a), bvh_world(b))
            rec = {"a": a.name, "b": b.name, "pose": pose_key(pose), "mm": round(d, 3), "min": D.get("min"), "max": D.get("max"), "why": D.get("why")}
            REPORT["checks"].setdefault("distances", {"findings": []}).setdefault("rows", []).append(rec)
            if (D.get("min") is not None and d < D["min"]) or (D.get("max") is not None and d > D["max"]):
                finding("distances", "fail", "%s to %s = %.2f mm at %s, wanted %s..%s (%s)" % (a.name, b.name, d, rec["pose"], D.get("min"), D.get("max"), D.get("why", "")), **rec)
    set_pose({})


# ------------------------------------------------------------------ stability

def centroid_vol(o):
    bm = world_bm(o)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    v6, c = 0.0, Vector()
    for f in bm.faces:
        a, b, d = (l.vert.co for l in f.loops)
        vol = a.dot(b.cross(d))
        v6 += vol
        c += vol * (a + b + d) / 4.0
    bm.free()
    if abs(v6) < 1e-9:
        lo, hi = bbox_world(o)
        return (lo + hi) / 2, 0.0
    return c / v6, abs(v6) / 6


def hull2d(pts):
    pts = sorted(set((round(x, 3), round(y, 3)) for x, y in pts))
    if len(pts) < 3:
        return pts
    cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def check_stability():
    set_pose({})
    statics = [o for o in SOLIDS if body(o) == "static"]
    if not statics:
        return
    zmin = min(min((o.matrix_world @ v.co).z for v in o.data.vertices) for o in statics)
    foot = [((o.matrix_world @ v.co).x, (o.matrix_world @ v.co).y) for o in statics for v in o.data.vertices if (o.matrix_world @ v.co).z < zmin + 0.6]
    hull = hull2d(foot)
    masses = CFG["masses_g"]
    rows = []
    missing = [o.name for o in PURCHASED if not any(fnmatch.fnmatch(o.name, k) for k in masses) and "mass_g" not in o.keys()]
    drv = frozenset(n for n in JOINTS if n not in COUPLE and not JOINTS[n].get("continuous"))
    for pose, over in pose_grid(drv, True, cap=27):
        if over:
            continue
        set_pose(pose)
        M, S = 0.0, Vector()
        for o in SOLIDS:
            c, vol = centroid_vol(o)
            if KIND[o.name] == "PRT":
                inf = float(o.get("infill", 20)) / 100
                m = vol * CFG["pla_density"] * (0.45 + 0.55 * inf)
            else:
                m = float(o.get("mass_g", next((v for k, v in masses.items() if fnmatch.fnmatch(o.name, k)), 0.0)))
            M += m
            S += c * m
        cg = S / M
        # signed distance from CG projection to the hull boundary (positive inside)
        dmin = 1e9
        for i in range(len(hull)):
            (x1, y1), (x2, y2) = hull[i], hull[(i + 1) % len(hull)]
            ex, ey = x2 - x1, y2 - y1
            L = math.hypot(ex, ey) or 1e-9
            dmin = min(dmin, ((cg.x - x1) * ey - (cg.y - y1) * ex) / L * -1)
        h = cg.z - zmin
        rows.append({"pose": pose_key(pose), "mass_g": round(M), "cg": [round(c, 1) for c in cg], "edge_margin_mm": round(dmin, 1),
                     "tip_angle_deg": round(math.degrees(math.atan2(dmin, h)), 1)})
    set_pose({})
    worst = min(rows, key=lambda r: r["tip_angle_deg"])
    REPORT["checks"].setdefault("stability", {"findings": []}).update({"rows": rows, "worst": worst, "footprint_pts": len(hull), "purchased_without_mass": missing})
    if worst["tip_angle_deg"] < 10:
        finding("stability", "fail", "static tip angle only %.1f deg at %s" % (worst["tip_angle_deg"], worst["pose"]), **worst)
    elif worst["tip_angle_deg"] < 20:
        finding("stability", "warn", "static tip angle %.1f deg at %s" % (worst["tip_angle_deg"], worst["pose"]), **worst)
    if missing:
        finding("stability", "warn", "no mass for %d purchased parts (counted as 0 g): %s" % (len(missing), missing[:6]))
    REPORT["coverage"].append("stability: CG and tip angle over %d poses, footprint from static parts' lowest faces" % len(rows))
    REPORT["not_checked"].append("stability: dynamic loads (recoil, pan acceleration), friction/sliding")


def check_cables():
    rows = []
    for o in CABLES:
        L = o.get("path_len")
        lead = o.get("lead_len") or next((v for k, v in CFG["cable_leads"].items() if fnmatch.fnmatch(o.name, k)), None)
        rows.append({"object": o.name, "path_len": L, "lead_len": lead})
        if L is not None and lead is not None and L > lead:
            finding("cables", "fail", "%s route is %.0f mm but the lead is %.0f mm" % (o.name, L, lead), object=o.name)
    REPORT["checks"].setdefault("cables", {"findings": []})["rows"] = rows
    have = sum(1 for r in rows if r["path_len"] is not None)
    REPORT["coverage"].append("cables: %d routes, %d with path length" % (len(rows), have))
    REPORT["not_checked"].append("cables: bend radius, slack across joints, connector positions (review by section render)")


# ------------------------------------------------------------------ main

def main():
    log("objects: %d printed, %d purchased, %d fasteners, %d cables; joints %s" % (
        len(PRINTED), len(PURCHASED), len(FASTENERS), len(CABLES),
        {n: (s["axis"], s["lo"], s["hi"]) for n, s in JOINTS.items()}))
    for name, fn in (("parts", check_parts), ("interference", check_interference), ("fasteners", check_fasteners),
                     ("drop", check_drop), ("slide", check_slide), ("distances", check_distances),
                     ("stability", check_stability), ("cables", check_cables)):
        if want(name) or (name == "interference" and want("clearance")):
            t = time.time()
            fn()
            REPORT["checks"].setdefault(name, {"findings": []})["runtime_s"] = round(time.time() - t, 1)
            log("%s done" % name)
    if not CABLES:
        REPORT["not_checked"].append("cables: Cables collection empty")
    REPORT["not_checked"].append("not geometric: service/teardown steps, alignment jigs, aesthetics, BOM correctness")
    REPORT["summary"] = {"pass": not FAILS, "fails": len(FAILS), "warns": len(WARNS), "fail_list": FAILS, "warn_list": WARNS[:60],
                         "coverage": REPORT["coverage"], "not_checked": REPORT["not_checked"], "runtime_s": round(time.time() - T0, 1)}
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(REPORT, f, indent=1, default=str)
    print("CADCHECK %s: %d fail, %d warn -> %s" % ("PASS" if not FAILS else "FAIL", len(FAILS), len(WARNS), OUT))
    for s in FAILS[:40]:
        print("  FAIL", s)
    for s in WARNS[:25]:
        print("  warn", s)
    if len(WARNS) > 25:
        print("  ... %d more warnings in the report" % (len(WARNS) - 25))
    print("  not checked:", "; ".join(REPORT["not_checked"]))


main()
