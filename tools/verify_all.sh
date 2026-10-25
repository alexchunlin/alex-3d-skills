#!/bin/sh
# Re-prove every tool in this repo. Writes only under /tmp/alex3d-verify. About 8 minutes, run at nice 10.
# The attempt regressions use examples/mm-launcher-{a1,a2,a3,v2a1,v2a2}/*.blend.gz (the blends the reviewers saw).
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

# 3b template build into another dir (parallel builders, V2A1-T1); `cad check` with a flag where CONFIG/OUT would be
$CAD build "$V/tplroot/blender/build_assembly.py" -- --out "$V/tplout" >/dev/null
[ -f "$V/tplout/model.blend" ] && [ -f "$V/tplout/manifest.json" ] && ok "template: --out writes model.blend + manifest there" || bad "template --out"
(cd "$V" && $CAD check "$V/tplout/model.blend" --only parts >/dev/null)
[ -f "$V/tplout/cadcheck.json" ] && [ ! -e "$V/--only" ] && ok "cad check: a flag in the CONFIG slot is not a file name" || bad "cad check arg parsing"

# 3c cad py: params and cadlib import with bpy present (v2 A2 builders stubbed bpy by hand, V2A2-T3)
(cd "$V/tplroot/blender" && $CAD py -c "import bpy, cadlib, params; print('CADPY', bpy.app.version_string)") | grep -q "^CADPY" \
  && ok "cad py: project modules import with bpy + cadlib" || bad "cad py"

# 4 attempt-1 regression on the archived attempt-1 blend (the live HW blend moves on every attempt)
A1="$ROOT/examples/mm-launcher-a1/mm_launcher_a1.blend.gz"
if [ -f "$A1" ]; then
  mkdir -p "$V/a1"; gunzip -c "$A1" > "$V/a1/mm_launcher.blend"
  $CAD check "$V/a1/mm_launcher.blend" "$ROOT/examples/mm-launcher-a1/checks.json" "$V/a1/cadcheck.json" >/dev/null
  for pat in "PRT_feeder_disc x FST_cap_R-1" "PRT_flywheel x FST_motor_0" "PRT_arm_cover_L x PRT_trunnion_L touch" \
             "PRT_hopper to PRT_launcher_body only 0.21" "feed_outlet_to_wheel at tilt=0: lands" "FST_motor_0 head is inside" \
             "PRT_hood to PRT_flywheel = 9.50"; do
    grep -qF "$pat" "$V/a1/cadcheck.json" && ok "A1 reproduces: $pat" || bad "A1 missing: $pat"
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
             "FST_jack_0 head stands 11.0 mm" "CAB_bus_feeder: about 15 mm of cable is visible from outside around [-104.9"; do
    grep -qF "$pat" "$V/a2/cadcheck.json" && ok "A2 reproduces: $pat" || bad "A2 missing: $pat"
  done
  python3 -I -c "
import json,sys; d=json.load(open(sys.argv[1]))
f=d['summary']['fail_list']; drop=[x for x in d['checks']['drop']['findings'] if x['status']=='fail']
bad=[x for x in f if not any(k in x for k in ('FST_fw_bolt','FST_adapter','feeder_one_candy'))]
sys.exit(1 if (bad or drop or d['summary']['fails']!=15) else 0)" "$V/a2/cadcheck.json" \
    && ok "A2: exactly the 15 R2-confirmed fails, slide tracer feeds 29/29 at every tilt" || bad "A2: unexpected fails or feed result"
fi
# 4c attempt-3 regression (FINDINGS A3-F1..F8): battery slide through nuts, leaf printed across layers, stall margin,
# notch-visible cable, visible nuts; and the nip stud/thumbwheel mechanism (carry, captive) gives no false fails
A3="$ROOT/examples/mm-launcher-a3/mm_launcher_a3.blend.gz"
if [ -f "$A3" ]; then
  mkdir -p "$V/a3"; gunzip -c "$A3" > "$V/a3/mm_launcher.blend"
  $CAD check "$V/a3/mm_launcher.blend" "$ROOT/examples/mm-launcher-a3/checks.json" "$V/a3/cadcheck.json" >/dev/null
  for pat in "BUY_battery slide-out blocked by ['FST_adapter_nut_1', 'FST_adapter_nut_3'] at 5 mm" \
             "PRT_nip_cover (leaf spring): the beam stands 85 deg off the bed" \
             "feed_spout_to_tape at tilt=45: 29/29 rays reach the target over a slide of only 21.3 deg" \
             "feed_spout_to_tape at tilt=46: 29/29 rays reach the target over a slide of only 20.3 deg" \
             "CAB_launcher_bundle_0: about 8 mm of cable is visible" "FST_adapter_nut_1 is visible from outside" \
             "FST_hinge: only 2.0 mm of thread"; do
    grep -qF "$pat" "$V/a3/cadcheck.json" && ok "A3 reproduces: $pat" || bad "A3 missing: $pat"
  done
  python3 -I -c "
import json,sys; d=json.load(open(sys.argv[1])); s=d['summary']
nip=[x for x in s['fail_list'] + [w for w in s['warn_list'] if w.startswith('fasteners')] if 'nip_stud' in x or 'nip_nut' in x]
sys.exit(1 if (s['fails'] != 2 or nip or d['checks']['index']['findings']) else 0)" "$V/a3/cadcheck.json" \
    && ok "A3: exactly the 2 R3-confirmed fails, no nip-mechanism findings, feeder index 1 candy per fire" || bad "A3: unexpected fails"
fi
# 4d v2 attempt-1 regression (FINDINGS V2A1): the first tool-using attempt, archived as R1 saw it
V2="$ROOT/examples/mm-launcher-v2a1"
if [ -f "$V2/mm_launcher_v2a1.blend.gz" ]; then
  mkdir -p "$V/v2a1"; gunzip -c "$V2/mm_launcher_v2a1.blend.gz" > "$V/v2a1/model.blend"
  # designer config + R1's two missing pieces: hood-end drop poses (A1-01) and contact_normal on the journal fits (dispute 7)
  $CAD check "$V/v2a1/model.blend" "$V2/checks.json" "$V/v2a1/cadcheck.json" --overlay "$V2/overlay_drop.json" --overlay "$V2/overlay_fits.json" >/dev/null
  for pat in "the payload path touches ['PRT_hood'], which moves on PIV_hood" \
             "nip drop at both hood ends at hood=-6.50948, tilt=46: 31/31 rays end at ['stall']" \
             "magnet centring on the rear shaft (A1-#7, A2-#6): worst case 0.40" "PRT_feeder_crown: 40 wall samples < 1.6 mm (min 0.94)"; do
    grep -qF "$pat" "$V/v2a1/cadcheck.json" && ok "V2A1 reproduces: $pat" || bad "V2A1 missing: $pat"
  done
  python3 -I -c "
import json,sys; d=json.load(open(sys.argv[1])); s=d['summary']; i=d['checks']['interference']
pairs={frozenset((r['a'],r['b'])) for r in i['min_clearance']}
need={frozenset(('PRT_post_R','PRT_journal_plate')), frozenset(('PRT_base_shell','PRT_turntable'))}
st=d['checks']['stability']
ok = s['fails']==3 and all('nip drop at both hood ends at hood=-6.5' in f for f in s['fail_list']) and need <= pairs and st['poses'] >= 100
sys.exit(0 if ok else 1)" "$V/v2a1/cadcheck.json" \
    && ok "V2A1: exactly the 3 open-end stall fails; contact fits measure their journals; stability over 864 poses" || bad "V2A1: unexpected fails, journals unmeasured or 1-pose stability"
  # a row naming a part that isn't built yet: one fail, the run carries on (V2A1-T3)
  echo '{"distances": [{"a": "PRT_not_built_yet", "b": "PRT_hood", "min": 1}]}' > "$V/v2a1/missing.json"
  $CAD check "$V/v2a1/model.blend" "$V2/checks.json" "$V/v2a1/missing_out.json" --only distances --overlay "$V/v2a1/missing.json" >/dev/null
  grep -qF "PRT_not_built_yet not in the scene; row skipped" "$V/v2a1/missing_out.json" && ok "missing object: reported, run completes" || bad "missing object crashed the run"
  # section through closed solids uses Manifold: the EXACT cutter flooded 95% of this view (V2A1-T5)
  $CAD q "$V/v2a1/model.blend" section x 21 "$V/v2a1/sec_x21.png" 400,0,200 320 >/dev/null
  "$BL" -b --factory-startup --python-expr "
import bpy; from collections import Counter
im=bpy.data.images.load('$V/v2a1/sec_x21.png'); p=im.pixels[:]; n=len(p)//4
c=Counter((round(p[4*i],1),round(p[4*i+1],1),round(p[4*i+2],1)) for i in range(0,n,7)); t=sum(c.values())
print('SECTION_TOP', max(v/t for k,v in c.items() if k!=(1.0,1.0,1.0)))" 2>&1 | python3 -I -c "
import sys; v=[float(l.split()[1]) for l in sys.stdin if l.startswith('SECTION_TOP')]; sys.exit(0 if v and v[0] < 0.5 else 1)" \
    && ok "section x21: no flooded cut colour" || bad "section x21 flooded (EXACT inversion back?)"
fi
# 4e v2 attempt-2 regression (FINDINGS V2A2): the blend V2R2 reviewed, the designer's own config
V22="$ROOT/examples/mm-launcher-v2a2"
if [ -f "$V22/mm_launcher_v2a2.blend.gz" ]; then
  mkdir -p "$V/v2a2"; gunzip -c "$V22/mm_launcher_v2a2.blend.gz" > "$V/v2a2/model.blend"
  # designer config: still 0 fails; the new config-completeness warns name V2R2's A2-02/A2-04 gaps and the A2-01 lead
  $CAD check "$V/v2a2/model.blend" "$V22/checks.json" "$V/v2a2/cadcheck.json" >/dev/null
  for pat in "PRT_nip_leaf is named compliant in distances" "says M2 x 4, but its M2 screws are [8.0] long" \
             "10 cables have no lead length" "which moves on PIV_nip_lift (-1.49302..0), but the test holds PIV_nip_lift at home"; do
    grep -qF "$pat" "$V/v2a2/cadcheck.json" && ok "V2A2 flags: $pat" || bad "V2A2 missing: $pat"
  done
  set -- $(summ "$V/v2a2/cadcheck.json"); [ "${1:-x}" = 0 ] && ok "V2A2 designer config: 0 fails" || bad "V2A2 designer config: ${1:-?} fails"
  # V2R2's missing rows as payload_fit / sightlines / slide expect / ray artefact, plus two planted rows
  $CAD check "$V/v2a2/model.blend" "$V22/checks.json" "$V/v2a2/overlay.json" --overlay "$V22/overlay_v2a2.json" --overlay-only \
       --only payload,sightlines,slide,distances >/dev/null
  python3 -I -c "
import json,sys; d=json.load(open(sys.argv[1])); s=d['summary']; f=' | '.join(s['fail_list']); w=' | '.join(s['warn_list'])
p=lambda k: next(r for r in d['checks']['payload']['rows'] if r['name'].startswith(k))
ok = (s['fails'] == 4 and 'edge-on pair (min candy 12.5 x 6.5)' in f and 'planted: the slot ray' in f and 'planted: gate stop' in f
      and '14.18 mm (along ray)' in f and 'only 0.11 mm to spare' in w and 'much wider than the nearest gap 7.06' in w
      and 0.1 <= p('pocket blocks an edge-on pair (min')['short_by_mm'] <= 0.2 and p('pocket seats one flat candy (max')['margin_mm'] >= 0.4)
sys.exit(0 if ok else 1)" "$V/v2a2/overlay.json" \
    && ok "V2A2: pocket seats a 12.5x6.5 pair (0.14 short), 13x7 blocked by 0.11; sightlines, gate stop, ray artefact; planted rows fail" \
    || bad "V2A2 overlay: unexpected result"
  # cad q: help without a model; a ray given in the tilt frame at tilt 45 (V2A2-T3)
  $CAD q | grep -q "ray X,Y,Z DX,DY,DZ \[--frame" && ok "cad q prints its help" || bad "cad q help"
  $CAD q "$V/v2a2/model.blend" ray 19.5,-2.33,111.274 0,-0.316,0.949 --frame PIV_tilt --pose PIV_tilt=45 | grep -q '"hit": "PRT_nip_wheel", "mm": 14.4' \
    && ok "cad q ray --frame: finger-slot ray at tilt 45 hits the thumbwheel at 14.4" || bad "cad q ray --frame"
fi
# 4b smoke: cadcheck runs on the live v1 project blend (frozen at attempt 3 since v1 stopped); reports, never asserts
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
