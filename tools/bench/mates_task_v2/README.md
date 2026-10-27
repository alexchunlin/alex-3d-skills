# mates_task_v2: a pan-tilt head placed from interfaces, not coordinates

The second A/B kit for `cadlib.mates`. In `mates_task` (v1) the brief handed over world positions, so both arms scored
7/7 and there was no placement reasoning left for mates to save. This brief gives datasheet patterns and relational
constraints only. Every placement follows from a chain: deck → pan servo → pan horn → pan bracket → tilt servo
(turned so its spline is +Y and its case hangs below) → tilt horn → tilt bracket → camera. Done by hand, that chain
needs two rotations composed and tapped-hole patterns carried through them. Sized for 20-30 minutes of design.

| File | What |
|---|---|
| `brief.md` | the assembly and its constraints (tilt axis 40 above the pan horn and crossing the pan axis, camera axis through both axes, board back 25 ahead, joint ranges); no positions |
| `prompt_absolute.md`, `prompt_mates.md` | differ only in the template paragraph (`diff` them). Fill `{SKILL}`, `{KIT}` (this folder) and `{PROJECT}`. The absolute arm copies `../mates_task/template_absolute/`; run it with `{SKILL}` = `/tmp/skill-abs/skills/print-cad-blender` |
| `components.json`, `kit_parts.py` | servo (with bottom and side tapped-hole patterns), horn, camera board; data, connectors, placeholders |
| `interfaces.json` | what is scored and the answers (derived in its `_about`) |
| `checks.json` | cadcheck overlay rows: cover to pan bracket over the pan range, pan servo on the deck |
| `reference/blender/` | a mates solution: 0 cadcheck fails, 24/24 rows, 153 lines (47 of them template) |
| `selftest.sh` | the reference plus two planted errors (below); verify_all runs it |

The scorer is v1's, pointed at this folder: `tools/bench/mates_task/score.py <project> --kit tools/bench/mates_task_v2`.

## Run one arm

```sh
KIT=~/code-stuff/alex-3d-skills/tools/bench/mates_task_v2
SKILL=~/code-stuff/alex-3d-skills/skills/print-cad-blender            # mates arm; absolute arm: /tmp/skill-abs/skills/print-cad-blender
mkdir -p /tmp/mt2/mates-1
sed -e "s#{KIT}#$KIT#g" -e "s#{SKILL}#$SKILL#g" -e "s#{PROJECT}#/tmp/mt2/mates-1#g" $KIT/prompt_mates.md > /tmp/mt2/mates-1/PROMPT.md
# ... run the designer agent on PROMPT.md, then:
python3 -I $KIT/../mates_task/score.py /tmp/mt2/mates-1 --kit $KIT    # writes mates_task_v2_score.json there
```

## What the score reports (24 rows plus cadcheck)
- **cadcheck fails** with the designer's `checks.json` plus `checks.json` here as an overlay (cadcheck's own joint
  sweeps cover interference over each joint's declared range).
- **frames** (3): pan servo, tilt servo and camera, each found by a rigid fit of its placeholder mesh. **axial** (2):
  each horn on its spline.
- **joints** (2): `PIV_pan` on the pan axis; `PIV_tilt` on the tilt axis, under `PIV_pan`; ranges and what each carries.
- **screws** (6): pan servo to deck, pan bracket to horn, tilt servo to bracket, tilt bracket to horn, camera to
  bracket (each coaxial with the holes, on the right joint), and 2 M3 joining cover and deck from either side.
- **poses** (5): the camera's frame at (pan, tilt) = (0, 0), (45, 30), (-90, -25), (90, 60), (-30, 45), against the
  analytic chain (tilt about the tilt axis, then pan).
- **clearances** (6 pairs): minimum distance over pan {-90, -45, 0, 45, 90} x tilt {-25, 0, 30, 60}, at least 1 mm.

Poses, clearances and the tilt range use the brief's senses (pan counter-clockwise from above, tilt + raises). The
scorer maps them onto the design's joint by the sign of its axis at home: `asm.joint` only turns about +X/+Y/+Z, so a
tilt servo whose spline points +Y has a joint where + lowers the camera, and the brief allows it.

## Planted errors (`selftest.sh`)
- camera back 25.5 ahead of the tilt axis instead of 25: exactly `BUY_cam` and the 5 pose rows are off, each 0.500 mm;
- tilt range typed in the brief's sense on a joint that counts the other way (60 down, 25 up): exactly `PIV_tilt`.
