# cadlib.mates (sourced by tools/verify_all.sh; uses $ROOT $CAD $V, calls ok/bad). Writes under $V/mates.
# 1. unit cases (tools/verify.d/mates_cases.py): frames, chains, flips, prismatic, patterns, loops, errors, print_rot
# 2. the demo turret placed through mates (examples/demo-turret/build_mates.py) gives build.py's cadcheck rows
# 3. its planted pattern mismatch fails the build with both specs; 4. `cad mates` on a manifest and a blend
# 5. the mates_task and mates_task_v2 scorers on their reference solutions and planted errors (tools/bench/)
mkdir -p "$V/mates"
$CAD build "$ROOT/tools/verify.d/mates_cases.py" --out "$V/mates/cases" > "$V/mates/cases.log" 2>&1
grep "^MATES \(PASS\|FAIL\)" "$V/mates/cases.log" | while read -r _ st msg; do echo "$st mates $msg"; done > "$V/mates/cases.txt"
[ "$(grep -c . "$V/mates/cases.txt")" -ge 27 ] || echo "FAIL mates cases: only $(grep -c . "$V/mates/cases.txt") of 27 case lines (log $V/mates/cases.log)" >> "$V/mates/cases.txt"
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/mates/cases.txt"

# 2. same design, two placements; the absolute build is section 1's demo-clean when it ran in this verify run
ABS="$V/demo-clean/cadcheck.json"
if [ ! -f "$ABS" ]; then
  $CAD build "$ROOT/examples/demo-turret/build.py" --out "$V/mates/demo-abs" >/dev/null 2>&1
  CAD_LAYER_CHECK=1 $CAD check "$V/mates/demo-abs/demo.blend" "$ROOT/examples/demo-turret/checks.json" "$V/mates/demo-abs/cadcheck.json" >/dev/null 2>&1
  ABS="$V/mates/demo-abs/cadcheck.json"
fi
$CAD build "$ROOT/examples/demo-turret/build_mates.py" --out "$V/mates/demo" > "$V/mates/demo.log" 2>&1
CAD_LAYER_CHECK=1 $CAD check "$V/mates/demo/demo.blend" "$ROOT/examples/demo-turret/checks.json" "$V/mates/demo/cadcheck.json" >/dev/null 2>&1
python3 -I "$ROOT/tools/verify.d/mates_compare.py" "$ABS" "$V/mates/demo/cadcheck.json" > "$V/mates/compare.txt" 2>&1
[ "$(grep -c '^CMP ' "$V/mates/compare.txt")" = 4 ] || echo "CMP FAIL compare did not run ($V/mates/compare.txt)" >> "$V/mates/compare.txt"
grep '^CMP ' "$V/mates/compare.txt" | while read -r _ st msg; do echo "$st demo through mates vs absolute: $msg"; done > "$V/mates/compare_asserts.txt"
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/mates/compare_asserts.txt"

# 3. planted bug: the servo seat's pattern typed 0.5 mm off
$CAD build "$ROOT/examples/demo-turret/build_mates.py" --out "$V/mates/demo-bug" --bug-pattern > "$V/mates/demo-bug.log" 2>&1; rc=$?
[ $rc != 0 ] && grep -q "BUILD FAILED" "$V/mates/demo-bug.log" && grep -q "rect(10, 30.5)" "$V/mates/demo-bug.log" && grep -q "rect(10, 30) " "$V/mates/demo-bug.log" \
  && ok "demo through mates, planted pattern mismatch: build fails (exit $rc) printing rect(10, 30.5) and rect(10, 30)" \
  || bad "demo through mates, planted pattern mismatch not refused (exit $rc, $V/mates/demo-bug.log)"

# 4. the mate table, from the manifest (no Blender) and from the blend
$CAD mates "$V/mates/demo/manifest.json" > "$V/mates/mates_manifest.txt" 2>&1
$CAD mates "$V/mates/demo/demo.blend" > "$V/mates/mates_blend.txt" 2>&1
[ "$(grep -c . "$V/mates/mates_manifest.txt")" = 7 ] && grep -q "^PIV_tilt  *revolute  *PRT_arm_L:pivot > PRT_barrel:end_L  axis +X" "$V/mates/mates_manifest.txt" \
  && grep -q "^arm_L .*1x M3 selftap pan sink 2.8 head on a: FST_arm_0 L10" "$V/mates/mates_manifest.txt" \
  && cmp -s "$V/mates/mates_manifest.txt" "$V/mates/mates_blend.txt" \
  && ok "cad mates: 7 demo mates, one line each, the same from manifest.json and demo.blend" || bad "cad mates ($V/mates/mates_manifest.txt)"
$CAD mates "$V/mates/demo/manifest.json" "M3 nut" | grep -q "^side .*FST_side" && ok "cad mates REGEX: the side bolt by 'M3 nut'" || bad "cad mates REGEX"

# 5. the evaluation kits' scorers (v1: placement given; v2: pan-tilt from interfaces)
if [ -f "$ROOT/tools/bench/mates_task/selftest.sh" ]; then
  sh "$ROOT/tools/bench/mates_task/selftest.sh" "$V/mates/kit" > "$V/mates/kit.log" 2>&1
  grep "^KIT \(PASS\|FAIL\)" "$V/mates/kit.log" | while read -r _ st msg; do echo "$st mates_task $msg"; done > "$V/mates/kit.txt"
  [ "$(grep -c . "$V/mates/kit.txt")" -ge 5 ] || echo "FAIL mates_task selftest: $(grep -c . "$V/mates/kit.txt") lines ($V/mates/kit.log)" >> "$V/mates/kit.txt"
  while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/mates/kit.txt"
fi
if [ -f "$ROOT/tools/bench/mates_task_v2/selftest.sh" ]; then
  sh "$ROOT/tools/bench/mates_task_v2/selftest.sh" "$V/mates/kit2" > "$V/mates/kit2.log" 2>&1
  grep "^KIT \(PASS\|FAIL\)" "$V/mates/kit2.log" | while read -r _ st msg; do echo "$st mates_task_v2 $msg"; done > "$V/mates/kit2.txt"
  [ "$(grep -c . "$V/mates/kit2.txt")" -ge 5 ] || echo "FAIL mates_task_v2 selftest: $(grep -c . "$V/mates/kit2.txt") lines ($V/mates/kit2.log)" >> "$V/mates/kit2.txt"
  while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/mates/kit2.txt"
fi
