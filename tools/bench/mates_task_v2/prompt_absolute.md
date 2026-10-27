You are the designer for a small 3D-printed assembly. Use the print-cad-blender skill ({SKILL}/SKILL.md) and
its tools (`{SKILL}/scripts/cad`). Read the brief at {KIT}/brief.md; the purchased-part data and placeholders are in
{KIT} (`components.json`, `kit_parts.py`: put {KIT} on sys.path to import it). Work only in {PROJECT}.

Template: copy {KIT}/../mates_task/template_absolute/ to {PROJECT}/blender/ and build from it. It places each part in
world coordinates: build each part where it sits in the assembly, declare joints with `asm.joint` in `params.joints()`,
and place screws with `features.fastener_joint(name, size, at, into, parts, ...)`.

Build with `cad build {PROJECT}/blender/build_assembly.py`, check with `cad check {PROJECT}/blender/model.blend
{PROJECT}/blender/checks.json`, and stop when the brief's "Done when" holds. Report the final cad check summary
(fails, warns) and the time you spent.
