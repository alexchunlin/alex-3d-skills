# slide_out through allowed pairs (sourced by tools/verify_all.sh; uses $ROOT $CAD $V, calls ok/bad). Writes under $V/sa.
# watch: @core tools/verify.d/slide_allow_build.py
# A slide row dropped every part an allow rule covered against a mover, so push-assist A7's load cell slid through the
# cartridge it was allowed 3 mm3 against (zero-gap seats) and the unfittable cell passed for two rounds (PA-A7-T19a).
# Allowed pairs are now obstacles, bounded by max_mm3 (with none: their overlap at rest). The a7 slot must fail past
# the allow; the a8 slot, a crush pad within its allow and a nut pulled off its stud must pass. An allow that measures
# 0 mm3 everywhere, or covers no pair, is a config warn, never a design warn (PA-A8-T6). PR #18 review: a snap riding a
# row fails unless it is in the row's flex; an allow insertion needs (a snap lid under a lip) or one that hides a
# clearance warn (an arm 0.70 mm from a wall) is not stale, and --only interference reports none. Cases: slide_allow_build.py.
CAD="${CAD:-$ROOT/skills/print-cad-blender/scripts/cad}"   # set by verify_all; this default lets the script run on its own
mkdir -p "$V/sa"
$CAD build "$ROOT/tools/verify.d/slide_allow_build.py" -- --out "$V/sa" > "$V/sa/build.log" 2>&1
$CAD check "$V/sa/sa.blend" "$V/sa/checks.json" "$V/sa/cadcheck.json" --only slide,interference,insertion > /dev/null 2>&1
$CAD check "$V/sa/sa.blend" "$V/sa/checks.json" "$V/sa/only_int.json" --only interference > /dev/null 2>&1
# the controls: the lid and arm allows removed (an overlay's allow list replaces the base's under --overlay-only)
python3 -I -c "import json,sys; a=json.load(open(sys.argv[1]))['allow']; json.dump({'allow': [x for x in a if x['a'] not in ('PRT_sa_h_lid', 'PRT_sa_i_arm')]}, open(sys.argv[2], 'w'))" \
  "$V/sa/checks.json" "$V/sa/no_hi.json"
$CAD check "$V/sa/sa.blend" "$V/sa/checks.json" "$V/sa/no_hi_out.json" --only interference,insertion --overlay "$V/sa/no_hi.json" --overlay-only > /dev/null 2>&1
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
d1 = [x for x in F if x.startswith("slide: d1:")]
d3 = [x for x in F if x.startswith("slide: d3:")]
say(len(d1) == 1 and "past the 0.5 mm3 its allow covers" in d1[0] and "row's `flex`" in d1[0]
    and len(d3) == 1 and "at rest plus vol_tol" in d3[0] and "row's `flex`" in d3[0] and "needs max_mm3" in d3[0]
    and row("d2: snap hook off over the ridge").get("blocked_by") is None and row("d2: snap hook off over the ridge").get("flexed"),
    "a snap riding the row fails without flex, bounded (d1) or not (d3), and says so; with flex it passes (d2): %s" % [x[:110] for x in d1 + d3])
say(len([x for x in F if x.startswith("slide:")]) == 4 and not [x for x in W if x.startswith("slide:")],
    "exactly 4 slide fails (short, nut sideways, d1, d3) and no slide warns: %s" % [x[:60] for x in F + W if x.startswith("slide:")])
st = [x for x in C if "possibly stale" in x]
want = ("allow PRT_sa_fixed_cart x BUY_sa_fixed_cell: 0 mm3 on its 1 pair at home and in 1 slide row",
        "allow BUY_sa_gone x PRT_*: covers no pair", "allow PRT_sa_d2_hook x PRT_sa_d2_base: 0 mm3 on its 1 pair at home;")
say(len(st) == 3 and all(any(x.startswith(w) for x in st) for w in want) and all("check what it was for" in x for x in st)
    and set(s["unused_allows"]) == {"PRT_sa_fixed_cart x BUY_sa_fixed_cell", "BUY_sa_gone x PRT_*", "PRT_sa_d2_hook x PRT_sa_d2_base"},
    "unused allows (0 mm3 everywhere; no pair; d2's, which its row's flex replaces) are config warns: %s" % st)
say(not any("possibly stale" in x or "covers no pair" in x for x in F + W), "and never design fails or warns")
def load(f):
    try:
        return json.load(open("%s/%s" % (d, f)))["summary"]
    except Exception as e:
        return {"error": str(e)}
n = load("no_hi_out.json")
nh = [x for x in n.get("warn_list", []) if x.startswith("insertion: PRT_sa_h_lid") and "no straight way in" in x]
ni = [x for x in n.get("fail_list", []) + n.get("warn_list", []) if x.startswith("clearance: PRT_sa_i_arm to PRT_sa_i_wall 0.7")]
say(not any(k.startswith(("PRT_sa_h_lid", "PRT_sa_i_arm")) for k in s["unused_allows"]) and nh and ni,
    "allows that insertion needs (snap lid under a lip) or that hide a clearance warn (arm at 0.70 mm) are not stale; without "
    "them: %s / %s" % ([x[:70] for x in nh] or "NO INSERTION WARN", [x[:70] for x in ni] or "NO CLEARANCE WARN"))
o = load("only_int.json")
say(o.get("unused_allows", "missing") is None and not [x for x in o.get("config_warns", []) if "possibly stale" in x],
    "--only interference (slide and insertion rows not run) reports no unused allows: %s" % o.get("unused_allows", o))
EOF
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/sa/asserts.txt"
