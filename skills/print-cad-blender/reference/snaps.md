# Snap fits and print-in-place hinges

`cadlib.features` builds four joins that are sized by the call and re-checked by cadcheck from their records, so you
write no `checks.json` rows for them. The math is in `scripts/cadsnap.py` (plain python3). The user's v2 print had
about 103 screws in 18 types across 36 parts. Use these for parts that are neither loaded nor serviced. Use
`fastener_joint` for load paths, service access and metal parts.

Every call follows the `fastener_joint` pattern. Build the parts uncut and give them their final `PRT_` names. Make
the call, then run `geom.csg(part, **ops[part.name])` for each part (`ops` is `{part: {"add": [...], "sub": [...]}}`;
pass `ops=` to collect several calls). Register the parts with `asm.part`. The call raises `SnapError` with the fix
when nothing fits, and writes a record to the manifest's `"joins"` and to the blend.

| Call | Builds |
|---|---|
| `snap_hook(name, host, catch, at, along, out, length, width, undercut, thickness=None, entry_deg=30, retain_deg=90, taper=1.0, uses="repeated", material=None, print_up=None)` | Cantilever arm with a root fillet (r = 0.5 h) and barb, on `host`. Cuts a channel and an undercut pocket in `catch`, leaving the ledge. `at` is the middle of the root on the host's face; `along` runs root to tip (the way the hook goes in); `out` is the barb's side; `length` runs root to the retaining face. With `thickness=None` it uses the thickest arm in [1.2, length/5] whose strain stays within the allowable |
| `annular_snap(name, shaft, hub, at, axis, d, hub_od, interference=None, entry_deg=30, retain_deg=45, ...)` | A bead on `shaft` and a groove in `hub`'s bore. `at` is the bead's crest on the axis; `axis` is the direction the hub comes off. The hub's bore is measured. `interference` is diametral; None picks the largest within the hub's allowable |
| `torsion_snap(name, host, catch, at, along, out, bar_len, lever, width, undercut, bar_d=None, bar_d_max=None, ...)` | A lever on a round bar whose ends sit in `host`, which needs a window around the lever. `bar_len` is the free span. `bar_d=None` picks the thickest bar within the shear-strain limit, up to `bar_d_max` (give it the host's thickness). Torsion puts the principal stress at 45° to the bar, so it crosses layers on the bar's sides however the bar lies: the bar always gets the across-layer allowable |
| `pip_hinge(name, (static, moving), axis_at, axis, length, knuckles, pin_d, clearance=0.4, gap=0.4, wall=1.2, lo=0, hi=90, print_up=None, strict=True)` | Alternating knuckles with a pin on the static part's knuckles, teardrop bores (when you give `print_up`), and a relief around each knuckle in the other part. Use an odd knuckle count, so the pin runs into a static knuckle at both ends. With an even count it ends inside the last moving knuckle, held from one side, and the build prints a note. Its 45° cone tip only avoids a flat end face; it doesn't make the stub self-supporting on a flat axis. Creates `PIV_<name>`: register the moving part with `joint="PIV_<name>"`. The export writes the pair once, as `pip_<name>.stl/.3mf` in the static part's print frame. The two parts' own files are not written (quantity 0), so printing every STL prints the hinge once |

`material=None` takes the flexing part's `asm.part(material=)` if it is already registered, else PLA. `print_up` is
the world print +Z of the flexing part. Sizes and angles are validated first: a size that isn't positive, an angle
outside its range, an arm shorter than 5 × a given thickness, or `hub_od <= d` raises `SnapError`. Without it the call sizes for the layer plane, and cadcheck decides the layer
direction from the part's `print_rot`.

## What cadcheck does with the records (`snaps`)

- **Snaps.** cadcheck recomputes the strain for the flexing part's material and checks it against the allowable for
  `uses`. A torsion bar's shear strain is checked against (1 + ν) times the across-layer allowable, always. For the
  others the allowable becomes `across_mpa / E` when the flexing member's tension crosses layers: a beam more than 45°
  off the bed in `print_rot`, or a ring whose axis is less than 45° off it. At 20-45° it warns. A permanent snap
  (retain ≥ 80°) on a part that a `service` op removes also warns.
- **Slide.** A `slide_out` row that moves the host or the catch, but not both, along the snap's way out (within 30°
  of the record's `insert_dir`, reversed for the host) lets the barb ride its partner as `flex`. The bound is 1.5 × the
  barb's volume plus `vol_tol`, so a real crash still blocks. This applies only when the retaining face releases. A
  self-locking face (retain 90°, `W_release` None) stays a blocker, and the fail names the permanent snap.
- **Insertion.** Each snapped part also tries the snap's way in. Along it, the partner drops out of the ray test, and
  the part is swept through it in 1 mm steps: the overlap must stay within the same bound. In every other direction
  the partner is an obstacle like any part.
- **Hinges.** Radial and axial gaps must be at least `print_in_place.min_clearance` (0.3). The axis must lie within
  `axis_flat_deg` (10°) of the bed. Both parts need the same `print_rot`, and the moving part must be on the
  hinge's joint. A generated `fits` rule (min 0.28) lets the interference sweep measure the real gap instead of
  failing it against `moving_min_clearance` 0.5. The rule covers the whole pair, so the leaves' clearance to each other
  is also held to 0.28, not 0.5. A leaf that swings within 0.5 mm of the other part's leaf passes. Give the pair a
  `distances` row if that gap matters.
- **flexures rows with dimensions.** Give `l`, `b`, `h` and `deflection` (mm), with `end` set to `"free"` (default)
  or `"guided"` (a parallel leaf) and `kt` (default 1). cadcheck then computes the stress and ignores a typed
  `stress_mpa`; it warns when the typed value is more than 20 % off. A `compliant` distances row on a snap's host
  or catch still needs its own flexures row: only a slide's flex on them is the snap's. Push-assist A3 typed 7.6 MPa, and the
  reviewer's script found 9-22 MPa with Kt (PA-A3-T22).

## Formulas and sources

Sources: the Bayer MaterialScience (now Covestro) "Snap-Fit Joints for Plastics - A Design Guide" ("Bayer" below),
and the BASF snap-fit design guide as a second source. **These were written down without network access, from
memory.** Constants marked *recalled* need checking against the guides before you rely on them.

| Quantity | Formula | Source |
|---|---|---|
| Cantilever strain, constant section | ε = 1.5 · y · h / l² (Bayer writes it as y = 0.67 · ε · l² / h) | Bayer, cantilever design type 1. Also follows from Euler-Bernoulli: y = P l³ / 3EI, σ = P l (h/2) / I |
| Thickness halving to the tip | ε = 0.92 · y · h / l² (y = 1.09 · ε · l² / h) | Bayer, design type 2 (*recalled*). `cadsnap.cantilever` integrates any linear taper; the test checks it gives 1.09 |
| Deflection force | P = b · h² · E · ε / (6 l) | Bayer. Root bending moment = σ · Z |
| Mating force | W = P · (μ + tan α) / (1 − μ · tan α). α = entry angle to insert, retain angle to release. 1 − μ tan α ≤ 0 means the face self-locks (W = None) | Bayer |
| Annular strain | ε = Δd / d (diametral interference over diameter; the hub takes it all, the shaft is rigid) | Bayer; it is the hoop strain of a thin ring |
| Annular transverse force | P = Δd · d · E · X, with X = 0.62 · √((δ − 1)/(δ + 1)) / ((δ² + 1)/(δ² − 1) + ν), δ = hub_od / d | Bayer, X for an elastic hub on a rigid shaft (*recalled*: the Lamé term is standard, but check the 0.62 and the square root against the guide's X-vs-δ chart) |
| Torsion snap | φ = y / lever. γ = φ · r / l, with l = (bar_len − width)/2 on each side (Bayer: φ = 180 γ l / (π r) in degrees). Limit: γ ≤ (1 + ν) · ε_allow. Torque T = 2 · G · J · φ / l, with G = E / 2(1 + ν) and J = π d⁴/32; P = T / lever | Bayer torsion snap-fits (*recalled*); torque from elementary torsion of a round bar |
| Leaf stress (flexures rows) | σ = kt · 1.5 · E · h · y / l² for a free end; 3 · E · h · y / l² for a guided end | Roark's Formulas for Stress and Strain, 7th ed., Table 8.1 cases 1a and 1e |

These formulas use E from the TDS. Bayer uses the secant modulus at the design strain, which is lower, so the forces
here are on the high side.

## Constants

| Constant | Value | Basis |
|---|---|---|
| Allowable strain, `uses="once"` | `snap_strain` = yield / 2 (PLA 0.0165) | cadmat (PR #20): our assumption. Bayer keeps the permissible strain well below yield, and a printed part is brittle at its layer lines |
| Allowable strain, `uses="repeated"` | 0.6 × once (PLA 0.0099) | Bayer: frequent separation takes about 60 % of the one-time value (*recalled*) |
| Across layers | `across_mpa / E` (PLA 15 / 2200 = 0.0068) | the layer-bond allowable (cadmat) expressed as a strain; always for a torsion bar (principal stress at 45° to its axis, from elementary torsion) |
| μ, PLA on PLA | 0.5 (`cadmat` `mu_self`) | **Assumption.** No published PLA value was at hand. Bayer's table gives 0.5-0.7 for PC on PC and 0.3-0.4 for POM on POM (*recalled*) |
| ν (Poisson) | PLA 0.35, PETG 0.38 (`cadmat` `poisson`) | assumption: the commonly quoted ranges |
| Arm or bar thickness range | 1.2 mm up to l/5 (bar: 1.6 mm up to `bar_d_max`) | 1.2 = three 0.42 mm lines (FDM practice). The l/h ≥ 5 limit is for beam theory: shorter arms are stiffer than the formula (*recalled*, Bayer) |
| Root fillet | r = 0.5 h | Bayer's stress-concentration chart levels off near R/h = 0.5 (*recalled*). The strain formulas carry no Kt, as in Bayer |
| Snap pocket clearance | 0.25 mm around the barb; the barb stands undercut + 0.25 | assumption, the same as `RULES` fit_slide |
| Smallest annular interference | 0.1 mm diametral | assumption: FDM holds about ±0.1 mm |
| Hinge clearance and gap | 0.4 mm default, 0.3 mm minimum | **Common FDM practice** (maker guides and test hinges on 0.4 mm nozzles at 0.2 mm layers), not a standard. Print a test hinge for a new printer or material |

## Not covered

Creep under a sustained snap preload, which PLA does. Fatigue beyond the 60 % rule. Snap arms with a non-rectangular
section (U or T sections need their own I). The release force of a hook you deflect by hand. Ring snaps on a slotted
hub (treat each finger as a `snap_hook`). Hinges whose axis is not along a world axis (asm.joint turns about X, Y or Z
only).
