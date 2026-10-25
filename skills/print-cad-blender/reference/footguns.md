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

## Attempt 3 (the designer fixed or partly fixed all 10 A2 items; these are new)

| ID | Mistake | Catch | Caught on A3 |
|---|---|---|---|
| A3-F1 | Feed reaches the tape at tilt 45 and at the 46° hard stop, but over a 21° / 20° slide with a 20° stall limit | slide `flattest_slide_deg` and `stall_margin_deg`; poses at the hard stop | yes (warn): 21.3° at 45, 20.3° at 46 (R3: 21.0, 19.9) |
| A3-F2 | Leaf spring printed standing up, so 21-44 MPa of bending stress crosses layer bonds | `flexures` with the beam direction and stress | yes: 85° off the bed, 20.9 > 15 MPa |
| A3-F3 | "Battery slides out without tools", but the stem runs through two adapter nuts from 10 mm out; the designer's checks tested the rest pose only | `slide_out`, which now includes fasteners | yes: blocked by `FST_adapter_nut_1`/`_3` at 5 mm |
| A3-F5 | Hinge axle threads 2.5 mm into PLA | engagement < `min_engagement` | yes (warn): 2.0 mm |
| A3-F7 | 8 mm of bundle seen through a notch at the bonnet foot (unchanged since A2; R2 missed it) | cable exposure, viewer-direction rule | yes (warn): 8 mm (R3: about 8) |
| A3-F8 | Battery-bay window shows the adapter nuts | nut visibility | partial: both nuts warned; window size not checked |
| V2A1-F1 | Nip adjuster tested at its home setting only; stalls at the open end, hood hits the body past the closed end | drop coverage warn ("holds PIV_hood at home"), then drop rows at both ends | yes: warn, then 3 fails with both ends |
| V2A1-F2 | Gap adjustment needs a cover that comes off only at tilt 45 | service warn when an op removes parts without a slide_out at its pose | only if the op lists `remove` |
| V2A1-F5 | 0.94 mm wall at self-tap pilots, 0.40 mm magnet stack, knife edges: all warns, none read | `accepted_warns`, `untriaged_warns` | yes (they were always warns) |
| V2A1-V4 | `contact: true` for a thrust face also hid the journal on the same pair | `contact_normal` | yes, once declared |
| V2A1-F3, V2A2-F2 | Pocket admits two payloads side by side (Ø15 in A1; Ø14.4 in A2 still seats a 12.5 x 6.5 pair) | `payload_fit` pair at the minimum size, flat at the maximum | yes on v2 A2: fail, 0.14 short; 13 x 7 blocked by only 0.11 |
| V2A2-F1 | Compliant leaf runs out of travel at full lift; the declared lift limit was not a real stop | `distances` at full deflection at both adjuster ends; a hard-stop row at the limit; drop coverage warn names the held joint | warn only ("holds PIV_nip_lift at home"); the rows are config |
| V2A2-F6 | A ray distance fixed in the tilt frame slipped past the moving hood lip (14.18 vs 7.06) | ray-vs-nearest warn | yes |
| V2A2-F4, F5 | Cables with no lead length; a step label's screw size disagreed with the model; a named spring with no flexures row | `cables`, `assembly` and `flexures` config warns | yes |

**Rule from v2 A1:** 0 fails is not done. Read every warn on your objects: fix it, or list it under `accepted_warns`
with a reason. Three of the first v2 reviewer's twelve issues were warns in the designer's own hand-off.

**Rule from A2:** every sentence in the BOM or design log that states a motion, timing or service claim ("park at 0, fire
at +60", "change the gap without disassembly", "the flywheel comes off at tilt 45") gets a `checks.json` entry
(`index_tests`, `service`, `slide_out`) **before** it is written into the BOM. A2-F2 (a major) and A2-F6 were confident prose
that nothing had executed.

The checker does not cover these. Use sections, the design log or the reviewer checklist:
- service paths, such as tape or shim changes, that need a full teardown (A1-F6)
- alignment jigs, such as magnet centring (A1-F7)
- the order of indexing and feed moves, such as tilting mid-drop (A1-F8); single-axis index timing is `index_tests`
- tolerance stacks you have not written down (A2-F7)
- form language, proportions, colour (A2 R2 #10, A3 R3 #4)
- brief numbers the design quietly misses, such as a nip range of 5.5-10 against the brief's 9-12 (A3 R3 #6): keep a table of the brief's numbers against the design's
- channel width along the payload path (R3 measured "at least 9.5 mm" by hand)
