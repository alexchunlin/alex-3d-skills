"""Print features for PLA on Bambu P1S/H2D: screw holes, nut traps, inserts, bosses, slots, horn recesses.

Every feature is placed with the same two arguments a fastener uses:
    at    = point on the surface where the screw head (or nut, or insert) bears, world mm
    into  = unit direction the shank travels, from the head into the material
so `features.screw_hole(at, into, ...)` and `asm.fastener(name, at, into, ...)` take identical
placement, and a reversed screw (attempt 1: FST_motor_* pointed the wrong way, FINDINGS A1-F10)
shows up as a mismatch instead of a silent clash. Features return objects to pass to geom.csg():
`cut` lists go in sub=, `add` lists in add=.

Numbers are from the design brief (pilot 2.5, clearance 3.4, nut 5.7 AF, wall >= 1.6) plus common
PLA practice; change RULES per printer if a test print disagrees. SIZES holds M2 to M5.

fastener_joint() is the one call per screw: it measures the parts along the axis, picks the stock length,
cuts every part and places the screw and its nut or insert. It replaces the screw() wrapper the v2 designer
wrote three times (mm-launch-hw/v2/blender/parts/base.py:64, launcher.py:43, pan_stage.py:19).

snap_hook(), annular_snap(), torsion_snap() and pip_hinge() follow the same pattern for joins without screws: size from
the part's material (cadsnap.py), build the geometry, raise SnapError naming the fix, and write a record ("joins" in
the manifest, cad_joins in the blend) that cadcheck's `snaps` check re-evaluates (reference/snaps.md).
"""
import ast, json, math, os, sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from . import geom

RULES = {
    # metric fasteners (mm)
    "m3_selftap_pilot_d": 2.5,      # self-tapping M3 into PLA (brief)
    "m3_clear_d": 3.4,              # M3 clearance (brief)
    "m3_tap_machine_d": 2.8,        # M3 machine screw cutting its own thread in PLA
    "m3_head_d": 5.5, "m3_head_h": 3.0,     # socket cap
    "m3_pan_head_d": 6.0, "m3_pan_head_h": 2.4,
    "m3_csk_head_d": 6.0,           # 90 deg countersunk
    "m3_nut_af": 5.5, "m3_nut_h": 2.4,
    "nut_trap_af": 5.7,             # brief: 5.7 across flats
    "nut_trap_h_extra": 0.3,
    "m3_insert_hole_d": 4.0, "m3_insert_len": 5.7,   # typical M3 x 5.7 brass heat-set insert, 4.0-4.2 hole
    "counterbore_d": 6.5,           # R1 fix for the feeder-plate screw heads
    # fits (diametral clearance unless noted)
    "fit_press": 0.10, "fit_snug": 0.15, "fit_slide": 0.25, "fit_running": 0.30, "fit_loose": 0.40,
    "fit_journal_radial": 0.20,
    # printability
    "min_wall": 1.6, "max_overhang_deg": 45, "max_bridge": 25.0,
    "layer_h": 0.2, "elephant_foot_chamfer": 0.4,
    "pcb_pocket_clear": 0.4,        # brief: perimeter lip +0.4
    "horn_recess_clear": 0.2,       # brief: recess = disc + 0.2
}

# Per-size fastener table for fastener_joint() and the size= argument of screw_hole / nut_trap (mm).
# Clearance: ISO 273 medium (M2 2.4, M2.5 2.9, M3 3.4, M4 4.5, M5 5.5). Self-tap pilot ~0.83-0.85 d, above the thread's
# minor diameter (M2.5: 2.1 vs 1.95). PLA-tap (a machine screw cutting its own thread) ~0.93 d. Heads: ISO 4762 (cap),
# ISO 7045 (pan), ISO 7046 actual dk (csk); nuts ISO 4032; heat-set inserts are the common CNC Kitchen / Ruthex sizes.
# The M2, M2.5, M4 and M5 holes are table values: confirm them with a test-print coupon before trusting a fit.
# Not here, read from cadcheck (project checks.json first, then cadcheck DEFAULTS; see check_value): stock lengths,
# max_protrusion, and thread engagement (2 d into a printed part, 1.5 d into a tapped purchased one).
# The M3 row is overlaid with the m3_* entries of RULES at lookup (size_rules), so RULES stays the place to tune M3.
SIZES = {
    "M2": dict(d=2.0, pitch=0.4, clear_d=2.4, pilot_d=1.7, tap_d=1.8, cap=(3.8, 2.0), pan=(4.0, 1.6), csk=(3.8, 1.2),
               nut_af=4.0, nut_h=1.6, insert_d=3.2, insert_len=3.0),
    "M2.5": dict(d=2.5, pitch=0.45, clear_d=2.9, pilot_d=2.1, tap_d=2.3, cap=(4.5, 2.5), pan=(5.0, 2.1), csk=(4.7, 1.5),
                 nut_af=5.0, nut_h=2.0, insert_d=3.6, insert_len=4.0),
    # M3 holes, nut and insert: RULES m3_*
    "M3": dict(d=3.0, pitch=0.5, cap=(5.5, 3.0), pan=(6.0, 2.4), csk=(6.0, 1.7)),
    "M4": dict(d=4.0, pitch=0.7, clear_d=4.5, pilot_d=3.3, tap_d=3.7, cap=(7.0, 4.0), pan=(8.0, 3.1), csk=(8.4, 2.7),
               nut_af=7.0, nut_h=3.2, insert_d=5.6, insert_len=8.1),
    "M5": dict(d=5.0, pitch=0.8, clear_d=5.5, pilot_d=4.2, tap_d=4.6, cap=(8.5, 5.0), pan=(9.5, 3.7), csk=(9.3, 2.7),
               nut_af=8.0, nut_h=4.7, insert_d=6.4, insert_len=9.5),
}


def size_rules(size="M3"):
    """One row of SIZES with the derived numbers: counterbore_d (cap head + 1.0, as RULES counterbore_d for M3),
    trap_af (nut + 0.2, the brief's 5.7 for M3), and from cadcheck's rules (check_value): lengths (stock_lengths for d),
    min_engagement (min_engagement_d x d) and tapped_engagement (tapped_engagement_d x d), both replaced by a project's
    fasteners.min_engagement in mm when its checks.json sets one (cadcheck does the same)."""
    if size not in SIZES:
        raise ValueError("size %r: known sizes %s" % (size, sorted(SIZES)))
    s = dict(SIZES[size])
    if size == "M3":
        R = RULES
        s.update(clear_d=R["m3_clear_d"], pilot_d=R["m3_selftap_pilot_d"], tap_d=R["m3_tap_machine_d"],
                 nut_af=R["m3_nut_af"], nut_h=R["m3_nut_h"], trap_af=R["nut_trap_af"], insert_d=R["m3_insert_hole_d"],
                 insert_len=R["m3_insert_len"], counterbore_d=R["counterbore_d"],
                 cap=(R["m3_head_d"], R["m3_head_h"]), pan=(R["m3_pan_head_d"], R["m3_pan_head_h"]),
                 csk=(R["m3_csk_head_d"], s["csk"][1]))
    s.setdefault("counterbore_d", s["cap"][0] + 1.0)
    s.setdefault("trap_af", s["nut_af"] + 0.2)
    key = "%g" % s["d"]
    stock = check_value("fasteners", "stock_lengths") or {}
    s["lengths"] = list(stock.get(key) or check_default("fasteners", "stock_lengths")[key])
    mm = check_value("fasteners", "min_engagement")
    s["min_engagement"] = mm if mm is not None else round(check_value("fasteners", "min_engagement_d") * s["d"], 2)
    s["tapped_engagement"] = mm if mm is not None else round(check_value("fasteners", "tapped_engagement_d") * s["d"], 2)
    return s


LOG = []   # every placed feature, written to the manifest by asm.write_manifest()


def _frame(at, into):
    """4x4 with local +Z = into, origin = at."""
    w = Vector(into).normalized()
    a = Vector((1, 0, 0)) if abs(w.x) < 0.9 else Vector((0, 1, 0))
    u = w.cross(a).normalized()
    v = w.cross(u).normalized()
    return geom.frame(Vector(at), u, v, w)


def _place(ob, at, into):
    return geom.xform(ob, _frame(at, into))


def _log(feature, at, into, **dims):
    LOG.append({"feature": feature, "at": [round(c, 3) for c in at], "into": [round(c, 4) for c in Vector(into).normalized()], **dims})


def _hole(name, d, z0, z1, print_up=None, into=None):
    """Round hole along local Z, or a teardrop when the axis lies within 60 deg of horizontal in print."""
    if print_up is not None and into is not None and abs(Vector(into).normalized().dot(Vector(print_up).normalized())) < 0.5:
        # express print_up in the feature's local (u, v) plane
        F = _frame((0, 0, 0), into).to_3x3()
        up = F.inverted() @ Vector(print_up)
        prof = geom.teardrop((0, 0), d / 2, (up.x, up.y))
        return geom.prism(name, prof, z0, z1, 'Z')
    return geom.cyl(name, (0, 0), d / 2, z0, z1, 'Z')


def screw_hole(at, into, length, kind="selftap", head="cap", sink=0.0, clamp=0.0, print_up=None, name="hole", size="M3",
               tip=1.0):
    """Cutters for a `size` screw (default M3) whose head bears at `at` and whose shank runs `length` along `into`.

    kind:  "selftap"  pilot (M3 Ø2.5) all the way (the screw cuts its thread in this part)
           "clearance" clearance (M3 Ø3.4) all the way (the part being clamped)
           "clamp"    clearance for the first `clamp` mm (the clamped part), pilot beyond (the host)
           "tap"      clearance for `clamp` mm, then the PLA-tap hole (a machine screw cutting its own thread)
           "insert"   clearance for `clamp` mm, then a heat-set insert pocket, then clearance to the tip
    head:  "cap" | "pan" | "csk" | "none".
    sink:  the bearing face `at` lies this far below the part's outer surface: a counterbore
           (cap/pan) is cut from `at` back out by sink + 0.6 mm. For "csk", `at` is the outer
           surface and the countersink cone is cut there.
    print_up: world direction of print +Z for this part; holes with a horizontal axis become
           teardrops (no support inside the hole).
    tip:   how far the pilot / tap / insert-relief hole runs past the screw's tip.
    """
    S = size_rules(size)
    cuts = []
    over = 0.6  # extend cutters past the faces so booleans never leave skins
    if kind == "selftap":
        cuts.append(_hole(name + "_pilot", S["pilot_d"], -over, length + tip, print_up, into))
    elif kind == "clearance":
        cuts.append(_hole(name + "_clr", S["clear_d"], -over, length + over, print_up, into))
    elif kind in ("clamp", "tap"):
        cuts.append(_hole(name + "_clr", S["clear_d"], -over, clamp + 0.01, print_up, into))
        d = S["pilot_d"] if kind == "clamp" else S["tap_d"]
        cuts.append(_hole(name + "_pilot", d, clamp - 0.01, length + tip, print_up, into))
    elif kind == "insert":
        cuts.append(_hole(name + "_clr", S["clear_d"], -over, clamp + 0.01, print_up, into))
        z1 = clamp + S["insert_len"] + 0.5
        cuts.append(_hole(name + "_ins", S["insert_d"], clamp - 0.01, z1, print_up, into))
        if length + tip > z1:   # a screw longer than the insert needs room past it
            cuts.append(_hole(name + "_tip", S["clear_d"], z1 - 0.01, length + tip, print_up, into))
    else:
        raise ValueError(kind)
    if sink > 0 and head in ("cap", "pan"):
        d = S["counterbore_d"] if head == "cap" else S["pan"][0] + 0.6
        cuts.append(geom.cyl(name + "_cb", (0, 0), d / 2, -sink - over, 0.01, 'Z'))
    elif head == "csk":
        r = S["csk"][0] / 2 + 0.2
        cuts.append(geom.cone(name + "_csk", (0, 0), r + over, S["clear_d"] / 2, -over, r + over - S["clear_d"] / 2 - over, 'Z'))
    for c in cuts:
        _place(c, at, into)
    _log("screw_hole", at, into, length=length, kind=kind, head=head, sink=sink, clamp=clamp, size=size)
    return cuts


def nut_trap(at, into, depth=None, af=None, rot_deg=0.0, slot_dir=None, slot_len=0.0, name="nut", size="M3"):
    """Hex pocket for a `size` nut (default M3) whose bearing face is at `at`, pocket going `into`.
    slot_dir (world vector, perpendicular to into) adds a side-entry slot for captive nuts."""
    S = size_rules(size)
    af = af or S["trap_af"]
    depth = depth or S["nut_h"] + RULES["nut_trap_h_extra"]
    pk = geom.prism(name + "_hex", geom.hexagon((0, 0), af, math.radians(rot_deg)), -0.01, depth, 'Z')
    cuts = [pk]
    if slot_dir is not None and slot_len > 0:
        F = _frame((0, 0, 0), into).to_3x3()
        s = (F.inverted() @ Vector(slot_dir)).normalized()
        ang = math.atan2(s.y, s.x)
        L = slot_len
        pts = [(-0.0, -af / 2), (L, -af / 2), (L, af / 2), (0.0, af / 2)]
        pts = [(x * math.cos(ang) - y * math.sin(ang), x * math.sin(ang) + y * math.cos(ang)) for x, y in pts]
        cuts.append(geom.prism(name + "_slot", pts, -0.01, depth, 'Z'))
    for c in cuts:
        _place(c, at, into)
    _log("nut_trap", at, into, af=af, depth=depth, slot=bool(slot_dir))
    return cuts


def boss(at, into, od, height, name="boss"):
    """Solid cylinder grown from `at` *against* `into` (toward the screw head side) by `height`.
    Union it, then cut the screw_hole through it."""
    b = geom.cyl(name, (0, 0), od / 2, -height, 0.01, 'Z')
    _place(b, at, into)
    _log("boss", at, into, od=od, height=height)
    return [b]


def drill_to_fit_boss(at, into, od=7.0, height=6.0, dimple_d=1.2, dimple_depth=0.6, name="dtf"):
    """Solid boss with only a centre-punch dimple (brief: servo controller holes unconfirmed).
    Returns (add, cut)."""
    add = boss(at, into, od, height, name)
    cut = [_place(geom.cone(name + "_dimple", (0, 0), dimple_d / 2, 0.05, -0.01, dimple_depth, 'Z'), at, into)]
    _log("drill_to_fit_boss", at, into, od=od, height=height)
    return add, cut


def slot(at, into, along, length, width=None, depth=10.0, name="slot"):
    """Stadium slot (adjustment) centred at `at`, long axis `along`, cut `depth` along `into`."""
    width = width or RULES["m3_clear_d"]
    F = _frame((0, 0, 0), into).to_3x3()
    s = (F.inverted() @ Vector(along)).normalized()
    ang = math.atan2(s.y, s.x)
    h = length / 2
    prof = geom.hull_circles([((h * math.cos(ang), h * math.sin(ang)), width / 2), ((-h * math.cos(ang), -h * math.sin(ang)), width / 2)])
    c = geom.prism(name, prof, -0.6, depth, 'Z')
    _place(c, at, into)
    _log("slot", at, into, length=length, width=width)
    return [c]


def horn_recess(at, into, disc_d=20.0, depth=1.0, bolt_circle_d=14.0, n_holes=8, dimple_d=1.0, centre_hole_d=6.5, name="horn"):
    """Servo horn interface (brief): 1.0 mm recess at disc + 0.2, pilot dimples on the bolt circle,
    and a centre through-hole so the horn's centre screw can be driven after assembly (R1 item 4)."""
    cuts = [geom.cyl(name + "_rec", (0, 0), (disc_d + RULES["horn_recess_clear"]) / 2, -0.6, depth, 'Z')]
    for k in range(n_holes):
        a = 2 * math.pi * k / n_holes
        c = (bolt_circle_d / 2 * math.cos(a), bolt_circle_d / 2 * math.sin(a))
        cuts.append(geom.cone(name + "_dim%d" % k, c, dimple_d / 2, 0.05, depth - 0.01, depth + 0.6, 'Z'))
    if centre_hole_d:
        cuts.append(geom.cyl(name + "_ctr", (0, 0), centre_hole_d / 2, -0.6, 200.0, 'Z'))
    for c in cuts:
        _place(c, at, into)
    _log("horn_recess", at, into, disc_d=disc_d, depth=depth, bolt_circle_d=bolt_circle_d)
    return cuts


def pcb_pocket(at, into, w, h, depth, clear=None, corner_r=1.0, name="pcb"):
    """Locating pocket for a board w x h (local u, v), `clear` added all round (brief: +0.4)."""
    clear = RULES["pcb_pocket_clear"] if clear is None else clear
    W, H = w / 2 + clear, h / 2 + clear
    c = geom.prism(name, geom.rrect(-W, W, -H, H, corner_r), -0.6, depth, 'Z')
    _place(c, at, into)
    _log("pcb_pocket", at, into, w=w, h=h, depth=depth, clear=clear)
    return [c]


def bore(name, c, r_shaft, w0, w1, axis='X', fit="running"):
    """Cutter for a bore that runs on a printed shaft/journal of radius r_shaft (profile centre c in the
    axis's (u, v) plane). Declare the pair under "fits" in the check config with min_clearance."""
    rad = RULES["fit_journal_radial"] if fit == "running" else RULES["fit_" + fit] / 2
    return geom.cyl(name, c, r_shaft + rad, w0, w1, axis)


# ------------------------------------------------------------------ fastened joints

class FastenerError(ValueError):
    """fastener_joint could not make a joint that meets the rules; the message says what to change."""


TOL = 0.01   # mm: ray-measured stacks carry float noise; a 16.004 mm minimum still takes the 16 mm screw
SEAT_TOL = 0.2   # mm of material above the bearing face that still seats a head (cadcheck probes 0.25 behind it)
GAP_TOL = 0.3    # mm of air between clamped parts on the axis before it is called a gap

_CHECK_DEFAULTS = {}
_PROJECT = {"path": None, "set": False, "cache": {}}


def check_default(section, key):
    """A value from cadcheck.py DEFAULTS, read from its source (cadcheck runs on import), so the joint rules and the
    check that judges them cannot drift apart."""
    if not _CHECK_DEFAULTS:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cadcheck.py")) as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DEFAULTS":
                _CHECK_DEFAULTS.update(ast.literal_eval(node.value))
    return _CHECK_DEFAULTS[section].get(key)


def use_checks(path):
    """Read fastener rules from this checks.json (None: no project file). Without a call, the project file is
    $CAD_CHECKS, else the checks.json beside the build script (`cad build blender/build_assembly.py` reads
    blender/checks.json, the file `cad check` is given)."""
    _PROJECT.update(path=path, set=True)


def project_checks_path():
    if _PROJECT["set"]:
        return _PROJECT["path"]
    if os.environ.get("CAD_CHECKS"):
        return os.environ["CAD_CHECKS"]
    if "--python" in sys.argv[:-1]:
        p = os.path.join(os.path.dirname(os.path.abspath(sys.argv[sys.argv.index("--python") + 1])), "checks.json")
        return p if os.path.isfile(p) else None
    return None


def check_value(section, key):
    """cadcheck's value for section.key: the project checks.json's when it sets one (cadcheck merges a project section
    over DEFAULTS key by key), else DEFAULTS. None when neither has it."""
    p = project_checks_path()
    if p:
        if p not in _PROJECT["cache"]:
            with open(p) as f:
                _PROJECT["cache"][p] = json.load(f)
        sec = _PROJECT["cache"][p].get(section)
        if isinstance(sec, dict) and key in sec:
            return sec[key]
    return check_default(section, key)


def _bvh(ob):
    M = ob.matrix_world
    vs = [M @ x.co for x in ob.data.vertices]
    return BVHTree.FromPolygons(vs, [tuple(f.vertices) for f in ob.data.polygons]), vs


def _spans(tree, p, w, reach):
    """Material stretches [(t0, t1)] along the line through p along w, t in mm from p."""
    o, hits, t = p - w * reach, [], 0.0
    while t < 2 * reach:
        loc, nrm, _, dist = tree.ray_cast(o + w * t, w, 2 * reach - t)
        if loc is None:
            break
        th, sgn = t + dist - reach, (1 if nrm.dot(w) < 0 else -1)     # +1 entering material, -1 leaving
        if not hits or abs(hits[-1][0] - th) > 1e-3 or hits[-1][1] != sgn:
            hits.append((th, sgn))
        t += dist + 1e-4
    out, depth, t0 = [], 0, None
    for th, sgn in hits:
        depth = max(0, depth + sgn)
        if sgn > 0 and depth == 1:
            t0 = th
        elif sgn < 0 and depth == 0 and t0 is not None:
            out.append((t0, th))
            t0 = None
    return out


def _ahead(spans, eps):
    """The first stretch that ends ahead of `at` (it may start behind it: a buried head)."""
    return next(((a, b) for a, b in spans if b > eps), None)


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if len(xs) % 2 else 0.5 * (xs[len(xs) // 2 - 1] + xs[len(xs) // 2])


def _survey(at, into, parts, shank_r, head_r, n=8, eps=0.05):
    """Per part: the first stretch ahead of `at` on the axis, and on n rays each on a ring at shank_r and at head_r.
    The axis line is offset 0.01 mm and the rings start off the 0 deg direction, so no ray runs down a mesh edge."""
    w = Vector(into).normalized()
    F3 = _frame((0, 0, 0), w).to_3x3()
    u, v = F3.col[0], F3.col[1]
    p = Vector(at) + u * 0.0137 + v * 0.0091
    ring = lambda r: [p + (u * math.cos(a) + v * math.sin(a)) * r
                      for a in (2 * math.pi * (k + 0.37) / n for k in range(n))]
    out = {}
    for ob in parts:
        tree, vs = _bvh(ob)
        reach = max((x - p).length for x in vs) + head_r + 1.0
        out[ob.name] = {"ob": ob, "axis": _ahead(_spans(tree, p, w, reach), eps),
                        "shank": [_ahead(_spans(tree, q, w, reach), eps) for q in ring(shank_r)] if shank_r else [],
                        "head": [_ahead(_spans(tree, q, w, reach), eps) for q in ring(head_r)] if head_r else []}
    return out


def _classify(sv):
    """(t_in, t_out, kind) of one part from its survey: "solid" (material on the axis), "pilot" (a hole smaller than
    the shank: material at 0.92 x shank radius), "clear" (a hole the shank passes: material only at the head ring),
    or (None, None, None)."""
    if sv["axis"]:
        return sv["axis"][0], sv["axis"][1], "solid"
    for ring, kind in (("shank", "pilot"), ("head", "clear")):
        got = [x for x in sv[ring] if x]
        if got and len(got) * 2 >= len(sv[ring]):
            return _median([a for a, b in got]), _median([b for a, b in got]), kind
    return None, None, None


def axis_stack(at, into, parts, eps=0.05, shank_r=None, head_r=None, n=8):
    """[(object, t_in, t_out, kind)]: each part's first stretch of material along the screw axis through `at` along
    `into` that ends ahead of `at` (t in mm from `at`, negative behind it), sorted by t_in. kind is "solid" when the
    axis itself is in material; with shank_r / head_r, a part already holed on the axis is found by rays on those
    rings ("pilot": hole smaller than the shank, "clear": the shank passes). A part with no material ahead comes back
    as (object, None, None, None) at the end."""
    sv = _survey(at, into, parts, shank_r, head_r, n, eps)
    rows = [(x["ob"],) + _classify(x) for x in sv.values()]
    return sorted([r for r in rows if r[1] is not None], key=lambda r: r[1]) + [r for r in rows if r[1] is None]


def _purchased(ob):
    return ob.name.startswith("BUY_") or any(c.name == "Purchased" for c in ob.users_collection)


def _r(v):
    return [round(c, 2) for c in v]


def _used_lengths(spec):
    """{length: count} of screws of this spec already placed in this build (asm.PARTS), for length reuse."""
    from . import asm
    out = {}
    for info in asm.PARTS.values():
        if info.get("spec") == spec and info.get("length") is not None:
            out[float(info["length"])] = out.get(float(info["length"]), 0) + 1
    return out


def fastener_joint(name, size, at, into, parts, style="selftap", head="cap", sink=0.0, length=None,
                   min_engagement=None, depth=None, trap=True, nut_rot_deg=0.0, print_up=None,
                   joint=None, host=None, step=None, strict=True, cuts=None, lengths=None,
                   through_ok=False, gap_ok=False):
    """One fastened joint: measure the stack, pick the length, cut every part, place the screw (and nut or insert).
    Use it when a screw is the right join (a load path, service access, a metal part); snaps, pins and tabs are not.

    at, into: as screw_hole / asm.fastener. `at` is the head's bearing face (for head="csk", the outer surface the
              head sits flush with); `into` is the direction the shank travels.
    size:     "M2", "M2.5", "M3", "M4" or "M5" (SIZES). Changing the size is this one argument.
    parts:    the solids the screw passes, in any order. The stack is measured along the axis (and on rings at the
              shank and head radius): every part but the last one met is clamped (clearance hole); the last one holds
              the thread. A part already holed on the axis (a purchased board, a servo ear, a part cut earlier) is a
              pre-drilled layer: counted in the grip and seating the head, not cut. Name the solids with their final
              PRT_/BUY_ names: the cutters come back under those names.
    style:    "selftap"  pilot in the last part (printed); thread >= min_engagement (2 d) into it
              "nut"      through-bolt; nut in a hex trap at the far face of the last part (trap=False: the nut
                         bears on that face). The bolt passes the nut by at least one pitch.
              "insert"   heat-set insert pocket in the last part (printed); the screw runs through the whole insert
              "tapped"   machine screw into a tapped purchased part (no cut in it; thread >= tapped_engagement, 1.5 d,
                         and <= depth, the datasheet depth of its tapped hole). A printed last part gets the PLA-tap
                         hole and the 2 d rule.
    head:     "cap" | "pan" | "csk". sink > 0 counterbores the head (cap/pan): `at` is then up to sink below the
              surface; on a sloped face that is a spot-face.
    length:   None picks a stock length in the rule's window: one this build already uses for the same spec if one
              fits (fewer screw types), else the shortest. Stock is `lengths=`, else the project checks.json's
              fasteners.stock_lengths, else cadcheck's DEFAULTS. The tip stays within fasteners.max_protrusion of the
              last material (the nut counts). A given length is checked against the same rule; strict=False keeps one
              that breaks it (rule_ok False).
    min_engagement: mm of thread, replacing the 2 d / 1.5 d rule (cadcheck's fasteners.min_engagement_d and
              tapped_engagement_d, or the project's fasteners.min_engagement in mm).
    through_ok: selftap / insert / PLA-tap holes are blind by default: the screw stops min_wall + 1 mm short of the
              host's far face. True lets the hole break through it instead.
    gap_ok:   True accepts air (> 0.3 mm) between clamped parts on the axis (a deliberate stand-off).
    print_up: world print +Z, or {part name: print +Z}, for teardrop holes in parts printed on their side.
    joint, host, step: as asm.fastener (host defaults to the last part's name).
    cuts:     a dict to extend, so several joints accumulate and each part gets one csg.

    Returns cuts: {part name: [cutters]}, for geom.csg(part, sub=cuts[part.name]); a part may get an empty list.
    The record (stack, grip, length, engagement, rule) goes to the manifest under the screw's "fastener_joint".
    Raises FastenerError when the joint cannot meet the rules: no part ahead of `at` (a reversed screw, FINDINGS
    A1-F10), a head inside or off the first part or on a sloped seat, an air gap in the stack, a self-tap or insert
    into a purchased part, too little thread (A3-F5), a blind hole too shallow for any stock length, a countersink
    deeper than the plate allows, or a given length that stops short of its nut (A2-F3).
    """
    from . import asm      # asm imports features
    S = size_rules(size)
    if style not in ("selftap", "nut", "insert", "tapped"):
        raise ValueError("style %r: selftap, nut, insert or tapped" % style)
    if head not in ("cap", "pan", "csk"):
        raise ValueError("head %r: cap, pan or csk" % head)
    w, at = Vector(into).normalized(), Vector(at)
    maxp = check_value("fasteners", "max_protrusion")
    wall = RULES["min_wall"]
    head_r = S[head][0] / 2
    sv = _survey(at, w, parts, 0.92 * S["d"] / 2, 0.8 * head_r)
    rows = [(x["ob"],) + _classify(x) for x in sv.values()]
    st = sorted([r for r in rows if r[1] is not None], key=lambda r: r[1])
    lost = [r[0].name for r in rows if r[1] is None]
    if not st:
        raise FastenerError("%s: none of %s has material ahead of at=%s along into=%s, so the parts are behind the "
                            "head: flip `into` (it points from the head into the material)" % (
                                name, [o.name for o in parts], _r(at), _r(w)))
    if lost:
        raise FastenerError("%s: %s not on the axis ahead of at=%s along into=%s, nor within the head (stack found: "
                            "%s)" % (name, lost, _r(at), _r(w), [(o.name, round(a, 2), round(b, 2)) for o, a, b, k in st]))
    stack = lambda: [(o.name, round(a, 2) + 0.0, round(b, 2) + 0.0) + (() if k == "solid" else (k,)) for o, a, b, k in st]
    # head seat: on the axis and at 0.8 x head radius, as cadcheck's head-buried probe (0.25 mm behind the face)
    first, (last, t_in, t_out, lkind) = st[0], st[-1]
    spot = sink > 0 and head != "csk"
    lo_seat = -sink - 0.5 if spot else -SEAT_TOL         # a counterbore clears back to sink + 0.6
    if first[1] < lo_seat:
        raise FastenerError("%s: the head would sit %.2f mm inside %s; `at` is the bearing face: move it, flip "
                            "`into`, or pass sink=%.2f for a counterbore" % (
                                name, (-sink if spot else 0.0) - first[1], first[0].name, -first[1]))
    if first[1] > 0.3:
        raise FastenerError("%s: the head stands %.2f mm off %s; `at` is the bearing face%s" % (
            name, first[1], first[0].name, " (sink=%g puts it %g below the surface)" % (sink, sink) if sink else ""))
    seat = []
    for k in range(len(sv[first[0].name]["head"])):
        es = [x["head"][k][0] for x in sv.values() if x["head"][k]]
        seat.append(min(es) if es else None)
    es = [e for e in seat if e is not None]
    if es and min(es) < lo_seat:
        rise, low = -min(es), max(es)
        raise FastenerError(
            "%s: the head seat is not flat: at 0.8 x head radius (%.2f mm) the material runs from %.2f mm above to "
            "%.2f mm %s the bearing face (a sloped face, or `into` not normal to it), so cadcheck would fail 'head "
            "buried'. Spot-face it: move `at` %.2f mm along `into` and pass sink=%.1f, or make the face normal to the "
            "axis" % (name, 0.8 * head_r, rise, abs(low), "below" if low >= 0 else "above", max(0.0, low),
                      math.ceil((max(0.0, low) - min(es)) * 10 + 2) / 10.0))
    # gaps: the clamp pulls the stack together, so air on the axis bends a part or leaves the joint loose
    for (a, _, a1, _k), (b, b0, _, _k2) in zip(st, st[1:]):
        if b0 - a1 > GAP_TOL and not gap_ok:
            raise FastenerError("%s: %.2f mm of air between %s and %s on this axis (%s): close the gap, or pass "
                                "gap_ok=True for a deliberate stand-off" % (name, b0 - a1, a.name, b.name, stack()))
    buy = _purchased(last)
    # what the last part can hold
    if buy and style in ("selftap", "insert"):
        raise FastenerError("%s: style=%r into purchased part %s: a self-tap or heat-set insert needs a printed host. "
                            "Use style='tapped' (machine screw into its tapped hole, depth=) or style='nut'" % (
                                name, style, last.name))
    if buy and style == "nut" and trap:
        raise FastenerError("%s: a nut trap cannot be cut in purchased part %s; pass trap=False (nut on its far face)"
                            % (name, last.name))
    if lkind == "clear" and not (style == "nut" or (style == "tapped" and buy)):
        raise FastenerError("%s: %s has a hole the %s shank passes on this axis (material only at the head ring): "
                            "nothing for a %s thread to grip. Use style='nut', or a part without the hole" % (
                                name, last.name, size, style))
    for o, a, b, k in st[:-1]:
        if k == "pilot" and _purchased(o):
            raise FastenerError("%s: clamped part %s has a hole smaller than the %s shank on this axis: the screw would "
                                "thread into it instead of clamping it" % (name, o.name, size))
    if head == "csk" and first[3] == "solid":
        cone, thick = S["csk"][0] / 2 + 0.2 - S["clear_d"] / 2, first[2] - first[1]
        if cone > thick - wall + TOL:
            raise FastenerError("%s: the %s countersink is %.2f mm deep but %s is %.2f mm thick here, leaving %.2f mm "
                                "under it (min_wall %.1f): a knife edge. Use head='cap' or 'pan', or a plate >= %.2f" % (
                                    name, size, cone, first[0].name, thick, thick - cone, wall, cone + wall))
    rec = {"size": size, "style": style, "head": head, "stack": [list(x) for x in stack()]}
    nf = nf_lo = nf_hi = None                       # nut bearing face, mm from `at`
    blind = style in ("selftap", "insert") or (style == "tapped" and not buy)
    cap_why = "the protrusion limit (tip <= %.1f mm past the last material)" % maxp
    if style in ("selftap", "tapped"):
        need = S["tapped_engagement"] if (style == "tapped" and buy) else S["min_engagement"]
        need = need if min_engagement is None else min_engagement
        if t_in + need > t_out + TOL:
            raise FastenerError("%s: %s gives only %.1f mm of thread on this axis; %s %s needs %.1f. Add a boss, use "
                                "style='nut' or 'insert', or pass min_engagement=" % (
                                    name, last.name, t_out - t_in, size, style, need))
        lo, hi = t_in + need, t_out + maxp
        if style == "tapped" and depth:
            hi, cap_why = min(hi, t_in + depth), "the tapped hole's depth (%g mm)" % depth
        rule = "thread >= %.1f mm in %s" % (need, last.name)
        lo_why = "%.1f mm of thread" % need
    elif style == "insert":
        if t_in + S["insert_len"] + 0.5 > t_out + TOL:
            raise FastenerError("%s: %s is %.1f mm thick on this axis; a %s insert pocket needs %.1f" % (
                name, last.name, t_out - t_in, size, S["insert_len"] + 0.5))
        # cadcheck pairs the screw with the insert proxy (a nut), so a tip out of the part counts from the insert's end
        lo, hi = t_in + S["insert_len"], max(t_out, min(t_out, t_in + S["insert_len"]) + maxp)
        rule = "screw through the %.1f mm insert" % S["insert_len"]
        lo_why = "through the insert"
    else:
        pocket = S["nut_h"] + RULES["nut_trap_h_extra"]
        nf_hi, nf_lo = (t_out - pocket, t_in + wall) if trap else (t_out, t_out)
        if nf_hi < nf_lo - TOL:
            raise FastenerError("%s: %s is %.1f mm thick on this axis, too thin for a %s nut trap (needs %.1f); use "
                                "trap=False (nut on its far face)" % (
                                    name, last.name, t_out - t_in, size, pocket + wall))
        nf = nf_hi
        lo, hi = nf + S["nut_h"] + S["pitch"], nf + S["nut_h"] + maxp
        rule = "bolt passes the nut by %.2f to %.1f mm" % (S["pitch"], maxp)
        lo_why = "past the nut"
    if blind and not through_ok and t_out - wall - 1.0 < hi:
        hi, cap_why = t_out - wall - 1.0, "a blind hole (1 mm of pilot past the tip, then min_wall %.1f to the far face)" % wall
    ok = True
    stock = [float(x) for x in (lengths if lengths is not None else S["lengths"])]
    spec = "%s_%s" % (size, head)
    if length is None:
        fit = [l for l in stock if lo - TOL <= l <= hi + TOL]
        if not fit and style == "nut" and trap:
            # no stock length with the nut at the far face: sink the trap deeper, as little as needed
            deeper = [l for l in stock if nf_lo + S["nut_h"] + S["pitch"] - TOL <= l < lo - TOL]
            if deeper:
                fit = [max(deeper)]
                nf = max(nf_lo, fit[0] - S["nut_h"] - min(2 * S["pitch"], maxp))
                lo, hi = nf + S["nut_h"] + S["pitch"], nf + S["nut_h"] + maxp
                rec["trap_deepened_mm"] = round(nf_hi - nf, 2)
        if not fit:
            if lo > hi + TOL:
                fix = ("deepen it by %.1f mm, use style='nut', or pass through_ok=True to let the hole break through"
                       % (lo - hi) if cap_why.startswith("a blind") else "change the stack")
                raise FastenerError("%s: %s is too shallow on this axis: %s needs a screw >= %.2f mm, but %s allows "
                                    "<= %.2f. %s" % (name, last.name, lo_why, lo, cap_why, hi, fix[0].upper() + fix[1:]))
            raise FastenerError("%s: no stock %s length between %.2f and %.2f mm (%s; %s). Stock: %s. Change the "
                                "stack, pass lengths=, or pass length= with strict=False" % (
                                    name, size, lo, hi, rule, cap_why, [("%g" % x) for x in stock]))
        used = _used_lengths(spec)
        reuse = [l for l in fit if used.get(l)]
        L = max(reuse, key=lambda l: (used[l], -l)) if reuse else min(fit)
        rec["length_reused"] = bool(reuse)
    else:
        L = float(length)
        if not lo - TOL <= L <= hi + TOL:
            msg = "%s: length %g breaks the rule (%s; %s): needs %.2f to %.2f mm" % (name, L, rule, cap_why, lo, hi)
            if nf is not None and L < nf:
                msg += "; it stops %.2f mm short of its nut" % (nf - L)
            if strict:
                raise FastenerError(msg + "; leave length=None to pick one")
            ok, rec["rule_note"] = False, msg
    if nf is not None:
        eng, prot = L - nf, L - nf - S["nut_h"]
    elif style == "insert":
        eng, prot = min(L - t_in, S["insert_len"]), max(0.0, L - t_out)
    else:
        eng, prot = min(L, t_out) - t_in, max(0.0, L - t_out)
    rec.update(length=L, grip_mm=round(nf if nf is not None else t_in, 2), engagement_mm=round(eng, 2),
               protrusion_mm=round(prot, 2), window_mm=[round(lo, 2), round(hi, 2)], rule=rule, rule_ok=ok,
               blind=blind and not through_ok, holes={k: S[k] for k in ("clear_d", "pilot_d", "tap_d", "trap_af", "insert_d")})
    # cutters per part; head cuts go to every part (a countersink deeper than the first part cuts the next). A clamped
    # part whose hole the shank already passes (kind "clear") is not cut, nor is a tapped purchased part. A solid
    # purchased placeholder that is clamped gets its clearance hole, as before (apply it to model the real hole).
    cuts = {} if cuts is None else cuts
    clamp = max(0.0, t_in)
    tip = 1.0
    if 0 < t_out - (L + tip) < wall:
        # through_ok, or a given length: a blind hole would leave a skin too thin to print under the tip
        tip = t_out - wall - L if t_out - wall >= L + 0.5 else t_out - L + 0.6
    for i, (ob, a, b, kind) in enumerate(st):
        up = print_up.get(ob.name) if isinstance(print_up, dict) else print_up
        kw = dict(head=head, sink=sink, print_up=up, name="%s_%d" % (name, i), size=size, tip=tip)
        lst = cuts.setdefault(ob.name, [])
        if kind == "clear" and ob is not last:
            continue
        if ob is not last:
            lst += screw_hole(at, w, L, "clearance", **kw)
        elif style == "selftap":
            lst += screw_hole(at, w, L, "clamp", clamp=clamp, **kw)
        elif style == "tapped":
            lst += [] if buy else screw_hole(at, w, L, "tap", clamp=clamp, **kw)
        elif style == "insert":
            lst += screw_hole(at, w, L, "insert", clamp=clamp, **kw)
        else:
            if kind != "clear":
                lst += screw_hole(at, w, L, "clearance", **kw)
            if trap:
                lst += nut_trap(at + w * nf, w, depth=t_out - nf + 0.6, rot_deg=nut_rot_deg, name=kw["name"] + "_nut", size=size)
    # hardware on the same at/into
    asm.fastener(name, at, w, L, spec=spec, joint=joint, host=host or last.name, step=step)
    if nf is not None:
        asm.nut(name + "_nut", at + w * nf, w, joint=joint, step=step, size=size)
    elif style == "insert":
        # proxy just inside the pocket, tagged as a nut so cadcheck checks the screw runs through it
        af = (S["insert_d"] / 2 - 0.15) * 2 * math.cos(math.pi / 6)
        asm.nut(name + "_insert", at + w * t_in, w, joint=joint, af=af, h=S["insert_len"], step=step, size=size,
                label="%s heat-set insert" % size)
    asm.PARTS[name]["fastener_joint"] = rec
    _log("fastener_joint", at, w, name=name, **rec)
    return cuts


def fastener_summary(parts):
    """{"screws": n, "distinct": k, "by_spec_length": {"M3_cap x 12": count}} over every screw in asm.PARTS."""
    by = {}
    for info in parts.values():
        if info.get("spec") and info.get("length") is not None:
            k = "%s x %g" % (info["spec"], float(info["length"]))
            by[k] = by.get(k, 0) + 1
    return {"screws": sum(by.values()), "distinct": len(by), "by_spec_length": dict(sorted(by.items()))}


# ------------------------------------------------------------------ snap fits and print-in-place hinges

class SnapError(ValueError):
    """A snap or print-in-place joint that cannot meet its rules; the message names what to change."""


JOINS = []   # snap and print-in-place records: the manifest's "joins", and the scene's cad_joins (cadcheck reads them)


def _cadsnap():
    try:
        import cadsnap
    except ImportError:      # scripts/ is usually on sys.path; asm puts it there too
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import cadsnap
    return cadsnap


def _inside(ob, p, w=(0.0123, 0.0071, 1.0), reach=500.0):
    """Is world point p in ob's material (ray parity along w)?"""
    return any(a - 1e-6 <= 0.0 <= b + 1e-6 for a, b in _spans(_bvh(ob)[0], Vector(p), Vector(w).normalized(), reach))


def _material(part, material):
    """(material, where it came from): the argument, the part's asm.part(material=) if it is registered, else the
    slicer default. cadcheck re-checks every record against the part as built, so a default here is not final."""
    from . import asm
    S = _cadsnap()
    if material:
        if material not in S.CM.MATERIALS:
            raise SnapError("material %r is not in cadmat.MATERIALS (%s)" % (material, ", ".join(S.CM.MATERIALS)))
        return material, "argument"
    m = asm.PARTS.get(part.name, {}).get("material")
    if m:
        return m, "asm.part"
    return S.CM.PRINT_DEFAULTS["material"], "default (%s not registered yet; cadcheck re-checks the built part)" % part.name


def _across(beam_dir, kind, print_up):
    """(crosses layers?, angle to the bed) for world print +Z print_up, or (False, None) when it isn't given."""
    if print_up is None:
        return kind == "torsion", None
    up = Vector(print_up).normalized()
    ang = math.degrees(math.asin(min(1.0, abs(Vector(beam_dir).normalized().dot(up)))))
    return _cadsnap().layer_stress_dir(kind, ang), ang


def _join(rec):
    import bpy
    rec = json.loads(json.dumps(rec))
    JOINS.append(rec)
    LOG.append(dict({"feature": rec["kind"]}, **{k: v for k, v in rec.items() if k != "kind"}))
    bpy.context.scene["cad_joins"] = json.dumps(JOINS)    # in the .blend too, so cadcheck reads a copied blend
    return rec


def _ops(ops, *names):
    ops = {} if ops is None else ops
    for n in names:
        ops.setdefault(n, {"add": [], "sub": []})
    return ops


def _fwd(along, out, name):
    if Vector(along).length < 1e-9 or Vector(out).length < 1e-9:
        raise SnapError("%s: along %r and out %r need a direction" % (name, along, out))
    u, v = Vector(along).normalized(), Vector(out).normalized()
    if abs(u.dot(v)) > 1e-3:
        raise SnapError("%s: along %s and out %s must be perpendicular" % (name, _r(u), _r(v)))
    return u, v, u.cross(v).normalized()


def _barb(l, f, yb, entry_deg, retain_deg, tf):
    """Barb above the face t = f, (s, t) points counter-clockwise, retaining face at s = l; and its tip s."""
    s1 = l + (yb / math.tan(math.radians(retain_deg)) if retain_deg < 89.999 else 0.0)
    s2 = s1 + tf
    s3 = s2 + yb / math.tan(math.radians(entry_deg))
    return [(s3, f), (s2, f + yb), (s1, f + yb), (l, f)], s3


def _catch_cutters(name, barb, s3, f, back, y, half_w, c, M):
    """The catch's cut: a channel the arm runs in (room behind it to deflect by y) and the barb's pocket, both c clear.
    The ledge left between them is what the barb holds on."""
    ch = geom.box(name + "_ch", 0.0, s3 + c, back - y - c, f + c, -half_w - c, half_w + c)
    pk = geom.prism(name + "_pk", geom.offset_convex(barb, c), -half_w - c, half_w + c, 'Z')
    return [geom.xform(ch, M), geom.xform(pk, M)]


def _check_in(name, entry_deg=30.0, retain_deg=90.0, **vals):
    """SnapError for a size that isn't a positive number (None: not given) or a face angle outside its range, before
    anything divides by it (PR #22 review: undercut=0, length=0, hub_od <= d crashed with ZeroDivisionError)."""
    for k, v in vals.items():
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not v > 0 or not math.isfinite(v)):
            raise SnapError("%s: %s=%r must be a positive number (mm)" % (name, k, v))
    if not 0 < entry_deg < 90:
        raise SnapError("%s: entry_deg=%r: a lead-in between 0 and 90 deg (30 is usual)" % (name, entry_deg))
    if not 0 < retain_deg <= 90:
        raise SnapError("%s: retain_deg=%r: between 0 and 90 deg (90 self-locks, <= 45 separates)" % (name, retain_deg))


def _sized(name, what, uses, allow, src, fix):
    raise SnapError("%s: no %s fits under the %s allowable strain %.4f (%s). %s" % (name, what, uses, allow, src, fix))


def snap_hook(name, host, catch, at, along, out, length, width, undercut, thickness=None, entry_deg=30.0,
              retain_deg=90.0, taper=1.0, uses="repeated", material=None, print_up=None, clearance=None, ops=None):
    """Cantilever snap hook: the arm (root fillet, barb) on `host`, the channel and undercut pocket cut in `catch`.

    at:        root of the arm on host's surface, the middle of its cross-section (world mm)
    along:     the arm's length direction, root to tip; the hook goes into the catch along it
    out:       the barb's side (perpendicular to along); the arm deflects toward -out while it goes in
    length:    root to the barb's retaining face (Bayer's l); width: across the arm (b); undercut: how far the barb
               holds behind the catch's ledge (y), which is also how far the arm deflects
    thickness: None sizes the root thickness: the thickest (most retention) in [1.2 mm, length / 5] whose strain is
               within the allowable; a given one is checked. taper: tip / root thickness (0.5 halves it)
    entry_deg, retain_deg: the barb's lead-in and retaining face angles (90: permanent, it self-locks)
    uses:      "repeated" (snap_strain, half of yield) or "once" (snap_strain / 0.6)
    material:  of the host (default: its asm.part material if registered, else PLA); print_up: world print +Z of the
               host, when known, so an arm standing across layers is sized to the layer-bond allowable
    clearance: around the barb in the pocket (cadsnap.CLEAR, 0.25)
    ops:       a dict to extend. Returns {part name: {"add": [...], "sub": [...]}}: geom.csg(part, **ops[part.name])

    The record (dims, strain, allowable, P, W_insert, W_release, beam direction, sources) goes to the manifest's
    "joins", and cadcheck's `snaps` check re-evaluates it against the host as built (material, print_rot). Raises
    SnapError when no thickness fits (it names the length, undercut or material that would), when at is not on the
    host, or when the catch has no material where its ledge must be. Formulas: reference/snaps.md."""
    S = _cadsnap()
    _check_in(name, entry_deg, retain_deg, length=length, width=width, undercut=undercut, thickness=thickness,
              taper=taper, clearance=clearance)
    if taper > 1:
        raise SnapError("%s: taper=%r: tip / root thickness, at most 1" % (name, taper))
    if thickness is not None and length < S.SLENDER * thickness:
        raise SnapError("%s: length %.1f < %g x thickness %.2f: the beam formulas don't hold for an arm that stubby (it is "
                        "stiffer and strains more at the root); lengthen it or thin it" % (name, length, S.SLENDER, thickness))
    u, v, wd = _fwd(along, out, name)
    at = Vector(at)
    c = S.CLEAR if clearance is None else clearance
    mat, msrc = _material(host, material)
    M_ = S.CM.MATERIALS[mat]
    E, mu = M_["E_mpa"], M_["mu_self"]
    across, ang = _across(u, "along", print_up)
    allow, asrc = S.allowable(mat, uses, across)
    l, b, y = float(length), float(width), float(undercut)
    if thickness is None:
        h = S.size_hook(l, b, y, E, allow, taper)
        if h is None:
            K, _ = S.cantilever(taper)
            lmin = max(math.sqrt(K * y * S.H_MIN / allow), S.SLENDER * S.H_MIN)
            ymax = allow * l ** 2 / (K * S.H_MIN)
            _sized(name, "arm thickness in [%.1f, %.1f] mm" % (S.H_MIN, l / S.SLENDER), uses, allow, asrc,
                   "Make the arm >= %.1f mm long, or the undercut <= %.2f mm%s, or use a tougher material (PETG)" % (
                       lmin, ymax, ", or uses='once'" if uses == "repeated" else "") +
                   (", or print the arm in the layer plane" if across else ""))
        hsrc = "sized"
    else:
        h, hsrc = float(thickness), "given"
    r = S.hook(l, h, b, y, E, taper, mu, entry_deg, retain_deg)
    if r["strain"] > allow * (1 + 1e-6):
        raise SnapError("%s: strain %.4f at thickness %.2f is over the %s allowable %.4f (%s): pass thickness=None to "
                        "size it, lengthen the arm, or reduce the undercut" % (name, r["strain"], h, uses, allow, asrc))
    # the arm in (s, t) = (along, out), extruded across the width: front face (barb side) at t = h / 2
    f, ht, rr, e = h / 2, h * taper, S.ROOT_R * h, 0.5
    yb = y + c                                 # the ledge starts c above the arm, so the barb stands y + c
    barb, s3 = _barb(l, f, yb, entry_deg, retain_deg, S.TOP_FLAT)
    prof = ([(-e, f + rr)] + geom.arc((rr, f + rr), rr, math.pi, 1.5 * math.pi, 8) + [(l, f)] + barb[::-1][1:3] +
            [(s3, f), (s3, f - ht), (l, f - ht)] + geom.arc((rr, -f - rr), rr, 0.5 * math.pi, math.pi, 8) + [(-e, -f - rr)])
    M = geom.frame(at, u, v, wd)
    if not _inside(host, at - u * 0.3):
        raise SnapError("%s: at=%s is not on %s's surface (no material 0.3 mm behind it, against `along`)" % (
            name, _r(at), host.name))
    ledge = M @ Vector((l - c - 0.3, f + c + y / 2, 0.0))
    if not _inside(catch, ledge):
        raise SnapError("%s: %s has no material at %s, where the ledge the barb holds on must be (just root-side of the "
                        "retaining face, %.2f mm above the arm): move the hook or the catch" % (name, catch.name, _r(ledge), c))
    arm = geom.xform(geom.prism(name + "_arm", prof, -b / 2, b / 2, 'Z'), M)
    ops = _ops(ops, host.name, catch.name)
    ops[host.name]["add"].append(arm)
    ops[catch.name]["sub"] += _catch_cutters(name, barb, s3, f, -f, y, b / 2, c, M)
    barb_mm3 = b * yb * (S.TOP_FLAT + (s3 - l)) / 2
    _join({"kind": "snap_hook", "name": name, "host": host.name, "catch": catch.name, "flex_part": host.name,
           "at": _r(at), "along": _r(u), "out": _r(v), "beam_dir": _r(u), "beam_kind": "along",
           "length": l, "width": b, "undercut": y, "thickness": round(h, 3), "thickness_src": hsrc, "taper": taper,
           "entry_deg": entry_deg, "retain_deg": retain_deg, "uses": uses, "clearance": c, "root_r": round(rr, 2),
           "material": mat, "material_src": msrc, "E_mpa": E, "mu": mu, "strain": round(r["strain"], 5),
           "K": round(r["K"], 4), "allow": round(allow, 5), "allow_src": asrc, "across_layers": across,
           "angle_to_bed_deg": None if ang is None else round(ang, 1), "P_n": round(r["P_n"], 2),
           "W_insert_n": None if r["W_insert_n"] is None else round(r["W_insert_n"], 2),
           "W_release_n": None if r["W_release_n"] is None else round(r["W_release_n"], 2),
           "flex_mm3": round(barb_mm3, 2), "insert_dir": _r(u),
           "source": "Bayer snap-fit guide: eps = K y h / l^2, P = b h^2 E eps / 6 l, W = P (mu + tan a) / (1 - mu tan a)"})
    return ops


def annular_snap(name, shaft, hub, at, axis, d, hub_od, interference=None, entry_deg=30.0, retain_deg=45.0,
                 uses="repeated", material=None, print_up=None, clearance=None, ops=None):
    """Annular (ring) snap, a cap onto a boss: a bead on `shaft` and the matching groove in `hub`'s bore.

    at:     on the axis, at the middle of the bead's crest; axis: the direction the hub comes off (root of the shaft
            toward its free end); d: the shaft diameter at the joint; hub_od: the hub's outside diameter there
    interference: diametral (the bead stands interference / 2 above the hub's bore); None sizes it: the largest
            (0.05 mm steps) whose hoop strain interference / d is within the allowable of the hub's material
    The hub's bore is measured on a ray from `at`: the bead's crest sits interference / 2 above it. The hub is the
    flexing member: its material, uses and print_up set the allowable (the hoop lies in the layers when the axis stands
    up). Returns ops as snap_hook; the record goes to "joins" for cadcheck. Raises SnapError when no interference of at
    least 0.1 mm fits, the bore is smaller than d, or the hub doesn't extend past the bead on the retaining side."""
    S = _cadsnap()
    _check_in(name, entry_deg, retain_deg, d=d, hub_od=hub_od, interference=interference, clearance=clearance)
    if hub_od <= d:
        raise SnapError("%s: hub_od %.2f must be larger than d %.2f" % (name, hub_od, d))
    w, at = Vector(axis).normalized(), Vector(at)
    F = _frame(at, w)
    rad = F.to_3x3() @ Vector((1, 0, 0))
    c = S.CLEAR if clearance is None else clearance
    mat, msrc = _material(hub, material)
    M_ = S.CM.MATERIALS[mat]
    E, nu, mu = M_["E_mpa"], M_["poisson"], M_["mu_self"]
    across, ang = _across(w, "normal", print_up)
    allow, asrc = S.allowable(mat, uses, across)
    if interference is None:
        dd = math.floor(allow * d / 0.05 + 1e-9) * 0.05
        if dd < S.MIN_DD - 1e-9:
            _sized(name, "diametral interference >= %.2f mm" % S.MIN_DD, uses, allow, asrc,
                   "Make the diameter >= %.1f mm, use uses='once', or a tougher material%s" % (
                       S.MIN_DD / allow, " or print the hub with its axis upright" if across else ""))
        src = "sized"
    else:
        dd, src = float(interference), "given"
        if dd / d > allow * (1 + 1e-6):
            raise SnapError("%s: hoop strain %.4f (interference %.2f / d %.1f) is over the %s allowable %.4f (%s): use "
                            "interference <= %.2f or None to size it" % (name, dd / d, dd, d, uses, allow, asrc, allow * d))
    sp = [(a, b_) for a, b_ in _spans(_bvh(hub)[0], at, rad, hub_od) if b_ > 0]
    if not sp:
        raise SnapError("%s: no %s material on a ray out from the axis at %s" % (name, hub.name, _r(at)))
    r_bore = max(0.0, sp[0][0])
    if r_bore < d / 2 - 0.01:
        raise SnapError("%s: %s's bore at the bead is %.2f mm across, smaller than the shaft (d %.2f)" % (
            name, hub.name, 2 * r_bore, d))
    r = S.annular(d, dd, E, hub_od, nu, mu, entry_deg, retain_deg)
    rc, tf = r_bore + dd / 2, S.TOP_FLAT
    hr = rc - d / 2
    z_lo = -tf / 2 - (hr / math.tan(math.radians(retain_deg)) if retain_deg < 89.999 else 0.0)
    z_hi = tf / 2 + hr / math.tan(math.radians(entry_deg))
    ri = max(0.1, d / 2 - 0.5)
    bead = [(ri, z_lo), (d / 2, z_lo), (rc, -tf / 2), (rc, tf / 2), (d / 2, z_hi), (ri, z_hi)]
    hold = F @ Vector((r_bore + max(0.05, dd / 4), 0.0, z_lo - c - 0.3))
    if not _inside(hub, hold):
        raise SnapError("%s: %s has no material at %s, on the retaining side of the bead (toward -axis): the hub must "
                        "reach past the bead" % (name, hub.name, _r(hold)))
    if not _inside(shaft, at + rad * (d / 2 - 0.3)):
        raise SnapError("%s: %s has no material just inside d/2 at %s: check at, axis and d" % (name, shaft.name, _r(at)))
    ops = _ops(ops, shaft.name, hub.name)
    ops[shaft.name]["add"].append(geom.xform(geom.revolve(name + "_bead", bead), F))
    groove = geom.offset_convex(bead, c)        # bead is counter-clockwise in (r, z)
    ops[hub.name]["sub"].append(geom.xform(geom.revolve(name + "_groove", groove), F))
    _join({"kind": "annular_snap", "name": name, "host": shaft.name, "catch": hub.name, "flex_part": hub.name,
           "at": _r(at), "axis": _r(w), "beam_dir": _r(w), "beam_kind": "normal", "d": d, "hub_od": hub_od,
           "interference": round(dd, 3), "interference_src": src, "bore_d": round(2 * r_bore, 3),
           "entry_deg": entry_deg, "retain_deg": retain_deg, "uses": uses, "clearance": c, "material": mat,
           "material_src": msrc, "E_mpa": E, "poisson": nu, "mu": mu, "strain": round(r["strain"], 5),
           "allow": round(allow, 5), "allow_src": asrc, "across_layers": across,
           "angle_to_bed_deg": None if ang is None else round(ang, 1), "X": round(r["X"], 4), "P_n": round(r["P_n"], 2),
           "W_insert_n": None if r["W_insert_n"] is None else round(r["W_insert_n"], 2),
           "W_release_n": None if r["W_release_n"] is None else round(r["W_release_n"], 2),
           "flex_mm3": round(math.pi * 2 * rc * hr * (z_hi - z_lo) / 2, 2), "insert_dir": _r(w),
           "source": "Bayer snap-fit guide: eps = dd / d, P = dd d E X (X: hub elastic, shaft rigid), W as the hook"})
    return ops


def torsion_snap(name, host, catch, at, along, out, bar_len, lever, width, undercut, bar_d=None, bar_d_max=None,
                 thickness=None, entry_deg=30.0, retain_deg=90.0, uses="repeated", material=None, print_up=None, clearance=None, ops=None):
    """Torsion-bar snap: a lever on a round bar that twists, the bar's ends in `host`, the barb's pocket cut in `catch`.

    at:      the middle of the bar; the bar runs along `along` x `out`, bar_len of free span between host's supports
             (it runs 1 mm into each); host must leave a window around the lever (only the bar's ends in material)
    along:   from the bar to the barb (the lever goes into the catch along it); out: the barb's side
    lever:   bar axis to the barb's retaining face; width: the lever's width along the bar; undercut: as snap_hook
    bar_d:   None sizes the bar: the thickest in [1.6 mm, bar_d_max (default the twisting length)] whose shear strain
             phi r / l (l = the twisting length each side, (bar_len - width) / 2) is within (1 + nu) x the allowable;
             give bar_d_max the host's thickness there. thickness: the lever plate (default max(2, bar_d))
    Returns ops as snap_hook; the record goes to "joins" for cadcheck. Raises SnapError when no bar fits, the bar's ends
    are not in host, or the lever sits inside host."""
    S = _cadsnap()
    _check_in(name, entry_deg, retain_deg, bar_len=bar_len, lever=lever, width=width, undercut=undercut, bar_d=bar_d,
              bar_d_max=bar_d_max, thickness=thickness, clearance=clearance)
    u, v, wd = _fwd(along, out, name)
    at = Vector(at)
    c = S.CLEAR if clearance is None else clearance
    mat, msrc = _material(host, material)
    M_ = S.CM.MATERIALS[mat]
    E, nu, mu = M_["E_mpa"], M_["poisson"], M_["mu_self"]
    across, ang = _across(wd, "torsion", print_up)     # always across: torsion's principal stress is at 45 deg
    allow, asrc = S.allowable(mat, uses, across)
    L1, y, bw = float(lever), float(undercut), float(width)
    tl_ = (bar_len - bw) / 2
    if tl_ <= 0:
        raise SnapError("%s: bar_len %.1f leaves no bar to twist beside the %.1f mm lever" % (name, bar_len, bw))
    if bar_d is None:
        dbar = S.size_torsion(tl_, L1, y, allow, nu, d_max=bar_d_max)
        if dbar is None:
            _sized(name, "bar diameter >= %.1f mm" % (S.H_MIN + 0.4), uses, allow, asrc,
                   "Lengthen the bar (each side twists %.1f mm), lengthen the lever, or reduce the undercut" % tl_)
        dsrc = "sized"
    else:
        dbar, dsrc = float(bar_d), "given"
    r = S.torsion(tl_, dbar, L1, y, E, nu, mu, entry_deg, retain_deg)
    if r["shear_strain"] > (1 + nu) * allow * (1 + 1e-6):
        raise SnapError("%s: shear strain %.4f is over (1 + nu) x the %s allowable = %.4f (%s): pass bar_d=None to size it" % (
            name, r["shear_strain"], uses, (1 + nu) * allow, asrc))
    for sgn in (1, -1):
        if not _inside(host, at + wd * sgn * (bar_len / 2 + 0.5)):
            raise SnapError("%s: the bar's end at %s is not in %s: bar_len is the free span between its supports" % (
                name, _r(at + wd * sgn * (bar_len / 2 + 0.5)), host.name))
    if _inside(host, at + u * L1 / 2) or _inside(host, at + wd * tl_ / 2):
        raise SnapError("%s: the lever or bar sits inside %s: cut a window around them first" % (name, host.name))
    tp = max(2.0, dbar) if thickness is None else float(thickness)
    f = tp / 2
    yb = y + c
    barb, s3 = _barb(L1, f, yb, entry_deg, retain_deg, S.TOP_FLAT)
    prof = [(0.0, -f), (s3, -f), (s3, f), barb[1], barb[2], (L1, f), (0.0, f)]
    M = geom.frame(at, u, v, wd)
    plate = geom.xform(geom.prism(name + "_lever", prof, -bw / 2, bw / 2, 'Z'), M)
    bar = geom.xform(geom.cyl(name + "_bar", (0, 0), dbar / 2, -bar_len / 2 - 1.0, bar_len / 2 + 1.0, 'Z'), M)
    ops = _ops(ops, host.name, catch.name)
    ops[host.name]["add"] += [bar, plate]
    ops[catch.name]["sub"] += _catch_cutters(name, barb, s3, f, -f, y, bw / 2, c, M)
    _join({"kind": "torsion_snap", "name": name, "host": host.name, "catch": catch.name, "flex_part": host.name,
           "at": _r(at), "along": _r(u), "out": _r(v), "bar_axis": _r(wd), "beam_dir": _r(wd), "beam_kind": "torsion",
           "bar_len": bar_len, "bar_l": round(tl_, 3), "bars": 2, "bar_d": round(dbar, 3), "bar_d_src": dsrc, "lever": L1,
           "width": bw, "thickness": tp, "undercut": y, "entry_deg": entry_deg, "retain_deg": retain_deg, "uses": uses,
           "clearance": c, "material": mat, "material_src": msrc, "E_mpa": E, "poisson": nu, "mu": mu,
           "shear_strain": round(r["shear_strain"], 5), "strain": round(r["strain"], 5), "phi_deg": round(r["phi_deg"], 2),
           "allow": round(allow, 5), "allow_src": asrc, "across_layers": across,
           "angle_to_bed_deg": None if ang is None else round(ang, 1), "P_n": round(r["P_n"], 2),
           "W_insert_n": None if r["W_insert_n"] is None else round(r["W_insert_n"], 2),
           "W_release_n": None if r["W_release_n"] is None else round(r["W_release_n"], 2),
           "flex_mm3": round(bw * yb * (S.TOP_FLAT + (s3 - L1)) / 2, 2), "insert_dir": _r(u),
           "source": "Bayer snap-fit guide: phi = y / lever, gamma = phi r / l <= (1 + nu) eps; T = 2 G J phi / l"})
    return ops


def pip_hinge(name, parts, axis_at, axis, length, knuckles, pin_d, clearance=None, gap=None, wall=None, lo=0.0,
              hi=90.0, home=0.0, step=None, print_up=None, strict=True, ops=None):
    """Print-in-place hinge between parts = (static, moving): alternating knuckles (first and odd ones on the static
    part), a pin on the static part's knuckles through the moving part's bores, axial gaps between knuckles, and a
    relief cut around each knuckle in the other part. Creates the joint PIV_<name> (register the moving part with
    asm.part(..., joint="PIV_<name>")), so cadcheck sweeps it.

    axis_at: a point on the axis where the hinge starts; axis: a world axis ("X", "Y", "Z", or a unit vector along
             one; the hinge runs `length` along it); knuckles: how many (>= 2)
    pin_d:   pin diameter; clearance: radial, pin to bore and knuckle to relief (cadsnap.HINGE 0.4); gap: axial between
             knuckles (0.4); wall: knuckle wall around the bore (1.2)
    lo, hi, home, step: the joint range in degrees about +axis. print_up: world print +Z: horizontal bores get a
             teardrop. Use an odd knuckle count, so the pin runs into a static knuckle at both ends. With an even
             count it ends inside the last (moving) knuckle, cantilevered from one side, with a 45 deg cone so its end
             is not a flat face. That cone helps only a vertical pin; on the flat axis cadcheck wants, it doesn't
             make the stub self-supporting (the build prints a note).
    The parts must stop short of the knuckle bores in each other's knuckle spans (leaves tangent to the knuckles).
    Returns ops as snap_hook. strict=False builds a clearance or gap under cadsnap.HINGE "min" (0.3) that cadcheck
    then fails; otherwise that raises SnapError. The record goes to "joins"; cadcheck checks the clearances, that the
    axis lies flat on the bed and that both parts print together (the same print_rot)."""
    from . import asm
    S = _cadsnap()
    H = S.HINGE
    c = H["clearance"] if clearance is None else float(clearance)
    g = H["gap"] if gap is None else float(gap)
    wl = H["wall"] if wall is None else float(wall)
    A, B = parts
    _check_in(name, length=length, pin_d=pin_d, clearance=c, gap=g, wall=wl)
    if not isinstance(knuckles, int) or isinstance(knuckles, bool):
        raise SnapError("%s: knuckles=%r: a whole number" % (name, knuckles))
    if isinstance(axis, str):
        if axis.upper() not in ("X", "Y", "Z"):
            raise SnapError("%s: axis=%r: 'X', 'Y', 'Z' or a unit vector along one" % (name, axis))
        axis = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[axis.upper()]
    if Vector(axis).length < 1e-9:
        raise SnapError("%s: axis %r has no direction" % (name, axis))
    w = Vector(axis).normalized()
    k = max(range(3), key=lambda i: abs(w[i]))
    if abs(abs(w[k]) - 1) > 1e-6:
        raise SnapError("%s: axis %s is not along a world axis (asm.joint turns about X, Y or Z)" % (name, _r(w)))
    sgn = 1 if w[k] > 0 else -1
    if knuckles < 2:
        raise SnapError("%s: knuckles=%d: at least 2 (one on each part)" % (name, knuckles))
    if min(c, g) < H["min"] - 1e-9 and strict:
        raise SnapError("%s: clearance %.2f / gap %.2f under %.2f mm fuse in print (cadsnap.HINGE, common FDM practice): "
                        "raise them, or strict=False to build it anyway" % (name, c, g, H["min"]))
    at = Vector(axis_at)
    od = pin_d + 2 * c + 2 * wl
    seg = length / knuckles
    # each relief runs 0.01 into the neighbouring knuckles and trims their ends (no 0.01 mm slivers of leaf, whose
    # faces triangulated across the gaps), so the knuckles are built 0.02 longer to keep the axial gap at g
    gb = g - 0.02
    spans = [(i * seg + (gb / 2 if i else 0.0), (i + 1) * seg - (gb / 2 if i < knuckles - 1 else 0.0)) for i in range(knuckles)]
    if min(z1 - z0 for z0, z1 in spans) < 1.0:
        raise SnapError("%s: knuckles %.2f mm long: fewer knuckles or a longer hinge" % (name, min(z1 - z0 for z0, z1 in spans)))
    F = _frame(at, w)
    rad = [F.to_3x3() @ Vector((math.cos(a), math.sin(a), 0)) for a in [i * math.pi / 4 for i in range(8)]]
    for i, (z0, z1) in list(enumerate(spans))[1::2]:     # the static part's pin runs through these bores
        other = A
        for p in [at + w * (z0 + z1) / 2 + q * rr for q in rad for rr in (pin_d / 2 + c / 2,)] + [at + w * (z0 + z1) / 2]:
            if _inside(other, p):
                raise SnapError("%s: %s has material at %s, inside knuckle %d's bore zone (%.2f mm from the axis): stop it "
                                "at the knuckle (od %.2f)" % (name, other.name, _r(p), i, (p - at - w * (z0 + z1) / 2).length, od))
    ops = _ops(ops, A.name, B.name)
    n = 48
    for i, (z0, z1) in enumerate(spans):
        mine, other = (A, B) if i % 2 == 0 else (B, A)
        ops[mine.name]["add"].append(_place(geom.cyl("%s_k%d" % (name, i), (0, 0), od / 2, z0, z1, 'Z', n), at, w))
        r0, r1 = z0 - gb - 0.01 if i else z0 - 1.0, z1 + gb + 0.01 if i < knuckles - 1 else z1 + 1.0
        rel = geom.cyl("%s_r%d" % (name, i), (0, 0), od / 2 + c, r0, r1, 'Z', n)
        if other is A:      # around a moving knuckle the static part keeps its pin
            geom.csg(rel, sub=[geom.cyl("%s_ri%d" % (name, i), (0, 0), pin_d / 2 + c, r0 - 1, r1 + 1, 'Z', n)])
        ops[other.name]["sub"].append(_place(rel, at, w))
        if mine is B:
            ops[B.name]["sub"].append(_place(_hole("%s_b%d" % (name, i), pin_d + 2 * c, z0 - 0.5, z1 + 0.5, print_up, w), at, w))
    last = spans[-1]
    if knuckles % 2:
        ops[A.name]["add"].append(_place(geom.cyl(name + "_pin", (0, 0), pin_d / 2, 0.0, length, 'Z', n), at, w))
        pin_end = length
    else:
        print("SNAP NOTE %s: %d knuckles: the pin ends inside the last (moving) knuckle, held from one side; an odd "
              "count holds it at both ends" % (name, knuckles))
        pin_end = last[0] + 0.5 * (last[1] - last[0])
        ops[A.name]["add"].append(_place(geom.cyl(name + "_pin", (0, 0), pin_d / 2, 0.0, pin_end, 'Z', n), at, w))
        ops[A.name]["add"].append(_place(geom.cone(name + "_tip", (0, 0), pin_d / 2, 0.05, pin_end - 0.01,
                                                   pin_end + pin_d / 2, 'Z', n), at, w))
    jn = "PIV_%s" % name
    lo_, hi_ = (lo, hi) if sgn > 0 else (-hi, -lo)
    asm.joint(jn, tuple(at), "XYZ"[k], lo_, hi_, home=home * sgn, step=step)
    _join({"kind": "pip_hinge", "name": name, "parts": [A.name, B.name], "static": A.name, "moving": B.name, "joint": jn,
           "axis_at": _r(at), "axis": _r(w), "length": length, "knuckles": knuckles, "pin_d": pin_d, "od": round(od, 3),
           "clearance": c, "gap": g, "wall": wl, "lo": lo, "hi": hi, "pin_end": round(pin_end, 3),
           "spans": [[round(a + (0.01 if i else 0), 3), round(b_ - (0.01 if i < knuckles - 1 else 0), 3)] for i, (a, b_) in enumerate(spans)], "teardrop": print_up is not None,
           "source": "clearances: common FDM practice (cadsnap.HINGE), not a standard"})
    return ops
