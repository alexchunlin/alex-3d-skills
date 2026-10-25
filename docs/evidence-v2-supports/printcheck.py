# Independent support check on exported STLs, as-is (assumes they are in print orientation, bed = min z).
# Finds: (1) floating islands: local-minimum vertices / flat-down regions above the bed whose boundary
# does not continue downward (start in mid-air -> support required); (2) unanchored or partly anchored
# ceilings (bridges), with span; (3) sloped overhang regions steeper than 45 deg, by connected region size.
import bpy, bmesh, sys, json, math, glob, os
from mathutils import Vector
args = sys.argv[sys.argv.index("--") + 1:]
stl_dir, out = args[0], args[1]
COS45 = math.cos(math.radians(45)); EPS = 0.05
res = []
for path in sorted(glob.glob(os.path.join(stl_dir, "*.stl"))):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.stl_import(filepath=path)
    o = bpy.context.selected_objects[0]
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.faces.ensure_lookup_table(); bm.verts.ensure_lookup_table()
    zmin = min(v.co.z for v in bm.verts); zmax = max(v.co.z for v in bm.verts)
    def zc(f): return sum(v.co.z for v in f.verts) / len(f.verts) - zmin
    down = {f.index for f in bm.faces if f.normal.z < -COS45 - 1e-3 and zc(f) > 0.25}
    # connected regions of downward faces
    seen, regions = set(), []
    for i in down:
        if i in seen: continue
        stack, reg = [i], []
        seen.add(i)
        while stack:
            f = bm.faces[stack.pop()]; reg.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index in down and g.index not in seen:
                        seen.add(g.index); stack.append(g.index)
        regions.append(reg)
    issues = []
    for reg in regions:
        ids = {f.index for f in reg}
        area = sum(f.calc_area() for f in reg)
        vz = [v.co.z for f in reg for v in f.verts]
        rz = min(vz) - zmin
        xs = [v.co.x for f in reg for v in f.verts]; ys = [v.co.y for f in reg for v in f.verts]
        ext = (max(xs) - min(xs), max(ys) - min(ys))
        flat = all(f.normal.z < -0.985 for f in reg)
        # boundary edges and whether the neighbouring face descends below the edge (wall from below = anchor)
        blen = alen = 0.0
        for f in reg:
            for e in f.edges:
                others = [g for g in e.link_faces if g.index not in ids]
                if not others: continue
                L = e.calc_length(); blen += L
                ez = min(v.co.z for v in e.verts)
                if any(min(v.co.z for v in g.verts) < ez - 0.2 for g in others):
                    alen += L
        anchored = alen / blen if blen else 0.0
        # lowest point of a sloped region: does anything continue downward from it?
        kind = "ceiling" if flat else "slope"
        floating = anchored < 0.02
        span = min(ext)
        sev = None
        if floating and area > 1.0:
            sev = "SUPPORT: starts in mid-air (island)"
        elif kind == "ceiling" and anchored < 0.35 and span > 3:
            sev = "SUPPORT?: ceiling mostly unanchored (cantilever, %.0f%% anchored)" % (anchored * 100)
        elif kind == "ceiling" and span > 25:
            sev = "BRIDGE > 25 mm"
        elif kind == "slope" and area > 25 and max(ext) > 6:
            sev = "OVERHANG > 45 deg, %.0f mm2" % area
        if sev:
            c = Vector((sum(xs) / len(xs), sum(ys) / len(ys), min(vz)))
            issues.append({"issue": sev, "area_mm2": round(area, 1), "z_mm": round(rz, 1), "extent_mm": [round(e, 1) for e in ext],
                           "anchored_frac": round(anchored, 2), "at_print_frame": [round(c.x, 1), round(c.y, 1), round(c.z - zmin, 1)]})
    # isolated local-minimum vertices above the bed (point islands, e.g. a downward cone tip)
    pts = 0
    for v in bm.verts:
        if v.co.z - zmin < 0.3: continue
        nb = [e.other_vert(v).co.z for e in v.link_edges]
        if nb and all(z > v.co.z + 0.05 for z in nb):
            pts += 1
            if pts <= 3: issues.append({"issue": "SUPPORT: point island (local minimum vertex)", "z_mm": round(v.co.z - zmin, 1), "at_print_frame": [round(v.co.x, 1), round(v.co.y, 1)]})
    bed = sum(f.calc_area() for f in bm.faces if f.normal.z < -0.999 and zc(f) < 0.05)
    res.append({"stl": os.path.basename(path), "height_mm": round(zmax - zmin, 1), "bed_mm2": round(bed, 1), "issues": issues})
    bm.free()
json.dump(res, open(out, "w"), indent=1)
