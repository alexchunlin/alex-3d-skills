"""Why cadcheck counts 0 non-manifold edges on a part whose STL has some: coincident vertices the model never welds.

    Blender -b model.blend --factory-startup --python-exit-code 1 -P nm_model_vertices.py -- OBJ [OBJ ...]

Per object (evaluated mesh, float64, in the print frame before the STL export shifts it onto the bed): bmesh's
non-manifold edge count (what cadcheck's `check_parts` reads; `is_manifold` is topological, so two distinct vertices
at one point are two vertices), then how many pairs of distinct vertices are exactly equal or within 1 um, and the
closest 10 with where they sit. An STL stores positions, not indices, so any welder (a slicer's, trimesh's) turns
each such pair into one vertex and the two surfaces meeting there into a 4-face edge.
"""
import sys
import bmesh, bpy
import numpy as np

for name in sys.argv[sys.argv.index("--") + 1:]:
    o = bpy.data.objects[name]
    dg = bpy.context.evaluated_depsgraph_get()
    me = o.evaluated_get(dg).to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    co = np.array([v.co[:] for v in me.vertices], dtype=np.float64)
    M = np.array(o.matrix_world, dtype=np.float64)
    R = np.array(o["print_rot"], dtype=np.float64) if "print_rot" in o.keys() else np.eye(3)
    P = (R @ (co @ M[:3, :3].T + M[:3, 3]).T).T
    order = np.lexsort(P.T[::-1])
    S = P[order]
    near = []
    for i in range(len(S) - 1):            # neighbours in lexicographic order, then a short scan for 1 um matches
        for j in range(i + 1, min(i + 8, len(S))):
            d = float(np.linalg.norm(S[i] - S[j]))
            if d < 1e-3:
                near.append((int(order[i]), int(order[j]), d))
    print("NM_MODEL", name, "bmesh_non_manifold_edges", nm, "verts", len(P),
          "coincident_pairs_exact", sum(1 for *_, d in near if d == 0.0),
          "within_1um", len(near), "max_um", round(1e3 * max((d for *_, d in near), default=0.0), 4))
    for a, b, d in sorted(near, key=lambda x: x[2])[:10]:
        print("NM_MODEL_PAIR", name, [round(float(x), 4) for x in P[a]], "d_um", round(1e3 * d, 4))
    o.evaluated_get(dg).to_mesh_clear()
