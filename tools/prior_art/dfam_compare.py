"""Prior-art measurement: text-to-cad's dfam-check (`dfam_tool.py measure`) against `cad printcheck` on the same STLs.

    python3 dfam_compare.py <dfam_tool.py> <stl_dir> <printcheck.json> [extra.stl ...] > result.json

dfam_tool runs in its own uv env (trimesh, numpy, rtree, scipy, networkx, lxml) with `python -I`, one STL per process.
Per part: printcheck's verdict (fail if any finding is a fail) next to dfam's facts at the FDM 45 deg limit (area of
off-plate downward faces flatter than 45 deg from horizontal, prism support volume, wall p05). dfam emits no verdict, so
the script sweeps an area threshold and counts how many printcheck fails it flags and how many passing parts it also
flags.
"""
import json, os, subprocess, sys, time

tool, stl_dir, pc_path, extra = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
UV = ["uv", "run", "--no-project", "--python", "3.12"] + sum((["--with", p] for p in
      ("trimesh", "numpy", "rtree", "scipy", "networkx", "lxml")), []) + ["python", "-I", tool, "measure"]

pc = json.load(open(pc_path))["parts"]
verdict = {}
for p in pc:
    st = [x.get("status") for x in p.get("findings") or []]
    verdict[p["stl"]] = "fail" if "fail" in st else ("warn" if st else "ok")


def measure(path):
    t = time.time()
    r = subprocess.run(UV + [path, "--angle-limit", "45"], capture_output=True, text=True, cwd="/tmp")
    d = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {"error": r.stderr[-400:]}
    return d, time.time() - t, r.returncode


rows, t0 = [], time.time()
files = sorted(os.path.join(stl_dir, f) for f in os.listdir(stl_dir) if f.endswith(".stl")) + extra
for path in files:
    name = os.path.splitext(os.path.basename(path))[0]
    d, dt, rc = measure(path)
    ov, sv, wt = d.get("overhangs", {}), d.get("support_volume", {}), d.get("wall_thickness", {})
    rows.append({"part": name, "printcheck": verdict.get(name, "n/a"), "exit": rc, "seconds": round(dt, 1),
                 "overhang_lt45_mm2": ov.get("down_facing_area_below_limit_mm2"),
                 "hist_mm2": ov.get("down_facing_angle_histogram_mm2"),
                 "support_pct": sv.get("support_to_part_ratio_pct"),
                 "wall_p05_mm": wt.get("p05_mm"), "wall_min_mm": wt.get("min_mm"),
                 "watertight": d.get("mesh", {}).get("watertight"), "keys": sorted(d)[:12]})

fails = [r for r in rows if r["printcheck"] == "fail"]
passing = [r for r in rows if r["printcheck"] in ("ok", "warn")]
sweep = []
for thr in (0, 10, 25, 50, 100, 200, 400, 800):
    hit = [r["part"] for r in fails if (r["overhang_lt45_mm2"] or 0) > thr]
    fp = [r["part"] for r in passing if (r["overhang_lt45_mm2"] or 0) > thr]
    sweep.append({"area_gt_mm2": thr, "printcheck_fails_flagged": f"{len(hit)}/{len(fails)}", "missed":
                  sorted({r["part"] for r in fails} - set(hit)), "passing_parts_flagged": f"{len(fp)}/{len(passing)}"})
print(json.dumps({"n": len(rows), "seconds": round(time.time() - t0, 1), "sweep": sweep,
                  "rows": sorted(rows, key=lambda r: -(r["overhang_lt45_mm2"] or 0))}, indent=1))
