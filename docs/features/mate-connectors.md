# Mate connectors (`cadlib.mates`, `cad mates`)

Branch `feat/mate-connectors`, 2026-10-27. Task: `docs/tasks/2026-10-27-mate-connectors.md`.
Code: `skills/print-cad-blender/scripts/cadlib/mates.py`, `asm.py` (registries, manifest `mates` and per-part
`connectors`), `scripts/cadmates.py` and `cad mates`, `cadrows.py` (mate lines in `cad rows manifest.json`).
Template: `templates/project/` places its parts only through `mates.assemble`. Purchased-part connectors:
`components/components.json`. Tests: `tools/verify.d/mates.sh`. Eval kit: `tools/bench/mates_task/`.

## Why
Designers compute every part's world placement by hand, and the spatial errors come from there: in the CADGenBench
pilot, agents got cross products, winding, mirrored views and a 180 deg view wrong; in the mm-launcher and push-assist
loops the reviewers' majors are mostly placement and access. The interface is data the designer already has (this
bolt pattern goes on that one; this spline is that arm's pivot). Stored once, code places the parts and cuts the
features, and the mate table is a grep-able record of every interface. Adoption is the risk (push-assist never called
`fastener_joint`, `route` or `blend` although SKILL.md named them), so the template places parts *through* mates.

## What it does
- **Connector**: `connector(ob, name, origin, z, x=None, pattern=None, hole=None)`, a named frame on a part in the
  frame it was modelled in, stored on the object (`mate_connectors`, plus `mate_frame` once placed), so it moves with
  the part (`frame_of`, `world_points`). `z` points out of the part from the mating face. Patterns in minimal form:
  `rect(px, py)`, `circle(pcd, n, a0)`, `line(pitch, n)`, `points([...])`. Default `x`: the frame's +X flattened into
  the face, +Z when z is along X, so two parts modelled in the same orientation mate without turning.
  `from_component(ob, entry)` reads a `components.json` entry's `connectors`.
- **Mate**: `mate(a, b, kind, gap, rot, fit, lo, hi, home, fastener, step, note)`, face to face (origins together, z
  opposed, x together), kinds `rigid | fastened | revolute | prismatic`, fits `press | slip | clearance | snap`.
  `fasten(conn, ...)` is a fastened "mate" to nothing (floor screws, a bolt through a wall).
- **Assemble**: `assemble(ground)` walks the mates breadth-first from the ground, composes matrices, bakes each
  placement into the mesh (cadlib's world-at-home convention), makes `asm.joint(PIV_...)` for each revolute or
  prismatic mate (axis sign folded into lo/hi/home and coupling ratios), checks every pair of patterns, runs
  `features.fastener_joint` once per pattern point (head on `head_on`'s far face, measured by a ray through that part,
  or on a ring when the axis is a pre-drilled hole), cuts, converts each part's `print_rot` from its own frame to
  world, and calls `asm.part`. Raises `MateError` on a loop, an unreached part, a pattern mismatch (count, position,
  hole size; both specs printed, plus a mirror hint when one side was typed as seen from the other face), a
  revolute/prismatic axis that isn't a world axis, or a part that has an object transform.
- **Mate table**: scene `cad_mates` in the .blend and `mates` in the manifest; `cad mates <manifest|blend> [REGEX]
  [--connectors]` prints one line per mate:

```
PIV_pan   revolute   PRT_base:deck > PRT_pan:bottom  axis +Z at (0,0,30)  -90..90 deg  home 0  gap 0.5  fit clearance
arm_L     fastened   PRT_pan:arm_L > PRT_arm_L:foot  at (-17.5,0,35.5) z (0,0,1)  hole M3  1x M3 selftap pan sink 2.8 head on a: FST_arm_0 L10  step arms
pcb       fastened   PRT_deck:pcb > BUY_pcb:mount  at (35,0,12) z (0,0,1)  pattern rect(42, 32)  hole M2.5  4x M2.5 selftap pan head on b: FST_pcb_0..3 L8  fit clearance  step board
```

## Why not the existing code (measured)

| Prior art | What it can do | Measured | Why it isn't enough |
|---|---|---|---|
| `asm.joint`, `asm.part` (in repo) | a PIV joint at a world point about X/Y/Z with limits; registers a part already in world coordinates | the demo's `build.py` builds each part where it sits: 25 of its lines use the placement parameters `TILT_Z`, `BASE_H`, `z0`, `z_bear` or `ARM_GAP`; `build_mates.py` uses them on 12 | No frame on a part, no record of what meets what: the placement lives in the designer's arithmetic. Kept as is: `assemble` calls both, so every sweep, held-pose and insertion check works unchanged. |
| `features.fastener_joint` (in repo) | measures a stack along a world `at`/`into`, picks the length, cuts, places the screw | `tools/prior_art/mates_pattern_prior.py`: deck posts at `rect(42, 32 + d)` under a board pre-drilled at `rect(42, 32)`. d = 0, 0.25, 0.5, 1.0 mm (each screw d/2 off its hole): 0 of 4 raise, and `cad check` on each blend gives **0 fails, 0 warns**. d = 2.0: all 4 raise, with "the screw would thread into it" | It sees geometry, not intent: a hole pitch typed 1 mm long ships. `mates` checks the two patterns against each other (0.01 mm) before any cut; the same 0.25 mm per hole fails with both specs (`mates_cases.py` pitch case, demo `--bug-pattern`). Kept: `assemble` calls it once per pattern point. |
| `cadlib.joints` (in repo) | reads and poses PIV joints for cadcheck and the router | n/a | Posing, not placing. Reused by the eval scorer. |
| build123d joints (`RigidJoint`, `RevoluteJoint`, `LinearJoint`, `CylindricalJoint`, `BallJoint`, `connect_to`) | named joints on parts; `connect_to` relocates the other part; revolute angle validated against its range | `tools/prior_art/mates_build123d_prior.py` (CADGenBench venv, build123d 0.10.0): its rigid connect makes the two frames **coincide** (same z). With z out of each mating face, as a designer describes a face, the lid lands at z 1..5, inside the deck (top at 5); it needs one frame flipped by hand (lid at 5..9). One joint per hole: no pattern type, so a 0.5 mm pattern error is just two joints that don't meet. No tree: each `connect_to` moves the other part at call time, in call order | API shape copied: a named frame on a part, kinds rigid / revolute / linear(prismatic), limits on the moving kinds. Not copied: coincident frames (face to face instead, so both sides use "z out of the face"); one-shot relocation (a tree solved once, so a loop or an orphan is an error, not a silent re-place). Not a dependency: OCC, and it doesn't produce cadlib's world-baked meshes, PIV joints or fastener records. |
| CadQuery assembly constraints | Point / Axis / Plane / PointInPlane constraints solved numerically; loops allowed | concept only (as the task says) | A numeric solve with no joint ranges, no fasteners and an OCC dependency; the result of a mis-stated constraint is a different pose, not an error. |
| Onshape mate connectors | a named frame on a part; fastened / revolute / slider / cylindrical / planar / ball mates with limits; patterns by replicate | concept only | The model this follows: connector frames and mates. Its pattern handling (replicate) and inferred connectors are left out. |

The gap that justifies new code: none of these, configured or wrapped, stores an interface as data on the part and
refuses two interfaces that don't agree; the in-repo pieces need the placement already computed. `mates` is a thin
layer: it computes the placement and calls `asm.joint`, `fastener_joint` and `asm.part` unchanged.

## Demo rebuild (`examples/demo-turret/build_mates.py`)
The demo turret with each part modelled in its own frame and placed by 7 mates (floor screws and the side bolt as
`fasten`, `PIV_pan` and `PIV_tilt` revolute, two fastened arm feet, the servo block rigid): 86 code lines against
`build.py`'s 99. Same checks.json, `CAD_LAYER_CHECK=1`:

| | absolute (`build.py`) | mates (`build_mates.py`) |
|---|---|---|
| fails / warns | 0 / 8 | 0 / 8 |
| fail list | (none) | (none) |
| warn list | 8 | the same 8; 7 verbatim, 1 with another pose for a tie (`PRT_base to PRT_pan 0.50 mm at pan=-92.5` vs `pan=92.5`: a disc's clearance is the same at every angle) |
| cadcheck rows | 50 | 50; 48 verbatim, 2 differ only in where a tied minimum was found (the same disc clearance; the pan's 1.6 mm bridge reported at another hole) |

`--bug-pattern` types the servo seat's pegs as `rect(10, 30.5)` against the servo's `rect(10, 30)`; the build stops:

```
MateError: mate servo (rigid): the connectors' hole patterns don't match: a point at (-5.00, -15.25) in a's frame
(world [-25.0, -15.25, 5.0]) is 0.250 mm from the nearest point of the other pattern.
  a PRT_base:servo_seat          pattern rect(10, 30.5)         hole None (4 points)
  b BUY_servo_pan:bottom         pattern rect(10, 30)           hole None (4 points)
```

## Proof (`tools/verify.d/mates.sh`, sourced by `verify_all.sh`)
- 27 unit cases (`mates_cases.py`): face to face with gap; `rot` and a mate declared child-first give the same
  placement; the default-x rule and a side mount staying upright; a 4-part chain (base, pan revolute Z, yoke rigid, head
  revolute X) with `PIV_tilt` parented to `PIV_pan` and a connector followed through pan 90 + tilt 30 to 1e-3 mm; a
  parent connector pointing -Z (lo/hi/home negated, mate +30 = -30 about world Z); prismatic along -X; pitch, count and
  hole-size mismatches; a 3-hole circle typed the same on both faces failing with the mirror hint; a fastened
  `rect(42, 32)` M2.5 board end to end; loop, orphan, tilted axis, unknown connector, missing range, object transform;
  `print_rot` converted for a plate mounted on a wall; servo and horn placed from `components.json` connectors.
- the demo comparison above (`mates_compare.py`), the bug build, `cad mates` from manifest and blend, and the eval
  kit's self-test.

## Evaluation kit (`tools/bench/mates_task/`)
A brief (deck, servo, horn-driven arm on the spline, PCB on 4 standoffs, lid with 4 screws), purchased-part data with
connectors and placeholders, two prompts that differ only in the template paragraph, the pre-mates template frozen
for the absolute arm, acceptance rows, and `score.py`: cadcheck fails, 7 interfaces measured from the blend alone
(placeholders found by a rigid fit of their meshes, screws by their axes) against 0.2 mm / 1 deg, and lines of build
code. The reference solution scores 0 fails, 0 warns, 7/7, 131 lines; a copy with the board 0.5 mm off scores only
`BUY_pcb` off, by 0.500 mm. How to run: the kit's README. The A/B runs are the coordinator's.

### A/B results on v1, and v2
The coordinator ran 3 designers per arm on v1. Every run: 0 cadcheck fails and 7/7 interfaces (mates-1 first scored
6/7 because the scorer only counted lid screws driven from the lid side; fixed, re-scored 7/7, with a selftest case for
the other direction). Wall time: absolute 3.3 / 4.0 / 5.5 min, mates 6.0 / 4.2 / 4.5. Lines: absolute 134 / 134 / 160,
mates 159 / 144 / 145. v1's brief hands over the world positions, so neither arm had placement to reason about.

`tools/bench/mates_task_v2/` is a two-servo pan-tilt with constraints only (tilt axis 40 above the pan horn and
crossing the pan axis, tilt servo's case below the axis and centred on the pan axis, camera axis through both axes,
board back 25 ahead): the tilt servo and camera are turned twice and carry tapped-hole patterns through the turns. It
scores 24 rows, including the camera's frame at 5 (pan, tilt) poses against the analytic chain and clearances over a
5 x 4 pan x tilt grid. The reference (mates) scores 0 fails and 24/24 in 153 lines. A camera planted 0.5 mm forward
flags exactly the camera and its 5 poses; a tilt range typed in the wrong sense flags exactly `PIV_tilt`.

Building the v2 reference found a limit that touches both arms: `asm.joint` turns only about +X/+Y/+Z, so with the
tilt spline pointing +Y the joint's + lowers the camera, whatever the brief says. The brief now allows either sense,
and the scorer maps the brief's sense onto the design's joint by its axis at home. A mate whose parent connector points
along a negative axis has PIV values that are the mate's negated; `cad mates` now says so on that line.

## Limits, and what I'd change after building it
- **Joint sense.** A joint can't count "+ about -Y" (above). A signed axis in `asm.joint` (`'-Y'`, as a base rotation
  with the joint channel applied first) would let a mate's values and the PIV's values be the same numbers.
- **Tilted axes.** A revolute or prismatic mate must turn about a world axis, because `asm.joint` and cadcheck pose
  joints by one Euler channel. Supporting a tilted hinge needs a base rotation on the PIV empty with rotation mode
  ZYX (so the joint channel is the local one); `joints.world_at` already reads the mode, `asm.set_pose` doesn't.
- **Loops.** The barrel sits in both arms but is mated to one; a second support raises. A "check" mate that verifies a
  closing interface (coincident within tolerance) instead of placing would cover four-bar-free cases like this.
- **Pattern subsets.** Using 4 of a horn's 8 holes needed a second connector in the data (`face_4`); a mate-level
  subset (`use=[0, 2, 4, 6]`) would keep one datasheet pattern.
- **Mirror.** Face to face mirrors y, so a `points` or odd circle pattern must be typed as seen from outside its
  face. The pattern check catches it with a hint when both sides declare a pattern; it cannot when only one does.
- **Fits are recorded, not checked.** A `clearance` or `slip` mate could write its cadcheck `fits` row (and a `press`
  mate its `allow`), removing the second declaration in checks.json.
- `cad mates model.blend --connectors` prints only the mates; the connector lines come from the manifest.
