"""Prior-art measurement: Blender's 3D-Print Toolbox extension (print3d_toolbox 1.5.0) against `cad printcheck`.

    Blender -b --factory-startup --python-exit-code 1 -P print3d_toolbox_compare.py -- \
        <pkg_dir> <stl_dir> <printcheck.json> [extra.stl ...] > result.json

<pkg_dir> holds a copy of the extension's `source/` folder named `print3d_toolbox` (the extension is not installed:
it is imported from there and registered for this run only, so Blender's user config is untouched). Each check's
`main_check` runs directly on the imported STL, with the toolbox's own settings: overhang 45 deg, thickness 1.2 mm
(FDM, text-to-cad's process-limits row) and 0.8 mm. The overhang check counts faces, so the script also sums their
area and the area of those off the bed (centroid z > min z + 0.1) to give it the same footing as dfam_compare.py.
"""
import json, os, sys, time
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
pkg_dir, stl_dir, pc_path, extra = argv[0], argv[1], argv[2], argv[3:]
sys.path.insert(0, pkg_dir)
import print3d_toolbox as tb
from print3d_toolbox import report
from print3d_toolbox.operators import analyze as an
tb.register()
props = bpy.context.scene.print3d_toolbox
props.angle_overhang = 0.785398  # 45 deg (the default)

verdict = {}
for p in json.load(open(pc_path))["parts"]:
    st = [x.get("status") for x in p.get("findings") or []]
    verdict[p["stl"]] = "fail" if "fail" in st else ("warn" if st else "ok")


def run(check, ob):
    data = []
    check.main_check(ob, data)
    return {d.name: (d.value, list(d.indices) if d.indices is not None else None) for d in data}


rows, t_all = [], time.time()
files = sorted(os.path.join(stl_dir, f) for f in os.listdir(stl_dir) if f.endswith(".stl")) + extra
for path in files:
    name = os.path.splitext(os.path.basename(path))[0]
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.wm.stl_import(filepath=path)
    ob = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = ob
    t = time.time()
    solid = run(an.MESH_OT_check_solid, ob)
    inter = run(an.MESH_OT_check_intersections, ob)
    over = run(an.MESH_OT_check_overhang, ob)["Overhang Faces"][1]
    me, zmin = ob.data, min(v.co.z for v in ob.data.vertices)
    area = sum(me.polygons[i].area for i in over)
    off_bed = sum(me.polygons[i].area for i in over if me.polygons[i].center.z > zmin + 0.1)
    thick = {}
    for t_mm in (1.2, 0.8):
        props.thickness_min = t_mm   # the scene unit is 1 mm per Blender unit here (STL import, no scaling)
        idx = run(an.MESH_OT_check_thick, ob)["Thin Faces"][1]
        thick[t_mm] = {"faces": len(idx), "area_mm2": round(sum(me.polygons[i].area for i in idx), 1)}
    rows.append({"part": name, "printcheck": verdict.get(name, "n/a"), "faces": len(me.polygons),
                 "non_manifold_edges": int(solid["Non-manifold Edges"][0]),
                 "self_intersect_faces": int(inter["Intersect Faces"][0]),
                 "overhang_faces": len(over), "overhang_mm2": round(area, 1), "overhang_off_bed_mm2": round(off_bed, 1),
                 "thin_lt_1.2": thick[1.2], "thin_lt_0.8": thick[0.8], "seconds": round(time.time() - t, 2)})

fails = [r for r in rows if r["printcheck"] == "fail"]
passing = [r for r in rows if r["printcheck"] in ("ok", "warn")]
sweep = []
for thr in (0, 25, 100, 200, 400, 800):
    hit = [r["part"] for r in fails if r["overhang_off_bed_mm2"] > thr]
    fp = [r["part"] for r in passing if r["overhang_off_bed_mm2"] > thr]
    sweep.append({"off_bed_area_gt_mm2": thr, "printcheck_fails_flagged": f"{len(hit)}/{len(fails)}",
                  "passing_parts_flagged": f"{len(fp)}/{len(passing)}"})
sys.stdout.write("\nRESULT " + json.dumps({
    "n": len(rows), "seconds": round(time.time() - t_all, 1), "sweep": sweep,
    "parts_with_overhang_faces": sum(r["overhang_faces"] > 0 for r in rows),
    "rows": sorted(rows, key=lambda r: -r["overhang_off_bed_mm2"])}) + "\n")
