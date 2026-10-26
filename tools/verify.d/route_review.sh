# cadlib.route: the PR #3 review's adversarial scenes as small regressions (tools/verify.d/route_review_cases.py).
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V $BL; calls ok/bad). About 10 s.
RR="$V/route_review"; mkdir -p "$RR"
nice -n 10 "$BL" -b --factory-startup --python "$ROOT/tools/verify.d/route_review_cases.py" -- \
  "$ROOT/skills/print-cad-blender/scripts" "$RR" 2>/dev/null | grep '^RREV' | cut -c6- > "$RR/cases.json"
rr() {   # rr "message" 'python condition on d'
  python3 -I -c "import json, sys; d = json.load(open(sys.argv[1])); sys.exit(0 if ($2) else 1)" "$RR/cases.json" 2>/dev/null \
    && ok "$1" || bad "$1 (see $RR/cases.json)"
}
rr "router review: a 0..40 mm slide is swept in mm; route keeps >= 0.95 mm from the drawer at every 0.5 mm" \
   "d['slide']['fine_clearance'] >= 0.95"
rr "router review: an arm on +-30 deg is not threaded between samples (>= 0.95 mm at every 0.5 deg)" \
   "d['thread']['fine_clearance'] >= 0.95 and d['thread']['length_mm'] > d['thread']['straight_mm'] + 5"
rr "router review: pan x tilt chain avoided at every 1 x 2.5 deg pose" \
   "d['chain']['fine_clearance'] >= 0.95 and d['chain']['violations'] == 0"
rr "router review: a paddle on a continuous joint is avoided at every 1 deg (spin envelope)" \
   "d['wheel']['fine_clearance'] >= 0.95"
rr "router review: an end inside an arm's sweep (scene wedge) raises 'swept path', no silent route" \
   "'swept path of PIV_arm' in (d['wedge'].get('raised') or '')"
rr "router review: crossing a hinge across its axis warns of the fold (0 / 110 deg); along the axis it doesn't" \
   "d['hinge_fold']['turn_deg']['110'] > 100 and d['hinge_fold']['warn'] and d['hinge_axis']['on_axis'] and not d['hinge_axis']['warn'] and max(d['hinge_axis']['turn_deg'].values()) < 5"
rr "router review: a 3 mm cable forced through a 2 mm slot reports violations (into the solid)" \
   "d['slot_2.0_viadir']['violations'] > 0 and d['slot_2.0_viadir']['worst'] < 0 and d['slot_2.0_viadir']['warned']"
rr "router review: a point via in a 5.4 mm slot reaches the asked clearance or reports it" \
   "(d['slot_5.4_via']['fine_clearance'] >= d['slot_5.4_via']['asked'] - 0.05) or (d['slot_5.4_via']['violations'] > 0 and d['slot_5.4_via']['warned'])"
# cad q route exits non-zero on a violation (the cad wrapper keeps cadq's status through its output filter)
if [ -f "$RR/slot_2.0_viadir.blend" ]; then
  $CAD q "$RR/slot_2.0_viadir.blend" route CAB_s --via "0,15,4@1,0,0:6" > "$RR/cadq_route.txt" 2>&1
  st=$?
  [ "$st" != 0 ] && grep -q '"violation"' "$RR/cadq_route.txt" \
    && ok "router review: cad q route exits $st and prints violation rows on the 2 mm slot" \
    || bad "router review: cad q route exit status $st on the 2 mm slot (see $RR/cadq_route.txt)"
else
  bad "router review: route_review_cases.py wrote no slot blend"
fi
