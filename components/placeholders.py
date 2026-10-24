"""Purchased-part placeholders built from components.json, in each part's own local frame.

    sys.path.insert(0, "<repo>/components"); import placeholders as PH
    ob = PH.servo("BUY_servo_tilt")                 # local frame, see each docstring
    G.xform(ob, G.frame(origin, u, v, w))           # place it
    A.part(ob, "BUY_servo_tilt", 'BUY', "buy", joint="PIV_pan", mass_g=PH.C["hiwonder_bus_servo"]["mass_g"], src="components.json")

Dimensions come from components.json (one source of truth). The STL-backed parts need the reference
folder; pass ref_dir or set MM_REF.
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G  # noqa: E402

C = json.load(open(os.path.join(HERE, "components.json")))
REF = os.environ.get("MM_REF", os.path.expanduser("~/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/reference"))


def servo(name="BUY_servo"):
    """Hiwonder bus servo. Origin on the spline axis at the top face; spline up +Z; body below z=0;
    length along X with the body centre at x = -offset."""
    s = C["hiwonder_bus_servo"]
    L, W, H = s["body"]
    off, sp = s["spline"]["offset_from_body_centre"], s["spline"]["protrudes"]
    b = G.box(name, -off - L / 2, -off + L / 2, -W / 2, W / 2, -H, 0)
    G.bevel(b, 1.0)
    r = s["spline"]["boss_d"] / 2
    return G.csg(b, add=[G.cyl(name + "s", (0, 0), r, -0.01, sp), G.cyl(name + "i", (0, 0), r, -H - s["idler_boss"]["protrudes"], -H + 0.01)])


def horn(name="BUY_horn"):
    """Disc horn. Origin on the axis at the hub underside (sits on the spline top), disc above."""
    h = C["servo_horn_disc"]
    hub = G.cyl(name + "h", (0, 0), h["hub"]["d"] / 2, 0, h["hub"]["h"] + 0.01)
    d = G.cyl(name, (0, 0), h["disc"]["d"] / 2, h["hub"]["h"], h["hub"]["h"] + h["disc"]["t"])
    bc = h["holes"]["bolt_circle_d"] / 2
    holes = [G.cyl(name + "x%d" % k, (bc * math.cos(k * math.pi / 4), bc * math.sin(k * math.pi / 4)), h["holes"]["d"] / 2, -1, 10, n=12)
             for k in range(h["holes"]["n"])]
    return G.csg(d, add=[hub], sub=holes)


def motor_3674(name="BUY_motor"):
    """XTEAM 3674. Axis = +X, origin at the front face centre, body toward -X, shaft toward +X (D-flat on +Y side)."""
    m = C["xteam_3674"]
    D, L = m["body"]["d"], m["body"]["l"]
    sh = m["shaft"]
    body = G.cyl(name, (0, 0), D / 2, -L, 0, 'X', n=96)
    G.bevel(body, 0.8)
    round_len = sh["l"] - sh["d_flat_len"]
    shaft = G.cyl(name + "s", (0, 0), sh["d"] / 2, -0.01, round_len, 'X', n=24)
    rb, fl = sh["d"] / 2, sh["flat_to_axis"]
    dp = [(rb * math.cos(math.radians(a)), rb * math.sin(math.radians(a))) for a in range(0, 360, 10) if rb * math.sin(math.radians(a)) < fl]
    dsh = G.prism(name + "d", G.hull2d(dp + [(-math.sqrt(rb * rb - fl * fl), fl), (math.sqrt(rb * rb - fl * fl), fl)]), round_len - 0.01, sh["l"], 'X')
    acc = G.cyl(name + "a", (0, 0), m["rear_access_hole_d"] / 2, -L - 1, -L + 1.5, 'X', n=24)
    stub = G.cyl(name + "r", (0, 0), sh["d"] / 2, -L + 0.5, -L + 1.6, 'X', n=24)
    ob = G.csg(body, add=[shaft, dsh])
    ob = G.csg(ob, sub=[acc])
    return G.csg(ob, add=[stub])


def magnet(name="BUY_magnet"):
    """Diametric magnet, axis +Z, origin at the face glued to the shaft, magnet toward -Z."""
    mg = C["plink_mt6701"]["magnet"]
    return G.cyl(name, (0, 0), mg["d"] / 2, -mg["t"], 0, n=24)


def motorgo_axis(name="BUY_motorgo_axis", ref_dir=None):
    """Exact STL in its STEP frame (see components.json motorgo_axis.frame)."""
    return G.import_stl(os.path.join(ref_dir or REF, "mg_axis.stl"), name)


def plink(name="BUY_plink_encoder", ref_dir=None):
    """Exact STL: PCB back on z=0, IC up (+Z), IC centred on the origin."""
    return G.import_stl(os.path.join(ref_dir or REF, "plink_encoder.stl"), name)


def servo_controller(name="BUY_servo_controller"):
    """58 x 42 board, origin at the board centre on its underside, components +Z. Long edge along X."""
    s = C["hiwonder_servo_controller"]
    L, W, T = s["pcb"]
    pcb = G.box(name, -L / 2, L / 2, -W / 2, W / 2, 0, T)
    hx, hy = s["holes"]["rect"][0] / 2, s["holes"]["rect"][1] / 2
    pcb = G.csg(pcb, sub=[G.cyl(name + "h%d%d" % (a, b), (a * hx, b * hy), s["holes"]["d"] / 2, -1, T + 1, n=12) for a in (-1, 1) for b in (-1, 1)])
    comp = G.box(name + "c", -L / 2 + 4, L / 2 - 4, -W / 2 + 4, W / 2 - 4, T - 0.01, s["top_components_h"])
    ports = [G.box(name + "p%d" % k, -L / 2 + 6, L / 2 - 6, min(k * (W / 2 - 6), k * (W / 2 + s["port_overhang"])),
                   max(k * (W / 2 - 6), k * (W / 2 + s["port_overhang"])), T - 0.01, T + 7.5) for k in (-1, 1)]
    under = G.box(name + "u", -L / 2 + 8, L / 2 - 8, -W / 2 + 8, W / 2 - 8, -s["under_h"], 0.01)
    return G.join(name, [pcb, comp, under] + ports)


def battery(name="BUY_battery"):
    """DeWalt 20V envelope, origin at the centre of its underside, slide axis along X."""
    L, W, H = C["dewalt_20v_battery"]["envelope"]
    b = G.box(name, -L / 2, L / 2, -W / 2, W / 2, 0, H)
    return G.bevel(b, 3.0, seg=2)


def dewalt_adapter(name="BUY_dewalt_adapter"):
    """Adapter body, origin at the centre of its top face (screw holes), body below."""
    L, W, H = C["dewalt_20v_adapter"]["body"]
    b = G.box(name, -L / 2, L / 2, -W / 2, W / 2, -H, 0)
    return G.bevel(b, 2.0)


def buck(name="BUY_buck_12v"):
    """Finned buck, origin at the centre of its mounting base underside; fins up, along X."""
    Lx, Ly, H = C["buck_12v_finned"]["body"]
    base = G.box(name, -Lx / 2, Lx / 2, -Ly / 2 + 4, Ly / 2 - 4, 0, 5)
    fins = [G.box(name + "f%d" % k, -Lx / 2, Lx / 2, -Ly / 2 + 5 + k * 7.7, -Ly / 2 + 7 + k * 7.7, 4.9, H) for k in range(9)]
    return G.csg(base, add=fins)


def mm_lentil(name="MM"):
    """Payload M&M as a closed lentil (two spherical caps), axis +Z, centred on the origin."""
    m = C["mm_plain"]["lentil"]
    a, t = m["d"] / 2, m["t"] / 2
    R = (a * a + t * t) / (2 * t)              # sphere radius of each cap
    prof = [(0.0, -t)] + [(R * math.sin(th), -(R * math.cos(th) - (R - t))) for th in [i * math.asin(a / R) / 12 for i in range(1, 13)]]
    prof += [(r, -z) for r, z in reversed(prof[1:-1])] + [(0.0, t)]
    pts = [(max(r, 0.0), z) for r, z in prof]
    return G.revolve(name, [(r if r > 1e-3 else 1e-3, z) for r, z in pts], n=48)


ALL = [servo, horn, motor_3674, magnet, motorgo_axis, plink, servo_controller, battery, dewalt_adapter, buck, mm_lentil]
