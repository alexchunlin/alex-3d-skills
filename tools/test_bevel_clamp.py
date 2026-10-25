"""cadlib.bevel flags a globally clamped edge break (FINDINGS V2A6-T2). Run in Blender:

    Blender -b --factory-startup --python tools/test_bevel_clamp.py

v2 A5 and A6 built the gate detent tab as a box minus an n=768 cylinder; Blender's bevel overlap clamp is global, so
the 0.28 mm facets cut every 1.0 edge break on the tab to about 0.1. A plain box must not be flagged; the same box
minus an n=768 cylinder must be, with bevel_clamped set for cadcheck's parts warn.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G

plain = G.box("plain", 0, 10, 0, 6, 0, 5)
G.bevel(plain, 1.0)
cut = G.csg(G.box("cut", 0, 10, 0, 6, 0, 5), sub=[G.cyl("c", (5, -30), 34.0, -1, 6, n=768)])
G.bevel(cut, 1.0)
ok = "bevel_clamped" not in plain.keys() and "bevel_clamped" in cut.keys() and cut["bevel_clamped"][1] < 0.1
print("BEVEL_CLAMP", "ok" if ok else "FAIL", dict(plain.items()), list(cut.get("bevel_clamped", [])))
