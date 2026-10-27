# Task: drawing-reading tools, so the LLM stops doing computer vision by eye

Branch `feat/drawing-tools`, worktree `.claude/worktrees/drawing-tools`. PR target `next` (the coordinator opens it).

## Why
CADGenBench pilot, 2026-10-27 (same model, prompt and 25-min budget; scores in `tools/cgb/pilot1_scores.json`;
prompts and helpers in `tools/cgb/`):

| arm | mean CAD score on 10 drawings | median minutes |
|---|---|---|
| build123d | 0.699 | 5.4 |
| Blender/cadlib (faceted STEP) | 0.643 | 16.7 |

- The biggest losses were **interpretation**, not geometry: 116 (an end view read rotated 180°: interface 0.001),
  131 (base put on the wrong side), 106 (two extra holes), 136 (faint drawing traced by eye). Agents self-rated 2/5 and
  shipped anyway.
- Agents spent minutes cropping the PNG and counting pixels to read positions, scale and hole sizes, i.e. doing simple
  CV and OCR with a whole LLM. The user's point: use tools better suited to that, and keep the LLM for what it is best
  at (reading views, intent, associating numbers with features).

## Data and environment
- Drawings: `/tmp/cgb-data/<id>/input.png` (3072×2118), generation samples 101–150 (49 of them).
  **Test set = 101,106,111,116,121,126,131,136,141,146. Do not open those drawings while developing.** Develop and
  measure on the other 39 (the dev set). Ground truth is private; there is no local scorer.
- Python 3.12 venv with build123d 0.10, OCP 7.9, pyvista, PIL, numpy: `/tmp/cgb-venv` (cadgenbench installed, source
  in `/tmp/cgb-src/cadgenbench`). For CV/OCR dependencies make a separate venv (`/tmp/drawtools-venv`); pip and OCR
  model downloads are allowed. Tesseract is not installed; prefer pip-installable options (e.g. RapidOCR/ONNX,
  PaddleOCR, EasyOCR) and look at eDOCr/eDOCr2 (OCR built for mechanical drawings) as prior art.
- Run any downloaded code's Python with `-I`, from outside its directory.

## Prior art first (CLAUDE.md "Prior art before new code")
Survey and *measure* before writing: eDOCr/eDOCr2, general OCR packages, OpenCV (HoughCircles, contours), and
`cadgenbench`'s own renderer (`cadgenbench.common.viewer`, camera presets) for projections. The doc for this branch needs
a "Why not the existing code" section with numbers.

## Build (in `tools/drawing/`, one CLI, compact text/JSON output; never dump big arrays into the agent's context)
1. **`text`**: dimension and note text with pixel boxes (Ø, R, M-threads, "4X", "THRU", tolerances, angles), from a
   whole sheet or a crop. Measure precision/recall on 5 dev drawings you label by hand (put labels in the repo).
2. **`scale` / `measure`**: calibrate px→mm per view from one known dimension (two points + value), then measure
   points, distances, angles and circles in mm. **`holes`**: detect circles in a view crop, report centres and
   diameters in mm, grouped into patterns (rect, PCD, line) in minimal form.
3. **`overlay`** (render-and-diff): given a candidate STEP or STL, a view crop, its scale and view direction, render the
   part's orthographic outline at the drawing's scale and overlay it on the crop; output a PNG and an agreement number,
   and test all 8 flips/90° rotations so a mirrored or rotated reading shows up as "best match: mirrored X". This is the
   check that would have caught 116 and 131.
4. Prompt addendum `tools/cgb/prompt_drawing_tools.md`: how a designer agent uses these tools in the pilot (short).
   Also fix in `tools/cgb/check_step.py` anything you hit; it already prints the gate result last.
5. Tests in `tools/verify.d/` (synthetic drawings you generate with known answers, plus your labelled dev drawings),
   added to `tools/verify_all.sh`. Run verify_all once at the end, detached via `setsid` (nohup alone gets killed);
   others may be running it, so don't start more than one.

## Do NOT
- Run the benchmark pilot or spawn agents; the coordinator runs the evaluation on the test set.
- Push, open PRs, or touch `main`, `next`, the pin worktree (`~/code-stuff/alex-3d-skills-pin`) or other worktrees.

Commit on `feat/drawing-tools` in the repo's commit style, ending with
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Report back (short)
Tools built and how to call them, measured accuracy on dev drawings (text P/R, scale/measure error in mm, holes found,
overlay catching planted flips), what prior art you used or rejected and why, verify_all result, and the exact prompt
addendum to give pilot agents.
