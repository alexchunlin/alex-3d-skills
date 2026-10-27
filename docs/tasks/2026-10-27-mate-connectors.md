# Task: mate connectors, so parts are placed by their interfaces, not by world coordinates

Branch `feat/mate-connectors`, worktree `.claude/worktrees/mate-connectors`. PR target `next` (the coordinator opens it).

## Why
- Designers compute every part's world placement by hand (trig in a build script). That is where the spatial errors
  come from: in the 2026-10-27 CADGenBench pilot, agents got cross products, winding, mirrored views and a 180° view
  wrong; in the mm-launcher and push-assist loops the reviewers' majors are mostly placement and access problems.
- The user designs robots and wants to stay the designer. Interfaces are data the designer already has when modelling
  (this bolt hole goes to that bolt hole; this servo spline is that arm's pivot). Store it once, as data, and let code
  place the parts and cut the features. Onshape's mate connectors are the model: a named frame on a part, and a mate
  between two frames.
- The mate table doubles as a searchable record of every interface (what mates with what, how, which fastener, which
  fit), cheap for an agent to grep instead of re-deriving geometry.
- **Adoption is the risk, not the code.** Push-assist FINDINGS ("Push-assist loop (2026-10-26/27)"): SKILL.md told
  designers to use `features.fastener_joint`, `cadlib.route` and `cadlib.blend`; they read those lines and the build
  never called any of them. So the project template must place parts *through* mates, not offer mates as an extra.

## Prior art: read the source before designing (CLAUDE.md "Prior art before new code")
- In this repo: `cadlib/asm.py` (`joint`, `part`, `fastener`, `manifest`), `cadlib/joints.py` (spec/read/apply,
  couplings), `cadlib/features.py` `fastener_joint` (measures the stack, picks the length, cuts every part),
  `cadcheck.py` sweeps and `insertion`, `docs/FINDINGS.md`, `skills/print-cad-blender/reference/*.md`.
- build123d's joint API, which is this idea in Python: `/tmp/cgb-venv/lib/python3.12/site-packages/build123d/joints.py`
  (`RigidJoint`, `RevoluteJoint`, `LinearJoint`, `CylindricalJoint`, `BallJoint`, `connect_to`). Copy its API shape
  where it fits; do not add build123d as a dependency of cadlib.
- CadQuery assembly constraints (solver based) and Onshape mate connectors, as concepts only.
- Write what each can do and why it is or isn't enough into the design doc's "Why not the existing code" section.

## Build (in cadlib, Blender/mathutils only, no new dependencies)
1. **Connector**: a named frame on a part (origin, z axis, x axis), stored on the object so it moves with it, with an
   optional **pattern** in minimal form: `rect(px, py)`, `circle(pcd, n, a0)`, `line(pitch, n)`, or explicit points;
   and optional hole spec (`"M3"`). A purchased part's connectors come from its datasheet once (components.json).
2. **Mate**: between two connectors, kind `rigid | fastened | revolute | prismatic`, with fit metadata
   (`press | slip | clearance | snap`), fastener style for `fastened` (as `fastener_joint`), and limits for
   revolute/prismatic.
3. **Assemble**: place every part from one grounded part through the mate tree (matrix composition; loops are out of
   scope and must raise clearly). Revolute/prismatic mates create the `PIV_*` joint through `asm.joint` so every
   existing sweep, held-pose and insertion check works unchanged. Fastened mates call `fastener_joint` once per pattern
   point. A pattern mismatch between the two connectors (count, pitch, size) **fails loudly** with both specs printed.
4. **Mate table**: stored in the .blend and the manifest; `cad mates <blend|manifest> [REGEX]` prints one line per mate
   (like `cad rows`), no Blender needed for the manifest form.
5. **Template**: the project template's build places parts only through `assemble`; update SKILL.md and api.md (short;
   say what to do, not history). Note: `api.md` line 8 says angles are degrees but `geom.circle/arc/revolve` take
   radians; fix that line while there.

## Prove
- Unit tests for the solver (frames, chains, flips, pattern mismatch), in `tools/verify.d/`.
- Rebuild one existing example with mates (`examples/demo-turret` or `examples/blend-bracket`) and show cadcheck gives
  the same results as the absolute-coordinate build (same rows, same fails/warns), plus a planted-bug variant (a
  pattern mismatch) that fails.
- Add to `tools/verify_all.sh`; run it once at the end, detached via `setsid` (nohup alone gets killed), and report the
  pass count. Other agents may be running verify_all; don't start more than one yourself.

## Evaluation kit (build it; do NOT run agent A/B yourself, the coordinator runs it)
Write `tools/bench/mates_task/`: a small assembly brief a designer agent can do in ~20 min, e.g. a deck, a servo
(datasheet dims), a horn-driven arm on the servo spline, a PCB with a 4-hole pattern on standoffs, a lid with 4 screws.
Include the purchased-part data, an acceptance `checks.json`, and a scorer script that reports: cadcheck fails, any
part off its intended interface by > 0.2 mm or 1°, and lines of build code. Two prompt variants: `absolute` (today's
template) and `mates` (new template). Keep the brief identical apart from the template.

## Rules
- Work and commit only on `feat/mate-connectors` in this worktree. Don't push, don't open PRs, don't touch `main`,
  `next`, the pin worktree (`~/code-stuff/alex-3d-skills-pin`) or any other worktree.
- Don't spawn sub-agents. No network except pip if truly needed (say why).
- Commit messages follow the repo's style (`git log`), ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Report back (short)
What you built (files), the "Why not the existing code" finding, the demo rebuild comparison, verify_all result, the
eval kit's location and how to run it, and anything you'd change in the design after building it.
