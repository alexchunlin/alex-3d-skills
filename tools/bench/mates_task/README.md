# mates_task: does placing parts through mate connectors cut placement errors?

An A/B kit for `cadlib.mates`. One brief, two prompts that differ only in the template the designer starts from.
The coordinator runs the agents; nothing here calls an LLM.

| File | What |
|---|---|
| `brief.md` | the assembly (deck, servo, horn-driven arm on the spline, PCB on 4 standoffs, lid with 4 screws); about 20 min of design |
| `prompt_absolute.md`, `prompt_mates.md` | the designer prompts; `diff` shows the template paragraph is the only difference. Fill `{SKILL}`, `{KIT}` (this folder) and `{PROJECT}` (an empty folder per run) |
| `components.json`, `kit_parts.py` | purchased-part data (with connectors) and placeholders, each in its own local frame. Both arms get the same data |
| `template_absolute/` | the project template as it was before mates (`5412b4f`), for the `absolute` arm. The `mates` arm copies `skills/print-cad-blender/templates/project-mates/` (it was `templates/project/` during the 2026-10-27 runs) |
| `checks.json` | acceptance rows the scorer adds as a cadcheck overlay: arm-to-lid clearance over the swing, lid-to-board clearance, servo on the deck |
| `interfaces.json`, `measure_blend.py` | what "on its interface" means and how it is measured, from the blend alone (no connectors or mate table read) |
| `score.py` | the scorer; `--kit DIR` scores against another kit folder (`mates_task_v2`) |
| `reference/blender/` | a mates solution: 0 cadcheck fails, 0 warns, 7 of 7 interfaces, 131 lines (47 of them template) |
| `selftest.sh` | builds the reference, a copy with the board planted 0.5 mm off, and a copy with the lid screws driven from under the deck; the scorer must pass the first and third and flag only the board in the second (verify_all runs it) |

## Run one arm

```sh
KIT=~/code-stuff/alex-3d-skills/tools/bench/mates_task
SKILL=~/code-stuff/alex-3d-skills/skills/print-cad-blender
mkdir -p /tmp/mt/mates-1
sed -e "s#{KIT}#$KIT#g" -e "s#{SKILL}#$SKILL#g" -e "s#{PROJECT}#/tmp/mt/mates-1#g" $KIT/prompt_mates.md > /tmp/mt/mates-1/PROMPT.md
# ... run the designer agent on PROMPT.md, then:
python3 -I $KIT/score.py /tmp/mt/mates-1            # writes /tmp/mt/mates-1/mates_task_score.json
```

The absolute arm is the same with `prompt_absolute.md`. Its agents still read the current SKILL.md, which tells them
to place parts through mates; for a clean baseline run that arm against a skill checkout at `5412b4f` (`--skill` on
`score.py` only changes which `cad` the scorer runs, not what the agent read).

## What the score reports

- **cadcheck fails** with the designer's `checks.json` plus this kit's `checks.json` as an overlay.
- **Interfaces off by more than 0.2 mm or 1 deg** (7 rows): the servo's and the board's placement against the brief
  (each found by a rigid fit of its placeholder mesh, vertex for vertex: a cut or joined placeholder counts as off), the
  horn coaxial and seated on the spline, `PIV_arm` on the spline axis with -90..90 carrying the horn and arm, the 4 arm
  screws coaxial with the horn's 0/90/180/270 holes and on `PIV_arm`, the 4 board screws coaxial with the board's holes,
  and 4 M3 screws that join the lid and the deck, from either side (the shank has lid and deck material around it).
- **Lines of build code**: non-blank, non-comment lines of every `.py` under `<project>/blender/` (template lines
  included; the reference's template share is 47).

Compare arms on: runs with 0 fails and 0 interfaces off, interfaces off per run, wall time, output tokens
(`tools/transcript/cc_transcript.py`), and lines of code.

## Results (coordinator, 3 runs per arm, 2026-10-27)
Every run: 0 cadcheck fails, 7/7 interfaces (mates-1 first scored 6/7: the scorer wanted the lid screws driven from
the lid side; fixed, re-scored 7/7). Wall time absolute 3.3 / 4.0 / 5.5 min, mates 6.0 / 4.2 / 4.5; lines absolute
134 / 134 / 160, mates 159 / 144 / 145. The brief gives the world positions, so the task sits at the ceiling: there is
no placement reasoning for mates to save. `../mates_task_v2` gives constraints instead.
