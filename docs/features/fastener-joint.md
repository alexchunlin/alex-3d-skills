# features.fastener_joint: one call per fastened joint

Branch `feat/fastener-joint`, 2026-10-25. Code: `skills/print-cad-blender/scripts/cadlib/features.py`
(`SIZES`, `size_rules`, `axis_stack`, `fastener_joint`), `asm.py` (`FASTENER_SPECS` for every size, `nut(size=)`).
Test: `tools/verify.d/fastener_joint.sh`, which builds `tools/verify.d/fastener_joint_build.py`.

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
| FINDINGS A3-F5 (an A2 candidate first) | The hinge screw had 2.0-2.5 mm of thread in PLA. | A self-tap into less than `min_engagement` (2 d) raises `... gives only 4.7 mm of thread on this axis; M3 selftap needs 6.0. Add a boss, use style='nut' or 'insert'`. |
| FINDINGS A1-F10 | Screws were modelled reversed. | If no part lies ahead of `at` along `into`, it raises `... the parts are behind the head: flip into`. A head inside the first part raises `the head would sit 1.00 mm inside ...`. |
| FINDINGS A3-T2 | D3 spent 289 s at `0:13:55` working out which way a stud head faces. | `into` is checked against the geometry, so a wrong guess fails in the same build. |

## What it does

1. **Size table.** `SIZES` covers M2, M2.5, M3, M4 and M5: pitch, clearance, self-tap pilot, PLA-tap hole, cap/pan/csk
   head d and h, nut AF and h, trap AF, insert hole and length, `min_engagement` (2 d) and `tapped_engagement` (1.5 d).
   The stock lengths come from cadcheck's default `fasteners.stock_lengths` (read like `max_protrusion`, below), so the
   joint never picks a length cadcheck's stock-length check warns about. The M3 row reads the `m3_*` entries of `RULES` at lookup, so tuning `RULES` still works and every
   existing M3 hole keeps its diameter. Changing the size is one argument: the template now has `P.SCREW = "M3"`.
2. **Stack.** `axis_stack` ray-casts each given part along `at`/`into`, using a BVH of the world-space mesh and a line
   offset 0.01 mm so it never runs down an edge. For each part it keeps the first stretch of material ahead of `at`.
   Parts are sorted by where they start: every part but the last is clamped, and the last one holds the thread or the nut.
3. **Styles.**
   - `selftap`: pilot in the last part.
   - `nut`: clearance through every part, plus a hex trap at the far face of the last part (`trap=False` puts the nut on that face).
   - `insert`: heat-set pocket, plus clearance past it for a longer screw.
   - `tapped`: nothing is cut in a purchased last part. A printed last part gets the PLA-tap hole.

   `sink=` cuts a counterbore and `head="csk"` cuts a countersink. Teardrops come from `print_up`, given either as a
   vector or as `{part: vector}`.
4. **Length.** It picks the shortest stock length in the window:
   - `selftap` / `tapped`: thread ≥ `min_engagement` (2 d) or `tapped_engagement` (1.5 d). A tapped part is capped by `depth=` (the datasheet depth of its hole).
   - `nut`: the bolt passes the nut by at least one pitch.
   - `insert`: the screw runs through the whole insert.

   In every case the tip stays within `fasteners.max_protrusion` of the last material. That value is read from
   `cadcheck.py` DEFAULTS with `ast`, so the joint and the check share one number. If no stock length fits with a nut
   trap at the face, the trap is sunk deeper by the least amount that makes one fit. If nothing fits at all, it raises
   with the window and the stock list. A blind hole that would leave less than `min_wall` under the tip stops at
   `min_wall`, or goes through.
5. **Placement.** `asm.fastener` places the screw with the same `at`/`into`, and `asm.nut` places the nut. An insert is
   placed as a nut-tagged proxy, so cadcheck checks that the screw runs through it. The record goes to the manifest as
   `parts[FST].fastener_joint`: size, style, stack, grip, length, engagement, protrusion, window, rule and hole
   diameters. It also goes to `features` as `"feature": "fastener_joint"`.
6. **Return.** `{part name: [cutters]}`. Like every other feature, it returns cutters for `geom.csg(sub=...)`; it never
   applies them. Pass `cuts=` to collect several joints, then run one csg per part.

## Proof (`tools/verify.d/fastener_joint.sh`, 11 checks)

`sh tools/verify_all.sh` on this branch: **47 passed, 0 failed**. That is the 36 existing checks plus these 11.

The test stack is a 4.7 mm plate on an 11 mm block, plus a 3 mm bracket on a purchased motor with an 8 mm tapped hole.
The same build runs at M3 and at M4. Hole diameters are measured with 360 radial rays in the cut parts: the max for
round holes, and the min (across flats) for the hex trap.

| Joint | M3 length | M4 length | Rule window M3 / M4 (mm) |
|---|---|---|---|
| nut, trap in the block, cap | 16 | 18 | 15.9-18.4 / 16.1-18.4 |
| self-tap, csk | 12 | 14 | 10.7-18.7 / 12.7-18.7 |
| heat-set insert | 12 | 14 | 10.4-18.7 / 12.8-18.7 |
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
- **A3 (`examples/mm-launcher-a3`)**: `FST_hinge` (M3 x 30) ends 2.5 mm into `PRT_journal_plate`, and cadcheck counts
  2.0 mm of thread. As a self-tap joint, the call needs 6.0 mm in that part. It would pick a longer screw, or raise
  "gives only ... mm of thread" if the plate is under 6 mm thick on that axis; I did not measure the plate's thickness
  there. v2 fixed it by hand with a nut.
- **v2 now (`HW/v2/blender/cadcheck.json`)**: the hand-picked hinge, an M3 x 35 into a nut at 28.8-31.2 mm, protrudes
  3.8 mm past its nut, over the 3.0 limit. The window is 31.7-34.2 mm, and no stock M3 length falls in it, so the call
  would pick M3 x 30 and sink the trap 2.2 mm. 30 of v2's 86 screw rows have 4.0-5.5 mm of self-tap or tapped thread:
  enough for cadcheck's 4.0 warn threshold, but below this table's 2 d / 1.5 d.

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
wraps them. `tools/prior_art/fastener_joint_prior.py` ran that code on the same test stack, extracted with
`git archive next`. "Configured as well as I can" means v2's own wrapper, with every number worked out by hand.

| Case | Result with the prior art |
|---|---|
| M3, correct hand numbers (16 and 12) | builds; cadcheck 0 fails, 0 warns. The prior art does the job **when a person does the arithmetic**: 6 hand numbers for 2 joints. |
| M4, same call with `"M4_cap"` | `KeyError: 'M4_cap'`, and the holes it cut are still Ø3.40. `screw_hole` has no size, and the only way to change a diameter is to edit `RULES`, which changes every screw in the build. |
| M3, nut length 14 by hand | builds silently; only a later cadcheck run fails it: `FST_fj_nut engages only 1.0 of FST_fj_nut_nut's 2.4 mm`. That is A2-F3, which went to review. |

The gap is sizes other than M3, and lengths and grips that come from the geometry instead of a person. No setting or
wrapper on the old functions provides either. The new code stays small: `fastener_joint` calls `screw_hole`, `nut_trap`,
`asm.fastener` and `asm.nut` and keeps their `at`/`into` convention. The only changes to those four are `size=` and `tip=`
arguments, a `tap` kind, and clearance past an insert.

## Risks and follow-ups

- **The parts must exist uncut when you call it.** The stack is measured, so v2's pattern breaks: v2 builds cut lists
  before the parts (`build_shell(P, g, sh)`). Adopting the call means building the solids, then the joints, then one csg
  per part. The demo and the template show that order.
- Stock lengths come from cadcheck's DEFAULTS. A project that overrides `fasteners.stock_lengths` in its
  `checks.json` is not seen by the joint, which can then pick a length the project's check warns about.
- The 2 d self-tap rule is stricter than cadcheck's 4.0 mm warn. Of the 30 v2 screws under it, each would get a longer
  screw or a `FastenerError` unless `min_engagement=` is passed. That may be correct, but it is a behaviour change for
  anyone porting v2.
- Only the first stretch of each part along the axis counts. A part the screw crosses twice (a U-channel) gets clearance
  along the whole length, but its second wall is not treated as part of the stack.
- The M4/M5/M2.5/M2 numbers are table values and have not been test-printed. `insert_d` and `tap_d` in particular
  should be checked on a print.
- Hole diameters are still not checked by cadcheck (its `not_checked` says so). The manifest record now holds them.
