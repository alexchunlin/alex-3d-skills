# features.fastener_joint (sourced by tools/verify_all.sh; uses $ROOT $CAD $V, calls ok/bad). Writes under $V/fj.
# watch: @core tools/verify.d/fastener_joint_build.py tools/verify.d/fastener_joint_review.py
# Builds the same 4-joint test assembly at M3 and at M4 (nut trap, self-tap, insert, tapped purchased part), then:
# lengths picked from the stock list by the rule, hole diameters measured in the cut parts, cadcheck 0 fails with
# the bolt through its nut, and the four mistakes it must refuse (FINDINGS A1-F10, A2-F3, A3-F5).
FJB="$ROOT/tools/verify.d/fastener_joint_build.py"
mkdir -p "$V/fj"
$CAD build "$FJB" --size M3 --out "$V/fj/M3" --errors > "$V/fj/M3.log" 2>&1
$CAD build "$FJB" --size M4 --out "$V/fj/M4" > "$V/fj/M4.log" 2>&1
for s in M3 M4; do $CAD check "$V/fj/$s/fj.blend" "" "$V/fj/$s/cadcheck.json" > /dev/null 2>&1; done
python3 -I - "$V/fj" <<'EOF' > "$V/fj/asserts.txt"
import json, sys
d = sys.argv[1]
want = {  # stack: plate 4.7 on block 11; bracket 3 on a motor with an 8 mm tapped hole
    "M3": dict(L={"FST_fj_nut": 16, "FST_fj_tap": 12, "FST_fj_ins": 12, "FST_fj_motor": 8},
               D={"clear": 3.4, "pilot": 2.5, "trap_af": 5.7, "insert": 4.0}),
    "M4": dict(L={"FST_fj_nut": 18, "FST_fj_tap": 14, "FST_fj_ins": 14, "FST_fj_motor": 10},
               D={"clear": 4.5, "pilot": 3.3, "trap_af": 7.2, "insert": 5.6}),
}
for s, w in want.items():
    try:
        r = json.load(open("%s/%s/fj_report.json" % (d, s)))
        c = json.load(open("%s/%s/cadcheck.json" % (d, s)))
    except Exception as e:
        print("FAIL %s: no report (%s)" % (s, e)); continue
    got = {n: j["length"] for n, j in r["joints"].items()}
    print(("PASS" if got == w["L"] else "FAIL") + " fastener_joint %s lengths %s (want %s)" % (s, got, w["L"]))
    h, D = r["holes"], w["D"]
    meas = {"clear": [h[k]["max_d"] for k in ("nut_plate_clear", "nut_block_clear", "tap_plate_clear", "ins_block_tip", "motor_bracket_clear")],
            "pilot": [h["tap_block_pilot"]["max_d"]], "trap_af": [h["nut_trap"]["min_d"]], "insert": [h["ins_block_pocket"]["max_d"]]}
    off = {k: v for k, v in meas.items() if any(abs(x - D[k]) > 0.03 for x in v)}
    print(("PASS" if not off else "FAIL") + " fastener_joint %s measured holes clear/pilot/trap/insert = %s (want %s)" % (
        s, {k: v[0] for k, v in meas.items()}, D))
    rows = {x["object"]: x for x in c["checks"]["fasteners"]["rows"]}
    nb = rows.get("FST_fj_nut", {})
    nut = nb.get("nut") or {}
    through = nut and nb["nut_gap_mm"] == 0 and nb["engagement_mm"] >= nut["len_mm"] and nb["length_mm"] > nut["to_mm"]
    ffails = [x for x in c["summary"]["fail_list"] if x.startswith("fasteners")]
    print(("PASS" if through and not ffails and c["summary"]["fails"] == 0 and c["summary"]["warns"] == 0 else "FAIL") +
          " fastener_joint %s cadcheck: bolt %.1f passes its nut (%.1f-%.1f) by %.1f, %d fasteners fails, %d fails, %d warns" % (
              s, nb.get("length_mm", 0), nut.get("from_mm", 0), nut.get("to_mm", 0), nb.get("length_mm", 0) - nut.get("to_mm", 0),
              len(ffails), c["summary"]["fails"], c["summary"]["warns"]))
EOF
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/fj/asserts.txt"
for pat in "FJ_ERR reversed: .*flip \`into\`" "FJ_ERR thin_host: .*only 4.7 mm of thread" "FJ_ERR short_bolt: .*stops 1.00 mm short of its nut" \
           "FJ_ERR buried_head: .*1.00 mm inside" "FJ_DEEP length=30 deepened=1.7"; do
  grep -q "$pat" "$V/fj/M3.log" && ok "fastener_joint refuses/handles: $pat" || bad "fastener_joint missing: $pat"
done
# the independent review's cases (fastener_joint_review.py): pre-drilled purchased board, sloped seat, blind boss,
# self-tap into a purchased part, air gap, csk knife edge, length reuse / lengths= / project checks.json, M2 at 2 d
$CAD build "$ROOT/tools/verify.d/fastener_joint_review.py" --out "$V/fj/review" > "$V/fj/review.log" 2>&1
$CAD check "$V/fj/review/fjr.blend" "" "$V/fj/review/cadcheck.json" > /dev/null 2>&1
grep "^FJR \(PASS\|FAIL\)" "$V/fj/review.log" | while read -r _ st msg; do echo "$st fastener_joint review $msg"; done > "$V/fj/review_asserts.txt"
[ "$(grep -c . "$V/fj/review_asserts.txt")" -ge 18 ] || echo "FAIL fastener_joint review: $(grep -c . "$V/fj/review_asserts.txt") of 18 case lines (build log $V/fj/review.log)" >> "$V/fj/review_asserts.txt"
python3 -I - "$V/fj/review/cadcheck.json" <<'PY' >> "$V/fj/review_asserts.txt"
import json, sys
try:
    c = json.load(open(sys.argv[1]))
except Exception as e:
    print("FAIL fastener_joint review cadcheck: no report (%s)" % e); sys.exit()
rows = {r["object"]: r for r in c["checks"]["fasteners"]["rows"]}
fw = [w for w in c["summary"]["warn_list"] if w.startswith("fasteners")]
m2 = rows.get("FST_fjr_m2", {})
print(("PASS" if m2.get("engagement_mm") == 4.0 and m2.get("engagement_need_mm") == 4.0 and not fw else "FAIL") +
      " fastener_joint review cadcheck: M2 x 6 with exactly 2 d reads %s of %s mm, %d fasteners warns" % (
          m2.get("engagement_mm"), m2.get("engagement_need_mm"), len(fw)))
b = [rows.get("FST_fjr_board_%d" % i, {}) for i in range(4)]
ok = all(r and not r["head_buried_in"] and not r["into_purchased"] and r["standoff_mm"] == 0 and r["thread_host"] == "PRT_fjr_mount" for r in b)
print(("PASS" if ok and c["summary"]["fails"] == 0 else "FAIL") +
      " fastener_joint review cadcheck: 4 M2.5 through the pre-drilled board seat on it, thread the boss, %d fails" % c["summary"]["fails"])
s = rows.get("FST_fjr_slope", {})
print(("PASS" if s and not s["head_buried_in"] else "FAIL") + " fastener_joint review cadcheck: spot-faced sloped seat, head buried in %s" % s.get("head_buried_in"))
PY
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/fj/review_asserts.txt"
