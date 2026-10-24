# Findings: agent-driven printable CAD (mm-launcher loop)

Running evidence log. Each revision run adds an `## Attempt N` section. Every rule or tool in this repo
should point at an ID here (for example `A1-T3`).

Sources are abbreviated:
- `HW` = `~/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/`
- `WF` = `~/.claude/projects/-Users-alxchunlin-code-stuff-mmlauncher-mm-launcher/c043264a-30c7-474d-8ca2-0c2301d01041/subagents/workflows/`
- `D1` = designer attempt 1, `WF/wf_26e26b28-15e/agent-af2e15ae070705e95.jsonl`
- `R1` = reviewer attempt 1, `WF/wf_26e26b28-15e/agent-a4e34520e7cf12eb4.jsonl`
- `D0` = the killed designer, `WF/wf_ebc9f356-a79/agent-a0e1dc96a1cba327c.jsonl`
- `D2` = designer attempt 2 (still running at harvest time), `WF/wf_26e26b28-15e/agent-a6815d61faa83f67e.jsonl`

Timestamps like `D1 0:17:41` are elapsed time from the agent's first message, as printed by
`tools/transcript/cc_transcript.py timeline`. All numbers below come from that tool unless stated otherwise.

---

## Attempt 1 (harvested 2026-10-24)

### Per-agent cost

| Agent | Wall | Model time | Tool time (Blender) | API calls | Output tok (thinking) | Cache read | Cache write | Peak context | Images read | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| D0 (killed) | 43.6 min | 38.5 | 0.1 (0.1) | 13 | 193k (186k) | 0.5M | 0.41M | 237k | 9 | 6 KB plan only |
| D1 | 64.0 min | 61.6 | 2.4 (2.3) | 60 | 378k (255k) | 19.2M | 0.91M | 522k | 29 | 35 parts, 84 KB script |
| R1 | 18.6 min | 18.2 | 0.4 (0.3) | 42 | 103k (71k) | 7.6M | 0.31M | 313k | 33 | 5 / 6 / 5 |
| D2 (first 24 min) | 24.1+ | 24.0 | 0.1 | 13 | 134k (131k) | 1.0M | 0.38M | 245k | 10 | running |

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
`build_assembly.py` in chunks to find parameters and part intent (`R1 #21-23, #26, #30, #34, #42`), with
70-104 s of thinking before each. It then wrote 10 throwaway measurement scripts (`/tmp/rv_*.py`). A
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

### Implications for tooling (what this run built, see STATUS.md)

1. A geometry/assembly library and project scaffold, so the designer writes only design-specific code (A1-T1, T3, T7).
2. One check runner over **all** collections, with joint sweeps beyond the limits, contacts reported, fastener sanity and screw access, a drop-path simulator, slide-out, and a coverage list in the JSON (A1-F1…F14).
3. A part manifest written by the build, and a measure CLI (A1-T8).
4. A reviewer rubric with anchors and an evidence checklist (reviewer quality).
5. An orchestration template with checkpoints, milestones, progress files and short generation steps (A1-T1, T4, T9).
6. **No** Blender daemon or MCP server: the measured cold start is 0.7 s (A1-T2).
