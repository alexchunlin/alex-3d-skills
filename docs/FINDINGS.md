# Findings: agent-driven printable CAD (mm-launcher loop)

Running evidence log. Each revision run adds an `## Attempt N` section. Every rule or tool in this repo
should point at an ID here (for example `A1-T3`).

Sources are abbreviated:
- `HW` = `~/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/`
- `WF` = `~/.claude/projects/-Users-alxchunlin-code-stuff-mmlauncher-mm-launcher/c043264a-30c7-474d-8ca2-0c2301d01041/subagents/workflows/`
- `D1` = designer attempt 1, `WF/wf_26e26b28-15e/agent-af2e15ae070705e95.jsonl`
- `R1` = reviewer attempt 1, `WF/wf_26e26b28-15e/agent-a4e34520e7cf12eb4.jsonl`
- `D0` = the killed designer, `WF/wf_ebc9f356-a79/agent-a0e1dc96a1cba327c.jsonl`
- `D2` = designer attempt 2, `WF/wf_26e26b28-15e/agent-a6815d61faa83f67e.jsonl`
- `R2` = reviewer attempt 2, `WF/wf_26e26b28-15e/agent-a49e56a72136dd0ee.jsonl`
- `D3` = designer attempt 3, `WF/wf_26e26b28-15e/agent-a16a800e7f34fb0ab.jsonl`
- `R3a` = the first reviewer for attempt 3, interrupted after 6.6 min, `WF/wf_26e26b28-15e/agent-a84bc90b0abd58f66.jsonl`
- `R3` = reviewer attempt 3 (the restart that scored it), `WF/wf_26e26b28-15e/agent-aec430aae41935a1a.jsonl`
- `V2WF` = the v2 loop's workflow dir, `WF/wf_8db95a5a-12a/`. `HW2` = `HW/v2/`. v2 A1 agents: `P1` plan
  `agent-a0cb3a38bac407e33`, builders `B1-base` `a800ddf5500adfcaa`, `B1-pan` `acdd6edb2981721dc`, `B1-launcher`
  `a1e1c2446d3391a63`, `B1-feeder` `a598ac3528dfdb917`, `F1` finish `a4c7fa6df0fe83871`, `V2R1` review `a7067013f1c442a01`.
  v2 A2 agents: `P2` plan `a5f662b6704e21351`, builders `B2-params` `a5117b3d375e416e5`, `B2-pan` `a74de34b0f6956e51`,
  `B2-launcher` `ae270a06dae7409de`, `B2-feeder` `ac785fe505d626741`, `B2-base` `a4005e3c23adee0f0`, `B2-finish`
  `a08af4e9c73aea17a`, `F2` finish `acf219186d0bd28e9`, `V2R2` review `abf293a6ad3a00f0f`.
  v2 A3 agents: `P3` plan `a6a1ef3c308de2f03`, builders `B3-params` `a697af8569035dd0c`, `B3-launcher` `a54906111c8558bce`,
  `B3-feeder` `ac1b0b7e457db418e`, `B3-base` `ae57b92afa22d5800`, `B3-finish` `ae03e95c6533a28da`, `F3` finish
  `ae5efc1c43c08dd7a`, `V2R3` review `a9d0baaa5e62c78f0`.
  v2 A4 agents: `P4` plan `aaea83537a75dface`, builders `B4-params` `a7061741ac9adb630`, `B4-launcher` `ab19211aef41d8234`,
  `B4-feeder` `a7f1b7ad89443aea1`, `B4-cables` `a98004765603d790f`, `B4-finish` `a4c233ad282956d1b`, `F4` finish
  `a2dd9ca6dd2a3d344`, `V2R4` review `a9b8ec9c08d63b15a`.
  v2 A5 agents: `P5` plan `a3ebd0625cbbbed8c`, builders `B5-params` `a88feb02c28c95899`, `B5-launcher` `a38b2d19c5e922bf3`,
  `B5-feeder` `a2ac75214634ea45d`, `B5-finish` `aaceba7df82b03f7a`, `F5` finish `a25a45ccbe64f5e05`, `V2R5` review
  `a4683ee602e280ba5`.
  v2 A6 agents: `P6` plan `a5c6c97fd5291db4f`, builders `B6-checks` `ab67c3c981ceb6e7b`, `B6-feeder` `a6f76c31bfd31b5c4`,
  `B6-junction` `aac18bdc4f360b240`, `B6-finish` `ad52a387901339499`, `F6` finish `a901396d59e028176`, `V2R6` review
  `a63e157964068fba7`.
  v2 A7 agents: `P7` plan `ad3613ab937789401`, builders `B7-checks` `a91da03e25e2193ee`, `B7-cap` `ab7fc7097ebb0f9d8`,
  `B7-tail` `aabeff3011188d075`, `B7-finish` `ade4ba6e78782e6a9`, `F7` finish `ad3729c48968e6dc0`, `V2R7` review
  `aa6f4aea5dd48c1d4`
- `PA` = `~/code-stuff/space-bar-push-assist/` (the push-assist project, a second design run through these skills;
  read-only). `PALOG` = `docs/evidence-push-assist/loop-log.txt`, the recon log kept during its review loop.
- `PASESS` = `~/.claude/projects/-Users-alxchunlin-code-stuff-space-bar-push-assist/beb7cf69-3aa8-486b-8098-1801e05fe0d3`.
  `PASESS.jsonl` is the coordinator, which also designed A1 and A2 inline. Agents are in `PASESS/subagents/agent-<id>.jsonl`.
  Push-assist agents: reviewers `PA-R1` `ad9fb7f4623b031a1`, `PA-R2` `a134c4732d01b3fa9`, `PA-R3` `afcccadc60d39dabd`,
  `PA-R4` `ae1d40ece5cb4f293`, `PA-R5` `aebabdf9ab4fc8a5c`, `PA-R6` `abc841ef91bf6c685`, `PA-R7` `a5c527e47ff09f34d`,
  `PA-R8` `aa2101a1a30a12ace`. Designers `PA-D3` `a90cb39836f00bda6`, `PA-D4` `aa0377354f9159b42`, `PA-D5`
  `a2b121d6d12a95494` (with its firmware sub-agent `ad17a3df5862d2263`), `PA-D6` `a98d3a242fa8b026b`, `PA-D7`
  `a9833809bb3b8e55b`, `PA-D8` `a9775a6b2357a2a14`. IDs: `PA-A7-T19` is PALOG's observation T19 of attempt 7.
  `PA-R7 #1` is issue 1 in PA-R7's ranked list.

**Baseline:** v1 (the no-tools loop) ran attempts 1-3 and was then stopped by the user (2026-10-24 evening, see
`HARVEST_BRIEF.md` "Process change"). The v1 tool results below are counterfactual. Every
"caught" or "would have flagged" below is counterfactual, measured on archived copies after the fact. The per-attempt
cost and score rows are the baseline that the first tool-using loop will be compared against.

Timestamps like `D1 0:17:41` are elapsed time from the agent's first message, as printed by
`tools/transcript/cc_transcript.py timeline`. All numbers below come from that tool unless stated otherwise.

---

## Attempt 1 (harvested 2026-10-24)

### Per-agent cost

| Agent | Wall | Model time | Tool time (Blender) | API calls | Output tok (thinking) | Cache read | Cache write | Peak context | Images read | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| D0 (killed) | 43.6 min | 38.5 | 0.1 (0.1) | 13 | 215k (208k)¹ | 0.5M | 0.41M | 237k | 9 | 6 KB plan only |
| D1 | 64.0 min | 61.6 | 2.4 (2.3) | 60 | 378k (255k) | 19.2M | 0.91M | 522k | 29 | 35 parts, 84 KB script |
| R1 | 18.6 min | 18.2 | 0.4 (0.3) | 42 | 103k (71k) | 7.6M | 0.31M | 313k | 33 | 5 / 6 / 5 |
| D2 (first 24 min) | 24.1+ | 24.0 | 0.1 | 13 | 134k (131k) | 1.0M | 0.38M | 245k | 10 | running |

¹ Corrected in the attempt-2 run: one 233 s call had no final usage line, so the first harvest counted 5 output tokens for it (A2-T5).

### Time and token sinks

**A1-T1. Single upfront thinking blocks dominate wall time, not Blender.** In D1, two thinking blocks took
16.7 min (`D1 0:01:00 → 0:17:41`, 90k thinking tokens) and 10 min (`0:17:53 → 0:27:42`, 56k). Then one `Write`
streamed the whole 78 KB `build_assembly.py` in 5.4 min (`0:27:57 → 0:33:17`, 44k output tokens). The first
Blender build ran at `0:35:38`. So 56% of D1's wall time passed before any geometry existed. The same pattern
shows up in every designer: D0 spent 14.8 min and 18.4 min in two blocks (186k thinking tokens) and never
wrote geometry; D2 spent 17.1 min in one block (`D2 0:00:48 → 0:17:56`, 97k thinking tokens) re-deriving
the feed trajectory by hand.

**A1-T2. Blender cold starts are not a cost.** Measured on this machine: `Blender -b --factory-startup
--python-expr "import bpy"` takes 0.69 s, and loading the 6 MB `mm_launcher.blend` takes 0.70 s. D1 ran
Blender 27 times for 2.3 min in total, and most of that was the build itself (about 6 s per full rebuild with
checks; `D1 #26–#49`). A persistent Blender daemon or MCP server would save at most about 20 s per attempt.

**A1-T3. What the long thinking re-derived** (`cc_transcript.py thinking D1 --min-s 300`): Blender 5.1 API
details (STL import, bmesh, Manifold boolean solver), a CSG helper layer, an involute gear generator, a
binary STL writer, the world frame, base layout and battery orientation, the PCB orientation for USB-C, and
the tilt-arm topology. About 270 lines of `build_assembly.py` are generic geometry helpers (`HW/blender/
build_assembly.py:146-415`: `loft, prism, cyl, cone, hull2d, hull_circles, revolve, csg, bevel, gear_poly,
teardrop_x`), and about 400 more are registry, export, render and section code (`:417-500`, `:1518-1768`).
A library removes all of that from the generation. D2 re-read the brief and five reference PNGs that hadn't
changed (`D2 #17-19`), and spent 17 min working out the drop trajectory in its head (A1-F1). A drop simulator
would have answered that in seconds.

**A1-T4. Prompt-cache expiry during long generations.** The cache has a 5 min TTL. Every generation longer
than 5 min made the next call re-write the whole context: D1 had 3 misses (140k + 202k + 246k = 587k
tokens re-written, `D1 usage` at `0:17:48`, `0:27:57`, `0:35:15`), D0 had 2 misses (363k), and D2 has had 1
so far (242k). Shorter steps avoid this.

**A1-T5. Context growth.** D1's context grew to 522k tokens over 60 calls. Its 19.2M cache-read tokens are
mostly that context being re-sent on every call after `0:35`. Most of the growth is retained thinking (the
90k block raised the context from 46k to 140k) plus the 78 KB script echoed as tool input. 29 images added
about 3.5 MB, but the Read tool downsized them to 60-340 KB each, so they are a minor share.

**A1-T6. Images are not the sink people expect.** The 1800 x 1350 Workbench renders are 2.0-2.3 MB on disk
(`HW/renders/attempt-1/*.png`), but arrive at the model as 95-170 KB (`cc_transcript.py images`). D1 read 29
images and R1 read 33. R1 re-read 2 renders after adding M&M markers (`R1 #44-48`). The real cost of images is
the render-and-look loop, so a numeric check is preferred over a picture wherever one exists.

**A1-T7. Brittle full-file string edits.** D1 made 30 edits by piping Python `str.replace` heredocs into the
84 KB script (`D1 #17, #23, #26, #29, #42, #43, #45`). One failed with `ValueError: substring not found`
(`D1 0:55:24 #43`). A script split into per-subsystem modules makes the edits small and local.

**A1-T8. The reviewer spends its time reverse-engineering the script.** R1 used 7 calls to read
`build_assembly.py` in chunks to find parameters and part intent (`R1 #21-23, #26, #30, #34, #42`). The
model time before the longer reads was 71-93 s (`R1 #26, #30, #34`). It then wrote 10 throwaway measurement scripts (`/tmp/rv_*.py`). A
machine-readable part manifest (part, pivot, joint ranges, fastener axes) and a standard measure CLI remove
both.

**A1-T9. Work lost on interruption.** D0 was killed by a session restart at 43.6 min with 193k output
tokens spent. The only artefact was a 6 KB `DESIGN_LOG.md` plan, written at `D0 0:34:41`. Nothing was
checkpointed in between, and the orchestration script cannot resume an attempt (`workflows/scripts/
mm-launcher-cad-loop-*.js`: the loop starts at `n = 1` with no state read from disk). Nothing gave the user
progress either: no file was updated during the 35 min before the first build.

### Foot-guns (caught by R1; could a tool have caught them?)

| ID | Issue (R1 item) | Why D1's checks missed it | Tool that catches it |
|---|---|---|---|
| A1-F1 | **Blocker:** the M&M lands 43-76° behind TDC, outside the 26° hood lip; at 45° tilt it hits the chute rear wall (R1 #1) | No feed simulation; the designer deferred it as "designed from geometry only and untested" | `drop_test` ray grid at every tilt, reporting landing angle vs. hood arc |
| A1-F2 | Nip never squeezes a 7 mm M&M: 8.9-12.1 mm gap minus tape (R1 #2) | No check relates the adjustment range to the payload | `gap_range` check: payload thickness vs. min/max gap |
| A1-F3 | **Blocker:** arm-cap screw head under the feeder disc, 27.2 mm³ overlap (R1 #3) | `checks.py` excludes Fasteners and Cables (`HW/blender/checks.py:7`, `solids = printed + bought`) | interference over **all** collections |
| A1-F4 | Horn adapter can't be assembled: screws can't be driven (R1 #4) | No tool-access check | `screw_access`: ray from the head outward along the screw axis |
| A1-F5 | Tilt has no margin: 0.21 mm at 45°, contact at 46°, overlap at 47.5° (R1 #5) | Poses only at 0 / 22.5 / 45; contacts under 0.5 mm³ counted as fine (`VOL_TOL`) | joint sweep past the limits plus a clearance margin threshold |
| A1-F6 | Service needs a 15-screw teardown (R1 #6) | not checkable automatically | reviewer checklist item: service operations |
| A1-F7 | Magnet centring is uncontrolled (R1 #7) | not geometric | reviewer checklist item: alignment jigs |
| A1-F8 | Outlet partly blocked at 40-45° tilt; the log claimed it clears (R1 #9) | Claim made from reasoning, never measured | `drop_test` |
| A1-F9 | Trunnion face rubs the bonnet flange at 0.00 mm at every tilt (R1 #11) | Zero-volume contacts are counted and then ignored (`checks.py: touching_pairs_zero_volume`) | report every contact pair between parts on **different** pivots as a failure |
| A1-F10 | Motor-face screws modelled reversed; shanks inside the flywheel (R1 #15) | Fasteners excluded (A1-F3); `screw()` takes a direction that's easy to flip (`build_assembly.py:1375`, the motor screws pass `(1,0,0)`) | `fastener_sanity`: head clear of material, tip inside a part on the same pivot, no fastener touching a part on another pivot |
| A1-F11 | Trunnion screws at the bottom of a 102 mm bore; encoder-cap screw reachable only at 45° tilt (R1 #14) | No tool-access check | `screw_access` reports the clear driver length per screw |
| A1-F12 | Bullet joints of the motor leads land at the moving bend (R1 #10); no UART route (R1 #12) | Cables are drawn but never checked | cable-length check (path length vs. lead length) plus a required-route list in the checklist |
| A1-F13 | Battery side clearance only 1.0 mm against a nominal envelope (R1 #13) | not flagged | `slide_out` sweep plus clearance minimum for purchased envelopes |
| A1-F14 | **Overclaimed checks:** D1 returned `checks_passed: true` and "zero unintended interference at 9 poses", with fasteners and cables excluded and contacts ignored | The schema asks a yes/no question | Checks emit evidence JSON with an explicit `coverage` list. The designer reports the JSON, not a boolean. |

8 of the 18 R1 issues (F1, F3, F4, F5, F8, F9, F10, F11), including both blockers, are geometric and
detectable by a tool. The reviewer found them only by writing ad-hoc scripts (`/tmp/rv_measure.py`: feed
drop rays, cross-pivot fastener/cable overlaps, 2.5° tilt sweep, battery slide; `/tmp/rv_m7.py`: tilt
46/47 clearance).

### What worked (worth turning into a library)

- **Manifold-solver booleans** via Blender's built-in `BOOLEAN` modifier with `solver='MANIFOLD'` (`build_assembly.py:321 csg`). All 35 printed parts were manifold first time once the solver was used.
- **BVH triangle overlap as a pre-filter, then Manifold intersection volume** (`checks.py:inter_volume`). Fast and exact enough. Took about 5 s for 50 solids at 9 poses (`D1 #20`).
- **Ray-cast wall-thickness probe** (`checks.py:overhang_and_walls`). It found real thin walls that D1 fixed (`D1 #28-#31`).
- **Print-orientation rotation stored on each object** (`print_rot` custom property) and used for both the STL export and the bed-fit/overhang checks, so they agree.
- **Centre of mass / static tip angle at every pose** (`checks.py:stability`): tip ≥ 44.1°.
- **STL contact sheet in print orientation** (`/tmp/mmwork/sheet.py`, `D1 #59`): one image showed all 29 parts on the bed.
- **Section renders with scope** (`build_assembly.py:1675 render_section`): R1 reused them for 10 of its 14 extra views.
- **Swept-cutter clearance:** subtracting the moving part's swept volume in 1.5° steps (`sweep_cutters`) is a good pattern, but it must sweep past the joint limit (A1-F5).
- **Reviewer techniques:** a ray grid through the outlet (A1-F1), cross-pivot overlaps of fasteners and cables (A1-F10), a 2.5° tilt sweep with nearest distance (A1-F5), a battery slide-out sweep in 5 mm steps (A1-F13), and M&M lentil markers plus tangent rods in section renders (`/tmp/rv_render.py`).

### Reviewer quality

- **Actionable evidence:** every R1 issue cites a number or a file (`measurements.json`, a named render, a parameter name) and gives a fix with dimensions. The issues D2 picked up first are the measured ones.
- **Strictness held:** "a single blocker caps that metric at 6" was applied (F = 5, M = 6).
- **Noise risks:** Aesthetics (5) rests on judgement from 33 images, with no anchor examples. Scores are integers with anchors 5-6 = "significant risk", so a 1-point move can come from one issue. `measurements.json` uses ad-hoc keys (36 KB, mostly per-ray hit lists), so the next reviewer can't diff it.
- **Cost:** 18.6 min and 103k output tokens, of which about 8 min went on reading code and writing measurement scripts (A1-T8).

### Verification of the tools built this run (2026-10-24)

All runs are on copies: `/tmp/alex3d-a1` (attempt-1 outputs), plus the archived blend `examples/mm-launcher-a1/mm_launcher_a1.blend.gz`.
`tools/verify_all.sh` re-runs everything: 17/17 passed.

- **cadcheck on the attempt-1 blend** (`examples/mm-launcher-a1/checks.json`, which declares the D1 joints, the 9 designed running fits and the BOM assembly order; 36 s, 102 objects, 11 joint groups up to 48 poses each). It reproduces R1 numerically:
  - A1-F3 feeder disc x screw: 48.6 mm³ at feeder 30° (27.2 at home, the same as R1)
  - A1-F10 four motor screws: 27 mm³ each in the flywheel, plus "head inside launcher_body"
  - A1-F9 trunnion x bonnet contact at 19 poses
  - A1-F5 hopper 0.21 mm at 45° (fail) and overlap at 47.5° (warn)
  - A1-F1 drop landing 44-80° against a 0-26° window at tilt 0; tilt 22.5 and 45 hit the chute wall
  - A1-F2 nip 9.50 mm
  - A1-F11 trunnion screws need 114 mm reach

  22 fails in total.
- **The same blend without the declarations** (the first run) gave 36 fails. The extra 14 were designed running fits (journals 0.14 mm, hub 0.26 mm, horn pockets 0.30 mm) and the plain thrust bearing. Declaring `fits` removed them. This is why `fits` and `allow` must carry a reason the reviewer audits.
- **New, unconfirmed by R1:**
  - `CAB_12v_ctrl` runs 1332 mm³ through `BUY_servo_controller`
  - `FST_cover_0`'s driver path is blocked 2.4 mm out by the cover's own boss
  - the yoke-foot screws sit beside 108-114 mm arm walls (driver handle clearance)
  - the flywheel has a 72 mm ceiling region in print orientation (`parts` warn)

  The next reviewer should confirm or refute each with a section.
- **cadq** reproduces R1's numbers exactly: disc x screw -27.235 mm³, hopper 0.212 mm at 45° and -38.9 mm³ at 47.5°, and the outlet ray hits `PRT_launcher_body` 39.0 mm down at 45° tilt.
- **Demo turret** (`examples/demo-turret`): the clean build passes (0 fails). The `--bug` build plants a reversed screw, a proud head in the muzzle sweep and a tilt range into the pan disc; all three fail.
  The first demo build had 7 real fails of my own making: arm screw heads in the base deck, a cable through a solid disc, and an axle fit declared tighter than faceting allows. The checker found them before any render.
- **Earlier checker bugs fixed during verification:**
  - A normal-sign point-in-solid test misfired near edges: it reported `FST_cap_L1` "head inside encoder_cap", which is false. It was replaced by a 3-direction ray parity test.
  - A thread test on the screw axis always saw the pilot hole (air). It now samples a ring at 92% of the shank radius.
  - Tool access without an assembly order blocked screws behind parts installed later. `assembly_order` with bench/merge steps fixed that.
  - Slide-out used a triangle overlap and flagged the battery at 0 mm. It now uses the intersection volume.

### Why not the existing code (prior art, measured; details in `tools/prior_art/README.md`)

- **D1's `checks.py`:** R1's re-run (`HW/renders/attempt-1/review/checks_rerun.json`) reports 0 interference on the same blend where cadcheck finds both blockers. It excludes fasteners and cables, ignores contacts and checks only 3 tilt poses. Its manifold, wall, overhang, CG and boolean-volume code is kept inside cadcheck.
- **D1's geometry helpers:** kept, moved into `cadlib/geom.py` (plus the CSG closed-solid check and teardrop orientation).
- **trimesh + manifold3d:** checks 29 STLs in 0.16 s with the same answers. STLs have no assembly, joints or fasteners, so 0 of the 8 tool-catchable R1 issues are reachable. Blender's MANIFOLD solver is the same library.
- **Blender MCP / daemon:** not built. Cold start is 0.7 s and Blender was 2.3 of 64 min.
- **build123d:** not measured yet. It is the candidate for the fillet/aesthetics gap.

### Implications for tooling (what this run built, see STATUS.md)

1. A geometry/assembly library and project scaffold, so the designer writes only design-specific code (A1-T1, T3, T7).
2. One check runner over **all** collections, with joint sweeps beyond the limits, contacts reported, fastener sanity and screw access, a drop-path simulator, slide-out, and a coverage list in the JSON (A1-F1…F14).
3. A part manifest written by the build, and a measure CLI (A1-T8).
4. A reviewer rubric with anchors and an evidence checklist (reviewer quality).
5. An orchestration template with checkpoints, milestones, progress files and short generation steps (A1-T1, T4, T9).
6. **No** Blender daemon or MCP server: the measured cold start is 0.7 s (A1-T2).

---

## Attempt 2 (harvested 2026-10-24, revision run)

Inputs: the D2 and R2 journal results, the D2 and R2 transcripts, `HW/renders/attempt-2/` (review.md, checks.json,
review/checks_rerun.json, 33 PNGs), and the 20:27 blend R2 reviewed. That blend is archived as
`examples/mm-launcher-a2/mm_launcher_a2.blend.gz`. D3 (`agent-a16a800e7f34fb0ab`) was 0.6 min old and is not ingested.
The live loop still runs its own prompts, so nothing from this repo reached D2 or R2. The tool numbers below are what
the tools would have reported, not what the agents saw.

### Per-agent and per-attempt cost

| Agent | Wall | Model time | Tool time (Blender) | API calls | Output tok (thinking) | Cache read | Cache write | Peak context | Images read | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| D2 | 82.8 min | 72.3 | 10.5 (10.4) | 74 | 443k (305k)² | 31.9M | 1.36M | 698k | 32 | 33 printed parts, 54 fasteners, 111 KB script, 32 KB checks.py |
| R2 | 14.2 min | 13.3 | 1.0 (0.9) | 37 | 77k (49k) | 6.0M | 0.30M | 298k | 34 | 6 / 5 / 6 |

| Attempt | Design + review wall | Output tokens | Cache read | Scores F/M/A (sum) |
|---|---|---|---|---|
| 1 | 64.0 + 18.6 = 82.6 min | 481k | 26.8M | 5/6/5 (16) |
| 2 | 82.8 + 14.2 = 97.0 min | 520k | 37.9M | 6/5/6 (17) |

² 372.6k reported plus about 70k estimated for the `0:24:00 → 0:36:12` call, whose final usage line never arrived (A2-T5).

**The loop is not converging fast enough.** R2 marks 12 of 18 R1 issues FIXED and 6 PARTIAL, but it raises 10 new
ones, including a new blocker. The new issues fall in the same classes as A1's: tool access, fastener length and
placement, indexer behaviour, alignment datums. One point of total score per attempt, at 97 min per attempt, does not
reach 9/9/9 within the 8-attempt budget.

### Time and token sinks (do they recur?)

**A2-T1. Upfront thinking recurs (A1-T1).** D2 spent 36 min, 44% of its wall time, before writing its first new file.
That was three thinking blocks: 17.1 min (`D2 0:00:48 → 0:17:56`, 96k thinking tokens), 5.6 min (`→ 0:24:00`, 32k) and
12.1 min (`→ 0:36:12`, about 68k). The content (`thinking --min-s 300`) was the drop trajectory in the tilted launcher
frame worked out by hand. That repeats A1-T3, and it ended in an architecture change from an overshot to an
undershot wheel. Only then did D2 write a 2D feasibility script (`/tmp/mmwork/geo2d.py`, `#22`). The `slide` drop mode
built this run answers "where does it land at tilt θ" in 0.8 s for 5 tilts × 29 rays. A designer who can call it can
test a topology instead of deriving it.

**A2-T2. Blender time is up but still not the bottleneck (A1-T2 holds).** It went from 2.4 to 10.4 min (12.6% of wall)
over 14 rebuild-and-check cycles at 37-50 s each (`D2 #53-#94`). D2's own checks.py grew to sweeps, a tracer and
service sweeps. A full cadcheck run on this 119-object blend takes 58 s (interference 41 s, fasteners 11 s); `cad check
... --only fasteners,cables` takes 13 s. A daemon would still save only the 0.7 s cold start per call.

**A2-T3. D2 avoided the 84 KB single Write itself (A1-T7 partly fixed).** It wrote three chunks (9.6, 37.6 and
42.8 KB in `#27`, `#32` and `#33`, about 2.5-3.5 min each) and reused unchanged A1 code by slicing the old file
(`#23`, `#31`). No edit failed this time. It still rewrote checks.py whole (30 KB in `#46`), and the build script grew
from 84 to 111 KB.

**A2-T4. Cache misses recur (A1-T4).** Three misses re-wrote 869k tokens (`D2 0:18:18` 242k, `0:36:12` 278k, `0:36:22`
350k). The last two are 10 s apart. The 12-min call before them ended without a final usage line, and the next call
found no cache either.

**A2-T5. Extractor bug, fixed.** Calls whose stream ends without a final usage line keep the streaming-start usage
(`output_tokens` ≈ 8, no `output_tokens_details`). D2 had 2 such calls and D0 had 1. `cc_transcript.py` now estimates
their thinking from `thinkingDurationMs`, at the rate measured on complete calls in the same transcript (88-95
tokens/s across all five agents). `summary` prints a warning, and `workflow` includes the estimate.

**A2-T6. Reviewer cost fell, but code reading recurs (A1-T8).** R2 took 14.2 min, with no cache misses and no
generation over 120 s. The time split:
- 0:00-1:07: read 23 designer renders.
- 1:14-5:42: read the build and check code (11 calls, about 4.5 min).
- 6:12-9:42: 7 ad-hoc measurement scripts (`/tmp/mmrev/*.py`).
- 10:33-12:39: renders and looking at them.
- 13:30: wrote the review.

Every one of the 7 scripts now has a cadcheck block: nip rays → `distances.ray`; pinch bolts → bolt-to-nut pairing;
L-key → access `lkey`; battery, USB and drop column → `slide_out` / `drop`; same-pivot fasteners → `into_purchased`;
feeder pockets → `index_tests`; encoder → `stacks`. The code reading remains because D2 wrote no manifest (it doesn't
use cadlib).

**A2-T7. Images stay minor (A1-T6 holds).** 32 + 34 reads, which reached the model as 3.7 + 4.0 MB. R2 read all 23
designer renders within the first 67 s.

### Foot-guns (R2), and whether cadcheck catches them

"Before" is cadcheck at `f593896` (the attempt-1 harvest) on the A2 blend with `examples/mm-launcher-a2/checks.json`.
"After" is this run. Both runs: `/tmp/alex3d-a2/cadcheck_baseline.json` and `cadcheck_final.json`.

| ID | R2 issue | Before | After | Needs a declaration? |
|---|---|---|---|---|
| A2-F1 | **Blocker:** a 2.5 mm L-key can't reach the flywheel pinch bolts (R2 #1) | fail, straight bit blocked at 18.5 mm (right for the wrong reason) | fail: straight bit blocked at 18.5 mm, L-key arc 0° (need 60); service op fails at tilt 45 too | no |
| A2-F2 | The documented 0 → 60 → 0 feeder index drops two candies (R2 #2) | not checked | fail: 2 windows (0-6°, 54-60°), open at park | yes: `index_tests` from BOM §0 |
| A2-F3 | M3 x 16 pinch bolts end 0.36 mm short of their nuts (R2 #3) | warn "no material grips the thread" | fail: stops 0.35 mm short of `FST_fw_nut_0` | no |
| A2-F4 | Rigid 1 mm nip squeeze, nothing yields (R2 #4) | false fail: nearest distance 5.49 mm is flange to plate | warn: gap along the BDC ray 6.49 mm (R2: 6.5), squeeze 1.01 mm, no `compliant` part | yes: the ray and payload |
| A2-F5 | Adapter through-bolts and nuts inside the battery envelope (R2 #5) | partial: nuts "head inside BUY_battery" (wrong message); bolts skipped as same-body FST/BUY, the same blind spot as D2's checks.py | fail: 4 bolts 2.5 mm into `BUY_battery`, 4 nuts 100% inside | no |
| A2-F6 | Right clamp screw blocked at tilt 0, so "gap change needs no disassembly" is false (R2 #7) | not checked (on the bench it is reachable) | warn: reachable only at tilt 45, blocked by `PRT_yoke_arm_R` 2.2 mm out (R2: about 2.5) | yes: `service` op from BOM §5 |
| A2-F7 | Magnet jig datum chain 0.55-0.75 mm vs 0.3 (R2 #6) | not checked | warn: worst case 0.55 > 0.30, RSS 0.29 | yes, all of it: I wrote the terms from R2, so this is a calculator, not a detection |
| A2-F8 | 10 mm of feeder bus bare above the left bonnet (R2 #8) | not checked | warn: 11 mm visible at (-107, -8, 249) | no |
| A2-F9 | Jack screws and lock nuts hang under the pod (R2 #9) | not checked | warn: head stand-off 11 mm on both jacks | no |
| - | Pieces don't share a form language (R2 #10) | - | - | not tool-catchable |

After this run, 8 of the 10 R2 issues produce a fail or warn naming the right objects and close to R2's numbers
(A2-F7 only once declared; #10 is out of scope). Five fire from geometry alone: F1, F3, F5, F8 and F9. Three need a
config entry that restates a BOM claim: F2 (BOM §0 index), F4 (nip line and payload) and F6 (BOM §5 service). That is
why `SKILL.md` now says to turn every motion, timing or service claim into a check before writing it into the BOM.
F2 (a major) and F6 were confident BOM prose that nothing had executed. The designer's log says "park at 0 deg
(pocket A under the hopper)", while the pocket is over the outlet at 0.

**False fails in the earlier cadcheck, fixed this run (A2-V1).** The `f593896` cadcheck gave 34 fails on A2, and 28 were false or
config artefacts:
- 12: nuts treated as screws ("head buried", "cannot be driven").
- 6: bolt × nut overlaps counted as interference.
- 1: a flush countersunk head "inside" the feeder disc, which runs 0.3-0.6 mm above it. The head probe moved from
  0.6 to 0.25 mm and to same-body parts.
- 5: straight-ray feed fails on a chute the candy slides down.
- 4: config (jack screws modelled fixed while the backplate sweeps, clamp-screw contacts, a nearest-distance nip).

After the fixes, the 15 remaining fails are all R2-confirmed. They are per object: 12 fastener fails cover A2-F1, F3
and F5, plus 2 service fails and 1 index fail. Runtime is 58 s.

**New, unconfirmed by R2** (the next reviewer should confirm or refute each with a section):
- Backplate-to-bay clearance is 0.14 mm at hood -1.2°. The bay is a union of translated, not rotated, plate outlines
  (`D2 0:36:12` thinking).
- `FST_hinge` has only 2.0 mm of thread in `PRT_journal_plate`.
- 39 mm of the feeder-servo lead is visible under the plate around (21, -84, 227).
- Foot screws need a 130 mm+ driver (A1 carry-over).
- `CAB_12v_ctrl` runs 1332 mm³ through the servo-controller envelope (A1 carry-over).
- Battery slide-out minimum is 1.25 mm, where R2 measured 2.0 all round.

### Recurrence across attempts

| Class | A1 | A2 | Tool now |
|---|---|---|---|
| Payload path never simulated | A1-F1 blocker | FIXED: D2 wrote its own tracer | `drop_tests` `mode: slide` (port of D2's tracer) |
| Working condition at the nip | A1-F2 no squeeze | A2-F4 rigid squeeze | `distances` `ray` + `payload_mm` + `compliant` |
| Fasteners left out of the checks, and overclaiming | A1-F3, F10, F14 | A2-F5: D2's checks.py skips same-pivot FST vs BUY and reported "all_pass: true, 0 unintended interferences" | shank or nut inside a purchased part; `coverage` list |
| Screws you can't drive | A1-F4, F11 | A2-F1 (blocker again), A2-F6 | L-key access, `service` ops, continuous-joint poses |
| Indexer behaviour | A1 R1 #9 (undocumented index) | A2-F2 (documented index double-feeds) | `index_tests` |
| Alignment datum | A1-F7 (no jig) | A2-F7 (jig, weak datum) | `stacks` (declared) |
| Tilt margin | A1-F5 | FIXED: hard stops at -3 / +46 | overtravel warns show the stop contact at 47.5 |
| Rubbing faces | A1-F9 | FIXED (0.5 mm); D2's checks still count and ignore 61 zero-volume contacts | contacts across joints fail unless declared |
| Cables | A1-F12 (routes) | routes FIXED; A2-F8 bare run | cable exposure |
| Visible hardware | (aesthetics 5) | A2-F9 | head stand-off, protruding thread |

### What worked (A2)

- D2's drop tracer (fall, slide, stall below 20°; `HW/blender/checks.py:395`) is now cadcheck `drop_tests`
  `"mode": "slide"`. On the same blend it gives 29/29 rays on the tape at psi 66-89°, against D2's 37/37 at 65-85°. The
  ray grids differ (29 vs 37 starts), and capture counts any face of `PRT_flywheel`.
- D2's service sweeps (move a group, ignore removed parts) are now `slide_out` with `objects` / `ignore` / `pose`. They
  reproduce "flywheel off 140 mm along +X at tilt 45: clear".
- D2 timed the A1 build before rewriting it (`#21`) and reused unchanged code by slicing the old file (`#23`, `#31`).
- R2's previous-issue table (18 rows, FIXED / PARTIAL / NOT FIXED) made progress auditable. The loop prompt already
  asks for it, and `templates/cad-loop.workflow.js` keeps it.
- R2's L-key sweep used real key dimensions (18 mm short leg, 60° swing), and its feeder-pocket check was done at the
  **documented** stroke ends. Both are now checks with the same parameters.

### Reviewer quality (A2)

- The anchors held: one blocker capped M at 6, and R2 scored it 5. F went 5 → 6 with 3 majors, A went 5 → 6.
- R2's evidence is numeric for 9 of 10 issues. Two numbers disagree slightly with cadcheck: clamp-screw clearance 2.5
  vs 2.2 mm, and battery clearance 2.0 vs 1.25 mm.
- Noise: aesthetics still has no anchors for form language (R2 #10), and that one issue could move A by a point.

### Why not the existing code (A2 additions)

- **D2's checks.py tracer:** hard-wired to the launcher frame (`B.W_P`, `B.WHEEL_R`, `launcher_frame()`) and fixed
  start offsets. The port takes target objects and an angle spec from config and gives the same verdict (table above).
- **D2's fastener cross-pivot check:** checks only fasteners against other pivots. It has no same-pivot FST-vs-BUY check, no
  nut pairing and no tool access, so it misses A2-F1, F3, F5 and F6 on the blend it ran on (R2 re-ran it: "same
  results as the designer's: 0 unintended interferences").
- **cadcheck at f593896:** the "before" column above. Config alone could not express nuts, L-keys, service ops,
  indexers or slide feeds. Each needed code (about 450 lines in `cadcheck.py`).

### Verification of this run

- `tools/verify_all.sh`: 28/28 passed in 2:43. That includes the A1 regression (unchanged) and a new A2 regression: 9
  patterns plus "exactly the 15 R2-confirmed fails, and the slide tracer feeds 29/29 at every tilt".
- The demo turret gained a bolt with a nut: through in the clean build, 0.40 mm short in `--bug` (caught).
- `cc_transcript.py workflow` on both runs. D0 was corrected from 193k to 215k output tokens.

---

## Attempt 3 (harvested 2026-10-24, revision run; the last v1 baseline attempt)

Inputs: the D3, R3a and R3 journal entries and transcripts, and `HW/renders/attempt-3/`: review.md, checks.json,
review/checks_rerun*.json, 30 designer PNGs and 14 reviewer PNGs. Also the 21:20 blend that R3 reviewed (md5
`763db27f…`), now archived as `examples/mm-launcher-a3/mm_launcher_a3.blend.gz`. v1 stopped after this attempt. The
tool numbers below are counterfactual: nothing from this repo reached D3 or R3.

### Per-agent and per-attempt cost

| Agent | Wall | Model time | Tool time (Blender) | API calls | Output tok (thinking) | Cache read | Cache write | Peak context | Images read | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| D3 | 41.0 min | 36.3 | 4.7 (4.3) | 75 | 219k (139k) | 22.9M | 0.49M | 488k | 36 | 32 STLs (36 printed objects), 54 fasteners, 133 KB script, 38 KB checks.py |
| R3a (interrupted) | 6.6 min | 6.3 | 0.3 (0.2) | 25 | 34k (26k) | 3.1M | 0.21M | 207k | 29 | none: "[Request interrupted by user]" at 21:31 |
| R3 | 18.5 min | 17.1 | 1.5 (1.4) | 50 | 99k (63k) | 9.8M | 0.33M | 333k | 43 | 6 / 6 / 6 |

**Baseline rows (v1, no tools).** Attempt 3 includes R3a, which was lost work.

| Attempt | Design + review wall | Output tokens (thinking) | Cache read | Cache misses (re-written) | Peak context | Longest generation | F/M/A (sum) | Issues B/M/m | Tool-catchable now | cadcheck on the archived blend | Recur from earlier attempts |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 64.0 + 18.6 = 82.6 min | 481k (327k) | 26.8M | 3 (587k) | 522k | 1001 s | 5/6/5 (16) | 18 (R1) | 7 R1 findings reproduced | `examples/mm-launcher-a1/cadcheck_summary.json` | (first) |
| 2 | 82.8 + 14.2 = 97.0 min | 520k (354k) | 37.9M | 3 (869k) | 698k | 1028 s | 6/5/6 (17) | 1/3/6 | 8 of 10 | 15 fails, all R2-confirmed | 6 of 10 classes (table A2) |
| 3 | 41.0 + 6.6 + 18.5 = 66.1 min | 352k (228k) | 35.8M | 0 | 488k | 290 s | 6/6/6 (18) | 0/4/4 | 6 of 8 (one partial) | 2 fails, both R3 majors; 0 false fails | 6 of 8 classes; 3 at the same spot as A2 |

**The score still rises one point per attempt** (16 → 17 → 18), so the v1 baseline ends at 6/6/6 after 3 attempts and
245.7 min. R3 marks 8 of 10 R2 issues FIXED and 2 PARTIAL (battery path, form language). It raises 8 new issues: no
blocker, 4 majors, 4 minors. Each fix brought its own new problem: the compliant nip that fixed A2-F4 is the leaf
spring of A3-F2, and the nuts moved out of the battery envelope (A2-F5) now sit in the battery's slide path (A3-F3).

### Time and token sinks (do they recur?)

**A3-T1. Edit-in-place halved the designer (A1-T7, A2-T3 fixed by the agent).** D3 made 9 `Edit` calls on
build_assembly.py (52 B to 3.9 KB each, `D3 0:16:46-0:20:15`) and one 27 KB `Write` of the BOM. It did not rewrite
the 133 KB script. Wall time fell from 82.8 to 41.0 min and output from 443k to 219k tokens. This is the template's
"edit one module, rebuild, check" rule, done without the template on a script that was already mature.

**A3-T2. Upfront thinking shrank but is still 41% of wall (A1-T1, A2-T1).** The first edit came at 16.8 min. Five
generations of 120 s or more total 16.9 min. They were mostly hand geometry that a tool answers:
- `0:04:14`, 216 s: where the L-key elbow lands for the moved pinch bolts. cadcheck `lkey` access answers that in
  11 s after an edit.
- `0:13:55`, 289 s: which way the stud head faces ("I'm puzzling over screw orientation"). This is the A1-F10 class
  again. `asm.fastener(at, into)` fixes the convention.
- `0:16:45`, 159 s: the swept envelope of the pod for the shroud cut. **No cadlib helper exists for this (gap).**

**A3-T3. No cache misses (A1-T4, A2-T4 did not recur).** The longest generation was 290 s, against 1028 s in D2.
That agrees with A2-T4: the misses followed 10-17 min generations.

**A3-T4. An interrupted reviewer lost 6.6 min and its restart redid the work (new).** The user stopped the loop
at 21:31 (R3a's last line is "[Request interrupted by user]"). The workflow resumed and started R3 at 21:38 with
the same journal key. R3a had written `/tmp/mmrev/{list,measure1,lkey,batt}.py`. R3 wrote
`/tmp/mmrev/scripts/{list,measure,…,batt}.py` again from zero: nothing on disk told it what R3a had measured. That cost
34k output tokens and 3.1M cache reads. **Fix (this run):** the reviewer skill and the template's review prompt now
append every measurement to `review/notes.md`, and a restarted reviewer reads it first.

**A3-T5. Reviewer code reading recurs (A1-T8, A2-T6).** R3's time went like this:
- 0:00-1:01: read 17 renders.
- 1:20-6:52: rebuilt in a scratch copy and read checks.py, about 5.5 min.
- 7:42-12:14: 9 measurement scripts.
- 13:09-17:00: 14 renders, 2 of them re-rendered.

Most of the 13 scripts now map to cadcheck blocks:
- `slope.py` → `drop` `flattest_slide_deg`;
- `batt.py` and `battshape.py` → `slide_out`, now with fasteners;
- `enc.py` and `enc2.py` → `stacks` and `distances`.

The 4 chute-width scripts (`chute`, `choke`, `choke2`, `choke_render`: "at least 9.5 mm wide along the candy path")
have **no cadcheck equivalent (gap)**.

**A3-T6. Small failures.** D3 had 3 bash failures: no matplotlib, no skia, and an `AssertionError` from its own
parameter assert, fixed in one edit. R3 had 1 (`__file__` undefined under `--python-expr`). None cost more than a minute.

### Foot-guns (R3), and whether cadcheck catches them

"Before" is cadcheck at `2197aac` with the A3 config (`/tmp/alex3d-a3/cadcheck_before_a3cfg.json`). "After" is this
run (`examples/mm-launcher-a3/cadcheck_summary.json`). The config is `examples/mm-launcher-a3/checks.json`: the A2
config updated from the A3 BOM (sections 0, 4 and 5) and from `build_assembly.py:780-830`.

| ID | R3 issue | Before | After | Needs a declaration? |
|---|---|---|---|---|
| A3-F1 | **Major:** feed may stall near full tilt; last slide 21.0° at tilt 45 and 19.9° at the 46° stop (R3 #1) | pass (29/29 hit; no margin reported) | warn: flattest slide 21.3° at 45 and 20.3° at 46, stall 20 + margin 5 | the slide test exists from A2; the 46° pose is a config line (hard stop from BOM 0) |
| A3-F2 | **Major:** nip-cover leaf spring printed standing up, bending stress across layers (R3 #2) | not checked | fail: beam 85° off the bed, 20.9 MPa > 15 | yes: `flexures` (beam direction, D3's own stress number) |
| A3-F3 | **Major:** battery slides through two adapter nuts from dx 10 to 70 mm (R3 #3) | warn for the wrong reason: "only 1.25 mm to PRT_base_shell"; fasteners were not in the sweep | fail: blocked by `FST_adapter_nut_1`/`_3` at 5 mm | the `slide_out` entry from A2 (BOM 1 #8) |
| - | **Major:** no unifying form language (R3 #4) | - | - | not tool-catchable |
| A3-F5 | Hinge axle threads 2.5 mm into PLA (R3 #5) | warn 2.0 mm | warn 2.0 mm | no. **This was an A2 candidate; R3 confirms it** |
| A3-F6 | Nip range 5.5-10 can't reach the brief's 9-12 and isn't called out (R3 #6) | - | - | not geometric: brief-numbers table (checklist) |
| A3-F7 | 8 mm of bundle visible in a turntable notch at the bonnet foot (R3 #7) | not flagged (6/26 rays, threshold 8) | warn: 8 mm at (-107, -2, 100) on all 4 bundle wires and the bus | no |
| A3-F8 | Battery-bay window shows the adapter, screw tips and nuts (R3 #8) | not checked | partial: warn "FST_adapter_nut_1/_3 visible from outside"; window size not checked | no |

**After this run, 6 of 8 R3 issues produce a fail or warn naming the right objects, with R3's numbers within 0.4°
and 0 mm.** Before, it was 1 of 8 (the hinge warn). Three of the six fire from geometry alone (F5, F7, F8). F1 fires
at tilt 45 with the A2 config as it stands; F3 needs the `slide_out` entry, which A2 already had; F2 needs a
`flexures` entry. The before column has **6 false fails** (A3-V1) and catches no R3 major.

**A3-F7 is also an R2 miss.** The archived A2 blend has the same notch with the same escape counts (probe
`/tmp/alex3d-a3/probe/cab.py` on both blends: 6/26 at (-110, -3, 98)). R2 did not raise it; R3 did. The new rule
flags it on both blends, so this is reviewer noise that the tool removes.

**False fails in the earlier cadcheck on A3 (A3-V1), fixed this run.** Before, there were 6 fails, all false, all
from the new nip mechanism:
- 4 came from sweeping the thumbwheel and its nut as fixed while the stud swings with the backplate. In use they ride
  on the stud. The new `carry` config re-parents them onto `PIV_hood`.
- 2 came from treating the hex-head stud as a screw: "head is inside PRT_hood" and "cannot be driven". It is captive
  in a hex pocket, and the thumbwheel turns. The new `fasteners.captive` config skips seating and access but keeps
  engagement.

Allowing these pairs would have hidden real clearances. The stud-to-slot and stud-to-cover clearances are still
swept. The stud-to-cover clearance is a 0.59 mm warn at overtravel.

**cadcheck bugs found by this attempt (fixed):**
- `slide_out` swept only printed and purchased solids, so a part slid through fasteners unseen. That is the
  A1-F14 class ("checks that skip fasteners") inside this repo's own tool. Pairs already overlapping at rest are now
  listed in `overlapping_at_rest` instead of failing the slide. BVH `overlap` misses a nut wholly inside a part, so
  the rest test uses volume.
- The summary's `warn_list` was cut at 60 entries. A3 has 66 warns, and the cut dropped the two stall-margin warns.
  The list is no longer truncated.
- Stacks compared floats exactly: 0.1 + 0.1 + 0.1 > 0.3 gave a false warn.

**Exposure rule changed (A3-F7).** The 26-ray rule needs 8 escaping rays. A notch shows a cable through a narrow cone,
which 26 rays sample too coarsely. The new rule is "8 of 26, or 10% of 240 directions toward a viewer above or level".
On the A3 notch it gives 8.3 mm, against R3's "about 8 mm". On A2 the same rule:
- sizes R2's bare bus run at 15 mm, against R2's 10 and the old rule's 11;
- flags the A2 candidate feeder-servo lead at (21, -84, 227) at 39 mm. A `cad q render` from (140, -200, 200),
  `/tmp/alex3d-a2p/spot_21.png`, shows that lead on the side of the servo;
- flags two unconfirmed A2 runs at (-38, -26, 252) and (-27, -57, 252). A top-down render shows no cable, so they are
  likely seen from below the plate edge.

Cost: cables went from 1.5 to 5.5 s.

### Recurrence across attempts (adds the A3 column to the A2 table)

| Class | A1 | A2 | A3 | Tool now |
|---|---|---|---|---|
| Payload path never simulated, or no margin | A1-F1 blocker | FIXED by D2's tracer | A3-F1: feeds, but 1° above stall | slide `flattest_slide_deg` + `stall_margin_deg`, hard-stop poses |
| Working condition at the nip | A1-F2 | A2-F4 rigid squeeze | FIXED by a leaf spring, which A3-F2 then breaks | `distances` + `compliant`; `flexures` |
| Fasteners left out of checks, and overclaiming | A1-F3, F10, F14 | A2-F5 | A3-F3: D3's checks test the battery at rest only (R3: "checks.py tests the rest pose only"), and cadcheck's own `slide_out` skipped fasteners | `slide_out` includes fasteners |
| Purchased part vs fasteners | - | A2-F5 (at rest) | A3-F3 (on its slide path) | shank or nut inside BUY; slide_out |
| Screws you can't drive | A1-F4, F11 | A2-F1, F6 | FIXED: L-key 10/10, nip-cover screws reachable | L-key, `service` |
| Thread engagement | - | A2 candidate: hinge 2.0 mm | A3-F5, same screw | engagement warn (since A2) |
| Cables visible | A1-F12 | A2-F8 | A3-F7 (same notch as A2) | viewer-direction exposure |
| Visible hardware | (A 5) | A2-F9 jack nuts | A3-F8 battery-window nuts | stand-off, nut visibility |
| Form language | (A 5) | R2 #10 | R3 #4 | not a tool problem |

### What worked (A3)

- **Small, targeted edits** (A3-T1): 41 min instead of 83, with no regressions in the 8 FIXED items.
- **D3 turned R2's evidence into checks:** an L-key sweep, same-pivot fastener versus purchased parts, feeder index
  geometry, nip spring numbers and pinch-bolt engagement (D3 journal `summary`). Those are what cadcheck had added in
  the A2 run. The designer rebuilt them by hand in checks.py (38 KB, up from 32).
- **R3's slide-path sweep** (`batt.py`: battery in 5 mm steps against every part, BVH) is what cadcheck `slide_out`
  already did, minus fasteners. That difference was the bug.
- **R3 re-ran the designer's tracer and measured the margin, not just the verdict.** That is now a reported number on
  every slide-mode drop row.

### Reviewer quality (A3)

- The anchors held: there was no blocker, so no score was capped. The four majors are 1 F (feed margin), 2 M (leaf,
  battery path) and 1 A (form language). All three scores are 6.
- Every R3 issue cites a measurement or a render path, and R3 reproduced every designer number before repeating it ("all 32
  STLs match byte for byte"). cadcheck agrees with R3 within 0.4° on the slide angles and exactly on the battery
  nuts and the 8 mm cable.
- Noise: A3-F7 existed in A2, and R2 didn't see it. Aesthetics 6 → 6 with the same "kit of boxes" critique, so the
  form-language anchor still decides A.
- R3 rated one item as Function major on a friction estimate ("roughly 19 to 24 deg"). The tool now reports the
  margin, but the right stall angle for a sugar shell on PLA is a physical test, not a number either agent can measure.

### Why not the existing code (A3 additions)

- **D3's checks.py battery check:** rest pose only (R3 #3). cadcheck's `slide_out` existed, but it skipped fasteners.
  The fix is about 10 lines in the existing check, not a new one.
- **`allow` instead of `carry`/`captive`:** allowing the 6 nip pairs would also silence the thumbwheel-and-nut sweeps
  against the cover and the seat land (0.42 and 0.59 mm warns, and the seat stop). `carry` (about 10 lines) keeps them.
  `captive` (about 8 lines) is narrower than `allow`: it keeps engagement and nut pairing.
- **Exposure:** the old 26-ray rule was tuned on A2 (bare 10-12, grooved 4-7). The notch scores 6, inside the
  "grooved" band, so no threshold on 26 rays separates it. The dense viewer pass runs only on samples that are not
  enclosed.
- **Flexures:** nothing in cadcheck or cadlib reads print orientation against load. `print_rot` was already on every
  part for bed fit and STL export, so the check reuses it (about 40 lines).

### Verification of this run

- `tools/verify_all.sh`: 36/36 passed (`/tmp/alex3d-verify/verify_all.log`). That adds an A3 regression: 7 patterns,
  plus "exactly 2 fails, no nip-mechanism fastener or fail findings, feeder index 2 windows over [0, 30, 0, -30, 0]".
- A1 is unchanged. A2 still gives exactly the 15 R2-confirmed fails after the slide and exposure changes. The A2
  drop assertion now counts fails only, because A2 also gets the tilt-45 margin warn (same geometry). The A2 bus
  pattern changed from 11 to 15 mm with the new exposure rule.
- The live v1 blend (frozen at A3) with the A2 config gives 10 fails, all config mismatches. The A3 config is the
  right one for it.

---

## v2 Attempt 1 (harvested 2026-10-25; the first attempt that used these tools for real)

Inputs: the 7 attempt-1 entries in `V2WF/journal.jsonl` and their transcripts, plus `HW2/renders/attempt-1/`:
progress.md, cadcheck.json, review.md, review.json, review/, 16 PNGs and `cg_grid.txt`. The blend V2R1 reviewed
(`/tmp/rv1/model.blend`, md5 `d952d17f…`) is archived as `examples/mm-launcher-v2a1/`. Plan #2 and build #2 had started
and are not ingested.

**The tools the agents used were `2197aac`** (progress.md line 1: "tools: 2197aac"). That is before the A3 revision
commit `ca81683`, so v2 A1 had no `carry`, `captive`, `flexures` or fastener-aware `slide_out`. Attempt 2 runs on
`6b62667`, which has those. This run's fixes reach **v2 attempt 3**.

### Per-agent cost (`cc_transcript.py workflow V2WF`)

| Agent | Wall | Model | Tools | Output tok (thinking) | Cache read | Peak ctx | First edit | Longest gen | cad runs (failed) | Images |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 plan | 20.1 | 19.8 | 0.3 | 118k (68k) | 4.7M | 226k | 12.4 min | 176 s | 4 (1) | 0 |
| B1-base | 27.3 | 25.3 | 2.0 | 149k (112k) | 11.2M | 303k | 17.7 min | 307 s | 16 (0) | 4 |
| B1-pan | 30.2 | 26.7 | 3.5 | 151k (109k) | 11.2M | 283k | 15.2 min | **765 s** (cache miss, 174k re-written) | 22 (5) | 2 |
| B1-launcher | 32.9 | 27.1 | 5.8 | 156k (102k) | 14.9M | 348k | 8.6 min | 231 s | 20 (4) | 1 |
| B1-feeder | 46.2 | 34.8 | 11.4 | 188k (149k) | 13.1M | 331k | 23.8 min | 446 s (cache miss, 157k) | 16 (3) | 3 |
| F1 finish | 16.1 | 9.9 | 6.2 | 61k (15k) | 8.3M | 191k | 0.5 min | <120 s | 25 (2) | 13 |
| V2R1 review | 14.7 | 13.6 | 1.1 | 79k (45k) | 6.3M | 196k | - | <120 s | 18 (0) | 10 |

**Against the v1 baseline:**

| | v1 A1 | v1 A2 | v1 A3 | **v2 A1** |
|---|---|---|---|---|
| Wall (design + review) | 82.6 min | 97.0 | 66.1 | **187.5** (plan 20.1, builds 136.6, finish 16.1, review 14.7) |
| Output tokens (thinking) | 481k (327k) | 520k (354k) | 352k (228k) | **902k (601k)** |
| Cache read | 26.8M | 37.9M | 35.8M | **69.7M** |
| Peak context (any agent) | 522k | 698k | 488k | **348k** |
| Longest generation | 1001 s | 1028 s | 290 s | 765 s |
| F/M/A (sum) | 5/6/5 (16) | 6/5/6 (17) | 6/6/6 (18) | **7/7/6 (20)** |
| Issues B/M/m | 18 | 1/3/6 | 0/4/4 | **0/5/7** |
| cadcheck at hand-off | (none) | (none) | (none) | 0 fails, 34 warns |

v2 A1 scores **2 points above v1's final attempt**, starting from scratch on a changed brief (jar hopper, test-rig
launcher), with no blocker. It also took 2.3 times v1 A1's wall time and 1.9 times its output tokens. Peak context
fell by a third. The aim was fewer, cheaper attempts, and only the first half held: one attempt beat three, but that
one attempt cost 76% of v1's whole three-attempt total (245.7 min).

### Time and token sinks

**V2A1-T1. Four builders in series: 136.6 of 187.5 min (new; template shape).** The template runs builders one
after another, because they share one `model.blend`. Each builder is a fresh agent. Before its first edit, each one
re-read SKILL.md, api.md, checks-config.md, checks.json, the brief, the design log and progress.md, about 25-30k
tokens and about 1 min of calls each. The builders spent **65.3 min in total before their first edit**: base 17.7,
pan 15.2, launcher 8.6, feeder 23.8. Most of that was hand geometry against v1 coordinates:
- B1-pan `0:13:38`, 765 s and 72k thinking tokens: re-deriving v1 journal, lug and servo positions to map them onto
  the IF_* frame.
- B1-base `0:14:35`, 307 s: the MotorGo world envelope and USB niche.

The rest was tool source (T2). A first attempt builds every subsystem from zero, so later attempts should cost less.
**Fix (template, opt-in):** `parallel_builds`. Builders run at once, each with `cad build -- --out /tmp/cadloop-<sub>`,
and their new rows go to `checks.d/<sub>.json` (run with `--overlay`). The planner owns params.py, and the finisher
merges. Wall time for an all-subsystem attempt would drop from 136.6 to about 46 min (the slowest builder). This is
untested in a live run, so it is off by default. The v2 script is its own copy, so this needs the user to adopt it.

**V2A1-T2. Builders read tool source for answers the docs lacked (new).** There were 30+ source reads across 7 agents
(fork scan, timestamps in `/tmp/alex3d-v2a1/`):
- bench/merge semantics in assembly_order: 4 agents (B1-base `0:07:12`, B1-pan `0:14:57`, B1-feeder `0:17:21`, P1
  `0:15:27`). B1-feeder `0:20:37` then spent 186 s restructuring steps 10a/10b because "bench-to-bench merging isn't
  supported";
- `cad q section` syntax: 4 agents;
- screw_hole/fastener semantics: 3;
- slide semantics: 2;
- stability/pose_grid: 2.

**Fixed:** checks-config.md now has an assembly-order semantics paragraph, a "Running subsets" section and the
contact-fit, stability, drop-coverage and warn-triage rules. api.md has a screw+hole+nut example and the `cad q
section` command line. cadcheck now supports nested bench merges (`lands_in`, any depth). SKILL.md says to read the
reference before the source.

**V2A1-T3. `check_distances` crashed on a not-yet-built object (KeyError, `cadcheck.py:1456` at 2197aac).** It hit P1
`0:16:46` and B1-pan `0:28:13`. The workaround in progress.md "Tool issues" was to drop distances with `--only` in
every builder run (12 runs), so every distances row went unchecked until the finisher. **Fixed:** `present()` turns a
missing name in distances, index or drop rows into one fail ("not in the scene; row skipped") and the run continues.
Regression: verify 4d, "missing object".

**V2A1-T4. `cad` wrapper argument bugs (3 hits).**
- `cad check m.blend c.json --only X` took `--only` as the output path, so the filter was lost. B1-base `0:17:35`
  deleted a 44 KB file named `./--only`; B1-feeder `0:35:32` found a 130 KB one.
- `cad build x.py -- --render` passed a doubled `--`, and Blender tried to open `blender/--` (B1-feeder `0:37:02`).
  SKILL.md documented exactly that form.
- `cad q section X ...` gave `ValueError: substring not found` on an uppercase axis (B1-pan `0:28:55`, B1-launcher
  `0:31:50`, B1-feeder `0:44:27`).

**Fixed:** flags in the CONFIG or OUT position are no longer swallowed; a leading `--` after the build script is
dropped; the axis is lower-cased. `cad build` exports `CAD_SKILL` from its own checkout, and the template no longer
defaults to the unpinned path (P1 had to repoint it: progress.md "Tool issues").

**V2A1-T5. `render.section` turned closed solids inside out (EXACT boolean).** PRT_jar_valve, PRT_base_shell and
PRT_journal_plate flooded the sections. F1 bisected it from `0:05:17` to `0:07:11`, with 7 extra image reads, and
wrote `HW2/blender/tools/section_precut.py` to pre-cut with `geom.csg` (Manifold). V2R1 reused that script.
**Fixed:** `render.section` uses Manifold on closed solids. Reproduced on the archive:
- at HEAD the x=21 section is 95% one cut colour (`/tmp/alex3d-v2a1/sec_x21_old.png`);
- after the fix, the largest non-background colour is 13% (`sec_x21.png`).

Regression: verify 4d, "section x21".

**V2A1-T6. The reviewer hand-built checks.json copies (5.5 of 14.7 min).** V2R1 spent `0:01:53-0:04:44` and
`0:09:51-0:12:18` writing `checks_review{,2,3,4,5}.json` by emptying other sections. **Fixed:** `cad check ...
--overlay rows.json` (repeatable) appends rows (allow and fits rules go first), and `--overlay-only` replaces the base
rows of the named sections. The reviewer skill and template now say to keep added rows in
`review/review_rows.json`, which the next planner merges.

**V2A1-T7. `cc_transcript.py` counted 0 Blender runs for v2 agents.** It only matched the Blender binary. **Fixed:**
it now matches `cad build|check|q|sheet` through any path or variable. The counts in the table above come from the
fixed tool: 121 cad runs, 15 failed.

### Issues V2R1 raised, and what the tools did with them

"At hand-off" is the designer's cadcheck at 2197aac (`HW2/renders/attempt-1/cadcheck.json`, 0 F / 34 W). "Now" is
this run on the archive with the designer's own config (`/tmp/alex3d-v2a1/final_designcfg.json`).

| ID | V2R1 issue | At hand-off | Now (designer config) | Why it got through |
|---|---|---|---|---|
| V2A1-F1 | **Major:** nip has no hard stops; drop stalls from a 7.4 mm gap; hood hits the body past the minimum (A1-01) | not flagged: drop rows held PIV_hood at home | **warn:** "the payload path touches ['PRT_hood'], which moves on PIV_hood (-6.51..1.09), but the test holds PIV_hood at home". With both ends added (`overlay_drop.json`): **fail**, 18/31 stall at tilt 0 and 31/31 at tilt 22.5 and 46 | coverage gap: new drop coverage warn |
| V2A1-F2 | **Major:** setting the gap needs the nip cover off, which comes off only at tilt 45 (A1-02) | not flagged | not flagged: the service op has no `remove` list (its title says "nip cover off") | config gap. New warn when an op removes parts without a matching slide_out; checklist |
| V2A1-F3 | **Major:** Ø15 pocket admits two edge-on candies (A1-03) | - | - | **no payload-fit check (gap)**: V2R1 wrote `review/add_mm_probe.py` |
| V2A1-F4 | **Major:** feeder servo swap needs a feeder teardown (A1-04) | not flagged: no service row | fails once V2R1's row exists | config gap: BOM claim without a row. Checklist and template already ask; not done |
| V2A1-F5 | **Major:** 0.94 mm crown wall at the self-tap pilots (A1-05) | **warn** (thin wall 0.94) | warn | **an unread warn.** New `accepted_warns` and untriaged count; finish prompt and SKILL "done" rule |
| V2A1-F6 | Pod drop-in only at tilt 10-35 (A1-06) | not flagged | not flagged | the assembly-order merge has no insertion sweep; needs a slide_out row (checklist) |
| V2A1-F7 | Magnet stack 0.40 > 0.30 (A1-07) | **warn** | warn | an unread warn (as F5) |
| V2A1-F8 | Knife edges and an undeclared 48 mm bridge (A1-08) | **warns** | warns | an unread warn (as F5) |
| - | Bare gate sheet, feeder form language, colours (A1-09, 10, 12) | - | - | not tool-catchable (A1-09's open state is a modelling gap: no PIV_gate) |
| V2A1-F11 | PCB visible through a base-wall notch (A1-11) | - | - | **exposure covers cables and nuts only, not PCBs (gap)** |

V2R1 marked 9 of 12 issues `tool_catchable`. **At hand-off, cadcheck had already flagged 3 of them (F5, F7, F8),
all as warns the designer passed on.** With this run's tools and the designer's own config, 4 of 12 are flagged (F1
added). The rest need a row the designer did not write (F2, F4, F6) or a check that doesn't exist (F3, F11). The
pattern differs from v1. There, the tools lacked checks. Here, the checks existed, and **warns and missing rows** let
issues through.

**Config disputes (8), and what each became:**
1. A gate slide that ignores its own guide: config.
2. A service op with no pose: new warn plus checklist.
3. Drop at home hood only: new warn.
4. Distances at home only: checklist.
5. No feeder-servo service row: checklist.
6. Step 7 needs a pose: checklist.
7. **V2A1-V4. Contact fits hide journals:** fixed with `contact_normal`. On the archive with `overlay_fits.json`,
   post_R x journal_plate is now measured at 0.142 mm and shell x turntable at 0.258 mm. Before, neither pair had a
   clearance row.
8. **Stability evaluated 1 pose:** fixed (V2A1-V3).

### cadcheck bugs this attempt exposed (fixed)

- **V2A1-V2. `pose_grid` thinning dropped the in-range limits.** `thin()` kept the list ends, which are the
  overtravel samples. In a two-joint group thinned to 5 samples per joint, tilt -3 and 46 were never visited, so a
  collision at a hard stop would have shown only as an overtravel warn. Now `thin(keep=...)` always keeps lo, hi and
  both overtravel samples. On v2 A1 this changed nothing (the same 34 warns plus 2 new ones, F1 and a cable spot).
  Interference went from 40 to 62 s, with 3-joint groups at 64-75 poses instead of 36-45.
- **V2A1-V3. Stability evaluated 1 pose.** `pose_grid(cap=27)` thinned 5 joints to 3 samples, 2 of them overtravel,
  and stability skips overtravel, so only the all-midpoint pose survived. Continuous pan was excluded too. F1 wrote
  its own 64-pose `cg_grid.py` (worst 29.8°). Now every driver joint is sampled at lo/home/hi, and continuous joints
  every 45°. Local centroids are computed once, so 864 poses take 1.0 s. Worst: 31.2° at pan -90, tilt 45, hood
  -6.5, feeder -60. The 1.4° gap to F1's number comes from mass assumptions; F1 used a full jar.
- **V2A1-V4. Contact fits** (dispute 7): see above.
- **check_drop** crashed when a slide ray ended on nothing (`None in bpy.data.objects` raises a TypeError). This run's
  first version of the coverage warn hit it on the demo; found by verify_all.

### What worked

- **The modular project.** params.py with IF_* interfaces, one module per subsystem, and progress.md lines after
  every build plus check made a 4-subsystem first attempt resumable. Peak context was 348k, against 522-698k in v1.
- **cadcheck as the builders' loop.** 121 cad runs and 0 fails at hand-off. Every V2R1 measurement re-ran with the
  same tool: V2R1 had 18 cad runs and 0 failures, against R1's hand scripts. Its review took 14.7 min, the shortest
  so far, with 10 images.
- **progress.md "Tool issues".** The planner prompt asked agents to log tool problems instead of stopping. That
  section is where T3 and the CAD_SKILL bug were found. Keep it.
- **The reviewer issue cap** (at most 10 B/M and 8 minors, folded): 12 issues, each with one fix and a number.

### Reviewer quality (V2R1)

- Every issue cites a cadcheck row, a `cad q` line or a render, and there are 8 concrete config disputes. The anchors
  were applied as written: F 7 for "3 or more majors"; M rounded down from 8; A capped at 6 by "unfinished element in
  a hero view".
- V2R1 found F1, F2, F4 and F6 by **adding rows** the designer had not written. That is the reviewer doing the
  designer's coverage work, which is why the template now asks the planner for adjuster-end rows and merges
  `review_rows.json`.
- V2R1 accepted the designer's cg_grid as evidence (dispute 8) instead of re-running it. That was reasonable with a
  1-pose tool; the tool now covers it.

### Why not the existing code (v2 A1 additions)

- **Overlay vs `--only` and hand copies:** `--only` filters checks, not rows. The merge loop for DEFAULTS existed, and
  `--overlay` reuses it (about 15 lines). Measured: V2R1 spent 5.5 min on copies.
- **Stability sampler vs `pose_grid`:** `pose_grid` is tuned for interference, which wants overtravel. Stability wants
  limits and continuous joints. Reusing it was the bug, and a separate 20-line sampler fixes it.
  `centroid_vol` is reused, just called once per part.
- **`contact_normal` vs splitting the rule:** rules match object pairs, and the thrust face and journal are the same
  two objects, so no glob separates them. Filtering by face normal in the existing overlap and min_dist path is
  about 35 lines.
- **Section:** `geom.csg` (Manifold) already existed, and F1's workaround used it. The fix picks the solver per
  object in `render.section` (3 lines). F1's pre-cut script is no longer needed.
- **Drop coverage:** this reuses `slide_trace`, `joint_chain` and `drivers`. The only addition is face-to-object
  bookkeeping in `scene_bvh` (`owner()`).
- **Parallel builds:** the sequential loop is the prior art, and its cost is measured: 136.6 min for 4 builders. The
  change is about 20 template lines plus `--out` in the project template. Its benefit is unmeasured until a run uses
  it.

### Still open (gaps)
- No payload-fit check, such as two candies in a pocket (F3). V2R1's probe is `HW2/renders/attempt-1/review/add_mm_probe.py`.
- Exposure doesn't cover PCBs or other purchased internals (F11).
- No insertion sweep for an assembly merge step (F6); this needs a slide_out row today.
- Missing-row problems (F2, F4, F6) are config completeness, which no tool can force. The levers are the checklist,
  the planner prompt and review_rows.json.

### Verification of this run
- `tools/verify_all.sh`: 45/45 passed (`/tmp/alex3d-verify.log`). The 9 new tests: template `--out`; `cad check`
  argument parsing; v2 A1 (4 patterns, plus "exactly the 3 open-end stall fails, journals measured, stability over 864
  poses"); the missing-object row; the x=21 section colour test.
- A1, A2 and A3 are unchanged after the `pose_grid` and stability changes: still 7 patterns, exactly 15 fails, and
  exactly 2 fails.
- The template dry run passes both sequential and `parallel_builds`. `parallel_builds` has not been tried in a live
  run.

---

## v2 Attempt 2 (harvested 2026-10-25)

Inputs: the 9 attempt-2 entries in `V2WF/journal.jsonl` (lines 15-32) and their transcripts, plus `HW2/renders/attempt-2/`:
progress.md, cadcheck.json, review.md, review.json, review/ (notes.md, lentils.py, three review cadchecks), 18 PNGs and
`cg_grid.txt`. The blend V2R2 reviewed (`/tmp/rv2/model.blend`, md5 `de54b968…`, the same as `HW2/blender/model.blend`
at 03:10) is archived as `examples/mm-launcher-v2a2/`, with the designer's checks.json and `overlay_v2a2.json` (the rows
V2R2 showed were missing). Plan #3 had started (0.7 min) and is not ingested.

**The tools were `6b62667`** (progress.md line 1), before the v2 A1 revision commit `f039205`. So v2 A2 had no
`--overlay`, `accepted_warns`, missing-object handling, drop coverage warn, `contact_normal` or stability sampler.
Problems those fix are attributed to the pin below, not counted as new. This run's fixes reach **v2 attempt 4**; v2 A3
runs on `f039205`.

### Per-agent cost (`cc_transcript.py workflow V2WF`)

| Agent | Wall | Model | Tools | Output tok (thinking) | Cache read | Peak ctx | Longest gen | cad runs (failed) | Images |
|---|---|---|---|---|---|---|---|---|---|
| P2 plan | 9.8 | 8.0 | 1.8 | 41k (22k) | 2.7M | 141k | <120 s | 5 (0) | 0 |
| B2-params | 6.7 | 5.1 | 1.6 | 24k (9k) | 2.4M | 92k | <120 s | 5 (0) | 0 |
| B2-pan | 6.3 | 2.2 | 4.2 | 10k (2k) | 1.0M | 65k | <120 s | 4 (1) | 0 |
| B2-launcher | **45.0** | 32.5 | 12.6 | **177k (133k)** | 14.8M | 340k | 291 s | 25 (0) | 4 |
| B2-feeder | 33.6 | 21.9 | 11.7 | 109k (73k) | 9.2M | 222k | 159 s | 24 (0) | 0 |
| B2-base | 10.6 | 5.5 | 5.1 | 30k (16k) | 2.2M | 92k | <120 s | 8 (0) | 2 |
| B2-finish | 12.2 | 6.5 | 5.7 | 37k (10k) | 3.7M | 139k | <120 s | 11 (0) | 6 |
| F2 finish | 7.3 | 2.4 | 5.1 | 13k (2k) | 1.0M | 73k | <120 s | 4 (0) | 2 |
| V2R2 review | 18.5 | 16.3 | 2.2 | 83k (45k) | 8.7M | 234k | <120 s | 7 (0)¹ | 11 |

¹ V2R2 ran most measurements through its own `/tmp/rv2/q` wrapper, which the extractor doesn't count.

**Against the baseline and v2 A1:**

| | v1 A1 | v1 A2 | v1 A3 | v2 A1 | **v2 A2** |
|---|---|---|---|---|---|
| Wall (design + review) | 82.6 min | 97.0 | 66.1 | 187.5 | **150.0** (plan 9.8, builds 114.4, finish 7.3, review 18.5) |
| Output tokens (thinking) | 481k (327k) | 520k (354k) | 352k (228k) | 902k (601k) | **524k (312k)** |
| Cache read | 26.8M | 37.9M | 35.8M | 69.7M | **45.6M** |
| Peak context (any agent) | 522k | 698k | 488k | 348k | **340k** |
| Longest generation | 1001 s | 1028 s | 290 s | 765 s | **291 s** |
| F/M/A (sum) | 5/6/5 (16) | 6/5/6 (17) | 6/6/6 (18) | 7/7/6 (20) | **8/8/9 (25)** |
| Issues B/M/m | 18 | 1/3/6 | 0/4/4 | 0/5/7 | **0/2/6** |
| cadcheck at hand-off | - | - | - | 0 F, 34 W | **0 F, 44 W** |
| cad runs (failed) | - | - | - | 121 (15) | **93 (1)** |

v2 A2 is the best-scoring attempt so far (25 against v1's best of 18), and it gained 5 points in one revision where v1 gained 1
per attempt. It cost 20% less wall time and 42% fewer output tokens than v2 A1, but still 1.5 to 2.3 times a v1
attempt. The two v2 attempts total 337.5 min, against 245.7 min for all three v1 attempts.

### Time and token sinks

**V2A2-T1. One builder was 30% of the attempt.** B2-launcher took 45.0 of 150.0 min and 177k output tokens: two passes
on the nip (min-gap stop pad, stop sleeve, leaf-lift joint split, bay relief, finger slot). Its long generations were:
- `0:06:46`, 187 s: reading cadcheck's `contact`/`carry`/`vol_tol` code to decide how to declare the stop contacts;
- `0:11:41`, 291 s: nip geometry (leaf lift against stop positions).

The feeder took 33.6 min, also over two passes. The small builders were cheap: params 6.7, pan 6.3, base 10.6. Builders
were still in series (114.4 min); the v2 script has not adopted `parallel_builds`, so it is still unmeasured. In a revision
attempt only two builders were long, so parallel builds would save about 35 min here, against about 90 in A1.

**V2A2-T2. Tool source reads, again: about 44 across 9 agents.** 8 of 9 agents read the first 30-80 lines of `cadq.py`
for usage, because `cad q` filtered its own help out: the wrapper passes only `CADQ` and `cadq:` lines, and the usage
was a bare `sys.exit(__doc__)`. The rest were cadcheck semantics (contact and carry, `pose_grid`, `assembly_order`,
`ray_gap`, slide, service, the parts wall/overhang code). Most of those are documented at `f039205`, which the pin did not
have yet. **Fixed:** `cad q` alone prints the command list; a command with missing arguments prints its own usage line
instead of `IndexError` (B2-pan `0:03:01`, `cad q model.blend ray`); api.md has a `cad q` section.

**V2A2-T3. Hand stubs to import project modules without Blender.** B2-launcher `0:00:22` (`No module named 'bpy'`)
wrote `/tmp/a2stub/cadlib/__init__.py` so it could run `launcher_geom.report()` from plain python3. B2-feeder `0:12:20`
hit `No module named 'cadlib'` and then `'bmesh'`. **Fixed:** `cad py -c "..."` or `cad py script.py` runs Python inside
Blender, with bpy, cadlib, `./` and `./parts` on the path. Verified: `launcher_geom.report()` runs on a copy of the v2
project.

**V2A2-T4. Claims no row could hold** (progress.md "Tool issues"):
- "Line of sight from outside to a printed part is clear": the A1-02 finger reach was proved with 9 hand `cad q ray`
  lines plus a section. **New `sightlines` section:** origins, a direction in a joint frame, poses, and the first hit
  that must match.
- "A slide must be blocked past X": a blocked slide was always a fail, so the gate's open stop was a section. **New:**
  `slide_out` with `"expect": "blocked"`, `blocked_by` and `at_mm`.
- `cad q ray --pose` takes world coordinates, so a ray from a pod point at tilt 45 was transformed by hand. **New:**
  `cad q ray ... --frame PIV_tilt`. On the archive it gives PRT_nip_wheel at 14.4 at tilt 45, which matches the
  designer's hand-transformed ray.
- No prismatic joint in cadlib, so the gate's open state can't join the interference sweep: **still open.** A
  `slide_out` row covers the open position.
- The `distances` KeyError workaround (V2A1-T3) was still in use: this is the pin, fixed at `f039205`.

**V2A2-T5. cadq argument errors (3).** V2R2 `0:11:07` and `0:11:13` passed `--lentil 21,36,131.3 0,0,1`, which is the
form the help showed, and got `ValueError` twice. **Fixed:** the help shows `--lentil X,Y,Z[:NX,NY,NZ]`, and a bare point
defaults the normal to +Z.

### Issues V2R2 raised, and what the tools did with them

"At hand-off" is the designer's cadcheck at `6b62667` (`HW2/renders/attempt-2/cadcheck.json`, 0 F / 44 W). "Now" is
this run on the archive, with the designer's own config (`/tmp/alex3d-v2a2/main_designcfg.json` before this run's
additions, `verify 4e` after).

| ID | V2R2 issue | At hand-off | Now (designer config) | Why it got through |
|---|---|---|---|---|
| V2A2-F1 | **Major (A2-01):** below a 6.1 setting the leaf runs out of travel before a 7.0 candy on 0.5 tape passes (6.685 bare gap at full lift at the min stop). The declared lift limit is not a real stop: the stud is 2.36 clear there, and the thumbwheel hits the cover at about -2.1° | not flagged | **warn:** the drop path touches PRT_hood, "which moves on PIV_nip_lift (-1.49..0), but the test holds PIV_nip_lift at home" (2 rows) | config gap: no full-lift distances row, no hard-stop row. The rigid-squeeze warn fired only on V2R2's row. SKILL and checklist now ask for both |
| V2A2-F2 | **Major (A1-03, recurring from V2A1-F3):** the Ø14.4 pocket blocks a 13 x 7 edge-on pair by a hair and seats 12.5 x 6.5 | - | **fail with a row:** `payload_fit` pair at 12.5 x 6.5 seats, 0.14 mm short; 13 x 7 blocked with 0.11 mm spare (warn); a 13.5 x 7.5 flat candy fits with 0.45 | **no check existed (2nd attempt running).** V2R2 wrote `review/lentils.py`; B2-feeder copied V2R1's probe. New `payload_fit` |
| - | Minor (A1-08): 1.12 wall at the widened bay; 171 mm² overhang on the nip cover | **warns** | warns | unread warns. The pin had no `accepted_warns`; v2 A3 does |
| V2A2-F4 | Minor (A2-02): only the phase leads have a lead length; the pan U-loop slack isn't modelled | not flagged | **warn:** "10 cables have no lead length" | config gap. New warn |
| V2A2-F5 | Minor (A2-04): step 10a says M2 x 4 over M2 x 8 screws; no flexures row for the leaf; (claimed) two parts in no step | not flagged | **warns:** the label mismatch; "PRT_nip_leaf is named compliant ... but has no flexures row". The "no step" part is **wrong**, see V2A2-R1 | config gaps. New `assembly` audit and compliance warn |
| V2A2-F6 | (in A2-04) the fixed y37 nip ray slips past the hood lip at full lift: 14.18 against a real gap of about 8.3 | not flagged | **warn:** "ray gap 14.18 ... much wider than the nearest gap 7.06" (with V2R2's row) | ray artefact. New ray-vs-nearest warn |
| - | Minor (A2-05): flattest slide 32.8° at gap 5.3 and tilt 46 (4.8° over the stall, rule 5°) | **warn** | warn | unread warn (as A1-08) |
| - | Minors A1-09 (gate detents), A2-03 (finger slot ergonomics) | - | - | not tool-catchable. A2-03's rim height is a `sightlines` row with several origins |

V2R2 marked 6 of 8 issues `tool_catchable`. **At hand-off, cadcheck flagged 2 of them (A1-08 and A2-05), both as unread
warns again.** With this run's tools and the designer's own config, 5 of 6 are flagged: F1 as a lead warn, F4, F5, F6
and the two warns. F2 needs a `payload_fit` row; the check now exists and fails on this model.

**Recurrence:** the edge-on-pair pocket (V2A1-F3 then V2A2-F2) is the only issue that recurred, and it was the one gap
the v2 A1 run left open. The adjuster-end lesson (V2A1-F1) half carried over: the designer tested both hood stops, but
not the second adjuster joint (leaf lift) that the plan added.

**Config disputes (7), and what each became:**
1. fits hood x thumbwheel `contact: true` is unnecessary and could hide a rub: config.
2. The PIV_nip_lift limit doesn't match the geometry: hard-stop distances row (SKILL, checklist).
3. No full-lift bare-gap row; the y37 ray artefact: ray-vs-nearest warn plus checklist.
4. drop_tests lack tilt -3 and stops x tilt 45: the drop coverage warn (`f039205`) catches the stop half.
5. No flexures row for the leaf: compliance warn.
6. Parts in no step, 10a label: label warn; the "no step" half is wrong (V2A2-R1).
7. Shell x turntable contact still hides the R20 journal: fixed at `f039205` (`contact_normal`, V2A1-V4); the pin lacked it.

### What worked

- **The planner wrote the rows before the geometry.** P2 wrote v2-A1-NN rows for 9 of 12 issues and ran them on the
  attempt-1 model: 12 F / 36 W. Builders then drove them to 0 F, and V2R2 rated 9 of 12 previous issues FIXED and 3
  PARTIAL. The template's planner prompt now asks for this explicitly.
- **A separate params work item** (B2-params, 6.7 min) made the interface change before any builder ran.
- **Tool friction fell:** 1 failed cad run of 93, against 15 of 121 in v2 A1, mainly from the `f039205`-era fixes to
  `cad` arguments that `6b62667` already had.
- **The reviewer re-measured instead of trusting:** a full-lift sweep at 8 hood settings, lentil pairs at 3 sizes, and
  the first contact on the lift joint. Each major has a number and a fix with dimensions.

### Reviewer quality (V2R2)

- **V2A2-R1. A false config claim.** V2R2 said PRT_nip_stop_sleeve and FST_valve_* were in no `assembly_order` step
  (review.json A2-04, dispute 6, and the M anchor: "not 9 because ... 2 parts are in no assembly step"). Both are listed:
  the sleeve last in step 6e, and FST_valve_* in step 12. cadcheck's own `unordered_solids_assumed_present` was
  `['BUY_battery']`. The claim fed a manufacturability anchor, so it may have cost a point. **Fixed:** cadcheck reports
  `assembly.step_of` and `in_no_step`, and the reviewer skill and checklist say to cite them.
- V2R2 hand-copied checks.json into `checks_review.json` (36 KB) instead of an overlay. That is the pin again: `--overlay`
  is from `f039205`.
- The 7/7/6 to 8/8/9 jump is mostly aesthetics (+3): the colour map, the finished gate tab, port-only cut-outs and the
  transmissive jar. Every anchor sentence cites a number.

### Why not the existing code (v2 A2 additions)

- **payload_fit vs a probe script or `cad q inside`:** `inside` tests points, and a pair of candies in a cylinder is a
  volume question. The three probe scripts (V2R1 `add_mm_probe.py`, B2-feeder's copy, V2R2 `lentils.py`) each built
  lens meshes and read `cad q dist` by hand. The new check reuses `inter_volume` (Manifold) and `frame_point`; the new
  parts are the probe mesh, the placement and a bisection for the margin (about 120 lines). It reproduces V2R2's
  numbers: 12.8 x 6.8 just touching (here 0.14 short at 12.5 x 6.5, so 12.78 x 6.78), 13 x 7 overlapping.
- **sightlines vs drop_tests with `hit`:** a drop test emits a disc of rays along gravity and checks a landing window. A
  finger or view ray needs explicit origins, any direction and a first-hit name. It reuses `scene_bvh`/`owner()` (about
  45 lines).
- **slide expect vs a new stop check:** the slide sweep already finds the blocker and the distance; the expectation adds
  10 lines.
- **`cad py` vs a cadlib that imports without bpy:** cadlib is bpy throughout. A Blender run takes 0.7 s, so running
  Python inside it is 2 lines in the wrapper.
- **Assembly audit and config warns:** the step map already existed inside `assembly_present`. The label, cable-lead and
  compliance warns read data already in the scene props (`fst_d`, `fst_len`) and config.

### Still open (gaps)
- No prismatic joint in cadlib (the gate open state is out of the interference sweep).
- The full-deflection gap of a compliant part is config: nothing makes the designer write the row. The drop coverage
  warn names the held joint, and the SKILL, checklist and planner prompt ask for it.
- Exposure doesn't cover PCBs (V2A1-F11); there is no insertion sweep for assembly merges (V2A1-F6).
- `parallel_builds` is still untested live.

### Verification of this run
- `tools/verify_all.sh`: 54/54 passed (`/tmp/alex3d-verify.log`); A1, A2, A3 and v2 A1 are unchanged. The 9 new tests: v2 A2 designer config (4 new warns, still 0 fails); the overlay
(payload_fit fail at 12.5 x 6.5, 0.14 short; 13 x 7 warn at 0.11; flat 13.5 x 7.5 fits; sightlines; the gate stop at
52.5; the ray artefact; two planted rows fail); `cad q` help; `cad q ray --frame`; `cad py`.

---

## v2 Attempt 3 (harvested 2026-10-25)

Inputs: the 8 attempt-3 agents in `V2WF/journal.jsonl` (lines 34-49) and their transcripts, plus `HW2/renders/attempt-3/`:
progress.md, cadcheck.json, review.md, review.json, review/ (notes.md, review_rows.json, cadcheck_review.json, 3 PNGs).
The blend V2R3 reviewed (`/tmp/rv3/model.blend`, md5 `dd734037…`, the same as `HW2/blender/model.blend` at 05:42) is
archived as `examples/mm-launcher-v2a3/`, with the designer's checks.json, manifest.json, BOM and `overlay_v2a3.json` (the
reviewer's rows rewritten with this run's features). Plan #4 had started (1.0 min) and is not ingested.

**The tools were `f039205`** (progress.md line 1): the first attempt with `--overlay`, `accepted_warns`, the drop
coverage warn, `contact_normal` and missing-object handling, but not `a20a4d7` (`payload_fit`, `sightlines`, slide
`expect`, `cad py`, the `cad q` help fixes). Plan #4 moved the pin to `a20a4d7`, so **this run's fixes reach v2 attempt 5.**

### Per-agent cost (`cc_transcript.py workflow V2WF`)

| Agent | Wall | Model | Tools | Output tok (thinking) | Cache read | Peak ctx | Longest gen | cad runs (failed) | Images |
|---|---|---|---|---|---|---|---|---|---|
| P3 plan | 22.2 | 16.5 | 5.7 | 72k (46k) | 5.2M | 208k | 129 s | 5 (0) | 0 |
| B3-params | 6.6 | 4.2 | 2.4 | 18k (5k) | 1.5M | 71k | <120 s | 2 (0) | 0 |
| B3-launcher | 29.6 | 19.6 | 9.9 | 103k (72k) | 9.6M | 223k | 203 s | 20 (0) | 2 |
| B3-feeder | 24.6 | 13.4 | 11.3 | 74k (50k) | 4.9M | 169k | 182 s | 14 (1) | 1 |
| B3-base | 16.7 | 9.2 | 7.5 | 51k (31k) | 2.7M | 119k | 125 s | 14 (1) | 0 |
| B3-finish | 30.5 | 20.5 | 10.0 | 87k (32k) | 15.7M | **257k** | 276 s | 24 (0) | 5 |
| F3 finish | 0.8 | 0.8 | 0.0 | 5k (0.3k) | 0.1M | 36k | - | 0 | 0 |
| V2R3 review | 14.8 | 13.6 | 1.2 | 64k (31k) | 7.4M | 207k | <120 s | 12 (1) | 10 |

**Against the baseline and the earlier v2 attempts:**

| | v1 best (A3) | v2 A1 | v2 A2 | **v2 A3** |
|---|---|---|---|---|
| Wall (design + review) | 66.1 min | 187.5 | 150.0 | **145.8** (plan 22.2, builds 108.0, finish 0.8, review 14.8) |
| Output tokens (thinking) | 352k (228k) | 902k (601k) | 524k (312k) | **474k (268k)** |
| Cache read | 35.8M | 69.7M | 45.6M | **47.1M** |
| Peak context (any agent) | 488k | 348k | 340k | **257k** |
| Longest generation | 290 s | 765 s | 291 s | **276 s** |
| F/M/A (sum) | 6/6/6 (18) | 7/7/6 (20) | 8/8/9 (25) | **8/8/8 (24)** |
| Issues B/M/m | 0/4/4 | 0/5/7 | 0/2/6 | **0/1/5** |
| cadcheck at hand-off | - | 0 F, 34 W | 0 F, 44 W | **0 F, 34 W, 0 untriaged** |
| cad runs (failed) | - | 121 (15) | 93 (1) | **91 (3)** |

v2 A3 is the cheapest v2 attempt (3% less wall and 10% fewer output tokens than A2) with the lowest peak context of any
attempt, v1 or v2. It closed 5 of 8 previous issues and halved the majors (2 to 1), but scored 1 lower: aesthetics went
9 to 8 for the one new part, the gate detent clip (A3-01). Three v2 attempts total 483.3 min; the scores have stalled at
8/8/8-9 with one major each time.

### Time and token sinks

**V2A3-T1. Reading reports by hand-written `json.load` snippets: 67 bash calls in 7 of 8 agents, 6 of them died on a
guessed key.** B3-finish alone had 26. The keys guessed wrong: `checks.distances.rows` exists, but `checks.drop.tests[i]`
has `rows`, not `poses` (B3-launcher `0:28:05`, B3-finish `0:23:48`), and the manifest has no `fasteners` key (P3
`0:04:47`, B3-finish `0:23:55`). About 11 more calls only printed key lists ("Inspect cadcheck.json structure").
**Fixed:** `cad rows [cadcheck.json|manifest.json] [REGEX] [--check a,b] [--findings]` prints one line per row of every
check (drop and payload tests flattened per pose, `why` at the end) or per manifest part, with no Blender. On the A3
report, `cad rows "min-gap stop \(gap 6.2\)" --check drop` gives the 5 pose rows B3-launcher was after. checks-config.md
now spells out the report layout for scripts that still need it.

**V2A3-T2. The `a20a4d7` ray-vs-nearest warn is 9 for 9 false on A3, and A4 runs on it.** The rule (a ray gap far
wider than the nearest gap, from V2A2-F6) fired on the four Ø13.9 pocket-diameter rows (a part measured against itself,
nearest 0), the three fingertip approach lines (ray 23.6-25.6 against a nearest 12.14 elsewhere on the body) and both
stud-axis thumbwheel rows (6.0 and 4.49 against 1.55 and 1.13 at the rim). On the A3 blend at `a20a4d7`: 0 F, 43 W,
**9 untriaged, all false.** **Fixed:** the warn now also needs the ray's hit on a part to have left its home face (off
the home face's plane by > 0.5 mm, or a normal turned > 25°) at a non-home pose. V2R2's slipped row on the v2 A2 blend
still warns (14.18 against 7.06, verify 4e), and the A3 rows give none.

**V2A3-T3. A false bridge warn the finisher disproved by hand.** cadcheck took a ceiling region's span as the short
side of its xy bounding box. The crown's L-slot floors are 56.5° arc sectors, R31.35..37.4: bbox 26.4, real width 6.
B3-finish read the bridge code (`0:08:25`), wrote `bridge_probe.py` and `inscribed.py` (`0:08:44` to `0:10:16`) and
accepted the warn with "widest inscribed circle 5.1". The flywheel flange ring (72) and nacelle (39) warns were the same
artefact, accepted with reasons in A3. **Fixed:** the span is now the diameter of the widest inscribed circle (a grid over the
region, nearest boundary edge), with `bridge_at` in world coordinates. Synthetic: a 30 x 5 strip at 45° reads 5.0 (bbox
24.7), a 20 mm square 19.9, the crown's sector 6.05. On A3: crown 26.4 to 16.6 (another region), flywheel 72 to 2.7,
nacelle 38.9 to 15.0; the 3 accepted bridge warns go stale. Parts runtime 0.6 to 2.6 s.

**V2A3-T4. A service op with no pose could never be proved.** cadcheck compared `None` with the slide row's pose key,
so no slide_out row could prove it, and the designer added `"pose": {}` to the op by hand (progress.md "Tool issues").
**Fixed:** an op with no pose is proved by a slide row at home.

**V2A3-T5. A flexing detent can't be a slide row.** The gate slide had to `ignore` the detent clip, so nothing bounded
the bump's ride (progress.md "Tool issues"; V2R3 measured it with `gate_move.py`: -0.43 mm³ at +26). **Fixed:** a slide
row's `flex: {"PRT_gate_detent": 1.0}` records the largest overlap with the spring and where, and blocks only above that
bound, even when an `allow` covers the pair. A part named in `flex` needs a `flexures` row.

**V2A3-T6. No slide joint, second attempt running.** The gate's open state was outside every sweep (V2A2-T4), the
detent's open-notch claim had no row, and V2R3 asked for "a prismatic PIV_gate 0..52.35 if the tool supports one"
(A3-03). **Fixed:** `asm.joint(..., prismatic=True)` slides along +axis in mm; cadcheck sweeps it like any joint, with
`overtravel_mm` (1.0) past each end. Proven on `examples/slide-gate` (verify 8).

**V2A3-T7. Other costs.**
- P3 took 22.2 min (P2 9.8): it wrote a 10 KB `mkchecks.py` in one generation (`0:16:55`) and pre-ran the new rows on
  the A2 model (11 F / 2 W, every fail a review issue), as the template now asks.
- `No module named 'cadlib'` 4 times (P3, B3-launcher, B3-feeder): `cad py` from `a20a4d7`, not in the pin.
- 31 tool-source reads (V2A2: about 44): distances, slide, cable leads, buried heads, overhang, bridge, overlay. Most
  are documented at `a20a4d7` or now.
- B3-finish rendered the 8-view final set twice (19 renders saved).
- **The progress file worked as a checkpoint:** the planner made "finish" a build work item, so the Finish phase found
  every step marked done and returned in 0.8 min.

### Issues V2R3 raised, and what the tools did with them

"At hand-off" is the designer's cadcheck at `f039205` (0 F / 34 W, 0 untriaged). "Now" is this run's tools on the archive:
the designer's config (verify 4f) and `overlay_v2a3.json`, V2R3's rows written with this run's features.

| ID | V2R3 issue | At hand-off | Now | Why it got through |
|---|---|---|---|---|
| V2A3-F1 | **Major (A2-01, recurring from V2A2-F1):** the min-gap stop was sized for the nominal 7.0 candy (NIP_PASS = MM_T_NOM + tape), while params declare MM_T up to 7.5. A 7.5 candy is rigidly squeezed 0.07-0.39 mm at full lift over 46 % of the window | not flagged (the row asserted 7.5) | **2 fails** with `"min": "=MM_T[1] + TAPE_T"` (7.61 and 7.93 against 8.0) | the row was typed for the nominal. New `=EXPR` rows; SKILL, checklist and planner prompt say to size pass rows at the declared max |
| V2A3-F2 | Minor (A1-03, third attempt): the Ø13.9 pocket blocks a 12.5 x 6.3 pair by 0.016 mm³, a zero margin | - (no `payload_fit` at `f039205`) | **warn:** `payload_fit` min pair, "only 0.00 mm to spare" (size from `=MM_D[0]`, `=MM_T[0]`) | `payload_fit` is in `a20a4d7`, which A4 has |
| V2A3-F3 | Minor (A2-02, recurring): the 150 mm encoder lead ends at the journal bore; ~430 mm onward through the bundle and base lead is in no BOM row | not flagged | **fail** with a `cable_chains` row: 514 mm against 150. Fresh builds also warn on cable ends that meet with no connector | each route passed against its own lead. New `cable_chains`, junction warn, `cab_ends` in cadlib |
| V2A3-F5 | Minor (A3-01): the detent clip's EB 0.3 and square plate; proud pan head; **M3 x 9 is not stock** | not flagged | **warn:** "non-stock screw lengths: M3 x 9 (FST_detent_0)"; `cad bom` flags the BOM row | new stock-length warn. The edge break and the plate shape are not tool-catchable |
| V2A3-F6 | Minor (A3-02): the BOM lists the nip stud as M3 x 20 hex head; the model has M3_cap x 16 | not flagged | **`cad bom`: BAD** "FST_nip_stud is 16 long in the model ... has a cap head" | BOM text was never compared with the manifest. New `cad bom`; `M3_hex` spec |
| V2A3-F7 | Minor (A3-03): no slide row for the base floor service; the detent open notch has no row (the gate is not a joint) | not flagged | V2R3's floor slide passes; the gate needs a `prismatic` joint (new) | config gap; no slide joint (T6) |

V2R3 marked 2 of 6 issues `tool_catchable`. **At hand-off, cadcheck flagged none of the six.** That is new: in A1 and A2
the misses were warns nobody read, and this time the designer triaged all 34. With this run's tools, 5 of 6 are flagged
(F1, F2, F3 with their rows; F5 and F6 with no config at all), and the 6th needs a prismatic joint in the model. The
remaining misses are now rows nobody writes, which is why the rows can now be written against the params.

**Recurrence:** A2-01 recurred (V2A2-F1 major, now PARTIAL and still the one major), A1-03 is on its third attempt (the
margin went from negative to zero), and A2-02 recurred. All three are payload or cable *extremes*: the designer fixed the
nominal case each time.

**Config disputes (4):** the full-lift row's 7.5 (F1, `=EXPR` now); the base floor's missing slide row (V2R3's row
passes); the detent's open notch with no row (prismatic joint now); post_R x journal_plate contact still hides the
journal (deferred by the designer, `contact_normal` exists).

### What worked
- **Warn triage, for the first time:** 34 warns, 0 untriaged, each with a measured reason (26 new). V2R3's re-run matched
  the warn set exactly, and two of the accepted reasons exposed tool false warns (T3, gear-tooth wall samples).
- **review_rows.json + `--overlay`:** V2R3 put its 3 rows in one file and ran them in one call (2 fails). The planner
  merged V2R2's rows and pre-ran them on the old model (11 F).
- **The finisher's inscribed-circle probe is now cadcheck's bridge span** (T3).
- **Cheapest v2 attempt, lowest peak context (257k) of all six attempts.** No 300 s+ generation.
- V2R3 reused the designer's measurements (identical warn set, re-run in 134 s) and spent its probes on what had no row.

### Reviewer quality (V2R3)
- Every issue has a number and a dimensioned fix. The one major is anchored to a row that fails (7.613 against 8.0).
- **`tool_catchable` was under-marked** (2 of 6): the BOM mismatch and non-stock screw were tool-catchable with a BOM
  cross-check, which didn't exist. The template now says "cadcheck, cad q or cad bom".
- 2 probe scripts where a row would do: `lentil_tilt.py` (leaning pairs; it showed upright is the worst case, so a
  `payload_fit` row suffices) and `gate_move.py` (a prismatic joint now). 1 of 4 renders wasted (camera inside a solid).
- The aesthetics drop 9 to 8 follows the rubric ("each failed item costs a point"): 2 failed items, both on the new clip.

### Why not the existing code (v2 A3 additions)
- **`cad rows` vs jq or `json.tool`:** jq isn't guaranteed on the agents' machine, and the problem was the nesting
  (`tests[].rows[]`, manifest `parts` by kind), not the parser. 120 lines of standard library, one line per row.
- **Inscribed-circle bridge span vs the bbox:** the bbox is right only for axis-aligned rectangles. A medial-axis or
  polygon-offset library (shapely) isn't in Blender's Python; a 0.1-0.24 mm grid with numpy point-to-segment distances
  costs 2 s over 36 parts and is within one grid step on the synthetic cases.
- **Ray slip vs dropping the warn:** V2A2-F6 was a real slip worth a warn. Comparing the hit face with the home pose
  keeps that case (verify 4e) and drops all 9 A3 rows; it reuses `ray_gap` (25 lines).
- **`=EXPR` vs a payload block in config:** a payload block would cover the payload rows only. Params are already in
  the build (`asm.new_scene(params=...)`), and the same mechanism serves stops, travels and leads. Restricted `eval`
  with no builtins (about 40 lines); a bad expression is a `config` fail, not a crash.
- **Prismatic joints vs `slide_out` rows:** a slide row moves one group once and checks it alone; a joint joins every
  sweep (interference with all four collections, drops, sightlines, stability). The joint is a location instead of a
  rotation in two `set_pose` functions plus mm overtravel (about 30 lines).
- **`cad bom` vs the reviewer reading the BOM:** the table format is the template's own (`| M3 x 16 csk ST | 18 |
  \`FST_post_*\` ...`). 130 lines; on A3 it gives exactly V2R3's two BOM errors and no false row after exact names win
  over globs (`FST_pinion_*` vs `FST_pinion_ctr`).
- **`cable_chains` vs per-cable leads:** per-cable leads all passed; the failure was across routes.

### Still open (gaps)
- Edge-break consistency (A3-01) is not measurable from the mesh; the params grep in the checklist stays.
- The wall probe still flags involute gear tooth tips as thin walls (3 accepted warns in A3: disc, pinion, hub gear).
- Exposure doesn't cover PCBs (V2A1-F11); no insertion sweep for assembly merges (V2A1-F6).
- Cable-end junctions need ends stored by cadlib: blends built before this run report "junctions on 0 routes".
- `parallel_builds` is still untested live.
- The stall: three v2 attempts end with one major on a payload extreme. `=EXPR` rows make the extremes cheap to write,
  but nothing forces a planner to write them.

### Verification of this run
- `tools/verify_all.sh`: 66/66 passed (`/tmp/alex3d-verify.log`); A1-A3 and v2 A1-A2 unchanged. New tests: 4f (v2 A3 designer config: 0 F, 1 untriaged warn, no ray-slip or
  bbox-bridge warns; overlay: 3 fails exactly and the zero-margin pocket; `cad bom`: exactly 2 BAD rows; `cad rows`) and
  8 (`examples/slide-gate`: clean 0 F with the prismatic sweep, detent flex 3.2 mm³, the stop at 20.5, bridge 5.0, chain
  and service; `--bug` catches 6 planted problems; the junction warn).

## v2 Attempt 4 (harvested 2026-10-25)

Inputs: the 8 attempt-4 agents in `V2WF/journal.jsonl` (lines 50-65) and their transcripts, plus `HW2/renders/attempt-4/`:
progress.md, cadcheck.json, precheck_rows.json, precheck_a3_model.json, review.md, review.json, review/ (notes.md,
review_rows.json, cadcheck_review.json, 2 PNGs). The blend V2R4 reviewed (`/tmp/rv4/model.blend`, md5 `a6085127…`, the
same as `HW2/blender/model.blend` at 07:10) is archived as `examples/mm-launcher-v2a4/`, with the designer's checks.json,
manifest.json, BOM, V2R4's `review_rows_v2a4.json` and `overlay_v2a4.json` (V2R4's major as one swept row). Plan #5 had
started (0.6 min) and is not ingested.

**The tools were `a20a4d7`** (progress.md line 1): the first attempt with `payload_fit`, `sightlines`, slide `expect`,
`cad py` and the `cad q` help, but not `dea6536` (`cad rows`, `cad bom`, `=EXPR`, prismatic joints, slide `flex`,
`cable_chains`, stock lengths, the ray-slip and inscribed-bridge fixes). Plan #5 moved the pin to `dea6536`, so **this
run's fixes reach v2 attempt 6.**

### Per-agent cost (`cc_transcript.py workflow V2WF`)

| Agent | Wall | Model | Tools | Output tok (thinking) | Cache read | Peak ctx | Longest gen | cad runs (failed) | Images |
|---|---|---|---|---|---|---|---|---|---|
| P4 plan | 8.3 | 7.6 | 0.7 | 40k (20k) | 2.8M | 137k | <120 s | 2 (0) | 0 |
| B4-params | 7.0 | 4.2 | 2.8 | 19k (5k) | 1.6M | 89k | <120 s | 3 (0) | 0 |
| B4-launcher | 18.7 | 8.8 | 9.9 | 39k (19k) | 4.6M | 139k | <120 s | 13 (2) | 1 |
| B4-feeder | 18.8 | 9.6 | 9.2 | 45k (25k) | 3.4M | 142k | <120 s | 8 (0) | 1 |
| B4-cables | 3.9 | 1.2 | 2.7 | 6k (1k) | 0.4M | 43k | <120 s | 1 (0) | 0 |
| B4-finish | 21.0 | 11.0 | 10.0 | 57k (12k) | 8.8M | 199k | <120 s | 12 (0) | 6 |
| F4 finish | 1.0 | 1.0 | 0.0 | 6k (0.3k) | 0.2M | 39k | - | 0 | 0 |
| V2R4 review | 12.8 | 10.1 | 2.8 | 54k (25k) | 5.9M | **200k** | <120 s | 11 (0) | 5 |

| | v1 best (A3) | v2 A1 | v2 A2 | v2 A3 | **v2 A4** |
|---|---|---|---|---|---|
| Wall (design + review) | 66.1 min | 187.5 | 150.0 | 145.8 | **91.5** (plan 8.3, builds 69.4, finish 1.0, review 12.8) |
| Output tokens (thinking) | 352k (228k) | 902k (601k) | 524k (312k) | 474k (268k) | **266k (107k)** |
| Cache read | 35.8M | 69.7M | 45.6M | 47.1M | **27.6M** |
| Peak context (any agent) | 488k | 348k | 340k | 257k | **200k** |
| Longest generation | 290 s | 765 s | 291 s | 276 s | **< 120 s** |
| F/M/A (sum) | 6/6/6 (18) | 7/7/6 (20) | 8/8/9 (25) | 8/8/8 (24) | **8/9/9 (26)** |
| Issues B/M/m | 0/4/4 | 0/5/7 | 0/2/6 | 0/1/5 | **0/1/2** |
| cadcheck at hand-off | - | 0 F, 34 W | 0 F, 44 W | 0 F, 34 W, 0 untriaged | **0 F, 43 W, 0 untriaged** |
| cad runs (failed) | - | 121 (15) | 93 (1) | 91 (3) | **50 (2)** |

**The best attempt of all seven, and the cheapest v2 one:** the highest score (26), the fewest issues (3), 37% less
wall time and 44% fewer output tokens than v2 A3, the lowest peak context, and no generation over 120 s. It is the
first v2 attempt within 1.4x of the v1 baseline's wall time (91.5 against 66.1) while scoring 8 points higher. Part of
the drop is scope: four small changes and no base rebuild. Manufacturability went to 9 for the first time ("cadcheck 0
fails and every warn explained ... BOM fasteners and steps match the manifest").

### Time and token sinks

**V2A4-T1. A failed build read as a clean check of the old model.** B4-launcher removed the wrong line and the build
raised `UnboundLocalError` (`0:03:44`). The agent ran `cad build ... | tail` and then `cad check`, and read a full report
of the previous blend; it noticed only from the traceback ("the check actually ran against the old model since the
build failure didn't halt the pipeline (tail masked the exit code)"). The cause was in the wrapper, not just the pipe:
**Blender exits 0 when a `--python` script raises**, and `cad`'s `run()` ended in `| grep ... || true`. Measured: a
raising script gave exit 0 without `--python-exit-code`, 1 with it. **Fixed:** `run()` passes `--python-exit-code 1`
and keeps Blender's status through the filter; `cad build` prints `cad: BUILD FAILED (exit N) ...` on stderr, which a
`| tail` doesn't swallow. cadcheck warns `build: the model is older than parts/launcher.py` when a `*.py` or
`parts/*.py` beside the blend is newer than it, and that warn can't be accepted. Verify 4g plants both.

**V2A4-T2. Poses past a joint's limit are taken silently** (progress.md "Tool issues"). P4 pre-ran the new full-lift
rows at `PIV_nip_lift -2.19` on the A3 model, whose limit was -1.493: the hood was posed through the solid leaf and the
rows passed. Only the hard-stop ray rows failed, so the precheck still worked. A warn would be wrong here: A4's own
config has 8 deliberate past-limit poses (tilt -3/46 for hard stops beyond the 0..45 firmware range, hood 1 deg past the
min-gap stop). **Fixed:** cadcheck lists every pose outside its joint's range in the summary, grouped by joint
(`poses_past_limits`). `"past_limit_ok": true` drops a row from the list. A pose that names no joint, or a coupled
joint, is a `config` fail, because set_pose ignored both. On the A3 blend with A4's config the list leads with
"PIV_nip_lift range -1.49302..0: -2.19 in distances[23] distances[24] distances[25] distances[38] sightlines[0]".

**V2A4-T3. The `a20a4d7` false warns were paid for again, as predicted.** P4 counted 9 ray-vs-nearest warns on the A3
model and accepted them with 3 reasons. The 3 inherited bbox-bridge accepts stayed too. With today's tools all 6 accepts go
stale on the A4 blend: designer config 0 F, 31 W, 0 untriaged, 6 stale accepts. The fix (V2A3-T2/T3) is in `dea6536`,
which A5 runs.

**V2A4-T4. Hand-written report readers, still:** 71 bash calls with `json.load` (A3: 67) in all 8 agents. 3 died on a
guessed key: `accepted_warns` is a list, not a dict (B4-launcher); `checks.X.rows` (B4-finish); the manifest has no
`fasteners` key (B4-finish, the same key P3 and B3-finish guessed in A3). `cad rows` arrives in A5; count again there.

**V2A4-T5. Other costs.**
- About 22 bash calls read tool source (A3: 31), mostly the ray gap, joint and `--only` code. The questions were
  prismatic joints and hex specs, both added in `dea6536`.
- `cad build` deletes `stl/*.stl` before exporting, which deleted B4-feeder's test coupon. B4-finish moved it to `stl/tools/`.
  Now in footguns.md.
- The planner was short this time (8.3 min, P3 22.2): it wrote `a4_checks.py` (7 KB) and precheck rows. On the A3 model
  the precheck gave 7 F / 13 W, every fail a planned change.
- The finish phase again found every step done and returned in 1.0 min.

### Issues V2R4 raised, and what the tools did with them

| ID | V2R4 issue | At hand-off | Now | Why it got through |
|---|---|---|---|---|
| V2A4-F1 | **Major (A2-01, third attempt as the one major):** the full leaf lift opens the nip at BDC (8.28..9.12) but not on the entry arc. The hood is concentric to PSI_C 78 and hinged at PSI_TOP 112, so the 2.19° lift opens psi 80 by 1.14 (BDC 1.97). Full-lift gap 7.50 / 7.67 / 7.95 at psi 80 (min / home / max stop): a 7.5 candy is rigidly squeezed at every setting | not flagged: 4 full-lift rays at BDC passed (8.28-9.12), and params `gap_bdc()` asserted over psi ±2 | **3 fails from one row:** `ray.sweep` over psi 0..100 about the wheel axis gives 7.496 / 7.666 / 7.954, worst at 80, with the profile. V2R4's 3 rows plus `gap_profile.py` gave the same numbers | the row and the assert sampled one station of a passage. New `ray.sweep`; SKILL, checklist, footguns and planner prompt say to sweep the passage |
| V2A4-F2 | Minor (A4-01, aesthetics): the detent tab's band relief leaves a square step; the pan head stands 1.4 proud | - | - | not geometric-checkable |
| V2A4-F3 | Minor (A4-02): BOM leaf stress numbers rest on the BDC-only gap helper; the cover's manifest orient text says slot 22 x 7.5, geometry 22 x 8.3 | - | - | follows from F1; free text built from a literal, not params |

V2R4 marked 1 of 3 issues `tool_catchable`, correctly. **At hand-off cadcheck flagged none**, as in A3: every warn was
triaged, and the miss was a row that measured the wrong place. Previous issues: 5 of 6 FIXED (A1-03 pocket, A2-02
encoder lead, A3-01 detent, A3-02 BOM stud, A3-03 floor slide), A2-01 PARTIAL.

**Recurrence: A2-01 has now been the one major in v2 A2, A3 and A4,** and each time the designer fixed exactly what
the last reviewer's row measured. A2: the leaf ran out of travel, so travel was added. A3: the row asserted the nominal
candy, so it was resized to the max. A4: the row sat at BDC, and the entry arc fails. The tools moved from "nobody wrote the
row" (A1/A2) to "the row was too narrow" (A3/A4). The swept row is the cheap 1-D cover. A full payload-pass check (a
lens probe moved along the passage) would be the next step if the sweep row still gets written at one station.

**Config disputes (5):** the BDC-only full-lift rows (F1, swept row now); the params assert over psi ±2 (F1, rule in
the SKILL); the leaf operating stress quoted at BDC lift (follows F1); the detent open notch with no row (prismatic
joint in `dea6536`); post_R x journal_plate contact still hides the journal (`contact_normal` exists, deferred for the
third time).

### What worked
- **Plan-time precheck with review rows:** P4 merged V2R3's rows and pre-ran them on the A3 model. All 7 fails were
  planned changes. Five of six previous issues closed.
- **`payload_fit`, first live use:** 4 rows with `margin` (MIN pair blocked 0.06, flat 13.5 fits 0.14). A1-03, open
  since v1 A1, is FIXED. The designer also printed a pocket coupon to calibrate against real candies.
- **Warn triage held:** 0 untriaged at hand-off for the second attempt running. V2R4's re-run matched the warn set.
- **Small steps:** no generation over 120 s in any agent (A3: 5 over 120 s, the longest 276 s).

### Reviewer quality (V2R4)
- 12.8 min, the fastest v2 review. Each issue has numbers and a dimensioned fix (PSI_C 78 to 45, analytic 8.14 at psi
  50). The major is anchored to failing rows (`review_rows.json`, 6 fails).
- Probes where a row would do: `gap_profile.py` is now a swept row, `gate_move.py` a prismatic joint (`dea6536`), and
  `rot_clear.py` (rotating clearance against the brief's 1.5) could be `distances` rows. `psi_c.py` is design
  arithmetic and fine as a probe.
- `tool_catchable` was right on all 3.

### Why not the existing code (v2 A4 additions)
- **`ray.sweep` vs N ray rows:** V2R4 wrote 3 rows by hand (origins and directions computed per angle) and still
  needed a probe for the profile. The sweep reuses `ray_gap` per station (about 25 lines), and turns the ray in its
  frame before the frame transform, so a ray framed in a moving joint stays framed.
- **Sweep vs `payload_fit` along a path:** payload_fit places a probe at one floor point. A moving probe along an arc is
  the general answer but costs a Manifold intersection per station and pose. The ray profile is enough to size PSI_C.
- **Past-limit list vs warn vs clamping:** a warn gave 8 false warns on A4's config; clamping would silently change
  deliberate hard-stop rows. A summary list costs nothing to triage.
- **`--python-exit-code` vs parsing the output for "Error":** Blender's own flag; the status file keeps POSIX sh (no
  `pipefail`).

### Still open (gaps)
- A swept ray is 1-D: a candy tilting in the passage, or a passage that isn't an arc or a line, needs a payload-pass probe.
- Edge-break consistency and free text in the manifest (F3's stale "22 x 7.5") are not checkable from the mesh.
- Gear tooth tips as thin walls; PCB exposure (V2A1-F11); no insertion sweep for merges (V2A1-F6); `parallel_builds`
  untested live.

### Verification of this run
- `tools/verify_all.sh`: 71/71 passed (`/tmp/alex3d-verify.log`); A1-A3 and v2 A1-A3 unchanged. New: verify 4g (v2 A4 designer config 0 F / 0 untriaged / 6 stale accepts / 8 past-limit poses; the
  swept row fails at 7.50 / 7.67 / 7.95 worst at psi 80; -2.19 on the A3 model listed past the limit; stale-model warn
  survives an accept; a raising build script exits non-zero with `BUILD FAILED`).

## v2 Attempt 5 (harvested 2026-10-25)

Inputs: the 7 attempt-5 agents in `V2WF/journal.jsonl` (lines 66-79) and their transcripts, plus `HW2/renders/attempt-5/`:
progress.md, cadcheck.json, precheck_a4_model*.json, review.md, review.json, review/ (notes.md, review_rows.json,
cadcheck_review.json, 2 PNGs). The blend V2R5 reviewed (`/tmp/rv5/model.blend`, md5 `015396a3…`, the same as
`HW2/blender/model.blend` at 08:46) is archived as `examples/mm-launcher-v2a5/` with the designer's checks.json,
manifest.json, BOM, V2R5's `review_rows_v2a5.json`, `overlay_v2a5.json` (the entry arc as one swept row per setting) and
`overlay_v2a5_band.json` (the designer's band stack with `between`, plus a planted bounded allow). Plan #6 had started
(0.6 min) and is not ingested.

**The tools were `dea6536`** (progress.md line 1): the first attempt with `cad rows`, `cad bom`, `=EXPR`, prismatic
joints, slide `flex`, `cable_chains` and the ray-slip / inscribed-bridge fixes, but not `36189b8` (`ray.sweep`, past-limit
list, stale-model warn, `BUILD FAILED`). Plan #6 moves the pin to `36189b8`, so **this run's fixes reach v2 attempt 7.**

### Per-agent cost (`cc_transcript.py workflow V2WF`)

| Agent | Wall | Model | Tools | Output tok (thinking) | Cache read | Peak ctx | Longest gen | cad runs (failed) | Images |
|---|---|---|---|---|---|---|---|---|---|
| P5 plan | 8.5 | 7.5 | 0.9 | 38k (18k) | 2.6M | 127k | <120 s | 2 (0) | 0 |
| B5-params | 9.3 | 3.4 | 5.9 | 18k (9k) | 0.6M | 69k | <120 s | 4 (0) | 0 |
| B5-launcher | **30.2** | 18.1 | 12.1 | **93k (62k)** | 11.5M | **240k** | <120 s | 12 (1) | 0 |
| B5-feeder | 13.1 | 6.7 | 6.4 | 40k (18k) | 4.4M | 134k | <120 s | 11 (0) | 3 |
| B5-finish | 17.3 | 10.6 | 6.7 | 62k (15k) | 9.8M | 221k | <120 s | 9 (0) | 3 |
| F5 finish | 0.7 | 0.6 | 0.0 | 4k (0.3k) | 0.1M | 34k | - | 0 | 0 |
| V2R5 review | 14.2 | 11.1 | 3.0 | 59k (33k) | 5.5M | 200k | <120 s | 6 (0) | 6 |

| | v1 best (A3) | v2 A3 | v2 A4 | **v2 A5** |
|---|---|---|---|---|
| Wall (design + review) | 66.1 min | 145.8 | 91.5 | **93.3** (plan 8.5, builds 69.9, finish 0.7, review 14.2) |
| Output tokens (thinking) | 352k (228k) | 474k (268k) | 266k (107k) | **314k (157k)** |
| Cache read | 35.8M | 47.1M | 27.6M | **34.4M** |
| Peak context (any agent) | 488k | 257k | 200k | **240k** |
| Longest generation | 290 s | 276 s | < 120 s | **< 120 s** |
| F/M/A (sum) | 6/6/6 (18) | 8/8/8 (24) | 8/9/9 (26) | **9/8/9 (26)** |
| Issues B/M/m | 0/4/4 | 0/1/5 | 0/1/2 | **0/1/5** |
| cadcheck at hand-off | - | 0 F, 34 W, 0 untriaged | 0 F, 43 W, 0 untriaged | **0 F, 34 W, 0 untriaged, 0 stale** |
| cad runs (failed) | - | 91 (3) | 50 (2) | **44 (1)** |

Same score sum as A4 at about the same cost. **Functionality reached 9 for the first time:** A2-01, the one major in v2
A2, A3 and A4, is FIXED (entry arc >= 8.0 everywhere, minimum 8.099). The new major is a different part (the detent tab
against the jar band). All six A4 false-warn accepts went stale on `dea6536` as predicted, and B5-finish removed them.
**`cad rows` and `cad bom` were used** (8 and 8 calls; `cad bom` at finish: 18 rows, 0 disagree; V2R5 re-ran it).

### Time and token sinks

**V2A5-T1. `cad check ... --only x --out X` ignored `--out`** (progress.md "Tool issues"). The wrapper always put its
default `--out <dir>/cadcheck.json` first, and cadcheck's `_arg` took the first occurrence, so P5's precheck overwrote
the designer's `blender/cadcheck.json`; P5 restored it from attempt-4. **Fixed:** the wrapper adds no default when
`--out` is among the flags, and `_arg` takes the last occurrence. Verify 4h runs the flag form and checks that
`cadcheck.json` beside the blend is untouched.

**V2A5-T2. A shared-param change predicted on paper, then redesigned by a builder.** P5 planned PSI_C 78 -> 45 from
analytic numbers (8.138 at the min stop) and ran its precheck rows (`--only distances,slide,cables`) on the A4 model.
It never built the new value. B5-params applied it and got **14 drop fails** (the 7.0 candy landed at psi 63-66 and
stalled at tilt >= 40) plus a sightline fail, and wrote "Needs a design decision". B5-launcher then spent **30.2 min, 62k
thinking tokens and a 240k context** replacing the quadratic profile with a lift-matched one (8.105 floor), with
experiments along the way. The design was right in the end (31/31 drops, entry arc >= 8.1), but the conflict was there
to find at plan time with a scratch build. **Template:** the planner tries a shared params change in a `/tmp` copy with
`cad check --only drop,distances,sightlines` before planning around it. The v2 loop uses its own copy of the template,
so this reaches v2 only if the user adopts it.

**V2A5-T3. Slide `flex` recorded nothing below `vol_tol`** (progress.md "Tool issues"). The detent rides the blade at
0.43 mm³ < 0.5, so `flexed` was `{}` and the row proved only that the detent no longer blocks. **Fixed:** a flex part's
overlap is recorded at any volume > 0 up to its bound. On the A5 blend the gate slide row now reports the ride.

**V2A5-T4. `json.load` again, but mostly config edits.** 76 bash calls with `json.load` (A4 71 by the old count). Split
by what they do: **47 load and dump checks.json to add rows** (A4: 51 of 82 under the same split), 24 read a report, 3
read checks.json, 2 other. So the earlier count overstated the reader problem: `cad rows` covers report reads (8
uses), and editing JSON through `json.load`/`dump` is a fair way to append rows. The reads left: drop `stall_points`
(`cad rows` printed only `[N]`) and V2R5's reads of the designer's allow, slide and stack rows. **Fixed:** `cad rows`
prints the first stall points, and `cad rows checks.json [REGEX]` prints config rows (allow, fits, distances, stacks, ...).

**V2A5-T5. Other costs.**
- `slide_out.step` is mm per station; the A1-A4 gate rows' `"step": 2` read to P5 like an assembly step. Now commented
  in checks-config.md.
- 18 bash calls read tool source (A4 about 22).
- V2R5 wrote **9 hand rows** for the entry arc (psi 10..102) because `dea6536` has no `ray.sweep`. One swept row per
  setting gives the same minimum (verify 4h). A6 has it.
- The finish phase again found every step done (0.7 min).

### Issues V2R5 raised, and what the tools did with them

| ID | V2R5 issue | At hand-off | Now | Why it got through |
|---|---|---|---|---|
| V2A5-F1 | **Major (A5-01):** the detent tab top wraps the jar band's lower corner at 0.322 normal (0.455 radial); the band chain is RSS 1.26 / worst 1.90, and every other band row uses min 2.0 | passed: row `BUY_jar_band>PRT_gate_detent min 0.3` read 0.322; the band stack passed (typed `limit` 3.0, RSS 1.31) | **fails with the designer's own terms:** the band stack plus `"between": ["BUY_jar_band", "*"]` gives "RSS 1.31 mm > 0.32 (measured: PRT_gate_detent at 0.322, jar=30)"; the adapter is listed as touching | the row's `min` was set to what the geometry gave (A4 0.5, A5 0.32), and the stack's limit was a typed design intent the new tab never touched. New stacks `between`; SKILL, checklist, planner prompt |
| V2A5-F2 | Minor (A5-02): the 7.5 candy passes the min-stop entry arc by 0.099 (8.099 at psi 90); the designer's rows covered psi 50..80 | passed (8.105..8.182) | one swept row per setting gives 8.099 at psi 90, 8.211 / 8.397 at the other settings (V2R5: 8.219 / 8.423 at psi 90) | rows at stations, not the passage: V2A4-F1 again, now with margin. `ray.sweep` reaches A6 |
| V2A5-F3 | Minor (A5-03): the 3-way bus junction (BOM 14a) is real hardware but not modelled | warned, then waived with `cable_junctions_ok` | still waived; listed in `cables.junctions_waived` and the coverage line; the warn says to model a connector wider than the cable | the waiver was offered for "a connector sits there" without asking whether it takes room |
| V2A5-F4 | Minor (A5-04): the PLA leaf cycles to 28-34 MPa on a 12.5 MPa preload (creep, fatigue) | - | - | material judgement, not geometry |
| V2A5-F5 | Minor (A5-05): BUY_tape modelled 13.8 wide, BOM buys 12.7 tape; side.png crops | - | - | `cad bom` covers fasteners only |
| V2A5-F6 | Minor (A5-06): an open `allow` PRT_gate_detent x PRT_jar_gate, although its own reason (0.43 mm³ < vol_tol) makes it unnecessary; it would hide a deeper clash in every gate sweep | not flagged | **listed** in `summary.unbounded_allows` (with 5 other designed allows across joints); an `allow` with `"max_mm3"` measures the overlap and fails past it: bounded at 0.1 it fails at 0.43 mm³ | an allow skipped the pair at every pose with no bound. New `max_mm3` |

V2R5 marked 4 of 6 `tool_catchable` (F1, F3, F5, F6), correctly. **At hand-off cadcheck flagged one of them** (F3, waived);
now F1 fails with a config row, F3 and F6 are listed, and F5 is not covered. Previous issues: 3 of 3 FIXED (A2-01, A4-01,
A4-02).

**Recurrence:** A2-01 is closed after four attempts. The pattern behind it did recur in a new place. F1 is a row whose
bound followed the geometry (min 0.3 for a tab built 0.32 away), next to sibling rows at 2.0 on the same purchased part.
A row the designer writes after measuring passes by construction. The measured stack limit ties the bound to the
tolerance chain instead.

**Config disputes (3):** the band-detent `min` 0.3 (F1, `between` now); the open detent allow (F6, `max_mm3` now); the
entry-arc rows at psi 50..80 only (F2, `ray.sweep` in A6).

### What worked
- **The plan-time precheck again:** P5's 6 precheck fails on the A4 model matched V2R4's A2-01 numbers exactly (7.943 /
  7.719 / 7.496 at psi 60/70/80). The gate became a prismatic joint and the stud an `M3_hex`, closing two A4 tool-limit
  deferrals.
- **`cad bom` at finish** (18 rows, 0 disagree) and **stale accepts cleaned up** at finish (6 removed, `stale []`).
- **Small steps held:** no generation over 120 s in any agent for the second attempt running, despite the redesign.
- **The designer modelled the tape** (`BUY_tape`) and aimed drop rows at it, which V2R5 called conservative.

### Reviewer quality (V2R5)
- 14.2 min. Every issue has numbers, evidence rows (`review_rows.json`, 1 fail) and a dimensioned fix (cap the tab at
  z 299.5, EB 1.0). V2R5 re-ran the full check and matched all 16 sections of the designer's report.
- It wrote a `stacks` row by hand with the measured 0.455 typed in as the limit: exactly what `between` now does.
- The 9 hand entry-arc rows are one swept row in A6.
- `tool_catchable` was right on all 6.

### Why not the existing code (v2 A5 additions)
- **Stacks `between` vs tightening the distances row:** the row's `min` is a number the designer types after measuring;
  the stack already holds the tolerance chain. `between` reuses `min_dist` and `bb_gap` (about 40 lines) and skips
  candidates farther than the stack's worst case.
- **`max_mm3` vs deleting the allow:** without the allow, a 0.43 mm³ ride counts as zero-clearance contact across a joint
  (a rubbing fail), so V2R5's "delete it" would trade one dispute for a fail. A bound keeps the ride legal and makes a
  deeper clash fail. It reuses `inter_volume`, only for bounded rules and only at overlapping poses.
- **An unbounded-allow list vs a warn:** the A5 config has 5 legitimate allows across joints (spline, glued magnet,
  captive stud). A warn would add 5 accepts; a summary list costs nothing to read.
- **Fixing `--out` in both places:** the wrapper fix alone leaves direct `Blender ... --python cadcheck.py` callers with
  first-wins; last-wins is the usual CLI rule.

### Still open (gaps)
- BOM free text vs model (F5: tape width; A4's "22 x 7.5"): `cad bom` reads fasteners only.
- Material creep and fatigue (F4) are outside geometry.
- A swept ray is 1-D; gear tooth tips as thin walls; PCB exposure (V2A1-F11); no insertion sweep for merges
  (V2A1-F6); `parallel_builds` untested live.

### Verification of this run
- `tools/verify_all.sh`: 75/75 passed (`/tmp/alex3d-verify.log`); A1-A3 and v2 A1-A4 unchanged. New: verify 4h (v2 A5
  designer config 0 F / 0 untriaged / 0 stale with the detent allow listed as unbounded and the gate slide recording the
  sub-vol_tol ride; one swept row gives 8.099 at psi 90; the band stack with `between` fails at 0.322 on the detent and a
  0.1 mm³ bounded allow fails at 0.43; `--out` after `--only` leaves `cadcheck.json` alone).

## v2 Attempt 6 (harvested 2026-10-25)

Inputs: the 7 attempt-6 agents in `V2WF/journal.jsonl` (lines 80-93) and their transcripts, plus `HW2/renders/attempt-6/`:
progress.md, cadcheck.json, precheck_a5_model.json, checks_attempt5.json, review.md, review.json, review/ (notes.md,
review_rows.json, cadcheck_review.json, 2 PNGs). The blend V2R6 reviewed (`/tmp/rv6/model.blend`, md5 `e3cf6fdd…`, the same
as `HW2/blender/model.blend` at 10:25, before attempt 7 edited the sources) is archived as `examples/mm-launcher-v2a6/` with
the designer's checks.json, manifest.json, BOM, V2R6's `review_rows_v2a6.json` and `overlay_v2a6_steps.json` (the
assembly_order with the three step facts the new insertion check asks for). Plan #7 had started (0.6 min) and is not
ingested.

**The tools were `36189b8`** (progress.md line 1): the first attempt with `ray.sweep`, the past-limit list, the stale-model
warn and `BUILD FAILED`, but not `6025133` (stacks `between`, `max_mm3`, `cad rows checks.json`). Plan #7 moves the pin to
`6025133`, so **this run's fixes reach v2 attempt 8.** v2 agents: `P6` plan `a5c6c97fd5291db4f`, builders `B6-checks`
`ab67c3c981ceb6e7b` (a no-op: the planner had done the step), `B6-feeder` `a6f76c31bfd31b5c4`, `B6-junction`
`aac18bdc4f360b240` (pan_stage + base), `B6-finish` `ad52a387901339499`, `F6` finish `a901396d59e028176`, `V2R6` review
`a63e157964068fba7`.

### Per-agent cost (`cc_transcript.py workflow V2WF`)

| Agent | Wall | Model | Tools | Output tok (thinking) | Cache read | Peak ctx | Longest gen | cad runs (failed) | Images |
|---|---|---|---|---|---|---|---|---|---|
| P6 plan | **17.6** | 8.9 | 8.7 | 44k (26k) | 2.8M | 146k | <120 s | 0 (0) | 0 |
| B6-checks | 0.5 | 0.5 | 0.0 | 3k (0.2k) | 0.1M | 30k | - | 0 | 0 |
| B6-feeder | 14.6 | 4.9 | 9.7 | 24k (9k) | 2.4M | 97k | <120 s | 11 (0) | 1 |
| B6-junction | 15.3 | 8.3 | 7.0 | 44k (23k) | 3.2M | 118k | <120 s | 17 (3) | 0 |
| B6-finish | 14.9 | 8.1 | 6.9 | 50k (9k) | 9.0M | **193k** | <120 s | 10 (0) | 6 |
| F6 finish | 4.7 | 1.9 | 2.8 | 9k (1k) | 0.5M | 43k | - | 1 | 0 |
| V2R6 review | 9.3 | 7.2 | 2.1 | 40k (16k) | 4.3M | 163k | <120 s | 7 (0) | 7 |

| | v1 best (A3) | v2 A4 | v2 A5 | **v2 A6** |
|---|---|---|---|---|
| Wall (design + review) | 66.1 min | 91.5 | 93.3 | **76.9** (plan 17.6, builds 45.3, finish 4.7, review 9.3) |
| Output tokens (thinking) | 352k (228k) | 266k (107k) | 314k (157k) | **213k (83k)** |
| Cache read | 35.8M | 27.6M | 34.4M | **22.3M** |
| Peak context (any agent) | 488k | 200k | 240k | **193k** |
| Longest generation | 290 s | < 120 s | < 120 s | **< 120 s** |
| F/M/A (sum) | 6/6/6 (18) | 8/9/9 (26) | 9/8/9 (26) | **9/8/9 (26)** |
| Issues B/M/m | 0/4/4 | 0/1/2 | 0/1/5 | **0/1/2** |
| cadcheck at hand-off | - | 0 F, 43 W, 0 untriaged | 0 F, 34 W, 0 untriaged | **0 F, 35 W, 0 untriaged, 0 stale** |
| cad runs (failed) | - | 50 (2) | 44 (1) | **46 (3)** |

The cheapest v2 attempt so far, and the first under 80 minutes: about 32% fewer output tokens than A5 and the smallest
peak context in either loop. The score held at 26. All 6 of A5's issues are FIXED. The new major is a part placed in a
step that cannot reach it.

**What `36189b8` did in use:**
- **`ray.sweep` was adopted.** P6 turned the designer's 5 point entry-arc rows (and V2R5's 9) into one swept row per
  setting, plus swept hood-to-tape and rest-gap rows. They reproduced V2R5 exactly: 8.099 at psi 90 / 8.211 / 8.397.
- **The past-limit list** showed 8 intended poses on the unchanged A5 model; P6 marked 7 rows `past_limit_ok`.
- **`BUILD FAILED`** fired twice in B6-junction (its own `_note_loop` and cable-budget asserts), and each was fixed on the
  next 2.4 s build. The stale-model warn never fired.
- **`cad rows`** went from 8 calls in A5 to 39. `json.load` calls fell from 76 to 48: 16 config edits (load + dump), 21
  report reads, 8 config reads, 2 manifest reads, 1 other.

### Time and token sinks

**V2A6-T1. Plan doubled to 17.6 min, mostly in checks.** P6 ran four checks on the unchanged A5 model, 8.7 min of tool
time in all:
- a full baseline check on the new tools (165 s);
- `--only interference` with the new rows (96 s);
- the bounded-fits rule (90 s);
- a full precheck of the new checks.json (169 s).

The baseline on the new tools paid off, because it found the past-limit list. The last full precheck repeated the
first, and only the rows had changed. The builds still came in 25 min under A5 (45.3 against 69.9): this time the
planner had tried its changes, and no builder redesigned anything (contrast V2A5-T2). Not changed: a subset precheck
would have been enough, but the template already says to precheck the rows.

**V2A6-T2. `G.bevel` after a dense-faceted cut gave ~0.1 edge breaks on the whole part (A5 and A6).** B6-feeder found
the detent tab's EB 1.0 measuring 0.115 (ray at 0:04:48), and traced it to the n=768 cylinder cut (0.28 mm facets).
Blender's bevel overlap clamp is **global**: one short edge next to a bevelled one scales every break on the part. The
fix was to rebuild the tab as a 6-chord prism, after about 2 min of probing. A5's tab had the same defect, and V2R5 did
not see it ("edge-break consistency is not measurable", in Known gaps).
**Fixed:** `cadlib.geom.bevel` measures how far its new vertices move. An unclamped break moves box corners about
1.4 x w. Under 0.7 x w, it prints a warning and sets `bevel_clamped`, and cadcheck's `parts` warns on that. The test
(`tools/test_bevel_clamp.py`): a plain box is not flagged, and a box minus an n=768 cylinder is (largest move 0.014 for
w 1.0). The template and demo builds are not flagged.

**V2A6-T3. Facet sag against a design-value `min`.** B6-junction's splice-to-hub-gear row (min 1.0) read 0.969 with
default facets: an n=48 Ø10 envelope against an R13 bore. Bumping the bore to n=256 fixed it, at about 1.5 min.
This is now in the SKILL as a note; cadlib's facet defaults are unchanged, because changing them mid-v2 would move
every number in the next build.

**V2A6-T4. Remaining report reads.** Of the 21 report reads, 8 were the summary, coverage, not_checked and
`assembly.step_of` (B6-finish, F6, V2R6). **Fixed:** `cad rows cadcheck.json --summary [REGEX]` prints the counts,
unbounded allows, coverage, not_checked and step_of, one line each. The other reads were slide, part mass and
thin-wall rows, and `cad rows` already prints those.

**V2A6-T5. Other costs.**
- B6-checks spent 0.5 min finding its step done, because the planner had done it. The finish phase again found
  little to do (4.7 min, text only).
- 7 bash calls read tool source (A5: 18).
- V2R6 took 9.3 min, the fastest review in v2. It re-ran the full check (identical in all 16 sections) and wrote 4
  review rows (one fails).

### Issues V2R6 raised, and what the tools did with them

| ID | V2R6 issue | At hand-off | Now | Why it got through |
|---|---|---|---|---|
| V2A6-F1 | **Major (A6-01):** BOM step 10d splices and seats the bus junction in the hub bore, but by then the groove cap (2c) closes it above and the base floor (3) below; V2R6's slide row: +Z blocked by `PRT_groove_cap` at 4 mm | not flagged: `BUY_bus_junction` was in the feeder's **bench** step 10d, so every test at that step saw only feeder parts | **two warns:** "BUY_bus_junction is in bench step '10d' (group 'feeder') but 146.0 mm from every other part of that group", and the feeder merge (step 11) "has no straight way in: +Z PRT_groove_cap (BUY_bus_junction) at 3, -Z PRT_beam (PRT_feeder_housing) at 0, ..." | nothing tested whether a part can get to its place; the config step was the feeder's, because the feeder bus lead runs to it. New `insertion` check |
| V2A6-F2 | Minor (A6-02): the static pan lead ends 1.2 under the splice, which now sits at r 7 and orbits 9.9 mm over ±90 pan; the base lead's meeting point at r 4 does the same, and its `distances` row passes only because the two Ø6 sleeves overlap | not flagged (the junction warn compares ends at home only) | **two warns:** CAB_bus_pan 8.8 mm further from BUY_bus_junction at pan -90; CAB_launcher_base 5.7 mm from CAB_launcher_bundle at pan 90. A5's on-axis meetings: 6 pairs, all 0.0 | cable ends were compared at home only. New `cables.end_drift` |
| V2A6-F3 | Minor (A6-03): the swept full-lift and tape rows at home and the max stop miss their psi 0 station (`missed_deg [0]`) | passed silently (an open station passes a `min`) | **4 warns**, one per row and pose, "missed a part at 1 of 53 stations (0 deg)" | `ray.sweep` (36189b8) reported `missed_deg` but did not warn |

V2R6 marked all 3 `tool_catchable`, correctly. **At hand-off cadcheck flagged none of them; now all 3 are warns** with V2R6's
numbers (groove cap at 3 above the splice top, against V2R6's 2.5 from a ray origin 0.5 higher; 8.8 + 1.2 = 10.0 against
V2R6's 9.9 chord). Previous issues: 6 of 6 FIXED (A5-01 to A5-06).

**Recurrence:** the config described the design inaccurately again, this time in assembly_order. A part sat in a step
that matched its cable, not where it is assembled. Every row at that step then passed by construction, just as A5's
detent row (`min` 0.3 for a tab built 0.32 away, V2A5-F1) passed by construction. The insertion check doesn't depend on
which step the designer chose: it moves the bench group in at its merge, so the part is tested where it ends up.

**Config disputes (3):** no row for placing the splice (F1); the base/bundle meeting row passing on overlapping
sleeves (F2); the swept rows missing psi 0 (F3).

### New: the insertion check (`--only insertion`, V2A6-F1)
Each PRT/BUY part, and each bench group at its merge, has to come out of its place in a straight line past the
solids and fasteners of the earlier steps in its assembly. Directions tried: ±X/Y/Z, ± the axis of each screw that
touches the part, and the step's `insert_dirs`. The step's `pose` is set first. Rays run both ways: from the moving
part's samples into the obstacles, and from obstacle samples in its lane back into it.

It took four rounds on the A6 blend to get the false blocks out:
- **28 warns at first.** A hit at t ≈ 0 on a face sharing an edge with the mover blocked every seated cover, so the
  first version ignored entering hits within 0.05 mm.
- **11 warns.** Parts of a merge step were counted as present before that step, which blocked A6's thrust ring with
  the turntable it goes under. Also, the pod parts sit on 3° and 19° screw axes, so screw axes became directions.
- **9 warns.** A flush cover's edge break, a coplanar seat and faceted bores at zero clearance still read "blocked at
  0.05-0.6". So a hit now counts only when the point 0.3 mm past it is inside the obstacle and more than 0.05 mm from
  its surface.
- **5 warns.** Each one is real or a config fact. Besides the two A6-01 warns:
  - the jar step says "drop in at +30" and the pod step "held nose-up about 20 deg", but neither has a `pose`. With
    the poses declared, the jar comes out +Z and the pod +Z;
  - `FST_nip_stud` is in step 6c, "dropped into the backplate pocket", one step before the backplate. Moved to 6d,
    the backplate comes out +X.

On the v2 A1-A5 blends it gives the same 3 config-fact warns and nothing else. Time on A6 is 6.6 s with the facts
declared and 15.6 s in a full run with the failing details. One bench rule needs no geometry: a bench part more than
2 mm from every other part of its group, by bounding box, warns. That is the A6 splice, 146 mm from the feeder.

### What worked
- **Plan-time trial, done properly:** P6 prechecked every new row on the A5 model. The failure count was 5 F, as
  planned, and the builders hit no surprises; contrast V2A5-T2.
- **B6-feeder found and fixed the cause** of the clamped edge breaks instead of accepting them. **B6-junction measured
  an overlap** (-5.09 mm³ against the swept splice) and moved the base lead rather than accepting a warn.
- **Swept rows and `cad rows`** became the default way to measure and to read.

### Reviewer quality (V2R6)
- 9.3 min, every issue with numbers and a fix. V2R6 re-ran the full check and matched all 16 sections. It wrote 4
  review rows: 3 slides and 1 service, with 1 fail, the A6-01 evidence. They are verified as tool rows (verify 4i).
- It found the closed bore from `assembly.step_of` plus two `cad q ray` lines, which is what the insertion check now
  does for every part.
- `tool_catchable` was right on all 3.

### Why not the existing code (v2 A6 additions)
- **Insertion vs `slide_out` rows:** a slide row tests one part along one direction that the designer chose, at a pose
  with everything present. V2R6 needed 3 rows and a service op to show A6-01. The insertion check tests every part at
  its own step, against only what is there, with no rows to write. It reuses `bvh_world`, `_edge_samples`, `inside`,
  `fastener_axis` and the bench/merge rules from `assembly_present`. A swept-BVH step test like `check_slide`'s would
  cost 6 directions x 80 parts x ~100 steps of BVH rebuilds. Ray casting is about 3-7 s.
- **Considered: a disassembly planner** (blocking graphs, non-straight paths). It would need a motion-planning
  dependency for a case that one straight line plus a declared pose covered on all six v2 configs.
- **End drift vs a `distances` row:** the row measures surface distance, so two overlapping Ø6 sleeves read 0 whatever
  the ends do (A6-02). Drift follows the end points through each joint limit; it reuses `cab_ends` and `relevant_joints`.
- **Bevel clamp flag vs `use_clamp_overlap = False`:** without the clamp, Blender makes self-intersecting geometry
  when the break is wider than a short neighbouring edge. Measuring the vertex moves costs one KD-tree and does not
  change geometry: every v2 build stays bit-identical.

### Still open (gaps)
- Insertion: straight lines only, and parts of the same step are not tested against each other. A part pushed in
  along an axis no screw marks needs `insert_dirs`.
- BOM free text vs model (tape width, splice position text). Material creep and fatigue are outside geometry.
- A swept ray is 1-D. Other open gaps: gear tooth tips read as thin walls; PCB exposure (V2A1-F11); `parallel_builds`
  is untested live.
- cadlib facet defaults are not sag-based (V2A6-T3).

### Verification of this run
- `tools/verify_all.sh`: 79/79 passed (`/tmp/alex3d-verify.log`). A1-A3 and v2 A1-A5 are unchanged, except that
  v2 A3-A5 now also carry the 3 insertion step-fact warns, which are asserted exactly. New:
  - verify 4i: the v2 A6 designer config gives 0 F and exactly 11 untriaged warns: A6-01 x2, A6-02 x2 (8.8 / 5.7),
    A6-03 x4, plus the 3 step facts. With `overlay_v2a6_steps.json`, only the 2 A6-01 warns remain. V2R6's slide row
    fails on `PRT_groove_cap`.
  - verify 4j: `tools/test_bevel_clamp.py`.
- The insertion check on the v2 A1-A5 blends gives 3 warns each, all of them config facts. The `end_drift` check on
  v2 A5 gives 6 pairs, all 0.0 apart.

## v2 Attempt 7 (harvested 2026-10-25)

Inputs: the 7 attempt-7 agents in `V2WF/journal.jsonl` (lines 94-107) and their transcripts, plus `HW2/renders/attempt-7/`:
progress.md, cadcheck.json, check_step{1,2,3a}.json, precheck_a6_model.json, checks_attempt6.json, checks_edit_a7.py,
tail_feasibility.py, review.md, review.json, review/ (notes.md, review_rows.json, cadcheck.json, cadcheck_review.json, 1 PNG).
The blend V2R7 reviewed (`/tmp/rv7/model.blend` with its checks.json) is archived as `examples/mm-launcher-v2a7/`, with
the manifest and BOM (both unchanged since 11:00, before the review), V2R7's `review_rows_v2a7.json` and
`overlay_v2a7_steps.json` (the step facts the insertion check asks for). Plan #8 had started (0.2 min) and is not ingested.

**The tools were `6025133`** (progress.md line 1): stacks `between`, `max_mm3`, `cad rows checks.json`, but not the
insertion check, end drift, missed-station warns, the bevel flag or `cad rows --summary` (all in `fb54dbb`, which plan
#8 moves the pin to). **This run's fixes reach v2 attempt 9.** v2 agents: `P7` plan `ad3613ab937789401`, builders
`B7-checks` `a91da03e25e2193ee` (a no-op again: the planner did the step), `B7-cap` `ab7fc7097ebb0f9d8`, `B7-tail`
`aabeff3011188d075` (base + pan_stage), `B7-finish` `ade4ba6e78782e6a9`, `F7` finish `ad3729c48968e6dc0` (a no-op),
`V2R7` review `aa6f4aea5dd48c1d4`.

### Per-agent cost (`cc_transcript.py workflow V2WF`)

| Agent | Wall | Model | Tools | Output tok (thinking) | Cache read | Peak ctx | Longest gen | cad runs (failed) | Images |
|---|---|---|---|---|---|---|---|---|---|
| P7 plan | 10.8 | 9.4 | 1.5 | 48k (27k) | 3.4M | 138k | 152 s | 4 (1) | 0 |
| B7-checks | 0.6 | 0.6 | 0.0 | 4k (0.1k) | 0.1M | 26k | - | 0 | 0 |
| B7-cap | 4.0 | 1.0 | 3.1 | 5k (0.4k) | 0.3M | 48k | - | 1 (0) | 0 |
| B7-tail | 9.0 | 2.8 | 6.2 | 14k (3k) | 1.4M | 86k | - | 6 (0) | 0 |
| B7-finish | 15.7 | 7.8 | 7.9 | 47k (7k) | 5.3M | 155k | - | 10 (0) | 3 |
| F7 finish | 0.7 | 0.7 | 0.0 | 4k (0.4k) | 0.1M | 34k | - | 0 | 0 |
| V2R7 review | 9.6 | 8.9 | 0.7 | 50k (24k) | 4.8M | **164k** | - | 5 (0) | 4 |

| | v1 best (A3) | v2 A5 | v2 A6 | **v2 A7** |
|---|---|---|---|---|
| Wall (design + review) | 66.1 min | 93.3 | 76.9 | **50.5** (plan 10.8, builds 29.3, finish 0.7, review 9.6) |
| Output tokens (thinking) | 352k (228k) | 314k (157k) | 213k (83k) | **173k (62k)** |
| Cache read | 35.8M | 34.4M | 22.3M | **15.4M** |
| Peak context (any agent) | 488k | 240k | 193k | **164k** |
| Longest generation | 290 s | < 120 s | < 120 s | **152 s** (P7, reading the row options) |
| F/M/A (sum) | 6/6/6 (18) | 9/8/9 (26) | 9/8/9 (26) | **9/8/9 (26)** |
| Issues B/M/m | 0/4/4 | 0/1/5 | 0/1/2 | **0/1/3** |
| cadcheck at hand-off | - | 0 F, 34 W, 0 untriaged | 0 F, 35 W, 0 untriaged | **0 F, 37 W, 0 untriaged** |
| cad runs (failed) | - | 44 (1) | 46 (3) | **26 (1)** |

The cheapest attempt in either loop, and the first under the v1 baseline's best wall time (66.1): 23% under it with 51%
of its output tokens. The score held at 26 for the third attempt running. A6-01 and A6-03 are FIXED, A6-02 is PARTIAL
(the bus hand-over is on the axis, the launcher bundle's is not). The one major is new, and it came from the A6-01 fix.

**What `6025133` did in use:**
- No tool issue was logged ("No tool misbehaved"). The one failed cad run was the planner's own checks.json edit
  script, which left a missing comma; cadcheck stopped with the JSON decoder's traceback (line and column), fixed in 12 s.
- `cad rows` calls fell from 39 to 7 and `json.load` commands stayed at 45 (A6: 48): 14 in P7 (8 of them keeping the
  checks.json format through an edit script), 16 in B7-finish (summary, coverage, evidence numbers), 5 in V2R7 (2 to diff
  its report against the designer's). `cad rows --summary` (in `fb54dbb`) covers the summary and coverage reads.
- No stacks or bounded allows were added: A7's changes did not touch a toleranced purchased part.

### Time and token sinks

**V2A7-T1. The cheapest attempt because the fixes were small and planned.** The plan held an order change, a 14.6 mm
cable tail and BOM text, each tried before it was planned: P7 prechecked every new row on the A6 model (4 F, all
"CAB_bus_pan_tail not in the scene", as planned) and modelled the tail's clearances with capsules
(`tail_feasibility.py`) before choosing `LB_LEG_R` 6.5. The builders met no surprises: B7-cap took 4.0 min for a
one-line step change, B7-tail 9.0 min.

**V2A7-T2. Finish work is now one agent.** B7-finish (15.7 min, 7.8 of it Blender: final renders, two hub-bore sections, a
full check) did the BOM, log and renders; the `finish` phase found its step done (0.7 min), as did B7-checks (0.6). Not
changed: the template already lets the planner fold steps.

**V2A7-T3. Remaining hand reads.** V2R7 diffed its full report against the designer's with two `json.load` scripts (V2R6
did the same), and B7-finish gathered evidence numbers with 16. Not changed this run: a `cad rows --diff` would save
about a minute per review.

### Issues V2R7 raised, and what the tools did with them

| ID | V2R7 issue | At hand-off (`6025133`) | Now | Why it got through |
|---|---|---|---|---|
| V2A7-F1 | **Major (A7-01):** step 11a starts "tilt the pod to 45" (FST_gcap_5 is reachable only there), but the tilt servo has been in since step 8 and nothing is powered until the battery at 14: back-driving an unpowered servo through its gears and holding it at 45 while 6 screws go in | accepted warn "FST_gcap_5 reachable only at tilt=45" | **warn:** "step '11a ...' needs PIV_tilt at 45 (FST_gcap_5 is reachable only at tilt=45), but BUY_servo_tilt (by name) holds that joint from step '8 ...' and no step up to here is "powered" ..." | the fastener check found the pose, and nothing asked whether the joint can get there at that step. New **held-pose** check (`assembly.held_poses`) |
| V2A7-F2 | Minor (A7-02): CAB_bus_tilt and CAB_bus_feeder share one tube to the splice top (-82.5 mm³) and both turn 90 deg onto its face 1.5 below | not flagged: cable-cable pairs are never tested, bend radius was in not_checked | **3 warns:** both leads "kinks: 90 deg at [5.7, 4.0, 100.5] with radius 0.0", and "CAB_bus_feeder and CAB_bus_tilt lie in one tube for 16 mm" | no check looked at cable shape. New `cables.kinks` and `cables.shared_runs` |
| A6-02 (PARTIAL) | Minor: the Ø6 launcher bundle still hands over at r 4 and swings a 5.66 chord; the v2-A2-02 row passes only on sleeve overlap (0.916 against max 1.0) | not flagged (end drift is in `fb54dbb`) | **warn:** "CAB_launcher_base ends 0.0 mm from CAB_launcher_bundle ... at pan=90 that point is 5.7 mm further away" | the designer deferred it ("the joint never opens"); in A8 the drift warn makes that an explicit accept |
| V2A7-F3 | Minor (A7-03): the cap-removal row lifts +Z 40 and passes, leaving the cap under the pod; the review's forward-up row at tilt 45 is clear (min 0.2), back-up hits the nip cover at 54. Two `why` strings say z 64 / r 6 (model 63 / 6.5) | passed | not flagged (SKILL and template now say a removal row runs until the part is clear) | a row's length is the designer's choice; prose numbers in `why` are not checked |

V2R7 marked A7-02, A6-02 and A7-03 `tool_catchable` and A7-01 not. **At hand-off cadcheck flagged none of the four; now
three are warns**, with V2R7's numbers. Previous issues: A6-01 FIXED, A6-02 PARTIAL, A6-03 FIXED.

**Recurrence: a fix creates the next major.** A6-01 (a part placed where it cannot get in) was fixed by moving the
groove cap to after the splice. That move put six screws at a step where one of them needs tilt 45, and the designer
accepted the existing "reachable only at tilt=45" warn: true of the geometry, but it hid an assembly that cannot be done
as written. The same pattern as A5 to A6: each fix is tested against the rows it touches, not against the order of
operations around it. The held-pose check and the insertion check now test the order itself.

**Recurrence: a deferred minor.** A6-02's second half was deferred with a reason ("the two Ø6 ends are 5.66 apart at
pan ±90, less than one sleeve diameter, so that joint never opens"). The reviewer disagreed and kept it open. With the
drift warn in A8, the deferral becomes an `accepted_warns` entry the reviewer can see.

**Config disputes (4):** the 40 mm cap lift proves no removal (F3); no method or row for tilt 45 at 11a (F1); the
base/bundle `distances` row passes on sleeve overlap (A6-02); two stale `why` strings (F3).

### New: held poses (`assembly.held_poses`, V2A7-F1)
A **need** is a step `pose`, or a screw at that step whose access the fastener check found only at a joint limit (its
`access_best` pose). A joint's **drive** is `joint_drives[joint]`, or by name a `BUY_` part named servo, motor, stepper
or actuator that ends in the joint's name: PIV_tilt -> BUY_servo_tilt, PIV_pan -> BUY_servo_pan, PIV_feeder ->
BUY_servo_feeder on all v2 blends. Continuous and coupled joints are left out. The drive is in from the step where it
lands in the need's group, which is the bench merge for the tilt drive (step 8). A need after that, away from home and
before the first step marked `"powered": true`, warns, unless the step says how in `"pose_how"`. Needs at one step and
joint are merged into one warn.

On the v2 A1-A6 configs it finds no need at all: no step poses and no pose-only screws. A6's overlay pose (pod nose-up 20
at step 7) comes before the tilt servo at 8, so it passes. On A7 it gives exactly A7-01. With 11a's own text ("pod at
tilt 45") declared as a pose, the warn lists both needs. Marking the battery step `powered` does not clear it, because
power comes at 14, after 11a. A `pose_how` on 11a lists it instead of warning. The check reads the fastener rows, so it
needs no geometry and runs in no measurable time.

**Considered: inferring drives from contact.** The tilt servo body sits on the post (static under pan) and its key on
the journal plate (PIV_tilt). A contact test across the joint would find it without names, but the horn adapter, the
key socket and the bearing faces all touch across the same joint. Names plus `joint_drives` were exact on all 7 blends.

### New: cable kinks and shared tubes (`cables.kinks`, `cables.shared_runs`, V2A7-F2)
Each route's polyline comes from `cab_path` (cadlib stores it from this run on) or, on older blends, from the tube
mesh: one ring of vertices per polyline point, with ring 0 repeating the last point. The reconstruction matches
`path_len` on all 15 A7 routes and is dropped when it doesn't. Rules:
- **Kink:** a corner's fitted centreline radius is under `cable_min_bend_od` (0.75) x OD. A corner gets half of each
  neighbouring segment for its arc. At an end within 3 mm of a `BUY_` part (a plug, splice or board), the first OD must
  run straight. At an end that meets the next route of the same `cable_chains` row (a hand-over), the corner gets the
  full segment. Without the BUY rule, A7's bus leads read radius 1.5 (90 deg over a 1.5 mm stub); with it they read 0,
  which is what V2R7 called a zero-radius bend at the heat-shrink exit. The first version applied the straight-exit rule
  at every end that met no chained end, which flagged the bundle's hand-over in the journal bore (radius 0). Only ends
  at a purchased part count now.
- **Shared tube:** two routes on one body, not in one chain, whose centrelines stay within half their summed radii
  for more than 2 OD.

On the v2 blends it gives (A1-A5) 5 warns and (A6, A7) 6: A7-02's three on A6 and A7, plus three that recur in every
attempt and that no reviewer raised:
- the bundle's 90 deg corner at radius 4.0 for OD 6 at the journal bore (inner radius 1.0);
- the feeder bus lying inside the bundle for 218 mm down the left post;
- the encoder lead sharing 22 mm of the journal bore with phase 2.

Each is a real modelling question (does the channel hold both?), so they are warns to triage, not suppressed. Thresholds
tried: 1 x OD also flags the designed R4.75 U-loop of the Ø6 base lead (0.78) and the pan bus's 140 deg turn (0.76).
Runtime is about 5.5 s on A7.

**Considered: cable-cable overlap in the interference check.** `pair_class` skips CAB-CAB pairs. Turning them on gives
volumes (-82.5 mm³ for A7-02) but flags every hand-over between chained routes and every meeting at a splice, and it
doesn't say how long the run is or where. Centreline distance does both, at no BVH cost.

**Tried and dropped: insertion in step-list order.** The groove cap read "free +Y" with the splice (same step) ignored,
so obstacles were extended to the parts listed earlier in the same step. On v2 A1-A7 that added 4-5 warns per config
(the pan servo listed after its own clamp glob, the jar parts in list order, the nip stop sleeve), all list-order
artefacts, and the cap still came out +Y with the splice present. Reverted.

### What worked
- **Plan-time trial again:** P7 prechecked the new rows (4 F, all planned), modelled the tail with capsules, and wrote
  each step's acceptance as row numbers. The builders followed the plan with no redesign.
- **The A6-01 fix used the rows the reviewer wrote:** V2R6's slide rows became the designer's service and slide
  rows, and the captive row (`expect` blocked at 2.0..4.5 by the cap) is a new pattern: a row that proves retention.
- **On-axis hand-over** for the bus lead (`BUS_PAN_AX`), with a chain row across the two routes.

### Reviewer quality (V2R7)
- 9.6 min. V2R7 re-ran the full check (identical in all 16 sections), wrote 6 cap-exit rows (4 blocked as probes, 2
  clear), measured the shared tube with `cad q dist` and found the tilt problem from `FST_gcap_5`'s access rows plus the
  BOM's power step. These rows are verified as tool rows (verify 4k).
- It marked A7-01 not tool-catchable. That was correct for `6025133`; with this run's check it is.

### Why not the existing code (v2 A7 additions)
- **Held poses vs the fastener access warn:** the fastener check already said "reachable only at tilt=45" and was
  right; what it cannot say is whether tilt 45 is reachable at that step. That needs the joint's drive and the step's
  power, which are assembly facts. It reuses the fastener rows, `fastener_poses` and the bench/merge rules.
- **Held poses vs a `service` row at tilt 45:** the designer had one, and it passed: service rows assume a built,
  powered machine.
- **Kinks vs `distances` rows:** a row measures surface distance between two parts. A turn right at a plug and two
  leads in one tube are properties of the routes themselves, and no row names them.
- **`cab_path` vs reading the manifest:** the manifest drops cadlib's `path`. Storing the polyline on the object keeps
  the blend self-contained, like `cab_ends`, and changes no geometry.

### Still open (gaps)
- A removal row that stops short (A7-03) is not caught; the insertion check tests each part to infinity at its step,
  but a `slide_out` row's length is the designer's choice.
- Prose in `why` strings and the BOM (z 64 against a model at 63) is unchecked. `=EXPR` covers row values, not text.
- Insertion treats parts made in place (a soldered splice lowered 25 mm) like parts brought from outside: the A7 splice
  reads "no straight way in" at tilt 45 (+Z PRT_nip_cover at 67.6). Mark such steps `insert_ok`.
- Held poses cover assembly steps, not service ops: those assume power.
- Known from earlier runs: BOM free text vs model, creep and fatigue, PCB exposure, gear tips as thin walls, facet
  defaults, `parallel_builds` untested live.

### Verification of this run
- `tools/verify_all.sh`: 84/84 passed (`/tmp/alex3d-verify.log`). A1-A3 and v2 A1-A6 are unchanged except for the new
  cable-shape warns, which are asserted exactly: 5 on v2 A3-A5, 6 on v2 A6 (with A7-02's shared tube). New:
  - verify 4k: the v2 A7 designer config gives 0 F and exactly 12 untriaged warns: A7-01 (held pose), A7-02 (2 kinks,
    1 shared tube), the A6-02 drift (5.7), 4 insertion step facts and 3 other cable shapes. With
    `overlay_v2a7_steps.json`, insertion leaves only the in-place splice and the held-pose row names both needs.
    `powered` on step 14 does not clear it, and `pose_how` on 11a does. V2R7's cap rows: forward-up is clear (0.2),
    back-up is blocked by the nip cover at 54.
  - verify 4l: `tools/test_cable_shapes.py`: a kink into a plug and a 21 mm shared run are flagged; the rounded route
    and the chained hand-over are not.

## v2 post-freeze: supports on a design that claimed none (2026-10-25, task docs/tasks/2026-10-25-printability-and-slicing.md)

v2 was frozen at attempt 7 and packaged with "supports: no" on all 36 printed parts. The user questioned it; an
orchestrator check (`docs/evidence-v2-supports/printcheck.py`, `result.json`, renders) found two parts that need support
and that cadcheck had passed. This run built a layer-based check on the exported STLs and a guarded slicer tool.

### What was missed, and why (V2PF-1)
The layer check on the shipped STLs (`mm-launch-hw/v2/stl`, written 11:14, byte-identical to the v2a7 model's export;
archived as `examples/mm-launcher-v2a7/stl.tar.gz`) fails four parts, seven regions, all marked supports: no:

| Part | Region (print frame) | Measured | Cause in the source |
|---|---|---|---|
| jar_valve | 3 bayonet tabs at z 2.0 | cantilevers 5.5, 5.5, 5.6 mm (65 mm² each; bbox 13 x 10.6, a rotated 5.5 x 12 tab) | tabs on the skirt, nothing under them ("lug undersides bridge 5.5 mm" in `orient`) |
| feeder_cover | 2 screw ears at z 32.2 | cantilevers 10.4, 10.5 mm (77 mm² each) | ears printed at the top of a cover printed upside down |
| base_shell | zip-tie anchor block at z 45 | cantilever 6.0 mm (39 mm²) | `parts/base.py:165`: a 6.5 x 8 x 10 block on the niche wall; printed deck-down its underside hangs off one wall |
| post_R | top above the cover band at z 142 | cantilever 11.7 mm (512 mm², 48 mm long) | `parts/pan_stage.py:228`: `G.csg(ob, sub=[band])` splits the cover off and leaves the post top overhanging the gap |

The old `check_parts` saw every one of these regions and passed them: it measured each flat downward face's inscribed
circle as a "bridge span" (jar_valve 5.5, feeder_cover 5.6, base_shell 4.1, post_R 11.7, all under 25) without asking
whether the face was anchored on two sides, only ever warned, only above 150 mm² for slopes, never looked for regions
starting in mid-air, and read the model rather than the STLs (cadcheck.json at hand-off, `parts.rows`). The
orchestrator's checker did flag base_shell's block (40 mm², "20% anchored", at z 45) but the part went on its
false-positive list with the window tops; post_R's top it did not report. Both were checked in the source above.

Ground truth from the task, as measured:
- **Flagged:** jar_valve (3 fails), feeder_cover (2 fails). Pass.
- **Not flagged:** beam and nip_cover (bed-edge chamfers and countersinks: 0 findings), flywheel's flange ring (within
  the 45 deg allowance; two 2.9 mm ledges warn), base_shell's window tops (bridges 15.4 and 15.8 mm, pass), feeder_crown
  (the T-junction pocket roof is a bridge: no fail; three 35 mm arc-slot floors anchored at both radial ends warn as
  bridges over 25), nacelle (14.8 mm bridge, pass). Pass.
- **Disagreement:** the task lists base_shell among the false positives because of its window tops; those pass. Its
  zip-tie block is a real 6 mm cantilever (layer sections at z 44.9 / 45.1 show the block appearing off one wall with air
  below), so base_shell does fail, once.

On every archived attempt (verify 4n): v2 A1-A7 all carry the same 7 fails; v1 A1 has arm_cover_R (a 2.6 mm wall
9.3 mm off its flange at z 1), base_shell's 0.6 mm ribs starting 20 mm up (4) and the hopper's funnel lip in mid-air;
A2 and A3 the same base_shell and hopper regions. No reviewer raised any of them: tool-catchable, never caught.

### The layer check (`scripts/printcheck.py`, `cad printcheck`, cadcheck `parts`, `cad q printcheck`)
Each STL is sliced at mid-layer (0.2 mm) into a raster (0.1 mm, coarser only past 1.5 M cells) by nonzero winding, so
overlapping shells union and the T-junction topology that broke the orchestrator's face-adjacency test does not matter.
A pixel is supported within 0.2 mm (45 deg) plus half a pixel of the layer below. Each unsupported region is a
**bridge** when straight lines in one direction end on supported material at both ends for at least half of it (holes
the region encloses are filled first, so a counterbore printed face down is a roof with a screw hole, not a ledge), a
**cantilever** otherwise (overhang = straight distance to the anchor or to the bridged part), or an **island** with no
anchor. On supports: no, islands from 0.5 mm² and cantilevers over 3 mm fail; ledges of 1-3 mm and bridges over 25 mm
warn. Unsupported slivers with no 0.4 mm core (one extrusion line) are dropped from the layer, so they neither fail nor
carry the layer above: v1's 0.2 mm base_shell fins and the hopper's 0.1 mm funnel hairline were otherwise false
cantilevers 12-39 mm long, and dropping the hairline exposed the real island above it.

Thresholds against the data: the smallest real miss is 5.5 mm, the largest short ledge on v2 is 2.9 (flywheel). The
3 mm fail line sits between. Runtime: 26 s for the 36 v2 STLs cold, layers that cross only the same vertical walls are
reused, and results are cached under $TMPDIR by triangle hash, so a repeat `cad check` costs about 1 s. cadcheck reads
`stl/<name>.stl` when it is on disk (and warns when it differs from the model), else the model's print triangles; on
the v2a7 blend both give identical verdicts and the cache key matched byte for byte.

Fixtures (`tools/test_printcheck.py`, built with cadlib and written with `cadlib.export`): an 8 mm tab (7.9 measured)
and a floating block fail, a 35 mm bridge warns (34.7), and a 20 mm bridge, a 0.8 mm ledge, a 45 deg chamfer, a
counterbore face down, a 6 mm horizontal hole and two overlapping unjoined shells pass.

The repo's own examples had the same flaw: the project template's floor bosses stopped 16 mm short of the deck (4
cantilevers, 4.4 mm, printed deck-down) and now run to the deck; the demo turret's base bosses (4 islands) and barrel
muzzle (35 mm) are now declared supports: yes, which the check reports without failing.

### `cad slice` (V2PF-2): a slicer that cannot hurt the user
Installed: Bambu Studio 02.05.00.66 only (`/Applications/Orca.app` is the Orca agent IDE, `com.stablyai.orca`, not
OrcaSlicer; detection goes by bundle id). `~/Library/Logs/DiagnosticReports` held 10 BambuStudio crash reports from
2026-10-24 21:48-22:37, from an agent's CLI attempts with flattened and inheriting profiles (transcript of the launch-rig
agent): all SIGSEGV in `Slic3r::CLI::run`, 7 in `PartPlateList::set_shapes -> generate_print_polygon ->
GUI_App::plater()` at address 0x768 (a null GUI app), 3 in `GUI::get_min_flush_volumes`. GUI code called from the CLI.

The guard (`scripts/guarded_run.py`) starts the slicer with posix_spawn and points its task exception ports at a Mach
port the guard owns: a fault arrives there first and the slicer is SIGKILLed before ReportCrash sees it; an abort's
EXC_CRASH is answered KERN_SUCCESS. Measured with a compiled crasher: unguarded, a segfault and an abort wrote 2
`.ips` reports; guarded, as a plain binary, inside an ad-hoc-signed hardened-runtime .app, and under sandbox-exec, 0.
Two traps found on the way, both macOS 27.0.1: (1) setting identity-carrying exception ports (EXCEPTION_DEFAULT) on a
platform binary (`/bin/echo`, `sandbox-exec`) is an `EXC_GUARD SET_EXCEPTION_BEHAVIOR` kill of the spawner, so the guard
refuses platform binaries and runs **inside** the sandbox rather than around it; the first attempt crashed the guard's
own Python (one `Python-2026-10-25-170400.ips`, which may have shown the user a dialog); (2) EXCEPTION_STATE contains
faults but lets an abort reach ReportCrash, so the identity behavior stays.

Isolation: `sandbox-exec` with `(deny network*)`, reads and writes of `~/Library/Application Support/{BambuStudio,
OrcaSlicer,PrusaSlicer}`, their caches and preferences denied, and writes allowed only in a fresh temp dir that is
also HOME and CFFIXED_USER_HOME (and `--datadir` for Prusa/Orca). Stand-in slicers (`tools/fake_slicer.c`) prove it:
a write outside the temp dir and a loopback connect are both denied (EPERM), HOME is the temp dir, a crashing slicer is
marked unusable on its one smoke test without a crash report and is not run again, and time (12m 30s), filament
(3.7 g), support heights (z 0.6-1.0 on the supports-on pass) and warnings parse.

The one real smoke test: `cad slice --probe bambustudio` (20 mm cube, the app's own BBL P1S / 0.20 Standard / PLA
Basic presets flattened into the temp dir): `3207: nozzle_volume_type not found`, then EXC_BAD_ACCESS after 0.2 s,
caught; DiagnosticReports still 10 BambuStudio reports; the user's BambuStudio folder mtimes unchanged (stat only).
Bambu Studio 02.05.00.66 is recorded unusable in `slicers/known.json` (committed, so the v2 pin never re-tests it).
`cad slice` now says "NO USABLE SLICER ... cad printcheck is the authority". PrusaSlicer would make it work
(STATUS.md has the install command); its profile is vendored (`slicers/profiles/prusa_p1s_pla.ini`, untested against a
real PrusaSlicer, as is the G-code parsing of real Prusa/Orca/Bambu output).

### Why not the existing code
- **cadcheck `check_parts`** (prior art in this repo): it already found every region (ceiling_mm2, inscribed span).
  Its only knob is `max_bridge_mm`. To warn on all four misses it must drop to 4.0, where it also warns on 7 parts that
  print fine (base_floor, feeder_crown, nacelle, post_L, post_R_cover, tilt_horn_adapter, turntable: 11 warns, 4 real),
  and it still only warns. A face's span says nothing about which of its edges are anchored.
  Kept: manifold, bed fit, walls, slopes; replaced: the ceiling-span warn.
- **The orchestrator's `printcheck.py`** (face adjacency, anchored edge fraction): flags jar_valve and feeder_cover, but
  also 12 bed-chamfer islands on beam, a nip_cover island, crown islands from T-junction edges, and bbox spans on
  nacelle and flywheel (the task's false-positive list). Its anchoring test needs shared edges, which booleans break.
- **A slicer as the checker:** none usable here (above). A raster per layer needs only numpy, which Blender ships.

### Still open
- Sustained steep slopes (say 60-70 deg from vertical) step less than 0.3 mm per layer and pass the layer check; the
  face-based sloped-overhang warn (over 150 mm²) still covers them.
- The G-code and log parsing in `cad slice` is tested on stand-in output only; no working slicer is installed.
- The fail line (3 mm) is a judgement between 2.9 (short ledges that print) and 5.5 (the smallest real miss).

### Verification of this run
- `tools/verify_all.sh`: 100/100 passed in 27.5 min (`/tmp/alex3d-verify.log`; layer results were cached from earlier
  runs, a cold cache adds a few minutes). The attempt regressions (A1-A3, v2 A1-A7, slide gate) run with
  `CAD_LAYER_CHECK=0` and are unchanged: the ceiling-span warn this run removed was accepted nowhere, so no accept went
  stale. The demo and the template run with the layer check and pass (after the fixes above). New:
  - 4m: the fixtures; `cad printcheck` on the archived v2 STLs (exactly the 4 parts and 7 regions above, none of the
    task's false positives fail, every finding has world coordinates); cadcheck `parts` on the v2a7 blend reads
    `stl/*.stl` and gives the same 7 fails; `cad q printcheck`; `tools/test_cad_slice.sh` (stand-in slicers, guard,
    sandbox, parsing); `cad slice --detect` reports Bambu Studio unusable from known.json and runs nothing.
  - 4n: the layer check on every archived attempt, fails asserted per part (v1 A1-A3, v2 A1-A7).

## Push-assist loop (2026-10-26/27)

A second project through the same skills. The push-assist unit (handles with load cells in a barrel, bolted to a
chair's seat-back plate) ran a `/loop` in `PASESS` from 2026-10-26 22:02 to 2026-10-27 07:58 EDT. Each attempt had a
designer, then an independent reviewer using `skills/cad-design-review`. The loop allowed up to 8 attempts and stopped
early only at 9+ on Functionality, Manufacturability and Aesthetics.
PALOG was kept while it ran, as observation only: nothing in `skills/` or `tools/` changed during the loop.

Inputs:
- PALOG (1,228 lines, 8 attempts, a run summary, ranked candidates).
- `PA/cad/review/attempts.md`: the loop's own score table and change logs.
- `PA/cad/review/aN/`: the reviews.
- `cc_transcript.py workflow PASESS/subagents`, plus `usage` and `timeline` on `PASESS.jsonl` for the two inline
  designs.

### Which tools the loop used: `49aa21f`, the same tree as `next` today
- `PA/.claude/skills/{print-cad-blender,cad-design-review}` are symlinks (created 2026-10-26 21:24) into this repo's
  main checkout. Agents ran `~/code-stuff/alex-3d-skills/skills/print-cad-blender/scripts/cad` and read
  `.../cad-design-review/SKILL.md` by that path (`cc_transcript.py grep`: PA-R1 at 0:00:02 and 0:00:59, PA-R8 at
  0:00:13, PA-D8 at 0:07:52).
- The coordinator's freshness check (`PASESS.jsonl` #121, 22:29) printed branch `next` at `49aa21f`, with only the
  untracked log in `git status`. PA-D8 saw `49aa21f` at 06:32 (0:00:45).
- The checkout's reflog has HEAD at `49aa21f` from 2026-10-26 16:51 to 2026-10-27 11:28, with no commit, checkout or
  reset in between.
- Not pinned: uncommitted edits to the checkout between those two checks. `git status` was seen only at 22:29.
- `git diff 49aa21f 2e6717d` is empty: `next` today has the tree the loop ran on. **Every tool gap below is still in
  `next`** unless its status says otherwise.

That tree already had PRs #1-#5. SKILL.md told designers to place screws with `features.fastener_joint`, route with
`cadlib.route` and grow connectors with `cadlib.blend`, and the designers read those lines (PA-D3 at 0:00:07,
PA-D8 at 0:00:49). The project's build never called any of them. `PA/cad/blender/build_concept.py` is a hand-written bpy and SDF script from before the loop,
and it imports only `cadlib.geom`. No tool call in the session's transcripts names any of the three.

**PA-A0-T1: the build bypassed the tools before attempt 1** (added after the loop from `cc_transcript.py grep` on the
transcripts; not in PALOG).
- The coordinator read SKILL.md at 78:13:41 (session-elapsed, `PASESS.jsonl`). At 78:13:53 it judged "fully migrating
  the existing build script to cadlib's conventions is a large undertaking". At 78:17:09 it called it "a bigger
  migration to propose separately rather than do now", and saved that to project memory at 78:17:13.
- At 78:58 it wrote `to_cadcheck.py`, a converter to cadcheck conventions. Every designer prompt then called that
  pipeline "already working".
- The designers read the tool lines (above), but edited the build's own `screw()` and `cable()` helpers. No designer's
  thinking names any of the three tools. PA-D3 drew the patch cable by hand as a spline (0:32:13; `poly_cable` at
  0:37:34).
- `cad q route` on a /tmp copy of A8's `check.blend`:
  - `CAB_Patch_cable` is drawn at 150.0 mm for a 150 mm cable; the routed path is 84.5 mm, with 0 violations.
  - `CAB_Load_cell_lead_R` stops at "buried" at its cell end. With `--from 152.9,50.8,-6.9 --to 127.3,50.8,-49.6` it
    routes 50.8 mm, against the hand path's 85.5 mm, which overlaps solids by 24.7 mm³.

### Scores (`PA/cad/review/attempts.md`; issue counts from the reviewers' ranked lists in PALOG)

| Attempt | Designer | F/M/A (sum) | Issues B/M/m | cad check (designer, at hand-off) | printcheck |
|---|---|---|---|---|---|
| 1 | coordinator, inline | 5/5/7 (17) | 2/5/4 | 0 fail, 65 warn | 10 parts, 0 fail, 12 warn |
| 2 | coordinator, inline | 5/6/6 (17) | 1/5/7 | 0 fail, 35 warn | 10 parts, 0 fail, 0 warn; pistons need support |
| 3 | PA-D3 | 7/8/7 (22) | 0/2/7 | 0 fail, 23 warn (all triaged) | 11 parts, 0 fail, 8 warn; no supports |
| 4 | PA-D4 | 7/8/8 (23) | 0/4/4 | 0 fail, 39 warn (all triaged); moving-link rows 0/0 | 15 parts, 0 fail, 24 warn; no supports |
| 5 | PA-D5 | 8/6/9 (23) | 1/1/6 | 0 fail, 47 warn (all accepted); moving-link/bench 0/0 | 17 parts, 0 fail, 16 warn; no supports |
| 6 | PA-D6 | 8/8/9 (25) | 0/2/5 | 0 fail, 47 warn (all accepted); moving-link 0/0 | 17 parts, 0 fail, 16 warn; no supports |
| 7 | PA-D7 | **4/4/9** (17) | 1/1/7 | 0 fail, 51 warn (all accepted); moving-link 0/0 | 18 parts, 0 fail, 20 warn; no supports |
| 8 | PA-D8 | **8/8/9** (25) | 0/2/8 | 0 fail, 51 warn (all accepted); moving-link 0/0 | 18 parts, 0 fail, 20 warn; no supports |

attempts.md gives no printcheck warn counts for A5-A8. The 16 and 20 come from the designers' hand-off notes in PALOG.

**Outcome: 8 attempts, no pass.** The best score was 8/8/9, reached in A6 and again in A8. Aesthetics reached 9 at A5
and held. F and M peaked at 8. attempts.md's outcome note: "Stopped after 8 attempts without reaching 9+ on all three.
Best: a8 8/8/9 (a6 also 8/8/9). The a8 majors are documentation/settings and cable-order fixes, not geometry."
PA-R8's anchors agree: under 1 h, no reprint (PA-END-T1).

A7's fall to 4/4/9 came from a 0.2 mm slot error. The slot was the fix for the A6 cell that could not be fitted
(PA-A7-T7, PA-A7-T14). cad check, printcheck and `cad bom` all passed both A6 and A7 (PA-A7-T17).

### Cost (`cc_transcript.py workflow PASESS/subagents`; A1/A2 design from `usage` + `timeline` on `PASESS.jsonl`)

| Agent | Wall | Model | Tools | Output tok (thinking) | Cache read | Peak ctx | Blender runs | Images |
|---|---|---|---|---|---|---|---|---|
| A1 design (inline) | 12.2 | 6.0 | 6.2 | 36k (16k) | 10.1M | 367k* | - | - |
| PA-R1 (foreground) | 13.9 | 10.4 | 3.5 | 57k (32k) | 5.1M | 174k | 0 | 12 |
| A2 design (inline) | 20.9 | 9.0 | 11.9 | 53k (30k) | 12.0M | 446k* | - | - |
| PA-R2 | 17.0 | 15.1 | 1.9 | 88k (56k) | 4.9M | 194k | 0 | 9 |
| PA-D3 | 89.6 | 54.4 | 35.2 | 319k (250k) | 23.5M | 516k | 10 | 4 |
| PA-R3 | 15.8 | 13.4 | 2.4 | 76k (44k) | 6.4M | 206k | 1 | 7 |
| PA-D4 | 68.7 | 47.8 | 21.0 | 283k (195k) | 39.2M | 526k | 13 | 16 |
| PA-R4 | 13.0 | 11.5 | 1.5 | 67k (40k) | 4.7M | 198k | 0 | 12 |
| PA-D5 | 85.6 | 58.1 | 27.5 | 345k (254k) | 37.3M | 577k | 8 | 9 |
| PA-D5's firmware sub-agent | 1.9 | 1.9 | 0.0 | 13k (3k) | 0.2M | 33k | 0 | 0 |
| PA-R5 | 15.1 | 14.6 | 0.6 | 80k (47k) | 6.3M | 223k | 0 | 14 |
| PA-D6 | 31.4 | 16.7 | 14.7 | 97k (54k) | 12.1M | 255k | 4 | 3 |
| PA-R6 | 12.9 | 9.9 | 2.9 | 58k (32k) | 4.2M | 185k | 4 | 13 |
| PA-D7 | 88.8 | 63.5 | 25.3 | 378k (268k) | **59.9M** | **659k** | 17 | 16 |
| PA-R7 | 20.1 | 15.5 | 4.6 | 88k (49k) | 10.0M | 232k | 0 | 8 |
| PA-D8 | 58.7 | 33.6 | 25.4 | 196k (125k) | 34.0M | 468k | **22** | 15 |
| PA-R8 | **28.5** | 18.0 | 10.5 | 105k (58k) | 10.7M | 282k | 7 | 15 |

\* The coordinator's whole context, not a designer's.

| Attempt | Design wall | Review wall | Total | Output tok (design + review) |
|---|---|---|---|---|
| 1 | 12.2 (inline) | 13.9 | 26.1 | 93k |
| 2 | 20.9 (inline) | 17.0 | 37.9 | 141k |
| 3 | 89.6 | 15.8 | 105.4 | 395k |
| 4 | 68.7 | 13.0 | 81.7 | 350k |
| 5 | 85.6 (firmware sub-agent's 1.9 ran inside it) | 15.1 | 100.7 | 425k (+13k sub-agent) |
| 6 | 31.4 | 12.9 | 44.3 | 154k |
| 7 | 88.8 | 20.1 | 108.9 | 466k |
| 8 | 58.7 | 28.5 | 87.2 | 301k |
| **Total** | **455.9 (7.6 h)** | **136.3 (2.3 h)** | **592.2** | **2.33M (1.55M thinking)** |

- **The inline designs.** A1 and A2 ran in the coordinator, with no transcript of their own (PALOG: "designer work
  happens inline in the main session"). Their rows sum the coordinator's API calls and tool runs over two windows.
  A1 ran from the `/loop` prompt to the PA-R1 launch, 22:02:37-22:14:47. A2 ran from PA-R1's return to the PA-R2
  launch, 22:28:41-22:49:33. In `timeline` terms, those are `78:55:22-79:07:32` and `79:21:26-79:42:18` after the
  session start, 2026-10-23 15:07:15. Coordinator turns between later attempts are not counted.
- The loop took 9.9 h of wall clock. Designers and reviewers ran one at a time, so agent wall time accounts for
  almost all of it.
- **PALOG's run summary is low.** It gives designers "~6.5 h ... D3-D8 45-90 min each". cc_transcript gives
  D3-D8 422.8 min (7.0 h) at 31.4-89.6 min each, and 7.6 h with the inline A1/A2.
- PALOG's reviewer walls were read when review.json landed. cc_transcript's totals cover each whole transcript and
  run 0.3-1.2 min higher (PA-R1 13.6 vs 13.9, PA-R8 27.4 vs 28.5). The range is 12.9-28.5, not 12-27.
- **Designer time is front-loaded thinking.** PA-D3's first edit came at 0:35:06, after three single generations of
  385, 949 and 556 s (174k thinking, PA-A3-T6). PA-D4 had a 757 s generation (PA-A4-T5). PA-D5's 1,062 s generation
  was the longest of the run, and its first build came at 0:35:03 (PA-A5-T9). PA-D7 had five generations of
  165-622 s (PA-A7-T5).
- Thinking time tracks how much of the mechanism changes. PA-D6 had a narrow issue list and took 31.4 min, with a
  longest generation of 169 s (PALOG, PA-D6 snapshot).
- Prompt-cache misses after those gaps re-wrote 167k (D3), 561k (D5), 589k (D7) and 638k tokens (D8), per PALOG.
  The D5, D7 and D8 figures are from mid-run snapshots.
- **Reviews got longer when they walked the assembly.** PA-R7 (20.1) and PA-R8 (28.5) ran slide rows along the
  cell's path and probed the exported STL. PA-R8 also walked the README step by step. PA-R6 was the shortest review,
  at 12.9.

### What gated the score (PALOG run summary)
1. **Each fix brought the next blocker.**
   - A2: the teardrop bore for a flat fin print removed the wall the stop pin bore on (PA-A2-T9).
   - A5: the printed bench cradle could not take the 50 kg cell's load (PA-A5-T23).
   - A6: the setting plug's 2.1 mm lip took the whole pull-stop load (PA-A6-T16).
   - A7: the 45 deg cell slot was 0.2 mm short (PA-A7-T14).

   None of these new parts had rows for its own load or assembly case until a reviewer wrote them.
2. **A bought part that could not be fitted stayed invisible to cad check for 2+ rounds** (PA-A7-T7, PA-A7-T19). Two
   defaults hid it, both verified in `cadcheck.py` by PALOG and unchanged on `next`:
   - an allow on a pair drops that part from `slide_out` sweeps (`cadcheck.py:1833`);
   - `insertion` skips parts of the same step and tries only ±XYZ plus `insert_dirs` (`cadcheck.py:2450`).

   PA-A8-T1 and PA-A8-T10 worked around both through config: the allow was narrowed, the cartridge moved to an
   earlier step, and the 45 deg line went in `insert_dirs`.
3. **Some fixes needed decisions outside the designer's authority:** the cell size, the outer outline and
   soldering. The coordinator reframed them ("Alex decides", "external outline only") instead of asking (PA-A4-T21,
   PA-A5-T24, PA-A6-T1, PA-A7-T1, PA-A8-T3). PA-R5 scored F against the cell the BOM recommended, not the one in the
   model, and F rose 7 -> 8 partly from that framing (PA-A5-T24).
4. **Every stress row assumed solid sections, and no part had a print spec** (PA-A8-T13). This surfaced only in
   the last round. Eight rounds of stress rows used solid I and Z, and the 3MFs carry no slicer settings. PA-R8
   found 133 MPa at the piston mouth at slicer defaults.

### Tool candidates, ranked by evidence, with their status on `next` (`2e6717d`)

**Planned** means a PR into `next` is planned, from the gaps listed in PR #7 ("Known gaps") and the feature docs.
**Open** means nothing on `next` addresses it and no PR is planned.

| # | Candidate (PALOG) | PA IDs | Status |
|---|---|---|---|
| 1 | `slide_out`: keep allowed pairs as obstacles, bounded by `max_mm3`, instead of dropping them | PA-A7-T19a, PA-A8-T6 | Open. `cadcheck.py:1833` drops any part allowed against the mover unless it is listed in `flex` |
| 2 | `insertion`: test same-step parts in order; warn when a `BUY_` part shares a step with the `PRT_` it seats in; take off-axis approach directions from features, or warn | PA-A7-T19b/c, PA-A7-T17 | Open. The `cadcheck.py:2450` docstring still says "parts of the same step are placed in any order". Config workaround: PA-A8-T10 |
| 3 | A first-class `calcs` block (`value` `=expr`, min/max, unit, why) instead of stacks used as calcs | PA-A6-T9, PA-A1-T10, PA-A3-T23 | Open. Agents put calcs in `stacks` rows with a single `=expr` term. The report calls those "worst case / RSS", and `abs()` hides the sign |
| 4 | Per-part print settings (walls, infill, material) in the manifest, written to 3MF metadata, used for I_eff in calcs | PA-A8-T13 | Open. Prior art: `asm.part(infill=)` is stored per printed part, but only cadcheck's mass and time estimate reads it (`cadcheck.py:780`, with a fixed 0.84 mm shell). It has no walls or material, is not in the 3MF, and no calc uses it |
| 5 | Report allows that measure 0 overlap at every pose as unused | PA-A8-T6 | Open |
| 6 | A command that locates overhang and steep regions and roof spans per part in print orientation, plus a per-layer section view | PA-A2-T7, PA-A5-T27, PA-A8-T15 | **Partly planned:** the printcheck overhang-gap PR adds a face-normal overhang pass. Its regions get locations like the layer findings (`docs/features/blend-bracket.md` "The printcheck gap", PR #6, PR #7). The per-layer text view (`layer_ascii`, `roof_ascii`) is not planned |
| 7 | cadcheck config hygiene: warn on unknown config keys; checks named in `--only` with no rows go to `not_checked`; report stale accepts under `--only`; `accepted_warns` match by check and kind, not substring | PA-A2-T11, PA-A4-T6, PA-A4-T10 | Open. `cadcheck.py:3111-3115` is unchanged: `a["match"] in w`, and `stale = [] if ONLY` |
| 8 | `check_stacks`: a failed `=expr` (None) is a config FAIL, not a TypeError crash (verified) | PA-A5-T26 | Open. `cadcheck.py:2566` still runs `float(t["tol"])` |
| 9 | `G.csg`: new cut faces get the target's material (verified in use, patched per project) | PA-A4-T14 | Open. `geom.csg` sets no material |
| 10 | Moving sub-bodies of a printed part (a flexure link) without hand-splitting; the flexures check computes stress and buckling instead of taking a typed number | PA-A3-T21, PA-A3-T22, PA-A4-T15, PA-A4-T27 | Open. `geom.swept_envelope` (PR #4) makes keep-outs for a whole moving part. It does not split one printed part. `=param` stress (PA-A4-T16) is the workaround |
| 11 | A material allowables table (PLA in-layer and across-layer, PETG), so row limits aren't chosen per agent | PA-A6-T10 | Open |
| 12 | interference: nothing checks nuts (FST) against PRT parts on the same body | PA-A2-T12 | **Planned:** the fastener head/nut vs same-body parts check (`docs/features/fastener-joint.md` "cadcheck gap found in review"; PR #7 "screw heads and nuts against same-body parts are unchecked"). Covers PA-A2-T12 |
| 13 | An STL reader for bought parts that handles ASCII and binary | PA-A3-T9, PA-A5-T13 | Open for plain Python, where both failures happened. Inside Blender, `geom.import_stl` (Blender's importer) already reads both formats |
| 14 | Fastener access: report where a straight bit would clear, so placing a screw isn't trial and error (13.7 min for one M4, PA-A3-T10) | PA-A3-T10 | Open. `fastener_joint` (PR #2) sizes and places a screw at a given point. It does not search for an access position |

**The planned PRs, mapped to PA findings:**
- **printcheck overhang gap.** Covers #6 in part. It also bears on PA-A2-T2 and PA-A2-T13, which are unverified
  (see below).
- **cadcheck sweep step.** PR #6's "between-frame bound for sweep step sizing" and PR #7's "joint sweeps too coarsely
  for long reach". It addresses no PA finding: the loop's sweep misses came from the obstacle set (#1) and from
  same-step parts (#2), not from step size.
- **fastener head/nut vs same-body parts.** Covers #12 (PA-A2-T12).

**PRs #2-#4, already merged, mapped to PA findings.** The loop had all three and called none of them (see "Which
tools").
- **#2 `features.fastener_joint`.** PA-R1 #1's screws gripped nothing or sat 6 mm off the wall, and cad check only
  warned (PA-A1-T8). Called on the finished parts, `fastener_joint` raises on those: thread under 2 d, more than
  0.3 mm of air in the stack, material on the head seat. Engagement in shank diameters was in the loop's cadcheck
  already. #2 does not address PA-A3-T10 (#14).
- **#3 `cadlib.route`.** No tool candidate. It is relevant to two reviewer cable issues, PA-R1 #9 (the patch cable
  kinks at R2.8 for OD 5) and PA-R3 #7 (a 149.97 mm path for a 150 mm cable), because the router reports bend radius,
  length and slack. PA-R8 #2 (a Qwiic jumper ties the two tray halves together) is about assembly order, which the
  router doesn't cover.
- **#4 `cadlib.blend`, `geom.swept_envelope`.** No PA finding. Its review produced the printcheck-gap report behind
  the planned overhang PR.

### Skill and checklist candidates (`cad-design-review`, `print-cad-blender`)

| Candidate (PALOG) | PA IDs | Status |
|---|---|---|
| Checklist: every bought part can reach its seat along a stated path (slide rows), with clearance > 0 | PA-A7-T15, PA-A8-T7 | Open. `checklist.md:25` asks only whether bench sub-assemblies can be lifted in. PA-R7 did the walk unprompted; PA-R8 did it because the prompt asked (PA-A8-T12). PA-A8-T7 is the part on clearance: the cell path passes `slide_out` at 0.0 mm |
| Checklist: load-path parts have a print spec | PA-A8-T13 | Open |
| SKILL step 2: audit `accepted_warns` the way `allow` and `fits` are audited; check `ignore` lists in adapted rows | PA-A3-T24, PA-A5-T17 | Open. Step 2 names `allow` and `fits` only. PA-R4 and PA-R5 audited the accepts unprompted (PA-A4-T27, PA-A5-T28). PA-R3 did not, and its 0.58 mm wall stayed under an accept (PA-A3-T28) |
| SKILL: write review rows against params (`=param`), not literals, so they survive redesigns | PA-A7-T9, PA-A3-T15 | Open in the review SKILL. `=EXPR` rows have existed since `dea6536`. Old rows broke 3 times on redesigns (PA-A3-T15, PA-A4-T22, PA-A5-T18) |
| SKILL step 0: notes go in as you go (the restart case) | PA-A1-T1 | **Already there** in `49aa21f`'s step 0, which cites A3-T4. PA-R1 still wrote `notes.md` in one Write at 0:12:18. Reviewers appended as they went from PA-R2 on, once the loop prompt named the file (PA-A2-T6, PA-A2-T15). The prompt changed the behaviour; the skill's wording did not |
| Point SKILL step 2 at `reference/checks-config.md` for row schemas | PA-A1-T3 | Open. `print-cad-blender/SKILL.md:79` points there, but `cad-design-review` never mentions it |
| Designer done-criteria: adopt the previous review rows, and walk the assembly guide as a strict self-reviewer. The self-walk found 5 real issues in A8 (PA-A8-T8), though not the L-key gap (PA-A8-T14) | PA-A2-T10, PA-A8-T8 | Row adoption: already in the v2 workflow template (`templates/cad-loop.workflow.js:161, 242`: the planner merges `review_rows.json`). This loop was a hand-written `/loop` prompt and added the line itself from A3 on (PA-A3-T1). Self-walk: in the loop prompt only (PA-A7-T3, PA-A8-T2). Open for both skills |

### Loop-prompt candidates (for the next `/loop` prompt; not skill changes)

| Candidate (PALOG) | PA IDs | Status |
|---|---|---|
| Pass the user's seeded defects to reviewer 1 as previous issues | PA-A1-T13 | Open. The `/loop` prompt is the user's, and no file in this repo holds it |
| Ask the user when a fix needs a decision outside the brief, instead of reframing it | PA-A5-T24, PA-A7-T1 (also PA-A4-T21, PA-A6-T1, PA-A8-T3) | Open |
| The score history in reviewer prompts didn't visibly anchor scores | PA-A4-T28 | Observation only; no change proposed |
| Render-only geometry (drive recesses, materials) shouldn't count toward aesthetics | PA-A4-T12, PA-A8-T9 | Open. `rubric.md` says nothing about render-only detail |

### Not verified (reviewer or designer claims only, as PALOG marks them)
- **`slide_out` at-rest contact (PA-A3-T16).** The designer says "the slide test ignores the at-rest facet contact",
  meaning a part touching at 0 gap doesn't block at step 0. Not tested. Related: the cell path in PA-A8-T7 passes at
  0.0 mm.
- **printcheck missing overhangs that `overhang_gt_45_mm2` sees (PA-A2-T2, PA-A2-T13, partly).**
  - The case: on the piston, printcheck flagged the 2,211 mm² spigot underside but not 821 mm² over 45 deg on the
    body. PA-R2's own script says that face is over a void and harmless.
  - The general gap is reproduced separately: gradual 5-40 deg overhangs pass printcheck
    (`docs/features/blend-bracket.md` "The printcheck gap"), and PR #7 calls it "confirmed by user prints".
  - Whether the piston is an instance of that gap was not checked.
- **Where the "printcheck misses overhangs" note came from.** It first appears in the coordinator's PA-R2 prompt
  (`PASESS.jsonl` #149, 22:49:33) as "Known tool bug (from the user)". Every later designer and reviewer prompt
  repeats it. No user line in `PASESS` has it (`cc_transcript.py grep`).
- Also marked unverified in the attempt notes:
  - PA-A7-T7's "possibly true since A5 or earlier". Only A6 and A7 are established.
  - The Qwiic Scale footprint is "from a forum reading of SparkFun's Eagle files, not verified on a board"
    (PA-A7-T8, PA-R7 #8). PA-R8 #10 also lists purchased parts as unverified.
  - The firmware was only syntax-checked, never compiled for a board (PA-A5-T19, PA-A6-T6).

**PA-A0-T2: the designers' last `cad check` was an `--only` run, 3 of 3** (added after the loop from the transcripts). The designers of attempts 3, 6 and 7 are the only designers that ran `cad check`, and each ended on a partial one, so each handed off on a report that said PASS for the checks it ran. Count: `python3 -I tools/transcript/cc_transcript.py handoffs ~/.claude/projects/-Users-alxchunlin-code-stuff-space-bar-push-assist/*/subagents/agent-*.jsonl` (the Designer rows). Reviewers also ended on `--only` runs (5 of 5) by their instructions, which is expected. Fixed by cadcheck issue #28: `CADCHECK PARTIAL`, `run` in the report, `cadcheck.partial.json`.

### Verification of this harvest
- PALOG is byte-identical to the untracked source (`sha256 0a5f90f3...`).
- Scores and cad check / printcheck cells match `PA/cad/review/attempts.md`. Issue counts were taken from PALOG's
  ranked lists.
- Every cost number comes from `cc_transcript.py workflow PASESS/subagents`, or from `usage` / `timeline` on
  `PASESS.jsonl` for the two inline windows. No transcript was read whole.
- Every PA ID in this section exists in PALOG, except PA-A0-T1 and PA-A0-T2, which were added after the loop from the transcripts. Each status was checked against `2e6717d`: `cadcheck.py` line refs,
  SKILL.md, checklist.md, rubric.md, the workflow template, the feature docs, and PR #6 and #7 bodies.
- `tools/verify_all.sh` was not run: this change is docs only.
