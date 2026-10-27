"""Prior-art measurement: text-to-cad's dfam-check (`dfam_tool.py measure`) against `cad printcheck` on the same STLs.

    git clone https://github.com/earthtojake/text-to-cad /tmp/x/t2c && git -C /tmp/x/t2c checkout 2f793659f
    python3 -I dfam_compare.py /tmp/x/t2c/skills/dfam-check/scripts/dfam_tool.py <stl_dir> <printcheck.json> \
        [--angle-limit 45] [extra.stl ...] > result.json

text-to-cad is MIT (c) 2026 Thompson Labs LLC; it is called, not copied. dfam_tool runs in its own uv env with the
versions pinned below (trimesh's `watertight` and its normals depend on the version: unpinned runs gave 5 and 12
non-watertight parts) with `python -I`, one STL per process, cwd /tmp. Per part: printcheck's verdict (fail if any
finding is a fail) next to dfam's facts at `--angle-limit` (area of off-plate downward faces flatter than the limit
from horizontal, its 10 deg histogram, prism support volume, wall p05, watertight). dfam emits no verdict, so the script
sweeps an area threshold and counts how many printcheck fails it flags and how many passing parts it also flags, and
gives the highest line that still flags every fail. The "no flat" sweep drops dfam's 0-10 deg bin (flat ceilings,
which printcheck judges as bridges), leaving the sloped faces from 10 deg to the limit.

At exactly 45 deg the limit is a coin toss: a 45 deg face computes as 44.99999 or 45.00001 from float32 vertices, so
some of each part's 45 deg chamfers are counted. Run 44.99 to leave them all out (overhang_regions.py measures them).
"""
import argparse, json, os, subprocess, time

PINS = ("trimesh==5.2.0", "numpy==2.5.4", "rtree==1.4.1", "scipy==1.18.1", "networkx==3.7", "lxml==6.1.3")
ap = argparse.ArgumentParser()
ap.add_argument("tool")
ap.add_argument("stl_dir")
ap.add_argument("printcheck_json")
ap.add_argument("extra", nargs="*")
ap.add_argument("--angle-limit", type=float, default=45.0)
args = ap.parse_args()
UV = ["uv", "run", "--no-project", "--python", "3.12"] + sum((["--with", p] for p in PINS), []) + \
     ["python", "-I", os.path.abspath(args.tool), "measure"]

verdict = {}
for p in json.load(open(args.printcheck_json))["parts"]:
    st = [x.get("status") for x in p.get("findings") or []]
    verdict[p["stl"]] = "fail" if "fail" in st else ("warn" if st else "ok")


def measure(path):
    t = time.time()
    r = subprocess.run(UV + [os.path.abspath(path), "--angle-limit", "%g" % args.angle_limit],
                       capture_output=True, text=True, cwd="/tmp")
    d = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {"error": r.stderr[-400:]}
    return d, time.time() - t, r.returncode


rows, t0 = [], time.time()
files = sorted(os.path.join(args.stl_dir, f) for f in os.listdir(args.stl_dir) if f.endswith(".stl")) + args.extra
for path in files:
    name = os.path.splitext(os.path.basename(path))[0]
    d, dt, rc = measure(path)
    ov, sv, wt = d.get("overhangs", {}), d.get("support_volume", {}), d.get("wall_thickness", {})
    hist = ov.get("down_facing_angle_histogram_mm2") or {}
    area = ov.get("down_facing_area_below_limit_mm2") or 0.0
    rows.append({"part": name, "printcheck": verdict.get(name, "n/a"), "exit": rc, "seconds": round(dt, 1),
                 "overhang_mm2": area, "overhang_no_flat_mm2": round(area - hist.get("0-10deg", 0.0), 2),
                 "hist_mm2": hist, "support_pct": sv.get("support_to_part_ratio_pct"),
                 "wall_p05_mm": wt.get("p05_mm"), "wall_min_mm": wt.get("min_mm"),
                 "watertight": d.get("mesh", {}).get("watertight"), "error": d.get("error")})

fails = [r for r in rows if r["printcheck"] == "fail"]
passing = [r for r in rows if r["printcheck"] in ("ok", "warn")]


def sweep(key):
    out = []
    for thr in (0, 10, 25, 50, 90, 100, 150, 200, 400, 800):
        hit = [r["part"] for r in fails if r[key] > thr]
        fp = [r["part"] for r in passing if r[key] > thr]
        out.append({"area_gt_mm2": thr, "printcheck_fails_flagged": f"{len(hit)}/{len(fails)}",
                    "missed": sorted({r["part"] for r in fails} - set(hit)),
                    "passing_parts_flagged": f"{len(fp)}/{len(passing)}"})
    line = min(r[key] for r in fails) if fails else None   # flag at area >= line: every fail, and these passing parts
    line = line if line else None                           # a fail with no counted area: no line catches them all
    fp = sorted(r["part"] for r in passing if line is not None and r[key] >= line)
    return {"sweep": out, "catch_all_line_mm2": line, "passing_flagged_at_line": f"{len(fp)}/{len(passing)}",
            "passing_flagged": fp, "top_passing": max(passing, key=lambda r: r[key])["part"] if passing else None}


print(json.dumps({"angle_limit_deg": args.angle_limit, "pins": PINS, "n": len(rows),
                  "seconds": round(time.time() - t0, 1),
                  "not_watertight": sorted(r["part"] for r in rows if r["watertight"] is False),
                  "with_flat": sweep("overhang_mm2"), "no_flat": sweep("overhang_no_flat_mm2"),
                  "rows": sorted(rows, key=lambda r: -r["overhang_mm2"])}, indent=1))
