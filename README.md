# alex-3d-skills

Skills and tools for agent-driven, 3D-printable CAD in headless Blender. They were harvested from the
mm-launcher design/review loop, and the evidence behind every rule is in `docs/FINDINGS.md`. Current state is in `docs/STATUS.md`.

| Path | What |
|---|---|
| `skills/print-cad-blender/` | Skill for designers: conventions, workflow, `cadlib` (geometry, print features, assembly, export, renders), `cadcheck` (assembly-wide checks with joint sweeps, fastener access, drop tests), `cadq` (one-shot measurements), the `cad` wrapper, and a project template |
| `skills/cad-design-review/` | Skill for reviewers: check-first protocol, scoring anchors, evidence checklist |
| `templates/cad-loop.workflow.js` | Design/review loop for the Workflow tool: plan, then one build agent per subsystem, then finish, then review. Resumable. |
| `components/` | Purchased-part data with sources (`components.json`) and Blender placeholders |
| `tools/transcript/cc_transcript.py` | Digest Claude Code agent transcripts: time split, long generations, tokens, cache misses, Blender runs, images |
| `tools/verify_all.sh` | Re-proves everything (about 28 minutes, writes only under `/tmp/alex3d-verify`). `--changed [BASE]` runs only the sections and `tools/verify.d` scripts the change since `merge-base(BASE, HEAD)` affects (BASE defaults to `next`; `--dry-run` prints the plan); promoting `next` to `main` runs it all |
| `examples/` | `demo-turret` and `slide-gate` (clean and planted-bug builds); `mm-launcher-{a1,a2,a3,v2a1,v2a2,v2a3}` (check config and archived blend per attempt, plus the reviewer's missing rows as overlays) |

## Requirements

Blender 5.1+ at `/Applications/Blender.app` (or set `BLENDER`), python3, and node (for the workflow test only).
There are no pip dependencies.

## Install (manual; nothing here installs itself)

Link the skills into Claude Code:

```sh
ln -s ~/code-stuff/alex-3d-skills/skills/print-cad-blender ~/.claude/skills/print-cad-blender
ln -s ~/code-stuff/alex-3d-skills/skills/cad-design-review ~/.claude/skills/cad-design-review
```

Optionally, put the wrapper on PATH: `ln -s ~/code-stuff/alex-3d-skills/skills/print-cad-blender/scripts/cad /usr/local/bin/cad`.

To use the loop, copy `templates/cad-loop.workflow.js` and set `CONFIG.hw` and `CONFIG.subsystems` (or pass them as
Workflow `args`). To resume after a crash, pass `start_attempt` and `history`, or use `resumeFromRunId`.

Project template: copy `skills/print-cad-blender/templates/project/` to `<project>/blender/`. The build finds cadlib through
`CAD_SKILL` (default `~/code-stuff/alex-3d-skills/skills/print-cad-blender`).

## Quick use

```sh
S=~/code-stuff/alex-3d-skills/skills/print-cad-blender/scripts
$S/cad build my/blender/build_assembly.py -- --render
$S/cad check my/blender/model.blend my/blender/checks.json
$S/cad check my/blender/model.blend my/blender/checks.json /tmp/cc.json --only fasteners,service   # 2-13 s subsets while iterating
$S/cad check my/blender/model.blend my/blender/checks.json /tmp/cc.json --overlay my_rows.json        # extra rows without editing checks.json
$S/cad q my/blender/model.blend sweep PRT_launcher PRT_hopper tilt 40 50 2.5
$S/cad q my/blender/model.blend section x 21 /tmp/nip.png 900,25,185 120 --lentil "21,-8,196:0,0,1"
$S/cad q                                   # every cad q command
(cd my/blender && $S/cad py -c "import params as P; print(P.HOOD_HI)")   # project Python with bpy + cadlib
$S/cad rows my/blender/cadcheck.json "hood.*flywheel"   # one line per report row; manifest.json and checks.json work too (no Blender)
$S/cad bom my/BOM_AND_ASSEMBLY.md my/blender/manifest.json   # BOM fastener table vs the model
$S/cad printcheck my/stl --manifest my/blender/manifest.json --render /tmp/pc   # layer support check on the exported STLs
$S/cad slice --detect                                    # slicers found and whether they are usable (runs nothing)
$S/cad slice my/stl                                      # sandboxed, crash-guarded slice: time, filament, where support goes
$S/cad sheet my/stl /tmp/sheet.png
python3 -I tools/transcript/cc_transcript.py workflow ~/.claude/projects/<proj>/<session>/subagents/workflows/wf_XXXX
sh tools/verify_all.sh                                   # everything (next -> main)
sh tools/verify_all.sh --changed --dry-run               # what this branch affects, vs next
```
