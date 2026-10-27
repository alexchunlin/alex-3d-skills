# Task: run only the tests a change affects

Branch `feat/verify-select`, worktree `.claude/worktrees/verify-select`. PR target `next` (the coordinator opens it).

## Why
`tools/verify_all.sh` runs all ~100 checks every time (28 min alone, about 2x that with other runs going). It ran on
every feature branch and every merge. The user wants only the tests that the changed tools affect. The full suite
stays for promoting `next` to `main`, because `main` is what the v2 design agents run (the pin worktree).

## Build
1. `sh tools/verify_all.sh --changed [BASE]` (BASE defaults to `git merge-base HEAD next`). Changed files = committed
   diff BASE...HEAD plus uncommitted and untracked changes. With no flag it runs everything, exactly as today.
2. Map changed paths to sections. Tag each existing numbered section (1, 2, 3, 3b, 3c, 4, 4a-4n, 4b, 5, 6, 7, 8,
   slide-gate) with the paths it exercises, by reading what each section actually runs. Be conservative: when unsure,
   include the section. A starting point to check against the code, not to trust blindly:
   - `scripts/cadcheck.py`, `cadq.py`, `cadlib/**`, `scripts/cad`: the demo, template, attempt regressions,
     slide-gate, and every verify.d script that builds or checks.
   - `scripts/printcheck.py`: 4m, 4n, and anything else that runs the layer check (demo and template use
     CAD_LAYER_CHECK=1).
   - `cadslice.py`, `guarded_run.py`, `slicers/**`: 4m's slice part.
   - `cadrows.py` / `cadbom.py`: the sections that call `cad rows` / `cad bom`.
   - `templates/project/**`: 3, 3b, 3c.
   - `components/**`: 5. `templates/cad-loop.workflow.js`: 6. `tools/transcript/**`: 7.
   - `examples/<x>/**`: the sections using that example.
   - Docs only (`docs/**`, `*.md` outside `skills/*/scripts`, `skills/cad-design-review/**`): nothing; print
     "no tests affected".
   - Paths that no rule matches: run everything, and say why ("unmapped: path").
3. `tools/verify.d/*.sh`: each script declares what it watches in a header line, e.g.
   `# watch: skills/print-cad-blender/scripts/cadlib/route.py tools/verify.d/route_*`. It runs when a watched path
   changed, when the script itself changed, or when a core path it depends on changed. Add the header to every
   existing script by reading what it imports or runs.
4. Print the plan before running: each section and verify.d script that will run, with the path that triggered it,
   and what's skipped. Add `--dry-run` to print only the plan.
5. A test of the selector itself in `tools/verify.d/` (fake changed-file lists, then check the plan), so a future edit
   can't silently skip tests.
6. Update the README line and `tools/verify.d/README`.

## Prove
- Dry-run plans for: a docs-only change, a printcheck.py-only change, a cadlib change, a new standalone tools/ dir,
  and this branch itself.
- Then actually run `--changed` on this branch and report what ran and the time it took.
- Don't run the full suite; the machine is overloaded. Run detached via `setsid` if a run might outlive a tool call.

## Rules
Work and commit only on `feat/verify-select` in this worktree. Don't push, open PRs, or touch `main`, `next`, the pin
worktree or other worktrees. Don't spawn agents. Commit in the repo's style, ending with
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Report back briefly: the flags, the mapping table, the
dry-run plans, and the test result.
