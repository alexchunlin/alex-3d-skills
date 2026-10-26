# cadlib API

```python
import sys; sys.path.insert(0, "<skill>/scripts")
from cadlib import geom as G, features as F, asm as A, export as E, render as R
```

Units are mm and degrees. 2D profiles are lists of `(u, v)`. Extrusion `axis` 'X' maps (u, v, w) to (y, z, x),
'Y' maps to (x, z, y) and 'Z' maps to (x, y, z). Every solid function returns a new mesh object in the scratch collection.

## geom: shapes and booleans

| Call | Notes |
|---|---|
| `circle(c, r, n=None)`, `arc(c, r, a0, a1)`, `hexagon(c, af)`, `rrect(x0, x1, y0, y1, r)` | profiles; `n` defaults to ~0.4 mm chord |
| `hull2d(pts)`, `hull_circles([(c, r), ...])`, `offset_convex(poly, d)` | rounded plates, bosses joined to walls |
| `teardrop(c, r, up=(0, 1))` | horizontal hole printable without support; `up` = print +Z in the profile plane |
| `gear_poly(m, z, c, backlash=0.15, phase=0)` | involute spur gear outline |
| `prism(name, poly, w0, w1, axis)`, `loft(name, p0, p1, w0, w1, axis)` | extrusions; loft rings need equal point counts |
| `cyl(name, c, r, w0, w1, axis)`, `cone(name, c, r0, r1, w0, w1, axis)`, `box(name, x0, x1, y0, y1, z0, z1)` | |
| `revolve(name, [(r, z), ...], center, n=96, a0=0, a1=None)` | about Z; partial when `a1` is given |
| `csg(base, add=[], sub=[], inter=[])` | Manifold solver, applies the result and deletes the tools; raises `CSGError` if the result isn't a closed solid |
| `bevel(ob, w, seg=1, angle=40)` | edge break; apply before booleans that cut fine detail |
| `xform(ob, M4)`, `frame(origin, u, v, w)` | bake a transform; build a placement matrix |
| `join(name, obs)` | merge shells without booleans (purchased placeholders only) |
| `import_stl(path, name)` | e.g. `reference/mg_axis.stl` as a placeholder |

## features: print features

`at` is the bearing face of the head or nut. `into` is the direction the shank travels. Each call returns a list of cutters (or adders) for `csg`.

| Call | Notes |
|---|---|
| `fastener_joint(name, size, at, into, parts, style="selftap", head="cap", sink=0, cuts=None, ...)` | **Use this for every screw.** Measures the stack of `parts` (uncut solids named with their final `PRT_`/`BUY_` names) along the axis, picks the shortest stock length that meets the rule, cuts each part and places the FST plus nut or insert. `style`: `selftap`, `nut` (trap in the last part; `trap=False` for a nut on its face), `insert`, `tapped` (purchased part, `depth=` of its tapped hole). Returns `{part name: [cutters]}`; pass `cuts=` to accumulate. Raises `FastenerError` for a reversed screw, a buried head, too little thread, or no stock length. M3 to M4 is the `size` argument. |
| `screw_hole(at, into, length, kind, head="cap", sink=0, clamp=0, print_up=None, size="M3")` | `kind`: `selftap` (Ø2.5), `clearance` (Ø3.4), `clamp` (Ø3.4 for `clamp` mm then Ø2.5), `tap` (Ø3.4 then the PLA-tap hole), `insert` (Ø3.4, a heat-set pocket, then Ø3.4 past it). Diameters are M3; `size` picks another row of `SIZES`. `sink` gives a counterbore depth. `head="csk"` cuts a countersink. `print_up` turns horizontal holes into teardrops. |
| `nut_trap(at, into, depth=None, af=5.7, rot_deg=0, slot_dir=None, slot_len=0, size="M3")` | hex pocket, optional side-entry slot |
| `boss(at, into, od, height)` | cylinder grown back from `at` (against `into`); union it, then cut the hole |
| `drill_to_fit_boss(at, into, od=7, height=6)` | returns `(add, cut)`: solid boss with a centre-punch dimple only |
| `slot(at, into, along, length, width=3.4, depth=10)` | adjustment slot |
| `horn_recess(at, into, disc_d=20, depth=1, bolt_circle_d=14, n_holes=8, centre_hole_d=6.5)` | servo horn interface with a centre-screw access hole |
| `pcb_pocket(at, into, w, h, depth, clear=0.4)` | board locating pocket |
| `bore(name, c, r_shaft, w0, w1, axis, fit="running")` | journal bore with the fit's clearance |
| `RULES` | all PLA and fastener numbers; change them here, not inline |
| `SIZES`, `size_rules(size)` | M2-M5: pitch, clearance, pilot, tap, cap/pan/csk head d and h, nut AF and h, trap AF, insert hole, min engagement. The M3 row reads the `m3_*` entries of `RULES`. `size_rules` adds the stock lengths from cadcheck's default `fasteners.stock_lengths` |

## asm: assembly

| Call | Notes |
|---|---|
| `new_scene(params=dict)` | mm units, clears registries; `params` go into the manifest |
| `joint("PIV_x", loc, axis, lo, hi, parent=None, home=0, step=None, continuous=False, couple_to=None, couple_ratio=1, prismatic=False)` | create joints before parts that hang under them; `prismatic=True` slides along +axis, values in mm (gates, drawers) |
| `set_pose(PIV_pan=30, PIV_tilt=45)` | unlisted joints go home; coupled joints follow |
| `part(ob, name, kind, color, joint=None, **info)` | `PRT` needs `stl, print_rot, orient, supports` (plus `infill`); `BUY` should give `mass_g, src`. Colours: `"pla_a"`, `"pla_b"`, `"buy"`, `"buy_metal"`, `"pcb"`, or an RGBA tuple. |
| `R_ID, R_FLIP, R_PX_DOWN, R_NX_DOWN, R_PY_DOWN, R_NY_DOWN` | common `print_rot` values |
| `fastener(name, at, into, length, spec="M3_cap", joint=None, host=None, step=None)` | `spec`: `<size>_cap`, `_pan`, `_csk` for every size in `SIZES` (M2 to M5), plus `M3_selftap_pan` and `M3_hex`; use stocked lengths (cadcheck warns otherwise) |
| `nut(name, at, into, joint=None, af=None, h=None, step=None, size="M3")` | hex nut, bearing face at `at`; cadcheck checks the bolt on its axis reaches through it |
| `cable(name, pts, r, color, joint=None, lead_len=None)` | stores `path_len` and both ends; cadcheck compares it with `lead_len`, and flags ends that meet another cable with no connector (declare `cable_chains`) |
| `write_manifest(path)` | parts, joints, fasteners, cables, features, params |

### A screw, its hole and its nut (one `at`, one `into`)

`fastener_joint` does all three in one call and picks the length. The hand-placed form below is what it calls; use it
for a screw the joint can't express.

```python
at, into = (40, 0, 30), (0, 0, -1)                   # head bears on z=30, shank goes down
cover = G.csg(cover, sub=F.screw_hole(at, into, 12, kind="clamp", clamp=3, head="cap", sink=2.5))
A.fastener("FST_cover_0", at, into, 12, spec="M3_cap", joint="PIV_tilt", host="PRT_body", step="cover")
A.nut("FST_cover_nut_0", (40, 0, 30 - 10), into, joint="PIV_tilt")    # optional: bearing face 10 mm down the shank
```

`length` is the shank under the head, measured from `at` along `into`. `clamp` is the clearance-hole depth in the
clamped part. `sink` puts `at` that far below the outer face, and the counterbore is cut back out from it. `fastener`
specs: `<size>_cap`, `_pan`, `_csk` for M2, M2.5, M3, M4 and M5, plus `M3_selftap_pan` and `M3_hex`. `screw_hole` and
`nut_trap` cut M3 unless given `size=` (a row of `SIZES`: M2.5 is 2.9 clear, 2.0 pilot).

## cad q (one-shot measurements)

`cad q` with no arguments prints every command. The ones agents use most:

```
cad q model.blend dist PRT_a PRT_b [--pose PIV_tilt=45]            # nearest distance, negative = overlap mm3
cad q model.blend sweep PRT_a PRT_b PIV_tilt -3 48 2.5             # the same over a joint
cad q model.blend ray 19.5,-2.33,111.27 0,-0.316,0.949 [--frame PIV_tilt --pose PIV_tilt=45]   # first hit
cad q model.blend inside 10,18,265                                  # which solids contain the point
```

`--frame` gives the ray in that joint's home coordinates and moves it with the joint. Measurements that back a BOM
claim belong in checks.json (`distances`, `sightlines`, `payload_fit`, `slide_out`), so every run re-proves them.

## cad rows, cad bom (plain python3, no Blender)

```
cad rows cadcheck.json v2-A2              # every row whose line matches the regex, one line each, with its why
cad rows cadcheck.json --check drop,slide # rows of those checks
cad rows cadcheck.json --findings         # fails and warns, with (accepted) marks
cad rows manifest.json FST_nip            # parts (fasteners are kind FST), joints, params
cad bom ../BOM_AND_ASSEMBLY.md manifest.json   # BOM fastener rows vs the model; exit 1 on a mismatch
```

## cad q section (the command line, not the function)

```
cad q model.blend section AXIS VAL OUT.png CAMX,CAMY,CAMZ ORTHO [--keep -|+] [--scope PIV_tilt,static] [--pose PIV_tilt=45] [--lentil X,Y,Z:NX,NY,NZ]
cad q model.blend section x 21 /tmp/sec_x21.png 400,0,200 320       # cut at x=21, keep x<21, camera on +X, 320 mm wide
```

AXIS is x, y or z (either case). The camera looks along AXIS toward VAL, from CAM. ORTHO is the view width in mm.
Four v2 A1 agents read cadq.py to get this right.

## export and render

| Call | Notes |
|---|---|
| `E.export_stls(dir)` | one STL per unique `stl` name, in print orientation; deletes stale STLs; returns `{name: qty}` |
| `E.save_blend(path)` | removes scratch objects, goes to the home pose, saves, deletes the `.blend1` backup |
| `R.view_set(outdir, poses={name: {joint: deg}})` | iso, iso_front_left, front, side, top, rear, plus one iso per pose. 960 px by default; `CAD_RENDER_FINAL=1` gives 1800 px. |
| `R.section(outdir, fname, axis, val, cam_loc, cam_tgt, ortho, keep_side="-", scope={joints})` | cut faces in yellow; closed solids are cut with Manifold |
| `R.exploded(outdir, offsets=None, scale=1)` | auto radial explode when `offsets` is None |
| `R.contact_sheet(stl_dir, out_png)` | fresh process only (it resets the scene); `cad sheet` does that |
| `R.marker_lentil(name, center, normal, d=13, t=7)`, `R.marker_rod(name, a, b)` | payload and tangent markers for sections |
| `CAD_RENDER_BUDGET` (env, default 40) | renders per process before `shot` refuses |
