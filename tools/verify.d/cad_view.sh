# cad view: one offline HTML page of a checked assembly (sliders per joint, cadcheck's findings clickable).
# watch: @core skills/print-cad-blender/scripts/cadview.py skills/print-cad-blender/scripts/viewer/**
# watch: examples/mm-launcher-v2a7/mm_launcher_v2a7.blend.gz examples/mm-launcher-v2a7/manifest.json tools/verify.d/cad_view_browser.mjs
# needs: 2
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V, calls ok/bad). Reads unit 2's demo-bug blend and report. About 30 s.
# Headless Chrome (CHROME overrides the path) and node 22+ drive the pages (cad_view_browser.mjs); without them the
# browser half is a NOTE, not a pass.
CV="$V/cadview"; mkdir -p "$CV"
DB="$V/demo-bug"
size_kb() { echo $(( $(wc -c < "$1") / 1024 )); }
# the turret with its four planted bugs: page builds, small, no external reference
$CAD view "$DB/demo.blend" "$DB/cadcheck.json" -o "$CV/demo.html" > "$CV/demo.log" 2>&1; rc=$?
grep -q '^CADVIEW .* 16 objects, 2 joints, 21 findings (9 fail)' "$CV/demo.log" && [ $rc = 0 ] \
  && ok "cad view: demo-bug page built: $(sed -n 's/^CADVIEW [^ ]* //p' "$CV/demo.log")" \
  || bad "cad view: demo-bug page (exit $rc): $(tail -3 "$CV/demo.log")"
[ -f "$CV/demo.html" ] && [ "$(size_kb "$CV/demo.html")" -lt 700 ] && ok "cad view: demo page under 700 KB ($(size_kb "$CV/demo.html") KB)" \
  || bad "cad view: demo page missing or 700 KB or more"
# no <script src>, <link href> or CSS url() that leaves the file (the browser run below also traps every request)
python3 -I - "$CV/demo.html" <<'PY' > "$CV/refs.txt"
import re, sys
h = open(sys.argv[1], encoding="utf-8").read()
refs = re.findall(r'<(?:script|link|img|iframe)\b[^>]*\b(?:src|href)=["\']([^"\']+)', h) + re.findall(r'url\((?!data:)([^)]+)\)', h)
print(("PASS" if not refs and h.count("<script") >= 6 else "FAIL") + " cad view: the page loads nothing from outside the file: %s" % (refs[:5] or "none"))
PY
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$CV/refs.txt"
$CAD view "$DB/demo.blend" "$DB/cadcheck.json" -o "$CV/demo_st.html" --selftest > "$CV/demo_st.log" 2>&1
# the v2 launcher (178 objects, 10 joints with a coupling, a slide and a continuous wheel)
mkdir -p "$CV/v2a7"; gunzip -c "$ROOT/examples/mm-launcher-v2a7/mm_launcher_v2a7.blend.gz" > "$CV/v2a7/model.blend"
$CAD view "$CV/v2a7/model.blend" -o "$CV/v2a7.html" > "$CV/v2a7.log" 2>&1; rc=$?
[ $rc = 0 ] && [ "$(size_kb "$CV/v2a7.html")" -lt 2048 ] && ok "cad view: v2a7 page under 2 MB: $(sed -n 's/^CADVIEW [^ ]* //p' "$CV/v2a7.log")" \
  || bad "cad view: v2a7 page (exit $rc, $( [ -f "$CV/v2a7.html" ] && size_kb "$CV/v2a7.html") KB): $(tail -3 "$CV/v2a7.log")"
$CAD view "$CV/v2a7/model.blend" -o "$CV/v2a7_st.html" --selftest --pose feeder=20 > "$CV/v2a7_st.log" 2>&1
# negative controls: a report from another model, a file that isn't a report, a pose on a joint the blend lacks
rm -f "$CV/wrong.html"
$CAD view "$CV/v2a7/model.blend" "$DB/cadcheck.json" -o "$CV/wrong.html" > "$CV/wrong.log" 2>&1; rc=$?
[ $rc = 2 ] && [ ! -f "$CV/wrong.html" ] && grep -q 'not in the blend: .*PRT_barrel' "$CV/wrong.log" \
  && ok "cad view: the demo report on the v2a7 blend is refused (exit 2, no page): $(grep -o '[0-9]* name(s) in the report are not in the blend' "$CV/wrong.log")" \
  || bad "cad view: a report from another model was not refused (exit $rc): $(tail -2 "$CV/wrong.log")"
$CAD view "$CV/v2a7/model.blend" "$DB/cadcheck.json" -o "$CV/forced.html" --force > "$CV/forced.log" 2>&1; rc=$?
[ $rc = 0 ] && grep -q 'MISMATCH flagged' "$CV/forced.log" && grep -q 'name(s) in the report are not in this blend' "$CV/forced.html" \
  && ok "cad view: --force builds the mismatched page with the mismatch in its banner" || bad "cad view: --force (exit $rc): $(tail -2 "$CV/forced.log")"
$CAD view "$DB/demo.blend" "$ROOT/examples/mm-launcher-v2a7/manifest.json" -o "$CV/manifest.html" > "$CV/manifest.log" 2>&1; rc=$?
[ $rc = 2 ] && grep -q 'is not a cadcheck report' "$CV/manifest.log" && ok "cad view: a manifest.json given as the report is refused (exit 2)" \
  || bad "cad view: a manifest.json as the report (exit $rc): $(tail -2 "$CV/manifest.log")"
$CAD view "$DB/demo.blend" -o "$CV/pose.html" --pose PIV_nope=3 > "$CV/pose.log" 2>&1; rc=$?
[ $rc = 2 ] && grep -q 'give joint=value pairs of PIV_pan, PIV_tilt' "$CV/pose.log" && ok "cad view: --pose on a joint the blend lacks is refused (exit 2)" \
  || bad "cad view: --pose PIV_nope (exit $rc): $(tail -2 "$CV/pose.log")"
# in a browser: Blender's matrix_world at every joint's limits against the page's pose maths, a slider, a finding click
CHROME_BIN="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [ -x "$CHROME_BIN" ] && node -e 'process.exit(typeof WebSocket === "function" ? 0 : 1)' 2>/dev/null; then
  for p in demo v2a7; do
    node "$ROOT/tools/verify.d/cad_view_browser.mjs" "$CV/${p}_st.html" --selftest --shot "$CV/$p.png" > "$CV/${p}_browser.txt" 2>&1; rc=$?
    python3 -I - "$CV/${p}_browser.txt" "$p" "$rc" <<'PY' > "$CV/${p}_browser_asserts.txt"
import json, sys
txt, page, rc = open(sys.argv[1]).read(), sys.argv[2], sys.argv[3]
line = next((l for l in txt.splitlines() if l.startswith("CVTEST ")), None)
def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "cad view (%s, Chrome): %s" % (page, msg))
if line is None:
    say(False, "no selftest result: %s" % txt[-300:].replace("\n", " | "))
    sys.exit()
r = json.loads(line[7:])
say(rc == "0" and r["pass"], "page loaded with no console errors and no network request, %d/%d objects; %s" % (
    r["objects"], r["expected_objects"], " | ".join(l for l in txt.splitlines() if l.startswith(("CONSOLE", "NET", "LOADED", "ERROR")))[:400]))
say(r["poses"] >= 5 and r["max_err_mm"] < 0.01, "pose maths match Blender's matrix_world (cadlib.joints.apply) at %d poses: worst %.6f mm on %s" % (
    r["poses"], r["max_err_mm"], r["worst"]))
s = r["ui"].get("slider") or {}
say(s.get("moved_mm", 0) > 1, "moving the %s slider to %s moves %s by %s mm" % (s.get("joint"), s.get("to"), s.get("part"), s.get("moved_mm")))
if page == "demo":
    f = r["ui"].get("finding") or {}
    say(f.get("pose") == {"PIV_tilt": -50} and f.get("page_pose") == {"PIV_tilt": -50} and f.get("sliders") == {"PIV_tilt": -50}
        and sorted(f.get("lit", [])) == ["PRT_barrel", "PRT_pan"] and f.get("markers_visible"),
        "clicking the PRT_pan x PRT_barrel fail poses the turret at tilt=-50, slider included, and lights both parts: %s" % f)
    say(r["ui"].get("explode", 0) > 5, "the explode slider moves parts apart (%s mm)" % r["ui"].get("explode"))
PY
    while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$CV/${p}_browser_asserts.txt"
  done
else
  echo "NOTE cad view: no headless Chrome at $CHROME_BIN or no node 22+: the page's pose maths, slider and finding click were not run in a browser"
fi
