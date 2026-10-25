"""printcheck on planted fixtures (FINDINGS "v2 post-freeze"). Run in Blender:

    Blender -b --factory-startup --python tools/test_printcheck.py -- --out /tmp/dir

Each fixture is built with cadlib (Manifold booleans) and written with cadlib.export, the same path as a project's STLs.
Must fail: a tab cantilevered 8 mm off a wall, a block floating 4 mm above the part. Must warn: a 35 mm bridge.
Must pass: a 20 mm bridge, a 0.8 mm ledge, a 45 deg outward chamfer, a counterbore printed face down (a roof with a
screw hole through it), a 6 mm horizontal hole, two overlapping shells that were joined without a boolean.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "print-cad-blender", "scripts"))
from cadlib import geom as G, export as E   # noqa: E402
import printcheck as PC   # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = args[args.index("--out") + 1] if "--out" in args else "/tmp/alex3d-printcheck-fixtures"
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith(".stl"):
        os.remove(os.path.join(OUT, f))


def save(name, ob):
    E.write_stl(os.path.join(OUT, name + ".stl"), E.print_tris(ob))


def deck(gap):
    return G.csg(G.box("p0", 0, 10, 0, 10, 0, 10), add=[G.box("p1", 10 + gap, 20 + gap, 0, 10, 0, 10), G.box("d", 0, 20 + gap, 0, 10, 10, 12)])


save("bridge_20", deck(20))
save("bridge_35", deck(35))
save("tab_8", G.csg(G.box("w", 0, 20, 0, 4, 0, 20), add=[G.box("t", 0, 20, 4, 12, 10, 12)]))
save("ledge_08", G.csg(G.box("w", 0, 20, 0, 4, 0, 20), add=[G.box("t", 0, 20, 4, 4.8, 10, 12)]))
save("island", G.join("isl", [G.box("b", 0, 20, 0, 20, 0, 2), G.box("f", 5, 15, 5, 15, 6, 8)]))
save("chamfer_45", G.csg(G.cyl("c", (0, 0), 5, 0, 2), add=[G.cone("k", (0, 0), 5, 10, 2, 7, n=96), G.cyl("t", (0, 0), 10, 7, 9, n=96)]))
save("counterbore", G.csg(G.box("b", -15, 15, -15, 15, 0, 8), sub=[G.cyl("r", (0, 0), 10, -1, 1.0, n=96), G.cyl("h", (0, 0), 3, -1, 9)]))
save("hhole_6", G.csg(G.box("b", 0, 20, 0, 20, 0, 20), sub=[G.cyl("h", (10, 10), 3, -1, 21, axis='X')]))
save("overlap_shells", G.join("ov", [G.box("a", 0, 20, 0, 10, 0, 10), G.box("b", 10, 30, 0, 10, 0, 10)]))

rep = PC.run([OUT], out=os.path.join(OUT, "printcheck.json"))
by = {r["stl"]: r for r in rep["parts"]}
want = {"tab_8": "fail", "island": "fail", "bridge_35": "warn"}
bad = []
for name, r in sorted(by.items()):
    st = sorted(set(f["status"] for f in r["findings"]))
    exp = [want[name]] if name in want else []
    if st != exp:
        bad.append("%s: %s, wanted %s (%s)" % (name, st, exp, [f["msg"] for f in r["findings"]]))
t = by["tab_8"]["regions"][0]
if not (t["kind"] == "cantilever" and 7.0 <= t["overhang_mm"] <= 8.5 and abs(t["z_mm"] - 10.0) <= 0.2):
    bad.append("tab_8 measured %s" % t)
if by["island"]["n_islands"] != 1:
    bad.append("island: %d islands" % by["island"]["n_islands"])
b = by["bridge_35"]["max_bridge_mm"]
if not 34.0 <= b <= 36.5:
    bad.append("bridge_35 span %.1f" % b)
if not 19.0 <= by["bridge_20"]["max_bridge_mm"] <= 21.5:
    bad.append("bridge_20 span %.1f" % by["bridge_20"]["max_bridge_mm"])
cb = [g for g in by["counterbore"]["regions"] if g["kind"] == "bridge"]
if not cb or not 19.0 <= cb[0]["span_mm"] <= 21.5:
    bad.append("counterbore roof not a 20 mm bridge: %s" % by["counterbore"]["regions"][:2])
# a part marked supports: yes reports where support goes, without failing
sup = PC.analyze(PC.read_stl(os.path.join(OUT, "tab_8.stl")), supports="yes")
if sup["findings"] or not sup["needs_support"]:
    bad.append("supports: yes still fails or lost the region: %s" % sup["findings"])
print("PRINTCHECK_FIXTURES", "ok" if not bad else "FAIL", "%d parts" % len(by), "; ".join(bad))
