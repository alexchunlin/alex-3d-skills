"""cadmat without Blender: python3 -I calcs_materials_cases.py ROOT. Prints PASS/FAIL lines.

The printed section (I_eff under solid I for a 2-wall 20 % part; solid at 100 % infill, the negative control), the
allowables table (a source for every number; interlayer_mpa = PLA across-layer allowable), calcs in order (a calc
failing its max, a failed expression and the calc naming it, a non-number), the defaults note, the unknown-key warn on
a calcs row, and the one-term =expr stacks rows that are calcs (PA-A6-T9) with a real two-term stack as control.
"""
import os, sys

ROOT = sys.argv[1]
S = os.path.join(ROOT, "skills/print-cad-blender/scripts")
sys.path.insert(0, S)
import cadmat as M  # noqa: E402
import cadcfg as C  # noqa: E402


def want(name, cond, detail=""):
    print("%s cadmat: %s%s" % ("PASS" if cond else "FAIL", name, "" if cond or not detail else " (%s)" % detail))


# section: PA-A8-T13, stress rows on solid sections
s = M.section(10, 4, walls=2, infill=20)
want("I_eff of a 10 x 4 section, 2 walls 20 %% infill, is under solid I (%.1f of %.1f mm4, ratio %.2f)" % (s["I"], s["I_solid"], s["ratio"]),
     s["I"] < s["I_solid"] and 0.5 < s["ratio"] < 0.95 and abs(s["I_solid"] - 10 * 4 ** 3 / 12) < 1e-9)
b = M.section(10, 10, walls=2, infill=20)
want("a deeper section loses more (10 x 10: ratio %.2f < %.2f)" % (b["ratio"], s["ratio"]), b["ratio"] < s["ratio"])
want("Z = I / (h / 2), and the shell is min(walls x line_w, shells x layer_h) = 0.6 mm by default",
     abs(s["Z"] - s["I"] / 2) < 1e-9 and abs(s["t"] - 0.6) < 1e-9 and abs(M.section(10, 4, walls=1)["t"] - 0.42) < 1e-9)
want("more walls or more infill never lowers I", M.section(10, 10, walls=4, shells=6)["I"] >= b["I"] and M.section(10, 10, infill=60)["I"] >= M.section(10, 10, infill=20)["I"])
want("negative control: 100 % infill is the solid section, and so is one no wider than two shells",
     abs(M.section(10, 10, infill=100)["ratio"] - 1) < 1e-12 and M.section(1.0, 4)["ratio"] == 1.0)

# the table
nums = [(m, k) for m, t in M.MATERIALS.items() for k, v in t.items() if isinstance(v, (int, float))]
nosrc = [(m, k) for m, k in nums if not M.SOURCES.get(m, {}).get(k)]
want("every number in MATERIALS has a source (%d numbers)" % len(nums), not nosrc, nosrc)
D = C.literal(os.path.join(S, "cadcheck.py"), "DEFAULTS")
want("cadcheck interlayer_mpa (%g) is the PLA across-layer allowable (%g)" % (D["interlayer_mpa"], M.MATERIALS["PLA"]["across_mpa"]),
     D["interlayer_mpa"] == M.MATERIALS["PLA"]["across_mpa"])
want("cadcheck pla_density is the table's PLA density", D["pla_density"] == M.MATERIALS["PLA"]["density"])
want("print_problems refuses ABS, 2.5 walls, 120 % infill and accepts a good spec",
     len(M.print_problems({"material": "ABS", "walls": 2.5, "infill": 120})) == 3 and not M.print_problems({"material": "PETG", "walls": 3, "infill": 40, "layer_h": 0.16}))

# calcs
parts = {"PRT_leaf": {"material": "PETG", "walls": 3, "infill": 40}, "PRT_base": {}}
rows = [{"name": "F", "value": "=LOAD * 1.5", "unit": "N"},
        {"name": "leaf_mpa", "value": "=F * ARM / z_eff(B, H, part='PRT_leaf')", "max": "=mat('PRT_leaf', 'in_mpa')", "unit": "MPa"},
        {"name": "base_mpa", "value": "=F * ARM / z_eff(40, 10, part='PRT_base')", "max": "=mat('PRT_base', 'in_mpa')"},
        {"name": "broken", "value": "=NOPE * 2"},
        {"name": "uses_broken", "value": "=broken + 1"},
        {"name": "not_a_number", "value": "='12'"},
        {"name": "low", "value": 3, "min": 5},
        {"name": "solid_mpa", "value": "=F * ARM / (B * H ** 2 / 6)", "max": 1000}]
r = {x["name"]: x for x in M.run_calcs(rows, {"LOAD": 50.0, "ARM": 20.0, "B": 10.0, "H": 4.0}, parts)}
want_leaf = 75.0 * 20 / M.section(10, 4, walls=3, infill=40)["Z"]
want("a calc over an earlier calc and the part's printed section fails its max from the part's material (%.1f MPa > %g, PETG in-layer)" % (
    r["leaf_mpa"]["value"], r["leaf_mpa"]["max"]),
     r["leaf_mpa"]["result"] == "fail" and abs(r["leaf_mpa"]["value"] - want_leaf) < 1e-9 and r["leaf_mpa"]["max"] == M.MATERIALS["PETG"]["in_mpa"])
want("the printed-section stress is above the solid-section one (%.1f vs %.1f MPa)" % (r["leaf_mpa"]["value"], r["solid_mpa"]["value"]),
     r["leaf_mpa"]["value"] > r["solid_mpa"]["value"] and r["solid_mpa"]["result"] == "pass")
want("negative control: a calc within its max passes", r["base_mpa"]["result"] == "pass" and r["F"]["result"] == "info")
want("a calc under its min fails", r["low"]["result"] == "fail")
want("the defaults note names what a part left unset (PRT_base: material, walls, infill; PRT_leaf: nothing)",
     r["base_mpa"]["parts"] == {"PRT_base": ["material", "walls", "infill"]} and r["leaf_mpa"]["parts"] == {"PRT_leaf": []})
want("a failed expression is an error, and so is the calc that names it",
     "NameError" in r["broken"].get("error", "") and "'broken'" in r["uses_broken"].get("error", "") and "value" not in r["broken"])
want("a value that is not a number is an error", "not a number" in r["not_a_number"].get("error", ""))
bad_part = M.run_calcs([{"name": "x", "value": "=i_eff(1, 1, part='PRT_none')"}], {}, parts)[0]
want("a part that is not in the model is an error, not the defaults", "PRT_none" in bad_part.get("error", ""))

# schema: an unknown key on a calcs row warns with the closest key
R, N = C.literal(os.path.join(S, "cadcheck.py"), "CONFIG_ROWS"), C.literal(os.path.join(S, "cadcheck.py"), "CONFIG_NAMED")
u = C.unknown_keys({"calcs": [{"name": "x", "value": 1, "maxx": 2, "unit": "MPa", "why": "w"}]}, D, R, N)
want("an unknown key on a calcs row warns with the closest key", u == [("calcs[0] (x)", "maxx", "max")], u)
want("negative control: a full calcs row has no unknown key",
     not C.unknown_keys({"calcs": [{"name": "x", "value": "=1", "min": 0, "max": 2, "unit": "MPa", "why": "w"}]}, D, R, N))

# stacks rows that are calcs
st = [{"name": "stress as a stack", "limit": 15, "terms": [{"what": "sigma", "tol": "=cradle_mpa"}]},
      {"name": "real stack", "limit": 0.3, "terms": [{"what": "a", "tol": 0.2}, {"what": "b", "tol": "=T"}]},
      {"name": "one literal term", "limit": 0.3, "terms": [{"what": "a", "tol": 0.2}]},
      {"name": "measured", "between": ["A", "B"], "terms": [{"what": "a", "tol": "=T"}]}]
want("a one-term =expr stack is flagged as a calc; two terms, a literal term and a measured stack are not", M.stack_calcs(st) == [0], M.stack_calcs(st))
