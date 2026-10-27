# cadlib.route: cable routing

Read this when you route a cable. `from cadlib import route as RT`. It routes around every solid in Printed,
Purchased and Fasteners at home. Parts on another body are swept over every joint in between: revolute joints in
degrees, prismatic (slide) joints in mm, both posed exactly as cadcheck poses them.

## Calls

| Call | Notes |
|---|---|
| `RT.cable(name, start, end, r, color, via=[], joint=None, lead_len=None, **opt)` | route, then `asm.cable`. Returns `(objects, result)`: one object per body (`name`, `name_1`, ...), each on its piece's joint |
| `RT.route(start, end, r, via=[], joint=None, **opt)` | the result dict only. Use `res["pts"]` with `asm.cable` only when `len(res["pieces"]) == 1`; a split route needs one object per piece on its joint, which is what `RT.cable` does |
| `cad q model.blend route CAB_x[,CAB_y] [--via ...] [--clearance C] [--cell H] [--save out.blend] [--json out.json]` | re-routes existing cables between their own endpoints and compares them with the hand route. Exits 1 when a route has a violation |

`joint` is the body of the first leg: the joint you would give `asm.cable`.

## Vias

- `(x, y, z)`: a point the cable passes.
- `{"at": p, "dir": d, "len": L}`: a straight run of length L through p, for a bore or a slot. A slot or bore narrower
  than 2 (r + clearance) + cell has no free grid cell inside it, so it needs a via with `"dir"`. A point via there
  stubs to the nearest free cell at an angle and cuts the slot's corner. The guard reports that cut as a violation.
- Add `"joint": "PIV_x"` (or `"static"`) to either form when the cable changes body at the via. The route is then
  split there: one piece per body.

## Crossing a joint

Cross along the joint's axis: give the crossing via `"dir"` equal to the axis, or model a service loop. A cable that
crosses a hinge across its axis folds by the hinge angle at the via. The PR #3 review's lid hinge folded 0, 55 and
109° at 0, 55 and 110°. The result's `crossings` row gives the turn at each joint limit. Above `fold_warn_deg` (30°)
the router warns, unless the via's `"dir"` runs along the axis.

`slack` is the path length at each joint limit, with the via as a straight bridge. It is 0 at an on-axis via by
design. It says nothing about the fold: read `crossings` for that.

A split route is one conductor in several objects. Give the pieces one `cable_chains` row with the purchased lead.
`RT.cable` returns it as `res["cable_chain"]` and prints it, and `cad q route` prints `cable_chain`. `lead_len` goes
on the object only when the route is one piece. cadcheck compares each object's own `path_len` with its `lead_len`, so
a whole-run lead on one piece would pass a run that is too long.

## Result

| Key | Meaning |
|---|---|
| `pts`, `pieces` | all points; one `{joint, pts}` per body |
| `length_mm`, `straight_mm` | route length, and the straight line between the ends |
| `min_clearance_mm`, `min_clearance_at` | exact minimum clearance away from the end stubs. None when no solid is within r + clearance + 5 mm. Near a moving part it is measured against the part inflated by its largest move between sampled poses |
| `violations` | `{i, at, clearance_mm}` for every 0.5 mm sample, away from the two ends, that is under the requested clearance. Straight runs and via stubs count. Below 0 means into a solid or its swept path |
| `warnings` | violations, and folds at joint crossings; also printed as `route: WARN ...` |
| `crossings` | `{joint, at, from, to, turn_deg: {limit: deg}, on_axis}` per body change |
| `stubs` | ends (and vias) that leave a solid or the clearance band through a straight stub, with its clearance |
| `bend_r_min`, `bend_r_floor`, `sharp_corners`, `corners` | fillet radii. No arc is under `min_bend_od` x OD, and a corner that can't take one stays sharp for cadcheck's kink test |
| `exposed_mm`, `slack`, `legs`, `time_s` | visible length (cadcheck's rule), slack rows, per-leg grid, sweep and timing stats |

## Options (`**opt`)

`clearance=1.0`, `cell=2.0`, `margin=20`, `bend_r=5*r`, `min_bend_od=0.75` (cadcheck's `cable_min_bend_od`),
`w_open=0.5`, `w_exposed=8`, `w_turn=3`, `prefer=[(lo, hi)]` (groove boxes), `avoid=[(lo, hi)]`, `exposure=True`.

Moving parts:
- `sweep_tol` (default (r + clearance) / 2) is the largest move of a swept part between two sampled poses. Each joint's
  step follows from the reach of the moving side, so that reach x step <= r + clearance.
- `max_joint_poses=96` caps the samples per joint.
- `max_group_poses=1024` thins long chains. The swept parts are inflated by the move the sampling can miss, so a cap
  costs room, never a miss.
- A part behind a continuous joint (a wheel) is swept as its spin envelope, an annulus about the axis.

## When it fails

- **"buried ... in the swept path of PIV_x"**: the end lies where a moving part passes. Move the end, or put the
  cable on that body.
- **"no path"**: use `cell=1` and a smaller `clearance` for a tight duct, or add a via with `"dir"` at the bore. On
  the A3 trunnion duct, `cell=1, clearance=0.3` plus one bore via gave 95 mm against the hand route's 94.
- **Violations**: the result breaks the asked clearance away from its ends. Usually this is a forced straight run
  through a narrow slot, or a point via in a slot. Widen the slot, lower `clearance` on purpose, or give the via a
  `"dir"`.
