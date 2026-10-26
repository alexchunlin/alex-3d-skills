# Design principles: form language

Read this when you choose the form language for a new project. `footguns.md` lists the mistakes and the check that
catches each one; the rubric's Aesthetics items say what the reviewer scores. This page says what to build so that
those items hold together.

Evidence is a review issue. "R2 #10" is issue 10 of the attempt-2 review (`mm-launch-hw/renders/attempt-2/review.md`).
R3 issues are numbered by rank, so "R3 #4" is the one R3 labels "A1". No tool checks form language: only the
reviewer does. Look at `iso` and `iso_front_left` yourself before you hand over.

Form language capped Aesthetics at 5-6 in all three v1 attempts, and no tool moved it. A3 held a 1 mm edge break on
every part and still scored 6, because each subsystem had its own shape (R3's Scores section: "a kit of boxes").

**DP1. One declared detail set.** Declare `EB` and `CR` in `params.py`, as the project template does, and pass them
to every `G.bevel` and `G.rrect`; grep for them.

**DP2. Build arms, housings and shrouds from one section.** Write one profile function from the declared radius plus
one chamfer, and extrude every arm, servo housing and shroud from it. You may scale it, but don't restyle it. Close
arms into capped sections, not flat plates. R2 #10 and R3 #4 name the same failure: a square base, a plain Ø224
disc, thin plate arms, a boxy servo housing and a feeder box, each in its own shape. R3's fix: "one section and
corner treatment (the pod's chamfer plus R6)".

**DP3. Continue lines across parts.** Where two parts meet in a standard view, put the joint on a line that carries
on: a shared height, one chamfer running through both parts, or a cover that "continues the right-arm profile" (R1
#16). To close a gap, extend one part until it meets the other. Don't leave a step. Two cable exposures were gaps
at joint lines: the bonnet top had to be raised to the plate (R2 #8), and the bonnet skirt had to reach into a rim
notch (R3 #7). cadcheck `cables` exposure catches the gaps that show a wire.

**DP4. Give the accent colour one role**, and write that role in the design log. A part takes `pla_b` only if it
has that role. In A3 terracotta sat on three unrelated boxes (the pod, the tilt-servo housing and the feeder box), so
it marked shapes, not a function (R3 #4).

**DP5. Make every visible cut a deliberate feature.** If a clearance cut shows in a hero view, make it a full-width
chamfer or a framed opening. An opening the payload leaves through gets a lip. R1 #16 flagged the sweep-cut V-notch
(fix: "one deliberate 45 deg chamfer that runs the full pod width"). R1 #17 flagged the "plain rectangular hole"
muzzle (fix: "a short flared lip"). The rubric caps A at 6 for any unfinished element.
