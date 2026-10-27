# printcheck-overhangs: the face pass for sloped overhangs, STL edges in more than two faces, --where and layer sections.
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V $BL, calls ok/bad). About 1.5 min (1 min plain python3, one Blender
# run for cad q overhangs). Evidence: the PR "printcheck: sloped overhangs" and docs/features/blend-bracket.md "The printcheck gap".
PO="$V/pc-overhangs"; mkdir -p "$PO"
SCR="$ROOT/skills/print-cad-blender/scripts"
V27="$ROOT/examples/mm-launcher-v2a7"
mkdir -p "$PO/v2" && tar -C "$PO/v2" -xzf "$V27/stl.tar.gz"
nice -n 10 python3 -I "$ROOT/tools/verify.d/printcheck_overhangs_cases.py" "$SCR" "$PO/v2/stl" "$V27/manifest.json" "$PO/out" > "$PO/cases.txt" 2>&1
for c in ramp_5 ramp_10 ramp_15 ramp_20 ramp_30 ramp_40; do
  grep -q "\"case\": \"$c\", \"ok\": true" "$PO/cases.txt" && ok "printcheck face pass fails the $c ramp (the layer check alone: 0 fails)" || bad "printcheck $c: $(grep "\"$c\"" "$PO/cases.txt" | cut -c1-240)"
done
for c in ramp_45 ramp_50 tube_between_walls hole_6 hole_20; do   # negative controls: self-supporting slopes and sloped bridges
  grep -q "\"case\": \"$c\", \"ok\": true" "$PO/cases.txt" && ok "printcheck face pass leaves $c alone" || bad "printcheck $c: $(grep "\"$c\"" "$PO/cases.txt" | cut -c1-240)"
done
grep -q '"case": "tube_off_one_wall", "ok": true' "$PO/cases.txt" && ok "printcheck face pass fails a 20 mm tube 30 mm off one wall" || bad "printcheck tube off one wall: $(grep tube_off "$PO/cases.txt")"
grep -q '"case": "prior_art_area_rule", "ok": true' "$PO/cases.txt" \
  && ok "prior_art/overhang_regions.py agrees on the ramps (400 mm2 projected) and would fail the 20 mm hole and the bridged tube (283 mm2)" \
  || bad "prior-art cross-check: $(grep prior_art "$PO/cases.txt" | cut -c1-300)"
grep -q '"case": "v2_face_pass", "ok": true' "$PO/cases.txt" \
  && ok "printcheck v2 STLs: the face pass adds no fail or warn (max 1.6 mm past 45 deg, beam); fails stay jar_valve, feeder_cover, base_shell, post_R" \
  || bad "printcheck v2 face pass: $(grep v2_face "$PO/cases.txt" | cut -c1-400)"
grep -q '"case": "v2_stl_edges", "ok": true' "$PO/cases.txt" \
  && ok "printcheck v2 STLs: base_shell's 7 edges in 4 faces warn; hood's 4 nm slivers and every other part: 0" || bad "printcheck STL edges: $(grep v2_stl "$PO/cases.txt")"
grep -q '"case": "jar_valve_print_evidence", "ok": true' "$PO/cases.txt" \
  && ok "jar_valve (printed 2026-10-26, drooped): printcheck exits 1, --where lists the 3 tabs at z 2 with world coordinates, --section auto shows them" \
  || bad "jar_valve print evidence: $(grep jar_valve "$PO/cases.txt")"
# cad q overhangs on the v2a7 model: reads stl/jar_valve.stl next to the blend (section 4m extracted both)
if [ -f "$V/pc-v2/blender/model.blend" ]; then
  CAD_LAYER_CHECK=1 $CAD q "$V/pc-v2/blender/model.blend" overhangs PRT_jar_valve --section auto > "$PO/q.txt" 2>&1
  [ "$(grep -c '^CADQ| FAIL    layer z   2.0 .*world \[' "$PO/q.txt")" = 3 ] && grep -q '^CADQ| section z 2.1' "$PO/q.txt" \
    && grep -q '"source": "stl/jar_valve.stl"' "$PO/q.txt" \
    && ok "cad q overhangs PRT_jar_valve: 3 tab regions at z 2 with world coordinates and a layer section, from stl/jar_valve.stl" \
    || bad "cad q overhangs: $(head -c 400 "$PO/q.txt")"
fi
