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
| `swept_envelope(...)`, `cadlib.blend` | keep-outs for moving parts; organic connectors grown around tubes and parts: `reference/blend.md` (`Tube` clearance is radial) |

## features: print features

`at` is the bearing face of the head or nut. `into` is the direction the shank travels. Each call returns a list of cutters (or adders) for `csg`.

| Call | Notes |
|---|---|
| `screw_hole(at, into, length, kind, head="cap", sink=0, clamp=0, print_up=None)` | `kind`: `selftap` (Ø2.5), `clearance` (Ø3.4), `clamp` (Ø3.4 for `clamp` mm then Ø2.5), `insert` (Ø3.4 then a heat-set pocket). `sink` gives a counterbore depth. `head="csk"` cuts a countersink. `print_up` turns horizontal holes into teardrops. |
| `nut_trap(at, into, depth=None, af=5.7, rot_deg=0, slot_dir=None, slot_len=0)` | hex pocket, optional side-entry slot |
| `boss(at, into, od, height)` | cylinder grown back from `at` (against `into`); union it, then cut the hole |
| `drill_to_fit_boss(at, into, od=7, height=6)` | returns `(add, cut)`: solid boss with a centre-punch dimple only |
| `slot(at, into, along, length, width=3.4, depth=10)` | adjustment slot |
| `horn_recess(at, into, disc_d=20, depth=1, bolt_circle_d=14, n_holes=8, centre_hole_d=6.5)` | servo horn interface with a centre-screw access hole |
| `pcb_pocket(at, into, w, h, depth, clear=0.4)` | board locating pocket |
| `bore(name, c, r_shaft, w0, w1, axis, fit="running")` | journal bore with the fit's clearance |
| `RULES` | all PLA and fastener numbers; change them here, not inline |

## asm: assembly

| Call | Notes |
|---|---|
| `new_scene(params=dict)` | mm units, clears registries; `params` go into the manifest |
| `joint("PIV_x", loc, axis, lo, hi, parent=None, home=0, step=None, continuous=False, couple_to=None, couple_ratio=1, prismatic=False)` | create joints before parts that hang under them; `prismatic=True` slides along +axis, values in mm (gates, drawers) |
| `set_pose(PIV_pan=30, PIV_tilt=45)` | unlisted joints go home; coupled joints follow |
| `part(ob, name, kind, color, joint=None, **info)` | `PRT` needs `stl, print_rot, orient, supports` (plus `infill`); `BUY` should give `mass_g, src`. Colours: `"pla_a"`, `"pla_b"`, `"buy"`, `"buy_metal"`, `"pcb"`, or an RGBA tuple. |
| `R_ID, R_FLIP, R_PX_DOWN, R_NX_DOWN, R_PY_DOWN, R_NY_DOWN` | common `print_rot` values |
| `fastener(name, at, into, length, spec="M3_cap", joint=None, host=None, step=None)` | `spec`: `M3_cap`, `M3_pan`, `M3_csk`, `M3_selftap_pan`, `M3_hex`, `M2_pan`, `M2.5_cap`, `M2.5_pan`; use stocked lengths (cadcheck warns otherwise) |
| `nut(name, at, into, joint=None, af=None, h=None, step=None)` | hex nut, bearing face at `at`; cadcheck checks the bolt on its axis reaches through it |
| `cable(name, pts, r, color, joint=None, lead_len=None)` | stores `path_len` and both ends; cadcheck compares it with `lead_len`, and flags ends that meet another cable with no connector (declare `cable_chains`) |
| `write_manifest(path)` | parts, joints, fasteners, cables, features, params |

### A screw, its hole and its nut (one `at`, one `into`)

```python
at, into = (40, 0, 30), (0, 0, -1)                   # head bears on z=30, shank goes down
cover = G.csg(cover, sub=F.screw_hole(at, into, 12, kind="clamp", clamp=3, head="cap", sink=2.5))
A.fastener("FST_cover_0", at, into, 12, spec="M3_cap", joint="PIV_tilt", host="PRT_body", step="cover")
A.nut("FST_cover_nut_0", (40, 0, 30 - 10), into, joint="PIV_tilt")    # optional: bearing face 10 mm down the shank
```

`length` is the shank under the head, measured from `at` along `into`. `clamp` is the clearance-hole depth in the
clamped part. `sink` puts `at` that far below the outer face, and the counterbore is cut back out from it. `fastener`
specs: `M3_cap`, `M3_pan`, `M3_csk`, `M3_selftap_pan`, `M3_hex`, `M2_pan`, `M2.5_cap`, `M2.5_pan`. `screw_hole` cuts M3 sizes
only; for M2.5, cut `G.cyl` holes with `RULES`-style clearances (2.7 clear, 2.1 pilot).

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
