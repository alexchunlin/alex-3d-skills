"""cadsnap: snap-fit and print-in-place hinge math. Plain python3, no Blender: cadlib.features sizes snap_hook,
annular_snap, torsion_snap and pip_hinge with it, and cadcheck re-checks their manifest records (and hand-written
flexures rows with dimensions) with it, against the part's material and print orientation as built.

    hook(l, h, b, y, E, taper)            cantilever hook: strain, deflection force P, insertion / release force W
    size_hook(l, b, y, E, allow, taper)   the thickest arm (most retention) under the allowable strain, or None
    annular(d, dd, E, hub_od, nu)         ring snap: hoop strain dd / d, transverse force, W
    torsion(bar_l, bar_d, lever, y, ...)  torsion-bar snap: shear strain, angle, P, W
    wedge(P, alpha_deg, mu)               W = P (mu + tan a) / (1 - mu tan a); None when the face self-locks
    allowable(material, uses, across)     allowable strain and where it comes from
    beam_stress(l, h, y, E, end, kt)      bending stress of a leaf from its deflection (flexures rows)

Every formula and constant names its source in reference/snaps.md. They were written down without network access, from
the Bayer MaterialScience (now Covestro) "Snap-Fit Joints for Plastics - A Design Guide" and the BASF snap-fit design
guide as recalled: constants marked RECALLED below are to be checked against the guides before relying on them.

Why: push-assist's designer typed a leaf stress of 7.6 MPa into a flexures row that cadcheck trusted; the reviewer's
script found 9-22 MPa with Kt (PA-A3-T22). mm-launcher v2 had about 103 screws in 18 types across 36 parts, and the
user wants more snaps and printed hinges: a join that is sized by a call and re-checked from its record.
"""
import math
import cadmat as CM

# PLA on PLA has no published coefficient we could cite offline. Bayer's table gives 0.5-0.7 for PC on PC and 0.3-0.4
# for POM on POM (RECALLED); 0.5 is an ASSUMPTION for printed PLA on itself, inside that range. cadmat carries it per
# material (MATERIALS[m]["mu_self"]) so a measured value goes in one place.
H_MIN = 1.2         # mm: thinnest printed arm or bar; three 0.42 mm lines (common FDM practice, ASSUMPTION)
SLENDER = 5.0       # beam formulas need l >= ~5 h: shear and root rotation stiffen a stubbier arm (RECALLED, Bayer)
TOP_FLAT = 0.5      # mm: flat on the barb's crest, so the tip doesn't print as a knife edge (ASSUMPTION)
ROOT_R = 0.5        # root fillet radius / thickness: Bayer's stress-concentration chart levels off near R/h = 0.5 (RECALLED)
CLEAR = 0.25        # mm: snap catch pocket clearance around the barb (ASSUMPTION: features.RULES fit_slide is 0.25 diametral)
MIN_DD = 0.1        # mm: smallest diametral interference worth printing; FDM holds about +-0.1 mm (ASSUMPTION)
ONCE_FACTOR = 0.6   # Bayer: a snap separated often gets about 60 % of the one-time permissible strain (RECALLED)
# print-in-place hinge defaults: 0.4 mm radial and axial gaps print and break free on a 0.4 mm nozzle at 0.2 mm layers;
# 0.3 mm is about the least that reliably doesn't fuse. Common FDM practice (maker guides, test hinges), ASSUMPTION,
# not a standard: print a test hinge for a new printer or material.
HINGE = {"clearance": 0.4, "gap": 0.4, "min": 0.3, "wall": 1.2}   # cadcheck: print_in_place.min_clearance


def cantilever(taper=1.0, n=400):
    """(K, C) for a cantilever whose thickness runs linearly from h at the root to taper x h at the tip, loaded at the
    tip: max strain = K y h / l^2 and P = C E b h^3 y / l^3. Constant section: K = 1.5 (Bayer's y = 0.67 eps l^2 / h),
    C = 0.25 (y = P l^3 / 3 E I). Thickness halving: K = 0.92 (Bayer's y = 1.09 eps l^2 / h). Simpson integration of
    the Euler-Bernoulli deflection, so any taper in (0, 1] works."""
    if not 0 < taper <= 1:
        raise ValueError("taper=%r: tip/root thickness ratio in (0, 1]" % taper)
    hx = lambda x: 1.0 - (1.0 - taper) * x          # thickness / h at x / l
    f = lambda x: 12.0 * (1.0 - x) ** 2 / hx(x) ** 3      # y = (P l^3 / E b h^3) * integral
    s = f(0) + f(1) + sum((4 if i % 2 else 2) * f(i / n) for i in range(1, n))
    yint = s / (3.0 * n)
    emax = max(6.0 * (1.0 - i / n) / hx(i / n) ** 2 for i in range(n))   # eps = (P l / E b h^2) * this
    return emax / yint, 1.0 / yint


def wedge(P, alpha_deg, mu):
    """Bayer's mating force over a ramp of angle alpha: W = P (mu + tan a) / (1 - mu tan a). None when 1 - mu tan a
    <= 0: the face self-locks (retain 90 deg), and the joint only comes apart by deflecting the arm by hand."""
    if P is None:
        return None
    t = math.tan(math.radians(alpha_deg)) if alpha_deg < 89.999 else float("inf")
    den = 1.0 - mu * t
    if den <= 1e-9:
        return None
    return P * (mu + t) / den


def allowable(material, uses="repeated", across=False):
    """(allowable strain, source). repeated: cadmat snap_strain (half the yield strain); once: snap_strain / 0.6 (Bayer:
    repeated use takes about 60 % of the one-time value). across=True (the flexing member's tension crosses layer
    bonds): no more than across_mpa / E, the layer-bond allowable as a strain."""
    if uses not in ("repeated", "once"):
        raise ValueError("uses=%r: 'repeated' or 'once'" % uses)
    m = CM.MATERIALS[material]
    e = m["snap_strain"] if uses == "repeated" else m["snap_strain"] / ONCE_FACTOR
    src = "%s snap_strain %.4f (yield/2)%s" % (material, m["snap_strain"], "" if uses == "repeated" else " / %.1f, one-time use" % ONCE_FACTOR)
    if across:
        ea = m["across_mpa"] / m["E_mpa"]
        if ea < e:
            e, src = ea, "%s across layers: across_mpa %g / E %g" % (material, m["across_mpa"], m["E_mpa"])
    return e, src


def hook(l, h, b, y, E, taper=1.0, mu=0.5, entry_deg=30.0, retain_deg=90.0):
    """Cantilever hook of length l (root to the barb's retaining face), root thickness h, width b, undercut y, modulus E.
    strain = K y h / l^2 (K = 1.5 constant section); P = b h^2 E eps / (6 l) at the root (Bayer), the same number as
    P = C E b h^3 y / l^3; W_insert / W_release = wedge(P, entry / retain). Forces in N."""
    K, C = cantilever(taper)
    eps = K * y * h / l ** 2
    P = C * E * b * h ** 3 * y / l ** 3
    return {"strain": eps, "K": K, "P_n": P, "W_insert_n": wedge(P, entry_deg, mu), "W_release_n": wedge(P, retain_deg, mu)}


def size_hook(l, b, y, E, allow, taper=1.0, h_min=H_MIN, h_max=None, step=0.1):
    """The thickest root thickness (rounded down to `step`) in [h_min, h_max (l / SLENDER)] whose strain is within
    `allow`, or None. Thicker is more retention force for the same strain."""
    K, _ = cantilever(taper)
    h_max = l / SLENDER if h_max is None else h_max
    h = min(h_max, allow * l ** 2 / (K * y))
    h = math.floor(h / step + 1e-9) * step
    return round(h, 3) if h >= h_min - 1e-9 else None


def lame_X(delta, nu):
    """Bayer's geometric factor for an annular snap whose hub (outer part, outer/inner diameter ratio delta) takes the
    deformation over a rigid shaft: X = 0.62 sqrt((delta - 1) / (delta + 1)) / ((delta^2 + 1) / (delta^2 - 1) + nu).
    RECALLED: the (delta^2 + 1) / (delta^2 - 1) + nu term is Lame's thick-cylinder compliance; the 0.62 and the square
    root are from the guide's equation as remembered. Check against its chart of X vs delta."""
    if delta <= 1:
        raise ValueError("hub_od / d = %.3f: the hub must be larger than the joint diameter" % delta)
    return 0.62 * math.sqrt((delta - 1) / (delta + 1)) / ((delta ** 2 + 1) / (delta ** 2 - 1) + nu)


def annular(d, dd, E, hub_od, nu=0.35, mu=0.5, entry_deg=30.0, retain_deg=45.0):
    """Annular snap at joint diameter d with diametral interference dd: hoop strain = dd / d (the hub takes all of it,
    the shaft is rigid: Bayer); transverse force P = dd x d x E x X (X: lame_X), W as wedge(). Forces in N."""
    eps = dd / d
    X = lame_X(hub_od / d, nu)
    P = dd * d * E * X
    return {"strain": eps, "X": X, "P_n": P, "W_insert_n": wedge(P, entry_deg, mu), "W_release_n": wedge(P, retain_deg, mu)}


def torsion(bar_l, bar_d, lever, y, E, nu=0.35, mu=0.5, entry_deg=30.0, retain_deg=90.0, bars=2):
    """Torsion-bar snap: a lever on a round bar that twists, `bars` lengths of bar_l each (a lever in the middle of one
    bar held at both ends: two). Angle phi = y / lever (rad); shear strain gamma = phi r / bar_l (Bayer: phi = 180 gamma
    l / (pi r) in degrees); the allowable is gamma <= (1 + nu) eps (Bayer). Torque T = bars G J phi / bar_l, G =
    E / 2(1 + nu), J = pi d^4 / 32; P = T / lever at the barb. Forces in N."""
    phi = y / lever
    gamma = phi * (bar_d / 2) / bar_l
    G = E / (2 * (1 + nu))
    T = bars * G * math.pi * bar_d ** 4 / 32 * phi / bar_l
    P = T / lever
    return {"shear_strain": gamma, "strain": gamma / (1 + nu), "phi_deg": math.degrees(phi), "torque_nmm": T, "P_n": P,
            "W_insert_n": wedge(P, entry_deg, mu), "W_release_n": wedge(P, retain_deg, mu)}


def size_torsion(bar_l, lever, y, allow, nu=0.35, d_min=H_MIN + 0.4, d_max=None, step=0.1):
    """The thickest bar (rounded down to `step`) in [d_min, d_max (bar_l)] with gamma <= (1 + nu) x allow, or None."""
    phi = y / lever
    d = 2 * (1 + nu) * allow * bar_l / phi
    d = math.floor(min(d, bar_l if d_max is None else d_max) / step + 1e-9) * step
    return round(d, 3) if d >= d_min - 1e-9 else None


def beam_stress(l, h, y, E, end="free", kt=1.0):
    """Bending stress (MPa) at the root of a leaf of length l, thickness h, deflected y at its end: free end (a
    cantilever, tip load) 3 E h y / (2 l^2); guided end (a parallel-leaf flexure, each leaf fixed-guided) 3 E h y / l^2.
    Roark's Formulas for Stress and Strain (Young & Budynas, 7th ed.), Table 8.1 cases 1a and 1e. Times kt."""
    if end not in ("free", "guided"):
        raise ValueError("end=%r: 'free' (cantilever) or 'guided' (parallel leaf)" % end)
    return kt * (1.5 if end == "free" else 3.0) * E * h * y / l ** 2


def beam_angle(print_rot, d):
    """Angle (deg) of world direction d to the bed after print_rot (a 3x3 nested list): 0 = in the layer plane."""
    n = math.sqrt(sum(c * c for c in d)) or 1.0
    v = [sum(print_rot[i][j] * d[j] for j in range(3)) / n for i in range(3)]
    m = math.sqrt(sum(c * c for c in v)) or 1.0
    return math.degrees(math.asin(min(1.0, abs(v[2]) / m)))


def layer_stress_dir(kind, angle):
    """Whether the flexing member's tension crosses layers: 'along' (a beam or bar: its length should lie in the layer
    plane) crosses when it stands > 45 deg off the bed; 'normal' (a ring's axis: the hoop lies in the layers when the
    axis stands up) crosses when the axis is < 45 deg off the bed."""
    return angle > 45.0 if kind == "along" else angle < 45.0


SNAP_KINDS = ("snap_hook", "annular_snap", "torsion_snap")
PIP_KINDS = ("pip_hinge",)


def recheck(rec, material, print_rot=None, mu=None):
    """A manifest snap record re-evaluated for the part's material and (when known) print_rot. Returns strain, allow,
    allow_source, across, angle_deg, forces and result 'pass' / 'fail'. A torsion snap compares its shear strain
    with (1 + nu) x the allowable."""
    m = CM.MATERIALS[material]
    E, nu = m["E_mpa"], m["poisson"]
    mu = m["mu_self"] if mu is None else mu
    ang = beam_angle(print_rot, rec["beam_dir"]) if print_rot is not None else None
    across = ang is not None and layer_stress_dir(rec.get("beam_kind", "along"), ang)
    allow, src = allowable(material, rec.get("uses", "repeated"), across)
    k = rec["kind"]
    if k == "snap_hook":
        r = hook(rec["length"], rec["thickness"], rec["width"], rec["undercut"], E, rec.get("taper", 1.0), mu,
                 rec["entry_deg"], rec["retain_deg"])
        val, lim = r["strain"], allow
    elif k == "annular_snap":
        r = annular(rec["d"], rec["interference"], E, rec["hub_od"], nu, mu, rec["entry_deg"], rec["retain_deg"])
        val, lim = r["strain"], allow
    elif k == "torsion_snap":
        r = torsion(rec["bar_l"], rec["bar_d"], rec["lever"], rec["undercut"], E, nu, mu, rec["entry_deg"], rec["retain_deg"],
                    rec.get("bars", 2))
        val, lim = r["shear_strain"], (1 + nu) * allow
    else:
        raise ValueError("not a snap record: %r" % k)
    return dict(r, value=val, limit=lim, allow=allow, allow_source=src, across=across, angle_deg=ang, material=material,
                result="pass" if val <= lim * (1 + 1e-6) else "fail")
