# cadcheck exposure on purchased PCBs and, opted in, plugs and screw heads (sourced by tools/verify_all.sh; uses $ROOT
# $CAD $V, calls ok/bad). Writes under $V/exm. V2A1-F11: a servo-controller PCB showed through a base notch and no check
# said so (exposure covered cables and nuts); #40 (2026-11-03): the render-only review findings were a plug in the hero
# view and proud or dark screw heads. Negative control: a PCB half outside the shell warns by default; opted in, a plug
# typed by its buy_kind prop and a proud head warn. False-positive control: a PCB seen through an 8 mm hole (under pcb_min_share),
# a plug fully inside and a counterbored head stay silent; by default plugs and heads say nothing. heads_ok silences
# the proud head. The cases are in exposure_more_build.py. About 10 s.
# watch: @core tools/verify.d/exposure_more_build.py
mkdir -p "$V/exm"
$CAD build "$ROOT/tools/verify.d/exposure_more_build.py" -- --out "$V/exm" > "$V/exm/build.log" 2>&1
for c in checks checks_on checks_ok; do
  $CAD check "$V/exm/exm.blend" "$V/exm/$c.json" "$V/exm/$c.out.json" --only exposure > "$V/exm/$c.log" 2>&1
done
python3 -I - "$V/exm" <<'PY' > "$V/exm/asserts.txt" 2>&1
import json, sys
d = sys.argv[1]
def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "exposure: " + msg)
try:
    r, o, k = (json.load(open("%s/%s.out.json" % (d, c))) for c in ("checks", "checks_on", "checks_ok"))
except Exception as e:
    say(False, "no report (%s; see %s/build.log and the logs)" % (e, d)); sys.exit()
def ex(rep):
    return [w for w in rep["summary"]["warn_list"] if w.startswith("exposure:")]
W, Wo, Wk = ex(r), ex(o), ex(k)
rows = {x["object"]: x for x in o["checks"]["exposure"]["rows"]}
heads = {x["object"]: x for x in o["checks"]["exposure"]["heads"]}
def warned(ws, n, kind):
    return any(n + " " in w and kind in w for w in ws)
say(len(W) == 1 and warned(W, "BUY_exm_board", "(PCB) is visible from outside") and not r["checks"]["exposure"]["heads"]
    and "BUY_exm_widget" not in {x["object"] for x in r["checks"]["exposure"]["rows"]},
    "defaults: only the PCB half outside the shell warns; plugs and heads are not checked: %s" % W)
e = rows.get("BUY_exm_board_edge", {})
say(e.get("exposed_samples", 0) >= 2 and e["exposed_samples"] < 0.05 * e["samples"] and not any("BUY_exm_board_edge" in w for w in W + Wo),
    "a PCB seen through an 8 mm hole is seen but under pcb_min_share 5%%, silent (%s)" % e)
say(warned(Wo, "BUY_exm_widget", "(plug) is visible from outside"), "opted in: a plug typed by its buy_kind prop, half outside, warns")
say(warned(Wo, "FST_exm_proud", "1 screw head is proud and visible from outside"), "opted in: a head proud on the outer face warns (%s)" % heads.get("FST_exm_proud"))
say(rows.get("BUY_exm_usbc_plug", {}).get("kind") == "plug" and rows["BUY_exm_usbc_plug"]["exposed_samples"] == 0
    and not any("BUY_exm_usbc_plug" in w for w in Wo), "opted in: a plug fully inside is checked and silent (%s)" % rows.get("BUY_exm_usbc_plug"))
say("FST_exm_cbore" in heads and heads["FST_exm_cbore"]["exposed_rim"] < 2 and not any("FST_exm_cbore" in w for w in Wo),
    "opted in: a counterbored head is checked and silent (%s)" % heads.get("FST_exm_cbore"))
say(len(Wo) == 3, "opted in: exactly 3 exposure warns (board, widget, one heads line): %s" % Wo)
say(not any("FST_exm_proud" in w for w in Wk) and len(Wk) == 2, "exposure.heads_ok silences the proud head: %s" % Wk)
PY
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$V/exm/asserts.txt"
grep -q '^PASS\|^FAIL' "$V/exm/asserts.txt" || bad "exposure: asserts crashed (see $V/exm/asserts.txt)"
