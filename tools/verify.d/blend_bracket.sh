# blend-bracket: cadlib.blend grows the 6-way tube node and the servo bracket; geom.swept_envelope holds every pose.
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V $BL, calls ok/bad). About 25 s. Evidence: docs/features/blend-bracket.md.
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
$CAD check "$BB/node/node.blend" "" "$BB/node/cadcheck.json" --only parts >/dev/null
python3 -I -c "
import json,sys; d=json.load(open(sys.argv[1])); r=d['checks']['parts']['rows'][0]
sys.exit(0 if d['summary']['fails']==0 and r['non_manifold_edges']==0 and r['fits']['P1S'] and r['min_wall_mm']>=4.0 else 1)" "$BB/node/cadcheck.json" \
  && ok "blend node: cadcheck parts 0 fails, fits P1S, wall probe >= 4.0" || bad "blend node: cadcheck parts"

# swept envelope: every vertex and edge midpoint of 25 random poses inside (synthetic L arm, and the A3 nacelle if present)
sweep() { nice -n 10 "$BL" -b --factory-startup "$@" 2>&1 | grep '^SWEEPCHK' | sed 's/^SWEEPCHK //'; }
S1=$(sweep --python "$ROOT/tools/verify.d/blend_bracket_sweep.py" -- "$SCR")
echo "$S1" | grep -q '"outside": 0,' && echo "$S1" | grep -q '"non_manifold_edges": 0' \
  && ok "swept envelope contains 25 random poses of an L arm: $S1" || bad "swept envelope (L arm): $S1"
S2=$(sweep --python "$ROOT/tools/verify.d/blend_bracket_sweep.py" -- "$SCR" union)
echo "$S2" | grep -q '"outside": 0,' && bad "containment check has no teeth: union of 5 deg poses passed" \
  || ok "containment check fails the 5 deg pose union (negative control): $S2"
if [ -f "$V/a3/mm_launcher.blend" ]; then
  S3=$(sweep "$V/a3/mm_launcher.blend" --python "$ROOT/tools/verify.d/blend_bracket_sweep.py" -- "$SCR" PRT_nacelle PIV_tilt -3 46)
  echo "$S3" | grep -q '"outside": 0,' && echo "$S3" | grep -q '"non_manifold_edges": 0' \
    && ok "swept envelope contains 25 random poses of A3 PRT_nacelle over PIV_tilt -3..46: $S3" || bad "swept envelope (A3 nacelle): $S3"
fi

# bracket: servo cradle fit, closed, prints without supports, with the arm sweep as a keep-out
$CAD build "$ROOT/examples/blend-bracket/build.py" -- --out "$BB/bracket" >/dev/null
python3 -I -c "
import json,sys; r=json.load(open(sys.argv[1])); g=r['grow']; s=r['holds']['servo']
sys.exit(0 if g['non_manifold_edges']==0 and s['fit_ok'] and s['missed']==0 and s['wall_min']>=3.0 and r['orientation']['overhang_mm2']<50 else 1)" "$BB/bracket/report.json" \
  && ok "blend bracket: closed, servo fit within 0.05 mm, wall >= 3, no overhang" || bad "blend bracket: $(head -c 400 "$BB/bracket/report.json")"
