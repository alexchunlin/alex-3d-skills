"""cadcheck: evidence-producing checks for a printable Blender assembly.

    Blender -b model.blend --python cadcheck.py -- [--config checks.json] [--out report.json]
                                                   [--only parts,interference,...] [--quick]
                                                   [--overlay extra.json ... [--overlay-only]]

--overlay merges another config on top (repeatable): list sections (drop_tests, slide_out, service, distances, ...)
are appended (allow and fits rules go first, so they win), dict sections updated. With --overlay-only, list sections
named in the overlays replace the base rows, so `--only drop,slide --overlay mine.json --overlay-only` runs just
your rows. The v2 A1 reviewer spent about 5.5 of 14.7 min hand-building copies of checks.json with sections emptied
(FINDINGS V2A1-T6).

Works on any .blend that follows the conventions in ../SKILL.md (collections Printed / Purchased /
Fasteners / Cables, moving links parented under PIV_* empties). Joint ranges come from PIV_* custom
properties written by cadlib.asm.joint() or from the "joints" block of the config.

Checks (each one writes evidence into the JSON report, with an explicit `coverage` list):
  parts         manifold, volume, print-orientation bed fit, overhang area, min wall, bed contact, and the layer support
                check (printcheck.py: bridges, cantilevers, islands per 0.2 mm layer) on the exported STLs
  interference  every pair in ALL four collections, swept over the joints that separate the two bodies,
                including overtravel past each limit; contacts between different bodies are failures
  clearance     min distance between parts on different bodies over the same sweep
  fasteners     head not buried, thread engagement (bolt-to-nut pairing), shanks or nuts inside purchased
                parts, driver access (straight bit, then an L-key with a swing arc) per pose, including the
                fastener's own continuous joints; head stand-off and protruding thread
  service       tool access for service operations from config ("service"): whole assembly present,
                listed parts removed, at the stated pose
  drop          drop tests from config ("drop_tests"): straight rays, or mode "slide" (fall, slide on walls,
                stall below stall_deg) with landing-angle windows
  index         indexer timing from config ("index_tests"): open windows of a probe through a moving
                disc over a motion cycle (one window = one candy per cycle)
  slide         slide-out sweeps from config ("slide_out"), one object or a group
  distances     min/max distance assertions from config ("distances"), optionally as a gap along a ray (or the worst of a ray swept over a passage, "sweep"),
                with payload squeeze and a declared compliant element
  assembly      assembly_order audit: objects in no step, step labels whose screw size disagrees with the model,
                steps that move a servo-held joint before any step is "powered" (held poses)
  insertion     each part and each merged bench group out along a straight line past the earlier steps' parts
  stacks        tolerance stacks from config ("stacks"): worst case and RSS against a limit
  flexures      declared springs and snap arms: beam direction vs the part's print orientation (layer bonds)
  stability     centre of mass and static tip angle over a coarse pose grid
  cables        path length vs. lead length, chains, junctions, ends that come apart across a joint, kinked corners,
                two routes in one tube, exposed cable

Evidence for the rules here: docs/FINDINGS.md A1-F1, F3, F4, F5, F9, F10, F11, F13, F14, A2-F1 to F9, A3-F1 to F3, F7, F8 and A3-V1.
"""
import bpy, bmesh, json, math, os, re, sys, time, fnmatch, glob, itertools
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cadlib import joints as JT   # noqa: E402  (joint specs and posing, shared with cadlib.route)

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _arg(name, default=None):
    # the last one wins: `cad check m.blend c.json --only x --out y` put the wrapper's default --out first and y was
    # ignored, so a precheck overwrote the designer's cadcheck.json (v2 A5 progress.md "Tool issues", FINDINGS V2A5-T1)
    return ARGV[len(ARGV) - 1 - ARGV[::-1].index(name) + 1] if name in ARGV else default


DEFAULTS = {
    "collections": {"printed": "Printed", "purchased": "Purchased", "fasteners": "Fasteners", "cables": "Cables"},
    "printers": {"P1S": [256, 256, 256], "H2D": [325, 320, 325]},
    "prefer_printer": "P1S",
    "min_wall": 1.6,
    "overhang_deg": 45.0,
    "joints": {},
    "couplings": {},
    "overtravel_deg": 2.5,
    "overtravel_mm": 1.0,       # past the ends of a prismatic (slide) joint
    "max_poses_per_group": 48,
    "allow": [],
    "vol_tol": 0.5,
    "moving_min_clearance": 0.5,
    "moving_warn_clearance": 1.0,
    # thread engagement, in shank diameters: 2 d self-tapped or PLA-tapped into a printed part, 1.5 d into a tapped
    # purchased (metal) part. A project "min_engagement" (mm) overrides both, as before.
    "fasteners": {"driver_r": 3.0, "hand_r": 14.0, "max_reach": 60.0, "max_reach_ext": 150.0,
                  "min_engagement_d": 2.0, "tapped_engagement_d": 1.5,
                  # 2.5 mm hex key for M3 socket heads (ISO 2936 short leg ~20, long ~58): A2-F1
                  "lkey_short": 18.0, "lkey_insert": 2.5, "lkey_long": 56.0, "lkey_r": 1.25, "lkey_swing_deg": 60.0,
                  "max_standoff": 2.0, "max_protrusion": 3.0, "captive": {},
                  # ISO 4762 / 7045 / 10642 lengths commonly stocked (mm), by shank diameter
                  "stock_lengths": {"2": [3, 4, 5, 6, 8, 10, 12, 14, 16, 20],
                                    "2.5": [3, 4, 5, 6, 8, 10, 12, 14, 16, 20, 25],
                                    "3": [3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 30, 35, 40, 45, 50],
                                    "4": [4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 35, 40, 45, 50],
                                    "5": [6, 8, 10, 12, 14, 16, 20, 25, 30, 35, 40, 45, 50]},
                  "stock_ok": []},
    "service": [],
    "index_tests": [],
    "stacks": [],
    # exposed = >= min_escape of 26 rays leave the assembly (R2's bare bus run scored 10-12), or >= view_frac of 240
    # directions toward a viewer above or level (z > view_z) do. A3's bonnet-foot notch scores 6/26 and was missed;
    # at 10% of the viewer directions it is 8.3 mm long (R3: "about 8 mm"), FINDINGS A3-F7
    "exposure": {"max_cable_mm": 5.0, "cables_ok": [], "min_escape": 8, "view_frac": 0.10, "view_z": -0.2, "nuts_ok": []},
    "carry": {},
    "flexures": [],
    "drop_tests": [],
    "slide_out": [],
    "distances": [],
    "payload_fit": [],
    "sightlines": [],
    "masses_g": {},
    "pla_density": 1.24e-3,
    "flow_mm3_s": 12.0,
    "cable_leads": {},
    "cable_chains": [],         # [{"name", "cables": [CAB_a, CAB_b, ...], "lead": mm, "why"}]: one conductor run, one lead
    "cable_junctions_ok": [],   # globs of cables whose meeting ends are a real connector
    "cable_min_bend_od": 0.75,  # a corner whose centreline radius is under this x OD is a kink (V2A7-F2)
    "joint_drives": {},         # {"PIV_x": "BUY_servo_x" or null}: what holds a joint during assembly (default: by name)
    # [{"match": "substring of the warn text", "why": "..."}]: a warn you looked at and accept. The summary counts
    # untriaged warns separately. v2 A1 finished at 0 fails, 34 warns; 3 of R1's issues (A1-05, 07, 08) were warns
    # in that list that nobody acted on (FINDINGS V2A1-F5)
    "accepted_warns": [],
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
_replaced = set()
for _ov in [ARGV[i + 1] for i, a in enumerate(ARGV[:-1]) if a == "--overlay"]:     # repeatable
    with open(_ov) as f:
        extra = json.load(f)
    for k, v in extra.items():
        if isinstance(v, list) and isinstance(CFG.get(k), list):
            if "--overlay-only" in ARGV and k not in _replaced:
                CFG[k], _ = list(v), _replaced.add(k)
            else:
                CFG[k] = v + CFG[k] if k in ("allow", "fits", "accepted_warns") else CFG[k] + v   # first matching rule wins
        elif isinstance(v, dict) and isinstance(CFG.get(k), dict):
            CFG[k].update(v)
        else:
            CFG[k] = v


def _load_params():
    """The build's named parameters: --params file, the scene (cadlib.asm.new_scene stores them), or the manifest.json
    beside the blend."""
    for src in [_arg("--params")] + [None, os.path.join(os.path.dirname(bpy.data.filepath) or ".", "manifest.json")]:
        if src is None and "cad_params" in bpy.context.scene.keys():
            return json.loads(bpy.context.scene["cad_params"]), "scene"
        if src and os.path.isfile(src):
            with open(src) as f:
                m = json.load(f)
            return m.get("params", m), src
    return {}, None


PARAMS, PARAMS_SRC = _load_params()
EXPRS = []   # [{"at", "expr", "value" or "error"}]


def _eval_exprs(x, at):
    """A config string that starts with "=" is a Python expression over the build's params: "min": "=MM_T[1] + TAPE_T".
    v2 A3 sized the full-lift gap row for the nominal candy (a hand-typed 7.5 = MM_T_NOM + tape) while params
    declared MM_T up to 7.5, so the row passed and the reviewer's max-candy row failed (V2A3-F1). A row written
    against the param range follows it when the params change."""
    if isinstance(x, dict):
        return {k: _eval_exprs(v, "%s.%s" % (at, k)) for k, v in x.items()}
    if isinstance(x, list):
        return [_eval_exprs(v, "%s[%d]" % (at, i)) for i, v in enumerate(x)]
    if isinstance(x, str) and x.startswith("="):
        try:
            v = eval(x[1:], {"__builtins__": {}, "min": min, "max": max, "abs": abs, "round": round, "sqrt": math.sqrt,
                             "math": math}, dict(PARAMS))
            if isinstance(v, tuple):
                v = list(v)
            EXPRS.append({"at": at, "expr": x[1:], "value": v})
            return v
        except Exception as e:
            EXPRS.append({"at": at, "expr": x[1:], "error": "%s: %s" % (type(e).__name__, e)})
            return None
    return x


for _k in list(CFG):
    if _k != "accepted_warns":
        CFG[_k] = _eval_exprs(CFG[_k], _k)
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

# "carry": {"glob": "PIV_x"} re-parents objects onto a joint for every sweep, keeping their home pose. For parts
# modelled on one body at one setting that ride on another in use (A3: the nip thumbwheel and its nut sit on the pod
# in the model but ride on the backplate stud; swept as fixed they gave 4 false fails, FINDINGS A3-V1).
bpy.context.view_layer.update()
CARRIED = {}    # name -> original parent, so a tool that saves the blend (cadq route --save) can undo the carry
for _g, _piv in CFG["carry"].items():
    for _o in [x for x in ALL if fnmatch.fnmatch(x.name, _g)]:
        _mw = _o.matrix_world.copy()
        CARRIED.setdefault(_o.name, _o.parent)
        _o.parent = O[_piv]
        _o.matrix_world = _mw
bpy.context.view_layer.update()


HOME_MW = {}


def is_nut(o):
    """Nuts (cadlib asm.nut sets fst_kind; otherwise the name says so). A2 modelled the first nuts: treating them
    as screws gave 12 false fails ("head buried", "cannot be driven"), FINDINGS A2-V1."""
    k = o.get("fst_kind")
    return k == "nut" if k else "nut" in o.name.lower().replace("fst_", "", 1)


def is_joint(o):
    return o is not None and o.type == 'EMPTY' and o.name.startswith("PIV_")


# name -> spec dict: cadlib props, then legacy "axis" prop (attempt-1 blends), then config overrides (cadlib/joints.py)
JOINTS = {e.name: JT.spec(e, CFG["joints"].get(e.name, {})) for e in O if is_joint(e)}
OT_TEXT = "%.1f deg" % CFG["overtravel_deg"] + (" (%g mm on slides)" % CFG["overtravel_mm"] if any(s["kind"] == "prismatic" for s in JOINTS.values()) else "")
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
    """pose: {driver_joint: deg, or mm on a slide}. Unlisted joints go to home. Couplings applied (cadlib/joints.py)."""
    JT.apply(JOINTS, COUPLE, pose, O)


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
    pr = s.get("kind") == "prismatic"
    st = s.get("step") or max(1.0 if pr else 2.5, (hi - lo) / 12.0)
    if quick:
        st *= 2
    vals = [(a, False) for a in frange(lo, hi, st)]
    if abs(vals[-1][0] - hi) > 1e-6:
        vals.append((hi, False))
    ot = CFG["overtravel_mm"] if pr else CFG["overtravel_deg"]
    if ot:
        vals = [(lo - ot, True)] + vals + [(hi + ot, True)]
    return vals


def frange(a, b, st):
    out, x = [], a
    while x <= b + 1e-9:
        out.append(round(x, 4))
        x += st
    return out


def thin(lst, k, keep=()):
    """k evenly spaced items of lst; indices in `keep` always stay."""
    if len(lst) <= k:
        return lst
    keep = set(i % len(lst) for i in keep) | {0, len(lst) - 1}
    rest = [i for i in range(len(lst)) if i not in keep]
    m = max(0, k - len(keep))
    pick = set(rest[round(j * (len(rest) - 1) / (m - 1))] for j in range(m)) if m > 1 else ({rest[len(rest) // 2]} if m == 1 and rest else set())
    return [lst[i] for i in sorted(keep | pick)]


def pose_grid(drv, quick=False, cap=None):
    """Joint-angle combinations for a group of driver joints, thinned to `cap`. Thinning keeps each joint's limits and
    overtravel poses: it used to keep only the list ends, which are the overtravel poses, so in a two-joint group the
    in-range limits (tilt -3 and 46 in v2 A1) were never visited and a collision there showed only as an overtravel
    warn (FINDINGS V2A1-V2)."""
    drv = sorted(drv)
    if not drv:
        return [({}, False)]
    per = [samples(j, quick) for j in drv]
    keeps = [(0, 1, -2, -1) if len(p) > 3 and p[0][1] else (0, -1) for p in per]
    cap = cap or CFG["max_poses_per_group"]
    while math.prod(len(p) for p in per) > cap:
        i = max(range(len(per)), key=lambda k: len(per[k]) - len(keeps[k]))
        floor = len(keeps[i]) + (0 if len(keeps[i]) == 4 else 1)
        if len(per[i]) <= floor:
            break
        per[i] = thin(per[i], max(floor, len(per[i]) - 2), keeps[i])
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


def inter_volume(a, b, _swapped=False):
    """Intersection volume (mm^3) and region bbox using a world-space copy; Manifold when both are manifold, else
    EXACT (retried in the other order when the result looks like the open operand's own volume, see below)."""
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
    # EXACT with a non-manifold cutter can return the cutter's whole volume: A1-A3's hand-made CAB_12v_ctrl tube (open
    # cap rings) gave 1331.9 mm3 "through BUY_servo_controller", its own volume (1332.0); the other order gives 38.0.
    # Only that signature (>= 98% of a non-manifold operand's own volume) triggers the swapped order, and only a smaller
    # swapped result replaces it, so a real full containment still reports its whole volume.
    if solver == 'EXACT' and not _swapped and v > 0 and any(
            v >= 0.98 * own_volume(o) for o in (a, b) if not manifold_ok(o)):
        v2, region2, _ = inter_volume(b, a, _swapped=True)
        if v2 < v:
            return v2, region2, solver
    return v, region, solver


def own_volume(o):
    bm = world_bm(o)
    v = abs(bm.calc_volume())
    bm.free()
    return v


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


def contact_faces(fit, a, b):
    """For a fits rule with contact=true and "contact_normal" ([x,y,z] or a list, home-pose world directions of the
    rule's `a` part, turning with it): a test f(world_normal) -> True when a face is one of the declared contact faces
    (within 20 deg of +-a normal). Without contact_normal, contact=true accepts contact anywhere on the pair, which also
    hides a rubbing journal on the same pair (v2 A1 review: post x journal plate and shell x turntable were thrust or
    stop faces plus a R15/R15.2 and R20/R20.3 journal, FINDINGS V2A1-V4)."""
    cn = fit.get("contact_normal") if fit else None
    if not cn:
        return None
    cn = [cn] if isinstance(cn[0], (int, float)) else cn
    ref = a if fnmatch.fnmatch(a.name, fit.get("a", "*")) else b
    hm = HOME_MW.get(ref.name, ref.matrix_world).to_3x3()
    loc = [(hm.inverted() @ Vector(c)).normalized() for c in cn]
    cur = ref.matrix_world.to_3x3()
    wn = [(cur @ v).normalized() for v in loc]
    return lambda n: any(abs(n.normalized().dot(v)) >= 0.94 for v in wn)


def min_dist_off(a, b, ta, tb, is_contact):
    """min_dist that ignores samples whose nearest face is a declared contact face."""
    best = (1e9, None)
    for src, tree in ((a, tb), (b, ta)):
        for p in sample_pts(src):
            r = tree.find_nearest(p)
            if r[0] is not None and r[3] < best[0] and not is_contact(r[1]):
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
PAST_LIMITS = []   # poses outside a joint's range (check_pose_values)
UNBOUNDED_ALLOWS = {}   # allow rules with no max_mm3 that skip a pair across a joint: "a x b" -> why (check_interference)


def present(check, label, names):
    """True when every named object exists. Otherwise one fail naming the row, and the caller skips the row: a
    half-built assembly keeps its checks.json rows (v2 A1: a distances row naming a not-yet-built part raised
    KeyError and took down the whole run, so builders skipped every distances row with --only, FINDINGS V2A1-T3)."""
    miss = sorted({n for n in names if isinstance(n, str) and n and n != "world" and n not in O})
    if miss:
        finding(check, "fail", "%s: %s not in the scene; row skipped (build the part or fix the name)" % (label, ", ".join(miss)), missing=miss)
    return not miss


def finding(check, status, msg, **data):
    rec = {"status": status, "msg": msg, **data}
    REPORT["checks"].setdefault(check, {"findings": []})["findings"].append(rec)
    (FAILS if status == "fail" else WARNS if status == "warn" else []).append("%s: %s" % (check, msg))


# ------------------------------------------------------------------ parts

def bridge_span(tris):
    """Widest inscribed circle over connected ceiling regions = the bridge length a slicer would need, and where."""
    if not tris:
        return None, None
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
        groups.setdefault(find(i), []).append(t)
    best, where = 0.0, None
    for g in groups.values():
        span, c = _inscribed_span(g)
        if span > best:
            best, where = span, Vector((c[0], c[1], sum(p.z for t in g for p in t) / (3 * len(g))))
    return round(best, 1), where


def _inscribed_span(tris):
    """Diameter of the widest circle inside one ceiling region (print frame, xy), and its centre. The span used to be
    the short side of the region's xy bounding box, which is wrong for any region that isn't an axis-aligned
    rectangle: v2 A3's crown L-slot floors are 56.5 deg arc sectors whose inscribed width is 5.1, but whose bbox
    reads 26.4, a false bridge warn that took the finish builder two probe scripts (FINDINGS V2A3-T3)."""
    import numpy as np
    key = lambda p: (round(p.x, 2), round(p.y, 2))
    cnt = {}
    for t in tris:
        for i in range(3):
            k = tuple(sorted((key(t[i]), key(t[(i + 1) % 3]))))
            cnt[k] = cnt.get(k, 0) + 1
    seg = np.array([[*a, *b] for (a, b), n in cnt.items() if n == 1 and a != b], dtype=float)
    T = np.array([[[p.x, p.y] for p in t] for t in tris], dtype=float)
    lo, hi = T.reshape(-1, 2).min(0), T.reshape(-1, 2).max(0)
    if not len(seg) or (hi - lo).min() < 1e-6:
        return 0.0, None
    h = max(0.1, float((hi - lo).max()) / 250.0)
    gx, gy = np.meshgrid(np.arange(lo[0] + h / 2, hi[0], h), np.arange(lo[1] + h / 2, hi[1], h))
    P = np.stack([gx.ravel(), gy.ravel()], 1)
    inside = np.zeros(len(P), bool)
    for a, b, c in T:
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        w1 = ((b[1] - c[1]) * (P[:, 0] - c[0]) + (c[0] - b[0]) * (P[:, 1] - c[1])) / d
        w2 = ((c[1] - a[1]) * (P[:, 0] - c[0]) + (a[0] - c[0]) * (P[:, 1] - c[1])) / d
        inside |= (w1 >= -1e-9) & (w2 >= -1e-9) & (w1 + w2 <= 1 + 1e-9)
    P = P[inside]
    if not len(P):
        return 0.0, None
    A, B = seg[:, :2], seg[:, 2:]
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    best, bi = 0.0, 0
    for s in range(0, len(P), 2000):
        Q = P[s:s + 2000, None, :]
        u = np.clip(((Q - A) * AB).sum(2) / L2, 0, 1)
        dmin = np.sqrt((((A + u[..., None] * AB) - Q) ** 2).sum(2)).min(1)
        j = int(dmin.argmax())
        if dmin[j] > best:
            best, bi = float(dmin[j]), s + j
    return 2 * best, [round(float(v), 1) for v in P[bi]]


LAYER_DONE = {}


def print_frame_tris(o):
    """The part's triangles exactly as cadlib.export writes its STL: print_rot @ world, centred in xy, bed at z = 0.
    Returns (tris (n,3,3) numpy, R, off) with stl = R @ world + off."""
    import numpy as np
    R = Matrix(o["print_rot"]) if "print_rot" in o.keys() else Matrix.Identity(3)
    me = o.data
    me.calc_loop_triangles()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    M = np.array(o.matrix_world)
    Rn = np.array(R)
    w = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    v = w @ Rn.T
    off = np.array([-(v[:, 0].min() + v[:, 0].max()) / 2, -(v[:, 1].min() + v[:, 1].max()) / 2, -v[:, 2].min()])
    idx = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", idx)
    return (v + off)[idx.reshape(-1, 3)], Rn, off


def stl_dirs():
    """Where `cad build` exported the STLs: <project>/stl next to blender/, or stl/ next to the blend (--out builds)."""
    b = bpy.data.filepath
    if not b:
        return []
    d = os.path.dirname(os.path.abspath(b))
    return [x for x in (os.path.join(d, "stl"), os.path.join(os.path.dirname(d), "stl")) if os.path.isdir(x)]


def layer_check(o, dirs):
    """printcheck.analyze on the exported STL (what gets sliced), or on the model's print triangles when there is no STL
    on disk. FINDINGS "v2 post-freeze": the face-based ceiling test passed jar_valve's cantilevered bayonet tabs and
    feeder_cover's 10.5 mm screw ear, both marked supports: no."""
    import numpy as np
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import printcheck as PC
    tris, Rn, off = print_frame_tris(o)
    src, note = "model", None
    for d in dirs:
        fp = os.path.join(d, "%s.stl" % o.get("stl"))
        if os.path.isfile(fp):
            st = PC.read_stl(fp)
            lo_m, hi_m = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
            lo_s, hi_s = st.reshape(-1, 3).min(0), st.reshape(-1, 3).max(0)
            if len(st) != len(tris) or np.abs(lo_m - lo_s).max() > 0.05 or np.abs(hi_m - hi_s).max() > 0.05:
                note = "%s differs from the model (%d vs %d triangles, bbox %s vs %s): re-export; checked the STL" % (
                    fp, len(st), len(tris), [round(float(x), 1) for x in hi_s - lo_s], [round(float(x), 1) for x in hi_m - lo_m])
            tris, src = st, os.path.relpath(fp, os.path.dirname(os.path.dirname(fp)))
            break
    pc = dict(CFG.get("printcheck") or {})
    pc.setdefault("overhang_deg", CFG["overhang_deg"])
    pc.setdefault("bridge_warn_mm", CFG.get("max_bridge_mm", 25))
    res = PC.analyze_cached(tris, pc, supports=o.get("supports"), print_to_world=(Rn.T, -Rn.T @ off))
    return res, src, note


def check_parts():
    P = CFG["printers"]
    pref = CFG["prefer_printer"]
    cos_o = math.cos(math.radians(CFG["overhang_deg"]))
    set_pose({})
    rows = []
    seen = set()
    tot_g = tot_h = 0.0
    dirs = stl_dirs()
    LAYER_DONE.clear()
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
        span, sp_at = bridge_span(ceil_tris)
        if sp_at is not None:
            sp_at = [round(v, 1) for v in R.inverted() @ sp_at]   # print frame back to world
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
               "ceiling_mm2": round(ceil, 1), "max_bridge_span_mm": span, "bridge_at": sp_at,
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
        # layer check (printcheck) on the exported STL; it replaces the ceiling-span warn, which called every flat
        # downward face a bridge without asking whether it was anchored on two sides (FINDINGS "v2 post-freeze")
        if os.environ.get("CAD_LAYER_CHECK") == "0":   # verify_all's older regressions, which count other checks' rows
            pass
        elif stl not in LAYER_DONE:
            LAYER_DONE[stl] = layer_check(o, dirs)
            lc, src, note = LAYER_DONE[stl]
            if note:
                finding("parts", "warn", "%s: %s" % (o.name, note), object=o.name)
            for f in lc["findings"]:
                finding("parts", f["status"], "%s (%s): %s%s" % (o.name, src, f["msg"], ", supports: %s" % (o.get("supports") or "unset")
                        if f["status"] == "fail" else ""), object=o.name, stl=stl, kind=f["kind"], z=f["z_mm"])
        if stl in LAYER_DONE:
            lc, src, note = LAYER_DONE[stl]
            row["layer_check"] = {"source": src, "needs_support": lc["needs_support"], "max_overhang_mm": lc["max_overhang_mm"],
                                  "max_bridge_mm": lc["max_bridge_mm"], "n_islands": lc["n_islands"], "n_cantilevers": lc["n_cantilevers"],
                                  "regions": [g for g in lc["regions"] if g["status"] != "ok"][:6], "px_mm": lc["px_mm"]}
        if "print_rot" not in o.keys():
            finding("parts", "warn", "%s has no print_rot; checked as modelled" % o.name, object=o.name)
        if o.get("bevel_clamped"):
            w_, mv_ = list(o["bevel_clamped"])
            finding("parts", "warn", "%s: cadlib.bevel's overlap clamp cut the %g edge break to about %.2f on every edge (dense facets or a sliver "
                    "next to a bevelled edge; bevel before that cut, FINDINGS V2A6-T2)" % (o.name, w_, mv_ / 1.4), object=o.name)
    REPORT["checks"].setdefault("parts", {"findings": []}).update(
        {"rows": rows, "unique_stls": len(seen), "est_total_g": round(tot_g), "est_total_h": round(tot_h, 1)})
    if os.environ.get("CAD_LAYER_CHECK") == "0":
        REPORT["not_checked"].append("parts: layer support check skipped (CAD_LAYER_CHECK=0)")
    srcs = sorted(set(v[1] for v in LAYER_DONE.values()))
    REPORT["coverage"].append("parts: %d printed objects (%d unique STLs): manifold, bed fit %s, overhang, wall probe, bed contact; "
                              "layer support check (bridge / cantilever / island) on %s" % (
                                  len(PRINTED), len(seen), list(P), "the exported STLs" if srcs and all(x != "model" for x in srcs)
                                  else "the model's print triangles (no stl/ on disk)" if srcs == ["model"] else "STLs where exported, else the model"))


# ------------------------------------------------------------------ interference + clearance over sweeps

def pair_class(a, b):
    ka, kb = KIND[a.name], KIND[b.name]
    same = body(a) == body(b)
    kinds = {ka, kb}
    if same:
        if kinds <= {"PRT", "BUY"}:
            return "solid"
        if kinds == {"FST"}:
            return None if (is_nut(a) or is_nut(b)) else "fst_fst"  # bolt through its nut: fastener check pairs them
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
    res = {"groups": [], "collisions": [], "contacts": [], "solid_overlaps": [], "cable_overlaps": [], "min_clearance": [], "allowed_max": []}
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
                isc = contact_faces(fit, a, b) if fit and fit.get("contact") else None
                if ov and isc and all(isc(a.matrix_world.to_3x3() @ a.data.polygons[i].normal) for i, _ in ov):
                    ov = None     # touching only on declared contact faces; the rest of the pair is measured below
                if ov:
                    if why and why.get("max_mm3") is None:
                        if cls == "moving":
                            UNBOUNDED_ALLOWS.setdefault("%s x %s" % key, why.get("why", ""))
                        continue
                    vol, region, solver = inter_volume(a, b)
                    if why:
                        # a bounded allow: a riding detent or a crush rib may overlap up to max_mm3, a deeper clash
                        # still fails. An unbounded allow across a joint hid any clash in every sweep (V2R5 A5-06)
                        bound = float(why["max_mm3"])
                        b_rec = worst.setdefault(("allowed_max", key), {"a": a.name, "b": b.name, "max_mm3": bound, "volume_mm3": 0.0,
                                                                        "pose": None, "why": why.get("why")})
                        if vol > b_rec["volume_mm3"]:
                            b_rec.update(volume_mm3=round(vol, 2), pose=pose_key(pose))
                        if vol <= bound:
                            continue
                    rec = {"a": a.name, "b": b.name, "pose": pose_key(pose), "overtravel": over, "tri_overlaps": len(ov),
                           "volume_mm3": round(vol, 2), "region": region, "solver": solver}
                    if cls == "moving":
                        tag = "collisions" if vol >= CFG["vol_tol"] else ("contacts" if not (fit and fit.get("contact") and not isc) else None)
                    elif cls == "cable":
                        tag = "cable_overlaps" if vol >= CFG["vol_tol"] else None
                    else:
                        tag = "solid_overlaps" if vol >= CFG["vol_tol"] else None
                    if why:   # past a bounded allow's max_mm3: a clash, whatever vol_tol says
                        tag = {"moving": "collisions", "cable": "cable_overlaps"}.get(cls, "solid_overlaps")
                        rec["allow_max_mm3"] = float(why["max_mm3"])
                    if tag:
                        prev = worst.get((tag, key))
                        if prev is None or rec["volume_mm3"] > prev["volume_mm3"] or (prev["overtravel"] and not over):
                            rec["n_poses"] = (prev or {}).get("n_poses", 0) + 1
                            rec["in_range_poses"] = (prev or {}).get("in_range_poses", 0) + (0 if over else 1)
                            worst[(tag, key)] = rec
                        else:
                            prev["n_poses"] += 1
                            prev["in_range_poses"] += 0 if over else 1
                elif cls == "moving" and not why and (isc or not (fit and fit.get("contact"))):
                    d, p = min_dist_off(a, b, ta, tb, isc) if isc else min_dist(a, b, ta, tb)
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
            finding("interference", "fail", "%s x %s collide on different bodies: %.1f mm3 at %s%s" % (r["a"], r["b"], r["volume_mm3"], r["pose"],
                    " (over the allow's max_mm3 %g)" % r["allow_max_mm3"] if "allow_max_mm3" in r else ""), **r)
        else:
            finding("interference", "warn", "%s x %s collide only %s past the joint limit (%s): no margin" % (r["a"], r["b"], OT_TEXT, r["pose"]), **r)
    for r in res["contacts"]:
        if r["in_range_poses"]:
            finding("interference", "fail", "%s x %s touch with zero clearance across a joint (rubbing) at %d poses, e.g. %s" % (r["a"], r["b"], r["in_range_poses"], r["pose"]), **r)
        else:
            finding("interference", "warn", "%s x %s touch just past the joint limit (%s)" % (r["a"], r["b"], r["pose"]), **r)
    for r in res["solid_overlaps"]:
        finding("interference", "fail", "%s x %s overlap %.1f mm3 on the same body%s" % (r["a"], r["b"], r["volume_mm3"],
                " (over the allow's max_mm3 %g)" % r["allow_max_mm3"] if "allow_max_mm3" in r else ""), **r)
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


def scene_bvh(objs, skip=(), index=None):
    """One BVH over many objects. index (a list) receives (first face index, name) per object, for owner()."""
    bm = bmesh.new()
    for o in objs:
        if o.name in skip:
            continue
        if index is not None:
            index.append((len(bm.faces), o.name))
        t = world_bm(o)
        me = bpy.data.meshes.new("_t")
        t.to_mesh(me)
        t.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    tree = BVHTree.FromBMesh(bm)
    bm.free()
    return tree


def owner(index, face):
    """Object name owning face `face` of a scene_bvh built with index=[...]."""
    name = None
    for start, n in index:
        if start > face:
            break
        name = n
    return name


def perp_basis(d):
    a = Vector((1, 0, 0)) if abs(d.x) < 0.9 else Vector((0, 1, 0))
    u = d.cross(a).normalized()
    return u, d.cross(u).normalized()


def _ring(u, v, r, n=6):
    return [(u * math.cos(k * 2 * math.pi / n) + v * math.sin(k * 2 * math.pi / n)) * r for k in range(n)]


# 26 roughly even directions for "is this point visible from outside" (exposure) tests
_SPH = [Vector((math.cos(2.39996 * i) * math.sqrt(1 - (1 - 2 * (i + 0.5) / 26) ** 2),
                math.sin(2.39996 * i) * math.sqrt(1 - (1 - 2 * (i + 0.5) / 26) ** 2),
                1 - 2 * (i + 0.5) / 26)) for i in range(26)]


def escapes(tree, p, maxd=3000.0):
    """How many of 26 directions leave the assembly without hitting a solid (0 = enclosed)."""
    return sum(1 for d in _SPH if tree.ray_cast(p, d, maxd)[0] is None)


_N_VIEW = 400
_SPH400 = [d for d in (Vector((math.cos(2.39996 * i) * math.sqrt(1 - (1 - 2 * (i + 0.5) / _N_VIEW) ** 2),
                             math.sin(2.39996 * i) * math.sqrt(1 - (1 - 2 * (i + 0.5) / _N_VIEW) ** 2),
                             1 - 2 * (i + 0.5) / _N_VIEW)) for i in range(_N_VIEW))]
_VIEW = {}


def exposed(tree, p, maxd=3000.0):
    """Visible from outside: many of 26 rays escape, or a view_frac of the directions toward a viewer above or level
    do (a notch or slot shows a cable in a narrow cone that 26 rays sample too coarsely)."""
    ex = CFG["exposure"]
    n = sum(1 for d in _SPH if tree.ray_cast(p, d, maxd)[0] is None)
    if n >= ex["min_escape"]:
        return True
    view = _VIEW.setdefault(ex["view_z"], [d for d in _SPH400 if d.z > ex["view_z"]])
    if n == 0 and all(tree.ray_cast(p, d, maxd)[0] is not None for d in view[::8]):
        return False    # enclosed: skip the dense pass
    return sum(1 for d in view if tree.ray_cast(p, d, maxd)[0] is None) >= ex["view_frac"] * len(view)


def access(head, out, tree, solids_trees, fc):
    """Drive a screw from `head` along `out`: a straight bit (ray bundle at driver radius until open space of
    hand_r is reached), else an L-key (short leg in the socket, long leg swung about the axis), FINDINGS A2-F1."""
    u, v = perp_basis(out)
    rays = [Vector((0, 0, 0))] + _ring(u, v, fc["driver_r"])
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
        return {"reach_mm": round(depth, 1), "blocked": False, "tool": "straight"}
    who = None
    if blocked_at < 1e8:
        p = start + out * blocked_at
        best = 1e9
        for n, t in solids_trees.items():
            r = t.find_nearest(p)
            if r[0] is not None and r[3] < best:
                best, who = r[3], n
    rec = {"reach_mm": None, "blocked": True, "blocked_at_mm": round(blocked_at, 1) if blocked_at < 1e8 else None, "blocked_by": who}
    rec.update(lkey(head, out, u, v, tree, fc))
    if rec["lkey_ok"]:
        rec.update(blocked=False, tool="L-key", reach_mm=round(fc["lkey_short"] - fc["lkey_insert"], 1))
    return rec


def lkey(head, out, u, v, tree, fc):
    """Hex key: the short leg runs along the screw axis to the elbow, the long leg is swung about the axis.
    Returns the largest contiguous arc (deg) over which the long leg is clear for its full length."""
    elbow_s = fc["lkey_short"] - fc["lkey_insert"]
    kr = fc["lkey_r"]
    start = head + out * 0.3
    for off in [Vector((0, 0, 0))] + _ring(u, v, kr, 4):
        h = tree.ray_cast(start + off, out, elbow_s + kr)
        if h[0] is not None:
            return {"lkey_ok": False, "lkey_arc_deg": 0, "lkey_why": "short leg blocked %.1f mm out (elbow at %.1f)" % (h[3], elbow_s)}
    elbow = start + out * elbow_s
    clear = []
    for k in range(36):
        a = math.radians(k * 10)
        w = u * math.cos(a) + v * math.sin(a)
        clear.append(all(tree.ray_cast(elbow + off, w, fc["lkey_long"])[0] is None for off in (Vector((0, 0, 0)), out * kr, -out * kr)))
    if all(clear):
        arc = 360
    else:
        best = run = 0
        for c in clear + clear:
            run = run + 1 if c else 0
            best = max(best, run)
        arc = max(0, min(best, 36) - 1) * 10
    return {"lkey_ok": arc >= fc["lkey_swing_deg"], "lkey_arc_deg": arc,
            "lkey_why": "long leg clear over %d deg (need %g)" % (arc, fc["lkey_swing_deg"])}


def assembly_present():
    """object name -> set of solids present when it is installed (None = unknown, assume all).

    assembly_order: [{"step": "...", "objects": [globs], "bench": "<group>"?, "merge": "<group>"?}, ...]
    A bench step builds a sub-assembly away from the rest; a later step with merge=<group> brings it in. A merge step
    that is itself a bench step brings the group into that bench (sub-assemblies of sub-assemblies, any depth; v2 A1's
    feeder designer restructured its steps because this was missing, FINDINGS V2A1-T2).
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

    def lands_in(g, grp, i):
        """Is a part built in group g (None = the main assembly) present in group grp at step i?"""
        seen = set()
        while g != grp:
            j = merged_at.get(g)
            if g is None or j is None or j > i or g in seen:
                return False
            seen.add(g)
            g = steps[j].get("bench")
        return True

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
            if lands_in(steps[j].get("bench"), grp, i):
                pres.add(m)
        out[n] = pres
    return out


def fastener_poses():
    """Home, each driver joint at its limits, and the fastener's own continuous joints every 60 deg
    (you can turn a wheel to bring a screw round to the access window)."""
    poses = [({}, "home")]
    for jn, s in JOINTS.items():
        if jn in COUPLE or s["axis"] is None:
            continue
        if s.get("continuous"):
            if any(jn in joint_chain(o) for o in FASTENERS):
                poses += [({jn: a}, pose_key({jn: a})) for a in (60, 120, 180, 240, 300)]
            continue
        if s["lo"] is None or s["hi"] is None:
            continue
        for a in (s["lo"], s["hi"]):
            if abs(a - (s.get("home") or 0)) > 1e-6:
                poses.append(({jn: a}, pose_key({jn: a})))
    return poses


def _verts_world(o, cap=60):
    vs = [o.matrix_world @ v.co for v in o.data.vertices]
    return vs[:: max(1, len(vs) // cap)]


def _edge_samples(o, step=2.0, cap=1500):
    """Points every `step` mm along the mesh edges: a tube along a polyline has vertices only at its corners."""
    mw = o.matrix_world
    vs = [mw @ v.co for v in o.data.vertices]
    pts = list(vs)
    for e in o.data.edges:
        a, b = vs[e.vertices[0]], vs[e.vertices[1]]
        n = int((b - a).length // step)
        pts += [a + (b - a) * (k / (n + 1)) for k in range(1, n + 1)]
    return pts[:: max(1, len(pts) // cap)]


def head_height(o, head, d, sr):
    """Bearing face offset from the head end. cadlib fasteners store the bearing face itself (0); for inferred
    fasteners the head end is the top of the head, so measure how far the wider-than-shank section runs."""
    if "fst_head" in o.keys():
        return 0.0
    hh = 0.0
    for v in o.data.vertices:
        w = o.matrix_world @ v.co - head
        t = w.dot(d)
        if (w - d * t).length > sr * 1.25 and t > hh:
            hh = t
    return hh


def pair_nuts(geo, nuts):
    """bolt name -> (nut name, t0, t1): nut extent along the bolt axis measured from the head (mm)."""
    out = {}
    for n, (head, tip, d, hr, sr) in geo.items():
        L = (tip - head).length
        best = None
        for nut in nuts:
            vs = [O[nut].matrix_world @ v.co for v in O[nut].data.vertices]
            c = sum(vs, Vector()) / len(vs)
            tc = (c - head).dot(d)
            radial = ((c - head) - d * tc).length
            if radial < sr + 1.0 and -5 < tc < L + 15 and (best is None or radial < best[0]):
                ts = [(v - head).dot(d) for v in vs]
                best = (radial, nut, min(ts), max(ts))
        if best:
            out[n] = best[1:]
    return out


def check_fasteners():
    fc = CFG["fasteners"]
    if not FASTENERS:
        REPORT["not_checked"].append("fasteners: Fasteners collection is empty; screws are not modelled")
        return
    rows = []
    screws = [o for o in FASTENERS if not is_nut(o)]
    nuts = [o.name for o in FASTENERS if is_nut(o)]
    poses = fastener_poses()
    set_pose({})
    geo = {o.name: fastener_axis(o) for o in screws}
    nut_of = pair_nuts(geo, nuts)
    full_tree = scene_bvh(SOLIDS)
    per = {o.name: {} for o in screws}
    present = assembly_present()
    for pose, pk in poses:
        set_pose(pose)
        trees = {o.name: (bvh_world(o), bbox_world(o)) for o in SOLIDS}
        tree_cache = {}
        for o in screws:
            head, tip, d, hr, sr = fastener_axis(o) if pose else geo[o.name]
            if not pose:
                per[o.name].update(survey_screw(o, head, tip, d, hr, sr, trees, nut_of.get(o.name), full_tree, fc))
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
        # captive: a head held in a pocket and never driven (the nut turns), A3 nip stud. Head seating and access
        # do not apply; engagement and nut pairing still do.
        cap = next((why for g, why in fc.get("captive", {}).items() if fnmatch.fnmatch(n, g)), None)
        if cap:
            r["captive"] = cap
            r["head_buried_in"] = []
            ok, best = {"home": {}}, ("home", {"reach_mm": 0})
        rows.append({"object": n, **r})
        if r["head_buried_in"]:
            finding("fasteners", "fail", "%s head is inside %s (reversed, or a missing counterbore)" % (n, r["head_buried_in"]), object=n)
        nut = r.get("nut")
        if nut:
            if r["nut_gap_mm"] > 0:
                finding("fasteners", "fail", "%s stops %.2f mm short of its nut %s: no thread engagement" % (n, r["nut_gap_mm"], nut["name"]), object=n)
            elif r["engagement_mm"] < nut["len_mm"] - 0.3:
                finding("fasteners", "fail" if r["engagement_mm"] < 0.5 * nut["len_mm"] else "warn",
                        "%s engages only %.1f of %s's %.1f mm (the bolt should pass through the nut)" % (
                            n, r["engagement_mm"], nut["name"], nut["len_mm"]), object=n)
        elif not r["thread_host"]:
            finding("fasteners", "warn", "%s: no material grips the thread (floating screw, or every hole is clearance)" % n, object=n)
        elif r["engagement_mm"] < r["engagement_need_mm"] - 1e-6:
            finding("fasteners", "warn", "%s: only %.1f mm of thread in %s (needs %.1f: %s)" % (
                n, r["engagement_mm"], r["thread_host"], r["engagement_need_mm"], r["engagement_rule"]), object=n)
        for b, mm in r["into_purchased"].items():
            finding("fasteners", "fail", "%s runs %.1f mm into purchased part %s, which is not what it threads into%s" % (
                n, mm, b, " (it has a nut)" if nut else ""), object=n, purchased=b)
        if r["standoff_mm"] > fc["max_standoff"] and not cap:
            finding("fasteners", "warn", "%s head stands %.1f mm off the part: exposed shank under the head" % (n, r["standoff_mm"]), object=n)
        if r["protrusion_mm"] > fc["max_protrusion"] and r["tip_exposed"]:
            finding("fasteners", "warn", "%s thread protrudes %.1f mm past the last part, visible from outside" % (n, r["protrusion_mm"]), object=n)
        if not ok:
            h = acc["home"]
            finding("fasteners", "fail", "%s cannot be driven: straight bit blocked by %s at %s mm; %s (all %d poses tried)" % (
                n, h.get("blocked_by"), h.get("blocked_at_mm"), "L-key " + h.get("lkey_why", ""), len(acc)), object=n)
        elif "home" not in ok:
            finding("fasteners", "warn", "%s reachable only at %s (blocked at home pose)" % (n, best[0]), object=n)
        elif best[1]["reach_mm"] > fc["max_reach_ext"]:
            finding("fasteners", "fail", "%s sits %.0f mm deep" % (n, best[1]["reach_mm"]), object=n)
        elif best[1]["reach_mm"] > fc["max_reach"]:
            finding("fasteners", "warn", "%s needs a %.0f mm+ bit/extension (head %.0f mm below open space)" % (n, best[1]["reach_mm"] + 10, best[1]["reach_mm"]), object=n)
    nut_rows = check_nuts(nuts, nut_of, full_tree)
    # lengths you can buy (v2 A3 specified an M3 x 9 self-tap; the reviewer docked it, V2A3-F5)
    stock = {float(k): v for k, v in fc["stock_lengths"].items()}
    odd = {}
    for o in screws:
        d, L = float(o.get("fst_d", 0) or 0), float(o.get("fst_len", 0) or 0)
        ls = next((v for k, v in stock.items() if abs(k - d) < 0.05), None)
        if ls and not any(abs(L - x) < 0.05 for x in ls) and not any(fnmatch.fnmatch(o.name, g) for g in fc["stock_ok"]):
            odd.setdefault("M%g x %g" % (d, L), []).append(o.name)
    if odd:
        finding("fasteners", "warn", "non-stock screw lengths: %s (declare custom lengths under fasteners.stock_ok)" % "; ".join(
            "%s (%s)" % (k, ", ".join(v[:3]) + (" ..." if len(v) > 3 else "")) for k, v in sorted(odd.items())), objects=odd)
    REPORT["checks"].setdefault("fasteners", {"findings": []}).update(rows=rows, nuts=nut_rows)
    REPORT["coverage"].append("fasteners: %d screws, %d nuts; head-buried, thread engagement (bolt-to-nut pairing), shanks/nuts inside purchased parts, "
                              "head stand-off, protruding thread, access (Ø%.0f bit to %.0f mm hand clearance, else a %.0f/%.0f mm L-key with a %g deg swing) at %d poses, %s" % (
        len(screws), len(nuts), 2 * fc["driver_r"], fc["hand_r"], fc["lkey_short"], fc["lkey_long"], fc["lkey_swing_deg"], len(poses),
        "parts present per assembly_order (%d steps)" % len(CFG.get("assembly_order", [])) if CFG.get("assembly_order") else "ALL parts present (no assembly_order: later parts may block falsely)"))
    if not CFG.get("assembly_order"):
        REPORT["not_checked"].append("fasteners: assembly order (declare assembly_order so access is tested against the parts present at that step)")
    if not CFG.get("service"):
        REPORT["not_checked"].append("fasteners: service access (declare service ops: assembly-order access says nothing about re-adjusting a built machine)")
    REPORT["not_checked"].append("fasteners: pilot/clearance hole diameters (use cadlib.features for those); wrench access to nuts")


def survey_screw(o, head, tip, d, hr, sr, trees, nut, full_tree, fc):
    """Home-pose facts about one screw: thread host and engagement, same-body penetrations, head seating."""
    u, v = perp_basis(d)
    L = (tip - head).length
    me = body(o)
    same = {n: tb for n, tb in trees.items() if body(O[n]) == me}
    ring = _ring(u, v, sr * 0.92)
    # every same-body solid the shank runs through (ring at 92% of the shank radius inside it)
    pen, s_ = {}, 0.25
    while s_ < L:
        c = head + d * s_
        for n, (t, bb) in same.items():
            if sum(1 for r in ring if inside(t, c + r, bb)) >= 4:
                pen[n] = pen.get(n, 0.0) + 0.5
        s_ += 0.5
    # thread host: walk back from the tip, one sample at the middle of each 0.5 mm step (the walk used to start
    # 0.5 mm in, so it read 0.5 mm short and a joint at exactly 2 d warned)
    eng, host, s_ = 0.0, None, 0.25
    while s_ < L:
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
    rec = {}
    if "min_engagement" in fc:      # project override in mm (old configs)
        rec["engagement_need_mm"], rec["engagement_rule"] = float(fc["min_engagement"]), "fasteners.min_engagement"
    else:
        dia = float(o.get("fst_d", 0) or 0) or 2 * sr
        k = "tapped_engagement_d" if host and KIND.get(host) == "BUY" else "min_engagement_d"
        rec["engagement_need_mm"], rec["engagement_rule"] = round(fc[k] * dia, 2), "%g d, fasteners.%s" % (fc[k], k)
    if nut:
        nn, t0, t1 = nut
        rec["nut"] = {"name": nn, "from_mm": round(t0, 2), "to_mm": round(t1, 2), "len_mm": round(t1 - t0, 2)}
        rec["nut_gap_mm"] = round(t0 - L, 2) if L < t0 else 0.0
        host, eng = nn, max(0.0, min(L, t1) - max(0.0, t0))
    into_buy = {n: round(mm, 1) for n, mm in pen.items() if KIND[n] == "BUY" and mm >= 1.0 and n != (None if nut else host) and not allowed(o.name, n)}
    # head seated? Points just under the bearing face at 80% of head radius should be in material (any body: a
    # clamp-screw head bears on the slot face of the part it clamps against)
    hring = _ring(u, v, hr * 0.8, 4)
    hh = head_height(o, head, d, sr)
    standoff, s_ = None, hh + 0.3
    while s_ < min(L, 40.0):
        if sum(1 for r in hring for n, (t, bb) in trees.items() if inside(t, head + d * s_ + r, bb)) >= 2:
            standoff = s_ - 0.3 - hh
            break
        s_ += 0.5
    standoff = round(standoff if standoff is not None else min(L, 40.0) - hh, 1)
    # head buried: just behind the bearing face, in a part on the same body (cross-body overlaps are interference's job)
    head_pts = [head - d * 0.25 + r for r in hring] + [head - d * 0.25]
    buried = sorted({n for n, (t, bb) in same.items() for p in head_pts if inside(t, p, bb)})
    # thread past the last material (the nut counts as material)
    if nut:
        prot = max(0.0, L - nut[2])
    else:
        prot, s_ = L, 0.0
        while s_ < L:
            c = tip - d * s_
            if any(sum(1 for r in ring if inside(t, c + r, bb)) >= 4 for t, bb in trees.values()):
                prot = s_
                break
            s_ += 0.5
    rec.update({"head": [round(c, 1) for c in head], "into": [round(c, 3) for c in d], "length_mm": round(L, 1),
                "thread_host": host, "engagement_mm": round(eng, 2), "head_buried_in": buried, "body": me,
                "passes_through": {n: round(mm, 1) for n, mm in pen.items()}, "into_purchased": into_buy,
                "standoff_mm": standoff, "protrusion_mm": round(prot, 1),
                "tip_exposed": prot > 0 and exposed(full_tree, tip + d * 0.3)})
    return rec


def check_nuts(nuts, nut_of, full_tree):
    rows = []
    paired = {v[0]: k for k, v in nut_of.items()}
    for nn in nuts:
        o = O[nn]
        vs = [O[nn].matrix_world @ v.co for v in o.data.vertices]
        c = sum(vs, Vector()) / len(vs)
        pts = [c + (p - c) * 0.85 for p in vs[:: max(1, len(vs) // 30)]] + [c]
        inside_buy = {}
        for s in SOLIDS:
            if KIND[s.name] != "BUY" or allowed(nn, s.name):
                continue
            t, bb = bvh_world(s), bbox_world(s)
            k = sum(1 for p in pts if inside(t, p, bb))
            if k >= 0.3 * len(pts):
                inside_buy[s.name] = round(k / len(pts), 2)
        # visible nut: sample the nut's outer vertices (its centre sits on the bolt, inside the solid tree's holes)
        vis = sum(1 for p in vs[:: max(1, len(vs) // 12)] if exposed(full_tree, c + (p - c) * 1.02))
        row = {"object": nn, "bolt": paired.get(nn), "inside_purchased": inside_buy, "exposed": vis >= 2}
        rows.append(row)
        if row["exposed"] and not inside_buy and not any(fnmatch.fnmatch(nn, g) for g in CFG["exposure"]["nuts_ok"]):
            finding("fasteners", "warn", "%s is visible from outside (A2 jack nuts, A3 battery-bay window): hide it or list it under "
                    "exposure.nuts_ok" % nn, object=nn)
        if not row["bolt"]:
            finding("fasteners", "warn", "%s has no bolt on its axis" % nn, object=nn)
        for b, f in inside_buy.items():
            finding("fasteners", "fail", "%s sits inside purchased part %s (%d%% of its volume samples)" % (nn, b, 100 * f), object=nn, purchased=b)
    return rows


def check_service():
    """Tool access for service operations on the built machine (A2-F6: the right clamp screw could be fitted on the
    bench but not re-adjusted at tilt 0). op = {"op", "fasteners": [globs], "remove": [globs], "pose": {...}}."""
    ops = CFG.get("service") or []
    if not ops:
        return
    fc = CFG["fasteners"]
    rows = []
    for op in ops:
        removed = {o.name for o in ALL if any(fnmatch.fnmatch(o.name, g) for g in op.get("remove", []))}
        # removal is assumed, not tested: say so unless a slide_out row moves those parts at the op's pose (v2 A1: the
        # nip cover came off only at tilt 45, blocked by the groove cap at tilt 0, and the op had no pose, FINDINGS V2A1-F2)
        parts_off = sorted(n for n in removed if KIND.get(n) in ("PRT", "BUY"))
        if parts_off:
            # an op with no pose is proved by a slide_out row at home. It used to compare None with the row's pose key,
            # so nothing could ever prove it, and the v2 A3 designer added `"pose": {}` to the op by hand (V2A3-T4)
            pk = pose_key(op.get("pose") or {})
            proved = [S for S in CFG["slide_out"] if any(fnmatch.fnmatch(n, g) for n in parts_off for g in (S.get("objects") or [S.get("object", "")]))
                      and pose_key(S.get("pose", {})) == pk]
            if not proved:
                finding("service", "warn", "'%s' removes %s; no slide_out row moves them at %s, so removal is assumed" % (
                    op["op"], parts_off[:4], pk), op=op["op"])
        fsts = [o for o in FASTENERS if not is_nut(o) and o.name not in removed and any(fnmatch.fnmatch(o.name, g) for g in op["fasteners"])]
        poses = [(op["pose"], pose_key(op["pose"]))] if "pose" in op else [p for p in fastener_poses() if not any(JOINTS[j].get("continuous") for j in p[0])]
        res = {o.name: {} for o in fsts}
        for pose, pk in poses:
            set_pose(pose)
            solids = [o for o in SOLIDS if o.name not in removed]
            tree = scene_bvh(solids)
            trees = {o.name: bvh_world(o) for o in solids}
            for o in fsts:
                head, tip, d, hr, sr = fastener_axis(o)
                res[o.name][pk] = access(head, -d, tree, trees, fc)
        set_pose({})
        for n, acc in res.items():
            ok = [pk for pk, a in acc.items() if not a["blocked"]]
            first = poses[0][1]
            rows.append({"op": op["op"], "object": n, "access": acc})
            if not ok:
                a = acc[first]
                finding("service", "fail", "'%s': %s cannot be reached (straight bit blocked by %s at %s mm; L-key %s) at %s" % (
                    op["op"], n, a.get("blocked_by"), a.get("blocked_at_mm"), a.get("lkey_why"), ", ".join(acc)), object=n, op=op["op"])
            elif first not in ok:
                a = acc[first]
                finding("service", "warn", "'%s': %s reachable only at %s (at %s blocked by %s %s mm out)" % (
                    op["op"], n, ", ".join(ok), first, a.get("blocked_by"), a.get("blocked_at_mm")), object=n, op=op["op"])
    REPORT["checks"].setdefault("service", {"findings": []})["rows"] = rows
    REPORT["coverage"].append("service: %d ops, %d screw accesses with the built assembly present" % (len(ops), len(rows)))


# ------------------------------------------------------------------ drop tests

def frame_point(frame, p_home, home_mats):
    if not frame or frame == "world":
        return Vector(p_home)
    return O[frame].matrix_world @ home_mats[frame].inverted() @ Vector(p_home)


def _axis(spec):
    sg = -1.0 if spec.startswith("-") else 1.0
    return "XYZ".index(spec[-1]), sg


def landing_angle(ang, point):
    """Angle of `point` about ang.center in ang.frame coordinates, from the `zero` axis toward `positive`
    (either may carry a sign, e.g. zero "-Z" = bottom dead centre)."""
    c = O[ang["center"]].matrix_world.translation
    F = O[ang.get("frame", ang["center"])].matrix_world.to_3x3()
    loc = F.inverted() @ (point - c)
    zk, zs = _axis(ang.get("zero", "Z"))
    pk, ps = _axis(ang.get("positive", "-Y"))
    return math.degrees(math.atan2(ps * loc[pk], zs * loc[zk]))


def slide_trace(p, g, walls, targets, T, touched=None):
    """Fall along g; on a wall, slide down its slope; stall below stall_deg. Ported from the attempt-2 designer's
    tracer (HW/blender/checks.py:395 trace_drops), generalised to any target objects.
    Returns (outcome, point, target, flattest slide in deg or None): outcome is "hit", "stall", "lost" or "max_steps".
    The flattest slide is the stall margin: A3 fed 29/29 at tilt 45 over a 21 deg last slide, 1 deg above the stall
    limit, and R3 rated it a major (FINDINGS A3-F1)."""
    cap, pay = T.get("capture_mm", 0.5), T.get("payload_mm", 7.0)
    stall = T.get("stall_deg", 20.0)

    def near_target(q, within):
        best = None
        for n, t in targets.items():
            r = t.find_nearest(q, within)
            if r[0] is not None and (best is None or r[3] < best[0]):
                best = (r[3], n, r[0])
        return best

    def visible(q, tp):
        w = tp - q
        L = w.length
        return L < 0.2 or walls.ray_cast(q + w.normalized() * 0.1, w.normalized(), L - 0.2)[0] is None

    P, mode, n, flat = p.copy(), "fall", None, None
    for _ in range(900):
        if mode == "fall":
            h = walls.ray_cast(P, g, T.get("max_mm", 400))
            hit_d = h[3] if h[0] is not None else T.get("max_mm", 400)
            if touched is not None and h[0] is not None:
                touched[1].add(h[2])
            th = None
            for nm, t in targets.items():
                r = t.ray_cast(P, g, hit_d)
                if r[0] is not None and (th is None or r[3] < th[0]):
                    th = (r[3], nm, r[0])
            s = 0.0
            while th is None and s < hit_d:     # near miss: passes within capture of the target surface
                q = near_target(P + g * s, cap)
                if q:
                    th = (s, q[1], q[2])
                s += 0.4
            if th:
                return "hit", th[2], th[1], flat
            if h[0] is None:
                return "lost", P + g * hit_d, None, flat
            n = h[1].normalized()
            if n.dot(g) > 0:
                n = -n
            P = h[0] + n * 0.05
            mode = "slide"
            continue
        d = g - g.dot(n) * n
        if d.length < 1e-6:
            return "stall", P, None, 0.0
        d.normalize()
        q = near_target(P, pay)
        if q and visible(P, q[2]):
            return "hit", q[2], q[1], flat
        slope = math.degrees(math.asin(max(-1.0, min(1.0, d.dot(g)))))
        flat = slope if flat is None else min(flat, slope)
        if slope < stall:
            return "stall", P, None, flat
        hw = walls.ray_cast(P, d, 1.0)
        if touched is not None and hw[0] is not None:
            touched[1].add(hw[2])
        if hw[0] is not None:
            n2 = hw[1].normalized()
            if n2.dot(d) > 0:
                n2 = -n2
            P, n = hw[0] + n2 * 0.05, n2
            continue
        Pn = P + d * 1.0
        ha = walls.ray_cast(Pn + n * 0.8, -n, 2.5)
        if touched is not None and ha[0] is not None:
            touched[1].add(ha[2])
        if ha[0] is not None:
            n2 = ha[1].normalized()
            if n2.dot(n) < 0:
                n2 = -n2
            P, n = ha[0] + n2 * 0.05, n2
        else:
            P, mode = Pn, "fall"
    return "max_steps", P, None, flat


def check_drop():
    tests = CFG["drop_tests"]
    if not tests:
        REPORT["not_checked"].append("drop: no drop_tests configured (feed paths unsimulated)")
        return
    set_pose({})
    home_mats = {n: O[n].matrix_world.copy() for n in JOINTS}
    out = []
    modes = set()
    for T in tests:
        mode = T.get("mode", "ray")
        modes.add(mode)
        em = T["emit"]
        if not present("drop", T["name"], [em.get("frame"), (T.get("expect", {}).get("angle") or {}).get("center")]):
            continue
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
        want_hit = exp.get("hit")
        ang = exp.get("angle")
        rows = []
        on_path = set()      # objects the payload touched or first hit, at any pose
        for pose in poses:
            set_pose(pose)
            objs = [o for o in SOLIDS + FASTENERS if o.name not in T.get("ignore", [])]
            if mode == "slide":
                tnames = [o.name for o in objs if want_hit and any(fnmatch.fnmatch(o.name, w) for w in want_hit if w)]
                widx = []
                walls = scene_bvh([o for o in objs if o.name not in tnames], index=widx)
                touched = (widx, set())
                targets = {n: bvh_world(O[n]) for n in tnames}
            else:
                trees = {o.name: (bvh_world(o), o) for o in objs}
            hits, angles, outcomes, stalls, flats = {}, [], {}, [], []
            for (i, j) in offs:
                p_home = Vector(em["center"]) + u * i + v * j
                p = frame_point(em.get("frame"), p_home, home_mats)
                if mode == "slide":
                    oc, pt, name, flat = slide_trace(p, g, walls, targets, T, touched)
                    outcomes[oc] = outcomes.get(oc, 0) + 1
                    if oc == "hit" and flat is not None:
                        flats.append((flat, [round(c, 1) for c in p]))
                    if oc == "stall":
                        stalls.append([round(c, 1) for c in pt])
                    best = (0, name, pt) if oc == "hit" else None
                    if oc != "hit":
                        name = oc
                else:
                    best = None
                    for n, (t, o) in trees.items():
                        h = t.ray_cast(p, g, T.get("max_mm", 400))
                        if h[0] is not None and (best is None or h[3] < best[0]):
                            best = (h[3], n, h[0])
                    name = best[1] if best else None
                hits[name] = hits.get(name, 0) + 1
                if best and ang and name in (want_hit or [name]):
                    angles.append(landing_angle(ang, best[2]))
            on_path |= {n for n in hits if isinstance(n, str) and n in O}
            if mode == "slide":
                on_path |= {owner(widx, f) for f in touched[1]}
            row = {"pose": pose_key(pose), "rays": len(offs), "first_hit": hits}
            if mode == "slide":
                row.update(outcomes=outcomes, stall_points=stalls[:5])
                if flats:
                    fmin = min(flats)
                    row["flattest_slide_deg"] = round(fmin[0], 1)
                    margin = T.get("stall_margin_deg", 5.0)
                    stall = T.get("stall_deg", 20.0)
                    n_low = sum(1 for f, _ in flats if f < stall + margin)
                    if n_low:
                        finding("drop", "warn", "%s at %s: %d/%d rays reach the target over a slide of only %.1f deg (stall %g, "
                                "margin %g): friction varies, so these can stall" % (T["name"], row["pose"], n_low, len(offs), fmin[0],
                                                                                   stall, margin), test=T["name"], pose=row["pose"])
            if angles:
                row["angle_deg"] = [round(min(angles), 1), round(max(angles), 1)]
            rows.append(row)
            bad = sum(c for n, c in hits.items() if want_hit and n not in want_hit)
            if bad:
                finding("drop", "fail", "%s at %s: %d/%d rays %s %s, not %s" % (
                    T["name"], row["pose"], bad, len(offs), "end at" if mode == "slide" else "first hit",
                    sorted(str(n) for n in hits if n not in want_hit), want_hit), test=T["name"], pose=row["pose"])
            if angles and ang and ang.get("range"):
                lo, hi = ang["range"]
                if min(angles) < lo or max(angles) > hi:
                    finding("drop", "fail", "%s at %s: lands %.0f..%.0f deg, window %g..%g" % (
                        T["name"], row["pose"], min(angles), max(angles), lo, hi), test=T["name"], pose=row["pose"])
        # A ranged joint that moves a wall the payload touches, held at home for the whole test: the v2 A1 nip drop ran at
        # the home hood setting only, and R1 found stalls from a 7.4 mm gap at the open end (FINDINGS V2A1-F1)
        swept = set(T.get("poses", {})) | set(T.get("sweep", [])) | set(T.get("home_only_ok", []))
        movers = {}
        fr = em.get("frame")
        fchain = set(joint_chain(O[fr])) if fr and fr != "world" else set()
        for n in sorted(on_path - {None}):
            for j in drivers(set(joint_chain(O[n])) ^ fchain):     # joints that move it relative to the emitter
                sj = JOINTS.get(j, {})
                if j not in swept and not sj.get("continuous") and sj.get("lo") is not None and sj.get("hi") is not None and sj["hi"] > sj["lo"]:
                    movers.setdefault(j, []).append(n)
        for j, names in movers.items():
            finding("drop", "warn", "%s: the payload path touches %s, which moves on %s (%g..%g), but the test holds %s at home; add both "
                    "ends to poses (or list it under home_only_ok)" % (T["name"], names[:4], j, JOINTS[j]["lo"], JOINTS[j]["hi"], j), test=T["name"], joint=j)
        out.append({"name": T["name"], "mode": mode, "rows": rows, "on_path": sorted(on_path - {None})})
    set_pose({})
    REPORT["checks"].setdefault("drop", {"findings": []})["tests"] = out
    REPORT["coverage"].append("drop: %d tests (%s)" % (len(tests), ", ".join(
        {"ray": "first-contact straight rays", "slide": "fall + slide on walls, no bounce or rolling"}.get(m, m) for m in sorted(modes))))


def check_index():
    """Indexer timing (A2-F2: the documented 0 -> 60 -> 0 feeder stroke had a pocket over the outlet at both ends,
    so every fire command dropped two candies). A probe bundle is cast through the moving disc at the outlet while the
    joint runs the motion `sequence`; each maximal run of "open" poses is one window (one release)."""
    tests = CFG.get("index_tests") or []
    if not tests:
        return
    set_pose({})
    home_mats = {n: O[n].matrix_world.copy() for n in JOINTS}
    rows = []
    for T in tests:
        pr = T["probe"]
        if not present("index", T["name"], list(T["blockers"]) + [T["joint"], pr.get("frame")]):
            continue
        g = Vector(pr.get("dir", [0, 0, -1])).normalized()
        u, v = perp_basis(g)
        offs = [Vector((0, 0, 0))] + _ring(u, v, pr.get("radius", 3.0))
        seq = T["sequence"]
        angs = []
        for a, b in zip(seq, seq[1:]):
            n = max(1, int(math.ceil(abs(b - a) / T.get("step", 2.0))))
            angs += [a + (b - a) * k / n for k in range(n)]
        angs.append(seq[-1])
        state = []
        for a in angs:
            pose = dict(T.get("pose", {}), **{T["joint"]: a})
            set_pose(pose)
            trees = [bvh_world(O[n]) for n in T["blockers"]]
            c = frame_point(pr.get("frame"), Vector(pr["center"]), home_mats)
            state.append(all(all(t.ray_cast(c + o, g, pr.get("depth", 30))[0] is None for t in trees) for o in offs))
        set_pose({})
        cyc = seq[0] == seq[-1]
        runs, prev = [], False   # each run = the joint angles visited while open
        for a, s in zip(angs, state):
            if s and not prev:
                runs.append([])
            if s:
                runs[-1].append(a)
            prev = s
        if cyc and len(runs) > 1 and state[0] and state[-1]:
            runs[0] += runs.pop()   # a window spanning the cycle start is one window
        runs = [(min(r), max(r)) for r in runs]
        row = {"name": T["name"], "joint": T["joint"], "sequence": seq, "windows": len(runs),
               "open_ranges_deg": [[round(x, 1), round(y, 1)] for x, y in runs], "open_at_start": state[0], "why": T.get("why")}
        rows.append(row)
        want = T.get("expect_windows", 1)
        if len(runs) != want:
            finding("index", "fail", "%s: %d open windows over %s on %s (want %d), open at %s deg%s" % (
                T["name"], len(runs), seq, T["joint"], want, row["open_ranges_deg"], "; open at the park position" if state[0] else ""), **row)
        elif state[0]:
            finding("index", "warn", "%s: the park position %g deg is already open over the outlet" % (T["name"], seq[0]), **row)
    REPORT["checks"].setdefault("index", {"findings": []})["rows"] = rows
    REPORT["coverage"].append("index: %d indexer timing tests (probe through the moving parts over the motion sequence)" % len(tests))


# ------------------------------------------------------------------ slide-out, distances

def check_slide():
    """Slide-out sweeps. {"object": name} or {"objects": [globs]} moves as one group (the attempt-2 designer's
    service sweeps: flywheel plus its bolts, cover, encoder cap), with "ignore" for parts already removed."""
    for S in CFG["slide_out"]:
        set_pose(S.get("pose", {}))
        globs = S.get("objects") or [S["object"]]
        grp = [o for o in ALL if KIND[o.name] != "CAB" and any(fnmatch.fnmatch(o.name, g) for g in globs)]
        gnames = {o.name for o in grp}
        ign = {o.name for o in ALL if any(fnmatch.fnmatch(o.name, g) for g in S.get("ignore", []))}
        label = S.get("name") or (grp[0].name if len(grp) == 1 else "+".join(globs))
        d = Vector(S["dir"]).normalized()
        # fasteners too: A3's battery slid through two adapter nuts that a solids-only sweep never saw (FINDINGS A3-F3)
        # a `flex` part stays in the sweep even when an allow rule covers the pair, so its riding overlap is measured
        fx = lambda n: any(fnmatch.fnmatch(n, g) for g in (S.get("flex") or {}))
        others = {o.name: bvh_world(o) for o in SOLIDS + FASTENERS if o.name not in gnames | ign and (fx(o.name) or not any(allowed(o.name, g) for g in gnames))}
        bm0 = bmesh.new()
        for o in grp:
            t = world_bm(o)
            me = bpy.data.meshes.new("_s")
            t.to_mesh(me)
            t.free()
            bm0.from_mesh(me)
            bpy.data.meshes.remove(me)
        free_until, blocker = None, None
        # already overlapping in place (BVH overlap misses a nut wholly inside the part, A2): interference and
        # fasteners report those; the slide reports what the motion adds
        at_rest = [n for n in others if any(bb_gap(bbox_world(o), bbox_world(O[n])) == 0 for o in grp)
                   and sum(inter_volume(o, O[n])[0] for o in grp) >= CFG["vol_tol"]]
        minclr = (1e9, None)
        flex, flexed = S.get("flex") or {}, {}
        M0 = {o.name: o.matrix_world.copy() for o in grp}
        for s in frange(0, S["dist"], S.get("step", 5)):
            bm = bm0.copy()
            bmesh.ops.translate(bm, verts=bm.verts, vec=d * s)
            t = BVHTree.FromBMesh(bm)
            pts = [v.co.copy() for v in bm.verts][:: max(1, len(bm.verts) // 1500)]
            bm.free()
            hit = []
            for n, ot in others.items():
                if n in at_rest:
                    continue
                if t.overlap(ot):
                    for o in grp:
                        o.matrix_world = Matrix.Translation(d * s) @ M0[o.name]
                    bpy.context.view_layer.update()
                    vol = sum(inter_volume(o, O[n])[0] for o in grp)
                    for o in grp:
                        o.matrix_world = M0[o.name]
                    bpy.context.view_layer.update()
                    lim = next((v for g, v in flex.items() if fnmatch.fnmatch(n, g)), None)
                    if lim is not None and 0 < vol <= lim:
                        # a declared spring riding the moving part (a detent bump over its track), not a stop
                        # (v2 A3: the gate detent overlaps the blade 0.43 mm3 mid-travel, V2A3-T5). Recorded below
                        # vol_tol too: A5's 0.43 mm3 ride left `flexed` empty, so the row proved nothing (V2A5-T3)
                        if vol > flexed.get(n, (0, 0))[0]:
                            flexed[n] = (round(vol, 2), s)
                    elif vol >= CFG["vol_tol"]:
                        hit.append(n)
            if hit:
                free_until, blocker = s, hit
                break
            for n, ot in others.items():
                if n in at_rest:
                    continue
                for p in pts:
                    r = ot.find_nearest(p, 3.0)
                    if r[0] is not None and r[3] < minclr[0]:
                        minclr = (r[3], n)
        bm0.free()
        rec = {"object": label, "members": sorted(gnames), "dir": list(d), "dist": S["dist"], "blocked_at_mm": free_until, "blocked_by": blocker,
               "min_clearance_mm": round(minclr[0], 2) if minclr[1] else None, "closest": minclr[1], "pose": pose_key(S.get("pose", {})),
               "overlapping_at_rest": at_rest}
        if flex:
            rec["flexed"] = {n: {"max_mm3": v, "at_mm": a} for n, (v, a) in flexed.items()}
        REPORT["checks"].setdefault("slide", {"findings": []}).setdefault("rows", []).append(rec)
        if S.get("expect") == "blocked":
            # an end stop: the motion must be stopped, by the named part, within at_mm (v2 A2 gate open stop, V2A2-T4)
            rng = S.get("at_mm")
            by_ok = not S.get("blocked_by") or any(fnmatch.fnmatch(b, g) for b in (blocker or []) for g in S["blocked_by"])
            if not blocker:
                finding("slide", "fail", "%s: expected a stop, but it slides the full %g mm" % (label, S["dist"]), **rec)
            elif not by_ok or (rng and not rng[0] - 1e-6 <= free_until <= rng[1] + 1e-6):
                finding("slide", "fail", "%s: stopped by %s at %g mm, wanted %s at %s mm" % (label, blocker, free_until, S.get("blocked_by", "any part"), rng or "any"), **rec)
        elif blocker:
            finding("slide", "fail", "%s slide-out blocked by %s at %g mm" % (label, blocker, free_until), **rec)
        elif minclr[1] and minclr[0] < S.get("min_clearance", 1.5):
            finding("slide", "warn", "%s slides out but with only %.2f mm to %s" % (label, minclr[0], minclr[1]), **rec)
    set_pose({})
    if CFG["slide_out"]:
        REPORT["coverage"].append("slide: %d slide-out sweeps" % len(CFG["slide_out"]))


def ray_stations(R):
    """[(deg or None, ray)]: the ray itself, or one ray per station of its `sweep`, turned about sweep.axis through
    sweep.center (both in the ray's frame coordinates). v2 A4's four full-lift nip rays sat at BDC and passed at 8.28;
    the candy enters on an arc where the hood, hinged far up the arc, opens less: 7.50 at psi 80 (FINDINGS V2A4-F1)."""
    sw = R.get("sweep")
    if not sw:
        return [(None, R)]
    c, ax = Vector(sw["center"]), Vector(sw["axis"]).normalized()
    out = []
    for a in frange(float(sw["from"]), float(sw["to"]), float(sw.get("step", 5.0))) + [float(sw["to"])]:
        if out and abs(out[-1][0] - a) < 1e-6:
            continue
        M = Matrix.Rotation(math.radians(a), 3, ax)
        out.append((a, dict(R, origin=list(c + M @ (Vector(R["origin"]) - c)), dir=list(M @ Vector(R["dir"])))))
    return out


def ray_gap(D, home_mats, R=None):
    """Gap along a line: from `origin` (frame coords) cast +dir to the first face of b and -dir to the first face of a."""
    R = R or D["ray"]
    o = frame_point(R.get("frame"), Vector(R["origin"]), home_mats)
    F = O[R["frame"]].matrix_world.to_3x3() @ home_mats[R["frame"]].to_3x3().inverted() if R.get("frame") else Matrix.Identity(3)
    w = (F @ Vector(R["dir"])).normalized()
    hb = bvh_world(O[D["b"]]).ray_cast(o, w, 500)
    ha = bvh_world(O[D["a"]]).ray_cast(o, -w, 500)
    if hb[0] is None or ha[0] is None:
        return None, o, None
    return ha[3] + hb[3], o, {D["a"]: (ha[0], ha[1]), D["b"]: (hb[0], hb[1])}


def _local_hits(hits):
    """World ray hits -> each part's own frame (point, normal), to compare one pose with home."""
    out = {}
    for n, (p, nv) in (hits or {}).items():
        M = O[n].matrix_world
        out[n] = (M.inverted() @ p, (M.to_3x3().inverted() @ nv).normalized())   # rigid links: no shear
    return out


def ray_slip(home, now):
    """Parts whose ray hit at this pose is on another face than at home: the point moved off the home face's plane
    by more than 0.5 mm, or the face normal turned more than 25 deg. Sliding along the same face is not a slip."""
    out = []
    for n, (p0, n0) in (home or {}).items():
        if n not in (now or {}):
            continue
        p1, n1 = now[n]
        off = abs((p1 - p0).dot(n0))
        if off > 0.5 or n0.angle(n1, 0.0) > math.radians(25):
            out.append({"part": n, "off_plane_mm": round(off, 2), "normal_turn_deg": round(math.degrees(n0.angle(n1, 0.0)), 1)})
    return out


def check_distances():
    set_pose({})
    home_mats = {n: O[n].matrix_world.copy() for n in JOINTS}
    for D in CFG["distances"]:
        poses = D.get("poses", [D.get("pose", {})])
        if not present("distances", "%s to %s" % (D["a"], D["b"]), [D["a"], D["b"], (D.get("ray") or {}).get("frame")]):
            continue
        stations = ray_stations(D["ray"]) if D.get("ray") else []
        home_hits = {}
        if D.get("ray") and any(poses):
            set_pose({})
            home_hits = {k: _local_hits(ray_gap(D, home_mats, R)[2]) for k, (_, R) in enumerate(stations)}
        for pose in poses:
            set_pose(pose)
            a, b = O[D["a"]], O[D["b"]]
            near, slip, sweep = None, [], None
            if D.get("ray"):
                prof = [(deg, R) + ray_gap(D, home_mats, R) for deg, R in stations]   # (deg, R, d, origin, hits)
                hit = [(k, x) for k, x in enumerate(prof) if x[2] is not None]
                lo, hi = D.get("min"), D.get("max")
                bad = lambda x: max(([lo - x] if lo is not None else []) + ([x - hi] if hi is not None else []) or [-x])
                k, (deg, R, d, p, hits) = max(hit, key=lambda kx: bad(kx[1][2])) if hit else (0, prof[0])   # the worst station
                how = "along ray"
                if deg is not None:
                    w = D["ray"]["sweep"]
                    sweep = {"sweep_deg": deg, "missed_deg": [x[0] for x in prof if x[2] is None],
                             "profile": [[x[0], round(x[2], 3) if x[2] is not None else None] for x in prof]}
                    how = "along ray swept %g..%g deg, worst at %g" % (float(w["from"]), float(w["to"]), deg)
                    if D.get("max") is not None and sweep["missed_deg"]:
                        d = None   # an open station has no upper bound
                if pose and home_hits.get(k):
                    slip = ray_slip(home_hits[k], _local_hits(hits))
                if slip:
                    near = min_dist(a, b, bvh_world(a), bvh_world(b))[0]
            else:
                d, p = min_dist(a, b, bvh_world(a), bvh_world(b))
                how = "nearest"
            rec = {"a": a.name, "b": b.name, "pose": pose_key(pose), "mm": round(d, 3) if d is not None else None, "how": how,
                   "min": D.get("min"), "max": D.get("max"), "why": D.get("why")}
            if sweep:
                rec.update(sweep)
            REPORT["checks"].setdefault("distances", {"findings": []}).setdefault("rows", []).append(rec)
            if d is None:
                finding("distances", "fail", "%s to %s: the ray missed one of them at %s%s" % (
                    a.name, b.name, rec["pose"], " (swept stations %s)" % sweep["missed_deg"] if sweep else ""), **rec)
                continue
            if (D.get("min") is not None and d < D["min"]) or (D.get("max") is not None and d > D["max"]):
                finding("distances", "fail", "%s to %s = %.2f mm (%s) at %s, wanted %s..%s (%s)" % (a.name, b.name, d, how, rec["pose"], D.get("min"), D.get("max"), D.get("why", "")), **rec)
            if sweep and sweep["missed_deg"]:
                # a min-only row passes a station whose ray hits nothing: v2 A6's full-lift rows at home and the max stop
                # silently dropped psi 0 (V2R6 A6-03, FINDINGS V2A6-F3)
                finding("distances", "warn", "%s to %s: the swept ray missed a part at %d of %d stations (%s deg) at %s, so they measured nothing; "
                        "start the sweep where both faces are, or move the origin onto the passage" % (
                            a.name, b.name, len(sweep["missed_deg"]), len(sweep["profile"]), ", ".join("%g" % x for x in sweep["missed_deg"][:8]), rec["pose"]), **rec)
            if slip:
                rec["nearest_mm"], rec["ray_slip"] = round(near, 3), slip
                if d > near + max(1.0, 0.3 * near):
                    # v2 A2: a nip ray fixed in PIV_tilt slipped past the hood lip at full lift and read 14.18 against a
                    # 7.06 nearest gap (FINDINGS V2A2-F6); frame the ray in the moving part's joint. The first version
                    # compared every ray with the nearest gap and gave 9 false warns on v2 A3 (diameters, approach
                    # lines, a stud-axis gap), so it now needs the hit to have left its home face too (V2A3-T2)
                    finding("distances", "warn", "%s to %s: at %s the ray hits %s on another face than at home, and its gap %.2f mm is much wider than "
                            "the nearest gap %.2f; the ray may miss the working face (frame it in the joint that moves %s)" % (
                                a.name, b.name, rec["pose"], ", ".join(x["part"] for x in slip), d, near, slip[0]["part"]), **rec)
            if D.get("payload_mm"):
                # A2-F4: a rigid 1 mm squeeze on a hard candy; thickness varies +-0.5 mm, so something must yield
                sq = D["payload_mm"] - (d - D.get("tape_mm", 0.0))
                rec["squeeze_mm"] = round(sq, 2)
                if sq <= 0:
                    finding("distances", "fail", "%s to %s: payload %.1f mm is not gripped (gap %.2f after %.1f mm liner)" % (
                        a.name, b.name, D["payload_mm"], d - D.get("tape_mm", 0.0), D.get("tape_mm", 0.0)), **rec)
                elif not D.get("compliant"):
                    finding("distances", "warn", "%s to %s: %.2f mm rigid squeeze on a %.1f mm payload; name the part that yields (spring, flexure) under 'compliant' or the nip slips or crushes as the payload varies" % (
                        a.name, b.name, sq, D["payload_mm"]), **rec)
    set_pose({})



# ------------------------------------------------------------------ payload fit and sightlines

def _payload_mesh(name, shape, D, T, c, ax):
    """A candy-like probe centred at c with its thickness along ax. "lens" = two spherical caps (sharp rim; the v2
    reviewers' probe), "ellipsoid" = oblate spheroid (round rim), "sphere" = D only, "cylinder" = a D x T puck."""
    r, h = D / 2.0, T / 2.0
    bm = bmesh.new()
    if shape == "cylinder":
        bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=r, radius2=r, depth=T)
    else:
        bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=1.0)
        R = (r * r + h * h) / (2 * h) if shape == "lens" else None
        for v in bm.verts:
            x, y, z = v.co
            if shape == "lens":
                rho = min(1.0, math.hypot(x, y)) * r
                zc = math.sqrt(max(R * R - rho * rho, 0.0)) - (R - h)
                k = rho / max(math.hypot(x, y), 1e-9)
                v.co = Vector((x * k, y * k, zc if z >= 0 else -zc))
            elif shape == "sphere":
                v.co = Vector((x * r, y * r, z * r))
            else:
                v.co = Vector((x * r, y * r, z * h))
    z = Vector((0, 0, 1))
    rot = z.rotation_difference(ax.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation(c) @ rot, verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    tmpcoll().objects.link(ob)
    return ob


def _payload_place(P, D, T, F, home_mats):
    """[(centre, thickness axis)] in world for a payload row at size D x T. The candies rest on the floor point."""
    c0 = frame_point(P.get("frame"), Vector(P["center"]), home_mats)
    up = (F @ Vector(P.get("up", [0, 0, 1]))).normalized()
    gap = 0.02 + P.get("gap", 0.0)
    place = P.get("place", "flat")
    if place == "flat":
        return [(c0 + up * (T / 2 + gap), up)]
    ac = (F @ Vector(P.get("across", [1, 0, 0]))).normalized()
    if place == "edge_on":
        return [(c0 + up * (D / 2 + gap), ac)]
    if place == "pair_edge_on":
        n = int(P.get("count", 2))
        return [(c0 + up * (D / 2 + gap) + ac * (T * (k - (n - 1) / 2.0)), ac) for k in range(n)]
    if place == "stack_flat":
        n = int(P.get("count", 2))
        return [(c0 + up * (T / 2 + gap + T * k), up) for k in range(n)]
    sys.exit("cadcheck: payload_fit place %r (flat | edge_on | pair_edge_on | stack_flat)" % place)


def check_payload():
    """Does a pocket, slot or chute admit the payload the way it should? (v2 A1 and A2: the feeder pocket admitted an
    edge-on pair; both reviewers and one designer wrote their own lentil probe, FINDINGS V2A1-F3 / V2A2-F2.)
    Row: {"name", "against": [globs], "center": floor point, "frame", "pose", "up", "across", "place",
          "size": [D, T], "shape": "lens", "expect": "blocked" | "fits", "margin": 0.2}
    The probe size is moved until the answer flips: `margin_mm` is how far it can shrink (blocked) or grow (fits)
    before the expectation stops holding. Fail when it does not hold at `size`, warn when the margin is under `margin`."""
    rows = []
    for P in CFG.get("payload_fit") or []:
        if not present("payload", P["name"], [P.get("frame")]):
            continue
        set_pose({})
        home_mats = {n: O[n].matrix_world.copy() for n in JOINTS}
        set_pose(P.get("pose", {}))
        F = (O[P["frame"]].matrix_world.to_3x3() @ home_mats[P["frame"]].to_3x3().inverted()) if P.get("frame") else Matrix.Identity(3)
        against = [o for o in SOLIDS if any(fnmatch.fnmatch(o.name, g) for g in P["against"])]
        if not against:
            finding("payload", "fail", "%s: no solid matches %s; row skipped" % (P["name"], P["against"]))
            continue
        PD, PT = (list(P["size"]) + [P["size"][0]])[:2] if isinstance(P["size"], list) else (P["size"], P["size"])
        shape = P.get("shape", "lens")
        want_block = P.get("expect", "blocked") == "blocked"

        def overlap(delta):
            """Overlap volume (mm3) with the probe grown by delta mm on every side (negative = shrunk)."""
            D, T = PD + 2 * delta, max(0.2, PT + 2 * delta)
            probes = [_payload_mesh("_PAYLOAD_%d" % k, shape, D, T, c, ax) for k, (c, ax) in enumerate(_payload_place(P, D, T, F, home_mats))]
            bpy.context.view_layer.update()
            tot, hit = 0.0, set()
            for pr in probes:
                MANIFOLD_OK.pop(pr.name, None)
                tp = bvh_world(pr)
                for o in against:
                    if bb_gap(bbox_world(pr), bbox_world(o)) > 0 or not tp.overlap(bvh_world(o)):
                        continue
                    v = inter_volume(pr, o)[0]
                    if v > 1e-3:
                        tot += v
                        hit.add(o.name)
            for pr in probes:
                me = pr.data
                bpy.data.objects.remove(pr)
                bpy.data.meshes.remove(me)
            return tot, sorted(hit)

        v0, hit0 = overlap(0.0)
        ok = (v0 > 0.01) if want_block else (v0 <= 0.01)
        # bisect the flip point: shrink until a blocked probe seats, grow until a fitting one touches (2 mm max)
        lo, hi = 0.0, 2.0
        sgn = -1.0 if want_block else 1.0
        if ok:
            if ((overlap(sgn * hi)[0] > 0.01) == want_block):
                lo = hi
            else:
                for _ in range(7):
                    mid = (lo + hi) / 2
                    if (overlap(sgn * mid)[0] > 0.01) == want_block:
                        lo = mid
                    else:
                        hi = mid
            margin = lo
        else:
            # how far off: grow a seating probe until it is blocked, shrink a jamming one until it fits
            margin, lo, hi = 0.0, 0.0, 2.0
            for _ in range(7):
                mid = (lo + hi) / 2
                if (overlap(-sgn * mid)[0] > 0.01) == want_block:
                    hi = mid
                else:
                    lo = mid
            short = hi
        rec = {"name": P["name"], "place": P.get("place", "flat"), "shape": shape, "size": [PD, PT], "pose": pose_key(P.get("pose", {})),
               "expect": "blocked" if want_block else "fits", "overlap_mm3": round(v0, 3), "overlaps": hit0,
               "margin_mm": round(margin, 2) if ok else None, "short_by_mm": None if ok else round(short, 2), "why": P.get("why")}
        rows.append(rec)
        what = "%s %s %gx%g" % (rec["place"].replace("_", " "), shape, PD, PT)
        if not ok:
            if want_block:
                finding("payload", "fail", "%s: a %s seats without touching %s (should be blocked; it blocks only from %.2f mm larger)" % (
                    P["name"], what, [o.name for o in against], short), **rec)
            else:
                finding("payload", "fail", "%s: a %s overlaps %s by %.2f mm3 (should fit; it fits only from %.2f mm smaller)" % (
                    P["name"], what, hit0, v0, short), **rec)
        elif margin < P.get("margin", 0.2) - 1e-6:
            finding("payload", "warn", "%s: %s holds with only %.2f mm to spare: a %s %.2f mm %s would %s" % (
                P["name"], rec["expect"], margin, shape, margin, "smaller" if want_block else "larger", "seat" if want_block else "jam"), **rec)
    set_pose({})
    if rows:
        REPORT["checks"].setdefault("payload", {"findings": []})["rows"] = rows
        REPORT["coverage"].append("payload: %d payload-fit probes (rigid probe, no settling)" % len(rows))
    elif not CFG.get("payload_fit"):
        REPORT["not_checked"].append("payload: no payload_fit rows (pocket or slot admits two payloads, or jams one)")


def check_sightlines():
    """First-hit rays: a finger or tool line, a window, a line of sight (v2 A2: the planner proved 'the thumbwheel is
    reachable through the nip-cover slot' with hand `cad q ray` lines because no row could say it).
    Row: {"name", "origin": [x,y,z] or "origins": [...], "dir", "frame", "pose" or "poses", "first_hit": glob or null,
          "max_mm", "through": [globs ignored, e.g. a cover you remove]}"""
    rows = []
    for S in CFG.get("sightlines") or []:
        if not present("sightlines", S["name"], [S.get("frame")]):
            continue
        set_pose({})
        home_mats = {n: O[n].matrix_world.copy() for n in JOINTS}
        origins = S.get("origins") or [S["origin"]]
        want_hit = S.get("first_hit")
        for pose in S.get("poses", [S.get("pose", {})]):
            set_pose(pose)
            F = (O[S["frame"]].matrix_world.to_3x3() @ home_mats[S["frame"]].to_3x3().inverted()) if S.get("frame") else Matrix.Identity(3)
            skip = {o.name for o in SOLIDS + FASTENERS if any(fnmatch.fnmatch(o.name, g) for g in S.get("through", []))}
            idx = []
            tree = scene_bvh(SOLIDS + FASTENERS, skip=skip, index=idx)
            w = (F @ Vector(S["dir"])).normalized()
            bad = []
            hits = []
            for p0 in origins:
                p = frame_point(S.get("frame"), Vector(p0), home_mats)
                h = tree.ray_cast(p, w, S.get("max_mm", 1e4))
                name = owner(idx, h[2]) if h[0] is not None else None
                hits.append({"origin": [round(c, 2) for c in p], "hit": name, "mm": round(h[3], 2) if h[0] is not None else None})
                good = (name is None) if want_hit is None else (name is not None and fnmatch.fnmatch(name, want_hit))
                if not good:
                    bad.append(hits[-1])
            rec = {"name": S["name"], "pose": pose_key(pose), "first_hit_wanted": want_hit, "rays": len(origins), "ok": len(origins) - len(bad),
                   "hits": hits, "why": S.get("why")}
            rows.append(rec)
            if bad:
                finding("sightlines", "fail", "%s at %s: %d of %d rays hit %s first, wanted %s (e.g. %s at %s mm)" % (
                    S["name"], rec["pose"], len(bad), len(origins), sorted({b["hit"] for b in bad}, key=str), want_hit, bad[0]["hit"], bad[0]["mm"]), **rec)
    set_pose({})
    if rows:
        REPORT["checks"].setdefault("sightlines", {"findings": []})["rows"] = rows
        REPORT["coverage"].append("sightlines: %d first-hit ray rows" % len(rows))

def check_assembly():
    """Config audit of assembly_order (v2 A2: the reviewer could not tell which step held the stop sleeve and the
    valve screws, and a step label said M2 x 4 over M2 x 8 screws, FINDINGS V2A2-F5). Reports `step_of` for every
    object; warns on objects in no step (assumed present from the start, so access tests are optimistic for them)
    and on a step label whose "M<d> x <L>" matches none of that step's screws."""
    steps = CFG.get("assembly_order") or []
    if not steps:
        REPORT["not_checked"].append("assembly: no assembly_order (fastener access tested with everything present)")
        return
    step_of = {}
    for i, st in enumerate(steps):
        for o in ALL:
            if o.name not in step_of and any(fnmatch.fnmatch(o.name, g) for g in st["objects"]):
                step_of[o.name] = i
    REPORT.setdefault("assembly", {})["step_of"] = {n: steps[i]["step"] for n, i in sorted(step_of.items())}
    loose = sorted(o.name for o in SOLIDS + FASTENERS if o.name not in step_of)
    REPORT["assembly"]["in_no_step"] = loose
    if loose:
        finding("assembly", "warn", "%d objects are in no assembly_order step, so access tests assume they are there from the start: %s" % (
            len(loose), ", ".join(loose[:12]) + (" ..." if len(loose) > 12 else "")), objects=loose)
    for i, st in enumerate(steps):
        screws = [o for o in FASTENERS if step_of.get(o.name) == i and "fst_d" in o.keys() and not is_nut(o)]
        for m in re.finditer(r"\bM(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)", st["step"]):
            d, L = float(m.group(1)), float(m.group(2))
            same_d = [o for o in screws if abs(o["fst_d"] - d) < 0.3]
            if same_d and not any(abs(o["fst_len"] - L) < 0.6 for o in same_d):
                finding("assembly", "warn", "step '%s' says %s, but its M%g screws are %s long" % (
                    st["step"][:60], m.group(0), d, sorted({round(o["fst_len"], 1) for o in same_d})), step=st["step"],
                    screws=[o.name for o in same_d])
    REPORT["coverage"].append("assembly: %d steps, %d objects placed, %d in no step" % (len(steps), len(step_of), len(loose)))
    check_held_poses(steps)


def joint_drives():
    """joint -> the purchased part that holds it (a servo or gearmotor), from "joint_drives" ({"PIV_x": "BUY_..." or
    null for a joint that is free by hand}) or by name: a BUY_ part named servo/motor/stepper/actuator ending in the
    joint's name (PIV_tilt -> BUY_servo_tilt). Continuous and coupled joints are left out."""
    buy = [o.name for o in PURCHASED]
    out = {}
    for jn, s in JOINTS.items():
        if jn in COUPLE or s.get("continuous") or s["axis"] is None:
            continue
        if jn in CFG["joint_drives"]:
            if CFG["joint_drives"][jn]:
                out[jn] = (CFG["joint_drives"][jn], "joint_drives")
            continue
        sfx = jn[4:].lower()
        hit = [n for n in buy if re.search(r"servo|motor|stepper|actuator", n.lower()) and n.lower().endswith("_" + sfx)]
        if len(hit) == 1:
            out[jn] = (hit[0], "by name")
    return out


def check_held_poses(steps):
    """A step that needs a joint away from home after the joint's drive is in. v2 A7 moved the groove cap to step 11a,
    where one of its screws is reachable only at tilt 45, but the tilt servo went in at step 8 and nothing is powered
    until the battery (step 14): "tilt the pod to 45" meant back-driving an unpowered servo through its gears and
    holding it there (V2R7 A7-01, major; FINDINGS V2A7-F1). Needs come from a step's "pose" and from screws that the
    fastener check reaches only away from home. Mark the step that brings power with "powered": true; a step that says
    how the joint gets there (drive taken out, horn off, a prop) gets "pose_how": "<how>"."""
    drives = joint_drives()
    REPORT["assembly"]["joint_drives"] = {j: {"by": d, "from": how} for j, (d, how) in sorted(drives.items())}
    if not drives:
        return
    step_of = {}
    for i, st in enumerate(steps):
        for o in ALL:
            if o.name not in step_of and any(fnmatch.fnmatch(o.name, g) for g in st["objects"]):
                step_of[o.name] = i
    merged_at = {st["merge"]: i for i, st in enumerate(steps) if st.get("merge")}

    def arrives(n, grp):
        """First step at which n is in group grp (None = main), or None."""
        if n not in step_of:
            return None
        i, g, seen = step_of[n], steps[step_of[n]].get("bench"), set()
        while g != grp:
            j = merged_at.get(g)
            if g is None or j is None or g in seen:
                return None
            seen.add(g)
            i, g = max(i, j), steps[j].get("bench")
        return i

    powered = next((i for i, st in enumerate(steps) if st.get("powered")), None)
    needs = []
    for i, st in enumerate(steps):
        for jn, v in (st.get("pose") or {}).items():
            needs.append((i, jn, v, "the step's pose"))
    pk_pose = {pk: p for p, pk in fastener_poses()}
    for r in REPORT["checks"].get("fasteners", {}).get("rows", []):
        acc = r.get("access") or {}
        best = r.get("access_best")
        if r.get("captive") or not best or "home" not in acc or not acc["home"].get("blocked") or r["object"] not in step_of:
            continue
        for jn, v in pk_pose.get(best["pose"], {}).items():
            needs.append((step_of[r["object"]], jn, v, "%s is reachable only at %s" % (r["object"], best["pose"])))
    rows, merged = [], {}
    for i, jn, v, why in needs:
        merged.setdefault((i, jn, v), []).append(why)
    for (i, jn, v), whys in sorted(merged.items()):
        why = "; ".join(whys)
        if jn not in drives or abs(v - (JOINTS[jn].get("home") or 0.0)) < 1e-6:
            continue
        drv, how = drives[jn]
        a = arrives(drv, steps[i].get("bench"))
        if a is None or a > i:
            continue
        rec = {"step": steps[i]["step"], "joint": jn, "value": v, "why": why, "drive": drv, "drive_step": steps[a]["step"],
               "powered": powered is not None and powered <= i, "pose_how": steps[i].get("pose_how")}
        rows.append(rec)
        if not rec["powered"] and not rec["pose_how"]:
            finding("assembly", "warn", "step '%s' needs %s at %g (%s), but %s (%s) holds that joint from step '%s' and no step up to "
                    "here is \"powered\": an unpowered %s has to be back-driven through its gears and held there by hand. Do this "
                    "before the drive goes in, take the drive out first, or say how in the step's \"pose_how\"" % (
                        steps[i]["step"][:50], jn, v, why, drv, how, steps[a]["step"][:40], "servo" if "servo" in drv.lower() else "drive"), **rec)
    REPORT["assembly"]["held_poses"] = rows
    REPORT["coverage"].append("assembly: %d step poses and pose-only screws checked against %d joint drives (%s)" % (
        len(needs), len(drives), ", ".join("%s<-%s" % (j, d) for j, (d, _h) in sorted(drives.items()))))


_AXES6 = [("+Z", (0, 0, 1)), ("-Z", (0, 0, -1)), ("+X", (1, 0, 0)), ("-X", (-1, 0, 0)), ("+Y", (0, 1, 0)), ("-Y", (0, -1, 0))]


def _entry_hit(tree, p, d, maxd=3000.0):
    """Distance along d to the first face the ray enters and goes on into solid material, or None. A hit counts when
    the point 0.3 mm past it is inside the part and more than 0.05 mm from its surface. That passes faces the ray
    leaves through (it starts on or inside a part it touches), grazes, or clips at zero clearance: on the A6 model a
    flush cover's edge break, a coplanar seat and faceted bores at zero clearance each read "blocked" at 0.05-0.6 mm
    on parts that lift straight out. A part pressed against a wall is still blocked: its samples behind the contact
    face run into the wall."""
    q, went = p, 0.0
    for _ in range(12):
        loc, nrm, _i, dist = tree.ray_cast(q, d, maxd - went)
        if loc is None:
            return None
        if nrm.dot(d) < -0.02:
            r = loc + d * 0.3
            near = tree.find_nearest(r)
            if near[0] is not None and near[3] > 0.05 and inside(tree, r):
                return went + dist
        went += dist + 1e-3
        q = loc + d * 1e-3
    return None


def _lane(boxes, d):
    """The lane a group of boxes sweeps along d: (u, v, d basis, (lo, hi) per basis axis) from the box corners."""
    u, v = perp_basis(d)
    B = (u, v, d)
    cs = [Vector((x, y, z)) for lo, hi in boxes for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    return B, [(min(c.dot(e) for c in cs), max(c.dot(e) for c in cs)) for e in B]


def _ahead(B, ext, pts, tol=0.05):
    """Do any of pts lie in the lane, ahead of its back end?"""
    return any(all(ext[k][0] - tol <= p.dot(B[k]) <= ext[k][1] + tol for k in (0, 1)) and p.dot(B[2]) > ext[2][0] - tol for p in pts)


def _box_ahead(box, B, ext):
    """Conservative: the box's projection overlaps the lane's cross-section and reaches past its back end."""
    e2 = [(min(c.dot(e) for c in _corners(box)), max(c.dot(e) for c in _corners(box))) for e in B]
    return all(e2[k][1] >= ext[k][0] - 0.05 and e2[k][0] <= ext[k][1] + 0.05 for k in (0, 1)) and e2[2][1] > ext[2][0]


def _corners(box):
    lo, hi = box
    return [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]


def _blocked(movers, obst, d, cache, first_only):
    """Straight-line insertion test along -d (removal along d, to infinity): rays from the moving parts' samples
    along d into the obstacles, and rays from the obstacles' samples in a moving part's lane back into it.
    -> [(obstacle, mover, mm)] sorted by distance; only the first found when first_only. Otherwise the nearest hit
    per obstacle, from the reverse rays only where the forward rays found none (6 s -> 2 s on A6's feeder group)."""
    quick = first_only
    d = Vector(d).normalized()
    B, ext = _lane([bbox_world(o) for o in movers], d)
    ahead = [n for n in obst if _box_ahead(bbox_world(O[n]), B, ext)]
    out = []
    for n in ahead:
        tn = cache["bvh"].setdefault(n, bvh_world(O[n]))
        nb = bbox_world(O[n])
        for m in movers:
            Bm, em = _lane([bbox_world(m)], d)
            if not _box_ahead(nb, Bm, em):
                continue
            best = None
            for p in cache["pts"].setdefault(m.name, _edge_samples(m, 2.0, 600)):
                h = _entry_hit(tn, p, d)
                if h is not None and (best is None or h < best):
                    best = h
                    if quick:
                        break
            if best is None:
                tm = cache["bvh"].setdefault(m.name, bvh_world(m))
                for p in cache["pts"].setdefault(n, _edge_samples(O[n], 2.0, 3000)):
                    if _ahead(Bm, em, (p,)):
                        h = _entry_hit(tm, p, -d)
                        if h is not None and (best is None or h < best):
                            best = h
                            if quick:
                                break
            if best is not None:
                out.append((n, m.name, round(best, 2)))
                if first_only:
                    return out
    return sorted(out, key=lambda x: x[2])


def check_insertion():
    """Can each part, and each bench group at its merge, go in along a straight line with the parts of the earlier
    steps in place? v2 A6 put a bus splice in a hub bore at step 10d: the groove cap (2c) closes the bore above and the
    base floor (3) below, and nothing in the config said so; V2R6 found it with a hand slide row (FINDINGS V2A6-F1).

    Tested: each PRT/BUY object against the solids and fasteners of earlier steps that are in its assembly (bench or
    main), and each merge step's group against the assembly it joins, along +-X, +-Y, +-Z and the step's
    "insert_dirs" ([[x, y, z], ...]: the direction the part moves to come out), at the step's "pose" (default home).
    A step with "insert_ok": "<reason>" is listed, not tested (bayonets, snap arms, parts tilted in). Cables bend, and
    parts of the same step are placed in any order, so neither is an obstacle. Also warns on a bench part with no part
    of its group within 2 mm (by bounding box): it is not in that sub-assembly (the A6 splice sat in bench 'feeder')."""
    steps = CFG.get("assembly_order") or []
    if not steps:
        return
    step_of = {}
    for i, st in enumerate(steps):
        for o in SOLIDS + FASTENERS:
            if o.name not in step_of and any(fnmatch.fnmatch(o.name, g) for g in st["objects"]):
                step_of[o.name] = i
    merged_at = {st["merge"]: i for i, st in enumerate(steps) if st.get("merge")}

    def lands_in(g, grp, i):
        seen = set()
        while g != grp:
            j = merged_at.get(g)
            if g is None or j is None or j > i or g in seen:
                return False
            seen.add(g)
            g = steps[j].get("bench")
        return True

    unordered = [o.name for o in SOLIDS if o.name not in step_of]

    def placed(grp, i):
        """Solids and fasteners in group grp (None = main) before step i. A group merged at step i itself is left out:
        parts of one step go in in any order (A6 step 2d: the thrust ring goes on the hub before the turntable)."""
        return [n for n, j in step_of.items() if j < i and lands_in(steps[j].get("bench"), grp, i - 1)]

    fst_axes = []
    for f in FASTENERS:
        if not is_nut(f):
            try:
                fst_axes.append((f.name, bbox_world(f), fastener_axis(f)[2]))
            except Exception:
                pass

    def axes_for(mv):
        """+-X/Y/Z, then +-the axis of each screw that touches the moving parts: a part goes on along its screw
        or stud (A6's nip stop and sleeve sit on 3 and 19 deg screw axes, and read blocked along every world axis)."""
        out = list(_AXES6)
        for fn, fb, ax in fst_axes:
            if any(bb_gap(fb, bbox_world(o)) < 0.5 for o in mv) and all(abs(ax.dot(Vector(v))) < 0.9995 for _, v in out):
                out += [("along %s" % fn, tuple(ax)), ("against %s" % fn, tuple(-ax))]
            if len(out) >= 14:
                break
        return out

    rows, skipped, loose = [], [], []
    set_pose({})
    cache = {"bvh": {}, "pts": {}, "pose": pose_key({})}
    for i, st in enumerate(steps):
        tests = []
        grp = st.get("bench")
        for n, j in step_of.items():
            if j == i and KIND[n] in ("PRT", "BUY"):
                tests.append(([O[n]], n))
        if st.get("merge"):
            g = st["merge"]
            mem = [n for n, j in step_of.items() if j < i and lands_in(steps[j].get("bench"), g, i)]
            if mem:
                tests.append(([O[n] for n in mem], "group '%s' (%d objects)" % (g, len(mem))))
        if not tests:
            continue
        if st.get("insert_ok"):
            skipped.append({"step": st["step"], "why": st["insert_ok"], "objects": [t[1] for t in tests]})
            continue
        if grp:
            # a bench part far from the rest of its sub-assembly is in the wrong group (A6: the splice in 'feeder')
            mates = [n for n, j in step_of.items() if KIND[n] in ("PRT", "BUY") and lands_in(steps[j].get("bench"), grp, merged_at.get(grp, len(steps)))]
            for mv, label in tests:
                if len(mv) == 1 and len(mates) > 1:
                    gap = min(bb_gap(bbox_world(mv[0]), bbox_world(O[m])) for m in mates if m != label)
                    if gap > 2.0:
                        loose.append(label)
                        finding("insertion", "warn", "%s is in bench step '%s' (group '%s') but %.1f mm from every other part of that group: "
                                "it is not in that sub-assembly; place it in the step where it goes in" % (label, st["step"][:50], grp, gap),
                                object=label, step=st["step"], gap_mm=round(gap, 1))
        if pose_key(st.get("pose", {})) != cache.get("pose"):
            set_pose(st.get("pose", {}))
            cache = {"bvh": {}, "pts": {}, "pose": pose_key(st.get("pose", {}))}
        for mv, label in tests:
            dirs = axes_for(mv) + [("dir %s" % list(v), tuple(Vector(v).normalized())) for v in st.get("insert_dirs", [])]
            names = {o.name for o in mv}
            obst = [n for n in placed(grp, i) + unordered if n not in names and KIND[n] != "CAB"
                    and not any(allowed(n, m) for m in names)]
            free = None
            for dn, d in dirs:
                if not _blocked(mv, obst, d, cache, True):
                    free = dn
                    break
            rec = {"object": label, "step": st["step"], "free_dir": free, "obstacles": len(obst)}
            if free is None:
                rec["blocked"] = {dn: [{"by": b, "mover": m, "at_mm": a} for b, m, a in _blocked(mv, obst, d, cache, False)[:3]] for dn, d in dirs}
                why = "; ".join("%s %s" % (dn, ", ".join("%s%s at %g" % (x["by"], "" if len(mv) == 1 else " (%s)" % x["mover"], x["at_mm"]) for x in bl[:2]))
                                for dn, bl in rec["blocked"].items())
                finding("insertion", "warn", "%s (step '%s') has no straight way in with the earlier steps' parts in place: %s. Reorder the "
                        "steps, remove the blocker first (a service row), or give the step its \"insert_dirs\" / \"pose\" (\"insert_ok\" with a "
                        "reason for a twist or snap)" % (label, st["step"][:50], why), **rec)
            rows.append(rec)
    set_pose({})
    REPORT["checks"].setdefault("insertion", {"findings": []}).update(rows=rows, not_tested=skipped, loose_bench_parts=loose)
    REPORT["coverage"].append("insertion: %d parts and merged groups, straight along +-X/Y/Z (and insert_dirs) against earlier steps; %d steps insert_ok" % (
        len(rows), len(skipped)))
    REPORT["not_checked"].append("insertion: paths that are not one straight line, parts of the same step against each other, cables")


def check_stacks():
    """Tolerance stacks (A2-F7: the magnet jig referenced the nacelle bore, 0.55-0.75 mm worst case vs 0.3 allowed).
    {"name", "limit": mm, "terms": [{"what", "tol": +-mm}]}: worst case = sum, RSS = root of the sum of squares.
    "between": [A, B] measures the limit instead: the nearest gap from A to B (a name, a glob or a list; "*" = every
    solid and fastener not touching A), over "poses" (default home). A typed limit is a design intent that the geometry
    can leave behind: v2 A5's band stack said "designed radial clearance 3.0" while a new detent tab sat 0.32 from the
    band, under the stack's RSS 1.26 (V2R5 A5-01, FINDINGS V2A5-F1). With both, the smaller limit counts."""
    rows = []
    for S in CFG.get("stacks") or []:
        tols = [abs(float(t["tol"])) for t in S["terms"]]
        wc, rss = sum(tols), math.sqrt(sum(t * t for t in tols))
        limit = S.get("limit")
        row = {"name": S["name"], "limit": limit, "worst_case": round(wc, 3), "rss": round(rss, 3), "terms": S["terms"], "why": S.get("why")}
        if S.get("between"):
            a_n, bg = S["between"][0], S["between"][1]
            bg = [bg] if isinstance(bg, str) else list(bg)
            if not present("stacks", S["name"], [a_n]):
                continue
            best, touching = None, set()
            for pose in S.get("poses") or [{}]:
                set_pose(pose)
                a = O[a_n]
                ta, ba = bvh_world(a), bbox_world(a)
                for o in SOLIDS + FASTENERS:
                    if o.name == a_n or not any(fnmatch.fnmatch(o.name, g) for g in bg):
                        continue
                    if bb_gap(ba, bbox_world(o)) > max(wc, limit or 0) + 1.0:   # farther than the stack can reach
                        continue
                    d, p = min_dist(a, o, ta, bvh_world(o))
                    if d < 0.05 and bg == ["*"]:
                        touching.add(o.name)   # in contact with A: part of its datum chain, not a clearance
                        continue
                    if best is None or d < best[0]:
                        best = (d, o.name, pose_key(pose), [round(c, 1) for c in p] if p else None)
            set_pose({})
            if best:
                row.update(measured_mm=round(best[0], 3), nearest=best[1], pose=best[2], at=best[3])
                limit = best[0] if limit is None else min(limit, best[0])
            else:
                row["measured_mm"] = None   # nothing within reach of the stack: it passes on any limit
            if touching:
                row["touching"] = sorted(touching)
            row["limit"] = round(limit, 3) if limit is not None else None
        rows.append(row)
        if limit is None:
            continue
        near = " (measured: %s at %.3f%s)" % (row["nearest"], row["measured_mm"], ", " + row["pose"] if row.get("pose") else "") if row.get("nearest") else ""
        if rss > limit + 1e-9:
            finding("stacks", "fail", "%s: RSS %.2f mm > %.2f%s (worst case %.2f); shorten the datum chain or open the gap" % (S["name"], rss, limit, near, wc), **row)
        elif wc > limit + 1e-9:
            finding("stacks", "warn", "%s: worst case %.2f mm > %.2f%s (RSS %.2f)" % (S["name"], wc, limit, near, rss), **row)
    if rows:
        REPORT["checks"].setdefault("stacks", {"findings": []})["rows"] = rows
        REPORT["coverage"].append("stacks: %d tolerance stacks (declared terms only), %d with a measured limit" % (
            len(rows), sum(1 for r in rows if "measured_mm" in r)))


# ------------------------------------------------------------------ stability

def check_flexures():
    """Printed springs, flexures and snap arms against the layer direction (A3-F2: the nip leaf spring printed
    standing up, so its 21-44 MPa bending stress ran across layer bonds). Each entry: {"part", "dir": [x,y,z] or
    "from"/"to" points (world, home pose) along the beam's length, optional "stress_mpa", "why"}. The beam should
    lie in the layer plane: its angle to the bed is from the part's print_rot, the same matrix the STL export uses."""
    fl = CFG["flexures"]
    # a distances row that names a yielding part claims a spring; that spring needs a flexures row (v2 A2: the nip
    # leaf carried every squeeze claim and had none, FINDINGS V2A2-F5)
    declared = {F["part"] for F in fl}
    for D in CFG["distances"]:
        m = re.match(r"\s*((?:PRT|BUY)_[A-Za-z0-9_]+)", str(D.get("compliant") or ""))
        if m and m.group(1) in O and m.group(1) not in declared:
            declared.add(m.group(1))
            finding("flexures", "warn", "%s is named compliant in distances (%s to %s) but has no flexures row: its print orientation is unchecked" % (
                m.group(1), D["a"], D["b"]), part=m.group(1))
    for S in CFG["slide_out"]:
        # a slide that lets a part flex over it (a detent) claims a spring too
        for g in (S.get("flex") or {}):
            for n in [o.name for o in SOLIDS if fnmatch.fnmatch(o.name, g) and o.name not in declared]:
                declared.add(n)
                finding("flexures", "warn", "%s flexes in slide_out '%s' but has no flexures row: its print orientation is unchecked" % (
                    n, S.get("name") or S.get("object") or S.get("objects")), part=n)
    if not fl:
        REPORT["not_checked"].append("flexures: no springs or snap arms declared (print orientation vs bending stress)")
        return
    set_pose({})
    lim = CFG.get("interlayer_mpa", 15.0)
    rows = []
    for F in fl:
        o = O.get(F["part"])
        if o is None or "print_rot" not in o.keys():
            finding("flexures", "warn", "%s: not found or has no print_rot" % F["part"], part=F["part"])
            continue
        d = Vector(F["dir"]) if "dir" in F else Vector(F["to"]) - Vector(F["from"])
        pd = (Matrix(o["print_rot"]) @ d.normalized()).normalized()
        ang = math.degrees(math.asin(min(1.0, abs(pd.z))))
        st = F.get("stress_mpa")
        rec = {"part": F["part"], "beam_print_dir": [round(c, 3) for c in pd], "angle_to_bed_deg": round(ang, 1), "stress_mpa": st,
               "interlayer_mpa": lim, "why": F.get("why")}
        rows.append(rec)
        tag = "%s%s" % (F["part"], " (%s)" % F["name"] if F.get("name") else "")
        if ang > 45 and (st is None or st > lim):
            finding("flexures", "fail", "%s: the beam stands %.0f deg off the bed, so bending stress%s crosses layer bonds (limit %g MPa): "
                    "print it with the beam in the layer plane" % (tag, ang, " of %g MPa" % st if st else "", lim), **rec)
        elif ang > 20:
            finding("flexures", "warn", "%s: beam %.0f deg off the bed; part of the bending stress crosses layers" % (tag, ang), **rec)
    REPORT["checks"].setdefault("flexures", {"findings": []})["rows"] = rows
    REPORT["coverage"].append("flexures: %d declared springs or snap arms against print orientation" % len(rows))


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


def stability_poses():
    """Every driver joint at lo, home and hi; continuous joints every 45 deg. The old pose_grid(cap=27) call thinned
    5 joints to 3 samples each, 2 of them overtravel, so 1 pose survived, and continuous pan was left out
    (v2 A1: the finisher wrote its own 64-pose CG grid, FINDINGS V2A1-V3)."""
    per = []
    for n in sorted(JOINTS):
        s = JOINTS[n]
        if n in COUPLE or s["axis"] is None:
            continue
        if s.get("continuous"):
            per.append([(n, a) for a in frange(0, 359.9, 45.0)])
        elif s["lo"] is not None and s["hi"] is not None:
            per.append([(n, a) for a in sorted({float(s["lo"]), float(s.get("home") or 0.0), float(s["hi"])})])
    while per and math.prod(len(p) for p in per) > 4000:
        i = max(range(len(per)), key=lambda k: len(per[k]))
        per[i] = thin(per[i], len(per[i]) - 1)
    return [dict(c) for c in itertools.product(*per)] if per else [{}]


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
    # mass and local centroid once per part; each pose only moves the centroids
    parts = []
    for o in SOLIDS:
        c, vol = centroid_vol(o)
        if KIND[o.name] == "PRT":
            inf = float(o.get("infill", 20)) / 100
            m = vol * CFG["pla_density"] * (0.45 + 0.55 * inf)
        else:
            m = float(o.get("mass_g", next((v for k, v in masses.items() if fnmatch.fnmatch(o.name, k)), 0.0)))
        if m > 0:
            parts.append((o, o.matrix_world.inverted() @ c, m))
    for pose in stability_poses():
        set_pose(pose)
        M, S = 0.0, Vector()
        for o, cl, m in parts:
            M += m
            S += (o.matrix_world @ cl) * m
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
    REPORT["checks"].setdefault("stability", {"findings": []}).update({"poses": len(rows), "rows": sorted(rows, key=lambda r: r["tip_angle_deg"])[:10], "worst": worst, "footprint_pts": len(hull), "purchased_without_mass": missing})
    if worst["tip_angle_deg"] < 10:
        finding("stability", "fail", "static tip angle only %.1f deg at %s" % (worst["tip_angle_deg"], worst["pose"]), **worst)
    elif worst["tip_angle_deg"] < 20:
        finding("stability", "warn", "static tip angle %.1f deg at %s" % (worst["tip_angle_deg"], worst["pose"]), **worst)
    if missing:
        finding("stability", "warn", "no mass for %d purchased parts (counted as 0 g): %s" % (len(missing), missing[:6]))
    REPORT["coverage"].append("stability: CG and tip angle over %d poses, footprint from static parts' lowest faces" % len(rows))
    REPORT["not_checked"].append("stability: dynamic loads (recoil, pan acceleration), friction/sliding")


def cable_path(o):
    """(world points at the current pose, tube radius) of a cable route, or (None, r). cadlib stores the polyline as
    cab_path / cab_r; older blends get it back from the tube mesh, which is one ring of vertices per polyline point
    (ring 0 repeats the last point). A reconstruction whose length is off path_len is dropped."""
    M = o.matrix_world @ HOME_MW.get(o.name, o.matrix_world).inverted()
    if o.get("cab_path") is not None:
        f = list(o["cab_path"])
        return [M @ Vector(f[i:i + 3]) for i in range(0, len(f), 3)], float(o.get("cab_r", 0.0))
    vs = [o.matrix_world @ v.co for v in o.data.vertices]
    for N in (10, 8, 12, 14, 16, 6, 4):
        if len(vs) % N or len(vs) < 3 * N:
            continue
        rings = [vs[i:i + N] for i in range(0, len(vs), N)]
        cs = [sum(rg, Vector()) / N for rg in rings]
        if any(abs((p - c).length - (rings[1][0] - cs[1]).length) > 0.02 for rg, c in zip(rings, cs) for p in rg):
            continue
        pts = []
        for c in cs[1:]:
            if not pts or (c - pts[-1]).length > 1e-3:
                pts.append(c)
        L = sum((pts[i + 1] - pts[i]).length for i in range(len(pts) - 1))
        if o.get("path_len") and abs(L - o["path_len"]) > 0.005 * o["path_len"] + 0.05:
            continue
        return pts, (rings[1][0] - cs[1]).length
    return None, 0.0


def _bends(pts, od, free_ends=(True, True)):
    """Corners of a polyline as [(centreline radius that fits, turn deg, at)]. A corner gets half of each neighbouring
    segment for its arc; an end segment that terminates in a part (not a hand-over to the next route of the same
    conductor) first keeps one OD straight out of the termination, so a turn right at the plug reads radius 0."""
    out, n = [], len(pts)
    for k in range(1, n - 1):
        a, b = pts[k] - pts[k - 1], pts[k + 1] - pts[k]
        if a.length < 1e-6 or b.length < 1e-6:
            continue
        th = a.angle(b)
        if th < math.radians(20):
            continue
        ta = (max(0.0, a.length - od) if free_ends[0] else a.length) if k == 1 else a.length / 2
        tb = (max(0.0, b.length - od) if free_ends[1] else b.length) if k == n - 2 else b.length / 2
        out.append((min(ta, tb) / math.tan(th / 2), math.degrees(th), [round(c, 1) for c in pts[k]]))
    return out


def _seg_dist(p, pts):
    best = 1e9
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ab = b - a
        t = 0.0 if ab.length_squared < 1e-12 else max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
        best = min(best, (p - (a + ab * t)).length)
    return best


def _cable_shapes(chained, ends, buy):
    """Kinked corners and shared runs. v2 A7 laid the tilt and feeder bus leads in one tube for 16 mm (82.5 mm3 of
    overlap) and turned both 90 deg onto the splice face 1.5 mm below (V2R7 A7-02): cable-cable pairs were never
    tested, and bend radius was in not_checked."""
    paths = {}
    for o in CABLES:
        pts, r = cable_path(o)
        if pts and len(pts) >= 2 and r > 0:
            paths[o.name] = (pts, r)
    kinks, shared = [], []
    for n, (pts, r) in sorted(paths.items()):
        od = 2 * r
        # an end within 3 mm of a purchased part (plug, splice, board) is a termination; an end in free space, or one
        # that meets the next route of the same conductor, is a hand-over and may turn at once
        free = tuple(bool(buy and buy.find_nearest(pe, 3.0)[0] is not None) and not any(
            frozenset((n, m)) in chained and any((pe - q).length < 2.0 for q in ends.get(m, [])) for m in paths if m != n)
            for pe in (pts[0], pts[-1]))
        bad = [b for b in _bends(pts, od, free) if b[0] < CFG["cable_min_bend_od"] * od]
        if bad:
            kinks.append({"cable": n, "od_mm": round(od, 2), "bends": [{"radius_mm": round(R, 2), "turn_deg": round(t), "at": at} for R, t, at in sorted(bad)]})
    names = sorted(paths)
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            if body(O[x]) != body(O[y]) or frozenset((x, y)) in chained:
                continue
            (px, rx), (py, ry) = paths[x], paths[y]
            if bb_gap(bbox_world(O[x]), bbox_world(O[y])) > 0:
                continue
            lim, run, at = 0.5 * (rx + ry), 0.0, None
            for k in range(len(px) - 1):
                a, b = px[k], px[k + 1]
                m = max(1, int((b - a).length / 0.5))
                for j in range(m):
                    p = a + (b - a) * (j / m)
                    if _seg_dist(p, py) < lim:
                        run += (b - a).length / m
                        at = at or [round(c, 1) for c in p]
            if run > 2 * (rx + ry):
                shared.append({"cables": [x, y], "run_mm": round(run, 1), "od_mm": [round(2 * rx, 2), round(2 * ry, 2)], "from": at})
    return kinks, shared, len(paths)


def _end_drift(ends, meet=2.0, near=3.0, tol=2.0):
    """Cable ends that meet something at home (another cable's end within 2 mm, or a solid within 3 mm) on another
    body: how far they come apart at each joint limit. v2 A6 moved the bus splice off the pan axis to r 7; the static
    pan lead still ended 1.2 under it at home, and at pan +-90 its attach point was 9.9 mm away. The launcher base
    lead met the moving bundle at r 4 the same way (5.7 mm), and its distances row passed because the sleeves overlap
    (V2R6 A6-02, FINDINGS V2A6-F2). Ends that meet on the joint axis do not move apart, so they pass."""
    idx = []
    tree = scene_bvh(SOLIDS, index=idx)
    pairs = []   # (cable, end k, other object, other end k or None, home local point on the other object)
    names = sorted(ends)
    for x in names:
        for k, p in enumerate(ends[x]):
            for y in names:
                if y != x and relevant_joints(O[x], O[y]):
                    for k2, q in enumerate(ends[y]):
                        if (p - q).length < meet and (y, k2, x, k) not in [(a, b, c, e) for a, b, c, e, _ in pairs]:
                            pairs.append((x, k, y, k2, None))
            loc, _n, fi, dist = tree.find_nearest(p, near)
            if loc is not None:
                s = owner(idx, fi)
                if s and relevant_joints(O[x], O[s]):
                    pairs.append((x, k, s, None, O[s].matrix_world.inverted() @ loc))
    if not pairs:
        return []

    def endpt(c, k):
        return O[c].matrix_world @ HOME_MW[c].inverted() @ ends[c][k] if c in HOME_MW else ends[c][k]

    out = []
    for x, k, y, k2, ql in pairs:
        p0 = ends[x][k]
        q0 = ends[y][k2] if k2 is not None else HOME_MW[y] @ ql
        d0 = (p0 - q0).length
        worst = (0.0, "home")
        for jn in sorted(relevant_joints(O[x], O[y])):
            s = JOINTS.get(jn) or {}
            vals = (90.0, 180.0, 270.0) if s.get("continuous") else tuple(v for v in (s.get("lo"), s.get("hi")) if v is not None)
            for v in vals:
                set_pose({jn: v})
                p = endpt(x, k)
                q = endpt(y, k2) if k2 is not None else O[y].matrix_world @ ql
                g = (p - q).length - d0
                if g > worst[0]:
                    worst = (g, pose_key({jn: v}))
        set_pose({})
        r = {"cable": x, "end": [round(c, 1) for c in p0], "meets": y, "home_mm": round(d0, 2), "moves_apart_mm": round(worst[0], 1),
             "at": worst[1], "bodies": [body(O[x]), body(O[y])]}
        out.append(r)
        if worst[0] > tol:
            finding("cables", "warn", "%s ends %.1f mm from %s at home, but they are on different bodies (%s / %s): at %s that point is %.1f mm "
                    "further away, so the route stops short of what it plugs into. Meet on the joint axis, or put the last stretch on the moving "
                    "body after a service loop" % (x, d0, y, r["bodies"][0], r["bodies"][1], worst[1], worst[0]), **r)
    return out


def check_cables():
    rows = []
    ex = CFG["exposure"]
    set_pose({})
    tree = scene_bvh(SOLIDS) if CABLES else None
    for o in CABLES:
        L = o.get("path_len")
        lead = o.get("lead_len") or next((v for k, v in CFG["cable_leads"].items() if fnmatch.fnmatch(o.name, k)), None)
        # exposed run (A2-F8: 10 mm of feeder bus bare above the left bonnet): sample the tube, count escaping rays
        pts = _edge_samples(o, 2.0, 1200)
        exp = [p for p in pts if exposed(tree, p)]
        clusters = []   # single-linkage at 6 mm, so separate bare spots are reported separately
        for p in exp:
            near = [c for c in clusters if any((p - q).length < 6.0 for q in c)]
            merged = [p] + [q for c in near for q in c]
            clusters = [c for c in clusters if c not in near] + [merged]
        spots = []
        for c in clusters:
            lo = Vector([min(q[k] for q in c) for k in range(3)])
            hi = Vector([max(q[k] for q in c) for k in range(3)])
            spots.append({"extent_mm": round((hi - lo).length, 1), "center": [round(x, 1) for x in (lo + hi) / 2], "samples": len(c)})
        spots.sort(key=lambda r: -r["extent_mm"])
        rows.append({"object": o.name, "path_len": L, "lead_len": lead, "exposed_samples": len(exp), "samples": len(pts), "exposed_spots": spots})
        if L is not None and lead is not None and L > lead:
            finding("cables", "fail", "%s route is %.0f mm but the lead is %.0f mm" % (o.name, L, lead), object=o.name)
        for sp in spots:
            if sp["extent_mm"] > ex["max_cable_mm"] and not any(fnmatch.fnmatch(o.name, g) for g in ex["cables_ok"]):
                finding("cables", "warn", "%s: about %.0f mm of cable is visible from outside around %s (declare it under exposure.cables_ok if intended)" % (
                    o.name, sp["extent_mm"], sp["center"]), object=o.name, **sp)
    # cable_chains: conductors that run on through several routes are checked against one purchased lead. v2 A3's
    # encoder lead (150) was routed 84 mm to the journal bore and then "continued in the bundle and the base lead",
    # about 430 mm more that no BOM row bought (V2A3-F3)
    plen = {r["object"]: r["path_len"] for r in rows}
    chained = set()
    crow = []
    for C in CFG["cable_chains"]:
        miss = [c for c in C["cables"] if c not in plen]
        tot = sum(plen[c] or 0 for c in C["cables"] if c in plen)
        r = {"name": C.get("name") or "+".join(C["cables"]), "cables": C["cables"], "route_mm": round(tot, 1), "lead_mm": C.get("lead"),
             "why": C.get("why")}
        crow.append(r)
        chained |= {frozenset((x, y)) for x in C["cables"] for y in C["cables"] if x != y}
        if miss:
            finding("cables", "fail", "cable chain '%s': %s not in the scene" % (r["name"], miss), **r)
        elif C.get("lead") is not None and tot > C["lead"]:
            finding("cables", "fail", "cable chain '%s' runs %.0f mm through %s, but its lead is %.0f mm" % (r["name"], tot, " + ".join(C["cables"]), C["lead"]), **r)
    # ends that meet another cable's end with no purchased part (a connector, a board) within 3 mm: either the
    # conductors run on (declare a chain) or there is a connector to name (cable_junctions_ok)
    ends = {}
    for o in CABLES:
        e = o.get("cab_ends")
        if e is not None and len(e) == 6:
            M = o.matrix_world @ HOME_MW.get(o.name, o.matrix_world).inverted()
            ends[o.name] = [M @ Vector(e[:3]), M @ Vector(e[3:])]
    buy = scene_bvh(PURCHASED) if PURCHASED and ends else None
    junctions, waived = [], []
    names = sorted(ends)
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            if frozenset((x, y)) in chained:
                continue
            ok = any(fnmatch.fnmatch(x, g) or fnmatch.fnmatch(y, g) for g in CFG["cable_junctions_ok"])
            for p in ends[x]:
                if any((p - q).length < 2.0 for q in ends[y]) and not (buy and buy.find_nearest(p, 3.0)[0] is not None):
                    (waived if ok else junctions).append({"cables": [x, y], "at": [round(c, 1) for c in p]})
                    break
    if junctions:
        finding("cables", "warn", "%d cable junctions with no purchased part (connector or board) within 3 mm: %s. If the conductors run on, "
                "add a cable_chains row so the whole run is checked against one lead; if a connector or splice block sits there, model "
                "it as a BUY_ part (it takes room in the bore and in the twist), or list the cables under cable_junctions_ok if it "
                "is no wider than the cable" % (len(junctions), "; ".join("%s / %s at %s" % (j["cables"][0], j["cables"][1], j["at"]) for j in junctions[:6])),
                junctions=junctions)
    drift = _end_drift(ends) if ends else []
    kinks, shared, n_paths = _cable_shapes(chained, ends, buy)
    for k in kinks:
        finding("cables", "warn", "%s (OD %g) kinks: %s. Round the corner (centreline radius >= %g x OD) and leave one OD of straight "
                "lead out of a plug or splice" % (k["cable"], k["od_mm"], "; ".join("%d deg at %s with radius %.1f" % (
                    b["turn_deg"], b["at"], b["radius_mm"]) for b in k["bends"][:3]), CFG["cable_min_bend_od"]), **k)
    for r in shared:
        finding("cables", "warn", "%s and %s lie in one tube for %.0f mm from %s: two leads cannot share a place. Route them side by side "
                "(the channel or groove must hold both), or model the bundle as one cable with a cable_chains row per conductor" % (
                    r["cables"][0], r["cables"][1], r["run_mm"], r["from"]), **r)
    # waived junctions stay visible: v2 A5 waived a 3-way bus junction it never modelled, and V2R5 raised it (A5-03)
    REPORT["checks"].setdefault("cables", {"findings": []}).update(chains=crow, junctions=junctions, junctions_waived=waived, ends_known=len(ends),
                                                                    end_drift=drift, kinks=kinks, shared_runs=shared)
    nolead = [r["object"] for r in rows if r["lead_len"] is None]
    if nolead:
        # v2 A2: only the phase leads had a length; bus, UART and encoder runs across the pan joint went unchecked (V2A2-F4)
        finding("cables", "warn", "%d cables have no lead length (cable_leads or lead_len), so route vs purchased lead is unchecked: %s" % (
            len(nolead), ", ".join(nolead[:10]) + (" ..." if len(nolead) > 10 else "")), objects=nolead)
    REPORT["checks"].setdefault("cables", {"findings": []})["rows"] = rows
    have = sum(1 for r in rows if r["path_len"] is not None)
    REPORT["coverage"].append("cables: %d routes, %d with path length, %d chains; junctions on %d routes with known ends (cadlib cab_ends), %d waived "
                              "with no modelled part (cable_junctions_ok); "
                              "exposure (>= %d of 26 rays escape, or %d%% of the directions toward a viewer) at home pose" % (
        len(rows), have, len(crow), len(ends), len(waived), ex["min_escape"], 100 * ex["view_frac"]))
    REPORT["coverage"].append("cables: %d routes with a known path: corners under %g x OD (one OD straight out of a plug or splice), "
                              "and pairs on one body sharing a tube for more than 2 OD" % (n_paths, CFG["cable_min_bend_od"]))
    REPORT["not_checked"].append("cables: bend radius of a lead that is not modelled as a route, slack across joints, connector positions (review by section render)")


# ------------------------------------------------------------------ main

def check_pose_values():
    """Every pose a row asks for must name a joint and sit inside its range. set_pose takes any number, so v2 A4's
    planner pre-ran full-lift rows at PIV_nip_lift -2.19 on a model whose limit was -1.493: the hood was posed through
    the solid leaf and the rows passed (progress.md "Tool issues", FINDINGS V2A4-T2). Rows past a firmware limit on
    purpose (a hard stop beyond it, "1 deg past the stop") are common: 7 in v2 A4's config. So a pose outside the range
    is listed in the summary, not warned; a pose naming no joint, or a coupled one, is a config fail."""

    def walk(x, at):
        if isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, "%s[%d]" % (at, i))
        elif isinstance(x, dict):
            for k, v in x.items():
                if k in ("pose", "poses") and not x.get("past_limit_ok"):
                    for j, ps in enumerate(v if isinstance(v, list) else [v]):
                        if isinstance(ps, dict):
                            check(ps, "%s.%s" % (at, k) + ("[%d]" % j if isinstance(v, list) else ""))
                else:
                    walk(v, "%s.%s" % (at, k))

    def check(ps, at):
        for jn, val in ps.items():
            if not isinstance(jn, str) or not jn.startswith("PIV_") or not isinstance(val, (int, float)):
                continue
            if jn not in JOINTS:
                finding("config", "fail", "%s: pose names %s, which is not a joint in the model (set_pose would ignore it)" % (at, jn), at=at, joint=jn)
                continue
            if jn in COUPLE:
                finding("config", "fail", "%s: %s is coupled to %s, so a pose on it is overwritten; pose %s instead" % (at, jn, COUPLE[jn]["to"], COUPLE[jn]["to"]), at=at, joint=jn)
                continue
            sp = JOINTS[jn]
            if sp.get("continuous") or sp["lo"] is None or sp["hi"] is None:
                continue
            if not float(sp["lo"]) - 1e-3 <= val <= float(sp["hi"]) + 1e-3:
                PAST_LIMITS.append({"at": at, "joint": jn, "value": val, "lo": sp["lo"], "hi": sp["hi"]})

    for key, v in CFG.items():
        if key not in ("accepted_warns", "joints", "couplings", "carry"):
            walk(v, key)


def stale_model():
    """Build sources next to the blend that are newer than it: the last `cad build` failed (or never ran), so this
    report is about the previous model. v2 A4's launcher builder piped a failed build through tail and read a clean
    check of the old blend (FINDINGS V2A4-T1)."""
    b = bpy.data.filepath
    if not b or not os.path.isfile(b):
        return []
    d = os.path.dirname(b)
    t = os.path.getmtime(b)
    srcs = glob.glob(os.path.join(d, "*.py")) + glob.glob(os.path.join(d, "parts", "*.py"))
    return sorted((os.path.relpath(x, d), time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(x))))
                  for x in srcs if os.path.getmtime(x) > t + 2.0)


def main():
    set_pose({})
    HOME_MW.update({o.name: o.matrix_world.copy() for o in ALL})
    if EXPRS:
        REPORT["params"] = {"source": PARAMS_SRC, "expressions": EXPRS}
        for e in EXPRS:
            if "error" in e:
                finding("config", "fail", "%s: expression '=%s' failed (%s; params from %s)" % (e["at"], e["expr"], e["error"], PARAMS_SRC), **e)
    check_pose_values()
    old_srcs = stale_model()
    if old_srcs:
        REPORT["stale_model"] = old_srcs
        finding("build", "warn", "the model is older than %s (blend saved %s): the last cad build failed or was not run, so this report is about "
                "the previous model. Rebuild, then check" % (", ".join("%s (%s)" % x for x in old_srcs[:4]),
                                                              time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(bpy.data.filepath)))))
    log("objects: %d printed, %d purchased, %d fasteners, %d cables; joints %s" % (
        len(PRINTED), len(PURCHASED), len(FASTENERS), len(CABLES),
        {n: (s["axis"], s["lo"], s["hi"]) for n, s in JOINTS.items()}))
    for name, fn in (("parts", check_parts), ("interference", check_interference), ("fasteners", check_fasteners),
                     ("service", check_service), ("drop", check_drop), ("index", check_index), ("slide", check_slide),
                     ("distances", check_distances), ("payload", check_payload), ("sightlines", check_sightlines),
                     ("assembly", check_assembly), ("insertion", check_insertion), ("stacks", check_stacks), ("flexures", check_flexures), ("stability", check_stability), ("cables", check_cables)):
        if want(name) or (name == "interference" and want("clearance")):
            t = time.time()
            fn()
            REPORT["checks"].setdefault(name, {"findings": []})["runtime_s"] = round(time.time() - t, 1)
            log("%s done" % name)
    if not CABLES:
        REPORT["not_checked"].append("cables: Cables collection empty")
    REPORT["not_checked"].append("not geometric: teardown step count, alignment-jig datums (declare stacks), aesthetics, BOM correctness")
    acc = CFG.get("accepted_warns") or []
    accepted = {w: next(a.get("why", "") for a in acc if a["match"] in w) for w in WARNS
                if any(a["match"] in w for a in acc) and not w.startswith("build: ")}   # a stale model is never accepted
    untriaged = [w for w in WARNS if w not in accepted]
    # under --only most warns never get a chance to fire, so "matched nothing" would list nearly every accept
    stale = [] if ONLY else [a["match"] for a in acc if not any(a["match"] in w for w in WARNS)]
    REPORT["summary"] = {"pass": not FAILS, "fails": len(FAILS), "warns": len(WARNS), "untriaged_warns": len(untriaged),
                         "fail_list": FAILS, "warn_list": untriaged, "accepted_warns": accepted, "stale_accepts": stale,
                         "coverage": REPORT["coverage"], "not_checked": REPORT["not_checked"], "poses_past_limits": PAST_LIMITS,
                         "unbounded_allows": UNBOUNDED_ALLOWS,
                         "runtime_s": round(time.time() - T0, 1)}
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(REPORT, f, indent=1, default=str)
    print("CADCHECK %s: %d fail, %d warn (%d untriaged, %d accepted) -> %s" % (
        "PASS" if not FAILS else "FAIL", len(FAILS), len(WARNS), len(untriaged), len(accepted), OUT))
    for s in FAILS[:40]:
        print("  FAIL", s)
    for s in untriaged[:25]:
        print("  warn", s)
    if len(untriaged) > 25:
        print("  ... %d more untriaged warnings in the report" % (len(untriaged) - 25))
    if stale:
        print("  accepted_warns that matched nothing (fixed? remove them):", stale)
    if PAST_LIMITS:
        # the parts are posed through their stops: a hard stop beyond a firmware limit is fine, a joint limit the model
        # has not caught up with is not (V2A4-T2). Mark intended rows "past_limit_ok": true to drop them from this list
        by = {}
        for x in PAST_LIMITS:
            by.setdefault((x["joint"], x["lo"], x["hi"]), {}).setdefault(x["value"], set()).add(x["at"].split(".pose")[0])
        print("  poses outside the joint range (posed through the stops; intended?):", "; ".join(
            "%s range %g..%g: %s" % (j, lo, hi, ", ".join("%g in %s" % (v, " ".join(sorted(r))) for v, r in sorted(vals.items())))
            for (j, lo, hi), vals in sorted(by.items())))
    if UNBOUNDED_ALLOWS:
        # an allow skips the pair at every pose, so a deeper clash in a sweep never shows; give a riding or crushing
        # pair "max_mm3" (V2R5 A5-06: the gate detent allow, 0.43 mm3 by its own reason, hid the whole gate sweep)
        print("  allows that skip a pair across a joint with no max_mm3 (any clash there is hidden):", "; ".join(sorted(UNBOUNDED_ALLOWS)))
    print("  not checked:", "; ".join(REPORT["not_checked"]))


if __name__ == "__main__" and not os.environ.get("CADCHECK_NO_MAIN"):
    main()
