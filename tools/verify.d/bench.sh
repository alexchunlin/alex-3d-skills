# tools/bench smoke test (sourced by verify_all.sh; uses $ROOT, $V and ok/bad).
# 1. The locator lint on labels.json: no top-level |, no check '*', every locator names an object, no pinned numbers.
# 2. The scoring rules on JSON fixtures (no Blender), and two mutants of replay.py that must fail them.
# 3. The scorer on verify_all's own v2 A7 reports (no Blender; the commit comes from $V/meta.json).
# 4. The runner on one attempt, one run (v2 A6 layer check, about 10 s): the 4 printability findings fail, nothing else.
# 5. labels.json vs verify_all's per-attempt assertions: a report, never a failure.
B="$ROOT/tools/bench/replay.py"
mkdir -p "$V/bench"
python3 -I "$B" lint > "$V/bench/lint.txt" 2>&1 && ok "bench labels: locator lint clean" || bad "bench labels: locator lint (see $V/bench/lint.txt)"
python3 -I "$ROOT/tools/bench/test_replay.py" > "$V/bench/fixtures.txt" 2>&1 && grep -q "^BENCH_FIXTURES ok" "$V/bench/fixtures.txt" \
  && ok "bench scoring fixtures: check prefix, accepted, partial, rows-only, crashed run, false fail, noise, lint; ignore-prefix and no-false-fail mutants killed" \
  || bad "bench scoring fixtures (see $V/bench/fixtures.txt)"
if [ -f "$V/v2a7/cadcheck.json" ] && [ -f "$V/meta.json" ]; then
  python3 -I "$B" --from-verify "$V" --attempts v2a7 --results "$V/bench/verify.jsonl" --quiet >/dev/null 2>&1
  python3 -I -c "
import json,sys; r=[json.loads(l) for l in open(sys.argv[1])][0]; p=r['per_label']
ok = (r['attempt'] == 'v2a7' and r['labels'] == 4 and r['caught_fail'] == 0 and r['caught_fw'] == 3 and r['caught_fw_rows'] == 3
      and r['false_fails'] == 0 and r['pf_fail'] == 4 and r['pf_findings'] == 4 and p['A7-01']['designer'] == 'warn' and p['A7-03']['rows'] is None
      and 'needs PIV_tilt at 45' in p['A7-01']['designer_line'] and not r['errors'] and r.get('commit_assumed') is None)
sys.exit(0 if ok else 1)" "$V/bench/verify.jsonl" \
    && ok "bench scorer on verify's v2a7 reports: 3 of 4 reviewer labels warn (A7-03 missed), 0 false fails, 4/4 support findings fail" \
    || bad "bench scorer on verify's v2a7 reports (see $V/bench/verify.jsonl)"
fi
python3 -I "$B" --attempts v2a6 --runs layer --results "$V/bench/run.jsonl" --quiet >/dev/null 2>&1
python3 -I -c "
import json,sys; r=[json.loads(l) for l in open(sys.argv[1])][0]
ok = (r['attempt'] == 'v2a6' and r['pf_fail'] == 4 and r['pf_findings'] == 4 and all(e['designer'] == 'fail' for e in r['pf'].values())
      and r['false_fails'] == 0 and not r['errors'] and r['runs_subset'] == ['layer'])
sys.exit(0 if ok else 1)" "$V/bench/run.jsonl" \
  && ok "bench runner, v2a6 layer run: the 4 support findings fail, 0 false fails" || bad "bench runner on v2a6 (see $V/bench/run.jsonl)"
if [ -f "$V/v2a7/cadcheck.json" ] && [ -f "$V/meta.json" ]; then
  python3 -I "$B" xcheck --from-verify "$V" > "$V/bench/xcheck.txt" 2>&1 \
    && echo "NOTE bench labels vs verify_all assertions: $(grep -c '^- ' "$V/bench/xcheck.txt") lists in $V/bench/xcheck.txt (report only)"
fi
