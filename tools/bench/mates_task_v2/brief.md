# Brief: two-servo pan-tilt camera head

A printed deck carries a pan servo; a printed pan bracket on its horn holds a tilt servo; a printed tilt bracket on
the tilt servo's horn holds a camera board. A printed cover goes over the pan servo. About 20-30 minutes of design
work. Purchased-part data: `KIT/components.json` (dimensions, tapped-hole patterns, connectors); placeholders:
`KIT/kit_parts.py` (each part in its own local frame, described by the entry's `frame` line).

The brief gives interfaces and constraints, not positions: work out where each part goes from them.

## World frame
X right, Y forward, Z up, mm. The **pan axis** is the world Z axis. The origin is on the pan axis at the deck's
underside; the deck lies on the table.

## Parts (use these names)

| Name | What | Interfaces and constraints |
|---|---|---|
| `PRT_deck` | printed plate 160 x 120 x 6, centred on the pan axis | Carries the pan servo and the cover. |
| `BUY_servo_pan` | `kit_parts.servo()` | Upright on the deck top, spline up, **its spline on the pan axis**, case toward -X (as in its frame). Fixed by **4 M2.5 screws from under the deck into its bottom tapped holes** (heads in counterbores: the deck lies on the table). |
| `BUY_horn_pan` | `kit_parts.horn()` | On the pan servo's spline: hub on the spline top, coaxial. |
| `PRT_pan_bracket` | printed | On the pan horn's disc, fixed by **4 M2 screws through 4 of the horn's holes** (0/90/180/270 deg); turns with it: joint **`PIV_pan`**, **-90 to +90 deg**, positive counter-clockwise seen from above. Holds the tilt servo. |
| `BUY_servo_tilt` | `kit_parts.servo()` | Held by the pan bracket with **4 M2.5 screws into its side tapped holes** (`tapped_holes.side`). At pan 0: **its spline points +Y**, the **tilt axis (its spline axis) is horizontal, crosses the pan axis, and is 40 mm above the pan horn's disc top**; the case hangs **below** the tilt axis; along the tilt axis the case is **centred on the pan axis**. |
| `BUY_horn_tilt` | `kit_parts.horn()` | On the tilt servo's spline: hub on the spline top, coaxial. |
| `PRT_tilt_bracket` | printed | On the tilt horn's disc, fixed by **4 M2 screws through 4 of its holes** (0/90/180/270 deg); turns with it: joint **`PIV_tilt`**, from **25 deg down to 60 deg up** (-25..+60 with + raising the camera; if your joint counts the other way, the same range negated: say which in the design log). Holds the camera. |
| `BUY_cam` | `kit_parts.camera()` | On the tilt bracket, fixed by **4 M2 screws through its holes**. At pan 0, tilt 0: the **lens looks along +X**; the **optical axis is horizontal and passes through both the tilt axis and the pan axis**; the **board's back is 25 mm in front of the tilt axis**; the board's own "up" (+Y in its frame) is world +Z. |
| `PRT_cover` | printed | Covers the pan servo case (sides and the top around the spline), **2 M3 screws** into or through the deck (your layout and style). |

Every moving part keeps at least 1 mm from everything it doesn't touch over the whole pan x tilt range. Screws are
modelled (`FST_*`) with holes cut and lengths from the stock list, and every part is registered as the skill's
conventions say (printed parts with `stl`, `print_rot`, `orient`, `supports`, `infill`; purchased with `mass_g`, `src`).

## Done when
- `cad build` writes `blender/model.blend` and `blender/manifest.json` in the project;
- `cad check blender/model.blend blender/checks.json` reports 0 fails, with your `checks.json` declaring the designed
  fits and contacts and an `assembly_order`;
- the design log (`DESIGN_LOG.md`, a few lines) says how each interface is made and where the parts ended up.

The scorer reruns `cad check` with `KIT/checks.json` as an overlay (clearances over a pan x tilt grid), measures each
purchased part's placement and each screw against the holes it should pass, poses the joints and compares the camera's
position and direction with the brief's answer, and counts the build's lines of code.
