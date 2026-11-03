"""cadbom: check the BOM's fastener table against the model's manifest.json.

    cad bom BOM_AND_ASSEMBLY.md manifest.json [--json out.json]

Reads markdown table rows whose first cell is a screw spec ("M3 x 16 csk ST", "**M2.5 x 10 cap ST**") and that name
fasteners in backticks (`FST_hub_*`). For each row it compares the size, length, head and count with the manifest's
FST parts. It also lists modelled screws no row mentions, and lengths that aren't commonly stocked.

v2 A3's BOM listed the nip stud as "M3 x 20 hex head" while the model was M3_cap x 16, and listed an M3 x 9 self-tap;
the reviewer found both by hand and they cost a manufacturability point (FINDINGS V2A3-F5, F6). Plain python3.
Exit status 1 when a row disagrees with the model.
"""
import fnmatch, json, os, re, sys

# the one stock table: cadcheck's DEFAULTS fasteners.stock_lengths, read as a literal (cadcheck imports bpy, this does not);
# it had its own copy here with no M5 row, so an unstocked M5 length passed (issue #29)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cadcfg  # noqa: E402
STOCK = {float(k): v for k, v in cadcfg.literal(os.path.join(HERE, "cadcheck.py"), "DEFAULTS")["fasteners"]["stock_lengths"].items()}
HEADS = ("csk", "cap", "pan", "hex", "button")
SPEC = re.compile(r"M(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)", re.I)


def head_of(text):
    t = text.lower()
    return next((h for h in HEADS if h in t), None)


def expand(glob):
    """`FST_feedmount_0..3` -> FST_feedmount_[0-3]; `FST_fw_nut_0/1` -> two names."""
    m = re.match(r"(.*?)(\d+)\.\.(\d+)$", glob)
    if m:
        return [m.group(1) + str(i) for i in range(int(m.group(2)), int(m.group(3)) + 1)]
    m = re.match(r"(.*?)(\d+(?:/\d+)+)$", glob)
    if m:
        return [m.group(1) + i for i in m.group(2).split("/")]
    return [glob]


def main(argv):
    if len(argv) < 2 or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    bom, man = open(argv[0]).read().splitlines(), json.load(open(argv[1]))
    fst = {n: p for n, p in man["parts"].items() if p.get("kind") == "FST" and p.get("spec")}   # nuts have no spec
    rows, problems, seen = [], [], set()
    # a name a row lists exactly belongs to that row, not to another row's glob (`FST_pinion_*` vs `FST_pinion_ctr`)
    exact = set(re.findall(r"`(FST_[A-Za-z0-9_]+)`", "\n".join(l for l in bom if l.lstrip().startswith("|")))) & set(fst)
    for i, ln in enumerate(bom, 1):
        if not ln.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        m = SPEC.search(cells[0].replace("*", ""))
        globs = [g for c in cells[1:] for g in re.findall(r"`(FST_[^`]+)`", c)]
        if not m or not globs or "nut" in cells[0].lower():
            continue
        d, L, head = float(m.group(1)), float(m.group(2)), head_of(cells[0])
        qty = int(cells[1]) if cells[1].isdigit() else None
        names = sorted({n for g in globs for e in expand(g) for n in fst if fnmatch.fnmatch(n, e) and (n == e or n not in exact)})
        seen |= set(names)
        r = {"line": i, "bom": cells[0].replace("*", ""), "qty": qty, "globs": globs, "model": len(names), "issues": []}
        if not names:
            r["issues"].append("names no modelled screw")
        if qty is not None and names and qty != len(names):
            r["issues"].append("qty %d, model has %d" % (qty, len(names)))
        for n in names:
            p = fst[n]
            md = float(re.match(r"M(\d+(?:\.\d+)?)", p["spec"]).group(1)) if re.match(r"M\d", p["spec"]) else None
            ml = float(p.get("length") or 0)
            mh = head_of(p["spec"].replace("selftap_", ""))
            if md is not None and abs(md - d) > 0.05:
                r["issues"].append("%s is M%g in the model" % (n, md))
            if abs(ml - L) > 0.05:
                r["issues"].append("%s is %g long in the model (%s)" % (n, ml, p.get("part")))
            if head and mh and head != mh:
                r["issues"].append("%s has a %s head in the model (%s)" % (n, mh, p["spec"]))
        st = next((v for k, v in STOCK.items() if abs(k - d) < 0.05), None)
        if st and L not in st:
            r["issues"].append("M%g x %g is not a stock length" % (d, L))
        rows.append(r)
        if r["issues"]:
            problems.append(r)
    unlisted = sorted(set(fst) - seen)
    for r in rows:
        print("%s line %d: %-28s qty %-3s model %-3d %s" % ("BAD " if r["issues"] else "ok  ", r["line"], r["bom"][:28], r["qty"], r["model"],
                                                         "; ".join(r["issues"])))
    if unlisted:
        print("NOT IN BOM: %d modelled screws: %s" % (len(unlisted), ", ".join(unlisted[:12]) + (" ..." if len(unlisted) > 12 else "")))
    print("CADBOM %s: %d rows, %d disagree, %d modelled screws in no row" % ("FAIL" if problems else "PASS", len(rows), len(problems), len(unlisted)))
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w") as f:
            json.dump({"rows": rows, "unlisted": unlisted}, f, indent=1)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
