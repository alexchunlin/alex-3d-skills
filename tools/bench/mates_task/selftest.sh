#!/bin/sh
# mates_task kit self-test: build the reference solution (mates template), score it, then a copy with the board planted
# 0.5 mm off its brief position, and check the scorer tells them apart. Prints KIT PASS|FAIL lines.
#   sh tools/bench/mates_task/selftest.sh /tmp/mates-kit
set -u
KIT="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$KIT/../../.." && pwd)"
CAD="$ROOT/skills/print-cad-blender/scripts/cad"
OUT="${1:-/tmp/mates-kit}"
rm -rf "$OUT"; mkdir -p "$OUT/ref" "$OUT/bug"
cp -R "$KIT/reference/blender" "$OUT/ref/"; cp -R "$KIT/reference/blender" "$OUT/bug/"
MATES_KIT="$KIT" $CAD build "$OUT/ref/blender/build_assembly.py" > "$OUT/ref/build.log" 2>&1
MATES_KIT="$KIT" MATES_REF_PCB_DX=0.5 $CAD build "$OUT/bug/blender/build_assembly.py" > "$OUT/bug/build.log" 2>&1
python3 -I "$KIT/score.py" "$OUT/ref" --out "$OUT/ref/score.json" > "$OUT/ref/score.txt" 2>&1
python3 -I "$KIT/score.py" "$OUT/bug" --out "$OUT/bug/score.json" > "$OUT/bug/score.txt" 2>&1
python3 -I - "$OUT" <<'PY'
import json, sys
d = sys.argv[1]
try:
    r, b = (json.load(open("%s/%s/score.json" % (d, k))) for k in ("ref", "bug"))
except Exception as e:
    print("KIT FAIL no score (%s; see %s/*/score.txt)" % (e, d)); sys.exit()
off = {x["name"]: x for x in r["interfaces"] if not x["ok"]}
print(("KIT PASS" if r["cadcheck"]["fails"] == 0 else "KIT FAIL") + " reference solution: cadcheck %d fails with the kit's acceptance rows (%s)" % (
    r["cadcheck"]["fails"], r["cadcheck"]["fail_list"][:2]))
print(("KIT PASS" if not off and len(r["interfaces"]) == 7 else "KIT FAIL") + " reference solution: %d of %d interfaces within 0.2 mm / 1 deg %s" % (
    len(r["interfaces"]) - len(off), len(r["interfaces"]), sorted(off)))
print(("KIT PASS" if 60 <= r["loc"] <= 400 else "KIT FAIL") + " reference solution: %d lines of build code counted" % r["loc"])
bo = {x["name"]: x for x in b["interfaces"] if not x["ok"]}
pcb = bo.get("BUY_pcb", {})
print(("KIT PASS" if list(bo) == ["BUY_pcb"] and abs((pcb.get("err_mm") or 0) - 0.5) < 1e-3 else "KIT FAIL") +
      " planted board offset: the scorer flags only BUY_pcb, %s mm off (others %s)" % (pcb.get("err_mm"), sorted(set(bo) - {"BUY_pcb"})))
PY
