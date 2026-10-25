# Design principles

Rules to follow while you model, distilled from what the v1 reviewers kept finding. `footguns.md` lists the mistakes
and the check that catches each one. This page says what to build instead.

Evidence is either a `<repo>/docs/FINDINGS.md` ID or a review issue. "R2 #10" is issue 10 of the attempt-2 review
(`mm-launch-hw/renders/attempt-2/review.md`). R3 issues are numbered by rank, so "R3 #4" is the one R3 labels "A1".
"R2 prev #17" is row 17 of R2's previous-issues table. "Enforced by: reviewer" means no tool checks it: only the
`cad-design-review` checklist does. Look at `iso` and `iso_front_left` yourself before you hand over.

## Form language

Form language capped Aesthetics at 5-6 in all three attempts, and no tool moved it. A3 held a 1 mm edge break on
every part and still scored 6, because each subsystem had its own shape (R3 #4: "a kit of boxes"). Decide DP1, DP2
and DP4 at the plan checkpoint and write them into the design log, before you model the first visible part.

**DP1. Declare one radius and chamfer set, and use only that set.** In `params.py`, declare one edge break
(`EB = 1.0`), at most two corner radii (for example `R_S = 6`, `R_L = 16`) and one chamfer angle. Every
`geom.bevel`, `rrect` and chamfer cut takes a name from the set, never a literal. A1 had edge breaks of 0.6-1.5 mm
and radii of 4-16 mm (R1 #17). A2 moved to 1.0 mm and R6 "throughout" (R2 prev #17), and A went from 5 to 6.
*Enforced by:* reviewer (grep the params).

**DP2. Build arms, housings and shrouds from one section.** Write one profile function from the set: the declared
radius plus the chamfer, as D3's `pod_chamfer_cut` did for the pod. Extrude every arm, servo housing and shroud from
that function. You may scale it, but don't restyle it. Close arms into capped sections, not flat plates. R2 #10 and
R3 #4 name the same failure: a square base, a plain Ø224 disc, thin plate arms, a boxy servo housing and a feeder
box, each in its own shape. R3's fix: "one section and corner treatment (the pod's chamfer plus R6), for example
closed terracotta-capped arms". *Enforced by:* reviewer.

**DP3. Continue lines across parts.** Where two parts meet in a standard view, put the joint on a line that carries
on: a shared height, one chamfer running through both parts, or a cover that "continues the right-arm profile" (R1
#16). To close a gap, extend one part until it meets the other. Don't leave a step. Two cable exposures were gaps
at joint lines: the bonnet top had to be raised to the plate (R2 #8), and the bonnet skirt had to reach into a rim
notch (R3 #7). *Enforced by:* reviewer (rubric "parting lines aligned"). cadcheck `cables` exposure catches the gaps
that show a wire.

**DP4. Give each colour one role.** `pla_a` (warm grey) is structure. `pla_b` (terracotta) has one role, which you
state in the design log: for example the covers and shrouds that hide purchased parts, or the moving launcher stage.
A part takes the accent only if it has that role. Use the palette names, not RGBA tuples. R1 praised the two-colour
palette and asked for a terracotta shroud "sharing the guard's outline". In A3, R3 #4 lists terracotta on three
unrelated boxes (the pod, the tilt-servo housing and the feeder box), so the accent marked shapes, not a function.
*Enforced by:* reviewer (rubric "two PLA colours used to mean something").

**DP5. Hide hardware, wires and purchased parts, and size every window.** The standard views show no wire, PCB
edge, motor can, nut or screw tip.
- Shroud purchased parts (DP2), except the faces the user touches: battery, USB and switch.
- Counterbore visible screw heads (`features.screw_hole(sink=...)` or `head="csk"`).
- Recess adjusters into the part: a flush thumbwheel, not jack nuts under the pod.
- Cut every opening to what passes through it plus 2 mm, and give it a chamfered lead-in frame.

Evidence: R1 #16 (motor can, leads, PCB edge); R2 #8 and #9 (a bare bus, jack nuts); R3 #7 (8 mm of bundle in a
notch) and R3 #8 (a battery window up to z 89 that shows the adapter nuts; the fix was "pack outline plus 2 mm").
FINDINGS: A2-F8, A2-F9, A3-F7, A3-F8. *Enforced by:* cadcheck `cables` exposure, and `fasteners` stand-off,
protruding thread and nut visibility. The reviewer checks window size.

**DP6. Keep the masses compact around the main axis.** In plan view at the home pose, keep each subsystem within
about 60 mm of the pan axis. Put tall or heavy items, such as the hopper and servo boxes, over the axis, not behind
it or outboard of it. Size plain elements to their job: R3 asked for the Ø224 turntable to step down to about Ø180.
The servo box hung 50 mm outboard of the right arm (R1 #16). The hopper sat 45 mm behind the pan axis (R2 #10), and
its edge sat 118 mm behind it (R3 #4; the fix was "within about 60 mm"). *Enforced by:* reviewer. Measure it with
`cad q model.blend list 'PRT_*'` (world bounding boxes) and the CG rows from `stability`.

**DP7. Make every visible cut a deliberate feature.** If a clearance cut shows in a hero view, make it a full-width
chamfer at the declared angle, or a framed opening. An opening the payload leaves through gets a lip. R1 #16 flagged
the sweep-cut V-notch (fix: "one deliberate 45 deg chamfer that runs the full pod width"). R1 #17 flagged the
"plain rectangular hole" muzzle (fix: "a short flared lip"). The rubric caps A at 6 for any unfinished element.
*Enforced by:* reviewer.

## Mechanism

These are recurring classes from the FINDINGS recurrence tables. `footguns.md` names the mistake; each principle
here says what to design instead.

**DP8. A fix is a new part, so give it its own checks.** In A3, each fix brought a new problem. The leaf spring that
made the nip compliant (A2-F4) was printed across its layers (A3-F2). The nuts moved out of the battery envelope
(A2-F5) ended up in its slide path (A3-F3). When a fix adds or moves a part, add the entry for its class in the same
edit: a spring gets `flexures`, and a nut moved near a purchased part gets `slide_out`. Then run the full `cad check`,
not `--only`. *Enforced by:* cadcheck, once the entry exists.

**DP9. Make consumables and adjusters reachable in place.** Put tape, shims, wheel clamps and the gap adjuster
behind a cover that comes off with the machine assembled, at the pose the BOM states. Fix the cover with 2 screws or
a hand-turned thumbwheel, so no wrench is needed. A tape change on A1 took a 15-screw teardown (R1 #6, A1-F6). A3's
nip cover has 2 reachable screws and a thumbwheel you turn by hand (R3 prev #7). *Enforced by:* cadcheck `service`
ops for access. The reviewer counts teardown screws.

**DP10. Locate by construction, from the datum that matters.** Centre a magnet, sensor or wheel with a spigot or
crush ribs on the shaft's own datum, never by eye and never off a neighbouring bore. A1 had no jig (A1-F7). A2's jig
referenced the nacelle bore, giving a worst case of 0.55-0.75 mm against a 0.3 mm limit (A2-F7). A3 fixed it with a
Ø7.8 spigot in the motor's access hole (R3 prev #6). *Enforced by:* cadcheck `stacks` (you write the chain).

**DP11. Stop every limited joint in plastic.** Give each joint with a range a printed hard stop just past the
firmware limit, and model the stop so the sweep tests it. A1 had 0.21 mm of clearance at 45° and contact at 46°
(A1-F5). A2's printed stops at -3° and +46° fixed it (R2 prev #5). *Enforced by:* cadcheck `interference` with
overtravel, and `clearance`.
