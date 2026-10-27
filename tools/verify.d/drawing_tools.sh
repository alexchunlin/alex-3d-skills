# tools/drawing (draw: text, scale, measure, holes, overlay) on a synthetic sheet with known answers and on
# hand-labelled CADGenBench dev drawings (tools/verify.d/drawing_tools_cases.py). Sourced by tools/verify_all.sh
# (uses $ROOT $V; calls ok/bad). Needs /tmp/drawtools-venv (sh tools/drawing/setup_venv.sh); the dev rows need
# /tmp/cgb-data. About 4 minutes, most of it OCR.
DTV="$V/drawing"; mkdir -p "$DTV"
DTPY="${DRAWTOOLS_PY:-/tmp/drawtools-venv/bin/python}"
if [ ! -x "$DTPY" ]; then
  bad "drawing tools: $DTPY missing (sh tools/drawing/setup_venv.sh)"
else
  DRAWTOOLS_CACHE="$DTV/cache" nice -n 10 "$DTPY" -I "$ROOT/tools/verify.d/drawing_tools_cases.py" "$DTV" \
    > "$DTV/cases.jsonl" 2> "$DTV/cases.err"
  dt() {   # dt "message" 'python condition on c (dict: case name -> row)'
    python3 -I -c "
import json, re, sys
c = {}
for l in open(sys.argv[1]):
    l = l.strip()
    if l.startswith('{'):
        d = json.loads(l); c[d['case']] = d
num = lambda s, pat: float(re.search(pat, s).group(1))
sys.exit(0 if ($2) else 1)" "$DTV/cases.jsonl" 2>/dev/null && ok "$1" || bad "$1 (see $DTV/cases.jsonl, cases.err)"
  }
  dt "drawing text: all 8 dimension texts on the synthetic sheet, incl. 3 vertical ones; '3X Ø8 THRU' parsed as 3x dia 8 THRU" \
     "not c['synth_text']['missing'] and c['synth_text']['callout']['count'] == 3 and c['synth_text']['callout']['value'] == 8 and 'THRU' in c['synth_text']['callout']['flags']"
  dt "drawing scale --auto: synthetic sheet 3.000 px/mm within 0.5% from 3+ dimension lines" \
     "abs(c['synth_scale']['clusters'][0]['px_per_mm'] / 3 - 1) < 0.005 and c['synth_scale']['clusters'][0]['n'] >= 3"
  dt "drawing holes: 3x Ø8 within 0.2 mm at their positions within 0.3 mm, and the Ø12/Ø24 boss as one concentric set" \
     "any(p['n'] == 3 and abs(p['dias'][0] - 8) < 0.2 and all(min(abs(x - a) + abs(y - b) for a, b in ((20, 20), (20, 60), (100, 15))) < 0.3 for x, y in p['centres']) for p in c['synth_holes']['patterns']) and any(len(p['dias']) == 2 and abs(p['dias'][0] - 12) < 0.2 and abs(p['dias'][1] - 24) < 0.2 for p in c['synth_holes']['patterns'])"
  dt "drawing measure: snapped 120 mm dimension within 0.2 mm; circle at the boss centre Ø12 within 0.2 mm" \
     "abs(num(c['synth_measure']['out'], r'= ([0-9.]+) mm') - 120) < 0.2 and abs(num(c['synth_measure']['out'], r'Ø ([0-9.]+) mm') - 12) < 0.2"
  dt "drawing overlay: the reference part reads 'as modelled' in the top and front views, and with --view all picks top" \
     "c['synth_overlay_ref.step_top']['verdict'].startswith('OK') and c['synth_overlay_ref.step_front']['verdict'].startswith('OK') and c['synth_overlay_ref.step_all']['verdict'].startswith('OK') and 'view top' in c['synth_overlay_ref.step_all']['head']"
  dt "drawing overlay: planted flips caught (rotated 180 in top, STEP and STL; mirrored left-right; base turned over -> mirrored top-bottom in front)" \
     "\"'rotated 180'\" in c['synth_overlay_rot180z.step_top']['verdict'] and \"'rotated 180'\" in c['synth_overlay_rot180z.stl_top']['verdict'] and \"'mirrored left-right'\" in c['synth_overlay_mirx.step_top']['verdict'] and \"'mirrored top-bottom'\" in c['synth_overlay_flipx.step_front']['verdict']"
  if grep -q '"dev_skipped"' "$DTV/cases.jsonl"; then
    ok "drawing tools: dev-drawing rows skipped (/tmp/cgb-data missing)"
  else
    dt "drawing text on 5 hand-labelled dev drawings: precision >= 0.90 and recall >= 0.85" \
       "c['dev_text']['P'] >= 0.90 and c['dev_text']['R'] >= 0.85"
    dt "drawing scale --auto on dev 102: within 0.5% of a two-point calibration on its 220 mm dimension" \
       "abs(num(c['dev_scale_102']['auto'], r'scale ([0-9.]+) px/mm') / num(c['dev_scale_102']['manual'], r'scale ([0-9.]+) px/mm') - 1) < 0.005"
    dt "drawing holes on dev 145/102: 7+ of 8 called-out diameters found, mean error <= 0.3 mm" \
       "int(re.search(r'ALL: (\\d+)/', c['dev_circles']['out']).group(1)) >= 7 and num(c['dev_circles']['out'], r'mean \\|err\\| ([0-9.]+) mm') <= 0.3"
    dt "drawing overlay on dev 142 (part traced from its profile view): as modelled OK; planted rotate 180, mirror, rotate 90 caught" \
       "c['dev_overlay142_ref']['verdict'].startswith('OK') and \"'rotated 180'\" in c['dev_overlay142_rot180']['verdict'] and \"'mirrored left-right'\" in c['dev_overlay142_mirlr']['verdict'] and \"'rotated 90 CW'\" in c['dev_overlay142_rot90']['verdict']"
  fi
fi
