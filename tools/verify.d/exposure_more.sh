# cadcheck exposure on purchased PCBs and plugs and on screw heads (sourced by tools/verify_all.sh; uses $ROOT $CAD $V,
# calls ok/bad). Writes under $V/exm. V2A1-F11: a servo-controller PCB showed through a base notch and no check said so
# (exposure covered cables and nuts); #40 (2026-11-03): the render-only review findings were a plug in the hero view
# and proud or dark screw heads. Negative control: a PCB half outside the shell and a proud head must warn (and a plug
# typed by its buy_kind prop). False-positive control: a plug fully inside and a counterbored head stay silent.
# heads_ok silences the proud head. The cases are in exposure_more_build.py. About 10 s.
# watch: @core tools/verify.d/exposure_more_build.py
mkdir -p "$V/exm"
$CAD build "$ROOT/tools/verify.d/exposure_more_build.py" -- --out "$V/exm" > "$V/exm/build.log" 2>&1
$CAD check "$V/exm/exm.blend" "$V/exm/checks.json" "$V/exm/cadcheck.json" --only exposure > "$V/exm/check.log" 2>&1
$CAD check "$V/exm/exm.blend" "$V/exm/checks_ok.json" "$V/exm/cadcheck_ok.json" --only exposure > "$V/exm/check_ok.log" 2>&1
python3 -I - "$V/exm" <<'PY' > "$V/exm/asserts.txt" 2>&1
import json, sys
d = sys.argv[1]
def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "exposure: " + msg)
try:
    r, k = json.load(open(d + "/cadcheck.json")), json.load(open(d + "/cadcheck_ok.json"))
except Exception as e:
    say(False, "no report (%s; see %s/build.log, check.log)" % (e, d)); sys.exit()
W = [w for w in r["summary"]["warn_list"] if w.startswith("exposure:")]
def warned(n, kind):
    return any(n + " " in w and kind in w for w in W)
rows = {x["object"]: x for x in r["checks"]["exposure"]["rows"]}
heads = {x["object"]: x for x in r["checks"]["exposure"]["heads"]}
say(warned("BUY_exm_board", "(PCB) is visible from outside"), "a PCB half outside the shell warns (%s)" % rows.get("BUY_exm_board"))
say(warned("BUY_exm_widget", "(plug) is visible from outside"), "a plug typed by its buy_kind prop, half outside, warns")
say(warned("FST_exm_proud", "1 screw head is proud and visible from outside"), "a head proud on the outer face warns (%s)" % heads.get("FST_exm_proud"))
say(rows.get("BUY_exm_usbc_plug", {}).get("kind") == "plug" and rows["BUY_exm_usbc_plug"]["exposed_samples"] == 0
    and not any("BUY_exm_usbc_plug" in w for w in W), "a plug fully inside is checked and silent (%s)" % rows.get("BUY_exm_usbc_plug"))
say("FST_exm_cbore" in heads and heads["FST_exm_cbore"]["exposed_rim"] < 2 and not any("FST_exm_cbore" in w for w in W),
    "a counterbored head is checked and silent (%s)" % heads.get("FST_exm_cbore"))
say(len(W) == 3, "exactly 3 exposure warns (board, widget, one heads line): %s" % W)
Wk = [w for w in k["summary"]["warn_list"] if w.startswith("exposure:")]
say(not any("FST_exm_proud" in w for w in Wk) and len(Wk) == 2, "exposure.heads_ok silences the proud head: %s" % Wk)
PY
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$V/exm/asserts.txt"
grep -q '^PASS\|^FAIL' "$V/exm/asserts.txt" || bad "exposure: asserts crashed (see $V/exm/asserts.txt)"
