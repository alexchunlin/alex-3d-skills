# checks.json

Every key is optional. Defaults live in `scripts/cadcheck.py DEFAULTS`, row fields in `CONFIG_ROWS`. A key cadcheck
doesn't read is a config warn naming the closest known key (`summary.config_warns`, apart from the design warns); a key
starting with `_` (`"_about"`) is a note. A worked config for a real 102-object assembly is
`<repo>/examples/mm-launcher-a1/checks.json`; attempt 2 (`examples/mm-launcher-a2/checks.json`) uses most blocks below, and attempt 3 (`examples/mm-launcher-a3/checks.json`)
adds `carry`, `fasteners.captive` and `flexures`.

```jsonc
{
  "joints": {"PIV_tilt": {"axis": "X", "lo": 0, "hi": 45, "step": 2.5, "home": 0}, "PIV_pan": {"axis": "Z", "continuous": true},
             "PIV_gate": {"axis": "X", "kind": "prismatic", "lo": 0, "hi": 56}},   // axis/lo/hi/kind only for blends without cadlib joint props; step: see Between samples
  "couplings": {"PIV_pinion": {"to": "PIV_pan", "ratio": -1, "offset": 0}},
  "carry": {"PRT_nip_wheel": "PIV_hood"},   // modelled on one body at one setting, rides on this joint in use (A3)
  "overtravel_deg": 2.5,          // sweep this far past each limit; hits there are warns ("no margin")
  "overtravel_mm": 1.0,           // the same past the ends of a prismatic joint
  "max_poses_per_group": 48,      // grids over several joints are thinned to this
  "sweep_tol": 0.25,              // mm: swept-envelope step error, and the finest move the refinement halves to
  "envelope_voxel": 1.0,          // swept envelope voxel (mm); the envelope is oversize by sweep_tol + voxel
  "max_guard_poses": 256,         // refinement poses per envelope hit; past it the pair warns as unproven
  "envelope_max_poses": 600,      // a part on 2+ joints (tilt on pan): its envelope coarsens to this many poses

  "allow": [                      // designed overlap: interference skips the pair; a slide_out row keeps it, bounded
    {"a": "BUY_servo_*", "b": "BUY_horn_*", "why": "spline inside horn hub"},
    {"a": "PRT_gate_detent", "b": "PRT_jar_gate", "max_mm3": 1.0, "why": "detent rides the blade"}],  // bounded: deeper fails
  "fits": [                       // designed running fit across a joint
    {"a": "PRT_yoke_arm_L", "b": "PRT_trunnion_L", "min_clearance": 0.1, "why": "journal, 0.2 diametral"},
    {"a": "PRT_base_shell", "b": "PRT_turntable", "contact": true, "contact_normal": [0, 0, 1], "min_clearance": 0.1,
     "why": "thrust face on the deck; the R20/R20.3 hub journal is still measured"}],   // see "Contact fits" below
  "moving_min_clearance": 0.5,    // undeclared pairs across a joint: fail below this
  "moving_warn_clearance": 1.0,
  "vol_tol": 0.5,                 // mm3; below this an overlap counts as contact
  "printcheck": {                 // the parts layer check (scripts/printcheck.py DEFAULTS); rarely needs changing
    "cantilever_mm": 3.0, "cantilever_warn_mm": 1.0, "island_mm2": 0.5, "bridge_warn_mm": 25, "min_feature_mm": 0.4,
    // face pass: sloped regions measured past the overhang_deg cone from their anchored edges (overhang_deg comes from
    // the top-level key); warn past face_warn_mm, fail past cantilever_mm when face_fail_mm2 or more (projected);
    // two anchors more than face_bridge_dz_mm apart in height make a cantilever, not a sloped bridge
    "face_warn_mm": 2.0, "face_fail_mm2": 5, "face_min_mm2": 2, "face_flat_deg": 1.0, "face_bridge_dz_mm": 2.0,
    // two bands: slopes flatter than overhang_fail_deg (from vertical; 60 = 30 from horizontal, about Bambu/Orca's default
    // support threshold) fail past cantilever_mm; between it and overhang_deg (45) they only warn
    "overhang_fail_deg": 60,
    // tangent bed contact: under contact_min_mm wide (two extrusion lines) over contact_len_mm or more, below an
    // underside of radius contact_r_mm or more (a cylinder lying on the bed); fix: cut a flat about 0.3 x r
    "contact_min_mm": 0.9, "contact_len_mm": 3.0, "contact_r_mm": 3.5},

  "assembly_order": [             // tool access is tested against the parts present at each step
    {"step": "base", "objects": ["PRT_base_*", "FST_floor_*"]},
    {"step": "flywheel (bench)", "bench": "fw", "objects": ["PRT_flywheel", "FST_fw_*"]},
    {"step": "launcher (bench)", "bench": "launcher", "objects": ["PRT_launcher_*", "FST_motor_*"]},
    {"step": "cell into the cartridge (bench)", "bench": "cart", "objects": ["PRT_cartridge", "BUY_cell", "FST_cell_nut_*"],
     "order": ["PRT_cartridge", "FST_cell_nut_*", "BUY_cell"]},   // within a step (default: any order that fits)
    {"step": "flywheel onto launcher", "bench": "launcher", "merge": "fw", "objects": ["FST_hub_*"]},  // bench into bench
    {"step": "launcher into yoke", "merge": "launcher", "objects": ["PRT_arm_cap_*"]},
    {"step": "jar on: drop in at +30, twist to 0", "merge": "jar", "objects": [], "pose": {"PIV_jar": 30}},   // insertion pose
    {"step": "pod in, nose up 20", "merge": "pod", "objects": [], "insert_dirs": [[0, -0.34, 0.94]]},  // extra out-direction
    {"step": "snap cover", "objects": ["PRT_snap_cover"], "insert_ok": "snap arms flex 0.8 over the lip"},   // not tested
    {"step": "cap screws at tilt 45", "objects": ["FST_cap_*"], "pose": {"PIV_tilt": 45},
     "pose_how": "tilt servo slid out +X first (post cover off); pod on the 45 deg prop"},   // how a held joint gets there
    {"step": "battery on", "objects": ["BUY_battery"], "powered": true}],   // drives can be commanded from here on
  "joint_drives": {"PIV_tilt": "BUY_servo_tilt", "PIV_hood": null},   // what holds a joint (default: BUY_*servo*_<joint>)
  "fasteners": {"driver_r": 3.0, "hand_r": 14.0, "max_reach": 60, "max_reach_ext": 150,
                "min_engagement_d": 2.0, "tapped_engagement_d": 1.5,   // thread >= 2 d in PLA, 1.5 d in a tapped BUY part
                "lkey_short": 18, "lkey_insert": 2.5, "lkey_long": 56, "lkey_r": 1.25, "lkey_swing_deg": 60,   // 2.5 mm hex key
                "max_standoff": 2.0, "max_protrusion": 3.0, "hint_tilt_deg": 10,   // a bit that can't reach: smallest tilt that clears
                "captive": {"FST_nip_stud": "hex head in a hex pocket; the thumbwheel nut turns"},   // never driven
                "min_engagement": 4.0},   // mm, replaces both _d rules, as in configs before 2026-10; fastener_joint reads it too
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
     "expect": {"hit": ["PRT_flywheel"], "angle": {"center": "PIV_flywheel", "frame": "PIV_tilt", "zero": "-Z", "positive": "-Y", "range": [0, 135]}}},
    {"name": "line of fire clear", "emit": {...}, "sweep": ["PIV_pan"], "expect": {"hit": [null]},   // every pan pose
     "ignore": ["PRT_barrel"], "max_mm": 400, "home_only_ok": ["PIV_hood"]}],   // hood held at home on purpose
  "index_tests": [{                                     // one window = one release; count them over the motion
    "name": "feeder_one_candy_per_cycle", "joint": "PIV_feeder", "sequence": [0, 60, 0], "step": 2,
    "probe": {"frame": "PIV_pan", "center": [21, 0, 267], "dir": [0, 0, -1], "radius": 3, "depth": 23},
    "blockers": ["PRT_feeder_disc", "PRT_feeder_plate"], "expect_windows": 1, "pose": {"PIV_tilt": 0}}],
  "slide_out": [{"object": "BUY_battery", "dir": [1, 0, 0], "dist": 130, "step": 5, "min_clearance": 1.5},  // step: mm per station
                {"name": "gate open stop", "object": "PRT_jar_gate", "dir": [1, 0, 0], "dist": 56, "step": 0.5,
                 "expect": "blocked", "blocked_by": ["PRT_jar_adapter"], "at_mm": [52, 53],       // an end stop: must stop there
                 "flex": {"PRT_gate_detent": 1.0}},                                                // the detent rides over (below)
                {"name": "flywheel off", "objects": ["PRT_flywheel", "FST_fw_*"], "ignore": ["PRT_launcher_cover"],
                 "pose": {"PIV_tilt": 45}, "dir": [1, 0, 0], "dist": 140}],
  "distances": [{"a": "PRT_hood", "b": "PRT_flywheel", "min": 5.5, "max": 7.0, "why": "nip squeezes a 7 mm M&M",
                 "ray": {"frame": "PIV_tilt", "origin": [21, 37, 132], "dir": [0, 0, 1]},   // gap along a line, not nearest
                 "payload_mm": 7.0, "tape_mm": 0.5, "compliant": "PRT_hood leaf spring", "pose": {"PIV_tilt": 0}},   // squeeze > 0 needs a yielding part
                {"a": "PRT_hood", "b": "PRT_flywheel", "min": "=MM_T[1] + TAPE_T",      // over the whole entry arc, not one station
                 "ray": {"origin": [21, 37, 132], "dir": [0, 0, 1],                     // the station at sweep angle 0 (BDC)
                         "sweep": {"center": [21, 37, 170], "axis": [-1, 0, 0], "from": 0, "to": 100, "step": 5}},
                 "poses": [{"PIV_hood": 0.327, "PIV_nip_lift": -2.19}]}],
  "payload_fit": [                // does the pocket take one payload and refuse two? (v2 A1/A2 feeder pocket)
    {"name": "pocket blocks an edge-on pair", "against": ["PRT_feeder_disc"], "center": [10.5, 18.19, 263.0],  // floor point
     "frame": "PIV_feeder", "up": [0, 0, 1], "across": [1, 0, 0], "place": "pair_edge_on", "size": [12.5, 6.5],  // D x T, MIN size
     "shape": "lens", "expect": "blocked", "margin": 0.2},
    {"name": "pocket seats one flat", "against": ["PRT_feeder_disc"], "center": [10.5, 18.19, 263.0], "place": "flat",
     "size": [13.5, 7.5], "expect": "fits", "pose": {"PIV_feeder": 30}},                                   // MAX size
    {"name": "tube holds a stack of three", "against": ["PRT_hopper"], "center": [0, 0, 250], "place": "stack_flat",
     "count": 3, "gap": 0.2, "size": [13.5, 7.5], "expect": "fits"}],               // count: pair_edge_on, stack_flat; gap: lift off the floor
  "sightlines": [{"name": "finger reaches the thumbwheel through the slot", "frame": "PIV_tilt", "poses": [{}, {"PIV_tilt": 45}],
                  "origins": [[19.5, -2.33, 111.27], [15.5, -2.33, 111.27]], "dir": [0, -0.316, 0.949],
                  "first_hit": "PRT_nip_wheel", "max_mm": 40, "through": []},     // null = must hit nothing
                 {"name": "view of the reveal", "origin": [0, -300, 120], "dir": [0, 1, 0], "pose": {"PIV_tilt": 0}, "first_hit": "PRT_beam"}],
  "stacks": [{"name": "magnet centring", "limit": 0.3, "terms": [{"what": "can in bore", "tol": 0.2}, {"what": "jig in bore", "tol": 0.1}]},
             {"name": "jar band clears its neighbours", "between": ["BUY_jar_band", "*"], "poses": [{}, {"PIV_jar": 30}],  // limit measured
              "terms": [{"what": "glass thread / band", "tol": 1.0}, {"what": "adapter disc in the band", "tol": 0.75}]}],
  "flexures": [{"part": "PRT_nip_cover", "name": "leaf spring", "dir": [0, -0.48, 0.88],   // beam length, world at home
                "stress_mpa": 20.9},
               {"part": "PRT_gate_detent", "from": [0, 10, 5], "to": [0, 22, 5]}],      // or the beam's ends
  "interlayer_mpa": 15,
  "exposure": {"max_cable_mm": 5, "cables_ok": ["CAB_usb*"], "min_escape": 8, "view_frac": 0.1, "view_z": -0.2,
               "nuts_ok": ["FST_wheel_nut_*"]},
  "masses_g": {"BUY_battery": 620, "BUY_servo_*": 66},
  "cable_leads": {"CAB_phase_*": 80},
  "cable_chains": [{"name": "encoder signal", "cables": ["CAB_encoder", "CAB_launcher_bundle", "CAB_launcher_base"],
                    "lead": 550, "why": "one 5-wire lead, Plink to MotorGo, unspliced across both joints"}],
  "cable_junctions_ok": ["CAB_bus_*"],      // an inline connector no wider than the cable; a bigger one is a BUY_ part
  "cable_min_bend_od": 0.75,                // a corner tighter than this x OD (centreline radius) is a kink
  "fasteners": {"stock_ok": ["FST_custom_*"], "stock_lengths": {"3": [6, 8, 10, 12, 16, 20]}},   // override the stocked lengths
  "accepted_warns": [{"check": "parts", "object": "PRT_flywheel", "kind": "bridge", "match": "a 72.0 mm bridge",   // pins the span
                      "why": "1 mm flange ring, prints as a bridge over infill"},
                     {"check": "clearance", "object": ["PRT_hood", "FST_nipstop"], "kind": "just past the limit", "any": true, "why": "..."}],
  "printers": {"P1S": [256, 256, 256], "H2D": [325, 320, 325]}, "prefer_printer": "P1S",
  // overhang_deg: support angle from vertical, for printcheck's layer allowance and face pass warn line (a slicer
  // "threshold angle" of 30 from horizontal is 60 here)
  "min_wall": 1.6, "overhang_deg": 45, "overhang_warn_mm2": 150, "max_bridge_mm": 25,
  "pla_density": 1.24e-3, "flow_mm3_s": 12,   // mass and print-time estimates (g/mm3, mm3/s)
  "collections": {"printed": "Printed", "purchased": "Purchased", "fasteners": "Fasteners", "cables": "Cables"}
}
```

## Rows that follow the params: `"=EXPR"`

Any string value that starts with `=` is evaluated as a Python expression over the build's named parameters (those
passed to `asm.new_scene(params=...)`, stored in the .blend; older blends read `manifest.json` beside the blend, or
pass `--params file.json`). It works anywhere a number goes: `min`, `max`, `payload_mm`, `size`, `dist`, `at_mm`,
joint values in `poses`, `lead`.

```jsonc
{"a": "PRT_hood", "b": "PRT_flywheel", "min": "=MM_T[1] + TAPE_T", "poses": [{"PIV_hood": "=HOOD_HI", "PIV_nip_lift": -1.493}]},
{"name": "min pair blocked", "place": "pair_edge_on", "size": ["=MM_D[0]", "=MM_T[0]"], "expect": "blocked", ...}
```

Write pass rows against the payload's declared **max** and blocking rows against its **min**, from the same params the
geometry uses. v2 A3 declared `MM_T = (6.3, 7.5)` but typed its full-lift gap row as 7.5 (nominal 7.0 + tape), so the
row passed while the reviewer's 8.0 row failed (FINDINGS V2A3-F1). A failed expression (a param that isn't there) is a
`config` fail naming the row and the expression, and the row is skipped. A failed setting falls back to its default
(`DEFAULTS`), or is dropped so the code's own fallback applies; an entry of a section keyed by name (`couplings.PIV_x`,
`masses_g.BUY_x`) is dropped whole. Each says which in its fail. A None left in place crashed check_stacks (push-assist
PA-A5-T26), cadlib.joints (a coupling ratio) and the fasteners check (`min_engagement`), each with no report. The
report's `params.expressions` lists every value used.

`cad rows cadcheck.json [REGEX]` prints one line per row of every check (and `cad rows manifest.json FST_` the parts),
so you grep the report instead of writing a `json.load` snippet. Report layout, if you do script it:
`checks.<check>.findings[]` (status, msg), `checks.<check>.rows[]` for most checks, `checks.drop.tests[].rows[]` and
`checks.payload.rows[]`, `checks.interference.{collisions,contacts,min_clearance}[]`; the manifest keeps fasteners
under `parts` with `kind: "FST"` (there is no `fasteners` key).

## Running subsets and your own rows

```
cad check model.blend checks.json out.json --only drop,slide             # these checks only
cad check model.blend checks.json out.json --overlay mine.json            # append mine.json's rows
cad check model.blend checks.json out.json --only drop --overlay mine.json --overlay-only   # only mine.json's drop rows
```

`--overlay` appends list sections and updates dict sections; `allow` and `fits` rows from the overlay go first, so they
win. Use it instead of hand-copying checks.json with sections emptied: the v2 A1 reviewer spent about 5.5 of 14.7 min
doing that (FINDINGS V2A1-T6). CONFIG and OUT are optional, and a flag in their place is not taken as a file name.

A row that names an object not in the scene (a subsystem not built yet) gives one fail, "not in the scene; row
skipped", and the run carries on. Keep the row; don't `--only` around it.

A check that runs with no rows in its section (`--only stacks` with no `stacks`) adds "no stacks rows in the config,
nothing checked" to `not_checked`, and under `--only` the summary lists it in `only_without_rows`. Push-assist A2 named 11
checks in `--only`, 5 with no rows, and read PASS (PA-A2-T11). An `--only` name that is no check is a config warn.

## Reading the semantics

- **Assembly order.** Steps run in list order. A part is present at step *i* when its own step is at or before *i*
  and it was built in the same group: the main assembly (no `bench`), or the same `bench`. A `merge: "<group>"` step
  brings a bench group in: into the main assembly, or into another bench when the merge step has its own `bench`.
  Merges chain to any depth. Parts that no step matches are assumed present throughout and listed under
  `assembly.unordered_solids_assumed_present`. Fasteners are access-tested against the parts present at their step.
- **Insertion** (`--only insertion`, about 7 s on the v2 launcher). Each `PRT_`/`BUY_` part must come out of its place
  along one straight line, to infinity, past the solids and fasteners of the earlier steps in its group; so must each
  merged bench group, past the group it joins. Directions: ±X, ±Y, ±Z, ± the axis of each screw that touches the part
  (a sleeve goes on along its stud), and the step's `insert_dirs` (the direction the part moves to come **out**). The
  step's `pose` is set first (a bayonet at its drop-in angle). Cables are not obstacles; zero-clearance seats and
  edge breaks don't block (a hit counts only 0.3 mm into the other part). A step with `insert_ok: "<reason>"` is listed, not tested. A part in a `bench` step that is more than 2 mm
  from every other part of its group warns too: it is in the wrong sub-assembly. v2 A6 put the bus splice (in the pan
  hub) in the feeder's bench step; the feeder merge then read "+Z PRT_groove_cap (BUY_bus_junction) at 3" (FINDINGS
  V2A6-F1). On the v2 A1-A5 configs it gives 3 warns, all config facts: the jar step's +30 drop-in and the pod's
  nose-up angle need a `pose`, and the nip stud is listed one step before the backplate it drops into.
- **Order within a step** (insertion). The parts of one step are tested against each other too. Without `order`,
  they must go in in some order that works: cadcheck takes them out, last listed first, while any can come out (so it
  finds an order whenever one exists, and the listed one when that works) and reports it in `step_orders` (`order`,
  `listed_differs`). The step's own fasteners are no obstacle then (screws go in after the parts they join). With
  `order: [globs]` the step goes in in exactly that order, fasteners included; objects on one `order` glob aren't
  tested against each other, objects no `order` glob matches go in last, and a glob matching none of the step's
  objects warns. A part with no way in past its own step's parts warns "in any order of the step's parts" (or, with
  `order`, "which the step's order puts before it", with the order that works). push-assist A6/A7 listed the
  cartridge, its load cell and the cell's nuts in one bench step; under the old "any order, not obstacles" rule the
  cell was never tested against the cartridge it could not be fitted into (PA-A7-T7, T19). A bounded `allow`
  (`max_mm3`, facet overlap at a seat) doesn't drop the pair here, an unbounded one (a spline in a horn) does: A7's
  cartridge x cell allow measured 0.0 mm³ and hid the cell (PA-A8-T6). `buy_seat_same_step` lists each `BUY_` part
  that shares a step with the `PRT_` part it seats in (surfaces within 0.2 mm); give such a step an `order` when the
  build order matters beyond what fits (PA-R7 #7: the stops went in first in the README, and the cell only fits
  before them). On one `order` glob the pair warns. On the 10 archived designs 20 of 146 multi-part steps fit only in
  another order than listed (taking the listing as the order gave 57 warns), 128 bought parts share a step with their
  seat (as warns, the noise would have swamped the check), and two new warns are true facts: v1's MotorGo board in a
  pocket of the base shell, shell 0.36 mm above and 5.4 below it (a1-a3), and v2's M&M mass carrier inside its
  closed jar (poured, not inserted).
- **Off-axis ways in** (insertion). When every stated direction is blocked, the 20 cube diagonals are tried, and the
  warn says "free along [x, y, z] (off-axis)" with the `insert_dirs` to add, or "No cube diagonal is free either".
  Push-assist A8's cell goes in at 45° along its stud slots, which only an `insert_dirs` entry tested.
- **Held poses** (part of `assembly`). A step that needs a joint away from home after the joint's drive is in: the
  step's `pose`, or a screw at that step that the fastener check reaches only at a joint limit. The drive is
  `joint_drives[joint]`, or by name a `BUY_` servo/motor/stepper/actuator ending in the joint's name (PIV_tilt ->
  BUY_servo_tilt; continuous and coupled joints are left out; `null` says a joint is free by hand). The drive is in
  from the step it lands in the main assembly (its bench merge). Before the first step marked `"powered": true` a
  servo can only be back-driven through its gears, so the step warns unless it has `"pose_how": "<how>"`. v2 A7 put
  the groove cap at step 11a, where one screw is reachable only at tilt 45, but the tilt servo went in at step 8 and
  the battery at step 14 (V2R7 A7-01, major; FINDINGS V2A7-F1). Fix: do the step before the drive goes in, move the
  screw so it is reachable at home, or take the drive out first and say so in `pose_how`.
- **Contact fits.** `contact: true` alone accepts contact anywhere on the pair. That also hides a journal rubbing on the
  same pair: v2 A1 declared post x journal plate and shell x turntable for their thrust and stop faces, and the journals
  inside them went unmeasured (FINDINGS V2A1-V4). Add `contact_normal` (one `[x, y, z]` or a list, a home-pose world
  direction of the rule's `a` part, turning with it) and contact is accepted only on faces within 20° of ±that normal.
  The rest of the pair is measured against the rule's `min_clearance`, so set it to the journal's radial clearance.
- **Warn triage.** List each warn you have looked at and accept under `accepted_warns`: `check` (the text before the
  first `: `), `kind` (whole words of the defect in the message, outside object names: `wall samples`, `bridge`,
  `collide only`), `object` (a name, glob or list, each a whole token of the message) and `why`. A warn with a measured
  value is accepted only with `match` (text that must be in the line, e.g. `"427 wall samples < 3.0 mm (min 2.21)"`; it
  pins the number, so a worse wall is a new warn) or `"any": true`; a near miss is a config warn. An accept with no
  `object` and no `any` is a config warn: it takes the kind on every part. The PR #10 review thinned the demo base's wall
  from 2.4 to 1.2: an accept without the number swallowed the new 0.46 mm warn. The summary reports `untriaged_warns`, and `warn_list` holds only untriaged ones. An accept that matches no warn is stale
  (`stale_accepts`); under `--only`, one whose check did not run is `accepts_not_evaluated`. v2 A1 finished at 0 fails,
  34 warns, and three of R1's issues were in those warns. The old form, `{"match": "<substring>"}`, still works and is a
  config warn: `"PRT_tray_L: "` accepted every warn on the part, later ones of another kind too, and it names no check,
  so under `--only` an unmatched one can't be called stale (push-assist PA-A4-T10). `summary.accept_suggestions` gives
  the structured accepts that cover what each old one covers in the run.
- **Stability.** Every driver joint at lo, home and hi, and continuous joints every 45°, up to 4000 poses. The 10 worst
  rows are kept.
- **Bodies.** An object's body is its nearest `PIV_` ancestor, or `static`. A pair is swept over the joints that separate the two bodies, with each coupled joint replaced by its driver.
- **Pair classes.** For solids on the same body, an overlap above `vol_tol` fails. Across a joint, any overlap fails, a contact (zero volume) fails unless a `fits` rule sets `contact: true`, and clearance below the minimum fails. Fasteners may overlap the part they thread into on their own body (the head and nut overlap test below covers the rest); across a joint they are treated like any other solid. Cable overlaps are warns, and cable-to-cable pairs are ignored.
- **Fasteners.** Head direction comes from cadlib props, otherwise it is inferred: the wider end is the head. Nuts are `fst_kind: "nut"` or `FST_*nut*`; a bolt-nut overlap is never an interference. The head is buried when points 0.25 mm behind its bearing face are inside a solid on the same body. Head and nut overlap: the head from 0.25 mm behind its bearing face to its top, and each nut between its faces (less 0.25 mm at each) and within its flats, are intersected with every solid on the same body: over `vol_tol` fails ("overlaps": a rib through the head, a counterbore or pocket too small, a nut with no pocket), a smaller overlap warns ("grazes"); `allow` rules apply (`max_mm3` bounds them). A cadlib countersunk head is not tested (its cone sits in the countersink, ahead of `at`). A screw without cadlib props is probed from where it is last wider than 1.25 x its shank back to its top, so a modelled countersunk cone with intermediate rings is partly tested. A fastener whose probe comes out empty (no head behind its bearing face, no material inside a nut's flats) is listed under `not_checked`. Engagement is the length over which a ring at 92% of shank radius sits inside one host part, or, when a nut sits on the bolt axis, the overlap of shank and nut (short of the nut = fail). A shank or nut inside a `BUY_` that is not its thread host fails (`allow` it if the envelope just lacks the hole). Access casts a Ø`2*driver_r` ray bundle out from the head until a sphere of `hand_r` is free; if that is blocked it tries an L-key (short leg along the axis, long leg swung about it, needs `lkey_swing_deg` of clear arc). A screw neither reaches, or reaches only past `max_reach`, gets a `[bit: ...]` hint. Along the axis: for one printed part on the screw's own body, the bit length through a hole in it or fitting it after the screw (`assembly_order`); for several, or one that moves, only the latter; a purchased one is named. Tilted: the smallest tilt up to `hint_tilt_deg` (2 deg steps, 8 headings) that clears with a reach under `max_reach` (over 3 deg: a ball-end driver). A bolt with its nut and its head closed in within 5 mm is taken for a captive stud nobody declared, and the hint says to declare it (`captive`); a buried head without a nut says fix that first. Poses: home, each joint limit, and the screw's own continuous joints every 60°; parts present per `assembly_order`. Stand-off = shank exposed under the head; protrusion = thread past the last part, warned only when visible from outside.
- **Service.** Same access test, with every solid present except `remove`, at `pose` (or home and each limit). Blocked at the first pose but reachable at another is a warn naming the pose to use. Removal itself is assumed, so an op that removes printed or purchased parts warns unless a `slide_out` row moves them at the op's `pose`; an op with no `pose` is proved by a row at home. In v2 A1 the nip cover came off only at tilt 45, while the op had no pose (FINDINGS V2A1-F2).
- **Index tests.** The probe bundle is cast through `blockers` at every `step` of the `sequence`; a maximal run of open poses is one window. A window spanning the cycle start counts once. Open at the park position is reported.
- **Exposure.** A cable sample is exposed when `min_escape` of 26 rays leave the assembly without hitting a solid, or when `view_frac` of the 240 directions toward a viewer above or level (`z > view_z`) do. The second rule finds a cable seen through a notch: the A3 bonnet-foot notch scores 6/26 but 8.3 mm at 10%, and R3 said "about 8 mm". Exposed samples within 6 mm form one spot, warned when its extent passes `max_cable_mm`. A nut is warned when 2 or more of its outer samples are exposed, unless it is listed in `nuts_ok`.
- **Carry and captive.** `carry` re-parents the named objects onto a joint before any sweep, keeping their home pose. Use it for parts modelled at one setting that ride on another body in use (a thumbwheel on a stud). A `captive` fastener (screw or nut) skips the head-buried, stand-off, access and head or nut overlap tests; engagement and nut pairing still apply. Each entry needs a reason a reviewer can check.
- **Flexures.** The beam direction is mapped through the part's `print_rot` (the STL export matrix). More than 45° off the bed with `stress_mpa` unknown or above `interlayer_mpa` (default 15, R3's limit for PLA across layers) fails; 20-45° warns.
- **Payload fit.** Rigid probes stand on the `center` floor point: `flat` (thickness along `up`), `edge_on`, `pair_edge_on`
  (`count` side by side along `across`) or `stack_flat`. `shape` is `lens` (two spherical caps, the sharpest rim, so the
  conservative choice for "blocked"), `ellipsoid`, `sphere` or `cylinder`. The probe is overlapped (Manifold) with the
  `against` solids, then grown or shrunk until the answer flips: `margin_mm` is the spare, `short_by_mm` how far a
  failing row is off. Use the payload's **minimum** size for `blocked` and its **maximum** for `fits`. v2 A2's Ø14.4
  pocket blocked a 13 x 7 pair by 0.11 mm and seated a 12.5 x 6.5 pair (fail, 0.14 short). No settling or tumbling.
  "Blocked" means an overlap above 0.01 mm³, so a rim that just touches the wall reads margin 0.00 (v2 A4 progress.md).
- **Sightlines.** Each origin casts along `dir` (both in `frame` home coordinates, moved with the joint) through solids
  and fasteners, minus `through`. The first hit must match `first_hit`, or nothing when it is null.
- **Assembly audit.** `assembly.step_of` in the report maps every object to its step: look there before claiming a part
  is in no step. Solids and fasteners in no step warn, and so does a step label whose `M<d> x <L>` matches none of
  that step's screws of that diameter.
- **Ray slip.** A ray row at a non-home pose is compared with the same ray at home. When the ray lands on a different
  face of a part (off the home face's plane by more than 0.5 mm, or a normal turned more than 25°) **and** the gap is
  much wider than the nearest gap, it warns: the ray probably slipped past the working face. Frame the ray in the joint
  that moves the part (v2 A2: a nip ray in the tilt frame read 14.18 at full leaf lift against a 7.06 nearest gap).
  Diameters, approach lines and gaps measured along a stud are not flagged (the first version flagged 9 such rows in
  v2 A3, all false: V2A3-T2).
- **Swept ray.** `ray.sweep` turns the ray (origin and dir) about `axis` through `center`, both in the ray's frame
  coordinates, from `from` to `to` degrees in `step`s. The row's `mm` is the worst station against `min`/`max` (the
  smallest gap when there is no bound), with `sweep_deg`, `profile` ([[deg, mm]]) and `missed_deg`. A station where the
  ray misses a part counts as open: it fails a `max`, and on a `min` row it warns, because that station measured
  nothing (v2 A6's full-lift rows at home and the max stop dropped psi 0 unseen, V2R6 A6-03). Start the sweep where
  both faces are. One row replaced v2 A4's three reviewer rows and its probe script, with the same numbers
  (7.50 / 7.67 / 7.95 at psi 80, V2A4-F1).
- **Poses outside a joint's range.** Any `pose`/`poses` value past the joint's `lo..hi` is listed in the summary
  (`poses_past_limits`), not warned: rows past a firmware limit on purpose are common (a hard stop beyond it). Add
  `"past_limit_ok": true` to such a row to drop it from the list. A pose naming no joint, or a coupled joint, is a
  `config` fail (set_pose would ignore it). v2 A4's planner pre-ran full-lift rows at -2.19 on a model whose limit was
  -1.493; the hood was posed through the solid leaf and the rows passed (V2A4-T2).
- **Stale model.** When `*.py` or `parts/*.py` beside the blend is newer than the blend, cadcheck warns (`build:`), and
  the warn cannot be accepted: the last build failed and the report is about the previous model (V2A4-T1).
- **Compliance.** A distances row whose `compliant` names a part (`"PRT_nip_leaf: ..."`) warns when that part has no
  `flexures` row. Cables with no lead length (no `lead_len`, no `cable_leads` match) are listed in one warn.
- **Slide-out** with `"expect": "blocked"` fails when the motion is not stopped, or is stopped by something other than
  `blocked_by` or outside `at_mm`.
- **Bounded allow.** `"max_mm3"` on an `allow` rule skips overlaps up to that volume and fails anything deeper (the
  largest seen is in `interference.allowed_max`). An allow without it skips the pair at every pose, so a deeper clash in a
  sweep never shows; cadcheck lists allows that skip a pair across a joint with no bound (`summary.unbounded_allows`).
  v2 A5 allowed the gate detent against the blade "0.43 mm³ < vol_tol", which also hid the whole gate sweep (V2R5 A5-06).
- **Allows in a slide.** A `slide_out` row keeps an allowed pair as an obstacle: overlap up to the rule's `max_mm3`
  (with none, the pair's overlap at rest plus `vol_tol`, or 0.1% of a large one) rides and is recorded in the row's
  `allowed`; deeper stops the slide, and the fail names the allow (`over_allow`). Its clearance is not measured. A snap
  or spring that rides the mover goes in the row's `flex`; a press fit pushed deeper needs `max_mm3`. The row used to
  drop the pair, so push-assist A7's load cell slid through the cartridge its 3 mm³ seat allow covered, and the 0.2 mm
  short slot passed two rounds (PA-A7-T19a).
- **Unused allows.** An allow that measures 0 mm³ on every pair it covers, wherever the checks evaluate the pair (home
  on one body; the interference pose grid across a joint, where a touch or a gap under `moving_warn_clearance` counts
  as use; the slide rows that bring the pair within 3 mm; insertion, when a part it lets through would block the way
  in), or that covers no pair, is a config warn and is listed in `summary.unused_allows`. It needs interference, plus
  slide and insertion when the config has their rows, so `--only interference` reports none. Possibly stale: check what
  it was for, and remove it if no check needs it. The A7 seat allow measured 0.0 mm³ and protected nothing (PA-A8-T6).
- **Measured stack limit.** A `stacks` row with `"between": [A, B]` takes its limit from the geometry: the nearest gap
  from A to B (name, glob, list, or `"*"` for every solid and fastener not touching A), over `poses`. The row reports
  `measured_mm`, `nearest` and `touching`. Use it for every stack that guards a clearance: a typed limit stays put when
  the geometry moves. v2 A5's band stack said "designed radial clearance 3.0" while a new detent tab sat 0.322 from the
  band; with `between` the same terms fail at RSS 1.31 > 0.322 (V2A5-F1).
- **Slide-out flex.** `"flex": {"PRT_gate_detent": 1.0}` lets a spring ride the moving part: overlaps with it up to
  that many mm³ are recorded in `flexed` (largest overlap and where, below `vol_tol` too) instead of blocking, even when an `allow` rule
  covers the pair. Use it for detents and snap bumps instead of `ignore`, which proves nothing about the spring (v2 A3
  ignored its gate detent, V2A3-T5). A part named in `flex` needs a `flexures` row.
- **Prismatic joints.** `asm.joint(..., prismatic=True)` slides along +axis, with `lo`, `hi`, `home` and `step` in mm.
  Every sweep covers it like a rotary joint, with `overtravel_mm` (default 1.0) past each end. Model gates, drawers and
  plungers this way: the open state then joins interference, drops, sightlines and stability.
- **Between samples.** Each joint is sampled every `step` (the joint's `step`, from `asm.joint(step=)` or a `joints`
  row, which overrides the default of range / 12, at least 2.5° or 1 mm), and grids are thinned to
  `max_poses_per_group`. The samples give the clearance numbers and the poses in the report. Between two of them a
  part moves up to its reach x the step and could pass through a thin part unseen: the PR #3 review's `wedge`, a 2 mm
  arm at 70 mm reach, passed through a cable between the 0 and 15° samples (3.4 mm sampled, 100.5 mm³ at 7.5°).
  So each pair across a joint (no `allow` rule) also goes through three stages:
  1. **Broad phase.** Each part's box is swept over its joints' ranges with overtravel: a ring sector
     (radius x height x angle) about a revolute joint, or the box extruded along a slide. It is compared with the
     other part's bounds. These are comparisons only.
  2. **Narrow phase.** `geom.swept_envelope` of the moving part, cached per part, is tested once against the other
     part. Every connected shell of each side counts, so a joined placeholder's small pin inside the envelope is a
     meeting. No meeting proves the pair clear over the whole range. A part on two or more joints (tilt on pan) uses
     `swept_envelope_chain`. A wheel's spin in a chain is first replaced by its solid of revolution (the router's
     annulus), so only the other joints are swept. The envelope is oversize by `sweep_tol` + `envelope_voxel`
     (1.25 mm at the defaults) about one joint. A chain adds `sweep_tol` per joint, more when `envelope_max_poses`
     coarsens it. The coverage line gives the actual range of pads.
  3. **Refinement**, for envelope hits only. The pair's cells are halved where a lower bound on the clearance (dense
     surface samples, less their covering radius) can't beat the reach bound (`cadlib.joints.move_rate`). This
     continues until the cell is clear, a collision is found (reported as "between the sampled poses", with its
     pose and volume), the move is under `sweep_tol`, or `max_guard_poses` are spent. A pair left unproven **warns**,
     naming the cell's pose range.
     A declared `fits` pair the envelope meets is refined for collision only. Cells where the turning test (each
     triangle's height, radius and angle about the axis) proves a one-axis pair clear are skipped (a journal). The
     rest are swept with every point moving under `sweep_tol`, and only an overlap of `vol_tol` or more fails.
     A lug in the arm's path on the same part as the shaft is still caught. The outcome per fit is in
     `between_samples.fits_flagged`.

  An explicit `step` still sets the sampled grid. Counts and the time of each stage are in
  `interference.between_samples`.
- **Bridges.** The span of a ceiling region is the diameter of the widest circle inside it, in print orientation, and
  `bridge_at` gives its centre (world). It used to be the short side of the region's bounding box, which read 26.4 for
  a 56.5° arc of width 6 (v2 A3, V2A3-T3).
- **Cables.** A `cable_chains` row adds up its routes and fails above `lead`: use it when conductors run on through
  several routes. Cable ends that meet another cable's end with no purchased part within 3 mm warn (cadlib builds store
  the ends, `cab_ends`); declare the chain, or model the connector as a `BUY_` part. `cable_junctions_ok` waives an
  inline connector no wider than the cable; waived junctions are listed in `cables.junctions_waived` (v2 A5 waived a 3-way
  bus junction it never modelled, V2R5 A5-03).
- **Cable ends across a joint** (`cables.end_drift`). A cable end that meets another cable's end (within 2 mm) or a
  solid (within 3 mm) on another body is followed to each joint limit; coming more than 2 mm apart warns. Ends that
  meet on the joint axis stay together and pass. v2 A6 moved the bus splice to r 7 off the pan axis: the static pan
  lead's end came 8.8 mm away from it at pan -90, and the base lead 5.7 mm from the bundle, while its `distances` row
  passed because the two sleeves overlap (V2R6 A6-02). Fix: meet on the axis, or end the static run in a service loop
  and start a new route on the moving body.
- **Kinks and shared tubes** (`cables.kinks`, `cables.shared_runs`). From each route's polyline (cadlib stores it as
  `cab_path`; older blends get it back from the tube mesh): a corner whose fitted centreline radius is under
  `cable_min_bend_od` x OD warns. A corner gets half of each neighbouring segment for its arc; at an end within 3 mm of
  a `BUY_` part (plug, splice, board) the first OD must run straight, so a turn right at the plug reads radius 0. An
  end that meets the next route of the same `cable_chains` row is a hand-over and gets its full segment. Two routes on
  one body whose centrelines stay within half their summed radii for more than 2 OD lie in one tube and warn: the
  channel has to hold both. v2 A7 laid the tilt and feeder bus leads in one tube for 16 mm and turned both 90 deg onto
  the splice face 1.5 mm below (V2R7 A7-02). Model a real bundle as one route with a chain row per conductor.
- **`--out`.** `cad check m.blend c.json OUT.json --only x` or `... --only x --out OUT.json`: both write OUT.json. Before
  v2 A6 the flag form was ignored and the default `cadcheck.json` was overwritten (V2A5-T1).
- **Stock lengths.** Screws whose length isn't in `fasteners.stock_lengths` for their diameter warn, unless listed in
  `fasteners.stock_ok`. `cad bom BOM.md manifest.json` checks the BOM's fastener table against the model (size, length,
  head, count) with the same table.
- **Slide-out** sweeps against solids **and fasteners**. Pairs already overlapping at rest are listed in `overlapping_at_rest` and left to the interference and fastener checks.
- **Drop slide margin.** Each pose row has `flattest_slide_deg`, the shallowest slide a hitting ray made. Rays whose slide was flatter than `stall_deg + stall_margin_deg` warn: friction varies, and A3's 21° slide over a 20° limit was a major (A3-F1).
- **Drop coverage.** Each test lists `on_path`, the objects its rays touched. A ranged joint that moves one of them relative to the emitter, and is not in `poses` or `sweep`, is a warn: the test held it at home. Typical cases are an adjuster such as a nip-gap hinge, and a gate. Put both ends in `poses`, or list the joint under `home_only_ok` with a reason. v2 A1's nip drop ran at the home hood setting only, and R1 found stalls at the open end (FINDINGS V2A1-F1).
- **Drop tests.** Default mode casts straight first-contact rays. `"mode": "slide"` falls, then slides down wall slopes, stalls below `stall_deg`, and counts a hit when the falling point passes within `capture_mm` of the target or a sliding point is within `payload_mm` of it in line of sight (the attempt-2 designer's tracer, generalised). No bounce or rolling. The angle is measured about `center` in `frame` coordinates, from the `zero` axis toward `positive`, so it turns about the third axis; `angle.axis`, if given, must be that one (a config fail otherwise).
- **Coverage.** Every run lists `coverage` and `not_checked`. Quote both when you report results.
