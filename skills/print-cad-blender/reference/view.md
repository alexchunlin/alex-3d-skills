# cad view: one offline HTML page of a checked assembly

```sh
cad view model.blend cadcheck.json -o out.html          # the report is optional
cad view model.blend -o out.html --pose tilt=30,pan=45  # open at a pose (joint names with or without PIV_)
```

The page is one file with no network: three.js, the Draco decoder and the fonts are inlined. Anyone can open it from
a mail attachment or a chat and turn the model in a browser. It holds about 1 MB for the 178-object v2 launcher and
0.5 MB for the demo turret. The licence texts of what it inlines travel in the file. Nearly all of the turret's page is the viewer (three.js, the decoder, the fonts); the
launcher's geometry adds 0.5 MB.

What it shows:

- Every PRT_/BUY_/FST_/CAB_ mesh (by collection, else by name) in the blend's own material colours.
- A slider per PIV_ joint over its real range (degrees, or mm on a slide). A coupled joint follows its driver and
  shows the ratio. A continuous joint runs 0-360. A joint with no range stays at home, as cadcheck holds it. The pose
  maths are `cadlib.joints` (what cadcheck and `cad q` use), and checks.json `carry` is applied as cadcheck applies
  it. The report's own config (`joints`, `couplings`, `carry`) is used, or `--config checks.json`.
- With a report, every fail and warn in a side panel, with accepted warns marked and their reason. Clicking one lights
  its objects, ghosts the rest, sets every joint to the finding's pose (unlisted joints go home, as in cadcheck; a
  pose past a limit shows in yellow), marks its `at` points and overlap `region`, and frames the camera on them. The
  markers show only at that pose, because they are world coordinates there. Objects named in any fail get a red
  outline.
- Hover: name, role, joint, and the part's `orient`, `supports` and `infill` props. Clicking a part filters the list
  to its findings and jumps to its joint's slider.
- Explode (radial, about the assembly centre), x-ray, and a section plane on X, Y or Z.
  Keys: H home, F fit, X x-ray, S section, Esc clears the selection.

It refuses (exit 2) a report from another model: one where every name it uses is missing from the blend, or at least
3 names and 20 % are (the demo report on the v2 launcher misses 11 of 17). `--force` builds the page anyway with the
mismatch in a red banner. A few missing names (a stale config name cadcheck warns about) are flagged in the banner
and on each finding. So are a blend saved after its report and a report made from another blend path.

The geometry is Blender's glTF exporter with Draco at 14-bit positions (about 0.02 mm on a 300 mm part), so measure
with `cad q`, never from the page. To test a page: `node tools/verify.d/cad_view_browser.mjs out.html --shot s.png`
(headless Chrome; `--selftest` with a page built with `--selftest` compares the page's poses with Blender's).

The vendored files in `scripts/viewer/vendor/` (three.js 0.170.0 tree-shaken, Draco's glTF decoder, the Roboto
subsets, the alex-style tokens) are rebuilt by `scripts/viewer/vendor/build.sh`. It is dev-only and needs network
and npm. Their licences sit next to them.

# model.glb: the assembly for any glTF viewer

```sh
cad build blender/build_assembly.py -- --glb               # <out>/model.glb next to stl/ (Draco)
cad build blender/build_assembly.py -- --glb --no-draco    # raw meshes
cad build blender/build_assembly.py -- --glb --glb-report blender/cadcheck.json   # parts fly in along insertion
```

From a script: `export.write_glb(path, checks="checks.json", report=None, draco=True)` (it lives in `cadlib/gltf.py`).
For a blend with no build script, open it first: `cad py -c "import bpy; bpy.ops.wm.open_mainfile(filepath='m.blend');
from cadlib import export; export.write_glb('model.glb', checks='checks.json')"`.

- Every PRT_/BUY_/FST_/CAB_ mesh and PIV_ empty is a node with its own name, in the blend's hierarchy, under one root
  node `ROOT_zup_mm` (rotation -90 deg about X, scale 0.001): the scene is Z-up mm, glTF is Y-up m. Without the root a
  viewer read the v2 launcher as 433 m; with it, 0.245 x 0.433 x 0.300 m.
- A clip per driven joint, named after it: lo, hi, lo over 4 s (a continuous joint turns 360 and back), coupled joints
  following (v2a7's `PIV_feeder_pinion` turns in the `PIV_feeder` clip at -1.4667). Keys come from `cadlib.joints`
  (`values`, `world_at`) at 10 deg or less apart, so a viewer's interpolation stays on the joint's path. Each clip's
  `extras` lists the driver value per key. The checks.json `joints`/`couplings` overrides apply; `carry` does not.
- An `assembly` clip, 1 s per `assembly_order` step: a step's objects appear (scale 0 before) and fly home. The
  direction is the one the insertion check found free for that object (its `free_dir_vec` in a report given with
  `--glb-report`; it prints the report's path and time, and no report is ever picked up on its own), else away from
  the assembly centre as `render.exploded` draws it (fasteners, cables, merged groups, objects with no report row).
  Bench sub-assemblies are built in place, in listed order. Objects in no step are there throughout.
- Geometry is the exporter call cad view uses (`gltf.export`), with the blend's material colours. v2a7 (178 objects):
  0.88 MB with Draco, 7.0 MB raw, written in 0.6 s. As with the page, measure with `cad q`, not from the GLB.
