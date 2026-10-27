# cadcheck head and nut overlap (sourced by tools/verify_all.sh; uses $ROOT $CAD $V, calls ok/bad). Writes under $V/fo.
# A screw head or a nut overlapping a solid on its own body was checked by nothing: interference skips same-body FST
# pairs. The PR #2 review repro (a rib through an M4 head), push-assist PA-A2-T12 (a nut in the sliding piston) and a
# nut with no pocket must fail; a counterbore, a nut trap (also turned 30 deg), a side-slot nut and a declared captive
# pressed nut must not; a rib grazing a head corner warns. Review: hand-modelled bored nuts (buried: fail; in a trap:
# pass) and a triangulated bored nut with no bolt (buried: fail). The cases are in fastener_overlap_build.py.
mkdir -p "$V/fo"
$CAD build "$ROOT/tools/prior_art/cadcheck_head_overlap_repro.py" -- --out "$V/fo/repro" > "$V/fo/repro.log" 2>&1
$CAD check "$V/fo/repro/repro.blend" --out "$V/fo/repro/cadcheck.json" > /dev/null 2>&1
$CAD build "$ROOT/tools/verify.d/fastener_overlap_build.py" -- --out "$V/fo" > "$V/fo/build.log" 2>&1
$CAD check "$V/fo/fo.blend" "$V/fo/checks.json" "$V/fo/cadcheck.json" > /dev/null 2>&1
$CAD check "$V/fo/fo.blend" --out "$V/fo/noconf.json" --only fasteners > /dev/null 2>&1
python3 -I - "$V/fo" <<'EOF' > "$V/fo/asserts.txt"
import json, re, sys
d = sys.argv[1]
def load(f):
    try:
        return json.load(open("%s/%s" % (d, f)))["summary"]
    except Exception as e:
        print("FAIL fastener overlap: no report %s (%s)" % (f, e)); sys.exit()
def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "fastener overlap " + msg)
r = load("repro/cadcheck.json")
say(r["fails"] == 1 and "FST_m4 head overlaps PRT_rib by" in r["fail_list"][0],
    "repro (rib 3.2 mm off an M4 head, 0.5 mm above the bearing face) fails: %s" % r["fail_list"])
s = load("cadcheck.json")
F, W = s["fail_list"], s["warn_list"]
for pat in ("FST_fo_nut_nut overlaps PRT_fo_piston by", "FST_fo_buried overlaps PRT_fo_solid by",
            "FST_fo_bburied_nut overlaps PRT_fo_bburied_block by", "FST_fo_tri_nut overlaps PRT_fo_tri_block by"):
    say(any(pat in x for x in F), "fails: %s" % (next((x for x in F if pat in x), pat + " NOT FOUND")))
g = [x for x in W if "FST_fo_graze head grazes PRT_fo_graze_rib" in x]
say(len(g) == 1 and not any("FST_fo_graze" in x for x in F), "warns (near-zero contact): %s" % (g or "NOT FOUND"))
quiet = [x for x in F + W for n in ("cb", "trap", "rot", "slot", "press", "btrap") if re.search(r"\bFST_fo_%s(_nut)?\b" % n, x)]
say(not quiet, "counterbore, nut trap, trap turned 30 deg, side-slot nut, captive pressed nut and bored nut in a trap: %s" % (
    quiet or "no findings"))
ff, fw = [x for x in F if x.startswith("fasteners")], [x for x in W if x.startswith("fasteners")]
say(len(ff) == 4 and len(fw) == 3, "exactly 4 fasteners fails and 3 warns (graze; the buried and the triangulated nut have no bolt): "
    "%d, %d" % (len(ff), len(fw)))
say(not any("probe came out empty" in x for x in json.load(open(d + "/cadcheck.json"))["not_checked"]), "no fastener left untested (empty probe)")
n = load("noconf.json")
say(any("FST_fo_press_nut overlaps PRT_fo_press_block by" in x for x in n["fail_list"]),
    "the pressed nut fails without its captive entry (negative control)")
EOF
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/fo/asserts.txt"
