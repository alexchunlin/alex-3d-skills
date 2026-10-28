# cadcheck fasteners: where a straight bit would clear a screw it can't reach (push-assist PA-A3-T10).
# watch: @core tools/verify.d/fastener_access_hint_build.py
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V, calls ok/bad). Writes under $V/ah. About 20 s. Four M4s in wells,
# cases in fastener_access_hint_build.py: under a lid, under a lid edge 1.8 mm short of the axis, open, 70 mm deep,
# under a purchased board. origin/next gives the same 3 fails and 1 warn without the [bit: ...] text.
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
lid, edge, deep, buy = line("FST_ah_lid"), line("FST_ah_edge"), line("FST_ah_deep"), line("FST_ah_buy")
say(lid in F and "[bit: along the axis a 58 mm bit through a Ø6 hole in PRT_ah_lid_lid (open space 48 mm out); no tilt up to 10 deg" in lid,
    "under a lid: the clear bit length through it, no tilt: %s" % lid)
say(edge in F and "tilted 2 deg toward +x it clears, reach 48 mm" in edge, "under a lid edge: 2 deg toward +x clears: %s" % edge)
say(deep in W and deep.startswith("fasteners: FST_ah_deep needs a 92 mm+ bit/extension") and "[bit: no tilt up to 10 deg clears" in deep,
    "70 mm deep: the warn keeps its text and gains the hint: %s" % deep)
say(buy in F and "[bit: along the axis BUY_ah_buy_lid in the way, not printed;" in buy and "hole" not in buy,
    "under a purchased board: names it, suggests no hole through it: %s" % buy)
say(not line("FST_ah_open") and "bit_hint" not in json.dumps([r for r in rep["checks"]["fasteners"]["rows"] if r["object"] == "FST_ah_open"]),
    "a reachable screw reports nothing new (negative control)")
fa = [x for x in F if x.startswith("fasteners")]
wa = [x for x in W if x.startswith("fasteners")]
say(len(fa) == 3 and len(wa) == 1, "counts as before the hint: 3 fasteners fails, 1 warn: %d, %d" % (len(fa), len(wa)))
PY
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/ah/asserts.txt"
