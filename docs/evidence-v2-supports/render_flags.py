import bpy, bmesh, sys, math, os
from mathutils import Vector
args = sys.argv[sys.argv.index("--") + 1:]
stl, out = args[0], args[1]
COS45 = math.cos(math.radians(45))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.stl_import(filepath=stl)
o = bpy.context.selected_objects[0]
bm = bmesh.new(); bm.from_mesh(o.data); bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
zmin = min(v.co.z for v in bm.verts)
down = {f.index for f in bm.faces if f.normal.z < -COS45 - 1e-3 and (sum(v.co.z for v in f.verts)/len(f.verts) - zmin) > 0.3}
bm.faces.ensure_lookup_table()
seen = set(); red = set(); amber = set()
for i in down:
    if i in seen: continue
    stack, reg = [i], []; seen.add(i)
    while stack:
        f = bm.faces[stack.pop()]; reg.append(f)
        for e in f.edges:
            for g in e.link_faces:
                if g.index in down and g.index not in seen: seen.add(g.index); stack.append(g.index)
    ids = {f.index for f in reg}; blen = alen = 0
    for f in reg:
        for e in f.edges:
            oth = [g for g in e.link_faces if g.index not in ids]
            if not oth: continue
            L = e.calc_length(); blen += L; ez = min(v.co.z for v in e.verts)
            if any(min(v.co.z for v in g.verts) < ez - 0.2 for g in oth): alen += L
    frac = alen / blen if blen else 0
    (red if frac < 0.35 else amber).update(ids)
mat = lambda n, c: (lambda m: (setattr(m, "diffuse_color", c), m)[1])(bpy.data.materials.new(n))
mats = [mat("base", (0.75, 0.75, 0.75, 1)), mat("red", (0.9, 0.1, 0.1, 1)), mat("amber", (1.0, 0.65, 0.0, 1))]
for f in bm.faces: f.material_index = 1 if f.index in red else (2 if f.index in amber else 0)
bm.to_mesh(o.data); bm.free()
for m in mats: o.data.materials.append(m)
# bed plane for reference
bpy.ops.mesh.primitive_plane_add(size=1); p = bpy.context.object
c = sum((o.matrix_world @ Vector(b) for b in o.bound_box), Vector()) / 8
d = max(o.dimensions)
p.scale = (d * 1.4, d * 1.4, 1); p.location = (c.x, c.y, zmin - 0.05)
pm = mat("bed", (0.2, 0.3, 0.45, 0.35)); p.data.materials.append(pm)
sc = bpy.context.scene; sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.color_type = "MATERIAL"; sc.display.shading.light = "STUDIO"
sc.display.shading.show_xray = False
sc.render.resolution_x = sc.render.resolution_y = 700
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = d * 1.5
# view from below-front-side (looking up at the overhangs)
dirv = Vector((0.9, -1.2, -0.7)).normalized()
cam.location = c + dirv * d * 3
cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
