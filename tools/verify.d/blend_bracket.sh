# blend-bracket: cadlib.blend grows the 6-way tube node and the servo bracket; geom.swept_envelope holds every pose.
# watch: @core @layer examples/blend-node/** examples/blend-bracket/** tools/verify.d/blend_bracket_*.py examples/mm-launcher-a3/** components/**
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V $BL, calls ok/bad). About 6 min cold on a loaded machine (1.5 warm), most of it
# best_orientation running printcheck on 2-10 orientations per part (cached by triangles after the first run).
# Evidence: docs/features/blend-bracket.md.
BB="$V/bb"; mkdir -p "$BB"
SCR="$ROOT/skills/print-cad-blender/scripts"

# node: closed, every socket within 0.05 mm of the 0.2 mm fit (radial rays), walls at or above the 4 mm spec
$CAD build "$ROOT/examples/blend-node/build.py" -- --out "$BB/node" >/dev/null
python3 -I -c "
import json,sys; r=json.load(open(sys.argv[1])); g=r['grow']; h=r['holds']
c=[x for m in h.values() for x in (m['clearance_min'], m['clearance_max'])]
ok = g['non_manifold_edges']==0 and len(h)==6 and all(m['fit_ok'] and m['missed']==0 for m in h.values()) \
  and max(abs(x-0.2) for x in c) <= 0.05 and min(m['wall_min'] for m in h.values()) >= 4.0 and g['tris'] < 60000
print('clearance %.3f-%.3f, wall %.3f, %d tris, %.1f s' % (min(c), max(c), min(m['wall_min'] for m in h.values()), g['tris'], g['t_total_s']))
sys.exit(0 if ok else 1)" "$BB/node/report.json" > "$BB/node.txt" 2>&1 \
  && ok "blend node: closed, 6 sockets $(cat "$BB/node.txt")" || bad "blend node: $(cat "$BB/node.txt")"
# layer check on (verify_all exports CAD_LAYER_CHECK=0): the node declares supports, and printcheck must agree it needs them
CAD_LAYER_CHECK=1 $CAD check "$BB/node/node.blend" --only parts --out "$BB/node/cadcheck.json" >/dev/null
python3 -I -c "
import json,sys; d=json.load(open(sys.argv[1])); r=d['checks']['parts']['rows'][0]; L=r['layer_check']
sys.exit(0 if d['summary']['fails']==0 and r['non_manifold_edges']==0 and r['fits']['P1S'] and r['min_wall_mm']>=4.0 \
  and str(r['supports']).startswith('yes') == L['needs_support'] and L['n_islands']==0 else 1)" "$BB/node/cadcheck.json" \
  && ok "blend node: cadcheck parts 0 fails, fits P1S, wall probe >= 4.0, layer check agrees with best_orientation's supports" || bad "blend node: cadcheck parts"

# organic node (fillet 15, short grips): same fit and wall assertions
$CAD build "$ROOT/examples/blend-node/build.py" -- --out "$BB/node" --organic >/dev/null
python3 -I -c "
import json,sys; r=json.load(open(sys.argv[1])); g=r['grow']; h=r['holds']
c=[x for m in h.values() for x in (m['clearance_min'], m['clearance_max'])]
ok = g['non_manifold_edges']==0 and len(h)==6 and all(m['fit_ok'] and m['missed']==0 for m in h.values()) \
  and max(abs(x-0.2) for x in c) <= 0.05 and min(m['wall_min'] for m in h.values()) >= 4.0 and g['fillet']==15
print('clearance %.3f-%.3f, wall %.3f, %d tris' % (min(c), max(c), min(m['wall_min'] for m in h.values()), g['tris']))
sys.exit(0 if ok else 1)" "$BB/node/report_organic.json" > "$BB/node_organic.txt" 2>&1 \
  && ok "blend node --organic (fillet 15): closed, $(cat "$BB/node_organic.txt")" || bad "blend node --organic: $(cat "$BB/node_organic.txt")"

# size guard: oversized grow and sweep requests are refused before allocating
G1=$(nice -n 10 "$BL" -b --factory-startup --python "$ROOT/tools/verify.d/blend_bracket_guard.py" -- "$SCR" 2>&1 | grep '^GUARD' | sed 's/^GUARD //')
echo "$G1" | grep -q '"ok": true' && ok "blend size guard refuses 190M-cell grow and 76M-cell sweep before allocating: $(echo "$G1" | cut -c1-160)" \
  || bad "blend size guard: $G1"

# hold names: unnamed holds are numbered, duplicates raise; a print_up tube gets a teardrop bore that keeps its sleeve closed
H=$(nice -n 10 "$BL" -b --factory-startup -t 4 --python "$ROOT/tools/verify.d/blend_bracket_holds.py" -- "$SCR" 2>&1 | grep '^HOLDS' | sed 's/^HOLDS //')
echo "$H" | grep -q '"ok": true' && ok "blend holds: tube0/tube1 auto names, duplicate names raise, teardrop bore with fit kept: $(echo "$H" | cut -c1-220)" \
  || bad "blend holds: $H"

# swept envelope: every vertex and edge midpoint of 25 random poses inside (synthetic L arm, and the A3 nacelle if present)
sweep() { nice -n 10 "$BL" -b --factory-startup "$@" 2>&1 | grep '^SWEEPCHK' | sed 's/^SWEEPCHK //'; }
S1=$(sweep --python "$ROOT/tools/verify.d/blend_bracket_sweep.py" -- "$SCR")
echo "$S1" | grep -q '"outside": 0,' && echo "$S1" | grep -q '"non_manifold_edges": 0' \
  && ok "swept envelope contains 25 random poses of an L arm: $S1" || bad "swept envelope (L arm): $S1"
# coarse voxel and tight tol, checked at every mid-angle between poses: the old voxel / 4 pad left 74k of 611k points
# outside (0.55 mm) at voxel 1 / tol 0.05 and 33k at voxel 0.5 / tol 0.05 (PR #4 review)
for vt in "1.0 0.05" "0.5 0.05" "2.0 0.25"; do
  S=$(sweep --python "$ROOT/tools/verify.d/blend_bracket_sweep.py" -- "$SCR" dense $vt)
  echo "$S" | grep -q '"outside": 0,' && echo "$S" | grep -q '"non_manifold_edges": 0' \
    && ok "swept envelope, voxel/tol $vt, every mid-pose of an L arm inside: $S" || bad "swept envelope dense $vt: $S"
done
# a prismatic joint slides (0..50 mm along X: the envelope spans -10..60), a continuous joint sweeps 0..360
S=$(sweep --python "$ROOT/tools/verify.d/blend_bracket_sweep.py" -- "$SCR" slide)
echo "$S" | python3 -I -c "
import json,sys; d=json.loads(sys.stdin.read()); x=d['env_x']
sys.exit(0 if d['outside']==0 and d['kind']=='prismatic' and -11.5<x[0]<-10 and 60<x[1]<61.5 and d['non_manifold_edges']==0 else 1)" \
  && ok "swept envelope of a slide joint is a translation sweep: $S" || bad "swept envelope (slide): $S"
S=$(sweep --python "$ROOT/tools/verify.d/blend_bracket_sweep.py" -- "$SCR" wheel)
echo "$S" | grep -q '"outside": 0,' && echo "$S" | grep -q '"non_manifold_edges": 0' \
  && ok "swept envelope of a continuous joint (no lo/hi) covers 0..360: $S" || bad "swept envelope (continuous): $S"
S2=$(sweep --python "$ROOT/tools/verify.d/blend_bracket_sweep.py" -- "$SCR" union)
echo "$S2" | grep -q '"outside": 0,' && bad "containment check has no teeth: union of 5 deg poses passed" \
  || ok "containment check fails the 5 deg pose union (negative control): $S2"
# section 4c unpacks the A3 blend in a full run; a --changed run may skip 4c
[ -f "$V/a3/mm_launcher.blend" ] || { mkdir -p "$V/a3"; gunzip -c "$ROOT/examples/mm-launcher-a3/mm_launcher_a3.blend.gz" > "$V/a3/mm_launcher.blend"; }
if [ -f "$V/a3/mm_launcher.blend" ]; then
  S3=$(sweep "$V/a3/mm_launcher.blend" --python "$ROOT/tools/verify.d/blend_bracket_sweep.py" -- "$SCR" PRT_nacelle PIV_tilt -3 46)
  echo "$S3" | grep -q '"outside": 0,' && echo "$S3" | grep -q '"non_manifold_edges": 0' \
    && ok "swept envelope contains 25 random poses of A3 PRT_nacelle over PIV_tilt -3..46: $S3" || bad "swept envelope (A3 nacelle): $S3"
fi

# bracket: servo cradle fit, closed, prints without supports, with the arm sweep as a keep-out
$CAD build "$ROOT/examples/blend-bracket/build.py" -- --out "$BB/bracket" >/dev/null
python3 -I -c "
import json,sys; r=json.load(open(sys.argv[1])); g=r['grow']; s=r['holds']['servo']
o=r['orientation']; b=o['ranked'][0]
sys.exit(0 if g['non_manifold_edges']==0 and s['fit_ok'] and s['missed']==0 and s['wall_min']>=3.0 and o['best']=='clip -z face down' and b['fails']==0 and b['warns']==0 else 1)" "$BB/bracket/report.json" \
  && ok "blend bracket: closed, servo fit within 0.05 mm, wall >= 3, best_orientation picks the clip face with 0 printcheck fails or warns" || bad "blend bracket: $(head -c 400 "$BB/bracket/report.json")"
# best_orientation on the review's three connectors: the pick passes printcheck where the least-overhang direction did not
O=$(nice -n 10 "$BL" -b --factory-startup -t 4 --python "$ROOT/tools/verify.d/blend_bracket_orient.py" -- "$SCR" 2>&1 | grep '^ORIENT' | sed 's/^ORIENT //')
echo "$O" | grep -q '^ORIENT_ALL {"ok": true}' && ok "best_orientation picks a printcheck pass on n3, n4, brc: $(echo "$O" | grep -o '"part": "[^"]*", "ok": [a-z]*, "pick": "[^"]*"' | tr '\n' ' ')" \
  || bad "best_orientation on the review connectors: $(echo "$O" | cut -c1-300)"
# "supports: no" needs printcheck evidence (SKILL step 5): the layer check on the exported STL, 0 regions needing support
CAD_LAYER_CHECK=1 $CAD check "$BB/bracket/bracket.blend" --only parts --out "$BB/bracket/cadcheck.json" >/dev/null
python3 -I -c "
import json,sys; d=json.load(open(sys.argv[1])); r=d['checks']['parts']['rows'][0]; L=r['layer_check']
sys.exit(0 if d['summary']['fails']==0 and r['supports']=='no' and L['source'].endswith('bracket.stl') and not L['needs_support'] else 1)" "$BB/bracket/cadcheck.json" \
  && ok "blend bracket: supports: no holds, layer check on stl/bracket.stl finds nothing needing support" || bad "blend bracket: layer check"
