# cadcheck insertion order within a step (sourced by tools/verify_all.sh; uses $ROOT $CAD $V, calls ok/bad). Writes under $V/iss.
# watch: @core tools/verify.d/insertion_same_step_build.py
# Push-assist A6/A7 (PA-A7-T7, T19, T17): the load cell could not be fitted into its cartridge, and cad check passed:
# the cell and the cartridge were in one assembly step ("parts of one step go in in any order, so neither is an
# obstacle"), a bounded allow on the pair dropped it, and the cell's only way in (45 deg along the stud slots) is
# off-axis. Must warn under the A7-shaped config: the a6 cell (round stud holes) and the a7 cell (slots that stop
# inside the wall), no way in in any order and no free diagonal; the a8 cell (slots out through the corner) free only
# along [-0.71, 0, 0.71]. Under a step "order": the board ordered after the lid that closes over it, a typo'd glob; a
# board on one glob with its tray is tested (an order found within the glob). Negative controls: the trays without
# "order" (an order is found; the lid's differs from its listing, a note); and under the A8-shaped config (cartridge
# first, the cell in its own step, a8 with insert_dirs, the lid step in its right order) only the a6 and a7 cells warn.
# PR #19 review cases (checks_review.json): C1 a block that goes in before the plate it rests on (a note), C3 a 30 deg
# slot (free along [-0.5, 0, 0.87]), C4 a crush-rib pin with a bounded allow (a press fit: no warn), C5 discs stacked
# in a cup listed top first (a note: bottom first), C6 an interlocked pair on no glob of a partial "order" (warns).
mkdir -p "$V/iss"
$CAD build "$ROOT/tools/verify.d/insertion_same_step_build.py" -- --out "$V/iss" > "$V/iss/build.log" 2>&1
for c in a7 order fixed review; do
  f=checks_$c.json; [ $c = a7 ] && f=checks.json
  $CAD check "$V/iss/iss.blend" "$V/iss/$f" "$V/iss/$c.json" --only insertion > /dev/null 2>&1
done
python3 -I - "$V/iss" <<'EOF' > "$V/iss/asserts.txt"
import json, sys
d = sys.argv[1]
def load(f):
    try:
        r = json.load(open("%s/%s.json" % (d, f)))
        return r, [x for x in r["summary"]["warn_list"] if x.startswith("insertion: ")], {x["object"]: x for x in r["checks"]["insertion"]["rows"]}
    except Exception as e:
        print("FAIL insertion same-step: no report %s (%s)" % (f, e)); sys.exit()
def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "insertion same-step " + msg)
r, W, rows = load("a7")
one = lambda pat: [x for x in W if pat in x]
for c in ("a6", "a7"):
    w = one("BUY_%s_cell (step" % c)
    say(len(w) == 1 and "past PRT_%s_cartridge of the same step, in any order of the step's parts" % c in w[0] and "the 20 cube diagonals or 30/60 deg" in w[0],
        "A7 config: the %s cell has no way in, in any order, and no free diagonal: %s" % (c, w or "NOT FOUND"))
w = one("BUY_a8_cell (step")
say(len(w) == 1 and "in any order" in w[0] and "free along [-0.71, 0, 0.71] (off-axis" in w[0],
    "A7 config: the a8 cell is free only off-axis, up-inboard at 45 deg, and the bounded allow on the pair hides nothing: %s" % (w or "NOT FOUND"))
say(len(W) == 3, "A7 config: those 3 insertion warns and none on the trays without an order: %d %s" % (len(W), [x[:50] for x in W]))
o = {x["step"][:3]: x for x in r["checks"]["insertion"]["step_orders"]}
say(o["lid"]["order"] == ["PRT_lid_tray", "BUY_lid_board", "PRT_lid_lid"] and o["lid"]["listed_differs"] and not o["ok "]["listed_differs"]
    and o["a6 "]["no_order"] == ["BUY_a6_cell", "PRT_a6_cartridge"],
    "step_orders: the lid tray's order found (tray, board, lid; not as listed), ok's as listed, the a6 pair with none: %s" % o["lid"]["order"])
seat = {(x["buy"], x["seat"]) for x in r["checks"]["insertion"]["buy_seat_same_step"]}
say(("BUY_a6_cell", "PRT_a6_cartridge") in seat and ("BUY_tie_board", "PRT_tie_tray") in seat and len(seat) == 6,
    "buy_seat_same_step lists the 3 cells on their base plates and the 3 boards in their trays: %s" % sorted(seat))
r, W, rows = load("order")
w = one("BUY_lid_board (step")
say(len(w) == 1 and "which the step's \"order\" puts before it" in w[0] and "go in in the order PRT_lid_tray, BUY_lid_board, PRT_lid_lid" in w[0],
    "order [tray, lid, board]: the board is blocked by the lid, and the order that works is given: %s" % (w or "NOT FOUND"))
o = {x["step"][:3]: x for x in r["checks"]["insertion"]["step_orders"]}
say(not one("_tie_") and sorted(rows[n]["same_step_before"] for n in ("BUY_tie_board", "PRT_tie_tray")) == [0, 1],
    "a BUY on one order glob with its seat is tested in an order found within the glob: %s" % o["tie"]["order"])
say(len(one("\"order\" glob PRT_ok_lidd matches none")) == 1 and len(W) == 2 and rows["PRT_ok_lid"]["same_step_before"] == 2,
    "a typo'd order glob warns; exactly 2 warns: %s" % [x[:60] for x in W])
r, W, rows = load("fixed")
say(len(W) == 2 and all("with the earlier steps' parts in place" in x and "the 20 cube diagonals" in x for x in W)
    and {x.split()[1] for x in W} == {"BUY_a6_cell", "BUY_a7_cell"},
    "A8 config: only the a6 and a7 cells warn (no way in past the cartridge of the step before): %s" % [x[:60] for x in W])
say(rows["BUY_a8_cell"]["free_dir"] == "dir [-0.7071, 0, 0.7071]" and rows["BUY_lid_board"]["free_dir"] == "+Z" and rows["PRT_lid_lid"]["same_step_before"] == 2,
    "A8 config: the a8 cell goes in along its insert_dirs, the board before the lid by the step's order: %s, %s" % (
        rows["BUY_a8_cell"]["free_dir"], rows["BUY_lid_board"]["free_dir"]))
r, W, rows = load("review")
N = r["summary"]["notes"]
say(any("step 'c1 plate on the floor, block on the plate': the listed order doesn't fit; it fits as PRT_c1_block, PRT_c1_plate" in x for x in N),
    "C1: the block goes in before the plate it rests on: a note, not a warn: %s" % [x[:90] for x in N if "c1" in x])
w = one("BUY_c3_cell (step")
say(len(w) == 1 and "free along [-0.5, 0, 0.87] (off-axis" in w[0], "C3: the 30 deg slot is found off-axis: %s" % (w or "NOT FOUND"))
say(not one("c4") and rows["BUY_c4_pin"]["free_dir"] == "+Z", "C4: a crush-rib pin under a bounded allow goes in +Z (a press fit drops the pair): %s" % rows["BUY_c4_pin"]["free_dir"])
say(any("c5 discs, top first" in x and "fits as PRT_c5_disc_0, PRT_c5_disc_1," in x for x in N) and not one("c5"),
    "C5: discs listed top first: a note, bottom first fits (face samples see the disc below): %s" % [x[:90] for x in N if "c5" in x])
w = one("PRT_c6_cell (step")
say(len(w) == 1 and "in any order of its \"order\" glob's parts" in w[0] and "PRT_c6_cartridge" in w[0],
    "C6: an interlocked pair on no glob of a partial order still warns: %s" % (w or "NOT FOUND"))
say(len(W) == 2, "review config: exactly the C3 and C6 warns: %s" % [x[:50] for x in W])
EOF
while read -r st msg; do [ "$st" = PASS ] && ok "$msg" || bad "$msg"; done < "$V/iss/asserts.txt"
