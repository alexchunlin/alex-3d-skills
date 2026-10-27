"""Score one mates_task design: cadcheck fails, interfaces off by more than 0.2 mm or 1 deg, lines of build code.

    python3 -I tools/bench/mates_task/score.py <project> [--out score.json] [--skill <print-cad-blender>] [--kit DIR]

--kit picks another kit folder with the same files (checks.json, interfaces.json, kit_parts.py): mates_task_v2 runs
this scorer that way.

<project> holds blender/model.blend (built by the designer), blender/checks.json and the build's .py files. Runs
`cad check` with this kit's checks.json as an overlay, then measure_blend.py in Blender. Plain python3; BLENDER
overrides the Blender binary. Exit 0 when it scored (whatever the score), 2 when it could not.
"""
import json, os, subprocess, sys

KIT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))


def loc(blender_dir):
    """Non-blank, non-comment lines of the build's Python (docstrings count: they are written too)."""
    out = {}
    for dp, dn, fn in os.walk(blender_dir):
        dn[:] = [d for d in dn if d not in ("__pycache__", "stl", "renders")]
        for f in fn:
            if f.endswith(".py"):
                p = os.path.join(dp, f)
                n = sum(1 for ln in open(p, errors="replace") if ln.strip() and not ln.strip().startswith("#"))
                out[os.path.relpath(p, blender_dir)] = n
    return out


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    global KIT
    if "--kit" in argv:
        KIT = os.path.abspath(argv[argv.index("--kit") + 1])
    proj = os.path.abspath(argv[0])
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(proj, os.path.basename(KIT) + "_score.json")
    skill = argv[argv.index("--skill") + 1] if "--skill" in argv else os.path.join(ROOT, "skills", "print-cad-blender")
    cad = os.path.join(skill, "scripts", "cad")
    bdir = os.path.join(proj, "blender")
    blend = os.path.join(bdir, "model.blend")
    if not os.path.isfile(blend):
        print("score: no %s (build it first)" % blend)
        return 2
    work = os.path.join(os.path.dirname(out) or ".", os.path.basename(KIT) + "_work")
    os.makedirs(work, exist_ok=True)
    cc = os.path.join(work, "cadcheck.json")
    cfg = os.path.join(bdir, "checks.json")
    cmd = [cad, "check", blend] + ([cfg] if os.path.isfile(cfg) else []) + [cc, "--overlay", os.path.join(KIT, "checks.json")]
    if not os.path.isfile(cfg):   # no designer config: the kit rows alone
        cmd = [cad, "check", blend, os.path.join(KIT, "checks.json"), cc]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        s = json.load(open(cc))["summary"]
    except Exception as e:
        print("score: cad check wrote no report (%s)" % e)
        return 2
    bl = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
    mj = os.path.join(work, "measure.json")
    r = subprocess.run([bl, "-b", blend, "--factory-startup", "--python-exit-code", "1", "--python",
                        os.path.join(os.path.dirname(os.path.abspath(__file__)), "measure_blend.py"), "--", os.path.join(skill, "scripts"), KIT, mj],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode or not os.path.isfile(mj):
        print("score: measure_blend.py failed:\n" + r.stdout[-2000:])
        return 2
    m = json.load(open(mj))
    lines = loc(bdir)
    res = {"project": proj, "senses": m.get("senses"), "cadcheck": {"fails": s["fails"], "warns": s["warns"], "fail_list": s["fail_list"]},
           "interfaces": m["rows"], "interfaces_off": sum(not x["ok"] for x in m["rows"]),
           "loc": sum(lines.values()), "loc_by_file": lines}
    json.dump(res, open(out, "w"), indent=1)
    print("SCORE cadcheck_fails=%d interfaces_off=%d/%d loc=%d  (%s)" % (
        s["fails"], res["interfaces_off"], len(m["rows"]), res["loc"], out))
    for f in s["fail_list"]:
        print("  FAIL %s" % f)
    for x in m["rows"]:
        print("  %-4s %-14s %-7s %s%s  | %s" % (
            "ok" if x["ok"] else "OFF", x["name"], x["kind"],
            "" if x["err_mm"] is None else "%.3f mm" % x["err_mm"] + ("" if x["err_deg"] is None else " %.2f deg" % x["err_deg"]),
            "" if x["ok"] else "  " + json.dumps({k: v for k, v in x.items() if k not in ("name", "kind", "ok", "err_mm", "err_deg", "why")}),
            x["why"]))
    for f, n in sorted(lines.items()):
        print("  loc %4d %s" % (n, f))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
