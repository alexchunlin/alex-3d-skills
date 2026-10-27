# cadlib.route (docs/features/cable-router.md): synthetic tray (block + wall slot + turntable bore), then one A3 re-route.
# watch: @core examples/cable-router/** examples/mm-launcher-a3/** tools/verify.d/inter_volume_cases.py tools/verify.d/route_bend_cases.py
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V; calls ok/bad). About 25 s.
CR="$V/cr"; mkdir -p "$CR"
$CAD build "$ROOT/examples/cable-router/build.py" --out "$CR" >/dev/null
if [ -f "$CR/route.json" ]; then
  python3 -I -c "
import json, math, sys
d = json.load(open(sys.argv[1]))
def seg_dist(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]; L2 = sum(x * x for x in ab) or 1e-12
    t = max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / L2))
    return math.dist(p, [a[i] + t * ab[i] for i in range(3)])
s, b = d['slot'], d['bore']
via = min(seg_dist((0, 15, 4), p, q) for p, q in zip(s['pts'], s['pts'][1:]))
ok = s['min_clearance_mm'] >= 0.95 and s['inside_samples'] == 0 and via < 0.05 and s['length_mm'] > s['straight_mm'] + 10
ok &= len(b['pieces']) == 2 and b['pieces'][1]['joint'] == 'PIV_turn' and b['slack'] and abs(b['slack'][0]['slack_mm']) < 0.5
ok &= b['min_clearance_mm'] >= 0.95
sys.exit(0 if ok else 1)" "$CR/route.json" \
    && ok "router: synthetic slot route keeps 1.0 mm clearance, passes the via, crosses the joint in 2 pieces with 0 slack" \
    || bad "router: synthetic route assertions (see $CR/route.json)"
  # independent of the router's own numbers: cadq distance to the block, and cadcheck finds no cable overlap
  $CAD q "$CR/route.blend" dist CAB_slot BUY_block | python3 -I -c "import json,sys; sys.exit(0 if json.loads(sys.stdin.read()[5:])['mm'] >= 0.95 else 1)" \
    && ok "router: cadq CAB_slot to BUY_block >= 0.95 mm" || bad "router: CAB_slot too close to BUY_block"
  $CAD check "$CR/route.blend" --out "$CR/cadcheck.json" --only interference >/dev/null
  python3 -I -c "
import json, sys; d = json.load(open(sys.argv[1]))['summary']
sys.exit(1 if [x for x in d['fail_list'] + d['warn_list'] if 'CAB_' in x] else 0)" "$CR/cadcheck.json" \
    && ok "router: cadcheck interference has no cable findings on the routed scene" || bad "router: cadcheck cable findings on the routed scene"
  # main's cable checks read the router's cab_path / cab_r: no kinks, no shared runs, the on-axis hand-over does not
  # drift; the two CAB_bore pieces meet with no connector, which is the one junction (a cable_chains row clears it)
  $CAD check "$CR/route.blend" --out "$CR/cadcheck_cables.json" --only cables >/dev/null
  python3 -I -c "
import json, sys; c = json.load(open(sys.argv[1]))['checks']['cables']
ok = c['kinks'] == [] and c['shared_runs'] == [] and c['ends_known'] == 3
ok &= all(r['moves_apart_mm'] <= 0.1 for r in c['end_drift']) and [j['cables'] for j in c['junctions']] == [['CAB_bore', 'CAB_bore_1']]
sys.exit(0 if ok else 1)" "$CR/cadcheck_cables.json" \
    && ok "router: cadcheck cables reads the routes (cab_path): 0 kinks, 0 shared runs, 0 end drift, the 2-piece junction only" \
    || bad "router: cadcheck cables on the routed scene (see $CR/cadcheck_cables.json)"
else
  bad "router: synthetic build wrote no route.json"
fi
# A3: CAB_12v_mg re-routed between its own endpoints has zero solid overlap (hand route: 1.7 mm3 in BUY_buck_12v)
A3B="$V/a3/mm_launcher.blend"
if [ ! -f "$A3B" ] && [ -f "$ROOT/examples/mm-launcher-a3/mm_launcher_a3.blend.gz" ]; then
  mkdir -p "$V/a3"; gunzip -c "$ROOT/examples/mm-launcher-a3/mm_launcher_a3.blend.gz" > "$A3B"
fi
# cadcheck inter_volume: the EXACT retry fixes the open-tube artefact (A3 CAB_12v_ctrl: raw 1331.9, real 38.0) and keeps
# real full containments (closed cube in a non-manifold box; open tube wholly in a box)
nice -n 10 "$BL" -b --factory-startup --python "$ROOT/tools/verify.d/inter_volume_cases.py" -- \
  "$ROOT/skills/print-cad-blender/scripts" "$A3B" 2>/dev/null | grep '^IVOL' | cut -c6- > "$CR/inter_volume.json"
python3 -I -c "
import json, sys; d = json.load(open(sys.argv[1]))
ok = d['inner_in_outer_mm3'] >= 0.98 * 125 and d['outer_around_inner_mm3'] >= 0.98 * 125 and not d['outer_manifold']
ok &= min(d['tube_inside_block_first_mm3'], d['tube_inside_tube_first_mm3']) >= 0.98 * d['tube_inside_own_mm3']
if 'a3_raw_ctrl_first_mm3' in d:
    ok &= d['a3_raw_ctrl_first_mm3'] >= 0.98 * d['a3_tube_own_mm3'] and abs(d['a3_ctrl_first_mm3'] - 38.0) < 1.0 and abs(d['a3_cab_first_mm3'] - 38.0) < 1.0
sys.exit(0 if ok else 1)" "$CR/inter_volume.json" \
  && ok "inter_volume: open A3 tube x controller 38.0 mm3 (raw EXACT 1331.9), full containments kept (125.0)" \
  || bad "inter_volume cases (see $CR/inter_volume.json)"
# router fillets vs the kink test: no arc under 0.75 x OD, none within one OD of a plug end (those corners stay sharp)
nice -n 10 "$BL" -b --factory-startup --python "$ROOT/tools/verify.d/route_bend_cases.py" -- \
  "$ROOT/skills/print-cad-blender/scripts" 2>/dev/null | grep '^IBEND' | cut -c7- > "$CR/route_bends.json"
python3 -I -c "
import json, sys; d = json.load(open(sys.argv[1]))
ok = d['bend_7.5']['radii'] == [7.5, 7.5] and d['bend_7.5']['sharp'] == 0
ok &= d['bend_1']['radii'] == [0.0, 0.0] and d['bend_1']['sharp'] == 2
ok &= d['end_corner']['radii'] == [0.0] and d['no_clearance']['radii'] == [0.0, 0.0] and d['no_clearance']['sharp'] == 2
sys.exit(0 if ok else 1)" "$CR/route_bends.json" \
  && ok "router: no fillet under 0.75 x OD or within one OD of a plug end; those corners stay sharp for the kink test" \
  || bad "router: fillet floor / end lead (see $CR/route_bends.json)"
if [ -f "$A3B" ]; then
  $CAD q "$A3B" route CAB_12v_mg --config "$ROOT/examples/mm-launcher-a3/checks.json" --json "$CR/a3_12v_mg.json" --save "$CR/a3_rerouted.blend" >/dev/null
  python3 -I -c "
import json, sys; r = json.load(open(sys.argv[1]))[0]
after = sum(v for d in r['after_overlap_mm3'].values() for v in d.values())
sys.exit(0 if (sum(r['hand']['overlap_mm3'].values()) > 1.0 and after == 0 and r['routed']['min_clearance_mm'] >= 0.95) else 1)" "$CR/a3_12v_mg.json" \
    && ok "router: A3 CAB_12v_mg re-route has 0 mm3 solid overlap (hand route 1.7)" || bad "router: A3 CAB_12v_mg re-route overlap (see $CR/a3_12v_mg.json)"
fi
