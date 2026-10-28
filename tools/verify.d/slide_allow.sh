# slide_out through allowed pairs (sourced by tools/verify_all.sh; uses $ROOT $CAD $V, calls ok/bad). Writes under $V/sa.
# watch: @core tools/verify.d/slide_allow_build.py
# A slide row dropped every part an allow rule covered against a mover, so push-assist A7's load cell slid through the
# cartridge it was allowed 3 mm3 against (zero-gap seats) and the unfittable cell passed for two rounds (PA-A7-T19a).
# Allowed pairs are now obstacles, bounded by max_mm3 (with none: their overlap at rest). The a7 slot must fail past
# the allow; the a8 slot, a crush pad within its allow and a nut pulled off its stud must pass. An allow that measures
# 0 mm3 everywhere, or covers no pair, is a config warn, never a design warn (PA-A8-T6). Cases: slide_allow_build.py.
mkdir -p "$V/sa"
$CAD build "$ROOT/tools/verify.d/slide_allow_build.py" -- --out "$V/sa" > "$V/sa/build.log" 2>&1
$CAD check "$V/sa/sa.blend" "$V/sa/checks.json" "$V/sa/cadcheck.json" --only slide,interference > /dev/null 2>&1
python3 -I - "$V/sa" <<'EOF' > "$V/sa/asserts.txt"
import json, sys
d = sys.argv[1]
try:
    r = json.load(open(d + "/cadcheck.json"))
except Exception as e:
    print("FAIL slide allow: no report (%s, see %s/build.log)" % (e, d)); sys.exit()
s = r["summary"]
rows = {x["object"]: x for x in r["checks"]["slide"]["rows"]}
row = lambda name: rows.get(name) or {}
def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "slide allow " + msg)
F, W, C = s["fail_list"], s["warn_list"], s["config_warns"]
sh = row("short: the cell out along the slot")
f = [x for x in F if x.startswith("slide: short:")]
say(len(f) == 1 and "blocked by ['PRT_sa_short_cart']" in f[0] and "past the 3 mm3 its allow covers" in f[0]
    and sh.get("over_allow", {}).get("PRT_sa_short_cart", {}).get("volume_mm3", 0) > 3,
    "a7 slot (wedge over the exit, 3 mm3 allow) fails past the allow: %s" % (f or "NOT FOUND"))
fx, cr = row("fixed: the cell out along the slot"), row("crush: the cell out along the slot")
say(fx.get("dist") == 40 and fx.get("blocked_by") is None and not any("fixed" in x for x in F + W),
    "a8 slot (past the face) passes with the same allow (negative control): blocked_by %s" % fx.get("blocked_by"))
ride = cr.get("allowed", {}).get("PRT_sa_crush_cart", {}).get("max_mm3", 0)
say(cr.get("dist") == 40 and cr.get("blocked_by") is None and 1.5 <= ride <= 1.7 and not any("crush" in x for x in F + W),
    "crush pad rides within its 3 mm3 allow: %s mm3 recorded, no finding" % ride)
ax, sw = row("nut: the cell pulled off its nut along the stud"), row("nut: the cell out sideways with its nut left on")
say(ax.get("blocked_by") is None and sw.get("blocked_by") == ["BUY_sa_nut_nut"] and len([x for x in F if x.startswith("slide: nut:")]) == 1,
    "an allow with no max_mm3 (nut on its stud): off along the stud passes, sideways blocked by the nut at %s mm" % sw.get("blocked_at_mm"))
say(len([x for x in F if x.startswith("slide:")]) == 2 and not [x for x in W if x.startswith("slide:")],
    "exactly 2 slide fails and no slide warns: %s" % [x[:60] for x in F + W if x.startswith("slide:")])
st = [x for x in C if "possibly stale" in x]
want = ("allow PRT_sa_fixed_cart x BUY_sa_fixed_cell: 0 mm3 on its 1 pair at home and in 1 slide row",
        "allow BUY_sa_gone x PRT_*: covers no pair")
say(len(st) == 2 and all(any(x.startswith(w) for x in st) for w in want) and set(s["unused_allows"]) == {
    "PRT_sa_fixed_cart x BUY_sa_fixed_cell", "BUY_sa_gone x PRT_*"}, "unused allows (0 mm3 everywhere; no pair) are config warns: %s" % st)
say(not any("possibly stale" in x or "covers no pair" in x for x in F + W), "and never design fails or warns")
EOF
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/sa/asserts.txt"
