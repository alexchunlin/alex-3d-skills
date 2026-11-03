# cad check --only/--quick is a partial run: it says so, and never lands on the full report's path (issue #28; agentcad
# #237: a model rejected by the full profile switched to the reduced one and submitted). About 40 s: one --bug build, three checks.
# watch: @core examples/demo-turret/**
OP="$V/only-bug"; mkdir -p "$OP"
CADW="${CAD:-$ROOT/skills/print-cad-blender/scripts/cad}"
$CADW build "$ROOT/examples/demo-turret/build.py" --out "$OP" --bug > "$OP/build.log" 2>&1
rm -f "$OP/cadcheck.json" "$OP/cadcheck.partial.json"
$CADW check "$OP/demo.blend" "$ROOT/examples/demo-turret/checks.json" --only stability > "$OP/partial.txt" 2>&1
if grep -Eq '^CADCHECK PASS' "$OP/partial.txt"; then bad "--only stability printed a bare CADCHECK PASS"
elif grep -q '^CADCHECK PARTIAL ' "$OP/partial.txt" && grep -q 'skipped checks:' "$OP/partial.txt"; then ok "--only stability prints CADCHECK PARTIAL and lists the skipped checks"
else bad "--only stability summary is neither a bare PASS nor PARTIAL (see $OP/partial.txt)"; fi
[ ! -e "$OP/cadcheck.json" ] && [ -f "$OP/cadcheck.partial.json" ] && ok "--only with no OUT writes cadcheck.partial.json and leaves cadcheck.json alone" || bad "--only with no OUT touched cadcheck.json or wrote no partial report"
python3 -I -c "
import json, sys; r = json.load(open(sys.argv[1]))['run']
sys.exit(0 if r == {'only': ['stability'], 'quick': False} else 1)" "$OP/cadcheck.partial.json" \
  && ok "partial report has run.only == [stability], run.quick false" || bad "partial report run field"
$CADW check "$OP/demo.blend" "$ROOT/examples/demo-turret/checks.json" --quick > "$OP/quick.txt" 2>&1
grep -q '^CADCHECK PARTIAL ' "$OP/quick.txt" && [ ! -e "$OP/cadcheck.json" ] && ok "--quick prints CADCHECK PARTIAL and does not write cadcheck.json" || bad "--quick summary or path"
# negative control: the full run on the same planted-bug model still FAILs and writes cadcheck.json with run.only == []
$CADW check "$OP/demo.blend" "$ROOT/examples/demo-turret/checks.json" > "$OP/full.txt" 2>&1
grep -Eq '^CADCHECK FAIL: 9 fail' "$OP/full.txt" && ! grep -q PARTIAL "$OP/full.txt" && [ -f "$OP/cadcheck.json" ] \
  && ok "negative control: the full run on the --bug turret still prints CADCHECK FAIL: 9 fail" || bad "full --bug run: expected 'CADCHECK FAIL: 9 fail' (see $OP/full.txt)"
python3 -I -c "
import json, sys; r = json.load(open(sys.argv[1]))['run']
sys.exit(0 if r == {'only': [], 'quick': False} else 1)" "$OP/cadcheck.json" && ok "full report has run.only == [], run.quick false" || bad "full report run field"
