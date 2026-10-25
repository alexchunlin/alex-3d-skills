---
name: print-cad-blender
description: Parametric, 3D-printable assemblies in headless Blender with cadlib, checked by cadcheck. Use when designing or revising printed parts or assemblies in Blender (bpy), or when checking, measuring, sectioning or rendering a .blend for printability, interference, fastener access or joint clearance.
---

# Print CAD in Blender

`<skill>` below is this folder. Tools live in `<skill>/scripts/`:

| Tool | Does |
|---|---|
| `cadlib/` | geometry + Manifold booleans (`geom`), print features (`features`), assembly conventions (`asm`), STL export (`export`), renders (`render`) |
| `cad build build.py -- args` | run a build script headless. A script that raises exits non-zero and prints `cad: BUILD FAILED`; `cad check` warns when sources are newer than the blend |
| `cad check model.blend checks.json` | every check below, JSON evidence plus a 40-line summary, about 2-40 s |
| `cad q model.blend <cmd>` | one measurement: `dist`, `sweep`, `ray`, `inside`, `list`, `section`, `render`. `cad q` alone prints the commands |
| `cad py -c "import params as P; print(P.X)"` | Python with bpy and cadlib, run from `blender/`: evaluate params or geometry helpers without stubbing bpy |
| `cad rows cadcheck.json [REGEX]` | one line per check row (or `manifest.json` part), no Blender: grep the report instead of writing a `json.load` snippet. v2 A3's agents wrote them in 67 bash calls, and 6 died on a guessed key |
| `cad bom BOM.md manifest.json` | the BOM's fastener table against the model: size, length, head, count, stock lengths |
| `cad sheet stl_dir out.png` | all STLs in print orientation on one image |

Blender starts in 0.7 s, so run these as often as you like; Blender time was 2.3 of 64 min in the attempt that motivated this skill. Wall time goes on long single generations, so work in small steps.

## Workflow

1. **Plan checkpoint (first 10 minutes).** Read the brief and `<repo>/components/*.json` for purchased-part dimensions. Write the plan to the design log before modelling: world frame, subsystems, joints with ranges, the load path, the feed or payload path, the assembly order. Done when the log has a section per subsystem with its key dimensions. The killed attempt-0 designer lost 44 minutes because nothing reached disk.
2. **Scaffold.** Copy `<skill>/templates/project/` into the project (`build_assembly.py` plus one module per subsystem under `parts/`, and `checks.json`). Each subsystem module is a few hundred lines that you edit in place. Writing one 80 KB script in a single generation took 5.4 min, and string-replace edits on it broke.
3. **Build one subsystem at a time.** For each one: model it with cadlib, then `cad build`, then `cad check`. Fix every **fail** before starting the next subsystem, and append one line to `progress.md` (subsystem, check summary, time). Done when that subsystem has zero fails, and every warn on its objects is either fixed or listed under `accepted_warns` with a reason. v2 A1 finished at 0 fails and 34 warns, and three of the reviewer's issues were in those warns: a 0.94 mm wall at a self-tap pilot, a 0.40 mm magnet stack, and knife edges.
   - Place every screw with `features.screw_hole(at, into, ...)` and `asm.fastener(name, at, into, ...)` using the **same** `at`/`into`. `at` is the head's bearing face; `into` is the direction the shank travels.
   - Declare each joint with its real range (`asm.joint(..., lo, hi)`), and declare every designed running fit, thrust face and assembly step in `checks.json`. cadcheck fails anything undeclared, by design.
   - Model the payload path, then add a `drop_tests` entry with the landing window it must hit (`"mode": "slide"` when the payload slides down a chute).
   - Model nuts as `asm.nut()` (or name them `FST_*nut*`): cadcheck pairs each bolt with the nut on its axis and fails a bolt that stops short (A2-F3).
   - Turn every motion, timing or service claim into a check before it goes in the BOM: indexers into `index_tests`, "adjust without disassembly" into `service`, "comes off at tilt 45" into `slide_out`. In attempt 2 the double-feeding index and the "no disassembly" gap adjustment were prose nobody had run (A2-F2, A2-F6).
   - "Removable" means the whole path, not the rest pose. A `slide_out` sweeps the part out and counts fasteners in the way. In attempt 3, checks.py passed the battery at rest, but it slid through two adapter nuts (A3-F3).
   - Every printed spring, flexure or snap arm gets a `flexures` entry: the beam must lie in the layer plane. Attempt 3 printed its nip leaf spring standing up, so the bending stress ran across layer bonds (A3-F2).
   - Run payload tests at the **hard stops**, not just the firmware limits, and keep the flattest slide 5° above the stall angle. Attempt 3 fed 29/29 at tilt 45, but over a 21° slide with a 20° stall limit (A3-F1).
   - **Every adjuster gets tested at both ends of its travel:** drop tests, distances and service, not just the home setting. Give it real hard stops in the model. v2 A1's nip hinge was tested at home only. At one end the drop stalled, and at the other the hood hit the body (V2A1-F1). cadcheck now warns when a drop test holds a joint at home that moves a wall the payload touches.
   - **A pocket, slot or chute sized for the payload gets `payload_fit` rows at the payload's size limits:** two payloads must be blocked at the *smallest* size, and one must fit at the *largest*. v2 A1 and A2 both shipped a feeder pocket that seated two edge-on candies, and three agents wrote their own lentil probes (V2A2-F2).
   - **Write payload numbers as params expressions at the declared extremes**, not typed-in nominals: `"min": "=MM_T[1] + TAPE_T"`, `"size": ["=MM_D[0]", "=MM_T[0]"]`. v2 A3 declared candies up to 7.5 thick, sized the nip gap row for the nominal 7.0, and the reviewer's 7.5-candy row failed: the one major left (V2A3-F1).
   - **A gap the payload passes through is checked over the whole passage:** a `distances` ray with `"sweep"` (turned about the wheel axis over the gripped arc, or slid down a chute) reports the worst station and the profile. v2 A4's full-lift nip rows sat at BDC and passed at 8.28; the reviewer swept the entry arc and found 7.50 at psi 80, the one major left (V2A4-F1). Asserts in params (a `gap_bdc()` over ±2°) get the same rule.
   - **A gate, drawer or plunger is a `prismatic=True` joint**, so its open state is in every sweep. A detent that rides it goes in the slide row's `flex` with a bound in mm³, not in `ignore`. v2 A2 and A3 left the gate's open state unchecked and the reviewer moved it by hand (V2A3-T6).
   - **Conductors that run on through several cable routes get a `cable_chains` row** with the one purchased lead. v2 A3's 150 mm encoder lead "continued in the bundle" for 430 mm that no BOM row bought (V2A3-F3).
   - Turn "reachable through the slot" or "visible through the window" into a `sightlines` row, and "stops at 52" into a `slide_out` row with `"expect": "blocked"`. A `cad q ray` line proves it once; a row re-proves it on every run (V2A2-T4).
   - Each **hard stop** gets a `distances` row at the joint limit with `max` about 0.1, naming the two parts that touch. In v2 A2 the leaf-lift limit said "the stud bottoms on the cover", but the stud was 2.36 mm clear there (V2A2-F1).
   - A `fits` rule with `contact: true` covering a thrust or stop face **and** a journal needs `contact_normal`. Otherwise the journal is never measured (V2A1-V4).
   - For an adjuster modelled at one setting (for example a thumbwheel on a stud), `carry` it onto the joint it rides on. List a captive stud under `fasteners.captive`. Don't `allow` its clashes (A3-V1).
4. **Renders.** Make preview renders only after checks pass (`render.view_set`, 960 px). Then look at sections through the critical interfaces (`cad q ... section`, with `--lentil` markers for the payload). Render the final 1600 px+ set once, at the end (`CAD_RENDER_FINAL=1`).
5. **Report evidence, not verdicts.** Run `cad bom` on the BOM before hand-off (v2 A3's BOM gave the stud as M3 x 20 hex while the model had M3_cap x 16, V2A3-F6). Hand over the `cadcheck.json` summary: fails, warns, `coverage`, `not_checked`. Every claim in the design log cites a check row or a `cad q` line. Attempt 1 reported "zero interference" while fasteners and cables were excluded and contacts ignored.

## Conventions (cadcheck and the web viewer depend on these)

- World X right, Y forward (front/muzzle), Z up, units mm, origin on the table under the main axis.
- Collections `Printed`, `Purchased`, `Fasteners`, `Cables`. Names are `PRT_`, `BUY_`, `FST_`, `CAB_` plus the part name.
- Moving links hang under `PIV_<joint>` empties made by `asm.joint`. Mesh data is baked in world coordinates at the home pose. Things that rotate with a shaft (rotor, magnet, wheel) belong to the shaft's joint, not the stator's.
- Every `PRT_` carries `stl`, `print_rot`, `orient`, `supports` and `infill` (`asm.part` refuses without them). Every `BUY_` carries `mass_g` and `src`.
- `asm.write_manifest()` writes parts, joints, fasteners, cables, features and parameters, so a reviewer reads JSON instead of your script.

## What cadcheck covers

parts (manifold, bed fit, sloped overhang, bridge span, wall probe, bed contact) · interference over **all four** collections, swept over the joints between each pair plus 2.5° of overtravel · contacts across a joint · clearance below 0.5 mm · fasteners: head buried, thread engagement, bolt-to-nut engagement, shanks or nuts inside purchased parts, head stand-off, protruding thread, access with a straight bit or an L-key at the step it is installed (and at the wheel angles you can turn it to) · service ops on the built machine · drop paths (straight rays or fall-and-slide) with angle windows · indexer timing · slide-out of a part or a group · distances (nearest, or a gap along a ray or a swept ray, with payload squeeze; a ray that lands on another face than at home warns), with `=EXPR` values from the params · payload fit (two payloads blocked, one fits, with the size margin) · sightlines (first hit along a finger, tool or view ray) · assembly config (objects in no step, step labels whose screw size disagrees with the model) · tolerance stacks · springs and snap arms against print orientation (`flexures`) · CG tip angle · cable length, cable chains and connector-less junctions, exposed cable and visible nuts · stocked screw lengths · prismatic (slide) joints in every sweep.

It also lists what it did **not** check (teardown count, cable bend radius, wrench access to nuts, aesthetics beyond exposure). Cover those with sections and the design log. A full run on the 119- to 122-object attempt-2 and attempt-3 assemblies takes 58-64 s; use `--only fasteners,service` while iterating.

## Reference

- `reference/api.md`: cadlib functions and their arguments. Read it before writing the first part.
- `reference/checks-config.md`: `checks.json` schema (joints, carry, fits and contact_normal, allow, captive fasteners, assembly_order with nested bench merges, service, drop_tests, index_tests, slide_out (with expected stops), distances, payload_fit, sightlines, stacks, flexures, exposure, masses, accepted_warns) plus `--only`/`--overlay`. Read it when cadcheck flags something you designed on purpose, **before** reading cadcheck.py: v2 A1 agents spent minutes in the source on bench merges and slide semantics.
- `reference/footguns.md`: the mistakes from attempts 1-3 and the check that catches each. Read it before declaring a subsystem done.
- PLA rules (pilot 2.5, clearance 3.4, nut 5.7 AF, fits, bridge 25 mm): `cadlib/features.py RULES`.
