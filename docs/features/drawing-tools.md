# Feature: drawing-reading tools (`tools/drawing/draw`)

Branch `feat/drawing-tools`, measured 2026-10-27 on the 39 CADGenBench dev drawings (generation samples 101-150
minus the test set 101, 106, 111, 116, 121, 126, 131, 136, 141, 146, which were never opened). The task brief is
`docs/tasks/2026-10-27-drawing-tools.md`. Timings were taken while other sessions held the machine at load 40-58, so
read them as upper bounds.

## Why

In CADGenBench pilot 1, most of the lost score came from interpretation, not geometry (`tools/cgb/pilot1_scores.json`):
- 116: an end view read rotated 180 deg (interface 0.001);
- 131: the base on the wrong side;
- 106: two extra holes;
- 136: a faint drawing traced by eye.

The agents also spent minutes cropping the PNG and counting pixels to get positions, scale and hole sizes. That is CV
and OCR work, and a whole LLM is a poor tool for it. These tools do that part and leave the LLM to read views, intent,
and which number belongs to which feature.

## What was built

One CLI, `tools/drawing/draw` (a sh wrapper running `drawtool.py` in `/tmp/drawtools-venv`; build the venv with
`sh tools/drawing/setup_venv.sh`). Every command prints a few lines, or `--json`.

| Command | What it does |
|---|---|
| `views IMG` | View boxes: ink blobs with their dimensions, and an ink fraction that marks shaded iso views |
| `text IMG [--crop BOX] [--kind dia,radius]` | Dimension and note text with pixel boxes, parsed into kind (dia, radius, thread, chamfer, angle, linear, note), value, count (`4X`, `(6X)`), pitch, depth, tolerance, flags (THRU, TYP, DEEP, DRAFT). Results are cached per sheet in `/tmp/drawtools-cache` |
| `scale IMG --auto` | px/mm from the drawing's own linear dimensions. It measures each dimension line between its arrow-tipped extension lines, divides by the value, and clusters the ratios, because views on one sheet often differ in scale |
| `scale IMG --p1 X,Y --p2 X,Y --mm V` / `--circle X,Y --mm D` | px/mm from one dimension. The points snap to the extension lines, and the dimension line they sit on is ignored |
| `measure IMG --scale S --dist / --pt / --circle / --angle` | Distances, positions from an origin (y up), circle fits (centre and Ø) and angles, in mm |
| `holes IMG --crop BOX --scale S [--origin X,Y]` | Circles in mm, grouped into concentric sets (bore, counterbore, rim) and then into patterns: PCD (dia, start angle, step, and any empty position), grid, line |
| `overlay MODEL IMG --crop BOX --scale S --view top\|front\|...\|all` | Render and diff. MODEL is a STEP or STL. Prints OK, AMBIGUOUS or MISMATCH and, for a mismatch, the rotation that fixes the part. Writes a PNG: blue = as modelled, red = the better reading |

Code: `tools/drawing/dtlib/` holds `sheet` (load, faint-ink normalisation, the CADGenBench sheet template mask),
`ocr`, `textparse`, `geom` (snap, circle fit, dimension lines, auto-scale), `holes`, `overlay`, `views` and `cache`.
`tools/drawing/eval_dev.py` measures accuracy on the dev drawings and refuses the test set.
The prompt addendum for pilot agents is `tools/cgb/prompt_drawing_tools.md`.

How the pieces work:
- **text.** RapidOCR (PaddleOCR PP-OCRv4 detector and recogniser, ONNX) runs on 2000 px tiles upscaled 2x. A second
  pass runs on the sheet turned 90 deg, for upward-running dimension text. The two passes are merged so each read
  comes from the pass in which it runs along the line; for overlapping reads, the longer one wins. Lines cut by a tile
  edge are stitched back together. Split callouts are joined (`Ø10.00` + `(6X)`, `4X` + `Ø30` + `THRU`), and run-together
  numbers are split (`31 30`). After that, `textparse.norm` fixes the glyphs general OCR gets wrong on these sheets:
  Ø read as Q, 0, D, @ or β; ° read as `*` or a middle dot; arrowheads read as `T`, `-` or `+`.
- **scale --auto.** The dimension line is the nearest line that passes through the text, under it, or beside its end.
  It is followed both ways. A terminal is an extension line next to an arrowhead, so chained dimensions that share an
  extension line are not merged. The text's dimension runs between the two terminals that bracket it.
- **holes.** OpenCV `HOUGH_GRADIENT_ALT` proposes circles. Text boxes from the OCR cache are blanked first, because
  "0", "6" and "8" are rings. Each proposal is refitted on the ink (the mode of ray-crossing radii, then a Kasa fit),
  and kept when at least 80% of its circumference is inked.
- **overlay.** The part is tessellated (build123d for STEP; STL is read directly) and rasterised at the drawing's
  scale with a painter's algorithm, one face index and depth per pixel. An edge is a pixel where the normal turns more
  than 30 deg, the depth jumps, or the part meets the background: the visible lines of a drawing. Each of the 8
  flips and quarter turns, at 5 sizes from x0.97 to x1.03, is matched to the dilated drawing ink by FFT correlation over
  every shift. f is the harmonic mean of P (model edge pixels on ink) and R (view ink near model edges). View names
  and directions are cadgenbench's camera presets, so they agree with `check_step.py`'s renders.

## Measured

### text: precision and recall against hand labels (`eval_dev.py text`; labels in `tools/verify.d/drawing_labels/`)

Labels cover every text item in the drawing area outside the sheet template: dimensions, callouts, notes, view and
datum letters, and balloon numbers. A read matches a label when its normalised text is equal and the boxes touch.

| Drawings | Labels | P | R | Dimensions only, P / R |
|---|---|---|---|---|
| 102, 103, 139, 145, 147 (the OCR merging and the glyph fixes were tuned on these) | 275 | 0.962 | 0.916 | 0.982 / 0.912 |
| 109, held out: labelled after the settings were frozen | 59 | 0.763 | 0.763 | 0.759 / 0.759 |
| 109, after three generic glyph fixes it exposed (`·` as °, `β` as Ø, a leading `/`) | 59 | 0.864 | 0.864 | 0.870 / 0.870 |

Per drawing (tuned set), P / R: 102 0.95/0.98, 103 0.99/0.82, 139 0.96/0.96, 145 0.90/0.95, 147 1.00/1.00. 103 is
the hard case: 10 px text, many small vertical and 45 deg labels. What is still missed: rotated text at 45 deg, a Ø
that the recogniser drops entirely (Ø66.94 read as 66.94), and a few small vertical numbers. A whole sheet takes 15-60
s under load (mean 33 s over 34 dev sheets at load 40-58), cached after the first read. `text --crop` on one view is faster.

### scale and measure

- **Auto-scale against a two-point calibration.** On 102, `scale --auto` gives 1.7109 px/mm from 12 agreeing
  dimensions (spread 0.53%). A snapped two-point calibration on the 220 mm dimension gives 1.7114, 0.03% apart. On
  145, auto gives 5.3683 from 27.50 and 23.82, and a snapped calibration on 27.50 gives 5.3636 (0.09%).
- **Views differ in scale.** On 102, the plan view is 1.7561 px/mm (from its Ø120 circle) and the section 1.7111: 2.6%
  apart. Other sheets have 2-3 clusters (139: 1.148 and 1.561; 145: 5.36 and 3.17). Calibrate per view.
- **Leave-one-out over the dev sheets** (`eval_dev.py scale`; each dimension in a cluster of 3 or more, re-measured at
  the scale of the others; `eval_dev.py scale`, all 39 sheets): 36 of 39 sheets have a cluster of 3 or more agreeing
  dimensions, and 20 have two or more scales. 552 of the 998 dimension lines found join a cluster. For those, the
  median error is 0.08 mm, p90 0.31 mm and max 1.35 mm; 96% are within 0.5 mm and 95% within 1%. These are the
  dimensions that agree within 1.5%, so the numbers show how precisely a calibrated view measures, not how often
  auto-scale finds the right dimension line. The other 446 lines are dimensions whose text sits away from their own line
  (leaders, angles, radii misread as linear), or that belong to a view with fewer than 3 dimensions.
- **Circle diameters against their callouts** (`eval_dev.py circles`, scale from one linear dimension or circle):
  7 of 8 found, mean |error| 0.15 mm, max 0.40 mm. On 145: Ø116.00 → 115.60, Ø66.94 dash-dot → 66.75, Ø40.00 →
  39.93, Ø15.00 → 14.98, Ø10.00 (6X) → 9.97, and the 6 holes' PCD (2 x 13.75) → 27.49 with a step of 60.0 deg. On 102,
  the Ø230 hole PCD measures 229.67 (6 holes, uneven steps as drawn). The Ø175.3 groove was not found at 60% ring
  support.
- **Synthetic sheet at 3 px/mm** (`verify.d/drawing_tools_cases.py`):
  - 120 mm dimension measured 120.00 with snapping;
  - 3x Ø8 holes 7.94, centres within 0.15 mm;
  - boss Ø24 / Ø12 measured 24.07 / 11.97;
  - auto-scale 3.000 from 4 dimensions, 3 of them vertical.

### holes

On the synthetic sheet it finds exactly the 5 drawn circles. On dev 145's plan view it finds the 6 holes (Ø10.00 (6X))
as one PCD, and the bore, the boss, the dash-dot circle and the rim as one concentric set. On 102 it finds the 6 holes
on their Ø230 PCD. Arcs and circles hidden by more than 20% are dropped. The output marks partly hidden circles, and
for an even PCD it names any position where it found no circle.

### overlay: planted flips

| Case | Planted | Verdict |
|---|---|---|
| Synthetic L-plate, top view | none | OK (margin 0.47) |
| " | rotated 180 about Z (STEP, and again as STL) | MISMATCH 'rotated 180', fix: rotate 180 about +Z (f 0.95 vs 0.42) |
| " | mirrored in X | MISMATCH 'mirrored left-right' (0.95 vs 0.47) |
| Synthetic, front view | turned over (180 about X: the base on the wrong side, as in 131) | MISMATCH 'mirrored top-bottom', fix: 180 about +X (0.96 vs 0.60) |
| " | none | OK (margin 0.05) |
| Dev 142 (a part traced from its profile view and extruded) | none | OK (margin 0.09) |
| " | rotated 180 | MISMATCH 'rotated 180' (0.53 vs 0.34) |
| " | mirrored | MISMATCH 'mirrored left-right' (0.50 vs 0.30) |
| " | rotated 90 | MISMATCH 'rotated 90 CW', fix: rotate -90 about +Z (0.53 vs 0.16) |

All 9 planted cases are called correctly. A view that is symmetric under some transform reports AMBIGUOUS and names
the ties, rather than guessing. Cost: 3-5 s to load a STEP (build123d import), 0.1 s per raster, and 0.5-1.5 s for the
8 x 5 FFT matches on a 1000 px crop.

## Why not the existing code (measured)

| Prior art | What it would do | Measured | Verdict |
|---|---|---|---|
| RapidOCR 1.4.4 with defaults, whole sheet (`tools/prior_art/drawing_ocr_compare.py run rapidocr-default`) | text | On the 5 labelled sheets: P 0.800, R 0.538 (dimensions 0.801 / 0.504), 5 s per sheet. 103: R 0.19 | Kept as the engine. The gap is configuration: by default it shrinks any image over 2000 px to 2000, so the 3072 px sheet is read at 0.65x and small text is lost. It also has no pass for vertical text and no Ø or °. Tiles at 2x, a 90 deg pass, merging and glyph fixes take it to P 0.962, R 0.916, at 3-5x the time |
| PaddleOCR | text | Not run separately: RapidOCR ships the same PP-OCRv4 detection and recognition models as ONNX, without the paddlepaddle install | Same models as the row above |
| EasyOCR 1.7 (`run easyocr`, CPU, en) | text | P 0.524, R 0.393 (dimensions 0.509 / 0.338), 32 s per sheet. 103: R 0.14 | Rejected: lower on every sheet, slower, and it needs torch (about 1 GB) |
| eDOCr2 ([javvi51/edocr2](https://github.com/javvi51/edocr2) f6f9651, MIT; recogniser `recognizer_dimensions_2.keras` from its v1.0.0 release; TensorFlow 2.16 in its own venv; `run edocr2`) | text, built for mechanical drawings | P 0.380, R 0.229 (dimensions 0.450 / 0.263), 58 s per sheet. 103: 0 matches. It does read Ø (`⌀66.94`, which RapidOCR drops), but it splits and merges callouts (`13.58 13.79`, `45.00: 15.47`) and garbles section labels | Rejected. Its "is this a dimension" filter and its table reader need Tesseract, which isn't installed; the run stubs the filter to "yes", its best case for dimensions. Its `symbol_search` crashes on these sheets (`ValueError`, list.remove on tuples that hold arrays) and is caught, which keeps the recognised text without its Ø template pass. eDOCr (v1) is the same keras-ocr design and was not run |
| OpenCV `HoughCircles` alone (`HOUGH_GRADIENT` and `HOUGH_GRADIENT_ALT`) | holes | Synthetic view, 5 true circles: 16 proposals from `HOUGH_GRADIENT`, 7 from `_ALT`. Dev 145 plan view: 8,950 / 208. Dev 102: 7,744 / 65 | Kept as the proposal step. Verifying each proposal on the ink (refit, 80% ring support, text blanked) brings 145 to 10 circles and the synthetic sheet to exactly 5 |
| cadgenbench `render_step` (`common/viewer.py`, the renderer `check_step.py` uses) | overlay | It fits each view to the window (`_parallel_scale_for_view`) and draws shaded faces without edge lines. You can't set px/mm, and the PNG has no lines to compare with a drawing | Its camera presets (`camera_presets.PRESETS`) are reused, so `--view front` means the same thing in both tools. The renderer itself is not |
| build123d hidden-line projection (`Shape.project_to_viewport`, OCCT HLRBRep) | overlay edges | 8 edit-fixture STEPs (201-208, real parts): 1.4-13.7 s per view, and 207 returned no edges at all. On a faceted STEP from the Blender arm every facet becomes an edge | Used only to draw the synthetic test sheet, so the test's drawing doesn't come from the renderer under test. The raster edges take 0.1 s per view and treat STEP and STL the same |

## Limits and follow-ups

- Text in a 45 deg orientation (slanted radius leaders) is read only when the detector's own box rotation catches it;
  a ±45 deg pass would cost two more passes.
- Auto-scale needs at least 2 linear dimensions that agree in a view. Plan views with only Ø and angle dimensions need
  `scale --circle`. Two-member clusters can be coincidences: check that a cluster's dimensions are in your view.
- Overlay compares one view against the visible edges. Hidden lines drawn dashed on the sheet lower P a little for
  every transform alike. A part that is wrong in shape, not orientation, shows as low f overall, which the verdict
  reports.
- `holes` reports circles, not whether they are holes or bosses; the views and the section decide that.
