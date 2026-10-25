# Status (updated 2026-10-25, after the revision run for v2 attempt 1)

## Ingested
- v1 (the no-tools baseline, attempts 1-3) is complete. Its rows are below; details are in FINDINGS A1-A3.
- **v2 attempt 1**, all 7 agents (FINDINGS "v2 Attempt 1"; agent ids under `V2WF` in the FINDINGS header). It ran
  on tools `2197aac`, before the A3 fixes. v2 A2 runs on `6b62667`. **This run's fixes reach v2 attempt 3.**
- Not yet ingested: v2 plan #2 and the builds after it, in `V2WF = WF/wf_8db95a5a-12a/`.
- Archived blends: `examples/mm-launcher-{a1,a2,a3,v2a1}/`, each the blend its reviewer saw, with its checks.json.
  v2a1 also has `overlay_drop.json` and `overlay_fits.json`, the rows R1 showed were missing.

## What exists, and what is proven (`sh tools/verify_all.sh`: 45/45 pass, about 9 min)

| Piece | Proven by |
|---|---|
| `tools/transcript/cc_transcript.py` | FINDINGS cost tables. It now counts `cad` wrapper runs as Blender runs (V2A1-T7) |
| `skills/print-cad-blender`: cadlib, cadcheck, cadq, `cad`, template, references | regressions A1 (7), A2 (15 fails exactly), A3 (2 fails exactly), **v2 A1** (3 open-end stall fails exactly, plus the hood-coverage warn, journals measured, 864-pose stability, missing-object row, unflooded section); demo clean and `--bug` 4/4; template build, `--out`, `cad check` argument parsing |
| cadcheck additions this run | missing objects become one fail (no crash); `--overlay` (repeatable) and `--overlay-only`; `accepted_warns` with an `untriaged_warns` count; drop coverage warn for a joint held at home; service warn for unproven removal; fits `contact_normal`; nested bench merges; `pose_grid` keeps in-range limits; stability sampler (lo/home/hi, continuous every 45°) |
| cadlib/cad fixes | `render.section` cuts closed solids with Manifold; `cad q section` takes X or x; `cad build x.py -- args`; `cad check` doesn't swallow flags; `cad build` exports `CAD_SKILL`; M2.5 fastener specs |
| `skills/cad-design-review` | **first real use: v2 R1, 14.7 min, 7/7/6, 12 issues and 8 config disputes.** It now says to put added rows in `review/review_rows.json` with `--overlay`, to treat untriaged warns as leads, and to test adjusters at both ends |
| `templates/cad-loop.workflow.js` | dry run, sequential and parallel. New: `parallel_builds` (opt-in, untested live), `stop_after`, an issue cap, warn triage in finish, review_rows.json, a "## Tool issues" note. The v2 loop uses its own copy, so **template edits reach v2 only if the user adopts them** |

## v1 baseline vs v2

| Attempt | Wall (design + review) | Output tok | F/M/A | Issues B/M/m | Peak ctx | Caught before review |
|---|---|---|---|---|---|---|
| v1 1 | 82.6 min | 481k | 5/6/5 | 18 | 522k | counterfactual 7 |
| v1 2 | 97.0 | 520k | 6/5/6 | 1/3/6 | 698k | counterfactual 8 of 10 |
| v1 3 | 66.1 | 352k | 6/6/6 | 0/4/4 | 488k | counterfactual 6 of 8 |
| **v2 1** | **187.5** (builds in series: 136.6) | **902k** | **7/7/6** | 0/5/7 | 348k | real: 3 of 12, as warns nobody acted on; now 4 |

v2 A1 beat v1's final score after one attempt, but cost 2.3x v1 A1's time. The main sinks:
- four builders run in series;
- 65 min of builder time before the first edit;
- tool source reads and tool bugs (15 failed `cad` runs).

## Known gaps
- No payload-fit check, such as two candies in one pocket (V2A1-F3). R1 used a probe script.
- Exposure covers cables and nuts, not PCBs (V2A1-F11).
- No insertion sweep for assembly merge steps (V2A1-F6); for now that needs a `slide_out` row.
- Rows nobody writes (V2A1-F2, F4, F6): only the checklist, the planner prompt and review_rows.json push on these.
- From v1, still open: channel width along a payload path; a swept-envelope helper; stall and interlayer limits are
  estimates; nut wrench access, cable bend radius, teardown count.

## Next (revision run for v2 attempt N)
1. Run `cc_transcript.py workflow <V2WF>`, then `summary` per new agent. Compare against the table above.
2. Read `HW/v2/renders/attempt-N/{progress.md,cadcheck.json,review.json}`:
   - "## Tool issues" in progress.md;
   - `check_config_disputes`;
   - `tool_catchable` issues; for each, did cadcheck flag it at hand-off (fail, or warn left untriaged)?
3. v2 A2 runs on `6b62667` and doesn't have this run's fixes, so expect the T3/T4/T5 bugs to recur there. Attribute
   them to the pin, not to new problems. v2 A3 is the first attempt with overlay, accepted_warns and the drop coverage
   warn: check whether designers use them.
4. Run `sh tools/verify_all.sh` before every commit, because `main` feeds the next v2 attempt.
