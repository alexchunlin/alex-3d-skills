# cadlib.geom.csg gives new faces the base's material (push-assist PA-A4-T14: cut walls on an empty slot rendered grey).
# watch: @core tools/verify.d/csg_material_cases.py
# Sourced by tools/verify_all.sh (uses $ROOT $V $BL, calls ok/bad). About 5 s. On origin/next before the fix the recut
# and second-slot cases fail (walls on the empty slot, walls on slot 0's other material); the bare and coloured tool
# cases passed before too (the common case, unchanged). The PR #17 review added a tool carrying the base's other
# material (walls took it) and a cutter sharing its mesh with a kept part (the kept part was recoloured).
mkdir -p "$V/csgmat"
nice -n 10 "$BL" -b --factory-startup --python "$ROOT/tools/verify.d/csg_material_cases.py" -- "$ROOT/skills/print-cad-blender/scripts" 2>&1 \
  | grep '^CSGMAT' | cut -c8- > "$V/csgmat/cases.jsonl"
for c in "recut, tool faces on index 1" "bare tool" "coloured tool" "two tools" "union and intersect" "part on its second slot" "bare part stays bare" \
         "tool carries the base's other material" "shared cutter mesh"; do
  grep -F "\"case\": \"$c\"" "$V/csgmat/cases.jsonl" | grep -q '"ok": true' && ok "csg material: $c" \
    || bad "csg material: $c: $(grep -F "\"case\": \"$c\"" "$V/csgmat/cases.jsonl" || echo 'no output')"
done
