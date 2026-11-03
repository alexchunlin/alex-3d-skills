# cad diff on the archived v2 launcher: v2a6 -> v2a7 designer reports against V2R7's previous_issue_status
# (renders/attempt-7/review.json: A6-01 FIXED, A6-02 PARTIAL, A6-03 FIXED). Which warn is which issue: 4i's comment.
# The turret cases are cad_diff.sh (issue #30).
# watch: skills/print-cad-blender/scripts/cad skills/print-cad-blender/scripts/caddiff.py skills/print-cad-blender/scripts/cadcfg.py
# needs: 4i 4k
# Sourced by tools/verify_all.sh (uses $V, calls ok/bad). Plain python3 on 4i's and 4k's reports, under a second.
CD="$V/cad-diff"; mkdir -p "$CD"
if [ -f "$V/v2a6/cadcheck.json" ] && [ -f "$V/v2a7/cadcheck.json" ]; then
  agree=0
  $CAD diff "$V/v2a6/cadcheck.json" "$V/v2a7/cadcheck.json" > "$CD/d_v2.txt" 2>&1
  grep -q "^  fixed .*insertion: BUY_bus_junction is in bench step '10d" "$CD/d_v2.txt" && grep -q "^  fixed .*insertion: group 'feeder' (16 objects)" "$CD/d_v2.txt" \
    && { agree=$((agree+1)); ok "cad diff v2a6 -> v2a7: both A6-01 insertion warns fixed (V2R7: FIXED)"; } || bad "cad diff v2: A6-01 warns not fixed"
  grep -q "^  fixed .*cables: CAB_bus_pan ends 1.2 mm from BUY_bus_junction" "$CD/d_v2.txt" && grep -q "^  still .*cables: CAB_launcher_base ends 0.0 mm from CAB_launcher_bundle" "$CD/d_v2.txt" \
    && { agree=$((agree+1)); ok "cad diff v2a6 -> v2a7: A6-02 one warn fixed (pan bus lead), one still (launcher bundle, 5.7 mm drift) (V2R7: PARTIAL)"; } || bad "cad diff v2: A6-02 fixed/still lines"
  [ "$(grep -c "^  fixed .*the swept ray missed a part at 1 of 53 stations (0 deg)" "$CD/d_v2.txt")" = 4 ] && grep -q "ray sweep.from 0 -> 1" "$CD/d_v2.txt" \
    && { agree=$((agree+1)); ok "cad diff v2a6 -> v2a7: the 4 A6-03 missed-station warns fixed, the sweeps start at 1 (V2R7: FIXED)"; } || bad "cad diff v2: A6-03 lines"
  grep -q "^  new .*assembly: step '11a .*needs PIV_tilt at 45" "$CD/d_v2.txt" && ok "cad diff v2a6 -> v2a7: V2R7's new A7-01 (tilt 45 on the unpowered servo at 11a) is listed new" || bad "cad diff v2: A7-01 not new"
  [ "$agree" = 3 ] && ok "cad diff v2a6 -> v2a7 agrees with V2R7 on 3 of 3 previous issues" || bad "cad diff v2: agrees with V2R7 on $agree of 3"
else
  nochecks "cad diff v2a6 -> v2a7: no 4i / 4k reports in $V (run with units 4i and 4k)"
fi
