"""Write the printcheck-gap ramp (docs/features/blend-bracket.md, "The printcheck gap") as binary STLs.

    python3 -I ramp_stl.py <out_dir> [angle_deg ...]       (default 20 30 40)

A 10 x 20 x 40 mm column with a wedge on its +x side whose underside rises at `a` from horizontal, reaching 20 mm out
to the column top. A PLA slicer supports that underside at every a from 5 to 40; printcheck gives 0 fails, 0 warns.
"""
import math, os, struct, sys

out, angles = sys.argv[1], [float(a) for a in sys.argv[2:]] or [20.0, 30.0, 40.0]
os.makedirs(out, exist_ok=True)
for a in angles:
    h = 40 - 20 * math.tan(math.radians(a))
    prof = [(0, 0), (10, 0), (10, h), (30, 40), (0, 40)]          # xz profile, counter-clockwise seen from -y
    fan = [(4, 0, 1), (4, 1, 2), (4, 2, 3)]
    P = lambda i, y: (prof[i][0], y, prof[i][1])
    tris = [(P(i, 0), P(j, 0), P(k, 0)) for i, j, k in fan] + [(P(i, 20), P(k, 20), P(j, 20)) for i, j, k in fan]
    for i in range(5):
        j = (i + 1) % 5
        tris += [(P(i, 0), P(i, 20), P(j, 20)), (P(i, 0), P(j, 20), P(j, 0))]
    with open(os.path.join(out, f"ramp_{int(a)}.stl"), "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<3f", 0, 0, 0) + b"".join(struct.pack("<3f", *v) for v in t) + b"\0\0")
