"""STL and 3MF export in print orientation, and saving the .blend.

One binary STL per unique `stl` name, rotated by the part's print_rot, dropped to z = 0 and centred
in XY, plus a 3MF of the same mesh (one build item per copy) that carries the part's declared print settings.
Stale STLs and 3MFs are deleted (the brief requires it; attempt 1 did it by hand).

The settings ride in two places in the 3MF: core-spec per-object metadata (<metadatagroup>, "cad:walls" ...), which any
reader can list, and Metadata/model_settings.config with Bambu Studio / OrcaSlicer's per-object keys (wall_loops,
sparse_infill_density, ...), so the slicer starts from them instead of its defaults. Push-assist's hand-written 3MFs
had neither, so the parts would print at 2 walls and 15 % (PA-A8-T13). An STL has only its 80-byte header: the
settings go there as text ("alex-3d-skills cadlib PETG walls=3 infill=40%"), which slicers ignore.
"""
import bpy, os, struct, zipfile
from xml.sax.saxutils import quoteattr, escape
from mathutils import Vector, Matrix
from . import asm
import cadmat

CAD_NS = "https://github.com/alexchunlin/alex-3d-skills/print-settings"


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


def declared(ob):
    """The print settings set on the part (asm.part custom properties), in cadmat.PRINT_KEYS order."""
    return {k: ob[k] for k in cadmat.PRINT_KEYS if k in ob.keys()}


def settings_header(st):
    t = "alex-3d-skills cadlib" + "".join(" %s" % st["material"] if k == "material" else " %s=%g%s" % (k, st[k], "%" if k == "infill" else "")
                                          for k in st)
    return t.encode("ascii", "replace")[:80]


def write_3mf(path, name, tris, st, qty=1):
    """A 3MF of one part's print-orientation triangles, `qty` build items side by side along X, with the declared print
    settings `st` as per-object metadata (core spec) and as Bambu Studio / OrcaSlicer per-object keys."""
    idx, verts, faces = {}, [], []
    for t in tris:
        f = []
        for v in t:
            k = (round(v.x, 5), round(v.y, 5), round(v.z, 5))
            if k not in idx:
                idx[k] = len(verts)
                verts.append(k)
            f.append(idx[k])
        if len(set(f)) == 3:
            faces.append(f)
    w = (max(v[0] for v in verts) - min(v[0] for v in verts)) + 5.0 if verts else 0.0
    md = "".join('<metadata name="cad:%s" type="%s">%s</metadata>' % (k, "xs:string" if k == "material" else "xs:double", escape(str(v)))
                 for k, v in st.items())
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:cad=%s>'
             '<metadata name="Application">alex-3d-skills cadlib</metadata><metadata name="Title">%s</metadata>'
             '<resources><object id="1" name=%s type="model">%s<mesh><vertices>%s</vertices><triangles>%s</triangles></mesh>'
             '</object></resources><build>%s</build></model>') % (
        quoteattr(CAD_NS), escape(name), quoteattr(name), "<metadatagroup>%s</metadatagroup>" % md if md else "",
        "".join('<vertex x="%g" y="%g" z="%g"/>' % v for v in verts),
        "".join('<triangle v1="%d" v2="%d" v3="%d"/>' % tuple(f) for f in faces),
        "".join('<item objectid="1" transform="1 0 0 0 1 0 0 0 1 %g 0 0"/>' % (j * w) for j in range(qty)))
    keys = [("name", name)]
    for k, v in st.items():
        if k in cadmat.SLICER_KEYS:
            sk, fmt = cadmat.SLICER_KEYS[k]
            keys += [(x, fmt % v) for x in (sk if isinstance(sk, tuple) else (sk,))]
    cfg = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <object id="1">\n%s    <part id="1" subtype="normal_part">\n'
           '      <metadata key="name" value=%s/>\n    </part>\n  </object>\n</config>\n') % (
        "".join('    <metadata key="%s" value=%s/>\n' % (k, quoteattr(v)) for k, v in keys), quoteattr(name))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
                   '<Default Extension="config" ContentType="text/xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
                   'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/model_settings.config", cfg)


def export_stls(stl_dir, clean=True, threemf=True):
    """One STL (and with threemf, one 3MF carrying the part's print settings) per unique `stl` name."""
    os.makedirs(stl_dir, exist_ok=True)
    asm.set_pose()
    if clean:
        for f in os.listdir(stl_dir):
            if f.endswith((".stl", ".3mf")):
                os.remove(os.path.join(stl_dir, f))
    done, first = {}, {}
    for ob in sorted(bpy.data.collections["Printed"].objects, key=lambda o: o.name):
        stl = ob.get("stl")
        if stl:
            done[stl] = done.get(stl, 0) + 1
            first.setdefault(stl, ob)
    for stl, ob in first.items():
        tris, st = print_tris(ob), declared(ob)
        write_stl(os.path.join(stl_dir, stl + ".stl"), tris, settings_header(st))
        if threemf:
            write_3mf(os.path.join(stl_dir, stl + ".3mf"), stl, tris, st, done[stl])
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
