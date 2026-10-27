#!/bin/sh
# mates_task kit self-test: build the reference solution (mates template), score it, then a copy with the board planted
# 0.5 mm off its brief position, and check the scorer tells them apart; and a copy with the lid screws driven from
# under the deck (heads in deck counterbores, nuts on the lid ears), which must score the same as the reference.
# Prints KIT PASS|FAIL lines.
#   sh tools/bench/mates_task/selftest.sh /tmp/mates-kit
set -u
KIT="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$KIT/../../.." && pwd)"
CAD="$ROOT/skills/print-cad-blender/scripts/cad"
OUT="${1:-/tmp/mates-kit}"
rm -rf "$OUT"; mkdir -p "$OUT/ref" "$OUT/bug" "$OUT/rev"
for d in ref bug rev; do cp -R "$KIT/reference/blender" "$OUT/$d/"; done
MATES_KIT="$KIT" $CAD build "$OUT/ref/blender/build_assembly.py" > "$OUT/ref/build.log" 2>&1
MATES_KIT="$KIT" MATES_REF_PCB_DX=0.5 $CAD build "$OUT/bug/blender/build_assembly.py" > "$OUT/bug/build.log" 2>&1
MATES_KIT="$KIT" MATES_REF_LID_FROM_BELOW=1 $CAD build "$OUT/rev/blender/build_assembly.py" > "$OUT/rev/build.log" 2>&1
for d in ref bug rev; do python3 -I "$KIT/score.py" "$OUT/$d" --out "$OUT/$d/score.json" > "$OUT/$d/score.txt" 2>&1; done
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
try:
    v = json.load(open("%s/rev/score.json" % d))
except Exception as e:
    print("KIT FAIL lid screws from below: no score (%s; %s/rev/build.log)" % (e, d)); sys.exit()
lid = [x for x in v["interfaces"] if x["name"] == "screws:lid"][0]
vo = [x["name"] for x in v["interfaces"] if not x["ok"]]
print(("KIT PASS" if not vo and lid.get("count") == 4 and v["cadcheck"]["fails"] == 0 else "KIT FAIL") +
      " lid screws from under the deck (nuts on the ears): screws:lid counts %s, %d interfaces off %s, cadcheck %d fails %s" % (
          lid.get("count"), len(vo), vo, v["cadcheck"]["fails"], v["cadcheck"]["fail_list"][:2]))
PY
