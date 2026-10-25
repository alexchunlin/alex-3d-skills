# Status (updated 2026-10-25, after the revision run for v2 attempt 3)

## Ingested
- v1 (the no-tools baseline, attempts 1-3) is complete. Its rows are below; details are in FINDINGS A1-A3.
- **v2 attempts 1-3**, all agents (FINDINGS "v2 Attempt 1" to "v2 Attempt 3"; agent ids under `V2WF` in the FINDINGS
  header). v2 A1 ran on tools `2197aac`, A2 on `6b62667`, A3 on `f039205`, and **A4 runs on `a20a4d7`**. This run's
  fixes reach **v2 attempt 5**.
- Not yet ingested: v2 plan #4 and everything after it, in `V2WF = WF/wf_8db95a5a-12a/` (journal line 50 onward).
- Archived blends: `examples/mm-launcher-{a1,a2,a3,v2a1,v2a2,v2a3}/`, each the blend its reviewer saw, with its checks.json.
  The v2 ones carry overlays of the rows each reviewer showed were missing; v2a3 also has its manifest.json and BOM.

## What exists, and what is proven (`sh tools/verify_all.sh`: 66/66 pass, about 12 min)

| Piece | Proven by |
|---|---|
| `tools/transcript/cc_transcript.py` | FINDINGS cost tables. It counts `cad` runs, not a reviewer's own wrapper script |
| `skills/print-cad-blender`: cadlib, cadcheck, cadq, `cad`, template, references | regressions A1 (7), A2 (15 fails exactly), A3 (2 fails exactly), v2 A1 (3 fails exactly), v2 A2 (0 fails plus 4 config warns; overlay 4 fails), **v2 A3** (designer config: 0 fails, 1 untriaged warn, the real M3 x 9; overlay: 3 fails exactly plus a zero-margin pocket); demo clean and `--bug` 4/4; **slide-gate clean and `--bug` 6/6**; template, `cad py`, `cad q` |
| cadcheck changes this run | **ray-slip warn** replaces ray-vs-nearest (9 for 9 false on v2 A3, V2A3-T2); **inscribed-circle bridge span** (bbox was false for arcs and rotated slots); **`=EXPR` values** over the build's params anywhere a number goes; **prismatic joints** in every sweep (`overtravel_mm`); slide **`flex`** bounds for detents; **`cable_chains`** and a junction warn; **stock screw lengths**; a no-pose service op is proved by a home slide row; no stale-accept list under `--only` |
| New commands | **`cad rows`** (one line per report or manifest row, plain python3; v2 A3 wrote 67 `json.load` snippets); **`cad bom`** (BOM fastener table vs manifest: exactly V2R3's 2 BOM errors on A3) |
| cadlib | `asm.joint(prismatic=True)`; params stored in the .blend (`cad_params`); cable ends (`cab_ends`); `M3_hex` spec |
| `skills/cad-design-review` | v2 R1 14.7 min (7/7/6), R2 18.5 (8/8/9), R3 14.8 (8/8/8). Now: grep with `cad rows`, `cad bom` in the checklist, max-payload rows from params, cable chains, prismatic gates |
| `templates/cad-loop.workflow.js` | dry run, sequential and parallel. New this run: rows as `=EXPR` at the declared extremes (planner), `cad bom` (finish), `cad rows` (all). The v2 loop uses its own copy, so **template edits reach v2 only if the user adopts them** |

## v1 baseline vs v2

| Attempt | Wall (design + review) | Output tok | F/M/A | Issues B/M/m | Peak ctx | Caught before review |
|---|---|---|---|---|---|---|
| v1 1 | 82.6 min | 481k | 5/6/5 | 18 | 522k | counterfactual 7 |
| v1 2 | 97.0 | 520k | 6/5/6 | 1/3/6 | 698k | counterfactual 8 of 10 |
| v1 3 | 66.1 | 352k | 6/6/6 | 0/4/4 | 488k | counterfactual 6 of 8 |
| v2 1 | 187.5 (builds in series: 136.6) | 902k | 7/7/6 | 0/5/7 | 348k | real: 3 of 12, as warns nobody acted on; now 4 |
| v2 2 | 150.0 (builds 114.4) | 524k | 8/8/9 | 0/2/6 | 340k | real: 2 of 6 tool-catchable, as unread warns; now 5 |
| **v2 3** | **145.8** (plan 22.2, builds 108.0, review 14.8) | **474k** | **8/8/8** | 0/1/5 | **257k** | real: **0 of 6** (all 34 warns triaged); now 5 of 6, 3 of them with a row |

v2 A3 is the cheapest v2 attempt and has the lowest peak context of all six, but the score is flat (24 against 25). The
designer triaged every warn this time, so the misses moved from unread warns to **rows written for the nominal case**:
the one major (A2-01) and two recurring minors (A1-03, A2-02) are all payload or cable extremes.

## Known gaps
- Rows nobody writes are still the main leak. `=EXPR` rows make the extremes cheap; only the SKILL, the checklist and the
  planner prompt ask for them.
- `a20a4d7` (what A4 runs) has the 9-false-warn ray rule and the bbox bridge span: expect A4's untriaged count, or its
  accepted_warns, to show them.
- Edge-break consistency is not measurable; gear tooth tips still read as thin walls.
- Exposure covers cables and nuts, not PCBs (V2A1-F11). No insertion sweep for assembly merges (V2A1-F6).
- Cable junctions need cadlib-stored ends (fresh builds only). `parallel_builds` is untested live.

## Next (revision run for v2 attempt N)
1. Run `cc_transcript.py workflow <V2WF>`, then `summary` per new agent. Compare against the table above.
2. Read `HW/v2/renders/attempt-N/{progress.md,cadcheck.json,review.json}`:
   - "## Tool issues" in progress.md;
   - `check_config_disputes`;
   - `tool_catchable` issues; for each, did cadcheck flag it at hand-off (fail, or an accepted warn)?
   - verify every reviewer config claim against cadcheck.json.
3. v2 A4 runs on `a20a4d7`: the first attempt with `payload_fit`, `sightlines`, slide `expect`, `cad py` and `cad q`
   help. Check whether the A1-03 pocket gets a `payload_fit` row, and count the ray-vs-nearest false warns (T2) and how
   the designer triaged them. `cad rows`, `=EXPR`, prismatic joints and `cad bom` arrive in A5.
4. Count `json.load` snippets (FINDINGS V2A3-T1 method) to see whether `cad rows` gets used from A5.
5. Run `sh tools/verify_all.sh` before every commit, because `main` feeds the next v2 attempt. Don't edit
   verify_all.sh while it runs: sh reads it incrementally.
