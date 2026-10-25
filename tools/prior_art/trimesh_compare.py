"""Prior-art measurement: what trimesh + manifold3d can check from the exported STLs alone.

    uv run --no-project --with trimesh --with manifold3d --with numpy python -I trimesh_compare.py <stl_dir>
"""
import sys, os, time, json
import trimesh
import manifold3d as m3d

d = sys.argv[1]
t0 = time.time()
rows = []
for f in sorted(os.listdir(d)):
    if not f.endswith(".stl"):
        continue
    m = trimesh.load(os.path.join(d, f))
    ext = m.extents
    fits = sorted(ext[:2])[0] <= 256 and sorted(ext[:2])[1] <= 256 and ext[2] <= 256
    n = m.face_normals
    over = float(m.area_faces[(n[:, 2] < -0.7071) & (m.triangles_center[:, 2] > 0.25)].sum())
    man = m3d.Manifold(m3d.Mesh(vert_properties=m.vertices.astype("float32"), tri_verts=m.faces.astype("uint32")))
    rows.append({"stl": f, "watertight": bool(m.is_watertight), "volume": round(float(m.volume), 1),
                 "manifold3d_status": str(man.status()), "fits_P1S": bool(fits), "overhang_mm2": round(over, 1)})
dt = time.time() - t0
print(json.dumps({"n": len(rows), "seconds": round(dt, 2), "all_watertight": all(r["watertight"] for r in rows),
                  "not_watertight": [r["stl"] for r in rows if not r["watertight"]], "rows": rows[:3]}, indent=1))
