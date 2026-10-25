# Status (updated 2026-10-24, after the revision run for v1 attempt 3)

## Ingested
- v1 is **complete and stopped** after attempt 3 (`HARVEST_BRIEF.md` "Process change"). All v1 agents are ingested:
  - A1: D1, R1, and the killed D0.
  - A2: D2, R2.
  - A3: D3 `agent-a16a800e7f34fb0ab` (41.0 min), R3a `agent-a84bc90b0abd58f66` (interrupted at 6.6 min), R3
    `agent-aec430aae41935a1a` (18.5 min, 6/6/6).
- Archived blends: `examples/mm-launcher-a{1,2,3}/`, each with checks.json, a cadcheck summary and the blend the
  reviewer saw.
- **Next data is v2**: `HW/v2/renders/attempt-N/` and the v2 workflow journal (path given in the prompt). v2 uses
  these tools for real via the pin worktree `~/code-stuff/alex-3d-skills-pin`. Never touch the pin.

## What exists, and what is proven (`sh tools/verify_all.sh`: 36/36 pass, about 5 min)

| Piece | Proven by |
|---|---|
| `tools/transcript/cc_transcript.py` | FINDINGS A1-A3 cost tables |
| `skills/print-cad-blender`: cadlib, cadcheck, cadq, `cad`, template, references | A1 regression (7 R1 findings), A2 regression (9 R2 findings, exactly 15 fails), A3 regression (7 R3 patterns, exactly 2 fails, no nip-mechanism false fails); demo clean 0 fails and `--bug` 4/4; template 0 fails |
| cadcheck additions this run | `slide_out` includes fasteners (with a rest-overlap test); `carry`; `fasteners.captive`; `flexures` (beam vs print orientation); slide-drop `flattest_slide_deg` and `stall_margin_deg`; viewer-direction exposure; nut visibility; full `warn_list`; float-safe stacks |
| `skills/cad-design-review` | checklist: hard stops, slide margin, brief-numbers table, whole-path removal, flexures, visible nuts; step 0 `notes.md` for restarts. **First real use is v2.** |
| `templates/cad-loop.workflow.js` | dry run only. The review prompt has notes and restart handling; the finish prompt asks for slide_out and flexures. The v2 orchestration is its own copy under `mmlauncher/orchestration/`, so template edits **don't** reach v2. Skill and cadcheck edits do, through the pin. |

## v1 baseline (final)

| Attempt | Wall (design + review) | Output tok | F/M/A | Issues B/M/m | Tool-catchable (now) |
|---|---|---|---|---|---|
| 1 | 82.6 min | 481k | 5/6/5 | 18 | 7 reproduced |
| 2 | 97.0 min | 520k | 6/5/6 | 1/3/6 | 8 of 10 |
| 3 | 66.1 min (6.6 lost to an interrupted reviewer) | 352k | 6/6/6 | 0/4/4 | 6 of 8 |

The full rows (thinking, cache, misses, peak context, longest generation, recurrence) are in FINDINGS A3, "Baseline
rows". Total: 245.7 min for 3 attempts at about +1 score point per attempt. Compare v2 against this.

## Known gaps
- No check for channel width along a payload path. R3 measured it by hand with 4 scripts (A3-T5).
- No cadlib helper for the swept envelope of a moving part (D3 spent 159 s deriving one, A3-T2).
- Stall angle and PLA interlayer limits are defaults from reviewer estimates (20° + 5°, 15 MPa), not tests.
- Several catches need a config entry restating a BOM claim: index, service, slide_out, flexures and hard-stop
  poses. The reviewer checklist asks for them. v2 will show whether designers write them.
- Exposure now flags two unconfirmed A2 spots at (-38, -26, 252) and (-27, -57, 252). The A3 versions of these are
  gone.
- Not checked: nut wrench access, cable bend radius and slack, teardown count, window-vs-content size, form language.

## Next (revision run for v2 attempt N)
1. `cc_transcript.py workflow <v2 wf dir>`, then `summary` per agent. Compare time, tokens and peak context against
   the v1 baseline table above.
2. Read `HW/v2/renders/attempt-N/{progress.md,cadcheck.json,review.json}`. Count:
   - cadcheck false fails that cost agent time (grep the transcripts for allow/fits edits and "false");
   - `check_config_disputes`;
   - `tool_catchable` issues that cadcheck still missed.
3. Fix what v2 agents actually tripped over: cadcheck, SKILL wording, checks-config docs. Run
   `sh tools/verify_all.sh` before every commit, because `main` feeds the next v2 attempt.
