# Status (updated 2026-10-25, after the revision run for v2 attempt 6)

## Ingested
- v1 (the no-tools baseline, attempts 1-3) is complete. Its rows are below; details are in FINDINGS A1-A3.
- **v2 attempts 1-6**, all agents (FINDINGS "v2 Attempt 1" to "v2 Attempt 6"; agent ids under `V2WF` in the FINDINGS
  header). v2 A1 ran on tools `2197aac`, A2 `6b62667`, A3 `f039205`, A4 `a20a4d7`, A5 `dea6536`, A6 `36189b8`, and **A7
  runs on `6025133`**. This run's fixes reach **v2 attempt 8**.
- Not yet ingested: v2 plan #7 and everything after it, in `V2WF = WF/wf_8db95a5a-12a/` (journal line 94 onward).
- Archived blends: `examples/mm-launcher-{a1,a2,a3,v2a1,...,v2a6}/`, each the blend its reviewer saw, with its checks.json.
  The v2 ones carry overlays of the rows each reviewer showed were missing; v2a3 to v2a6 also have manifest.json and BOM.

## What exists, and what is proven (`sh tools/verify_all.sh`: 79/79 pass, about 21 min)

| Piece | Proven by |
|---|---|
| `tools/transcript/cc_transcript.py` | FINDINGS cost tables. It counts `cad` runs, not a reviewer's own wrapper script |
| `skills/print-cad-blender`: cadlib, cadcheck, cadq, `cad`, template, references | regressions A1 (7), A2 (15 fails exactly), A3 (2 fails exactly), v2 A1 (3 fails exactly), v2 A2-A5 (designer configs and overlays, see FINDINGS), **v2 A6** (designer config: 0 F, 11 untriaged = V2R6's 3 issues as 8 warns plus 3 step facts; with the step facts declared only the 2 A6-01 warns remain; V2R6's slide row fails on the groove cap); demo clean and `--bug` 4/4; slide-gate clean and `--bug` 6/6; bevel clamp test; template, `cad py`, `cad q` |
| cadcheck changes this run (v2 A6) | **`insertion` check**: each part and each bench group at its merge, out in a straight line (±XYZ, screw axes, `insert_dirs`, at the step's `pose`) past the earlier steps' parts, plus a warn for a bench part far from its group (V2A6-F1: the splice in the feeder's bench step; the feeder merge "+Z PRT_groove_cap (BUY_bus_junction) at 3"). **`cables.end_drift`**: ends that meet across a joint, followed to each limit (V2A6-F2: 8.8 and 5.7 mm). **Swept ray missed station warns** on `min` rows (V2A6-F3). `parts` warns on `bevel_clamped` |
| cadlib (v2 A6) | `geom.bevel` measures its vertex moves and flags a globally clamped edge break (V2A6-T2: n=768 cut, 1.0 -> 0.01) |
| `cad rows` (v2 A6) | `--summary` (counts, coverage, not_checked, step_of); insertion `blocked` per direction |
| `cad rows` (v2 A5) | `cad rows checks.json [REGEX]` prints config rows; drop stall points printed (V2A5-T4) |
| cadcheck changes (v2 A4 run, in `36189b8`) | **`ray.sweep`**: a distances ray turned over a passage, worst station plus profile (V2R4's major as one row: 7.50/7.67/7.95 at psi 80, V2A4-F1); **poses past a joint's range** listed in the summary, and a pose on no joint or a coupled one is a config fail (V2A4-T2); **stale-model warn** when sources are newer than the blend, never acceptable (V2A4-T1) |
| `cad` wrapper (v2 A4 run) | `cad build` exits non-zero and prints `BUILD FAILED` when the script raises: Blender exits 0 on a script error, and `run()` ended in `|| true` (V2A4-T1). `cad rows` prints a swept profile |
| cadcheck changes (v2 A3 run, in `dea6536`) | **ray-slip warn** replaces ray-vs-nearest (9 for 9 false on v2 A3, V2A3-T2); **inscribed-circle bridge span** (bbox was false for arcs and rotated slots); **`=EXPR` values** over the build's params anywhere a number goes; **prismatic joints** in every sweep (`overtravel_mm`); slide **`flex`** bounds for detents; **`cable_chains`** and a junction warn; **stock screw lengths**; a no-pose service op is proved by a home slide row; no stale-accept list under `--only` |
| New commands | **`cad rows`** (one line per report or manifest row, plain python3; v2 A3 wrote 67 `json.load` snippets); **`cad bom`** (BOM fastener table vs manifest: exactly V2R3's 2 BOM errors on A3) |
| cadlib | `asm.joint(prismatic=True)`; params stored in the .blend (`cad_params`); cable ends (`cab_ends`); `M3_hex` spec |
| `skills/cad-design-review` | v2 R1 14.7 min (7/7/6), R2 18.5 (8/8/9), R3 14.8 (8/8/8), R4 12.8 (8/9/9), R5 14.2 (9/8/9). New: measured stacks for toleranced purchased parts, `unbounded_allows`, `cad rows checks.json`. Earlier: sweep a passage gap, not one station; grep with `cad rows`, `cad bom` in the checklist, max-payload rows from params, cable chains, prismatic gates |
| `templates/cad-loop.workflow.js` | dry run, sequential and parallel. New this run: the planner puts a part in the step where it goes in and gives angled steps a `pose`, routes meet on the joint axis; finish checks `checks.insertion` and uses `cad rows --summary` (V2A6-F1/F2). v2 A5 run: the planner tries a shared params change in a /tmp build before planning on it (V2A5-T2), and writes stacks with `between` (V2A5-F1). Earlier: `ray.sweep` for a passage (V2A4-F1), rows as `=EXPR` at the declared extremes (planner), `cad bom` (finish), `cad rows` (all). The v2 loop uses its own copy, so **template edits reach v2 only if the user adopts them** |

## v1 baseline vs v2

| Attempt | Wall (design + review) | Output tok | F/M/A | Issues B/M/m | Peak ctx | Caught before review |
|---|---|---|---|---|---|---|
| v1 1 | 82.6 min | 481k | 5/6/5 | 18 | 522k | counterfactual 7 |
| v1 2 | 97.0 | 520k | 6/5/6 | 1/3/6 | 698k | counterfactual 8 of 10 |
| v1 3 | 66.1 | 352k | 6/6/6 | 0/4/4 | 488k | counterfactual 6 of 8 |
| v2 1 | 187.5 (builds in series: 136.6) | 902k | 7/7/6 | 0/5/7 | 348k | real: 3 of 12, as warns nobody acted on; now 4 |
| v2 2 | 150.0 (builds 114.4) | 524k | 8/8/9 | 0/2/6 | 340k | real: 2 of 6 tool-catchable, as unread warns; now 5 |
| v2 3 | 145.8 (plan 22.2, builds 108.0, review 14.8) | 474k | 8/8/8 | 0/1/5 | 257k | real: 0 of 6 (all 34 warns triaged); now 5 of 6, 3 of them with a row |
| v2 4 | 91.5 (plan 8.3, builds 69.4, review 12.8) | 266k | 8/9/9 | 0/1/2 | 200k | real: 0 of 1 tool-catchable (0 untriaged); now 1 of 1 with a swept row |
| v2 5 | 93.3 (plan 8.5, builds 69.9, review 14.2) | 314k | 9/8/9 | 0/1/5 | 240k | real: 1 of 4 tool-catchable (warned, then waived); now 3 of 4 (F1 fails with `between`, F3/F6 listed) |
| **v2 6** | **76.9** (plan 17.6, builds 45.3, review 9.3) | **213k** | **9/8/9** | **0/1/2** | **193k** | real: 0 of 3 tool-catchable; now 3 of 3 as warns (insertion, end drift, missed stations) |

v2 A6 is the cheapest v2 attempt (76.9 min, 213k output tokens, peak context 193k), at the same score (26). All 6 of
A5's issues are fixed. The one major (A6-01) was a part placed in a bench step that never reaches it: the bus splice in
the feeder's step 10d, though it sits in the pan hub under a groove cap fitted at 2c. Every check at that step passed
by construction, and the new insertion check catches it twice.

## Known gaps
- Insertion is straight-line only and does not test parts of one step against each other. On the v2 A1-A6 configs
  it asks for 3 step facts: poses for the pod and jar steps, and the nip stud in the backplate's step. Expect A8's
  designer to add them.
- Rows whose bound follows the geometry (V2A5-F1) still pass by construction. `between` (in A7) and the insertion check
  cover the two cases seen so far.
- BOM free text vs model: `cad bom` reads fasteners only. Material creep and fatigue are out of scope. cadlib facet
  defaults are not sag-based (V2A6-T3).
- Exposure covers cables and nuts, not PCBs (V2A1-F11). Gear tooth tips read as thin walls. `parallel_builds` is
  untested live.
- Template edits (V2A4 to V2A6) reach v2 only if the user adopts them.

## Next (revision run for v2 attempt N)
0. v2 A7 runs on `6025133`: the first with stacks `between`, `max_mm3`, `cad rows checks.json`. A8 gets the insertion
   check, end drift, missed-station warns, the bevel flag and `cad rows --summary`. In A7, check whether the splice
   access (A6-01) gets a row and whether the pan lead gets a moving tail (A6-02). In A8, count the new insertion warns
   and how long their triage takes. False warns there are a direct cost.
1. Run `cc_transcript.py workflow <V2WF>`, then `summary` per new agent. Compare against the table above.
2. Read `HW/v2/renders/attempt-N/{progress.md,cadcheck.json,review.json}`:
   - "## Tool issues" in progress.md;
   - `check_config_disputes`;
   - `tool_catchable` issues; for each, did cadcheck flag it at hand-off (fail, or an accepted/waived warn)?
   - verify every reviewer config claim against cadcheck.json.
3. Archive the reviewed blend before the next attempt edits the sources: the planner starts within a minute of the
   review, and by 10:38 attempt 7 had already changed `parts/base.py` and `pan_stage.py`.
4. Run `sh tools/verify_all.sh` before every commit, because `main` feeds the next v2 attempt. Don't edit
   verify_all.sh while it runs: sh reads it incrementally.
