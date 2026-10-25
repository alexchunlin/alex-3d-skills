#!/bin/sh
# Re-prove every tool in this repo. Writes only under /tmp/alex3d-verify. About 3 minutes, run at nice 10.
# The attempt regressions use examples/mm-launcher-a{1,2}/mm_launcher_a*.blend.gz (the blends the reviewers saw).
#   sh tools/verify_all.sh            # HW defaults to the mm-launcher project (read-only; copied first)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAD="$ROOT/skills/print-cad-blender/scripts/cad"
HW="${HW:-$HOME/code-stuff/mmlauncher/mm-launcher/mm-launch-hw}"
V=/tmp/alex3d-verify
BL="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
rm -rf "$V"; mkdir -p "$V"
pass=0; fail=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
summ() { python3 -I -c "import json,sys; s=json.load(open(sys.argv[1]))['summary']; print(s['fails'], s['warns'])" "$1" 2>/dev/null; }

# 1 demo, clean: must pass
$CAD build "$ROOT/examples/demo-turret/build.py" --out "$V/demo-clean" >/dev/null
$CAD check "$V/demo-clean/demo.blend" "$ROOT/examples/demo-turret/checks.json" "$V/demo-clean/cadcheck.json" >/dev/null
set -- $(summ "$V/demo-clean/cadcheck.json"); [ "${1:-x}" = 0 ] && ok "demo clean: 0 fails" || bad "demo clean: ${1:-?} fails"

# 2 demo, planted bugs: reversed screw, proud head in sweep, tilt into pan disc, bolt short of its nut must all fail
$CAD build "$ROOT/examples/demo-turret/build.py" --out "$V/demo-bug" --bug >/dev/null
$CAD check "$V/demo-bug/demo.blend" "$ROOT/examples/demo-turret/checks.json" "$V/demo-bug/cadcheck.json" >/dev/null
for pat in "FST_arm_0 head is inside" "PRT_barrel x FST_proud" "PRT_pan x PRT_barrel" "FST_side stops 0.40 mm short"; do
  grep -q "$pat" "$V/demo-bug/cadcheck.json" && ok "demo bug caught: $pat" || bad "demo bug missed: $pat"
done

# 3 project template builds and passes
cp -R "$ROOT/skills/print-cad-blender/templates/project" "$V/tpl"; mkdir -p "$V/tplroot"; mv "$V/tpl" "$V/tplroot/blender"
$CAD build "$V/tplroot/blender/build_assembly.py" >/dev/null
$CAD check "$V/tplroot/blender/model.blend" "$V/tplroot/blender/checks.json" >/dev/null
set -- $(summ "$V/tplroot/blender/cadcheck.json"); [ "${1:-x}" = 0 ] && ok "template: 0 fails" || bad "template: ${1:-?} fails"

# 4 attempt-1 regression on the archived attempt-1 blend (the live HW blend moves on every attempt)
A1="$ROOT/examples/mm-launcher-a1/mm_launcher_a1.blend.gz"
if [ -f "$A1" ]; then
  mkdir -p "$V/a1"; gunzip -c "$A1" > "$V/a1/mm_launcher.blend"
  $CAD check "$V/a1/mm_launcher.blend" "$ROOT/examples/mm-launcher-a1/checks.json" "$V/a1/cadcheck.json" >/dev/null
  for pat in "PRT_feeder_disc x FST_cap_R-1" "PRT_flywheel x FST_motor_0" "PRT_arm_cover_L x PRT_trunnion_L touch" \
             "PRT_hopper to PRT_launcher_body only 0.21" "feed_outlet_to_wheel at tilt=0: lands" "FST_motor_0 head is inside" \
             "PRT_hood to PRT_flywheel = 9.50"; do
    grep -q "$pat" "$V/a1/cadcheck.json" && ok "A1 reproduces: $pat" || bad "A1 missing: $pat"
  done
  # cadq reproduces R1's exact numbers
  $CAD q "$V/a1/mm_launcher.blend" dist PRT_feeder_disc FST_cap_R-1 --config "$ROOT/examples/mm-launcher-a1/checks.json" | grep -q '"mm": -27.2' \
    && ok "cadq: feeder disc x cap screw 27.2 mm3 (R1: 27.2)" || bad "cadq dist"
fi
# 4a attempt-2 regression: every R2 item a tool can see (FINDINGS A2-F1..F9), and no false fails left
A2="$ROOT/examples/mm-launcher-a2/mm_launcher_a2.blend.gz"
if [ -f "$A2" ]; then
  mkdir -p "$V/a2"; gunzip -c "$A2" > "$V/a2/mm_launcher.blend"
  $CAD check "$V/a2/mm_launcher.blend" "$ROOT/examples/mm-launcher-a2/checks.json" "$V/a2/cadcheck.json" >/dev/null
  for pat in "FST_fw_bolt_0 stops 0.35 mm short of its nut" "FST_fw_bolt_0 cannot be driven: straight bit blocked by PRT_flywheel at 18.5 mm; L-key long leg clear over 0 deg" \
             "FST_adapter_0 runs 2.5 mm into purchased part BUY_battery" "FST_adapter_nut_0 sits inside purchased part BUY_battery" \
             "feeder_one_candy_per_cycle: 2 open windows" "FST_clamp_r reachable only at tilt=45" "1.01 mm rigid squeeze" \
             "FST_jack_0 head stands 11.0 mm" "CAB_bus_feeder: about 11 mm of cable is visible"; do
    grep -q "$pat" "$V/a2/cadcheck.json" && ok "A2 reproduces: $pat" || bad "A2 missing: $pat"
  done
  python3 -I -c "
import json,sys; d=json.load(open(sys.argv[1]))
f=d['summary']['fail_list']; drop=d['checks']['drop']['findings']
bad=[x for x in f if not any(k in x for k in ('FST_fw_bolt','FST_adapter','feeder_one_candy'))]
sys.exit(1 if (bad or drop or d['summary']['fails']!=15) else 0)" "$V/a2/cadcheck.json" \
    && ok "A2: exactly the 15 R2-confirmed fails, slide tracer feeds 29/29 at every tilt" || bad "A2: unexpected fails or feed result"
fi
# 4b smoke: cadcheck runs on the live project blend (whatever attempt it is at); reports, never asserts
if [ -f "$HW/blender/mm_launcher.blend" ]; then
  mkdir -p "$V/live"; cp "$HW/blender/mm_launcher.blend" "$V/live/"
  $CAD check "$V/live/mm_launcher.blend" "$ROOT/examples/mm-launcher-a2/checks.json" "$V/live/cadcheck.json" >/dev/null
  set -- $(summ "$V/live/cadcheck.json"); [ -n "${1:-}" ] && ok "live HW blend checked: $1 fails, $2 warns (see $V/live/cadcheck.json)" || bad "live HW blend check crashed"
fi

# 5 component placeholders build closed
"$BL" -b --factory-startup --python-expr "
import sys; sys.path.insert(0, '$ROOT/components'); import placeholders as PH
from cadlib import asm, geom as G
asm.new_scene(); bad=[f.__name__ for f in PH.ALL if G.solid_stats(f())[0]]
print('PLACEHOLDERS', len(PH.ALL), 'nonmanifold', bad)" 2>&1 | grep -q "nonmanifold \[\]" && ok "11 placeholders closed" || bad "placeholders"

# 6 workflow template control flow
python3 -I "$ROOT/tools/test_workflow_template.py" >/dev/null && ok "workflow template dry run" || bad "workflow template"

# 7 transcript extractor on any available transcript
T=$(ls "$HOME"/.claude/projects/-Users-alxchunlin-code-stuff-mmlauncher-mm-launcher/*/subagents/workflows/*/agent-*.jsonl 2>/dev/null | head -1)
if [ -n "$T" ]; then python3 -I "$ROOT/tools/transcript/cc_transcript.py" summary "$T" | grep -q "^wall" && ok "transcript summary" || bad "transcript summary"; fi

echo "verify_all: $pass passed, $fail failed"
[ $fail = 0 ]
