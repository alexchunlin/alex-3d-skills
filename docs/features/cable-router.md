# Cable router (`cadlib/route.py`, `cad q ... route`)

Measured 2026-10-25 on copies under `/tmp/alex3d-cr-*`. Blender 5.1.2, whose Python has numpy 2.3.4 and no scipy,
networkx, trimesh or manifold3d. All runs used nice 10 alongside the live CAD loop.

## Why

- Every v1 attempt had a cable review issue: A1-F12 (routes), A2-F8 (bare run) and A3-F7 (visible in a notch).
- On the attempt-3 blend, cadcheck gives 12 "cable ... overlap ... (route through solid?)" warns.
- v2 still hand-types coordinates: `mm-launch-hw/v2/blender/parts/base.py:332 build_cables`, like v1's
  `blender/build_assembly.py:2244`.

## What it does

`route(start, end, r, via=[...])` returns points for `asm.cable`, so cadcheck's cable checks apply unchanged.

1. **Grid.** Cells of 2 mm cover the leg's endpoints plus a 20 mm margin. A cell is blocked when a surface of a
   Printed, Purchased or Fastener object is closer than r + clearance (BVH `find_nearest`), or when the cell is inside
   a solid. Inside means column ray parity per object, or the nearest face pointing away. Solids on another body are
   swept over the joints in between, so the route clears them at every pose.
2. **Search.** A* over 26 neighbours. Cost per mm:
   - 1 near a wall or in a declared `prefer` box;
   - 1.5 in open space;
   - +8 where the cell is visible from outside (cadcheck's viewer-direction rule, one sample per 2x2x2 block);
   - plus 3 mm per radian of turn.

   An endpoint inside a part, such as a connector pin in a header block, gets a straight stub to the nearest free
   cell. The stub may not go deeper into the solid than the endpoint already is. Only when that finds nothing does
   it allow any stub, and the result reports it.
3. **Vias.** A via is a point, or `{"at", "dir", "len"}` for a straight run through a bore or slot. Adding
   `"joint"` puts the legs after it on another body. The result then has one piece per body, plus a `slack` row:
   the path length at each limit of the joint.
4. **Smoothing.**
   1. Line-of-sight shortcuts with exact clearance; a shortcut never crosses costlier cells than the A* path used.
   2. Merge the short staircase segments A* leaves at a turn.
   3. Fillet each corner with `bend_r` (default 5 r). Where an arc would lose clearance, push the corner outward;
      if that fails, shrink the radius. The output is straight runs plus arcs, so `bend_r_min` is the curve's real
      minimum radius.
5. **Report.** The JSON gives length, exact min clearance (and where), stubs with their clearance, the radius per
   corner, centre-line visible length, slack, per-leg grid size and timings.

## Prove it: A3 blend (`examples/mm-launcher-a3`, the blend R3 reviewed)

```
cad q mm_launcher_a3.blend route CAB_12v_ctrl,CAB_uart,CAB_12v_mg,CAB_bus_ctrl --config checks.json --save rerouted_base.blend
cad q rerouted_base.blend route CAB_encoder_tilt --via "-80,4.1,224.9@1,0,0:30" --clearance 0.3 --cell 1 --margin 10 --config checks.json --save rerouted.blend
cad check {mm_launcher_a3,rerouted}.blend checks.json
```

All five cables use the existing objects' own endpoints. Overlap is cadcheck's intersection volume
(`inter_volume`) against every solid and fastener at home, and cadcheck itself reports the same numbers.

| Cable | r | Hand mm | Routed mm | Overlap before, mm³ | Overlap after, mm³ | Min clearance | Bend radius (target) | Route time |
|---|---|---|---|---|---|---|---|---|
| CAB_12v_ctrl | 1.6 | 180.4 | 202.9 | 38.0 (controller) | 20.2, both end stubs | 1.16 | 6.4 (8.0) | 3.8 s |
| CAB_uart | 1.2 | 243.8 | 185.0 | 113.4 (buck 74.1, MotorGo 16.3, controller 15.1, floor 7.9) | 27.9, both end stubs | 1.08 | 6.0 (6.0) | 11.8 s |
| CAB_12v_mg | 1.6 | 69.0 | 71.4 | 1.7 (buck) | **0** | 1.57 | 8.0 (8.0) | 2.2 s |
| CAB_bus_ctrl | 1.4 | 102.0 | 109.0 | 0.7 (controller) | **0** | 2.76 | 7.0 (7.0) | 3.1 s |
| CAB_encoder_tilt | 1.3 | 93.9 | 94.2 | 11.8 (nacelle) | **0** | 0.30 (asked 0.3) | 3.8 (6.5) | 2.4 s |
| **Total** | | 689.1 | 662.5 | **165.6** | **48.1**, all at endpoints | | | 23 s (28 s wall, 2 loads + 2 saves) |

Visible length is 0 mm before and after for all five: the router's centre-line estimate, and no cadcheck exposure
warn on any of them. These cables run inside the base and the nacelle.

**The 48.1 mm³ left over is at the endpoints, not along the routes.**
- `CAB_12v_ctrl` starts 1.0 mm inside the buck's face (the hand endpoint itself overlaps). It ends inside the
  controller's header block, which it must enter.
- `CAB_uart` starts 0.7 mm inside the MotorGo envelope. It ends in a pocket under the controller board that a
  1.2 mm cable can't leave without cutting a solid (the stub's min clearance is -3.0 mm). The hand route cut the
  board there as well.

Making these zero needs a connector declaration or endpoints that sit on the part's surface. That is a follow-up,
listed below.

**cadcheck before and after** (`/tmp/alex3d-cr-a3/cadcheck_{before,after}.json`, same `checks.json`):
- Fails: 2 → 2, the same two R3-confirmed fails.
- Warns: 65 → 60.
- Cable overlap warns: 12 → 7. For the five re-routed cables, 8 warns totalling 165.6 mm³ became 3 totalling
  48.1 mm³.
- No new finding of any other kind.
- Runtime: 81.9 and 80.9 s.

**Tight duct.** The encoder runs up a nacelle duct and through the tilt trunnion bore, which has a radius of about
10 mm at x -60 to -100. With the default 1.0 mm clearance on a 2 mm grid there is no path. With `--cell 1
--clearance 0.3` and one bore via there is: 94.2 mm against the hand route's 93.9, at 0.30 mm clearance. Without
the via, the router went around the outside, with 61.7 mm visible and more overlap. That is why bores are vias.

**Slack across a joint (A3 tilt).** The same encoder cable, continued across the tilt joint onto the pan body
(`--to -109,0,192`, second via `>PIV_pan`):

| Via where the cable leaves the tilt body | Length at tilt 0 | Length at tilt 45 | Slack |
|---|---|---|---|
| (-102, 0, 222), on the tilt axis | 120.6 | 120.6 | 0.0 mm |
| (-102, 0, 230), 8 mm off the axis | 129.3 | 135.5 | 6.1 mm |

The off-axis value is 2 x 8 x sin 22.5° = 6.1 mm, the chord the via swings through.

**Render:** `/tmp/alex3d-cr-a3/base_after.png` (and `base_before.png`) is a section at z 30 seen from above.
`CAB_12v_ctrl` (red) runs along the floor from the buck and climbs over the controller to its header.

## Finding: the "1332 mm³" was a cadcheck artefact

FINDINGS carried "CAB_12v_ctrl runs 1332 mm³ through BUY_servo_controller" from A1 to A3. The hand-made tube is
not manifold: the curve bevel's cap rings are separate copies of the end rings. Without a manifold pair, cadcheck
falls back to the EXACT solver. With the controller as the base and the cable as the cutter, EXACT returns the
cutter's whole volume: 1331.9 mm³, against the cable's own 1332.0. In the other operand order it returns 38.0 mm³,
the last 6 mm of cable inside the header block.

Fixes on this branch:
- `inter_volume` now runs EXACT in both orders and keeps the smaller volume. On A3, interference took 41.7 s
  against 47.3 s before, which is within noise from the live loop, and the counts didn't change.
- `asm.tube_mesh` welds the cap rings, so cadlib cables are closed solids.

## Synthetic test (`examples/cable-router/build.py`, `tools/verify.d/cable_router.sh`)

The scene is a tray with a block, a wall with one floor slot, and a turntable (`PIV_turn`, ±90°) with a centre bore
and an off-centre post.

- `CAB_slot` goes from (-50, 0, 3) to (40, -20, 3). The straight line runs through the block and the wall.
  - Routed length 117.6 mm (straight line 92.2).
  - Min clearance 1.5 mm (asked 1.0). `cad q dist` to the block is at least 0.95 mm.
  - Passes the slot via exactly. Bend radius 5.3 mm.
- `CAB_bore` goes from the tray up through the bore onto the deck.
  - Two pieces (static, `PIV_turn`).
  - Slack 0.0 mm over ±90°, because the via is on the axis.
  - It clears the post at every pose, because the post is swept.
- cadcheck `--only interference` gives no cable findings.

The test also re-routes A3 `CAB_12v_mg` and asserts 0 mm³ overlap (hand route: 1.7). It takes about 15 s.

## Why not the existing code

| Option | Measured | Result |
|---|---|---|
| Hand-typed waypoints (v1 `build_assembly.py:2244`, v2 `base.py:332`) | 5 A3 cables: 165.6 mm³ in solids over 8 cadcheck warns; issues in A1, A2 and A3 | the status quo this replaces |
| cadcheck alone (detect, then hand-edit) | it flags overlaps and exposure but proposes no route; its biggest number (1332 mm³) was an artefact, now fixed | kept, and run on the router's output |
| Blender Geometry Nodes "Shortest Edge Paths" (C++ Dijkstra, in the dependency) | same `CAB_12v_ctrl` grid: 169k cells, 98.6k free, 1.13M lattice edges. Mesh build 0.16 s + evaluation 0.07 s, against 0.98 s for A*. Path cost 243.8 against 240.4 | 4x faster search, but no turn cost (Dijkstra keeps no direction state) and no per-entry stub cost, plus a 1.1M-edge mesh round trip. Search is 3-21% of a route (0.06-0.79 s); the grid and exposure sampling are the rest. It could become the search engine later without changing the API |
| `bpy.ops.mesh.shortest_path_select` | read, not run: an edit-mode operator over edge length or topology | no cost field, so no wall or exposure preference |
| scipy `csgraph` / networkx | not in Blender's Python (checked); no installs allowed | n/a |
| `asm.cable` | kept: the router only produces its `pts` | changed only to store `path` and weld the caps |

The smallest change that closes the gap: there is no config of the existing code that produces a route, so the new
module only adds the search and smoothing. It reuses cadcheck's exposure rule, joint and pose conventions, and
`asm.cable`.

## Limits and follow-ups

- Cables are routed one at a time and don't see each other; bundles can overlap (cadcheck ignores cable pairs).
- Tight ducts need `cell=1`, about 8x the cells. Exposure sampling is the slowest stage (0.4-4.3 s per leg).
- Turn cost uses the parent cell's direction, which is approximate. Slack treats the pieces as rigid with a straight
  bridge at the via: no twist and no bend.
- Endpoints inside parts stay as stub overlaps. A `connectors` declaration (an allow scoped to the endpoint) would
  silence these warns honestly.
- Not yet re-routed:
  - `CAB_bus_feeder`, `CAB_launcher_bundle_*`, `CAB_phase_tilt_*`. These cross the pan or tilt joints and need
    vias at the hub and trunnion bores.
  - v2's `build_cables`.
