# Bench: do tool features improve design results, or only add tokens?

Two tiers, no LLM calls. Plain python3, standard library. Nothing here runs a slicer.

## Tier 1: replay bench (`replay.py`)

Replays the 10 archived designs (`examples/mm-launcher-{a1,a2,a3,v2a1..v2a7}`) through the tools of a chosen commit and
scores the reports against what the reviewers found.

```sh
python3 -I tools/bench/replay.py                        # HEAD's tools, all 10 attempts (Blender-bound; 75 min wall at -j 3 on a loaded machine)
python3 -I tools/bench/replay.py --commit origin/next   # any commit: its skills/ is git-archived into the scratch dir
python3 -I tools/bench/replay.py --attempts v2a6,v2a7 -j 2
python3 -I tools/bench/replay.py --from-verify /tmp/alex3d-verify/latest   # score a finished verify_all run, no Blender
python3 -I tools/bench/replay.py --from-run /tmp/alex3d-bench/run-<pid>   # rescore an earlier bench run (after a label edit)
python3 -I tools/bench/replay.py table                  # one line per (commit, attempt) in results/replay.jsonl
```

- **Corpus** (`corpus.json`): per attempt, the same cad runs `tools/verify_all.sh` makes (configs, overlays, `--only`
  sets, `CAD_LAYER_CHECK`), each with the file name verify_all writes, so `--from-verify` scores verify's own reports.
  Run kinds: `designer` (the designer's config plus the always-on tools: the layer check, `cad printcheck` on the v2a7
  STLs, `cad bom`) and `review` (the rows each reviewer showed were missing, as overlays). Bench-only runs, which
  verify_all doesn't make: the v2a1 designer config alone (verify always adds V2R1's overlays) and `cad bom` on v2a7.
- **Labels** (`labels.json`): one entry per issue a reviewer raised (FINDINGS "Issues V2Rn raised" tables, the v1
  R1-R3 foot-gun tables, and the R1 items those tables leave out), plus the 4 v2 post-freeze support misses on every v2
  attempt. Each has `attempt`, `id` (the reviewer's id; `findings_id` is the FINDINGS one), `severity`,
  `tool_catchable` (the reviewer's flag; FINDINGS for v1), `locators` (check + regex on the report line that would
  name it; `null` when no check can) and `source` (FINDINGS line or review file). `judgment` says where the label is
  a call rather than a reading. `known_true_positives` lists real fails no reviewer raised (v1 layer-check finds) and
  planted overlay rows, so they don't count as false fails.
- **Scores**, per attempt, in two scopes: `designer` (designer runs only) and `rows` (all runs, suffix `_rows`).
  - `recall_fail`: labels whose best match is a fail. `recall_fw`: fail or warn, accepted warns included (the tool said
    it, the config dismissed it; `caught_accepted_only` counts those).
  - `false_fails`: fails matching no label locator and no known true positive (listed in `false_fail_list`).
  - `warn_load`: untriaged warns per label: what a designer must triage per real issue.
  - `runtime_s`: wall time of the cad runs (contention-sensitive: other Blender jobs on the machine inflate it).
- **Results** append to `results/replay.jsonl`, one row per (commit, attempt) plus an `ALL` row, with the commit,
  branch, labels-file hash and per-label status, so two commits compare with `replay.py table`.
- Scratch: `/tmp/alex3d-bench/run-<pid>` (latest: `/tmp/alex3d-bench/latest`), as verify_all uses `/tmp/alex3d-verify`.
- v1 had no tools: its "designer" config is the harvest run's `checks.json`, written from the v1 BOM. v1 recall is
  counterfactual, as FINDINGS says.

**Adding a feature.** A PR that claims a check catches a labelled issue adds or widens that label's locator (naming
the issue's objects, not a catch-all) and shows `replay.py table` before and after: recall up, false fails and warn
load not up. A locator change applies to old commits too, so re-run the base commit with the new labels.

## Tier 2: cost telemetry

```sh
python3 -I tools/transcript/cc_transcript.py bench [--attempt v2a3,v2a7] [--json]   # per agent (agents.json)
python3 -I tools/bench/doccost.py [REF] [--sections] [--base REF2] [--json]        # static doc cost
python3 -I tools/bench/features.py [--ref REF] [--json]                            # the join, as markdown tables
```

- **`cc_transcript.py bench`**: per agent of the v1 and v2 loops (`agents.json`, from the FINDINGS header): skill-doc
  tokens read before the first `.py`/`.json` edit (by file), tool and library source reads (cadcheck.py, cadlib: signs
  of a doc gap), failed cad or Blender runs, and the `cad` subcommands, `cad q` commands, `--only` sections,
  checks.json keys (written to checks / review_rows / overlay JSON) and cadlib calls (in written code) it used. A call
  that reads several files splits its result over them by file size when all are read whole, else evenly.
- **`doccost.py`**: bytes and tokens (chars / 4, an approximation: no tokenizer) of every skill doc at any ref, by
  section heading and by item (bold-lead list items, tool-table rows). `docs.json` says which docs are always read: the
  SKILL.md bodies and the docs they tell the agent to read unconditionally (api.md, footguns.md; checklist.md,
  rubric.md); checks-config.md is conditional. `--base` gives "adds N always-read tokens per session" for a PR.
- **`features.py`**: features are `cad` subcommands, `cad q` commands, checks.json keys (the jsonc block of
  checks-config.md) and cadlib functions. Each always-read unit's tokens split evenly over the features it names;
  "paid over v2" multiplies by the v2 sessions of the role. Uses come from the transcripts, plus the archived v2
  designer configs and the shipped v2 code (calls the template wrote, which agents never typed). A feature that no v2
  pin had is "new since v2 A7", not "unused".

Limits: tokens are chars / 4; reads are attributed per call, not per byte; config-key use is detected from written
JSON and from Bash commands that name a checks/review_rows/overlay file; transcripts live outside the repo, so tier 2
reports them missing on another machine.

## Smoke test

`tools/verify.d/bench.sh` (sourced by verify_all): scores verify's own v2a7 reports and runs the runner on the v2a6
layer check (about 10 s), asserting the known per-label results.
