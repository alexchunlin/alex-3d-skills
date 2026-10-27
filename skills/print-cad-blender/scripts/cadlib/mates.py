"""Mate connectors: parts placed by their interfaces, not by world coordinates.

A connector is a named frame on a part, in the frame the part was modelled in: an origin on the mating face, z pointing
out of the part, x in the face. A mate joins two connectors face to face (origins together, z axes opposed, x axes
together), optionally with a gap along z and a turn about z. assemble() walks the mate tree from one grounded part,
places every part (bakes its world transform into the mesh), makes a PIV_ joint (asm.joint) for each revolute or
prismatic mate, runs features.fastener_joint once per pattern point of each fastened mate, cuts the holes and registers
the parts with asm.part. The mate table goes into the .blend (scene "cad_mates") and the manifest ("mates");
`cad mates manifest.json [REGEX]` prints one line per mate.

    from cadlib import geom as G, asm as A, mates as M
    deck = G.box("deck", -40, 40, -40, 40, 0, 4)
    M.connector(deck, "pcb", (20, 0, 4), z=(0, 0, 1), pattern=M.rect(42, 32), hole="M2.5")
    M.part(deck, "PRT_deck", 'PRT', "pla_a", stl="deck", print_rot=A.R_ID, orient="flat", supports="no", infill=20)
    M.from_component(board, C["pcb"])                       # connectors from components.json, once per purchased part
    M.part(board, "BUY_pcb", 'BUY', "pcb", mass_g=8, src="datasheet")
    M.mate("PRT_deck:pcb", "BUY_pcb:mount", "fastened", fit="clearance",
           fastener=dict(size="M2.5", style="selftap", head="pan"), gap=8)
    M.assemble("PRT_deck")

Rules the solver enforces (each raises MateError with the fix):
- the mates form a tree from the ground part; a loop, or a part not reached, raises;
- two connectors that both carry a hole pattern must match in count, positions and hole size (both specs printed);
- a revolute or prismatic axis must be a world axis (asm.joint and cadcheck sweep X, Y or Z);
- parts are modelled with the object at identity (mesh coordinates are the part's own frame).
"""
import json, math
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from . import geom, features, asm

KINDS = ("rigid", "fastened", "revolute", "prismatic")
FITS = (None, "press", "slip", "clearance", "snap")
PATTERN_TOL = 0.01          # mm: two patterns from the same datasheet numbers agree to float noise
AXIS_TOL = 1e-6


class MateError(ValueError):
    """A connector, mate or assembly that can't be solved; the message says what to change."""


# ------------------------------------------------------------------ patterns (in the connector's x/y plane)

def rect(px, py):
    """4 holes on a px x py rectangle centred on the connector, in reading order: (-x,-y), (+x,-y), (-x,+y), (+x,+y)."""
    return ["rect", float(px), float(py)]


def circle(pcd, n, a0=0.0):
    """n holes on a pitch circle of diameter pcd, the first at a0 degrees from x toward y."""
    return ["circle", float(pcd), int(n), float(a0)]


def line(pitch, n):
    """n holes along x at `pitch`, centred on the connector."""
    return ["line", float(pitch), int(n)]


def points(pts):
    """Explicit hole positions (x, y) in the connector frame, seen from outside the face (z toward you): the bottom
    face of a board sees its datasheet's top view mirrored in y."""
    return ["points", [[float(p[0]), float(p[1])] for p in pts]]


def pattern_points(pattern):
    """[(x, y), ...] in the connector frame; [(0, 0)] for no pattern."""
    if not pattern:
        return [(0.0, 0.0)]
    k = pattern[0]
    if k == "rect":
        px, py = pattern[1] / 2, pattern[2] / 2
        return [(sx * px, sy * py) for sy in (-1, 1) for sx in (-1, 1)]
    if k == "circle":
        r, n, a0 = pattern[1] / 2, int(pattern[2]), pattern[3] if len(pattern) > 3 else 0.0
        return [(r * math.cos(math.radians(a0 + 360.0 * i / n)), r * math.sin(math.radians(a0 + 360.0 * i / n)))
                for i in range(n)]
    if k == "line":
        p, n = pattern[1], int(pattern[2])
        return [((i - (n - 1) / 2.0) * p, 0.0) for i in range(n)]
    if k == "points":
        return [(float(x), float(y)) for x, y in pattern[1]]
    raise MateError("pattern %r: use rect(px, py), circle(pcd, n, a0), line(pitch, n) or points([...])" % (pattern,))


def pattern_str(pattern):
    if not pattern:
        return "single"
    if pattern[0] == "points":
        return "points(%s)" % ", ".join("(%g, %g)" % tuple(p) for p in pattern[1])
    return "%s(%s)" % (pattern[0], ", ".join("%g" % v for v in pattern[1:]))


def _norm_pattern(p):
    """Accept the list form, or the dict form a components.json entry may use ({"rect": [58, 49]})."""
    if p is None or isinstance(p, list) and p and isinstance(p[0], str):
        return p
    if isinstance(p, dict) and len(p) == 1:
        k, v = next(iter(p.items()))
        return {"rect": lambda: rect(*v), "circle": lambda: circle(*v), "line": lambda: line(*v),
                "points": lambda: points(v)}[k]()
    raise MateError("pattern %r: use rect(px, py), circle(pcd, n, a0), line(pitch, n) or points([...])" % (p,))


# ------------------------------------------------------------------ connectors

def default_x(z):
    """x for a connector that doesn't give one: the frame's +X flattened into the face, or +Z when z is along X.
    Two parts modelled in the same orientation then mate without turning about z."""
    z = Vector(z).normalized()
    for ref in (Vector((1, 0, 0)), Vector((0, 0, 1))):
        x = ref - z * ref.dot(z)
        if x.length > 1e-3:
            return x.normalized()
    raise MateError("no default x for z=%s" % list(z))


def frame_matrix(origin, z, x):
    z = Vector(z).normalized()
    x = Vector(x).normalized()
    return geom.frame(Vector(origin), x, z.cross(x), z)


def _conns(ob):
    return json.loads(ob.get("mate_connectors", "{}"))


def connector(ob, name, origin=(0, 0, 0), z=(0, 0, 1), x=None, pattern=None, hole=None, note=None):
    """Name a frame on `ob`, in the frame its mesh was modelled in. `z` points out of the part, from the mating face;
    `x` lies in the face (default: default_x(z)). `pattern` is rect/circle/line/points; `hole` a size ("M3").
    Stored on the object, so it moves with it. Returns "<object>:<name>"."""
    zv = Vector(z)
    if zv.length < 1e-9:
        raise MateError("%s:%s: z is zero" % (ob.name, name))
    zv.normalize()
    xv = default_x(zv) if x is None else Vector(x).normalized()
    if abs(xv.dot(zv)) > 1e-3:
        raise MateError("%s:%s: x %s is not perpendicular to z %s (dot %.3f)" % (
            ob.name, name, _r(x), _r(z), xv.dot(zv)))
    xv = (xv - zv * xv.dot(zv)).normalized()
    pat = _norm_pattern(pattern)
    pattern_points(pat)
    if hole is not None and str(hole) not in features.SIZES:
        raise MateError("%s:%s: hole %r: one of %s" % (ob.name, name, hole, sorted(features.SIZES)))
    c = _conns(ob)
    c[name] = {"origin": [float(v) for v in origin], "z": list(map(float, zv)), "x": list(map(float, xv)),
               "pattern": pat, "hole": hole, "note": note}
    ob["mate_connectors"] = json.dumps(c)
    return "%s:%s" % (ob.name, name)


def from_component(ob, comp, names=None):
    """Connectors from a components.json entry's "connectors" block (in the placeholder's local frame):
    {"spline": {"origin": [0, 0, 3.9], "z": [0, 0, 1], "pattern": ["circle", 14, 4, 45], "hole": "M2"}}."""
    cs = comp.get("connectors") or {}
    if not cs:
        raise MateError("%s: no \"connectors\" in this components.json entry (%s)" % (ob.name, comp.get("what", "?")))
    for n, c in cs.items():
        if names is None or n in names:
            connector(ob, n, c.get("origin", (0, 0, 0)), c.get("z", (0, 0, 1)), c.get("x"), c.get("pattern"),
                      c.get("hole"), c.get("note"))
    return ob


def local_frame(ob, name):
    c = _conns(ob).get(name)
    if c is None:
        raise MateError("%s has no connector %r (it has %s)" % (ob.name, name, sorted(_conns(ob))))
    return frame_matrix(c["origin"], c["z"], c["x"])


def _placement(ob):
    if "mate_frame" in ob.keys():
        v = list(ob["mate_frame"])
        return Matrix([v[0:4], v[4:8], v[8:12], v[12:16]])
    return Matrix.Identity(4)


def frame_of(ref):
    """World frame (4x4: columns x, y, z, origin) of connector "PART:name" at the scene's current pose."""
    ob, n = _resolve(ref)
    return ob.matrix_world @ _placement(ob) @ local_frame(ob, n)


def world_points(ref, M=None):
    """World positions of a connector's pattern points (current pose, or under placement M)."""
    ob, n = _resolve(ref)
    F = (ob.matrix_world @ _placement(ob) if M is None else M) @ local_frame(ob, n)
    return [F @ Vector((x, y, 0.0)) for x, y in pattern_points(_conns(ob)[n]["pattern"])]


# ------------------------------------------------------------------ parts and mates (declared; solved by assemble)

def part(ob, name, kind, color, **info):
    """Declare a part for assemble(): as asm.part (same info keys), but `print_rot` is in the part's own frame (how
    you'd lay the part as modelled on the bed); assemble converts it to world. The part is renamed now, so connector
    refs and fastener stacks can use the final name."""
    assert name.startswith(kind + "_"), "%s must start with %s_" % (name, kind)
    if name in asm.MATE_PARTS:
        raise MateError("%s declared twice" % name)
    if ob.parent is not None or ob.matrix_basis != Matrix.Identity(4):
        raise MateError("%s: the object has a transform; model parts in mesh coordinates (their own frame) and let "
                        "assemble() place them" % name)
    ob.name = name
    if ob.name != name:
        raise MateError("%s: another object already has this name (got %s)" % (name, ob.name))
    ob.data.name = name
    asm.MATE_PARTS[name] = {"ob": ob, "kind": kind, "color": color, "info": info}
    return ob


def mate(a, b, kind="rigid", name=None, gap=0.0, rot=0.0, fit=None, lo=None, hi=None, home=0.0, sweep_step=None,
         continuous=False, fastener=None, step=None, note=None, **joint_kw):
    """Mate connector `a` ("PART:conn") with `b` face to face: b's origin on a's, b's z opposite a's, x together,
    then `gap` mm apart along a's z and turned `rot` degrees about it.

    kind: "rigid" (glued, pressed, snapped), "fastened" (screws, one per pattern point), "revolute" (turns about a's
          z: lo/hi/home in degrees, positive = right-handed about the parent side's z), "prismatic" (slides along a's
          z: lo/hi/home in mm, positive = apart). Revolute and prismatic mates become asm.joint(name, ...): name is
          the PIV_ joint (default PIV_<b part>), sweep_step its sweep step, continuous / couple_to / couple_ratio pass
          through. The part farther from the ground moves.
    fit:  None, "press", "slip", "clearance" or "snap" (recorded in the mate table).
    fastener (fastened): dict for features.fastener_joint: size (default the connectors' hole), style ("selftap",
          "nut", "insert", "tapped"), head ("cap", "pan", "csk"), sink, head_on ("a" or "b": the part the head bears
          on, default "b"), name (FST_ prefix, default FST_<mate name>; _<i> per point when there are several),
          head_depth (mm from the mating face to the head's bearing face; default measured through the head part),
          stack (more part names between the two), and any other fastener_joint keyword (trap, through_ok, gap_ok,
          length, lengths, depth, print_up, nut_rot_deg, min_engagement).
    step: the assembly step label for the fasteners (as fastener_joint's step).
    """
    if kind not in KINDS:
        raise MateError("mate %s-%s: kind %r: one of %s" % (a, b, kind, KINDS))
    if fit not in FITS:
        raise MateError("mate %s-%s: fit %r: one of %s" % (a, b, fit, FITS[1:]))
    if kind in ("revolute", "prismatic"):
        name = name or "PIV_" + _short(b.split(":")[0])
        if not name.startswith("PIV_"):
            raise MateError("mate %s: a %s mate is a joint; its name starts with PIV_" % (name, kind))
        if (lo is None or hi is None) and not continuous:
            raise MateError("mate %s: a %s mate needs lo and hi (its real range)" % (name, kind))
    if kind == "fastened" and fastener is None:
        fastener = {}
    if kind != "fastened" and fastener:
        raise MateError("mate %s-%s: fastener= is for kind='fastened'" % (a, b))
    name = name or "%s-%s" % (_short(a.split(":")[0]), _short(b.split(":")[0]))
    if any(m["name"] == name for m in asm.MATES):
        raise MateError("mate %s declared twice; give one a name=" % name)
    asm.MATES.append(dict(name=name, a=a, b=b, kind=kind, gap=float(gap), rot=float(rot), fit=fit, lo=lo, hi=hi,
                          home=float(home), sweep_step=sweep_step, continuous=bool(continuous),
                          fastener=dict(fastener) if fastener is not None else None, step=step, note=note,
                          joint_kw=joint_kw))
    return name


def fasten(conn, name=None, step=None, note=None, **fastener):
    """Screws into one part only (floor screws, a bolt through a wall): one per pattern point of `conn`, head on the
    connector's face, shank into the part (against z). Recorded in the mate table as a fastened mate to nothing."""
    n = name or "FST_" + _short(conn.split(":")[0]) + "_" + conn.split(":")[1]
    fastener = dict(fastener, name=n)
    asm.MATES.append(dict(name=n[4:] if n.startswith("FST_") else n, a=conn, b=None, kind="fastened", gap=0.0, rot=0.0,
                          fit=None, lo=None, hi=None, home=0.0, sweep_step=None, continuous=False, fastener=fastener,
                          step=step, note=note, joint_kw={}))
    return n


# ------------------------------------------------------------------ solve

def _short(n):
    for p in ("PRT_", "BUY_", "FST_", "CAB_"):
        if n.startswith(p):
            return n[len(p):]
    return n


def _r(v, nd=3):
    return [round(float(c), nd) + 0.0 for c in v]


def _resolve(ref):
    if not isinstance(ref, str) or ":" not in ref:
        raise MateError("connector %r: write it as \"PART:connector\"" % (ref,))
    pn, cn = ref.split(":", 1)
    if pn in asm.MATE_PARTS:
        ob = asm.MATE_PARTS[pn]["ob"]
    else:
        ob = bpy.data.objects.get(pn)
        if ob is None:
            raise MateError("connector %s: no part %s (declared: %s)" % (ref, pn, sorted(asm.MATE_PARTS)))
    if cn not in _conns(ob):
        raise MateError("connector %s: %s has no connector %r (it has %s)" % (ref, pn, cn, sorted(_conns(ob))))
    return ob, cn


FLIP = Matrix.Rotation(math.pi, 4, 'X')


def mated_frame(Fp, gap=0.0, rot=0.0):
    """World frame of the child connector given the parent connector's world frame (face to face)."""
    return Fp @ Matrix.Rotation(math.radians(rot), 4, 'Z') @ Matrix.Translation((0, 0, gap)) @ FLIP


def _axis_letter(z, what):
    for i, L in enumerate("XYZ"):
        if abs(abs(z[i]) - 1.0) < AXIS_TOL and all(abs(z[j]) < AXIS_TOL for j in range(3) if j != i):
            return L, (1.0 if z[i] > 0 else -1.0)
    raise MateError("%s: its axis %s is not a world axis. asm.joint and cadcheck's sweeps turn about X, Y or Z: model "
                    "the parts so this mate's parent connector z is along one (a tilted axis is not supported yet)" % (
                        what, _r(z, 4)))


def _check_patterns(m, Ma, Mb):
    oa, ca = _resolve(m["a"])
    ob_, cb = _resolve(m["b"])
    sa, sb = _conns(oa)[ca], _conns(ob_)[cb]
    if sa["hole"] and sb["hole"] and sa["hole"] != sb["hole"]:
        _pattern_fail(m, sa, sb, "hole sizes differ (%s vs %s)" % (sa["hole"], sb["hole"]))
    if not (sa["pattern"] and sb["pattern"]):
        return
    pa = world_points(m["a"], Ma)
    pb = world_points(m["b"], Mb)
    if len(pa) != len(pb):
        _pattern_fail(m, sa, sb, "%d points on a, %d on b" % (len(pa), len(pb)))
    Fa_inv = (Ma @ local_frame(oa, ca)).inverted()
    worst, where = 0.0, None
    for P, Q in ((pa, pb), (pb, pa)):
        for p in P:
            d = min((p - q).length for q in Q)
            if d > worst:
                worst, where = d, p
    if worst > PATTERN_TOL:
        loc = Fa_inv @ where
        why = "a point at (%.2f, %.2f) in a's frame (world %s) is %.3f mm from the nearest point of the other " \
              "pattern" % (loc.x, loc.y, _r(where, 2), worst)
        Fa = Ma @ local_frame(oa, ca)
        mir = [Fa @ Vector((x, -y, 0.0)) for x, y in pattern_points(sa["pattern"])]
        if all(min((p - q).length for q in pb) <= PATTERN_TOL for p in mir):
            why += ". They match mirrored in y: one side was typed as seen from the other face. A pattern is seen " \
                   "from outside its face (z toward you): negate y on one side (circle: a0 -> -a0)"
        _pattern_fail(m, sa, sb, why)


def _pattern_fail(m, sa, sb, why):
    raise MateError(
        "mate %s (%s): the connectors' hole patterns don't match: %s.\n"
        "  a %-28s pattern %-22s hole %s (%d points)\n"
        "  b %-28s pattern %-22s hole %s (%d points)\n"
        "Both sides should come from the same datasheet numbers: fix the one that was typed by hand." % (
            m["name"], m["kind"], why, m["a"], pattern_str(sa["pattern"]), sa["hole"], len(pattern_points(sa["pattern"])),
            m["b"], pattern_str(sb["pattern"]), sb["hole"], len(pattern_points(sb["pattern"]))))


def _depth_through(ob, p, into, size, head):
    """mm from mate point p back through `ob` (against `into`) to its far face: on the axis, else on a ring between
    the clearance hole and the head (a pre-drilled board has no material on the axis)."""
    me = ob.data
    tree = BVHTree.FromPolygons([v.co for v in me.vertices], [tuple(f.vertices) for f in me.polygons])
    back = -Vector(into).normalized()
    S = features.size_rules(size)
    hits = []
    loc, nrm, idx, t = tree.ray_cast(p + back * 1e-3, back)       # from just inside the mating face
    if loc is not None:
        return t + 1e-3
    u = back.orthogonal().normalized()
    v = back.cross(u)
    r = 0.5 * (S["clear_d"] / 2 + S[head][0] / 2)
    for k in range(8):
        a = 2 * math.pi * k / 8
        q = p + (u * math.cos(a) + v * math.sin(a)) * r
        loc, nrm, idx, t = tree.ray_cast(q + back * 1e-3, back)
        if loc is not None:
            hits.append(t + 1e-3)
    if not hits:
        return None
    hits.sort()
    return hits[len(hits) // 2]


def assemble(ground, at=None):
    """Place every part declared with part() from `ground` through the mates; make the joints; cut the fastened mates'
    holes; register the parts (asm.part). `at` is the ground's world placement (4x4, default identity).
    Returns {part name: 4x4 world matrix of its modelling frame at home}."""
    P = asm.MATE_PARTS
    if ground not in P:
        raise MateError("ground %s is not a declared part (declared: %s)" % (ground, sorted(P)))
    mates = asm.MATES
    for m in mates:
        _resolve(m["a"])
        if m["b"] is not None:
            _resolve(m["b"])
            for side in ("a", "b"):
                if m[side].split(":")[0] not in P:
                    raise MateError("mate %s: %s is not declared with mates.part()" % (m["name"], m[side]))
            if m["a"].split(":")[0] == m["b"].split(":")[0]:
                raise MateError("mate %s mates a part with itself" % m["name"])
    place = {ground: Matrix(at) if at is not None else Matrix.Identity(4)}
    body = {ground: None}
    parent = {ground: None}          # part -> (parent part, mate)
    used = set()
    queue = [ground]
    while queue:
        cur = queue.pop(0)
        for m in mates:
            if m["b"] is None or id(m) in used:
                continue
            pa, pb = m["a"].split(":")[0], m["b"].split(":")[0]
            if cur not in (pa, pb):
                continue
            other = pb if cur == pa else pa
            if other in place:
                raise MateError(_loop_msg(m, pa, pb, parent))
            used.add(id(m))
            pref, cref = (m["a"], m["b"]) if cur == pa else (m["b"], m["a"])
            po, pc = _resolve(pref)
            co, cc = _resolve(cref)
            Fp = place[cur] @ local_frame(po, pc)
            place[other] = mated_frame(Fp, m["gap"], m["rot"]) @ local_frame(co, cc).inverted()
            parent[other] = (cur, m)
            m["_parent"], m["_child"] = cur, other
            m["_origin"], m["_z"] = list(Fp.translation), list(Fp.col[2][:3])
            if m["kind"] in ("revolute", "prismatic"):
                L, sgn = _axis_letter(Fp.col[2][:3], "%s mate %s" % (m["kind"], m["name"]))
                lo, hi, home = m["lo"], m["hi"], m["home"]
                if sgn < 0 and lo is not None:
                    lo, hi = -hi, -lo
                kw = dict(m["joint_kw"])
                if "couple_to" in kw:
                    # couple_ratio is between mate values; each PIV value is the mate value times its axis sign
                    o = asm.JOINTS.get(kw["couple_to"])
                    if o is None:
                        raise MateError("mate %s: couple_to %s is not a joint yet: it must be nearer the ground in the "
                                        "mate tree" % (m["name"], kw["couple_to"]))
                    s2 = o.get("mate_axis_sign", 1.0)
                    kw["couple_ratio"] = sgn * s2 * float(kw.get("couple_ratio", 1.0))
                asm.joint(m["name"], tuple(Fp.translation), L, lo, hi, parent=body[cur], home=sgn * home,
                          step=m["sweep_step"], continuous=m["continuous"], prismatic=m["kind"] == "prismatic", **kw)
                asm.JOINTS[m["name"]]["mate_axis_sign"] = sgn
                body[other] = m["name"]
                m["_axis"] = ("+" if sgn > 0 else "-") + L
            else:
                body[other] = body[cur]
            queue.append(other)
    lost = [n for n in P if n not in place]
    if lost:
        raise MateError("not mated to the ground (%s): %s. Mate each to a placed part, or chain it through one" % (
            ground, lost))
    for m in mates:
        if m["b"] is not None and id(m) not in used:
            raise MateError(_loop_msg(m, m["a"].split(":")[0], m["b"].split(":")[0], parent))
    # bake: the mesh goes to world at home, the placement stays on the object for its connectors
    for n, M in place.items():
        ob = P[n]["ob"]
        if M != Matrix.Identity(4):
            geom.xform(ob, M)
        ob["mate_frame"] = [M[i][j] for i in range(4) for j in range(4)]
    for m in mates:
        if m["b"] is not None:
            _check_patterns(m, place[m["a"].split(":")[0]], place[m["b"].split(":")[0]])
    # fasteners, in declaration order (fastener_joint reuses lengths already in the build)
    cuts = {}
    for m in mates:
        if m["kind"] == "fastened":
            _fasten(m, place, body, cuts)
    for n, info in P.items():
        if cuts.get(n):
            geom.csg(info["ob"], sub=cuts[n])
    unknown = [k for k, v in cuts.items() if v and k not in P]
    if unknown:
        raise MateError("fastener cuts for parts assemble() doesn't own: %s (declare them with mates.part)" % unknown)
    for n, info in P.items():
        kw = dict(info["info"])
        if "print_rot" in kw:
            R = Matrix(kw["print_rot"]).to_3x3()
            kw["print_rot"] = R @ place[n].to_3x3().inverted()
        asm.part(info["ob"], n, info["kind"], info["color"], joint=body[n], **kw)
        asm.PARTS[n]["placed_by"] = "mate %s" % parent[n][1]["name"] if parent[n] else "ground"
    asm.MATE_TABLE[:] = [_record(m) for m in mates]
    bpy.context.scene["cad_mates"] = json.dumps(asm.MATE_TABLE)
    return place


def _loop_msg(m, pa, pb, parent):
    def chain(n):
        out = [n]
        while parent.get(n):
            n = parent[n][0]
            out.append(n)
        return out
    ca, cb = chain(pa), chain(pb)
    path = " -> ".join(reversed(ca)) + " | " + " -> ".join(reversed(cb))
    return ("mate %s (%s %s - %s) closes a loop: both parts are already placed through other mates (%s). Loops "
            "are not solved: drop this mate, or make it a fastened/rigid mate between parts that are not otherwise "
            "connected" % (m["name"], m["kind"], m["a"], m["b"], path))


def _fasten(m, place, body, cuts):
    f = dict(m["fastener"] or {})
    oa, ca = _resolve(m["a"])
    sa = _conns(oa)[ca]
    holes = {sa["hole"]}
    if m["b"] is not None:
        ob_, cb = _resolve(m["b"])
        holes.add(_conns(ob_)[cb]["hole"])
    holes.discard(None)
    size = f.pop("size", None) or (holes.pop() if holes else None)
    if size is None:
        raise MateError("mate %s: no fastener size: give fastener=dict(size=...) or a hole= on a connector" % m["name"])
    head = f.pop("head", "cap")
    sink = float(f.pop("sink", 0.0))
    head_on = f.pop("head_on", "b")
    depth = f.pop("head_depth", None)
    stack = [asm.MATE_PARTS[s]["ob"] if s in asm.MATE_PARTS else bpy.data.objects[s] for s in f.pop("stack", [])]
    fname = f.pop("name", None) or "FST_" + m["name"].replace("PIV_", "")
    if m["b"] is None:
        hob, href, other = oa, m["a"], None
    else:
        if head_on not in ("a", "b"):
            raise MateError("mate %s: head_on %r: 'a' or 'b'" % (m["name"], head_on))
        hob, href = (oa, m["a"]) if head_on == "a" else (ob_, m["b"])
        other = ob_ if head_on == "a" else oa
    F = place[hob.name] @ local_frame(*_resolve(href))
    z = Vector(F.col[2][:3]).normalized()
    # numbered in a's pattern order (b's when only b has a pattern); the two coincide when both have one
    src = m["a"] if (m["b"] is None or sa["pattern"] or not _conns(ob_)[cb]["pattern"]) else m["b"]
    pts = world_points(src, place[src.split(":")[0]])
    names, lengths = [], []
    for i, p in enumerate(pts):
        nm = fname if len(pts) == 1 else "%s_%d" % (fname, i)
        if other is None:
            into = -z                                            # into the part, head on its face
            at = p + into * sink
        else:
            into = z                                             # from the head part toward the other
            t = depth if depth is not None else _depth_through(hob, p, into, size, head)
            if t is None:
                raise MateError("mate %s: no material of %s behind point %d %s: pass fastener head_depth= (mm from the "
                                "mating face to the head's bearing face)" % (m["name"], hob.name, i, _r(p, 2)))
            at = p - into * (t - sink)
        parts = [hob] + stack + ([other] if other is not None else [])
        features.fastener_joint(nm, size, tuple(at), tuple(into), parts, head=head, sink=sink, joint=body[hob.name],
                                step=m["step"], cuts=cuts, **f)
        names.append(nm)
        lengths.append(asm.PARTS[nm]["length"])
    m["_fst"] = dict(size=size, style=f.get("style", "selftap"), head=head, sink=sink,
                     head_on=None if m["b"] is None else head_on, names=names, lengths=lengths)


def _record(m):
    oa, ca = _resolve(m["a"])
    sa = _conns(oa)[ca]
    r = {"name": m["name"], "kind": m["kind"], "a": m["a"], "b": m["b"], "fit": m["fit"],
         "pattern_a": pattern_str(sa["pattern"]), "hole_a": sa["hole"], "n": len(pattern_points(sa["pattern"])),
         "gap": m["gap"], "rot": m["rot"], "step": m["step"], "note": m["note"]}
    if m["b"] is not None:
        sb = _conns(_resolve(m["b"])[0])[m["b"].split(":", 1)[1]]
        r.update(pattern_b=pattern_str(sb["pattern"]), hole_b=sb["hole"], parent=m.get("_parent"),
                 child=m.get("_child"), origin=_r(m.get("_origin", (0, 0, 0))), z=_r(m.get("_z", (0, 0, 1))))
    if m["kind"] in ("revolute", "prismatic"):
        r.update(joint=m["name"], axis=m.get("_axis"), lo=m["lo"], hi=m["hi"], home=m["home"],
                 continuous=m["continuous"], units="deg" if m["kind"] == "revolute" else "mm")
        if (m.get("_axis") or "+")[0] == "-":
            # asm.joint turns about +X/+Y/+Z, so this PIV's values (set_pose, checks.json poses) are the mate's negated
            r["piv_sign"] = -1
    if m.get("_fst"):
        r["fastener"] = m["_fst"]
    return {k: v for k, v in r.items() if v is not None and v != "" and not (k in ("gap", "rot") and v == 0)}


def connectors_world(ob):
    """{name: {origin, z, x, pattern, hole}} in world at the current pose (for the manifest)."""
    out = {}
    W = ob.matrix_world @ _placement(ob)
    for n, c in _conns(ob).items():
        F = W @ frame_matrix(c["origin"], c["z"], c["x"])
        out[n] = {"origin": _r(F.translation), "z": _r(F.col[2][:3], 4), "x": _r(F.col[0][:3], 4),
                  "pattern": pattern_str(c["pattern"]), "hole": c["hole"]}
        if c.get("note"):
            out[n]["note"] = c["note"]
    return out
