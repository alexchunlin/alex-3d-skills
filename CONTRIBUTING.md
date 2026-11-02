# Contributing

Thanks for helping. This repo grows from evidence: a design loop hits a problem, the problem gets a finding ID, and a
tool or a rule closes it. Changes follow the same path.

## Branches

- `main` is what design agents run. Nothing is committed to it directly.
- `next` collects reviewed work. `next` is promoted to `main` by PR after a full `tools/verify_all.sh` passes.
- Work on `feat/<name>` or `fix/<name>`, branched from `next`, with a PR into `next`.

## A good PR

1. **Points at evidence.** Name the finding it closes (`V2A6-F1`, `PA-A7-T19`, ...) from [docs/FINDINGS.md](docs/FINDINGS.md),
   or add the finding first.
2. **Says why the existing code wasn't enough.** Before adding or replacing a component, try the existing code with
   better settings, a thin wrapper or a small fix, and measure it. Put what you tried and the measured gap in a
   "Why not the existing code" section.
3. **Proves itself.** Add a `tools/verify.d/<name>.sh` script with a `# watch:` header for the paths it reads, plus a
   negative control (a planted bug the check must catch). Run your own scripts and
   `sh tools/verify_all.sh --changed origin/next --dry-run` to see what else your change touches.
4. **Doesn't regress the bench.** If you claim a check now catches a labelled issue, tighten its locator in
   `tools/bench/labels.json` and show `python3 -I tools/bench/replay.py compare BASE NEW`: recall up, false fails and
   noise warns not up.
5. **Keeps the skill docs lean.** Every line in an always-read doc costs every agent session tokens.
   `python3 -I tools/bench/doccost.py HEAD --base origin/next` prints the cost. Put details in `reference/` docs that are
   read on demand.

Each PR gets an independent review from someone (or an agent) who hasn't seen earlier verdicts. Apply the fixes, list
them under "Changes after review", then merge.

## Style

Numbers with units, no adjectives where a measurement fits. Reports and docs name the file, the command and the value,
so anyone can re-run them.
