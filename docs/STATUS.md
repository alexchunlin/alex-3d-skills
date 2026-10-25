# Status (updated 2026-10-25, after the printability and slicing task; before it, the revision run for v2 attempt 7)

## Ingested
- v1 (the no-tools baseline, attempts 1-3) is complete. Its rows are below; details are in FINDINGS A1-A3.
- **v2 attempts 1-7**, all agents (FINDINGS "v2 Attempt 1" to "v2 Attempt 7"; agent ids under `V2WF` in the FINDINGS
  header). v2 A1 ran on tools `2197aac`, A2 `6b62667`, A3 `f039205`, A4 `a20a4d7`, A5 `dea6536`, A6 `36189b8`, A7
  `6025133`, and **A8 runs on `fb54dbb`**. This run's fixes reach **v2 attempt 9**.
- Not yet ingested: v2 plan #8 and everything after it, in `V2WF = WF/wf_8db95a5a-12a/` (journal line 108 onward).
- Archived blends: `examples/mm-launcher-{a1,a2,a3,v2a1,...,v2a7}/`, each the blend its reviewer saw, with its checks.json.
  The v2 ones carry overlays of the rows each reviewer showed were missing; v2a3 to v2a7 also have manifest.json and BOM.

## Printability and slicing (2026-10-25, docs/tasks/2026-10-25-printability-and-slicing.md; FINDINGS "v2 post-freeze")
- **v2 shipped "supports: no" on 4 parts that need support:** jar_valve (3 tabs, 5.5 mm cantilevers at z 2), feeder_cover
  (2 ears, 10.5 mm at z 32), base_shell (zip-tie block, 6 mm), post_R (top over the cover split, 11.7 mm). The old
  parts check measured all four as bridges under 25 mm and passed them. Every v2 attempt (A1-A7) has the same 7 fails.
- **`cad printcheck`** (`scripts/printcheck.py`) slices the exported STLs per 0.2 mm layer and classifies unsupported
  regions as bridge / cantilever / island; cadcheck `parts` and `cad q printcheck` run it too. Proven on the v2 STLs
  against the task's ground truth (jar_valve and feeder_cover fail; beam, nip_cover, flywheel ring, window tops, crown,
  nacelle do not) plus planted fixtures and every archived attempt (verify 4m, 4n). The older attempt regressions run
  with `CAD_LAYER_CHECK=0` so their exact counts keep meaning what they did.
- **`cad slice`** (`scripts/cadslice.py`, `guarded_run.py`): sandboxed (no network, writes only in a temp dir, the user's
  slicer folders denied), crash-guarded (the crash never reaches ReportCrash: 0 reports where unguarded runs wrote 2),
  one smoke test per slicer version. **Bambu Studio 02.05.00.66 is unusable**: its smoke test crashed in 0.2 s (caught,
  no dialog), as did 10 unguarded agent runs on 2026-10-24; recorded in `slicers/known.json`. No other slicer is
  installed, so `cad slice` reports "NO USABLE SLICER" and `cad printcheck` is the authority.
- **Recommendation for the user:** install PrusaSlicer, whose CLI is the stable headless one:
  `brew install --cask prusaslicer`. Then `cad slice --detect`; the first `cad slice` runs its one guarded smoke test
  (a 20 mm cube) and, if it passes, every later run reports time, filament and where PrusaSlicer adds support. The
  vendored profile (`slicers/profiles/prusa_p1s_pla.ini`) and the G-code parsing have only met stand-in output so far.
- Template and demo fixed: the project template's floor bosses now run to the deck (they started 16 mm up when printed
  deck-down); the demo turret's base and barrel are declared supports: yes.

## What exists, and what is proven (`sh tools/verify_all.sh`: 100/100 pass, about 28 min)

| Piece | Proven by |
|---|---|
| `tools/transcript/cc_transcript.py` | FINDINGS cost tables. It counts `cad` runs, not a reviewer's own wrapper script |
| `skills/print-cad-blender`: cadlib, cadcheck, cadq, `cad`, template, references | regressions A1 (7), A2 (15 fails exactly), A3 (2 fails exactly), v2 A1 (3 fails exactly), v2 A2-A5 (designer configs and overlays, see FINDINGS), **v2 A6** (designer config: 0 F, 11 untriaged = V2R6's 3 issues as 8 warns plus 3 step facts; with the step facts declared only the 2 A6-01 warns remain; V2R6's slide row fails on the groove cap); demo clean and `--bug` 4/4; slide-gate clean and `--bug` 6/6; bevel clamp test; template, `cad py`, `cad q` |
| cadcheck changes this run (v2 A7) | **Held poses** (`assembly.held_poses`): a step `pose` or a pose-only screw on a servo-held joint (`joint_drives`, default by name) after the drive is in and before a `"powered"` step warns unless the step has `pose_how` (V2A7-F1: tilt 45 at 11a, servo in at 8, battery at 14). **Cable kinks and shared tubes** (`cables.kinks`, `cables.shared_runs`): corners under 0.75 x OD with one OD straight out of a plug or splice, and two routes in one tube for more than 2 OD (V2A7-F2: both bus leads). Proven by verify 4k (v2 A7 designer config: 0 F, 12 untriaged = A7-01, A7-02 x3, A6-02 drift, 4 step facts, 3 other cable shapes; overlay, `powered`/`pose_how` cases, V2R7's cap rows) and 4l (`tools/test_cable_shapes.py`). On v2 A1-A6 the held-pose check finds no need; cable shapes add 5 warns (A1-A5) and 6 (A6) |
| cadlib (v2 A7) | `asm.cable` stores `cab_path` and `cab_r`; older blends get the path back from the tube rings |
| `cad rows` (v2 A7) | kink bends per corner; `--summary` prints `joint_drive` and `held_pose` lines |
| cadcheck changes (v2 A6 run, in `fb54dbb`) | **`insertion` check**: each part and each bench group at its merge, out in a straight line (±XYZ, screw axes, `insert_dirs`, at the step's `pose`) past the earlier steps' parts, plus a warn for a bench part far from its group (V2A6-F1: the splice in the feeder's bench step; the feeder merge "+Z PRT_groove_cap (BUY_bus_junction) at 3"). **`cables.end_drift`**: ends that meet across a joint, followed to each limit (V2A6-F2: 8.8 and 5.7 mm). **Swept ray missed station warns** on `min` rows (V2A6-F3). `parts` warns on `bevel_clamped` |
| cadlib (v2 A6) | `geom.bevel` measures its vertex moves and flags a globally clamped edge break (V2A6-T2: n=768 cut, 1.0 -> 0.01) |
| `cad rows` (v2 A6) | `--summary` (counts, coverage, not_checked, step_of); insertion `blocked` per direction |
| `cad rows` (v2 A5) | `cad rows checks.json [REGEX]` prints config rows; drop stall points printed (V2A5-T4) |
| cadcheck changes (v2 A4 run, in `36189b8`) | **`ray.sweep`**: a distances ray turned over a passage, worst station plus profile (V2R4's major as one row: 7.50/7.67/7.95 at psi 80, V2A4-F1); **poses past a joint's range** listed in the summary, and a pose on no joint or a coupled one is a config fail (V2A4-T2); **stale-model warn** when sources are newer than the blend, never acceptable (V2A4-T1) |
| `cad` wrapper (v2 A4 run) | `cad build` exits non-zero and prints `BUILD FAILED` when the script raises: Blender exits 0 on a script error, and `run()` ended in `|| true` (V2A4-T1). `cad rows` prints a swept profile |
| cadcheck changes (v2 A3 run, in `dea6536`) | **ray-slip warn** replaces ray-vs-nearest (9 for 9 false on v2 A3, V2A3-T2); **inscribed-circle bridge span** (bbox was false for arcs and rotated slots); **`=EXPR` values** over the build's params anywhere a number goes; **prismatic joints** in every sweep (`overtravel_mm`); slide **`flex`** bounds for detents; **`cable_chains`** and a junction warn; **stock screw lengths**; a no-pose service op is proved by a home slide row; no stale-accept list under `--only` |
| New commands | **`cad rows`** (one line per report or manifest row, plain python3; v2 A3 wrote 67 `json.load` snippets); **`cad bom`** (BOM fastener table vs manifest: exactly V2R3's 2 BOM errors on A3) |
| cadlib | `asm.joint(prismatic=True)`; params stored in the .blend (`cad_params`); cable ends (`cab_ends`); `M3_hex` spec |
| `skills/cad-design-review` | v2 R1 14.7 min (7/7/6), R2 18.5 (8/8/9), R3 14.8 (8/8/8), R4 12.8 (8/9/9), R5 14.2 (9/8/9), R6 9.3 (9/8/9), R7 9.6 (9/8/9). New this run: `assembly.held_poses`, `cables.kinks`/`shared_runs` and removal rows to infinity in the checklist. Earlier: measured stacks for toleranced purchased parts, `unbounded_allows`, `cad rows checks.json`. Earlier: sweep a passage gap, not one station; grep with `cad rows`, `cad bom` in the checklist, max-payload rows from params, cable chains, prismatic gates |
| `templates/cad-loop.workflow.js` | dry run, sequential and parallel. New this run: the planner marks the `powered` step and gives a step that moves a servo-held joint a `pose_how` (or reorders it), and routes each lead on its own with a straight exit (V2A7-F1/F2); finish checks `assembly.held_poses` and runs removal rows until the part is clear (V2R7 A7-03). v2 A6 run: the planner puts a part in the step where it goes in and gives angled steps a `pose`, routes meet on the joint axis; finish checks `checks.insertion` and uses `cad rows --summary` (V2A6-F1/F2). v2 A5 run: the planner tries a shared params change in a /tmp build before planning on it (V2A5-T2), and writes stacks with `between` (V2A5-F1). Earlier: `ray.sweep` for a passage (V2A4-F1), rows as `=EXPR` at the declared extremes (planner), `cad bom` (finish), `cad rows` (all). The v2 loop uses its own copy, so **template edits reach v2 only if the user adopts them** |

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
| v2 6 | 76.9 (plan 17.6, builds 45.3, review 9.3) | 213k | 9/8/9 | 0/1/2 | 193k | real: 0 of 3 tool-catchable; now 3 of 3 as warns (insertion, end drift, missed stations) |
| **v2 7** | **50.5** (plan 10.8, builds 29.3, review 9.6) | **173k** | **9/8/9** | **0/1/3** | **164k** | real: 0 of 4 (3 marked tool-catchable); now 3 of 4 as warns (held pose, kinks + shared tube, end drift); A7-03 (a short removal row) is not |

v2 A7 is the cheapest attempt in either loop (50.5 min, 173k output tokens, peak context 164k) and the first under
v1's best wall time (66.1), at the same score (26). A6-01 and A6-03 are FIXED, A6-02 PARTIAL. The one major (A7-01)
came from the A6-01 fix: the groove cap moved to step 11a, where one screw is reachable only at tilt 45, six steps after
the tilt servo went in and before anything is powered. The new held-pose check names it; the A6 run's insertion check
also asks for 11a's "pod at tilt 45" as a pose, which leads to the same warn.

## Known gaps
- Layer check: sustained 60-70 deg slopes step under the allowance per layer and pass (the face-based slope warn over
  150 mm² still covers them). The 3 mm cantilever fail line sits between 2.9 (short ledges) and 5.5 (smallest real miss).
  `cad slice` G-code parsing is tested on stand-ins only.
- A `slide_out` removal row that stops short (V2R7 A7-03) passes; prose numbers in `why` strings and the BOM are not
  checked against params.
- Insertion treats parts made in place (a soldered splice) as brought from outside; such steps need `insert_ok`. It is
  straight-line only and does not test parts of one step against each other (tried in step-list order: 4-5 list-order
  false warns per config, reverted).
- Held poses cover assembly steps, not service ops (those assume power). Drives come from names or `joint_drives`.
- Cable shapes add 3 recurring warns on the v2 model that no reviewer raised (bundle corner R4 for OD 6, feeder bus inside
  the bundle, encoder beside phase 2); expect A9's designer to fix or accept them.
- Rows whose bound follows the geometry (V2A5-F1) still pass by construction. BOM free text vs model: `cad bom` reads
  fasteners only. Creep and fatigue out of scope. cadlib facet defaults are not sag-based (V2A6-T3). Exposure covers
  cables and nuts, not PCBs. Gear tooth tips read as thin walls. `parallel_builds` is untested live.
- Template edits (V2A4 to V2A7) reach v2 only if the user adopts them.

## Next (revision run for v2 attempt N)
- If the loop restarts: its agents now get 7 new parts fails on the v2 design (above). They are real; expect the
  designer to re-orient, gusset or split those parts, or mark them supports: "yes". The finish step runs `cad printcheck`
  and `cad slice` (template), which reaches v2 only if the user adopts the template.
0. v2 A8 runs on `fb54dbb`: the first with the insertion check, end drift, missed-station warns, the bevel flag and
   `cad rows --summary`. Count its insertion and drift warns, how it triages them, and how long that takes (false warns
   are a direct cost). Check whether A7-01 is fixed by order or by `pose_how`, and whether the bundle hand-over (A6-02)
   is fixed or accepted. A9 gets held poses and cable shapes: on the A7 config that is 7 new warns, 4 of them V2R7's.
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
