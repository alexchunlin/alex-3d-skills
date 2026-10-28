---
name: cad-design-review
description: Independent review and 1-10 scoring of a 3D-printable Blender assembly for functionality, manufacturability and aesthetics, with measured evidence. Use when asked to review, score or verify a CAD design attempt, or to check whether previous review issues were fixed.
---

# CAD design review

You are the reviewer, not the designer. Every issue you raise carries a number or a file that a third party can re-run. Tools come from the `print-cad-blender` skill (`<pcb>` = `~/code-stuff/alex-3d-skills/skills/print-cad-blender`): `<pcb>/scripts/cad check` and `<pcb>/scripts/cad q`.

## Steps

0. **Notes go in as you measure, not at the end.** Create `<review_dir>/notes.md` before your first command and append each result right after it (what, number, script path). Notes written last save nothing (PA-A1-T1). If the file exists when you start, you are a restart: read it and skip those measurements (A3-T4: a restart redid 6.6 min of scripts).
1. **Run the checks yourself.** Run `cad check <blend> <checks.json> <review_dir>/cadcheck.json` on a **copy** of the .blend. Read the summary, `coverage` and `not_checked`. Diff it against the designer's report: any fail they didn't mention, or any `not_checked` item they claimed, is an overclaim issue. Done when you can list every fail with its row. Every **untriaged warn** (`summary.warn_list`) is a lead. In v2 A1, three of R1's twelve issues were designer warns nobody had acted on.
2. **Audit the check config.** Read `checks.json` (schemas: `<pcb>/reference/checks-config.md`). Every `allow`, `fits` and `accepted_warns` entry, and every `ignore` list, needs a physical reason you agree with, checked with `cad q ... dist` or a section. A bad allow hides a clash, a bad accept hides its warn, and an `"any": true` one any worse value too: PA-R3 measured a 0.58 mm wall under an accept and left the accept standing (PA-A3-T28). Joint ranges must match the brief. `drop_tests` must cover every payload path at every joint extreme. `assembly_order` must match the BOM steps. Done when each entry is marked agreed or disputed. Put every row you add (drop poses at adjuster ends, service, slide_out) in `<review_dir>/review_rows.json`, with `"=EXPR"` values, not literals, so they survive a redesign (PA-A3-T15). Run `cad check <copy> checks.json <review_dir>/cadcheck_review.json --overlay <review_dir>/review_rows.json`; add `--only drop,slide --overlay-only` for just your rows. Don't hand-edit copies of checks.json (V2A1-T6: 5.5 of 14.7 min).
3. **Read the manifest, not the script.** `manifest.json` gives parts, joints, fasteners, features and parameters. Open the build modules only for a specific question; grep them, don't page through them. Attempt 1's reviewer spent 7 calls reverse-engineering an 84 KB script.
4. **Verify previous issues.** For each one, re-run the measurement that defined it (`cad q`, a check row or a section) and mark it FIXED, PARTIAL or NOT FIXED with the new number.
5. **Walk the checklist** in `checklist.md`. For each item, cite a check row or a `cad q` line. If neither exists, make **one** targeted section or render (`cad q <blend> section ...`, `--lentil` for the payload). The budget is 12 new renders. Look at each render once; if you have to re-render with markers, plan the markers first.
6. **Score** with `rubric.md`. Write the anchor you matched next to each score.
7. **Write** `review.md` (format in `rubric.md`) and `review.json` in the same structure as your returned result. Rank issues by impact. Every issue has evidence (a check id, a cadq JSON line or a render path) and a fix with dimensions.

## Evidence rules

- **Measured beats inferred.** "0.21 mm at 45° (cad q sweep)" is evidence. "Looks tight in side_tilt45.png" is a lead to measure, not a finding.
- **Quote coverage.** If a class of problem was not checked, say so instead of implying it passed.
- **Re-run, don't trust.** Re-run the designer's numbers before you repeat them.
- **Config claims need the report too.** "X is in no step", "no row covers Y": cite the cadcheck.json field (`assembly.step_of`, the section's `rows`) that shows it. V2R2's "two parts in no step" was wrong, and it cost the design a manufacturability point (V2A2-R1).
- **Grep the report.** `cad rows <review_dir>/cadcheck.json REGEX` prints every row of every check on one line, `cad rows manifest.json FST_` the parts, and `cad rows checks.json "band|^allow"` the designer's config rows (V2R5 read allow, slide and stack rows with `json.load`). Don't write `json.load` snippets: v2 A3's agents wrote them in 67 bash calls, and 6 died on a guessed key (V2A3-T1).
- **Rows, not probe scripts.** Pocket fit, finger reach and end stops are `payload_fit`, `sightlines` and `slide_out` with `expect: blocked`. Put them in `review_rows.json` so the designer re-runs them.
