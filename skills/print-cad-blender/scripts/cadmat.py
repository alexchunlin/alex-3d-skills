"""cadmat: printed-material allowables, per-part print settings, printed-section properties and checks.json calcs.
Plain python3, no Blender: cadcheck (the calcs check), cadlib.asm and cadlib.export import it, and so can a project.

    MATERIALS["PLA"]["across_mpa"]                    allowables, each number with its source (reference/materials.md)
    print_settings(info)                              a part's declared settings with the defaults filled in
    section(b, h, walls=2, infill=15, ...)            effective I and Z of a printed b x h rectangle
    run_calcs(rows, params, parts)                    evaluate checks.json "calcs" rows in order

Why: push-assist agents folded stress calcs into `stacks` rows ("worst case / RSS" of a stress, abs() hiding the sign,
PA-A6-T9), set their own limits per row (20 / 10 / 15 MPa against the reviewer's 25, PA-A6-T10), and for 8 rounds
computed stress on solid sections while the 3MFs carried no slicer settings, so the parts would print at the slicer's
2 walls and 15 % (PA-A8-T13).
"""
import math

# Allowables. Strengths are tensile values (MPa); "in" is along the layers (X-Y), "across" pulls layers apart (Z).
# Design allowables are strength / SF (SF = 2, static load: our assumption, stated). Every number has its source in
# SOURCES. They were entered without network access from the documents named there, as recalled: check each against
# the current TDS before relying on its last digit (reference/materials.md says the same).
SF = 2.0
_TABLE = {   # key: (value, source)
    "PLA": {
        "density": (1.24e-3, "g/mm3; Prusament PLA TDS and Bambu PLA Basic TDS: 1.24 g/cm3 (= cadcheck pla_density)"),
        "E_mpa": (2200, "Prusament PLA TDS: tensile modulus 2.2 GPa (ISO 527); Bambu PLA Basic's TDS gives about 2.75"),
        "tensile_in_mpa": (35, "Bambu PLA Basic TDS: tensile strength X-Y about 35 MPa, as recalled (check the TDS); the "
                               "lower of the two vendors, so the allowable holds for either: Prusament PLA TDS gives a "
                               "57 MPa tensile yield strength (ISO 527)"),
        "tensile_across_mpa": (30, "working figure, no TDS number: push-assist reviewers took PLA across layers as 20-30 "
                                   "MPa ('25 MPa = PLA tensile across layers'); 30 / SF 2 = 15, R3's interlayer_mpa"),
        "flex_in_mpa": (76, "Bambu PLA Basic TDS: bending strength 76 MPa (X-Y), the figure push-assist PA-R8 used"),
        "yield_strain": (0.033, "Prusament PLA TDS: elongation at yield 3.3 %"),
        "poisson": (0.35, "assumption: 0.33-0.36 is the range quoted for PLA; no TDS gives it (cadsnap: annular, torsion)"),
        "mu_self": (0.5, "assumption: no published PLA-on-PLA value at hand; Bayer's snap-fit guide lists 0.5-0.7 for "
                         "PC on PC and 0.3-0.4 for POM on POM, as recalled (cadsnap mating forces)"),
    },
    "PETG": {
        "density": (1.27e-3, "g/mm3; Prusament PETG TDS: 1.27 g/cm3"),
        "E_mpa": (1500, "Prusament PETG TDS: tensile modulus 1.5 GPa (ISO 527)"),
        "tensile_in_mpa": (47, "Prusament PETG TDS: tensile yield strength 47 MPa (ISO 527)"),
        "tensile_across_mpa": (30, "working figure, no TDS number: taken equal to PLA's 30 until a Z-direction TDS "
                                   "value is entered"),
        "flex_in_mpa": (None, "not entered"),
        "yield_strain": (0.049, "Prusament PETG TDS: elongation at yield 4.9 %"),
        "poisson": (0.38, "assumption: about 0.38 is quoted for PET/PETG; no TDS gives it"),
        "mu_self": (0.5, "assumption, as PLA's (no value at hand)"),
    },
}
MATERIALS = {m: {k: v for k, (v, _) in t.items()} for m, t in _TABLE.items()}
SOURCES = {m: {k: s for k, (_, s) in t.items()} for m, t in _TABLE.items()}
for _n, _m in MATERIALS.items():
    _m["in_mpa"] = _m["tensile_in_mpa"] / SF                  # allowable bending or tension along the layers
    _m["across_mpa"] = _m["tensile_across_mpa"] / SF          # allowable stress that pulls layers apart
    # snap arms and flexures that cycle: half the yield strain. The Bayer snap-fit guide keeps the permissible strain
    # well under yield, and about 60 % of the one-time value for frequent separation; half of yield is our assumption
    _m["snap_strain"] = _m["yield_strain"] / 2
    SOURCES[_n].update(in_mpa="tensile_in_mpa / SF", across_mpa="tensile_across_mpa / SF",
                       snap_strain="yield_strain / 2 (assumption, Bayer snap-fit guide)")

# What an unset key prints at: the slicer's process preset. A Bambu Studio 2.5 project file (X1C preset) has wall_loops 2,
# sparse_infill_density 15 %, line_width 0.42, bottom_shell_layers 3, top 4; the vendored slicers/profiles/
# prusa_p1s_pla.ini has perimeters 2, fill_density 15 %. 0.2 mm layers: the P1S standard profile.
PRINT_DEFAULTS = {"material": "PLA", "walls": 2, "infill": 15, "layer_h": 0.2, "line_w": 0.42, "shells": 3}
PRINT_KEYS = tuple(PRINT_DEFAULTS)
SPEC_KEYS = ("material", "walls", "infill")   # a load-path part's print spec (cad-design-review checklist, PA-A8-T13)
# per-object keys in a Bambu Studio / OrcaSlicer 3MF (Metadata/model_settings.config), same names as their presets
SLICER_KEYS = {"walls": ("wall_loops", "%d"), "infill": ("sparse_infill_density", "%g%%"),
               "layer_h": ("layer_height", "%g"), "line_w": ("line_width", "%g"),
               "shells": (("top_shell_layers", "bottom_shell_layers"), "%d")}


def print_problems(info):
    """Messages for print settings asm.part should refuse: a material not in the table, walls/shells not a whole
    number >= 1, infill outside 0-100, a non-positive layer height or line width. None counts as not given."""
    out, g = [], {k: v for k, v in info.items() if k in PRINT_KEYS and v is not None}
    if "material" in g and g["material"] not in MATERIALS:
        out.append("material %r is not in cadmat.MATERIALS (%s)" % (g["material"], ", ".join(MATERIALS)))
    for k in ("walls", "shells"):
        if k in g and (isinstance(g[k], bool) or not isinstance(g[k], (int, float)) or g[k] != int(g[k]) or g[k] < 1):
            out.append("%s=%r: a whole number >= 1" % (k, g[k]))
    if "infill" in g and not (isinstance(g["infill"], (int, float)) and 0 <= g["infill"] <= 100):
        out.append("infill=%r: percent, 0-100" % (g["infill"],))
    for k in ("layer_h", "line_w"):
        if k in g and not (isinstance(g[k], (int, float)) and g[k] > 0):
            out.append("%s=%r: mm, > 0" % (k, g[k]))
    return out


def print_settings(info):
    """The settings a part prints with: its declared ones, PRINT_DEFAULTS for the rest, and "defaulted" listing
    which keys came from the defaults (a load-path part should have none of SPEC_KEYS there, PA-A8-T13)."""
    out = {k: v if info.get(k) is None else info[k] for k, v in PRINT_DEFAULTS.items()}
    out["defaulted"] = [k for k in PRINT_KEYS if info.get(k) is None]
    return out


def section(b, h, walls=2, infill=15, line_w=0.42, shells=3, layer_h=0.2, t=None):
    """Effective bending properties of a printed b x h rectangle (h along the load, mm): a solid shell of thickness
    t = min(walls x line_w, shells x layer_h) on all four sides, and the core filled at `infill` % counted at
    (infill / 100)^2 of solid stiffness (Gibson & Ashby, Cellular Solids, 2nd ed. 1997: a bending-dominated cellular
    solid's relative modulus ~ relative density squared). Returns I, I_solid, Z = I / (h / 2) (stress in the shell is
    M / Z: the core is the softer material of a transformed section), t, k (the core's stiffness fraction) and ratio
    = I / I_solid. Ignores holes, stress raisers, the anisotropy (use "in" or "across" allowables) and the wall-to-infill
    bond. With infill 100, or a section no wider than two shells, it is the solid section. t= sets the shell directly
    (a section whose four faces are all walls, e.g. a beam standing up: t = walls x line_w)."""
    t = min(walls * line_w, shells * layer_h) if t is None else t
    I_solid = b * h ** 3 / 12.0
    k = (min(max(infill, 0.0), 100.0) / 100.0) ** 2
    bi, hi = b - 2 * t, h - 2 * t
    I = I_solid if bi <= 0 or hi <= 0 else I_solid - bi * hi ** 3 / 12.0 * (1.0 - k)
    return {"I": I, "I_solid": I_solid, "Z": I / (h / 2.0), "t": t, "k": k, "ratio": I / I_solid}


# ------------------------------------------------------------------ calcs

# what every "=expr" in checks.json sees besides the params (cadcheck's _eval_exprs uses it too)
BASE_ENV = {"__builtins__": {}, "min": min, "max": max, "abs": abs, "round": round, "sqrt": math.sqrt, "math": math,
            "pi": math.pi}
SECTION_KEYS = ("walls", "infill", "line_w", "shells", "layer_h", "t")   # what section/i_eff/z_eff take by keyword

def calc_env(params, parts, used):
    """The names a calc's "=expr" sees: the params, math, and the helpers below. `parts`: {PRT_name: its declared
    print settings}; `used` collects the parts a helper read, for the defaults note."""
    def settings(part, over, reads):
        bad = sorted(set(over) - set(SECTION_KEYS))
        if bad:
            raise TypeError("unknown keyword %s (known: %s)" % (", ".join(bad), ", ".join(SECTION_KEYS)))
        if part is not None and part not in parts:
            raise NameError("part %r is not a printed part in the model" % part)
        s = print_settings(parts.get(part, {}))
        if part is not None:      # the spec keys this helper read from the defaults (not those given by keyword)
            u = used.setdefault(part, [])
            u += [k for k in s["defaulted"] if k in reads and over.get(k) is None and k not in u]
            u.sort(key=SPEC_KEYS.index)
        s.update({k: v for k, v in over.items() if v is not None})
        return s

    def mat(name, key):
        """mat("PLA", "across_mpa"), or mat("PRT_leaf", "in_mpa") for that part's material."""
        m = settings(name, {}, ("material",))["material"] if str(name).startswith("PRT_") else name
        if m not in MATERIALS:
            raise KeyError("material %r is not in cadmat.MATERIALS" % m)
        return MATERIALS[m][key]

    def sect(b, h, part=None, **over):
        s = settings(part, over, ("walls", "infill"))
        return section(b, h, s["walls"], s["infill"], s["line_w"], s["shells"], s["layer_h"], s.get("t"))

    return dict(BASE_ENV, mat=mat, section=sect, i_eff=lambda b, h, part=None, **o: sect(b, h, part, **o)["I"],
                z_eff=lambda b, h, part=None, **o: sect(b, h, part, **o)["Z"])


def _eval(x, env, names):
    if isinstance(x, str) and x.startswith("="):
        return eval(x[1:], env, names)
    return x


def run_calcs(rows, params, parts):
    """Evaluate "calcs" rows in order. A row: {"name", "value": "=expr", "min", "max", "unit", "why"}; min and max
    may be expressions too. A calc whose name is an identifier is a name for the calcs after it. Returns one record
    per row: name, value, unit, min, max, result ("pass", "fail" or "info" with no bound), expr, parts (the
    printed parts its helpers read, each with the SPEC_KEYS it left at the defaults), index and why; or "error" for a
    failed expression, a value that is None or not finite, or a name that clashes with a param, an earlier calc or a
    helper (the row is skipped and later calcs that name it fail too)."""
    names, out = dict(params), []
    helpers = set(calc_env({}, {}, {}))
    for i, r in enumerate(rows):
        r = r if isinstance(r, dict) else {"value": r}
        used = {}
        env = calc_env(params, parts, used)
        rec = {"name": r.get("name") or "calcs[%d]" % i, "unit": r.get("unit"), "expr": r.get("value")}
        try:
            n = r.get("name")
            if isinstance(n, str) and n in helpers | set(names):
                # {"name": "LOAD", "value": "=LOAD * 0.1"} shadowed the param for every calc below it
                raise NameError("name %r is already %s; rename the calc" % (
                    n, "a helper" if n in helpers else "a param" if n in params else "an earlier calc"))
            if "value" not in r:
                raise KeyError("no \"value\"")
            vals = {}
            for k in ("value", "min", "max"):
                v = _eval(r.get(k), env, names)
                if v is None and k == "value":
                    raise ValueError("value is None")      # mat('PETG', 'flex_in_mpa'), "value": null
                if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
                    raise TypeError("%s is %r, not a number" % (k, v))
                if v is not None and not math.isfinite(v):
                    raise ValueError("%s is %r, not finite" % (k, v))   # NaN passed every bound
                vals[k] = v
        except Exception as e:
            rec["error"] = "%s: %s" % (type(e).__name__, e)
            out.append(dict(rec, index=i, why=r.get("why")))
            continue
        v, lo, hi = vals["value"], vals["min"], vals["max"]
        rec = {"name": rec["name"], "value": v, "unit": rec["unit"], "min": lo, "max": hi,
               "result": "info" if lo is None and hi is None else
               "fail" if (lo is not None and v < lo - 1e-9) or (hi is not None and v > hi + 1e-9) else "pass",
               "expr": rec["expr"], "parts": used}
        if isinstance(r.get("name"), str) and r["name"].isidentifier():
            names[r["name"]] = v
        out.append(dict(rec, index=i, why=r.get("why")))
    return out


def stack_calcs(stacks):
    """Indexes of `stacks` rows that are calcs in disguise: one term whose tol is an "=expr" and no "between"
    (push-assist PA-A6-T9: 22 stacks rows, the cradle ones a stress, tilt or stroke with one =expr term)."""
    return [i for i, s in enumerate(stacks or []) if isinstance(s, dict) and not s.get("between")
            and len(s.get("terms") or []) == 1 and isinstance(s["terms"][0], dict)
            and str(s["terms"][0].get("tol", "")).startswith("=")]
