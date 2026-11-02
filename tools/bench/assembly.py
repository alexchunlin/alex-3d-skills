#!/usr/bin/env python3
"""Design-for-assembly report on the archived designs: gradients to improve (fewer parts, fewer screws, fewer SKUs),
not pass/fail.

Per design, from the records cadcheck already reads: the blend through cadcheck's own scene model (assembly_scan.py
in Blender: its Printed / Purchased / Fasteners collections, its nut test, its fastener axis), the designer's
checks.json (assembly_order), the designer's cadcheck report from a bench run (each screw's thread host), and the
manifest where one was archived (fastener specs, the cadlib feature log for heat-set inserts).

  python3 -I tools/bench/assembly.py --from-run /tmp/alex3d-bench/run-<pid> [--json out.json]

Columns: printed parts; purchased parts (BUY_, not fasteners); screws; distinct screw SKUs (size x length x head,
self-tap apart); snaps and print-in-place joints (cadlib features.snap_hook / annular_snap / torsion_snap and
pip_hinge records: the blend's cad_joins, else the manifest's "joins"; 0 for designs built before them); joins (screws +
snaps + print-in-place: the user's v2 print had about 103 screws in 18 types across 36 parts); nuts; heat-set inserts (from the manifest's feature log; n/a without one); screws threading into a
printed part; assembly steps (assembly_order rows); screws per printed part; rigid bodies carrying printed parts
(parts on different joint bodies must stay separate: Boothroyd-Dewhurst's relative-motion criterion).

No Boothroyd-Dewhurst theoretical minimum: its other two criteria (a different material, and a part that must be
separate to assemble or service the rest) and printability (bed size, orientation, supports) are judgments the
records don't hold, so any number from motion alone would read as a floor it isn't.
Blender runs at nice 10, one at a time; scans are cached in the run dir (<attempt>/assembly_scan.json).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parents[1]
SCRIPTS = ROOT / "skills/print-cad-blender/scripts"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS))
import cadbom  # noqa: E402  (its spec regex and head names)


def scan(att: str, spec: dict, rdir: Path) -> dict:
    out = rdir / att / "assembly_scan.json"
    if out.exists():
        return json.load(open(out))
    blend = rdir / att / spec["as"]
    if not blend.exists():
        raise SystemExit("%s: no blend in %s (run the bench there first)" % (att, blend.parent))
    bl = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
    env = dict(os.environ, CAD_SCRIPTS=str(SCRIPTS))
    p = subprocess.run(["nice", "-n", "10", bl, "-b", "--factory-startup", str(blend), "--python", str(BENCH / "assembly_scan.py"),
                        "--python-exit-code", "1", "--", "--config", str(ROOT / spec["dir"] / "checks.json"), "--scan-out", str(out)],
                       env=env, capture_output=True, text=True)
    if p.returncode or not out.exists():
        raise SystemExit("%s: assembly scan failed (exit %d): %s" % (att, p.returncode, (p.stdout + p.stderr)[-800:]))
    return json.load(open(out))


def sku(f: dict) -> str:
    """'M3 x 12 csk' from the cadlib part string ('M3_csk x 12', 'M3_selftap_pan x 9'), else from the measured
    shank (geometry: v1 had no cadlib props) with the head unknown."""
    part = f.get("part") or ""
    m = re.match(r"M(\d+(?:\.\d+)?)_(\w+) x (\d+(?:\.\d+)?)", part)
    if m:
        head = cadbom.head_of(m.group(2).replace("selftap_", "")) or m.group(2)
        return "M%s x %s %s%s" % (m.group(1), m.group(3), head, " ST" if "selftap" in m.group(2) else "")
    d = min((2, 2.5, 3, 4, 5), key=lambda x: abs(x - f["d"]))
    return "M%g x %g ?" % (d, round(f["length"]))


def report(att: str, spec: dict, rdir: Path) -> dict:
    s = scan(att, spec, rdir)
    src = ROOT / spec["dir"]
    screws = [f for f in s["fasteners"] if not f["nut"]]
    nuts = [f for f in s["fasteners"] if f["nut"]]
    skus = Counter(sku(f) for f in screws)
    inserts = None
    joins = s.get("joins") or []
    man = src / "manifest.json"
    if man.exists():
        m = json.load(open(man))
        inserts = sum(1 for x in m.get("features", []) if x.get("feature") == "screw_hole" and x.get("kind") == "insert")
        joins = joins or m.get("joins") or []
    pip = sum(1 for j in joins if j.get("kind") == "pip_hinge")
    snaps = len(joins) - pip
    into_prt = None
    rep = rdir / att / "designer.json"
    if rep.exists():
        rows = json.load(open(rep)).get("checks", {}).get("fasteners", {}).get("rows", [])
        into_prt = sum(1 for r in rows if str(r.get("thread_host") or "").startswith("PRT_"))
    bodies = Counter(p["body"] for p in s["printed"])
    n = len(s["printed"])
    return {"attempt": att, "printed": n, "purchased": len(s["purchased"]), "screws": len(screws), "skus": len(skus),
            "snaps": snaps, "print_in_place": pip, "joins": len(screws) + snaps + pip, "nuts": len(nuts), "inserts": inserts, "screws_into_printed": into_prt, "steps": len(s["assembly_order"]),
            "screws_per_printed": round(len(screws) / n, 2) if n else None, "bodies": len(bodies),
            "printed_per_body": round(n / len(bodies), 1) if bodies else None,
            "head_unknown": sum(1 for f in screws if f.get("source") == "geometry"), "sku_counts": dict(skus.most_common()),
            "bodies_detail": dict(bodies.most_common())}


def markdown(rows: list[dict]) -> str:
    L = ["| design | printed | purchased | screws | screw SKUs | snaps | print-in-place | joins | nuts | inserts | screws into PLA | steps | screws / printed | bodies w/ printed | printed / body |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        na = lambda v: "n/a" if v is None else str(v)
        L.append("| %s | %d | %d | %d | %d%s | %d | %d | %d | %d | %s | %s | %d | %.2f | %d | %.1f |" % (
            r["attempt"], r["printed"], r["purchased"], r["screws"], r["skus"], " (head ?)" if r["head_unknown"] else "",
            r["snaps"], r["print_in_place"], r["joins"], r["nuts"],
            na(r["inserts"]), na(r["screws_into_printed"]), r["steps"], r["screws_per_printed"] or 0, r["bodies"], r["printed_per_body"] or 0))
    return "\n".join(L)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from-run", required=True, help="a bench run dir (/tmp/alex3d-bench/run-<pid>): its blends and designer reports")
    p.add_argument("--corpus", default=str(BENCH / "corpus.json"))
    p.add_argument("--attempts")
    p.add_argument("--json")
    a = p.parse_args(argv)
    corpus = json.load(open(a.corpus))["attempts"]
    names = a.attempts.split(",") if a.attempts else list(corpus)
    rows = [report(n, corpus[n], Path(a.from_run)) for n in names]
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))
    print(markdown(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
