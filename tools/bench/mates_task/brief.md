# Brief: servo arm and controller on a deck

A small assembly: a printed deck carries a bus servo that swings a printed arm, and a controller board under a
printed lid. About 20 minutes of design work. Purchased-part data: `KIT/components.json`; placeholders:
`KIT/kit_parts.py` (each part in its own local frame, described by the entry's `frame` line).

## World frame
X right, Y forward, Z up, mm. Origin at the centre of the deck's underside; the deck lies on the table at z = 0.

## Parts (use these names)

| Name | What | Where and how |
|---|---|---|
| `PRT_deck` | printed plate 140 x 90 x 4, centred on the origin, underside at z = 0 | Carries everything. Add what the interfaces below need: a locating rim or pocket for the servo case, standoffs for the board, bosses for the lid screws. |
| `BUY_servo` | `kit_parts.servo()` | Stands upright on the deck top (case bottom on z = 4), spline up, **spline axis at x = -35, y = 0**, case toward -X (as in its frame). Located by the deck (rim or pocket, 0.2 mm clearance); no screws. |
| `BUY_horn` | `kit_parts.horn()` | On the spline: hub underside on the spline top, coaxial. |
| `PRT_arm` | printed arm, 4 mm thick, **70 mm from the spline axis to its tip** | Lies on the horn's disc top, fixed to the horn by **4 M2 screws through 4 of the horn's holes** (0, 90, 180, 270 deg), so it turns with the horn. Joint **`PIV_arm`** about the spline axis, **-90 to +90 deg**, the arm pointing +X at 0. |
| `BUY_pcb` | `kit_parts.pcb()` | Board centred at **x = +35, y = 0**, components up, header toward +X, **underside 8 mm above the deck top (z = 12)**, on 4 printed standoffs, held by **4 M2.5 self-tap screws** from the top through its holes into the standoffs. |
| `PRT_lid` | printed cover over the board | Covers the board from above with at least 1 mm to every component, held to the deck by **4 M3 screws** (your layout and style). Must clear the arm through its whole swing by at least 2 mm. |

Screws are modelled (`FST_*`), with their holes cut, lengths from the stock list, and every part registered as the
skill's conventions say (printed parts with `stl`, `print_rot`, `orient`, `supports`, `infill`; purchased with
`mass_g`, `src`).

## Done when
- `cad build` writes `blender/model.blend` and `blender/manifest.json` in the project;
- `cad check blender/model.blend blender/checks.json` reports 0 fails, with your `checks.json` declaring the designed
  fits and contacts (servo in its rim, hub on the spline) and an `assembly_order`;
- the design log (`DESIGN_LOG.md`, a few lines) says how each interface is made.

The scorer reruns `cad check` with `KIT/checks.json` as an overlay, measures each purchased part's placement and each
screw against the hole it should pass, and counts the build's lines of code.
