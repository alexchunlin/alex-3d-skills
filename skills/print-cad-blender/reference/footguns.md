# Foot-guns from the mm-launcher run, and what catches them

IDs point into `<repo>/docs/FINDINGS.md`. "Caught" means cadcheck or cadq flags it on the archived blend of that attempt
(`<repo>/examples/mm-launcher-a1/`, `<repo>/examples/mm-launcher-a2/`).

| ID | Mistake | Catch | Caught on A1 |
|---|---|---|---|
| A1-F1 | Feed drops the payload outside the nip; at 45° tilt it hits the chute wall | `drop_tests` with a landing `angle` window at every tilt | yes: lands 44-80° vs 0-26° window; tilt 22.5/45 hit `PRT_launcher_body` |
| A1-F2 | Adjustment range never reaches the working condition (nip > payload) | `distances` with `max` | yes: 9.50 mm vs ≤ 7.0 |
| A1-F3 | Screw head under a rotating disc | interference over Fasteners across joints | yes: 48.6 mm³ (27.2 at home) |
| A1-F4/F11 | Screw that can't be driven, or only through a 102 mm bore | fastener `access` per assembly step | yes: trunnion screws need 114 mm reach |
| A1-F5 | Tilt limit with no margin (contact at 46°, overlap at 47.5°) | sweep with `overtravel_deg`, clearance minimum | yes: 0.21 mm fail at 45°, overlap warn at 47.5° |
| A1-F9 | Zero-clearance rubbing face across a joint | contacts across joints fail unless declared `contact` | yes: trunnion x bonnet at 19 poses |
| A1-F10 | Screw modelled reversed (shank in the flywheel) | head-buried test plus cross-joint interference | yes: 4 motor screws, 27 mm³ each |
| A1-F12 | Cable bullet joints at a moving bend; missing UART route | `cable_leads` with `asm.cable(lead_len=)`; route list in the design log | needs `path_len` (cadlib cables) |
| A1-F13 | Purchased envelope with 1 mm clearance | `slide_out` with `min_clearance` | passes (no volumetric clash); warn needs the purchased tolerance |
| A1-F14 | "checks_passed: true" with fasteners and cables excluded | report `coverage` and `not_checked`, never a bare boolean | by construction |

## Attempt 2 (the designer had fixed every A1 item above; these are new)

| ID | Mistake | Catch | Caught on A2 |
|---|---|---|---|
| A2-F1 | Pinch bolts a straight bit can't reach, and an L-key can't swing (rim and web in the way) | fastener access: straight bit, then L-key arc ≥ 60° | yes: blocked at 18.5 mm, L-key arc 0° |
| A2-F2 | Documented feeder index (park 0, fire 60) puts a pocket over the outlet at **both** ends: two candies per fire | `index_tests` over the documented motion | yes: 2 windows (0-6°, 54-60°) |
| A2-F3 | M3 x 16 pinch bolt ends 0.36 mm short of its nut | bolt-to-nut pairing (any `FST_*nut*` on the bolt axis) | yes: 0.35 mm short |
| A2-F4 | Rigid 1 mm squeeze on a hard payload, nothing yields | `distances` with `ray`, `payload_mm` and `compliant` | yes (warn): 1.01 mm squeeze, no compliant part |
| A2-F5 | Through-bolts and nuts inside the battery envelope; the designer's checks skipped same-pivot fastener vs purchased | shank or nut inside a `BUY_` it does not thread into | yes: 4 bolts 2.5 mm deep, 4 nuts 100% inside |
| A2-F6 | Gap adjustment "needs no disassembly", but one clamp screw is reachable only at tilt 45 | `service` ops with the built machine present | yes (warn): blocked by the right arm 2.2 mm out |
| A2-F7 | Magnet jig datum is the nacelle bore: worst case 0.55-0.75 mm vs 0.3 | `stacks` (declared terms) | arithmetic only: you must write the chain |
| A2-F8 | 10 mm of bus cable bare between bonnet and plate | cable exposure (≥ 8 of 26 rays escape) | yes (warn): 11 mm at x -107, z 249 |
| A2-F9 | Jack screws and nuts hang under the pod | head stand-off > 2 mm | yes (warn): 11 mm |

**Rule from A2:** every sentence in the BOM or design log that states a motion, timing or service claim ("park at 0, fire
at +60", "change the gap without disassembly", "the flywheel comes off at tilt 45") gets a `checks.json` entry
(`index_tests`, `service`, `slide_out`) **before** it is written into the BOM. A2-F2 (a major) and A2-F6 were confident prose
that nothing had executed.

The checker does not cover these. Use sections, the design log or the reviewer checklist:
- service paths, such as tape or shim changes, that need a full teardown (A1-F6)
- alignment jigs, such as magnet centring (A1-F7)
- the order of indexing and feed moves, such as tilting mid-drop (A1-F8); single-axis index timing is `index_tests`
- tolerance stacks you have not written down (A2-F7)
- form language, proportions, colour (A2 R2 #10)
