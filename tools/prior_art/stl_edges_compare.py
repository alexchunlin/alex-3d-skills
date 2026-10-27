"""Non-manifold edges on exported STLs, four ways: which method a `cad printcheck` STL topology check should use.

    uv run --no-project --python 3.12 --with trimesh==5.2.0 --with numpy==2.5.4 \
        python -I stl_edges_compare.py [-v] a.stl [b.stl ...] > out.json

A binary STL is a triangle soup in float32, so a topology count first has to weld vertices. Per part:
- `trimesh_watertight`: trimesh 5.2.0's `is_watertight` after its default load (merges vertices, keeps the faces
  that collapse to a line or a point once their float32 corners coincide; dfam-check reports this flag).
- `exact`: weld only bit-identical vertices, drop collapsed faces (two corners the same vertex), count edges not shared
  by exactly 2 faces (`gt2`: shared by 3 or more, `lt2`: open).
- `grid_1e-4`: the same after snapping vertices to a 0.1 um grid.
- `rule`: the suggested printcheck check, a warn: exact weld, drop collapsed faces, edges shared by more than 2 faces
  and at least 0.01 mm long. It ignores open edges left by slivers, which a slicer closes up.
`collapsed_faces` counts the dropped faces; `-v` lists each flagged edge's ends and length.
"""
import os, struct, sys
import json
import numpy as np
import trimesh

verbose = "-v" in sys.argv
paths = [a for a in sys.argv[1:] if a != "-v"]


def read(path):
    d = open(path, "rb").read()
    n = struct.unpack("<I", d[80:84])[0]
    r = np.frombuffer(d, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=n, offset=84)
    return r["v"].astype(np.float64)


def edges(T, grid=None):
    V = T.reshape(-1, 3)
    key = np.round(V / grid).astype(np.int64) if grid else V
    _, vid = np.unique(key, axis=0, return_inverse=True)
    vid = vid.reshape(-1, 3)
    keep = (vid[:, 0] != vid[:, 1]) & (vid[:, 1] != vid[:, 2]) & (vid[:, 0] != vid[:, 2])
    pos = np.zeros((vid.max() + 1, 3))
    pos[vid.ravel()] = V
    f = vid[keep]
    E = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    ue, cnt = np.unique(E, axis=0, return_counts=True)
    length = np.linalg.norm(pos[ue[:, 0]] - pos[ue[:, 1]], axis=1)
    return ue, cnt, length, pos, int((~keep).sum())


rows = []
for path in paths:
    T = read(path)
    m = trimesh.load(path)
    row = {"part": os.path.splitext(os.path.basename(path))[0], "faces": len(T),
           "trimesh_watertight": bool(m.is_watertight)}
    for label, grid in (("exact", None), ("grid_1e-4", 1e-4)):
        ue, cnt, length, pos, dropped = edges(T, grid)
        row[label] = {"bad": int((cnt != 2).sum()), "gt2": int((cnt > 2).sum()), "lt2": int((cnt < 2).sum()),
                      "collapsed_faces": dropped}
        if grid is None:
            bad = (cnt > 2) & (length >= 0.01)
            row["rule"] = int(bad.sum())
            if verbose:
                row["rule_edges"] = [{"a": [round(x, 4) for x in pos[e[0]]], "b": [round(x, 4) for x in pos[e[1]]],
                                      "faces": int(c), "len_mm": round(float(l), 4)}
                                     for e, c, l in zip(ue[cnt != 2], cnt[cnt != 2], length[cnt != 2])][:20]
    rows.append(row)

flag = lambda k: sorted(r["part"] for r in rows if (r[k]["bad"] if isinstance(r[k], dict) else r[k]))
print(json.dumps({"n": len(rows), "trimesh": trimesh.__version__,
                  "trimesh_not_watertight": sorted(r["part"] for r in rows if not r["trimesh_watertight"]),
                  "trimesh_only_collapsed": sorted(r["part"] for r in rows if not r["trimesh_watertight"]
                                                   and r["exact"]["bad"] == 0 and r["exact"]["collapsed_faces"]),
                  "exact_flags": flag("exact"), "grid_flags": flag("grid_1e-4"), "rule_flags": flag("rule"),
                  "rows": [r for r in rows if not r["trimesh_watertight"] or r["exact"]["bad"] or r["grid_1e-4"]["bad"]]},
                 indent=1))
