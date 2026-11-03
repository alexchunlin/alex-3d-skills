# features.SIZES vs bd_warehouse (issue #37)

`tools/verify.d/sizes_vs_bdw.sh` compares `features.SIZES` (with the `RULES` M3 overlay, read from the `s.update(...)` call in
`size_rules()` by ast, not copied) and cadcheck's `DEFAULTS["fasteners"]["stock_lengths"]` with bd_warehouse's ISO tables,
copied unchanged into `bd_warehouse_data/` (gumyr/bd_warehouse c88b9a4, Apache-2.0; `LICENSE`, `NOTICE`, `SHA256SUMS`).
Run it from the repo root with `python3 -I tools/verify.d/sizes_vs_bdw.py "$PWD"` (`--table` prints the excepted rows).

Tolerance: nut across-flats exact; every other diameter and height 0.04 mm (the CSVs carry 2 decimals and our table 1, so
a 0.05 step is a disagreement). 128 values compared (M2, M2.5, M3, M4, M5: nut AF and height, clearance, self-tap pilot,
cap/pan/csk dk and k, heat-set hole and radial wall, stock lengths). 108 agree; the 20 below are on
`tools/verify.d/sizes_vs_bdw_exceptions.json`. The check fails on any other disagreement, on an exception that stops
firing, on a malformed exceptions file, and on a CSV in our copy that no longer matches `SHA256SUMS`.

Verdict words (also the enum in the JSON): `ours` = the standard or a deliberate choice supports our value; `theirs` =
the standard supports bd, change ours in a follow-up; `pending-coupon` = a test print decides; `pending-standard` = needs
the standard text or a datasheet. Nothing is marked `theirs` and no `SIZES` value changed in this PR.

The hash check compares our copy only; it cannot see upstream. To re-check against upstream, see `NOTICE`:
`git clone https://github.com/gumyr/bd_warehouse /tmp/bdw && git -C /tmp/bdw checkout c88b9a4 && (cd /tmp/bdw/src/bd_warehouse/data && sha256sum -c "$OLDPWD/tools/prior_art/bd_warehouse_data/SHA256SUMS")`.

| Row | Ours | bd_warehouse | Verdict | Why |
|---|---|---|---|---|
| M2 cap_d | 3.8 | 3.98 | ours | ISO 4762 dk max for a plain head is ours; bd_warehouse lists the knurled-head max (+0.18 mm M2 to M3, +0.22 mm M4 to M5). Our counterbore_d is dk + 1.0, so the knurled max still clears by 0.78 to 0.82 mm diametral. The counterbore fit itself is untested: coupon open in #37. |
| M2.5 cap_d | 4.5 | 4.68 | ours | ISO 4762 dk max for a plain head is ours; bd_warehouse lists the knurled-head max (+0.18 mm M2 to M3, +0.22 mm M4 to M5). Our counterbore_d is dk + 1.0, so the knurled max still clears by 0.78 to 0.82 mm diametral. The counterbore fit itself is untested: coupon open in #37. |
| M3 cap_d | 5.5 | 5.68 | ours | ISO 4762 dk max for a plain head is ours; bd_warehouse lists the knurled-head max (+0.18 mm M2 to M3, +0.22 mm M4 to M5). Our counterbore_d is dk + 1.0, so the knurled max still clears by 0.78 to 0.82 mm diametral. The counterbore fit itself is untested: coupon open in #37. |
| M4 cap_d | 7 | 7.22 | ours | ISO 4762 dk max for a plain head is ours; bd_warehouse lists the knurled-head max (+0.18 mm M2 to M3, +0.22 mm M4 to M5). Our counterbore_d is dk + 1.0, so the knurled max still clears by 0.78 to 0.82 mm diametral. The counterbore fit itself is untested: coupon open in #37. |
| M5 cap_d | 8.5 | 8.72 | ours | ISO 4762 dk max for a plain head is ours; bd_warehouse lists the knurled-head max (+0.18 mm M2 to M3, +0.22 mm M4 to M5). Our counterbore_d is dk + 1.0, so the knurled max still clears by 0.78 to 0.82 mm diametral. The counterbore fit itself is untested: coupon open in #37. |
| M2 pilot_d | 1.7 | 1.6 | pending-coupon | bd 'Soft' is a tap-drill table value, not an ISO dimension; ours is 0.1 above it for a PLA self-tap (features.py header: the M2 holes are table values to confirm by coupon). |
| M2.5 pilot_d | 2.1 | 2.05 | pending-coupon | Differs by exactly 0.05 (tolerance 0.04). Same bd 'Soft' tap-drill table; ours sits above the thread's minor diameter (features.py comment: M2.5 2.1 vs 1.95). Table value, coupon open in #37. |
| M2.5 insert_d | 3.6 | 4 | pending-coupon | Vendors (CNC Kitchen M2.5x4 dc 4.0; Ruthex M2.5x5.7 dc 3.9) say 3.9 to 4.0; ours is 0.3 to 0.4 mm under. Vendor data favours theirs, but a print decides: coupon 3.6/3.8/3.9/4.0 open in #37. |
| M3 pan_d | 6 | 5.6 | ours | ours follows the standard named in the features.py header comment ('ISO 7045 (pan)', cross recess, dk max 6.0 per that citation; not checkable here). bd has no ISO 7045 table: its pan data is ISO 14583 (Torx) and ISO 1580 (slotted), both 5.6 at M3, so this is a different standard rather than a contradiction. |
| M3 csk_d | 6 | 5.6 | pending-standard | bd's iso7046 rows equal its iso2009 rows (M3 5.6/1.65, M4 7.5/2.2, M5 9.2/2.5), so they are not independent evidence for ISO 7046; ours (features.py header: 'ISO 7046 actual dk (csk)') equal bd's iso10642 M3 row (6.0/1.7) at M3. Not settled from these tables; needs the standard text or a datasheet. SIZES left alone; a larger dk only widens the countersink cutter. |
| M3 csk_h | 1.7 | 1.65 | pending-standard | bd's iso7046 rows equal its iso2009 rows (M3 5.6/1.65, M4 7.5/2.2, M5 9.2/2.5), so they are not independent evidence for ISO 7046; ours (features.py header: 'ISO 7046 actual dk (csk)') equal bd's iso10642 M3 row (6.0/1.7) at M3. Not settled from these tables; needs the standard text or a datasheet. SIZES left alone; a larger dk only widens the countersink cutter. |
| M4 csk_d | 8.4 | 7.5 | pending-standard | bd's iso7046 rows equal its iso2009 rows (M3 5.6/1.65, M4 7.5/2.2, M5 9.2/2.5), so they are not independent evidence for ISO 7046; ours (features.py header: 'ISO 7046 actual dk (csk)') equal bd's iso10642 M3 row (6.0/1.7) at M3. Not settled from these tables; needs the standard text or a datasheet. SIZES left alone; a larger dk only widens the countersink cutter. |
| M4 csk_h | 2.7 | 2.2 | pending-standard | bd's iso7046 rows equal its iso2009 rows (M3 5.6/1.65, M4 7.5/2.2, M5 9.2/2.5), so they are not independent evidence for ISO 7046; ours (features.py header: 'ISO 7046 actual dk (csk)') equal bd's iso10642 M3 row (6.0/1.7) at M3. Not settled from these tables; needs the standard text or a datasheet. SIZES left alone; a larger dk only widens the countersink cutter. |
| M5 csk_d | 9.3 | 9.2 | pending-standard | bd's iso7046 rows equal its iso2009 rows (M3 5.6/1.65, M4 7.5/2.2, M5 9.2/2.5), so they are not independent evidence for ISO 7046; ours (features.py header: 'ISO 7046 actual dk (csk)') equal bd's iso10642 M3 row (6.0/1.7) at M3. Not settled from these tables; needs the standard text or a datasheet. SIZES left alone; a larger dk only widens the countersink cutter. |
| M5 csk_h | 2.7 | 2.5 | pending-standard | bd's iso7046 rows equal its iso2009 rows (M3 5.6/1.65, M4 7.5/2.2, M5 9.2/2.5), so they are not independent evidence for ISO 7046; ours (features.py header: 'ISO 7046 actual dk (csk)') equal bd's iso10642 M3 row (6.0/1.7) at M3. Not settled from these tables; needs the standard text or a datasheet. SIZES left alone; a larger dk only widens the countersink cutter. |
| M4 insert_wall | 1.6 (axial only) | 2.1 | pending-coupon | bd material_thickness for the Ruthex / CNC Kitchen M4x8.1 insert is 2.1 mm around the insert; our min_wall 1.6 is only applied along the axis, no radial wall is enforced for inserts. Vendor guidance favours theirs; follow-up: a radial-wall check in cadcheck sized from a coupon. |
| M5 insert_wall | 1.6 (axial only) | 2.6 | pending-coupon | As M4: vendor material_thickness 2.6 mm for M5x9.5 against 1.6 axial-only. Same follow-up. |
| M3 stock_length 18 | 18 | not a nominal length of ISO 4762/7046/14583 | ours | Assumed, not sourced: 18 and 22 mm are not in the ISO preferred-length lists, and no vendor listing was checked for this PR. cadcheck's list is the project's stock list and a project checks.json can override it. No dimensional conflict. |
| M3 stock_length 22 | 22 | not a nominal length of ISO 4762/7046/14583 | ours | Assumed, not sourced: 18 and 22 mm are not in the ISO preferred-length lists, and no vendor listing was checked for this PR. cadcheck's list is the project's stock list and a project checks.json can override it. No dimensional conflict. |
| M4 stock_length 18 | 18 | not a nominal length of ISO 4762/7046/14583 | ours | Assumed, not sourced: 18 and 22 mm are not in the ISO preferred-length lists, and no vendor listing was checked for this PR. cadcheck's list is the project's stock list and a project checks.json can override it. No dimensional conflict. |

Matches (no row above): nut AF and height (ISO 4032), clearance Normal (ISO 273 medium), ISO 14583 pan dk and k for
M2, M2.5, M4, M5, cap head k, and the M3, M4, M5 self-tap pilots.
Not compared (no bd_warehouse counterpart): `tap_d` (PLA machine-screw tap), `trap_af`, `counterbore_d`, fits.
