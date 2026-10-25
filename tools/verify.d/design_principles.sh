# design-principles.md: every FINDINGS ID it cites exists, and both skills point at it.
DP="$ROOT/skills/print-cad-blender/reference/design-principles.md"
missing=""
for id in $(grep -oE 'A[0-9]-[FTV][0-9]+' "$DP" | sort -u); do
  grep -q "$id" "$ROOT/docs/FINDINGS.md" || missing="$missing $id"
done
[ -z "$missing" ] && ok "design principles: every cited FINDINGS ID exists" || bad "design principles: unknown IDs$missing"
grep -q "reference/design-principles.md" "$ROOT/skills/print-cad-blender/SKILL.md" \
  && grep -q "design-principles.md" "$ROOT/skills/cad-design-review/checklist.md" \
  && grep -q "design-principles.md" "$ROOT/skills/cad-design-review/rubric.md" \
  && ok "design principles: linked from both skills" || bad "design principles: a link is missing"
