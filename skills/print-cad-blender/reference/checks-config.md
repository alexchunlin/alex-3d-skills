# checks.json

Every key is optional. Defaults live in `scripts/cadcheck.py DEFAULTS`. A worked config for a real 102-object assembly is
`<repo>/examples/mm-launcher-a1/checks.json`.

```jsonc
{
  "joints": {"PIV_tilt": {"axis": "X", "lo": 0, "hi": 45, "step": 2.5}},   // only for blends without cadlib joint props
  "couplings": {"PIV_pinion": {"to": "PIV_pan", "ratio": -1}},
  "overtravel_deg": 2.5,          // sweep this far past each limit; hits there are warns ("no margin")
  "max_poses_per_group": 48,      // grids over several joints are thinned to this

  "allow": [                      // designed overlap: the pair is skipped entirely
    {"a": "BUY_servo_*", "b": "BUY_horn_*", "why": "spline inside horn hub"}],
  "fits": [                       // designed running fit across a joint
    {"a": "PRT_yoke_arm_L", "b": "PRT_trunnion_L", "min_clearance": 0.1, "why": "journal, 0.2 diametral"},
    {"a": "PRT_base_shell", "b": "PRT_turntable", "contact": true, "why": "plain thrust bearing"}],
  "moving_min_clearance": 0.5,    // undeclared pairs across a joint: fail below this
  "moving_warn_clearance": 1.0,
  "vol_tol": 0.5,                 // mm3; below this an overlap counts as contact

  "assembly_order": [             // tool access is tested against the parts present at each step
    {"step": "base", "objects": ["PRT_base_*", "FST_floor_*"]},
    {"step": "launcher (bench)", "bench": "launcher", "objects": ["PRT_launcher_*", "FST_motor_*"]},
    {"step": "launcher into yoke", "merge": "launcher", "objects": ["PRT_arm_cap_*"]}],
  "fasteners": {"driver_r": 3.0, "hand_r": 14.0, "max_reach": 60, "max_reach_ext": 150, "min_engagement": 4.0},

  "drop_tests": [{
    "name": "feed_outlet_to_wheel",
    "emit": {"frame": "PIV_pan", "center": [21, 0, 239], "normal": [0, 0, 1], "radius": 6.5, "step": 2},
    "dir": [0, 0, -1],                                   // gravity, world
    "poses": {"PIV_tilt": [0, 22.5, 45]},                // or "sweep": ["PIV_tilt"]
    "expect": {"hit": ["PRT_flywheel"],                  // [null] = must hit nothing (line of fire)
               "angle": {"center": "PIV_flywheel", "frame": "PIV_tilt", "axis": "X", "zero": "Z",
                         "positive": "-Y", "range": [0, 26]}}}],
  "slide_out": [{"object": "BUY_battery", "dir": [1, 0, 0], "dist": 130, "step": 5, "min_clearance": 1.5}],
  "distances": [{"a": "PRT_hood", "b": "PRT_flywheel", "min": 5.5, "max": 7.0, "why": "nip squeezes a 7 mm M&M"}],
  "masses_g": {"BUY_battery": 620, "BUY_servo_*": 66},
  "cable_leads": {"CAB_phase_*": 80},
  "printers": {"P1S": [256, 256, 256], "H2D": [325, 320, 325]}, "prefer_printer": "P1S",
  "min_wall": 1.6, "overhang_deg": 45, "overhang_warn_mm2": 150, "max_bridge_mm": 25
}
```

## Reading the semantics

- **Bodies.** An object's body is its nearest `PIV_` ancestor, or `static`. A pair is swept over the joints that separate the two bodies, with each coupled joint replaced by its driver.
- **Pair classes.** For solids on the same body, an overlap above `vol_tol` fails. Across a joint, any overlap fails, a contact (zero volume) fails unless a `fits` rule sets `contact: true`, and clearance below the minimum fails. Fasteners may overlap the part they thread into on their own body; across a joint they are treated like any other solid. Cable overlaps are warns, and cable-to-cable pairs are ignored.
- **Fasteners.** Head direction comes from cadlib props, otherwise it is inferred: the wider end is the head. The head is buried when points just behind its bearing face are inside a solid. Engagement is the length over which a ring at 92% of shank radius sits inside one host part. Access casts a Ø`2*driver_r` ray bundle out from the head until a sphere of `hand_r` is free, at the home pose and at each joint limit, counting only the parts present at the fastener's assembly step.
- **Drop tests.** These cast straight first-contact rays with no bounce or slide. The angle is measured about `center` in `frame` coordinates, from the `zero` axis toward `positive`.
- **Coverage.** Every run lists `coverage` and `not_checked`. Quote both when you report results.
