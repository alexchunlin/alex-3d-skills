# Status (updated 2026-10-25, after the revision run for v2 attempt 4)

## Ingested
- v1 (the no-tools baseline, attempts 1-3) is complete. Its rows are below; details are in FINDINGS A1-A3.
- **v2 attempts 1-4**, all agents (FINDINGS "v2 Attempt 1" to "v2 Attempt 4"; agent ids under `V2WF` in the FINDINGS
  header). v2 A1 ran on tools `2197aac`, A2 on `6b62667`, A3 on `f039205`, A4 on `a20a4d7`, and **A5 runs on
  `dea6536`**. This run's fixes reach **v2 attempt 6**.
- Not yet ingested: v2 plan #5 and everything after it, in `V2WF = WF/wf_8db95a5a-12a/` (journal line 66 onward).
- Archived blends: `examples/mm-launcher-{a1,a2,a3,v2a1,v2a2,v2a3,v2a4}/`, each the blend its reviewer saw, with its
  checks.json. The v2 ones carry overlays of the rows each reviewer showed were missing; v2a3 and v2a4 also have their
  manifest.json and BOM.

## What exists, and what is proven (`sh tools/verify_all.sh`: 71/71 pass, about 15 min)

| Piece | Proven by |
|---|---|
| `tools/transcript/cc_transcript.py` | FINDINGS cost tables. It counts `cad` runs, not a reviewer's own wrapper script |
| `skills/print-cad-blender`: cadlib, cadcheck, cadq, `cad`, template, references | regressions A1 (7), A2 (15 fails exactly), A3 (2 fails exactly), v2 A1 (3 fails exactly), v2 A2 (0 fails plus 4 config warns; overlay 4 fails), v2 A3 (designer config: 0 fails, 1 untriaged warn, the real M3 x 9; overlay: 3 fails exactly plus a zero-margin pocket), **v2 A4** (designer config: 0 F, 0 untriaged, 6 stale false-warn accepts, 8 past-limit poses listed; swept overlay: 3 fails exactly); demo clean and `--bug` 4/4; **slide-gate clean and `--bug` 6/6**; template, `cad py`, `cad q` |
| cadcheck changes this run (v2 A4) | **`ray.sweep`**: a distances ray turned over a passage, worst station plus profile (V2R4's major as one row: 7.50/7.67/7.95 at psi 80, V2A4-F1); **poses past a joint's range** listed in the summary, and a pose on no joint or a coupled one is a config fail (V2A4-T2); **stale-model warn** when sources are newer than the blend, never acceptable (V2A4-T1) |
| `cad` wrapper this run | `cad build` exits non-zero and prints `BUILD FAILED` when the script raises: Blender exits 0 on a script error, and `run()` ended in `|| true` (V2A4-T1). `cad rows` prints a swept profile |
| cadcheck changes (v2 A3 run, in `dea6536`) | **ray-slip warn** replaces ray-vs-nearest (9 for 9 false on v2 A3, V2A3-T2); **inscribed-circle bridge span** (bbox was false for arcs and rotated slots); **`=EXPR` values** over the build's params anywhere a number goes; **prismatic joints** in every sweep (`overtravel_mm`); slide **`flex`** bounds for detents; **`cable_chains`** and a junction warn; **stock screw lengths**; a no-pose service op is proved by a home slide row; no stale-accept list under `--only` |
| New commands | **`cad rows`** (one line per report or manifest row, plain python3; v2 A3 wrote 67 `json.load` snippets); **`cad bom`** (BOM fastener table vs manifest: exactly V2R3's 2 BOM errors on A3) |
| cadlib | `asm.joint(prismatic=True)`; params stored in the .blend (`cad_params`); cable ends (`cab_ends`); `M3_hex` spec |
| `skills/cad-design-review` | v2 R1 14.7 min (7/7/6), R2 18.5 (8/8/9), R3 14.8 (8/8/8), R4 12.8 (8/9/9). Now: sweep a passage gap, not one station; grep with `cad rows`, `cad bom` in the checklist, max-payload rows from params, cable chains, prismatic gates |
| `templates/cad-loop.workflow.js` | dry run, sequential and parallel. New this run: the planner sweeps a passage gap with `ray.sweep` (V2A4-F1). Earlier: rows as `=EXPR` at the declared extremes (planner), `cad bom` (finish), `cad rows` (all). The v2 loop uses its own copy, so **template edits reach v2 only if the user adopts them** |

## v1 baseline vs v2

| Attempt | Wall (design + review) | Output tok | F/M/A | Issues B/M/m | Peak ctx | Caught before review |
|---|---|---|---|---|---|---|
| v1 1 | 82.6 min | 481k | 5/6/5 | 18 | 522k | counterfactual 7 |
| v1 2 | 97.0 | 520k | 6/5/6 | 1/3/6 | 698k | counterfactual 8 of 10 |
| v1 3 | 66.1 | 352k | 6/6/6 | 0/4/4 | 488k | counterfactual 6 of 8 |
| v2 1 | 187.5 (builds in series: 136.6) | 902k | 7/7/6 | 0/5/7 | 348k | real: 3 of 12, as warns nobody acted on; now 4 |
| v2 2 | 150.0 (builds 114.4) | 524k | 8/8/9 | 0/2/6 | 340k | real: 2 of 6 tool-catchable, as unread warns; now 5 |
| v2 3 | 145.8 (plan 22.2, builds 108.0, review 14.8) | 474k | 8/8/8 | 0/1/5 | 257k | real: 0 of 6 (all 34 warns triaged); now 5 of 6, 3 of them with a row |
| **v2 4** | **91.5** (plan 8.3, builds 69.4, review 12.8) | **266k** | **8/9/9** | **0/1/2** | **200k** | real: **0 of 1** tool-catchable (0 untriaged); now 1 of 1 with a swept row |

v2 A4 is the best attempt of all seven: the highest score (26), the fewest issues, 37% less wall time than v2 A3, no
generation over 120 s, and within 1.4x of v1's wall time. The one major is A2-01 for the third attempt running, and
each time the designer fixed exactly what the last row measured (travel, then the max candy, now BDC only, while the
entry arc squeezes). The misses are now **rows that are too narrow**, not missing rows or unread warns.

## Known gaps
- Rows that are too narrow are the main leak: one station of a passage (V2A4-F1), the nominal payload (V2A3-F1).
  `ray.sweep` and `=EXPR` make the right row cheap; only the SKILL, the checklist and the planner prompt ask for them. A
  swept ray is 1-D: a tilting candy or a passage that isn't an arc or a line needs a payload-pass probe.
- Edge-break consistency is not measurable; gear tooth tips still read as thin walls.
- Exposure covers cables and nuts, not PCBs (V2A1-F11). No insertion sweep for assembly merges (V2A1-F6).
- Cable junctions need cadlib-stored ends (fresh builds only). `parallel_builds` is untested live.

## Next (revision run for v2 attempt N)
0. v2 A5 runs on `dea6536`: the first with `cad rows`, `cad bom`, `=EXPR`, prismatic joints, slide `flex`,
   `cable_chains` and the ray-slip / inscribed-bridge fixes. Expect A4's 6 false-warn accepts to show as stale in A5's
   first check. Check whether the A2-01 rows get swept by hand (A5 has no `ray.sweep`) and whether the gate becomes a
   prismatic joint.
1. Run `cc_transcript.py workflow <V2WF>`, then `summary` per new agent. Compare against the table above.
2. Read `HW/v2/renders/attempt-N/{progress.md,cadcheck.json,review.json}`:
   - "## Tool issues" in progress.md;
   - `check_config_disputes`;
   - `tool_catchable` issues; for each, did cadcheck flag it at hand-off (fail, or an accepted warn)?
   - verify every reviewer config claim against cadcheck.json.
3. Count `json.load` snippets (A3 67, A4 71; FINDINGS V2A4-T4) to see whether `cad rows` gets used from A5, and
   whether `cad bom` runs at finish.
4. Run `sh tools/verify_all.sh` before every commit, because `main` feeds the next v2 attempt. Don't edit
   verify_all.sh while it runs: sh reads it incrementally.
