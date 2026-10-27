# Usage inside a cad build script, after modelling:  exec(open('/tmp/cgb-tools/blender_export_world.py').read()); export_world(obj, '/path/part.stl')
# Writes the object's mesh in WORLD coordinates (no print rotation, no re-centring), so the pose you model is the pose submitted.
def export_world(ob, path):
    from cadlib.export import write_stl
    me = ob.data; me.calc_loop_triangles(); M = ob.matrix_world
    vs = [M @ v.co for v in me.vertices]
    write_stl(path, [(vs[t.vertices[0]], vs[t.vertices[1]], vs[t.vertices[2]]) for t in me.loop_triangles])
