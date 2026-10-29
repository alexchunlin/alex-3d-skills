# Materials, print settings and printed sections

`scripts/cadmat.py` (plain python3) holds the material table, the print-setting defaults and the section model.
cadcheck's `calcs` rows ([checks-config.md](checks-config.md#calcs-a-computed-number-against-limits)), `asm.part`,
the export and project scripts import it. Push-assist ran 8 rounds of stress rows on solid sections. Its 3MFs carried
no settings, so the parts would print at the slicer's 2 walls and 15 % (PA-A8-T13), and every agent picked its own
limits (PA-A6-T10).

## Allowables: `mat(material or PRT_name, key)`

Design allowables are strength / SF, with SF = 2 for a static load. SF is our assumption, not a code value. Use a
bigger factor for a sustained load (PLA creeps), a fatigue load or an impact. "in" means stress along the layers, in a
beam that lies in the layer plane. "across" means stress that pulls layers apart, in a beam standing off the bed.

| key | PLA | PETG | source |
|---|---|---|---|
| `in_mpa` | 17.5 | 23.5 | `tensile_in_mpa` / SF |
| `across_mpa` | 15 | 15 | `tensile_across_mpa` / SF. PLA's 15 is cadcheck's `interlayer_mpa` default (R3's limit) |
| `snap_strain` | 0.0165 | 0.0245 | `yield_strain` / 2, a snap's one-time strain. Our assumption: the Bayer snap-fit design guide keeps the permissible strain well under yield. For frequent separation take about 60 % of it (Bayer; `cadsnap` does, for `uses="repeated"`) |
| `tensile_in_mpa` | 35 | 47 | PLA: Bambu PLA Basic TDS, X-Y tensile strength, about 35 MPa as recalled: **check it against the TDS**. It is the lower of the two vendors (Prusament PLA's TDS gives a 57 MPa yield strength), so the allowable holds for either. PETG: Prusament PETG TDS, tensile yield strength (ISO 527) |
| `tensile_across_mpa` | 30 | 30 | **Working figure, no TDS number.** For PLA: push-assist reviewers took 20-30 MPa across layers ("25 MPa = PLA tensile across layers"), and 30 / 2 = R3's 15. PETG is set equal to PLA until a Z-direction TDS value is entered |
| `flex_in_mpa` | 76 | - | Bambu PLA Basic TDS, bending strength (X-Y). This is also the figure push-assist PA-R8 used |
| `E_mpa` | 2200 | 1500 | Prusament PLA / PETG TDS, tensile modulus (Bambu PLA Basic gives about 2750) |
| `yield_strain` | 0.033 | 0.049 | Prusament PLA / PETG TDS, elongation at yield |
| `density` (g/mm³) | 1.24e-3 | 1.27e-3 | Prusament TDS. PLA's value is the same as cadcheck's `pla_density` |
| `poisson` | 0.35 | 0.38 | **Assumption**, the commonly quoted ranges; no TDS gives it. Annular and torsion snaps ([snaps.md](snaps.md)) |
| `mu_self` | 0.5 | 0.5 | **Assumption**, friction against the same material. No PLA value was at hand; Bayer's snap-fit guide lists 0.5-0.7 for PC on PC (as recalled). Snap mating forces |

**Check the numbers before you trust them.** They were entered without network access, from the documents named here
as recalled. Check each one against the current TDS before you rely on its last digit. `cadmat.SOURCES` holds the same
source string for every number. TPU is not in the table: a stress allowable means little for a 95A elastomer, so size
TPU parts by strain from its own TDS.

## Per-part print settings

`asm.part(..., material="PETG", walls=3, infill=40, layer_h=0.16, shells=4, line_w=0.45)`. Every key is optional.
`asm.part` refuses a material that is not in the table, and a wall or shell count that is not a whole number of 1 or
more. Keys you leave out print at the slicer's process preset, which is what `cadmat.PRINT_DEFAULTS` assumes: PLA,
2 walls, 15 %, 0.2 mm layers, 0.42 mm lines and 3 shell layers. The walls, infill, line width and bottom shell layers
are the values in a Bambu Studio 2.5 project file (X1C preset), and the vendored `slicers/profiles/prusa_p1s_pla.ini`
also has 2 perimeters and 15 %.

| where | what |
|---|---|
| `manifest.json` `parts.PRT_x.print` | every key, with the defaults filled in, and `defaulted`, which lists the keys left out |
| `<stl>.3mf` beside each STL (`export_stls(dir, threemf=True)`) | one build item per copy. Only the declared keys are written, so the rest stay with the slicer's preset. Core-spec per-object `<metadatagroup>` (`cad:walls`, `cad:infill`, `cad:material`, ...), and `Metadata/model_settings.config` with Bambu Studio / OrcaSlicer per-object keys: `wall_loops`, `sparse_infill_density` (`"40%"`), `layer_height`, `line_width`, `top_shell_layers` / `bottom_shell_layers` |
| the STL's 80-byte header | `alex-3d-skills cadlib PETG walls=3 infill=40% ...` as text. STL has no other slot, and slicers ignore the header |

The key names come from a Bambu Studio 2.5 project file (`project_settings.config`). No slicer has opened these
3MFs: the export was checked by reading the files. Whether Bambu Studio applies `model_settings.config` overrides
from a 3MF that another program wrote is unverified, so set them by hand if the slicer shows its defaults. The 3MF
has no material key, so pick the filament in the slicer. PrusaSlicer's per-object config
(`Slic3r_PE_model.config`) is not written.

The `parts` mass estimate now takes its shell from `walls x line_w`. The default, 2 x 0.42 = 0.84 mm, is the old fixed
shell. A part with no `infill` still counts 20 % in that estimate.

## Printed section: `section(b, h, part=..., **over)`, `i_eff`, `z_eff`

The section is a b x h rectangle, with h along the load. It has a solid shell of thickness
`t = min(walls x line_w, shells x layer_h)` on all four sides, and a core at `infill` % that counts for
`(infill / 100)^2` of solid stiffness. That follows Gibson & Ashby, *Cellular Solids* (2nd ed., 1997): the relative
modulus of a bending-dominated cellular solid goes as its relative density squared. The section has
`I = I_solid - I_core x (1 - k)` and `Z = I / (h / 2)`. The outer fibre is in the shell, so the shell's stress is
`M / Z`, as in a transformed section. `section()` returns `I`, `I_solid`, `Z`, `t`, `k` and `ratio`.
`part="PRT_x"` takes the part's settings, and keyword arguments override them (`z_eff(10, 4, part="PRT_leaf", infill=100)`).
The keywords are `walls`, `infill`, `line_w`, `shells`, `layer_h` and `t`; any other is an error. `t=` sets the shell
directly. A calc that gives `walls` and `infill` by keyword is not warned about the part's undeclared ones.

| section (mm) | 2 walls 15 % | 2 walls 20 % | 3 walls 40 % | 100 % |
|---|---|---|---|---|
| 10 x 4 | 0.70 | 0.71 | 0.75 | 1.00 |
| 10 x 10 | 0.41 | 0.42 | 0.50 | 1.00 |
| 24 x 24 | 0.20 | 0.22 | 0.32 | 1.00 |

The table gives `I / I_solid`. **`walls` barely changes the result:** with the default 3 shell layers, `t` stops at
0.6 mm, so walls past 2 add nothing until you declare `shells` or pass `t=`. This is deliberately conservative: top and
bottom faces get only their shell layers. For a beam standing up, where all four faces of the section are walls, pass
`t=walls x line_w`.

The model's limits:
- **Rectangles only.** For a round or other section, work out the same shell and core by hand, or split the section into rectangles.
- **No holes or stress raisers.** Multiply by your own Kt.
- **No anisotropy in the section.** Pick `in_mpa` or `across_mpa` for the orientation instead.
- **The bond between walls and infill is taken as perfect.**
- **Infill pattern is ignored.** The squared law is Gibson & Ashby's for bending-dominated cells; a stretch-dominated
  lattice goes nearer linearly in density, so for stiffness the squared law is the low side. Which side gyroid or grid
  infill falls on is not checked here.
- **Low stiffness is conservative only for stress.** For a stress under a given load, a low I is safe. For a calc
  driven by stiffness, such as an insertion force, a preload or a snap's push-in force at a given deflection, a low I
  under-predicts the force, so it is unconservative: bound those with `infill=100` (or `t=` the whole section) too.

For a part that carries load, declare `walls` and `infill` and use `z_eff`. Otherwise cadcheck warns that the calc
assumed the slicer defaults.
