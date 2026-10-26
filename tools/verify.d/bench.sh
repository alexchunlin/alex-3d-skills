# tools/bench smoke test (sourced by verify_all.sh; uses $ROOT, $V and ok/bad).
# 1. The scorer on verify_all's own v2 A7 reports (no Blender): the labels, the designer/rows split and the false-fail
#    count must come out as tools/bench/README.md states for this tree.
# 2. The runner on one attempt, one run (v2 A6 layer check, about 10 s): gunzip, `cad check` with the layer check on,
#    and the score: the 4 post-freeze support misses fail, nothing else does.
B="$ROOT/tools/bench/replay.py"
mkdir -p "$V/bench"
python3 -I "$B" --from-verify "$V" --attempts v2a7 --results "$V/bench/verify.jsonl" --quiet >/dev/null 2>&1
python3 -I -c "
import json,sys; r=[json.loads(l) for l in open(sys.argv[1])][0]
ok = (r['attempt'] == 'v2a7' and r['labels'] == 8 and r['caught_fail'] == 4 and r['caught_fw'] == 7 and r['caught_fw_rows'] == 7
      and r['false_fails'] == 0 and r['per_label']['A7-01']['designer'] == 'warn' and r['per_label']['A7-03']['rows'] is None)
sys.exit(0 if ok else 1)" "$V/bench/verify.jsonl" \
  && ok "bench scorer on verify's v2a7 reports: 4 fail (support misses), 7 of 8 fail-or-warn, A7-03 missed, 0 false fails" \
  || bad "bench scorer on verify's v2a7 reports (see $V/bench/verify.jsonl)"
python3 -I "$B" --attempts v2a6 --runs layer --results "$V/bench/run.jsonl" --quiet >/dev/null 2>&1
python3 -I -c "
import json,sys; r=[json.loads(l) for l in open(sys.argv[1])][0]
pf=[k for k, v in r['per_label'].items() if k.startswith('V2PF')]
ok = (r['attempt'] == 'v2a6' and r['caught_fail'] == 4 and len(pf) == 4 and all(r['per_label'][k]['designer'] == 'fail' for k in pf)
      and r['false_fails'] == 0 and not r['errors'] and r['runtime_s'] > 0)
sys.exit(0 if ok else 1)" "$V/bench/run.jsonl" \
  && ok "bench runner, v2a6 layer run: the 4 support misses fail, 0 false fails" || bad "bench runner on v2a6 (see $V/bench/run.jsonl)"
