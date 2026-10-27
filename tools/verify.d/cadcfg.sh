# checks.json hygiene (sourced by tools/verify_all.sh; uses $ROOT $V $BL, calls ok/bad). Writes under $V/cfg.
# Push-assist loop (docs/evidence-push-assist/loop-log.txt): typo'd keys ignored (PA-A4-T6), --only checks with no rows read as
# PASS (PA-A2-T11), substring accepts and no stale report under --only (PA-A4-T10), check_stacks died on a failed
# =expr (PA-A5-T26). The schema/doc agreement and accept cases run in plain python (cadcfg_cases.py); the rest in
# cadcheck on an empty scene (a few seconds each), and the suggestions are checked on verify's own v2 reports.
# watch: @core tools/verify.d/cadcfg_cases.py skills/print-cad-blender/reference/checks-config.md examples/mm-launcher-v2a3/** examples/mm-launcher-v2a7/** examples/demo-turret/**
CF="$V/cfg"; mkdir -p "$CF"
python3 -I "$ROOT/tools/verify.d/cadcfg_cases.py" "$ROOT" \
  "$V/v2a3/cadcheck.json" "$ROOT/examples/mm-launcher-v2a3/checks.json" "$V/v2a7/cadcheck.json" "$ROOT/examples/mm-launcher-v2a7/checks.json" \
  > "$CF/cases.txt" 2>&1 || echo "FAIL cadcfg: cases crashed (see $CF/cases.txt)" >> "$CF/cases.txt"
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$CF/cases.txt"
CCK="$ROOT/skills/print-cad-blender/scripts/cadcheck.py"
# a stacks term naming a missing param: config fail naming row and expression, row skipped, report written (PA-A5-T26)
printf '{"min_wall": "=NO_WALL", "stacks": [{"name": "stop gap", "limit": 0.6, "terms": [{"what": "pin in bore", "tol": "=PIN_TOL"}, {"what": "slot", "tol": 0.1}]}]}' > "$CF/stacks.json"
printf '{"OTHER": 1}' > "$CF/p_bad.json"; printf '{"PIN_TOL": 0.2}' > "$CF/p_ok.json"
"$BL" -b --factory-startup --python "$CCK" -- --config "$CF/stacks.json" --params "$CF/p_bad.json" --only stacks --out "$CF/stacks_bad.json" > "$CF/stacks_bad.log" 2>&1
"$BL" -b --factory-startup --python "$CCK" -- --config "$CF/stacks.json" --params "$CF/p_ok.json" --only stacks --out "$CF/stacks_ok.json" > "$CF/stacks_ok.log" 2>&1
python3 -I -c "
import json, sys
b, g = json.load(open(sys.argv[1]))['summary'], json.load(open(sys.argv[2]))
f = ' | '.join(b['fail_list'])
ok = (\"stacks[0].terms[0].tol: expression '=PIN_TOL' failed (NameError\" in f and \"stacks row 'stop gap' skipped\" in f
      and \"min_wall: expression '=NO_WALL' failed\" in f and 'using the default 1.6' in f and b['fails'] == 2
      and any(x.startswith('stacks: no stacks rows') for x in b['not_checked'])
      and g['checks']['stacks']['rows'][0]['worst_case'] == 0.3 and g['summary']['fails'] == 1)
sys.exit(0 if ok else 1)" "$CF/stacks_bad.json" "$CF/stacks_ok.json" 2>/dev/null && ! grep -q Traceback "$CF/stacks_bad.log" \
  && ok "stacks: a term naming a missing param is a config fail naming row and expression, row skipped (was a TypeError, no report); with the param the row runs" \
  || bad "stacks failed =expr (see $CF/stacks_bad.log)"
# --only with no rows, a typo'd key and --only name, and the accept triage, under --only and in a full run
cat > "$CF/only.json" <<'EOF'
{"flexure": [{"part": "PRT_x", "dir": [1, 0, 0]}],
 "stacks": [{"name": "wc", "limit": 0.3, "terms": [{"what": "a", "tol": 0.2}, {"what": "b", "tol": 0.2}]}],
 "accepted_warns": [{"check": "stacks", "kind": "worst case", "any": true, "why": "ok"}, {"check": "stacks", "kind": "RSS too big"},
                    {"check": "parts", "kind": "wall samples"}, {"match": "nothing like this"}, {"match": "worst case"}]}
EOF
"$BL" -b --factory-startup --python "$CCK" -- --config "$CF/only.json" --only stacks,slide,flexure,flexures --out "$CF/only_run.json" > "$CF/only_run.log" 2>&1
"$BL" -b --factory-startup --python "$CCK" -- --config "$CF/only.json" --out "$CF/full_run.json" > "$CF/full_run.log" 2>&1
python3 -I -c "
import json, sys
o, f = json.load(open(sys.argv[1]))['summary'], json.load(open(sys.argv[2]))['summary']
cw = ' | '.join(o['config_warns'])
ok = (o['warns'] == 1 and o['untriaged_warns'] == 0 and len(o['accepted_warns']) == 1
      and 'slide: no slide_out rows in the config, nothing checked' in o['not_checked'] and o['only_without_rows'] == ['slide']
      and \"unknown key 'flexure', ignored (did you mean 'flexures'?)\" in cw and \"--only: 'flexure' is not a check\" in cw
      and '2 of 5 entries use the old substring' in cw
      and o['stale_accepts'] == ['stacks: RSS too big'] and o['accepts_not_evaluated'] == ['parts: wall samples', 'nothing like this']
      and o['accept_suggestions'][0]['use'] == [{'check': 'stacks', 'kind': 'worst case', 'any': True}]
      and 'takes this kind of warn on every part' in cw
      and f['stale_accepts'] == ['stacks: RSS too big', 'parts: wall samples', 'nothing like this'] and not f['accepts_not_evaluated']
      and not f['only_without_rows'] and f['warns'] == 1)
sys.exit(0 if ok else 1)" "$CF/only_run.json" "$CF/full_run.json" 2>/dev/null \
  && ok "--only: rowless checks in not_checked and only_without_rows (flexures says its own); typo'd key and --only name are config warns, not design warns; stale vs not-evaluated accepts, under --only and in a full run" \
  || bad "--only gaps / config warns / accept triage (see $CF/only_run.json, $CF/full_run.json)"
# the review's crash cases on the demo turret (section 1 builds it): a failed =expr in a coupling ratio and in
# fasteners.min_engagement (TypeErrors, no report), a typo'd ray.sweep key (KeyError), and an --only naming no check
DB="$V/demo-clean/demo.blend"
if [ -f "$DB" ]; then
  printf '{"couplings": {"PIV_tilt": {"to": "PIV_pan", "ratio": "=NOPE"}}}' > "$CF/x_coupling.json"
  printf '{"fasteners": {"min_engagement": "=NOPE"}}' > "$CF/x_fmineng.json"
  printf '{"distances": [{"a": "PRT_pan", "b": "PRT_base", "min": 0.1, "ray": {"origin": [0, 0, 0], "dir": [0, 0, 1], "sweep": {"center": [0, 0, 0], "axis": [1, 0, 0], "form": 0, "to": 10}}}]}' > "$CF/x_form.json"
  for x in coupling fmineng; do
    "$BL" -b --factory-startup "$DB" --python "$CCK" -- --config "$CF/x_$x.json" --only stacks,fasteners,stability --out "$CF/x_$x.out.json" > "$CF/x_$x.log" 2>&1
  done
  "$BL" -b --factory-startup "$DB" --python "$CCK" -- --config "$CF/x_form.json" --only distances --out "$CF/x_form.out.json" > "$CF/x_form.log" 2>&1
  "$BL" -b --factory-startup "$DB" --python "$CCK" -- --config "$CF/x_form.json" --only flexure,distnces --out "$CF/x_none.out.json" > "$CF/x_none.log" 2>&1
  python3 -I -c "
import json, sys
d = sys.argv[1]
f = {x: ' | '.join(json.load(open('%s/x_%s.out.json' % (d, x)))['summary']['fail_list']) for x in ('coupling', 'fmineng', 'form', 'none')}
cw = ' | '.join(json.load(open(d + '/x_form.out.json'))['summary']['config_warns'])
ok = (\"couplings.PIV_tilt.ratio: expression '=NOPE' failed\" in f['coupling'] and \"couplings 'PIV_tilt' dropped\" in f['coupling']
      and \"fasteners.min_engagement: expression '=NOPE' failed\" in f['fmineng'] and 'fasteners.min_engagement dropped' in f['fmineng']
      and \"ray.sweep has no 'from'; row skipped\" in f['form'] and \"unknown key 'form', ignored (did you mean 'from'?)\" in cw
      and 'names no check, so nothing ran' in f['none'])
sys.exit(0 if ok else 1)" "$CF" 2>/dev/null && ! grep -l Traceback "$CF"/x_*.log >/dev/null \
    && ok "failed =expr in a coupling ratio and in fasteners.min_engagement, a typo'd ray.sweep key, an --only of no check: config fails, reports written (were TypeError/KeyError crashes)" \
    || bad "review crash cases (see $CF/x_*.log)"
fi
