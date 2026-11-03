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
