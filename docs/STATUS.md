# Status (updated 2026-10-24, after the revision run for attempt 2)

## Ingested
- Attempt 1: D1 `agent-af2e15ae070705e95`, R1 `agent-a4e34520e7cf12eb4`, killed D0 `agent-a0e1dc96a1cba327c` (wf_ebc9f356-a79), `HW/renders/attempt-1/`.
- Attempt 2: D2 `agent-a6815d61faa83f67e` (complete, 82.8 min), R2 `agent-a49e56a72136dd0ee` (14.2 min, 6/5/6), `HW/renders/attempt-2/`, and the 20:27 blend (archived).
- **Not ingested:** D3 `agent-a16a800e7f34fb0ab` (started 20:43). The next run takes D3 and R3 from the start.

## What exists, and what is proven (`sh tools/verify_all.sh`: 28/28 pass, about 3 min)

| Piece | Proven by |
|---|---|
| `tools/transcript/cc_transcript.py` | FINDINGS A1 and A2 tables. It now estimates calls that have no final usage line (A2-T5). |
| `skills/print-cad-blender`: cadlib (now with `asm.nut`), cadcheck, cadq, `cad` (passes `--only`/`--quick`), template, references | A1 regression: 7 R1 findings. A2 regression: 9 R2 findings, and exactly the 15 R2-confirmed fails (no false fails). Demo clean has 0 fails; demo `--bug` catches 4/4. Template has 0 fails. |
| cadcheck additions this run | bolt-to-nut pairing, shank or nut inside purchased parts, L-key access, continuous-joint poses, head stand-off, protrusion, `service` ops, `index_tests`, `drop_tests` `mode: slide`, group `slide_out`, `distances.ray` with payload and compliance, `stacks`, cable exposure |
| `skills/cad-design-review` | updated checklist; **still not exercised by a real reviewer** |
| `templates/cad-loop.workflow.js` | dry run only; **never run with real agents**. Designer and reviewer now get the claims-to-checks rule. |
| `examples/mm-launcher-a1/`, `examples/mm-launcher-a2/` | config, summary and archived blend per attempt |

## Baseline (decided 2026-10-24)
The live loop runs **unchanged for all 8 attempts** as a baseline: no prompt edits, no skills, no `cad check`. The tools here are adopted only after the loop ends, and the first loop that uses them is compared against this one. So:
- Don't propose switching or patching the live loop. Tool results stay counterfactual: "would have flagged", never "helped".
- Record the same baseline row for every attempt: wall and model minutes per agent, output, thinking and cache tokens, cache misses, peak context, the longest single generation, F/M/A scores, the number of review issues (blocker/major/minor), how many are tool-catchable, how many cadcheck flags on the archived blend, and how many issues recur from earlier attempts.

## Key numbers
- Per attempt: A1 82.6 min, 481k output tokens, 5/6/5. A2 97.0 min, 520k output tokens, 6/5/6. At about 1 score point per attempt, the loop will not reach 9/9/9 in 8 attempts.
- cadcheck on A2: before this run, 34 fails, 28 of them false. After, 15 fails, all R2-confirmed. 8 of 10 R2 issues are flagged, and 5 of those come from geometry alone. Full run 58 s.

## Known gaps
- Three of the A2 catches (index, nip squeeze, service) need config entries that restate BOM claims. The tooling helps only if the designer writes them. Nothing checks yet that every BOM claim has an entry; that is a reviewer checklist item.
- `stacks` is arithmetic on declared terms only. Form language and proportions are not tooling problems.
- Not checked: nut wrench access, cable bend radius and slack, teardown screw count. The slide tracer has no bounce or rolling.
- Six new unconfirmed A2 candidates are listed in FINDINGS (backplate bay 0.14 mm, hinge 2.0 mm thread, servo lead 39 mm visible, and others). R3 can confirm or refute them.

## Next (revision run for attempt 3)
1. Run `cc_transcript.py workflow WF/wf_26e26b28-15e`, then `summary` and `thinking --min-s 300` on D3 and R3. Check whether A2-T1 (36 min of upfront thinking) and A2-T4 (cache misses) recur.
2. Copy the A3 blend to `/tmp/alex3d-a3`. Start from `examples/mm-launcher-a2/checks.json`, update the joints, fits, order, service and index entries from the A3 BOM, and run `cad check`. Score each R3 issue as caught, partial or missed, in the same table format as A2.
3. Check whether R3 confirms or refutes the six A2 candidates. Fix the cadcheck false positives or misses this shows. Archive the A3 blend only if it adds new regression patterns (each blend is about 6 MB in git).
4. Record the baseline row for A3 (see "Baseline" above) in the same format as A1 and A2.
