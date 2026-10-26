# features.fastener_joint: one call per fastened joint

Branch `feat/fastener-joint`, 2026-10-25, revised 2026-10-26 after an independent review (section "After review").
Code: `skills/print-cad-blender/scripts/cadlib/features.py` (`SIZES`, `size_rules`, `check_value`, `use_checks`,
`axis_stack`, `fastener_joint`, `fastener_summary`), `asm.py` (`FASTENER_SPECS` for every size, `nut(size=)`, the
`FASTENERS` build-log line), `cadcheck.py` (thread engagement in shank diameters). Test: `tools/verify.d/fastener_joint.sh`,
which builds `tools/verify.d/fastener_joint_build.py` and `tools/verify.d/fastener_joint_review.py`.

Use it when a screw is the right join: a load path, service access, a metal part. Parts that are neither loaded nor
serviced join better with snaps, press-fit pins, bayonets, captive tabs or printed hinges (SKILL.md "Joining").

```python
cuts = {}
F.fastener_joint("FST_lid_0", "M3", at, DOWN, [lid, shell], style="nut", head="cap", step="3", cuts=cuts)
G.csg(shell, sub=cuts[shell.name])
```

## Why it exists

| Evidence | What happened | What the call does now |
|---|---|---|
| v2 `parts/base.py:64`, `launcher.py:43`, `pan_stage.py:19` | The v2 designer wrote the same `screw()` wrapper three times (14 lines). It runs `features.screw_hole` once per cut list and then `asm.fastener`. | One library call. |
| FINDINGS A2-F3 | An M3 x 16 pinch bolt ended 0.36 mm short of its nut because the length was picked by hand. | The length comes from the measured stack. A given length that stops short raises `FastenerError: ... stops 1.00 mm short of its nut`. |
| FINDINGS A3-F5 (an A2 candidate first) | The hinge screw had 2.5 mm of thread in PLA (cadcheck read 2.0 until its walk was fixed). | A self-tap into less than 2 d raises `... gives only 4.7 mm of thread on this axis; M3 selftap needs 6.0. Add a boss, use style='nut' or 'insert'`. |
| FINDINGS A1-F10 | Screws were modelled reversed. | If no part lies ahead of `at` along `into`, it raises `... the parts are behind the head: flip into`. A head inside the first part raises `the head would sit 1.00 mm inside ...`. |
| FINDINGS A3-T2 | D3 spent 289 s at `0:13:55` working out which way a stud head faces. | `into` is checked against the geometry, so a wrong guess fails in the same build. |

## What it does

1. **Size table.** `SIZES` covers M2, M2.5, M3, M4 and M5: pitch, clearance (ISO 273 medium), self-tap pilot
   (0.83-0.85 d, above the thread minor diameter), PLA-tap hole, cap/pan/csk head d and h, nut AF and h, trap AF,
   insert hole and length. The M2, M2.5, M4 and M5 holes are table values and need a test-print coupon. The rules that
   cadcheck judges by are read from cadcheck (`check_value`): the project `checks.json` first (`use_checks(path)`,
   `$CAD_CHECKS`, or the `checks.json` beside the build script), then cadcheck's DEFAULTS. That covers
   `stock_lengths`, `max_protrusion` and the engagement (`min_engagement_d` 2.0, `tapped_engagement_d` 1.5, or a
   project's `min_engagement` in mm). The M3 row reads the `m3_*` entries of `RULES` at lookup, so tuning `RULES`
   still works and every existing M3 hole keeps its diameter. Changing the size is one argument: the template has
   `P.SCREW = "M3"`.
2. **Stack.** Each given part is ray-cast along `at`/`into` (a BVH of the world-space mesh, the line offset 0.01 mm
   so it never runs down an edge) and on 8 rays each on two rings: 0.92 x the shank radius and 0.8 x the head radius.
   A part with material on the axis is solid. A part with material only on the rings is already holed on the axis: a
   purchased board, a servo ear, a part cut earlier. It is a pre-drilled layer: counted in the grip, the head seats on
   it, and it is not cut. Parts are sorted by where they start: every part but the last is clamped, and the last one
   holds the thread or the nut. More than 0.3 mm of air between two of them raises (`gap_ok=True` for a stand-off).
   The head seat is sampled at 0.8 x head radius, as cadcheck's head-buried probe is: material more than 0.2 mm above
   the bearing face (a sloped face, or an axis not normal to it) raises with the spot-face that fixes it.
3. **Styles.**
   - `selftap`: pilot in the last part, which must be printed (into a purchased part it raises and points to `tapped`).
   - `nut`: clearance through every part, plus a hex trap at the far face of the last part (`trap=False` puts the nut on that face).
   - `insert`: heat-set pocket in a printed part, plus clearance past it for a longer screw.
   - `tapped`: nothing is cut in a purchased last part. A printed last part gets the PLA-tap hole.

   `sink=` cuts a counterbore (a spot-face on a sloped face) and `head="csk"` cuts a countersink; a countersink deeper
   than the first part's thickness minus `min_wall` raises (knife edge). Teardrops come from `print_up`, given either as
   a vector or as `{part: vector}`.
4. **Length.** The window:
   - `selftap` / `tapped`: thread ≥ 2 d into a printed part, ≥ 1.5 d into a tapped purchased one. A tapped part is capped by `depth=` (the datasheet depth of its hole).
   - `nut`: the bolt passes the nut by at least one pitch.
   - `insert`: the screw runs through the whole insert.

   In every case the tip stays within `fasteners.max_protrusion` of the last material (for an insert, of the insert's
   end once the tip is out of the part, as cadcheck measures it). Self-tap, insert and PLA-tap holes are blind: the
   tip plus 1 mm of pilot stops `min_wall` short of the host's far face, and a host too shallow for that raises
   ("too shallow ... deepen it by 0.6 mm, use style='nut', or pass through_ok=True"). If no stock length fits with a
   nut trap at the face, the trap is sunk deeper by the least amount that makes one fit. In the window it takes a length
   this build already uses for the same spec (the most used), else the shortest. Stock is `lengths=`, else the
   project's `stock_lengths`, else cadcheck's. `asm.write_manifest` prints `FASTENERS n screws, k distinct spec x
   length: ...` and writes it to the manifest as `fastener_summary`.
5. **Placement.** `asm.fastener` places the screw with the same `at`/`into`, and `asm.nut` places the nut. An insert is
   placed as a nut-tagged proxy, so cadcheck checks that the screw runs through it. The record goes to the manifest as
   `parts[FST].fastener_joint`: size, style, stack, grip, length, engagement, protrusion, window, rule and hole
   diameters. It also goes to `features` as `"feature": "fastener_joint"`.
6. **Return.** `{part name: [cutters]}`. Like every other feature, it returns cutters for `geom.csg(sub=...)`; it never
   applies them. Pass `cuts=` to collect several joints, then run one csg per part.

## After review (2026-10-26)

An independent review found the cases below. Each is now a regression in `tools/verify.d/fastener_joint_review.py`
(one `FJR` line per case, asserted by `fastener_joint.sh`), plus a cadcheck run on the joints it keeps.

| Finding | Fix | Evidence (`FJR` line or cadcheck row) |
|---|---|---|
| HIGH: a screw through a part that already has a hole (a purchased board, a servo ear, a part cut earlier) raised "not on the axis". That is v2's MotorGo pattern (4 x M2.5). | Rays on two rings (0.92 x shank radius, 0.8 x head radius) besides the axis. Material only on the rings makes a pre-drilled layer: in the grip, head seated on it, not cut. A hole the shank passes in the last part raises unless the style is `nut` or `tapped` into a purchased part. A purchased clamped part with a hole smaller than the shank raises. | `board`: stack `BUY_fjr_board 0.0-1.6 clear`, `PRT_fjr_mount 1.6-13.6`; M2.5 x 8, 6.40 mm of thread, 0 cuts in the board. cadcheck: the 4 screws seat on the board, thread the boss, nothing runs into the purchased part, 0 fails. |
| MEDIUM: a sloped seat or a tilted axis was accepted, and cadcheck then failed "head buried". | The seat is sampled at 0.8 x head radius, as cadcheck does. Material more than 0.2 mm above the bearing face raises with the spot-face that fixes it (`move at ... and pass sink=`). With `sink`, the counterbore may run deeper than the surface (a spot-face). | `sloped` (12 deg face): "material runs from 0.45 mm above to 0.45 mm below ... move `at` 0.45 mm along `into` and pass sink=1.1"; the suggested call builds, cadcheck head buried in `[]`. `tilted_axis` (10 deg on a flat face): raises the same way. |
| MEDIUM: a blind boss was drilled through its far face without a word. | Self-tap, insert and PLA-tap holes are blind: the screw is capped at t_out - min_wall - 1 mm. Too shallow raises; `through_ok=True` restores through-holes. | `blind`: plate 3 on an 8 mm boss raises "too shallow ... allows <= 8.40. Deepen it by 0.6 mm, use style='nut', or pass through_ok=True"; `through_ok=True` builds M3 x 10; a 10 mm boss gets M3 x 10 with 2.00 mm of PLA measured under the pilot. |
| MEDIUM: a self-tap into a purchased part was accepted. | `selftap` and `insert` into a purchased part raise and point to `style='tapped'`; a nut trap in a purchased part raises (`trap=False`). | `buy_selftap`, `buy_insert`. |
| MEDIUM: an air gap between clamped parts was accepted. | More than 0.3 mm between consecutive parts on the axis raises unless `gap_ok=True`. | `gap`: "0.50 mm of air between PRT_fjr_gplate and PRT_fjr_gblock"; `gap_ok=True` builds. |
| MEDIUM: shortest-fit lengths raise variety (v2: 18 distinct spec x length would become 20; covering windows would give 12). | A length this build already uses for the spec is taken when it fits the window. `lengths=` per joint. The project `checks.json` `fasteners.stock_lengths` (and `min_engagement`, `max_protrusion`) are read, as cadcheck reads them. `asm.write_manifest` prints `FASTENERS n screws, k distinct spec x length` and writes `fastener_summary`. | `reuse`: the second joint (window 8.7-13.1, shortest 10) takes the first's 12; `lengths=[10]` gives 10; a project file with stock `[7, 9, 11, 13]` and `min_engagement 4.0` gives M3 x 9 in an 8.7-13.1 window. Demo 7 screws in 3 kinds, template 4 in 1. |
| Engagement: two rules (cadcheck 4.0 mm, the joint 2 d). | One rule, in cadcheck DEFAULTS (next section). | `rules`: M2 4.0 / 3.0, M2.5 5.0 / 3.75, M3 6.0 / 4.5, M4 8.0 / 6.0, M5 10.0 / 7.5 (printed / tapped purchased). `m2_2d`: M2 x 6 with exactly 4.0 mm of thread; cadcheck reads 4.0 of 4.0, no warn. |
| M2.5 and M2 holes. | M2.5 clearance 2.9 (ISO 273 medium), pilot 2.0 -> 2.1 (0.84 d; minor diameter 1.95). M2 pilot 1.6 -> 1.7. The table comment says the M2, M2.5, M4 and M5 holes need a test-print coupon. | `rules`: M2 2.4 / 1.7, M2.5 2.9 / 2.1. |
| LOW: countersunk M5 in a 2 mm plate. | A countersink deeper than the plate's thickness minus `min_wall` raises. | `csk`: "the M5 countersink is 2.10 mm deep but PRT_fjr_cplate is 2.00 mm thick ... a knife edge". |
| LOW: pan heads. | ISO 7045: M2 4.0 x 1.6 (was 3.8 x 1.3), M2.5 5.0 x 2.1 (k was 1.75). `asm.FASTENER_SPECS` now takes M2 and M2.5 from `SIZES` instead of its own copies. | `rules`. |
| LOW: "no stock length between 4.00 and 3.00". | An empty window says why: "X is too shallow on this axis: 6.0 mm of thread needs a screw >= 9.00 mm, but a blind hole (...) allows <= 8.40". | `blind`. |

Found while fixing: an insert screw that leaves the part was measured from the part's far face, but cadcheck measures
it from the insert's end (the insert is a nut-tagged proxy), so length reuse picked an M4 x 18 insert screw that
cadcheck then warned about (5.2 mm past the insert). The insert window now uses the insert's end once the tip is out
of the part; the M4 test keeps 14 and 0 warns.

## Engagement: one rule for both tools

The reviewer recommended one rule and it is adopted here; the user may override it.

- cadcheck DEFAULTS `fasteners.min_engagement_d: 2.0` (self-tap or PLA-tap into a printed part: M2 4, M2.5 5, M3 6,
  M4 8, M5 10 mm) and `tapped_engagement_d: 1.5` (into a tapped purchased part). The warn names the rule:
  `only 4.0 mm of thread in BUY_motor (needs 4.5: 1.5 d, fasteners.tapped_engagement_d)`.
- A project `fasteners.min_engagement` in mm still replaces both, so old configs behave as before. All seven v2
  configs set 4.0, so v2a1-v2a7 give the same findings.
- `fastener_joint` reads the same keys through `check_value`, as it reads `max_protrusion`.
- cadcheck's thread walk started 0.5 mm in from the tip and so read 0.5 mm short; a joint at exactly 2 d warned. It
  now samples the middle of each 0.5 mm step (`cadcheck.py` `survey_screw`). A3's hinge reads 2.5 mm, the value R3
  measured.

Engagement findings before -> after (designer config, `--only fasteners`; only these warns changed, fails did not):

| Archive | Before | After | Screws |
|---|---|---|---|
| A1 (default config) | 1 engagement warn, 16 warns | 8, 23 | `FST_motor_0..3` into PRT_flywheel 3.5 -> 4.0 of 6.0 (all four now, one before); `FST_hood_l0, l1, r0, r1` 5.5 of 6.0 |
| A2 (default config) | 5, 17 | 15, 27 | `FST_hinge` 2.0 -> 2.5 of 6.0; `FST_motor_0..3` 3.5 -> 4.0 of 4.5 (1.5 d, tapped BUY_motor); `FST_clamp_l, r` 5.5 of 6.0; `FST_foot_0..7` 5.0 of 6.0 |
| A3 (default config) | 5, 15 | 15, 25 | as A2 without the clamps, plus `FST_nip_cover_0, 1` 5.0 of 6.0 |
| v2 A1-A7 (`min_engagement: 4.0`) | unchanged | unchanged | 17 of v2a7's 103 screws are under 2 d (`FST_hub_*`, `FST_feedmount_*`, `FST_fplate_*`, `FST_leaf_*`, `FST_nipcover_*`, `FST_buck_*`, `FST_nipstop`, `FST_detent_0`); its config keeps them quiet |
| slide-gate clean | 1 warn | 2 | `FST_stop` (M3 x 10) 5.0 of 6.0 |
| demo `--bug` | `FST_proud` 3.0 | 4.0 of 6.0 | the planted proud head; still warns |

`tools/verify_all.sh` assertions changed: A3 `"FST_hinge: only 2.0 mm of thread"` -> `"only 2.5 mm"` (the walk fix),
and slide-gate clean `warns == 1` -> `warns == 2` with the `FST_stop` warn named (the 2 d rule). A1-A3 assert fail
counts only, which did not change.

## Proof (`tools/verify.d/fastener_joint.sh`, 32 checks)

`sh tools/verify_all.sh` on this branch after the review (one detached run, 2026-10-26): **132 passed, 0 failed**, of
which 32 are `fastener_joint.sh`: the 11 below (the M3/M4 cadcheck lines now also require 0 warns) plus 21 review
cases (18 `FJR` lines and 3 cadcheck asserts, section "After review").

The test stack is a 4.7 mm plate on an 11 mm block, plus a 3 mm bracket on a purchased motor with an 8 mm tapped hole.
The same build runs at M3 and at M4. Hole diameters are measured with 360 radial rays in the cut parts: the max for
round holes, and the min (across flats) for the hex trap.

| Joint | M3 length | M4 length | Rule window M3 / M4 (mm) |
|---|---|---|---|
| nut, trap in the block, cap | 16 | 18 | 15.9-18.4 / 16.1-18.4 |
| self-tap, csk | 12 | 14 (`through_ok`) | 10.7-13.1 (blind) / 12.7-18.7 |
| heat-set insert | 12 | 14 (`through_ok`) | 10.4-13.1 (blind) / 12.8-15.8 |
| tapped motor (depth 8), pan | 8 | 10 | 7.5-11.0 / 9.0-11.0 |

| Hole (measured) | M3 | M4 |
|---|---|---|
| clearance (5 holes) | 3.398 | 4.498 |
| self-tap pilot | 2.499 | 3.299 |
| nut trap, across flats | 5.700 | 7.200 |
| insert pocket | 3.998 | 5.597 |

- cadcheck, full run, no config: **0 fails and 0 warns at both sizes**. The M3 bolt (16) passes its nut (13.0-15.4) by
  0.6 mm, and the M4 bolt (18) passes its nut (12.2-15.4) by 2.6 mm. The insert proxy and the tapped purchased part
  raise no findings.
- Refusals (M3): reversed `into`; self-tap into the 4.7 mm plate alone; `length=12` on the nut joint ("stops 1.00 mm
  short of its nut"); `at` 1 mm inside the plate. Trap deepening: a 31 mm stack needs 31.2-33.7 mm, which falls between the
  30 and 35 stock lengths. It uses the M3 x 30 and sinks the trap 1.7 mm deeper, so the bolt still passes the nut by 1.0 mm.
- The first M4 build caught a bug in the joint itself. The insert's tip hole stopped 0.7 mm above the block's bottom face
  (a cadcheck wall warn), which is why the `min_wall` rule above exists.

## Conversions (cadcheck before / after, `next` cadlib vs this branch)

Re-measured after the rebase onto `next` d9cd12d (main's printability task: the demo base and barrel declare
`supports: yes`, the template's floor bosses run to the deck, and the demo and template are checked with
`CAD_LAYER_CHECK=1`). The first run, on the older `next`, gave 8 -> 7 demo warns.

| Build | Before | After |
|---|---|---|
| `examples/demo-turret/build.py` clean (7 joints converted) | 0 fails, 9 warns | **0 fails, 8 warns** |
| demo `--bug` | 4/4 planted bugs caught | 4/4 caught (`FST_side stops 0.40 mm short` is forced with `length=2, strict=False`) |
| template (`P.SCREW`, 4 floor screws) | 0 fails, 1 warn | 0 fails, 1 warn (M3_pan x 6); with `SCREW = "M4"`: 0 fails, 1 warn, M4_pan x 8, Ø3.3 pilots |

The warning that went away was a real defect. The hand-picked M3 x 10 floor screws had their pilot running to 11 mm in
a 12 mm boss, which left a 1.01 mm skin: `PRT_base: 32 wall samples < 1.6 mm`, all at the boss tops (±33, ±33, z 11-12).
The rule picks M3 x 6. The hand-picked M3 x 8 side bolt protruded 3.2 mm past its nut, over the 3.0 limit; the rule
picks 6 (1.2 mm). The arm screws stay at 10, which both the hand pick and the rule chose.

Before the rebase, this branch made `tools/verify_all.sh` pass `CAD_SKILL="$ROOT/skills/print-cad-blender"` to the
template build, because the template imported cadlib from the main checkout. main has since fixed that in `cad build`,
which exports `CAD_SKILL` from its own checkout, so the line was dropped in the rebase. The template's floor bosses
now run to the deck (main), so the self-tap window is 6-33 mm; the rule still picks the shortest stock screw, M3 x 6,
where main's hand-placed screw was M3 x 10.

## Real data (archived blends, read-only copies)

- **A2 (`examples/mm-launcher-a2`)**: `FST_fw_bolt_0` is M3 x 16, and its nut sits at about 16.35-18.75 mm from the
  bearing face (cadcheck measures 18.95-21.35 from the head top, where the inferred head is 2.6 mm tall). The nut rule's
  window is about 19.3-21.8 mm, so the call would have chosen **M3 x 20**. v2 independently ended up at 20.
- **A3 (`examples/mm-launcher-a3`)**: `FST_hinge` (M3 x 30) ends 2.5 mm into `PRT_journal_plate`; cadcheck now reads
  2.5 (2.0 before the walk fix). As a self-tap joint, the call needs 6.0 mm in that part: a longer screw, or "gives only
  ... mm of thread" if the plate is under 6 mm there. v2 fixed it by hand with a nut.
- **v2 A7 (`examples/mm-launcher-v2a7`)**: 103 screws in 18 distinct spec x length (manifest `spec`, `length`), in
  three sizes (M2, M2.5, M3). 17 of them have less than 2 d of thread; v2's config sets `min_engagement: 4.0`, so its
  checks stay as they were. The hand-picked hinge, an M3 x 35 into a nut at 28.8-31.2 mm, protrudes 3.8 mm past its
  nut, over the 3.0 limit; the call would pick M3 x 30 and sink the trap 2.2 mm.

## Call-site cost (`python3 -I tools/prior_art/fastener_joint_callsites.py`)

The script measures the 20 `screw()` calls in v2. The "after" form is each call rewritten mechanically as a
`fastener_joint` call that keeps the same name, at, into, step, joint and head text, wrapped at 120 columns.

| | v2 wrapper + calls | fastener_joint |
|---|---|---|
| wrapper definitions | 14 lines (3 copies) | 0 |
| 20 call sites | 41 lines, 3873 chars | 26 lines, 2158 chars |
| hinge nut (`nh`, `nf`, `nut_trap`, `A.nut`, `launcher.py:455-458`) | 4 lines | 0 (`style="nut"`) |
| **total** | **59 lines** | **26 lines (-56%)**, chars -44% |
| numbers worked out by hand (each length plus every `clamp=`/`sink=`, plus the hinge's nut face and trap depth) | 60 | 0 (`sink=` stays when a counterbore is wanted) |

## Why not the existing code (measured)

Prior art: `features.screw_hole`, `features.nut_trap`, `asm.fastener` and `asm.nut` on `next`, wrapped exactly as v2
wraps them, judged by `next`'s cadcheck. `tools/prior_art/fastener_joint_prior.py` (the test stack) and
`tools/prior_art/fastener_joint_review_prior.py` (the review's cases) run that code, extracted with `git archive next`.
"Configured as well as I can" means v2's own wrapper, with every number worked out by hand.

| Case | Result with the prior art |
|---|---|
| M3, correct hand numbers (16 and 12) | builds; cadcheck 0 fails, 0 warns. The prior art does the job **when a person does the arithmetic**: 6 hand numbers for 2 joints. |
| M4, same call with `"M4_cap"` | `KeyError: 'M4_cap'`, and the holes it cut are still Ø3.40. `screw_hole` has no size; the only way to change a diameter is to edit `RULES`, which changes every screw in the build. |
| M3, nut length 14 by hand | builds; the next cadcheck run fails it: `FST_fj_nut engages only 1.0 of FST_fj_nut_nut's 2.4 mm` (A2-F3). |
| M3 through a board's own Ø3.4 hole, `clamp=1.6` by hand | builds; cadcheck 0 findings, 6.0 mm of thread. The prior art handles pre-drilled parts fine; the first `fastener_joint` did not (review HIGH). |
| M3 cap on a 12 deg slope | builds; cadcheck fails `FST_slope head is inside ['PRT_slope']`. |
| M5 countersink in a 2 mm plate (cut by hand: no M5 in the old API) | builds; cadcheck warns `PRT_csk_plate: 16 wall samples < 1.6 mm (min 0.95)`. |
| 0.5 mm of air between the plate and the block | builds; **no finding**. |
| self-tap into a purchased motor block | builds; **no finding** (the thread host is excluded from "runs into purchased part"). |
| M3 x 10 self-tap into an 8 mm boss under a 3 mm plate | builds; **no finding**, and the pilot (tip + 1 mm) breaks through the boss's far face. |

Honestly: cadcheck already catches most of what the length and seat rules guard against, one check later: a short
bolt, thin thread, a non-stock length, a buried head on a slope, a thin countersunk plate. What `fastener_joint` adds
there is fewer build-check iterations and no hand-worked numbers (60 in v2's 20 calls, section "Call-site cost"), and
an error that says what to change. What neither the prior art nor cadcheck catches is sizes other than M3 (no M4 or M5
holes at all), an air gap in the stack, a self-tap into a purchased part, and a blind boss drilled through. No setting
or wrapper on the old functions provides those. The new code stays small: `fastener_joint` calls `screw_hole`,
`nut_trap`, `asm.fastener` and `asm.nut` and keeps their `at`/`into` convention; the only changes to those four are
`size=` and `tip=` arguments, a `tap` kind, and clearance past an insert.

## Risks and follow-ups

- **The parts must exist uncut when you call it**, except parts whose hole the shank already passes (pre-drilled).
  v2 builds cut lists before the parts (`build_shell(P, g, sh)`); adopting the call means solids, then joints, then one
  csg per part. The demo and the template show that order.
- **The engagement rule changes cadcheck for configs without `min_engagement`** (the template, the demo, A1-A3,
  slide-gate): screws under 2 d now warn. A project that wants the old 4.0 mm sets `fasteners.min_engagement: 4.0`.
- **Reuse makes some screws longer than the shortest fit**, within the same window (thread, protrusion and blind
  limits all still hold). The order of calls decides which length is "already used". Pass `lengths=` to pin it.
- A blind hole is now the default; a design that relied on a through pilot gets "too shallow" and needs
  `through_ok=True` (the M4 test stack does).
- Only the first stretch of each part along the axis counts. A part the screw crosses twice (a U-channel) gets
  clearance along the whole length, but its second wall is not treated as part of the stack.
- The M2, M2.5, M4 and M5 holes are table values and have not been test-printed; print a coupon (pilot, clearance,
  insert, trap per size) before trusting a fit. `insert_d` and `tap_d` especially.
- Hole diameters are still not checked by cadcheck (its `not_checked` says so). The manifest record holds them.

## cadcheck gap found in review (not fixed here): a part overlapping a screw head above the bearing face

Repro (`tools/prior_art/cadcheck_head_overlap_repro.py`, 3 boxes): an M4 cap screw (head Ø7.0 x 4.0) placed by `fastener_joint` through a
4 mm plate into an 11 mm block, and a third printed part, `PRT_rib`, from 3.2 mm off the axis and 0.5 mm above the
bearing face. The rib cuts 0.3 mm into the head's rim over 3.5 mm of its height (about 2 mm3; an undersized
counterbore in a cover plate is the same shape). `cad check` with no config: **0 fails, 0 warns**; the screw row has
`head_buried_in: []`, `standoff_mm: 0.0`, access `straight` at 22 mm, and interference has no finding.

Why, in `skills/print-cad-blender/scripts/cadcheck.py`:
- `pair_class` (line 869): a fastener and a printed or purchased part on the same body return `None`, so
  interference never tests them ("threads bite into the part they hold; fastener check covers heads").
- `survey_screw` (lines 1440, 1450-1451): the head-buried probe is 4 points at 0.8 x head radius plus the axis, all
  0.25 mm behind the bearing face. Material higher up the head, or outside 0.8 x head radius, is never sampled.
- `access` (line 1112): the bit is a ray bundle at `driver_r` (3.0 mm), so anything between 3.0 mm and the head
  radius (3.5 for M4 cap, 3.0-4.75 for pan heads) does not block it either.

Suggested fix (separate PR): sample the head volume itself (rings at 0.5, 0.8 and 0.98 x head radius, every 0.5 mm
from 0.25 mm behind the bearing face to the head top) against same-body parts other than the ones the shank passes,
and fail "head overlaps X"; or give interference a fastener-head-vs-part class that tests only the head.

