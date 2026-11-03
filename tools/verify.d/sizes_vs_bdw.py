"""Drift check: features.SIZES / RULES (M3 overlay) and cadcheck stock_lengths vs bd_warehouse's ISO tables.

Usage: python3 -I sizes_vs_bdw.py ROOT [--data DIR] [--set M4.nut_af=6.8 ...] [--table]
Exit 1 when a disagreement is not on sizes_vs_bdw_exceptions.json, or an exception no longer fires (stale: the
row now agrees, or ours/theirs moved), or a data file's sha256 differs from SHA256SUMS, or the exceptions file is malformed.
features.py imports mathutils at module level, so SIZES, RULES and the M3 overlay are read with ast, not imported.
The overlay is not mirrored by hand: the keyword arguments of the `s.update(...)` call in size_rules() are evaluated,
and the check stops with a message if that call takes a form this evaluator does not know.
"""
import ast, csv, hashlib, json, os, sys

AF_TOL = 0.0       # nut across-flats: exact (ISO 4032 s is a nominal wrench size)
DIM_TOL = 0.04     # mm: other diameters and heights. The CSVs carry 2 decimals and our table 1, so any 0.05 step is a disagreement
EPS = 1e-9
VERDICTS = ("ours", "theirs", "pending-coupon", "pending-standard")


def parse(path):
    with open(path) as fh:
        return ast.parse(fh.read())


def conv(node):
    """literal_eval that also takes dict(k=v, ...) calls (SIZES rows are written that way)."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "dict" and not node.args:
        return {k.arg: conv(k.value) for k in node.keywords}
    if isinstance(node, ast.Dict):
        return {ast.literal_eval(k): conv(v) for k, v in zip(node.keys, node.values)}
    return ast.literal_eval(node)


def top_level_value(tree, name, path):
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets):
            return n.value
    raise SystemExit("no top-level %s in %s" % (name, path))


def dict_path(node, keys, path):
    """Walk nested dict literals by key path without evaluating the other (possibly non-literal) values."""
    for k in keys:
        if not isinstance(node, ast.Dict):
            raise SystemExit("%s: expected a dict literal before key %r" % (path, k))
        hit = [v for kk, v in zip(node.keys, node.values) if isinstance(kk, ast.Constant) and kk.value == k]
        if not hit:
            raise SystemExit("%s: key %r not found" % (path, k))
        node = hit[0]
    return node


def overlay_node(feat_tree, path):
    for fn in feat_tree.body:
        if isinstance(fn, ast.FunctionDef) and fn.name == "size_rules":
            for c in ast.walk(fn):
                if (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "update"
                        and getattr(c.func.value, "id", None) == "s"):
                    return c
    raise SystemExit("%s: size_rules() has no s.update(...) call; update sizes_vs_bdw.py" % path)


def eval_overlay(node, rules, row, path):
    """Values the overlay uses: constants, R["key"], s["key"][i], tuples of these."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(eval_overlay(e, rules, row, path) for e in node.elts)
    if isinstance(node, ast.Subscript):
        inner = node.value
        if isinstance(inner, ast.Name) and inner.id == "R" and isinstance(node.slice, ast.Constant):
            return rules[node.slice.value]
        if (isinstance(inner, ast.Subscript) and getattr(inner.value, "id", None) == "s"
                and isinstance(inner.slice, ast.Constant) and isinstance(node.slice, ast.Constant)):
            return row[inner.slice.value][node.slice.value]
    raise SystemExit("%s: size_rules() overlay uses %s, which sizes_vs_bdw.py cannot evaluate; teach eval_overlay"
                     % (path, ast.dump(node)[:80]))


def ours_table(root):
    feat = os.path.join(root, "skills/print-cad-blender/scripts/cadlib/features.py")
    cc = os.path.join(root, "skills/print-cad-blender/scripts/cadcheck.py")
    ftree, ctree = parse(feat), parse(cc)
    sizes = conv(top_level_value(ftree, "SIZES", feat))
    rules = conv(top_level_value(ftree, "RULES", feat))
    ours = {}
    for size, r in sizes.items():
        ours[size] = row = {k: v for k, v in r.items() if not isinstance(v, tuple)}
        for k, v in r.items():
            if isinstance(v, tuple):
                row[k + "_d"], row[k + "_h"] = v
    # the M3 overlay: evaluate the keyword arguments of size_rules()'s s.update(...), then flatten tuples like SIZES
    for kw in overlay_node(ftree, feat).keywords:
        v = eval_overlay(kw.value, rules, sizes["M3"], feat)
        if isinstance(v, tuple):
            ours["M3"][kw.arg + "_d"], ours["M3"][kw.arg + "_h"] = v
        else:
            ours["M3"][kw.arg] = v
    stock = ast.literal_eval(dict_path(top_level_value(ctree, "DEFAULTS", cc), ("fasteners", "stock_lengths"), cc))
    return ours, rules, stock


def load(data, name):
    with open(os.path.join(data, name + ".csv"), newline="") as fh:
        return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]


def check_hashes(data):
    """Compares our copy of the CSVs with SHA256SUMS. It cannot see upstream; see NOTICE for the upstream re-check."""
    bad = []
    with open(os.path.join(data, "SHA256SUMS")) as fh:
        for line in fh:
            digest, name = line.split()
            p = os.path.join(data, name)
            if not os.path.exists(p):
                bad.append(name)
                continue
            with open(p, "rb") as cf:
                if hashlib.sha256(cf.read()).hexdigest() != digest:
                    bad.append(name)
    return bad


def fmt(x):
    return x if isinstance(x, str) else "%g" % x


def compare(root, data, overrides):
    ours, rules, stock = ours_table(root)
    for size, field, value in overrides:
        ours[size][field] = value
    nuts, clearance = load(data, "hex_nut_parameters"), load(data, "clearance_hole_sizes")
    caps, pans = load(data, "socket_head_cap_parameters"), load(data, "pan_head_parameters")
    csks, heat = load(data, "countersunk_head_parameters"), load(data, "heatset_nut_parameters")
    taps = load(data, "tap_hole_sizes")
    nominal = {r["Screw_Type"]: r["Nominal_Sizes"] for r in load(data, "nominal_screw_lengths")}
    rows = []   # (id, ours, theirs, disagrees, source)

    def add(row_id, o, t, tol, src):
        rows.append((row_id, fmt(o), fmt(t), abs(o - t) > tol + EPS, src))

    def find(table, key):
        return next(r for r in table if r["Size"] == key)

    for size, o in sorted(ours.items()):
        key = "M%g-%g" % (o["d"], o["pitch"])
        nut = find(nuts, key)
        add(size + " nut_af", o["nut_af"], float(nut["iso4032:s"]), AF_TOL, "hex_nut iso4032:s")
        add(size + " nut_h", o["nut_h"], float(nut["iso4032:m"]), DIM_TOL, "hex_nut iso4032:m")
        add(size + " clear_d", o["clear_d"], float(find(clearance, "M%g" % o["d"])["Normal"]), DIM_TOL,
            "clearance Normal (ISO 273 medium)")
        add(size + " pilot_d", o["pilot_d"], float(find(taps, key)["Soft"]), DIM_TOL, "tap_hole_sizes Soft")
        cap = find(caps, key)
        add(size + " cap_d", o["cap_d"], float(cap["iso4762:dk"]), DIM_TOL, "iso4762:dk")
        add(size + " cap_h", o["cap_h"], float(cap["iso4762:k"]), DIM_TOL, "iso4762:k")
        pan = find(pans, key)
        add(size + " pan_d", o["pan_d"], float(pan["iso14583:dk"]), DIM_TOL, "iso14583:dk")
        add(size + " pan_h", o["pan_h"], float(pan["iso14583:k"]), DIM_TOL, "iso14583:k")
        csk = find(csks, key)
        add(size + " csk_d", o["csk_d"], float(csk["iso7046:dk"]), DIM_TOL, "iso7046:dk")
        add(size + " csk_h", o["csk_h"], float(csk["iso7046:k"]), DIM_TOL, "iso7046:k")
        # heat-set: Ruthex / CNC Kitchen rows of this size whose insert length matches ours; else every row of the size
        vendor = []
        for r in heat:
            if r["Size"].startswith("M%g-%g-" % (o["d"], o["pitch"])):
                for v in ("ruthex", "CNCKitchen"):
                    if r.get(v + ":dc"):
                        vendor.append(dict(m=float(r[v + ":m"]), dc=float(r[v + ":dc"]),
                                           wall=float(r[v + ":material_thickness"])))
        match = [r for r in vendor if abs(r["m"] - o["insert_len"]) < 0.05] or vendor
        lo, hi = min(r["dc"] for r in match), max(r["dc"] for r in match)
        rows.append((size + " insert_d", fmt(o["insert_d"]), fmt(lo) if lo == hi else "%g-%g" % (lo, hi),
                     not (lo - DIM_TOL - EPS <= o["insert_d"] <= hi + DIM_TOL + EPS),
                     "heatset ruthex/CNCKitchen dc, insert length %g" % o["insert_len"]))
        wall = max(r["wall"] for r in match)
        rows.append((size + " insert_wall", fmt(rules["min_wall"]) + " (axial only)", fmt(wall),
                     wall > rules["min_wall"] + EPS, "heatset material_thickness vs RULES min_wall"))
        # stock lengths (cadcheck DEFAULTS["fasteners"]["stock_lengths"])
        iso_lengths = set(float(x) for k in ("iso4762", "iso7046", "iso14583") for x in nominal[k].split(","))
        for length in stock["%g" % o["d"]]:
            rows.append(("%s stock_length %g" % (size, length), fmt(length),
                         "not a nominal length of ISO 4762/7046/14583", length not in iso_lengths,
                         "nominal_screw_lengths iso4762, iso7046, iso14583"))
    return rows


def load_exceptions(path):
    """{id: entry}; each entry has id, ours, theirs, verdict (one of VERDICTS) and why (text) or why_ref (key in "shared")."""
    with open(path) as fh:
        doc = json.load(fh)
    shared, out, problems = doc.get("shared", {}), {}, []
    for e in doc["exceptions"]:
        if e.get("verdict") not in VERDICTS:
            problems.append("exception %s: verdict %r not in %s" % (e.get("id"), e.get("verdict"), "|".join(VERDICTS)))
        if "why" not in e and e.get("why_ref") not in shared:
            problems.append("exception %s: needs why or a why_ref that is in shared" % e.get("id"))
        e["why"] = e.get("why") or shared.get(e.get("why_ref"), "")
        out[e["id"]] = e
    return out, problems


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
            size, field = k.split(".")
            overrides.append((size, field, float(v)))
            i += 2
        elif argv[i] == "--table":
            table = True
            i += 1
        else:
            raise SystemExit("bad arg " + argv[i])
    fail = 0
    for name in check_hashes(data):
        print("HASH %s: our copy no longer matches SHA256SUMS (edited or replaced here; this does not look at upstream, "
              "see NOTICE for the upstream re-check)" % name)
        fail += 1
    exc, problems = load_exceptions(os.path.join(here, "sizes_vs_bdw_exceptions.json"))
    for p in problems:
        print("EXCEPTIONS " + p)
        fail += 1
    rows = compare(root, data, overrides)
    seen = set()
    for row_id, o, t, disagrees, src in rows:
        if not disagrees:
            continue
        e = exc.get(row_id)
        if e and str(e["ours"]) == o and str(e["theirs"]) == t:
            seen.add(row_id)
            if table:
                print("| %s | %s | %s | %s | %s |" % (row_id, o, t, e["verdict"], e["why"]))
            continue
        print("DRIFT %s: ours %s, bd_warehouse %s (%s), not on the exceptions list" % (row_id, o, t, src))
        fail += 1
    for row_id, e in exc.items():
        if row_id not in seen:
            print("STALE exception %s: no longer a disagreement with ours %s / theirs %s (SIZES or CSV changed): "
                  "update or remove it" % (row_id, e["ours"], e["theirs"]))
            fail += 1
    print("compared %d values, %d excepted, %d problems" % (len(rows), len(seen), fail))
    return 1 if fail else 0


sys.exit(main(sys.argv))
