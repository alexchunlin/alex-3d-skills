"""Drift check: features.SIZES / RULES (M3 overlay) and cadcheck stock_lengths vs bd_warehouse's ISO tables.

Usage: python3 -I sizes_vs_bdw.py ROOT [--data DIR] [--set M4.nut_af=6.8 ...] [--table]
Exit 1 when a disagreement is not on sizes_vs_bdw_exceptions.json, or an exception no longer fires (stale: the
row now agrees, or ours/theirs moved), or a data file's sha256 differs from SHA256SUMS.
features.py imports mathutils at module level, so SIZES and RULES are read with ast, not imported.
"""
import ast, csv, hashlib, json, os, sys

AF_TOL = 0.0       # nut across-flats: exact (ISO 4032 s is a nominal wrench size)
DIM_TOL = 0.05     # mm: other diameters and heights; the CSVs carry 2 decimals, our table 1
EPS = 1e-9


def conv(node):
    """literal_eval that also takes dict(k=v, ...) calls (SIZES rows are written that way)."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "dict" and not node.args:
        return {k.arg: conv(k.value) for k in node.keywords}
    if isinstance(node, ast.Dict):
        return {ast.literal_eval(k): conv(v) for k, v in zip(node.keys, node.values)}
    return ast.literal_eval(node)


def literal(path, name):
    tree = ast.parse(open(path).read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets):
            return conv(n.value)
    raise SystemExit("no top-level %s in %s" % (name, path))


def stock_lengths(path):
    for n in ast.walk(ast.parse(open(path).read())):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value == "stock_lengths":
                    return ast.literal_eval(v)
    raise SystemExit("no stock_lengths in %s" % path)


def ours_table(root):
    f = os.path.join(root, "skills/print-cad-blender/scripts/cadlib/features.py")
    S, R = literal(f, "SIZES"), literal(f, "RULES")
    t = {}
    for size, r in S.items():
        o = {k: v for k, v in r.items() if not isinstance(v, tuple)}
        for k, v in r.items():
            if isinstance(v, tuple):
                o[k + "_d"], o[k + "_h"] = v
        t[size] = o
    # the overlay size_rules() applies to M3 (features.py size_rules)
    t["M3"].update(clear_d=R["m3_clear_d"], pilot_d=R["m3_selftap_pilot_d"], tap_d=R["m3_tap_machine_d"],
                   nut_af=R["m3_nut_af"], nut_h=R["m3_nut_h"], insert_d=R["m3_insert_hole_d"],
                   insert_len=R["m3_insert_len"], cap_d=R["m3_head_d"], cap_h=R["m3_head_h"],
                   pan_d=R["m3_pan_head_d"], pan_h=R["m3_pan_head_h"], csk_d=R["m3_csk_head_d"])
    return t, R, stock_lengths(os.path.join(root, "skills/print-cad-blender/scripts/cadcheck.py"))


def load(data, name):
    with open(os.path.join(data, name + ".csv"), newline="") as fh:
        return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]


def check_hashes(data):
    bad = []
    for line in open(os.path.join(data, "SHA256SUMS")):
        h, f = line.split()
        p = os.path.join(data, f)
        if not os.path.exists(p) or hashlib.sha256(open(p, "rb").read()).hexdigest() != h:
            bad.append(f)
    return bad


def g(x):
    return x if isinstance(x, str) else "%g" % x


def compare(root, data, overrides):
    ours, R, stock = ours_table(root)
    for sz, k, v in overrides:
        ours[sz][k] = v
    nut, clr = load(data, "hex_nut_parameters"), load(data, "clearance_hole_sizes")
    cap, pan = load(data, "socket_head_cap_parameters"), load(data, "pan_head_parameters")
    csk, heat = load(data, "countersunk_head_parameters"), load(data, "heatset_nut_parameters")
    tap = load(data, "tap_hole_sizes")
    nom = {r["Screw_Type"]: r["Nominal_Sizes"] for r in load(data, "nominal_screw_lengths")}
    rows = []   # (id, ours, theirs, disagrees, source)

    def add(i, o, t, tol, src):
        rows.append((i, g(o), g(t), abs(o - t) > tol + EPS, src))

    def by(tab, key):
        return next(r for r in tab if r["Size"] == key)

    for sz, o in sorted(ours.items()):
        key = "M%g-%g" % (o["d"], o["pitch"])
        n = by(nut, key)
        add(sz + " nut_af", o["nut_af"], float(n["iso4032:s"]), AF_TOL, "hex_nut iso4032:s")
        add(sz + " nut_h", o["nut_h"], float(n["iso4032:m"]), DIM_TOL, "hex_nut iso4032:m")
        add(sz + " clear_d", o["clear_d"], float(by(clr, "M%g" % o["d"])["Normal"]), DIM_TOL, "clearance Normal (ISO 273 medium)")
        add(sz + " pilot_d", o["pilot_d"], float(by(tap, key)["Soft"]), DIM_TOL, "tap_hole_sizes Soft")
        c = by(cap, key)
        add(sz + " cap_d", o["cap_d"], float(c["iso4762:dk"]), DIM_TOL, "iso4762:dk")
        add(sz + " cap_h", o["cap_h"], float(c["iso4762:k"]), DIM_TOL, "iso4762:k")
        p = by(pan, key)
        add(sz + " pan_d", o["pan_d"], float(p["iso14583:dk"]), DIM_TOL, "iso14583:dk")
        add(sz + " pan_h", o["pan_h"], float(p["iso14583:k"]), DIM_TOL, "iso14583:k")
        s7 = by(csk, key)
        add(sz + " csk_d", o["csk_d"], float(s7["iso7046:dk"]), DIM_TOL, "iso7046:dk")
        add(sz + " csk_h", o["csk_h"], float(s7["iso7046:k"]), DIM_TOL, "iso7046:k")
        # heat-set: Ruthex / CNC Kitchen rows of this size whose insert length matches ours; else every row of the size
        vend = []
        for r in heat:
            if r["Size"].startswith("M%g-%g-" % (o["d"], o["pitch"])):
                for v in ("ruthex", "CNCKitchen"):
                    if r.get(v + ":dc"):
                        vend.append(dict(m=float(r[v + ":m"]), dc=float(r[v + ":dc"]), wall=float(r[v + ":material_thickness"])))
        match = [r for r in vend if abs(r["m"] - o["insert_len"]) < 0.05] or vend
        lo, hi = min(r["dc"] for r in match), max(r["dc"] for r in match)
        rows.append((sz + " insert_d", g(o["insert_d"]), g(lo) if lo == hi else "%g-%g" % (lo, hi),
                     not (lo - DIM_TOL - EPS <= o["insert_d"] <= hi + DIM_TOL + EPS),
                     "heatset ruthex/CNCKitchen dc, insert length %g" % o["insert_len"]))
        wall = max(r["wall"] for r in match)
        rows.append((sz + " insert_wall", g(R["min_wall"]) + " (axial only)", g(wall), wall > R["min_wall"] + EPS,
                     "heatset material_thickness vs RULES min_wall"))
        # stock lengths (cadcheck DEFAULTS fasteners.stock_lengths)
        ok_len = set(float(x) for k in ("iso4762", "iso7046", "iso14583") for x in nom[k].split(","))
        for L in stock["%g" % o["d"]]:
            rows.append(("%s stock_length %g" % (sz, L), g(L), "not a nominal length of ISO 4762/7046/14583", L not in ok_len,
                         "nominal_screw_lengths iso4762, iso7046, iso14583"))
    return rows


def main(argv):
    root, overrides, table = argv[1], [], False
    here = os.path.dirname(os.path.abspath(__file__))
    data = os.path.join(root, "tools/prior_art/bd_warehouse_data")
    i = 2
    while i < len(argv):
        if argv[i] == "--data":
            data = argv[i + 1]
            i += 2
        elif argv[i] == "--set":
            k, v = argv[i + 1].split("=")
            sz, f = k.split(".")
            overrides.append((sz, f, float(v)))
            i += 2
        elif argv[i] == "--table":
            table = True
            i += 1
        else:
            raise SystemExit("bad arg " + argv[i])
    fail = 0
    for f in check_hashes(data):
        print("HASH %s differs from SHA256SUMS (upstream drift or edit; the copy must stay unchanged)" % f)
        fail += 1
    exc = {e["id"]: e for e in json.load(open(os.path.join(here, "sizes_vs_bdw_exceptions.json")))}
    rows = compare(root, data, overrides)
    seen = set()
    for i_, o, t, dis, src in rows:
        if not dis:
            continue
        e = exc.get(i_)
        if e and str(e["ours"]) == o and str(e["theirs"]) == t:
            seen.add(i_)
            if table:
                print("| %s | %s | %s | %s | %s |" % (i_, o, t, e["verdict"], e["reason"]))
            continue
        print("DRIFT %s: ours %s, bd_warehouse %s (%s), not on the exceptions list" % (i_, o, t, src))
        fail += 1
    for i_, e in exc.items():
        if i_ not in seen:
            print("STALE exception %s: no longer a disagreement with ours %s / theirs %s (SIZES or CSV changed): update or remove it"
                  % (i_, e["ours"], e["theirs"]))
            fail += 1
    print("compared %d values, %d excepted, %d problems" % (len(rows), len(seen), fail))
    return 1 if fail else 0


sys.exit(main(sys.argv))
