# cad check --only/--quick is a partial run: it says so, and never lands on the full report's path (issue #28; agentcad
# #237: a model rejected by the full profile switched to the reduced one and submitted). About 50 s: one --bug build, four checks.
# watch: @core examples/demo-turret/**
OP="$V/only-bug"; mkdir -p "$OP"
CADW="${CAD:-$ROOT/skills/print-cad-blender/scripts/cad}"
$CADW build "$ROOT/examples/demo-turret/build.py" --out "$OP" --bug > "$OP/build.log" 2>&1
rm -f "$OP/cadcheck.json" "$OP/cadcheck.partial.json"
# negative control: the full run on the planted-bug model FAILs, writes cadcheck.json, and says it is a full run
$CADW check "$OP/demo.blend" "$ROOT/examples/demo-turret/checks.json" > "$OP/full.txt" 2>&1
grep -Eq '^CADCHECK FAIL: 9 fail' "$OP/full.txt" && ! grep -q PARTIAL "$OP/full.txt" && [ -f "$OP/cadcheck.json" ] \
  && ok "negative control: the full run on the --bug turret prints CADCHECK FAIL: 9 fail" || bad "full --bug run: expected 'CADCHECK FAIL: 9 fail' (see $OP/full.txt)"
python3 -I -c "
import json, sys; r = json.load(open(sys.argv[1]))['run']
sys.exit(0 if r == {'only': [], 'quick': False} else 1)" "$OP/cadcheck.json" && ok "full report has run.only == [], run.quick false" || bad "full report run field"
SUM0=$(shasum -a 256 "$OP/cadcheck.json" | cut -d' ' -f1)
# a partial run beside an existing full report must leave that report byte for byte alone (V2A5-T1)
$CADW check "$OP/demo.blend" "$ROOT/examples/demo-turret/checks.json" --only stability > "$OP/partial.txt" 2>&1
if grep -Eq '^CADCHECK PASS' "$OP/partial.txt"; then bad "--only stability printed a bare CADCHECK PASS"
elif grep -q '^CADCHECK PARTIAL ' "$OP/partial.txt" && grep -q 'skipped checks:' "$OP/partial.txt"; then ok "--only stability prints CADCHECK PARTIAL and lists the skipped checks"
else bad "--only stability summary is neither a bare PASS nor PARTIAL (see $OP/partial.txt)"; fi
[ "$(shasum -a 256 "$OP/cadcheck.json" | cut -d' ' -f1)" = "$SUM0" ] && [ -f "$OP/cadcheck.partial.json" ] \
  && ok "--only with no OUT leaves the existing full cadcheck.json byte for byte and writes cadcheck.partial.json" || bad "--only with no OUT changed cadcheck.json or wrote no partial report"
python3 -I -c "
import json, sys; r = json.load(open(sys.argv[1]))['run']
sys.exit(0 if r == {'only': ['stability'], 'quick': False} else 1)" "$OP/cadcheck.partial.json" \
  && ok "partial report has run.only == [stability], run.quick false" || bad "partial report run field"
$CADW rows "$OP/cadcheck.partial.json" --summary 2>&1 | grep -q '^run: only=stability quick=false' && $CADW rows "$OP/cadcheck.json" --summary 2>&1 | grep -q '^run: full' \
  && ok "cad rows --summary prints the run line (partial and full)" || bad "cad rows --summary run line"
# --quick: a reduced pose grid, no checks skipped, and the PARTIAL line says exactly that
rm -f "$OP/cadcheck.partial.json"
$CADW check "$OP/demo.blend" "$ROOT/examples/demo-turret/checks.json" --quick > "$OP/quick.txt" 2>&1
grep -q '^CADCHECK PARTIAL ' "$OP/quick.txt" && grep -q 'reduced pose grid, no checks skipped' "$OP/quick.txt" \
  && [ "$(shasum -a 256 "$OP/cadcheck.json" | cut -d' ' -f1)" = "$SUM0" ] && ok "--quick prints PARTIAL with 'reduced pose grid, no checks skipped' and leaves cadcheck.json alone" || bad "--quick summary or path"
python3 -I -c "
import json, sys; r = json.load(open(sys.argv[1]))['run']
sys.exit(0 if r == {'only': [], 'quick': True} else 1)" "$OP/cadcheck.partial.json" && ok "--quick report has run.quick true" || bad "--quick report run field"
# an empty --only is a full run (one rule, wrapper and cadcheck.py): cadcheck.json, not cadcheck.partial.json
rm -f "$OP/cadcheck.partial.json"
$CADW check "$OP/demo.blend" "$ROOT/examples/demo-turret/checks.json" --only "" > "$OP/empty.txt" 2>&1
grep -Eq '^CADCHECK FAIL: 9 fail' "$OP/empty.txt" && [ ! -e "$OP/cadcheck.partial.json" ] && ok "--only \"\" is a full run and writes cadcheck.json" || bad "--only \"\" handling (see $OP/empty.txt)"
# an empty string in the CONFIG slot is "no config" and the OUT after it still wins over the partial default
# (daily 2026-11-03: stl_read.sh and sweep_guard.sh pass "" and their reports landed in cadcheck.partial.json)
rm -f "$OP/cadcheck.partial.json" "$OP/empty_cfg.json"
$CADW check "$OP/demo.blend" "" "$OP/empty_cfg.json" --only stability > "$OP/empty_cfg.txt" 2>&1
[ -f "$OP/empty_cfg.json" ] && [ ! -e "$OP/cadcheck.partial.json" ] && ok "cad check: an empty CONFIG slot keeps the OUT after it" || bad "cad check: empty CONFIG slot lost the OUT (see $OP/empty_cfg.txt)"
