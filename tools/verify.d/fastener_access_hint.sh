# cadcheck fasteners: where a straight bit would clear a screw it can't reach (push-assist PA-A3-T10).
# watch: @core tools/verify.d/fastener_access_hint_build.py
# needs: 4a
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V, calls ok/bad). Writes under $V/ah. About 20 s. Four M4s in wells,
# cases in fastener_access_hint_build.py: under a lid, under a lid edge 1.8 mm short of the axis, open, 70 mm deep,
# under a purchased board; from the PR #17 review, under two lids, under a lid on a joint, a 6 deg tilt (ball-end) and
# an undeclared captive stud. origin/next gives the same 7 fails and 1 warn without the [bit: ...] text.
mkdir -p "$V/ah"
$CAD build "$ROOT/tools/verify.d/fastener_access_hint_build.py" -- --out "$V/ah" > "$V/ah/build.log" 2>&1
$CAD check "$V/ah/ah.blend" "$V/ah/checks.json" "$V/ah/cadcheck.json" --only fasteners > /dev/null 2>&1
python3 -I - "$V/ah" <<'PY' > "$V/ah/asserts.txt"
import json, sys
d = sys.argv[1]
try:
    rep = json.load(open(d + "/cadcheck.json"))
except Exception as e:
    print("FAIL access hint: no report (%s)" % e); sys.exit()
s = rep["summary"]
F, W = s["fail_list"], s["warn_list"]
def line(n):
    return next((x for x in F + W if x.startswith("fasteners: %s " % n)), "")
def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "access hint " + msg)
L = {n: line("FST_ah_" + n) for n in ("lid", "edge", "deep", "buy", "open", "two", "mov", "ball", "cap")}
lid, edge, deep, buy = L["lid"], L["edge"], L["deep"], L["buy"]
say(lid in F and "[bit: along the axis a 58 mm bit through a Ø6 hole in PRT_ah_lid_lid (open space 48 mm out), or fit "
    "PRT_ah_lid_lid after this screw (assembly_order); no tilt up to 10 deg" in lid,
    "under a lid: the clear bit length through it (or fit the lid after), no tilt: %s" % lid)
say(edge in F and "tilted 2 deg toward +x a straight bit clears, reach 48 mm" in edge, "under a lid edge: 2 deg toward +x clears: %s" % edge)
say(deep in W and deep.startswith("fasteners: FST_ah_deep needs a 92 mm+ bit/extension") and "[bit: no tilt up to 10 deg clears" in deep,
    "70 mm deep: the warn keeps its text and gains the hint: %s" % deep)
say(buy in F and "[bit: along the axis BUY_ah_buy_lid in the way, not printed;" in buy and "hole" not in buy,
    "under a purchased board: names it, suggests no hole through it: %s" % buy)
say(L["two"] in F and "along the axis PRT_ah_two_lid and PRT_ah_two_lid2 in the way (open space 58 mm out): fit them after this "
    "screw (assembly_order)" in L["two"] and "hole" not in L["two"],
    "two lids (review: a2's flywheel bolts were told to drill through three parts): no hole, fit them after: %s" % L["two"])
say(L["mov"] in F and "PRT_ah_mov_lid (moves) in the way" in L["mov"] and "fit it after this screw" in L["mov"] and "hole" not in L["mov"],
    "a lid on a joint: it moves, no hole: %s" % L["mov"])
say(L["ball"] in F and "a ball-end driver tilted 6 deg toward +x clears, reach 48 mm" in L["ball"],
    "a tilt over 3 deg names a ball-end driver: %s" % L["ball"])
say(L["cap"] in F and "[bit: the head is closed in 4.2 mm out and FST_ah_cap_nut is on the bolt: if the nut is what turns, declare "
    "FST_ah_cap captive (fasteners.captive)]" in L["cap"], "a bolt with its nut and a closed-in head reads as an undeclared captive stud: %s" % L["cap"])
say(not L["open"] and "bit_hint" not in json.dumps([r for r in rep["checks"]["fasteners"]["rows"] if r["object"] == "FST_ah_open"]),
    "a reachable screw reports nothing new (negative control)")
say('"_hint":' not in json.dumps(rep["checks"]["fasteners"]["rows"]), "the hint's working data stays out of the report")
fa = [x for x in F if x.startswith("fasteners")]
wa = [x for x in W if x.startswith("fasteners")]
say(len(fa) == 7 and len(wa) == 1, "counts as before the hint: 7 fasteners fails, 1 warn: %d, %d" % (len(fa), len(wa)))
PY
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/ah/asserts.txt"
# the review's a2 case on the archived design (4a's report): the flywheel bolts are behind flywheel, hood and launcher
# body; the hint must not tell anyone to drill through all three
python3 -I - "$V/a2/cadcheck.json" <<'PY' > "$V/ah/a2.txt"
import json, sys
try:
    s = json.load(open(sys.argv[1]))["summary"]
except Exception as e:
    print("FAIL access hint: no a2 report from 4a (%s)" % e); sys.exit()
fw = [x for x in s["fail_list"] if x.startswith("fasteners: FST_fw_bolt_") and "cannot be driven" in x]
ok = fw and all("[bit: along the axis " in x and "in the way" in x and "fit them after this screw (assembly_order)" in x
                and "hole" not in x for x in fw)
print(("PASS" if ok else "FAIL") + " access hint a2 flywheel bolts (review): parts in the way, fit them after, no hole: %s" % (fw[:1] or s["fail_list"][:3]))
PY
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/ah/a2.txt"
