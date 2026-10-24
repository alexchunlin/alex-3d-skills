# Foot-guns from the mm-launcher run, and what catches them

IDs point into `<repo>/docs/FINDINGS.md`. "Caught" means cadcheck or cadq flags it on the attempt-1 blend
(`<repo>/examples/mm-launcher-a1/cadcheck_summary.json`).

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

The checker does not cover these. Use sections, the design log or the reviewer checklist:
- service paths, such as tape or shim changes, that need a full teardown (A1-F6)
- alignment jigs, such as magnet centring (A1-F7)
- the order of indexing and feed moves, such as tilting mid-drop (A1-F8)
- aesthetics
