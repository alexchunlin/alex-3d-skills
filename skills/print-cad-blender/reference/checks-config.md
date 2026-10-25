# checks.json

Every key is optional. Defaults live in `scripts/cadcheck.py DEFAULTS`. A worked config for a real 102-object assembly is
`<repo>/examples/mm-launcher-a1/checks.json`; attempt 2 (`examples/mm-launcher-a2/checks.json`) uses most blocks below, and attempt 3 (`examples/mm-launcher-a3/checks.json`)
adds `carry`, `fasteners.captive` and `flexures`.

```jsonc
{
  "joints": {"PIV_tilt": {"axis": "X", "lo": 0, "hi": 45, "step": 2.5}},   // only for blends without cadlib joint props
  "couplings": {"PIV_pinion": {"to": "PIV_pan", "ratio": -1}},
  "carry": {"PRT_nip_wheel": "PIV_hood"},   // modelled on one body at one setting, rides on this joint in use (A3)
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
  "fasteners": {"driver_r": 3.0, "hand_r": 14.0, "max_reach": 60, "max_reach_ext": 150, "min_engagement": 4.0,
                "lkey_short": 18, "lkey_insert": 2.5, "lkey_long": 56, "lkey_swing_deg": 60,   // 2.5 mm hex key
                "max_standoff": 2.0, "max_protrusion": 3.0,
                "captive": {"FST_nip_stud": "hex head in a hex pocket; the thumbwheel nut turns"}},   // never driven
  "service": [                    // access on the BUILT machine (assembly_order only covers first assembly)
    {"op": "change the nip gap", "fasteners": ["FST_clamp_*", "FST_jack_*"]},          // home + joint limits
    {"op": "re-tighten flywheel", "pose": {"PIV_tilt": 45}, "remove": ["PRT_launcher_cover", "FST_cover_*"],
     "fasteners": ["FST_fw_bolt_*"]}],

  "drop_tests": [{
    "name": "feed_outlet_to_wheel",
    "emit": {"frame": "PIV_pan", "center": [21, 0, 239], "normal": [0, 0, 1], "radius": 6.5, "step": 2},
    "dir": [0, 0, -1],                                   // gravity, world
    "poses": {"PIV_tilt": [0, 22.5, 45]},                // or "sweep": ["PIV_tilt"]
    "expect": {"hit": ["PRT_flywheel"],                  // [null] = must hit nothing (line of fire)
               "angle": {"center": "PIV_flywheel", "frame": "PIV_tilt", "axis": "X", "zero": "Z",
                         "positive": "-Y", "range": [0, 26]}}},              // zero/positive may be signed: "-Z" = BDC
    {"name": "feed_spout_to_tape", "mode": "slide", "stall_deg": 20, "stall_margin_deg": 5, "capture_mm": 0.5, "payload_mm": 7.0,
     "emit": {...}, "poses": {"PIV_tilt": [0, 15, 22.5, 30, 45, 46]}, // 46 = hard stop; stall below 20 deg, warn below 25
     "expect": {"hit": ["PRT_flywheel"], "angle": {"center": "PIV_flywheel", "frame": "PIV_tilt", "zero": "-Z", "positive": "-Y", "range": [0, 135]}}}],
  "index_tests": [{                                     // one window = one release; count them over the motion
    "name": "feeder_one_candy_per_cycle", "joint": "PIV_feeder", "sequence": [0, 60, 0], "step": 2,
    "probe": {"frame": "PIV_pan", "center": [21, 0, 267], "dir": [0, 0, -1], "radius": 3, "depth": 23},
    "blockers": ["PRT_feeder_disc", "PRT_feeder_plate"], "expect_windows": 1}],
  "slide_out": [{"object": "BUY_battery", "dir": [1, 0, 0], "dist": 130, "step": 5, "min_clearance": 1.5},
                {"name": "flywheel off", "objects": ["PRT_flywheel", "FST_fw_*"], "ignore": ["PRT_launcher_cover"],
                 "pose": {"PIV_tilt": 45}, "dir": [1, 0, 0], "dist": 140}],
  "distances": [{"a": "PRT_hood", "b": "PRT_flywheel", "min": 5.5, "max": 7.0, "why": "nip squeezes a 7 mm M&M",
                 "ray": {"frame": "PIV_tilt", "origin": [21, 37, 132], "dir": [0, 0, 1]},   // gap along a line, not nearest
                 "payload_mm": 7.0, "tape_mm": 0.5, "compliant": "PRT_hood leaf spring"}],   // squeeze > 0 needs a yielding part
  "stacks": [{"name": "magnet centring", "limit": 0.3, "terms": [{"what": "can in bore", "tol": 0.2}, {"what": "jig in bore", "tol": 0.1}]}],
  "flexures": [{"part": "PRT_nip_cover", "name": "leaf spring", "dir": [0, -0.48, 0.88],   // beam length, world at home
                "stress_mpa": 20.9}],                                                    // or "from"/"to" points
  "interlayer_mpa": 15,
  "exposure": {"max_cable_mm": 5, "cables_ok": ["CAB_usb*"], "min_escape": 8, "view_frac": 0.1, "view_z": -0.2,
               "nuts_ok": ["FST_wheel_nut_*"]},
  "masses_g": {"BUY_battery": 620, "BUY_servo_*": 66},
  "cable_leads": {"CAB_phase_*": 80},
  "printers": {"P1S": [256, 256, 256], "H2D": [325, 320, 325]}, "prefer_printer": "P1S",
  "min_wall": 1.6, "overhang_deg": 45, "overhang_warn_mm2": 150, "max_bridge_mm": 25
}
```

## Reading the semantics

- **Bodies.** An object's body is its nearest `PIV_` ancestor, or `static`. A pair is swept over the joints that separate the two bodies, with each coupled joint replaced by its driver.
- **Pair classes.** For solids on the same body, an overlap above `vol_tol` fails. Across a joint, any overlap fails, a contact (zero volume) fails unless a `fits` rule sets `contact: true`, and clearance below the minimum fails. Fasteners may overlap the part they thread into on their own body; across a joint they are treated like any other solid. Cable overlaps are warns, and cable-to-cable pairs are ignored.
- **Fasteners.** Head direction comes from cadlib props, otherwise it is inferred: the wider end is the head. Nuts are `fst_kind: "nut"` or `FST_*nut*`; a bolt-nut overlap is never an interference. The head is buried when points 0.25 mm behind its bearing face are inside a solid on the same body. Engagement is the length over which a ring at 92% of shank radius sits inside one host part, or, when a nut sits on the bolt axis, the overlap of shank and nut (short of the nut = fail). A shank or nut inside a `BUY_` that is not its thread host fails (`allow` it if the envelope just lacks the hole). Access casts a Ø`2*driver_r` ray bundle out from the head until a sphere of `hand_r` is free; if that is blocked it tries an L-key (short leg along the axis, long leg swung about it, needs `lkey_swing_deg` of clear arc). Poses: home, each joint limit, and the screw's own continuous joints every 60°; parts present per `assembly_order`. Stand-off = shank exposed under the head; protrusion = thread past the last part, warned only when visible from outside.
- **Service.** Same access test, with every solid present except `remove`, at `pose` (or home and each limit). Blocked at the first pose but reachable at another is a warn naming the pose to use.
- **Index tests.** The probe bundle is cast through `blockers` at every `step` of the `sequence`; a maximal run of open poses is one window. A window spanning the cycle start counts once. Open at the park position is reported.
- **Exposure.** A cable sample is exposed when `min_escape` of 26 rays leave the assembly without hitting a solid, or when `view_frac` of the 240 directions toward a viewer above or level (`z > view_z`) do. The second rule finds a cable seen through a notch: the A3 bonnet-foot notch scores 6/26 but 8.3 mm at 10%, and R3 said "about 8 mm". Exposed samples within 6 mm form one spot, warned when its extent passes `max_cable_mm`. A nut is warned when 2 or more of its outer samples are exposed, unless it is listed in `nuts_ok`.
- **Carry and captive.** `carry` re-parents the named objects onto a joint before any sweep, keeping their home pose. Use it for parts modelled at one setting that ride on another body in use (a thumbwheel on a stud). A `captive` fastener skips the head-buried, stand-off and access tests; engagement and nut pairing still apply. Each entry needs a reason a reviewer can check.
- **Flexures.** The beam direction is mapped through the part's `print_rot` (the STL export matrix). More than 45° off the bed with `stress_mpa` unknown or above `interlayer_mpa` (default 15, R3's limit for PLA across layers) fails; 20-45° warns.
- **Slide-out** sweeps against solids **and fasteners**. Pairs already overlapping at rest are listed in `overlapping_at_rest` and left to the interference and fastener checks.
- **Drop slide margin.** Each pose row has `flattest_slide_deg`, the shallowest slide a hitting ray made. Rays whose slide was flatter than `stall_deg + stall_margin_deg` warn: friction varies, and A3's 21° slide over a 20° limit was a major (A3-F1).
- **Drop tests.** Default mode casts straight first-contact rays. `"mode": "slide"` falls, then slides down wall slopes, stalls below `stall_deg`, and counts a hit when the falling point passes within `capture_mm` of the target or a sliding point is within `payload_mm` of it in line of sight (the attempt-2 designer's tracer, generalised). No bounce or rolling. The angle is measured about `center` in `frame` coordinates, from the `zero` axis toward `positive`.
- **Coverage.** Every run lists `coverage` and `not_checked`. Quote both when you report results.
