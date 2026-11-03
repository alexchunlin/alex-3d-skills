# Prior-art campaign, 2026-11-03: what we tested and what we learned

Coordinator run over the prior-art issues #28-#47. Start: `next` at b92f385 (after PR #48). Every change went through a
feature branch, a two-axis review (standards and spec, by agents blind to each other), fixes, and the author's own
verify.d scripts, then merged into `next`. `main` was not touched. The daily full `verify_all` ran once at the end
(section 6); its two regressions are fixed in PR #57. Measurements that needed no code are posted as "Measured 2026-11-03" comments on their issues.

## 1. Triage

Prioritised by scientific yield per token and by what unblocks what: bugs and deterministic tools first, measurement
questions in parallel (they are read-only and cheap), then the tool changes those measurements justified, then the
Blender-heavy audit (#45) once `cad diff` (#30) existed. Effort: Sonnet for mechanical fixes and docs (#28/#29, #37,
#44/#46); Opus for tools whose matching logic matters (#30, #31, #45), the loop template, and every measurement.

Deferred, with the reason:
- #32 viewer: PR #48 already shipped `cad view` with sliders, ghosting, explode, x-ray and a section plane; the three
  remaining gaps (part tree, capped sections, timeline) are noted on the issue.
- #33 URDF/MJCF: needs the sibling team's MJCF conventions first.
- #34 ghosted renders: the #40 measurement removed the reviewer-side case; per-step PNGs stay open.
- #35 connector-on-surface: lives on `feat/mate-connectors`, which is 7 commits ahead of and 128 behind `next`.
- #38 bearings and #37's coupons: need test prints only the owner can make.
- #39 step.parts: a network API, off limits here.
- #43 drawing-tools ground truth: about 90 LLM runs plus an AGPL tool in a venv; too costly for this pass.

## 2. Hypotheses, procedures, results

| # | Hypothesis (H1) and null (H0) | Procedure | Result | Verdict |
|---|---|---|---|---|
| 28 | H1: designers handed off on a partial (`--only`) check in the archived loops. H0: never. | `cc_transcript.py handoffs` over every mm-launcher and push-assist agent transcript: each agent's last `cad check`. | mm-launcher: all 10 finishers ended on a full check (0 partial hand-offs; builders hand to the finisher). Push-assist: 3 of 3 designers ended on a partial check. Reviewers and planners run `--only` by instruction (`cc_transcript.py handoffs` on the same transcripts: 8 of 8 review agents, 5 of 7 plan agents ended on one). | H1 holds for push-assist. Fix shipped (PR #50): PARTIAL PASS/FAIL print, `run.only` in the report, partial runs write `cadcheck.partial.json`, the loop refuses a partial hand-off. |
| 29 | `cad bom` passes unstocked M5 lengths. | BOM fixture M5 x 13 / M5 x 12 through `cad bom`; 4f regression (v2a3: exactly 2 BAD rows). | M5 x 13 was passed on `next`; flagged after. 4f still exactly 2 BAD. | Fixed (PR #50): one stock table, read from cadcheck's DEFAULTS. |
| 30 | H1: an automatic report diff reproduces the reviewer's FIXED/PARTIAL/NOT FIXED verdicts. H0: the diff cannot separate them. | Build `cad diff`; turret clean vs `--bug` (4 planted fails), self-diff; v2a6 → v2a7 reports diffed and compared with V2R7's `previous_issue_status`; reviewer step-4 tool calls counted on R2-R7 transcripts. | Turret: 4 planted fails new / fixed; self-diff empty. v2a6→v2a7: 4 new, 7 fixed, 47 same; agrees with V2R7 on 3 of 3 (A6-01 FIXED, A6-02 PARTIAL as one fixed + one still, A6-03 FIXED) given the author's warn-to-issue mapping; A7-01 appears as new. Reviewer step-4 calls before: 4/1/1/2/1/2 strict, 9/5/5/5/6/7 broad, per review R2-R7. | H1 holds on the one archived pair. The delta now prints unasked at the end of every `cad check` (PR #53), with weakened requirements first (removed rows, grown ignore lists, fewer poses, less overtravel). "After" needs a live loop. |
| 37 | H1: our fastener tables disagree with bd_warehouse's ISO tables in a few explainable rows; a drift check catches a planted error. | 8 CSVs vendored (Apache-2.0 text, sha256); `sizes_vs_bdw.py` compares 128 values M2-M5 against `features.SIZES` + the M3 overlay (read by ast from `size_rules()` itself). | 108 agree, 20 excepted with a verdict enum (ours / theirs / pending-coupon / pending-standard), 0 problems. Planted M4 nut AF 6.8 flagged; stale exception flagged; CSV edit flagged. bd_warehouse's own iso7046 M4/M5 rows equal its iso2009 rows. | H1 holds (PR #51). Coupons (M2.5 heat-set 3.6 vs 4.0, cap-head counterbores, insert walls) stay open. |
| 40 | H1: render-only findings are < 25% of reviewer issues and carry few blockers/majors. H0: ≥ 25% or they carry the majors. | Classify all 154 issues (v2 R1-R7: 42; push-assist a1-a12: 112) by cited evidence: measurement / both / render / reading. Count renders made vs cited. | measurement 100 (65%), both 15, render-only 8 (5.2%; 5 rest on a render alone, 3 more have a visual sub-point), reading 31. Of 45 blockers+majors, 0 render-only. 18 reviews made 26 new renders (max 3 each) against a budget of 12. | H0 rejected. The LLM re-run (reviewer at budget 0) was not worth running: all 7 labels on v2a6/v2a7 rest on measurements. Instead PR #54: budget 12 → 4 and the exposure check extended (PCBs on by default with a 5% visible-share floor, plugs and screw heads opt-in). A1-11 now caught with defaults; v2a2-a7 gain 0 warns. |
| 41 | H1: mis-routed review issues cost ≥ 10% of builder minutes or ≥ 1 bounce per attempt. H0: rare or cheap. | Label all 34 v2 ids and the push-assist ids by the layer that fixed them; count bounces and attributable minutes from FINDINGS and the workflow journal. | 19 of 34 v2 issues needed a layer other than one part builder, but the planner already routes them (params / checks / finish items from A2 on). 2 mis-routes (A1-06, A6-01), both fixed next review. Bounces 4 in 6 revision attempts (0.67). Minutes: at most 35.3 of 436.3 (8.1%), 30.2 of them V2A5-T2 which the template already fixes (1.2% without it). Three new issues came from builders refusing text-only edits outside their file. | H0 holds: no `owner` field. PR #52 widens the `subsystem` description and tells builders to fix text-only mismatches. |
| 42 | H1: issues recur because the approach repeats, and the loop hands off the last attempt, not the best. | Recurrence streaks per id from `previous_issue_status`; compare `fix` text across attempts; read the template's return path; the push-assist A6→A7 drop. | v2: A1-03 and A2-01 missed twice in a row; push-assist: 4 chains, two of them three misses. Only 3 of 6 chains repeated the approach; the commoner cause was testing only the case the last review measured. The loop keeps the last attempt and cannot restore an earlier one. "Keep best by score" would have been wrong: push-assist A6 (8/8/9) hid an unfittable cell that A7 (4/4/9) exposed. | Half holds. PR #52: the planner sees every earlier review, ids at two misses must get an `escalations[]` entry (what was tried, a different approach or a defer, tested at the declared extremes), each attempt snapshots its sources, and the run returns `best` without restoring it. |
| 44 | H1: no public assembly benchmark is runnable on our loop today. | Web research with URLs (cadbench.ai submission + validator READMEs, MUSE data/code pages, one search for others). | cadbench: submissions are a manifest pointing at a Harbor Hub job, validator reads FCStd + spec JSON (no mate or hierarchy check); rank 1 Claude Opus 5.5 at $573.94. MUSE: 106 cases public (CC BY 4.0), MIT judge, scores CadQuery code with a VLM; only its Overlap-Free and geometric-validity (manifold) classes have cadcheck counterparts; Functional is the larger failure class in its Table 2. Others: AssemBench (120 Fusion360 assemblies). | H1 holds. Recorded in tools/prior_art/README.md (PR #49). |
| 36 | H1: per-spec bend radius in mm plus a per-connector strain-relief stub (harnessy ADR 0007) changes the v2 cable warn set materially. H0: cosmetic. | Patched cadcheck copy (38 lines, repo untouched) with `cable_min_bend_mm` and `cable_stub_mm`; 6 variants × 7 archived v2 blends, `--only cables`, 5 s each. | Assumed numbers (3-4× OD, 4-5 mm stubs): +37 to +44 warns, none ever raised by a reviewer. Sourced numbers only (USB-C 15 mm / 25 mm): +7, −11, and it loses the A6/A7 bus kinks V2R7 did raise. The 3 recurring unraised warns do not change (two come from the shared-run check, which has no radius). Per-stretch slack: not needed (0-2 moving ends, 58-94 mm spare). Bundle radius = max of members: ~5 lines. | H1 holds but no change shipped: the prerequisite is sourced radii and stubs in components.json; ADR 0007 itself rejects invented numbers. |
| 45 | H1: some findings flip (pass ↔ warn/fail) under ±0.2 mm parameter nudges; some flips match labels, the rest are noise. H0: no flips. | `tools/bench/perturb.py`: ast-listed numeric params, −d/+d in scratch copies, nominal once plus an unchanged control rebuild, `cad diff` per nudge. Demo turret all 10 params; v2 launcher (attempt 7 + one row) 13 sampled params: 12 with `--quick`, PSI_C and LIFT_FLOOR on full checks. | Turret: 3.7 s per rebuild+check, 46 s total, nothing brittle, control flips nothing. v2: 244 s per full check, 264 s per nudge with `--quick`; all 407 params ≈ 30-33 h at 2 jobs. 7 of 13 sampled params brittle (9 counting pinned rows): MM_T[1] +0.2, TAPE_T +0.2 and LIFT_FLOOR −0.2 all trip the same params.py assert, which has 0.005 mm of margin at nominal (V2A3-F1's mechanism); HOOD_GAP / HOOD_GAP_MIN (0.31-0.38 vs 0.5), LEAF_T, BORE_CLR −0.2 (3.3 mm³ overlap); DISC_CLR and GATE_STOP_CLR are pinned (a declared minimum within 0.2 mm of nominal: 0.30 at 0.30, 0.30 at 0.35). PSI_C ±1° (attempt 7 no longer uses it) and CLR change no STL. 36 flips: 20 design, 6 fixed, 5 coverage (sampler budget), 5 pinned, 0 matching a v2a7 label, 0 printability; control rebuild 0 flips. | H1 holds (PR #56). The flips do not coincide with what reviewers raised: brittleness is a different signal from review recall. |
| 31 | A GLB with a clip per joint and an assembly clip reproduces `joints.world_at`. | `write_glb` (cadlib/gltf.py) via the exporter cad view already uses; FK check parses the GLB with stdlib through the root; negative controls: flipped joint sign, root rotation removed, a part shown at the wrong step. | v2a7: 8 clips, 188 keys, 10,528 part positions, worst error 0.0001 mm / 0.0000°. 0.88 MB Draco (0.55 s) vs 6.99 MB raw; extent 0.245 × 0.4326 × 0.3002 m Y-up. Flipped sign fails at 89.99 mm / 80°. | Shipped (PR #55). Not loaded in an external viewer or validator (none installed offline). |

## 3. Merged into `next` (none into `main`)

| PR | Issue | What |
|---|---|---|
| #49 | #46, #44 | prior-art README: licence note, 2026-11-02 survey, assembly benchmarks |
| #50 | #28, #29 | PARTIAL PASS/FAIL, `run.only`, `cadcheck.partial.json`, loop refuses partial hand-offs; one fastener stock table |
| #51 | #37 | `sizes_vs_bdw` drift check, 20 reasoned exceptions, vendored CSVs with licence |
| #52 | #41, #42 | loop template: all reviews to the planner, escalation after two misses, snapshots, `best` |
| #53 | #30 | `cad diff`, automatic delta on every `cad check`, weakened-requirement lines |
| #54 | #40 | reviewer render budget 4, exposure check for PCBs (plugs/heads opt-in), A1-11 caught |
| #55 | #31 | GLB export with joint clips and an assembly clip, FK-checked |
| #56 | #45 | perturbation audit tool and the v2 measurement |
| #57 | daily | the two regressions the daily check found (section 6); the bench rows for c550ae2 and 799b36f |

## 4. Conclusions we can draw

1. **Measurements, not renders, carry the review.** Nothing a reviewer marked blocker or major rested on a render alone.
   The render budget (12) was 4× what any review used (at most 3), and the one gap renders were covering (visible PCBs) is now a check.
2. **Routing is not the loop's problem; recurrence is, and it is a test-coverage problem.** Fixes were checked at the one
   case the last review measured. The template now forces the declared extremes into the acceptance test after two
   misses, and keeps every attempt's sources so the owner can pick the best by judgement, not by score.
3. **The v2 design passes only at nominal.** 7 of 13 hand-picked interface parameters (clearances, gaps, thicknesses) are brittle within print
   tolerance, and three nudges trip one params.py assert with 0.005 mm of margin. A full audit is 30-33 h of Blender;
   the 13-parameter sample took 75 min (56 min for the 12 `--quick` runs, 9 min each for the two full ones). This argues for a `--quick` perturbation pass in the
   finish step on the parameters the plan changed.
4. **Reviewers were re-deriving FIXED/NOT FIXED by hand** at 1-4 tool calls per review (strict count; 5-9 broad); the diff reproduces the verdicts
   on the one archived pair, and prints the requirement weakenings that reviewers caught only by re-reading the config.
5. **Partial checks were a push-assist hand-off path** (3 of 3 designers) and not a v2 one; the loop now refuses them.
6. **Cable rules need data before code.** Without sourced bend radii, the per-spec rule either invents 40 warns or
   loses the two kinks a reviewer did raise.
7. **No external assembly benchmark fits the loop today.** MUSE is the closest (public cases, MIT judge) but scores
   CadQuery code with a VLM; cadbench submissions run inside Harbor and its validator reads FCStd, so a Blender arm cannot submit as is (the FCStd requirement is inferred from the validator README).

## 5. Costs

Agent tokens, from the harness's per-agent counts: wave 1 (six agents) about 1.45M; wave 2 and 3 builders about
1.6M; review and fix rounds (two reviewers per PR, 8 PRs) about 1.4M. Total near 4.5M agent tokens over about 2.5 h
wall. Blender time: the #45 audit was the largest (75 min for the 13-parameter v2 sample plus 5 min nominal); everything
else ran in seconds to a few minutes. Not measured: the coordinator's own context, and the user's weekly limit, which this
session cannot read; the stop point was chosen by issue coverage, not by the limit.

## 6. Daily check on `next`

Full `tools/verify_all.sh` on `next` 799b36f (after PRs #49-#55, before #56 which is bench tooling only), 2026-11-03
02:44, run dir `/tmp/alex3d-verify/run-60629`: **575 passed, 19 failed**. Both causes came from this campaign and are
fixed in PR #57:

- PR #50 moved the default OUT of a `--only` run to `cadcheck.partial.json`; two verify.d scripts pass `""` in the
  CONFIG slot, the wrapper did not consume it, and 18 reports (stl_read, 17 sweep_guard cases) landed on the partial
  path. The wrapper now consumes an empty CONFIG or OUT, with a regression line that fails on 799b36f.
- PR #54's exposure check warns on the slide-gate example's board (348 of 452 samples visible), one over the unit's
  exact count; the example lists it under `pcbs_ok`.

After the fix, the four affected units pass (slide-gate 8/8, stl_read 13/13, sweep_guard 22/22, only_partial 10/10).
The next daily run must confirm the whole suite on the merge result before `next` is promoted to `main`.

Replay bench (`replay.py --from-verify`, no Blender), compared with the v0.1 full run (c550ae2) rescored under
today's labels:

| scope | recall_fw | recall_fw_rows | false fails | noise warns | unproven (apart) |
|---|---|---|---|---|---|
| ALL-v1 | 0.629 → 0.629 | 0.657 → 0.657 | 0 → 0 | 250 → 250 | 5 |
| ALL-v2 | 0.286 → 0.286 | 0.524 → 0.548 | 0 → 0 | 177 → 177 | 4 |

`compare c550ae2 799b36f`: "worse: nothing". The one gain is v2a1 rows-scope recall 0.333 → 0.417 (A1-11, the PCB
seen through the base notch, now a check). The bench's own run-to-run noise is worth knowing: identical tools and
labels (990c436a, 2026-10-27) scored ALL-v2 recall_fw at 0.333 and 0.286 on different runs, so a one-label move is
within noise; the unproven-pairs column (now counted apart) is where that came from.

## 7. What to do next, in order of evidence

1. Promote `next` → `main` after the next clean daily run (the v2 pin runs `main`; the finish-step partial refusal, the
   automatic diff and the exposure check only reach the loop through it).
2. Adopt the template changes in the v2 loop copy (#42 escalation, #28 refusal) and measure recurrence on the next
   attempts: that is the "after" every table above lacks.
3. Run `perturb.py --quick` on the parameters each plan changes, in the finish step, before review: about 4.5 min
   per parameter on the v2 model, so a plan that touches 10 parameters costs 45 min.
4. Source bend radii and strain-relief stubs for the cables actually used (components.json), then the 40-line cable
   change (#36).
5. The coupons (#37, #38) and the external-viewer checks for the GLB (#31) need the owner's hands.
