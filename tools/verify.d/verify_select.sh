# The verify_all.sh --changed selector (tools/verify_select.py): its map and fake change lists, so an edit can't
# silently skip tests. Sourced by tools/verify_all.sh (uses $ROOT; calls ok/bad). About 2 s, no Blender.
# watch: tools/verify_select.py tools/verify.d/verify_select_cases.py tools/verify.d/*.sh
mkdir -p "$V/select"
python3 -I "$ROOT/tools/verify.d/verify_select_cases.py" "$ROOT" > "$V/select/cases.txt" 2>&1
grep -q '^PASS' "$V/select/cases.txt" || echo "FAIL verify_select: no cases ran ($(tail -1 "$V/select/cases.txt"))" >> "$V/select/cases.txt"
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; *) bad "verify_select: $st $msg" ;; esac; done < "$V/select/cases.txt"
