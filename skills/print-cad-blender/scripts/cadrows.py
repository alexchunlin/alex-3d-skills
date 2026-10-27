"""cadrows: one line per row of a cadcheck.json or manifest.json, so you grep instead of writing a dump script.

    cad rows [cadcheck.json] [REGEX] [--check distances,drop] [--findings] [--max N]
    cad rows cadcheck.json --summary [REGEX]             # counts, coverage, not_checked, held poses, assembly.step_of
    cad rows manifest.json [REGEX]                       # parts, fasteners, cables, joints, mates, params
    cad rows checks.json [REGEX] [--check allow,stacks]  # config rows: allow, fits, distances, stacks, slide_out, ...

REGEX filters the printed lines (case-insensitive), e.g. `cad rows v2-A2`, `cad rows "hood.*flywheel"`,
`cad rows manifest.json FST_nip`. --findings prints the fails and warns with their accepted status instead of rows.

In 67 bash calls, the v2 A3 agents json.load()ed cadcheck.json, manifest.json or checks.json, and 6 of
them died on a guessed key: checks.distances.rows is a list, drop is tests[].rows[], manifest fasteners are parts
with kind FST (FINDINGS V2A3-T1). Plain python3, no Blender.
"""
import json, os, re, sys


def short(v, n=60):
    if isinstance(v, float):
        return "%g" % round(v, 3)
    if isinstance(v, dict):
        if all(not isinstance(x, (dict, list)) for x in v.values()) and len(v) <= 6:
            return "{" + ",".join("%s:%s" % (k, short(x)) for k, x in v.items()) + "}"
        if len(v) <= 3:
            return "{" + ",".join("%s:%s" % (k, short(x)) for k, x in v.items()) + "}"
        return "{%d keys}" % len(v)
    if isinstance(v, list):
        if len(v) <= 4 and all(not isinstance(x, (dict, list)) for x in v):
            return "[" + ",".join(short(x) for x in v) + "]"
        if len(v) <= 3 and all(isinstance(x, list) and len(x) <= 3 for x in v):
            return "[" + ",".join(short(x) for x in v) + "]"
        if all(isinstance(x, list) and len(x) == 3 and all(isinstance(c, (int, float)) for c in x) for x in v):
            # points (drop stall_points): the first few, so a stall is located without a dump script (v2 A5 launcher)
            return "[" + ",".join(short(x) for x in v[:3]) + (",... %d pts]" % len(v) if len(v) > 3 else "]")
        if all(isinstance(x, list) and len(x) == 2 and not isinstance(x[1], (dict, list)) for x in v):
            # a swept ray's profile [[deg, mm], ...]: print it, it is the point of the row
            return " ".join("%s:%s" % (short(x[0]), "-" if x[1] is None else short(x[1])) for x in v)
        return "[%d]" % len(v)
    s = str(v)
    return s if len(s) <= n else s[:n - 3] + "..."


LABEL_KEYS = ("name", "op", "object", "part", "test")
SKIP = {"why", "msg", "status", "region", "where", "thin_wall_where", "exposed_spots", "members", "terms", "access", "blocked", "bends"}


def row_line(check, r, extra=""):
    if "a" in r and "b" in r:
        label = "%s>%s" % (r["a"], r["b"])
    else:
        label = next((str(r[k]) for k in LABEL_KEYS if k in r), "")
    bits = []
    for k, v in r.items():
        if k in SKIP or k in ("a", "b") or (k in LABEL_KEYS and str(v) == label):
            continue
        if v is None or v == [] or v == {}:
            continue
        bits.append("%s=%s" % (k, short(v)))
    if isinstance(r.get("blocked"), dict):
        # insertion: the nearest blocker per direction (v2 A6 feeder group: "+Z:PRT_groove_cap(BUY_bus_junction)@3")
        bits.append("blocked=" + " ".join("%s:%s%s@%s" % (dn, b[0]["by"], "(%s)" % b[0]["mover"] if b[0].get("mover") not in (None, label) else "",
                                                          short(b[0]["at_mm"])) if b else "%s:-" % dn for dn, b in r["blocked"].items()))
    if isinstance(r.get("bends"), list) and r["bends"] and isinstance(r["bends"][0], dict):
        # cables.kinks: each corner, so the reviewer has the place and radius (v2 A7 bus leads at the splice, V2A7-F2)
        bits.append("bends=" + " ".join("%sdeg@%s:r%s" % (b["turn_deg"], short(b["at"]), short(b["radius_mm"])) for b in r["bends"]))
    if "access" in r and isinstance(r["access"], dict):
        bits.append("access=" + ",".join("%s:%s" % (pk, "BLOCKED" if a.get("blocked") else "%s %g" % (a.get("tool", "ok"), a.get("reach_mm", 0)))
                                         for pk, a in r["access"].items()))
    why = r.get("why")
    return "%-12s %s%s  %s%s" % (check, extra, label, "  ".join(bits), ("  | " + str(why)) if why else "")


def report_rows(d, checks):
    for check, sec in d.get("checks", {}).items():
        if checks and check not in checks:
            continue
        for key, val in sec.items():
            if key == "findings" or not isinstance(val, list):
                continue
            for r in val:
                if not isinstance(r, dict):
                    continue
                if isinstance(r.get("rows"), list):          # drop / payload tests: one line per pose row
                    for rr in r["rows"]:
                        yield row_line(check, rr, "%s: " % r.get("name", key))
                else:
                    yield row_line(check if key == "rows" else "%s.%s" % (check, key), r)


def report_findings(d, checks):
    acc = d.get("summary", {}).get("accepted_warns", {})
    for check, sec in d.get("checks", {}).items():
        if checks and check not in checks:
            continue
        for f in sec.get("findings", []):
            msg = "%s: %s" % (check, f.get("msg"))
            tag = f["status"].upper() if f["status"] == "fail" else ("warn(accepted)" if msg in acc else "warn")
            yield "%-15s %s" % (tag, msg)


def report_summary(d):
    """--summary: header, counts, coverage, not_checked and assembly.step_of, one line each. v2 A6's finish agents and
    reviewer read these with 8 json.load snippets (summary keys, coverage, step_of; FINDINGS V2A6-T4)."""
    s = d.get("summary", {})
    yield "report  tool=%s  generated=%s  blend=%s" % (d.get("tool"), d.get("generated"), d.get("blend"))
    yield "summary  pass=%s  fails=%s  warns=%s  untriaged=%s  accepted=%d  stale_accepts=%s  poses_past_limits=%d  runtime_s=%s" % (
        s.get("pass"), s.get("fails"), s.get("warns"), s.get("untriaged_warns"), len(s.get("accepted_warns") or {}),
        short(s.get("stale_accepts") or []), len(s.get("poses_past_limits") or []), s.get("runtime_s"))
    for k in ("unbounded_allows",):
        for x in sorted(s.get(k) or []):
            yield "%s  %s" % (k, x)
    for x in s.get("coverage") or d.get("coverage") or []:
        yield "coverage  %s" % x
    for x in s.get("not_checked") or d.get("not_checked") or []:
        yield "not_checked  %s" % x
    asm = d.get("assembly") or {}
    for j, x in sorted((asm.get("joint_drives") or {}).items()):
        yield "joint_drive  %s  %s (%s)" % (j, x.get("by"), x.get("from"))
    for h in asm.get("held_poses") or []:
        yield "held_pose  %s=%g at step %s  drive %s since step %s  powered=%s  pose_how=%s  | %s" % (
            h["joint"], h["value"], short(h["step"], 40), h["drive"], short(h["drive_step"], 30), h["powered"], h.get("pose_how"), h["why"])
    for n, st in sorted(asm.get("step_of", {}).items()):
        yield "step_of  %s  %s" % (n, st)


def manifest_rows(m):
    for n, p in sorted(m.get("joints", {}).items()):
        yield "joint  %s  %s" % (n, "  ".join("%s=%s" % (k, short(v)) for k, v in p.items()))
    for n, p in sorted(m.get("parts", {}).items()):
        yield "%-6s %s  %s" % (p.get("kind", "?"), n, "  ".join("%s=%s" % (k, short(v)) for k, v in p.items() if k not in ("kind",)))
    if m.get("mates"):
        from cadmates import mate_line
        for x in m["mates"]:
            yield "mate   " + mate_line(x)
    for k, v in sorted(m.get("params", {}).items()):
        yield "param  %s = %s" % (k, short(v, 120))


def config_rows(c, checks):
    """checks.json: one line per row of each list section (V2R5 read allow, slide_out, stacks and band rows with
    json.load snippets, FINDINGS V2A5-T4)."""
    for sec, val in c.items():
        if checks and sec not in checks:
            continue
        if isinstance(val, list):
            for r in val:
                yield row_line(sec, r) if isinstance(r, dict) else "%-12s %s" % (sec, short(r, 120))
        elif isinstance(val, dict) and sec not in ("_about",):
            yield "%-12s %s" % (sec, short(val, 200))
        elif not sec.startswith("_"):
            yield "%-12s %s" % (sec, short(val, 120))


def main(argv):
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    flags = {a for a in argv if a.startswith("--")}
    vals = {}
    pos = []
    it = iter(argv)
    for a in it:
        if a in ("--check", "--max"):
            vals[a] = next(it, "")
        elif not a.startswith("--"):
            pos.append(a)
    path = pos.pop(0) if pos and pos[0].endswith(".json") else "cadcheck.json"
    pat = re.compile(pos[0], re.I) if pos else None
    if not os.path.isfile(path):
        print("cadrows: no %s here (pass the report path)" % path)
        return 2
    with open(path) as f:
        d = json.load(f)
    checks = set(vals.get("--check", "").split(",")) - {""}
    if "units" in d and "parts" in d:
        lines = manifest_rows(d)
    elif "checks" not in d and "summary" not in d:
        lines = config_rows(d, checks)
    elif "--findings" in flags:
        lines = report_findings(d, checks)
    elif "--summary" in flags:
        lines = report_summary(d)
    else:
        lines = report_rows(d, checks)
    cap = int(vals.get("--max") or 400)
    n = 0
    for ln in lines:
        if pat and not pat.search(ln):
            continue
        n += 1
        if n <= cap:
            print(ln)
    if n > cap:
        print("... %d more lines (narrow with a REGEX or --check, or raise --max)" % (n - cap))
    if not n:
        print("cadrows: nothing matched")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
