# features.SIZES + RULES M3 overlay + cadcheck stock_lengths vs bd_warehouse's ISO tables (sourced by tools/verify_all.sh;
# uses $ROOT $V, calls ok/bad). Issue #37. Pure stdlib, no Blender: features.py imports mathutils, so the helper reads SIZES by ast.
# watch: @core tools/verify.d/sizes_vs_bdw.py tools/verify.d/sizes_vs_bdw_exceptions.json tools/prior_art/bd_warehouse_data/**
# Every disagreement beyond 0.05 mm (nut AF: exact) must be on sizes_vs_bdw_exceptions.json with a reason; an exception that
# stops firing is itself a failure; the vendored CSVs must still match SHA256SUMS. Controls: M4 nut AF 6.8 planted in ours
# (must be flagged), M3 pan dk set to bd's 5.6 (the exception must go stale), one CSV byte changed (the hash must catch it).
SB="$ROOT/tools/verify.d/sizes_vs_bdw.py"
mkdir -p "$V/sizes_bdw"
python3 -I "$SB" "$ROOT" > "$V/sizes_bdw/real.txt" 2>&1 && ok "sizes vs bd_warehouse: $(tail -1 "$V/sizes_bdw/real.txt")" \
  || bad "sizes vs bd_warehouse: unexcepted drift (see $V/sizes_bdw/real.txt)"
python3 -I "$SB" "$ROOT" --set M4.nut_af=6.8 > "$V/sizes_bdw/neg_af.txt" 2>&1
[ $? -eq 1 ] && grep -q "^DRIFT M4 nut_af: ours 6.8, bd_warehouse 7" "$V/sizes_bdw/neg_af.txt" \
  && ok "negative control: planted M4 nut AF 6.8 is flagged against ISO 4032 s 7" \
  || bad "negative control: planted M4 nut AF 6.8 not flagged (see $V/sizes_bdw/neg_af.txt)"
python3 -I "$SB" "$ROOT" --set M3.pan_d=5.6 > "$V/sizes_bdw/neg_stale.txt" 2>&1
[ $? -eq 1 ] && grep -q "^STALE exception M3 pan_d" "$V/sizes_bdw/neg_stale.txt" \
  && ok "negative control: an exception whose row now agrees is reported stale" \
  || bad "negative control: stale exception not reported (see $V/sizes_bdw/neg_stale.txt)"
rm -rf "$V/sizes_bdw/data"; cp -R "$ROOT/tools/prior_art/bd_warehouse_data" "$V/sizes_bdw/data"
echo >> "$V/sizes_bdw/data/hex_nut_parameters.csv"
python3 -I "$SB" "$ROOT" --data "$V/sizes_bdw/data" > "$V/sizes_bdw/neg_hash.txt" 2>&1
[ $? -eq 1 ] && grep -q "^HASH hex_nut_parameters.csv" "$V/sizes_bdw/neg_hash.txt" \
  && ok "negative control: a changed CSV fails its sha256" \
  || bad "negative control: changed CSV not caught (see $V/sizes_bdw/neg_hash.txt)"
# overlay control: a size_rules() overlay expression the helper cannot evaluate must stop it with a message, not be skipped
FD="skills/print-cad-blender/scripts"
rm -rf "$V/sizes_bdw/root"; mkdir -p "$V/sizes_bdw/root/$FD/cadlib"
cp "$ROOT/$FD/cadcheck.py" "$V/sizes_bdw/root/$FD/cadcheck.py"
sed 's/nut_af=R\["m3_nut_af"\]/nut_af=R["m3_nut_af"] + 0/' "$ROOT/$FD/cadlib/features.py" > "$V/sizes_bdw/root/$FD/cadlib/features.py"
python3 -I "$SB" "$V/sizes_bdw/root" --data "$ROOT/tools/prior_art/bd_warehouse_data" > "$V/sizes_bdw/neg_overlay.txt" 2>&1
[ $? -ne 0 ] && grep -q "overlay uses .*cannot evaluate" "$V/sizes_bdw/neg_overlay.txt" \
  && ok "negative control: a changed size_rules() overlay form stops the check with a message" \
  || bad "negative control: changed overlay form not caught (see $V/sizes_bdw/neg_overlay.txt)"
