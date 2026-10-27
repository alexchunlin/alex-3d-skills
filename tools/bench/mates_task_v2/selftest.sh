#!/bin/sh
# mates_task_v2 kit self-test: build the reference (mates template) and two planted errors, score all three with
# tools/bench/mates_task/score.py --kit <this kit>. Prints KIT PASS|FAIL lines.
#   ref   the reference: 0 cadcheck fails, every interface, pose and clearance row within tolerance
#   cam   the camera's back 25.5 mm ahead of the tilt axis instead of 25: only BUY_cam and the 5 pose rows are off, by 0.5
#   sense the tilt range typed in the brief's sense on a joint that counts the other way (60 down, 25 up): only PIV_tilt
#   sh tools/bench/mates_task_v2/selftest.sh /tmp/mates-kit-v2
set -u
KIT="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$KIT/../../.." && pwd)"
CAD="$ROOT/skills/print-cad-blender/scripts/cad"
OUT="${1:-/tmp/mates-kit-v2}"
rm -rf "$OUT"
for d in ref cam sense; do mkdir -p "$OUT/$d"; cp -R "$KIT/reference/blender" "$OUT/$d/"; done
MATES_KIT="$KIT" $CAD build "$OUT/ref/blender/build_assembly.py" > "$OUT/ref/build.log" 2>&1
MATES_KIT="$KIT" MATES_REF_CAM_DX=0.5 $CAD build "$OUT/cam/blender/build_assembly.py" > "$OUT/cam/build.log" 2>&1
MATES_KIT="$KIT" MATES_REF_TILT_SENSE_WRONG=1 $CAD build "$OUT/sense/blender/build_assembly.py" > "$OUT/sense/build.log" 2>&1
for d in ref cam sense; do
  python3 -I "$KIT/../mates_task/score.py" "$OUT/$d" --kit "$KIT" --out "$OUT/$d/score.json" > "$OUT/$d/score.txt" 2>&1
done
python3 -I - "$OUT" <<'PY'
import json, sys
d = sys.argv[1]
S = {}
for k in ("ref", "cam", "sense"):
    try:
        S[k] = json.load(open("%s/%s/score.json" % (d, k)))
    except Exception as e:
        print("KIT FAIL %s: no score (%s; see %s/%s/score.txt)" % (k, e, d, k))
if "ref" in S:
    r = S["ref"]
    off = [x["name"] for x in r["interfaces"] if not x["ok"]]
    kinds = sorted({x["kind"] for x in r["interfaces"]})
    print(("KIT PASS" if r["cadcheck"]["fails"] == 0 else "KIT FAIL") + " v2 reference: cadcheck %d fails (%s)" % (
        r["cadcheck"]["fails"], r["cadcheck"]["fail_list"][:2]))
    print(("KIT PASS" if not off and len(r["interfaces"]) == 24 else "KIT FAIL") +
          " v2 reference: %d of %d rows within 0.2 mm / 1 deg / 1 mm clearance (%s) %s" % (
              len(r["interfaces"]) - len(off), len(r["interfaces"]), ", ".join(kinds), off))
    print(("KIT PASS" if 60 <= r["loc"] <= 400 else "KIT FAIL") + " v2 reference: %d lines of build code" % r["loc"])
if "cam" in S:
    c = S["cam"]
    off = {x["name"]: x for x in c["interfaces"] if not x["ok"]}
    want = {"BUY_cam"} | {x["name"] for x in c["interfaces"] if x["kind"] == "pose"}
    errs = sorted({round(x["err_mm"], 3) for x in off.values()})
    print(("KIT PASS" if set(off) == want and errs == [0.5] else "KIT FAIL") +
          " v2 planted camera 0.5 mm forward: flagged %s, each %s mm off" % (sorted(off), errs))
if "sense" in S:
    s = S["sense"]
    off = {x["name"]: x for x in s["interfaces"] if not x["ok"]}
    print(("KIT PASS" if list(off) == ["PIV_tilt"] else "KIT FAIL") +
          " v2 planted tilt range in the wrong sense: flagged %s (range %s)" % (sorted(off), (off.get("PIV_tilt") or {}).get("range")))
PY
