# cad bom reads cadcheck's one stock table, so M5 has a row: M5 x 13 is flagged, M5 x 12 is not (issue #29: cadbom's own
# copy had no M5, so any M5 length passed). No Blender, plain python3, about 1 s.
# watch: @core skills/print-cad-blender/scripts/cadbom.py skills/print-cad-blender/scripts/cadcfg.py skills/print-cad-blender/scripts/cadcheck.py
BM="$V/bom-m5"; mkdir -p "$BM"
CADW="${CAD:-$ROOT/skills/print-cad-blender/scripts/cad}"
cat > "$BM/manifest12.json" <<'J'
{"parts": {"FST_m5_a": {"kind": "FST", "spec": "M5_cap", "length": 12.0, "part": "M5_cap x 12"}}}
J
cat > "$BM/manifest13.json" <<'J'
{"parts": {"FST_m5_a": {"kind": "FST", "spec": "M5_cap", "length": 13.0, "part": "M5_cap x 13"}}}
J
printf '| Part | Qty | Where |\n|---|---|---|\n| M5 x 12 cap | 1 | `FST_m5_a` |\n' > "$BM/bom12.md"
printf '| Part | Qty | Where |\n|---|---|---|\n| M5 x 13 cap | 1 | `FST_m5_a` |\n' > "$BM/bom13.md"
rc12=0; rc13=0
$CADW bom "$BM/bom12.md" "$BM/manifest12.json" > "$BM/out12.txt" 2>&1 || rc12=$?
$CADW bom "$BM/bom13.md" "$BM/manifest13.json" > "$BM/out13.txt" 2>&1 || rc13=$?
[ $rc12 = 0 ] && ! grep -q "stock length" "$BM/out12.txt" && ok "cad bom: M5 x 12 is a stock length" || bad "cad bom: M5 x 12 flagged (see $BM/out12.txt)"
# negative control: the unstocked length must be caught (before the fix this passed, rc 0)
[ $rc13 = 1 ] && grep -q "M5 x 13 is not a stock length" "$BM/out13.txt" && ok "cad bom: M5 x 13 flagged as not a stock length" || bad "cad bom: M5 x 13 not flagged (see $BM/out13.txt)"
