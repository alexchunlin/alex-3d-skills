"""cadlib.geom.csg: new faces take the base's material (push-assist PA-A4-T14). Run in Blender:

    Blender -b --factory-startup --python tools/verify.d/csg_material_cases.py -- <skills/print-cad-blender/scripts>

Blender's Manifold boolean in its index mode gives a tool face the base slot with the tool face's index, and appends
the tools' slots, empty ones too. A cut on a part that had been cut before ([part, None]) by a tool whose faces sit on
index 1 put the new walls on the empty slot: default grey in renders (the push-assist head, a3's 08_head_open.png).
Prints one CSGMAT line of JSON per case: the slots after csg, and the materials of the new walls and of the old faces.
"""
import json, sys
import bpy
sys.path.insert(0, sys.argv[sys.argv.index("--") + 1])
from cadlib import geom as G


def mat(n):
    return bpy.data.materials.get(n) or bpy.data.materials.new(n)


def tool(name, slots, idx, x=0.0):
    c = G.cyl(name, (x, 0), 1.0, -10, 10)
    for s in slots:
        c.data.materials.append(mat(s) if s else None)
    for p in c.data.polygons:
        p.material_index = idx
    return c


def report(case, ob, want, hole_x=0.0):
    slots = [m.name if m else None for m in ob.data.materials]
    name = lambda p: slots[p.material_index] if p.material_index < len(slots) else "index %d" % p.material_index
    walls = sorted({str(name(p)) for p in ob.data.polygons if (p.center.x - hole_x) ** 2 + p.center.y ** 2 < 1.1 and abs(p.center.z) < 4.9})
    rest = sorted({str(name(p)) for p in ob.data.polygons if (p.center.x - hole_x) ** 2 + p.center.y ** 2 >= 1.1})
    print("CSGMAT " + json.dumps({"case": case, "slots": slots, "walls": walls, "other": rest, "want": want,
                                  "ok": walls == [want] and rest == [want]}))


def part(slots=("pla",), idx=0):
    b = G.box("part", -5, 5, -5, 5, -5, 5)
    for s in slots:
        b.data.materials.append(mat(s) if s else None)
    for p in b.data.polygons:
        p.material_index = idx
    return b


# the push-assist case: a part cut before (its slots [pla, None]), cut again by a tool whose faces are on index 1
b = part(("pla", None))
G.csg(b, sub=[tool("t", ["x", "y"], 1)])
report("recut, tool faces on index 1", b, "pla")
# a bare tool, a coloured tool, a union, an intersect, several tools at once
for case, kw in (("bare tool", dict(sub=lambda: [tool("t", [], 0)])),
                 ("coloured tool", dict(sub=lambda: [tool("t", ["red"], 0)])),
                 ("two tools", dict(sub=lambda: [tool("t1", [], 0), tool("t2", [None, "blue"], 1, x=3.0)]))):
    b = part()
    G.csg(b, **{k: v() for k, v in kw.items()})
    report(case, b, "pla")
b = part()
G.csg(b, add=[G.box("boss", -2, 2, -2, 2, 4, 8)], inter=[G.box("keep", -6, 6, -6, 6, -6, 7)])    # new faces: the boss's sides
slots = [m.name if m else None for m in b.data.materials]
print("CSGMAT " + json.dumps({"case": "union and intersect", "slots": slots, "walls": sorted({slots[p.material_index] for p in b.data.polygons}),
                              "want": "pla", "ok": slots == ["pla"] and all(p.material_index == 0 for p in b.data.polygons)}))
# a part on slot 1 of two (its first slot another material): new walls on slot 1 too, not slot 0
b = part(("paint", "pla"), idx=1)
G.csg(b, sub=[tool("t", [], 0)])
report("part on its second slot", b, "pla")
# a bare part (cadlib solids have no material until asm.part): it stays bare, no empty slot appended
b = G.box("bare", -5, 5, -5, 5, -5, 5)
G.csg(b, sub=[tool("t", ["red"], 0)])
print("CSGMAT " + json.dumps({"case": "bare part stays bare", "slots": [m.name if m else None for m in b.data.materials],
                              "ok": len(b.data.materials) == 0}))
