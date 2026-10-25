# Task: real printability checks and a slicer tool for the modeler

## Why
v2 shipped claiming "no supports" for every part. When the user questioned it, an orchestrator check found **2 parts that need support and that cadcheck missed**:
- `jar_valve`: 3 bayonet tabs, about 13 x 10 mm, start 2.1 mm above the bed, so they're cantilevered.
- `feeder_cover`: the screw ear at the top is a 10.5 mm cantilever at z 32.

cadcheck missed them for four reasons:
- `check_parts` treats every flat downward face as a "ceiling" and measures its span with an inscribed circle, but never checks whether the region is **anchored on two sides (a bridge) or one side (a cantilever needing support)**.
- It only warns, and only above 150 mm² total.
- It never detects regions that start in mid-air.
- It runs on the model with `print_rot` applied, not on the **exported STLs** the user actually slices.

The orchestrator's quick checker and its evidence are in `docs/evidence-v2-supports/`: `printcheck.py`, `result.json`, the `render_flags*.py` scripts and their renders. Read them. That checker has known **false positives**:
- Bottom-edge chamfers and countersinks that touch the bed: `beam`, `flywheel` flange ring, `nip_cover`.
- Window tops in vertical walls that are real 16 mm bridges: `base_shell`.
- A pocket roof whose walls have T-junction topology, so edges weren't shared: `feeder_crown`.
- Its span estimate, the bbox minimum: `nacelle`, `flywheel`.

These are ground truth. A good tool flags `jar_valve` and `feeder_cover`, and not the others.

## Build
1. **Layer-based support analysis on exported STLs**, with no new dependencies; Blender's bundled numpy is fine.
   - Slice each STL at layer height (0.2 mm), in raster or polygons.
   - Per layer, find area not supported by the layer below, dilated by the self-supporting overhang allowance (45°, so 0.2 mm per 0.2 mm layer).
   - Classify the unsupported area:
     - **bridge**: touches supported material on two or more opposite sides, with its span;
     - **cantilever**: one side, with its overhang length;
     - **island**: no support at all.
   - **Fail** islands and cantilevers beyond a small allowance on parts marked `supports: no`. Warn on bridges above 25 mm.
   - Report locations in print and world frames, and an optional render with the flagged areas in colour.
   - Integrate it into `cadcheck` (`parts` rows) and `cad q`, and add a standalone `cad printcheck <stl_dir|stl>`.
   - Prove it on the v2 STLs at `/Users/alxchunlin/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/v2/stl/` against the ground truth above, plus planted-bug fixtures, and add it to `verify_all.sh`.
2. **A slicer tool, `cad slice`,** so the modeler can confirm with a real slicer: support needed or not, time, filament, and warnings. **Safety requirements** (the user saw crash pop-ups when an agent ran the Bambu Studio CLI with hand-built profiles):
   - It never sends anything to a printer, never needs the network, and never reads or writes the user's slicer config (`~/Library/Application Support/BambuStudio`, OrcaSlicer, PrusaSlicer). Use an isolated temp data dir and profiles vendored or generated into this repo.
   - **It must not produce crash dialogs.** Detect which slicers are installed:
     - PrusaSlicer, OrcaSlicer: prefer whichever has a stable headless CLI.
     - Bambu Studio: is installed. Its CLI crashed on flattened profiles; see `docs/FINDINGS.md` and the test-rig notes in `/Users/alxchunlin/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/test-prints/launch-rig/`.
   - Run a **single** guarded smoke test per slicer. If one crashes, mark it unusable in a local cache and never retry it automatically.
   - If no slicer works, `cad slice` says so plainly and the layer check from step 1 is the authority.
   - Don't install software. If a slicer would make this much better, write the recommendation, with the exact install command for the user to run, in STATUS.md.
   - Parse the slicer output: G-code header estimates, support detection with supports disabled, warnings.
3. **Update the skill docs.**
   - `SKILL.md` and `footguns.md`: "no supports" is a claim that needs `cad printcheck` (and `cad slice` when available) evidence.
   - The reviewer checklist: printability is re-run on the exported STLs.
   - `templates/cad-loop.workflow.js`: the finish step runs both.
4. **Record** the miss in FINDINGS (a "v2 post-freeze" section) with the evidence, update STATUS, and commit only after `verify_all.sh` passes.

## Scope rule change
The earlier blanket rule ("never run any slicer binary") is replaced by: **slicers may only be run through `cad slice`, with the safety rules above.** Never contact printers or the network, and never touch the user's slicer settings.
