"""Print features for PLA on Bambu P1S/H2D: screw holes, nut traps, inserts, bosses, slots, horn recesses.

Every feature is placed with the same two arguments a fastener uses:
    at    = point on the surface where the screw head (or nut, or insert) bears, world mm
    into  = unit direction the shank travels, from the head into the material
so `features.screw_hole(at, into, ...)` and `asm.fastener(name, at, into, ...)` take identical
placement, and a reversed screw (attempt 1: FST_motor_* pointed the wrong way, FINDINGS A1-F10)
shows up as a mismatch instead of a silent clash. Features return objects to pass to geom.csg():
`cut` lists go in sub=, `add` lists in add=.

Numbers are from the design brief (pilot 2.5, clearance 3.4, nut 5.7 AF, wall >= 1.6) plus common
PLA practice; change RULES per printer if a test print disagrees.
"""
import math
from mathutils import Vector, Matrix
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


def screw_hole(at, into, length, kind="selftap", head="cap", sink=0.0, clamp=0.0, print_up=None, name="hole"):
    """Cutters for an M3 screw whose head bears at `at` and whose shank runs `length` along `into`.

    kind:  "selftap"  pilot Ø2.5 all the way (the screw cuts its thread in this part)
           "clearance" Ø3.4 all the way (the part being clamped)
           "clamp"    Ø3.4 for the first `clamp` mm (the clamped part), Ø2.5 pilot beyond (the host)
           "insert"   Ø3.4 for `clamp` mm, then a heat-set insert pocket
    head:  "cap" | "pan" | "csk" | "none".
    sink:  the bearing face `at` lies this far below the part's outer surface: a counterbore
           (cap/pan) is cut from `at` back out by sink + 0.6 mm. For "csk", `at` is the outer
           surface and the countersink cone is cut there.
    print_up: world direction of print +Z for this part; holes with a horizontal axis become
           teardrops (no support inside the hole).
    """
    R = RULES
    cuts = []
    over = 0.6  # extend cutters past the faces so booleans never leave skins
    if kind == "selftap":
        cuts.append(_hole(name + "_pilot", R["m3_selftap_pilot_d"], -over, length + 1.0, print_up, into))
    elif kind == "clearance":
        cuts.append(_hole(name + "_clr", R["m3_clear_d"], -over, length + over, print_up, into))
    elif kind == "clamp":
        cuts.append(_hole(name + "_clr", R["m3_clear_d"], -over, clamp + 0.01, print_up, into))
        cuts.append(_hole(name + "_pilot", R["m3_selftap_pilot_d"], clamp - 0.01, length + 1.0, print_up, into))
    elif kind == "insert":
        cuts.append(_hole(name + "_clr", R["m3_clear_d"], -over, clamp + 0.01, print_up, into))
        cuts.append(_hole(name + "_ins", R["m3_insert_hole_d"], clamp - 0.01, clamp + R["m3_insert_len"] + 0.5, print_up, into))
    else:
        raise ValueError(kind)
    if sink > 0 and head in ("cap", "pan"):
        d = R["counterbore_d"] if head == "cap" else R["m3_pan_head_d"] + 0.6
        cuts.append(geom.cyl(name + "_cb", (0, 0), d / 2, -sink - over, 0.01, 'Z'))
    elif head == "csk":
        r = R["m3_csk_head_d"] / 2 + 0.2
        cuts.append(geom.cone(name + "_csk", (0, 0), r + over, R["m3_clear_d"] / 2, -over, r + over - R["m3_clear_d"] / 2 - over, 'Z'))
    for c in cuts:
        _place(c, at, into)
    _log("screw_hole", at, into, length=length, kind=kind, head=head, sink=sink, clamp=clamp)
    return cuts


def nut_trap(at, into, depth=None, af=None, rot_deg=0.0, slot_dir=None, slot_len=0.0, name="nut"):
    """Hex pocket for an M3 nut whose bearing face is at `at`, pocket going `into`.
    slot_dir (world vector, perpendicular to into) adds a side-entry slot for captive nuts."""
    af = af or RULES["nut_trap_af"]
    depth = depth or RULES["m3_nut_h"] + RULES["nut_trap_h_extra"]
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
