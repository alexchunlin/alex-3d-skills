# Evidence checklist

Each line names the evidence that settles it. A check row (`cadcheck.json` → `checks.<name>`) beats a `cad q` line,
which beats a render. Items marked (A1) caught real problems in attempt 1. The ID points into `docs/FINDINGS.md`.

## Function
- [ ] Payload path: `drop` rows at every joint extreme, landing inside the working window (A1-F1). If none exists, add a `drop_tests` entry and re-run the check rather than eyeballing.
- [ ] Working condition reachable: `distances` rows for the nip, gap or preload at both ends of the adjustment (A1-F2).
- [ ] Indexing: one payload per cycle (pocket size vs. payload in any orientation). Check edge-on payloads (A1 R1 #8) with `cad q inside` or a section with `--lentil`.
- [ ] Joint sweeps: `interference` and `clearance` rows include overtravel. Margin past each limit, or a hard stop (A1-F5).
- [ ] Rotating parts: retention on the shaft, balance, guard coverage (section through the wheel plane).
- [ ] Encoder or alignment: the gap and coaxiality numbers, and how the magnet or part is centred during assembly (A1-F7).
- [ ] Cables: every brief cable has a route; `cables` rows show path vs. lead length; connectors and joints are not at a moving bend (A1-F12).
- [ ] Stability: `stability.worst` tip angle at the worst pose.
- [ ] Power, USB and cooling: plug clearance (`cad q dist`), and an air path past the heat sinks.

## Manufacture
- [ ] `parts`: all manifold, fit the P1S, no sloped overhang marked supports=no, bridges ≤ 25 mm, walls ≥ 1.6 mm.
- [ ] `fasteners`: no buried heads (reversed screws, A1-F10), engagement ≥ 4 mm, access at the assembly step, and the reach needed (A1-F4, F11).
- [ ] Fasteners and cables included in interference (A1-F3). The `coverage` line must list all four collections.
- [ ] `assembly_order` matches the BOM steps, and every bench sub-assembly can actually be lifted into place.
- [ ] Service: tape, shim, belt or battery changes without a full teardown. Count the screws (A1 R1 #6).
- [ ] Purchased-part tolerances: `slide_out` rows; bays sized for the envelope plus 2 mm (A1-F13).

## Aesthetics
- [ ] iso and iso_front_left: no exposed wires, PCB edges or motor cans.
- [ ] Edge breaks and radii from one declared set (grep the params for BEVEL/RADIUS).
- [ ] Visible screw heads counterbored; parting lines aligned.
- [ ] No leftover cut artefacts (notches, stray bosses) in hero views.
