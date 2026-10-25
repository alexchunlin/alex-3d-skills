# Feature: grown connectors (`cadlib.blend`) and swept envelopes (`geom.swept_envelope`)

Branch `feat/blend-bracket`, measured 2026-10-25 in Blender 5.1.2 at `nice 10`, while the v2 CAD loop shared the CPU.

## Why

- **Form language.** Aesthetics stayed at 5-6 in all three v1 attempts. Each time the critique was "kit of boxes, no
  unifying form language" (R2 #10, R3 #4). FINDINGS lists it as "not a tool problem" because no cadlib call makes
  anything but prisms, revolves and lofts joined by sharp booleans.
- **Keep-outs by hand.** D3 spent a 159 s generation deriving the pod's swept envelope for the shroud cut (FINDINGS
  A3-T2, `D3 0:16:45`). STATUS lists "no cadlib helper for the swept envelope of a moving part" as a known gap.

The user's reference part is a red 6-way tube node: three black tubes on X, Y and Z, joined by a printed connector
with concave fillets between the arms. The goal is "place the parts, then grow a smooth printed part that holds them."

## What was built

| Piece | Where |
|---|---|
| `geom.swept_envelope(obs, pivot, axis, lo, hi, tol=0.25, voxel=0.5)` | `skills/print-cad-blender/scripts/cadlib/geom.py` |
| `blend.Tube`, `blend.Block` (holds), `rod/capsule/sphere/rbox/mesh_field` (members), `blend.grow`, `blend.measure`, `blend.overhang` | `skills/print-cad-blender/scripts/cadlib/blend.py` |
| 6-way node example | `examples/blend-node/build.py` |
| Servo and board bracket with a swept keep-out | `examples/blend-bracket/build.py` |
| Prior-art harnesses | `tools/prior_art/blend_compare.py`, `tools/prior_art/sweep_compare.py` |
| Regression | `tools/verify.d/blend_bracket.sh` (+ `blend_bracket_sweep.py`) |

How `grow` works:
1. Every hold and member is a signed distance field on a numpy grid (float32, 0.5 mm voxels by default).
2. A round union (the n-ary form of hg_sdf `fOpUnionRound`) joins them, with a circular fillet of radius `fillet`.
3. Keep-outs (a mesh such as a swept envelope, via an OpenVDB level set, or a field) are cut with a rounded
   intersection that leaves `keepout_clear`.
4. OpenVDB `convertToPolygons` meshes the field. Collapse decimation brings it to 40k triangles, and a 0.02 mm
   outward bias pays back the chord error.
5. Then everything that must fit is cut exactly with Manifold:
   - each hold's cutter: the held part plus clearance, with facets within 0.01 mm of round;
   - `features.screw_hole` lists and other exact cutters;
   - the keep-out meshes;
   - a clip box for flat bed faces.

So fits are exact, and only the outer skin carries voxel error.

swept_envelope builds one OpenVDB level set from the triangle soup of all poses. Poses are `2 * tol / r_max` apart
and the mesh is taken at `+pad`, where `pad = r_max * step / 2 + voxel / 4`. A point moves at most
`r_max * step / 2` between poses and a distance field is 1-Lipschitz, so every in-between pose is inside by
construction. The cost is about `pad` of oversize.

## Prior art: what exists, and what I measured

**Availability.** Blender 5.1.2's Python has numpy 2.3.4 and `openvdb` 13. It has no skimage, scipy, mcubes, trimesh or
manifold3d (`/tmp/alex3d-bb-probe/pk.py`). External SDF libraries (fogleman/sdf, libfive) would need a pip install
or network access, and this run allows neither, so they were not measured. Option (e) needed no new package: OpenVDB is
both the isosurface extractor and the mesh-to-SDF converter.

### The 6-way node, side by side (`tools/prior_art/blend_compare.py`, `/tmp/alex3d-bb-cmp/blend_compare.json`)

Spec: 20 mm tubes, 0.2 mm clearance, 4 mm wall (arm radius 14.2), arms 40 mm, blind sockets from 14.2 mm, fillet 6,
voxel 0.5. Each approach makes the outer skin. Then the same exact Manifold socket cutters go in, so fit and wall
compare the skins alone.

How to read the columns:
- **arm dev**: max |outer radius - 14.2| on the plain arms, 22-34 mm out. This is the offset-surface accuracy, fair
  to every approach.
- **blend dev**: max |round-union field| at skin vertices, the distance from the intended r=6 filleted surface.
- **fill**: how far the surface stands out of the sharp crease. "Edge" is along (1,1,0), between two arms; "corner"
  is along (1,1,1), where three meet. The intended r=6 values are 2.49 and 3.11.
- **Clearance** is 0.190-0.199 on every row, because the same exact cutters are used. The hull row is the exception
  (0.162), where its bevel cut into a socket.

| Approach (configured as well as I could) | Time s | Triangles | Closed | Min wall | Arm dev | Blend dev | Fill edge / corner | Looks |
|---|---|---|---|---|---|---|---|---|
| Sharp union (every v1 attempt) | 0.01 | 4,296 | yes | 4.00 | 0.00 | 4.39 | 0 / 0 | sharp creases |
| (a) Mesh to Volume, Volume to Mesh, threshold 0.5 | 0.12 | 413,148 | yes | **2.99** | 1.01 | 5.53 | -0.88 / -0.81 | shrunk, creases kept |
| (a) same, threshold 0.1 | 0.12 | 447,708 | yes | 3.80 | 0.19 | 4.26 | 0.29 / 0.11 | creases kept |
| (a) same, threshold 0.1 + Laplacian x20 | 24.1 | 447,672 | yes | 3.81 | 0.19 | 3.95 | 0.37 / 0.32 | creases barely softened |
| (a) Mesh to SDF Grid, **SDF Grid Fillet x40** | 3.9 | 169,704 | yes | 3.99 | 0.01 | 2.24 | 1.97 / 1.52 | real fillets, smaller |
| (a) same, **x70** | 6.9 | 170,496 | yes | 3.99 | 0.02 | 1.56 | 2.57 / 2.00 | real fillets, close to (e) |
| (a) same, x120 | 10.9 | 171,480 | yes | 3.99 | 0.16 | 0.86 | 3.34 / 2.60 | fillets, rims start to round |
| (a) same, x70 at voxel 0.25 | 54.3 | 658,548 | yes | 3.99 | 0.01 | 7.46* | **1.28 / 1.01** | half the fillet of the 0.5 mm run |
| (b) Remesh voxel 0.5 + Laplacian x10 | 6.2 | 168,648 | yes | 3.97 | 0.02 | 3.50 | 0.76 / 0.63 | slight softening |
| (b) same, Laplacian x40 | 9.8 | 168,720 | yes | 3.84 | 0.07 | 2.69 | 1.24 / 1.21 | soft, walls thin |
| (c) Metaballs, 3 capsules, radius calibrated at mid-arm | 0.27 | 122,008 | yes | **1.57** | **8.66** | 6.84 | 5.28 / 6.09 | a blob; arms are not cylinders |
| (d) Convex hull of the union + bevel 6 x6 | 0.01 | 13,362 | **no (2 edges)** | **0.00** | 0.00 | 1.20 | 2.57 / 2.26 | an octahedral lump; the bevel cuts into a socket |
| (e) numpy SDF round union + OpenVDB, full mesh | 1.2 | 168,132 | yes | 4.00 | 0.004 | 0.057 | 2.49 / 3.11 | true r=6 fillets |
| (e) + adaptivity 0.05 | 0.96 | 19,606 | yes | **3.79** | 0.22 | 0.066 | 2.46 / 3.16 | faceted arms |
| **(e) + collapse to 30k + bias 0.02 (shipped default, 40k)** | 1.3 | 33,166 | yes | 4.02 | 0.02 | 0.035 | 2.51 / 3.12 | true r=6 fillets |

\* Max over 60k sampled vertices. The skin looks normal in `cmp_a2_sdf_fillet70_v0.25.png`, and arm dev and wall agree
with the 0.5 mm run, so this is likely one stray vertex. I did not investigate it further.

Renders: `/tmp/alex3d-bb-cmp/compare.png`, a 960 px sheet of seven of the rows, plus `cmp_<row>.png` per row.

What the numbers say:
- **(a) volume, (b) remesh and Laplacian smoothing don't make fillets.** At best they fill 1.24 mm of the 2.49 mm
  crease, and they thin the wall by up to 1 mm (threshold 0.5) or 0.16 mm (x40).
- **(c) metaballs and (d) hull + bevel can't hold a dimension.** Metaballs gave an 8.7 mm arm error and a 1.6 mm wall.
  The hull filled the space between the arms and left 2 non-manifold edges after the socket cut.
- **The real prior art is Blender's SDF Grid Fillet** (geometry nodes, OpenVDB `LevelSetFilter::fillet`). At 70
  iterations it matches (e) on the two-arm crease (2.57 against 2.49) and keeps walls at 3.99. What it cannot do, in
  numbers:
  1. **The fillet size is not a parameter.** It is a curvature flow, so the fill depends on iterations and voxel size
     together. The same 70 iterations fill 2.57 mm at voxel 0.5 but 1.28 mm at voxel 0.25. A designer would calibrate
     iterations per part and per resolution; with (e), `fillet=6` gives 2.51 / 3.12 against the analytic 2.49 / 3.11.
  2. **It is 5x slower at the same size:** 6.9 s against 1.3 s. At voxel 0.25 it takes 54 s.
  3. **The corner comes out different:** 2.00 against 3.11 for a circular r=6 blend. That is a look, not a fault.
  4. **It needs a mesh input.** The holds would have to be booleaned into a mesh first. Grip regions, keep-out
     clearances and rounded cuts would need a node graph built from Python (SDF Grid Boolean, Offset). In (e) each of
     these is one numpy line.
- So the smallest change that closes the gap is not configuration. It is a thin field layer, about 480 lines, over
  two things Blender already ships: OpenVDB for meshing and level sets, and Manifold for the exact cuts.

### Swept envelope, A3 `PRT_nacelle` over `PIV_tilt` -3..46 deg (`tools/prior_art/sweep_compare.py`)

The nacelle has 1,507 vertices and r_max = 90.3 mm. The prior art is what D3 and cadcheck already had: copies of the
part at sampled poses, joined with Manifold (`method="union"`).
- **outside**: the furthest any vertex or edge midpoint of 25 seeded random poses lies outside the envelope (189,975
  points; 3-ray parity vote).
- **oversize**: how far envelope vertices lie from the true swept solid (2,000 vertices against 0.25 deg poses).

| Method | Poses | Time s | Triangles | Closed | Outside: max mm (points) | Oversize max / mean mm |
|---|---|---|---|---|---|---|
| union, 5 deg | 11 | 0.36 | 59,172 | yes | **2.28 (3,570)** | 0.08 / 0.00 |
| union, 2 deg | 26 | 1.41 | 135,438 | yes | **0.91 (658)** | 0.10 / 0.00 |
| union, 1 deg | 50 | 4.68 | 295,558 | yes | **0.46 (372)** | 0.00 / 0.00 |
| **sdf, tol 0.25, voxel 0.5 (default)** | 156 | 2.32 | 460,060 | yes | **0 (0)** | 0.50 / 0.37 |
| sdf, + adaptivity 0.1 | 156 | 1.62 | 29,920 | yes | 0.12 (360) | 0.65 / 0.37 |
| sdf, tol 0.5, voxel 1.0 | 79 | 0.50 | 115,160 | yes | 0 (0) | 1.16 / 0.74 |

- The union of poses pokes out roughly in proportion to the step (2.28, 0.91, 0.46 mm at 5, 2, 1 deg). Corners lead
  the motion, so the error is first order, not the `r * step^2 / 8` of a smooth arc.
- Getting the union under 0.05 mm would take about 0.1 deg steps, around 490 poses.
- **The whole 7-part pod** (nacelle, launcher body and cover, encoder cap, journal plate, nip cover, tilt horn
  adapter; r_max 143 mm): sdf took 9.7 s for 247 poses, with 0 points outside over 7 random poses (`--quick`) and 0.49 / 0.37 mm
  oversize (`/tmp/alex3d-bb-sweep-pod.log`). The Manifold union of 11 poses at 5 deg had not finished after 10 min, and I
  stopped it.
- Adaptivity breaks the containment guarantee (0.12 mm outside on the nacelle), so the default is 0.
- Against A3-T2's 159 s generation, the call takes about 2 s for the nacelle and 10 s for the pod.

## The 6-way node (`examples/blend-node/build.py`, `/tmp/alex3d-bb-node/`)

20 mm tubes, 4 mm wall, 0.2 mm clearance, fillet 6. Each tube line is two stubs in blind sockets that stop 14.2 mm from
the centre. Three solid tubes can't share the centre point, so the core between the sockets is the tube stop, with
4 * sqrt(2) = 5.7 mm between neighbouring sockets.

| Measure | Result |
|---|---|
| `grow` time | 1.7 s (field 1.0, mesh + decimate 0.4, exact cuts 0.3) |
| Triangles | 43,304 (skin 181k decimated to 40k, plus the socket cutters) |
| Manifold | 0 non-manifold edges |
| Fit, 6 sockets x 12 stations x 24 rays (1,728) | 0.190-0.199 mm against 0.2 spec; 0 rays missed |
| Wall, radial from every socket | min 4.016 mm against 4.0 spec |
| `cad check --only parts` | 0 fails, 0 warns. Fits P1S (80 x 80 x 80 mm), wall probe min 4.02 |
| Print orientation | standing on the -Z sleeve rim: 3,018 mm2 overhang + 1,042 mm2 ceilings (20.4 mm bridge), 171 mm2 on the bed, `supports=yes` (the four horizontal sleeves and their sockets). Along the (1,1,1) corner: 3,984 mm2 overhang and 0.4 mm2 on the bed, so no better. |

Render: `/tmp/alex3d-bb-node/node.png`: tubes near-black, connector red.

### Organic setting (`--organic`, review on PR #4)

This setting is closer to the user's reference: one smooth body with large concave faces between short grips. It uses
fillet 15 and sleeves that end 36 mm from the centre (21.8 mm sockets, about 4 mm of plain sleeve showing), against
6 and 40 for the default. I also tried 30/13, which reads as a ball with collars and has only 15.8 mm sockets, and
34/12, which has visibly smaller concave faces.

| Measure | Result |
|---|---|
| `grow` time | 1.8 s (grid 268^3 = 19.2M cells) |
| Triangles | 43,040, closed |
| Fit | 0.190-0.199 mm over 1,296 rays |
| Wall | min 4.015 mm |
| `cad check --only parts` | 0 fails, 0 warns. 72 x 72 x 72 mm, wall probe 4.00 |
| Print orientation | 2,416 mm2 overhang + 738 mm2 ceilings, 98 mm2 on the bed: still `supports=yes` |

Render: `/tmp/alex3d-bb-node/node_organic.png`.

## Size guard (review on PR #4)

`blend.skin`/`grow` evaluate a dense float32 grid. `geom.swept_envelope` builds a sparse OpenVDB level set, but its
peak memory still tracks the swept box. Both now check the cell count first, against `max_cells` (default
`blend.MAX_CELLS` = 40M). Over it, they raise `blend.GridTooLarge` before anything big is allocated.
- The message names the extent, the voxel and the smallest voxel that fits: "341 x 263 x 263 mm at voxel 0.5 mm is
  190M cells (max_cells 40M); the smallest voxel that fits is 0.86 mm".
- I chose an error over auto-coarsening. The voxel sets the skin accuracy and the envelope's pad, so changing it
  silently would change a keep-out's guarantee.
- The swept box is computed pose by pose, so the guard runs before the triangle soup exists.

Peak RSS, measured with `resource.getrusage`, Blender baseline about 225 MB:

| Request | Cells | Peak RSS | Time |
|---|---|---|---|
| node `grow`, voxel 0.5 | 15.3M | 807 MB | 1.5 s |
| node `grow`, voxel 0.37 | 36.9M | 1,632 MB | 3.6 s |
| node `grow`, voxel 0.28 | 84M | refused, "smallest voxel that fits is 0.37" | 0.0 s |
| nacelle `swept_envelope`, voxel 0.5 | 9M (swept box) | 1,199 MB | 2.3 s |
| 7-part pod `swept_envelope`, voxel 0.5 | 34M (swept box) | 2,224 MB | 8.9 s |

- `grow` now folds members into the round union one at a time (two arrays live), so its memory no longer grows with
  the number of members.
- The envelope's memory is driven more by its output triangles (460k and 925k here) than by the box. At the 40M limit
  it is about 2.2 GB.

`tools/verify.d/blend_bracket_guard.py` asks for a 190M-cell `grow` and a 76M-cell sweep. Both must be refused in
under 2 s with peak RSS growing by under 150 MB (measured: 0.0 s, +0.5 MB).

## Place the parts, grow the bracket (`examples/blend-bracket/build.py`, `/tmp/alex3d-bb-bracket/`)

Hiwonder servo and the Hiwonder controller board from `components/placeholders.py`, at fixed poses:
- The servo drops into a `Block` cradle that grips the lowest 18 mm of the body (wall 3, clearance 0.2, open at +Z).
  An exact pocket clears the idler boss.
- The board sits on 4 `rod` posts. The tops are cut flat and exact at the board's underside, with
  `features.screw_hole` self-tap pilots.
- A base plate (clipped exactly at z = 0) and a sloped fin bracing the cradle are blended in with fillet 5.
- The keep-out is `geom.swept_envelope([horn, arm], spline, Z, -90, 90)`: 305 poses, 0.67 s, closed. The arm's finger
  hangs to z = 8 at r = 40-48, through the fin; the fin gets a notch with 1 mm clearance.

| Measure | Result |
|---|---|
| `grow` time | 1.7 s (with the 234k-triangle keep-out level set and its exact cut) |
| Triangles | 31,750, closed |
| Servo fit, 5 axis rays | 0.200 mm on every closed face; wall 3.02 against 3.0 |
| `cad check --only parts` | 0 fails, 0 warns. 162 x 58 x 26 mm, **0 mm2 overhang**, 9,312 mm2 on the bed, `supports=no`, wall probe min 2.26 (post wall around the pilot) |

Renders:
- `/tmp/alex3d-bb-bracket/bracket.png`
- `/tmp/alex3d-bb-bracket/bracket_keepout.png`: a section at y = 0 through the keep-out, showing the arm's swept
  profile over the notched fin and the servo in its cradle.

## Verification

`tools/verify.d/blend_bracket.sh` (about 20 s) asserts:
- The organic node (fillet 15) passes the same fit and wall assertions.
- The size guard refuses oversized `grow` and `swept_envelope` requests before allocating.
- The node is closed; all 6 sockets are within ±0.05 mm of the 0.2 mm fit with no missed rays; the wall is at least
  4.0; it has under 60k triangles.
- `cad check --only parts` on the node: 0 fails, fits P1S, wall probe at least 4.0.
- The swept envelope contains every vertex and edge midpoint of 25 random poses of a sharp-cornered L arm and of the
  A3 nacelle, and both envelopes are closed.
- A negative control: the same check fails the 5 deg pose union (398 of 1,550 points outside), so the check can fail.
- The bracket is closed, the servo fits within 0.05 mm, the wall is at least 3, and it has no overhang.

## Limits and follow-ups

- **Holds are tubes and boxes.** `mesh_field` blends any closed mesh as a member, but a mesh hold has no exact
  clearance cutter: Manifold has no offset. Pass an explicit cutter in `holes` for now.
- **Voxel cost grows as 1 / voxel^3.** The node grid is 248^3 (15M voxels, about 1 s). Parts over about 170 mm cube
  at voxel 0.5 hit the 40M-cell guard. They need a coarser voxel (the error names it), splitting, or sparse
  evaluation near the surface (not done).
- **Printability is reported, not designed in.** The node needs supports in every orientation. There is no overhang-
  aware field term (for example a 45 deg chamfer under horizontal sleeves) yet.
- **The fillet is circular per pair.** At three-way corners the n-ary round union gives a 3.11 mm fill. Changing that
  shape needs a different blend operator; the radius is the only knob.
- **OpenVDB uses every core** (about 400-1100% CPU in these runs) even at nice 10. That is fine for 2 s calls, but a
  heavy sweep competes with a live loop for its duration.
- **Not done:** the slicer view, which is forbidden here (HARVEST_BRIEF "Printer safety"); a print test of the fit;
  and use by a v2 designer.
