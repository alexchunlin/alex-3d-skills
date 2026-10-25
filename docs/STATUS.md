# Status (updated 2026-10-25, after the revision run for v2 attempt 2)

## Ingested
- v1 (the no-tools baseline, attempts 1-3) is complete. Its rows are below; details are in FINDINGS A1-A3.
- **v2 attempts 1 and 2**, all agents (FINDINGS "v2 Attempt 1" and "v2 Attempt 2"; agent ids under `V2WF` in the
  FINDINGS header). v2 A1 ran on tools `2197aac`, v2 A2 on `6b62667`, and v2 A3 runs on `f039205`. **This run's fixes
  reach v2 attempt 4.**
- Not yet ingested: v2 plan #3 and everything after it, in `V2WF = WF/wf_8db95a5a-12a/` (journal line 33 onward).
- Archived blends: `examples/mm-launcher-{a1,a2,a3,v2a1,v2a2}/`, each the blend its reviewer saw, with its checks.json.
  v2a1 has `overlay_drop.json` and `overlay_fits.json`; v2a2 has `overlay_v2a2.json`. Those are the rows each
  reviewer showed were missing.

## What exists, and what is proven (`sh tools/verify_all.sh`: 54/54 pass, about 11 min)

| Piece | Proven by |
|---|---|
| `tools/transcript/cc_transcript.py` | FINDINGS cost tables. It counts `cad` wrapper runs, but not a reviewer's own wrapper script (V2R2's `./q`) |
| `skills/print-cad-blender`: cadlib, cadcheck, cadq, `cad`, template, references | regressions A1 (7), A2 (15 fails exactly), A3 (2 fails exactly), v2 A1 (3 fails exactly, plus 4 patterns), **v2 A2** (designer config: 0 fails plus 4 new config warns; overlay: exactly 4 fails, 2 of them planted); demo clean and `--bug` 4/4; template build, `--out`, `cad check` argument parsing, `cad py` |
| cadcheck additions this run | **`payload_fit`** (lens/ellipsoid/sphere/cylinder probes, flat, edge-on, pair or stack, with a bisected size margin); **`sightlines`** (first-hit rays in a joint frame); `slide_out` `expect: "blocked"` with `blocked_by`/`at_mm`; **`assembly` audit** (`step_of`, objects in no step, step label vs screw size); ray-vs-nearest warn in `distances`; cables with no lead; a `compliant` part with no flexures row |
| cadq/cad fixes | `cad q` alone prints help, a short command prints its usage line; `ray --frame PIV_x`; `--lentil` takes a bare point; **`cad py`** (Python with bpy, cadlib and the project on the path) |
| `skills/cad-design-review` | v2 R1 14.7 min (7/7/6), v2 R2 18.5 min (8/8/9). It now says to cite `assembly.step_of` for config claims (V2R2 made a false one) and to write payload, sightline and stop rows instead of probe scripts |
| `templates/cad-loop.workflow.js` | dry run, sequential and parallel. New: the planner runs its new rows on the current model first (each must fail there), and covers springs at full deflection. The v2 loop uses its own copy, so **template edits reach v2 only if the user adopts them** |

## v1 baseline vs v2

| Attempt | Wall (design + review) | Output tok | F/M/A | Issues B/M/m | Peak ctx | Caught before review |
|---|---|---|---|---|---|---|
| v1 1 | 82.6 min | 481k | 5/6/5 | 18 | 522k | counterfactual 7 |
| v1 2 | 97.0 | 520k | 6/5/6 | 1/3/6 | 698k | counterfactual 8 of 10 |
| v1 3 | 66.1 | 352k | 6/6/6 | 0/4/4 | 488k | counterfactual 6 of 8 |
| v2 1 | 187.5 (builds in series: 136.6) | 902k | 7/7/6 | 0/5/7 | 348k | real: 3 of 12, as warns nobody acted on; now 4 |
| **v2 2** | **150.0** (builds 114.4; launcher alone 45.0) | **524k** | **8/8/9** | 0/2/6 | 340k | real: 2 of 6 tool-catchable, as unread warns; now 5, and the 6th with a `payload_fit` row |

v2 A2 scores 25 against v1's best of 18, and it cost 20% less than v2 A1. Each v2 attempt still costs 1.5 to 2.3 times
a v1 attempt. The pattern is the same in both v2 attempts: the checks existed, and issues got through as **unread warns
and rows nobody wrote**. The one recurring issue (two candies in a pocket) was the one with no check; it has one now.

## Known gaps
- No prismatic joint in cadlib: a slide gate's open state is outside the interference sweep (V2A2-T4).
- Exposure covers cables and nuts, not PCBs (V2A1-F11). No insertion sweep for assembly merge steps (V2A1-F6).
- Rows nobody writes (full-deflection gaps, hard stops, adjuster ends): only the SKILL, the checklist, the planner prompt
  and review_rows.json push on these. The drop coverage warn names the held joint.
- `parallel_builds` is untested live; the v2 script hasn't adopted it.
- From v1, still open: channel width along a payload path; a swept-envelope helper; stall and interlayer limits are
  estimates; nut wrench access, cable bend radius, teardown count.

## Next (revision run for v2 attempt N)
1. Run `cc_transcript.py workflow <V2WF>`, then `summary` per new agent. Compare against the table above.
2. Read `HW/v2/renders/attempt-N/{progress.md,cadcheck.json,review.json}`:
   - "## Tool issues" in progress.md;
   - `check_config_disputes`;
   - `tool_catchable` issues; for each, did cadcheck flag it at hand-off (fail, or warn left untriaged)?
   - verify every reviewer config claim against cadcheck.json (V2A2-R1).
3. v2 A3 runs on `f039205`: the first attempt with `--overlay`, `accepted_warns`, the drop coverage warn and
   `contact_normal`. Check whether designers triage warns and whether the reviewer uses review_rows.json. Expect
   payload-fit probes and hand `cad q` usage reads to recur there (fixed here, reaching A4).
4. Run `sh tools/verify_all.sh` before every commit, because `main` feeds the next v2 attempt. Don't edit
   verify_all.sh while it runs: sh reads it incrementally.
