# design-principles.md: cited IDs exist exactly as cited, the doc is on-demand, and the template declares EB/CR (DP1).
DP="$ROOT/skills/print-cad-blender/reference/design-principles.md"
CL="$ROOT/skills/cad-design-review/checklist.md"
SK="$ROOT/skills/print-cad-blender/SKILL.md"
TPL="$ROOT/skills/print-cad-blender/templates/project"
# Full IDs with word boundaries (A1-F1 is not A1-F13 or V2A1-F1), in the files this feature edits. Review refs
# ("R3 #4") must name an issue that exists in that attempt's review, when the HW reviews are on this machine.
out=$(python3 -I - "$ROOT/docs/FINDINGS.md" "${HW:-}" "$DP" "$CL" "$SK" <<'EOF'
import os, re, sys
findings, hw, files = open(sys.argv[1]).read(), sys.argv[2], sys.argv[3:]
B, E = r'(?<![A-Za-z0-9])', r'(?![A-Za-z0-9])'
ID = re.compile(B + r'(?:V2)?(?:A[0-9]+-[FTVR][0-9]+|PF-[0-9]+)' + E)
bad, n = [], 0
for p in files:
    for i in sorted(set(ID.findall(open(p).read()))):
        n += 1
        if not re.search(B + re.escape(i) + E, findings): bad.append(i)
for a, k in sorted(set(re.findall(r'\bR([1-9]) #([0-9]+)', open(files[0]).read()))):
    rv = os.path.join(hw, 'renders', 'attempt-%s' % a, 'review.md')
    if not hw or not os.path.exists(rv): continue
    n += 1
    sec = re.search(r'^## (?:Issues|Findings)[^\n]*\n(.*?)(?=^## |\Z)', open(rv).read(), re.M | re.S)
    issues = re.findall(r'^(?:[0-9]+\. \*\*|### )', sec.group(1) if sec else '', re.M)
    if int(k) > len(issues): bad.append('R%s #%s' % (a, k))
print(n, ' '.join(bad))
EOF
)
set -- $out
[ "${1:-0}" -gt 0 ] && [ -z "${2:-}" ] && ok "design principles: all $1 cited IDs exist as cited" || bad "design principles: unknown IDs: ${out#* }"
# On-demand reference: one SKILL.md line, not an up-front read, and no rubric or checklist anchors on it.
grep "reference/design-principles.md" "$SK" | grep -q "Worth reading when" \
  && ! grep -q "design-principles" "$ROOT/skills/cad-design-review/rubric.md" "$CL" \
  && ok "design principles: on-demand link from SKILL.md only" || bad "design principles: SKILL.md link missing or read up front"
# DP1 by example: the template declares EB and CR and passes no literal to G.bevel or G.rrect; the checklist greps them.
grep -qE '^EB = ' "$TPL/params.py" && grep -qE '^CR = ' "$TPL/params.py" \
  && ! grep -nE 'G\.(bevel|rrect)\([^#]*, *[0-9.]+\)' "$TPL"/parts/*.py >/dev/null \
  && grep -q '`EB`/`CR`' "$CL" \
  && ok "design principles: template declares EB/CR and uses no literal radius or edge break" || bad "design principles: template EB/CR"
