"""cadmates: one line per mate (what mates with what, how, which fastener, which fit), from manifest.json or a .blend.

    cad mates manifest.json [REGEX] [--connectors]     # plain python3, no Blender
    cad mates model.blend [REGEX] [--connectors]       # reads the scene's "cad_mates" through Blender

REGEX filters the printed lines (case-insensitive): `cad mates manifest.json servo`, `cad mates m.json "fastened.*M3"`.
--connectors adds one line per connector (world frame at home, pattern, hole) from the manifest.
Written by cadlib.mates.assemble().
"""
import json, os, re, sys


def g(v):
    return "%g" % round(float(v), 3)


def vec(v):
    return "(" + ",".join(g(c) for c in v) + ")"


def mate_line(m):
    b = m.get("b") or "-"
    bits = ["%-9s" % m["kind"], "%s > %s" % (m["a"], b)]
    if m.get("joint"):
        u = m.get("units", "deg")
        rng = "continuous" if m.get("continuous") else "%s..%s %s" % (g(m["lo"]), g(m["hi"]), u)
        bits.append("axis %s at %s  %s  home %s" % (m.get("axis"), vec(m.get("origin", (0, 0, 0))), rng, g(m.get("home", 0))))
        if m.get("piv_sign") == -1:
            bits.append("%s values are these negated (+ turns about %s)" % (m["joint"], "+" + m.get("axis", "?")[1:]))
    elif m.get("origin") and m.get("b"):
        bits.append("at %s z %s" % (vec(m["origin"]), vec(m.get("z", (0, 0, 1)))))
    if m.get("gap"):
        bits.append("gap %s%s" % (g(m["gap"]), " (designed)" if m.get("designed_gap") else ""))
    if m.get("rot"):
        bits.append("rot %s" % g(m["rot"]))
    pat = m.get("pattern_a")
    if pat and pat != "single" or m.get("pattern_b") not in (None, "single"):
        pb = m.get("pattern_b")
        bits.append("pattern %s%s" % (pat, "" if pb in (None, pat, "single") else " / " + pb))
    hole = m.get("hole_a") or m.get("hole_b")
    if hole:
        bits.append("hole %s" % hole)
    f = m.get("fastener")
    if f:
        ls = sorted(set(f.get("lengths") or []))
        names = f.get("names") or []
        nm = names[0] if len(names) == 1 else "%s..%s" % (names[0], names[-1].rsplit("_", 1)[-1]) if names else "-"
        bits.append("%dx %s %s %s%s%s: %s L%s" % (
            len(names), f.get("size"), f.get("style"), f.get("head"), " sink %s" % g(f["sink"]) if f.get("sink") else "",
            " head on %s" % f["head_on"] if f.get("head_on") else "", nm, "/".join(g(x) for x in ls)))
    if m.get("fit"):
        bits.append("fit %s" % m["fit"])
    if m.get("step"):
        bits.append("step %s" % m["step"])
    line = "%-14s %s" % (m["name"], "  ".join(bits))
    if m.get("warn"):
        line += "  WARN " + m["warn"]
    if m.get("note"):
        line += "  | " + m["note"]
    return line


def connector_lines(manifest):
    for n, p in sorted(manifest.get("parts", {}).items()):
        for c, f in sorted((p.get("connectors") or {}).items()):
            yield "connector  %s:%s  at %s  z %s  x %s%s%s%s" % (
                n, c, vec(f["origin"]), vec(f["z"]), vec(f["x"]),
                "" if f.get("pattern") in (None, "single") else "  pattern " + f["pattern"],
                "  hole %s" % f["hole"] if f.get("hole") else "", "  | " + f["note"] if f.get("note") else "")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    flags = {a for a in argv if a.startswith("--")}
    pos = [a for a in argv if not a.startswith("--")]
    src = pos.pop(0)
    pat = re.compile(pos[0], re.I) if pos else None
    d = json.load(sys.stdin if src == "-" else open(src))
    mates = d if isinstance(d, list) else d.get("mates")
    if mates is None:
        print("cadmates: %s has no mate table (built without cadlib.mates.assemble)" % src)
        return 1
    lines = [mate_line(m) for m in mates]
    if "--connectors" in flags and isinstance(d, dict):
        lines += list(connector_lines(d))
    n = 0
    for ln in lines:
        if pat is None or pat.search(ln):
            print(ln)
            n += 1
    if not n:
        print("cadmates: nothing matched")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
