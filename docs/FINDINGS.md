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
