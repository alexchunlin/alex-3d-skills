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
"""
import ast, math, os
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
    "min_engagement": 6.0,          # self-tap thread length worth having in PLA
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
# PLA holes: clearance d + 0.4 (M4/M5 + 0.5), self-tap pilot ~0.83 d, PLA-tap (machine screw cutting its own thread)
# ~0.93 d. Heads ISO 4762 (cap), ISO 7045 (pan), ISO 7046 actual dk (csk); nuts ISO 4032; heat-set inserts are the
# common CNC Kitchen / Ruthex sizes. min_engagement = 2 d of self-tap thread in PLA; tapped_engagement = 1.5 d in a
# tapped (aluminium) purchased part. Stock lengths are not here: size_rules reads them from cadcheck's
# fasteners.stock_lengths, so a picked length is never one cadcheck warns is not stocked. The M3 row is overlaid
# with the m3_* entries of RULES at lookup (size_rules), so RULES stays the place to tune M3 for a printer.
SIZES = {
    "M2": dict(d=2.0, pitch=0.4, clear_d=2.4, pilot_d=1.6, tap_d=1.8, cap=(3.8, 2.0), pan=(3.8, 1.3), csk=(3.8, 1.2),
               nut_af=4.0, nut_h=1.6, insert_d=3.2, insert_len=3.0, min_engagement=4.0, tapped_engagement=3.0),
    "M2.5": dict(d=2.5, pitch=0.45, clear_d=2.9, pilot_d=2.0, tap_d=2.3, cap=(4.5, 2.5), pan=(5.0, 1.75), csk=(4.7, 1.5),
                 nut_af=5.0, nut_h=2.0, insert_d=3.6, insert_len=4.0, min_engagement=5.0, tapped_engagement=3.75),
    # M3 holes, nut and insert: RULES m3_*
    "M3": dict(d=3.0, pitch=0.5, cap=(5.5, 3.0), pan=(6.0, 2.4), csk=(6.0, 1.7), tapped_engagement=4.5),
    "M4": dict(d=4.0, pitch=0.7, clear_d=4.5, pilot_d=3.3, tap_d=3.7, cap=(7.0, 4.0), pan=(8.0, 3.1), csk=(8.4, 2.7),
               nut_af=7.0, nut_h=3.2, insert_d=5.6, insert_len=8.1, min_engagement=8.0, tapped_engagement=6.0),
    "M5": dict(d=5.0, pitch=0.8, clear_d=5.5, pilot_d=4.2, tap_d=4.6, cap=(8.5, 5.0), pan=(9.5, 3.7), csk=(9.3, 2.7),
               nut_af=8.0, nut_h=4.7, insert_d=6.4, insert_len=9.5, min_engagement=10.0, tapped_engagement=7.5),
}


def size_rules(size="M3"):
    """One row of SIZES with the derived numbers: counterbore_d (cap head + 1.0, as RULES counterbore_d for M3),
    trap_af (nut + 0.2, the brief's 5.7 for M3), lengths (cadcheck DEFAULTS fasteners.stock_lengths for d)."""
    if size not in SIZES:
        raise ValueError("size %r: known sizes %s" % (size, sorted(SIZES)))
    s = dict(SIZES[size])
    if size == "M3":
        R = RULES
        s.update(clear_d=R["m3_clear_d"], pilot_d=R["m3_selftap_pilot_d"], tap_d=R["m3_tap_machine_d"],
                 nut_af=R["m3_nut_af"], nut_h=R["m3_nut_h"], trap_af=R["nut_trap_af"], insert_d=R["m3_insert_hole_d"],
                 insert_len=R["m3_insert_len"], counterbore_d=R["counterbore_d"], min_engagement=R["min_engagement"],
                 cap=(R["m3_head_d"], R["m3_head_h"]), pan=(R["m3_pan_head_d"], R["m3_pan_head_h"]),
                 csk=(R["m3_csk_head_d"], s["csk"][1]))
    s.setdefault("counterbore_d", s["cap"][0] + 1.0)
    s.setdefault("trap_af", s["nut_af"] + 0.2)
    s["lengths"] = list(check_default("fasteners", "stock_lengths")["%g" % s["d"]])
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


_CHECK_DEFAULTS = {}


def check_default(section, key):
    """A number from cadcheck.py DEFAULTS, read from its source (cadcheck runs on import), so the joint rules and
    the check that judges them cannot drift apart."""
    if not _CHECK_DEFAULTS:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cadcheck.py")) as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DEFAULTS":
                _CHECK_DEFAULTS.update(ast.literal_eval(node.value))
    return _CHECK_DEFAULTS[section][key]


def axis_stack(at, into, parts, eps=0.05):
    """[(object, t_in, t_out)]: each part's first stretch of material along the line through `at` along `into`
    that ends ahead of `at` (t in mm from `at`, negative behind it), sorted by t_in. A part with no material ahead
    comes back as (object, None, None) at the end. The line is offset 0.01 mm so it never runs down a mesh edge."""
    w = Vector(into).normalized()
    F3 = _frame((0, 0, 0), w).to_3x3()
    p = Vector(at) + F3.col[0] * 0.0137 + F3.col[1] * 0.0091
    found, missing = [], []
    for ob in parts:
        M = ob.matrix_world
        vs = [M @ x.co for x in ob.data.vertices]
        reach = max((x - p).length for x in vs) + 1.0
        tree = BVHTree.FromPolygons(vs, [tuple(f.vertices) for f in ob.data.polygons])
        o, hits, t = p - w * reach, [], 0.0
        while t < 2 * reach:
            loc, nrm, _, dist = tree.ray_cast(o + w * t, w, 2 * reach - t)
            if loc is None:
                break
            th, sgn = t + dist - reach, (1 if nrm.dot(w) < 0 else -1)     # +1 entering material, -1 leaving
            if not hits or abs(hits[-1][0] - th) > 1e-3 or hits[-1][1] != sgn:
                hits.append((th, sgn))
            t += dist + 1e-4
        depth, t0, span = 0, None, None
        for th, sgn in hits:
            depth = max(0, depth + sgn)
            if sgn > 0 and depth == 1:
                t0 = th
            elif sgn < 0 and depth == 0 and t0 is not None:
                if th > eps:
                    span = (t0, th)
                    break
                t0 = None
        if span:
            found.append((ob, span[0], span[1]))
        else:
            missing.append((ob, None, None))
    return sorted(found, key=lambda r: r[1]) + missing


def _purchased(ob):
    return ob.name.startswith("BUY_") or any(c.name == "Purchased" for c in ob.users_collection)


def _r(v):
    return [round(c, 2) for c in v]


def fastener_joint(name, size, at, into, parts, style="selftap", head="cap", sink=0.0, length=None,
                   min_engagement=None, depth=None, trap=True, nut_rot_deg=0.0, print_up=None,
                   joint=None, host=None, step=None, strict=True, cuts=None):
    """One fastened joint: measure the stack, pick the length, cut every part, place the screw (and nut or insert).

    at, into: as screw_hole / asm.fastener. `at` is the head's bearing face (for head="csk", the outer surface the
              head sits flush with); `into` is the direction the shank travels.
    size:     "M2", "M2.5", "M3", "M4" or "M5" (SIZES). Changing the size is this one argument.
    parts:    the solids the screw passes, uncut, in any order. The stack is measured along the axis: every part
              but the last one met is clamped (clearance hole); the last one holds the thread. Name the solids
              with their final PRT_/BUY_ names: the cutters come back under those names.
    style:    "selftap"  pilot in the last part; thread >= min_engagement (SIZES, 2 d) into it
              "nut"      through-bolt; nut in a hex trap at the far face of the last part (trap=False: the nut
                         bears on that face). The bolt passes the nut by at least one pitch.
              "insert"   heat-set insert pocket in the last part; the screw runs through the whole insert
              "tapped"   machine screw into a tapped purchased part (no cut in it; thread >= tapped_engagement, and
                         <= depth, the datasheet depth of its tapped hole). A printed last part gets the PLA-tap hole.
    head:     "cap" | "pan" | "csk". sink > 0 counterbores the head (cap/pan): `at` is then sink below the surface.
    length:   None picks the shortest stock length (size_rules(size)["lengths"]) that meets the rule, with the tip
              never more than cadcheck's fasteners.max_protrusion past the last material (the nut counts). A
              given length is checked against the same rule; strict=False keeps one that breaks it (rule_ok False).
    print_up: world print +Z, or {part name: print +Z}, for teardrop holes in parts printed on their side.
    joint, host, step: as asm.fastener (host defaults to the last part's name).
    cuts:     a dict to extend, so several joints accumulate and each part gets one csg.

    Returns cuts: {part name: [cutters]}, for geom.csg(part, sub=cuts[part.name]); a part may get an empty list.
    The record (stack, grip, length, engagement, rule) goes to the manifest under the screw's "fastener_joint".
    Raises FastenerError when the joint cannot meet the rules: no part ahead of `at` (a reversed screw,
    FINDINGS A1-F10), a head that would sit inside or off the first part, too little thread (A3-F5), no stock
    length between the minimum and the protrusion limit, or a given length that stops short of its nut (A2-F3).
    """
    from . import asm      # asm imports features
    S = size_rules(size)
    if style not in ("selftap", "nut", "insert", "tapped"):
        raise ValueError("style %r: selftap, nut, insert or tapped" % style)
    if head not in ("cap", "pan", "csk"):
        raise ValueError("head %r: cap, pan or csk" % head)
    w, at = Vector(into).normalized(), Vector(at)
    maxp = check_default("fasteners", "max_protrusion")
    st = axis_stack(at, w, parts)
    lost = [o.name for o, a, b in st if a is None]
    st = [r for r in st if r[1] is not None]
    if not st:
        raise FastenerError("%s: none of %s has material ahead of at=%s along into=%s, so the parts are behind the "
                            "head: flip `into` (it points from the head into the material)" % (
                                name, [o.name for o in parts], _r(at), _r(w)))
    if lost:
        raise FastenerError("%s: %s not on the axis ahead of at=%s along into=%s (stack found: %s)" % (
            name, lost, _r(at), _r(w), [(o.name, round(a, 2), round(b, 2)) for o, a, b in st]))
    first, (last, t_in, t_out) = st[0], st[-1]
    want0 = -sink if (sink > 0 and head != "csk") else 0.0
    if first[1] < want0 - 0.3:
        raise FastenerError("%s: the head would sit %.2f mm inside %s; `at` is the bearing face: move it, flip "
                            "`into`, or pass sink=%.2f for a counterbore" % (name, want0 - first[1], first[0].name, -first[1]))
    if first[1] > want0 + 0.3:
        raise FastenerError("%s: the head stands %.2f mm off %s; `at` is the bearing face%s" % (
            name, first[1] - want0, first[0].name, " (sink=%g puts it %g below the surface)" % (sink, sink) if sink else ""))
    buy = _purchased(last)
    rec = {"size": size, "style": style, "head": head, "stack": [[o.name, round(a, 2), round(b, 2)] for o, a, b in st]}
    nf = nf_lo = nf_hi = None                       # nut bearing face, mm from `at`
    if style in ("selftap", "tapped"):
        need = S["tapped_engagement"] if (style == "tapped" and buy) else S["min_engagement"]
        need = need if min_engagement is None else min_engagement
        if t_in + need > t_out + TOL:
            raise FastenerError("%s: %s gives only %.1f mm of thread on this axis; %s %s needs %.1f. Add a boss, use "
                                "style='nut' or 'insert', or pass min_engagement=" % (
                                    name, last.name, t_out - t_in, size, style, need))
        lo, hi = t_in + need, t_out + maxp
        if style == "tapped" and depth:
            hi = min(hi, t_in + depth)
        rule = "thread >= %.1f mm in %s" % (need, last.name)
    elif style == "insert":
        if t_in + S["insert_len"] + 0.5 > t_out + TOL:
            raise FastenerError("%s: %s is %.1f mm thick on this axis; a %s insert pocket needs %.1f" % (
                name, last.name, t_out - t_in, size, S["insert_len"] + 0.5))
        lo, hi = t_in + S["insert_len"], t_out + maxp
        rule = "screw through the %.1f mm insert" % S["insert_len"]
    else:
        pocket = S["nut_h"] + RULES["nut_trap_h_extra"]
        nf_hi, nf_lo = (t_out - pocket, t_in + RULES["min_wall"]) if trap else (t_out, t_out)
        if nf_hi < nf_lo - TOL:
            raise FastenerError("%s: %s is %.1f mm thick on this axis, too thin for a %s nut trap (needs %.1f); use "
                                "trap=False (nut on its far face)" % (
                                    name, last.name, t_out - t_in, size, pocket + RULES["min_wall"]))
        nf = nf_hi
        lo, hi = nf + S["nut_h"] + S["pitch"], nf + S["nut_h"] + maxp
        rule = "bolt passes the nut by %.2f to %.1f mm" % (S["pitch"], maxp)
    ok = True
    if length is None:
        fit = [l for l in S["lengths"] if lo - TOL <= l <= hi + TOL]
        if not fit and style == "nut" and trap:
            # no stock length with the nut at the far face: sink the trap deeper, as little as needed
            deeper = [l for l in S["lengths"] if nf_lo + S["nut_h"] + S["pitch"] - TOL <= l < lo - TOL]
            if deeper:
                fit = [max(deeper)]
                nf = max(nf_lo, fit[0] - S["nut_h"] - min(2 * S["pitch"], maxp))
                lo, hi = nf + S["nut_h"] + S["pitch"], nf + S["nut_h"] + maxp
                rec["trap_deepened_mm"] = round(nf_hi - nf, 2)
        if not fit:
            raise FastenerError("%s: no stock %s length between %.2f and %.2f mm (%s; tip <= %.1f past the last "
                                "material). Stock: %s. Change the stack, or pass length= with strict=False" % (
                                    name, size, lo, hi, rule, maxp, S["lengths"]))
        L = float(min(fit))
    else:
        L = float(length)
        if not lo - TOL <= L <= hi + TOL:
            msg = "%s: length %g breaks the rule (%s): needs %.2f to %.2f mm" % (name, L, rule, lo, hi)
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
               holes={k: S[k] for k in ("clear_d", "pilot_d", "tap_d", "trap_af", "insert_d")})
    # cutters per part; head cuts go to every part (a countersink deeper than the first part cuts the next)
    cuts = {} if cuts is None else cuts
    clamp = max(0.0, t_in)
    tip, wall = 1.0, RULES["min_wall"]
    if 0 < t_out - (L + tip) < wall:
        # a blind hole would leave a skin too thin to print under the tip: stop at min_wall, or go through
        tip = t_out - wall - L if t_out - wall >= L + 0.5 else t_out - L + 0.6
    for i, (ob, a, b) in enumerate(st):
        up = print_up.get(ob.name) if isinstance(print_up, dict) else print_up
        kw = dict(head=head, sink=sink, print_up=up, name="%s_%d" % (name, i), size=size, tip=tip)
        lst = cuts.setdefault(ob.name, [])
        if ob is not last:
            lst += screw_hole(at, w, L, "clearance", **kw)
        elif style == "selftap":
            lst += screw_hole(at, w, L, "clamp", clamp=clamp, **kw)
        elif style == "tapped":
            lst += [] if buy else screw_hole(at, w, L, "tap", clamp=clamp, **kw)
        elif style == "insert":
            lst += screw_hole(at, w, L, "insert", clamp=clamp, **kw)
        else:
            lst += screw_hole(at, w, L, "clearance", **kw)
            if trap:
                lst += nut_trap(at + w * nf, w, depth=t_out - nf + 0.6, rot_deg=nut_rot_deg, name=kw["name"] + "_nut", size=size)
    # hardware on the same at/into
    asm.fastener(name, at, w, L, spec="%s_%s" % (size, head), joint=joint, host=host or last.name, step=step)
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
