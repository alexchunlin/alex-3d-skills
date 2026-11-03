# features.SIZES vs bd_warehouse (issue #37)

`tools/verify.d/sizes_vs_bdw.sh` compares `features.SIZES` (with the `RULES` M3 overlay that `size_rules()` applies) and
cadcheck's `fasteners.stock_lengths` with bd_warehouse's ISO tables, copied unchanged into `bd_warehouse_data/`
(gumyr/bd_warehouse c88b9a4, Apache-2.0, sha256 in `SHA256SUMS`; see `NOTICE` and `LICENSE`). Run it from the repo root with
`python3 -I tools/verify.d/sizes_vs_bdw.py "$PWD"` (`--table` prints the excepted rows).

Tolerance: nut across-flats exact; every other diameter and height 0.05 mm. 128 values compared (M2, M2.5, M3, M4, M5:
nut AF and height, clearance, self-tap pilot, cap/pan/csk dk and k, heat-set hole and radial wall, stock lengths).
110 agree. The 18 below are on `tools/verify.d/sizes_vs_bdw_exceptions.json`; the check fails on any other
disagreement, on an exception that stops firing, and on a CSV that no longer matches its sha256. Verdicts "pending
coupon" and "pending standard" leave our value alone; no `SIZES` value changed in this PR.

| Row | Ours | bd_warehouse | Verdict | Reason |
|---|---|---|---|---|
| M2 cap_d | 3.8 | 3.98 | ours (plain-head max) | ISO 4762 dk max is the plain head; bd_warehouse lists the knurled-head max (+0.18 mm M2-M3, +0.22 mm M4-M5). Our counterbore_d is dk + 1.0, so the knurled max still clears with 0.82 mm diametral margin. Counterbore fit itself: pending coupon. |
| M2.5 cap_d | 4.5 | 4.68 | ours (plain-head max) | ISO 4762 dk max is the plain head; bd_warehouse lists the knurled-head max (+0.18 mm M2-M3, +0.22 mm M4-M5). Our counterbore_d is dk + 1.0, so the knurled max still clears with 0.82 mm diametral margin. Counterbore fit itself: pending coupon. |
| M3 cap_d | 5.5 | 5.68 | ours (plain-head max) | ISO 4762 dk max is the plain head; bd_warehouse lists the knurled-head max (+0.18 mm M2-M3, +0.22 mm M4-M5). Our counterbore_d is dk + 1.0, so the knurled max still clears with 0.82 mm diametral margin. Counterbore fit itself: pending coupon. |
| M4 cap_d | 7 | 7.22 | ours (plain-head max) | ISO 4762 dk max is the plain head; bd_warehouse lists the knurled-head max (+0.18 mm M2-M3, +0.22 mm M4-M5). Our counterbore_d is dk + 1.0, so the knurled max still clears with 0.78 mm diametral margin. Counterbore fit itself: pending coupon. |
| M5 cap_d | 8.5 | 8.72 | ours (plain-head max) | ISO 4762 dk max is the plain head; bd_warehouse lists the knurled-head max (+0.18 mm M2-M3, +0.22 mm M4-M5). Our counterbore_d is dk + 1.0, so the knurled max still clears with 0.78 mm diametral margin. Counterbore fit itself: pending coupon. |
| M2 pilot_d | 1.7 | 1.6 | pending coupon | bd 'Soft' is a tap-drill table value, not an ISO dimension; ours is deliberately 0.1 above it for a PLA self-tap (features.py header: M2 holes are table values to confirm by coupon). Left alone. |
| M2.5 insert_d | 3.6 | 4 | pending coupon | bd/vendors (CNC Kitchen M2.5x4 dc 4.0; Ruthex M2.5x5.7 dc 3.9) say 3.9-4.0; ours 3.6 is 0.3-0.4 mm under the vendor figure. Vendor data supports theirs, but a print decides; coupon 3.6/3.8/3.9/4.0 pending, SIZES not changed here. |
| M3 pan_d | 6 | 5.6 | ours (ISO 7045) | features.py:52 cites ISO 7045 (cross-recess pan head, dk max 6.0). bd has no ISO 7045 table: its pan data is ISO 14583 (Torx) and ISO 1580 (slotted), both 5.6 at M3. A different standard, not a contradiction. M2/M2.5/M4/M5 agree with 14583 because the standards coincide there. Cutter-side, a larger dk only widens the counterbore. |
| M3 csk_d | 6 | 5.6 | theirs (change in a follow-up) | ISO 7046 actual dk max at M3 is about 5.5 (issue #37), bd lists 5.6; ours 6.0 is above both and has no citation (RULES overlay comment: '90 deg countersunk'). Standard supports theirs. SIZES not changed in this PR; follow-up decides whether the 0.4 mm margin is wanted. |
| M4 csk_d | 8.4 | 7.5 | bd table unreliable; pending standard | bd's iso7046 M4 dk 7.5 and k 2.2 are identical to its iso2009 M4 dk and k, so the row is not independent evidence. Ours cites ISO 7046 (features.py header). Not settled from the tables; left alone. Larger dk is the safe side for a countersink cutter. |
| M4 csk_h | 2.7 | 2.2 | bd table unreliable; pending standard | Same bd error as M4 csk_d: iso7046 M4 k 2.2 equals iso2009 M4 k. Left alone. |
| M5 csk_d | 9.3 | 9.2 | bd table unreliable; pending standard | Same bd error as M4: iso7046 M5 (dk 9.2, k 2.5) equals iso2009 M5. 0.1 mm difference, left alone. |
| M5 csk_h | 2.7 | 2.5 | bd table unreliable; pending standard | Same bd error as M4: iso7046 M5 k 2.5 equals iso2009 M5 k. Left alone. |
| M4 insert_wall | 1.6 (axial only) | 2.1 | pending coupon | bd material_thickness for the Ruthex/CNC Kitchen M4x8.1 insert is 2.1 mm of material around the insert; our min_wall 1.6 is only applied along the axis, no radial wall is enforced for inserts. Vendor guidance supports theirs; follow-up: a radial-wall check in cadcheck, sized from a coupon. |
| M5 insert_wall | 1.6 (axial only) | 2.6 | pending coupon | As M4: vendor material_thickness 2.6 mm for M5x9.5 against 1.6 axial-only. Follow-up with the M4 check. |
| M3 stock_length 18 | 18 | not a nominal length of ISO 4762/7046/14583 | ours (stock list) | cadcheck DEFAULTS fasteners.stock_lengths is the set the project buys; the ISO lists are preferred lengths and 18 / 22 mm are non-preferred but sold. No dimensional conflict; a project's checks.json can override the list. |
| M3 stock_length 22 | 22 | not a nominal length of ISO 4762/7046/14583 | ours (stock list) | cadcheck DEFAULTS fasteners.stock_lengths is the set the project buys; the ISO lists are preferred lengths and 18 / 22 mm are non-preferred but sold. No dimensional conflict; a project's checks.json can override the list. |
| M4 stock_length 18 | 18 | not a nominal length of ISO 4762/7046/14583 | ours (stock list) | cadcheck DEFAULTS fasteners.stock_lengths is the set the project buys; the ISO lists are preferred lengths and 18 / 22 mm are non-preferred but sold. No dimensional conflict; a project's checks.json can override the list. |

Matches (no row above): nut AF and height (ISO 4032), clearance Normal (ISO 273 medium), ISO 14583 pan dk and k for
M2, M2.5, M4, M5, cap head k, and the M3, M4, M5 self-tap pilots (M2.5 differs by exactly 0.05, inside the tolerance).
Not compared (no bd_warehouse counterpart): `tap_d` (PLA machine-screw tap), `trap_af`, `counterbore_d`, fits.
