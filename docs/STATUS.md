# Status (updated 2026-10-25, after the revision run for v2 attempt 5)

## Ingested
- v1 (the no-tools baseline, attempts 1-3) is complete. Its rows are below; details are in FINDINGS A1-A3.
- **v2 attempts 1-5**, all agents (FINDINGS "v2 Attempt 1" to "v2 Attempt 5"; agent ids under `V2WF` in the FINDINGS
  header). v2 A1 ran on tools `2197aac`, A2 on `6b62667`, A3 on `f039205`, A4 on `a20a4d7`, A5 on `dea6536`, and **A6
  runs on `36189b8`**. This run's fixes reach **v2 attempt 7**.
- Not yet ingested: v2 plan #6 and everything after it, in `V2WF = WF/wf_8db95a5a-12a/` (journal line 80 onward).
- Archived blends: `examples/mm-launcher-{a1,a2,a3,v2a1,v2a2,v2a3,v2a4,v2a5}/`, each the blend its reviewer saw, with its
  checks.json. The v2 ones carry overlays of the rows each reviewer showed were missing; v2a3 to v2a5 also have their
  manifest.json and BOM.

## What exists, and what is proven (`sh tools/verify_all.sh`: 75/75 pass, about 17 min)

| Piece | Proven by |
|---|---|
| `tools/transcript/cc_transcript.py` | FINDINGS cost tables. It counts `cad` runs, not a reviewer's own wrapper script |
| `skills/print-cad-blender`: cadlib, cadcheck, cadq, `cad`, template, references | regressions A1 (7), A2 (15 fails exactly), A3 (2 fails exactly), v2 A1 (3 fails exactly), v2 A2 (0 fails plus 4 config warns; overlay 4 fails), v2 A3 (designer config: 0 fails, 1 untriaged warn, the real M3 x 9; overlay: 3 fails exactly plus a zero-margin pocket), v2 A4 (designer config: 0 F, 0 untriaged, 6 stale false-warn accepts, 8 past-limit poses listed; swept overlay: 3 fails exactly), **v2 A5** (designer config: 0 F / 0 untriaged / 0 stale, detent allow listed; one swept row = V2R5's 8.099 at psi 90; band stack with `between` and a bounded allow: 2 fails exactly); demo clean and `--bug` 4/4; **slide-gate clean and `--bug` 6/6**; template, `cad py`, `cad q` |
| cadcheck changes this run (v2 A5) | **stacks `between`**: the limit is the measured gap from A to B (or `"*"`, every part not touching A); the designer's own band stack then fails on the detent tab at 0.322 (V2A5-F1). **`allow` `max_mm3`**: a bounded allow fails past its volume; allows that skip a pair across a joint with no bound are listed in `summary.unbounded_allows` (V2A5-F6). Slide `flex` records rides below `vol_tol` (V2A5-T3). Waived cable junctions listed (`junctions_waived`, V2A5-F3). `--out` after the flags is honoured (V2A5-T1) |
| `cad rows` this run | `cad rows checks.json [REGEX]` prints config rows; drop stall points printed (V2A5-T4) |
| cadcheck changes (v2 A4 run, in `36189b8`) | **`ray.sweep`**: a distances ray turned over a passage, worst station plus profile (V2R4's major as one row: 7.50/7.67/7.95 at psi 80, V2A4-F1); **poses past a joint's range** listed in the summary, and a pose on no joint or a coupled one is a config fail (V2A4-T2); **stale-model warn** when sources are newer than the blend, never acceptable (V2A4-T1) |
| `cad` wrapper (v2 A4 run) | `cad build` exits non-zero and prints `BUILD FAILED` when the script raises: Blender exits 0 on a script error, and `run()` ended in `|| true` (V2A4-T1). `cad rows` prints a swept profile |
| cadcheck changes (v2 A3 run, in `dea6536`) | **ray-slip warn** replaces ray-vs-nearest (9 for 9 false on v2 A3, V2A3-T2); **inscribed-circle bridge span** (bbox was false for arcs and rotated slots); **`=EXPR` values** over the build's params anywhere a number goes; **prismatic joints** in every sweep (`overtravel_mm`); slide **`flex`** bounds for detents; **`cable_chains`** and a junction warn; **stock screw lengths**; a no-pose service op is proved by a home slide row; no stale-accept list under `--only` |
| New commands | **`cad rows`** (one line per report or manifest row, plain python3; v2 A3 wrote 67 `json.load` snippets); **`cad bom`** (BOM fastener table vs manifest: exactly V2R3's 2 BOM errors on A3) |
| cadlib | `asm.joint(prismatic=True)`; params stored in the .blend (`cad_params`); cable ends (`cab_ends`); `M3_hex` spec |
| `skills/cad-design-review` | v2 R1 14.7 min (7/7/6), R2 18.5 (8/8/9), R3 14.8 (8/8/8), R4 12.8 (8/9/9), R5 14.2 (9/8/9). New: measured stacks for toleranced purchased parts, `unbounded_allows`, `cad rows checks.json`. Earlier: sweep a passage gap, not one station; grep with `cad rows`, `cad bom` in the checklist, max-payload rows from params, cable chains, prismatic gates |
| `templates/cad-loop.workflow.js` | dry run, sequential and parallel. New this run: the planner tries a shared params change in a /tmp build before planning on it (V2A5-T2), and writes stacks with `between` (V2A5-F1). Earlier: `ray.sweep` for a passage (V2A4-F1), rows as `=EXPR` at the declared extremes (planner), `cad bom` (finish), `cad rows` (all). The v2 loop uses its own copy, so **template edits reach v2 only if the user adopts them** |

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
| **v2 5** | **93.3** (plan 8.5, builds 69.9, review 14.2) | **314k** | **9/8/9** | **0/1/5** | **240k** | real: 1 of 4 tool-catchable (warned, then waived); now 3 of 4 (F1 fails with `between`, F3/F6 listed) |

v2 A5 ties A4 on score (26) at about the same cost, and Functionality reached 9 for the first time: A2-01, the major
in A2-A4, is fixed. 30 of the 70 build minutes were B5-launcher redesigning a params change the planner had only
predicted on paper (V2A5-T2). The new major (detent tab 0.322 from the jar band) is a row whose bound followed the
geometry; a stack with a measured limit catches it.

## Known gaps
- Rows whose bound follows the geometry (V2A5-F1) or sample a few stations (V2A4-F1, V2A5-F2). `between` and `ray.sweep`
  make the right row cheap; only the SKILL, checklist and planner prompt ask for them. A swept ray is 1-D.
- BOM free text vs model (tape width, slot text): `cad bom` reads fasteners only. Material creep/fatigue is out of scope.
- Edge-break consistency is not measurable; gear tooth tips still read as thin walls.
- Exposure covers cables and nuts, not PCBs (V2A1-F11). No insertion sweep for assembly merges (V2A1-F6).
- Cable junctions need cadlib-stored ends (fresh builds only). `parallel_builds` is untested live.
- Template edits (V2A4 sweep, V2A5 scratch build and stacks) reach v2 only if the user adopts them.

## Next (revision run for v2 attempt N)
0. v2 A6 runs on `36189b8`: the first with `ray.sweep`, the past-limit list, the stale-model warn and `BUILD FAILED`.
   Check whether the entry-arc rows become swept rows (A5: designer 5 rows, V2R5 9 rows), whether V2R5's band stack row
   is adopted, and whether a `BUILD FAILED` or stale-model warn fired. A7 gets `between`, `max_mm3`, `cad rows checks.json`.
1. Run `cc_transcript.py workflow <V2WF>`, then `summary` per new agent. Compare against the table above.
2. Read `HW/v2/renders/attempt-N/{progress.md,cadcheck.json,review.json}`:
   - "## Tool issues" in progress.md;
   - `check_config_disputes`;
   - `tool_catchable` issues; for each, did cadcheck flag it at hand-off (fail, or an accepted/waived warn)?
   - verify every reviewer config claim against cadcheck.json.
3. Split `json.load` calls into config edits (load + dump) and report reads (FINDINGS V2A5-T4: A5 47 edits, 24 reads).
   Only the reads are a tool gap.
4. Run `sh tools/verify_all.sh` before every commit, because `main` feeds the next v2 attempt. Don't edit
   verify_all.sh while it runs: sh reads it incrementally.
