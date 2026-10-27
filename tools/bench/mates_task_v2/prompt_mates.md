You are the designer for a small 3D-printed assembly. Use the print-cad-blender skill ({SKILL}/SKILL.md) and
its tools (`{SKILL}/scripts/cad`). Read the brief at {KIT}/brief.md; the purchased-part data and placeholders are in
{KIT} (`components.json`, `kit_parts.py`: put {KIT} on sys.path to import it). Work only in {PROJECT}.

Template: copy {SKILL}/templates/project-mates/ to {PROJECT}/blender/ and build from it. It places parts through mate
connectors (`cadlib.mates`): model each part in its own frame, name a connector on each mating face, declare one mate
per interface (rigid, fastened, revolute, prismatic) and let `mates.assemble` place the parts, make the joints and
cut the screws. Purchased parts take their connectors from components.json (`mates.from_component`).

Build with `cad build {PROJECT}/blender/build_assembly.py`, check with `cad check {PROJECT}/blender/model.blend
{PROJECT}/blender/checks.json`, and stop when the brief's "Done when" holds. Report the final cad check summary
(fails, warns) and the time you spent.
