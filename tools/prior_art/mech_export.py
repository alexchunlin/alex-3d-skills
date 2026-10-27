"""Blender side of mech_compare.py: write chosen objects as world-frame STLs (home pose, evaluated meshes) and the pivots.

    Blender -b model.blend --factory-startup --python-exit-code 1 -P mech_export.py -- <out_dir> OBJ [OBJ ...]

Writes <out_dir>/<OBJ>.stl (binary, mm, world coordinates at the blend's saved pose) and <out_dir>/scene.json: per
object its PIV_* chain (nearest first), per PIV_* empty its world origin and local X / Z axes.
"""
import json, os, struct, sys
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
out, names = argv[0], argv[1:]
os.makedirs(out, exist_ok=True)
dg = bpy.context.evaluated_depsgraph_get()


def chain(o):
    c, p = [], o.parent
    while p:
        if p.name.startswith("PIV_"):
            c.append(p.name)
        p = p.parent
    return c


scene = {"objects": {}, "pivots": {}}
for n in names:
    o = bpy.data.objects[n]
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    M = o.matrix_world
    co = [M @ v.co for v in me.vertices]
    with open(os.path.join(out, n + ".stl"), "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(me.loop_triangles)))
        for t in me.loop_triangles:
            a, b, c = (co[i] for i in t.vertices)
            nrm = (b - a).cross(c - a).normalized()
            f.write(struct.pack("<12fH", *nrm, *a, *b, *c, 0))
    scene["objects"][n] = {"pivots": chain(o), "triangles": len(me.loop_triangles)}
    ev.to_mesh_clear()
for o in bpy.data.objects:
    if o.name.startswith("PIV_"):
        M = o.matrix_world
        scene["pivots"][o.name] = {"origin": list(M.translation), "x": list(M.col[0][:3]), "z": list(M.col[2][:3])}
json.dump(scene, open(os.path.join(out, "scene.json"), "w"), indent=1)
print("EXPORTED", len(names))
