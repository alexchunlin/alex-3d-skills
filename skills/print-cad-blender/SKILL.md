---
name: print-cad-blender
description: Parametric, 3D-printable assemblies in headless Blender with cadlib, checked by cadcheck. Use when designing or revising printed parts or assemblies in Blender (bpy), or when checking, measuring, sectioning or rendering a .blend for printability, interference, fastener access or joint clearance.
---

# Print CAD in Blender

`<skill>` below is this folder. Tools live in `<skill>/scripts/`:

| Tool | Does |
|---|---|
| `cadlib/` | geometry + Manifold booleans (`geom`), print features (`features`), assembly conventions (`asm`), STL export (`export`), renders (`render`) |
| `cad build build.py -- args` | run a build script headless |
| `cad check model.blend checks.json` | every check below, JSON evidence plus a 40-line summary, about 2-40 s |
| `cad q model.blend <cmd>` | one measurement: `dist`, `sweep`, `ray`, `inside`, `list`, `section`, `render` |
| `cad sheet stl_dir out.png` | all STLs in print orientation on one image |

Blender starts in 0.7 s, so run these as often as you like; Blender time was 2.3 of 64 min in the attempt that motivated this skill. Wall time goes on long single generations, so work in small steps.

## Workflow

1. **Plan checkpoint (first 10 minutes).** Read the brief and `<repo>/components/*.json` for purchased-part dimensions. Write the plan to the design log before modelling: world frame, subsystems, joints with ranges, the load path, the feed or payload path, the assembly order. Done when the log has a section per subsystem with its key dimensions. The killed attempt-0 designer lost 44 minutes because nothing reached disk.
2. **Scaffold.** Copy `<skill>/templates/project/` into the project (`build_assembly.py` plus one module per subsystem under `parts/`, and `checks.json`). Each subsystem module is a few hundred lines that you edit in place. Writing one 80 KB script in a single generation took 5.4 min, and string-replace edits on it broke.
3. **Build one subsystem at a time.** For each one: model it with cadlib, then `cad build`, then `cad check`. Fix every **fail** before starting the next subsystem, and append one line to `progress.md` (subsystem, check summary, time). Done when that subsystem has zero fails.
   - Place every screw with `features.screw_hole(at, into, ...)` and `asm.fastener(name, at, into, ...)` using the **same** `at`/`into`. `at` is the head's bearing face; `into` is the direction the shank travels.
   - Declare each joint with its real range (`asm.joint(..., lo, hi)`), and declare every designed running fit, thrust face and assembly step in `checks.json`. cadcheck fails anything undeclared, by design.
   - Model the payload path, then add a `drop_tests` entry with the landing window it must hit (`"mode": "slide"` when the payload slides down a chute).
   - Model nuts as `asm.nut()` (or name them `FST_*nut*`): cadcheck pairs each bolt with the nut on its axis and fails a bolt that stops short (A2-F3).
   - Turn every motion, timing or service claim into a check before it goes in the BOM: indexers into `index_tests`, "adjust without disassembly" into `service`, "comes off at tilt 45" into `slide_out`. In attempt 2 the double-feeding index and the "no disassembly" gap adjustment were prose nobody had run (A2-F2, A2-F6).
4. **Renders.** Make preview renders only after checks pass (`render.view_set`, 960 px). Then look at sections through the critical interfaces (`cad q ... section`, with `--lentil` markers for the payload). Render the final 1600 px+ set once, at the end (`CAD_RENDER_FINAL=1`).
5. **Report evidence, not verdicts.** Hand over the `cadcheck.json` summary: fails, warns, `coverage`, `not_checked`. Every claim in the design log cites a check row or a `cad q` line. Attempt 1 reported "zero interference" while fasteners and cables were excluded and contacts ignored.

## Conventions (cadcheck and the web viewer depend on these)

- World X right, Y forward (front/muzzle), Z up, units mm, origin on the table under the main axis.
- Collections `Printed`, `Purchased`, `Fasteners`, `Cables`. Names are `PRT_`, `BUY_`, `FST_`, `CAB_` plus the part name.
- Moving links hang under `PIV_<joint>` empties made by `asm.joint`. Mesh data is baked in world coordinates at the home pose. Things that rotate with a shaft (rotor, magnet, wheel) belong to the shaft's joint, not the stator's.
- Every `PRT_` carries `stl`, `print_rot`, `orient`, `supports` and `infill` (`asm.part` refuses without them). Every `BUY_` carries `mass_g` and `src`.
- `asm.write_manifest()` writes parts, joints, fasteners, cables, features and parameters, so a reviewer reads JSON instead of your script.

## What cadcheck covers

parts (manifold, bed fit, sloped overhang, bridge span, wall probe, bed contact) · interference over **all four** collections, swept over the joints between each pair plus 2.5° of overtravel · contacts across a joint · clearance below 0.5 mm · fasteners: head buried, thread engagement, bolt-to-nut engagement, shanks or nuts inside purchased parts, head stand-off, protruding thread, access with a straight bit or an L-key at the step it is installed (and at the wheel angles you can turn it to) · service ops on the built machine · drop paths (straight rays or fall-and-slide) with angle windows · indexer timing · slide-out of a part or a group · distances (nearest, or a gap along a ray, with payload squeeze) · tolerance stacks · CG tip angle · cable length and exposed cable.

It also lists what it did **not** check (teardown count, cable bend radius, wrench access to nuts, aesthetics beyond exposure). Cover those with sections and the design log. A full run on the 119-object attempt-2 assembly takes 58 s; use `--only fasteners,service` while iterating.

## Reference

- `reference/api.md`: cadlib functions and their arguments. Read it before writing the first part.
- `reference/checks-config.md`: `checks.json` schema (joints, fits, allow, assembly_order, service, drop_tests, index_tests, slide_out, distances, stacks, exposure, masses). Read it when cadcheck flags something you designed on purpose.
- `reference/footguns.md`: the attempt-1 and attempt-2 mistakes and the check that catches each. Read it before declaring a subsystem done.
- PLA rules (pilot 2.5, clearance 3.4, nut 5.7 AF, fits, bridge 25 mm): `cadlib/features.py RULES`.
