"""STL export in print orientation, and saving the .blend.

One binary STL per unique `stl` name, rotated by the part's print_rot, dropped to z = 0 and centred
in XY. Stale STLs are deleted (the brief requires it; attempt 1 did it by hand).
"""
import bpy, os, struct
from mathutils import Vector, Matrix
from . import asm


def print_tris(ob):
    R = Matrix(ob["print_rot"]) if "print_rot" in ob.keys() else Matrix.Identity(3)
    me = ob.data
    me.calc_loop_triangles()
    Mw = ob.matrix_world
    vs = [R @ (Mw @ v.co) for v in me.vertices]
    xs, ys, zs = [v.x for v in vs], [v.y for v in vs], [v.z for v in vs]
    off = Vector((-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs)))
    vs = [v + off for v in vs]
    return [(vs[t.vertices[0]], vs[t.vertices[1]], vs[t.vertices[2]]) for t in me.loop_triangles]


def write_stl(path, tris, header=b"alex-3d-skills cadlib"):
    with open(path, "wb") as f:
        f.write(header.ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            n = (b - a).cross(c - a)
            n = n.normalized() if n.length > 0 else n
            f.write(struct.pack("<12fH", n.x, n.y, n.z, a.x, a.y, a.z, b.x, b.y, b.z, c.x, c.y, c.z, 0))


def export_stls(stl_dir, clean=True):
    os.makedirs(stl_dir, exist_ok=True)
    asm.set_pose()
    if clean:
        for f in os.listdir(stl_dir):
            if f.endswith(".stl"):
                os.remove(os.path.join(stl_dir, f))
    done = {}
    for ob in sorted(bpy.data.collections["Printed"].objects, key=lambda o: o.name):
        stl = ob.get("stl")
        if not stl:
            continue
        done[stl] = done.get(stl, 0) + 1
        if done[stl] == 1:
            write_stl(os.path.join(stl_dir, stl + ".stl"), print_tris(ob))
    return done   # stl name -> quantity


def save_blend(path):
    asm.cleanup()
    asm.set_pose()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    # Blender writes path + "1" as a backup on overwrite; it is 6 MB of noise in a repo
    if os.path.exists(path + "1"):
        os.remove(path + "1")
    return path
