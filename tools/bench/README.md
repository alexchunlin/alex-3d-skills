# Bench: do tool features improve design results, or only add tokens?

Two tiers, no LLM calls. Plain python3, standard library. Nothing here runs a slicer.

## Tier 1: replay bench (`replay.py`)

Replays the 10 archived designs (`examples/mm-launcher-{a1,a2,a3,v2a1..v2a7}`) through the tools of a chosen commit and
scores the reports against what the reviewers found.

```sh
python3 -I tools/bench/replay.py                        # HEAD's tools, all 10 attempts (Blender-bound; 30-40 min at -j 1 on a loaded machine)
python3 -I tools/bench/replay.py --commit origin/next   # any commit: its skills/ is git-archived into the scratch dir
python3 -I tools/bench/replay.py --attempts v2a6,v2a7 -j 2
python3 -I tools/bench/replay.py --from-verify /tmp/alex3d-verify/run-<pid>   # score a finished verify_all run, no Blender
python3 -I tools/bench/replay.py --from-run /tmp/alex3d-bench/run-<pid>       # rescore an earlier bench run (after a label edit)
python3 -I tools/bench/replay.py table                  # one line per (commit, attempt) in results/replay.jsonl
python3 -I tools/bench/replay.py compare BASE NEW       # the gate: per-attempt deltas, refuses rows it can't compare
python3 -I tools/bench/replay.py lint                   # the locator lint
python3 -I tools/bench/replay.py xcheck --from-run DIR  # labels.json vs verify_all's per-attempt assertions (report only)
python3 -I tools/bench/assembly.py --from-run DIR       # design-for-assembly table (one Blender scan per design, cached)
```

Name run directories by pid (`run-<pid>`, printed at the start of a run). `latest` links point at whichever run started
last, which may be another worktree's. `--from-verify` takes the commit from the run's `meta.json`, which verify_all
writes; it refuses a directory without one unless you pass `--assume-commit`.

- **Corpus** (`corpus.json`): per attempt, the same cad runs `tools/verify_all.sh` makes (configs, overlays, `--only`
  sets, `CAD_LAYER_CHECK`), each with the file name verify_all writes, so `--from-verify` scores verify's own reports.
  Run kinds: `designer` (the designer's config plus the always-on tools: the layer check, `cad printcheck` on the v2a7
  STLs, `cad bom`) and `review` (the rows each reviewer showed were missing, as overlays). Bench-only runs, which
  verify_all doesn't make: the v2a1 designer config alone (verify always adds V2R1's overlays) and `cad bom` on v2a7.
- **Labels** (`labels.json`, schema in its `_doc`). Three lists, scored apart:
  - `labels`: one entry per issue a reviewer raised (the FINDINGS "Issues V2Rn raised" tables, the v1 R1-R3 tables, and
    the R1 items those tables leave out). These alone make the headline recall. `process: true` (A1-F14, an overclaimed
    report) is out of every denominator. `credit_scope: "rows"` (A2-F7, whose a2 config row was written from R2's
    review, FINDINGS:297) counts in rows scope only.
  - `printability`: tool findings no reviewer raised, one entry per finding with the attempts it is on: the layer
    check's support misses, v1 (arm_cover_R, base_shell ribs, hopper lip) and v2 (jar_valve, feeder_cover, base_shell,
    post_R) alike. Each is scored once, as its worst status over its attempts, in its own score. `confirmed_by` /
    `print_evidence` record real prints (jar_valve: printed 2026-10-26, drooped without supports).
  - `known_true_positives`: planted overlay rows and exploratory review rows. Not false fails; they credit nothing.
- **Locators**: `{check, objects, kind, region?, partial?}`. A report line matches when it starts with `check: `, names
  every object as a whole token (globs for families; a named row or test when the line names no object), matches `kind`
  (the defect) and, if given, `region` (where on the part, when the part has other findings). `partial: true` marks a
  line that covers part of the issue (a coverage warn, a sub-point); it scores `partial`, not caught. `replay.py lint`
  (run by the smoke test, and before every scoring run) rejects a top-level `|`, `check: "*"`, a locator with no object
  and a measured number pinned in `kind`.
- **Scores**, per attempt, in two scopes: `designer` (designer runs only) and `rows` (all runs, suffix `_rows`).
  - `recall_fail` / `recall_fw`: reviewer labels whose best line is a fail / a fail or warn. Accepted warns count (the
    tool said it, the config dismissed it; `caught_accepted_only` counts them). `recall_*_w`: severity-weighted,
    blocker 3, major 2, minor 1. `recall_fw_catchable`: of the labels the reviewer marked tool-catchable.
  - `caught_partial`: labels only a partial locator matched. `label_errors`: uncaught labels whose check came from a run
    that crashed. A crash is an error, never a miss; `compare` refuses rows with errors.
  - `false_fails`: fails that match no locator of the attempt's labels, printability findings or known true positives
    (`false_fail_list`; `excused_fails` says which entry excused each fail).
  - `noise_warns`: untriaged warns matching no locator (`noise_warn_list`). `hit_share`: the share of untriaged warns that
    match one. v1 was never triaged, so the summaries keep `ALL-v1` and `ALL-v2` apart (`ALL` pools the recall).
  - `unproven_warns`: cadcheck's "not proven clear between the sampled poses" warns (a pair the interference check
    could not finish between its samples): a limit of the tool, counted apart and in neither of the two above.
  - `pf_fail` / `pf_fw`: printability findings caught.
  - `per_label`: each label's status per scope and the report line that credited it (`designer_line`, `rows_line`).
  - `runtime_s`: information only (other Blender jobs move it). No table or gate uses it.
- **Results** append to `results/replay.jsonl`, one row per (commit, attempt) plus the summary rows, with the commit,
  labels-file hash, run subset and errors. `table` groups rows by labels hash and warns when there are several;
  `compare` refuses rows scored against different labels, with run errors, or with different run subsets. A label edit
  applies to old commits too: rescore their run dirs with `--from-run` before comparing.
- Scratch: `/tmp/alex3d-bench/run-<pid>`, as verify_all uses `/tmp/alex3d-verify/run-<pid>`.
- v1 had no tools: its "designer" config is the harvest run's `checks.json`, written from the v1 BOM. v1 recall is
  counterfactual, as FINDINGS says.

**Adding a feature.** A PR that claims a check catches a labelled issue adds or tightens that label's locator (check,
the issue's objects, the defect kind; never a catch-all) and shows `replay.py compare BASE NEW`: recall up, false fails
and noise warns not up. Rescore the base commit's run with the new labels first.

**Assembly** (`assembly.py`): per design, from the records cadcheck reads (the blend through cadcheck's own scene model,
the designer's checks.json and report, the manifest where archived): printed and purchased parts, screws, distinct screw
SKUs (size x length x head), nuts, heat-set inserts, screws threading into printed parts, assembly steps, screws per
printed part, and rigid bodies carrying printed parts. Gradients to improve, not pass/fail. It gives no
Boothroyd-Dewhurst theoretical minimum: only the relative-motion criterion is in the records; the material and
assembly/service criteria, and printability, are judgments.

## Tier 2: cost telemetry

```sh
python3 -I tools/transcript/cc_transcript.py calibrate [--write]                  # chars/token from the transcripts' usage -> tokens.json
python3 -I tools/transcript/cc_transcript.py bench [--attempt v2a3,v2a7] [--json]   # per agent (agents.json)
python3 -I tools/bench/doccost.py [REF] [--sections] [--base REF2] [--json]        # static doc cost
python3 -I tools/bench/features.py [--ref REF] [--json]                            # the join, as markdown tables
```

- **`cc_transcript.py bench`**: per agent of the v1 and v2 loops (`agents.json`, from the FINDINGS header): skill-doc
  tokens read before the first `.py`/`.json` write to the design project (a /tmp probe is not the first edit), tool and
  library source reads (cadcheck.py, cadlib: signs of a doc gap), failed cad or Blender runs, and the `cad` subcommands,
  `cad q` commands, `--only` sections, checks.json keys and cadlib calls it used. Read paths resolve against the skills
  tree at the attempt's tools pin (`git ls-tree` at `pins`; v1 had none: HEAD): non-files (`.`, `/2` of `2>/dev/null`,
  `../..`) drop out, globs and a recursive grep's bare directory expand. The result is credited per file by content
  (each output line to the pin file that has it), so a partly failed multi-file `cat` credits only what was printed;
  `read_methods` says how each read was split. cad uses count only commands in command position, never prose in
  heredocs or comments.
- **Tokens** are characters / the ratio `calibrate` measured on these transcripts (`tokens.json`): for a single-tool
  API call, the next call's context minus this call's, minus its output_tokens (thinking stays in context in the tool
  loop), is the result's tokens. On 29 skill-doc reads: **2.25 chars/token** (IQR 2.08-2.54, range 1.39-2.66), not 4.
- **`doccost.py`**: bytes and tokens (at the measured ratio) of every skill doc at any ref, by section heading and by
  item (bold-lead list items, tool-table rows). `docs.json` says which docs are always read: the SKILL.md bodies and the
  docs they tell the agent to read unconditionally (api.md, footguns.md; checklist.md, rubric.md); checks-config.md and
  design-principles.md are conditional. `--base` gives "adds N always-read tokens per session" for a PR.
- **`features.py`**: features are `cad` subcommands, `cad q` commands, checks.json keys (the jsonc block of
  checks-config.md) and cadlib functions. Each always-read unit's tokens split evenly over the features it names.
  "Paid over v2": each v2 session pays a unit's tokens x min(1, tokens it read of that doc / the doc's tokens at its
  pin), so sessions that never opened a doc pay nothing. Uses come from the transcripts, the archived v2 designer
  configs, the shipped v2 code and the feature log (`_log` entries in the v2 manifests). A cadlib feature logged by hand
  under its name but never called (drill_to_fit_boss, pcb_pocket in shipped parts/base.py) is "API didn't fit,
  reimplemented", not unused. A feature no v2 pin had is "new since v2 A7".

Tier 2 is descriptive: it says what agents read and used, not whether a doc caused a better design.

Limits: one measured chars/token ratio for all text (IQR 2.08-2.54); reads are credited by content at the pin, evenly
when the agent read another checkout; config-key use is detected from written JSON and from Bash commands that name a
checks/review_rows/overlay file; transcripts live outside the repo, so tier 2 reports them missing on another machine.

## Perturbation audit (`perturb.py`, issue #45)

Nudges each top-level float in `params.py` (or a build script's own constants, `--params-file build.py`) to -d and +d,
with d = 0.2 mm (1 deg for angles), or to an adjuster's own `--range NAME=LO:HI`. Each nudge is rebuilt and re-checked
in a scratch copy and diffed against one nominal build with `cad diff`'s key. A control rebuild (no change) is diffed
the same way. Scratch: `/tmp/alex3d-bench/run-<pid>/perturb/<tag>/`. Each run's project copy is deleted once its
report is saved; `build.log`, `check.log`, `cadcheck.json`, `manifest.json` and `diff.txt` stay. `perturb.json`
records the rules and each parameter's d and band.

- **Classes**, in this order:
  - `fixed`: a finding is gone, or a fail became a warn.
  - `coverage`: a "not proven clear" or "swept ray missed" warn. This is the sampler's budget, not the design.
  - `pinned`: the row declares a bound within d of the nudged parameter's nominal, one- or two-sided. Examples: a
    `wanted 6.0..6.4` row against HOOD_GAP 6.5, or a `(min 0.30;` row against DISC_CLR 0.30. The band is 2d: 0.4 mm,
    or 2 deg for angles. The row restates the parameter, so any nudge past its bound fails it by construction.
  - `label`: a labels.json locator of `--attempt`'s own labels matches.
  - `printability`: a printability locator of that attempt matches, or the check is parts/printcheck.
  - `control`: the control run flipped the same key.
  - `design`: anything else.
- **Brittle**: one sign of a parameter brings either a new fail, a new untriaged warn, or a warn -> fail in the design,
  label or printability class, or a build error (a `params.py` assert). `brittle_with_pinned` also counts pinned flips.
  Both counts are reported. `--from DIR [--attempt A]` rescores a stored run without Blender.

```sh
python3 -I tools/bench/perturb.py examples/demo-turret --params-file build.py --build-args "--out {out}" -j 2
mkdir -p /tmp/campaign/45w/v2 && cd ~/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/v2/blender && \
  cp -R build_assembly.py params.py parts checks.json tools /tmp/campaign/45w/v2/ && cd -
python3 -I tools/bench/perturb.py /tmp/campaign/45w/v2 --attempt v2a7 --quick -j 2 \
  --params '^(PSI_C|MM_T\[1\]|HOOD_GAP_MIN|TAPE_T|CLR|HOOD_GAP|BORE_CLR|DISC_CLR|SERVO_POCKET_CLR|GATE_STOP_CLR|LEAF_T|DISC_T|LIFT_FLOOR)$'
```

Measured 2026-11-03 (H45: findings flip within tolerance; the null is rejected):
- **Demo turret**, all 10 parameters, full check: 3.7 s per rebuild+check, 46 s total at -j 2. 0 brittle. 4 flips, all
  `fixed`: CLR +0.2 and SINK +0.2 clear the 0.90 mm screw-head warns, and SINK +0.2 also drops the arm screws from
  M3 x 10 to x 8. The control flipped nothing.
- **v2 launcher**: the live copy is attempt 7's params plus one post-review `checks.json` service row. 13 of 407
  parameters were sampled with `--quick`.
  - Cost: 264 s per rebuild+check; a full check alone is 244 s. All 407 parameters would take about 30 h at -j 2.
  - Brittle: **7 of 13**, or 9 counting pinned rows.
  - 3 build errors from `params.py`'s own V2A3-F1 assert. At nominal, the entry arc has 0.005 mm above the assert's
    floor (8.105 against NIP_PASS 8.0 + 0.1). MM_T[1] +0.2 and TAPE_T +0.2 raise that floor to 8.3; LIFT_FLOOR -0.2
    lowers the arc to 7.905.
  - Flips: 20 design, 6 fixed, 5 coverage, 5 pinned. **0 match a v2a7 label** (A7-01, A7-02, A6-02, A7-03 checked),
    and 0 are printability.
  - PSI_C (the V2A5-T2 parameter) and CLR change no STL: attempt 7 no longer uses them.
  - The control flipped nothing.

## Smoke test

`tools/verify.d/bench.sh` (sourced by verify_all): the locator lint; the scoring rules on JSON fixtures
(`fixtures/`, `test_replay.py`: check prefix, accepted warn, partial catch, rows-only label, crashed run, known true
positive, false fail, noise warns, lint, table and compare), with two mutants of `replay.py` (check prefix ignored;
false fails never reported) that must fail them; verify's own v2a7 reports scored through `--from-verify`; the runner
on the v2a6 layer check (about 10 s); and `xcheck` as a report.
