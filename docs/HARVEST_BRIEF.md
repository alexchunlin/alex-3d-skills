# Harvest brief: build 3D-modeling skills/tools from a live agent CAD loop

## Context
In `/Users/alxchunlin/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/`, a multi-agent loop is designing a 3D-printable M&M launcher turret in Blender (headless, `bpy`):
- A **designer** agent writes and revises a parametric `blender/build_assembly.py`, plus `checks.py`, renders, STLs, `DESIGN_LOG.md` and `BOM_AND_ASSEMBLY.md`.
- An independent **reviewer** agent scores each attempt 1-10 on Functionality, Manufacturability and Aesthetics, renders its own close-ups and measures in Blender. It writes `renders/attempt-N/review.md` and `review/measurements.json`.
- The loop repeats until all three scores reach 9 or more, for up to 8 attempts.

The loop works but is **slow and expensive**. Attempt 1 took about 64 min of design plus 18 min of review, with an 84 KB script and 35 parts, and scored 5/6/5. The user wants to turn what these agents do, and the mistakes they make, into reusable tooling in this repo (`~/code-stuff/alex-3d-skills`). Goals: **higher quality, fewer foot-guns, and less wall time and fewer tokens** for future agent-driven 3D-printable CAD work.

## Data sources (read-only; never modify or delete anything outside this repo)
| Source | Path |
|---|---|
| Design brief, the spec the agents work from | `/Users/alxchunlin/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/DESIGN_BRIEF.md` |
| Generated code, logs and outputs | `.../mm-launch-hw/blender/*.py`, `DESIGN_LOG.md`, `BOM_AND_ASSEMBLY.md`, `renders/attempt-*/` (checks.json, review.md, review/measurements.json, PNGs), `stl/` |
| Orchestration script (prompts, schemas, loop) | `/Users/alxchunlin/.claude/projects/-Users-alxchunlin-code-stuff-mmlauncher-mm-launcher/c043264a-30c7-474d-8ca2-0c2301d01041/workflows/scripts/mm-launcher-cad-loop-wf_ebc9f356-a79.js` |
| Agent transcripts (JSONL, ~10 MB each) | `/Users/alxchunlin/.claude/projects/-Users-alxchunlin-code-stuff-mmlauncher-mm-launcher/c043264a-30c7-474d-8ca2-0c2301d01041/subagents/workflows/wf_26e26b28-15e/` (current run: `journal.jsonl` holds each agent's structured result; `agent-*.jsonl` holds the full transcripts, and `*.meta.json` gives the label). `wf_ebc9f356-a79/` is an earlier designer run that was killed by a session restart after about 45 min, before it wrote any geometry. |
| Designer scratch dir | `/private/tmp/mmwork/` |

**Don't Read the raw JSONL transcripts whole.** Write small Python or jq extractors (keep them in `tools/transcript/` in this repo, so they're reusable) that pull out, per agent:
- the tool-call sequence with timestamps and gaps between calls (long gaps mean long generations),
- bash commands and their errors,
- Blender failures and retries,
- files written and their sizes,
- images read (count and bytes),
- re-renders of the same view,
- token usage per assistant message (`message.usage`), where present.

## What to look for
1. **Time and token sinks:** long single-shot generations, such as rewriting an 84 KB script; repeated Blender cold starts; reading 2 MB PNGs; re-deriving facts already in the brief; exploration that a library or helper would make unnecessary.
2. **Foot-guns:** mistakes the reviewer caught that a tool could have prevented or detected, for example:
   - fasteners modelled reversed,
   - checks that skip fasteners and cables,
   - interference checked only at nominal poses and not across the joint sweep,
   - zero-clearance rubbing faces,
   - feed trajectories nobody simulated,
   - assembly order that's impossible (screws you can't reach),
   - overclaimed checks.
   Also: process failures, such as work lost when the session died with no checkpoint, and the user having no visibility into progress.
3. **What worked:** helpers or checks the agents invented that are worth turning into a library, such as manifold booleans, BVH interference, tilt sweeps, ray-grid drop tests, contact sheets of STLs in print orientation, and tip-angle stability.
4. **Reviewer quality:** what evidence made the reviews actionable, and where scoring was noisy.

## What to build here (decide the right mix; justify it)
Candidates, not requirements:
- **A Claude Code skill** (`skills/<name>/SKILL.md` plus `scripts/`) for parametric, print-ready Blender CAD. It would cover a part/assembly conventions library (PRT/BUY/FST/PIV naming, collections, pivots for a web viewer), a print-feature library (screw bosses, self-tap pilots, nut traps, counterbores, heat-set pockets, snap fits, fillets/chamfers, PLA clearances), and a standard render set (low-res previews by default, sections, exploded views, an STL contact sheet).
- **A verification toolkit:** manifold checks, bed fit, overhang and bridge analysis, minimum wall, pairwise interference **including fasteners and cables across full joint sweeps**, clearance margins, tool-access and screw-reachability checks, part-specific simulations (drop-path ray tests), and a center-of-gravity/tip check. Each produces JSON evidence a reviewer can cite.
- **A reviewer skill/rubric** with scoring anchors and an evidence checklist, so reviews are consistent and cheap.
- **An MCP server or persistent Blender daemon,** so agents query or rebuild without cold-starting Blender each time, and can measure, section and render on demand. **Follow the global "prior art" rule:** evaluate existing options first (for example the existing Blender MCP projects, build123d/CadQuery for B-rep and STEP export, and trimesh/manifold3d for checks), measure them where you can, and include a "Why not the existing code" section for anything new.
- **An orchestration template** for the design/review loop:
  - checkpointing, so an interrupted run resumes from files;
  - incremental edits instead of full rewrites;
  - previous issues passed to the reviewer for verification;
  - render budgets;
  - per-attempt progress files the user can watch.
- **A component library:** reusable placeholder models and data for parts already characterised here (MotorGo Axis STEP to STL, Plink MT6701 encoder, XTEAM 3674 BLDC, Hiwonder bus servo, DeWalt adapter, buck converter). Keep the dimensions and sources together.

## Rules
- Write only inside `~/code-stuff/alex-3d-skills`. Commit locally with clear messages after each meaningful step (no remote, no push). Don't install anything into `~/.claude/skills` or settings; write install instructions in the README instead.
- Every rule or tool must cite the evidence that motivated it (attempt, file, transcript timestamp or measured number). Keep `docs/FINDINGS.md` as the running evidence log, with sections per attempt.
- Prove tools work. Run them against the real `mm-launch-hw` outputs (on copies, under `/tmp/alex3d-*`) and record the results. Be light on CPU while the CAD loop is running; avoid long Cycles renders.
- Keep `docs/STATUS.md` short and current (what exists, what's proven, what's next) so the next revision run can pick up without re-reading everything.

## Revision runs
The CAD loop produces a new attempt (design plus review) about every 60-90 min. After each attempt, a fresh session runs here with the prompt "Revision run for attempt N". Each revision run should:
1. Read `docs/STATUS.md` and `docs/FINDINGS.md`.
2. Ingest only the new attempt's data: the new journal entries, the new `agent-*.jsonl` transcripts and `renders/attempt-N/`.
3. Add findings, especially whether issues recur across attempts, which tooling would have prevented, and per-attempt time/tokens.
4. Improve the skills and tools, re-verify them, update STATUS and commit.

**Baseline decision (user, 2026-10-24):** none of the 8 attempts in this loop will use this repo's tools. The loop runs unchanged as a baseline. Revision runs measure what the tools *would* have caught and record per-attempt baseline metrics (see `docs/STATUS.md`). They don't propose changing the running loop.

## Process change (user decision, 2026-10-24 evening). This supersedes the "baseline runs all 8 attempts" decision.
- **v1 (the no-tools baseline) stopped after attempt 3.** The user stopped it to reassess. The baseline is attempts 1-3; attempt 3's review was run so it has three scored attempts. Record the A3 baseline row as usual.
- **v2 starts now and uses this repo's tools:** `templates/cad-loop.workflow.js` adapted, `print-cad-blender`, `cad-design-review` and `cadcheck`, in a modular project at `/Users/alxchunlin/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/v2/`. The orchestration script is at `/Users/alxchunlin/code-stuff/mmlauncher/mm-launcher/orchestration/`.
- From now on, v2 tool results are **real, not counterfactual**. Measure whether the tools helped: issues caught before review, false fails that cost agent time, time and tokens per attempt against the v1 baseline, and context peaks.
- **The v2 agents use a pinned checkout at `~/code-stuff/alex-3d-skills-pin`** (a git worktree, detached HEAD). Each v2 attempt's planner moves the pin to this repo's `main` at the start of that attempt. So:
  - `main` must always be working: run `sh tools/verify_all.sh` before every commit.
  - Your improvements reach the next v2 attempt, never one in flight.
  - Never edit or check out anything in the pin worktree yourself.
- v2 revision runs are launched as "Revision run for v2 attempt N". Their data is in the v2 workflow's journal and transcripts (path given in the prompt) and in `mm-launch-hw/v2/renders/attempt-N/`. That covers `progress.md`, `cadcheck.json`, `review.md` and `review.json`, which includes `tool_catchable` per issue and `check_config_disputes`. The most valuable improvements fix what v2 agents actually tripped over. Watch for cadcheck false fails, missing checks, unclear skill instructions, and template prompt problems.

## Printer safety
**Hard rule (user, 2026-10-24):** never run Bambu Studio, OrcaSlicer or any slicer binary, never read ~/Library/Application Support/BambuStudio, and never contact a printer or any network service. Print time and filament are estimates computed from geometry only. Don't build tools that invoke slicers.


## Printer safety, revised (user, 2026-10-25)
The blanket "never run any slicer binary" rule above is replaced. Slicers may be run **only through the skill's `cad slice` tool** (see `docs/tasks/2026-10-25-printability-and-slicing.md`): isolated temp data dir, no network, never send to a printer, never read or write the user's slicer settings, and one guarded smoke test per slicer with no automatic retries after a crash. Contacting printers or the network remains forbidden.
