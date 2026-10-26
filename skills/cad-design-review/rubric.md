# Scoring rubric

Scores are absolute, never relative to the previous attempt. Match the **lowest** anchor whose condition holds.
Round down.

| Score | Anchor (all metrics) |
|---|---|
| 10 | No credible issue. You would print and ship it as is. |
| 9 | Minor polish only. Nothing would change the print, the assembly or the performance. cadcheck has 0 fails and every warn is explained. |
| 8 | Works. At most 2 major issues, each with a known fix under 1 hour of CAD and no reprint of a big part. |
| 7 | Works, but has 3 or more majors, or one major that needs a large part reprinted. |
| 6 | Any single **blocker** caps the metric here. Also: significant risk of rework at assembly. |
| 5 | Two blockers, or a blocker in the core function (for a launcher: feed or nip). |
| ≤ 4 | Won't work as designed: the core function is geometrically impossible, or parts can't be assembled. |

Severity:
- **Blocker:** stops the core function, an assembly step, or printing. Examples: a check `fail` in interference, fasteners or drop; a part that fits no printer; a part that needs supports when the brief forbids them.
- **Major:** works, but with real risk or real cost. Examples: clearance under 0.5 mm, no margin past a joint limit, service needing a teardown, an alignment with no jig.
- **Minor:** polish, or a low-probability risk.

## Metric-specific anchors

**Functionality** (will it work, and work well?)
- 9 needs every payload path drop-tested at every joint extreme with landings inside the working window, adjustments that reach the working condition (a `distances` row), cables with length and slack, sweeps clear with margin, and encoder or alignment features with a jig or a by-construction locator.
- Attempt 1 scored 5: the feed landed outside the nip at every tilt (blocker) and the nip couldn't squeeze the payload (major).

**Manufacturability** (print and assemble, one person, hand tools)
- 9 needs 0 fastener fails, every screw reachable at its assembly step with a reach of 60 mm or less (or the extension listed in the BOM), no supports, every part fitting the P1S, thread engagement of 4 mm or more, and BOM steps that match `assembly_order`.
- Attempt 1 scored 6: a screw head under the feeder disc (blocker), the horn adapter couldn't be assembled, and service needed a 15-screw teardown.

**Aesthetics** (designed, not slapped together). Judge it from the iso views and two close-ups, and score only against these concrete items:
- one form language: edge breaks within ±0.5 mm of the declared value and corner radii from a declared set (grep the params)
- no exposed wires, PCB edges or motor cans in the standard views
- visible screw heads counterbored or deliberately aligned
- parting lines aligned between adjacent parts
- two PLA colours used to mean something (for example structure vs. moving parts)
- 9 needs every item true. Each failed item costs a point from 10, and an "unfinished" element in a hero view (a notch, a stray boss) caps the score at 6.

## review.md format

```
# Review: <project>, attempt N
Checks re-run: <cadcheck summary line> (coverage: ...; not checked: ...)
| Metric | Score | Anchor matched | One-line reason |
## Previous issues   (one row each: issue, FIXED/PARTIAL/NOT FIXED, new number)
## Measurements      (table: item, value, source command or check row)
## Issues            (ranked; severity, problem, evidence, fix with dimensions)
## Check-config audit (allow/fits entries disputed, missing drop tests, missing assembly steps)
## What is good
```
