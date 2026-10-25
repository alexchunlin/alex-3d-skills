# Status (updated 2026-10-24, after the initial harvest of attempt 1)

## Ingested
- Attempt 1: D1 `agent-af2e15ae070705e95`, R1 `agent-a4e34520e7cf12eb4` (wf_26e26b28-15e), killed D0 `agent-a0e1dc96a1cba327c` (wf_ebc9f356-a79), and `HW/renders/attempt-1/`.
- D2 `agent-a6815d61faa83f67e` only up to 19:30 (first 24 min: one 17 min thinking block, no geometry yet). **The next run must re-ingest D2 from the start**, plus R2.

## What exists, and what is proven (`sh tools/verify_all.sh`: 17/17 pass, about 1 min)

| Piece | Proven by |
|---|---|
| `tools/transcript/cc_transcript.py` (summary, timeline, usage, thinking, grep, workflow, ...) | numbers in FINDINGS attempt 1 |
| `skills/print-cad-blender`: cadlib, cadcheck, cadq, `cad` wrapper, project template, references | A1 regression reproduces R1's 7 key findings; demo clean = 0 fails; demo `--bug` catches 3/3; template = 0 fails |
| `skills/cad-design-review` (protocol, rubric anchors, checklist) | **not exercised by a real reviewer yet** |
| `templates/cad-loop.workflow.js` | stub dry-run only (`tools/test_workflow_template.py`); **never run with real agents** |
| `components/` (11 placeholders + data with sources) | all build closed |
| `examples/mm-launcher-a1/` (checks.json, archived blend .gz, summary) | regression fixture |

## Known gaps
- cadcheck: no cable bend-radius or slack check, no service-access (teardown count) check, and the drop test is straight rays (no bounce or slide). The 4 "new, unconfirmed" A1 warns in FINDINGS need a human or reviewer look.
- cadlib: no snap-fit or fillet helper beyond the angle-limited bevel. Aesthetics (R1 #16-17) is not addressed by tooling. build123d is not measured.
- The live loop still runs the old prompts. Nothing in it points at these skills, so attempt 2 and later can only be compared against the tools, not helped by them.
- The live HW blend at 20:03 (attempt-2 work in progress) runs under cadcheck with the A1 config: 59 fails / 70 warns. That config does not know A2's new joints or fits, so the number means nothing until an A2 config exists.

## Next (revision run for attempt 2)
1. `cc_transcript.py workflow WF/wf_26e26b28-15e`, then `summary` and `thinking --min-s 300` on D2 and R2. Record time and tokens per attempt, and whether A1-T1 (upfront thinking) and A1-T4 (cache misses) recur.
2. Write `examples/mm-launcher-a2/checks.json`: joints from the A2 blend (`cad q ... list`), fits, assembly order from the A2 BOM. Run cadcheck on a copy of the A2 blend.
3. Score the tools: for each R2 issue, did cadcheck/cadq flag it before review? Record it as a recurring table in FINDINGS (issue, A1 status, A2 status, tool-catchable, caught).
4. Fix the cadcheck false positives or misses this reveals. Re-run `verify_all.sh`. Add an A2 regression if it is cheap.
5. Ask the user whether to switch the live loop to `templates/cad-loop.workflow.js` with `start_attempt` = next. That is their call, because it changes a running process.
