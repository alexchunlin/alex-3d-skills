# blend and swept_envelope: grown connectors and keep-outs

Read this only when you use them. Measurements: `<repo>/docs/features/blend-bracket.md`.

```python
from cadlib import blend as B, geom as G      # blend loads numpy + openvdb on first use only
```

**When it's worth it:** a node or bracket that holds several tubes or parts at odd angles and should look like one
part, not a kit of boxes (v1 aesthetics stayed at 5-6, R2 #10, R3 #4). No v2 issue needed it, and it doesn't save
screws. For a box-shaped mount, `geom` and `features` are simpler.

## Holds, members, grow

| Call | Notes |
|---|---|
| `Tube(a, b, d, wall=4, clearance=0.2, stop=None, edge=1, lead_in=0.5, print_up=None, name=None)` | sleeve from a to b (b is the mouth) around a tube of diameter d. **`clearance` is radial**: 0.2 radial = 0.4 diametral = `F.RULES["fit_loose"]`. `stop`: the socket floor's distance from a (None: through bore). `print_up` (world print +Z): a bore within 60 deg of horizontal becomes a teardrop, as in `F.screw_hole`. |
| `Block(M, size, wall=2.4, clearance=0.2, grip=None, open=("+z",), name=None)` | box-shaped part (servo body, board, battery) centred on frame M; clearance per side. `grip` limits the cradle in local coordinates; the cutter runs out through the `open` faces. |
| `rod(a, b, r, edge)`, `capsule(a, b, r)`, `sphere(c, r)`, `rbox(M, size, r)`, `mesh_field(ob)` | extra members: plates, posts, fins, struts |
| `grow(name, holds, fillet=5, extra=[], keepout=[], keepout_clear=0.5, clip=None, holes=[], voxel=0.5)` | returns `(ob, report)`. About 2 s, under 45k triangles. `holes` takes exact cutters such as `F.screw_hole(...)` lists. `clip` is a **world-axis box** intersected exactly (flat bed faces); for a tilted cut, pass a rotated `G.box` in `holes`. Over `max_cells` (40M cells, about 1.7 GB) it raises `GridTooLarge` before allocating, naming the smallest voxel that fits. |
| `measure(ob, holds)` | fit clearance and wall per hold, by rays on the finished mesh. Unnamed holds are numbered `tube0`, `tube1`, `block0` in order; two holds with the same name raise. |
| `best_orientation(ob, candidates=None)` | ranks print orientations by `printcheck` (fails, then warns, then flagged sloped-overhang area, then bed contact), each with its verdict. Default candidates: each tube rim, each clip face, the 6 world axes (`orientation_candidates(ob)`; add your own). Candidates under 50 mm2 on the bed rank last. Use `r[0]["print_rot"]` and `r[0]["label"]` in `A.part`. 5-12 s per candidate. |

- **Grown sockets don't retain the tube.** The fit is a 0.4 mm diametral slip. Put a screw through the sleeve
  (`holes=F.screw_hole(...)`) or glue it.
- **Orientation:** take `best_orientation`'s pick, then run `cad printcheck` on the exported STL; printcheck is the
  authority for `supports`. Its face pass flags the sleeves' sloped undersides that the layer check alone passed (the
  review's 4-way node on tube1's rim: three regions 8.9-10.0 mm past 45 deg); `cad printcheck --where` says where.

## swept_envelope: keep-outs for moving parts

`G.swept_envelope(obs, pivot, axis=None, lo=None, hi=None, tol=0.25, voxel=0.5, prismatic=False)`
- `pivot`: a `PIV_` empty, giving its axis, range and kind; or a point plus `axis`, with `lo`/`hi` relative to now.
- Kinds:
  - prismatic joints slide (mm);
  - continuous joints with no `lo`/`hi` sweep 0..360.
- One closed mesh holds every pose. It is oversize by about `tol + voxel` (0.75 mm at the defaults).
- A coarser voxel makes it fatter, never leaky. Don't tighten `tol` to win the margin back.
- Keep it in the scratch collection, never `Printed`/`Purchased`: at 230k-925k triangles every cadcheck pass would pay
  for it.
- Pass it to `grow(keepout=[env])` or subtract it with `csg`.
- `method="union"` is exact at the poses but pokes out between them.

## Threads

OpenVDB uses every core (400-1100% CPU), even at nice 10. On a shared machine, cap it with Blender's `-t N`. For
example, `nice -n 10 blender -b -t 4 --python build.py`. `cad build` doesn't pass `-t`.
