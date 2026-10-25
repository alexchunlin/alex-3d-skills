# M&M Launcher Turret v2: BOM and Assembly (attempt 4)

All dimensions in mm. Source of truth: `blender/params.py` (every number) and `blender/parts/*.py` (one module per subsystem).
Printed parts are in `stl/` in print orientation (36 STLs). Tool prints are in `stl/tools/`: the magnet jig and the pocket test
coupon. Evidence: `renders/attempt-4/cadcheck.json` (tools a20a4d7, generated 2026-10-25 07:10, 150 s). Rows added in attempt 4
carry the tag `v2-A3-NN` (the review-3 item they close). Attempt-3 rows keep `v2-A2-NN`, attempt-2 rows `v2-A1-NN`. Each claim
below names the row it comes from:
`[slide: ...]`, `[service: ...]`, `[index: ...]`, `[distances: a-b @pose]`, `[payload: ...]`, `[sightlines: ...]`,
`[fasteners: FST_x]`, `[drop]`, `[stacks: ...]`, `[flexures: ...]`, `[stability]`, `[cables]`, or `[cad q ...]`.
`manifest.json` `parts.<name>.bom_item` names the purchased item behind `FST_nip_stud`, `FST_detent_0`, `CAB_encoder` and
`CAB_bus_pan` (written by `parts/finish.py`).

## Evidence summary (cadcheck.json, quoted)

- **0 fails, 43 warns, 0 untriaged, 0 stale accepts** (`summary.pass: true`). Every warn is in `accepted_warns` with a measured
  reason; section 7 groups them. `assembly.unordered_solids_assumed_present` is `[]` (every solid has an assembly step).
- **What was covered (`coverage`, quoted):**
  - parts: 36 printed objects (36 unique STLs): manifold, bed fit ['P1S', 'H2D'], overhang, wall probe, bed contact.
  - interference/clearance: 175 objects in ['Printed', 'Purchased', 'Fasteners', 'Cables'], 4727 pair-pose tests, joints swept
    ['PIV_feeder', 'PIV_flywheel', 'PIV_hood', 'PIV_jar', 'PIV_nip_lift', 'PIV_pan', 'PIV_tilt'] with 2.5 deg overtravel.
  - fasteners: 103 screws, 4 nuts; head-buried, thread engagement (bolt-to-nut pairing), shanks/nuts inside purchased parts, head
    stand-off, protruding thread, access (Ø6 bit to 14 mm hand clearance, else a 18/56 mm L-key with a 60 deg swing) at 15 poses,
    parts present per assembly_order (29 steps).
  - service: 8 ops, 26 screw accesses with the built assembly present.
  - drop: 4 tests (fall + slide on walls, no bounce or rolling).
  - index: 6 indexer timing tests (probe through the moving parts over the motion sequence).
  - slide: 12 slide-out sweeps.
  - payload: 4 payload-fit probes (rigid probe, no settling).
  - sightlines: 3 first-hit ray rows.
  - assembly: 29 steps, 175 objects placed, 0 in no step.
  - stacks: 3 tolerance stacks (declared terms only).
  - flexures: 2 declared springs or snap arms against print orientation.
  - stability: CG and tip angle over 1728 poses, footprint from static parts' lowest faces.
  - cables: 14 routes, 14 with path length; exposure (>= 8 of 26 rays escape, or 10% of the directions toward a viewer) at home pose.
  - (Not listed in `coverage`, but run: 62 `distances` rows, all passing.)
- **What was not checked (`not_checked`, quoted):**
  - "fasteners: pilot/clearance hole diameters (use cadlib.features for those); wrench access to nuts"
  - "stability: dynamic loads (recoil, pan acceleration), friction/sliding"
  - "cables: bend radius, slack across joints, connector positions (review by section render)"
  - "not geometric: teardown step count, alignment-jig datums (declare stacks), aesthetics, BOM correctness"
- **Stability.** Worst tip 31.2 deg over 1728 poses, at feeder -60, hood -0.558, jar 0, nip_lift -2.19, pan -90, tilt 45 (3937 g,
  CG (16.1, -13.9, 169.8), edge 102.9) [stability]. The supplementary `blender/tools/cg_grid.py` (same mass model, pan 0..315/45 x
  tilt -3/0/22.5/46 x jar 0/30, 64 poses, `renders/attempt-4/cg_grid.txt`) reaches tilt 46 and -3, past the joint range: **worst
  29.9 deg** at jar 0, tilt 46, pan 180 (3937 g, CG (8.7, -21.5, 169.9), edge 97.5). Acceptance (>= 20 deg) holds.
- **Pocket payload fit (v2-A3-A1-03).** Four `payload_fit` rows at the candy size limits (`MM_D` 12.5..13.5, `MM_T` 6.3..7.5) in the
  Ø13.75 pocket:
  - an edge-on MIN pair 12.5 x 6.3 is blocked, 0.253 mm3 overlap, margin 0.06, along x and along y;
  - an edge-on NOMINAL pair 13 x 7 is blocked, 17.553 mm3, margin 0.34;
  - one flat MAX 13.5 x 7.5 fits, margin 0.14 [payload: v2-A3-A1-03].
  - The `tools/lentil_probe.py` lenses agree: pair -0.134 mm3 each (A3 -0.013), flat +0.123
    [cad q dist ZMM_pair_a/b / ZMM_flat PRT_feeder_disc]. Section `sec_pocket_y18.19_lentil_pair_12.5x6.3.png`.
- **Estimated print totals** [parts]: about 1500 g PLA, about 31.6 h, from geometry only; no slicer was run.

## 0. How it works

- **Jar = hopper.** The user's Ball/Kerr regular-mouth pint jar hangs upside down on the pan axis. Its own metal band clamps a printed
  lid disc (`PRT_jar_adapter`). Nothing printed touches the glass or the band:
  - band to crown 14.5 at home and at jar 30 [distances: BUY_jar_band-PRT_feeder_crown];
  - glass to crown 16.6 [distances: BUY_jar-PRT_feeder_crown];
  - glass to the feeder servo cover 7.6 at home and 7.605 at jar 30 [distances: BUY_jar-PRT_feeder_cover].

  The worst-case radial stack from band to housing is 2.4 against a 3.0 design gap [stacks: jar band clears the housing].
- **Feeder index.** A 3-pocket disc (`PRT_feeder_disc`, PIV_feeder) sits under the column. Park is servo 0, where the disc is solid over the outlet.
  - **To fire:** disc +60, then back to 0. **Next shot:** -60, then 0.
  - Each stroke opens exactly one window: +60 opens at 50..60 deg, -60 at -60..-50 deg [index: feeder_fire_plus60_one_candy, feeder_fire_minus60_one_candy].
  - Over the whole 0, +60, 0, -60, 0 sequence the column is never open straight to the outlet, also with the jar drifted 5, 10 or 15 deg
    [index: feeder_column_never_open_to_outlet, v2 column never open, jar drifted 5/10/15 deg].
  - Pockets are Ø13.75 (v2-A3-A1-03, A3 Ø13.9) with a 1 x 45 rim chamfer: 13.75 along x and y at z 267.3 and 269.3, window
    13.65..13.85 [distances: v2-A3-A1-03 pocket diameter]. Two edge-on 12.5 x 6.3 M&Ms cannot sit side by side, and one flat
    13.5 x 7.5 drops through (payload rows above). Ø13.75 is a model value: set it from the printed coupon (section 8).
  - Pocket-over-outlet stack: worst case 0.67 against 1.125 = (16 - 13.75) / 2 [stacks: pocket over outlet at fire: v2-A1-03 / v2-A3-A1-03].
  - The disc is driven by servo #3 through a 30T pinion onto a 44T ring. Disc ±60 = servo ∓88 (`PIV_feeder_pinion` coupled -1.467).
- **Drop path.** The outlet sits at (21, 0), over the tilt axis in the wheel plane. At tilt 0, 15, 22.5, 30, 40, 45 and 46, all 31 of 31 traced
  candies end on `PRT_flywheel`, with 0 stalls [drop: outlet_to_descending_rear_tape]. At both nip stops (gap 6.2 at hood +0.327,
  gap 7.0 at hood -0.558) and tilt -3 / 0 / 22.5 / 45 / 46, 31/31 hit the wheel with 0 stalls [drop: v2-A2-01/A2-05 drop at the
  min-gap stop; v2-A2-01 drop at the thumbwheel max]. The flattest slide is 33.3 deg at tilt 46 (gap 6.2) and 33.5 (gap 7.0), both
  5 or more above the 28 deg stall. The thickest candy (`MM_T` max 7.5) drops 31/31 at both stops and tilt -3 / 0 / 45 / 46,
  flattest 34.2 [drop: v2-A3-A2-01 thick candy (MM_T max 7.5) drop at both hood stops]. The leaf is at rest in these drops: it
  lifts only while a candy is in the nip (`PIV_nip_lift` is `home_only_ok` with that reason); the full-lift case is the gap rows below.
- **Undershot nip** (v1 attempt-3 rig geometry, v2 deltas in params.py).
  - The gap is set by the thumbwheel inside the printed window **`NIP_SET` 6.2..7.0**. The minimum is `HOOD_GAP_MIN` 6.2. At full
    leaf lift the nip must pass the **declared thickest** candy: `NIP_PASS` = `MM_T` max 7.5 + 0.5 tape = **8.0** (v2-A3-A2-01; A3
    used the nominal 7.0 and asserted 7.5). params.py asserts `HOOD_GAP_LIFT` 8.181 >= `NIP_PASS` + 0.1. Two hard stops bound the
    setting:
    - min gap: the hood's front lug lands on `PRT_nip_stop` at hood +0.327; nip ray 6.202 (6.0..6.4)
      [distances: v2-A2-01 nip ray at the printed min-gap stop]; hood to stop 0.000 [distances: v2-A2-01 the hood lug lands on
      PRT_nip_stop].
    - max gap: the thumbwheel bottoms on `PRT_nip_stop_sleeve` at hood -0.558; nip ray 7.007 (6.8..7.2)
      [distances: v2-A1-01 nip ray at the thumbwheel static max]; `cad q dist PRT_nip_stop_sleeve PRT_nip_wheel --pose PIV_hood=-0.558139` = 0.000.
  - **Jam relief: the leaf-solid lift stop (v2-A3-A2-01).** A jam lifts the leaf (`PIV_nip_lift` -2.190..0, A3 -1.493) with the
    thumbwheel riding along. `LEAF_TRAVEL` 1.5 -> 2.2 and `LEAF_T` 2.5 -> 2.3 (`LEAF_PRE` 1.2 kept); the nip cover roof rose 0.5
    (`SHELL_U0` 11.5). The lift ends when the leaf stack goes solid: pad + strip (`LEAF_PAD_H` 2.0 + `LEAF_T` 2.3 = 4.3) between the
    thumbwheel top and the cover roof. Along the stud axis that gap is 6.500 at rest (6.4..6.6) and 4.288 at -2.19 (4.2..4.4)
    [distances: v2-A3-A2-01 hard stop / home].
    - Bare gap at full lift, hood +0.327 / 0 / -0.2 / -0.558: **8.282 / 8.593 / 8.782 / 9.124**, all >= 8.0 [distances: v2-A3-A2-01
      bare gap at FULL leaf lift]. A3 read 7.613 / 7.928 / - / 8.461.
    - **A jam opens the nip to about 9.0** at the gap-7.0 setting: 9.124 by the ray (8.8..9.3) [distances: v2-A3-A2-01 jam claim];
      9.0 is the solved `HOOD_GAP_MAX` 8.991 (A3 "about 8.35", ray 8.461).
    - The thumbwheel keeps 1.143 to the cover at full lift [cad q dist PRT_nip_wheel PRT_nip_cover --pose PIV_nip_lift=-2.18977]
      (A3 1.128).
  - **Leaf numbers** (`launcher_geom.leaf_numbers`, manifest `parts.PRT_nip_leaf.notes`): 21.9 wide x 34.0 long x 2.3 thick, PLA E
    3.5 GPa, rate 5.93 N/mm. Preload 7.1 N (12.5 MPa at the root) at `LEAF_PRE` 1.2; 20.2 N and **35.5 MPa** with the leaf solid
    (2.2 lift) [flexures: nip leaf spring, 2.2 deg to the bed, in the layer plane]. The thickest candy at the min stop needs
    30.4 MPa, a nominal candy 26.9 (A3: 30.7 MPa solid, and the nominal candy cycled within 0.12 of solid). Preload is a rig-feedback
    value (A3 9.1 N).
  - **`NIP_SET` table** (thumbwheel setting -> hood angle -> bare gap at BDC, at full leaf lift, stud tip u; `launcher_geom.report`):

    | Setting | Hood (deg) | Gap at rest | Gap at full lift (ray row) | Stud tip u at rest |
    |---|---|---|---|---|
    | min stop (printed `PRT_nip_stop`) | +0.327 | 6.2 (ray 6.202) | 8.282 | 5.72 |
    | home (model pose) | 0 | 6.5 | 8.593 | 6.05 |
    | - | -0.2 | about 6.7 | 8.782 | - |
    | max stop (stop sleeve) | -0.558 | 7.0 (ray 7.007) | 9.124 | 6.61 |
    | max + full lift (jam) | -2.748 (`HOOD_LO`) | - | 8.991 solved, 9.124 ray | 8.82 (2.70 under the roof) |

  - The hood keeps 0.54 to the body at the min-gap stop and 1 deg past it, and 4.899 to the wheel 1 deg past it
    [distances: hood keeps 0.5 to the body; hood never nears the wheel, at +0.327 / +1.327]. At the static max with the leaf solid
    (hood -0.558, lift -2.19) it keeps 0.54 [distances: v2-A3-A2-01 fix step 3]; at the min stop with the leaf solid 0.542
    [cad q dist PRT_hood PRT_launcher_body --pose PIV_hood=0.327143,PIV_nip_lift=-2.18977]. No bay step was needed.
  - Wheel to guard: 1.594 [distances: PRT_flywheel-PRT_launcher_body].
- **Motor direction:** the bottom of the wheel moves forward (+Y), so the rear of the tape descends into the nip (DESIGN_LOG payload path). This is
  design intent; cadcheck does not simulate it.
- **Tilt** 0..45 with hard stops at -3/+46. The firmware must clamp to 0..45.
  - Spout to the pod drum: 3.01 at -3, 3.0 at 0, 2.99 at 45, 2.71 at 46 [distances: PRT_feeder_housing-PRT_launcher_body].
  - Beam to the pod: 4.88 or more [distances: PRT_beam-PRT_launcher_body].
  - Left post to the encoder cap: 3.75 or more [distances: PRT_post_L-PRT_encoder_cap].

## 1. Purchased parts

| # | Part | Qty | Model object | Mass (g, model) | Notes |
|---|---|---|---|---|---|
| 1 | MotorGo Axis (ESP32-S3 BLDC driver) | 1 | `BUY_motorgo_axis` | 25 | On the rear partition, components toward the partition. **M2.5 screws** (see the fastener table). |
| 2 | XTEAM XTI-3674 1900KV inrunner | 1 | `BUY_motor` | 200 | Nacelle bore, crush ribs. |
| 3 | Plink MT6701 encoder + JST cable | 1 | `BUY_plink_encoder` | 3 | On the encoder cap pegs. |
| 4 | Diametric magnet Ø6 x 2.5 | 1 | `BUY_magnet` | 1 | Glued to the motor rear shaft with `stl/tools/encoder_jig`. |
| 5 | Hiwonder bus servo + round horn | 3 | `BUY_servo_pan/tilt/feeder`, `BUY_horn_*` | 66 + 4 each | Pan in the base, tilt inside the right post, feeder in the crown lobe. |
| 6 | Hiwonder bus servo controller | 1 | `BUY_servo_controller` | 30 | Floor plate. Located by +0.4 fences and drill-to-fit bosses; its holes are unconfirmed, so `FST_ctrl_*` is not modelled. Only its slide switch (y 42..57) and terminal (y 60..73.5) show, through two +X windows in a printed bezel; the wall stays closed over the PCB at y 32/50/68, 0.5 from the board [distances: v2-A1-11 +X wall closed]. |
| 7 | DeWalt 20V battery adapter | 1 | `BUY_dewalt_adapter` | 90 | 4 x M3 x 20 csk self-tap from the deck top, no nuts. |
| 8 | DeWalt 20V battery | 1 | `BUY_battery` | 620 | Slides out +X (section 5). |
| 9 | 12 V buck converter, finned 73.8 x 73.8 x 31 | 1 | `BUY_buck_12v` | 180 | Floor plate, flange holes ±33.4 (estimate, see section 8). |
| 10 | USB-C cable, straight plug | 1 | `BUY_usbc_plug`, `CAB_usb` | 10 | Vertical into the MotorGo, out through the rear niche. |
| 11 | Ball/Kerr regular-mouth pint jar + its metal band | 1 | `BUY_jar`, `BUY_jar_band` | 350 + 15 | The user's own. All `JAR_*` values are nominal; confirm them with calipers. About 400 g of M&Ms (`BUY_mm_fill`). |
| 12 | Hockey tape, 1/2" | about 0.25 m | - | - | Flywheel land. |
| 13 | 16 AWG silicone wire, 3 colours, + braided sleeve | 3 x 700 | `CAB_phase_*`, `CAB_launcher_bundle`, `CAB_launcher_base` | - | Motor leads cut to about 55 and extended in the journal bore (lead 80, path 62.4). Bundle down the left post to the hub: lead 350, path 265.4. Base lead from the hub junction to the MotorGo J6/J8 pads: lead 250, path 164.8 [cables]. The encoder lead (item 15) shares the sleeve, on the far side from the phases. |
| 14 | 3-pin Hiwonder servo bus leads | 3 | `CAB_bus_pan/tilt/feeder` | - | **Pan 350** (v2-A3-A2-02: the next stock length up; 300 left 9.5 spare), tilt 300, feeder 500. Routed 290.5 / 217.9 / 325.5, so 59.5 / 82.1 / 174.5 spare [cables]. |
| 15 | **5-wire JST-SH encoder lead, >= 550, one piece, twisted** (v2-A3-A2-02) | 1 | `CAB_encoder` (+ the encoder conductors in `CAB_launcher_bundle`, `CAB_launcher_base`) | - | From the Plink's JST-SH to the MotorGo encoder JST, unspliced across the tilt and pan joints. Buy it twisted (or shielded) and route it **on the far side of the sleeve from the three phase wires**, tied to the sleeve wall opposite them, through the journal bore, the left post channel and the base. Length budget `ENC_LEAD` 550 = bundle 265.4 + base 164.8 + the Plink-to-journal route + 5 spare; `parts/finish.py` writes the Plink-to-journal share, 114.8, as `CAB_encoder` `lead_len` and asserts it covers that route (84.1, 30.7 spare) [cables: CAB_encoder 84.1 / 114.8]. The A3 150 mm extension ended at the journal bore, so 430 mm of encoder lead was in no row (A2-02). |
| 16 | UART lead, 4-wire | 1 | `CAB_uart` | - | Lead 300, routed 213.8 [cables]. |
| 17 | 12 V leads | 3 | `CAB_12v_in/mg/ctrl` | - | Leads 200 / 100 / 250, routed 119.4 / 45.2 / 168.8 [cables]. |

**Lead lengths and the pan U-loop (v2-A2-02).** Every `A.cable` carries `lead_len` from `params.CABLE_LEADS` (the same table as
checks.json `cable_leads`), and every route is shorter than its lead [cables]. The pan axis gets its slack in a hanging U-loop under
the hub gear, on the static side of each hub junction:
- `CAB_launcher_base`: pan-axis junction (0, 0, 76), a U under the hub gear (legs r 3 / 16, centre z 48), then across the base to
  0.5 over the MotorGo encoder JST and the J6/J8 phase pads. Loop 69.3 against a 17.9 chord: **+51.4** (>= `PAN_LOOP_ADD` 45,
  asserted) [manifest `parts.CAB_launcher_base.loop`]. It reaches the board (0.722 to `BUY_motorgo_axis`, <= 3.0) and meets the
  moving bundle on the pan axis at pan -90 / 0 / +90 (0.008 / 0.028 / 0.008, <= 1.0) [distances: v2-A2-02].
- `CAB_bus_pan` hub end: pocket exit, riser, arch, U (legs r 9 / 3) to the junction: 127.1 against a 67.2 chord, **+59.9**.
- 45 mm covers ±90 pan on an R14 path (π/2 x 14 x 2 = 44). Bend radius and slack across the joint are in `not_checked`; the
  routes are drawn, not simulated.

## 2. Fasteners (from `manifest.json`)

"ST" = self-tapping into a Ø2.5 printed pilot (M3) or a Ø2.1 pilot (M2.5). Clearance holes are Ø3.4 (M3) or Ø2.7 (M2.5).

| Size | Qty | Objects (assembly step) |
|---|---|---|
| M3 x 20 csk ST | 4 | `FST_adapter_*` (1) |
| M2 x 8 pan | 12 | `FST_pinion_*` (1a), `FST_tilt_horn_*` (8a), `FST_fhorn_*` (10a): horn to printed part |
| M3 x 6 cap | 3 | `FST_pinion_ctr` (1b), `FST_tilt_horn_ctr` (8b): servo centre screws. The feeder has none (v2-A1-04). `FST_nipstop` (6c): retains the nip stop pad, up from the skin (the pocket wall takes the load). |
| M3 x 12 cap ST | 9 | `FST_panclamp_*` (1b), `FST_panservo_*` (1c), `FST_hub_*` (2d) |
| **M2.5 x 10 cap ST** | 4 | `FST_mg_*` (2a). Board holes measure Ø2.5 in `REF/mg_axis.stl` (v2 brief); `MG_SCREW` / `MG_HOLE_D` / `MG_PILOT_D` in params. Engagement 8.0 [fasteners: FST_mg_*]. Access was checked with the M3 tool geometry (Ø6 bit, 2.5 mm L-key); the real driver is a 2 mm key. |
| M3 x 10 csk ST | 10 | `FST_partition_*` (2a), `FST_gcap_*` (2c), `FST_leaf_*` (6e) |
| M3 x 8 pan ST | 2 | `FST_buck_*` (2b) |
| M3 x 16 csk ST | 18 | `FST_post_*` (2c), `FST_beam_*` (9), `FST_feedmount_*` (11) |
| M3 x 12 csk ST | 19 | `FST_floor_*` (3), `FST_enc_*` (6b), `FST_jp_*` (6d), `FST_cover_*` (6g), `FST_fcover_*` (10d) |
| M3 x 10 pan | 4 | `FST_motor_*` (6a), into the motor face |
| M3 x 12 pan ST | 2 | `FST_nacelle_*` (6a) |
| **M3 x 16 hex head, ISO 4017 (AF 5.5 x 2.0)** (stud) | 1 | `FST_nip_stud` (6c), `STUD_L` 16 (v2-A3-A3-02: A3 listed x 20, which puts the tip 4 further out at the stud window). Captive head in the hood's AF 5.7 x 3.2 hex pocket, never driven; the three +v flats key it against the thumbwheel's turning torque (`sec_stud_hex_pocket_y4.83.png`). cadlib has no hex-head spec, so the model carries an `M3_cap` x 16 (Ø5.5 x 3.0 head, same bearing face and shank); `manifest parts.FST_nip_stud.bom_item` names the real part. Thread in `FST_tw_nut` 2.4 [fasteners: FST_nip_stud]. |
| M3 x 35 csk | 1 | `FST_hinge` (6d), into `FST_hinge_nut` |
| M3 x 14 cap ST | 6 | `FST_nipcover_*` (6e), `FST_postcover_*` (8) |
| M3 x 20 cap | 2 | `FST_fw_bolt_*` (6f), through `FST_fw_nut_*` |
| M3 hex nut | 4 | `FST_fw_nut_0/1`, `FST_hinge_nut`, `FST_tw_nut` (captive in the thumbwheel) |
| M3 x 8 csk ST | 2 | `FST_fplate_*` (10c) |
| M3 x 10 cap ST | 3 | `FST_valve_*` (12), radial, counterbored flush with the valve OD |
| **M3 x 10 pan self-tap** (stock) | 1 | `FST_detent_0` (12): radial -Y through the gate detent clip's tab into the +Y valve cheek, head sunk 1.0 in a Ø6.6 x 1.0 counterbore (v2-A3-A3-01; A3 was a non-stock x 9 standing proud). Engagement 4.0, straight access 16 [fasteners: FST_detent_0]. Tip 2.652 above the gate blade (>= 2.4) and 1.142 off the adapter spout (>= 0.5) [distances: v2-A3-A3-01]. `sec_detent_cbore_x9.5.png`. |
| (not modelled) | 4 | `FST_ctrl_*`: drill to fit on the bench |

Every modelled screw passes head-buried, engagement (4.0 or more into plastic; `FST_nip_stud` takes the full 2.4 of `FST_tw_nut`), bolt-to-nut, purchased-part and access checks, at its step and at the
service poses [fasteners] (0 fails). One fastener warn remains, accepted (section 7): `FST_hinge` needs a 104 mm bit (bench step 6d;
the bit is in the tool list).

## 3. Printed parts (36, PLA, no supports)

Colour map (v2-A1-12, `params.COLOUR_B`, applied by `parts/finish.py` after every subsystem): **B = terracotta (`pla_b`) for the candy
path and the touch points** (jar adapter, valve, gate, feeder housing/spout, disc, launcher body with chute and muzzle, hood, flywheel,
thumbwheel). **A = warm grey (`pla_a`) for static structure and drivetrain** (base, turntable, posts, beam, crown, covers, nacelle,
journal plate, encoder cap, gears, pinions, stops). Grams and hours are the cadcheck estimates [parts]. Every part fits the P1S (256³) [parts].

| STL | Colour | Infill % | Orientation (from the manifest) | g | h |
|---|---|---|---|---|---|
| base_shell | A | 15 | upside down: deck face on the bed, walls up | 374.5 | 7.09 |
| base_floor | A | 15 | flat, bosses up | 135.4 | 2.63 |
| base_partition | A | 25 | rear face on the bed, standoffs up | 18.5 | 0.45 |
| pan_servo_mount | A | 30 | plate top on the bed, pocket walls up | 29.0 | 0.64 |
| pan_servo_clamp | A | 30 | flat | 4.8 | 0.19 |
| pan_pinion | A | 40 | gear top on the bed, horn recess up | 13.1 | 0.34 |
| thrust_ring | A | 100 | flat | 11.9 | 0.32 |
| turntable | A | 15 | top face on the bed, hub up (groove and cap rebate open to the bed) | 137.1 | 2.66 |
| groove_cap | A | 40 | flat, countersinks up | 12.6 | 0.34 |
| hub_gear | A | 40 | flat, screw heads' face down | 10.6 | 0.30 |
| post_L | A | 25 | upright, foot on the bed (U-bore opens to the top; channel cavity roofs bridge 6 mm) | 54.8 | 1.12 |
| post_R | A | 25 | upright, foot on the bed (servo pocket roof bridges 21 mm, teardrop passage, stop lugs drafted) | 157.1 | 3.03 |
| post_R_cover | A | 25 | flat inner face on the bed, arc face up | 15.5 | 0.39 |
| beam | A | 30 | top face on the bed, tongues up | 60.8 | 1.23 |
| tilt_horn_adapter | A | 60 | horn recess face on the bed, hex key up | 3.4 | 0.16 |
| nacelle | A | 25 | front plate on the bed, journal up (duct roof bridges 15 mm) | 121.5 | 2.37 |
| launcher_body | B | 25 | left (motor) wall outer face on the bed; profile extruded so every wall is vertical | 69.1 | 1.39 |
| journal_plate | A | 30 | inner face on the bed; lap step, journal, socket and stop lug grow up | 10.2 | 0.29 |
| launcher_cover | A | 25 | inner face on the bed; rebated edge steps in toward the top | 25.0 | 0.57 |
| hood | B | 40 | on its side face (profile extruded, all walls vertical; stud pocket has a vertex up) | 10.0 | 0.29 |
| nip_stop | A | 100 | bottom (screw) face on the bed: pilot vertical, contact face a vertical wall | 1.1 | 0.12 |
| nip_stop_sleeve | A | 100 | end on the bed (tube upright) | 0.4 | 0.11 |
| nip_wheel | B | 50 | outer face on the bed, nut trap up (press the nut in) | 1.0 | 0.12 |
| nip_leaf | A | 100 | flat: strip's outer face on the bed, root block and pads up (bending stress in the layer plane); v2-A3-A2-01 `LEAF_T` 2.3, fork half width 4.0 round `FST_tw_nut` | 3.1 | 0.16 |
| nip_cover | A | 30 | screw-block end on the bed; shell and end walls grow up as vertical walls; skirt bridges at the top; finger slot 22 x 8.3 (v2-A3-A2-01, A3 7.5) in the -v end wall over the thumbwheel rim (v2-A1-02); roof 0.5 higher (`SHELL_U0` 11.5) for the 2.2 leaf lift | 7.7 | 0.24 |
| flywheel | B | 100 | motor-side web face on the bed; rim and hub grow up (top flange has a 45 deg underside) | 41.2 | 0.87 |
| encoder_cap | A | 40 | back face on the bed, spigot and pegs up | 8.7 | 0.26 |
| feeder_housing | B | 30 | disc running face on the bed, spout up | 27.0 | 0.60 |
| feeder_crown | A | 25 | top (z 286) on the bed: lip, socket cone, slot ceilings and pocket floors all print as floors | 51.1 | 1.05 |
| feeder_cover | A | 20 | chamfered top on the bed, ears up | 14.7 | 0.37 |
| feeder_pinion | A | 60 | gear face on the bed, horn recess up | 11.5 | 0.32 |
| feeder_disc | B | 40 | gear band on the bed, fins up; 3 pockets Ø13.75 with a 1 x 45 rim chamfer (v2-A3-A1-03) | 17.0 | 0.42 |
| jar_adapter | B | 40 | lid disc (glass side) on the bed, spout up | 8.6 | 0.26 |
| jar_valve | B | 40 | skirt + baffle bottom on the bed (lug undersides bridge 5.5 mm) | 21.2 | 0.50 |
| jar_gate | B | 100 | flat, chamfer, tab and stop lug up; two R1.1 x 0.6 detent notches on the blade top (x 29.5 closed, -22.5 open) | 9.0 | 0.27 |
| gate_detent | A | 100 | flat +Y back face (screw-head face) on the bed: the beam along x and its bending lie in the layer plane (v2-A2-A1-09). v2-A3-A3-01: tab EB 1.0, plate EB 0.4 (0.6 on the 1.2 plate meets in a knife edge), R3 plan end on the plate, Ø6.6 x 1.0 counterbore for the pan head, back face at y 38.5 | 1.5 | 0.13 |

## 4. Assembly (the same steps, in the same order, as `checks.json` `assembly_order`)

cadcheck tests tool access for every screw at the step where it is driven, with only the parts listed up to that step present
[fasteners, 29 steps]. "Bench" steps are sub-assemblies, merged later. Step labels are the checks.json labels (there are no
steps 4 and 5). Every solid is in a step: `assembly.unordered_solids_assumed_present` is `[]` (v2-A2-04: A2 left
`PRT_nip_stop_sleeve`, `FST_valve_*` and `BUY_battery` present from step 1).

- **1** **Base shell upside down.** Put the adapter into its fence. Drive the 4 M3 x 20 self-tappers from the deck top. Tips sit 4.56 above the
    battery face [distances: FST_adapter_0/1-BUY_battery].
  - **1a** **Pan drive on the bench:** screw the horn into the pinion recess (4 x M2 x 8). With the horn hub in the way, cadcheck passes these
    only with the L-key fallback. Use a small Phillips.
  - **1b** **Pan drive on the bench:** servo into the pocket + clamp (2 x M3 x 12). Pinion onto the spline. Centre screw through the pinion.
  - **1c** **Pan drive onto the deck posts** (4 x M3 x 12).
- **2** **Floor plate on the bench.**
  - **2a** Partition (2 x M3 x 10 csk from below). MotorGo on its standoffs (4 x **M2.5 x 10** cap).
  - **2b** Buck (2 x M3 x 8 pan), servo controller (drill to fit).
  - **2c** **Turntable on the bench:** groove cap (6 x M3 x 10 csk). Posts from the turntable underside (7 x M3 x 16 csk).
  - **2d** Thrust ring on the hub. Turntable assembly into the deck hole. Hub gear meshed under the deck and screwed up into the hub
    (3 x M3 x 12). The floor is still off. The gear (R28.5) is wider than the R20.3 deck hole, so it goes on from below.
- **3** **Floor into the shell** (8 x M3 x 12 csk from below). Cables: 12 V, UART, USB-C, pan bus (with its U-loop under the hub
    gear), and the launcher base lead (v2-A2-02): from the hub junction on the pan axis, down through a hanging U-loop under the hub
    gear, then across the base to the MotorGo J6/J8 phase pads and its encoder JST. Leave the loops hanging free: they are the ±90 pan slack.
- **6** **Pod on the bench.**
  - **6a** Motor into the nacelle bore (crush ribs). Body onto the nacelle plate. Motor screws (4 x M3 x 10 pan) and nacelle screws (2 x M3 x 12)
    from inside the guard. Phase leads into the journal bore.
  - **6b** Glue the magnet on the rear shaft with the jig (spigot in the 8 mm access hole). Plink onto the cap pegs. Encoder cap into the bore
    (2 x M3 x 12 csk). Centring stack: worst case 0.30 against a 0.30 limit, with the 7.9 jig spigot and 2.4 Plink pegs (v2-A1-07) [stacks: magnet centring], a pass.
  - **6c** Drop the **M3 x 16 hex head (ISO 4017, AF 5.5 x 2.0)** stud head into the backplate's AF 5.7 hex pocket, flats keyed. It
    is captive and never driven. Press the nip stop pad
    (`PRT_nip_stop`) into its pocket under the muzzle floor, top flush with the floor, and retain it with 1 x M3 x 6 cap up from the skin
    (v2-A1-01).
  - **6d** Backplate into its bay. Journal plate on (3 x M3 x 12 csk). Hinge axle M3 x 35 through the wall, boss and plate into its trapped nut.
    The bit needs 104 mm of reach from -X (warn); do this on the bench.
  - **6e** Stop sleeve over the stud (v2-A1-01), then the thumbwheel onto the stud (set the gap). Leaf screwed under the nip cover from outside (2 x M3 x 10 csk). Cover onto the land
    (2 x M3 x 14 cap).
  - **6f** Flywheel onto the D-shaft. Two M3 x 20 pinch bolts through their nuts, with an L-key from +X.
  - **6g** Wheel-side cover (4 x M3 x 12 csk).
- **7** **Pod into the post U-slots, nose-up about 20 deg.** Hold the pod tilted nose-up about 20 deg and lower it straight down until
    both journals seat in the U-slots, then level it. Reversed, this is the +Z lift-out at tilt 20: it clears with 0.2 to post_L
    [slide_out: v2-A1-06 step 7 reversed].
  - **8a** **Tilt drive on the bench:** horn screwed to the adapter (4 x M2 x 8).
  - **8b** **Tilt drive on the bench:** adapter + horn onto the servo spline. Centre screw through the Ø6.5 key hole.
- **8** **Tilt servo + horn adapter slide in -X through the right post.** The hex key goes into the journal-plate socket. Then the post cover
    (4 x M3 x 14 cap).
- **9** **Beam closes the journal U-slots** (7 x M3 x 16 csk). Launcher bundle into the left post channel.
  - **10a** **Feeder drive on the bench:** horn screwed into the pinion recess (4 x M2 x 8).
  - **10b** **Crown upside down:** pinion + horn in from below. Then servo #3 goes into its pocket from the top, spline pressed into the
    horn. There is no centre screw (v2-A1-04): the 4 x M2 `FST_fhorn_*` hold the horn in the pinion recess, and the lobe cover (10d)
    holds the servo down on its pocket floor.
  - **10c** Disc in from below (the band meshes with the pinion). Floor plate on with 2 x M3 x 8 csk from below.
  - **10d** Feeder upright: bus into the channel, servo cover (2 x M3 x 12 csk).
- **11** **Feeder onto the beam:** 4 x M3 x 16 csk, up through the beam into the crown.
    - The -X pair sits at (-36, ±21) (v2-A1-05), 3.52 from the feeder pinion [distances: FST_feedmount_0/1-PRT_feeder_pinion].
      (-36, -21) takes a straight bit (58 mm reach). (-36, +21) takes the 2.5 mm L-key: the nacelle blocks a straight bit at 23.9, and
      the L-key arc is 180 deg. The (34, ±20) pair takes the L-key (journal plate at about 21 mm, arc 150-170 deg). Drive at tilt 0
      [fasteners: FST_feedmount_0..3].
- **12** **Jar on the bench:** adapter in the band. Lay the gate on the valve's gate floor, closed, with its stop lug up at the -X end.
    Then put the valve on the spout (3 x M3 x 10 cap, radial). The spout tip closes over the lug, so the gate is captive from here on
    (v2-A1-09). **Gate detent clip** (v2-A2-A1-09): hold `PRT_gate_detent`'s tab on the +Y cheek's outside face, with the gate closed,
    so its R1 bump drops into the blade's closed notch (x 29.5), and drive 1 x **M3 x 10 pan self-tap** radially (-Y) into the cheek,
    head down into the tab's Ø6.6 x 1.0 counterbore (v2-A3-A3-01) [fasteners: FST_detent_0, engagement 4.0, straight access 16];
    the tip ends 2.652 above the blade and 1.142 off the spout [distances: v2-A3-A3-01]. Seated bump to blade 0.10 (<= 0.15) [distances: v2-A2-A1-09 detent
    clip bump seated]. The clip's 1.2 x 12.5 plate lifts 0.4 to ride the blade between the notches: 16.1 MPa, beam in the layer plane
    [flexures: gate detent clip, 0.0 deg to the bed].
- **13** **Jar onto the feeder:** drop it in at +30 and twist to 0. The twist is swept in the interference check (PIV_jar 0..30, no fails).
- **14** **Battery** slides onto the adapter rail, +X to -X, last (checks.json step 14, v2-A2-04). Reversed, it slides out +X 120 past
    every fastener with 1.60 to the floor [slide: battery out +X].

## 5. Service (each row is a cadcheck `service` or `slide_out` result)

| Task | How | Evidence |
|---|---|---|
| Set the nip gap | **Cover on.** Roll the thumbwheel with a fingertip through the 22 x 8.3 slot in the nip cover's -v end wall. The slot top sits 0.3 over the rim, and an R8.5 finger scallop (v2-A2-03) is cut from the guard shelf beside it, so an R8 fingertip resting on the rim crest clears the shelf. Travel is bounded by the two printed stops: **gap 6.2..7.0** (`NIP_SET`). | [distances: v2-A2-03 thumbwheel rim crest on the finger approach line] 24.511 (24.0..25.0); [distances: v2-A2-03 R8 fingertip clears the guard shelf at u -4.5 / -6 / -8] 25.578 / 25.032 / 23.634 (>= 24.9 / 24.4 / 22.7); [cad q ray 19.5,-2.33,111.274 0,-0.316,0.949 -> PRT_nip_wheel at 14.4 (tilt 0)]; [cad q ray 19.5,77.315,143.401 0,-0.895,0.445 --pose PIV_tilt=45 -> PRT_nip_wheel at 14.4]; [sightlines: v2-A3-A2-03 fingertip line reaches the thumbwheel rim first] 3/3 rays hit `PRT_nip_wheel` first at home (13.75 / 14.4 / 13.75), at tilt 45 (same) and at full lift nip_lift -2.19 (15.48 x 3); the rim keeps 1.143 to the cover at full lift [cad q dist]; `renders/attempt-3/sec_x19p5_finger_scallop.png` |
| Nip leaf | Tilt to 45. Remove the nip cover (2 x M3 x 14 cap) and the leaf (2 x M3 x 10 csk), straight bit. | [service: v2-A1-02 replace the nip leaf] reach 18 / 14, straight |
| Tape / flywheel | Tilt to 45. Remove the pod cover (4 screws, straight bit). Loosen the pinch bolts with the L-key (arc 80 / 100 deg). The wheel slides off +X. | [service: pod cover off], [service: re-tighten the flywheel pinch bolts], [slide: flywheel off +X at tilt 45] 140 mm, min 1.59 |
| Encoder | Tilt to 45. Remove 2 screws. The cap comes off -X. | [service: encoder cap off], [slide: encoder cap off -X] not blocked (0.00 is the seat it slides off, row min 0.0) |
| Nip cover + leaf removal path | The cover and leaf drop out downward at tilt 45. | [slide: nip cover + leaf off] not blocked (0.00 is the seat, row min 0.0) |
| Tilt servo | Remove the right post cover (4 screws). The servo, horn and adapter slide out +X 60 mm. The pod stays in. | [service: tilt servo swap] reach 18, straight; [slide: tilt servo out +X] not blocked, min 0.10 (accepted warn: at rest, the tips of the four M2 x 8 horn screws 0.10 from the journal plate's counterbore floor, same body; then the 12 AF key leaves its 12.3 AF socket at 0.15 per flat for 6.5 mm) |
| Feeder servo | Remove the lobe cover (2 screws, reach 44). The servo lifts +Z off the horn spline; the horn and pinion stay in the crown. No other screw is involved (v2-A1-04: A1's centre screw was only reachable with the feeder off the beam). | [service: v2-A1-04 feeder servo swap: lobe cover off] reach 44, straight; [slide: v2-A1-04 feeder servo lifts +Z] 60 mm, not blocked (0.00 is the pocket floor it rests on); the `FST_fhorn_ctr` service row matches nothing |
| Base floor | 8 screws from below. The floor plate drops -Z with the partition, MotorGo, buck and servo controller on it (and their screws); unplug the leads as it comes down. | [service: base floor off]; [slide: v2-A3-A3-03 base floor plate with its electronics drops -Z after the 8 floor screws] 40 mm, not blocked (`blocked_at_mm` null; 0.00 is the seat, closest `PRT_base_shell`) |
| Refill | Push the gate closed with the R6 tab (the model's home pose). The tab is flush with the valve OD when closed. Twist the jar to 30 and lift it. Flip it, unscrew the band. To open, pull the tab +X until the lug meets the spout shoulder at +52.35 (the positive stop). The detent clip (v2-A2-A1-09) clicks into a notch at both ends, so the gate holds closed and open (the open notch is GATE_TRAVEL 52 along the same blade; there is no prismatic joint type, so only the closed notch has a posed row, see section 8). | [slide: v2-A1-09/A2 gate opens +X 52] min 0.35 to PRT_jar_adapter, valve present, clip present; [distances: v2-A2-A1-09 detent clip bump seated] 0.10; [flexures: gate detent clip] 16.1 MPa, 0.0 deg; [distances: FST_detent_0-PRT_jar_gate] 2.652 (>= 2.4); [slide: jar group lifts off when unlocked] not blocked (0.00 is the seat) |
| Battery | Last on (step 14). Slides out +X 120 mm past every fastener. | [slide: battery out +X] min 1.60 |

The pod cover, encoder cap, nip cover, jar group, feeder servo, lobe cover and base floor rows read 0.00: the resting contact at the start of each
move. Their rows now carry `min_clearance` 0.0 with that reason in the name, so they are not warns. None of the 12 slides is
blocked (`blocked_at_mm: null`).

## 6. Renders and sections (`renders/attempt-4/`)

- Final view set, 1800 x 1350 (`CAD_RENDER_FINAL=1`): `iso`, `iso_front_left`, `front`, `side`, `top`, `rear`, `pan-90_tilt0`,
  `pan+90_tilt45`, `tilt45`, `jar_unlocked`, `exploded`. `BUY_jar` is a transmissive glass material (RGBA alpha 0.25,
  `params.JAR_GLASS_RGBA`, set in `parts/finish.py`), so the M&M fill shows through (v2-A1-11).
- `stl_sheet.png`: all 36 STLs in print orientation, with the P1S bed (256 x 256) for scale (`cad sheet stl ...`).
- `cg_grid.txt`: the 64-pose tip-angle grid (worst 29.9 deg).
- Sections (960 px):
  - `sec_nip_x21_hood+0.327_lift-2.19.png`: the nip in the plane of the gap ray (x 21) at the min-gap stop with the leaf solid:
    hood, flywheel, nip stack (thumbwheel, leaf, nip cover). Ray 8.282 at this pose [distances: v2-A3-A2-01 bare gap at FULL leaf
    lift, hood +0.327].
  - `sec_pocket_y18.19_lentil_pair_12.5x6.3.png`: the parked +60 pocket cut through its centre (y 18.187) with the probe's edge-on
    12.5 x 6.3 pair (`tools/lentil_probe.py`, the lenses moved into Purchased so they draw): the pair fills the Ø13.75 pocket and
    rides on the rim chamfer [cad q dist ZMM_pair_a PRT_feeder_disc: -0.134 mm3].
  - `sec_detent_cbore_x9.5.png`: `FST_detent_0` on its axis: pan head 1.0 down in the tab's Ø6.6 counterbore, shank through the tab
    into the +Y valve cheek, tip above the gate blade.
  - `sec_stud_hex_pocket_y4.83.png`: across the stud head, 1.5 behind its bearing face: the hood's AF 5.7 hex pocket (three +v
    flats; the -v half runs out as a U-slot through the 26 deg back face), the stop sleeve, and the modelled Ø5.5 cap head that stands
    in for the ISO 4017 AF 5.5 hex.
  - Launcher step: `launcher_tongue_hood_lo_x22.png` (the chute tongue stays shingled inside the backplate at `HOOD_LO` -2.748).
  - Still current from attempt 3: `renders/attempt-3/sec_x19p5_finger_scallop.png` (finger slot and scallop).

## 7. Warns (43, all triaged in `checks.json` `accepted_warns`)

Each accept is a substring of the warn plus a measured reason; a fixed warn would show up as a stale accept (there are none).
- **Thin walls under 1.6 (A1-08), 13.** Each sample is located (cadcheck `where`) and explained:
  - gear tooth tips 1.54 (pan_pinion, hub_gear, feeder_disc, feeder_pinion): involute tips, not walls.
  - jar_valve 1.29: the roof between the three `FST_valve_*` cap-head counterbores (z 295.5) and the cheek tops (z 300).
  - journal_plate 1.29: the floor of the `FST_hinge_nut` trap (x 31.5..32.8), solid bottom layers loaded in compression.
  - gate_detent 1.19: all 55 samples on the 1.2 plate, the designed detent beam [flexures]; the tab reads none (its counterbore
    keeps 2.7 / 2.8 / 3.7 to the tab edges). jar_gate 1.40: blade under the two detent notches.
  - feeder_cover 1.40: the roof over the servo idler-boss recess, printed first on the bed.
  - nip_cover 1.48: the 45 deg slot-end chamfer and one counterbore edge.
  - nip_wheel 1.50: the thumbwheel's outer face over the captive-nut trap. nip_leaf 1.49: between `FST_leaf_1`'s pilot (now run
    through the root block) and the leaf's +X end.
- **Bridges over 25, 3.** flywheel 72: the declared 1 mm flange ring. nacelle 39: the phase-lead duct roof, widest inscribed circle
  15.0 (the real bridge). feeder_crown 26: the three bayonet L-slot leg floors, each 5.1 wide (26.4 is one arc's bounding box).
- **Overhang, 1.** beam 205 mm2: loft-seam facets at the four R6 plan corners where the top chamfer ends.
- **Overtravel, 16 (10 collide, 2 touch, 4 clearance).** All are at hood -3.06 or +2.83, nip_lift -4.69 or +2.5, or tilt 47.5: 2.5
  deg past a limit that is itself a printed stop (min-gap pad, stop sleeve, leaf solid, thumbwheel seat, tilt lugs at +46). Each
  accept quotes the in-range value: hood to body 0.54 at both stops (also with the leaf solid), sleeve to body 0.584-0.595, wheel to
  cover 1.143 at full lift, sleeve to leaf 1.782 at hood -0.558 + lift -2.19, hood to `FST_nipstop` 2.0, tilt lugs 0.000 at +46.
  The A3 leaf fork x `FST_tw_nut` 0.35 at full lift is now 1.289 (fork half width 4.0); only the -4.69 overtravel pose warns.
- **Distances ray vs nearest, 9 (new tool rule, a20a4d7).** Rows that are rays on purpose: the leaf-solid hard-stop and home rows
  along the stud axis (2), the four pocket-diameter rays across one part (a = b, nearest 0.00), and the three fingertip-vs-shelf rows
  along the finger line (3).
- **Fasteners, 1.** `FST_hinge` needs a 104 mm bit (bench step 6d).
- **Slide, 1.** Tilt servo 0.10: the horn-screw tips at rest, same body (section 5).
- **Drop.** None.

## 8. Not done / to confirm

- **Resolved in attempt 4** (each with its row):
  - v2-A3-A2-01 (major): full-lift gap >= `MM_T` max + tape = 8.0 at all four hood settings (8.282..9.124), jam 9.124 (8.8..9.3),
    leaf-solid hard stop 4.288 / home 6.500, hood to body 0.54 with the leaf solid, leaf 35.5 MPa in plane, thick-candy drops 31/31.
  - v2-A3-A1-03: pocket Ø13.75, `payload_fit` margins 0.06 / 0.06 (MIN pair blocked), 0.34 (nominal pair blocked), 0.14 (flat MAX
    fits); plus the test coupon below.
  - v2-A3-A2-02: one 550 encoder lead with a lead budget row, pan bus lead 350.
  - v2-A3-A3-01: detent clip edge breaks and R3 end, counterbored stock M3 x 10.
  - v2-A3-A3-02: the stud is M3 x 16 hex head ISO 4017 in the fastener table and step 6c.
  - v2-A3-A3-03: the base-floor `slide_out` row (not blocked), the full-lift row at 8.0; the detent open notch stays a probe (below).
- **Calipering and the pocket coupon (do this before printing the feeder disc).**
  1. Caliper 20 M&Ms: diameter across the flat face and thickness at the centre. Write the min and max into `params.py` `MM_D` and
     `MM_T` (now 12.5..13.5 and 6.3..7.5, nominal).
  2. Print `stl/tools/test_pocket_coupon.stl` like the feeder disc (same PLA, same slicer profile, flat, chamfered face up). It is
     an 8 mm disc, OD 51.1, with four through pockets Ø13.6 / 13.75 / 13.9 / 14.1 (smallest first; pocket k has k + 1 rim notches),
     each with the disc's 1 x 45 rim chamfer. Re-export with `cd blender && cad py tools/pocket_coupon.py` (writes `stl/tools/`).
  3. For each pocket: one flat candy of the largest diameter must drop through; two of the thinnest candies stood edge-on side by
     side must not both enter (push gently; they ride on the rim).
  4. Set `POCKET_D` to the smallest pocket that passes the flat candy and still blocks the pair, rebuild and `cad check`: the 4
     `payload_fit` rows and the 4 pocket-diameter ray rows follow `POCKET_D` (the ray rows' 13.65..13.85 window must move with it).
  5. If `MM_T` max changes, `NIP_PASS` and the full-lift rows follow (params asserts `HOOD_GAP_LIFT` >= `NIP_PASS` + 0.1).
- **Detent open notch (A3-03 part).** cadlib has no prismatic joint, so the gate's +52 pose cannot be a posed `distances` row. The
  closed notch has one (0.10); the open notch is the review's moved-gate probe (0.10 at +52) plus the flexures row.
- **Hex-head stud fit (A3-02 part).** cadlib has no hex-head fastener spec, so the AF 5.5 x 2.0 head in the AF 5.7 pocket is shown by
  section, not measured; the model's Ø5.5 x 3.0 cap head stands in (same bearing face).
- **`PRT_nip_cover` orient text** in the manifest still reads "finger slot 22 x 7.5" (a string in `parts/launcher.py`); the geometry
  and this BOM use `FINGER_SLOT` 22 x 8.3.
- **Nip window width.** The static window stays 6.2..7.0; the rig's 5..12 range waits for rig numbers (drops stall from 7.4 in this
  geometry; the leaf opens the nip dynamically 6.2..9.0).
- **Not modelled:** `FST_ctrl_*` (drill to fit); the bayonet detent nub (the L-slots have hard ends with 3 deg of margin); the
  optional open-gate interlock; the encoder lead's position inside the sleeve (cables are drawn as one route each).
- **Deferred (tool limit):** `post_R x journal_plate` `contact_normal` (the 0.156 journal row stays).
- **Confirm with calipers:** all `JAR_*`; `MM_D` / `MM_T` (above); the MotorGo hole size (`MG_*`: M2.5 now, components.json
  says Ø3.4) and its J6/J8 pad position (`MG_PHASE_PAD_STEP`, not in components.json); adapter corner holes (6 inset);
  `BATT_STEM_INSET`; buck flange holes ±33.4; the servo controller's switch and terminal positions (`CTRL_SW`, `CTRL_TB`).
- **Deviations from the plan:**
  - The baffle ramps are 45 deg from horizontal, not 30. 30 gave 325 mm² of supported overhang on the valve.
  - The baffle sits on the valve, so it covers the outlet only when the bayonet is locked at 0.
  - Detent plate edge break 0.4, not the review's 0.6 (0.6 on the 1.2 plate meets in a knife edge).
- **Launch rig feedback still to come:** `NIP_SET` 6.2..7.0, `G_IN`, `LEAF_*` (preload 7.1 N), `STUD_L` 16, tape thickness.
