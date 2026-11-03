# cad diff: two cadcheck reports (and manifests) of one design: new / fixed / worse / better findings, requirements
# that disappeared or loosened, manifest deltas; and the short delta every `cad check` prints when it overwrites a
# report (issue #30; V2A5-T2: a shared params change brought 14 drop fails, seen only by reading the report again).
# watch: @core examples/demo-turret/**
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V, calls ok/bad). About 45 s: two turret builds, 9 turret checks,
# plain python3 diffs. The archived v2a6 -> v2a7 diff is cad_diff_v2.sh (it reads 4i's and 4k's reports).
CD="$V/cad-diff"; mkdir -p "$CD/auto" "$CD/cfg"
T="$ROOT/examples/demo-turret"
$CAD build "$T/build.py" --out "$CD/clean" > "$CD/build.log" 2>&1
$CAD build "$T/build.py" --out "$CD/bug" --bug >> "$CD/build.log" 2>&1
$CAD check "$CD/clean/demo.blend" "$T/checks.json" "$CD/clean/cadcheck.json" > "$CD/clean.log" 2>&1
$CAD check "$CD/bug/demo.blend" "$T/checks.json" "$CD/bug/cadcheck.json" > "$CD/bug.log" 2>&1
PATS="FST_arm_0 head is inside|PRT_barrel x FST_proud|PRT_pan x PRT_barrel|FST_side stops 0.40 mm short"   # verify_all 2's planted bugs

# 1 clean -> bug: the 4 planted fails are new; bug -> clean: fixed; a report against itself: nothing (negative control)
$CAD diff "$CD/clean/cadcheck.json" "$CD/bug/cadcheck.json" > "$CD/d_cb.txt" 2>&1; rc_cb=$?
$CAD diff "$CD/bug/cadcheck.json" "$CD/clean/cadcheck.json" > "$CD/d_bc.txt" 2>&1
$CAD diff "$CD/bug/cadcheck.json" "$CD/bug/cadcheck.json" > "$CD/d_bb.txt" 2>&1; rc_bb=$?
n=$(grep -E "^  new +FAIL " "$CD/d_cb.txt" | grep -cE "$PATS")
[ "$n" = 4 ] && [ "$rc_cb" = 1 ] && ok "cad diff: turret clean -> bug lists the 4 planted fails as new (exit 1)" || bad "cad diff: clean -> bug: $n of 4 planted fails new, exit $rc_cb"
n=$(grep -E "^  fixed +FAIL " "$CD/d_bc.txt" | grep -cE "$PATS")
[ "$n" = 4 ] && ok "cad diff: turret bug -> clean lists them as fixed" || bad "cad diff: bug -> clean: $n of 4 fixed"
grep -q " 0 new (0 untriaged), 0 fixed, 0 worse, 0 better, 0 changed, " "$CD/d_bb.txt" && [ "$rc_bb" = 0 ] && ! grep -qE "^  (new|fixed|worse|better|changed|REQ|req) " "$CD/d_bb.txt" \
  && ok "cad diff: a report against itself: nothing new, fixed, worse or better (exit 0)" || bad "cad diff: self diff not empty (exit $rc_bb): $(sed -n 2p "$CD/d_bb.txt")"
grep -q "joint PIV_tilt range 0.0..40.0 -> -50.0..40.0" "$CD/d_cb.txt" && grep -q "FST_side length: 6.0 -> 2.0" "$CD/d_cb.txt" && grep -q "part added: FST_proud" "$CD/d_cb.txt" \
  && ok "cad diff: manifests next to the reports: PIV_tilt range, FST_side length 6 -> 2, FST_proud added" || bad "cad diff: manifest delta missing"

# --manifest wins over the manifests next to the reports; --max caps the lines; a crash or a bad flag exits 2, not 1
$CAD diff "$CD/bug/cadcheck.json" "$CD/bug/cadcheck.json" --manifest "$CD/clean/manifest.json" "$CD/bug/manifest.json" > "$CD/d_man.txt" 2>&1
$CAD diff "$CD/clean/cadcheck.json" "$CD/bug/cadcheck.json" --max 5 > "$CD/d_max.txt" 2>&1
echo '{"checks": [1]}' > "$CD/broken.json"
$CAD diff "$CD/clean/cadcheck.json" "$CD/broken.json" > "$CD/d_crash.txt" 2>&1; rc_crash=$?
$CAD diff "$CD/clean/cadcheck.json" "$CD/bug/cadcheck.json" --max x > "$CD/d_badmax.txt" 2>&1; rc_badmax=$?
cp "$CD/clean/cadcheck.json" "$CD/older.json"; cp "$CD/bug/cadcheck.json" "$CD/older.prev.json"
$CAD diff "$CD/older.json" > "$CD/d_older.txt" 2>&1; rc_older=$?
grep -q "part added: FST_proud" "$CD/d_man.txt" && [ "$(wc -l < "$CD/d_max.txt")" -le 8 ] && grep -q "more lines (raise --max)" "$CD/d_max.txt" \
  && [ "$rc_crash" = 2 ] && [ "$(wc -l < "$CD/d_crash.txt" | tr -d ' ')" = 1 ] && [ "$rc_badmax" = 2 ] && [ "$rc_older" = 2 ] && grep -q "is newer than" "$CD/d_older.txt" \
  && ok "cad diff: --manifest pair used, --max 5 caps, a crash ('$(cut -c1-50 "$CD/d_crash.txt")') and --max x exit 2, an older .prev.json is refused" \
  || bad "cad diff flags: manifest $(grep -c 'FST_proud' "$CD/d_man.txt"), max $(wc -l < "$CD/d_max.txt") lines, crash exit $rc_crash ($(wc -l < "$CD/d_crash.txt") lines), --max x exit $rc_badmax, older .prev exit $rc_older"

# same key, other number or status: worse / better, not fixed + new (messages carry numbers)
python3 -I - "$ROOT/skills/print-cad-blender/scripts" "$CD/bug/cadcheck.json" <<'PY' > "$CD/wb.txt" 2>&1
import copy, json, sys
sys.path.insert(0, sys.argv[1]); import caddiff as D
old = json.load(open(sys.argv[2])); new = copy.deepcopy(old)
for f in new["checks"]["interference"]["findings"]:
    if "PRT_pan x PRT_barrel" in f["msg"]:
        f["msg"] = f["msg"].replace("136.8 mm3", "150.2 mm3")     # a bigger collision
for f in new["checks"]["clearance"]["findings"]:
    if "PRT_base to PRT_barrel 0.65 mm" in f["msg"]:
        f["msg"] = f["msg"].replace("0.65 mm", "0.80 mm")          # a wider gap
    if "PRT_base to PRT_pan" in f["msg"]:
        f["status"] = "fail"                                       # warn -> fail
fd = D.diff_findings(old, new)
w = sorted(f["line"][:40] for _, f in fd["worse"]); b = sorted(f["line"][:40] for _, f in fd["better"])
print(("PASS" if len(w) == 2 and len(b) == 1 and not fd["new"] and not fd["fixed"] and "136.8 -> 150.2" in "\n".join(D.lines(fd, []))
       else "FAIL") + " cad diff: a bigger collision and warn -> fail are worse, a wider gap better, none new or fixed: worse %s better %s new %d" % (w, b, len(fd["new"])))
sr = D.short_report(old, new, "OLD.json", "NEW.json", cap=1)   # 2 worse, 1 better: 1 line shown, 2 more
print(("PASS" if len(sr) == 3 and "2 more" in sr[-1] and sr[-1].endswith("cad diff OLD.json NEW.json") else "FAIL") + " cad diff: the short form stops at its cap and says how to see the rest: %s" % sr[-1].strip())
rev = D.diff_findings(new, old)
print(("PASS" if len(rev["better"]) == 2 and len(rev["worse"]) == 1 else "FAIL") + " cad diff: and the other way round 2 better, 1 worse")
PY
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$CD/wb.txt"

# 2 the delta prints unasked at the end of cad check, against the report it overwrites (kept as .prev.json)
cp "$CD/clean/cadcheck.json" "$CD/auto/cadcheck.json"
$CAD check "$CD/bug/demo.blend" "$T/checks.json" "$CD/auto/cadcheck.json" > "$CD/auto1.log" 2>&1
sed -n '/delta vs the previous report/,$p' "$CD/auto1.log" > "$CD/auto1.delta"
n=$(grep -E "^    new +FAIL " "$CD/auto1.delta" | grep -cE "$PATS")
[ "$n" = 4 ] && [ -f "$CD/auto/cadcheck.prev.json" ] && [ "$(wc -l < "$CD/auto1.delta")" -le 23 ] \
  && ok "cad check: prints the delta unasked: 4 planted fails new, $(wc -l < "$CD/auto1.delta" | tr -d ' ') lines (cap 20 + header), old report kept as cadcheck.prev.json" \
  || bad "cad check delta: $n of 4 new, $(wc -l < "$CD/auto1.delta") lines, prev $( [ -f "$CD/auto/cadcheck.prev.json" ] && echo kept || echo missing)"
$CAD check "$CD/bug/demo.blend" "$T/checks.json" "$CD/auto/cadcheck.json" > "$CD/auto2.log" 2>&1
grep -q "delta vs the previous report .*: no change in findings or requirements" "$CD/auto2.log" && ok "cad check: the same model twice: 'no change' in one line" || bad "cad check: rerun delta: $(grep -A2 'delta vs' "$CD/auto2.log" | head -3)"
g2=$(python3 -I -c "import json,sys; print(json.load(open(sys.argv[1])).get('generated'))" "$CD/auto/cadcheck.json")
$CAD check "$CD/bug/demo.blend" "$T/checks.json" "$CD/auto/cadcheck.json" --no-diff > "$CD/auto3.log" 2>&1
gen() { python3 -I -c "import json,sys; print(json.load(open(sys.argv[1])).get('generated'))" "$1" 2>/dev/null; }
grep -q "^CADCHECK" "$CD/auto3.log" && ! grep -q "delta vs" "$CD/auto3.log" && [ "$(gen "$CD/auto/cadcheck.prev.json")" = "$g2" ] \
  && ok "cad check --no-diff: no delta, and cadcheck.prev.json still names the run before ($g2)" || bad "cad check --no-diff: delta printed or .prev.json not refreshed ($(gen "$CD/auto/cadcheck.prev.json") vs $g2)"
# an --only run over a full report: the checks that did not run are not compared, so nothing reads as fixed
$CAD check "$CD/bug/demo.blend" "$T/checks.json" "$CD/auto/cadcheck.json" --only parts > "$CD/auto4.log" 2>&1
grep -q "no change in findings or requirements; not compared: .*interference" "$CD/auto4.log" && ok "cad check --only parts over a full report: not compared, 0 fixed" || bad "cad check --only delta: $(grep 'delta vs' "$CD/auto4.log")"
# an unreadable report at OUT: no delta, and the old .prev.json is removed, so `cad diff OUT` cannot use a stale one
echo "{" > "$CD/auto/cadcheck.json"
$CAD check "$CD/bug/demo.blend" "$T/checks.json" "$CD/auto/cadcheck.json" > "$CD/auto5.log" 2>&1
grep -q "^CADCHECK" "$CD/auto5.log" && ! grep -q "delta vs" "$CD/auto5.log" && [ ! -f "$CD/auto/cadcheck.prev.json" ] \
  && ok "cad check over an unreadable report: no delta, stale cadcheck.prev.json removed" || bad "cad check over an unreadable report: delta or stale .prev.json left"

# requirements cannot silently disappear: the drop test deleted, a distances row swapped for a similar-named one about
# another part (review of PR #53: paired as a rename, exit 0), an accept added, min_wall lowered, a slide row's ignore
# list grown, fewer poses per group, less overtravel
python3 -I - "$T/checks.json" "$CD/cfg" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
slide = {"name": "barrel up out of the arms", "object": "PRT_barrel", "dir": [0, 0, 1], "dist": 30, "ignore": ["CAB_*"]}
a = json.loads(json.dumps(c)); a["distances"] = [{"name": "barrel above base", "a": "PRT_base", "b": "PRT_barrel", "min": 0.3}]
a["slide_out"] = [slide]
b = json.loads(json.dumps(c)); b["drop_tests"] = []; b["min_wall"] = 1.5
b["distances"] = [{"name": "barrel above pan", "a": "PRT_pan", "b": "PRT_barrel", "min": 0.3}]
b["slide_out"] = [dict(slide, ignore=["CAB_*", "PRT_arm_*"])]; b["max_poses_per_group"] = 24; b["overtravel_deg"] = 1.0
b["accepted_warns"] = [{"check": "parts", "kind": "wall samples", "object": "PRT_arm_L", "any": True, "why": "arm web"}]
json.dump(a, open(sys.argv[2] + "/old.json", "w")); json.dump(b, open(sys.argv[2] + "/new.json", "w"))
PY
$CAD check "$CD/clean/demo.blend" "$CD/cfg/old.json" "$CD/cfg/r.json" > /dev/null 2>&1
$CAD check "$CD/clean/demo.blend" "$CD/cfg/new.json" "$CD/cfg/r.json" > "$CD/cfg.log" 2>&1
$CAD diff "$CD/cfg/r.json" > "$CD/d_cfg.txt" 2>&1; rc_cfg=$?
miss=""
for pat in "REQ- .*distances row removed: 'barrel above base'" "REQ- .*drop_tests row removed: 'muzzle_line_of_fire'" \
           "REQ~ .*accepted_warns row added: 'parts: PRT_arm_L wall samples'" "REQ~ .*min_wall: 1.6 -> 1.5" "now accepted: parts: PRT_arm_L" \
           "REQ~ .*slide_out 'barrel up out of the arms': ignore \+\[\"PRT_arm_\*\"\]" "REQ~ .*max_poses_per_group: 48 -> 24" "REQ~ .*overtravel_deg: 2.5 -> 1"; do
  grep -qE "$pat" "$CD/cfg.log" && grep -qE "$pat" "$CD/d_cfg.txt" || miss="$miss '$pat'"
done
grep -q "req+ .*distances row added: 'barrel above pan'" "$CD/d_cfg.txt" && ! grep -q "renamed" "$CD/d_cfg.txt" || miss="$miss 'barrel above pan added, not renamed'"
[ -z "$miss" ] && grep -q "requirements: 2 removed, 5 loosened, 1 warns newly accepted" "$CD/d_cfg.txt" && [ "$rc_cfg" = 1 ] \
  && ok "cad diff: drop test deleted, a distances row swapped for one about another part (removed + added, not renamed), an accept, min_wall 1.6 -> 1.5, ignore +PRT_arm_*, max_poses_per_group 48 -> 24, overtravel_deg 2.5 -> 1 are REQ- / REQ~ (in cad check's delta and cad diff NEW, exit 1)" \
  || bad "cad diff requirements: missing$miss; $(sed -n 2p "$CD/d_cfg.txt")"
